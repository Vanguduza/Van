import os,subprocess,pathlib,json,time,hashlib,ctypes
assert ctypes.CDLL(None,use_errno=True).prctl(36,1,0,0,0)==0
root=pathlib.Path('/workspace/van-review-2026-10-18/publish')
out=pathlib.Path('/workspace/van-ml004-pg-final-20261026');out.mkdir(exist_ok=True)
name='van-ml004-pg-final-20261026'
image='postgres:17.11-bookworm@sha256:858bb5e98eed02eb8cafbcdc007f9a65d1b613972028944a8ec2133ccaf80d27'
env=dict(os.environ)
for key in ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH'):env.pop(key,None)
docker=['docker','--host=unix:///var/run/docker.sock']
def run(args,**kwargs):return subprocess.run(args,env=env,check=True,text=True,capture_output=True,timeout=600,**kwargs)
created=False
receipt={'base_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'source_state':'UNCOMMITTED_FORECAST_RUNTIME_SOURCE','container':name,'image':image,'completed':False,'cleaned':False}
receipt['diagnostic_plugin_sha256']=hashlib.sha256(pathlib.Path('/workspace/van_pytest_live_diagnostics.py').read_bytes()).hexdigest()
receipt['source_sha256']={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for subroot in ('trading/vati','trading/tests','trading/vati_forecast_worker') for p in (root/subroot).rglob('*.py')}
try:
 cid=run(docker+['run','--detach','--init','--cpus','1','--memory','1073741824','--pids-limit','256','--name',name,'--label','van.task=forecast-runtime-source-20261026','--publish','127.0.0.1::5432','--tmpfs','/var/lib/postgresql/data:rw,nosuid,nodev,size=1024m','--env','POSTGRES_USER=van_fixture','--env','POSTGRES_PASSWORD=van_ephemeral_test_only',image]).stdout.strip();created=True;receipt['container_id']=cid
 for attempt in range(40):
  ready=subprocess.run(docker+['exec','--env','PGPASSWORD=van_ephemeral_test_only',name,'psql','--host=127.0.0.1','--username=van_fixture','--dbname=postgres','--no-psqlrc','--tuples-only','--no-align','--set=ON_ERROR_STOP=1','--command=SELECT 1'],env=env,text=True,capture_output=True,timeout=5)
  if ready.returncode==0 and ready.stdout.strip()=='1':break
  time.sleep(.5)
 else:raise RuntimeError('owned PostgreSQL fixture not ready')
 binding=json.loads(run(docker+['inspect',name]).stdout)[0]['NetworkSettings']['Ports']['5432/tcp'][0]
 assert binding['HostIp']=='127.0.0.1'
 run(docker+['exec','--env','PGPASSWORD=van_ephemeral_test_only',name,'psql','--host=127.0.0.1','--no-psqlrc','--set=ON_ERROR_STOP=1','-U','van_fixture','-d','postgres','-c','CREATE SCHEMA vati'])
 receipt['canonical_fixture_schema_initialized']=True
 testenv=dict(os.environ,VAN_TEST_EVENT_LOG=str(out/'test-events.jsonl'),PYTHONPATH='/workspace:'+':'.join(str(root/p) for p in ('backend','backend/tests','trading','trading/tests','.')),VATI_TEST_PG_DSN='postgresql://van_fixture:van_ephemeral_test_only@127.0.0.1:'+binding['HostPort']+'/postgres',VATI_TEST_PG_ISOLATED_FIXTURE='1',DIAL_REPO='/workspace/van-review-2026-10-18/dial-development-system')
 files=['trading/tests/test_forecast_runtime_supervisor.py', 'trading/tests/test_forecast_fixture_artifacts.py', 'trading/tests/test_forecast_worker_policy.py', 'trading/tests/test_ml_runtime_boundary.py', 'trading/tests/test_backtest_runner_cli.py', 'trading/tests/test_infra_live.py', 'trading/tests/test_single_session_profile_authority.py', 'trading/tests/test_single_session_lease.py', 'trading/tests/test_mandate_dispatch_validity.py', 'trading/tests/test_mandate_current_signer.py']
 (out/'targets.txt').write_text('\n'.join(files)+'\n')
 with (out/'full-trading.log').open('wb') as log:
  test=subprocess.Popen(['/workspace/van-backend-venv-20261025/bin/python','tools/rebuild/source_storage_audit.py','--report',str(out/'storage-audit.json'),*files,'--junitxml='+str(out/'full-trading.xml'),'-p','van_pytest_live_diagnostics','-o','faulthandler_timeout=120','--maxfail=1','-q'],cwd=root,env=testenv,stdout=log,stderr=subprocess.STDOUT)
  try:code=test.wait(timeout=360)
  except subprocess.TimeoutExpired:
   import signal
   receipt['timeout_seconds']=360;test.send_signal(signal.SIGINT)
   try:code=test.wait(timeout=30)
   except subprocess.TimeoutExpired:
    test.terminate()
    try:code=test.wait(timeout=10)
    except subprocess.TimeoutExpired:test.kill();code=test.wait(timeout=10)
 receipt['exit']=code;receipt['completed']=True
finally:
 if created:
  bound=json.loads(run(docker+['inspect',name]).stdout)[0]
  assert bound['Config']['Labels'].get('van.task')=='forecast-runtime-source-20261026'
  run(docker+['rm','--force',name]);receipt['cleaned']=True
 reaped=[]
 for attempt in range(100):
  try:
   child,status=os.waitpid(-1,os.WNOHANG)
   if child:reaped.append({'pid':child,'status':status});continue
   time.sleep(.05)
  except ChildProcessError:break
 receipt['adopted_children_reaped']=reaped
 (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt),flush=True)

raise SystemExit(receipt.get("exit",1))
