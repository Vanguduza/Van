from pathlib import Path
import json,hashlib,subprocess,shutil,collections,datetime,xml.etree.ElementTree as E
root=Path('/workspace/van-review-2026-10-18/publish')
base=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
assert base=='291de61baf55255d8ccd51ae7783df0bec4b8692'
run=Path('/workspace/van-native-instrument-catalog-sql-r3-20261028')
r=json.loads((run/'receipt.json').read_text());outer=json.loads(Path('/workspace/van-native-instrument-catalog-sql-r3-process-20261028.json').read_text())
assert r['exit']==outer['exit']==0 and r['cleaned'] and r['owned_fixture_independently_absent']
assert not json.loads((run/'storage-audit.json').read_text())['forbidden_events']
assert all(hashlib.sha256((root/p).read_bytes()).hexdigest()==h for p,h in r['source_sha256'].items())
cases=E.parse(run/'full-trading.xml').findall('.//testcase')
assert cases and all(all(c.find(k) is None for k in ['failure','error','skipped']) for c in cases)
calls=[json.loads(l) for l in (run/'test-events.jsonl').read_text().splitlines() if json.loads(l)['phase']=='call']
assert len(calls)==len(cases) and all(c['outcome']=='passed' for c in calls)
assert all(n==1 for n in collections.Counter(c['nodeid'] for c in calls).values())
full=Path('/workspace/van-native-instrument-catalog-sql-r2-20261028')
full_receipt=json.loads((full/'receipt.json').read_text());full_outer=json.loads(Path('/workspace/van-native-instrument-catalog-sql-r2-process-20261028.json').read_text())
assert full_receipt['exit']==full_outer['exit']==1 and full_receipt['owned_fixture_independently_absent']
assert not json.loads((full/'storage-audit.json').read_text())['forbidden_events']
changed=[p for p,h in full_receipt['source_sha256'].items() if hashlib.sha256((root/p).read_bytes()).hexdigest()!=h]
assert changed==['backend/tests/test_trading_api.py']
inventory=json.loads(Path('/workspace/van-native-instrument-catalog-surface-inventory-review-20261028.json').read_text())
assert inventory['original_source_sha256']==full_receipt['source_sha256'][changed[0]]
assert inventory['updated_source_sha256']==r['source_sha256'][changed[0]]
full_calls=[json.loads(l) for l in (full/'test-events.jsonl').read_text().splitlines() if json.loads(l)['phase']=='call']
failed=[c['nodeid'] for c in full_calls if c['outcome']=='failed']
assert failed==['backend/tests/test_trading_api.py::test_service_never_exposes_an_order_path']
assert len(full_calls)==5160 and sum(c['outcome']=='passed' for c in full_calls)==5159
assert all(n==1 for n in collections.Counter(c['nodeid'] for c in full_calls).values())
assert {c['nodeid'] for c in calls}<={c['nodeid'] for c in full_calls}
assert set(failed)<={c['nodeid'] for c in calls}
unique_covered=len(full_calls)
review=json.loads(Path('/workspace/van-native-instrument-catalog-scope-review-20261028.json').read_text())
assert review['frozen_unit_contracts_and_dependencies_preserved'] and review['all_identity_sets_and105_source_function_contract_hashes_preserved']
raw=root/'docs/rebuild/rev118/ci/native_instrument_catalog_20261028';assert not raw.exists();raw.mkdir(parents=True)
def copy(src,rel):
 src=Path(src);dest=raw/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest);assert src.read_bytes()==dest.read_bytes()
for tag in ['r1','r2','r3']:
 folder=Path('/workspace/van-native-instrument-catalog-sql-'+tag+'-20261028')
 for p in folder.iterdir():
  if p.is_file():copy(p,'sql_'+tag+'/'+p.name)
 for path,rel in [('/workspace/van-native-instrument-catalog-sql-'+tag+'-20261028.py','controller.py'),('/workspace/van-native-instrument-catalog-sql-'+tag+'-process-20261028.json','outer-process.json')]:copy(path,'sql_'+tag+'/'+rel)
copy('/workspace/van-native-instrument-catalog-sql-r1-controlled-interruption-20261028.json','sql_r1/controlled-interruption.json')
copy('/workspace/van-native-instrument-catalog-surface-inventory-review-20261028.json','sql_r3/strict-surface-inventory-review.json')
copy('/workspace/van-native-instrument-catalog-surface-inventory-review-20261028.py','sql_r3/strict-surface-inventory-review.py')
for tag in ['r1','r2','r3']:
 for ext in ['.log','.xml','.json','-audit.json']:
  p=Path('/workspace/van-native-instrument-catalog-focused-'+tag+'-20261028'+ext)
  if p.exists():copy(p,'focused/'+p.name)
