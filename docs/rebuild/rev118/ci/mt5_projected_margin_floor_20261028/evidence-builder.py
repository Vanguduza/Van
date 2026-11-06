from pathlib import Path
import json,hashlib,subprocess,shutil,collections,datetime,ast,xml.etree.ElementTree as E
root=Path('/workspace/van-review-2026-10-18/publish');base='d53eea63539d5829ff0ac4f5aa7b55155a3c7491'
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()==base
run=Path('/workspace/van-mt5-projected-margin-floor-sql-r2-20261028');r=json.loads((run/'receipt.json').read_text())
outer=json.loads(Path('/workspace/van-mt5-projected-margin-floor-sql-r2-process-20261028.json').read_text())
assert r['exit']==outer['exit']==0 and r['cleaned'] and r['owned_fixture_independently_absent']
assert not json.loads((run/'storage-audit.json').read_text())['forbidden_events']
assert all(hashlib.sha256((root/p).read_bytes()).hexdigest()==h for p,h in r['source_sha256'].items())
assert all(hashlib.sha256((root/p).read_bytes()).hexdigest()==h for p,h in r['reference_fixtures_sha256'].items())
cases=E.parse(run/'full-trading.xml').findall('.//testcase')
assert cases and all(all(t.find(k) is None for k in ['failure','error','skipped']) for t in cases)
calls=[json.loads(l) for l in (run/'test-events.jsonl').read_text().splitlines() if json.loads(l)['phase']=='call']
assert len(calls)==len(cases) and all(c['outcome']=='passed' for c in calls)
assert all(n==1 for n in collections.Counter(c['nodeid'] for c in calls).values())
raw=root/'docs/rebuild/rev118/ci/mt5_projected_margin_floor_20261028';assert not raw.exists();raw.mkdir(parents=True)
def copy(src,rel):
 src=Path(src);dest=raw/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest);assert src.read_bytes()==dest.read_bytes()
for tag in ['r1','r2']:
 folder=Path('/workspace/van-mt5-projected-margin-floor-sql-'+tag+'-20261028')
 for p in folder.iterdir():
  if p.is_file():copy(p,'sql_'+tag+'/'+p.name)
 copy('/workspace/van-mt5-projected-margin-floor-sql-'+tag+'-20261028.py','sql_'+tag+'/controller.py')
 copy('/workspace/van-mt5-projected-margin-floor-sql-'+tag+'-process-20261028.json','sql_'+tag+'/outer-process.json')
copy('/workspace/van-mt5-projected-margin-floor-sql-r1-owned-interrupt-20261028.json','sql_r1/verified-owned-interrupt.json')
for stem in ['before','r1','r2','r3','r4','r5','r6','reported-fraction-before','reported-fraction-after']:
 for suffix in ['.log','.xml','.json','-audit.json']:
  p=Path('/workspace/van-mt5-projected-margin-floor-'+stem+'-20261028'+suffix)
  if p.exists():copy(p,'focused/'+p.name)
copy('/workspace/test_van_mt5_reported_fraction_20261028.py','focused/independent-reported-fraction-boundary.py')
for n in ['scope-check','owner-registry','frontend-registry','mutation-consistency','consolidation']:
 p=Path('/workspace/van-mt5-projected-margin-floor-'+n+'-20261028.json');assert json.loads(p.read_text())['exit']==0
 for ext in ['.json','.log']:copy(p.with_suffix(ext),'guards/'+p.with_suffix(ext).name)
for n in ['wip1','wip2','wip3']:
 for ext in ['.zip','.json']:copy('/workspace/van-mt5-projected-margin-floor-'+n+'-20261028'+ext,'source_recovery/'+n+ext)
for name,rel in [('van-mt5-pending-receipt-publication-20261028.json','publication.json'),('van-d53eea63-published-pr-ci-readback-20261028.json','pr-ci-readback.json'),('van-d53eea63-current-ci-evidence-20261028.json','current-ci-evidence.json')]:
 copy('/workspace/'+name,'published_parent/'+rel)
parent_log=Path('/workspace/van-d53eea63-postgres-hosted-original-20261028.log')
assert '5044 passed, 1 skipped' in parent_log.read_text() and '26 passed in' in parent_log.read_text() and '117 passed' in parent_log.read_text()
copy(parent_log,'published_parent/original-postgres-job.log')
if Path('/workspace/van-d53eea63-terminal-ci-evidence-20261028.json').exists():copy('/workspace/van-d53eea63-terminal-ci-evidence-20261028.json','published_parent/terminal-ci-evidence.json')
preserved=0
for folder in ['trading/tests','tests/rebuild']:
 for p in (root/folder).rglob('test_*.py'):
  rel=str(p.relative_to(root));before=subprocess.run(['git','show',base+':'+rel],cwd=root,capture_output=True)
  if before.returncode:continue
  old=ast.parse(before.stdout);new=ast.parse(p.read_bytes())
  a={n.name:ast.dump(n) for n in ast.walk(old) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name.startswith('test_')}
  b={n.name:ast.dump(n) for n in ast.walk(new) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name.startswith('test_')}
  assert all(b.get(k)==v for k,v in a.items()),rel
  preserved+=len(a)
