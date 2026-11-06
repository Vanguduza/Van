"""A genuine old approval is not proof of the account at actual submission."""
from contextlib import contextmanager
from decimal import Decimal
import pytest
from test_single_session_lease import config
from test_backtest_runner_cli import synthetic_bars
from vati.app.service import SessionService
from vati.core import EventKind
from vati.execution import PaperAdapter


@pytest.mark.parametrize('factor,allowed',[(Decimal('.50'),False),(Decimal('.99'),False),(Decimal('1.10'),True)])
def test_actual_single_service_revalidates_changed_equity_without_increasing_original_size(tmp_path,eurusd,factor,allowed):
    bars=synthetic_bars();clock={'ms':bars[100].end_ms};cfg=config(tmp_path,eurusd)
    # At this explicit simulated capital level a 1% change exceeds a lot step;
    # an unchanged quantised quantity would still be within the fresh budget.
    adapter=PaperAdapter(account_alias=cfg.account_alias,equity=Decimal('1000000'))
    service=SessionService(cfg,lambda now:[b for b in bars if b.end_ms<=now],clock=lambda:clock['ms'],adapter=adapter).build()
    cycle=service.runner.cycle;original_guard=cycle.router.lease_submission_guard;original_equity=service.adapter.equity;entered=[]
    @contextmanager
    def account_changed(epoch):
        with original_guard(epoch) as valid:
            if valid and not entered:
                entered.append(epoch);service.adapter.equity=original_equity*factor
            yield valid
    cycle.router.lease_submission_guard=account_changed
    try:
        service.start()
        for bar in bars[101:]:
            clock['ms']=bar.end_ms+1000;result=service.step_once()
            if entered:break
        assert entered
        from vati.execution.native_margin import reported_account_margin
        account_event=list(service._ledger.iter(EventKind.ACCOUNT_SNAPSHOT))[-1]
        margin=reported_account_margin(account_event,cfg.account_alias)
        assert margin['state']=='SIMULATED' and margin['used_margin']=='0'
        assert margin['execution_authority'] is False and margin['snapshot_ref']==account_event.hash
        original=[e for e in service._ledger.iter(EventKind.RISK_DECISION) if e.payload['decision']['decision'] in {'APPROVED','REDUCED'}]
        assert original and Decimal(original[0].payload['inputs']['snapshot']['equity'])==original_equity
        commands=list(service._ledger.iter(EventKind.ORDER_COMMAND))
        from vati.app.tradebook import build_trade_book
        book=build_trade_book(service._ledger)
        from vati.app.portfolio import trade_detail
        detail=trade_detail(service._ledger,original[0].correlation_id)
        assert detail is not None and detail['current_risk']['state'] in {'SUFFICIENT','REFUSED'}
        timeline=[row for row in detail['timeline'] if row['kind']=='RISK_RECHECK']
        assert timeline and timeline[0]['hash']==detail['current_risk']['proof_ref']
        if allowed:
            assert len(commands)==1 and service.adapter.positions()
            assert Decimal(commands[0].payload['quantity'])<=Decimal(original[0].payload['decision']['approved_size'])
            row=book['current'][0]['current_risk']
            assert row['state']=='SUFFICIENT' and row['proof_ref']==commands[0].payload['risk_revalidation_ref']
        else:
            assert result=='ROUTER_REFUSED','changed account risk reached the sender using the original approval'
            assert commands==[] and not service.adapter.positions()
            held=[r for r in book['potential'] if r.get('kind')=='RISK_RECHECK_REFUSED']
            assert held and held[0]['current_risk']['state']=='REFUSED'
            assert held[0]['current_risk']['execution_authority'] is False
    finally:service.close();service._ledger.close()


def prepared(eurusd):
    from test_mandate_dispatch_validity import flow,sender
    from vati.risk import RiskAuthority,Decision
    from conftest import NOW
    from vati.execution.risk_refresh import CurrentRiskFacts
    m,intent,snapshot=flow(eurusd);authority=RiskAuthority(m)
    decision=authority.evaluate_safe(intent,snapshot)
    assert decision.decision in {Decision.APPROVED,Decision.REDUCED}
    adapter,ledger,router=sender(m);router.clock=lambda:NOW*1000
    router.current_risk_authority=authority
    router.current_risk_facts_provider=lambda *a,**kw:CurrentRiskFacts(snapshot,NOW*1000)
    def send():return router.execute(intent,decision,m,now_ms=NOW*1000)
    return adapter,ledger,router,authority,intent,decision,snapshot,send


