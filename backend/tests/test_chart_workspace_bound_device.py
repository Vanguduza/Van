"""Current bound-device proof is required for chart settings mutations."""
import json
import pytest
from test_device_proof_enforcement import (_base_headers,_bind,_paired,_proof_headers,_settings,
    client as owner_client_fixture)
from test_chart_workspace_persistence import state

@pytest.mark.asyncio
async def test_bound_chart_write_requires_actual_signature_and_read_does_not_dispatch(owner_client_fixture):
    ac,app=owner_client_fixture;enrolled=await _paired(app);key=await _bind(app,enrolled.device.device_id)
    target='/v1/trading/charts/workspaces';body={'request_id':'bound-chart-create','state':state().model_dump()};raw=json.dumps(body).encode()
    unsigned=await ac.post(target,content=raw,headers={**_base_headers(enrolled),'Content-Type':'application/json'})
    assert unsigned.status_code==401 and unsigned.json()['detail']=='device_proof_required'
    assert not await app.state.store.fetchall('SELECT * FROM chart_workspace_operations')
    signed=await ac.post(target,content=raw,headers={**_base_headers(enrolled),'Content-Type':'application/json',
        **_proof_headers(key,method='POST',path=target,device_id=enrolled.device.device_id,body=raw)})
    assert signed.status_code==200,signed.text
    wid=signed.json()['workspace_id']
    actual=await ac.get(target+'/'+wid,headers=_base_headers(enrolled))
    assert actual.status_code==200 and actual.json()['state']==state().model_dump()
    assert actual.headers['cache-control']=='no-store'
    assert not await app.state.store.fetchall('SELECT * FROM mission_activities')
