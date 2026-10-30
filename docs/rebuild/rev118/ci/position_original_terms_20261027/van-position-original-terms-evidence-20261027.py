"""Guarded source receipts; execute only after both terminal results exist."""
from pathlib import Path
import datetime
import hashlib
import json
import shutil
import subprocess
import xml.etree.ElementTree as E

root = Path('/workspace/van-review-2026-10-18/publish')
work = Path('/workspace')
docs = root / 'docs/rebuild/rev118'
head = 'b58bb578418ac1d49dc67078f616ac4c3eb8b3ef'
raw = work / 'van-position-original-terms-final-r2-20261027'


def read(p):
    return json.loads(p.read_text())


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def write(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, indent=2) + '\n')


def cases(p):
    rows = list(E.parse(p).getroot().iter('testcase'))
    return dict(passed=sum(all(c.find(k) is None for k in ('failure', 'error', 'skipped')) for c in rows),
                failed=sum(c.find('failure') is not None for c in rows),
                errors=sum(c.find('error') is not None for c in rows),
                skipped=sum(c.find('skipped') is not None for c in rows))


assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip() == head
outer = read(work / 'van-position-original-terms-final-r2-process-20261027.json')
final = read(raw / 'receipt.json')
assert outer['state'] == 'COMPLETED' and outer['exit'] == final['exit'] == 0
assert final['completed'] and final['cleaned'] and final['owned_fixture_independently_absent']
assert all(sha(root / p) == h for p, h in final['source_sha256'].items())
assert all(sha(root / p) == h for p, h in final['reference_fixtures_sha256'].items())
assert not read(raw / 'storage-audit.json')['forbidden_events']
counts = cases(raw / 'full-trading.xml')
assert counts == dict(passed=1467, failed=0, errors=0, skipped=0)
assert cases(work / 'van-position-original-terms-baseline-20261027.xml') == dict(passed=2, failed=6, errors=0, skipped=0)
assert cases(work / 'van-position-margin-scale-baseline-20261027.xml') == dict(passed=30, failed=2, errors=0, skipped=0)
assert cases(work / 'van-position-margin-scale-focused-20261027.xml') == dict(passed=224, failed=0, errors=0, skipped=0)
assert read(work / 'van-position-original-terms-fault-fixture-r2-20261027.json')['exit'] == 0
probe = (work / 'van-position-original-terms-invariant-faults-r2-20261027.txt').read_text()
assert '13/13 probes behaved as expected' in probe and 'fuzz CRASHED' not in probe
assert probe.count('fuzz PASSED') == 3 and probe.count('fuzz FAILED') == 10
assert not read(work / 'van-position-original-terms-fault-fixture-r2-audit-20261027.json')['forbidden_events']
rebuild = cases(work / 'van-position-original-terms-rebuild-20261027.xml')
assert rebuild == dict(passed=165, failed=0, errors=0, skipped=0)
assert read(work / 'van-position-original-terms-rebuild-20261027.json')['exit'] == 0
assert not read(work / 'van-position-original-terms-rebuild-audit-20261027.json')['forbidden_events']
registry = read(work / 'van-position-original-terms-registry-20261027.json')
assert not registry['findings'] and registry['mutation_count'] == 374 and registry['edit_count'] == 383
assert registry['execution_state'] == 'NOT_RUN'
old = read(root / 'trading/tests/fixtures/legacy_risk_snapshot_b58bb578.json')
assert old['original_snapshot_hash'] == 'fb9716a45f8e9959a6c4b8871c874d3d4836d2f0182502121f1bf15f074bf300'
assert old['source_authority_sha256'] == hashlib.sha256(subprocess.check_output(
    ['git', 'show', head + ':trading/vati/risk/authority.py'], cwd=root)).hexdigest()
interrupted = read(work / 'van-position-original-terms-final-r1-20261027/receipt.json')
assert interrupted['exit'] != 0 and interrupted['owned_fixture_independently_absent']
hosted = work / 'van-b58bb578-full-hosted'
parent = read(hosted / 'reconciliation.json')
assert parent['source_head'] == head and parent['run_id'] == 40463198811
assert parent['status'].startswith('TERMINAL_FAILURE')
assert cases(hosted / 'van-postgres-ledger-report/trading-source-report.xml') == dict(
    passed=4373, failed=2, errors=0, skipped=1)

# Source qualification above is not unit acceptance, activation or a native certificate.
out = docs / 'ci/position_original_terms_20261027'
assert not out.exists()
shutil.copytree(raw, out / raw.name)
shutil.copytree(work / 'van-position-original-terms-final-r1-20261027',
                out / 'van-position-original-terms-final-r1-20261027')
for pattern in ['van-position-original-terms-*-20261027.*', 'van-position-margin-scale-*-20261027.*']:
    for p in work.glob(pattern):
        if p.is_file() and p.suffix in {'.py', '.json', '.xml', '.log', '.txt'}:
            shutil.copy2(p, out / p.name)
