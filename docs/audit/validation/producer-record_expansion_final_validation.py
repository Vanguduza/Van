"""Bind final local runner evidence to exact source without live-readiness claims."""
from pathlib import Path
from collections import Counter
import hashlib,json,shutil,subprocess,xml.etree.ElementTree as ET

ROOT=Path('/workspace/Van')
OUT=ROOT/'docs/audit/validation'
WORK=Path('/workspace/van-audit')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())
def verify(files):
    changed=[p for p,h in files.items() if not(ROOT/p).is_file() or sha(ROOT/p)!=h]
    assert not changed,changed[:20]
def counts(xml):
    d=ET.parse(xml).getroot()
    totals={k:sum(int(s.attrib.get(k,0)) for s in d.iter('testsuite')) for k in ('tests','failures','errors','skipped')}
    assert totals['failures']==totals['errors']==0,(str(xml),totals)
    totals['passed']=totals['tests']-totals['skipped']
    skips=[{'case':c.attrib.get('classname','')+'::'+c.attrib['name'],'reason':c.find('skipped').attrib.get('message','')}
        for c in d.iter('testcase') if c.find('skipped') is not None]
    return totals,skips
def artifact(p):return {'path':str(p.relative_to(ROOT)),'sha256':sha(p)}

freeze=OUT/'van-production-source-freeze-2026-10-08.json'
f=load(freeze);verify(f['files'])
checks=[]
selections=[
    ('backend','backend-expansion-frozen-final-2026-10-08-r2','backend/tests'),
    ('contracts','contracts-expansion-frozen-final-2026-10-08-r4','tests/contracts'),
    ('trading','trading-expansion-frozen-final-2026-10-08-r3','trading/tests'),
    ('hermes_and_scenarios','hermes-scenarios-expansion-frozen-final-2026-10-08-r3','tests/hermes hermes/policy/tests tests/scenarios'),
    ('native_browser_services','browser-services-expansion-final-2026-10-08','services'),
]
for scope,stem,selection in selections:
    evidence_root=OUT if scope=='contracts' else WORK
    xml=evidence_root/(stem+'.xml');log=evidence_root/(stem+'.log')
    assert xml.is_file() and log.is_file(),stem
    totals,skips=counts(xml)
    related=[p for p in evidence_root.glob(stem+'*.json') if p.is_file()]
    for p in [xml,log,*related]:
        if p.resolve()!=(OUT/p.name).resolve():shutil.copy2(p,OUT/p.name)
    checks.append({'scope':scope,'selection':selection,'status':'PASS','counts':totals,'skips':skips,
        'junit':artifact(OUT/xml.name),'log':artifact(OUT/log.name),
        'source_receipts':[artifact(OUT/p.name) for p in related]})
    if scope in {'backend','trading','hermes_and_scenarios'}:
        inputs=load(WORK/(stem+'-inputs.json'))
        result=load(WORK/(stem+'-result.json'))
        assert result['exit_code']==0
        if scope=='backend':
            qualification_path=OUT/'backend-component-requalification-2026-10-08.json'
            qualification=load(qualification_path)
            assert qualification['status']=='CURRENT_BACKEND_COMPONENT_AND_ANDROID_SOURCE_CONTRACT_PASS'
            assert qualification['full_junit_sha256']==sha(xml)
            assert qualification['final_production_manifest_sha256']==sha(freeze)
            excluded=qualification['changed_global_inputs']
            assert excluded==['android/app/src/main/java/com/dial/van/browser/BrowserPhoneActions.kt']
            verify({p:h for p,h in inputs['files'].items() if p not in excluded})
            checks[-1]['component_requalification']=artifact(qualification_path)
        else:
            verify(inputs['files'])
            assert result['source_unchanged_during_test']
            assert result['production_manifest_sha256']==sha(freeze)
    elif scope=='native_browser_services':
        receipt=load(WORK/(stem+'.source-inputs.json'))
        # Native collector independently includes tests, deployment package locks
        # and every imported protocol instead of irrelevant gateway modules.
        assert receipt['source_inputs_unchanged'] and receipt['exit_code']==0
        verify(receipt['source_sha256'])
    elif scope=='contracts':
        result=load(OUT/(stem+'-result.json'))
        assert result['exit_code']==0 and result['source_unchanged_during_test']
        assert result['production_manifest_sha256']==sha(freeze)
        before=load(ROOT/result['before_snapshot']);verify(before['files'])
        assert all(Path(p).is_file() and sha(Path(p))==h for p,h in before['external_files'].items())

a_path=OUT/'android-owner-controls-final-receipt-2026-10-08-r2.json'
a=load(a_path);verify(a['source_files'])
assert a['status']=='LOCAL_BUILD_TEST_LINT_NATIVE_ALIGNMENT_PASS'
assert not a['source_changed_during_final_validation']
assert sha(ROOT/a['apk']['path'])==a['apk']['sha256']
for suite in a['xml'].values():verify(suite['files'])
for entry in a['logs'].values():assert sha(ROOT/entry['path'])==entry['sha256']
assert a['checks']['jvm']['failures']==a['checks']['app_unit']['failures']==0

feature_path=ROOT/'registries/owner_features.json';screen_path=ROOT/'registries/owner_screens.json'
features=load(feature_path);screens=load(screen_path)
ep_path=ROOT/'registries/owner_endpoints.json';schema_path=ROOT/'registries/owner_endpoint_schemas.json'
endpoints=load(ep_path);schemas=load(schema_path)
plan_path=ROOT/'docs/audit/VAN_ARTEMIS_ACCEPTANCE_PLAN_2026-10-08.json';plan=load(plan_path)
registry_counts={'features':len(features['features']),
    'functions':sum(len(v.get('current_implementation',{}).get('functions',[])) for v in features['features']),
    'screens':len(screens['screens']),'endpoints':len(endpoints['endpoints']),
    'schemas':len(schemas.get('components',{}).get('schemas',{})), 'prepared_acceptance_cases':len(plan['cases'])}
