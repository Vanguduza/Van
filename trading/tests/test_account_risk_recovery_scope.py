"""Real account/cycle recovery must never combine different account histories."""
from decimal import Decimal as D
from dataclasses import replace

import pytest

from vati.core import EventKind,Ledger,make_event
from vati.risk.contracts import KillSwitchTrigger
from vati.risk.lockouts import ACCOUNT_SCOPE,DRAWDOWN_RESUME_EVENT,RESET_EVENT
from vati.risk.history_scope import risk_history_for_account
from test_recoverable_lockouts import _cycle

NOW=1_800_000_000_000
STRATEGY="FX-TREND-PULLBACK-01"


def record(ledger,kind,payload,corr="",now=NOW):
    event=make_event(kind,"vati-cycle",payload,event_time_ms=now,received_time_ms=now,correlation_id=corr)
    ledger.append(event)
    return event


def losses(ledger,account,n=4):
    for n in range(n):
        record(ledger,EventKind.TRADE_REVIEW,{"account_alias":account,"strategy_id":STRATEGY,"pnl":"-10"},f"{account}-{n}",NOW+n)


def test_another_accounts_win_cannot_reset_the_restarted_accounts_losses(eurusd):
    ledger=Ledger()
    losses(ledger,"fx_primary",n=3)
    record(ledger,EventKind.TRADE_REVIEW,{"account_alias":"other","strategy_id":STRATEGY,"pnl":"12"},"other-win",NOW+10)
    cycle=_cycle(eurusd,ledger)
    assert cycle.streaks.verdict(STRATEGY,NOW+11).losses==3


def test_another_accounts_losses_cannot_cool_down_this_account(eurusd):
    ledger=Ledger()
    losses(ledger,"other")
    cycle=_cycle(eurusd,ledger)
    assert not cycle.streaks.verdict(STRATEGY,NOW+10).lock


def test_another_accounts_owner_resume_cannot_rebaseline_this_accounts_peak(eurusd):
    ledger=Ledger()
    for account,peak in (("fx_primary","10000"),("other","2000")):
        record(ledger,EventKind.SESSION,{"account_alias":account,"event":DRAWDOWN_RESUME_EVENT,"new_peak_equity":peak},account)
    cycle=_cycle(eurusd,ledger)
    assert cycle.peak_equity==D("10000")


def test_another_accounts_reset_cannot_clear_this_accounts_probation(eurusd):
    ledger=Ledger()
    losses(ledger,"fx_primary")
    for scope in (STRATEGY,ACCOUNT_SCOPE):
        record(ledger,EventKind.SESSION,{"account_alias":"other","event":RESET_EVENT,"scope":scope})
    cycle=_cycle(eurusd,ledger)
    assert cycle.streaks.verdict(STRATEGY,NOW+86_400_100).risk_multiplier==D("0.5")


@pytest.mark.parametrize("kind,payload", [
    (EventKind.TRADE_REVIEW,{"strategy_id":STRATEGY,"pnl":"12"}),
    (EventKind.SESSION,{"event":RESET_EVENT,"scope":ACCOUNT_SCOPE}),
    (EventKind.SESSION,{"event":DRAWDOWN_RESUME_EVENT,"new_peak_equity":"100"}),
    (EventKind.RISK_DECISION,{"inputs":{"snapshot":{"peak_equity":"100"}}}),
])
def test_unbound_historical_financial_records_never_inherit_the_configured_account(eurusd,kind,payload):
    ledger=Ledger()
    original=record(ledger,kind,payload)
    cycle=_cycle(eurusd,ledger)
    assert KillSwitchTrigger.RECONCILIATION_FAILURE in cycle.kill.active
    assert "unbound" in cycle.streaks.verdict(STRATEGY,NOW).lock
    cycle.streaks.reset(STRATEGY)
    cycle.streaks.reset(ACCOUNT_SCOPE)
    cycle.streaks.on_close(STRATEGY,D("1000"),NOW)
    assert cycle.streaks.verdict(STRATEGY,NOW).lock
    assert cycle.snapshot(now_ms=NOW,quote_age_ms=0).loss_streak_lock
    cycle.mark(D("1.0"),D("1.00001"),now_ms=NOW)
    assert next(ledger.iter(kind)).hash==original.hash


