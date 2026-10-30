"""Independent persisted-state checks for reminder races and chained effects."""
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
import pytest
from conftest_automation import make_store
from van_gateway.models import ReminderCreate
from van_gateway.reminders.service import ReminderService
from van_gateway.reminders.timeparse import parse_due_expression,TimeParseError


def body(**fields):
    return ReminderCreate(**dict(text='Review actual result',due_at_unix=1,idempotency_key='owner-original',**fields))


@pytest.mark.asyncio
async def test_same_key_with_changed_request_is_not_a_successful_replay(tmp_path):
    service=ReminderService(await make_store(tmp_path));await service.create(body())
    with pytest.raises(ValueError,match='reminder_idempotency_conflict'):
        await service.create(ReminderCreate(text='Different instruction',due_at_unix=1,idempotency_key='owner-original'))


@pytest.mark.asyncio
async def test_two_concurrent_creators_return_one_original_reminder(tmp_path):
    store=await make_store(tmp_path);a=ReminderService(store);b=ReminderService(store)
    results=await asyncio.gather(a.create(body()),b.create(body()),return_exceptions=True)
    assert all(isinstance(r,dict) for r in results),[type(r).__name__ for r in results]
    assert results[0]['id']==results[1]['id']
    assert (await store.fetchone('SELECT count(*) AS n FROM reminders'))['n']==1


@pytest.mark.asyncio
async def test_two_schedulers_cannot_both_deliver_the_same_due_reminder(tmp_path):
    store=await make_store(tmp_path);a=ReminderService(store);b=ReminderService(store)
    row=await a.create(body());results=await asyncio.gather(a.fire_due(now=5),b.fire_due(now=5))
    assert [r['id'] for batch in results for r in batch]==[row['id']]


@pytest.mark.asyncio
async def test_cancelled_reminder_cannot_be_resolved_into_new_scheduled_work(tmp_path):
    store=await make_store(tmp_path);s=ReminderService(store)
    r=await s.create(body(chain_follow_up_text='Follow up',chain_follow_up_offset_seconds=60))
    await s.cancel(r['id'])
    with pytest.raises(ValueError,match='reminder_state_conflict'):
        await s.resolve(r['id'])
    assert (await store.fetchone('SELECT status FROM reminders WHERE id=?',(r['id'],)))['status']=='CANCELLED'
    assert await s.get_by_idempotency_key('chain:'+r['id']) is None


@pytest.mark.asyncio
async def test_follow_up_retains_original_project_and_source_and_replays_without_new_work(tmp_path):
    store=await make_store(tmp_path);s=ReminderService(store)
    r=await s.create(body(project_id='project-alpha',source='hermes',chain_follow_up_text='Follow up',chain_follow_up_offset_seconds=60))
    await s.resolve(r['id']);first=await s.get_by_idempotency_key('chain:'+r['id'])
    assert first['project_id']=='project-alpha' and first['source']=='hermes'
    await s.resolve(r['id']);assert await s.get_by_idempotency_key('chain:'+r['id'])==first


@pytest.mark.asyncio
async def test_failed_follow_up_creation_rolls_back_the_original_resolution(tmp_path):
    store=await make_store(tmp_path);s=ReminderService(store)
    r=await s.create(body(chain_follow_up_text='Follow up',chain_follow_up_offset_seconds=60))
    await store.execute("CREATE TRIGGER fixture_refuse_follow BEFORE INSERT ON reminders WHEN NEW.idempotency_key LIKE 'chain:%' BEGIN SELECT RAISE(ABORT,'fixture storage failure'); END")
    with pytest.raises(Exception,match='fixture storage failure'):
        await s.resolve(r['id'])
    assert (await store.fetchone('SELECT status FROM reminders WHERE id=?',(r['id'],)))['status']=='OPEN'
    assert await s.get_by_idempotency_key('chain:'+r['id']) is None


@pytest.mark.parametrize('expr',['at 13pm','at 12:77','in '+('9'*100)+' days'])
def test_invalid_time_is_a_typed_refusal(expr):
    with pytest.raises(TimeParseError):parse_due_expression(expr)


def test_relative_time_means_elapsed_time_across_dst():
    now=datetime(2026,3,29,0,30,tzinfo=ZoneInfo('Europe/London'))
    assert parse_due_expression('in 2 hours',now=now)==int(now.timestamp())+7200


@pytest.mark.parametrize('now',[datetime(2026,3,29,0,0,tzinfo=ZoneInfo('Europe/London')),datetime(2026,10,25,0,0,tzinfo=ZoneInfo('Europe/London'))])
def test_nonexistent_or_ambiguous_local_wall_time_is_not_silently_chosen(now):
    with pytest.raises(TimeParseError):parse_due_expression('at 1:30',now=now)


