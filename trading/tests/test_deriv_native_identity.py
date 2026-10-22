"""Real production factory + native websocket protocol, isolated provider frames."""
from dataclasses import replace
from decimal import Decimal as D
import json

import pytest

from test_account_lifecycle import _command
from vati.accounts import Account, AccountRegistry, CredentialRef
from vati.app.service import build_adapter
from vati.execution.transports import deriv_ws
from vati.risk.contracts import LossModel


class Socket:
    def __init__(self,profile):
        self.profile=profile;self.frames=[];self.requests=[]
    def send(self,raw):
        request=json.loads(raw);self.requests.append(request);rid=request['req_id']
        if 'authorize' in request:
            result={'authorize':self.profile}
        elif 'proposal' in request:
            result={'proposal':{'id':'fixture-proposal'}}
        elif 'buy' in request:
            result={'buy':{'buy_price':'25','contract_id':77,'transaction_id':5,'purchase_time':1}}
        elif 'portfolio' in request:
            result={'portfolio':{'contracts':[]}}
        else:
            result={'ping':'pong'}
        self.frames.append(json.dumps({'req_id':rid,**result}))
    def recv(self):
        return self.frames.pop(0)
    def close(self):
        pass


def factory(tmp_path,monkeypatch,profile,*,mode='DEMO_TRADER'):
    path=tmp_path/'accounts.json';registry=AccountRegistry(path)
    account=registry.add(Account(alias='bound_demo',broker='DERIV',mode=mode,currency='USD',
        login='VRTC900',server='1089',credential_ref=CredentialRef(env_var='VAN_NATIVE_DERIV_FIXTURE')))
    monkeypatch.setenv('VAN_NATIVE_DERIV_FIXTURE','fixture-token')
    sockets=[];real=deriv_ws.DerivWebSocketTransport
    def configured(**kwargs):
        def connector(url):
            socket=Socket(profile);sockets.append(socket);return socket
        return real(**kwargs,connector=connector)
    monkeypatch.setattr(deriv_ws,'DerivWebSocketTransport',configured)
    return build_adapter(account,registry),sockets,registry


def native(**patch):
    return {'loginid':'VRTC900','is_virtual':1,'currency':'USD','balance':'10000','scopes':['read','trade'],**patch}


def command():
    return replace(_command('native-bound'),account_alias='bound_demo',venue='deriv',symbol='frxEURUSD',
        entry_type='CONTRACT_BUY',loss_model=LossModel.FULL_STAKE,quantity=D('25'),command_hash='').sealed()


@pytest.mark.parametrize('patch',[{'loginid':'CR777','is_virtual':0},{'loginid':'VRTC999'},
    {'is_virtual':0},{'currency':'EUR'},{'scopes':['read']},{'is_virtual':None}])
def test_factory_does_not_verify_an_unproven_or_incompatible_native_account(tmp_path,monkeypatch,patch):
    adapter,_,_=factory(tmp_path,monkeypatch,native(**patch))
    assert adapter.sync_account().verified is False


@pytest.mark.parametrize('patch',[{'loginid':'CR777','is_virtual':0},{'loginid':'VRTC999'},
    {'is_virtual':0},{'currency':'EUR'},{'scopes':['read']},{'is_virtual':None}])
def test_an_incompatible_profile_cannot_reach_native_buy(tmp_path,monkeypatch,patch):
    adapter,sockets,_=factory(tmp_path,monkeypatch,native(**patch))
    adapter.sync_account()
    result=adapter.submit(command(),now_ms=1000)
    assert result.status=='REJECTED'
    assert not any('buy' in request for socket in sockets for request in socket.requests)


def test_the_matching_native_profile_retains_the_entry_path(tmp_path,monkeypatch):
    adapter,sockets,_=factory(tmp_path,monkeypatch,native())
    assert adapter.sync_account().verified is True
    assert adapter.submit(command(),now_ms=1000).status=='FILLED'
    assert sum('buy' in request for socket in sockets for request in socket.requests)==1


def test_readonly_local_mode_cannot_be_widened_by_a_trade_capable_token(tmp_path,monkeypatch):
    adapter,sockets,_=factory(tmp_path,monkeypatch,native(),mode='OBSERVE')
    adapter.sync_account()
    assert adapter.submit(command(),now_ms=1000).status=='REJECTED'
    assert not any('buy' in request for socket in sockets for request in socket.requests)


@pytest.mark.parametrize('patch',[{'loginid':'VRTC999'},{'is_virtual':0},{'scopes':['read']}])
def test_reconnected_socket_must_prove_its_own_identity(tmp_path,monkeypatch,patch):
    profile=native();adapter,sockets,_=factory(tmp_path,monkeypatch,profile)
    assert adapter.sync_account().verified
    adapter.transport.close();profile.update(patch)
    assert adapter.submit(command(),now_ms=1000).status=='REJECTED'
    assert len(sockets)==2
    assert not any('buy' in request for socket in sockets for request in socket.requests)


def test_good_reconnection_authorizes_before_private_portfolio(tmp_path,monkeypatch):
    adapter,sockets,_=factory(tmp_path,monkeypatch,native())
    assert adapter.sync_account().verified
    adapter.transport.close()
    assert adapter.positions()==[]
    assert [next(k for k in r if k!='req_id') for r in sockets[-1].requests]==['authorize','portfolio']


def test_rotated_token_is_reauthorized_even_on_an_open_socket(tmp_path,monkeypatch):
    profile=native();adapter,sockets,_=factory(tmp_path,monkeypatch,profile)
    assert adapter.sync_account().verified
    profile['loginid']='VRTC999'
    monkeypatch.setenv('VAN_NATIVE_DERIV_FIXTURE','fixture-other-token')
    assert adapter.submit(command(),now_ms=1000).status=='REJECTED'
    requests=sockets[0].requests
    assert sum('authorize' in r for r in requests)==2
    assert not any('buy' in r for r in requests)


