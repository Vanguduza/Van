from pathlib import Path
import collections,datetime,hashlib,json,shutil,subprocess,xml.etree.ElementTree as ET

root=Path('/workspace/van-review-2026-10-18/publish')
raw=root/'docs/rebuild/rev118/ci/native_collateral_margin_20261028'
assert not raw.exists();raw.mkdir(parents=True)
base=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
assert base=='d156d943df32329c14c1abf147edebe7d6425820'
run=Path('/workspace/van-native-collateral-margin-sql-r2-20261028')
r=json.loads((run/'receipt.json').read_text());outer=json.loads(Path('/workspace/van-native-collateral-margin-sql-r2-process-20261028.json').read_text())
assert r['exit']==outer['exit']==0 and r['owned_fixture_independently_absent'] and r['cleaned']
assert not json.loads((run/'storage-audit.json').read_text())['forbidden_events']
assert all(hashlib.sha256((root/f).read_bytes()).hexdigest()==h for f,h in r['source_sha256'].items())
cases=ET.parse(run/'full-trading.xml').findall('.//testcase')
assert len(cases)==333 and all(c.find('failure') is c.find('error') is c.find('skipped') is None for c in cases)
calls=[json.loads(line)['nodeid'] for line in (run/'test-events.jsonl').read_text().splitlines() if json.loads(line)['phase']=='call']
assert len(calls)==333 and all(n==1 for n in collections.Counter(calls).values())
def copy(src,rel):
 src=Path(src);dest=raw/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)
 assert dest.read_bytes()==src.read_bytes()
for f in run.iterdir():
 if f.is_file():copy(f,'sql_final/'+f.name)
copy('/workspace/van-native-collateral-margin-sql-r2-20261028.py','sql_final/controller.py')
copy('/workspace/van-native-collateral-margin-sql-r2-process-20261028.json','sql_final/outer-process.json')
for stem in ['van-native-collateral-margin-sql-r1-20261028','van-native-margin-book-r1-20261028','van-native-margin-book-r3-20261028','van-physical-order-exposure-invalid-isolated-20261028']:
 p=Path('/workspace')/stem
 if p.is_dir():
  for name in ['full-trading.log','full-trading.xml','storage-audit.json','receipt.json']:
   if (p/name).is_file():copy(p/name,'failed/'+stem+'/'+name)
 else:
  for ext in ['.log','.xml','.json']:
   if p.with_suffix(ext).is_file():copy(p.with_suffix(ext),'failed/'+stem+p.with_suffix(ext).suffix)
host=Path('/workspace/van-d156d943-selected-hosted-20261028')
for name in ['original-12794822760.zip','download-receipt.json','verified-evidence.json']:copy(host/name,'published_parent/'+name)
for stem in ['van-collateral-margin-scope-check-20261028','van-collateral-margin-mutation-consistency-20261028','van-collateral-margin-frontend-registry-20261028']:
 for ext in ['.json','.log']:copy('/workspace/'+stem+ext,'guards/'+stem+ext)
