"""Original cash/query lineage through risk and owner read models, no venue effects."""
from dataclasses import replace
from decimal import Decimal as D
from contextlib import contextmanager
import pytest
from test_mt5_funding_contract import frame, cash, account
from vati.core import Ledger, EventKind
from vati.core.events import make_event
from vati.core.ledger import LedgerError
from vati.execution.base import AccountState
from vati.execution.mt5_identity import Mt5Identity
from vati.execution.mt5_pull import Mt5PullAdapter, BridgeQueue
from vati.funding.mt5 import frame_from_poll, Mt5CashFact
from vati.funding.mt5_journal import Mt5FundingBook
from vati.funding.mt5_runtime import capture_cached_mt5
from vati.funding.risk_fence import funding_risk_fence
from vati.app.portfolio import account_states


def setup(tmp_path):
    ledger=Ledger(tmp_path/'facts.sqlite');f=frame()
    adapter=Mt5PullAdapter(BridgeQueue(tmp_path/'queue.sqlite'),account_alias='native',clock=lambda:10000,
        identity=Mt5Identity('12345678','Broker-Demo','USD',True))
    return ledger,adapter,AccountState('native',f.net_equity,f.balance,'USD',True,funding_mark=f)


def publish(ledger,acct,observation,**changes):
    e=make_event(EventKind.ACCOUNT_SNAPSHOT,'vati-service',{'account_alias':'native','equity':str(acct.equity),
        'balance':str(acct.balance),'currency':'USD','verified':True,'connected':True,
        'native_account_mark':acct.funding_mark.mark_body(),'funding_observation':observation,**changes},
        event_time_ms=11000,received_time_ms=11000,correlation_id='native-session')
    ledger.append(e);return e


def profile(**changes):
    return {'alias':'native','label':'Native','broker':'MT5','mode':'DEMO_TRADER','currency':'USD',
        'login':'12345678','server':'Broker-Demo','demo':True,'enabled':True,**changes}


def test_native_query_is_required_before_risk_and_never_grants_effect_authority(tmp_path):
    ledger,adapter,acct=setup(tmp_path)
    assert not funding_risk_fence(ledger,adapter,acct,now_ms=10000).available
    observed=capture_cached_mt5(ledger,acct,now_ms=10000)
    assert observed['execution_authority'] is False and observed['return_qualification']=='NOT_ISSUED'
    assert funding_risk_fence(ledger,adapter,acct,now_ms=10000).available
    assert adapter.queue._conn.execute('SELECT count(*) FROM commands').fetchone()[0]==0


@pytest.mark.parametrize('change',['newcash','shrink','correction','credit','server','future','identitymissing','markmissing','backclock','unknownoperation'])
def test_unsafe_funding_transition_holds_new_risk(change,tmp_path):
    ledger,adapter,acct=setup(tmp_path)
    original=acct.funding_mark
    if change in {'shrink','correction'}:
        original=replace(original,movements=(Mt5CashFact.from_body(cash()),))
        acct=replace(acct,funding_mark=original)
    capture_cached_mt5(ledger,acct,now_ms=10000)
    f=replace(original,source_nonce='next',observed_at_ms=10001)
    if change=='newcash':f=replace(f,movements=(Mt5CashFact.from_body(cash()),))
    elif change=='shrink':f=replace(f,movements=())
    elif change=='correction':f=replace(f,movements=(replace(original.movements[0],profit=D('11000')),))
    elif change=='credit':f=replace(f,credit=D('300'))
    elif change=='server':f=replace(f,server='other-server')
    elif change=='future':f=replace(f,observed_at_ms=12000)
    elif change=='identitymissing':adapter.identity=None
    elif change=='backclock':f=replace(f,native_clock_ms=7000)
    elif change=='unknownoperation':f=replace(f,movements=(Mt5CashFact.from_body(cash(operation='DEAL_TYPE_BONUS')),))
    acct=replace(acct,equity=f.net_equity,funding_mark=f)
    capture_cached_mt5(ledger,acct,now_ms=max(10001,f.observed_at_ms))
    if change=='markmissing':acct=replace(acct,funding_mark=None)
    assert not funding_risk_fence(ledger,adapter,acct,now_ms=10001).available
    assert adapter.queue._conn.execute('SELECT count(*) FROM commands').fetchone()[0]==0


