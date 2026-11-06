"""Original quote capture and replay reuse the existing SQL/query owner."""
from contextlib import contextmanager
import pytest

from test_mt5_quotes import source,read
from vati.core import Ledger
from vati.execution.mt5_quotes import Mt5QuoteObservation
from vati.market_data.mt5_quote_book import NativeQuoteBook
from vati.market_data.mt5_symbol_book import NativeSymbolBook,NativeSymbolUnknown


def test_actual_quote_capture_reopen_preserves_original_tick_time_and_does_not_freshen_history(tmp_path):
    sdk,worker,adapter,now,ledger,context=source(tmp_path);reopened=None
    try:
        book=NativeQuoteBook(ledger,clock=lambda:now['ms'])
        receipt=book.capture(adapter,'EURUSD',context=context,deadline_ms=now['ms']+1000)
        original=book.lookup(receipt['source_ref']);calls=len(adapter.client.sent)
        assert receipt['schema']=='vati.original-mt5-quote-receipt/1'
        assert receipt['state']=='ORIGINAL_NATIVE_QUOTE_STORED' and receipt['execution_authority'] is False
        # The common ledger owner retains separate, original data kinds.
        assert NativeSymbolBook(ledger,clock=lambda:now['ms']).lookup(receipt['source_ref']) is None
        now['ms']+=10000;reopened=Ledger(ledger.path)
        again=NativeQuoteBook(reopened,clock=lambda:now['ms'])
        assert again.lookup(receipt['source_ref'])==original
        q=Mt5QuoteObservation.from_body(original['observation'])
        assert q.snapshot(now_ms=now['ms'],max_age_ms=5000)['state']=='STALE_NATIVE_QUOTE'
        assert again.record(q)==receipt and len(adapter.client.sent)==calls and not sdk.sent
    finally:
        if reopened is not None:reopened.close()
        ledger.close()


def test_lost_outer_sql_ack_recovers_the_original_quote_without_another_native_read(tmp_path,monkeypatch):
    sdk,worker,adapter,now,ledger,context=source(tmp_path);reopened=None
    try:
        q=read(adapter,now,context);calls=len(adapter.client.sent);atomic=ledger.atomic;armed={'yes':True}
        @contextmanager
        def lost_ack():
            outer=not ledger._conn.in_transaction
            with atomic():yield
            if outer and armed['yes']:
                armed['yes']=False
                raise OSError('injected ACK loss after actual outer quote commit')
        monkeypatch.setattr(ledger,'atomic',lost_ack)
        with pytest.raises(NativeSymbolUnknown) as error:
            NativeQuoteBook(ledger,clock=lambda:now['ms']).record(q)
        reopened=Ledger(ledger.path)
        original=NativeQuoteBook(reopened,clock=lambda:now['ms']).lookup(error.value.source_ref)
        assert original['observation']==q.body() and len(adapter.client.sent)==calls and not sdk.sent
    finally:
        if reopened is not None:reopened.close()
        ledger.close()
