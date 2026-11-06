"""Build source evidence only after the original qualification process exits."""
from collections import Counter
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as E

root = Path('/workspace/van-review-2026-10-18/publish')
work = Path('/workspace')
docs = root / 'docs/rebuild/rev118'
head = '74b1749a97c9d647776384e9a4da7d4e371f1b4b'
raw = work / 'van-native-risk-context-final-r3-20261027'


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
outer = read(work / 'van-native-risk-context-final-r3-process-20261027.json')
final = read(raw / 'receipt.json')
assert outer['state'] == 'COMPLETED' and outer['exit'] == final['exit'] == 0
assert final['completed'] and final['cleaned'] and final['owned_fixture_independently_absent']
assert len(final['source_sha256']) == 1175
assert all(sha(root / p) == h for p, h in final['source_sha256'].items())
assert all(sha(root / p) == h for p, h in final['reference_fixtures_sha256'].items())
assert len(final['reference_fixtures_sha256']) == 2
assert cases(work / 'van-native-risk-context-final-r2-20261027/full-trading.xml') == dict(passed=758, failed=1, errors=0, skipped=0)
assert read(work / 'van-native-risk-context-final-r2-process-20261027.json')['exit'] == 1
assert read(work / 'van-native-risk-context-final-r2-20261027/receipt.json')['owned_fixture_independently_absent']
original74 = read(work / 'van-native-context-original74-serializer-20261027.json')
assert original74['snapshot_hash'] == original74['legacy_dict_hash'] == 'b046ce938b014c35fea53299f62d6d9067fa1221863528391f4e5f7f334f4c4f'
assert 'native_account_context' not in original74['dataclass_fields']
assert read(root / 'trading/tests/fixtures/legacy_risk_snapshot_no_margin_74b1749a.json')['snapshot'] == original74['body']
assert not read(raw / 'storage-audit.json')['forbidden_events']
counts = cases(raw / 'full-trading.xml')
assert counts == dict(passed=759, failed=0, errors=0, skipped=0)
collection = read(work / 'van-native-risk-context-final-collection-20261027.json')['nodeids']
assert len(collection) == len(set(collection)) == 759
assert sum('test_native_risk_account_context' in i for i in collection) == 43
events = [json.loads(s) for s in (raw / 'test-events.jsonl').read_text().splitlines()]
assert Counter(e['nodeid'] for e in events if e['phase'] == 'call' and e['outcome'] == 'passed') == Counter(collection)
assert not [e for e in events if e['outcome'] != 'passed']
assert cases(work / 'van-native-risk-context-focused-r6-20261027.xml') == dict(passed=308, failed=0, errors=0, skipped=0)
assert not read(work / 'van-native-risk-context-focused-r6-20261027-audit.json')['forbidden_events']
assert cases(work / 'van-native-risk-context-held-producer-probe-20261027.xml') == dict(passed=0, failed=2, errors=0, skipped=0)
assert cases(work / 'van-native-risk-context-published74-hold-controls-20261027.xml') == dict(passed=2, failed=0, errors=0, skipped=0)
interrupted = read(work / 'van-native-risk-context-final-r1-20261027/receipt.json')
assert interrupted['exit'] == 2 and interrupted['owned_fixture_independently_absent']
assert read(work / 'van-native-risk-context-final-r1-process-20261027.json')['exit'] == 2
assert read(work / 'van-native-risk-context-fault-final-20261027.json')['exit'] == 0
probe = (work / 'van-native-risk-context-invariant-faults-final-20261027.txt').read_text()
assert '13/13 probes behaved as expected' in probe and 'fuzz CRASHED' not in probe
assert probe.count('fuzz PASSED') == 3 and probe.count('fuzz FAILED') == 10
assert not read(work / 'van-native-risk-context-fault-final-20261027-audit.json')['forbidden_events']
rebuild = cases(work / 'van-native-risk-context-rebuild-final-20261027.xml')
assert rebuild == dict(passed=165, failed=0, errors=0, skipped=0)
assert read(work / 'van-native-risk-context-rebuild-final-20261027.json')['exit'] == 0
assert not read(work / 'van-native-risk-context-rebuild-final-20261027-audit.json')['forbidden_events']
registry = read(work / 'van-native-risk-context-final-mutation_registry-20261027.log')
assert registry['mutation_count'] == 374 and registry['edit_count'] == 383 and not registry['findings']
assert registry['execution_state'] == 'NOT_RUN'
assert read(work / 'van-native-risk-context-final-owner_registry-20261027.log')['changed'] == []
assert read(work / 'van-native-risk-context-final-frontend_registry-20261027.log')['changed'] is False
assert read(work / 'van-native-risk-context-final-consolidation-20261027.log')['findings'] == []
hosted = work / 'van-74b1749a-full-hosted'
parent = read(hosted / 'reconciliation.json')
assert parent['source_head'] == head and parent['public_jobs_success'] == 17
assert parent['status'] == 'TERMINAL_FAILURE_ONLY_TWO_MANDATORY_PREREQUISITES_UNWAIVED'
assert parent['canonical_mutations']['caught_exactly_once'] == 374
assert cases(hosted / 'van-postgres-ledger-report/trading-source-report.xml') == dict(passed=4414, failed=0, errors=0, skipped=1)

