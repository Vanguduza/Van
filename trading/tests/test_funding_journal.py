"""Native source identities, first availability, conflicts and uncertain commits."""
from contextlib import contextmanager
from dataclasses import replace
from decimal import Decimal as D
import concurrent.futures,threading
import pytest
from vati.core.events import EventKind
from vati.core.ledger import Ledger
from vati.funding.journal import FundingBook
from test_native_cash_history import NativeCash
from test_retirement_venue_observations import ctrader


def statement():
    adapter=ctrader(NativeCash());adapter.clock=lambda:3000
    return adapter.cash_movements(from_ms=1000,to_ms=2000)

def test_collects_native_provider_facts_into_existing_journal_without_sending_money(tmp_path):
    ledger=Ledger(tmp_path/'facts.sqlite3');book=FundingBook(ledger,clock=lambda:5000);adapter=ctrader(NativeCash());adapter.clock=lambda:3000
    receipt=book.collect_statement(adapter,from_ms=1000,to_ms=2000)
    facts=book.observations(receipt['scope_hash'])
    assert receipt['state']=='OBSERVED' and receipt['row_count']==1 and receipt['execution_authority'] is False
    assert len(facts['movements'])==1 and facts['movements'][0]['movement']['delta']=='0.01234567'
    assert facts['return_qualification']=='NOT_ISSUED' and ledger.verify_chain()[0]

def test_repeat_and_alias_relabel_retain_first_identity_and_availability(tmp_path):
    ledger=Ledger(tmp_path/'facts.sqlite3');book=FundingBook(ledger,clock=lambda:5000);source=statement()
    original=book.record_statement(source)
    replay=book.record_statement(replace(source,account_alias='a-new-alias',observed_at_ms=4000))
    assert original==replay and ledger.count(EventKind.FUNDING_STATEMENT)==1
    assert replay['observed_at_ms']==3000 and replay['received_at_ms']==5000

def test_conflicting_native_history_is_retained_without_overwriting_original_or_old_view(tmp_path):
    ledger=Ledger(tmp_path/'facts.sqlite3');book=FundingBook(ledger,clock=lambda:5000);source=statement();original=book.record_statement(source)
    changed=replace(source,movements=(replace(source.movements[0],delta=D('1')),))
    receipt=book.record_statement(changed)
    assert receipt['state']=='CONFLICT' and ledger.count(EventKind.FUNDING_STATEMENT)==2
    assert book.observations(source.scope_hash)['state']=='CONFLICT'
    assert book.observations(source.scope_hash)['movements'][0]['movement']['delta']=='0.01234567'
    old=book.observations(source.scope_hash,as_of=original['statement_ref'])
    assert old['state']=='OBSERVED' and old['conflicts']==[]
    assert book.record_statement(source)==original
    assert book.observations(source.scope_hash)['state']=='CONFLICT'

def test_native_account_or_environment_never_merges_with_another_scope(tmp_path):
    ledger=Ledger(tmp_path/'facts.sqlite3');book=FundingBook(ledger,clock=lambda:5000);source=statement();book.record_statement(source)
    other=replace(source,environment='LIVE',movements=(replace(source.movements[0],delta=D('5')),))
    book.record_statement(other)
    assert source.scope_hash!=other.scope_hash
    assert book.observations(source.scope_hash)['movements'][0]['movement']['delta']=='0.01234567'
    assert book.observations(other.scope_hash)['movements'][0]['movement']['delta']=='5'

def test_concurrent_identical_native_reads_have_one_original_publication(tmp_path):
    database=tmp_path/'facts.sqlite3';Ledger(database);source=statement();barrier=threading.Barrier(2)
    def write():
        ledger=Ledger(database);book=FundingBook(ledger,clock=lambda:5000);barrier.wait(timeout=5)
        return book.record_statement(source)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:write(),range(2)))
    assert results[0]==results[1] and Ledger(database).count(EventKind.FUNDING_STATEMENT)==1

def test_lost_real_journal_commit_ack_recovers_original_native_statement(tmp_path):
    ledger=Ledger(tmp_path/'facts.sqlite3');book=FundingBook(ledger,clock=lambda:5000);source=statement();original_atomic=ledger.atomic;armed=True
    @contextmanager
    def uncertain():
        nonlocal armed
        outer=not ledger._conn.in_transaction
        with original_atomic():yield ledger
        if outer and armed:armed=False;raise OSError('journal commit acknowledgement lost')
    ledger.atomic=uncertain
    with pytest.raises(OSError,match='journal commit acknowledgement lost'):book.record_statement(source)
    first=list(ledger.iter(EventKind.FUNDING_STATEMENT))[0]
    recovered=FundingBook(Ledger(tmp_path/'facts.sqlite3'),clock=lambda:6000).record_statement(source)
    assert recovered['statement_ref']==first.hash and recovered['received_at_ms']==5000
    assert ledger.count(EventKind.FUNDING_STATEMENT)==1


@pytest.mark.parametrize('value',[None,D('NaN'),D('Infinity'),D('0.000000001')])
def test_non_native_or_unrepresentable_money_is_never_recorded_as_a_provider_fact(tmp_path,value):
    ledger=Ledger(tmp_path/'facts.sqlite3');book=FundingBook(ledger,clock=lambda:5000);source=statement()
    bad=replace(source,movements=(replace(source.movements[0],delta=value),))
    with pytest.raises(ValueError):book.record_statement(bad)
    assert ledger.count(EventKind.FUNDING_STATEMENT)==0


def test_ledger_readback_rejects_a_valid_hash_with_foreign_native_scope_in_the_body(tmp_path):
    from copy import deepcopy
    from vati.core.events import make_event
    from vati.core.ledger import LedgerError
    from vati.funding.journal import PRODUCER
    ledger=Ledger(tmp_path/'facts.sqlite3');book=FundingBook(ledger,clock=lambda:5000);source=statement();book.record_statement(source)
    event=list(ledger.iter(EventKind.FUNDING_STATEMENT))[0];payload=deepcopy(event.payload)
    payload['statement']['native_account_id']=67890
    ledger.append(make_event(EventKind.FUNDING_STATEMENT,PRODUCER,payload,event_time_ms=2000,received_time_ms=6000,correlation_id=event.correlation_id))
    with pytest.raises(LedgerError,match='funding_observation_journal_invalid'):book.observations(source.scope_hash)
