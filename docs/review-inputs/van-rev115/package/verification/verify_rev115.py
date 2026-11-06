#!/usr/bin/env python3
"""Rev1.15 *document* conformance checks. No VAN code, backtest or venue execution.

Checks shape, links, deterministic graph/order, preservation, prepared-lock identity
and selected adversarial counterexamples. It does NOT verify that proof predicates
are true, signatures are authentic, the application implements them, or a policy
is profitable. All application tests and F15/BG remain NOT_RUN/NOT_ISSUED.
"""
from __future__ import annotations
import argparse, copy, hashlib, importlib.util, json, subprocess, sys
from collections import Counter
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FILES={
 'authority':'CANONICAL_AUTHORITY.json', 'plan':'plan/DEVELOPMENT_PLAN.json',
 'requirements':'traceability/REQUIREMENTS_AND_DU_MAPPING.json',
 'new_requirements':'traceability/REV114_REQUIREMENTS.json',
 'tests':'verification/TEST_CONTRACTS.json',
 'new_tests':'verification/SELF_OPTIMIZATION_ACCEPTANCE_CONTRACTS.json',
 'actions':'traceability/LEGACY_349_ACTIONS.json','truth':'traceability/PRODUCT_TRUTH.json',
 'surfaces':'design/ALL_SURFACE_CONTRACTS.json',
 'machines':'contracts/self_optimization/STATE_MACHINES.json',
 'proofs':'contracts/self_optimization/PROOF_PREDICATES.json',
 'invariants':'contracts/self_optimization/SEMANTIC_INVARIANTS.json',
 'authmap':'contracts/self_optimization/AUTHORITY_MATRIX.json',
 'schemas':'contracts/self_optimization/SELF_OPTIMIZATION_RECORDS.schema.json',
 'example_index':'contracts/self_optimization/EXAMPLE_INDEX.json',
 'fixture':'contracts/self_optimization/POSITIVE_LOOP_REPLAY_FIXTURE.json',
 'crosswalk':'traceability/SELF_OPTIMIZATION_SOURCE_CROSSWALK.json',
 'extensions':'contracts/self_optimization/UNIT_EXTENSIONS.json',
 'f15':'verification/F15_CERTIFICATE.json','bg':'verification/BACKEND_COMPLETE_CERTIFICATE.json',
 'lock':'plan/PROPOSED_SCOPE_LOCK.json'}
PARENTS={'requirements':('traceability/REQUIREMENTS_AND_DU_MAPPING.json','requirements'),
 'tests':('verification/TEST_CONTRACTS.json','tests'), 'actions':('traceability/LEGACY_349_ACTIONS.json','actions'),
 'truth':('traceability/PRODUCT_TRUTH.json','truth_atoms'), 'surfaces':('design/ALL_SURFACE_CONTRACTS.json','surfaces'),
 'plan':('plan/DEVELOPMENT_PLAN.json','units')}
def pairs(items):
 d={}
 for k,v in items:
  if k in d:raise ValueError('DUPLICATE_JSON_KEY:'+k)
  d[k]=v
 return d
