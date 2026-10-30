"""Executed candidate source evidence; never native or unit acceptance."""
from pathlib import Path
import datetime, gzip, hashlib, json, subprocess
import xml.etree.ElementTree as ET

root=Path('/workspace/van-review-2026-10-18/publish')
base='02e8e712da17a0c70b19e3e1a9dfbed394e58061'
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()==base
rel='receipts/NATIVE_CANCEL_SOURCE_20261030.json'
assert not (root/'docs/rebuild/rev118'/rel).exists(), 'Do not duplicate milestones'
full=Path('/workspace/van-native-cancel-full-r1-20261030')
focused=Path('/workspace/van-native-cancel-focused-r2-20261030')

def counts(path):
    cases=ET.parse(path).findall('.//testcase')
    return {'passed':sum(not any(c.find(k)is not None for k in ('failure','error','skipped')) for c in cases),
            'failed':sum(c.find('failure')is not None for c in cases),
            'errors':sum(c.find('error')is not None for c in cases),
            'skipped':sum(c.find('skipped')is not None for c in cases)}

def nodes(path):
    return {s for s in path.read_text().splitlines()
            if s.startswith(('trading/tests/','backend/tests/','tests/rebuild/')) and '::' in s}

expected=nodes(Path('/workspace/van-native-cancel-final-collection-20261030.log'))
parent=nodes(Path('/workspace/van-native-order-final-collection-20261030.log'))
assert len(expected)==5556 and len(parent)==5497 and parent<=expected
checks={}
for folder,label,passed in ((full,'full',5556),(focused,'focused',200)):
    result=json.loads((folder/'receipt.json').read_text())
    assert result['completed'] and result['exit']==0 and result['cleaned']
    assert result['owned_fixture_independently_absent'] and result['base_head']==base
    assert counts(folder/'full-trading.xml')=={'passed':passed,'failed':0,'errors':0,'skipped':0}
    assert not json.loads((folder/'storage-audit.json').read_text())['forbidden_events']
    pins=result['source_sha256']|result['reference_fixtures_sha256']
    for p,h in pins.items():assert hashlib.sha256((root/p).read_bytes()).hexdigest()==h,p
    events=[json.loads(s) for s in (folder/'test-events.jsonl').read_text().splitlines()]
    assert all(e['outcome']=='passed' for e in events)
    calls=[e['nodeid'] for e in events if e['phase']=='call']
    assert len(calls)==len(set(calls))==passed
    if label=='full':assert set(calls)==expected=={e['nodeid'] for e in events}
    checks[label]={'junit':counts(folder/'full-trading.xml'),'call_identities_unique':True,
        'storage_violations':0,'owned_postgres_independently_absent':True,
        'source_input_sha256':pins,'source_pins':len(pins)}
preserved=json.loads(Path('/workspace/van-native-cancel-all-original-tests-preserved-20261030.json').read_text())
assert preserved['base']==base and preserved['inherited_test_files']==preserved['byte_identical']==653
assert preserved['all_original_test_signatures_preserved'] and preserved['all_original_assertions_preserved']
assert preserved['original_test_functions']==6739 and preserved['original_assertions']==17926
lite=counts(Path('/workspace/van-native-cancel-backend-only-20261030.xml'))
assert lite=={'passed':53,'failed':0,'errors':0,'skipped':6}
environment=json.loads(Path('/workspace/van-native-cancel-backend-only-environment-20261030.json').read_text())
assert not environment['psycopg_present']
assert environment['lock_sha256']==hashlib.sha256((root/'backend/requirements.lock').read_bytes()).hexdigest()
guards={}
for name in ('collection','workmap','owner','frontend','mutations','consolidation'):
    d=json.loads(Path('/workspace/van-native-cancel-final-'+name+'-20261030.json').read_text())
    assert d['state']=='COMPLETED' and d['exit']==0
    guards[name]={'state':d['state'],'exit':d['exit']}
protocol={}
for name in ('OpenApiCommonMessages.proto','OpenApiCommonModelMessages.proto','OpenApiMessages.proto',
             'OpenApiModelMessages.proto','PROVENANCE.json'):
    p='trading/vati/execution/ctrader/proto/'+name;b=(root/p).read_bytes()
    assert b==subprocess.check_output(['git','show',base+':'+p],cwd=root)
    protocol[p]=hashlib.sha256(b).hexdigest()