copy('/workspace/van-mt5-projected-margin-floor-test-preservation-20261028.json','test-preservation.json')
assert json.loads((raw/'test-preservation.json').read_text())['original_test_functions_AST_preserved']==preserved
paths=subprocess.check_output(['git','diff','--name-only'],cwd=root,text=True).splitlines()+subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=root,text=True).splitlines()
source=sorted(p for p in paths if p.startswith(('trading/','deploy/van-trading-core/','tests/rebuild/')))
hashes={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in source}
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
summary=(f'Both native MT5 entry paths now preserve the existing RiskAuthority200% minimum after adding the original proposed isolated margin to native committed margin. Original cash excludes credit; money bounds round conservatively, and equality refuses. The lower original broker-reported level also remains binding. SDK uses exact Fraction; EA retains full original decimal mantissas/exponents and integer-string products, including sub-minor used margin and strictly above-floor reported fractions. Before/after/final facts cannot renew an originally insufficient margin budget. Known floor breach, insufficient free cash and unavailable facts remain distinct. Healthy/zero-requirement entries and protective tighten/close retain their existing paths. Neither path sizes or grants execution. Final full source qualification:{len(cases)}passed0skip/fail/error/audit,actualinner/outerexit0,everycallonce,all{len(r["source_sha256"])}inputhashesmatchplus2legacyfixtures,ownedPostgreSQLindependentlyabsent. {preserved} original trading/rebuild test functions retain identical AST. New actual EA MetaEditor compilation PENDING exact-source hosted job. Shared reservations, fee/fill contingencies, native working-order and economic finality remain open.0formal/native/production/S24acceptancesissued.')
rel='receipts/MT5_PROJECTED_MARGIN_FLOOR_SOURCE_20261028.json'
receipt={'schema':'van.rev118.mt5-projected-margin-floor-source/1','source_parent':base,'observed_at_utc':now,'source_files_sha256':hashes,'implementation':summary,
 'source_result':{'actual_inner_exit':0,'actual_outer_exit':0,'passed':len(cases),'skipped':0,'failures':0,'errors':0,'audit_violations':0,'unique_calls_once':len(calls),'pinned_inputs_matched':len(r['source_sha256']),'additional_legacy_fixtures_matched':len(r['reference_fixtures_sha256']),'original_test_functions_AST_preserved':preserved,'owned_postgres_independently_absent':True,'raw':'ci/mt5_projected_margin_floor_20261028/sql_r2'},
 'source_authorizations':['auth-20261022-owner-autonomous-candidate-build','auth-20261023-owner-native-worker-source'],
 'retained_failures':['Baseline actualexit1:7 simulated unsafe native sends,2 healthy controls passed. Both source transports admitted entry at/below the existing projected floor. No real broker effect.','Focusedr1 actualexit1:180passed1failed. EA healthy399.99 fixture crossed to original17digit text above399.99 and rounded required margin up to400 at declared2decimal units. Exactly representable399.5 restored the healthy control;399.99 remains a held boundary. No production rounding loosened.','Independent reported-fraction boundary actualexit1:1EAhelperpassed/1SDKfailed. SDK unnecessarily quantized percentage-derived capacity a second time; the exact ratio now remains Fraction, while original cash/money rounding stays conservative. Final independent2-case comparison passes.','First broadSQLr1 deliberately interrupted after reproducing the SDK positive-boundary defect, before modifying source. Only the exact owned audit process was signalled after PID/parentage/cmdline verification. Actual inner/outerexit2, partial evidence retained, ownedPostgreSQL independently absent; no full-run PASS.'],
 'fixture_preservation':'Original test functions/assertions remain. EntryCashSdk now supplies its explicit original reported margin level consistently with simulated equity/used facts; exact EA dependency extraction and C++ API model expand for original helpers. These remain declared source fixtures.',
 'native_EA_compilation':'PENDING_EXACT_MODIFIED_SOURCE_HOSTED_JOB','formal_acceptances_issued':0,
 'published_parent_hosted_logs':{'head':base,'run':40700452416,'job':122858524607,'trading_passed':5044,'declared_private_DDS_skips':1,'postgres_passed':26,'voice_passed':117,'original_JUnit_archive_verified':False,'supporting_workflows_succeeded':4,'mandatory_prerequisites_failed':['trusted-main ledger checker absent','DDS read deploy key unprovisioned']},
 'limitations':['The200% value is the existing RiskAuthority starting floor, not a new owner decision, measured optimum or profitability guarantee. Source guards bind both native constants to that owner; stricter current policy retains its existing owner.','These are projected original isolated-margin refusal fences. Native account reads are bracketed, not atomic. Actual fill prices, fees, changing portfolio offsets and post-fill economic margin require their complete qualification.','Shared all-origin transactional cash/margin/stop-risk reservations, qualified FX/contracts, current-policy arbitration, native working-order/partial-fill/cancel and funding/payment settlement remain required. No pending order acknowledgment releases funds.','EA helpers/entry bodies execute in an explicit C++ API model, not MetaTrader runtime. Modified EA native compilation is pending; no connected terminal/account/provider/device or production acceptance.','Every remaining backend/forecast/learning/crypto/assistant/operations and Android requirement remains required. Profitability needs evidence, never a guarantee.'],
 'next':'Genuine hooks, mandatory committed verification against4fd466de, normal push and independent exact remote readback after current parent public jobs finish. Inspect exact new hosted source and official MetaEditor evidence. Continue shared all-origin reservations/current-policy/native reconciliation and full backend-to-Android programme.'}
