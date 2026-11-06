"""Collect exact corrected full/affected/remainder identity sets without executing tests."""
import json,pathlib,subprocess,os,hashlib,datetime
W=pathlib.Path('/workspace');R=W/'van-lanes-20261101/auth-final';O=W/'van-auth-corrected-collection-20261101';O.mkdir(exist_ok=False)
original=json.load(open(W/'van-auth-integrated-backend-full-20261101.json'));assert original.get('state')=='COMPLETED' and original.get('exit')!=0 and original.get('timed_out') is True, 'Conditional collection requires reconciled original timeout'
import re
old_log=(W/'van-auth-integrated-backend-full-20261101.log').read_text()
assert not any(re.fullmatch(r'[.sFxXE]+(?:\s+\[.*)?',line.strip()) and any(c in line.split('[')[0] for c in 'FxXE') for line in old_log.splitlines()), 'Original progress records actual failure/error; inspect before recovery'
assert 'FAILURES' not in old_log and 'ERRORS' not in old_log, 'Original run contains diagnosed failures/errors'
corrected=json.load(open(W/'van-auth-corrected-affected-20261101.json'));targets=[x for x in corrected['command'] if x.startswith('backend/tests/') and x.endswith('.py')];assert len(targets)==111
pins=json.load(open(W/'van-auth-corrected-source-pins-20261101.json'))['files']
for f,h in pins.items():assert hashlib.sha256((R/f).read_bytes()).hexdigest()==h,f
selectors={k:os.environ.get(k) for k in ['PYTHONPATH','DIAL_REPO']}
env=dict(os.environ,PYTHONPATH='/workspace:'+':'.join(str(R/p) for p in ['backend','backend/tests','trading','trading/tests','.']),DIAL_REPO='/workspace/van-review-2026-10-18/dial-development-system')
def collect(label,paths):
 dest=O/(label+'.json');env['VAN_COLLECTION_MANIFEST']=str(dest)
 command=['/workspace/van-backend-venv-20261025/bin/python','tools/rebuild/source_storage_audit.py','--report',str(O/(label+'-audit.json')),*paths,'--collect-only','-q','-p','van_auth_collection_manifest_20261101']
 with (O/(label+'.log')).open('wb') as log:r=subprocess.run(command,cwd=R,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=240)
 assert r.returncode==0,(label,r.returncode)
 assert json.load(open(O/(label+'-audit.json')))['forbidden_events']==[],label
 return json.load(open(dest))
full=collect('full',['backend/tests']);selected=collect('selected',targets)
fullids=set(full['nodeids']);selectedids=set(selected['nodeids']);assert selectedids<=fullids
remainingfiles=sorted({n.split('::',1)[0] for n in fullids-selectedids});assert not set(remainingfiles)&set(targets)
remaining=collect('remainder',remainingfiles);remainingids=set(remaining['nodeids']);assert not remainingids&selectedids;assert fullids==selectedids|remainingids
(O/'remaining-targets.txt').write_text('\n'.join(remainingfiles)+'\n')
for f,h in pins.items():assert hashlib.sha256((R/f).read_bytes()).hexdigest()==h,f
receipt={'schema':'van.auth-corrected-disjoint-collection/1','at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'full_nodeids':len(fullids),'selected_nodeids':len(selectedids),'remaining_nodeids':len(remainingids),'selected_files':len(targets),'remaining_files':len(remainingfiles),'full_equals_disjoint_union':True,'source_pins':str(W/'van-auth-corrected-source-pins-20261101.json'),'source_pins_sha256':hashlib.sha256((W/'van-auth-corrected-source-pins-20261101.json').read_bytes()).hexdigest(),'manifests':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in O.glob('*.json')},'original_full_terminal':original,'collection_plugin_sha256':hashlib.sha256((W/'van_auth_collection_manifest_20261101.py').read_bytes()).hexdigest(),'no_test_execution':True}
(O/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt),flush=True)
