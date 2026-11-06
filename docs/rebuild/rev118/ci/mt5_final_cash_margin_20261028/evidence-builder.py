from pathlib import Path
import json,hashlib,subprocess,shutil,collections,datetime,xml.etree.ElementTree as E
root=Path('/workspace/van-review-2026-10-18/publish');base=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
assert base=='bf41e16b0213431eeaeb33da96676cfb7dc47477'
run=Path('/workspace/van-mt5-final-cash-margin-sql-r2-20261028');r=json.loads((run/'receipt.json').read_text())
outer=json.loads(Path('/workspace/van-mt5-final-cash-margin-sql-r2-process-20261028.json').read_text())
assert r['exit']==outer['exit']==0 and r['cleaned'] and r['owned_fixture_independently_absent']
assert not json.loads((run/'storage-audit.json').read_text())['forbidden_events']
assert all(hashlib.sha256((root/p).read_bytes()).hexdigest()==h for p,h in r['source_sha256'].items())
cases=E.parse(run/'full-trading.xml').findall('.//testcase');assert cases and all(all(c.find(k) is None for k in ['failure','error','skipped']) for c in cases)
calls=[json.loads(l) for l in (run/'test-events.jsonl').read_text().splitlines() if json.loads(l)['phase']=='call']
assert len(calls)==len(cases) and all(c['outcome']=='passed' for c in calls) and all(n==1 for n in collections.Counter(c['nodeid'] for c in calls).values())
raw=root/'docs/rebuild/rev118/ci/mt5_final_cash_margin_20261028';assert not raw.exists();raw.mkdir(parents=True)
def copy(src,rel):
 src=Path(src);dest=raw/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest);assert src.read_bytes()==dest.read_bytes()
for tag in ['r1','r2']:
 folder=Path('/workspace/van-mt5-final-cash-margin-sql-'+tag+'-20261028')
 for p in folder.iterdir():
  if p.is_file():copy(p,'sql_'+tag+'/'+p.name)
 copy('/workspace/van-mt5-final-cash-margin-sql-'+tag+'-20261028.py','sql_'+tag+'/controller.py')
 copy('/workspace/van-mt5-final-cash-margin-sql-'+tag+'-process-20261028.json','sql_'+tag+'/outer-process.json')
stems=['before','sdk-r1','original-r1','original-r2','sdk-r2','ea-units-r1','both-source-r1','both-source-r2','actual-ea-bodies-r1','actual-ea-bodies-r2']
for stem in stems:
 for suffix in ['.log','.xml','.json','-audit.json']:
  p=Path('/workspace/van-mt5-final-cash-margin-'+stem+'-20261028'+suffix)
  if p.exists():copy(p,'focused/'+p.name)
for suffix in ['.py','.json']:copy('/workspace/van-mt5-final-cash-margin-ea-before-20261028'+suffix,'original_ea_entry_body/verifier'+suffix)
for suffix in ['.py','.json']:copy('/workspace/van-mt5-final-cash-margin-test-preservation-20261028'+suffix,'test_preservation/verifier'+suffix)
for stem,tag in [('ea-before-process','process_r1'),('ea-before-r2-process','process_r2')]:
 for suffix in ['.log','.json']:copy('/workspace/van-mt5-final-cash-margin-'+stem+'-20261028'+suffix,'original_ea_entry_body/'+tag+suffix)
for name in ['owner-registry','frontend-registry','scope-check','mutation-consistency','consolidation']:
 p=Path('/workspace/van-mt5-final-cash-margin-'+name+'-20261028.json');assert json.loads(p.read_text())['exit']==0
 for ext in ['.json','.log']:copy(p.with_suffix(ext),'guards/'+p.with_suffix(ext).name)
for n in ['wip1','wip2','wip3']:
 for ext in ['.zip','.json']:copy('/workspace/van-mt5-final-cash-margin-'+n+'-20261028'+ext,'source_recovery/'+n+ext)
copy('/workspace/van-native-instrument-catalog-publication-20261028.json','published_parent/publication.json')
copy('/workspace/van-native-instrument-catalog-committed-inputs-20261028.json','published_parent/committed-inputs.json')
parent=Path('/workspace/van-bf41e16b-selected-hosted-20261028')
if parent.exists():
 for p in parent.rglob('*'):
  if p.is_file():copy(p,'published_parent_selected_hosted/'+str(p.relative_to(parent)))
