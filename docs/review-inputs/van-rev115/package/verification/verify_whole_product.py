#!/usr/bin/env python3
"""Rev1.18 full-scope document, compiled acceptance and protocol checks; no native claims."""
import copy,hashlib,importlib.util,json,subprocess,sys
from pathlib import Path
from jsonschema import Draft202012Validator,FormatChecker
P=Path(__file__).resolve().parents[1];D='contracts/whole_product/'
def rd(f):return json.loads((P/f).read_text())
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def load():
 return {'actions':rd(D+'ACTION_CONTRACTS.json'),'bindings':rd(D+'FEATURE_CONTEXT_BINDINGS.json'),'caps':rd(D+'CAPABILITY_BOUNDARIES.json'),'issues':rd(D+'ISSUE_DISPOSITION.json'),'qual':rd(D+'QUALIFICATION_REGISTER.json'),'ref':rd(D+'ACCEPTANCE_REFINEMENTS.json'),'scenarios':rd(D+'DOMAIN_SCENARIOS.json'),'effective':rd('verification/EFFECTIVE_TEST_CONTRACTS_REV118.json'),'plan':rd('plan/DEVELOPMENT_PLAN.json'),'schema':rd(D+'RECORDS.schema.json'),'protocol':rd(D+'PROTOCOLS.json')}
