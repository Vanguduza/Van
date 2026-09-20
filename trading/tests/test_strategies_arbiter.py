from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from conftest import mandate_dict, passing_certificate, snapshot
from test_intelligence import mk_bars, noisy_trend, pullback_fixture, ranging, trending
from vati.arbiter import HorizonArbiter, MetaLabel, MetaLabeler, OpportunityEngine, StrategyArbiter
from vati.intelligence import DEFAULT_EVENT_MATRIX, EventMatrix, RegimeEngine, Tier1Event, build_market_state
from vati.market_data import FX_CALENDAR
from vati.risk import Decision, Direction, LossModel, RiskAuthority, StrategyState, SymbolContract, TradingMandate
from vati.risk.contracts import MarketIntegrityState
from vati.strategies import STRATEGY_IMPLEMENTATIONS, Capsule, CapsuleError, CapsuleRegistry, EventDrift, FxTrendPullback, StrategyContext, ZseLiquidityProvision, ZseSnapshot, ZseValueRotation
from vati.zse.currency import CurrencyRegime

REG = Path(__file__).resolve().parents[1] / "strategies" / "registry"


def state_for(closes, *, now_offset_ms=0, events=DEFAULT_EVENT_MATRIX, engine=None):
    bars = mk_bars(closes)
    eng = engine or RegimeEngine()
    for i in range(60, len(closes)):
        eng.update(__import__("vati.intelligence", fromlist=["compute_features"]).compute_features(mk_bars(closes[:i])))
    # London hour: pick a now inside London
    now = bars[-1].end_ms + now_offset_ms
    return build_market_state(symbol="EURUSD", base="EUR", quote="USD", bars=bars, regime_engine=eng, calendar=FX_CALENDAR, events=events,
                              integrity=MarketIntegrityState.NORMAL, now_ms=now, last_quote_ms=now - 100, activation_id="vtil-act-test")


def test_capsule_registry_loads_seals_and_gates():
    reg = CapsuleRegistry.load_dir(REG)
    ids = {c.strategy_id for c in reg.all()}
    assert {"FX-TREND-PULLBACK-01", "FX-LONDON-BREAKOUT-01", "ZSE-VALUE-ROTATION-01"} <= ids
    c = reg.get("FX-TREND-PULLBACK-01")
    assert c.state is StrategyState.DEMO and c.capsule_hash == c.body_hash()
    with pytest.raises(CapsuleError, match="capsule_hash mismatch"):
        CapsuleRegistry([Capsule({**c.data, "capsule_hash": "0" * 64})])
    with pytest.raises(CapsuleError, match="SCALP/MICRO"):
        CapsuleRegistry([Capsule(CapsuleRegistry.seal({**c.data, "horizons": ["SCALP"]}))])
    with pytest.raises(CapsuleError, match="MICRO horizon removed"):
        CapsuleRegistry([Capsule(CapsuleRegistry.seal({**c.data, "horizons": ["MICRO"], "required_data_granularity": "L2"}))])


