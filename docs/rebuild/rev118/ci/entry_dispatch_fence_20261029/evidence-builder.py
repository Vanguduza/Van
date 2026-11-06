"""Publish only executed source evidence; preserve complete canonical obligations."""
from pathlib import Path
import ast,datetime,gzip,hashlib,io,json,subprocess,tarfile
import xml.etree.ElementTree as ET

root=Path('/workspace/van-review-2026-10-18/publish')
base='42b34f43657dcc64503e951d946f4231c4f3022d'
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()==base
run=Path('/workspace/van-entry-dispatch-final-full-r1-20261029')
receipt=json.loads((run/'receipt.json').read_text())
assert receipt['completed'] and receipt['exit']==0 and receipt['cleaned'] and receipt['owned_fixture_independently_absent']
pins=receipt['source_sha256']|receipt['reference_fixtures_sha256']
assert len(pins)==1305
for f,h in pins.items():assert hashlib.sha256((root/f).read_bytes()).hexdigest()==h,f
assert not json.loads((run/'storage-audit.json').read_text())['forbidden_events']
def junit(path):
 cases=ET.parse(path).findall('.//testcase')
 return {'passed':sum(not any(c.find(k)is not None for k in ('failure','error','skipped')) for c in cases),
   'failed':sum(c.find('failure')is not None for c in cases),
   'errors':sum(c.find('error')is not None for c in cases),'skipped':sum(c.find('skipped')is not None for c in cases)}
assert junit(run/'full-trading.xml')=={'passed':5408,'failed':0,'errors':0,'skipped':0}
calls=[json.loads(s) for s in (run/'test-events.jsonl').read_text().splitlines() if json.loads(s)['phase']=='call']
assert len(calls)==len({c['nodeid'] for c in calls})==5408 and all(c['outcome']=='passed' for c in calls)
def nodes(path):return {s for s in path.read_text().splitlines() if s.startswith(('trading/tests/','backend/tests/','tests/rebuild/')) and '::' in s}
collection=Path('/workspace/van-entry-dispatch-final-collection-20261029.log')
assert nodes(collection)=={c['nodeid'] for c in calls}
parent_nodes=nodes(Path('/workspace/van-mt5-native-cost-final-collection-20261029.log'))
assert len(parent_nodes)==5385 and parent_nodes<=nodes(collection)
preserved=functions=assertions=0
with tarfile.open(fileobj=io.BytesIO(subprocess.check_output(['git','archive',base,'trading/tests','tests/rebuild'],cwd=root))) as tar:
 for member in tar:
  if not member.isfile() or not member.name.endswith('.py') or not Path(member.name).name.startswith('test_'):continue
  before=tar.extractfile(member).read();assert before==(root/member.name).read_bytes(),member.name
  tree=ast.parse(before);preserved+=1
  functions+=sum(isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name.startswith('test_') for n in ast.walk(tree))
  assertions+=sum(isinstance(n,ast.Assert) for n in ast.walk(tree))
assert preserved==314
for label in ('collection','workmap','owner','frontend','mutations','consolidation'):
 r=json.loads(Path('/workspace/van-entry-dispatch-final-'+label+'-20261029.json').read_text())
 assert r['state']=='COMPLETED' and r['exit']==0
focused=Path('/workspace/van-entry-dispatch-focused-r1-20261029')
fr=json.loads((focused/'receipt.json').read_text())
assert fr['completed'] and fr['exit']==0 and fr['cleaned'] and fr['owned_fixture_independently_absent']
assert junit(focused/'full-trading.xml')=={'passed':90,'failed':0,'errors':0,'skipped':0}
parent_probe=json.loads(Path('/workspace/van-entry-dispatch-parent-differential-20261029.json').read_text())
assert parent_probe['state']=='COMPLETED_EXPECTED_TWO_FAILURES' and parent_probe['inputs_unchanged_after']
assert junit(Path('/workspace/van-entry-dispatch-parent-differential-20261029.xml'))=={'passed':0,'failed':2,'errors':0,'skipped':0}
protocol={}
for name in ('OpenApiCommonMessages.proto','OpenApiCommonModelMessages.proto','OpenApiMessages.proto','OpenApiModelMessages.proto','PROVENANCE.json'):
 f='trading/vati/execution/ctrader/proto/'+name;b=(root/f).read_bytes()
 assert b==subprocess.check_output(['git','show',base+':'+f],cwd=root);protocol[f]=hashlib.sha256(b).hexdigest()
raw=root/'docs/rebuild/rev118/ci/entry_dispatch_fence_20261029';raw.mkdir(parents=True,exist_ok=True)
def copy(source,dest):
 source=Path(source);dest=raw/dest;dest.parent.mkdir(parents=True,exist_ok=True);data=source.read_bytes()
 if dest.suffix=='.gz':dest.write_bytes(gzip.compress(data,mtime=0));assert gzip.decompress(dest.read_bytes())==data
 else:dest.write_bytes(data);assert dest.read_bytes()==data