(root/'docs/rebuild/rev118'/rel).write_text(json.dumps(receipt,indent=2)+'\n')
for name in ['EXECUTION_LEDGER.json','CANDIDATE_SOURCE_PROGRESS.json']:
 p=root/'docs/rebuild/rev118'/name;v=json.loads(p.read_text());v['updated_at_utc']=now
 if name=='EXECUTION_LEDGER.json':
  v['observations'].append(summary);v['current_action']=receipt['next']
  for uid in ['BE-003','BE-009','BE-010']:v['units'][uid]['evidence'].append(rel)
 else:
  for uid in ['BE-003','BE-009','BE-010']:v['units'][uid]['milestones'].append({'description':summary,'evidence':rel})
 p.write_text(json.dumps(v,indent=2)+'\n')
(root/'docs/rebuild/rev118/backend/BE-009_010_MT5_PROJECTED_MARGIN_FLOOR.md').write_text('# Existing risk floor at the final native entry boundary\n\nCandidate source only; no full-unit or native/account/production/device acceptance.\n\n'+summary+'\n\nRead [the exact source receipt](../'+rel+') and retained failures/partial run. Full source tests execute SQLite/PostgreSQL/HTTP and original SDK/EA function bodies through explicit native API models. The current modified EA still needs official MetaEditor compilation. No source fixture establishes an owner-connected broker or economic result.\n\nThe unchanged risk owner sets200% as an inherited starting floor, not an economic optimum. Native fences deny at equality or below after including the proposed isolated requirement. Cash/credit, original lower reported level and before/after/final scope remain bound. Reported percentages are exact ratios, not new spendable money. Current original healthy/zero and protective paths are preserved; source constants cannot silently drift from RiskAuthority.\n\nComplete shared all-origin transactional cash/margin/stop-risk reservations, fee/fill contingencies, actual post-fill portfolio margin, current-policy arbitration, native working-order/partial-fill/cancel and economic finality. Retain all payment/manual/handover, feeds/depth/entitlements, forecasts/learning/crypto, assistant and operations obligations. Android uses its provisioned production profile on Van trading core; real signing and Artemis/Samsung S24 acceptance remain separate. No frontend redesign before BG-001.\n')
p=root/'docs/rebuild/rev118/CONTINUATION_20261022.md';p.write_text(p.read_text()+'\n\n## Existing projected margin floor —28October\n\n'+summary+'\n\n[Source receipt]('+rel+'). '+receipt['next']+'\n')
p=root/'docs/rebuild/rev118/BUILD_EXECUTION_PLAN.md';text=p.read_text();start=text.index('## Current concrete gap and next result');end=text.index('## Commands and evidence economy',start)
latest='Published parentd53eea63 completed genuine hooks, committed GREEN192, normal push and exact remote readback. Its5272 source checks pass;1259 input pins plus2 legacy fixtures match committed Git objects. It retains pending ACCEPTED IDs and original completion/replay without fictitious fills. Exact parent source CI remains separately observed; no admission is inferred.\n\n'+summary+'\n\n[Source receipt]('+rel+'). '+receipt['next']+'\n\nComplete shared all-origin cash/margin/stop-risk reservations, actual post-fill margin/fee/fill contingencies, current-policy arbitration and full working-order/partial-fill/cancel/economic reconciliation. Complete discovery/aliases/subscriptions/bars/gaps/depth/entitlements and qualified native valuation/migration; payment/manual/handover workflows; every forecast, learning, crypto, assistant, security, operations and Android obligation. Profitability needs evidence. Provision Android on Van trading core without owner-entered backend addresses; signing and actual Artemis/Samsung S24 remain required. Preserve BG-001 and original acceptance dependencies.\n\n'
p.write_text(text[:start]+'## Current concrete gap and next result\n\n'+latest+text[end:])
copy(__file__,'evidence-builder.py')
print(json.dumps({'passed':len(cases),'pinned_inputs':len(r['source_sha256']),'original_test_functions_AST_preserved':preserved,'raw_files':sum(p.is_file() for p in raw.rglob('*')),'receipt':rel}))
