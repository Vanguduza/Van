"""Run the actual cognitive broad source selection with backend-only dependencies."""
from pathlib import Path
import ctypes,datetime,hashlib,importlib.util,json,os,signal,subprocess,time

assert ctypes.CDLL(None,use_errno=True).prctl(36,1,0,0,0)==0
root=Path('/workspace/van-review-2026-10-18/publish')
out=Path('/workspace/van-pretrade-ci-lite-broad-r1-20261030')
assert not out.exists();out.mkdir()
primary=json.loads(Path('/workspace/van-pretrade-durable-budget-final-full-r1-20261030/source-start.json').read_text())
pins=primary['source_sha256']|primary['reference_fixtures_sha256']
assert all(hashlib.sha256((root/f).read_bytes()).hexdigest()==h for f,h in pins.items())
python='/workspace/van-backend-ci-lite-20261029/bin/python'
capability=subprocess.check_output([python,'-c','import sys,importlib.util,json;print(json.dumps({"python":sys.version,"psycopg_available":importlib.util.find_spec("psycopg")is not None}))'],text=True)
capability=json.loads(capability);assert not capability['psycopg_available']
record={'base_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
 'state':'RUNNING_NOT_COMPLETE','completed':False,'cleaned':False,
 'started_at_utc':datetime.datetime.now(datetime.UTC).isoformat(),
 'source_sha256':primary['source_sha256'],'reference_fixtures_sha256':primary['reference_fixtures_sha256'],
 'dependency_mode':'FRESH_VENV_BACKEND_REQUIREMENTS_LOCK_ONLY_NO_POSTGRES_DRIVER',
 'capability':capability,'backend_requirements_lock_sha256':hashlib.sha256((root/'backend/requirements.lock').read_bytes()).hexdigest(),
 'diagnostic_plugin_sha256':hashlib.sha256(Path('/workspace/van_pytest_live_diagnostics.py').read_bytes()).hexdigest(),
 'native_or_independent_acceptance':False}
(out/'source-start.json').write_text(json.dumps(record,indent=2)+'\n')
env=dict(os.environ)
env.pop('VATI_TEST_PG_DSN',None);env.pop('DIAL_REPO',None)
env.update(VATI_TEST_PG_ISOLATED_FIXTURE='0',VAN_TEST_EVENT_LOG=str(out/'test-events.jsonl'),
 PYTHONPATH='/workspace:'+':'.join(str(root/p) for p in ('backend','backend/tests','trading','trading/tests','.')))
files=['trading/tests','backend/tests/test_cognitive_fabric.py','backend/tests/test_cognitive_twin.py',
 'backend/tests/test_context_admission_api.py','backend/tests/test_context_lifecycle_governance.py']
(out/'targets.txt').write_text('\n'.join(files)+'\n')
code=1
try:
 with (out/'broad.log').open('xb') as log:
  test=subprocess.Popen([python,'tools/rebuild/source_storage_audit.py','--report',str(out/'storage-audit.json'),
   *files,'--junitxml='+str(out/'broad.xml'),'-p','van_pytest_live_diagnostics','-o','faulthandler_timeout=0','-q'],
   cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  record['test_pid']=test.pid
  try:code=test.wait(timeout=1800)
  except subprocess.TimeoutExpired:
   record['timed_out']=True;os.killpg(test.pid,signal.SIGINT)
   try:code=test.wait(timeout=30)
   except subprocess.TimeoutExpired:
    os.killpg(test.pid,signal.SIGTERM)
    try:code=test.wait(timeout=10)
    except subprocess.TimeoutExpired:os.killpg(test.pid,signal.SIGKILL);code=test.wait(timeout=10)
finally:
 reaped=[];no_children=False
 for attempt in range(100):
  try:
   pid,status=os.waitpid(-1,os.WNOHANG)
   if pid:reaped.append({'pid':pid,'status':status})
   else:time.sleep(.05)
  except ChildProcessError:no_children=True;break
 record.update(exit=code,state='COMPLETED',completed=True,cleaned=no_children,
  adopted_children_reaped=reaped,owned_children_independently_reaped=no_children,
  source_hashes_still_match=all(hashlib.sha256((root/f).read_bytes()).hexdigest()==h for f,h in pins.items()),
  finished_at_utc=datetime.datetime.now(datetime.UTC).isoformat())
 (out/'receipt.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({k:v for k,v in record.items() if k not in ('source_sha256','reference_fixtures_sha256')}))
raise SystemExit(code)
