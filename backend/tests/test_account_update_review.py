"""Owner review describes the effective native edit and binds its interpretation."""
import hashlib
import hmac
import json
import time
from dataclasses import replace

import pytest

from test_trading_api import client,_env,_approval_proof
from test_trading_oauth_scope import act
from van_gateway.trading.accounts import ACTIONS,canonical_action,requires_owner_approval
from vati.accounts import Account,AccountRegistry,CredentialRef
from vati.core.canonical import canonical_hash


@pytest.fixture(autouse=True)
def isolate(tmp_path,monkeypatch,_env):
    from van_gateway.config import get_settings
    monkeypatch.setenv('VAN_VATI_ACCOUNTS_REGISTRY',str(tmp_path/'accounts.json'))
    monkeypatch.setenv('VAN_VATI_SECRETS_DIR',str(tmp_path/'secrets'))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def challenge(ac,action,args):
    issued=int(time.time())
    body={'device_id':'test-device','issued_at_unix':issued,'action':action,'args':args,
        'signature':hmac.new(b'test-device-secret',canonical_action('test-device',issued,action,args).encode(),hashlib.sha256).hexdigest()}
    response=await ac.post('/v1/trading/accounts/challenge',json=body)
    assert response.status_code==200,response.text
    return {**body,'approval_proof':_approval_proof(response.json())},response.json()


def seed(tmp_path):
    r=AccountRegistry(tmp_path/'accounts.json')
    account=r.add(Account(alias='owner_account',broker='DERIV',mode='OBSERVE',currency='EUR',
        label='Original',login='CR900',server='8123',demo=False,enabled=False,
        credential_ref=CredentialRef(env_var='FIXTURE_NATIVE_PRIVATE_LOCATOR'),notes='Owner notes'))
    return r,account


@pytest.mark.asyncio
async def test_exact_native_before_after_is_signed_and_applied_without_losing_connection(client,tmp_path):
    ac,app=client;registry,original=seed(tmp_path)
    body,issued=await challenge(ac,'account_upsert',{'alias':original.alias,'label':'Reviewed name'})
    review=issued['resolved_review']
    assert review['before']==original.public() and review['changed_fields']==['label']
    assert review['after']==replace(original,label='Reviewed name').public()
    assert 'FIXTURE_NATIVE_PRIVATE_LOCATOR' not in json.dumps(review)
    assert review['review_digest']==canonical_hash({k:v for k,v in review.items() if k!='review_digest'})
    row=await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',('owner_approval:'+body['approval_proof']['challenge_id'],))
    assert json.loads(row['value'])['parameters']=={'native_review':review}
    applied=await ac.post('/v1/trading/accounts/action',json=body)
    assert applied.status_code==200,applied.text
    assert AccountRegistry(registry.path).get(original.alias)==replace(original,label='Reviewed name')
    assert not (tmp_path/'secrets/owner_account.env').exists()


@pytest.mark.asyncio
async def test_enable_disable_is_an_actual_owner_control_and_keeps_other_fields(client,tmp_path):
    ac,_=client
    assert (await act(ac,'account_upsert',{'alias':'paper_owner','broker':'PAPER'})).status_code==200
    before=AccountRegistry(tmp_path/'accounts.json').get('paper_owner')
    for enabled in (False,True):
        result=await act(ac,'account_upsert',{'alias':'paper_owner','enabled':enabled})
        assert result.status_code==200,result.text
        assert AccountRegistry(tmp_path/'accounts.json').get('paper_owner')==replace(before,enabled=enabled)


@pytest.mark.asyncio
async def test_changed_resolved_semantics_cannot_reuse_an_approval_even_when_resource_is_unchanged(client,tmp_path,monkeypatch):
    ac,app=client;registry,original=seed(tmp_path)
    body,_=await challenge(ac,'account_upsert',{'alias':original.alias,'label':'Reviewed name'})
    native=app.state.onboarding.control.review
    def different(action,args):
        review=native(action,args)
        review['after']['label']='Different interpretation'
        review['review_digest']=canonical_hash({k:v for k,v in review.items() if k!='review_digest'})
        return review
    monkeypatch.setattr(app.state.onboarding.control,'review',different)
    response=await ac.post('/v1/trading/accounts/action',json=body)
    assert response.status_code==403,response.text
    assert AccountRegistry(registry.path).get(original.alias)==original


@pytest.mark.asyncio
async def test_final_native_writer_refuses_interpretation_drift_after_gateway_verification(client,tmp_path,monkeypatch):
    import commander.accounts as module
    ac,app=client;registry,original=seed(tmp_path)
    body,_=await challenge(ac,'account_upsert',{'alias':original.alias,'label':'Reviewed name'})
    native=app.state.onboarding.control.run;resolve=module.resolve_account_config
    def drift_at_write(command,args):
        if command!='account_upsert':return native(command,args)
        def changed(*a,**kw): return replace(resolve(*a,**kw),label='Unapproved native interpretation')
        with monkeypatch.context() as m:
            m.setattr(module,'resolve_account_config',changed)
            return native(command,args)
    monkeypatch.setattr(app.state.onboarding.control,'run',drift_at_write)
    response=await ac.post('/v1/trading/accounts/action',json=body)
    assert response.status_code==409 and response.json()['effect_state']=='REFUSED',response.text
    assert AccountRegistry(registry.path).get(original.alias)==original
    result=await ac.get('/v1/trading/accounts/operations/'+body['approval_proof']['challenge_id'])
    assert result.status_code==200 and result.json()['effect_state']=='REFUSED',result.text


@pytest.mark.asyncio
async def test_native_catalog_covers_exact_actions_and_exposes_enable_and_secret_input_contracts(client):
    ac,_=client;response=await ac.get('/v1/trading/accounts/catalog')
    assert response.status_code==200,response.text
    rows={r['action']:r for r in response.json()['actions']}
    assert set(rows)==set(ACTIONS)
    assert all(r['requires_owner_approval']==requires_owner_approval(k) for k,r in rows.items())
    assert rows['account_upsert']['requires_resolved_review']
    assert rows['account_upsert']['input_schema']['properties']['enabled']['type']=='boolean'
    assert rows['account_credentials']['input_schema']['properties']['secrets']['writeOnly'] is True
    assert rows['deriv_oauth_link']['input_schema']['oneOf'][0]['properties']['token']['writeOnly'] is True
    assert 'BRIDGE_SIGNING_KEY' in response.json()['credential_keys_by_broker']['MT5_EA']


@pytest.mark.asyncio
async def test_private_locator_or_incomplete_native_review_never_reaches_owner_approval(client,tmp_path,monkeypatch):
    ac,app=client;_,original=seed(tmp_path);native=app.state.onboarding.control.review
    def private(action,args):
        review=native(action,args);review['after']['credential_ref']['secrets_file']='fixture-private-locator'
        # Keep the reported changed-field set consistent, so it cannot mask a
        # missing public-only contract check before approval allocation.
        review['before']['credential_ref']['secrets_file']='fixture-private-locator'
        review['review_digest']=canonical_hash({k:v for k,v in review.items() if k!='review_digest'})
        return review
    monkeypatch.setattr(app.state.onboarding.control,'review',private)
    response=await act(ac,'account_upsert',{'alias':original.alias,'label':'Review'},expected_challenge_status=409)
    assert 'fixture-private-locator' not in response.text
    count=await app.state.store.fetchone("SELECT count(*) AS n FROM runtime_meta WHERE key GLOB 'owner_approval:*'")
    assert count['n']==0
