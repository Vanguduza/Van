#!/usr/bin/env python3
"""Produce immutable exact-source continuation after final checks are supplied.

Inputs are the parent's actual qualification report and, if already available,
its measured publication receipt. This helper performs no live or phone action.
"""
from pathlib import Path
import copy
import datetime
import hashlib
import json
import os
import re
import stat
import subprocess
import sys

ROOT = Path('/workspace/van-audit/canon-chromium-runtime-fix-2026-10-09')
OUT = ROOT.parent
expected = sys.argv[1]
qualification_path = Path(sys.argv[2]).resolve()
qualification = json.loads(qualification_path.read_text())
publication_path = Path(sys.argv[3]).resolve() if len(sys.argv) > 3 else None
publication = json.loads(publication_path.read_text()) if publication_path else None
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()

def tracked_snapshot():
    names = subprocess.check_output(['git', '-C', str(ROOT), 'ls-files', '-z']).decode().split('\0')
    measured = {}
    for name in filter(None, names):
        path = ROOT / name
        data = os.readlink(path).encode() if path.is_symlink() else path.read_bytes()
        measured[name] = {
            'sha256': hashlib.sha256(data).hexdigest(),
            'filesystem_mode_octal': oct(stat.S_IMODE(path.lstat().st_mode)),
            'is_symlink': path.is_symlink(),
        }
    return measured

