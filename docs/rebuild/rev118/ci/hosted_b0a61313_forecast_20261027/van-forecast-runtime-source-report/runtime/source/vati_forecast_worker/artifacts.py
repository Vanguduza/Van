"""Bounded fixed-fixture artifacts; never an admitted production model manifest."""
from contextlib import contextmanager
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import tempfile

from vati_forecast_worker.policy import WorkerBoundaryError,WorkerBudget

MODEL_FILES=frozenset({'qlib-lightgbm.txt','xgboost.json',
    'neuralforecast/NHITS_0.safetensors','neuralforecast/configuration.json'})
MODEL_ROWS={'qlib_lightgbm':10,'xgboost':10,'neuralforecast':2}


def _strict_json(raw):
    def pairs(values):
        result={}
        for key,value in values:
            if key in result:raise WorkerBoundaryError('ARTIFACT_DUPLICATE_JSON_KEY')
            result[key]=value
        return result
    def bad_constant(_value):raise WorkerBoundaryError('ARTIFACT_NONFINITE_JSON_NUMBER')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=bad_constant)


def write_fixture_bundle(work_root,cases):
    work_root=Path(work_root);target=work_root/'model-bundle';target.mkdir(mode=0o700)
    expected={case['case']:case['detail']['expected_predictions'] for case in cases if case['case'] in MODEL_ROWS}
    assert set(expected)==set(MODEL_ROWS)
    files={}
    for name in sorted(MODEL_FILES):
        source=work_root/name
        if source.is_symlink() or not source.is_file():raise WorkerBoundaryError('FIXTURE_MODEL_ARTIFACT_UNAVAILABLE')
        destination=target/name;destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,destination);files[name]=hashlib.sha256(destination.read_bytes()).hexdigest()
    manifest={'format':'van.fixed-fixture-model-bundle/1','data_environment':'FIXTURE',
        'execution_authority':False,'economic_admission':False,'fixture_definition':'van.stack-fixture/1',
        'file_sha256':files,'expected_predictions':expected}
    (target/'fixture-models.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n')
    # Exercise the same bounded reader used by the separate inference process.
    with verified_fixture_bundle(target):pass
    return {'bundle_manifest_sha256':hashlib.sha256((target/'fixture-models.json').read_bytes()).hexdigest(),
            'data_environment':'FIXTURE','execution_authority':False,'economic_admission':False}


@contextmanager
def verified_fixture_bundle(root,budget=None):
    root=Path(root);budget=budget or WorkerBudget()
    manifest_path=root/'fixture-models.json'
    if root.is_symlink() or manifest_path.is_symlink() or not manifest_path.is_file():
        raise WorkerBoundaryError('FIXTURE_BUNDLE_UNAVAILABLE')
    with manifest_path.open('rb') as stream:raw=stream.read(64*1024+1)
    if len(raw)>64*1024:raise WorkerBoundaryError('FIXTURE_MANIFEST_BYTE_LIMIT')
    manifest=_strict_json(raw)
    keys={'format','data_environment','execution_authority','economic_admission','fixture_definition',
          'file_sha256','expected_predictions'}
    if (not isinstance(manifest,dict) or set(manifest)!=keys
            or manifest['format']!='van.fixed-fixture-model-bundle/1'
            or manifest['data_environment']!='FIXTURE' or manifest['execution_authority'] is not False
            or manifest['economic_admission'] is not False or manifest['fixture_definition']!='van.stack-fixture/1'
            or not isinstance(manifest['file_sha256'],dict) or set(manifest['file_sha256'])!=MODEL_FILES
            or not isinstance(manifest['expected_predictions'],dict) or set(manifest['expected_predictions'])!=set(MODEL_ROWS)):
        raise WorkerBoundaryError('UNADMITTED_FIXTURE_ARTIFACT_SCOPE_OR_FORMAT')
    for name,count in MODEL_ROWS.items():
        vector=manifest['expected_predictions'][name]
        if (not isinstance(vector,list) or len(vector)!=count
                or any(type(value) not in (int,float) or not math.isfinite(value) for value in vector)):
            raise WorkerBoundaryError('FIXTURE_PREDICTION_VECTOR_INVALID')
    present={str(path.relative_to(root)) for path in root.rglob('*') if path.is_file()}
    if present!=MODEL_FILES|{'fixture-models.json'} or any(path.is_symlink() for path in root.rglob('*')):
        raise WorkerBoundaryError('UNSUPPORTED_OR_LINKED_ARTIFACT_FILE')
    total=0;verified={}
    for name in sorted(MODEL_FILES):
        expected=manifest['file_sha256'][name]
        if not isinstance(expected,str) or re.fullmatch('[a-f0-9]{64}',expected) is None:
            raise WorkerBoundaryError('ARTIFACT_HASH_INVALID')
        with (root/name).open('rb') as stream:data=stream.read(budget.artifact_bytes-total+1)
        total+=len(data)
        if total>budget.artifact_bytes:raise WorkerBoundaryError('MODEL_ARTIFACT_BYTE_LIMIT')
        if hashlib.sha256(data).hexdigest()!=expected:raise WorkerBoundaryError('MODEL_ARTIFACT_HASH_MISMATCH')
        verified[name]=data
    configuration=_strict_json(verified['neuralforecast/configuration.json'])
    if not isinstance(configuration,dict) or configuration.get('nf_format')!='2':
        raise WorkerBoundaryError('NEURALFORECAST_UNSAFE_OR_UNKNOWN_FORMAT')
    # Native loaders receive these verified private bytes, never a second read
    # of a mutable incoming directory or a remote model URI.
    with tempfile.TemporaryDirectory(prefix='van-verified-fixture-') as temporary:
        directory=Path(temporary)
        for name,data in verified.items():
            path=directory/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        yield directory,manifest
