from pathlib import Path
import datetime
import hashlib
import json
import shutil
import subprocess

repo = Path('/workspace/van-review-2026-10-18/publish')
work = Path('/workspace')
docs = repo / 'docs/rebuild/rev118'
head = 'abafcf9094beaa3230e1959f999f13eb055fff9f'
def read(p): return json.loads(p.read_text())
def write(p, v): p.write_text(json.dumps(v, indent=2) + '\n')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip() == head
assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=repo)
verify = read(work / 'van-physical-account-committed-verify-20261027.json')
assert verify['state'] == 'COMPLETED' and verify['exit'] == 0
assert 'GREEN — 173 commit(s)' in (work / 'van-physical-account-committed-verify-20261027.log').read_text()
source = read(work / 'van-physical-account-final-r2-20261027/receipt.json')
assert source['exit'] == 0 and len(source['source_sha256']) == 1167
assert all(sha(repo / name) == digest for name, digest in source['source_sha256'].items())
root = work / 'van-b0a61313-full-hosted'
main = read(root / 'reconciliation.json')
assert main['public_jobs_success'] == 17 and main['actual_verified_archives_total'] == 19
assert main['canonical_mutations'] == {'reports': 9, 'caught_exactly_once': 374, 'edits': 383, 'survivors': 0, 'unexecuted': 0}
assert all(sha(root / name) == digest for name, digest in main['file_sha256'].items())
forecast = read(work / 'van-b0a61313-forecast-hosted/independent-reconciliation.json')
cognitive = read(work / 'van-b0a61313-cognitive-failure-20261027/reconciliation.json')
out = docs / 'ci/hosted_b0a61313_full_20261027'
shutil.copytree(root, out)
for name in ('van-b0-main-reconcile-20261027.py', 'van-b0-forecast-reconcile-20261027.py',
             'van-b0-hosted-final-evidence-20261027.py'):
    shutil.copy2(work / name, out / name)
shutil.copy2(work / 'van-physical-account-committed-verify-20261027.log', out / 'local_abaf_actual_GREEN173.log')
write(out / 'PARTIAL_SNAPSHOT_SCOPE.json', {
    'historical_partial_snapshot': '../hosted_b0a61313_pending_20261027',
    'meaning': 'The older partial-reconciliation file hashes apply to the immutable18archive pending snapshot. The workspace download receipt later advanced to19archives. Final reconciliation covers the final raw tree; source helpers and the separately labelled local abaf ledger log are additional evidence, not hosted b0 test results.'})
now = datetime.datetime.now(datetime.timezone.utc).isoformat()
summary = ('Exact published b0a61313e5167bafca4dbeea96f2bfcc5c7c6b90 main40448997885 is terminal '
           'FAILED on two unwaived mandatory prerequisites; all17public jobs succeeded. Nineteen raw main/forecast '
           'archives independently size/SHA/GitHubdigest/CRC/path verified. Actual4283trading/1DDSskip,26PostgreSQL, '
           '117voice,5854gateway/7declaredskips,198media,258monitor, browser/firewall and emulator18/4declaredskips '
           'are retained. All374canonical identities caught exactly once/383edits/9reports/0survivor/0unexecuted; '
           'public selection hashes and canonical coverage verification match exact b0. Forecast40448997941 '
           'independently verifies114nativeSQL/Parquet,6synthetic fixtures,3separate cold models/parity0/232versions/'
           'kernel/cleanup/source-controller-report hashes and tree-equivalent62914c238308d5178b6b85ca15960449b28b0187. '
           'Separate cognitive40448997882 remains FAILED:79focusedpass, broad1collectionerror from optional-driver '
           'import, Androidsuccess. These results do not qualify later physical-scope/import correction. '
           'Local correction abafcf9094beaa3230e1959f999f13eb055fff9f is genuineGREEN173/manifest6671/clean '
           'before this evidence-only follow-up, with922current source cases0skip/audit0/1167hashes/PGabsent, '
           '165rebuild and79focused controlled-absent-driver checks. No unit/native/production/economic/S24 acceptance.')
write(docs / 'receipts/HOSTED_SOURCE_b0a61313_FINAL.json', {
    'schema': 'van.rebuild.hosted-source/1', 'source_head': 'b0a61313e5167bafca4dbeea96f2bfcc5c7c6b90',
    'updated_at_utc': now, 'main': main, 'forecast': forecast, 'cognitive_failure': cognitive,
    'earlier_pending_observation': 'receipts/HOSTED_SOURCE_b0a61313.json',
    'evidence': 'ci/hosted_b0a61313_full_20261027', 'qualification': summary})
