"""A read or inner guard cannot release a live outer submission row lock.

Actual PostgreSQL arbitration; synthetic clocks, no venue or financial effect.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import threading
import time

import psycopg
import pytest

from test_postgres_ledger_isolation import pg_dsn
from vati.app.account_lease import AccountRuntimeLease, PostgresLeaseStore, LeaseOutcome, LeaseStoreUnavailable
from vati.core.ledger_pg import PostgresLedger


@pytest.mark.parametrize('nested_operation', ['none', 'read', 'fence', 'guard', 'write', 'close',
                                             'read_error', 'guard_error', 'guard_entry_error', 'cross_thread_read',
                                             'sql_read_error', 'sql_guard_entry_error'])
def test_outer_guard_keeps_actual_row_lock_across_nested_operations(pg_dsn, nested_operation, monkeypatch):
    with closing(PostgresLedger(pg_dsn)):
        pass
    original = PostgresLeaseStore(pg_dsn)
    owner = AccountRuntimeLease(original, account_alias='guard_owner', instance_id='original', ttl_ms=1000)
    requested = threading.Event()
    peer_pid = []

    def peer_takeover():
        class ObservedStore(PostgresLeaseStore):
            def write_if(self, expected, new):
                requested.set()
                return super().write_if(expected, new)
        store = ObservedStore(pg_dsn)
        try:
            peer_pid.append(store._conn.info.backend_pid)
            peer = AccountRuntimeLease(store, account_alias='guard_owner', instance_id='peer', ttl_ms=1000)
            return peer.acquire(now_ms=1001)
        finally:
            store.close()

    try:
        assert owner.acquire(now_ms=0).outcome is LeaseOutcome.GRANTED
        epoch = owner.epoch
        with psycopg.connect(pg_dsn, autocommit=True) as observer, ThreadPoolExecutor(max_workers=2) as executor:
            borrowed_read = None
            with owner.submission_guard(epoch, now_ms=1) as allowed:
                assert allowed is True
                if nested_operation == 'read':
                    assert original.read('guard_owner').lease_epoch == epoch
                elif nested_operation == 'fence':
                    assert owner.fence(epoch, now_ms=2, min_validity_ms=0) is True
                elif nested_operation == 'guard':
                    with owner.submission_guard(epoch, now_ms=2) as inner:
                        assert inner is True
                elif nested_operation == 'write':
                    with pytest.raises(LeaseStoreUnavailable, match='inside a submission guard'):
                        original.write_if(owner.held, owner.held)
                elif nested_operation == 'close':
                    with pytest.raises(LeaseStoreUnavailable, match='inside a submission guard'):
                        original.close()
                    assert original.read('guard_owner').lease_epoch == epoch
                elif nested_operation == 'read_error':
                    def invalid_row(_):
                        raise ValueError('injected decode failure')
                    with monkeypatch.context() as patch:
                        patch.setattr(original, '_from_row', invalid_row)
                        with pytest.raises(LeaseStoreUnavailable, match='decode failure'):
                            original.read('guard_owner')
                elif nested_operation == 'guard_error':
                    with pytest.raises(RuntimeError, match='original guarded failure'):
                        with owner.submission_guard(epoch, now_ms=2) as inner:
                            assert inner is True
                            raise RuntimeError('original guarded failure')
                elif nested_operation == 'guard_entry_error':
                    def invalid_guard_row(_):
                        raise ValueError('injected guard decode failure')
                    with monkeypatch.context() as patch:
                        patch.setattr(original, '_from_row', invalid_guard_row)
                        with owner.submission_guard(epoch, now_ms=2) as inner:
                            assert inner is False
                elif nested_operation in {'sql_read_error', 'sql_guard_entry_error'}:
                    def server_query_error(_):
                        # An actual PostgreSQL error, not a Python decoder error.
                        original._conn.execute('SELECT 1 / 0')
                    with monkeypatch.context() as patch:
                        patch.setattr(original, '_from_row', server_query_error)
                        if nested_operation == 'sql_read_error':
                            with pytest.raises(LeaseStoreUnavailable):
                                original.read('guard_owner')
                        else:
                            with owner.submission_guard(epoch, now_ms=2) as inner:
                                assert inner is False
                elif nested_operation == 'cross_thread_read':
                    read_requested = threading.Event()
                    def read_from_peer_thread():
                        read_requested.set()
                        return original.read('guard_owner')
                    borrowed_read = executor.submit(read_from_peer_thread)
                    assert read_requested.wait(timeout=5)
                    assert not borrowed_read.done()
                future = executor.submit(peer_takeover)
                assert requested.wait(timeout=5)
                waiting_on_actual_lock = False
                for _ in range(100):
                    if future.done():
                        break
                    row = observer.execute('SELECT wait_event_type FROM pg_stat_activity WHERE pid=%s',
                                           (peer_pid[0],)).fetchone()
                    if row is not None and row[0] == 'Lock':
                        waiting_on_actual_lock = True
                        break
                    time.sleep(.01)
                assert waiting_on_actual_lock, 'peer did not remain blocked by the original submission row lock'
                assert not future.done()
                if borrowed_read is not None:
                    assert not borrowed_read.done()
            result = future.result(timeout=5)
            assert result.outcome is LeaseOutcome.GRANTED
            assert result.lease.lease_epoch > epoch
            if borrowed_read is not None:
                assert borrowed_read.result(timeout=5) is not None
            assert owner.fence(epoch, now_ms=1002, min_validity_ms=0) is False
    finally:
        original.close()
