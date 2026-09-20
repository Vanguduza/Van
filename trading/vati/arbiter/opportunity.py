"""Opportunity Engine: MarketState → strategies → arbiters → meta-labeller →
sealed TradeIntent. It never sizes; the Risk Authority does."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from vati.arbiter.confidence import confidence_score
from vati.arbiter.horizon import HorizonArbiter
from vati.arbiter.meta_labeler import MetaLabel, MetaLabeler, MetaVerdict
from vati.arbiter.strategy_arbiter import StrategyArbiter
from vati.core.canonical import canonical_hash
from vati.intelligence.market_state import MarketState
from vati.risk.contracts import TradeIntent
from vati.risk.mandate import TradingMandate
from vati.strategies.base import Signal, Strategy, StrategyContext
from vati.strategies.capsule import Capsule, CapsuleRegistry


@dataclass(frozen=True)
class OpportunityAssessment:
    symbol: str
    as_of_ms: int
    activation_id: str
    state_hash: str
    candidates: tuple[dict, ...]
    decision: str                      # TRADE | REDUCE_SIZE | WAIT | SKIP | NO_TRADE
    abstain_reason: str
    intent: Optional[TradeIntent]
    #: P1-TRADE-007 — the winning signal's own targets. The decision cycle used to throw
    #: these away and re-derive a single target from expected_gross_move_pct, so a strategy
    #: with a scaled exit plan had it silently replaced by one price.
    targets: tuple[Decimal, ...] = ()
    assessment_hash: str = ""


class OpportunityEngine:
    def __init__(self, registry: CapsuleRegistry, implementations: dict[str, Strategy], mandate: TradingMandate, *, labeler: MetaLabeler | None = None) -> None:
        self.registry, self.impl, self.mandate = registry, implementations, mandate
        self.h, self.s, self.m = HorizonArbiter(), StrategyArbiter(), labeler or MetaLabeler()

    def assess(self, state: MarketState, ctx: StrategyContext, *, regime_label: str, currency_regime_label: str | None = None,
               account_alias: str, venue: str, idempotency_seed: str) -> OpportunityAssessment:
        cands: list[dict] = []
        best: Optional[tuple[Decimal, Signal, Capsule, MetaVerdict, str]] = None
        for cap in self.registry.all():
            elig = self.s.evaluate(cap, state, self.mandate, regime_label=regime_label, currency_regime_label=currency_regime_label, context=ctx)
            row = {"strategy_id": cap.strategy_id, "eligible": elig.eligible, "reasons": list(elig.reasons)}
            if not elig.eligible:
                cands.append(row); continue
            strat = self.impl.get(cap.strategy_id)
            if strat is None:
                row["reasons"] = ["no implementation bound"]; cands.append(row); continue
            sig = strat.evaluate(state, ctx)
            if sig is None:
                row["reasons"] = ["no signal"]; cands.append(row); continue
            hv = self.h.decide(sig.horizon, sig.expected_gross_move_pct, ctx.round_trip_cost_pct, state.quote_age_ms)
            row.update({"signal": sig.rationale, "horizon": hv.horizon, "cost_multiple": str(hv.cost_multiple)})
            if hv.horizon is None:
                row["reasons"] = [hv.reason]; cands.append(row); continue
            mv = self.m.score(state, sig, hv.cost_multiple, ctx)
            mults = {"regime_multiplier": str(mv.regime_multiplier), "volatility_multiplier": str(mv.volatility_multiplier), "liquidity_multiplier": str(mv.liquidity_multiplier),
                     "event_risk_multiplier": str(mv.event_risk_multiplier), "confidence_multiplier": str(mv.confidence_multiplier)}
            conf = confidence_score(mults, capsule_health=self.m.capsule_health.get(cap.strategy_id))
            row.update({"label": mv.label.value, "meta_reasons": list(mv.reasons), "direction": sig.direction.value, "entry": str(sig.entry), "stop": str(sig.stop),
                        "expected_gross_move_pct": str(sig.expected_gross_move_pct) if sig.expected_gross_move_pct is not None else None,
                        "multipliers": mults, "confidence": conf.as_dict()})
            cands.append(row)
            if mv.label in (MetaLabel.TRADE, MetaLabel.REDUCE_SIZE):
                score = hv.cost_multiple * mv.confidence_multiplier * mv.regime_multiplier
                if best is None or score > best[0]:
                    best = (score, sig, cap, mv, hv.horizon)
        if best is None:
            waits = [c for c in cands if c.get("label") in ("WAIT", "REQUIRE_CONFIRMATION")]
            decision = "WAIT" if waits else "NO_TRADE"
            reason = "; ".join(f"{c['strategy_id']}: {', '.join(c['reasons'] or c.get('meta_reasons', []))}" for c in cands) or "no capsules"
            oa = OpportunityAssessment(state.symbol, state.as_of_ms, state.activation_id, state.state_hash, tuple(cands), decision, reason, None)
            return OpportunityAssessment(**{**oa.__dict__, "assessment_hash": canonical_hash({k: v for k, v in oa.__dict__.items() if k != "assessment_hash"})})
        _, sig, cap, mv, horizon = best
        decision_body = {"state_hash": state.state_hash, "strategy_id": cap.strategy_id, "capsule_hash": cap.capsule_hash, "signal": sig.__dict__, "meta": mv.__dict__, "horizon": horizon}
        decision_hash = canonical_hash(decision_body)
        intent = TradeIntent(
            trade_intent_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"vati:{decision_hash}")),
            idempotency_key=canonical_hash({"seed": idempotency_seed, "decision": decision_hash})[:32],
            account_alias=account_alias, venue=venue, symbol=sig.symbol, direction=sig.direction, strategy_id=cap.strategy_id, strategy_version=cap.version,
            strategy_state=cap.state, entry=sig.entry, stop=sig.stop, requested_risk_pct=Decimal(str(cap.data["risk_limits"].get("max_risk_per_trade", "0.005"))),
            decision_hash=decision_hash, market_snapshot_hash=state.state_hash, owner_authority="MANDATE", is_event_certified=cap.event_certified,
            holds_over_weekend=sig.holds_over_weekend, stake=sig.stake, expected_gross_move_pct=sig.expected_gross_move_pct,
            regime_multiplier=mv.regime_multiplier, confidence_multiplier=mv.confidence_multiplier, volatility_multiplier=mv.volatility_multiplier,
            liquidity_multiplier=mv.liquidity_multiplier, event_risk_multiplier=mv.event_risk_multiplier,
        )
        oa = OpportunityAssessment(state.symbol, state.as_of_ms, state.activation_id, state.state_hash, tuple(cands), mv.label.value, "", intent, targets=tuple(sig.targets))
        return OpportunityAssessment(**{**oa.__dict__, "assessment_hash": canonical_hash({k: (v.__dict__ if k == "intent" else v) for k, v in oa.__dict__.items() if k != "assessment_hash"})})
