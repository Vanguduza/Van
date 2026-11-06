"""Original session expiry survives SQL contention, restart and lost replies."""
import asyncio
from types import SimpleNamespace
import aiosqlite
import pytest
from van_gateway.session import router as router_module, service as service_module
from van_gateway.session.router import SessionRouter, SessionDelegates
from van_gateway.session.service import VanHermesSessionService
from van_gateway.storage.db import Store
from test_van_hermes_session import DEVICE, _envelope

async def setup(tmp_path, monkeypatch):
    clock = [1.0]
    for module in (router_module, service_module):
        monkeypatch.setattr(module, 'time', SimpleNamespace(time=lambda: clock[0]))
    store = Store(str(tmp_path / 'session.sqlite'))
    await store.migrate()
    service = VanHermesSessionService(store)
    session, epoch = await service.open(device_id=DEVICE)
    calls = []
    async def effect(payload, device_id):
        calls.append(payload)
        return {'recorded': True}
    router = SessionRouter(service, SessionDelegates(submit_command=effect, message_mission=effect))
    envelope = _envelope(session, epoch, kind='mission.message', expires_at_ms=2000, idempotency_key='original')
    return clock, store, service, router, envelope, calls

@pytest.mark.asyncio
async def test_expiry_during_real_writer_wait_prevents_admission_and_effect(tmp_path, monkeypatch):
    clock, store, service, router, envelope, calls = await setup(tmp_path, monkeypatch)
    started = asyncio.Event()
    execute = aiosqlite.Connection.execute
    async def observed(db, sql, *args, **kwargs):
        if sql == 'BEGIN IMMEDIATE': started.set()
        return await execute(db, sql, *args, **kwargs)
    async with store.connection() as blocker:
        await blocker.execute('BEGIN IMMEDIATE')
        monkeypatch.setattr(aiosqlite.Connection, 'execute', observed)
        task = asyncio.create_task(router.route(envelope))
        try:
            await asyncio.wait_for(started.wait(), 2)
            assert not task.done()
            clock[0] = 2.0
            await blocker.commit()
            result = await asyncio.wait_for(task, 3)
            assert not result.accepted and result.refusal == 'session_message_expired'
            assert calls == []
            assert await store.fetchall('SELECT * FROM van_session_messages') == []
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

@pytest.mark.asyncio
async def test_committed_terminal_result_remains_readable_after_expiry_and_restart(tmp_path, monkeypatch):
    clock, store, service, router, envelope, calls = await setup(tmp_path, monkeypatch)
    first = await router.route(envelope)
    assert first.accepted
    clock[0] = 2.0
    router.sessions = VanHermesSessionService(Store(store.path))
    replay = await router.route(envelope)
    assert replay.accepted and replay.result == first.result
    assert len(calls) == 1

@pytest.mark.asyncio
async def test_pending_original_cannot_be_reauthorized_with_changed_expiry(tmp_path, monkeypatch):
    clock, store, service, router, envelope, calls = await setup(tmp_path, monkeypatch)
    await service.admit(envelope)
    async def recover(request, device):
        calls.append(request.payload)
        return {'recorded': True}
    router.delegates.recover_result = recover
    clock[0] = 2.0
    replay = await router.route(envelope.model_copy(update={'expires_at_ms': 3000}))
    assert not replay.accepted
    assert calls == []
    assert (await store.fetchone('SELECT result_json FROM van_session_messages'))['result_json'] is None

@pytest.mark.asyncio
async def test_expiry_after_admission_prevents_dispatch_and_retains_original_identity(tmp_path, monkeypatch):
    clock, store, service, router, envelope, calls = await setup(tmp_path, monkeypatch)
    original = service.admit
    async def delayed(*args, **kwargs):
        result = await original(*args, **kwargs)
        clock[0] = 2.0
        return result
    monkeypatch.setattr(service, 'admit', delayed)
    result = await router.route(envelope)
    assert not result.accepted and result.refusal == 'session_message_expired'
    assert calls == []
    assert len(await store.fetchall('SELECT * FROM van_session_messages')) == 1
    monkeypatch.setattr(service, 'admit', original)
    async def recover(*args): raise AssertionError('expired effect must not be recovered by execution')
    router.delegates.recover_result = recover
    replay = await router.route(envelope)
    assert not replay.accepted and replay.refusal == 'session_result_pending'

