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
base = 'b0a61313e5167bafca4dbeea96f2bfcc5c7c6b90'

def read(p): return json.loads(p.read_text())
def write(p, d): p.write_text(json.dumps(d, indent=2) + '\n')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def passed(p, count):
    rows = list(E.parse(p).getroot().iter('testcase'))
    assert len(rows) == count and not any(r.find(k) is not None for r in rows for k in ('failure', 'error', 'skipped'))

assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip() == base
final = work / 'van-physical-account-final-r2-20261027'
actual = read(final / 'receipt.json')
assert actual['base_head'] == base and actual['exit'] == 0
assert actual['completed'] is actual['cleaned'] is actual['owned_fixture_independently_absent'] is True
assert len(actual['source_sha256']) == 1167
assert all(sha(repo / n) == h for n, h in actual['source_sha256'].items())
passed(final / 'full-trading.xml', 922)
assert not read(final / 'storage-audit.json')['forbidden_events']
passed(work / 'van-physical-account-pure-r2-20261027.xml', 52)
passed(work / 'van-physical-builder-focused-r1-20261027/full-trading.xml', 128)
passed(work / 'van-physical-builder-focused-r2-20261027/full-trading.xml', 78)
passed(work / 'van-physical-rebuild-20261027.xml', 165)
passed(work / 'van-cognitive-focused-no-driver-after-20261027.xml', 79)
assert not read(work / 'van-cognitive-focused-no-driver-after-audit-20261027.json')['forbidden_events']
assert not read(work / 'van-physical-rebuild-audit-20261027.json')['forbidden_events']
assert '4388 tests collected' in (work / 'van-cognitive-no-driver-after-20261027.log').read_text()
assert '2 errors during collection' in (work / 'van-cognitive-no-driver-before-20261027.log').read_text()
assert not read(work / 'van-cognitive-no-driver-after-audit-20261027.json')['forbidden_events']
baseline = read(work / 'van-physical-builder-baseline-source-20261027.json')
assert baseline['actual_SQL_failed_duplicate_physical_alias_cases'] == 4
assert baseline['passed_existing_alias_and_distinct_account_controls'] == 8
for name, filename in [('owner', 'van-physical-owner-check-r1-20261027.json'),
                       ('frontend', 'van-physical-frontend-check-20261027.json'),
                       ('registry', 'van-physical-registry-check-r1-20261027.json'),
                       ('consolidation', 'van-physical-consolidation-check-20261027.json')]:
    value = read(work / filename)
    if name == 'owner': assert value['changed'] == []
    elif name == 'frontend': assert value['changed'] is False
    else: assert value['findings'] == []
parent = work / 'van-b0a61313-full-hosted'
parent_terminal = (parent / 'reconciliation.json').exists()
parent_main = read(parent / ('reconciliation.json' if parent_terminal else 'partial-reconciliation.json'))
assert parent_main['public_jobs_success'] == (17 if parent_terminal else 16)
if not parent_terminal:
    assert parent_main['status'] == 'IN_PROGRESS_BACKEND_PUBLIC_RESULT_PENDING'
forecast = work / 'van-b0a61313-forecast-hosted'
parent_forecast = read(forecast / 'independent-reconciliation.json')
cognitive = work / 'van-b0a61313-cognitive-failure-20261027'
parent_cognitive = read(cognitive / 'reconciliation.json')
for root, report in [(parent, parent_main), (forecast, parent_forecast), (cognitive, parent_cognitive)]:
    assert all(sha(root / n) == h for n, h in report['file_sha256'].items())
    assert not any(p.name.startswith('private-download') for p in root.rglob('*'))

out = docs / 'ci/physical_account_scope_20261027'
out.mkdir(exist_ok=False)
for name, target in [('van-physical-builder-baseline-20261027', 'actual_b0_builder_baseline'),
                     ('van-physical-builder-focused-r1-20261027', 'first_128'),
                     ('van-physical-builder-focused-r2-20261027', 'extended_78'),
                     ('van-physical-account-final-r1-20261027', 'cancelled_for_confirmed_collection_fix'),
                     ('van-physical-account-final-r2-20261027', 'stable_final_922')]:
    shutil.copytree(work / name, out / target)