def structural(d):
 e=[]
 def need(ok,msg):
  if not ok:e.append(msg)
 original=rd('traceability/LEGACY_349_ACTIONS.json')['actions'];aa={a['action_id']:a for a in d['actions']['actions']};old={a['id']:a for a in original}
 need(len(d['actions']['actions'])==len(aa)==349 and set(aa)==set(old),'ACTION_COVERAGE')
 for i,a in old.items():
  x=aa.get(i,{})
  need(x.get('owner_goal')==a['text'] and x.get('context_id')==a['surface_id'] and x.get('test_id')==a['test_id'],'ACTION_IDENTITY:'+i)
  need(x.get('classification') in d['actions']['profiles'],'ACTION_PROFILE:'+i)
  need(all(len(x.get(k,''))>40 for k in ['positive_oracle','negative_oracle','recovery_oracle']),'ACTION_ORACLES:'+i)
 features=rd('traceability/REV2_93_FEATURE_CROSSWALK.json')['features'];surfaces=rd('design/ALL_SURFACE_CONTRACTS.json')['surfaces'];services=rd('contracts/BACKEND_SERVICE_CATALOG.json')['services'];tests={t['id']:t for t in d['effective']['tests']};units={u['id']:u for u in d['plan']['units']}
 need(len(tests)==len(d['effective']['tests'])==1610,'EFFECTIVE_TEST_COUNT')
 need(d['plan'].get('acceptance_owner_extensions')==d['ref']['owner_additions'],'CANONICAL_OWNER_EXTENSIONS')
 need(d['bindings']['features']==features,'FEATURE_COVERAGE')
 cc=d['bindings']['contexts'];need(len(cc)==234 and {c['context_id'] for c in cc}=={s['id'] for s in surfaces},'CONTEXT_COVERAGE')
 need(len(d['caps']['boundaries'])==82 and {s['id'] for s in d['caps']['boundaries']}=={s['id'] for s in services},'CAPABILITY_COVERAGE')
 need({s['id'] for s in d['qual']['entries']}=={s['id'] for s in services},'QUALIFICATION_COVERAGE')
 for q in d['qual']['entries']:need(q['runtime_state']=='NOT_QUALIFIED' and q['receipt_refs']==[],'FABRICATED_QUALIFICATION:'+q['id'])
 for f in features:
  owners={u for tid in f['test_ids'] for u in [tests[tid]['unit'],*tests[tid].get('additional_units',[])]}
  need(f['primary_frontend_unit'] in owners,'PRIMARY_OWNER:'+f['id'])
 for c in cc:
  need(set(c['backend_units']+c['frontend_units'])<=set(units),'CONTEXT_OWNERS:'+c['context_id'])
 need('FE-021' in next(c['frontend_units'] for c in cc if c['context_id']=='VNX-S-PRESENCE-05'),'VOICE_CONTEXT_OWNER')
 for t in tests.values():
  need(t['execution_state']=='NOT_RUN','FALSE_RESULT:'+t['id'])
  for uid in [t['unit'],*t.get('additional_units',[])]:need(t['id'] in units.get(uid,{}).get('acceptance_test_ids',[]),'EFFECTIVE_PLAN_OWNER:'+t['id']+':'+uid)
 for a in aa.values():need(tests[a['test_id']].get('required_assertions',{}).get('positive')==a['positive_oracle'],'MISSING_COMPILED_ORACLE:'+a['action_id'])
 issues=d['issues']['issues'];need(len(issues)==16 and {x['id'] for x in issues}=={f'WPC-{i:03}' for i in range(1,17)},'ISSUE_COVERAGE')
 for i in issues:need(i['runtime_status']=='NOT_QUALIFIED' and set(i['owners'])<=set(units) and bool(i['implementation_acceptance']),'ISSUE_BOUNDARY:'+i['id'])
 sc=d['scenarios']['scenarios'];need(len(sc)==len({s['id'] for s in sc})==72,'SCENARIO_COUNT')
 families=rd(D+'DOMAIN_DELIVERY_CONTRACTS.json')['families'];need(len(families)==24,'FAMILY_COUNT')
 need({u for f in families for u in f['backend_units']}=={s['id'] for s in services},'FAMILY_BACKEND_COVERAGE')
 for f in families:need({s['kind'] for s in sc if s['family']==f['id']}=={'POS','NEG','REC'},'FAMILY_SCENARIOS:'+f['id'])
 for s in sc:need(s['test_id'] in tests and s['state']=='NOT_RUN','SCENARIO_BINDING:'+s['id'])
 edges={(x['from'],x['to']):x['guard'] for x in d['protocol']['command_transitions']}
 need(('OUTCOME_UNKNOWN','DISPATCHING') not in edges,'UNKNOWN_REDISPATCH')
 for edge in [('RUNNING','SUCCEEDED'),('RUNNING','OUTCOME_UNKNOWN'),('DISPATCHING','OUTCOME_UNKNOWN'),('CANCEL_REQUESTED','CANCELLED'),('CANCEL_REQUESTED','SUCCEEDED'),('OUTCOME_UNKNOWN','SUCCEEDED')]:need(bool(edges.get(edge)),'MISSING_TRANSITION:'+str(edge))
 voice=d['protocol']['voice_ordering'];need(voice['partial_transcripts_can_dispatch'] is False and voice['late_cancelled_generation_can_play'] is False and voice['effect_completion_requires_readback'] is True and voice['speaker_similarity_is_authorization'] is False,'VOICE_AUTHORITY')
 return sorted(set(e))
