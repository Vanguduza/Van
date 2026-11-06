"""Original native estimates in isolated real PostgreSQL namespaces."""
from decimal import Decimal as D

import pytest

from conftest import NOW
from test_native_margin_book import setup_book, capture
from test_postgres_ledger_isolation import pg_dsn
from vati.core import EventKind
from vati.core.ledger import LedgerError
from vati.core.ledger_pg import PostgresLedger
from vati.risk.native_margin_book import NativeMarginBook


def test_original_postgres_margin_capture_scope_reopen_and_expired_data_only(pg_dsn,tmp_path,eurusd):
    ledger=PostgresLedger(pg_dsn,ledger_name='original-margin-writer')
    other=PostgresLedger(pg_dsn,ledger_name='other-margin-writer')
    reopened=None
    try:
        ledger,adapter,event,book,now,_=setup_book(tmp_path,eurusd,ledger=ledger)
        receipt=capture(adapter,event,book)
        assert other.count()==0 and NativeMarginBook(other).lookup(receipt['source_ref']) is None
        count=ledger.count();calls=len(adapter.transport.calls)
        reopened=PostgresLedger(pg_dsn,ledger_name='original-margin-writer')
        value=NativeMarginBook(reopened,clock=lambda:(NOW+90*86400)*1000).lookup(receipt['source_ref'])
        assert value['receipt']==receipt
        assert value['observation']['buy_margin']['currency']=='EUR'
        assert value['observation']['execution_authority'] is value['observation']['reservation_qualified'] is False
        assert ledger.count()==count and len(adapter.transport.calls)==calls
        assert ledger.count(EventKind.ORDER_COMMAND)==0 and ledger.verify_chain()[0]
    finally:
        if reopened is not None:reopened.close()
        other.close();ledger.close()


def test_postgres_writer_cannot_treat_its_staged_margin_record_as_original(pg_dsn,tmp_path,eurusd):
    ledger=PostgresLedger(pg_dsn,ledger_name='margin-staged')
    try:
        _,adapter,event,book,now,_=setup_book(tmp_path,eurusd,ledger=ledger)
        before=ledger.count()
        with pytest.raises(LedgerError,match='committed_source_read_requires'):
            with ledger.atomic():capture(adapter,event,book)
        assert ledger.count()==before and not adapter.transport.calls
    finally:ledger.close()
