from pathlib import Path
import collections,datetime,hashlib,json,shutil,subprocess,xml.etree.ElementTree as E

root=Path('/workspace/van-review-2026-10-18/publish')
base=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
assert base=='d3ef2cdb75e5d9888438e62ce1566771d25c7cd4'
run=Path('/workspace/van-mt5-symbol-contract-sql-r1-20261028')
r=json.loads((run/'receipt.json').read_text())
outer=json.loads(Path('/workspace/van-mt5-symbol-contract-sql-r1-process-20261028.json').read_text())
assert r['exit']==outer['exit']==0 and r['cleaned'] and r['owned_fixture_independently_absent']
assert not json.loads((run/'storage-audit.json').read_text())['forbidden_events']
assert all(hashlib.sha256((root/f).read_bytes()).hexdigest()==h for f,h in r['source_sha256'].items())
cases=E.parse(run/'full-trading.xml').findall('.//testcase')
assert cases and all(c.find('failure') is c.find('error') is c.find('skipped') is None for c in cases)
calls=[json.loads(l) for l in (run/'test-events.jsonl').read_text().splitlines() if json.loads(l)['phase']=='call']
assert len(calls)==len(cases) and all(n==1 for n in collections.Counter(c['nodeid'] for c in calls).values())
assert all(c['outcome']=='passed' for c in calls)
raw=root/'docs/rebuild/rev118/ci/mt5_symbol_contract_20261028'
assert not raw.exists();raw.mkdir(parents=True)
def copy(src,rel):
    src=Path(src);dest=raw/rel;dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(src,dest);assert src.read_bytes()==dest.read_bytes()
for p in run.iterdir():
    if p.is_file():copy(p,'sql_final/'+p.name)
copy('/workspace/van-mt5-symbol-contract-sql-r1-20261028.py','sql_final/controller.py')
copy('/workspace/van-mt5-symbol-contract-sql-r1-process-20261028.json','sql_final/outer-process.json')
stems=['van-mt5-symbol-identity-baseline','van-mt5-symbol-identity-focused-r1','van-mt5-symbol-identity-focused-r2',
    'van-mt5-symbol-contract-worker-r1','van-mt5-symbol-contract-adapter-r1',
    'van-mt5-symbol-contract-pull-r1','van-mt5-symbol-contract-pull-r2',
    'van-mt5-symbol-book-r1','van-mt5-symbol-book-r2','van-mt5-symbol-book-r3','van-mt5-symbol-book-r4']
for stem in stems:
    for suffix in ['.log','.xml','.json','-audit.json']:
        p=Path('/workspace/'+stem+'-20261028'+suffix)
        if p.exists():copy(p,'prior_attempts/'+p.name)
for stem in ['owner-registry','scope-check','mutation-consistency','frontend-registry','consolidation']:
    name='van-mt5-symbol-contract-'+stem+'-20261028'
    assert json.loads(Path('/workspace/'+name+'.json').read_text())['exit']==0
    for ext in ['.log','.json']:copy('/workspace/'+name+ext,'guards/'+name+ext)
for number in [1,2]:
    name='van-mt5-symbol-contract-wip'+str(number)+'-20261028'
    for suffix in ['.zip','.json']:copy('/workspace/'+name+suffix,'source_recovery/'+name+suffix)
parent=Path('/workspace/van-d3ef2cdb-selected-hosted-20261028')
if parent.exists():
    for p in parent.rglob('*'):
        if p.is_file():copy(p,'published_parent_selected_hosted/'+str(p.relative_to(parent)))
