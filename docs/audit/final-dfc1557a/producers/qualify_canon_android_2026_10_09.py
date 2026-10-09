"""Run sequential Android builds from one clean source revision; never install an APK."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(sys.argv[1]).resolve()
REVISION = sys.argv[2]
OUT = Path('/workspace/van-audit')
STATE = Path('/workspace/.onboarding')
STEM = 'canon-corrected-android-' + REVISION[:8] + '-2026-10-09'
ENV = dict(os.environ, JAVA_HOME=str(STATE/'jdk/usr/lib/jvm/java-21-openjdk-amd64'),
           GRADLE_USER_HOME=str(STATE/'gradle'), ANDROID_HOME=str(STATE/'android-sdk'),
           ANDROID_USER_HOME=str(STATE/'android-user'))
GRADLE = str(STATE/'gradle-8.11.1/bin/gradle')

def utc():
    return datetime.now(timezone.utc).isoformat()

def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()

def snapshot():
    names = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    return {name: {'sha256': sha(ROOT/name), 'bytes': (ROOT/name).stat().st_size,
                   'mode': oct((ROOT/name).stat().st_mode & 0o777)} for name in names if name}

def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True)+'\n')

def cases(directory):
    records = []
    for path in sorted(directory.glob('TEST-*.xml')):
        for case in ET.parse(path).getroot().iter('testcase'):
            records.append({'class': case.get('classname'), 'name': case.get('name'),
                            'failed': case.find('failure') is not None,
                            'error': case.find('error') is not None,
                            'skipped': case.find('skipped') is not None})
    return {'passed': sum(not any(c[key] for key in ('failed', 'error', 'skipped')) for c in records),
            'failed': sum(c['failed'] for c in records), 'errors': sum(c['error'] for c in records),
            'skipped': sum(c['skipped'] for c in records), 'cases': records}

def main():
    inputs = OUT/(STEM+'-inputs.json')
    result = OUT/(STEM+'-result.json')
    assert not inputs.exists() and not result.exists(), 'Immutable receipts already exist'
    assert git('rev-parse', 'HEAD') == REVISION and not git('status', '--porcelain=v1')
    before = snapshot()
    voice = ROOT/'android/app/build/generated/voice-assets'
    sealed = {str(p.relative_to(voice)): sha(p) for p in sorted(voice.rglob('*')) if p.is_file()}
    assert len(sealed) == 46, 'Expected 45 generic files plus pinned manifest'
    version = subprocess.check_output([GRADLE, '--version'], env=ENV, text=True)
    write(inputs, {'revision': REVISION, 'created_at_utc': utc(), 'files': before,
                   'generic_assets': sealed, 'gradle_version': version,
                   'java_binary_sha256': sha(Path(ENV['JAVA_HOME'])/'bin/java'),
                   'gradle_script_sha256': sha(Path(GRADLE)), 'runner_sha256': sha(Path(__file__)),
                   'nonsecret_environment_selectors': {k: ENV[k] for k in
                      ('JAVA_HOME', 'GRADLE_USER_HOME', 'ANDROID_HOME', 'ANDROID_USER_HOME')}})
    commands = [
        [GRADLE, '-p', str(ROOT/'android/verification'), 'test', '--no-daemon', '--max-workers=2', '--console=plain'],
        [GRADLE, '-p', str(ROOT/'android'), ':app:testDebugUnitTest', ':app:assembleDebug',
         ':app:lintDebug', ':app:assembleDebugAndroidTest', '--no-daemon', '--max-workers=2', '--console=plain'],
    ]
    executions = []
    started = utc()
    for index, command in enumerate(commands):
        log_path = OUT/(STEM+f'-{index+1}.log')
        assert not log_path.exists()
        clock = time.monotonic()
        with log_path.open('w') as log:
            code = subprocess.call(command, cwd=ROOT, env=ENV, stdout=log, stderr=subprocess.STDOUT)
        executions.append({'command': command, 'exit_code': code,
                           'duration_seconds': round(time.monotonic()-clock, 3),
                           'log_path': str(log_path), 'log_sha256': sha(log_path)})
        print(json.dumps({'completed_gradle_invocation': index+1, 'exit_code': code}), flush=True)
        if code:
            break
    after = snapshot()
    changed = sorted(p for p in before.keys() | after.keys() if before.get(p) != after.get(p))
    unchanged_voice = sealed == {str(p.relative_to(voice)): sha(p) for p in sorted(voice.rglob('*')) if p.is_file()}
    jvm = cases(ROOT/'android/verification/build/test-results/test')
    app = cases(ROOT/'android/app/build/test-results/testDebugUnitTest')
    lint = ROOT/'android/app/build/reports/lint-results-debug.xml'
    issues = list(ET.parse(lint).getroot().iter('issue')) if lint.exists() else []
    lint_counts = {level: sum(i.get('severity') == level for i in issues) for level in ('Fatal', 'Error', 'Warning')}
    apk = ROOT/'android/app/build/outputs/apk/debug/app-debug.apk'
    metadata = None
    apk_checks = {}
    if len(executions) == 2 and all(e['exit_code'] == 0 for e in executions):
        tool_dir = STATE/'android-sdk/build-tools/36.0.0'
        signer = subprocess.check_output([str(tool_dir/'apksigner'), 'verify', '--verbose', '--print-certs', str(apk)], env=ENV, text=True)
        badging = subprocess.check_output([str(tool_dir/'aapt'), 'dump', 'badging', str(apk)], env=ENV, text=True)
        signer_path = OUT/(STEM+'-apk-signer.txt')
        badging_path = OUT/(STEM+'-apk-badging.txt')
        signer_path.write_text(signer)
        badging_path.write_text(badging)
        with zipfile.ZipFile(apk) as archive:
            matches = [p for p in archive.infolist() if p.filename == 'assets/van-build-provenance.json']
            assert len(matches) == 1 and 1 <= matches[0].file_size <= 4096
            raw = archive.read(matches[0])
            metadata = json.loads(raw)
        config = (ROOT/'android/app/build/generated/source/buildConfig/debug/com/dial/van/BuildConfig.java').read_text()
        def field(name):
            match = re.search(r'public static final String '+name+r' = ("(?:\\.|[^"\\])*");', config)
            assert match, name
            return json.loads(match[1])
        assert metadata == {'schema_version': 1, 'application_id': 'com.dial.van',
            'source_sha': REVISION, 'gateway_url': field('VAN_GATEWAY_BASE_URL'),
            'gateway_ca_pem_b64_sha256': hashlib.sha256(field('VAN_GATEWAY_CA_PEM_B64').encode()).hexdigest(),
            'connectivity_trusted_keys_sha256': hashlib.sha256(field('VAN_CONNECTIVITY_TRUSTED_KEYS').encode()).hexdigest()}
        assert field('VAN_SOURCE_SHA') == REVISION
        assert "launchable-activity: name='com.dial.van.command.CommandCentreActivity'" in badging
        apk_checks = {'path': str(apk), 'bytes': apk.stat().st_size, 'sha256': sha(apk),
                      'public_provenance_sha256': hashlib.sha256(raw).hexdigest(),
                      'signature_verified': True, 'signer_readback_path': str(signer_path),
                      'signer_readback_sha256': sha(signer_path),
                      'badging_readback_sha256': sha(badging_path),
                      'command_centre_launcher_verified': True,
                      'embedded_source_and_connection_provenance_verified': True,
                      'production_owner_signer_verified': False,
                      'production_connection_profile_verified': False}
    passed = (len(executions) == 2 and all(e['exit_code'] == 0 for e in executions)
              and not changed and unchanged_voice and bool(jvm['passed']) and bool(app['passed'])
              and not any(jvm[k] or app[k] for k in ('failed', 'errors', 'skipped'))
              and lint.exists() and not lint_counts['Fatal'] and not lint_counts['Error'] and bool(apk_checks))
    write(result, {'revision': REVISION, 'started_at_utc': started, 'finished_at_utc': utc(),
                   'executions': executions, 'host_jvm': jvm, 'android_app_unit': app,
                   'lint': lint_counts, 'inputs_sha256': sha(inputs), 'changed_inputs': changed,
                   'source_unchanged_during_run': not changed, 'generic_assets_unchanged': unchanged_voice,
                   'git_head_after': git('rev-parse', 'HEAD'), 'git_status_after': git('status', '--porcelain=v1'),
                   'apk': apk_checks, 'public_apk_provenance': metadata,
                   'instrumentation_compiled': len(executions) == 2 and executions[-1]['exit_code'] == 0,
                   'instrumentation_executed': False, 'physical_handset_tests_executed': 0,
                   'owner_release_built': False, 'production_deployed': False,
                   'qualified_as_android_debug_source_pass': passed})
    print(json.dumps({'result_path': str(result), 'passed': passed,
                       'host_jvm': {k:v for k,v in jvm.items() if k != 'cases'},
                       'android_app_unit': {k:v for k,v in app.items() if k != 'cases'},
                       'lint': lint_counts, 'apk': apk_checks}), flush=True)
    return 0 if passed else 1

if __name__ == '__main__':
    sys.exit(main())
