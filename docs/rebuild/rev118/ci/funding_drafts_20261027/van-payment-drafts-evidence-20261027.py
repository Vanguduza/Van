from pathlib import Path
import collections,datetime,hashlib,json,shutil,xml.etree.ElementTree as ET

repo=Path('/workspace/van-review-2026-10-18/publish');docs=repo/'docs/rebuild/rev118';work=Path('/workspace')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def cases(path):return list(ET.parse(path).getroot().iter('testcase'))
actual=json.loads((work/'van-payment-drafts-final-r2-20261027/receipt.json').read_text())
assert actual['exit']==0 and actual['completed'] is actual['cleaned'] is actual['owned_fixture_independently_absent'] is True
assert len(actual['source_sha256'])==1158 and all(sha(repo/name)==value for name,value in actual['source_sha256'].items())
final=cases(work/'van-payment-drafts-final-r2-20261027/full-trading.xml')
assert len(final)==377 and not any(c.find(k) is not None for c in final for k in ['failure','error','skipped'])
assert not json.loads((work/'van-payment-drafts-final-r2-20261027/storage-audit.json').read_text())['forbidden_events']
new_counts=collections.Counter(c.attrib['classname'] for c in final if 'payment_' in c.attrib['classname'])
assert sum(new_counts.values())==122
for name in ['owner-check','frontend-check','registry','consolidation']:
    value=json.loads((work/f'van-payment-drafts-{name}-20261027.json').read_text())
    if name=='owner-check':assert value['changed']==[]
    elif name=='frontend-check':assert value['changed'] is False
    else:assert value['findings']==[]
assert '122 passed' in (work/'van-payment-drafts-rebuild-final-r2-20261027.log').read_text()
progress=json.loads((docs/'CANDIDATE_SOURCE_PROGRESS.json').read_text())
assert progress['units']['BE-007']['unit_acceptance']=='NOT_ISSUED'
host=work/'van-4cc7b3a8-full-hosted';full_forecast=json.loads((host/'independent-reconciliation.json').read_text())
assert all(sha(host/name)==value for name,value in full_forecast['file_sha256'].items())
current_forecast_dir=work/'van-2a1186ee-forecast-hosted';current_forecast=json.loads((current_forecast_dir/'independent-reconciliation.json').read_text())
assert all(sha(current_forecast_dir/name)==value for name,value in current_forecast['file_sha256'].items())

out=docs/'ci/funding_drafts_20261027';out.mkdir(exist_ok=False)
for source,target in [('van-payment-drafts-pg-r1-20261026','actual_sql_failed_r1'),('van-payment-drafts-pg-r2-20261026','actual_sql_r2'),('van-payment-drafts-final-r1-20261027','integration_before_credential_review'),('van-payment-drafts-final-r2-20261027','actual_sql_http_final_r2')]:
    shutil.copytree(work/source,out/target)
for pattern in ['van-payment-contracts-r1-20261026*','van-payment-draft-http-r*-20261026*','van-payment-drafts-*-20261026.json','van-payment-drafts-*-20261027.json','van-payment-drafts-rebuild*-20261027.log']:
    for path in work.glob(pattern):
        if path.is_file():shutil.copy2(path,out/path.name)
for name in ['van-payment-drafts-pg-r1-20261026.py','van-payment-drafts-pg-r2-20261026.py','van-payment-drafts-final-r1-20261027.py','van-payment-drafts-final-r2-20261027.py','van-payment-drafts-evidence-20261027.py','van_pytest_live_diagnostics.py']:
    shutil.copy2(work/name,out/name)
host_out=docs/'ci/hosted_4cc7b3a8_full_20261027';shutil.copytree(host,host_out)
for name in ['van-4cc7-main-reconcile-20261026.py','van-4cc7-full-forecast-reconcile-20261026.py']:shutil.copy2(work/name,host_out/name)
forecast_out=docs/'ci/hosted_2a1186ee_forecast_20261027';shutil.copytree(current_forecast_dir,forecast_out)
shutil.copy2(work/'van-2a-forecast-reconcile-20261027.py',forecast_out/'van-2a-forecast-reconcile-20261027.py')

