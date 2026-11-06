import pathlib,json,subprocess,os,hashlib,datetime
W=pathlib.Path('/workspace');R=W/'van-lanes-20261101/auth-final';C=W/'van-auth-corrected-collection-r2-20261101';receipt=json.load(open(C/'receipt.json'));assert receipt['full_equals_disjoint_union']
pins=json.load(open(W/'van-auth-corrected-source-pins-20261101.json'))['files']
for f,h in pins.items():assert hashlib.sha256((R/f).read_bytes()).hexdigest()==h,f
assert not (W/'van-auth-corrected-remainder-20261101.json').exists()
files=(C/'remaining-targets.txt').read_text().splitlines();assert len(files)==213
prefix='van-auth-corrected-remainder-20261101'
env=dict(os.environ,PYTHONPATH=':'.join(str(R/p) for p in ['backend','backend/tests','trading','trading/tests','.']),DIAL_REPO='/workspace/van-review-2026-10-18/dial-development-system')
freeze=subprocess.check_output(['/workspace/van-backend-venv-20261025/bin/python','-m','pip','freeze'],text=True)
(W/'van-auth-corrected-remainder-environment-20261101.json').write_text(json.dumps({'source_pins_sha256':hashlib.sha256((W/'van-auth-corrected-source-pins-20261101.json').read_bytes()).hexdigest(),'collection_receipt_sha256':hashlib.sha256((C/'receipt.json').read_bytes()).hexdigest(),'python':'/workspace/van-backend-venv-20261025/bin/python','package_freeze_sha256':hashlib.sha256(freeze.encode()).hexdigest(),'environment_selectors':{k:env[k] for k in ['PYTHONPATH','DIAL_REPO']},'fixture_selectors_present':{k:bool(env.get(k)) for k in ['VATI_TEST_PG_DSN','VATI_TEST_PG_ISOLATED_FIXTURE']},'timeout_seconds':3600,'timeout_rationale':'Original whole-backend attempt exhausted40minutes before completion. This disjoint4416-case remainder receives a bounded60-minute budget to avoid repeating that insufficient whole-suite limit while sharing CPU with the existing1527-case shard; no original tests are credited as passed, and no covered tests are restarted. Actual original terminal evidence and exact collection union are retained.'},indent=2)+'\n')
command=['/workspace/van-backend-venv-20261025/bin/python','/workspace/van-recorded-command-cwd-20261101.py','--name',prefix,'--cwd',str(R),'--timeout','3600','--','/workspace/van-backend-venv-20261025/bin/python','tools/rebuild/source_storage_audit.py','--report',str(W/'van-auth-corrected-remainder-audit-20261101.json'),*files,'--junitxml='+str(W/(prefix+'.xml')),'-q']
raise SystemExit(subprocess.call(command,cwd=R,env=env))
