"""Deterministic Risk Authority — the single gate between intent and order.

Rev 2 §27. Evaluation order is fixed and fail-closed. The first failing check
rejects; later checks are not consulted, so a rejection reason always names
the highest-priority cause. No check may be skipped by a caller.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from vati.risk.contracts import (
    Direction,
    KillSwitchTrigger,
    LossModel,
    MarketIntegrityState,
    OpenPosition,
    RiskSnapshot,
    StrategyState,
    TradeIntent,
)
from vati.risk.conformal import ConformalAdmissionGate, ConformalAdmissionRefused
from vati.risk.governor import drawdown_verdict
from vati.risk.heat import currency_leg_exposure, open_stop_risk
from vati.risk.mandate import AuthorizationMode, PlatformCeilings, TradingMandate
from vati.risk.sizing import Multipliers, SizingRejected, size_illiquid_equity, size_stake_contract, size_stop_contract

ZERO = Decimal("0")

#: P0-TRADE-006. Below this the venue itself starts closing positions, so VAN placing a
#: new one would be adding risk to an account already being liquidated.
MARGIN_CALL_LEVEL_PCT = Decimal("100")

#: The level at which VAN stops adding risk of its own accord, well above the venue's.
#: DECISION (recorded, no owner input): 200% is a common broker stop-out buffer and is a
#: starting point rather than a measured optimum. It is here as a named constant so it can
#: be argued with, which is what a hardcoded 1000 could never be.
MARGIN_FLOOR_LEVEL_PCT = Decimal("200")
ONE = Decimal("1")
STRATEGY_STATES_FOR_MODE = {
    AuthorizationMode.DEMO_TRADER: frozenset(
        {StrategyState.DEMO, StrategyState.SHADOW, StrategyState.LIMITED_LIVE, StrategyState.CERTIFIED_LIVE}
    ),
    AuthorizationMode.LIMITED_LIVE: frozenset({StrategyState.LIMITED_LIVE, StrategyState.CERTIFIED_LIVE}),
    AuthorizationMode.AUTONOMOUS_LIVE: frozenset({StrategyState.CERTIFIED_LIVE}),
}


class Decision(str, Enum):
    APPROVED = "APPROVED"
    REDUCED = "REDUCED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class RiskDecision:
    trade_intent_id: str
    decision: Decision
    reason_code: str
    reason_detail: str
    approved_size: Decimal
    approved_risk_pct: Decimal
    requested_risk_pct: Decimal
    portfolio_heat_before: Decimal
    portfolio_heat_after: Decimal
    constraints: tuple[str, ...]
    risk_policy_version: str
    mandate_id: str
    mandate_version: str
    risk_snapshot_hash: str
    decision_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for k, v in list(d.items()):
            if isinstance(v, Decimal):
                d[k] = str(v)
            elif isinstance(v, Enum):
                d[k] = v.value
        return d


def _canonical_hash(obj: Any) -> str:
    def default(o: Any) -> Any:
        if isinstance(o, Decimal):
            return str(o)
        if isinstance(o, Enum):
            return o.value
        if isinstance(o, (set, frozenset)):
            return sorted(str(x) for x in o)
        if hasattr(o, "__dataclass_fields__"):
            return asdict(o)
        raise TypeError(f"unhashable: {type(o)}")

    payload = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=default)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class RiskAuthority:
    def __init__(self, mandate: TradingMandate, *,
                 ceilings: PlatformCeilings = PlatformCeilings(),
                 conformal_gate: Optional[ConformalAdmissionGate] = None) -> None:
        mandate.validate(ceilings)
        self.mandate = mandate
        self.ceilings = ceilings
        self.conformal_gate = conformal_gate
        self._seen_keys: set[str] = set()

    # ----------------------------------------------------------------- helpers
    def _reject(self, intent: TradeIntent, snap_hash: str, heat_before: Decimal, code: str, detail: str) -> RiskDecision:
        d = RiskDecision(
            trade_intent_id=intent.trade_intent_id,
            decision=Decision.REJECTED,
            reason_code=code,
            reason_detail=detail,
            approved_size=ZERO,
            approved_risk_pct=ZERO,
            requested_risk_pct=intent.requested_risk_pct,
            portfolio_heat_before=heat_before,
            portfolio_heat_after=heat_before,
            constraints=(code,),
            risk_policy_version=self.ceilings.policy_version,
            mandate_id=self.mandate.mandate_id,
            mandate_version=self.mandate.version,
            risk_snapshot_hash=snap_hash,
        )
        return self._seal(d)

    @staticmethod
    def _seal(d: RiskDecision) -> RiskDecision:
        body = d.to_dict()
        body.pop("decision_hash", None)
        return RiskDecision(**{**asdict(d), "decision_hash": _canonical_hash(body)})

    # ------------------------------------------------------------ safe wrapper
    def evaluate_safe(self, intent: TradeIntent, snapshot: RiskSnapshot) -> RiskDecision:
        """The execution router calls this, never `evaluate` directly. Any
        unexpected exception inside the authority is a rejection, not a crash,
        so the ledger always receives a sealed decision (Rev 2 §59 Fail Closed)."""
        try:
            return self.evaluate(intent, snapshot)
        except Exception as exc:  # noqa: BLE001 — every fault is fail-closed
            return self._reject(intent, "0" * 64, Decimal("1"), "AUTHORITY_FAULT", f"{type(exc).__name__}: {exc}"[:200])

    # ---------------------------------------------------------------- evaluate
    def evaluate(self, intent: TradeIntent, snapshot: RiskSnapshot) -> RiskDecision:
        m = self.mandate
        snap_hash = _canonical_hash(snapshot)
        heat_before = open_stop_risk(snapshot.open_positions, snapshot.equity)
        heat_before_out = heat_before if heat_before.is_finite() else Decimal("1")
        rej = lambda code, detail: self._reject(intent, snap_hash, heat_before_out, code, detail)  # noqa: E731

        # 1. Kill switch
        if snapshot.kill_switch_triggers:
            return rej("KILL_SWITCH", ",".join(sorted(t.value for t in snapshot.kill_switch_triggers)))

        # 2. Account identity
        if not snapshot.account_verified:
            return rej("ACCOUNT_UNVERIFIED", "broker account state could not be verified")
        if snapshot.account_alias != m.account_alias or intent.account_alias != m.account_alias:
            return rej("ACCOUNT_MISMATCH", f"mandate={m.account_alias} snapshot={snapshot.account_alias} intent={intent.account_alias}")
        if intent.venue != m.venue or snapshot.symbol_contract.venue != m.venue:
            return rej("VENUE_MISMATCH", f"mandate venue {m.venue}")

        # 3. Mandate validity & mode
        if m.is_expired(snapshot.now_unix):
            return rej("MANDATE_EXPIRED", f"expired at {m.expires_at_unix}")
        if not m.sends_orders():
            return rej("MODE_NOT_ORDER_SENDING", m.mode.value)
        if intent.owner_authority != "MANDATE":
            return rej("AUTHORITY_UNKNOWN", intent.owner_authority)

        # 4. Duplicate intent
        if intent.idempotency_key in self._seen_keys:
            return rej("DUPLICATE_INTENT", intent.idempotency_key)

        # 5. Platform health — every flag must be affirmatively true
        if not snapshot.data_fresh:
            return rej("STALE_DATA", f"quote age {snapshot.quote_age_ms}ms > {snapshot.max_quote_age_ms}ms")
        if not snapshot.broker_connected:
            return rej("VENUE_DISCONNECTED", "broker session not connected")
        if not snapshot.reconciliation_ok:
            return rej("RECONCILIATION_FAILED", "ledger and broker state disagree")
        if not snapshot.clock_sync_ok:
            return rej("TIME_SYNC_FAULT", "clock not synchronised")
        if not snapshot.risk_store_ok:
            return rej("RISK_STORE_UNAVAILABLE", "risk state store unavailable")
        if snapshot.market_integrity in (MarketIntegrityState.ABNORMAL, MarketIntegrityState.HALTED):
            return rej("MARKET_INTEGRITY", snapshot.market_integrity.value)
        if not heat_before.is_finite():
            return rej("UNPROTECTED_POSITION", "an open position lacks a broker-side stop; no new risk until restored")

        # 5b. Broker margin (P0-TRADE-006). There was no margin model anywhere in the
        # stack, so the authority sized by stop distance with no visibility of what the
        # broker would actually allow — a position correctly sized for risk can still be
        # refused, or can put the account into a margin call, and VAN could see neither.
        #
        # None means the venue did not report it. That is treated as unknown rather than
        # healthy, and unknown is only acceptable where there is genuinely no margin to
        # report: a paper account, or a venue VAN does not place orders on.
        if snapshot.margin_level_pct is not None:
            if snapshot.margin_level_pct <= MARGIN_CALL_LEVEL_PCT:
                return rej(
                    "MARGIN_CALL",
                    f"margin level {snapshot.margin_level_pct}% at or below "
                    f"{MARGIN_CALL_LEVEL_PCT}%; the venue is closing positions",
                )
            if snapshot.margin_level_pct <= MARGIN_FLOOR_LEVEL_PCT:
                return rej(
                    "MARGIN_FLOOR",
                    f"margin level {snapshot.margin_level_pct}% at or below the "
                    f"{MARGIN_FLOOR_LEVEL_PCT}% floor; no new risk until it recovers",
                )
        if snapshot.free_margin is not None and snapshot.free_margin <= ZERO:
            return rej("NO_FREE_MARGIN", "the account has no free margin for a new position")

        # 6. Instrument / strategy eligibility
        contract = snapshot.symbol_contract
        symbol = intent.symbol.upper()
        if symbol not in m.instruments or contract.symbol.upper() != symbol:
            return rej("INSTRUMENT_NOT_MANDATED", symbol)
        if intent.strategy_id not in m.allowed_strategies:
            return rej("STRATEGY_NOT_MANDATED", intent.strategy_id)
        if intent.strategy_state not in STRATEGY_STATES_FOR_MODE[m.mode]:
            return rej("STRATEGY_STATE_INELIGIBLE", f"{intent.strategy_state.value} in mode {m.mode.value}")
        if not contract.allows(intent.direction):
            return rej("SYMBOL_TRADE_MODE", f"{contract.trade_mode} forbids {intent.direction.value}")

        # 7. Event and holding-period policy
        if snapshot.tier1_event_blackout_active:
            if m.tier1_event_policy == "flat" or not intent.is_event_certified:
                return rej("EVENT_BLACKOUT", "tier-1 event window; strategy not event-certified")
        if intent.holds_over_weekend and not m.weekend_hold_allowed:
            return rej("WEEKEND_HOLD_FORBIDDEN", "mandate forbids weekend holds")

        # 8. Loss limits and drawdown governor
        if snapshot.consecutive_losses >= m.max_consecutive_losses:
            return rej("CONSECUTIVE_LOSSES", f"{snapshot.consecutive_losses} >= {m.max_consecutive_losses}")
        if snapshot.day_start_equity > ZERO:
            day_loss = (snapshot.day_start_equity - snapshot.equity) / snapshot.day_start_equity
            if day_loss >= m.max_daily_loss:
                return rej("MAX_DAILY_LOSS", f"{day_loss}")
        else:
            return rej("EQUITY_BASELINE_MISSING", "day_start_equity unknown")
        if snapshot.week_start_equity > ZERO:
            week_dd = (snapshot.week_start_equity - snapshot.equity) / snapshot.week_start_equity
            if week_dd >= m.max_weekly_drawdown:
                return rej("MAX_WEEKLY_DRAWDOWN", f"{week_dd}")
        else:
            return rej("EQUITY_BASELINE_MISSING", "week_start_equity unknown")
        dd = drawdown_verdict(snapshot.peak_equity, snapshot.equity, m.drawdown_tiers)
        if dd.suspended:
            return rej("DRAWDOWN_SUSPENDED", f"drawdown {dd.drawdown}")
        if dd.top_tier_only and intent.strategy_state is not StrategyState.CERTIFIED_LIVE:
            return rej("DRAWDOWN_TOP_TIER_ONLY", f"drawdown {dd.drawdown}")

        # 9. Position count limits
        same_symbol = sum(1 for p in snapshot.open_positions if p.symbol.upper() == symbol)
        if same_symbol >= m.max_positions_per_instrument:
            return rej("MAX_POSITIONS_PER_INSTRUMENT", f"{same_symbol}")
        if len(snapshot.open_positions) >= m.max_total_positions:
            return rej("MAX_TOTAL_POSITIONS", f"{len(snapshot.open_positions)}")

        # 10. Allowed risk: min(requested, mandate) — never above either
        constraints: list[str] = []
        allowed_risk = intent.requested_risk_pct
        if allowed_risk <= ZERO:
            return rej("RISK_NON_POSITIVE", str(allowed_risk))
        if allowed_risk > m.max_risk_per_trade:
            allowed_risk = m.max_risk_per_trade
            constraints.append("RISK_CLAMPED_TO_MANDATE")
        liquidity = intent.liquidity_multiplier
        if snapshot.market_integrity is MarketIntegrityState.ELEVATED:
            liquidity = min(Decimal("0.5"), liquidity)
            constraints.append("MARKET_ELEVATED_HALF_SIZE")
        mult = Multipliers(
            regime=intent.regime_multiplier,
            confidence=intent.confidence_multiplier,
            volatility=intent.volatility_multiplier,
            liquidity=liquidity,
            event_risk=intent.event_risk_multiplier,
            correlation=intent.correlation_multiplier,
            drawdown=dd.multiplier,
        )
        if dd.tier_index >= 0:
            constraints.append(f"DRAWDOWN_TIER_{dd.tier_index}")

        # 10b. Edge must clear round-trip cost (Rev 3: cost is the first edge)
        if intent.expected_gross_move_pct is not None and contract.round_trip_cost_pct > ZERO:
            if intent.expected_gross_move_pct < contract.round_trip_cost_pct * Decimal("2"):
                return rej("EDGE_BELOW_COST", f"expected move {intent.expected_gross_move_pct} < 2 × round-trip cost {contract.round_trip_cost_pct}")

        # 10c. Optional conformal admission. Only strategies explicitly registered
        # in the conformal gate are affected. The gate can reject uncertainty; it
        # cannot size or increase risk (TRD-REV51-117 / INV-AUTH-001).
        if self.conformal_gate is not None:
            try:
                self.conformal_gate.check(intent, snapshot)
            except ConformalAdmissionRefused as exc:
                return rej(exc.code, exc.detail)

        # 11. Sizing
        try:
            if contract.loss_model is LossModel.ILLIQUID_EQUITY:
                if intent.stop is None:
                    return rej("STOP_REQUIRED", "illiquid equity requires a software stop level")
                if intent.direction is not Direction.LONG:
                    return rej("SYMBOL_TRADE_MODE", "illiquid equity is long-only (no short selling on ZSE/VFEX)")
                sized = size_illiquid_equity(
                    equity=snapshot.equity,
                    allowed_risk_pct=allowed_risk,
                    entry=intent.entry,
                    stop=intent.stop,
                    contract=contract,
                    multipliers=mult,
                )
            elif contract.loss_model is LossModel.FULL_STAKE:
                sized = size_stake_contract(
                    equity=snapshot.equity,
                    allowed_risk_pct=allowed_risk,
                    requested_stake=intent.stake,
                    contract=contract,
                    multipliers=mult,
                )
            else:
                if intent.stop is None:
                    return rej("STOP_REQUIRED", "stop-distance contracts require a protective stop")
                sized = size_stop_contract(
                    equity=snapshot.equity,
                    allowed_risk_pct=allowed_risk,
                    entry=intent.entry,
                    stop=intent.stop,
                    direction=intent.direction,
                    contract=contract,
                    multipliers=mult,
                )
        except SizingRejected as exc:
            return rej(exc.code, exc.detail)

        # 12. Portfolio heat and currency legs *after* the trade
        if contract.loss_model is LossModel.FULL_STAKE:
            new_pos = OpenPosition(symbol, intent.direction, ZERO, ZERO, ZERO, contract.base_currency,
                                   contract.quote_currency, intent.strategy_id, True, LossModel.FULL_STAKE, sized.size)
        elif contract.loss_model is LossModel.ILLIQUID_EQUITY:
            new_pos = OpenPosition(symbol, intent.direction, sized.size, intent.entry - intent.stop,  # type: ignore[operator]
                                   Decimal("1"), contract.base_currency, contract.quote_currency, intent.strategy_id,
                                   False, LossModel.ILLIQUID_EQUITY, ZERO, intent.entry * contract.liquidity_haircut)
        else:
            new_pos = OpenPosition(symbol, intent.direction, sized.size, abs(intent.entry - intent.stop),  # type: ignore[arg-type]
                                   contract.value_per_price_unit_per_lot, contract.base_currency,
                                   contract.quote_currency, intent.strategy_id, True)
        after = snapshot.open_positions + (new_pos,)
        heat_after = open_stop_risk(after, snapshot.equity)
        if heat_after > m.max_open_stop_risk:
            return rej("PORTFOLIO_HEAT", f"heat after {heat_after} > {m.max_open_stop_risk}")
        legs = currency_leg_exposure(after, snapshot.equity)
        hot = {c: v for c, v in legs.items() if v > m.max_currency_leg_exposure}
        if hot:
            return rej("CURRENCY_LEG_EXPOSURE", ",".join(f"{c}={v}" for c, v in sorted(hot.items())))

        # 13. Final invariant re-check (the contract, restated)
        if sized.risk_pct > m.max_risk_per_trade or sized.risk_pct > intent.requested_risk_pct:
            return rej("RISK_INVARIANT", f"{sized.risk_pct}")

        decision = Decision.APPROVED
        if constraints or sized.multiplier_product < ONE:
            decision = Decision.REDUCED
        self._seen_keys.add(intent.idempotency_key)
        d = RiskDecision(
            trade_intent_id=intent.trade_intent_id,
            decision=decision,
            reason_code="OK",
            reason_detail="",
            approved_size=sized.size,
            approved_risk_pct=sized.risk_pct,
            requested_risk_pct=intent.requested_risk_pct,
            portfolio_heat_before=heat_before_out,
            portfolio_heat_after=heat_after,
            constraints=tuple(constraints),
            risk_policy_version=self.ceilings.policy_version,
            mandate_id=m.mandate_id,
            mandate_version=m.version,
            risk_snapshot_hash=snap_hash,
        )
        return self._seal(d)
