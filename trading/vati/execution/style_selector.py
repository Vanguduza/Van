"""Execution style selector (TRD-REV51-116, G6).

The ExecutionPolicyEngine already answers "which template", from measured
expected shortfall, and this module does not second-guess it. What it adds is
the dimension the template engine has no view of: *how to work the order
inside the template it chose* — how many slices, how large each one, how long
to wait, and whether the position's own condition makes waiting a bad idea.

Everything here is bounded by the template rather than beside it. The selector
may narrow `max_slippage`, may pick among `allowed_entry_types`, may wait less
than `max_wait_ms` — and can do none of the opposites. `_bounded` is the one
function that matters: every parameter passes through it, and it is written so
that the worst a bug can do is produce a more conservative order than the
template already permits (INV-EXEC-001).

Slicing exists because size relative to displayed liquidity is a real cost and
the template engine cannot see it. The participation cap is the same idea the
ILLIQUID_EQUITY loss model already applies to sizing, applied to working the
order. Where the venue's lot step cannot express a slice, the slice count
comes down until it can — never the other way, and if a single slice is still
not expressible the selector refuses rather than rounding something up.

Urgency comes from deterministic state only — the trade health engine, the
event window, the protection path — never from a model. A style chosen partly
from a model output would put cognition on the exit path, and INV-FAIL-001
means the exit path has to work when every model is down.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from enum import Enum
from typing import Any, Optional

from vati.core.canonical import canonical_hash
from vati.core.events import EventKind, make_event
from vati.execution.policy_templates import (
    DO_NOT_EXECUTE,
    ExecutionTemplate,
    template as resolve_template,
)
from vati.execution.route_registry import QuantisationRefused, Route, quantise_volume

PRODUCER = "vati-execution-style"
STYLE_VERSION = "execution-style/5.1.0"

ZERO, ONE = Decimal("0"), Decimal("1")

#: An order may take at most this share of displayed size per slice. Same
#: reasoning as the ADV participation cap on sizing: taking the book is how a
#: good entry becomes an expensive one.
DEFAULT_PARTICIPATION_CAP = Decimal("0.25")

#: More slices than this stops helping and starts signalling.
MAX_SLICES = 8


class Urgency(str, Enum):
    """Why this order cannot wait. Deterministic sources only."""

    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"      # health degrading, or an event window approaching
    IMMEDIATE = "IMMEDIATE"    # protective exit; waiting is the risk


class StyleRefused(RuntimeError):
    pass


@dataclass(frozen=True)
class LiquidityView:
    """What the venue is showing, as the adapter reported it."""

    displayed_size: Decimal = ZERO
    spread: Decimal = ZERO
    typical_spread: Decimal = ZERO

    @property
    def known(self) -> bool:
        return self.displayed_size > ZERO

    @property
    def spread_multiple(self) -> Optional[Decimal]:
        if self.typical_spread <= ZERO:
            return None
        return self.spread / self.typical_spread


@dataclass(frozen=True)
class ExecutionStyle:
    """How to work one approved order, inside one template's bounds."""

    style_id: str
    trade_intent_id: str
    template_id: str
    template_version: str
    entry_type: str
    max_slippage: Decimal
    slices: int
    slice_quantity: Decimal
    final_slice_quantity: Decimal
    max_wait_ms: int
    urgency: Urgency
    reason: str
    style_version: str = STYLE_VERSION
    seal: str = ""

    @property
    def total_quantity(self) -> Decimal:
        return self.slice_quantity * (self.slices - 1) + self.final_slice_quantity

    def body(self) -> dict[str, Any]:
        return {
            "style_id": self.style_id,
            "trade_intent_id": self.trade_intent_id,
            "template_id": self.template_id,
            "template_version": self.template_version,
            "entry_type": self.entry_type,
            "max_slippage": str(self.max_slippage),
            "slices": self.slices,
            "slice_quantity": str(self.slice_quantity),
            "final_slice_quantity": str(self.final_slice_quantity),
            "total_quantity": str(self.total_quantity),
            "max_wait_ms": self.max_wait_ms,
            "urgency": self.urgency.value,
            "reason": self.reason,
            "style_version": self.style_version,
        }

    def sealed(self) -> "ExecutionStyle":
        return ExecutionStyle(**{**self.__dict__, "seal": canonical_hash(self.body())})

    def seal_ok(self) -> bool:
        return bool(self.seal) and self.seal == canonical_hash(self.body())

    def within(self, t: ExecutionTemplate) -> bool:
        """The check the router can repeat for itself."""
        return (self.entry_type in t.allowed_entry_types
                and self.max_slippage <= t.max_slippage
                and self.max_wait_ms <= t.max_wait_ms
                and 1 <= self.slices <= MAX_SLICES)


def _bounded(value, ceiling):
    """Never above the template. The one function that has to be right."""
    return value if value <= ceiling else ceiling


