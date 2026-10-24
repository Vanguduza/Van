"""Existing paired goal/watch routes expose complete typed source contracts."""
import pytest
from test_local_typed_actions import client,_settings,_pair_for_test
from van_gateway.mission.service import MissionService
from van_gateway.mission.models import MissionOrigin
from van_gateway.models import OriginChannel

pytestmark=pytest.mark.asyncio


async def test_paired_owner_goal_lifecycle_uses_real_links_and_preserves_distinct_mission_state(client):
    ac,app,hermes=client
    await _pair_for_test(ac,app,'dev-goal','fixture-goal-device-secret')
    response=await ac.post('/v1/goals',json={'title':'  Launch plan  ','description':'Owner description','milestones':['  first  ','second']})
    assert response.status_code==200,response.text
    goal=response.json();gid=goal['goal_id']
    assert goal['title']=='Launch plan' and [x['title'] for x in goal['milestones']]==['first','second']
    response=await ac.post(f'/v1/goals/{gid}/missions',json={'mission_id':'missing'})
    assert response.status_code==404 and response.json()['detail']=='MISSION_UNKNOWN'
    mission=await MissionService(app.state.store).create(owner_principal_id='owner',origin=MissionOrigin.OWNER_VOICE,
        origin_channel=OriginChannel.VOICE,title='Existing execution',goal='Related work')
    before=await app.state.store.fetchone('SELECT state FROM missions WHERE mission_id=?',(mission.mission_id,))
    for _ in range(2):
        response=await ac.post(f'/v1/goals/{gid}/missions',json={'mission_id':mission.mission_id})
        assert response.status_code==200,response.text
        assert response.json()['mission_ids']==[mission.mission_id]
    response=await ac.patch(f'/v1/goals/{gid}',json={'title':'Reviewed plan','status':'COMPLETED'})
    assert response.status_code==200,response.text
    assert response.json()['description']=='Owner description' and response.json()['completed_at_ms'] is not None
    response=await ac.patch(f'/v1/goals/{gid}',json={'status':'PAUSED'})
    assert response.status_code==200 and response.json()['completed_at_ms'] is None
    assert response.json()['milestones']==goal['milestones']
    after=await app.state.store.fetchone('SELECT state FROM missions WHERE mission_id=?',(mission.mission_id,))
    assert dict(before)==dict(after) and hermes['create_run']==0
    schema=app.openapi()
    for method,path in [('post','/v1/goals'),('get','/v1/goals/{goal_id}'),('patch','/v1/goals/{goal_id}')]:
        assert schema['paths'][path][method]['responses']['200']['content']['application/json']['schema'].get('$ref','').endswith('/Goal')
    assert {'goal_id','milestones','mission_ids','status'} <= set(schema['components']['schemas']['Goal']['properties'])


async def test_gateway_rejects_blank_goal_watch_fields_without_creating_hidden_records(client):
    ac,app,_=client;await _pair_for_test(ac,app,'dev-goal','fixture-goal-device-secret')
    for body in [{'title':' '},{'title':'Valid','milestones':['first',' ']}]:
        response=await ac.post('/v1/goals',json=body);assert response.status_code==422,response.text
    response=await ac.post('/v1/watches',json={'title':'Watch','source_kind':'PROVIDER','target':' ', 'condition':{'kind':'CHANGED'}})
    assert response.status_code==422,response.text
    assert not await app.state.store.fetchall('SELECT * FROM owner_goals')
    assert not await app.state.store.fetchall('SELECT * FROM watches')
