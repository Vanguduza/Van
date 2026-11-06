"""Durable original depth, historical policy and uncertain-publication recovery."""
from concurrent.futures import ThreadPoolExecutor
from decimal import localcontext,Inexact,Rounded
import json,multiprocessing,os,threading,time
from pathlib import Path
import pytest

from test_native_market_archive import contract
from test_native_quote_archive import sample as quote_sample
from test_ctrader_native_depth import DepthPeer,change
from test_ctrader import make_adapter
from vati.core.canonical import canonical_hash,canonical_json
from vati.execution.ctrader.depth import DepthBook,DepthObservation
from vati.execution.ctrader.transport import CtraderError
from vati.execution.base import VenueUnavailable
from vati.market_data.feeds.lake import BarLake
from vati.market_data.native_archive import NativeArchiveError
from vati.market_data.native_depth import NativeDepthCapture,NativeDepthArchive,NativeDepthCollector
from vati.market_data.native_quotes import NativeQuoteArchive


def sample(c=None,*,now=200000,limit=100):
    c=c or contract();book=DepthBook();book.observe(c,1,change(c),now)
    observation=book.snapshot(c,1,now_ms=now,max_age_ms=5000,limit=limit,subscribed=True,
        control_state='SUBSCRIBE_ACKNOWLEDGED_QUEUED')
    return NativeDepthCapture.capture(observation,quote_sample(c).body()['read_capacity'],max_age_ms=5000,limit=limit)


def archive(tmp_path,now=250000):return NativeDepthArchive(tmp_path/'depth',clock=lambda:now)


def test_original_depth_cold_readback_revisions_and_asof_keep_native_values_and_historical_policy(tmp_path):
    c=contract();book=archive(tmp_path);capture=sample(c);first=book.record('original',c,capture)
    assert first['state']=='HISTORICAL_PARTIAL_DEPTH_CAPTURE_UNQUALIFIED'
    assert first['current_freshness']=='NOT_EVALUATED_HISTORICAL_RECORD' and first['complete_book'] is False
    cold=archive(tmp_path,now=400000);assert cold.record('original',c,capture)==first
    second=cold.record('second',c,sample(c,now=300000))
    assert second['revision']==2 and second['available_at_ms']==400000
    assert cold.snapshot(c.native_scope,'DEPTH',as_of_ms=250000)['receipt']==first
    assert cold.snapshot(c.native_scope,'DEPTH',as_of_ms=249999) is None
    body=cold.snapshot(c.native_scope,'DEPTH',revision=1)['observation']
    assert body==capture.body() and body['depth']['bids'][0]['native_quote_id']=='9007199254740993'
    assert body['depth']['bids'][0]['native_size_cents']=='12345678901234567890'
    assert body['depth']['price_scale'] is None and body['depth']['normalized_prices_available'] is False


@pytest.mark.parametrize('bad',['authority','complete','false_number','normalized','native_time','sequence','price_scale',
                              'scope','contract','age_bool','age','clock_order','events_bool','count_bool',
                              'side_count','display_limit','truncation_number','side_state','crossed_number',
                              'duplicate','price_float','price_leading_zero','size_overflow','cent_amount',
                              'quote_hash','capture_hash','capacity','capacity_bool','policy_bool'])
