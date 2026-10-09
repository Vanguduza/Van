"""Qualify exactly the frozen PR-93 VAN backend; do not modify repository inputs."""
from __future__ import annotations

from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(sys.argv[1]).resolve()
OUT = Path('/workspace/van-audit')
REVISION = sys.argv[2]
PYTHON = Path('/workspace/van-audit/canon-backend-venv-2026-10-09/bin/python')
CHROMIUM = Path('/workspace/.onboarding/playwright/chromium-1243/chrome-linux64/chrome')
STEM = 'canon-corrected-backend-full-' + REVISION[:8] + '-2026-10-09'


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def snapshot() -> dict[str, dict[str, object]]:
    paths = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    return {p: {'sha256': sha(ROOT / p), 'mode': oct((ROOT / p).stat().st_mode & 0o777),
                'bytes': (ROOT / p).stat().st_size}
            for p in sorted(paths) if p}


def dependency_snapshot() -> dict[str, object]:
    """Bind installed dependency source/binaries; interpreter caches are mutable."""
    distributions = []
    for distribution in metadata.distributions():
        files = {}
        for relative in distribution.files or []:
            path = Path(distribution.locate_file(relative))
            if path.suffix == '.pyc' or '__pycache__' in path.parts:
                continue
            files[str(relative)] = ({'sha256': sha(path), 'bytes': path.stat().st_size}
                                    if path.is_file() else {'missing': True})
        distributions.append({'name': distribution.metadata['Name'],
                              'version': distribution.version,
                              'files': dict(sorted(files.items()))})
    return {'distributions': sorted(distributions, key=lambda item: item['name'].lower()),
            'python_binary_sha256': sha(PYTHON.resolve()),
            'chromium_binary_sha256': sha(CHROMIUM),
            'openssl_binary_sha256': sha(Path('/usr/bin/openssl'))}


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def main() -> int:
    manifest = OUT / (STEM + '-inputs.json')
    result = OUT / (STEM + '-result.json')
    junit = OUT / (STEM + '.xml')
    log_path = OUT / (STEM + '.log')
    for p in (manifest, result, junit, log_path):
        assert not p.exists(), f'Existing immutable receipt: {p}'
    assert git('rev-parse', 'HEAD') == REVISION
    assert git('status', '--porcelain=v1') == ''
    before = snapshot()
    dependencies_before = dependency_snapshot()
    dependencies = sorted((d.metadata['Name'], d.version) for d in metadata.distributions())
    chromium_version = subprocess.check_output([str(CHROMIUM), '--version'], text=True).strip()
    toolchain = {
        'python': sys.version,
        'python_executable': str(PYTHON),
        'python_binary_sha256': sha(PYTHON.resolve()),
        'dependencies': dependencies,
        'chromium_path': str(CHROMIUM),
        'chromium_version': chromium_version,
        'chromium_binary_sha256': sha(CHROMIUM),
        'openssl_path': '/usr/bin/openssl',
        'openssl_binary_sha256': sha(Path('/usr/bin/openssl')),
        'uid': os.geteuid(),
    }
    write(manifest, {
        'schema_version': 1,
        'recorded_at_utc': utc(),
        'revision': REVISION,
        'cwd': str(ROOT),
        'selection': ['backend/tests'],
        'input_binding': 'all Git-tracked source, test, fixture, registry and documentation files',
        'files': before,
        'toolchain': toolchain,
        'installed_dependencies_before': dependencies_before,
        'runner_path': str(Path(__file__)),
        'runner_sha256': sha(Path(__file__)),
        'additional_external_source_paths': {
            '/workspace/cf-dds/agent-system/orchestration/cognitive-twin.mjs': 'absent; checked-in fixture used',
            '/home/user/dial-development-system': 'absent; upstream DDS reproduction prerequisite unavailable',
        },
    })
    command = [str(PYTHON), '-u', '-m', 'pytest', '-q', '-ra', 'backend/tests',
               '--junitxml=' + str(junit),
               '--basetemp=' + str(Path('/tmp') / ('vbf-' + REVISION[:8])),
               '-o', 'cache_dir=' + str(OUT / (STEM + '-cache'))]
    env = dict(os.environ)
    env['PYTHONPATH'] = 'backend:trading:.'
    env['VAN_TEST_CHROMIUM'] = str(CHROMIUM)
    started = utc()
    clock = time.monotonic()
    with log_path.open('w') as log:
        code = subprocess.call(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    duration = time.monotonic() - clock
    after = snapshot()
    dependencies_after = dependency_snapshot()
    dependencies_unchanged = dependencies_before == dependencies_after
    changed = sorted(p for p in before.keys() | after.keys() if before.get(p) != after.get(p))
    parsed = ET.parse(junit).getroot() if junit.exists() else None
    cases = list(parsed.iter('testcase')) if parsed is not None else []
    failures = [c for c in cases if c.find('failure') is not None]
    errors = [c for c in cases if c.find('error') is not None]
    skipped = [c for c in cases if c.find('skipped') is not None]
    xfails = [c for c in skipped if c.find('skipped').get('type') == 'pytest.xfail']
    skips = [c for c in skipped if c not in xfails]
    counts = {'collected_junit_testcases': len(cases),
              'passed': len(cases) - len(failures) - len(errors) - len(skipped),
              'failed': len(failures), 'errors': len(errors),
              'skipped': len(skips), 'expected_failure': len(xfails)}
    log_text = log_path.read_text()
    summaries = re.findall(r'(?m)^([^\n]*(?:passed|failed|skipped|errors?|xfailed|xpassed)[^\n]*\bin [0-9.]+s(?: \([^\n]*\))?)\s*$', log_text)
    terminal_summary = summaries[-1] if summaries else None
    complete_run = code in (0, 1) and bool(cases) and bool(terminal_summary) and 'KeyboardInterrupt' not in log_text
    terminal_outcomes = {kind: int(count) for count, kind in
                         re.findall(r'(\d+) (passed|failed|errors?|skipped|xfailed|xpassed)', terminal_summary or '')}
    junit_inferred_passes = counts['passed']
    counts['junit_records_without_failure_error_or_skip'] = junit_inferred_passes
    counts['passed'] = terminal_outcomes.get('passed', junit_inferred_passes if complete_run else None)
    head_after = git('rev-parse', 'HEAD')
    status_after = git('status', '--porcelain=v1')
    checkout_unchanged = not changed and head_after == REVISION and status_after == ''
    receipt = {
        'schema_version': 1,
        'revision': REVISION,
        'complete_run': complete_run,
        'suite': 'full backend',
        'selection': ['backend/tests'],
        'cwd': str(ROOT),
        'command': command,
        'nonsecret_environment_selectors': {'PYTHONPATH': env['PYTHONPATH'],
                                           'VAN_TEST_CHROMIUM': env['VAN_TEST_CHROMIUM']},
        'started_at_utc': started,
        'finished_at_utc': utc(),
        'duration_seconds': round(duration, 3),
        'exit_code': code,
        'counts': counts,
        'input_files': len(before),
        'source_unchanged_during_test': not changed,
        'installed_dependencies_unchanged_during_test': dependencies_unchanged,
        'installed_dependencies_after': dependencies_after,
        'terminal_summary': terminal_summary,
        'terminal_pytest_outcomes': terminal_outcomes,
        'changed_inputs': changed,
        'git_head_after': head_after,
        'git_status_after': status_after,
        'inputs_path': str(manifest),
        'inputs_sha256': sha(manifest),
        'junit_path': str(junit),
        'junit_sha256': sha(junit) if junit.exists() else None,
        'log_path': str(log_path),
        'log_sha256': sha(log_path),
        'skips': [{'classname': c.get('classname'), 'name': c.get('name'),
                   'reason': c.find('skipped').get('message')} for c in skips],
        'failures': [{'classname': c.get('classname'), 'name': c.get('name'),
                      'reason': c.find('failure').get('message')} for c in failures],
        'qualified_as_full_backend_pass': code == 0 and complete_run and checkout_unchanged and dependencies_unchanged,
        'physical_handset_tests_executed': 0,
        'live_service_connectivity_qualified': False,
        'production_deployed': False,
    }
    write(result, receipt)
    print(json.dumps({key: value for key, value in receipt.items()
                      if key != 'installed_dependencies_after'}, indent=2))
    print('\n'.join(log_text.splitlines()[-35:]))
    return code or int(not checkout_unchanged or not dependencies_unchanged)


if __name__ == '__main__':
    sys.exit(main())
