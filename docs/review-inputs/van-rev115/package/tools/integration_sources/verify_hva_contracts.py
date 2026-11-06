#!/usr/bin/env python3
"""Executable specification tests, not implementation or on-chain tests."""
from __future__ import annotations
import argparse,copy,datetime,decimal,json,math,sys
from pathlib import Path
from jsonschema import Draft202012Validator,FormatChecker
ROOT=Path(__file__).resolve().parents[1]
NAMES=['ChainAssetIdentity','ChainSourceObservation','DiscoveryCohortEvent','ChainSecurityFinding','WalletAttributionSnapshot','SellabilitySimulation','ExecutableQuoteFacts','ExecutionEconomicsForecast','NetEdgeAssessment','MatchedOpportunityExperiment','TypedTradingJudgment','ResearchCapabilityReadModel']
def dt(s):return datetime.datetime.fromisoformat(s.replace('Z','+00:00'))
def check(name,r,schemas):
 out=['SCHEMA:'+e.json_path for e in Draft202012Validator(schemas[name],format_checker=FormatChecker()).iter_errors(r)]
 if out:return out
 if dt(r['available_at'])>dt(r['decision_cutoff']):out.append('FUTURE_AVAILABILITY')
 if dt(r['expires_at'])<=dt(r['decision_cutoff']):out.append('EXPIRED_AT_USE')
 if r['reality']=='SYNTHETIC' and r['implementation_evidence_level'] not in ['SPEC_ONLY','E1_DOCUMENTED']:out.append('FIXTURE_AS_QUALIFICATION')
 if name=='ChainAssetIdentity':
  if r['asset_id']!=r['chain_id']+':'+r['canonical_token_address']:out.append('IDENTITY_BINDING')
  if r['chain_family']=='EVM' and not (r['canonical_token_address'].startswith('0x') and len(r['canonical_token_address'])==42):out.append('EVM_ENCODING')
  if r['chain_family']=='SOLANA' and r['raw_token_address']!=r['canonical_token_address']:out.append('SOLANA_CASE_CHANGE')
 if name=='ChainSourceObservation':
  if dt(r['source_published_at'])>dt(r['observed_at']) or dt(r['observed_at'])>dt(r['available_at']):out.append('SOURCE_CLOCK_ORDER')
  if r['reality']=='SYNTHETIC' and r['actual_provider_receipt_ref'] is not None:out.append('FAKE_PROVIDER_RECEIPT')
 if name=='DiscoveryCohortEvent' and dt(r['first_seen_at'])>dt(r['decision_at']):out.append('DISCOVERY_AFTER_DECISION')
 if name=='ChainSecurityFinding' and r['unsupported_capabilities'] and r['verdict']=='NO_HARD_BLOCK':out.append('UNSUPPORTED_AS_CLEAR')
 if name=='WalletAttributionSnapshot':
  if decimal.Decimal(r['adjusted_holdings_total'])>decimal.Decimal(r['raw_holdings_total']):out.append('ADJUSTMENT_INCREASES_HOLDINGS')
  if r['growth_claim'] is not None and (r['previous_snapshot_ref'] is None or not r['lookback_complete']):out.append('GROWTH_FROM_ONE_SNAPSHOT')
 if name=='ExecutionEconomicsForecast':
  if not math.isfinite(r['p_fill']):out.append('NONFINITE_PROBABILITY')
  if r['calibration_state']!='VALID' or r['applicability']!='IN_DOMAIN':out.append('FORECAST_UNQUALIFIED_FOR_ECONOMIC_USE')
  components=[x['component'] for x in r['incremental_costs']]
  if len(components)!=len(set(components)) or set(components)&set(r['included_in_exit_proceeds']):out.append('DOUBLE_COUNTED_COST')
 if name=='NetEdgeAssessment':
  d=decimal.Decimal
  if d(r['net_ev'])!=d(r['expected_exit_proceeds'])-d(r['entry_cash_cost'])-d(r['incremental_exit_costs'])-d(r['failure_cost']):out.append('NET_EV_IDENTITY')
  if r['reality']=='SYNTHETIC' and r['economic_state']=='ELIGIBLE_FOR_SCOPED_REVIEW':out.append('FIXTURE_AS_ECONOMIC_ADMISSION')
 if name=='MatchedOpportunityExperiment':
  if r['included_count']!=r['discovered_count']:out.append('SURVIVOR_COHORT')
  if r['rejected_count']+r['missing_count']>r['included_count']:out.append('COHORT_COUNT_INCONSISTENT')
  if dt(r['sealed_at'])>dt(r['decision_at']) or dt(r['outcome_available_at'])<=dt(r['decision_at']):out.append('EXPERIMENT_CHRONOLOGY')
  if r['changes_trade_path'] and r['counterfactual_basis']=='SIZE_ONLY_BASELINE_R':out.append('WRONG_COUNTERFACTUAL_BASIS')
  if r['reality']=='SYNTHETIC' and r['result_label']!='SIMULATED_COUNTERFACTUAL':out.append('SIMULATED_AS_OBSERVED')
 if name=='ResearchCapabilityReadModel':
  f=r['funnel_counts']
  if f['discovered']!=sum(f[k] for k in ['rejected','unknown','research_eligible']):out.append('FUNNEL_MISMATCH')
  if r['provider_state']=='CONTRACT_FIXTURE' and (r['engineering_state']=='E2E_VERIFIED' or r['actual_runtime_receipt_ref'] is not None or r['source_reality_label']!='SYNTHETIC'):out.append('FIXTURE_AS_RUNTIME')
 return out