guards=['owner-registry','frontend-registry-r2','scope-check-r2','mutation-consistency','consolidation']
for n in guards:
 assert json.loads(Path('/workspace/van-native-instrument-catalog-'+n+'-20261028.json').read_text())['exit']==0
for n in guards+['frontend-registry','scope-check','owner-refresh','owner-refresh-r2','owner-refresh-r3','frontend-apply','workmap-apply']:
 for ext in ['.log','.json']:
  p=Path('/workspace/van-native-instrument-catalog-'+n+'-20261028'+ext)
  if p.exists():copy(p,'guards/'+p.name)
for ext in ['.py','.json']:copy('/workspace/van-native-instrument-catalog-scope-review-20261028'+ext,'scope_review/verifier'+ext)
copy('/workspace/van-native-instrument-catalog-workmap-preimage-20261028.json','scope_review/previous-workmap.json')
for n in ['wip1','wip2']:
 for ext in ['.zip','.json']:copy('/workspace/van-native-instrument-catalog-'+n+'-20261028'+ext,'source_recovery/'+n+ext)
for source,target in [('/workspace/van-291de61b-native-mql-20261028','published_parent_native_compile'),('/workspace/van-291de61b-selected-hosted-20261028','published_parent_selected_hosted'),('/workspace/van-291de61b-main-ci-20261028','published_parent_main_ci')]:
 folder=Path(source)
 for p in folder.rglob('*'):
  if p.is_file():copy(p,target+'/'+str(p.relative_to(folder)))
copy('/workspace/van-mt5-quotes-publication-20261028.json','published_parent/publication.json')
copy('/workspace/van-mt5-quotes-committed-inputs-20261028.json','published_parent/committed-inputs.json')
paths=subprocess.check_output(['git','diff','--name-only'],cwd=root,text=True).splitlines()+subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=root,text=True).splitlines()
source=sorted(p for p in paths if p.startswith(('backend/','trading/','tools/rebuild/')))
hashes={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in source}
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
summary=(f'Original native catalog discovery/alias resolution now reaches the registered paired-owner HTTP route through the existing dedicated catalog store. The new read-only SQLite opener creates/migrates no source and refuses writes. Discovery retains enabled/hidden/archived/omitted-name rows, realm/account identities and original availability. Exact-name collisions stay ambiguous even on a one-row page; explicit IDs disambiguate without trading permission. Source/selector/revision-bound pages preserve original history. Future captures, invalid/conflicting selectors and unavailable/corrupt/over-budget sources remain explicit; disconnected callers retain their owned read slots until completion. Existing frontend InstrumentRef is supplied only for representable original names, with no invented contract revision. Broad SQLr2 remains actualFAILED exit1:5159passed/1outdatedstrictpublic-methodinventoryassertion. The only subsequent AST change adds the two explicit readonly members to that expected set; every other assertion and banned capability check remains intact. Targeted SQLr3 reran the complete affected gateway module, catalog/HTTP/depth/private-core/schema/scope cases:{len(cases)}passed0skip/fail/audit,actualinner/outerexit0,all{len(r["source_sha256"])}finalinputhashesmatch,ownedPostgreSQLindependentlyabsent. Both runs cover{unique_covered}unique current-source case identities after that sole inventory correction; runtime input bytes are unchanged. This is reuse of unchanged runtime evidence plus an actual targeted rerun, not a single clean full rerun.84focusedpassesoverlap;30PostgreSQLcaseswereexplicitlydeselectedonlyinthefocusedrun. Frozen unit contracts/dependencies and allidentitysets/105sourcefunctioncontracthashesremainintact;source-rowhashupdatesareonlyactualcitationrefreshplusoneadditivecatalogextensionperexistingchartfeature/surface.0formal/native/production/S24acceptancesissued.')
rel='receipts/NATIVE_INSTRUMENT_CATALOG_SOURCE_20261028.json'
receipt={'schema':'van.rev118.native-instrument-catalog-source/1','source_parent':base,'observed_at_utc':now,
 'source_files_sha256':hashes,'implementation':summary,
 'source_result':{'qualification_method':'UNCHANGED_RUNTIME_EVIDENCE_PLUS_COMPLETE_AFFECTED_SQL_HTTP_RERUN_NOT_ONE_CLEAN_FULL_RUN',
  'broader_sql_r2':{'actual_inner_exit':1,'actual_outer_exit':1,'passed':5159,'failed':1,'skipped':0,'retained_failure':failed[0],'owned_postgres_independently_absent':True},
  'targeted_sql_r3':{'actual_outer_exit':0,'actual_inner_exit':0,'passed':len(cases),'skipped':0,'audit_violations':0,'unique_call_ids_once_in_this_run':len(calls),'pinned_inputs_matched':len(r['source_sha256']),'owned_postgres_independently_absent':True,'raw':'ci/native_instrument_catalog_20261028/sql_r3'},
  'unique_current_source_cases_covered_after_inventory_correction':unique_covered,'overlapping_targeted_case_ids':len(calls),'sole_changed_full_input':'backend/tests/test_trading_api.py','sole_AST_change':'Two explicit readonly expected members; all other assertions and capability bans preserved'},
 'retained_attempts':['Focusedr1:26passed1failed9deselected. The actual causal guard correctly hid future2027 data from a real2026 clock; the readonly fixture now injects its source clock.','Owner-refreshr2 refused an owned intermediate generated preimage. Its six outputs were CRC/hash-verified against WIP1 and preserved before restoring only those committed preimages. Genuine unchanged CLI regenerated successfully.','Initial frontend/workmap checks detected stale derived fingerprints. Real CLIs regenerated them; full original row/value/order review confirms source citations plus additive extension only.','FullSQLr1 was deliberately interrupted after starting before derived regeneration. Actualexit2; original controller cleaned and independently confirmed owned PostgreSQL absent. Partial evidence is not a pass.','FullSQLr2 actualexit1/5159pass1failure is retained as failed. Only the strict service public-method expected set needed the new readonly method/config field. Original input hash and AST delta independently checked; complete affected module and SQL/HTTP boundary cases reran inr3.'],
 'scope_review':{'raw':'ci/native_instrument_catalog_20261028/scope_review/verifier.json',
  'sha256':hashlib.sha256(Path('/workspace/van-native-instrument-catalog-scope-review-20261028.json').read_bytes()).hexdigest(),
  'frozen_unit_contracts_and_dependencies_preserved':True,'all_identity_sets_and105_source_function_contract_hashes_preserved':True,
  'changed_source_row_hashes':review['changed_source_row_hashes'],
  'existing_row_changes':'Original source citation refresh only; original lines independently match relocated lines. One additive catalog extension per existing chart feature/surface.'},
 'backend_registry_counts':{'endpoints':len(json.loads((root/'registries/owner_endpoints.json').read_text())['endpoints']),'schemas':len(json.loads((root/'registries/owner_endpoint_schemas.json').read_text())['components']['schemas'])},
 'formal_acceptances_issued':0,'limitations':['The HTTP source path is an existing provisioned SQLite catalog. Existing direct catalog owners retain SQLite/PostgreSQL support; no native collection, provider connection or PostgreSQL HTTP replica is fabricated.','Original source listings are not a resolved full contract, entitlement or current tradability. Other prescribed native discovery, subscription/stream/bar/gap/depth and qualification obligations remain open.','SQL/native protobuf and HTTP test fixtures are source evidence, not actual connected-provider or Samsung-device acceptance. Python storage audit is not an OS sandbox.','All financial reservations/current-policy/reconciliation/payment/manual/handover, forecast/learning/crypto/assistant/security/operations and Android functions remain required.'],
 'source_authorizations':['auth-20261022-owner-autonomous-candidate-build','auth-20261022-owner-owner-contract-refresh'],
 'next':'Genuine authorized commit, committed required-baseline verification, normal exact publication and hosted CI; continue full native contract/feed/valuation and shared financial workflow completion without dropping any original function.'}