out = docs / 'ci/native_risk_account_context_20261027'
assert not out.exists()
shutil.copytree(raw, out / raw.name)
shutil.copytree(work / 'van-native-risk-context-final-r1-20261027', out / 'van-native-risk-context-final-r1-20261027')
shutil.copytree(work / 'van-native-risk-context-final-r2-20261027', out / 'van-native-risk-context-final-r2-20261027')
for p in work.glob('van-native-context-original74-serializer*-20261027.*'):
    if p.is_file() and p.suffix in {'.json', '.py', '.log'}: shutil.copy2(p, out / p.name)
for p in work.glob('van-native-risk-context-*-20261027.*'):
    if p.is_file() and p.suffix in {'.py', '.json', '.xml', '.log', '.txt'}:
        shutil.copy2(p, out / p.name)
shutil.copy2(work / 'van_context_collection_snapshot.py', out / 'van_context_collection_snapshot.py')
hostout = docs / 'ci/hosted_74b1749a_20261027'
assert not hostout.exists()
shutil.copytree(hosted, hostout)
now = datetime.datetime.now(datetime.timezone.utc).isoformat()
summary = (
    'Optional immutable NativeAccountRiskContext binds original MT5 native source/query references and '
    'cTrader native account marks into actual risk snapshots, decisions and durable replay. The physical '
    'key omits presentation aliases, while the monetary scope and original source labels remain explicit. '
    'Both real snapshot producers capture the original source without provider/order I/O. Strict metadata '
    'validation binds provider/venue, alias, currency, original balance/equity, time and source references. '
    'Typed flags remain risk_capital_qualified=False and execution_authority=False. Legacy absent fields '
    'are omitted from serialization and hashing, including the original executed-b58 fixture hash. '
    'Actual SQLite decision/replay tests reject a changed source reference; original PostgreSQL query '
    'receipt and first availability survive restart/lost commit acknowledgement and cannot cross named '
    'ledgers. Expanded failure tests preserve original funding holds, baselines and private diagnostics. '
    'Two new-WIP builder failures were reproduced; both exact published74 methods retain the two original '
    'hold controls. The first broad run was deliberately interrupted after703 passing calls for that '
    'confirmed correction, actual exit2/ownedPG independently absent, not a passing run. Second run758passed/1failed: an inherited synthetic legacy fixture used asdict(currentclass) and thereby invented the new optional field in an old body. Executing the exact original published74 serializer independently proves the original b046...hash is unchanged. The test now uses that original output, retains both original hash assertions and adds exact body and historical hash comparisons. Its original failed run/exit1/ownedPG cleanup remain retained. Final308 focused '
    'and759 combined native/risk/account/execution/expiry/recovery/SQL/HTTP cases pass0skip/audit0; all759 '
    'independently collected identities execute once, including43 new cases. All1175Python source/test '
    'hashes and both original legacy reference JSONs match; the owned PostgreSQL fixture is independently '
    'absent. Final165 rebuild/private-topology cases and13 safety probes pass:3controls/10semantic '
    'assertion detections/0crashcredit. These selections overlap. The final38-file SQL/HTTP selection '
    'covers the changed integration; unchanged payment/provider authority selections from the interrupted '
    'broader run are not claimed as final-packet passes. Registry preflight374/383 has zero findings and '
    'is not mutation execution on this packet. Exact published74 independently verifies4414trading/1DDSskip, '
    '26PG,117voice,5854gateway/7declaredskips,198media,258monitor and374canonicalidentities caught once. '
    'Main40471188480 remainsFAILED two mandatory prerequisites/all17public jobsSUCCESS. Four supporting '
    'workflows reportSUCCESS; original forecast source/kernel/cleanup/hash evidence and cognitive79/4206 '
    'with245declaredPG-DDSskips and1568Android source cases are reconciled. Parent CI does not qualify this '
    'new uncommitted source. No unit, native/provider, production, economic or S24 acceptance is issued.')
next_action = (
    'Run the real manifest and verified full staged archive; commit through genuine candidate-build hooks, '
    'then run committed ledger verification against4fd466dec3910ed5de614bfbf95887ad619df5ca; normalpush and '
    'independent readback, then inspect exact new hosted CI. Continue shared physical financial history '
    'without assigning old history from current configuration or silently expanding alias-scoped owner '
    'reset grants. Complete collateral/all-origin reservations, payment/manual/provider/handover '
    'reconciliation and all remaining backend contracts and verification. New frontend remains behind '
    'BG-001; Van trading core is the host and Android must use a provisioned production profile without '
    'owner-entered addresses. Native admission, provisioning, signing and actual Artemis/S24 remain open.')
