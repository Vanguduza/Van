"""Execute once after frozen source qualification; no acceptance is issued."""
from pathlib import Path
import datetime,gzip,hashlib,json,subprocess
import xml.etree.ElementTree as ET

root=Path('/workspace/van-review-2026-10-18/publish')
base='0aa3bfc19cd7d0aa285d8b897ec1aa61ef157fd7'
rel='receipts/NATIVE_CLOSE_COST_SOURCE_20261030.json'
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()==base
assert not (root/'docs/rebuild/rev118'/rel).exists(),'Do not duplicate milestones'

def counts(path):
    cases=ET.parse(path).findall('.//testcase')
    return {'passed':sum(not any(c.find(k)is not None for k in ('failure','error','skipped')) for c in cases),
        'failed':sum(c.find('failure')is not None for c in cases),
        'errors':sum(c.find('error')is not None for c in cases),
        'skipped':sum(c.find('skipped')is not None for c in cases)}

def nodes(path):
    return {s for s in path.read_text().splitlines()
        if s.startswith(('trading/tests/','backend/tests/','tests/rebuild/')) and '::' in s}

expected=nodes(Path('/workspace/van-ctrader-close-cost-final-r2-collection-20261030.log'))
parent=nodes(Path('/workspace/van-native-cancel-final-collection-20261030.log'))
assert len(expected)==5604 and len(parent)==5556 and parent<=expected
checks={}
for label,passed in [('full',5604),('focused',138)]:
    folder=Path('/workspace/van-ctrader-close-cost-'+label+'-r2-20261030')
    result=json.loads((folder/'receipt.json').read_text())
    assert result['completed'] and result['exit']==0 and result['cleaned']
    assert result['owned_fixture_independently_absent'] and result['base_head']==base
    assert counts(folder/'full-trading.xml')==dict(passed=passed,failed=0,errors=0,skipped=0)
    assert not json.loads((folder/'storage-audit.json').read_text())['forbidden_events']
    pins=result['source_sha256']|result['reference_fixtures_sha256']
    for p,h in pins.items():assert hashlib.sha256((root/p).read_bytes()).hexdigest()==h,p
    events=[json.loads(s) for s in (folder/'test-events.jsonl').read_text().splitlines()]
    assert all(e['outcome']=='passed' for e in events)
    calls=[e['nodeid'] for e in events if e['phase']=='call']
    assert len(calls)==len(set(calls))==passed
    if label=='full':assert set(calls)==expected=={e['nodeid'] for e in events}
    checks[label]={'junit':counts(folder/'full-trading.xml'),'unique_call_identities':True,
        'storage_violations':0,'owned_postgres_independently_absent':True,'source_input_sha256':pins}
preserved=json.loads(Path('/workspace/van-ctrader-close-cost-all-original-tests-preserved-20261030.json').read_text())
assert preserved['base']==base and preserved['inherited_test_files']==preserved['byte_identical']==659
assert preserved['all_original_test_signatures_preserved'] and preserved['all_original_assertions_preserved']
assert preserved['original_test_functions']==6770 and preserved['original_assertions']==18026
lite=counts(Path('/workspace/van-ctrader-close-cost-backend-only-r2-20261030.xml'))
assert lite==dict(passed=45,failed=0,errors=0,skipped=3)
environment=json.loads(Path('/workspace/van-ctrader-close-cost-backend-only-environment-20261030.json').read_text())
assert not environment['psycopg_present']
assert environment['lock_sha256']==hashlib.sha256((root/'backend/requirements.lock').read_bytes()).hexdigest()
guards={}
for name in ('collection','workmap','owner','frontend','mutations','consolidation'):
    d=json.loads(Path('/workspace/van-ctrader-close-cost-final-'+name+'-20261030.json').read_text())
    assert d['state']=='COMPLETED' and d['exit']==0
    guards[name]={'state':d['state'],'exit':d['exit']}
protocol={}
for name in ('OpenApiCommonMessages.proto','OpenApiCommonModelMessages.proto','OpenApiMessages.proto',
             'OpenApiModelMessages.proto','PROVENANCE.json'):
    p='trading/vati/execution/ctrader/proto/'+name;b=(root/p).read_bytes()
    assert b==subprocess.check_output(['git','show',base+':'+p],cwd=root)
    protocol[p]=hashlib.sha256(b).hexdigest()
raw=root/'docs/rebuild/rev118/ci/native_close_cost_20261030';raw.mkdir(parents=True,exist_ok=False)

