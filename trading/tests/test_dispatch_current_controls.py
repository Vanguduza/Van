"""Real approval and sender: initial checks may expire while acquiring dispatch guards."""
from contextlib import contextmanager
from dataclasses import replace
import pytest
from conftest import NOW
from test_mandate_dispatch_validity import flow,sender
from vati.core import EventKind
from vati.execution import RouterError
from vati.execution.policy import ExecutionBucket,ExecutionPolicyEngine
from vati.execution.pretrade import MarketReference,PreTradeControls
from vati.execution.route_registry import RouteRegistry
from vati.execution.style_selector import ExecutionStyleSelector,LiquidityView
from vati.risk import RiskAuthority,Decision,KillSwitchTrigger


def prepared(eurusd):
    m,trade,native=flow(eurusd);decision=RiskAuthority(m).evaluate_safe(trade,native)
    assert decision.decision in {Decision.APPROVED,Decision.REDUCED}
    paper,ledger,router=sender(m);clock={'ms':NOW*1000};router.clock=lambda:clock['ms']
    routes=RouteRegistry(ledger=ledger);routes.refresh(account_alias=m.account_alias,adapter_id='paper',
        contracts={'EURUSD':replace(eurusd,venue='paper')},now_ms=clock['ms'])
    router.route_registry=routes;router.pretrade_controls=PreTradeControls(routes=routes,ledger=ledger)
    router.style_selector=ExecutionStyleSelector();router.enforce_rev51_controls=True
    policy=ExecutionPolicyEngine().select(candidate_id=trade.trade_intent_id,
        bucket=ExecutionBucket('paper',m.account_alias,'EURUSD','LONDON','NORMAL','NONE','LONG'))
    def send():
        return router.execute(trade,decision,m,now_ms=NOW*1000,execution_policy_decision=policy,
            market_reference=MarketReference(trade.entry,0,max_mark_age_ms=30),liquidity=LiquidityView())
    send.approved_size=decision.approved_size
    return paper,ledger,router,clock,routes,trade,send


def test_valid_current_controls_reach_actual_sender_at_the_mark_age_boundary(eurusd):
    paper,ledger,router,clock,routes,trade,send=prepared(eurusd)
    @contextmanager
    def boundary(epoch):clock['ms']+=30;yield True
    router.lease_submission_guard=boundary
    receipt=send()
    assert receipt.status=='FILLED' and paper.positions() and ledger.count(EventKind.ORDER_COMMAND)==1


@pytest.mark.parametrize('boundary',['heartbeat','guard','last_fence'])
def test_owner_halt_after_initial_check_stops_new_dispatch_without_consuming_intent(eurusd,boundary):
    paper,ledger,router,clock,routes,trade,send=prepared(eurusd)
    if boundary=='heartbeat':
        original=paper.heartbeat
        def halt(*,now_ms):
            router.kill.trip(KillSwitchTrigger.OWNER_HALT,now_ms);return original(now_ms=now_ms)
        paper.heartbeat=halt
    elif boundary=='last_fence':
        calls={'n':0}
        def halt(epoch):
            calls['n']+=1
            if calls['n']==2:router.kill.trip(KillSwitchTrigger.OWNER_HALT,clock['ms'])
            return True
        router.lease_fence=halt
    else:
        @contextmanager
        def halt(epoch):router.kill.trip(KillSwitchTrigger.OWNER_HALT,clock['ms']);yield True
        router.lease_submission_guard=halt
    with pytest.raises(RouterError,match='kill switch'):send()
    assert not paper.positions() and ledger.count(EventKind.ORDER_COMMAND)==0
    assert trade.idempotency_key not in router._seen
    assert trade.idempotency_key not in router.pretrade_controls._sent_keys


