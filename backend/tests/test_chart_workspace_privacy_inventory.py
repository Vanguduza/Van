"""Owner memory controls explain saved chart work; explicit delete removes its bodies."""
import pytest
from test_local_typed_actions import client,_settings,_pair_for_test
from test_chart_workspace_persistence import state

@pytest.mark.asyncio
async def test_owner_inventory_names_saved_chart_work_and_delete_removes_all_revision_bodies(client):
    ac,app,hermes=client;await _pair_for_test(ac,app,'dev-chart-privacy','fixture-chart-secret')
    saved=await ac.post('/v1/trading/charts/workspaces',json={'request_id':'privacy-chart','state':state().model_dump()})
    assert saved.status_code==200,saved.text
    inventory=await ac.get('/v1/context/memory');assert inventory.status_code==200,inventory.text
    assert 'chart_workspaces' in inventory.json()['kept_deliberately']
    assert 'chart_workspaces' not in inventory.json()['stores']
    deleted=await ac.request('DELETE','/v1/trading/charts/workspaces/'+saved.json()['workspace_id'],json={'request_id':'privacy-delete','expected_revision':1})
    assert deleted.status_code==200 and deleted.json()['status']=='DELETED'
    assert not await app.state.store.fetchall('SELECT * FROM chart_workspace_revisions')
    assert hermes['create_run']==0
