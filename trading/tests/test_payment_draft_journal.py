"""Real SQL draft storage; existing retention policy; no payment capability."""
from contextlib import closing,contextmanager
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import os,threading,uuid

import pytest

from test_payment_contracts import intent,usd
from van_gateway.trading.payment_draft_policy import guard_payment_draft
from vati.core import Ledger,EventKind,make_event
from vati.core.canonical import canonical_hash
from vati.core.ledger import LedgerError
from vati.funding.payment_contracts import PaymentContractError
from vati.funding.payment_drafts import PaymentDraftBook,PaymentDraftError,PaymentDraftUnknown,PRODUCER,SCHEMA


@pytest.fixture(params=['sqlite','postgres'])
def drafts(tmp_path,request):
    if request.param=='postgres':
        if os.environ.get('VATI_TEST_PG_ISOLATED_FIXTURE')!='1':pytest.skip('requires actual isolated PostgreSQL draft fixture')
        from vati.core.ledger_pg import PostgresLedger
        name='payment-draft-'+uuid.uuid4().hex
        fresh=lambda:PostgresLedger(os.environ['VATI_TEST_PG_DSN'],ledger_name=name)
    else:
        path=tmp_path/'drafts.sqlite';fresh=lambda:Ledger(path)
    clock={'now':1500};ledger=fresh()
    with closing(ledger):
        yield ledger,PaymentDraftBook(ledger,privacy_guard=guard_payment_draft,clock=lambda:clock['now']),fresh,clock


def state(ledger):
    with ledger.read_snapshot():return ledger.head(),ledger.count()


def test_real_original_storage_independent_readback_and_expired_replay_are_not_approval(drafts):
    ledger,book,fresh,clock=drafts;original=intent();receipt=book.publish('owner:one',original)
    assert receipt['state']=='DRAFT_STORED_NOT_APPROVED' and receipt['execution_authority'] is receipt['provider_qualified'] is False
    before=state(ledger)
    with closing(fresh()) as cold:
        reader=PaymentDraftBook(cold,privacy_guard=guard_payment_draft,clock=lambda:2100)
        assert reader.lookup('owner:one',original.request_id)==receipt
        detail=reader.inspect('owner:one',original.request_id)
        assert detail['intent']==original.body() and detail['claimed_quote_time_state']=='EXPIRED'
        assert detail['current_payment_eligibility']=='NOT_ADMITTED'
        assert reader.publish('owner:one',original)==receipt
    book.clock=lambda:pytest.fail('replay renewed original draft time')
    assert book.publish('owner:one',original)==receipt and state(ledger)==before
    assert before[1]==1
    assert all(ledger.count(kind)==0 for kind in [EventKind.ORDER_COMMAND,EventKind.RISK_DECISION,
        EventKind.EXECUTION_RECEIPT,EventKind.FINANCIAL_MOVEMENT,EventKind.FUNDING_STATEMENT])


def test_original_owner_request_cannot_be_rebound_and_foreign_reads_do_not_disclose_it(drafts):
    ledger,book,_,_=drafts;original=intent();receipt=book.publish('owner:one',original);before=state(ledger)
    with pytest.raises(PaymentDraftError,match='ORIGINAL_REQUEST_CONFLICT'):
        book.publish('owner:one',replace(original,operation='TRANSFER'))
    with pytest.raises(PaymentDraftError,match='OWNER_OR_INPUT'):
        book.publish('owner:two',original)
    assert book.lookup('owner:two',original.request_id) is None and state(ledger)==before
    assert book.lookup('owner:one',original.request_id)==receipt


def test_same_request_text_in_another_owner_scope_has_a_distinct_original(drafts):
    ledger,book,_,_=drafts;one=intent();two=replace(one,quote=replace(one.quote,beneficiary=replace(one.quote.beneficiary,owner_ref='owner:two')))
    a=book.publish('owner:one',one);b=book.publish('owner:two',two)
    assert a['record_ref']!=b['record_ref'] and a['intent_hash']!=b['intent_hash'] and state(ledger)[1]==2
    assert book.lookup('owner:one',one.request_id)==a and book.lookup('owner:two',two.request_id)==b