def test_legacy_review_uses_exact_native_order_identity_not_current_configuration(eurusd):
    ledger=Ledger()
    command=make_event(EventKind.ORDER_COMMAND,"vati-execution-router",
        {"trade_intent_id":"historic-trade","account_alias":"fx_primary","idempotency_key":"historic-key"},
        event_time_ms=NOW,received_time_ms=NOW,correlation_id="historic-trade")
    ledger.append(command)
    record(ledger,EventKind.TRADE_REVIEW,{"trade_intent_id":"historic-trade","strategy_id":STRATEGY,"pnl":"-10"},"historic-trade")
    cycle=_cycle(eurusd,ledger)
    assert not cycle.kill.halted
    assert cycle.streaks.verdict(STRATEGY,NOW).losses==1
    other=risk_history_for_account(ledger.iter(),"other")
    assert not other.events and not other.unresolved_refs


def test_a_trade_id_reused_by_two_accounts_is_ambiguous_even_without_reviews():
    ledger=Ledger()
    for account in ("fx_primary","other"):
        ledger.append(make_event(EventKind.ORDER_COMMAND,"vati-execution-router",
            {"trade_intent_id":"shared-id","account_alias":account,"idempotency_key":account},
            event_time_ms=NOW,received_time_ms=NOW,correlation_id="shared-id"))
    assert len(risk_history_for_account(ledger.iter(),"fx_primary").unresolved_refs)==2
    assert len(risk_history_for_account(ledger.iter(),"other").unresolved_refs)==2


@pytest.mark.parametrize("change", ["producer","seal","identity","review_identity"])
def test_invalid_ownership_evidence_cannot_select_a_financial_fact(change):
    order=make_event(EventKind.ORDER_COMMAND,"vati-execution-router",
        {"trade_intent_id":"trade","account_alias":"fx_primary"},event_time_ms=NOW,received_time_ms=NOW,correlation_id="trade")
    review=make_event(EventKind.TRADE_REVIEW,"vati-cycle",{"trade_intent_id":"trade","strategy_id":STRATEGY,"pnl":"-10"},
        event_time_ms=NOW,received_time_ms=NOW,correlation_id="trade")
    if change=="producer":
        order=make_event(EventKind.ORDER_COMMAND,"model-advisory",order.payload,event_time_ms=NOW,received_time_ms=NOW,correlation_id="trade")
    elif change=="seal":
        order=replace(order,hash="0"*64)
    elif change=="identity":
        order=make_event(EventKind.ORDER_COMMAND,"vati-execution-router",order.payload,event_time_ms=NOW,received_time_ms=NOW,correlation_id="another-trade")
    else:
        review=make_event(EventKind.TRADE_REVIEW,"vati-cycle",review.payload|{"trade_intent_id":"another-trade"},event_time_ms=NOW,received_time_ms=NOW,correlation_id="trade")
    result=risk_history_for_account([order,review],"fx_primary")
    assert result.unresolved_refs and not result.events


def test_first_real_snapshot_restores_only_this_accounts_daily_and_weekly_loss_baselines(eurusd):
    ledger=Ledger()
    for account,peak,day,week in (("fx_primary","12345","12000","12100"),("other","1000","900","950")):
        record(ledger,EventKind.RISK_DECISION,{"inputs":{"intent":{"account_alias":account,"trade_intent_id":account},
            "snapshot":{"peak_equity":peak,"day_start_equity":day,"week_start_equity":week}}},account)
    cycle=_cycle(eurusd,ledger)
    snapshot=cycle.snapshot(now_ms=NOW+1000,quote_age_ms=0,strategy_id=STRATEGY)
    assert (snapshot.peak_equity,snapshot.day_start_equity,snapshot.week_start_equity)==(D("12345"),D("12000"),D("12100"))
    assert not cycle.kill.halted


def test_actual_close_records_account_inside_the_review_seal(eurusd):
    from vati.core import canonical_hash
    ledger=Ledger()
    cycle=_cycle(eurusd,ledger)
    from vati.risk import Direction
    cycle._entries["closed"]={"entry":D("1.1"),"stop":D("1.09"),"direction":Direction.LONG,
        "strategy_id":STRATEGY,"cost_pct":D("0")}
    cycle.adapter.closed.append({"intent":"closed","pnl":D("-10")})
    cycle._on_close("closed",D("1.09"),"VENUE_STOP",NOW)
    review=next(ledger.iter(EventKind.TRADE_REVIEW)).payload
    assert review["account_alias"]=="fx_primary"
    assert canonical_hash({k:v for k,v in review.items() if k!="artifact_hash"})==review["artifact_hash"]
    restored=_cycle(eurusd,ledger)
    assert not restored.kill.halted and restored.streaks.verdict(STRATEGY,NOW+1).losses==1


