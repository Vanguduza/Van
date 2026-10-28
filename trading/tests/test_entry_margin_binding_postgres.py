"""Actual PostgreSQL publication, original replay and independent writer CAS."""
from concurrent.futures import ThreadPoolExecutor
import threading

from test_postgres_ledger_isolation import pg_dsn
from test_entry_margin_binding import mt5_entry,entry_command
from vati.core import EventKind
from vati.core.ledger_pg import PostgresLedger
from vati.risk.native_margin_book import NativeMarginBook
from conftest import NOW


def test_original_entry_binding_survives_postgres_reopen_and_other_scope_isolation(pg_dsn,tmp_path,eurusd):
    ledger=PostgresLedger(pg_dsn,ledger_name='entry-margin-original');other=None;reopened=None
    try:
        sdk,adapter,now,ledger,event,book=mt5_entry(tmp_path,eurusd,ledger=ledger)
        cmd=entry_command(event);receipt=book.capture_entry(adapter,event.hash,cmd,deadline_ms=NOW*1000+2000)
        count=ledger.count();calls=len(sdk.margin_calls)
        reopened=PostgresLedger(pg_dsn,ledger_name='entry-margin-original')
        history=NativeMarginBook(reopened,clock=lambda:NOW*1000+900000)
        assert history.lookup_entry(cmd.command_hash,receipt['source_ref'])['receipt']==receipt
        assert history.bind_entry(event.hash,cmd,receipt['source_ref'])==receipt
        other=PostgresLedger(pg_dsn,ledger_name='entry-margin-other')
        assert NativeMarginBook(other).lookup_entry(cmd.command_hash,receipt['source_ref']) is None
        assert ledger.count()==count and other.count()==0 and len(sdk.margin_calls)==calls and not sdk.sent
        assert ledger.count(EventKind.ORDER_COMMAND)==0 and ledger.verify_chain()[0]
    finally:
        if reopened is not None:reopened.close()
        if other is not None:other.close()
        ledger.close()


def test_independent_postgres_binding_writers_retain_one_original_completion(pg_dsn,tmp_path,eurusd):
    ledger=PostgresLedger(pg_dsn,ledger_name='entry-margin-racing')
    try:
        sdk,adapter,now,ledger,event,book=mt5_entry(tmp_path,eurusd,ledger=ledger)
        cmd=entry_command(event);raw=book.capture(adapter,event.hash,cmd.symbol,cmd.quantity,
            price=cmd.entry_price,direction=cmd.direction,deadline_ms=NOW*1000+2000)
        start=threading.Barrier(2);before=ledger.count();calls=len(sdk.margin_calls)
        def bind():
            connection=PostgresLedger(pg_dsn,ledger_name='entry-margin-racing')
            try:
                start.wait(5)
                return NativeMarginBook(connection,clock=lambda:now['ms']).bind_entry(event.hash,cmd,raw['source_ref'])
            finally:connection.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs=[pool.submit(bind) for _ in range(2)];receipts=[j.result(timeout=15) for j in jobs]
        assert receipts[0]==receipts[1] and ledger.count()==before+1
        assert len(sdk.margin_calls)==calls and not sdk.sent and ledger.verify_chain()[0]
    finally:ledger.close()
