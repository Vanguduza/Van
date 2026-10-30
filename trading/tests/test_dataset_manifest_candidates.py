"""Contract candidates with unresolved fixture IDs are never market evidence."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import os
import sys

import pytest

from vati.contracts import load_schema
from vati.research.dataset_manifest import DatasetContractError, DatasetManifestCandidate, MAX_MANIFEST_BYTES


def fixture():
    return {'schema_version':'van-ml/1.0', 'record_id':'fixture-dataset-unresolved', 'authority_effect':'NONE',
        'scope':{'project_id':'fixture-project', 'cohort_id':'fixture-cohort', 'instrument_id':'fixture-instrument',
                 'venue_id':'fixture-venue', 'environment':'FIXTURE'},
        'created_at':'2020-01-02T00:00:00Z', 'data_cutoff':'2020-01-01T00:00:00Z',
        'max_input_available_at':'2020-01-01T00:00:00Z', 'availability_quality':'OBSERVED',
        **{name: 'a'*64 for name in ('universe_digest','calendar_digest','source_manifest_digest',
                                    'row_identity_digest','feature_definition_digest')},
        'row_count':3, 'target_spec_ids':['fixture-target-unresolved'], 'entitlement_refs':['fixture-rights-unresolved'],
        'consent_scope_ref':'fixture-consent-unresolved', 'revision_policy':'AS_OBSERVED',
        'partitions':[{'artifact_id':'fixture-artifact-unresolved', 'sha256':'b'*64,
                       'media_type':'application/vnd.apache.parquet', 'size_bytes':100}]}


def parse(record):
    return DatasetManifestCandidate(json.dumps(record).encode())


def test_registered_schema_is_exact_frozen_wire_contract():
    original=Path(__file__).resolve().parents[2]/'docs/review-inputs/van-rev115/package/contracts/forecast/DatasetManifest.schema.json'
    assert load_schema('dataset_manifest') == json.loads(original.read_bytes())


def test_well_formed_manifest_stays_unresolved_and_mutation_cannot_rewrite_candidate():
    record=fixture(); candidate=parse(record); before=candidate.digest
    assert candidate.body() == record
    result=candidate.unresolved()
    assert result['status']=='UNRESOLVED_DATASET_CANDIDATE' and result['qualified_for_research'] is False
    assert result['authority_effect']=='NONE' and len(result['reason_codes'])==3
    refs=result['required_resolutions']
    assert refs['entitlement_refs']==record['entitlement_refs']
    assert refs['artifact_ids']==['fixture-artifact-unresolved']
    result['scope']['environment']='LIVE_ADVISORY'; record['scope']['project_id']='changed'
    assert candidate.digest==before and candidate.body()['scope']['environment']=='FIXTURE'
    assert candidate.body()['scope']['project_id']=='fixture-project'


@pytest.mark.parametrize('change', ['field','scope','partition','schema','authority','bool_count','bool_size','digest',
    'duplicate_target','duplicate_entitlement','duplicate_partition','missing_target','empty_partitions','size_overflow'])
def test_malformed_or_ambiguous_manifest_is_refused(change):
    record=fixture()
    if change=='field': record['ready']=True
    elif change=='scope': record['scope']['account_alias']='unbound'
    elif change=='partition': record['partitions'][0]['path']='/tmp/untrusted'
    elif change=='schema': record['schema_version']='van-ml/future'
    elif change=='authority': record['authority_effect']='ORDER'
    elif change=='bool_count': record['row_count']=True
    elif change=='bool_size': record['partitions'][0]['size_bytes']=True
    elif change=='digest': record['row_identity_digest']='A'*64
    elif change=='duplicate_target': record['target_spec_ids']*=2
    elif change=='duplicate_entitlement': record['entitlement_refs']*=2
    elif change=='duplicate_partition': record['partitions']*=2
    elif change=='missing_target': record['target_spec_ids']=[]
    elif change=='empty_partitions': record['partitions']=[]
    elif change=='size_overflow':
        record['partitions'][0]['size_bytes']=2**63-1
        record['partitions'].append(dict(record['partitions'][0], artifact_id='different-fixture-id'))
    with pytest.raises(DatasetContractError): parse(record)


@pytest.mark.parametrize('stamp', ['2020-01-01', '2020-01-01T00:00:00', '2020-01-01T00:00:00-00:00',
    '2020-01-01T00:00:00+00:90', '2020-02-30T00:00:00Z', '2020-01-01T00:00:60Z'])
def test_unknown_invalid_or_unsupported_clock_never_gets_utc_by_assumption(stamp):
    record=fixture(); record['max_input_available_at']=stamp
    with pytest.raises(DatasetContractError): parse(record)


@pytest.mark.parametrize('field', ['max_input_available_at','data_cutoff'])
def test_temporal_order_compares_exact_nanoseconds(field):
    record=fixture()
    record['max_input_available_at']=record['data_cutoff']=record['created_at']='2020-01-01T00:00:00.000000001Z'
    record[field]='2020-01-01T00:00:00.000000002Z'
    with pytest.raises(DatasetContractError,match='TEMPORAL_ORDER'): parse(record)


def test_equivalent_offset_and_subsecond_representations_compare_actual_instants_without_rounding():
    record=fixture(); record['max_input_available_at']='2020-01-01T01:00:00.000000001+01:00'
    record['data_cutoff']='2020-01-01T00:00:00.0000000010Z'
    record['created_at']='2020-01-01T00:00:00.0000000011Z'
    assert parse(record).body()==record


@pytest.mark.parametrize('digits',['٠٠١','００１'])
def test_rfc3339_fraction_is_ascii_even_when_python_integer_parser_accepts_unicode_digits(digits):
    record=fixture()
    for field in ('max_input_available_at','data_cutoff','created_at'):
        record[field]='2020-01-01T00:00:00.'+digits+'Z'
    with pytest.raises(DatasetContractError): parse(record)


@pytest.mark.parametrize('environment', ['SHADOW','LIVE_ADVISORY'])
def test_corrected_research_cannot_be_presented_as_as_observed_advisory(environment):
    record=fixture(); record['scope']['environment']=environment; record['revision_policy']='CORRECTED_RESEARCH_ONLY'
    with pytest.raises(DatasetContractError,match='CORRECTED_RESEARCH'): parse(record)


@pytest.mark.parametrize('raw', [b'{"scope":{},"scope":{}}', b'{"row_count":NaN}', b'{"row_count":Infinity}',
    b'\xff', b'[]', b'x'*(MAX_MANIFEST_BYTES+1)],
    ids=['duplicate-key','nan','infinity','invalid-utf8','wrong-shape','over-byte-capacity'])
def test_raw_byte_boundary_refuses_duplicate_keys_nonfinite_invalid_and_oversize_input(raw):
    with pytest.raises(DatasetContractError): DatasetManifestCandidate(raw)


def test_actual_research_cli_reports_unresolved_refs_and_never_ready(tmp_path):
    spec=tmp_path/'manifest.json';spec.write_text(json.dumps({'operation':'dataset_manifest_check','manifest':fixture()}))
    child=subprocess.run([sys.executable,'-m','vati','research','--spec',str(spec)],
        env=dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parents[1])),capture_output=True,text=True,timeout=30)
    assert child.returncode==0,child.stderr
    report=json.loads(child.stdout)['candidate']
    assert report['status']=='UNRESOLVED_DATASET_CANDIDATE' and report['qualified_for_research'] is False
    assert 'CURRENT_SCOPE_CONSENT_AND_SOURCE_USE_NOT_VERIFIED' in report['reason_codes']


@pytest.mark.parametrize('operation',['dataset_manifest_check','dataset_source_inspect'])
def test_actual_research_cli_refuses_nested_duplicate_keys_before_any_reference_resolution(tmp_path,operation):
    spec_body={'operation':operation,'manifest':fixture()}
    if operation=='dataset_source_inspect':
        spec_body['expected_scope']={'provider':'CTRADER','environment':'DEMO','transport_host':'demo.ctraderapi.com',
            'native_account_id':123,'native_symbol_id':12}
    raw=json.dumps(spec_body)
    assert raw.count('"row_count": 3')==1
    raw=raw.replace('"row_count": 3','"row_count": 3, "row_count": 4')
    spec=tmp_path/'ambiguous.json';spec.write_text(raw)
    child=subprocess.run([sys.executable,'-m','vati','research','--spec',str(spec)],
        env=dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parents[1])),capture_output=True,text=True,timeout=30)
    assert child.returncode!=0 and 'RESEARCH_DUPLICATE_JSON_KEY' in child.stderr
    assert 'UNRESOLVED_DATASET_CANDIDATE' not in child.stdout