paths=subprocess.check_output(['git','status','--porcelain=v1'],cwd=root,text=True).splitlines()
source=[line[3:] for line in paths if line[3:].startswith('trading/')]
assert len(source)==12
hashes={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in source}
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
summary=('Original native collateral now retains exact cash-backed bounds without borrowing credit-inclusive reported free margin. Original commands and receipts across aliases retain pending, partial, open, uncertain and proven-no-effect quantities; missing margin is never zero. The actual cTrader adapter reads pinned expected-margin protocol and a bounded SQL book captures original input/context/contract, exact native quantities and money scales with expiry inside the writer, replay, restart and independent readback. Current-price and GSL limitations remain explicit; no reservation/execution grant is issued. Final333 source/SQLite/PostgreSQL/protocol/recovery cases pass0skip/audit0;333unique callIDs once and1207pinnedPythonhashes match; ownedPG independently absent. Original failures retained, including native codec enum handling, missing-evidence PostgreSQL fixture expectation, nested-vs-outer ACK fixture and an incorrect module import. Published d156 artifact independently verifies4615tradingPASS/1declaredDDSskip,26PGPASS,117voicePASS; does not qualify these later changes. Shared reservations, active mandate/policy reconciliation, native finality, payment effects and all other canonical requirements remain open. No whole-unit/native/production/S24 acceptance.')
receipt={'schema':'van.rev118.native-collateral-margin-source/1','source_parent':base,'observed_at_utc':now,'source_files_sha256':hashes,'implementation':summary,'source_result':{'actual_outer_exit':0,'actual_inner_exit':0,'passed':333,'skipped':0,'audit_violations':0,'unique_call_identities_once':333,'pinned_python_inputs_matched':1207,'owned_postgres_independently_absent':True,'raw':'ci/native_collateral_margin_20261028/sql_final'},'failure_history':{'first_combined_SQL':{'passed':331,'failed':2},'initial_book_ACK_fixture':{'passed':42,'failed':1},'wrong_module_import':{'passed':37,'failed':20},'isolated_invalid_original_commands':{'failed_before_fix':4},'retained_as_failed':True},'published_parent_selected_artifact':json.loads((host/'verified-evidence.json').read_text()),'limitations':['Original source data/readback only; not reservation admission or a new financial authority','Native expected-margin protocol is current-price estimate without order price and excludes ACCORDING_TO_GSL','MT5 prospective margin and full quote freshness qualification remain open','Pending reader is cold/bounded-workflow data; not installed as a full-history scan on each trading tick','Python storage audit is not an OS sandbox','Frozen programme and all formal/native/production acceptances unchanged'],'formal_acceptances_issued':0,'next':'Complete all-origin shared reservation enforcement, including original policy/active mandate reconciliation and native settlement/release; continue canonical backend programme.'}
rel='receipts/NATIVE_COLLATERAL_MARGIN_SOURCE_20261028.json';(root/'docs/rebuild/rev118'/rel).write_text(json.dumps(receipt,indent=2)+'\n')
for name in ['EXECUTION_LEDGER.json','CANDIDATE_SOURCE_PROGRESS.json']:
 p=root/'docs/rebuild/rev118'/name;v=json.loads(p.read_text());v['updated_at_utc']=now
 if name=='EXECUTION_LEDGER.json':
  v['observations'].append(summary);v['current_action']=receipt['next']
  for uid in ['BE-006','BE-009','BE-010']:
   row=v['units'].setdefault(uid,{'status':'IN_PROGRESS','candidate_source_only':True,'acceptance':'NOT_ISSUED','evidence':[]});row['evidence'].append(rel)
 else:
  for uid in ['BE-006','BE-009','BE-010']:v['units'][uid]['milestones'].append({'description':summary,'evidence':rel})
 p.write_text(json.dumps(v,indent=2)+'\n')
doc=root/'docs/rebuild/rev118/backend/BE-009_NATIVE_COLLATERAL_MARGIN.md'
doc.write_text('# Original native collateral, pending exposure and margin readback\n\nCandidate source evidence for BE-006/009/010; no complete unit or reservation admission.\n\n'+summary+'\n\nThe collateral reader independently resolves the original sealed native risk input, keeps account-scoped Money identity and distinguishes measured, unmeasured and unavailable. Historical expiry never becomes a fresh grant. The order reader joins command and receipt seals, original approving input, causal availability and physical/monetary ownership. Missing ACKs, late/partial or conflicting evidence cannot release a commitment.\n\n`CtraderAdapter.expected_margin` uses the actual pinned protobuf codec contract and exact native volume steps, binds original symbol metadata and account deposit currency, and refuses reconnect, leverage/margin-semantic or deadline changes during I/O. `NativeMarginBook.capture` supplies the actual adapter-to-writer caller; original native account, metadata, request/response and source input survive SQL restart and independent readback. Quote expiry is rechecked inside the writer; lost storage acknowledgement is reconciled by the original source identity, without recapture or duplicate publication. These reads do not approve payment or execute trades.\n\nSee [source receipt](../'+rel+') and original raw evidence under `../ci/native_collateral_margin_20261028/`. The 333-case selection overlaps earlier native-input/funding/codec checks. The newly added PostgreSQL checks executed, without skip. Failed runs remain failed with their original oracles; the native codec enum representation was fixed in application source, while the missing-source namespace assertion now requires explicit refusal rather than an invented empty exposure.\n\nNext dependencies remain shared reservations across funding/orders/manual/handover, native future margin for every supported path, original active policy/grant reconciliation, native filled/cancel/finality/release, payment approval through settlement/compensation, and the complete unchanged backend programme. None is replaced by these source readers.\n')
copy(__file__,'evidence-builder.py')
print(json.dumps({'source_files':len(source),'raw_files':sum(p.is_file() for p in raw.rglob('*')),'receipt':rel,'passed':333}))
