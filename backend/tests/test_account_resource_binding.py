"""Owner intent must name the current native account resource, not rebase silently."""
import hashlib
import hmac
import time
from dataclasses import replace

import pytest

from test_trading_api import client, _env, _approval_proof
from test_trading_oauth_scope import act
from van_gateway.trading.accounts import canonical_action
from vati.accounts import AccountRegistry


@pytest.fixture(autouse=True)
def isolated_native_account_files(tmp_path,monkeypatch,_env):
    from van_gateway.config import get_settings
    monkeypatch.setenv('VAN_VATI_ACCOUNTS_REGISTRY',str(tmp_path/'accounts.json'))
    monkeypatch.setenv('VAN_VATI_SECRETS_DIR',str(tmp_path/'secrets'))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def approved(ac,action,args):
    issued=int(time.time());device='test-device'
    text=canonical_action(device,issued,action,args)
    body=dict(device_id=device,issued_at_unix=issued,action=action,args=args,
        signature=hmac.new(b'test-device-secret',text.encode(),hashlib.sha256).hexdigest())
    challenge=await ac.post('/v1/trading/accounts/challenge',json=body)
    assert challenge.status_code==200,challenge.text
    body['approval_proof']=_approval_proof(challenge.json())
    return body


@pytest.mark.asyncio
@pytest.mark.parametrize('action',['account_upsert','account_remove'])
async def test_delayed_owner_approval_cannot_overwrite_a_newer_account(client,tmp_path,action):
    ac,app=client
    assert (await act(ac,'account_upsert',{'alias':'paper_lab','broker':'PAPER','label':'Original'})).status_code==200
    args={'alias':'paper_lab','broker':'PAPER','label':'Old approved edit'} if action=='account_upsert' else {'alias':'paper_lab'}
    body=await approved(ac,action,args)
    assert (await act(ac,'account_upsert',{'alias':'paper_lab','broker':'PAPER','label':'New owner edit'})).status_code==200
    response=await ac.post('/v1/trading/accounts/action',json=body)
    assert response.status_code in (403,409),response.text
    assert AccountRegistry(tmp_path/'accounts.json').get('paper_lab').label=='New owner edit'


@pytest.mark.asyncio
async def test_approval_for_an_absent_alias_cannot_replace_a_later_registration(client,tmp_path):
    ac,_=client
    body=await approved(ac,'account_upsert',{'alias':'paper_lab','broker':'PAPER','label':'Absent approved'})
    assert (await act(ac,'account_upsert',{'alias':'paper_lab','broker':'PAPER','label':'Later registration'})).status_code==200
    response=await ac.post('/v1/trading/accounts/action',json=body)
    assert response.status_code in (403,409),response.text
    assert AccountRegistry(tmp_path/'accounts.json').get('paper_lab').label=='Later registration'


@pytest.mark.asyncio
async def test_native_cas_still_checks_changes_after_gateway_proof_verification(client,tmp_path,monkeypatch):
    ac,app=client
    assert (await act(ac,'account_upsert',{'alias':'paper_lab','broker':'PAPER','label':'Original'})).status_code==200
    body=await approved(ac,'account_upsert',{'alias':'paper_lab','broker':'PAPER','label':'Approved edit'})
    native=app.state.onboarding.control.run
    def concurrent_native_update(command,args):
        if command=='account_upsert':
            registry=AccountRegistry(tmp_path/'accounts.json')
            registry.replace(replace(registry.get('paper_lab'),label='Native concurrent update'))
        return native(command,args)
    monkeypatch.setattr(app.state.onboarding.control,'run',concurrent_native_update)
    response=await ac.post('/v1/trading/accounts/action',json=body)
    assert response.status_code==409,response.text
    assert AccountRegistry(tmp_path/'accounts.json').get('paper_lab').label=='Native concurrent update'


