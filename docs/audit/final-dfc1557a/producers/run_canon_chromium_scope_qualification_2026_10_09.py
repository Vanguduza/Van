"""Bind candidate scoped regressions without claiming a clean committed full suite."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path('/workspace/van-audit/canon-chromium-runtime-fix-2026-10-09')
BASE = Path('/workspace/van-audit')
STEM = 'canon-chromium-combined-scoped-2026-10-09'
PYTHON = Path('/workspace/van-audit/canon-backend-venv-2026-10-09/bin/python')
CHROMIUM = Path('/workspace/.onboarding/playwright/chromium-1243/chrome-linux64/chrome')
SELECTION = [
    'backend/tests/test_browser_review_i5_task_scope.py',
    'backend/tests/test_browser_review_i6_scope.py',
    'backend/tests/test_harness_elements.py',
    'backend/tests/test_browser_review_i4_fail_safe_classifier.py',
    'backend/tests/test_browser_interaction_router.py',
    'tests/contracts/test_task_scope_shared_url_rule.py',
    'backend/tests/test_harness_pseudo_hit_ownership.py',
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def snapshot():
    files = set(subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')) - {''}
    files.update(SELECTION)
    return {name: {'sha256': sha(ROOT / name), 'bytes': (ROOT / name).stat().st_size,
                   'mode': oct((ROOT / name).stat().st_mode & 0o777)}
            for name in sorted(files)}


def write(path, body):
    path.write_text(json.dumps(body, indent=2, sort_keys=True) + '\n')


import os

inputs = BASE / (STEM + '-inputs.json')
result = BASE / (STEM + '-result.json')
log = BASE / (STEM + '.log')
xml = BASE / (STEM + '.xml')
assert all(not path.exists() for path in (inputs, result, log, xml))
assert all((ROOT / name).is_file() for name in SELECTION)
before = snapshot()
head = git('rev-parse', 'HEAD')
status = git('status', '--porcelain=v1')
binding_runner = BASE / 'run_canon_corrected_backend_qualification_2026_10_09.py'
sys.argv = [str(binding_runner), str(ROOT), head]
spec = importlib.util.spec_from_file_location('scoped_dependency_binding', binding_runner)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
dependencies = module.dependency_snapshot()
write(inputs, {'schema_version': 1, 'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
               'base_revision': head, 'candidate_git_status': status,
               'source_binding': 'All tracked inputs plus explicitly selected new regression file; candidate is intentionally uncommitted.',
               'files': before, 'installed_dependencies_before': dependencies,
               'selection': SELECTION, 'runner_path': str(Path(__file__)),
               'runner_sha256': sha(Path(__file__)), 'whole_backend_suite': False})
command = [str(PYTHON), '-u', '-m', 'pytest', '-q', '-ra', *SELECTION,
           '--junitxml=' + str(xml), '--basetemp=/tmp/vbcs20261009',
           '-o', 'cache_dir=' + str(BASE / (STEM + '-cache'))]
env = dict(os.environ, PYTHONPATH='backend:trading:.:backend/tests', VAN_TEST_CHROMIUM=str(CHROMIUM))
started = datetime.now(timezone.utc).isoformat()
clock = time.monotonic()
with log.open('w') as stream:
    code = subprocess.call(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
elapsed = time.monotonic() - clock
after = snapshot()
dependency_after = module.dependency_snapshot()
cases = list(ET.parse(xml).getroot().iter('testcase')) if xml.exists() else []
failed = [c for c in cases if c.find('failure') is not None]
errors = [c for c in cases if c.find('error') is not None]
skipped = [c for c in cases if c.find('skipped') is not None]
receipt = {'schema_version': 1, 'scope': 'combined changed Chromium/scope regressions',
           'base_revision': head, 'candidate_git_status_before': status,
           'source_clean_committed_claimed': False, 'whole_backend_suite': False,
           'selection': SELECTION, 'command': command,
           'started_at_utc': started, 'finished_at_utc': datetime.now(timezone.utc).isoformat(),
           'duration_seconds': round(elapsed, 3), 'exit_code': code,
           'counts': {'passed': len(cases) - len(failed) - len(errors) - len(skipped),
                      'failed': len(failed), 'errors': len(errors), 'skipped': len(skipped),
                      'expected_failure': sum(c.find('skipped').get('type') == 'pytest.xfail' for c in skipped)},
           'all_bound_source_bytes_modes_unchanged': before == after,
           'installed_dependencies_unchanged': dependencies == dependency_after,
           'head_unchanged': git('rev-parse', 'HEAD') == head,
           'git_status_after': git('status', '--porcelain=v1'),
           'input_manifest': str(inputs), 'input_manifest_sha256': sha(inputs),
           'junit_path': str(xml), 'junit_sha256': sha(xml) if xml.exists() else None,
           'log_path': str(log), 'log_sha256': sha(log),
           'physical_handset_tests_executed': 0, 'live_host_services_qualified': False,
           'production_deployed': False,
           'scoped_checks_passed': code == 0 and before == after and dependencies == dependency_after,
           'complete_final_backend_run_still_required': True}
write(result, receipt)
print(json.dumps(receipt, indent=2))
print('\n'.join(log.read_text().splitlines()[-25:]))
sys.exit(code or int(before != after or dependencies != dependency_after))
