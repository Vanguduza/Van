"""Actual capture worker and owner portfolio consume the original SQL postings."""
from contextlib import closing, contextmanager
import threading

from test_funding_runtime import setup
from test_funding_owner_reports import profile, snapshot
from vati.app.portfolio import account_states
from vati.core import EventKind, Ledger
from vati.core.units import UnitError
from vati.funding.journal import FundingBook
from vati.funding.movement_journal import FinancialMovementBook
from vati.funding.runtime import capture_funding
from vati.funding.worker import FundingIngestWorker


def test_real_capture_and_current_owner_report_read_exact_native_postings(tmp_path):
    ledger,transport,adapter=setup(tmp_path)
    with closing(ledger):
        account=adapter.sync_account();result=capture_funding(ledger,adapter,account,now_ms=3000)
        posted=result['financial_movements'];assert posted['posted_count']==1 and posted['pending_count']==0
        assert 'movements' not in posted
        movement=FinancialMovementBook(ledger).projection(account.funding_mark.scope_hash)['movements'][0]['movement']
        assert movement['amount']['minor_units']=='1234567' and movement['amount']['scale']==8
        assert [r['amount']['minor_units'] for r in movement['postings']]==['1234567','-1234567']
        event=snapshot(ledger,funding_observation=result)
        before=ledger.head(),ledger.count()
        owner=account_states(ledger,[profile()])[0]
        detail=owner['funding']['financial_movements']
        assert detail['posted_count']==posted['posted_count']
        assert detail['movements'][0]['publication']==posted['last_publication']
        assert detail['movements'][0]['movement']==movement
        assert owner['funding']['snapshot_ref']==event.hash
        assert owner['day_pnl'] is None and owner['drawdown_pct'] is None
        assert posted['risk_capital_qualified'] is posted['execution_authority'] is False
        assert (ledger.head(),ledger.count())==before
        for changed in (profile(login='999'),profile(demo=False),profile(currency='USD')):
            hidden=account_states(ledger,[changed])[0]['funding']['financial_movements']
            assert hidden['state']=='UNSUPPORTED' and 'movements' not in hidden
        assert not any(name in {'ProtoOANewOrderReq','ProtoOAWithdrawReq'} for name,_ in transport.requests)


def test_native_source_committed_before_restart_is_projected_from_older_window(tmp_path):
    ledger,transport,adapter=setup(tmp_path)
    with closing(ledger):
        original=adapter.cash_movements(from_ms=0,to_ms=2000)
        receipt=FundingBook(ledger).record_statement(original)
        assert ledger.count(EventKind.FINANCIAL_MOVEMENT)==0
    with closing(Ledger(tmp_path/'facts.sqlite')) as recovered:
        transport.rows=[]
        result=capture_funding(recovered,adapter,adapter.sync_account(),now_ms=3000)
        posted=result['financial_movements']
        assert posted['posted_count']==1 and posted['pending_count']==0
        detail=FinancialMovementBook(recovered).projection(original.scope_hash)
        assert detail['movements'][0]['movement']['source_statement_ref']==receipt['statement_ref']
        before=recovered.count(EventKind.FINANCIAL_MOVEMENT)
        capture_funding(recovered,adapter,adapter.sync_account(),now_ms=3000)
        assert recovered.count(EventKind.FINANCIAL_MOVEMENT)==before


def test_projection_failure_preserves_native_facts_and_owner_read_never_writes(tmp_path,monkeypatch):
    ledger,transport,adapter=setup(tmp_path)
    with closing(ledger):
        with monkeypatch.context() as patch:
            patch.setattr(FinancialMovementBook,'materialize',lambda *_:(_ for _ in ()).throw(UnitError('fixture-private-note')))
            result=capture_funding(ledger,adapter,adapter.sync_account(),now_ms=3000)
        assert result['state']=='OBSERVED' and result['financial_movements']['state']=='UNAVAILABLE'
        assert 'fixture-private-note' not in str(result)
        snapshot(ledger,funding_observation=result);before=ledger.head(),ledger.count()
        projection=account_states(ledger,[profile()])[0]['funding']['financial_movements']
        assert projection['state']=='PENDING' and projection['pending_count']==1
        assert ledger.count(EventKind.FINANCIAL_MOVEMENT)==0 and (ledger.head(),ledger.count())==before
        result=capture_funding(ledger,adapter,adapter.sync_account(),now_ms=3000)
        assert result['financial_movements']['posted_count']==1


def test_actual_projection_commit_lost_ack_is_unknown_then_original_recovers(tmp_path,monkeypatch):
    ledger,transport,adapter=setup(tmp_path)
    with closing(ledger):
        atomic=ledger.atomic;failed=False
        @contextmanager
        def lost():
            nonlocal failed
            outer=not ledger._conn.in_transaction
            with atomic() as writer:yield writer
            if outer and not failed and ledger.count(EventKind.FINANCIAL_MOVEMENT):
                failed=True;raise OSError('fixture-private-lost-ACK')
        with monkeypatch.context() as patch:
            patch.setattr(ledger,'atomic',lost)
            result=capture_funding(ledger,adapter,adapter.sync_account(),now_ms=3000)
        assert failed and result['state']=='OBSERVED'
        projection=result['financial_movements'];assert projection['state']=='UNKNOWN'
        request=projection['original_request_id'];original=FinancialMovementBook(ledger).lookup(request)
        assert original and 'fixture-private' not in str(result)
        recovered=capture_funding(ledger,adapter,adapter.sync_account(),now_ms=3000)
        assert recovered['financial_movements']['posted_count']==1
        assert FinancialMovementBook(ledger).lookup(request)==original


def test_readonly_projection_unavailable_does_not_claim_empty_or_qualified_cash(tmp_path,monkeypatch):
    ledger,transport,adapter=setup(tmp_path)
    with closing(ledger):
        result=capture_funding(ledger,adapter,adapter.sync_account(),now_ms=3000)
        snapshot(ledger,funding_observation=result)
        monkeypatch.setattr(FinancialMovementBook,'projection',lambda *_:(_ for _ in ()).throw(OSError('fixture-private-storage')))
        posted=account_states(ledger,[profile()])[0]['funding']['financial_movements']
        assert posted['state']=='UNAVAILABLE' and 'posted_count' not in posted and 'movements' not in posted
        assert posted['risk_capital_qualified'] is posted['execution_authority'] is False
        assert 'fixture-private' not in str(posted)


def test_actual_separate_worker_publishes_and_reaps_its_owned_reader_thread(tmp_path):
    ledger,transport,adapter=setup(tmp_path);closed=threading.Event()
    class Reader:
        def cash_movements(self,**window):return adapter.cash_movements(**window)
        def close(self):closed.set()
    with closing(ledger):
        worker=FundingIngestWorker(ledger.path,Reader)
        try:
            assert worker.submit(adapter.sync_account(),3000)['state']=='PENDING'
            assert worker.wait_idle(timeout=10)
            assert ledger.count(EventKind.FINANCIAL_MOVEMENT)==1
            assert worker._result['financial_movements']['posted_count']==1
        finally:
            worker.close();worker._thread.join(timeout=10)
        assert closed.is_set() and not worker._thread.is_alive()
