"""Independent Rev1.15 document regression checks; never application/venue evidence."""
import copy,hashlib,importlib.util,json,tempfile,zipfile
from pathlib import Path
from jsonschema import Draft202012Validator
P=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('revision',P/'verification/verify_rev115.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
d={k:v.read(p) for k,p in v.FILES.items()}
parents={k:v.read('lineage/rev1_13/'+p)[field] for k,(p,field) in v.PARENTS.items()}
rows=[]
def require(id,ok,detail=None):
 rows.append({'id':id,'passed':bool(ok),'detail':detail})
def reseal(x):
 for key,coll,field in [('requirements','requirements','requirements'),('tests','tests','tests'),('actions','actions','actions'),('truth','truth','truth_atoms'),('units','plan','units'),('surfaces','surfaces','surfaces')]:x['lock']['objects'][key]={a['id']:v.digest(a) for a in x[coll][field]}

parentzip=P/'lineage/REV1_14_EXACT_PARENT.zip'
require('EXACT_PARENT_ARCHIVE',hashlib.sha256(parentzip.read_bytes()).hexdigest()=='f12020bd852d2c3a6f8f8ee237f4cf7a3dba7665762d05f984f0eae271f4dc37')
with zipfile.ZipFile(parentzip) as z:
 root='VAN_NEXT_UNIFIED_REBUILD_REV1_14_20261018/'
 manifest=json.loads(z.read(root+'MANIFEST.json'))
 require('PARENT_MEMBERS',all(hashlib.sha256(z.read(root+p)).hexdigest()==m['sha256'] for p,m in manifest['files'].items()))
 for path,field in [('traceability/REQUIREMENTS_AND_DU_MAPPING.json','requirements'),('verification/TEST_CONTRACTS.json','tests'),('traceability/LEGACY_349_ACTIONS.json','actions'),('traceability/PRODUCT_TRUTH.json','truth_atoms'),('design/ALL_SURFACE_CONTRACTS.json','surfaces')]:
  old=json.loads(z.read(root+path))[field];new={r['id']:r for r in v.read(path)[field]}
  require('PRESERVE_'+field,all(r==new.get(r['id']) for r in old),{'parent':len(old),'current':len(new)})
 old=json.loads(z.read(root+'plan/DEVELOPMENT_PLAN.json'))['units'];new=d['plan']['units']
 require('PRESERVE_UNIT_IDENTITIES',[(r['id'],r['packet_id'],r['sequence'],r['dependencies']) for r in old]==[(r['id'],r['packet_id'],r['sequence'],r['dependencies']) for r in new])
 for f in ['design/VAN_LOCKED_DARK.png','design/VAN_LOCKED_LIGHT.png','design/VAN_MATERIAL_TOKENS_REV2.json']:
  require('VISUAL_'+Path(f).name,z.read(root+f)==(P/f).read_bytes())

x=copy.deepcopy(d)
next(t for m in x['machines']['machines'] if m['id']=='SO-CHILD' for t in m['transitions'] if t['to']=='SUBMITTING')['proof_predicates'].remove('POLICY_QUALIFIED')
reseal(x);errors=v.check(x,parents,False)
require('SEMANTIC_DISPATCH_WITH_LOCKS_RESEALED',any('CRITICAL_EDGE_PROOF_MISSING:SO-CHILD-T002:POLICY_QUALIFIED'==e for e in errors),errors)
for mid,target,proof in [('SO-CHILD','CANCEL_REQUESTED','CANCEL_SCOPE_AUTHORIZED'),('SO-BINDING','EXPIRED','BINDING_EXPIRED'),('SO-CANDIDATE','CANCELLED','RESEARCH_STOP_AUTHORIZED')]:
 x=copy.deepcopy(d);t=next(t for m in x['machines']['machines'] if m['id']==mid for t in m['transitions'] if t['to']==target);t['proof_predicates'].remove(proof)
 reseal(x);errors=v.check(x,parents,False)
 require('SEMANTIC_DROP_'+proof,any(e.startswith('CRITICAL_EDGE_PROOF_MISSING:'+t['id']) and proof in e for e in errors),errors)
for state in ('AUTHORIZED','ACTIVE','SUSPENDED','DRAINING'):
 x=copy.deepcopy(d);m=next(m for m in x['machines']['machines'] if m['id']=='SO-BINDING');m['transitions']=[t for t in m['transitions'] if (t['from'],t['to'])!=(state,'EXPIRED')]
 reseal(x);require('SEMANTIC_EXPIRY_'+state,'MISSING_BINDING_EXPIRY:'+state in v.check(x,parents,False))
for a,b in [('OUTCOME_UNKNOWN','CANCELLED'),('OUTCOME_UNKNOWN','EXPIRED'),('CANCEL_REQUESTED','OUTCOME_UNKNOWN'),('FILLED','OUTCOME_UNKNOWN')]:
 x=copy.deepcopy(d);m=next(m for m in x['machines']['machines'] if m['id']=='SO-CHILD')
 m['transitions']=[t for t in m['transitions'] if (t['from'],t['to'])!=(a,b)];reseal(x)
 errors=v.check(x,parents,False);require('SEMANTIC_REMOVE_'+a+'_'+b,'MISSING_UNKNOWN_RECOVERY:'+a+':'+b in errors,errors)

ex={}
for rel in d['example_index']['fixtures']:
 r=v.read('contracts/self_optimization/'+rel);ex[r['record_type']]=r
val=Draft202012Validator(d['schemas'])
require('ALL_POSITIVE_SCHEMA_FIXTURES',all(val.is_valid(r) for r in ex.values()))
for prop in ['price_tick','base_step','maximum_quantity_base']:
 x=copy.deepcopy(ex['CryptoVenueProfile']);x[prop]='0';require('ZERO_REJECTED_'+prop,not val.is_valid(x))
 x[prop]='0.001';require('POSITIVE_DECIMAL_'+prop,val.is_valid(x))
x=copy.deepcopy(ex['ExecutionQualityMeasurement']);x['measurement_state']='MATURE';x['explicit_nonembedded_cost_quote']=None
require('MATURE_UNKNOWN_COST_REJECTED',not val.is_valid(x))
x['measurement_state']='UNKNOWN';require('UNKNOWN_COST_PRESERVED',val.is_valid(x))
x=copy.deepcopy(ex['ExecutionOutcome']);x['maturity']['eligible_for_estimator']=True;x['maturity']['fees_complete']=False
require('IMMATURE_ELIGIBILITY_REJECTED',not val.is_valid(x))

f=copy.deepcopy(d['fixture']);base=v.fixture_model(f)
require('POSITIVE_REFERENCE_LOOP',base[0][2]=='A' and base[0][5]=='B' and base[0][6]=='B')
e=copy.deepcopy(f['events'][0]);e.update(id='correction-r2',cursor=7,observation_revision=2,fill_price='99.0');f['events'].append(e)
corrected=v.fixture_model(f)
e2=copy.deepcopy(e);e2.update(id='late-old-r1',cursor=8,observation_revision=1,fill_price='105.0');f['events'].append(e2)
result=v.fixture_model(f)
require('STALE_REVISION_DOES_NOT_CHANGE_CHOICE',result[0][8]==corrected[0][7]=='A',{'before':corrected[1],'after':result[1]})
require('REFERENCE_REPLAY',v.fixture_model(copy.deepcopy(f))==result,'Fresh-memory reference replay only; actual process durability NOT_TESTED')
e3=copy.deepcopy(e);e3.update(id='conflict-r2',cursor=9,fill_price='108.0');f['events'].append(e3)
try:v.fixture_model(f);error=None
except ValueError as exc:error=str(exc)
require('EQUAL_REVISION_CONFLICT',error=='CONFLICTING_REVISION',error)

by={r['id']:r for r in d['requirements']['requirements']};ts={r['id'] for r in d['tests']['tests']}
for r in v.read('traceability/REV115_REQUIREMENTS.json')['requirements']:
 require('NEW_REQUIREMENT_'+r['id'],by.get(r['id'])==r and set(r['test_ids']).issubset(ts))
require('COUNTS',len(by)==309 and len(ts)==1544 and len(d['plan']['units'])==131)
components={c['requirement_id'] for c in v.read('contracts/self_optimization/COMPONENT_LEDGER.json')['components']}
for r in v.read('traceability/REV115_REQUIREMENTS.json')['requirements']:require('COMPONENT_'+r['id'],r['id'] in components)
require('NO_CERTIFICATES_OR_APP_RESULTS',d['f15']['status']==d['bg']['status']=='NOT_ISSUED' and all(t['execution_state']=='NOT_RUN' for t in d['tests']['tests']))
for dc in v.read('review/DESIGN_CHANGE_PROPOSALS.json')['proposals']:
 require('DCP_LINKS_'+dc['id'],dc['requirement'] in by and set(dc['acceptance_test_refs']).issubset(ts) and dc['financial_activation']=='NONE')
focus=(P/d['authority']['focused_blueprint']).read_text().rstrip();master=(P/d['authority']['master']).read_text()
require('MASTER_EMBEDS_FOCUSED_SPEC',focus in master)
require('NO_NET_INVENTORY_BUDGET_FORMULA','cumulative_net_filled' not in focus)
require('NO_EXTRA_DEPLOYABLES',d['plan']['new_deployable_services_required']==0)
out={'scope':'DOCUMENT_ONLY_NOT_APPLICATION_OR_ECONOMIC_VALIDATION','passed':sum(r['passed'] for r in rows),'total':len(rows),'application_tests_executed':0,'cases':rows}
print(json.dumps(out,indent=2));raise SystemExit(0 if all(r['passed'] for r in rows) else 1)