def test_caller_owned_writers_cannot_be_published_or_reported_as_committed_drafts(drafts):
    ledger,book,_,_=drafts
    with ledger.atomic():
        with pytest.raises(LedgerError,match='committed_source'):book.publish('owner:one',intent())
        with pytest.raises(LedgerError,match='committed_source'):book.lookup('owner:one','request:original')
    assert state(ledger)[1]==0
    receipt=book.publish('owner:one',intent())
    with ledger.read_snapshot():
        assert book.lookup('owner:one','request:original')==receipt
        with pytest.raises(PaymentDraftError,match='OWN_WRITER'):book.publish('owner:one',intent())


@pytest.mark.parametrize('text',['4111 1111 1111 1111','cvv:123','GB82WEST12345698765432','payment_token=fixture-secret-value',
    'password=public-source-fixture','Bearer public-source-fixture',
    '-----BEGIN PRIVATE KEY----- public-source-fixture -----END PRIVATE KEY-----',
    'wallet_private_key=public-source-fixture','seed_phrase=public-source-fixture','secretref://fixture/key#VALUE'])
def test_existing_instrument_retention_owner_refuses_text_before_any_durable_append(drafts,text):
    ledger,book,_,_=drafts;original=intent();unsafe=replace(original,quote=replace(original.quote,reference=text));before=state(ledger)
    with pytest.raises(PaymentDraftError,match='RETENTION_BOUNDARY_REFUSED'):book.publish('owner:one',unsafe)
    assert state(ledger)==before and book.lookup('owner:one',unsafe.request_id) is None


def test_typed_exact_numbers_and_clocks_are_not_payment_instrument_text(drafts):
    ledger,book,_,clock=drafts;original=intent();units=4111111111111111
    # The untrusted free-text field above refuses the public card fixture. Here
    # the value has the exact amount type, not a stored payment-method field.
    q=replace(original.quote,amount=usd(units),quoted_debit=usd(units+100),issued_at_ms=1700000000000,expires_at_ms=1800000000000)
    clock['now']=1750000000000;receipt=book.publish('owner:one',replace(original,quote=q))
    assert receipt['state']=='DRAFT_STORED_NOT_APPROVED' and state(ledger)[1]==1


def test_actual_lost_commit_ack_keeps_the_original_durable_request(drafts,monkeypatch):
    ledger,book,fresh,_=drafts;atomic=ledger.atomic
    @contextmanager
    def lost():
        outer=not getattr(ledger,'_atomic_depth',0) and not getattr(ledger._conn,'in_transaction',False)
        with atomic() as value:yield value
        if outer:raise OSError('fixture lost committed draft ACK')
    with monkeypatch.context() as patch:
        patch.setattr(ledger,'atomic',lost)
        with pytest.raises(PaymentDraftUnknown):book.publish('owner:one',intent())
    with closing(fresh()) as cold:
        receipt=PaymentDraftBook(cold,privacy_guard=guard_payment_draft).lookup('owner:one','request:original')
    assert receipt and book.publish('owner:one',intent())==receipt and state(ledger)[1]==1


def test_missing_readback_is_unknown_even_after_the_original_commit(drafts,monkeypatch):
    ledger,book,_,_=drafts
    with monkeypatch.context() as patch:
        patch.setattr(book,'lookup',lambda *args:None)
        with pytest.raises(PaymentDraftUnknown):book.publish('owner:one',intent())
    receipt=book.lookup('owner:one','request:original')
    assert receipt and book.publish('owner:one',intent())==receipt and state(ledger)[1]==1