def test_rehashed_corrupt_or_overclaiming_depth_is_refused_before_publication(tmp_path,bad):
    c=contract();capture=sample(c);body=capture.body();depth=body['depth']
    if bad=='authority':depth['authority_effect']='ORDER'
    elif bad=='complete':depth['complete_book']=True
    elif bad=='false_number':depth['complete_book']=0
    elif bad=='normalized':depth['normalized_prices_available']=True
    elif bad=='native_time':depth['native_timestamp_ms']=199999
    elif bad=='sequence':depth['native_sequence']=1
    elif bad=='price_scale':depth['price_scale']=5
    elif bad=='scope':depth['scope']['native_account_id']=124
    elif bad=='contract':depth['contract_revision']='0'*64
    elif bad=='age_bool':depth['processing_age_ms']=False
    elif bad=='age':depth['processing_age_ms']=1
    elif bad=='clock_order':depth['processed_at_ms']=99999
    elif bad=='events_bool':depth['native_change_events_processed']=True
    elif bad=='count_bool':depth['observed_quote_count']=True
    elif bad=='side_count':depth['observed_bid_count']=2
    elif bad=='display_limit':depth['display_limit_per_side']=99
    elif bad=='truncation_number':depth['display_truncated']=0
    elif bad=='side_state':depth['side_state']='EMPTY'
    elif bad=='crossed_number':depth['crossed_observed_levels']=0
    elif bad=='duplicate':depth['asks'][0]['native_quote_id']=depth['bids'][0]['native_quote_id']
    elif bad=='price_float':depth['bids'][0]['native_price']=110100.0
    elif bad=='price_leading_zero':depth['bids'][0]['native_price']='0110100'
    elif bad=='size_overflow':depth['bids'][0]['native_size_cents']=str(2**64)
    elif bad=='cent_amount':depth['bids'][0]['native_size']='123.45'
    elif bad=='capacity':body['read_capacity']['state']='EXHAUSTED'
    elif bad=='capacity_bool':body['read_capacity']['admitted_frame_headers']=True
    elif bad=='policy_bool':body['limit']=True
    depth['observation_sha256']=canonical_hash({k:v for k,v in depth.items() if k!='observation_sha256'})
    if bad=='quote_hash':depth['observation_sha256']='0'*64
    body['capture_sha256']=canonical_hash({k:v for k,v in body.items() if k!='capture_sha256'})
    if bad=='capture_hash':body['capture_sha256']='0'*64
    forged=NativeDepthCapture(body['max_age_ms'],body['limit'],canonical_json(depth),canonical_json(body['read_capacity']))
    # Keep an intentionally invalid outer digest visible to the real archive validator.
    if bad=='capture_hash':
        class WrongDigest(NativeDepthCapture):
            def body(self):return body
        forged=WrongDigest(body['max_age_ms'],body['limit'],canonical_json(depth),canonical_json(body['read_capacity']))
    with pytest.raises(NativeArchiveError):archive(tmp_path).record('invalid',c,forged)
    assert not list((tmp_path/'depth').rglob('*.json'))


def test_original_collection_replay_never_reads_native_again_or_changes_capture_policy(tmp_path):
    c=contract();first=archive(tmp_path).record('original',c,sample(c))
    def forbidden():raise AssertionError('original depth replay performed new native I/O')
    collector=NativeDepthCollector(archive(tmp_path,now=500000),forbidden)
    assert collector.collect('original',c)==first
    with pytest.raises(NativeArchiveError,match='conflicts'):collector.collect('original',c,limit=99)
    with pytest.raises(NativeArchiveError,match='conflicts'):collector.collect('original',c,max_age_ms=4999)
    changed=contract(detail=dict(c.metadata['detail'],minVolume=2000))
    with pytest.raises(NativeArchiveError,match='conflicts'):collector.collect('original',changed)


def test_original_raw_depth_remains_exact_under_hostile_caller_arithmetic(tmp_path):
    c=contract();capture=sample(c)
    with localcontext() as ctx:
        ctx.clear_flags();ctx.prec=2;ctx.Emax=2;ctx.Emin=-2;ctx.traps[Inexact]=ctx.traps[Rounded]=True
        receipt=archive(tmp_path).record('original',c,capture)
        assert archive(tmp_path).lookup(c.native_scope,'DEPTH','original')==receipt
        assert not any(ctx.flags.values())


def test_depth_and_spot_share_existing_archive_owner_without_partition_collision(tmp_path):
    c=contract();root=tmp_path/'sources';depth=NativeDepthArchive(root,clock=lambda:250000)
    spot=NativeQuoteArchive(root,clock=lambda:250000)
    a=depth.record('same-request',c,sample(c));b=spot.record('same-request',c,quote_sample(c))
    assert a['record_ref']!=b['record_ref'] and a['timeframe']=='DEPTH' and b['timeframe']=='SPOT'
    assert depth.lookup(c.native_scope,'DEPTH','same-request')==a
    assert spot.lookup(c.native_scope,'SPOT','same-request')==b


