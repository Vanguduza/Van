"""A legitimate risk decision cannot authorize changed order economics."""
from dataclasses import replace
from decimal import Decimal as D

import pytest

from conftest import mandate_dict
from test_execution import approved,NOW
from vati.core import Ledger,EventKind
from vati.execution import ExecutionRouter,PaperAdapter,ProtectionManager,RouterError
from vati.execution.policy import ExecutionPolicyEngine,ExecutionBucket
from vati.execution.pretrade import PreTradeControls
from vati.execution.route_registry import RouteRegistry
from vati.execution.style_selector import ExecutionStyleSelector
from vati.risk import KillSwitch,StrategyState,TradingMandate,Direction


def setup(eurusd,production):
    mandate = TradingMandate.from_mapping(mandate_dict(venue="paper",mode="DEMO_TRADER"))
    contract = replace(eurusd,venue="paper")
    intent,decision = approved(mandate,contract,venue="paper",strategy_state=StrategyState.DEMO)
    ledger,adapter,routes = Ledger(),PaperAdapter(),RouteRegistry()
    routes.refresh(account_alias=intent.account_alias,adapter_id="paper",contracts={intent.symbol:contract},now_ms=NOW)
    router = ExecutionRouter(ledger=ledger,adapters={"paper":adapter},kill_switch=KillSwitch(),protection=ProtectionManager(),
        route_registry=routes,pretrade_controls=PreTradeControls(routes=routes),style_selector=ExecutionStyleSelector(),
        enforce_rev51_controls=production)
    policy = ExecutionPolicyEngine().select(candidate_id="candidate",bucket=ExecutionBucket("paper",intent.account_alias,
        intent.symbol,"LONDON","NORMAL","NONE","LONG"))
    return mandate,intent,decision,router,ledger,adapter,policy


@pytest.mark.parametrize("production", [False,True])
@pytest.mark.parametrize("change", ["stop","account","idempotency","strategy","direction"])
def test_changed_trade_fields_are_refused_before_a_broker_command(eurusd,production,change):
    mandate,intent,decision,router,ledger,adapter,policy = setup(eurusd,production)
    changes = {"stop":{"stop":intent.entry-D("0.02")},"account":{"account_alias":"another-account"},
        "idempotency":{"idempotency_key":"new-key-same-approval"},"strategy":{"strategy_version":"unapproved-revision"},
        "direction":{"direction":Direction.SHORT,"stop":intent.entry+D("0.001")}}
    altered = replace(intent,**changes[change])
    with pytest.raises(RouterError,match="intent|approval"):
        router.execute(altered,decision,mandate,now_ms=NOW,execution_policy_decision=policy)
    assert ledger.count(EventKind.ORDER_COMMAND) == 0 and not adapter.positions()


@pytest.mark.parametrize("production", [False,True])
def test_unchanged_real_risk_approval_still_executes(eurusd,production):
    mandate,intent,decision,router,ledger,adapter,policy = setup(eurusd,production)
    receipt = router.execute(intent,decision,mandate,now_ms=NOW,execution_policy_decision=policy)
    assert receipt.status == "FILLED" and ledger.count(EventKind.ORDER_COMMAND) == 1
    assert adapter.positions() and router.protection.rules


def test_legacy_approval_stays_readable_but_cannot_authorize_a_new_order(eurusd):
    from vati.risk import RiskAuthority
    from vati.execution.router import recompute_decision_hash
    mandate,intent,decision,router,ledger,adapter,policy = setup(eurusd,True)
    legacy = RiskAuthority._seal(replace(decision,intent_hash=None,mandate_hash=None,approval_schema_version=None))
    assert "intent_hash" not in legacy.to_dict() and "approval_schema_version" not in legacy.to_dict()
    assert legacy.decision_hash == recompute_decision_hash(legacy)
    with pytest.raises(RouterError,match="re-evaluation"):
        router.execute(intent,legacy,mandate,now_ms=NOW,execution_policy_decision=policy)
    assert ledger.count(EventKind.ORDER_COMMAND)==0 and not adapter.positions()


def test_pretrade_port_independently_refuses_changed_or_unbound_intent(eurusd):
    from vati.risk import RiskAuthority
    mandate,intent,decision,router,ledger,adapter,policy = setup(eurusd,True)
    altered = replace(intent,stop=intent.entry-D("0.02"))
    result = router.pretrade_controls.check(intent=altered,decision=decision,mark=None,now_ms=NOW)
    assert not result.passed and result.reason_code=="DECISION_INTENT_MISMATCH"
    legacy = RiskAuthority._seal(replace(decision,intent_hash=None,mandate_hash=None,approval_schema_version=None))
    result = router.pretrade_controls.check(intent=intent,decision=legacy,mark=None,now_ms=NOW)
    assert not result.passed and result.reason_code=="DECISION_INTENT_UNBOUND"


def test_serialized_intent_roundtrip_retains_the_exact_binding(eurusd):
    import json
    from vati.risk.serde import intent_from_dict,intent_to_dict,intent_binding_hash
    _,intent,decision,*_ = setup(eurusd,True)
    restored = intent_from_dict(json.loads(json.dumps(intent_to_dict(intent))))
    assert decision.approval_schema_version==2
    assert decision.intent_hash==intent_binding_hash(restored)==intent_binding_hash(intent)


