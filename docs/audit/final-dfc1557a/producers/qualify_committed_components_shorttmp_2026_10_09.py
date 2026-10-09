#!/usr/bin/env python3
"""Source-bound local component qualification; never contacts production hosts."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.metadata as metadata
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import time
import tempfile
import shutil
import xml.etree.ElementTree as ET

ROOT = Path('/workspace/van-audit/canon-pr93-4ad31883-2026-10-09')
OUT = Path('/workspace/van-audit')
DDS = Path('/workspace/dial-development-system')
CANON_SHA = '4ad31883d57ab518ba9af414aa849db6e240eb71'
DDS_INPUTS = (
    'AGENTS.md',
    'agent-system/orchestration/engineering-resource-resolver.mjs',
    'agent-system/orchestration/engineering-resource-registry.mjs',
    'agent-system/orchestration/skill-resolver.mjs',
    'agent-system/orchestration/skill-registry.mjs',
    'agent-system/orchestration/state-store.mjs',
)
SUITES = {
    'trading': ('/workspace/van-audit/canon-backend-venv-2026-10-09/bin/python', ['trading/tests']),
    'hermes-scenarios': ('/workspace/van-audit/canon-backend-venv-2026-10-09/bin/python', ['hermes/policy/tests', 'tests/hermes', 'tests/scenarios']),
    'native-browser-services': ('/workspace/van-browser-runtime-venv/bin/python', ['services']),
}

def hash_file(path: Path) -> dict:
    data = path.read_bytes()
    return {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
            'mode': oct(path.stat().st_mode & 0o777)}

def capture_inputs() -> dict:
    revision = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != CANON_SHA:
        raise RuntimeError('qualification checkout revision changed')
    paths = subprocess.check_output(['git', '-C', str(ROOT), 'ls-files', '-z']).split(b'\0')
    files = {p.decode(): hash_file(ROOT / p.decode()) for p in paths if p}
    return {
        'revision': revision,
        'tracked_status': subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain=v1', '--untracked-files=no'], text=True),
        'files': files,
        'dds_revision': subprocess.check_output(['git', '-C', str(DDS), 'rev-parse', 'HEAD'], text=True).strip(),
        'dds_resolver_inputs': {p: hash_file(DDS / p) for p in DDS_INPUTS},
        'runner': hash_file(Path(__file__)),
    }

def stamp() -> str:
    return dt.datetime.now(dt.UTC).isoformat()

def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')

def main() -> int:
    global ROOT, CANON_SHA
    parser = argparse.ArgumentParser()
    parser.add_argument('suite', choices=SUITES)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--label', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9a-f]{40}', args.revision) or not re.fullmatch(r'[A-Za-z0-9._-]{1,80}', args.label):
        raise ValueError('literal revision and receipt label required')
    ROOT, CANON_SHA = args.repo, args.revision
    executable, selected = SUITES[args.suite]
    stem = OUT / f'committed-{args.suite}-{args.label}-2026-10-09'
    for suffix in ['-inputs.json', '.log', '.xml', '-result.json']:
        if Path(str(stem) + suffix).exists():
            raise RuntimeError(f'prior immutable receipt exists: {stem}{suffix}')
    inputs = capture_inputs()
    if inputs['tracked_status']:
        raise RuntimeError('tracked checkout dirt before qualification')
    temporary = Path(tempfile.mkdtemp(prefix='vq-', dir='/tmp'))
    temporary.chmod(0o700)
    env = dict(os.environ)
    env['TMPDIR'] = str(temporary)
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['PYTHONPATH'] = 'backend:trading:.'
    env['DIAL_REPO'] = str(DDS)
    env['VAN_TEST_CHROMIUM'] = '/workspace/.onboarding/playwright/chromium-1243/chrome-linux64/chrome'
    env['PATH'] = '/workspace/.onboarding/bin:' + env['PATH']
    command = [executable, '-m', 'pytest', *selected, '-q', '-ra', '-o', 'cache_dir=' + str(temporary / 'cache'), '--basetemp=' + str(temporary / 'pt'), f'--junitxml={stem}.xml']
    runtime = subprocess.check_output([executable, '-c', 'import importlib.metadata as m,json,sys; print(json.dumps({"executable":sys.executable,"version":sys.version,"packages":{d.metadata["Name"]:d.version for d in m.distributions()}},sort_keys=True))'], text=True)
    before = {'schema_version': 1, 'recorded_at_utc': stamp(), 'suite': args.suite, 'cwd': str(ROOT),
              'command': command, 'environment_selectors': {key:env[key] for key in ('PYTHONDONTWRITEBYTECODE','PYTHONPATH','DIAL_REPO','VAN_TEST_CHROMIUM','PATH','TMPDIR')},
              'toolchain': json.loads(runtime), 'source_inputs': inputs,
              'scope': 'local controlled component suites; no production deployment or handset acceptance'}
    write(Path(str(stem) + '-inputs.json'), before)
    start = time.monotonic()
    with Path(str(stem) + '.log').open('w') as log:
        run = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=False)
    after = capture_inputs()
    changed = []
    for section in ('files', 'dds_resolver_inputs'):
        original, current = inputs[section], after[section]
        changed.extend(f'{section}:{key}' for key in sorted(original.keys() | current.keys()) if original.get(key) != current.get(key))
    changed.extend(key for key in ('revision', 'dds_revision', 'tracked_status', 'runner') if inputs[key] != after[key])
    cases = ET.parse(str(stem) + '.xml').getroot().findall('.//testcase')
    skips = [{'name': x.attrib.get('classname','') + '::' + x.attrib.get('name',''),
              'message': x.find('skipped').attrib.get('message',''), 'detail': x.find('skipped').text}
             for x in cases if x.find('skipped') is not None]
    failures = [{'name': x.attrib.get('classname','') + '::' + x.attrib.get('name',''),
                 'kind': child.tag, 'message': child.attrib.get('message',''), 'detail': child.text}
                for x in cases for child in x if child.tag in ('failure','error')]
    result = {'schema_version':1, 'recorded_at_utc':stamp(), 'suite':args.suite,
              'revision':CANON_SHA, 'exit_code':run.returncode, 'elapsed_seconds':round(time.monotonic()-start,3),
              'counts':{'cases':len(cases), 'passed':len(cases)-len(skips)-len(failures),'skipped':len(skips),
                        'failed':sum(x['kind']=='failure' for x in failures),'errors':sum(x['kind']=='error' for x in failures)},
              'skipped_cases':skips,'failed_cases':failures,'changed_inputs':changed,
              'inputs_sha256':hash_file(Path(str(stem)+'-inputs.json'))['sha256'],
              'log_sha256':hash_file(Path(str(stem)+'.log'))['sha256'],
              'junit_sha256':hash_file(Path(str(stem)+'.xml'))['sha256'],
              'qualified':run.returncode==0 and not changed,
              'live_production_qualified':False,'handset_cases_executed':0}
    shutil.rmtree(temporary)
    result['private_short_tmp_removed'] = True
    write(Path(str(stem)+'-result.json'), result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('failed_cases','skipped_cases')}, sort_keys=True))
    return run.returncode if not changed else 99

if __name__ == '__main__':
    raise SystemExit(main())
