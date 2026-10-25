"""Cumulative native read capacities; no vendor or process-memory qualification."""
import struct

import pytest

from test_ctrader_transport_lifecycle import harness, receive_frame
from vati.execution.ctrader import CtraderTransport, CtraderReadTransport, CtraderError, SCHEMA


def source(harness, **options):
    client,server=harness.pair()
    transport=CtraderReadTransport(connector=lambda *_:client,timeout_s=2,**options)
    harness.transports.append(transport)
    return transport,server


def send(server,name,body,cid=None):
    frame=SCHEMA.wrap(name,body,cid)
    server.sendall(struct.pack('>I',len(frame))+frame)
    return len(frame)


@pytest.mark.parametrize('option',['max_read_frames','max_read_bytes'])
@pytest.mark.parametrize('bad',[True,False,0,-1,1.5,'1',2**32])
def test_invalid_cumulative_capacity_is_refused_before_connecting(option,bad):
    with pytest.raises(ValueError):CtraderReadTransport(**{option:bad})


def test_frame_limit_retires_before_waiting_for_the_next_body(harness):
    transport,server=source(harness,max_read_frames=1)
    transport.connect();worker=transport._reader
    first=send(server,'ProtoOAExecutionEvent',{'ctidTraderAccountId':12345,'executionType':'ORDER_FILLED'})
    # Only a valid second header, no body. Capacity must fence before receiving it.
    server.sendall(struct.pack('>I',first))
    worker.join(.5)
    assert not worker.is_alive() and not transport.connected
    state=transport.read_capacity_snapshot()
    assert state['state']=='EXHAUSTED' and state['admitted_frame_headers']==1
    assert state['reserved_encoded_bytes']==first and state['refused_frame_length']==first
    assert transport.drain_events()==[('ProtoOAExecutionEvent',{
        'payloadType':'PROTO_OA_EXECUTION_EVENT','ctidTraderAccountId':12345,'executionType':'ORDER_FILLED'})]
    with pytest.raises(CtraderError,match='capacity'):transport.check_budget()


def test_encoded_byte_limit_refuses_the_payload_before_reading_it(harness):
    transport,server=source(harness,max_read_bytes=1)
    transport.connect();worker=transport._reader
    server.sendall(struct.pack('>I',2))
    worker.join(.5)
    assert not worker.is_alive() and not transport.connected
    state=transport.read_capacity_snapshot()
    assert state['admitted_frame_headers']==0 and state['reserved_encoded_bytes']==0
    assert state['refused_frame_length']==2


def test_exact_encoded_limit_and_correlated_reply_are_preserved(harness):
    body={'ctidTraderAccountId':12345,'symbol':[]}
    size=len(SCHEMA.wrap('ProtoOASymbolsListRes',body,'a'*16))
    transport,server=source(harness,max_read_frames=1,max_read_bytes=size)
    caller,result=harness.worker(lambda:transport.call('ProtoOASymbolsListReq',{'ctidTraderAccountId':12345}))
    _,_,cid=receive_frame(server)
    assert send(server,'ProtoOASymbolsListRes',body,cid)==size
    caller.join(1);assert not caller.is_alive()
    assert result.get_nowait()[0]=='ProtoOASymbolsListRes'
    state=transport.read_capacity_snapshot()
    assert state['state']=='WITHIN_LIMIT' and state['admitted_frame_headers']==1
    assert state['reserved_encoded_bytes']==size and state['provider_qualified'] is False


def test_draining_native_events_does_not_refund_the_original_operation_budget(harness):
    transport,server=source(harness,max_read_frames=1)
    transport.connect();worker=transport._reader
    send(server,'ProtoOAExecutionEvent',{'ctidTraderAccountId':12345,'executionType':'ORDER_FILLED'})
    assert transport.wait_event(lambda *_:True,timeout_s=.2) is not None
    server.sendall(struct.pack('>I',2))
    worker.join(.5);assert not worker.is_alive()
    with pytest.raises(CtraderError,match='capacity'):transport.connect()
    assert transport.read_capacity_snapshot()['admitted_frame_headers']==1


