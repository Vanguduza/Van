"""Historical native quote capture, original-policy recovery and cold readback."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
import json
import multiprocessing
import os

import pytest

from test_native_market_archive import contract
from vati.core.canonical import canonical_hash,canonical_json
from vati.execution.ctrader.spots import SpotBook
from vati.market_data.feeds.lake import BarLake
from vati.market_data.native_archive import NativeArchiveError,NativeMarketArchive
from vati.market_data.native_quotes import NativeQuoteCapture,NativeQuoteArchive,NativeQuoteCollector


def sample(c=None,*,now=200000):
    c=c or contract();book=SpotBook()
    book.observe(c,1,{'ctidTraderAccountId':c.native_scope['native_account_id'],
        'symbolId':c.native_scope['native_symbol_id'],'bid':110100,'ask':110108,'timestamp':now},now)
    observed=replace(book.snapshot(c,1,now_ms=now,max_age_ms=5000,subscribed=True),
                     control_state='SUBSCRIBE_ACKNOWLEDGED_QUEUED')
    capacity={'schema':'vati.ctrader-read-capacity/1','state':'WITHIN_LIMIT','max_read_frames':4096,
        'max_read_bytes':16777216,'admitted_frame_headers':5,'reserved_encoded_bytes':256,
        'refused_frame_length':None,
        'accounting_basis':'ADMITTED_PROTOBUF_LENGTH_EXCLUDING_PREFIX_NOT_DECODED_DELIVERY_OR_PROCESS_MEMORY',
        'provider_qualified':False,'authority_effect':'NONE'}
    return NativeQuoteCapture.capture(observed,capacity,max_age_ms=5000)


def archive(tmp_path,now=250000):return NativeQuoteArchive(tmp_path/'quotes',clock=lambda:now)


def test_cold_quote_replay_preserves_original_times_policy_and_unknown_current_freshness(tmp_path):
    c=contract();book=archive(tmp_path);capture=sample(c)
    first=book.record('original',c,capture)
    assert first['state']=='HISTORICAL_QUOTE_CAPTURE_UNQUALIFIED'
    assert first['current_freshness']=='NOT_EVALUATED_HISTORICAL_RECORD'
    assert first['native_bid_time_ms']==200000 and first['available_at_ms']==250000
    cold=archive(tmp_path,now=500000)
    assert cold.record('original',c,capture)==first
    second=cold.record('second',c,sample(c,now=300000))
    assert second['revision']==2
    assert cold.snapshot(c.native_scope,'SPOT',as_of_ms=250000)['receipt']==first
    assert cold.snapshot(c.native_scope,'SPOT',as_of_ms=249999) is None
    assert cold.snapshot(c.native_scope,'SPOT',revision=1)['observation']==capture.body()


@pytest.mark.parametrize('bad',['authority','scope','precision','crossed','stale','native_time','processing',
    'clock_order','age','contract','subscription','control','session','quote_hash','capture_hash',
    'capacity_exhausted','capacity_bool','capacity_empty','capacity_bytes','capacity_totals','policy_bool'])
def test_rehashed_invalid_or_overclaiming_quote_cannot_be_persisted(tmp_path,bad):
    c=contract();capture=sample(c);body=capture.body();q=body['quote'];cap=body['read_capacity']
    if bad=='authority':q['provider_qualified']=True
    elif bad=='scope':q['scope']['native_account_id']=999
    elif bad=='precision':q['bid']='1.101001'
    elif bad=='crossed':q['bid']='2'
    elif bad=='stale':q['evaluated_at_ms']=206000;q['age_ms']=6000
    elif bad=='native_time':q['bid_native_time_ms']=200001
    elif bad=='processing':q['processed_at_ms']=99999
    elif bad=='clock_order':q['evaluated_at_ms']=199999
    elif bad=='age':q['age_ms']=True
    elif bad=='contract':q['contract_revision']='0'*64
    elif bad=='subscription':q['subscription_state']='NOT_ACKNOWLEDGED'
    elif bad=='control':q['control_state']='UNSUBSCRIBE_REQUESTED_UNCONFIRMED'
    elif bad=='session':q['market_session_state']='LIVE'
    elif bad=='capacity_exhausted':cap['state']='EXHAUSTED';cap['refused_frame_length']=100
    elif bad=='capacity_bool':cap['admitted_frame_headers']=True
    elif bad=='capacity_empty':cap['admitted_frame_headers']=0
    elif bad=='capacity_bytes':cap['reserved_encoded_bytes']=16777217
    elif bad=='capacity_totals':cap['reserved_encoded_bytes']=1
    elif bad=='policy_bool':body['max_age_ms']=True
    q['observation_sha256']=canonical_hash({k:v for k,v in q.items() if k!='observation_sha256'})
    if bad=='quote_hash':q['observation_sha256']='0'*64
    body['capture_sha256']=canonical_hash({k:v for k,v in body.items() if k!='capture_sha256'})
    if bad=='capture_hash':body['capture_sha256']='0'*64
    object.__setattr__(capture,'body',lambda:body)
    with pytest.raises(NativeArchiveError):archive(tmp_path).record('refused',c,capture)
    assert not list((tmp_path/'quotes').rglob('*.json'))


@pytest.mark.parametrize('phase',['record','head'])
def test_lost_ack_recovers_original_quote_without_recapturing_or_rewriting(tmp_path,monkeypatch,phase):
    book=archive(tmp_path);c=contract();capture=sample(c);write=BarLake._atomic_write
    def lose_ack(path,payload):
        write(path,payload)
        if (path.name=='head.json')==(phase=='head'):raise OSError('fixture lost native quote ACK')
    with monkeypatch.context() as patch:
        patch.setattr(BarLake,'_atomic_write',lose_ack)
        with pytest.raises(NativeArchiveError,match='ACK'):book.record('original',c,capture)
    paths=list((tmp_path/'quotes').rglob('*-*.json'));assert len(paths)==1
    original=paths[0].read_bytes()
    receipt=archive(tmp_path,now=500000).reconcile(c.native_scope,'SPOT','original')
    assert receipt['revision']==1 and receipt['available_at_ms']==250000
    assert receipt['record_ref']==hashlib.sha256(original).hexdigest() and paths[0].read_bytes()==original


def test_same_quote_request_cannot_change_its_original_policy_or_metadata(tmp_path):
    book=archive(tmp_path);c=contract();first=book.record('original',c,sample(c))
    def forbidden():raise AssertionError('replay attempted another native source read')
    collector=NativeQuoteCollector(book,forbidden)
    assert collector.collect('original',c)==first
    with pytest.raises(NativeArchiveError,match='conflicts'):collector.collect('original',c,max_age_ms=4999)
    changed=contract(detail=dict(c.metadata['detail'],minVolume=2000))
    with pytest.raises(NativeArchiveError,match='conflicts'):collector.collect('original',changed)


def test_quote_cannot_be_available_in_the_archive_before_its_host_evaluation(tmp_path):
    c=contract()
    with pytest.raises(NativeArchiveError):archive(tmp_path,now=199999).record('before-evaluation',c,sample(c))
    assert not list((tmp_path/'quotes').rglob('*.json'))


def test_concurrent_writers_keep_one_original_revision_and_independent_durable_receipt(tmp_path):
    c=contract();capture=sample(c)
    with ThreadPoolExecutor(max_workers=4) as workers:
        receipts=list(workers.map(lambda _:archive(tmp_path).record('same',c,capture),range(8)))
    assert all(receipt==receipts[0] for receipt in receipts)
    assert archive(tmp_path).snapshot(c.native_scope,'SPOT')['receipt']['revision']==1


def test_identical_ticker_in_another_account_has_a_separate_quote_history(tmp_path):
    a=contract();b=contract(account_id=999);book=archive(tmp_path)
    one=book.record('same',a,sample(a));two=book.record('same',b,sample(b))
    assert one['revision']==two['revision']==1 and one['record_ref']!=two['record_ref']
    assert book.snapshot(a.native_scope,'SPOT')['contract']==a.body()
    with pytest.raises(NativeArchiveError):NativeMarketArchive(tmp_path/'quotes').snapshot(a.native_scope,'SPOT')


def test_native_collector_uses_independent_real_socket_and_replays_original_after_cold_restart(tmp_path):
    from test_ctrader import FakeCtrader,make_adapter
    primary=FakeCtrader();adapter=make_adapter(primary);adapter._ensure_auth()
    expected=adapter.symbol('EURUSD').native_contract;before=list(primary.requests);peers=[]
    def independent(host,port):
        native=FakeCtrader();peers.append(native);return native.connector(host,port)
    adapter.transport._connector=independent
    book=archive(tmp_path,now=adapter.clock()+1)
    collector=NativeQuoteCollector(book,adapter.market_reader)
    first=collector.collect('original-native-quote',expected)
    assert primary.requests==before and len(peers)==1
    snapshot=book.snapshot(expected.native_scope,'SPOT')
    assert snapshot['observation']['quote']['bid']=='1.101'
    assert snapshot['observation']['read_capacity']['admitted_frame_headers']>=5
    assert first['provider_qualified'] is False and first['authority_effect']=='NONE'
    assert [name for name,_ in peers[0].requests]==['ProtoOAApplicationAuthReq','ProtoOAAccountAuthReq',
        'ProtoOASymbolsListReq','ProtoOASymbolByIdReq','ProtoOASubscribeSpotsReq']
    def never():raise AssertionError('cold replay opened another native connection')
    cold=NativeQuoteCollector(archive(tmp_path,now=adapter.clock()+10000),never)
    assert cold.collect('original-native-quote',expected)==first


@pytest.mark.parametrize('phase',['record','head'])
def test_native_collector_lost_durable_ack_does_not_open_a_second_source_connection(tmp_path,monkeypatch,phase):
    from test_ctrader import FakeCtrader,make_adapter
    primary=FakeCtrader();adapter=make_adapter(primary);adapter._ensure_auth()
    expected=adapter.symbol('EURUSD').native_contract;peers=[]
    def independent(host,port):
        native=FakeCtrader();peers.append(native);return native.connector(host,port)
    adapter.transport._connector=independent
    book=archive(tmp_path,now=adapter.clock()+1);collector=NativeQuoteCollector(book,adapter.market_reader)
    write=BarLake._atomic_write
    def lose_ack(path,payload):
        write(path,payload)
        if (path.name=='head.json')==(phase=='head'):raise OSError('fixture lost collector durable ACK')
    with monkeypatch.context() as patch:
        patch.setattr(BarLake,'_atomic_write',lose_ack)
        with pytest.raises(NativeArchiveError,match='ACK'):collector.collect('native-original',expected)
    receipt=collector.collect('native-original',expected)
    assert receipt['revision']==1 and receipt['index_state']=='CONSISTENT' and len(peers)==1
    assert book.snapshot(expected.native_scope,'SPOT')['receipt']==receipt


def test_subscription_ack_without_a_native_quote_cannot_create_a_durable_empty_success(tmp_path):
    from test_ctrader import FakeCtrader,make_adapter
    from vati.execution.base import VenueUnavailable
    class NoQuote(FakeCtrader):
        def handle(self,name,body,cid):
            if name=='ProtoOASubscribeSpotsReq':
                return self.send('ProtoOASubscribeSpotsRes',{'ctidTraderAccountId':12345},cid)
            return super().handle(name,body,cid)
    primary=FakeCtrader();adapter=make_adapter(primary);adapter._ensure_auth()
    expected=adapter.symbol('EURUSD').native_contract;peers=[]
    def independent(host,port):
        native=NoQuote();peers.append(native);return native.connector(host,port)
    adapter.transport._connector=independent
    collector=NativeQuoteCollector(archive(tmp_path,now=adapter.clock()+1),
        lambda:adapter.market_reader(collection_timeout_s=.3))
    with pytest.raises(VenueUnavailable):collector.collect('no-delivery',expected)
    assert not list((tmp_path/'quotes').rglob('*.json'))
    assert len(peers)==1
    assert peers[0].requests[-1][0]=='ProtoOASubscribeSpotsReq'
    peers[0].worker.join(1);assert not peers[0].worker.is_alive()


@pytest.mark.parametrize('corruption',['record_bytes','head_hash','missing_tail'])
def test_cold_quote_history_refuses_corruption_instead_of_recapturing(tmp_path,corruption):
    c=contract();book=archive(tmp_path);first=book.record('original',c,sample(c))
    part=book._partition(c.native_scope,'SPOT');path=next(part.glob('00000000000000000001-*.json'))
    if corruption=='record_bytes':path.write_bytes(path.read_bytes()+b' ')
    elif corruption=='missing_tail':path.unlink()
    else:
        head=json.loads((part/'head.json').read_text());head['record_hash']='0'*64
        (part/'head.json').write_text(canonical_json(head))
    def never():raise AssertionError('corrupt original caused a new source read')
    with pytest.raises(NativeArchiveError):NativeQuoteCollector(archive(tmp_path),never).collect('original',c)


def crash_after_quote_record(root):
    write=BarLake._atomic_write
    def commit_then_die(path,payload):
        write(path,payload)
        if path.name!='head.json':os._exit(77)
    BarLake._atomic_write=staticmethod(commit_then_die)
    c=contract();NativeQuoteArchive(root,clock=lambda:250000).record('process-original',c,sample(c))


def test_actual_process_death_recovers_the_durable_original_before_derived_head(tmp_path):
    root=tmp_path/'quotes';ctx=multiprocessing.get_context('spawn')
    child=ctx.Process(target=crash_after_quote_record,args=(str(root),))
    try:
        child.start();child.join(8)
        assert child.exitcode==77,'fixture did not die at the actual durable quote commit point'
    finally:
        if child.pid is not None and child.is_alive():child.terminate();child.join(3)
    c=contract();book=archive(tmp_path);original=book.lookup(c.native_scope,'SPOT','process-original')
    assert original['index_state']=='MISSING' and original['available_at_ms']==250000
    def never():raise AssertionError('process recovery repeated an original native read')
    receipt=NativeQuoteCollector(book,never).collect('process-original',c)
    assert receipt['record_ref']==original['record_ref'] and receipt['index_state']=='CONSISTENT'


def test_concurrent_collectors_use_one_original_native_connection_and_receipt(tmp_path):
    from test_ctrader import FakeCtrader,make_adapter
    primary=FakeCtrader();adapter=make_adapter(primary);adapter._ensure_auth()
    expected=adapter.symbol('EURUSD').native_contract;peers=[]
    def independent(host,port):
        native=FakeCtrader();peers.append(native);return native.connector(host,port)
    adapter.transport._connector=independent
    collector=NativeQuoteCollector(archive(tmp_path,now=adapter.clock()+1),adapter.market_reader)
    with ThreadPoolExecutor(max_workers=4) as workers:
        receipts=list(workers.map(lambda _:collector.collect('one-native-request',expected),range(8)))
    assert len(peers)==1 and all(receipt==receipts[0] for receipt in receipts)
    assert receipts[0]['revision']==1
