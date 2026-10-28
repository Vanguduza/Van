"""Actual original-query/SQLite ownership and durable symbol readback."""
from contextlib import contextmanager
import pytest

from test_mt5_symbol_contract import source,read
from vati.core import Ledger
from vati.market_data.mt5_symbol_book import NativeSymbolBook,NativeSymbolError,NativeSymbolUnknown


def test_real_public_capture_reopen_and_expired_replay_never_repeats_native_read(tmp_path):
    sdk,worker,adapter,now,ledger,context=source(tmp_path);reopened=None
    try:
        book=NativeSymbolBook(ledger,clock=lambda:now['ms'])
        result=book.capture(adapter,'EURUSD',context=context,deadline_ms=now['ms']+1000)
        assert result['source_query_ref']==context.source_query_ref
        assert result['execution_authority'] is result['risk_terms_qualified'] is False
        original=book.lookup(result['source_ref']);calls=len(adapter.client.sent)
        now['ms']+=5000;reopened=Ledger(ledger.path);again=NativeSymbolBook(reopened,clock=lambda:now['ms'])
        assert again.lookup(result['source_ref'])==original
        from vati.execution.mt5_symbol_contract import Mt5SymbolContractObservation
        assert again.record(Mt5SymbolContractObservation.from_body(original['observation']))==result
        assert len(adapter.client.sent)==calls and not sdk.sent and reopened.verify_chain()[0]
    finally:
        if reopened is not None:reopened.close()
        ledger.close()


def test_missing_original_account_query_refuses_before_native_read(tmp_path):
    sdk,worker,adapter,now,ledger,context=source(tmp_path);other=Ledger(tmp_path/'other.sqlite')
    try:
        before=len(adapter.client.sent)
        with pytest.raises(NativeSymbolError,match='ORIGINAL_QUERY_UNAVAILABLE'):
            NativeSymbolBook(other,clock=lambda:now['ms']).capture(adapter,'EURUSD',context=context,deadline_ms=now['ms']+1000)
        assert other.count()==0 and len(adapter.client.sent)==before and not sdk.sent
    finally:other.close();ledger.close()


def test_expiry_rechecked_inside_actual_sql_writer_without_publishing(tmp_path,monkeypatch):
    sdk,worker,adapter,now,ledger,context=source(tmp_path)
    try:
        observation=read(adapter,now,context);before=ledger.count();atomic=ledger.atomic
        @contextmanager
        def delayed():
            with atomic():
                now['ms']+=1000
                yield
        monkeypatch.setattr(ledger,'atomic',delayed)
        with pytest.raises(NativeSymbolError,match='EXPIRED'):
            NativeSymbolBook(ledger,clock=lambda:now['ms']).record(observation)
        assert ledger.count()==before and not sdk.sent
    finally:ledger.close()


def test_lost_sql_commit_ack_is_recovered_by_original_record_without_native_retry(tmp_path,monkeypatch):
    sdk,worker,adapter,now,ledger,context=source(tmp_path);reopened=None
    try:
        observation=read(adapter,now,context);calls=len(adapter.client.sent);atomic=ledger.atomic;armed={'yes':True}
        @contextmanager
        def lost_ack():
            outer=not ledger._conn.in_transaction
            with atomic():yield
            if outer and armed['yes']:
                armed['yes']=False
                raise OSError('injected ACK loss after actual SQL commit')
        monkeypatch.setattr(ledger,'atomic',lost_ack)
        with pytest.raises(NativeSymbolUnknown) as error:
            NativeSymbolBook(ledger,clock=lambda:now['ms']).record(observation)
        assert error.value.source_ref==observation.body()['source_ref']
        reopened=Ledger(ledger.path)
        original=NativeSymbolBook(reopened,clock=lambda:now['ms']).lookup(error.value.source_ref)
        assert original['receipt']['source_ref']==error.value.source_ref
        assert original['observation']==observation.body() and len(adapter.client.sent)==calls and not sdk.sent
    finally:
        if reopened is not None:reopened.close()
        ledger.close()


def test_uncommitted_source_cannot_issue_a_native_read_or_publish_a_record(tmp_path):
    from vati.core.ledger import LedgerError
    sdk,worker,adapter,now,ledger,context=source(tmp_path)
    try:
        book=NativeSymbolBook(ledger,clock=lambda:now['ms']);before=len(adapter.client.sent)
        with ledger.atomic():
            with pytest.raises(LedgerError,match='committed_source_read_requires_idle_or_readonly_snapshot'):
                book.capture(adapter,'EURUSD',context=context,deadline_ms=now['ms']+1000)
        assert len(adapter.client.sent)==before and not sdk.sent
    finally:ledger.close()


@pytest.mark.parametrize('budget',[{'max_records':1},{'max_bytes':1},{'max_ledger_events':1}])
def test_capacity_refusal_preserves_original_events_and_never_sends_an_order(tmp_path,budget):
    sdk,worker,adapter,now,ledger,context=source(tmp_path)
    try:
        first=read(adapter,now,context)
        if 'max_records' in budget:
            NativeSymbolBook(ledger,clock=lambda:now['ms'],**budget).record(first)
            value=read(adapter,now,context)
        else:value=first
        before=ledger.count()
        with pytest.raises(NativeSymbolError,match='CAPACITY'):
            NativeSymbolBook(ledger,clock=lambda:now['ms'],**budget).record(value)
        assert ledger.count()==before and ledger.verify_chain()[0] and not sdk.sent
    finally:ledger.close()
