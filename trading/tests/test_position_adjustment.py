"""GAP-F-003: adaptive position management, and the ceiling on adding.

The rule this file exists to pin: an ADD is permitted only when protection is
already at or beyond break-even *and* total risk after the add is no greater
than the risk originally approved for the position. "Winning" is never evidence
that more can be afforded, and the proof is in two places — the proposal
refuses to construct one that would breach the ceiling, and the Risk Authority
rejects a delta intent that tries to anyway.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from conftest import mandate_dict, snapshot
from vati.core.events import EventKind
from vati.core.ledger import Ledger
from vati.lifecycle.scale_policy import (
    ADAPTIVE,
    ADJUSTMENT_REASONS,
    ALL_ADJUSTMENTS,
    CONSERVATIVE,
    DEFENSIVE,
    HOLD_OR_EXIT,
    NO_SCALING,
    SIZE_CHANGING,
    Adjustment,
    AdjustmentError,
    AdjustmentPolicy,
    AdjustmentPolicyRegistry,
    PositionAdjustmentEngine,
    PositionAdjustmentProposal,
)
from vati.lifecycle.thesis import ThesisAssessment, ThesisState
from vati.lifecycle.trade_health import (
    HealthState, PositionHealthInputs, TradeHealthEngine,
)
from vati.risk import Decision, LossModel, OpenPosition, RiskAuthority, TradingMandate
from vati.risk.contracts import Direction, StrategyState, SymbolContract, TradeIntent

NOW = 1_800_000_000_000
ORIGINAL_RISK = Decimal("0.004")


def assessment(state: ThesisState, **overrides) -> ThesisAssessment:
    base = dict(
        trade_intent_id="ti-1", symbol="EURUSD", strategy_id="FX-TREND-03",
        thesis_seal="seal-1", state=state, reasons=(), evidence={},
        current_r=Decimal("1"), health_state=HealthState.HEALTHY,
        time_in_trade_ms=60_000, event_materiality=Decimal("0"), event_refs=(),
        assessed_ms=NOW,
    )
    base.update(overrides)
    return ThesisAssessment(**base)


def health(state: HealthState = HealthState.HEALTHY):
    price = {
        HealthState.HEALTHY: Decimal("1.1010"),
        HealthState.WATCH: Decimal("1.0975"),
        HealthState.IMPAIRED: Decimal("1.0962"),
        HealthState.FAILING: Decimal("1.1010"),
    }[state]
    return TradeHealthEngine().assess(PositionHealthInputs(
        trade_intent_id="ti-1", symbol="EURUSD", direction=Direction.LONG,
        entry_price=Decimal("1.1000"), current_price=price,
        original_stop=Decimal("1.0950"), current_stop=Decimal("1.0950"),
        has_confirmed_stop=state is not HealthState.FAILING,
        opened_ms=NOW, now_ms=NOW + 60_000, expected_horizon_ms=4 * 3_600_000,
        worst_price=price, best_price=price))


def propose(state, *, policy, ledger=None, scale_policy=NO_SCALING,
            protection_be=False, current_risk=ORIGINAL_RISK,
            health_state=HealthState.HEALTHY, proposed_stop=None, **kw):
    engine = PositionAdjustmentEngine(ledger=ledger)
    return engine.propose(
        assessment(state, **kw), health=health(health_state), policy=policy,
        original_approved_risk_pct=ORIGINAL_RISK,
        current_risk_pct=current_risk,
        protection_at_break_even=protection_be,
        scale_policy=scale_policy, proposed_stop=proposed_stop, now_ms=NOW)


# --- the vocabulary -------------------------------------------------------

def test_the_vocabulary_contains_no_way_to_raise_risk_directly():
    assert {a.value for a in ALL_ADJUSTMENTS} == {
        "HOLD", "ADD", "REDUCE", "MOVE_PROTECTION", "PARTIAL_TAKE", "EXIT"}
    for action in Adjustment:
        assert "WIDEN" not in action.value and "OVERRIDE" not in action.value


def test_only_size_changing_actions_require_the_authority():
    assert SIZE_CHANGING == {Adjustment.ADD, Adjustment.REDUCE, Adjustment.PARTIAL_TAKE}
    for action in SIZE_CHANGING:
        assert action in ALL_ADJUSTMENTS


def test_the_default_policy_is_hold_or_leave():
    assert AdjustmentPolicyRegistry().policy_for("never-heard-of-it") is HOLD_OR_EXIT
    assert HOLD_OR_EXIT.permitted == {Adjustment.HOLD, Adjustment.EXIT}


def test_a_policy_that_cannot_do_nothing_is_refused():
    with pytest.raises(AdjustmentError, match="does not permit HOLD"):
        AdjustmentPolicy(policy_id="X", permitted=frozenset({Adjustment.EXIT}))


def test_a_policy_fraction_outside_the_unit_interval_is_refused():
    with pytest.raises(AdjustmentError, match="outside"):
        AdjustmentPolicy(policy_id="X", permitted=HOLD_OR_EXIT.permitted,
                         reduce_fraction=Decimal("1.5"))


# --- proposals ------------------------------------------------------------

def test_an_intact_thesis_holds():
    p = propose(ThesisState.INTACT, policy=ADAPTIVE)
    assert p.action is Adjustment.HOLD and not p.changes_size


def test_an_invalidated_thesis_exits():
    p = propose(ThesisState.INVALIDATED, policy=DEFENSIVE)
    assert p.action is Adjustment.EXIT
    assert "THESIS_INVALIDATED" in p.reasons


def test_a_failing_health_verdict_exits_whatever_the_thesis_says():
    p = propose(ThesisState.INTACT, policy=DEFENSIVE, health_state=HealthState.FAILING)
    assert p.action is Adjustment.EXIT
    assert "HEALTH_FAILING" in p.reasons


def test_a_weaker_thesis_reduces_when_the_policy_permits_it():
    p = propose(ThesisState.WEAKER, policy=DEFENSIVE)
    assert p.action is Adjustment.REDUCE
    assert p.size_fraction == DEFENSIVE.reduce_fraction
    assert p.requires_authority


def test_a_riskier_thesis_reduces():
    p = propose(ThesisState.RISKIER, policy=DEFENSIVE,
                event_materiality=Decimal("0.8"))
    assert p.action is Adjustment.REDUCE
    assert "THESIS_RISKIER" in p.reasons and "EVENT_RISK" in p.reasons


def test_a_capsule_that_permits_only_hold_and_exit_still_gets_a_sound_answer():
    p = propose(ThesisState.WEAKER, policy=HOLD_OR_EXIT)
    assert p.action is Adjustment.HOLD
    assert "POLICY_FORBIDS" in p.reasons


def test_a_weaker_thesis_tightens_protection_when_reducing_is_forbidden():
    policy = AdjustmentPolicy(
        policy_id="PROTECT_ONLY",
        permitted=frozenset({Adjustment.HOLD, Adjustment.EXIT,
                             Adjustment.MOVE_PROTECTION}))
    p = propose(ThesisState.WEAKER, policy=policy, proposed_stop=Decimal("1.1000"))
    assert p.action is Adjustment.MOVE_PROTECTION
    assert p.new_stop == Decimal("1.1000")
    assert not p.requires_authority


def test_an_asymmetric_position_banks_when_adding_is_not_permitted():
    p = propose(ThesisState.ASYMMETRIC, policy=DEFENSIVE, protection_be=True,
                current_risk=Decimal("0"))
    assert p.action is Adjustment.PARTIAL_TAKE
    assert p.size_fraction == DEFENSIVE.partial_take_fraction


# --- the ADD ceiling ------------------------------------------------------

def test_an_add_needs_protection_at_or_beyond_break_even():
    p = propose(ThesisState.STRONGER, policy=ADAPTIVE, scale_policy=CONSERVATIVE,
                protection_be=False)
    assert p.action is not Adjustment.ADD
    assert "PROTECTION_BELOW_BREAK_EVEN" in p.reasons


def test_an_add_is_permitted_inside_the_original_risk_and_no_further():
    p = propose(ThesisState.STRONGER, policy=ADAPTIVE, scale_policy=CONSERVATIVE,
                protection_be=True, current_risk=Decimal("0"))
    assert p.action is Adjustment.ADD
    assert p.delta_risk_pct == ORIGINAL_RISK * CONSERVATIVE.scale_fractions[0]
    assert p.risk_after_action_pct <= p.original_approved_risk_pct
    assert p.requires_authority


def test_an_add_is_refused_when_the_original_risk_is_already_spent():
    p = propose(ThesisState.STRONGER, policy=ADAPTIVE, scale_policy=CONSERVATIVE,
                protection_be=True, current_risk=ORIGINAL_RISK)
    assert p.action is not Adjustment.ADD
    assert "RISK_BUDGET_SPENT" in p.reasons


def test_an_add_is_refused_when_health_is_not_healthy():
    p = propose(ThesisState.STRONGER, policy=ADAPTIVE, scale_policy=CONSERVATIVE,
                protection_be=True, current_risk=Decimal("0"),
                health_state=HealthState.WATCH)
    assert p.action is not Adjustment.ADD
    assert "HEALTH_BLOCKS_SCALING" in p.reasons


def test_an_add_is_refused_when_the_scale_policy_does_not_permit_scaling():
    p = propose(ThesisState.STRONGER, policy=ADAPTIVE, scale_policy=NO_SCALING,
                protection_be=True, current_risk=Decimal("0"))
    assert p.action is not Adjustment.ADD
    assert "POLICY_FORBIDS" in p.reasons


def test_an_add_without_the_original_risk_cannot_be_bounded():
    engine = PositionAdjustmentEngine()
    p = engine.propose(
        assessment(ThesisState.STRONGER), health=health(), policy=ADAPTIVE,
        original_approved_risk_pct=None, current_risk_pct=None,
        protection_at_break_even=True, scale_policy=CONSERVATIVE, now_ms=NOW)
    assert p.action is not Adjustment.ADD
    assert "NO_ORIGINAL_RISK" in p.reasons


def test_a_proposal_that_breaches_the_ceiling_cannot_even_be_constructed():
    """The rule is enforced where it cannot be skipped: in __post_init__."""
    with pytest.raises(AdjustmentError, match="past the originally approved"):
        PositionAdjustmentProposal(
            trade_intent_id="ti-1", symbol="EURUSD", strategy_id="S",
            action=Adjustment.ADD, reasons=("THESIS_STRONGER",),
            rationale="doubling down on a winner",
            delta_risk_pct=Decimal("0.004"),
            original_approved_risk_pct=Decimal("0.004"),
            risk_after_action_pct=Decimal("0.008"))


def test_every_proposal_reason_is_classified():
    for state in ThesisState:
        p = propose(state, policy=ADAPTIVE, scale_policy=CONSERVATIVE,
                    protection_be=True, current_risk=Decimal("0"))
        for reason in p.reasons:
            assert reason in ADJUSTMENT_REASONS


# --- persistence ----------------------------------------------------------

def test_every_proposal_is_persisted_with_its_rationale(tmp_path):
    ledger = Ledger(tmp_path / "v.sqlite")
    propose(ThesisState.WEAKER, policy=DEFENSIVE, ledger=ledger)
    rows = list(ledger.iter(EventKind.POSITION_ADJUSTMENT))
    assert len(rows) == 1
    payload = rows[0].payload
    assert payload["action"] == "REDUCE"
    assert payload["rationale"]
    assert payload["reason_detail"]
    assert payload["authority"] == "PROPOSAL_ONLY_RISK_AUTHORITY_DECIDES"
    assert payload["requires_authority"] is True


def test_execution_is_deterministic_per_capsule(tmp_path):
    """The same capsule policy always produces the same action."""
    first = propose(ThesisState.WEAKER, policy=DEFENSIVE)
    second = propose(ThesisState.WEAKER, policy=DEFENSIVE)
    assert first.action is second.action and first.digest == second.digest
    restricted = propose(ThesisState.WEAKER, policy=HOLD_OR_EXIT)
    assert restricted.action is Adjustment.HOLD


# --- the authority is the gate, not the proposal --------------------------

def _delta_intent(requested_risk_pct: Decimal, contract) -> TradeIntent:
    return TradeIntent(
        trade_intent_id="ti-delta", idempotency_key="idem-delta",
        account_alias="fx_primary", venue="mt5", symbol="EURUSD",
        direction=Direction.LONG, strategy_id="FX-LONDON-BREAKOUT-04",
        strategy_version="4.2.1", strategy_state=StrategyState.CERTIFIED_LIVE,
        entry=Decimal("1.10500"), stop=Decimal("1.10000"),
        requested_risk_pct=requested_risk_pct,
        decision_hash="dh-delta", market_snapshot_hash="msh")


def test_a_delta_intent_that_would_increase_original_risk_is_rejected_by_the_authority(
        eurusd):
    """The proposal layer bounds the request; the authority is what refuses it.

    The book already carries the original position's full risk. A delta intent
    asking for more on top takes portfolio heat past the mandate's
    `max_open_stop_risk`, and `RiskAuthority.evaluate` rejects it — which is
    the guarantee that matters, because the proposal layer is advisory and the
    authority is not (INV-AUTH-001).
    """
    mandate = TradingMandate.from_mapping(mandate_dict())
    authority = RiskAuthority(mandate)
    # Existing exposure sized to sit just under the portfolio ceiling.
    open_position = OpenPosition(
        "EURUSD", Direction.LONG, Decimal("2.5"), Decimal("0.00050"),
        eurusd.value_per_price_unit_per_lot, "EUR", "USD",
        "FX-LONDON-BREAKOUT-04", True)
    snap = snapshot(eurusd, open_positions=(open_position,))

    greedy = authority.evaluate(
        _delta_intent(mandate.max_risk_per_trade, eurusd), snap)
    assert greedy.decision is Decision.REJECTED
    assert greedy.reason_code in ("PORTFOLIO_HEAT", "CURRENCY_LEG_EXPOSURE",
                                 "MAX_POSITIONS_PER_INSTRUMENT")
    assert greedy.approved_size == Decimal("0")


def test_a_delta_intent_inside_the_ceiling_is_evaluated_by_the_same_gate(eurusd):
    """An add is not special-cased: it goes through evaluate() like any trade."""
    mandate = TradingMandate.from_mapping(mandate_dict())
    authority = RiskAuthority(mandate)
    snap = snapshot(eurusd)
    decision = authority.evaluate(_delta_intent(Decimal("0.002"), eurusd), snap)
    assert decision.decision in (Decision.APPROVED, Decision.REDUCED)
    assert decision.approved_risk_pct <= mandate.max_risk_per_trade
    assert decision.decision_hash
