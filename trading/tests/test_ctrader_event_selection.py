"""Original native deliveries survive selective waits, errors and competing readers."""
from copy import deepcopy
import struct
import threading

import pytest

from test_ctrader_transport_lifecycle import harness, receive_frame
from vati.execution.ctrader import SCHEMA


def seeded(harness, count=3):
    client,server=harness.pair();transport=harness.transport(lambda *_:client)
    transport.connect()
    for number in range(1,count+1):
        body={'ctidTraderAccountId':12345,'executionType':'ORDER_FILLED',
              'order':{'orderId':number,'clientOrderId':str(number),'orderType':'MARKET',
                       'orderStatus':'ORDER_STATUS_FILLED',
                       'tradeData':{'symbolId':1,'volume':100000,'tradeSide':'BUY'}}}
        frame=SCHEMA.wrap('ProtoOAExecutionEvent',body)
        server.sendall(struct.pack('>I',len(frame))+frame)
    # Actual ordered correlated native RPC after all original framed deliveries.
    caller,result=harness.worker(lambda:transport.call('ProtoOAApplicationAuthReq',
        {'clientId':'fixture','clientSecret':'fixture-not-a-credential'}))
    _,_,cid=receive_frame(server)
    frame=SCHEMA.wrap('ProtoOAApplicationAuthRes',{},cid)
    server.sendall(struct.pack('>I',len(frame))+frame)
    caller.join(1);assert not caller.is_alive()
    assert result.get_nowait()[0]=='ProtoOAApplicationAuthRes'
    return transport


def originals(transport):
    with transport.events.mutex:
        return deepcopy([body for _,_,body in transport.events.queue])


def test_selective_wait_preserves_original_relative_order_and_complete_payloads(harness):
    transport=seeded(harness);before=originals(transport)
    selected=transport.wait_event(lambda name,body:body['order']['orderId']==2,timeout_s=.1)
    assert selected[1]==before[1]
    assert originals(transport)==[before[0],before[2]],'selection reordered earlier native evidence'


def test_predicate_exception_does_not_consume_the_original_financial_delivery(harness):
    transport=seeded(harness);before=originals(transport)
    def broken(name,body):raise RuntimeError('fixture selector failure')
    with pytest.raises(RuntimeError,match='selector failure'):
        transport.wait_event(broken,timeout_s=.1)
    assert originals(transport)==before,'selector error discarded original financial evidence'


def test_slow_selector_does_not_hide_an_unmatched_event_from_another_consumer(harness):
    transport=seeded(harness);entered=threading.Event();release=threading.Event()
    harness.release.append(release)
    def slow(name,body):
        if body['order']['orderId']==1:
            entered.set();assert release.wait(2)
        return body['order']['orderId']==3
    worker,result=harness.worker(lambda:transport.wait_event(slow,timeout_s=.5))
    assert entered.wait(1)
    try:
        other=transport.wait_event(lambda name,body:body['order']['orderId']==1,timeout_s=.1)
        assert other is not None,'unmatched original was hidden in a different selector stash'
    finally:release.set()
    worker.join(1);assert not worker.is_alive()
    assert result.get_nowait()[1]['order']['orderId']==3
    assert [body['order']['orderId'] for body in originals(transport)]==[2]


@pytest.mark.parametrize('matched',[False,True])
def test_predicate_cannot_mutate_the_original_native_payload(harness,matched):
    transport=seeded(harness,count=1);before=originals(transport)
    def mutating(name,body):
        body['order']['tradeData']['volume']=999999
        body['order']['clientOrderId']='different'
        return matched
    selected=transport.wait_event(mutating,timeout_s=.03)
    if matched:
        assert selected[1]==before[0] and originals(transport)==[]
    else:
        assert selected is None and originals(transport)==before


def test_two_selectors_cannot_both_claim_one_original_delivery(harness):
    transport=seeded(harness,count=1);barrier=threading.Barrier(2,timeout=1)
    def match(name,body):barrier.wait();return True
    workers=[harness.worker(lambda:transport.wait_event(match,timeout_s=.15)) for _ in range(2)]
    for worker,_ in workers:worker.join(1);assert not worker.is_alive()
    values=[result.get_nowait() for _,result in workers]
    assert sum(value is None for value in values)==1
    winner=next(value for value in values if value is not None)
    assert winner[1]['order']['orderId']==1 and originals(transport)==[]


def test_selector_that_returns_after_timeout_leaves_the_original_for_reconciliation(harness):
    transport=seeded(harness,count=1);before=originals(transport)
    def late(name,body):
        threading.Event().wait(.03)
        return True
    assert transport.wait_event(late,timeout_s=.01) is None
    assert originals(transport)==before


def test_unmatched_originals_are_evaluated_once_and_remain_ordered_on_timeout(harness):
    transport=seeded(harness);before=originals(transport);seen=[]
    def miss(name,body):seen.append(body['order']['orderId']);return False
    assert transport.wait_event(miss,timeout_s=.02) is None
    assert seen==[1,2,3] and originals(transport)==before


@pytest.mark.parametrize('bad',[True,-1,float('nan'),float('inf'),'1'])
def test_invalid_wait_timeout_does_not_remove_original_evidence(harness,bad):
    transport=seeded(harness);before=originals(transport)
    with pytest.raises(ValueError):transport.wait_event(lambda *_:True,timeout_s=bad)
    assert originals(transport)==before


def test_arrival_after_snapshot_wakes_the_original_wait_without_reordering(harness):
    transport=seeded(harness);before=originals(transport);entered=threading.Event()
    def match(name,body):
        entered.set()
        return body.get('errorCode')=='FIXTURE_NEW_DELIVERY'
    worker,result=harness.worker(lambda:transport.wait_event(match,timeout_s=.3))
    assert entered.wait(1)
    server=harness.sockets[1]
    frame=SCHEMA.wrap('ProtoOAErrorRes',{'errorCode':'FIXTURE_NEW_DELIVERY','description':'original payload'})
    server.sendall(struct.pack('>I',len(frame))+frame)
    worker.join(1);assert not worker.is_alive()
    selected=result.get_nowait()
    assert selected[0]=='ProtoOAErrorRes' and selected[1]['description']=='original payload'
    assert originals(transport)==before


def test_retired_quote_cannot_be_returned_after_a_predicate_closes_its_connection(harness):
    transport=seeded(harness);before=originals(transport)
    sock=transport._sock
    transport.events.put((sock,'ProtoOASpotEvent',{'ctidTraderAccountId':12345,'symbolId':1,'bid':110100}))
    def close_original(name,body):
        if name=='ProtoOASpotEvent':transport.close();return True
        return False
    assert transport.wait_event(close_original,timeout_s=.05) is None
    assert originals(transport)==before