def test_capsule_promotion_requires_signature_and_one_step():
    """P0-TRADE-001 — promoting towards live capital used to accept "sig:owner"."""
    from conftest_owner_authority import OwnerAuthorityHarness

    owner = OwnerAuthorityHarness()
    reg = CapsuleRegistry.load_dir(REG, authority=owner.verifier)
    signature_gate_cert = passing_certificate(
        strategy_id="FX-TREND-PULLBACK-01",
        capsule_hash=reg.get("FX-TREND-PULLBACK-01").capsule_hash,
    )
    # Certificate validation now precedes owner-authority validation. Supply
    # valid semantic evidence here so these assertions isolate the signature gate.
    with pytest.raises(CapsuleError, match="signature"):
        reg.promote(
            "FX-TREND-PULLBACK-01", StrategyState.SHADOW,
            approval_signature_ref="", evidence_refs=["bt-1"],
            approved_at_unix=1, certificate=signature_gate_cert,
        )
    with pytest.raises(CapsuleError, match="signature"):
        reg.promote(
            "FX-TREND-PULLBACK-01", StrategyState.SHADOW,
            approval_signature_ref="sig:owner", evidence_refs=["bt-1"],
            approved_at_unix=1, certificate=signature_gate_cert,
        )
    # Authority to promote to SHADOW is not authority to promote to CERTIFIED_LIVE.
    with pytest.raises(CapsuleError, match="one state"):
        reg.promote("FX-TREND-PULLBACK-01", StrategyState.CERTIFIED_LIVE,
                    approval_signature_ref=owner.token(act="capsule-promote", subject="FX-TREND-PULLBACK-01:CERTIFIED_LIVE", issued_at_unix=1),
                    evidence_refs=["e"], approved_at_unix=1)
    cert_for_shadow = passing_certificate(
        strategy_id="FX-TREND-PULLBACK-01",
        capsule_hash=reg.get("FX-TREND-PULLBACK-01").capsule_hash,
    )
    with pytest.raises(CapsuleError, match="signature"):
        reg.promote("FX-TREND-PULLBACK-01", StrategyState.SHADOW,
                    approval_signature_ref=owner.token(
                        act="capsule-promote",
                        subject=f"FX-TREND-PULLBACK-01:CERTIFIED_LIVE:{cert_for_shadow.validation_hash}",
                        issued_at_unix=1,
                    ),
                    evidence_refs=["bt-1"], approved_at_unix=1, certificate=cert_for_shadow)
    # TRD-ENH-021 — a signed promotion with only opaque evidence refs is refused
    # from DEMO onwards; the certificate is the semantic content refs never had.
    with pytest.raises(CapsuleError, match="StrategyValidationCertificate"):
        reg.promote("FX-TREND-PULLBACK-01", StrategyState.SHADOW,
                    approval_signature_ref=owner.token(act="capsule-promote", subject="FX-TREND-PULLBACK-01:SHADOW", issued_at_unix=1),
                    evidence_refs=["bt-1"], approved_at_unix=1)
    cert = passing_certificate(strategy_id="FX-TREND-PULLBACK-01",
                               capsule_hash=reg.get("FX-TREND-PULLBACK-01").capsule_hash)
    c = reg.promote("FX-TREND-PULLBACK-01", StrategyState.SHADOW,
                    approval_signature_ref=owner.token(
                        act="capsule-promote",
                        subject=f"FX-TREND-PULLBACK-01:SHADOW:{cert.validation_hash}",
                        issued_at_unix=1,
                    ),
                    evidence_refs=["bt-1"], approved_at_unix=1, certificate=cert)
    assert c.state is StrategyState.SHADOW and c.data["supersedes"] and c.capsule_hash == c.body_hash()
    assert c.data["validation_hash"] == cert.validation_hash
    d = reg.demote("FX-TREND-PULLBACK-01", StrategyState.DEGRADED, reason="health 0.5")
    assert d.state is StrategyState.DEGRADED


def test_trend_pullback_fires_on_pullback_only():
    closes = trending(120)
    st = state_for(closes)
    strat = FxTrendPullback()
    ctx = StrategyContext(round_trip_cost_pct=Decimal("0.0003"))
    sig_at_high = strat.evaluate(st, ctx)  # price above EMA in an uptrend: no pullback → None
    assert sig_at_high is None
    st2 = state_for(pullback_fixture())
    sig = strat.evaluate(st2, ctx)
    assert sig is not None and sig.direction is Direction.LONG and sig.stop < sig.entry < sig.targets[0] and sig.expected_gross_move_pct > 0


def test_event_drift_only_in_drift_window():
    closes = trending(120, drift=0.0002)
    bars_end = mk_bars(closes)[-1].end_ms
    ev = EventMatrix([Tier1Event("NFP", "NFP", bars_end - 2 * 3_600_000, frozenset({"USD"}), verified_sources=2)])
    st = state_for(closes, events=ev)
    sig = EventDrift().evaluate(st, StrategyContext(round_trip_cost_pct=Decimal("0.0003"), event_release_ref_price=Decimal(str(closes[-1])) - Decimal("0.01")))
    assert sig is not None and sig.event_certified and sig.direction is Direction.LONG
    quiet = EventMatrix([Tier1Event("NFP", "NFP", bars_end - 30 * 60_000, frozenset({"USD"}), verified_sources=2)])
    assert EventDrift().evaluate(state_for(closes, events=quiet), StrategyContext(Decimal("0.0003"), Decimal("1.0"))) is None


def zse_snap(**over):
    base = dict(symbol="DELTA", exchange="ZSE", last_price=Decimal("25"), adv_20d_shares=Decimal("120000"), trading_days_of_20=18, median_spread_pct=Decimal("0.02"),
                value_score=Decimal("0.8"), days_since_results=40, post_results_drift_pct=None, currency_regime=CurrencyRegime.ELEVATED,
                round_trip_cost_pct=Decimal("0.044"), liquidity_haircut=Decimal("0.02"))
    base.update(over)
    return ZseSnapshot(**base)


def test_zse_strategies_respect_regime_and_cost():
    st = state_for(ranging(120))
    v = ZseValueRotation()
    sig = v.evaluate(st, StrategyContext(Decimal("0.044"), zse=zse_snap()))
    assert sig is not None and sig.direction is Direction.LONG and sig.horizon == "POSITION" and sig.expected_gross_move_pct >= Decimal("0.132")
    assert v.evaluate(st, StrategyContext(Decimal("0.07"), zse=zse_snap(currency_regime=CurrencyRegime.DISORDERLY))) is None
    assert v.evaluate(st, StrategyContext(Decimal("0.07"), zse=zse_snap(value_score=Decimal("0.6"), round_trip_cost_pct=Decimal("0.07")))) is None  # 8% gap < 3×7%
    lp = ZseLiquidityProvision()
    sig = lp.evaluate(st, StrategyContext(Decimal("0.02"), zse=zse_snap(median_spread_pct=Decimal("0.08"), round_trip_cost_pct=Decimal("0.02"))))
    assert sig is not None and sig.entry_type == "PASSIVE_LIMIT" and sig.entry < Decimal("25")
    assert lp.evaluate(st, StrategyContext(Decimal("0.02"), zse=zse_snap(median_spread_pct=Decimal("0.08"), currency_regime=CurrencyRegime.STRESSED))) is None


