"""Deterministic Risk Authority — the single gate between intent and order.

Rev 2 §27. Evaluation order is fixed and fail-closed. The first failing check
rejects; later checks are not consulted, so a rejection reason always names
the highest-priority cause. No check may be skipped by a caller.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, fields
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
    SymbolContract,
    TradeIntent,
)
from vati.risk.conformal import ConformalAdmissionGate, ConformalAdmissionRefused
from vati.risk.governor import drawdown_verdict
from vati.risk.lockouts import at_or_above
from vati.risk.heat import currency_leg_exposure, open_stop_risk, exact_open_stop_risk, exact_currency_leg_exposure
from vati.risk.arithmetic import fraction, decimal, exact_loss_amount
from vati.risk.serde import intent_binding_hash, mandate_binding_hash, RISK_APPROVAL_SCHEMA_VERSION
from vati.risk.mandate import AuthorizationMode, PlatformCeilings, TradingMandate
from vati.risk.sizing import Multipliers, SizingRejected, size_illiquid_equity, size_stake_contract, size_stop_contract
from vati.core.decimal_context import native_financial_arithmetic

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

# Native producers must publish an explicit boolean, never a truthy string,
# integer, missing value or generic container. Derive the field lists from
# the declared contracts so a new boolean fact cannot silently skip this gate.
BOOLEAN_FACT_FIELDS = {
    cls: tuple(f.name for f in fields(cls) if f.type in (bool, 'bool'))
    for cls in (RiskSnapshot,TradeIntent,SymbolContract,OpenPosition)
}


def invalid_boolean_fact(intent, snapshot):
    records=[('snapshot',snapshot,RiskSnapshot),('intent',intent,TradeIntent),
             ('contract',snapshot.symbol_contract,SymbolContract)]
    records.extend((f'open_positions[{index}]',position,OpenPosition)
                   for index,position in enumerate(snapshot.open_positions))
    for scope,record,contract in records:
        for name in BOOLEAN_FACT_FIELDS[contract]:
            if type(getattr(record,name)) is not bool:
                return f'{scope}.{name} requires an explicit boolean source fact'
    return None


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
    intent_hash: Optional[str] = None
    mandate_hash: Optional[str] = None
    approval_schema_version: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Historical v1 bodies remain byte-equivalent when decoded. They are
        # readable evidence, but cannot authorize a new broker submission.
        for key in ("intent_hash", "mandate_hash", "approval_schema_version"):
            if d[key] is None:
                d.pop(key)
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
            result = asdict(o)
            if isinstance(o, RiskSnapshot) and o.used_margin is None:
                result.pop("used_margin")  # original snapshot identities remain reproducible
            return result
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
            intent_hash=intent_binding_hash(intent),
            mandate_hash=mandate_binding_hash(self.mandate),
            approval_schema_version=RISK_APPROVAL_SCHEMA_VERSION,
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
    @native_financial_arithmetic
    def evaluate(self, intent: TradeIntent, snapshot: RiskSnapshot) -> RiskDecision:
        m = self.mandate
        snap_hash = _canonical_hash(snapshot)
        heat_before = open_stop_risk(snapshot.open_positions, snapshot.equity)
        heat_before_out = heat_before if heat_before.is_finite() else Decimal("1")
        rej = lambda code, detail: self._reject(intent, snap_hash, heat_before_out, code, detail)  # noqa: E731

        # 1. Kill switch
        if snapshot.kill_switch_triggers:
            return rej("KILL_SWITCH", ",".join(sorted(t.value for t in snapshot.kill_switch_triggers)))

        invalid_fact=invalid_boolean_fact(intent,snapshot)
        if invalid_fact:
            return rej('INVALID_BOOLEAN_FACT',invalid_fact)

        if not m.authority_matches_policy():
            return rej('MANDATE_AUTHORITY_MISMATCH','current effective policy lacks its original owner grant; re-admission required')

        if not m.owner_keys_current():
            return rej('MANDATE_SIGNER_UNAVAILABLE','current owner signer is not registered or changed; re-admission required')

        # 1b. Post-entry preservation has precedence over new risk. The
        # lifecycle may describe why, but only RiskAuthority turns that fact
        # into a refusal (INV-AUTH-001).
        if snapshot.preservation_blocks_new_risk:
            return rej(
                "PRESERVATION_BLOCK",
                snapshot.preservation_reason or "open-family preservation blocks new risk",
            )

        # 2. Account identity
        if not snapshot.account_verified:
            return rej("ACCOUNT_UNVERIFIED", "broker account state could not be verified")
        if snapshot.account_alias != m.account_alias or intent.account_alias != m.account_alias:
            return rej("ACCOUNT_MISMATCH", f"mandate={m.account_alias} snapshot={snapshot.account_alias} intent={intent.account_alias}")
        if intent.venue != m.venue or snapshot.symbol_contract.venue != m.venue:
            return rej("VENUE_MISMATCH", f"mandate venue {m.venue}")

        # 3. Mandate validity & mode
        if snapshot.now_unix < m.signed_at_unix:
            return rej('MANDATE_NOT_YET_VALID',f'valid from {m.signed_at_unix}')
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
        native_margin = (snapshot.symbol_contract.loss_model is LossModel.STOP_DISTANCE
                         and intent.venue != "paper")
        amounts = (snapshot.used_margin, snapshot.free_margin, snapshot.margin_level_pct)
        if any(value is not None and (type(value) is not Decimal or not value.is_finite()) for value in amounts):
            return rej("MARGIN_INVALID", "margin facts require original finite decimal amounts")
        if snapshot.used_margin is not None and snapshot.used_margin < ZERO:
            return rej("MARGIN_INVALID", "native committed margin cannot be negative")
        if native_margin and (snapshot.used_margin is None or snapshot.free_margin is None
                              or snapshot.used_margin > ZERO and snapshot.margin_level_pct is None):
            return rej("MARGIN_UNKNOWN", "native committed/free margin or applicable margin level unavailable")
        # Credit/bonuses excluded from risk equity cannot restore margin capacity.
        # These are conservative risk bounds, never newly reported broker money.
        from vati.risk.margin import cash_margin_bounds
        free,level=cash_margin_bounds(snapshot.equity,snapshot.used_margin,snapshot.free_margin,snapshot.margin_level_pct)
        if snapshot.used_margin == ZERO and snapshot.margin_level_pct is not None:
            return rej("MARGIN_INVALID", "zero committed margin has no defined equity/margin ratio")
        if level is not None:
            if level <= MARGIN_CALL_LEVEL_PCT:
                return rej("MARGIN_CALL", f"risk margin level {level}% at or below {MARGIN_CALL_LEVEL_PCT}%")
            if level <= MARGIN_FLOOR_LEVEL_PCT:
                return rej("MARGIN_FLOOR", f"risk margin level {level}% at or below {MARGIN_FLOOR_LEVEL_PCT}%")
        if free is not None and free <= ZERO:
            return rej("NO_FREE_MARGIN", "the account has no cash-backed free margin for a new position")

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
        if snapshot.loss_streak_lock:
            # P1-TRADE-RISK-005: a cooldown or an owner-reset suspension, not a permanent lock.
            return rej("CONSECUTIVE_LOSSES", snapshot.loss_streak_lock)
        if snapshot.day_start_equity > ZERO:
            day_loss = (fraction(snapshot.day_start_equity) - fraction(snapshot.equity)) / fraction(snapshot.day_start_equity)
            if day_loss >= m.max_daily_loss:
                return rej("MAX_DAILY_LOSS", f"{decimal(day_loss)}")
        else:
            return rej("EQUITY_BASELINE_MISSING", "day_start_equity unknown")
        if snapshot.week_start_equity > ZERO:
            week_dd = (fraction(snapshot.week_start_equity) - fraction(snapshot.equity)) / fraction(snapshot.week_start_equity)
            if week_dd >= m.max_weekly_drawdown:
                return rej("MAX_WEEKLY_DRAWDOWN", f"{decimal(week_dd)}")
        else:
            return rej("EQUITY_BASELINE_MISSING", "week_start_equity unknown")
        dd = drawdown_verdict(snapshot.peak_equity, snapshot.equity, m.drawdown_tiers)
        if dd.suspended:
            return rej("DRAWDOWN_SUSPENDED", f"drawdown {dd.drawdown}")
        # P1-TRADE-RISK-005: "top tier" is the highest promotion state the mandate's
        # strategies actually hold, so a restricted account keeps trading its best-proven
        # strategies at the tier's reduced size and can recover. Legacy floor when unset.
        top_floor = snapshot.drawdown_top_state or StrategyState.CERTIFIED_LIVE
        if dd.top_tier_only and not at_or_above(intent.strategy_state, top_floor):
            return rej("DRAWDOWN_TOP_TIER_ONLY", f"drawdown {dd.drawdown}; trading limited to {top_floor.value}")

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
            drawdown=decimal(fraction(dd.multiplier) * fraction(min(ONE, max(ZERO, snapshot.loss_streak_multiplier)))),
        )
        if dd.tier_index >= 0:
            constraints.append(f"DRAWDOWN_TIER_{dd.tier_index}")
        if snapshot.loss_streak_multiplier < ONE:
            constraints.append("LOSS_STREAK_PROBATION")

        # 10b. Edge must clear round-trip cost (Rev 3: cost is the first edge)
        if intent.expected_gross_move_pct is not None and contract.round_trip_cost_pct > ZERO:
            if fraction(intent.expected_gross_move_pct) < fraction(contract.round_trip_cost_pct) * 2:
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
        new_loss = exact_loss_amount(sized.size, contract, entry=intent.entry, stop=intent.stop)
        # Reporting ratios may repeat. Compare unrounded source arithmetic to
        # the signed ceiling; even a tiny positive excess must still refuse.
        heat_after = exact_open_stop_risk(snapshot.open_positions, snapshot.equity, additional_loss=new_loss)
        if heat_after > m.max_open_stop_risk:
            return rej("PORTFOLIO_HEAT", f"entry would exceed portfolio risk limit {m.max_open_stop_risk}; reported heat {decimal(heat_after)}")
        legs = exact_currency_leg_exposure(snapshot.open_positions, snapshot.equity,
            additional_loss=new_loss, base_currency=contract.base_currency,
            quote_currency=contract.quote_currency, direction=intent.direction)
        hot = {c: v for c, v in legs.items() if v > m.max_currency_leg_exposure}
        if hot:
            return rej("CURRENCY_LEG_EXPOSURE", ",".join(f"{c}={decimal(v)}" for c, v in sorted(hot.items())))

        # 13. Final invariant re-check (the contract, restated)
        exact_risk_pct = new_loss / fraction(snapshot.equity)
        if exact_risk_pct > m.max_risk_per_trade or exact_risk_pct > intent.requested_risk_pct:
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
            portfolio_heat_after=decimal(heat_after),
            constraints=tuple(constraints),
            risk_policy_version=self.ceilings.policy_version,
            mandate_id=m.mandate_id,
            mandate_version=m.version,
            risk_snapshot_hash=snap_hash,
            intent_hash=intent_binding_hash(intent),
            mandate_hash=mandate_binding_hash(m),
            approval_schema_version=RISK_APPROVAL_SCHEMA_VERSION,
        )
        return self._seal(d)
