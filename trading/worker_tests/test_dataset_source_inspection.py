"""Resolve real source-owner bytes; all fixture permissions remain unverified."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from test_forecast_source_partitions import source
from test_dataset_manifest_candidates import fixture, parse
from test_native_bar_windows import capture
from vati.core.canonical import canonical_hash
from vati.market_data.native_windows import NativeBarWindowReader
from vati.research.bar_partitions import NativeBarPartitionService
from vati.research.dataset_manifest import DatasetContractError
from vati.research.dataset_sources import NativeDatasetSourceInspector, DatasetInspectionBudget
from vati_forecast_worker.source_partitions import projected_rows


def binding(source, tmp_path, windows=None):
    book, contract, sample, window = source
    service=NativeBarPartitionService(NativeBarWindowReader(book),tmp_path/'derived')
    windows=windows or [window]
    receipts=[service.publish(w,expected_scope=contract.native_scope) for w in windows]
    record=fixture()
    record.update(created_at='1970-01-01T00:06:41Z', data_cutoff='1970-01-01T00:06:40Z',
        max_input_available_at='1970-01-01T00:06:40Z', source_manifest_digest=window['window_sha256'],
        row_count=sum(len(w['rows']) for w in windows),
        row_identity_digest=canonical_hash([r['row_id'] for w in windows for r in projected_rows(w)]),
        partitions=[{'artifact_id':r['publication_ref'],**{k:r[k] for k in ('sha256','media_type','size_bytes')}} for r in receipts])
    return service,record,contract


def test_actual_sources_resolve_without_conferring_any_dataset_or_market_permission(source,tmp_path):
    service,record,contract=binding(source,tmp_path)
    result=NativeDatasetSourceInspector(service).inspect(parse(record),expected_scope=contract.native_scope)
    facts=result['resolved_source_facts']
    assert facts['row_count']==3 and facts['row_identity_digest']==record['row_identity_digest']
    assert facts['source_manifest_resolved'] and facts['native_scope']==contract.native_scope
    assert facts['provider_qualified'] is facts['qualified_for_research'] is False
    assert result['status']=='UNRESOLVED_DATASET_CANDIDATE' and result['qualified_for_research'] is False
    assert 'CURRENT_SCOPE_CONSENT_AND_SOURCE_USE_NOT_VERIFIED' in result['reason_codes']
    assert 'CANONICAL_DATASET_SCOPE_AND_DATA_ORIGIN_NOT_VERIFIED' in result['reason_codes']


@pytest.mark.parametrize('damage',['missing','hash','size','media','rows','row_identity','source_digest',
    'cutoff','availability','quality','corrected','scope'])
def test_plausible_metadata_cannot_replace_actual_bytes_clocks_or_native_scope(source,tmp_path,damage):
    service,record,contract=binding(source,tmp_path)
    scope=contract.native_scope
    if damage=='missing':record['partitions'][0]['artifact_id']='f'*64
    elif damage=='hash':record['partitions'][0]['sha256']='f'*64
    elif damage=='size':record['partitions'][0]['size_bytes']+=1
    elif damage=='media':record['partitions'][0]['media_type']='text/csv'
    elif damage=='rows':record['row_count']=2
    elif damage=='row_identity':record['row_identity_digest']='f'*64
    elif damage=='source_digest':record['source_manifest_digest']='f'*64
    elif damage=='cutoff':record['data_cutoff']=record['max_input_available_at']='1970-01-01T00:06:39.999999999Z'
    elif damage=='availability':
        record['max_input_available_at']='1970-01-01T00:06:40.000000001Z'
        record['data_cutoff']='1970-01-01T00:06:41Z'
    elif damage=='quality':record['availability_quality']='RECONSTRUCTED'
    elif damage=='corrected':record['revision_policy']='CORRECTED_RESEARCH_ONLY'
    elif damage=='scope':scope=dict(scope,native_account_id=999)
    with pytest.raises(ValueError):NativeDatasetSourceInspector(service).inspect(parse(record),expected_scope=scope)


def test_independent_source_read_returns_private_immutable_bytes_and_fresh_metadata(source,tmp_path):
    service,record,contract=binding(source,tmp_path)
    original=service.read(record['partitions'][0]['artifact_id'],expected_scope=contract.native_scope)
    before=original.window_json
    changed=original.window();changed['rows'][0]['bar']['close']='999'
    changed=original.receipt();changed['qualified_for_research']=True
    assert original.window_json==before and original.receipt()['qualified_for_research'] is False
    assert original.parquet.startswith(b'PAR1')


def test_later_same_clock_source_correction_cannot_rewrite_resolved_dataset_candidate(source,tmp_path):
    service,record,contract=binding(source,tmp_path);inspector=NativeDatasetSourceInspector(service)
    before=inspector.inspect(parse(record),expected_scope=contract.native_scope)
    book,c,sample,window=source
    book.record('future-correction',c,replace(sample,bars=(replace(sample.bars[0],close=sample.bars[0].low),)))
    assert inspector.inspect(parse(record),expected_scope=contract.native_scope)==before


def test_disjoint_partitions_resolve_rows_but_cannot_invent_compound_source_manifest(source,tmp_path):
    book,c,sample,window=source
    first=NativeBarWindowReader(book).capture(c.native_scope,'M1',through_revision=1,boundary_ref=window['boundary_ref'],
        as_of_ms=400000,from_ms=120000,to_ms=180000)
    second=NativeBarWindowReader(book).capture(c.native_scope,'M1',through_revision=1,boundary_ref=window['boundary_ref'],
        as_of_ms=400000,from_ms=180000,to_ms=300000)
    service,record,c=binding(source,tmp_path,[first,second])
    result=NativeDatasetSourceInspector(service).inspect(parse(record),expected_scope=c.native_scope)
    assert result['resolved_source_facts']['row_count']==3
    assert result['resolved_source_facts']['source_manifest_resolved'] is False
    assert 'COMPOUND_SOURCE_MANIFEST_NOT_RESOLVED' in result['reason_codes']


def test_overlapping_revised_rows_are_not_silently_dropped_sorted_or_averaged(source,tmp_path):
    book,c,sample,window=source
    later=book.record('second-window',c,sample);second=capture(book,c,later)
    service,record,c=binding(source,tmp_path,[window,second])
    with pytest.raises(DatasetContractError,match='DUPLICATE_OR_UNORDERED'):
        NativeDatasetSourceInspector(service).inspect(parse(record),expected_scope=c.native_scope)


@pytest.mark.parametrize('budget',[DatasetInspectionBudget(rows=1),DatasetInspectionBudget(source_bytes=1)])
def test_declared_capacity_refuses_before_reading_native_artifacts(source,tmp_path,monkeypatch,budget):
    service,record,c=binding(source,tmp_path)
    monkeypatch.setattr(service,'read',lambda *a,**k:pytest.fail('artifact read before capacity refusal'))
    with pytest.raises(DatasetContractError,match='CAPACITY_REFUSED'):
        NativeDatasetSourceInspector(service,budget=budget).inspect(parse(record),expected_scope=c.native_scope)


def test_actual_cli_resolves_original_source_artifacts_and_retains_unknown_use_state(source,tmp_path):
    service,record,c=binding(source,tmp_path)
    spec=tmp_path/'inspect.json';spec.write_text(json.dumps({'operation':'dataset_source_inspect','manifest':record,
        'expected_scope':c.native_scope}))
    child=subprocess.run([sys.executable,'-m','vati','research','--spec',str(spec),'--native-archive',str(source[0].root),
        '--source-partitions',str(service.root)],env=dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parents[1])),
        capture_output=True,text=True,timeout=30)
    assert child.returncode==0,child.stderr
    report=json.loads(child.stdout)['candidate']
    assert report['resolved_source_facts']['row_count']==3 and report['qualified_for_research'] is False
    assert report['status']=='UNRESOLVED_DATASET_CANDIDATE'
