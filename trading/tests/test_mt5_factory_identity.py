"""Factory reads must verify the registered native identity, not just a friendly alias."""
from dataclasses import replace
from decimal import Decimal as D

import pytest

from test_mt5_worker import make_worker,KEY
from vati.accounts import Account,AccountRegistry,CredentialRef
from vati.app.service import build_adapter
from vati.execution.base import VenueUnavailable
from vati.execution.mt5_pull import BridgeQueue


@pytest.mark.parametrize('route',['MT5','MT5_EA'])
@pytest.mark.parametrize('field,value',[('login','999999'),('server','Other-Server'),('currency','EUR'),('demo',False)])
def test_an_actual_factory_cannot_verify_a_different_physical_account(tmp_path,monkeypatch,route,field,value):
    registry=AccountRegistry(tmp_path/'accounts.json')
    account=Account(alias='fx_primary',broker=route,mode='OBSERVE',currency='USD',login='12345678',server='Broker-Demo',
        credential_ref=CredentialRef(env_var='SOURCE_FIXTURE_NOT_READ'))
    account=registry.add(replace(account,**{field:value}))
    monkeypatch.setattr(registry,'credentials',lambda alias:{'BRIDGE_SIGNING_KEY':KEY.decode(),'BRIDGE_CA_FILE':'source-fixture-ca'})
    if route=='MT5':
        import vati.execution.transports.mt5_http as transport
        worker,_=make_worker(tmp_path,lambda:1000000)
        monkeypatch.setattr(transport,'Mt5HttpTransport',lambda *args,**kwargs:worker.handle)
    else:
        import vati.execution.mt5_pull as pull
        queue=BridgeQueue(tmp_path/'queue.sqlite')
        queue.set_state(account.alias,{'login':12345678,'server':'Broker-Demo','demo':True,
            'equity':'10000','balance':'10000','currency':'USD','hedging':True,'trade_allowed':True,'server_time_ms':1000000},[],now_ms=1000000,nonce='first')
        monkeypatch.setattr(pull,'open_bridge_queue',lambda *args:queue)
    adapter=build_adapter(account,registry);adapter.clock=lambda:1000000
    try:
        with pytest.raises(VenueUnavailable,match='identity|account|binding'):
            state=adapter.sync_account()
            assert state.verified is True
    finally:
        if route=='MT5_EA':queue.close()


def test_matching_push_factory_reaches_the_real_signed_worker_and_preserves_native_protection(tmp_path,monkeypatch):
    from vati.execution.base import OrderCommand,StopMode
    from vati.risk.contracts import Direction,LossModel
    import vati.execution.transports.mt5_http as transport
    registry=AccountRegistry(tmp_path/'accounts.json')
    account=registry.add(Account(alias='fx_primary',broker='MT5',mode='DEMO_TRADER',currency='USD',login='12345678',server='Broker-Demo',
        credential_ref=CredentialRef(env_var='SOURCE_FIXTURE_NOT_READ')))
    monkeypatch.setattr(registry,'credentials',lambda alias:{'BRIDGE_SIGNING_KEY':KEY.decode(),'BRIDGE_CA_FILE':'source-fixture-ca'})
    worker,_=make_worker(tmp_path,lambda:1000000)
    monkeypatch.setattr(transport,'Mt5HttpTransport',lambda *args,**kwargs:worker.handle)
    adapter=build_adapter(account,registry);adapter.clock=lambda:1000000
    assert adapter.sync_account().verified and adapter.heartbeat(now_ms=1000000).connected
    cmd=OrderCommand('factory-entry','d'*64,'factory-key',account.alias,'mt5','EURUSD',Direction.LONG,'MARKET',
        D('0.1'),D('1.10008'),D('1.09'),StopMode.VENUE,LossModel.STOP_DISTANCE).sealed()
    receipt=adapter.submit(cmd,now_ms=1000000)
    assert receipt.status=='FILLED' and receipt.protective_stop_confirmed
    assert len(worker.t.mt5.sent)==1 and adapter.positions()[0].trade_intent_id==cmd.trade_intent_id
    assert all(request.body.get('expected_account')==adapter.identity.as_dict() for request in adapter.client.sent)


def test_a_legacy_worker_without_binding_acknowledgement_cannot_receive_a_factory_entry(tmp_path,monkeypatch):
    from vati.execution.base import OrderCommand,StopMode
    from vati.risk.contracts import Direction,LossModel
    import vati.execution.transports.mt5_http as transport
    registry=AccountRegistry(tmp_path/'accounts.json')
    account=registry.add(Account(alias='fx_primary',broker='MT5',mode='DEMO_TRADER',currency='USD',login='12345678',server='Broker-Demo',
        credential_ref=CredentialRef(env_var='SOURCE_FIXTURE_NOT_READ')))
    monkeypatch.setattr(registry,'credentials',lambda alias:{'BRIDGE_SIGNING_KEY':KEY.decode(),'BRIDGE_CA_FILE':'source-fixture-ca'})
    calls=[]
    def legacy(request):
        calls.append(request['op'])
        return {'nonce':request['nonce'],'worker_time_ms':request['issued_ms'],
            'account':{'login':12345678,'server':'Broker-Demo','currency':'USD','demo':True,'verified':True,'hedging':True,'equity':'10000','balance':'10000'}}
    monkeypatch.setattr(transport,'Mt5HttpTransport',lambda *args,**kwargs:legacy)
    adapter=build_adapter(account,registry);adapter.clock=lambda:1000000
    cmd=OrderCommand('legacy-entry','d'*64,'legacy-key',account.alias,'mt5','EURUSD',Direction.LONG,'MARKET',
        D('0.1'),D('1.10008'),D('1.09'),StopMode.VENUE,LossModel.STOP_DISTANCE).sealed()
    with pytest.raises(VenueUnavailable,match='binding'):adapter.submit(cmd,now_ms=1000000)
    assert calls==['sync_account']
