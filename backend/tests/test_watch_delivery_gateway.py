"""Paired gateway watch admission and real scheduler publication recovery."""
import json
import pytest
from test_local_typed_actions import client, _settings, _pair_for_test
from van_gateway.attention.engine import AttentionEngine

pytestmark=pytest.mark.asyncio


async def test_gateway_watch_sweep_recovers_the_original_alert_without_a_second_observation(client,monkeypatch):
    ac,app,hermes=client
    await _pair_for_test(ac,app,'dev-watch','fixture-watch-device-secret')
    response=await ac.post('/v1/goals',json={'title':'Owner goal','project_id':'project-watch'})
    assert response.status_code==200,response.text
    response=await ac.post('/v1/watches',json={'title':'Owner condition','source_kind':'PROVIDER',
        'target':'fixture:availability','condition':{'kind':'BOOLEAN_TRUE'},'interval_seconds':60,'goal_id':response.json()['goal_id']})
    assert response.status_code==200,response.text
    wid=response.json()['watch_id'];upsert=AttentionEngine.upsert
    async def lost(self,**kwargs):
        await upsert(self,**kwargs)
        raise RuntimeError('lost persisted attention reply')
    monkeypatch.setattr(AttentionEngine,'upsert',lost)
    response=await ac.post(f'/v1/watches/{wid}/observations',json={'observation':True})
    assert response.status_code==200,response.text
    result=response.json();assert result['triggered'] and result['notification_state']=='PENDING'
    alert=await app.state.store.fetchone("SELECT * FROM attention WHERE source='watch'")
    assert alert['project_id']=='project-watch'
    await app.state.goals.attention.acknowledge(alert['id'])
    monkeypatch.setattr(AttentionEngine,'upsert',upsert)
    # No BROWSER watch is due. The actual standing scheduler still drains it.
    sweep=app.state.scheduler.jobs['owner.watches'].run
    assert (await sweep())['published']==1
    assert (await sweep())['published']==0
    row=await app.state.store.fetchone("SELECT * FROM attention WHERE source='watch'")
    assert row['id']==alert['id'] and row['state']=='ACKNOWLEDGED'
    assert json.loads(row['payload_json'])['watch_id']==wid
    rows=await app.state.store.fetchall('SELECT run_id FROM watch_runs WHERE watch_id=?',(wid,))
    assert [r['run_id'] for r in rows]==[result['run_id']] and hermes['create_run']==0


async def test_gateway_invalid_watch_values_and_paused_read_are_explicit_refusals(client):
    ac,app,_=client;await _pair_for_test(ac,app,'dev-watch','fixture-watch-device-secret')
    response=await ac.post('/v1/watches',json={'title':'Strict boolean','source_kind':'PROVIDER',
        'target':'fixture:boolean','condition':{'kind':'BOOLEAN_TRUE'},'interval_seconds':60})
    assert response.status_code==200,response.text
    wid=response.json()['watch_id']
    response=await ac.post(f'/v1/watches/{wid}/observations',json={'observation':'false'})
    assert response.status_code==409 and response.json()['detail']=='WATCH_OBSERVATION_INVALID'
    assert (await ac.patch(f'/v1/watches/{wid}',json={'status':'PAUSED'})).status_code==200
    response=await ac.post(f'/v1/watches/{wid}/observations',json={'observation':True})
    assert response.status_code==409 and response.json()['detail']=='WATCH_NOT_ACTIVE'
    assert (await ac.get(f'/v1/watches/{wid}')).json()['last_observation'] is None
    assert not await app.state.store.fetchall('SELECT * FROM watch_runs WHERE watch_id=?',(wid,))
