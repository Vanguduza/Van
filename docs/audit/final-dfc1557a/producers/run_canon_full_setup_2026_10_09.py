"""Execute the complete reusable installer and bind independent source readback."""
from pathlib import Path
from datetime import datetime, timezone
from importlib import metadata
import hashlib
import json
import os
import subprocess
import sys
import time

revision = sys.argv[1]
script = Path(sys.argv[2]).resolve()
out = Path('/workspace/van-audit')
stem = 'canon-setup-full-install-' + revision[:8] + '-2026-10-09'
result_path = out / (stem + '-result.json')
inputs_path = out / (stem + '-inputs.json')
log_path = out / (stem + '.log')
after_path = out / (stem + '-after.json')
assert not any(path.exists() for path in (result_path, inputs_path, log_path, after_path))
assert Path(sys.prefix).resolve() == Path('/workspace/van-audit/canon-backend-venv-2026-10-09')
expected_script_sha256 = '16243ab17f6e3273a26656afb75899155a4f226c05399830de2773bf429ec583'
assert revision == 'dfc1557ab99ad8d41cf84714e1bb671e89b045e6'
assert script == Path('/workspace/.onboarding/reusable-install-canon-dfc1557a-2026-10-09.sh')
publication_path = out / f'canon-source-publication-{revision[:8]}-2026-10-09.json'
publication = json.loads(publication_path.read_text())
assert publication['source_sha'] == revision
canon_root = Path('/workspace/.onboarding/canon') / revision / 'Van'
assert not canon_root.exists(), 'This check requires an independently acquired new checkout'

def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')

def git(path, *args):
    return subprocess.check_output(['git', '-C', str(path), *args], text=True).strip()

def tree(path, checkout_modes=False):
    values = {}
    raw = subprocess.check_output(['git', '-C', str(path), 'ls-files', '-s', '-z'])
    for entry in raw.split(b'\0'):
        if not entry:
            continue
        header, raw_name = entry.split(b'\t', 1)
        mode, blob, stage = header.decode().split()
        name = os.fsdecode(raw_name)
        file = path / name
        assert stage == '0' or checkout_modes
        if not file.exists() and not file.is_symlink():
            assert checkout_modes, name
            values[name] = {'git_mode': mode, 'git_blob': blob, 'missing': True}
            continue
        if file.is_symlink():
            content = os.fsencode(os.readlink(file))
            digest, size = hashlib.sha256(content).hexdigest(), len(content)
        else:
            digest, size = sha(file), file.stat().st_size
            if not checkout_modes:
                assert bool(file.stat().st_mode & 0o111) == (mode == '100755')
        values[name] = {'git_mode': mode, 'git_blob': blob, 'sha256': digest, 'bytes': size}
        if checkout_modes:
            values[name]['checkout_mode'] = oct(file.lstat().st_mode & 0o777)
    return values

def original_state():
    return {str(path): {'head': git(path, 'rev-parse', 'HEAD'),
                       'status_sha256': hashlib.sha256(git(path, 'status', '--porcelain=v1').encode()).hexdigest(),
                       'git_index_records_sha256': hashlib.sha256(subprocess.check_output(['git', '-C', str(path), 'ls-files', '-s', '-z'])).hexdigest(),
                       'tracked_files': tree(path, True)}
            for path in (Path('/workspace/Van'), Path('/workspace/dial-development-system'))}

def dependencies():
    values = {}
    for distribution in metadata.distributions():
        files = {}
        for relative in distribution.files or []:
            file = Path(distribution.locate_file(relative))
            if file.suffix == '.pyc' or '__pycache__' in file.parts:
                continue
            files[str(relative)] = {'sha256': sha(file), 'bytes': file.stat().st_size} if file.is_file() else {'missing': True}
        values[distribution.metadata['Name']] = {'version': distribution.version, 'files': files}
    return values

before = original_state()
dependencies_before = dependencies()
assert sha(script) == expected_script_sha256
started = datetime.now(timezone.utc).isoformat()
write(inputs_path, {'source_sha': revision, 'script': {'path': str(script), 'sha256': sha(script)},
                    'publication_receipt_sha256': sha(publication_path),
                    'originals_before': before, 'backend_dependencies_before': dependencies_before,
                    'invoking_python': {'executable': sys.executable, 'prefix': sys.prefix,
                                        'binary_sha256': sha(Path(sys.executable).resolve())},
                    'producer_sha256': sha(Path(__file__))})
clock = time.monotonic()
code = None
after = None
dependencies_after = None
source_readback = None
collection_errors = []
source_origin_matches = False
try:
    with log_path.open('x') as log:
        code = subprocess.call(['bash', str(script)], stdout=log, stderr=subprocess.STDOUT)
except Exception as exc:
    collection_errors.append({'phase': 'installer_execution', 'type': type(exc).__name__, 'message': str(exc)})
