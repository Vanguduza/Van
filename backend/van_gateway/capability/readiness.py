"""Rev 1 §7 — readiness adapters.

Each adapter is a thin bridge to a subsystem that was already authoritative for
its own health before the canonical registry existed. They exist so the registry
can *ask* rather than *store*, which is the difference between subsuming the
automation and Google registries and duplicating them.

Every adapter is read-only by construction. A probe returns whether something is
ready and why not; it has no way to change a declaration, so a healthy subsystem
can never widen what a capability is permitted to do.
"""

from __future__ import annotations

from typing import Any

from van_gateway.capability.models import CapabilityDeclaration
from van_gateway.storage.db import Store


class AutomationReadiness:
    """Ready iff the automation fabric holds an ADMITTED artifact.

    §36 of Rev 1.3: nothing executes before admission. Asking the automation
    registry rather than mirroring its lifecycle means a workflow withdrawn there
    stops being routable here with no synchronisation step in between.
    """

    def __init__(self, store: Store, *, enabled: bool = False) -> None:
        self.store = store
        self.enabled = enabled

    async def is_ready(self, declaration: CapabilityDeclaration) -> tuple[bool, str | None]:
        if not self.enabled:
            return False, "AUTOMATION_FABRIC_DISABLED"
        row = await self.store.fetchone(
            "SELECT COUNT(*) AS n FROM automation_artifacts "
            "WHERE lifecycle_state IN ('ADMITTED','HOT')"
        )
        if row is None or int(row["n"]) == 0:
            return False, "NO_ADMITTED_AUTOMATION_ARTIFACT"
        return True, None


class GoogleMeshReadiness:
    """Ready iff the Google mesh reports READY for this capability.

    The mesh already distinguishes UNVERIFIED / CONFIGURED / READY per principal,
    and Rev 1.3's evidence rule — CONFIGURED is not READY — is exactly the
    distinction this registry needs. Re-deriving it here would have re-created
    that bug.
    """

    def __init__(self, broker: Any | None) -> None:
        self.broker = broker

    async def is_ready(self, declaration: CapabilityDeclaration) -> tuple[bool, str | None]:
        if self.broker is None:
            return False, "GOOGLE_MESH_UNCONFIGURED"
        probe = declaration.health_probe or declaration.capability_id.split(".")[-1]
        try:
            status = await self.broker.capability_status(probe)
        except Exception as exc:  # noqa: BLE001 - an unknown capability is not-ready
            return False, f"GOOGLE_STATUS_UNAVAILABLE:{type(exc).__name__}"
        state = getattr(status, "state", None)
        state_value = getattr(state, "value", str(state))
        if state_value != "READY":
            return False, f"GOOGLE_CAPABILITY_{state_value}"
        return True, None


class ExternalRuntimeReadiness:
    """Ready iff the private worker has recorded readiness evidence.

    Rev 1.3 §§368/420's ladder — UNCONFIGURED, CONFIGURED_EGRESS_DISABLED,
    CONFIGURED, LIVE_CANARY_RUNNING, READY — already lives in
    ExternalRuntimeRegistry, so this asks it through its own accessor rather than
    reading `runtime_meta` behind its back. "CONFIGURED is not READY" is that
    registry's rule to enforce, and re-deriving it here would eventually
    re-create the bug it exists to prevent.
    """

    def __init__(self, registry: Any, *, enabled: bool = False) -> None:
        self.registry = registry
        self.enabled = enabled

    async def is_ready(self, declaration: CapabilityDeclaration) -> tuple[bool, str | None]:
        if not self.enabled:
            return False, "BROWSER_FABRIC_DISABLED"
        capability = declaration.health_probe
        if capability is None:
            return False, "NO_HEALTH_PROBE_DECLARED"
        evidence = await self.registry.get_evidence(capability)
        if evidence is None:
            # §368 — an unproven runtime is not READY, and absence of evidence is
            # the honest default rather than a reason to assume the best.
            return False, f"NO_READINESS_EVIDENCE:{capability}"
        return True, None


__all__ = [
    "AutomationReadiness",
    "ExternalRuntimeReadiness",
    "GoogleMeshReadiness",
]
