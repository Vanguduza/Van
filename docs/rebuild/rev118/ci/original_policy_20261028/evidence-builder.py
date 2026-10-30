from pathlib import Path
import collections,datetime,hashlib,json,shutil,subprocess,xml.etree.ElementTree as E

root=Path('/workspace/van-review-2026-10-18/publish');raw=root/'docs/rebuild/rev118/ci/original_policy_20261028'
assert not raw.exists();raw.mkdir(parents=True)
base=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip();assert base=='e12ef22329700775e6111eb0bc1354ba84bb88ba'
run=Path('/workspace/van-original-policy-sql-r2-20261028');r=json.loads((run/'receipt.json').read_text())
outer=json.loads(Path('/workspace/van-original-policy-sql-r2-process-20261028.json').read_text())
assert r['exit']==outer['exit']==0 and r['cleaned'] and r['owned_fixture_independently_absent']
assert not json.loads((run/'storage-audit.json').read_text())['forbidden_events']
assert all(hashlib.sha256((root/f).read_bytes()).hexdigest()==h for f,h in r['source_sha256'].items())
cases=E.parse(run/'full-trading.xml').findall('.//testcase')
assert len(cases)==766 and all(c.find('failure') is c.find('error') is c.find('skipped') is None for c in cases)
calls=[json.loads(l)['nodeid'] for l in (run/'test-events.jsonl').read_text().splitlines() if json.loads(l)['phase']=='call']
assert len(calls)==766 and all(n==1 for n in collections.Counter(calls).values())
def copy(src,rel):
 src=Path(src);dest=raw/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest);assert src.read_bytes()==dest.read_bytes()
for p in run.iterdir():
 if p.is_file():copy(p,'sql_final/'+p.name)
copy('/workspace/van-original-policy-sql-r2-20261028.py','sql_final/controller.py')
copy('/workspace/van-original-policy-sql-r2-process-20261028.json','sql_final/outer-process.json')
old=Path('/workspace/van-original-policy-sql-r1-20261028')
for name in ['receipt.json','full-trading.log','full-trading.xml','storage-audit.json']:copy(old/name,'failed_sql/'+name)
for ext in ['.log','.xml','.json']:copy('/workspace/van-original-mandate-source-r2-20261028'+ext,'failed_temperament/attempt'+ext)
copy('/workspace/van-original-policy-wip-20261028.zip','failed_sql/original-five-file-source.zip')
copy('/workspace/van-original-policy-wip-20261028.json','failed_sql/original-five-file-source.json')
for stem in ['owner-registry','scope-check','mutation-consistency','frontend-registry','consolidation']:
 full='van-original-policy-'+stem+'-20261028'
 assert json.loads(Path('/workspace/'+full+'.json').read_text())['exit']==0
 for ext in ['.log','.json']:copy('/workspace/'+full+ext,'guards/'+full+ext)
