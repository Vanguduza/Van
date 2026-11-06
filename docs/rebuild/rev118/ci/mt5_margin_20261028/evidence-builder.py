from pathlib import Path
import collections,datetime,hashlib,json,shutil,subprocess,xml.etree.ElementTree as E

root=Path('/workspace/van-review-2026-10-18/publish');raw=root/'docs/rebuild/rev118/ci/mt5_margin_20261028'
assert not raw.exists();raw.mkdir(parents=True)
base=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip();assert base=='9c19f375988fe2bace6f234f0b459510718e9de4'
run=Path('/workspace/van-mt5-margin-sql-r1-20261028');r=json.loads((run/'receipt.json').read_text())
outer=json.loads(Path('/workspace/van-mt5-margin-sql-r1-process-20261028.json').read_text())
assert r['exit']==outer['exit']==0 and r['cleaned'] and r['owned_fixture_independently_absent']
assert not json.loads((run/'storage-audit.json').read_text())['forbidden_events']
assert all(hashlib.sha256((root/f).read_bytes()).hexdigest()==h for f,h in r['source_sha256'].items())
cases=E.parse(run/'full-trading.xml').findall('.//testcase');assert len(cases)==1050
assert all(c.find('failure') is c.find('error') is c.find('skipped') is None for c in cases)
calls=[json.loads(l)['nodeid'] for l in (run/'test-events.jsonl').read_text().splitlines() if json.loads(l)['phase']=='call']
assert len(calls)==1050 and all(n==1 for n in collections.Counter(calls).values())
def copy(src,rel):
 src=Path(src);dest=raw/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest);assert src.read_bytes()==dest.read_bytes()
for p in run.iterdir():
 if p.is_file():copy(p,'sql_final/'+p.name)
copy('/workspace/van-mt5-margin-sql-r1-20261028.py','sql_final/controller.py')
copy('/workspace/van-mt5-margin-sql-r1-process-20261028.json','sql_final/outer-process.json')
for stem in ['van-mt5-margin-adapter-r1-20261028','van-mt5-margin-shared-book-r1-20261028']:
 for ext in ['.log','.xml','.json']:copy('/workspace/'+stem+ext,'failed_decoder/'+stem+ext)
for name in ['van-mt5-margin-wip-20261028.zip','van-mt5-margin-wip-20261028.json']:copy('/workspace/'+name,'source_recovery/'+name)
for stem in ['owner-registry','scope-check','mutation-consistency','frontend-registry','consolidation']:
 name='van-mt5-margin-'+stem+'-20261028';assert json.loads(Path('/workspace/'+name+'.json').read_text())['exit']==0
 for ext in ['.log','.json']:copy('/workspace/'+name+ext,'guards/'+name+ext)
