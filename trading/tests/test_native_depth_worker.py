"""Owned framed/SQL-source fixtures; never a provider or hardware qualification."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import json
import multiprocessing
import os
import threading

import pytest

from test_ctrader import make_adapter
from test_ctrader_native_depth import DepthPeer
from vati.accounts.registry import AccountRegistry, Account, BrokerKind, CredentialRef
from vati.accounts.resource_version import resource_snapshot
from vati.core.canonical import canonical_hash
from vati.market_data.native_depth import NativeDepthArchive
from vati.market_data.native_depth_worker import (NativeDepthSourcePolicy, NativeDepthWorker,
    source_profile_ref, poll_depth_capture, stop_depth_capture)
from vati.market_data.feeds.lake import BarLake


@pytest.fixture
def depth_service(tmp_path):
    primary = DepthPeer()
    adapter = make_adapter(primary)
    adapter._ensure_auth()
    contract = adapter.symbol('EURUSD').native_contract
    peers = []
    def connect(host, port):
        peer = DepthPeer()
        peers.append(peer)
        return peer.connector(host, port)
    adapter.transport._connector = connect
    secret = tmp_path/'source.env'
    secret.write_text('CTRADER_CLIENT_ID=app-id\nCTRADER_CLIENT_SECRET=app-secret\nCTRADER_ACCESS_TOKEN=tok\n')
    secret.chmod(0o600)
    registry = AccountRegistry(tmp_path/'accounts.json')
    registry.add(Account(alias='ct_demo', broker=BrokerKind.CTRADER, mode='OBSERVE', currency='USD',
        login='12345', credential_ref=CredentialRef(secrets_file=str(secret))))
    now = [adapter.clock()+1]
    cfg = SimpleNamespace(account_alias='ct_demo', registry_path=str(registry.path), depth_capture=None)
    service = SimpleNamespace(cfg=cfg, adapter=adapter, clock=lambda:now[0], stop_requested=False)
    body = {'schema':'vati.depth-source-policy/1','archive_root':str(tmp_path/'native-sources'),
        'source_profile_ref':source_profile_ref(registry.path,'ct_demo'),
        'resource_version':resource_snapshot(registry,'ct_demo')['resource_version'],
        'config_generation':'a'*64,'queue_capacity':2,'max_history_bytes':1024**2,
        'max_request_bytes':65536,'max_requests':10,'operation_timeout_s':0.2,
        'max_read_frames':100,'max_read_bytes':1024**2,
        'requests':[{'request_id':'original','contract':contract.body(),'contract_ref':canonical_hash(contract.body()),
            'max_age_ms':5000,'limit':1,'not_before_ms':now[0]-1,'expires_at_ms':now[0]+10000}]}
    cfg.depth_capture = body
    service.test = SimpleNamespace(primary=primary, peers=peers, contract=contract, now=now, secret=secret)
    yield service
    stop_depth_capture(service)
    adapter.transport.close()
    owned_peers=[primary,*peers]
    sockets=[peer.a for peer in owned_peers]
    owned_readers=[thread for thread in threading.enumerate()
        if any(arg is sock for arg in getattr(thread,'_args',()) for sock in sockets)]
    for peer in owned_peers:
        for sock in [peer.a,peer.b]:
            try:sock.close()
            except OSError:pass
    owned_threads=[peer.worker for peer in owned_peers]+owned_readers
    for thread in owned_threads:thread.join(timeout=3)
    assert not [thread for thread in owned_threads if thread.is_alive()]


def worker(service, **kwargs):
    return NativeDepthWorker(service, NativeDepthSourcePolicy.parse(service.cfg.depth_capture), **kwargs)


def test_framed_original_commits_and_cold_replay_after_expiry_without_another_native_read(depth_service):
    s=depth_service;w=worker(s);r=s.cfg.depth_capture['requests'][0]
    result=w.capture(r)
    assert result['state']=='CAPTURED',result
    assert len(s.test.peers)==1 and s.test.peers[0].a.fileno()==-1
    assert not any(n=='ProtoOASubscribeDepthQuotesReq' for n,_ in s.test.primary.requests)
    cold=NativeDepthArchive(w.archive.root)
    snapshot=cold.snapshot(s.test.contract.native_scope,'DEPTH',revision=1)
    assert snapshot['receipt']==result['receipt']
    assert snapshot['observation']['depth']['bids'][0]['native_quote_id']=='9007199254740993'
    assert snapshot['observation']['depth']['price_scale'] is None
    assert snapshot['receipt']['provider_qualified'] is False
    s.test.now[0]=r['expires_at_ms']+1
    def never():raise AssertionError('original native read repeated')
    assert worker(s,reader_factory=never).capture(r)==result
    assert cold.request_state(s.test.contract.native_scope,'original',max_bytes=65536)['history'][-1]['state']=='CAPTURED'
    assert not list(cold.root.rglob('*.sqlite'))
    assert 'app-secret' not in ''.join(p.read_text() for p in cold.root.rglob('*.json'))


@pytest.mark.parametrize('change',['body','version','profile','scope','contract_ref','queue','time','frames','bytes','age','limit'])
def test_configuration_and_original_binding_refusals_are_not_new_authority(depth_service,change):
    s=depth_service
    if change in {'body','version','profile','scope'}:
        w=worker(s);r=s.cfg.depth_capture['requests'][0];assert w.capture(r)['state']=='CAPTURED'
        config=deepcopy(s.cfg.depth_capture)
        if change=='body':config['requests'][0]['limit']=2
        elif change=='version':config['resource_version']='b'*64
        elif change=='profile':config['source_profile_ref']='b'*64
        else:
            c=s.test.contract.body();c['metadata']['native_account_id']=5
            with pytest.raises(ValueError):type(s.test.contract).from_body(c)
            return
        s.cfg.depth_capture=config
        with pytest.raises(ValueError):worker(s).capture(config['requests'][0])
        assert len(s.test.peers)==1
        return
    config=deepcopy(s.cfg.depth_capture)
    if change=='contract_ref':config['requests'][0]['contract_ref']='b'*64
    elif change=='queue':config['queue_capacity']=False
    elif change=='time':config['operation_timeout_s']=float('inf')
    elif change=='frames':config['max_read_frames']=0
    elif change=='bytes':config['max_read_bytes']=False
    elif change=='age':config['requests'][0]['max_age_ms']=False
    elif change=='limit':config['requests'][0]['limit']=0
    with pytest.raises(ValueError):NativeDepthSourcePolicy.parse(config)
    assert not s.test.peers


@pytest.mark.parametrize('boundary',['expired','key','profile','contract','stopped','registry_removed','registry_recreated'])
def test_final_after_fsync_currentness_refuses_without_committed_capture(depth_service,monkeypatch,boundary):
    s=depth_service;w=worker(s);r=s.cfg.depth_capture['requests'][0];original=BarLake._atomic_write
    def staged(path,blob,*,before_replace=None):
        if before_replace is not None:
            def late():
                if boundary=='expired':s.test.now[0]=r['expires_at_ms']
                elif boundary=='key':s.test.secret.write_text('ROTATED_KEY=not-an-original-key\n')
                elif boundary=='profile':s.cfg.account_alias='other_alias'
                elif boundary=='contract':s.adapter.symbols['EURUSD'].native_contract=None
                elif boundary in {'registry_removed','registry_recreated'}:
                    registry=AccountRegistry(s.cfg.registry_path);account=registry.get('ct_demo')
                    registry.remove('ct_demo')
                    if boundary=='registry_recreated':registry.add(account)
                else:s.stop_requested=True
                before_replace()
            return original(path,blob,before_replace=late)
        return original(path,blob)
    monkeypatch.setattr(BarLake,'_atomic_write',staged)
    result=w.capture(r)
    assert result['state']=='UNCERTAIN' and result['receipt'] is None
    assert w.archive.lookup(s.test.contract.native_scope,'DEPTH','original') is None
    assert len(s.test.peers)==1 and s.test.peers[0].a.fileno()==-1
    state=w.archive.request_state(s.test.contract.native_scope,'original',max_bytes=65536)
    assert state['history'][-1]['state']=='UNCERTAIN'
    assert not list(w.archive.root.rglob('.lake-*'))
    # Even after restoring current scope, uncertainty cannot recapture.
    s.cfg.account_alias='ct_demo';s.stop_requested=False
    assert worker(s).capture(r)['state']=='UNCERTAIN'
    assert len(s.test.peers)==1


def test_uncommitted_possible_read_reconstruction_does_not_reread(depth_service):
    s=depth_service;w=worker(s);r=s.cfg.depth_capture['requests'][0];scope=s.test.contract.native_scope
    w.archive.prepare_request(scope,'original',w._intent(r),max_bytes=65536,max_requests=10)
    w.archive.advance_request(scope,'original',w._intent(r),'READ_MAY_HAVE_OCCURRED',max_bytes=65536)
    def never():raise AssertionError('uncertain original was read again')
    assert worker(s,reader_factory=never).capture(r)['state']=='UNCERTAIN'
    assert not s.test.peers


def test_lost_index_ack_reconstructs_only_original_record(depth_service,monkeypatch):
    s=depth_service;w=worker(s);r=s.cfg.depth_capture['requests'][0];original=w.archive._write_head
    def lost(*args):raise OSError('injected lost index ACK')
    monkeypatch.setattr(w.archive,'_write_head',lost)
    assert w.capture(r)['state']=='UNCERTAIN'
    def never():raise AssertionError('durable original was recaptured')
    replay=worker(s,reader_factory=never).capture(r)
    assert replay['state']=='CAPTURED' and replay['receipt']['revision']==1
    assert len(s.test.peers)==1


def test_expiry_before_first_reader_is_durable_refusal(depth_service):
    s=depth_service;r=s.cfg.depth_capture['requests'][0];s.test.now[0]=r['expires_at_ms']
    w=worker(s);assert w.capture(r)['state']=='REFUSED';assert not s.test.peers
    s.test.now[0]-=1
    assert worker(s).capture(r)['state']=='REFUSED'


def test_cancelled_active_reader_retains_capacity_until_closed(depth_service):
    s=depth_service;r=s.cfg.depth_capture['requests'][0];entered=threading.Event();release=threading.Event();closed=[]
    class Slow:
        def read_depth(self,*args,**kwargs):
            entered.set();assert release.wait(5);raise OSError('owned unavailable source')
        def close(self):closed.append(True)
    w=worker(s,reader_factory=Slow);s._depth_capture_worker=w;w.start();assert entered.wait(3)
    assert w.close() is False
    assert w.snapshot()['state']=='STOP_PENDING'
    assert poll_depth_capture(s)['state']=='STOP_PENDING'
    release.set();assert w.wait_idle(3)
    assert closed==[True] and w.snapshot()['state']=='STOPPED'
    assert w.snapshot()['requests']['original']['state']=='UNCERTAIN'


def test_real_process_death_after_possible_read_retains_original_unknown(depth_service):
    s=depth_service
    ctx=multiprocessing.get_context('fork')
    def die():
        w=worker(s,reader_factory=lambda:os._exit(73))
        w.capture(s.cfg.depth_capture['requests'][0])
    child=ctx.Process(target=die);child.start();child.join(5)
    if child.is_alive():child.kill();child.join();pytest.fail('owned crash child did not exit')
    assert child.exitcode==73
    assert worker(s).capture(s.cfg.depth_capture['requests'][0])['state']=='UNCERTAIN'
    assert not s.test.peers


def test_generic_atomic_writer_callback_is_optional_and_refusal_preserves_bytes(tmp_path):
    path=tmp_path/'original';BarLake._atomic_write(path,b'original')
    def refuse():raise ValueError('current source retired')
    with pytest.raises(ValueError):BarLake._atomic_write(path,b'replacement',before_replace=refuse)
    assert path.read_bytes()==b'original' and not list(tmp_path.glob('.lake-*'))
    BarLake._atomic_write(path,b'healthy');assert path.read_bytes()==b'healthy'


def test_two_real_processes_arbitrate_one_original_one_native_reader(depth_service):
    s=depth_service;ctx=multiprocessing.get_context('fork');start=ctx.Event();reads=ctx.Value('i',0)
    def capture_original(connection):
        def reader():
            with reads.get_lock():reads.value+=1
            return s.adapter.market_reader(collection_timeout_s=.2,max_read_frames=100,max_read_bytes=1024**2)
        assert start.wait(3)
        connection.send(worker(s,reader_factory=reader).capture(s.cfg.depth_capture['requests'][0]))
        connection.close()
    pipes=[ctx.Pipe(duplex=False) for _ in range(2)]
    children=[ctx.Process(target=capture_original,args=(pair[1],)) for pair in pipes]
    for c in children:c.start()
    start.set()
    try:
        results=[]
        for pair in pipes:
            assert pair[0].poll(8),'owned competing original did not terminate'
            results.append(pair[0].recv())
        for c in children:c.join(3);assert c.exitcode==0
        assert reads.value==1 and results[0]==results[1] and results[0]['state']=='CAPTURED'
        assert NativeDepthArchive(s.cfg.depth_capture['archive_root']).lookup(
            s.test.contract.native_scope,'DEPTH','original')==results[0]['receipt']
    finally:
        for c in children:
            if c.is_alive():c.kill();c.join()
        for pair in pipes:
            for endpoint in pair:endpoint.close()


@pytest.mark.parametrize('phase',['after_read','after_record','after_index'])
def test_real_process_death_recovers_only_actual_original_bytes(depth_service,phase):
    s=depth_service;ctx=multiprocessing.get_context('fork')
    def crash():
        w=worker(s)
        if phase=='after_read':
            original=w._factory
            def make():
                reader=original();read=reader.read_depth
                def lose(*args,**kwargs):
                    read(*args,**kwargs);reader.close();os._exit(73)
                reader.read_depth=lose
                return reader
            w._factory=make
        elif phase=='after_record':
            original=BarLake._atomic_write
            def write(path,blob,*,before_replace=None):
                original(path,blob,before_replace=before_replace)
                if before_replace is not None:os._exit(73)
            BarLake._atomic_write=write
        else:
            original=w.archive._write_head
            def write(*args):original(*args);os._exit(73)
            w.archive._write_head=write
        w.capture(s.cfg.depth_capture['requests'][0])
    child=ctx.Process(target=crash);child.start();child.join(8)
    if child.is_alive():child.kill();child.join();pytest.fail('owned crash child exceeded boundary')
    assert child.exitcode==73
    def never():raise AssertionError('original uncertainty or archive was recaptured')
    result=worker(s,reader_factory=never).capture(s.cfg.depth_capture['requests'][0])
    if phase=='after_read':assert result['state']=='UNCERTAIN' and result['receipt'] is None
    else:
        assert result['state']=='CAPTURED' and result['receipt']['revision']==1
        assert result['receipt']['index_state']=='CONSISTENT'
    assert not s.test.peers


def test_source_read_slot_wait_rechecks_expiry_before_any_reader(depth_service):
    from vati.core.file_lock import exclusive_state_lock
    s=depth_service;w=worker(s);r=s.cfg.depth_capture['requests'][0]
    scope={k:v for k,v in s.test.contract.native_scope.items() if k!='native_symbol_id'}
    slot=w.archive.root/('depth-reader-'+canonical_hash(scope))
    ctx=multiprocessing.get_context('fork');entered=ctx.Event();release=ctx.Event()
    def hold():
        with exclusive_state_lock(slot):entered.set();assert release.wait(8)
    child=ctx.Process(target=hold);child.start();assert entered.wait(3)
    outcomes=[];thread=threading.Thread(target=lambda:outcomes.append(w.capture(r)))
    thread.start()
    try:
        s.test.now[0]=r['expires_at_ms'];release.set();child.join(3);thread.join(3)
        assert child.exitcode==0 and not thread.is_alive()
        assert outcomes[0]['state']=='REFUSED' and not s.test.peers
    finally:
        release.set()
        if child.is_alive():child.kill();child.join()
        thread.join(3)


@pytest.mark.parametrize('corrupt',['task','record','index'])
def test_corrupt_original_state_never_recaptures_native(depth_service,corrupt):
    s=depth_service;w=worker(s);r=s.cfg.depth_capture['requests'][0]
    assert w.capture(r)['state']=='CAPTURED'
    if corrupt=='task':path=w.archive._request_file(s.test.contract.native_scope,'original')
    elif corrupt=='record':path=next(w.archive.root.rglob('00000000000000000001-*.json'))
    else:path=next(w.archive.root.rglob('head.json'))
    path.write_text('{broken')
    def never():raise AssertionError('corrupt original triggered recapture')
    if corrupt=='index':
        # Original immutable bytes can repair a derived index, never substitute
        # a new sample. Corrupt originals/tasks themselves always HOLD.
        try:result=worker(s,reader_factory=never).capture(r)
        except ValueError:pass
        else:assert result['state']=='CAPTURED'
    else:
        with pytest.raises(ValueError):worker(s,reader_factory=never).capture(r)
    assert len(s.test.peers)==1


def test_only_explicit_new_request_can_sample_after_uncertainty(depth_service):
    s=depth_service;w=worker(s);r=s.cfg.depth_capture['requests'][0]
    w.archive.prepare_request(s.test.contract.native_scope,'original',w._intent(r),max_bytes=65536,max_requests=10)
    w.archive.advance_request(s.test.contract.native_scope,'original',w._intent(r),'READ_MAY_HAVE_OCCURRED',max_bytes=65536)
    assert w.capture(r)['state']=='UNCERTAIN'
    config=deepcopy(s.cfg.depth_capture);new=deepcopy(r);new['request_id']='explicit-second'
    config['requests'].append(new);s.cfg.depth_capture=config
    current=worker(s)
    assert current.capture(new)['state']=='CAPTURED' and len(s.test.peers)==1
    assert current.capture(r)['state']=='UNCERTAIN' and len(s.test.peers)==1