@pytest.mark.asyncio
@pytest.mark.parametrize('legacy', [False, True])
async def test_unknown_or_missing_original_deadline_never_reexecutes_after_restart(tmp_path, monkeypatch, legacy):
    clock, store, service, router, envelope, calls = await setup(tmp_path, monkeypatch)
    await service.admit(envelope)
    if legacy: await store.execute("DELETE FROM runtime_meta WHERE key LIKE 'session_expiry:%'")
    router.sessions = VanHermesSessionService(Store(store.path))
    clock[0] = 2.0
    async def recover(*args): raise AssertionError('missing or expired authority cannot execute')
    router.delegates.recover_result = recover
    replay = await router.route(envelope)
    assert not replay.accepted
    assert replay.refusal == ('session_original_expiry_unavailable' if legacy else 'session_result_pending')
    assert (await store.fetchone('SELECT result_json FROM van_session_messages'))['result_json'] is None

@pytest.mark.asyncio
async def test_optional_unbounded_envelope_keeps_its_declared_recovery_behavior(tmp_path, monkeypatch):
    clock, store, service, router, envelope, calls = await setup(tmp_path, monkeypatch)
    envelope = envelope.model_copy(update={'expires_at_ms': None})
    await service.admit(envelope)
    clock[0] = 2000000.0
    async def recover(*args): return {'recorded': True}
    router.delegates.recover_result = recover
    result = await router.route(envelope)
    assert result.accepted and result.result == {'recorded': True}

from test_session_transport_api import _settings, client, _device, _headers, _mission, _open

@pytest.fixture(autouse=True)
def no_scheduler(monkeypatch):
    monkeypatch.setenv('VAN_SCHEDULER_ENABLED', 'false')

@pytest.mark.asyncio
@pytest.mark.parametrize('scenario', ['cached', 'lost_ack', 'corrupt_event', 'foreign_owner'])
async def test_http_original_mission_result_recovers_after_expiry_without_effects(client, monkeypatch, scenario):
    ac, app = client
    device = await _device(app)
    opened = await _open(ac, device)
    mission = await _mission(ac)
    clock = [1.0]
    for module in (router_module, service_module):
        monkeypatch.setattr(module, 'time', SimpleNamespace(time=lambda: clock[0]))
    body = {'message_id':'expiry-note', 'van_session_id':opened['van_session_id'],
            'session_epoch':opened['session_epoch'], 'path_epoch':opened['path_epoch'],
            'kind':'mission.message', 'created_at_ms':1000, 'expires_at_ms':2000,
            'idempotency_key':'expiry-note-key', 'payload':{'mission_id':mission, 'text':'original owner note'}}
    if scenario != 'cached':
        original_record = app.state.van_sessions.record_result
        async def failed_receipt(*args, **kwargs):
            raise RuntimeError('session receipt failed after original effect')
        monkeypatch.setattr(app.state.van_sessions, 'record_result', failed_receipt)
        with pytest.raises(RuntimeError, match='session receipt failed'):
            await ac.post('/v1/session/messages', json=body, headers=_headers(device))
        monkeypatch.setattr(app.state.van_sessions, 'record_result', original_record)
        event = await app.state.store.fetchone("SELECT event_id FROM mission_events WHERE event_type='mission.message'")
        expected = {'event_id': event['event_id'], 'recorded': True}
        assert (await app.state.store.fetchone('SELECT result_json FROM van_session_messages'))['result_json'] is None
    else:
        first = await ac.post('/v1/session/messages', json=body, headers=_headers(device))
        assert first.status_code == 200, first.text
        expected = first.json()['result']
    if scenario == 'corrupt_event':
        await app.state.store.execute("UPDATE mission_events SET summary='different source' WHERE event_type='mission.message'")
    if scenario == 'foreign_owner':
        await app.state.store.execute("UPDATE missions SET owner_principal_id='device:other-phone' WHERE mission_id=?", (mission,))
    before = [dict(r) for r in await app.state.store.fetchall('SELECT * FROM mission_events')]
    async def forbidden(*args): raise AssertionError('readback cannot invoke effectful delegate')
    app.state.session_router.delegates.message_mission = forbidden
    app.state.session_router.delegates.recover_result = forbidden
    clock[0] = 2.0
    replay = await ac.post('/v1/session/messages', json=body, headers=_headers(device))
    if scenario in {'corrupt_event', 'foreign_owner'}:
        assert replay.status_code == 503, replay.text
        assert replay.json()['detail'] == 'session_result_pending'
        assert (await app.state.store.fetchone('SELECT result_json FROM van_session_messages'))['result_json'] is None
    else:
        assert replay.status_code == 200, replay.text
        assert replay.json()['result'] == expected
    assert [dict(r) for r in await app.state.store.fetchall('SELECT * FROM mission_events')] == before

