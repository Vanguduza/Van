"""Revalidate every backend test module reading Android source after its sole delta."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib,json,os,subprocess,xml.etree.ElementTree as ET
ROOT=Path('/workspace/Van')
OUT=Path('/workspace/van-audit')
FREEZE=ROOT/'docs/audit/validation/van-production-source-freeze-provider-speaker-2026-10-08-r7.json'
STEM='backend-android-static-provider-speaker-2026-10-08-r7'
SELECTION=['backend/tests/test_account_approval_contract.py','backend/tests/test_owner_status_kotlin_contract.py']

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def snapshot(frozen):
    files={ROOT/p for p in frozen}
    files.update(p for p in (ROOT/'backend/tests').rglob('*') if p.is_file() and not set(p.parts)&{'__pycache__','.pytest_cache','build','.gradle','.git'})
    return {str(p.relative_to(ROOT)):digest(p) for p in sorted(files)}

frozen=json.loads(FREEZE.read_text())['files']
assert all((ROOT/p).is_file() and digest(ROOT/p)==h for p,h in frozen.items())
before=snapshot(frozen)
(OUT/(STEM+'-inputs-before.json')).write_text(json.dumps({'schema_version':1,'files':before,'production_manifest':str(FREEZE.relative_to(ROOT)),'production_manifest_sha256':digest(FREEZE)},indent=2)+'\n')
command=['/workspace/.onboarding/van-venv/bin/python','-m','pytest','-q',*SELECTION,'--junitxml='+str(OUT/(STEM+'.xml'))]
started=datetime.now(timezone.utc).isoformat()
with (OUT/(STEM+'.log')).open('w') as log:
    code=subprocess.call(command,cwd=ROOT,env={**os.environ,'PYTHONPATH':'backend:trading:.'},stdout=log,stderr=subprocess.STDOUT)
after=snapshot(frozen)
changed=sorted(p for p in before.keys()|after.keys() if before.get(p)!=after.get(p))
(OUT/(STEM+'-inputs-after.json')).write_text(json.dumps({'schema_version':1,'files':after,'production_manifest':str(FREEZE.relative_to(ROOT)),'production_manifest_sha256':digest(FREEZE)},indent=2)+'\n')
cases=list(ET.parse(OUT/(STEM+'.xml')).getroot().iter('testcase'))
counts={'tests':len(cases),'failures':sum(c.find('failure') is not None for c in cases),'errors':sum(c.find('error') is not None for c in cases),'skipped':sum(c.find('skipped') is not None for c in cases)}
counts['passed']=counts['tests']-counts['failures']-counts['errors']-counts['skipped']
result={'schema_version':1,'suite':'backend-static-android-source','selection':SELECTION,'command':command,'started_at_utc':started,'finished_at_utc':datetime.now(timezone.utc).isoformat(),'exit_code':code,'counts':counts,'source_unchanged_during_test':not changed,'changed_inputs':changed,'input_files':len(before),'production_manifest_sha256':digest(FREEZE),'physical_tests_executed':0,'production_deployed':False,'overlay_count_is_non_additive_to_full_backend':True}
(OUT/(STEM+'-result.json')).write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
print((OUT/(STEM+'.log')).read_text().splitlines()[-1])
raise SystemExit(code or bool(changed))
