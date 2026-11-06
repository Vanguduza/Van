"""Actual HMAC poll + native queue + factory binding; no real MT5 terminal is claimed."""
from dataclasses import replace
from decimal import Decimal as D
import json

from fastapi.testclient import TestClient
import pytest

from test_mt5_worker import KEY
from vati.accounts import Account,AccountRegistry,CredentialRef
from vati.app.service import build_adapter
from vati.execution.base import OrderCommand,StopMode,VenueUnavailable
from vati.execution.mt5_pull import BridgeQueue,create_pull_app,key_provider_from_registry,sign_poll
from vati.risk.contracts import Direction,LossModel


@pytest.fixture
def rig(tmp_path):
    secret=tmp_path/'fixture.env';queue_path=tmp_path/'queue.sqlite'
    secret.write_text('BRIDGE_SIGNING_KEY='+KEY.decode()+'\nBRIDGE_QUEUE='+str(queue_path)+'\n');secret.chmod(0o600)
    registry=AccountRegistry(tmp_path/'accounts.json')
    account=registry.add(Account(alias='bound_ea',broker='MT5_EA',mode='DEMO_TRADER',currency='USD',
        server='Broker|Demo香港',login='12345678',credential_ref=CredentialRef(secrets_file=str(secret))))
    queue=BridgeQueue(queue_path);provider=key_provider_from_registry(str(registry.path));clock={'now':1000000}
    app=create_pull_app(queue,provider,clock=lambda:clock['now'])
    native={'login':12345678,'server':account.server,'currency':'USD','demo':True,
        'equity':'10000','balance':'10000','trade_allowed':True,'hedging':True,'server_time_ms':clock['now']}
    adapter=build_adapter(account,registry);adapter.clock=lambda:clock['now'];adapter.timeout_s=0
    command=OrderCommand('native-original','d'*64,'native-original',account.alias,'mt5','EURUSD',Direction.LONG,
        'MARKET',D('0.1'),D('1.1'),D('1.09'),StopMode.VENUE,LossModel.STOP_DISTANCE).sealed()
    with TestClient(app) as client:
        nonce={'value':0}
        def poll(**changes):
            nonce['value']+=1
            body=json.dumps({'account':native,'positions':[],'results':[],**changes}).encode()
            ts=str(clock['now']//1000);n='n'+str(nonce['value'])
            return client.post('/ea/v1/'+account.alias+'/poll',content=body,headers={
                'x-van-ts':ts,'x-van-nonce':n,'x-van-signature':sign_poll(KEY,ts,n,account.alias,body),
                'content-type':'application/json'})
        assert poll().status_code==200 and adapter.sync_account().verified
        yield registry,account,queue,provider,adapter,command,poll,clock,native
    adapter.queue.close();queue.close()


def test_matching_factory_claim_roundtrips_the_bound_wire_and_original_result(rig):
    reg,account,queue,provider,adapter,command,poll,clock,native=rig
    receipt=adapter.submit(command,now_ms=clock['now']);assert receipt.status=='UNKNOWN'
    response=poll();assert response.status_code==200
    fields=response.text.strip().split('|');assert len(fields)==17
    assert fields[12:] == ['MARKET',account.login,account.server.encode().hex(),'USD'.encode().hex(),'true']
    cid=int(fields[0]);assert queue.result(cid) is None
    result={'id':cid,'status':'FILLED','volume':'0.1','price':'1.1','position':'700','order':'700','sl_confirmed':True}
    assert poll(results=[result]).status_code==200
    assert adapter.recover_entry(command,now_ms=clock['now']).status=='FILLED'
    clock['now']+=60000  # historical original result does not require a fresh quote/account snapshot
    assert adapter.recover_entry(command,now_ms=clock['now']).status=='FILLED'
    with pytest.raises(VenueUnavailable,match='stale'):adapter.positions()
    with pytest.raises(VenueUnavailable,match='stale'):adapter.sync_account()
    assert len(queue.native_entries(account.alias))==1


@pytest.mark.parametrize('field,value',[('login',999),('server','Other'),('currency','EUR'),('demo',False)])
def test_validly_signed_foreign_physical_snapshot_cannot_take_a_queued_original(rig,field,value):
    reg,account,queue,provider,adapter,command,poll,clock,native=rig
    assert adapter.submit(command,now_ms=clock['now']).status=='UNKNOWN'
    foreign={**native,field:value};response=poll(account=foreign)
    assert response.status_code==409 and not response.text.startswith('1|')
    rows=queue.native_entries(account.alias);assert len(rows)==1 and rows[0]['status']=='QUEUED'
    assert rows[0]['result'] is None and queue.state(account.alias)['account']==native


def test_current_disable_refuses_only_queued_entries_with_zero_native_effect(rig):
    reg,account,queue,provider,adapter,command,poll,clock,native=rig
    assert adapter.submit(command,now_ms=clock['now']).status=='UNKNOWN'
    reg.replace(replace(account,enabled=False))
    response=poll();assert response.status_code==200 and response.text==''
    original=adapter.recover_entry(command,now_ms=clock['now'])
    assert original.status=='REJECTED' and original.filled_qty==0
    assert queue.native_entries(account.alias)[0]['status']=='DONE'


def test_disable_after_delivery_cannot_turn_an_unknown_native_effect_into_a_refusal(rig):
    reg,account,queue,provider,adapter,command,poll,clock,native=rig
    assert adapter.submit(command,now_ms=clock['now']).status=='UNKNOWN'
    assert poll().text.strip().split('|')[1]=='ORDER_SEND'
    reg.replace(replace(account,enabled=False))
    assert poll().text==''
    assert adapter.recover_entry(command,now_ms=clock['now']).status=='UNKNOWN'
    assert queue.native_entries(account.alias)[0]['status']=='TAKEN'


def test_permission_is_reloaded_after_receiving_the_signed_poll_body(rig,monkeypatch):
    reg,account,queue,provider,adapter,command,poll,clock,native=rig
    assert adapter.submit(command,now_ms=clock['now']).status=='UNKNOWN'
    import vati.execution.mt5_pull as pull
    compare=pull.hmac.compare_digest;changed={'value':False}
    def verify_then_disable(left,right):
        verified=compare(left,right)
        if verified and isinstance(left,str) and len(left)==64 and not changed['value']:
            reg.replace(replace(account,enabled=False));changed['value']=True
        return verified
    monkeypatch.setattr(pull.hmac,'compare_digest',verify_then_disable)
    response=poll();assert response.status_code==200 and response.text==''
    assert changed['value'] and queue.native_entries(account.alias)[0]['result']['status']=='REJECTED'


@pytest.mark.parametrize('bad', [{'account':[]},{'positions':{}},{'results':None}])
def test_malformed_native_poll_body_is_a_closed_client_error_before_queue_delivery(rig,bad):
    reg,account,queue,provider,adapter,command,poll,clock,native=rig
    assert adapter.submit(command,now_ms=clock['now']).status=='UNKNOWN'
    response=poll(**bad);assert response.status_code==400
    assert queue.native_entries(account.alias)[0]['status']=='QUEUED'


def test_a_queued_original_cannot_migrate_to_the_alias_new_physical_account(rig):
    reg,account,queue,provider,adapter,command,poll,clock,native=rig
    assert adapter.submit(command,now_ms=clock['now']).status=='UNKNOWN'
    reg.replace(replace(account,server='Other-Server'))
    response=poll(account={**native,'server':'Other-Server'})
    assert response.status_code==200 and response.text==''
    assert adapter.recover_entry(command,now_ms=clock['now']).status=='REJECTED'
    assert queue.native_entries(account.alias)[0]['result']['volume']=='0'


def test_a_taken_original_does_not_become_no_effect_after_a_physical_migration(rig):
    reg,account,queue,provider,adapter,command,poll,clock,native=rig
    assert adapter.submit(command,now_ms=clock['now']).status=='UNKNOWN'
    assert poll().text
    reg.replace(replace(account,server='Other-Server'))
    assert poll(account={**native,'server':'Other-Server'}).text==''
    assert adapter.recover_entry(command,now_ms=clock['now']).status=='UNKNOWN'
    assert queue.native_entries(account.alias)[0]['status']=='TAKEN'


def test_explicit_entry_type_is_independent_of_the_original_intent_label(rig):
    reg,account,queue,provider,adapter,command,poll,clock,native=rig
    command=replace(command,trade_intent_id='native-LIMIT-label',command_hash='').sealed()
    assert adapter.submit(command,now_ms=clock['now']).status=='UNKNOWN'
    fields=poll().text.strip().split('|')
    assert fields[9]=='vati:native-LIMIT-label' and fields[12]=='MARKET'


def test_key_rotation_after_authentication_blocks_the_old_poll_before_any_native_delivery(rig,monkeypatch):
    import vati.execution.mt5_pull as pull
    from pathlib import Path
    reg,account,queue,provider,adapter,command,poll,clock,native=rig
    assert adapter.submit(command,now_ms=clock['now']).status=='UNKNOWN'
    compare=pull.hmac.compare_digest;changed={'value':False}
    def verify_then_rotate(left,right):
        verified=compare(left,right)
        if verified and isinstance(left,str) and len(left)==64 and not changed['value']:
            with reg.operation_lock(account.alias):
                Path(account.credential_ref.secrets_file).write_text('BRIDGE_SIGNING_KEY='+'z'*32+'\n')
                reg.touch(account.alias)
            changed['value']=True
        return verified
    monkeypatch.setattr(pull.hmac,'compare_digest',verify_then_rotate)
    response=poll();assert changed['value'] and response.status_code==409
    assert queue.native_entries(account.alias)[0]['status']=='QUEUED'