hosted=json.loads(Path('/workspace/van-02e8e712-cognitive-python-original-readback-20261030.json').read_text())
assert hosted['source_head']==base and hosted['artifact_id']==12971225934
assert hosted['members']['cognitive-broad.xml']['junit']=={'passed':5176,'failed':0,'errors':0,'skipped':316}
raw=root/'docs/rebuild/rev118/ci/native_cancel_20261030';raw.mkdir(parents=True,exist_ok=False)

def copy(source,destination):
    source=Path(source);destination=raw/destination;destination.parent.mkdir(parents=True,exist_ok=True)
    b=source.read_bytes()
    if destination.suffix=='.gz':
        destination.write_bytes(gzip.compress(b,mtime=0));assert gzip.decompress(destination.read_bytes())==b
    else:destination.write_bytes(b);assert destination.read_bytes()==b

for folder,label in ((full,'full'),(focused,'focused-final'),(Path('/workspace/van-native-cancel-focused-r1-20261030'),'focused-intermediate')):
    d=json.loads((folder/'receipt.json').read_text());assert d['completed'] and d['exit']==0 and d['cleaned']
    for name in ('receipt.json','storage-audit.json','full-trading.log','full-trading.xml','test-events.jsonl','targets.txt'):
        copy(folder/name,label+'/'+name+('.gz' if name.endswith('.jsonl') else ''))
    copy(str(folder)+'.py',label+'/controller.py')
prefixes=('van-native-cancel-transport-before-20261030','van-native-cancel-transport-before-r2-20261030',
          'van-native-cancel-transport-after-r1-20261030','van-native-cancel-adapter-r1-20261030',
          'van-native-cancel-owner-r1-20261030','van-native-cancel-recovery-before-20261030',
          'van-native-cancel-recovery-after-r1-20261030','van-native-cancel-capacity-before-20261030',
          'van-native-cancel-owner-expanded-r1-20261030','van-native-cancel-owner-expanded-r2-20261030',
          'van-native-cancel-backend-only-20261030',
          *('van-native-cancel-final-'+name+'-20261030' for name in guards))
for prefix in prefixes:
    for suffix in ('.json','.log','.xml'):
        p=Path('/workspace')/(prefix+suffix)
        if p.exists():copy(p,p.name)
for name in ('van-native-cancel-all-original-tests-preserved-20261030.json',
             'van-native-cancel-backend-only-environment-20261030.json',
             'van-native-cancel-transport-wip1-20261030.json','van-native-cancel-adapter-wip2-20261030.json',
             'van-native-cancel-owner-wip3-20261030.json','van-native-cancel-final-wip4-20261030.json',
             'van-02e8e712-cognitive-python-original-readback-20261030.json',
             'van-02e8e712-main-terminal-jobs-20261030.json','van-02e8e712-backend-public-original-20261030.log',
             'van-02e8e712-backend-failed-original-20261030.log','van-02e8e712-ledger-failed-original-20261030.log'):
    copy('/workspace/'+name,name)
copy(__file__,'evidence-builder.py')
now=datetime.datetime.now(datetime.UTC).isoformat()
summary=('Signed cancellation of an original CTrader pending entry now has a positive source path through the '
    'actual execution router, original command/receipt-bound query owner, registered-owner verifier, shared SQL '
    'journal, adapter and bounded framed transport. Exact target/deadline and original/current lease epochs are '
    'bound to the signed intent. Durable nonce/request admission precedes the native write; expiry, current key, '
    'lease and source checks repeat after writer acquisition/readback and at send. Storage admission reserves a '
    'result slot. Original requests never resend after restart, timeout or lost commit/reply; recovery reads '
    'the same native order. Pre-cancel snapshots cannot become post-cancel evidence, and replayed queries do '
    'not republish or roll back later knowledge. A newly signed attempt after explicit scoped cancellation '
    'rejection requires later native reconciliation; a still-working snapshot alone cannot clear an unknown '
    'attempt. Historical attempt disposition remains separate from current native observations. Closing and '
    'unowned orders refuse; new-entry halt does not disable the scoped reduction. Partial fills/raw responses '
    'and unavailable receipt time survive, without zero-fill cancellation receipts or financial release. '
    'Working zero-fill native orders now contradict an earlier no-effect receipt in the actual pending-risk owner. '
    'Affected source suite:5,556 passed, zero failures/errors/skips/storage violations; all5,497 parent cases '
    'retained and59 cases added. Focused real PostgreSQL selection:200 passed, zero failures/errors/skips/storage '
    'violations. Backend-lock-only new cases:53 passed and6 declared PostgreSQL skips; those same6 cases executed '
    'in real PostgreSQL. These suites overlap and are not additive. Owned PostgreSQL is independently absent. '
    'All653 inherited Python test files are byte-identical, preserving6,739 functions and17,926 assertions. '
    'This partial BE-003/009/010 source packet does not complete financial reservations/release, automatic '
    'qualified parent/child control, amendment/replacement, gateway/client controls, the provider matrix or native acceptance.')