def test_lost_commit_ack_retries_original_query_without_changing_first_availability(tmp_path):
    ledger,adapter,acct=setup(tmp_path);atomic=ledger.atomic
    @contextmanager
    def lost_ack():
        with atomic():yield
        raise OSError('fixture lost original commit reply')
    # Only the outer transaction loses its reply; nested journal calls retain
    # the real transaction boundary rather than mocking away persistence.
    depth={'n':0}
    @contextmanager
    def wrapper():
        outer=depth['n']==0;depth['n']+=1
        try:
            with atomic():yield
        finally:depth['n']-=1
        if outer:raise OSError('fixture lost original commit reply')
    ledger.atomic=wrapper
    with pytest.raises(OSError):capture_cached_mt5(ledger,acct,now_ms=10000)
    ledger.atomic=atomic
    assert ledger.count(EventKind.FUNDING_MT5_STATEMENT)==1 and ledger.count(EventKind.FUNDING_MT5_QUERY)==1
    ledger.close();ledger=Ledger(tmp_path/'facts.sqlite')
    observed=capture_cached_mt5(ledger,acct,now_ms=15000)
    assert ledger.count(EventKind.FUNDING_MT5_QUERY)==1
    assert Mt5FundingBook(ledger)._queries(acct.funding_mark.scope_hash)[0].received_time_ms==10000
    assert funding_risk_fence(ledger,adapter,acct,now_ms=15000).available


def test_snapshot_exposes_original_cash_components_without_fabricating_cash_delta_or_return(tmp_path):
    ledger,adapter,acct=setup(tmp_path);f=replace(acct.funding_mark,movements=(Mt5CashFact.from_body(cash()),))
    acct=replace(acct,funding_mark=f);observed=capture_cached_mt5(ledger,acct,now_ms=10000)
    event=publish(ledger,acct,observed);before=ledger.count();row=account_states(ledger,[profile()])[0]
    assert row['floating_pnl']=='0' and row['day_pnl'] is None and row['performance_state']=='UNMEASURED'
    funding=row['funding'];assert funding['query_ref']==observed['query_ref'] and funding['snapshot_ref']==event.hash
    movement=funding['movements'][0]['movement']
    assert movement['native_id']==9007199254740993 and movement['fee']=='-1.3E-7' and 'delta' not in movement
    assert funding['return_qualification']=='NOT_ISSUED' and funding['execution_authority'] is False
    assert ledger.count()==before
    for changes in ({'server':'other'},{'login':'999'},{'demo':False},{'currency':'EUR'},{'broker':'CTRADER'}):
        hidden=account_states(ledger,[profile(**changes)])[0]
        assert hidden['funding']['reason']=='CURRENT_PROFILE_NATIVE_SCOPE_MISMATCH'
        assert hidden['equity'] is None and hidden['floating_pnl'] is None and not hidden['funding']['movements']


def test_forged_query_snapshot_or_legacy_credit_cannot_display_floating_profit(tmp_path):
    ledger,adapter,acct=setup(tmp_path);observed=capture_cached_mt5(ledger,acct,now_ms=10000)
    publish(ledger,acct,observed|{'query_ref':'unobserved-query'})
    row=account_states(ledger,[profile()])[0]
    assert row['funding']['state']=='UNAVAILABLE' and row['floating_pnl'] is None
    publish(ledger,acct,observed,equity='10200')
    row=account_states(ledger,[profile()])[0]
    assert row['funding']['state']=='UNAVAILABLE' and row['floating_pnl'] is None


