"""Socket handshake and open frames enforce the same owner binding as HTTP."""
import hashlib
import json
import time
import asyncio
from functools import partial

import pytest
from cryptography import x509
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from starlette.testclient import TestClient
from starlette.websockets import WebSocket, WebSocketDisconnect

from test_device_proof_enforcement import _bind, _proof_headers
from test_mtls_pki import csr_for
from test_owner_device_binding import PACKAGE, SIGNING_CERT
from van_gateway.app import create_app
from van_gateway.config import get_settings
from van_gateway.events.bus import EventBus
from van_gateway.mission.models import MissionOrigin
from van_gateway.models import OriginChannel
from van_gateway.mtls.pki import DeviceCA,init_ca
from van_gateway.mtls.transport import EXTENSION,MutualTLSGate

@pytest.fixture
def gateway(tmp_path,monkeypatch,request):
    configured=getattr(request,'param','configured')!='unconfigured'
    for name,value in {
        'VAN_DATABASE_PATH':str(tmp_path/'socket.sqlite3'),
        'VAN_HERMES_BASE_URL':'http://hermes.invalid',
        'VAN_GOOGLE_TOKEN_FERNET_KEY':Fernet.generate_key().decode(),
        'VAN_DEVICE_SECRET_FERNET_KEY':Fernet.generate_key().decode(),
        'VAN_INGRESS_TOKEN':'socket-test-ingress-token-0123456789',
        'VAN_INTERNAL_CONTROL_TOKEN':'socket-test-runtime-token-0123456789',
        'VAN_OWNER_DEVICE_PACKAGE':PACKAGE,
        'VAN_OWNER_DEVICE_SIGNING_CERT_SHA256':SIGNING_CERT if configured else '',
        'VAN_REQUIRE_DEVICE_BINDING':'true',
        'VAN_SCHEDULER_ENABLED':'false',
    }.items():
        monkeypatch.setenv(name,value)
    get_settings.cache_clear()
    app=create_app()
    with TestClient(app) as client:
        yield client,app,tmp_path
    get_settings.cache_clear()

async def _seed(app, *, bind=True,device_id='socket-owner'):
    ticket=await app.state.auth.create_pairing_ticket(device_id)
    paired=await app.state.auth.pair_device(ticket.token,device_id,'s'*32,'PEM',device_id)
    key=await _bind(app,device_id) if bind else None
    if bind:
        # Trusted synthetic binding isolates the transport proof/revocation checks.
        # Actual signed attestation chains are exercised in the enrollment API tests.
        await app.state.store.execute(
            'UPDATE owner_device_bindings SET attestation_chain_verified = 1 WHERE device_id = ?', (device_id,),
        )
    session,epoch=await app.state.van_sessions.open(device_id=device_id)
    mission=await app.state.missions.create(owner_principal_id=f'device:{device_id}',origin=MissionOrigin.OWNER_UI,
                                           origin_channel=OriginChannel.UI,title='socket mission',goal='socket mission')
    return paired,session,epoch,mission,key

def _url(seeded):
    paired,session,_epoch,_mission,_key=seeded
    return f'/v1/session/ws?van_session_id={session.van_session_id}&device_token={paired.access_token}'

def _proof(seeded,**changes):
    paired,_session,_epoch,_mission,key=seeded
    return _proof_headers(key,method=changes.get('method','GET'),path=changes.get('path','/v1/session/ws'),
                          device_id=paired.device.device_id,body=changes.get('body',b''))

def _cancel(socket,seeded):
    paired,session,epoch,mission,_key=seeded
    payload={'mission_id':mission.mission_id}
    socket.send_json({'protocol_version':1,'message_id':'socket-cancel','van_session_id':session.van_session_id,
                      'session_epoch':session.session_epoch,'path_epoch':epoch,'kind':'mission.cancel',
                      'created_at_ms':int(time.time()*1000),'idempotency_key':'socket-cancel-key',
                      'payload_digest':hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
                      'payload':payload})
    while True:
        message=socket.receive_json()
        if message.get('message_id')=='socket-cancel': return message

def _refused(client,url,reason,code,headers=None):
    with pytest.raises(WebSocketDisconnect) as raised:
        with client.websocket_connect(url,headers=headers or {}): pass
    assert raised.value.code==code and raised.value.reason==reason

@pytest.mark.parametrize('gateway',['unconfigured'],indirect=True)
def test_strict_unconfigured_socket_cannot_bypass_http_binding_gate(gateway):
    client,app,_tmp=gateway
    seeded=client.portal.call(partial(_seed,app,bind=False))
    paired=seeded[0]
    response=client.post('/v1/session/open',json={},headers={
        'X-Van-Ingress-Token':'socket-test-ingress-token-0123456789','X-Van-Device-Token':paired.access_token,
    })
    assert response.status_code==503
    _refused(client,_url(seeded),'owner_device_binding_unconfigured',1011)
    assert client.portal.call(app.state.missions.get,seeded[3].mission_id).state.value=='CAPTURED'

