"""Price-unit attribution must agree with the account-currency trade result."""
from decimal import Decimal as D
from types import SimpleNamespace

import pytest

from vati.app.trade_lifecycle import AccountTradeLifecycle
from vati.cognition.attribution import AttributionEngine, AttributionError, TradeFacts
from vati.core.events import EventKind
from vati.core.ledger import Ledger
from vati.execution.paper import PaperAdapter
from vati.execution.protection import ProtectionManager
from vati.risk.contracts import Direction


def test_actual_fx_close_produces_attribution_in_the_same_currency_as_review(eurusd):
    ledger = Ledger()
    lifecycle = AccountTradeLifecycle(ledger=ledger, adapter=PaperAdapter(), router=SimpleNamespace(),
        protection=ProtectionManager(), contracts={"EURUSD": eurusd}, engines_by_symbol={},
        modelled_costs={"EURUSD": D("0.0001")})
    lifecycle.entries["scaled-fx"] = {"trade_intent_id": "scaled-fx", "symbol": "EURUSD",
        "strategy_id": "FX-TEST", "direction": Direction.LONG, "quantity": D("0.1"),
        "entry": D("1.1001"), "decision_price": D("1.1000"), "stop": D("1.0991"),
        "fees": D("0.25"), "opened_ms": 1}
    lifecycle._on_close("scaled-fx", D("1.1010"), "TARGET", 2)
    review = next(ledger.iter(EventKind.TRADE_REVIEW)).payload
    actual = next(ledger.iter(EventKind.PNL_ATTRIBUTION)).payload
    assert D(review["pnl"]) == D("8.75")
    assert D(actual["realised"]["money"]) == D("8.75")
    assert D(actual["buckets"]["edge"]["money"]) == D("10")
    assert D(actual["buckets"]["execution"]["money"]) == D("-1")
    assert D(actual["buckets"]["cost"]["money"]) == D("-0.25")
    assert actual["dominant_bucket"] == "edge"
    assert D(actual["contract_value_per_price_unit"]) == D("100000")
    assert actual["account_currency"] == "USD"
    assert actual["explanation_basis"] == "DESCRIPTIVE_PRICE_DECOMPOSITION_NOT_CAUSAL_PROOF"


@pytest.mark.parametrize("direction,exit_price,expected", [(Direction.LONG, "1.1010", "8.75"),
    (Direction.SHORT, "1.0992", "8.75")])
def test_contract_scale_and_fee_units_are_preserved(direction, exit_price, expected):
    facts = TradeFacts(trade_intent_id="fx", symbol="EURUSD", strategy_id="test", direction=direction,
        quantity=D("0.1"), decision_price=D("1.1000"), fill_price=D("1.1001"), exit_price=D(exit_price),
        money_risk=D("10"), costs=D("0.25"), contract_value_per_price_unit=D("100000"), account_currency="USD")
    result = AttributionEngine().attribute(facts)
    assert result.realised_money == D(expected)
    assert sum((result.edge_money, result.execution_money, result.cost_money, result.carry_money)) == D(expected)


@pytest.mark.parametrize("bad", [D("0"), D("-1"), D("NaN"), D("Infinity")])
def test_invalid_contract_scale_cannot_create_a_learning_attribution(bad):
    with pytest.raises(AttributionError):
        TradeFacts(trade_intent_id="bad", symbol="EURUSD", strategy_id="test", direction=Direction.LONG,
            quantity=D("0.1"), decision_price=D("1.1"), fill_price=D("1.1"), exit_price=D("1.2"),
            money_risk=D("10"), contract_value_per_price_unit=bad)


def test_unreconciled_net_result_is_not_hidden_in_an_accounting_bucket():
    facts = TradeFacts(trade_intent_id="unreconciled", symbol="EURUSD", strategy_id="test", direction=Direction.LONG,
        quantity=D("0.1"), decision_price=D("1.1000"), fill_price=D("1.1001"), exit_price=D("1.1010"),
        money_risk=D("10"), costs=D("0.25"), contract_value_per_price_unit=D("100000"), reported_net_pnl=D("8"))
    ledger = Ledger()
    with pytest.raises(AttributionError, match="reconcile"):
        AttributionEngine(ledger=ledger).attribute(facts)
    assert ledger.count(EventKind.PNL_ATTRIBUTION) == 0


def test_net_loss_cannot_teach_a_positive_return_multiple():
    from vati.execution.review import review_trade
    review = review_trade(trade_intent_id="fees-exceed-price-profit", strategy_id="test", entry=D("100"),
        exit_price=D("101"), stop=D("90"), direction_long=True, pnl=D("-1"), thesis_correct=False,
        process_ok=True, initial_money_risk=D("10"), initial_risk_evidence_ref="risk-decision://source")
    assert review.r_multiple == D("-0.10")
    assert review.r_basis == "NET_PNL_OVER_APPROVED_MONEY_RISK"


