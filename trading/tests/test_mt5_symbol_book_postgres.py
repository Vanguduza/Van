"""Original pre-decision symbol source on independent PostgreSQL owners."""
from contextlib import contextmanager
import pytest

from test_postgres_ledger_isolation import pg_dsn
from test_mt5_symbol_contract_worker import TermsSdk
from test_mt5_worker_funding import connection
from vati.core.ledger_pg import PostgresLedger
from vati.funding.mt5_runtime import capture_cached_mt5
from vati.risk.account_context import context_for_account
from vati.market_data.mt5_symbol_book import NativeSymbolBook,NativeSymbolError,NativeSymbolUnknown


def test_pg_actual_adapter_capture_reopen_namespace_and_expired_original_readback(pg_dsn,tmp_path):
    sdk,worker,adapter,now=connection(tmp_path,TermsSdk())
    ledger=PostgresLedger(pg_dsn,ledger_name='native-symbol');reopened=None
    other=PostgresLedger(pg_dsn,ledger_name='other-symbol')
    try:
        account=adapter.sync_account();captured=capture_cached_mt5(ledger,account,now_ms=now['ms'])
        context=context_for_account(ledger,adapter,account,now_ms=now['ms'],mt5_capture=captured)
        book=NativeSymbolBook(ledger,clock=lambda:now['ms'])
        result=book.capture(adapter,'EURUSD',context=context,deadline_ms=now['ms']+1000)
        calls=len(adapter.client.sent);now['ms']+=5000
        reopened=PostgresLedger(pg_dsn,ledger_name='native-symbol')
        original=NativeSymbolBook(reopened,clock=lambda:now['ms']).lookup(result['source_ref'])
        assert original['receipt']==result and original['observation']['state']=='OBSERVED_NATIVE_TERMS'
        assert original['receipt']['execution_authority'] is original['receipt']['risk_terms_qualified'] is False
        with pytest.raises(NativeSymbolError,match='ORIGINAL_QUERY_UNAVAILABLE'):
            NativeSymbolBook(other,clock=lambda:now['ms']).capture(adapter,'EURUSD',context=context,deadline_ms=now['ms']+1000)
        assert len(adapter.client.sent)==calls and other.count()==0 and ledger.verify_chain()[0] and not sdk.sent
    finally:
        if reopened is not None:reopened.close()
        other.close();ledger.close()


def test_pg_original_symbol_storage_lost_ack_reopens_without_native_retry(pg_dsn,tmp_path,monkeypatch):
    sdk,worker,adapter,now=connection(tmp_path,TermsSdk());ledger=PostgresLedger(pg_dsn,ledger_name='native-symbol-ack');reopened=None
    try:
        account=adapter.sync_account();captured=capture_cached_mt5(ledger,account,now_ms=now['ms'])
        context=context_for_account(ledger,adapter,account,now_ms=now['ms'],mt5_capture=captured)
        q=adapter.symbol_contract('EURUSD',context=context,deadline_ms=now['ms']+1000)
        calls=len(adapter.client.sent);atomic=ledger.atomic;armed={'yes':True}
        @contextmanager
        def lost_ack():
            # Start this source write at the actual outer commit boundary;
            # a nested ledger.append savepoint is not a committed write.
            outer=ledger._conn.info.transaction_status==0
            with atomic():yield
            if outer and armed['yes']:
                armed['yes']=False
                raise OSError('injected lost ACK after actual PostgreSQL commit')
        monkeypatch.setattr(ledger,'atomic',lost_ack)
        with pytest.raises(NativeSymbolUnknown):NativeSymbolBook(ledger,clock=lambda:now['ms']).record(q)
        reopened=PostgresLedger(pg_dsn,ledger_name='native-symbol-ack')
        original=NativeSymbolBook(reopened,clock=lambda:now['ms']).lookup(q.body()['source_ref'])
        assert original is not None and original['observation']==q.body()
        assert len(adapter.client.sent)==calls and not sdk.sent
    finally:
        if reopened is not None:reopened.close()
        ledger.close()
