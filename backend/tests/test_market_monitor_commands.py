"""Original signed owner controls, actual SQL receipts and signed gateway execution."""
import asyncio
import json
import time
from types import SimpleNamespace

import pytest
from conftest_market_monitors import isolate_native_backgrounds
from test_local_typed_actions import client, _settings, _pair_for_test
from test_a4_owner_approval import _signed_command
from test_market_monitor_persistence import service, create_alert
from van_gateway.command.authority import CommandAuthorityRecord, CommandAuthorityService
from van_gateway.command.local_executors import AlertControlExecutor, LocalExecutionError
from van_gateway.command.resolver import TypedCommandResolver, ResolutionMode
from van_gateway.command.success_contracts import contract_for
from van_gateway.models import ActionClass, PrincipalType, OriginChannel
from van_gateway.trading.monitor_commands import parameters, control_readback, request_id
from van_gateway.trading.monitor_models import MonitorControl
from van_gateway.trading.monitor_service import MonitorError
from van_gateway.verification.production import build_mission_registry


ALERT = 'mal_'+'a'*32


def owner_command(app, *, device_id, text, idempotency_key):
    now = int(time.time())
    return _signed_command(app, device_id=device_id, text=text, idempotency_key=idempotency_key,
        issued_at=now, expires_at=now+30, no_stale_replay=True)


@pytest.mark.parametrize('operation', ['pause','restart','delete'])
def test_exact_resolution_and_historical_success_contract(operation):
    resolved = TypedCommandResolver().resolve(f'{operation} trading alert id {ALERT} revision 3')
    assert resolved.mode is ResolutionMode.EXACT_ACTION
    assert resolved.action_id == 'trading.alert.'+operation
    assert resolved.canonical_action_class is ActionClass.A2 and resolved.no_stale_replay
    assert resolved.parameters == {'alert_id':ALERT,'expected_revision':3}
    contract = contract_for(resolved)
    assert contract.is_checkable and contract.postconditions['control_completed'] is True
    assert contract.postconditions['control_revision']=='4'
    assert 'lifecycle' not in contract.postconditions


@pytest.mark.parametrize('phrase', [
    f'pause trading alert id {ALERT} revision 0',
    f'pause trading alert id {ALERT} revision -1',
    f'pause trading alert id {ALERT} revision 01',
    f'pause trading alert id {ALERT} revision 1.0',
    f'pause trading alert id {ALERT.upper()} revision 1',
    f'pause trading alert id {ALERT} revision 9223372036854775807',
    f'pause trading alert id {ALERT} revision 1 then buy EURUSD',
    'pause trading alert id guessed revision 1',
])
def test_ambiguous_or_invalid_phrases_never_become_alert_controls(phrase):
    assert not (TypedCommandResolver().resolve(phrase).action_id or '').startswith('trading.alert.')


@pytest.mark.parametrize('value', [True, 0, -1, 1.5, '1', 2**63-1])
def test_revision_is_a_strict_positive_sql_integer(value):
    with pytest.raises(ValueError): parameters({'alert_id':ALERT,'expected_revision':value})


async def command(s, identity, operation='pause', revision=1, command_id='original-owner-command', **changes):
    values = dict(command_id=command_id, device_id='owner-device', principal_type=PrincipalType.OWNER_DEVICE,
        requested_by='owner', origin_channel=OriginChannel.TEXT, signed_action_class=ActionClass.A2,
        effective_action_class=ActionClass.A2, typed_action_id='trading.alert.'+operation,
        typed_parameter_constraints={'alert_id':identity,'expected_revision':revision}, snapshot_id='snapshot',
        context_digest='a'*64, issued_at_unix=999, expires_at_unix=1020, sealed_at_unix_ms=999000)
    values.update(changes)
    record = CommandAuthorityRecord(**values)
    await CommandAuthorityService(s.store).seal(record)
    return SimpleNamespace(store=s.store, command_id=command_id, device_id='owner-device', market_monitors=s,
                           parameters=record.typed_parameter_constraints)


@pytest.mark.asyncio
@pytest.mark.parametrize('changes', [
    {'authority_source':'STANDING_AUTOMATION'}, {'principal_type':'SYSTEM'},
    {'effective_action_class':'A1'}, {'effective_action_class':'A4'}, {'device_id':'another-device'},
    {'typed_action_id':'trading.halt'},
    {'typed_parameter_constraints':{'alert_id':ALERT,'expected_revision':1,'order':'buy'}},
])
async def test_non_owner_or_different_sealed_authority_cannot_write(tmp_path,changes):
    s = await service(tmp_path); alert = await create_alert(s)
    ctx = await command(s,alert.object_id,**changes)
    with pytest.raises(LocalExecutionError,match='exact sealed owner'): await AlertControlExecutor().execute(ctx)
    assert (await s.get('owner','ALERT',alert.object_id)).revision==1