def test_strict_unbound_socket_refused(gateway):
    client,app,_tmp=gateway
    seeded=client.portal.call(partial(_seed,app,bind=False))
    _refused(client,_url(seeded),'device_not_bound',4403)

def test_strict_legacy_binding_requires_chain_recertification(gateway):
    client,app,_tmp=gateway
    seeded=client.portal.call(_seed,app)
    client.portal.call(app.state.store.execute,
                       'UPDATE owner_device_bindings SET attestation_chain_verified = 0 WHERE device_id = ?',
                       (seeded[0].device.device_id,))
    _refused(client,_url(seeded),'device_attestation_recertification_required',4403,headers=_proof(seeded))

def test_bound_owner_socket_requires_proof_and_client_header_cannot_mint_certificate(gateway):
    client,app,_tmp=gateway
    seeded=client.portal.call(_seed,app)
    _refused(client,_url(seeded),'device_proof_required',4401)
    _refused(client,_url(seeded),'device_proof_required',4401,headers={'X-Van-mTLS-Device':'socket-owner'})

@pytest.mark.parametrize('changes',[{'path':'/v1/commands'},{'method':'POST'},{'body':b'changed'}])
def test_proof_is_bound_to_get_socket_and_empty_body(gateway,changes):
    client,app,_tmp=gateway
    seeded=client.portal.call(_seed,app)
    _refused(client,_url(seeded),'device_proof_invalid',4401,headers=_proof(seeded,**changes))

def test_malformed_and_stale_proof_refused(gateway):
    client,app,_tmp=gateway
    seeded=client.portal.call(_seed,app)
    _refused(client,_url(seeded),'device_proof_malformed',4401,
             headers={'X-Van-Device-Proof':'not base64','X-Van-Device-Proof-Issued-At':'x'})
    headers=_proof(seeded)
    headers['X-Van-Device-Proof-Issued-At']='1'
    _refused(client,_url(seeded),'device_proof_stale',4401,headers=headers)

def test_valid_proof_routes_owner_command_and_cannot_open_another_socket(gateway):
    client,app,_tmp=gateway
    seeded=client.portal.call(_seed,app)
    headers=_proof(seeded)
    with client.websocket_connect(_url(seeded),headers=headers) as socket:
        assert _cancel(socket,seeded)['accepted'] is True
    admission=client.portal.call(app.state.store.fetchone,
                                 "SELECT after_json FROM audit WHERE capability='session.transport.admitted'")
    evidence=json.loads(admission['after_json'])
    assert evidence=={'van_session_id':seeded[1].van_session_id,'binding_id':client.portal.call(app.state.owner_device_bindings.active).binding_id,
                      'transport':'WEBSOCKET','certified_matching':False,'certificate_serial':None,'proof_verified':True}
    assert seeded[0].access_token not in admission['after_json']
    assert client.portal.call(app.state.missions.get,seeded[3].mission_id).state.value=='CANCELLED'
    _refused(client,_url(seeded),'device_proof_replayed',4401,headers=headers)

def test_second_paired_device_cannot_downgrade_bound_owner(gateway):
    client,app,_tmp=gateway
    client.portal.call(_seed,app)
    second=client.portal.call(partial(_seed,app,bind=False,device_id='other-phone'))
    _refused(client,_url(second),'device_not_owner_device',4403)

@pytest.mark.parametrize('revoke',['device','binding'])
def test_revocation_stops_an_already_open_socket_before_next_control_frame(gateway,revoke):
    client,app,_tmp=gateway
    seeded=client.portal.call(_seed,app)
    with client.websocket_connect(_url(seeded),headers=_proof(seeded)) as socket:
        if revoke=='device':
            client.portal.call(app.state.auth.revoke,seeded[0].device.device_id)
        else:
            client.portal.call(partial(app.state.owner_device_bindings.revoke,reason='test revocation'))
        with pytest.raises(WebSocketDisconnect) as raised:
            _cancel(socket,seeded)
        assert raised.value.code==(4401 if revoke=='device' else 4403)
    assert client.portal.call(app.state.missions.get,seeded[3].mission_id).state.value=='CAPTURED'

