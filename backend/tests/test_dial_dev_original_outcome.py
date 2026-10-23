"""Owner reads must reach the native original action, beyond bounded recent lists."""
import pytest
from test_dial_dev_proxy import gateway,_owner,_auth
from dial_dev_fakes import envelope


@pytest.mark.asyncio
async def test_owner_can_read_exact_native_action_outcome_without_dispatch(gateway):
    ac,app,dial=gateway;enrolled,_=await _owner(app)
    original=envelope({'action_id':'act_original','action':'PAUSE_MISSION','target':{'project_id':'van'},'state':'APPLIED','reason':None})
    dial.json('GET','/v1/dev/actions/act_original',original)
    r=await ac.get('/v1/dial-dev/actions/act_original',headers=_auth(enrolled))
    assert r.status_code==200,r.text
    assert r.json()==original and len(dial.requests)==1
    assert dial.requests[0].method=='GET'
    assert not dial.calls('POST','/v1/dev/actions')


@pytest.mark.asyncio
async def test_original_outcome_read_requires_owner_device_authentication(gateway):
    ac,app,dial=gateway
    r=await ac.get('/v1/dial-dev/actions/act_original')
    assert r.status_code==401 and dial.requests==[]


@pytest.mark.asyncio
@pytest.mark.parametrize('status',[404,409,422,503])
async def test_missing_or_unavailable_native_original_is_never_resubmitted(gateway,status):
    ac,app,dial=gateway;enrolled,_=await _owner(app)
    dial.json('GET','/v1/dev/actions/act_original',{'error':'ACTION_NOT_FOUND'},status=status)
    r=await ac.get('/v1/dial-dev/actions/act_original',headers=_auth(enrolled))
    assert r.status_code==status and r.headers['cache-control']=='no-store'
    assert len(dial.requests)==1 and dial.requests[0].method=='GET'


@pytest.mark.asyncio
async def test_native_credential_echo_is_refused_on_the_original_outcome_route(gateway):
    from pathlib import Path
    ac,app,dial=gateway;enrolled,_=await _owner(app)
    secret=Path(app.state.dial_dev_config.token_file).read_text().strip()
    dial.json('GET','/v1/dev/actions/act_original',envelope({'action_id':'act_original','reason':secret}))
    r=await ac.get('/v1/dial-dev/actions/act_original',headers=_auth(enrolled))
    assert r.status_code==503 and secret not in r.text
