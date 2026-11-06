"""Controller fault controls; simulated Docker replies are not native evidence."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

from vati_forecast_worker.policy import WorkerBudget

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('forecast_source_supervisor',ROOT/'tools/rebuild/run_forecast_runtime_smoke.py')
controller=importlib.util.module_from_spec(spec);spec.loader.exec_module(controller)


def fixture(tmp_path):
    source=tmp_path/'source';source.mkdir()
    return controller.DockerFixture('sha256:'+'1'*64,source,tmp_path/'output','RESEARCH_FIXTURE_SMOKE',WorkerBudget())


def test_unknown_creation_keeps_original_identity_and_never_creates_again(tmp_path,monkeypatch):
    worker=fixture(tmp_path);calls=[]
    def call(args,**kwargs):
        calls.append(args)
        if args[0]=='image':return subprocess.CompletedProcess(args,0,json.dumps([{'Size':0}]),'')
        if args[0]=='create':raise subprocess.TimeoutExpired('docker create',600)
        raise AssertionError(args)
    monkeypatch.setattr(worker,'call',call);monkeypatch.setattr(worker,'inspect',lambda:None)
    with pytest.raises(RuntimeError,match='CONTAINER_CREATE_UNKNOWN'):worker.execute()
    intent=json.loads((tmp_path/'research_fixture_smoke-intent.json').read_text())
    receipt=json.loads((tmp_path/'research_fixture_smoke-supervisor.json').read_text())
    assert receipt['container']==intent['container']==worker.name
    assert receipt['status']=='CREATE_UNKNOWN_RECONCILE_ORIGINAL_NAME' and receipt['removed'] is False
    assert sum(args[0]=='create' for args in calls)==1
    with pytest.raises(RuntimeError,match='CLEANUP_NOT_CONFIRMED'):controller.require_completed_worker(receipt)


def test_cleanup_failure_retains_receipt_and_original_execution_failure(tmp_path,monkeypatch):
    worker=fixture(tmp_path)
    def call(args,**kwargs):
        if args[0]=='image':return subprocess.CompletedProcess(args,0,json.dumps([{'Size':0}]),'')
        if args[0]=='create':raise subprocess.TimeoutExpired('docker create',600)
        if args[0]=='rm':raise subprocess.TimeoutExpired('docker rm',180)
        raise AssertionError(args)
    monkeypatch.setattr(worker,'call',call)
    monkeypatch.setattr(worker,'inspect',lambda:{'State':{'Status':'removing'}})
    with pytest.raises(RuntimeError,match='CONTAINER_CREATE_STATE_UNKNOWN'):worker.execute()
    receipt=json.loads((tmp_path/'research_fixture_smoke-supervisor.json').read_text())
    assert receipt['container']==worker.name and receipt['removed'] is False
    assert receipt['cleanup_error_type']=='TimeoutExpired'
    with pytest.raises(RuntimeError,match='CLEANUP_NOT_CONFIRMED'):controller.require_completed_worker(receipt)


@pytest.mark.parametrize('damage',['changed','missing','symlink'])
def test_changed_source_snapshot_refuses_success(tmp_path,damage):
    original=tmp_path/'source.py';original.write_bytes(b'original')
    hashes={'source.py':hashlib.sha256(b'original').hexdigest()}
    controller.require_unchanged_snapshot(tmp_path,hashes)
    if damage=='changed':original.write_bytes(b'changed')
    elif damage=='missing':original.unlink()
    else:
        original.unlink();target=tmp_path/'target.py';target.write_bytes(b'original');original.symlink_to(target)
    with pytest.raises(RuntimeError,match='SOURCE_SNAPSHOT_CHANGED'):controller.require_unchanged_snapshot(tmp_path,hashes)


def test_controller_does_not_forward_host_environment_to_model(tmp_path,monkeypatch):
    monkeypatch.setenv('OWNER_PRIVATE_TOKEN','synthetic-sensitive-value')
    monkeypatch.setenv('DOCKER_HOST','tcp://unintended.example:2375')
    worker=fixture(tmp_path)
    assert worker.docker==['docker','--host=unix:///var/run/docker.sock']
    assert 'DOCKER_HOST' not in worker.env
    assert 'OWNER_PRIVATE_TOKEN' not in controller.fixture_environment(worker.role)
    assert 'synthetic-sensitive-value' not in json.dumps(controller.fixture_environment(worker.role))
