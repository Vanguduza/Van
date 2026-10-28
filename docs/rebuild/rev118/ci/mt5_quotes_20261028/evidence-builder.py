from pathlib import Path
import collections,datetime,hashlib,json,shutil,subprocess,xml.etree.ElementTree as E

root=Path('/workspace/van-review-2026-10-18/publish')
base=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
assert base=='28705ca89e767e7c6193401410d36b0988f5212b'
run=Path('/workspace/van-mt5-quotes-sql-r1-20261028')
r=json.loads((run/'receipt.json').read_text())
outer=json.loads(Path('/workspace/van-mt5-quotes-sql-r1-process-20261028.json').read_text())
assert r['exit']==outer['exit']==0 and r['cleaned'] and r['owned_fixture_independently_absent']
assert not json.loads((run/'storage-audit.json').read_text())['forbidden_events']
assert all(hashlib.sha256((root/f).read_bytes()).hexdigest()==h for f,h in r['source_sha256'].items())
cases=E.parse(run/'full-trading.xml').findall('.//testcase')
assert cases and all(c.find('failure') is c.find('error') is c.find('skipped') is None for c in cases)
calls=[json.loads(l) for l in (run/'test-events.jsonl').read_text().splitlines() if json.loads(l)['phase']=='call']
assert len(calls)==len(cases) and all(n==1 for n in collections.Counter(c['nodeid'] for c in calls).values())
assert all(c['outcome']=='passed' for c in calls)
raw=root/'docs/rebuild/rev118/ci/mt5_quotes_20261028'
assert not raw.exists();raw.mkdir(parents=True)
def copy(src,rel):
    src=Path(src);dest=raw/rel;dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(src,dest);assert src.read_bytes()==dest.read_bytes()
for p in run.iterdir():
    if p.is_file():copy(p,'sql_final/'+p.name)
copy('/workspace/van-mt5-quotes-sql-r1-20261028.py','sql_final/controller.py')
copy('/workspace/van-mt5-quotes-sql-r1-process-20261028.json','sql_final/outer-process.json')
for stem in ['van-mt5-quote-worker-r1','van-mt5-quotes-adapter-r1','van-mt5-quote-book-r1','van-mt5-quotes-pull-r1']:
    for suffix in ['.log','.xml','.json','-audit.json']:
        p=Path('/workspace/'+stem+'-20261028'+suffix)
        if p.exists():copy(p,'focused/'+p.name)
for stem in ['owner-registry','scope-check','mutation-consistency','frontend-registry','consolidation']:
    name='van-mt5-quotes-'+stem+'-20261028'
    assert json.loads(Path('/workspace/'+name+'.json').read_text())['exit']==0
    for ext in ['.log','.json']:copy('/workspace/'+name+ext,'guards/'+name+ext)
for suffix in ['.zip','.json']:
    copy('/workspace/van-mt5-quotes-wip1-20261028'+suffix,'source_recovery/wip1'+suffix)
native=Path('/workspace/van-28705ca8-native-mql-20261028')
for p in native.rglob('*'):
    if p.is_file():copy(p,'published_parent_native_compile/'+str(p.relative_to(native)))
parent=Path('/workspace/van-28705ca8-selected-hosted-20261028')
if parent.exists():
    for p in parent.rglob('*'):
        if p.is_file():copy(p,'published_parent_selected_hosted/'+str(p.relative_to(parent)))
