"""Callbacks survive the create-receipt race and never select their own mission."""
import asyncio
import time

import pytest

from test_command_execution_result import INTERNAL, _enrol, _settings, _signed, client
from test_mission_core import CHECKABLE, GOOD_OBSERVATION, _mission, _registry, _service
from van_gateway.mission.models import MissionEventType, MissionState
from van_gateway.mission.service import MissionError, MissionService
from van_gateway.mission.verifiers import ObservationVerifier, VerifierRegistry
from van_gateway.storage.db import Store


async def _authorized(svc, **kwargs):
    mission = await _mission(svc, **kwargs)
    for state in (MissionState.UNDERSTOOD, MissionState.PLANNED, MissionState.AUTHORIZED):
        mission = await svc.transition(mission.mission_id, target=state)
    return mission


@pytest.mark.asyncio
async def test_callback_before_create_response_is_retained_and_applied(client, monkeypatch):
    ac, app = client
    device_id = await _enrol(ac, app)
    observed = {}
    async def create_run(text, metadata=None):
        report = await ac.post('/v1/runtime/missions/result', headers={'X-Van-Internal-Token': INTERNAL},
                               json={'hermes_run_id': 'fast-worker', 'status': 'COMPLETED'})
        assert report.status_code == 202
        assert report.json()['status'] == 'WAITING_FOR_BINDING'
        assert report.json()['mission_id'] is None
        observed.update(metadata or {})
        return {'id': 'fast-worker'}
    monkeypatch.setattr(app.state.orchestrator.hermes, 'create_run', create_run)
    body = _signed(app, device_id, 'brief me about the current project', idempotency_key='fast-worker-key')
    accepted = await ac.post('/v1/commands', json=body)
    assert accepted.status_code == 200 and accepted.json()['status'] == 'accepted'
    mission = await app.state.missions.get(accepted.json()['mission_id'])
    assert mission.mission_id == observed['mission_id']
    assert mission.state is MissionState.UNVERIFIABLE
    row = await app.state.store.fetchone('SELECT * FROM hermes_result_inbox')
    assert row['state'] == 'APPLIED'
    assert (await ac.get(f"/v1/commands/{body['command_id']}")).json()['owner_status'] == 'COULD_NOT_VERIFY'


@pytest.mark.asyncio
async def test_callback_observation_failure_does_not_lose_accepted_run(client, monkeypatch):
    ac, app = client
    device_id = await _enrol(ac, app)
    original = app.state.missions._perform_verification
    async def unavailable(*args, **kwargs):
        raise RuntimeError('observation temporarily unavailable')
    monkeypatch.setattr(app.state.missions, '_perform_verification', unavailable)
    async def create_run(text, metadata=None):
        report = await ac.post('/v1/runtime/missions/result', headers={'X-Van-Internal-Token': INTERNAL},
                               json={'hermes_run_id': 'observation-down', 'status': 'COMPLETED'})
        assert report.status_code == 202
        return {'id': 'observation-down'}
    monkeypatch.setattr(app.state.orchestrator.hermes, 'create_run', create_run)
    body = _signed(app, device_id, 'brief me', idempotency_key='observation-down-key')
    accepted = (await ac.post('/v1/commands', json=body)).json()
    assert accepted['status'] == 'accepted'
    assert (await app.state.missions.get(accepted['mission_id'])).state is MissionState.VERIFYING
    assert (await app.state.store.fetchone('SELECT state FROM hermes_result_inbox'))['state'] == 'RECEIVED'
    monkeypatch.setattr(app.state.missions, '_perform_verification', original)
    assert await app.state.missions.reconcile_hermes_results() == 1
    assert (await app.state.missions.get(accepted['mission_id'])).state is MissionState.UNVERIFIABLE


@pytest.mark.asyncio
async def test_wait_then_complete_before_bind_preserves_order(client, monkeypatch):
    ac, app = client
    device_id = await _enrol(ac, app)
    async def create_run(text, metadata=None):
        for outcome in ('WAITING_EXTERNAL', 'COMPLETED'):
            result = await ac.post('/v1/runtime/missions/result', headers={'X-Van-Internal-Token': INTERNAL},
                                   json={'hermes_run_id': 'ordered-worker', 'status': outcome})
            assert result.status_code == 202
        return {'id': 'ordered-worker'}
    monkeypatch.setattr(app.state.orchestrator.hermes, 'create_run', create_run)
    accepted = (await ac.post('/v1/commands', json=_signed(app, device_id, 'brief me', idempotency_key='ordered-key'))).json()
    events = await app.state.missions.events(accepted['mission_id'])
    types = [event.event_type for event in events]
    reports = await app.state.store.fetchall('SELECT outcome,state FROM hermes_result_inbox ORDER BY result_id')
    assert [(r['outcome'], r['state']) for r in reports] == [('WAITING_EXTERNAL', 'APPLIED'), ('COMPLETED', 'APPLIED')]
    assert types.count(MissionEventType.MISSION_STARTED) == 2
    assert (await app.state.missions.get(accepted['mission_id'])).state is MissionState.UNVERIFIABLE


