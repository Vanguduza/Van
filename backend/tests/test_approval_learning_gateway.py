"""Actual cryptographic owner challenge -> sealed command -> native approval learning."""
import pytest
from tests.test_owner_memory_erasure import client,_settings,_pair,_approve
from van_gateway.learning.feed import LearningFeed
from van_gateway.mission.service import MissionService

@pytest.mark.asyncio
async def test_verified_owner_approval_creates_one_native_choice_after_seal_not_on_capture(client):
    ac,app,_=client;key=await _pair(ac,app)
    body,result=await _approve(ac,app,key,'forget owner-derived memory store owner_facts','learning-approved-choice')
    assert result['status']=='accepted',result
    rows=await app.state.store.fetchall('SELECT * FROM decision_fingerprints')
    assert len(rows)==1
    original=dict(rows[0]);assert original['inferred_reason'] is None and original['owner_stated_reason'] is None
    assert 'command-authority:'+body['command_id'] in original['evidence_used_json']
    assert '"signed_action_class":"A1"' in original['context_json']
    mission=await MissionService(app.state.store).get(original['mission_id'])
    assert mission.authority_envelope.source_command_id==body['command_id']
    assert await LearningFeed(app.state.store).record_owner_approval(mission)==original['decision_id']
    assert [dict(r) for r in await app.state.store.fetchall('SELECT * FROM decision_fingerprints')]==[original]

@pytest.mark.asyncio
async def test_original_approval_projection_cannot_resurrect_explicitly_erased_memory(client):
    ac,app,_=client;key=await _pair(ac,app)
    body,_=await _approve(ac,app,key,'forget owner-derived memory store owner_facts','old-learning-source')
    row=await app.state.store.fetchone('SELECT * FROM decision_fingerprints')
    original_mission=await MissionService(app.state.store).get(row['mission_id'])
    await _approve(ac,app,key,'forget owner-derived memory store decision_fingerprints','erase-old-decisions')
    assert not await app.state.store.fetchall('SELECT * FROM decision_fingerprints')
    assert await LearningFeed(app.state.store).record_owner_approval(original_mission) is None
    assert not await app.state.store.fetchall('SELECT * FROM decision_fingerprints')

@pytest.mark.asyncio
async def test_selective_erasure_blocks_only_the_original_choice_and_fresh_approval_remains_learnable(client):
    from van_gateway.understanding.records import OwnerRecords
    ac,app,_=client;key=await _pair(ac,app)
    _,_=await _approve(ac,app,key,'forget owner-derived memory store owner_facts','selective-old-source')
    original=await app.state.store.fetchone('SELECT * FROM decision_fingerprints')
    mission=await MissionService(app.state.store).get(original['mission_id'])
    target=(await OwnerRecords(app.state.store).list('decision_fingerprints'))['records'][0]
    await _approve(ac,app,key,target['erasure']['command_text'],'selective-erase-choice')
    assert not await app.state.store.fetchone('SELECT * FROM decision_fingerprints WHERE decision_id=?',(original['decision_id'],))
    assert await LearningFeed(app.state.store).record_owner_approval(mission) is None
    # The later explicit erasure choice is not the old erased choice.
    rows=await app.state.store.fetchall('SELECT * FROM decision_fingerprints')
    assert len(rows)==1 and rows[0]['decision_id']!=original['decision_id']

@pytest.mark.asyncio
async def test_bulk_erasure_barrier_preserves_fresh_sources_even_with_equal_native_creation_times(client):
    ac,app,_=client;key=await _pair(ac,app)
    await _approve(ac,app,key,'forget owner-derived memory store owner_facts','barrier-original-source')
    old=await app.state.store.fetchone('SELECT * FROM decision_fingerprints');old_mission=await MissionService(app.state.store).get(old['mission_id'])
    await _approve(ac,app,key,'forget owner-derived memory store decision_fingerprints','barrier-erasure')
    body,_=await _approve(ac,app,key,'forget owner-derived memory store owner_facts','barrier-fresh-source')
    current=await app.state.store.fetchone('SELECT * FROM decision_fingerprints')
    assert current is not None and current['decision_id']!=old['decision_id']
    fresh_mission=await MissionService(app.state.store).get(current['mission_id'])
    # Native context revisions, rather than ambiguous timestamp equality, order consent.
    await app.state.store.execute('UPDATE missions SET created_at_ms=1000')
    feed=LearningFeed(app.state.store)
    assert await feed.record_owner_approval(old_mission) is None
    assert await feed.record_owner_approval(fresh_mission)==current['decision_id']
    assert len(await app.state.store.fetchall('SELECT * FROM decision_fingerprints'))==1

@pytest.mark.asyncio
async def test_bulk_erasure_blocks_delayed_source_absent_from_original_erased_rows(client,monkeypatch):
    ac,app,_=client;key=await _pair(ac,app)
    async def delayed(*args,**kwargs):return None
    with monkeypatch.context() as control:
        control.setattr(LearningFeed,'record_owner_approval',delayed)
        body,_=await _approve(ac,app,key,'forget owner-derived memory store owner_facts','delayed-old-source')
    assert not await app.state.store.fetchall('SELECT * FROM decision_fingerprints')
    row=await app.state.store.fetchone("SELECT mission_id FROM missions WHERE json_extract(authority_envelope_json,'$.source_command_id')=?",(body['command_id'],))
    mission=await MissionService(app.state.store).get(row['mission_id'])
    await _approve(ac,app,key,'forget owner-derived memory store decision_fingerprints','erase-before-delayed-source')
    assert not await app.state.store.fetchall('SELECT * FROM decision_fingerprints')
    assert await LearningFeed(app.state.store).record_owner_approval(mission) is None
    assert not await app.state.store.fetchall('SELECT * FROM decision_fingerprints')
