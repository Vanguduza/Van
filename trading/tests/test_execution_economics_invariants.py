"""Independent accounting and venue constraints for BE-010 / BE-012 candidates."""
from dataclasses import replace
from decimal import Decimal as D

import pytest

from vati.execution.base import ExecutionReceipt
from vati.execution.tca import compute_tca
from vati.execution.style_selector import LiquidityView, StyleRefused
from vati.execution.policy import ExecutionEvidence, ExecutionPolicyEngine, EVIDENCE_THIN
from vati.execution.policy_templates import PASSIVE, CERTIFIED_DEFAULT
from test_execution_and_exits import BUCKET
from vati.risk.contracts import Direction
from test_rev51_execution_conformal import _contract, _route, _select


def receipt(**changes):
    base = ExecutionReceipt("intent", "decision", "paper", "FILLED", D("1"), D("99"),
        D("100"), D("100"), D("99"), True, 1, 2, spread_at_submit=D("2"))
    return replace(base, **changes)


@pytest.mark.parametrize("direction", [Direction.LONG, Direction.SHORT])
@pytest.mark.parametrize("prices", [("100", "100", "99", "99"), ("100", "102", "103", "104"),
                                      ("100", "98", "101", "97"), ("100", "100", "100", "100")])
def test_tca_equals_direct_signed_fill_cost_without_adding_spread_again(direction, prices):
    decision, arrival, submitted, fill = map(D, prices)
    r = receipt(decision_price=decision, arrival_price=arrival, submitted_price=submitted,
                average_fill=fill, filled_qty=D("0.4"), fees=D("-0.05"))
    cost = compute_tca(r, direction=direction, qty=r.filled_qty, value_per_unit=D("10"), modelled_cost_pct=D("0.01"))
    sign = D(1) if direction is Direction.LONG else D(-1)
    oracle = sign*(fill-decision)*r.filled_qty*D("10")+r.fees
    assert cost.implementation_shortfall == oracle
    assert (cost.delay_cost+cost.submission_cost+cost.slippage)*r.filled_qty*D("10")+r.fees == oracle
    assert cost.spread_cost == D("4"), "spread remains a separate diagnostic"
    assert cost.realised_cost_pct == oracle / (decision*r.filled_qty*D("10"))
    assert cost.reference_notional == decision*r.filled_qty*D("10")
    assert cost.filled_quantity == r.filled_qty and cost.measurement_version == "tca/2.0.0"


def test_tca_partial_fill_cannot_be_valued_using_requested_quantity():
    r = receipt(status="PARTIAL", filled_qty=D("0.4"))
    with pytest.raises(ValueError, match="filled quantity"):
        compute_tca(r, direction=Direction.LONG, qty=D("1"), value_per_unit=D("1"), modelled_cost_pct=D("0.01"))


def test_untyped_direction_cannot_silently_turn_a_buy_into_a_sell():
    with pytest.raises(ValueError, match="direction"):
        compute_tca(receipt(), direction="LONG", qty=D("1"), value_per_unit=D("1"), modelled_cost_pct=D("0.01"))


@pytest.mark.parametrize("field,value", [("average_fill", "NaN"), ("arrival_price", "Infinity"),
    ("decision_price", "0"), ("spread_at_submit", "-1"), ("fees", "NaN"), ("filled_qty", "-1")])
def test_tca_refuses_invalid_economic_inputs(field, value):
    r = receipt(**{field: D(value)})
    with pytest.raises(ValueError):
        compute_tca(r, direction=Direction.LONG, qty=r.filled_qty, value_per_unit=D("1"), modelled_cost_pct=D("0.01"))


@pytest.mark.parametrize("quantity,depth,step,minimum", [("200", "10", "1", "1"),
    ("0.03", "0.01", "0.01", "0.01"), ("1", "0.5", "0.01", "0.01"),
    ("0.05", "0.16", "0.01", "0.03")])
def test_joint_slice_constraints_refuse_infeasible_order_without_raising_participation(quantity, depth, step, minimum):
    route = _route(_contract(volume_min=D(minimum), volume_step=D(step), volume_max=D("1000")))
    with pytest.raises(StyleRefused, match="participation"):
        _select(quantity=D(quantity), liquidity=LiquidityView(displayed_size=D(depth)), route=route)


@pytest.mark.parametrize("quantity,depth", [("0.96", "0.5"), ("0.95", "0.5"),
    ("0.10", "0.16"), ("0.03", "0.08"), ("0.05", "1")])