def test_query_cannot_be_backdated_or_changed_into_execution_authority(tmp_path):
    ledger,adapter,acct=setup(tmp_path);capture_cached_mt5(ledger,acct,now_ms=10000)
    original=next(ledger.iter(EventKind.FUNDING_MT5_QUERY))
    ledger_iter=ledger.iter
    for payload,when in ((original.payload|{'execution_authority':True},original.event_time_ms),(original.payload,original.event_time_ms-1)):
        forged=make_event(original.kind,original.producer,payload,event_time_ms=when,received_time_ms=original.received_time_ms,correlation_id=original.correlation_id)
        def altered(kind=None,correlation_id=None):
            return iter([forged]) if kind is EventKind.FUNDING_MT5_QUERY else ledger_iter(kind,correlation_id)
        ledger.iter=altered
        with pytest.raises(LedgerError):Mt5FundingBook(ledger)._queries(acct.funding_mark.scope_hash)
        ledger.iter=ledger_iter


@pytest.mark.parametrize('field,value',[('equity','NaN'),('balance','Infinity'),('currency',''),('equity',True)])
def test_invalid_cached_native_account_becomes_unavailable_not_an_uncaught_parse_error(tmp_path,field,value):
    from vati.execution.base import VenueUnavailable
    ledger,adapter,acct=setup(tmp_path)
    body=account();body[field]=value;body['trade_allowed']=True;body['hedging']=True
    adapter.queue.set_state('native',body,[],nonce='invalid-account-native-poll',now_ms=10000)
    with pytest.raises(VenueUnavailable):adapter.sync_account()


@pytest.mark.parametrize('change',['cash','credit','clock','clockbasis'])
def test_returning_to_old_telemetry_cannot_erase_an_observed_funding_hazard(tmp_path,change):
    ledger,adapter,acct=setup(tmp_path);original=acct.funding_mark
    capture_cached_mt5(ledger,acct,now_ms=10000)
    changed=replace(original,source_nonce='intervening',observed_at_ms=10001)
    if change=='cash':changed=replace(changed,movements=(Mt5CashFact.from_body(cash()),))
    elif change=='credit':changed=replace(changed,credit=D('300'))
    elif change=='clock':changed=replace(changed,native_clock_ms=8500)
    else:changed=replace(changed,source_kind='MT5_SIGNED_MTLS_READ')
    capture_cached_mt5(ledger,replace(acct,equity=changed.net_equity,funding_mark=changed),now_ms=10001)
    reverted=replace(original,source_nonce='reverted',observed_at_ms=10002)
    current=replace(acct,funding_mark=reverted)
    capture_cached_mt5(ledger,current,now_ms=10002)
    assert not funding_risk_fence(ledger,adapter,current,now_ms=10002).available


def test_provider_reverting_a_corrected_row_does_not_hide_original_conflict_from_owner(tmp_path):
    ledger,adapter,acct=setup(tmp_path)
    original=replace(acct.funding_mark,movements=(Mt5CashFact.from_body(cash()),));acct=replace(acct,funding_mark=original)
    capture_cached_mt5(ledger,acct,now_ms=10000)
    corrected=replace(original,source_nonce='correction',observed_at_ms=10001,
        movements=(replace(original.movements[0],profit=D('11000')),))
    capture_cached_mt5(ledger,replace(acct,funding_mark=corrected),now_ms=10001)
    reverted=replace(original,source_nonce='reverted',observed_at_ms=10002);acct=replace(acct,funding_mark=reverted)
    observed=capture_cached_mt5(ledger,acct,now_ms=10002);publish(ledger,acct,observed)
    row=account_states(ledger,[profile()])[0]
    assert row['funding']['state']=='CONFLICT' and len(row['funding']['conflicts'])==1
    assert row['funding']['movements'][0]['movement']['profit']=='10000'
