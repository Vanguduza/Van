"""Only real owner instructions may drive goals, and old source replay cannot undo erasure."""
import pytest
from tests.test_owner_memory_erasure import client,_settings,_pair,_approve
from van_gateway.learning.feed import LearningFeed
from van_gateway.mission.service import MissionService
from van_gateway.mission.models import MissionOrigin
from van_gateway.models import OriginChannel
from conftest_automation import make_store

@pytest.mark.asyncio
async def test_old_owner_mission_cannot_recreate_intents_after_native_erasure(client):
    ac,app,_=client;key=await _pair(ac,app)
    body,_=await _approve(ac,app,key,'forget owner-derived memory store owner_facts','original-goal-source')
    row=await app.state.store.fetchone("SELECT mission_id FROM missions WHERE json_extract(authority_envelope_json,'$.source_command_id')=?",(body['command_id'],))
    original=await MissionService(app.state.store).get(row['mission_id'])
    assert await app.state.store.fetchall('SELECT * FROM intent_nodes')
    await _approve(ac,app,key,'forget owner-derived memory store intent_nodes','erase-goal-source')
    assert not await app.state.store.fetchall('SELECT * FROM intent_nodes')
    result=await LearningFeed(app.state.store).record_mission_opened(original)
    assert result['intent_id'] is None
    assert not await app.state.store.fetchall('SELECT * FROM intent_nodes')

@pytest.mark.asyncio
@pytest.mark.parametrize('origin,channel',[(MissionOrigin.AUTOMATION_EVENT,OriginChannel.AUTOMATION),(MissionOrigin.SCHEDULED,OriginChannel.SYSTEM_EVENT)])
async def test_automatic_work_cannot_be_counted_as_repeated_owner_intent(tmp_path,origin,channel):
    store=await make_store(tmp_path);missions=MissionService(store,learning=LearningFeed(store))
    for _ in range(3):
        await missions.create(owner_principal_id='owner',origin=origin,origin_channel=channel,
            title='Automatic event',goal='An external event VAN processed')
    assert not await store.fetchall('SELECT * FROM intent_nodes')

@pytest.mark.asyncio
async def test_presence_of_owner_origin_without_native_command_evidence_does_not_create_stated_goals(tmp_path):
    store=await make_store(tmp_path);missions=MissionService(store,learning=LearningFeed(store))
    await missions.create(owner_principal_id='owner',origin=MissionOrigin.OWNER_UI,origin_channel=OriginChannel.UI,
        title='Claimed origin',goal='A raw native object without a verified source')
    assert not await store.fetchall('SELECT * FROM intent_nodes')

@pytest.mark.asyncio
async def test_selective_goal_erasure_does_not_let_old_source_attach_to_a_fresh_same_goal(client):
    from van_gateway.understanding.records import OwnerRecords,record_identity
    ac,app,_=client;key=await _pair(ac,app)
    body,_=await _approve(ac,app,key,'forget owner-derived memory store owner_facts','selective-goal-original')
    row=await app.state.store.fetchone("SELECT mission_id FROM missions WHERE json_extract(authority_envelope_json,'$.source_command_id')=?",(body['command_id'],))
    mission=await MissionService(app.state.store).get(row['mission_id'])
    link=await app.state.store.fetchone('SELECT intent_id FROM intent_missions WHERE mission_id=?',(mission.mission_id,))
    old=await app.state.store.fetchone('SELECT * FROM intent_nodes WHERE intent_id=?',(link['intent_id'],))
    target=await OwnerRecords(app.state.store).exact('intent_nodes',record_identity('intent_nodes',old))
    await _approve(ac,app,key,target['erasure']['command_text'],'selective-goal-erasure')
    assert await LearningFeed(app.state.store).record_mission_opened(mission)=={'intent_id':None,'decision_id':(await app.state.store.fetchone('SELECT decision_id FROM decision_fingerprints WHERE mission_id=?',(mission.mission_id,)))['decision_id']}
    new_body,_=await _approve(ac,app,key,'forget owner-derived memory store owner_facts','selective-goal-fresh')
    new_row=await app.state.store.fetchone("SELECT mission_id FROM missions WHERE json_extract(authority_envelope_json,'$.source_command_id')=?",(new_body['command_id'],))
    new_link=await app.state.store.fetchone('SELECT intent_id FROM intent_missions WHERE mission_id=?',(new_row['mission_id'],))
    assert new_link is not None
    assert new_link['intent_id']!=old['intent_id']
    assert (await app.state.store.fetchone('SELECT observation_count FROM intent_nodes WHERE intent_id=?',(new_link['intent_id'],)))['observation_count']==1
    assert (await LearningFeed(app.state.store).record_mission_opened(mission))['intent_id'] is None
    assert (await app.state.store.fetchone('SELECT observation_count FROM intent_nodes WHERE intent_id=?',(new_link['intent_id'],)))['observation_count']==1

@pytest.mark.asyncio
async def test_goal_source_receipt_is_atomic_with_node_count_and_mission_link(tmp_path):
    from test_owner_memory_has_a_producer import _open
    store=await make_store(tmp_path);mission=await _open(MissionService(store),goal='One actual owner request')
    await store.execute("CREATE TRIGGER fixture_reject_intent_receipt BEFORE INSERT ON runtime_meta WHEN NEW.key GLOB 'intent_observation_source:*' BEGIN SELECT RAISE(ABORT,'intent receipt unavailable'); END")
    with pytest.raises(Exception,match='intent receipt unavailable'):await LearningFeed(store).record_mission_opened(mission)
    assert not await store.fetchall('SELECT * FROM intent_nodes')
    assert not await store.fetchall('SELECT * FROM intent_missions')
    await store.execute('DROP TRIGGER fixture_reject_intent_receipt')
    result=await LearningFeed(store).record_mission_opened(mission)
    assert result['intent_id'] is not None
    assert len(await store.fetchall('SELECT * FROM intent_nodes'))==1

