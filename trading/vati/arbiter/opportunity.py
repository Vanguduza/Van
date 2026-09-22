"""Opportunity Engine: MarketState → strategies → arbiters → meta-labeller →
sealed TradeIntent. It never sizes; the Risk Authority does."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from vati.arbiter.candidate import CandidateOpportunity, make_candidate_id
from vati.arbiter.confidence import confidence_score
from vati.arbiter.horizon import HorizonArbiter
from vati.arbiter.meta_labeler import MetaLabel, MetaLabeler, MetaVerdict
from vati.arbiter.strategy_arbiter import StrategyArbiter
from vati.core.canonical import canonical_hash
from vati.intelligence.market_state import MarketState
from vati.intelligence.mtf import MultiTimeframeMarketState, TimeframeContract
from vati.intelligence.feature_registry import venue_class_for
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


#: TRD-ENH-033 — how long a candidate stays eligible to become an intent.
#: A stale candidate must expire rather than execute against moved prices.
CANDIDATE_TTL_MS: dict[str, int] = {
    "SCALP": 2 * 60_000,
    "INTRADAY": 15 * 60_000,
    "SESSION": 60 * 60_000,
    "OVERNIGHT": 4 * 3_600_000,
    "SWING": 12 * 3_600_000,
    "POSITION": 24 * 3_600_000,
}
DEFAULT_CANDIDATE_TTL_MS = 15 * 60_000


def capsule_mtf_evidence(
    cap,
    mtf_state: MultiTimeframeMarketState | None,
    *,
    fallback_hash: str,
    fallback_sources: tuple[str, ...],
) -> tuple[bool, str, tuple[str, ...]]:
    """Return whether this capsule's own timeframe contract is complete.

    The instrument-level MTF state may be incomplete because another capsule
    asks for an unrelated timeframe. Only the current capsule's required subset
    is authority for its abstention.
    """
    if mtf_state is None:
        return True, fallback_hash, fallback_sources
    contract = TimeframeContract.from_capsule(cap.data)
    if contract is None:
        return True, fallback_hash or mtf_state.mtf_state_hash, fallback_sources
    missing = tuple(
        tf for tf in contract.required_timeframes
        if tf not in mtf_state.constituent_states
    )
    if missing:
        return False, "", ()
    sources = tuple(
        mtf_state.constituent_states[tf].timeframe_state_hash
        for tf in contract.required_timeframes
    )
    envelope = canonical_hash({
        "strategy_id": cap.strategy_id,
        "required_timeframes": list(contract.required_timeframes),
        "constituents": list(zip(contract.required_timeframes, sources)),
        "fusion_policy_version": mtf_state.fusion_policy_version,
    })
    return True, envelope, sources


class OpportunityEngine:
    def __init__(self, registry: CapsuleRegistry, implementations: dict[str, Strategy], mandate: TradingMandate, *, labeler: MetaLabeler | None = None,
                 lessons=None) -> None:
        self.registry, self.impl, self.mandate = registry, implementations, mandate
        self.h, self.s, self.m = HorizonArbiter(), StrategyArbiter(), labeler or MetaLabeler()
        #: GAP-F-003. A `LessonStore` (learning/episodes.py) whose lessons are
        #: attached to candidates as *evidence strings*. It is read through
        #: `evidence_for`, which returns no number, so retrieval can inform the
        #: owner and the arbiter's reasons without ever becoming a size
        #: multiplier (INV-RISK-001 — no intelligence input may exceed 1, and
        #: this one has no numeric form at all).
        self.lessons = lessons

    def _lesson_evidence(self, strategy_id: str, state: MarketState,
                         regime_label: str) -> tuple[str, ...]:
        if self.lessons is None:
            return ()
        try:
            return tuple(self.lessons.evidence_for(
                strategy_id, regime_label, state.session.value))
        except Exception:  # noqa: BLE001 — evidence retrieval never blocks a decision
            return ()

    def assess_candidates(self, state: MarketState, ctx: StrategyContext, *, regime_label: str,
                          currency_regime_label: str | None = None, account_alias: str, venue: str,
                          mtf_state_hash: str = "", source_state_hashes: tuple[str, ...] = (),
                          mtf_state: MultiTimeframeMarketState | None = None,
                          now_ms: int | None = None) -> tuple[CandidateOpportunity, ...]:
        """Every tradable opportunity for this symbol, as candidates.

        TRD-ENH-031. This is `assess` stopping one step earlier: same arbiters,
        same meta-labeller, same eligibility — but it emits candidates rather
        than a single `TradeIntent`, because the choice between symbols has not
        been made yet and this layer is not the one that makes it.
        """
        now = state.as_of_ms if now_ms is None else now_ms
        out: list[CandidateOpportunity] = []
        for cap in self.registry.all():
            mtf_ok, cap_mtf_hash, cap_source_hashes = capsule_mtf_evidence(
                cap, mtf_state,
                fallback_hash=mtf_state_hash or state.state_hash,
                fallback_sources=source_state_hashes or (state.state_hash,),
            )
            if not mtf_ok:
                continue
            elig = self.s.evaluate(
                cap, state, self.mandate, regime_label=regime_label,
                currency_regime_label=currency_regime_label,
                venue_class=venue_class_for(venue, state.symbol),
                history_bars=getattr(state.features, "history_bars", None),
                context=ctx,
            )
            if not elig.eligible:
                continue
            strat = self.impl.get(cap.strategy_id)
            if strat is None:
                continue
            sig = strat.evaluate(state, ctx)
            if sig is None:
                continue
            hv = self.h.decide(sig.horizon, sig.expected_gross_move_pct, ctx.round_trip_cost_pct, state.quote_age_ms)
            if hv.horizon is None:
                continue
            mv = self.m.score(state, sig, hv.cost_multiple, ctx)
            if mv.label not in (MetaLabel.TRADE, MetaLabel.REDUCE_SIZE):
                continue
            mults = {
                "regime_multiplier": str(mv.regime_multiplier), "volatility_multiplier": str(mv.volatility_multiplier),
                "liquidity_multiplier": str(mv.liquidity_multiplier), "event_risk_multiplier": str(mv.event_risk_multiplier),
                "confidence_multiplier": str(mv.confidence_multiplier),
            }
            conf = confidence_score(mults, capsule_health=self.m.capsule_health.get(cap.strategy_id))
            ttl = CANDIDATE_TTL_MS.get(hv.horizon, DEFAULT_CANDIDATE_TTL_MS)
            out.append(CandidateOpportunity(
                candidate_id=make_candidate_id(account_alias=account_alias, symbol=state.symbol,
                                               strategy_id=cap.strategy_id, state_hash=state.state_hash,
                                               as_of_ms=state.as_of_ms),
                account_alias=account_alias, venue=venue, symbol=state.symbol,
                strategy_id=cap.strategy_id, strategy_version=cap.version,
                capsule_hash=cap.capsule_hash, strategy_state=cap.state.value,
                generated_at_ms=now, valid_from_ms=now, valid_until_ms=now + ttl,
                mtf_state_hash=cap_mtf_hash,
                source_state_hashes=cap_source_hashes,
                feature_contract_hash=elig.feature_contract.verdict_hash if elig.feature_contract else "",
                direction=sig.direction, entry=sig.entry, stop=sig.stop,
                targets=tuple(sig.targets), horizon=hv.horizon,
                expected_gross_move_pct=sig.expected_gross_move_pct,
                cost_multiple=hv.cost_multiple,
                capsule_risk_ceiling=Decimal(str(cap.data.get("risk_limits", {}).get("max_risk_per_trade", "0.005"))),
                confidence_score=conf.score,
                regime_multiplier=mv.regime_multiplier, confidence_multiplier=mv.confidence_multiplier,
                volatility_multiplier=mv.volatility_multiplier, liquidity_multiplier=mv.liquidity_multiplier,
                event_risk_multiplier=mv.event_risk_multiplier,
                holds_over_weekend=sig.holds_over_weekend,
                is_event_certified=cap.event_certified, meta_label=mv.label.value,
                evidence_refs=tuple(mv.reasons) + self._lesson_evidence(
                    cap.strategy_id, state, regime_label),
            ).sealed())
        return tuple(out)

    def assess(self, state: MarketState, ctx: StrategyContext, *, regime_label: str, currency_regime_label: str | None = None,
               account_alias: str, venue: str, idempotency_seed: str) -> OpportunityAssessment:
        cands: list[dict] = []
        best: Optional[tuple[Decimal, Signal, Capsule, MetaVerdict, str]] = None
        for cap in self.registry.all():
            elig = self.s.evaluate(
                cap, state, self.mandate, regime_label=regime_label,
                currency_regime_label=currency_regime_label,
                venue_class=venue_class_for(venue, state.symbol),
                history_bars=getattr(state.features, "history_bars", None),
                context=ctx,
            )
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
            row.update({"label": mv.label.value, "meta_reasons": list(mv.reasons),
                        "lessons": list(self._lesson_evidence(cap.strategy_id, state, regime_label)),
                        "direction": sig.direction.value, "entry": str(sig.entry), "stop": str(sig.stop),
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
