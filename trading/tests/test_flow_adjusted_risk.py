"""Independent economic oracles for sampled returns and immutable loss history."""
from dataclasses import replace
from decimal import Decimal as D, localcontext, Inexact, Rounded
from fractions import Fraction

import pytest

from vati.core.canonical import canonical_hash
from vati.core.units import UnitError
from vati.funding.flow_risk import FlowAdjustedRisk, MAX_POINTS
from vati.funding.unitization import NetEquityPoint as V, FlowPoint as F, FlowKind as K, unitize

S=canonical_hash({'fixture_scope':'normalized-account-values'})
def value(at,equity,ref,order=None):return V(S,at,D(equity),canonical_hash(ref),order)
def flow(at,delta,after,ref,kind=K.EXTERNAL,order=None):return F(S,at,D(delta),None if after is None else D(after),kind,canonical_hash(ref),order)


def test_intermediate_loss_between_external_flows_cannot_disappear_from_drawdown():
    first=value(1000,'100','baseline');last=value(4000,'150','closing')
    flows=[flow(2000,'100','180','deposit'),flow(3000,'-90','180','withdrawal')]
    samples=[value(1500,'80','first-loss'),value(2250,'50','deep-loss'),value(2500,'270','recovery')]
    # Shares:100 ->225 afterdeposit ->150 afterwithdrawal. The intermediate
    # 50/225 NAV is2/9, so drawdown from NAV1 is7/9; closing NAV returns to1.
    original=unitize(first,last,flows)
    assert D(original['worst_observed_drawdown'])==D('.2')
    result=FlowAdjustedRisk(first,last,flows,samples=samples).body();calculation=result['calculation']
    assert result['state']=='MEASURED' and D(calculation['units'])==150
    assert D(calculation['flow_neutral_return'])==0 and D(calculation['external_net_flow'])==10
    assert D(calculation['net_account_pnl'])==40
    assert abs(Fraction(D(calculation['worst_observed_drawdown']))-Fraction(7,9))<Fraction(1,10**79)
    assert result['risk_capital_qualified'] is result['execution_authority'] is False
    assert result['native_source_qualification']==result['settlement_qualification']=='NOT_ISSUED'


def test_capital_redemption_and_replacement_preserve_the_prior_sampled_loss():
    first=value(1,'100','start');last=value(6,'50','end')
    result=FlowAdjustedRisk(first,last,[flow(3,'-80','0','redeem'),flow(5,'50','50','new-capital')],
        samples=[value(2,'80','loss'),value(4,'0','no-capital')]).body()['calculation']
    assert D(result['flow_neutral_return'])==D('-.2') and D(result['worst_observed_drawdown'])==D('.2')
    assert D(result['external_net_flow'])==-30 and D(result['net_account_pnl'])==-20


@pytest.mark.parametrize('kind,reason',[(K.EXTERNAL,'NATIVE_NET_FLOW_VALUATION_UNAVAILABLE'),(K.UNKNOWN,'UNCLASSIFIED_NATIVE_MOVEMENT')])
def test_unknown_native_history_preserves_known_prefix_without_zero_measurement(kind,reason):
    result=FlowAdjustedRisk(value(1,'100','start'),value(4,'180','end'),
        [flow(3,'100',None,'unqualified-native-flow',kind)],samples=[value(2,'80','loss')]).body()
    assert result['state']=='UNMEASURED' and result['reason']==reason
    calc=result['calculation'];assert calc['worst_observed_drawdown'] is calc['flow_neutral_return'] is None
    assert D(calc['known_prefix_drawdown'])==D('.2')


def test_account_fees_and_already_excluded_credit_do_not_issue_external_units():
    result=FlowAdjustedRisk(value(1,'100','start'),value(5,'98','end'),[
        flow(2,'100','100','excluded-credit',K.CREDIT_EXCLUDED),flow(4,'-2','98','fee',K.INTERNAL)],
        samples=[value(3,'90','intermediate-loss')]).body()['calculation']
    assert D(result['units'])==100 and D(result['external_net_flow'])==0
    assert D(result['flow_neutral_return'])==D('-.02') and D(result['worst_observed_drawdown'])==D('.1')


