"""Document/fixture checks only, NOT the VAN production semantic validator.

The constants and synthetic references are not permission, calibration, actual
provider facts or execution evidence. No network, model fitting or trading occurs.
"""
from __future__ import annotations
import copy
import datetime as dt
import math
from decimal import Decimal
from typing import Any
from jsonschema import Draft202012Validator, FormatChecker


def timestamp(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace('Z', '+00:00'))


def finite(value: Any) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(finite(x) for x in value.values())
    if isinstance(value, list):
        return all(finite(x) for x in value)
    return True


def fixture_errors(kind: str, obj: dict, schema: dict) -> list[str]:
    errors = [f'schema: {x.message}' for x in Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(obj)]
    if errors:
        return errors
    if not finite(obj):
        return ['nonfinite number']
    if obj['environment'] != 'FIXTURE':
        errors.append('portable synthetic example must remain FIXTURE')
    if not obj['record_id'].startswith('fixture:') or not all(x.startswith('fixture:') for x in obj['evidence_refs']):
        errors.append('synthetic example provenance may not claim real evidence')
    D=Decimal
    if kind == 'PredictionMarketSourceProfile':
        if obj['acquisition_mode'] != 'FIXTURE_REPLAY' and (obj['permission_state']!='ESTABLISHED_FOR_EXACT_USE' or not obj['permission_ref']):
            errors.append('nonfixture source route lacks even required use metadata')
        if obj['operator_eligibility']!='NOT_ASSERTED':
            errors.append('this fixture contains no verified operator eligibility')
        if obj['acquisition_mode']=='FIXTURE_REPLAY' and obj['permission_state']!='FIXTURE_ONLY':
            errors.append('fixture source cannot assert external use permission')
    elif kind == 'PredictionMarketContract':
        if timestamp(obj['observation_start'])>timestamp(obj['observation_end']):
            errors.append('reversed observation interval')
        lo,hi=obj['lower_bound'],obj['upper_bound']
        if obj['comparator']=='RANGE' and (lo is None or hi is None or D(lo)>=D(hi)):
            errors.append('invalid or absent interval bounds')
        if obj['comparator'] in ('GT','GTE') and lo is None:
            errors.append('lower threshold absent')
        if obj['comparator'] in ('LT','LTE') and hi is None:
            errors.append('upper threshold absent')
        if D(obj['success_payout_per_contract'])<=0:
            errors.append('nonpositive payout')
        if obj['equivalence_state'] in ('EXACT_REVIEWED','COMPLEMENT_REVIEWED') and not obj['review_ref']:
            errors.append('equivalence lacks required review reference; actual truth remains unchecked')
    elif kind == 'PredictionMarketObservation':
        if not timestamp(obj['received_at'])<=timestamp(obj['available_at'])<=timestamp(obj['decision_cutoff']):
            errors.append('receipt/availability/decision order invalid')
        # Provider clocks can skew in reality; this exact clean fixture has ordered clocks.
        if obj['provider_event_at'] and timestamp(obj['provider_event_at'])>timestamp(obj['received_at']):
            errors.append('provider clock ahead of receipt needs skew state, absent in this clean fixture')
        if obj['book_state']=='VALID' and obj['gap_count']>0:
            errors.append('gapped book incorrectly marked valid')
        if obj['book_state']!='VALID' and (obj['derived_yes_ask'] is not None or obj['derived_no_ask'] is not None):
            errors.append('invalid book exposes usable current asks')
        for side in ('yes_bids','no_bids'):
            prices=[D(x['price']) for x in obj[side]]
            if prices!=sorted(set(prices)):
                errors.append('normalized price levels not strictly ascending')
            if any(p<0 or p>1 for p in prices) or any(D(x['quantity'])<=0 for x in obj[side]):
                errors.append('price/quantity outside normalized binary domain')
        for side,ask in [('no_bids','derived_yes_ask'),('yes_bids','derived_no_ask')]:
            expected=D(1)-max(D(x['price']) for x in obj[side]) if obj[side] and obj['book_state']=='VALID' else None
            actual=None if obj[ask] is None else D(obj[ask])
            if actual!=expected:
                errors.append('complementary ask does not match opposite side or missing-book state')
        if obj['yes_bids'] and obj['no_bids'] and obj['book_state']=='VALID':
            if max(D(x['price']) for x in obj['yes_bids'])+max(D(x['price']) for x in obj['no_bids'])>1:
                errors.append('crossed binary book marked valid')
        if obj['input_mode']!='FIXTURE_REPLAY' and not obj['permission_ref']:
            errors.append('nonfixture observation lacks use metadata')
    elif kind == 'EventProbabilitySnapshot':
        if obj['armed_eligible']:
            errors.append('portable synthetic fixture has no actual armed eligibility evidence')
        if obj['armed_eligible'] and not obj['armed_eligibility_evidence_ref']:
            errors.append('armed eligibility metadata missing evidence reference; authority still separate')
        if timestamp(obj['max_input_available_at'])>timestamp(obj['as_of']):
            errors.append('future-available event information')
        # This supplied example is explicitly a frozen pre-release expectation.
        if timestamp(obj['as_of'])>=timestamp(obj['scheduled_release_at']):
            errors.append('pre-release fixture frozen at or after release')
        raw=obj['raw_probabilities']; calibrated=obj['calibrated_probabilities']
        if len({x['outcome'] for x in raw})!=len(raw):
            errors.append('duplicate probability outcome')
        if obj['distribution_representation']=='EXCLUSIVE_EXHAUSTIVE_BINS' and abs(sum(x['probability'] for x in raw)-1)>1e-9:
            errors.append('exhaustive bins not normalized')
        th=obj['thresholds']; thresholds=[x['threshold'] for x in th]; survival=[x['survival_probability'] for x in th]
        if thresholds!=sorted(set(thresholds)) or survival!=sorted(survival,reverse=True):
            errors.append('threshold/survival ordering invalid')
        if obj['estimate_kind']=='CALIBRATED_EVENT_PROBABILITY' and (not calibrated or not obj['calibrator_ref'] or obj['event_count']<=0):
            errors.append('calibrated probability lacks metadata/sample evidence')
        if calibrated:
            if not obj['calibrator_ref'] or obj['event_count']<=0:
                errors.append('calibrated payload without calibrator/event count')
            if [x['outcome'] for x in calibrated]!=[x['outcome'] for x in raw]:
                errors.append('calibrated outcome identities differ')
            if obj['distribution_representation']=='EXCLUSIVE_EXHAUSTIVE_BINS' and abs(sum(x['probability'] for x in calibrated)-1)>1e-9:
                errors.append('calibrated exhaustive bins not normalized')
        if obj['source_count']!=len(obj['source_names']) or len(obj['source_names'])!=len(set(obj['source_names'])) or len(obj['source_event_ids'])!=obj['source_count']:
            errors.append('source cardinality/duplicate identity mismatch')
        if obj['agreement_state']=='MATCHED_TWO_SOURCES':
            if not {'KALSHI','POLYMARKET'}.issubset(set(obj['source_names'])) or any(x!=obj['canonical_event_id'] for x in obj['source_event_ids']):
                errors.append('claimed agreement does not match two required source/event identities')
        if obj['origin_event_id_for_change']!=obj['canonical_event_id']:
            errors.append('probability change splices different events')
    elif kind == 'EventAssetResponse':
        cutoff=timestamp(obj['prediction_cutoff'])
        if timestamp(obj['fit_cutoff'])>cutoff or timestamp(obj['max_input_available_at'])>cutoff:
            errors.append('response fit/input is in the future')
        if obj['output_task']=='TRADE_EVENT_PROBABILITY':
            if not 0<=obj['output_value']<=1 or not obj['calibrator_ref']:
                errors.append('asset event probability lacks calibration/domain')
        if obj['output_task']=='REALIZED_VOLATILITY' and obj['output_value']<0:
            errors.append('negative raw volatility')
    elif kind == 'EventPositionProposal':
        if not 0<=D(obj['news_multiplier'])<=1:
            errors.append('news multiplier increases risk or is negative')
        if not 0<=D(obj['risk_request_fraction'])<=1:
            errors.append('research request fraction outside range')
        if obj['use_scope']=='BINARY_CONTRACT_RESEARCH' and obj['valuation_basis']=='SETTLEMENT':
            n=D(obj['analysis_contract_count']);p=D(str(obj['analysis_success_probability']))
            if n<=0:
                errors.append('nonpositive analysis contract count')
            costs=sum(D(obj[k]) for k in ['entry_cost_total','fees_total','other_costs_total'])
            if any(D(obj[k])<0 for k in ['entry_cost_total','fees_total','other_costs_total']):
                errors.append('negative cost in no-rebate fixture')
            if D(obj['expected_payout_total'])!=n*p:
                errors.append('synthetic $1 expected payout arithmetic mismatch')
            if D(obj['expected_net_value'])!=D(obj['expected_payout_total'])-costs:
                errors.append('expected net value/cost arithmetic mismatch')
            if D(obj['maximum_loss_bound'])<costs:
                errors.append('full paid-outlay loss understated')
        if obj['use_scope']=='EXTERNAL_ASSET_RESEARCH' and obj['valuation_basis']!='EXTERNAL_ASSET_RESPONSE':
            errors.append('external response confused with binary settlement')
    elif kind == 'PredictionMarketStudySpec':
        if obj['result']!='NOT_RUN':
            errors.append('synthetic protocol cannot claim a performed economic result')
        if len(obj['baseline_policies'])!=len(set(obj['baseline_policies'])):
            errors.append('duplicated comparators')
    elif kind == 'EventExecutionScenario':
        expected=D(obj['cash_before'])-D(obj['entry_cost'])-D(obj['fees'])-D(obj['other_cash_costs'])+D(obj['final_payout'])
        if D(obj['cash_after'])!=expected:
            errors.append('cash reconciliation mismatch')
        if not timestamp(obj['trade_close_at'])<=timestamp(obj['settled_at'])<=timestamp(obj['cash_available_at']):
            errors.append('fixture settlement/cash availability chronology mismatch')
        if obj['source_evidence_claim']!='FIXTURE_ONLY' or obj['input_granularity']!='FIXTURE':
            errors.append('synthetic execution cannot assert real capture granularity')
    elif kind == 'ArbitrageCandidate':
        states=obj['payoff_states'];cost=D(obj['purchase_cost'])+D(obj['fees_and_costs'])
        minimum=min(D(x['portfolio_payout'])-cost for x in states)
        if D(obj['min_conditional_net_payoff'])!=minimum:
            errors.append('minimum conditional payoff calculation incorrect')
        if len({x['state'] for x in states})!=len(states):
            errors.append('duplicate payoff states')
        if minimum<0:
            errors.append('synthetic positive hedge example contains a losing state')
    elif kind == 'MarketMakingPolicy':
        if D(obj['inventory_limit_contracts'])<=0 or D(obj['max_gross_outlay'])<=0:
            errors.append('quote policy lacks positive bounded limits')
    else:
        errors.append('unknown fixture kind')
    return errors


