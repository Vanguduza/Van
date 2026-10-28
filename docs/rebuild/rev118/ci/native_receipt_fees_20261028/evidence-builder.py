"""Bind original executed evidence without issuing native or unit acceptance."""
from pathlib import Path
import ast, datetime, gzip, hashlib, io, json, shutil, subprocess, tarfile, zipfile
import xml.etree.ElementTree as ET

root = Path('/workspace/van-review-2026-10-18/publish')
base = 'ab91a8ebf2a7e94e9ab7d742108eba81b88d93cd'
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip() == base
run = Path('/workspace/van-native-receipt-fee-full-sql-r2-20261028')
r = json.loads((run/'receipt.json').read_text())
assert r['exit'] == 0 and r['completed'] and r['cleaned'] and r['owned_fixture_independently_absent']
pins = r['source_sha256'] | r['reference_fixtures_sha256']
assert all(hashlib.sha256((root/f).read_bytes()).hexdigest() == h for f,h in pins.items())
assert not json.loads((run/'storage-audit.json').read_text())['forbidden_events']
cases = ET.parse(run/'full-trading.xml').findall('.//testcase')
assert len(cases) == 5334 and all(not any(c.find(k) is not None for k in ('failure','error','skipped')) for c in cases)
calls = [json.loads(s) for s in (run/'test-events.jsonl').read_text().splitlines() if json.loads(s)['phase'] == 'call']
assert len(calls) == len({c['nodeid'] for c in calls}) == 5334 and all(c['outcome'] == 'passed' for c in calls)
collection = Path('/workspace/van-native-receipt-fee-collection-r2-20261028')
assert json.loads(collection.with_suffix('.json').read_text())['exit'] == 0
nodes = [s for s in collection.with_suffix('.log').read_text().splitlines() if s.startswith(('trading/tests/','backend/tests/','tests/rebuild/')) and '::' in s]
assert len(nodes) == len(set(nodes)) == 5334 and set(nodes) == {c['nodeid'] for c in calls}
files = functions = 0
with tarfile.open(fileobj=io.BytesIO(subprocess.check_output(['git','archive',base,'trading/tests','tests/rebuild'],cwd=root))) as tar:
    for m in tar:
        if not m.isfile() or not m.name.endswith('.py') or not Path(m.name).name.startswith('test_'): continue
        old = tar.extractfile(m).read()
        assert old == (root/m.name).read_bytes(), m.name
        files += 1
        functions += sum(isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name.startswith('test_') for n in ast.walk(ast.parse(old)))
for label in ('workmap','owner','frontend','mutations','consolidation'):
    assert json.loads(Path('/workspace/van-native-receipt-fee-'+label+'-20261028.json').read_text())['exit'] == 0
assert json.loads(Path('/workspace/van-native-receipt-fee-schema-20261028.json').read_text())['exit'] == 0
raw = root/'docs/rebuild/rev118/ci/native_receipt_fees_20261028'
raw.mkdir(parents=True,exist_ok=True)
def copy(source, dest):
    source = Path(source); dest = raw/dest; dest.parent.mkdir(parents=True,exist_ok=True)
    data = source.read_bytes()
    if dest.suffix == '.gz':
        dest.write_bytes(gzip.compress(data,mtime=0)); assert gzip.decompress(dest.read_bytes()) == data
    else:
        dest.write_bytes(data); assert dest.read_bytes() == data
for prefix in ('van-native-receipt-fee-before-20261028','van-native-receipt-fee-before-r2-20261028',
               'van-native-receipt-fee-after-r1-20261028','van-native-receipt-fee-consumers-r1-20261028',
               'van-native-receipt-fee-consumers-r2-20261028','van-native-receipt-fee-collection-r2-20261028'):
    for suffix in ('.json','.log','.xml'):
        p = Path('/workspace')/(prefix+suffix)
        if p.exists(): copy(p, p.name)
for attempt in (1,2):
    folder = Path('/workspace/van-native-receipt-fee-full-sql-r'+str(attempt)+'-20261028')
    original = json.loads((folder/'receipt.json').read_text())
    assert original['completed'] and original['cleaned'] and original['owned_fixture_independently_absent']
    if attempt == 1:
        assert original['exit'] == 1
        first = ET.parse(folder/'full-trading.xml').findall('.//testcase')
        failures = [c for c in first if c.find('failure') is not None]
        assert len(first) == 5334 and len(failures) == 3
        assert all(c.get('classname','').endswith('test_native_receipt_fee_knowledge') for c in failures)
    for p in folder.iterdir():
        if p.is_file(): copy(p, 'full-r'+str(attempt)+'/'+p.name+('.gz' if p.name.endswith('.jsonl') else ''))
    copy('/workspace/van-native-receipt-fee-full-sql-r'+str(attempt)+'-20261028.py', 'full-r'+str(attempt)+'/controller.py')
