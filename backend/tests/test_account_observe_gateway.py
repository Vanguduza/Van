"""Actual enrolled Gateway A4 with PAPER metadata and pre-provider native refusals."""
import hashlib,hmac,json,time
import pytest
from backend.tests.test_trading_api import client,_env,_approval_proof
from backend.tests.test_account_update_review import isolate
from van_gateway.trading.accounts import canonical_action
from vati.accounts import Account,AccountRegistry,CredentialRef


def signed(action,args):
    issued=int(time.time())
    return {'device_id':'test-device','issued_at_unix':issued,'action':action,'args':args,
        'signature':hmac.new(b'test-device-secret',canonical_action('test-device',issued,action,args).encode(),hashlib.sha256).hexdigest()}


async def admitted(ac,action,args):
    body=signed(action,args)
    response=await ac.post('/v1/trading/accounts/challenge',json=body)
    assert response.status_code==200,response.text
    return {**body,'approval_proof':_approval_proof(response.json())}


@pytest.mark.asyncio
async def test_real_enrolled_owner_paper_creation_defaults_observe_and_keeps_existing_mode(client,tmp_path):
    ac,app=client
    catalog=await ac.get('/v1/trading/accounts/catalog')
    assert catalog.status_code==200,catalog.text
    rows={row['action']:row['input_schema'] for row in catalog.json()['actions']}
    for action in ('deriv_create_demo','deriv_oauth_link','ctrader_link'):
        for schema in rows[action].get('oneOf',[rows[action]]):
            assert schema['properties']['mode']['enum']==['OBSERVE']
            assert schema['properties']['mode']['default']=='OBSERVE'
    assert 'default' not in rows['account_upsert']['properties']['mode']
    assert rows['mt5_ea_issue_key']['required']==['alias'] and 'mode' in rows['mt5_ea_issue_key']['properties']
    body=await admitted(ac,'account_upsert',{'alias':'new_paper','broker':'PAPER'})
    created=await ac.post('/v1/trading/accounts/action',json=body)
    assert created.status_code==200,created.text
    assert created.json()['account']['mode']=='OBSERVE' and created.json()['account']['safety_identity']=='PAPER'
    registry=AccountRegistry(tmp_path/'accounts.json')
    registry.add(Account('admitted_paper','PAPER','DEMO_TRADER','USD',mandate_ref='existing-admitted-control'))
    edit=await admitted(ac,'account_upsert',{'alias':'admitted_paper','label':'Updated label'})
    updated=await ac.post('/v1/trading/accounts/action',json=edit)
    assert updated.status_code==200,updated.text
    current=AccountRegistry(registry.path).get('admitted_paper')
    assert current.mode=='DEMO_TRADER' and current.mandate_ref=='existing-admitted-control'
    assert not (tmp_path/'secrets/new_paper.env').exists() and not (tmp_path/'secrets/admitted_paper.env').exists()


@pytest.mark.asyncio
@pytest.mark.parametrize('action',['account_upsert','deriv_create_demo','deriv_oauth_link','ctrader_link','mt5_ea_issue_key'])
async def test_gateway_refuses_explicit_initial_trading_mode_before_approval_or_provider(client,tmp_path,action):
    ac,app=client;args={'alias':'initial_refused','mode':'DEMO_TRADER'}
    if action=='account_upsert':args['broker']='PAPER'
    response=await ac.post('/v1/trading/accounts/challenge',json=signed(action,args))
    assert response.status_code==422 and response.json()['detail']['code']=='NEW_ACCOUNT_OBSERVE_REQUIRED',response.text
    assert not (tmp_path/'accounts.json').exists() and not (tmp_path/'secrets/initial_refused.env').exists()


@pytest.mark.asyncio
@pytest.mark.parametrize('action',['deriv_create_demo','deriv_oauth_link','ctrader_link','mt5_ea_issue_key'])
async def test_native_creator_still_refuses_initial_trading_mode_with_real_a4_from_stale_gateway_preview(client,tmp_path,monkeypatch,action):
    ac,app=client;onboarding=app.state.onboarding;version=onboarding.resource_version
    async def older_preview(command,args,**kwargs):
        # Model the previous Gateway's missing initial-mode policy only. The
        # real enrolled A4 still signs the full requested trading-mode args.
        return await version(command,{k:v for k,v in args.items() if k!='mode'},**kwargs)
    monkeypatch.setattr(onboarding,'resource_version',older_preview)
    native=onboarding.control.run;calls=[]
    def observed(command,args):
        if command==action:calls.append((command,args.get('mode')))
        return native(command,args)
    monkeypatch.setattr(onboarding.control,'run',observed)
    body=await admitted(ac,action,{'alias':'native_refused','mode':'DEMO_TRADER'})
    response=await ac.post('/v1/trading/accounts/action',json=body)
    assert response.status_code==422 and response.json()['detail']['code']=='NEW_ACCOUNT_OBSERVE_REQUIRED',response.text
    assert calls==[(action,'DEMO_TRADER')]
    assert not (tmp_path/'accounts.json').exists() and not (tmp_path/'secrets/native_refused.env').exists()
    if action=='deriv_create_demo':assert not (tmp_path/'secrets/.demo-operation-digest.env').exists()


@pytest.mark.asyncio
@pytest.mark.parametrize('change',['mode','native_identity','other_broker','missing_identity'])
async def test_bridge_key_issue_cannot_mutate_existing_identity_or_skip_initial_identity(client,tmp_path,change):
    ac,app=client;alias='existing_bridge';args={'alias':alias}
    if change!='missing_identity':
        broker='PAPER' if change=='other_broker' else 'MT5_EA'
        AccountRegistry(tmp_path/'accounts.json').add(Account(alias,broker,'OBSERVE','USD',
            login='12345678',server='Original-Demo',enabled=False,notes='Retained owner metadata',
            credential_ref=CredentialRef(env_var='METADATA_ONLY_NOT_READ')))
        before=(tmp_path/'accounts.json').read_bytes()
    else:before=None
    if change=='mode':args['mode']='DEMO_TRADER'
    elif change=='native_identity':args['login']='different-native-login'
    body=await admitted(ac,'mt5_ea_issue_key',args)
    response=await ac.post('/v1/trading/accounts/action',json=body)
    if change=='mode':
        assert response.status_code==422 and response.json()['detail']['code']=='ACCOUNT_MODE_REQUIRES_EXISTING_CONTROL',response.text
    elif change=='missing_identity':
        assert response.status_code==422 and response.json()['detail']=='New MT5 account needs login and server',response.text
    else:
        assert response.status_code==409 and response.json()['effect_state']=='REFUSED',response.text
        assert response.json()['detail']=='Native account identity changes require verified migration; current connection retained'
    if before is None:assert not (tmp_path/'accounts.json').exists()
    else:assert (tmp_path/'accounts.json').read_bytes()==before
    assert not (tmp_path/'secrets'/f'{alias}.env').exists()