@pytest.mark.asyncio
async def test_credential_generation_change_invalidates_a_pending_local_edit(client,tmp_path):
    from commander.accounts import _write_secrets
    ac,_=client
    assert (await act(ac,'account_upsert',{'alias':'deriv_demo','broker':'DERIV','login':'VRTC900'})).status_code==200
    body=await approved(ac,'account_upsert',{'alias':'deriv_demo','broker':'DERIV','login':'VRTC900','label':'Old approved edit'})
    _write_secrets(tmp_path/'secrets/deriv_demo.env',{'DERIV_API_TOKEN':'fixture-native-rotated'})
    response=await ac.post('/v1/trading/accounts/action',json=body)
    assert response.status_code in (403,409),response.text
    assert AccountRegistry(tmp_path/'accounts.json').get('deriv_demo').label!='Old approved edit'


@pytest.mark.asyncio
async def test_a_disjoint_owner_edit_does_not_invalidate_this_account_approval(client,tmp_path):
    ac,_=client
    assert (await act(ac,'account_upsert',{'alias':'paper_lab','broker':'PAPER'})).status_code==200
    body=await approved(ac,'account_upsert',{'alias':'paper_lab','broker':'PAPER','label':'Approved edit'})
    assert (await act(ac,'account_upsert',{'alias':'other_alias','broker':'PAPER'})).status_code==200
    response=await ac.post('/v1/trading/accounts/action',json=body)
    assert response.status_code==200,response.text
    assert AccountRegistry(tmp_path/'accounts.json').get('paper_lab').label=='Approved edit'


@pytest.mark.asyncio
async def test_restoring_old_metadata_does_not_restore_an_obsolete_approval(client,tmp_path):
    ac,_=client
    initial={'alias':'paper_lab','broker':'PAPER','label':'Original'}
    assert (await act(ac,'account_upsert',initial)).status_code==200
    body=await approved(ac,'account_upsert',{**initial,'label':'Old approved edit'})
    assert (await act(ac,'account_upsert',{**initial,'label':'Temporary'})).status_code==200
    assert (await act(ac,'account_upsert',initial)).status_code==200
    response=await ac.post('/v1/trading/accounts/action',json=body)
    assert response.status_code in (403,409),response.text
    assert AccountRegistry(tmp_path/'accounts.json').get('paper_lab').label=='Original'


@pytest.mark.asyncio
async def test_device_cannot_supply_the_gateways_internal_resource_binding(client,tmp_path):
    ac,_=client
    args={'alias':'paper_lab','broker':'PAPER','_expected_resource_version':'0'*64}
    issued=int(time.time());text=canonical_action('test-device',issued,'account_upsert',args)
    body=dict(device_id='test-device',issued_at_unix=issued,action='account_upsert',args=args,
        signature=hmac.new(b'test-device-secret',text.encode(),hashlib.sha256).hexdigest())
    response=await ac.post('/v1/trading/accounts/challenge',json=body)
    assert response.status_code==422,response.text
    assert not (tmp_path/'accounts.json').exists()


@pytest.mark.asyncio
async def test_failed_native_readback_returns_refused_without_dispatching_a_change(client,tmp_path,monkeypatch):
    ac,app=client
    assert (await act(ac,'account_upsert',{'alias':'paper_lab','broker':'PAPER','label':'Original'})).status_code==200
    body=await approved(ac,'account_upsert',{'alias':'paper_lab','broker':'PAPER','label':'Unsent'})
    def unreadable(*args):raise RuntimeError('fixture-private-diagnostic')
    def no_effect(*args):raise AssertionError('mutation dispatched without native account version')
    monkeypatch.setattr(app.state.onboarding.control,'resource_version',unreadable)
    monkeypatch.setattr(app.state.onboarding.control,'review',unreadable)
    monkeypatch.setattr(app.state.onboarding.control,'run',no_effect)
    response=await ac.post('/v1/trading/accounts/action',json=body)
    assert response.status_code==409,response.text
    assert response.json()['effect_state']=='REFUSED' and response.json()['reconciliation_required'] is False
    assert 'fixture-private-diagnostic' not in response.text
    assert AccountRegistry(tmp_path/'accounts.json').get('paper_lab').label=='Original'
