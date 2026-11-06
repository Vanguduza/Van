"""Publish measured source evidence; never issue native or unit acceptance."""
from pathlib import Path
import datetime, gzip, hashlib, json, subprocess
import xml.etree.ElementTree as ET

root = Path('/workspace/van-review-2026-10-18/publish')
base = '748e98b35b2e757d5f615fa0d3bcfc0d93441c06'
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip() == base
run = Path('/workspace/van-native-order-book-full-r1-20261030')
focused = Path('/workspace/van-native-order-book-focused-r1-20261030')
rel = 'receipts/NATIVE_ORDER_RECOVERY_SOURCE_20261030.json'
assert not (root/'docs/rebuild/rev118'/rel).exists(), 'Do not repeat milestones'

def counts(path):
    cases = ET.parse(path).findall('.//testcase')
    return {'passed': sum(not any(c.find(k) is not None for k in ('failure', 'error', 'skipped')) for c in cases),
            'failed': sum(c.find('failure') is not None for c in cases),
            'errors': sum(c.find('error') is not None for c in cases),
            'skipped': sum(c.find('skipped') is not None for c in cases)}

def nodes(path):
    return {s for s in path.read_text().splitlines()
            if s.startswith(('trading/tests/', 'backend/tests/', 'tests/rebuild/')) and '::' in s}

expected = nodes(Path('/workspace/van-native-order-final-collection-20261030.log'))
parent = nodes(Path('/workspace/van-pretrade-durable-budget-final-collection-20261030.log'))
assert len(expected) == 5497 and len(parent) == 5442 and parent <= expected
proofs = {}
for folder, label, count in ((run, 'full', 5497), (focused, 'focused', 191)):
    receipt = json.loads((folder/'receipt.json').read_text())
    assert receipt['completed'] and receipt['exit'] == 0 and receipt['cleaned']
    assert receipt['owned_fixture_independently_absent'] and receipt['base_head'] == base
    assert counts(folder/'full-trading.xml') == {'passed': count, 'failed': 0, 'errors': 0, 'skipped': 0}
    assert not json.loads((folder/'storage-audit.json').read_text())['forbidden_events']
    pins = receipt['source_sha256'] | receipt['reference_fixtures_sha256']
    for p, digest in pins.items():
        assert hashlib.sha256((root/p).read_bytes()).hexdigest() == digest, p
    events = [json.loads(s) for s in (folder/'test-events.jsonl').read_text().splitlines()]
    assert all(e['outcome'] == 'passed' for e in events)
    calls = [e['nodeid'] for e in events if e['phase'] == 'call']
    assert len(calls) == len(set(calls)) == count
    if label == 'full':
        assert set(calls) == expected == {e['nodeid'] for e in events}
    proofs[label] = {'junit': counts(folder/'full-trading.xml'), 'call_identities_unique': True,
                     'storage_violations': 0, 'owned_postgres_independently_absent': True,
                     'source_input_sha256': pins, 'source_pins': len(pins)}
preserved = json.loads(Path('/workspace/van-native-order-all-original-tests-preserved-20261030.json').read_text())
assert preserved['base'] == base and preserved['inherited_test_files'] == preserved['byte_identical']
assert preserved['all_original_test_signatures_preserved'] and preserved['all_original_assertions_preserved']
lite = counts(Path('/workspace/van-native-order-backend-only-20261030.xml'))
assert lite == {'passed':50,'failed':0,'errors':0,'skipped':5}
lite_environment = json.loads(Path('/workspace/van-native-order-backend-only-environment-20261030.json').read_text())
assert not lite_environment['psycopg_present']
assert lite_environment['lock_sha256'] == hashlib.sha256((root/'backend/requirements.lock').read_bytes()).hexdigest()
guards = {}
for name in ('collection', 'workmap', 'owner', 'frontend', 'mutations', 'consolidation'):
    p = Path('/workspace/van-native-order-final-'+name+'-20261030.json')
    result = json.loads(p.read_text())
    assert result['state'] == 'COMPLETED' and result['exit'] == 0
    guards[name] = {'state': result['state'], 'exit': result['exit']}
protocol = {}
for name in ('OpenApiCommonMessages.proto', 'OpenApiCommonModelMessages.proto', 'OpenApiMessages.proto',
             'OpenApiModelMessages.proto', 'PROVENANCE.json'):
    p = 'trading/vati/execution/ctrader/proto/'+name
    b = (root/p).read_bytes()
    assert b == subprocess.check_output(['git', 'show', base+':'+p], cwd=root)
    protocol[p] = hashlib.sha256(b).hexdigest()
raw = root/'docs/rebuild/rev118/ci/native_order_recovery_20261030'
raw.mkdir(parents=True, exist_ok=False)

def copy(source, dest):
    source = Path(source); dest = raw/dest; dest.parent.mkdir(parents=True, exist_ok=True)
    b = source.read_bytes()
    if dest.suffix == '.gz':
        dest.write_bytes(gzip.compress(b, mtime=0)); assert gzip.decompress(dest.read_bytes()) == b
    else:
        dest.write_bytes(b); assert dest.read_bytes() == b

