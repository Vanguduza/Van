"""Real PostgreSQL read isolation and native period evidence, never broker execution."""
from concurrent.futures import ThreadPoolExecutor
import threading
import pytest
from test_postgres_ledger_isolation import pg_dsn
from test_ledger_read_snapshot import event
from test_native_deal_journal import statement
from test_native_balance_reconciliation import mark,snapshot,observe
from vati.core.ledger import LedgerError
from vati.core.ledger_pg import PostgresLedger
from vati.funding.deal_journal import DealBook
from vati.funding.reconciliation import period_report

def test_postgres_owner_snapshot_is_repeatable_without_blocking_the_order_writer(pg_dsn):
    reader=PostgresLedger(pg_dsn,ledger_name='one');reader.append(event(1));committed=threading.Event()
    def write():
        writer=PostgresLedger(pg_dsn,ledger_name='one')
        try:writer.append(event(2));committed.set();return writer.count()
        finally:writer.close()
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            with reader.read_snapshot():
                assert reader.count()==1
                pending=executor.submit(write)
                assert committed.wait(2),'a read projection reserved the financial chain head'
                assert pending.result(timeout=2)==2 and reader.count()==1 and reader.verify_incremental()[0]
            assert reader.count()==2 and reader.verify_incremental()[0]
    finally:reader.close()

def test_postgres_nested_reads_refuse_appends_and_leave_the_connection_usable(pg_dsn):
    ledger=PostgresLedger(pg_dsn,ledger_name='one');ledger.append(event(1))
    try:
        with ledger.read_snapshot():
            with ledger.read_snapshot():assert ledger.count()==1
            with pytest.raises(LedgerError,match='read-only'):ledger.append(event(2))
            with pytest.raises(LedgerError,match='read-only'):
                with ledger.atomic():pass
        ledger.append(event(3));assert ledger.count()==2
    finally:ledger.close()

def test_postgres_original_deal_availability_and_named_scope_survive_native_read_projection(pg_dsn):
    a=PostgresLedger(pg_dsn,ledger_name='one');b=PostgresLedger(pg_dsn,ledger_name='two')
    try:
        source=statement();book=DealBook(a,clock=lambda:6000);receipt=book.record_statement(source)
        view=book.observations(source.scope_hash)
        assert view['deals'][0]['original_statement_ref']==receipt['statement_ref']
        assert view['deals'][0]['received_at_ms']==6000 and view['knowledge_through_received_ms']==6000
        assert DealBook(b).observations(source.scope_hash)['state']=='NO_DATA'
    finally:a.close();b.close()

def test_postgres_period_uses_only_its_original_native_account_marks_and_cash_history(pg_dsn):
    ledger=PostgresLedger(pg_dsn,ledger_name='one')
    try:
        snapshot(ledger,mark(1000));snapshot(ledger,mark(2000,equity='80'));snapshot(ledger,mark(3000,equity='110'))
        report=period_report(ledger,observe(ledger))
        assert report['state']=='MEASURED' and report['balance_state']=='RECONCILED'
        assert report['performance']['worst_observed_drawdown']=='0.2' and report['return_qualification']=='NOT_ISSUED'
        assert report['knowledge_through_received_ms']==6000
    finally:ledger.close()
