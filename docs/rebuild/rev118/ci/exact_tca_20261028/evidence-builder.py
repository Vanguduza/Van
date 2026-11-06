from pathlib import Path
import ast,datetime,hashlib,io,json,shutil,subprocess,tarfile,xml.etree.ElementTree as ET

root=Path('/workspace/van-review-2026-10-18/publish');base='b0317e3dd3f01748abe6cf92504c6d965e0956bb'
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()==base
run=Path('/workspace/van-exact-tca-full-sql-r1-20261028');r=json.loads((run/'receipt.json').read_text())
assert r['exit']==0 and r['completed'] and r['cleaned'] and r['owned_fixture_independently_absent']
pins=r['source_sha256']|r.get('reference_fixtures_sha256',{})
assert all(hashlib.sha256((root/f).read_bytes()).hexdigest()==h for f,h in pins.items())
assert not json.loads((run/'storage-audit.json').read_text())['forbidden_events']
cases=ET.parse(run/'full-trading.xml').findall('.//testcase');count=len(cases)
assert count>5000 and all(all(c.find(k)is None for k in ('failure','error','skipped')) for c in cases)
calls=[json.loads(s) for s in (run/'test-events.jsonl').read_text().splitlines() if json.loads(s)['phase']=='call']
assert len(calls)==len({c['nodeid'] for c in calls})==count and all(c['outcome']=='passed' for c in calls)
collection=Path('/workspace/van-exact-tca-collection-20261028')
assert json.loads(collection.with_suffix('.json').read_text())['exit']==0
nodes=[s for s in collection.with_suffix('.log').read_text().splitlines() if s.startswith(('trading/tests/','backend/tests/','tests/rebuild/')) and '::' in s]
assert len(nodes)==len(set(nodes))==count and set(nodes)=={c['nodeid'] for c in calls}
files=functions=0
with tarfile.open(fileobj=io.BytesIO(subprocess.check_output(['git','archive',base,'trading/tests','tests/rebuild'],cwd=root))) as tar:
 for m in tar:
  if not m.isfile() or not m.name.endswith('.py') or not Path(m.name).name.startswith('test_'):continue
  old=tar.extractfile(m).read();assert old==(root/m.name).read_bytes(),m.name;files+=1
  functions+=sum(isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name.startswith('test_') for n in ast.walk(ast.parse(old)))
for name in ('workmap','owner','frontend','mutations','consolidation'):
 assert json.loads(Path('/workspace/van-exact-tca-'+name+'-20261028.json').read_text())['exit']==0
raw=root/'docs/rebuild/rev118/ci/exact_tca_20261028';raw.mkdir(parents=True,exist_ok=True)
def copy(source,dest):
 source=Path(source);dest=raw/dest;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest);assert source.read_bytes()==dest.read_bytes()
for p in Path('/workspace').iterdir():
 if not p.name.startswith('van-exact-tca-') or 'wip' in p.name or p==Path(__file__):continue
 if p.is_dir():
  for c in p.iterdir():
   if c.is_file():copy(c,'runs/'+p.name+'/'+c.name)
 elif p.suffix in ('.json','.log','.xml','.py'):copy(p,'runs/'+p.name)
for ext in ('.json','.zip'):copy('/workspace/van-exact-tca-wip1-20261028'+ext,'recovery/wip1'+ext)
for name in ('van-b0317e3d-ci-jobs-observation-20261028.json','van-b0317e3d-ci-workflows-observation-20261028.json',
 'van-b0317e3d-job-123091550075-original-20261028.log','van-b0317e3d-job-123091550579-original-20261028.log',
 'van-b0317e3d-job-123091550169-original-20261028.log','van-b0317e3d-postgres-original-20261028.zip',
 'van-b0317e3d-postgres-archive-readback-20261028.json'):
 copy('/workspace/'+name,'published-parent/'+name)
