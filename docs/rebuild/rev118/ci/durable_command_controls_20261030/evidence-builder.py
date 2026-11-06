"""Bind executed command-control evidence without issuing unit or native acceptance."""
from pathlib import Path
import datetime,gzip,hashlib,json,subprocess
import xml.etree.ElementTree as ET

root=Path('/workspace/van-review-2026-10-18/publish');base='524e1ca2aadc076642b5e237e0b9765065610927'
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()==base
run=Path('/workspace/van-pretrade-durable-budget-final-full-r1-20261030')
lite=Path('/workspace/van-pretrade-ci-lite-broad-r1-20261030')
r=json.loads((run/'receipt.json').read_text());lr=json.loads((lite/'receipt.json').read_text())
assert r['completed'] and r['exit']==0 and r['cleaned'] and r['owned_fixture_independently_absent']
assert lr['completed'] and lr['exit']==0 and lr['cleaned'] and lr['owned_children_independently_reaped'] and lr['source_hashes_still_match']
assert lr['capability']['psycopg_available'] is False
pins=r['source_sha256']|r['reference_fixtures_sha256'];assert len(pins)==1308
assert pins==lr['source_sha256']|lr['reference_fixtures_sha256']
for f,h in pins.items():assert hashlib.sha256((root/f).read_bytes()).hexdigest()==h,f
def counts(path):
 cases=ET.parse(path).findall('.//testcase')
 return {'passed':sum(not any(c.find(k)is not None for k in ('failure','error','skipped')) for c in cases),
 'failed':sum(c.find('failure')is not None for c in cases),'errors':sum(c.find('error')is not None for c in cases),
 'skipped':sum(c.find('skipped')is not None for c in cases)}
assert counts(run/'full-trading.xml')=={'passed':5442,'failed':0,'errors':0,'skipped':0}
assert counts(lite/'broad.xml')=={'passed':5126,'failed':0,'errors':0,'skipped':311}
def nodes(path):return {s for s in path.read_text().splitlines() if s.startswith(('trading/tests/','backend/tests/','tests/rebuild/')) and '::' in s}
primary_nodes=nodes(Path('/workspace/van-pretrade-durable-budget-final-collection-20261030.log'))
lite_nodes=nodes(Path('/workspace/van-pretrade-ci-lite-collection-20261030.log'))
parent_nodes=nodes(Path('/workspace/van-entry-dispatch-final-collection-20261029.log'))
assert len(primary_nodes)==5442 and len(lite_nodes)==5437 and len(parent_nodes)==5408 and parent_nodes<=primary_nodes
for folder,expected,passed,skipped in ((run,primary_nodes,5442,0),(lite,lite_nodes,5126,311)):
 assert not json.loads((folder/'storage-audit.json').read_text())['forbidden_events']
 events=[json.loads(s) for s in (folder/'test-events.jsonl').read_text().splitlines()]
 assert {e['nodeid'] for e in events}==expected
 calls=[e for e in events if e['phase']=='call']
 assert len(calls)==len({e['nodeid'] for e in calls})
 assert all(e['outcome'] in ('passed','skipped') for e in events)
 passed_ids={e['nodeid'] for e in calls if e['outcome']=='passed'}
 skipped_ids={e['nodeid'] for e in events if e['outcome']=='skipped'}
 assert len(passed_ids)==passed and len(skipped_ids)==skipped and passed_ids|skipped_ids==expected
preserved=json.loads(Path('/workspace/van-pretrade-source-preservation-20261030.json').read_text())
assert preserved['inherited_test_files']==316 and preserved['byte_identical']==315
assert preserved['all_original_test_signatures_preserved'] and preserved['all_original_assertions_preserved']
assert preserved['changed_only_deferred_optional_import']==['trading/tests/test_entry_dispatch_commit_fence_postgres.py']
for name in ('collection','workmap','owner','frontend','mutations','consolidation'):
 d=json.loads(Path('/workspace/van-pretrade-durable-budget-final-'+name+'-20261030.json').read_text())
 assert d['state']=='COMPLETED' and d['exit']==0