next_action=('Publish through genuine hooks, wait for terminal required-baseline committed verification before '
    'normal push, independently read exact remote and hosted CI. Continue atomic amend versus cancel-replace, '
    'complete late/cross-child identity and protection recovery, governed automatic parent/child lifetime budgets, '
    'complete fees/fill/price/FX/principal/finality and all-origin shared reservations/outbox/consumers. Preserve '
    'current policy/runtime-cohort admission and immutable V1 missing-obligation receipts. Complete manual, '
    'payment/transfer/handover and provider reconciliation, all market/feed/chart/voice, assistant, learning/all38 '
    'forecast-research, crypto/CEX and operations obligations across all82backend units and12 verification packets. '
    'Android follows actual BG-001 and uses its provisioned production profile on Van trading core, genuine '
    'signing and Artemis/S24 acceptance. Profitability remains an evidence-based objective, never guaranteed.')
receipt={'schema':'van.rev118.native-cancel-source/1','observed_at_utc':now,'source_parent':base,
    'state':'PARTIAL_CANDIDATE_SOURCE_TESTED_CTRADER_SIGNED_CONTROL_NOT_FINANCIAL_RELEASE_OR_NATIVE_ACCEPTANCE',
    'implementation':summary,'checks':checks,'guards':guards,'preservation':preserved,
    'backend_only_new_cases':{'junit':lite,'environment':environment,'same6PGcasesExecuted':True},
    'all5497parent_cases_retained':True,'new_cases':59,'overlapping_suites_not_additive':True,
    'original_protocol_reference_sha256':protocol,'raw':'ci/native_cancel_20261030',
    'authority':['auth-20261022-owner-autonomous-candidate-build'],'formal_acceptance':'NOT_ISSUED',
    'execution_authority':False,'reservation_qualified':False,'native_qualified':False,
    'fixture_signatures_and_socket_peers':'Source logic only; no actual owner/device, broker account, financial effect or native certificate is claimed.',
    'retained_findings':['Transport first probe:13 missing-method failures plus1 new-fixture constructor-parameter failure. '
       'The parameter was corrected without changing assertions. Second probe:14 observed missing-method failures; '
       'source editing began before terminal driver readback, so it is retained without strict frozen-before qualification.',
       'Recovery expansion:4 failures/13 passes for duplicate reconciliation publication, stale preflight reuse, '
       'rejection recovery and an unfilled working order contradicting no-effect. Assertions were preserved.',
       'Capacity counterexample:1 failure; native cancellation could happen with no journal result slot. '
       'Admission now reserves pending results before dispatch.'],
    'parent_hosted_evidence':{'commit':base,'cognitive_run':41041627661,'python_job':124015578088,
       'android_job':124015578267,'both_jobs':'SUCCESS','verified_python_artifact':hosted,
       'main_run':41041627938,'actual_failed_jobs':[124015580535,124015580687],
       'main_terminal_successful_jobs':17,'main_terminal_failed_jobs':2,
       'public_backend_media_original_log':{'passed':6070,'declared_skips':7},
       'actual_reasons':['private DDS deploykey unprovisioned','trusted main lacks its ledger checker'],
       'gates_preserved':True,'not_current_candidate_validation':True},
    'remaining':['No live broker, signed production owner command, independent native/provider/device or full-unit acceptance executed.',
       'Finite source capacities and local clocks do not qualify storage availability, provider clocks, matching, latency or production policy.',
       'This is explicit one-shot owner control of original CTrader engine pending entries. Governed automatic parent controls, manual/handover obligations, full MT5/current-market and eligible CEX scope remain required.',
       'Atomic amend/cancel-replace, all-origin reservations, full cross-child corrections/bust/finality, confirmed protection and nonduplicated economic release remain open.',
       'All original82backend/12verification/38forecast-research and gated Android contracts retain their full requirements.'],
    'next':next_action}
