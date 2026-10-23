"""Actual persisted owner-memory observations; no execution or learned-truth grants."""
import asyncio
import pytest
from conftest_automation import make_store
from van_gateway.understanding.memory import IntentContinuityGraph, IntentEdgeType
from van_gateway.learning.feed import LearningFeed
from van_gateway.mission.models import MissionOrigin
from van_gateway.mission.service import MissionService
from van_gateway.models import OriginChannel

async def graph_at(tmp_path):
    return IntentContinuityGraph(await make_store(tmp_path))

@pytest.mark.asyncio
async def test_concurrent_first_observations_form_one_node_with_every_observation(tmp_path):
    graph=await graph_at(tmp_path)
    results=await asyncio.gather(*(graph.observe(owner_goal='Preserve the owner constraints',project_id=f'project-{n}') for n in range(8)))
    rows=await graph.store.fetchall('SELECT * FROM intent_nodes')
    assert len(rows)==1 and len({r.intent_id for r in results})==1
    current=await graph.get(results[0].intent_id)
    assert current.observation_count==8 and current.projects==[f'project-{n}' for n in range(8)]

@pytest.mark.asyncio
async def test_concurrent_existing_observations_do_not_drop_counts_or_project_context(tmp_path):
    graph=await graph_at(tmp_path);original=await graph.observe(owner_goal='Continue the plan')
    await asyncio.gather(*(graph.observe(owner_goal='Continue the plan',project_id=f'project-{n}') for n in range(8)))
    current=await graph.get(original.intent_id)
    assert current.observation_count==9 and len(current.projects)==8

@pytest.mark.asyncio
async def test_failed_superseding_update_does_not_leave_a_committed_relationship(tmp_path):
    graph=await graph_at(tmp_path);old=await graph.observe(owner_goal='Previous goal');new=await graph.observe(owner_goal='Replacement goal')
    await graph.store.execute("CREATE TRIGGER fixture_refuse_supersede BEFORE UPDATE ON intent_nodes BEGIN SELECT RAISE(ABORT,'cannot update intent'); END")
    with pytest.raises(Exception,match='cannot update intent'):
        await graph.relate(from_intent_id=new.intent_id,to_intent_id=old.intent_id,edge_type=IntentEdgeType.SUPERSEDES)
    assert not await graph.store.fetchall('SELECT * FROM intent_edges')
    assert (await graph.get(old.intent_id)).status.value=='ACTIVE'

@pytest.mark.asyncio
async def test_replaying_same_real_mission_does_not_manufacture_repetition_evidence(tmp_path):
    graph=await graph_at(tmp_path)
    mission=await MissionService(graph.store).create(owner_principal_id='owner',origin=MissionOrigin.OWNER_VOICE,origin_channel=OriginChannel.VOICE,title='One request',goal='Read the current balance')
    feed=LearningFeed(graph.store)
    await feed.record_mission_opened(mission)
    await feed.record_mission_opened(mission)
    await feed.record_mission_opened(mission)
    rows=await graph.store.fetchall('SELECT * FROM intent_nodes')
    assert len(rows)==1 and rows[0]['observation_count']==1 and rows[0]['horizon']=='EPHEMERAL'
    assert len(await graph.store.fetchall('SELECT * FROM intent_missions'))==1

@pytest.mark.asyncio
async def test_repeated_owner_goals_keep_later_constraints_without_dropping_earlier_ones(tmp_path):
    graph=await graph_at(tmp_path)
    node=await graph.observe(owner_goal='Ship the app',constraints=['Keep approval checks'])
    current=await graph.observe(owner_goal='Ship the app',constraints=['Preserve privacy','Keep approval checks'])
    assert current.intent_id==node.intent_id and current.constraints==['Keep approval checks','Preserve privacy']

@pytest.mark.asyncio
async def test_old_observation_does_not_move_latest_owner_evidence_backwards(tmp_path):
    graph=await graph_at(tmp_path);node=await graph.observe(owner_goal='Current evidence',now_ms=5000)
    current=await graph.observe(owner_goal='Current evidence',now_ms=1000)
    assert current.latest_observed_ms==5000 and current.first_observed_ms==1000

@pytest.mark.asyncio
async def test_mission_link_failure_rolls_back_the_observation_it_would_claim(tmp_path):
    graph=await graph_at(tmp_path)
    mission=await MissionService(graph.store).create(owner_principal_id='owner',origin=MissionOrigin.OWNER_VOICE,origin_channel=OriginChannel.VOICE,title='Atomic source',goal='Do not invent a repeated instruction')
    await graph.store.execute("CREATE TRIGGER fixture_refuse_link BEFORE INSERT ON intent_missions BEGIN SELECT RAISE(ABORT,'cannot link source'); END")
    with pytest.raises(Exception,match='cannot link source'):
        await LearningFeed(graph.store).record_mission_opened(mission)
    assert not await graph.store.fetchall('SELECT * FROM intent_nodes')
    assert not await graph.store.fetchall('SELECT * FROM intent_missions')