for pattern in ('van-physical-*.py', 'van-physical-*.json', 'van-physical-*.xml', 'van-physical-*.log',
                'van-cognitive-no-driver-*.xml', 'van-cognitive-no-driver-*.json', 'van-cognitive-no-driver-*.log',
                'van-cognitive-focused-no-driver-*.xml', 'van-cognitive-focused-no-driver-*.json',
                'van-cognitive-focused-no-driver-*.log'):
    for p in work.glob(pattern):
        if p.is_file(): shutil.copy2(p, out / p.name)
shutil.copy2(work / 'van-cognitive-no-driver-20261027/sitecustomize.py', out / 'absent_driver_fixture.py')
for root, target in [(parent, 'hosted_b0a61313_full_20261027' if parent_terminal else 'hosted_b0a61313_pending_20261027'),
                     (forecast, 'hosted_b0a61313_forecast_20261027'),
                     (cognitive, 'hosted_b0a61313_cognitive_failure_20261027')]:
    shutil.copytree(root, docs / 'ci' / target)
now = datetime.datetime.now(datetime.timezone.utc).isoformat()
summary = (
    'Native sending profiles in both runtime builders now require the existing logical alias lease and an '
    'additional expected physical-account lease. The original alias/public epoch, holder, CAS, owner controls '
    'and native identity checks remain. cTrader uses the actual factory host and normalized account ID; '
    'MT5 bridge/EA share exact native server/login; Deriv uses native login/environment, excluding client app '
    'and endpoint aliases. Display, credential, route and currency labels cannot split one expected scope. '
    'Non-sending/paper/owner-ticket paths retain their original contract. Both rows remain locked through '
    'final submission; partial acquisition/renewal refuses and releases only this holder/epoch. '
    'Unchanged b0 actual PostgreSQL builders reproduced4duplicate-account failures with8controls. '
    '128first focused,78extended and52current pure checks pass; counts overlap and earlier snapshots differ. '
    'The extended run includes actual peer lock waits across nested fences, guards, SQL errors and original '
    'body failures, plus retirement/profile/unknown-effect/recovery controls. Published b0 cognitive Python '
    'broad collection failed because its locked environment lacks optional psycopg. Imports in both PG test '
    'modules now occur behind the unchanged canonical pg_dsn fixture; no assertion, case or opt-in rule was '
    'removed. Controlled absent-driver collection changes from2errors to4388collected/0errors, not a runtime '
    'pass.79focused cognitive runtime cases also pass under that explicit absent-driver fixture. '
    'First combined run was deliberately interrupted for that fix, with raw signal/pytest teardown '
    'error retained and fixture independently absent. Stable current combined922actualSQL/HTTP cases pass '
    '0skip/audit0/all1167source-test hashes matching/ownedPGindependentlyabsent;165rebuild/private-topology '
    'checks pass. This does not share financial history/reservations or solve alias handover/unknown-effect '
    'reconciliation, fence old binaries, qualify a mixed cohort or establish native connectivity. No unit, '
    'production, economic or S24 acceptance.'
)
paths = ['trading/vati/accounts/physical_scope.py', 'trading/vati/app/physical_account_lease.py',
         'trading/vati/app/service.py', 'trading/vati/app/account_service.py',
         'trading/tests/test_physical_account_builders.py', 'trading/tests/test_physical_account_lease.py',
         'trading/tests/test_physical_account_lease_postgres.py', 'trading/tests/test_postgres_lease_guard_ownership.py']
