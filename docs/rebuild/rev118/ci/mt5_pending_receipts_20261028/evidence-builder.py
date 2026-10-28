from pathlib import Path
import json,hashlib,subprocess,shutil,collections,datetime,ast,xml.etree.ElementTree as E
root=Path('/workspace/van-review-2026-10-18/publish');base='3732798104c476680cac8e22f833f2ed764d77e2'
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()==base
run=Path('/workspace/van-mt5-pending-receipt-sql-r1-20261028');r=json.loads((run/'receipt.json').read_text())
outer=json.loads(Path('/workspace/van-mt5-pending-receipt-sql-r1-process-20261028.json').read_text())
assert r['exit']==outer['exit']==0 and r['cleaned'] and r['owned_fixture_independently_absent']
assert not json.loads((run/'storage-audit.json').read_text())['forbidden_events']
assert all(hashlib.sha256((root/p).read_bytes()).hexdigest()==h for p,h in r['source_sha256'].items())
cases=E.parse(run/'full-trading.xml').findall('.//testcase')
assert cases and all(all(t.find(k) is None for k in ['failure','error','skipped']) for t in cases)
calls=[json.loads(l) for l in (run/'test-events.jsonl').read_text().splitlines() if json.loads(l)['phase']=='call']
assert len(calls)==len(cases) and all(c['outcome']=='passed' for c in calls)
assert all(n==1 for n in collections.Counter(c['nodeid'] for c in calls).values())
raw=root/'docs/rebuild/rev118/ci/mt5_pending_receipts_20261028';assert not raw.exists();raw.mkdir(parents=True)
def copy(src,rel):
 src=Path(src);dest=raw/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest);assert src.read_bytes()==dest.read_bytes()
for p in run.iterdir():
 if p.is_file():copy(p,'sql_r1/'+p.name)
copy('/workspace/van-mt5-pending-receipt-sql-r1-20261028.py','sql_r1/controller.py')
copy('/workspace/van-mt5-pending-receipt-sql-r1-process-20261028.json','sql_r1/outer-process.json')
for stem in ['before','r1','r2']:
 for suffix in ['.log','.xml','.json','-audit.json']:
  p=Path('/workspace/van-mt5-pending-receipt-'+stem+'-20261028'+suffix)
  if p.exists():copy(p,'focused/'+p.name)
expiry=json.loads(Path('/workspace/van-mt5-pending-receipt-expiry-readback-20261028.json').read_text())
assert len(expiry['checks'])==8 and all(c['passed'] for c in expiry['checks'])
assert json.loads(Path('/workspace/van-mt5-pending-receipt-expiry-process-20261028.json').read_text())['exit']==0
assert all(hashlib.sha256((root/p).read_bytes()).hexdigest()==h for p,h in expiry['source_sha256'].items())
for suffix in ['.py','.json']:copy('/workspace/van-mt5-pending-receipt-expiry-readback-20261028'+suffix,'explicit_expiry/readback'+suffix)
for suffix in ['.json','.log']:copy('/workspace/van-mt5-pending-receipt-expiry-process-20261028'+suffix,'explicit_expiry/process'+suffix)
for n in ['scope-check','owner-registry','frontend-registry','mutation-consistency','consolidation']:
 p=Path('/workspace/van-mt5-pending-receipt-'+n+'-20261028.json');assert json.loads(p.read_text())['exit']==0
 for ext in ['.json','.log']:copy(p.with_suffix(ext),'guards/'+p.with_suffix(ext).name)
for n in ['wip1','wip2']:
 for ext in ['.zip','.json']:copy('/workspace/van-mt5-pending-receipt-'+n+'-20261028'+ext,'source_recovery/'+n+ext)
