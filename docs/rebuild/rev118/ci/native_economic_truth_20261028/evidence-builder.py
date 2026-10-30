from pathlib import Path
import ast,datetime,hashlib,io,json,shutil,subprocess,tarfile,xml.etree.ElementTree as ET

root=Path('/workspace/van-review-2026-10-18/publish');base='3bec9a18e7b51f73a19c872c13e642138d27d41e'
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()==base
run=Path('/workspace/van-native-economic-truth-full-sql-r1-20261028')
r=json.loads((run/'receipt.json').read_text());assert r['exit']==0 and r['completed'] and r['cleaned'] and r['owned_fixture_independently_absent']
pins=r['source_sha256']|r['reference_fixtures_sha256'];assert len(pins)==1286
assert all(hashlib.sha256((root/f).read_bytes()).hexdigest()==h for f,h in pins.items())
assert not json.loads((run/'storage-audit.json').read_text())['forbidden_events']
main_cases=ET.parse(run/'full-trading.xml').findall('.//testcase')
assert len(main_cases)==5303 and all(not any(c.find(k)is not None for k in ('failure','error','skipped')) for c in main_cases)
main_calls=[json.loads(s) for s in (run/'test-events.jsonl').read_text().splitlines() if json.loads(s)['phase']=='call']
assert len(main_calls)==len({c['nodeid'] for c in main_calls})==5303 and all(c['outcome']=='passed' for c in main_calls)
supp=Path('/workspace/van-native-entry-risk-recovery-final-20261028')
assert json.loads(supp.with_suffix('.json').read_text())['exit']==0
assert not json.loads(Path('/workspace/van-native-entry-risk-recovery-final-audit-20261028.json').read_text())['forbidden_events']
sp=json.loads(Path('/workspace/van-native-entry-risk-recovery-final-start-20261028.json').read_text())['source_pins_before_final_supplement']
assert all(hashlib.sha256((root/f).read_bytes()).hexdigest()==h for f,h in sp.items()) and set(sp)-set(pins)=={'trading/tests/test_native_entry_risk_recovery.py'}
assert all(sp[f]==h for f,h in pins.items());pins=sp
extra_cases=ET.parse(supp.with_suffix('.xml')).findall('.//testcase')
assert len(extra_cases)==2 and all(not any(c.find(k)is not None for k in ('failure','error','skipped')) for c in extra_cases)
extra_calls=[json.loads(s) for s in Path('/workspace/van-native-entry-risk-recovery-final-events-20261028.jsonl').read_text().splitlines() if json.loads(s)['phase']=='call']
assert len(extra_calls)==len({c['nodeid'] for c in extra_calls})==2 and all(c['outcome']=='passed' for c in extra_calls)
calls=main_calls+extra_calls;assert len(calls)==len({c['nodeid'] for c in calls})==5305
collection=Path('/workspace/van-native-economic-truth-collection-20261028');assert json.loads(collection.with_suffix('.json').read_text())['exit']==0
nodes=[s for s in collection.with_suffix('.log').read_text().splitlines() if s.startswith(('trading/tests/','backend/tests/','tests/rebuild/')) and '::' in s]
assert len(nodes)==len(set(nodes))==5305 and set(nodes)=={c['nodeid'] for c in calls}
protocol={}
for name in ['OpenApiCommonMessages.proto','OpenApiCommonModelMessages.proto','OpenApiMessages.proto','OpenApiModelMessages.proto','PROVENANCE.json']:
 f='trading/vati/execution/ctrader/proto/'+name;b=(root/f).read_bytes()
 assert b==subprocess.check_output(['git','show',base+':'+f],cwd=root);protocol[f]=hashlib.sha256(b).hexdigest()
files=functions=0
with tarfile.open(fileobj=io.BytesIO(subprocess.check_output(['git','archive',base,'trading/tests','tests/rebuild'],cwd=root))) as tar:
 for m in tar:
  if not m.isfile() or not m.name.endswith('.py') or not Path(m.name).name.startswith('test_'):continue
  old=tar.extractfile(m).read();assert old==(root/m.name).read_bytes(),m.name;files+=1
  functions+=sum(isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name.startswith('test_') for n in ast.walk(ast.parse(old)))
for name in ('workmap','owner','frontend','mutations','consolidation'):
 assert json.loads(Path('/workspace/van-native-economic-truth-'+name+'-20261028.json').read_text())['exit']==0
