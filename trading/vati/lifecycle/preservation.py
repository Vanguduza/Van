"""Loss containment and profit preservation (TRD-REV51-111, G7).

Runs on every open family before any scale or new-entry action is considered,
and its output is the reason those actions may not happen. The ordering is the
point: a system that evaluates new opportunities before protecting what it
already holds will, on its worst day, add risk to an account that is already
losing.

Every action this module can produce moves in one direction. The vocabulary
has TIGHTEN_STOP and has no widen; it has PARTIAL_CLOSE and FULL_CLOSE and has
no add. That is INV-RISK-001 expressed as a type rather than as a policy
document — there is no value any caller can pass that turns a preservation
decision into an increase in exposure, and no branch to audit for one.

Urgency matters more than elegance here. A FAILING family produces a
FULL_CLOSE immediately, without waiting for a better price, because the cases
that produce FAILING — no confirmed stop, an invalidated thesis, a stop wider
than the one approved — are exactly the cases where waiting for a better price
is how a bounded loss becomes an unbounded one.

Nothing in this module reads a model. Preservation must work when every
provider is down, so the module imports nothing from the cognition package and
the certification harness checks that it still does not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Optional, Sequence

from vati.core.canonical import canonical_hash, dec
from vati.core.events import EventKind, make_event
from vati.lifecycle.envelope import PositionRiskEnvelope
from vati.lifecycle.family import FamilyState, PositionFamily
from vati.lifecycle.trade_health import HealthState, TradeHealth
from vati.risk.contracts import Direction

PRODUCER = "vati-preservation"
PRESERVATION_VERSION = "preservation/5.1.0"

ZERO, ONE = Decimal("0"), Decimal("1")

#: Gain at which the stop is moved to the entry price. Not a claim that
#: breakeven stops improve expectancy — a claim that a trade which has been
#: 1R in front and returns to a loss is a specific, avoidable way to lose.
BREAKEVEN_TRIGGER_R = Decimal("1.0")

#: Beyond this, the stop trails at the configured fraction of the excursion.
TRAIL_TRIGGER_R = Decimal("2.0")
TRAIL_FRACTION = Decimal("0.5")

#: Give-back at which half the position comes off, once the gain was real.
PARTIAL_CLOSE_GIVE_BACK = Decimal("0.50")
PARTIAL_CLOSE_FRACTION = Decimal("0.50")

#: Worst-case loss, as a fraction of equity, above which no new risk is
#: admitted anywhere on the account until it comes down.
ACCOUNT_HALT_WORST_CASE_PCT = Decimal("0.06")


class ActionKind(str, Enum):
    """Everything preservation may do. There is no widen and no add."""

    NONE = "NONE"
    TIGHTEN_STOP = "TIGHTEN_STOP"
    PARTIAL_CLOSE = "PARTIAL_CLOSE"
    FULL_CLOSE = "FULL_CLOSE"
    HALT_NEW_RISK = "HALT_NEW_RISK"


class Urgency(str, Enum):
    ROUTINE = "ROUTINE"
    PROMPT = "PROMPT"
    IMMEDIATE = "IMMEDIATE"


#: Why an action was taken. Closed vocabulary, same discipline as elsewhere.
PRESERVATION_REASONS: dict[str, str] = {
    "UNPROTECTED": "no confirmed stop; the position's loss is unbounded",
    "THESIS_INVALIDATED": "the condition the entry depended on no longer holds",
    "STOP_WIDER_THAN_APPROVED": "the resting stop is further than the approved distance",
    "FAMILY_DIVERGED": "the venue and the family disagree about what is held",
    "BREAKEVEN_REACHED": "the position has been far enough in front to stop risking the entry",
    "TRAIL_ADVANCED": "the excursion supports a tighter stop",
    "GIVE_BACK": "most of a real gain has been handed back",
    "HEALTH_IMPAIRED": "the position is working against its own premise",
    "ACCOUNT_WORST_CASE_HIGH": "account worst-case loss is above its ceiling",
    "RISK_UNKNOWN": "the family's risk cannot be computed",
}


@dataclass(frozen=True)
class PreservationAction:
    family_id: str
    kind: ActionKind
    urgency: Urgency
    reasons: tuple[str, ...]
    #: Present for TIGHTEN_STOP. Always tighter than the current stop.
    new_stop: Optional[Decimal] = None
    #: Present for PARTIAL_CLOSE. A fraction of the net quantity, in (0, 1).
    close_fraction: Optional[Decimal] = None
    detail: str = ""
    decided_ms: int = 0
    preservation_version: str = PRESERVATION_VERSION

    @property
    def is_exit(self) -> bool:
        return self.kind in (ActionKind.PARTIAL_CLOSE, ActionKind.FULL_CLOSE)

    @property
    def blocks_new_risk(self) -> bool:
        return self.kind is not ActionKind.NONE

    def body(self) -> dict[str, Any]:
        return {
            "family_id": self.family_id,
            "kind": self.kind.value,
            "urgency": self.urgency.value,
            "reasons": list(self.reasons),
            "reason_detail": [PRESERVATION_REASONS[r] for r in self.reasons],
            "new_stop": None if self.new_stop is None else str(self.new_stop),
            "close_fraction": None if self.close_fraction is None else str(self.close_fraction),
            "detail": self.detail,
            "decided_ms": self.decided_ms,
            "blocks_new_risk": self.blocks_new_risk,
            "preservation_version": self.preservation_version,
        }

    @property
    def digest(self) -> str:
        return canonical_hash(self.body())


class PreservationEngine:
    """Decides what must be protected, before anything may be added."""

    def __init__(self, *, ledger=None, producer: str = PRODUCER) -> None:
        self._ledger = ledger
        self._producer = producer

    # ------------------------------------------------------------------ family
    def evaluate(self, *, family: PositionFamily, health: TradeHealth,
                 envelope: PositionRiskEnvelope, mark: Decimal,
                 now_ms: int) -> PreservationAction:
        mark = dec(mark)
        reasons: list[str] = []

        # --- immediate exits. No waiting for a better price. ---
        if health.state is HealthState.FAILING:
            for code, present in (("UNPROTECTED", "NO_CONFIRMED_STOP" in health.reasons),
                                  ("THESIS_INVALIDATED", "THESIS_INVALIDATED" in health.reasons),
                                  ("STOP_WIDER_THAN_APPROVED",
                                   "STOP_WIDER_THAN_ORIGINAL" in health.reasons)):
                if present:
                    reasons.append(code)
            return self._act(family, ActionKind.FULL_CLOSE, Urgency.IMMEDIATE,
                             tuple(reasons or ("UNPROTECTED",)), now_ms,
                             detail="failing health admits no delay")

        if family.state is FamilyState.DIVERGED:
            return self._act(family, ActionKind.FULL_CLOSE, Urgency.IMMEDIATE,
                             ("FAMILY_DIVERGED",), now_ms,
                             detail=family.divergence_detail)

        if not envelope.risk_is_known:
            return self._act(family, ActionKind.HALT_NEW_RISK, Urgency.PROMPT,
                             ("RISK_UNKNOWN",), now_ms,
                             detail="a family whose stop is unknown has unbounded risk")

        # --- take some off when a real gain is being handed back ---
        if "GIVE_BACK" in health.reasons and health.mfe_r >= BREAKEVEN_TRIGGER_R:
            return self._act(family, ActionKind.PARTIAL_CLOSE, Urgency.PROMPT,
                             ("GIVE_BACK",), now_ms,
                             close_fraction=PARTIAL_CLOSE_FRACTION,
                             detail=f"mfe {health.mfe_r}R, now {health.current_r}R")

        # --- tighten, where tightening is available ---
        tighten = self._tighten_to(family, health, mark)
        if tighten is not None:
            new_stop, why = tighten
            return self._act(family, ActionKind.TIGHTEN_STOP, Urgency.ROUTINE,
                             (why,), now_ms, new_stop=new_stop,
                             detail=f"{family.current_stop} -> {new_stop}")

        if health.state is HealthState.IMPAIRED:
            return self._act(family, ActionKind.HALT_NEW_RISK, Urgency.PROMPT,
                             ("HEALTH_IMPAIRED",), now_ms,
                             detail=", ".join(health.reasons))

        return self._act(family, ActionKind.NONE, Urgency.ROUTINE, (), now_ms)

    def _tighten_to(self, family: PositionFamily, health: TradeHealth,
                    mark: Decimal) -> Optional[tuple[Decimal, str]]:
        """The tightest defensible stop, or None when none is available."""
        entry = family.average_entry
        if entry is None or family.current_stop is None or family.original_stop is None:
            return None
        risk_distance = abs(entry - family.original_stop)
        if risk_distance <= ZERO:
            return None

        candidate: Optional[Decimal] = None
        why = ""
        if health.mfe_r >= TRAIL_TRIGGER_R:
            give = risk_distance * health.mfe_r * TRAIL_FRACTION
            candidate = entry + give if family.direction is Direction.LONG else entry - give
            why = "TRAIL_ADVANCED"
        elif health.mfe_r >= BREAKEVEN_TRIGGER_R:
            candidate = entry
            why = "BREAKEVEN_REACHED"
        if candidate is None:
            return None

        # Only ever tighter, and never through the mark: a stop on the wrong
        # side of the current price is an exit, and exits are the exit path's
        # business, not the stop's.
        if family.direction is Direction.LONG:
            if candidate <= family.current_stop or candidate >= mark:
                return None
        else:
            if candidate >= family.current_stop or candidate <= mark:
                return None
        return candidate, why

    # ----------------------------------------------------------------- account
    def account_verdict(self, envelopes: Sequence[PositionRiskEnvelope], *,
                        equity: Decimal, now_ms: int) -> PreservationAction:
        """One verdict for the whole account, evaluated before new entries."""
        equity = dec(equity)
        unknown = [e.family_id for e in envelopes if not e.risk_is_known]
        worst = sum((e.worst_case_loss for e in envelopes if e.risk_is_known), ZERO)
        pct = (worst / equity) if equity > ZERO else None

        if unknown:
            return self._act(None, ActionKind.HALT_NEW_RISK, Urgency.PROMPT,
                             ("RISK_UNKNOWN",), now_ms,
                             detail=f"families with unknown risk: {', '.join(sorted(unknown))}")
        if pct is not None and pct >= ACCOUNT_HALT_WORST_CASE_PCT:
            return self._act(None, ActionKind.HALT_NEW_RISK, Urgency.PROMPT,
                             ("ACCOUNT_WORST_CASE_HIGH",), now_ms,
                             detail=f"worst case {pct} of equity")
        return self._act(None, ActionKind.NONE, Urgency.ROUTINE, (), now_ms)

    # --------------------------------------------------------------- internals
    def _act(self, family: Optional[PositionFamily], kind: ActionKind, urgency: Urgency,
             reasons: tuple[str, ...], now_ms: int, *, new_stop: Optional[Decimal] = None,
             close_fraction: Optional[Decimal] = None, detail: str = "") -> PreservationAction:
        action = PreservationAction(
            family_id=family.family_id if family is not None else "*account*",
            kind=kind, urgency=urgency, reasons=reasons, new_stop=new_stop,
            close_fraction=close_fraction, detail=detail, decided_ms=now_ms)
        if self._ledger is not None and kind is not ActionKind.NONE:
            self._ledger.append(make_event(
                EventKind.PRESERVATION_ACTION, self._producer, action.body(),
                event_time_ms=now_ms, received_time_ms=now_ms,
                correlation_id=action.family_id))
        return action
