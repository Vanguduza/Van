"""Read-only producer, original-operation replay and native connection separation."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import threading

import pytest

from test_native_market_archive import archive, contract, observation
from vati.execution.base import VenueUnavailable
from vati.market_data.native_archive import NativeArchiveError
from vati.market_data.feeds.lake import BarLake
from vati.market_data.native_collector import NativeMarketCollector


def fixture(tmp_path, *, fail=False, changed=False):
    c=contract();book=archive(tmp_path);calls=[];closed=[]
    class Reader:
        def read_window(self,expected,**window):
            calls.append((expected.revision,window))
            if fail:raise VenueUnavailable('fixture provider unavailable')
            sample=observation(c)
            if changed:sample=replace(sample,to_ms=299999)
            return c,sample
        def close(self):closed.append(True)
    return NativeMarketCollector(book,Reader),book,c,calls,closed


def test_original_collection_replays_before_provider_access_and_preserves_available_time(tmp_path):
    collector,book,c,calls,closed=fixture(tmp_path)
    first=collector.collect('original',c,timeframe='M1',from_ms=120000,to_ms=300000)
    assert first['available_at_ms']==400000 and len(calls)==len(closed)==1
    collector.reader_factory=lambda:pytest.fail('completed original must not reconnect')
    assert collector.collect('original',c,timeframe='M1',from_ms=120000,to_ms=300000)==first
    assert book.snapshot(c.native_scope,'M1')['receipt']['provider_qualified'] is False


def test_rebound_original_request_is_refused_without_provider_access(tmp_path):
    collector,book,c,calls,closed=fixture(tmp_path)
    original=collector.collect('original',c,timeframe='M1',from_ms=120000,to_ms=300000)
    with pytest.raises(NativeArchiveError,match='conflicts'):
        collector.collect('original',c,timeframe='M1',from_ms=120001,to_ms=300000)
    assert len(calls)==1 and book.lookup(c.native_scope,'M1','original')==original


@pytest.mark.parametrize('mode',['unavailable','changed'])
def test_failed_native_read_closes_its_reader_and_does_not_publish_empty_success(tmp_path,mode):
    collector,book,c,calls,closed=fixture(tmp_path,fail=mode=='unavailable',changed=mode=='changed')
    with pytest.raises((NativeArchiveError,VenueUnavailable)):
        collector.collect('failed',c,timeframe='M1',from_ms=120000,to_ms=300000)
    assert closed==[True] and book.lookup(c.native_scope,'M1','failed') is None


@pytest.mark.parametrize('kwargs',[{'from_ms':True,'to_ms':300000},{'from_ms':300000,'to_ms':120000},
                                    {'from_ms':120000,'to_ms':2**63}])
def test_invalid_native_window_is_refused_before_constructing_a_provider(tmp_path,kwargs):
    collector,book,c,calls,closed=fixture(tmp_path)
    collector.reader_factory=lambda:pytest.fail('malformed window reached provider')
    with pytest.raises(ValueError):collector.collect('refused',c,timeframe='M1',**kwargs)
    assert not (tmp_path/'native').exists()


def test_same_original_collection_is_serialized_without_duplicate_native_reads(tmp_path):
    collector,book,c,calls,closed=fixture(tmp_path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        receipts=list(pool.map(lambda _:collector.collect('same-original',c,timeframe='M1',from_ms=120000,to_ms=300000),range(4)))
    assert len(calls)==len(closed)==1 and all(receipt==receipts[0] for receipt in receipts)


def test_native_io_does_not_hold_the_archive_head_writer_or_other_scope_operations(tmp_path):
    collector,book,c,calls,closed=fixture(tmp_path);entered=threading.Event();release=threading.Event()
    original=collector.reader_factory
    class SlowReader(original):
        def read_window(self,*args,**kwargs):
            entered.set();assert release.wait(3)
            return super().read_window(*args,**kwargs)
    collector.reader_factory=SlowReader
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending=pool.submit(collector.collect,'slow-native',c,timeframe='M1',from_ms=120000,to_ms=300000)
        try:
            assert entered.wait(1)
            independent=book.record('independent-capture',c,observation(c))
            assert independent['revision']==1 and not pending.done()
        finally:release.set()
        assert pending.result(timeout=3)['revision']==2


def test_actual_protocol_market_capture_uses_only_selected_product_on_a_separate_connection(tmp_path):
    from test_ctrader import FakeCtrader,make_adapter
    from vati.market_data.native_archive import NativeMarketArchive
    primary=FakeCtrader();adapter=make_adapter(primary)
    end=(28_333_333+3*60)*60000;adapter.clock=lambda:end
    adapter._ensure_auth();expected=adapter.symbol('EURUSD').native_contract
    before=list(primary.requests);peers=[]
    def independent(host,port):
        peer=FakeCtrader();peers.append(peer);return peer.connector(host,port)
    adapter.transport._connector=independent
    book=NativeMarketArchive(tmp_path/'actual',clock=lambda:end+100)
    collector=NativeMarketCollector(book,adapter.market_reader)
    receipt=collector.collect('native-source',expected,timeframe='H1',from_ms=28_333_333*60000,to_ms=end)
    assert adapter.transport.connected and primary.requests==before and len(peers)==1
    names=[name for name,_ in peers[0].requests]
    assert names==['ProtoOAApplicationAuthReq','ProtoOAAccountAuthReq','ProtoOASymbolsListReq',
                  'ProtoOASymbolByIdReq','ProtoOAGetTrendbarsReq']
    assert next(body['symbolId'] for name,body in peers[0].requests if name=='ProtoOASymbolByIdReq')==[1]
    assert peers[0].a.fileno()==-1
    saved=book.snapshot(expected.native_scope,'H1')
    assert len(saved['observation']['bars'])==3 and receipt['available_at_ms']==end+100
    assert saved['contract']['metadata_revision']==expected.revision
    assert not hasattr(adapter.market_reader(),'submit') and not hasattr(adapter.market_reader(),'withdraw')
    adapter.transport.close()


def test_actual_native_contract_change_refuses_before_history_read_or_archive_publication(tmp_path):
    from test_ctrader import FakeCtrader,make_adapter
    from vati.market_data.native_archive import NativeMarketArchive
    primary=FakeCtrader();adapter=make_adapter(primary);adapter._ensure_auth()
    expected=adapter.symbol('EURUSD').native_contract
    class ChangedBroker(FakeCtrader):
        def handle(self,name,body,cid):
            if name=='ProtoOASymbolByIdReq':
                return self.send('ProtoOASymbolByIdRes',{'ctidTraderAccountId':12345,
                    'symbol':[{'symbolId':1,'digits':5,'pipPosition':4,'lotSize':10000000,'minVolume':200000,
                               'stepVolume':100000,'maxVolume':10**10}]},cid)
            return super().handle(name,body,cid)
    changed=ChangedBroker();adapter.transport._connector=changed.connector
    book=NativeMarketArchive(tmp_path/'actual');collector=NativeMarketCollector(book,adapter.market_reader)
    with pytest.raises(VenueUnavailable,match='contract changed'):
        collector.collect('changed-native',expected,timeframe='M1',from_ms=120000,to_ms=300000)
    assert not any(name=='ProtoOAGetTrendbarsReq' for name,_ in changed.requests)
    assert book.lookup(expected.native_scope,'M1','changed-native') is None
    assert changed.a.fileno()==-1 and adapter.transport.connected
    adapter.transport.close()


def test_collector_recovers_a_lost_index_ack_without_native_recollection(tmp_path,monkeypatch):
    collector,book,c,calls,closed=fixture(tmp_path);original=BarLake._atomic_write
    def lost_index(path,payload):
        original(path,payload)
        if path.name!='head.json':raise OSError('fixture record acknowledgement lost')
    with monkeypatch.context() as patch:
        patch.setattr(BarLake,'_atomic_write',lost_index)
        with pytest.raises(NativeArchiveError):collector.collect('original',c,timeframe='M1',from_ms=120000,to_ms=300000)
    before=book.lookup(c.native_scope,'M1','original');assert before['index_state']=='MISSING'
    collector.reader_factory=lambda:pytest.fail('durable original must not reconnect')
    after=collector.collect('original',c,timeframe='M1',from_ms=120000,to_ms=300000)
    assert len(calls)==1 and after['record_ref']==before['record_ref'] and after['index_state']=='CONSISTENT'


def test_index_recovery_requires_actual_durable_index_readback(tmp_path,monkeypatch):
    collector,book,c,calls,closed=fixture(tmp_path);original=BarLake._atomic_write
    def record_only(path,payload):
        if path.name=='head.json':raise OSError('fixture index unavailable')
        original(path,payload)
    with monkeypatch.context() as patch:
        patch.setattr(BarLake,'_atomic_write',record_only)
        with pytest.raises(NativeArchiveError):collector.collect('original',c,timeframe='M1',from_ms=120000,to_ms=300000)
    monkeypatch.setattr(book,'_write_head',lambda *args:None)
    with pytest.raises(NativeArchiveError,match='not confirmed'):
        collector.collect('original',c,timeframe='M1',from_ms=120000,to_ms=300000)
    assert len(calls)==1 and book.lookup(c.native_scope,'M1','original')['index_state']=='MISSING'
