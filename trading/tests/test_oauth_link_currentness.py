"""Actual native link writers/registered owner route, injected sockets only."""
import json,time
from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from commander.accounts import AccountControlSettings,build_account_handlers
from commander.app import CommanderSettings,create_app
from commander.auth import sign_headers,HDR_TS,SKEW_S
from test_commander_accounts import FakeDeriv
from vati.accounts import AccountRegistry,Account

class DelayedAuthorization(FakeDeriv):
    def __init__(self):super().__init__();self.after=None
    def recv(self):
        response=super().recv()
        if self.after and self.msgs and 'authorize' in self.msgs[-1]:
            callback,self.after=self.after,None;callback()
        return response


def fixture(tmp_path):
    peer=DelayedAuthorization()
    h=build_account_handlers(AccountControlSettings(str(tmp_path/'accounts.json'),str(tmp_path/'secrets'),
        operation_ledger=str(tmp_path/'native.sqlite'),deriv_connector=peer.connector))
    domain=h['account_revision']({})['account_control_domain']
    version=h['account_revision']({'alias':'linked_once'})['resource_version']
    args={'alias':'linked_once','loginid':'VRTC900','token':'a1-linked','currency':'USD',
        '_expected_resource_version':version,'_expected_account_control_domain':domain,
        '_oauth_link_admission':{'operation_id':'original_link_operation_123456','device_id':'owner-device',
            'account_control_domain':domain,'resource_version':version,'expires_at_unix':int(time.time())+60}}
    return peer,h,args


@pytest.mark.parametrize('change',['expired','namespace','version','authority'])
def test_slow_authorization_cannot_overtake_original_link_currentness(tmp_path,monkeypatch,change):
    import commander.accounts as module
    peer,h,args=fixture(tmp_path)
    if change=='expired':
        peer.after=lambda:monkeypatch.setattr(module,'time',SimpleNamespace(time=lambda:args['_oauth_link_admission']['expires_at_unix']))
    elif change=='namespace':
        peer.after=lambda:(tmp_path/'secrets/.account-control-domain.env').write_text('invalid-owned-namespace')
    elif change=='version':
        peer.after=lambda:AccountRegistry(tmp_path/'accounts.json').add(Account(alias='linked_once',broker='PAPER',mode='DEMO_TRADER',currency='USD'))
    else:
        revoked=[False]
        def guard():
            if revoked[0]:raise HTTPException(401,'owned native authority revoked')
        args['_account_dispatch_guard']=guard;peer.after=lambda:revoked.__setitem__(0,True)
    with pytest.raises(HTTPException):h['deriv_oauth_link'](args)
    assert len([m for m in peer.msgs if 'authorize' in m])==1
    assert not (tmp_path/'secrets/linked_once.env').exists()
    if change=='version':assert AccountRegistry(tmp_path/'accounts.json').get('linked_once').broker=='PAPER'
    else:assert not (tmp_path/'accounts.json').exists()


def test_expiry_before_protected_credentials_preserves_partial_history(tmp_path,monkeypatch):
    import commander.accounts as module
    peer,h,args=fixture(tmp_path);write=module._write_secrets
    def delayed(path,values,**kwargs):
        if 'DERIV_API_TOKEN' in values:
            monkeypatch.setattr(module,'time',SimpleNamespace(time=lambda:args['_oauth_link_admission']['expires_at_unix']))
        return write(path,values,**kwargs)
    monkeypatch.setattr(module,'_write_secrets',delayed)
    with pytest.raises(HTTPException):h['deriv_oauth_link'](args)
    registry=AccountRegistry(tmp_path/'accounts.json')
    assert registry.get('linked_once').login=='VRTC900' and registry.credentials('linked_once')=={}


@pytest.mark.parametrize('change',['key','time'])
def test_actual_registered_signed_owner_rechecked_after_authorize(tmp_path,monkeypatch,change):
    import commander.auth as auth
    peer=DelayedAuthorization();token='owned-current-native-token-'*3
    settings=CommanderSettings(tokens={'van-gateway':token},ledger=str(tmp_path/'native.sqlite'),
        log_dir=str(tmp_path/'log'),units=(),account_control=AccountControlSettings(str(tmp_path/'accounts.json'),
            str(tmp_path/'secrets'),deriv_connector=peer.connector))
    app=create_app(settings)
    with TestClient(app) as client:
        def call(command,args):
            path='/v1/cmd/'+command;body=json.dumps({'args':args}).encode()
            return client.post(path,content=body,headers={**sign_headers(token,'POST',path,body),'content-type':'application/json'})
        version=call('account_revision',{'alias':'linked_once'}).json()['result']['resource_version']
        if change=='key':peer.after=lambda:settings.tokens.__setitem__('van-gateway','replacement-current-key-'*3)
        else:peer.after=lambda:monkeypatch.setattr(auth,'time',SimpleNamespace(time=lambda:time.time()+SKEW_S+1))
        response=call('deriv_oauth_link',{'alias':'linked_once','loginid':'VRTC900','token':'a1-linked','currency':'USD','_expected_resource_version':version})
        assert response.status_code==401,response.text
        assert not (tmp_path/'accounts.json').exists() and not (tmp_path/'secrets/linked_once.env').exists()
        assert len([m for m in peer.msgs if 'authorize' in m])==1


def test_queued_profile_writer_keeps_original_link_and_refuses_stale_preimage(tmp_path,monkeypatch):
    from dataclasses import replace
    from threading import Thread,Event
    peer,h,args=fixture(tmp_path);public=Account.public;writers=[];failures=[]
    attempted=Event();finished=Event()
    def readback(account):
        result=public(account)
        if account.alias=='linked_once' and not writers:
            def edit():
                try:
                    registry=AccountRegistry(tmp_path/'accounts.json');attempted.set()
                    registry.replace(replace(registry.get('linked_once'),label='Newer owner edit'))
                except BaseException as exc:failures.append(exc)
                finally:finished.set()
            writer=Thread(target=edit,daemon=True);writers.append(writer);writer.start()
            assert attempted.wait(timeout=5) and not finished.is_set()
        return result
    monkeypatch.setattr(Account,'public',readback)
    try:result=h['deriv_oauth_link'](args)
    finally:
        for writer in writers:writer.join(timeout=5)
    from vati.accounts.registry import AccountRegistryError
    assert writers and all(not writer.is_alive() for writer in writers)
    assert len(failures)==1 and isinstance(failures[0],AccountRegistryError)
    assert 'changed since read' in str(failures[0])
    registry=AccountRegistry(tmp_path/'accounts.json')
    assert result['account']['label']=='Deriv VRTC900'
    assert registry.get('linked_once').label=='Deriv VRTC900'
    registry.replace(replace(registry.get('linked_once'),label='Newer owner edit'))
    assert registry.get('linked_once').label=='Newer owner edit'
    assert result['account']['label']=='Deriv VRTC900'
    assert registry.credentials('linked_once')['DERIV_API_TOKEN']=='a1-linked'
