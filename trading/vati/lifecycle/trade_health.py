"""TradeHealth engine (TRD-REV51-099, G5).

Runs on every open position before anything is allowed to consider scaling it
or opening new risk beside it. The question is narrow and deterministic: is
this position behaving like the trade that was put on, or has it become
something else?

The engine is one-directional on purpose. A health verdict can withhold —
block a scale, demand preservation, require a tighter look — and it can never
license anything. There is no HealthState that says "this is going well, take
more", because a position doing well is not evidence that the account can
afford more risk, and conflating those two is how a good run becomes a bad
month. Expansion has its own gate (110) with its own evidence.

Inputs are all deterministic and venue-reported: excursions, elapsed time,
stop distance, spread. No model output reaches this module. That matters
because health gates protection, and INV-FAIL-001 says a model failure must
never be able to disable a protective path — the simplest way to guarantee
that is for the protective path not to read models at all.

A position VAN cannot prove is protected is FAILING, not unknown. The absence
of a confirmed stop is the single loudest fact available about a position.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from vati.core.canonical import canonical_hash, dec
from vati.core.events import EventKind, make_event
from vati.risk.contracts import Direction

PRODUCER = "vati-trade-health"
HEALTH_VERSION = "trade-health/5.1.0"

ZERO, ONE = Decimal("0"), Decimal("1")

#: Fraction of the original risk distance the position has given up against
#: it. Past this the trade is working against its own premise.
ADVERSE_IMPAIRED = Decimal("0.75")
ADVERSE_WATCH = Decimal("0.50")

#: Multiple of the expected horizon after which a position going nowhere is
#: no longer the trade that was put on: the setup's edge was time-bounded.
STAGNANT_TIME_MULTIPLE = Decimal("1.5")
STAGNANT_PROGRESS_R = Decimal("0.25")

#: Fraction of the best unrealised gain handed back. Only meaningful once the
#: position actually had something to hand back.
GIVE_BACK_WATCH = Decimal("0.60")
MEANINGFUL_MFE_R = Decimal("1.0")

#: Spread this many times its typical level is a venue condition, not a trade
#: condition, but it changes what an exit will cost.
SPREAD_ABNORMAL_MULTIPLE = Decimal("3")


class HealthState(str, Enum):
    """Ordered worst-last. Nothing here licenses additional risk."""

    HEALTHY = "HEALTHY"      # behaving as intended
    WATCH = "WATCH"          # deteriorating; no scale
    IMPAIRED = "IMPAIRED"    # working against its premise; preserve
    FAILING = "FAILING"      # unprotected or invalidated; act now

    @property
    def rank(self) -> int:
        return {"HEALTHY": 0, "WATCH": 1, "IMPAIRED": 2, "FAILING": 3}[self.value]


#: Why a position is not healthy. Closed vocabulary, same discipline as the
#: assessment reasons.
HEALTH_REASONS: dict[str, str] = {
    "NO_CONFIRMED_STOP": "no protective stop is confirmed at the venue",
    "STOP_WIDER_THAN_ORIGINAL": "the current stop is further away than the one approved",
    "THESIS_INVALIDATED": "the condition the entry depended on no longer holds",
    "ADVERSE_EXCURSION_DEEP": "the position has given up most of its risk distance",
    "ADVERSE_EXCURSION_ELEVATED": "the position has given up half its risk distance",
    "STAGNANT": "well past its expected horizon with no progress",
    "GIVE_BACK": "most of the best unrealised gain has been handed back",
    "SPREAD_ABNORMAL": "exiting now would cross an abnormally wide spread",
    "MARK_STALE": "the mark used for this assessment is older than its useful life",
}


class HealthInputError(ValueError):
    pass


@dataclass(frozen=True)
class PositionHealthInputs:
    """Deterministic, venue-reported facts about one open position."""

    trade_intent_id: str
    symbol: str
    direction: Direction
    entry_price: Decimal
    current_price: Decimal
    original_stop: Decimal
    current_stop: Optional[Decimal]
    has_confirmed_stop: bool
    opened_ms: int
    now_ms: int
    expected_horizon_ms: int
    #: Worst and best prices seen since entry, as the lifecycle recorded them.
    worst_price: Decimal
    best_price: Decimal
    mark_age_ms: int = 0
    max_mark_age_ms: int = 60_000
    spread: Decimal = ZERO
    typical_spread: Decimal = ZERO
    thesis_invalidated: bool = False

    def __post_init__(self) -> None:
        if self.entry_price <= ZERO:
            raise HealthInputError(f"{self.trade_intent_id} has entry price {self.entry_price}")
        if self.risk_distance <= ZERO:
            raise HealthInputError(
                f"{self.trade_intent_id} has no risk distance; health is undefined without one")

    @property
    def sign(self) -> Decimal:
        return ONE if self.direction is Direction.LONG else Decimal("-1")

    @property
    def risk_distance(self) -> Decimal:
        """Entry to the originally approved stop. The R unit for this trade."""
        return abs(self.entry_price - self.original_stop)

    @property
    def elapsed_ms(self) -> int:
        return max(0, self.now_ms - self.opened_ms)

    @property
    def current_r(self) -> Decimal:
        return self.sign * (self.current_price - self.entry_price) / self.risk_distance

    @property
    def mae_r(self) -> Decimal:
        """Maximum adverse excursion, in R. Always >= 0."""
        adverse = self.sign * (self.worst_price - self.entry_price) / self.risk_distance
        return -adverse if adverse < ZERO else ZERO

    @property
    def mfe_r(self) -> Decimal:
        """Maximum favourable excursion, in R. Always >= 0."""
        fav = self.sign * (self.best_price - self.entry_price) / self.risk_distance
        return fav if fav > ZERO else ZERO

    @property
    def time_fraction(self) -> Optional[Decimal]:
        if self.expected_horizon_ms <= 0:
            return None
        return Decimal(self.elapsed_ms) / Decimal(self.expected_horizon_ms)

    @property
    def give_back_fraction(self) -> Optional[Decimal]:
        if self.mfe_r <= ZERO:
            return None
        handed_back = self.mfe_r - self.current_r
        if handed_back <= ZERO:
            return ZERO
        return handed_back / self.mfe_r

    @property
    def stop_is_wider_than_approved(self) -> bool:
        """INV-RISK-001 has no stop widening, so this is a defect, not a state."""
        if self.current_stop is None:
            return False
        return abs(self.entry_price - self.current_stop) > self.risk_distance


@dataclass(frozen=True)
class TradeHealth:
    trade_intent_id: str
    symbol: str
    state: HealthState
    reasons: tuple[str, ...]
    current_r: Decimal
    mae_r: Decimal
    mfe_r: Decimal
    assessed_ms: int
    health_version: str = HEALTH_VERSION

    @property
    def blocks_scaling(self) -> bool:
        """Anything but HEALTHY withholds. Health never licenses."""
        return self.state is not HealthState.HEALTHY

    @property
    def requires_preservation(self) -> bool:
        return self.state.rank >= HealthState.IMPAIRED.rank

    @property
    def is_urgent(self) -> bool:
        return self.state is HealthState.FAILING

    def body(self) -> dict[str, Any]:
        return {
            "trade_intent_id": self.trade_intent_id,
            "symbol": self.symbol,
            "state": self.state.value,
            "reasons": list(self.reasons),
            "reason_detail": [HEALTH_REASONS[r] for r in self.reasons],
            "current_r": str(self.current_r),
            "mae_r": str(self.mae_r),
            "mfe_r": str(self.mfe_r),
            "blocks_scaling": self.blocks_scaling,
            "requires_preservation": self.requires_preservation,
            "assessed_ms": self.assessed_ms,
            "health_version": self.health_version,
        }

    @property
    def digest(self) -> str:
        return canonical_hash(self.body())


class TradeHealthEngine:
    """Deterministic health assessment. Reads no model output, ever."""

    def __init__(self, *, ledger=None, producer: str = PRODUCER) -> None:
        self._ledger = ledger
        self._producer = producer

    def assess(self, inp: PositionHealthInputs) -> TradeHealth:
        reasons: list[str] = []
        state = HealthState.HEALTHY

        def escalate(to: HealthState, reason: str) -> None:
            nonlocal state
            if reason not in reasons:
                reasons.append(reason)
            if to.rank > state.rank:
                state = to

        # The loudest facts first. An unprotected position is failing whatever
        # the price is doing.
        if not inp.has_confirmed_stop:
            escalate(HealthState.FAILING, "NO_CONFIRMED_STOP")
        if inp.stop_is_wider_than_approved:
            escalate(HealthState.FAILING, "STOP_WIDER_THAN_ORIGINAL")
        if inp.thesis_invalidated:
            escalate(HealthState.FAILING, "THESIS_INVALIDATED")

        # A stale mark makes every price-derived judgement below unreliable,
        # so it is a WATCH in its own right rather than a silent caveat.
        if inp.mark_age_ms > inp.max_mark_age_ms:
            escalate(HealthState.WATCH, "MARK_STALE")

        if inp.mae_r >= ADVERSE_IMPAIRED:
            escalate(HealthState.IMPAIRED, "ADVERSE_EXCURSION_DEEP")
        elif inp.mae_r >= ADVERSE_WATCH:
            escalate(HealthState.WATCH, "ADVERSE_EXCURSION_ELEVATED")

        tf = inp.time_fraction
        if tf is not None and tf >= STAGNANT_TIME_MULTIPLE and inp.current_r < STAGNANT_PROGRESS_R:
            escalate(HealthState.WATCH, "STAGNANT")

        gb = inp.give_back_fraction
        if gb is not None and inp.mfe_r >= MEANINGFUL_MFE_R and gb >= GIVE_BACK_WATCH:
            escalate(HealthState.WATCH, "GIVE_BACK")

        if inp.typical_spread > ZERO and inp.spread >= inp.typical_spread * SPREAD_ABNORMAL_MULTIPLE:
            escalate(HealthState.WATCH, "SPREAD_ABNORMAL")

        health = TradeHealth(
            trade_intent_id=inp.trade_intent_id, symbol=inp.symbol, state=state,
            reasons=tuple(reasons), current_r=inp.current_r, mae_r=inp.mae_r,
            mfe_r=inp.mfe_r, assessed_ms=inp.now_ms)

        if self._ledger is not None:
            self._ledger.append(make_event(
                EventKind.TRADE_HEALTH, self._producer, health.body(),
                event_time_ms=inp.now_ms, received_time_ms=inp.now_ms,
                correlation_id=inp.trade_intent_id))
        return health