raw=root/'docs/rebuild/rev118/ci/native_economic_truth_20261028';raw.mkdir(parents=True,exist_ok=True)
def copy(source,dest):
 source=Path(source);dest=raw/dest;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest);assert source.read_bytes()==dest.read_bytes()
prefixes=('van-native-fee-terms-','van-native-entry-volume-','van-native-entry-pending-',
 'van-native-entry-risk-recovery-','van-native-economic-truth-')
for p in Path('/workspace').iterdir():
 if not p.name.startswith(prefixes) or 'wip' in p.name or p==Path(__file__):continue
 if p.is_dir():
  for c in p.iterdir():
   if c.is_file():copy(c,'runs/'+p.name+'/'+c.name)
 elif p.suffix in ('.json','.log','.xml','.py','.jsonl'):copy(p,'runs/'+p.name)
for ext in ('.json','.zip'):copy('/workspace/van-native-economic-truth-wip2-20261028'+ext,'recovery/wip2'+ext)
for name in ['van-3bec9a18-postgres-artifact-meta-20261028.json','van-3bec9a18-postgres-original-20261028.zip',
 'van-3bec9a18-postgres-archive-readback-20261028.json','van-3bec9a18-failed-job-123111940275-original-20261028.log',
 'van-3bec9a18-failed-job-123112992807-original-20261028.log','van-3bec9a18-android-original-rerun-request-20261028.json',
 'van-3bec9a18-ci-current-20261028.json','van-b0317e3d-backend-public-cancelled-original-20261028.log',
 'van-b0317e3d-backend-public-cancelled-20261028.zip','van-b0317e3d-backend-public-cancelled-readback-20261028.json']:
 copy('/workspace/'+name,'published-parent/'+name)
proof={'source_parent':base,'broad_cases_passed':5303,'separate_new_recovery_cases_passed':2,
 'current_source_unique_cases_passed':5305,'failed':0,'errors':0,'skipped':0,'audit_violations':0,
 'partition_note':'Two new recovery/ownership tests were added after broad collection and separately rerun with source hashes and call diagnostics. Product code was final and unchanged for both partitions. This is not one full current-collection run.',
 'every_current_discovered_case_executed_once_in_final_partition_union':True,'source_and_fixture_pins':pins,
 'separate_native_protocol_reference_pins_equal_committed_parent':protocol,
 'owned_postgres_independently_absent':True,'original_test_files_byte_identical':files,
 'original_test_functions_AST_preserved':functions,'native_or_production_acceptance':False}
