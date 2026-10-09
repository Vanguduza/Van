"""Summarize original completed receipts; never infer production/phone acceptance."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('root', type=Path)
parser.add_argument('revision')
parser.add_argument('component_proof', type=Path)
parser.add_argument('setup_result', type=Path)
parser.add_argument('draft_result', type=Path)
args = parser.parse_args()
root = args.root.resolve()
out = Path('/workspace/van-audit')
revision = args.revision
short = revision[:8]

def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def read(path):
    path = Path(path)
    return json.loads(path.read_text()), {'path': str(path), 'sha256': sha(path)}

def git(*words):
    return subprocess.check_output(['git', '-C', str(root), *words], text=True).strip()

assert git('rev-parse', 'HEAD') == revision and not git('status', '--porcelain=v1')
backend, backend_ref = read(out / f'canon-corrected-backend-full-{short}-2026-10-09-result.json')
contracts, contracts_ref = read(out / f'canon-final-contracts-{short}-2026-10-09-result.json')
android, android_ref = read(out / f'canon-corrected-android-{short}-2026-10-09-result.json')
native, native_ref = read(out / f'canon-corrected-android-{short}-2026-10-09-native-alignment.json')
apk_contents, apk_contents_ref = read(out / f'canon-android-apk-content-layout-{short}-2026-10-09.json')
publication, publication_ref = read(out / f'canon-source-publication-{short}-2026-10-09.json')
affected, affected_ref = read(out / f'committed-trading-affected-parser-consumers-final-{short}-2026-10-09-result.json')
components, components_ref = read(args.component_proof)
setup, setup_ref = read(args.setup_result)
draft, draft_ref = read(args.draft_result)
registry, registry_ref = read(out / 'canon-registry-and-native-contracts-qualification-2026-10-09-r7.json')
fixture, fixture_ref = read(out / 'canon-native-826-source-fixture-proof-2026-10-09-r7.json')
focused, focused_ref = read(out / 'canon-chromium-combined-scoped-2026-10-09-result.json')
review, review_ref = read(root / 'docs/audit/VAN_OWNER_REGISTRY_SOURCE_REVIEW_2026-10-09-r7.json')
for receipt in (backend, contracts, android, native, affected):
    assert receipt['revision'] == revision
assert backend['complete_run'] and backend['qualified_as_full_backend_pass']
assert backend['source_unchanged_during_test'] and backend['installed_dependencies_unchanged_during_test']
assert not backend['counts']['failed'] and not backend['counts']['errors']
assert contracts['complete_run'] and contracts['source_unchanged'] and contracts['installed_dependencies_unchanged'] and contracts['external_dds_unchanged']
assert contracts['counts']['failed'] == 1 and contracts['counts']['errors'] == 0
assert len(contracts['failure_details']) == 1
assert contracts['failure_details'][0]['name'] == 'test_the_real_branch_verifies_at_head'
assert 'project_truth' in contracts['failure_details'][0]['class'].lower()
assert android['qualified_as_android_debug_source_pass'] and android['source_unchanged_during_run']
assert native['qualified_16kb_native_alignment'] and affected['qualified']
assert native['apk']['sha256_before'] == native['apk']['sha256_after'] == android['apk']['sha256']
assert apk_contents['revision'] == revision and apk_contents['apks_unchanged_during_comparison']
assert apk_contents['source_pinned_voice_files_and_manifest_verified']
assert apk_contents['generic_weights_verified'] == 45 and apk_contents['voice_entries_verified'] == 46
assert apk_contents['all_seven_native_libraries_byte_identical_and_16k_qualified']
assert apk_contents['new_qualified_receipt_sha256'] == android_ref['sha256']
assert components['reviewed_child_revision'] == revision and components['source_unchanged_during_proof']
assert components['measured_retained_execution_revision'] == '805f3b67c2b9eb68d887cd700f9443f476e26132'
assert components['fresh_child_trading_counts'] == affected['counts']
assert components['fresh_child_consumer_execution_result'] == affected_ref['path']
assert set(components['excluded_retained_trading_consumers']) == {
    'trading/tests/test_browser_worker_deployment.py', 'trading/tests/test_jev_architecture_boundary.py',
}
assert len(components['excluded805f_trading_cases']) == 18
assert components['retained_scope_child_whole_suite_runs'] == components['retained_scope_child_postgres_runs'] == 0
assert publication['source_sha'] == revision and publication['publication'] == 'NEW_REVIEW_BRANCH_VERIFIED'
assert setup['source_sha'] == revision and setup['completed_successfully']
assert draft['status'] == 'saved' and draft['application_sha'] == revision
assert focused['scoped_checks_passed'] and focused['all_bound_source_bytes_modes_unchanged']
focused_inputs_path = Path(focused['input_manifest'])
assert sha(focused_inputs_path) == focused['input_manifest_sha256']
focused_inputs = json.loads(focused_inputs_path.read_text())
for name in (
    'backend/van_gateway/browser/task_scope.py', 'deploy/van-browser-core/browser/harness_service.py',
    'deploy/van-browser-core/browser/egress_proxy.py', 'backend/tests/fixtures/task_scope/url_vectors.v1.json',
    'tests/contracts/test_task_scope_shared_url_rule.py', 'backend/tests/test_harness_pseudo_hit_ownership.py',
):
    current = root / name
    assert focused_inputs['files'][name] == {
        'sha256': sha(current), 'bytes': current.stat().st_size,
        'mode': oct(current.stat().st_mode & 0o777),
    }
assert sorted(result['tests'] for result in registry['results']) == [19, 39]
assert all(result['failures'] == result['errors'] == result['skipped'] == 0 for result in registry['results'])
assert all(sha(root / name) == digest for name, digest in review['files'].items())
assert fixture['physical_cases_executed'] == 0 and not fixture['actual_native_schema_discovery']
counts = registry['counts']
assert counts == {'features': 42, 'functions': 105, 'surfaces': 78, 'endpoints': 432, 'schemas': 251}

def case_counts(value):
    return {key: value[key] for key in ('passed', 'failed', 'errors', 'skipped')}

report = {
    'record_kind': 'FINAL_APPLICATION_SOURCE_AND_LOCAL_QUALIFICATION_REVIEW',
    'created_at_utc': datetime.now(timezone.utc).isoformat(),
    'application_sha': revision, 'application_checkout': str(root),
    'source_status': 'SOURCE_AND_CONTROLLED_RUNTIME_CHECKS_QUALIFIED_ADMISSION_AND_LIVE_GATES_PENDING',
    'source_branch': publication['branch'], 'source_publication': publication_ref,
    'source_publication_readback_file_count': publication['verified_file_count'],
    'source_merged_to_main': False, 'production_deployed': False,
    'topology': {'version': 'CORE_ONLY_V2', 'gateway': 'van-trading-core', 'product_hermes_profile_van': 'van-trading-core', 'native_artemis_direct': 'dial-control'},
    'in_app_connection_configuration_required_by_owner_release_contract': False,
    'owner_connection_release_live_qualified': False,
    'qualification': {
        'full_backend': {'executed_revision': revision, 'counts': backend['counts'], 'receipt': backend_ref, 'complete': True, 'source_and_dependencies_unchanged': True, 'skips': backend['skips']},
        'full_contracts': {'executed_revision': revision, 'counts': contracts['counts'], 'receipt': contracts_ref, 'all_contracts_pass': False, 'failure_details': contracts['failure_details'], 'skip_details': contracts['skip_details'], 'source_dds_and_dependencies_unchanged': True},
        'android': {'executed_revision': revision, 'host_jvm': case_counts(android['host_jvm']), 'app_unit': case_counts(android['android_app_unit']), 'lint': android['lint'], 'receipt': android_ref, 'apk': android['apk'], 'embedded_provenance': android['public_apk_provenance'], 'instrumentation_compiled': android['instrumentation_compiled'], 'instrumentation_executed': False, 'owner_release_built': False},
        'android_actual_native_alignment': {'executed_revision': revision, 'native_library_count': len(native['native_libraries']), 'qualified_16kb_native_alignment': True, 'receipt': native_ref},
        'android_actual_packaged_voice_and_native_assets': {'executed_revision': revision, 'generic_weights_verified': 45, 'voice_entries_including_manifest_verified': 46, 'native_libraries_verified': 7, 'receipt': apk_contents_ref, 'debug_only': True},
        'affected_trading_consumers': {'executed_revision': revision, 'counts': affected['counts'], 'receipt': affected_ref},
        'retained_component_scopes': {'original_execution_revision': components['measured_retained_execution_revision'], 'retained_original_counts': components['retained805f_counts'], 'fresh_child_trading_counts': components['fresh_child_trading_counts'], 'excluded_retained_trading_consumers': components['excluded_retained_trading_consumers'], 'scope_proof': components_ref, 'interpretation': 'Only unchanged, explicitly mapped inputs/cases retain their original execution evidence. No complete component rerun on the child is claimed.'},
        'focused_changed_browser_runtime': {'execution_identity': 'Reviewed uncommitted source vector based on ffa18; exact frozen runtime bytes later committed in this candidate', 'counts': focused['counts'], 'receipt': focused_ref, 'overlaps_full_backend_and_contracts': True},
        'registry_and_native_contracts': {'receipt': registry_ref, 'review_manifest': review_ref, 'reviewed_inputs': len(review['files']), 'current_citations_verified': registry['current_source_citations_hash_verified'], 'historical_containers_preserved': registry['original_baseline_historical_containers_preserved']},
    },
    'registry': counts,
    'native_artemis_candidate_matrix': {'coverage': fixture['coverage'], 'case_kinds': fixture['case_kinds'], 'source_fixture_proof': fixture_ref, 'actual_native_schema_discovery': False, 'physical_cases_executed': 0, 'physical_total': 826},
    'cloud_setup': {'actual_install': setup_ref, 'draft_save': draft_ref, 'draft_saved': True, 'configuration_activated': False, 'fresh_task_restoration_tested': False, 'settings_action': 'Remove the obsolete unbound diagnostic DIAL_MCP_ACCESS_TOKEN requirement when reviewing/saving and publishing. The tested installer does not use it, and the draft API explicitly permits removal only in the review UI. It is separate from native DIAL admin authentication.'},
    'remaining_live_gates': [
        'Exact owner first adoption of PR94 framework, followed by separate trusted application authorization intake/admission; no blanket approval or baseline reset.',
        'Existing protected production signer, CORE_ONLY_V2 deployment/profile/trust/connectivity/provisioning bindings and rollback readback.',
        'Actual van-trading-core service/provider/ingress/TLS and privileged IPv4/IPv6/NAT/firewall qualification; host-health-only receipts are insufficient.',
        'Joined PRE_PHONE_PASS before any phone effect, then fresh direct native Artemis schemas, paired private wireless endpoint, raw serial/model and all 826 physical cases.',
    ],
    'limits': [
        'Suite scopes overlap and are never summed into a single pass count.',
        'Earlier failed/interrupted runs remain original historical diagnostics; the new complete backend run is independently bound to this SHA.',
        'This APK is debug signed; embedded source/connection provenance and 16KiB alignment do not qualify production signer/profile or live connectivity.',
        'Current cloud tools do not expose DIAL, Commander or Artemis. This is a tool-availability limit, not a claim about the separate owner MCP admin authentication.',
        'Saving a tested setup draft does not activate a configuration or prove a new-task restoration.',
    ],
    'producer': {'path': str(Path(__file__)), 'sha256': sha(Path(__file__))},
}
machine_path = out / f'VAN_FINAL_QUALIFICATION_REVIEW_{short}_2026-10-09.json'
human_path = out / f'VAN_FINAL_QUALIFICATION_REVIEW_{short}_2026-10-09.md'
with machine_path.open('x') as stream:
    json.dump(report, stream, indent=2, sort_keys=True)
    stream.write('\n')
human = f'''# VAN final source and local qualification

Application source `{revision}` is published on `{publication['branch']}`. The corrected application passes its complete backend run and Android checks. Project Truth admission and actual production-host acceptance remain unresolved; physical handset execution is **0/826**. Main was not merged and no production service or handset was changed by this cloud work.

| Scope | Actual result | Scope limit |
|---|---|---|
| Full backend at `{short}` | {backend['counts']['passed']:,} passed, {backend['counts']['skipped']} skipped; no failures/errors | Five explicit applicability/environment skips; controlled services and real Chromium, not production-host acceptance |
| Full contracts at `{short}` | {contracts['counts']['passed']:,} passed, one Project Truth history failure, {contracts['counts']['skipped']} privileged kernel skips | Admission stays RED; no firewall proof inferred from skips |
| Android at `{short}` | {android['host_jvm']['passed']:,} JVM + {android['android_app_unit']['passed']} app tests; lint {android['lint']['Error']} errors/{android['lint']['Warning']} warnings | Debug APK; instrumentation assembled, unexecuted |
| Actual APK native alignment | All {len(native['native_libraries'])} arm64 libraries and SDK zipalign passed 16KiB checks | No production signer/profile or handset qualification |
| Affected trading consumers at `{short}` | {affected['counts']['passed']} passed | Remaining component evidence retained through separate explicit input/case equivalence on 805f |
| Registry and native source contracts | 19 + 39 passed; {len(review['files'])} source inputs bound | Synthetic native schema; no actual discovery or handset evidence |

The code corrections enforce typed automation predicates; safe terminal SSE refusal and cancellation cleanup; independent browser profile egress; non-public IP refusal; signed APK source/connection provenance; resident Android deep-link navigation; strict installer/native handset identity; and honest legacy authority and qualifier diagnostics. The final Chromium fixes preserve encoded dots in ordinary path segments while refusing ambiguous separators, and accept only fresh direct own-pseudo hits while retaining overlay, nested-control, binding and event guards. Their combined 655-case scoped run and original failing-case receipts remain separately bound and overlap the complete runs.

The frontend design registry supplies **42 feature groups, 105 functions, 78 surfaces, 432 endpoints and 251 schema components**. Its 5,230 current citations and 588 original historical containers are preserved. Use the [registry guide](https://github.com/Vanguduza/Van/blob/{revision}/docs/audit/OWNER_FRONTEND_REGISTRY_GUIDE.md) and searchable contract for the redesign. The native 826-case source matrix covers happy, error, refusal and recovery paths; all physical execution remains pending.

CORE_ONLY_V2 places gateway and product Hermes profile `van` on **van-trading-core**, with direct native Artemis on **dial-control**, outside Hermes engineering actuation. The genuine owner release and signed provisioning path supplies Android's connection values; it has no owner-facing host/token/CA/model configuration. The cloud-built debug artifact retains its historical debug profile and is not an install candidate for owner acceptance. Its SHA256 is `{android['apk']['sha256']}`.

Reusable setup was executed against an independent exact-source HTTPS checkout, and complete `install_script` / `start_skill` contents were saved as a draft. Review/save and publish through environment settings to activate it. Remove the obsolete unbound `DIAL_MCP_ACCESS_TOKEN` requirement during that review: the tested installer does not use it, and the draft API only permits removal in the review UI. This requirement is separate from native DIAL admin authentication. Existing original checkouts were preserved; neither draft saving nor this independent checkout test proves fresh-task snapshot restoration.

Before S24 testing, the existing tool-enabled DIAL session must independently locate protected production bindings, complete source admission, produce owner-signed release/provisioning and rollback evidence, and qualify actual services/providers/TLS/ingress/kernel fences. Join those matching original receipts into PRE_PHONE_PASS before any phone effect. Then refresh the paired private wireless endpoint and require raw serial `RFCX2054F5W` and raw model `SM-S928B`; the old endpoint and sanitized device-list model are insufficient. Execute all 826 cases with native traces and independent effect/refusal readbacks.

The repository's [first-adoption instruction](https://github.com/Vanguduza/Van/blob/296d647d8755b6036ddb6bc66a5526b78db07029/tools/ci/README.md#L162-L168) says: “The first landing of this change is therefore the owner's explicit act (merge with the old check red, or a direct push by the integrator), once.” PR94 at exact 296d647d8755b6036ddb6bc66a5526b78db07029 is framework-only. It does not approve application history or all 28 authorization records; separate trusted intake remains required. No authorization, signed approval or enforcement baseline was invented here.

The [machine report]({machine_path.name}) links original result/input/log/JUnit receipts and explicit equivalence scopes. Counts are not added across overlapping runs. Earlier diagnostics remain intact.
'''
with human_path.open('x') as stream:
    stream.write(human)
print(json.dumps({'machine_report': str(machine_path), 'machine_sha256': sha(machine_path), 'human_report': str(human_path), 'human_sha256': sha(human_path), 'application_sha': revision}))
