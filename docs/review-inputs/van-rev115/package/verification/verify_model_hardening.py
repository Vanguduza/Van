"""Rev1.17 document integration/schema/negative controls; no model/economic invocation."""
from pathlib import Path
import copy,json,hashlib
from decimal import Decimal
from jsonschema import Draft202012Validator
P=Path(__file__).resolve().parents[1]
FILES={'authority':'CANONICAL_AUTHORITY.json','requirements':'traceability/REQUIREMENTS_AND_DU_MAPPING.json','tests':'verification/TEST_CONTRACTS.json','new_requirements':'traceability/REV117_REQUIREMENTS.json','new_tests':'verification/REV117_ACCEPTANCE_CONTRACTS.json','plan':'plan/DEVELOPMENT_PLAN.json','baseline':'lineage/REV116_OBJECT_FINGERPRINTS.json','surfaces':'design/ALL_SURFACE_CONTRACTS.json','actions':'traceability/LEGACY_349_ACTIONS.json','truth':'traceability/PRODUCT_TRUTH.json','contract':'contracts/self_optimization/MODEL_USE_CONTRACT.json','schema':'contracts/self_optimization/MODEL_USE_RECORDS.schema.json','examples':'contracts/self_optimization/MODEL_USE_EXAMPLES.json','experiments':'research/PROFITABILITY_EXPERIMENTS.json','sources':'research/REV117_SOURCE_REGISTER.json','contexts':'design/MODEL_HARDENING_CONTEXT_BINDINGS.json','catalog':'contracts/BACKEND_SERVICE_CATALOG.json'}
def load():return {k:json.loads((P/f).read_text()) for k,f in FILES.items()}
def digest(o):return hashlib.sha256(json.dumps(o,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def check(d):
 e=[]
 def need(ok,code):
  if not ok:e.append(code)
 rr={r['id']:r for r in d['requirements']['requirements']};tt={t['id']:t for t in d['tests']['tests']};uu={u['id']:u for u in d['plan']['units']};ss={s['id']:s for s in d['surfaces']['surfaces']};services={s['id']:s for s in d['catalog']['services']}
 need(len(rr)==d['requirements']['count']==d['requirements']['total']==d['authority']['active_requirement_count']==324,'REQUIREMENT_COUNT')
 need(len(tt)==d['tests']['count']==d['authority']['active_application_test_count']==1610,'TEST_COUNT')
 expected={f'VAN-JM-{i:03d}' for i in range(1,9)};test_ids={f'T-VAN-JM-{i:03d}-{k}' for i in range(1,9) for k in ['POS','NEG','REC']}
 need({r['id'] for r in d['new_requirements']['requirements']}==expected,'HARDENING_SCOPE_LOSS');need(set(d['contract']['requirements'])==expected,'CONTRACT_SCOPE_LOSS')
 need({t['id'] for t in d['new_tests']['tests']}==test_ids,'ACCEPTANCE_COVERAGE')
 for r in d['new_requirements']['requirements']:
  need(rr.get(r['id'])==r,'REQUIREMENT_NOT_IN_MAIN:'+r['id'])
  for uid in r['backend_units']+r['frontend_units']+r['other_units']:
   need(r['id'] in d['plan']['requirement_ownership'].get(uid,[]),'MISSING_PLAN_OWNER:'+r['id']+':'+uid)
   if uid in services:need(r['id'] in services[uid].get('rev117_requirements',[]),'MISSING_SERVICE_REQUIREMENT:'+r['id']+':'+uid)
 for t in d['new_tests']['tests']:
  need(tt.get(t['id'])==t,'TEST_NOT_IN_MAIN:'+t['id']);need(t['execution_state']=='NOT_RUN','FALSE_APPLICATION_RESULT')
  need(t['requirement_id'] in rr and t['id'] in rr.get(t['requirement_id'],{}).get('test_ids',[]),'UNLINKED_TEST')
  need(t.get('execution_phase')=='BACKEND_HEADLESS_BEFORE_BG' and not {'PRE-002','PRE-003'}&set([t['unit'],*t['additional_units']]),'WRONG_ACCEPTANCE_PHASE')
  for uid in [t['unit'],*t['additional_units']]:need(t['id'] in uu.get(uid,{}).get('acceptance_test_ids',[]),'MISSING_PLAN_TEST:'+t['id'])
 for key,field in [('requirements','requirements'),('tests','tests'),('surfaces','surfaces'),('actions','actions'),('truth','truth_atoms')]:
  current={r['id']:digest(r) for r in d[key][field]};need(all(current.get(k)==v for k,v in d['baseline']['objects'][key].items()),'PRESERVATION:'+key)
 need([{k:u[k] for k in ['id','packet_id','sequence','dependencies']} for u in d['plan']['units']]==d['baseline']['unit_graph'],'UNIT_GRAPH_CHANGED')
 true_flags=['no_model_rpc_on_financial_path','shared_jev_owner_preserved','jev_score_not_trade_probability','native_scope_and_effect_validation','all_attempts_reserved_before_transport','unknown_cost_retains_liability','durable_global_budget','resolved_identity_epoch_required','replay_recorded_response_without_model_call','model_weight_leakage_assessed','all_opportunities_and_trials_retained','probability_target_requires_calibration','net_cost_and_risk_matched_qualification','reviewer_and_holdout_separated','generated_code_isolated','bounded_update_rate_and_hysteresis','economic_health_separate_from_procedural_health','native_authority_required_for_activation','no_new_deployable_services','all_prior_model_capabilities_preserved']
 for k in true_flags:need(d['contract']['invariants'].get(k) is True,'MISSING_INVARIANT:'+k)
 for k in ['automatic_live_exploration','model_can_widen_risk','benchmark_is_profit_evidence']:need(d['contract']['invariants'].get(k) is False,'UNAUTHORIZED_OR_FALSE_CLAIM:'+k)
 source_ids={s['id'] for s in d['sources']['sources']}
 for model in d['contract']['models']:
  need(model['source_refs'] and set(model['source_refs'])<=source_ids,'UNSOURCED_MODEL')
  need(model['access_tested'] is False and model['economic_qualification']=='NOT_RUN','FALSE_MODEL_QUALIFICATION')
 need({m['requested_model'] for m in d['contract']['models']}=={'gemini-4-argon','deepseek-v4-pro','deepseek-flash'},'WRONG_MODEL_IDENTITY')
 for s in d['sources']['sources']:need(hashlib.sha256((P/s['archived_excerpt']).read_bytes()).hexdigest()==s['excerpt_sha256'],'SOURCE_EXCERPT_IDENTITY')
 experiments=d['experiments']['experiments'];need({x['id'] for x in experiments}=={f'JM-EXP-{i:03d}' for i in range(1,7)},'EXPERIMENT_COVERAGE')
 for x in experiments:
  need(x['state']=='NOT_RUN','FALSE_ECONOMIC_RESULT')
  need({'complete_trial_budget','protected_confirmation_windows','cost_schedule_and_reservation','risk_limits','positive_power_and_null_ensemble_oracles'}<=set(x['required_pre_run_bindings']),'INCOMPLETE_STUDY_BINDINGS')
  need('INCONCLUSIVE' in x['outcomes'] and 'BASELINE_RETAINED' in x['outcomes'],'FORCED_PROFIT_CLAIM')
 need('design/MODEL_HARDENING_CONTEXT_BINDINGS.json' in d['surfaces']['extension_registries'],'ORPHAN_CONTEXTS')
 for c in d['contexts']['bindings']:
  need(c['context_id'] in ss,'UNKNOWN_CONTEXT')
  need({'IDENTITY_UNVERIFIED','COST_UNKNOWN','CALIBRATION_MISSING','INCONCLUSIVE'}<=set(c['required_states']),'HIDDEN_ERROR_OR_UNKNOWN_STATE')
  need(set(c['operation_ids'])<=set(d['contract']['existing_api_operations']),'UNBOUND_UI_OPERATION')
 need(set(d['contract']['owner_units'])<=set(uu),'UNKNOWN_CONTRACT_OWNER')
 return sorted(set(e))
def main():
 d=load();rows=[]
 def test(k,v):rows.append({'id':k,'passed':bool(v)})
 errors=check(d);test('INTEGRATION',not errors)
 for flag in ['no_model_rpc_on_financial_path','all_attempts_reserved_before_transport','unknown_cost_retains_liability','model_weight_leakage_assessed','probability_target_requires_calibration','reviewer_and_holdout_separated','economic_health_separate_from_procedural_health']:
  x=copy.deepcopy(d);x['contract']['invariants'][flag]=False;test('DROP_'+flag,'MISSING_INVARIANT:'+flag in check(x))
 for name,mutate,code in [('REMOVE_REQUIREMENT',lambda x:x['requirements']['requirements'].pop(),'REQUIREMENT_NOT_IN_MAIN:'),('REMOVE_TEST',lambda x:x['tests']['tests'].pop(),'TEST_NOT_IN_MAIN:'),('FORGE_MODEL_WIN',lambda x:x['contract']['models'][0].update(economic_qualification='PASS'),'FALSE_MODEL_QUALIFICATION'),('RELABEL_ARGON',lambda x:x['contract']['models'][0].update(requested_model='grok-4'),'WRONG_MODEL_IDENTITY'),('NO_CONFIRMATION',lambda x:x['experiments']['experiments'][0]['required_pre_run_bindings'].remove('protected_confirmation_windows'),'INCOMPLETE_STUDY_BINDINGS'),('HIDE_UNKNOWN_COST',lambda x:x['contexts']['bindings'][0]['required_states'].remove('COST_UNKNOWN'),'HIDDEN_ERROR_OR_UNKNOWN_STATE')]:
  x=copy.deepcopy(d);mutate(x);test(name,any(v.startswith(code) for v in check(x)))
 Draft202012Validator.check_schema(d['schema']);v=Draft202012Validator(d['schema']);examples={r['record_type']:r for r in d['examples']['examples']}
 for name,obj in examples.items():test('VALID_'+name,v.is_valid(obj))
 for name,field,value in [('ModelUseRecord','resolved_model',None),('ModelUseRecord','evidence_epoch',None),('ModelUseRecord','calibration_ref',None),('ModelUseRecord','financial_authority',True),('ResearchBudgetReservation','liability_retained',False),('ModelQualificationEvidence','protected_confirmation_ref',None),('ModelQualificationEvidence','cost_and_risk_comparison_ref',None),('ModelQualificationEvidence','independent_review_ref',None)]:
  obj=copy.deepcopy(examples[name]);obj[field]=value;test('REJECT_'+name+'_'+field,not v.is_valid(obj))
 obj=copy.deepcopy(examples['ModelQualificationEvidence']);obj.update(evidence_state='INCONCLUSIVE',protected_confirmation_ref=None);test('PRESERVE_INCONCLUSIVE',v.is_valid(obj))
 focus=(P/d['authority']['focused_blueprint']).read_text().rstrip();master=(P/d['authority']['master']).read_text();test('FULL_NORMATIVE_SECTION','### 8.7 Hardened self-improvement' in focus and focus in master)
 test('NEW_TESTS_RENDERED',all(t in (P/d['authority']['rendered_plan']).read_text() for t in (f'T-VAN-JM-{i:03d}-{k}' for i in range(1,9) for k in ['POS','NEG','REC'])))
 test('ACTIVE_COUNTS','The active totals are 324 requirements and 1,610 planned application tests' in focus and 'Active Rev1.16:' not in master)
 for name,inp,out,expected in [('ARGON','2','10','0.08'),('ARGON_DEC','4','20','0.16'),('DS_PRO_PEAK','1.32','3.96','0.04224'),('DS_PRO_OFFPEAK','.66','1.98','.02112'),('DS_FLASH_PEAK','.3','1.2','.0108'),('DS_FLASH_OFFPEAK','.15','.6','.0054')]:test('TOKEN_COST_ARITHMETIC_'+name,(Decimal(20000)*Decimal(inp)+Decimal(4000)*Decimal(out))/Decimal(1000000)==Decimal(expected))
 print(json.dumps({'scope':'DOCUMENT_INTEGRATION_SCHEMA_MUTATIONS_AND_COST_ARITHMETIC_ONLY','passed':sum(r['passed'] for r in rows),'total':len(rows),'findings':errors,'model_invocations':0,'application_tests_executed':0,'economic_experiments_executed':0,'cases':rows},indent=2));return 0 if not errors and all(r['passed'] for r in rows) else 1
if __name__=='__main__':raise SystemExit(main())
