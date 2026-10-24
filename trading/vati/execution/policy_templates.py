"""Sealed execution templates (§22, TRD-ENH-050).

`FxCostModel` already models a passive entry as saving half a spread, and the
router already takes `entry_type`. So the choice exists — it is simply never
learned, and "passive saves half a spread" is an approximation that ignores the
real trade-off: fill probability against adverse selection against the
opportunity cost of not filling at all.

The engine chooses among *these* templates and nothing else. A learned component
selects a template id; it never emits an order shape. Every template carries its
own hard bounds, so a bad selection is still a bounded one.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Optional

PASSIVE = "PASSIVE"
PASSIVE_THEN_CROSS = "PASSIVE_THEN_CROSS"
LIMIT_AT_TOUCH = "LIMIT_AT_TOUCH"
LIMIT_WITH_BOUNDED_CHASE = "LIMIT_WITH_BOUNDED_CHASE"
MARKET_WITH_SLIPPAGE_CAP = "MARKET_WITH_SLIPPAGE_CAP"
STOP_ENTRY = "STOP_ENTRY"
DO_NOT_EXECUTE = "DO_NOT_EXECUTE"

TEMPLATE_IDS = (PASSIVE, PASSIVE_THEN_CROSS, LIMIT_AT_TOUCH,
                LIMIT_WITH_BOUNDED_CHASE, MARKET_WITH_SLIPPAGE_CAP, STOP_ENTRY, DO_NOT_EXECUTE)

#: P1-TRADE-EXEC-004 — which order types may carry out a strategy's requested entry.
#: The decision cycle sent every order as LIMIT, so a breakout's STOP entry ("buy only if
#: price breaks above the range") became a limit above the market: refused as off-market,
#: or filled before the breakout. A requested entry type is now binding up to this table.
#: LIMIT keeps its existing latitude (passive, at touch, or capped market), so ordinary
#: entries behave exactly as before; STOP and PASSIVE_LIMIT are never substituted.
ENTRY_COMPATIBILITY: dict[str, frozenset[str]] = {
    "LIMIT": frozenset({"LIMIT", "PASSIVE_LIMIT", "MARKET"}),
    "MARKET": frozenset({"MARKET", "LIMIT"}),
    "PASSIVE_LIMIT": frozenset({"PASSIVE_LIMIT"}),
    "STOP": frozenset({"STOP"}),
}


def entry_compatible(requested: str, chosen: str) -> bool:
    return chosen in ENTRY_COMPATIBILITY.get(requested, frozenset({requested}))


class ExecutionTemplateError(ValueError):
    """A template shape the router must never be handed."""


@dataclass(frozen=True)
class ExecutionTemplate:
    template_id: str
    version: str
    allowed_entry_types: tuple[str, ...]
    max_chase_ticks: int
    max_wait_ms: int
    max_replace_count: int
    #: Fraction of the order price (0.0001 = 1 basis point), not price units.
    #: P1-TRADE-EXEC-002: this was an absolute price bound, so 0.0001 meant 1 pip on
    #: EURUSD but 0.01 pip on USDJPY and one cent on gold, and every JPY order with any
    #: slippage was refused. The router converts it to price units at the order's own
    #: entry price (`slippage_bound_in_price`). Version 1.1.0 marks the change of unit.
    max_slippage: Decimal
    cancel_on_event_state: tuple[str, ...] = ()
    fallback_template_id: Optional[str] = None

    def __post_init__(self) -> None:
        if self.template_id not in TEMPLATE_IDS:
            raise ExecutionTemplateError(f"unknown template {self.template_id}")
        if self.max_chase_ticks < 0 or self.max_slippage < 0:
            raise ExecutionTemplateError(f"{self.template_id}: negative bound")
        if self.fallback_template_id == self.template_id:
            raise ExecutionTemplateError(f"{self.template_id}: fallback loops to itself")

    def as_dict(self) -> dict:
        return {
            "template_id": self.template_id, "version": self.version,
            "allowed_entry_types": list(self.allowed_entry_types),
            "max_chase_ticks": self.max_chase_ticks, "max_wait_ms": self.max_wait_ms,
            "max_replace_count": self.max_replace_count, "max_slippage": str(self.max_slippage),
            "cancel_on_event_state": list(self.cancel_on_event_state),
            "fallback_template_id": self.fallback_template_id,
        }


def slippage_bound_in_price(fraction: Decimal, reference_price: Decimal) -> Decimal:
    """Convert a template slippage fraction to price units at `reference_price`."""
    if fraction < 0 or reference_price <= 0:
        raise ExecutionTemplateError("slippage bound needs a non-negative fraction and a positive price")
    return fraction * reference_price


#: The certified set. Bounds are deliberately tight; a template that needs
#: wider ones is a new template with its own admission, not a loosened old one.
DEFAULT_TEMPLATES: dict[str, ExecutionTemplate] = {
    PASSIVE: ExecutionTemplate(
        PASSIVE, "1.1.0", ("PASSIVE_LIMIT",), 0, 30_000, 0, Decimal("0"),
        ("PRE_BLACKOUT", "POST_BLACKOUT"), LIMIT_AT_TOUCH),
    PASSIVE_THEN_CROSS: ExecutionTemplate(
        PASSIVE_THEN_CROSS, "1.1.0", ("PASSIVE_LIMIT", "LIMIT"), 1, 15_000, 1, Decimal("0.0002"),
        ("PRE_BLACKOUT", "POST_BLACKOUT"), LIMIT_AT_TOUCH),
    LIMIT_AT_TOUCH: ExecutionTemplate(
        LIMIT_AT_TOUCH, "1.1.0", ("LIMIT",), 0, 10_000, 0, Decimal("0.0001"),
        ("PRE_BLACKOUT",), MARKET_WITH_SLIPPAGE_CAP),
    LIMIT_WITH_BOUNDED_CHASE: ExecutionTemplate(
        LIMIT_WITH_BOUNDED_CHASE, "1.1.0", ("LIMIT",), 3, 8_000, 3, Decimal("0.0005"),
        ("PRE_BLACKOUT",), MARKET_WITH_SLIPPAGE_CAP),
    MARKET_WITH_SLIPPAGE_CAP: ExecutionTemplate(
        MARKET_WITH_SLIPPAGE_CAP, "1.1.0", ("MARKET",), 0, 2_000, 0, Decimal("0.0010"),
        ("PRE_BLACKOUT", "POST_BLACKOUT"), DO_NOT_EXECUTE),
    # A resting stop entry: triggers only when price trades through the level, then
    # fills within 3 bp of it. Waits up to 4 h; cancelled in either blackout.
    STOP_ENTRY: ExecutionTemplate(
        STOP_ENTRY, "1.1.0", ("STOP",), 0, 4 * 3_600_000, 0, Decimal("0.0003"),
        ("PRE_BLACKOUT", "POST_BLACKOUT"), DO_NOT_EXECUTE),
    DO_NOT_EXECUTE: ExecutionTemplate(
        DO_NOT_EXECUTE, "1.1.0", (), 0, 0, 0, Decimal("0"), (), None),
}

#: What VATI does today: a plain LIMIT. Used whenever evidence is insufficient,
#: so an unlearned path behaves exactly as the certified default already does.
CERTIFIED_DEFAULT = LIMIT_AT_TOUCH


def template(template_id: str, registry: Mapping[str, ExecutionTemplate] | None = None) -> ExecutionTemplate:
    reg = registry or DEFAULT_TEMPLATES
    t = reg.get(template_id)
    if t is None:
        raise ExecutionTemplateError(f"unknown template {template_id}")
    return t


__all__ = [
    "CERTIFIED_DEFAULT", "DEFAULT_TEMPLATES", "DO_NOT_EXECUTE", "LIMIT_AT_TOUCH",
    "LIMIT_WITH_BOUNDED_CHASE", "MARKET_WITH_SLIPPAGE_CAP", "PASSIVE",
    "PASSIVE_THEN_CROSS", "TEMPLATE_IDS",
    "ExecutionTemplate", "ExecutionTemplateError", "template",
]
