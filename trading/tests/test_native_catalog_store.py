"""Real source-ledger catalog vintages, replay and corrupt/unknown publication."""
from contextlib import closing,contextmanager
from copy import deepcopy
import json
import os
import uuid

import pytest

from vati.core import EventKind,Ledger,make_event
from vati.core.canonical import canonical_json
from vati.execution.ctrader.catalog import NativeSymbolCatalog
from vati.market_data.catalog_store import NativeCatalogStore,CatalogArchiveError,CatalogPublicationUnknown
from test_native_symbol_catalog import SCOPE,NOW,response,captured


@pytest.fixture(params=['sqlite','postgres'])
def source(tmp_path,request):
    if request.param=='postgres':
        if os.environ.get('VATI_TEST_PG_ISOLATED_FIXTURE')!='1' or not os.environ.get('VATI_TEST_PG_DSN'):
            pytest.skip('requires actual isolated PostgreSQL source fixture')
        from vati.core.ledger_pg import PostgresLedger
        owned=PostgresLedger(os.environ['VATI_TEST_PG_DSN'],ledger_name='catalog-source-'+uuid.uuid4().hex)
    else:owned=Ledger(tmp_path/'catalog-source.sqlite')
    with closing(owned) as ledger:
        yield ledger,NativeCatalogStore(ledger,clock=lambda:NOW+100)


def test_real_catalog_original_replay_and_cold_readback_do_not_append(source,tmp_path):
    ledger,store=source;value=captured();first=store.record('original',value);head=ledger.head()
    store.clock=lambda:(_ for _ in ()).throw(AssertionError('replay renewed capture clock'))
    assert store.record('original',value)==first and ledger.head()==head
    assert NativeCatalogStore(ledger).lookup(SCOPE,'original')==first
    frozen=store.snapshot(SCOPE,revision=1,record_ref=first['record_ref'])
    assert len(frozen['members'])==4 and frozen['qualified_for_research'] is False
    assert first['received_at_ms']==NOW and first['available_at_ms']==NOW+100


def test_delisting_source_update_does_not_backdate_or_rewrite_prior_universe_vintage(source):
    ledger,store=source;first=store.record('before',captured());past=store.snapshot(SCOPE,revision=1)
    rows=response();rows['symbol']=[r for r in rows['symbol'] if r['symbolId']!=1]
    rows['archivedSymbol'].append({'symbolId':1,'name':'EUR/USD','utcLastUpdateTimestamp':NOW-10000})
    update=captured(response=rows,received_at_ms=NOW+200);store.clock=lambda:NOW+300
    second=store.record('archived-later',update)
    old=store.snapshot(SCOPE,as_of_ms=NOW+250)
    assert old==past and old['members'][0]['visible'] is True
    current=store.snapshot(SCOPE,revision=2,record_ref=second['record_ref'])
    item=next(r for r in current['members'] if r['native_symbol_id']==1)
    assert item['source_kind']=='ARCHIVED' and item['visible'] is False
    assert item['lifecycle_effective_at_ms'] is None
    assert store.snapshot(SCOPE,revision=1,record_ref=first['record_ref'])==past


def test_catalog_scope_and_ordinal_remain_pinned_when_same_clock_has_more_captures(source):
    ledger,store=source;first=store.record('first',captured());before=store.snapshot(SCOPE,revision=1)
    altered=response();altered['symbol'][0]['symbolName']='new label'
    second=store.record('second',captured(response=altered))
    assert first['available_at_ms']==second['available_at_ms']
    assert store.snapshot(SCOPE,revision=1,record_ref=first['record_ref'])==before
    with pytest.raises(CatalogArchiveError,match='pinned'):store.snapshot(SCOPE,revision=2,record_ref=first['record_ref'])