p = docs / 'EXECUTION_LEDGER.json';d = read(p)
d['updated_at_utc'] = now;d['checkpoint']['updated_utc'] = now
d['checkpoint']['last_validation'] = summary;d['observations'].append(summary)
d['continuation']['verified_source_head'] = head + ' local genuineGREEN173/manifest6671; b0 remains published; evidence-only final-parent follow-up not yet committed at generation'
d['continuation']['source_qualification_run'] = 40448997885
d['continuation']['qualification_scope'] = 'Exact published b0 main17publicsuccess/two mandatory failures; separate cognitive collection failure retained. Later physical-scope/import fix has local source evidence and needs its own hosted CI. Zero unit/native/production acceptances.'
d['current_action'] = ('Real manifest/staged backup/genuine evidence-only hook; committed required-baseline verification '
                       'exit0, normalpush/readback and exact new CI. Parent b0 main is terminal, so the next push '
                       'does not cancel it. Preserve cognitive failure and qualify its import fix. Continue shared '
                       'physical-account financial lineage, all-origin risk/reservations, funding/provider/manual '
                       'handover and the remaining canonical backend/Android programme. No new frontend before BG-001.')
write(p, d)
(docs / 'CHECKPOINT_20261027_PHYSICAL_ACCOUNT_SCOPE.md').write_text(
    '# Physical-account source and completed parent qualification\n\n' + now + '\n\n' + summary + '\n\n'
    'The physical-scope implementation retains logical alias arbitration and every original public epoch, '
    'owner grant, provider identity and refusal contract. Both native sending builders require both leases. '
    'Actual shared SQL baseline4failures/8controls became12passing builder cases;68new scope cases include '
    'identity/profile mappings, partial state and real peer lock waits. Earlier128/78/52results overlap and '
    'belong to their documented snapshots. The final922current cases and all1167hashes qualify the present '
    'application source; the16PGcases still execute with the real driver. Controlled no-driver4388collection '
    'is not a runtime pass;79focused cases are a separate actual source run under that explicit simulation. '
    'The cancelled first combined run and its signal teardown error remain retained, not passed.\n\n'
    'abafcf9094beaa3230e1959f999f13eb055fff9f was committed with the actual candidate-build hook and '
    'verifiedGREEN173 against4fd466dec3910ed5de614bfbf95887ad619df5ca. This evidence-only follow-up is '
    'uncommitted at generation; inspect actual Git. Finish the real manifest, verified staged archive and '
    'genuine hook, await committed verification exit0, then push normally and read back the exact remote '
    'head and its CI. No hosted result is assigned to an intermediate commit without its own run.\n\n'
    'The immutable parent pending18archive observation remains in ci/hosted_b0a61313_pending_20261027. '
    'The final19archive result is in ci/hosted_b0a61313_full_20261027 and '
    'receipts/HOSTED_SOURCE_b0a61313_FINAL.json. Canonical public coverage verification and source hashes '
    'were independently rerun against Git b0, not the later worktree. Parent overall main FAILED two '
    'prerequisites and separate cognitive FAILED collection remain unwaived. Forecast success is fixture-only.\n\n'
    'Additional physical arbitration does not share financial history/collateral/reservations, reconcile '
    'cross-alias uncertain effects, complete handover/retirement/provider rails or fence old binaries. '
    'A coherent upgraded cohort, native bindings and activation still need independent qualification. '
    'Continue the full canonical programme:82backend units,30with source milestones/52without recorded '
    'milestones,12verification packets outstanding,0formallyaccepted. Inherited source may exist in unrecorded '
    'units. No feature/error/owner/frontend contract is retired. Frozen131units/324requirements/1610acceptances/'
    '234contexts/349actions/93features and42groups/105functions/78surfaces remain;483endpoints/376schemas. '
    'Van trading core remains chosen host; provision Android production profile without owner-entered addresses. '
    'All signing/deployment/native/Artemis/S24 evidence remains required. Profitability requires evidence, '
    'never a guarantee. Do not touch /workspace/Van or delegate; no frontend redesign before BG-001.\n')
write(out / 'packet-file-hashes.json', {str(p.relative_to(out)): sha(p) for p in out.rglob('*') if p.is_file()})
print(json.dumps({'verified_parent_archives': 19, 'public_main_jobs_passed': 17,
                  'canonical_cases_caught': 374, 'current_source_head': head,
                  'evidence_only_followup': True, 'acceptance': 'NOT_ISSUED'}))