@pytest.mark.parametrize('damage',['true','mapping','none','future','past','boolclock','snapshotclock','foreign','unverified'])
def test_bad_current_facts_cannot_spend_the_original_proposal_key(eurusd,damage):
    from dataclasses import replace
    from conftest import NOW
    from vati.execution import RouterError
    from vati.execution.risk_refresh import CurrentRiskFacts
    adapter,ledger,router,authority,intent,decision,snapshot,send=prepared(eurusd)
    facts=CurrentRiskFacts(snapshot,NOW*1000)
    if damage=='true':facts=True
    elif damage=='mapping':facts={'approved':True}
    elif damage=='none':facts=None
    elif damage=='future':facts=replace(facts,observed_at_ms=NOW*1000+1)
    elif damage=='past':facts=replace(facts,observed_at_ms=NOW*1000-1)
    elif damage=='boolclock':facts=replace(facts,observed_at_ms=True)
    elif damage=='snapshotclock':facts=replace(facts,snapshot=replace(snapshot,now_unix=NOW-1))
    elif damage=='foreign':facts=replace(facts,snapshot=replace(snapshot,account_alias='other-native-account'))
    else:facts=replace(facts,snapshot=replace(snapshot,account_verified=False))
    router.current_risk_facts_provider=lambda *a,**kw:facts
    with pytest.raises(RouterError,match='current account risk'):send()
    assert not adapter.positions() and ledger.count(EventKind.ORDER_COMMAND)==0
    assert intent.idempotency_key not in router._seen and intent.idempotency_key in authority._seen_keys


def test_fresh_proof_binds_original_command_and_approval_without_consuming_authority_again(eurusd):
    adapter,ledger,router,authority,intent,decision,snapshot,send=prepared(eurusd)
    receipt=send();assert receipt.status=='FILLED'
    original_keys=set(authority._seen_keys)
    proof=next(ledger.iter(EventKind.RISK_REVALIDATION));command=next(ledger.iter(EventKind.ORDER_COMMAND))
    assert proof.payload['execution_authority'] is False
    assert proof.payload['original_decision_hash']==decision.decision_hash
    assert proof.payload['original_command_hash']==command.payload['command_hash']
    assert command.payload['risk_revalidation_ref']==proof.hash
    assert command.payload['decision_hash']==decision.decision_hash
    assert authority._seen_keys==original_keys=={intent.idempotency_key}
    from vati.execution import RouterError
    with pytest.raises(RouterError,match='duplicate idempotency'):send()
    assert ledger.count(EventKind.RISK_REVALIDATION)==1 and ledger.count(EventKind.ORDER_COMMAND)==1


@pytest.mark.parametrize('when',['before-write','after-append'])
def test_current_risk_evidence_failure_refuses_before_order_and_retries_without_native_replay(eurusd,when):
    from vati.execution import RouterError
    adapter,ledger,router,authority,intent,decision,snapshot,send=prepared(eurusd)
    append=ledger.append
    def interrupted(event):
        if event.kind is EventKind.RISK_REVALIDATION:
            if when=='after-append':append(event)
            raise OSError('synthetic private storage note')
        return append(event)
    ledger.append=interrupted
    with pytest.raises(RouterError,match='risk evidence not committed'):send()
    assert not adapter.positions() and ledger.count(EventKind.ORDER_COMMAND)==0 and intent.idempotency_key not in router._seen
    ledger.append=append
    assert send().status=='FILLED'
    assert ledger.count(EventKind.RISK_REVALIDATION)==1 and ledger.count(EventKind.ORDER_COMMAND)==1


def test_provider_failure_does_not_expose_native_private_error_text_or_consume_command(eurusd):
    from vati.execution import RouterError,VenueUnavailable
    adapter,ledger,router,authority,intent,decision,snapshot,send=prepared(eurusd)
    def unavailable(*a,**kw):raise VenueUnavailable('synthetic-private-provider-note')
    router.current_risk_facts_provider=unavailable
    with pytest.raises(RouterError,match='current account risk read unavailable') as caught:send()
    assert 'synthetic-private-provider-note' not in str(caught.value)
    assert not adapter.positions() and ledger.count(EventKind.ORDER_COMMAND)==0


