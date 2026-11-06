"""Bind the executed candidate without issuing native or formal acceptance."""
from pathlib import Path
import ast,collections,datetime,gzip,hashlib,io,json,subprocess,tarfile,zipfile
import xml.etree.ElementTree as ET

root=Path('/workspace/van-review-2026-10-18/publish');base='457205e3ac3c73f115a7bf7134b33c98bd905f12'
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()==base
run=Path('/workspace/van-mt5-native-cost-final-full-r1-20261029')
r=json.loads((run/'receipt.json').read_text())
assert r['completed'] and r['exit']==0 and r['cleaned'] and r['owned_fixture_independently_absent']
pins=r['source_sha256']|r['reference_fixtures_sha256']
assert len(pins)==1303 and all(hashlib.sha256((root/f).read_bytes()).hexdigest()==h for f,h in pins.items())
assert not json.loads((run/'storage-audit.json').read_text())['forbidden_events']
cases=ET.parse(run/'full-trading.xml').findall('.//testcase')
assert len(cases)==5385 and all(not any(c.find(k)is not None for k in ('failure','error','skipped')) for c in cases)
calls=[json.loads(s) for s in (run/'test-events.jsonl').read_text().splitlines() if json.loads(s)['phase']=='call']
assert len(calls)==len({c['nodeid'] for c in calls})==5385 and all(c['outcome']=='passed' for c in calls)
collection=Path('/workspace/van-mt5-native-cost-final-collection-20261029')
assert json.loads(collection.with_suffix('.json').read_text())['exit']==0
def nodes(path):return {s for s in path.read_text().splitlines() if s.startswith(('trading/tests/','backend/tests/','tests/rebuild/')) and '::' in s}
current=nodes(collection.with_suffix('.log'));original_nodes=nodes(Path('/workspace/van-native-receipt-fee-collection-r2-20261028.log'))
assert len(current)==5385 and current=={c['nodeid'] for c in calls} and len(original_nodes)==5334 and original_nodes<=current
preserved=functions=assertions=0;changed=[];original_files=0
def asserts(tree):return [ast.dump(n,include_attributes=False) for n in ast.walk(tree) if isinstance(n,ast.Assert)]
def signatures(tree):return collections.Counter((n.name,ast.dump(n.args,include_attributes=False),type(n).__name__) for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name.startswith('test_'))
with tarfile.open(fileobj=io.BytesIO(subprocess.check_output(['git','archive',base,'trading/tests','tests/rebuild'],cwd=root))) as tar:
 for member in tar:
  if not member.isfile() or not member.name.endswith('.py') or not Path(member.name).name.startswith('test_'):continue
  before=tar.extractfile(member).read();after=(root/member.name).read_bytes();a=ast.parse(before);b=ast.parse(after)
  assert asserts(a)==asserts(b),member.name
  assert signatures(a)==signatures(b),member.name
  original_files+=1;functions+=sum(signatures(a).values());assertions+=len(asserts(a))
  if before==after:preserved+=1
  else:changed.append(member.name)
assert original_files==310 and set(changed)=={'trading/tests/test_single_session_unknown_entry.py','trading/tests/test_mql_native_function_bodies.py'}
for label in ('workmap','owner','frontend','mutations','consolidation'):
 assert json.loads(Path('/workspace/van-mt5-native-cost-final-'+label+'-20261029.json').read_text())['exit']==0
protocol={}
for name in ('OpenApiCommonMessages.proto','OpenApiCommonModelMessages.proto','OpenApiMessages.proto','OpenApiModelMessages.proto','PROVENANCE.json'):
 f='trading/vati/execution/ctrader/proto/'+name;b=(root/f).read_bytes();assert b==subprocess.check_output(['git','show',base+':'+f],cwd=root);protocol[f]=hashlib.sha256(b).hexdigest()