write(docs / 'receipts/PHYSICAL_ACCOUNT_SCOPE_SOURCE_20261027.json', {
    'schema': 'van.rebuild.physical-account-source/1', 'base_head': base, 'updated_at_utc': now,
    'status': 'SOURCE_TESTED_COMPONENT_NOT_UNIT_ACCEPTANCE', 'acceptance': 'NOT_ISSUED',
    'units': ['BE-009'], 'implementation': summary,
    'source_sha256': {n: sha(repo / n) for n in paths},
    'actual_tests': {'baseline_failed': 4, 'baseline_passed_controls': 8,
                    'first_focused': 128, 'extended': 78, 'current_pure': 52,
                    'new_scope_cases': 68, 'stable_combined': 922, 'stable_skips': 0,
                    'audit_violations': 0, 'current_source_hashes': 1167,
                    'owned_fixture_independently_absent': True, 'rebuild': 165,
                    'counts_overlap': True},
    'absent_driver_collection': {'environment': 'EXPLICIT_SIMULATED_ABSENCE_NOT_HOSTED_RUNTIME',
                                 'before_errors': 2, 'after_collected': 4388, 'after_errors': 0,
                                 'collection_runtime_tests_executed': 0,
                                 'separate_actual_focused_runtime_passes': 79},
    'contracts': {'endpoints': 483, 'schemas': 376, 'original_coverage': [42, 105, 78], 'drift': False},
    'canonical_mutation_preflight': {'cases': 374, 'edits': 383, 'findings': [], 'execution': 'NOT_RUN'},
    'remaining': ['Shared physical-account financial lineage and all-origin risk/reservations',
                  'Cross-alias handover, unresolved effects, retirement and provider reconciliation',
                  'Coherent runtime cohort drain/migration and independent native qualification',
                  'Full canonical backend, provisioning/signing/deployment and Android/S24 programme'],
    'evidence': 'ci/physical_account_scope_20261027'})
write(docs / 'receipts/HOSTED_SOURCE_b0a61313.json', {
    'schema': 'van.rebuild.hosted-source/1', 'source_head': base, 'updated_at_utc': now,
    'main': parent_main, 'forecast': parent_forecast, 'cognitive_failure': parent_cognitive,
    'qualification': ('Exact b0 source only. Main17publicsuccess/two mandatory failures. ' if parent_terminal else
                      'Exact b0 source only. Main still IN_PROGRESS:16publicsuccess/two mandatory failures, backend-public result pending and unqualified. ') +
                     'Separate cognitive Python broad collection failed. Forecast fixtures passed. Later physical-scope/import fix needs its own exact hosted qualification. No acceptance.'})
(docs / 'backend/BE-009_PHYSICAL_ACCOUNT_SCOPE_FENCE.md').write_text(
    '# Require both logical and expected physical account ownership\n\n' + summary + '\n\n'
    'The additional scope is computed from existing expected native adapter bindings. It is not a verified '
    'observation, a new grant or provider connectivity. The original native response checks, current account '
    'profile and owner authority remain necessary. Multiple observer/profile aliases remain valid. No alias '
    'is replaced, no public epoch namespace is changed and no arbitrary account hash authorizes execution.\n\n'
    'A coherent upgraded cohort and current provider binding must be independently qualified before activation. '
    'An old binary that ignores this protocol is not fenced by source presence. Shared balances, histories, '
    'uncertain orders, funding/withdrawal reservations and alias-switch handover still need their own integrated '
    'owners and evidence. The additional concurrency fence alone does not complete account-wide financial safety.\n\n'
    'See `../receipts/PHYSICAL_ACCOUNT_SCOPE_SOURCE_20261027.json` and `../receipts/HOSTED_SOURCE_b0a61313.json`. '
    'Source milestones are not whole-unit acceptance.\n')
p = docs / 'backend/BE-009_PHYSICAL_ACCOUNT_ARBITRATION_INSPECTION.md'
p.write_text(p.read_text() + '\nA later candidate implements additional expected physical scope while retaining '
             'logical alias fencing. See `BE-009_PHYSICAL_ACCOUNT_SCOPE_FENCE.md`; this dated inspection remains '
             'the pre-implementation record, and financial sharing/handover/native qualification remain required.\n')
