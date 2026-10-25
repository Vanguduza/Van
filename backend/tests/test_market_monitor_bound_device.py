"""Real current-device proof on owner monitor mutations; readbacks do not sign."""
import json
import pytest
from conftest_market_monitors import isolate_native_backgrounds
PREFIX = "/v1/trading/monitors"
pytestmark = pytest.mark.asyncio

from test_device_proof_enforcement import (_base_headers, _bind, _paired, _proof_headers,
    client as bound_monitor_client_fixture, _settings)


async def test_bound_monitor_mutation_needs_real_device_signature_and_reads_need_only_current_token(bound_monitor_client_fixture):
    ac, app = bound_monitor_client_fixture
    enrolled = await _paired(app)
    key = await _bind(app,enrolled.device.device_id)
    target = PREFIX+'/watchlists'
    raw = json.dumps({'request_id':'bound-monitor','state':{'name':'Bound owner list','entries':[]}}).encode()
    unsigned = await ac.post(target,content=raw,headers={**_base_headers(enrolled),'Content-Type':'application/json'})
    assert unsigned.status_code == 401 and unsigned.json()['detail'] == 'device_proof_required'
    assert not await app.state.store.fetchall('SELECT * FROM market_monitor_operations')
    signed = await ac.post(target,content=raw,headers={**_base_headers(enrolled),'Content-Type':'application/json',
        **_proof_headers(key,method='POST',path=target,device_id=enrolled.device.device_id,body=raw)})
    assert signed.status_code == 200,signed.text
    actual = await ac.get(target+'/'+signed.json()['object_id'],headers=_base_headers(enrolled))
    assert actual.status_code == 200 and actual.json()['state']['name'] == 'Bound owner list'
