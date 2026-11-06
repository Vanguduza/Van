"""A one-symbol production runtime needs the same final account fence as a book."""
import os
import json
import multiprocessing
from contextlib import contextmanager
from dataclasses import asdict,replace
from pathlib import Path

import pytest

from conftest import historical_mandate_dict, mandate_dict
from vati.accounts import Account,AccountRegistry,CredentialRef
from vati.app.service import ServiceConfig,SessionService
from vati.execution.paper import PaperAdapter
from vati.risk.serde import contract_to_dict
from vati.app.account_lease import AccountRuntimeLease,LeaseStoreUnavailable
from vati.app.sqlite_lease import SQLiteLeaseStore


def config(tmp_path,contract,*,broker='PAPER',ledger=None):
    registry=AccountRegistry(tmp_path/'accounts.json')
    account=registry.add(Account(alias='paper_lease',broker=broker,mode='DEMO_TRADER',currency='USD',
        credential_ref=CredentialRef() if broker=='PAPER' else CredentialRef(env_var='SOURCE_FIXTURE_NOT_READ')))
    return ServiceConfig(account_alias=account.alias,symbol='EURUSD',base='EUR',quote='USD',timeframe='H1',
        contract=contract_to_dict(contract),mandate=historical_mandate_dict(venue=account.router_venue,mode='DEMO_TRADER',
            account_alias=account.alias,allowed_strategies=['FX-TREND-PULLBACK-01']),
        capsules=['FX-TREND-PULLBACK-01'],registry_path=str(registry.path),
        ledger=ledger or str(tmp_path/'native.sqlite'),heartbeat_path=str(tmp_path/'heartbeat.json'))


def test_real_single_symbol_builder_installs_shared_and_final_submission_fences(tmp_path,eurusd):
    service=SessionService(config(tmp_path,eurusd),lambda now:[],clock=lambda:1000).build()
    try:
        assert callable(service.runner.cycle.router.lease_fence)
        assert callable(service.runner.cycle.router.lease_submission_guard)
        assert service.runner.cycle.router.lease_fence(None) is False
    finally:
        if callable(getattr(service,'close',None)): service.close()
        service._ledger.close()


def test_non_paper_single_symbol_sending_runtime_refuses_a_local_lease(tmp_path,eurusd):
    cfg=config(tmp_path,eurusd,broker='DERIV')
    with pytest.raises(RuntimeError,match='shared PostgreSQL'):
        SessionService(cfg,lambda now:[],clock=lambda:1000,
            adapter=PaperAdapter(venue='deriv',account_alias=cfg.account_alias)).build()


def test_read_only_native_observation_still_has_a_local_source_path(tmp_path,eurusd):
    cfg=config(tmp_path,eurusd,broker='DERIV'); cfg.mandate=mandate_dict(venue='deriv',mode='OBSERVE',account_alias=cfg.account_alias)
    service=SessionService(cfg,lambda now:[],clock=lambda:1000,
        adapter=PaperAdapter(venue='deriv',account_alias=cfg.account_alias)).build()
    try:
        service.start()
        assert service.lease.held is not None and not service.runner.cycle.mandate.sends_orders()
    finally: service.close(); service._ledger.close()


def test_a_second_real_runtime_cannot_displace_its_live_peer_and_release_preserves_epoch(tmp_path,eurusd):
    cfg=config(tmp_path,eurusd)
    a=SessionService(cfg,lambda now:[],clock=lambda:1000).build()
    b=SessionService(cfg,lambda now:[],clock=lambda:1000).build()
    try:
        a.start(); epoch=a.lease.epoch
        with pytest.raises(RuntimeError,match='REFUSED_HELD_BY_OTHER'): b.start()
        b.close()
        assert a.runner.cycle.router.lease_fence(epoch) is True
        a.close()
        assert a.runner.cycle.router.lease_fence(epoch) is False
        c=SessionService(cfg,lambda now:[],clock=lambda:1000).build()
        try:
            c.start(); assert c.lease.epoch > epoch
            assert a.runner.cycle.router.lease_fence(epoch) is False
        finally: c.close(); c._ledger.close()
    finally:
        a.close(); b.close(); a._ledger.close(); b._ledger.close()