assert features['current_source_qualification']['source_freeze_sha256']==sha(freeze)
assert plan['physical_cases_executed']==0
main_counts={'passed':sum(c['counts']['passed'] for c in checks)+a['checks']['jvm']['passed']+a['checks']['app_unit']['passed'],
    'skipped':sum(c['counts']['skipped'] for c in checks),'failed':0,'errors':0}
guards_path=OUT/'android-release-guards-supplement-2026-10-08-r2.json'
guards=load(guards_path);verify(guards['source_files'])
assert guards['checks']['release_guards']['passed']==2 and not guards['source_changed_during_validation']
assert sha(ROOT/guards['junit_xml']['path'])==guards['junit_xml']['sha256']
pg_path=OUT/'trading-postgres-retained-input-check-2026-10-08.json'
pg=load(pg_path);verify(pg['current_inputs_sha256'])
assert pg['all_5_current_inputs_match'] and pg['prior_fixture_source_matches']
assert sha(ROOT/pg['prior_receipt'])==pg['prior_receipt_sha256']
dds_path=OUT/'trading-dial-resolver-retained-input-check-2026-10-08.json'
dds=load(dds_path);assert dds['all_current_inputs_match']
assert sha(ROOT/dds['prior_receipt'])==dds['prior_receipt_sha256']
for row in dds['inputs']:
    base=ROOT if row['repository']=='van' else Path('/workspace/dial-development-system')
    assert sha(base/row['path'])==row['prior_sha256']==row['current_sha256']
expected_skips={
    'test_actual_agp_direct_package_release_refuses_missing_core_deployment_profile',
    'test_actual_agp_valid_target_still_refuses_missing_production_signing',
    'test_postgres_ledger_matches_sqlite_chain_and_detects_tampering',
    'test_dial_resolver_selects_trading_knowledge_from_van_registry'}
actual_skips={s['case'].split('::')[-1] for c in checks for s in c['skips']}
assert actual_skips==expected_skips,actual_skips
supplements=[{'scope':'actual_release_refusal','qualification':'FRESH_CURRENT_SOURCE_EXECUTION','passed':2,'receipt':artifact(guards_path)},
    {'scope':'isolated_real_postgres_ledger','qualification':'RETAINED_EXECUTION_WITH_UNCHANGED_INPUTS','qualified_cases':1,'receipt':artifact(pg_path)},
    {'scope':'readonly_DDS_resolver','qualification':'RETAINED_EXECUTION_WITH_UNCHANGED_INPUTS','qualified_cases':1,'receipt':artifact(dds_path)}]

doc={'schema_version':1,'status':'CURRENT_SOURCE_LOCAL_VALIDATION_PASS_WITH_EXTERNAL_PREREQUISITES',
    'repository':'Vanguduza/Van','base_commit':f['base_commit'],'source_manifest':artifact(freeze),
    'production_source_files':len(f['files']),'checks':checks,
    'android':{'receipt':artifact(a_path),'jvm':a['checks']['jvm'],'app_unit':a['checks']['app_unit'],
        'debug_apk':a['apk'],'lint':a['checks']['lint'],'native_libraries':len(a['checks']['native_arm64']),
        'native_16k_alignment':'PASS','zipalign_16k':'PASS'},
    'disjoint_runner_executions':main_counts,
    'supplemental_skip_qualification':supplements,
    'fresh_passing_disjoint_executions_including_release_guards':main_counts['passed']+2,
    'retained_passing_cases_with_unchanged_inputs':2,
    'qualified_current_source_cases':main_counts['passed']+4,
    'registry':{'counts':registry_counts,'wiring_status_counts':dict(Counter(v.get('functional_wiring_status') for v in features['features'])),
        'features':artifact(feature_path),'screens':artifact(screen_path),'endpoints':artifact(ep_path),'schemas':artifact(schema_path),'acceptance_plan':artifact(plan_path)},
    'deployment_choice':{'gateway':'van-trading-core','hermes':'dial-control profile van',
        'device_actuator':'NATIVE_ARTEMIS_VIA_DIAL_COMMANDER'},
    'physical_tests_executed':0,'owner_release_built':False,'production_deployed':False,
    'live_provider_canaries_run':False,'only_s24_testing_remains':False,
    'external_prerequisites':['Callable authorized DIAL/Commander production route',
        'Actual van-trading-core deployment, private Hermes connectivity, valid gateway trust and live firewall evidence',
        'Existing owner production signer, attestation/provisioning bindings and verified release packet',
        'Governed Oracle/VEKL owner-artifact target contract and canonical admission/introspection integration',
        'Qualified production voice/acoustic assets; Rive redesign remains separately deferred',
        'Publish the saved managed environment configuration draft'],
    'scope':'Disjoint complete local suites and independent Android build evidence, with exact byte bindings. Focused overlapping tests excluded from totals. Native browser tests use controlled TLS/CDP/WebRTC fixtures. No actual production service, provider, signed owner release, or S24 qualification.',
    'source_control':{'committed':False,'pushed':False,
        'dds_modified':bool(subprocess.check_output(['git','status','--porcelain'],cwd='/workspace/dial-development-system').strip())}}
output=ROOT/'docs/audit/VAN_PRE_S24_VALIDATION_2026-10-08.json'
output.write_text(json.dumps(doc,indent=2)+'\n')
print(json.dumps({'receipt':str(output),'sha256':sha(output),'counts':main_counts,'registry':registry_counts}))
