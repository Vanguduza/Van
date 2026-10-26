from pathlib import Path
import datetime,hashlib,json,shutil,xml.etree.ElementTree as E

repo=Path('/workspace/van-review-2026-10-18/publish');docs=repo/'docs/rebuild/rev118'
out=docs/'ci/coordinator_instance_20261026';out.mkdir(exist_ok=True)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
for source,target in [('van-coordinator-instance-before-20261026','actual_pg_before'),('van-coordinator-instance-after-r1-20261026','actual_pg_focused'),('van-coordinator-instance-pg-final-r1-20261026','actual_pg_final')]:
    shutil.copytree(Path('/workspace')/source,out/target,dirs_exist_ok=True)
for pattern in ['van-coordinator-instance-baseline-20261026.json','van-coordinator-instance-*-check-20261026.json','van-coordinator-instance-registry-20261026.json','van-coordinator-instance-consolidation-20261026.json','van-coordinator-instance-evidence-writer-recovery-20261026.json']:
    for path in Path('/workspace').glob(pattern):shutil.copy2(path,out/path.name)
for name in ['van-coordinator-instance-before-20261026.py','van-coordinator-instance-after-r1-20261026.py','van-coordinator-instance-pg-final-r1-20261026.py','van-coordinator-instance-evidence-20261026.py','van_pytest_live_diagnostics.py']:
    shutil.copy2(Path('/workspace')/name,out/name)
actual=json.loads((out/'actual_pg_final/receipt.json').read_text())
assert actual['exit']==0 and actual['completed'] is actual['cleaned'] is actual['owned_fixture_independently_absent'] is True
assert len(actual['source_sha256'])==1150 and all(sha(repo/name)==h for name,h in actual['source_sha256'].items())
cases=list(E.parse(out/'actual_pg_final/full-trading.xml').getroot().iter('testcase'))
assert len(cases)>=1000 and not any(c.find(key) is not None for c in cases for key in ['failure','error','skipped'])
assert not json.loads((out/'actual_pg_final/storage-audit.json').read_text())['forbidden_events']
before=list(E.parse(out/'actual_pg_before/full-trading.xml').getroot().iter('testcase'))
assert len(before)==3 and sum(c.find('failure') is not None for c in before)==2 and not any(c.find('error') is not None for c in before)
assert json.loads((out/'van-coordinator-instance-baseline-20261026.json').read_text())['source_matches_committed'] is True
assert json.loads((out/'van-coordinator-instance-owner-check-20261026.json').read_text())['changed']==[]
assert json.loads((out/'van-coordinator-instance-frontend-check-20261026.json').read_text())['changed'] is False
assert not json.loads((out/'van-coordinator-instance-consolidation-20261026.json').read_text())['findings']
forecast_dir=docs/'ci/hosted_4cc7b3a8_forecast_20261026'
shutil.copytree('/workspace/van-4cc7b3a8-hosted',forecast_dir,dirs_exist_ok=True)
shutil.copy2('/workspace/van-4cc7-forecast-reconcile-20261026.py',forecast_dir/'van-4cc7-forecast-reconcile-20261026.py')
forecast=json.loads((forecast_dir/'independent-reconciliation.json').read_text())
assert all(sha(forecast_dir/name)==h for name,h in forecast['file_sha256'].items())
now=datetime.datetime.now(datetime.timezone.utc).isoformat();count=len(cases)
summary=(f'Two actual coordinator builders in one process previously shared hostname/PID lease identity. '
         f'Real PostgreSQL reproduced a peer acquiring the live owner lease and peer shutdown releasing its authority: two failures and one expiry control. '
         f'Each coordinator now gets a UUID instance suffix, matching the single-session runtime; logical account aliases, signed mandates, store CAS, epochs and submission guards are unchanged. '
         f'Three focused cases and {count} final SQL/HTTP/runtime/authority/recovery cases pass, with no skips or storage-audit violations. '
         f'All 1,150 pinned backend/trading runtime and test hashes match; the owned PostgreSQL fixture is independently absent. '
         f'This is a source component, not whole-unit, provider, native, production or owner acceptance. Physical-account aliases and shared financial reservations remain separate open work.')
