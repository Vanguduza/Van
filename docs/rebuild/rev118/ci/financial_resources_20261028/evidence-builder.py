from pathlib import Path
import ast,collections,datetime,hashlib,io,json,shutil,subprocess,tarfile,xml.etree.ElementTree as ET

root=Path('/workspace/van-review-2026-10-18/publish')
base='b876fc27f35765244fb169dbde1030f2b79b836e'
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()==base
raw=root/'docs/rebuild/rev118/ci/financial_resources_20261028'
assert not raw.exists()

def checked(name,expected,current):
    path=Path('/workspace/'+name+'-20261028')
    receipt=json.loads((path/'receipt.json').read_text())
    process=json.loads(Path(str(path).replace('-20261028','-process-20261028')+'.json').read_text())
    assert receipt['exit']==process['exit']==0 and receipt['completed'] and receipt['cleaned']
    assert receipt['owned_fixture_independently_absent']
    assert not json.loads((path/'storage-audit.json').read_text())['forbidden_events']
    cases=ET.parse(path/'full-trading.xml').findall('.//testcase')
    assert len(cases)==expected and all(all(c.find(k)is None for k in ['failure','error','skipped']) for c in cases)
    calls=[json.loads(x) for x in (path/'test-events.jsonl').read_text().splitlines() if json.loads(x)['phase']=='call']
    assert len(calls)==expected and all(c['outcome']=='passed' for c in calls)
    nodes={c['nodeid'] for c in calls};assert len(nodes)==expected
    pins=receipt['source_sha256']|receipt['reference_fixtures_sha256']
    mismatches=sorted(f for f,h in pins.items() if hashlib.sha256((root/f).read_bytes()).hexdigest()!=h)
    if current:assert not mismatches,mismatches
    return {'passed':expected,'inner_exit':0,'outer_exit':0,'audit_violations':0,
        'owned_postgres_independently_absent':True,'source_pins':pins,'current_input_differences':mismatches},nodes

broad,broad_nodes=checked('van-financial-resources-full-sql-r1',5390,False)
final,final_nodes=checked('van-provisional-resource-book-sql-r5',122,True)
assert broad['current_input_differences']==sorted(['trading/vati/risk/provisional_resource_book.py',
    'trading/tests/test_provisional_resource_book.py','trading/tests/test_entry_resource_groups.py'])
before=json.loads(Path('/workspace/van-financial-resources-broad-r1-verified-20261028.json').read_text())
assert before['pins']==broad['source_pins'] and before['source_and_fixture_pins_match_before_receipt_fix']==1274
collection=Path('/workspace/van-financial-resources-collection-20261028')
assert json.loads(collection.with_suffix('.json').read_text())['exit']==0
discovered=[x for x in collection.with_suffix('.log').read_text().splitlines()
    if x.startswith(('trading/tests/','backend/tests/','tests/rebuild/')) and '::' in x]
assert len(discovered)==len(set(discovered))==5391 and set(discovered)==broad_nodes|final_nodes
assert len(final_nodes-broad_nodes)==1
external=Path('/workspace/van-financial-resources-original-receipt-after-20261028')
assert json.loads(external.with_suffix('.json').read_text())['exit']==0
cases=ET.parse(external.with_suffix('.xml')).findall('.//testcase')
assert len(cases)==1 and all(cases[0].find(k)is None for k in ['failure','error','skipped'])
assert json.loads(Path('/workspace/van-provisional-original-receipt-before-20261028.json').read_text())['exit']==1

preserved=0;files_preserved=0
archive=subprocess.check_output(['git','archive',base,'trading/tests','tests/rebuild'],cwd=root)
with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
    for member in tar:
        if not member.isfile() or not member.name.endswith('.py') or not Path(member.name).name.startswith('test_'):continue
        old=tar.extractfile(member).read();new=(root/member.name).read_bytes()
        assert old==new,member.name
        files_preserved+=1
        preserved+=sum(isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name.startswith('test_') for n in ast.walk(ast.parse(old)))

raw.mkdir(parents=True)
def copy(src,relative):
    src=Path(src);dest=raw/relative;dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(src,dest);assert src.read_bytes()==dest.read_bytes()

prefixes=('van-current-entry-source-','van-entry-resource-projection-','van-provisional-resource-book-',
    'van-entry-resource-groups-','van-entry-resource-sqlite-lock-diagnostic-',
    'van-provisional-original-receipt-before-','van-financial-resources-original-receipt-after-')
