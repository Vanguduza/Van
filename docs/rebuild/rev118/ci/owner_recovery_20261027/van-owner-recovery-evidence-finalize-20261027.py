from pathlib import Path
import datetime
import hashlib
import json
import shutil
import subprocess
import xml.etree.ElementTree as E

repo = Path('/workspace/van-review-2026-10-18/publish')
work = Path('/workspace')
docs = repo / 'docs/rebuild/rev118'
base = 'ca981d19615f614a1c41f78618e04ea1582d620e'

def read(path):
    return json.loads(path.read_text())

def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def cases(path, passed, failed=0):
    rows = list(E.parse(path).getroot().iter('testcase'))
    failures = sum(r.find('failure') is not None for r in rows)
    errors = sum(r.find('error') is not None for r in rows)
    skips = sum(r.find('skipped') is not None for r in rows)
    assert (len(rows), failures, errors, skips) == (passed + failed, failed, 0, 0)

assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip() == base
final = work / 'van-owner-recovery-final-r3-20261027'
actual = read(final / 'receipt.json')
assert actual['base_head'] == base and actual['exit'] == 0
assert actual['completed'] is actual['cleaned'] is actual['owned_fixture_independently_absent'] is True
assert len(actual['source_sha256']) == 1162
assert all(sha(repo / name) == value for name, value in actual['source_sha256'].items())
cases(final / 'full-trading.xml', 780)
assert not read(final / 'storage-audit.json')['forbidden_events']
cases(work / 'van-owner-recovery-final-r1-20261027/full-trading.xml', 779, 1)
cases(work / 'van-recovery-digest-baseline-20261027/full-trading.xml', 42, 62)
cases(work / 'van-recovery-digest-focused-r1-20261027/full-trading.xml', 131)
cases(work / 'van-recovery-digest-compatibility-r2-20261027.xml', 59)
cases(work / 'van-owner-recovery-timing-control-20261027.xml', 6)
cases(work / 'van-owner-recovery-rebuild-20261027.xml', 165)
assert not read(work / 'van-owner-recovery-rebuild-audit-20261027.json')['forbidden_events']
for name in ('owner', 'frontend', 'registry', 'consolidation'):
    value = read(work / f'van-owner-recovery-{name}-check-20261027.json')
    if name == 'owner':
        assert value['changed'] == []
    elif name == 'frontend':
        assert value['changed'] is False
    else:
        assert value['findings'] == []
before = read(work / 'van-recovery-digest-C11-before-20261027.json')
assert all(sha(repo / name) == value for name, value in before.items())
assert '1/1 caught' in (work / 'van-recovery-digest-C11-20261027.log').read_text()
assert not (repo / 'tools/audit/.mutation-journal.json').exists()
failed_root = work / 'van-ca981d19-full-hosted'
failed = read(failed_root / 'failed-reconciliation.json')
assert failed['source_head'] == base and failed['verified_archives'] == 19
assert failed['status'] == 'FAILED_FOUR_JOBS_RETAINED'
assert failed['canonical_public_verifier'] == 'REFUSED_FAILED_CASES_AS_REQUIRED'
assert failed['canonical_mutations']['caught'] == 373
assert failed['canonical_mutations']['survivors'] == {'C11 an expired approval challenge can still be signed': 1}
assert all(sha(failed_root / name) == value for name, value in failed['file_sha256'].items())

out = docs / 'ci/owner_recovery_20261027'
out.mkdir(exist_ok=False)
for source, target in [
    ('van-recovery-digest-baseline-20261027', 'actual_ca981_causal_baseline'),
    ('van-recovery-digest-focused-r1-20261027', 'focused_131'),
    ('van-owner-recovery-final-r1-20261027', 'failed_wall_clock_fixture_779_1'),
    ('van-owner-recovery-final-r2-20261027', 'interrupted_no_final_report_r2'),
    ('van-owner-recovery-final-r3-20261027', 'stable_final_780'),
]:
    shutil.copytree(work / source, out / target)
for pattern in ('van-recovery-digest-*.py', 'van-recovery-digest-*.json',
                'van-recovery-digest-*.log', 'van-recovery-digest-*.xml'):
    for path in work.glob(pattern):
        if path.is_file():
            shutil.copy2(path, out / path.name)
for name in ('van-owner-recovery-final-r1-20261027.py',
             'van-owner-recovery-final-r2-20261027.py',
             'van-owner-recovery-final-r3-20261027.py',
             'van-owner-recovery-final-r3-process-20261027.json',
             'van-owner-recovery-final-r1-timing-fixture-20261027.json',
             'van_pytest_live_diagnostics.py',
             'van-owner-recovery-evidence-finalize-20261027.py'):
    shutil.copy2(work / name, out / name)