def parse(s):return json.loads(s,object_pairs_hook=pairs)
def read(p):return parse((ROOT/p).read_text(encoding='utf-8'))
def canonical(o):return json.dumps(o,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def digest(o):return hashlib.sha256(canonical(o)).hexdigest()
def unique(seq,key,code,errors):
 out={}
 for o in seq:
  i=o.get(key)
  if not isinstance(i,str) or not i:errors.append(code+':MISSING');continue
  if i in out:errors.append(code+':'+i)
  out[i]=o
 return out

def state_checks(d):
 e=[]; ms=unique(d['machines']['machines'],'id','DUPLICATE_MACHINE',e)
 ps=unique(d['proofs']['proofs'],'id','DUPLICATE_PROOF',e)
 if not d['machines'].get('external_fact_rule'):e.append('MISSING_REAL_FILL_FACT_RULE')
 for mid,m in ms.items():
  states=m.get('states',[])
  if len(states)!=len(set(states)):e.append('DUPLICATE_STATE:'+mid)
  if m.get('initial') not in states:e.append('UNKNOWN_INITIAL:'+mid)
  if not set(m.get('terminal_states',[])).issubset(states):e.append('UNKNOWN_TERMINAL:'+mid)
  ts=unique(m.get('transitions',[]),'id','DUPLICATE_TRANSITION',e);edges=set()
  for t in ts.values():
   edge=(t.get('from'),t.get('to'))
   if edge in edges:e.append('DUPLICATE_EDGE:'+mid)
   edges.add(edge)
   if not set(edge).issubset(states):e.append('UNKNOWN_TRANSITION_STATE:'+mid)
   proof=t.get('proof_predicates',[])
   if len(proof)!=len(set(proof)) or not proof or any(x not in ps for x in proof):e.append('INVALID_PROOF_SET:'+t['id'])
   req=set()
   if mid=='SO-CHILD' and t['to']=='SUBMITTING':req={'COMMAND_DURABLE','GRANT_CURRENT','FENCE_CURRENT','RESERVATION_CURRENT','FEASIBLE_ACTION','POLICY_QUALIFIED'}
   if mid=='SO-CHILD' and t['to'] in ('FILLED','PARTIALLY_FILLED'):req={'VENUE_FILL'}
   if mid=='SO-CHILD' and t['to']=='CANCELLED':req={'CANCEL_FINAL'}
   if mid=='SO-PARENT' and t['to']=='ECONOMICALLY_RECONCILED':req={'EXPOSURE_RECONCILED','CASH_RECONCILED','PROTECTION_RESOLVED'}
   if mid=='SO-EVIDENCE' and t['to']=='APPLIED':req={'MATURE_OBSERVATION','NOT_APPLIED','COHORT_COMPATIBLE','UPDATE_RULE_QUALIFIED'}
   if mid=='SO-CANDIDATE' and t['to']=='AUTHORIZED':req={'INDEPENDENT_QUALIFICATION','PROMOTION_AUTHORIZED'}
   if mid=='SO-BINDING' and t['to']=='ACTIVE':req={'PROMOTION_AUTHORIZED','ACTIVATION_READBACK','POLICY_QUALIFIED'}
   if mid in ('SO-CHILD','SO-PARENT') and t['to']=='CANCEL_REQUESTED':req={'COMMAND_DURABLE','FENCE_CURRENT','CANCEL_SCOPE_AUTHORIZED'}
   if mid=='SO-BINDING' and t['to']=='EXPIRED':req={'BINDING_EXPIRED'}
   if mid=='SO-CANDIDATE' and t['to']=='CANCELLED':req={'RESEARCH_STOP_AUTHORIZED'}
   if not req.issubset(proof):e.append('CRITICAL_EDGE_PROOF_MISSING:'+t['id']+':'+','.join(sorted(req-set(proof))))
  # Only inspect explicit reachability; this is not full temporal runtime model checking.
  reachable={m['initial']}
  while True:
   nxt=reachable|{b for a,b in edges if a in reachable}
   if nxt==reachable:break
   reachable=nxt
  if set(states)-reachable:e.append('UNREACHABLE_STATE:'+mid+':'+','.join(sorted(set(states)-reachable)))
 # Corrections must reopen terminal revisions; observation never reauthorizes entry.
 cm=ms.get('SO-CHILD',{});ce={(t.get('from'),t.get('to')) for t in cm.get('transitions',[])}
 for state in ('CANCELLED','EXPIRED','REJECTED','RECONCILED'):
  if (state,'OUTCOME_UNKNOWN') not in ce:e.append('MISSING_LATE_FACT_RECONCILIATION:'+state)
 pm=ms.get('SO-PARENT',{});pe={(t.get('from'),t.get('to')) for t in pm.get('transitions',[])}
 for edge in [('OUTCOME_UNKNOWN','CANCELLED'),('OUTCOME_UNKNOWN','EXPIRED'),('CANCEL_REQUESTED','OUTCOME_UNKNOWN'),('FILLED','OUTCOME_UNKNOWN')]:
  if edge not in ce:e.append('MISSING_UNKNOWN_RECOVERY:'+':'.join(edge))
 if ('EVALUATED','RECONCILING') not in pe or ('ABORTED','UNRESOLVED') not in pe:e.append('MISSING_PARENT_CORRECTION_PATH')
 bm=ms.get('SO-BINDING',{});be={(t.get('from'),t.get('to')) for t in bm.get('transitions',[])}
 for state in ('AUTHORIZED','ACTIVE','SUSPENDED','DRAINING'):
  if (state,'EXPIRED') not in be:e.append('MISSING_BINDING_EXPIRY:'+state)
 for state in ('PROPOSED','AUTHORIZED','ACTIVE','SUSPENDED','DRAINING'):
  if (state,'REVOKED') not in be:e.append('MISSING_BINDING_REVOCATION:'+state)
 inv=unique(d['invariants']['invariants'],'id','DUPLICATE_INVARIANT',e)
 required={'INV-AUTH','INV-FACT','INV-EXPOSURE','INV-LIMIT','INV-DEADLINE','INV-PROTECT','INV-REPLAY','INV-PROMOTE','INV-LEARN','INV-URGENCY','INV-SPOT','INV-PROVIDER','INV-SCOPE','INV-FRONTEND','INV-COMPLEXITY','INV-ECONOMICS'}
 if required-set(inv):e.append('MISSING_INDEPENDENT_INVARIANT')
 if not d['invariants'].get('guard_list_is_not_sufficient'):e.append('GUARD_LABELS_NOT_RUNTIME_PROOF')
 return e

def check(d,parents,files_check=True):
 e=[];p=d['plan'];rs=d['requirements']['requirements'];tests=d['tests']['tests']
 rr=unique(rs,'id','DUPLICATE_REQUIREMENT',e);tt=unique(tests,'id','DUPLICATE_TEST',e);uu=unique(p['units'],'id','DUPLICATE_UNIT',e)
 aa=unique(d['actions']['actions'],'id','DUPLICATE_ACTION',e);ss=unique(d['surfaces']['surfaces'],'id','DUPLICATE_SURFACE',e)
 pts=unique(d['truth']['truth_atoms'],'id','DUPLICATE_PRODUCT_TRUTH',e)
 maps=unique(d['truth']['mappings'],'id','DUPLICATE_TRUTH_MAPPING',e)
 for t in pts:
  if t not in maps:e.append('UNMAPPED_PRODUCT_TRUTH:'+t)
 for m in maps.values():
  if not m.get('van_requirements') or set(m['van_requirements'])-set(rr):e.append('INVALID_TRUTH_REQUIREMENTS:'+m['id'])
 for name,current,key in [('requirements',rr,'requirements'),('tests',tt,'tests'),('actions',aa,'actions'),('truth',pts,'truth_atoms')]:
  for old in parents[name]:
   i=old['id']
   if i not in current:e.append('PARENT_'+name.upper()+'_REMOVED:'+i)
   elif canonical(current[i])!=canonical(old):e.append('PARENT_'+name.upper()+'_CHANGED:'+i)
 if set(uu)!={x['id'] for x in parents['plan']}:e.append('PARENT_UNIT_IDS_CHANGED')
 if set(ss)!={x['id'] for x in parents['surfaces']}:e.append('PARENT_CONTEXT_IDS_CHANGED')
 for row in d['new_requirements']['requirements']:
  if row['id'] not in rr or canonical(rr[row['id']])!=canonical(row):e.append('NEW_REQUIREMENT_MISSING_OR_CHANGED:'+row['id'])
 # Literal product intentions are separate from catalog length.
 for prefix,count in [('VAN-SO-',44),('VAN-CRYPTO-',14),('VAN-LEAN-',6)]:
  expected={f'{prefix}{i:03d}' for i in range(1,count+1)}
  if not expected.issubset(rr):e.append('MANDATORY_SCOPE_LOSS:'+prefix)
 for row in d['new_tests']['tests']:
  if row['id'] not in tt or canonical(tt[row['id']])!=canonical(row):e.append('NEW_ACCEPTANCE_CONTRACT_MISSING:'+row['id'])
 for row in rs:
  owners=sum([row.get(k,[]) for k in ['backend_units','frontend_units','other_units']],[])
  if not owners or set(owners)-set(uu):e.append('INVALID_REQUIREMENT_OWNER:'+row['id'])
  ids=row.get('test_ids',[]) or ([row['test_id']] if row.get('test_id') else [])
  if not ids or set(ids)-set(tt):e.append('REQUIREMENT_WITHOUT_TEST:'+row['id'])
  for owner in owners:
   if row['id'] not in p['requirement_ownership'].get(owner,[]):e.append('PLAN_OWNERSHIP_MISSING:'+row['id']+':'+owner)
 for t in tests:
  if t.get('execution_state')!='NOT_RUN':e.append('FABRICATED_APPLICATION_RESULT:'+t['id'])
  if t['unit'] not in uu or set(t.get('additional_units',[]))-set(uu):e.append('TEST_OWNER_UNKNOWN:'+t['id'])
 for x in p['units']:
  if x.get('completion')!='FULL' or x.get('status')!='NOT_STARTED' or x.get('implementation_evidence'):e.append('FALSE_UNIT_COMPLETION:'+x['id'])
  if len(x['dependencies'])!=len(set(x['dependencies'])):e.append('DUPLICATE_DEPENDENCY:'+x['id'])
  for dep in x['dependencies']:
   if dep not in uu:e.append('UNKNOWN_DEPENDENCY:'+x['id']+':'+dep)
   elif uu[dep]['sequence']>=x['sequence']:e.append('DEPENDENCY_ORDER_OR_CYCLE:'+x['id'])
 ids=set(uu);anc={}
 def ancestors(i,seen=None):
  if i in anc:return anc[i]
  seen=set() if seen is None else set(seen)
  if i in seen:raise ValueError('CYCLE:'+i)
  seen.add(i);a=set()
  for q in uu[i]['dependencies']:
   if q in ids:a.add(q);a|=ancestors(q,seen)
  anc[i]=a;return a
 try:
  for i in uu:ancestors(i)
  back={i for i,u in uu.items() if u['kind']=='BACKEND'};bq={i for i,u in uu.items() if u['kind']=='BACKEND_VERIFICATION'}
  if back!=set(p['required_backend_ids']) or bq!=set(p['required_backend_verification_ids']):e.append('BACKEND_DENOMINATOR_MISMATCH')
  if (back|bq)-anc.get('BG-001',set()):e.append('BACKEND_OMISSION_BEFORE_BG')
  for i,u in uu.items():
   if u['kind'] in ('FRONTEND','FRONTEND_DESIGN') and 'BG-001' not in anc[i]:e.append('FRONTEND_BEFORE_BG:'+i)
   if u['kind'] in ('BACKEND','BACKEND_VERIFICATION','FRONTEND','FRONTEND_DESIGN') and 'PRE-003' not in anc[i]:e.append('CODE_BEFORE_F15:'+i)
  if not {'BE-010','BE-012','BE-035'}.issubset(anc.get('BE-036',set())):e.append('LEARNING_BEFORE_EXECUTION_OR_EVALUATOR')
 except ValueError as ex:e.append(str(ex))
 if p.get('new_deployable_services_required')!=0:e.append('UNJUSTIFIED_NEW_DAEMON_REQUIREMENT')
 am=unique(d['authmap']['actions'],'action','DUPLICATE_AUTHORITY_ACTION',e)
 if d['authmap'].get('live_exploration_enabled_by_default') is not False:e.append('UNAUTHORIZED_LIVE_EXPLORATION')
 for action in ('CHANGE_RISK_CEILING','WITHDRAW_FUNDS'):
  if am.get(action,{}).get('level')!='NOT_OPTIMIZER_AUTHORITY':e.append('OPTIMIZER_FINANCIAL_AUTHORITY_LEAK:'+action)
 if am.get('ACTIVATE_NEW_POLICY',{}).get('required_authority')!='INDEPENDENT_QUALIFICATION_AND_AUTHORIZED_PROMOTION':e.append('UNAUTHORIZED_PROMOTION')
 if set(d['authmap'].get('autonomy_levels',[]))!={'AUTOMATIC_OPERATIONAL_OPTIMIZATION','GOVERNED_POLICY_EVOLUTION'}:e.append('TWO_AUTONOMY_LEVELS_MISSING')
 for cert in ('f15','bg'):
  c=d[cert]
  if c.get('status')!='NOT_ISSUED' or c.get('signature') or c.get('issuer') or c.get('evidence_refs'):e.append('FABRICATED_CERTIFICATE:'+cert)
 e+=state_checks(d)
 if len(d['crosswalk']['sections'])!=24 or len(d['crosswalk']['gaps'])!=30:e.append('SOURCE_COVERAGE_INCOMPLETE')
 # Prepared object fingerprints: a simultaneous edit of object + lock is not prevented
 # without external signature. Both remain pending; this verifier never claims otherwise.
 lock=d['lock']
 if lock.get('status')!='PREPARED_PENDING_OWNER_SIGNATURE':e.append('FALSE_LOCK_AUTHORITY')
 for name,current in [('requirements',rr),('tests',tt),('actions',aa),('truth',pts),('units',uu),('surfaces',ss)]:
  if {k:digest(v) for k,v in current.items()}!=lock.get('objects',{}).get(name):e.append('PREPARED_OBJECT_LOCK_MISMATCH:'+name)
 if files_check:
  for path,sha in lock.get('file_hashes',{}).items():
   q=ROOT/path
   if not q.is_file() or hashlib.sha256(q.read_bytes()).hexdigest()!=sha:e.append('PREPARED_FILE_LOCK_MISMATCH:'+path)
  for k in ('master','plan','rendered_plan','focused_blueprint','review_prompt','scope_lock'):
   if not (ROOT/d['authority'][k]).is_file():e.append('MISSING_CANONICAL_ARTIFACT:'+k)
 return sorted(set(e))

def fixture_model(f):
 """Independent tiny documentary arithmetic example; never real VATI evidence."""
 if f.get('evidence_grade')!='SYNTHETIC_SPECIFICATION_MODEL_ONLY' or not f.get('not_real_market_or_learning_result'):raise ValueError('FIXTURE_RELABELLED')
 Q=Decimal(f['subject']['quantity_base']);p0=Decimal(f['subject']['decision_reference']);latest={};seen={};chosen={};alg=f['qualified_algorithms'];minimum=f['policy']['minimum_mature_distinct_parents_per_method']
 for event in f['events']:
  v={k:z for k,z in event.items() if k not in ('cursor','delivery_duplicate_of')}
  if event['id'] in seen:
   if canonical(v)!=canonical(seen[event['id']]):raise ValueError('CONFLICTING_DUPLICATE')
  else:
   seen[event['id']]=v
   if event['environment']!='FIXTURE':raise ValueError('MIXED_FIXTURE_PROVENANCE')
   if not isinstance(event.get('observation_revision'),int) or event['observation_revision']<0:raise ValueError('MISSING_REVISION')
   previous=latest.get(event['parent'])
   if previous and event['observation_revision']<previous['observation_revision']:pass
   elif previous and event['observation_revision']==previous['observation_revision']:
    old={k:z for k,z in previous.items() if k not in ('cursor','delivery_duplicate_of','id')}
    new={k:z for k,z in event.items() if k not in ('cursor','delivery_duplicate_of','id')}
    if canonical(old)!=canonical(new):raise ValueError('CONFLICTING_REVISION')
   else:latest[event['parent']]=event
  cost={x:[] for x in alg}
  for row in latest.values():
   if row['status']!='MATURE':continue
   q=Decimal(row['filled_base'])
   if q<0 or q>Q:raise ValueError('QUANTITY_INVARIANT')
   if q and row['fill_price'] is None:raise ValueError('MISSING_ACTUAL_FILL')
   if q<Q and row['horizon_price'] is None:raise ValueError('UNKNOWN_NONFILL_BENCHMARK')
   loss=q*(Decimal(row['fill_price'])-p0) if q else Decimal(0)
   if q<Q:loss+=(Q-q)*(Decimal(row['horizon_price'])-p0)
   loss+=Decimal(row['explicit_cost']);cost[row['method']].append(loss)
  means={x:sum(vals)/Decimal(len(vals)) for x,vals in cost.items() if len(vals)>=minimum}
  choice=min(means,key=lambda x:(means[x],f['policy']['stable_tie_break'].index(x))) if means else f['policy']['fallback']
  chosen[event['cursor']]=choice
 return chosen,{k:str(v.quantize(Decimal('.01'))) for k,v in means.items()},len([x for x in latest.values() if x['status']=='MATURE'])

def schema_checks(d):
 from jsonschema import Draft202012Validator, FormatChecker
 s=d['schemas'];Draft202012Validator.check_schema(s);v=Draft202012Validator(s,format_checker=FormatChecker());e=[]
 for rel in d['example_index']['fixtures']:
  record=read('contracts/self_optimization/'+rel)
  for issue in v.iter_errors(record):e.append('SCHEMA:'+rel+':'+issue.json_path)
  if record.get('environment')!='FIXTURE':e.append('EXAMPLE_NOT_FIXTURE:'+rel)
 return e

def package_check():
 m=read('MANIFEST.json');e=[];files=m['files'];actual={p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='MANIFEST.json'}
 if actual!=set(files):e.append('MANIFEST_FILE_SET_MISMATCH')
 for name,meta in files.items():
  p=ROOT/name
  if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=meta['sha256'] or p.stat().st_size!=meta['bytes']:e.append('PACKAGE_HASH:'+name)
 return e

def selftests(d,parents):
 rows=[]
 def probe(name,fn):
  x=copy.deepcopy(d);fn(x)
  try:errors=check(x,parents,False);detected=bool(errors)
  except Exception as ex:errors=[type(ex).__name__+':'+str(ex)];detected=False
  rows.append({'id':name,'detected':detected,'finding_count':len(errors),'examples':errors[:3]})
 probe('DELETE_PARENT_REQUIREMENT',lambda x:x['requirements']['requirements'].pop(0))
 probe('ALTER_PARENT_REQUIREMENT',lambda x:x['requirements']['requirements'][0].update(text='thinned'))
 probe('DELETE_SELF_OPTIMIZATION_OBJECTIVE',lambda x:x['requirements'].update(requirements=[a for a in x['requirements']['requirements'] if a['id']!='VAN-SO-001']))
 probe('DELETE_CRYPTO_EXECUTION',lambda x:x['requirements'].update(requirements=[a for a in x['requirements']['requirements'] if a['id']!='VAN-CRYPTO-001']))
 probe('DUPLICATE_REQUIREMENT',lambda x:x['requirements']['requirements'].append(copy.deepcopy(x['requirements']['requirements'][0])))
 probe('DELETE_LEGACY_ACTION',lambda x:x['actions']['actions'].pop())
 probe('DELETE_CONTEXT',lambda x:x['surfaces']['surfaces'].pop())
 probe('DELETE_PARENT_ACCEPTANCE_TEST',lambda x:x['tests']['tests'].pop(0))
 probe('DELETE_NEW_LOOP_ACCEPTANCE',lambda x:x['tests']['tests'].pop())
 probe('MARK_APPLICATION_TEST_PASSED',lambda x:x['tests']['tests'][0].update(execution_state='PASSED'))
 probe('DELETE_UNIT',lambda x:x['plan']['units'].pop(5))
 probe('DUPLICATE_UNIT',lambda x:x['plan']['units'].append(copy.deepcopy(x['plan']['units'][0])))
 probe('CYCLE',lambda x:x['plan']['units'][0]['dependencies'].append('BG-001'))
 probe('FRONTEND_BEFORE_BG',lambda x:next(a for a in x['plan']['units'] if a['id']=='UX-001').update(dependencies=['BE-001']))
 probe('BG_BACKEND_DENOMINATOR_REMOVAL',lambda x:x['plan']['required_backend_ids'].pop())
 probe('LEARNING_BEFORE_EVALUATOR',lambda x:next(a for a in x['plan']['units'] if a['id']=='BE-036').update(dependencies=['BE-001']))
 probe('FALSE_UNIT_COMPLETION',lambda x:x['plan']['units'][3].update(status='COMPLETE'))
 probe('ADD_DAEMON_REQUIREMENT',lambda x:x['plan'].update(new_deployable_services_required=64))
 probe('FORGE_F15',lambda x:x['f15'].update(status='FORENSIC_BUILD_READY',issuer='self',signature='yes'))
 probe('FORGE_BG',lambda x:x['bg'].update(status='BACKEND_COMPLETE',signature='yes'))
 probe('DEFAULT_LIVE_EXPLORATION',lambda x:x['authmap'].update(live_exploration_enabled_by_default=True))
 probe('OPTIMIZER_WITHDRAWAL_RIGHT',lambda x:next(a for a in x['authmap']['actions'] if a['action']=='WITHDRAW_FUNDS').update(level='AUTOMATIC_OPERATIONAL_OPTIMIZATION'))
 probe('UNQUALIFIED_PROMOTION',lambda x:next(a for a in x['authmap']['actions'] if a['action']=='ACTIVATE_NEW_POLICY').update(required_authority='BACKTEST_PASS'))
 probe('REMOVE_PRODUCT_TRUTH_MAP',lambda x:x['truth']['mappings'].pop())
 probe('DROP_LATE_FILL_RECONCILIATION',lambda x:next(m for m in x['machines']['machines'] if m['id']=='SO-CHILD').update(transitions=[t for t in next(m for m in x['machines']['machines'] if m['id']=='SO-CHILD')['transitions'] if not (t['from']=='RECONCILED' and t['to']=='OUTCOME_UNKNOWN')]))
 probe('DUPLICATE_MACHINE',lambda x:x['machines']['machines'].append(copy.deepcopy(x['machines']['machines'][0])))
 probe('DUPLICATE_STATE',lambda x:x['machines']['machines'][0]['states'].append('APPROVED'))
 probe('DUPLICATE_TRANSITION',lambda x:x['machines']['machines'][0]['transitions'].append(copy.deepcopy(x['machines']['machines'][0]['transitions'][0])))
 probe('UNKNOWN_TRANSITION_STATE',lambda x:x['machines']['machines'][0]['transitions'][0].update(to='PAID'))
 probe('REMOVED_INDEPENDENT_AUTHORITY_INVARIANT',lambda x:x['invariants'].update(invariants=[a for a in x['invariants']['invariants'] if a['id']!='INV-AUTH']))
 probe('REMOVE_TYPED_PROOF',lambda x:x['proofs']['proofs'].pop(0))
 probe('PREPARED_LOCK_RELABELLED_SIGNED',lambda x:x['lock'].update(status='OWNER_SIGNED'))
 probe('SOURCE_GAP_DROPPED',lambda x:x['crosswalk']['gaps'].pop())
 def edge_mut(machine,to):
  def mutate(x):
   m=next(a for a in x['machines']['machines'] if a['id']==machine)
   t=next(a for a in m['transitions'] if a['to']==to);t['proof_predicates']=['SOURCE_VALID']
  return mutate
 for a,b in [('SO-CHILD','SUBMITTING'),('SO-CHILD','FILLED'),('SO-PARENT','ECONOMICALLY_RECONCILED'),('SO-EVIDENCE','APPLIED'),('SO-CANDIDATE','AUTHORIZED'),('SO-BINDING','ACTIVE')]:probe('SHORTCUT_'+a+'_'+b,edge_mut(a,b))
 # Strict JSON parsing poison.
 try:parse('{"id":1,"id":2}');hit=False
 except ValueError:hit=True
 rows.append({'id':'DUPLICATE_JSON_KEY','detected':hit})
 # Record-shape poisons do not establish authenticity, but must not admit invalid domains.
 from jsonschema import Draft202012Validator
 validator=Draft202012Validator(d['schemas'])
 examples={Path(p).name.split('.')[0]:read('contracts/self_optimization/'+p) for p in d['example_index']['fixtures']}
 cases=[('CRYPTO_WITHDRAWAL_ENABLED','CryptoVenueProfile','trade_key_withdrawal_permission',True),('CRYPTO_SPOT_SCOPE_REMOVED','CryptoVenueProfile','spot_only',False),('UNKNOWN_SCHEMA_FIELD','ExecutionObjective','mint_money',True),('NEGATIVE_QUANTITY','ExecutionObjective','quantity_base','-1'),('NONFINITE_MONEY','ExecutionQualityMeasurement','total_benchmark_loss','NaN')]
 for name,kind,k,val in cases:
  x=copy.deepcopy(examples[kind]);x[k]=val;rows.append({'id':name,'detected':bool(list(validator.iter_errors(x)))})
 # Demonstrated causal fixture checks, not trained or live performance.
 x=copy.deepcopy(d['fixture']);x['events'][4]['horizon_price']=None
 try:fixture_model(x);hit=False
 except ValueError:hit=True
 rows.append({'id':'MISSING_NONFILL_IS_NOT_ZERO','detected':hit})
 x=copy.deepcopy(d['fixture']);x['events'][-1]['explicit_cost']='9'
 try:fixture_model(x);hit=False
 except ValueError:hit=True
 rows.append({'id':'CONFLICTING_DUPLICATE_OUTCOME','detected':hit})
 return rows

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--selftest',action='store_true');ap.add_argument('--check-package',action='store_true');ap.add_argument('--json',action='store_true');args=ap.parse_args()
 d={k:read(v) for k,v in FILES.items()};parents={k:read('lineage/rev1_13/'+p)[field] for k,(p,field) in PARENTS.items()}
 if args.check_package:
  e=package_check();o={'scope':'ARCHIVE_MEMBER_IDENTITY_ONLY','findings':e,'files_checked':len(read('MANIFEST.json')['files'])}
 elif args.selftest:
  cases=selftests(d,parents);o={'scope':'ADVERSARIAL_DOCUMENT_AND_SYNTHETIC_FIXTURE_CHECKS_ONLY','detected':sum(x['detected'] for x in cases),'total':len(cases),'cases':cases};e=[x['id'] for x in cases if not x['detected']]
 else:
  e=check(d,parents)+schema_checks(d)
  selected,cost,n=fixture_model(d['fixture']);exp=d['fixture']['expected']
  for cursor in (2,4,5,6):
   if selected[cursor]!=exp[f'after_cursor_{cursor}']:e.append('POSITIVE_FIXTURE_SELECTION:'+str(cursor))
  if cost!={'A':exp['method_A_cost'],'B':exp['method_B_cost']} or n!=exp['distinct_mature_parent_count']:e.append('POSITIVE_FIXTURE_ACCOUNTING')
  # Load a fresh model state for a cold replay and compare logical output.
  if fixture_model(copy.deepcopy(d['fixture']))!=(selected,cost,n):e.append('FIXTURE_REPLAY_MISMATCH')
  result=subprocess.run([sys.executable,str(ROOT/'plan/render_plan.py'),'--check'],capture_output=True,text=True,timeout=30)
  if result.returncode:e.append('STALE_PLAN:'+result.stdout.strip())
  o={'scope':'DOCUMENT_SCHEMA_GRAPH_AND_SYNTHETIC_MODEL_ONLY','findings':sorted(set(e)),'requirements':len(d['requirements']['requirements']),'planned_application_contracts':len(d['tests']['tests']),'application_tests_executed':0,'units':len(d['plan']['units']),'schema_examples':len(d['example_index']['fixtures']),'synthetic_loop':{'selections':selected,'mean_benchmark_cost':cost,'mature_distinct_parents':n,'cold_replay_equal':True,'not_actual_VATI_execution':True},'F15':'NOT_ISSUED','BG':'NOT_ISSUED'}
 print(json.dumps(o,indent=2,sort_keys=True) if args.json else json.dumps(o,sort_keys=True));return 1 if e else 0
if __name__=='__main__':
 try:raise SystemExit(main())
 except Exception as exc:print(type(exc).__name__+': '+str(exc),file=sys.stderr);raise SystemExit(2)
