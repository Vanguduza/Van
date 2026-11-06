"""Bounded native source reads with real framed sockets and owned workers."""
import socket
import struct
import threading
import time
from dataclasses import replace

import pytest

from test_ctrader_transport_lifecycle import harness, receive_frame
from vati.execution.ctrader import CtraderTransport, CtraderError, SCHEMA
from vati.execution.ctrader import transport as module
from vati.execution.entry_deadline import EntryNotSent


def reader(harness, **options):
    cls=getattr(module,'CtraderReadTransport',None)
    assert cls is not None,'explicit bounded read-only native transport is missing'
    transport=cls(**options);harness.transports.append(transport)
    return transport


def test_oversized_native_header_retires_before_waiting_for_its_payload(harness):
    client,server=harness.pair();transport=harness.transport(lambda *_:client)
    transport.connect();worker=transport._reader
    server.sendall(struct.pack('>I',2**32-1))
    worker.join(.3)
    assert not worker.is_alive(),'unbounded native length left the reader waiting for a multi-gigabyte payload'
    assert not transport.connected and client.fileno()==-1


def test_close_joins_an_already_detached_reader_still_releasing_its_socket(harness):
    client,server=harness.pair();entered=threading.Event();release=threading.Event()
    harness.release.append(release)
    class SlowClose:
        def recv(self,size):return client.recv(size)
        def sendall(self,value):return client.sendall(value)
        def shutdown(self,how):return client.shutdown(how)
        def close(self):
            entered.set();assert release.wait(2);client.close()
    transport=harness.transport(lambda *_:SlowClose());transport.connect();original=transport._reader
    server.shutdown(socket.SHUT_RDWR);server.close()
    assert entered.wait(1) and not transport.connected
    closer,result=harness.worker(transport.close)
    try:
        closer.join(.1)
        assert closer.is_alive(),'close forgot an original reader after it detached itself'
    finally:release.set()
    closer.join(1)
    assert result.get_nowait() is None and not original.is_alive()


@pytest.mark.parametrize('bad',[True,False,0,-1,2**32,'1024',1.5])
def test_invalid_native_frame_budget_is_refused_before_connecting(bad):
    with pytest.raises(ValueError):CtraderTransport(max_frame_bytes=bad)


def test_frame_at_exact_budget_preserves_original_correlation(harness):
    client,server=harness.pair()
    size=len(SCHEMA.wrap('ProtoHeartbeatEvent',{},'a'*16))
    transport=CtraderTransport(connector=lambda *_:client,max_frame_bytes=size)
    harness.transports.append(transport)
    caller,result=harness.worker(lambda:transport.call('ProtoHeartbeatEvent',{}))
    _,_,cid=receive_frame(server)
    payload=SCHEMA.wrap('ProtoHeartbeatEvent',{},cid);assert len(payload)==size
    for byte in struct.pack('>I',len(payload))+payload:server.sendall(bytes([byte]))
    caller.join(1)
    assert result.get_nowait()[0]=='ProtoHeartbeatEvent' and transport.connected


def test_frame_budget_fault_after_native_order_write_keeps_unknown_original_effect():
    from test_ctrader import FakeCtrader,make_adapter
    from test_ctrader_original_outcomes import cmd
    class LostBroker(FakeCtrader):
        def handle(self,name,body,cid):
            if name=='ProtoOANewOrderReq':return self.b.sendall(struct.pack('>I',2**32-1))
            return super().handle(name,body,cid)
    native=LostBroker();adapter=make_adapter(native);adapter.transport.timeout_s=.5
    command=replace(cmd(),account_alias=adapter.account_alias,command_hash='').sealed()
    result=adapter.submit(command,now_ms=1000)
    assert result.status=='UNKNOWN' and not result.protective_stop_confirmed
    # Financial receipts intentionally redact wire diagnostics. Preserve the
    # existing uncertainty/privacy contract while observing actual disconnect.
    assert result.reject_reason=='native entry reply unavailable; reconcile original before retrying'
    assert sum(name=='ProtoOANewOrderReq' for name,_ in native.requests)==1
    assert not adapter.transport.connected
    adapter.transport.close()


@pytest.mark.parametrize('bad',[True,False,0,-1,float('nan'),float('inf'),'1'])
def test_invalid_total_read_budget_refuses_before_native_io(harness,bad):
    cls=getattr(module,'CtraderReadTransport',None)
    assert cls is not None,'explicit bounded source transport missing'
    with pytest.raises(ValueError):reader(harness,operation_timeout_s=bad)


@pytest.mark.parametrize('message',['ProtoOANewOrderReq','ProtoOAClosePositionReq','ProtoOAAmendPositionSLTPReq',
                                   'unknown',None,{}])
def test_read_only_transport_refuses_financial_or_unknown_operations_before_connection(harness,message):
    calls=[]
    transport=reader(harness,connector=lambda *_:calls.append(True))
    with pytest.raises(CtraderError,match='read-only'):transport.call(message,{})
    with pytest.raises(EntryNotSent):transport.call_entry('ProtoOANewOrderReq',{},expires_at_ms=2000,clock=lambda:1000)
    assert calls==[] and not transport.connected


def test_silent_native_peer_uses_one_total_budget_and_reaps_its_reader(harness):
    client,server=harness.pair();transport=reader(harness,connector=lambda *_:client,timeout_s=2,operation_timeout_s=.12)
    before=time.monotonic()
    with pytest.raises(CtraderError):transport.call('ProtoOASymbolsListReq',{'ctidTraderAccountId':12345})
    elapsed=time.monotonic()-before
    assert .05<=elapsed<.6 and not transport.connected and transport._pending=={}
    assert client.fileno()==-1


