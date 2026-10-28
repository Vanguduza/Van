from pathlib import Path
import collections,datetime,hashlib,json,shutil,subprocess,xml.etree.ElementTree as E

root=Path('/workspace/van-review-2026-10-18/publish')
raw=root/'docs/rebuild/rev118/ci/pending_current_contract_20261028'
assert not raw.exists();raw.mkdir(parents=True)
base=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
assert base=='eac4761f34c2c966ccc57578d7a8865695b40cf7'
run=Path('/workspace/van-pending-current-contract-sql-r2-20261028')
r=json.loads((run/'receipt.json').read_text())
outer=json.loads(Path('/workspace/van-pending-current-contract-sql-r2-process-20261028.json').read_text())
assert r['exit']==outer['exit']==0 and r['cleaned'] and r['owned_fixture_independently_absent']
assert not json.loads((run/'storage-audit.json').read_text())['forbidden_events']
assert all(hashlib.sha256((root/f).read_bytes()).hexdigest()==h for f,h in r['source_sha256'].items())
cases=E.parse(run/'full-trading.xml').findall('.//testcase')
assert cases and all(c.find('failure') is c.find('error') is c.find('skipped') is None for c in cases)
calls=[json.loads(l) for l in (run/'test-events.jsonl').read_text().splitlines() if json.loads(l)['phase']=='call']
assert len(calls)==len(cases) and all(n==1 for n in collections.Counter(c['nodeid'] for c in calls).values())
assert all(c['outcome']=='passed' for c in calls)
def copy(src,rel):
    src=Path(src);dest=raw/rel;dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(src,dest);assert src.read_bytes()==dest.read_bytes()
for p in run.iterdir():
    if p.is_file():copy(p,'sql_final/'+p.name)
copy('/workspace/van-pending-current-contract-sql-r2-20261028.py','sql_final/controller.py')
copy('/workspace/van-pending-current-contract-sql-r2-process-20261028.json','sql_final/outer-process.json')
for stem in ['baseline','parent-baseline-r2','parent-golden-r3','focused-r1','focused-r2','focused-r3','focused-r4','focused-r5','focused-r6']:
    name='van-pending-current-contract-'+stem+'-20261028'
    for suffix in ['.log','.xml','.json','-audit.json']:
        p=Path('/workspace/'+name+suffix)
        if p.exists():copy(p,'prior_attempts/'+p.name)
failed=Path('/workspace/van-pending-current-contract-sql-r1-20261028')
for p in failed.iterdir():
    if p.is_file():copy(p,'failed_collection/'+p.name)
copy('/workspace/van-pending-current-contract-sql-r1-20261028.py','failed_collection/controller.py')
copy('/workspace/van-pending-current-contract-sql-r1-process-20261028.json','failed_collection/outer-process.json')
for stem in ['owner-registry','scope-check','mutation-consistency','frontend-registry','consolidation']:
    name='van-pending-current-contract-'+stem+'-20261028'
    assert json.loads(Path('/workspace/'+name+'.json').read_text())['exit']==0
    for ext in ['.log','.json']:copy('/workspace/'+name+ext,'guards/'+name+ext)
for number in [1,2,3]:
    copy('/workspace/van-pending-current-contract-wip'+str(number)+'-20261028.zip',
         'source_recovery/wip'+str(number)+'.zip')
copy('/workspace/van-pending-current-contract-wip3-20261028.json','source_recovery/wip3.json')
parent=Path('/workspace/van-pending-current-contract-parent-runtime-20261028')
for name in ['original.tar','source-manifest.json']:copy(parent/name,'exact_parent_runtime/'+name)
copy('/workspace/van_parent_pending_capture.py','exact_parent_runtime/van_parent_pending_capture.py')
copy('/workspace/van-pending-current-contract-parent-bodies-20261028.jsonl','exact_parent_runtime/original-bodies.jsonl')
native=Path('/workspace/van-eac4761f-native-mql-20261028')
for p in native.rglob('*'):
    if p.is_file():copy(p,'published_parent_native_compile/'+str(p.relative_to(native)))
hosted=Path('/workspace/van-eac4761f-selected-hosted-20261028')
for p in hosted.rglob('*'):
    if p.is_file():copy(p,'published_parent_selected_hosted/'+str(p.relative_to(hosted)))