def copy(source,destination):
    source=Path(source);destination=raw/destination;destination.parent.mkdir(parents=True,exist_ok=True)
    b=source.read_bytes()
    if destination.suffix=='.gz':
        destination.write_bytes(gzip.compress(b,mtime=0));assert gzip.decompress(destination.read_bytes())==b
    else:destination.write_bytes(b);assert destination.read_bytes()==b

for label in ('full','focused'):
    folder=Path('/workspace/van-ctrader-close-cost-'+label+'-r2-20261030')
    for name in ('receipt.json','storage-audit.json','full-trading.log','full-trading.xml','test-events.jsonl','targets.txt'):
        copy(folder/name,label+'/'+name+('.gz' if name.endswith('.jsonl') else ''))
    copy(str(folder)+'.py',label+'/controller.py')
for label in ('full','focused'):
    folder=Path('/workspace/van-ctrader-close-cost-'+label+'-r1-20261030')
    for name in ('receipt.json','storage-audit.json','full-trading.log','full-trading.xml','test-events.jsonl','targets.txt'):
        p=folder/name
        if p.exists():copy(p,label+'-intermediate/'+name+('.gz' if name.endswith('.jsonl') else ''))
    copy(str(folder)+'.py',label+'-intermediate/controller.py')
prefixes=('van-ctrader-close-fee-before-20261030','van-ctrader-close-fee-after-r1-20261030',
    'van-ctrader-close-cost-review-before-20261030','van-ctrader-close-cost-review-after-r1-20261030',
    'van-ctrader-close-cost-review-after-r2-20261030','van-ctrader-close-cost-expanded-r1-20261030',
    'van-ctrader-close-cost-expanded-r2-20261030','van-ctrader-close-cost-expanded-r3-20261030',
    'van-ctrader-close-cost-backend-only-20261030','van-ctrader-close-cost-backend-only-r2-20261030',
    'van-native-fee-provenance-before-20261030','van-native-fee-provenance-after-r1-20261030',
    'van-native-fee-provenance-after-r2-20261030','van-native-fee-provenance-expanded-r1-20261030',
    'van-native-fee-provenance-expanded-r2-20261030',
    *('van-ctrader-close-cost-final-r2-'+name+'-20261030' for name in guards))
for prefix in prefixes:
    for suffix in ('.json','.log','.xml'):
        p=Path('/workspace')/(prefix+suffix)
        if p.exists():copy(p,p.name)
for name in ('van-ctrader-close-cost-all-original-tests-preserved-20261030.json',
    'van-ctrader-close-cost-backend-only-environment-20261030.json','van-ctrader-close-cost-wip5-20261030.json',
    'van-0aa3bfc1-terminal-ci-20261030.json','van-0aa3bfc1-ledger-failed-original-20261030.log',
    'van-0aa3bfc1-backend-failed-original-20261030.log','van-0aa3bfc1-android-instrumentation-failed-original-20261030.log',
    'van-0aa3bfc1-android-original-rerun-request-20261030.json',
    'van-0aa3bfc1-android-original-report-readback-20261030.json',
    'van-0aa3bfc1-instrumentation-original-20261030.zip',
    'van-0aa3bfc1-android-retry-original-20261030.zip',
    'van-0aa3bfc1-android-retry-original-readback-20261030.json',
    'van-ctrader-close-cost-full-r1-stop-reason-20261030.json',
    'van-family-after-partial-before-20261030.json'):
    copy('/workspace/'+name,name)
copy(__file__,'evidence-builder.py')
now=datetime.datetime.now(datetime.UTC).isoformat()
summary=('CTrader closing execution receipts now retain their own recorded commission and money precision. '
    'An absent/invalid optional charge remains unknown without erasing the actual fill, original order/position '
    'identity or protection. Separate immutable native commission provenance distinguishes actual measured '
    'zero from historical default zero without changing legacy receipt seal bodies. Missing original '
    'charge evidence remains unknown; a native deal cannot count under a second close request. '
    'Both actual trade-review consumers independently read committed original command, '
    'entry receipt, close receipts and ExitJournal requests/dispositions. They include each recorded exit '
    'charge once; replay does not charge twice. Partial-then-full closes use every recorded exit price/quantity '
    'and original entry quantity instead of the last price times the residual position. Exact rational '
    'arithmetic preserves the recorded aggregate. Original entry fees/TCA and receipt hashes remain immutable. '
    'Foreign, future, corrupted, conflicting, ambiguous or incomplete source holds an explicit unknown charge; '
    'independently reported net cash retains its existing precedence. Framed source peers, real SQLite and '
    'PostgreSQL cover both review consumers, restart/readback, replay and negative scope. Full affected suite: '
    '5,604 passed with zero failures/errors/skips/storage violations, retaining all5,556 parent cases and48 '
    'new cases. Focused real PostgreSQL:138 passed with zero failures/errors/skips/storage violations. '
    'Backend-lock-only new cases:45 passed with3 declared PostgreSQL skips; those3 execute against real '
    'PostgreSQL. Suites overlap. All659 inherited Python test files are byte-identical, preserving6,770 '
    'test functions and18,026 assertions. Owned PostgreSQL fixtures are independently absent. '
    'This source packet retains the existing commission-magnitude convention and does not qualify signed '
    'rebates, all fees, multi-entry/deal economics, FX, cash reconciliation or settlement/finality. '
    'CTrader economic finality and all financial release/production/native acceptance remain unissued.')