report={'schema':'van.rebuild.coordinator-instance-source/1','base_head':actual['base_head'],'updated_at_utc':now,
        'units':['BE-003','BE-009'],'status':'SOURCE_TESTED_COMPONENT_NOT_UNIT_NATIVE_OR_PRODUCTION_ACCEPTANCE',
        'acceptance':'NOT_ISSUED','implementation':summary,
        'source_sha256':{name:sha(repo/name) for name in ['trading/vati/app/account_service.py','trading/tests/test_coordinator_instance_arbitration.py']},
        'actual_tests':{'before_failed':2,'before_positive_expiry_control':1,'focused_passed':3,'final_passed':count,
                       'final_skips':0,'audit_violations':0,'pinned_runtime_test_hashes':1150,'owned_fixture_independently_absent':True,'counts_overlap':True},
        'canonical_checks':{'owner_frontend_drift':False,'mutation_registry_cases':374,'mutation_registry_edits':383,'registry_check_is_execution':False},
        'qualification':'Actual runtime construction, PostgreSQL arbitration and Paper source fixtures. No native broker send or new owner authority exercised. This does not close physical-account alias fencing, shared order/funding reservations, account-wide risk, native activation, unit admission, economic or S24 acceptance.',
        'evidence':'ci/coordinator_instance_20261026'}
(docs/'receipts/COORDINATOR_INSTANCE_SOURCE_20261026.json').write_text(json.dumps(report,indent=2)+'\n')
(docs/'receipts/HOSTED_FORECAST_SOURCE_4cc7b3a8.json').write_text(json.dumps({
    'schema':'van.rebuild.hosted-forecast-source/1','source_head':'4cc7b3a841054b326958edc30bc3a6cd42196105','updated_at_utc':now,
    'forecast':forecast,'main_run':40415113142,'main_state':'IN_PROGRESS_AT_CAPTURE;inspect current GitHub for later outcome',
    'qualification':'Published 4cc7 forecast/source fixtures only. Later aggregation and coordinator changes are not qualified by this run. No whole-main, unit, provider, native, production, economic or S24 acceptance.',
    'evidence':'ci/hosted_4cc7b3a8_forecast_20261026'},indent=2)+'\n')
(docs/'backend/BE-003_009_COORDINATOR_INSTANCE_ARBITRATION.md').write_text(f'''# Coordinator instance arbitration

{summary}

The original account coordinator used only hostname and PID as its holder identity. Two independently built coordinators in one process therefore appeared to be the same holder. The real shared PostgreSQL lease owner granted the peer acquisition, and a peer release could remove the first coordinator's current authority. The original three-case run retains both failures and the passing expired-owner control. Its account-service bytes match the committed parent.

The repair adds a fresh UUID suffix when the coordinator constructs its lease, using the same identity pattern already used by SessionService. The PostgreSQL store remains the arbiter. A live peer refuses, its shutdown cannot release the holder, and expired owners stay fenced after takeover. No policy ceiling, account scope, signature, grant format, expiry, recovery action or provider call is relaxed. The final selection includes the actual account recovery, current signer, mandate deadline, registry entry, native deadline, single-session and source-storage regressions. The test venue is an explicit Paper fixture; no live financial effect or production owner authority is claimed.

This repair concerns distinct runtime instances for one logical account alias. Separate read-only inspection of two aliases for one physical cTrader account found alias-scoped registry and lease behavior, but did not prove an end-to-end financial bypass. Physical-account arbitration and shared order/funding reservations remain open. Any future change must preserve observer profiles, current signed aliases, account retirement, exact recovery controls and existing-cohort migration requirements.

Raw source receipts, JUnit, storage audits, source hashes and bounded fixture controllers are retained in `../ci/coordinator_instance_20261026`. Source contract and consolidation checks have no drift. Mutation registry preflight remains consistency evidence, not execution of 374 cases. All formal acceptance remains unissued.
''')
for filename in ['CANDIDATE_SOURCE_PROGRESS.json','EXECUTION_LEDGER.json']:
    path=docs/filename;value=json.loads(path.read_text());value['updated_at_utc']=now
    for unit in ['BE-003','BE-009']:
        if filename=='CANDIDATE_SOURCE_PROGRESS.json':
            milestone={'description':summary,'evidence':'backend/BE-003_009_COORDINATOR_INSTANCE_ARBITRATION.md;receipts/COORDINATOR_INSTANCE_SOURCE_20261026.json'}
            if not any(m.get('evidence')==milestone['evidence'] for m in value['units'][unit]['milestones']):
                value['units'][unit]['milestones'].append(milestone)
        elif unit in value['units']:
            # The execution ledger groups most units under ALL_BE_BQ_UX_FE_QA_REL;
            # the complete individual BE-009 milestones live in source progress.
            for evidence in ['backend/BE-003_009_COORDINATOR_INSTANCE_ARBITRATION.md','receipts/COORDINATOR_INSTANCE_SOURCE_20261026.json']:
                if evidence not in value['units'][unit]['evidence']:value['units'][unit]['evidence'].append(evidence)
    if filename=='EXECUTION_LEDGER.json':
        value['checkpoint']['updated_utc']=now;value['checkpoint']['last_validation']=summary;value['observations'].append(summary)
        value['continuation']['verified_source_head']='a7485a9a1ca6b3b11c96436b04fa2e1c05397029 local/genuine GREEN167/manifest5367; published4cc7 GREEN166; coordinator UUID source uncommitted'
        value['continuation']['latest_checkpoint_report']='docs/rebuild/rev118/CHECKPOINT_20261026_COORDINATOR_INSTANCE.md'
        value['current_action']='Finish coordinator instance source manifest, verified staged backup, genuine candidate-build hook commit and actual committed baseline verification. Preserve published4cc7 main40415113142 until terminal; inspect/reconcile exact results, normally push combined local head and verify remote readback/exact CI. Continue canonical backend functionality; no unit acceptance issued.'
    path.write_text(json.dumps(value,indent=2)+'\n')
