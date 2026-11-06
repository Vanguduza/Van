"""Build strict illustrative contracts and synthetic examples; no provider implementation."""
from copy import deepcopy

S={'type':'string','minLength':1}
HASH={'type':'string','pattern':'^[a-f0-9]{64}$'}
DEC={'type':'string','pattern':r'^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$'}
POS={'type':'string','pattern':r'^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$'}
TS={'type':'string','format':'date-time'}
def enum(*v):return {'enum':list(v)}
def array(item=S,minimum=1):return {'type':'array','items':item,'minItems':minimum,'uniqueItems':True}
def obj(props,required=None):return {'type':'object','properties':props,'required':list(props) if required is None else required,'additionalProperties':False}
ANCHOR=obj({'chain_id':S,'height':{'type':'integer','minimum':0},'hash':S,'finality':enum('FINALIZED','CONFIRMED','UNFINALIZED','UNKNOWN'),'state_epoch':{'type':'integer','minimum':0}})
COMMON={
 'schema_version':{'const':'1.0'},'record_id':S,
 'reality':enum('SYNTHETIC','OBSERVED','MODELED','DERIVED'),
 'research_source_class':enum('RS1_PRIMARY','RS2_REPEATABLE_RESEARCH','RS3_VENDOR_CAPABILITY','RS4_SELF_REPORTED','RS5_UNVERIFIED_CREATOR','SYNTHETIC','NOT_APPLICABLE'),
 'implementation_evidence_level':enum('SPEC_ONLY','E0_OWNER_REFERENCE','E1_DOCUMENTED','E2_SOURCE_STATIC','E3_TEST_RECEIPT','E4_RUNTIME_OBSERVED','E5_DEVICE_CERTIFIED','E6_OWNER_VISUALLY_ACCEPTED'),
 'available_at':TS,'decision_cutoff':TS,'expires_at':TS,'source_refs':array(),
 'trade_authorized':{'const':False}
}
P={
'ChainAssetIdentity':{
 'chain_family':enum('EVM','SOLANA'),'chain_id':S,'raw_token_address':S,'canonical_token_address':S,'address_codec_version':S,'asset_id':S,'ticker':S,'pool_ids':array(S,0)},
'ChainSourceObservation':{
 'provider':S,'endpoint_capability':enum('DISCOVER','READ_STATE','READ_HISTORY','READ_QUOTE','SIMULATE_READ_ONLY'),'entitlement_state':enum('PERMITTED_EXISTING_ACCESS','UNVERIFIED','DENIED','EXPIRED'),
 'observed_at':TS,'source_published_at':TS,'payload_sha256':HASH,'cursor':S,'state_anchor':ANCHOR,'actual_provider_receipt_ref':{'type':['string','null']},'new_purchase_required':{'const':False}},
'DiscoveryCohortEvent':{
 'cohort_id':S,'asset_id':S,'pool_id':S,'discovery_event_id':S,'first_seen_at':TS,'decision_at':TS,
 'screening_version':S,'status':enum('DISCOVERED','REJECTED','UNKNOWN','INVESTIGATE','ELIGIBLE_FOR_RESEARCH','MIGRATED','DELISTED','EXPIRED','UNREACHABLE'),
 'reason_codes':array(),'state_anchor':ANCHOR,'outcome_state':enum('NOT_MATURED','OBSERVED','CENSORED','MISSING'),'source_cursor':S},
'ChainSecurityFinding':{
 'asset_id':S,'chain_family':enum('EVM','SOLANA'),'analyzer_version':S,'state_anchor':ANCHOR,
 'mint_authority':enum('YES','NO','UNKNOWN'),'freeze_authority':enum('YES','NO','UNKNOWN'),'upgrade_authority':enum('YES','NO','UNKNOWN'),
 'unsupported_capabilities':array(S,0),'factual_restrictions':array(S,0),'verdict':enum('REJECT','INVESTIGATE','NO_HARD_BLOCK'),'reason_codes':array(),
 'permission_to_buy':{'const':False}},
'WalletAttributionSnapshot':{
 'asset_id':S,'state_anchor':ANCHOR,'previous_snapshot_ref':{'type':['string','null']},'lookback_complete':{'type':'boolean'},
 'raw_holdings_total':POS,'adjusted_holdings_total':POS,'quantity_unit':S,'technical_exclusions':array(S,0),
 'attribution_version':S,'ownership_confidence':enum('SUPPORTED','HEURISTIC','UNKNOWN'),
 'flow_classification':enum('OBSERVED_SWAP','TRANSFER_ONLY','ROUTER_HOP','UNKNOWN'),'growth_claim':{'type':['string','null']}},
'SellabilitySimulation':{
 'asset_id':S,'pool_id':S,'router_id':S,'state_anchor':ANCHOR,'buy_result':enum('PASS','REVERT','UNKNOWN','UNSUPPORTED'),'sell_result':enum('PASS','REVERT','UNKNOWN','UNSUPPORTED'),
 'quantity':POS,'quantity_unit':S,'caller_context_hash':HASH,'simulation_engine_version':S,
 'assumptions':array(),'future_sell_guaranteed':{'const':False},'submitted_transaction':{'const':False}},
'ExecutableQuoteFacts':{
 'quote_id':S,'asset_id':S,'venue':S,'pool_id':S,'router_id':S,'state_anchor':ANCHOR,
 'side':enum('BUY','SELL'),'quantity':POS,'quantity_unit':S,'cash_currency':S,'observed_cash_amount':POS,'price_convention':enum('TOTAL_CASH_FOR_REQUESTED_SIZE'),
 'included_cost_components':array(S,0),'quote_status':enum('CURRENT','STALE','UNAVAILABLE'),'payload_sha256':HASH},
'ExecutionEconomicsForecast':{
 'quote_ref':S,'asset_id':S,'side':enum('BUY','SELL'),'quantity':POS,'quantity_unit':S,'cash_currency':S,
 'target_id':S,'horizon_seconds':{'type':'integer','minimum':1},'model_hash':HASH,'feature_hash':HASH,'calibration_id':S,
 'calibration_state':enum('VALID','EXPIRED','UNQUALIFIED'),'applicability':enum('IN_DOMAIN','UNKNOWN','OUT_OF_DOMAIN'),
 'p_fill':{'type':'number','minimum':0,'maximum':1},'expected_exit_proceeds':DEC,
 'incremental_costs':array(obj({'component':S,'cash_amount':DEC}),0),'included_in_exit_proceeds':array(S,0),'failure_cost':POS},
'NetEdgeAssessment':{
 'quote_ref':S,'forecast_ref':S,'asset_id':S,'quantity':POS,'quantity_unit':S,'cash_currency':S,
 'entry_cash_cost':DEC,'expected_exit_proceeds':DEC,'incremental_exit_costs':DEC,'failure_cost':DEC,'net_ev':DEC,
 'economic_materiality_floor':DEC,'economic_state':enum('RESEARCH_ONLY','INCONCLUSIVE','REJECTED','ELIGIBLE_FOR_SCOPED_REVIEW'),
 'existing_risk_authority_ref':{'type':['string','null']},'own_sizing_permission':{'const':False}},
'MatchedOpportunityExperiment':{
 'experiment_id':S,'hypothesis_id':S,'cohort_manifest_hash':HASH,'sealed_at':TS,'decision_at':TS,'outcome_available_at':TS,
 'control_policy_hash':HASH,'challenger_policy_hash':HASH,'fill_model_hash':HASH,'validation_policy_id':S,
 'discovered_count':{'type':'integer','minimum':1},'included_count':{'type':'integer','minimum':1},'rejected_count':{'type':'integer','minimum':0},'missing_count':{'type':'integer','minimum':0},
 'result_label':enum('SIMULATED_COUNTERFACTUAL','FORWARD_PAPER_OBSERVED','REALIZED_VENUE_OBSERVED','INCONCLUSIVE'),
 'independent_cash_replay':{'const':True},'counterfactual_basis':enum('WHOLE_POLICY','SIZE_ONLY_BASELINE_R'),
 'changes_trade_path':{'type':'boolean'},'resampling_unit':enum('EVENT_TIME_ASSET_CLUSTER'),'automatic_promotion':{'const':False}},
'TypedTradingJudgment':{
 'service_owner':{'const':'dial-jev'},'question_set_id':S,'question_set_version':S,'input_snapshot_hash':HASH,'model_id':S,
 'answers':array(obj({'question_id':S,'answer':enum('YES','NO','UNKNOWN'),'answer_quality':{'type':'number','minimum':0,'maximum':1}})),
 'use':enum('EXPLANATION','RESEARCH','ABSTENTION','SCOPED_REDUCE_ONLY_REVIEW'),
 'confidence_semantics':{'const':'ANSWER_QUALITY_NOT_TRADE_PROBABILITY'},'hard_filter_override':{'const':False},'mandatory_exit_veto':{'const':False}},
'ResearchCapabilityReadModel':{
 'capability_id':S,'engineering_state':enum('NOT_STARTED','IMPLEMENTED','INTEGRATION_UNVERIFIED','E2E_VERIFIED'),
 'provider_state':enum('UNAVAILABLE','CONTRACT_FIXTURE','OBSERVED','QUALIFIED','REVOKED'),
 'economic_state':enum('NOT_EVALUATED','INCONCLUSIVE','REJECTED','DEFENSIVE_ONLY','QUALIFIED_SCOPED'),
 'financial_authority_state':{'const':'NONE_GRANTED_BY_ADDITIVE'},
 'source_reality_label':enum('SYNTHETIC','DELAYED','OBSERVED','UNVERIFIED'),
 'funnel_counts':obj({'discovered':{'type':'integer','minimum':0},'rejected':{'type':'integer','minimum':0},'unknown':{'type':'integer','minimum':0},'research_eligible':{'type':'integer','minimum':0}}),
 'actual_runtime_receipt_ref':{'type':['string','null']},'new_frontend_gate':{'const':'BG-001'},'completion_by_fixture':{'const':False}}
}
def schema(name):
 d=obj({**deepcopy(COMMON),**deepcopy(P[name])});d.update({'$schema':'https://json-schema.org/draft/2020-12/schema','$id':f'urn:van:hva:{name}:1.0','title':name,'description':'Proposed Rev1.12 application contract. Examples and schema checks are documentary only; no implementation/permission implied.'});return d
