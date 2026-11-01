"""Sequential exact-case recovery, frozen source, owned bounded temp lifecycle."""
from pathlib import Path
import argparse,json,subprocess,os,hashlib,datetime,ctypes,time,signal
from van_owned_basetemp_20261101 import preflight,cleanup
p=argparse.ArgumentParser();p.add_argument('label',choices=['selected','remainder']);a=p.parse_args();assert ctypes.CDLL(None,use_errno=True).prctl(36,1,0,0,0)==0
W=Path('/workspace');R=W/'van-lanes-20261101/auth-final';out=W/('van-auth-'+a.label+'-storage-recovery-r1-20261101');out.mkdir(exist_ok=False);temp='/tmp/van-recovery-auth-'+a.label+'-20261101';before=preflight(temp)
plan_path=W/'van-storage-recovery-sets-20261101'/(a.label+'.json');plan=json.load(open(plan_path));files=plan['recovery_cases'];assert len(files)=={'selected':588,'remainder':999}[a.label]
pins=json.load(open(W/'van-auth-corrected-source-pins-20261101.json'))['files']
for f,h in pins.items():assert hashlib.sha256((R/f).read_bytes()).hexdigest()==h,f
extra=json.load(open(W/'van-auth-shared-shard-environment-20261101.json'))
for f,h in extra['source_config_fixture_files'].items():assert hashlib.sha256((R/f).read_bytes()).hexdigest()==h,f
freeze=subprocess.check_output(['/workspace/van-backend-venv-20261025/bin/python','-m','pip','freeze'],text=True);assert hashlib.sha256(freeze.encode()).hexdigest()==extra['package_freeze_sha256']
env=dict(os.environ,PYTHONPATH='/workspace:'+':'.join(str(R/p) for p in ['backend','backend/tests','trading','trading/tests','.']),DIAL_REPO='/workspace/van-review-2026-10-18/dial-development-system',VAN_TEST_EVENT_LOG=str(out/'test-events.jsonl'))
command=['/workspace/van-backend-venv-20261025/bin/python','tools/rebuild/source_storage_audit.py','--report',str(out/'storage-audit.json'),*files,'--basetemp='+temp,'--junitxml='+str(out/'recovery.xml'),'-p','van_pytest_live_diagnostics','-q']
receipt={'schema':'van.auth-storage-recovery/1','label':a.label,'started_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'cwd':str(R),'source_sha256':pins,'source_pins_sha256':hashlib.sha256((W/'van-auth-corrected-source-pins-20261101.json').read_bytes()).hexdigest(),'environment_pin_sha256':hashlib.sha256((W/'van-auth-shared-shard-environment-20261101.json').read_bytes()).hexdigest(),'recovery_plan_sha256':hashlib.sha256(plan_path.read_bytes()).hexdigest(),'command':command,'environment_selectors':{k:env[k] for k in ['PYTHONPATH','DIAL_REPO','VAN_TEST_EVENT_LOG']},'diagnostic_plugin_sha256':hashlib.sha256((W/'van_pytest_live_diagnostics.py').read_bytes()).hexdigest(),'instrumentation_difference':'External /workspace path added only to import pinned passive test-report diagnostic plugin; same application/worktree, packages, fixtures and tests.','owned_temp_preflight':before,'timeout_seconds':5400,'timeout_rationale':'Originalselected1053cases took1258seconds withCPUsharing; exact588/999recoverycases receive90minute boundedbudget on sequentialworker to avoid restarting an insufficient40minute whole-suite limit. Ownedtemp preflight+cleanup required.','completed':False,'controller_pid':os.getpid()}
(out/'source-start.json').write_text(json.dumps(receipt,indent=2)+'\n');(out/'targets.txt').write_text('\n'.join(files)+'\n')
with (out/'recovery.log').open('wb') as log:
 child=subprocess.Popen(command,cwd=R,env=env,stdout=log,stderr=subprocess.STDOUT);receipt['command_pid']=child.pid
 try:code=child.wait(timeout=5400)
 except subprocess.TimeoutExpired:
  receipt['timed_out']=True;child.send_signal(signal.SIGINT)
  try:code=child.wait(timeout=30)
  except subprocess.TimeoutExpired:
   child.terminate()
   try:code=child.wait(timeout=10)
   except subprocess.TimeoutExpired:child.kill();code=child.wait(timeout=10)
reaped=[]
while True:
 try:
  pid,status=os.waitpid(-1,os.WNOHANG)
  if pid:reaped.append({'pid':pid,'status':status})
  else:time.sleep(.05)
 except ChildProcessError:break
receipt.update(completed=True,exit=code,finished_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),adopted_children_reaped=reaped)
receipt['owned_temp_cleanup']=cleanup(temp,out)
for f,h in pins.items():assert hashlib.sha256((R/f).read_bytes()).hexdigest()==h,f
(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items() if k not in ['source_sha256','command']}),flush=True);raise SystemExit(code)