for folder,label in ((run,'final-full'),(focused,'focused90')):
 for p in folder.iterdir():
  if p.is_file():copy(p,label+'/'+p.name+('.gz' if p.suffix=='.jsonl' else ''))
 copy(str(folder)+'.py',label+'/controller.py')
for prefix in ('van-entry-dispatch-fence-before-20261029','van-entry-dispatch-ambient-before-20261029',
 'van-entry-dispatch-fence-after-r1-20261029','van-entry-dispatch-fence-after-r2-20261029',
 'van-entry-dispatch-fence-after-r3-20261029','van-entry-dispatch-parent-differential-exec-20261029',
 *('van-entry-dispatch-final-'+label+'-20261029' for label in ('collection','workmap','owner','frontend','mutations','consolidation'))):
 for suffix in ('.json','.log','.xml'):
  p=Path('/workspace')/(prefix+suffix)
  if p.exists():copy(p,p.name)
for name in ('van-entry-dispatch-parent-differential-20261029.json','van-entry-dispatch-parent-differential-20261029.xml',
 'van-entry-dispatch-wip1-20261029.json','van-42b34f43-mql-original-readback-20261029.json',
 'van-42b34f43-postgres-original-readback-20261029.json','van-42b34f43-android-original-readback-20261029.json',
 'van-42b34f43-main-jobs-observed-20261029.json','van-42b34f43-supporting-runs-observed-20261029.json',
 'van-42b34f43-ledger-original-failure-20261029.log',
 'van-42b34f43-backend-original-failure-20261029.log'):
 copy('/workspace/'+name,name)
copy('/workspace/van-entry-dispatch-parent-runtime-42-20261029/trading/tests/test_entry_dispatch_parent_differential.py','original-parent-probe.py')
proof={'selected_suite':{'passed':5408,'failed':0,'errors':0,'skipped':0,'storage_violations':0},
 'one_collection_and_call_set_each_once':True,'all5385_parent_cases_retained':True,'new_cases':23,
 'source_input_sha256':pins,'source_pins':len(pins),'original_protocol_reference_sha256':protocol,
 'all_inherited_test_files_byte_identical':preserved,'original_test_functions_preserved':functions,
 'original_assertions_preserved':assertions,'owned_postgres_independently_absent':True,
 'focused90_overlaps_final_suite_not_additive':True,'isolated_published_parent_counterexamples':{'failed':2,'pinned_inputs':652},
 'native_or_formal_acceptance':False}
(raw/'source-preservation-and-discovery.json').write_text(json.dumps(proof,indent=2)+'\n')
now=datetime.datetime.now(datetime.UTC).isoformat();rel='receipts/ENTRY_DISPATCH_COMMIT_FENCE_SOURCE_20261029.json'
summary=(f'The actual shared ExecutionRouter now serializes its final durable idempotency check and original command append under the existing SQLite/PostgreSQL writer. Transport requires an independently read committed command; a stale pre-existing router cannot resend the same key. Caller write/read transactions cannot dispatch staged commands. Grant/lease/kill/current controls and original deadlines are checked after writer acquisition and again after independent readback. Lost commit ACK/readback remains an original-command publication uncertainty with no transport attempt; confirmed post-commit refusal records source-bound NOT_DISPATCHED rather than inventing a native effect. Actual process death, concurrency, SQL lock wait, signed SDK handoff and restart preserve the original key. Final source suite:5,408 passed, zero failures/errors/skips/storage violations, one independently identical collection/call set each once; all1,305 input hashes matched and ownedPostgreSQL independently absent. All5,385 parent cases and all{preserved} inherited test files/{functions} original test functions/{assertions} assertions remain unchanged. Isolated published-parent reproduction fails both unsafe paths with652 input pins verified. Focused90 overlaps the final run. This entry publication fence does not complete parent/child budgets, all-origin reservations, native/economic reconciliation or formal/native/production/device acceptance.')
next_action='Genuine Project Truth hook commit using existing autonomous-candidate authorization, terminal required-baseline committed verification before normal push, independently read exact remote and CI. Continue complete exact resources/order-price semantics, immutable parent/child lifetime quantity/command budgets, complete fee/fill/multi-asset obligations, current qualified policy/cohort and all-origin transactional reservations/outbox/reconciliation. Preserve every remaining backend requirement and gated Android production profile on Van trading core, signing and actual Artemis/S24 acceptance.'
data={'schema':'van.rev118.entry-dispatch-commit-fence-source/1','observed_at_utc':now,'source_parent':base,
 'state':'PARTIAL_CANDIDATE_SOURCE_TESTED_NOT_FINANCIAL_RESERVATION_OR_NATIVE_ACCEPTANCE','implementation':summary,
 'checks':proof,'raw':'ci/entry_dispatch_fence_20261029','authority':['auth-20261022-owner-autonomous-candidate-build'],
 'retained_failures':['Original two source probes failed before repair. Current unchanged counterexample functions also fail against isolated published42b34f43 runtime;652 pinned inputs verified unchanged.',
 'First implementation:17failed/34passed/1declaredDDSskip. Independent JSON readback was incorrectly compared to the in-memory Decimal payload as Python objects; canonical event hashes are now checked. No original assertion changed.',
 'Intermediate focused51pass/1declaredDDSskip and66pass/1declaredDDSskip are separate, overlapping checks, not the final5,408-case result.'],
 'native_compile':'Parent42b34f43 original official signed MetaEditor artifact byte/source/log/binary proof retained; EA remains byte-identical. This is compilation only.',
 'formal_acceptance':'NOT_ISSUED','execution_authority':False,'reservation_qualified':False,
 'remaining':['Parent/child grants, complete child methods, immutable lifetime budgets and financial resource allocation are still required.',
 'Different-ledger/host/native-writer cohort qualification and all-origin shared reservations/legacy migration are still required; the entry SQL fence is scoped to its existing ledger owner.',
 'Full native fees, economic finality/corrections/bust/release and all manual/payment/transfer/handover consumers remain open.',
 'All original market/forecast/learning/crypto/assistant/voice/security/operations and gated Android requirements remain intact.'],
 'next':next_action}