def mutation_cases():
 C=[]
 def add(n,t,k,v,code):C.append((n,t,lambda r,k=k,v=v:r.__setitem__(k,v),code))
 for n in NAMES:
  add(n,'future:'+n,'available_at','2026-10-17T10:02:00Z','FUTURE_AVAILABILITY')
  add(n,'authority:'+n,'trade_authorized',True,'SCHEMA:')
  add(n,'grade:'+n,'implementation_evidence_level','E5_DEVICE_CERTIFIED','FIXTURE_AS_QUALIFICATION')
 add('ChainAssetIdentity','asset-binding','asset_id','other','IDENTITY_BINDING')
 add('ChainAssetIdentity','evm-length','canonical_token_address','0x123','EVM_ENCODING')
 add('ChainSourceObservation','clock-order','source_published_at','2026-10-17T10:00:10Z','SOURCE_CLOCK_ORDER')
 add('ChainSourceObservation','provider-receipt','actual_provider_receipt_ref','invented-runtime','FAKE_PROVIDER_RECEIPT')
 add('ChainSourceObservation','procurement','new_purchase_required',True,'SCHEMA:')
 add('DiscoveryCohortEvent','later-discovery','first_seen_at','2026-10-17T10:03:00Z','DISCOVERY_AFTER_DECISION')
 add('ChainSecurityFinding','string-boolean','mint_authority','no','SCHEMA:')
 add('ChainSecurityFinding','unsafe-clear','verdict','NO_HARD_BLOCK','UNSUPPORTED_AS_CLEAR')
 add('ChainSecurityFinding','safe-to-buy','verdict','SAFE_TO_BUY','SCHEMA:')
 add('WalletAttributionSnapshot','one-snapshot-growth','growth_claim','increasing','GROWTH_FROM_ONE_SNAPSHOT')
 add('WalletAttributionSnapshot','adjusted-larger','adjusted_holdings_total','1001','ADJUSTMENT_INCREASES_HOLDINGS')
 add('SellabilitySimulation','sell-guarantee','future_sell_guaranteed',True,'SCHEMA:')
 add('SellabilitySimulation','chain-signing','submitted_transaction',True,'SCHEMA:')
 add('ExecutableQuoteFacts','probability-in-facts','p_fill_estimate',0.8,'SCHEMA:')
 add('ExecutionEconomicsForecast','expired-calibration','calibration_state','EXPIRED','FORECAST_UNQUALIFIED_FOR_ECONOMIC_USE')
 add('ExecutionEconomicsForecast','nonfinite','p_fill',float('nan'),'NONFINITE_PROBABILITY')
 add('ExecutionEconomicsForecast','double-charge','included_in_exit_proceeds',['exit_gas'],'DOUBLE_COUNTED_COST')
 add('NetEdgeAssessment','wrong-ev','net_ev','10','NET_EV_IDENTITY')
 add('NetEdgeAssessment','fake-economic','economic_state','ELIGIBLE_FOR_SCOPED_REVIEW','FIXTURE_AS_ECONOMIC_ADMISSION')
 add('MatchedOpportunityExperiment','survivors-only','included_count',40,'SURVIVOR_COHORT')
 add('MatchedOpportunityExperiment','future-outcome','outcome_available_at','2026-10-17T09:00:00Z','EXPERIMENT_CHRONOLOGY')
 add('MatchedOpportunityExperiment','wrong-r','counterfactual_basis','SIZE_ONLY_BASELINE_R','WRONG_COUNTERFACTUAL_BASIS')
 add('MatchedOpportunityExperiment','fake-realized','result_label','REALIZED_VENUE_OBSERVED','SIMULATED_AS_OBSERVED')
 add('MatchedOpportunityExperiment','independent-row-bootstrap','resampling_unit','INDEPENDENT_ROWS','SCHEMA:')
 add('TypedTradingJudgment','new-jev','service_owner','new-jev-trader','SCHEMA:')
 add('TypedTradingJudgment','confidence-is-win','confidence_semantics','PROFIT_PROBABILITY','SCHEMA:')
 add('TypedTradingJudgment','override-hardgate','hard_filter_override',True,'SCHEMA:')
 add('TypedTradingJudgment','exit-veto','mandatory_exit_veto',True,'SCHEMA:')
 add('ResearchCapabilityReadModel','early-ui','new_frontend_gate','M2','SCHEMA:')
 add('ResearchCapabilityReadModel','fake-runtime','engineering_state','E2E_VERIFIED','FIXTURE_AS_RUNTIME')
 add('ResearchCapabilityReadModel','false-funnel','funnel_counts',{'discovered':100,'rejected':0,'unknown':0,'research_eligible':1},'FUNNEL_MISMATCH')
 return C