for folder, label in ((run, 'full'), (focused, 'focused')):
    for name in ('receipt.json', 'storage-audit.json', 'full-trading.log', 'full-trading.xml', 'test-events.jsonl', 'targets.txt'):
        copy(folder/name, label+'/'+name+('.gz' if name.endswith('.jsonl') else ''))
    copy(str(folder)+'.py', label+'/controller.py')
for prefix in ('van-native-order-details-first-20261030', 'van-native-order-details-r2-20261030',
               'van-native-order-book-before-20261030', 'van-native-order-book-r1-20261030',
               'van-native-order-book-r2-20261030',
               'van-native-order-backend-only-20261030',
               *('van-native-order-final-'+name+'-20261030' for name in guards)):
    for suffix in ('.json', '.log', '.xml'):
        p = Path('/workspace')/(prefix+suffix)
        if p.exists(): copy(p, p.name)
for name in ('van-native-order-all-original-tests-preserved-20261030.json',
             'van-native-order-backend-only-environment-20261030.json',
             'van-native-order-details-wip1-20261030.json', 'van-native-order-book-wip2-20261030.json',
             'van-748e98b3-cognitive-python-original-readback-20261030.json',
             'van-748e98b3-ledger-failed-original-20261030.log',
             'van-748e98b3-backend-failed-original-20261030.log',
             'van-native-orders-resume-main-20261030.json', 'van-native-orders-resume-cognitive-20261030.json'):
    copy('/workspace/'+name, name)
copy(__file__, 'evidence-builder.py')
now = datetime.datetime.now(datetime.UTC).isoformat()
summary = ('Original cTrader order details now retain account-bound raw order/deal facts, absent optional fields, '
           'conflicting execution totals and original query availability. The actual execution router reads an already '
           'dispatched native order through a durable request journal bound to its original command, native margin '
           'input and receipt-owned order identity. Reopened and repeated requests return their first committed result '
           'without another provider call. Writer acquisition rechecks expiry; staged caller transactions cannot query '
           'or publish original evidence; lost commit/readback acknowledgements require original-request recovery. '
           'The existing pending-risk owner observes new journal records and blocks fills contradicting no-effect '
           'receipts, overfill, changed deals and unreconciled native facts. A cancelled or empty snapshot does not '
           'release original pending quantity, prove flatness, finalize fees or authorize execution. '
           'Full affected source suite: 5,497 passed, no failures/errors/skips/storage violations; all 5,442 parent '
           'cases retained with 55 additional cases. Focused real PostgreSQL selection: 191 passed, no '
           'failures/errors/skips/storage violations. These overlapping suites are not additive. '
           'Owned PostgreSQL fixtures are independently absent. All inherited tests in trading/tests, backend/tests '
           'and tests/rebuild are byte-identical to the published parent. This is a partial BE-003/009/010 source packet; '
           'cancellation/amend/replace, full parent budgets, all-origin financial reservations and native qualification '
           'remain required.')
next_action = ('Commit with genuine Project Truth hooks; complete required-baseline committed verification before '
               'normal push, independently read remote and exact-head hosted CI. Continue complete native '
               'cancel/amend/replace and original-operation reconciliation, protection, immutable parent/child budgets '
               'and shared all-origin financial reservations. Retain complete fees/fills/prices/FX/principal, '
               'policy/cohort admission and late correction/finality obligations. Then finish all original market, '
               'assistant/voice, learning/38 forecast/research, crypto and operations units and all 12 backend '
               'verification packets. Android follows actual BG-001, uses its provisioned production profile on '
               'Van trading core, and needs genuine signing and Artemis/S24 acceptance. Profitability remains an '
               'evidence-based objective, never guaranteed.')