def test_conflicting_request_keeps_original_first_capture(source):
    ledger,store=source;first=store.record('same-request',captured());head=ledger.head()
    with pytest.raises(CatalogArchiveError,match='conflicts'):store.record('same-request',captured(received_at_ms=NOW+1))
    assert ledger.head()==head and store.lookup(SCOPE,'same-request')==first


def test_financial_or_other_event_kinds_cannot_share_catalog_source_ledger(source):
    ledger,store=source;ledger.append(make_event(EventKind.SESSION,'fixture',{},event_time_ms=NOW,received_time_ms=NOW))
    with pytest.raises(CatalogArchiveError,match='dedicated source-only'):store.record('source',captured())
    assert ledger.count(EventKind.NATIVE_SYMBOL_CATALOG)==0


def test_global_byte_capacity_is_checked_before_new_scope_publication(source):
    ledger,store=source;store.record('one',captured())
    other=captured(scope=SCOPE|{'native_account_id':999},response=response()|{'ctidTraderAccountId':999})
    store.record('other-account',other)
    original_bytes=sum(len(canonical_json(e.body()).encode()) for e in ledger.iter())
    store.max_bytes=original_bytes+200
    before=ledger.count();head=ledger.head()
    with pytest.raises(CatalogArchiveError,match='byte capacity'):store.record('new-for-first-account',captured())
    assert ledger.count()==before and ledger.head()==head


def test_hidden_original_readback_refuses_new_publication_instead_of_recreating_it(source,monkeypatch):
    ledger,store=source;store.record('one',captured());head=ledger.head();iterate=ledger.iter
    def hidden(kind=None,correlation_id=None):
        for event in iterate(kind,correlation_id):
            if event.kind is not EventKind.NATIVE_SYMBOL_CATALOG:yield event
    monkeypatch.setattr(ledger,'iter',hidden)
    with pytest.raises(CatalogArchiveError,match='readback missing'):store.record('new',captured())
    assert ledger.head()==head and ledger.count()==1


def test_lost_commit_ack_stays_unknown_then_original_is_recovered_once(source,monkeypatch):
    ledger,store=source;atomic=ledger.atomic
    @contextmanager
    def lost():
        outer=(not ledger._conn.in_transaction if hasattr(ledger._conn,'in_transaction')
            else ledger._atomic_depth==0)
        before=ledger.count()
        with atomic():yield ledger
        if outer and ledger.count()>before:raise OSError('fixture native catalog ACK lost')
    with monkeypatch.context() as patch:
        patch.setattr(ledger,'atomic',lost)
        with pytest.raises(CatalogPublicationUnknown):store.record('original-request',captured())
    assert ledger.count()==1;original=store.lookup(SCOPE,'original-request')
    assert original is not None and store.record('original-request',captured())==original
    assert ledger.count()==1


def test_missing_independent_readback_never_becomes_acknowledged_publication(source,monkeypatch):
    ledger,store=source
    with monkeypatch.context() as patch:
        patch.setattr(store,'lookup',lambda *args:None)
        with pytest.raises(CatalogPublicationUnknown):store.record('original',captured())
    assert ledger.count()==1 and store.lookup(SCOPE,'original') is not None


def test_different_native_accounts_have_distinct_original_scopes_and_revision_sequences(source):
    ledger,store=source;one=store.record('shared-request-id',captured())
    other=captured(scope=SCOPE|{'native_account_id':999},response=response()|{'ctidTraderAccountId':999})
    two=store.record('shared-request-id',other)
    assert one['revision']==two['revision']==1 and one['record_ref']!=two['record_ref']
    assert store.snapshot(SCOPE)['captured']['metadata']['scope']==SCOPE


def test_known_past_catalog_before_first_availability_is_missing_not_an_empty_universe(source):
    ledger,store=source;store.record('original',captured())
    assert store.snapshot(SCOPE,as_of_ms=NOW+99) is None
    assert store.snapshot(SCOPE,as_of_ms=NOW+100)['receipt']['revision']==1


