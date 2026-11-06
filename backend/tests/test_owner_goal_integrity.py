"""Owner-authored goals must not be partial writes or invented mission links."""
import sqlite3
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from van_gateway.goals.models import GoalCreate,GoalPatch,WatchCreate,WatchSourceKind
from van_gateway.goals.service import GoalService,GoalServiceError
from van_gateway.attention.engine import AttentionEngine
from van_gateway.storage.db import Store


async def service(tmp_path):
    store=Store(str(tmp_path/'goals.sqlite'));await store.migrate()
    return GoalService(store,AttentionEngine(store))


@pytest.mark.asyncio
async def test_failed_second_milestone_insert_rolls_back_the_entire_goal(tmp_path):
    s=await service(tmp_path)
    await s.store.execute("CREATE TRIGGER fixture_refuse_milestone BEFORE INSERT ON goal_milestones WHEN NEW.title='second' BEGIN SELECT RAISE(ABORT,'milestone unavailable'); END")
    with pytest.raises(Exception,match='milestone unavailable'):
        await s.create(GoalCreate(title='Complete owner intent',milestones=['first','second']))
    assert not await s.store.fetchall('SELECT * FROM owner_goals')
    assert not await s.store.fetchall('SELECT * FROM goal_milestones')


@pytest.mark.asyncio
async def test_goal_cannot_claim_a_mission_that_does_not_exist(tmp_path):
    s=await service(tmp_path);goal=await s.create(GoalCreate(title='Real linked work'))
    with pytest.raises(GoalServiceError,match='MISSION_UNKNOWN'):
        await s.link_mission(goal.goal_id,'nonexistent-mission')
    assert (await s.get(goal.goal_id)).mission_ids==[]


@pytest.mark.asyncio
async def test_concurrent_goal_patch_preserves_an_independent_owner_description_change(tmp_path,monkeypatch):
    s=await service(tmp_path);goal=await s.create(GoalCreate(title='Original',description='Before'))
    connection=s.store.connection;attempted=committed=False
    @asynccontextmanager
    async def interleaved():
        async with connection() as db:
            async def execute(sql,params=()):
                cursor=await db.execute(sql,params)
                if 'SELECT * FROM owner_goals WHERE goal_id' not in sql:return cursor
                async def fetchone():
                    nonlocal attempted,committed
                    row=await cursor.fetchone()
                    if not attempted:
                        attempted=True
                        with sqlite3.connect(s.store.path,timeout=0) as owner:
                            try:
                                owner.execute("UPDATE owner_goals SET description='Independent owner edit' WHERE goal_id=?",(goal.goal_id,));owner.commit();committed=True
                            except sqlite3.OperationalError as exc:assert 'locked' in str(exc)
                    return row
                return SimpleNamespace(fetchone=fetchone)
            yield SimpleNamespace(execute=execute,commit=db.commit)
    monkeypatch.setattr(s.store,'connection',interleaved)
    await s.patch(goal.goal_id,GoalPatch(title='New title'))
    assert attempted
    if not committed:await s.store.execute("UPDATE owner_goals SET description='Independent owner edit' WHERE goal_id=?",(goal.goal_id,))
    current=await s.get(goal.goal_id)
    assert current.title=='New title' and current.description=='Independent owner edit'


@pytest.mark.parametrize('factory',[
    lambda:GoalCreate(title='   '),lambda:GoalPatch(title='\t'),
    lambda:WatchCreate(title=' ',source_kind=WatchSourceKind.PROVIDER,target='source',condition={'kind':'CHANGED'}),
    lambda:WatchCreate(title='Valid',source_kind=WatchSourceKind.PROVIDER,target='   ',condition={'kind':'CHANGED'}),
    lambda:GoalCreate(title='Valid',milestones=['First','   ']),
])
def test_blank_owner_input_is_refused_instead_of_silently_becoming_missing_work(factory):
    with pytest.raises(ValidationError):factory()


@pytest.mark.asyncio
async def test_goal_read_uses_one_snapshot_for_goal_fields_and_milestones(tmp_path,monkeypatch):
    s=await service(tmp_path);goal=await s.create(GoalCreate(title='Before',milestones=['Before milestone']))
    connection=s.store.connection;changed=False
    @asynccontextmanager
    async def interleaved():
        async with connection() as db:
            async def execute(sql,params=()):
                cursor=await db.execute(sql,params)
                if 'SELECT * FROM owner_goals WHERE goal_id' not in sql:return cursor
                async def fetchone():
                    nonlocal changed
                    row=await cursor.fetchone()
                    if not changed:
                        changed=True
                        with sqlite3.connect(s.store.path) as owner:
                            owner.execute("UPDATE owner_goals SET title='After' WHERE goal_id=?",(goal.goal_id,))
                            owner.execute("UPDATE goal_milestones SET title='After milestone' WHERE goal_id=?",(goal.goal_id,));owner.commit()
                    return row
                return SimpleNamespace(fetchone=fetchone)
            yield SimpleNamespace(execute=execute,commit=db.commit)
    monkeypatch.setattr(s.store,'connection',interleaved)
    snapshot=await s.get(goal.goal_id)
    assert changed
    assert (snapshot.title,snapshot.milestones[0].title) in {('Before','Before milestone'),('After','After milestone')}
    current=await s.get(goal.goal_id)
    assert current.title=='After' and current.milestones[0].title=='After milestone'