@pytest.mark.asyncio
@pytest.mark.parametrize('failure_point',['before_event','lost_event_ack','lost_attention_ack','lost_final_ack'])
async def test_pending_delivery_recovers_original_effect_without_duplicate_owner_events(tmp_path,monkeypatch,failure_point):
    from van_gateway.events.bus import EventBus
    from van_gateway.attention.engine import AttentionEngine
    store=await make_store(tmp_path);s=ReminderService(store);bus=EventBus(store);attention=AttentionEngine(store)
    r=await s.create(body(project_id='project-alpha'));await s.fire_due(now=5)
    publish=bus.publish;upsert=attention.upsert;execute=store.execute;failed=False
    async def failing_publish(*args,**kwargs):
        nonlocal failed
        if not failed and failure_point=='before_event':failed=True;raise RuntimeError('fixture lost delivery')
        result=await publish(*args,**kwargs)
        if not failed and failure_point=='lost_event_ack':failed=True;raise RuntimeError('fixture lost delivery')
        return result
    async def failing_attention(**kwargs):
        nonlocal failed
        result=await upsert(**kwargs)
        if not failed and failure_point=='lost_attention_ack':failed=True;raise RuntimeError('fixture lost delivery')
        return result
    async def failing_execute(sql,params=()):
        nonlocal failed
        if not failed and failure_point=='lost_final_ack' and params and str(params[0]).startswith('reminder_publication_receipt:'):
            failed=True;raise RuntimeError('fixture lost delivery')
        return await execute(sql,params)
    monkeypatch.setattr(bus,'publish',failing_publish);monkeypatch.setattr(attention,'upsert',failing_attention);monkeypatch.setattr(store,'execute',failing_execute)
    with pytest.raises(RuntimeError,match='fixture lost delivery'):await s.publish_pending(bus,attention)
    assert failed and not await store.fetchone('SELECT value FROM runtime_meta WHERE key=?',('reminder_publication_receipt:'+r['id'],))
    assert (await store.fetchone('SELECT status FROM reminders WHERE id=?',(r['id'],)))['status']=='FIRED'
    assert await s.fire_due(now=5)==[]
    assert await s.publish_pending(bus,attention)==1
    assert await s.publish_pending(bus,attention)==0
    assert (await store.fetchone("SELECT count(*) AS n FROM events WHERE event_type='reminder.fired'"))['n']==1
    item=await store.fetchone('SELECT * FROM attention WHERE dedupe_key=?',('reminder:'+r['id'],))
    assert item is not None
    assert item['project_id']=='project-alpha'


@pytest.mark.asyncio
async def test_legacy_delivery_and_owner_acknowledgement_are_preserved(tmp_path):
    from van_gateway.events.bus import EventBus
    from van_gateway.attention.engine import AttentionEngine
    from van_gateway.models import AttentionSeverity
    store=await make_store(tmp_path);s=ReminderService(store);bus=EventBus(store);attention=AttentionEngine(store)
    r=await s.create(body());await s.fire_due(now=5)
    original=await bus.publish('reminder.fired',{'reminder_id':r['id'],'text':r['text'],'due_at_unix':r['due_at_unix']})
    item=await attention.upsert(title=r['text'],severity=AttentionSeverity.FOLLOW_UP,source='reminder',dedupe_key='reminder:'+r['id'])
    await attention.acknowledge(item.id)
    assert await s.publish_pending(bus,attention)==1
    rows=await store.fetchall("SELECT seq FROM events WHERE event_type='reminder.fired'")
    assert len(rows)==1 and rows[0]['seq']==original
    assert (await store.fetchone('SELECT state FROM attention WHERE id=?',(item.id,)))['state']=='ACKNOWLEDGED'


@pytest.mark.asyncio
async def test_delivery_ack_committed_before_lost_reply_prevents_another_attempt(tmp_path,monkeypatch):
    from van_gateway.events.bus import EventBus
    from van_gateway.attention.engine import AttentionEngine
    store=await make_store(tmp_path);s=ReminderService(store);bus=EventBus(store);attention=AttentionEngine(store)
    await s.create(body());await s.fire_due(now=5);original=store.execute
    async def lost_ack(sql,params=()):
        await original(sql,params)
        if params and str(params[0]).startswith('reminder_publication_receipt:'):
            raise RuntimeError('fixture ack committed then lost')
    monkeypatch.setattr(store,'execute',lost_ack)
    with pytest.raises(RuntimeError,match='fixture ack committed'):await s.publish_pending(bus,attention)
    assert await s.publish_pending(bus,attention)==0
    assert (await store.fetchone("SELECT count(*) AS n FROM events WHERE event_type='reminder.fired'"))['n']==1


@pytest.mark.asyncio
async def test_resolve_and_cancel_conflict_instead_of_scheduling_after_cancellation(tmp_path):
    store=await make_store(tmp_path);s=ReminderService(store)
    row=await s.create(body(chain_follow_up_text='Follow up',chain_follow_up_offset_seconds=60))
    results=await asyncio.gather(s.resolve(row['id']),s.cancel(row['id']),return_exceptions=True)
    assert sum(isinstance(r,ValueError) for r in results)==1
    status=(await store.fetchone('SELECT status FROM reminders WHERE id=?',(row['id'],)))['status']
    assert (await s.get_by_idempotency_key('chain:'+row['id']) is not None)==(status=='RESOLVED')


@pytest.mark.asyncio
async def test_explicit_epoch_zero_is_not_replaced_by_current_time(tmp_path):
    s=ReminderService(await make_store(tmp_path));await s.create(body())
    assert await s.fire_due(now=0)==[]


def test_out_of_range_epoch_is_a_typed_refusal():
    with pytest.raises(TimeParseError,match='time_out_of_range'):parse_due_expression('253402300800')
