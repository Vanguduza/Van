"""Select a finite reviewed set; never recursively archive a workspace or secrets."""
from pathlib import Path
import hashlib
import json

out = Path('/workspace/van-audit')
setup = Path('/workspace/.onboarding')
revision = 'dfc1557ab99ad8d41cf84714e1bb671e89b045e6'
records = {}

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def add(name, kind, section, parent=out, expected=None):
    path = parent / name
    assert path.is_file() and path.resolve() == path
    if expected is not None:
        assert sha(path) == expected
    archive_name = section + '/' + name
    assert archive_name not in records
    records[archive_name] = {'kind': kind, 'path': str(path),
                             'archive_path': archive_name, 'reviewed_sha256': sha(path)}

def suite(stem, section):
    for suffix, kind in [('-inputs.json', 'input_manifest'), ('-result.json', 'qualification_receipt'),
                         ('.log', 'test_log'), ('.xml', 'junit')]:
        add(stem + suffix, kind, section)

for stem in ['canon-corrected-backend-full-dfc1557a-2026-10-09',
             'canon-final-contracts-dfc1557a-2026-10-09']:
    suite(stem, 'final-suites')
for name, kind in [
    ('canon-corrected-android-dfc1557a-2026-10-09-inputs.json', 'input_manifest'),
    ('canon-corrected-android-dfc1557a-2026-10-09-result.json', 'qualification_receipt'),
    ('canon-corrected-android-dfc1557a-2026-10-09-1.log', 'test_log'),
    ('canon-corrected-android-dfc1557a-2026-10-09-2.log', 'test_log'),
    ('canon-corrected-android-dfc1557a-2026-10-09-apk-badging.txt', 'public_apk_metadata'),
    ('canon-corrected-android-dfc1557a-2026-10-09-apk-signer.txt', 'public_apk_metadata'),
    ('canon-corrected-android-dfc1557a-2026-10-09-native-alignment.json', 'qualification_receipt'),
    ('canon-corrected-android-dfc1557a-2026-10-09-zipalign.log', 'test_log'),
    ('canon-android-apk-content-layout-dfc1557a-2026-10-09.json', 'qualification_receipt'),
    ('canon-android-apk-dex-layout-dfc1557a-2026-10-09.json', 'qualification_receipt'),
    ('CANON_ANDROID_FINAL_QUALIFICATION_DFC1557A_2026-10-09.md', 'audit_report'),
]:
    add(name, kind, 'android')

proof_name = 'component-scope-equivalence-805f-to-final-dfc1557a-2026-10-09.json'
proof = json.loads((out / proof_name).read_text())
assert proof['reviewed_child_revision'] == revision
for path_text, observed in sorted(proof['execution_receipt_artifacts'].items()):
    path = Path(path_text)
    assert path.parent == out
    if path.name.endswith('-debian-signatures.txt'):
        kind = 'package_signature_proof'
    else:
        kind = {'.json': 'input_manifest' if path.name.endswith('-inputs.json') else 'qualification_receipt',
                '.log': 'test_log', '.xml': 'junit'}[path.suffix]
    add(path.name, kind, 'components', expected=observed['sha256'])
add(proof_name, 'qualification_receipt', 'components')
add('components-final-805f3b67-2026-10-09.json', 'qualification_receipt', 'components')

for name, kind in [
    ('canon-registry-and-native-contracts-qualification-2026-10-09-r7.json', 'qualification_receipt'),
    ('canon-registry-r7-before-tests-inputs-2026-10-09.json', 'input_manifest'),
    ('canon-registry-r7-reviewed-runtime-freeze-2026-10-09.json', 'input_manifest'),
    ('canon-current-registry-contracts-2026-10-09-r7.xml', 'junit'),
    ('canon-native-plan-contracts-2026-10-09-r7.xml', 'junit'),
    ('canon-native-826-source-fixture-proof-2026-10-09-r7.json', 'qualification_receipt'),
    ('NATIVE_ARTEMIS_SCHEMA_FIXTURE_NOT_DISCOVERY_2026-10-09-r7.json', 'input_manifest'),
    ('VAN_NATIVE_ARTEMIS_SOURCE_FIXTURE_PLAN_2026-10-09-r7.json', 'audit_report'),
]:
    add(name, kind, 'registry-proof')
export = json.loads((out / 'VAN_OWNER_REGISTRY_EXPORT_DFC1557A_2026-10-09.json').read_text())
assert export['source_sha'] == revision
for name in [
    'VAN_OWNER_FEATURES_DFC1557A_2026-10-09.json', 'VAN_OWNER_SCREENS_DFC1557A_2026-10-09.json',
    'VAN_OWNER_ENDPOINTS_DFC1557A_2026-10-09.json', 'VAN_OWNER_ENDPOINT_SCHEMAS_DFC1557A_2026-10-09.json',
    'VAN_OWNER_FRONTEND_CONTRACT_DFC1557A_2026-10-09.html', 'VAN_OWNER_REGISTRY_GUIDE_DFC1557A_2026-10-09.md',
    'VAN_OWNER_REGISTRY_SOURCE_REVIEW_R7_DFC1557A_2026-10-09.json',
    'VAN_OWNER_REGISTRY_EXPORT_DFC1557A_2026-10-09.json',
]:
    add(name, 'frontend_registry', 'frontend')