(root/'docs/rebuild/rev118'/rel).write_text(json.dumps(data,indent=2)+'\n')
for name in ('EXECUTION_LEDGER.json','CANDIDATE_SOURCE_PROGRESS.json'):
 p=root/'docs/rebuild/rev118'/name;d=json.loads(p.read_text());d['updated_at_utc']=now
 if name=='EXECUTION_LEDGER.json':
  d['observations'].append(summary);d['current_action']=next_action
  for uid in ('BE-003','BE-009','BE-010'):
   if rel not in d['units'][uid]['evidence']:d['units'][uid]['evidence'].append(rel)
 else:
  for uid in ('BE-003','BE-009','BE-010'):d['units'][uid]['milestones'].append({'description':summary,'evidence':rel})
 p.write_text(json.dumps(d,indent=2)+'\n')
p=root/'docs/rebuild/rev118/CONTINUATION_20261022.md';p.write_text(p.read_text()+'\n\n## Committed entry dispatch and shared durable idempotency — 29 October\n\n'+summary+'\n\n[Source receipt]('+rel+'). '+next_action+'\n')
doc='# Committed entry dispatch and shared durable idempotency\n\n'+summary+'\n\nThe original caller-visible receipt and sealed command formats remain compatible. Confirmed post-commit refusals carry the original command reference, `native_dispatch_attempted=false` and `dispatch_state=NOT_DISPATCHED`. An unavailable local arrival clock stays unavailable. The source fence performs no provider query while holding the SQL writer and retains existing owner-key and runtime-lease guards through submission and protection. It never automatically resubmits an uncertain original command.\n\nThe original two counterexamples execute against a separate pinned copy of the published parent runtime. Source-bound tests cover a distinct connection observing the command before signed SDK order send, concurrent pre-existing routers, real PostgreSQL lock waiting through grant expiry, commit ACK loss, readback failure, actual process death, restart and expiry/revocation/kill/clock changes at both storage boundaries. All original tests remain byte-identical.\n\n[Source receipt](../'+rel+') and its raw evidence retain failed attempts and exact source/discovery/call proofs. Admission, native account, deployed cohort and S24 evidence remain separate. Full economic obligations, parent/child lifetime budgets and every order/manual/payment/handover reservation consumer remain required. All82 backend units and12 verification packets retain their full contracts; no formal acceptance is issued. Android follows BG-001, uses its provisioned profile on Van trading core and requires genuine signing and Artemis/S24 acceptance. Profitability remains an evidence-based objective.\n'
(root/'docs/rebuild/rev118/backend/BE-003_009_010_ENTRY_DISPATCH_COMMIT_FENCE.md').write_text(doc)
p=root/'docs/rebuild/rev118/BUILD_EXECUTION_PLAN.md';text=p.read_text();a=text.index('## Current concrete gap and next result');b=text.index('## Commands and evidence economy',a)
p.write_text(text[:a]+'## Current concrete gap and next result\n\n'+summary+'\n\n[Current source receipt]('+rel+'). '+next_action+'\n\nThe complete work fronts above and all82 backend units/12 verification packets retain their full contracts. No original feature becomes complete through this bounded source result. Private DDS credentials and trusted-main ledger admission remain required; neither is waived by a local source check.\n\n'+text[b:])
copy(__file__,'evidence-builder.py')
print(json.dumps({'passed':5408,'source_pins':len(pins),'inherited_files_unchanged':preserved,'functions':functions,'assertions':assertions,'raw_files':sum(p.is_file() for p in raw.rglob('*')),'receipt':rel}))
