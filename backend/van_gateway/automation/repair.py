"""Rev 1.3 §§78, 243-245 — workflow repair, with lineage.

§78 ends with the rule that governs this module: *"Do not mutate the admitted
production workflow in place without lineage."* A repair therefore never edits
an artifact. It produces a candidate, and promotion is the ordinary admission
path with the old version marked SUPERSEDED — so a rollback is always just the
previous artifact, still sitting there.

§244 is the other half, and it is the part that is easy to get wrong: not every
failure deserves a new workflow. A transient HTTP timeout must not trigger
regeneration. The decision function here is deliberately conservative, and it
refuses to guess: an unrecognised failure goes to SECURITY_REVIEW_REQUIRED or
IR_REPAIR_REQUIRED rather than to an automatic recompile.

Nothing in the repair packet is owner memory or an unrelated secret (§243). It
carries digests, error codes and catalog state — the shapes a diagnosis needs,
never the values a leak would want.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from van_gateway.automation.canonical import new_id
from van_gateway.automation.models import AutomationWorkflowArtifact, WorkflowLifecycle
from van_gateway.automation.registry import AutomationRegistry, RegistryError
from van_gateway.automation.workflow_health import FailureClass, WorkflowHealthService
from van_gateway.storage.db import Store


class RepairDecision(str, Enum):
    """§244 — the full set of outcomes. There is no 'regenerate and hope'."""

    RETRY_NO_CHANGE = "RETRY_NO_CHANGE"
    REFRESH_CREDENTIAL = "REFRESH_CREDENTIAL"
    RECOMPILE_SAME_IR = "RECOMPILE_SAME_IR"
    IR_REPAIR_REQUIRED = "IR_REPAIR_REQUIRED"
    CONNECTOR_DEGRADED = "CONNECTOR_DEGRADED"
    EXTERNAL_API_CHANGED = "EXTERNAL_API_CHANGED"
    SECURITY_REVIEW_REQUIRED = "SECURITY_REVIEW_REQUIRED"

    @property
    def needs_new_ir(self) -> bool:
        return self in (RepairDecision.IR_REPAIR_REQUIRED, RepairDecision.EXTERNAL_API_CHANGED)

    @property
    def is_automatic(self) -> bool:
        """Whether VAN may act on this without asking anyone."""
        return self in (
            RepairDecision.RETRY_NO_CHANGE,
            RepairDecision.RECOMPILE_SAME_IR,
        )


@dataclass(frozen=True)
class RepairPacket:
    """§243 — exactly what a diagnosis is given, and nothing else.

    Note what is absent: credential values, owner memory, evidence contents. A
    repair works from shapes and error codes.
    """

    capability_id: str
    failing_artifact_id: str
    failing_run_id: str | None
    failure_class: FailureClass
    error_code: str | None
    failing_node: str | None
    input_schema_digest: str | None
    output_schema_digest: str | None
    node_catalog_version: str
    compiler_version: str
    policy_version: str
    previous_successful_artifact_id: str | None
    external_observations: dict[str, Any] = field(default_factory=dict)
    repair_patterns: tuple[dict[str, Any], ...] = ()

    def as_diagnosis_input(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "failure_class": self.failure_class.value,
            "error_code": self.error_code,
            "failing_node": self.failing_node,
            "input_schema_digest": self.input_schema_digest,
            "output_schema_digest": self.output_schema_digest,
            "node_catalog_version": self.node_catalog_version,
            "compiler_version": self.compiler_version,
            "policy_version": self.policy_version,
            "previous_successful_artifact_id": self.previous_successful_artifact_id,
            "external_observations": dict(self.external_observations),
            "repair_patterns": [dict(p) for p in self.repair_patterns],
        }


def decide(packet: RepairPacket, *, attempt: int = 1) -> RepairDecision:
    """§244 — classify before acting. Conservative on purpose.

    `attempt` matters for exactly one case: a transient failure is worth one
    plain retry, and after that it stops being plausibly transient.
    """
    match packet.failure_class:
        case FailureClass.SECURITY:
            return RepairDecision.SECURITY_REVIEW_REQUIRED
        case FailureClass.TRANSIENT:
            # §244 — never regenerate a whole workflow for a timeout.
            return (
                RepairDecision.RETRY_NO_CHANGE
                if attempt <= 1
                else RepairDecision.CONNECTOR_DEGRADED
            )
        case FailureClass.CREDENTIAL:
            return RepairDecision.REFRESH_CREDENTIAL
        case FailureClass.CONNECTOR:
            return RepairDecision.CONNECTOR_DEGRADED
        case FailureClass.SCHEMA:
            # The target's shape moved. That is an IR problem, not a compile one.
            return RepairDecision.EXTERNAL_API_CHANGED
        case FailureClass.VERIFICATION:
            # The engine said it worked and the world disagreed. Recompiling the
            # same IR cannot fix that; the IR itself is wrong about something.
            return RepairDecision.IR_REPAIR_REQUIRED
        case _:
            if packet.compiler_version and packet.node_catalog_version:
                return RepairDecision.RECOMPILE_SAME_IR
            return RepairDecision.IR_REPAIR_REQUIRED


class RepairService:
    """Opens repairs, records decisions, and promotes candidates with lineage."""

    def __init__(
        self,
        store: Store,
        *,
        registry: AutomationRegistry,
        health: WorkflowHealthService | None = None,
    ) -> None:
        self.store = store
        self.registry = registry
        self.health = health or WorkflowHealthService(store)

    async def build_packet(
        self,
        *,
        capability_id: str,
        failing_artifact_id: str,
        failure_class: FailureClass,
        failing_run_id: str | None = None,
        error_code: str | None = None,
        failing_node: str | None = None,
        external_observations: dict[str, Any] | None = None,
        repair_patterns: list[dict[str, Any]] | None = None,
    ) -> RepairPacket:
        artifact = await self.registry.get_artifact(failing_artifact_id)
        if artifact is None:
            raise RegistryError(f"unknown_artifact:{failing_artifact_id}")
        capability = await self.registry.get_capability(capability_id)

        previous = await self.store.fetchone(
            "SELECT artifact_id FROM automation_artifacts "
            "WHERE capability_id = ? AND version < ? AND lifecycle_state IN "
            "('ADMITTED','HOT','SUPERSEDED') ORDER BY version DESC LIMIT 1",
            (capability_id, artifact.version),
        )
        return RepairPacket(
            capability_id=capability_id,
            failing_artifact_id=failing_artifact_id,
            failing_run_id=failing_run_id,
            failure_class=failure_class,
            error_code=error_code,
            failing_node=failing_node,
            input_schema_digest=(
                None if capability is None else capability.workflow_ir_digest
            ),
            output_schema_digest=artifact.compiled_semantic_digest,
            node_catalog_version=artifact.node_catalog_version,
            compiler_version=artifact.compiler_version,
            policy_version=artifact.policy_version,
            previous_successful_artifact_id=(
                str(previous["artifact_id"]) if previous is not None else None
            ),
            external_observations=dict(external_observations or {}),
            repair_patterns=tuple(repair_patterns or ()),
        )

    async def open(
        self, packet: RepairPacket, *, attempt: int = 1, now_ms: int | None = None
    ) -> tuple[str, RepairDecision]:
        """Record the diagnosis. Recording it is not acting on it."""
        now = int(time.time() * 1000) if now_ms is None else now_ms
        decision = decide(packet, attempt=attempt)
        repair_id = new_id("repair")
        await self.store.execute(
            """
            INSERT INTO automation_repairs(
              repair_id, capability_id, failing_artifact_id, failing_run_id, failure_class,
              error_code, decision, candidate_artifact_id, superseded_artifact_id,
              promoted_at_ms, detail_json, created_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?)
            """,
            (
                repair_id, packet.capability_id, packet.failing_artifact_id,
                packet.failing_run_id, packet.failure_class.value, packet.error_code,
                decision.value, Store.dumps(packet.as_diagnosis_input()), now,
            ),
        )
        if decision is RepairDecision.SECURITY_REVIEW_REQUIRED:
            artifact = await self.registry.get_artifact(packet.failing_artifact_id)
            if artifact is not None:
                await self.health.quarantine(packet.capability_id, artifact.version, now_ms=now)
        return repair_id, decision

    async def promote(
        self,
        *,
        repair_id: str,
        candidate_artifact_id: str,
        now_ms: int | None = None,
    ) -> AutomationWorkflowArtifact:
        """§245 — HOT v4 -> candidate v5 -> admitted; v4 becomes SUPERSEDED.

        The candidate walks the ordinary lifecycle, so a repaired workflow is
        admitted on the same evidence as any other. The old artifact is kept
        rather than deleted: a rollback is only useful if the thing you roll
        back to still exists.
        """
        now = int(time.time() * 1000) if now_ms is None else now_ms
        row = await self.store.fetchone(
            "SELECT * FROM automation_repairs WHERE repair_id = ?", (repair_id,)
        )
        if row is None:
            raise RegistryError(f"unknown_repair:{repair_id}")
        if row["promoted_at_ms"] is not None:
            raise RegistryError(f"repair_already_promoted:{repair_id}")

        candidate = await self.registry.get_artifact(candidate_artifact_id)
        if candidate is None:
            raise RegistryError(f"unknown_artifact:{candidate_artifact_id}")
        if candidate.lifecycle_state is not WorkflowLifecycle.ADMITTED:
            # §245 — promotion happens *after* validation and admission, never
            # instead of them.
            raise RegistryError(
                f"repair_candidate_not_admitted:{candidate.lifecycle_state.value}"
            )
        failing_id = str(row["failing_artifact_id"])
        failing = await self.registry.get_artifact(failing_id)
        if failing is not None and failing.lifecycle_state in (
            WorkflowLifecycle.ADMITTED,
            WorkflowLifecycle.HOT,
        ):
            await self.registry.transition(
                failing_id,
                expected=failing.lifecycle_state,
                target=WorkflowLifecycle.SUPERSEDED,
                now_ms=now,
            )

        await self.store.execute(
            "UPDATE automation_repairs SET candidate_artifact_id = ?, "
            "superseded_artifact_id = ?, promoted_at_ms = ? WHERE repair_id = ?",
            (candidate_artifact_id, failing_id, now, repair_id),
        )
        await self.health.mark_repaired(candidate.capability_id, candidate.version, now_ms=now)
        return candidate

    async def open_repairs(self, capability_id: str | None = None) -> list[dict[str, Any]]:
        if capability_id is None:
            rows = await self.store.fetchall(
                "SELECT * FROM automation_repairs WHERE promoted_at_ms IS NULL "
                "ORDER BY created_at_ms DESC"
            )
        else:
            rows = await self.store.fetchall(
                "SELECT * FROM automation_repairs WHERE promoted_at_ms IS NULL "
                "AND capability_id = ? ORDER BY created_at_ms DESC",
                (capability_id,),
            )
        return [dict(row) for row in rows]


__all__ = ["RepairDecision", "RepairPacket", "RepairService", "decide"]