suite('canon-corrected-backend-full-805f3b67-2026-10-09', 'original-failed-diagnostics')
suite('canon-chromium-combined-scoped-2026-10-09', 'browser-runtime')
suite('harness-pseudo-hit-ownership-selected-contracts-r2-2026-10-09', 'browser-runtime')
for name in ['canon-chromium-parser-source-fix-2026-10-09.json', 'canon-chromium-parser-real-browser-2026-10-09.json']:
    add(name, 'qualification_receipt', 'browser-runtime')
for name in ['canon-chromium-parser-boundary-red-2026-10-09.xml', 'canon-chromium-parser-boundary-final-2026-10-09.xml']:
    add(name, 'junit', 'browser-runtime')

for name, kind in [
    ('canon-setup-full-install-dfc1557a-2026-10-09-inputs.json', 'input_manifest'),
    ('canon-setup-full-install-dfc1557a-2026-10-09-after.json', 'input_manifest'),
    ('canon-setup-full-install-dfc1557a-2026-10-09-result.json', 'qualification_receipt'),
    ('canon-setup-full-install-dfc1557a-2026-10-09.log', 'test_log'),
    ('canon-final-cloud-setup-draft-save-dfc1557a-2026-10-09.json', 'qualification_receipt'),
]:
    add(name, kind, 'cloud-setup')
add('reusable-install-canon-dfc1557a-2026-10-09.sh', 'setup_script', 'cloud-setup', setup)
add('canon-start-skill-dfc1557a-r2-2026-10-09.md', 'setup_start_skill', 'cloud-setup', setup)
for name in ['canon-setup-inputs-and-public-cache-dfc1557a-2026-10-09.json',
             'canon-setup-subset-verification-dfc1557a-r1-2026-10-09-result.json']:
    add(name, 'setup_receipt', 'cloud-setup', setup)

for name, kind in [
    ('canon-source-publication-dfc1557a-2026-10-09.json', 'qualification_receipt'),
    ('VAN_CANON_SOURCE_DFC1557A_2026-10-09.bundle', 'source_bundle'),
    ('VAN_CANON_SOURCE_DFC1557A_2026-10-09_BUNDLE_VERIFICATION.json', 'qualification_receipt'),
    ('VAN_FINAL_QUALIFICATION_REVIEW_dfc1557a_2026-10-09.json', 'audit_report'),
    ('VAN_FINAL_QUALIFICATION_REVIEW_dfc1557a_2026-10-09.md', 'audit_report'),
    ('VAN_FINAL_DIRECT_DIAL_CONTINUATION_2026-10-09_dfc1557a.json', 'audit_report'),
    ('VAN_FINAL_DIRECT_DIAL_CONTINUATION_PROMPT_2026-10-09_dfc1557a.md', 'audit_report'),
    ('VAN_FINAL_DIRECT_DIAL_CONTINUATION_SOURCE_RECEIPT_2026-10-09_dfc1557a.json', 'qualification_receipt'),
    ('VAN_PRE_PHONE_CANARY_CHECKLIST_DFC1557A_2026-10-09.md', 'audit_report'),
    ('van-pre-phone-canary-source-and-skip-inventory-dfc1557a-2026-10-09.json', 'input_manifest'),
    ('VAN_CLOUD_RUNTIME_CAPABILITY_OBSERVATION_2026-10-09-r2.json', 'qualification_receipt'),
]:
    add(name, kind, 'review-and-handoff')

for name in [
    'prepare_canon_final_qualification_report_2026_10_09.py', 'prepare_final_dial_continuation_runtime_2026_10_09.py',
    'package_canon_final_evidence_2026_10_09.py', 'publish_canon_final_evidence_2026_10_09.py',
    'publish_canon_source_2026_10_09.py', 'run_canon_full_setup_2026_10_09.py',
    'run_canon_corrected_backend_qualification_2026_10_09.py', 'qualify_canon_android_2026_10_09.py',
    'qualify_canon_android_native_alignment_2026_10_09.py', 'compare_canon_android_apk_coverage_dfc1557a_2026_10_09.py',
    'qualify_committed_components_shorttmp_2026_10_09.py', 'prove_parser_child_component_scope_2026_10_09.py',
    'prepare_registry_r7_qualification_2026_10_09.py', 'finish_registry_r7_qualification_2026_10_09.py',
    'refresh_current_canon_registry_2026_10_09_r7.py', 'qualify_canon_chromium_parser_2026_10_09.py',
    'run_canon_chromium_scope_qualification_2026_10_09.py', 'run_pseudo_hit_contracts_r2_2026_10_09.py',
    'refresh_pre_phone_dfc1557a_2026_10_09.py',
]:
    add(name, 'helper_source', 'producers')

spec = {'record_kind': 'FINITE_REVIEWED_PUBLIC_EVIDENCE_SELECTION', 'source_sha': revision,
        'files': list(records.values()), 'physical_cases_executed': 0,
        'production_deployed': False, 'all_contracts_pass': False,
        'notice': 'Public source/controlled qualification only. No APK, weights, private owner files, uploads or credentials.'}
target = out / 'canon-final-evidence-packet-spec-dfc1557a-2026-10-09.json'
with target.open('x') as stream:
    json.dump(spec, stream, indent=2, sort_keys=True)
    stream.write('\n')
print(json.dumps({'spec_path': str(target), 'sha256': sha(target), 'selected_file_count': len(records),
                  'selected_original_bytes': sum(Path(r['path']).stat().st_size for r in records.values())}))