def test_publication_clock_cannot_move_backwards_or_precede_source_capture(source):
    ledger,store=source;store.record('original',captured());head=ledger.head();store.clock=lambda:NOW+50
    with pytest.raises(CatalogArchiveError,match='clock moved backwards'):store.record('late',captured())
    assert ledger.head()==head
    store.clock=lambda:NOW-1
    with pytest.raises(ValueError):store.record('earlier-than-native',captured())
    assert ledger.head()==head


def test_original_catalog_cannot_self_issue_dataset_permission_even_with_correct_event_seal(source):
    ledger,store=source;store.record('original',captured());event=next(ledger.iter());payload=deepcopy(event.payload)
    payload['captured']['qualified_for_research']=True
    # Simulate privileged source tampering, preserving a valid outer event seal.
    with closing(Ledger(':memory:')) as altered:
        altered.append(make_event(EventKind.NATIVE_SYMBOL_CATALOG,event.producer,payload,
            event_time_ms=event.event_time_ms,received_time_ms=event.received_time_ms,correlation_id=event.correlation_id))
        with pytest.raises(ValueError,match='authority'):NativeCatalogStore(altered).snapshot(SCOPE)


@pytest.mark.parametrize('field,value',[('event_time_ms',True),('received_time_ms',True),('event_time_ms',1.0)])
def test_correct_event_seal_does_not_make_bool_or_float_source_clocks_valid(field,value):
    body=response();body['archivedSymbol'][0]['utcLastUpdateTimestamp']=0
    native=captured(response=body,received_at_ms=1)
    with closing(Ledger(':memory:')) as original:
        NativeCatalogStore(original,clock=lambda:1).record('original',native)
        event=next(original.iter())
    times={'event_time_ms':1,'received_time_ms':1}|{field:value}
    with closing(Ledger(':memory:')) as altered:
        altered.append(make_event(EventKind.NATIVE_SYMBOL_CATALOG,event.producer,event.payload,
            correlation_id=event.correlation_id,**times))
        with pytest.raises(CatalogArchiveError):NativeCatalogStore(altered).snapshot(SCOPE)


def _catalog_process(path,body,queue):
    try:
        with closing(Ledger(path)) as ledger:
            result=NativeCatalogStore(ledger,clock=lambda:NOW+100).record('shared-process-request',NativeSymbolCatalog.from_body(body))
            queue.put(('ok',result))
    except BaseException as error:queue.put(('error',type(error).__name__))
    finally:queue.close();queue.join_thread()


def test_real_separate_process_catalog_writers_publish_one_original(tmp_path):
    import multiprocessing
    context=multiprocessing.get_context('spawn');queue=context.Queue();path=str(tmp_path/'catalog-processes.sqlite')
    with closing(Ledger(path)):pass
    children=[context.Process(target=_catalog_process,args=(path,captured().body(),queue)) for _ in range(2)]
    try:
        for child in children:child.start()
        for child in children:
            child.join(10);assert not child.is_alive() and child.exitcode==0
        results=[queue.get(timeout=3) for _ in children]
        assert all(status=='ok' for status,_ in results) and results[0][1]==results[1][1]
        with closing(Ledger(path)) as ledger:
            assert ledger.count(EventKind.NATIVE_SYMBOL_CATALOG)==1 and ledger.verify_chain()==(True,1)
    finally:
        for child in children:
            if child.is_alive():child.terminate()
            if child.pid is not None:child.join(5)
        queue.close();queue.join_thread()


def test_real_concurrent_postgres_catalog_writers_share_original_source_receipt():
    if os.environ.get('VATI_TEST_PG_ISOLATED_FIXTURE')!='1' or not os.environ.get('VATI_TEST_PG_DSN'):
        pytest.skip('requires actual isolated PostgreSQL source fixture')
    from concurrent.futures import ThreadPoolExecutor
    from vati.core.ledger_pg import PostgresLedger
    name='catalog-cas-'+uuid.uuid4().hex
    def publish(_number):
        with closing(PostgresLedger(os.environ['VATI_TEST_PG_DSN'],ledger_name=name)) as ledger:
            return NativeCatalogStore(ledger,clock=lambda:NOW+100).record('shared-db-request',captured())
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(publish,range(2)))
    assert results[0]==results[1]
    with closing(PostgresLedger(os.environ['VATI_TEST_PG_DSN'],ledger_name=name)) as ledger:
        assert ledger.count()==1 and ledger.verify_chain()==(True,1)


