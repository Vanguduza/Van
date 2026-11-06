"""A lost opening response cannot create another logical session or path grant."""
import asyncio

import pytest

from conftest_automation import make_store
from test_session_transport_api import _device, _headers, _settings, client
from van_gateway.session.models import PathClass, ResumeRequest, TransportPathDescriptor
from van_gateway.session.service import SessionError, VanHermesSessionService
from van_gateway.storage.db import Store

REQUEST = '54cfd3b6-98f4-4cba-b853-54286a3124ce'

def _path(**changes):
    args={'path_id':'primary','path_class':PathClass.A_REALTIME,'protocol':'WSS',
          'endpoint':'/v1/session/ws','route_id':'primary-ingress','supports_full_duplex':True}
    args.update(changes)
    return TransportPathDescriptor(**args)

@pytest.fixture(autouse=True)
def _no_scheduler(monkeypatch):
    monkeypatch.setenv('VAN_SCHEDULER_ENABLED','false')

@pytest.mark.asyncio
async def test_http_exact_opening_retry_echoes_identity_and_returns_one_session(client):
    ac,app=client
    device=await _device(app)
    body={'open_request_id':REQUEST,'path_id':'primary','route_id':'primary-ingress','protocol':'WSS'}
    first=await ac.post('/v1/session/open',headers=_headers(device),json=body)
    second=await ac.post('/v1/session/open',headers=_headers(device),json=body)
    assert first.status_code==200 and first.json()==second.json()
    assert first.json()['open_request_id']==REQUEST
    assert len(await app.state.store.fetchall('SELECT * FROM van_sessions'))==1
    assert len(await app.state.store.fetchall('SELECT * FROM van_session_paths'))==1
    changed=await ac.post('/v1/session/open',headers=_headers(device),json=dict(body,route_id='different'))
    assert changed.status_code==409 and changed.json()['detail']=='session_open_request_conflict'
    assert len(await app.state.store.fetchall('SELECT * FROM van_sessions'))==1

@pytest.mark.asyncio
async def test_closed_opening_receipt_is_not_resurrected_or_replaced(client):
    ac,app=client
    device=await _device(app)
    body={'open_request_id':REQUEST}
    first=(await ac.post('/v1/session/open',headers=_headers(device),json=body)).json()
    await app.state.van_sessions.close(first['van_session_id'])
    refused=await ac.post('/v1/session/open',headers=_headers(device),json=body)
    assert refused.status_code==409 and refused.json()['detail']=='session_closed'
    assert len(await app.state.store.fetchall('SELECT * FROM van_sessions'))==1

@pytest.mark.asyncio
async def test_legacy_open_without_request_identity_retains_distinct_session_behavior(client):
    ac,app=client
    device=await _device(app)
    one=(await ac.post('/v1/session/open',headers=_headers(device),json={})).json()
    two=(await ac.post('/v1/session/open',headers=_headers(device),json={})).json()
    assert one['open_request_id'] is None and two['open_request_id'] is None
    assert one['van_session_id']!=two['van_session_id']

@pytest.mark.asyncio
async def test_bad_open_request_id_does_not_create_a_session(client):
    ac,app=client
    device=await _device(app)
    response=await ac.post('/v1/session/open',headers=_headers(device),json={'open_request_id':'short'})
    assert response.status_code==422
    assert not await app.state.store.fetchall('SELECT * FROM van_sessions')

@pytest.mark.asyncio
async def test_request_identity_is_scoped_to_the_authenticated_device(tmp_path):
    svc=VanHermesSessionService(await make_store(tmp_path))
    one,_=await svc.open(device_id='device-one',path=_path(),open_request_id=REQUEST)
    two,_=await svc.open(device_id='device-two',path=_path(),open_request_id=REQUEST)
    assert one.van_session_id!=two.van_session_id
    assert len(await svc.store.fetchall('SELECT * FROM van_sessions'))==2

@pytest.mark.asyncio
async def test_concurrent_exact_opening_retries_commit_one_complete_session(tmp_path):
    svc=VanHermesSessionService(await make_store(tmp_path))
    results=await asyncio.gather(*(svc.open(device_id='owner',path=_path(),open_request_id=REQUEST) for _ in range(10)))
    assert len({session.van_session_id for session,_ in results})==1
    assert len(await svc.store.fetchall('SELECT * FROM van_sessions'))==1
    assert len(await svc.store.fetchall('SELECT * FROM van_session_paths'))==1
    assert len(await svc.store.fetchall("SELECT * FROM runtime_meta WHERE key LIKE 'session_open:%'"))==1

@pytest.mark.asyncio
@pytest.mark.parametrize('changes',[{'path_id':'changed'},{'route_id':'changed'},{'protocol':'HTTP2'},
                                    {'path_class':PathClass.B_STREAMING},{'endpoint':'/different'},
                                    {'supports_full_duplex':False}])
async def test_changed_opening_parameters_refuse_without_modifying_original_path(tmp_path,changes):
    svc=VanHermesSessionService(await make_store(tmp_path))
    original,_=await svc.open(device_id='owner',path=_path(),open_request_id=REQUEST)
    with pytest.raises(SessionError) as refused:
        await svc.open(device_id='owner',path=_path(**changes),open_request_id=REQUEST)
    assert refused.value.reason=='session_open_request_conflict'
    paths=await svc.live_paths(original.van_session_id)
    assert paths[0]['route_id']=='primary-ingress' and paths[0]['path_id']=='primary'

@pytest.mark.asyncio
async def test_opening_receipt_survives_gateway_restart(tmp_path):
    svc=VanHermesSessionService(await make_store(tmp_path))
    first,epoch=await svc.open(device_id='owner',path=_path(),open_request_id=REQUEST)
    restarted=VanHermesSessionService(Store(svc.store.path))
    recovered,recovered_epoch=await restarted.open(device_id='owner',path=_path(),open_request_id=REQUEST)
    assert first==recovered and epoch==recovered_epoch

@pytest.mark.asyncio
async def test_retry_after_existing_resume_does_not_grant_a_new_path_epoch(tmp_path):
    svc=VanHermesSessionService(await make_store(tmp_path))
    first,_=await svc.open(device_id='owner',path=_path(),open_request_id=REQUEST)
    resumed=await svc.resume(ResumeRequest(van_session_id=first.van_session_id,session_epoch=first.session_epoch,device_id='owner'),
                             path=_path(route_id='fallback'))
    recovered,epoch=await svc.open(device_id='owner',path=_path(),open_request_id=REQUEST)
    assert epoch==resumed.new_path_epoch==recovered.authoritative_path_epoch==2
    assert len(await svc.store.fetchall('SELECT * FROM van_session_paths'))==2

@pytest.mark.asyncio
async def test_first_path_failure_rolls_back_session_and_opening_receipt(tmp_path,monkeypatch):
    svc=VanHermesSessionService(await make_store(tmp_path))
    async def cannot_record_path(*args,**kwargs):
        raise RuntimeError('path persistence interrupted')
    monkeypatch.setattr(svc,'_record_path',cannot_record_path)
    with pytest.raises(RuntimeError):
        await svc.open(device_id='owner',path=_path(),open_request_id=REQUEST)
    assert not await svc.store.fetchall('SELECT * FROM van_sessions')
    assert not await svc.store.fetchall('SELECT * FROM van_session_paths')
    assert not await svc.store.fetchall("SELECT * FROM runtime_meta WHERE key LIKE 'session_open:%'")