class ExecutionStyleSelector:
    """Chooses how to work an order the authority already approved."""

    def __init__(self, *, participation_cap: Decimal = DEFAULT_PARTICIPATION_CAP,
                 ledger=None, producer: str = PRODUCER) -> None:
        if not (ZERO < participation_cap <= ONE):
            raise StyleRefused(f"participation cap {participation_cap} is outside (0, 1]")
        self.participation_cap = participation_cap
        self._ledger = ledger
        self._producer = producer

    def select(self, *, trade_intent_id: str, policy_decision, route: Route,
               quantity: Decimal, liquidity: LiquidityView,
               urgency: Urgency = Urgency.NORMAL, now_ms: int) -> ExecutionStyle:
        template_id = getattr(policy_decision, "template_id", "")
        if template_id == DO_NOT_EXECUTE or not template_id:
            raise StyleRefused(f"execution policy refused this order: {template_id or 'none'}")
        t = resolve_template(template_id)
        if not t.allowed_entry_types:
            raise StyleRefused(f"template {t.template_id} permits no entry type")

        entry_type = self._entry_type(t, urgency)
        slices, slice_qty, final_qty, reason = self._slice(route, quantity, liquidity, urgency)
        max_wait = self._wait(t, urgency)
        slippage = self._slippage(t, liquidity, urgency)

        style = ExecutionStyle(
            style_id=canonical_hash({"i": trade_intent_id, "t": now_ms, "tid": t.template_id})[:32],
            trade_intent_id=trade_intent_id,
            template_id=t.template_id,
            template_version=t.version,
            entry_type=entry_type,
            max_slippage=slippage,
            slices=slices,
            slice_quantity=slice_qty,
            final_slice_quantity=final_qty,
            max_wait_ms=max_wait,
            urgency=urgency,
            reason=reason,
        ).sealed()

        if not style.within(t):
            # Belt and braces on _bounded: a style outside its template must
            # never reach the router, even if the arithmetic above is wrong.
            raise StyleRefused(f"selected style escapes template {t.template_id}")

        if self._ledger is not None:
            self._ledger.append(make_event(
                EventKind.EXECUTION_STYLE, self._producer, style.body(),
                event_time_ms=now_ms, received_time_ms=now_ms,
                correlation_id=trade_intent_id))
        return style

    # ------------------------------------------------------------- decisions
    @staticmethod
    def _entry_type(t: ExecutionTemplate, urgency: Urgency) -> str:
        """Prefer the most patient type the template allows, unless waiting is
        the risk — and even then only among types the template already names."""
        allowed = t.allowed_entry_types
        if urgency is Urgency.IMMEDIATE:
            for preferred in ("MARKET", "LIMIT", "PASSIVE_LIMIT"):
                if preferred in allowed:
                    return preferred
        for preferred in ("PASSIVE_LIMIT", "LIMIT", "MARKET"):
            if preferred in allowed:
                return preferred
        return allowed[0]

    @staticmethod
    def _wait(t: ExecutionTemplate, urgency: Urgency) -> int:
        if urgency is Urgency.IMMEDIATE:
            return 0
        if urgency is Urgency.ELEVATED:
            return _bounded(t.max_wait_ms // 2, t.max_wait_ms)
        return t.max_wait_ms

    @staticmethod
    def _slippage(t: ExecutionTemplate, liquidity: LiquidityView,
                  urgency: Urgency) -> Decimal:
        """Only ever narrower than the template.

        A wide spread does not buy a wider cap — it is a reason to tolerate
        *less*, because the measured cost of crossing has gone up.
        """
        cap = t.max_slippage
        mult = liquidity.spread_multiple
        if mult is not None and mult >= Decimal("2") and urgency is not Urgency.IMMEDIATE:
            cap = _bounded(cap / Decimal("2"), t.max_slippage)
        return _bounded(cap, t.max_slippage)

    def _slice(self, route: Route, quantity: Decimal, liquidity: LiquidityView,
               urgency: Urgency) -> tuple[int, Decimal, Decimal, str]:
        """How many pieces, and how big, with the lot step the binding fact."""
        try:
            total, _shortfall = quantise_volume(route.contract, quantity)
        except QuantisationRefused as exc:
            raise StyleRefused(str(exc)) from exc

        if urgency is Urgency.IMMEDIATE or not liquidity.known:
            # No view of depth is not a licence to assume it is deep; it is a
            # reason not to pretend slicing is informed.
            return 1, total, total, ("urgent exit, worked in one" if urgency is Urgency.IMMEDIATE
                                     else "no displayed depth; single order")

        per_slice_cap = liquidity.displayed_size * self.participation_cap
        if per_slice_cap <= ZERO or total <= per_slice_cap:
            return 1, total, total, "size within the participation cap"

        wanted = int((total / per_slice_cap).to_integral_value(rounding="ROUND_CEILING"))
        slices = max(1, min(wanted, MAX_SLICES))

        # Walk the count down until every slice is expressible at the venue.
        while slices > 1:
            candidate = _floor(total / Decimal(slices), route.contract.volume_step)
            if candidate >= route.contract.volume_min:
                break
            slices -= 1
        if slices == 1:
            return 1, total, total, "lot step cannot express a smaller slice"

        slice_qty = _floor(total / Decimal(slices), route.contract.volume_step)
        final = total - slice_qty * (slices - 1)
        return slices, slice_qty, final, (
            f"size is {total} against {liquidity.displayed_size} displayed; "
            f"worked in {slices} at a {self.participation_cap} cap")


def _floor(value: Decimal, step: Decimal) -> Decimal:
    if step <= ZERO:
        return value
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step
