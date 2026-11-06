"""Snapshot approval cannot transfer authority past the actual dispatch lifetime."""
from contextlib import contextmanager
from dataclasses import replace

import pytest

from conftest import NOW,intent,mandate_dict,snapshot
from vati.core import EventKind,Ledger
from vati.execution import ExecutionRouter,PaperAdapter,ProtectionManager
from vati.risk import Decision,KillSwitch,RiskAuthority,StrategyState,TradingMandate


def flow(contract,**overrides):
    m=TradingMandate.from_mapping(mandate_dict(venue='paper',mode='DEMO_TRADER',**overrides))
    trade=intent(venue='paper',strategy_state=StrategyState.DEMO);native=snapshot(replace(contract,venue='paper'))
    return m,trade,native


def sender(m):
    paper=PaperAdapter(account_alias=m.account_alias);ledger=Ledger()
    router=ExecutionRouter(ledger=ledger,adapters={'paper':paper},kill_switch=KillSwitch(),protection=ProtectionManager())
    return paper,ledger,router


def test_a_future_signed_policy_cannot_approve_current_risk(eurusd):
    m,trade,native=flow(eurusd,signed_at_unix=NOW+86400,expires_at_unix=NOW+2*86400)
    decision=RiskAuthority(m).evaluate_safe(trade,native)
    assert decision.decision is Decision.REJECTED and decision.reason_code=='MANDATE_NOT_YET_VALID'


@pytest.mark.parametrize('when',['before-signing','at-expiry'])
def test_a_genuine_snapshot_approval_cannot_send_outside_its_mandate_lifetime(eurusd,when):
    m,trade,native=flow(eurusd);decision=RiskAuthority(m).evaluate_safe(trade,native)
    assert decision.decision in {Decision.APPROVED,Decision.REDUCED}
    paper,ledger,router=sender(m)
    now=m.signed_at_unix*1000-1 if when=='before-signing' else m.expires_at_unix*1000
    try:receipt=router.execute(trade,decision,m,now_ms=now)
    except Exception as exc:
        from vati.execution import RouterError
        assert isinstance(exc,RouterError) and 'mandate' in str(exc).lower()
        assert ledger.count(EventKind.ORDER_COMMAND)==0 and not paper.positions();return
    assert receipt.status=='FILLED' and paper.positions()
    pytest.fail('an out-of-lifetime approval reached the actual paper sender')


def test_expiry_while_acquiring_native_submission_authority_is_rechecked_before_effect(eurusd):
    m,trade,native=flow(eurusd);decision=RiskAuthority(m).evaluate_safe(trade,native)
    paper,ledger,router=sender(m);clock={'now':NOW*1000};router.clock=lambda:clock['now']
    @contextmanager
    def guard(epoch):
        clock['now']=m.expires_at_unix*1000
        yield True
    router.lease_submission_guard=guard
    try:receipt=router.execute(trade,decision,m,now_ms=NOW*1000)
    except Exception as exc:
        from vati.execution import RouterError
        assert isinstance(exc,RouterError) and 'mandate' in str(exc).lower()
        assert ledger.count(EventKind.ORDER_COMMAND)==0 and not paper.positions();return
    assert receipt.status=='FILLED' and paper.positions()
    pytest.fail('expiry during native guard acquisition still reached the actual sender')


@pytest.mark.parametrize('boundary',['start','last-millisecond'])
def test_current_grant_boundaries_still_reach_the_real_sender(eurusd,boundary):
    m,trade,native=flow(eurusd);decision=RiskAuthority(m).evaluate_safe(trade,native)
    paper,ledger,router=sender(m)
    now=m.signed_at_unix*1000 if boundary=='start' else m.expires_at_unix*1000-1
    receipt=router.execute(trade,decision,m,now_ms=now)
    assert receipt.status=='FILLED' and paper.positions() and ledger.count(EventKind.ORDER_COMMAND)==1


def test_dispatch_receipt_and_native_command_keep_the_observed_send_and_original_decision_times(eurusd):
    m,trade,native=flow(eurusd);decision=RiskAuthority(m).evaluate_safe(trade,native)
    paper,ledger,router=sender(m);router.clock=lambda:NOW*1000+25
    receipt=router.execute(trade,decision,m,now_ms=NOW*1000)
    command=next(ledger.iter(EventKind.ORDER_COMMAND))
    assert receipt.received_time_unix_ms==NOW*1000+25
    assert command.event_time_ms==command.received_time_ms==NOW*1000+25
    assert command.decision_time_ms==NOW*1000


@pytest.mark.parametrize('invalid',[None,True,NOW*1000-1])
def test_unknown_or_backward_current_clock_cannot_send(eurusd,invalid):
    from vati.execution import RouterError
    m,trade,native=flow(eurusd);decision=RiskAuthority(m).evaluate_safe(trade,native)
    paper,ledger,router=sender(m);router.clock=lambda:invalid
    with pytest.raises(RouterError,match='clock'):router.execute(trade,decision,m,now_ms=NOW*1000)
    assert not paper.positions() and ledger.count(EventKind.ORDER_COMMAND)==0


