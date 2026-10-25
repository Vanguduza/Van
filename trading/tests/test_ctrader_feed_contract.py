"""Native read boundary: scope, exact numeric fields, closed windows and registry recovery.

Transports here are source fixtures. The existing socket/protobuf suite separately
exercises the real codec/transport; neither suite claims live provider qualification.
"""
from copy import deepcopy
from decimal import Decimal, localcontext
from types import SimpleNamespace

import pytest
from vati.execution.base import VenueUnavailable
from vati.execution.ctrader.adapter import CtraderAdapter, SymbolInfo
from vati.execution.ctrader.feed import trendbars


def bar(minute=2, **changes):
    return dict(volume=12, low=110000, deltaOpen=5, deltaClose=12, deltaHigh=20,
                utcTimestampInMinutes=minute, **changes)


def response(**changes):
    return dict(ctidTraderAccountId=123, symbolId=12, period='M1',
                trendbar=[bar(2),bar(3),bar(4)], **changes)


def fixture(body=None, name='ProtoOAGetTrendbarsRes'):
    calls=[]
    def call(message,request):calls.append((message,request));return name,body if body is not None else response()
    return SimpleNamespace(_ensure_auth=lambda:None, ctid_trader_account_id=123,
        symbol=lambda symbol:SymbolInfo(12,'EURUSD',5,10000000,1,1,1000000000),
        transport=SimpleNamespace(call=call,host='demo.ctraderapi.com'),clock=lambda:300005),calls


@pytest.mark.parametrize('changes', [
    {'ctidTraderAccountId':999}, {'ctidTraderAccountId':True}, {'symbolId':999},
    {'symbolId':True}, {'period':'H1'}, {'trendbar':None},
])
def test_wrong_response_scope_or_missing_series_is_an_explicit_native_refusal(changes):
    body=response();body.update(changes);adapter,_=fixture(body)
    with pytest.raises(VenueUnavailable):trendbars(adapter,'EURUSD','M1',from_ms=120000,to_ms=300000)


def test_wrong_native_response_type_is_refused():
    adapter,_=fixture(response(),name='ProtoOASpotEvent')
    with pytest.raises(VenueUnavailable):trendbars(adapter,'EURUSD','M1',from_ms=120000,to_ms=300000)


@pytest.mark.parametrize('field', ['volume','low','utcTimestampInMinutes'])
def test_absent_native_fields_never_become_zero_market_facts(field):
    body=response();del body['trendbar'][0][field];adapter,_=fixture(body)
    with pytest.raises(VenueUnavailable):trendbars(adapter,'EURUSD','M1',from_ms=120000,to_ms=300000)


@pytest.mark.parametrize('field', ['deltaOpen','deltaClose','deltaHigh'])
def test_native_proto2_optional_zero_delta_is_valid_with_explicit_provenance(field):
    from vati.execution.ctrader import SCHEMA
    from vati.execution.ctrader.feed import read_trendbars
    row=bar();row.update(deltaOpen=0,deltaClose=0,deltaHigh=0);del row[field]
    payload=response()|{'trendbar':[row]}
    # Traverse the actual pinned wire codec with the optional field absent.
    decoded=SCHEMA.decode('ProtoOAGetTrendbarsRes',SCHEMA.encode('ProtoOAGetTrendbarsRes',payload))
    assert field not in decoded['trendbar'][0]
    adapter,_=fixture(decoded)
    observed=read_trendbars(adapter,'EURUSD','M1',from_ms=120000,to_ms=300000)
    assert observed.bars[0].open==observed.bars[0].close==observed.bars[0].high==Decimal('1.1')
    assert observed.body()['defaulted_delta_fields']==[{'start_ms':120000,'fields':[field]}]
    assert observed.body()['provider_qualified'] is False