@pytest.mark.asyncio
async def test_concurrent_real_source_replays_produce_one_goal_observation(tmp_path):
    import asyncio
    from test_owner_memory_has_a_producer import _open
    store=await make_store(tmp_path);mission=await _open(MissionService(store),goal='Preserve this owner request')
    feed=LearningFeed(store)
    results=await asyncio.gather(*(feed.record_mission_opened(mission) for _ in range(6)))
    assert len({r['intent_id'] for r in results})==1
    rows=await store.fetchall('SELECT * FROM intent_nodes')
    assert len(rows)==1 and rows[0]['observation_count']==1
    assert len(await store.fetchall('SELECT * FROM runtime_meta WHERE key GLOB ?',('intent_observation_source:*',)))==1

@pytest.mark.asyncio
async def test_lost_native_goal_commit_ack_replays_original_count_and_identity(tmp_path,monkeypatch):
    from contextlib import asynccontextmanager
    from test_owner_memory_has_a_producer import _open
    store=await make_store(tmp_path);mission=await _open(MissionService(store),goal='Original goal source')
    original_connection=store.connection;armed=True
    @asynccontextmanager
    async def uncertain():
        async with original_connection() as db:
            class Connection:
                def __getattr__(self,name):return getattr(db,name)
                async def commit(self):
                    nonlocal armed
                    await db.commit()
                    if armed:armed=False;raise OSError('goal commit acknowledgement lost')
            yield Connection()
    monkeypatch.setattr(store,'connection',uncertain)
    with pytest.raises(OSError,match='goal commit acknowledgement lost'):await LearningFeed(store).record_mission_opened(mission)
    row=await store.fetchone('SELECT * FROM intent_nodes');assert row is not None
    result=await LearningFeed(store).record_mission_opened(mission)
    assert result['intent_id']==row['intent_id']
    again=await store.fetchone('SELECT * FROM intent_nodes')
    assert again['observation_count']==1
    assert again['latest_observed_ms']==row['latest_observed_ms']

@pytest.mark.asyncio
async def test_corrupt_original_goal_receipt_cannot_be_reinterpreted_as_new_owner_evidence(tmp_path):
    from test_owner_memory_has_a_producer import _open
    store=await make_store(tmp_path);mission=await _open(MissionService(store),goal='Corroborate the exact native source')
    feed=LearningFeed(store);before=await feed.record_mission_opened(mission)
    import json
    saved=await store.fetchone('SELECT value FROM runtime_meta WHERE key=?',('intent_observation_source:'+mission.mission_id,))
    corrupt=json.loads(saved['value']);corrupt['scope_sha256']='0'*64
    await store.execute('UPDATE runtime_meta SET value=? WHERE key=?',(json.dumps(corrupt),'intent_observation_source:'+mission.mission_id))
    with pytest.raises(ValueError,match='INTENT_MISSION_SCOPE_CONFLICT'):await feed.record_mission_opened(mission)
    row=await store.fetchone('SELECT * FROM intent_nodes WHERE intent_id=?',(before['intent_id'],))
    assert row['observation_count']==1

@pytest.mark.asyncio
async def test_existing_native_legacy_link_backfills_receipt_without_recounting(tmp_path):
    from test_owner_memory_has_a_producer import _open
    store=await make_store(tmp_path);mission=await _open(MissionService(store),goal='Original linked source')
    feed=LearningFeed(store);original=await feed.record_mission_opened(mission)
    await store.execute('DELETE FROM runtime_meta WHERE key=?',('intent_observation_source:'+mission.mission_id,))
    assert await feed.record_mission_opened(mission)==original
    node=await store.fetchone('SELECT * FROM intent_nodes WHERE intent_id=?',(original['intent_id'],))
    assert node['observation_count']==1
    assert await store.fetchone('SELECT value FROM runtime_meta WHERE key=?',('intent_observation_source:'+mission.mission_id,))

@pytest.mark.asyncio
async def test_bulk_erasure_excludes_a_delayed_old_source_without_an_original_receipt(client,monkeypatch):
    from van_gateway.understanding.memory import IntentContinuityGraph
    ac,app,_=client;key=await _pair(ac,app)
    async def delayed(*args,**kwargs):return None
    with monkeypatch.context() as control:
        control.setattr(IntentContinuityGraph,'observe',delayed)
        body,_=await _approve(ac,app,key,'forget owner-derived memory store owner_facts','delayed-intent-source')
    row=await app.state.store.fetchone("SELECT mission_id FROM missions WHERE json_extract(authority_envelope_json,'$.source_command_id')=?",(body['command_id'],))
    original=await MissionService(app.state.store).get(row['mission_id'])
    assert not await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',('intent_observation_source:'+original.mission_id,))
    await _approve(ac,app,key,'forget owner-derived memory store intent_nodes','erase-before-intent-projection')
    assert (await LearningFeed(app.state.store).record_mission_opened(original))['intent_id'] is None
    assert not await app.state.store.fetchall('SELECT * FROM intent_nodes')

@pytest.mark.asyncio
async def test_mislabelled_automatic_origin_cannot_borrow_an_actual_owner_command(tmp_path):
    from test_owner_memory_has_a_producer import _open
    store=await make_store(tmp_path);mission=await _open(MissionService(store),goal='Owner source requires its actual origin')
    await store.execute("UPDATE missions SET origin='SCHEDULED' WHERE mission_id=?",(mission.mission_id,))
    assert (await LearningFeed(store).record_mission_opened(mission))['intent_id'] is None
    assert not await store.fetchall('SELECT * FROM intent_nodes')