def test_initial_risk_is_bound_to_the_actual_decision_snapshot(mandate, eurusd):
    from conftest import intent, snapshot, NOW
    from vati.core.events import make_event
    from vati.execution.review import initial_risk_from_ledger
    from vati.risk import RiskAuthority
    from vati.risk.serde import intent_to_dict, snapshot_to_dict
    i, s = intent(trade_intent_id="initial-risk"), snapshot(eurusd)
    decision = RiskAuthority(mandate).evaluate(i, s)
    ledger = Ledger()
    payload = {"inputs": {"intent": intent_to_dict(i), "snapshot": snapshot_to_dict(s)}, "decision": decision.to_dict()}
    event = make_event(EventKind.RISK_DECISION, "vati-account-coordinator", payload,
        event_time_ms=NOW*1000, received_time_ms=NOW*1000, correlation_id=i.trade_intent_id)
    ledger.append(event)
    result = initial_risk_from_ledger(ledger, i.trade_intent_id, available_cutoff_ms=NOW*1000)
    assert result.amount == s.equity*decision.approved_risk_pct
    assert result.evidence_ref == "risk-decision://"+event.hash
    assert initial_risk_from_ledger(ledger, i.trade_intent_id, available_cutoff_ms=NOW*1000-1) is None
    # The ledger row is freshly sealed, but the changed snapshot is no longer
    # the snapshot the original risk authority bound. Hash-chain validity alone
    # cannot authorize a new normalization denominator.
    payload["inputs"]["snapshot"]["equity"] = "999999"
    bad = Ledger()
    bad.append(make_event(EventKind.RISK_DECISION, "vati-account-coordinator", payload,
        event_time_ms=NOW*1000, received_time_ms=NOW*1000, correlation_id=i.trade_intent_id))
    assert initial_risk_from_ledger(bad, i.trade_intent_id) is None


def test_actual_close_uses_frozen_money_risk_after_stop_moves_and_fees_reverse_price_profit(mandate, eurusd):
    from conftest import intent, snapshot, NOW
    from vati.core.events import make_event
    from vati.risk import RiskAuthority
    from vati.risk.serde import intent_to_dict, snapshot_to_dict
    i, s = intent(trade_intent_id="net-risk-close"), snapshot(eurusd)
    decision = RiskAuthority(mandate).evaluate(i, s)
    assert decision.approved_size > 0
    ledger = Ledger()
    event = make_event(EventKind.RISK_DECISION, "vati-account-coordinator",
        {"inputs": {"intent": intent_to_dict(i), "snapshot": snapshot_to_dict(s)}, "decision": decision.to_dict()},
        event_time_ms=NOW*1000, received_time_ms=NOW*1000, correlation_id=i.trade_intent_id)
    ledger.append(event)
    lifecycle = AccountTradeLifecycle(ledger=ledger, adapter=PaperAdapter(), router=SimpleNamespace(),
        protection=ProtectionManager(), contracts={"EURUSD": eurusd}, engines_by_symbol={}, modelled_costs={})
    lifecycle.entries[i.trade_intent_id] = {"trade_intent_id": i.trade_intent_id, "symbol": "EURUSD",
        "strategy_id": i.strategy_id, "direction": Direction.LONG, "quantity": decision.approved_size,
        "entry": i.entry, "decision_price": i.entry, "stop": i.entry,  # active protection moved to break-even
        "fees": D("50"), "opened_ms": NOW*1000+1}
    lifecycle._on_close(i.trade_intent_id, i.entry+D("0.0001"), "TARGET", NOW*1000+2)
    review = next(ledger.iter(EventKind.TRADE_REVIEW)).payload
    net = D("0.0001")*decision.approved_size*D("100000")-D("50")
    risk = s.equity*decision.approved_risk_pct
    assert D(review["pnl"]) == net < 0
    assert D(review["r_multiple"]) == (net/risk).quantize(D("0.01")) < 0
    assert review["r_basis"] == "NET_PNL_OVER_APPROVED_MONEY_RISK"
    assert review["initial_risk_evidence_ref"] == "risk-decision://"+event.hash
    assert review["thesis_evidence_basis"] == "PNL_SIGN_PROXY_NOT_SETUP_VALIDATION"
    assert lifecycle.consecutive_losses == 1


def test_unreconciled_explanation_does_not_block_recording_an_actual_close(eurusd):
    ledger, adapter = Ledger(), PaperAdapter()
    adapter.closed.append({"intent": "closed", "pnl": D("8"), "pnl_basis": "NET_REPORTED"})
    lifecycle = AccountTradeLifecycle(ledger=ledger, adapter=adapter, router=SimpleNamespace(),
        protection=ProtectionManager(), contracts={"EURUSD": eurusd}, engines_by_symbol={}, modelled_costs={})
    lifecycle.entries["closed"] = {"trade_intent_id": "closed", "symbol": "EURUSD", "strategy_id": "test",
        "direction": Direction.LONG, "quantity": D("0.1"), "entry": D("1.1001"),
        "decision_price": D("1.1"), "stop": D("1.0991"), "fees": D("0.25"), "opened_ms": 1}
    lifecycle._on_close("closed", D("1.1010"), "TARGET", 2)
    assert "closed" not in lifecycle.entries
    assert ledger.count(EventKind.TRADE_REVIEW) == 1 and ledger.count(EventKind.PNL_ATTRIBUTION) == 0
    assert any(e.payload.get("event") == "PNL_ATTRIBUTION_UNRECONCILED" for e in ledger.iter(EventKind.SESSION))


def test_unresolved_financial_outcome_cannot_become_a_win_loss_or_lesson():
    from vati.cognition.attribution import DecisionQualityInputs, DecisionQualityLedger
    from vati.learning.episodes import Environment, lesson_from_verdict
    inputs = DecisionQualityInputs(trade_intent_id="unknown", strategy_id="test",
        thesis_sealed=True, thesis_falsifiable=True)
    verdict = DecisionQualityLedger().record(inputs, symbol="EURUSD", r_multiple=D("0"),
        now_ms=1, outcome_known=False)
    body = verdict.body()
    assert body["outcome_quality"] == "UNKNOWN_OUTCOME" and body["r_multiple"] is None
    assert not body["is_lucky"] and not body["is_unlucky"]
    with pytest.raises(ValueError, match="unresolved"):
        lesson_from_verdict(verdict, symbol="EURUSD", regime="NORMAL", session="LONDON", environment=Environment.LIVE, now_ms=1)