raw=root/'docs/rebuild/rev118/ci/mt5_native_cost_20261029';raw.mkdir(parents=True,exist_ok=True)
def copy(source,dest):
 source=Path(source);dest=raw/dest;dest.parent.mkdir(parents=True,exist_ok=True);data=source.read_bytes()
 if dest.suffix=='.gz':dest.write_bytes(gzip.compress(data,mtime=0));assert gzip.decompress(dest.read_bytes())==data
 else:dest.write_bytes(data);assert dest.read_bytes()==data
for folder,label in ((run,'final-full'),(Path('/workspace/van-mt5-owner-cost-full-sql-r1-20261028'),'original-failed-full'),
 (Path('/workspace/van-mt5-charge-integration-r1-20261029'),'integration147'),
 (Path('/workspace/van-mt5-cost-availability-r2-20261029'),'availability36'),
 (Path('/workspace/van-mt5-entry-cost-recovery-before-20261029'),'entry-cost-before')):
 rec=json.loads((folder/'receipt.json').read_text());assert rec['completed'] and rec['cleaned'] and rec['owned_fixture_independently_absent']
 if label=='original-failed-full':assert rec['exit']==1
 for p in folder.iterdir():
  if p.is_file():copy(p,label+'/'+p.name+('.gz' if p.suffix=='.jsonl' else ''))
 copy(str(folder)+'.py',label+'/controller.py')
prefixes=('van-mt5-recorded-fee-absence-before-20261028','van-owner-cost-replay-before-20261028',
 'van-mt5-owner-cost-after-r1-20261028','van-mt5-owner-cost-consumers-r1-20261028',
 'van-mt5-owner-cost-consumers-r2-20261028','van-mt5-owner-cost-consumers-r3-20261028',
 'van-mt5-recorded-charge-producers-r1-20261029','van-mt5-recorded-charge-producers-r2-20261029',
 'van-mt5-recorded-charge-producers-r3-20261029','van-mt5-unprotected-cost-before-20261029',
 'van-mt5-charge-priority-r1-20261029','van-mt5-native-cost-final-collection-20261029',
 *('van-mt5-native-cost-final-'+label+'-20261029' for label in ('workmap','owner','frontend','mutations','consolidation')))
for prefix in prefixes:
 for suffix in ('.json','.log','.xml'):
  p=Path('/workspace')/(prefix+suffix)
  if p.exists():copy(p,p.name)
for name in ('test_van_mt5_recorded_fee_absence_20261028.py','test_van_owner_cost_replay_20261028.py',
 'van-mt5-positive-fixture-correction-20261029.json','van-mt5-owner-cost-android-inspection-20261028.json',
 'van-mt5-native-cost-primary-references-20261029.json','van-mt5-owner-cost-wip2-20261028.json',
 'van-mt5-owner-cost-wip3-20261029.json','van-mt5-owner-cost-wip5-20261029.json','van-mt5-native-cost-wip6-20261029.json'):
 copy('/workspace/'+name,name)
archive_meta=json.loads(Path('/workspace/van-mt5-owner-cost-wip2-20261028.json').read_text());archive=Path(archive_meta['archive'] if 'archive' in archive_meta else archive_meta['path'])
assert hashlib.sha256(archive.read_bytes()).hexdigest()==archive_meta['sha256']
with zipfile.ZipFile(archive) as z:
 for f,h in archive_meta['manifest']['files'].items():
  b=z.read(f);assert hashlib.sha256(b).hexdigest()==h
  p=raw/'original-failed-full/original-source'/f;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
proof={'passed':5385,'failure':0,'error':0,'skip':0,'storage_violations':0,'single_complete_collection':True,
 'collection_call_IDs_each_once':True,'all5334published_parent_cases_retained':True,'new_cases':51,
 'source_input_sha256':pins,'source_pins':len(pins),'original_protocol_reference_sha256':protocol,
 'inherited_test_files':original_files,'inherited_test_files_byte_identical':preserved,
 'fixture_extensions_with_all_original_assertions_and_test_signatures_unchanged':changed,
 'original_test_functions_retained':functions,'original_assertions_retained':assertions,
 'owned_postgres_independently_absent':True,'native_or_formal_acceptance':False,
 'changed_EA_requires_fresh_actual_MetaEditor_compile':'PENDING_EXACT_COMMIT_HOSTED_EVIDENCE'}
