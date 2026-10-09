from pathlib import Path
from collections import Counter
import json,hashlib,subprocess,re,datetime,xml.etree.ElementTree as E
ROOT=Path('/workspace/van-audit/canon-chromium-runtime-fix-2026-10-09');OUT=ROOT.parent
ORIGINAL=OUT/'canon-pr93-4ad31883-2026-10-09';BASE='4ad31883d57ab518ba9af414aa849db6e240eb71'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
before_path=OUT/'canon-registry-r7-before-tests-inputs-2026-10-09.json';before=json.loads(before_path.read_text())
assert all(sha(ROOT/f)==h for f,h in before['files'].items())
review_path=ROOT/'docs/audit/VAN_OWNER_REGISTRY_SOURCE_REVIEW_2026-10-09-r7.json';review=json.loads(review_path.read_text())
assert all(sha(ROOT/f)==h for f,h in review['files'].items())
proof_path=OUT/'canon-native-826-source-fixture-proof-2026-10-09-r7.json';proof=json.loads(proof_path.read_text())
assert all(sha(ROOT/f)==h for f,h in proof['source_inputs_sha256'].items())
assert proof['physical_cases_executed']==0 and proof['actual_native_schema_discovery'] is False
original_head=subprocess.check_output(['git','-C',str(ORIGINAL),'rev-parse','HEAD']).decode().strip();assert original_head==BASE
assert not subprocess.check_output(['git','-C',str(ORIGINAL),'status','--porcelain']).decode().strip()
current_head=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD']).decode().strip()
old_manifests={}
old_oct8=ROOT/'docs/audit/VAN_OWNER_REGISTRY_SOURCE_REVIEW_2026-10-08.json'
assert sha(old_oct8)==sha(ORIGINAL/old_oct8.relative_to(ROOT))
old_manifests[str(old_oct8.relative_to(ROOT))]=sha(old_oct8)
for suffix,expected in [('', '8d5de0e2de6fc285266cb3c38cb56f6e74d6d347763a0c8b9b5fce47b4474192'),('-r2','aae6d956b544a1e3d1b46a218e90e11155ea7c5fba5b92ccd65925d27c99bb06'),('-r3','88aae512e9c28f98132bcd1d5b14f3d9d7ec11669952a35c94ca3aa524999a27'),('-r4','d2a21730c96323879d382fa020c607312324475810824169c88765d4c7a92364'),('-r5','060e4c1653ba1c3f4f4ff761ec9f2faa04d07fb1c736acd6f0391faf5631d5af'),('-r6','9f92777dee9a5b08d239f86fb1a23e38900bfcaea6c7fd76b13befb4fd371539')]:
 p=ROOT/f'docs/audit/VAN_OWNER_REGISTRY_SOURCE_REVIEW_2026-10-09{suffix}.json'
 assert sha(p)==expected,p;old_manifests[str(p.relative_to(ROOT))]=expected
containers=[]
def collect(v,p):
 if isinstance(v,dict):
  for k,c in v.items():
   if k.startswith(('baseline','historical')):containers.append((p+[k],c))
   else:collect(c,p+[k])
 elif isinstance(v,list):
  for i,c in enumerate(v):collect(c,p+[i])
def subset(old,new,p):
 if isinstance(old,dict):
  assert isinstance(new,dict),p
  for k,v in old.items():assert k in new,p+[k];subset(v,new[k],p+[k])
 else:assert old==new,p
preserved=0
for filename in ['owner_features.json','owner_screens.json','owner_endpoints.json']:
 rel='registries/'+filename
 old=json.loads(subprocess.check_output(['git','-C',str(ROOT),'show',BASE+':'+rel]))
 current=json.loads((ROOT/rel).read_text())
 containers.clear();collect(old,[])
 for p,v in containers:
  latest=current
  for key in p:latest=latest[key]
  subset(v,latest,[rel]+p);preserved+=1
features=json.loads((ROOT/'registries/owner_features.json').read_text());screens=json.loads((ROOT/'registries/owner_screens.json').read_text());endpoints=json.loads((ROOT/'registries/owner_endpoints.json').read_text());schemas=json.loads((ROOT/'registries/owner_endpoint_schemas.json').read_text())
counts={'features':len(features['features']),'functions':sum(len(f['current_implementation']['functions']) for f in features['features']),'surfaces':len(screens['screens']),'endpoints':len(endpoints['endpoints']),'schemas':len(schemas['components']['schemas'])}
assert counts=={'features':42,'functions':105,'surfaces':78,'endpoints':432,'schemas':251}
deployments=[r['deployment_requirements'] for r in features['features']+screens['screens'] if r.get('deployment_requirements')]
assert len(deployments)==5
for d in deployments:
 assert d['topology']=='CORE_ONLY_V2' and d['schema_version']==2
 assert d['backend_host']==d['hermes_host']==d['phone_ingress_host']==d['ingress_host']=='van-trading-core'
 assert d['artemis_host']=='dial-control' and not d['oracle_admin_runtime_dependency']
 assert d['status']=='PREPARED_CORE_ONLY_V2_LIVE_PROFILE_RELEASE_AND_INGRESS_UNQUALIFIED'
