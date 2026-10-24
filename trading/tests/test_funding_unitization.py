"""Economic counterexamples independent of order execution and payment authority."""
from decimal import Decimal as D
import pytest
from vati.funding.unitization import NetEquityPoint as V,FlowPoint as F,FlowKind as K,unitize
S='native-account-scope'
def valuation(at,value,ref='native-valuation',order=None):return V(S,at,D(value),ref,order)
def flow(at,delta,after,ref='native-flow',kind=K.EXTERNAL,order=None):return F(S,at,D(delta),D(after) if after is not None else None,kind,ref,order)

def test_deposit_is_not_profit_and_withdrawal_is_not_a_loss():
    for delta,after in [('100','200'),('-50','50')]:
        r=unitize(valuation(1,'100','start'),valuation(3,after,'end'),[flow(2,delta,after)])
        assert r['status']=='MEASURED' and D(r['flow_neutral_return'])==0 and D(r['net_account_pnl'])==0
        assert D(r['worst_observed_drawdown'])==0 and r['execution_authority'] is False

def test_deposit_cannot_erase_the_prior_trading_loss_or_drawdown():
    r=unitize(valuation(1,'100','start'),valuation(3,'190','end'),[flow(2,'100','190')])
    assert D(r['flow_neutral_return'])==D('-.1') and D(r['worst_observed_drawdown'])==D('.1')
    assert D(r['net_account_pnl'])==D('-10')

def test_withdrawal_after_a_gain_retains_the_gain():
    r=unitize(valuation(1,'100','start'),valuation(3,'60','end'),[flow(2,'-50','60')])
    assert D(r['flow_neutral_return'])==D('.1') and D(r['net_account_pnl'])==10

def test_new_capital_does_not_reweight_old_time_weighted_losses():
    r=unitize(valuation(1,'100','start'),valuation(4,'95','end'),[flow(2,'100','190'),flow(3,'-100','90','native-withdrawal')])
    assert D(r['net_account_pnl'])==D('-5')
    assert D(r['worst_observed_drawdown'])==D('.1')
    assert D(r['flow_neutral_return'])==D('-.05')

def test_internal_fees_are_account_losses_and_normalized_credit_is_not_capital():
    r=unitize(valuation(1,'100','start'),valuation(4,'98','end'),[
        flow(2,'100','100','credit',K.CREDIT_EXCLUDED),flow(3,'-2','98','fee',K.INTERNAL)])
    assert D(r['external_net_flow'])==0 and D(r['net_account_pnl'])==-2
    assert D(r['flow_neutral_return'])==D('-.02')

def test_full_redemption_preserves_history_without_inventing_a_loss_or_reset():
    r=unitize(valuation(1,'100','start'),valuation(3,'0','end'),[flow(2,'-100','0')])
    assert r['status']=='NO_ACTIVE_CAPITAL' and D(r['flow_neutral_return'])==0 and D(r['net_account_pnl'])==0
    r=unitize(valuation(1,'100','start'),valuation(5,'50','end'),[flow(2,'-100','0'),flow(4,'50','50','new-funds')])
    assert r['status']=='MEASURED' and D(r['flow_neutral_return'])==0

@pytest.mark.parametrize('movement,reason',[(flow(2,'1',None),'NATIVE_NET_FLOW_VALUATION_UNAVAILABLE'),
    (flow(2,'1','101',kind=K.UNKNOWN),'UNCLASSIFIED_NATIVE_MOVEMENT'),
    (flow(2,'100','80'),'NONPOSITIVE_NAV_AT_EXTERNAL_FLOW'),
    (flow(2,'-110','-10'),'OUTFLOW_EXCEEDS_NET_CAPITAL')])
def test_missing_or_impossible_evidence_is_unmeasured_not_zero(movement,reason):
    r=unitize(valuation(1,'100','start'),valuation(3,'100','end'),[movement])
    assert r['status']=='UNMEASURED' and r['reason']==reason and r['flow_neutral_return'] is None

def test_same_timestamp_needs_native_order_instead_of_sorting_by_id():
    flows=[flow(2,'100','210','second',order=2),flow(2,'50','260','first',order=3)]
    r=unitize(valuation(1,'100','start'),valuation(3,'260','end'),list(reversed(flows)))
    assert r['status']=='MEASURED' and D(r['flow_neutral_return'])==D('.1')
    assert unitize(valuation(1,'100','start'),valuation(3,'260','end'),[flow(2,'100','210','a'),flow(2,'50','260','b')])['status']=='UNMEASURED'

def test_native_scope_and_original_identity_cannot_be_rebound():
    from dataclasses import replace
    a=flow(2,'100','200')
    with pytest.raises(ValueError):unitize(valuation(1,'100'),valuation(3,'200'),[replace(a,scope_hash='other-account')])
    with pytest.raises(ValueError):unitize(valuation(1,'100'),valuation(3,'200'),[a,a])


def test_many_native_capital_movements_cannot_manufacture_any_account_return():
    current=D('100');events=[]
    for i in range(100):
        delta=D(i%7+1)/100;current+=delta
        events.append(flow(i+2,str(delta),str(current),'native-capital-'+str(i)))
    result=unitize(valuation(1,'100','start'),valuation(103,str(current),'end'),events)
    assert result['status']=='MEASURED' and D(result['flow_neutral_return'])==0
    assert D(result['net_account_pnl'])==0 and D(result['worst_observed_drawdown'])==0


def test_native_order_is_required_at_equal_time_valuation_boundaries():
    point=flow(1,'100','200',order=11)
    assert unitize(valuation(1,'100','start'),valuation(3,'200','end'),[point])['status']=='UNMEASURED'
    result=unitize(valuation(1,'100','start',10),valuation(3,'200','end'),[point])
    assert result['status']=='MEASURED' and D(result['flow_neutral_return'])==0
    assert unitize(valuation(0,'100','start'),valuation(1,'200','end'),[point])['status']=='UNMEASURED'
    assert unitize(valuation(0,'100','start'),valuation(1,'200','end',11),[point])['status']=='MEASURED'


def test_unmeasured_results_do_not_publish_zero_drawdown_as_if_it_were_a_complete_measurement():
    result=unitize(valuation(1,'100','start'),valuation(3,'100','end'),[flow(2,'1',None)])
    assert result['worst_observed_drawdown'] is None and result['evidence_refs']==[]
    assert result['units'] is None and result['external_net_flow'] is None
    assert 'native-flow' in result['input_refs']