def test_refusal_before_dispatch_does_not_consume_the_intent_and_expiry_keeps_protective_exit_available(eurusd):
    from vati.execution import RouterError
    m,trade,native=flow(eurusd);decision=RiskAuthority(m).evaluate_safe(trade,native)
    paper,ledger,router=sender(m);clock={'now':NOW*1000};router.clock=lambda:clock['now']
    @contextmanager
    def guard(epoch):
        clock['now']=True
        yield True
    router.lease_submission_guard=guard
    with pytest.raises(RouterError,match='clock'):router.execute(trade,decision,m,now_ms=NOW*1000)
    assert not paper.positions() and ledger.count(EventKind.ORDER_COMMAND)==0
    router.lease_submission_guard=None;clock['now']=NOW*1000
    receipt=router.execute(trade,decision,m,now_ms=NOW*1000)
    assert receipt.status=='FILLED'
    clock['now']=m.expires_at_unix*1000
    closed=router.apply_preservation('paper',position_id=receipt.broker_position_id,
        trade_intent_id=trade.trade_intent_id,action='FULL_CLOSE',reason='owner-reduction',now_ms=clock['now'])
    assert closed.status=='FILLED' and not paper.positions()


def test_actual_single_symbol_factory_uses_its_current_clock_after_native_guard_acquisition(tmp_path,eurusd,monkeypatch):
    from test_backtest_runner_cli import synthetic_bars
    from test_single_session_lease import config
    from vati.app.service import SessionService
    bars=synthetic_bars();clock={'now':bars[100].end_ms};cfg=config(tmp_path,eurusd)
    service=SessionService(cfg,lambda now:[b for b in bars if b.end_ms<=now],clock=lambda:clock['now']).build()
    native_guard=service.lease.submission_guard;entered=[]
    @contextmanager
    def after_native_guard(epoch,*,now_ms):
        with native_guard(epoch,now_ms=now_ms) as valid:
            assert valid
            entered.append(epoch);clock['now']=service.runner.cycle.mandate.expires_at_unix*1000
            yield valid
    monkeypatch.setattr(service.lease,'submission_guard',after_native_guard)
    try:
        service.start()
        for bar in bars[101:]:
            clock['now']=bar.end_ms+1000
            result=service.step_once()
            if entered:
                assert result=='ROUTER_REFUSED';break
        assert entered and not service.adapter.positions()
        assert service._ledger.count(EventKind.ORDER_COMMAND)==0
        refusals=[e.payload['router_refused'] for e in service._ledger.iter(EventKind.SESSION) if 'router_refused' in e.payload]
        assert refusals and 'mandate' in refusals[-1]
    finally:service.close();service._ledger.close()


def test_actual_book_factory_rechecks_its_own_clock_before_the_native_sender(tmp_path,eurusd,monkeypatch):
    import os
    import uuid
    if not os.environ.get('VATI_TEST_PG_DSN'):pytest.skip('requires isolated PostgreSQL fixture')
    from test_single_session_lease import config
    from vati.app.account_service import AccountCoordinatorService
    from vati.execution.policy import ExecutionBucket,ExecutionPolicyEngine
    from vati.execution.pretrade import MarketReference
    from vati.execution.style_selector import LiquidityView
    from vati.execution import RouterError
    from vati.risk.serde import contract_to_dict
    from vati.accounts import AccountRegistry
    from conftest import historical_mandate_dict
    cfg=config(tmp_path,eurusd,ledger=os.environ['VATI_TEST_PG_DSN']);cfg.lake_root=str(tmp_path/'lake')
    # The real lease table is shared by the suite. A different virtual clock
    # must use its own account, preserving every earlier lease and epoch.
    registry=AccountRegistry(cfg.registry_path);alias='dispatch_book_'+uuid.uuid4().hex[:12]
    registry.add(replace(registry.get(cfg.account_alias),alias=alias));cfg.account_alias=alias
    cfg.mandate=historical_mandate_dict(venue='paper',mode='DEMO_TRADER',account_alias=alias,
        allowed_strategies=['FX-TREND-PULLBACK-01'])
    other=replace(eurusd,symbol='GBPUSD',base_currency='GBP')
    cfg.instruments=[{'symbol':'GBPUSD','base':'GBP','quote':'USD','contract':contract_to_dict(other)}]
    clock={'now':cfg.mandate['expires_at_unix']*1000-1000}
    service=AccountCoordinatorService(cfg,clock=lambda:clock['now']).build()
    entered=[];native_guard=service.lease.submission_guard
    @contextmanager
    def after_native_guard(epoch,*,now_ms):
        with native_guard(epoch,now_ms=now_ms) as valid:
            assert valid
            entered.append(epoch);clock['now']=cfg.mandate['expires_at_unix']*1000
            yield valid
    monkeypatch.setattr(service.lease,'submission_guard',after_native_guard)
    try:
        service.start();m=TradingMandate.from_mapping(cfg.mandate)
        contract=replace(eurusd,venue='paper')
        trade=intent(account_alias=cfg.account_alias,venue='paper',strategy_state=StrategyState.DEMO,
            strategy_id='FX-TREND-PULLBACK-01')
        native=replace(snapshot(contract),account_alias=cfg.account_alias,now_unix=clock['now']//1000)
        decision=RiskAuthority(m).evaluate_safe(trade,native)
        assert decision.decision in {Decision.APPROVED,Decision.REDUCED}
        service.routes.refresh(account_alias=cfg.account_alias,adapter_id='paper',contracts={'EURUSD':contract},now_ms=clock['now'])
        policy=ExecutionPolicyEngine().select(candidate_id=trade.trade_intent_id,
            bucket=ExecutionBucket('paper',cfg.account_alias,'EURUSD','LONDON','NORMAL','NONE','LONG'))
        with pytest.raises(RouterError,match='mandate'):
            service.router.execute(trade,decision,m,now_ms=clock['now'],lease_epoch=service.lease.epoch,
                execution_policy_decision=policy,market_reference=MarketReference(trade.entry,0),liquidity=LiquidityView())
        assert entered and not service.adapter.positions() and service._ledger.count(EventKind.ORDER_COMMAND)==0
    finally:
        service.lease.release(now_ms=clock['now']);service._lease_store.close();service._ledger.close()