hostout = docs / 'ci/hosted_b58bb578_20261027'
assert not hostout.exists()
shutil.copytree(hosted, hostout)
now = datetime.datetime.now(datetime.timezone.utc).isoformat()
summary = (
    'Both actual native position producers and resting cycle entries now preserve original entry/stop/tick '
    'facts through optional StopRiskTerms. Exact heat and currency risk do not consume rounded tick reports. '
    'Native FULL_STAKE positions retain their builtin stake loss, and illiquid stop/haircut inputs are exact. '
    'Unknown symbol/model/protection still holds new risk. Legacy position/snapshot bodies omit absent optional '
    'terms and reproduce the original b58 hash fb9716a45f8e9959a6c4b8871c874d3d4836d2f0182502121f1bf15f074bf300, '
    'using a fixture generated by executing actual isolated original Git source. Native margin bounds restore '
    'original Decimal subtraction scale and minimum-value spelling; all permission comparisons use exact '
    'original fractions. The original native observation assertions remain unchanged. New projection baseline '
    'reproduced6failures/2controls on unchanged b58; margin regression reproduced2failures/30controls with '
    'unchanged causal sources. Corrected224focused cases pass. First broad run was deliberately interrupted '
    'for that confirmed hosted fix after666recorded passing calls; its signal/tmpstash teardown error and '
    'actual exit1 remain retained, not passed. Owned fixture was independently absent. Stable second combined '
    'actualSQL/HTTP/execution/accounting/authority run1467passed0skip/audit0; all1172Python source/test hashes '
    'and1legacy reference JSON hash match, owned PostgreSQL independently absent.165rebuild/private-topology '
    'cases and13semantic safety probes pass:3controls/10assertion detections/0crashcredit. Selections overlap. '
    'Registry preflight374identities/383edits has0findings, but the full corpus has not executed on this '
    'uncommitted source packet. Published b58 remains failed in its original hosted evidence, including '
    '4373trading passes/2original string failures/1DDSskip. Mandatory DDS/trusted-main prerequisites remain '
    'unwaived. No unit, live-provider, production, economic or S24 acceptance is issued.')
next_action = (
    'Finish real manifest, verified staged archive, genuine candidate-build hook and required-baseline '
    'committed verification; normalpush/readback and qualify exact new hosted head after b58 terminal. '
    'Continue full shared physical-account financial history/collateral/all-origin reservations, payment '
    'and manual/provider/handover reconciliation and all remaining backend features. No new frontend before '
    'BG-001. Van trading core remains the host; provision Android production profile without owner-entered '
    'backend addresses. Native admission, provisioning, signing, deployment and Artemis/S24 remain required.')
receipt = {'schema': 'van.rebuild.original-position-terms-source/1', 'created_at_utc': now,
    'base_head': head, 'state': 'SOURCE_TESTED_UNCOMMITTED_AT_GENERATION', 'units': ['BE-009'],
    'implementation': summary, 'source_tests': counts, 'focused_tests': 224, 'new_cases': 39,
    'source_test_hashes_verified': 1172, 'reference_json_hashes_verified': 1,
    'owned_fixture_independently_absent': True, 'semantic_probes': {'controls': 3, 'detections': 10, 'crash_credit': 0},
    'rebuild': rebuild, 'registry_preflight': registry, 'acceptance': 'NOT_ISSUED', 'next_action': next_action}
write(docs / 'receipts/POSITION_ORIGINAL_TERMS_SOURCE_20261027.json', receipt)
write(docs / 'receipts/HOSTED_SOURCE_b58bb578.json', parent)
(docs / 'backend/BE-009_ORIGINAL_POSITION_TERMS.md').write_text(
    '# Original position terms and native margin compatibility\n\n' + summary + '\n\n' + next_action + '\n\n'
    'This preserves source arithmetic and serialization. It does not share alias financial history, reserve '
    'all-origin collateral, settle fees/assets, grant native authority or complete BE-009.\n')
p = docs / 'CANDIDATE_SOURCE_PROGRESS.json'; d = read(p)
assert all(v['unit_acceptance'] == 'NOT_ISSUED' for v in d['units'].values())
d['updated_at_utc'] = now
d['units']['BE-009']['milestones'].append({'description': summary,
    'evidence': 'backend/BE-009_ORIGINAL_POSITION_TERMS.md;receipts/POSITION_ORIGINAL_TERMS_SOURCE_20261027.json'})
write(p, d)
p = docs / 'EXECUTION_LEDGER.json'; d = read(p)
d['updated_at_utc'] = now; c = d['checkpoint']; c['updated_utc'] = now
c['head'] = c['published_head'] = c['local_base_head'] = head
c['committed_ledger_verification'] = 'Actual published GREEN175 exit0 against4fd466dec3910ed5de614bfbf95887ad619df5ca; new source uncommitted at generation'
c['last_validation'] = summary; c['current_packet'] = 'BE-009_ORIGINAL_POSITION_TERMS_SOURCE_TESTED_UNCOMMITTED'
c['background_jobs'] = c['current_background_jobs'] = []; c['next_action'] = next_action
d['observations'].append(summary); d['current_action'] = next_action
d['continuation']['latest_checkpoint_report'] = 'docs/rebuild/rev118/CHECKPOINT_20261027_POSITION_ORIGINAL_TERMS.md'
write(p, d)
(docs / 'CHECKPOINT_20261027_POSITION_ORIGINAL_TERMS.md').write_text(
    '# Original position terms source continuation\n\n' + now + '\n\n' + summary + '\n\n' + next_action + '\n\n'
    'Programme remains82backend units:30with partial source milestones/52without recorded milestones; '
    '12verification packets and all131formal unit acceptances remain open. Frozen package and every feature, '
    'error state, owner control and frontend contract remain. Inherited source may exist without milestones. '
    'Profitability needs evidence, never a guarantee. No delegation; do not touch /workspace/Van.\n')
write(out / 'evidence-file-hashes.json', {str(p.relative_to(out)): sha(p) for p in out.rglob('*') if p.is_file()})
print(json.dumps({'source': counts, 'python_hashes': 1172, 'reference_json': 1, 'acceptance': 'NOT_ISSUED'}))