A='eip155:8453:0x'+'11'*20
ANCH={'chain_id':'eip155:8453','height':100,'hash':'synthetic-block-100','finality':'FINALIZED','state_epoch':1}
B={'schema_version':'1.0','record_id':'synthetic-record','reality':'SYNTHETIC','research_source_class':'SYNTHETIC','implementation_evidence_level':'SPEC_ONLY','available_at':'2026-10-17T10:00:00Z','decision_cutoff':'2026-10-17T10:01:00Z','expires_at':'2026-10-17T10:05:00Z','source_refs':['fixture:controlled-input-only'],'trade_authorized':False}
H='a'*64
EX={
'ChainAssetIdentity':dict(chain_family='EVM',chain_id='eip155:8453',raw_token_address='0x'+'11'*20,canonical_token_address='0x'+'11'*20,address_codec_version='fixture-evm/1',asset_id=A,ticker='EXAMPLE',pool_ids=['fixture:pool:1']),
'ChainSourceObservation':dict(provider='SYNTHETIC_PROVIDER',endpoint_capability='READ_STATE',entitlement_state='UNVERIFIED',observed_at='2026-10-17T09:59:50Z',source_published_at='2026-10-17T09:59:40Z',payload_sha256=H,cursor='fixture:cursor:1',state_anchor=ANCH,actual_provider_receipt_ref=None,new_purchase_required=False),
'DiscoveryCohortEvent':dict(cohort_id='fixture:cohort:1',asset_id=A,pool_id='fixture:pool:1',discovery_event_id='fixture:discovery:1',first_seen_at='2026-10-17T09:58:00Z',decision_at='2026-10-17T10:01:00Z',screening_version='fixture-screen/1',status='UNKNOWN',reason_codes=['INSUFFICIENT_HISTORY'],state_anchor=ANCH,outcome_state='NOT_MATURED',source_cursor='fixture:cursor:1'),
'ChainSecurityFinding':dict(asset_id=A,chain_family='EVM',analyzer_version='fixture-evm/1',state_anchor=ANCH,mint_authority='UNKNOWN',freeze_authority='UNKNOWN',upgrade_authority='UNKNOWN',unsupported_capabilities=['INSUFFICIENT_STATE'],factual_restrictions=[],verdict='INVESTIGATE',reason_codes=['UNKNOWN_CAPABILITIES'],permission_to_buy=False),
'WalletAttributionSnapshot':dict(asset_id=A,state_anchor=ANCH,previous_snapshot_ref=None,lookback_complete=False,raw_holdings_total='1000',adjusted_holdings_total='600',quantity_unit='TOKEN_BASE_UNITS',technical_exclusions=['fixture:pool:1'],attribution_version='fixture-attribution/1',ownership_confidence='UNKNOWN',flow_classification='TRANSFER_ONLY',growth_claim=None),
'SellabilitySimulation':dict(asset_id=A,pool_id='fixture:pool:1',router_id='fixture:router:1',state_anchor=ANCH,buy_result='PASS',sell_result='UNKNOWN',quantity='10',quantity_unit='TOKEN_BASE_UNITS',caller_context_hash=H,simulation_engine_version='fixture-sim/1',assumptions=['Synthetic result; not a chain RPC call.'],future_sell_guaranteed=False,submitted_transaction=False),
'ExecutableQuoteFacts':dict(quote_id='fixture:quote:1',asset_id=A,venue='SYNTHETIC_DEX',pool_id='fixture:pool:1',router_id='fixture:router:1',state_anchor=ANCH,side='BUY',quantity='10',quantity_unit='TOKEN_BASE_UNITS',cash_currency='USD',observed_cash_amount='100',price_convention='TOTAL_CASH_FOR_REQUESTED_SIZE',included_cost_components=['entry_spread','entry_impact'],quote_status='CURRENT',payload_sha256=H),
'ExecutionEconomicsForecast':dict(quote_ref='fixture:quote:1',asset_id=A,side='BUY',quantity='10',quantity_unit='TOKEN_BASE_UNITS',cash_currency='USD',target_id='fixture:executable-exit/1',horizon_seconds=3600,model_hash=H,feature_hash=H,calibration_id='fixture:calibration:1',calibration_state='VALID',applicability='IN_DOMAIN',p_fill=0.7,expected_exit_proceeds='112',incremental_costs=[{'component':'exit_gas','cash_amount':'2'}],included_in_exit_proceeds=['exit_spread','exit_impact'],failure_cost='1'),
'NetEdgeAssessment':dict(quote_ref='fixture:quote:1',forecast_ref='fixture:ExecutionEconomicsForecast:1',asset_id=A,quantity='10',quantity_unit='TOKEN_BASE_UNITS',cash_currency='USD',entry_cash_cost='100',expected_exit_proceeds='112',incremental_exit_costs='2',failure_cost='1',net_ev='9',economic_materiality_floor='2',economic_state='RESEARCH_ONLY',existing_risk_authority_ref=None,own_sizing_permission=False),
'MatchedOpportunityExperiment':dict(experiment_id='fixture:experiment:1',hypothesis_id='fixture:hypothesis:1',cohort_manifest_hash=H,sealed_at='2026-10-17T09:59:00Z',decision_at='2026-10-17T10:01:00Z',outcome_available_at='2026-10-18T10:00:00Z',control_policy_hash=H,challenger_policy_hash='b'*64,fill_model_hash=H,validation_policy_id='fixture:validation:1',discovered_count=100,included_count=100,rejected_count=60,missing_count=5,result_label='SIMULATED_COUNTERFACTUAL',independent_cash_replay=True,counterfactual_basis='WHOLE_POLICY',changes_trade_path=True,resampling_unit='EVENT_TIME_ASSET_CLUSTER',automatic_promotion=False),
'TypedTradingJudgment':dict(service_owner='dial-jev',question_set_id='fixture:trading-evidence-questions',question_set_version='1',input_snapshot_hash=H,model_id='fixture:judge:1',answers=[{'question_id':'identity-supported','answer':'UNKNOWN','answer_quality':0.5}],use='RESEARCH',confidence_semantics='ANSWER_QUALITY_NOT_TRADE_PROBABILITY',hard_filter_override=False,mandatory_exit_veto=False),
'ResearchCapabilityReadModel':dict(capability_id='fixture:crypto-intelligence',engineering_state='NOT_STARTED',provider_state='CONTRACT_FIXTURE',economic_state='NOT_EVALUATED',financial_authority_state='NONE_GRANTED_BY_ADDITIVE',source_reality_label='SYNTHETIC',funnel_counts={'discovered':100,'rejected':60,'unknown':35,'research_eligible':5},actual_runtime_receipt_ref=None,new_frontend_gate='BG-001',completion_by_fixture=False)
}
def example(name):return {**deepcopy(B),'record_id':f'fixture:{name}:1',**deepcopy(EX[name])}