@pytest.mark.parametrize('boundary',['heartbeat','guard','last_fence'])
def test_native_read_or_guard_delay_cannot_reuse_a_stale_mark(eurusd,boundary):
    paper,ledger,router,clock,routes,trade,send=prepared(eurusd)
    if boundary=='heartbeat':
        original=paper.heartbeat
        def delayed(*,now_ms):clock['ms']+=31;return original(now_ms=now_ms)
        paper.heartbeat=delayed
    elif boundary=='last_fence':
        calls={'n':0}
        def delayed(epoch):
            calls['n']+=1
            if calls['n']==2:clock['ms']+=31
            return True
        router.lease_fence=delayed
    else:
        @contextmanager
        def delayed(epoch):clock['ms']+=31;yield True
        router.lease_submission_guard=delayed
    with pytest.raises(RouterError,match='MARK_STALE'):send()
    assert not paper.positions() and ledger.count(EventKind.ORDER_COMMAND)==0
    assert trade.idempotency_key not in router._seen


def test_route_disabled_while_acquiring_the_guard_cannot_reach_actual_sender(eurusd):
    paper,ledger,router,clock,routes,trade,send=prepared(eurusd)
    @contextmanager
    def disabled(epoch):routes.disable(trade.account_alias,trade.symbol);yield True
    router.lease_submission_guard=disabled
    with pytest.raises(RouterError,match='ROUTE_UNRESOLVED'):send()
    assert not paper.positions() and ledger.count(EventKind.ORDER_COMMAND)==0


@pytest.mark.parametrize('age,observed,now,expected',[(17,6500,10000,3517),(-1,7000,10000,-1),
    (0,10001,10000,-1),(17,10001,10000,-1),(0,None,10000,-1),(True,7000,10000,-1),(0,7000,True,-1)])
def test_quote_age_includes_waiting_before_native_reads_and_rejects_unknown_or_future_origin(age,observed,now,expected):
    from vati.execution.pretrade import quote_age_at
    assert quote_age_at(age_ms=age,observed_at_ms=observed,now_ms=now)==expected


def test_changed_lot_contract_after_initial_pretrade_is_refused_without_resizing_command(eurusd):
    from decimal import Decimal
    paper,ledger,router,clock,routes,trade,send=prepared(eurusd)
    @contextmanager
    def changed(epoch):
        routes.refresh(account_alias=trade.account_alias,adapter_id='paper',
            contracts={'EURUSD':replace(eurusd,venue='paper',volume_step=send.approved_size*Decimal('.61'),volume_min=Decimal('.00000001'))},now_ms=clock['ms'])
        yield True
    router.lease_submission_guard=changed
    with pytest.raises(RouterError,match='quantisation changed'):send()
    assert not paper.positions() and ledger.count(EventKind.ORDER_COMMAND)==0


def test_actual_single_service_preserves_snapshot_quote_age_through_guard_delay(tmp_path,eurusd):
    from test_single_session_lease import config
    from test_backtest_runner_cli import synthetic_bars
    from vati.app.service import SessionService
    from vati.execution import PaperAdapter
    bars=synthetic_bars();clock={'ms':bars[100].end_ms};active={'snapshot':False}
    cfg=config(tmp_path,eurusd);cfg.max_quote_age_ms=2000
    class SlowObservedPaper(PaperAdapter):
        def sync_account(self):
            account=super().sync_account()
            if active['snapshot']:clock['ms']+=500
            return account
    adapter=SlowObservedPaper(account_alias=cfg.account_alias)
    service=SessionService(cfg,lambda now:[b for b in bars if b.end_ms<=now],clock=lambda:clock['ms'],adapter=adapter).build()
    cycle=service.runner.cycle;original_snapshot=cycle.snapshot;original_guard=cycle.router.lease_submission_guard;entered=[]
    def delayed_snapshot(**kwargs):
        active['snapshot']=True
        try:return original_snapshot(**kwargs)
        finally:active['snapshot']=False
    cycle.snapshot=delayed_snapshot
    @contextmanager
    def delayed_guard(epoch):
        with original_guard(epoch) as allowed:
            if allowed:entered.append(epoch);clock['ms']+=600
            yield allowed
    cycle.router.lease_submission_guard=delayed_guard
    try:
        service.start()
        for bar in bars[101:]:
            clock['ms']=bar.end_ms+1000;result=service.step_once()
            if entered:
                assert result=='ROUTER_REFUSED';break
        assert entered and not adapter.positions() and service._ledger.count(EventKind.ORDER_COMMAND)==0
        decisions=list(service._ledger.iter(EventKind.RISK_DECISION))
        approved=[e for e in decisions if e.payload['decision']['decision'] in {'APPROVED','REDUCED'}]
        assert approved and approved[-1].payload['inputs']['snapshot']['quote_age_ms']==1500
        refusals=[e.payload['router_refused'] for e in service._ledger.iter(EventKind.SESSION) if 'router_refused' in e.payload]
        assert refusals and 'MARK_STALE' in refusals[-1]
    finally:service.close();service._ledger.close()