now=datetime.datetime.now(datetime.timezone.utc).isoformat()
summary=(
    'Immutable unapproved funding drafts now bind exact Money, owner/account claims, beneficiary/quote references, '
    'all fee assets, conversion reference, operation, original request, revision and expiry. '
    'The existing VATI ledger owner stores original drafts with SQL serialization, writer-lock expiry recheck, '
    'committed source reads, independent cold readback, lost-ACK/rollback recovery and explicit capacity refusal. '
    'Three paired-owner HTTP routes retain original receipts; bound request proof is not payment approval. '
    'Existing instrument and owner credential screens reject unsafe metadata before storage; strict JSON/encoded body limits '
    'and cancellation-safe worker admission apply. Native draft retention/deletion is explicitly excluded from inferred-memory erasure and remains unqualified. '
    'Final377 actual SQLite/PostgreSQL/HTTP/privacy/authority cases pass with0skips/audit violations, '
    'all1158 pinned source/test hashes match and owned fixture independently absent;122rebuild/workflow/T0 checks pass. '
    'New cases:45value,58dual-engine journal,18gateway and1bound-proof executions; counts overlap. '
    'Earlier fixture failures and the uncommitted prototype credential gap remain retained. '
    'BE007 is IN_PROGRESS; no payment/provider/native/unit/production/owner acceptance is issued.')
source_names=['trading/vati/core/events.py','trading/vati/funding/payment_contracts.py','trading/vati/funding/payment_drafts.py',
    'backend/van_gateway/app.py','backend/van_gateway/trading/payment_draft_api.py','backend/van_gateway/trading/payment_draft_policy.py',
    'backend/van_gateway/owner_privacy.py','backend/van_gateway/context/forget.py',
    'trading/tests/test_payment_contracts.py','trading/tests/test_payment_draft_journal.py',
    'backend/tests/test_payment_draft_gateway.py','backend/tests/test_payment_draft_bound_device.py','tools/rebuild/refresh_owner_source_contracts.py']
report={'schema':'van.rebuild.funding-drafts-source/1','base_head':actual['base_head'],'updated_at_utc':now,'unit':'BE-007',
    'status':'SOURCE_TESTED_COMPONENT_NOT_UNIT_NATIVE_OR_PRODUCTION_ACCEPTANCE','acceptance':'NOT_ISSUED',
    'implementation':summary,'source_sha256':{name:sha(repo/name) for name in source_names},
    'actual_tests':{'new_case_executions':dict(new_counts),'new_total':122,'initial_values_and_money':86,
        'failed_first_sql':{'passed':123,'failed':3,'status':'FAILED_RETAINED'},'corrected_sql':126,
        'failed_first_http':{'passed':67,'failed':1,'status':'FAILED_RETAINED'},'http_r2':68,'http_r3':72,
        'integration_before_credential_review':362,'final_actual_SQLite_Postgres_HTTP_privacy':377,
        'final_skips':0,'final_audit_violations':0,'source_test_hashes_verified':1158,'owned_fixture_independently_absent':True,
        'rebuild_workflow_T0':122,'counts_overlap':True},
    'credential_review':'Three public non-secret probe shapes were allowed by the uncommitted prototype guard. Existing owner credential screen is now reused and includes wallet private-key/seed assignments; actual SQL/HTTP refusal cases pass. No production incident or real credential exposure is claimed.',
    'canonical_checks':{'endpoints':483,'schemas':376,'original_feature_groups':42,'original_functions':105,'original_surfaces':78,
        'owner_frontend_drift':False,'mutation_registry_cases':374,'mutation_registry_edits':383,'registry_validation_is_execution':False},
    'remaining':['actual provider quote/reference resolution','beneficiary verification','fresh exact sealed A4 approval',
        'shared order/funding reservations','submission/outbox','unknown-effect reconciliation','independent debit/credit settlement',
        'compensating reversals','verified hosted handoff','native draft privacy/deletion, retention and cohort migration qualification'],
    'qualification':'Draft preparation/storage only. All reference digests and provider/quote claims remain unverified. No retained payment instrument, automated payment, financial effect, new owner grant, provider certificate, deployment or S24 evidence is issued.',
    'evidence':'ci/funding_drafts_20261027'}
