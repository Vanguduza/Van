"""Fixture preflight is not model admission; unsafe legacy bytes never reach a loader."""
import hashlib
import json
from pathlib import Path

import pytest

from vati_forecast_worker.artifacts import MODEL_FILES,MODEL_ROWS,verified_fixture_bundle
from vati_forecast_worker.policy import WorkerBoundaryError,WorkerBudget


@pytest.fixture
def bundle(tmp_path):
    root=tmp_path/'bundle';root.mkdir()
    for name in MODEL_FILES:
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(b'{"nf_format":"2"}' if name.endswith('configuration.json') else b'preflight-fixture-not-native-weights')
    manifest={'format':'van.fixed-fixture-model-bundle/1','data_environment':'FIXTURE',
        'execution_authority':False,'economic_admission':False,'fixture_definition':'van.stack-fixture/1',
        'file_sha256':{name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in MODEL_FILES},
        'expected_predictions':{name:[.25]*count for name,count in MODEL_ROWS.items()}}
    (root/'fixture-models.json').write_text(json.dumps(manifest))
    return root,manifest


def write_manifest(root,manifest):
    (root/'fixture-models.json').write_text(json.dumps(manifest))


def test_loader_receives_verified_private_bytes_even_if_incoming_files_change(bundle):
    root,manifest=bundle;expected=(root/'xgboost.json').read_bytes()
    with verified_fixture_bundle(root) as (private,observed):
        (root/'xgboost.json').write_bytes(b'changed after verification')
        assert (private/'xgboost.json').read_bytes()==expected
        assert observed==manifest and private!=root
    assert not private.exists()


@pytest.mark.parametrize('change',[{'economic_admission':True},{'execution_authority':True},
    {'data_environment':'LIVE'},{'broker_credentials':'fixture-secret'},{'format':'unknown'}])
def test_fixture_metadata_cannot_self_issue_market_or_execution_permission(bundle,change):
    root,manifest=bundle;write_manifest(root,manifest | change)
    with pytest.raises(WorkerBoundaryError):
        with verified_fixture_bundle(root):pytest.fail('unadmitted fixture scope was accepted')


def test_legacy_pickle_is_rejected_without_executing_its_payload(bundle,tmp_path):
    import pickle
    root,manifest=bundle;marker=tmp_path/'executed'
    class Poison:
        def __reduce__(self):return (Path.write_text,(marker,'executed'))
    (root/'neuralforecast/dataset.pkl').write_bytes(pickle.dumps(Poison()))
    with pytest.raises(WorkerBoundaryError,match='UNSUPPORTED'):
        with verified_fixture_bundle(root):pytest.fail('legacy pickle entered loader')
    assert not marker.exists()


def test_hash_mismatch_and_symlink_refuse_before_native_loading(bundle,tmp_path):
    root,manifest=bundle;original=(root/'xgboost.json').read_bytes()
    (root/'xgboost.json').write_bytes(b'corrupt')
    with pytest.raises(WorkerBoundaryError,match='HASH_MISMATCH'):
        with verified_fixture_bundle(root):pass
    other=tmp_path/'outside.json';other.write_bytes(original)
    (root/'xgboost.json').unlink();(root/'xgboost.json').symlink_to(other)
    with pytest.raises(WorkerBoundaryError,match='LINKED'):
        with verified_fixture_bundle(root):pass


def test_unknown_neuralforecast_format_does_not_fall_back_to_legacy_loading(bundle):
    root,manifest=bundle;path=root/'neuralforecast/configuration.json';path.write_text('{"nf_format":"1"}')
    manifest['file_sha256']['neuralforecast/configuration.json']=hashlib.sha256(path.read_bytes()).hexdigest()
    write_manifest(root,manifest)
    with pytest.raises(WorkerBoundaryError,match='UNSAFE_OR_UNKNOWN'):
        with verified_fixture_bundle(root):pass


def test_nonfinite_or_duplicate_manifest_keys_cannot_be_normalized_into_success(bundle):
    root,manifest=bundle;manifest['expected_predictions']['neuralforecast'][0]=float('nan');write_manifest(root,manifest)
    with pytest.raises(WorkerBoundaryError,match='NONFINITE'):
        with verified_fixture_bundle(root):pass
    (root/'fixture-models.json').write_text('{"format":"old","format":"new"}')
    with pytest.raises(WorkerBoundaryError,match='DUPLICATE'):
        with verified_fixture_bundle(root):pass


def test_manifest_and_aggregate_artifact_caps_are_checked_before_loading(bundle):
    root,manifest=bundle;(root/'fixture-models.json').write_bytes(b' '*65537)
    with pytest.raises(WorkerBoundaryError,match='MANIFEST_BYTE_LIMIT'):
        with verified_fixture_bundle(root):pass
    write_manifest(root,manifest);path=root/'xgboost.json';path.write_bytes(b'x'*2048)
    manifest['file_sha256']['xgboost.json']=hashlib.sha256(path.read_bytes()).hexdigest();write_manifest(root,manifest)
    with pytest.raises(WorkerBoundaryError,match='ARTIFACT_BYTE_LIMIT'):
        with verified_fixture_bundle(root,WorkerBudget(artifact_bytes=1024)):pass