(raw/'source-preservation-and-discovery.json').write_text(json.dumps(proof,indent=2)+'\n')
summary=(f'The existing native margin/entry owner now reads original commission vintages and gross native entry volume. All four pinned commission types use exact native units; precise fields never fall back to deprecated fields or missing-as-zero. Minimums combine only in the same proven denomination; unknown conversion, financing, sign convention and charge-count bounds remain explicit. Conditional scenarios retain their exact inputs and confer no fee reservation. Original dispatched commands, verified receipts and deduplicated deal publications supply gross entry volume across aliases, preserving raw fees and original availability anchors. Fees, other orders, closes or changed history cannot reopen an entry allowance. A real counterexample showed the actual cached pending-risk owner accepting a zero-fill rejection after an original native fill arrived. It now reloads on deal statements and refuses native overfill or contradictory no-effect claims; original partial readback can restore conservative pending risk. Product code passed{5303}full trading/SQLite/PostgreSQL/HTTP cases plus2separately added and source-pinned recovery/ownership cases:5305unique current cases,0fail/error/skip/audit, current discovery/call IDs once across the final partition union, all{len(pins)}source/fixture hashes matching and ownedPostgreSQL independently absent. This is two explicit partitions, not one clean current-collection run. All{files}inherited test files/{functions}original test functions remain byte-identical. Complete future fee/fill/price/multi-asset obligations, parent/child lifetime budgets, qualified policy/cohort and all-origin transactional reservations/economic settlement remain open. No unit/native/provider/production/S24 acceptance is issued.')
rel='receipts/NATIVE_FEE_GROSS_ENTRY_SOURCE_20261028.json';now=datetime.datetime.now(datetime.UTC).isoformat()
next_action='Finish exact published3bec CI and reconcile the original SDK installation failure by a bounded original-job retry after workflow terminal; preserve all gates and failed receipts. Then genuine hooks, required-baseline committed verification, normal push/readback and exact-head hosted qualification for this packet. Continue full economic obligations/all-origin reservations, immutable parent/child budgets, current policy/cohort and every remaining original backend/Android requirement.'
receipt={'schema':'van.rev118.native-fee-gross-entry-source/1','observed_at_utc':now,'source_parent':base,
 'state':'PARTIAL_CANDIDATE_SOURCE_TESTED_NOT_COMPLETE_FEES_PARENT_BUDGET_OR_RESERVATION','implementation':summary,
 'checks':proof,'authority':'auth-20261022-owner-autonomous-candidate-build','raw':'ci/native_economic_truth_20261028',
 'native_fee_reference':{'url':'https://help.ctrader.com/open-api/model-messages/',
  'meaning':'Pinned ProtoOACommissionType and precise rate/minimum units; original observed contract fields remain the source. A current documentation lookup does not qualify an account, native fee sign, conversion, fill count or complete future costs.'},
 'retained_failures':['Three original4-failure prototype runs are retained: dispatched commands include original extra binding fields; NativeAccountRiskContext has no environment attribute; the deal owner as_of argument is a durable publication hash, not a timestamp. Corrected to actual owners/contracts, no inherited test changed.',
 'Actual pending-risk contradiction counterexample:6passed1failed before correction;75focused passed after. Earlier65/72fee,190/191SQL and4gross successes overlap the final full5303/extra2 and are not added.',
 'Published3bec Android SDK emulator preparation failed with Error on ZipFile unknown archive before app tests; Character Forge correctly refused absent RiveContractTest evidence. Original job retry returned403 because workflow stillrunning. No Android assertions or gate pass inferred.',
 'Publishedb031 gateway source job was cancelled on successor publication and produced no gateway JUnit. Original verified partial artifact retains198media passes, not a full gateway pass.'],
 'published_parent':{'head':base,'main_run':40772084829,'state':'IN_PROGRESS_AT_LAST_READBACK',
  'four_supporting_workflows':'SUCCESS','original_postgres_artifact':{'artifact_id':12853456941,'bytes':200278,
   'sha256':'da63ef5c03c97eba9d50176a8867ac0c7e5b949833f5667cfa47468b038a25d5',
   'trading_passed':5219,'trading_declared_DDS_skip':1,'postgres_passed':26,'voice_passed':117},
  'mandatory_prerequisites':'trusted-main ledger checker absent and privateDDSread key unprovisioned; enforced'},
 'limits':['Native entry reader bounds:100000ledger events and32MiBcanonical history by default; capacity refusal is not measured production capacity.',
  'Only original cTrader deal/order joins are supported by this new reader; MT5/spot multi-asset/native-family reconciliation remain original obligations.',
  'Gross quantities do not implement parent/child dispatch or budget admission, fee allocation, finality, settlement, compensation or release.',
  'Existing provisional hold schema and its immutable missing requirements, fees-unmeasured state and dispatch=false are unchanged.'],
 'remaining':['complete native future fees/financing/fill/price and multi-asset principal/fee/conversion obligations',
  'immutable lifetime parent budgets and full child methods, family/correlation, current qualified policy and effect-capable cohort',
  'all-origin transactional order/manual/payment/transfer/handover reservation/outbox and actual effect consumers',
  'native economic finality and nonduplicated asset/margin release, bust/reversal/late-fee compensation',
  'all canonical market/feed/depth/news/entitlement,38forecast/research,assistant/voice/crypto,security/operations and gated Android/provisioned-profile/signing/Artemis S24 requirements'],
 'formal_acceptance':'NOT_ISSUED','execution_authority':False,'settlement_qualified':False,'next':next_action}
(root/'docs/rebuild/rev118'/rel).write_text(json.dumps(receipt,indent=2)+'\n')
for name in ('EXECUTION_LEDGER.json','CANDIDATE_SOURCE_PROGRESS.json'):
 p=root/'docs/rebuild/rev118'/name;d=json.loads(p.read_text());d['updated_at_utc']=now
 if name=='EXECUTION_LEDGER.json':
  d['observations'].append(summary);d['current_action']=next_action
  for uid in ('BE-009','BE-010','BE-012'):
   row=d['units'].setdefault(uid,{'status':'IN_PROGRESS','candidate_source_only':True,'acceptance':'NOT_ISSUED','evidence':[]})
   if rel not in row['evidence']:row['evidence'].append(rel)
 else:
  for uid in ('BE-009','BE-010','BE-012'):d['units'][uid]['milestones'].append({'description':summary,'evidence':rel})
 p.write_text(json.dumps(d,indent=2)+'\n')
