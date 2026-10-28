"""Actual PostgreSQL hold writers over explicit migrated source fixtures."""
from concurrent.futures import ThreadPoolExecutor
import threading
import pytest

from test_postgres_ledger_isolation import pg_dsn
from test_current_entry_risk_source_postgres import restore_original_history
from test_provisional_resource_book import prepared
from vati.core import EventKind
from vati.core.ledger_pg import PostgresLedger
from vati.risk.provisional_resource_book import ProvisionalResourceBook,ResourceHoldError


def test_independent_postgres_writers_retain_one_original_provisional_hold(pg_dsn,tmp_path,eurusd):
    sdk,clock,original,command,margin_ref,current_ref,authority,old,router=prepared(tmp_path,eurusd)
    ledger=PostgresLedger(pg_dsn,ledger_name='provisional-hold-race')
    try:
        restore_original_history(ledger,original);before=ledger.count();start=threading.Barrier(2)
        def reserve():
            connection=PostgresLedger(pg_dsn,ledger_name='provisional-hold-race')
            try:
                start.wait(5)
                return ProvisionalResourceBook(connection,clock=lambda:clock['ms']).reserve_entry(command,margin_ref,current_ref,authority)
            finally:connection.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs=[pool.submit(reserve) for _ in range(2)];receipts=[job.result(timeout=15) for job in jobs]
        assert receipts[0]==receipts[1] and ledger.count()==before+1
        assert receipts[0]['eligible_for_native_dispatch'] is False
        assert ledger.count(EventKind.ORDER_COMMAND)==0 and not sdk.sent and ledger.verify_chain()[0]
    finally:ledger.close();original.close()


def test_provisional_hold_expiry_is_rechecked_after_an_actual_postgres_row_lock(pg_dsn,tmp_path,eurusd):
    import time
    sdk,clock,original,command,margin_ref,current_ref,authority,old,router=prepared(tmp_path,eurusd)
    ledger=PostgresLedger(pg_dsn,ledger_name='provisional-expiry');blocker=None
    try:
        restore_original_history(ledger,original);before=ledger.count()
        blocker=PostgresLedger(pg_dsn,ledger_name='provisional-expiry')
        blocker._conn.execute('SELECT chain_hash FROM vati.chain_head WHERE ledger=%s FOR UPDATE',('provisional-expiry',))
        ready=threading.Event();backend={}
        def reserve():
            connection=PostgresLedger(pg_dsn,ledger_name='provisional-expiry')
            try:
                backend['pid']=connection._conn.info.backend_pid;ready.set()
                return ProvisionalResourceBook(connection,clock=lambda:clock['ms']).reserve_entry(command,margin_ref,current_ref,authority)
            finally:connection.close()
        with ThreadPoolExecutor(max_workers=1) as pool:
            job=pool.submit(reserve)
            try:
                assert ready.wait(5)
                end=time.monotonic()+5;waiting=False
                while time.monotonic()<end and not job.done():
                    blocker._conn.execute('SELECT pg_stat_clear_snapshot()')
                    row=blocker._conn.execute('SELECT wait_event_type,query FROM pg_stat_activity WHERE pid=%s',(backend['pid'],)).fetchone()
                    if row and row[0]=='Lock' and 'chain_head' in row[1] and 'FOR UPDATE' in row[1]:
                        waiting=True;break
                    time.sleep(.01)
                assert waiting,'source hold never reached the actual PostgreSQL writer lock'
                clock['ms']=command.expires_at_ms
            finally:blocker._conn.rollback()
            with pytest.raises(ResourceHoldError,match='EXPIRED_OR_CLOCK_REGRESSED'):job.result(timeout=15)
        assert ledger.count()==before and not sdk.sent and ledger.verify_chain()[0]
    finally:
        if blocker is not None:blocker._conn.rollback();blocker.close()
        ledger.close();original.close()


def test_distinct_postgres_entries_cannot_allocate_the_same_last_margin_budget(pg_dsn,tmp_path,eurusd):
    from decimal import Decimal
    from test_entry_resource_groups import another_entry
    sdk,clock,original,command,margin,current,authority,old,router=prepared(tmp_path,eurusd,
        native_margin=Decimal('2500'),mandate_changes={'max_positions_per_instrument':2})
    other,other_margin,other_current=another_entry(original,command,authority,router,clock)
    ledger=PostgresLedger(pg_dsn,ledger_name='distinct-hold-budget')
    try:
        restore_original_history(ledger,original);before=ledger.count();start=threading.Barrier(2)
        entries=[(command,margin,current),(other,other_margin,other_current)]
        def reserve(entry):
            connection=PostgresLedger(pg_dsn,ledger_name='distinct-hold-budget')
            try:
                start.wait(5)
                try:return ProvisionalResourceBook(connection,clock=lambda:clock['ms']).reserve_entry(*entry,authority)
                except ResourceHoldError as error:return error
            finally:connection.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(reserve,e) for e in entries]
            results=[job.result(timeout=20) for job in futures]
        winners=[i for i,r in enumerate(results) if isinstance(r,dict)]
        assert len(winners)==1 and ledger.count()==before+1
        winner=winners[0];loser=1-winner
        assert isinstance(results[loser],ResourceHoldError)
        assert str(results[loser]) in {'RESOURCE_SOURCE_CHANGED_RETRY_ORIGINAL',
            'RESOURCE_CAPACITY_EXCEEDED:margin_floor_equity'}
        book=ProvisionalResourceBook(ledger,clock=lambda:clock['ms'])
        assert book.reserve_entry(*entries[winner],authority)==results[winner]
        with pytest.raises(ResourceHoldError,match='RESOURCE_CAPACITY_EXCEEDED:margin_floor_equity'):
            book.reserve_entry(*entries[loser],authority)
        assert ledger.count()==before+1 and ledger.verify_chain()[0]
        assert not sdk.sent and ledger.count(EventKind.ORDER_COMMAND)==0
    finally:ledger.close();original.close()
