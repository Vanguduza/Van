from pathlib import Path
from collections import Counter
import json,hashlib,datetime,sys
ROOT=Path('/workspace/van-audit/canon-chromium-runtime-fix-2026-10-09')
OUT=ROOT.parent
sys.path.insert(0,str(ROOT))
from tools.certification import artemis_acceptance as a
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def immutable(name,value):
 p=OUT/name
 with p.open('x') as f:json.dump(value,f,indent=2);f.write('\n')
 p.chmod(0o444)
 return p
review_path=ROOT/'docs/audit/VAN_OWNER_REGISTRY_SOURCE_REVIEW_2026-10-09-r7.json'
review=json.loads(review_path.read_text())
assert all(sha(ROOT/f)==h for f,h in review['files'].items())
inputs=dict(review['files'])
for f in ['registries/owner_features.json','registries/owner_screens.json','registries/owner_endpoints.json','registries/owner_endpoint_schemas.json','docs/audit/OWNER_FRONTEND_CONTRACT.html','docs/audit/VAN_OWNER_REGISTRY_SOURCE_REVIEW_2026-10-09-r7.json','tests/contracts/test_owner_endpoint_registry.py','tests/contracts/test_owner_redesign_registry.py','tests/contracts/test_native_artemis_plan.py']:
 inputs[f]=sha(ROOT/f)
immutable('canon-registry-r7-before-tests-inputs-2026-10-09.json',{'record_kind':'SOURCE_INPUTS_BEFORE_SCOPED_LOCAL_QUALIFICATION','measured_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':inputs,'review_manifest_sha256':sha(review_path),'physical_cases_executed':0,'deployment_accepted':False,'owner_release':False})
fields={'task_desc','device_serial','model','locked_app_package','verification_level','expected_output_desc'}
tools={n:{} for n in ('mobile_manage_task','mobile_inspect_trace','mobile_get_device_state','mobile_diagnose')}
tools['mobile_run_task']={'properties':{n:{'type':'string'} for n in sorted(fields)},'required':['task_desc']}
schema={'record_kind':'NATIVE_ARTEMIS_SCHEMA_DISCOVERY','route':'NATIVE_ARTEMIS_MCP_DIRECT_COMMANDER','root':'/unit/native-artemis-not-live','tools':tools,'source_fixture':True,'actual_discovery':False,'notice':'Synthetic source-contract fixture. No live tool was discovered and no runtime/device was admitted.'}
schema_path=immutable('NATIVE_ARTEMIS_SCHEMA_FIXTURE_NOT_DISCOVERY_2026-10-09-r7.json',schema)
plan=a.build_plan(root=ROOT,dds_root=Path('/nonexistent-dds-not-required'),native_schema=schema)
assert plan['coverage']=={'features':42,'functions':105,'surfaces':78,'cases':826},plan['coverage']
kinds=dict(Counter(c['kind'] for c in plan['cases']))
assert kinds=={'feature':420,'function':238,'surface':156,'cross_cutting':12},kinds
assert len({c['id'] for c in plan['cases']})==826
assert plan['target']['backend']==plan['target']['hermes']=='van-trading-core'
assert plan['target']['artemis']=='dial-control'
assert plan['target']['device_transport']==a.WIRELESS_ADB
assert plan['target']['device_serial']=='RFCX2054F5W'
assert 'hermes_and_artemis' not in plan['target']
assert plan['physical_cases_executed']==0
assert plan['transport_adaptation']['verified_applicable_cases']==0
assert not plan['dds_readiness_required'] and not plan['governed_schema_sources']
assert plan['status']=='NATIVE_PLAN_PREPARED_NOT_EXECUTED'
assert all(sha(ROOT/f)==h for f,h in plan['inputs_sha256'].items())
plan_path=immutable('VAN_NATIVE_ARTEMIS_SOURCE_FIXTURE_PLAN_2026-10-09-r7.json',plan)
proof={'record_kind':'NATIVE_ARTEMIS_SOURCE_FIXTURE_PLAN_CONSISTENCY_PROOF','created_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'outcome':'SOURCE_FIXTURE_CONTRACT_CONSISTENCY_ONLY','source_fixture':True,'actual_native_schema_discovery':False,'runtime_admission_verified':False,'actual_device_binding_verified':False,'physical_cases_executed':0,'transport_verified_applicable_cases':0,'owner_release':False,'deployment_accepted':False,'coverage':plan['coverage'],'case_kinds':kinds,'function_case_breakdown':{'happy_and_error':210,'explicit_function_recovery':28},'target':plan['target'],'plan_internal_sha256':plan['plan_sha256'],'schema_fixture_path':str(schema_path),'schema_fixture_file_sha256':sha(schema_path),'plan_path':str(plan_path),'plan_file_sha256':sha(plan_path),'source_review_manifest':str(review_path),'source_review_manifest_sha256':sha(review_path),'source_input_count':len(plan['inputs_sha256']),'source_inputs_sha256':plan['inputs_sha256'],'evidence_limits':['Source-derived candidate matrix only; fixture schema does not prove actual Artemis exposure, admission, pairing, transport or execution.','No owner release, deployment, provider, firewall or handset result is inferred.','Use actual current native schema discovery and actual paired device identity before executing the prepared cases.']}
proof_path=immutable('canon-native-826-source-fixture-proof-2026-10-09-r7.json',proof)
print(json.dumps({'review_manifest_sha256':sha(review_path),'source_review_inputs':len(review['files']),'coverage':plan['coverage'],'case_kinds':kinds,'plan_input_count':len(plan['inputs_sha256']),'proof_path':str(proof_path),'proof_sha256':sha(proof_path),'physical_cases_executed':0}))
