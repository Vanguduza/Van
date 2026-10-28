"""Real isolated SQL ownership, original readback and uncertain completion."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import threading
import pytest

from test_postgres_ledger_isolation import pg_dsn
from test_native_close_movement import originals
from vati.core import EventKind
from vati.core.ledger_pg import PostgresLedger
from vati.core.units import UnitError
from vati.funding.movement_journal import FinancialMovementBook,MovementPublicationUnknown


def test_independent_postgres_close_writers_retain_one_original_completion(pg_dsn):
    ledger=PostgresLedger(pg_dsn,ledger_name='native-close-race')
    try:
        before,source,scope=originals(ledger);initial=ledger.count();start=threading.Barrier(2)
        def publish():
            connection=PostgresLedger(pg_dsn,ledger_name='native-close-race')
            try:
                start.wait(5)
                return FinancialMovementBook(connection,clock=lambda:7000).publish_close('original-close',
                    scope_hash=scope,native_id=1,statement_ref=source.hash,balance_anchor_ref=before.hash)
            finally:connection.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs=[pool.submit(publish) for _ in range(2)]
            receipts=[job.result(timeout=15) for job in jobs]
        assert receipts[0]==receipts[1] and ledger.count()==initial+1
        assert ledger.count(EventKind.FINANCIAL_MOVEMENT)==1 and ledger.verify_chain()[0]
        assert receipts[0]['execution_authority'] is receipts[0]['risk_capital_qualified'] is False
    finally:ledger.close()


def test_actual_postgres_close_commit_ack_loss_recovers_original_without_new_write(pg_dsn,monkeypatch):
    ledger=PostgresLedger(pg_dsn,ledger_name='native-close-ack')
    try:
        before,source,scope=originals(ledger);journal=FinancialMovementBook(ledger,clock=lambda:7000)
        atomic=ledger.atomic
        @contextmanager
        def lost_ack():
            outer=ledger._conn.info.transaction_status==0
            with atomic():yield ledger
            if outer:raise OSError('fixture original close posting commit ACK lost')
        monkeypatch.setattr(ledger,'atomic',lost_ack)
        with pytest.raises(MovementPublicationUnknown) as error:
            journal.publish_close('original-close',scope_hash=scope,native_id=1,
                statement_ref=source.hash,balance_anchor_ref=before.hash)
        assert error.value.request_id=='original-close'
        monkeypatch.setattr(ledger,'atomic',atomic)
        count=ledger.count();original=journal.lookup('original-close')
        journal.clock=lambda:pytest.fail('replay resampled original availability')
        assert journal.publish_close('original-close',scope_hash=scope,native_id=1,
            statement_ref=source.hash,balance_anchor_ref=before.hash)==original
        assert ledger.count()==count and ledger.count(EventKind.FINANCIAL_MOVEMENT)==1
    finally:ledger.close()


def test_another_postgres_namespace_cannot_borrow_original_native_close_or_anchor(pg_dsn):
    first=PostgresLedger(pg_dsn,ledger_name='native-close-original')
    other=PostgresLedger(pg_dsn,ledger_name='native-close-empty')
    try:
        before,source,scope=originals(first)
        original=FinancialMovementBook(first,clock=lambda:7000).publish_close('original-close',
            scope_hash=scope,native_id=1,statement_ref=source.hash,balance_anchor_ref=before.hash)
        journal=FinancialMovementBook(other,clock=lambda:7000)
        assert journal.lookup('original-close') is None
        with pytest.raises(UnitError):journal.publish_close('original-close',scope_hash=scope,native_id=1,
            statement_ref=source.hash,balance_anchor_ref=before.hash)
        assert other.count()==0 and FinancialMovementBook(first).lookup('original-close')==original
    finally:other.close();first.close()


def test_close_publication_clock_is_rechecked_after_actual_postgres_writer_lock(pg_dsn):
    import time
    from dataclasses import replace
    from test_native_balance_reconciliation import observe,closed
    ledger=PostgresLedger(pg_dsn,ledger_name='native-close-clock');blocker=None
    try:
        anchor,source,scope=originals(ledger)
        FinancialMovementBook(ledger,clock=lambda:7000).publish_close('first-close',scope_hash=scope,
            native_id=1,statement_ref=source.hash,balance_anchor_ref=anchor.hash)
        second=replace(closed(balance='115',version=3,at=2500),native_id=2)
        observe(ledger,deals=(closed(),second))
        source=list(ledger.iter(EventKind.FUNDING_DEAL_STATEMENT))[-1];count=ledger.count()
        blocker=PostgresLedger(pg_dsn,ledger_name='native-close-clock')
        blocker._conn.execute('SELECT chain_hash FROM vati.chain_head WHERE ledger=%s FOR UPDATE',('native-close-clock',))
        ready=threading.Event();backend={};clock={'ms':8000}
        def publish():
            connection=PostgresLedger(pg_dsn,ledger_name='native-close-clock')
            try:
                backend['pid']=connection._conn.info.backend_pid;ready.set()
                return FinancialMovementBook(connection,clock=lambda:clock['ms']).publish_close('second-close',
                    scope_hash=scope,native_id=2,statement_ref=source.hash,
                    balance_anchor_ref=source.hash,anchor_native_id=1)
            finally:connection.close()
        with ThreadPoolExecutor(max_workers=1) as pool:
            job=pool.submit(publish)
            try:
                assert ready.wait(5);end=time.monotonic()+5;waiting=False
                while time.monotonic()<end and not job.done():
                    blocker._conn.execute('SELECT pg_stat_clear_snapshot()')
                    row=blocker._conn.execute('SELECT wait_event_type,query FROM pg_stat_activity WHERE pid=%s',
                        (backend['pid'],)).fetchone()
                    if row and row[0]=='Lock' and 'chain_head' in row[1] and 'FOR UPDATE' in row[1]:
                        waiting=True;break
                    time.sleep(.01)
                assert waiting,'close publisher never reached the genuine PostgreSQL writer lock'
                clock['ms']=6999
            finally:blocker._conn.rollback()
            with pytest.raises(UnitError,match='PUBLICATION_CLOCK_MOVED_BACKWARDS'):job.result(timeout=15)
        assert ledger.count()==count and ledger.count(EventKind.FINANCIAL_MOVEMENT)==1
        assert ledger.verify_chain()[0]
    finally:
        if blocker is not None:blocker._conn.rollback();blocker.close()
        ledger.close()
