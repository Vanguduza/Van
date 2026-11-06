"""Original native read protocol fixtures; no live account qualification."""
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal as D, localcontext
from types import SimpleNamespace

import pytest

from vati.core import Ledger
from vati.core.units import Money
from vati.execution.base import VenueUnavailable
from vati.execution.ctrader import SCHEMA
from vati.execution.ctrader.adapter import CtraderAdapter, SymbolInfo
from vati.execution.ctrader.contracts import NativeSymbolContract
from vati.execution.ctrader.transport import DEMO_HOST
from vati.funding.native import NativeAccountMark
from vati.risk.account_context import context_for_account


class MarginTransport:
    connected = True
    connection_id = 1
    host = DEMO_HOST

    def __init__(self):
        self.calls = []
        self.trader = dict(ctidTraderAccountId=12345, depositAssetId=2,
            balance=1000000, moneyDigits=2, leverageInCents=10000)
        self.response = dict(ctidTraderAccountId=12345, moneyDigits=3,
            margin=[dict(volume=1230000, buyMargin=12345, sellMargin=23456)])
        self.response_name = 'ProtoOAExpectedMarginRes'
        self.on_quote = lambda: None
        self.currency = 'EUR'

    def call(self, name, body):
        self.calls.append((name, deepcopy(body)))
        if name == 'ProtoOATraderReq':
            return 'ProtoOATraderRes', dict(ctidTraderAccountId=12345, trader=deepcopy(self.trader))
        if name == 'ProtoOAAssetListReq':
            return 'ProtoOAAssetListRes', dict(ctidTraderAccountId=12345,
                asset=[dict(assetId=2, name=self.currency)])
        assert name == 'ProtoOAExpectedMarginReq', 'unexpected effectful request'
        self.on_quote()
        return self.response_name, deepcopy(self.response)


def source(tmp_path):
    transport = MarginTransport()
    adapter = CtraderAdapter(transport, 'fixture', lambda:'unused', lambda:'unused',
        12345, clock=lambda:1000)
    adapter._authed = True
    adapter._auth_connection = adapter._symbol_connection = 1
    original = NativeSymbolContract.capture(account_id=12345, transport_host=DEMO_HOST,
        light=dict(symbolId=7, symbolName='EURUSD', enabled=True),
        detail=dict(symbolId=7, digits=5, pipPosition=4, lotSize=10000000,
            minVolume=1000, maxVolume=100000000, stepVolume=1000), received_at_ms=900)
    adapter.symbols['EURUSD'] = SymbolInfo(7, 'EURUSD', 5, 10000000, 1000, 1000,
        100000000, original.revision, original)
    mark = NativeAccountMark('CTRADER', 'DEMO', adapter.account_alias, 12345, 2,
        'EUR', 900, D('10000'), D('10000'), 1, None, None, None)
    account = SimpleNamespace(verified=True, funding_mark=mark, account_alias=adapter.account_alias,
        balance=mark.balance, equity=mark.net_equity, currency=mark.currency)
    context = context_for_account(Ledger(tmp_path/'scope.sqlite'), adapter, account, now_ms=1000)
    return adapter, context


def quote(adapter, context, **kw):
    return adapter.expected_margin('EUR/USD', D('.123'), context=context, deadline_ms=2000, **kw)


def test_actual_adapter_read_preserves_original_native_quantity_scale_scope_and_no_order_effect(tmp_path):
    adapter, context = source(tmp_path)
    adapter.transport.response = SCHEMA.decode('ProtoOAExpectedMarginRes',
        SCHEMA.encode('ProtoOAExpectedMarginRes', adapter.transport.response))
    with localcontext() as precision:
        precision.prec = 2
        value = quote(adapter, context)
    body = value.body()
    assert body['native_volume'] == 1230000 and body['original_quantity'] == '0.123'
    assert Money.from_body(body['buy_margin']).decimal == D('12.345')
    assert Money.from_body(body['sell_margin']).decimal == D('23.456')
    assert body['buy_margin']['asset_ref'] == context.monetary_scope_hash
    assert body['physical_account_key'] == context.physical_account_key
    assert body['native_contract_revision'] == adapter.symbols['EURUSD'].native_contract.revision
    assert body['execution_authority'] is body['reservation_qualified'] is body['provider_qualified'] is False
    assert 'ACCORDING_TO_GSL' in body['calculation_limitations'][0]
    assert body['valuation_basis'] == 'NATIVE_CURRENT_PRICE_ESTIMATE_NO_ORDER_PRICE_INPUT'
    request = [b for n,b in adapter.transport.calls if n == 'ProtoOAExpectedMarginReq']
    assert request == [dict(ctidTraderAccountId=12345,symbolId=7,volume=[1230000])]
    assert SCHEMA.decode('ProtoOAExpectedMarginReq',SCHEMA.encode('ProtoOAExpectedMarginReq',request[0]))['volume'] == [1230000]
    changed = value.body(); changed['buy_margin']['atoms'] = 0
    assert value.body() == body


