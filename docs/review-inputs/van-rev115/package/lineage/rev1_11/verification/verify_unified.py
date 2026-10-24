#!/usr/bin/env python3
"""Deterministic specification validation; does not issue or accept runtime authority.

Negative tests mutate in-memory inputs, require an actual change and check a named
error code. Source locks are prepared, not owner-signed; coordinated edits to the
files and their lock still require independent signature verification at F15.
"""
from __future__ import annotations
import argparse,collections,copy,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PATHS={'authority':'CANONICAL_AUTHORITY.json','plan':'plan/DEVELOPMENT_PLAN.json','requirements':'traceability/REQUIREMENTS_AND_DU_MAPPING.json','services':'contracts/BACKEND_SERVICE_CATALOG.json','surfaces':'design/ALL_SURFACE_CONTRACTS.json','tests':'verification/TEST_CONTRACTS.json','actions':'traceability/LEGACY_349_ACTIONS.json','atoms':'traceability/REV2_171_ATOM_CROSSWALK.json','features':'traceability/REV2_93_FEATURE_CROSSWALK.json','truth':'traceability/PRODUCT_TRUTH.json','aliases':'traceability/FORECAST_PACKET_CROSSWALK.json','corrections':'contracts/CORRECTIVE_IMPLEMENTATION_CONTRACTS.json','gaps':'verification/GAP_CLOSURE_REGISTER.json','f15':'verification/F15_CERTIFICATE.json','bg':'verification/BACKEND_COMPLETE_CERTIFICATE.json'}
EXPECTED_COUNTS={'requirements':205,'nodes':121,'backend':74,'backend_verification':10,'surfaces':228,'actions':349,'atoms':171,'features':93,'truth':18,'forecast_aliases':48,'tests':1185}
def pairs(items):
 d={}
 for k,v in items:
  if k in d:raise ValueError(f'DUPLICATE_JSON_KEY:{k}')
  d[k]=v
 return d
def loads(s):return json.loads(s,object_pairs_hook=pairs)
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def load_bundle(root=ROOT):return {k:loads((root/p).read_text()) for k,p in PATHS.items()}
def records(b):return {'requirements':b['requirements']['requirements'],'nodes':b['plan']['units'],'services':b['services']['services'],'surfaces':b['surfaces']['surfaces'],'tests':b['tests']['tests'],'actions':b['actions']['actions'],'atoms':b['atoms']['requirements'],'features':b['features']['features'],'truth':b['truth']['truth_atoms'],'aliases':b['aliases']['mappings']}
def lock_snapshot(b):
 r=records(b)
 return {k:{str(x.get('id',x.get('source_id'))):digest(x) for x in v} for k,v in r.items()}
