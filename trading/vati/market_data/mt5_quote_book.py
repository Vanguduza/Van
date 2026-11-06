"""Original native quote snapshots through the existing query-bound SQL owner.

Historical data retain their original tick time. A durable receipt cannot make
an old quote current, grant risk, or represent last-trade volume as depth.
"""
from vati.market_data.mt5_symbol_book import NativeSymbolBook
from vati.execution.mt5_quotes import Mt5QuoteObservation


class NativeQuoteBook(NativeSymbolBook):
    observation_type=Mt5QuoteObservation
    event_name='ORIGINAL_MT5_QUOTE_SNAPSHOT'
    producer='vati-mt5-quote-book'
    record_schema='vati.original-mt5-quote-record/1'
    receipt_schema='vati.original-mt5-quote-receipt/1'
    stored_state='ORIGINAL_NATIVE_QUOTE_STORED'

    def _read(self,adapter,symbol,*,context,deadline_ms):
        return adapter.quote_snapshot(symbol,context=context,deadline_ms=deadline_ms)
