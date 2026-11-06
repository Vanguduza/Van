"""Real signing/SQL/router/adapter/framing with an owned deterministic peer."""
import pytest

from test_ctrader_cancel_transport import CancelPeer
from test_ctrader_order_details import native_reply
from test_native_cancel_owner import setup_cancel
from vati.execution.ctrader.adapter import CtraderAdapter
from vati.execution.ctrader.transport import CtraderTransport,DEMO_HOST


class PendingPeer(CancelPeer):
    def __init__(self,*,lost_reply):
        self.cancelled=False;self.lost_reply=lost_reply
        super().__init__()

    def handle(self,name,body,cid):
        if name=='ProtoOATraderReq':
            return self.send('ProtoOATraderRes',{'ctidTraderAccountId':12345,
                'trader':{'ctidTraderAccountId':12345,'depositAssetId':2,'balance':1000000,'moneyDigits':2}},cid)
        if name=='ProtoOAAssetListReq':
            return self.send('ProtoOAAssetListRes',{'ctidTraderAccountId':12345,'asset':[{'assetId':2,'name':'EUR'}]},cid)
        reply=native_reply();reply['order']['orderId']=2
        reply['order']['orderStatus']='ORDER_STATUS_CANCELLED' if self.cancelled else 'ORDER_STATUS_ACCEPTED'
        for deal in reply['deal']:deal['orderId']=2;deal['positionId']=3
        if name=='ProtoOAOrderDetailsReq':
            assert body['orderId']==2
            return self.send('ProtoOAOrderDetailsRes',reply,cid)
        if name=='ProtoOACancelOrderReq':
            assert body['orderId']==2;self.cancelled=True
            if self.lost_reply:return
            reply['order']['orderStatus']='ORDER_STATUS_CANCELLED'
            return self.send('ProtoOAExecutionEvent',{'ctidTraderAccountId':12345,'executionType':'ORDER_CANCELLED',
                'order':reply['order'],'deal':reply['deal'][0]},cid)
        return super().handle(name,body,cid)


@pytest.mark.parametrize('lost_reply',[False,True])
def test_actual_signed_control_committed_sql_and_framed_cancel_recover_same_original_order(tmp_path,eurusd,lost_reply):
    ledger,fixture,router,owner,authority,clock,intent,token=setup_cancel(tmp_path,eurusd)
    peer=PendingPeer(lost_reply=lost_reply)
    transport=CtraderTransport(host=DEMO_HOST,connector=peer.connector,timeout_s=.2)
    adapter=CtraderAdapter(transport,'fixture',lambda:'app-secret',lambda:'tok',12345,
        account_alias=fixture.account_alias,clock=lambda:clock['ms'])
    router.adapters={'ctrader':adapter}
    try:
        result=router.cancel_native_order(intent,token,authority=authority.verifier)
        assert result['attempt_state']==('UNKNOWN' if lost_reply else 'WIRE_OBSERVED')
        assert peer.cancelled
        clock['ms']+=100000
        current=router.reconcile_native_cancel('cancel-1','framed-read-original',deadline_ms=clock['ms']+1000,
                                               authority=authority.verifier)
        assert current['state']=='ORDER_OBSERVED' and current['position_flat'] is None and current['cash_settled'] is False
        assert router.cancel_native_order(intent,None,authority=authority.verifier)['attempt_state']==result['attempt_state']
        assert [n for n,_ in peer.requests].count('ProtoOACancelOrderReq')==1
        assert not {'ProtoOANewOrderReq','ProtoOAClosePositionReq','ProtoOAAmendOrderReq'}.intersection(n for n,_ in peer.requests)
        from vati.execution.native_order_book import NativeOrderBook
        native=NativeOrderBook(ledger).lookup('framed-read-original')['observation']
        assert native['facts']['recorded_gross_deal_volume']==500000
        assert native['facts']['native_order_status']=='ORDER_STATUS_CANCELLED'
        assert ledger.verify_chain()[0]
    finally:transport.close();peer.close();ledger.close()