def test_lost_revalidation_transaction_commit_reply_preserves_original_proof_and_no_send(eurusd):
    from vati.execution import RouterError
    adapter,ledger,router,authority,intent,decision,snapshot,send=prepared(eurusd)
    atomic=ledger.atomic;depth={'n':0}
    @contextmanager
    def lost_reply():
        outer=depth['n']==0;depth['n']+=1
        try:
            with atomic():yield
        finally:depth['n']-=1
        if outer:raise OSError('synthetic commit reply lost after durable proof')
    ledger.atomic=lost_reply
    with pytest.raises(RouterError,match='risk evidence not committed'):send()
    assert ledger.count(EventKind.RISK_REVALIDATION)==1 and ledger.count(EventKind.ORDER_COMMAND)==0
    original=next(ledger.iter(EventKind.RISK_REVALIDATION)).hash
    ledger.atomic=atomic
    assert send().status=='FILLED'
    assert ledger.count(EventKind.RISK_REVALIDATION)==1 and ledger.count(EventKind.ORDER_COMMAND)==1
    assert next(ledger.iter(EventKind.ORDER_COMMAND)).payload['risk_revalidation_ref']==original


def projection_pair(eurusd):
    from conftest import NOW
    from vati.core.events import make_event
    from vati.risk.serde import intent_to_dict,snapshot_to_dict
    adapter,ledger,router,authority,intent,decision,snapshot,send=prepared(eurusd)
    send()
    original=make_event(EventKind.RISK_DECISION,'original-risk-authority',
        {'decision':decision.to_dict(),'inputs':{'intent':intent_to_dict(intent),'snapshot':snapshot_to_dict(snapshot)}},
        event_time_ms=NOW*1000,received_time_ms=NOW*1000,correlation_id=intent.trade_intent_id)
    return next(ledger.iter(EventKind.RISK_REVALIDATION)),original


@pytest.mark.parametrize('damage',['producer','decision_seal','snapshot','account','intent','mandate','authority','clock','state','quantity','snapshot_seal'])
def test_owner_projection_refuses_unbound_or_resealed_foreign_current_risk(eurusd,damage):
    from copy import deepcopy
    from dataclasses import replace
    from vati.core.canonical import canonical_hash
    from vati.execution.risk_refresh import reported_current_risk
    event,original=projection_pair(eurusd)
    assert reported_current_risk(event,original)['state']=='SUFFICIENT'
    p=deepcopy(event.payload)
    if damage=='producer':event=replace(event,producer='untrusted-import')
    elif damage=='decision_seal':p['decision']['approved_size']='999999'
    elif damage=='snapshot':p['snapshot']['equity']='999999'
    elif damage=='account':p['account_alias']='other-account'
    elif damage=='intent':p['decision']['intent_hash']='f'*64
    elif damage=='mandate':p['decision']['mandate_hash']='f'*64
    elif damage=='authority':p['execution_authority']=True
    elif damage=='clock':p['observed_at_ms']+=1
    elif damage=='state':p['state']='REFUSED'
    elif damage=='quantity':p['original_command_quantity']='NaN'
    else:p['decision']['risk_snapshot_hash']='f'*64
    if damage in {'intent','mandate','snapshot_seal'}:
        p['decision']['decision_hash']=canonical_hash({k:v for k,v in p['decision'].items() if k!='decision_hash'})
    event=replace(event,payload=p);event=replace(event,hash=canonical_hash(event.body()))
    assert reported_current_risk(event,original)=={'state':'UNAVAILABLE','execution_authority':False,'reason_code':'CURRENT_RISK_PROOF_NOT_BOUND'}