def test_feasible_slices_all_obey_cap_minimum_step_and_total(quantity, depth):
    style = _select(quantity=D(quantity), liquidity=LiquidityView(displayed_size=D(depth)))
    pieces = [style.slice_quantity]*(style.slices-1)+[style.final_slice_quantity]
    assert sum(pieces) == D(quantity) == style.total_quantity
    assert all(D("0.01") <= p <= D(depth)*D("0.25") and p % D("0.01") == 0 for p in pieces)
    assert style.seal_ok()


def test_expected_cost_uses_complete_sample_mean_instead_of_conditional_medians():
    evidence = ExecutionEvidence()
    for cost in ("0", "0", "99"):
        evidence.observe(filled=True, shortfall=D(cost))
    evidence.observe(filled=False, non_fill_cost=D("1"))
    assert evidence.expected_shortfall_estimate() == D("25"), "a rare expensive fill cannot disappear in the median"


@pytest.mark.parametrize("outcome", [{"filled": True}, {"filled": False},
    {"filled": True, "partial": True, "shortfall": D("0")}])
def test_missing_or_partial_objective_cost_cannot_masquerade_as_free_execution(outcome):
    evidence = ExecutionEvidence()
    evidence.observe(**outcome)
    assert evidence.expected_shortfall_estimate() is None


def test_partial_objective_can_be_scored_only_with_explicit_complete_cost():
    evidence = ExecutionEvidence()
    evidence.observe(filled=True, partial=True, shortfall=D("-1"), objective_cost=D("2.5"))
    assert evidence.expected_shortfall_estimate() == D("2.5")


def test_many_missing_outcomes_cannot_promote_a_template():
    policy = ExecutionPolicyEngine()
    for _ in range(30):
        policy.observe(BUCKET, PASSIVE, filled=True)
    chosen = policy.select(candidate_id="candidate", bucket=BUCKET)
    assert chosen.template_id == CERTIFIED_DEFAULT
    assert chosen.evidence_state == EVIDENCE_THIN and chosen.expected_shortfall is None


def test_urgent_exit_label_cannot_bypass_entry_participation(mandate, eurusd):
    from conftest import mandate_dict
    from test_execution import approved, router, NOW
    from vati.execution import PaperAdapter, RouterError
    from vati.execution.style_selector import Urgency
    from vati.risk import StrategyState, TradingMandate
    m = TradingMandate.from_mapping(mandate_dict(venue="paper", mode="DEMO_TRADER"))
    contract = replace(eurusd, venue="paper")
    i, decision = approved(m, contract, venue="paper", strategy_state=StrategyState.DEMO)
    adapter = PaperAdapter()
    sender, ledger = router(adapter)
    with pytest.raises(RouterError, match="protective-exit urgency"):
        sender.execute(i, decision, m, now_ms=NOW, urgency=Urgency.IMMEDIATE)
    assert not adapter.positions()


def test_infeasible_style_is_an_order_refusal_before_adapter_submission(mandate, eurusd):
    from conftest import mandate_dict
    from test_execution import approved, NOW
    from vati.core import EventKind, Ledger
    from vati.execution import ExecutionRouter, PaperAdapter, ProtectionManager, RouterError
    from vati.execution.policy import ExecutionBucket
    from vati.execution.pretrade import PreTradeControls
    from vati.execution.route_registry import RouteRegistry
    from vati.execution.style_selector import ExecutionStyleSelector
    from vati.risk import KillSwitch, StrategyState, TradingMandate
    m = TradingMandate.from_mapping(mandate_dict(venue="paper", mode="DEMO_TRADER"))
    contract = replace(eurusd, venue="paper")
    i, decision = approved(m, contract, venue="paper", strategy_state=StrategyState.DEMO)
    routes, ledger, adapter = RouteRegistry(), Ledger(), PaperAdapter()
    routes.refresh(account_alias=i.account_alias, adapter_id="paper", contracts={i.symbol: contract}, now_ms=NOW)
    sender = ExecutionRouter(ledger=ledger, adapters={"paper": adapter}, kill_switch=KillSwitch(),
        protection=ProtectionManager(), route_registry=routes, pretrade_controls=PreTradeControls(routes=routes),
        style_selector=ExecutionStyleSelector(), enforce_rev51_controls=True)
    policy = ExecutionPolicyEngine().select(candidate_id="candidate", bucket=ExecutionBucket("paper", i.account_alias,
        i.symbol, "LONDON", "NORMAL", "NONE", "LONG"))
    with pytest.raises(RouterError, match="execution style refused.*participation"):
        sender.execute(i, decision, m, now_ms=NOW, execution_policy_decision=policy,
            liquidity=LiquidityView(displayed_size=D("0.00001")))
    assert ledger.count(EventKind.ORDER_COMMAND) == 0 and not adapter.positions()