(root/'docs/rebuild/rev118'/rel).write_text(json.dumps(receipt,indent=2)+'\n')
for name in ['EXECUTION_LEDGER.json','CANDIDATE_SOURCE_PROGRESS.json']:
 p=root/'docs/rebuild/rev118'/name;v=json.loads(p.read_text());v['updated_at_utc']=now
 if name=='EXECUTION_LEDGER.json':
  v['observations'].append(summary);v['current_action']=receipt['next']
  for uid in ['BE-003','BE-008']:v['units'][uid]['evidence'].append(rel)
 else:
  for uid in ['BE-003','BE-008']:v['units'][uid]['milestones'].append({'description':summary,'evidence':rel})
 p.write_text(json.dumps(v,indent=2)+'\n')
p=root/'docs/rebuild/rev118/backend/BE-008_NATIVE_INSTRUMENT_CATALOG_HTTP.md';text=p.read_text();text=text.replace('Focused SQLite/HTTP and private-core regressions passed; actual full PostgreSQL/trading/HTTP qualification and source evidence are pending.',summary+'\n\nRead the [exact source receipt](../'+rel+') and retained raw evidence.');p.write_text(text)
copy(__file__,'evidence-builder.py')
print(json.dumps({'source_files':len(source),'raw_files':sum(p.is_file() for p in raw.rglob('*')),'targeted_passed':len(cases),'broader_actual_failed_run':'5159passed1failed','unique_cases_covered_after_sole_inventory_correction':unique_covered,'pinned_inputs':len(r['source_sha256']),'receipt':rel}))
