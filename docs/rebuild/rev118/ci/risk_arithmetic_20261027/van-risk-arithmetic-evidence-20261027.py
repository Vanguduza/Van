"""Write candidate evidence only after actual terminal source qualification."""
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
raw = work / 'van-risk-arithmetic-final-r1-20261027'
head = '068267e2901d0e1d62c29d101e83860916461bec'
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip() == head


def read(p):
    return json.loads(p.read_text())


def write(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, indent=2) + '\n')


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def cases(p):
    rows = list(E.parse(p).getroot().iter('testcase'))
    return dict(passed=sum(all(c.find(k) is None for k in ('failure', 'error', 'skipped')) for c in rows),
                failed=sum(c.find('failure') is not None for c in rows),
                errors=sum(c.find('error') is not None for c in rows),
                skipped=sum(c.find('skipped') is not None for c in rows))


final = read(raw / 'receipt.json')
controller = read(work / 'van-risk-arithmetic-final-r1-process-20261027.json')
assert controller['state'] == 'COMPLETED' and controller['exit'] == 0
assert final['completed'] and final['exit'] == 0
assert final['cleaned'] and final['owned_fixture_independently_absent']
assert final['base_head'] == head
assert all(sha(root / p) == h for p, h in final['source_sha256'].items())
assert not read(raw / 'storage-audit.json')['forbidden_events']
counts = cases(raw / 'full-trading.xml')
assert counts['passed'] > 1000 and counts['failed'] == counts['errors'] == counts['skipped'] == 0
new = [c for c in E.parse(raw / 'full-trading.xml').getroot().iter('testcase')
       if c.get('classname') == 'trading.tests.test_risk_arithmetic_context']
assert len(new) == 24
assert cases(work / 'van-risk-arithmetic-baseline-20261027.xml') == dict(passed=1, failed=7, errors=0, skipped=0)
for name, controls in [('report-ratio', 9), ('tick', 10), ('cost', 23)]:
    assert cases(work / ('van-risk-arithmetic-' + name + '-baseline-20261027.xml')) == dict(
        passed=controls, failed=1, errors=0, skipped=0)
focused = cases(work / 'van-risk-arithmetic-final-focused-20261027.xml')
assert focused == dict(passed=190, failed=0, errors=0, skipped=0)
rebuild = cases(work / 'van-risk-arithmetic-rebuild-20261027.xml')
assert rebuild['passed'] >= 165 and rebuild['failed'] == rebuild['errors'] == rebuild['skipped'] == 0
assert read(work / 'van-risk-arithmetic-rebuild-20261027.json')['exit'] == 0
assert not read(work / 'van-risk-arithmetic-rebuild-audit-20261027.json')['forbidden_events']
assert read(work / 'van-risk-arithmetic-fault-fixture-final-20261027.json')['exit'] == 0
assert cases(work / 'van-risk-arithmetic-fault-fixture-final-20261027.xml') == dict(passed=1, failed=0, errors=0, skipped=0)
probe = (work / 'van-risk-arithmetic-invariant-faults-valid-owner-20261027.txt').read_text()
assert '13/13 probes behaved as expected' in probe and 'fuzz CRASHED' not in probe
assert probe.count('fuzz PASSED') == 3 and probe.count('fuzz FAILED') == 10
assert not read(work / 'van-risk-arithmetic-fault-fixture-final-audit-20261027.json')['forbidden_events']
registry = read(work / 'van-risk-arithmetic-registry-final-20261027.json')
assert registry['mutation_count'] == 374 and registry['edit_count'] == 383 and registry['findings'] == []
assert registry['execution_state'] == 'NOT_RUN'
hosted = work / 'van-068267e2-full-hosted'
parent = read(hosted / 'reconciliation.json')
assert parent['public_jobs_success'] == 17 and parent['source_head'] == head
assert parent['canonical_mutations']['caught_exactly_once'] == 374
assert read(hosted / 'independent-reconciliation.json')['run'] == 40454839421
assert read(hosted / 'cognitive-reconciliation.json')['broad_python_declared_skips'] == 245
assert cases(work / 'van-position-source-arithmetic-probe-20261027.xml') == dict(
    passed=2, failed=2, errors=0, skipped=0)