@pytest.mark.asyncio
async def test_numeric_watch_threshold_is_not_a_boolean(tmp_path):
    s=await service(tmp_path)
    with pytest.raises(GoalServiceError,match='WATCH_THRESHOLD_INVALID'):
        await s.create_watch(WatchCreate(title='Price threshold',source_kind=WatchSourceKind.PROVIDER,
            target='fixture:price',condition={'kind':'NUMERIC_ABOVE','threshold':True}))
    assert await s.list_watches()==[]


@pytest.mark.asyncio
async def test_goal_status_filter_and_returned_goals_share_one_snapshot(tmp_path,monkeypatch):
    from van_gateway.goals.models import GoalStatus
    s=await service(tmp_path);goal=await s.create(GoalCreate(title='Active goal'))
    connection=s.store.connection;changed=False
    @asynccontextmanager
    async def interleaved():
        async with connection() as db:
            async def execute(sql,params=()):
                cursor=await db.execute(sql,params)
                if 'SELECT goal_id FROM owner_goals WHERE status' not in sql:return cursor
                async def fetchall():
                    nonlocal changed
                    rows=await cursor.fetchall()
                    if not changed:
                        changed=True
                        with sqlite3.connect(s.store.path) as owner:
                            owner.execute("UPDATE owner_goals SET status='PAUSED' WHERE goal_id=?",(goal.goal_id,));owner.commit()
                    return rows
                return SimpleNamespace(fetchall=fetchall)
            yield SimpleNamespace(execute=execute,commit=db.commit)
    monkeypatch.setattr(s.store,'connection',interleaved)
    rows=await s.list(GoalStatus.ACTIVE)
    assert changed and len(rows)==1
    assert rows[0].status is GoalStatus.ACTIVE
    assert (await s.get(goal.goal_id)).status is GoalStatus.PAUSED


async def existing_mission(s):
    from van_gateway.mission.service import MissionService
    from van_gateway.mission.models import MissionOrigin
    from van_gateway.models import OriginChannel
    return await MissionService(s.store).create(owner_principal_id='owner',origin=MissionOrigin.OWNER_VOICE,
        origin_channel=OriginChannel.VOICE,title='Existing mission',goal='Real execution reference')


@pytest.mark.asyncio
@pytest.mark.parametrize('operation',['milestone','link'])
async def test_goal_change_timestamp_includes_its_milestone_and_link_changes(tmp_path,operation):
    s=await service(tmp_path);goal=await s.create(GoalCreate(title='Visible progress',milestones=['First']),now_ms=1000)
    if operation=='milestone':await s.set_milestone(goal.goal_id,goal.milestones[0].milestone_id,True,now_ms=2000)
    else:
        mission=await existing_mission(s)
        await s.link_mission(goal.goal_id,mission.mission_id,now_ms=2000)
        await s.link_mission(goal.goal_id,mission.mission_id,now_ms=3000)
    assert (await s.get(goal.goal_id)).updated_at_ms==2000


@pytest.mark.asyncio
@pytest.mark.parametrize('operation',['milestone','link'])
async def test_goal_parent_update_failure_cannot_commit_a_child_change(tmp_path,operation):
    s=await service(tmp_path);goal=await s.create(GoalCreate(title='Atomic child change',milestones=['First']),now_ms=1000)
    mission=await existing_mission(s)
    await s.store.execute("CREATE TRIGGER fixture_no_goal_update BEFORE UPDATE ON owner_goals BEGIN SELECT RAISE(ABORT,'parent update unavailable'); END")
    with pytest.raises(Exception,match='parent update unavailable'):
        if operation=='milestone':await s.set_milestone(goal.goal_id,goal.milestones[0].milestone_id,True,now_ms=2000)
        else:await s.link_mission(goal.goal_id,mission.mission_id,now_ms=2000)
    current=await s.get(goal.goal_id)
    assert current.updated_at_ms==1000 and current.milestones[0].done is False and current.mission_ids==[]
