from pathlib import Path
import hashlib, json, os, subprocess, time, xml.etree.ElementTree as ET
ROOT=Path('/workspace/van-audit/canon-chromium-runtime-fix-2026-10-09')
OUT=Path('/workspace/van-audit/harness-pseudo-hit-ownership-selected-contracts-r2-2026-10-09')
PYTHON='/workspace/van-audit/canon-backend-venv-2026-10-09/bin/python'
CHROME='/workspace/.onboarding/playwright/chromium-1243/chrome-linux64/chrome'
selected=[
'backend/tests/test_harness_pseudo_hit_ownership.py',
'deploy/van-browser-core/browser/harness_service.py',
'deploy/van-browser-core/browser/egress_proxy.py',
'backend/van_gateway/browser/action_risk.py',
'backend/van_gateway/browser/adapters.py',
'backend/van_gateway/browser/interaction_router.py',
'backend/van_gateway/browser/task_scope.py',
'backend/van_gateway/browser/models.py',
'backend/van_gateway/config.py',
'backend/tests/test_browser_review_i5_task_scope.py',
'backend/tests/test_harness_elements.py',
'backend/tests/test_browser_interaction_router.py',
'backend/tests/test_browser_api.py',
'backend/tests/cdp_harness_kit.py',
'backend/tests/fixtures/review_i5/media.html',
'backend/tests/conftest.py',
'backend/pytest.ini',
'backend/requirements.txt',
]
def snapshot():
    return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in selected if (ROOT/p).is_file()}
for suffix in ['-inputs.json','.xml','.log','-result.json']:
    if Path(str(OUT)+suffix).exists(): raise RuntimeError('refusing overwrite')
before=snapshot()
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
cmd=[PYTHON,'-u','-m','pytest','-q','-ra','backend/tests/test_harness_pseudo_hit_ownership.py','--junitxml='+str(OUT)+'.xml','--basetemp=/tmp/vhpo-r2-20261009','-o','cache_dir='+str(OUT)+'-cache']
inputs={'checkout':str(ROOT),'base_revision':head,'scope':'New real-Chromium pseudo ownership file; selected sources only; no full backend, live host or phone qualification','selected_source_sha256_before':before,'command':cmd,'tool_binaries_sha256':{p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in [PYTHON,CHROME]},'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
Path(str(OUT)+'-inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
env={**os.environ,'PYTHONPATH':'backend:trading:.','VAN_TEST_CHROMIUM':CHROME}
start=time.monotonic()
with Path(str(OUT)+'.log').open('w') as log:
    code=subprocess.run(cmd,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT).returncode
after=snapshot()
x=ET.parse(str(OUT)+'.xml').getroot()
testcases=x.findall('.//testcase')
result={'exit_code':code,'elapsed_seconds':round(time.monotonic()-start,3),'cases':len(testcases),'failures':len(x.findall('.//failure')),'errors':len(x.findall('.//error')),'skipped':len(x.findall('.//skipped')),'selected_sources_unchanged':before==after,'selected_source_sha256_after':after,'junit_sha256':hashlib.sha256(Path(str(OUT)+'.xml').read_bytes()).hexdigest(),'log_sha256':hashlib.sha256(Path(str(OUT)+'.log').read_bytes()).hexdigest(),'input_receipt_sha256':hashlib.sha256(Path(str(OUT)+'-inputs.json').read_bytes()).hexdigest(),'live_host_tests':False,'phone_tests':False,'broad_suite_run':False}
Path(str(OUT)+'-result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
raise SystemExit(code or (2 if before!=after else 0))
