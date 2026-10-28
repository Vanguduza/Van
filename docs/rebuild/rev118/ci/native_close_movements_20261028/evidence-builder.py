from pathlib import Path
import ast,hashlib,io,json,shutil,subprocess,tarfile,datetime,xml.etree.ElementTree as ET

root=Path('/workspace/van-review-2026-10-18/publish');base='8ff365d42bb118620d3b53a0d932edeb085b1350'
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()==base
run=Path('/workspace/van-native-close-movement-consumers-sql-r1-20261028')
receipt=json.loads((run/'receipt.json').read_text());outer=json.loads(Path('/workspace/van-native-close-movement-consumers-sql-r1-process-20261028.json').read_text())
assert receipt['exit']==outer['exit']==0 and receipt['completed'] and receipt['cleaned'] and receipt['owned_fixture_independently_absent']
pins=receipt['source_sha256']|receipt['reference_fixtures_sha256']
assert all(hashlib.sha256((root/f).read_bytes()).hexdigest()==h for f,h in pins.items())
assert not json.loads((run/'storage-audit.json').read_text())['forbidden_events']
cases=ET.parse(run/'full-trading.xml').findall('.//testcase')
assert len(cases)==449 and all(all(c.find(k)is None for k in ['failure','error','skipped']) for c in cases)
calls=[json.loads(x) for x in (run/'test-events.jsonl').read_text().splitlines() if json.loads(x)['phase']=='call']
assert len(calls)==len({x['nodeid'] for x in calls})==449 and all(x['outcome']=='passed' for x in calls)
collection=Path('/workspace/van-native-close-collection-20261028');assert json.loads(collection.with_suffix('.json').read_text())['exit']==0
nodes=[x for x in collection.with_suffix('.log').read_text().splitlines() if x.startswith(('trading/tests/','backend/tests/')) and '::' in x]
assert len(nodes)==len(set(nodes))==449 and set(nodes)=={x['nodeid'] for x in calls}
files=functions=0
with tarfile.open(fileobj=io.BytesIO(subprocess.check_output(['git','archive',base,'trading/tests','tests/rebuild'],cwd=root))) as tar:
    for m in tar:
        if not m.isfile() or not m.name.endswith('.py') or not Path(m.name).name.startswith('test_'):continue
        old=tar.extractfile(m).read();assert old==(root/m.name).read_bytes(),m.name;files+=1
        functions+=sum(isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name.startswith('test_') for n in ast.walk(ast.parse(old)))
raw=root/'docs/rebuild/rev118/ci/native_close_movements_20261028';assert not raw.exists();raw.mkdir(parents=True)
def copy(src,dest):
    src=Path(src);dest=raw/dest;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest);assert src.read_bytes()==dest.read_bytes()
for p in Path('/workspace').iterdir():
    if not p.name.startswith('van-native-close-') or 'wip' in p.name or p==Path(__file__):continue
    if p.is_dir():
        for c in p.iterdir():
            if c.is_file():copy(c,'runs/'+p.name+'/'+c.name)
    elif p.suffix in ['.json','.log','.xml','.py']:copy(p,'runs/'+p.name)
for ext in ['.json','.zip']:copy('/workspace/van-native-close-movement-wip3-20261028'+ext,'recovery/wip3'+ext)
for name in ['scope','owner','frontend','mutations','consolidation']:
    assert json.loads(Path('/workspace/van-native-close-'+name+'-20261028.json').read_text())['exit']==0
for name in ['van-8ff365d4-terminal-artifacts-20261028.json','van-8ff365d4-terminal-workflows-20261028.json',
    'van-8ff365d4-ci-guard-observation-20261028.json','van-8ff365d4-mandatory-job-123054076877-20261028.log',
    'van-8ff365d4-mandatory-job-123054077554-20261028.log','van-8ff365d4-postgres-hosted-original-20261028.log',
    'van-8ff365d4-postgres-original-20261028.zip','van-8ff365d4-postgres-archive-readback-20261028.json',
    'van-8ff365d4-backend-public-original-20261028.zip','van-8ff365d4-backend-public-archive-readback-20261028.json']:
    copy('/workspace/'+name,'published-parent/'+name)
