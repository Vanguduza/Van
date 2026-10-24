"""Real journal and native-read recovery at the runtime snapshot boundary."""
from dataclasses import replace
from decimal import Decimal as D
from types import SimpleNamespace as N
import pytest
from test_native_cash_history import NativeCash,ROW
from test_retirement_venue_observations import ctrader
from vati.core.events import EventKind
from vati.core.ledger import Ledger
from vati.execution.base import VenueUnavailable,Health
from vati.funding.runtime import capture_funding,WEEK_MS

def setup(tmp_path):
    class WindowCash(NativeCash):
        def call(self,name,body):
            response,result=super().call(name,body)
            if name=='ProtoOACashFlowHistoryListReq':
                result['depositWithdraw']=[row for row in result['depositWithdraw'] if body['fromTimestamp']<=row['changeBalanceTimestamp']<=body['toTimestamp']]
            return response,result
    ledger=Ledger(tmp_path/'facts.sqlite');transport=WindowCash();adapter=ctrader(transport);adapter.clock=lambda:3000
    return ledger,transport,adapter

def test_native_mark_excludes_separate_bonuses_and_never_guesses_missing_bonus_values(tmp_path):
    _,transport,adapter=setup(tmp_path)
    transport.trader.update(balanceVersion=10,managerBonus=200,ibBonus=300,nonWithdrawableBonus=500)
    account=adapter.sync_account();mark=account.funding_mark
    assert mark.balance==D('100.25') and mark.net_equity==D('100.25') and mark.nonwithdrawable_bonus==D('5')
    assert mark.balance_version==10 and mark.environment=='DEMO'
    del transport.trader['ibBonus']
    assert adapter.sync_account().funding_mark.ib_bonus is None

def test_first_runtime_history_window_respects_native_account_registration(tmp_path):
    ledger,transport,adapter=setup(tmp_path);transport.trader['registrationTimestamp']=2500;transport.rows=[]
    account=adapter.sync_account()
    assert account.funding_mark.registered_at_ms==2500
    result=capture_funding(ledger,adapter,account,now_ms=3000)
    assert result['state']=='OBSERVED' and result['coverage_from_ms']==2500
    with pytest.raises(VenueUnavailable):adapter.cash_movements(from_ms=0,to_ms=3000)

@pytest.mark.parametrize('field',['balanceVersion','managerBonus','ibBonus','nonWithdrawableBonus'])
def test_changed_native_version_or_bonus_during_mark_is_never_verified(field):
    class Changed(NativeCash):
        def call(self,name,body):
            if name=='ProtoOAGetPositionUnrealizedPnLReq':self.trader[field]=1
            return super().call(name,body)
    with pytest.raises(VenueUnavailable):ctrader(Changed()).sync_account()

def test_runtime_repeat_restart_and_failed_read_reconcile_original_native_history(tmp_path):
    ledger,transport,adapter=setup(tmp_path);acct=adapter.sync_account()
    first=capture_funding(ledger,adapter,acct,now_ms=3000)
    same=capture_funding(Ledger(tmp_path/'facts.sqlite'),adapter,acct,now_ms=3000)
    # The first catch-up window and a closed point window have distinct identities;
    # neither creates a second native movement or submits funds.
    assert first['state']=='OBSERVED' and same['state']=='OBSERVED'
    assert ledger.count(EventKind.FUNDING_STATEMENT)==2
    latest=same['statement']['statement_ref']
    repeat=capture_funding(ledger,adapter,acct,now_ms=3000)
    assert repeat['statement']['statement_ref']==latest and ledger.count(EventKind.FUNDING_STATEMENT)==2
    adapter.clock=lambda:4000;acct=adapter.sync_account();native_read=adapter.cash_movements
    adapter.cash_movements=lambda **_:(_ for _ in ()).throw(VenueUnavailable('fixture-secret must never leak'))
    unavailable=capture_funding(ledger,adapter,acct,now_ms=4000)
    assert unavailable['state']=='UNAVAILABLE' and unavailable['retry_from_ms']==3000 and 'fixture-secret' not in str(unavailable)
    adapter.cash_movements=native_read;transport.rows=[]
    recovered=capture_funding(ledger,adapter,acct,now_ms=4000)
    assert recovered['coverage_from_ms']==3000 and recovered['coverage_to_ms']==4000