@pytest.mark.parametrize('change',[{'mode':'OBSERVE'},{'mode':'SHADOW_TRADER'},{'enabled':False},
    {'login':'VRTC999'},{'currency':'EUR'},{'server':'999'},{'demo':False}])
def test_existing_connection_respects_current_registry_entry_ceiling(tmp_path,monkeypatch,change):
    adapter,sockets,registry=factory(tmp_path,monkeypatch,native())
    assert adapter.sync_account().verified
    current=AccountRegistry(registry.path)
    current.replace(replace(current.get('bound_demo'),**change))
    assert adapter.submit(command(),now_ms=1000).status=='REJECTED'
    assert not any('buy' in r for socket in sockets for r in socket.requests)


def test_entry_disable_keeps_native_protective_portfolio_available(tmp_path,monkeypatch):
    adapter,_,registry=factory(tmp_path,monkeypatch,native())
    assert adapter.sync_account().verified
    current=AccountRegistry(registry.path)
    current.replace(replace(current.get('bound_demo'),enabled=False,mode='OBSERVE'))
    assert adapter.positions()==[]


@pytest.mark.parametrize('field,value',[('account_alias','other_alias'),('venue','paper')])
def test_command_binding_cannot_target_a_different_account(tmp_path,monkeypatch,field,value):
    adapter,sockets,_=factory(tmp_path,monkeypatch,native())
    changed=replace(command(),**{field:value,'command_hash':''}).sealed()
    assert adapter.submit(changed,now_ms=1000).status=='REJECTED'
    assert sockets==[]


def test_money_is_parsed_without_a_binary_float_roundtrip(tmp_path,monkeypatch):
    adapter,sockets,_=factory(tmp_path,monkeypatch,native())
    original=Socket.recv
    def native_number(self):
        return original(self).replace('"10000"','10000.00000000000000000001')
    monkeypatch.setattr(Socket,'recv',native_number)
    assert adapter.sync_account().balance==D('10000.00000000000000000001')


def test_missing_registry_refuses_entry_from_a_cached_connection(tmp_path,monkeypatch):
    adapter,sockets,registry=factory(tmp_path,monkeypatch,native())
    assert adapter.sync_account().verified
    registry.path.unlink()
    assert adapter.submit(command(),now_ms=1000).status=='REJECTED'
    assert not any('buy' in r for socket in sockets for r in socket.requests)


def test_lost_buy_response_is_not_replayed_on_a_new_socket(tmp_path,monkeypatch):
    from vati.execution.base import VenueUnavailable
    adapter,sockets,_=factory(tmp_path,monkeypatch,native())
    original=Socket.recv
    def lost(self):
        if self.requests and 'buy' in self.requests[-1]:
            raise TimeoutError('fixture private detail that must not escape')
        return original(self)
    monkeypatch.setattr(Socket,'recv',lost)
    with pytest.raises(VenueUnavailable,match='reconcile') as exc:
        adapter.submit(command(),now_ms=1000)
    assert 'private detail' not in str(exc.value)
    assert sum('buy' in r for socket in sockets for r in socket.requests)==1
    assert adapter.transport.authorized_loginid is None
    assert adapter.positions()==[]
    assert len(sockets)==2
    assert sum('buy' in r for socket in sockets for r in socket.requests)==1


def test_account_mutation_cannot_overtake_checked_native_buy(tmp_path,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    entered=threading.Event();release=threading.Event();mutation_started=threading.Event();mutated=threading.Event()
    adapter,sockets,registry=factory(tmp_path,monkeypatch,native())
    original=Socket.send
    def waiting(self,raw):
        if 'buy' in json.loads(raw):
            entered.set();assert release.wait(5)
        return original(self,raw)
    monkeypatch.setattr(Socket,'send',waiting)
    def disable():
        current=AccountRegistry(registry.path);mutation_started.set()
        try:
            current.replace(replace(current.get('bound_demo'),enabled=False))
        finally:
            mutated.set()
    with ThreadPoolExecutor(max_workers=2) as pool:
        effect=pool.submit(adapter.submit,command(),now_ms=1000)
        assert entered.wait(5)
        mutation=pool.submit(disable);assert mutation_started.wait(5)
        try:
            assert not mutated.wait(0.15), "registry mutation overtook the in-flight native send"
        finally:
            release.set()
        assert effect.result(5).status=='FILLED'
        mutation.result(5)
    assert adapter.submit(command(),now_ms=1001).status=='REJECTED'
    assert sum('buy' in r for socket in sockets for r in socket.requests)==1


def test_failed_native_identity_readback_never_becomes_an_empty_portfolio(tmp_path,monkeypatch):
    from vati.execution.base import VenueUnavailable
    adapter,sockets,_=factory(tmp_path,monkeypatch,native(loginid='VRTC999'))
    with pytest.raises(VenueUnavailable,match='exposure must be reconciled'):
        adapter.positions()
    assert not any('portfolio' in r for socket in sockets for r in socket.requests)


@pytest.mark.parametrize('patch',[{'balance':'NaN'},{'balance':'Infinity'},{'balance':None},
    {'scopes':None},{'is_virtual':True},{'is_virtual':'1'},{'currency':''},{'loginid':''}])
def test_incomplete_or_ambiguous_native_identity_is_not_verified(tmp_path,monkeypatch,patch):
    adapter,_,_=factory(tmp_path,monkeypatch,native(**patch))
    assert adapter.sync_account().verified is False
