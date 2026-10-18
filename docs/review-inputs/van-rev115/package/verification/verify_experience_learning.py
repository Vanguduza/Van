"""Rev1.16 documentary integration and schema regressions, never application evidence."""
from pathlib import Path
import copy,hashlib,json,re,sys
from jsonschema import Draft202012Validator,FormatChecker
P=Path(__file__).resolve().parents[1]
FILES={'requirements':'traceability/REQUIREMENTS_AND_DU_MAPPING.json','new_requirements':'traceability/REV116_REQUIREMENTS.json','tests':'verification/TEST_CONTRACTS.json','new_tests':'verification/REV116_ACCEPTANCE_CONTRACTS.json','plan':'plan/DEVELOPMENT_PLAN.json','authority':'CANONICAL_AUTHORITY.json','contract':'contracts/self_optimization/EXPERIENCE_LEARNING_CONTRACT.json','schema':'contracts/self_optimization/EXPERIENCE_LEARNING_RECORDS.schema.json','examples':'contracts/self_optimization/EXPERIENCE_LEARNING_EXAMPLES.json','contexts':'design/EXPERIENCE_LEARNING_CONTEXT_BINDINGS.json','surfaces':'design/ALL_SURFACE_CONTRACTS.json','catalog':'contracts/BACKEND_SERVICE_CATALOG.json','baseline':'lineage/REV115_OBJECT_FINGERPRINTS.json','actions':'traceability/LEGACY_349_ACTIONS.json','truth':'traceability/PRODUCT_TRUTH.json','extensions':'contracts/self_optimization/UNIT_EXTENSIONS.json'}
def read(p):return json.loads((P/p).read_text())
def load():return {k:read(p) for k,p in FILES.items()}
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def check(d):
 e=[]
 def need(ok,code):
  if not ok:e.append(code)
 rr={r['id']:r for r in d['requirements']['requirements']};tt={t['id']:t for t in d['tests']['tests']};uu={u['id']:u for u in d['plan']['units']};ss={s['id']:s for s in d['surfaces']['surfaces']}
 need(len(rr)==len(d['requirements']['requirements'])==d['requirements']['total']==d['requirements']['count']==316,'REQUIREMENT_COUNT_OR_DUPLICATE')
 need(len(tt)==len(d['tests']['tests'])==1586,'TEST_COUNT_OR_DUPLICATE')
 need(d['authority']['active_requirement_count']==316 and d['authority']['active_application_test_count']==1586,'STALE_AUTHORITY_COUNTS')
 need({r['id'] for r in d['new_requirements']['requirements']}=={f'VAN-EL-{i:03d}' for i in range(1,8)},'REQUIRED_LEARNING_SCOPE')
 expected={f'EL-AT-{i:03d}-{k}' for i in range(1,15) for k in ['POS','NEG','REC']}
 need({t['id'] for t in d['new_tests']['tests']}==expected,'SCENARIO_COVERAGE')
 ext={x['unit_id']:x for x in d['extensions']['extensions']}
 for r in d['new_requirements']['requirements']:
  need(rr.get(r['id'])==r,'REQUIREMENT_NOT_IN_MAIN:'+r['id'])
  need(set(r['test_ids'])<=expected,'INVALID_REQUIREMENT_TEST:'+r['id'])
  for uid in r['backend_units']+r['frontend_units']+r['other_units']:
   need(uid in uu and r['id'] in d['plan']['requirement_ownership'].get(uid,[]),'MISSING_PLAN_OWNER:'+r['id']+':'+uid)
   need(r['id'] in ext.get(uid,{}).get('new_requirements',[]),'MISSING_UNIT_EXTENSION:'+r['id']+':'+uid)
 for t in d['new_tests']['tests']:
  need(tt.get(t['id'])==t,'TEST_NOT_IN_MAIN:'+t['id'])
  need(t.get('execution_state')=='NOT_RUN','FABRICATED_APPLICATION_RESULT:'+t['id'])
  need(t.get('execution_phase')=='BACKEND_HEADLESS_BEFORE_BG' and not ({'PRE-002','PRE-003'} & set([t['unit'],*t['additional_units']])),'APPLICATION_TEST_AT_PRE_GATE:'+t['id'])
  need(t['requirement_id'] in rr and t['id'] in rr.get(t['requirement_id'],{}).get('test_ids',[]),'TEST_REQUIREMENT_LINK:'+t['id'])
  need(all(t.get(k) for k in ['preconditions','action','expectation','oracle','receipt_binding','command_binding']),'INCOMPLETE_ACCEPTANCE:'+t['id'])
  for uid in [t['unit'],*t['additional_units']]:need(t['id'] in uu.get(uid,{}).get('acceptance_test_ids',[]),'MISSING_PLAN_TEST:'+t['id']+':'+uid)
 for key,field in [('requirements','requirements'),('tests','tests'),('surfaces','surfaces'),('actions','actions'),('truth','truth_atoms')]:
  current={r['id']:digest(r) for r in d[key][field]}
  need(all(current.get(i)==h for i,h in d['baseline']['objects'][key].items()),'PRESERVATION:'+key)
 need([{k:u[k] for k in ['id','packet_id','sequence','dependencies']} for u in d['plan']['units']]==d['baseline']['unit_graph'],'UNIT_GRAPH_CHANGED')
 invariants={'single_outcome_proves_edge':False,'outcome_rewrites_original_decision':False,'unknown_cost_equals_zero':False,'llm_confidence_is_win_probability':False,'causal_claim_requires_identification':True,'all_trials_retained':True,'protected_confirmation_required':True,'dependence_and_selection_adjustment_required':True,'null_and_power_controls_required':True,'automatic_state_update_within_qualified_bounds':True,'policy_evolution_requires_independent_qualification_and_authority':True,'supported_state_requires_native_evidence_resolution':True,'live_randomized_exploration_enabled':False}
 need(all(d['contract']['invariants'].get(k)==v for k,v in invariants.items()),'LEARNING_INVARIANT_LOSS')
 paths=d['contract']['consumer_paths'];need({x['target'] for x in paths}=={'STRATEGY','EXECUTION'} and len(paths)==2,'BOTH_LOOPS_REQUIRED')
 for x in paths:
  need(all(x[k] in uu for k in ['producer','lineage','diagnosis','evaluator','adaptation','consumer']),'UNKNOWN_LOOP_OWNER')
  need(x['consumer']=={'STRATEGY':'BE-013','EXECUTION':'BE-010'}.get(x['target']),'WRONG_REAL_CONSUMER')
  need('EL-AT-012-NEG' in x['end_to_end_tests'] and set(x['end_to_end_tests'])<=expected,'MISSING_OBSERVER_REMOVAL_TEST')
 ops=d['contract']['operations'];opmap={o['id']:o for o in ops};catalog={s['id']:s for s in d['catalog']['services']}
 need(set(opmap)=={f'EL-OP-{i:03d}' for i in range(1,9)} and len(ops)==8,'OPERATION_COVERAGE')
 need(len({(o['method'],o['proposed_path']) for o in ops})==len(ops),'DUPLICATE_ROUTE')
 for o in ops:
  need(o['response_record'] in d['schema']['$defs'],'UNKNOWN_RESPONSE_SCHEMA')
  need(o['implementation_status']=='SPECIFIED_NOT_IMPLEMENTED','FALSE_ENDPOINT_IMPLEMENTATION')
  for uid in [o['owner_unit'],o['gateway_unit']]:need(o['id'] in catalog.get(uid,{}).get('experience_learning_operation_ids',[]),'MISSING_SERVICE_OPERATION:'+o['id']+':'+uid)
  if o['method']=='POST':need(o['request_record']=='LearningCommand' and 'OUTCOME_UNKNOWN' in o['errors'],'COMMAND_RECOVERY_MISSING')
 need('design/EXPERIENCE_LEARNING_CONTEXT_BINDINGS.json' in d['surfaces'].get('extension_registries',[]),'ORPHAN_CONTEXT_EXTENSION')
 need(len(d['contexts']['bindings'])==8,'CONTEXT_COVERAGE')
 for b in d['contexts']['bindings']:
  need(b['context_id'] in ss,'NEW_OR_UNKNOWN_CONTEXT')
  need(set(b['operation_ids'])<=set(opmap),'UNKNOWN_CONTEXT_OPERATION')
  need(set(b['backend_units']+b['frontend_units'])<=set(uu),'UNKNOWN_CONTEXT_OWNER')
  need({'INCONCLUSIVE','STALE','ERROR','OUTCOME_UNKNOWN'}<=set(b['states']),'MISSING_CONTEXT_ERROR_STATE')
 need(set().union(*(set(b['operation_ids']) for b in d['contexts']['bindings']))==set(opmap),'OPERATION_WITHOUT_OWNER_SURFACE')
 return sorted(set(e))
