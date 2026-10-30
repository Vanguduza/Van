"""Original signed native read through the existing shared SQL quote owner."""
from contextlib import contextmanager
from dataclasses import replace
from decimal import Decimal as D

import pytest

from conftest import NOW,snapshot
from test_mt5_expected_margin import source
from test_native_risk_history_inputs import record
from vati.core import Ledger,EventKind
from vati.risk.native_margin_book import NativeMarginBook,NativeMarginUnknown
from vati.execution.mt5_expected_margin import Mt5ExpectedMarginObservation


def original(tmp_path,eurusd,*,ledger=None):
    sdk,worker,adapter,now,ledger,context=source(tmp_path,ledger=ledger,at=NOW*1000)
    facts=snapshot(eurusd,account_alias=adapter.account_alias,balance=D('10000'),equity=D('10000'),native_account_context=context)
    event=record(ledger,facts);now['ms']+=1000
    return sdk,worker,adapter,now,ledger,event,NativeMarginBook(ledger,clock=lambda:now['ms'])


def capture(adapter,now,event,book):
    return book.capture(adapter,event.hash,'EURUSD',D('.10'),deadline_ms=NOW*1000+2000)


def test_mt5_original_request_to_shared_sql_readback_keeps_independent_native_query_and_money_scope(tmp_path,eurusd):
    sdk,worker,adapter,now,ledger,event,book=original(tmp_path,eurusd)
    receipt=capture(adapter,now,event,book);count=ledger.count();calls=len(sdk.margin_calls)
    reopened=Ledger(ledger.path)
    try:
        read=NativeMarginBook(reopened,clock=lambda:NOW*1000+90*86400*1000).lookup(receipt['source_ref'])
        assert read['receipt']==receipt
        assert read['observation']['native_account_context']['source_query_ref']==event.payload['inputs']['snapshot']['native_account_context']['source_query_ref']
        assert read['observation']['request']['price']==event.payload['inputs']['intent']['entry']
        assert read['observation']['request']['type']=='BUY'
        assert read['observation']['estimate_money']['asset_ref']==read['observation']['native_account_context']['monetary_scope_hash']
        assert book.record(event.hash,Mt5ExpectedMarginObservation.from_body(read['observation']))==receipt
        assert ledger.count()==count and len(sdk.margin_calls)==calls and not sdk.sent
        assert ledger.count(EventKind.ORDER_COMMAND)==0 and ledger.verify_chain()[0]
    finally:reopened.close()


def test_mt5_margin_actual_outer_commit_ack_loss_reconciles_original_without_native_requery(tmp_path,eurusd,monkeypatch):
    sdk,worker,adapter,now,ledger,event,book=original(tmp_path,eurusd)
    original_atomic=ledger.atomic
    @contextmanager
    def lost_ack():
        outer=not ledger._conn.in_transaction
        with original_atomic():yield ledger
        if outer:raise OSError('fixture committed native quote ACK lost')
    monkeypatch.setattr(ledger,'atomic',lost_ack)
    with pytest.raises(NativeMarginUnknown) as error:capture(adapter,now,event,book)
    calls=len(sdk.margin_calls);count=ledger.count();read=book.lookup(error.value.source_ref)
    assert read is not None
    monkeypatch.setattr(ledger,'atomic',original_atomic)
    assert book.record(event.hash,Mt5ExpectedMarginObservation.from_body(read['observation']))==read['receipt']
    assert ledger.count()==count and len(sdk.margin_calls)==calls and not sdk.sent