for path in Path('/workspace').iterdir():
    if path.name.startswith(prefixes) and 'wip' not in path.name:
        if path.is_dir():
            for child in path.iterdir():
                if child.is_file():copy(child,'runs/'+path.name+'/'+child.name)
        elif path.suffix in ('.json','.log','.xml','.py'):
            copy(path,'runs/'+path.name)
full=Path('/workspace/van-financial-resources-full-sql-r1-20261028')
for path in full.iterdir():
    if path.is_file():copy(path,'broad-before-receipt-fix/'+path.name)
for suffix in ['.py','-process.json']:
    pass
copy(str(full)+'.py','broad-before-receipt-fix/controller.py')
copy('/workspace/van-financial-resources-full-sql-r1-process-20261028.json','broad-before-receipt-fix/outer-process.json')
copy('/workspace/van-financial-resources-broad-r1-verified-20261028.json','broad-before-receipt-fix/input-verification-before-mutation.json')
for name in ['scope-check','owner-registry','frontend-registry','mutation-consistency','consolidation','collection']:
    path=Path('/workspace/van-financial-resources-'+name+'-20261028')
    assert json.loads(path.with_suffix('.json').read_text())['exit']==0
    for ext in ['.json','.log']:copy(path.with_suffix(ext),'checks/'+path.name+ext)
for name in ['van-financial-resources-collect-20261028.py','van-financial-resources-full-targets-20261028.json']:
    copy('/workspace/'+name,'checks/'+name)
for version in [5,6]:
    for ext in ['.json','.zip']:copy('/workspace/van-financial-resource-owner-wip'+str(version)+'-20261028'+ext,'recovery/wip'+str(version)+ext)
for name in ['test_van_provisional_original_receipt_20261028.py','test_van_ctrader_signed_commission_20261028.py']:
    copy('/workspace/'+name,'independent/'+name)
for suffix in ['.json','.log','.xml','-audit.json']:
    copy('/workspace/van-ctrader-signed-commission-before-20261028'+suffix,'open-provider-semantics/signed-commission'+suffix)
copy('/workspace/van-ctrader-commission-sign-open-finding-20261028.json','open-provider-semantics/finding.json')
for name in ['van-b876fc27-terminal-candidate-0-20261028.json','van-b876fc27-terminal-candidate-1-20261028.json',
    'van-b876fc27-ledger-original-job-20261028.log','van-b876fc27-backend-original-job-20261028.log',
    'van-b876fc27-postgres-original-readback-20261028.json','van-b876fc27-postgres-original-20261028.zip']:
    copy('/workspace/'+name,'published-parent/'+name)
native=Path('/workspace/van-b876fc27-native-mql-download-20261028.raw')
assert hashlib.sha256(native.read_bytes()).hexdigest()=='4a594f0aea6e7dd3657b657d735415f7fb950018e745af1ae208e7ddb013fc24'
assert hashlib.sha256((root/'deploy/van-trading-core/mql5/VanBridgeEA.mq5').read_bytes()).hexdigest()=='a7a4f9ed47012d07e5f284654d625cbb149015c4bd25e555e2a523ff086afead'
copy(native,'published-parent/native-original.zip')
copy('/workspace/van-b876fc27-native-mql-20261028/verified-evidence.json','published-parent/native-independent-verification.json')

proof={'base':base,'broad_pre_receipt_fix':broad,'final_targeted_source':final,
    'current_discovered_case_count':5391,'coverage_union_equals_current_collection':True,
    'not_a_single_current_source_full_run':True,'independent_original_receipt_after_passed':1,
    'original_test_files_byte_identical':files_preserved,'original_test_functions_AST_preserved':preserved}
