from pathlib import Path
import ast,collections,datetime,hashlib,io,json,shutil,subprocess,tarfile,xml.etree.ElementTree as ET

root=Path('/workspace/van-review-2026-10-18/publish')
base='0726ee9f4ea6a022442b6e76cfd29392512e7166'
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()==base
stem='van-entry-margin-binding-'
all_calls=[];pins=None;cases_count=0
partitions={}
for name in ['full-sql-r2']:
    d=Path('/workspace/'+stem+name+'-20261028')
    receipt=json.loads((d/'receipt.json').read_text())
    outer=json.loads(Path(str(d).replace('-20261028','-process-20261028')+'.json').read_text())
    assert receipt['completed'] and receipt['exit']==outer['exit']==0
    assert receipt['cleaned'] and receipt['owned_fixture_independently_absent']
    assert not json.loads((d/'storage-audit.json').read_text())['forbidden_events']
    source=receipt['source_sha256']|receipt['reference_fixtures_sha256']
    assert all(hashlib.sha256((root/p).read_bytes()).hexdigest()==h for p,h in source.items())
    if pins is None:pins=source
    assert pins==source
    cases=ET.parse(d/'full-trading.xml').findall('.//testcase')
    assert cases and all(all(c.find(k) is None for k in ['failure','error','skipped']) for c in cases)
    calls=[json.loads(l) for l in (d/'test-events.jsonl').read_text().splitlines() if json.loads(l)['phase']=='call']
    assert len(cases)==len(calls) and all(c['outcome']=='passed' for c in calls)
    all_calls.extend(c['nodeid'] for c in calls);cases_count+=len(cases)
    partitions[name]={'passed':len(cases),'inner_exit':0,'outer_exit':0,'audit_violations':0,'owned_postgres_independently_absent':True}
assert all(n==1 for n in collections.Counter(all_calls).values())
collection=Path('/workspace/'+stem+'collection-r2-20261028')
assert json.loads(collection.with_suffix('.json').read_text())['exit']==0
discovered=[l for l in collection.with_suffix('.log').read_text().splitlines() if l.startswith(('trading/tests/','backend/tests/','tests/rebuild/')) and '::' in l]
assert len(discovered)==len(set(discovered))==len(all_calls) and set(discovered)==set(all_calls)

preserved=0;reviewed=[]
allowed={'trading/tests/test_boolean_execution_receipts.py':{'test_false_text_from_order_check_cannot_reach_the_actual_send','test_unconfirmed_native_stop_is_not_reported_protected_and_uses_the_actual_flatten_path','test_malformed_reply_after_a_sent_modification_stays_unknown'},'trading/tests/test_receipt_availability_clock.py':{'test_experience_rejects_unmeasured_availability_with_a_real_positive_control'},'trading/tests/test_provider_entry_deadline.py':{'test_actual_router_binds_ctrader_mandate_and_original_quote_through_wire_dispatch'}}
arch=subprocess.check_output(['git','archive',base,'trading/tests','tests/rebuild'],cwd=root)
with tarfile.open(fileobj=io.BytesIO(arch)) as tar:
    for member in tar:
        if not member.isfile() or not Path(member.name).name.startswith('test_') or not member.name.endswith('.py'):continue
        old=ast.parse(tar.extractfile(member).read());new=ast.parse((root/member.name).read_bytes())
        def functions(tree):return {n.name:ast.dump(n) for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name.startswith('test_')}
        a,b=functions(old),functions(new)
        changed={k for k,v in a.items() if b.get(k)!=v}
        assert changed==allowed.get(member.name,set()),(member.name,changed)
        for name in changed:reviewed.append({'file':member.name,'function':name,'before_AST_sha256':hashlib.sha256(a[name].encode()).hexdigest(),'after_AST_sha256':hashlib.sha256(b[name].encode()).hexdigest()})
        preserved+=len(a)-len(changed)
assert len(reviewed)==5

raw=root/'docs/rebuild/rev118/ci/entry_margin_binding_20261028'
assert not raw.exists();raw.mkdir(parents=True)
def copy(src,rel):
    src=Path(src);dest=raw/rel;dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(src,dest);assert src.read_bytes()==dest.read_bytes()
for name in ['full-sql-r2','full-sql-r1','recovery-sql-r1','rest-sql-r1','focused-sql-r1','focused-sql-r2','focused-sql-r3']:
    d=Path('/workspace/'+stem+name+'-20261028')
    for p in d.iterdir():
        if p.is_file():copy(p,name+'/'+p.name)
    copy(str(d)+'.py',name+'/controller.py')
    copy(str(d).replace('-20261028','-process-20261028')+'.json',name+'/outer-process.json')