def test_runtime_never_skips_weekly_catchup_or_merges_a_changed_native_account(tmp_path):
    ledger,transport,adapter=setup(tmp_path);capture_funding(ledger,adapter,adapter.sync_account(),now_ms=3000)
    transport.rows=[];adapter.clock=lambda:3000+3*WEEK_MS
    account=adapter.sync_account()
    first=capture_funding(ledger,adapter,account,now_ms=account.server_time_unix_ms)
    second=capture_funding(ledger,adapter,account,now_ms=account.server_time_unix_ms)
    assert first['coverage_from_ms']==3000 and first['coverage_to_ms']==3000+WEEK_MS and first['catch_up_state']=='PENDING'
    assert second['coverage_from_ms']==first['coverage_to_ms'] and second['coverage_to_ms']==3000+2*WEEK_MS
    native=adapter.cash_movements
    adapter.cash_movements=lambda **kwargs:replace(native(**kwargs),native_account_id=99999)
    rejected=capture_funding(ledger,adapter,account,now_ms=account.server_time_unix_ms)
    assert rejected['reason']=='NATIVE_ACCOUNT_BINDING_CHANGED' and ledger.count(EventKind.FUNDING_STATEMENT)==3

def test_deal_history_has_its_own_recovery_cursor_when_cash_collection_succeeded(tmp_path):
    from test_native_deal_history import NativeDeals
    from vati.execution.ctrader.transport import CtraderApiError
    ledger=Ledger(tmp_path/'native.sqlite');transport=NativeDeals();adapter=ctrader(transport);adapter.clock=lambda:3000
    original=adapter.deal_history
    adapter.deal_history=lambda **_:(_ for _ in ()).throw(CtraderApiError('NOT_AVAILABLE','fixture-private-provider-note'))
    first=capture_funding(ledger,adapter,adapter.sync_account(),now_ms=3000)
    assert first['state']=='OBSERVED' and first['deal_observation']['state']=='UNAVAILABLE'
    assert 'fixture-private-provider-note' not in str(first)
    adapter.deal_history=original;adapter.clock=lambda:4000;transport.rows=[]
    recovered=capture_funding(ledger,adapter,adapter.sync_account(),now_ms=4000)
    assert recovered['coverage_from_ms']==3000 and recovered['deal_observation']['coverage_from_ms']==0
    assert recovered['deal_observation']['state']=='OBSERVED' and ledger.count(EventKind.FUNDING_DEAL_STATEMENT)==1

@pytest.mark.parametrize('runtime',['account','session'])
def test_both_existing_runtime_snapshot_producers_ingest_native_facts(runtime,tmp_path):
    ledger,transport,adapter=setup(tmp_path)
    adapter.heartbeat=lambda **_:Health(True,0,3000)
    class Reader:
        def cash_movements(self,**window):return adapter.cash_movements(**window)
        def close(self):pass
    adapter.funding_reader=Reader
    if runtime=='session':
        from vati.app.service import SessionService
        service=SessionService.__new__(SessionService);service.learning=None
        service.runner=N(cycle=N(adapter=adapter,ledger=ledger,peak_equity=D('100.25'),day_start_equity=D('100.25'),week_start_equity=D('100.25'),
            kill=N(active=[]),mandate=N(mode=N(value='DEMO_TRADER')),streaks=N(recovery_issue=''),cfg=N(session_id='original-session')))
    else:
        from vati.app.account_service import AccountCoordinatorService
        service=AccountCoordinatorService.__new__(AccountCoordinatorService);service.learning=None;service.adapter=adapter;service._ledger=ledger
        service.peak_equity=service.day_start_equity=service.week_start_equity=D('100.25')
        service.kill=N(active=[]);service.mandate=None;service.coordinator=None;service.lifecycle=None;service.cfg=N(account_alias=adapter.account_alias)
    service.clock=lambda:3000
    from vati.funding.worker import stop_funding
    try:
        service._account_snapshot(3000)
        assert getattr(service,'_funding_worker',None) is not None
        assert service._funding_worker.wait_idle()
        service._account_snapshot(3000)
        event=list(ledger.iter(EventKind.ACCOUNT_SNAPSHOT))[-1]
        assert event.payload['funding_observation']['state']=='OBSERVED'
        assert event.payload['native_account_mark']['observed_at_ms']==3000
        assert event.received_time_ms>=3000
        assert event.payload['funding_observation']['statement']['statement_ref']==list(ledger.iter(EventKind.FUNDING_STATEMENT))[0].hash
        assert service._funding_worker.wait_idle()
        stop_funding(service)
        previous=event.payload['funding_observation']
        class OldWorkerResult:
            def submit(self,*_):return previous
            def close(self):pass
        service._funding_worker=OldWorkerResult();adapter.clock=lambda:4000;service.clock=lambda:5000
        service._account_snapshot(3000)
        latest=list(ledger.iter(EventKind.ACCOUNT_SNAPSHOT))[-1]
        assert latest.payload['native_account_mark']['observed_at_ms']==4000
        assert latest.payload['funding_observation']['native_mark']['observed_at_ms']==3000
        assert latest.received_time_ms==5000
    finally:stop_funding(service)

