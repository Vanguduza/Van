from pathlib import Path
import collections,datetime,hashlib,json,shutil,subprocess,xml.etree.ElementTree as E

root=Path('/workspace/van-review-2026-10-18/publish')
raw=root/'docs/rebuild/rev118/ci/physical_pending_risk_20261028'
assert not raw.exists();raw.mkdir(parents=True)
base=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
assert base=='42d8b386e61f2ea26730d4232cab494b3173320e'
run=Path('/workspace/van-physical-pending-risk-sql-r1-20261028')
r=json.loads((run/'receipt.json').read_text())
outer=json.loads(Path('/workspace/van-physical-pending-risk-sql-r1-process-20261028.json').read_text())
assert r['exit']==outer['exit']==0 and r['cleaned'] and r['owned_fixture_independently_absent']
assert not json.loads((run/'storage-audit.json').read_text())['forbidden_events']
assert all(hashlib.sha256((root/f).read_bytes()).hexdigest()==h for f,h in r['source_sha256'].items())
cases=E.parse(run/'full-trading.xml').findall('.//testcase')
assert cases and all(c.find('failure') is c.find('error') is None for c in cases)
skips=[{'name':c.attrib['name'],'reason':c.find('skipped').attrib} for c in cases if c.find('skipped') is not None]
assert len(skips)<=1,skips
passed=sum(c.find('skipped') is None for c in cases)
calls=[json.loads(l) for l in (run/'test-events.jsonl').read_text().splitlines() if json.loads(l)['phase']=='call']
assert len(calls)==passed and all(n==1 for n in collections.Counter(c['nodeid'] for c in calls).values())
assert all(c['outcome']=='passed' for c in calls)
def copy(src,rel):
    src=Path(src);dest=raw/rel;dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(src,dest);assert src.read_bytes()==dest.read_bytes()
for p in run.iterdir():
    if p.is_file():copy(p,'sql_final/'+p.name)
copy('/workspace/van-physical-pending-risk-sql-r1-20261028.py','sql_final/controller.py')
copy('/workspace/van-physical-pending-risk-sql-r1-process-20261028.json','sql_final/outer-process.json')
for stem in ['baseline','focused-r1','focused-r2','focused-r3','focused-r4']:
    name='van-physical-pending-risk-'+stem+'-20261028'
    for suffix in ['.log','.xml','.json','-audit.json']:
        p=Path('/workspace/'+name+suffix)
        if p.exists():copy(p,'prior_attempts/'+p.name)
for stem in ['owner-registry','scope-check','mutation-consistency','frontend-registry','consolidation']:
    name='van-physical-pending-risk-'+stem+'-20261028'
    assert json.loads(Path('/workspace/'+name+'.json').read_text())['exit']==0
    for ext in ['.log','.json']:copy('/workspace/'+name+ext,'guards/'+name+ext)
for name in ['van-physical-pending-risk-wip1-20261028.zip']:
    copy('/workspace/'+name,'source_recovery/'+name)
# Follow-up evidence retains original compilation and original CI failures.
native=Path('/workspace/van-42d8b386-native-mql-20261028')
for p in native.rglob('*'):
    if p.is_file():copy(p,'parent_native_compile/'+str(p.relative_to(native)))
hosted=Path('/workspace/van-42d8b386-selected-hosted-20261028')
for p in hosted.rglob('*'):
    if p.is_file():copy(p,'parent_selected_hosted/'+str(p.relative_to(hosted)))
