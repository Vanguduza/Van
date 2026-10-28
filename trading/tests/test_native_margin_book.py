"""Real SQL publication/readback of original native read-only estimates."""
from contextlib import contextmanager
from dataclasses import replace
from decimal import Decimal as D

import pytest

from conftest import NOW, snapshot, intent
from test_ctrader_expected_margin import source
from test_native_risk_history_inputs import record
from vati.core import EventKind, Ledger
from vati.core.ledger import LedgerError
from vati.execution.ctrader.margin_quote import ExpectedMarginObservation
from vati.risk.native_margin_book import NativeMarginBook, NativeMarginError, NativeMarginUnknown


def setup_book(tmp_path,eurusd,*,ledger=None):
    adapter,context=source(tmp_path)
    ledger=ledger or Ledger(tmp_path/'quotes.sqlite')
    facts=snapshot(replace(eurusd,venue='ctrader',account_currency='EUR'),
        account_alias=adapter.account_alias,equity=D('10000'),balance=D('10000'),native_account_context=context)
    event=record(ledger,facts)
    now={'ms':NOW*1000+1000}
    adapter.clock=lambda:now['ms']
    book=NativeMarginBook(ledger,clock=lambda:now['ms'])
    return ledger,adapter,event,book,now,facts


def capture(adapter,event,book):
    return book.capture(adapter,event.hash,'EURUSD',D('.123'),deadline_ms=NOW*1000+2000)


def test_actual_adapter_to_sql_to_independent_reopen_retains_original_quote_and_input(tmp_path,eurusd):
    ledger,adapter,event,book,now,_=setup_book(tmp_path,eurusd)
    receipt=capture(adapter,event,book)
    assert receipt['state']=='ORIGINAL_NATIVE_ESTIMATE_STORED'
    assert receipt['execution_authority'] is receipt['reservation_qualified'] is False
    assert receipt['original_input_ref']==event.hash
    count=ledger.count();calls=len(adapter.transport.calls)
    now['ms']+=90*86400*1000
    reopened=Ledger(ledger.path)
    try:
        observed=NativeMarginBook(reopened,clock=lambda:now['ms']).lookup(receipt['source_ref'])
        assert observed['receipt']==receipt
        assert observed['observation']['native_contract']['metadata']['detail']['lotSize']==10000000
        assert observed['observation']['request']['volume']==[1230000]
        assert observed['observation']['native_account_context']==event.payload['inputs']['snapshot']['native_account_context']
        assert book.record(event.hash,ExpectedMarginObservation.from_body(observed['observation']))==receipt
        observed['observation']['request']['volume'][0]=0
        assert book.lookup(receipt['source_ref'])['observation']['request']['volume']==[1230000]
        assert ledger.count()==count and len(adapter.transport.calls)==calls
        assert ledger.count(EventKind.ORDER_COMMAND)==0 and ledger.verify_chain()[0]
    finally:reopened.close()


def test_storage_commit_ack_loss_reconciles_original_without_recapture_or_duplicate(tmp_path,eurusd,monkeypatch):
    ledger,adapter,event,book,now,_=setup_book(tmp_path,eurusd)
    original=ledger.atomic
    @contextmanager
    def lost_ack():
        outer=not ledger._conn.in_transaction
        with original():yield ledger
        if outer:raise OSError('fixture actual commit ACK loss')
    monkeypatch.setattr(ledger,'atomic',lost_ack)
    with pytest.raises(NativeMarginUnknown) as error:capture(adapter,event,book)
    calls=len(adapter.transport.calls);count=ledger.count()
    observed=book.lookup(error.value.source_ref)
    assert observed is not None
    monkeypatch.setattr(ledger,'atomic',original)
    from vati.execution.ctrader.margin_quote import ExpectedMarginObservation
    assert book.record(event.hash,ExpectedMarginObservation.from_body(observed['observation']))==observed['receipt']
    assert ledger.count()==count and len(adapter.transport.calls)==calls


def test_quote_expiry_is_rechecked_after_actual_writer_acquisition(tmp_path,eurusd,monkeypatch):
    ledger,adapter,event,book,now,_=setup_book(tmp_path,eurusd);before=ledger.count()
    original=ledger.atomic
    @contextmanager
    def queued():
        with original():
            now['ms']=NOW*1000+2000
            yield ledger
    monkeypatch.setattr(ledger,'atomic',queued)
    with pytest.raises(NativeMarginError,match='EXPIRED'):capture(adapter,event,book)
    assert ledger.count()==before and ledger.verify_chain()[0]


def test_own_staged_input_is_never_durable_margin_evidence(tmp_path,eurusd):
    ledger,adapter,event,book,now,facts=setup_book(tmp_path,eurusd);before=ledger.count()
    with pytest.raises(LedgerError,match='committed_source_read_requires'):
        with ledger.atomic():
            staged=record(ledger,replace(facts,peak_equity=D('11000')))
            capture(adapter,staged,book)
    assert ledger.count()==before and not adapter.transport.calls


def test_same_quote_cannot_be_rebound_to_another_original_input(tmp_path,eurusd):
    ledger,adapter,event,book,now,facts=setup_book(tmp_path,eurusd)
    receipt=capture(adapter,event,book);count=ledger.count()
    other=record(ledger,replace(facts,peak_equity=D('11000')),
        request=intent(trade_intent_id='another-input',account_alias=adapter.account_alias,venue='ctrader'))
    from vati.execution.ctrader.margin_quote import ExpectedMarginObservation
    observation=ExpectedMarginObservation.from_body(book.lookup(receipt['source_ref'])['observation'])
    with pytest.raises(NativeMarginError,match='CONFLICT'):book.record(other.hash,observation)
    assert ledger.count()==count+1


def test_failed_independent_readback_reports_unknown_until_original_can_be_read(tmp_path,eurusd,monkeypatch):
    ledger,adapter,event,book,now,_=setup_book(tmp_path,eurusd);original=book.lookup;calls=[]
    def unavailable(ref):
        calls.append(ref)
        if len(calls)==2:raise OSError('fixture independent read unavailable')
        return original(ref)
    monkeypatch.setattr(book,'lookup',unavailable)
    with pytest.raises(NativeMarginUnknown) as error:capture(adapter,event,book)
    monkeypatch.setattr(book,'lookup',original)
    assert book.lookup(error.value.source_ref)['receipt']['source_ref']==error.value.source_ref


@pytest.mark.parametrize('limit,value',[('max_records',1),('max_bytes',100),('max_ledger_events',1)])
def test_storage_capacity_refuses_without_partial_publication(tmp_path,eurusd,limit,value):
    ledger,adapter,event,book,now,_=setup_book(tmp_path,eurusd)
    book=NativeMarginBook(ledger,clock=lambda:now['ms'],**{limit:value})
    if limit=='max_records':
        capture(adapter,event,book)
        now['ms']+=1
    before=ledger.count()
    with pytest.raises(NativeMarginError,match='CAPACITY'):capture(adapter,event,book)
    assert ledger.count()==before and ledger.verify_chain()[0]