env=json.loads(Path('/workspace/van-pretrade-ci-lite-environment-20261030.json').read_text())
assert not env['psycopg_available'] and env['lock_sha256']==hashlib.sha256((root/'backend/requirements.lock').read_bytes()).hexdigest()
assert counts(Path('/workspace/van-pretrade-ci-lite-optional-pg-20261030.xml'))=={'passed':0,'failed':0,'errors':0,'skipped':9}
protocol={}
for name in ('OpenApiCommonMessages.proto','OpenApiCommonModelMessages.proto','OpenApiMessages.proto','OpenApiModelMessages.proto','PROVENANCE.json'):
 f='trading/vati/execution/ctrader/proto/'+name;b=(root/f).read_bytes()
 assert b==subprocess.check_output(['git','show',base+':'+f],cwd=root);protocol[f]=hashlib.sha256(b).hexdigest()
raw=root/'docs/rebuild/rev118/ci/durable_command_controls_20261030';raw.mkdir(parents=True,exist_ok=True)
def copy(source,dest):
 source=Path(source);dest=raw/dest;dest.parent.mkdir(parents=True,exist_ok=True);data=source.read_bytes()
 if dest.suffix=='.gz':dest.write_bytes(gzip.compress(data,mtime=0));assert gzip.decompress(dest.read_bytes())==data
 else:dest.write_bytes(data);assert dest.read_bytes()==data
for folder,label in ((run,'primary-full'),(lite,'backend-only-broad'),
 (Path('/workspace/van-pretrade-durable-budget-focused-r1-20261029'),'focused167'),
 (Path('/workspace/van-pretrade-durable-budget-focused-r2-20261029'),'focused171')):
 rec=json.loads((folder/'receipt.json').read_text());assert rec['completed'] and rec['exit']==0 and rec['cleaned']
 for p in folder.iterdir():
  if p.is_file():copy(p,label+'/'+p.name+('.gz' if p.suffix=='.jsonl' else ''))
 copy(str(folder)+'.py',label+'/controller.py')
prefixes=('van-pretrade-durable-budget-before-20261029','van-pretrade-config-before-20261029',
 *('van-pretrade-durable-budget-after-r'+str(i)+'-20261029' for i in (1,2,3,4)),
 'van-pretrade-ci-lite-install-20261029','van-pretrade-ci-lite-collection-20261030','van-pretrade-ci-lite-optional-pg-20261030',
 *('van-pretrade-durable-budget-final-'+name+'-20261030' for name in ('collection','workmap','owner','frontend','mutations','consolidation')))
for prefix in prefixes:
 for suffix in ('.json','.log','.xml'):
  p=Path('/workspace')/(prefix+suffix)
  if p.exists():copy(p,p.name)
for name in ('van-pretrade-durable-budget-before-source-20261029.json','van-pretrade-source-preservation-20261030.json',
 'van-pretrade-ci-lite-environment-20261030.json','van-pretrade-durable-budget-wip1-20261029.json',
 'van-pretrade-durable-budget-wip2-20261030.json','van-524e1ca2-main-final-jobs-20261030.json',
 'van-524e1ca2-final-workflows-20261030.json','van-524e1ca2-cognitive-python-failed-original-20261029.log',
 'van-524e1ca2-ledger-original-failure-20261030.log','van-524e1ca2-backend-original-failure-20261030.log'):
 copy('/workspace/'+name,name)
proof={'primary_suite':counts(run/'full-trading.xml'),'dependency_light_suite':counts(lite/'broad.xml'),
 'overlapping_suites_not_additive':True,'primary_collection_and_calls_once':True,
 'dependency_light_collection_and_passed_or_declared_skip_identity_sets_match':True,
 'all5408_parent_cases_retained':True,'new_primary_cases':34,'source_input_sha256':pins,'source_pins':len(pins),
 'original_protocol_reference_sha256':protocol,'preservation':preserved,'storage_violations_both_runs':0,
 'owned_postgres_independently_absent':True,'dependency_light_owned_children_reaped':True,
 'dependency_light_postgres_driver_absent_before_and_after':True,'native_or_formal_acceptance':False}
