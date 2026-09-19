"""P2-GOOG-003 — the Google credential planes, reported one by one.

Four credentials reach Google and they expire independently:

  * `workspace_oauth`   the owner's refresh token, revoked when they change a password or
                        withdraw consent;
  * `gemini_runtime`    the model runtime, which has its own entitlement and capacity;
  * `cloud_service`     project credentials for the discoveryengine APIs, which rotate on
                        a schedule nobody at VAN controls;
  * `consumer_session`  a browser profile the owner signed in with, which dies on a
                        sign-out or a session timeout.

`GoogleCredentialPlane` already named all four and each had a reporter. What did not exist
was anything that composed them, so the health surface answered "is Google connected" with
one boolean derived from the refresh token alone. An expired cloud credential and a
signed-out browser profile were both invisible there, and a revoked refresh token made the
whole of Google look down when the enterprise notebook path was fine.

The consequence is the one §421 names for every fabric: degradation must be scoped. A
reader who cannot see which plane failed cannot know what still works, and the two wrong
answers are symmetrical — reporting everything broken when one credential lapsed, or
reporting everything fine because the one credential that is checked happens to be good.

This module composes, and composes only. Each plane's state comes from the authority that
already owned it; nothing here decides whether a credential is valid.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from van_gateway.google.mesh import GoogleCredentialPlane

REGISTRY = Path(__file__).resolve().parents[3] / "registries" / "google_capabilities.json"


class PlaneState:
    """The states a plane can be in, deliberately few.

    Not an Enum reusing `GoogleCapabilityState`: that enum describes a *capability*, and a
    capability can be RATE_LIMITED or CAPACITY_LIMITED in ways a credential cannot. Three
    states is what a credential actually has, and inventing more would invite a reader to
    look for a distinction that is not there.
    """

    READY = "READY"
    #: The credential is absent or was never set up. Distinguished from EXPIRED because
    #: they need different actions from the owner, and reporting one as the other sends
    #: them to the wrong place.
    UNCONFIGURED = "UNCONFIGURED"
    #: Configured and no longer accepted: revoked, signed out, or rotated away.
    AUTH_REQUIRED = "AUTH_REQUIRED"


@dataclass(frozen=True)
class PlaneHealth:
    plane: GoogleCredentialPlane
    state: str
    #: What holds this credential, so the owner knows where to go to fix it.
    credential_locus: str
    #: The capabilities that stop working when this plane fails, from the registry rather
    #: than from a list kept here — a second list would drift.
    serves: tuple[str, ...]
    detail: str | None = None

    @property
    def usable(self) -> bool:
        return self.state == PlaneState.READY

    def as_dict(self) -> dict[str, Any]:
        return {
            "plane": self.plane.value,
            "state": self.state,
            "usable": self.usable,
            "credential_locus": self.credential_locus,
            "serves": list(self.serves),
            "detail": self.detail,
        }


def capabilities_by_plane() -> dict[str, tuple[str, ...]]:
    """Which declared Google capabilities each plane serves, read from the registry."""
    rows = json.loads(REGISTRY.read_text(encoding="utf-8"))["capabilities"]
    grouped: dict[str, list[str]] = {plane.value: [] for plane in GoogleCredentialPlane}
    for row in rows:
        plane = str(row.get("credential_plane") or "")
        if plane in grouped:
            grouped[plane].append(str(row["id"]))
    return {plane: tuple(sorted(ids)) for plane, ids in grouped.items()}


async def plane_health(
    *,
    google: Any,
    notebook_enterprise: Any | None = None,
    notebook_consumer: Any | None = None,
    broker: Any | None = None,
) -> list[PlaneHealth]:
    """One row per plane, each answered by the authority that already owned it."""
    serves = capabilities_by_plane()
    out: list[PlaneHealth] = []

    # --- workspace_oauth: the owner's refresh token ------------------------------
    workspace = await google.status()
    out.append(PlaneHealth(
        plane=GoogleCredentialPlane.WORKSPACE_OAUTH,
        state=PlaneState.READY if workspace.connected else (
            PlaneState.UNCONFIGURED if not google.ready() else PlaneState.AUTH_REQUIRED
        ),
        credential_locus="gateway-held encrypted refresh token",
        serves=serves[GoogleCredentialPlane.WORKSPACE_OAUTH.value],
        detail=(
            None if workspace.connected
            else "the owner has not connected Google, or the refresh token was revoked"
        ),
    ))

    # --- cloud_service: project credentials for discoveryengine -------------------
    if notebook_enterprise is not None:
        status = await notebook_enterprise.status()
        out.append(PlaneHealth(
            plane=GoogleCredentialPlane.CLOUD_SERVICE,
            state=_from_provider_state(status.state),
            credential_locus=status.credential_locus,
            serves=serves[GoogleCredentialPlane.CLOUD_SERVICE.value],
            detail=None if status.state.value == "READY" else status.state.value,
        ))

    # --- consumer_session: a browser profile the owner signed in with -------------
    if notebook_consumer is not None:
        status = await notebook_consumer.status()
        out.append(PlaneHealth(
            plane=GoogleCredentialPlane.CONSUMER_SESSION,
            state=_from_provider_state(status.state),
            credential_locus=status.credential_locus,
            serves=serves[GoogleCredentialPlane.CONSUMER_SESSION.value],
            detail=None if status.state.value == "READY" else status.state.value,
        ))

    # --- gemini_runtime: the model runtime's own entitlement ----------------------
    if broker is not None:
        principal = await broker.principal_status()
        out.append(PlaneHealth(
            plane=GoogleCredentialPlane.GEMINI_RUNTIME,
            state=(
                PlaneState.READY if principal.registered and principal.status == "active"
                else PlaneState.UNCONFIGURED if not principal.registered
                else PlaneState.AUTH_REQUIRED
            ),
            credential_locus="google principal registration",
            serves=serves[GoogleCredentialPlane.GEMINI_RUNTIME.value],
            detail=(
                None if principal.registered and principal.status == "active"
                else "no Google principal is registered, so the runtime's entitlement is "
                     "unverified"
            ),
        ))

    return out


def _from_provider_state(state: Any) -> str:
    """Translate a knowledge-provider state into the three a credential has.

    CONFIGURED means the credential is present and has not been exercised, which is not the
    same as working. Reporting it as READY would be the optimistic answer the whole
    verification discipline exists to refuse.
    """
    value = state.value if hasattr(state, "value") else str(state)
    if value == "READY":
        return PlaneState.READY
    if value in ("DISABLED", "UNCONFIGURED"):
        return PlaneState.UNCONFIGURED
    return PlaneState.AUTH_REQUIRED


def summarise(planes: list[PlaneHealth]) -> dict[str, Any]:
    """What still works, said plainly.

    The two wrong answers are symmetrical: everything broken because one credential
    lapsed, or everything fine because the one credential that is checked happens to be
    good. Naming the working and failing capabilities separately makes both impossible to
    state by accident.
    """
    working: list[str] = []
    blocked: list[str] = []
    for plane in planes:
        (working if plane.usable else blocked).extend(plane.serves)
    return {
        "planes": [plane.as_dict() for plane in planes],
        # Named for exactly what they are. `capabilities_available` would be read as "VAN
        # can do these", and a working credential is not a working capability: the runtime
        # can still be unreachable, rate limited or not certified. This says only that the
        # credential is not the thing stopping it, which is the question this surface
        # answers and the only one it can.
        "capabilities_whose_credential_plane_is_ready": sorted(working),
        "capabilities_blocked_by_their_credential_plane": sorted(blocked),
        "credential_readiness_is_not_capability_readiness": (
            "a plane being READY means its credential works; whether the capability works "
            "is answered by /v1/capabilities/status"
        ),
        "all_planes_ready": all(plane.usable for plane in planes),
        # Stated rather than implied: one plane failing never takes another down, which is
        # the property the single-boolean surface made impossible to see.
        "planes_fail_independently": True,
    }


__all__ = [
    "PlaneHealth",
    "PlaneState",
    "capabilities_by_plane",
    "plane_health",
    "summarise",
]
