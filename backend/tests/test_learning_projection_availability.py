"""Optional inferred-memory projections cannot change native owner work outcomes."""
import pytest
from conftest_automation import make_store
from van_gateway.learning.feed import LearningFeed
from van_gateway.mission.service import MissionService
from van_gateway.mission.models import MissionOrigin,MissionState
from van_gateway.models import OriginChannel
from tests.test_owner_memory_erasure import client,_settings,_pair,_approve

async def captured(service):
    return await service.create(owner_principal_id='owner',origin=MissionOrigin.OWNER_UI,
        origin_channel=OriginChannel.UI,title='Native owner work',goal='Keep a native work record')

@pytest.mark.asyncio
async def test_unavailable_optional_capture_learning_cannot_block_native_capture(tmp_path,monkeypatch,caplog):
    store=await make_store(tmp_path);feed=LearningFeed(store);missions=MissionService(store,learning=feed)
    async def unavailable(*args,**kwargs):raise RuntimeError('fixture-private-learning-text')
    monkeypatch.setattr(feed,'record_mission_opened',unavailable)
    try:result=await captured(missions)
    except Exception as exc:result=exc
    assert not isinstance(result,Exception),type(result).__name__
    assert result.state is MissionState.CAPTURED and (await missions.get(result.mission_id)).state is MissionState.CAPTURED
    assert await store.fetchone("SELECT event_id FROM mission_events WHERE mission_id=? AND event_type='mission.created'",(result.mission_id,))
    assert 'learning projection unavailable' in caplog.text and 'fixture-private-learning-text' not in caplog.text

@pytest.mark.asyncio
async def test_one_failed_learning_sink_cannot_hide_native_terminal_state_or_other_sinks(tmp_path,monkeypatch,caplog):
    store=await make_store(tmp_path);feed=LearningFeed(store);missions=MissionService(store,learning=feed);mission=await captured(missions)
    observed=[]
    async def unavailable(*args,**kwargs):observed.append('mission');raise RuntimeError('fixture-private-learning-text')
    async def strategy(*args,**kwargs):observed.append('strategy')
    async def decision(*args,**kwargs):observed.append('decision')
    monkeypatch.setattr(feed,'record_mission_outcome',unavailable);monkeypatch.setattr(feed,'record_strategy_outcome',strategy);monkeypatch.setattr(feed,'record_decision_outcome',decision)
    failure=None
    try:
        for target in [MissionState.UNDERSTOOD,MissionState.PLANNED,MissionState.AUTHORIZED,MissionState.RUNNING,MissionState.FAILED]:
            mission=await missions.transition(mission.mission_id,target=target)
    except Exception as exc:failure=exc
    assert failure is None,type(failure).__name__
    assert observed==['mission','strategy','decision']
    assert mission.state is MissionState.FAILED and (await missions.get(mission.mission_id)).state is MissionState.FAILED
    assert 'learning projection unavailable' in caplog.text and 'fixture-private-learning-text' not in caplog.text

@pytest.mark.asyncio
async def test_optional_post_seal_learning_failure_cannot_block_actual_approved_owner_control(client,monkeypatch,caplog):
    from van_gateway.command.authority import CommandAuthorityService
    ac,app,_=client;key=await _pair(ac,app);original=LearningFeed.record_owner_approval
    async def unavailable_after_seal(self,mission,**kwargs):
        source=mission.authority_envelope.source_command_id
        if source and await CommandAuthorityService(self.store).get(source):raise RuntimeError('fixture-private-learning-text')
        return await original(self,mission,**kwargs)
    monkeypatch.setattr(LearningFeed,'record_owner_approval',unavailable_after_seal)
    try:outcome=await _approve(ac,app,key,'forget owner-derived memory store owner_facts','learning-unavailable-approved-control')
    except Exception as exc:outcome=exc
    assert not isinstance(outcome,Exception),type(outcome).__name__
    body,result=outcome
    assert result['status']=='accepted' and result['local_execution']['removed_counts']=={'owner_facts':0}
    assert await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',('memory_erasure_witness:'+body['command_id'],))
    assert not await app.state.store.fetchall('SELECT * FROM decision_fingerprints')
    assert 'learning projection unavailable' in caplog.text and 'fixture-private-learning-text' not in caplog.text


@pytest.mark.asyncio
async def test_optional_learning_cancellation_remains_cancellation(tmp_path,monkeypatch):
    import asyncio
    store=await make_store(tmp_path);feed=LearningFeed(store);missions=MissionService(store,learning=feed)
    async def cancelled(*args,**kwargs):raise asyncio.CancelledError()
    monkeypatch.setattr(feed,'record_mission_opened',cancelled)
    with pytest.raises(asyncio.CancelledError):await captured(missions)
    rows=await store.fetchall('SELECT state FROM missions')
    assert len(rows)==1 and rows[0]['state']=='CAPTURED'
