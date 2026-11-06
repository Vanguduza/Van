"""Actual SQL writers and original native readback; projections never grant spend."""
from contextlib import closing, contextmanager
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
import os
import threading
import uuid

import pytest

from test_funding_journal import statement
from vati.core import Ledger, EventKind, make_event
from vati.core.canonical import canonical_hash, canonical_json
from vati.core.units import UnitError
from vati.funding.journal import FundingBook
from vati.funding.postings import FinancialMovement
from vati.funding.movement_journal import FinancialMovementBook, MovementPublicationUnknown, PRODUCER


def state(ledger):
    with ledger.read_snapshot():return ledger.head(),ledger.count()


@pytest.fixture(params=['sqlite','postgres'])
def book(tmp_path,request):
    if request.param=='postgres':
        if os.environ.get('VATI_TEST_PG_ISOLATED_FIXTURE')!='1' or not os.environ.get('VATI_TEST_PG_DSN'):
            pytest.skip('requires actual isolated PostgreSQL funding fixture')
        from vati.core.ledger_pg import PostgresLedger
        owned=PostgresLedger(os.environ['VATI_TEST_PG_DSN'],ledger_name='movement-'+uuid.uuid4().hex)
    else:owned=Ledger(tmp_path/'financial.sqlite')
    native=statement();receipt=FundingBook(owned,clock=lambda:5000).record_statement(native)
    with closing(owned):
        yield owned,FinancialMovementBook(owned,clock=lambda:6000),native,receipt['statement_ref']


def publish(book,request='original'):
    _,journal,native,source=book
    return journal.publish(request,scope_hash=native.scope_hash,native_id=native.movements[0].native_id,statement_ref=source)


def test_real_publication_independent_readback_and_original_replay_are_not_settlement(book):
    ledger,journal,native,ref=book;first=publish(book)
    assert first['risk_capital_qualified'] is first['execution_authority'] is False
    assert first['settlement_qualification']=='NOT_ISSUED' and first['available_at_ms']==6000
    current=journal.inspect('original');assert current['current_original_source_verified'] is True
    assert current['movement']['source_statement_ref']==ref
    head=state(ledger);journal.clock=lambda:pytest.fail('replay renewed original availability')
    assert publish(book)==first and FinancialMovementBook(ledger).lookup('original')==first
    assert state(ledger)==head and head[1]==2


def test_original_request_and_native_movement_identity_cannot_be_rebound(book):
    ledger,journal,native,ref=book;first=publish(book);before=state(ledger)
    with pytest.raises(UnitError,match='REQUEST_CONFLICT'):
        journal.publish('original',scope_hash=native.scope_hash,native_id=native.movements[0].native_id+1,statement_ref=ref)
    with pytest.raises(UnitError,match='ALREADY_POSTED'):
        publish(book,'another-request')
    assert state(ledger)==before and journal.lookup('original')==first


def test_unknown_and_caller_owned_transactions_cannot_claim_committed_projection(book):
    ledger,journal,native,ref=book
    with ledger.atomic():
        with pytest.raises(UnitError,match='OWN_WRITER'):publish(book)
        with pytest.raises(UnitError,match='OWN_WRITER'):journal.lookup('original')
    assert journal.lookup('missing') is None
    first=publish(book)
    with ledger.read_snapshot():assert journal.lookup('original')==first
    assert state(ledger)[1]==2


def test_actual_lost_commit_ack_reconciles_original_without_second_financial_effect(book,monkeypatch):
    ledger,journal,native,ref=book;atomic=ledger.atomic
    @contextmanager
    def lost():
        outer=not getattr(ledger,'_atomic_depth',0) and not getattr(ledger._conn,'in_transaction',False)
        with atomic() as writer:yield writer
        if outer:raise OSError('fixture actual committed financial projection ACK lost')
    with monkeypatch.context() as patch:
        patch.setattr(ledger,'atomic',lost)
        with pytest.raises(MovementPublicationUnknown):publish(book,'lost-ack')
    original=journal.lookup('lost-ack');assert original and state(ledger)[1]==2
    assert publish(book,'lost-ack')==original and state(ledger)[1]==2


def test_missing_original_readback_is_unknown_and_does_not_erase_actual_commit(book,monkeypatch):
    ledger,journal,native,ref=book
    with monkeypatch.context() as patch:
        patch.setattr(journal,'lookup',lambda _:None)
        with pytest.raises(MovementPublicationUnknown,match='READBACK_UNAVAILABLE'):publish(book)
    assert journal.lookup('original') and state(ledger)[1]==2
    assert publish(book)['record_ref']==journal.lookup('original')['record_ref']