def test_pending_empty_subscription_is_not_archived_as_observed_empty_market(tmp_path):
    c=contract();waiting=DepthBook().snapshot(c,1,now_ms=200000,max_age_ms=5000,subscribed=True,
        control_state='SUBSCRIBE_ACKNOWLEDGED_QUEUED')
    capture=NativeDepthCapture.capture(waiting,quote_sample(c).body()['read_capacity'],max_age_ms=5000,limit=100)
    with pytest.raises(NativeArchiveError):archive(tmp_path).record('queued-only',c,capture)


def test_real_record_commit_with_lost_head_ack_recovers_original_without_recapture(tmp_path,monkeypatch):
    c=contract();book=archive(tmp_path);write=BarLake._atomic_write;armed=True
    def lose_head(path,payload):
        nonlocal armed
        if path.name=='head.json' and armed:armed=False;raise OSError('fixture depth index acknowledgement lost')
        return write(path,payload)
    monkeypatch.setattr(BarLake,'_atomic_write',staticmethod(lose_head))
    with pytest.raises(NativeArchiveError):book.record('original',c,sample(c))
    original=book.lookup(c.native_scope,'DEPTH','original');assert original['index_state']=='MISSING'
    def never():raise AssertionError('durable original depth was recaptured')
    recovered=NativeDepthCollector(archive(tmp_path,now=500000),never).collect('original',c)
    assert recovered['record_ref']==original['record_ref'] and recovered['available_at_ms']==250000
    assert recovered['index_state']=='CONSISTENT' and recovered['revision']==1


@pytest.mark.parametrize('bad',['bytes','head','tail'])
def test_cold_corrupt_depth_refuses_without_new_native_read(tmp_path,bad):
    c=contract();book=archive(tmp_path);book.record('original',c,sample(c));part=book._partition(c.native_scope,'DEPTH')
    record=next(part.glob('00000000000000000001-*.json'))
    if bad=='bytes':record.write_bytes(record.read_bytes()+b' ')
    elif bad=='tail':record.unlink()
    else:
        head=json.loads((part/'head.json').read_text());head['record_hash']='0'*64;(part/'head.json').write_text(canonical_json(head))
    def never():raise AssertionError('corrupt depth history was recaptured')
    with pytest.raises(NativeArchiveError):NativeDepthCollector(archive(tmp_path),never).collect('original',c)


def test_concurrent_collection_makes_one_original_native_read_and_revision(tmp_path):
    c=contract();capture=sample(c);gate=threading.Barrier(4);lock=threading.Lock();counts={'reads':0,'closes':0}
    class Reader:
        def read_depth(self,expected,**policy):
            with lock:counts['reads']+=1
            time.sleep(.03)
            return c,DepthObservation(capture.depth_json)
        def close(self):
            with lock:counts['closes']+=1
        def read_capacity_snapshot(self):return json.loads(capture.read_capacity_json)
    def collect(_):
        gate.wait(timeout=5);return NativeDepthCollector(archive(tmp_path),Reader).collect('original',c)
    with ThreadPoolExecutor(max_workers=4) as pool:receipts=list(pool.map(collect,range(4)))
    assert all(receipt==receipts[0] for receipt in receipts) and counts=={'reads':1,'closes':1}
    assert receipts[0]['revision']==1


def crash_after_original_depth_record(root):
    write=BarLake._atomic_write
    def write_then_exit(path,payload):
        if path.name=='head.json':os._exit(0)
        return write(path,payload)
    BarLake._atomic_write=staticmethod(write_then_exit)
    c=contract();NativeDepthArchive(root,clock=lambda:250000).record('process-original',c,sample(c))