(raw/'source-preservation-and-discovery.json').write_text(json.dumps(proof,indent=2)+'\n')
now=datetime.datetime.now(datetime.UTC).isoformat();rel='receipts/MT5_NATIVE_COST_SOURCE_20261029.json'
summary=(f'Actual MT5 Windows-worker and EA producers read original entry-deal commission/fee components, bind native account/order/deal/position/symbol/side/volume and preserve explicit zero, signed components or unavailability. Optional cost reads cannot delay unprotected-fill recovery. Core parsing is exact under caller decimal traps and does not treat absent/mismatched data as0. Receipt-bound unavailable-cost facts are durable/idempotent; native fills, thesis, protection and real session restart survive unavailable costs without numericTCA. Later zero-effect receipts cannot replace original entry-cost knowledge. Owner replay restores the original cost ratio/model, including legacy records, without duplicateTCA/learning or overwriting conflicts. Final selected source suite:{5385}passed/0fail/error/skip/audit, one independently identical collection/call set eachonce, all{len(pins)}input hashes matched, ownedPostgreSQL absent. All5334published-parent cases remain;{preserved}/{original_files}inherited test files are byte-identical and every original assertion/test signature remains unchanged across two documented fixture extensions. Five original full-suite failures and all intermediate failures remain retained. This partial BE009/010/012 source packet does not complete future fees, economic finality, parent budgets, reservations or formal/native/production/device acceptance.')
next_action='Genuinehook commit with existing autonomous-candidate and native-worker-source authorization IDs; wait for terminal required-baseline committed verification before normalpush. Independently read exact remote head/CI, including fresh actual MetaEditor compilation for changedEA. Then continue complete fee/closing/fill/price/multi-asset obligations and native/economic reconciliation, immutable parent/child lifetime budgets, all-origin shared reservations/outbox/current qualified policy/cohort and every original backend requirement; gated Android with provisioned profile on Vantradingcore, real signing and Artemis/S24.'
receipt={'schema':'van.rev118.mt5-native-cost-source/1','observed_at_utc':now,'source_parent':base,
 'state':'PARTIAL_CANDIDATE_SOURCE_TESTED_NOT_COMPLETE_FEES_OR_NATIVE_ACCEPTANCE','implementation':summary,'checks':proof,
 'authority':['auth-20261022-owner-autonomous-candidate-build','auth-20261023-owner-native-worker-source'],
 'raw':'ci/mt5_native_cost_20261029','formal_acceptance':'NOT_ISSUED','execution_authority':False,'settlement_qualified':False,
 'retained_failures':['Original full5349attempt:5344passed/5failed because absent MT5fees became noTCA and existing recovery assumed numericTCA. Never relabeledgreen.',
 'Actual entry-cost recovery2before-cases failed: latecancel/rejectfee0 replaced original unknownentryfees. Actual unprotectedcost-before probe failed. Both source paths corrected.',
 'Intermediate newfixtures/APIerrors, inherited-model replay failures, duplicateC++declaration and preciseDecimalvolume consumption failures are retained with original logs. Later overlapping focused checks are not added to5385.'],
 'remaining':['Complete native fee schedules/sign/provider qualification, future/deferred/day-month charges, financing/minimum/charge-count/FX/fee-asset bounds and closing/resting-fill/late-cost observation/reconciliation remain open.',
 'Full raw-source retention beyond typed receipts/original durable pull results, fee allocation/correction/bust/economic finality and nonduplicated release remain original obligations.',
 'Immutable lifetime parent/child budgets/full child methods, family/correlation, current qualified policy/cohort and all-origin transactional reservations/outbox/effect consumers remain open.',
 'Every original market/feed/depth/news/calendar/entitlement/chart/voice,38forecast/research,assistant/crypto,security/operations and gated Android requirement remains.'],
 'next':next_action}
