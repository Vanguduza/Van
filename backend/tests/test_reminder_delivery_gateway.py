"""Actual paired gateway producer, scheduler and owner replay integration."""
import time
import pytest
from test_local_typed_actions import client,_settings,_pair_for_test
from van_gateway.events.bus import EventBus

pytestmark=pytest.mark.asyncio


@pytest.fixture(autouse=True)
def manual_reminder_sweep(monkeypatch):
    # These cases call the real registered sweep, including its deliberate lost ACK.
    # A competing optional periodic sweep would consume that one-shot fault first.
    monkeypatch.setenv('VAN_SCHEDULER_ENABLED', 'false')


async def test_gateway_sweep_recovers_lost_delivery_ack_without_refiring(client,monkeypatch):
    ac,app,hermes=client
    await _pair_for_test(ac,app,'dev-reminder','fixture-reminder-device-secret')
    r=await ac.post('/v1/reminders',json={'text':'Confirm actual outcome','due_at_unix':int(time.time())-60,'idempotency_key':'reminder-gateway-original','project_id':'project-alpha'})
    assert r.status_code==200,r.text
    reminder=r.json();publish=EventBus.publish;failed=False
    async def lost_ack(self,event_type,payload,**kwargs):
        nonlocal failed
        result=await publish(self,event_type,payload,**kwargs)
        if event_type=='reminder.fired' and not failed:
            failed=True;raise RuntimeError('fixture lost gateway event acknowledgement')
        return result
    monkeypatch.setattr(EventBus,'publish',lost_ack)
    sweep=app.state.scheduler.jobs['reminders.fire_due'].run
    with pytest.raises(RuntimeError,match='fixture lost gateway event'):await sweep()
    result=await sweep();assert result=={'fired':0,'published':1}
    assert (await sweep())=={'fired':0,'published':0}
    replay=await ac.get('/v1/events',params={'device_id':'dev-reminder','after_seq':0})
    assert replay.status_code==200,replay.text
    events=[e for e in replay.json()['events'] if e['event_type']=='reminder.fired']
    assert len(events)==1 and events[0]['payload']['reminder_id']==reminder['id']
    attention=await app.state.store.fetchone('SELECT project_id FROM attention WHERE dedupe_key=?',('reminder:'+reminder['id'],))
    assert attention['project_id']=='project-alpha' and hermes['create_run']==0


async def test_gateway_reminder_conflicts_and_bad_time_are_explicit_refusals(client):
    ac,app,_=client;await _pair_for_test(ac,app,'dev-reminder','fixture-reminder-device-secret')
    body={'text':'Original','due_at_unix':int(time.time())+1000,'idempotency_key':'reminder-api-original'}
    created=await ac.post('/v1/reminders',json=body);assert created.status_code==200,created.text
    assert (await ac.post('/v1/reminders',json={**body,'text':'Changed'})).status_code==409
    rid=created.json()['id'];assert (await ac.post(f'/v1/reminders/{rid}/cancel')).status_code==200
    assert (await ac.post(f'/v1/reminders/{rid}/resolve')).status_code==409
    assert (await ac.post('/v1/reminders/missing/cancel')).status_code==404
    for due in ['at 13pm','at 12:77','in '+('9'*100)+' days']:
        r=await ac.post('/v1/reminders/parse',json={'text':'Invalid time','due_expression':due,'idempotency_key':'invalid-time'})
        assert r.status_code==400,r.text