@pytest.mark.parametrize('posted',[False,True])
def test_native_conflict_blocks_new_projection_but_preserves_historical_completion(book,posted):
    ledger,journal,native,ref=book;first=publish(book) if posted else None
    conflicting=replace(native,movements=(replace(native.movements[0],delta=native.movements[0].delta+1),))
    assert FundingBook(ledger,clock=lambda:5500).record_statement(conflicting)['state']=='CONFLICT'
    before=state(ledger)
    if posted:
        assert journal.lookup('original')==first and publish(book)==first
        current=journal.inspect('original')
        assert current['current_original_source_verified'] is False and current['source_state']=='UNAVAILABLE_OR_CONFLICTED'
    else:
        with pytest.raises(UnitError,match='SOURCE_UNAVAILABLE_OR_CONFLICTED'):publish(book)
    assert state(ledger)==before


def test_a_valid_seal_and_balanced_forgery_do_not_replace_original_native_amount(book):
    ledger,journal,native,ref=book
    with ledger.read_snapshot():source=next(e for e in ledger.iter(EventKind.FUNDING_STATEMENT) if e.hash==ref)
    movement=FinancialMovement(source,native.movements[0].native_id,recorded_at_ms=6000).body()
    units=int(movement['amount']['minor_units'])+1;movement['amount']['minor_units']=str(units)
    movement['postings'][0]['amount']['minor_units']=str(units)
    movement['postings'][1]['amount']['minor_units']=str(-units)
    requested={'scope_hash':native.scope_hash,'native_id':str(native.movements[0].native_id),'statement_ref':ref}
    payload={'format':'native-financial-movement-record/1','request_id':'forged',
        'request_sha256':canonical_hash(requested),'source':requested,'movement':movement}
    event=make_event(EventKind.FINANCIAL_MOVEMENT,PRODUCER,payload,event_time_ms=movement['occurred_at_ms'],
        received_time_ms=6000,correlation_id=movement['movement_id']);ledger.append(event)
    before=state(ledger)
    with pytest.raises(UnitError,match='ORIGINAL_POSTINGS'):journal.lookup('forged')
    assert state(ledger)==before and ledger.verify_chain()[0]


@pytest.mark.parametrize('field',['risk_capital_qualified','execution_authority','trade_alpha_claimed','scale','recorded_at_ms'])
def test_resealed_numeric_values_cannot_impersonate_exact_json_boolean_or_integer_types(book,field):
    ledger,journal,native,ref=book
    with ledger.read_snapshot():source=next(ledger.iter(EventKind.FUNDING_STATEMENT))
    requested={'scope_hash':native.scope_hash,'native_id':str(native.movements[0].native_id),'statement_ref':ref}
    payload={'format':'native-financial-movement-record/1','request_id':'original',
        'request_sha256':canonical_hash(requested),'source':requested,
        'movement':FinancialMovement(source,native.movements[0].native_id,recorded_at_ms=6000).body()}
    if field=='scale':payload['movement']['amount']['scale']=float(payload['movement']['amount']['scale'])
    elif field=='recorded_at_ms':payload['movement'][field]=float(payload['movement'][field])
    else:payload['movement'][field]=0
    forged=make_event(EventKind.FINANCIAL_MOVEMENT,PRODUCER,payload,
        event_time_ms=payload['movement']['occurred_at_ms'],received_time_ms=6000,
        correlation_id=payload['movement']['movement_id'])
    ledger.append(forged)
    assert ledger.verify_chain()[0]
    before=state(ledger)
    with pytest.raises(UnitError,match='ORIGINAL_POSTINGS'):journal.lookup('original')
    assert state(ledger)==before


@pytest.mark.parametrize('capacity',['source-count','bytes','movements'])
def test_global_projection_capacity_refuses_before_append_and_preserves_source(book,capacity):
    ledger,journal,native,ref=book
    if capacity=='bytes':
        with ledger.read_snapshot():source=next(ledger.iter(EventKind.FUNDING_STATEMENT))
        journal.max_bytes=len(canonical_json(source.body()).encode())+1
    else:
        if capacity=='movements':publish(book);journal.max_movements=1
        else:journal.max_source_statements=1
        extra=replace(native,movements=(replace(native.movements[0],native_id=native.movements[0].native_id+1),))
        receipt=FundingBook(ledger,clock=lambda:5500).record_statement(extra)
        native=extra;ref=receipt['statement_ref']
    before=state(ledger)
    with pytest.raises(UnitError,match='CAPACITY'):
        journal.publish('over-capacity',scope_hash=native.scope_hash,native_id=native.movements[0].native_id,statement_ref=ref)
    assert state(ledger)==before