def test_total_budget_is_not_reset_by_a_later_request_or_reconnect(harness):
    client,server=harness.pair();clock={'now':0.0};calls=[]
    def connector(*_):calls.append(True);return client
    transport=reader(harness,connector=connector,operation_timeout_s=.2,monotonic=lambda:clock['now'])
    caller,result=harness.worker(lambda:transport.call('ProtoHeartbeatEvent',{}))
    _,_,cid=receive_frame(server);payload=SCHEMA.wrap('ProtoHeartbeatEvent',{},cid)
    server.sendall(struct.pack('>I',len(payload))+payload);caller.join(1)
    assert result.get_nowait()[0]=='ProtoHeartbeatEvent'
    transport.close();clock['now']=.21
    with pytest.raises(CtraderError,match='budget'):transport.call('ProtoHeartbeatEvent',{})
    assert len(calls)==1 and not transport.connected


def test_budget_is_checked_after_the_actual_send_lock_before_any_source_write(harness):
    client,server=harness.pair();clock={'now':0.0}
    transport=reader(harness,connector=lambda *_:client,operation_timeout_s=.1,monotonic=lambda:clock['now'])
    transport.connect()
    class DelayedLock:
        def acquire(self,**_):clock['now']=.2;return True
        def release(self):pass
    transport._lock=DelayedLock()
    with pytest.raises(CtraderError,match='budget'):transport.call('ProtoOASymbolsListReq',{'ctidTraderAccountId':12345})
    assert transport.sent==0 and server.recv(1024)==b''


def test_an_actual_held_send_mutex_cannot_outlive_the_read_operation_budget(harness):
    client,server=harness.pair();transport=reader(harness,connector=lambda *_:client,operation_timeout_s=.12)
    transport.connect();transport._lock.acquire()
    caller,result=harness.worker(lambda:transport.call('ProtoOASymbolsListReq',{'ctidTraderAccountId':12345}))
    try:
        caller.join(.6)
        assert not caller.is_alive(),'native read remained blocked on the send mutex beyond its budget'
        assert isinstance(result.get_nowait(),CtraderError) and transport.sent==0
    finally:transport._lock.release()


def test_connector_elapsed_time_is_charged_before_any_native_request(harness):
    client,server=harness.pair();clock={'now':0.0}
    def connector(*_):clock['now']=.2;return client
    transport=reader(harness,connector=connector,operation_timeout_s=.1,monotonic=lambda:clock['now'])
    with pytest.raises(CtraderError,match='budget'):transport.connect()
    assert client.fileno()==-1 and transport.sent==0 and not transport.connected


@pytest.mark.parametrize('bad',[True,None,'0',float('nan')])
def test_invalid_monotonic_read_clock_cannot_connect(harness,bad):
    calls=[];transport=reader(harness,connector=lambda *_:calls.append(True),monotonic=lambda:bad)
    with pytest.raises(CtraderError,match='clock'):transport.call('ProtoHeartbeatEvent',{})
    assert calls==[]


def test_backward_monotonic_read_clock_refuses_before_reconnection(harness):
    client,server=harness.pair();clock={'now':10.0};calls=[]
    def connector(*_):calls.append(True);return client
    transport=reader(harness,connector=connector,monotonic=lambda:clock['now'])
    transport.connect();transport.close();clock['now']=9.0
    with pytest.raises(CtraderError,match='backwards'):transport.call('ProtoHeartbeatEvent',{})
    assert len(calls)==1


@pytest.mark.parametrize('bad',[True,0,-1,'1',float('inf'),float('nan')])
def test_invalid_explicit_read_response_timeout_never_connects(harness,bad):
    calls=[];transport=reader(harness,connector=lambda *_:calls.append(True))
    with pytest.raises(ValueError):transport.call('ProtoHeartbeatEvent',{},timeout_s=bad)
    assert calls==[]


def test_actual_native_collection_shares_one_budget_across_auth_metadata_and_history(tmp_path):
    from test_ctrader import FakeCtrader,make_adapter
    from vati.execution.base import VenueUnavailable
    from vati.market_data.native_archive import NativeMarketArchive
    from vati.market_data.native_collector import NativeMarketCollector
    primary=FakeCtrader();adapter=make_adapter(primary)
    end=(28_333_333+3*60)*60000;adapter.clock=lambda:end;adapter._ensure_auth()
    expected=adapter.symbol('EURUSD').native_contract;before=list(primary.requests);peers=[]
    class SlowBroker(FakeCtrader):
        def handle(self,*args):time.sleep(.035);return super().handle(*args)
    def separate(host,port):
        peer=SlowBroker();peers.append(peer);return peer.connector(host,port)
    adapter.transport._connector=separate
    archive=NativeMarketArchive(tmp_path/'native',clock=lambda:end+100)
    collector=NativeMarketCollector(archive,lambda:adapter.market_reader(collection_timeout_s=.09))
    started=time.monotonic()
    with pytest.raises(VenueUnavailable):
        collector.collect('bounded-source',expected,timeframe='H1',from_ms=28_333_333*60000,to_ms=end)
    assert time.monotonic()-started<.6
    assert archive.lookup(expected.native_scope,'H1','bounded-source') is None
    assert adapter.transport.connected and primary.requests==before
    assert len(peers)==1 and peers[0].a.fileno()==-1
    adapter.transport.close()