def test_rolled_back_append_cannot_become_completion_and_original_retry_is_safe(drafts,monkeypatch):
    ledger,book,_,_=drafts;append=ledger.append
    def failed(event):append(event);raise OSError('fixture failed before draft transaction commit')
    with monkeypatch.context() as patch:
        patch.setattr(ledger,'append',failed)
        with pytest.raises(PaymentDraftUnknown):book.publish('owner:one',intent())
    assert book.lookup('owner:one','request:original') is None and state(ledger)[1]==0
    assert book.publish('owner:one',intent())['state']=='DRAFT_STORED_NOT_APPROVED' and state(ledger)[1]==1


@pytest.mark.parametrize('clock_value',[True,None,1499])
def test_bad_or_regressed_storage_clock_cannot_rewrite_history_or_become_current_permission(drafts,clock_value):
    ledger,book,_,clock=drafts;original=intent();receipt=book.publish('owner:one',original);before=state(ledger)
    clock['now']=clock_value
    with pytest.raises(PaymentDraftError,match='STORAGE_CLOCK'):
        book.publish('owner:one',replace(original,request_id='request:later'))
    assert book.lookup('owner:one',original.request_id)==receipt and state(ledger)==before


def test_queued_expiry_rechecks_after_the_actual_SQL_writer_is_acquired(drafts,monkeypatch):
    ledger,book,fresh,clock=drafts;ready=threading.Event();connected=threading.Event();begin=threading.Event()
    def publish():
        # SQLite connections belong to the thread that created them. Build the
        # worker's real connection before the independent blocker takes its lock.
        with closing(fresh()) as owned:
            writer=PaymentDraftBook(owned,privacy_guard=guard_payment_draft,clock=lambda:clock['now'])
            atomic=owned.atomic
            @contextmanager
            def queued():
                ready.set()
                with atomic() as value:yield value
            owned.atomic=queued;connected.set()
            assert begin.wait(5),'owned writer was not released to begin'
            return writer.publish('owner:one',intent())
    with closing(fresh()) as blocker,ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(publish);assert connected.wait(5)
        with blocker.atomic():
            begin.set()
            assert ready.wait(5),'draft never reached the real SQL writer admission'
            clock['now']=2000
        with pytest.raises(PaymentContractError,match='EXPIRED'):future.result(5)
    assert book.lookup('owner:one','request:original') is None and state(ledger)[1]==0


@pytest.mark.parametrize('capacity',['records','bytes','global-events'])
def test_capacity_refuses_before_append_and_preserves_original_replay(drafts,capacity):
    ledger,book,_,_=drafts;original=intent();receipt=book.publish('owner:one',original);before=state(ledger)
    if capacity=='records':book.max_records=1
    elif capacity=='bytes':
        _,size,_=book._committed_history();book.max_bytes=size
    else:book.max_ledger_events=1
    assert book.publish('owner:one',original)==receipt
    with pytest.raises(PaymentDraftError,match='CAPACITY'):book.publish('owner:one',replace(original,request_id='request:another'))
    assert state(ledger)==before and book.lookup('owner:one',original.request_id)==receipt


@pytest.mark.parametrize('bad',['numeric-authority','wrong-hash','false-producer','wrong-correlation'])
def test_resealed_false_records_do_not_become_approved_or_valid_draft_history(drafts,bad):
    ledger,book,_,_=drafts;original=intent();body=original.body()
    if bad=='numeric-authority':body['execution_authority']=0
    event=make_event(EventKind.PAYMENT_DRAFT,'foreign' if bad=='false-producer' else PRODUCER,
        {'schema':SCHEMA,'intent':body,'intent_hash':'e'*64 if bad=='wrong-hash' else canonical_hash(body)},
        event_time_ms=1500,received_time_ms=1500,
        correlation_id='wrong' if bad=='wrong-correlation' else book._key('owner:one',original.request_id))
    ledger.append(event);before=state(ledger)
    with pytest.raises(PaymentDraftError):book.lookup('owner:one',original.request_id)
    with pytest.raises(PaymentDraftError):book.publish('owner:one',original)
    assert state(ledger)==before and ledger.verify_chain()[0]