proof={'source_parent':base,'passed':count,'failed':0,'errors':0,'skipped':0,'audit_violations':0,
 'inner_exit':0,'every_current_discovered_case_executed_once':True,'source_and_fixture_pins':pins,
 'owned_postgres_independently_absent':True,'original_test_files_byte_identical':files,
 'original_test_functions_AST_preserved':functions,'native_or_production_acceptance':False}
(raw/'source-preservation-and-discovery.json').write_text(json.dumps(proof,indent=2)+'\n')
summary=(f'The existing receipt-to-TCA-to-durable-learning path now measures signed execution costs with exact rational arithmetic independently of caller Decimal precision, rounding, traps and exponent settings. Delay, submission and slippage plus recorded nonembedded charges equal direct signed fill-versus-reference cost; spread remains a separate embedded-cost diagnostic. Finite monetary values materialize exactly. Recurring ratios have original exact numerator/denominator and an explicit deterministic28digit display. New arithmetic claims are independently checked before broker/strategy-health or nested experience-artifact evidence is cached, including cold replay. Legacy numeric spelling and absence of the additive witness do not rewrite or alone invalidate original historical rows; changed economics still conflict. The receipt fee input does not attest complete native fees, financing, future obligations or settlement. Final{count}actual trading/SQLite/PostgreSQL/HTTP consumer cases passed,0fail/error/skip/audit; independent collection and call IDs match exactly once, all{len(pins)}input hashes match and ownedPostgreSQL is independently absent. All{files}inherited test files/{functions}test functions remain byte-identical. No whole-unit/native/provider/production/S24 acceptance or dispatch authority is issued.')
rel='receipts/EXACT_TCA_ARITHMETIC_SOURCE_20261028.json';now=datetime.datetime.now(datetime.UTC).isoformat()
next_action='Publish through genuine hooks, required-baseline committed verification and normal push/readback; inspect exact-head CI. Continue complete native fee/fill/price obligations, immutable parent budgets, qualified current policy/cohort, all-origin reservations/outbox and effectful economic reconciliation, preserving every canonical unit and acceptance identity.'
receipt={'schema':'van.rev118.exact-tca-source/1','observed_at_utc':now,'source_parent':base,
 'state':'CANDIDATE_SOURCE_TESTED_NOT_COMPLETE_ECONOMIC_OBLIGATION_OR_RESERVATION','implementation':summary,'checks':proof,
 'authority':'auth-20261022-owner-autonomous-candidate-build','raw':'ci/exact_tca_20261028',
 'retained_failures':['Original precision/trap/input-capacity reproduction:11failed1passed.',
 'First correction:58passed0. Intermediate consumer harness used unsupported Ledger context-manager protocol:11failed124passed; changed only new fixture to close actual ledgers.',
 'Next partition151passed0; new consumer additions35passed1failed due incorrect new artifact EvidenceClass enum; fixed to actual VTIL_ARTIFACT, no inherited test changed.'],
 'published_parent':{'head':base,'run_id':40766386824,'observed_state':'IN_PROGRESS_TWO_PUBLIC_JOBS_REMAINING_AT_LAST_CHECK',
  'mandatory_jobs':'FAILED: trusted-main ledger checker absent; DDS_CONTRACT_READ_DEPLOY_KEY unprovisioned',
  'four_supporting_workflows':'SUCCESS','original_archive':{'artifact_id':12850203447,'bytes':199151,
   'sha256':'3ca950ac4e31eb735e5ebe9bd70af61fcd02ff33cded5b24528f6e49e3b8ad04',
   'trading_passed':5182,'trading_declared_DDS_skip':1,'postgres_passed':26,'voice_passed':117}},
 'remaining':['Provider complete/native fee sources, future fees/financing/fill/price contingencies and multi-asset obligations',
 'family/correlation and immutable parent lifetime budgets; current qualified policy and effect-capable runtime cohort',
 'all-origin transactional order/manual/payment/transfer/handover reservations and durable effect consumers',
 'native economic finality, late fees/bust/reversal compensation and nonduplicated release',
 'all remaining canonical backend, forecast/research, assistant, crypto and operations requirements; gated Android provisioned profile on Van trading core/signing/actual Artemis S24'],
 'formal_acceptance':'NOT_ISSUED','execution_authority':False,'settlement_qualified':False,'next':next_action}
