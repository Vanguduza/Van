"""GAP-F-003: the sealed trade thesis and its per-cycle assessment.

A position used to carry a price, a stop and a health verdict, and nothing that
said why it existed. These tests pin the claim being written down once and
never rewritten, and the assessment that decides, from deterministic evidence,
whether the reason is still there.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from vati.core.events import EventKind
from vati.core.ledger import Ledger
from vati.lifecycle.thesis import (
    THESIS_REASONS,
    ThesisEngine,
    ThesisError,
    ThesisInputs,
    ThesisState,
    TradeThesis,
    thesis_from_capsule,
)
from vati.lifecycle.trade_health import (
    HealthState, PositionHealthInputs, TradeHealth, TradeHealthEngine,
)
from vati.risk.contracts import Direction

NOW = 1_800_000_000_000
HORIZON = 4 * 3_600_000


def make_thesis(**overrides) -> TradeThesis:
    base = dict(
        trade_intent_id="ti-1",
        symbol="EURUSD",
        strategy_id="FX-TREND-03",
        direction=Direction.LONG,
        capsule_hash="cap-1",
        market_state_hash="msh-1",
        statement="long EURUSD from 1.1000 with risk to 1.0950",
        expected_path={"target_r": "2"},
        invalidation={"price": "1.0950"},
        confirmation={"first_target": "1.1100", "progress_r": "1"},
        adverse_signals=(),
        event_sensitivity=("EUR", "USD"),
        entry=Decimal("1.1000"),
        original_stop=Decimal("1.0950"),
        original_approved_risk_pct=Decimal("0.004"),
        expected_horizon_ms=HORIZON,
        created_ms=NOW,
        entry_volatility=Decimal("0.0010"),
        entry_liquidity=Decimal("0.8"),
    )
    base.update(overrides)
    return TradeThesis(**base).sealed()


def health_at(price: Decimal, *, stop=Decimal("1.0950"), confirmed=True,
              now_ms=NOW + 60_000, worst=None, best=None) -> TradeHealth:
    return TradeHealthEngine().assess(PositionHealthInputs(
        trade_intent_id="ti-1", symbol="EURUSD", direction=Direction.LONG,
        entry_price=Decimal("1.1000"), current_price=price,
        original_stop=Decimal("1.0950"), current_stop=stop,
        has_confirmed_stop=confirmed, opened_ms=NOW, now_ms=now_ms,
        expected_horizon_ms=HORIZON,
        worst_price=worst if worst is not None else min(price, Decimal("1.1000")),
        best_price=best if best is not None else max(price, Decimal("1.1000")),
    ))


def inputs(price: Decimal, **overrides) -> ThesisInputs:
    base = dict(
        thesis=make_thesis(),
        health=health_at(price),
        current_price=price,
        now_ms=NOW + 60_000,
        current_stop=Decimal("1.0950"),
    )
    base.update(overrides)
    return ThesisInputs(**base)


# --- the claim ------------------------------------------------------------

def test_a_thesis_is_sealed_over_everything_it_claims():
    t = make_thesis()
    assert t.seal_ok()
    edited = TradeThesis(**{**t.__dict__, "statement": "a different story"})
    assert not edited.seal_ok()


def test_a_thesis_without_a_risk_distance_is_refused():
    """No R unit means no falsifiable claim."""
    with pytest.raises(ThesisError, match="no risk distance"):
        make_thesis(original_stop=Decimal("1.1000"))


def test_an_unchecked_invalidation_axis_is_refused():
    """A condition nothing checks is worse than no condition at all."""
    with pytest.raises(ThesisError, match="which nothing checks"):
        make_thesis(invalidation={"vibes": "bad"})


def test_a_claim_is_made_once_and_cannot_be_rewritten(tmp_path):
    engine = ThesisEngine(ledger=Ledger(tmp_path / "v.sqlite"))
    engine.seal(make_thesis())
    engine.seal(make_thesis())          # identical is idempotent
    with pytest.raises(ThesisError, match="a claim is made once"):
        engine.seal(make_thesis(statement="actually it was a short"))


def test_sealing_writes_one_ledger_event(tmp_path):
    ledger = Ledger(tmp_path / "v.sqlite")
    ThesisEngine(ledger=ledger).seal(make_thesis())
    rows = list(ledger.iter(EventKind.TRADE_THESIS))
    assert len(rows) == 1
    assert rows[0].payload["original_approved_risk_pct"] == "0.004"
    assert rows[0].correlation_id == "ti-1"


def test_a_thesis_round_trips_through_its_ledger_payload():
    t = make_thesis()
    assert TradeThesis.from_payload(t.to_dict()).seal == t.seal


# --- derivation from the capsule -----------------------------------------

def test_a_derived_thesis_is_always_falsifiable():
    """The approved stop is a price invalidation even with no capsule input."""
    t = thesis_from_capsule(
        trade_intent_id="ti-2", symbol="EURUSD", strategy_id="S",
        direction=Direction.LONG, capsule_hash="", market_state_hash="m",
        entry=Decimal("1.10"), original_stop=Decimal("1.09"),
        original_approved_risk_pct=Decimal("0.003"), created_ms=NOW)
    assert t.invalidation["price"] == "1.09"
    assert t.statement and t.seal_ok()


def test_a_capsule_may_declare_its_own_conditions():
    t = thesis_from_capsule(
        trade_intent_id="ti-3", symbol="EURUSD", strategy_id="S",
        direction=Direction.LONG, capsule_hash="", market_state_hash="m",
        entry=Decimal("1.10"), original_stop=Decimal("1.09"),
        original_approved_risk_pct=Decimal("0.003"), created_ms=NOW,
        capsule_data={"thesis": {
            "statement": "London continuation after the Asian range breaks",
            "invalidation_structure": "range low reclaimed",
            "adverse_signals": ["SPREAD_ABNORMAL"],
        }},
        targets=(Decimal("1.12"),), regime_label="UP", expected_horizon_ms=HORIZON)
    assert t.statement.startswith("London continuation")
    assert t.invalidation["structure"] == "range low reclaimed"
    assert t.invalidation["regime"] == "UP"
    assert t.confirmation["first_target"] == "1.12"
    assert t.adverse_signals == ("SPREAD_ABNORMAL",)


def test_the_time_invalidation_does_not_fire_on_a_confirmed_trade():
    """A trade that is working is never closed by the clock alone."""
    t = thesis_from_capsule(
        trade_intent_id="ti-4", symbol="EURUSD", strategy_id="S",
        direction=Direction.LONG, capsule_hash="", market_state_hash="m",
        entry=Decimal("1.10"), original_stop=Decimal("1.09"),
        original_approved_risk_pct=Decimal("0.003"), created_ms=NOW,
        expected_horizon_ms=HORIZON)
    deadline = int(t.invalidation["time_ms"])
    engine = ThesisEngine()
    past = engine.assess(ThesisInputs(
        thesis=t, health=health_at(Decimal("1.1005"), now_ms=deadline + 1),
        current_price=Decimal("1.1005"), now_ms=deadline + 1,
        current_stop=Decimal("1.09"), confirmations_met=("progress_r",)), persist=False)
    assert past.state is not ThesisState.INVALIDATED


# --- the assessment -------------------------------------------------------

def test_an_untouched_position_is_intact():
    a = ThesisEngine().assess(inputs(Decimal("1.1005")), persist=False)
    assert a.state is ThesisState.INTACT
    assert a.reasons == ()


def test_price_through_the_invalidation_level_invalidates():
    a = ThesisEngine().assess(inputs(Decimal("1.0940")), persist=False)
    assert a.state is ThesisState.INVALIDATED
    assert "INVALIDATION_PRICE" in a.reasons


def test_a_broken_structure_invalidates_when_the_claim_named_one():
    a = ThesisEngine().assess(inputs(
        Decimal("1.1005"),
        thesis=make_thesis(invalidation={"price": "1.0950", "structure": "range low"}),
        structure_broken=True), persist=False)
    assert a.state is ThesisState.INVALIDATED
    assert "INVALIDATION_STRUCTURE" in a.reasons


def test_a_changed_regime_invalidates_when_the_claim_named_one():
    a = ThesisEngine().assess(inputs(
        Decimal("1.1005"),
        thesis=make_thesis(invalidation={"price": "1.0950", "regime": "UP"}),
        regime_label="DOWN"), persist=False)
    assert a.state is ThesisState.INVALIDATED
    assert "INVALIDATION_REGIME" in a.reasons


def test_a_failing_health_verdict_invalidates_whatever_price_is_doing():
    """An unprotected position has no claim left to assess."""
    a = ThesisEngine().assess(inputs(
        Decimal("1.1050"),
        health=health_at(Decimal("1.1050"), confirmed=False)), persist=False)
    assert a.state is ThesisState.INVALIDATED


def test_expanded_volatility_makes_the_same_claim_riskier():
    a = ThesisEngine().assess(inputs(
        Decimal("1.1005"), volatility=Decimal("0.0020")), persist=False)
    assert a.state is ThesisState.RISKIER
    assert "VOLATILITY_EXPANDED" in a.reasons
    assert a.evidence["volatility_ratio"] == "2"


def test_impaired_liquidity_makes_the_same_claim_riskier():
    a = ThesisEngine().assess(inputs(
        Decimal("1.1005"), liquidity=Decimal("0.4")), persist=False)
    assert a.state is ThesisState.RISKIER
    assert "LIQUIDITY_IMPAIRED" in a.reasons


def test_portfolio_crowding_makes_the_same_claim_riskier():
    a = ThesisEngine().assess(inputs(
        Decimal("1.1005"), correlation_multiplier=Decimal("0.6")), persist=False)
    assert a.state is ThesisState.RISKIER
    assert "CORRELATION_CROWDED" in a.reasons


def test_a_material_event_makes_the_same_claim_riskier():
    a = ThesisEngine().assess(inputs(
        Decimal("1.1005"), event_materiality=Decimal("0.7"),
        event_refs=("h1",)), persist=False)
    assert a.state is ThesisState.RISKIER
    assert "EVENT_IMPACT" in a.reasons
    assert a.event_refs == ("h1",)
    assert a.argues_for_less


def test_an_immaterial_event_does_not_change_the_state():
    a = ThesisEngine().assess(inputs(
        Decimal("1.1005"), event_materiality=Decimal("0.1")), persist=False)
    assert a.state is ThesisState.INTACT


def test_a_declared_adverse_signal_weakens_the_claim():
    a = ThesisEngine().assess(inputs(
        Decimal("1.1005"),
        thesis=make_thesis(adverse_signals=("SPREAD_ABNORMAL",)),
        adverse_present=("SPREAD_ABNORMAL",)), persist=False)
    assert a.state is ThesisState.WEAKER
    assert "ADVERSE_SIGNAL" in a.reasons


def test_time_past_the_horizon_weakens_the_claim():
    a = ThesisEngine().assess(inputs(
        Decimal("1.1005"), now_ms=NOW + HORIZON * 2), persist=False)
    assert a.state is ThesisState.WEAKER
    assert "TIME_IN_TRADE" in a.reasons


def test_protected_and_well_in_front_is_asymmetric():
    price = Decimal("1.1090")
    a = ThesisEngine().assess(inputs(
        price, current_stop=Decimal("1.1000"),
        health=health_at(price, stop=Decimal("1.1000"))), persist=False)
    assert a.state is ThesisState.ASYMMETRIC
    assert "PROTECTION_AT_BREAK_EVEN" in a.reasons
    assert a.current_r >= Decimal("1.5")


def test_a_met_confirmation_makes_the_claim_stronger():
    a = ThesisEngine().assess(inputs(
        Decimal("1.1030"), confirmations_met=("first_target",)), persist=False)
    assert a.state is ThesisState.STRONGER
    assert "CONFIRMATION_MET" in a.reasons


def test_a_move_far_past_the_expected_path_is_overextended():
    price = Decimal("1.1200")   # 4R against a declared 2R target
    a = ThesisEngine().assess(inputs(
        price, current_stop=Decimal("1.1100"),
        health=health_at(price, stop=Decimal("1.1100"))), persist=False)
    assert a.state is ThesisState.OVEREXTENDED
    assert "MOVE_EXCEEDED_EXPECTATION" in a.reasons


def test_no_state_licenses_more_risk():
    """Every state is a description or a withholding. None is a permission."""
    assert not hasattr(ThesisState, "INCREASE")
    for state in ThesisState:
        assert "INCREASE" not in state.value and "MORE" not in state.value


def test_every_reason_is_in_the_closed_vocabulary():
    a = ThesisEngine().assess(inputs(
        Decimal("1.0940"), volatility=Decimal("0.0030"),
        event_materiality=Decimal("0.9")), persist=False)
    for reason in a.reasons:
        assert reason in THESIS_REASONS


# --- persistence ----------------------------------------------------------

def test_assessments_are_written_only_on_state_change(tmp_path):
    ledger = Ledger(tmp_path / "v.sqlite")
    engine = ThesisEngine(ledger=ledger)
    engine.seal(make_thesis())
    for _ in range(4):
        engine.assess(inputs(Decimal("1.1005")))
    assert len(list(ledger.iter(EventKind.THESIS_ASSESSMENT))) == 1

    engine.assess(inputs(Decimal("1.0940")))
    rows = list(ledger.iter(EventKind.THESIS_ASSESSMENT))
    assert len(rows) == 2
    assert rows[-1].payload["state"] == "INVALIDATED"
    assert rows[-1].payload["previous_state"] == "INTACT"
    assert rows[-1].payload["reason_detail"]


def test_the_assessment_carries_the_evidence_that_drove_it(tmp_path):
    a = ThesisEngine().assess(inputs(
        Decimal("1.0970"), volatility=Decimal("0.0020"),
        correlation_multiplier=Decimal("0.5"),
        event_materiality=Decimal("0.8")), persist=False)
    ev = a.evidence
    assert {"current_r", "health_state", "time_in_trade_ms", "volatility_ratio",
            "correlation_multiplier", "event_materiality",
            "protection_at_break_even"} <= set(ev)
    assert a.body()["reason_detail"]