def test_equal_time_samples_need_native_order_and_never_sort_by_source_hash():
    first=value(1,'100','start');last=value(3,'110','end')
    samples=[value(2,'80','z-loss'),value(2,'120','a-peak')]
    assert FlowAdjustedRisk(first,last,samples=samples).body()['reason']=='NATIVE_FLOW_ORDER_UNAVAILABLE'
    samples=[replace(samples[0],native_order=1),replace(samples[1],native_order=2)]
    one=FlowAdjustedRisk(first,last,samples=samples).body()['calculation']
    two=FlowAdjustedRisk(first,last,samples=list(reversed(samples))).body()['calculation']
    assert one['worst_observed_drawdown']==two['worst_observed_drawdown']
    assert D(one['worst_observed_drawdown'])==D('.2')


@pytest.mark.parametrize('damage',['scope','reused-ref','float-time','bool-order','wrong-dimension','bad-ref','capacity'])
def test_wrong_scope_identity_dimensions_and_capacity_cannot_be_computed(damage):
    first=value(1,'100','start');last=value(3,'110','end');samples=[value(2,'90','sample')]
    if damage=='scope':samples=[replace(samples[0],scope_hash='f'*64)]
    elif damage=='reused-ref':samples=[replace(samples[0],source_ref=first.source_ref)]
    elif damage=='float-time':samples=[replace(samples[0],at_ms=2.0)]
    elif damage=='bool-order':samples=[replace(samples[0],native_order=True)]
    elif damage=='wrong-dimension':samples=[flow(2,'0','90','flow-not-valuation')]
    elif damage=='bad-ref':samples=[replace(samples[0],source_ref='alias-only')]
    else:samples=[value(2,'90','unique-capacity-sample-'+str(i),i) for i in range(MAX_POINTS+1)]
    with pytest.raises(UnitError,match='POINT_CAPACITY' if damage=='capacity' else None):
        FlowAdjustedRisk(first,last,samples=samples)


def test_exact_sampled_reports_are_immutable_and_independent_of_decimal_context():
    first=value(1,'3','start');last=value(3,'4','end');samples=[value(2,'2','loss')]
    expected=FlowAdjustedRisk(first,last,samples=samples).body()
    with localcontext() as context:
        context.prec=2;context.Emax=1;context.Emin=-1
        context.traps[Inexact]=context.traps[Rounded]=True
        model=FlowAdjustedRisk(first,last,samples=samples)
        assert model.body()==expected
    body=model.body();body['calculation']['flow_neutral_return']='100'
    assert model.body()==expected


def test_identical_boundary_samples_retain_source_refs_without_issuing_units():
    first=value(1,'100','start',1);last=value(3,'90','end',1)
    samples=[value(1,'100','same-baseline',1),value(2,'80','trough',1),
        value(2,'80','same-trough',1),value(3,'90','same-closing',1)]
    result=FlowAdjustedRisk(first,last,samples=samples).body()
    assert result['state']=='MEASURED' and D(result['calculation']['units'])==100
    assert D(result['calculation']['worst_observed_drawdown'])==D('.2')
    assert set(result['redundant_sample_refs'])=={p.source_ref for p in (samples[0],samples[2],samples[3])}
    assert all(p.source_ref in result['source_refs'] for p in samples)


def test_a_float_cannot_hide_in_an_equal_redundant_sample():
    first=value(1,'100','start',1);last=value(3,'90','end',1)
    with pytest.raises(UnitError,match='NORMALIZED_INPUT_INVALID'):
        FlowAdjustedRisk(first,last,samples=[replace(value(1,'100','float',1),equity=100.0)])
