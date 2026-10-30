"""Real PostgreSQL original cash identities and account-scoped background writes."""
from contextlib import contextmanager
from dataclasses import replace
from decimal import Decimal as D
import concurrent.futures,threading
import pytest
from test_postgres_ledger_isolation import pg_dsn
from test_funding_journal import statement
from test_funding_runtime import setup
from vati.core.events import EventKind
from vati.core.ledger_pg import PostgresLedger
from vati.funding.journal import FundingBook
from vati.funding.worker import FundingIngestWorker

def test_postgres_concurrent_native_replay_is_one_original_and_conflicts_do_not_restate_it(pg_dsn):
    source=statement();initial=PostgresLedger(pg_dsn,ledger_name='funding-one');barrier=threading.Barrier(2)
    def record(_):
        ledger=PostgresLedger(pg_dsn,ledger_name='funding-one')
        try:
            barrier.wait(timeout=5)
            return FundingBook(ledger,clock=lambda:5000).record_statement(source)
        finally:ledger.close()
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(record,range(2)))
        assert results[0]==results[1] and initial.count(EventKind.FUNDING_STATEMENT)==1
        book=FundingBook(initial,clock=lambda:6000)
        changed=replace(source,movements=(replace(source.movements[0],delta=D('1')),))
        assert book.record_statement(changed)['state']=='CONFLICT'
        assert book.observations(source.scope_hash)['state']=='CONFLICT'
        assert book.observations(source.scope_hash,as_of=results[0]['statement_ref'])['state']=='OBSERVED'
        assert book.record_statement(source)==results[0] and initial.verify_chain()[0]
    finally:initial.close()

def test_postgres_lost_real_commit_ack_returns_the_original_native_receipt(pg_dsn):
    ledger=PostgresLedger(pg_dsn,ledger_name='funding-one');original=ledger.atomic;armed=True
    @contextmanager
    def uncertain():
        nonlocal armed
        outer=ledger._atomic_depth==0
        with original():yield ledger
        if outer and armed:armed=False;raise OSError('fixture-native-commit-ack-lost')
    ledger.atomic=uncertain;source=statement()
    try:
        with pytest.raises(OSError):FundingBook(ledger,clock=lambda:5000).record_statement(source)
        first=list(ledger.iter(EventKind.FUNDING_STATEMENT))[0]
        recovered=FundingBook(ledger,clock=lambda:6000).record_statement(source)
        assert recovered['statement_ref']==first.hash and recovered['received_at_ms']==5000 and ledger.count()==1
    finally:ledger.close()

def test_background_funding_worker_preserves_the_original_postgres_named_ledger(pg_dsn,tmp_path):
    _,_,adapter=setup(tmp_path);account=adapter.sync_account()
    class Reader:
        def cash_movements(self,**window):return adapter.cash_movements(**window)
        def close(self):pass
    ledger=PostgresLedger(pg_dsn,ledger_name='funding-one');other=PostgresLedger(pg_dsn,ledger_name='funding-two')
    worker=FundingIngestWorker(pg_dsn,Reader,ledger_name=ledger.name)
    try:
        assert worker.submit(account,3000)['state']=='PENDING' and worker.wait_idle()
        assert ledger.count(EventKind.FUNDING_STATEMENT)==1 and other.count()==0
        assert ledger.verify_chain()[0] and other.verify_chain()[0]
    finally:worker.close();ledger.close();other.close()