def validate(b,lock):
 out=[]
 def err(code,detail):out.append({'code':code,'detail':str(detail)})
 r=records(b);ids={}
 for kind,rs in r.items():
  names=[x.get('id',x.get('source_id')) for x in rs];dups=[k for k,n in collections.Counter(names).items() if n>1]
  if dups:err('DUPLICATE_ID',f'{kind}:{dups}')
  if any(x is None for x in names):err('MISSING_ID',kind)
  ids[kind]=set(names)
  expected=lock['records'].get(kind,{})
  if set(names)!=set(expected):err('SCOPE_SET_CHANGED',f'{kind}: missing={sorted(set(expected)-set(names))}; new={sorted(set(names)-set(expected))}')
  for x in rs:
   name=x.get('id',x.get('source_id'))
   if name in expected and digest(x)!=expected[name]:err('SCOPE_RECORD_CHANGED',f'{kind}:{name}')
 for k,v in EXPECTED_COUNTS.items():
  n=(len(r[k]) if k in r else len(r['aliases']) if k=='forecast_aliases' else sum(x['kind']=='BACKEND' for x in r['nodes']) if k=='backend' else sum(x['kind']=='BACKEND_VERIFICATION' for x in r['nodes']) if k=='backend_verification' else None)
  if n!=v:err('SCOPE_COUNT_CHANGED',f'{k}:{n}!={v}')
 a=b['authority'];p=b['plan'];u={x['id']:x for x in r['nodes']};rq={x['id']:x for x in r['requirements']};testids=ids['tests']
 if a.get('sole_f15')!='PRE-003' or a.get('sole_frontend_entry_gate')!='BG-001':err('DUPLICATE_GATE_AUTHORITY','One PRE-003 and one BG-001 only')
 if a.get('plan')!='plan/DEVELOPMENT_PLAN.json' or a.get('master')!='VAN_NEXT_UNIFIED_REBUILD_BLUEPRINT_REV1_11_20261017.md':err('OLD_PLAN_AUTHORITY','Canonical selector changed')
 if not a.get('no_frontend_before_backend') or not a.get('no_silent_feature_retirement'):err('OWNER_SCOPE_WEAKENED','Backend-first/no-loss required')
 if a.get('application_code_changed_by_this_pack') is not False or a.get('signed_authority') is not False:err('FALSE_AUTHORITY_CLAIM','Documentary pack cannot issue signed operational authority')
 kinds={'PREDEVELOPMENT','PREDEVELOPMENT_GATE','BACKEND','BACKEND_VERIFICATION','BACKEND_GATE','FRONTEND_DESIGN','FRONTEND','FINAL_QUALIFICATION','RELEASE','RETIREMENT'}
 for x in r['nodes']:
  if x.get('kind') not in kinds:err('INVALID_KIND',x['id'])
  if x.get('completion')!='FULL':err('THIN_UNIT',x['id'])
  if x.get('status')!='NOT_STARTED' or x.get('implementation_evidence'):err('FALSE_IMPLEMENTATION_STATE',x['id'])
  if not x.get('receipt_required'):err('RECEIPT_REMOVED',x['id'])
  if not x.get('exit_contract'):err('EXIT_CONTRACT_MISSING',x['id'])
  ds=x.get('dependencies',[])
  if len(ds)!=len(set(ds)):err('DUPLICATE_DEPENDENCY',x['id'])
  for d in ds:
   if d not in u:err('UNKNOWN_DEPENDENCY',f'{x["id"]}<-{d}')
   elif u[d]['stage']>x['stage']:err('PHASE_INVERSION',f'{x["id"]}<-{d}')
  if x['id'] in ds:err('CYCLE',x['id'])
 remaining=set(u);done=[]
 while remaining:
  ready=[u[i] for i in remaining if set(u[i]['dependencies'])<=set(done)]
  if not ready:err('CYCLE_OR_MISSING_DEPENDENCY',sorted(remaining));break
  z=min(ready,key=lambda x:(x['stage'],x.get('lane_order',0),x['id']));done.append(z['id']);remaining.remove(z['id'])
 if not remaining and done!=[x['id'] for x in r['nodes']]:err('NONDETERMINISTIC_ORDER','Stored order differs from deterministic topological order')
 if [x.get('packet_id') for x in r['nodes']]!=[f'VAN-PKT-{i:03}' for i in range(1,len(r['nodes'])+1)]:err('PACKET_SEQUENCE_CHANGED','Packet IDs must derive from graph')
 def ancestors(i):
  seen=set();stack=list(u.get(i,{}).get('dependencies',[]))
  while stack:
   z=stack.pop()
   if z not in seen:seen.add(z);stack.extend(u.get(z,{}).get('dependencies',[]))
  return seen
 anc={i:ancestors(i) for i in u}
 backend={x['id'] for x in r['nodes'] if x['kind']=='BACKEND'};bv={x['id'] for x in r['nodes'] if x['kind']=='BACKEND_VERIFICATION'};ui={x['id'] for x in r['nodes'] if x['kind'] in ('FRONTEND','FRONTEND_DESIGN')}
 if set(p.get('required_backend_ids',[]))!=backend or set(p.get('required_backend_verification_ids',[]))!=bv:err('BACKEND_SCOPE_MISMATCH','Required ID sets differ from node roles')
 if set(u.get('BG-001',{}).get('dependencies',[]))!=backend|bv:err('BG_INCOMPLETE_SCOPE','Global gate must explicitly account for every backend and verifier')
 if ids['services']!=backend:err('SERVICE_SCOPE_MISMATCH','Every backend unit requires a full service contract')
 for i,x in u.items():
  if x['kind'] not in ('PREDEVELOPMENT','PREDEVELOPMENT_GATE') and 'PRE-003' not in anc[i]:err('CODE_BEFORE_F15',i)
  if i in ui and 'BG-001' not in anc[i]:err('UI_BEFORE_BACKEND',i)
  if i in backend|bv and anc[i]&ui:err('BACKEND_DEPENDS_ON_FRONTEND',i)
  if i in backend|bv and i not in anc.get('BG-001',set()):err('BACKEND_NOT_IN_GATE',i)
  if x['kind'] in ('FRONTEND','FRONTEND_DESIGN') and i not in anc.get('QA-005',set()):err('UI_NOT_IN_FINAL_ACCEPTANCE',i)
  if x['kind']=='BACKEND' and i!='BE-001' and 'BE-001' not in anc[i]:err('PARITY_BEFORE_CHECKER',i)
 for consumer,producers in {'BE-013':['BE-035'],'BE-036':['BE-035','BE-013','BE-028','VAN-ML-PKT-023','VAN-ML-PKT-027'],'BE-032':['BE-036','VAN-ML-PKT-028','VAN-ML-PKT-048'],'VAN-ML-PKT-008':['BE-035'],'VAN-ML-PKT-009':['BE-035'],'FE-023':['BG-001','UX-003'],'BG-001':['BQ-007','VAN-ML-PKT-032']}.items():
  for pr in producers:
   if pr not in anc.get(consumer,set()):err('PRODUCER_NOT_UPSTREAM',f'{consumer} requires {pr}')
 for s in r['services']:
  if not s.get('operations') or not s.get('models') or not s.get('authority') or not s.get('adversarial_acceptance'):err('INCOMPLETE_SERVICE_CONTRACT',s['id'])
  if s.get('completion')!='FULL_REQUIRED_BEFORE_BG001':err('PARTIAL_BACKEND',s['id'])
 for row in r['requirements']:
  owners=row.get('backend_units',[])+row.get('frontend_units',[])+row.get('other_units',[])
  if not owners or not row.get('text') or not row.get('acceptance'):err('INCOMPLETE_REQUIREMENT',row['id'])
  for i in owners:
   if i not in u:err('UNMAPPED_REQUIREMENT',f'{row["id"]}:{i}')
  for i in row.get('backend_units',[]):
   if i in u and u[i]['kind']!='BACKEND':err('REQUIREMENT_ROLE_MISMATCH',f'{row["id"]}:{i}')
  for i in row.get('frontend_units',[]):
   if i in u and u[i]['kind']!='FRONTEND':err('REQUIREMENT_ROLE_MISMATCH',f'{row["id"]}:{i}')
  if row.get('test_id') not in testids:err('MISSING_REQUIREMENT_TEST',row['id'])
 for s in r['surfaces']:
  if not s.get('backend_units') or not s.get('frontend_units') or not s.get('first_fold') or not s.get('dark_light'):err('INCOMPLETE_SURFACE',s['id'])
  for i in s.get('backend_units',[])+s.get('frontend_units',[]):
   if i not in u:err('SURFACE_OWNER_MISSING',f'{s["id"]}:{i}')
  for i in s.get('van_requirements',[]):
   if i not in rq:err('SURFACE_REQUIREMENT_MISSING',s['id'])
  if s.get('test_id') not in testids:err('SURFACE_TEST_MISSING',s['id'])
 for ac in r['actions']:
  if ac.get('surface_id') not in ids['surfaces']:err('ACTION_SURFACE_MISSING',ac['id'])
  if not ac.get('text') or not ac.get('backend_units') or not ac.get('frontend_units'):err('ACTION_CONTRACT_MISSING',ac['id'])
  if ac.get('test_id') not in testids:err('ACTION_TEST_MISSING',ac['id'])
 for row in r['atoms']:
  if not row.get('product_truth_ids') or not row.get('van_requirements'):err('ATOM_BINDING_MISSING',row['id'])
  if any(x not in ids['truth'] for x in row.get('product_truth_ids',[])):err('UNKNOWN_PRODUCT_TRUTH',row['id'])
  if any(x not in rq for x in row.get('van_requirements',[])):err('ATOM_REQUIREMENT_MISSING',row['id'])
 for row in r['features']:
  if not row.get('backend_units') or not row.get('frontend_units') or not row.get('van_requirements'):err('FEATURE_MAPPING_MISSING',row['id'])
  if any(x not in ids['surfaces'] for x in row.get('context_ids',[])):err('FEATURE_CONTEXT_MISSING',row['id'])
 for t in r['tests']:
  if t.get('unit') not in u or any(i not in u for i in t.get('additional_units',[])):err('TEST_OWNER_MISSING',t['id'])
  if t.get('execution_state')!='NOT_RUN' or not t.get('receipt_required'):err('FALSE_TEST_CLAIM',t['id'])
 for x in r['aliases']:
  if x['canonical_unit'] not in u or not x.get('all_deliverables_retained') or not x.get('all_exit_evidence_retained'):err('FORECAST_OBLIGATION_LOSS',x['source_id'])
 for source,dest in {'VAN-ML-PKT-001':'PRE-001','VAN-ML-PKT-002':'PRE-002','VAN-ML-PKT-003':'PRE-003','VAN-ML-PKT-033':'BG-001','VAN-ML-PKT-034':'FE-023','VAN-ML-PKT-035':'QA-005','VAN-ML-PKT-036':'REL-001'}.items():
  rows=[x for x in r['aliases'] if x['source_id']==source]
  if len(rows)!=1 or rows[0]['canonical_unit']!=dest:err('FORECAST_DUPLICATE_GATE',source)
 for g in b['gaps']['items']:
  if g.get('waiver_allowed') is not False:err('B4_WAIVER',g['id'])
  if g.get('first_gate') not in u:err('GAP_GATE_MISSING',g['id'])
 for name in ('f15','bg'):
  cert=b[name]
  if cert.get('status')!='NOT_ISSUED' or cert.get('signature') is not None or cert.get('issuer') is not None:err('SELF_ISSUED_CERTIFICATE',name)
 oq=p.get('owner_questions',[])
 if len({x['id'] for x in oq})!=len(oq):err('DUPLICATE_QUESTION','owner question IDs')
 decided=[x for x in oq if x['id']=='OQ-21']
 if len(decided)!=1 or decided[0].get('status')!='VALUES_ACCEPTED_OD39_NOT_RUNTIME_ACTIVATION':err('OQ21_REOPENED_OR_ACTIVATED','Do not confuse accepted values with signed runtime policy')
 return out