def main():
 d=load();rows=[]
 def test(name,ok):rows.append({'id':name,'passed':bool(ok)})
 errors=check(d);test('INTEGRATION',not errors)
 mutations=[('DROP_REQUIREMENT',lambda x:x['requirements']['requirements'].pop(),'REQUIREMENT_NOT_IN_MAIN:'),('DROP_TEST',lambda x:x['tests']['tests'].pop(),'TEST_NOT_IN_MAIN:'),('STALE_COUNT',lambda x:x['authority'].update(active_application_test_count=1544),'STALE_AUTHORITY_COUNTS'),('DROP_STRATEGY_LOOP',lambda x:x['contract']['consumer_paths'].pop(0),'BOTH_LOOPS_REQUIRED'),('DROP_OBSERVER_TEST',lambda x:x['contract']['consumer_paths'][0]['end_to_end_tests'].remove('EL-AT-012-NEG'),'MISSING_OBSERVER_REMOVAL_TEST'),('FALSE_EDGE_FROM_ONE_TRADE',lambda x:x['contract']['invariants'].update(single_outcome_proves_edge=True),'LEARNING_INVARIANT_LOSS'),('ORPHAN_CONTEXT',lambda x:x['surfaces']['extension_registries'].clear(),'ORPHAN_CONTEXT_EXTENSION'),('DELETE_INCONCLUSIVE',lambda x:x['contexts']['bindings'][0]['states'].remove('INCONCLUSIVE'),'MISSING_CONTEXT_ERROR_STATE'),('FORGED_TEST_RESULT',lambda x:x['new_tests']['tests'][0].update(execution_state='PASS'),'FABRICATED_APPLICATION_RESULT:'),('CHANGE_PARENT_TEST',lambda x:x['tests']['tests'][0].update(execution_state='PASS'),'PRESERVATION:tests')]
 mutations += [('UNPROTECTED_CONFIRMATION',lambda x:x['contract']['invariants'].update(protected_confirmation_required=False),'LEARNING_INVARIANT_LOSS'),('APPLICATION_AT_PRE',lambda x:x['new_tests']['tests'][0]['additional_units'].append('PRE-002'),'APPLICATION_TEST_AT_PRE_GATE:'),('DROP_SERVICE_BINDING',lambda x:next(a for a in x['catalog']['services'] if a['id']=='BE-012')['experience_learning_operation_ids'].clear(),'MISSING_SERVICE_OPERATION:')]
 for name,mutate,code in mutations:
  x=copy.deepcopy(d);mutate(x);test(name,any(e.startswith(code) for e in check(x)))
 Draft202012Validator.check_schema(d['schema']);validator=Draft202012Validator(d['schema'],format_checker=FormatChecker())
 by={x.get('record_type', 'LearningCommandReceipt' if 'command_id' in x else 'LearningCommand'):x for x in d['examples']['examples']}
 for name,obj in by.items():test('VALID_'+name,validator.is_valid(obj))
 for name,field,val in [('TradeExperience','reconciled_economics_ref',None),('TradeDiagnosis','causal_identification_ref',None),('EvidenceAssessment','null_control_results_ref',None),('EvidenceAssessment','power_control_results_ref',None),('EvidenceAssessment','selection_adjustment_ref',None),('EvidenceAssessment','independent_review_ref',None),('LearningChange','promotion_authority_ref',None),('LearningChange','consumer_receipt_ref',None),('LearningCommand','idempotency_key',''),('LearningCommandReceipt','readback_ref',None)]:
  obj=copy.deepcopy(by[name])
  if name=='TradeExperience':obj['outcome_maturity']='MATURE'
  if name=='TradeDiagnosis':obj['claim_type']='CAUSALLY_SUPPORTED'
  if name=='LearningCommandReceipt':obj.update(status='SUCCEEDED',result_ref='fixture:result')
  obj[field]=val;test('REJECT_'+name+'_'+field,not validator.is_valid(obj))
 obj=copy.deepcopy(by['EvidenceAssessment']);obj.update(assessment_state='INCONCLUSIVE',null_control_results_ref=None,power_control_results_ref=None,qualification_ref=None,independent_review_ref=None)
 test('PRESERVE_INCONCLUSIVE_WITH_MISSING_EVIDENCE',validator.is_valid(obj))
 focus=(P/d['authority']['focused_blueprint']).read_text().rstrip();master=(P/d['authority']['master']).read_text();test('NORMATIVE_SECTION_EMBEDDED','### 8.6 Learning from trading experience' in focus and focus in master)
 test('ACTIVE_COUNTS_IN_BLUEPRINT','The active totals are 316 requirements and 1,586 planned application tests' in focus and 'Active Rev1.15:' not in master)
 test('ALL_SCENARIOS_OUTLINED',all(f'`EL-AT-{i:03d}`' in focus for i in range(1,15)))
 test('INTEGRATED_PLAN_TEXT',all(t['id'] in (P/d['authority']['rendered_plan']).read_text() for t in d['new_tests']['tests']))
 out={'scope':'DOCUMENT_LINK_SCHEMA_AND_MUTATION_CHECKS_ONLY','passed':sum(r['passed'] for r in rows),'total':len(rows),'findings':errors,'application_tests_executed':0,'cases':rows};print(json.dumps(out,indent=2));return 0 if not errors and all(r['passed'] for r in rows) else 1
if __name__=='__main__':sys.exit(main())