(docs/'receipts/FUNDING_DRAFTS_SOURCE_20261027.json').write_text(json.dumps(report,indent=2)+'\n')
(docs/'receipts/HOSTED_SOURCE_4cc7b3a8.json').write_text(json.dumps({'schema':'van.rebuild.hosted-source/1',
    'source_head':'4cc7b3a841054b326958edc30bc3a6cd42196105','updated_at_utc':now,
    'main':json.loads((host/'reconciliation.json').read_text()),'forecast':full_forecast,
    'qualification':'Exact4cc7 source fixtures only; later aggregation/coordinator/funding drafts are not qualified. Two mandatory prerequisites remain unwaived. Earlier partial receipts retain their captured observations. No unit/native/production/economic/S24 acceptance.',
    'evidence':'ci/hosted_4cc7b3a8_full_20261027'},indent=2)+'\n')
(docs/'receipts/HOSTED_FORECAST_SOURCE_2a1186ee.json').write_text(json.dumps({'schema':'van.rebuild.hosted-forecast-source/1',
    'source_head':'2a1186ee1199f56c0ae9fce06d13b27f9098d3c3','updated_at_utc':now,'forecast':current_forecast,
    'main_run':40421043580,'main_scope':'Whole main outcome not reconciled by this forecast receipt; inspect exact run.',
    'qualification':'Exact2a source forecast fixtures only; later funding drafts are not qualified. No unit/native/production/economic/S24 acceptance.',
    'evidence':'ci/hosted_2a1186ee_forecast_20261027'},indent=2)+'\n')
path=docs/'backend/BE-007_IMMUTABLE_FUNDING_DRAFTS.md'
text=path.read_text().replace('Expanded integration and final source-hash/cleanup qualification are pending; these overlapping results are not unit acceptance.',
    'The final combined selection passes377 actual SQLite/PostgreSQL/HTTP/privacy/authority cases with no skips or audit violations, all1158 pinned runtime/test hashes matching and the owned PostgreSQL fixture independently absent.122rebuild/workflow/T0 checks pass. A subsequent credential review caught three allowed metadata shapes in the uncommitted prototype; reusing the owner credential screen and adding SQL/HTTP negatives closes that source gap. These overlapping results are not unit acceptance. See `../receipts/FUNDING_DRAFTS_SOURCE_20261027.json` and the retained raw evidence.')