def test_a_tighter_current_mandate_cannot_reuse_an_older_larger_approval(eurusd):
    mandate,intent,decision,router,ledger,adapter,policy = setup(eurusd,True)
    tighter = replace(mandate,max_risk_per_trade=decision.approved_risk_pct/D("10"))
    assert tighter.mandate_id==mandate.mandate_id and tighter.version==mandate.version
    with pytest.raises(RouterError,match="current mandate"):
        router.execute(intent,decision,tighter,now_ms=NOW,execution_policy_decision=policy)
    assert not adapter.positions() and ledger.count(EventKind.ORDER_COMMAND)==0


@pytest.mark.parametrize("failure", ["UNKNOWN", "PARTIAL", "missing_price", "transport_error"])
def test_unconfirmed_stop_with_unknown_flattening_is_not_reported_as_flattened(eurusd,failure):
    from vati.risk.contracts import KillSwitchTrigger
    class MissingStop(PaperAdapter):
        def submit(self,*args,**kwargs):
            return replace(super().submit(*args,**kwargs),protective_stop_confirmed=False).sealed()
        def close(self,position_id,quantity,*,now_ms,reason):
            from vati.execution.base import ExecutionReceipt
            if failure == "transport_error":
                raise TimeoutError("response lost")
            p = self._positions[position_id]
            status = "FILLED" if failure == "missing_price" else failure
            qty = D("1") if failure != "UNKNOWN" else D("0")
            return ExecutionReceipt(p["intent"],"",self.venue,status,qty,None,
                p["entry"],p["entry"],p["entry"],False,now_ms,now_ms,broker_position_id=position_id).sealed()
    mandate,intent,decision,router,ledger,_,policy = setup(eurusd,True)
    adapter = MissingStop()
    router.adapters["paper"] = adapter
    with pytest.raises(RouterError,match="unresolved"):
        router.execute(intent,decision,mandate,now_ms=NOW,execution_policy_decision=policy)
    assert adapter.positions()
    pending = router.exit_journal.unresolved()
    assert len(pending)==1 and pending[0].payload["state"] in {"REQUESTED","UNKNOWN"}
    assert {KillSwitchTrigger.STOP_REJECTED,KillSwitchTrigger.RECONCILIATION_FAILURE} <= router.kill.active
    restored = ExecutionRouter(ledger=ledger,adapters={"paper":adapter},kill_switch=KillSwitch(),protection=ProtectionManager())
    assert restored.exit_journal.unresolved() and KillSwitchTrigger.RECONCILIATION_FAILURE in restored.kill.active
    with pytest.raises(RouterError,match="kill switch"):
        restored.execute(intent,decision,mandate,now_ms=NOW+1)
    assert ledger.count(EventKind.ORDER_COMMAND)==1


def test_v2_initial_risk_cannot_be_joined_to_different_intent_inputs(eurusd):
    from conftest import snapshot
    from vati.core.events import make_event
    from vati.execution.review import initial_risk_from_ledger
    from vati.risk.serde import intent_to_dict,snapshot_to_dict
    mandate,intent,decision,*_ = setup(eurusd,True)
    s = snapshot(replace(eurusd,venue="paper"))
    payload = {"inputs":{"intent":intent_to_dict(intent),"snapshot":snapshot_to_dict(s)},"decision":decision.to_dict()}
    ledger = Ledger()
    def append(target,body):
        target.append(make_event(EventKind.RISK_DECISION,"vati-account-coordinator",body,
            event_time_ms=NOW,received_time_ms=NOW,correlation_id=intent.trade_intent_id))
    append(ledger,payload)
    assert initial_risk_from_ledger(ledger,intent.trade_intent_id).amount==s.equity*decision.approved_risk_pct
    payload["inputs"]["intent"]["stop"] = str(intent.entry-D("0.02"))
    altered = Ledger()
    append(altered,payload)
    assert initial_risk_from_ledger(altered,intent.trade_intent_id) is None


def test_historical_replay_never_silently_upgrades_a_legacy_approval(eurusd):
    from vati.core.events import make_event
    from vati.risk import RiskAuthority
    _,_,decision,_,ledger,*_ = setup(eurusd,True)
    legacy = RiskAuthority._seal(replace(decision,intent_hash=None,mandate_hash=None,approval_schema_version=None))
    event = make_event(EventKind.RISK_DECISION,"vati-account-coordinator",{"inputs":{"historical":True},"decision":legacy.to_dict()},
        event_time_ms=NOW,received_time_ms=NOW,correlation_id=legacy.trade_intent_id)
    ledger.append(event)
    original_export = list(ledger.iter(EventKind.RISK_DECISION))
    # Byte replay requires the original decision representation/evaluator.
    # A new binding must never be treated as if it existed at the old decision.
    assert not ledger.replay_decisions(lambda _:decision.to_dict()).ok
    assert ledger.replay_decisions(lambda _:legacy.to_dict()).ok
    assert list(ledger.iter(EventKind.RISK_DECISION))==original_export
    assert original_export[0].hash==event.hash
