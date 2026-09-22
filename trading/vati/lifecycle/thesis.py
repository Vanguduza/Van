"""Trade thesis: what the trade was for, and whether that is still true (GAP-F-003).

GAP-F-003 says VAN's reasoning layer cannot observe trading state. The read path
is half of that; the other half is that there was nothing worth reading. A
position carried an entry, a stop and a health verdict, and nothing anywhere
recorded *why* it was opened — so "does this news change my thesis" (REQ-FLOW-08)
had no thesis to change, and "why is my trade moving" (REQ-FLOW-07) could only be
answered with a price.

Two objects close that.

`TradeThesis` is sealed once, when an intent is approved. It is the claim the
trade is making: the expected path, the conditions that would prove it wrong,
the conditions that would confirm it, the adverse signals worth watching, and
what kind of event it is exposed to. It is hashed and written to the ledger, so
it cannot be edited after the outcome is known (INV-REPLAY-001) — a thesis you
can revise in hindsight is a story, not a claim.

`ThesisAssessment` is produced every cycle for every open position. It extends
`lifecycle/trade_health.py` rather than duplicating it: the deterministic
health verdict is an *input*, and this adds the dimensions health deliberately
does not carry — volatility change, liquidity change, portfolio interaction,
time in trade, R, and event impact. Health answers "is this position behaving
as intended"; the thesis answers "is the reason for it still there".

What this module may and may not do
-----------------------------------
It may withhold and it may describe. It cannot license. `ASYMMETRIC` and
`STRONGER` exist because an owner needs to know when a trade is working, and
they are attached to a `PositionAdjustmentProposal` that still has to pass
`RiskAuthority.evaluate` — no state here authorises size (INV-AUTH-001), and
the ADD path in `scale_policy.py` is additionally capped at the position's
*original* approved risk, so "winning" can never mean "more risk".

Model output does not reach this module. Event impact arrives as a materiality
score in [0, 1] from `events/news_ingress.py`, which is itself reduce-only, and
`trade_health.py` stays model-free for the reason its own docstring gives:
health gates protection, and INV-FAIL-001 forbids a model failure from being
able to disable a protective path.

Persistence is on state change only. Writing an INTACT assessment on every bar
would bury the three transitions that matter in ten thousand rows that say
nothing happened.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping, Optional

from vati.core.canonical import canonical_hash, dec
from vati.core.events import EventKind, make_event
from vati.lifecycle.trade_health import HealthState, TradeHealth
from vati.risk.contracts import Direction

PRODUCER = "vati-trade-thesis"
THESIS_VERSION = "trade-thesis/5.1.0"
ASSESSMENT_VERSION = "thesis-assessment/5.1.0"

ZERO, ONE = Decimal("0"), Decimal("1")

#: Volatility this many times its entry level has changed the trade's terms:
#: the same stop distance is now a different bet.
VOLATILITY_RISKIER_MULTIPLE = Decimal("1.5")
VOLATILITY_CALMER_MULTIPLE = Decimal("0.7")

#: Liquidity below this fraction of its entry level means exiting costs more
#: than the plan assumed.
LIQUIDITY_IMPAIRED_FRACTION = Decimal("0.6")

#: Event materiality at or above this is treated as bearing on the thesis
#: rather than as background noise.
EVENT_MATERIAL = Decimal("0.5")

#: R at which a position is far enough in front that the asymmetry has changed.
ASYMMETRIC_R = Decimal("1.5")

#: R in front at which "overextended" becomes a fair description: the move has
#: gone well past what the thesis claimed.
OVEREXTENDED_R_MULTIPLE = Decimal("1.5")

#: Fraction of the expected horizon past which a thesis that has not confirmed
#: is weakening on time alone.
TIME_WEAKENING_FRACTION = Decimal("1.0")


class ThesisError(ValueError):
    pass


class ThesisState(str, Enum):
    """What this cycle says about the claim the trade was making.

    Ordered by nothing: these are descriptions, not a severity ladder. Severity
    lives in `HealthState`, which is what protection reads.
    """

    INTACT = "INTACT"                # the claim still holds, nothing has moved
    STRONGER = "STRONGER"            # a confirmation condition has been met
    WEAKER = "WEAKER"                # evidence against, not yet decisive
    INVALIDATED = "INVALIDATED"      # an invalidation condition has fired
    OVEREXTENDED = "OVEREXTENDED"    # the move has gone past what was claimed
    RISKIER = "RISKIER"              # same claim, worse terms (vol, liquidity, event)
    ASYMMETRIC = "ASYMMETRIC"        # protected and in front; downside is bounded


#: Why an assessment reached its state. Closed vocabulary, same discipline as
#: `HEALTH_REASONS` and the cognition reason registry: an unclassified reason
#: is forbidden (INV-LEARN-001), including here.
THESIS_REASONS: dict[str, str] = {
    "INVALIDATION_PRICE": "price reached a level the thesis said it would not",
    "INVALIDATION_STRUCTURE": "the structural condition the entry depended on broke",
    "INVALIDATION_REGIME": "the regime the thesis was written for no longer holds",
    "INVALIDATION_TIME": "the thesis' own deadline passed without confirmation",
    "CONFIRMATION_MET": "a declared confirmation condition was satisfied",
    "ADVERSE_SIGNAL": "a declared adverse signal is present",
    "VOLATILITY_EXPANDED": "realised volatility is materially above entry conditions",
    "VOLATILITY_CONTRACTED": "realised volatility is materially below entry conditions",
    "LIQUIDITY_IMPAIRED": "quoted depth is materially worse than at entry",
    "CORRELATION_CROWDED": "the book now carries this exposure under another name",
    "TIME_IN_TRADE": "the position is past its expected horizon",
    "R_MULTIPLE_AHEAD": "the position is materially in front on an R basis",
    "R_MULTIPLE_BEHIND": "the position is materially behind on an R basis",
    "EVENT_IMPACT": "a relevant event bears on this position",
    "PROTECTION_AT_BREAK_EVEN": "protection is at or beyond break-even",
    "HEALTH_DEGRADED": "the deterministic health verdict is not HEALTHY",
    "MOVE_EXCEEDED_EXPECTATION": "the realised move is past the expected path",
}


def _reasons_ok(reasons: tuple[str, ...]) -> tuple[str, ...]:
    for r in reasons:
        if r not in THESIS_REASONS:
            raise ThesisError(f"{r!r} is not a classified thesis reason")
    return reasons


# ------------------------------------------------------------------- the claim
@dataclass(frozen=True)
class TradeThesis:
    """The claim one trade is making, sealed at approval and never edited.

    `market_state_hash` binds it to what was known; `capsule_hash` binds it to
    the strategy version that made the claim. Both are in the seal, so a thesis
    cannot be quietly re-pointed at a different state or a different capsule
    once the outcome is known.
    """

    trade_intent_id: str
    symbol: str
    strategy_id: str
    direction: Direction
    capsule_hash: str
    market_state_hash: str
    #: One owner-readable sentence assembled from the capsule, never parsed.
    statement: str
    #: What the trade expects to happen, in its own terms.
    expected_path: Mapping[str, Any]
    #: Conditions that would prove the claim wrong. Keys are the four axes the
    #: assessment knows how to check: price, structure, regime, time.
    invalidation: Mapping[str, Any]
    #: Conditions that would confirm it.
    confirmation: Mapping[str, Any]
    #: Named signals that argue against the claim while it is open.
    adverse_signals: tuple[str, ...]
    #: Event classes and currencies this claim is exposed to.
    event_sensitivity: tuple[str, ...]
    entry: Decimal
    original_stop: Decimal
    #: Risk approved for this position at entry. The ADD ceiling in
    #: `scale_policy.py` is measured against this number and no other.
    original_approved_risk_pct: Decimal
    expected_horizon_ms: int
    created_ms: int
    #: Entry-time market terms, so "riskier than when we entered" is a
    #: comparison rather than an opinion.
    entry_volatility: Optional[Decimal] = None
    entry_liquidity: Optional[Decimal] = None
    thesis_version: str = THESIS_VERSION
    seal: str = ""

    def __post_init__(self) -> None:
        if not self.trade_intent_id:
            raise ThesisError("a thesis without a trade intent id belongs to nothing")
        if self.risk_distance <= ZERO:
            raise ThesisError(
                f"{self.trade_intent_id} has no risk distance; R is undefined")
        unknown = sorted(set(self.invalidation) - {"price", "structure", "regime", "time_ms"})
        if unknown:
            raise ThesisError(
                f"{self.trade_intent_id} declares invalidation on {unknown}, which "
                "nothing checks; an unchecked invalidation condition is worse than none")

    @property
    def sign(self) -> Decimal:
        return ONE if self.direction is Direction.LONG else Decimal("-1")

    @property
    def risk_distance(self) -> Decimal:
        return abs(self.entry - self.original_stop)

    def body(self) -> dict[str, Any]:
        return {
            "trade_intent_id": self.trade_intent_id,
            "symbol": self.symbol,
            "strategy_id": self.strategy_id,
            "direction": self.direction.value,
            "capsule_hash": self.capsule_hash,
            "market_state_hash": self.market_state_hash,
            "statement": self.statement,
            "expected_path": dict(sorted(self.expected_path.items())),
            "invalidation": dict(sorted(self.invalidation.items())),
            "confirmation": dict(sorted(self.confirmation.items())),
            "adverse_signals": list(self.adverse_signals),
            "event_sensitivity": list(self.event_sensitivity),
            "entry": str(self.entry),
            "original_stop": str(self.original_stop),
            "original_approved_risk_pct": str(self.original_approved_risk_pct),
            "expected_horizon_ms": self.expected_horizon_ms,
            "created_ms": self.created_ms,
            "entry_volatility": None if self.entry_volatility is None else str(self.entry_volatility),
            "entry_liquidity": None if self.entry_liquidity is None else str(self.entry_liquidity),
            "thesis_version": self.thesis_version,
        }

    def sealed(self) -> "TradeThesis":
        return TradeThesis(**{**self.__dict__, "seal": canonical_hash(self.body())})

    def seal_ok(self) -> bool:
        return bool(self.seal) and self.seal == canonical_hash(self.body())

    def to_dict(self) -> dict[str, Any]:
        return {**self.body(), "seal": self.seal}

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "TradeThesis":
        """Rebuild from a ledger payload. Used by the gateway read models."""
        return cls(
            trade_intent_id=str(payload["trade_intent_id"]),
            symbol=str(payload["symbol"]),
            strategy_id=str(payload.get("strategy_id", "")),
            direction=Direction(str(payload["direction"])),
            capsule_hash=str(payload.get("capsule_hash", "")),
            market_state_hash=str(payload.get("market_state_hash", "")),
            statement=str(payload.get("statement", "")),
            expected_path=dict(payload.get("expected_path") or {}),
            invalidation=dict(payload.get("invalidation") or {}),
            confirmation=dict(payload.get("confirmation") or {}),
            adverse_signals=tuple(payload.get("adverse_signals") or ()),
            event_sensitivity=tuple(payload.get("event_sensitivity") or ()),
            entry=dec(payload["entry"]),
            original_stop=dec(payload["original_stop"]),
            original_approved_risk_pct=dec(payload.get("original_approved_risk_pct", "0")),
            expected_horizon_ms=int(payload.get("expected_horizon_ms", 0)),
            created_ms=int(payload.get("created_ms", 0)),
            entry_volatility=(None if payload.get("entry_volatility") is None
                              else dec(payload["entry_volatility"])),
            entry_liquidity=(None if payload.get("entry_liquidity") is None
                             else dec(payload["entry_liquidity"])),
            seal=str(payload.get("seal", "")),
        )


# ------------------------------------------------------------- the observation
@dataclass(frozen=True)
class ThesisInputs:
    """Everything the assessment reads. Deterministic or explicitly bounded.

    `event_materiality` is the only field sourced from outside the venue, and
    it is bounded to [0, 1] by `news_ingress.py` before it reaches here.
    """

    thesis: TradeThesis
    health: TradeHealth
    current_price: Decimal
    now_ms: int
    current_stop: Optional[Decimal] = None
    #: Current realised volatility on the same basis as `thesis.entry_volatility`.
    volatility: Optional[Decimal] = None
    #: Current liquidity on the same basis as `thesis.entry_liquidity`.
    liquidity: Optional[Decimal] = None
    #: Correlation multiplier from `risk/dependency.py`. <= 1 by construction;
    #: below 1 means the book already carries this exposure.
    correlation_multiplier: Decimal = ONE
    #: Structural/regime truth from the current market state.
    structure_broken: bool = False
    regime_label: str = ""
    #: Which declared adverse signals are present right now.
    adverse_present: tuple[str, ...] = ()
    #: Which declared confirmation conditions have been met.
    confirmations_met: tuple[str, ...] = ()
    #: [0, 1] from the event impact assessment; 0 means nothing relevant.
    event_materiality: Decimal = ZERO
    event_refs: tuple[str, ...] = ()

    @property
    def elapsed_ms(self) -> int:
        return max(0, self.now_ms - self.thesis.created_ms)

    @property
    def current_r(self) -> Decimal:
        t = self.thesis
        return t.sign * (self.current_price - t.entry) / t.risk_distance

    @property
    def protection_at_break_even(self) -> bool:
        """True when the stop can no longer give back the original risk."""
        if self.current_stop is None:
            return False
        t = self.thesis
        return (self.current_stop >= t.entry if t.direction is Direction.LONG
                else self.current_stop <= t.entry)

    @property
    def time_fraction(self) -> Optional[Decimal]:
        if self.thesis.expected_horizon_ms <= 0:
            return None
        return Decimal(self.elapsed_ms) / Decimal(self.thesis.expected_horizon_ms)


@dataclass(frozen=True)
class ThesisAssessment:
    """One cycle's verdict on one open position's claim."""

    trade_intent_id: str
    symbol: str
    strategy_id: str
    thesis_seal: str
    state: ThesisState
    reasons: tuple[str, ...]
    #: The facts that drove the state, as strings. This is what the owner reads
    #: and what the gateway surfaces; it is never parsed for behaviour.
    evidence: Mapping[str, Any]
    current_r: Decimal
    health_state: HealthState
    time_in_trade_ms: int
    event_materiality: Decimal
    event_refs: tuple[str, ...]
    assessed_ms: int
    assessment_version: str = ASSESSMENT_VERSION

    @property
    def is_invalidated(self) -> bool:
        return self.state is ThesisState.INVALIDATED

    @property
    def argues_for_less(self) -> bool:
        """States that argue for reducing. None of them can argue for more."""
        return self.state in (
            ThesisState.WEAKER, ThesisState.INVALIDATED,
            ThesisState.RISKIER, ThesisState.OVEREXTENDED,
        )

    def body(self) -> dict[str, Any]:
        return {
            "trade_intent_id": self.trade_intent_id,
            "symbol": self.symbol,
            "strategy_id": self.strategy_id,
            "thesis_seal": self.thesis_seal,
            "state": self.state.value,
            "reasons": list(self.reasons),
            "reason_detail": [THESIS_REASONS[r] for r in self.reasons],
            "evidence": dict(sorted(self.evidence.items())),
            "current_r": str(self.current_r),
            "health_state": self.health_state.value,
            "time_in_trade_ms": self.time_in_trade_ms,
            "event_materiality": str(self.event_materiality),
            "event_refs": list(self.event_refs),
            "argues_for_less": self.argues_for_less,
            "assessed_ms": self.assessed_ms,
            "assessment_version": self.assessment_version,
        }

    @property
    def digest(self) -> str:
        return canonical_hash(self.body())


class ThesisEngine:
    """Seals theses at approval and assesses them per cycle.

    Assessment is pure: the same inputs give the same state and the same
    reasons, on this bar and on replay months later. Ledger writes happen on
    seal and on state change, never on every call.
    """

    def __init__(self, *, ledger=None, producer: str = PRODUCER) -> None:
        self._ledger = ledger
        self._producer = producer
        self._theses: dict[str, TradeThesis] = {}
        self._last_state: dict[str, ThesisState] = {}

    # ------------------------------------------------------------------- seal
    def seal(self, thesis: TradeThesis, *, now_ms: Optional[int] = None) -> TradeThesis:
        """Record the claim. Idempotent on an identical seal."""
        sealed = thesis if thesis.seal else thesis.sealed()
        if not sealed.seal_ok():
            raise ThesisError(f"{sealed.trade_intent_id}: thesis seal does not recompute")
        existing = self._theses.get(sealed.trade_intent_id)
        if existing is not None and existing.seal == sealed.seal:
            return existing
        if existing is not None:
            # A second, different thesis for the same position would let the
            # claim be rewritten once the outcome was visible.
            raise ThesisError(
                f"{sealed.trade_intent_id} already has a sealed thesis; a claim is "
                "made once")
        self._theses[sealed.trade_intent_id] = sealed
        if self._ledger is not None:
            t = now_ms if now_ms is not None else sealed.created_ms
            self._ledger.append(make_event(
                EventKind.TRADE_THESIS, self._producer, sealed.to_dict(),
                event_time_ms=t, received_time_ms=t,
                correlation_id=sealed.trade_intent_id))
        return sealed

    def thesis_for(self, trade_intent_id: str) -> Optional[TradeThesis]:
        return self._theses.get(trade_intent_id)

    def adopt(self, thesis: TradeThesis) -> TradeThesis:
        """Load a thesis recovered from the ledger without re-writing it."""
        self._theses[thesis.trade_intent_id] = thesis
        return thesis

    def forget(self, trade_intent_id: str) -> None:
        self._theses.pop(trade_intent_id, None)
        self._last_state.pop(trade_intent_id, None)

    # ------------------------------------------------------------- assessment
    def assess(self, inp: ThesisInputs, *, persist: bool = True) -> ThesisAssessment:
        t = inp.thesis
        reasons: list[str] = []
        evidence: dict[str, Any] = {
            "current_r": str(inp.current_r),
            "health_state": inp.health.state.value,
            "health_reasons": list(inp.health.reasons),
            "mae_r": str(inp.health.mae_r),
            "mfe_r": str(inp.health.mfe_r),
            "time_in_trade_ms": inp.elapsed_ms,
            "protection_at_break_even": inp.protection_at_break_even,
            "correlation_multiplier": str(inp.correlation_multiplier),
            "event_materiality": str(inp.event_materiality),
        }

        def note(reason: str) -> None:
            if reason not in reasons:
                reasons.append(reason)

        # --- invalidation, in the order the claim declared it -------------
        invalidated = False
        price_level = t.invalidation.get("price")
        if price_level is not None:
            level = dec(price_level)
            evidence["invalidation_price"] = str(level)
            breached = (inp.current_price <= level if t.direction is Direction.LONG
                        else inp.current_price >= level)
            if breached:
                note("INVALIDATION_PRICE")
                invalidated = True
        if t.invalidation.get("structure") and inp.structure_broken:
            note("INVALIDATION_STRUCTURE")
            invalidated = True
        regime_required = t.invalidation.get("regime")
        if regime_required and inp.regime_label and str(regime_required) != inp.regime_label:
            evidence["regime_now"] = inp.regime_label
            evidence["regime_required"] = str(regime_required)
            note("INVALIDATION_REGIME")
            invalidated = True
        deadline = t.invalidation.get("time_ms")
        if deadline is not None and inp.now_ms >= int(deadline) and not inp.confirmations_met:
            note("INVALIDATION_TIME")
            invalidated = True

        # --- terms of the trade ------------------------------------------
        riskier = False
        if t.entry_volatility is not None and inp.volatility is not None and t.entry_volatility > ZERO:
            ratio = inp.volatility / t.entry_volatility
            evidence["volatility_ratio"] = str(ratio)
            if ratio >= VOLATILITY_RISKIER_MULTIPLE:
                note("VOLATILITY_EXPANDED")
                riskier = True
            elif ratio <= VOLATILITY_CALMER_MULTIPLE:
                note("VOLATILITY_CONTRACTED")
        if t.entry_liquidity is not None and inp.liquidity is not None and t.entry_liquidity > ZERO:
            ratio = inp.liquidity / t.entry_liquidity
            evidence["liquidity_ratio"] = str(ratio)
            if ratio <= LIQUIDITY_IMPAIRED_FRACTION:
                note("LIQUIDITY_IMPAIRED")
                riskier = True
        if inp.correlation_multiplier < ONE:
            note("CORRELATION_CROWDED")
            riskier = True
        if inp.event_materiality >= EVENT_MATERIAL:
            note("EVENT_IMPACT")
            riskier = True

        # --- evidence for and against ------------------------------------
        if inp.adverse_present:
            evidence["adverse_present"] = list(inp.adverse_present)
            note("ADVERSE_SIGNAL")
        if inp.confirmations_met:
            evidence["confirmations_met"] = list(inp.confirmations_met)
            note("CONFIRMATION_MET")
        if inp.protection_at_break_even:
            note("PROTECTION_AT_BREAK_EVEN")
        if inp.health.state is not HealthState.HEALTHY:
            note("HEALTH_DEGRADED")

        tf = inp.time_fraction
        past_horizon = tf is not None and tf >= TIME_WEAKENING_FRACTION
        if past_horizon:
            evidence["time_fraction"] = str(tf)
            note("TIME_IN_TRADE")

        expected_r = t.expected_path.get("target_r")
        overextended = False
        if expected_r is not None:
            target = dec(expected_r)
            evidence["expected_target_r"] = str(target)
            if target > ZERO and inp.current_r >= target * OVEREXTENDED_R_MULTIPLE:
                note("MOVE_EXCEEDED_EXPECTATION")
                overextended = True
        if inp.current_r >= ASYMMETRIC_R:
            note("R_MULTIPLE_AHEAD")
        elif inp.current_r <= -ASYMMETRIC_R / Decimal("2"):
            note("R_MULTIPLE_BEHIND")

        # --- state, most decisive first ----------------------------------
        if invalidated or inp.health.state is HealthState.FAILING:
            state = ThesisState.INVALIDATED
        elif overextended:
            state = ThesisState.OVEREXTENDED
        elif riskier:
            # A trade whose terms have worsened is RISKIER even when price is
            # kind: the same claim is being carried on worse conditions.
            state = ThesisState.RISKIER
        elif inp.adverse_present or past_horizon or inp.health.state.rank >= HealthState.WATCH.rank:
            state = ThesisState.WEAKER
        elif inp.protection_at_break_even and inp.current_r >= ASYMMETRIC_R:
            # Bounded downside and a real gain in front: the shape of the trade
            # has changed even though the claim has not. This licenses nothing
            # on its own — `scale_policy.py` still caps any add at the original
            # approved risk (INV-RISK-001).
            state = ThesisState.ASYMMETRIC
        elif inp.confirmations_met:
            state = ThesisState.STRONGER
        else:
            state = ThesisState.INTACT

        assessment = ThesisAssessment(
            trade_intent_id=t.trade_intent_id,
            symbol=t.symbol,
            strategy_id=t.strategy_id,
            thesis_seal=t.seal,
            state=state,
            reasons=_reasons_ok(tuple(reasons)),
            evidence=evidence,
            current_r=inp.current_r,
            health_state=inp.health.state,
            time_in_trade_ms=inp.elapsed_ms,
            event_materiality=inp.event_materiality,
            event_refs=tuple(inp.event_refs),
            assessed_ms=inp.now_ms,
        )

        if persist and self._ledger is not None:
            previous = self._last_state.get(t.trade_intent_id)
            if previous is not state:
                self._ledger.append(make_event(
                    EventKind.THESIS_ASSESSMENT, self._producer,
                    assessment.body() | {
                        "previous_state": None if previous is None else previous.value,
                        "assessment_hash": assessment.digest,
                    },
                    event_time_ms=inp.now_ms, received_time_ms=inp.now_ms,
                    correlation_id=t.trade_intent_id))
        if persist:
            self._last_state[t.trade_intent_id] = state
        return assessment

    def last_state(self, trade_intent_id: str) -> Optional[ThesisState]:
        return self._last_state.get(trade_intent_id)


def thesis_from_capsule(
    *,
    trade_intent_id: str,
    symbol: str,
    strategy_id: str,
    direction: Direction,
    capsule_hash: str,
    market_state_hash: str,
    entry: Decimal,
    original_stop: Decimal,
    original_approved_risk_pct: Decimal,
    created_ms: int,
    capsule_data: Optional[Mapping[str, Any]] = None,
    expected_gross_move_pct: Optional[Decimal] = None,
    targets: tuple[Decimal, ...] = (),
    expected_horizon_ms: int = 0,
    regime_label: str = "",
    entry_volatility: Optional[Decimal] = None,
    entry_liquidity: Optional[Decimal] = None,
    event_sensitivity: tuple[str, ...] = (),
) -> TradeThesis:
    """Build the thesis a capsule and a market state together imply.

    The capsule is allowed to declare its own invalidation, confirmation and
    adverse signals under a `thesis` key. When it does not, the defaults are
    derived from facts the trade already carries — the approved stop is a price
    invalidation, the first target is a confirmation, the horizon is a deadline
    — rather than invented. A thesis with no invalidation condition would be
    unfalsifiable, which is the one thing it must not be.
    """
    data = dict(capsule_data or {})
    declared = dict(data.get("thesis") or {})
    risk_distance = abs(entry - original_stop)

    invalidation: dict[str, Any] = {"price": str(original_stop)}
    if declared.get("invalidation_price") is not None:
        invalidation["price"] = str(dec(declared["invalidation_price"]))
    if declared.get("invalidation_structure"):
        invalidation["structure"] = str(declared["invalidation_structure"])
    if regime_label:
        invalidation["regime"] = regime_label
    if expected_horizon_ms > 0:
        # A time invalidation only fires when nothing has confirmed, so a trade
        # that is working is never closed by the clock alone.
        invalidation["time_ms"] = created_ms + expected_horizon_ms * 2

    confirmation: dict[str, Any] = {}
    if targets:
        confirmation["first_target"] = str(targets[0])
    if risk_distance > ZERO:
        confirmation["progress_r"] = str(ONE)
    for key in ("confirmation", "confirmations"):
        if declared.get(key):
            confirmation["declared"] = list(declared[key])
            break

    expected_path: dict[str, Any] = {}
    if expected_gross_move_pct is not None:
        expected_path["expected_gross_move_pct"] = str(expected_gross_move_pct)
    if targets and risk_distance > ZERO:
        sign = ONE if direction is Direction.LONG else Decimal("-1")
        expected_path["target_r"] = str(sign * (targets[0] - entry) / risk_distance)
    if expected_horizon_ms > 0:
        expected_path["expected_horizon_ms"] = expected_horizon_ms

    statement = str(declared.get("statement") or "").strip()
    if not statement:
        statement = (
            f"{strategy_id} is {direction.value} {symbol} from {entry} with risk to "
            f"{original_stop}"
            + (f", expecting {targets[0]}" if targets else "")
            + (f" under a {regime_label} regime" if regime_label else "")
        )

    return TradeThesis(
        trade_intent_id=trade_intent_id,
        symbol=symbol.upper(),
        strategy_id=strategy_id,
        direction=direction,
        capsule_hash=capsule_hash,
        market_state_hash=market_state_hash,
        statement=statement[:500],
        expected_path=expected_path,
        invalidation=invalidation,
        confirmation=confirmation,
        adverse_signals=tuple(str(x) for x in (declared.get("adverse_signals") or ())),
        event_sensitivity=tuple(event_sensitivity),
        entry=entry,
        original_stop=original_stop,
        original_approved_risk_pct=original_approved_risk_pct,
        expected_horizon_ms=expected_horizon_ms,
        created_ms=created_ms,
        entry_volatility=entry_volatility,
        entry_liquidity=entry_liquidity,
    ).sealed()


__all__ = [
    "ASSESSMENT_VERSION", "THESIS_REASONS", "THESIS_VERSION",
    "ThesisAssessment", "ThesisEngine", "ThesisError", "ThesisInputs",
    "ThesisState", "TradeThesis", "thesis_from_capsule",
]