next_action=('Publish using genuine hooks, terminal required-baseline committed verification before normal '
    'push, independent exact remote readback and exact-head CI. Repair the confirmed family remaining '
    'cost-basis error after partial exits and later additions, and verify original lifetime history recovery '
    'and actual risk/expansion consumers. Complete the original native economic '
    'owner for per-deal/correction/bust/late charge identity, signed fees/rebates, carry/FX/principal and '
    'cash/finality; retain scalar ambiguity as unknown until that owner supplies evidence. Continue atomic '
    'amend versus cancel-replace, governed parent/child lifetime budgets, all-origin shared financial '
    'reservations/outbox/effect consumers, manual/payment/transfer/handover/provider reconciliation and '
    'nonduplicated release. Preserve immutable V1 missing-obligation receipts and native policy/runtime '
    'admission. Retain the intermittent Android deep-link instrumentation failure and inspect exact-head '
    'CI; unchanged parent replay passed18 cases with4 declared skips, without S24 acceptance. '
    'All82backend units,12 verification packets,38forecast/research '
    'backend units and every market/chart/voice/assistant/crypto/operations contract retain full scope. '
    'Android follows the actual BG-001 gate and uses the provisioned production profile on Van trading core; '
    'genuine signing and actual Artemis/S24 acceptance remain required. Profitability is evaluated with '
    'evidence, never guaranteed.')
receipt={'schema':'van.rev118.native-close-cost-source/1','observed_at_utc':now,'source_parent':base,
    'state':'PARTIAL_CANDIDATE_SOURCE_TESTED_RECORDED_NATIVE_CHARGES_NOT_FULL_ECONOMIC_QUALIFICATION',
    'implementation':summary,'checks':checks,'guards':guards,'preservation':preserved,
    'backend_only_new_cases':{'junit':lite,'environment':environment,'same3_pg_cases_executed':True},
    'all5556_parent_cases_retained':True,'new_cases':48,'overlapping_suites_not_additive':True,
    'original_protocol_reference_sha256':protocol,'raw':'ci/native_close_cost_20261030',
    'authority':['auth-20261022-owner-autonomous-candidate-build'],'formal_acceptance':'NOT_ISSUED',
    'execution_authority':False,'reservation_qualified':False,'native_qualified':False,
    'retained_failures':['Native close before:6failed/1passed; only explicit zero was correct.',
        'Actual review before:2failed/7passed; missing charge falsely known and net48.20 instead of44.95.',
        'Review after first:65passed/4failed; original process-death assertions unexecuted because direct runner omitted inherited child PYTHONPATH. Declared-path rerun69passed; no inherited assertions changed.',
        'Expanded-r2:81passed/2failed; new partial fixture hardcoded foreign symbol7 instead of actual native symbol1. Corrected fixture to original position symbol; expanded-r3:83passed.',
        'Historical default-zero provenance counterexample:1failed; a scalar default masqueraded as measured cost. Native observations now bind entry/exit components and precision.',
        'Initial provenance implementation:78passed/6failed because durable Decimal strings were omitted from the bounded parser. Corrected without weakening assertions;84passed then105passed after expanded identity controls.',
        'Full-r1 deliberately interrupted exit2 before provenance edits. Owned PostgreSQL cleanup and absence verified; partial calls are not a completed full qualification.'],
    'parent_ci':{'source_head':base,'original_terminal':'16SUCCESS/3FAIL',
        'original_failed_jobs':[124039398057,124039398498,124039398463],
        'reasons':['Trusted main8eb188 lacks its ledger checker','Private DDS deploy key not provisioned',
                   'Android Compose test-clock recomposition on a worker without looper'],
        'unchanged_android_replay':json.loads(Path('/workspace/van-0aa3bfc1-android-retry-original-readback-20261030.json').read_text()),
        'supporting_workflows':'4SUCCESS','gates_preserved':True,'not_current_candidate_validation':True},
    'next_confirmed_family_gap':json.loads(Path('/workspace/van-family-after-partial-before-20261030.json').read_text()),
    'remaining':['Single unambiguous original scalar entry plus complete recorded exit volume required; native multi-fill/deal reconciliation remains required.',
        'Provider commission sign/rebates, funding/financing/late costs, FX and cash/settlement/correction/bust finality remain unqualified.',
        'Full automatic parent control, atomic amend/replace, all-origin reservations and native protection/release remain open.',
        'No live broker, production owner/device command, independent unit/provider/native/deployment/S24 acceptance executed.',
        'All original backend, forecast/research, assistant, market, crypto, operations and gated Android obligations retain full scope.'],
    'next':next_action}