@pytest.mark.parametrize('field,value', [
    ('volume',-1),('volume',True),('low',1.2),('deltaOpen',-1),
    ('deltaHigh',4),('deltaClose',21),('utcTimestampInMinutes',True),
    ('deltaOpen',2**64),('low',2**63),
])
def test_malformed_native_integers_and_incoherent_prices_are_refused(field,value):
    body=response();body['trendbar'][0][field]=value;adapter,_=fixture(body)
    with pytest.raises(VenueUnavailable):trendbars(adapter,'EURUSD','M1',from_ms=120000,to_ms=300000)


@pytest.mark.parametrize('minutes', [[2,2,4],[1,2,3],[2,3,6]])
def test_duplicate_and_outside_request_bars_do_not_enter_the_series(minutes):
    adapter,_=fixture(response()|{'trendbar':[bar(m) for m in minutes]})
    with pytest.raises(VenueUnavailable):trendbars(adapter,'EURUSD','M1',from_ms=120000,to_ms=300000)


def test_only_closed_bars_are_returned_and_native_tick_volume_is_not_one():
    adapter,_=fixture(response())
    result=trendbars(adapter,'EURUSD','M1',from_ms=120000,to_ms=270000)
    assert [b.start_ms for b in result]==[120000,180000]
    assert all(b.ticks==12 and b.volume==Decimal('12') for b in result)


def test_exact_native_price_conversion_does_not_depend_on_ambient_decimal_precision():
    body=response();body['trendbar'][0]['low']=123456789012345
    adapter,_=fixture(body)
    with localcontext() as context:
        context.prec=3
        actual=trendbars(adapter,'EURUSD','M1',from_ms=120000,to_ms=300000)[0]
    assert actual.low==Decimal('1234567890.12345') and actual.open==Decimal('1234567890.12350')


def test_future_request_end_does_not_make_an_open_bar_closed_before_actual_receipt():
    from vati.execution.ctrader.feed import read_trendbars
    adapter,_=fixture(response()|{'trendbar':[bar(2),bar(3)]})
    adapter.clock=lambda:200000
    actual=read_trendbars(adapter,'EURUSD','M1',from_ms=120000,to_ms=300000)
    assert len(actual.bars)==1 and actual.excluded_open_bars==1
    assert actual.received_at_ms==200000
    future,_=fixture(response());future.clock=lambda:200000
    with pytest.raises(VenueUnavailable):read_trendbars(future,'EURUSD','M1',from_ms=120000,to_ms=300000)


def test_native_observation_exposes_original_scope_pagination_and_missing_spread():
    from vati.execution.ctrader.feed import read_trendbars
    from vati.core.canonical import canonical_hash
    adapter,_=fixture(response()|{'hasMore':True,'timestamp':1})
    actual=read_trendbars(adapter,'EURUSD','M1',from_ms=120000,to_ms=300000).body()
    assert actual['native_account_id']==123 and actual['native_symbol_id']==12
    assert actual['from_ms']==120000 and actual['to_ms']==300000
    assert actual['received_at_ms']==300005 and actual['has_more'] is True
    assert actual['spread'] is None and actual['spread_state'].startswith('UNAVAILABLE')
    assert actual['volume_basis']=='NATIVE_TICK_COUNT' and actual['authority_effect']=='NONE'
    assert actual['provider_qualified'] is False and actual['contract_revision'] is None
    assert actual['observation_sha256']==canonical_hash({k:v for k,v in actual.items() if k!='observation_sha256'})


def test_empty_native_series_and_unknown_pagination_remain_explicit():
    from vati.execution.ctrader.feed import read_trendbars
    body=response();del body['trendbar'];adapter,_=fixture(body)
    actual=read_trendbars(adapter,'EURUSD','M1',from_ms=120000,to_ms=300000)
    assert actual.bars==() and actual.has_more is None


def test_m30_keeps_actual_native_gap_without_interpolating_a_live_bar():
    from vati.execution.ctrader.feed import read_trendbars
    adapter,_=fixture(response()|{'period':'M30','trendbar':[bar(0),bar(60)]})
    adapter.clock=lambda:5400000
    actual=read_trendbars(adapter,'EURUSD','M30',from_ms=0,to_ms=5400000)
    assert [b.start_ms for b in actual.bars]==[0,3600000]
    assert all(b.end_ms-b.start_ms==1800000 for b in actual.bars)