def test_actual_catalog_collector_joins_independent_wire_reader_and_original_source_ledger(source):
    from test_native_symbol_catalog import CatalogPeer
    from test_ctrader import make_adapter
    from vati.market_data.catalog_store import NativeCatalogCollector
    ledger,store=source;peer=CatalogPeer();parent=make_adapter(peer);parent.clock=lambda:NOW
    collector=NativeCatalogCollector(store,parent.market_reader)
    try:
        first=collector.collect('actual-wire-to-source',SCOPE)
        assert ledger.count()==1 and len(peer.requests)==3 and not parent.transport.connected
        collector.reader_factory=lambda:(_ for _ in ()).throw(AssertionError('original source request was sent again'))
        assert collector.collect('actual-wire-to-source',SCOPE)==first and len(peer.requests)==3
        assert store.snapshot(SCOPE,revision=1)['members'][-1]['source_kind']=='ARCHIVED'
    finally:peer.close()


def test_reader_is_closed_before_catalog_source_writer_is_entered(source):
    from vati.market_data.catalog_store import NativeCatalogCollector
    ledger,store=source;closed=[];record=store.record
    class Reader:
        def read_catalog(self,scope):return captured()
        def close(self):closed.append(True)
    def write(*args):
        assert closed==[True]
        return record(*args)
    store.record=write
    assert NativeCatalogCollector(store,Reader).collect('closed-before-writer',SCOPE)['revision']==1


def test_collector_does_not_publish_other_native_scope_or_partial_request_profile(source):
    from vati.market_data.catalog_store import NativeCatalogCollector
    ledger,store=source;closed=[]
    class Other:
        def read_catalog(self,scope):return captured(scope=SCOPE|{'native_account_id':999},response=response()|{'ctidTraderAccountId':999})
        def close(self):closed.append(True)
    with pytest.raises(CatalogArchiveError,match='scope or request'):NativeCatalogCollector(store,Other).collect('wrong-scope',SCOPE)
    assert closed==[True] and ledger.count()==0


def test_real_driver_commit_lost_reply_is_unknown_then_reconciled_on_original_connection(tmp_path):
    import sqlite3
    from vati.market_data.catalog_store import NativeCatalogCollector
    with closing(Ledger(tmp_path/'driver-unknown.sqlite')) as ledger:
        store=NativeCatalogStore(ledger,clock=lambda:NOW+100);atomic=ledger.atomic;read=[];closed=[]
        @contextmanager
        def lost():
            outer=not ledger._conn.in_transaction;before=ledger.count()
            with atomic():yield ledger
            if outer and ledger.count()>before:raise sqlite3.OperationalError('fixture native SQL commit reply lost')
        class Reader:
            def read_catalog(self,scope):read.append(True);return captured()
            def close(self):closed.append(True)
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(ledger,'atomic',lost)
            result=NativeCatalogCollector(store,Reader).collect('driver-original',SCOPE)
        assert result==store.lookup(SCOPE,'driver-original')
        assert ledger.count()==1 and read==closed==[True]


def test_prepublication_source_storage_failure_is_not_a_completed_or_unknown_write(source,monkeypatch):
    import sqlite3
    ledger,store=source
    @contextmanager
    def unavailable():
        raise sqlite3.OperationalError('fixture source writer unavailable')
        yield
    monkeypatch.setattr(ledger,'atomic',unavailable)
    with pytest.raises(CatalogArchiveError,match='before publication'):store.record('unstarted',captured())
    assert ledger.count()==0


