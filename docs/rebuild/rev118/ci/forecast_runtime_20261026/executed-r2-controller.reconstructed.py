#!/usr/bin/env python3
"""Run fixed synthetic research and cold inference in separate offline containers.

No general training job, market dataset, broker credential, deployment binding or
native/economic admission is accepted by this source-test harness.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'trading'))
from vati_forecast_worker.policy import WorkerBudget,fixture_environment
from vati_forecast_worker.artifacts import verified_fixture_bundle


def source_snapshot(destination):
    source=ROOT/'trading/vati_forecast_worker';destination.mkdir(parents=True)
    hashes={}
    for path in sorted(source.rglob('*')):
        relative=path.relative_to(source)
        if (not path.is_file() or path.is_symlink() or '__pycache__' in relative.parts
                or path.suffix not in {'.py','.json','.lock'}):continue
        target=destination/relative;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(path,target);hashes[str(relative)]=hashlib.sha256(target.read_bytes()).hexdigest()
    return hashes


class DockerFixture:
    def __init__(self,image,source,output,role,budget):
        if re.fullmatch('sha256:[a-f0-9]{64}',image) is None:raise ValueError('IMMUTABLE_LOCAL_IMAGE_ID_REQUIRED')
        self.image=image;self.source=source;self.output=output;self.role=role;self.budget=budget
        self.name='van-ml004-'+uuid.uuid4().hex;self.created=False
        self.env=dict(os.environ)
        for key in ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH'):
            self.env.pop(key,None)
        self.docker=['docker','--host=unix:///var/run/docker.sock']
        self.receipt={'container':self.name,'image_id':image,'role':role,'status':'NOT_STARTED','removed':False}

    def call(self,args,*,timeout=30,check=True):
        return subprocess.run(self.docker+args,env=self.env,text=True,capture_output=True,timeout=timeout,check=check)

    def inspect(self):
        response=self.call(['inspect',self.name],check=False)
        if response.returncode:
            if 'No such' in response.stderr:return None
            raise RuntimeError('TASK_CONTAINER_READBACK_UNAVAILABLE')
        value=json.loads(response.stdout)[0]
        if value['Config']['Labels'].get('van.ml004.run')!=self.name or value['Image']!=self.image:
            raise RuntimeError('TASK_CONTAINER_IDENTITY_CONFLICT')
        return value

    def stop(self):
        current=self.inspect()
        if current is not None and current['State']['Running']:
            self.call(['stop','--time','5',self.name])

    def execute(self,*,input_artifacts=None):
        self.output.mkdir(mode=0o700)
        image=json.loads(self.call(['image','inspect',self.image]).stdout)[0]
        if shutil.disk_usage(self.output).free<image['Size']+2*1024**3:
            raise RuntimeError('LOCAL_IMAGE_COPY_DISK_RESERVE_UNAVAILABLE')
        args=['create','--name',self.name,'--label','van.ml004.run='+self.name,
            '--network','none','--init','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',
            '--user',str(os.getuid())+':'+str(os.getgid()),'--pids-limit',str(self.budget.pids),
            '--cpus',str(self.budget.cpu_millis/1000),'--memory',str(self.budget.memory_bytes),
            '--tmpfs','/tmp:rw,nosuid,nodev,size=512m,mode=1777','--workdir','/work',
            '--mount','type=bind,source='+str(self.source)+',target=/opt/van/vati_forecast_worker,readonly',
            '--mount','type=bind,source='+str(self.output)+',target=/work']
        if input_artifacts is not None:
            args+=['--mount','type=bind,source='+str(input_artifacts)+',target=/artifacts,readonly']
        for name,value in fixture_environment(self.role).items():args+=['--env',name+'='+value]
        module='smoke' if self.role=='RESEARCH_FIXTURE_SMOKE' else 'inference_smoke'
        args+=[self.image,'python','-m','vati_forecast_worker.'+module]
        self.receipt['status']='CREATE_REQUESTED'
        (self.output.parent/(self.role.lower()+'-intent.json')).write_text(json.dumps(self.receipt,indent=2)+'\n')
        creation_started=time.monotonic()
        try:
            try:self.call(args,timeout=600)
            except subprocess.TimeoutExpired:
                # Server-side creation can outlive its client. Reuse only its
                # original, independently observed stopped identity.
                current=self.inspect()
                if current is None:
                    self.receipt['status']='CREATE_UNKNOWN_RECONCILE_ORIGINAL_NAME'
                    raise RuntimeError('CONTAINER_CREATE_UNKNOWN')
                self.created=True;self.receipt['create_reply']='TIMED_OUT_RECONCILED'
                if current['State']['Status']!='created':raise RuntimeError('CONTAINER_CREATE_STATE_UNKNOWN')
            self.created=True
            current=self.inspect()
            if current is None or current['State']['Status']!='created':raise RuntimeError('CONTAINER_CREATE_READBACK_FAILED')
            self.receipt['container_id']=current['Id'];self.receipt['status']='RUNNING'
            self.receipt['creation_seconds']=time.monotonic()-creation_started
            process=subprocess.Popen(self.docker+['start','--attach',self.name],env=self.env,
                stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
            selector=selectors.DefaultSelector();selector.register(process.stdout,selectors.EVENT_READ)
            used=0;deadline=time.monotonic()+self.budget.runtime_seconds;limit_reason=None
            try:
                with (self.output.parent/(self.role.lower()+'.log')).open('wb') as log:
                    while selector.get_map():
                        if time.monotonic()>=deadline:
                            limit_reason='WALL_TIME_LIMIT';self.stop();deadline=float('inf')
                        for key,_mask in selector.select(timeout=1):
                            chunk=os.read(key.fd,65536)
                            if not chunk:selector.unregister(key.fileobj);continue
                            remaining=max(0,self.budget.log_bytes-used)
                            if remaining:log.write(chunk[:remaining])
                            used+=len(chunk)
                            if used>self.budget.log_bytes and limit_reason is None:
                                limit_reason='LOG_BYTE_LIMIT';self.stop()
                    code=process.wait(timeout=15)
            finally:
                selector.close();process.stdout.close()
                if process.poll() is None:
                    self.stop();process.terminate()
                    try:process.wait(timeout=10)
                    except subprocess.TimeoutExpired:process.kill();process.wait(timeout=10)
            current=self.inspect()
            if current is None:raise RuntimeError('CONTAINER_FINAL_READBACK_UNAVAILABLE')
            self.receipt.update(exit=code,container_exit=current['State']['ExitCode'],
                oom_killed=current['State']['OOMKilled'],limit_reason=limit_reason,
                declared_kernel_configuration={name:current['HostConfig'].get(name) for name in
                    ('NanoCpus','Memory','PidsLimit','ReadonlyRootfs','NetworkMode','Init')})
            if code or current['State']['ExitCode'] or current['State']['OOMKilled'] or limit_reason:
                raise RuntimeError('SOURCE_WORKER_EXECUTION_FAILED')
            self.receipt['status']='EXECUTED_PENDING_REPORT_RECONCILIATION'
            return dict(self.receipt)
        finally:
            if self.created:
                current=self.inspect()
                if current is not None:self.call(['rm','--force',self.name],timeout=180)
                self.receipt['removed']=self.inspect() is None
            (self.output.parent/(self.role.lower()+'-supervisor.json')).write_text(json.dumps(self.receipt,indent=2)+'\n')


def run(image,output):
    output=Path(output).resolve();output.mkdir(mode=0o700,parents=False,exist_ok=False)
    assert ctypes.CDLL(None,use_errno=True).prctl(36,1,0,0,0)==0
    snapshot=output/'source'/'vati_forecast_worker';hashes=source_snapshot(snapshot)
    budget=WorkerBudget();research=DockerFixture(image,snapshot,output/'research','RESEARCH_FIXTURE_SMOKE',budget)
    inference=None;receipt={'schema':'van.ml004.two-process-environments-source/1',
        'status':'RUNNING','data_environment':'FIXTURE','economic_evidence':False,'execution_authority':False,
        'image_id':image,'source_sha256':hashes,'controller_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'output':str(output)}
    try:
        research.execute()
        actual=json.loads((output/'research/train-probe-receipt.json').read_text())
        if (actual['status']!='SOURCE_FIXTURE_SMOKE_PASS_NOT_UNIT_QUALIFICATION' or actual['unexecuted']
                or len(actual['cases'])!=6 or any(case['status']!='PASS' for case in actual['cases'])):
            raise RuntimeError('RESEARCH_CASES_NOT_ALL_EXECUTED_PASS')
        with verified_fixture_bundle(output/'research/model-bundle'):pass
        research.receipt['status']='SOURCE_REPORT_VERIFIED_NOT_ADMISSION'
        inference=DockerFixture(image,snapshot,output/'inference','INFERENCE_FIXTURE_SMOKE',budget)
        inference.execute(input_artifacts=output/'research/model-bundle')
        cold=json.loads((output/'inference/inference-receipt.json').read_text())
        if (cold['status']!='SOURCE_FIXTURE_INFERENCE_PASS' or cold['training_executed'] is not False
                or cold['execution_authority'] is not False or cold['economic_evidence'] is not False
                or cold['model_rows']!={'qlib_lightgbm':10,'xgboost':10,'neuralforecast':2}
                or any(error>1e-6 for error in cold['max_abs_reload_errors'].values())):
            raise RuntimeError('COLD_INFERENCE_PARITY_NOT_CONFIRMED')
        inference.receipt['status']='SOURCE_REPORT_VERIFIED_NOT_ADMISSION'
        receipt.update(status='SOURCE_FIXTURE_RESEARCH_AND_COLD_INFERENCE_PASS_NOT_ADMISSION',
            research_report_sha256=hashlib.sha256((output/'research/train-probe-receipt.json').read_bytes()).hexdigest(),
            inference_report_sha256=hashlib.sha256((output/'inference/inference-receipt.json').read_bytes()).hexdigest())
        return 0
    finally:
        receipt['research']=research.receipt
        if inference is not None:receipt['inference']=inference.receipt
        if receipt['status']=='RUNNING':receipt['status']='FAILED_OR_INCOMPLETE_SOURCE_PROBE'
        receipt['source_snapshot_unchanged']=all(hashlib.sha256((snapshot/path).read_bytes()).hexdigest()==digest for path,digest in hashes.items())
        adopted=[]
        for _ in range(100):
            try:
                pid,status=os.waitpid(-1,os.WNOHANG)
                if pid:adopted.append({'pid':pid,'status':status});continue
                time.sleep(.01)
            except ChildProcessError:break
        receipt['owned_adopted_children_reaped']=adopted
        (output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',required=True,help='Exact already-built local image ID, sha256:...')
    parser.add_argument('--output',required=True,help='New private source-test output directory')
    args=parser.parse_args()
    return run(args.image,args.output)


if __name__=='__main__':raise SystemExit(main())
