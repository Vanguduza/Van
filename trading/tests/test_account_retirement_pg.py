"""Actual PostgreSQL account lease/journal isolation; no broker effects."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal as D
import os,asyncio
from threading import Event
import time
from types import SimpleNamespace as NS
import uuid

import pytest
from backend.tests.test_trading_api import client,_env
from backend.tests.test_account_update_review import isolate,immediate_challenge
from van_gateway.trading.accounts import LocalAccountControl
from fastapi import HTTPException
from commander.accounts import AccountControlSettings,build_account_handlers,_write_secrets
from vati.accounts import Account,AccountRegistry,CredentialRef
from vati.app.account_lease import AccountRuntimeLease,PostgresLeaseStore,LeaseOutcome
from vati.core.ledger_pg import PostgresLedger
from vati.execution.base import AccountState,Health,OrderCommand,StopMode
from vati.accounts.access import bind_entry_authority
from vati.risk.contracts import Direction,LossModel


def _observe_native_failure(invoke, diagnostics, snapshot):
    """Test-only observation; no retry, result substitution or exception translation."""
    def observed(journal,intent,handler,**kwargs):
        stage=['CLAIM_OR_DISPATCH'];captured=[]
        def effect():
            stage[0]='HANDLER_ENTERED'
            try:
                value=handler();stage[0]='HANDLER_RETURNED';return value
            except BaseException as error:
                captured.append(error);raise
        try:return invoke(journal,intent,effect,**kwargs)
        except BaseException as error:
            original=captured[0] if captured else error
            record={'stage':stage[0],'exception_class':type(original).__name__,
                'http_status':original.status_code if isinstance(original,HTTPException) else None}
            try:record.update(snapshot())
            except BaseException:record['snapshot_stage']='UNAVAILABLE'
            diagnostics.append(record)
            raise
    return observed


def test_failure_observer_preserves_original_exception_and_paper_metadata():
    diagnostics=[];failure=HTTPException(409,'controlled nonsensitive failure')
    def invoke(journal,intent,handler,**kwargs):return handler()
    def effect():raise failure
    observed=_observe_native_failure(invoke,diagnostics,lambda:{'account_present':True,
        'lifecycle_phase':'DISCONNECTING','private_facts':[{'kind':'STEP','state':'MAY_BEGIN'}]})
    with pytest.raises(HTTPException) as caught:observed(None,None,effect)
    assert caught.value is failure
    assert diagnostics==[{'stage':'HANDLER_ENTERED','exception_class':'HTTPException','http_status':409,
        'account_present':True,'lifecycle_phase':'DISCONNECTING','private_facts':[{'kind':'STEP','state':'MAY_BEGIN'}]}]


@pytest.fixture
def pg_native(tmp_path,monkeypatch,client):
    dsn=os.environ.get('VATI_TEST_PG_DSN')
    if not dsn or os.environ.get('VATI_TEST_PG_ISOLATED_FIXTURE')!='1':
        pytest.skip('actual isolated PostgreSQL fixture must be explicitly bound')
    namespace='unlink_'+uuid.uuid4().hex;alias='unlink_'+uuid.uuid4().hex[:12]
    PostgresLedger(dsn,ledger_name=namespace).close()
    monkeypatch.setattr('vati.core.ledger_pg.open_ledger',lambda spec:PostgresLedger(spec,ledger_name=namespace))
    secret=tmp_path/(alias+'.env');_write_secrets(secret,{'BRIDGE_SIGNING_KEY':'fixture-only'})
    registry=AccountRegistry(tmp_path/'accounts.json');account=registry.add(Account(alias,'MT5','DEMO_TRADER','USD',
        login='12345678',server='Broker-Demo',bridge_url='https://fixture.invalid:9443',
        credential_ref=CredentialRef(secrets_file=str(secret))))
    view=NS(block=None,release=None)
    def balance():
        from commander.account_effects import _effect_started
        if view.block is not None and _effect_started.get() is not None:
            view.block.set();assert view.release.wait(timeout=5)
        return AccountState(alias,D('100'),D('100'),'USD',True,server_time_unix_ms=int(time.time()*1000))
    adapter=NS(sync_account=balance,positions=lambda:[],orders=lambda:[],
        heartbeat=lambda **kw:Health(True,0,kw['now_ms']))
    monkeypatch.setattr('vati.app.service.build_adapter',lambda *a,**k:adapter)
    ac,app=client
    app.state.onboarding.control=LocalAccountControl(str(registry.path),str(tmp_path),operation_ledger=dsn)
    app.state.account_lifecycle.bind_local_admission_verifier()
    handlers=app.state.onboarding.control.handlers
    return NS(ac=ac,dsn=dsn,namespace=namespace,alias=alias,account=account,handlers=handlers,registry=registry.path,secret=secret,view=view)


@pytest.mark.asyncio
async def test_actual_pg_live_runtime_prevents_destructive_unlink(pg_native):
    n=pg_native;store=PostgresLeaseStore(n.dsn)
    actor=AccountRuntimeLease(store,account_alias=n.alias,instance_id='actual-pg-runtime')
    assert actor.acquire().permits_orders;before=n.secret.read_bytes()
    try:
        refused=await immediate_challenge(n.ac,n.alias,expected_status=409)
        assert refused.status_code==409 and 'runtime is active' in refused.text
        assert n.secret.read_bytes()==before and AccountRegistry(n.registry).get(n.alias)
    finally:actor.release();store.close()


@pytest.mark.asyncio
async def test_actual_pg_first_retirement_owns_the_previously_absent_lease_row(pg_native):
    n=pg_native;store=PostgresLeaseStore(n.dsn)
    try:assert store.read(n.alias) is None
    finally:store.close()
    body,_=await immediate_challenge(n.ac,n.alias)
    response=await n.ac.post('/v1/trading/accounts/action',json=body)
    assert response.status_code==200,response.text
    result=response.json()
    assert result['removed'] is True and result['remote_account_closed'] is False
    assert not n.secret.exists() and n.alias not in AccountRegistry(n.registry).accounts


@pytest.mark.asyncio
async def test_actual_pg_row_guard_fences_a_competing_actor_even_beyond_lease_ttl(pg_native,monkeypatch):
    import json,psycopg
    import commander.account_lifecycle as lifecycle
    n=pg_native;entered=Event();release=Event();diagnostics=[]
    def snapshot():
        registry=AccountRegistry(n.registry);row=registry._lifecycles.get(n.alias)
        # Only fixed stage enums escape; no body values, paths or private keys.
        with psycopg.connect(n.dsn) as db:
            exists=db.execute("SELECT to_regclass('vati.account_unlink_facts')").fetchone()[0]
            facts=[] if exists is None else db.execute(
                'SELECT body_json FROM vati.account_unlink_facts WHERE namespace=%s AND operation_id=%s ORDER BY seq',
                (n.namespace,body['approval_proof']['challenge_id'])).fetchall()
        kinds={'PLAN','EPOCH','STEP','RESOLUTION'};states={'MAY_BEGIN','DONE'}
        stages=[]
        for fact in facts:
            payload=json.loads(fact[0])['payload'];kind=payload.get('kind')
            state=payload.get('data',{}).get('state')
            stages.append({'kind':kind if kind in kinds else 'OTHER',
                'state':state if state in states else None})
        phase=row.get('phase') if row else None
        return {'account_present':n.alias in registry.accounts,'lifecycle_phase':phase if phase in
            {'DISCONNECTING','DISCONNECTED','DELETING','PENDING_ARCHIVE','ARCHIVED','RELINK_REQUIRED'} else None,
            'private_facts':stages}
    monkeypatch.setattr(lifecycle,'invoke_account_effect',
        _observe_native_failure(lifecycle.invoke_account_effect,diagnostics,snapshot))
    body,_=await immediate_challenge(n.ac,n.alias)
    n.view.block=entered;n.view.release=release
    store=PostgresLeaseStore(n.dsn);other=AccountRuntimeLease(store,account_alias=n.alias,instance_id='competing-native-runtime')
    with ThreadPoolExecutor(max_workers=2) as pool:
        removal=asyncio.create_task(n.ac.post('/v1/trading/accounts/action',json=body))
        try:
            assert await asyncio.to_thread(entered.wait,5)
            current=store.read(n.alias);assert current and current.holder_instance_id.startswith('commander-unlink:')
            competing=pool.submit(other.acquire,now_ms=current.expires_at_ms+1)
            assert not competing.done()
            # The second actor has an explicitly later logical clock. The
            # actual DB row guard, rather than an unexpired timestamp, fences it.
            assert not release.wait(timeout=.15)
            assert not competing.done()
        finally:release.set()
        removed=await asyncio.wait_for(removal,5)
        assert removed.status_code==200 and removed.json()['removed'] is True,(removed.text,diagnostics)
        result=competing.result(timeout=5)
        if not result.permits_orders:
            # Retirement releases its row lock before expiring the lease. A
            # waiter may read the old lease, then lose CAS to that expiry. This
            # is a healthy refusal, not a promise that the first attempt wins.
            assert result.outcome is LeaseOutcome.REFUSED_HELD_BY_OTHER
            assert result.detail=='lost compare-and-set race'
            assert other.acquire(now_ms=current.expires_at_ms+2).permits_orders
        assert n.alias not in AccountRegistry(n.registry).accounts
        sent=[]
        adapter=bind_entry_authority(NS(submit=lambda *a,**k:sent.append('unexpected SDK effect')),
            AccountRegistry(n.registry),n.account)
        command=OrderCommand('after-unlink','d'*64,'original',n.alias,'mt5','EURUSD',Direction.LONG,
            'MARKET',D('.1'),D('1.1'),D('1.09'),StopMode.VENUE,LossModel.STOP_DISTANCE).sealed()
        assert adapter.submit(command,now_ms=int(time.time()*1000)).status=='REJECTED' and not sent
    other.release();store.close()