(raw/'source-preservation-and-check-partitions.json').write_text(json.dumps(proof,indent=2)+'\n')
now=datetime.datetime.now(datetime.UTC).isoformat()
summary=('Shared-resource source work remains IN_PROGRESS. Original sealed entry/native-margin/current-risk evidence and real signed mandate proof now feed exact projected cash, post-entry margin-floor equity, stop-risk, signed account/instrument slot counts and independent currency-leg intervals. The existing SQL writer retains one provisional hold across actual SQLite/PostgreSQL competitors; aliases share physical account capacity. Lost commit ACK, queued expiry, current-key revocation, original replay and resealed over-allocation retain explicit behavior. Original missing requirements are stored durably and cannot change with later code. Provisional holds cannot dispatch orders or qualify reservations. Broader pre-metadata-fix source:5390passed0; all1274pins matched before mutation. Final corrected source:122targeted SQL/source passes0 plus1independent receipt-replay pass. Only3new-component source/test inputs differ between these runs; all final source pins match, every current5391discovered case occurs in their coverage union, and all inherited test files remain byte-identical. These overlapping runs are not added together or called one current-source full run.0formal/native/production/S24acceptances.')
rel='receipts/PROVISIONAL_SHARED_RESOURCES_SOURCE_20261028.json'
receipt={'schema':'van.rev118.provisional-shared-resources-source/1','source_parent':base,'observed_at_utc':now,
    'state':'IN_PROGRESS_CANDIDATE_SOURCE_NOT_QUALIFIED_RESERVATIONS','implementation':summary,
    'source_checks':proof,'source_authorizations':['auth-20261022-owner-autonomous-candidate-build'],
    'reservation_qualified':False,'execution_authority':False,'formal_acceptance':'NOT_ISSUED',
    'retained_failures':['Original reader missing API failed before implementation.','Prototype multiplied sub-minor margin before quantization; one actual math failure retained; round margin first before applying existing floor.',
        'New2500margin competition fixtures replace earlier1600fixture that correctly fit twice; production capacity not loosened.',
        'New alias test initially signed maxOpen below default maxRisk; coherent explicit test grant corrected, production mandate validation retained.',
        'Group fixtures first reused an old signature after changing policy and were correctly rejected; existing test owner now signs actual effective policy. New tighter leg fixtures also required coherent smaller signed per-trade risk. Exact USD/EUR limiting-dimension expectation corrected; both monetary burdens remain asserted.',
        'Independent original receipt replay failed because current-code MISSING rewrote historical missing requirements; durable requirements fixed and independently passed.',
        'Commission sign probe remains failed/unqualified: positive-is-credit semantics require corroboration; no adapter change or provider qualification inferred.'],
    'remaining':['complete fee/fill/price/native-contract obligation envelopes and multi-asset fee reserves',
        'family/correlation limits and immutable parent lifetime budgets','current qualified policy and effect-capable runtime cohort',
        'all-origin transactional order/manual/payment/transfer/handover ownership and outbox',
        'legacy migration, working/uncertain/partial/cancel/native economic reconciliation and compensation',
        'actual effectful consumers and independent acceptance; all other canonical backend/forecast/assistant/crypto/operations and gated Android obligations'],
    'raw':'ci/financial_resources_20261028','next':'Continue complete economic obligation envelopes, current shared policy/cohort and actual financial-owner consumers; preserve every canonical full-workflow requirement. Publish reviewable partial source through genuine hooks and exact-head CI without treating it as feature completion.'}
(root/'docs/rebuild/rev118'/rel).write_text(json.dumps(receipt,indent=2)+'\n')
for name in ['EXECUTION_LEDGER.json','CANDIDATE_SOURCE_PROGRESS.json']:
    path=root/'docs/rebuild/rev118'/name;body=json.loads(path.read_text());body['updated_at_utc']=now
    if name=='EXECUTION_LEDGER.json':
        body['observations'].append(summary);body['current_action']=receipt['next']
        for uid in ['BE-009','BE-010']:
            assert body['units'][uid]['status']=='IN_PROGRESS'
            body['units'][uid]['evidence'].append(rel)
    else:
        for uid in ['BE-009','BE-010']:body['units'][uid]['milestones'].append({'description':summary,'evidence':rel})
    path.write_text(json.dumps(body,indent=2)+'\n')
path=root/'docs/rebuild/rev118/CONTINUATION_20261022.md';path.write_text(path.read_text()+'\n\n## Shared projected financial resources —28October\n\n'+summary+'\n\n[Exact source receipt]('+rel+'). '+receipt['next']+'\n')
path=root/'docs/rebuild/rev118/backend/BE-009_010_SHARED_RESOURCE_WORK.md';text=path.read_text();text=text.replace('Latest focused source run: 121 passes, no failures/errors/skips,','Final focused source run: 122 passes, no failures/errors/skips,');text=text.replace('The broader current-source regression run is pending; its original receipt is','The broader pre-receipt-metadata-fix run passed 5,390 cases. The final targeted run validates the corrected record format, plus one independent replay check. These overlapping revisions are not one current-source full run. Its original broad receipt is');path.write_text(text+'\n[Exact source receipt](../'+rel+') retains all test partitions, input differences, original failed probes and remaining full-feature obligations.\n')
copy(__file__,'evidence-builder.py')
print(json.dumps({'broad_pre_receipt_fix':5390,'final_targeted':122,'independent_after':1,'current_discovered':5391,
    'old_test_files_unchanged':files_preserved,'old_test_functions_preserved':preserved,'raw_files':sum(p.is_file() for p in raw.rglob('*')),'receipt':rel}))