(raw/'source-preservation-and-discovery.json').write_text(json.dumps(proof,indent=2)+'\n')
now=datetime.datetime.now(datetime.UTC).isoformat();rel='receipts/DURABLE_COMMAND_CONTROLS_SOURCE_20261030.json'
summary=('Actual pre-trade controls now recover original account command times, keys and exact quantities from the shared SQLite/PostgreSQL ledger. Recreating a control owner cannot reset its configured rate window or erase the size history used by the fat-finger control. Only the exact independently committed current command is excluded from prior-history checks; its admission remains recorded. Invalid/future/conflicting/unbound history, changed joint configuration, a foreign ledger owner and unmerged legacy notes refuse new entries while protective reductions remain available. Optional PostgreSQL test imports now run inside the existing opted-in fixture boundary, preserving every assertion. Primary source qualification: 5,442 passed, zero failures/errors/skips/storage violations. Fresh backend-lock-only cognitive selection: 5,126 passed, 311 declared skips, zero failures/errors/storage violations; psycopg absent before and after. These overlapping suites are separate. All 1,308 input hashes and both discovery/event identity sets match; owned PostgreSQL is independently absent and dependency-light children reaped. All 3,100 original test signatures and 7,651 assertions remain unchanged across 316 inherited test files: 315 byte-identical, one optional-import relocation. This partial BE-003/009/010 packet does not complete immutable parent budgets, policy/cohort admission, all-origin financial reservations or native/economic reconciliation.')
next_action='Commit through the genuine Project Truth hook, wait for terminal required-baseline committed verification before normal push, independently read the exact remote and all hosted workflows, and repair actual failures. Continue the canonical complete financial workflow: immutable parent/child lifetime quantity and command budgets, complete fee/fill/price/multi-asset obligations, qualified policy/runtime cohort and all-origin transactional reservations/outbox/reconciliation. Then complete every original backend/forecast/assistant/crypto/operations obligation and gated Android with provisioned profile on Van trading core, genuine signing and actual Artemis/S24 acceptance.'
receipt={'schema':'van.rev118.durable-command-controls-source/1','observed_at_utc':now,'source_parent':base,
 'state':'PARTIAL_CANDIDATE_SOURCE_TESTED_NOT_PARENT_BUDGET_OR_RESERVATION_ACCEPTANCE','implementation':summary,
 'checks':proof,'raw':'ci/durable_command_controls_20261030','authority':['auth-20261022-owner-autonomous-candidate-build'],
 'formal_acceptance':'NOT_ISSUED','execution_authority':False,'reservation_qualified':False,
 'retained_failures':['Original rate-window counterexample: warm owner passed and recreated owner failed (two dispatches), 1 passed/1 failed.',
 'Original invalid control configuration probes: 9 failed; bool/nonfinite/nonpositive limits were admitted. Strict typed validation and instance configuration identity now retain those failures as repaired counterexamples.',
 'Intermediate expanded run:94 passed/1 new-fixture failure because requested risk was below native minimum lot. The fixture now uses .0003 risk to obtain the same asserted .01 lot; no assertion weakened.',
 'Published parent524 cognitive workflow40802854444/job123214772667 failed broad collection on unconditional psycopg import. Original failed run remains failed; its broad functional assertions were unexecuted. The new dependency-light run validates the repair separately.'],
 'remaining':['The instance configuration seal does not admit a different policy or software version. Current qualified policy/artifact/cohort admission and immutable original parent grants remain required.',
 'Configured per-account entry-command controls do not complete parent lifetime budgets, all child methods, physical-account all-alias or all-origin reservations, financial release/corrections/bust and complete native economic obligations.',
 'All 82 backend units,12 verification packets,38 forecast/research backend units and all original assistant/voice/crypto/operations/Android contracts retain their full requirements.'],
 'adjacent_native_work_reuse':{'state':'REPORTED_BOUNDED_HARNESS_SOFTWARE_REPAIR_COMPLETE_NOT_VAN_ACCEPTANCE',
 'source':'https://github.com/Vanguduza/dial-development-system/pull/308#issuecomment-6514813335',
 'instruction_for_continuation':'Reuse the reported completed Harness repair when integrating the actual Van browser consumer. Preserve remaining production admission and native interactive-session binding requirements; do not repeat its completed installation/canary.',
 'formal_unit_acceptance':False},'next':next_action}
