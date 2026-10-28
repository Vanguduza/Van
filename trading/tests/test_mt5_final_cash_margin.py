"""Actual signed entry protocol over explicit native SDK cash fixtures."""
from decimal import Decimal as D
import pytest

from test_mt5_expected_margin_worker import MarginSdk
from test_mt5_worker_funding import connection
from vati.execution.base import OrderCommand,StopMode
from vati.risk.contracts import Direction,LossModel


class EntryCashSdk(MarginSdk):
    def __init__(self,*,equity,credit,used,reported_free):
        super().__init__();self.entry_equity=equity;self.credit=credit
        self.entry_used=used;self.entry_reported_free=reported_free
    def account_info(self):
        a=super().account_info();a.equity=self.entry_equity;a.margin=self.entry_used
        a.margin_level=self.entry_equity*100/self.entry_used if self.entry_used>0 else 0.
        a.margin_free=self.entry_reported_free;return a


def command(alias,*,intent='cash-entry',expiry=None):
    return OrderCommand(intent,'d'*64,intent,alias,'mt5','EURUSD',Direction.LONG,'MARKET',
        D('.10'),D('1.10008'),D('1.09800'),StopMode.VENUE,LossModel.STOP_DISTANCE,
        max_slippage=D('.0002'),expires_at_ms=expiry).sealed()


@pytest.mark.parametrize('facts',[{'equity':100.,'credit':95.,'used':0.,'reported_free':100.},
    {'equity':100.,'credit':0.,'used':90.,'reported_free':100.}])
def test_original_signed_entry_cannot_spend_credit_or_more_than_cash_free_capacity(tmp_path,facts):
    sdk,worker,adapter,now=connection(tmp_path,EntryCashSdk(**facts));sdk.margin_value=33.25
    receipt=adapter.submit(command(adapter.account_alias),now_ms=now['ms'])
    assert not sdk.sent,'actual native order_send was reached despite insufficient cash-backed margin'
    assert receipt.status=='REJECTED' and receipt.filled_qty==0
    assert receipt.reject_reason.startswith('NATIVE_CASH_MARGIN_INSUFFICIENT:')


def test_original_signed_entry_with_sufficient_native_cash_retains_fill_and_protection(tmp_path):
    sdk,worker,adapter,now=connection(tmp_path,EntryCashSdk(equity=1000.,credit=0.,used=10.,reported_free=990.))
    receipt=adapter.submit(command(adapter.account_alias),now_ms=now['ms'])
    assert receipt.status=='FILLED' and receipt.filled_qty==D('.10') and receipt.protective_stop_confirmed
    assert len(sdk.sent)==1 and sdk.sent[0]['sl']==1.098
    assert sdk.margin_calls==[(sdk.ORDER_TYPE_BUY,'EURUSD',.1,1.10008)]


@pytest.mark.parametrize('value',[None,-1.,float('nan'),float('inf'),True])
def test_unavailable_native_margin_is_never_a_zero_requirement(tmp_path,value):
    sdk,worker,adapter,now=connection(tmp_path,EntryCashSdk(equity=1000.,credit=0.,used=0.,reported_free=1000.))
    sdk.margin_value=value;receipt=adapter.submit(command(adapter.account_alias),now_ms=now['ms'])
    assert receipt.status=='REJECTED' and not sdk.sent
    assert receipt.reject_reason.startswith('NATIVE_CASH_MARGIN_UNAVAILABLE:')


@pytest.mark.parametrize('field',['credit','equity','margin','margin_free','currency_digits','leverage','margin_mode'])
def test_missing_native_cash_or_unit_fact_refuses_without_hiding_a_new_entry(tmp_path,field):
    sdk=EntryCashSdk(equity=1000.,credit=0.,used=0.,reported_free=1000.);original=sdk.account_info
    def missing():
        a=original();setattr(a,field,None);return a
    sdk.account_info=missing;sdk,worker,adapter,now=connection(tmp_path,sdk)
    receipt=adapter.submit(command(adapter.account_alias),now_ms=now['ms'])
    assert receipt.status=='REJECTED' and not sdk.sent


