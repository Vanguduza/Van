"""Actual PostgreSQL account lease/journal isolation; no broker effects."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal as D
import os
from threading import Event
import time
from types import SimpleNamespace as NS
import uuid

import pytest
from fastapi import HTTPException
from commander.accounts import AccountControlSettings,build_account_handlers,_write_secrets
from vati.accounts import Account,AccountRegistry,CredentialRef
from vati.app.account_lease import AccountRuntimeLease,PostgresLeaseStore,LeaseOutcome
from vati.core.ledger_pg import PostgresLedger
from vati.execution.base import AccountState,Health,OrderCommand,StopMode
from vati.accounts.access import bind_entry_authority
from vati.risk.contracts import Direction,LossModel


@pytest.fixture
def pg_native(tmp_path,monkeypatch):
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
        if view.block is not None:
            view.block.set();assert view.release.wait(timeout=5)
        return AccountState(alias,D('100'),D('100'),'USD',True,server_time_unix_ms=int(time.time()*1000))
    adapter=NS(sync_account=balance,positions=lambda:[],orders=lambda:[],
        heartbeat=lambda **kw:Health(True,0,kw['now_ms']))
    monkeypatch.setattr('vati.app.service.build_adapter',lambda *a,**k:adapter)
    handlers=build_account_handlers(AccountControlSettings(str(registry.path),str(tmp_path),operation_ledger=dsn))
    return NS(dsn=dsn,namespace=namespace,alias=alias,account=account,handlers=handlers,registry=registry.path,secret=secret,view=view)


def test_actual_pg_live_runtime_prevents_destructive_unlink(pg_native):
    n=pg_native;store=PostgresLeaseStore(n.dsn)
    actor=AccountRuntimeLease(store,account_alias=n.alias,instance_id='actual-pg-runtime')
    assert actor.acquire().permits_orders;before=n.secret.read_bytes()
    try:
        with pytest.raises(HTTPException) as refused:n.handlers['account_remove']({'alias':n.alias})
        assert refused.value.status_code==409
        assert n.secret.read_bytes()==before and AccountRegistry(n.registry).get(n.alias)
    finally:actor.release();store.close()


def test_actual_pg_first_retirement_owns_the_previously_absent_lease_row(pg_native):
    n=pg_native;store=PostgresLeaseStore(n.dsn)
    try:assert store.read(n.alias) is None
    finally:store.close()
    result=n.handlers['account_remove']({'alias':n.alias})
    assert result['removed'] is True and result['remote_account_closed'] is False
    assert not n.secret.exists() and n.alias not in AccountRegistry(n.registry).accounts


def test_actual_pg_row_guard_fences_a_competing_actor_even_beyond_lease_ttl(pg_native):
    n=pg_native;entered=Event();release=Event();n.view.block=entered;n.view.release=release
    store=PostgresLeaseStore(n.dsn);other=AccountRuntimeLease(store,account_alias=n.alias,instance_id='competing-native-runtime')
    with ThreadPoolExecutor(max_workers=2) as pool:
        removal=pool.submit(n.handlers['account_remove'],{'alias':n.alias})
        try:
            assert entered.wait(timeout=5)
            current=store.read(n.alias);assert current and current.holder_instance_id.startswith('commander-unlink:')
            competing=pool.submit(other.acquire,now_ms=current.expires_at_ms+1)
            assert not competing.done()
            # The second actor has an explicitly later logical clock. The
            # actual DB row guard, rather than an unexpired timestamp, fences it.
            assert not release.wait(timeout=.15)
            assert not competing.done()
        finally:release.set()
        assert removal.result(timeout=5)['removed'] is True
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