proof={'source_parent':base,'passed':449,'skipped':0,'failures':0,'errors':0,'audit_violations':0,
    'inner_exit':0,'outer_exit':0,'every_current_discovered_case_executed_once':True,
    'source_and_fixture_pins':pins,'owned_postgres_independently_absent':True,
    'original_test_files_byte_identical':files,'original_test_functions_AST_preserved':functions,
    'native_or_production_acceptance':False}
(raw/'source-preservation-and-discovery.json').write_text(json.dumps(proof,indent=2)+'\n')
summary=('Original native closing-balance observations now flow through the existing financial movement owner and existing ledger, not a second journal. An adjacent original native balance version supplies the exact scoped delta; original account marks, cash rows or prior closes can anchor it. Raw commission/conversion fields remain signed/unknown as observed; no component sign, zero fee, settled profit, spendable capital or parent release is inferred. The owner preserves original durable requests and readback, actual SQL serialization, unknown commit ACK, clock after queued writer-lock acquisition, namespaces and late source conflicts. Cash/deal IDs have separate identities and ambiguous shared native versions refuse double posting. Bounded catch-up and read-only projections retain pending/missing-anchor versus conflicting-version states. The actual funding capture now collects deals before materializing, so a new close appears in the same sweep. Final449source/SQLite/PostgreSQL/HTTP/consumer cases pass with0fail/error/skip/audit;449independently collected calls each execute once, all1277source/fixture pins match, and ownedPostgreSQL is independently absent. All inherited test files remain byte-identical. No whole-unit/native/provider/production/S24 acceptance is issued.')
rel='receipts/NATIVE_CLOSE_OBSERVATIONS_SOURCE_20261028.json';now=datetime.datetime.now(datetime.UTC).isoformat()
result={'schema':'van.rev118.native-close-observations-source/1','source_parent':base,'observed_at_utc':now,
    'state':'PARTIAL_CANDIDATE_SOURCE_TESTED_NOT_SETTLEMENT_OR_RISK_ADMISSION','implementation':summary,
    'checks':proof,'source_authorizations':['auth-20261022-owner-autonomous-candidate-build'],
    'retained_failures':['Initial4missing-module failures and missing publish_close owner method are retained.',
        'First owner run:52passed/1failed/23declaredPGskips; an existing independent-writer test exposed the changed private-history call signature. Original cash invocation preserved; no test/assertion weakened.',
        'Three actual version-collision counterexamples posted ambiguous observations before the new guard. A prototype used the wrong observation timestamp field; corrected to the actual received_at_ms contract.',
        'Two automatic-materialization counterexamples failed while closes were ignored. Native runtime first-sweep counterexample exposed deals captured after materialization; ordering corrected.',
        'Three conflicting-version read-model cases also incorrectly said the original anchor was missing. These states now remain distinct.',
        'Intermediate unconfigured SQL runs retain23declaredPostgreSQLskips. Actual freshPostgreSQL runs later execute those paths; final449has0skips. Earlier162/163focused SQL successes overlap final449 and are not added.'],
    'published_parent':{'head':base,'main_run':40755754628,'conclusion':'FAILURE','public_jobs_success':17,
        'mandatory_prerequisite_jobs_failure':2,'supporting_workflows_success':4,
        'independently_verified_original_archives':{'trading_passed':5162,'trading_declared_DDS_skip':1,'postgres_passed':26,
            'voice_passed':117,'gateway_passed':5872,'gateway_declared_skips':7,'media_passed':198},
        'compiler':'EA unchanged; reuse actual previously verified original MetaEditor source/binary proof; no native account qualification'},
    'remaining':['complete fee allocation and bounded future fee/fill/price/native-contract obligations, including MT5 and multi-asset cases',
        'qualified current shared policy and effect-capable runtime cohort','family/correlation and immutable parent lifetime budgets',
        'all-origin order/manual/payment/transfer/handover reservations/outbox and actual consumers',
        'native partial/working/cancel/bust/late-fee/economic finality and compensating facts; observation cannot release reservations',
        'every remaining canonical backend/forecast/learning/crypto/assistant/security/operations and gated Android obligation'],
    'raw':'ci/native_close_movements_20261028','formal_acceptance':'NOT_ISSUED','risk_capital_qualified':False,
    'execution_authority':False,'next':'Genuine hooks, required-baseline committed verification and normal push/readback/exactCI; continue complete economic obligation/policy/cohort/all-origin reservation and effectful reconciliation workflows. Preserve every original canonical dependency and acceptance identity.'}