for phase, collector in (('originals_after', original_state), ('backend_dependencies_after', dependencies)):
    try:
        value = collector()
        if phase == 'originals_after':
            after = value
        else:
            dependencies_after = value
    except Exception as exc:
        collection_errors.append({'phase': phase, 'type': type(exc).__name__, 'message': str(exc)})
observations = []
try:
    log_lines = log_path.read_text().splitlines() if log_path.exists() else []
except Exception as exc:
    collection_errors.append({'phase': 'installer_log_readback', 'type': type(exc).__name__, 'message': str(exc)})
    log_lines = []
for line in log_lines:
    try:
        item = json.loads(line)
    except json.JSONDecodeError:
        continue
    if isinstance(item, dict):
        observations.append(item)
if canon_root.exists():
    try:
        source_origin_matches = git(canon_root, 'config', '--get', 'remote.origin.url') == 'https://github.com/Vanguduza/Van.git'
        source_readback = {'root': str(canon_root), 'head': git(canon_root, 'rev-parse', 'HEAD'),
                           'status': git(canon_root, 'status', '--porcelain=v1'), 'files': tree(canon_root),
                           'expected_https_origin_matches': source_origin_matches}
    except Exception as exc:
        collection_errors.append({'phase': 'new_source_readback', 'type': type(exc).__name__, 'message': str(exc)})
try:
    script_digest_after = sha(script)
except Exception as exc:
    collection_errors.append({'phase': 'installer_script_after', 'type': type(exc).__name__, 'message': str(exc)})
    script_digest_after = None
script_unchanged = script_digest_after == expected_script_sha256
source_matches = bool(source_readback and source_origin_matches and source_readback['head'] == revision and not source_readback['status'] and source_readback['files'] == publication['files'])
readiness = any(item.get('setup') == 'PASS' and item.get('source_revision') == revision for item in observations)
gateway = any(item.get('scope') == 'OWNED_ISOLATED_LOCAL_GATEWAY' and item.get('status') == 'PASS' and item.get('source_revision') == revision for item in observations)
chromium = any(item.get('local_chromium_functional_request') == 'PASS' for item in observations)
original_differences = [name for name in before.keys() | (after or {}).keys() if before.get(name) != (after or {}).get(name)]
dependency_differences = [name for name in dependencies_before.keys() | (dependencies_after or {}).keys() if dependencies_before.get(name) != (dependencies_after or {}).get(name)]
source_differences = [name for name in publication['files'].keys() | (source_readback or {}).get('files', {}).keys() if publication['files'].get(name) != (source_readback or {}).get('files', {}).get(name)]
write(after_path, {'originals_after': after, 'backend_dependencies_after': dependencies_after,
                   'source_readback': source_readback, 'script_sha256_after': script_digest_after,
                   'original_differences': original_differences,
                   'dependency_differences': dependency_differences,
                   'source_differences': source_differences, 'collection_errors': collection_errors})
passed = code == 0 and not collection_errors and script_unchanged and before == after and dependencies_before == dependencies_after and source_matches and readiness and gateway and chromium
write(result_path, {
    'record_kind': 'ACTUAL_COMPLETE_REUSABLE_CLOUD_INSTALLER_EXECUTION',
    'source_sha': revision, 'started_at_utc': started, 'finished_at_utc': datetime.now(timezone.utc).isoformat(),
    'elapsed_seconds': round(time.monotonic() - clock, 3), 'exit_code': code,
    'completed_successfully': passed, 'independent_https_source_readback_matches': source_matches,
    'source_readback_file_count': len(source_readback['files']) if source_readback else 0,
    'original_git_heads_status_and_tracked_bytes_modes_unchanged': before == after,
    'original_untracked_file_bytes_measured': False,
    'backend_dependencies_unchanged': dependencies_before == dependencies_after,
    'owned_local_gateway_functional_requests_pass': gateway, 'real_chromium_functional_request_pass': chromium,
    'observations': observations, 'inputs_path': str(inputs_path), 'inputs_sha256': sha(inputs_path),
    'log_path': str(log_path), 'log_sha256': sha(log_path) if log_path.exists() else None, 'script_path': str(script), 'script_sha256': script_digest_after,
    'reviewed_script_unchanged': script_unchanged, 'expected_https_clone_origin_verified': source_origin_matches,
    'after_path': str(after_path), 'after_sha256': sha(after_path),
    'original_differences': original_differences, 'dependency_differences': dependency_differences,
    'source_differences': source_differences, 'collection_errors': collection_errors,
    'complete_application_suites_rerun_by_installer': False, 'configuration_activated': False,
    'fresh_task_snapshot_restoration_tested': False, 'production_deployed': False, 'physical_cases_executed': 0,
})
print(json.dumps({'result': str(result_path), 'passed': passed, 'exit_code': code,
                  'source_files_independently_verified': len(source_readback['files']) if source_readback else 0}))
raise SystemExit(0 if passed else 1)