p=root/'docs/rebuild/rev118/CONTINUATION_20261022.md';p.write_text(p.read_text()+'\n\n## Original native fee and entry truth —28October\n\n'+summary+'\n\n[Source receipt]('+rel+'). '+next_action+'\n')
doc='# Original native fee terms, gross entry volume and pending-risk reconciliation\n\n'+summary+'\n\n[Source receipt](../'+rel+') retains every original failed counterexample, source/call/collection partitions, native protocol pins and unchanged tests. The actual collector fixtures speak the existing protocol; no connected broker account or live qualification is claimed.\n\nThe existing margin book retains its original record formats and adds read methods for those original vintages. The new view resolves actual dispatched command and receipt identities, physical monetary scope, native symbol/order IDs and original deal publication hashes. Repeated statements cannot duplicate gross execution. Later conflicting native observations refuse current use. Other orders and fee signs cannot reduce original gross entry volume. Gross overfill is preserved as a contradiction, not a negative remaining allowance. Parent remaining allowance stays unknown; no new parent/child protocol is silently substituted.\n\nThe actual pending-risk cache now invalidates on native deal publications. A zero-fill rejection contradicted by a native fill, or an overfill, blocks new-risk admission through the existing unavailable-source path. Risk reduction/protection retain their existing owners. Original partial-result reconciliation restores conservative pending exposure without re-sending the command. This does not close the transactional publication/race, legacy-obligation, shared collateral or native-economic settlement requirements.\n\nThe reader has declared100000event/32MiBdefault history bounds. This is not production capacity qualification. Native minimum charges are combined only in a proven common denomination; conditional turnover is an explicit scenario, never observed FX or an execution-price bound. Missing precise fields do not use deprecated zero-valued fields. MT5 fee absence, future financing/other charges, charge count, asset mapping/conversion and native sign qualification remain explicit. Existing provisional receipts, their immutable missing requirements and dispatch=false flags are unchanged.\n\nComplete all original financial/manual/payment/handover,markets,forecast/research,assistant/voice,crypto and operations requirements. Android still follows BG-001 and original gates, uses its provisioned production profile on Van trading core, and requires real signing and Artemis/S24 acceptance. Profitability requires evidence and is not guaranteed.\n'
(root/'docs/rebuild/rev118/backend/BE-009_010_NATIVE_FEE_AND_ENTRY_TRUTH.md').write_text(doc)
p=root/'docs/rebuild/rev118/BUILD_EXECUTION_PLAN.md';s=p.read_text();a=s.index('## Current concrete gap and next result');b=s.index('## Commands and evidence economy',a)
p.write_text(s[:a]+'## Current concrete gap and next result\n\n'+summary+'\n\n[Exact source receipt]('+rel+'). '+next_action+'\n\nPublished3bec local source qualification passed5261cases0skip/GREEN197 with exact normal remote readback. Original verified hosted evidence:5219trading passes/1declaredDDSskip,26PostgreSQL,117voice and4supporting successes. Main40772084829 is stillinprogress at the last readback. SDK emulator archive installation failed before app tests and Character Forge correctly refused missing instrumentation evidence; the original-job retry is unavailable while its workflow is running. Trusted-main/private-key prerequisites remain enforced. No full CI green or native/device acceptance is claimed.\n\nPreserve every original payment/manual/handover,market/feed/depth/entitlement,forecast/learning/crypto,assistant/security/operations obligation. Android uses its provisioned production profile on Van trading core after canonical gates, with real signing and Artemis/S24 acceptance. No dependency, function or acceptance identity is omitted.\n\n'+s[b:])
copy(__file__,'evidence-builder.py')
print(json.dumps({'full_passed':5303,'supplement_passed':2,'unique_current_cases':5305,'source_pins':len(pins),
 'protocol_reference_pins':len(protocol),'original_test_files_preserved':files,'original_test_functions_preserved':functions,
 'raw_files':sum(p.is_file() for p in raw.rglob('*')),'receipt':rel}))