@pytest.mark.parametrize('queue_event_before_revocation',[False,True])
def test_receiver_shutdown_cannot_cancel_the_revocation_close_frame(gateway,monkeypatch,queue_event_before_revocation):
    client,app,_tmp=gateway
    seeded=client.portal.call(_seed,app)
    close_started=asyncio.Event()
    control_received=asyncio.Event()
    event_queued=asyncio.Event()
    original_close,original_receive=WebSocket.close,WebSocket.receive_json
    original_send=WebSocket.send_json
    async def delayed_close(socket,**kwargs):
        close_started.set()
        await control_received.wait()
        await original_close(socket,**kwargs)
    async def note_control(socket,*args,**kwargs):
        body=await original_receive(socket,*args,**kwargs)
        if body.get('kind')=='mission.cancel': control_received.set()
        return body
    async def note_downstream(socket,body,*args,**kwargs):
        await original_send(socket,body,*args,**kwargs)
        if body.get('direction')=='DOWNSTREAM': event_queued.set()
    monkeypatch.setattr(WebSocket,'close',delayed_close)
    monkeypatch.setattr(WebSocket,'receive_json',note_control)
    monkeypatch.setattr(WebSocket,'send_json',note_downstream)
    with client.websocket_connect(_url(seeded),headers=_proof(seeded)) as socket:
        if queue_event_before_revocation:
            # Force the legitimate pre-revocation event to remain queued ahead of
            # the close. Teardown authority is independent of that frame ordering.
            client.portal.call(partial(asyncio.wait_for,event_queued.wait(),timeout=2))
        client.portal.call(app.state.auth.revoke,seeded[0].device.device_id)
        client.portal.call(partial(asyncio.wait_for,close_started.wait(),timeout=2))
        # A control frame wakes the receiver while the event pump is sending a close.
        # Its shutdown must still deliver that close, rather than cancel the sender.
        socket.send_json({'kind':'mission.cancel'})
        # Read the actual ASGI close frame with a deadline; a missing frame must fail
        # the regression instead of blocking the sync TestClient indefinitely.
        async def next_close_frame():
            while True:
                frame=await socket._send_rx.receive()
                if frame['type']=='websocket.close': return frame
                assert frame['type']=='websocket.send'
                assert json.loads(frame['text'])['direction']=='DOWNSTREAM'
        frame=client.portal.call(partial(asyncio.wait_for,next_close_frame(),timeout=2))
        assert frame=={'type':'websocket.close','code':4401,'reason':'device_access_revoked'}
    assert client.portal.call(app.state.missions.get,seeded[3].mission_id).state.value=='CAPTURED'

def test_peer_teardown_does_not_interrupt_cancelled_event_pump_cleanup(gateway,monkeypatch):
    client,app,_tmp=gateway
    seeded=client.portal.call(_seed,app)
    entered,cleanup_started,cleanup_finished=asyncio.Event(),asyncio.Event(),asyncio.Event()

    async def held_replay(*args,**kwargs):
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            # The real event pump may still be closing its asynchronous store
            # connection. Hold that same shutdown boundary while the peer exits.
            cleanup_started.set()
            await asyncio.sleep(0.1)
            cleanup_finished.set()
            raise

    monkeypatch.setattr(EventBus,'replay',held_replay)
    with client.websocket_connect(_url(seeded),headers=_proof(seeded)) as socket:
        client.portal.call(partial(asyncio.wait_for,entered.wait(),timeout=2))
        client.portal.call(app.state.auth.revoke,seeded[0].device.device_id)
        with pytest.raises(WebSocketDisconnect) as raised:
            _cancel(socket,seeded)
        assert raised.value.code==4401 and raised.value.reason=='device_access_revoked'
        client.portal.call(partial(asyncio.wait_for,cleanup_started.wait(),timeout=2))
    assert cleanup_finished.is_set()
    assert client.portal.call(app.state.missions.get,seeded[3].mission_id).state.value=='CAPTURED'

def test_verified_certificate_scope_admits_bound_device_and_refuses_mismatch(gateway):
    client,app,tmp=gateway
    seeded=client.portal.call(_seed,app)
    ca_dir=tmp/'device-ca'
    init_ca(ca_dir)
    ca=DeviceCA(ca_dir)
    issued=ca.issue_client(csr_for('socket-owner')[0],'socket-owner')
    der=x509.load_pem_x509_certificate(issued.certificate_pem.encode()).public_bytes(serialization.Encoding.DER)
    gate=MutualTLSGate(app,lambda:ca)
    async def certified_app(scope,receive,send):
        if scope['type']=='websocket': scope.setdefault('extensions',{})[EXTENSION]={'client_cert_der':der}
        await gate(scope,receive,send)
    # The certificate has passed the real CA admission gate; a request header is never used.
    with TestClient(certified_app) as secured:
        with secured.websocket_connect(_url(seeded)) as socket:
            assert _cancel(socket,seeded)['accepted'] is True
        other=secured.portal.call(partial(_seed,app,bind=False,device_id='wrong-token'))
        with pytest.raises(WebSocketDisconnect) as raised:
            with secured.websocket_connect(_url(other)): pass
        assert raised.value.code==4403
