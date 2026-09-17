"""Rev 1.3 §§50-51, 151, 154-155, 168-170 — capability/artifact registry, admission, HOT index.

VAN owns workflow lineage independently of n8n's runtime storage (§50), so an
artifact is keyed by its digests and its capability, and n8n's workflow ID is a
foreign runtime reference stored alongside — never the identity.

Two rules from the blueprint are enforced structurally rather than by convention:

* §151 *"Never overwrite an admitted artifact row. A repair creates a new
  version."* — :meth:`AutomationRegistry.record_artifact` refuses to mutate an
  artifact once it is ADMITTED or HOT.
* §154 *"No partial admission."* — every lifecycle transition is a single
  conditional UPDATE guarded by the expected current state.
"""

from __future__ import annotations

import time
from typing import Any

from van_gateway.automation.canonical import digest, new_id
from van_gateway.automation.models import (
    LIFECYCLE_TRANSITIONS,
    AutomationWorkflowArtifact,
    IntentSignature,
    WorkflowCapability,
    WorkflowEngine,
    WorkflowLifecycle,
)
from van_gateway.models import ActionClass
from van_gateway.storage.db import Store


class RegistryError(ValueError):
    """Raised on an illegal lifecycle transition or an attempt to mutate admitted state."""


_IMMUTABLE_STATES = {WorkflowLifecycle.ADMITTED, WorkflowLifecycle.HOT}