paths=subprocess.check_output(['git','diff','--name-only'],cwd=root,text=True).splitlines()
paths+=subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=root,text=True).splitlines()
source=sorted(p for p in paths if p.startswith(('trading/','deploy/van-trading-core/')))
hashes={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in source}
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
summary=(f'Original MT5 quote snapshots now flow through both signed SDK and authenticated EA/public adapters and the existing original-account-query SQL owner. Both native account and contract observations are retained around tick access. Original bid/ask/last, native full-tick time, subscription/delay facts and exact integer volume remain explicit; last-trade volume is not lots or genuine depth. Causal view distinguishes missing ticks/sides/time, inconsistent/future time, crossed prices, unverified subscription/entitlement, delayed and stale data. It never invents native time from local receipt time or refreshes history on replay. Original symbol receipt shape and data-kind isolation remain compatible through shared SQL ownership. Final full trading plus selected backend HTTP/schema/scope qualification:{len(cases)}pass0skip/fail/audit,every call once,all{len(r["source_sha256"])} pinned input hashes match,ownedPostgreSQL independently absent.57focused source passes overlap. New modified-EA compilation PENDING exact-source hosted evidence; parent symbol EA compilation is retained separately.0formal/native/production/S24acceptance issued.')
receipt={'schema':'van.rev118.mt5-original-quote-source/1','source_parent':base,'observed_at_utc':now,
    'source_files_sha256':hashes,'implementation':summary,
    'source_result':{'actual_outer_exit':0,'actual_inner_exit':0,'passed':len(cases),'skipped':0,
        'audit_violations':0,'unique_call_identities_once':len(calls),'pinned_source_inputs_matched':len(r['source_sha256']),
        'owned_postgres_independently_absent':True,'includes_actual_worker_EA_README':True,
        'raw':'ci/mt5_quotes_20261028/sql_final'},
    'native_EA_compilation':'PENDING_EXACT_MODIFIED_SOURCE_HOSTED_JOB',
    'parent_native_compilation':json.loads((native/'verified-evidence.json').read_text()),
    'formal_acceptances_issued':0,
    'source_authorizations':['auth-20261022-owner-autonomous-candidate-build','auth-20261023-owner-native-worker-source'],
    'limitations':[
        'Native SDK and EA responses in Linux checks were explicit fixtures, not actual connected terminal/provider evidence.',
        'Full native tick snapshot time is not a fabricated individual-side timestamp. The observed state remains unqualified and confers no risk/execution grant.',
        'This is snapshot input and durable readback, not complete tick-stream delivery, gap recovery, native bar aggregation, genuine depth or qualified FX conversion.',
        'All discovery/feed/entitlement, financial reservation/current-policy/native finality and remaining canonical backend/Android obligations remain in scope.',
        'The parent native compile does not qualify the changed EA; Python storage audit is not an OS sandbox.'],
    'next':'Genuine hooks, required committed-baseline verify, normal push/exact remote, exact hosted source and changed-EA native compilation; then full feed/valuation/current-policy/shared transactional reservation workflows and complete remaining backend/Android programme.'}
rel='receipts/MT5_ORIGINAL_QUOTE_SOURCE_20261028.json'
(root/'docs/rebuild/rev118'/rel).write_text(json.dumps(receipt,indent=2)+'\n')
for name in ['EXECUTION_LEDGER.json','CANDIDATE_SOURCE_PROGRESS.json']:
    p=root/'docs/rebuild/rev118'/name;v=json.loads(p.read_text());v['updated_at_utc']=now
    if name=='EXECUTION_LEDGER.json':
        v['observations'].append(summary);v['current_action']=receipt['next']
        for uid in ['BE-003','BE-008','BE-009']:v['units'][uid]['evidence'].append(rel)
    else:
        for uid in ['BE-003','BE-008','BE-009']:v['units'][uid]['milestones'].append({'description':summary,'evidence':rel})
    p.write_text(json.dumps(v,indent=2)+'\n')
(root/'docs/rebuild/rev118/backend/BE-008_MT5_ORIGINAL_QUOTES.md').write_text(
    '# Original MT5 quote snapshots and causal state\n\nCandidate source only; no full-unit or financial/native admission.\n\n'+summary+
    '\n\nThe native SDK/EA read captures original full-tick time and account/instrument observations. Exact capability/18-field expiry framing keeps old peers and expired queued reads away from native handoff. Trading permission is independent of these reads, and no order check/send obtains a quote.\n\nCausal view is evaluated against the requested current clock and age bound. Missing native clock stays missing; historical readback cannot substitute a new local timestamp. Original currency, prices and uint64 volume remain intact. Metadata, quote and source-receipt kinds stay distinct under the same tested SQL owner; existing symbol serialization is preserved. Public SDK and signed HTTP/EA queue routes exercise the actual original query/SQL readback chain over declared native fixtures.\n\nRead the [source receipt](../'+rel+') and raw source evidence. The changed EA requires its own subsequent exact-source native compilation. Source-state observation is not current tradability, financial authority, fresh FX qualification or production/native/provider/device acceptance.\n\nComplete native stream/bar/gap/depth/entitlement and discovery obligations, qualified valuation/migration, shared transactional all-origin cash/margin/stop-risk reservations, active-policy arbitration and working-order/economic-finality workflows. Preserve every remaining payment/manual/handover, backend/forecast/assistant/operations and prescribed Android function. Profitability is never guaranteed.\n')
copy(__file__,'evidence-builder.py')
print(json.dumps({'source_files':len(source),'raw_files':sum(p.is_file() for p in raw.rglob('*')),'passed':len(cases),'receipt':rel}))