for pattern in ('van-owner-recovery-*-check-20261027.json',
                'van-owner-recovery-timing-control*20261027.*',
                'van-owner-recovery-rebuild*20261027.*'):
    for path in work.glob(pattern):
        if path.is_file():
            shutil.copy2(path, out / path.name)
hosted = docs / 'ci/hosted_ca981d19_full_20261027'
shutil.copytree(failed_root, hosted)
shutil.copy2(work / 'van-ca981-main-failed-reconcile-20261027.py', hosted / 'van-ca981-main-failed-reconcile-20261027.py')
now = datetime.datetime.now(datetime.timezone.utc).isoformat()
summary = (
    'Current gateway A4 signatures and native runtime recovery now agree on the exact structured intent digest. '
    'Native verification also preserves original legacy signatures and authority references, while durable outbox '
    'readback must match the digest actually signed. Only the three typed native recovery actions retain '
    'unconsumed legacy challenges with their exact fixed command/text shape; generic delimiter ambiguity still refuses. '
    'A shared expiry predicate is called after writer acquisition and again immediately before consumption, '
    'preserving both fresh half-open deadline checks and the original canonical mutation identity. '
    'Published ca981 main remains FAILED:62gateway failures and one expired-approval mutation survivor plus two '
    'unwaived mandatory prerequisites. Local unchanged causal sources reproduced62failures/42controls; '
    '131focused and59compatibility checks pass. Actual canonical C11 caught1/1, byte-exact restoration verified; '
    'this is not current execution of the full374case corpus. First broad run779pass/1correct command-expiry refusal '
    'used a live five-second positive fixture that took23seconds. A scoped deterministic test clock retained its '
    'TTL/assertions; all dedicated expiry boundaries remain unchanged. Six controls pass. A second broad attempt '
    'lost its controller with754recorded passing calls and no final report; original exit/cause are unknown. '
    'Its exact labeled PostgreSQL fixture was independently removed; that attempt is interrupted, never passed. '
    'The third run uses a recorded detached controller with its own deadline and cleanup. Stable current combined '
    'actualSQL/HTTP/accounting/authority/recovery run780pass/0skip/audit0, all1162source/test hashes match, owned '
    'PostgreSQL fixture independently absent.165rebuild/private-topology checks pass. PostgreSQL guard12new '
    'cases are included; earlier guard672 passes belong to their earlier snapshot. No unit/native/production/S24 acceptance.'
)
runtime_files = ['backend/van_gateway/approval/service.py',
                 'backend/van_gateway/trading/runtime_recovery_dispatch.py',
                 'trading/vati/app/runtime_control_protocol.py',
                 'backend/tests/test_runtime_recovery_protocol.py',
                 'backend/tests/test_runtime_recovery_outbox.py',
                 'backend/tests/test_a4_owner_approval.py']