class AutomationRegistry:
    """Capability and artifact lineage, plus the admission state machine."""

    def __init__(self, store: Store) -> None:
        self.store = store

    # ------------------------------------------------------------ capabilities

    async def upsert_capability(self, capability: WorkflowCapability) -> WorkflowCapability:
        now = int(time.time() * 1000)
        await self.store.execute(
            """
            INSERT INTO automation_capabilities(
              capability_id, semantic_name, engine, runtime_workflow_ref, action_class,
              mutates_state, input_schema_json, output_schema_json, allowed_principals_json,
              allowed_origin_channels_json, latency_class, duration_class, required_context_json,
              required_credentials_json, verifier_type, idempotency_policy, evidence_policy,
              lifecycle_state, workflow_ir_digest, policy_version, compiler_version,
              created_at_ms, updated_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(capability_id) DO UPDATE SET
              semantic_name=excluded.semantic_name,
              runtime_workflow_ref=excluded.runtime_workflow_ref,
              action_class=excluded.action_class,
              mutates_state=excluded.mutates_state,
              lifecycle_state=excluded.lifecycle_state,
              workflow_ir_digest=excluded.workflow_ir_digest,
              updated_at_ms=excluded.updated_at_ms
            """,
            (
                capability.capability_id, capability.semantic_name, capability.engine.value,
                capability.runtime_workflow_ref, capability.action_class.value,
                1 if capability.mutates_state else 0, Store.dumps(capability.input_schema),
                Store.dumps(capability.output_schema), Store.dumps(sorted(capability.allowed_principals)),
                Store.dumps(sorted(capability.allowed_origin_channels)), capability.latency_class,
                capability.duration_class, Store.dumps(capability.required_context),
                Store.dumps(capability.required_credentials), capability.verifier_type,
                capability.idempotency_policy, capability.evidence_policy,
                capability.lifecycle_state.value, capability.workflow_ir_digest,
                capability.policy_version, capability.compiler_version,
                capability.created_at_ms or now, now,
            ),
        )
        return capability

    async def get_capability(self, capability_id: str) -> WorkflowCapability | None:
        row = await self.store.fetchone(
            "SELECT * FROM automation_capabilities WHERE capability_id = ?", (capability_id,)
        )
        return self._row_to_capability(row) if row is not None else None

    # --------------------------------------------------------------- artifacts

    async def record_artifact(self, artifact: AutomationWorkflowArtifact) -> AutomationWorkflowArtifact:
        existing = await self.get_artifact(artifact.artifact_id)
        if existing is not None and existing.lifecycle_state in _IMMUTABLE_STATES:
            # §151 — a repair creates a new version; it never rewrites history.
            raise RegistryError("admitted_artifact_is_immutable")
        await self.store.execute(
            """
            INSERT INTO automation_artifacts(
              artifact_id, capability_id, version, workflow_ir_digest, compiled_semantic_digest,
              compiled_full_digest, n8n_workflow_id, compiler_version, node_catalog_version,
              policy_version, source_refs_json, validation_report_digest, lifecycle_state,
              created_at_ms, validated_at_ms, admitted_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(artifact_id) DO UPDATE SET
              compiled_semantic_digest=excluded.compiled_semantic_digest,
              compiled_full_digest=excluded.compiled_full_digest,
              n8n_workflow_id=excluded.n8n_workflow_id,
              validation_report_digest=excluded.validation_report_digest,
              lifecycle_state=excluded.lifecycle_state
            """,
            (
                artifact.artifact_id, artifact.capability_id, artifact.version,
                artifact.workflow_ir_digest, artifact.compiled_semantic_digest,
                artifact.compiled_full_digest, artifact.n8n_workflow_id, artifact.compiler_version,
                artifact.node_catalog_version, artifact.policy_version,
                Store.dumps(artifact.source_refs), artifact.validation_report_digest,
                artifact.lifecycle_state.value, artifact.created_at_ms, artifact.validated_at_ms,
                artifact.admitted_at_ms,
            ),
        )
        return artifact

    async def get_artifact(self, artifact_id: str) -> AutomationWorkflowArtifact | None:
        row = await self.store.fetchone(
            "SELECT * FROM automation_artifacts WHERE artifact_id = ?", (artifact_id,)
        )
        return self._row_to_artifact(row) if row is not None else None

    async def next_version(self, capability_id: str) -> int:
        row = await self.store.fetchone(
            "SELECT COALESCE(MAX(version), 0) AS v FROM automation_artifacts WHERE capability_id = ?",
            (capability_id,),
        )
        return int(row["v"]) + 1 if row is not None else 1

    async def admitted_artifact(self, capability_id: str) -> AutomationWorkflowArtifact | None:
        row = await self.store.fetchone(
            "SELECT * FROM automation_artifacts WHERE capability_id = ? "
            "AND lifecycle_state IN ('ADMITTED','HOT') ORDER BY version DESC LIMIT 1",
            (capability_id,),
        )
        return self._row_to_artifact(row) if row is not None else None

    # -------------------------------------------------------------- transitions

    async def transition(
        self,
        artifact_id: str,
        *,
        expected: WorkflowLifecycle,
        target: WorkflowLifecycle,
        validation_report_digest: str | None = None,
        n8n_workflow_id: str | None = None,
        now_ms: int | None = None,
    ) -> AutomationWorkflowArtifact:
        """§§154-155 — one transaction, guarded by the expected current state."""
        if target not in LIFECYCLE_TRANSITIONS[expected]:
            raise RegistryError(f"illegal_transition:{expected.value}->{target.value}")
        now = int(time.time() * 1000) if now_ms is None else now_ms

        sets = ["lifecycle_state = ?"]
        params: list[Any] = [target.value]
        if target is WorkflowLifecycle.VALIDATED:
            sets.append("validated_at_ms = ?")
            params.append(now)
        if target is WorkflowLifecycle.ADMITTED:
            sets.append("admitted_at_ms = ?")
            params.append(now)
        if validation_report_digest is not None:
            sets.append("validation_report_digest = ?")
            params.append(validation_report_digest)
        if n8n_workflow_id is not None:
            sets.append("n8n_workflow_id = ?")
            params.append(n8n_workflow_id)
        params.extend([artifact_id, expected.value])

        async with self.store.connection() as db:
            cur = await db.execute(
                f"UPDATE automation_artifacts SET {', '.join(sets)} "
                "WHERE artifact_id = ? AND lifecycle_state = ?",
                tuple(params),
            )
            if cur.rowcount != 1:
                await db.rollback()
                raise RegistryError("transition_precondition_failed")
            # Capability lifecycle follows its admitted artifact.
            if target in (WorkflowLifecycle.ADMITTED, WorkflowLifecycle.HOT, WorkflowLifecycle.REVOKED):
                await db.execute(
                    "UPDATE automation_capabilities SET lifecycle_state = ?, updated_at_ms = ? "
                    "WHERE capability_id = (SELECT capability_id FROM automation_artifacts "
                    "WHERE artifact_id = ?)",
                    (target.value, now, artifact_id),
                )
            await db.commit()

        artifact = await self.get_artifact(artifact_id)
        assert artifact is not None
        return artifact

    # ------------------------------------------------------------------ rows

    @staticmethod
    def _row_to_capability(row: Any) -> WorkflowCapability:
        import json

        return WorkflowCapability(
            capability_id=str(row["capability_id"]),
            semantic_name=str(row["semantic_name"]),
            engine=WorkflowEngine(str(row["engine"])),
            runtime_workflow_ref=str(row["runtime_workflow_ref"]) if row["runtime_workflow_ref"] else None,
            action_class=ActionClass(str(row["action_class"])),
            mutates_state=bool(row["mutates_state"]),
            input_schema=json.loads(row["input_schema_json"] or "{}"),
            output_schema=json.loads(row["output_schema_json"] or "{}"),
            allowed_principals=json.loads(row["allowed_principals_json"] or "[]"),
            allowed_origin_channels=json.loads(row["allowed_origin_channels_json"] or "[]"),
            latency_class=str(row["latency_class"]),
            duration_class=str(row["duration_class"]),
            required_context=json.loads(row["required_context_json"] or "[]"),
            required_credentials=json.loads(row["required_credentials_json"] or "[]"),
            verifier_type=str(row["verifier_type"]),
            idempotency_policy=str(row["idempotency_policy"]),
            evidence_policy=str(row["evidence_policy"]),
            lifecycle_state=WorkflowLifecycle(str(row["lifecycle_state"])),
            workflow_ir_digest=str(row["workflow_ir_digest"]),
            policy_version=str(row["policy_version"]),
            compiler_version=str(row["compiler_version"]),
            created_at_ms=int(row["created_at_ms"]),
            updated_at_ms=int(row["updated_at_ms"]),
        )

    @staticmethod
    def _row_to_artifact(row: Any) -> AutomationWorkflowArtifact:
        import json

        return AutomationWorkflowArtifact(
            artifact_id=str(row["artifact_id"]),
            capability_id=str(row["capability_id"]),
            version=int(row["version"]),
            workflow_ir_digest=str(row["workflow_ir_digest"]),
            compiled_semantic_digest=str(row["compiled_semantic_digest"]),
            compiled_full_digest=str(row["compiled_full_digest"]),
            n8n_workflow_id=str(row["n8n_workflow_id"]) if row["n8n_workflow_id"] else None,
            compiler_version=str(row["compiler_version"]),
            node_catalog_version=str(row["node_catalog_version"]),
            policy_version=str(row["policy_version"]),
            source_refs=json.loads(row["source_refs_json"] or "[]"),
            validation_report_digest=str(row["validation_report_digest"])
            if row["validation_report_digest"]
            else None,
            lifecycle_state=WorkflowLifecycle(str(row["lifecycle_state"])),
            created_at_ms=int(row["created_at_ms"]),
            validated_at_ms=int(row["validated_at_ms"]) if row["validated_at_ms"] else None,
            admitted_at_ms=int(row["admitted_at_ms"]) if row["admitted_at_ms"] else None,
        )


