"""Both MT5 read transports feed the actual isolated PostgreSQL quote owner."""
from decimal import Decimal as D

import pytest

from conftest import NOW,snapshot
from test_mt5_native_margin_book import original,capture
from test_mt5_expected_margin_pull import prepared,roundtrip
from test_mt5_bound_poll import rig
from test_native_risk_history_inputs import record
from test_postgres_ledger_isolation import pg_dsn
from vati.core import EventKind
from vati.core.ledger_pg import PostgresLedger
from vati.risk.native_margin_book import NativeMarginBook


def test_signed_worker_margin_survives_original_postgres_reopen_and_scope_isolation(pg_dsn,tmp_path,eurusd):
    ledger=PostgresLedger(pg_dsn,ledger_name='signed-worker-margin')
    other=PostgresLedger(pg_dsn,ledger_name='other-signed-margin');reopened=None
    try:
        sdk,worker,adapter,now,ledger,event,book=original(tmp_path,eurusd,ledger=ledger)
        receipt=capture(adapter,now,event,book);count=ledger.count();calls=len(sdk.margin_calls)
        reopened=PostgresLedger(pg_dsn,ledger_name='signed-worker-margin')
        read=NativeMarginBook(reopened).lookup(receipt['source_ref'])
        assert read['receipt']==receipt
        assert read['observation']['native_read_identity']['kind']=='SIGNED_MTLS_READ'
        assert read['observation']['native_read_identity']['request_nonce']>0
        assert NativeMarginBook(other).lookup(receipt['source_ref']) is None and other.count()==0
        assert ledger.count()==count and len(sdk.margin_calls)==calls and not sdk.sent
        assert ledger.count(EventKind.ORDER_COMMAND)==0 and ledger.verify_chain()[0]
    finally:
        if reopened is not None:reopened.close()
        other.close();ledger.close()


def test_signed_ea_http_margin_survives_original_postgres_reopen_and_quote_expiry(pg_dsn,tmp_path,eurusd,rig):
    ledger=PostgresLedger(pg_dsn,ledger_name='signed-ea-margin');reopened=None
    try:
        reg,profile,queue,provider,adapter,command,poll,clock,native=rig
        clock['now']=NOW*1000
        adapter,queue,poll,clock,native,context,ledger=prepared(rig,tmp_path,ledger=ledger)
        facts=snapshot(eurusd,account_alias=adapter.account_alias,balance=D('10000'),equity=D('10000'),native_account_context=context)
        event=record(ledger,facts)
        values,errors=roundtrip(adapter,queue,poll,clock,native,context)
        assert not errors and len(values)==1
        book=NativeMarginBook(ledger,clock=lambda:clock['now'])
        receipt=book.record(event.hash,values[0]);count=ledger.count()
        reopened=PostgresLedger(pg_dsn,ledger_name='signed-ea-margin')
        read=NativeMarginBook(reopened,clock=lambda:(NOW+90*86400)*1000).lookup(receipt['source_ref'])
        assert read['receipt']==receipt and read['observation']['native_read_identity']['kind']=='EA_PULL_READ'
        assert read['observation']['reservation_amount'] is None and read['observation']['execution_authority'] is False
        assert ledger.count()==count and queue.native_entries(adapter.account_alias)==[]
        assert ledger.count(EventKind.ORDER_COMMAND)==0 and ledger.verify_chain()[0]
    finally:
        if reopened is not None:reopened.close()
        ledger.close()
