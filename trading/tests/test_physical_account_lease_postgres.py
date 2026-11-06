"""An actual SQL peer cannot take physical scope during either final guard."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, nullcontext
import threading
import time

import pytest

from test_postgres_ledger_isolation import pg_dsn
from vati.accounts.physical_scope import ExpectedPhysicalScope
from vati.app.account_lease import PostgresLeaseStore, LeaseOutcome, LeaseStoreUnavailable
from vati.app.physical_account_lease import PhysicalAccountRuntimeLease
from vati.core.ledger_pg import PostgresLedger


@pytest.mark.parametrize('nested_operation', ['fence', 'nested_guard', 'sql_error', 'body_error'])
def test_physical_peer_waits_until_the_complete_submission_scope_exits(pg_dsn, monkeypatch, nested_operation):
    import psycopg  # Admitted by the unchanged canonical actual-PG fixture.
    with closing(PostgresLedger(pg_dsn)):
        pass
    scope = ExpectedPhysicalScope('ctrader', 'demo.ctraderapi.com', '123')
    original = PostgresLeaseStore(pg_dsn)
    owner = PhysicalAccountRuntimeLease(original, physical_scope=scope,
        account_alias='native_one', instance_id='original', ttl_ms=1000)
    requested = threading.Event(); peer_pid = []

    def takeover():
        class ObservedStore(PostgresLeaseStore):
            def write_if(self, expected, new):
                if new.account_alias == scope.lease_key:
                    requested.set()
                return super().write_if(expected, new)
        store = ObservedStore(pg_dsn)
        try:
            peer_pid.append(store._conn.info.backend_pid)
            peer = PhysicalAccountRuntimeLease(store, physical_scope=scope,
                account_alias='native_two', instance_id='peer', ttl_ms=1000)
            return peer.acquire(now_ms=1001)
        finally:
            store.close()

    failure = RuntimeError('original composite guarded failure')
    try:
        assert owner.acquire(now_ms=0).outcome is LeaseOutcome.GRANTED
        logical_epoch = owner.epoch
        with psycopg.connect(pg_dsn, autocommit=True) as observer, ThreadPoolExecutor(max_workers=1) as executor:
            before = observer.execute('SELECT lease_epoch FROM vati.account_runtime_leases WHERE account_alias=%s',
                                      (scope.lease_key,)).fetchone()[0]
            expected_error = pytest.raises(RuntimeError) if nested_operation == 'body_error' else nullcontext()
            with expected_error as caught:
                with owner.submission_guard(logical_epoch, now_ms=1) as allowed:
                    assert allowed is True
                    if nested_operation == 'fence':
                        assert owner.fence(logical_epoch, now_ms=2, min_validity_ms=0)
                    elif nested_operation == 'nested_guard':
                        with owner.submission_guard(logical_epoch, now_ms=2) as nested:
                            assert nested is True
                    elif nested_operation == 'sql_error':
                        def server_query_error(_):
                            original._conn.execute('SELECT 1 / 0')
                        with monkeypatch.context() as patch:
                            patch.setattr(original, '_from_row', server_query_error)
                            with pytest.raises(LeaseStoreUnavailable):
                                original.read(scope.lease_key)
                    future = executor.submit(takeover)
                    assert requested.wait(timeout=5)
                    waiting = False
                    for _ in range(100):
                        if future.done():
                            break
                        row = observer.execute('SELECT wait_event_type FROM pg_stat_activity WHERE pid=%s',
                                               (peer_pid[0],)).fetchone()
                        if row is not None and row[0] == 'Lock':
                            waiting = True
                            break
                        time.sleep(.01)
                    assert waiting, 'physical peer did not remain blocked by the outer submission owner'
                    assert not future.done()
                    if nested_operation == 'body_error':
                        raise failure
            if nested_operation == 'body_error':
                assert caught.value is failure
            result = future.result(timeout=5)
            assert result.outcome is LeaseOutcome.GRANTED
            assert result.lease.account_alias == 'native_two'
            after = observer.execute('SELECT lease_epoch FROM vati.account_runtime_leases WHERE account_alias=%s',
                                     (scope.lease_key,)).fetchone()[0]
            assert after > before
            assert owner.fence(logical_epoch, now_ms=1002, min_validity_ms=0) is False
    finally:
        original.close()