def test_slow_cash_reader_does_not_block_snapshots_and_request_queue_is_bounded(tmp_path):
    import threading,time
    from vati.funding.worker import FundingIngestWorker
    ledger,transport,adapter=setup(tmp_path);account=adapter.sync_account()
    entered=threading.Event();release=threading.Event();closed=threading.Event();calls=[]
    class SlowReader:
        def cash_movements(self,**window):
            calls.append(window);entered.set();assert release.wait(3)
            return adapter.cash_movements(**window)
        def close(self):closed.set()
    worker=FundingIngestWorker(ledger.path,SlowReader)
    try:
        assert worker.submit(account,3000)['state']=='PENDING' and entered.wait(2)
        before=time.monotonic()
        for _ in range(100):assert worker.submit(account,3000)['state']=='PENDING'
        assert time.monotonic()-before<1 and len(calls)==1
        release.set();assert worker.wait_idle()
        assert len(calls)==2 and ledger.count(EventKind.FUNDING_STATEMENT)==2
    finally:release.set();worker.close()
    assert closed.wait(2)

def test_native_funding_reader_uses_a_separate_actual_protocol_connection():
    from test_ctrader import FakeCtrader,make_adapter
    class CashBroker(FakeCtrader):
        def handle(self,name,body,cid):
            if name=='ProtoOACashFlowHistoryListReq':
                return self.send('ProtoOACashFlowHistoryListRes',{'ctidTraderAccountId':12345,'depositWithdraw':[]},cid)
            return super().handle(name,body,cid)
    primary=CashBroker();readers=[]
    adapter=make_adapter(primary);adapter.sync_account()
    def fresh_connection(host,port):
        broker=CashBroker();readers.append(broker);return broker.connector(host,port)
    adapter.transport._connector=fresh_connection
    reader=adapter.funding_reader()
    try:
        result=reader.cash_movements(from_ms=1000,to_ms=2000)
        assert result.movements==() and len(readers)==1
        assert not any(name=='ProtoOACashFlowHistoryListReq' for name,_ in primary.requests)
        assert adapter.transport.connected and not hasattr(reader,'submit') and not hasattr(reader,'withdraw')
        assert not any(name in {'ProtoOANewOrderReq','ProtoOASymbolsListReq'} for name,_ in readers[0].requests)
    finally:reader.close();adapter.transport.close()

def test_failed_account_startup_stops_funding_admission_and_closes_its_native_reader(tmp_path,monkeypatch):
    import signal,threading
    from vati.app.account_service import AccountCoordinatorService
    from vati.funding.worker import FundingIngestWorker
    ledger,_,adapter=setup(tmp_path);account=adapter.sync_account();entered=threading.Event();release=threading.Event();closed=threading.Event()
    class Reader:
        def cash_movements(self,**window):
            entered.set();assert release.wait(3);return adapter.cash_movements(**window)
        def close(self):closed.set()
    worker=FundingIngestWorker(ledger.path,Reader)
    service=AccountCoordinatorService.__new__(AccountCoordinatorService)
    service._funding_worker=worker;service._packet_worker_stop=None;service._packet_worker=None;service.lease=None;service._lease_store=None
    def failed_start():
        worker.submit(account,3000);assert entered.wait(2)
        raise RuntimeError('fixture-original-startup-failure')
    service.start=failed_start
    monkeypatch.setattr(signal,'signal',lambda *_:None)
    try:
        with pytest.raises(RuntimeError,match='fixture-original-startup-failure'):service.run_forever()
        assert service._funding_worker is None
        with pytest.raises(RuntimeError,match='funding_collector_stopped'):worker.submit(account,3000)
    finally:release.set();worker.close()
    assert closed.wait(2)