copy('/workspace/van-mt5-final-cash-margin-publication-20261028.json','published_parent/publication.json')
copy('/workspace/van-37327981-source-evidence-readback-20261028.json','published_parent/source-readback.json')
native=Path('/workspace/van-37327981-native-mql-20261028');proof=json.loads((native/'verified-evidence.json').read_text())
ea='deploy/van-trading-core/mql5/VanBridgeEA.mq5'
assert proof['source_sha256']==hashlib.sha256((root/ea).read_bytes()).hexdigest()
assert subprocess.check_output(['git','show',base+':'+ea],cwd=root)==(root/ea).read_bytes()
assert proof['requested_head']==base
assert subprocess.check_output(['git','rev-parse',base+':'+ea],cwd=root,text=True).strip()==proof['source_blob_oid']
archive=(native/'original-12817329530.zip').read_bytes()
assert len(archive)==proof['original_archive_bytes'] and hashlib.sha256(archive).hexdigest()==proof['original_archive_sha256']
for case in proof['compile_cases']:
 assert hashlib.sha256((native/'extracted'/(case['name']+'.log')).read_bytes()).hexdigest()==case['log_sha256']
 if case['expected_success']:
  assert case['errors']==case['warnings']==0 and case['fresh_binary']
  assert hashlib.sha256((native/'extracted'/(case['name']+'.ex5')).read_bytes()).hexdigest()==case['binary_sha256']
 else:assert case['errors']>0 and not case['fresh_binary'] and not (native/'extracted'/(case['name']+'.ex5')).exists()
for p in native.rglob('*'):
 if p.is_file():copy(p,'published_parent_native_compiler/'+str(p.relative_to(native)))
copy('/workspace/van-37327981-selected-hosted-20261028/original-postgres-job.log','published_parent_hosted/original-postgres-job.log')
copy('/workspace/van-37327981-selected-hosted-20261028/log-evidence.json','published_parent_hosted/log-evidence.json')
for name in ['van-37327981-selected-hosted-process-20261028.json','van-37327981-selected-hosted-process-20261028.log','van-37327981-selected-hosted-verify-20261028.py']:
 copy('/workspace/'+name,'published_parent_hosted/artifact_download_attempt/'+name)