def test_actual_child_crash_before_head_publication_reconciles_original_in_a_cold_owner(tmp_path):
    root=tmp_path/'depth';child=multiprocessing.get_context('spawn').Process(target=crash_after_original_depth_record,args=(root,))
    child.start();child.join(15)
    try:
        assert not child.is_alive() and child.exitcode==0
    finally:
        if child.is_alive():child.kill();child.join(5)
        child.close()
    def never():raise AssertionError('child-committed depth was recaptured')
    c=contract();receipt=NativeDepthCollector(NativeDepthArchive(root,clock=lambda:500000),never).collect('process-original',c)
    assert receipt['revision']==1 and receipt['available_at_ms']==250000 and receipt['index_state']=='CONSISTENT'


def test_actual_isolated_native_reader_commits_exact_depth_and_closes_before_publication(tmp_path):
    primary=DepthPeer();adapter=make_adapter(primary);adapter._ensure_auth();expected=adapter.symbol('EURUSD').native_contract
    peers=[]
    def independent(host,port):
        peer=DepthPeer();peers.append(peer);return peer.connector(host,port)
    adapter.transport._connector=independent
    book=archive(tmp_path,now=adapter.clock()+1);collector=NativeDepthCollector(book,adapter.market_reader)
    receipt=collector.collect('actual-native',expected,limit=1)
    assert peers[0].a.fileno()==-1 and len(peers)==1
    assert not any(name=='ProtoOASubscribeDepthQuotesReq' for name,_ in primary.requests)
    stored=book.snapshot(expected.native_scope,'DEPTH')['observation']
    assert stored['depth']['bids'][0]['native_quote_id']=='9007199254740993'
    assert stored['depth']['asks'][0]['native_price']=='110108' and stored['limit']==1
    def never():raise AssertionError('successful original depth capture was repeated')
    assert NativeDepthCollector(archive(tmp_path,now=adapter.clock()+10000),never).collect('actual-native',expected,limit=1)==receipt


def test_absent_native_delivery_closes_source_reader_and_never_publishes_an_empty_success(tmp_path):
    primary=DepthPeer();adapter=make_adapter(primary);adapter._ensure_auth();peers=[]
    def independent(host,port):
        peer=DepthPeer();peer.initial=False;peers.append(peer);return peer.connector(host,port)
    adapter.transport._connector=independent
    collector=NativeDepthCollector(archive(tmp_path,now=adapter.clock()+1),lambda:adapter.market_reader(collection_timeout_s=.5))
    with pytest.raises((VenueUnavailable,CtraderError)):collector.collect('no-delivery',adapter.symbol('EURUSD').native_contract)
    assert len(peers)==1 and peers[0].a.fileno()==-1
    assert not list((tmp_path/'depth').rglob('*.json'))


def test_depth_cannot_be_available_before_its_original_host_evaluation(tmp_path):
    c=contract()
    with pytest.raises(NativeArchiveError):archive(tmp_path,now=199999).record('too-early',c,sample(c))
    assert not list((tmp_path/'depth').rglob('*.json'))


@pytest.mark.parametrize('bad',['foreign-contract','changed-revision','untyped-observation','native-error','capacity-error'])
def test_failed_source_result_is_closed_before_readback_and_never_published(tmp_path,bad):
    c=contract();capture=sample(c)
    class Reader:
        closed=False
        def read_depth(self,expected,**policy):
            if bad=='native-error':raise VenueUnavailable('fixture native depth unavailable')
            actual=contract(account_id=124) if bad=='foreign-contract' else c
            if bad=='changed-revision':actual=contract(detail=dict(c.metadata['detail'],minVolume=2000))
            return actual,{} if bad=='untyped-observation' else DepthObservation(capture.depth_json)
        def close(self):self.closed=True
        def read_capacity_snapshot(self):
            assert self.closed,'source readback occurred before original reader joined'
            if bad=='capacity-error':raise CtraderError('fixture final read-capacity unavailable')
            return json.loads(capture.read_capacity_json)
    reader=Reader();collector=NativeDepthCollector(archive(tmp_path),lambda:reader)
    with pytest.raises((NativeArchiveError,VenueUnavailable,CtraderError)):collector.collect('bad-source',c)
    assert reader.closed is True and not list((tmp_path/'depth').rglob('*.json'))