def test_incoming_heartbeats_count_even_though_they_do_not_enter_the_event_queue(harness):
    transport,server=source(harness,max_read_frames=1)
    transport.connect();worker=transport._reader
    first=send(server,'ProtoHeartbeatEvent',{})
    server.sendall(struct.pack('>I',first))
    worker.join(.5);assert not worker.is_alive()
    assert transport.events.empty()
    assert transport.read_capacity_snapshot()['admitted_frame_headers']==1


def test_overflow_wakes_the_original_pending_request_and_cannot_renew_on_reconnect(harness):
    transport,server=source(harness,max_read_frames=1)
    caller,result=harness.worker(lambda:transport.call('ProtoOAApplicationAuthReq',{'clientId':'fixture','clientSecret':'fixture'}))
    receive_frame(server)
    length=send(server,'ProtoHeartbeatEvent',{})
    server.sendall(struct.pack('>I',length))
    caller.join(.5);assert not caller.is_alive()
    error=result.get_nowait();assert isinstance(error,CtraderError) and 'capacity' in str(error)
    with pytest.raises(CtraderError,match='capacity'):transport.connect()
    snapshot=transport.read_capacity_snapshot();snapshot['state']='QUALIFIED'
    assert transport.read_capacity_snapshot()['state']=='EXHAUSTED'


def test_financial_transport_retains_its_existing_frame_and_response_policy():
    transport=CtraderTransport()
    assert not hasattr(transport,'max_read_frames') and not hasattr(transport,'max_read_bytes')


def test_multiple_small_frames_share_one_encoded_byte_budget(harness):
    frame=SCHEMA.wrap('ProtoHeartbeatEvent',{});size=len(frame)
    transport,server=source(harness,max_read_bytes=size*2-1)
    transport.connect();worker=transport._reader
    server.sendall(struct.pack('>I',size)+frame+struct.pack('>I',size))
    worker.join(.5);assert not worker.is_alive()
    state=transport.read_capacity_snapshot()
    assert state['admitted_frame_headers']==1 and state['reserved_encoded_bytes']==size
    assert state['refused_frame_length']==size


def test_close_and_reconnect_do_not_reset_admitted_frames_or_encoded_bytes(harness):
    transport,server=source(harness,max_read_frames=1)
    transport.connect()
    size=send(server,'ProtoOAExecutionEvent',{'ctidTraderAccountId':12345,'executionType':'ORDER_FILLED'})
    assert transport.wait_event(lambda *_:True,timeout_s=.2) is not None
    transport.close()
    replacement,peer=harness.pair();transport._connector=lambda *_:replacement
    transport.connect();worker=transport._reader
    peer.sendall(struct.pack('>I',size))
    worker.join(.5);assert not worker.is_alive()
    state=transport.read_capacity_snapshot()
    assert state['admitted_frame_headers']==1 and state['reserved_encoded_bytes']==size
    assert state['state']=='EXHAUSTED'


def test_independent_market_reader_exposes_original_capacity_and_reaps_on_overflow():
    from test_ctrader import FakeCtrader,make_adapter
    primary=FakeCtrader();adapter=make_adapter(primary);adapter._ensure_auth()
    expected=adapter.symbol('EURUSD').native_contract;before=list(primary.requests);peers=[]
    def independent(host,port):
        native=FakeCtrader();peers.append(native);return native.connector(host,port)
    adapter.transport._connector=independent
    reader=adapter.market_reader(max_read_frames=1,max_read_bytes=1024)
    try:
        with pytest.raises(CtraderError,match='capacity'):reader.read_quote(expected)
        state=reader.read_capacity_snapshot()
        assert state['state']=='EXHAUSTED' and state['admitted_frame_headers']==1
        assert primary.requests==before and adapter.transport.connected
        assert all(name not in {'ProtoOANewOrderReq','ProtoOAClosePositionReq'} for name,_ in peers[0].requests)
    finally:reader.close()
