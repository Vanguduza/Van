"""Original native deal facts, immutable history and existing financial fences."""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal as D
import pytest
from test_native_deal_history import NativeDeals
from test_funding_journal import statement as cash_statement
from test_retirement_venue_observations import ctrader
from vati.core.events import EventKind,make_event
from vati.core.ledger import Ledger,LedgerError
from vati.funding.deal_journal import DealBook
from vati.funding.journal import FundingBook

def statement():
    adapter=ctrader(NativeDeals());adapter.clock=lambda:3000
    return adapter.deal_history(from_ms=1000,to_ms=2000)

def test_cash_and_native_deal_originals_share_a_journal_without_merging_source_kinds(tmp_path):
    ledger=Ledger(tmp_path/'facts.sqlite');cash=FundingBook(ledger,clock=lambda:5000);deals=DealBook(ledger,clock=lambda:5000)
    source=statement();cash.record_statement(cash_statement());receipt=deals.record_statement(source)
    result=deals.observations(source.scope_hash)
    assert result['state']=='OBSERVED' and len(result['deals'])==1 and result['deals'][0]['deal']['close']['balance_after']=='1005.30123456'
    assert result['deals'][0]['original_statement_ref']==receipt['statement_ref']
    assert len(cash.observations(source.scope_hash)['movements'])==1
    assert ledger.count(EventKind.FUNDING_STATEMENT)==ledger.count(EventKind.FUNDING_DEAL_STATEMENT)==1 and ledger.verify_chain()[0]

def test_repeat_relabel_and_changed_paging_cost_keep_the_original_native_receipt(tmp_path):
    ledger=Ledger(tmp_path/'facts.sqlite');book=DealBook(ledger,clock=lambda:5000);source=statement()
    first=book.record_statement(source)
    repeat=book.record_statement(replace(source,account_alias='a-new-label',observed_at_ms=4000,request_count=8))
    assert repeat==first and first['received_at_ms']==5000 and first['observed_at_ms']==3000
    assert ledger.count(EventKind.FUNDING_DEAL_STATEMENT)==1

def test_changed_native_deal_fee_retains_original_and_preserves_previous_asof_view(tmp_path):
    ledger=Ledger(tmp_path/'facts.sqlite');book=DealBook(ledger,clock=lambda:5000);source=statement();first=book.record_statement(source)
    corrected=replace(source,deals=(replace(source.deals[0],close=replace(source.deals[0].close,commission=D('-.00000014'))),))
    correction=book.record_statement(corrected)
    assert correction['state']=='CONFLICT' and book.observations(source.scope_hash)['state']=='CONFLICT'
    old=book.observations(source.scope_hash,as_of=first['statement_ref'])
    assert old['state']=='OBSERVED' and old['deals'][0]['deal']['close']['commission']=='-1.3E-7'
    assert book.record_statement(source)==first and book.observations(source.scope_hash)['state']=='CONFLICT'

def test_lost_original_native_deal_commit_ack_is_reconciled_without_second_publication(tmp_path):
    ledger=Ledger(tmp_path/'facts.sqlite');source=statement();original=ledger.atomic;armed=True
    @contextmanager
    def uncertain():
        nonlocal armed
        outer=not ledger._conn.in_transaction
        with original():yield ledger
        if outer and armed:armed=False;raise OSError('fixture-original-deal-commit-ack-lost')
    ledger.atomic=uncertain
    with pytest.raises(OSError):DealBook(ledger,clock=lambda:5000).record_statement(source)
    first=list(ledger.iter(EventKind.FUNDING_DEAL_STATEMENT))[0]
    recovered=DealBook(ledger,clock=lambda:6000).record_statement(source)
    assert recovered['statement_ref']==first.hash and recovered['received_at_ms']==5000 and ledger.count()==1

@pytest.mark.parametrize('value',[D('NaN'),D('Infinity'),D('.000000001')])
def test_invalid_native_close_money_cannot_enter_the_journal(tmp_path,value):
    ledger=Ledger(tmp_path/'facts.sqlite');source=statement()
    invalid=replace(source,deals=(replace(source.deals[0],close=replace(source.deals[0].close,commission=value)),))
    with pytest.raises(ValueError):DealBook(ledger,clock=lambda:5000).record_statement(invalid)
    assert ledger.count()==0

def test_valid_hash_does_not_admit_a_foreign_native_deal_scope(tmp_path):
    ledger=Ledger(tmp_path/'facts.sqlite');book=DealBook(ledger,clock=lambda:5000);source=statement();book.record_statement(source)
    event=list(ledger.iter(EventKind.FUNDING_DEAL_STATEMENT))[0];body=deepcopy(event.payload)
    body['statement']['native_account_id']=99999
    ledger.append(make_event(event.kind,event.producer,body,event_time_ms=2000,received_time_ms=6000,correlation_id=event.correlation_id))
    with pytest.raises(LedgerError):book.observations(source.scope_hash)