@pytest.mark.asyncio
async def test_http_queued_expiry_never_writes_mission_event(client, monkeypatch):
    ac, app = client
    device = await _device(app)
    opened = await _open(ac, device)
    mission = await _mission(ac)
    clock = [1.0]
    for module in (router_module, service_module):
        monkeypatch.setattr(module, 'time', SimpleNamespace(time=lambda: clock[0]))
    original = app.state.van_sessions.admit
    execute = aiosqlite.Connection.execute
    waiting = asyncio.Event()
    async def observed(db, sql, *args, **kwargs):
        if sql == 'BEGIN IMMEDIATE': waiting.set()
        return await execute(db, sql, *args, **kwargs)
    async def contended(*args, **kwargs):
        async with app.state.store.connection() as blocker:
            await blocker.execute('BEGIN IMMEDIATE')
            with monkeypatch.context() as local:
                local.setattr(aiosqlite.Connection, 'execute', observed)
                task = asyncio.create_task(original(*args, **kwargs))
                try:
                    await asyncio.wait_for(waiting.wait(), 2)
                    assert not task.done()
                    clock[0] = 2.0
                    await blocker.commit()
                    return await asyncio.wait_for(task, 3)
                finally:
                    if not task.done():
                        task.cancel()
                        await asyncio.gather(task, return_exceptions=True)
    monkeypatch.setattr(app.state.van_sessions, 'admit', contended)
    body = {'message_id':'queued', 'van_session_id':opened['van_session_id'],
            'session_epoch':opened['session_epoch'], 'path_epoch':opened['path_epoch'],
            'kind':'mission.message', 'created_at_ms':1000, 'expires_at_ms':2000,
            'idempotency_key':'queued-key', 'payload':{'mission_id':mission, 'text':'expired owner note'}}
    reply = await ac.post('/v1/session/messages', json=body, headers=_headers(device))
    assert reply.status_code == 400, reply.text
    assert reply.json()['detail'] == 'session_message_expired'
    assert await app.state.store.fetchall("SELECT * FROM mission_events WHERE event_type='mission.message'") == []
    assert await app.state.store.fetchall('SELECT * FROM van_session_messages') == []