old = json.loads(Path('/workspace/van-native-receipt-fee-wip1-20261028.json').read_text())
archive = Path(old['archive'])
assert hashlib.sha256(archive.read_bytes()).hexdigest() == old['sha256']
with zipfile.ZipFile(archive) as z:
    path = 'trading/tests/test_native_receipt_fee_knowledge.py'
    original = z.read(path)
    first_pins = json.loads(Path('/workspace/van-native-receipt-fee-full-sql-r1-20261028/source-start.json').read_text())['source_sha256']
    assert hashlib.sha256(original).hexdigest() == first_pins[path]
    (raw/'full-r1/original-new-test-source.py').write_bytes(original)
for label in ('workmap','owner','frontend','mutations','consolidation'):
    for suffix in ('.json','.log'):
        p = Path('/workspace/van-native-receipt-fee-'+label+'-20261028'+suffix); copy(p,p.name)
for name in ('test_van_native_receipt_fee_knowledge_20261028.py','van-native-receipt-fee-probe1-source-20261028.py',
             'van-native-receipt-fee-schema-20261028.py','van-native-receipt-fee-schema-20261028.log','van-native-receipt-fee-schema-20261028.json',
             'van-native-receipt-fee-environment-20261028.json',
             'van-native-receipt-fee-protocol-20261028.json',
             'van-native-receipt-fee-wip1-20261028.json','van-ab91-postgres-archive-readback-20261028.json',
             'van-ab91-postgres-artifact-meta-20261028.json',
             'test_van_mt5_recorded_fee_absence_20261028.py','van-mt5-recorded-fee-absence-before-20261028.log',
             'van-mt5-recorded-fee-absence-before-20261028.json','van-mt5-recorded-fee-absence-before-20261028.xml',
             'test_van_owner_cost_replay_20261028.py','van-owner-cost-replay-before-20261028.log',
             'van-owner-cost-replay-before-20261028.json','van-owner-cost-replay-before-20261028.xml'):
    copy('/workspace/'+name,name)
for job in (123145423660,123145423621,123145423657):
    p=Path('/workspace/van-ab91-original-job-'+str(job)+'-20261028.log'); copy(p,p.name)
proof = {'full_passed':len(cases),'failures':0,'errors':0,'skips':0,'storage_violations':0,
    'single_complete_current_collection':True,'collection_call_IDs_identical_each_once':True,
    'source_input_sha256':pins,'source_pins':len(pins),'original_test_files_unchanged':files,
    'original_test_functions_unchanged':functions,'owned_postgres_independently_absent':True,
    'source_preservation_only_not_native_or_unit_acceptance':True}
(raw/'source-preservation-and-discovery.json').write_text(json.dumps(proof,indent=2)+'\n')
now = datetime.datetime.now(datetime.UTC).isoformat()
summary = (f'Native cTrader execution receipts retain unknown commission/row precision as null rather than fee zero; actual fills, quantity, positions and protective stops survive missing or malformed optional charge metadata. Explicit zero and the existing recorded magnitude convention remain available; exact int64 charges survive hostile decimal contexts. The original sealed receipt fields/defaults remain compatible. Both runtime cost consumers and owner-confirmation adoption record cost-unavailable without emitting numeric TCA, and existing measured-receipt repair remains positive. SQLite/PostgreSQL original receipt readback and cold position/protection recovery preserve null and its original hash; no synthetic cost-learning evidence is produced. Derived price/gross PnL requires recorded charges, while reported net cash retains its explicit convention without a fabricated charge decomposition. Final full source run: {len(cases)} passed,0fail/error/skip/storage violations; exact independent collection/call IDs each once, all{len(pins)}input hashes matched; ownedPostgreSQL independently absent. All{files}inherited test files/{functions}original test functions remain unchanged. Original wire counterexamples and the failed intermediate full run are retained. This partial BE009/010/012 source packet does not complete native fees, economic finality, parent budgets, reservations or any unit/native/production/device acceptance.')
rel = 'receipts/NATIVE_RECEIPT_FEE_KNOWLEDGE_SOURCE_20261028.json'
next_action = ('Commit through genuine Project Truth hooks, verify committed ledger against4fd466dec3910ed5de614bfbf95887ad619df5ca, push normally, independently read remote head and inspect exact-head CI. Continue complete native fee/fill/price/multi-asset and all-origin obligations, lifetime parent/child budgets/current policy/cohort, economic reconciliation and all original backend requirements; then gated Android with provisioned production profile on Van trading core and actual signing/Artemis S24 evidence. No routine permission or completion claim.')
receipt = {'schema':'van.rev118.native-receipt-fee-knowledge-source/1','observed_at_utc':now,'source_parent':base,
    'state':'PARTIAL_CANDIDATE_SOURCE_TESTED_NOT_FULL_NATIVE_COST_OR_SETTLEMENT','implementation':summary,
    'checks':proof,'authority':'auth-20261022-owner-autonomous-candidate-build','raw':'ci/native_receipt_fees_20261028',
    'retained_failures':['Original and refined framed counterexamples:3failed/1passed each; missing precision uses nonzero commission in the refined probe.',
        'First full run:5331passed/3failed; two new tests inherited previously set Decimal flags, and a new test used a nonexistent owner_ticket module. Corrected local-context setup and actual zse_ticket import; all original assertions and inherited tests preserved.'],
    'remaining':['MT5/other-provider recorded fee completeness and original signed native charge semantics; no complete future fee/financing/charge-count claim.',
        'Two adjacent MT5 missing-charge counterexamples and one owner-adoption cost-ratio replay counterexample remain failing outside the selected5334-case suite. They are explicitly retained for the next packet; this result does not claim all product requirements or all known probes pass.',
        'Complete native cash/fill/price and multi-asset obligations, family/correlation and immutable lifetime parent/child budgets.',
        'Current qualified policy/cohort, all-origin transactional reservations/outbox, actual effect consumers, native finality and nonduplicated release/bust/late-charge compensation.',
        'Every original markets/feeds/depth/news/calendar/entitlement/chart/voice,38forecast/research,assistant/crypto,security/operations and gated Android requirement.'],
    'formal_acceptance':'NOT_ISSUED','execution_authority':False,'settlement_qualified':False,'next':next_action}