copy('/workspace/van-37327981-selected-hosted-20261028/download-r1.raw','published_parent_hosted/artifact_download_attempt/returned_metadata.json')
# No original tests changed or disappeared. The C++ fixture adds one scenario;
# actual production EA bytes are unchanged and remain independently compiled.
names=subprocess.check_output(['git','diff','--name-only',base],cwd=root,text=True).splitlines()
assert not any(p.startswith('trading/tests/') and p.endswith('.py') for p in names)
preserved=0
for p in (root/'trading/tests').rglob('test_*.py'):
 rel=str(p.relative_to(root));before=subprocess.run(['git','show',base+':'+rel],cwd=root,capture_output=True)
 if before.returncode:continue
 old=ast.parse(before.stdout);new=ast.parse(p.read_bytes())
 a={n.name:ast.dump(n) for n in ast.walk(old) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name.startswith('test_')}
 b={n.name:ast.dump(n) for n in ast.walk(new) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name.startswith('test_')}
 assert all(b.get(k)==v for k,v in a.items()),rel
 preserved+=len(a)
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
summary=(f'Actual native EA PLACED acknowledgments now remain ACCEPTED with the exact uint64 native order ID, zero filled quantity, no invented average fill or position, and only explicitly confirmed protection. Missing or invalid broker clocks remain unknown. Contradictory pending acknowledgments retain UNKNOWN and require original reconciliation. Submit independently reads the original durable SQL claim/result; timeout, stale account availability and replay cannot create a new claim or renew its completion. Valid original completion clocks and receipt hashes survive duplicate results, reopen and historical recovery. Corrupt/unavailable completion clocks withhold local receipt availability without erasing a known effect. Existing supported entry types remain MARKET; no new entry permission or native execution is added. Final full source qualification:{len(cases)}passed0skip/fail/error/audit,actualinner/outerexit0,everycallonce,all{len(r["source_sha256"])}inputhashesmatch,ownedPostgreSQLindependentlyabsent. {preserved} original test functions retain identical AST.0formal/native/production/S24acceptancesissued.')
rel='receipts/MT5_PENDING_RECEIPTS_SOURCE_20261028.json'
receipt={'schema':'van.rev118.mt5-pending-receipts-source/1','source_parent':base,'observed_at_utc':now,'implementation':summary,
 'source_files_sha256':{p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in ['trading/vati/execution/mt5_pull.py','trading/tests/mql_terminal_fixture.cpp','trading/tests/test_mt5_pending_receipts.py']},
 'source_result':{'actual_inner_exit':0,'actual_outer_exit':0,'passed':len(cases),'skipped':0,'failures':0,'errors':0,'audit_violations':0,'unique_calls_once':len(calls),'pinned_inputs_matched':len(r['source_sha256']),'original_test_functions_AST_preserved':preserved,'owned_postgres_independently_absent':True,'raw':'ci/mt5_pending_receipts_20261028/sql_r1'},
 'additional_explicit_expiry_readback':{'checks_passed':8,'actual_exit':0,'source_hashes_match':True,'new_native_effects':False,'scope':'Actual bounded native claims, first completion, database reopen and unchanged result/hash after command expiry; all six terminal statuses plus QUEUED/TAKEN uncertainty.'},
 'retained_failures':['Baseline actualexit1:2 actual EA ACCEPTED responses misclassified UNKNOWN.','Focusedr1 actualexit1:105passed1failed; reopened test adapter omitted original physical-account binding. Exact binding restored in fixture; production identity matching unchanged.','Parent selected artifact download actualexit1: advertised ZIP URL returned695-byte JSON artifact metadata instead of192716-byte ZIP. Rejected by byte-size check before extraction. Repeated supported download returned the same metadata; direct approved GitHub archive request was403. Original job logs are separately observed; no original JUnit archive verification claimed.'],
 'published_parent_evidence':{'head':base,'source_tests_passed':5215,'committed_ledger':'GREEN191','native_compiler':'SOURCE_COMPILED_0_ERRORS_0_WARNINGS_EXACT_UNCHANGED_EA','native_proof':'ci/mt5_pending_receipts_20261028/published_parent_native_compiler/verified-evidence.json','hosted_job_log':{'run':40692934675,'job':122832127397,'trading_passed':4987,'trading_declared_private_DDS_skips':1,'postgres_passed':26,'voice_passed':117,'original_JUnit_archive_verified':False},'main_CI':'IN_PROGRESS_AT_OBSERVATION_TWO_MANDATORY_FAILURES','mandatory_failure_reasons':['DDS_CONTRACT_READ_DEPLOY_KEY unprovisioned','trusted main8eb18898 lacks tools/ci/project_truth_ledger.py']},
 'source_authorizations':['auth-20261022-owner-autonomous-candidate-build'],'formal_acceptances_issued':0,
 'limitations':['The exact production EA functions execute through an explicit C++ terminal API model. Actual MetaEditor compilation is separately verified for unchanged parent source, not an owner-connected terminal or provider acceptance.','ACCEPTED is a pending effect, never a fill, cash settlement, verified native stop execution, reservation release or renewed financial authority. Full working-order/partial-fill/cancel reconciliation and economic finality remain required.','Corrupt or missing completion clocks retain a known native effect with received_time_unix_ms=None; consumers must reconcile. No fabricated availability timestamp repairs missing source facts.','Shared all-origin transactional cash/margin/stop-risk reservations, post-entry margin floors, fee/fill contingencies, qualified FX/contracts and active-policy arbitration remain open.','Every remaining backend/forecast/learning/crypto/assistant/operations and Android requirement remains required. Profitability is evidence-based, never guaranteed.'],
 'next':'Genuine hooks, mandatory committed verification against4fd466de, normal push and independent exact remote readback, exact-head hosted checks. Continue shared financial reservations and complete native working-order/economic reconciliation under original financial owners; retain full backend-to-Android programme.'}
