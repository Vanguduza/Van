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
from vati.app.account_lease import AccountRuntimeLease, PostgresLeaseStore, LeaseOutcome
from vati.core.ledger_pg import PostgresLedger


@pytest.mark.parametrize('nested_operation', ['none', 'read', 'fence', 'guard'])
def test_outer_guard_keeps_actual_row_lock_across_nested_operations(pg_dsn, nested_operation):
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
        with psycopg.connect(pg_dsn, autocommit=True) as observer, ThreadPoolExecutor(max_workers=1) as executor:
            with owner.submission_guard(epoch, now_ms=1) as allowed:
                assert allowed is True
                if nested_operation == 'read':
                    assert original.read('guard_owner').lease_epoch == epoch
                elif nested_operation == 'fence':
                    assert owner.fence(epoch, now_ms=2, min_validity_ms=0) is True
                elif nested_operation == 'guard':
                    with owner.submission_guard(epoch, now_ms=2) as inner:
                        assert inner is True
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
            result = future.result(timeout=5)
            assert result.outcome is LeaseOutcome.GRANTED
            assert result.lease.lease_epoch > epoch
            assert owner.fence(epoch, now_ms=1002, min_validity_ms=0) is False
    finally:
        original.close()