paths=subprocess.check_output(['git','diff','--name-only'],cwd=root,text=True).splitlines()
paths+=subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=root,text=True).splitlines()
source=sorted(p for p in paths if p.startswith(('trading/','deploy/van-trading-core/')))
hashes={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in source}
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
summary=(f'MT5 signed SDK and authenticated EA source transports now expose original symbol terms with native loss/profit tick values, quantity/tick rules and base/profit/margin currencies. Both public adapters preserve original request/nonce or queue identity, exact deadline, account scope and original numeric/clock formats. Explicit zero loss value remains UNPRICED; no missing value becomes zero or LIVE. Two genuine legacy signed symbol reads accepted a switched login/currency while retaining the old label; post-SDK readback now fences login/server/currency/demo changes without changing stable legacy shape or requiring trading permission. EA adds separate SYMBOL_CONTRACT capability and18-field expiry frame outside entry claims. NativeSymbolBook independently binds the existing MT5 account-query journal before a risk decision exists, preserving SQL replay/reopen/namespace isolation, queued/writer expiry and lost-ACK recovery without native retry. Final full trading plus selected backend HTTP/schema/scope qualification:{len(cases)}pass0skip/fail/audit,every call once,all{len(r["source_sha256"])} pinned input hashes match,ownedPostgreSQL independently absent.56focused checks overlap. Modified EA native compilation PENDING exact-source hosted evidence.0formal/native/production/S24acceptance issued.')
receipt={'schema':'van.rev118.mt5-original-symbol-source/1','source_parent':base,'observed_at_utc':now,
    'source_files_sha256':hashes,'implementation':summary,
    'source_result':{'actual_outer_exit':0,'actual_inner_exit':0,'passed':len(cases),'skipped':0,
        'audit_violations':0,'unique_call_identities_once':len(calls),
        'pinned_source_inputs_matched':len(r['source_sha256']),'owned_postgres_independently_absent':True,
        'includes_actual_worker_EA_and_README':True,'raw':'ci/mt5_symbol_contract_20261028/sql_final'},
    'retained_failed_attempts':[
        '2 actual signed legacy sync_symbols identity counterexamples failed DID_NOT_RAISE before the source fix.',
        'Pull r1:68passes/1 new expiry-oracle shape mismatch. Existing queue durably returned REJECTED/deadline/no native handoff; oracle now asserts that exact refusal.',
        'Book r1:50passes/1 lost-ACK fixture injected at nested append rather than real outer commit; outer-boundary injection corrected with original independent readback assertions retained.',
        'Book r3:55passes/1 new regex mismatch. The existing committed-source guard already refused before native read; assertion now names its exact original error.'],
    'native_EA_compilation':'PENDING_EXACT_MODIFIED_SOURCE_HOSTED_JOB',
    'formal_acceptances_issued':0,
    'source_authorizations':['auth-20261022-owner-autonomous-candidate-build','auth-20261023-owner-native-worker-source'],
    'limitations':[
        'Linux native SDK and EA responses were explicit source fixtures, not an actual connected terminal or provider.',
        'Source terms have no separate authoritative FX timestamp or atomic account snapshot; risk/provider/execution qualification flags remain false.',
        'This packet stores small original risk-input metadata, not a complete feed/catalog in the financial journal. Full discovery/feed/quote/depth/news/entitlement obligations remain in scope.',
        'It does not admit financial risk terms, reserve collateral/cash/margin, arbitrate active mandates, qualify migration/native finality or complete any unit.',
        'Parent native compilation cannot qualify the changed EA. Python storage audit is not an OS sandbox.'],
    'next':'Genuine hooks, required committed-baseline verify, normal push/exact remote readback, actual hosted source and modified-EA compilation; then native valuation/current-policy/shared transactional reservation workflows and remaining complete backend/Android programme.'}
rel='receipts/MT5_ORIGINAL_SYMBOL_SOURCE_20261028.json'
(root/'docs/rebuild/rev118'/rel).write_text(json.dumps(receipt,indent=2)+'\n')
for name in ['EXECUTION_LEDGER.json','CANDIDATE_SOURCE_PROGRESS.json']:
    p=root/'docs/rebuild/rev118'/name;v=json.loads(p.read_text());v['updated_at_utc']=now
    if name=='EXECUTION_LEDGER.json':
        v['observations'].append(summary);v['current_action']=receipt['next']
        for uid in ['BE-003','BE-008','BE-009','BE-010']:v['units'][uid]['evidence'].append(rel)
    else:
        for uid in ['BE-003','BE-008','BE-009','BE-010']:v['units'][uid]['milestones'].append({'description':summary,'evidence':rel})
    p.write_text(json.dumps(v,indent=2)+'\n')
(root/'docs/rebuild/rev118/backend/BE-008_MT5_ORIGINAL_SYMBOLS.md').write_text(
    '# Original MT5 symbol inputs and account fences\n\nCandidate source only; no full-unit or financial/native admission.\n\n'+summary+
    '\n\nThe actual legacy signed-read counterexamples retain their original failed evidence. Stable legacy responses stay compatible. Both new adapter paths retain original account/monetary scope, request identity, native numeric text, deadline and source clock basis. The EA capability is exact and separate from entry operations. Disabled trading permission still allows a read. Unknown native values refuse; zero loss tick value is explicit unpriced data. No order_check/send is used to obtain terms.\n\nThe original MT5 account-query receipt is independently read in the existing SQL owner before a native capture and before publication. This avoids a dependency cycle requiring a risk decision before its inputs exist. Original durable lookup survives expiry and restart, preserves namespace isolation, and reconciles lost storage acknowledgement without repeating a native read. Uncommitted inputs and expired queued/writer operations refuse.\n\nRead the [source receipt](../'+rel+') and raw failed/final evidence. Exact modified-EA native compilation remains pending after source publication. All actual terminal/provider/deployment/signing/device requirements remain unissued. Native source metadata is not a separately timestamped FX observation, atomic account snapshot, current risk grant or portfolio reservation.\n\nContinue complete instrument discovery/aliases, subscriptions/bars/gap/depth and entitlement contracts, qualified native valuation/migration, shared transactional cash/margin reservations across all origins, active-policy arbitration and native economic finality. Preserve all payment/manual/handover workflows, remaining backend/forecast/assistant/operations units and the prescribed Android programme. No feature or function is retired by this source packet.\n')
copy(__file__,'evidence-builder.py')
print(json.dumps({'source_files':len(source),'raw_files':sum(p.is_file() for p in raw.rglob('*')),'passed':len(cases),'receipt':rel}))
