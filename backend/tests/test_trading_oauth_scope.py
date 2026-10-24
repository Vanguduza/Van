"""Real gateway/device proof and encrypted pending state; no live OAuth provider."""
import time

import pytest

from test_trading_api import client, _env, _approval_proof, DEVICE_PEM, HDR
from van_gateway.trading.accounts import canonical_action, requires_owner_approval


async def act(ac, action, args, *, device='test-device', secret='test-device-secret', headers=None, expected_challenge_status=200):
    import hashlib,hmac
    issued = int(time.time())
    signature = hmac.new(secret.encode(), canonical_action(device,issued,action,args).encode(),hashlib.sha256).hexdigest()
    body = {'device_id':device,'issued_at_unix':issued,'signature':signature,'action':action,'args':args}
    if requires_owner_approval(action):
        challenge = await ac.post('/v1/trading/accounts/challenge',json=body,headers=headers)
        assert challenge.status_code == expected_challenge_status, challenge.text
        if expected_challenge_status != 200:
            return challenge
        body['approval_proof'] = _approval_proof(challenge.json())
    return await ac.post('/v1/trading/accounts/action',json=body,headers=headers)


@pytest.mark.asyncio
async def test_missing_deriv_state_cannot_be_substituted_with_the_latest_owner_flow(client):
    ac, app = client
    started = await act(ac,'oauth_start',{'broker':'deriv'})
    assert started.status_code == 200
    response = await ac.get('/v1/trading/oauth/deriv/callback',params={'acct1':'VRTC900','token1':'fixture-token','cur1':'USD'})
    assert response.status_code == 400
    assert (await act(ac,'oauth_pending',{'state':started.json()['state']})).json() == {'ready':False}


@pytest.mark.asyncio
async def test_one_brokers_callback_cannot_populate_another_brokers_state(client):
    ac, app = client
    started = await act(ac,'oauth_start',{'broker':'ctrader','client_id':'fixture-app','client_secret':'fixture-secret'})
    assert started.status_code == 200
    response = await ac.get('/v1/trading/oauth/deriv/callback',params={'state':started.json()['state'],
        'acct1':'VRTC900','token1':'fixture-token','cur1':'USD'})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_pending_state_is_owned_by_the_device_that_started_it(client):
    ac, app = client
    started = await act(ac,'oauth_start',{'broker':'deriv'})
    state = started.json()['state']
    callback = await ac.get('/v1/trading/oauth/deriv/callback',params={'state':state,
        'acct1':'VRTC900','token1':'fixture-token','cur1':'USD'})
    assert callback.status_code == 200
    ticket = await ac.post('/v1/devices/pairing-ticket',json={'label':'second','ttl_seconds':600},headers=HDR)
    paired = await ac.post('/v1/devices/pair',json={'pairing_token':ticket.json()['pairing_token'],
        'device_id':'second-device','device_secret':'second-device-secret','public_key_pem':DEVICE_PEM,'label':'second'})
    assert paired.status_code == 200, paired.text
    headers={'X-Van-Ingress-Token':paired.json()['ingress_token'],'X-Van-Device-Token':paired.json()['device_access_token']}
    for action,args in [('oauth_pending',{'state':state}),('deriv_oauth_link',{'state':state,'loginid':'VRTC900','alias':'wrong_device'})]:
        response = await act(ac,action,args,device='second-device',secret='second-device-secret',headers=headers, expected_challenge_status=403 if action=='deriv_oauth_link' else 200)
        assert response.status_code == 403, response.text
    own = await act(ac,'oauth_pending',{'state':state})
    assert own.status_code == 200 and own.json()['ready'] is True
    assert 'fixture-token' not in own.text


@pytest.mark.asyncio
async def test_legacy_unbound_state_is_not_adopted_by_the_current_device(client):
    ac, app = client
    state = await app.state.onboarding.pending.create('deriv',{'app_id':'fixture-app'})
    callback = await ac.get('/v1/trading/oauth/deriv/callback',params={'state':state,
        'acct1':'VRTC900','token1':'fixture-token','cur1':'USD'})
    assert callback.status_code == 400
    response = await act(ac,'oauth_pending',{'state':state})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_a_restarted_pending_reader_preserves_the_original_device_owner(client):
    from van_gateway.storage.db import Store
    from van_gateway.config import get_settings
    from van_gateway.trading.accounts import OAuthPending, AccountOnboarding
    from fastapi import HTTPException
    ac, app = client
    started = await act(ac,'oauth_start',{'broker':'deriv','_owner_device_id':'spoofed-owner'})
    state = started.json()['state']
    original = app.state.onboarding
    cold = AccountOnboarding(original.control, OAuthPending(Store(app.state.store.path),get_settings().google_token_fernet_key), original.public_base_url)
    assert await cold.oauth_pending({'state':state},owner_device_id='test-device') == {'ready':False}
    with pytest.raises(HTTPException) as error:
        await cold.oauth_pending({'state':state},owner_device_id='spoofed-owner')
    assert error.value.status_code == 403
    row = await app.state.store.fetchone('SELECT payload_enc FROM trading_oauth_pending WHERE state=?',(state,))
    assert 'test-device' not in row['payload_enc'] and 'spoofed-owner' not in row['payload_enc']


@pytest.mark.asyncio
async def test_unreadable_encrypted_pending_state_is_an_explicit_error_not_an_empty_flow(client):
    from cryptography.fernet import Fernet
    from van_gateway.trading.accounts import OAuthPending
    from fastapi import HTTPException
    ac, app = client
    state = (await act(ac,'oauth_start',{'broker':'deriv'})).json()['state']
    cold = OAuthPending(app.state.store,Fernet.generate_key().decode())
    before = await app.state.store.fetchone('SELECT payload_enc FROM trading_oauth_pending WHERE state=?',(state,))
    with pytest.raises(HTTPException) as error:
        await cold.get(state)
    assert error.value.status_code == 409 and 'restart linking' in error.value.detail
    after = await app.state.store.fetchone('SELECT payload_enc FROM trading_oauth_pending WHERE state=?',(state,))
    assert after['payload_enc'] == before['payload_enc']


@pytest.mark.asyncio
async def test_expired_state_refuses_the_callback_and_releases_no_account_identifiers(client):
    ac, app = client
    state = (await act(ac,'oauth_start',{'broker':'deriv'})).json()['state']
    import json
    pending=app.state.onboarding.pending
    row=await app.state.store.fetchone('SELECT payload_enc FROM trading_oauth_pending WHERE state=?',(state,))
    material=json.loads(pending._f.decrypt(row['payload_enc'].encode()))
    material['_created_at_unix']=1
    encrypted=pending._f.encrypt(json.dumps(material).encode()).decode()
    await app.state.store.execute('UPDATE trading_oauth_pending SET created_at_unix=1,payload_enc=? WHERE state=?',(encrypted,state))
    response = await ac.get('/v1/trading/oauth/deriv/callback',params={'state':state,
        'acct1':'VRTC900','token1':'fixture-token','cur1':'USD'})
    assert response.status_code == 400
    pending = await act(ac,'oauth_pending',{'state':state})
    assert pending.json() == {'ready':False,'expired':True}
