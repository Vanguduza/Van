"""Independent SQL writers, durable original order recovery and scope isolation."""
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
import threading
from decimal import Decimal as D

import pytest

from test_postgres_ledger_isolation import pg_dsn
from test_native_order_book import setup_order, capture
from vati.core.ledger import LedgerError
from vati.core.ledger_pg import PostgresLedger
from vati.execution.ctrader.orders import NativeOrderObservation
from vati.execution.native_order_book import NativeOrderBook, NativeOrderUnknown
from vati.risk.physical_pending import PhysicalPendingRisk


def test_pg_original_order_reopens_without_provider_and_other_ledger_is_isolated(pg_dsn, tmp_path, eurusd):
    ledger = PostgresLedger(pg_dsn, ledger_name='order-source')
    reopened = PostgresLedger(pg_dsn, ledger_name='order-source')
    foreign = PostgresLedger(pg_dsn, ledger_name='order-foreign')
    try:
        parts = setup_order(tmp_path, eurusd, ledger=ledger)
        _, adapter, book, clock, command, binding, _ = parts
        receipt = capture(parts); count = ledger.count(); calls = len(adapter.transport.calls)
        clock['ms'] += 999999
        recovery = NativeOrderBook(reopened, clock=lambda: clock['ms'])
        assert recovery.lookup('query-1')['receipt'] == receipt
        assert recovery.capture(None, 'query-1', command.command_hash, binding['source_ref'], 2,
                                deadline_ms=1) == receipt
        assert NativeOrderBook(foreign).lookup('query-1') is None and foreign.count() == 0
        assert ledger.count() == count and len(adapter.transport.calls) == calls and ledger.verify_chain()[0]
    finally:
        foreign.close(); reopened.close(); ledger.close()


def test_pg_recreated_pending_owner_retains_native_contradiction(pg_dsn, tmp_path, eurusd):
    ledger = PostgresLedger(pg_dsn, ledger_name='pending-order-source')
    reopened = PostgresLedger(pg_dsn, ledger_name='pending-order-source')
    try:
        parts = setup_order(tmp_path, eurusd, ledger=ledger,
            receipt_changes={'status': 'REJECTED', 'filled_qty': D(0), 'average_fill': None})
        _, _, _, clock, _, _, context = parts
        warm = PhysicalPendingRisk(ledger, context, now_ms=clock['ms'])
        assert warm.refresh((), now_ms=clock['ms']) == ()
        capture(parts)
        with pytest.raises(ValueError, match='native order'): warm.refresh((), now_ms=clock['ms'])
        with pytest.raises(ValueError, match='native order'):
            PhysicalPendingRisk(reopened, context, now_ms=clock['ms'])
        assert ledger.verify_chain()[0]
    finally: reopened.close(); ledger.close()


def test_pg_concurrent_connections_publish_exactly_one_original_order(pg_dsn, tmp_path, eurusd):
    ledger = PostgresLedger(pg_dsn, ledger_name='concurrent-order')
    try:
        parts = setup_order(tmp_path, eurusd, ledger=ledger)
        _, adapter, book, clock, command, binding, context = parts
        observation = adapter.order_details(2, context=context, deadline_ms=clock['ms']+1000).body()
        barrier = threading.Barrier(2)
        def write():
            other = PostgresLedger(pg_dsn, ledger_name='concurrent-order')
            try:
                owned = NativeOrderBook(other, clock=lambda: clock['ms']); barrier.wait(timeout=10)
                return owned.record('same-query', command.command_hash, binding['source_ref'],
                                    NativeOrderObservation.from_body(observation))
            finally: other.close()
        count = ledger.count()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: write(), range(2)))
        assert results[0] == results[1] == book.lookup('same-query')['receipt']
        assert ledger.count() == count+1 and ledger.verify_chain()[0]
    finally: ledger.close()


def test_pg_staged_caller_never_queries_original_order(pg_dsn, tmp_path, eurusd):
    ledger = PostgresLedger(pg_dsn, ledger_name='staged-order')
    try:
        parts = setup_order(tmp_path, eurusd, ledger=ledger)
        _, adapter, _, _, _, _, _ = parts
        count = ledger.count(); calls = len(adapter.transport.calls)
        with ledger.atomic():
            with pytest.raises(LedgerError, match='committed_source_read_requires'): capture(parts)
        assert ledger.count() == count and len(adapter.transport.calls) == calls
    finally: ledger.close()


def test_pg_lost_commit_ack_uses_original_request_without_requery(pg_dsn, tmp_path, eurusd, monkeypatch):
    ledger = PostgresLedger(pg_dsn, ledger_name='unknown-order')
    try:
        parts = setup_order(tmp_path, eurusd, ledger=ledger)
        _, adapter, book, _, _, _, _ = parts
        original = ledger.atomic
        @contextmanager
        def lost_ack():
            with original(): yield ledger
            raise OSError('fixture original PG commit ACK loss')
        monkeypatch.setattr(ledger, 'atomic', lost_ack)
        with pytest.raises(NativeOrderUnknown) as error: capture(parts)
        assert error.value.request_id == 'query-1'
        monkeypatch.setattr(ledger, 'atomic', original)
        count = ledger.count(); calls = len(adapter.transport.calls)
        assert capture(parts) == book.lookup('query-1')['receipt']
        assert ledger.count() == count and len(adapter.transport.calls) == calls and ledger.verify_chain()[0]
    finally: ledger.close()