@pytest.mark.parametrize('fact',['positions','free_margin','quote_age','clock_sync','store','halt','reconciliation','preservation'])
def test_new_exposure_and_factual_holds_are_rechecked_by_actual_authority(eurusd,fact):
    from dataclasses import replace
    from vati.execution import RouterError
    from vati.execution.risk_refresh import CurrentRiskFacts
    from vati.risk.contracts import OpenPosition,Direction,KillSwitchTrigger
    from conftest import NOW
    adapter,ledger,router,authority,intent,decision,snapshot,send=prepared(eurusd)
    if fact=='positions':
        position=OpenPosition('other-open',intent.symbol,Direction.LONG,Decimal('100'),Decimal('1'),
            eurusd.value_per_price_unit_per_lot,eurusd.base_currency,eurusd.quote_currency)
        current=replace(snapshot,open_positions=(position,))
    else:
        change={'free_margin':{'free_margin':Decimal('0')},'quote_age':{'quote_age_ms':999999},
            'clock_sync':{'clock_sync_ok':False},'store':{'risk_store_ok':False},
            'halt':{'kill_switch_triggers':frozenset({KillSwitchTrigger.OWNER_HALT})},
            'reconciliation':{'reconciliation_ok':False},
            'preservation':{'preservation_blocks_new_risk':True,'preservation_reason':'unqualified original funding'}}[fact]
        current=replace(snapshot,**change)
    router.current_risk_facts_provider=lambda *a,**kw:CurrentRiskFacts(current,NOW*1000)
    with pytest.raises(RouterError,match='current account risk'):send()
    assert ledger.count(EventKind.ORDER_COMMAND)==0 and not adapter.positions()
    proof=next(ledger.iter(EventKind.RISK_REVALIDATION))
    assert proof.payload['state']=='REFUSED' and proof.payload['decision']['decision']=='REJECTED'
    assert intent.idempotency_key not in router._seen


def test_native_read_occurs_before_short_financial_writer_transaction(eurusd):
    from conftest import NOW
    from vati.execution.risk_refresh import CurrentRiskFacts
    adapter,ledger,router,authority,intent,decision,snapshot,send=prepared(eurusd)
    observed=[]
    def facts(*a,**kw):
        observed.append(ledger._conn.in_transaction)
        assert not ledger._conn.in_transaction,'native I/O acquired the protective/order journal writer'
        return CurrentRiskFacts(snapshot,NOW*1000)
    router.current_risk_facts_provider=facts
    assert send().status=='FILLED' and observed==[False]


@pytest.mark.parametrize('change',['halt','expiry'])
def test_mutable_refusal_after_native_risk_io_still_precedes_dispatch(eurusd,change):
    from conftest import NOW
    from vati.execution import RouterError
    from vati.execution.risk_refresh import CurrentRiskFacts
    from vati.risk.contracts import KillSwitchTrigger
    adapter,ledger,router,authority,intent,decision,snapshot,send=prepared(eurusd)
    def facts(*a,**kw):
        if change=='halt':router.kill.trip(KillSwitchTrigger.OWNER_HALT,NOW*1000)
        else:router.clock=lambda:authority.mandate.expires_at_unix*1000
        return CurrentRiskFacts(snapshot,NOW*1000)
    router.current_risk_facts_provider=facts
    with pytest.raises(RouterError):send()
    assert ledger.count(EventKind.ORDER_COMMAND)==0 and not adapter.positions()
    assert intent.idempotency_key not in router._seen


def test_account_runtime_provider_reads_current_snapshot_and_its_original_clock(eurusd):
    from types import SimpleNamespace as N
    from vati.app.account_service import AccountCoordinatorService
    from vati.execution.risk_refresh import CurrentRiskFacts
    adapter,ledger,router,authority,intent,decision,snapshot,send=prepared(eurusd)
    service=AccountCoordinatorService.__new__(AccountCoordinatorService);service._risk_snapshot_ms=0;calls=[]
    clock={'ms':snapshot.now_unix*1000};router.clock=lambda:clock['ms']
    def current(candidate):
        calls.append(candidate);clock['ms']+=7;service._risk_snapshot_ms=clock['ms'];return snapshot
    service._snapshot_for=current
    router.current_risk_facts_provider=service._current_risk_facts
    assert send().status=='FILLED' and calls==[intent]
    proof=next(ledger.iter(EventKind.RISK_REVALIDATION))
    assert proof.payload['observed_at_ms']==snapshot.now_unix*1000+7