report = {
    'schema': 'van.rebuild.owner-recovery-source/1', 'base_head': base,
    'updated_at_utc': now, 'status': 'SOURCE_TESTED_COMPONENT_NOT_UNIT_ACCEPTANCE',
    'acceptance': 'NOT_ISSUED', 'units': ['BE-002', 'BE-003', 'BE-009'],
    'implementation': summary,
    'source_sha256': {name: sha(repo / name) for name in runtime_files},
    'actual_tests': {'unchanged_causal_baseline': {'failed': 62, 'passed': 42},
                    'focused': 131, 'extended_compatibility': 59,
                    'failed_first_broad': {'passed': 779, 'failed': 1, 'cause': 'Positive fixture exceeded unchanged command deadline; correct runtime refusal'},
                    'timing_controls': 6, 'stable_combined': 780, 'stable_skips': 0,
                    'storage_audit_violations': 0, 'pinned_hashes': 1162,
                    'owned_fixture_independently_absent': True, 'rebuild': 165,
                    'new_recovery_cases': 4, 'counts_overlap': True},
    'canonical_mutation_execution': {'selected_case': 'C11 an expired approval challenge can still be signed',
                                   'caught': 1, 'selected': 1, 'survivors': 0,
                                   'source_restoration': 'BYTE_EXACT', 'full_current_corpus': 'NOT_RUN'},
    'canonical_preflight': {'cases': 374, 'edits': 383, 'findings': [], 'execution': 'NOT_RUN'},
    'contracts': {'endpoints': 483, 'schemas': 376, 'original_groups': 42,
                  'original_functions': 105, 'original_surfaces': 78, 'drift': False},
    'programme_snapshot': {'backend_units': 82, 'units_with_source_milestones': 30,
                          'units_without_recorded_source_milestones': 52,
                          'candidate_status_source_tested': 14, 'candidate_status_in_progress': 16,
                          'backend_verification_packets': 12, 'formally_accepted_units': 0,
                          'meaning': 'Component milestones, not full-unit completion. Unrecorded units may contain inherited implementation.'},
    'evidence': 'ci/owner_recovery_20261027',
    'qualification': 'Local source fixtures and software test keys only. No device biometric, native admission, broker effect, production, economic or S24 qualification; all remaining canonical backend work and Android prerequisites remain required.'
}
write(docs / 'receipts/OWNER_RECOVERY_COMPATIBILITY_SOURCE_20261027.json', report)
write(docs / 'receipts/HOSTED_SOURCE_ca981d19.json', {
    'schema': 'van.rebuild.hosted-source/1', 'source_head': base,
    'updated_at_utc': now, 'main': failed, 'evidence': 'ci/hosted_ca981d19_full_20261027',
    'forecast_receipt': 'receipts/HOSTED_FORECAST_SOURCE_ca981d19.json',
    'qualification': 'Main terminal FAILED four jobs.15public jobs succeeded;2public failures and2mandatory failures retained. Forecast fixtures passed independently. Does not qualify later uncommitted guard/recovery fixes or issue acceptance.'
})
p = docs / 'receipts/HOSTED_FORECAST_SOURCE_ca981d19.json'
d = read(p); d['main_scope'] = 'Main40432745614 terminal FAILED four jobs; see HOSTED_SOURCE_ca981d19.json. Forecast success remains separate.'; write(p, d)
p = docs / 'receipts/LEASE_GUARD_SOURCE_20261027.json'
d = read(p); d['earlier_stable_snapshot'] = 'The672case result and its1162matching hashes were measured before the native recovery follow-up. They do not establish current full-source equality.'
d['current_combined_revalidation'] = {'passed': 780, 'skipped': 0, 'audit_violations': 0,
                                     'source_hashes_current': 1162, 'owned_fixture_independently_absent': True,
                                     'evidence': 'ci/owner_recovery_20261027/stable_final_780'}; write(p, d)
(docs / 'backend/BE-002_003_009_NATIVE_RECOVERY_DIGEST_COMPATIBILITY.md').write_text(
    '# Preserve original approval identity across native recovery\n\n' + summary + '\n\n'
    'The native verifier derives both allowed statements from the strict typed recovery intent and the original '
    'operation and expiry. It authenticates the actual signature and hashes that exact statement into its authority '
    'reference. Selecting the other recognized digest in saved receipt metadata still refuses. No arbitrary digest '
    'or caller-selected encoding can create authority. Signature authentication for immutable expired history '
    'does not grant current execution; native lifetime, registered owner key, account epoch and final submission '
    'checks remain in their existing owners. Recovery remains separate from blanket order-entry permission.\n\n'
    'The published mutation survived because its single edit affected only the first of two repeated expiry '
    'predicates. Refactoring one shared predicate keeps two fresh calls while restoring the original registered '
    'fault meaning. No registry case, test assertion, deadline or hook was removed. The original hosted '
    '373caught/1survived result stays failed. The local1/1 result is a different snapshot and is never added to '
    'the old373to claim a current374pass.\n\n'
    'See `../receipts/OWNER_RECOVERY_COMPATIBILITY_SOURCE_20261027.json`, '
    '`../receipts/HOSTED_SOURCE_ca981d19.json` and their raw evidence. No unit acceptance or production claim.\n')
p = docs / 'backend/BE-003_009_LEASE_GUARD_TRANSACTION_OWNER.md'
p.write_text(p.read_text() + '\nThe later native-recovery follow-up revalidates the combined current source in780cases, '
             'zero skips/audit violations, all1162hashes matching and the owned PostgreSQL fixture independently absent. '
             'Earlier672evidence remains tied to its earlier full-source snapshot. See '
             '`BE-002_003_009_NATIVE_RECOVERY_DIGEST_COMPATIBILITY.md`.\n')