copy('/workspace/'+stem+'focused-sql-r1-owned-interrupt-20261028.json','focused-sql-r1/verified-owned-interrupt.json')
copy('/workspace/'+stem+'full-sql-r1-owned-interrupt-20261028.json','full-sql-r1/verified-owned-interrupt.json')
for name in ['before','r1','r2','r3','r4','dispatch-r1','dispatch-r2','boolean-r1','boolean-r2','consumers-r1','consumers-r2','consumers-r3','clock-before','clock-after','short-independent','short-independent-r2','short-independent-r3','short-independent-r4','short-independent-r5']:
    for suffix in ['.json','.log','.xml','-audit.json']:
        p=Path('/workspace/'+stem+name+'-20261028'+suffix)
        if p.exists():copy(p,'focused/'+p.name)
short=Path('/workspace/'+stem+'short-independent-r5-20261028')
assert json.loads(short.with_suffix('.json').read_text())['exit']==0
short_cases=ET.parse(short.with_suffix('.xml')).findall('.//testcase')
assert len(short_cases)==2 and all(all(c.find(k) is None for k in ['error','failure','skipped']) for c in short_cases)
copy('/workspace/test_van_short_entry_margin_binding_20261028.py','focused/independent-short-side-source.py')
for name in ['scope-check','owner-registry','owner-registry-r2','frontend-registry','mutation-consistency','consolidation','collection-r2']:
    p=Path('/workspace/'+stem+name+'-20261028.json');r=json.loads(p.read_text())
    assert r['exit']==(2 if name=='owner-registry' else 0)
    for ext in ['.json','.log']:copy(p.with_suffix(ext),'checks/'+p.with_suffix(ext).name)
for name in ['scope-check','owner-registry','frontend-registry','mutation-consistency','consolidation']:
    p=Path('/workspace/'+stem+'final-'+name+'-20261028.json');assert json.loads(p.read_text())['exit']==0
    for ext in ['.json','.log']:copy(p.with_suffix(ext),'checks/'+p.with_suffix(ext).name)
for ext in ['.json','.zip']:copy('/workspace/'+stem+'wip5-20261028'+ext,'recovery/wip5'+ext)
for name in ['full-targets','collect']:
    ext='.json' if name=='full-targets' else '.py'
    copy('/workspace/'+stem+name+'-20261028'+ext,'checks/'+name+ext)
for name in ['terminal-workflows','terminal-jobs']:
    copy('/workspace/van-0726ee9f-'+name+'-20261028.json','published_parent/'+name+'.json')
for job in [122890635245,122890637264]:
    copy('/workspace/van-0726ee9f-mandatory-job-'+str(job)+'-20261028.log','published_parent/job-'+str(job)+'.log')
