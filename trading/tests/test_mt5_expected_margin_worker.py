"""Actual signed Windows-worker protocol over an explicit native SDK fixture."""
from types import SimpleNamespace as N

import pytest

from test_mt5_worker_funding import CashMt5,connection


class MarginSdk(CashMt5):
    def __init__(self):
        super().__init__();self.margin_calls=[];self.margin_value=33.25;self.on_margin=lambda:None
    def order_calc_margin(self,*args):
        self.margin_calls.append(args);self.on_margin();return self.margin_value


def query(adapter,now,**changes):
    body={'alias':adapter.account_alias,'symbol':'EURUSD','type':'BUY','volume':'0.10','price':'1.10000',
        'deadline_ms':now['ms']+1000}
    body.update(changes)
    return adapter._call('expected_margin',body,now_ms=now['ms'])


def test_actual_signed_worker_preserves_request_price_scope_and_unapproved_native_estimate(tmp_path):
    sdk,worker,adapter,now=connection(tmp_path,MarginSdk())
    r=query(adapter,now);body=r['observation']
    assert sdk.margin_calls==[(sdk.ORDER_TYPE_BUY,'EURUSD',.1,1.1)]
    assert body['request']=={'symbol':'EURUSD','type':'BUY','volume':'0.10','price':'1.10000'}
    assert body['raw_margin']=='33.25' and body['currency_digits']==2
    assert body['account_before']['login']==12345678 and body['account_after']['currency']=='USD'
    assert body['execution_authority'] is body['reservation_qualified'] is body['account_snapshot_atomic'] is False
    assert body['valuation_basis']=='ISOLATED_ORDER_AT_REQUEST_PRICE_EXCLUDES_EXISTING_POSITIONS_AND_PENDING_ORDERS'
    assert not sdk.sent and adapter.positions()==[]


@pytest.mark.parametrize('changes',[{'volume':'0'}, {'volume':'-0.1'}, {'volume':True},
    {'volume':'NaN'},{'volume':'0.015'}, {'price':'0'}, {'price':'1.100001'},
    {'price':1.1},{'type':'STOP'}, {'deadline_ms':1000000}, {'deadline_ms':True}])
def test_invalid_original_native_request_has_no_quote_or_order_effect(tmp_path,changes):
    from vati.execution.base import VenueUnavailable
    sdk,worker,adapter,now=connection(tmp_path,MarginSdk())
    with pytest.raises(VenueUnavailable):query(adapter,now,**changes)
    assert not sdk.margin_calls and not sdk.sent


@pytest.mark.parametrize('amount',[None,-1,float('nan'),float('inf'),True])
def test_unmeasured_invalid_margin_never_becomes_zero(tmp_path,amount):
    from vati.execution.base import VenueUnavailable
    sdk=MarginSdk();sdk.margin_value=amount;_,worker,adapter,now=connection(tmp_path,sdk)
    with pytest.raises(VenueUnavailable):query(adapter,now)
    assert not sdk.sent


def test_native_margin_deadline_is_rechecked_after_actual_sdk_read(tmp_path):
    from vati.execution.base import VenueUnavailable
    sdk,worker,adapter,now=connection(tmp_path,MarginSdk())
    sdk.on_margin=lambda:now.update(ms=now['ms']+1000)
    with pytest.raises(VenueUnavailable):query(adapter,now)
    assert len(sdk.margin_calls)==1 and not sdk.sent


def test_explicit_zero_margin_and_disabled_trade_permission_remain_readable(tmp_path):
    sdk,worker,adapter,now=connection(tmp_path,MarginSdk());sdk.margin_value=0;sdk.trade_allowed=False
    body=query(adapter,now)['observation']
    assert body['raw_margin']=='0' and body['execution_authority'] is False and not sdk.sent


@pytest.mark.parametrize('field,value',[('margin_mode',None),('margin_mode',True),('leverage',None),('currency_digits',None)])
def test_missing_original_native_margin_semantics_never_use_account_defaults(tmp_path,field,value):
    from vati.execution.base import VenueUnavailable
    sdk,worker,adapter,now=connection(tmp_path,MarginSdk());original=sdk.account_info
    def observed():
        account=original();setattr(account,field,value);return account
    sdk.account_info=observed
    with pytest.raises(VenueUnavailable):query(adapter,now)
    assert not sdk.margin_calls and not sdk.sent


@pytest.mark.parametrize('field,value',[('margin_mode',0),('leverage',100),('currency_digits',3)])
def test_native_margin_semantics_cannot_change_inside_the_original_read(tmp_path,field,value):
    from vati.execution.base import VenueUnavailable
    sdk,worker,adapter,now=connection(tmp_path,MarginSdk());original=sdk.account_info
    def change():
        def observed():
            account=original();setattr(account,field,value);return account
        sdk.account_info=observed
    sdk.on_margin=change
    with pytest.raises(VenueUnavailable):query(adapter,now)
    assert len(sdk.margin_calls)==1 and not sdk.sent
