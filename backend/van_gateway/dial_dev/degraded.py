"""Map DIAL's `degraded[]` rows onto VAN's degraded model (VAN-DEV-010).

The envelope itself still reaches the device unchanged — the device renders
`ScreenState.Degraded` from it. This mapping is what makes the same condition visible on
VAN's own `/health` and `/v1/degraded`, so a DIAL-side fault is reported as a DIAL-side
fault instead of being invisible to the gateway.

A subsystem DIAL names that VAN does not know is left out of the registry rather than
guessed into a code: the device still sees the row, verbatim, in the envelope.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from van_gateway.degraded.registry import DegradedRegistry
from van_gateway.models import DegradedCode

#: DIAL subsystem name (normalised: upper case, alphanumerics only) → VAN code.
SUBSYSTEM_CODES: dict[str, DegradedCode] = {
    "ORCA": DegradedCode.DIAL_ORCA_DEGRADED,
    "SPMRF": DegradedCode.DIAL_SPMRF_DEGRADED,
    "OPENVIKING": DegradedCode.DIAL_OPENVIKING_DEGRADED,
    "VEKL": DegradedCode.DIAL_VEKL_DEGRADED,
    "ARTEMIS": DegradedCode.DIAL_ARTEMIS_DEGRADED,
    "ZUUL": DegradedCode.DIAL_ZUUL_DEGRADED,
    "HERMES": DegradedCode.DIAL_HERMES_DEGRADED,
    "HERMESDIAL": DegradedCode.DIAL_HERMES_DEGRADED,
    "DIALHERMES": DegradedCode.DIAL_HERMES_DEGRADED,
}

#: The codes a projection envelope is authoritative for. The two link codes
#: (DIAL_DEV_UNAVAILABLE, DIAL_DEV_EVENT_STREAM_DOWN) are VAN's own observation and are
#: never cleared by an envelope.
PROJECTED_CODES: frozenset[DegradedCode] = frozenset(SUBSYSTEM_CODES.values())


def _normalise(name: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(name or "").upper())


def codes_for(rows: Iterable[Any]) -> set[DegradedCode]:
    codes: set[DegradedCode] = set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        code = SUBSYSTEM_CODES.get(_normalise(row.get("subsystem")))
        if code is not None:
            codes.add(code)
    return codes


def apply_envelope(registry: DegradedRegistry | None, envelope: dict[str, Any]) -> None:
    """Latest projection wins for the DIAL subsystem codes."""
    if registry is None:
        return
    rows = envelope.get("degraded")
    if not isinstance(rows, list):
        return
    active = codes_for(rows)
    for code in PROJECTED_CODES:
        registry.set(code, code in active)
    registry.set(DegradedCode.DIAL_DEV_UNAVAILABLE, False)


def mark_unavailable(registry: DegradedRegistry | None, unavailable: bool) -> None:
    if registry is not None:
        registry.set(DegradedCode.DIAL_DEV_UNAVAILABLE, unavailable)