@pytest.mark.asyncio
async def test_http_signed_command_lost_session_receipt_reads_exact_original_idempotency(client, monkeypatch):
    from test_command_recovery import _request
    ac, app = client
    device = await _device(app)
    opened = await _open(ac, device)
    command = await _request(app, 'owner-phone')
    async def healthy(): return {'ok':True}
    calls = []
    async def accepted(text, metadata=None):
        calls.append(metadata)
        return {'id':'source-test-original-run'}
    monkeypatch.setattr(app.state.orchestrator.hermes, 'health', healthy)
    monkeypatch.setattr(app.state.orchestrator.hermes, 'create_run', accepted)
    clock = [1.0]
    for module in (router_module, service_module):
        monkeypatch.setattr(module, 'time', SimpleNamespace(time=lambda: clock[0]))
    body = {'message_id':'signed-original', 'van_session_id':opened['van_session_id'],
            'session_epoch':opened['session_epoch'], 'path_epoch':opened['path_epoch'],
            'kind':'command.submit', 'command_id':command['command_id'], 'created_at_ms':1000,
            'expires_at_ms':2000, 'idempotency_key':'outer-signed-original', 'payload':command}
    original_record = app.state.van_sessions.record_result
    async def failed_receipt(*args, **kwargs): raise RuntimeError('session receipt failed')
    monkeypatch.setattr(app.state.van_sessions, 'record_result', failed_receipt)
    with pytest.raises(RuntimeError, match='session receipt failed'):
        await ac.post('/v1/session/messages', json=body, headers=_headers(device))
    monkeypatch.setattr(app.state.van_sessions, 'record_result', original_record)
    assert len(calls) == 1
    async def forbidden(*args, **kwargs): raise AssertionError('original result lookup must not dispatch')
    monkeypatch.setattr(app.state.orchestrator.hermes, 'create_run', forbidden)
    app.state.session_router.delegates.recover_result = forbidden
    app.state.session_router.delegates.submit_command = forbidden
    clock[0] = 2.0
    replay = await ac.post('/v1/session/messages', json=body, headers=_headers(device))
    assert replay.status_code == 200, replay.text
    assert replay.json()['result']['command_id'] == command['command_id']
    assert replay.json()['result']['status'] == 'accepted'
    assert len(calls) == 1

@pytest.mark.asyncio
async def test_original_deadline_and_admission_roll_back_together(tmp_path, monkeypatch):
    clock, store, service, router, envelope, calls = await setup(tmp_path, monkeypatch)
    await store.execute("CREATE TRIGGER fail_original_deadline BEFORE INSERT ON runtime_meta WHEN NEW.key LIKE 'session_expiry:%' BEGIN SELECT RAISE(ABORT, 'source deadline write failed'); END")
    with pytest.raises(aiosqlite.IntegrityError, match='source deadline write failed'):
        await router.route(envelope)
    assert calls == []
    assert await store.fetchall('SELECT * FROM van_session_messages') == []
    assert await store.fetchall("SELECT * FROM runtime_meta WHERE key LIKE 'session_expiry:%'") == []

@pytest.mark.asyncio
async def test_retention_removes_original_deadline_with_its_message_only(tmp_path, monkeypatch):
    from van_gateway.ops.retention import RetentionService
    clock, store, service, router, envelope, calls = await setup(tmp_path, monkeypatch)
    assert (await router.route(envelope)).accepted
    future = 10 * 365 * 24 * 60 * 60 * 1000
    young = envelope.model_copy(update={'message_id':'young-message', 'idempotency_key':'young-key', 'expires_at_ms':None})
    await service.admit(young, now_ms=future)
    await store.execute("INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES('unrelated-owner-setting','preserve',1)")
    results = await RetentionService(store).prune(now_ms=future, tables=('van_session_messages',))
    assert sum(result.deleted for result in results if result.table == 'van_session_messages') == 1
    assert await store.fetchone('SELECT * FROM van_session_messages WHERE message_id=?', (envelope.message_id,)) is None
    assert await store.fetchone('SELECT * FROM runtime_meta WHERE key=?', (f'session_expiry:{envelope.message_id}',)) is None
    assert await store.fetchone('SELECT * FROM runtime_meta WHERE key=?', ('session_expiry:young-message',)) is not None
    assert (await store.fetchone("SELECT value FROM runtime_meta WHERE key='unrelated-owner-setting'"))['value'] == 'preserve'