copy('/workspace/van-bf41e16b-main-ci-20261028/terminal-evidence.json','published_parent/terminal-main-ci.json')
paths=subprocess.check_output(['git','diff','--name-only'],cwd=root,text=True).splitlines()+subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=root,text=True).splitlines()
source=sorted(p for p in paths if p.startswith(('trading/','deploy/van-trading-core/','tests/rebuild/')))
hashes={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in source};now=datetime.datetime.now(datetime.timezone.utc).isoformat()
summary=(f'Final MT5 SDK and EA entry paths now calculate original native isolated margin and compare against cash-backed capacity before native handoff. Credit cannot fund entry risk; available amounts round down and requirements up at original account precision. SDK uses exact Fraction over original text; EA uses 17-digit original text and integer-string arithmetic. Scope and cash are rechecked around calculation and at the final guard; original identity/permission/deadline checks remain. Known insufficient and unavailable facts remain distinct; explicit zero native requirement works with positive cash. Market/limit/native side and protective tighten/close behavior are preserved. Baseline actual signed SDK fixture reached unsafe native sends in2cases; exact original published EA entry body also reached2unsafe simulated sends. These are explicit source fixtures, not connected brokers. Final full source qualification:{len(cases)}passed0skip/fail/error/audit,actualinner/outerexit0,everycallonce,all{len(r["source_sha256"])}inputhashesmatchincludingactualCPPfixture/SDK/EA/README,ownedPostgreSQLindependentlyabsent. Original failed attempts remain retained. Actual new EA MetaEditor compilation PENDING exact-source hosted job. Shared reservations/post-entry margin floors/fee-and-fill contingencies/full valuation and financial qualification remain open.0formal/native/production/S24acceptancesissued.')
rel='receipts/MT5_FINAL_CASH_MARGIN_SOURCE_20261028.json'
receipt={'schema':'van.rev118.mt5-final-cash-margin-source/1','source_parent':base,'observed_at_utc':now,'source_files_sha256':hashes,'implementation':summary,
 'source_result':{'actual_inner_exit':0,'actual_outer_exit':0,'passed':len(cases),'skipped':0,'failures':0,'errors':0,'audit_violations':0,'unique_calls_once':len(calls),'pinned_inputs_matched':len(r['source_sha256']),'owned_postgres_independently_absent':True,'raw':'ci/mt5_final_cash_margin_20261028/sql_r2'},
 'source_authorizations':['auth-20261022-owner-autonomous-candidate-build','auth-20261023-owner-native-worker-source'],
 'retained_failures':['Signed SDK baseline actualexit1:2unsafe sends/1healthycontrolpass.','Original SDK regressionr1:52passed4failed; legacy native fixture lacked explicit cash/calculator facts, and a mutex dummy terminal bypassed actual native preparation. Explicit facts and real Terminal source path restored while original assertions remained.','First fullSQLr1 actualexit1:5139passed1failed60errors0skip. Existing actual-EA extractor omitted new cash helper dependencies; old final-clock fixture counted the former third read. Extractor now includes exact helper bodies/struct and original API-model facts. Clock delay now targets actual final guard read. All original assertions and financial source code retained.','Original EA entry-body verifier first completed behavioral assertions but exited1 while serializing Decimal artifact values. Exact Decimal text encoding repaired the artifact path; rerun actualexit0. Original failed process/log retained.'],
 'source_math_qualification':'Exact EA function bodies executed through the existing controlled C++ terminal model and independent Fraction oracle. This is not MetaTrader runtime; changed EA native compilation remains separately pending.',
 'native_EA_compilation':'PENDING_EXACT_MODIFIED_SOURCE_HOSTED_JOB','formal_acceptances_issued':0,
 'limitations':['A final native cash check is not a shared all-origin transactional reservation, post-entry margin floor, fee/fill-price contingency, qualified FX/contract migration or economic finality. All remain required.','Native doubles enter as original declared-format text. Down/up rounding supplies conservative bounds, not an invented exact broker debit or timestamped conversion. Source bracket checks do not claim atomic native account snapshots.','Linux SDK/EA responses and C++ API services are explicit fixtures. No connected account/provider/financial/native handset acceptance is claimed. Python storage audit is not an OS sandbox.','All remaining funding/payment/manual/handover, feeds/forecasts/learning/crypto/assistant/security/operations and Android functionality remains required. Profitability is evaluated with evidence, never guaranteed.'],
 'next':'Genuine hooks, required committed-baseline verify, normal exact publication, fresh changed-EA native compilation and exact-head source CI. Continue complete shared financial reservations/current policy/reconciliation and the full backend-to-Android programme.'}
(root/'docs/rebuild/rev118'/rel).write_text(json.dumps(receipt,indent=2)+'\n')
for name in ['EXECUTION_LEDGER.json','CANDIDATE_SOURCE_PROGRESS.json']:
 p=root/'docs/rebuild/rev118'/name;v=json.loads(p.read_text());v['updated_at_utc']=now
 if name=='EXECUTION_LEDGER.json':
  v['observations'].append(summary);v['current_action']=receipt['next']
  for uid in ['BE-003','BE-009','BE-010']:v['units'][uid]['evidence'].append(rel)
 else:
  for uid in ['BE-003','BE-009','BE-010']:v['units'][uid]['milestones'].append({'description':summary,'evidence':rel})
 p.write_text(json.dumps(v,indent=2)+'\n')
(root/'docs/rebuild/rev118/backend/BE-009_010_MT5_FINAL_CASH_MARGIN.md').write_text('# Final native MT5 cash-backed margin check\n\nCandidate source only; no full financial-unit or native/production acceptance.\n\n'+summary+'\n\nRead the [exact source receipt](../'+rel+') and retained failed/source checks. Original native reply reasons distinguish insufficient capital from unavailable facts. No margin read grants execution, and risk reduction retains its existing authority. The exact EA numerical and entry bodies execute in a declared C++ API model; official MetaEditor compilation and actual native/account qualification remain separate.\n\nComplete shared all-origin reservations, fee/fill-price contingencies, post-entry margin floors, qualified FX/contract migration, active-policy arbitration and native working-order/economic finality; preserve every other canonical backend, forecast, assistant, operations and Android function. No frontend redesign before BG-001; production-profile provisioning on Van trading core and actual Artemis/Samsung S24 acceptance remain required.\n')
copy(__file__,'evidence-builder.py')
print(json.dumps({'source_files':len(source),'raw_files':sum(p.is_file() for p in raw.rglob('*')),'passed':len(cases),'pinned_inputs':len(r['source_sha256']),'receipt':rel}))