# All validation above precedes repository writes. These are source receipts,
# never native certificates, production qualifications or accepted unit rows.
out = docs / 'ci/risk_arithmetic_20261027'
assert not out.exists()
shutil.copytree(raw, out / raw.name)
for p in work.glob('van-risk-arithmetic-*-20261027.*'):
    if p.suffix in {'.json', '.xml', '.log', '.txt', '.py'} and p.is_file():
        shutil.copy2(p, out / p.name)
for p in work.glob('van-position-source-arithmetic-probe*-20261027.*'):
    if p.suffix in {'.json', '.xml', '.log', '.py'} and p.is_file():
        shutil.copy2(p, out / p.name)
hostout = docs / 'ci/hosted_068267e2_20261027'
assert not hostout.exists()
shutil.copytree(hosted, hostout)
now = datetime.datetime.now(datetime.timezone.utc).isoformat()
summary = (
    'Risk sizing, portfolio heat, currency legs, loss/drawdown and cost gates now use original bounded '
    'Decimal facts as exact Fractions for permission comparisons. Venue quantities round down exactly; '
    'new-position loss uses original quantity, price and tick terms. Repeating Decimal values are reports '
    'only. Fresh complete arithmetic contexts ignore caller/default precision, traps, exponent range and '
    'clamp without mutating them. All original signed mandate/intent bindings, refusal codes, public '
    'Decimal fields and owner ceilings remain. Original0682 causal sources reproduced7failures/1control; '
    'intermediate report-ratio, original-tick and cost boundaries each reproduced1failure with9/10/23controls. '
    'Final190focused cases and' + str(counts['passed']) + 'combined actualSQL/HTTP/accounting/authority/execution '
    'cases pass0skip/audit0; all' + str(len(final['source_sha256'])) + 'source-test hashes match, ownedPGfixture '
    'independently absent. ' + str(rebuild['passed']) + 'rebuild/private-topology cases pass. Existing13safetyprobes '
    'produce3passing controls and10semantic assertion detections with0crashcredit. The initial missing-owner '
    'probe run and intermediate runtime-exception outcomes remain invalid semantic evidence and are retained. '
    'Canonical registry preflight374cases/383edits has0findings, but that corpus has not executed on this '
    'uncommitted risk packet. Exact published0682 independently records4351trading/1DDSskip,26PG,117voice, '
    '5854gateway/7skips,198media and374canonical cases caught once; main40454839376 remainsFAILED2mandatory '
    'prerequisites/all17publicSUCCESS. Forecast40454839421 independently verifies114native cases,6synthetic '
    'fixtures,3cold models/parity0/232versions/kernel/cleanup/hashes. Cognitive40454839472SUCCESS has79focused, '
    '4143broad with245declaredPG/DDSskips and1568Androidsource cases. Parent evidence does not qualify later '
    'risk source. No unit/native/production/economic/S24 acceptance is issued.')
next_action = (
    'Finish real manifest, verified staged backup, genuine candidate-build hook and required-baseline '
    'committed verification; normalpush/readback and inspect exact hosted CI. Continue canonical shared '
    'physical-account financial history, collateral and all-origin reservations, full payment/provider/manual '
    'reconciliation and remaining backend programme. No new frontend before BG-001. Van trading core remains '
    'the chosen host; Android uses a provisioned production profile without owner-entered backend addresses. '
    'Independent admission, provisioning, signing, deployment and actual Artemis/S24 acceptance remain open.')
