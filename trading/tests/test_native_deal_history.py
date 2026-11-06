"""Read the native protocol without guessing page order, money or finality."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
from decimal import Decimal as D,localcontext
import pytest
from test_native_cash_history import NativeCash
from test_retirement_venue_observations import ctrader
from vati.execution.base import VenueUnavailable

DEAL={'dealId':1,'orderId':2,'positionId':3,'symbolId':4,'volume':200,'filledVolume':100,
    'createTimestamp':1200,'executionTimestamp':1500,'dealStatus':'PARTIALLY_FILLED','tradeSide':'SELL',
    'executionPrice':1.105,'commission':-23,'moneyDigits':2,
    'closePositionDetail':{'entryPrice':1.1,'grossProfit':150,'swap':-7,'commission':-13,'balance':100530123456,
        'moneyDigits':8,'pnlConversionFee':2,'balanceVersion':10,'closedVolume':100}}

class NativeDeals(NativeCash):
    def __init__(self):super().__init__();self.deals=[deepcopy(DEAL)];self.page_size=1000;self.deal_requests=[]
    def call(self,name,body):
        if name=='ProtoOADealListReq':
            self.deal_requests.append(dict(body))
            rows=[deepcopy(d) for d in self.deals if body['fromTimestamp']<=d['executionTimestamp']<=body['toTimestamp']]
            return 'ProtoOADealListRes',{'ctidTraderAccountId':12345,'deal':rows[:self.page_size],'hasMore':len(rows)>self.page_size}
        return super().call(name,body)

def test_native_deal_precision_is_row_owned_and_optional_finality_fields_stay_unknown():
    adapter=ctrader(NativeDeals());adapter.clock=lambda:3000
    with localcontext() as context:
        context.prec=2
        statement=adapter.deal_history(from_ms=1000,to_ms=2000)
    deal=statement.deals[0]
    assert statement.currency=='EUR' and statement.environment=='DEMO' and statement.native_account_id==12345
    assert deal.commission==D('-.23') and deal.close.commission==D('-.00000013')
    assert deal.close.balance_after==D('1005.30123456') and deal.close.balance_version==10
    assert deal.close.pnl_conversion_fee==D('.00000002') and deal.filled_volume_cents==100
    with pytest.raises(FrozenInstanceError):deal.close.balance_after=D('0')
    transport=NativeDeals()
    for key in ['pnlConversionFee','balanceVersion','closedVolume']:transport.deals[0]['closePositionDetail'].pop(key)
    row=ctrader(transport).deal_history(from_ms=1000,to_ms=2000).deals[0]
    assert row.close.pnl_conversion_fee is row.close.balance_version is row.close.closed_volume_cents is None

def test_timestamp_partitioning_collects_complete_native_pages_without_id_order_assumptions():
    native=NativeDeals();native.page_size=1
    native.deals += [{**deepcopy(DEAL),'dealId':7,'createTimestamp':1600,'executionTimestamp':1700},
        {**deepcopy(DEAL),'dealId':4,'createTimestamp':1800,'executionTimestamp':1900}]
    statement=ctrader(native).deal_history(from_ms=1000,to_ms=2000)
    assert {row.native_id for row in statement.deals}=={1,4,7} and statement.request_count==len(native.deal_requests)>1
    assert all(q['maxRows']==1000 for q in native.deal_requests)
    assert all(q['toTimestamp']>=q['fromTimestamp'] for q in native.deal_requests)

def test_saturated_native_millisecond_never_drops_equal_time_deals_or_claims_a_complete_page():
    native=NativeDeals();native.page_size=1;native.deals += [{**deepcopy(DEAL),'dealId':2}]
    with pytest.raises(VenueUnavailable):ctrader(native).deal_history(from_ms=1000,to_ms=2000)
    assert any(q['fromTimestamp']==q['toTimestamp']==1500 for q in native.deal_requests)

@pytest.mark.parametrize('change',['foreign_account','wrong_type','bool_has_more','missing_has_more','lost_parent_fact','changed_parent_fact'])
def test_partial_foreign_or_changing_native_history_is_refused_as_a_whole(change):
    class Broken(NativeDeals):
        def call(self,name,body):
            response,value=super().call(name,body)
            if name!='ProtoOADealListReq':return response,value
            if change=='foreign_account':value['ctidTraderAccountId']=999
            elif change=='wrong_type':response='ProtoOAReconcileRes'
            elif change=='bool_has_more':value['hasMore']=1
            elif change=='missing_has_more':value.pop('hasMore')
            elif len(self.deal_requests)==1:value['hasMore']=True
            elif change=='lost_parent_fact':value['deal']=[]
            else:
                for row in value['deal']:row['closePositionDetail']['balance']+=1
            return response,value
    with pytest.raises(VenueUnavailable):ctrader(Broken()).deal_history(from_ms=1000,to_ms=2000)

@pytest.mark.parametrize('key,value',[('dealId',True),('orderId',0),('filledVolume',201),('filledVolume',-1),
    ('moneyDigits',None),('executionPrice',float('nan')),('executionTimestamp',999),('commission',True),('dealStatus',True)])
def test_invalid_native_money_fill_or_identity_is_not_normalized_into_a_fact(key,value):
    native=NativeDeals();native.deals[0][key]=value
    if key=='executionTimestamp':
        original=native.call
        def invalid_window(name,body):
            response,data=original(name,body)
            if name=='ProtoOADealListReq':data['deal']=[native.deals[0]]
            return response,data
        native.call=invalid_window
    with pytest.raises(VenueUnavailable):ctrader(native).deal_history(from_ms=1000,to_ms=2000)

def test_native_deals_have_no_effect_and_no_provider_free_text():
    native=NativeDeals();native.deals[0]['externalNote']='fixture-private-note';adapter=ctrader(native)
    statement=adapter.deal_history(from_ms=1000,to_ms=2000)
    assert 'fixture-private-note' not in str(statement.body())
    assert {name for name,_ in native.requests}=={'ProtoOATraderReq','ProtoOAAssetListReq'}
    assert statement.scope_hash==adapter.cash_movements(from_ms=1000,to_ms=2000).scope_hash

def test_native_closed_deal_money_survives_the_actual_framed_protobuf():
    from test_ctrader import FakeCtrader,make_adapter
    class Broker(FakeCtrader):
        def handle(self,name,body,cid):
            if name=='ProtoOADealListReq':return self.send('ProtoOADealListRes',{'ctidTraderAccountId':12345,'deal':[DEAL],'hasMore':False},cid)
            return super().handle(name,body,cid)
    broker=Broker();adapter=make_adapter(broker)
    try:
        statement=adapter.deal_history(from_ms=1000,to_ms=2000)
        assert statement.deals[0].commission==D('-.23') and statement.deals[0].close.swap==D('-.00000007')
        assert statement.deals[0].close.balance_after==D('1005.30123456') and statement.currency=='USD'
    finally:adapter.transport.close()
