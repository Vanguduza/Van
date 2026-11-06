from pathlib import Path
import os,subprocess,json,time,ctypes

assert ctypes.CDLL(None,use_errno=True).prctl(36,1,0,0,0)==0
root=Path('/workspace/van-ml004-bootstrap-20261026')
env=dict(os.environ)
for k in ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH'):env.pop(k,None)
docker=['docker','--host=unix:///var/run/docker.sock']
name='van-ml004-import-probe-20261026';label='ml004-import-probe-20261026'
receipt={'status':'RUNNING','container':name,'image_id':'sha256:d329d19854d7c1f414def27e5d681f050562cd32a506e56e274171b65d9124e1','created':False,'removed':False}
def call(args):return subprocess.run(docker+args,env=env,text=True,capture_output=True,check=True,timeout=180)
code=1
try:
    existing=json.loads(call(['inspect',name]).stdout)[0]
    assert existing['Id']=='2268273d00889c267c493fe0e637b43c58db50359830b2f4e3706d2e3b71bc71'
    assert existing['Config']['Labels'].get('van.task')==label
    assert existing['Image']==receipt['image_id'] and existing['State']['Status']=='created'
    receipt['created']=True;receipt['reused_reconciled_container']=existing['Id']
    with (root/'import-probe-r2.log').open('wb') as log:
        process=subprocess.Popen(docker+['start','--attach',name],env=env,stdout=log,stderr=subprocess.STDOUT)
        try:code=process.wait(timeout=120)
        except subprocess.TimeoutExpired:
            receipt['timeout_seconds']=120;call(['stop','--time','5',name]);code=process.wait(timeout=15)
    observed=json.loads(call(['inspect',name]).stdout)[0]
    receipt.update(exit=code,state=observed['State'],enforced_configuration={
        k:observed['HostConfig'].get(k) for k in ('Memory','NanoCpus','PidsLimit','ReadonlyRootfs','NetworkMode','CapDrop','SecurityOpt')})
    assert observed['Config']['Labels']['van.task']==label
    receipt['status']='IMPORT_EXIT_ZERO_PENDING_CGROUP_RECONCILIATION' if code==0 else 'FAILED_IMPORT_PROBE'
finally:
    if receipt['created']:
        observed=json.loads(call(['inspect',name]).stdout)[0]
        assert observed['Config']['Labels']['van.task']==label
        call(['rm','--force',name]);receipt['removed']=True
    adopted=[]
    for _ in range(100):
        try:
            pid,status=os.waitpid(-1,os.WNOHANG)
            if pid:adopted.append({'pid':pid,'status':status});continue
            time.sleep(.05)
        except ChildProcessError:break
    receipt['owned_adopted_children_reaped']=adopted
    (root/'import-probe-r2-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({k:receipt.get(k) for k in ('status','exit','removed','timeout_seconds')}),flush=True)
raise SystemExit(code)