receipt = {'schema': 'van.rev118.native-order-recovery-source/1', 'observed_at_utc': now, 'source_parent': base,
           'state': 'PARTIAL_CANDIDATE_SOURCE_TESTED_NOT_CANCELLATION_OR_FINANCIAL_RELEASE',
           'implementation': summary, 'checks': proofs, 'guards': guards, 'preservation': preserved,
           'backend_lock_only_new_cases': {'junit':lite,'environment':lite_environment,
               'same_five_pg_cases_executed_in_primary_and_focused':True,'overlapping_counts_not_additive':True},
           'all_parent_cases_retained': True, 'original_protocol_reference_sha256': protocol,
           'authority': ['auth-20261022-owner-autonomous-candidate-build'],
           'raw': 'ci/native_order_recovery_20261030', 'formal_acceptance': 'NOT_ISSUED',
           'execution_authority': False, 'reservation_qualified': False, 'native_qualified': False,
           'retained_failures': ['Before pending-owner wiring:2 failed/11 passed. The actual owner ignored a new '
                                 'fill contradicting a no-effect receipt and a changed original deal. Both failures '
                                 'remain in raw evidence; no assertion was weakened.'],
           'parent_hosted_evidence': {'commit': base, 'cognitive_run': 41034920891,
               'python_job': 123993298309, 'android_job': 123993298535, 'jobs': 'SUCCESS',
               'python_original_artifact': 12967054604, 'broad': {'passed':5126,'skipped':311,'failed':0,'errors':0},
               'focused': {'passed':79,'skipped':0,'failed':0,'errors':0},
               'main_run':41034920901, 'failed_jobs':[123993298865,123993298879],
               'actual_failure_reasons':['trustedmain8eb188 lacks the ledger checker','private DDS deploykey not provisioned'],
               'gates_preserved':True, 'not_current_candidate_validation':True},
           'remaining': ['No live broker/account or independent/native acceptance was executed.',
               'Native observation uses the existing request timeout with local deadline checks; it does not qualify provider clocks or hard interruptibility.',
               'No cancellation/amend/replace transport or durable effect lifecycle, complete cross-child identity/correction reconciliation, financial release or settlement owner is supplied by this packet.',
               'Policy/runtime-cohort qualification, immutable parent lifetime budgets, complete multi-asset economic obligations and all-origin reservations remain open.',
               'Every original 82 backend unit,12 verification packet,38 forecast/research unit and gated Android contract retains its full scope.'],
           'next':next_action}
(root/'docs/rebuild/rev118'/rel).write_text(json.dumps(receipt, indent=2)+'\n')
for name in ('EXECUTION_LEDGER.json', 'CANDIDATE_SOURCE_PROGRESS.json'):
    p=root/'docs/rebuild/rev118'/name; d=json.loads(p.read_text()); d['updated_at_utc']=now
    if name=='EXECUTION_LEDGER.json':
        d['observations'].append(summary); d['current_action']=next_action
        for uid in ('BE-003','BE-009','BE-010'):
            if rel not in d['units'][uid]['evidence']: d['units'][uid]['evidence'].append(rel)
    else:
        for uid in ('BE-003','BE-009','BE-010'):
            d['units'][uid]['milestones'].append({'description':summary,'evidence':rel})
    p.write_text(json.dumps(d,indent=2)+'\n')
p=root/'docs/rebuild/rev118/CONTINUATION_20261022.md'
p.write_text(p.read_text()+'\n\n## Original native order readback — 30 October\n\n'+summary+
             '\n\n[Source receipt]('+rel+'). '+next_action+'\n')
p=root/'docs/rebuild/rev118/BUILD_EXECUTION_PLAN.md'; s=p.read_text()
a=s.index('## Current concrete gap and next result'); b=s.index('## Commands and evidence economy',a)
p.write_text(s[:a]+'## Current concrete gap and next result\n\n'+summary+'\n\n[Current source receipt]('+rel+'). '+
             next_action+'\n\nKeep all original work fronts and unit identities above; source-tested subpaths issue '
             'no formal unit acceptance. Reuse the separately reported completed browser Harness repair when its '
             'actual Van consumer is dependency-ready, preserving native admission and interactive binding requirements.\n\n'+s[b:])
doc = '# Original native order readback and pending-risk integration\n\n'+summary+(
    '\n\n`ExecutionRouter.observe_native_order` calls the actual adapter and `NativeOrderBook`. '
    'Only original receipt-owned order IDs can be queried in that command workflow. Account, native symbol and '
    'side bind to the independently committed original margin/command input; order labels supply no authority. '
    'The pinned protocol is unchanged. The source socket-peer test executes framing/authentication/query and '
    'cleans up its own peer and readers; it does not connect a live broker.\n\n'
    'The journal retains original request identity, before/after native account identity, raw response, exact '
    'native integer volumes and the first durable publication. Duplicate identical deals within an order are '
    'counted once; conflicting snapshots remain unreconciled. Optional fee fields never erase known fills. '
    'The journal does not equate a native snapshot volume with original or remaining parent allowance. '
    'Later missing rows cannot erase previously observed fills. The existing risk owner reloads on new '
    'observations, retains conservative original exposure and blocks contradictory or unreconciled facts.\n\n'
    'SQL/commit/readback/expiry/concurrency tests use actual SQLite and PostgreSQL. The original two '
    'failing pending-owner counterexamples are preserved. All inherited assertions and functions are unchanged. '
    'Complete evidence is in the [source receipt](../'+rel+').\n\n'
    'Full native cancellation, atomic amend, cancel-replace, uncertain/late effects, cross-child identities, '
    'protection and nonduplicated reservation release remain required effectful workflows. Read-only recovery '
    'does not replace them. Cash, fees, order finality and flatness retain separate owners and acceptance.\n\n')+next_action+'\n'
(root/'docs/rebuild/rev118/backend/BE-003_009_010_NATIVE_ORDER_RECOVERY.md').write_text(doc)
print(json.dumps({'full_passed':5497,'focused_passed':191,'source_pins':proofs['full']['source_pins'],
                  'preserved_files':preserved['byte_identical'],'raw_files':sum(p.is_file() for p in raw.rglob('*')),
                  'receipt':rel}))
