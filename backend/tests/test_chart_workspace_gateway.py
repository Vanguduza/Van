"""Actual paired owner routes, typed conflicts and no execution delegation."""
import pytest
from test_local_typed_actions import client,_settings,_pair_for_test
from test_chart_workspace_persistence import state

pytestmark=pytest.mark.asyncio
PREFIX='/v1/trading/charts'

async def test_current_owner_can_restore_settings_and_recover_original_write(client):
    ac,app,hermes=client;await _pair_for_test(ac,app,'dev-chart-owner','fixture-chart-secret')
    capability=await ac.get(PREFIX+'/capabilities');assert capability.status_code==200,capability.text
    assert capability.json()['authority_effect']=='NONE' and capability.json()['qualified_vati_indicator_calculation'] is False
    first=await ac.post(PREFIX+'/workspaces',json={'request_id':'create-one','state':state().model_dump()})
    assert first.status_code==200,first.text
    identity=first.json()['workspace_id']
    current=await ac.get(PREFIX+'/workspaces/'+identity);assert current.status_code==200 and current.json()['state']==state().model_dump()
    assert current.headers['cache-control']=='no-store'
    changed=await ac.put(PREFIX+'/workspaces/'+identity,json={'request_id':'edit-one','expected_revision':1,'state':state('New owner layout').model_dump()})
    assert changed.status_code==200 and changed.json()['revision']==2
    stale=await ac.put(PREFIX+'/workspaces/'+identity,json={'request_id':'stale','expected_revision':1,'state':state().model_dump()})
    assert stale.status_code==409 and stale.json()['detail']=={'code':'CHART_REVISION_CONFLICT','current_revision':2}
    original=await ac.get(PREFIX+'/operations/create-one');assert original.json()==first.json()
    restored=await ac.post(PREFIX+'/workspaces/'+identity+'/restore',json={'request_id':'restore-one','expected_revision':2,'target_revision':1})
    assert restored.status_code==200 and restored.json()['revision']==3
    revisions=await ac.get(PREFIX+'/workspaces/'+identity+'/revisions',params={'limit':2})
    assert revisions.status_code==200 and revisions.json()['total_count']==3 and revisions.json()['next_before_revision']==2
    assert hermes['create_run']==0

async def test_chart_routes_refuse_unpaired_or_privileged_state_and_delete_only_current_revision(client):
    ac,app,hermes=client
    absent=await ac.get(PREFIX+'/capabilities');assert absent.status_code==401
    await _pair_for_test(ac,app,'dev-chart-refusals','fixture-chart-secret')
    bad=state().model_dump();bad['panels'][0]['indicators'][0]['provenance_tier']='VATI_SOURCE'
    refused=await ac.post(PREFIX+'/workspaces',json={'request_id':'bad','state':bad});assert refused.status_code==422
    assert not await app.state.store.fetchall('SELECT * FROM chart_workspace_operations')
    created=await ac.post(PREFIX+'/workspaces',json={'request_id':'create','state':state().model_dump()});identity=created.json()['workspace_id']
    wrong=await ac.request('DELETE',PREFIX+'/workspaces/'+identity,json={'request_id':'delete-stale','expected_revision':2})
    assert wrong.status_code==409
    deleted=await ac.request('DELETE',PREFIX+'/workspaces/'+identity,json={'request_id':'delete','expected_revision':1})
    assert deleted.status_code==200 and deleted.json()['status']=='DELETED'
    assert (await ac.get(PREFIX+'/workspaces/'+identity)).status_code==404
    missing=await ac.get(PREFIX+'/operations/missing');assert missing.status_code==404
    spec=app.openapi();route=spec['paths'][PREFIX+'/workspaces/{workspace_id}']['put']
    assert '409' in route['responses'] and '503' in route['responses']
    assert hermes['create_run']==0