def selftest(b,lock):
 cases=[]
 def add(name,code,fn):cases.append((name,code,fn))
 def node(z,i):return next(x for x in z['plan']['units'] if x['id']==i)
 def req(z,i):return next(x for x in z['requirements']['requirements'] if x['id']==i)
 add('drop funds requirement','SCOPE_SET_CHANGED',lambda z:z['requirements']['requirements'].__setitem__(slice(None),[x for x in z['requirements']['requirements'] if x['id']!='VAN-NX-055']))
 add('drop orb requirement','SCOPE_SET_CHANGED',lambda z:z['requirements']['requirements'].__setitem__(slice(None),[x for x in z['requirements']['requirements'] if x['id']!='VAN-NX-004']))
 add('drop weekly research requirement','SCOPE_SET_CHANGED',lambda z:z['requirements']['requirements'].__setitem__(slice(None),[x for x in z['requirements']['requirements'] if x['id']!='VAN-NX-072']))
 add('duplicate requirement','DUPLICATE_ID',lambda z:z['requirements']['requirements'].append(copy.deepcopy(z['requirements']['requirements'][0])))
 add('edit source requirement','SCOPE_RECORD_CHANGED',lambda z:req(z,'VAN-NX-076').update(text='Silently replace stop order with market order'))
 add('orphan requirement','UNMAPPED_REQUIREMENT',lambda z:req(z,'VAN-NX-055').update(backend_units=['BE-NOTREAL']))
 add('remove requirement test','MISSING_REQUIREMENT_TEST',lambda z:req(z,'VAN-NX-055').update(test_id='T-MISSING'))
 add('drop legacy action','SCOPE_SET_CHANGED',lambda z:z['actions']['actions'].pop())
 add('edit legacy action','SCOPE_RECORD_CHANGED',lambda z:z['actions']['actions'][0].update(text='Read only instead of inherited owner effect'))
 add('duplicate legacy action','DUPLICATE_ID',lambda z:z['actions']['actions'].append(copy.deepcopy(z['actions']['actions'][0])))
 add('orphan action surface','ACTION_SURFACE_MISSING',lambda z:z['actions']['actions'][0].update(surface_id='missing'))
 add('drop surface','SCOPE_SET_CHANGED',lambda z:z['surfaces']['surfaces'].pop())
 add('empty screen backend','INCOMPLETE_SURFACE',lambda z:z['surfaces']['surfaces'][0].update(backend_units=[]))
 add('remove dark-light contract','INCOMPLETE_SURFACE',lambda z:z['surfaces']['surfaces'][0].update(dark_light=''))
 add('drop truth mapping','ATOM_BINDING_MISSING',lambda z:z['atoms']['requirements'][0].update(product_truth_ids=[]))
 add('unknown truth mapping','UNKNOWN_PRODUCT_TRUTH',lambda z:z['atoms']['requirements'][0].update(product_truth_ids=['PT-MISSING']))
 add('unmapped feature','FEATURE_MAPPING_MISSING',lambda z:z['features']['features'][0].update(frontend_units=[]))
 add('cycle','CYCLE_OR_MISSING_DEPENDENCY',lambda z:node(z,'PRE-001')['dependencies'].append('BE-001'))
 add('unknown prerequisite','UNKNOWN_DEPENDENCY',lambda z:node(z,'BE-035')['dependencies'].append('BE-NOTREAL'))
 add('duplicate unit','DUPLICATE_ID',lambda z:z['plan']['units'].append(copy.deepcopy(z['plan']['units'][0])))
 add('duplicate prerequisite','DUPLICATE_DEPENDENCY',lambda z:node(z,'BE-035')['dependencies'].append(node(z,'BE-035')['dependencies'][0]))
 add('backend starts before F15','CODE_BEFORE_F15',lambda z:node(z,'BE-001').update(dependencies=['PRE-001']))
 add('UX before whole backend','UI_BEFORE_BACKEND',lambda z:node(z,'UX-001').update(dependencies=['PRE-003']))
 add('frontend before backend','UI_BEFORE_BACKEND',lambda z:node(z,'FE-004').update(dependencies=['PRE-003']))
 add('backend waits on new UI','BACKEND_DEPENDS_ON_FRONTEND',lambda z:node(z,'BE-004')['dependencies'].append('FE-004'))
 add('missing explicit backend gate member','BG_INCOMPLETE_SCOPE',lambda z:node(z,'BG-001')['dependencies'].remove('BE-035'))
 add('wrong backend set','BACKEND_SCOPE_MISMATCH',lambda z:z['plan']['required_backend_ids'].pop())
 add('rename backend into feature','SCOPE_RECORD_CHANGED',lambda z:node(z,'BE-035').update(kind='FRONTEND'))
 add('partial unit masquerades as full','THIN_UNIT',lambda z:node(z,'BE-035').update(completion='M1'))
 add('marked implemented without receipt','FALSE_IMPLEMENTATION_STATE',lambda z:node(z,'BE-035').update(status='DONE'))
 add('remove evidence requirement','RECEIPT_REMOVED',lambda z:node(z,'BE-035').update(receipt_required=False))
 add('empty backend operations','INCOMPLETE_SERVICE_CONTRACT',lambda z:next(s for s in z['services']['services'] if s['id']=='BE-035').update(operations=[]))
 add('omitted service','SERVICE_SCOPE_MISMATCH',lambda z:z['services']['services'].pop())
 add('candidate generator skips evaluator','PRODUCER_NOT_UPSTREAM',lambda z:node(z,'BE-036').update(dependencies=['PRE-003','BE-001']))
 add('training skips qualified evaluator','PRODUCER_NOT_UPSTREAM',lambda z:node(z,'VAN-ML-PKT-008').update(dependencies=['PRE-003','BE-001']))
 add('catalogue omits strategy research','PRODUCER_NOT_UPSTREAM',lambda z:node(z,'BE-032').update(dependencies=['PRE-003','BE-001']))
 add('invent child frontend entry gate','FORECAST_DUPLICATE_GATE',lambda z:next(x for x in z['aliases']['mappings'] if x['source_id']=='VAN-ML-PKT-033').update(canonical_unit='FE-023'))
 add('drop forecast obligation','FORECAST_OBLIGATION_LOSS',lambda z:z['aliases']['mappings'][0].update(all_exit_evidence_retained=[]))
 add('drop forecast requirement','SCOPE_SET_CHANGED',lambda z:z['requirements']['requirements'].__setitem__(slice(None),[x for x in z['requirements']['requirements'] if x['id']!='VAN-ML-REQ-090']))
 add('test fabricated passed','FALSE_TEST_CLAIM',lambda z:z['tests']['tests'][0].update(execution_state='PASSED'))
 add('test orphan unit','TEST_OWNER_MISSING',lambda z:z['tests']['tests'][0].update(unit='NO-UNIT'))
 add('duplicate test','DUPLICATE_ID',lambda z:z['tests']['tests'].append(copy.deepcopy(z['tests']['tests'][0])))
 add('old schedule active','OLD_PLAN_AUTHORITY',lambda z:z['authority'].update(plan='lineage/rev1_10/plan/DEVELOPMENT_PLAN.json'))
 add('second F15 authority','DUPLICATE_GATE_AUTHORITY',lambda z:z['authority'].update(sole_f15='VAN-ML-PKT-003'))
 add('waive whole backend','OWNER_SCOPE_WEAKENED',lambda z:z['authority'].update(no_frontend_before_backend=False))
 add('claim owner signed','FALSE_AUTHORITY_CLAIM',lambda z:z['authority'].update(signed_authority=True))
 add('blanket B4 waiver','B4_WAIVER',lambda z:z['gaps']['items'][0].update(waiver_allowed=True))
 add('self issue F15','SELF_ISSUED_CERTIFICATE',lambda z:z['f15'].update(status='FORENSIC_BUILD_READY',issuer='AUTHOR',signature='fake'))
 add('self issue backend complete','SELF_ISSUED_CERTIFICATE',lambda z:z['bg'].update(status='PASSED',issuer='AUTHOR',signature='fake'))
 add('reopen accepted OQ21','OQ21_REOPENED_OR_ACTIVATED',lambda z:next(q for q in z['plan']['owner_questions'] if q['id']=='OQ-21').update(status='UNRESOLVED'))
 add('duplicate owner question','DUPLICATE_QUESTION',lambda z:z['plan']['owner_questions'].append(copy.deepcopy(z['plan']['owner_questions'][0])))
 result=[]
 for name,code,fn in cases:
  z=copy.deepcopy(b);before=digest(z);fn(z)
  if digest(z)==before:raise ValueError('NOOP_MUTATION:'+name)
  errors=validate(z,lock);caught=code in {x['code'] for x in errors};result.append({'case':name,'expected_code':code,'caught':caught,'finding_count':len(errors)})
  print(('caught: ' if caught else 'MISSED: ')+name+' -> '+code)
 try:loads('{"id":1,"id":2}');caught=False
 except ValueError:caught=True
 result.append({'case':'duplicate JSON key','expected_code':'DUPLICATE_JSON_KEY','caught':caught})
 return result

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--selftest',action='store_true');ap.add_argument('--json-output',type=Path);args=ap.parse_args();b=load_bundle();lock=loads((ROOT/'plan/PROPOSED_SCOPE_LOCK.json').read_text());errors=validate(b,lock)
 if errors:
  print(json.dumps({'status':'FAIL','findings':errors},indent=2));return 1
 result={'schema':'van.document.check/1.0','status':'SPECIFICATION_STRUCTURAL_PASS_NOT_F15','source_head':b['authority']['source_head'],'counts':EXPECTED_COUNTS,'findings':[],'scope_lock_sha256':hashlib.sha256((ROOT/'plan/PROPOSED_SCOPE_LOCK.json').read_bytes()).hexdigest(),'scope_signature_status':'PREPARED_NOT_OWNER_SIGNED'}
 if args.selftest:
  tests=selftest(b,lock);result['negative_cases']=tests;result['caught']=sum(x['caught'] for x in tests);result['total']=len(tests)
  print(f"{result['caught']}/{len(tests)} deliberately broken inputs caught")
  if result['caught']!=len(tests):result['status']='FAIL'
 else:print(f"0 findings: {len(b['plan']['units'])} units, {len(b['requirements']['requirements'])} requirements, one global backend gate")
 if args.json_output:args.json_output.parent.mkdir(parents=True,exist_ok=True);args.json_output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
 return 0 if result['status']!='FAIL' else 1
if __name__=='__main__':
 try:raise SystemExit(main())
 except (ValueError,KeyError,TypeError,OSError) as e:print('INVALID_INPUT: '+str(e),file=sys.stderr);raise SystemExit(2)