(root/'docs/rebuild/rev118'/rel).write_text(json.dumps(receipt,indent=2)+'\n')
for name in ('EXECUTION_LEDGER.json','CANDIDATE_SOURCE_PROGRESS.json'):
    p=root/'docs/rebuild/rev118'/name;d=json.loads(p.read_text());d['updated_at_utc']=now
    if name=='EXECUTION_LEDGER.json':
        d['observations'].append(summary);d['current_action']=next_action
        for uid in ('BE-003','BE-009','BE-010'):
            if rel not in d['units'][uid]['evidence']:d['units'][uid]['evidence'].append(rel)
    else:
        for uid in ('BE-003','BE-009','BE-010','BE-013'):
            d['units'][uid]['milestones'].append({'description':summary,'evidence':rel})
    p.write_text(json.dumps(d,indent=2)+'\n')
p=root/'docs/rebuild/rev118/CONTINUATION_20261022.md'
p.write_text(p.read_text()+'\n\n## Recorded native close costs —30October\n\n'+summary+'\n\n[Source receipt]('+rel+'). '+next_action+'\n')
p=root/'docs/rebuild/rev118/BUILD_EXECUTION_PLAN.md';s=p.read_text()
a=s.index('## Current concrete gap and next result');b=s.index('## Commands and evidence economy',a)
p.write_text(s[:a]+'## Current concrete gap and next result\n\n'+summary+'\n\n[Source receipt]('+rel+'). '+next_action+
    '\n\nAll original work fronts above retain their full scope. Source-tested subpaths issue no formal unit acceptance.\n\n'+s[b:])
(root/'docs/rebuild/rev118/backend/BE-003_009_010_013_NATIVE_CLOSE_COSTS.md').write_text(
    '# Recorded native closing costs\n\n'+summary+'\n\nThe actual CTrader close adapter reads only the '
    'closing deal row commission with that same row moneyDigits. Nested closePositionDetail is not a '
    'substitute; it can describe different economic scope. An unavailable charge never invalidates a real '
    'fill. Both AccountTradeLifecycle and DecisionCycle read original durable records before price-derived '
    'review. Their projection is bounded and scoped by original account alias, venue, symbol, position and '
    'trade intent. It checks command/receipt seals, producers, source availability, original close request '
    'and disposition, exact quantities, conflicting vintages and replay. It changes only copied review '
    'inputs, preserving entry TCA and original receipts. Missing full volume or ambiguous entry vintages '
    'remain unavailable. Recorded per-leg price arithmetic handles a partial close followed by the remaining '
    'full close. A durable native deal/economic owner must still resolve multi-entry/multi-fill, sign, '
    'late charges, correction/bust and finality.\n\nProvider finality remains unavailable; recorded fees '
    'are not all fees or reconciled cash. No reservation is released by this change. Original inherited '
    'tests and frozen protocol/package remain unchanged. Source fixture keys/peers and disposable PostgreSQL '
    'are not live native/provider/device evidence.\n\n[Executed source receipt](../'+rel+'). '+next_action+'\n')
print(json.dumps({'full':5604,'focused':138,'backend_only':lite,'preserved_files':659,
    'source_pins':len(checks['full']['source_input_sha256']),'protocol_pins':len(protocol),
    'raw_files':sum(p.is_file() for p in raw.rglob('*')),'receipt':rel}))