def test_horizon_arbiter_cost_multiples():
    h = HorizonArbiter()
    assert h.decide("SCALP", Decimal("0.0006"), Decimal("0.0003"), 100).horizon is None      # 2× < 3×
    assert h.decide("SCALP", Decimal("0.0010"), Decimal("0.0003"), 100).horizon == "SCALP"
    assert h.decide("SCALP", Decimal("0.0010"), Decimal("0.0003"), 900).horizon is None      # stale for scalp
    assert h.decide("SWING", Decimal("0.01"), Decimal("0.0003"), 4000).horizon == "SWING"
    assert h.decide("MICRO", Decimal("1"), Decimal("0.0003"), 1).horizon is None
    assert h.decide("SWING", Decimal("1"), Decimal("0"), 1).horizon is None


def test_meta_labeler_rules():
    st = state_for(pullback_fixture())
    sig = FxTrendPullback().evaluate(st, StrategyContext(Decimal("0.0003")))
    m = MetaLabeler()
    v = m.score(st, sig, Decimal("5"))
    assert v.label in (MetaLabel.TRADE, MetaLabel.REDUCE_SIZE) and all(x <= 1 for x in (v.confidence_multiplier, v.volatility_multiplier, v.liquidity_multiplier, v.event_risk_multiplier, v.regime_multiplier))
    assert v.calibration_state == "RULES_V0_UNCALIBRATED"
    assert m.score(st, sig, Decimal("1.5")).label is MetaLabel.SKIP
    assert MetaLabeler(capsule_health={sig.strategy_id: Decimal("0.4")}).score(st, sig, Decimal("5")).label is MetaLabel.SKIP
    assert MetaLabeler(t2_assessment={"fresh": True, "model_disagreement": "0.7"}).score(st, sig, Decimal("5")).label is MetaLabel.WAIT
    stale_t2 = MetaLabeler(t2_assessment={"fresh": False, "model_disagreement": "0.9"}).score(st, sig, Decimal("5"))
    assert stale_t2.label is not MetaLabel.WAIT  # stale LLM output is ignored


def demo_mandate(**over):
    return TradingMandate.from_mapping(mandate_dict(mode="DEMO_TRADER", allowed_strategies=["FX-TREND-PULLBACK-01", "FX-LONDON-BREAKOUT-01"], **over))


def test_opportunity_engine_end_to_end_with_risk_authority(eurusd):
    reg = CapsuleRegistry.load_dir(REG)
    impl = {sid: STRATEGY_IMPLEMENTATIONS[sid.rsplit("-", 1)[0]](strategy_id=sid) for sid in ("FX-TREND-PULLBACK-01", "FX-LONDON-BREAKOUT-01")}
    m = demo_mandate()
    eng = OpportunityEngine(reg, impl, m)
    st = state_for(pullback_fixture())
    oa = eng.assess(st, StrategyContext(Decimal("0.0003")), regime_label=st.regime.trend.value, account_alias="fx_primary", venue="mt5", idempotency_seed="session-1")
    assert oa.intent is not None and oa.decision in ("TRADE", "REDUCE_SIZE") and oa.assessment_hash
    it = oa.intent
    assert it.owner_authority == "MANDATE" and it.market_snapshot_hash == st.state_hash and it.strategy_state is StrategyState.DEMO
    # same inputs → same intent id and idempotency key (deterministic)
    oa2 = OpportunityEngine(reg, impl, m).assess(st, StrategyContext(Decimal("0.0003")), regime_label=st.regime.trend.value, account_alias="fx_primary", venue="mt5", idempotency_seed="session-1")
    assert oa2.intent.trade_intent_id == it.trade_intent_id and oa2.intent.idempotency_key == it.idempotency_key
    snap = snapshot(eurusd)
    d = RiskAuthority(m).evaluate_safe(it, snap)
    assert d.decision in (Decision.APPROVED, Decision.REDUCED), d
    # no-trade path: ranging market → NO_TRADE with reasons for every capsule
    oa3 = eng.assess(state_for(ranging(120)), StrategyContext(Decimal("0.0003")), regime_label="RANGE", account_alias="fx_primary", venue="mt5", idempotency_seed="s")
    assert oa3.intent is None and oa3.decision in ("NO_TRADE", "WAIT") and len(oa3.candidates) == len(reg.all())