def test_cash_decline_during_native_calculation_refuses_the_original_entry(tmp_path):
    sdk,worker,adapter,now=connection(tmp_path,EntryCashSdk(equity=1000.,credit=0.,used=0.,reported_free=1000.))
    sdk.on_margin=lambda:setattr(sdk,'entry_equity',20.)
    receipt=adapter.submit(command(adapter.account_alias),now_ms=now['ms'])
    assert len(sdk.margin_calls)==1 and receipt.status=='REJECTED' and not sdk.sent


def test_final_native_guard_rechecks_cash_after_the_calculation_readback(tmp_path):
    sdk=EntryCashSdk(equity=1000.,credit=0.,used=0.,reported_free=1000.);original=sdk.account_info
    state={'armed':False,'reads':0}
    def account():
        a=original()
        if state['armed']:
            state['reads']+=1
            if state['reads']>=2:a.equity=20.
        return a
    sdk.account_info=account;sdk.on_margin=lambda:state.update(armed=True)
    sdk,worker,adapter,now=connection(tmp_path,sdk)
    receipt=adapter.submit(command(adapter.account_alias),now_ms=now['ms'])
    assert state['reads']==2 and receipt.status=='REJECTED' and not sdk.sent
    assert receipt.reject_reason.startswith('NATIVE_CASH_MARGIN_INSUFFICIENT:')


def test_unit_change_during_calculation_cannot_relabel_the_margin(tmp_path):
    sdk=EntryCashSdk(equity=1000.,credit=0.,used=0.,reported_free=1000.);original=sdk.account_info;state={'digits':2}
    def account():
        a=original();a.currency_digits=state['digits'];return a
    sdk.account_info=account;sdk.on_margin=lambda:state.update(digits=3)
    sdk,worker,adapter,now=connection(tmp_path,sdk)
    receipt=adapter.submit(command(adapter.account_alias),now_ms=now['ms'])
    assert receipt.status=='REJECTED' and not sdk.sent


def test_native_calculation_cannot_extend_the_original_explicit_entry_deadline(tmp_path):
    sdk,worker,adapter,now=connection(tmp_path,EntryCashSdk(equity=1000.,credit=0.,used=0.,reported_free=1000.))
    expiry=now['ms']+1000;sdk.on_margin=lambda:now.update(ms=expiry)
    receipt=adapter.submit(command(adapter.account_alias,expiry=expiry),now_ms=now['ms'])
    assert len(sdk.margin_calls)==1 and receipt.status=='REJECTED' and not sdk.sent


def test_exact_declared_unit_rounding_holds_under_hostile_decimal_context(tmp_path):
    from decimal import localcontext,Inexact,ROUND_CEILING
    sdk,worker,adapter,now=connection(tmp_path,EntryCashSdk(equity=33.25,credit=0.,used=0.,reported_free=33.25))
    sdk.margin_value=33.25000001;cmd=command(adapter.account_alias)
    with localcontext() as ctx:
        ctx.prec=1;ctx.rounding=ROUND_CEILING;ctx.traps[Inexact]=True
        receipt=adapter.submit(cmd,now_ms=now['ms'])
    assert receipt.status=='REJECTED' and not sdk.sent


def test_explicit_zero_native_requirement_retains_positive_cash_entry(tmp_path):
    sdk,worker,adapter,now=connection(tmp_path,EntryCashSdk(equity=1.,credit=0.,used=0.,reported_free=1.))
    sdk.margin_value=0.
    assert adapter.submit(command(adapter.account_alias),now_ms=now['ms']).status=='FILLED'
    assert len(sdk.margin_calls)==1 and len(sdk.sent)==1


def test_insufficient_cash_still_allows_original_protective_tighten_and_close(tmp_path):
    sdk,worker,adapter,now=connection(tmp_path,EntryCashSdk(equity=1000.,credit=0.,used=0.,reported_free=1000.))
    receipt=adapter.submit(command(adapter.account_alias),now_ms=now['ms']);assert receipt.status=='FILLED'
    sdk.entry_equity=1.;sdk.entry_reported_free=0.;before=len(sdk.margin_calls)
    assert adapter.modify_stop(receipt.broker_position_id,D('1.099'),now_ms=now['ms']).status=='ACCEPTED'
    assert adapter.close(receipt.broker_position_id,None,now_ms=now['ms'],reason='OWNER').status=='FILLED'
    assert not adapter.positions() and len(sdk.margin_calls)==before