(root/'docs/rebuild/rev118'/rel).write_text(json.dumps(receipt,indent=2)+'\n')
for name in ['EXECUTION_LEDGER.json','CANDIDATE_SOURCE_PROGRESS.json']:
 p=root/'docs/rebuild/rev118'/name;v=json.loads(p.read_text());v['updated_at_utc']=now
 if name=='EXECUTION_LEDGER.json':
  v['observations'].append(summary);v['current_action']=receipt['next']
  for uid in ['BE-003','BE-009','BE-010']:v['units'][uid]['evidence'].append(rel)
 else:
  for uid in ['BE-003','BE-009','BE-010']:v['units'][uid]['milestones'].append({'description':summary,'evidence':rel})
 p.write_text(json.dumps(v,indent=2)+'\n')
(root/'docs/rebuild/rev118/backend/BE-009_010_MT5_PENDING_RECEIPTS.md').write_text('# Original MT5 pending acknowledgments and completion readback\n\nCandidate source only; no full-unit, native account, production or device acceptance.\n\n'+summary+'\n\nRead [the exact source receipt](../'+rel+') and original failure evidence. The signed poll/SQLite path and original EA PLACED response run in source tests; C++ API model output is not connected MetaTrader execution. Protection is confirmed only by the explicit original native boolean. A pending acknowledgment never becomes a fill or a new financial grant. Current supported entry types remain MARKET.\n\nThe original373 parent has independently verified official MetaEditor compilation with zero errors/warnings, and this packet changes no EA bytes. Hosted parent job logs report4,987 trading passes/one declared private-DDS skip,26 PostgreSQL passes and117 voice passes. The selected JUnit archive could not be independently verified because the download tool returned JSON metadata under a ZIP declaration; that attempt remains failed. Mandatory source CI prerequisites remain failed and admission gates stay unissued.\n\nComplete shared all-origin financial reservations, fee/fill contingencies, post-entry margin floor, current-policy arbitration, native working-order/partial-fill/cancel reconciliation and economic finality. All feed, forecast, learning, crypto, assistant, operations and Android obligations remain. Provision Android through its production profile on Van trading core; actual signing and Artemis/Samsung S24 qualification remain separate. No frontend redesign before BG-001.\n')
for name in ['CONTINUATION_20261022.md','BUILD_EXECUTION_PLAN.md']:
 p=root/'docs/rebuild/rev118'/name
 text=p.read_text()
 latest='Published parent37327981 completed genuine hooks, committed GREEN191 against the required baseline, normal push and independent remote readback. Its5215 source cases passed, and exact unchanged EA source independently compiled under official MetaEditor with zero errors/warnings. The two mandatory CI prerequisites remain failed: missing DDS read key and trusted-main ledger checker. Source compilation is separate from native-account/provider qualification.\n\n'+summary+'\n\n[Source receipt]('+rel+'). Eight additional real-SQL checks retain original results and hashes after explicit command expiry; queued and taken claims remain uncertain without a second claim. '+receipt['next']+' No entire-unit or independent acceptance is issued.\n\nComplete shared all-origin transactional cash/margin/stop-risk reservations, post-entry margin floors, fee/fill contingencies, current-policy arbitration, native working-order/partial-fill/cancel reconciliation and economic finality. Complete all discovery/aliases/subscriptions/bars/gaps/depth/entitlements and native valuation/migration, payment/manual-trade/handover workflows, and every forecast, learning, crypto, assistant, security, operations and Android obligation. Profitability needs evidence. Android must use its provisioned production profile on Van trading core; signing and actual Artemis/Samsung S24 acceptance remain required. Preserve BG-001 and all original acceptance dependencies.\n'
 if name=='BUILD_EXECUTION_PLAN.md':
  start=text.index('## Current concrete gap and next result');end=text.index('## Commands and evidence economy',start)
  text=text[:start]+'## Current concrete gap and next result\n\n'+latest+'\n'+text[end:]
 else:text+='\n\n## Original pending acknowledgment and durable readback —28October\n\n'+latest
 p.write_text(text)
copy(__file__,'evidence-builder.py')
print(json.dumps({'passed':len(cases),'pinned_inputs':len(r['source_sha256']),'original_test_functions_AST_preserved':preserved,'raw_files':sum(p.is_file() for p in raw.rglob('*')),'receipt':rel}))
