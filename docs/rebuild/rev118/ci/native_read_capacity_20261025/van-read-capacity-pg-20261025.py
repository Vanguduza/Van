import os,subprocess,pathlib,json,time,hashlib,ctypes
assert ctypes.CDLL(None,use_errno=True).prctl(36,1,0,0,0)==0
root=pathlib.Path('/workspace/van-review-2026-10-18/publish')
out=pathlib.Path('/workspace/van-read-capacity-pg-20261025');out.mkdir(exist_ok=True)
name='van-read-capacity-pg-20261025'
image='postgres:17.11-bookworm@sha256:858bb5e98eed02eb8cafbcdc007f9a65d1b613972028944a8ec2133ccaf80d27'
env=dict(os.environ)
for key in ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH'):env.pop(key,None)
docker=['docker','--host=unix:///var/run/docker.sock']
def run(args,**kwargs):return subprocess.run(args,env=env,check=True,text=True,capture_output=True,timeout=60,**kwargs)
created=False
receipt={'base_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'source_state':'UNCOMMITTED_NATIVE_READ_CAPACITY_CANDIDATE','container':name,'image':image,'completed':False,'cleaned':False}
receipt['source_sha256']={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in ['trading/vati/execution/ctrader/transport.py','trading/vati/execution/ctrader/adapter.py','trading/vati/funding/deals.py','trading/tests/conftest.py','trading/tests/test_ctrader.py','trading/tests/test_provider_entry_deadline.py','trading/tests/test_ctrader_transport_lifecycle.py','trading/tests/test_ctrader_connection_auth.py','trading/vati/execution/ctrader/contracts.py','trading/vati/market_data/native_archive.py','trading/vati/market_data/native_collector.py','trading/tests/test_native_market_archive.py','trading/tests/test_native_market_collector.py','trading/tests/test_ctrader_feed_contract.py','trading/tests/test_ctrader_read_budget.py','trading/vati/execution/ctrader/__init__.py','trading/vati/execution/ctrader/spots.py','trading/tests/test_ctrader_spot_contract.py','trading/tests/test_ctrader_event_selection.py','trading/tests/test_ctrader_read_capacity.py']}
try:
 cid=run(docker+['run','--detach','--name',name,'--label','van.task=read-capacity-source-20261025','--publish','127.0.0.1::5432','--tmpfs','/var/lib/postgresql/data:rw,nosuid,nodev,size=1024m','--env','POSTGRES_USER=van_fixture','--env','POSTGRES_PASSWORD=van_ephemeral_test_only',image]).stdout.strip();created=True;receipt['container_id']=cid
 for attempt in range(40):
  ready=subprocess.run(docker+['exec',name,'pg_isready','-U','van_fixture','-d','postgres'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5)
  if ready.returncode==0:break
  time.sleep(.5)
 else:raise RuntimeError('owned PostgreSQL fixture not ready')
 binding=json.loads(run(docker+['inspect',name]).stdout)[0]['NetworkSettings']['Ports']['5432/tcp'][0]
 assert binding['HostIp']=='127.0.0.1'
 run(docker+['exec',name,'psql','-U','van_fixture','-d','postgres','-c','CREATE SCHEMA vati'])
 receipt['canonical_fixture_schema_initialized']=True
 testenv=dict(os.environ,PYTHONPATH=':'.join(str(root/p) for p in ('backend','backend/tests','trading','trading/tests','.')),VATI_TEST_PG_DSN='postgresql://van_fixture:van_ephemeral_test_only@127.0.0.1:'+binding['HostPort']+'/postgres',VATI_TEST_PG_ISOLATED_FIXTURE='1',DIAL_REPO='/workspace/van-review-2026-10-18/dial-development-system')
 patterns=('test_ctrader*.py','test_native*.py','test_funding*.py','test_account*.py','test_retirement*.py','test_provider_entry_deadline.py','test_router_native_entry_deadline.py','test_execution*.py','test_commander*.py')
 files=sorted({str(p.relative_to(root)) for pattern in patterns for p in (root/'trading/tests').glob(pattern)})
 (out/'targets.txt').write_text('\n'.join(files)+'\n')
 with (out/'full-trading.log').open('wb') as log:
  result=subprocess.run(['/workspace/van-backend-venv-20261025/bin/python','tools/rebuild/source_storage_audit.py','--report',str(out/'storage-audit.json'),*files,'--junitxml='+str(out/'full-trading.xml'),'-q'],cwd=root,env=testenv,stdout=log,stderr=subprocess.STDOUT,timeout=300)
 receipt['exit']=result.returncode;receipt['completed']=True
finally:
 if created:
  bound=json.loads(run(docker+['inspect',name]).stdout)[0]
  assert bound['Config']['Labels'].get('van.task')=='read-capacity-source-20261025'
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
