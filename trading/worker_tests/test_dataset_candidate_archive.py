"""Actual source objects and SQLite/PostgreSQL candidate-publication writers."""
from contextlib import closing, contextmanager
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import uuid

import pytest

from test_forecast_source_partitions import source
from test_dataset_source_inspection import binding
from test_dataset_manifest_candidates import parse
from vati.core import Ledger, EventKind, make_event
from vati.core.canonical import canonical_hash
from vati.research.dataset_archive import DatasetCandidateArchive, DatasetPublicationUnknown
from vati.research.dataset_manifest import DatasetContractError
from vati.research.dataset_sources import NativeDatasetSourceInspector


def state(ledger):
    with ledger.read_snapshot():return ledger.head(),ledger.count()


@pytest.fixture(params=['sqlite','postgres'])
def publication(source,tmp_path,request):
    if request.param=='postgres':
        if os.environ.get('VATI_TEST_PG_ISOLATED_FIXTURE')!='1' or not os.environ.get('VATI_TEST_PG_DSN'):
            pytest.skip('requires actual isolated PostgreSQL source fixture')
        from vati.core.ledger_pg import PostgresLedger
        owned=PostgresLedger(os.environ['VATI_TEST_PG_DSN'],ledger_name='dataset-candidate-'+uuid.uuid4().hex)
    else:owned=Ledger(tmp_path/'candidates.sqlite')
    partitions,record,contract=binding(source,tmp_path)
    inspector=NativeDatasetSourceInspector(partitions)
    with closing(owned) as ledger:
        yield ledger,DatasetCandidateArchive(ledger,inspector,clock=lambda:500000),record,contract


def test_real_publication_readback_replay_and_current_inspection_stay_unadmitted(publication):
    ledger,archive,record,contract=publication
    first=archive.publish('original',parse(record),expected_scope=contract.native_scope)
    assert first['status']=='CANDIDATE_PUBLISHED_NOT_ADMITTED' and first['qualified_for_research'] is False
    frozen=archive.inspect('original')
    assert frozen['manifest']['created_at']=='1970-01-01T00:08:20.000Z'
    assert frozen['manifest']['created_at']!=record['created_at']
    assert frozen['current_inspection']['resolved_source_facts']['row_count']==3
    assert frozen['current_inspection']['qualified_for_research'] is False
    head=state(ledger)[0];archive.clock=lambda:pytest.fail('original replay renewed creation time')
    archive.inspector=None
    assert archive.publish('original',parse(record),expected_scope=contract.native_scope)==first
    assert DatasetCandidateArchive(ledger).lookup('original')==first and state(ledger)[0]==head
    assert ledger.count(EventKind.DATASET_MANIFEST_CANDIDATE)==1


def test_original_request_and_record_identity_cannot_be_rebound(publication):
    ledger,archive,record,c=publication
    first=archive.publish('original',parse(record),expected_scope=c.native_scope)
    changed=deepcopy(record);changed['consent_scope_ref']='other-unresolved-reference'
    with pytest.raises(DatasetContractError,match='REQUEST_CONFLICT'):
        archive.publish('original',parse(changed),expected_scope=c.native_scope)
    with pytest.raises(DatasetContractError,match='RECORD_ID_OR_EVENT'):
        archive.publish('another-request',parse(record),expected_scope=c.native_scope)
    assert archive.lookup('original')==first and state(ledger)[1]==1


def test_source_unavailable_after_publication_does_not_erase_historical_receipt(publication):
    ledger,archive,record,c=publication
    first=archive.publish('original',parse(record),expected_scope=c.native_scope)
    path=archive.inspector.partitions.root/(record['partitions'][0]['artifact_id']+'.parquet')
    path.unlink()
    assert archive.lookup('original')==first
    with pytest.raises(ValueError):archive.inspect('original')
    assert first['current_source_use_verified'] is False and ledger.count()==1


@pytest.mark.parametrize('damage',['missing','changed'])
def test_new_publication_requires_current_original_bytes_before_any_sql_append(publication,damage):
    ledger,archive,record,c=publication
    path=archive.inspector.partitions.root/(record['partitions'][0]['artifact_id']+'.parquet')
    if damage=='missing':path.unlink()
    else:path.write_bytes(b'PAR1not-the-original-sourcePAR1')
    before=state(ledger)
    with pytest.raises(ValueError):archive.publish('invalid-source',parse(record),expected_scope=c.native_scope)
    assert state(ledger)==before