@pytest.mark.asyncio
async def test_mission_observation_rejects_a_missing_or_changed_source(tmp_path):
    graph=await graph_at(tmp_path)
    with pytest.raises(ValueError,match='INTENT_MISSION_UNKNOWN'):
        await graph.observe(owner_goal='Claimed mission',mission_id='missing')
    mission=await MissionService(graph.store).create(owner_principal_id='owner',origin=MissionOrigin.OWNER_VOICE,origin_channel=OriginChannel.VOICE,title='Native source',goal='Original source')
    with pytest.raises(ValueError,match='INTENT_MISSION_SCOPE_CONFLICT'):
        await graph.observe(owner_goal='Invented source',mission_id=mission.mission_id)
    assert not await graph.store.fetchall('SELECT * FROM intent_nodes')

@pytest.mark.asyncio
async def test_self_or_cyclic_supersession_cannot_retire_all_owner_goals(tmp_path):
    graph=await graph_at(tmp_path);old=await graph.observe(owner_goal='Original');new=await graph.observe(owner_goal='Replacement')
    with pytest.raises(ValueError,match='INTENT_SELF_RELATION'):
        await graph.relate(from_intent_id=old.intent_id,to_intent_id=old.intent_id,edge_type=IntentEdgeType.SUPERSEDES)
    await graph.relate(from_intent_id=new.intent_id,to_intent_id=old.intent_id,edge_type=IntentEdgeType.SUPERSEDES)
    with pytest.raises(ValueError,match='INTENT_SUPERSESSION_CYCLE'):
        await graph.relate(from_intent_id=old.intent_id,to_intent_id=new.intent_id,edge_type=IntentEdgeType.SUPERSEDES)
    assert (await graph.get(new.intent_id)).status.value=='ACTIVE'
    assert (await graph.get(old.intent_id)).status.value=='SUPERSEDED'

@pytest.mark.asyncio
async def test_whitespace_is_not_an_owner_objective(tmp_path):
    graph=await graph_at(tmp_path)
    with pytest.raises(ValueError,match='INTENT_GOAL_REQUIRED'):await graph.observe(owner_goal='  ')
    assert not await graph.store.fetchall('SELECT * FROM intent_nodes')

@pytest.mark.asyncio
async def test_independent_writer_cannot_be_lost_between_observation_read_and_update(tmp_path,monkeypatch):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    import sqlite3
    graph=await graph_at(tmp_path);node=await graph.observe(owner_goal='Current owner intent')
    connection=graph.store.connection;attempted=committed=False
    @asynccontextmanager
    async def interleaved():
        async with connection() as db:
            class Connection:
                def __getattr__(self,name):return getattr(db,name)
                async def execute(self,sql,params=()):
                    cursor=await db.execute(sql,params)
                    if 'SELECT * FROM intent_nodes WHERE owner_goal' not in sql:return cursor
                    async def fetchone():
                        nonlocal attempted,committed
                        row=await cursor.fetchone()
                        if not attempted:
                            attempted=True
                            with sqlite3.connect(graph.store.path,timeout=0) as independent:
                                try:
                                    independent.execute('UPDATE intent_nodes SET observation_count=9 WHERE intent_id=?',(node.intent_id,));independent.commit();committed=True
                                except sqlite3.OperationalError as exc:assert 'locked' in str(exc)
                        return row
                    return SimpleNamespace(fetchone=fetchone)
            yield Connection()
    monkeypatch.setattr(graph.store,'connection',interleaved)
    try:result=await graph.observe(owner_goal='Current owner intent')
    except Exception as exc:result=exc
    assert attempted and not isinstance(result,Exception)
    current=await graph.get(node.intent_id)
    assert current.observation_count==(10 if committed else 2)

@pytest.mark.asyncio
async def test_legacy_mission_link_checks_real_source_and_original_goal(tmp_path):
    graph=await graph_at(tmp_path);node=await graph.observe(owner_goal='Exact original goal')
    with pytest.raises(ValueError,match='INTENT_MISSION_UNKNOWN'):await graph.link_mission(node.intent_id,'missing')
    mission=await MissionService(graph.store).create(owner_principal_id='owner',origin=MissionOrigin.OWNER_VOICE,origin_channel=OriginChannel.VOICE,title='Original',goal='Exact original goal')
    other=await graph.observe(owner_goal='Different goal')
    with pytest.raises(ValueError,match='INTENT_MISSION_SCOPE_CONFLICT'):await graph.link_mission(other.intent_id,mission.mission_id)
    await graph.link_mission(node.intent_id,mission.mission_id,now_ms=1000)
    await graph.link_mission(node.intent_id,mission.mission_id,now_ms=2000)
    rows=await graph.store.fetchall('SELECT * FROM intent_missions')
    assert len(rows)==1 and rows[0]['linked_at_ms']==1000