(root/'docs/rebuild/rev118'/rel).write_text(json.dumps(result,indent=2)+'\n')
for name in ['EXECUTION_LEDGER.json','CANDIDATE_SOURCE_PROGRESS.json']:
    p=root/'docs/rebuild/rev118'/name;d=json.loads(p.read_text());d['updated_at_utc']=now
    if name=='EXECUTION_LEDGER.json':
        d['observations'].append(summary);d['current_action']=result['next']
        for uid in ['BE-006','BE-009','BE-010']:d['units'][uid]['evidence'].append(rel)
    else:
        for uid in ['BE-006','BE-009','BE-010']:d['units'][uid]['milestones'].append({'description':summary,'evidence':rel})
    p.write_text(json.dumps(d,indent=2)+'\n')
p=root/'docs/rebuild/rev118/CONTINUATION_20261022.md';p.write_text(p.read_text()+'\n\n## Original native close observations —28October\n\n'+summary+'\n\n[Source receipt]('+rel+'). '+result['next']+'\n')
doc='# Original native closing-balance observations\n\n'+summary+'\n\n[Exact source receipt](../'+rel+') retains original failed attempts, real SQL/HTTP qualification, full discovery, all source pins and remaining requirements.\n\nThe existing financial journal retains its original cash record format and accepts a distinct versioned close-observation format. Reopen/replay reconstructs the original source and anchor; late conflicts affect current use without rewriting historical completion. Native version collisions are held, not guessed. The existing native collector, financial materializer and owner read model share this path. No order, payment, wallet or host effect is published.\n\nComplete economic fee/allocation/settlement qualification and compensations, all-origin transactional reservations, immutable parent budgets, current qualified policy/cohort and actual effect consumers. MT5, spot/multi-asset, manual/payment/transfer/handover and every other original backend/ML/assistant/crypto/operations requirement remain. Android still uses its provisioned production profile on Van trading core and requires BG-001, signing and actual Artemis/S24 acceptance. Profitability remains an evidence-based objective.\n'
(root/'docs/rebuild/rev118/backend/BE-006_009_010_NATIVE_CLOSE_OBSERVATIONS.md').write_text(doc)
p=root/'docs/rebuild/rev118/backend/BE-009_010_SHARED_RESOURCE_WORK.md';p.write_text(p.read_text()+'\nOriginal native close observations now have a [same-journal capture/materialization/readback path](BE-006_009_010_NATIVE_CLOSE_OBSERVATIONS.md). This is bounded observation evidence; step5 native/economic settlement, fee allocation, compensation and reservation release remain open.\n')
p=root/'docs/rebuild/rev118/BUILD_EXECUTION_PLAN.md';s=p.read_text();start=s.index('## Current concrete gap and next result');end=s.index('## Commands and evidence economy',start)
section='## Current concrete gap and next result\n\nPublished8ff365d4 completed genuine hooks, required-baseline committed GREEN195, normal push and independent exact remote readback. Exact hosted main40755754628 is FAILED:17public jobs succeeded,2mandatory prerequisites failed (trusted-main checker missing and privateDDSkey unprovisioned). All4supporting workflows succeeded. Independent original archive readback:5162trading passes/1declaredDDSskip,26PostgreSQL,117voice;5872gateway passes/7declaredskips and198media passes. Skips remain unexecuted; source compile evidence is not native/provider qualification.\n\n'+summary+'\n\n[Exact source receipt]('+rel+'). '+result['next']+'\n\nComplete future and multi-asset fee/fill/price obligations, family/correlation and immutable parent budgets, qualified current policy/cohort, all-origin transactional reservations/outbox and effectful settlement/reconciliation. Current shared holds and close observations remain unqualified for dispatch or spend. Preserve all payment/manual/handover, markets/feeds/depth/entitlements, forecast/learning/crypto, assistant and security/operations obligations. Android follows original gates and its provisioned production profile on Van trading core, signing and actual Artemis/Samsung S24 evidence. No original dependency, function or acceptance identity is omitted.\n\n'
p.write_text(s[:start]+section+s[end:]);copy(__file__,'evidence-builder.py')
print(json.dumps({'passed':449,'pins':len(pins),'original_test_files_preserved':files,'original_test_functions_preserved':functions,'raw_files':sum(p.is_file() for p in raw.rglob('*')),'receipt':rel}))