@pytest.mark.parametrize('kwargs', [
    {'from_ms':True,'to_ms':300000}, {'from_ms':300000,'to_ms':120000},
    {'from_ms':120000,'to_ms':300000,'count':0}, {'from_ms':120000,'to_ms':300000,'count':True},
])
def test_invalid_request_refuses_before_native_io(kwargs):
    adapter,calls=fixture()
    with pytest.raises(ValueError):trendbars(adapter,'EURUSD','M1',**kwargs)
    assert calls==[]


def registry_fixture():
    light=[{'symbolId':12,'symbolName':'EUR/USD','enabled':True}]
    full=[dict(symbolId=12,digits=5,pipPosition=4,lotSize=10000000,minVolume=1000,stepVolume=1000,maxVolume=1000000000)]
    responses={
        'ProtoOASymbolsListReq':['ProtoOASymbolsListRes',{'ctidTraderAccountId':123,'symbol':light}],
        'ProtoOASymbolByIdReq':['ProtoOASymbolByIdRes',{'ctidTraderAccountId':123,'symbol':full}]}
    transport=SimpleNamespace(call=lambda name,body:responses[name])
    adapter=CtraderAdapter(transport,'fixture-app',lambda:'fixture-secret',lambda:'fixture-token',123)
    return adapter,responses


@pytest.mark.parametrize('kind', ['list_account','full_account','wrong_type','duplicate_id','alias_collision','missing_detail','unsolicited_detail','missing_lot','zero_step','bool_precision'])
def test_native_symbol_registry_never_publishes_wrong_scope_partial_or_default_contracts(kind):
    adapter,responses=registry_fixture();light=responses['ProtoOASymbolsListReq'][1]['symbol'];full=responses['ProtoOASymbolByIdReq'][1]['symbol']
    if kind=='list_account':responses['ProtoOASymbolsListReq'][1]['ctidTraderAccountId']=999
    elif kind=='full_account':responses['ProtoOASymbolByIdReq'][1]['ctidTraderAccountId']=999
    elif kind=='wrong_type':responses['ProtoOASymbolByIdReq'][0]='ProtoOASpotEvent'
    elif kind=='duplicate_id':light.append(dict(light[0]))
    elif kind=='alias_collision':light.append(dict(light[0],symbolId=13,symbolName='EURUSD'));full.append(dict(full[0],symbolId=13))
    elif kind=='missing_detail':full.clear()
    elif kind=='unsolicited_detail':full.append(dict(full[0],symbolId=13))
    elif kind=='missing_lot':del full[0]['lotSize']
    elif kind=='zero_step':full[0]['stepVolume']=0
    elif kind=='bool_precision':full[0]['digits']=True
    with pytest.raises(VenueUnavailable):adapter._load_symbols()


def test_symbol_refresh_failure_preserves_original_cache_but_refuses_its_use_until_recovery():
    adapter,responses=registry_fixture();adapter._load_symbols();old=deepcopy(adapter.symbols)
    responses['ProtoOASymbolByIdReq'][1]['symbol'][0]['minVolume']=0
    with pytest.raises(VenueUnavailable):adapter._load_symbols()
    assert adapter.symbols==old
    with pytest.raises(VenueUnavailable):adapter.symbol('EURUSD')
    responses['ProtoOASymbolByIdReq'][1]['symbol'][0]['minVolume']=1000
    adapter._load_symbols()
    assert adapter.symbol('EURUSD').symbol_id==12


def test_missing_optional_native_visibility_never_grants_a_symbol_but_keeps_other_valid_products():
    adapter,responses=registry_fixture()
    responses['ProtoOASymbolsListReq'][1]['symbol'].append({'symbolId':13,'symbolName':'INVISIBLE'})
    adapter._load_symbols()
    assert set(adapter.symbols)=={'EURUSD'}
    with pytest.raises(VenueUnavailable):adapter.symbol('INVISIBLE')