paths=[s[3:] for s in subprocess.check_output(['git','status','--porcelain=v1'],cwd=root,text=True).splitlines()]
files=[p for p in paths if p.startswith(('trading/','deploy/van-trading-core/'))];assert len(files)==12
hashes={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in files}
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
summary=('Both MT5 source transports now implement original price/side/quantity-bound isolated-margin reads. Signed Windows worker validates native increments, representable inputs, original account/model/precision and unchanged deadline before/after SDK read; missing/invalid values never become zero. EA source adds capability-bound identity/18-field expiry framing, original binary64 metadata and UTC-second uncertainty, with no order_check/send effect. Actual signed HTTP/queue plus public-adapter/SQL readback paths execute on explicit SDK/EA source fixtures. Original native request nonce or queue ID is retained. Shared NativeMarginBook independently binds the existing risk-input account context, supports restart/expired historical data and lost storage ACK without native requery, and keeps reservation_amountNone/authorityFalse. Final1050actualsourceSQLitePostgreSQLHTTP/protocol/recovery/protection cases pass0skip/audit0;1050unique calls once/all1218pinnedPython-and-deploy-EA hashes match/ownedPG independently absent. Focused144 overlap. Initial51PASS/1decoder-exception-contractFAIL and110PASS/1sameFAIL remain recorded; invalid scope was already refused and the pure decoder now consistently raises ValueError. Native MetaEditor compilation of the modified EA is PENDING until exact-head hosted source job; actual Windows SDK/terminal/provider qualification and deployment NOT_ISSUED. This isolated estimate excludes existing positions/pending orders and does not replace all-origin reservations, current active-policy arbitration, native finality, settlement or the complete canonical backend/Android programme.0formal/native/production/S24acceptance.')
receipt={'schema':'van.rev118.mt5-original-margin-source/1','source_parent':base,'observed_at_utc':now,'source_files_sha256':hashes,'implementation':summary,'source_result':{'actual_outer_exit':0,'actual_inner_exit':0,'passed':1050,'skipped':0,'audit_violations':0,'unique_call_identities_once':1050,'pinned_source_inputs_matched':1218,'includes_actual_deploy_worker_py_and_EA_mq5':True,'owned_postgres_independently_absent':True,'raw':'ci/mt5_margin_20261028/sql_final'},'failed_attempts':[{'passed':51,'failed':1,'reason':'Scope was refused with VenueUnavailable; pure decoder exception contract normalized to ValueError.'},{'passed':110,'failed':1,'same_unique_failure':True}],'native_MetaEditor_compilation':'PENDING_EXACT_HEAD_HOSTED_JOB','native_SDK_terminal_provider_qualification':'NOT_ISSUED','formal_acceptances_issued':0,'source_authorizations':['auth-20261022-owner-autonomous-candidate-build','auth-20261023-owner-native-worker-source'],'limitations':['Native SDK and EA calculations were explicit source fixtures in Linux tests, not real terminal execution','Native compile success must be independently read for this exact modified EA source; parent MQL passes do not qualify it','Original exact native estimate is not additional portfolio margin, admitted reservation, settlement or a current grant','Declared precision remains explicit; no invented spendable rounding or conversion','Python storage audit is not an OS sandbox'],'next':'Genuine hooks/required-baseline committed verify/normalpush/remote readback/exactCI and actual MetaEditor source compilation; then all-origin reservations/current active-policy reconciliation/native finality and remaining canonical backend work.'}
rel='receipts/MT5_ORIGINAL_MARGIN_SOURCE_20261028.json';(root/'docs/rebuild/rev118'/rel).write_text(json.dumps(receipt,indent=2)+'\n')
for name in ['EXECUTION_LEDGER.json','CANDIDATE_SOURCE_PROGRESS.json']:
 p=root/'docs/rebuild/rev118'/name;v=json.loads(p.read_text());v['updated_at_utc']=now
 if name=='EXECUTION_LEDGER.json':
  v['observations'].append(summary);v['current_action']=receipt['next']
  for uid in ['BE-006','BE-009','BE-010']:v['units'][uid]['evidence'].append(rel)
 else:
  for uid in ['BE-006','BE-009','BE-010']:v['units'][uid]['milestones'].append({'description':summary,'evidence':rel})
 p.write_text(json.dumps(v,indent=2)+'\n')
(root/'docs/rebuild/rev118/backend/BE-009_010_MT5_ORIGINAL_MARGIN.md').write_text('# Original MT5 prospective-margin read workflows\n\nCandidate source for BE-006/009/010; no full-unit or reservation admission.\n\n'+summary+'\n\nThe existing signed worker, authenticated EA poll server, native queue, public adapters and SQL observation book retain their original owners. Both source paths preserve original product/side/quantity/price/account identity and expiry; actual native model changes, unsupported legacy capability, missing precision, stale/foreign replies and unknown reads refuse explicitly. Zero is retained only when the original native fixture actually reported it. Read operations remain distinct from native entry claims and work with existing entry-halt controls.\n\nThe EA preserves original 17-digit native double text and reports its UTC-second interval; the receiver reconstructs the same native double for decimal increment validation while retaining the original raw source. No financial sizing uses a binary float or a guessed settlement quantum. The SQL owner preserves the original source request identity and account context across reopen, namespace isolation, expiry and lost ACK; no native read is repeated to recover a stored receipt.\n\nSee [receipt](../'+rel+') and original raw evidence in `../ci/mt5_margin_20261028/`. The1050-case selection includes actual SQLite/PostgreSQL and signed HTTP/queue/worker paths over explicit SDK/EA fixtures. Source compiler evidence remains pending the exact modified EA hosted job; real terminal, provider, deployment and economic behavior are separate qualifications. The successful parent compiler job does not qualify these source bytes.\n\nShared all-origin reservations, active policy/mandate arbitration, pending/partial/uncertain exposure, actual native fill/cancel/finality release, payment approval through settlement/compensation and every remaining canonical backend/forecast/assistant/operations/Android obligation remain open. No source reader replaces those required effects.\n')
copy(__file__,'evidence-builder.py')
print(json.dumps({'source_files':len(files),'raw_files':sum(p.is_file() for p in raw.rglob('*')),'passed':1050,'receipt':rel}))