def main():
 d=load();rows=[]
 def test(name,ok,detail=None):rows.append({'id':name,'passed':bool(ok),'detail':detail})
 errs=structural(d);test('INTEGRATION',not errs,errs)
 baseline=rd('lineage/REV117_WHOLE_PRODUCT_FINGERPRINTS.json')
 for name,file,key in [('requirements','traceability/REQUIREMENTS_AND_DU_MAPPING.json','requirements'),('tests','verification/TEST_CONTRACTS.json','tests'),('actions','traceability/LEGACY_349_ACTIONS.json','actions'),('surfaces','design/ALL_SURFACE_CONTRACTS.json','surfaces')]:
  current={x['id']:digest(x) for x in rd(file)[key]};test('PRESERVE_'+name,current==baseline['objects'][name])
 test('UNIT_GRAPH_PRESERVED',[{k:u[k] for k in ['id','packet_id','sequence','dependencies']} for u in d['plan']['units']]==baseline['units'])
 a=rd('CANONICAL_AUTHORITY.json');master=(P/a['master']).read_text();norm=(P/D/'ARCHITECTURE_REV118.md').read_text();test('NORMATIVE_MASTER_INTEGRATION',norm in master and a['revision']=='1.18' and a['effective_test_registry']=='verification/EFFECTIVE_TEST_CONTRACTS_REV118.json')
 test('DISCOVERABLE_CONTEXT_EXTENSION',D+'FEATURE_CONTEXT_BINDINGS.json' in rd('design/ALL_SURFACE_CONTRACTS.json')['extension_registries'])
 for script,args in [('plan/compile_rev118.py',['--check']),('plan/render_plan.py',['--check'])]:
  r=subprocess.run([sys.executable,'-B',str(P/script),*args],capture_output=True,text=True);test(script,r.returncode==0,r.stdout+r.stderr)
 schema=d['schema'];Draft202012Validator.check_schema(schema)
 def valid(name,value):return Draft202012Validator({'$schema':schema['$schema'],'$defs':schema['$defs'],'$ref':'#/$defs/'+name},format_checker=FormatChecker()).is_valid(value)
 examples=rd(D+'EXAMPLES.json')['examples']
 for name,x in examples.items():test('POSITIVE_SCHEMA_'+name,valid(name,x))
 negative=[('Outcome','postcondition_receipt_refs',[]),('Command','proof_ref',None),('VoiceEvent','command_id','forbidden-partial-command')]
 for name,key,value in negative:
  x=copy.deepcopy(examples[name]);x[key]=value;test('REJECT_'+name+'_'+key,not valid(name,x))
 x=copy.deepcopy(examples['Outcome']);x.update(state='OUTCOME_UNKNOWN',error_code='OUTCOME_UNKNOWN',retry_policy='NONE');test('UNKNOWN_CANNOT_BLIND_RETRY',not valid('Outcome',x))
 x=copy.deepcopy(examples['CapabilityBinding']);x['qualification_state']='QUALIFIED';test('QUALIFIED_REQUIRES_RECEIPT',not valid('CapabilityBinding',x))
 x=copy.deepcopy(examples['VoiceEvent']);x.update(event_type='PLAYBACK_COMPLETE',spoken_completion=True,command_id='cmd',verified_outcome_ref=None);test('SPOKEN_COMPLETION_NEEDS_EVIDENCE',not valid('VoiceEvent',x))
 # Mutation checks exercise omissions that the previous inventory-only checks missed.
 m=copy.deepcopy(d);m['actions']['actions'].pop();test('REJECT_OMITTED_ACTION','ACTION_COVERAGE' in structural(m))
 m=copy.deepcopy(d);m['caps']['boundaries'].pop();test('REJECT_OMITTED_CAPABILITY','CAPABILITY_COVERAGE' in structural(m))
 m=copy.deepcopy(d);m['issues']['issues'].pop();test('REJECT_OMITTED_FINDING','ISSUE_COVERAGE' in structural(m))
 m=copy.deepcopy(d);t=next(x for x in m['effective']['tests'] if x['id']=='T-FEATURE-PRESENCE-03');t['additional_units']=[];test('REJECT_VOICE_OWNER_OMISSION','PRIMARY_OWNER:VNX-F-PRESENCE-03' in structural(m))
 m=copy.deepcopy(d);m['protocol']['command_transitions'].append({'from':'OUTCOME_UNKNOWN','to':'DISPATCHING','guard':'retry'});test('REJECT_UNKNOWN_REDISPATCH','UNKNOWN_REDISPATCH' in structural(m))
 m=copy.deepcopy(d);m['qual']['entries'][0]['runtime_state']='QUALIFIED';test('REJECT_FALSE_QUALIFICATION',any(x.startswith('FABRICATED_QUALIFICATION') for x in structural(m)))
 report={'scope':'REV118_DOCUMENT_CONTRACT_COMPILATION_SCHEMA_AND_MUTATION_CHECKS','passed':sum(x['passed'] for x in rows),'total':len(rows),'findings':errs,'application_tests_executed':0,'native_or_economic_qualification_issued':False,'cases':rows};print(json.dumps(report,indent=2));return 0 if all(x['passed'] for x in rows) else 1
if __name__=='__main__':raise SystemExit(main())
