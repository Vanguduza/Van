"""Cognitive budget and degradation ladder (TRD-REV51-096, G4).

Cognition costs money and time, and both are finite. The question this packet
answers is what the system does as they run out — and the answer has to be
decided in advance, because a system deciding it under pressure will decide it
badly.

The ladder descends in one direction: each rung removes something cognition
*adds*, never something the deterministic path *guarantees*. That ordering is
INV-FAIL-001 made concrete. Blind review goes first because it is the most
expensive per unit of protection. Optional context goes next. Then cognition
narrows to high-impact decision points only. The bottom rung is no cognition
at all — which is safe by construction, because cognition is reduce-only: with
none of it, every trade is exactly the size the Risk Authority approved.

What the ladder never touches: stops, exits, kill switches, reconciliation,
the pre-trade controls. There is no rung that buys headroom by turning off a
protection, and `assert_protections_intact` exists so that claim is checked
rather than trusted.

Spend is attributed to the *context*, not the model, so falling down the
provider hierarchy cannot reset an allowance (see 132).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from vati.core.events import EventKind, make_event

PRODUCER = "vati-cognitive-budget"
BUDGET_VERSION = "cognitive-budget/5.1.0"


class Rung(int, Enum):
    """Descending rungs. Each removes something cognition adds."""

    FULL = 0                 # full context, retrieval, blind review on high impact
    NO_REVIEW = 1            # blind review suspended
    REDUCED_CONTEXT = 2      # optional context sections dropped
    HIGH_IMPACT_ONLY = 3     # cognition only for high-impact decision points
    SUSPENDED = 4            # no cognition; the deterministic path alone

    @property
    def label(self) -> str:
        return self.name


#: What each rung stops doing. Every entry is an addition being withdrawn.
RUNG_EFFECTS: dict[Rung, str] = {
    Rung.FULL: "nothing withdrawn",
    Rung.NO_REVIEW: "blind review suspended; assessments still recorded and measured",
    Rung.REDUCED_CONTEXT: "optional context sections dropped; the drop is sealed into the context",
    Rung.HIGH_IMPACT_ONLY: "cognition invoked only for high-impact decision points",
    Rung.SUSPENDED: "no cognition; every trade is the size the Risk Authority approved",
}

#: Fraction of the window budget remaining at or below which each rung engages.
#: Descending thresholds; the first one crossed wins.
RUNG_THRESHOLDS: tuple[tuple[Rung, float], ...] = (
    (Rung.SUSPENDED, 0.00),
    (Rung.HIGH_IMPACT_ONLY, 0.10),
    (Rung.REDUCED_CONTEXT, 0.25),
    (Rung.NO_REVIEW, 0.50),
    (Rung.FULL, 1.00),
)

#: Deterministic protections the ladder must never be able to reach. Named so
#: the assertion below is a list to check rather than an intention to hold.
PROTECTED_CONTROLS: tuple[str, ...] = (
    "risk_authority", "execution_router", "kill_switch", "protection_manager",
    "reconciliation", "pre_trade_controls", "stop_placement", "exit_management",
)


class BudgetViolation(RuntimeError):
    """Something tried to buy cognition headroom with a deterministic control."""


@dataclass(frozen=True)
class BudgetDecision:
    """Whether to invoke cognition now, and in what shape."""

    allowed: bool
    rung: Rung
    remaining_micros: int
    remaining_invocations: int
    reason: str
    include_review: bool
    include_optional_context: bool
    high_impact_only: bool

    def body(self) -> dict[str, Any]:
        return {
            "budget_version": BUDGET_VERSION,
            "allowed": self.allowed,
            "rung": self.rung.label,
            "rung_effect": RUNG_EFFECTS[self.rung],
            "remaining_micros": self.remaining_micros,
            "remaining_invocations": self.remaining_invocations,
            "reason": self.reason,
            "include_review": self.include_review,
            "include_optional_context": self.include_optional_context,
            "high_impact_only": self.high_impact_only,
        }


@dataclass
class _Window:
    start_ms: int = 0
    spent_micros: int = 0
    invocations: int = 0


class CognitiveBudget:
    """A fixed-window allowance with a pre-declared degradation ladder."""

    def __init__(self, *, micros_per_window: int, invocations_per_window: int,
                 window_ms: int = 3_600_000, ledger=None,
                 producer: str = PRODUCER) -> None:
        if micros_per_window <= 0 or invocations_per_window <= 0 or window_ms <= 0:
            raise ValueError("a budget of zero is a suspension, not a budget; say so explicitly")
        self.micros_per_window = micros_per_window
        self.invocations_per_window = invocations_per_window
        self.window_ms = window_ms
        self._ledger = ledger
        self._producer = producer
        self._window = _Window()
        self._by_context: dict[str, int] = {}
        self._floor: Optional[Rung] = None

    # ------------------------------------------------------------------ state
    def _roll(self, now_ms: int) -> None:
        if now_ms - self._window.start_ms >= self.window_ms:
            self._window = _Window(start_ms=now_ms - (now_ms % self.window_ms))

    def remaining_micros(self, now_ms: int) -> int:
        self._roll(now_ms)
        return max(0, self.micros_per_window - self._window.spent_micros)

    def remaining_invocations(self, now_ms: int) -> int:
        self._roll(now_ms)
        return max(0, self.invocations_per_window - self._window.invocations)

    def fraction_remaining(self, now_ms: int) -> float:
        """The tighter of the two allowances. Running out of either is running out."""
        self._roll(now_ms)
        by_cost = self.remaining_micros(now_ms) / self.micros_per_window
        by_count = self.remaining_invocations(now_ms) / self.invocations_per_window
        return min(by_cost, by_count)

    def set_floor(self, rung: Optional[Rung]) -> None:
        """Pin the ladder no higher than `rung`, e.g. during an incident.

        A floor can only make cognition do less, never more, so there is no
        value an operator can set here that widens anything.
        """
        self._floor = rung

    def rung(self, now_ms: int) -> Rung:
        frac = self.fraction_remaining(now_ms)
        chosen = Rung.FULL
        for rung, threshold in RUNG_THRESHOLDS:
            if frac <= threshold:
                chosen = rung
                break
        if self._floor is not None and self._floor.value > chosen.value:
            chosen = self._floor
        return chosen

    # -------------------------------------------------------------- decision
    def check(self, *, now_ms: int, context_hash: str = "",
              is_high_impact: bool = False) -> BudgetDecision:
        """Called before every cognition invocation. Never raises."""
        rung = self.rung(now_ms)
        remaining_micros = self.remaining_micros(now_ms)
        remaining_calls = self.remaining_invocations(now_ms)

        allowed = rung is not Rung.SUSPENDED
        reason = RUNG_EFFECTS[rung]
        if rung is Rung.HIGH_IMPACT_ONLY and not is_high_impact:
            allowed = False
            reason = "budget rung admits high-impact decision points only"
        if remaining_calls <= 0 or remaining_micros <= 0:
            allowed = False
            rung = Rung.SUSPENDED
            reason = "window allowance exhausted"

        decision = BudgetDecision(
            allowed=allowed,
            rung=rung,
            remaining_micros=remaining_micros,
            remaining_invocations=remaining_calls,
            reason=reason,
            include_review=rung is Rung.FULL,
            include_optional_context=rung.value <= Rung.NO_REVIEW.value,
            high_impact_only=rung.value >= Rung.HIGH_IMPACT_ONLY.value,
        )
        if self._ledger is not None:
            self._ledger.append(make_event(
                EventKind.COGNITIVE_BUDGET, self._producer,
                {**decision.body(), "context_hash": context_hash},
                event_time_ms=now_ms, received_time_ms=now_ms,
                correlation_id=context_hash))
        return decision

    def spend(self, *, micros: int, now_ms: int, context_hash: str = "") -> None:
        """Record what an invocation actually cost, against the context."""
        if micros < 0:
            raise ValueError("a negative spend is a refund, and there are none")
        self._roll(now_ms)
        self._window.spent_micros += micros
        self._window.invocations += 1
        if context_hash:
            self._by_context[context_hash] = self._by_context.get(context_hash, 0) + micros

    def spent_on(self, context_hash: str) -> int:
        """Spend follows the context, so a provider fallback cannot reset it."""
        return self._by_context.get(context_hash, 0)

    # ------------------------------------------------------------- invariant
    @staticmethod
    def assert_protections_intact(disabled_controls: Optional[list[str]] = None) -> None:
        """INV-FAIL-001, checked rather than trusted.

        Callers that degrade cognition pass what they turned off. Naming any
        deterministic control is a programming error loud enough to stop on.
        """
        touched = sorted(set(disabled_controls or ()) & set(PROTECTED_CONTROLS))
        if touched:
            raise BudgetViolation(
                "degradation would disable deterministic protection: " + ", ".join(touched))

    def report(self, *, now_ms: int) -> dict[str, Any]:
        return {
            "budget_version": BUDGET_VERSION,
            "window_ms": self.window_ms,
            "micros_per_window": self.micros_per_window,
            "invocations_per_window": self.invocations_per_window,
            "spent_micros": self._window.spent_micros,
            "invocations": self._window.invocations,
            "fraction_remaining": round(self.fraction_remaining(now_ms), 6),
            "rung": self.rung(now_ms).label,
            "floor": None if self._floor is None else self._floor.label,
            "protected_controls": list(PROTECTED_CONTROLS),
        }