@pytest.mark.asyncio
async def test_corrupt_authority_key_or_changed_submitted_parameters_cannot_write(tmp_path):
    s=await service(tmp_path); alert=await create_alert(s); ctx=await command(s,alert.object_id)
    ctx.parameters={**ctx.parameters,'expected_revision':2}
    with pytest.raises(LocalExecutionError,match='exact sealed owner'):await AlertControlExecutor().execute(ctx)
    record=await CommandAuthorityService(s.store).get(ctx.command_id)
    await s.store.execute('UPDATE runtime_meta SET value=? WHERE key=?',
        (record.model_copy(update={'command_id':'different-original-command'}).model_dump_json(),
         CommandAuthorityService.PREFIX+ctx.command_id))
    ctx.parameters=record.typed_parameter_constraints
    with pytest.raises(LocalExecutionError,match='exact sealed owner'):await AlertControlExecutor().execute(ctx)
    assert (await s.get('owner','ALERT',alert.object_id)).revision==1


@pytest.mark.asyncio
@pytest.mark.parametrize('operation,status,lifecycle', [('pause','PAUSED','PAUSED'),('restart','RESTARTED','ACTIVE'),('delete','DELETED',None)])
async def test_actual_sql_control_and_original_receipt_replay(tmp_path,operation,status,lifecycle):
    s = await service(tmp_path); alert = await create_alert(s)
    ctx = await command(s,alert.object_id,operation)
    first = await AlertControlExecutor().execute(ctx)
    assert first.observed_postcondition['control_status']==status
    assert first.observed_postcondition['authority_effect']=='NONE'
    if lifecycle:
        current = await s.get('owner','ALERT',alert.object_id)
        assert current.revision==2 and current.lifecycle==lifecycle
    else:
        with pytest.raises(MonitorError,match='MONITOR_OBJECT_UNKNOWN'):await s.get('owner','ALERT',alert.object_id)
    replay = await AlertControlExecutor().execute(ctx)
    assert replay == first
    assert len(await s.store.fetchall('SELECT * FROM market_monitor_operations'))==2
    assert not await s.store.fetchall('SELECT * FROM events')


@pytest.mark.asyncio
async def test_old_pause_verifies_its_receipt_after_later_restart_and_delete(tmp_path):
    s = await service(tmp_path); alert = await create_alert(s)
    ctx = await command(s,alert.object_id)
    original = await AlertControlExecutor().execute(ctx)
    await s.write('owner','ALERT','RESTART',MonitorControl(request_id='later-restart',expected_revision=2),alert.object_id)
    assert (await s.get('owner','ALERT',alert.object_id)).lifecycle=='ACTIVE'
    await s.write('owner','ALERT','DELETE',MonitorControl(request_id='later-delete',expected_revision=3),alert.object_id)
    assert await control_readback(s.store,ctx.command_id)==original.observed_postcondition
    registry=build_mission_registry(store=s.store,trading=None,knowledge=None)
    resolved=TypedCommandResolver().resolve(f'pause trading alert id {alert.object_id} revision 1')
    observed=await registry.verify(strategy='market-alert-control-readback',contract=contract_for(resolved),context={'authority_envelope':{'source_command_id':ctx.command_id}})
    assert observed.status.value=='VERIFIED'
    mismatched=resolved.model_copy(update={'parameters':{'alert_id':alert.object_id,'expected_revision':2}})
    refused=await registry.verify(strategy='market-alert-control-readback',contract=contract_for(mismatched),context={'authority_envelope':{'source_command_id':ctx.command_id}})
    assert refused.status.value=='FAILED'
    await AlertControlExecutor().execute(ctx)
    assert not await s.store.fetchall('SELECT * FROM market_monitor_objects')


@pytest.mark.asyncio
@pytest.mark.parametrize('column,value', [
    ('request_sha256','0'*64), ('result_json','{}'),
    ('result_json',json.dumps({'request_id':'wrong','object_id':ALERT,'kind':'ALERT','revision':2,'status':'PAUSED','state_sha256':'a'*64})),
])
async def test_corrupt_receipt_never_verifies(tmp_path,column,value):
    s = await service(tmp_path); alert = await create_alert(s); ctx = await command(s,alert.object_id)
    await AlertControlExecutor().execute(ctx)
    await s.store.execute(f'UPDATE market_monitor_operations SET {column}=? WHERE request_id=?',(value,request_id(ctx.command_id)))
    with pytest.raises(ValueError):await control_readback(s.store,ctx.command_id)


