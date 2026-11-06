import os,subprocess,pathlib,json,time,hashlib,ctypes
assert ctypes.CDLL(None,use_errno=True).prctl(36,1,0,0,0)==0
root=pathlib.Path('/workspace/van-review-2026-10-18/publish')
out=pathlib.Path('/workspace/van-native-risk-context-final-r2-20261027');out.mkdir(exist_ok=True)
name='van-native-risk-context-final-r2-20261027'
image='postgres:17.11-bookworm@sha256:858bb5e98eed02eb8cafbcdc007f9a65d1b613972028944a8ec2133ccaf80d27'
env=dict(os.environ)
for key in ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH'):env.pop(key,None)
docker=['docker','--host=unix:///var/run/docker.sock']
def run(args,**kwargs):return subprocess.run(args,env=env,check=True,text=True,capture_output=True,timeout=600,**kwargs)
created=False
receipt={'base_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'source_state':'ORIGINAL_NATIVE_ACCOUNT_CONTEXT_SOURCE_AND_LEGACY_COMPATIBILITY','container':name,'image':image,'completed':False,'cleaned':False}
receipt['diagnostic_plugin_sha256']=hashlib.sha256(pathlib.Path('/workspace/van_pytest_live_diagnostics.py').read_bytes()).hexdigest()
receipt['source_sha256']={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for subroot in ('backend/van_gateway','backend/tests','trading/vati','trading/tests','trading/vati_forecast_worker','trading/worker_tests') for p in (root/subroot).rglob('*.py')}
receipt['test_timeout_seconds']=1800
receipt['reference_fixtures_sha256']={'trading/tests/fixtures/legacy_risk_snapshot_b58bb578.json':hashlib.sha256((root/'trading/tests/fixtures/legacy_risk_snapshot_b58bb578.json').read_bytes()).hexdigest()}
(out/'source-start.json').write_text(json.dumps(receipt,indent=2)+'\n')
try:
 cid=run(docker+['run','--detach','--init','--cpus','1','--memory','1073741824','--pids-limit','256','--name',name,'--label','van.task=native-risk-context-source-20261027','--publish','127.0.0.1::5432','--tmpfs','/var/lib/postgresql/data:rw,nosuid,nodev,size=1024m','--env','POSTGRES_USER=van_fixture','--env','POSTGRES_PASSWORD=van_ephemeral_test_only',image]).stdout.strip();created=True;receipt['container_id']=cid
 for attempt in range(40):
  try:
   ready=subprocess.run(docker+['exec','--env','PGPASSWORD=van_ephemeral_test_only',name,'psql','--host=127.0.0.1','--username=van_fixture','--dbname=postgres','--no-psqlrc','--tuples-only','--no-align','--set=ON_ERROR_STOP=1','--command=SELECT 1'],env=env,text=True,capture_output=True,timeout=5)
  except subprocess.TimeoutExpired:
   receipt.setdefault('readiness_probe_timeouts',[]).append(attempt);continue
  if ready.returncode==0 and ready.stdout.strip()=='1':break
  time.sleep(.5)
 else:raise RuntimeError('owned PostgreSQL fixture not ready')
 binding=json.loads(run(docker+['inspect',name]).stdout)[0]['NetworkSettings']['Ports']['5432/tcp'][0]
 assert binding['HostIp']=='127.0.0.1'
 run(docker+['exec','--env','PGPASSWORD=van_ephemeral_test_only',name,'psql','--host=127.0.0.1','--no-psqlrc','--set=ON_ERROR_STOP=1','-U','van_fixture','-d','postgres','-c','CREATE SCHEMA vati'])
 receipt['canonical_fixture_schema_initialized']=True
 testenv=dict(os.environ,VAN_TEST_EVENT_LOG=str(out/'test-events.jsonl'),PYTHONPATH='/workspace:'+':'.join(str(root/p) for p in ('backend','backend/tests','trading','trading/tests','.')),VATI_TEST_PG_DSN='postgresql://van_fixture:van_ephemeral_test_only@127.0.0.1:'+binding['HostPort']+'/postgres',VATI_TEST_PG_ISOLATED_FIXTURE='1',DIAL_REPO='/workspace/van-review-2026-10-18/dial-development-system')

 files=['trading/tests/test_native_risk_account_context.py', 'trading/tests/test_native_risk_account_context_postgres.py', 'trading/tests/test_account_coordinator.py', 'trading/tests/test_coordinator_instance_arbitration.py', 'trading/tests/test_single_session_lease.py', 'trading/tests/test_single_session_unknown_entry.py', 'trading/tests/test_single_session_recovery.py', 'trading/tests/test_mt5_funding_runtime.py', 'trading/tests/test_funding_runtime.py', 'trading/tests/test_funding_risk_fence.py', 'trading/tests/test_funding_risk_fence_postgres.py', 'trading/tests/test_native_account_observation.py', 'trading/tests/test_position_risk_original_terms.py', 'trading/tests/test_margin_report_scale.py', 'trading/tests/test_risk_arithmetic_context.py', 'trading/tests/test_authority.py', 'trading/tests/test_authority_properties.py', 'trading/tests/test_risk_intent_binding.py', 'trading/tests/test_risk_boolean_facts.py', 'trading/tests/test_live_risk_is_real.py', 'trading/tests/test_dispatch_current_risk.py', 'trading/tests/test_account_risk_recovery_scope.py', 'trading/tests/test_recoverable_lockouts.py', 'trading/tests/test_native_margin_facts.py', 'trading/tests/test_execution.py', 'trading/tests/test_execution_and_exits.py', 'trading/tests/test_execution_economics_invariants.py', 'trading/tests/test_execution_scale_and_rounding.py', 'trading/tests/test_ledger_read_snapshot.py', 'trading/tests/test_consolidated_ledger_transactions.py', 'backend/tests/test_trading_api.py', 'backend/tests/test_trading_readmodels.py', 'backend/tests/test_account_runtime_recovery_gateway.py', 'backend/tests/test_runtime_recovery_expired_dispatch.py', 'backend/tests/test_runtime_recovery_faults.py', 'backend/tests/test_runtime_recovery_journal.py', 'backend/tests/test_runtime_recovery_outbox.py', 'backend/tests/test_runtime_recovery_protocol.py']
 (out/'targets.txt').write_text('\n'.join(files)+'\n')
 with (out/'full-trading.log').open('wb') as log:
  test=subprocess.Popen(['/workspace/van-backend-venv-20261025/bin/python','tools/rebuild/source_storage_audit.py','--report',str(out/'storage-audit.json'),*files,'--junitxml='+str(out/'full-trading.xml'),'-p','van_pytest_live_diagnostics','-o','faulthandler_timeout=0','-q'],cwd=root,env=testenv,stdout=log,stderr=subprocess.STDOUT)
  try:code=test.wait(timeout=1800)
  except subprocess.TimeoutExpired:
   import signal
   receipt['timeout_seconds']=1800;test.send_signal(signal.SIGINT)
   try:code=test.wait(timeout=30)
   except subprocess.TimeoutExpired:
    test.terminate()
    try:code=test.wait(timeout=10)
    except subprocess.TimeoutExpired:test.kill();code=test.wait(timeout=10)
 receipt['exit']=code;receipt['completed']=True
finally:
 if created:
  bound=json.loads(run(docker+['inspect',name]).stdout)[0]
  assert bound['Config']['Labels'].get('van.task')=='native-risk-context-source-20261027'
  run(docker+['rm','--force',name]);receipt['cleaned']=True
  absent=subprocess.run(docker+['inspect',name],env=env,text=True,capture_output=True,timeout=30)
  assert absent.returncode!=0 and 'No such object' in absent.stderr
  receipt['owned_fixture_independently_absent']=True
 reaped=[]
 for attempt in range(100):
  try:
   child,status=os.waitpid(-1,os.WNOHANG)
   if child:reaped.append({'pid':child,'status':status});continue
   time.sleep(.05)
  except ChildProcessError:break
 receipt['adopted_children_reaped']=reaped
 (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({k:v for k,v in receipt.items() if k!='source_sha256'}),flush=True)

raise SystemExit(receipt.get("exit",1))