(root/'docs/rebuild/rev118'/rel).write_text(json.dumps(receipt,indent=2)+'\n')
for name in ('EXECUTION_LEDGER.json','CANDIDATE_SOURCE_PROGRESS.json'):
 p=root/'docs/rebuild/rev118'/name;d=json.loads(p.read_text());d['updated_at_utc']=now
 if name=='EXECUTION_LEDGER.json':
  d['observations'].append(summary);d['current_action']=next_action
  for uid in ('BE-009','BE-010','BE-012'):
   if rel not in d['units'][uid]['evidence']:d['units'][uid]['evidence'].append(rel)
 else:
  for uid in ('BE-009','BE-010','BE-012'):d['units'][uid]['milestones'].append({'description':summary,'evidence':rel})
 p.write_text(json.dumps(d,indent=2)+'\n')
p=root/'docs/rebuild/rev118/CONTINUATION_20261022.md';p.write_text(p.read_text()+'\n\n## Recorded MT5 entry costs and durable cost availability —29October\n\n'+summary+'\n\n[Source receipt]('+rel+'). '+next_action+'\n')
doc='# Recorded MT5 entry costs and durable unavailable-cost recovery\n\n'+summary+'\n\n[Source receipt](../'+rel+') retains exact input/call/discovery evidence, originalfailedfullrun and native SDK/EA function-body/realSQL checks. Function-body C++ controls do not prove actual MetaEditor compilation or broker execution. The changedEA requires fresh exact-source compiler evidence; no native/account/device qualification is issued.\n\nNative producer reads can fail or mismatch without erasing the fill or stop. Explicit measured components use the declared native signed cash-component convention. Neither a zero nor an immediate recorded cost establishes complete future charges: daily/monthly commission, financing, later fills/charges, fee assets/conversion and settlement remain separate. No native fee schedule or sign qualification is self-issued. Protective recovery takes precedence over optional cost history reads.\n\nCost-unavailable facts bind the original sealed receipt and original account command. Unrelated/unsupported claims cannot complete recovery or poison later repair. A later cancellation/rejection cannot replace the fill\u2019s original cost knowledge. Original measured owner cost replay uses the original stored model; current setting changes and conflicting records do not rewrite history or duplicate learning.\n\nThe positive native crash fixture now emits explicit measured-zero observations and valid nativeorder IDs; its90original assertions remain unchanged. The EA fixture extracts the added actual source helper; every original assertion and test signature across310inherited test files remains intact. Two fixture files changed; no passing test was removed to hide a failure.\n\nComplete all original financial/manual/payment/handover,market,forecast/learning/crypto,assistant/voice and operations obligations. Android follows BG-001/canonical gates, uses its provisioned production profile on Vantradingcore and requires real signing/Artemis/S24. Profitability is evaluated with evidence, never guaranteed.\n'
(root/'docs/rebuild/rev118/backend/BE-010_012_MT5_NATIVE_COST.md').write_text(doc)
p=root/'docs/rebuild/rev118/BUILD_EXECUTION_PLAN.md';text=p.read_text();a=text.index('## Current concrete gap and next result');b=text.index('## Commands and evidence economy',a)
p.write_text(text[:a]+'## Current concrete gap and next result\n\n'+summary+'\n\n[Current source receipt]('+rel+'). '+next_action+'\n\nPreserve the complete original work fronts above: a missing measurement or native qualification remains an explicit gate, and no read-only replacement closes an effectful feature. All82backend units/12verification packets retain their full contracts, with0formalacceptance. The trusted-main/privateDDSkey prerequisites remain enforced; no overallCI/native/S24 pass is inferred.\n\n'+text[b:])
copy(__file__,'evidence-builder.py')
print(json.dumps({'passed':5385,'source_pins':len(pins),'inherited_files':original_files,'byte_identical':preserved,'functions':functions,'assertions':assertions,'raw_files':sum(p.is_file() for p in raw.rglob('*')),'receipt':rel}))