def test_nested_writer_and_read_transaction_cannot_claim_durable_completion(publication):
    ledger,archive,record,c=publication
    with ledger.atomic():
        with pytest.raises(DatasetContractError,match='OWN_TRANSACTION'):
            archive.publish('inside-writer',parse(record),expected_scope=c.native_scope)
    with ledger.read_snapshot():
        with pytest.raises(DatasetContractError,match='OWN_TRANSACTION'):
            archive.publish('inside-reader',parse(record),expected_scope=c.native_scope)
    assert ledger.count()==0


def test_lookup_cannot_report_an_uncommitted_candidate_as_published(publication):
    ledger,archive,record,c=publication
    archive.publish('committed',parse(record),expected_scope=c.native_scope)
    with ledger.atomic():
        with pytest.raises(DatasetContractError,match='OWN_TRANSACTION'):archive.lookup('committed')
        with pytest.raises(DatasetContractError,match='OWN_TRANSACTION'):archive.inspect('committed')
    assert archive.lookup('committed')['status']=='CANDIDATE_PUBLISHED_NOT_ADMITTED'


def test_financial_or_other_event_kinds_are_not_a_candidate_metadata_store(publication):
    ledger,archive,record,c=publication
    ledger.append(make_event(EventKind.SESSION,'test-unrelated',{'preserve':True},
        event_time_ms=1,received_time_ms=1,correlation_id='unrelated'))
    head=state(ledger)[0]
    with pytest.raises(DatasetContractError,match='DEDICATED_SOURCE_LEDGER'):
        archive.publish('do-not-mix',parse(record),expected_scope=c.native_scope)
    assert state(ledger)==(head,1)


@pytest.mark.parametrize('kind',['bytes','events'])
def test_publication_capacity_refuses_before_appending_and_preserves_original(publication,kind):
    ledger,archive,record,c=publication
    if kind=='bytes':archive.max_bytes=1
    else:
        archive.max_events=1;archive.publish('original',parse(record),expected_scope=c.native_scope)
        record=record|{'record_id':'another-fixture-record'}
    head,count=state(ledger)
    with pytest.raises(DatasetContractError,match='CAPACITY'):
        archive.publish('over-capacity',parse(record),expected_scope=c.native_scope)
    assert state(ledger)==(head,count)


def test_actual_committed_lost_ack_reconciles_original_without_second_publication(publication,monkeypatch):
    ledger,archive,record,c=publication;atomic=ledger.atomic
    @contextmanager
    def lost():
        outer=getattr(ledger,'_atomic_depth',0)==0 and not getattr(ledger._conn,'in_transaction',False)
        with atomic() as writer:yield writer
        if outer:raise OSError('injected ACK loss after actual commit')
    with monkeypatch.context() as patch:
        patch.setattr(ledger,'atomic',lost)
        with pytest.raises(DatasetPublicationUnknown):
            archive.publish('lost-ack',parse(record),expected_scope=c.native_scope)
    original=archive.lookup('lost-ack');assert original and state(ledger)[1]==1
    assert archive.publish('lost-ack',parse(record),expected_scope=c.native_scope)==original
    assert ledger.count()==1


def test_initial_storage_failure_is_unstarted_and_does_not_inspect_sources(publication,monkeypatch):
    ledger,archive,record,c=publication
    monkeypatch.setattr(archive,'_history',lambda:(_ for _ in ()).throw(OSError('storage unavailable')))
    monkeypatch.setattr(archive.inspector,'inspect',lambda *a,**k:pytest.fail('source read after storage refusal'))
    with pytest.raises(DatasetContractError,match='STORAGE_UNAVAILABLE_BEFORE'):
        archive.publish('unstarted',parse(record),expected_scope=c.native_scope)
    assert state(ledger)[1]==0


def test_hidden_original_readback_is_not_a_success_receipt(publication,monkeypatch):
    ledger,archive,record,c=publication
    with monkeypatch.context() as patch:
        patch.setattr(archive,'lookup',lambda _:None)
        with pytest.raises(DatasetPublicationUnknown,match='READBACK_UNAVAILABLE'):
            archive.publish('hidden',parse(record),expected_scope=c.native_scope)
    assert archive.lookup('hidden') and state(ledger)[1]==1
    assert archive.publish('hidden',parse(record),expected_scope=c.native_scope)['request_id']=='hidden'


def test_backwards_creation_clock_does_not_append_or_rewrite_original(publication):
    ledger,archive,record,c=publication
    first=archive.publish('first',parse(record),expected_scope=c.native_scope)
    archive.clock=lambda:499999
    with pytest.raises(DatasetContractError,match='CLOCK_MOVED_BACKWARDS'):
        archive.publish('second',parse(record|{'record_id':'later-fixture-record'}),expected_scope=c.native_scope)
    assert archive.lookup('first')==first and state(ledger)[1]==1