paths=subprocess.check_output(['git','diff','--name-only'],cwd=root,text=True).splitlines()
paths+=subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=root,text=True).splitlines()
source=sorted(p for p in paths if p.startswith(('trading/','tests/')))
hashes={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in source}
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
summary=(f'Both actual native snapshot owners now retain original pending contract terms and separate current risk-owner supplied valuation terms. Exact pending loss uses the larger original/current loss without reducing original commitments. Missing current symbol terms or changed instrument/currency/unit/model hold new risk; independent protection retains its owner. Incremental cached histories revalue on each snapshot without another financial event/full scan. Four actual counterexamples on an independently exported exact eac4761f runtime approved while current heat/currency risk exceeded its signed limit; all four now refuse at their correct original gates. Original parent snapshots/decisions retain exact serialized bodies and hashes, but original-only valuation cannot authorize current risk. Full trading plus selected backend HTTP recovery/schema/scope checks: {len(cases)} passes,0 skips/failures/audit violations,every call once,all{len(r["source_sha256"])} pinned inputs match,owned PostgreSQL independently absent.110 focused checks overlap.0formal/native/production/S24 acceptance issued.')
receipt={'schema':'van.rev118.pending-current-owner-contract-source/1','source_parent':base,
    'observed_at_utc':now,'source_files_sha256':hashes,'implementation':summary,
    'source_result':{'actual_outer_exit':0,'actual_inner_exit':0,'passed':len(cases),'skipped':0,
        'audit_violations':0,'unique_call_identities_once':len(calls),
        'pinned_source_inputs_matched':len(r['source_sha256']),
        'owned_postgres_independently_absent':True,'raw':'ci/pending_current_contract_20261028/sql_final'},
    'original_counterexamples':{'original_commit':base,'source_export_manifest':'ci/pending_current_contract_20261028/exact_parent_runtime/source-manifest.json',
        'actual_original_approvals':4,'actual_original_assertion_failures':4,
        'original_snapshot_bodies_and_hashes':4,'original_module_hashes_independently_matched':True},
    'retained_failed_attempts':[
        'Initial two actual approvals retained; initial expected PORTFOLIO_HEAT tag was corrected to the actual signed currency-limit violation and separate valid heat-limit cases were added.',
        'Focused r1:94 passes/2 incorrect expected gate tags. Focused r2/r3:96 passes/2 new fixture failures from invalid fraction1 and then platform ceiling0.5; fixtures corrected to the existing signed ceiling0.0400.',
        'Focused r5 and full SQL r1 failed collection because new test imported recompute_decision_hash from the wrong module; import corrected to existing execution router. No functional assertion ran in those collection failures. Original owned PG cleanup independently verified.',
        'Exact parent baseline r2 and golden capture r3 each retain4 genuine incorrect original approvals; these are expected failed counterexamples, not passing implementation tests.'],
    'native_parent':json.loads((native/'verified-evidence.json').read_text()),
    'selected_hosted_parent':json.loads((hosted/'verified-evidence.json').read_text()),
    'formal_acceptances_issued':0,'source_authorizations':['auth-20261022-owner-autonomous-candidate-build'],
    'limitations':[
        'These are the existing risk-owner supplied current terms; actual native refresh, timestamped FX conversion, authoritative contract migration and venue qualification remain separate BE-008 obligations.',
        'The original floor is not automatically released on a lower supplied valuation; release needs its separately qualified reconciliation owner.',
        'This is stop-risk valuation, not shared transactional cash/margin reservation, native fee/economic finality or financial authority.',
        'Active signed policy arbitration, all-origin payment/manual commitments and complete working-order workflows remain open.',
        'Source tests use explicit provider fixtures. Python storage audit is not an OS sandbox.'],
    'next':'Genuine hooks, committed required-baseline verify, normal push, exact remote and hosted readback; continue actual native valuation/reservation/current-policy prerequisites under the complete frozen programme.'}
rel='receipts/PENDING_CURRENT_CONTRACT_SOURCE_20261028.json'
(root/'docs/rebuild/rev118'/rel).write_text(json.dumps(receipt,indent=2)+'\n')
for name in ['EXECUTION_LEDGER.json','CANDIDATE_SOURCE_PROGRESS.json']:
    p=root/'docs/rebuild/rev118'/name;v=json.loads(p.read_text());v['updated_at_utc']=now
    if name=='EXECUTION_LEDGER.json':
        v['observations'].append(summary);v['current_action']=receipt['next']
        for uid in ['BE-008','BE-009','BE-010']:v['units'][uid]['evidence'].append(rel)
    else:
        for uid in ['BE-008','BE-009','BE-010']:v['units'][uid]['milestones'].append({'description':summary,'evidence':rel})
    p.write_text(json.dumps(v,indent=2)+'\n')
(root/'docs/rebuild/rev118/backend/BE-008_009_PENDING_CURRENT_CONTRACT.md').write_text(
    '# Original pending commitments and current risk-owner supplied terms\n\nCandidate source only; no unit/native/production acceptance.\n\n'+summary+
    '\n\nOriginal command/receipt identity and original contract remain immutable. A separate optional `valuation_contract` holds the current terms supplied by the existing snapshot owner. Both the original floor and current exact account-currency loss participate in the larger held amount. Partial-fill coverage, position slots and independently possible currency-leg fills retain their original source semantics.\n\nHistorical original-only bodies omit the new field, decode byte-for-byte and reproduce the actual original snapshot/decision hashes. They remain historical data. A current authority evaluation without current valuation refuses explicitly as `PENDING_VALUATION_UNAVAILABLE`; it cannot silently use old terms. A current instrument, monetary currency, contract-unit or loss-model change requires reconciliation.\n\nBoth native snapshot owners pass their existing symbol contracts to the common projection; cached original histories do not cache away a later current-term change. Unknown current terms hold new entries via the existing fence, while independent protection retains its owner. These supplied terms are not invented fresh native observations or timestamped conversions. Full native instrument/quote/conversion qualification remains open.\n\nRead the [source receipt](../'+rel+') and retained exact-parent/full SQL/HTTP/failed-attempt evidence. The parent native compiler retry is independently verified after its original installer-download failure; the failure remains recorded. Native compiler process codes are retained verbatim.\n\nContinue full native valuation inputs, qualified contract migration, shared transactional cash/margin reservations across every origin, current active-policy arbitration, working-order/partial-fill reconciliation and native economic finality. All remaining backend, forecast, assistant, operations and Android obligations remain attached to the frozen programme. This source projection does not replace those workflows.\n')
copy(__file__,'evidence-builder.py')
print(json.dumps({'source_files':len(source),'raw_files':sum(p.is_file() for p in raw.rglob('*')),'passed':len(cases),'receipt':rel}))