def test_lost_renewal_masks_actual_entry_and_heartbeat_without_clearing_owner_halt(tmp_path,eurusd,monkeypatch):
    from vati.core.events import EventKind,make_event
    cfg=config(tmp_path,eurusd); service=SessionService(cfg,lambda now:[],clock=lambda:1000).build()
    try:
        service.start(); epoch=service.lease.epoch
        def unavailable(*args): raise LeaseStoreUnavailable('fixture-unavailable')
        with monkeypatch.context() as m:
            m.setattr(service._lease_store,'read',unavailable)
            assert service.step_once() is None
            assert service.runner.cycle.router.lease_fence(epoch) is False
            heartbeat=json.loads(Path(cfg.heartbeat_path).read_text())
            assert heartbeat['permit_new_orders'] is False and heartbeat['lease_outcome']=='STORE_UNREACHABLE'
        service._ledger.append(make_event(EventKind.KILL_SWITCH,'fixture-native-owner-act',
            {'trigger':'OWNER_HALT'},event_time_ms=1000,received_time_ms=1000))
        service.step_once()
        assert service._lease_allows_entry is True
        assert service.runner.permit_new_orders is False
        assert json.loads(Path(cfg.heartbeat_path).read_text())['permit_new_orders'] is False
    finally: service.close(); service._ledger.close()


def test_native_sqlite_guard_allows_ledger_append_and_preserves_provider_uncertainty(tmp_path):
    from vati.core.ledger import Ledger
    from vati.core.events import EventKind,make_event
    path=tmp_path/'native.sqlite'; led=Ledger(path); store=SQLiteLeaseStore(path)
    lease=AccountRuntimeLease(store,account_alias='paper_lease',instance_id='original-runtime')
    try:
        assert lease.acquire(now_ms=1000).permits_orders
        original=OSError('fixture-lost-provider-reply')
        with pytest.raises(OSError) as error:
            with lease.submission_guard(lease.epoch,now_ms=1000) as allowed:
                assert allowed
                led.append(make_event(EventKind.SESSION,'source-fixture',{'guarded':True},event_time_ms=1000,received_time_ms=1000))
                raise original
        assert error.value is original and led.verify_chain()[0]
        assert SQLiteLeaseStore(path).read('paper_lease')==lease.held
    finally: lease.release(now_ms=1000); store.close(); led.close()


@pytest.mark.parametrize('control_change',['takeover','native-halt','process-stop'])
def test_actual_cycle_passes_held_epoch_and_final_guard_blocks_takeover_before_adapter(tmp_path,eurusd,monkeypatch,control_change):
    from test_backtest_runner_cli import synthetic_bars
    from vati.app.account_lease import LeaseOutcome
    bars=synthetic_bars(); clock={'now':bars[100].end_ms}
    cfg=config(tmp_path,eurusd)
    service=SessionService(cfg,lambda now:[b for b in bars if b.end_ms<=now],clock=lambda:clock['now']).build()
    thief=AccountRuntimeLease(SQLiteLeaseStore(cfg.ledger),account_alias=cfg.account_alias,instance_id='second-native-runtime')
    entered=[]; submissions=[]; before=service.runner.cycle.router.lease_submission_guard
    native_guard=service.lease.submission_guard
    submit=service.adapter.submit
    def delegated(request,**kwargs):
        submissions.append(request); return submit(request,**kwargs)
    def late_guard(epoch):
        assert epoch==service.lease.epoch and service.runner.cycle.router.lease_fence(epoch)
        entered.append(epoch)
        if control_change=='takeover':
            clock['now']=service.lease.held.expires_at_ms+1
            assert thief.acquire(now_ms=clock['now']).outcome is LeaseOutcome.GRANTED
        return before(epoch)
    @contextmanager
    def after_native_authority(epoch,*,now_ms):
        with native_guard(epoch,now_ms=now_ms) as allowed:
            if control_change=='native-halt':
                from vati.core.events import EventKind,make_event
                service._ledger.append(make_event(EventKind.KILL_SWITCH,'fixture-native-owner-act',
                    {'trigger':'OWNER_HALT'},event_time_ms=clock['now'],received_time_ms=clock['now']))
            elif control_change=='process-stop': service.stop_requested=True
            yield allowed
    monkeypatch.setattr(service.adapter,'submit',delegated)
    monkeypatch.setattr(service.runner.cycle.router,'lease_submission_guard',late_guard)
    monkeypatch.setattr(service.lease,'submission_guard',after_native_authority)
    try:
        service.start()
        for bar in bars[101:]:
            clock['now']=bar.end_ms+1000
            decision=service.step_once()
            if entered:
                assert decision=='ROUTER_REFUSED'
                break
        assert entered,'fixture never reached a genuine eligible router submission'
        assert not submissions
        assert json.loads(Path(cfg.heartbeat_path).read_text())['permit_new_orders'] is False
    finally:
        service.close(); service._ledger.close(); thief.release(now_ms=clock['now']); thief.store.close()


