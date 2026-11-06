"""Original native order facts remain separate from flatness and settlement."""
from copy import deepcopy
from decimal import Decimal as D,localcontext,Inexact,Rounded

import pytest

from test_ctrader_expected_margin import source
from vati.execution.base import VenueUnavailable
from vati.execution.ctrader import SCHEMA
from vati.execution.ctrader.orders import NativeOrderObservation


def native_reply():
    def deal(identity,filled):
        return {'dealId':identity,'orderId':71,'positionId':81,'symbolId':7,'volume':1230000,
            'filledVolume':filled,'tradeSide':'BUY','dealStatus':'PARTIALLY_FILLED',
            'createTimestamp':800,'executionTimestamp':900,'executionPrice':1.1,'commission':-2,'moneyDigits':2}
    return {'ctidTraderAccountId':12345,'order':{'orderId':71,
        'tradeData':{'symbolId':7,'volume':1230000,'tradeSide':'BUY'},'orderType':'LIMIT',
        'orderStatus':'ORDER_STATUS_CANCELLED','executedVolume':500000,'utcLastUpdateTimestamp':950,
        'closingOrder':False,'clientOrderId':'original-entry'},'deal':[deal(91,200000),deal(92,300000)]}


def reader(tmp_path):
    adapter,context=source(tmp_path)
    transport=adapter.transport
    transport.order_reply=native_reply();transport.order_name='ProtoOAOrderDetailsRes';transport.on_read=lambda:None
    original=transport.call
    def call(name,body):
        if name=='ProtoOAOrderDetailsReq':
            transport.calls.append((name,deepcopy(body)))
            transport.on_read()
            return transport.order_name,deepcopy(transport.order_reply)
        return original(name,body)
    transport.call=call
    return adapter,context


def test_native_cancelled_partial_order_retains_all_original_gross_deals(tmp_path):
    adapter,context=reader(tmp_path)
    adapter.transport.order_reply=SCHEMA.decode('ProtoOAOrderDetailsRes',SCHEMA.encode('ProtoOAOrderDetailsRes',native_reply()))
    with localcontext() as decimal:
        decimal.prec=2;decimal.traps[Inexact]=True;decimal.traps[Rounded]=True
        before=dict(decimal.flags)
        observed=adapter.order_details(71,context=context,deadline_ms=2000)
        assert dict(decimal.flags)==before
    body=observed.body();facts=body['facts']
    assert facts['native_order_status']=='ORDER_STATUS_CANCELLED'
    assert facts['recorded_gross_deal_volume']==500000 and facts['reported_executed_volume']==500000
    assert [d['native_id'] for d in facts['recorded_deals']]==[91,92]
    assert facts['native_position_ids']==[81]
    assert body['remaining_entry_allowance'] is body['position_flat'] is None
    assert all(body[k] is False for k in ('cash_settled','fees_final','provider_qualified','reservation_qualified','execution_authority'))
    assert [b for n,b in adapter.transport.calls if n=='ProtoOAOrderDetailsReq']==[{'ctidTraderAccountId':12345,'orderId':71}]
    assert {n for n,_ in adapter.transport.calls}<={'ProtoOATraderReq','ProtoOAAssetListReq','ProtoOAOrderDetailsReq'}
    assert NativeOrderObservation.from_body(body).body()==body
    body['response']['deal'][0]['filledVolume']=0
    assert observed.body()['facts']['recorded_gross_deal_volume']==500000


def test_native_optional_execution_and_closing_fields_stay_missing(tmp_path):
    adapter,context=reader(tmp_path)
    for name in ('executedVolume','utcLastUpdateTimestamp','closingOrder'):adapter.transport.order_reply['order'].pop(name)
    body=adapter.order_details(71,context=context,deadline_ms=2000).body()
    assert body['facts']['reported_executed_volume'] is None
    assert body['facts']['native_last_update_ms'] is None and body['facts']['closing_order'] is None
    assert body['facts']['recorded_gross_deal_volume']==500000
    assert body['remaining_entry_allowance'] is None and body['fees_final'] is False


def test_missing_or_invalid_optional_native_fees_do_not_erase_known_fills(tmp_path):
    adapter,context=reader(tmp_path)
    adapter.transport.order_reply['deal'][0].pop('commission')
    adapter.transport.order_reply['deal'][1]['commission']=True
    body=adapter.order_details(71,context=context,deadline_ms=2000).body()
    assert body['facts']['recorded_gross_deal_volume']==500000
    assert 'commission' not in body['response']['deal'][0]
    assert body['response']['deal'][1]['commission'] is True and body['fees_final'] is False


def test_identical_native_deal_repetition_is_not_an_additional_fill(tmp_path):
    adapter,context=reader(tmp_path)
    adapter.transport.order_reply['deal'].append(deepcopy(adapter.transport.order_reply['deal'][0]))
    facts=adapter.order_details(71,context=context,deadline_ms=2000).body()['facts']
    assert facts['recorded_gross_deal_volume']==500000 and len(facts['recorded_deals'])==2