p = docs / 'CANDIDATE_SOURCE_PROGRESS.json';d = read(p);d['updated_at_utc'] = now
assert d['units']['BE-009']['unit_acceptance'] == 'NOT_ISSUED'
d['units']['BE-009']['milestones'].append({'description': summary,
    'evidence': 'backend/BE-009_PHYSICAL_ACCOUNT_SCOPE_FENCE.md;receipts/PHYSICAL_ACCOUNT_SCOPE_SOURCE_20261027.json'})
write(p, d)
next_action = ('Finish real manifest and verified staged archive; genuine hook with existing candidate-build '
               'authorization, actual committed required-baseline verification exit0, normal push/readback and '
               'exact new CI. Do not cancel running parent qualification. Repair actual hosted failures and retain '
               'their original outcomes. Continue shared physical-account lineage/risk/reservations, payment/manual '
               'handover/provider reconciliation and all canonical remaining backend features. No frontend before BG-001.')
p = docs / 'EXECUTION_LEDGER.json';d = read(p);d['updated_at_utc'] = now
d['checkpoint']['updated_utc'] = now;d['checkpoint']['last_validation'] = summary
d['observations'].append(summary);d['current_action'] = next_action
d['continuation']['verified_source_head'] = base + ' published/actualGREEN172/manifest6400/normalpush+remote readback; physical-scope and optional-driver collection fix uncommitted at generation'
d['continuation']['latest_checkpoint_report'] = 'docs/rebuild/rev118/CHECKPOINT_20261027_PHYSICAL_ACCOUNT_SCOPE.md'
write(p, d)
(docs / 'CHECKPOINT_20261027_PHYSICAL_ACCOUNT_SCOPE.md').write_text(
    '# Expected physical account and logical alias arbitration continuation\n\n' + now + '\n\n' + summary + '\n\n'
    'Published `' + base + '` has actualGREEN172 against required '
    '`4fd466dec3910ed5de614bfbf95887ad619df5ca`, real manifest6400/zero mismatches/alltracked and normal '
    'push/readback. Current candidate is uncommitted at generation; inspect actual Git and do not guess the '
    'next GREEN.\n\n' + next_action + '\n\n'
    'Parent main40448997885 is ' + ('terminal with17publicsuccess/two mandatory failures' if parent_terminal else
    'still IN_PROGRESS with16publicsuccess/two mandatory failures and its final backend result pending; no whole-main pass is claimed') +
    '. Forecast40448997941 evidence is retained separately from failed '
    'cognitive40448997882:79focusedpass, broad1collectionerror, Androidsuccess. The source fix preserves '
    'the original PostgreSQL fixture and every assertion. Controlled absent-driver collection is not '
    'hosted/native runtime acceptance. First combined run cancellation, signal teardown error and cleanup '
    'remain raw; only stable corrected922is passing.\n\n'
    'There are82backend units,30with milestones/52without recorded milestones,12backend-verification '
    'packets outstanding and0formally accepted units. Inherited source may exist in unrecorded units. Frozen '
    '131units/324requirements/1610acceptances/234contexts/349actions/93features and original42groups/105functions/'
    '78surfaces remain; current483endpoints/376schemas. All assistant/voice/trading/learning/forecast/crypto/'
    'operations and independent/native/provisioning/signing/deployment/Android/Artemis/S24 requirements remain. '
    'Van trading core is the chosen host; use its provisioned production Android profile, no owner-entered '
    'backend addresses. Profitability needs evidence, never a guarantee. Do not touch /workspace/Van or delegate.\n')
write(out / 'evidence-file-hashes.json', {str(p.relative_to(out)): sha(p) for p in out.rglob('*') if p.is_file()})
print(json.dumps({'stable_passes': 922, 'source_hashes': 1167, 'new_scope_cases': 68,
                  'rebuild': 165, 'acceptance': 'NOT_ISSUED'}))
