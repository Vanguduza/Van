"""Rev 1.3 §§370-374, 404-406, 415, 421 — evidence-backed external runtime readiness.

This is the Exa pattern generalised, exactly as the Rev 1.2 review recommended
and Rev 1.3 §404 adopted: credential locus pinned to the gateway, egress default
off, and a state machine in which **configuration can never reach READY**.
`docs/EXTERNAL_GATES.md` rule 1 — "`CONFIGURED` is not `READY`" — is enforced
here in code rather than asserted in prose.

§415's regression case is the important one: configured credentials plus no
canary evidence must report `CONFIGURED`, never `READY`.
"""

from __future__ import annotations

import time
from enum import Enum

from pydantic import BaseModel, Field

from van_gateway.storage.db import Store


class RuntimeState(str, Enum):
    """§370 — the readiness ladder, plus post-READY failure states."""

    UNCONFIGURED = "UNCONFIGURED"
    CONFIGURED_EGRESS_DISABLED = "CONFIGURED_EGRESS_DISABLED"
    CONFIGURED = "CONFIGURED"
    LIVE_CANARY_RUNNING = "LIVE_CANARY_RUNNING"
    READY = "READY"
    DEGRADED = "DEGRADED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    POLICY_DISABLED = "POLICY_DISABLED"
    VERSION_MISMATCH = "VERSION_MISMATCH"


class ExternalRuntimeStatus(BaseModel):
    """§371 — the generic status contract every external runtime reports."""

    capability: str
    state: RuntimeState

    configured: bool
    egress_enabled: bool

    credential_locus: str
    runtime_version: str | None = None
    expected_version: str | None = None

    evidence_pointer: str | None = None
    verified_at_ms: int | None = None

    contains_secrets: bool = False
    detail: str | None = None
    degraded_code: str | None = None

    @property
    def ready(self) -> bool:
        return self.state is RuntimeState.READY


class ReadinessEvidence(BaseModel):
    """§409 — what a live canary must persist before READY is permitted."""

    capability: str
    evidence_pointer: str
    runtime_version: str
    verified_at_ms: int = Field(default_factory=lambda: int(time.time() * 1000))
    contains_secrets: bool = False


class ExternalRuntimeRegistry:
    """Resolves readiness for n8n, Stagehand and Browser Harness from durable evidence."""

    KEY_PREFIX = "external_runtime_evidence:"

    def __init__(self, store: Store) -> None:
        self.store = store

    async def record_evidence(self, evidence: ReadinessEvidence) -> ReadinessEvidence:
        if evidence.contains_secrets:
            # §370 — READY requires contains_secrets == false. Refuse to store
            # evidence that admits to carrying secrets rather than sanitising it.
            raise ValueError("readiness_evidence_contains_secrets")
        await self.store.execute(
            """
            INSERT INTO runtime_meta(key, value, updated_at_unix_ms) VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value,
                                          updated_at_unix_ms=excluded.updated_at_unix_ms
            """,
            (
                self.KEY_PREFIX + evidence.capability,
                evidence.model_dump_json(),
                evidence.verified_at_ms,
            ),
        )
        return evidence

    async def get_evidence(self, capability: str) -> ReadinessEvidence | None:
        row = await self.store.fetchone(
            "SELECT value FROM runtime_meta WHERE key = ?", (self.KEY_PREFIX + capability,)
        )
        if row is None:
            return None
        return ReadinessEvidence.model_validate_json(str(row["value"]))

    async def clear_evidence(self, capability: str) -> None:
        await self.store.execute(
            "DELETE FROM runtime_meta WHERE key = ?", (self.KEY_PREFIX + capability,)
        )

    async def resolve(
        self,
        *,
        capability: str,
        configured: bool,
        egress_enabled: bool,
        credential_locus: str = "gateway",
        expected_version: str | None = None,
        policy_enabled: bool = True,
        degraded_code: str | None = None,
    ) -> ExternalRuntimeStatus:
        """Compute state from configuration plus persisted canary evidence.

        The ordering matters and is deliberate: policy refusal and missing
        configuration are decided before evidence is even consulted, so a stale
        READY receipt can never resurrect a disabled runtime.
        """
        if not policy_enabled:
            return ExternalRuntimeStatus(
                capability=capability, state=RuntimeState.POLICY_DISABLED, configured=configured,
                egress_enabled=False, credential_locus=credential_locus,
                expected_version=expected_version, degraded_code=degraded_code,
                detail="disabled by policy or pending owner approval",
            )
        if not configured:
            return ExternalRuntimeStatus(
                capability=capability, state=RuntimeState.UNCONFIGURED, configured=False,
                egress_enabled=egress_enabled, credential_locus=credential_locus,
                expected_version=expected_version, degraded_code=degraded_code,
            )
        if not egress_enabled:
            return ExternalRuntimeStatus(
                capability=capability, state=RuntimeState.CONFIGURED_EGRESS_DISABLED,
                configured=True, egress_enabled=False, credential_locus=credential_locus,
                expected_version=expected_version, degraded_code=degraded_code,
            )

        evidence = await self.get_evidence(capability)
        if evidence is None:
            # §415 regression case: configured credentials + no canary == CONFIGURED.
            return ExternalRuntimeStatus(
                capability=capability, state=RuntimeState.CONFIGURED, configured=True,
                egress_enabled=True, credential_locus=credential_locus,
                expected_version=expected_version, degraded_code=degraded_code,
                detail="awaiting live canary evidence",
            )
        if expected_version and evidence.runtime_version != expected_version:
            # §274 — runtime drift. A pinned manifest disagreeing with the live
            # runtime invalidates readiness rather than being silently tolerated.
            return ExternalRuntimeStatus(
                capability=capability, state=RuntimeState.VERSION_MISMATCH, configured=True,
                egress_enabled=True, credential_locus=credential_locus,
                runtime_version=evidence.runtime_version, expected_version=expected_version,
                evidence_pointer=evidence.evidence_pointer, verified_at_ms=evidence.verified_at_ms,
                degraded_code=degraded_code,
                detail=f"observed {evidence.runtime_version}, manifest expects {expected_version}",
            )
        return ExternalRuntimeStatus(
            capability=capability, state=RuntimeState.READY, configured=True, egress_enabled=True,
            credential_locus=credential_locus, runtime_version=evidence.runtime_version,
            expected_version=expected_version, evidence_pointer=evidence.evidence_pointer,
            verified_at_ms=evidence.verified_at_ms, contains_secrets=False,
        )


__all__ = [
    "ExternalRuntimeRegistry",
    "ExternalRuntimeStatus",
    "ReadinessEvidence",
    "RuntimeState",
]
