"""Native deposit-currency PnL and exact fills; no broker or credentials."""
from copy import deepcopy
from decimal import Decimal as D

import pytest

from test_retirement_venue_observations import FundsTransport,ctrader
from vati.execution.base import VenueUnavailable
from vati.execution.ctrader.adapter import SymbolInfo


class NativeFunds(FundsTransport):
    def __init__(self):
        super().__init__()
        self.trader.update(balance=1005309,moneyDigits=4)
        self.positions=[{'positionId':7,'positionStatus':'POSITION_STATUS_OPEN',
            'tradeData':{'symbolId':1,'volume':10000,'tradeSide':'BUY'},'price':1.1}]
        self.pnl={'ctidTraderAccountId':12345,'moneyDigits':3,'positionUnrealizedPnL':[
            {'positionId':7,'grossUnrealizedPnL':-24000,'netUnrealizedPnL':-25000}]}
        self.requests=[]
    def call(self,name,body):
        self.requests.append((name,deepcopy(body)))
        if name=='ProtoOAGetPositionUnrealizedPnLReq':
            if self.pnl is None:raise VenueUnavailable('native PnL unavailable')
            return 'ProtoOAGetPositionUnrealizedPnLRes',deepcopy(self.pnl)
        if name=='ProtoOAReconcileReq':return 'ProtoOAReconcileRes',{'ctidTraderAccountId':12345,
            'position':deepcopy(self.positions),'order':[]}
        return deepcopy(super().call(name,body))


@pytest.mark.parametrize('volume,expected',[(10000,'0.001'),(150000,'0.015'),(123456,'0.0123456')])
def test_native_sub_centilot_quantities_are_never_rounded(volume,expected):
    symbol=SymbolInfo(1,'EURUSD',5,10000000,1,1,1000000000)
    assert symbol.volume_to_lots(volume)==D(expected)


@pytest.mark.parametrize('cached_quote',[None,(D('2'),D('2.1'))])
def test_equity_uses_native_net_pnl_in_deposit_currency_without_quote_estimation(cached_quote):
    native=NativeFunds();adapter=ctrader(native)
    adapter.symbols={'EURUSD':SymbolInfo(1,'EURUSD',5,10000000,1000,1000,1000000000)}
    if cached_quote:adapter._last_spot[1]=cached_quote
    account=adapter.sync_account()
    assert account.balance==D('100.5309') and account.equity==D('75.5309')
    assert account.currency=='EUR' and account.verified
    assert any(name=='ProtoOAGetPositionUnrealizedPnLReq' for name,_ in native.requests)


@pytest.mark.parametrize('defect',['unavailable','foreign_account','missing_position','duplicate_position',
    'foreign_position','missing_precision','string_precision','bool_money','missing_net_money'])
def test_incomplete_native_pnl_is_unavailable_not_zero_or_a_quote_estimate(defect):
    native=NativeFunds()
    if defect=='unavailable':native.pnl=None
    elif defect=='foreign_account':native.pnl['ctidTraderAccountId']=67890
    elif defect=='missing_position':native.pnl['positionUnrealizedPnL']=[]
    elif defect=='duplicate_position':native.pnl['positionUnrealizedPnL']*=2
    elif defect=='foreign_position':native.pnl['positionUnrealizedPnL'][0]['positionId']=8
    elif defect=='missing_precision':native.pnl.pop('moneyDigits')
    elif defect=='string_precision':native.pnl['moneyDigits']='3'
    elif defect=='bool_money':native.pnl['positionUnrealizedPnL'][0]['netUnrealizedPnL']=True
    elif defect=='missing_net_money':native.pnl['positionUnrealizedPnL'][0].pop('netUnrealizedPnL')
    with pytest.raises(VenueUnavailable):ctrader(native).sync_account()


def test_native_empty_position_pnl_is_an_observed_zero():
    native=NativeFunds();native.positions=[];native.pnl['positionUnrealizedPnL']=[]
    account=ctrader(native).sync_account()
    assert account.equity==account.balance==D('100.5309') and account.currency=='EUR'


@pytest.mark.parametrize('field,value',[('balance',1255309),('moneyDigits',3),('depositAssetId',1)])
def test_funds_change_during_the_native_pnl_read_needs_a_fresh_account_observation(field,value):
    class ChangingFunds(NativeFunds):
        def call(self,name,body):
            result=super().call(name,body)
            if name=='ProtoOAGetPositionUnrealizedPnLReq':self.trader[field]=value
            return result
    with pytest.raises(VenueUnavailable):ctrader(ChangingFunds()).sync_account()


def test_negative_native_pnl_round_trips_the_actual_framed_protocol():
    from test_ctrader import FakeCtrader,make_adapter
    class MarkedAccount(FakeCtrader):
        def handle(self,name,body,cid):
            if name=='ProtoOAGetPositionUnrealizedPnLReq':
                return self.send('ProtoOAGetPositionUnrealizedPnLRes',{'ctidTraderAccountId':12345,'moneyDigits':3,
                    'positionUnrealizedPnL':[{'positionId':7,'grossUnrealizedPnL':-24000,'netUnrealizedPnL':-25000}]},cid)
            return super().handle(name,body,cid)
    native=MarkedAccount();native.positions[7]={'positionId':7,'positionStatus':'POSITION_STATUS_OPEN',
        'tradeData':{'symbolId':1,'volume':10000,'tradeSide':'BUY'},'price':1.1,'swap':0}
    adapter=make_adapter(native)
    try:
        state=adapter.sync_account()
        assert state.balance==D('10053.09') and state.equity==D('10028.09')
        assert adapter.positions()[0].quantity==D('0.001')
    finally:
        adapter.transport.close();native.b.close()