@pytest.mark.parametrize('same_request',[True,False])
def test_independent_sql_writers_serialize_original_request_and_record_identity(publication,monkeypatch,same_request):
    ledger,archive,record,c=publication;barrier=threading.Barrier(2)
    inspect=NativeDatasetSourceInspector.inspect
    def synchronized(self,*args,**kwargs):
        result=inspect(self,*args,**kwargs);barrier.wait(timeout=10);return result
    monkeypatch.setattr(NativeDatasetSourceInspector,'inspect',synchronized)
    def publish(number):
        if isinstance(ledger,Ledger):owned=Ledger(ledger.path)
        else:
            from vati.core.ledger_pg import PostgresLedger
            owned=PostgresLedger(ledger.path,ledger_name=ledger.name)
        with closing(owned):
            other=DatasetCandidateArchive(owned,NativeDatasetSourceInspector(archive.inspector.partitions),clock=lambda:500000)
            try:return other.publish('same' if same_request else 'writer-'+str(number),parse(record),expected_scope=c.native_scope)
            except DatasetContractError as error:return error
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs=[pool.submit(publish,n) for n in range(2)]
        results=[job.result(timeout=30) for job in jobs]
    assert state(ledger)[1]==1 and ledger.verify_chain()[0]
    if same_request:
        assert results[0]==results[1] and results[0]['status']=='CANDIDATE_PUBLISHED_NOT_ADMITTED'
    else:
        assert sum(isinstance(result,dict) for result in results)==1
        refusal=next(result for result in results if isinstance(result,DatasetContractError))
        assert 'RECORD_ID_OR_EVENT_CAPACITY_CONFLICT' in str(refusal)


@pytest.mark.parametrize('damage',['decision','schema','producer','request_digest','created_at','witness'])
def test_even_sealed_incompatible_original_records_refuse_recovery(publication,damage):
    ledger,archive,record,c=publication
    archive.publish('original',parse(record),expected_scope=c.native_scope)
    with ledger.read_snapshot():original=next(ledger.iter(EventKind.DATASET_MANIFEST_CANDIDATE))
    payload=deepcopy(original.payload);payload['request_id']='malformed'
    payload['manifest']['record_id']=payload['requested_manifest']['record_id']='another-record'
    payload['request_sha256']=canonical_hash({'manifest':payload['requested_manifest'],'native_scope':payload['native_scope']})
    if damage=='request_digest':payload['request_sha256']='f'*64
    elif damage=='created_at':payload['manifest']['created_at']='1970-01-01T00:08:21Z'
    elif damage=='witness':payload['source_witness_digest']='invalid'
    altered=replace(original,payload=payload,correlation_id='another-record',hash='',
        decision_time_ms=1 if damage=='decision' else None,
        schema_version=2 if damage=='schema' else 1,
        producer='another-owner' if damage=='producer' else original.producer)
    altered=replace(altered,hash=canonical_hash(altered.body()));ledger.append(altered)
    head=state(ledger)
    with pytest.raises(DatasetContractError,match='ORIGINAL_'):archive.lookup('original')
    assert state(ledger)==head and ledger.verify_chain()[0]


def test_actual_cli_publishes_and_cold_looks_up_the_same_unadmitted_manifest(source,tmp_path):
    partitions,record,c=binding(source,tmp_path);ledger=tmp_path/'cli-candidates.sqlite'
    spec=tmp_path/'publish.json';spec.write_text(json.dumps({'operation':'dataset_candidate_publish',
        'request_id':'cli-original','manifest':record,'expected_scope':c.native_scope}))
    env=dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parents[1]))
    command=[sys.executable,'-m','vati','research','--ledger',str(ledger),'--spec',str(spec)]
    child=subprocess.run(command+['--native-archive',str(source[0].root),'--source-partitions',str(partitions.root)],
        env=env,capture_output=True,text=True,timeout=30)
    assert child.returncode==0,child.stderr
    first=json.loads(child.stdout)['candidate_publication']
    spec.write_text(json.dumps({'operation':'dataset_candidate_lookup','request_id':'cli-original'}))
    cold=subprocess.run(command,env=env,capture_output=True,text=True,timeout=30)
    assert cold.returncode==0,cold.stderr
    assert json.loads(cold.stdout)['candidate_publication']==first
    assert first['status']=='CANDIDATE_PUBLISHED_NOT_ADMITTED' and first['qualified_for_research'] is False