source=subprocess.check_output(['git','diff','--name-only'],cwd=root,text=True).splitlines()
source+=subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=root,text=True).splitlines()
source=sorted(p for p in source if p.startswith(('trading/','tests/')))
hashes={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in source}
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
summary=(f'Both actual native snapshot owners now carry original all-alias possible-fill stop-risk commitments into the existing RiskAuthority portfolio heat, position-count and currency-leg limits. Original commands, sealed approving inputs and native receipt position IDs bind the data; missing positions do not imply cancellation. Partial native coverage is counted once; independent opposing pending fills cannot prematurely cancel currency risk. Protection and execution authority remain explicitly false. Original native no-effect or a source-bound fully-filled close with current position absence can release position stop risk, never fee/cash settlement. Cache uses incremental rows between financial changes, retains original availability cutoffs and SQL reopen/namespace semantics. Two actual owner counterexamples failed APPROVED before the fix. Full trading plus original backend HTTP recovery/schema/workmap qualification: {passed} actual passes, {len(skips)} declared skips, no failures or storage-audit violations; every call once and all {len(r["source_sha256"])} pinned input hashes match; owned PostgreSQL independently absent. Legacy snapshot bytes and hashes and the 27 original required schema fields remain intact. No formal unit/native/production/S24 acceptance issued.')
receipt={'schema':'van.rev118.physical-pending-stop-risk-source/1','source_parent':base,
    'observed_at_utc':now,'source_files_sha256':hashes,'implementation':summary,
    'source_result':{'actual_outer_exit':0,'actual_inner_exit':0,'passed':passed,'skipped':skips,
        'audit_violations':0,'unique_call_identities_once':len(calls),
        'pinned_source_inputs_matched':len(r['source_sha256']),
        'owned_postgres_independently_absent':True,'raw':'ci/physical_pending_risk_20261028/sql_final'},
    'retained_failed_attempts':[
        'Baseline: both actual snapshot owners approved a second alias while first alias pending exposure was omitted (2 assertion failures).',
        'Focused r2: new pending cases passed; legacy resting-position helper lost its existing behavior (2 assertion failures), restored without weakening its assertions.',
        'Focused r3: 123 passes, two schema/dataclass extension equality failures; declared optional field lists updated, every original required field preserved.',
        'Focused r4: 127 passes, three new limit-oracle fixture failures from inherited one-position default; fixture now supplies explicit independent position ceilings.'],
    'parent_hosted':json.loads((hosted/'verified-evidence.json').read_text()),
    'parent_native_compile':json.loads((native/'verified-evidence.json').read_text()),
    'parent_main_workflow':'40651126263 terminal FAILURE:17 public jobs SUCCESS; missing DDS read key and absent trusted-main checker retained as failures',
    'formal_acceptances_issued':0,'source_authorizations':['auth-20261022-owner-autonomous-candidate-build'],
    'limitations':[
        'Pending stop-risk projection is not a transactional collateral/cash/margin reservation or native permission.',
        'Current active-policy arbitration, all-origin payment/manual commitments and current contract/FX revaluation remain programme obligations.',
        'Own-alias working entries retain existing unresolved-entry reconciliation gates; this packet does not complete all multi-pending workflows.',
        'Close-based release affects position stop risk only; no native fee/economic-finality or cash settlement qualification is inferred.',
        'Paper resting-entry behavior remains compatible; full paper/account reservations remain in scope.',
        'Local provider observations are explicit fixtures. Python storage audit is not an OS sandbox.'],
    'next':'Genuine hooks, committed required-baseline verification, normal push and exact-head hosted evidence; then actual shared reservation and active-policy work under the frozen full-scope programme.'}
rel='receipts/PHYSICAL_PENDING_STOP_RISK_SOURCE_20261028.json'
(root/'docs/rebuild/rev118'/rel).write_text(json.dumps(receipt,indent=2)+'\n')
for name in ['EXECUTION_LEDGER.json','CANDIDATE_SOURCE_PROGRESS.json']:
    p=root/'docs/rebuild/rev118'/name;v=json.loads(p.read_text());v['updated_at_utc']=now
    if name=='EXECUTION_LEDGER.json':
        v['observations'].append(summary);v['current_action']=receipt['next']
        for uid in ['BE-006','BE-009','BE-010']:v['units'][uid]['evidence'].append(rel)
    else:
        for uid in ['BE-006','BE-009','BE-010']:v['units'][uid]['milestones'].append({'description':summary,'evidence':rel})
    p.write_text(json.dumps(v,indent=2)+'\n')
(root/'docs/rebuild/rev118/backend/BE-009_010_PHYSICAL_PENDING_RISK.md').write_text(
    '# Original all-alias pending stop risk\n\nCandidate source for BE-006/009/010. Unit acceptance is not issued.\n\n'+summary+
    '\n\nThe existing native-context, funding, ledger and physical risk-source gates run before pending projection. A projection failure holds new entries through the existing funding fence while independent protection retains its owner. Pending commitments remain separate from confirmed protected positions. Native positions retain actual broker IDs in the serialized risk input; original receipt IDs, symbol and direction establish partial coverage, with unknown or duplicate coverage held explicitly. Zero-effect release requires original native proof; local expiry or cancellation alone cannot release a possible fill.\n\nThe pure authority uses exact fractions and independently possible currency fill intervals. Source snapshots omit empty new fields and absent native position IDs, retaining original immutable legacy bytes and hashes. The existing legacy paper resting-position helper still exposes its original contract.\n\nRead the [source receipt](../'+rel+') and retained original raw evidence under `../ci/physical_pending_risk_20261028/`. The previous MT5 packet now has independently verified native MetaEditor compilation; its earlier pre-publication PENDING record remains historical. The official compiler emitted a fresh binary with zero errors/warnings, and rejected deliberately invalid source. Its reported process codes (positive1, rejection0) are retained verbatim. This does not qualify a provider account, deployment or financial effect.\n\nThe frozen programme still requires actual transactional shared risk/cash/margin reservations, current active-policy arbitration, current native contract/conversion revaluation, full working-order/partial-fill reconciliation, native fee/economic finality, payment/manual-trade/handover settlement and every remaining backend/forecast/assistant/operations/Android unit. A source read or generic refusal cannot replace those required workflows.\n')
copy(__file__,'evidence-builder.py')
print(json.dumps({'source_files':len(source),'raw_files':sum(p.is_file() for p in raw.rglob('*')),'passed':passed,'skips':skips,'receipt':rel}))