def session_process(raw,begin,release,output):
    service=None
    try:
        if not begin.wait(8): raise RuntimeError('fixture-start-unavailable')
        service=SessionService(ServiceConfig(**raw),lambda now:[],clock=lambda:1000).build()
        try:
            service.start()
        except RuntimeError as exc:
            output.put(('REFUSED',str(exc),os.getpid())); return
        output.put(('STARTED',service.lease.epoch,os.getpid()))
        if not release.wait(8): raise RuntimeError('fixture-release-unavailable')
    except Exception as exc:
        output.put(('ERROR',repr(exc),os.getpid()))
    finally:
        if service:
            service.close()
            if service._ledger: service._ledger.close()


@pytest.mark.parametrize('backend',['sqlite','postgres'])
def test_actual_single_symbol_processes_arbitrate_before_startup_reconciliation(tmp_path,eurusd,backend):
    from vati.core.ledger_pg import open_ledger
    if backend=='postgres':
        spec=os.environ.get('VATI_TEST_PG_DSN')
        if not spec or os.environ.get('VATI_TEST_PG_ISOLATED_FIXTURE')!='1':
            pytest.skip('requires an explicitly isolated native PostgreSQL fixture')
    else: spec=None
    cfg=config(tmp_path,eurusd,ledger=spec)
    led=open_ledger(cfg.ledger); led.close()
    ctx=multiprocessing.get_context('spawn'); begin=ctx.Event(); release=ctx.Event(); output=ctx.Queue()
    children=[ctx.Process(target=session_process,args=(asdict(cfg),begin,release,output)) for _ in range(2)]
    try:
        for child in children: child.start()
        begin.set(); results=[output.get(timeout=12) for _ in children]
        assert sorted(row[0] for row in results)==['REFUSED','STARTED'],results
        assert 'REFUSED_HELD_BY_OTHER' in next(row[1] for row in results if row[0]=='REFUSED')
        assert len({row[2] for row in results})==2
        release.set()
        for child in children: child.join(5); assert child.exitcode==0
    finally:
        release.set()
        for child in children:
            if child.is_alive(): child.terminate(); child.join(3)
        output.close()


def first_pg_claim(spec,alias,barrier,release,output):
    """Both real transactions observe the absent row before their INSERTs."""
    import psycopg
    from vati.app.account_lease import PostgresLeaseStore
    class Cursor:
        def __init__(self,inner): self.inner=inner; self.at_absent_read=False
        def __enter__(self): self.inner.__enter__(); return self
        def __exit__(self,*args): return self.inner.__exit__(*args)
        def execute(self,query,*args):
            self.at_absent_read='FOR UPDATE' in query
            return self.inner.execute(query,*args)
        def fetchone(self):
            row=self.inner.fetchone()
            if self.at_absent_read and row is None:
                self.at_absent_read=False; barrier.wait(timeout=8)
            return row
    class Connection:
        def __init__(self,inner): self.inner=inner
        @property
        def autocommit(self): return self.inner.autocommit
        @autocommit.setter
        def autocommit(self,value): self.inner.autocommit=value
        def cursor(self): return Cursor(self.inner.cursor())
        def commit(self): return self.inner.commit()
        def rollback(self): return self.inner.rollback()
        def close(self): return self.inner.close()
    store=PostgresLeaseStore(spec,connect=lambda value:Connection(psycopg.connect(value)))
    lease=AccountRuntimeLease(store,account_alias=alias,instance_id='native-race-'+str(os.getpid()))
    try:
        result=lease.acquire(now_ms=1000)
        output.put(result.outcome.value)
        if result.permits_orders: release.wait(10)
    except Exception as exc: output.put('ERROR:'+type(exc).__name__)
    finally: lease.release(now_ms=1000); store.close()


def test_simultaneous_first_postgres_insert_reports_healthy_arbitration_not_outage():
    import secrets
    from vati.core.ledger_pg import open_ledger
    spec=os.environ.get('VATI_TEST_PG_DSN')
    if not spec or os.environ.get('VATI_TEST_PG_ISOLATED_FIXTURE')!='1':
        pytest.skip('requires an explicitly isolated native PostgreSQL fixture')
    led=open_ledger(spec); led.close()
    alias='first_lease_'+secrets.token_hex(6)
    ctx=multiprocessing.get_context('spawn'); barrier=ctx.Barrier(2); release=ctx.Event(); output=ctx.Queue()
    children=[ctx.Process(target=first_pg_claim,args=(spec,alias,barrier,release,output)) for _ in range(2)]
    try:
        for child in children: child.start()
        results=[output.get(timeout=12) for _ in children]
        assert sorted(results)==['GRANTED','REFUSED_HELD_BY_OTHER'],results
        release.set()
        for child in children: child.join(5); assert child.exitcode==0
    finally:
        release.set()
        for child in children:
            if child.is_alive(): child.terminate(); child.join(3)
        output.close()