receipt = {'schema': 'van.rebuild.exact-risk-arithmetic-source/1', 'created_at_utc': now,
           'base_head': head, 'state': 'SOURCE_TESTED_UNCOMMITTED_AT_GENERATION', 'units': ['BE-009'],
           'implementation': summary, 'source_tests': counts, 'focused_tests': focused,
           'new_regression_cases': 24, 'rebuild_private_topology': rebuild,
           'verified_source_test_hashes': len(final['source_sha256']),
           'owned_fixture_independently_absent': True,
           'semantic_probes': {'controls': 3, 'assertion_detections': 10, 'runtime_crash_credit': 0},
           'canonical_registry_preflight': registry, 'evidence_directory': str(out.relative_to(docs)),
           'acceptance': 'NOT_ISSUED', 'next_action': next_action}
write(docs / 'receipts/RISK_ARITHMETIC_SOURCE_20261027.json', receipt)
write(docs / 'receipts/HOSTED_SOURCE_068267e2.json', parent)
(docs / 'backend/BE-009_EXACT_RISK_ARITHMETIC.md').write_text(
    '# Exact native risk arithmetic source candidate\n\n' + summary + '\n\n' + next_action + '\n\n'
    'This packet closes a confirmed source arithmetic defect. It does not complete BE-009: shared financial '
    'lineage, physical-account collateral/reservations, uncertain effects, provider fee/asset accounting, '
    'manual/automated ownership and native admission still require their original full contracts. Native '
    'position projection also needs its own original entry/stop/tick arithmetic repair: a separate bounded '
    'unit probe on unchanged account_service/cycle sources reproduces2low-precision failures with2normal '
    'controls; it is not a native-connectivity or end-to-end approval bypass claim. Historical '
    'decision bodies and byte references are not rewritten; newly computed reports and hashes can differ.\n')
p = docs / 'CANDIDATE_SOURCE_PROGRESS.json'; d = read(p)
assert d['units']['BE-009']['unit_acceptance'] == 'NOT_ISSUED'
d['updated_at_utc'] = now
d['units']['BE-009']['milestones'].append({'description': summary,
    'evidence': 'backend/BE-009_EXACT_RISK_ARITHMETIC.md;receipts/RISK_ARITHMETIC_SOURCE_20261027.json'})
assert all(v['unit_acceptance'] == 'NOT_ISSUED' for v in d['units'].values())
write(p, d)
p = docs / 'EXECUTION_LEDGER.json'; d = read(p)
d['updated_at_utc'] = now; d['checkpoint']['updated_utc'] = now
d['checkpoint']['last_validation'] = summary
d['checkpoint']['current_packet'] = 'BE-009_EXACT_RISK_ARITHMETIC_SOURCE_TESTED_UNCOMMITTED'
d['checkpoint']['current_background_jobs'] = []
d['observations'].append(summary); d['current_action'] = next_action
d['continuation']['latest_checkpoint_report'] = 'docs/rebuild/rev118/CHECKPOINT_20261027_RISK_ARITHMETIC.md'
d['continuation']['verified_source_head'] = head + ' published genuineGREEN174; risk packet uncommitted at generation'
write(p, d)
(docs / 'CHECKPOINT_20261027_RISK_ARITHMETIC.md').write_text(
    '# Exact risk arithmetic and published qualification checkpoint\n\n' + now + '\n\n' + summary + '\n\n' +
    next_action + '\n\n'
    'There are82backend units:30with partial source milestones/52without recorded milestones;12backend '
    'verification packets remain open and all131unit acceptances areNOT_ISSUED. Inherited source may exist '
    'without recorded milestones. Frozen131units/324requirements/1610acceptances/234contexts/349actions/93features '
    'and original42featuregroups/105functionIDs/78surfaces remain. Current483endpoints/376schemas preserve their '
    'contracts. Every assistant, voice, trading, research, learning, crypto and operations obligation remains. '
    'Profitability is evidence to evaluate, never a guarantee. No delegation; do not touch /workspace/Van.\n')
write(out / 'evidence-file-hashes.json', {str(p.relative_to(out)): sha(p) for p in out.rglob('*') if p.is_file()})
print(json.dumps({'source': counts, 'source_test_hashes': len(final['source_sha256']),
                  'new_risk_cases': len(new), 'rebuild': rebuild, 'acceptance': 'NOT_ISSUED'}))
