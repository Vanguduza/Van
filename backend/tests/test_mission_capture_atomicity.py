"""Original mission capture, its event and pending local projections are one fact."""
from contextlib import asynccontextmanager
import sqlite3
import pytest
from conftest_automation import make_store
from van_gateway.command.mission_link import CommandMissionLink
from van_gateway.mission.models import MissionEventType,MissionOrigin,MissionState
from van_gateway.mission.service import MissionService
from van_gateway.models import OriginChannel
from test_command_mission_creation_race import request

class BrokenCreatedEvent(MissionService):
    async def _persist_event(self,db,event):
        if event.event_type is MissionEventType.MISSION_CREATED:
            await db.execute('INSERT INTO missions(mission_id) VALUES(?)',('invalid-native-event',))
        return await super()._persist_event(db,event)

@pytest.mark.asyncio
async def test_rejected_native_created_event_rolls_back_mission_and_learning_delivery(tmp_path):
    store=await make_store(tmp_path)
    with pytest.raises(sqlite3.IntegrityError,match='NOT NULL'):
        await CommandMissionLink(BrokenCreatedEvent(store)).open(request(),effective_action_class=request().action_class,owner_approved=False)
    assert not await store.fetchall('SELECT * FROM missions')
    assert not await store.fetchall('SELECT * FROM mission_events')
    assert not await store.fetchall('SELECT * FROM mission_learning_outbox')

@pytest.mark.asyncio
async def test_uncommitted_capture_cannot_feed_optional_owner_learning(tmp_path):
    store=await make_store(tmp_path);observed=[]
    class Learning:
        async def record_mission_opened(self,mission,**kw):observed.append(mission.mission_id)
    with pytest.raises(sqlite3.IntegrityError,match='NOT NULL'):
        await BrokenCreatedEvent(store,learning=Learning()).create(owner_principal_id='owner',origin=MissionOrigin.OWNER_UI,
            origin_channel=OriginChannel.UI,title='Owner work',goal='A native capture must either commit or fail')
    assert not observed

@pytest.mark.asyncio
async def test_lost_native_capture_commit_ack_recovers_the_original_complete_event(tmp_path,monkeypatch):
    store=await make_store(tmp_path);original=store.connection;armed=True
    @asynccontextmanager
    async def uncertain():
        async with original() as db:
            class Connection:
                def __getattr__(self,name):return getattr(db,name)
                async def commit(self):
                    nonlocal armed
                    await db.commit()
                    if armed:armed=False;raise OSError('native capture acknowledgement lost')
            yield Connection()
    monkeypatch.setattr(store,'connection',uncertain)
    link=CommandMissionLink(MissionService(store));body=request()
    with pytest.raises(OSError,match='native capture acknowledgement lost'):
        await link.open(body,effective_action_class=body.action_class,owner_approved=False)
    restored=await link.open(body,effective_action_class=body.action_class,owner_approved=False)
    assert restored.state is MissionState.CAPTURED
    events=await store.fetchall("SELECT * FROM mission_events WHERE event_type='mission.created'")
    assert len(events)==1 and events[0]['mission_id']==restored.mission_id
    assert len(await store.fetchall('SELECT * FROM missions'))==1
    assert len(await store.fetchall('SELECT * FROM mission_learning_outbox'))==1

@pytest.mark.asyncio
async def test_process_death_after_capture_commit_preserves_native_event_and_original_replay(tmp_path):
    import asyncio,os,subprocess,sys
    from pathlib import Path
    from van_gateway.storage.db import Store
    database=tmp_path/'capture-crash.sqlite3'
    code="""
import asyncio,os,sys
from contextlib import asynccontextmanager
from van_gateway.storage.db import Store
from van_gateway.command.mission_link import CommandMissionLink
from van_gateway.mission.service import MissionService
from test_command_mission_creation_race import request
async def work():
 store=Store(sys.argv[1]);await store.migrate();original=store.connection
 @asynccontextmanager
 async def crashing():
  async with original() as db:
   class Connection:
    def __getattr__(self,name):return getattr(db,name)
    async def commit(self):
     await db.commit();os._exit(33)
   yield Connection()
 store.connection=crashing
 body=request('native-capture-crash-command')
 await CommandMissionLink(MissionService(store)).open(body,effective_action_class=body.action_class,owner_approved=False)
asyncio.run(work())
"""
    root=Path(__file__).resolve().parents[2]
    result=await asyncio.to_thread(subprocess.run,[sys.executable,'-B','-c',code,str(database)],cwd=root,
        env=dict(os.environ,PYTHONPATH='backend:backend/tests:.:trading'),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=30)
    assert result.returncode==33,result.stderr
    store=Store(str(database));rows=await store.fetchall('SELECT * FROM missions');assert len(rows)==1
    events=await store.fetchall("SELECT * FROM mission_events WHERE event_type='mission.created'")
    assert len(events)==1 and events[0]['mission_id']==rows[0]['mission_id']
    body=request('native-capture-crash-command')
    replay=await CommandMissionLink(MissionService(store)).open(body,effective_action_class=body.action_class,owner_approved=False)
    assert replay.mission_id==rows[0]['mission_id']
    assert len(await store.fetchall('SELECT * FROM mission_events'))==1


@pytest.mark.asyncio
async def test_failed_capture_publication_retains_the_original_native_event_for_replay(tmp_path):
    store=await make_store(tmp_path)
    class UnavailableBus:
        async def publish(self,*a,**kw):raise OSError('native event publication reply unavailable')
    body=request();link=CommandMissionLink(MissionService(store,bus=UnavailableBus()))
    with pytest.raises(OSError,match='native event publication reply unavailable'):
        await link.open(body,effective_action_class=body.action_class,owner_approved=False)
    rows=await store.fetchall('SELECT * FROM missions');assert len(rows)==1
    events=await store.fetchall('SELECT * FROM mission_events')
    assert len(events)==1 and events[0]['event_type']=='mission.created' and events[0]['mission_id']==rows[0]['mission_id']
    recovered=await CommandMissionLink(MissionService(store)).open(body,effective_action_class=body.action_class,owner_approved=False)
    assert recovered.mission_id==rows[0]['mission_id'] and recovered.state is MissionState.CAPTURED
    assert len(await store.fetchall('SELECT * FROM mission_events'))==1
    assert len(await store.fetchall('SELECT * FROM mission_learning_outbox'))==1

@pytest.mark.asyncio
async def test_capture_is_published_only_after_its_original_native_event_is_visible(tmp_path):
    store=await make_store(tmp_path);observed=[]
    class NativeObserver:
        async def publish(self,*a,**kw):
            mission=await store.fetchone('SELECT * FROM missions')
            assert mission is not None and mission['state']=='CAPTURED'
            events=await store.fetchall("SELECT * FROM mission_events WHERE event_type='mission.created'")
            assert len(events)==1 and events[0]['mission_id']==mission['mission_id']
            assert events[0]['occurred_at_ms']==mission['created_at_ms']
            assert events[0]['actor']=='OWNER_DEVICE'
            observed.append(mission['mission_id'])
    body=request();mission=await CommandMissionLink(MissionService(store,bus=NativeObserver())).open(body,
        effective_action_class=body.action_class,owner_approved=False)
    assert observed==[mission.mission_id]