(root/'docs/rebuild/rev118'/rel).write_text(json.dumps(receipt,indent=2)+'\n')
for name in ('EXECUTION_LEDGER.json','CANDIDATE_SOURCE_PROGRESS.json'):
    p=root/'docs/rebuild/rev118'/name;d=json.loads(p.read_text());d['updated_at_utc']=now
    if name == 'EXECUTION_LEDGER.json':
        d['observations'].append(summary);d['current_action']=next_action
        for uid in ('BE-009','BE-010','BE-012'):
            row=d['units'][uid]
            if rel not in row['evidence']:row['evidence'].append(rel)
    else:
        for uid in ('BE-009','BE-010','BE-012'):
            d['units'][uid]['milestones'].append({'description':summary,'evidence':rel})
    p.write_text(json.dumps(d,indent=2)+'\n')
p=root/'docs/rebuild/rev118/CONTINUATION_20261022.md'
p.write_text(p.read_text()+'\n\n## Native receipt fee knowledge —28October\n\n'+summary+'\n\n[Source receipt]('+rel+'). '+next_action+'\n')
doc = ('# Native receipt charges, cost availability and safety recovery\n\n'+summary+'\n\n'
    '[Source receipt](../'+rel+') binds the original source, original failed attempts, exact final test collection and real SQL readback. These are native protocol fixtures, not a connected broker qualification.\n\n'
    'Unknown recorded fees cannot become numeric TCA or price-derived net PnL. The fill and protection remain known. Reported net cash keeps its original convention and is not silently recomputed from gross price or missing charges. Native economic finality still follows its existing separate owner. Old receipt bodies and numeric defaults are retained for hash compatibility; an old default is not retroactive proof of complete fees. A measured correction exercises the existing downstream repair consumer and does not grant native fee-correction authority.\n\n'
    'This packet changes only cTrader receipt extraction and shared runtime consumers. It does not qualify MT5/Deriv/spot complete charges, raw native sign mapping, fee assets/conversion, future financing/minimum/fill-count obligations, parent budgets, reservation publication, settlement or financial release. Those original requirements stay open. No frontend redesign occurs. The nullable recorded-fee contract is additive; owner endpoint registries are unchanged.\n\n'
    'Three additional adjacent counterexamples remain failing outside the selected5334-case suite: MT5 signed-worker and EA-function result decoders default missing charges to0, and repeated owner-confirmation adoption loses the in-memory cost ratio after the original TCA already exists. Original probes/results are retained here; fix them in the next source packet. No all-product or all-known-probe green result is claimed.\n\n'
    'Preserve all original manual/payment/handover,market,forecast/learning/crypto,assistant/voice and operations obligations. Android follows BG-001 and canonical gates, with a provisioned production profile on Van trading core, real signing and Artemis/S24 acceptance. Profitability is evaluated with evidence and never guaranteed.\n')
(root/'docs/rebuild/rev118/backend/BE-010_012_NATIVE_RECEIPT_FEE_KNOWLEDGE.md').write_text(doc)
copy(__file__,'evidence-builder.py')
print(json.dumps({'passed':len(cases),'source_pins':len(pins),'inherited_test_files':files,'inherited_functions':functions,'raw_files':sum(p.is_file() for p in raw.rglob('*')),'receipt':rel}))