(root/'docs/rebuild/rev118'/rel).write_text(json.dumps(receipt,indent=2)+'\n')
for name in ('EXECUTION_LEDGER.json','CANDIDATE_SOURCE_PROGRESS.json'):
    p=root/'docs/rebuild/rev118'/name;d=json.loads(p.read_text());d['updated_at_utc']=now
    if name=='EXECUTION_LEDGER.json':
        d['observations'].append(summary);d['current_action']=next_action
        for uid in ('BE-003','BE-009','BE-010'):
            if rel not in d['units'][uid]['evidence']:d['units'][uid]['evidence'].append(rel)
    else:
        for uid in ('BE-003','BE-009','BE-010'):d['units'][uid]['milestones'].append({'description':summary,'evidence':rel})
    p.write_text(json.dumps(d,indent=2)+'\n')
p=root/'docs/rebuild/rev118/CONTINUATION_20261022.md'
p.write_text(p.read_text()+'\n\n## Signed original pending-order cancellation —30October\n\n'+summary+
             '\n\n[Source receipt]('+rel+'). '+next_action+'\n')
p=root/'docs/rebuild/rev118/BUILD_EXECUTION_PLAN.md';s=p.read_text()
a=s.index('## Current concrete gap and next result');b=s.index('## Commands and evidence economy',a)
p.write_text(s[:a]+'## Current concrete gap and next result\n\n'+summary+'\n\n[Current source receipt]('+rel+'). '+
    next_action+'\n\nAll original work fronts above retain their full scope. Source-tested subpaths issue no formal '
    'unit acceptance. Reuse the reported completed browser Harness repair during the actual Van-consumer '
    'integration, preserving native admission and interactive binding.\n\n'+s[b:])
doc='# Signed original pending-order cancellation\n\n'+summary+(
    '\n\n`ExecutionRouter.prepare_native_cancel`, `cancel_native_order` and `reconcile_native_cancel` use '
    '`NativeCancelOwner`. Current registered-owner signature validation remains mandatory for a new action. '
    'The SQL writer owns one-shot nonce consumption; historical signature archives cannot redeem a new action. '
    'Original and current runtime lease epochs remain separate so a genuine new lease can recover an older '
    'order without rewriting origin identity. No epoch or owner authority is self-issued.\n\n'
    'Only exact receipt-owned original order IDs are considered. Native adapter checks require the same '
    'account/monetary scope/connection and an explicit nonclosing working pending order. Market-only native '
    'transport cannot inherit cancellation. The bounded financial transport accepts only CancelOrderReq and '
    'checks expiry/current authority and fence after its send lock. No new order, amendment, close or stop '
    'removal is sent. The pinned protocol is unchanged.\n\n'
    'A committed request is never automatically sent again. Lost commit acknowledgement, failed independent '
    'readback, dropped reply and restart retain the original request identity. Native order queries retain '
    'their first publication, reject pre-attempt snapshots as postconditions and preserve historical attempt '
    'disposition separately from the latest observed lifecycle. Explicit rejection recovery needs a fresh '
    'original-order query and a newly signed request; a still-working order cannot resolve an unknown cancel.\n\n'
    'Result slots remain reserved for outstanding attempts. Known partial/raw responses survive an unavailable '
    'arrival clock with an explicit missing timestamp. Neither cancel ACK, timeout, empty positions nor '
    'zero currently observed fills release a financial reservation or establish flatness. The current pending '
    'risk owner also holds when a working native order contradicts an old no-effect receipt.\n\n'
    'Framed peers and P256 fixture owner keys test source logic. Real SQLite and disposable PostgreSQL test '
    'durability, scope, contention and lost acknowledgements; no live broker, native owner/device, production '
    'financial effect or provider qualification is claimed. Original failures and all unchanged inherited '
    'assertions remain in the [source evidence](../'+rel+').\n\n'
    'Full amendment/replacement, governed automatic parent/child control, all providers and gateway/client '
    'controls remain required. Full fees/fill/price/FX/principal and late correction/bust/finality, independent '
    'protection and nonduplicated financial release need their complete owners. Existing provisional V1 '
    'missing requirements remain immutable.\n\n')+next_action+'\n'
(root/'docs/rebuild/rev118/backend/BE-003_009_010_NATIVE_CANCEL.md').write_text(doc)
print(json.dumps({'full_passed':5556,'focused_passed':200,'backend_only':lite,'source_pins':checks['full']['source_pins'],
    'preserved_files':653,'raw_files':sum(p.is_file() for p in raw.rglob('*')),'receipt':rel}))