checked=0
def current(v,h=False):
 global checked
 if isinstance(v,dict):
  if not h and {'file','line','ref','sha256'}<=v.keys() and v['ref']=='WORKSPACE_PATCH':assert sha(ROOT/v['file'])==v['sha256'],v;checked+=1
  for k,c in v.items():current(c,h or k.startswith(('baseline','historical')))
 elif isinstance(v,list):
  for c in v:current(c,h)
 elif isinstance(v,str) and not h:assert 'dial-control supplies Hermes and Artemis' not in v,v
for doc in (features,screens):current(doc)
html=(ROOT/'docs/audit/OWNER_FRONTEND_CONTRACT.html').read_text();match=re.search(r'<script id="registry" type="application/json">(.*?)</script>',html,re.S);assert match
assert json.loads(match.group(1))=={'features':features['features'],'screens':screens['screens'],'endpoints':endpoints['endpoints']}
results=[]
for name,expected in [('canon-current-registry-contracts-2026-10-09-r7.xml',19),('canon-native-plan-contracts-2026-10-09-r7.xml',39)]:
 p=OUT/name;suites=E.parse(p).findall('testsuite');vals={k:sum(int(s.attrib.get(k,0)) for s in suites) for k in ['tests','failures','errors','skipped']}
 assert vals=={'tests':expected,'failures':0,'errors':0,'skipped':0},vals
 results.append({'junit_path':str(p),'junit_sha256':sha(p),**vals,'seconds':sum(float(s.attrib.get('time',0)) for s in suites)})
receipt={'record_kind':'SCOPED_REGISTRY_AND_NATIVE_FIXTURE_QUALIFICATION','phase':'r7_actual_chromium_runtime_corrections_source','measured_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'outcome':'PASS_LOCAL_SOURCE_CONTRACTS_ONLY','application_parent_sha':current_head,'checkout_state':'UNCOMMITTED_SOURCE_PATCH_IDENTIFIED_BY_EXACT_FILE_HASHES_NOT_A_CLEAN_COMMIT_CLAIM','results':results,'counts':counts,'current_source_citations_hash_verified':checked,'original_baseline_historical_containers_preserved':preserved,'current_declared_core_only_deployment_requirements':len(deployments),'searchable_html_payload_matches_current_registries':True,'immutable_base_checkout_head':original_head,'immutable_base_checkout_clean':True,'immutable_prior_manifests_sha256':old_manifests,'before_tests_input_manifest_path':str(before_path),'before_tests_input_manifest_sha256':sha(before_path),'before_and_after_scoped_tests_inputs_equal':True,'source_review_manifest_path':str(review_path),'source_review_manifest_sha256':sha(review_path),'source_review_input_count':len(review['files']),'source_review_inputs_sha256':review['files'],'native_fixture_proof_path':str(proof_path),'native_fixture_proof_sha256':sha(proof_path),'native_fixture_plan_coverage':proof['coverage'],'native_fixture_case_kinds':proof['case_kinds'],'native_fixture_plan_input_count':proof['source_input_count'],'native_fixture_inputs_unchanged_after_checks':True,'actual_native_schema_discovery':False,'runtime_admission_verified':False,'physical_cases_executed':0,'owner_release':False,'deployment_accepted':False,'authority_effect':'No authorization record, enforcement baseline, ledger, merge, push or owner approval was created by this registry review. Root handles any separately required truthful ledger row.','limitations':['Local registry/source contract qualification at final r7 measured files. Parent must separately qualify the final clean committed source across full backend/Android/component suites.','Native826 consistency uses an explicitly synthetic schema and no actual DIAL/Artemis discovery, admission, device or live service was observed.','Production deployment, protected-state preservation, ingress/firewalls, owner release/provisioning, provider qualification and S24 acoustic/visual/effect acceptance require their own actual observations.']}
p=OUT/'canon-registry-and-native-contracts-qualification-2026-10-09-r7.json'
with p.open('x') as f:json.dump(receipt,f,indent=2);f.write('\n')
p.chmod(0o444)
print(json.dumps({'receipt_path':str(p),'receipt_sha256':sha(p),'review_manifest_sha256':sha(review_path),'tests':sum(r['tests'] for r in results),'counts':counts,'current_citations':checked,'historical_baseline_containers_preserved':preserved,'physical_cases_executed':0}))
