#!/usr/bin/env python3
"""Retain measured805f inputs only for reviewed unaffected component scopes."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

OUT = Path('/workspace/van-audit')
BASE = OUT / 'canon-runtime-fix-2026-10-09'
PREVIOUS = OUT / 'canon-android-build-fix-2026-10-09'
BASE_SHA = '805f3b67c2b9eb68d887cd700f9443f476e26132'
PREVIOUS_SHA = 'ffa18d578eae6dd2e484a60fa3fb912c4204635c'
OLD_PROOF = OUT / 'component-input-equivalence-805f-to-ffa18-2026-10-09.json'
HELPER = OUT / 'prove_component_equivalence_805f_ffa18_2026_10_09.py'
CONSUMERS = {
    'trading/tests/test_browser_worker_deployment.py': 'trading.tests.test_browser_worker_deployment',
    'trading/tests/test_jev_architecture_boundary.py': 'trading.tests.test_jev_architecture_boundary',
}
RUNTIME_REGRESSIONS = {
    'backend/van_gateway/browser/task_scope.py',
    'deploy/van-browser-core/browser/harness_service.py',
    'deploy/van-browser-core/browser/egress_proxy.py',
    'backend/tests/fixtures/task_scope/url_vectors.v1.json',
    'tests/contracts/test_task_scope_shared_url_rule.py',
    'backend/tests/test_harness_pseudo_hit_ownership.py',
}
METADATA = {
    'docs/audit/OWNER_FRONTEND_CONTRACT.html',
    'docs/audit/OWNER_FRONTEND_REGISTRY_GUIDE.md',
    'docs/audit/VAN_OWNER_REGISTRY_SOURCE_REVIEW_2026-10-09-r7.json',
    'registries/owner_features.json', 'registries/owner_screens.json',
    'docs/project-state/LOCAL_CHANGE_LEDGER.jsonl',
}

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def cases(path: Path) -> list[dict]:
    return [{'classname': node.get('classname', ''), 'name': node.get('name', ''),
             'status': 'skipped' if node.find('skipped') is not None else
                       'failed' if node.find('failure') is not None else
                       'error' if node.find('error') is not None else 'passed'}
            for node in ET.parse(path).getroot().iter('testcase')]

def counts(items: list[dict]) -> dict:
    return {'cases': len(items), **{key: sum(x['status'] == value for x in items)
            for key, value in [('passed', 'passed'), ('skipped', 'skipped'),
                               ('failed', 'failed'), ('errors', 'error')]}}

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', required=True, type=Path)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--label', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9a-f]{40}', args.revision) or not re.fullmatch(r'[A-Za-z0-9._-]{1,80}', args.label):
        raise RuntimeError('exact source revision and literal receipt label required')
    target = OUT / f'component-scope-equivalence-805f-to-{args.label}-2026-10-09.json'
    if target.exists():
        raise RuntimeError('prior immutable proof exists')
    spec = importlib.util.spec_from_file_location('retained_component_proof_helper', HELPER)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    digest, snapshot = helper.digest, helper.snapshot
    base = snapshot(BASE, BASE_SHA)
    previous = snapshot(PREVIOUS, PREVIOUS_SHA)
    child = snapshot(args.repo, args.revision)
    old = json.loads(OLD_PROOF.read_text())
    if old['measured_execution_revision'] != BASE_SHA or old['equivalent_child_revision'] != PREVIOUS_SHA or old['child_suite_executions'] != 0:
        raise RuntimeError('prior child proof scope differs')
    old_changed = set(old['reviewed_changes'])
    def changed(a, b):
        fields = ('sha256', 'bytes', 'git_mode', 'git_kind', 'git_blob')
        return {name for name in a.keys() | b.keys()
                if {field: a.get(name, {}).get(field) for field in fields} !=
                   {field: b.get(name, {}).get(field) for field in fields}}
    child_changes = changed(previous['tree'], child['tree'])
    if not RUNTIME_REGRESSIONS.issubset(child_changes) or child_changes - RUNTIME_REGRESSIONS - METADATA:
        raise RuntimeError('unreviewed source delta: ' + str(child_changes - RUNTIME_REGRESSIONS - METADATA))
    total_changes = changed(base['tree'], child['tree'])
    if total_changes - old_changed - child_changes:
        raise RuntimeError('unexpected805f ancestry delta')
    registry_differences = {}
    for filename in ('registries/owner_features.json', 'registries/owner_screens.json'):
        differences = helper.json_differences(json.loads((PREVIOUS / filename).read_text()),
                                             json.loads((args.repo / filename).read_text()))
        allowed = {'/current_source_qualification/source_review_manifest',
                   '/current_source_qualification/source_review_manifest_sha256',
                   '/historical_source_qualifications/pre_oct9_r7_chromium_runtime_correction'}
        if set(differences) != allowed:
            raise RuntimeError('owner feature/screen contracts changed beyond review pointers')
        registry_differences[filename] = differences
    guide = 'docs/audit/OWNER_FRONTEND_REGISTRY_GUIDE.md'
    if (PREVIOUS / guide).read_text().replace('VAN_OWNER_REGISTRY_SOURCE_REVIEW_2026-10-09-r6.json',
        'VAN_OWNER_REGISTRY_SOURCE_REVIEW_2026-10-09-r7.json') != (args.repo / guide).read_text():
        raise RuntimeError('guide changes exceed review pointer')
    ledger_path = 'docs/project-state/LOCAL_CHANGE_LEDGER.jsonl'
    old_ledger, new_ledger = (PREVIOUS / ledger_path).read_text(), (args.repo / ledger_path).read_text()
    if not new_ledger.startswith(old_ledger) or len(new_ledger[len(old_ledger):].splitlines()) != 1:
        raise RuntimeError('ledger change is not one preserved-history append')
    ledger = json.loads(new_ledger[len(old_ledger):].strip())
    if ledger['parent_sha'] != PREVIOUS_SHA or any(ledger[key] for key in ('covered_files', 'authority_classes', 'authorization_ids')):
        raise RuntimeError('ledger claims unmeasured authority')
    manifest_path = 'docs/audit/VAN_OWNER_REGISTRY_SOURCE_REVIEW_2026-10-09-r7.json'
    manifest = json.loads((args.repo / manifest_path).read_text())
    if manifest['base_application_sha'] != PREVIOUS_SHA or manifest['status'] != 'REVIEWED_SOURCE_ONLY' or manifest['physical_cases_executed'] != 0 or any(manifest[key] for key in ('owner_release', 'deployment_accepted', 'actual_native_schema_discovery', 'native_schema_fixture_is_live')):
        raise RuntimeError('manifest overstates observed qualification')
    if set(manifest['additional_review_inputs']) != RUNTIME_REGRESSIONS:
        raise RuntimeError('manifest runtime regression bindings differ')
    for name, recorded in manifest['files'].items():
        if sha(args.repo / name) != recorded:
            raise RuntimeError('manifest cited source hash changed: ' + name)
    unchanged = sorted(base['tree'].keys() - total_changes)
    permission_differences = {name: {'base': base['tree'][name], 'child': child['tree'][name]}
                              for name in unchanged if base['tree'][name]['mode'] != child['tree'][name]['mode']}
    if set(permission_differences) - helper.HISTORICAL_MODES:
        raise RuntimeError('runtime/source filesystem permission changed')
    retained = sorted(set(unchanged) - set(permission_differences))
    if any(base['tree'][name] != child['tree'][name] for name in retained):
        raise RuntimeError('retained source content/mode differs')
    receipts, original = {}, {}
    for suite in ('trading', 'hermes-scenarios', 'native-browser-services'):
        stem = OUT / f'committed-{suite}-final-805f3b67-2026-10-09'
        inp = json.loads(Path(str(stem) + '-inputs.json').read_text())
        result = json.loads(Path(str(stem) + '-result.json').read_text())
        if result['revision'] != BASE_SHA or not result['qualified'] or result['changed_inputs']:
            raise RuntimeError('original component qualification differs')
        for suffix, key in (('-inputs.json', 'inputs_sha256'), ('.log', 'log_sha256'), ('.xml', 'junit_sha256')):
            path = Path(str(stem) + suffix)
            if sha(path) != result[key]:
                raise RuntimeError('original execution artifact changed')
            receipts[str(path)] = digest(path)
        receipts[str(Path(str(stem) + '-result.json'))] = digest(Path(str(stem) + '-result.json'))
        for name, recorded in inp['source_inputs']['files'].items():
            if digest(BASE / name) != recorded:
                raise RuntimeError('original measured805f source changed')
        for name, recorded in inp['source_inputs']['dds_resolver_inputs'].items():
            if digest(Path('/workspace/dial-development-system') / name) != recorded:
                raise RuntimeError('recorded DDS resolver input changed')
        if subprocess.check_output(['git', '-C', '/workspace/dial-development-system', 'rev-parse', 'HEAD'], text=True).strip() != inp['source_inputs']['dds_revision']:
            raise RuntimeError('DDS source revision changed')
        runtime = json.loads(subprocess.check_output([inp['toolchain']['executable'], '-c',
            'import importlib.metadata as m,json,sys; print(json.dumps({"executable":sys.executable,"version":sys.version,"packages":{d.metadata["Name"]:d.version for d in m.distributions()}},sort_keys=True))'], text=True))
        if runtime != inp['toolchain']:
            raise RuntimeError('recorded component toolchain changed')
        original[suite] = {'result': result, 'cases': cases(Path(str(stem) + '.xml'))}
    trading = original['trading']['cases']
    excluded = [item for item in trading if item['classname'] in CONSUMERS.values()]
    remaining = [item for item in trading if item['classname'] not in CONSUMERS.values()]
    if counts(excluded) != {'cases': 18, 'passed': 18, 'skipped': 0, 'failed': 0, 'errors': 0} or counts(remaining)['passed'] != 1467:
        raise RuntimeError('affected trading case identities/counts differ')
    fresh_stem = OUT / f'committed-trading-affected-parser-consumers-{args.label}-2026-10-09'
    fresh = json.loads(Path(str(fresh_stem) + '-result.json').read_text())
    fresh_cases = cases(Path(str(fresh_stem) + '.xml'))
    if fresh['revision'] != args.revision or not fresh['qualified'] or fresh['changed_inputs'] or fresh['counts'] != counts(excluded):
        raise RuntimeError('fresh affected-consumer execution is not qualified')
    identity = lambda item: (item['classname'], item['name'])
    if sorted(map(identity, fresh_cases)) != sorted(map(identity, excluded)):
        raise RuntimeError('fresh trading consumer cases differ from excluded805f cases')
    for suffix, key in (('-inputs.json', 'inputs_sha256'), ('.log', 'log_sha256'), ('.xml', 'junit_sha256')):
        path = Path(str(fresh_stem) + suffix)
        if sha(path) != fresh[key]:
            raise RuntimeError('fresh18case artifact changed')
        receipts[str(path)] = digest(path)
    receipts[str(Path(str(fresh_stem) + '-result.json'))] = digest(Path(str(fresh_stem) + '-result.json'))
    pgstem = OUT / 'postgres-current-source-final-805f3b67-2026-10-09'
    pginputs = json.loads(Path(str(pgstem) + '-inputs.json').read_text())
    pg = json.loads(Path(str(pgstem) + '.json').read_text())
    if not pg['qualified'] or pg['revision'] != BASE_SHA or pg['changed_inputs'] or not all(pg[key] for key in ('fixture_stopped', 'no_fixture_server_running', 'temporary_database_removed')):
        raise RuntimeError('original actual PostgreSQL qualification/cleanup differs')
    pgroot = Path('/workspace/.onboarding/browser-parser/postgres-root')
    driver = OUT / 'canon-pg-driver-3.2.9-2026-10-09'
    for name, recorded in pginputs['source_inputs']['driver_files'].items():
        if digest(driver / name) != recorded:
            raise RuntimeError('exact private driver changed')
    for name, recorded in pginputs['source_inputs']['server_binaries'].items():
        if digest(pgroot / 'usr/lib/postgresql/17/bin' / name) != recorded:
            raise RuntimeError('one of four existing PostgreSQL binaries changed')
    for name, recorded in pginputs['source_inputs']['server_private_libraries'].items():
        if digest(pgroot / name) != recorded:
            raise RuntimeError('recorded PostgreSQL private library changed')
    if digest(OUT / 'canon-pg-driver-install-3.2.9-2026-10-09.json') != pginputs['source_inputs']['driver_install_receipt']:
        raise RuntimeError('exact private driver install receipt changed')
    for suffix in ('-inputs.json', '.log', '.xml', '-server.log', '-debian-signatures.txt', '.json'):
        path = Path(str(pgstem) + suffix)
        expected = pg.get(suffix + '_sha256')
        if expected and sha(path) != expected:
            raise RuntimeError('original PostgreSQL artifact changed')
        receipts[str(path)] = digest(path)
    # This explicit scope scan is supplementary to equal source bytes and reviewed reads.
    # Native services reach only unchanged standalone stream/control backend helpers.
    scope_dirs = ['trading', 'services', 'hermes', 'tests/hermes', 'tests/scenarios', 'tools/hermes']
    pattern = r'task_scope|van-browser-core/browser/(harness_service|egress_proxy)|harness_service\.py|url_vectors\.v1|test_harness_pseudo_hit_ownership|test_task_scope_shared_url_rule'
    scan = subprocess.run(['rg', '-n', pattern, *scope_dirs, '--glob', '*.py', '--glob', '*.sh'], cwd=args.repo, capture_output=True, text=True)
    if scan.returncode not in (0, 1):
        raise RuntimeError('component reference scan failed')
    matches = scan.stdout.splitlines()
    if any(not line.startswith('trading/tests/test_browser_worker_deployment.py:') for line in matches):
        raise RuntimeError('new parser/Harness reference in retained component scope')
    if not all(snapshot(repo, revision) == before for repo, revision, before in
               ((BASE, BASE_SHA, base), (PREVIOUS, PREVIOUS_SHA, previous), (args.repo, args.revision, child))):
        raise RuntimeError('source changed during scoped proof')
    proof = {
        'schema_version': 1, 'recorded_at_utc': dt.datetime.now(dt.UTC).isoformat(),
        'scope': 'retained805f execution inputs with18 affected consumer cases freshly replaced; no whole-child component-suite claim',
        'measured_retained_execution_revision': BASE_SHA, 'previous_equivalent_child_revision': PREVIOUS_SHA,
        'reviewed_child_revision': args.revision, 'child_checkout': str(args.repo),
        'fresh_child_trading_counts': fresh['counts'], 'fresh_child_consumer_execution_result': str(fresh_stem) + '-result.json',
        'retained805f_counts': {'trading_except_affected_consumers': counts(remaining),
            'hermes-scenarios': original['hermes-scenarios']['result']['counts'],
            'native-browser-services': original['native-browser-services']['result']['counts'],
            'actual-postgres': pg['counts']},
        'excluded_retained_trading_consumers': CONSUMERS, 'excluded805f_trading_cases': excluded,
        'remaining_retained805f_trading_cases': remaining,
        'retained_scope_child_whole_suite_runs': 0, 'retained_scope_child_postgres_runs': 0,
        'source_unchanged_during_proof': True, 'unchanged_byte_and_git_mode_count': len(unchanged),
        'unchanged_bytes_git_and_checkout_mode_count': len(retained),
        'retained_inputs': {name: base['tree'][name] for name in retained},
        'historical_document_checkout_only_mode_differences': permission_differences,
        'reviewed_total805f_to_child_changes': {name: {'base': base['tree'].get(name), 'child': child['tree'].get(name)} for name in sorted(total_changes)},
        'reviewed_ffa18_to_child_changes': {name: {'previous': previous['tree'].get(name), 'child': child['tree'].get(name)} for name in sorted(child_changes)},
        'reviewed_runtime_regression_paths': sorted(RUNTIME_REGRESSIONS),
        'registry_differences_limited_to_review_pointers': registry_differences,
        'guide_only_review_pointer_changed': True, 'ledger_preserves_history_and_appends_one_uncovered_row': True,
        'manifest_source_only_with_all_cited_file_hashes_verified': {'path': manifest_path, 'file_count': len(manifest['files']), 'additional_inputs': manifest['additional_review_inputs']},
        'scope_reference_scan': {'pattern': pattern, 'directories': scope_dirs, 'matches': matches},
        'dependency_review': {
            'affected_trading_harness_reader': 'test_browser_worker_deployment reads/imports the changed Harness',
            'affected_trading_scope_reader': 'test_jev_architecture_boundary scans the browser source tree and imports models/interaction_router→task_scope',
            'native_service_backend_imports': ['input_protocol', 'flood_bounds', 'stream_grants', 'agent_grant'],
            'native_deployment_reads': 'deploy/van-browser-stream only, not changed browser-core',
            'hermes_scenario_reads': 'unchanged hermes/tools/hermes/trading and existing registry/profile inputs',
            'actual_postgres_reads': 'unchanged trading fixture/ledger implementation; no browser-core input',
        },
        'freshly_rechecked_recorded_dds_and_component_toolchains': True,
        'freshly_rechecked_exact_private_pg_driver_libraries_and_four_server_binaries': True,
        'recorded_original_actual_pg_runtime': pg['observed_runtime'],
        'prior805f_to_ffa18_proof': digest(OLD_PROOF), 'proof_helper': digest(HELPER),
        'producer': digest(Path(__file__)), 'execution_receipt_artifacts': receipts,
        'handset_cases_executed': 0, 'live_production_qualified': False,
        'limits': ['Retained counts are actual805f executions, not newly executed child suites.',
                   'Only18 affected trading cases were freshly executed on the child; no whole1485 trading-pass claim is promoted.',
                   'Changed browser-core/parser/geometry paths require independent actual backend/browser and contract execution receipts.',
                   'Recorded source/dependency facts are compared; unrecorded operating-system state and production/handset are outside this proof.'],
    }
    target.write_text(json.dumps(proof, indent=2, sort_keys=True) + '\n')
    print(json.dumps({key: proof[key] for key in ('reviewed_child_revision', 'fresh_child_trading_counts', 'retained805f_counts', 'source_unchanged_during_proof')}))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