@pytest.mark.parametrize("payload", [
    [], {"inputs":[]}, {"inputs":{"intent":[]}}, {"inputs":{"intent":{"account_alias":[],"trade_intent_id":"trade"}}},
])
def test_malformed_financial_identity_remains_unresolved(payload):
    event=make_event(EventKind.RISK_DECISION,"vati-cycle",payload,event_time_ms=NOW,received_time_ms=NOW,correlation_id="trade")
    assert risk_history_for_account([event],"fx_primary").unresolved_refs==(event.hash,)


@pytest.mark.parametrize("pnl", [None,"NaN","Infinity","-Infinity","not-money"])
def test_invalid_review_pnl_cannot_reset_recovered_losses_or_crash_protection(eurusd,pnl):
    ledger=Ledger()
    losses(ledger,"fx_primary",n=3)
    record(ledger,EventKind.TRADE_REVIEW,{"account_alias":"fx_primary","strategy_id":STRATEGY,"pnl":pnl},"bad-review")
    cycle=_cycle(eurusd,ledger)
    assert cycle.kill.halted and cycle.streaks.recovery_issue
    cycle.mark(D("1.0"),D("1.0001"),now_ms=NOW+1000)


def test_ambiguous_scope_keeps_existing_venue_protection_running(eurusd):
    from test_account_lifecycle import _command
    ledger=Ledger()
    record(ledger,EventKind.TRADE_REVIEW,{"strategy_id":STRATEGY,"pnl":"-10"})
    cycle=_cycle(eurusd,ledger)
    # Seed the venue's already-existing protected holding; this is not a new
    # autonomous send through the halted runtime.
    command=replace(_command("protected-existing"),account_alias=cycle.cfg.account_alias).sealed()
    cycle.adapter.submit(command,now_ms=NOW)
    assert cycle.adapter.positions() and cycle.kill.halted
    cycle.mark(command.protective_stop-D("0.001"),command.protective_stop,now_ms=NOW+1000)
    assert not cycle.adapter.positions() and cycle.adapter.closed
    assert cycle.kill.halted and ledger.count(EventKind.ORDER_COMMAND)==0


def test_real_service_start_exposes_the_scope_issue_to_owner_readback(eurusd,tmp_path):
    import json
    from types import SimpleNamespace
    from vati.app.portfolio import account_states
    from vati.app.runner import SessionRunner
    from vati.app.service import SessionService
    ledger=Ledger()
    record(ledger,EventKind.TRADE_REVIEW,{"strategy_id":STRATEGY,"pnl":"-10"})
    cycle=_cycle(eurusd,ledger)
    cfg=SimpleNamespace(account_alias="fx_primary",symbol="EURUSD",heartbeat_path=str(tmp_path/"heartbeat.json"))
    service=SessionService(cfg,lambda now:[],clock=lambda:NOW)
    service.runner=SessionRunner(cycle)
    service.start()
    heartbeat=json.loads((tmp_path/"heartbeat.json").read_text())
    assert not heartbeat["permit_new_orders"] and "unbound" in heartbeat["risk_history_issue"]
    accounts=account_states(ledger,[])
    assert len(accounts)==1 and "unbound" in accounts[0]["risk_history_issue"]


def test_account_runtime_adjustment_probe_retains_scope_refusal_without_a_strategy_id(eurusd):
    from types import SimpleNamespace
    from vati.app.account_service import AccountCoordinatorService
    ledger=Ledger()
    record(ledger,EventKind.TRADE_REVIEW,{"strategy_id":STRATEGY,"pnl":"-10"})
    cycle=_cycle(eurusd,ledger)
    service=AccountCoordinatorService(SimpleNamespace(account_alias="fx_primary",max_quote_age_ms=5000),clock=lambda:NOW)
    service.adapter=cycle.adapter
    service.account=SimpleNamespace(alias="fx_primary")
    service._ledger=ledger
    service.contracts={"EURUSD":cycle.cfg.contract}
    service.evaluators={"EURUSD":SimpleNamespace(last_state=None)}
    service.lifecycle=SimpleNamespace(streaks=cycle.streaks,consecutive_losses=0,
        preservation_blocks_new_risk=False,preservation_reason="")
    # The ongoing ambiguity is also a snapshot refusal, even if a separately
    # reconstructed kill switch is currently clear. The probe omits strategy_id.
    assert not service.kill.halted
    snapshot=service._snapshot_for_symbol("EURUSD")
    assert snapshot is not None and "unbound" in snapshot.loss_streak_lock