@pytest.mark.parametrize('age,allowed',[(30,True),(31,False)])
def test_actual_account_delta_sender_ages_original_market_state_before_router(eurusd,age,allowed):
    from types import SimpleNamespace as N
    from vati.app.account_service import AccountCoordinatorService
    from vati.accounts import BrokerKind
    paper,ledger,router,clock,routes,trade,send=prepared(eurusd)
    m,trade,native=flow(eurusd);decision=RiskAuthority(m).evaluate_safe(trade,native)
    assert decision.decision in {Decision.APPROVED,Decision.REDUCED}
    service=AccountCoordinatorService.__new__(AccountCoordinatorService)
    state=N(as_of_ms=clock['ms']-age,quote_age_ms=0,features=N(close=trade.entry),session=N(value='LONDON'),
        regime=N(vol=N(value='NORMAL')),event_window=N(value='NONE'))
    service.evaluators={'EURUSD':N(last_state=state)};service.router=router;service.mandate=m
    service.account=N(alias=m.account_alias,broker=BrokerKind.PAPER);service.policy=ExecutionPolicyEngine()
    service.routes=routes;service.contracts={'EURUSD':replace(eurusd,venue='paper')};service.clock=lambda:clock['ms']
    service.lease=None;service.specs={'EURUSD':N(time_in_force='DAY')};service.cfg=N(max_quote_age_ms=30)
    service._ledger=ledger
    result=service._execute_delta(trade,decision)
    if allowed:
        assert result.status=='FILLED' and paper.positions() and ledger.count(EventKind.ORDER_COMMAND)==1
    else:
        assert result is None and not paper.positions() and ledger.count(EventKind.ORDER_COMMAND)==0
        refused=[e for e in ledger.iter(EventKind.SESSION) if e.payload.get('event')=='DELTA_ROUTER_REFUSED']
        assert refused and 'MARK_STALE' in refused[-1].payload['error']


def test_actual_account_entry_sender_does_not_reset_age_to_a_fresh_reference(eurusd):
    from types import SimpleNamespace as N
    from vati.app.account_service import AccountCoordinatorService
    from vati.accounts import BrokerKind
    paper,ledger,router,clock,routes,trade,send=prepared(eurusd)
    m,trade,native=flow(eurusd);decision=RiskAuthority(m).evaluate_safe(trade,native)
    assert decision.decision in {Decision.APPROVED,Decision.REDUCED}
    service=AccountCoordinatorService.__new__(AccountCoordinatorService)
    state=N(as_of_ms=clock['ms']-31,quote_age_ms=0,features=N(close=trade.entry),session=N(value='LONDON'),
        regime=N(vol=N(value='NORMAL')),event_window=N(value='NONE'))
    service.evaluators={'EURUSD':N(last_state=state)};service.router=router;service.mandate=m
    service.account=N(alias=m.account_alias,broker=BrokerKind.PAPER);service.policy=ExecutionPolicyEngine()
    service.routes=routes;service.contracts={'EURUSD':replace(eurusd,venue='paper')};service.clock=lambda:clock['ms']
    service.lease=None;service.specs={'EURUSD':N(time_in_force='DAY')};service.cfg=N(max_quote_age_ms=30)
    service._ledger=ledger
    candidate=N(symbol='EURUSD',candidate_id=trade.trade_intent_id,direction=trade.direction,entry_type='MARKET',
        valid_from_ms=clock['ms']-100,valid_until_ms=clock['ms']+1000)
    with pytest.raises(RouterError,match='MARK_STALE'):service._execute(candidate,trade,decision,(),None)
    assert not paper.positions() and ledger.count(EventKind.ORDER_COMMAND)==0