def test_independent_sql_connections_publish_the_same_original_once(book):
    ledger,journal,native,ref=book;barrier=threading.Barrier(2)
    def writer():
        if isinstance(ledger,Ledger):owned=Ledger(ledger.path)
        else:
            from vati.core.ledger_pg import PostgresLedger
            owned=PostgresLedger(ledger.path,ledger_name=ledger.name)
        with closing(owned):
            other=FinancialMovementBook(owned,clock=lambda:6000);history=other._history;first=True
            def synchronized():
                nonlocal first
                result=history()
                if first:first=False;barrier.wait(timeout=10)
                return result
            other._history=synchronized
            return other.publish('concurrent',scope_hash=native.scope_hash,native_id=native.movements[0].native_id,statement_ref=ref)
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs=[pool.submit(writer) for _ in range(2)];results=[job.result(timeout=30) for job in jobs]
    assert results[0]==results[1] and state(ledger)[1]==2 and ledger.verify_chain()[0]


def test_bounded_materialization_recovers_older_committed_source_windows(book):
    ledger,journal,native,ref=book
    next_native=replace(native,movements=(replace(native.movements[0],native_id=8),))
    next_ref=FundingBook(ledger,clock=lambda:5500).record_statement(next_native)['statement_ref']
    before=state(ledger)
    pending=journal.projection(native.scope_hash)
    assert pending['state']=='PENDING' and pending['pending_count']==2 and pending['posted_count']==0
    assert state(ledger)==before
    first=journal.materialize(native.scope_hash,max_batch=1)
    assert first['state']=='PENDING' and first['posted_count']==first['pending_count']==1
    old=first['movements'][0]['publication'];assert first['movements'][0]['movement']['source_statement_ref']==ref
    finished=FinancialMovementBook(ledger,clock=lambda:6500).materialize(native.scope_hash)
    assert finished['pending_count']==0 and finished['posted_count']==2
    assert finished['current_original_source_verified'] is True
    assert finished['movements'][0]['publication']==old
    assert finished['movements'][1]['movement']['source_statement_ref']==next_ref
    before=state(ledger)
    assert journal.materialize(native.scope_hash)==finished and state(ledger)==before
    limited=journal.projection(native.scope_hash,limit=1)
    assert limited['movements_truncated'] is True and len(limited['movements'])==1 and limited['posted_count']==2


def test_materialization_reconciles_original_unknown_then_resumes_remaining_rows(book,monkeypatch):
    ledger,journal,native,ref=book
    FundingBook(ledger,clock=lambda:5500).record_statement(replace(native,
        movements=(replace(native.movements[0],native_id=8),)))
    with monkeypatch.context() as patch:
        patch.setattr(journal,'lookup',lambda _:None)
        with pytest.raises(MovementPublicationUnknown) as failure:journal.materialize(native.scope_hash)
    request=failure.value.request_id
    original=journal.lookup(request);assert original and journal.projection(native.scope_hash)['pending_count']==1
    result=FinancialMovementBook(ledger,clock=lambda:6500).materialize(native.scope_hash)
    assert result['posted_count']==2 and result['pending_count']==0
    assert journal.lookup(request)==original and ledger.count(EventKind.FINANCIAL_MOVEMENT)==2


def test_conflict_projection_preserves_historical_rows_and_never_materializes_new_cash(book):
    ledger,journal,native,ref=book;publish(book)
    FundingBook(ledger,clock=lambda:6500).record_statement(replace(native,
        movements=(replace(native.movements[0],delta=native.movements[0].delta+1),)))
    before=state(ledger);result=journal.materialize(native.scope_hash)
    assert result['state']=='CONFLICT' and result['posted_count']==1
    assert result['current_original_source_verified'] is result['risk_capital_qualified'] is result['execution_authority'] is False
    assert state(ledger)==before
    foreign=journal.projection('f'*64)
    assert foreign['state']=='NO_DATA' and foreign['posted_count']==0 and foreign['movements']==[]


@pytest.mark.parametrize('bad',[True,0,1001])
def test_materialization_limits_are_strict_and_readonly_requests_cannot_write(book,bad):
    ledger,journal,native,ref=book;before=state(ledger)
    with pytest.raises(UnitError,match='CAPACITY'):journal.materialize(native.scope_hash,max_batch=bad)
    with pytest.raises(UnitError,match='CAPACITY'):journal.projection(native.scope_hash,limit=bad)
    with ledger.read_snapshot():
        with pytest.raises(UnitError,match='OWN_WRITER'):journal.materialize(native.scope_hash)
    assert state(ledger)==before