def test_actual_postgres_commit_reply_loss_retains_original_durable_catalog(monkeypatch):
    if os.environ.get('VATI_TEST_PG_ISOLATED_FIXTURE')!='1' or not os.environ.get('VATI_TEST_PG_DSN'):
        pytest.skip('requires actual isolated PostgreSQL source fixture')
    import psycopg
    from vati.core.ledger_pg import PostgresLedger
    with closing(PostgresLedger(os.environ['VATI_TEST_PG_DSN'],ledger_name='catalog-ack-'+uuid.uuid4().hex)) as ledger:
        store=NativeCatalogStore(ledger,clock=lambda:NOW+100);atomic=ledger.atomic
        @contextmanager
        def lost():
            outer=ledger._atomic_depth==0;before=ledger.count()
            with atomic():yield ledger
            if outer and ledger.count()>before:raise psycopg.OperationalError('fixture PostgreSQL commit reply lost')
        with monkeypatch.context() as patch:
            patch.setattr(ledger,'atomic',lost)
            with pytest.raises(CatalogPublicationUnknown):store.record('original-pg-query',captured())
        assert ledger.count()==1 and ledger.verify_chain()==(True,1)
        original=store.lookup(SCOPE,'original-pg-query')
        assert original is not None and store.record('original-pg-query',captured())==original
        assert ledger.count()==1


def test_actual_postgres_writer_queue_uses_availability_after_lock_acquisition():
    if os.environ.get('VATI_TEST_PG_ISOLATED_FIXTURE')!='1' or not os.environ.get('VATI_TEST_PG_DSN'):
        pytest.skip('requires actual isolated PostgreSQL source fixture')
    import psycopg,queue,time
    from concurrent.futures import ThreadPoolExecutor
    from vati.core.ledger_pg import PostgresLedger
    name='catalog-clock-'+uuid.uuid4().hex;clock={'value':NOW+100};backend=queue.Queue()
    def publish():
        with closing(PostgresLedger(os.environ['VATI_TEST_PG_DSN'],ledger_name=name)) as writer:
            backend.put(writer._conn.info.backend_pid)
            return NativeCatalogStore(writer,clock=lambda:clock['value']).record('queued-source',captured())
    with closing(PostgresLedger(os.environ['VATI_TEST_PG_DSN'],ledger_name=name)) as guard:
        with ThreadPoolExecutor(max_workers=1) as pool:
            with guard.atomic():
                future=pool.submit(publish)
                pid=backend.get(timeout=5)
                with closing(psycopg.connect(os.environ['VATI_TEST_PG_DSN'],autocommit=True)) as observer:
                    deadline=time.monotonic()+5
                    while time.monotonic()<deadline:
                        row=observer.execute('SELECT wait_event_type FROM pg_stat_activity WHERE pid=%s',(pid,)).fetchone()
                        if row and row[0]=='Lock':break
                        time.sleep(.01)
                    else:raise AssertionError('owned catalog writer was not observed queued on the SQL lock')
                assert not future.done();clock['value']=NOW+200
            result=future.result(timeout=10)
    assert result['received_at_ms']==NOW and result['available_at_ms']==NOW+200


def test_hidden_source_snapshot_is_explicitly_refused_even_if_the_sql_chain_is_healthy(source,monkeypatch):
    ledger,store=source;store.record('original',captured());head=ledger.head();iterate=ledger.iter
    def hidden(kind=None,correlation_id=None):
        for event in iterate(kind,correlation_id):
            if event.kind is not EventKind.NATIVE_SYMBOL_CATALOG:yield event
    monkeypatch.setattr(ledger,'iter',hidden)
    refused=False
    try:store.snapshot(SCOPE)
    except CatalogArchiveError:refused=True
    assert refused,'missing source readback was reported as an empty universe'
    assert ledger.head()==head and ledger.count()==1