class HotWorkflowIndex:
    """§§25, 168-169 — in-memory HOT lookup with no model, no VEKL, no n8n discovery.

    §57 targets p95 <= 10 ms for this lookup, which is only achievable if it never
    touches the network. The index is rebuilt from the registry at startup and on
    admission; a miss falls through to the WARM/COLD path rather than guessing.
    """

    def __init__(self) -> None:
        self._by_signature: dict[str, str] = {}
        self._versions: dict[str, int] = {}
        self._refs: dict[tuple[str, int], str] = {}
        self._revision = 0

    @staticmethod
    def signature_key(signature: IntentSignature) -> str:
        """§170 — canonicalized so wording never affects the key."""
        canonical = signature.canonical()
        return "|".join(
            [
                canonical["goal_class"],
                canonical["source_class"],
                canonical["destination_class"],
                canonical["mutation_class"],
            ]
        )

    def publish(
        self, signature: IntentSignature, capability_id: str, version: int, workflow_ref: str
    ) -> None:
        key = self.signature_key(signature)
        self._by_signature[key] = capability_id
        self._versions[capability_id] = version
        self._refs[(capability_id, version)] = workflow_ref
        self._revision += 1

    def withdraw(self, capability_id: str) -> None:
        """Used on DEGRADED/REVOKED so a broken capability stops being HOT (§77)."""
        for key, value in list(self._by_signature.items()):
            if value == capability_id:
                del self._by_signature[key]
        version = self._versions.pop(capability_id, None)
        if version is not None:
            self._refs.pop((capability_id, version), None)
        self._revision += 1

    def lookup(self, signature: IntentSignature) -> tuple[str, int, str] | None:
        capability_id = self._by_signature.get(self.signature_key(signature))
        if capability_id is None:
            return None
        version = self._versions.get(capability_id)
        if version is None:
            return None
        ref = self._refs.get((capability_id, version))
        if ref is None:
            return None
        return capability_id, version, ref

    @property
    def revision(self) -> int:
        return self._revision

    @property
    def size(self) -> int:
        return len(self._by_signature)

    async def rebuild(self, store: Store) -> int:
        """§273 — startup reconciliation from durable state."""
        self._by_signature.clear()
        self._versions.clear()
        self._refs.clear()
        rows = await store.fetchall(
            "SELECT c.capability_id, c.semantic_name, c.action_class, a.version, "
            "       COALESCE(a.n8n_workflow_id, '') AS ref "
            "FROM automation_capabilities c "
            "JOIN automation_artifacts a ON a.capability_id = c.capability_id "
            "WHERE c.lifecycle_state = 'HOT' AND a.lifecycle_state IN ('ADMITTED','HOT')"
        )
        for row in rows:
            parts = str(row["semantic_name"]).split(".")
            signature = IntentSignature(
                goal_class=parts[0] if parts else "UNKNOWN",
                source_class=parts[1] if len(parts) > 1 else "UNKNOWN",
                destination_class=parts[2] if len(parts) > 2 else "UNKNOWN",
                mutation_class=ActionClass(str(row["action_class"])),
            )
            self.publish(signature, str(row["capability_id"]), int(row["version"]), str(row["ref"]))
        return len(self._by_signature)


__all__ = ["AutomationRegistry", "HotWorkflowIndex", "RegistryError", "digest", "new_id"]