p = docs / 'CANDIDATE_SOURCE_PROGRESS.json'
d = read(p); d['updated_at_utc'] = now
for unit in ('BE-002', 'BE-003', 'BE-009'):
    assert d['units'][unit]['unit_acceptance'] == 'NOT_ISSUED'
    d['units'][unit]['milestones'].append({'description': summary,
        'evidence': 'backend/BE-002_003_009_NATIVE_RECOVERY_DIGEST_COMPATIBILITY.md;receipts/OWNER_RECOVERY_COMPATIBILITY_SOURCE_20261027.json'})
write(p, d)
next_action = ('Finish real manifest and verified staged archive, commit through genuine Project Truth hook with '
               'existing candidate-build authorization, run committed verification against4fd466dec3910ed5de614bfbf95887ad619df5ca '
               'and await actual exit0; normal push and independent remote readback, inspect exact new CI and repair '
               'actual failures. Published ca981 main40432745614 is already terminal FAILED four jobs. Continue '
               'physical-account arbitration, shared reservations/risk and the canonical backend programme. Preserve '
               'logical alias fencing and all owner/recovery/retirement/uncertainty controls; no new frontend before BG-001.')
p = docs / 'EXECUTION_LEDGER.json'
d = read(p); d['updated_at_utc'] = now; d['checkpoint']['updated_utc'] = now
d['checkpoint']['last_validation'] = summary; d['observations'].append(summary)
d['current_action'] = next_action
d['continuation']['latest_checkpoint_report'] = 'docs/rebuild/rev118/CHECKPOINT_20261027_LEASE_GUARD.md'
d['continuation']['verified_source_head'] = base + ' published/actualGREEN171; guard and native recovery follow-up uncommitted at evidence generation'
write(p, d)
(docs / 'CHECKPOINT_20261027_LEASE_GUARD.md').write_text(
    '# Lease guard and native owner-recovery continuation\n\n' + now + '\n\n' + summary + '\n\n' +
    'Published head: `' + base + '`, actualGREEN171 against required baseline '
    '`4fd466dec3910ed5de614bfbf95887ad619df5ca`, manifest5927, normal push/readback. '
    'Current candidate is uncommitted at this checkpoint; inspect actual Git.\n\n' + next_action + '\n\n' +
    'Exactca981 main40432745614:15public success, backend62fail/5788pass/7declaredskips, mutation373caught/1C11survivor/0unexecuted, '
    'two mandatory failures (private DDS deploy key and trusted-main checker unavailable).19raw ZIPs verified. '
    'Canonical public-source coverage verifier correctly refuses failed JUnit. Exactforecast40432745121 independently '
    'passed114nativeSQL/Parquet,6synthetic fixtures,3cold workers/parity0/232versions/kernel/cleanup/source hashes, '
    'tree-equivalent merge49debf86b517d1fef56e21d299a45ecfc0e76f74. Forecast success is not whole-main success. '
    'Parentf004 all17public success/mainFAILEDtwo mandatory/19verifiedZIPs remains separately recorded.\n\n' +
    'Guard baseline3actual lock failures/1control, initial4fixture failures before functional boundary, intermediate '
    '2actualSQL-error failures/10controls and all repairs remain in raw evidence. RLock transaction owner and native '
    'savepoints preserve parent row locks across borrowed reads and inner guards. Logical alias lease keys, CAS '
    'and epochs remain. Physical-account duplicate-alias arbitration is still unimplemented; the earlier alias '
    'probe was primitive-only, not an observed native financial bypass.\n\n' +
    'Actual resumed command/child/thread creation and joins passed; process health was97PID1zombies at environment '
    'recovery and108at later resume. No enforcing quota established or platform process killed. Own test children '
    'are reaped and ephemeral PostgreSQL fixtures independently removed. No local browser/emulator suite.\n\n' +
    'Zero formally accepted units. Frozen131units/324requirements/1610acceptances/234contexts/349actions/93features '
    'and original42groups/105functions/78surfaces remain; current483endpoints/376schemas. All remaining funding, '
    'risk/provider/native-market, forecasting/learning/crypto, assistant/voice/privacy/automation, operational, '
    'independent/native/provisioning/signing/Android/Artemis/S24 obligations remain required. Van trading core is '
    'the chosen host; Android must use provisioned production profile without owner-entered addresses. '
    'Profitability requires evidence, never a guarantee. Do not touch /workspace/Van or delegate.\n')
write(out / 'evidence-file-hashes.json', {str(p.relative_to(out)): sha(p) for p in out.rglob('*') if p.is_file()})
print(json.dumps({'stable_cases': 780, 'source_hashes': 1162, 'rebuild': 165,
                  'failed_hosted_archives': 19, 'acceptance': 'NOT_ISSUED'}))
