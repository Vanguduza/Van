"""Run a disjoint suite against the final source and record byte stability."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, os, subprocess, sys

ROOT = Path('/workspace/Van')
OUT = Path('/workspace/van-audit')
FREEZE = ROOT / 'docs/audit/validation/van-production-source-freeze-provider-speaker-2026-10-08-r6.json'
SUITES = {
    'backend': ['backend/tests'],
    'contracts': ['tests/contracts'],
    'hermes-scenarios': ['tests/hermes', 'hermes/policy/tests', 'tests/scenarios'],
    'trading': ['trading/tests'],
}

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def snapshot(selection, frozen):
    files = {ROOT/p for p in frozen}
    for path in selection:
        files.update(p for p in (ROOT/path).rglob('*') if p.is_file()
            and not set(p.parts) & {'__pycache__', '.pytest_cache', 'build', '.gradle', '.git'})
    if selection == SUITES['contracts']:
        files.update(p for base in ('registries', 'docs/audit') for p in (ROOT/base).rglob('*')
            if p.is_file() and 'validation' not in p.parts)
    return {str(p.relative_to(ROOT)): digest(p) for p in sorted(files)}

name = sys.argv[1]
selection = SUITES[name]
frozen = json.loads(FREEZE.read_text())['files']
assert all((ROOT/p).is_file() and digest(ROOT/p) == h for p,h in frozen.items())
revision = '-'+sys.argv[2] if len(sys.argv)>2 else ''
stem = name + '-expansion-frozen-final-2026-10-08'+revision
before = snapshot(selection, frozen)
manifest = OUT / (stem+'-inputs.json')
manifest.write_text(json.dumps({'schema_version':1, 'files':before,
    'production_manifest':str(FREEZE.relative_to(ROOT)),
    'production_manifest_sha256':digest(FREEZE)}, indent=2)+'\n')
command = ['/workspace/.onboarding/van-venv/bin/python', '-m', 'pytest', '-q', *selection,
    '--junitxml='+str(OUT/(stem+'.xml'))]
environment = dict(os.environ)
environment['PYTHONPATH'] = 'backend:trading:.'
started = datetime.now(timezone.utc).isoformat()
with (OUT/(stem+'.log')).open('w') as log:
    code = subprocess.call(command, cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT)
after = snapshot(selection, frozen)
changed = sorted(p for p in before.keys() | after.keys() if before.get(p) != after.get(p))
receipt = {'schema_version':1,'suite':name,'selection':selection,'command':command,
    'cwd':str(ROOT),'started_at_utc':started,'finished_at_utc':datetime.now(timezone.utc).isoformat(),
    'exit_code':code,'source_unchanged_during_test':not changed,'changed_inputs':changed,
    'input_files':len(before),'inputs_sha256':digest(manifest),
    'production_manifest_sha256':digest(FREEZE),'physical_tests_executed':0,
    'production_deployed':False}
(OUT/(stem+'-result.json')).write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
print('\n'.join((OUT/(stem+'.log')).read_text().splitlines()[-20:]))
sys.exit(code or bool(changed))
