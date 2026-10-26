"""Reconcile and start the original unstarted fixture container exactly once."""
from pathlib import Path
import os,json,subprocess,time,ctypes,hashlib

assert ctypes.CDLL(None,use_errno=True).prctl(36,1,0,0,0)==0
root=Path('/workspace/van-ml004-active-source-r1-20261026')
original=json.loads((root/'inference_fixture_smoke-supervisor.json').read_text())
name=original['container'];image=original['image_id'];env=dict(os.environ)
for key in ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH'):env.pop(key,None)
docker=['docker','--host=unix:///var/run/docker.sock']
def call(args):return subprocess.run(docker+args,env=env,text=True,capture_output=True,check=True,timeout=180)
def inspect():
    observed=json.loads(call(['inspect',name]).stdout)[0]
    assert observed['Config']['Labels'].get('van.ml004.run')==name and observed['Image']==image
    assert observed['Id']=='45f6cb54a1e1f9fa20ef5a18081d38411268dc37e21d91dde0502152d0dcabdd'
    return observed
receipt={'schema':'van.ml004.unknown-create-reconciliation/1','original_name':name,
    'original_status':original['status'],'status':'RECONCILED_CREATED_PENDING_START','removed':False}
code=1
try:
    observed=inspect();assert observed['State']['Status']=='created' and observed['State']['Pid']==0
    receipt['before_start']=observed['State']
    with (root/'inference_fixture_smoke-resume.log').open('wb') as log:
        process=subprocess.Popen(docker+['start','--attach',name],env=env,stdout=log,stderr=subprocess.STDOUT)
        try:code=process.wait(timeout=300)
        except subprocess.TimeoutExpired:
            receipt['timeout_seconds']=300;inspect();call(['stop','--time','5',name]);code=process.wait(timeout=15)
    observed=inspect();receipt.update(exit=code,state=observed['State'])
    if code==0:
        record=json.loads((root/'inference/inference-receipt.json').read_text())
        assert record['training_executed'] is False and record['execution_authority'] is False
        assert record['model_rows']=={'qlib_lightgbm':10,'xgboost':10,'neuralforecast':2}
        assert all(error<=1e-6 for error in record['max_abs_reload_errors'].values())
        receipt['report_sha256']=hashlib.sha256((root/'inference/inference-receipt.json').read_bytes()).hexdigest()
        receipt['status']='RECONCILED_ORIGINAL_COLD_INFERENCE_PASS_NOT_ADMISSION'
    else:receipt['status']='RECONCILED_ORIGINAL_INFERENCE_FAILED'
finally:
    inspect();call(['rm','--force',name]);receipt['removed']=True
    adopted=[]
    for _ in range(100):
        try:
            pid,status=os.waitpid(-1,os.WNOHANG)
            if pid:adopted.append({'pid':pid,'status':status});continue
            time.sleep(.01)
        except ChildProcessError:break
    receipt['owned_adopted_children_reaped']=adopted
    (root/'inference-resume-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({k:receipt.get(k) for k in ('status','exit','removed')}),flush=True)
raise SystemExit(code)