parentlog=Path('/workspace/van-0726ee9f-postgres-hosted-original-20261028.log')
assert all(s in parentlog.read_text() for s in ['5085 passed, 1 skipped','26 passed in','117 passed'])
copy(parentlog,'published_parent/original-postgres-job.log')
proof={'base':base,'original_test_functions_AST_preserved':preserved,'full_collection_matches_unique_executed_cases':len(all_calls),'partitions':partitions,'reviewed_test_function_changes':reviewed,'source_pins_sha256':pins}
(raw/'source-preservation-and-discovery.json').write_text(json.dumps(proof,indent=2)+'\n')
summary=(f'The actual MT5 SDK/EA and cTrader runtime entry path now captures an original native margin read for the exact sealed intended order, stores its full command binding through the existing NativeMarginBook and independently reads the original committed receipt before ORDER_COMMAND. Original durable risk input, account/product/side/quantity and full command seal remain linked. MT5 retains original reference-price identity; cTrader explicitly retains provider-current-price-only semantics. Quote/command expiry is checked inside the SQL writer and again after current-risk reads; quotes and bindings share one monotonic committed storage clock; kill, lease, owner and existing execution guards retain authority. Historical replay preserves the first receipt, lost storage ACK remains typed unknown, and competing PostgreSQL writers retain one completion. This is source evidence/data-only, not a shared financial reservation or new order authority. Final clean SQL/HTTP qualification covers all {cases_count} independently discovered cases exactly once, with0fail/error/skip/storage violations, actual inner/outerexit0 and the owned PostgreSQL fixture independently absent. All {len(pins)} source/fixture pins match; {preserved} original trading/rebuild test functions retain identical AST;5 reviewed consumer-test fixture migrations retain behavioral assertions and expand exact native-read traces.0formal/native/production/S24acceptances issued.')
rel='receipts/ENTRY_MARGIN_BINDING_SOURCE_20261028.json'
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
receipt={'schema':'van.rev118.entry-margin-binding-source/1','source_parent':base,'observed_at_utc':now,'source_files_sha256':json.loads(Path('/workspace/'+stem+'wip5-20261028.json').read_text())['manifest']['files'],'implementation':summary,'source_result':{'partitions':partitions,'unique_passed_cases':cases_count,'full_discovered_case_set_matches_executed':True,'source_and_fixture_pins_matched':len(pins),'original_test_functions_AST_preserved':preserved,'reviewed_test_functions':reviewed,'raw':'ci/entry_margin_binding_20261028'},'independent_short_side':{'passed':2,'actual_exit':0,'included_in_full_run_count':False,'mt5':'original SELL request retained','ctrader':'actual sell_margin selected, distinct from buy_margin'},'source_authorizations':['auth-20261022-owner-autonomous-candidate-build'],'retained_failures':['Before:actualexit1,2missing capture_entry failures; no completed behavior inferred.','Focusedr1:12passed1failed; new cTrader test asked .10lots while the explicit original native fixture quoted .123lots. Corrected new test to the exact original .123; the production quantity-match refusal remains.','Dispatchr1:42passed4failed30declaredPGskips; original native-deadline fixture omitted durable original risk/native context. Only fixture producer corrected; original test functions/assertions unchanged. Fresh realPG later executes all recovery cases.','FocusedSQLr1 interrupted after original uncertain-entry producer lacked the new read protocol. Actualexit2/partial, exact owned PID independently verified before interrupt; ownedPG absent.','FocusedSQLr2:2passed1failed. The simulated signed margin response arrived at the next bar, one hour beyond its four-second deadline. The actual native read waits directly on the durable queue result. Fixture now answers read-only MARGIN_QUOTE immediately after its actual queue enqueue through the original signed poll endpoint; effectful order sends retain timeout/lost-ACK boundaries.','Independent short-side first attempt had2fixture-discovery errors before any functional assertion. The next attempt had2actual owner-key-registration fixture failures; the external module now explicitly imports both existing owner-registration and cleanup fixtures. Third/fourth attempts correctly refused oversized new SHORT fixture requests; their wider stops independently approved less than the requested quantities. The final fixture mirrors the original22pip stop distance around its actual1.10010entry and asserts requested size is within the independently approved original size before the native read. The production original-approval limit remains unchanged. No production authority check was bypassed; final independent2cases pass.','FullSQLr1 was deliberately interrupted with actual inner/outerexit2 after identifying a cross-record storage-clock regression boundary; only exact owned audit PID597153 was signalled after parent/controller/cmdline verification. Its ownedPG was independently absent; not a passing run. Clock-before independently reproduced2unsafe chronology acceptances; clock-after100focused cases pass, preserving original quote/binding availability.','RestSQLr1 is a failed run with6consumer-fixture failures:missing original native inputs in2boolean/2cTrader cases and duplicate incomplete original-risk records in2receipt-timing cases. Original behavior assertions remain in the migrated fixtures; final consumer suite57passed. Booleanr1/r2 and consumersr1/r2 failed during explicit native fixture migration; their raw evidence is retained. Final full run includes all cases again without ignores.','Owner registry command r1 actualexit2:wrong checker CLI rejected --check without changing files. Correct source-contract checker r2 passed.'], 'fixture_preservation':'All but5original test functions retain identical AST. The5reviewed consumer tests migrate fixture parameters, keep real behavioral assertions, expand exact boolean-protocol call traces for newly required native reads and remove a duplicate incomplete risk input now supplied by flow. Native deadline fixture now supplies actual durable original risk/native context. Uncertain-entry fixture advertises its explicit simulated margin protocol, answers only read-only requests through signed HTTP, retains effect-only delivery identity and injects lost enqueue ACK only for original ENTRY_OPS. Its one-effect-claim SQL assertion now counts those exact entry operations rather than an unrelated preceding read. No duplicate-effect assertion removed. Native APIs remain explicit source fixtures, not connected broker evidence.','published_parent':{'head':base,'main_run':40709514471,'public_jobs_success':17,'required_prerequisite_jobs_failed':2,'failure_reasons':['DDS read deploy key unprovisioned','trusted-main ledger checker missing'],'supporting_workflows_success':4,'original_postgres_job':122890635282,'trading_passed':5085,'declared_private_DDS_skips':1,'postgres_passed':26,'voice_passed':117,'original_JUnit_archive_independently_verified':False,'native_compile_job_success_original_artifact_readback':'UNAVAILABLE:artifact download tool returned697byte JSON metadata instead of advertised108683byte ZIP; rejected before extraction. Direct approved archive GET denied. No new independent compiler/binary readback claimed.'},'formal_acceptances_issued':0,'limitations':['No quote creates spendable collateral, reservation, settlement or execution authority. Current risk/mandate/owner/lease/kill/native protections remain their existing owners.','Shared all-origin transactional cash/margin/stop-risk reservations, active-policy arbitration, qualified FX/contracts/fees/fill contingencies, actual post-fill margin and full working-order/partial-fill/cancel/funding/payment economic finality remain required.','MT5 original request price is a quote reference, not an independently approved stop/price. cTrader native quote does not accept that price. Native account snapshots are bracketed, not atomic. No pending-order support or provider/account qualification is inferred.','Every other original backend, ML/learning/crypto/assistant/operations and Android contract remains. Profitability requires evidence, never a guarantee.'], 'next':'Commit through genuine Project Truth hook; verify committed ledger against4fd466de; normal push, independent exact remote readback and exact-source CI. Continue existing-ledger all-origin reservations and remaining canonical backend programme; Android only with original gates and actual provisioned-profile/signing/Artemis-S24 evidence.'}
(root/'docs/rebuild/rev118'/rel).write_text(json.dumps(receipt,indent=2)+'\n')
for name in ['EXECUTION_LEDGER.json','CANDIDATE_SOURCE_PROGRESS.json']:
    p=root/'docs/rebuild/rev118'/name;v=json.loads(p.read_text());v['updated_at_utc']=now
    if name=='EXECUTION_LEDGER.json':
        v['observations'].append(summary);v['current_action']=receipt['next']
        for uid in ['BE-003','BE-009','BE-010']:v['units'][uid]['evidence'].append(rel)
    else:
        for uid in ['BE-003','BE-009','BE-010']:v['units'][uid]['milestones'].append({'description':summary,'evidence':rel})
    p.write_text(json.dumps(v,indent=2)+'\n')