(root/'docs/rebuild/rev118'/rel).write_text(json.dumps(receipt,indent=2)+'\n')
for name in ('EXECUTION_LEDGER.json','CANDIDATE_SOURCE_PROGRESS.json'):
 p=root/'docs/rebuild/rev118'/name;d=json.loads(p.read_text());d['updated_at_utc']=now
 if name=='EXECUTION_LEDGER.json':
  d['observations'].append(summary);d['current_action']=next_action
  for uid in ('BE-003','BE-009','BE-010'):
   if rel not in d['units'][uid]['evidence']:d['units'][uid]['evidence'].append(rel)
 else:
  for uid in ('BE-003','BE-009','BE-010'):d['units'][uid]['milestones'].append({'description':summary,'evidence':rel})
 p.write_text(json.dumps(d,indent=2)+'\n')
p=root/'docs/rebuild/rev118/CONTINUATION_20261022.md';p.write_text(p.read_text()+'\n\n## Durable command controls and optional-driver recovery — 30 October\n\n'+summary+'\n\n[Source receipt]('+rel+'). '+next_action+'\n')
doc='# Durable command controls and optional-driver recovery\n\n'+summary+'\n\nThe actual router and controls share the same ledger object so the final history check uses the command writer. An independently committed current command may be excluded only with its exact event reference, command hash, decision hash, trade identity, key and producer. Expiry follows original publication time. Fees, exits and receipt changes do not delete original command admissions. Corrupt history cannot raise the historical size baseline or silently clear an existing limit. Legacy in-memory notes cannot be discarded by rebinding an empty durable owner.\n\nLimits use strict positive integer counts/windows and finite Decimal notional caps. A changed configuration requires fresh admission; the instance seal issues none. Full immutable parent lifetime grants, current qualified policy/cohort and all-origin financial reservations remain separate required workflows.\n\nThe published parent cognitive job failed collection because a PG-only test imported an optional driver before its existing fixture could select the test. The import now occurs inside the selected test body. All original assertions and test signatures remain intact. Real PostgreSQL checks execute those cases; the backend-only mode reports its explicit PG skips. Both dependency modes retain their actual source inputs, outcomes and cleanup evidence in the [source receipt](../'+rel+'). No skipped or unexecuted assertion is labeled passing.\n\nAll original backend and frontend contracts remain. Reuse the separately reported completed browser Harness software repair during later real-consumer integration, retaining its native admission and interactive binding boundaries. Android follows BG-001, uses its provisioned production profile on Van trading core and requires genuine signing and actual Artemis/S24 acceptance. Profitability remains an objective evaluated with evidence.\n'
(root/'docs/rebuild/rev118/backend/BE-003_009_010_DURABLE_COMMAND_CONTROLS.md').write_text(doc)
p=root/'docs/rebuild/rev118/BUILD_EXECUTION_PLAN.md';text=p.read_text();a=text.index('## Current concrete gap and next result');b=text.index('## Commands and evidence economy',a)
p.write_text(text[:a]+'## Current concrete gap and next result\n\n'+summary+'\n\n[Current source receipt]('+rel+'). '+next_action+'\n\nKeep every complete work front above and all original unit identities. Source-tested subpaths issue no formal unit acceptance. The original parent CI failures and native admission requirements remain recorded; a local repair does not relabel an earlier failed run. Reuse the reported completed browser Harness software repair when its real Van consumer is dependency-ready; preserve production admission and native interactive binding requirements.\n\n'+text[b:])
copy(__file__,'evidence-builder.py')
print(json.dumps({'primary_passed':5442,'dependency_light_passed':5126,'dependency_light_declared_skips':311,
 'source_pins':len(pins),'inherited_files_byte_identical':315,'original_test_functions':3100,'original_assertions':7651,
 'raw_files':sum(p.is_file() for p in raw.rglob('*')),'receipt':rel}))
