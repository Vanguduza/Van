"""Independent risk-policy tests for owner-selected opportunity temperaments.

These tests use no venue or model and cannot place a trade. A mocked Risk
Authority receives each full TradeIntent and can reject before execution.
"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal as D
from types import SimpleNamespace

import pytest

from conftest import mandate_dict, owner_authority
from vati.app.account_coordinator import AccountDecisionCoordinator, CoordinatorConfig
from vati.arbiter.candidate import CandidateOpportunity
from vati.arbiter.portfolio_allocator import OpportunityPortfolioAllocator
from vati.arbiter.temperament import (
    AdmittedEdge, TemperamentPolicy, TemperedOpportunityAllocator,
)
from vati.risk.contracts import Direction
from vati.risk.mandate import (
    MandateError, PlatformCeilings, TradingMandate, TradingTemperament,
    trading_temperament_subject,
)

S1, S2 = "S-EURUSD", "S-GBPUSD"
NOW = 1_000


def signed_temperament(data):
    owner = owner_authority()
    data["temperament_owner_signature_ref"] = owner.token(
        act="trading-temperament-admit",
        subject=trading_temperament_subject(data),
        issued_at_unix=int(data["signed_at_unix"]),
        lifetime_seconds=int(data["expires_at_unix"]) - int(data["signed_at_unix"]),
    )
    return data


def mandate(**overrides):
    data = mandate_dict(allowed_strategies=[S1, S2], **overrides)
    if data.get("trading_temperament") is not None or data.get("strategy_temperaments"):
        signed_temperament(data)
    return TradingMandate.from_mapping(data, authority=owner_authority().verifier)


def cand(*, cid="a", strategy=S1, symbol="EURUSD", cost="6", regime="1",
         confidence="0.5", source=True, generated=NOW):
    return CandidateOpportunity(
        candidate_id=cid, account_alias="fx_primary", venue="mt5", symbol=symbol,
        strategy_id=strategy, strategy_version="1", capsule_hash="capsule-seal",
        strategy_state="DEMO", generated_at_ms=generated,
        valid_from_ms=generated, valid_until_ms=generated + 10_000,
        mtf_state_hash="market-seal" if source else "",
        source_state_hashes=("source-seal",) if source else (),
        feature_contract_hash="feature-seal" if source else "",
        direction=Direction.LONG, entry=D("1.1000"), stop=D("1.0900"),
        targets=(D("1.1300"),), horizon="INTRADAY",
        cost_multiple=D(cost), capsule_risk_ceiling=D("0.0050"),
        regime_multiplier=D(regime), confidence_score=D(confidence),
    ).sealed()


def evidence(c, *, edge="0.40", sample=80, expiry=NOW + 10_000,
             quality="0.95", stability="0.95", certificate="cert-sha"):
    return AdmittedEdge(
        candidate_hash=c.candidate_hash, account_alias=c.account_alias,
        strategy_id=c.strategy_id, capsule_hash=c.capsule_hash,
        edge_floor_R=D(edge), expected_R_per_risk_day=D("0.45"),
        execution_quality=D(quality), regime_stability=D(stability),
        validated_trade_count=sample, valid_until_ms=expiry,
        validation_certificate_hash=certificate,
    ).sealed()


def test_absent_mode_preserves_original_behavior():
    m = mandate()
    assert not m.temperament_enabled
    assert m.temperament_for(S1) is None
    v = TemperamentPolicy(m).verdict(cand(), now_ms=NOW)
    assert v.eligible and v.temperament == "LEGACY" and v.risk_fraction == D("1")
    assert m.max_risk_per_trade == D("0.0050")


def test_orthogonal_to_authorization_mode_and_signed_strategy_override():
    m = mandate(trading_temperament="NORMAL",
                strategy_temperaments={S1: "AGGRESSIVE"})
    assert m.mode.value == "LIMITED_LIVE"
    assert m.temperament_for(S1) is TradingTemperament.AGGRESSIVE
    assert m.temperament_for(S2) is TradingTemperament.NORMAL


@pytest.mark.parametrize("overrides", [
    {"trading_temperament": "EXTREME"},
    {"strategy_temperaments": {S1: "MARTINGALE"}},
    {"strategy_temperaments": {"UNAPPROVED": "NORMAL"}},
    {"strategy_temperaments": [S1, S2]},
])
def test_invalid_or_unapproved_profile_is_rejected(overrides):
    with pytest.raises(MandateError):
        mandate(**overrides)


def test_unsigned_profile_is_refused_even_if_base_mandate_signature_is_valid():
    unsigned = mandate_dict(allowed_strategies=[S1], trading_temperament="AGGRESSIVE")
    with pytest.raises(MandateError, match="owner-signed temperament"):
        TradingMandate.from_mapping(unsigned, authority=owner_authority().verifier)


def test_profile_signature_binds_entire_mandate_document_and_expires():
    data = mandate_dict(allowed_strategies=[S1], trading_temperament="RISKY")
    signed_temperament(data)
    data["max_risk_per_trade"] = "0.0090"
    with pytest.raises(MandateError, match="owner-signed"):
        TradingMandate.from_mapping(data, authority=owner_authority().verifier)


def test_risky_utilizes_more_signed_budget_than_normal_without_widening_it():
    c = cand(cost="4", regime="0.95")
    normal = TemperamentPolicy(mandate(trading_temperament="NORMAL")).verdict(c, now_ms=NOW)
    risky = TemperamentPolicy(mandate(trading_temperament="RISKY")).verdict(c, now_ms=NOW)
    assert normal.eligible and risky.eligible
    assert D("0") < normal.risk_fraction < risky.risk_fraction < D("1")
    assert normal.risk_fraction * D("0.005") <= D("0.005")
    assert risky.risk_fraction * D("0.005") <= D("0.005")


def test_aggressive_is_not_an_all_trades_high_risk_switch():
    m = mandate(trading_temperament="AGGRESSIVE")
    assert not TemperamentPolicy(m).verdict(cand(), now_ms=NOW).eligible
    assert not TemperamentPolicy(m, admitted_edge_fn=lambda c: evidence(c)).verdict(
        cand(cost="1"), now_ms=NOW).eligible
    assert not TemperamentPolicy(m, admitted_edge_fn=lambda c: evidence(c)).verdict(
        cand(cost="6", regime="0.4"), now_ms=NOW).eligible


def test_aggressive_requires_true_independently_admitted_edge_and_seal():
    m = mandate(trading_temperament="AGGRESSIVE")
    c = cand()
    for proof in (
        evidence(c, edge="-0.1"), evidence(c, sample=49),
        evidence(c, expiry=NOW), evidence(c, certificate=""),
        replace(evidence(c), edge_floor_R=D("0.99")),
    ):
        v = TemperamentPolicy(m, admitted_edge_fn=lambda _c, p=proof: p).verdict(
            c, now_ms=NOW)
        assert not v.eligible
        assert v.risk_fraction == D("0")


def test_aggressive_can_utilize_full_existing_budget_on_exceptional_evidence():
    m = mandate(trading_temperament="AGGRESSIVE")
    c = cand()
    v = TemperamentPolicy(m, admitted_edge_fn=lambda _c: evidence(c)).verdict(
        c, now_ms=NOW)
    assert v.eligible and v.grade == "EXCEPTIONAL"
    assert v.risk_fraction == D("1")
    assert v.evidence_hash == evidence(c).evidence_hash
    assert v.decision_hash


def test_admitted_high_conviction_does_not_automatically_use_entire_budget():
    m = mandate(trading_temperament="AGGRESSIVE")
    c = cand(cost="3.5", regime="0.82")
    v = TemperamentPolicy(m, admitted_edge_fn=lambda _c: evidence(c, edge="0.20")).verdict(
        c, now_ms=NOW)
    assert v.eligible and v.grade == "HIGH_CONVICTION"
    assert v.risk_fraction == D("0.70")


def test_model_confidence_cannot_change_entry_or_sizing():
    m = mandate(trading_temperament="AGGRESSIVE")
    low, high = cand(confidence="0.01"), cand(confidence="0.99")
    provider = lambda c: evidence(c)
    first = TemperamentPolicy(m, admitted_edge_fn=provider).verdict(low, now_ms=NOW)
    second = TemperamentPolicy(m, admitted_edge_fn=provider).verdict(high, now_ms=NOW)
    assert first.eligible == second.eligible
    assert first.quality_score == second.quality_score
    assert first.risk_fraction == second.risk_fraction


def test_profile_refuses_tampered_stale_or_unverified_candidates():
    policy = TemperamentPolicy(mandate(trading_temperament="RISKY"))
    c = cand()
    assert not policy.verdict(replace(c, cost_multiple=D("50")), now_ms=NOW).eligible
    assert not policy.verdict(c, now_ms=NOW + 10_000).eligible
    assert not policy.verdict(cand(source=False), now_ms=NOW).eligible


def test_independently_admitted_exceptional_setup_ranks_ahead_of_ordinary_candidate():
    m = mandate(trading_temperament="NORMAL",
                strategy_temperaments={S1: "AGGRESSIVE"})
    exceptional = cand(cid="great", strategy=S1, cost="6", symbol="EURUSD")
    ordinary = cand(cid="routine", strategy=S2, cost="6", symbol="GBPUSD")
    p = TemperamentPolicy(m, admitted_edge_fn=lambda c: evidence(c) if c.strategy_id == S1 else None)
    ranks = TemperedOpportunityAllocator(OpportunityPortfolioAllocator(), p).rank(
        [ordinary, exceptional], now_ms=NOW)
    assert ranks[0].candidate_id == "great"
    assert ranks[0].score_components["temperament"] == "AGGRESSIVE"
    assert ranks[0].score_components["profile_verdict_hash"]
    assert ranks[1].candidate_id == "routine"


class DummyEvaluator:
    def __init__(self, candidate):
        self.symbol, self.candidate = candidate.symbol, candidate

    def evaluate(self, bars, *, now_ms):
        return (self.candidate,)


def test_coordinator_applies_reduce_only_fraction_before_the_real_risk_gate():
    m = mandate(trading_temperament="RISKY")
    c = cand()
    p = TemperamentPolicy(m)
    risk_seen, executed = [], []

    def gate(intent, snapshot):
        risk_seen.append(intent)
        return SimpleNamespace(decision="APPROVED")

    coordinator = AccountDecisionCoordinator(
        CoordinatorConfig(account_alias=c.account_alias),
        evaluators=[DummyEvaluator(c)],
        allocator=TemperedOpportunityAllocator(OpportunityPortfolioAllocator(), p),
        risk_fn=gate, execute_fn=lambda *args: executed.append(args),
        snapshot_fn=lambda _c: SimpleNamespace(equity=D("1000")), mandate=m,
        temperament_policy=p)
    run = coordinator.step(now_ms=NOW, bars_by_symbol={})
    assert len(risk_seen) == len(executed) == 1
    original_ceiling = min(c.capsule_risk_ceiling, m.risk_budget_for(c.strategy_id))
    assert risk_seen[0].requested_risk_pct == original_ceiling * p.verdict(c, now_ms=NOW).risk_fraction
    assert risk_seen[0].requested_risk_pct <= m.max_risk_per_trade
    assert run.outcomes[0].temperament_verdict_hash
    assert run.outcomes[0].risk_fraction != ""


def test_coordinator_refuses_changed_evidence_before_risk_authority():
    m = mandate(trading_temperament="AGGRESSIVE")
    c = cand()
    call_count = [0]

    def shifting_proof(_candidate):
        call_count[0] += 1
        return evidence(c) if call_count[0] == 1 else None

    p = TemperamentPolicy(m, admitted_edge_fn=shifting_proof)
    risk_seen = []
    coordinator = AccountDecisionCoordinator(
        CoordinatorConfig(account_alias=c.account_alias),
        evaluators=[DummyEvaluator(c)],
        allocator=TemperedOpportunityAllocator(OpportunityPortfolioAllocator(), p),
        risk_fn=lambda intent, snap: risk_seen.append(intent),
        execute_fn=lambda *args: None, snapshot_fn=lambda _c: object(),
        mandate=m, temperament_policy=p)
    run = coordinator.step(now_ms=NOW, bars_by_symbol={})
    assert not risk_seen
    assert run.outcomes[0].decision == "NOT_SELECTED"


def test_platform_ceiling_remains_below_two_percent_under_every_mode():
    assert PlatformCeilings().max_risk_per_trade == D("0.02")
    for mode in TradingTemperament:
        m = mandate(trading_temperament=mode.value)
        assert m.max_risk_per_trade <= PlatformCeilings().max_risk_per_trade
        assert m.max_open_stop_risk <= PlatformCeilings().max_open_stop_risk


def test_winner_pursuit_takes_smaller_partial_only_when_preapproved():
    from vati.lifecycle.temperament import profit_pursuit_policy
    from vati.lifecycle.scale_policy import ADAPTIVE, DEFENSIVE
    normal = profit_pursuit_policy(DEFENSIVE, TradingTemperament.NORMAL)
    risky = profit_pursuit_policy(DEFENSIVE, TradingTemperament.RISKY)
    aggressive = profit_pursuit_policy(DEFENSIVE, TradingTemperament.AGGRESSIVE)
    assert normal is DEFENSIVE
    assert aggressive.partial_take_fraction < risky.partial_take_fraction < normal.partial_take_fraction
    assert aggressive.permitted == risky.permitted == normal.permitted
    assert aggressive.reduce_fraction == risky.reduce_fraction == normal.reduce_fraction
    assert profit_pursuit_policy(ADAPTIVE, TradingTemperament.AGGRESSIVE).permitted == ADAPTIVE.permitted


def test_aggressive_never_grants_unregistered_pyramiding_or_exit_actions():
    from vati.lifecycle.temperament import profit_pursuit_policy
    from vati.lifecycle.scale_policy import HOLD_OR_EXIT, NO_SCALING, Adjustment
    policy = profit_pursuit_policy(HOLD_OR_EXIT, TradingTemperament.AGGRESSIVE)
    assert policy.permitted == HOLD_OR_EXIT.permitted
    assert Adjustment.ADD not in policy.permitted
    assert Adjustment.EXIT in policy.permitted
    assert not NO_SCALING.enabled


def test_direct_mandate_construction_cannot_activate_unsigned_profile():
    from dataclasses import replace
    base = mandate()
    tampered = replace(base, trading_temperament=TradingTemperament.AGGRESSIVE)
    with pytest.raises(MandateError, match="owner-verified temperament"):
        tampered.validate(PlatformCeilings())