@pytest.mark.asyncio
async def test_unbound_conflicting_terminal_reports_refuse_and_cannot_choose_mission(client):
    ac, app = client
    await _enrol(ac, app)
    victim = await _authorized(app.state.missions)
    completed = await ac.post('/v1/runtime/missions/result', headers={'X-Van-Internal-Token': INTERNAL},
                              json={'hermes_run_id': 'unbound-worker', 'status': 'COMPLETED', 'mission_id': victim.mission_id})
    assert completed.status_code == 202 and completed.json()['mission_id'] is None
    conflict = await ac.post('/v1/runtime/missions/result', headers={'X-Van-Internal-Token': INTERNAL},
                            json={'hermes_run_id': 'unbound-worker', 'status': 'FAILED'})
    assert conflict.status_code == 409 and conflict.json()['detail'] == 'HERMES_RESULT_CONFLICT'
    assert (await app.state.missions.get(victim.mission_id)).state is MissionState.AUTHORIZED
    assert len(await app.state.store.fetchall('SELECT * FROM hermes_result_inbox')) == 1


@pytest.mark.asyncio
async def test_callback_requires_runtime_scope_before_durable_ingestion(client):
    ac, app = client
    await _enrol(ac, app)
    result = await ac.post('/v1/runtime/missions/result', json={'hermes_run_id': 'denied', 'status': 'COMPLETED'})
    assert result.status_code in {401, 403}
    assert not await app.state.store.fetchall('SELECT * FROM hermes_result_inbox')


@pytest.mark.asyncio
async def test_inbox_survives_restart_until_real_receipt_binds(tmp_path):
    svc = await _service(tmp_path)
    mission = await _authorized(svc)
    first = await svc.ingest_hermes_result(hermes_run_id='restart-worker', outcome='COMPLETED')
    assert first['status'] == 'WAITING_FOR_BINDING'
    restarted = MissionService(Store(svc.store.path))
    assert await restarted.reconcile_hermes_results() == 0
    bound = await restarted.bind_hermes_run(mission_id=mission.mission_id, hermes_run_id='restart-worker')
    assert bound.state is MissionState.UNVERIFIABLE
    duplicate = await restarted.ingest_hermes_result(hermes_run_id='restart-worker', outcome='COMPLETED')
    assert duplicate['status'] == 'APPLIED'
    assert len(await restarted.store.fetchall('SELECT * FROM hermes_result_inbox')) == 1


@pytest.mark.asyncio
async def test_crash_after_binding_before_started_is_reconciled(tmp_path):
    svc = await _service(tmp_path)
    mission = await _authorized(svc)
    await svc.ingest_hermes_result(hermes_run_id='receipt-committed', outcome='COMPLETED')
    await svc.store.execute('INSERT INTO hermes_run_bindings(hermes_run_id,mission_id,bound_at_ms) VALUES (?,?,?)',
                            ('receipt-committed', mission.mission_id, int(time.time() * 1000)))
    restarted = MissionService(Store(svc.store.path))
    assert await restarted.reconcile_hermes_results() == 1
    assert (await restarted.get(mission.mission_id)).state is MissionState.UNVERIFIABLE
    assert (await restarted.store.fetchone('SELECT started_at_ms FROM hermes_run_bindings'))['started_at_ms'] is not None


@pytest.mark.asyncio
async def test_crash_after_terminal_before_inbox_ack_does_not_repeat_terminal_events(tmp_path, monkeypatch):
    svc = await _service(tmp_path)
    mission = await _authorized(svc)
    await svc.bind_hermes_run(mission_id=mission.mission_id, hermes_run_id='ack-crash')
    async def die_before_ack(*args, **kwargs):
        raise RuntimeError('process died before durable inbox acknowledgment')
    monkeypatch.setattr(svc.hermes_results, '_finish', die_before_ack)
    with pytest.raises(RuntimeError):
        await svc.ingest_hermes_result(hermes_run_id='ack-crash', outcome='COMPLETED')
    assert (await svc.get(mission.mission_id)).state is MissionState.UNVERIFIABLE
    events_before = await svc.events(mission.mission_id)
    await svc.store.execute('UPDATE hermes_result_inbox SET lease_until_ms=0')
    restarted = MissionService(Store(svc.store.path))
    assert await restarted.reconcile_hermes_results() == 1
    assert len(await restarted.events(mission.mission_id)) == len(events_before)


