"""Original quote source on independent PostgreSQL owners."""
from contextlib import contextmanager
import pytest

from test_postgres_ledger_isolation import pg_dsn
from test_mt5_quote_worker import QuoteSdk
from test_mt5_worker_funding import connection
from vati.core.ledger_pg import PostgresLedger
from vati.funding.mt5_runtime import capture_cached_mt5
from vati.risk.account_context import context_for_account
from vati.execution.mt5_quotes import Mt5QuoteObservation
from vati.market_data.mt5_quote_book import NativeQuoteBook
from vati.market_data.mt5_symbol_book import NativeSymbolBook,NativeSymbolError,NativeSymbolUnknown


def test_pg_original_quote_source_reopen_retains_tick_time_and_account_namespace(pg_dsn,tmp_path):
    sdk,worker,adapter,now=connection(tmp_path,QuoteSdk())
    ledger=PostgresLedger(pg_dsn,ledger_name='native-quote');reopened=None
    other=PostgresLedger(pg_dsn,ledger_name='other-quote')
    try:
        account=adapter.sync_account();captured=capture_cached_mt5(ledger,account,now_ms=now['ms'])
        context=context_for_account(ledger,adapter,account,now_ms=now['ms'],mt5_capture=captured)
        book=NativeQuoteBook(ledger,clock=lambda:now['ms'])
        receipt=book.capture(adapter,'EURUSD',context=context,deadline_ms=now['ms']+1000)
        calls=len(adapter.client.sent);now['ms']+=10000
        reopened=PostgresLedger(pg_dsn,ledger_name='native-quote')
        original=NativeQuoteBook(reopened,clock=lambda:now['ms']).lookup(receipt['source_ref'])
        assert original['receipt']==receipt
        assert Mt5QuoteObservation.from_body(original['observation']).snapshot(now_ms=now['ms'],max_age_ms=5000)['state']=='STALE_NATIVE_QUOTE'
        assert NativeSymbolBook(reopened,clock=lambda:now['ms']).lookup(receipt['source_ref']) is None
        with pytest.raises(NativeSymbolError,match='ORIGINAL_QUERY_UNAVAILABLE'):
            NativeQuoteBook(other,clock=lambda:now['ms']).capture(adapter,'EURUSD',context=context,deadline_ms=now['ms']+1000)
        assert other.count()==0 and len(adapter.client.sent)==calls and ledger.verify_chain()[0] and not sdk.sent
    finally:
        if reopened is not None:reopened.close()
        other.close();ledger.close()


def test_pg_lost_outer_quote_commit_ack_recovers_original_without_native_retry(pg_dsn,tmp_path,monkeypatch):
    sdk,worker,adapter,now=connection(tmp_path,QuoteSdk())
    ledger=PostgresLedger(pg_dsn,ledger_name='native-quote-ack');reopened=None
    try:
        account=adapter.sync_account();captured=capture_cached_mt5(ledger,account,now_ms=now['ms'])
        context=context_for_account(ledger,adapter,account,now_ms=now['ms'],mt5_capture=captured)
        q=adapter.quote_snapshot('EURUSD',context=context,deadline_ms=now['ms']+1000)
        calls=len(adapter.client.sent);atomic=ledger.atomic;armed={'yes':True}
        @contextmanager
        def lost_ack():
            outer=ledger._atomic_depth==0
            with atomic():yield
            if outer and armed['yes']:
                armed['yes']=False
                raise OSError('injected lost ACK after actual outer PostgreSQL quote commit')
        monkeypatch.setattr(ledger,'atomic',lost_ack)
        with pytest.raises(NativeSymbolUnknown):NativeQuoteBook(ledger,clock=lambda:now['ms']).record(q)
        reopened=PostgresLedger(pg_dsn,ledger_name='native-quote-ack')
        stored=NativeQuoteBook(reopened,clock=lambda:now['ms']).lookup(q.body()['source_ref'])
        assert stored is not None and stored['observation']==q.body() and len(adapter.client.sent)==calls and not sdk.sent
    finally:
        if reopened is not None:reopened.close()
        ledger.close()