parent=Path('/workspace/van-e12ef223-selected-hosted-20261028')
for name in ['original-12795254478.zip','verified-evidence.json']:copy(parent/name,'published_parent/'+name)
files=['trading/vati/risk/mandate_source.py','trading/vati/app/account_service.py','trading/vati/app/cycle.py','trading/tests/test_mandate_source.py','trading/tests/test_mandate_source_postgres.py']
hashes={f:hashlib.sha256((root/f).read_bytes()).hexdigest() for f in files}
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
summary=('Both existing risk producers now archive the actual effective mandate and original standing-signature/public-key evidence used by the real kernel. A separate temperament grant retains its exact signed raw input; normalization cannot substitute a different signature subject. Original readback independently checks policy/decision hashes, scope, lifetime and P256 signatures after SQL reopen or key rotation/removal/revocation, without re-admission. The result is immutable OriginalMandatePolicy data, not a TradingMandate or current grant. Legacy/invalid proof stays UNBOUND without dropping original native losses or history. Positive account approval and both original producer paths execute; no trade effect is issued by these readbacks. Final766actualsourceSQLitePostgreSQLHTTP/recovery/authority cases pass0skip/audit0;766unique callIDs once/all1210pinnedPythonhashes match/ownedPGabsent. The69focused checks overlap. Initial68PASS/1source-temperamentFAIL and764PASS/1PGfault-fixtureFAIL remain recorded, then corrected without weakening original assertions or owner controls. Published e12 original selected artifact independently verifies4708tradingPASS/1declaredDDSskip,26PGPASS,117voicePASS; four supporting workflowsSUCCESS, mainstillrunning with two independently confirmed mandatory admission failures. Full current active-policy arbitration, all-origin reservations, native finality, payment settlement and the entire unchanged programme remain open.0formal/native/production/S24acceptance.')
receipt={'schema':'van.rev118.original-mandate-policy-source/1','source_parent':base,'observed_at_utc':now,'source_files_sha256':hashes,'implementation':summary,'source_result':{'actual_outer_exit':0,'actual_inner_exit':0,'passed':766,'skipped':0,'audit_violations':0,'unique_call_identities_once':766,'pinned_python_inputs_matched':1210,'owned_postgres_independently_absent':True,'raw':'ci/original_policy_20261028/sql_final'},'focused_result':{'passed':69,'overlaps_final':True},'failed_attempts':[{'passed':68,'failed':1,'reason':'Original separately signed temperament raw input was absent from the first normalizing reader; source fixed.'},{'passed':764,'failed':1,'reason':'PG append does not invoke the public atomic hook; fault fixture now enters an actual outer transaction and loses its commit reply.'}],'published_parent':json.loads((parent/'verified-evidence.json').read_text()),'limitations':['Original signature data cannot admit a current mandate or policy','Unknown historical policy does not erase its native financial contributions','Source key fixtures are not owner production keys, provider/device evidence or deployment','Active/revoked policy arbitration and all-origin reservation enforcement remain open','Metadata size, capacity and complete native deployment require their own qualification','Python storage audit is not an OS sandbox'],'formal_acceptances_issued':0,'next':'Complete native prospective-margin coverage and all-origin reservation state, current active mandate/policy reconciliation and authoritative native finality/release; preserve all canonical backend and Android requirements.'}
rel='receipts/ORIGINAL_MANDATE_POLICY_SOURCE_20261028.json';(root/'docs/rebuild/rev118'/rel).write_text(json.dumps(receipt,indent=2)+'\n')
for name in ['EXECUTION_LEDGER.json','CANDIDATE_SOURCE_PROGRESS.json']:
 p=root/'docs/rebuild/rev118'/name;v=json.loads(p.read_text());v['updated_at_utc']=now
 if name=='EXECUTION_LEDGER.json':v['observations'].append(summary);v['units']['BE-009']['evidence'].append(rel);v['current_action']=receipt['next']
 else:v['units']['BE-009']['milestones'].append({'description':summary,'evidence':rel})
 p.write_text(json.dumps(v,indent=2)+'\n')
(root/'docs/rebuild/rev118/backend/BE-009_ORIGINAL_MANDATE_POLICY.md').write_text('# Original mandate policy evidence at the existing risk owners\n\nCandidate source work; no full unit or active-policy admission.\n\n'+summary+'\n\nThe live existing OwnerAuthority verifier supplies the actual standing key/token binding. Capture checks current key identity and the unchanged admitted effective policy. The original effective policy is independently bound to the real RiskDecision mandate hash. Each original separately scoped temperament signature retains the exact raw input that its existing owner signed. No authority record, owner key, certificate or new grant is issued.\n\nHistorical readback returns immutable data outside TradingMandate and without runtime key bindings. Rotation, revocation or expiry cannot rewrite an earlier decision; neither can that archived proof override current authority. Legacy or corrupt proofs stay unbound while the original native account history and financial losses remain. Both real producers and a positive account approval were executed over isolated native/source fixtures; PostgreSQL namespace/reopen and actual outer-commit acknowledgement loss were exercised.\n\nSee [receipt](../'+rel+') and original raw evidence under `../ci/original_policy_20261028/`. The current active-policy/account-wide reservation owner remains to be implemented; original policy data is not a substitute. Native finality, payment approval/reserve/send/settle/compensate, manual and handover reconciliation and all remaining canonical backend/forecast/assistant/operations/Android requirements remain open. Existing no-UI-before-BG-001 and provisioning/signing/S24 gates remain.\n')
copy(__file__,'evidence-builder.py')
print(json.dumps({'source_files':len(files),'raw_files':sum(p.is_file() for p in raw.rglob('*')),'passed':766,'receipt':rel}))
