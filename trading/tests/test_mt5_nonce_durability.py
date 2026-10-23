"""The same signed native request cannot execute again after worker restart."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import sqlite3
import pytest

from test_mt5_physical_identity import build
from test_mt5_worker import worker_mod,KEY
from vati.execution.mt5_bridge import BridgeRequest,Mt5BridgeClient


def request(signer,nonce=1,issued_ms=1000000):
    return signer.sign(BridgeRequest('order_send',nonce,issued_ms,{'alias':'fx_primary','symbol':'EURUSD',
        'type':'BUY','volume':'0.1','price':'1.1','sl':'1.09','order_type':'MARKET'})).__dict__


def test_independent_native_workers_share_a_durable_single_use_request_identity(tmp_path):
    template,signer,native=build(tmp_path)
    cfg={**template.cfg,'nonce_store':str(tmp_path/'nonces.sqlite')}
    workers=[worker_mod.Worker(cfg,template.t,KEY,clock=lambda:1000000) for _ in range(2)]
    signed=request(signer)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda w:w.handle(signed),workers))
    assert sum(r.get('status')=='FILLED' for r in results)==1 and len(native.sent)==1
    assert workers[1].handle(request(signer,2))['status']=='FILLED' and len(native.sent)==2


def test_actual_native_worker_process_restart_cannot_replay_a_signed_sdk_effect(tmp_path):
    template,_,_=build(tmp_path)
    cfg={**template.cfg,'nonce_store':str(tmp_path/'nonces.sqlite')}
    config=tmp_path/'worker.json';config.write_text(json.dumps(cfg));effects=tmp_path/'sdk-effects'
    code='''
import json,sys
from pathlib import Path
from test_mt5_worker import worker_mod,FakeMt5,KEY
from vati.execution.mt5_bridge import Mt5BridgeClient,BridgeRequest
class SDK(FakeMt5):
 def order_send(self,body):
  with Path(sys.argv[2]).open('a') as f:f.write('SDK effect\\n')
  return super().order_send(body)
worker=worker_mod.Worker(json.loads(Path(sys.argv[1]).read_text()),worker_mod.Terminal(SDK()),KEY,clock=lambda:1000000)
client=Mt5BridgeClient(signing_key=KEY)
request=client.sign(BridgeRequest('order_send',1,1000000,{'alias':'fx_primary','symbol':'EURUSD','type':'BUY','volume':'0.1','price':'1.1','sl':'1.09','order_type':'MARKET'}))
print(json.dumps(worker.handle(request.__dict__)))
'''
    env=dict(os.environ,PYTHONPATH='trading:trading/tests:backend:backend/tests:.')
    responses=[json.loads(subprocess.run([sys.executable,'-c',code,str(config),str(effects)],
        env=env,check=True,capture_output=True,text=True).stdout) for _ in range(2)]
    assert responses[0]['status']=='FILLED'
    assert responses[1].get('status')!='FILLED' and effects.read_text().splitlines()==['SDK effect']


def test_purging_expired_nonce_rows_cannot_resurrect_an_old_request_after_clock_rollback(tmp_path):
    worker,signer,native=build(tmp_path);clock={'now':1000000};worker.clock=lambda:clock['now']
    first=request(signer)
    assert worker.handle(first)['status']=='FILLED'
    clock['now']+=60000
    assert worker.handle(request(signer,2,clock['now']))['status']=='FILLED'
    with sqlite3.connect(worker.nonces.path) as db:
        assert db.execute('SELECT COUNT(*) FROM van_native_nonces').fetchone()[0]==1
    clock['now']=1000000
    refused=worker.handle(first)
    assert 'clock rollback' in refused.get('error','') and len(native.sent)==2


def test_real_native_replay_store_lock_fails_closed_and_recovers_without_dispatch(tmp_path):
    worker,signer,native=build(tmp_path);signed=request(signer)
    with sqlite3.connect(worker.nonces.path) as blocker:
        blocker.execute('BEGIN EXCLUSIVE')
        try:
            refused=worker.handle(signed)
            assert 'store unavailable' in refused.get('error','') and not native.sent
        finally:blocker.rollback()
    assert worker.handle(signed)['status']=='FILLED' and len(native.sent)==1


def test_lost_nonce_commit_ack_cannot_make_the_original_request_fresh_again(tmp_path,monkeypatch):
    worker,signer,native=build(tmp_path);connect=worker.nonces._connect
    class LostAck:
        def __init__(self):self.db=connect()
        def __getattr__(self,name):return getattr(self.db,name)
        def commit(self):
            self.db.commit()
            raise sqlite3.OperationalError('lost nonce commit acknowledgement')
    monkeypatch.setattr(worker.nonces,'_connect',LostAck)
    signed=request(signer)
    assert 'store unavailable' in worker.handle(signed)['error'] and not native.sent
    monkeypatch.setattr(worker.nonces,'_connect',connect)
    assert worker.handle(signed)['error']=='nonce replayed' and not native.sent


def test_default_replay_path_is_derived_from_the_existing_backend_signing_profile(tmp_path):
    template,signer,native=build(tmp_path);cfg=dict(template.cfg);cfg.pop('nonce_store')
    key=tmp_path/'bridge.key';key.write_bytes(KEY);cfg['signing_key_file']=str(key)
    first=worker_mod.Worker(cfg,template.t,KEY,clock=lambda:1000000)
    assert first.handle(request(signer))['status']=='FILLED'
    restarted=worker_mod.Worker(cfg,template.t,KEY,clock=lambda:1000000)
    assert restarted.handle(request(signer)).get('error')=='nonce replayed' and len(native.sent)==1
    assert first.nonces.path==key.with_name('bridge.key.nonces.sqlite3')


def test_a_missing_or_in_memory_nonce_store_never_silently_admits_a_native_worker(tmp_path):
    template,_,_=build(tmp_path);cfg=dict(template.cfg);cfg.pop('nonce_store')
    with pytest.raises(ValueError,match='persistent native nonce store'):
        worker_mod.Worker(cfg,template.t,KEY)
    with pytest.raises(ValueError,match='persistent native nonce store'):
        worker_mod.NonceStore(':memory:')


def test_native_nonce_namespace_rollover_stays_inside_the_uint128_wire_contract(tmp_path):
    worker,client,native=build(tmp_path);client._nonce=2**128-1
    result=client.call('sync_account',{'alias':'fx_primary'},now_ms=1000000)
    assert result.get('account',{}).get('verified') is True
    assert 0<=client.sent[-1].nonce<2**128 and not native.sent


@pytest.mark.parametrize('change',[{'nonce':True},{'nonce':'1'},{'nonce':2**128},
    {'issued_ms':1000000.0},{'body':[]},{'signature':'\u00e9'}])
def test_malformed_native_headers_are_typed_refusals_before_any_sdk_effect(tmp_path,change):
    worker,signer,native=build(tmp_path);signed=request(signer)
    unsigned={**signed,**change}
    if 'signature' not in change:
        unsigned=signer.sign(BridgeRequest(unsigned['op'],unsigned['nonce'],unsigned['issued_ms'],unsigned['body'])).__dict__
    assert 'error' in worker.handle(unsigned) and not native.sent


def test_non_object_native_request_is_refused_without_an_http_handler_exception(tmp_path):
    worker,_,native=build(tmp_path)
    assert 'error' in worker.handle([]) and not native.sent


def test_a_corrupt_persisted_replay_clock_is_not_replaced_with_a_healthy_default(tmp_path):
    worker,signer,native=build(tmp_path)
    assert worker.handle(request(signer))['status']=='FILLED'
    with sqlite3.connect(worker.nonces.path) as db:
        db.execute("UPDATE van_native_replay_clock SET high_water_ms='corrupt' WHERE singleton=1")
    result=worker.handle(request(signer,2))
    assert 'store unavailable' in result['error'] and len(native.sent)==1


def test_a_missing_clock_with_existing_nonce_history_is_not_a_fresh_store(tmp_path):
    worker,signer,native=build(tmp_path)
    assert worker.handle(request(signer))['status']=='FILLED'
    with sqlite3.connect(worker.nonces.path) as db:
        db.execute('DELETE FROM van_native_replay_clock')
    result=worker.handle(request(signer,2))
    assert result.get('error')=='native replay store unavailable' and len(native.sent)==1