path.write_text(text)
milestone={'description':summary,'evidence':'backend/BE-007_IMMUTABLE_FUNDING_DRAFTS.md;receipts/FUNDING_DRAFTS_SOURCE_20261027.json'}
progress['updated_at_utc']=now
if progress['units']['BE-007']['candidate_status']=='NOT_STARTED':progress['units']['BE-007']['candidate_status']='IN_PROGRESS'
progress['units']['BE-007']['milestones'].append(milestone)
(docs/'CANDIDATE_SOURCE_PROGRESS.json').write_text(json.dumps(progress,indent=2)+'\n')
path=docs/'EXECUTION_LEDGER.json';ledger=json.loads(path.read_text());ledger['updated_at_utc']=now
unit=ledger['units'].setdefault('BE-007',{'status':'IN_PROGRESS','candidate_source_only':True,'acceptance':'NOT_ISSUED','evidence':[]})
assert unit['acceptance']=='NOT_ISSUED'
unit['evidence']+=['backend/BE-007_IMMUTABLE_FUNDING_DRAFTS.md','receipts/FUNDING_DRAFTS_SOURCE_20261027.json']
ledger['checkpoint']['updated_utc']=now;ledger['checkpoint']['last_validation']=summary;ledger['observations'].append(summary)
ledger['observations'].append('Exact4cc7 main40415113142 terminalFAILED2mandatory/all17publicSUCCESS;19rawarchives verified,4125trading+1DDSskip/PG26/voice117/gateway5807+7/media198/monitor258/browser/emulator18+4,374canonicalidentities caught once383edits. Forecast40415113329 independentlyverified114native+6synthetic+3cold/parity0/232versions/kernel/cleanup/source-controller-reporthashes/tree-equivalentce864a6c59a0fdd59f0d874ef9e78985b03d2b78. Exact2a forecast40421043611 independentlyverified114+6+3/tree76184cd978eee3dc558a2778ecb5501f2685546d; whole2a main outcome separate. Later funding drafts not qualified by parent runs.')
ledger['continuation']['verified_source_head']='2a1186ee1199f56c0ae9fce06d13b27f9098d3c3 published/genuine GREEN168/manifest5453/normal push+remote readback; funding draft candidate uncommitted'
ledger['continuation']['latest_checkpoint_report']='docs/rebuild/rev118/CHECKPOINT_20261027_FUNDING_DRAFTS.md'
ledger['current_action']='Finish funding draft real manifest, verified staged backup, genuine hook commit using BOTH existing candidate-build and owner-contract-refresh auth IDs, then actual committed verification against required4fd baseline. Preserve published2a main40421043580 until terminal, inspect/reconcile exact raw outcomes, normal push/readback/exact new CI. Continue complete canonical backend financial/provider/assistant/ML work;0formal unit acceptances.'
path.write_text(json.dumps(ledger,indent=2)+'\n')
(docs/'CHECKPOINT_20261027_FUNDING_DRAFTS.md').write_text(f'''# Funding draft continuation

{now}

Branch `ccr-9e07e1af-8mgz1p`, draft PR105. Published `2a1186ee1199f56c0ae9fce06d13b27f9098d3c3` passed genuine hooks, actual committed GREEN168 against `4fd466dec3910ed5de614bfbf95887ad619df5ca`, real manifest5453/zero mismatches/all tracked, normal push and independent remote readback. Intermediatea748 aggregation has no separate hosted run. This funding packet is uncommitted at documentation generation; inspect actual Git for later state.

{summary}

Final source checks report483endpoints/376schemas and no owner/frontend/consolidation drift. All original42featuregroups/105functionIDs/78surfaces remain. The real mutation registry checks374cases/383edits with no findings; that check is not execution. Use both `auth-20261022-owner-autonomous-candidate-build` and `auth-20261022-owner-owner-contract-refresh`, comma-separated, for the genuine hook. No new authorization or frozen-package amendment is issued. Do not guess the next committed GREEN number.

Exact4cc7 main40415113142 is terminalFAILED on two unwaived mandatory private-DDS-key/trusted-main-checker prerequisites; all17publicjobs succeeded.19rawZIPs independently verified and retained. Gateway5807passes/7declaredskips, trading4125/1privateDDSskip, PG26, voice117, media198, monitor258, browser/firewall, emulator18passes/4declaredskips;374canonicalidentities caught exactlyonce/383edits across9reports. Forecast40415113329 independently verified114native+6synthetic+3cold/parity0/232versions/kernel/cleanup/hashes/tree-equivalentce864a6c59a0fdd59f0d874ef9e78985b03d2b78. Earlier partial receipts remain historical.

Exact2a forecast40421043611 succeeded in both jobs and is independently reconciled:114native+6synthetic+3cold/parity0/232versions/kernel/cleanup/source-controller-report hashes/tree-equivalent76184cd978eee3dc558a2778ecb5501f2685546d. Whole-main40421043580 must be read separately; preserve it until terminal before another push. Parent proof does not qualify later funding source. Finish manifest/verified staged ZIP/normal genuine hook/actual committed baselineverify, then normal push and remote readback/exact CI when the published run is terminal.

Continue all actual remaining BE007 operations: provider quote/original-reference resolution, beneficiary verification, fresh exact A4 approval, shared reservations with orders, send/outbox, unknown-effect recovery, debit/credit settlement, reversals and verified hosted origin. Draft privacy/deletion/retention and event-kind cohort migration are not qualified. Other full financial, assistant, voice, forecast/research, crypto, backend operations, independent/native admission, host capacity/recovery, production profile/signing/deployment and Android/Artemis/S24 acceptance remain required. Zero formally accepted units. Preserve frozen131units/324requirements/1610acceptances/234contexts/349actions/93features. No frontend redesign beforeBG001, no /workspace/Van access or delegation. Van trading core remains the chosen host. Profitability requires evidence and is never guaranteed.
''')
print(json.dumps({'final_actual_passes':377,'new_case_executions':122,'pinned_hashes':1158,'rebuild':122,
    'registry':[483,376],'source_status':'BE-007 IN_PROGRESS,acceptance NOT_ISSUED','hosted4cc7_archives':19}))