@pytest.mark.parametrize('defect',['account','order','symbol','side','duplicate','bad-volume','bad-status','payload'])
def test_foreign_or_inconsistent_native_order_facts_are_unavailable(tmp_path,defect):
    adapter,context=reader(tmp_path);response=adapter.transport.order_reply
    if defect=='account':response['ctidTraderAccountId']=54321
    elif defect=='order':response['order']['orderId']=72
    elif defect=='symbol':response['deal'][0]['symbolId']=8
    elif defect=='side':response['deal'][0]['tradeSide']='SELL'
    elif defect=='duplicate':response['deal'].append({**response['deal'][0],'filledVolume':1})
    elif defect=='bad-volume':response['deal'][0]['filledVolume']=True
    elif defect=='bad-status':response['deal'][0]['dealStatus']='REJECTED'
    else:response['payloadType']='PROTO_OA_EXPECTED_MARGIN_RES'
    with pytest.raises(VenueUnavailable):adapter.order_details(71,context=context,deadline_ms=2000)
    assert not any(n.startswith(('ProtoOANewOrder','ProtoOACancelOrder')) for n,_ in adapter.transport.calls)


@pytest.mark.parametrize('identity',[0,-1,True,'71',2**63])
def test_invalid_original_order_identifiers_never_reach_native_lookup(tmp_path,identity):
    adapter,context=reader(tmp_path)
    with pytest.raises(VenueUnavailable):adapter.order_details(identity,context=context,deadline_ms=2000)
    assert adapter.transport.calls==[]


def test_late_or_reconnected_native_query_cannot_publish_a_valid_snapshot(tmp_path):
    adapter,context=reader(tmp_path)
    adapter.transport.on_read=lambda:setattr(adapter.transport,'connection_id',2)
    with pytest.raises(VenueUnavailable):adapter.order_details(71,context=context,deadline_ms=2000)
    adapter.transport.connection_id=1
    adapter.transport.on_read=lambda:setattr(adapter,'clock',lambda:2000)
    with pytest.raises(VenueUnavailable):adapter.order_details(71,context=context,deadline_ms=2000)
    assert sum(n=='ProtoOAOrderDetailsReq' for n,_ in adapter.transport.calls)==2


def test_conflicting_cumulative_totals_remain_visible_without_release_authority(tmp_path):
    adapter,context=reader(tmp_path)
    adapter.transport.order_reply['order']['executedVolume']=600000
    body=adapter.order_details(71,context=context,deadline_ms=2000).body()
    assert body['facts']['observation_state']=='NATIVE_EXECUTION_TOTALS_UNRECONCILED'
    assert body['facts']['execution_total_relation']=='CONFLICT'
    assert body['facts']['reported_executed_volume']==600000
    assert body['facts']['recorded_gross_deal_volume']==500000
    assert body['remaining_entry_allowance'] is None and body['reservation_qualified'] is False


@pytest.mark.parametrize('flag',['cash_settled','fees_final','provider_qualified','reservation_qualified','execution_authority'])
def test_resealing_a_snapshot_cannot_issue_native_finality_or_authority(tmp_path,flag):
    from vati.core.canonical import canonical_hash
    adapter,context=reader(tmp_path)
    body=adapter.order_details(71,context=context,deadline_ms=2000).body();body[flag]=True
    body['source_ref']=canonical_hash({k:v for k,v in body.items() if k!='source_ref'})
    with pytest.raises(ValueError):NativeOrderObservation.from_body(body)


def test_actual_framed_order_lookup_keeps_original_account_and_deals(tmp_path):
    from test_ctrader import FakeCtrader
    from vati.execution.ctrader.adapter import CtraderAdapter
    from vati.execution.ctrader.transport import CtraderTransport,DEMO_HOST
    class Peer(FakeCtrader):
        def handle(self,name,body,cid):
            if name=='ProtoOAOrderDetailsReq':return self.send('ProtoOAOrderDetailsRes',native_reply(),cid)
            if name=='ProtoOATraderReq':return self.send('ProtoOATraderRes',{'ctidTraderAccountId':12345,
                'trader':{'ctidTraderAccountId':12345,'depositAssetId':2,'balance':1000000,'moneyDigits':2}},cid)
            if name=='ProtoOAAssetListReq':return self.send('ProtoOAAssetListRes',{'ctidTraderAccountId':12345,
                'asset':[{'assetId':2,'name':'EUR'}]},cid)
            return super().handle(name,body,cid)
    _,context=source(tmp_path)
    peer=Peer();transport=CtraderTransport(host=DEMO_HOST,connector=peer.connector,timeout_s=.5)
    adapter=CtraderAdapter(transport,'fixture',lambda:'app-secret',lambda:'tok',12345,clock=lambda:1000)
    try:
        body=adapter.order_details(71,context=context,deadline_ms=2000).body()
        assert body['facts']['native_order_status']=='ORDER_STATUS_CANCELLED'
        assert body['facts']['recorded_gross_deal_volume']==500000
        assert [r for n,r in peer.requests if n=='ProtoOAOrderDetailsReq']==[
            {'payloadType':'PROTO_OA_ORDER_DETAILS_REQ','ctidTraderAccountId':12345,'orderId':71}]
        assert not any(n in ('ProtoOANewOrderReq','ProtoOACancelOrderReq') for n,_ in peer.requests)
    finally:
        transport.close();peer.close()