(docs/'CHECKPOINT_20261026_COORDINATOR_INSTANCE.md').write_text(f'''# Coordinator instance continuation

{now}

Branch `ccr-9e07e1af-8mgz1p`, draft PR105. Local parent `a7485a9a1ca6b3b11c96436b04fa2e1c05397029` passed genuine hooks and actual committed GREEN167 against `4fd466dec3910ed5de614bfbf95887ad619df5ca`; manifest 5,367 files, zero mismatches, all tracked. It contains the final 965-case aggregation repair and full preceding9255 hosted proof. It remains local while published `4cc7b3a841054b326958edc30bc3a6cd42196105` runs main CI40415113142. This coordinator packet is uncommitted at documentation generation; inspect actual Git for later state.

{summary}

Published4cc7 forecast40415113329 succeeded in both jobs. Two archive ZIPs were independently size/SHA/CRC/path verified, with 114 native Parquet/SQL cases, six synthetic upstream fixtures, three separate cold models and zero reload differences. The 232 versions, actual kernel limits, worker cleanup, source/controller/report hashes and tree-equivalent tested merge `ce864a6c59a0fdd59f0d874ef9e78985b03d2b78` were reconciled. Main remained in progress at capture. Forecast proof does not qualify later aggregation/coordinator source. Earlier failures and partial observations remain historical.

Next finish real manifest, verified staged ZIP, normal genuine candidate-build hook commit and actual committed baseline verification. Do not guess the next GREEN count. Wait for terminal4cc7 main before pushing; retain its real failures/skips and source binding. Push normally with independent remote readback, then inspect exact combined-head CI. Intermediate local commits without their own run receive no separate hosted qualification.

Continue all dependency-ready canonical backend features and qualification. Physical-account aliases and shared financial reservations remain open; UUID instance isolation does not resolve them. No native provider send, activation, deployment, signing, production profile or S24 evidence is claimed. Zero formally accepted units. Preserve frozen131 units/324 requirements/1,610 acceptance identities/234 contexts/349 actions/93 features and original frontend42 groups/105 function IDs/78 surfaces; current backend480 endpoints/372 schemas. No frontend redesign before BG001, no /workspace/Van access and no delegation. Van trading core remains the chosen host. Profitability requires evidence and is never guaranteed.
''')
print(json.dumps({'final_actual_passes':count,'pinned_hashes':1150,'new_cases':3,'original_failures_retained':2,'forecast4cc7':'independently reconciled; main pending at capture'}))