@pytest.mark.asyncio
@pytest.mark.parametrize('change', [
    {'revision':3}, {'revision':True}, {'request_id':'different'}, {'object_id':ALERT},
    {'kind':'WATCHLIST'}, {'status':'RESTARTED'}, {'state_sha256':None}, {'authority_effect':'ORDER'},
])
async def test_original_receipt_fields_are_exact_not_a_related_success(tmp_path,change):
    s=await service(tmp_path); alert=await create_alert(s); ctx=await command(s,alert.object_id)
    await AlertControlExecutor().execute(ctx)
    row=await s.store.fetchone('SELECT result_json FROM market_monitor_operations WHERE request_id=?',(request_id(ctx.command_id),))
    altered=json.loads(row['result_json']) | change
    await s.store.execute('UPDATE market_monitor_operations SET result_json=? WHERE request_id=?',
        (json.dumps(altered),request_id(ctx.command_id)))
    with pytest.raises(ValueError):await control_readback(s.store,ctx.command_id)


@pytest.mark.asyncio
async def test_service_return_cannot_substitute_for_independent_receipt(tmp_path):
    s = await service(tmp_path); alert=await create_alert(s); ctx=await command(s,alert.object_id)
    async def no_write(*args,**kwargs):return {'status':'PAUSED'}
    ctx.market_monitors=SimpleNamespace(write=no_write)
    with pytest.raises(LocalExecutionError,match='independently verified'):await AlertControlExecutor().execute(ctx)
    ctx.market_monitors=None
    with pytest.raises(LocalExecutionError,match='unavailable'):await AlertControlExecutor().execute(ctx)


@pytest.mark.asyncio
async def test_queue_wait_rechecks_expiry_under_actual_sql_writer_lock(tmp_path):
    clock=[1000000]
    s=await service(tmp_path,clock=lambda:clock[0]); alert=await create_alert(s)
    ctx=await command(s,alert.object_id)
    async with s.store.connection() as db:
        await db.execute('BEGIN IMMEDIATE')
        task=asyncio.create_task(AlertControlExecutor().execute(ctx))
        try:
            await asyncio.sleep(.05)
            assert not task.done()
            clock[0]=1020000
            await db.rollback()
            with pytest.raises(LocalExecutionError,match='MONITOR_COMMAND_EXPIRED'):
                await asyncio.wait_for(task,5)
        finally:
            if not task.done():task.cancel()
            await asyncio.gather(task,return_exceptions=True)
    assert (await s.get('owner','ALERT',alert.object_id)).revision==1
    assert len(await s.store.fetchall('SELECT * FROM market_monitor_operations'))==1


@pytest.mark.asyncio
async def test_signed_gateway_controls_verify_missions_without_order_or_hermes_dispatch(client):
    ac,app,hermes=client
    await _pair_for_test(ac,app,'dev-alert-command','fixture-owner-alert-secret')
    from test_market_monitor_persistence import alert
    response=await ac.post('/v1/trading/monitors/alerts',json={'request_id':'owner-alert-create','state':alert().model_dump(mode='json')})
    assert response.status_code==200,response.text
    identity=response.json()['object_id']
    for revision,operation in enumerate(['pause','restart','delete'],1):
        body=owner_command(app,device_id='dev-alert-command',text=f'{operation} trading alert id {identity} revision {revision}',
            idempotency_key='alert-'+operation)
        reply=await ac.post('/v1/commands',json=body)
        assert reply.status_code==200,reply.text
        result=reply.json()
        assert result['status']=='accepted',result
        assert result['resolved_action_id']=='trading.alert.'+operation
        assert result['local_execution']['verification_state']=='VERIFIED_SUCCESS',result
        mission=await app.state.missions.get(result['mission_id'])
        assert mission.state.value=='VERIFIED_SUCCESS'
        assert (await ac.post('/v1/commands',json=body)).json()==result
    assert hermes['create_run']==0
    assert not await app.state.store.fetchall("SELECT * FROM events WHERE event_type='trading.alert.triggered'")
    assert not await app.state.store.fetchall('SELECT * FROM market_monitor_objects')


@pytest.mark.asyncio
async def test_signed_stale_revision_and_missing_service_are_named_failures(client):
    ac,app,_=client;await _pair_for_test(ac,app,'dev-alert-refusal','fixture-alert-refusal-secret')
    from test_market_monitor_persistence import alert
    r=await ac.post('/v1/trading/monitors/alerts',json={'request_id':'create','state':alert().model_dump(mode='json')})
    identity=r.json()['object_id']
    body=owner_command(app,device_id='dev-alert-refusal',text=f'pause trading alert id {identity} revision 3',idempotency_key='stale')
    response=await ac.post('/v1/commands',json=body)
    assert response.status_code==200,response.text
    assert response.json()['status']=='denied' and 'MONITOR_REVISION_CONFLICT' in response.text
    app.state.orchestrator.market_monitors=None
    body=owner_command(app,device_id='dev-alert-refusal',text=f'pause trading alert id {identity} revision 1',idempotency_key='unavailable')
    response=await ac.post('/v1/commands',json=body)
    assert response.status_code==200,response.text
    result=response.json()
    assert result['status']=='degraded'
    assert (await app.state.missions.get(result['mission_id'])).final_outcome=='market_monitors_unavailable'
