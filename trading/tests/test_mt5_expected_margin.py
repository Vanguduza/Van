"""Actual source-bound adapter reads over the signed native SDK fixture."""
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal as D,localcontext

import pytest

from test_mt5_expected_margin_worker import MarginSdk
from test_mt5_worker_funding import connection
from vati.core import Ledger
from vati.core.canonical import canonical_hash
from vati.core.units import Money
from vati.execution.base import VenueUnavailable
from vati.execution.mt5_expected_margin import Mt5ExpectedMarginObservation
from vati.funding.mt5_runtime import capture_cached_mt5
from vati.risk.account_context import context_for_account
from vati.risk.contracts import Direction


def source(tmp_path,*,ledger=None,at=None):
    sdk,worker,adapter,now=connection(tmp_path,MarginSdk())
    if at is not None:now['ms']=at
    ledger=ledger or Ledger(tmp_path/'original.sqlite');account=adapter.sync_account()
    captured=capture_cached_mt5(ledger,account,now_ms=now['ms'])
    context=context_for_account(ledger,adapter,account,now_ms=now['ms'],mt5_capture=captured)
    return sdk,worker,adapter,now,ledger,context


def quote(adapter,now,context,**changes):
    args={'price':D('1.10000'),'direction':Direction.LONG,'context':context,'deadline_ms':now['ms']+1000}
    args.update(changes)
    return adapter.expected_margin('EURUSD',D('0.10'),**args)


def test_actual_public_adapter_keeps_native_raw_estimate_scope_and_precision_without_reservation(tmp_path):
    sdk,worker,adapter,now,ledger,context=source(tmp_path);before=ledger.count()
    sdk.margin_value=.3333333333333333
    with localcontext() as c:
        c.prec=2
        value=quote(adapter,now,context)
    body=value.body();money=Money.from_body(body['estimate_money'])
    assert money.decimal==D('.3333333333333333') and money.currency=='USD'
    assert money.asset_ref==context.monetary_scope_hash and body['reported_currency_digits']==2
    assert body['reservation_amount'] is None
    assert body['execution_authority'] is body['reservation_qualified'] is body['provider_qualified'] is False
    assert body['native_account_context']['source_query_ref']==context.source_query_ref
    assert body['request']=={'symbol':'EURUSD','type':'BUY','volume':'0.10','price':'1.10000'}
    assert body['observation']['account_before']['margin_mode']==2
    copy=value.body();copy['observation']['raw_margin']='0';assert value.body()==body
    assert ledger.count()==before and not sdk.sent


@pytest.mark.parametrize('direction,side',[(Direction.LONG,'BUY'),(Direction.SHORT,'SELL')])
def test_both_sides_use_the_original_requested_price(tmp_path,direction,side):
    sdk,worker,adapter,now,_,context=source(tmp_path)
    value=quote(adapter,now,context,direction=direction,price=D('1.11000'))
    assert value.body()['request']['type']==side
    assert sdk.margin_calls[-1]==(sdk.ORDER_TYPE_BUY if side=='BUY' else sdk.ORDER_TYPE_SELL,'EURUSD',.1,1.11)
    assert not sdk.sent


@pytest.mark.parametrize('change',['context_alias','identity_missing','future_source','expired','untyped_price','untyped_direction'])
def test_missing_original_scope_or_typed_request_never_supplies_a_margin_fallback(tmp_path,change):
    sdk,worker,adapter,now,_,context=source(tmp_path);kw={}
    if change=='context_alias':context=replace(context,account_alias='another')
    elif change=='identity_missing':adapter.identity=None
    elif change=='future_source':now['ms']-=1
    elif change=='expired':kw['deadline_ms']=now['ms']
    elif change=='untyped_price':kw['price']=1.1
    elif change=='untyped_direction':kw['direction']='LONG'
    with pytest.raises(VenueUnavailable):quote(adapter,now,context,**kw)
    assert not sdk.margin_calls and not sdk.sent


@pytest.mark.parametrize('change',['amount','request','scope','authority','contract','mode','deadline'])
def test_resealed_envelope_cannot_change_original_native_units_request_or_authority(tmp_path,change):
    sdk,worker,adapter,now,_,context=source(tmp_path);body=quote(adapter,now,context).body()
    if change=='amount':body['estimate_money']['minor_units']='0'
    elif change=='request':body['request']['volume']='0.11'
    elif change=='scope':body['observation']['account_after']['currency']='EUR'
    elif change=='authority':body['execution_authority']=True
    elif change=='contract':body['observation']['contract']['volume_step']='0.03'
    elif change=='mode':body['observation']['account_after']['margin_mode']=0
    elif change=='deadline':body['valid_until_ms']+=1
    body['source_ref']=canonical_hash({k:v for k,v in body.items() if k!='source_ref'})
    with pytest.raises((ValueError,TypeError,KeyError)):Mt5ExpectedMarginObservation.from_body(body)