(root/'docs/rebuild/rev118'/rel).write_text(json.dumps(receipt,indent=2)+'\n')
for name in ('EXECUTION_LEDGER.json','CANDIDATE_SOURCE_PROGRESS.json'):
 p=root/'docs/rebuild/rev118'/name;d=json.loads(p.read_text());d['updated_at_utc']=now
 if name=='EXECUTION_LEDGER.json':
  d['observations'].append(summary);d['current_action']=next_action
  for uid in ('BE-010','BE-012'):
   row=d['units'].setdefault(uid,{'status':'IN_PROGRESS','candidate_source_only':True,'acceptance':'NOT_ISSUED','evidence':[]})
   if rel not in row['evidence']:row['evidence'].append(rel)
 else:
  for uid in ('BE-010','BE-012'):d['units'][uid]['milestones'].append({'description':summary,'evidence':rel})
 p.write_text(json.dumps(d,indent=2)+'\n')
p=root/'docs/rebuild/rev118/CONTINUATION_20261022.md';p.write_text(p.read_text()+'\n\n## Exact signed cost measurement —28October\n\n'+summary+'\n\n[Source receipt]('+rel+'). '+next_action+'\n')
doc='# Exact signed transaction-cost measurement\n\n'+summary+'\n\n[Source receipt](../'+rel+') retains the original counterexamples, real SQL/HTTP consumer results, full source/discovery pins and remaining obligations.\n\nThe existing compute_tca, session decision cycle, account lifecycle and evidence resolver own this behavior. No parallel financial journal or effect route is introduced. The exact witness is immutable within the TCA value and returns independent wire copies. Original legacy records stay unchanged; unsupported arithmetic claims cannot enter live or cold learning through a nested artifact. Test fixtures use synthetic broker outcomes, not connected provider evidence.\n\nMeasurement is exact relative to the explicitly supplied receipt prices, recorded charges, filled quantity and contract-value input. It does not turn a rounded contract-value input into an original native tick valuation, infer absent fees as measured, establish fees final, balance assets, settle a trade, release capital or reopen a parent entry budget. Those complete native economic sources and all-origin reservation/effect integrations remain required. All canonical backend/forecast/assistant/crypto/operations and gated Android requirements remain open according to actual evidence; profitability is evaluated rather than guaranteed.\n'
(root/'docs/rebuild/rev118/backend/BE-010_012_EXACT_TCA_ARITHMETIC.md').write_text(doc)
p=root/'docs/rebuild/rev118/BUILD_EXECUTION_PLAN.md';s=p.read_text();a=s.index('## Current concrete gap and next result');b=s.index('## Commands and evidence economy',a)
p.write_text(s[:a]+'## Current concrete gap and next result\n\n'+summary+'\n\n[Source receipt]('+rel+'). '+next_action+'\n\nThe exact published parentb0317e3d has independently verified original hosted evidence:5182trading passes/1declaredprivateDDSskip,26PostgreSQL and117voice. All4supporting workflows succeeded. Main40766386824 remains in progress at the last readback with2public jobs outstanding; the2mandatory trusted-main/private-key prerequisites failed and remain enforced. No full CI green, native/provider qualification or acceptance is claimed.\n\nComplete every original payment/manual/handover, market/feed/depth/entitlement, forecast/learning/crypto, assistant/security/operations obligation. Android uses its provisioned production profile on Van trading core after canonical gates, with real signing and Artemis/S24 acceptance. No dependency, function or acceptance identity is omitted.\n\n'+s[b:])
copy(__file__,'evidence-builder.py')
print(json.dumps({'passed':count,'pins':len(pins),'inherited_test_files_unchanged':files,'inherited_test_functions_unchanged':functions,'raw_files':sum(p.is_file() for p in raw.rglob('*')),'receipt':rel}))