@pytest.mark.parametrize('changes', [
    {'ctidTraderAccountId':54321}, {'ctidTraderAccountId':True}, {'moneyDigits':None},
    {'moneyDigits':True}, {'moneyDigits':19}, {'margin':[]},
    {'margin':[dict(volume=1230001,buyMargin=1,sellMargin=1)]},
    {'margin':[dict(volume=1230000,buyMargin=-1,sellMargin=1)]},
    {'margin':[dict(volume=1230000,buyMargin=1,sellMargin=True)]},
    {'margin':[dict(volume=1230000,buyMargin=1,sellMargin=1.5)]},
    {'margin':[{},{}]},
])
def test_malformed_native_margin_has_no_estimate_or_zero_fallback(tmp_path,changes):
    adapter, context = source(tmp_path); adapter.transport.response.update(changes)
    with pytest.raises(VenueUnavailable):quote(adapter,context)


@pytest.mark.parametrize('quantity',[D('0'),D('-1'),D('NaN'),D('Infinity'),
    D('.000000001'),D('.00015'),D('20'),'0.123',.123,True])
def test_requested_quantity_is_exact_and_never_floored_to_native_step(tmp_path,quantity):
    adapter,context=source(tmp_path)
    with pytest.raises(VenueUnavailable):
        adapter.expected_margin('EURUSD',quantity,context=context,deadline_ms=2000)
    assert not any(n=='ProtoOAExpectedMarginReq' for n,b in adapter.transport.calls)


@pytest.mark.parametrize('change',['reconnect','deposit','currency','leverage','expiry','disconnect','margin_mode','money_digits'])
def test_quote_is_refused_if_scope_or_deadline_changes_during_native_io(tmp_path,change):
    adapter,context=source(tmp_path); transport=adapter.transport
    def change_state():
        if change=='reconnect':transport.connection_id=2
        elif change=='deposit':transport.trader['depositAssetId']=3
        elif change=='currency':transport.currency='USD'
        elif change=='leverage':transport.trader['leverageInCents']=20000
        elif change=='expiry':adapter.clock=lambda:2000
        elif change=='disconnect':transport.connected=False
        elif change=='margin_mode':transport.trader['totalMarginCalculationType']='SUM'
        elif change=='money_digits':transport.trader['moneyDigits']=3
    transport.on_quote=change_state
    with pytest.raises(VenueUnavailable):quote(adapter,context)


@pytest.mark.parametrize('change',['context_account','context_alias','metadata','future_contract','unbound_contract','wrong_response','symbol_name','symbol_digits','connection_missing'])
def test_original_native_context_and_contract_are_required(tmp_path,change):
    adapter,context=source(tmp_path);spec=adapter.symbols['EURUSD']
    if change=='context_account':adapter.ctid_trader_account_id=99999
    elif change=='context_alias':context=replace(context,account_alias='another')
    elif change=='metadata':spec.lot_size_cents+=1
    elif change=='future_contract':spec.native_contract=replace(spec.native_contract,received_at_ms=1001)
    elif change=='unbound_contract':spec.native_contract=None
    elif change=='wrong_response':adapter.transport.response_name='ProtoOANewOrderRes'
    elif change=='symbol_name':spec.name='GBPUSD'
    elif change=='symbol_digits':spec.digits=4
    elif change=='connection_missing':adapter.transport.connection_id=adapter._auth_connection=adapter._symbol_connection=None
    with pytest.raises(VenueUnavailable):quote(adapter,context)


@pytest.mark.parametrize('field,value',[('buy_margin',None),('execution_authority',True),
    ('reservation_qualified',True),('provider_qualified',True),('native_volume',True),
    ('original_quantity','0.122'),('native_symbol_id',8),('calculation_limitations',[])])
def test_even_resealed_observations_cannot_change_original_units_scope_or_authority(tmp_path,field,value):
    from vati.core.canonical import canonical_hash
    from vati.execution.ctrader.margin_quote import ExpectedMarginObservation
    adapter,context=source(tmp_path);body=quote(adapter,context).body();body[field]=value
    body['source_ref']=canonical_hash({k:v for k,v in body.items() if k!='source_ref'})
    with pytest.raises((ValueError,TypeError,KeyError)):ExpectedMarginObservation.from_body(body)


def test_original_native_zero_is_retained_and_missing_money_precision_is_refused(tmp_path):
    adapter,context=source(tmp_path)
    adapter.transport.response['margin'][0].update(buyMargin=0,sellMargin=0)
    assert Money.from_body(quote(adapter,context).body()['buy_margin']).minor_units==0
    del adapter.transport.response['moneyDigits']
    with pytest.raises(VenueUnavailable):quote(adapter,context)
