"""Native facts needed to distinguish unknown funds/orders from empty accounts."""
from decimal import Decimal
import pytest
from vati.execution.base import VenueUnavailable
from vati.execution.deriv import DerivAdapter
from vati.execution.ctrader.adapter import CtraderAdapter
from vati.execution.mt5_pull import BridgeQueue,Mt5PullAdapter


class FundsTransport:
    connected=True
    def __init__(self):
        self.trader={'ctidTraderAccountId':12345,'balance':10025,'depositAssetId':2,'moneyDigits':2}
        self.assets=[{'assetId':1,'name':'USD'},{'assetId':2,'name':'EUR'}]
    def call(self,name,body):
        if name=='ProtoOATraderReq':return 'ProtoOATraderRes',{'ctidTraderAccountId':12345,'trader':self.trader}
        if name=='ProtoOAAssetListReq':return 'ProtoOAAssetListRes',{'ctidTraderAccountId':12345,'asset':self.assets}
        if name=='ProtoOAReconcileReq':return 'ProtoOAReconcileRes',{'ctidTraderAccountId':12345,'position':[],'order':[]}
        if name=='ProtoOAGetPositionUnrealizedPnLReq':return 'ProtoOAGetPositionUnrealizedPnLRes',{
            'ctidTraderAccountId':12345,'moneyDigits':2,'positionUnrealizedPnL':[]}
        raise AssertionError('unexpected effectful/provider call '+name)


def ctrader(transport):
    a=CtraderAdapter(transport,client_id='fixture',client_secret_provider=lambda:'fixture',
        access_token_provider=lambda:'fixture',ctid_trader_account_id=12345)
    a._authed=True
    return a


def test_native_ctrader_currency_is_resolved_from_deposit_asset_not_default_usd():
    state=ctrader(FundsTransport()).sync_account()
    assert state.currency=='EUR' and state.balance==Decimal('100.25')


@pytest.mark.parametrize('change',['currency','precision','identity'])
def test_missing_or_mismatched_native_funds_are_not_healthy_defaults(change):
    native=FundsTransport()
    if change=='currency':native.assets=[]
    elif change=='precision':native.trader.pop('moneyDigits')
    else:native.trader['ctidTraderAccountId']=98765
    with pytest.raises(VenueUnavailable):ctrader(native).sync_account()


def test_missing_deriv_native_balance_cannot_be_guessed_zero():
    adapter=DerivAdapter(transport=lambda msg:{'authorize':{'loginid':'VRTC123','currency':'USD'}})
    with pytest.raises(VenueUnavailable):adapter.sync_account()


def test_legacy_ea_snapshot_has_unknown_orders_until_explicit_observation(tmp_path):
    queue=BridgeQueue(tmp_path/'queue.sqlite');now=1700000000000
    try:
        queue.set_state('mt5_ea',{'login':123},[],now_ms=now,nonce='n1')
        adapter=Mt5PullAdapter(queue,clock=lambda:now)
        with pytest.raises(VenueUnavailable):adapter.orders()
        queue.set_state('mt5_ea',{'login':123},[],now_ms=now,nonce='n2',orders=[])
        assert adapter.orders()==[]
        queue.set_state('mt5_ea',{'login':123},[],now_ms=now,nonce='n3')
        with pytest.raises(VenueUnavailable):adapter.orders()
    finally:queue.close()