receipt = {'schema': 'van.rebuild.native-risk-account-context-source/1', 'created_at_utc': now,
    'base_head': head, 'state': 'SOURCE_TESTED_UNCOMMITTED_AT_GENERATION', 'units': ['BE-009'],
    'implementation': summary, 'source_tests': counts, 'source_selection_files': 38,
    'independently_collected_cases': 759, 'focused_tests': 308, 'new_cases': 43,
    'source_test_hashes_verified': 1175, 'reference_json_hashes_verified': 2,
    'owned_fixture_independently_absent': True,
    'semantic_probes': {'controls': 3, 'detections': 10, 'crash_credit': 0},
    'rebuild': rebuild, 'registry_preflight': registry, 'acceptance': 'NOT_ISSUED', 'next_action': next_action}
write(docs / 'receipts/NATIVE_RISK_ACCOUNT_CONTEXT_SOURCE_20261027.json', receipt)
write(docs / 'receipts/HOSTED_SOURCE_74b1749a.json', parent)
(docs / 'backend/BE-009_NATIVE_RISK_ACCOUNT_CONTEXT.md').write_text(
    '# Original native account source in risk snapshots\n\n' + summary + '\n\n' + next_action + '\n\n'
    'This preserves provenance. It does not share financial history, collateral or reservations, '
    'qualify cash, authorize orders, widen owner reset grants, or complete BE-009.\n')
p = docs / 'CANDIDATE_SOURCE_PROGRESS.json'; d = read(p)
assert all(v['unit_acceptance'] == 'NOT_ISSUED' for v in d['units'].values())
d['updated_at_utc'] = now
d['units']['BE-009']['milestones'].append({'description': summary,
    'evidence': 'backend/BE-009_NATIVE_RISK_ACCOUNT_CONTEXT.md;receipts/NATIVE_RISK_ACCOUNT_CONTEXT_SOURCE_20261027.json'})
write(p, d)
p = docs / 'EXECUTION_LEDGER.json'; d = read(p)
d['updated_at_utc'] = now; c = d['checkpoint']; c['updated_utc'] = now
c['head'] = c['published_head'] = c['local_base_head'] = head
c['committed_ledger_verification'] = 'Published74 genuine GREEN176 required-baseline actualexit0; newpacket uncommitted at generation'
c['last_validation'] = summary; c['current_packet'] = 'BE-009_NATIVE_RISK_ACCOUNT_CONTEXT_SOURCE_TESTED_UNCOMMITTED'
c['background_jobs'] = c['current_background_jobs'] = []; c['next_action'] = next_action
d['observations'].append(summary); d['current_action'] = next_action
d['continuation']['latest_checkpoint_report'] = 'docs/rebuild/rev118/CHECKPOINT_20261027_NATIVE_RISK_ACCOUNT_CONTEXT.md'
write(p, d)
(docs / 'CHECKPOINT_20261027_NATIVE_RISK_ACCOUNT_CONTEXT.md').write_text(
    '# Native risk-account source continuation\n\n' + now + '\n\n' + summary + '\n\n' + next_action + '\n\n'
    'Programme remains82backend units:30with partial source milestones/52without recorded milestones; '
    '12verification packets and all131formal unit acceptances remain open. Preserve the frozen package, '
    'all features, error states, owner controls and frontend contracts. Inherited code may exist without '
    'milestones. Profitability requires evidence. No delegation; do not touch /workspace/Van.\n')
p = docs / 'BACKEND_STATUS_20261027.md'; s = p.read_text()
start = s.index('An uncommitted source packet') if 'An uncommitted source packet' in s else s.index('An uncommitted ten-file source packet')
end = s.index('\n\nThis source identity', start)
s = s[:start] + ('The uncommitted ten-file native account risk-context packet has passed308 focused and759 combined SQL/HTTP/PostgreSQL cases with0 skips and0 audit violations. All759 independently collected identities executed once;1175 Python source/test hashes and both historical reference JSONs match. Owned PostgreSQL cleanup is independently verified. Earlier R1 interruption703passes/exit2 and R2 legacy-fixture failure758passes/1failure remain retained. The final corrected fixture comes from actually executing the exact original published74 serializer and retains both original hash assertions plus exact body comparison.165 rebuild and13 semantic probes pass on unchanged application sources. Full exact-head hosted qualification and independent/native acceptance remain open. The verified ten-file source archive is `/workspace/van-native-risk-context-source-wip-r4-20261027.zip`, SHA256 `a705cac7ef1ffdf604ca0c6ee632f9e9558022e2af3c9b2df1958c9b2df80147`.') + s[end:]
import re
s = re.sub(r'Observed UTC: `[^`]+`', 'Observed UTC: `' + now + '`', s)
p.write_text(s)
write(out / 'evidence-file-hashes.json', {str(p.relative_to(out)): sha(p) for p in out.rglob('*') if p.is_file()})
print(json.dumps({'source': counts, 'python_hashes': 1175, 'new_cases': 43, 'acceptance': 'NOT_ISSUED'}))