(root/'docs/rebuild/rev118/backend/BE-009_010_ENTRY_MARGIN_BINDING.md').write_text('# Original intended-order margin binding\n\n'+summary+'\n\n[Exact source receipt](../'+rel+') retains actual failed/partial runs and the final clean full qualification. Independent full collection equals its unique executed case set; no omitted file is treated as passed. Original SDK/EA and cTrader source fixtures are not provider/financial acceptance.\n\nThe existing NativeMarginBook owns immutable quote and exact command linkage in the original ledger. Reopen/replay never renews the quote or its first availability. No full order or native price/stop approval is manufactured from a margin read. cTrader keeps explicit provider-current-price semantics.\n\nComplete all-origin cash/margin/stop-risk reservations with current-policy arbitration and original native/economic reconciliation. A timeout, empty account, cancellation request or expired quote cannot release an uncertain effect. Retain all frozen unit, feature, error/recovery, owner and frontend contracts, then original Android gates and provisioned profile on Van trading core.\n')
p=root/'docs/rebuild/rev118/CONTINUATION_20261022.md';p.write_text(p.read_text()+'\n\n## Exact intended-order margin binding —28October\n\n'+summary+'\n\n[Source receipt]('+rel+'). '+receipt['next']+'\n')
p=root/'docs/rebuild/rev118/BUILD_EXECUTION_PLAN.md';text=p.read_text();start=text.index('## Current concrete gap and next result');end=text.index('## Commands and evidence economy',start)
p.write_text(text[:start]+'## Current concrete gap and next result\n\nPublished0726ee9f completed genuine hooks, committed GREEN193 and independent exact remote readback. Its5314 local source checks passed. Exact hosted main CI finished17public successes/2mandatory prerequisite failures; all4support workflows succeeded. Original hosted log:5085trading passes/1declaredprivateDDSskip,26PostgreSQL and117voice passes. EA compile job succeeded; original artifact readback remains unavailable because the download tool returned metadata instead of the advertised ZIP. No new compiler/binary proof is claimed.\n\n'+summary+'\n\n[Source receipt]('+rel+'). '+receipt['next']+'\n\nShared all-origin cash/margin/stop-risk reservations are the next required financial-owner integration, not delivered by this binding. Complete current-policy arbitration, qualified valuation/fees, actual post-fill and working-order/partial-fill/cancel reconciliation; full funding/payment/manual/handover effects; all market/feed/depth/entitlement, forecast/learning/crypto, assistant and security/operations obligations. Android must use its provisioned production profile on Van trading core with original BG-001, signing and actual Artemis/Samsung S24 evidence. Preserve every original dependency and acceptance identity.\n\n'+text[end:])
copy(__file__,'evidence-builder.py')
print(json.dumps({'unique_passed':cases_count,'pins':len(pins),'preserved_original_test_functions':preserved,'partitions':partitions,'raw_files':sum(p.is_file() for p in raw.rglob('*')),'receipt':rel}))