def mutation_checks(fixtures: dict, schemas: dict) -> list[dict]:
    results=[]
    def mutate(name,kind,change):
        value=copy.deepcopy(fixtures[kind]);change(value)
        errors=fixture_errors(kind,value,schemas[kind])
        results.append({'name':name,'result':'DETECTED' if errors else 'MISSED','finding_count':len(errors),'boundary':'DOCUMENT_FIXTURE_ONLY'})
    mutate('PM procurement introduced as requirement','PredictionMarketSourceProfile',lambda x:x.update(licence_procurement_required=True))
    mutate('PM purchase authorized','PredictionMarketSourceProfile',lambda x:x.update(new_purchase_budget_usd='29.00'))
    mutate('PM host inferred as operator eligibility','PredictionMarketSourceProfile',lambda x:x.update(eligibility_inferred_from_host=True))
    mutate('PM fixture relabelled authorized capture','PredictionMarketSourceProfile',lambda x:x.update(acquisition_mode='AUTHORIZED_READ_ONLY_CAPTURE'))
    mutate('PM threshold absent','PredictionMarketContract',lambda x:x.update(lower_bound=None))
    mutate('PM reviewless exact equivalence','PredictionMarketContract',lambda x:x.update(review_ref=None))
    mutate('PM missing opposite bid replaced with ask','PredictionMarketObservation',lambda x:x.update(no_bids=[]))
    mutate('PM wrong complementary ask','PredictionMarketObservation',lambda x:x.update(derived_yes_ask='0.6000'))
    mutate('PM sequence gap marked healthy','PredictionMarketObservation',lambda x:x.update(gap_count=1))
    mutate('PM observation available after decision','PredictionMarketObservation',lambda x:x.update(available_at='2026-10-17T11:01:00Z'))
    mutate('PM negative book quantity','PredictionMarketObservation',lambda x:x['yes_bids'][0].update(quantity='-1.00'))
    mutate('PM threshold survival increases','EventProbabilitySnapshot',lambda x:x['thresholds'][1].update(survival_probability=.9))
    mutate('PM exclusive bins do not sum to one','EventProbabilitySnapshot',lambda x:x['raw_probabilities'][0].update(probability=.5))
    mutate('PM calibrated probability has no calibration','EventProbabilitySnapshot',lambda x:x.update(estimate_kind='CALIBRATED_EVENT_PROBABILITY'))
    mutate('PM outcome known before expectation frozen','EventProbabilitySnapshot',lambda x:x.update(as_of='2026-10-17T14:31:00Z'))
    mutate('PM probability change hides contract roll','EventProbabilitySnapshot',lambda x:x.update(origin_event_id_for_change='fixture:CPI-other-month'))
    mutate('PM two-source claim hides duplicate','EventProbabilitySnapshot',lambda x:x.update(source_names=['KALSHI','KALSHI']))
    mutate('PM two-source claim mismatches event','EventProbabilitySnapshot',lambda x:x['source_event_ids'].__setitem__(1,'fixture:OTHER_EVENT'))
    mutate('PM agreement treated as independence','EventProbabilitySnapshot',lambda x:x.update(agreement_proves_independence=True))
    mutate('PM fixture turns on armed eligibility','EventProbabilitySnapshot',lambda x:x.update(armed_eligible=True))
    mutate('PM event probability copied as trade-win probability','EventAssetResponse',lambda x:x.update(event_probability_copied_as_asset_probability=True))
    mutate('PM response trained in the future','EventAssetResponse',lambda x:x.update(fit_cutoff='2026-10-18T00:00:00Z'))
    mutate('PM asset probability lacks calibrator','EventAssetResponse',lambda x:x.update(output_task='TRADE_EVENT_PROBABILITY',output_value=.6))
    mutate('PM news proposal expands risk','EventPositionProposal',lambda x:x.update(news_path='D1',news_multiplier='1.20'))
    mutate('PM binary EV omits costs','EventPositionProposal',lambda x:x.update(expected_net_value='5.00'))
    mutate('PM binary maximum loss understated','EventPositionProposal',lambda x:x.update(maximum_loss_bound='1.00'))
    mutate('PM proposal enables live','EventPositionProposal',lambda x:x.update(live_enabled=True))
    mutate('PM study splits individual quotes','PredictionMarketStudySpec',lambda x:x.update(group_split_key='RANDOM_QUOTES'))
    mutate('PM study drops exposure-matched control','PredictionMarketStudySpec',lambda x:x.update(exposure_matched_control=False))
    mutate('PM study claims unrun economic success','PredictionMarketStudySpec',lambda x:x.update(result='QUALIFIED'))
    mutate('PM cash ignores fee debit','EventExecutionScenario',lambda x:x.update(cash_after='1040.00'))
    mutate('PM settlement cash released early','EventExecutionScenario',lambda x:x.update(cash_available_at='2026-10-17T14:30:00Z'))
    mutate('PM price touch guarantees fill','EventExecutionScenario',lambda x:x.update(touch_guarantees_fill=True))
    mutate('PM arbitrage has hidden losing state','ArbitrageCandidate',lambda x:x['payoff_states'].append({'state':'VOID_MISMATCH','portfolio_payout':'0.20'}))
    mutate('PM cross-venue legs assumed atomic','ArbitrageCandidate',lambda x:x.update(atomic_execution_assumed=True))
    mutate('PM quote cancel releases exposure before confirmation','MarketMakingPolicy',lambda x:x.update(pending_cancel_reservations_retained=False))
    mutate('PM maker assumes privileges','MarketMakingPolicy',lambda x:x.update(special_venue_privileges_assumed=True))
    mutate('PM maker allows live order submission','MarketMakingPolicy',lambda x:x.update(live_order_submission=True))
    return results
