"""Rev 1.3 §§388-403 — standing automation authority.

Rev 3.1 command authority is rooted in verified owner ingress: every
``CommandAuthorityRecord`` binds a device, a turn and an immutable context
snapshot. A timer or webhook has no owner-device gesture at event time, so
``PrincipalType.AUTOMATION`` alone cannot authorize an action — the Rev 1.2
review recorded this as blocking finding B4.

This module closes it the way Rev 1.3 §388 requires: **a derived authority path
inside the existing CommandAuthorityService, not a second authorization
system.** An owner-authorized standing intent seals a
:class:`StandingAutomationAuthority`; when its trigger fires, that authority is
validated, a *fresh* context snapshot is sealed, and an ordinary
``CommandAuthorityRecord`` is derived from it. ``authorize_action()`` then
remains the single final authority check for every action VAN takes.

Invariants enforced here:

* the originating owner device stays the revocation root (§392) — a revoked
  device kills all future derived authority;
* A4 can never become standing execution authority (§391);
* the run snapshot is always fresh, never the months-old source snapshot (§395);
* workflow version, trigger semantics and parameter surface are digest-bound,
  so a repaired or broadened workflow cannot inherit the grant (§§396-398).
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any

from pydantic import BaseModel, Field

from van_gateway.command.authority import (
    AuthoritySource,
    CommandAuthorityError,
    CommandAuthorityRecord,
    CommandAuthorityService,
)
from van_gateway.models import ActionClass, OriginChannel, PrincipalType
from van_gateway.storage.db import Store

# §391 — action-class rules for standing authority.
_STANDING_ALLOWED = {ActionClass.A1, ActionClass.A2, ActionClass.A3}
_RANK = {ActionClass.A1: 1, ActionClass.A2: 2, ActionClass.A3: 3, ActionClass.A4: 4, ActionClass.A5: 5}


class StandingAuthorityError(ValueError):
    """Raised when standing authority cannot be created or derived from."""


def canonical_digest(value: Any) -> str:
    """Deterministic digest over canonical JSON (Rev 1.3 §141)."""
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


class StandingAutomationAuthority(BaseModel):
    """Rev 1.3 §389. Sealed only after an owner-authorized creation action succeeds."""

    authority_id: str
    standing_intent_id: str

    source_command_id: str
    source_device_id: str
    source_turn_id: str | None = None
    source_snapshot_id: str
    source_context_digest: str

    principal_type: PrincipalType = PrincipalType.AUTOMATION
    requested_by: str

    capability_id: str
    artifact_id: str
    workflow_version: int

    action_class_ceiling: ActionClass

    trigger_digest: str
    parameter_constraints: dict[str, Any] = Field(default_factory=dict)
    parameter_constraints_digest: str
    allowed_effects: list[str] = Field(default_factory=list)
    allowed_domains: list[str] = Field(default_factory=list)

    issued_at_ms: int
    expires_at_ms: int | None = None
    revoked_at_ms: int | None = None

    owner_authority_evidence_ref: str
    policy_version: str

    @property
    def revoked(self) -> bool:
        return self.revoked_at_ms is not None


class DerivedRunAuthority(BaseModel):
    """Result of a per-run derivation (§393)."""

    run_id: str
    command_id: str
    authority: CommandAuthorityRecord
    standing_authority_id: str
    source_snapshot_id: str
    run_snapshot_id: str


class StandingAutomationAuthorityService:
    """Seals standing authorities and derives per-run command authority from them."""

    def __init__(self, store: Store, authority: CommandAuthorityService) -> None:
        self.store = store
        self.authority = authority

    # ------------------------------------------------------------------ create

    @staticmethod
    def trigger_digest(trigger: dict[str, Any]) -> str:
        """§397 — canonical trigger semantics, so a workflow cannot broaden its trigger."""
        return canonical_digest({"van-standing-trigger-v1": trigger})

    @staticmethod
    def parameter_constraints_digest(constraints: dict[str, Any]) -> str:
        """§398 — canonical parameter constraint surface."""
        return canonical_digest({"van-standing-parameters-v1": constraints})

    async def seal(
        self,
        *,
        standing_intent_id: str,
        source_command_id: str,
        capability_id: str,
        artifact_id: str,
        workflow_version: int,
        action_class_ceiling: ActionClass,
        trigger: dict[str, Any],
        parameter_constraints: dict[str, Any],
        allowed_effects: list[str],
        allowed_domains: list[str],
        owner_authority_evidence_ref: str,
        policy_version: str,
        expires_at_ms: int | None = None,
        requested_by: str | None = None,
        now_ms: int | None = None,
    ) -> StandingAutomationAuthority:
        """Seal standing authority from a live owner command authority record.

        The source command must already be an owner-authorized record whose
        effective class covers the requested ceiling. §391 forbids A4/A5.
        """
        now = int(time.time() * 1000) if now_ms is None else now_ms

        if action_class_ceiling not in _STANDING_ALLOWED:
            # §391: an A4 standing intent may monitor, prepare and propose, but the
            # A4 mutation itself always needs a fresh biometric approval (§424).
            raise StandingAuthorityError("standing_authority_action_class_prohibited")

        source = await self.authority.get(source_command_id)
        if source is None:
            raise StandingAuthorityError("source_command_authority_missing")
        if source.authority_source is not AuthoritySource.OWNER_COMMAND:
            # §390: standing authority is created only from a real owner command,
            # never from another derived automation record (no authority laundering).
            raise StandingAuthorityError("standing_authority_requires_owner_command")
        if _RANK[action_class_ceiling] > _RANK[source.effective_action_class]:
            raise StandingAuthorityError("standing_authority_exceeds_source_command")

        device = await self.store.fetchone(
            "SELECT revoked_at_unix FROM devices WHERE device_id = ?", (source.device_id,)
        )
        if device is None or device["revoked_at_unix"] is not None:
            raise StandingAuthorityError("source_device_revoked")

        record = StandingAutomationAuthority(
            authority_id=f"sauth_{uuid.uuid4().hex}",
            standing_intent_id=standing_intent_id,
            source_command_id=source_command_id,
            source_device_id=source.device_id,
            source_turn_id=source.turn_id,
            source_snapshot_id=source.snapshot_id,
            source_context_digest=source.context_digest,
            requested_by=requested_by or f"automation:{standing_intent_id}",
            capability_id=capability_id,
            artifact_id=artifact_id,
            workflow_version=workflow_version,
            action_class_ceiling=action_class_ceiling,
            trigger_digest=self.trigger_digest(trigger),
            parameter_constraints=parameter_constraints,
            parameter_constraints_digest=self.parameter_constraints_digest(parameter_constraints),
            allowed_effects=sorted(allowed_effects),
            allowed_domains=sorted(allowed_domains),
            issued_at_ms=now,
            expires_at_ms=expires_at_ms,
            owner_authority_evidence_ref=owner_authority_evidence_ref,
            policy_version=policy_version,
        )
        await self.store.execute(
            """
            INSERT INTO standing_automation_authorities(
              authority_id, standing_intent_id, source_command_id, source_device_id,
              source_turn_id, source_snapshot_id, source_context_digest, principal_type,
              requested_by, capability_id, artifact_id, workflow_version, action_class_ceiling,
              trigger_digest, parameter_constraints_json, parameter_constraints_digest,
              allowed_effects_json, allowed_domains_json, issued_at_ms, expires_at_ms,
              revoked_at_ms, owner_authority_evidence_ref, policy_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.authority_id, record.standing_intent_id, record.source_command_id,
                record.source_device_id, record.source_turn_id, record.source_snapshot_id,
                record.source_context_digest, record.principal_type.value, record.requested_by,
                record.capability_id, record.artifact_id, record.workflow_version,
                record.action_class_ceiling.value, record.trigger_digest,
                Store.dumps(record.parameter_constraints), record.parameter_constraints_digest,
                Store.dumps(record.allowed_effects), Store.dumps(record.allowed_domains),
                record.issued_at_ms, record.expires_at_ms, record.revoked_at_ms,
                record.owner_authority_evidence_ref, record.policy_version,
            ),
        )
        return record

    # -------------------------------------------------------------------- read

    async def get(self, authority_id: str) -> StandingAutomationAuthority | None:
        row = await self.store.fetchone(
            "SELECT * FROM standing_automation_authorities WHERE authority_id = ?", (authority_id,)
        )
        return self._row_to_authority(row) if row is not None else None

    async def revoke(self, authority_id: str, *, now_ms: int | None = None) -> bool:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        async with self.store.connection() as db:
            cur = await db.execute(
                "UPDATE standing_automation_authorities SET revoked_at_ms = ? "
                "WHERE authority_id = ? AND revoked_at_ms IS NULL",
                (now, authority_id),
            )
            await db.commit()
            return bool(cur.rowcount == 1)

    async def revoke_for_device(self, device_id: str, *, now_ms: int | None = None) -> int:
        """§392 — device revocation invalidates future derived automation authority."""
        now = int(time.time() * 1000) if now_ms is None else now_ms
        async with self.store.connection() as db:
            cur = await db.execute(
                "UPDATE standing_automation_authorities SET revoked_at_ms = ? "
                "WHERE source_device_id = ? AND revoked_at_ms IS NULL",
                (now, device_id),
            )
            await db.commit()
            return int(cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0)

    # ------------------------------------------------------------------ derive

    async def validate_for_run(
        self,
        authority: StandingAutomationAuthority,
        *,
        trigger: dict[str, Any],
        artifact_id: str,
        workflow_version: int,
        parameters: dict[str, Any],
        now_ms: int,
    ) -> None:
        """Run every §§392-398 precondition. Raises on the first failure."""
        if authority.revoked:
            raise StandingAuthorityError("STANDING_AUTHORITY_REVOKED")
        if authority.expires_at_ms is not None and now_ms >= authority.expires_at_ms:
            raise StandingAuthorityError("STANDING_AUTHORITY_EXPIRED")

        intent = await self.store.fetchone(
            "SELECT enabled, expires_at_ms FROM automation_standing_intents WHERE intent_id = ?",
            (authority.standing_intent_id,),
        )
        if intent is None or not bool(intent["enabled"]):
            raise StandingAuthorityError("STANDING_INTENT_DISABLED")
        if intent["expires_at_ms"] is not None and now_ms >= int(intent["expires_at_ms"]):
            raise StandingAuthorityError("STANDING_INTENT_EXPIRED")

        # §392 — source device remains the revocation root.
        device = await self.store.fetchone(
            "SELECT revoked_at_unix FROM devices WHERE device_id = ?", (authority.source_device_id,)
        )
        if device is None or device["revoked_at_unix"] is not None:
            raise StandingAuthorityError("SOURCE_DEVICE_REVOKED")

        # §396 — exact workflow artifact/version binding.
        if artifact_id != authority.artifact_id or workflow_version != authority.workflow_version:
            raise StandingAuthorityError("WORKFLOW_VERSION_MISMATCH")

        # §397 — trigger cannot broaden.
        if self.trigger_digest(trigger) != authority.trigger_digest:
            raise StandingAuthorityError("STANDING_AUTHORITY_TRIGGER_MISMATCH")

        # §398 — runtime parameters must satisfy the sealed constraint surface.
        violation = self.check_parameter_constraints(authority.parameter_constraints, parameters)
        if violation is not None:
            raise StandingAuthorityError("STANDING_AUTHORITY_PARAMETER_MISMATCH")

    @staticmethod
    def check_parameter_constraints(
        constraints: dict[str, Any], parameters: dict[str, Any]
    ) -> str | None:
        """Return the offending key, or None when every constraint is satisfied.

        Constraints are deliberately a small closed language (§398): ``enum`` for a
        permitted value set, ``const`` for an exact value, ``max_items`` for list
        width. Anything not expressible here needs fresh owner authority rather
        than a richer matcher.
        """
        for key, rule in constraints.items():
            if key not in parameters:
                return key
            value = parameters[key]
            if "enum" in rule and value not in rule["enum"]:
                return key
            if "const" in rule and value != rule["const"]:
                return key
            if "max_items" in rule:
                if not isinstance(value, list) or len(value) > int(rule["max_items"]):
                    return key
        return None

    async def derive_run_authority(
        self,
        authority: StandingAutomationAuthority,
        *,
        run_id: str,
        trigger: dict[str, Any],
        artifact_id: str,
        workflow_version: int,
        parameters: dict[str, Any],
        run_snapshot_id: str,
        run_context_digest: str,
        operation_action_class: ActionClass,
        typed_action_id: str | None = None,
        run_ttl_seconds: int = 900,
        now_ms: int | None = None,
    ) -> DerivedRunAuthority:
        """§393 — derive and seal an ordinary CommandAuthorityRecord for one run.

        ``run_snapshot_id`` must be a snapshot sealed for *this run* (§395). The
        source snapshot is evidence of what the owner authorized; it is retained
        on the standing authority and never reused as the execution snapshot.
        """
        now = int(time.time() * 1000) if now_ms is None else now_ms
        await self.validate_for_run(
            authority,
            trigger=trigger,
            artifact_id=artifact_id,
            workflow_version=workflow_version,
            parameters=parameters,
            now_ms=now,
        )

        if operation_action_class not in _STANDING_ALLOWED:
            # A4/A5 never execute under derived authority (§391, §424).
            raise StandingAuthorityError("STANDING_AUTHORITY_ACTION_CLASS_PROHIBITED")
        if _RANK[operation_action_class] > _RANK[authority.action_class_ceiling]:
            raise StandingAuthorityError("STANDING_AUTHORITY_CEILING_EXCEEDED")

        if not run_snapshot_id or run_snapshot_id == authority.source_snapshot_id:
            # §395 — a standing automation must not reuse the source snapshot.
            raise StandingAuthorityError("STANDING_AUTHORITY_STALE_SNAPSHOT")

        now_unix = now // 1000
        record = CommandAuthorityRecord(
            command_id=f"automation:{run_id}",
            device_id=authority.source_device_id,
            principal_type=PrincipalType.AUTOMATION,
            requested_by=authority.requested_by,
            origin_channel=OriginChannel.AUTOMATION,
            signed_action_class=authority.action_class_ceiling,
            effective_action_class=operation_action_class,
            typed_action_id=typed_action_id,
            snapshot_id=run_snapshot_id,
            context_digest=run_context_digest,
            issued_at_unix=now_unix,
            expires_at_unix=now_unix + max(60, int(run_ttl_seconds)),
            no_stale_replay=False,
            # §393: never true for a derived record. A4 is excluded above, and no
            # standing grant may stand in for a fresh owner approval.
            owner_approved=False,
            turn_id=None,
            sealed_at_unix_ms=now,
            authority_source=AuthoritySource.STANDING_AUTOMATION,
            source_authority_id=authority.authority_id,
            source_command_id=authority.source_command_id,
        )
        await self.authority.seal(record)
        return DerivedRunAuthority(
            run_id=run_id,
            command_id=record.command_id,
            authority=record,
            standing_authority_id=authority.authority_id,
            source_snapshot_id=authority.source_snapshot_id,
            run_snapshot_id=run_snapshot_id,
        )

    # ----------------------------------------------------------------- helpers

    @staticmethod
    def _row_to_authority(row: Any) -> StandingAutomationAuthority:
        return StandingAutomationAuthority(
            authority_id=str(row["authority_id"]),
            standing_intent_id=str(row["standing_intent_id"]),
            source_command_id=str(row["source_command_id"]),
            source_device_id=str(row["source_device_id"]),
            source_turn_id=str(row["source_turn_id"]) if row["source_turn_id"] is not None else None,
            source_snapshot_id=str(row["source_snapshot_id"]),
            source_context_digest=str(row["source_context_digest"]),
            principal_type=PrincipalType(str(row["principal_type"])),
            requested_by=str(row["requested_by"]),
            capability_id=str(row["capability_id"]),
            artifact_id=str(row["artifact_id"]),
            workflow_version=int(row["workflow_version"]),
            action_class_ceiling=ActionClass(str(row["action_class_ceiling"])),
            trigger_digest=str(row["trigger_digest"]),
            parameter_constraints=json.loads(row["parameter_constraints_json"] or "{}"),
            parameter_constraints_digest=str(row["parameter_constraints_digest"]),
            allowed_effects=json.loads(row["allowed_effects_json"] or "[]"),
            allowed_domains=json.loads(row["allowed_domains_json"] or "[]"),
            issued_at_ms=int(row["issued_at_ms"]),
            expires_at_ms=int(row["expires_at_ms"]) if row["expires_at_ms"] is not None else None,
            revoked_at_ms=int(row["revoked_at_ms"]) if row["revoked_at_ms"] is not None else None,
            owner_authority_evidence_ref=str(row["owner_authority_evidence_ref"]),
            policy_version=str(row["policy_version"]),
        )


__all__ = [
    "DerivedRunAuthority",
    "StandingAuthorityError",
    "StandingAutomationAuthority",
    "StandingAutomationAuthorityService",
    "canonical_digest",
]