assert re.fullmatch('[0-9a-f]{40}', expected)
assert subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD']).decode().strip() == expected
assert not subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain', '--untracked-files=all']).decode().strip()
before_tracked = tracked_snapshot()
# The parent report must explicitly bind this application identity. Its actual
# individual execution/equivalence scopes are copied, never inferred or summed.
assert qualification.get('application_sha') == expected
review_path = ROOT / 'docs/audit/VAN_OWNER_REGISTRY_SOURCE_REVIEW_2026-10-09-r7.json'
review = json.loads(review_path.read_text())
assert all(sha(ROOT / f) == h for f, h in review['files'].items())
prior_path = OUT / 'VAN_FINAL_DIRECT_DIAL_CONTINUATION_2026-10-09_ffa18d57.json'
prior = json.loads(prior_path.read_text())
prior_outputs = {p.name: sha(p) for p in OUT.glob('VAN_FINAL_DIRECT_DIAL_CONTINUATION*') if p.is_file()}
machine = copy.deepcopy(prior)
machine['created_at_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
machine['application_sha'] = expected
machine['supersedes_source_selection_only'] = {
    'prior_application_sha': prior['application_sha'],
    'prior_handoff_outputs_preserved': True,
    'selection_change': 'The final runtime child preserves encoded dots in ordinary Chromium path segments, retains fail-closed ambiguous separator handling, and resolves fresh direct CDP hit ownership for native pseudo-element geometry. R7 binds the reviewed runtime/regression inputs. Read the supplied actual qualification report for each executed SHA and any separately measured equivalence scope; no earlier whole-suite result is silently relabelled.',
}
machine['registry_review'] = {
    'path': str(review_path.relative_to(ROOT)),
    'sha256': sha(review_path),
    'source_input_count': len(review['files']),
    'inventory': {'features': 42, 'functions': 105, 'surfaces': 78, 'endpoints': 432, 'schemas': 251},
}
machine['full_local_checks'] = {
    'status': 'ACTUAL_SOURCE_BOUND_PARENT_REPORT_SUPPLIED_WITH_REPORTED_LIMITS',
    'report_path': str(qualification_path),
    'report_sha256': sha(qualification_path),
    'actual_report': qualification,
    'scope': 'Use each original suite receipt and its exact execution/input identity. Preserve all failures, skips, interrupted diagnostics and separate equivalence scopes. Local source tests and a debug APK do not qualify production deployment, owner signing or physical Artemis execution.',
}
machine['publication_status'] = 'ACTUAL_PARENT_PUBLICATION_RECEIPT_SUPPLIED' if publication else 'NOT_OBSERVED_BY_THIS_HANDOFF_PRODUCER'
machine['remote_publication_and_host_source_availability_verified'] = False
machine['remote_git_source_publication_verified'] = bool(publication and publication.get('publication') == 'NEW_REVIEW_BRANCH_VERIFIED' and publication.get('source_sha') == expected)
machine['actual_production_host_source_availability_verified'] = False
machine['exact_https_source_locator'] = 'https://github.com/Vanguduza/Van/tree/' + expected
bundle_receipt_path = OUT / 'VAN_CANON_SOURCE_DFC1557A_2026-10-09_BUNDLE_VERIFICATION.json'
bundle_receipt = json.loads(bundle_receipt_path.read_text())
assert bundle_receipt['source_sha'] == expected and bundle_receipt['verify_exit_code'] == 0
assert sha(Path(bundle_receipt['bundle_path'])) == bundle_receipt['bundle_sha256']
machine['source_bundle_locator'] = {
    'path': bundle_receipt['bundle_path'], 'sha256': bundle_receipt['bundle_sha256'],
    'required_base_sha': bundle_receipt['required_base_sha'],
    'verification_receipt': {'path': str(bundle_receipt_path), 'sha256': sha(bundle_receipt_path)},
    'scope': 'Actual verified incremental Git source transport, separate from host admission and live acceptance.',
}
machine['publication_receipt'] = {'path': str(publication_path), 'sha256': sha(publication_path), 'actual_receipt': publication} if publication else None
machine['source_inputs_sha256'] = {f: sha(ROOT / f) for f in prior['source_inputs_sha256']}
for f in ('backend/van_gateway/browser/task_scope.py', 'deploy/van-browser-core/browser/harness_service.py', 'deploy/van-browser-core/browser/egress_proxy.py', str(review_path.relative_to(ROOT))):
    machine['source_inputs_sha256'][f] = sha(ROOT / f)
latest_report = Path('/workspace/attachments/510d0b16-3ed9-4118-9e38-a17274613b54/Pasted text.txt')
if latest_report.is_file():
    machine['uploaded_report_inputs'].append({'path': str(latest_report), 'sha256': sha(latest_report), 'scope': 'Historical external DIAL/Commander observations, not fresh final-source host/device evidence.'})
machine['gates'][0] = {
    'id': 'G0_EXACT_SOURCE_AND_LOCAL_QUALIFICATION',
    'status': 'ACTUAL_LOCAL_REPORT_SUPPLIED_LIVE_SOURCE_RECOVERY_AND_ADMISSION_STILL_REQUIRED',
    'requires': [
        'Recover exact clean object ' + expected + ' on the estate and independently verify source transport/hash identity.',
        'Read the supplied actual parent report and original receipts, including each executed SHA/equivalence scope, unresolved Project Truth admission and privileged-check skips. Do not silently relabel earlier whole-suite runs as this source.',
        'An integration/merge that changes the selected source SHA requires its own exact-source qualification and rebuilt release APK with matching embedded provenance; an older APK cannot be relabelled.',
    ],
}
composite = next(gate for gate in machine['gates'] if gate['id'] == 'G5_COMPOSITE_PRE_PHONE_PASS')
composite['requires'][-1] = (
    'No handset installation, provisioning, launch, interaction, profile enrollment or audio capture '
    'before this composite passes. Separately admitted bounded provider canaries form part of G4; '
    'trading remains demo-only and NEVER_ROUTABLE throughout.'
)
machine['commands']['exact_source'] = machine['commands']['exact_source'].replace(prior['application_sha'], expected)
machine['return_contract']['required'].append('Independently observed fresh exact-hit/CDP pseudo-element ownership and ordinary encoded-dot versus ambiguous traversal refusals for the current browser runtime.')
machine['producer'] = {'path': str(Path(__file__).resolve()), 'sha256': sha(Path(__file__))}

intro = f'''Resume VAN live acceptance through the actual connected DIAL MCP and Commander, using native Artemis directly on dial-control outside Hermes engineering orchestration. Work from **Vanguduza/Van exact clean application SHA `{expected}`** and verify the actual branch/object identity. Read the attached machine handoff, R7 source review and the original qualification report. The handoff preserves every earlier source/diagnostic receipt and grants no admission or live PASS.

CORE_ONLY_V2 places gateway, product Hermes profile `van` and direct phone mTLS HTTPS/WSS ingress on **van-trading-core**. Direct native Artemis/development runs on **dial-control**. Oracle Admin is excluded. The release/installer supplies Android route and trust; the owner enters no host, token, CA or model configuration in the app.

The current registry supplies **42 feature groups, 105 source functions, 78 surfaces, 432 endpoints and 251 schema components**. Its native candidate matrix contains **826 cases**: 420 feature states/recovery, 238 function cases (210 happy/error plus 28 explicit recovery), 156 surface cases and 12 cross-cutting cases. **Physical execution is 0/826.** Source fixtures and imported consistency checks are not actual native discovery or handset evidence.

Local qualification is supplied in `{qualification_path.name}` (SHA256 `{sha(qualification_path)}`). Use the report's exact per-suite execution/input scopes and retained failure/skip diagnostics; no overlap is summed and no prior whole-suite result is relabelled. This runtime child corrects Chromium encoded-dot scope semantics and fresh direct CDP ownership for pseudo-element geometry. Source checks and debug build results do not establish production signing, host/provider/kernel readiness or phone acceptance.

1. Discover the real DIAL/Commander/native schemas and actual owner execution route. Recover this exact source object. Locate existing protected production file paths read-only through the actual hosts before asking the owner. Preserve PKI, owner data, installed signer/state, pairing identities, sibling MCP entries, browser profiles and trading. Credentials and pairing codes remain protected ephemeral inputs, outside chat and exported artifacts.

2. Close the repository admission gates. Reuse an independently verified exact owner framework adoption if one already exists. Otherwise [PR94](https://github.com/Vanguduza/Van/pull/94), exact `296d647d8755b6036ddb6bc66a5526b78db07029`, is the separate framework-only first-adoption proposal. Quote and link [tools/ci/README.md:162](https://github.com/Vanguduza/Van/blob/296d647d8755b6036ddb6bc66a5526b78db07029/tools/ci/README.md#L162) if confirmation is needed. Framework adoption is not blanket approval of the 28 records or application history. Perform separate trusted application authorization intake/merge/deployment admission using the actual trusted-base checker; preserve uncovered findings and unchanged enforcement baselines.

3. Bind the existing production keystore/alias/signer, device CA/owner records, connectivity signing/public verification anchors, protected CORE_ONLY_V2 profile, genuine scoped ingress/deployment authority, database/encryption keys, local Hermes runtime/profile and per-profile browser state. Produce backups/rollback and an independently qualified deployment. Verify dedicated public IPv4 TLS HTTPS/WSS CA/SAN and no-client-certificate/auth/scope refusals, actual VNIC NSG/security-list/routing and ordered native firewall/IPv6 evidence, local product Hermes/session/browser/automation effects, both browser profile proxy/UID/kernel fences, and each required hosted provider's real admission/readback/refusal canaries. Unbound providers remain BLOCKED. Uncertain effects retain their original identity without resend. Trading stays demo-only and NEVER_ROUTABLE.

4. Build and verify the genuine owner-signed arm64 release APK/packet at this selected SHA, including embedded source, gateway route, CA/key anchors and actual signer identity. Follow `tools/release/README.md`. A merge that changes the accepted SHA requires a corresponding exact-source rebuild; retain prior APKs as historical.

5. Join actual original G0-G4 receipts at matching source/APK/config/profile/host identities into **PRE_PHONE_PASS**. `LOCAL_PREFLIGHT_PASS`, gateway GREEN, compiler PREPARED_NOT_DEPLOYED, packet validity and `PASS_HOST_HEALTH_ONLY` are subsets; the host collector keeps `device_provisioning_permitted=false`. **No handset installation, provisioning, launch, interaction, profile enrollment or audio capture until the full non-phone gate passes.** Continue independent read-only work while any dependent gate is blocked and report its exact missing binding.

6. After PRE_PHONE_PASS, refresh the current private paired TLS wireless ADB endpoint. The historical `10.66.66.2:35749` was refused and is stale. Use the same actual ADB server for Artemis, adbutils and subprocesses. Preserve original stdout and require fresh `get-state=device`, raw `ro.serialno=RFCX2054F5W` and raw `ro.product.model=SM-S928B`; the sanitized `SM_S928B` descriptor is insufficient. Recheck after reboot/network/endpoint changes. Preserve installed signer/state, provision the real signed packet and independently observe SESSION_ADMITTED.

7. Export actual installed native schemas and runtime root; regenerate the exact-source matrix using exposed mobile_run_task, mobile_manage_task, mobile_inspect_trace, mobile_get_device_state and mobile_diagnose contracts. Diagnosis fixes stay disabled unless separately admitted. Native-call preparation grants no execution/admission and native plans cannot dispatch through the legacy DDS/Hermes adapter. Execute all 826 happy/refusal/error/recovery cases with independent bounded effects: consent/permissions, network loss, process death/reboot, request recovery, resident deep links, browser scope/CDP ownership, voice/acoustics and private speaker enrollment/erasure. The owner privately handles OS/OAuth/biometric/audio consent. Missing controls FAIL; unavailable prerequisites BLOCKED; ambiguous or unobserved effects remain UNKNOWN.

Return PASS/FAIL/BLOCKED/PARTIAL/OUTCOME_UNKNOWN totals with physical execution separate, plus original redacted bounded independently collected artifacts: exact source/deployed config/profile/APK/signer; host/transport/raw device/schema observations; plan/input hashes; native task/trace/case/action/request/session IDs; per-step screenshots/logcat/traces/timestamps; independent backend/product Hermes/provider effect and refusal/no-effect readbacks; byte lengths/SHA256 and producer/session/epoch correlations; cleanup/rollback evidence. Preserve raw observations privately. Never author observations from expected values, export credentials/keys/audio/embeddings/private owner contents, resend uncertain effects or infer owner-goal PASS from a successful process.

Resolve every selector below from actual protected operator inputs before its phase; empty or unknown bindings are BLOCKED. Phone-effect commands are post-PRE_PHONE_PASS only.
'''
for name, command in machine['commands'].items():
    subprocess.run(['bash', '-n'], input=command, text=True, check=True, capture_output=True)
    intro += f'\n`{name}`\n\n```sh\n{command}\n```\n'
quote = machine['gates'][1]['instruction_quote']
assert quote in (ROOT / 'tools/ci/README.md').read_text()
intro += '\nExact repository first-adoption instruction:\n\n> ' + quote.replace('\n  ', '\n> ') + '\n'

def immutable(path, content):
    assert path.parent.resolve() == OUT.resolve() and not path.resolve().is_relative_to(ROOT.resolve())
    with path.open('x') as stream:
        stream.write(content)
    path.chmod(0o444)

machine_path = OUT / f'VAN_FINAL_DIRECT_DIAL_CONTINUATION_2026-10-09_{expected[:8]}.json'
human_path = OUT / f'VAN_FINAL_DIRECT_DIAL_CONTINUATION_PROMPT_2026-10-09_{expected[:8]}.md'
immutable(machine_path, json.dumps(machine, indent=2) + '\n')
immutable(human_path, intro)
assert all(sha(OUT / name) == h for name, h in prior_outputs.items())
receipt = {
    'record_kind': 'FINAL_RUNTIME_CONTINUATION_HANDOFF_SOURCE_AND_SYNTAX_CHECK',
    'measured_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'application_sha': expected,
    'source_clean_verified': True,
    'source_inputs_sha256': machine['source_inputs_sha256'],
    'registry_review_manifest_path': str(review_path),
    'registry_review_manifest_sha256': sha(review_path),
    'registry_review_input_count': len(review['files']),
    'registry_review_inputs_all_match': True,
    'qualification_report_path': str(qualification_path),
    'qualification_report_sha256': sha(qualification_path),
    'machine_handoff_path': str(machine_path),
    'machine_handoff_sha256': sha(machine_path),
    'human_prompt_path': str(human_path),
    'human_prompt_sha256': sha(human_path),
    'producer_path': str(Path(__file__).resolve()),
    'producer_sha256': sha(Path(__file__)),
    'commands_bash_syntax_checked_without_execution': len(machine['commands']),
    'all_prior_handoff_outputs_unchanged_sha256': prior_outputs,
    'tracked_inputs_before': before_tracked,
    'tracked_content_and_filesystem_modes_unchanged': tracked_snapshot() == before_tracked,
    'tracked_content_or_mode_mutations_by_this_handoff': 0,
    'actual_dial_tools_called': 0,
    'deployment_mutations': 0,
    'handset_effects': 0,
    'physical_cases_executed': 0,
    'gate_scope': 'Original local evidence is bound; actual trusted source admission, production/live/provider/kernel/device gates still require independent observations.',
}
assert receipt['tracked_content_and_filesystem_modes_unchanged']
receipt_path = OUT / f'VAN_FINAL_DIRECT_DIAL_CONTINUATION_SOURCE_RECEIPT_2026-10-09_{expected[:8]}.json'
immutable(receipt_path, json.dumps(receipt, indent=2) + '\n')
assert not subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain', '--untracked-files=all']).decode().strip()
print(json.dumps({'application_sha': expected, 'machine_path': str(machine_path), 'machine_sha256': sha(machine_path), 'prompt_path': str(human_path), 'prompt_sha256': sha(human_path), 'receipt_path': str(receipt_path), 'receipt_sha256': sha(receipt_path), 'physical_cases_executed': 0}))