@pytest.mark.asyncio
async def test_verifier_exception_is_durable_and_retries_from_verifying(tmp_path, monkeypatch):
    svc = await _service(tmp_path)
    mission = await _authorized(svc, success_contract=CHECKABLE)
    await svc.bind_hermes_run(mission_id=mission.mission_id, hermes_run_id='verifier-retry')
    async def unavailable(*args, **kwargs):
        raise RuntimeError('readback temporarily unavailable')
    monkeypatch.setattr(svc, '_perform_verification', unavailable)
    with pytest.raises(RuntimeError):
        await svc.ingest_hermes_result(hermes_run_id='verifier-retry', outcome='COMPLETED')
    assert (await svc.get(mission.mission_id)).state is MissionState.VERIFYING
    assert (await svc.store.fetchone('SELECT state FROM hermes_result_inbox'))['state'] == 'RECEIVED'
    restarted = MissionService(Store(svc.store.path), verifiers=_registry(GOOD_OBSERVATION))
    assert await restarted.reconcile_hermes_results() == 1
    assert (await restarted.get(mission.mission_id)).state is MissionState.VERIFIED_SUCCESS


@pytest.mark.asyncio
async def test_cancel_during_observation_is_not_overwritten_or_announced_as_success(tmp_path):
    observing, release = asyncio.Event(), asyncio.Event()
    async def observe(context):
        observing.set()
        await release.wait()
        return GOOD_OBSERVATION
    registry = VerifierRegistry()
    registry.register('notebook.readback', ObservationVerifier(observe, verifier_version='test.readback/1', evidence_prefix='test://'))
    svc = await _service(tmp_path, registry)
    mission = await _authorized(svc, success_contract=CHECKABLE)
    await svc.bind_hermes_run(mission_id=mission.mission_id, hermes_run_id='cancel-race')
    report = asyncio.create_task(svc.ingest_hermes_result(hermes_run_id='cancel-race', outcome='COMPLETED'))
    await asyncio.wait_for(observing.wait(), timeout=2)
    await svc.transition(mission.mission_id, target=MissionState.CANCELLED, expected=MissionState.VERIFYING)
    release.set()
    result = await report
    assert result['state'] == 'CANCELLED'
    row = await svc.store.fetchone('SELECT verification_record_json FROM missions WHERE mission_id=?', (mission.mission_id,))
    assert row['verification_record_json'] is None
    events = await svc.events(mission.mission_id)
    assert not any(e.event_type is MissionEventType.MISSION_COMPLETED for e in events)
    with pytest.raises(MissionError) as refused:
        await svc.ingest_hermes_result(hermes_run_id='cancel-race', outcome='COMPLETED')
    assert refused.value.code == 'HERMES_RESULT_CONFLICT'


@pytest.mark.asyncio
async def test_concurrent_duplicate_callbacks_apply_one_receipt(tmp_path):
    svc = await _service(tmp_path)
    mission = await _authorized(svc)
    await svc.bind_hermes_run(mission_id=mission.mission_id, hermes_run_id='concurrent-worker')
    results = await asyncio.gather(*(svc.ingest_hermes_result(hermes_run_id='concurrent-worker', outcome='COMPLETED') for _ in range(10)))
    assert all(r['mission_id'] == mission.mission_id for r in results)
    assert len(await svc.store.fetchall('SELECT * FROM hermes_result_inbox')) == 1
    events = await svc.events(mission.mission_id)
    assert sum(e.event_type is MissionEventType.MISSION_VERIFYING for e in events) == 1


@pytest.mark.asyncio
async def test_run_binding_is_immutable_and_one_run_cannot_target_two_missions(tmp_path):
    svc = await _service(tmp_path)
    first, second = await _authorized(svc), await _authorized(svc)
    await svc.bind_hermes_run(mission_id=first.mission_id, hermes_run_id='immutable')
    for mission_id, run_id in ((second.mission_id, 'immutable'), (first.mission_id, 'different')):
        with pytest.raises(MissionError) as refused:
            await svc.bind_hermes_run(mission_id=mission_id, hermes_run_id=run_id)
        assert refused.value.code == 'HERMES_RUN_BINDING_CONFLICT'
    assert (await svc.get(second.mission_id)).state is MissionState.AUTHORIZED


@pytest.mark.asyncio
async def test_pending_callback_is_reconciled_before_deadline_expiry(tmp_path):
    svc = await _service(tmp_path)
    mission = await _authorized(svc)
    await svc.ingest_hermes_result(hermes_run_id='deadline-inbox', outcome='COMPLETED')
    await svc.store.execute('INSERT INTO hermes_run_bindings(hermes_run_id,mission_id,bound_at_ms) VALUES (?,?,?)',
                            ('deadline-inbox', mission.mission_id, int(time.time() * 1000)))
    await svc.set_deadline(mission.mission_id, 1)
    assert await svc.expire_overdue() == []
    assert (await svc.get(mission.mission_id)).state is MissionState.UNVERIFIABLE