def run(root=ROOT,selftest=False):
 p=root/'contracts/high_value';schemas={n:json.loads((p/(n+'.schema.json')).read_text()) for n in NAMES};examples={n:json.loads((p/'examples'/(n+'.fixture.json')).read_text()) for n in NAMES}
 for s in schemas.values():Draft202012Validator.check_schema(s)
 findings={n:e for n in NAMES if (e:=check(n,examples[n],schemas))}
 out={'scope':'Local or VM document-schema and synthetic-fixture tests only, not VAN application tests or provider verification','schema_count':len(schemas),'fixture_count':len(examples),'findings':findings}
 if selftest:
  cases=[]
  for n,title,fn,code in mutation_cases():
   r=copy.deepcopy(examples[n]);before=json.dumps(r,sort_keys=True);fn(r)
   if before==json.dumps(r,sort_keys=True):raise ValueError('NOOP_MUTATION:'+title)
   errs=check(n,r,schemas);caught=any(e.startswith(code) for e in errs)
   cases.append({'case':title,'expected':code,'caught':caught,'observed':errs})
  out['negative_cases']=cases
  out['negative_cases_caught']=sum(x['caught'] for x in cases)
 return out
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--selftest',action='store_true');p.add_argument('--root',type=Path,default=ROOT);a=p.parse_args();o=run(a.root,a.selftest);print(json.dumps(o,indent=2,allow_nan=False));sys.exit(bool(o['findings']) or any(not x['caught'] for x in o.get('negative_cases',[])))
