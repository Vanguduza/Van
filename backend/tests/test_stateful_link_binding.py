"""Owned paired-HTTP/A4/native-registry counterexample; no real provider."""
import json
from pathlib import Path
import pytest
from fastapi import HTTPException
from backend.tests.test_trading_api import client,_env
from backend.tests.test_trading_oauth_scope import act
from backend.tests.test_account_resource_binding import approved
from test_commander_accounts import FakeDeriv
from van_gateway.trading.accounts import LocalAccountControl
from vati.accounts import AccountRegistry

async def owned_ready_deriv(ac):
    started=await act(ac,'oauth_start',{'broker':'deriv','app_id':'1089'})
    assert started.status_code==200
    state=started.json()['state']
    callback=await ac.get('/v1/trading/oauth/deriv/callback',params={
        'state':state,'acct1':'VRTC900','token1':'a1-linked','cur1':'USD'})
    assert callback.status_code==200
    return state


@pytest.mark.asyncio
async def test_original_oauth_link_domain_cannot_retarget_another_native_state(client,tmp_path,monkeypatch):
    ac,app=client;peer=FakeDeriv()
    def control(name):return LocalAccountControl(str(tmp_path/(name+'-accounts.json')),str(tmp_path/(name+'-secrets')),
        operation_ledger=str(tmp_path/(name+'-native.sqlite')),deriv_connector=peer.connector)
    original=control('original');other=control('other')
    app.state.onboarding.control=original
    expected=original.domain();actual=other.domain();assert expected!=actual
    started=await act(ac,'oauth_start',{'broker':'deriv','app_id':'1089'})
    assert started.status_code==200,started.text
    state=started.json()['state']
    callback=await ac.get('/v1/trading/oauth/deriv/callback',params={'state':state,'acct1':'VRTC900','token1':'a1-linked','cur1':'USD'})
    assert callback.status_code==200,callback.text
    args={'state':state,'loginid':'VRTC900','alias':'linked_original'}
    body=await approved(ac,'deriv_oauth_link',args)
    captured={};run=original.run
    def switched(command,values):
        if command=='deriv_oauth_link':
            captured['native_expected_domain_forwarded']=values.get('_expected_account_control_domain')==expected
            return other.run(command,values)
        return run(command,values)
    monkeypatch.setattr(original,'run',switched)
    response=await ac.post('/v1/trading/accounts/action',json=body,headers={'X-Van-Account-Control-Domain':expected})
    other_exists=(tmp_path/'other-accounts.json').exists()
    observation={'action':'stateful deriv_oauth_link','paired_http_and_real_a4':True,
        'original_and_replacement_native_domains_distinct':expected!=actual,
        'explicit_original_domain_header':True,**captured,'status_code':response.status_code,
        'original_registry_exists':(tmp_path/'original-accounts.json').exists(),
        'replacement_registry_exists':other_exists,
        'replacement_registered_alias':AccountRegistry(tmp_path/'other-accounts.json').get('linked_original').alias if other_exists else None,
        'controlled_authorize_calls':sum('authorize' in m for m in peer.msgs),
        'controlled_remote_account_creates':sum('new_account_virtual' in m for m in peer.msgs)}
    assert observation['native_expected_domain_forwarded'] is True
    assert observation['controlled_authorize_calls']==0 and observation['controlled_remote_account_creates']==0
    assert response.status_code==409 and not other_exists, 'Original-domain owner approval wrote a link into another native state namespace'


@pytest.mark.asyncio
@pytest.mark.parametrize('broker',['deriv','ctrader'])
async def test_original_link_result_is_bound_durable_and_readable_after_ack_loss(client,tmp_path,monkeypatch,broker):
    from van_gateway.storage.db import Store
    from van_gateway.config import get_settings
    from van_gateway.trading.accounts import AccountOnboarding,OAuthPending
    ac,app=client;peer=FakeDeriv()
    ctl=LocalAccountControl(str(tmp_path/'accounts.json'),str(tmp_path/'secrets'),
        operation_ledger=str(tmp_path/'native.sqlite'),deriv_connector=peer.connector)
    app.state.onboarding.control=ctl
    run=ctl.run;calls=[]
    def control(command,values):
        if command=='ctrader_oauth_exchange':return {'access_token':'owned-fixture-access','refresh_token':'owned-fixture-refresh'}
        if command in {'ctrader_link','deriv_oauth_link'}:calls.append(command)
        return run(command,values)
    monkeypatch.setattr(ctl,'run',control)
    args={'broker':broker}
    if broker=='ctrader':args.update(client_id='fixture-id',client_secret='fixture-secret')
    started=await act(ac,'oauth_start',args);assert started.status_code==200
    state=started.json()['state'];action='deriv_oauth_link' if broker=='deriv' else 'ctrader_link'
    query={'state':state,'acct1':'VRTC900','token1':'a1-linked','cur1':'USD'} if broker=='deriv' else {'state':state,'code':'owned-fixture-code'}
    assert (await ac.get('/v1/trading/oauth/'+broker+'/callback',params=query)).status_code==200
    link={'state':state,'alias':'linked_once',**({'loginid':'VRTC900'} if broker=='deriv' else {'ctid_trader_account_id':12345,'is_live':False})}
    body=await approved(ac,action,link);original=body['approval_proof']['challenge_id'];domain=ctl.domain()
    before_version=ctl.resource_version('linked_once')['resource_version']
    def drop(point):
        if point=='after_commit_before_reply':raise TimeoutError('owned lost commit acknowledgement')
    app.state.onboarding.pending.effects.fault=drop
    first=await ac.post('/v1/trading/accounts/action',json=body)
    assert first.status_code==200,first.text
    app.state.onboarding.pending.effects.fault=None
    receipt=first.json()
    assert receipt['operation_id']==original and receipt['oauth_state']==state
    assert receipt['native_resource_version']==before_version and receipt['account_control_domain']==domain
    assert ctl.resource_version('linked_once')['resource_version']!=before_version
    cold=AccountOnboarding(ctl,OAuthPending(Store(app.state.store.path),get_settings().google_token_fernet_key),app.state.onboarding.public_base_url)
    recovered=await cold.run(action,link,owner_device_id='test-device')
    assert recovered==receipt and calls==[action]
    reread=await act(ac,'oauth_pending',{'state':state})
    assert reread.status_code==200 and reread.json()['operation_id']==original
    assert reread.json()['ready'] is False and reread.json()['expired'] is True
    assert (await act(ac,action,link)).json()==receipt and calls==[action]
    from dataclasses import replace
    registry=AccountRegistry(tmp_path/'accounts.json');current=registry.get('linked_once')
    registry.replace(replace(current,label='Current owner label'))
    historical=await act(ac,'oauth_pending',{'state':state})
    assert historical.json()['account']['label']==receipt['account']['label']
    assert AccountRegistry(tmp_path/'accounts.json').get('linked_once').label=='Current owner label'
    assert (await act(ac,action,{**link,'alias':'different_alias'})).status_code==409
    with pytest.raises(HTTPException) as conflict:
        await cold.run(action,link,owner_device_id='test-device',native_resource_version='f'*64)
    assert conflict.value.status_code==409
    other=LocalAccountControl(str(tmp_path/'other.json'),str(tmp_path/'other-secrets'),operation_ledger=str(tmp_path/'other.sqlite'))
    app.state.onboarding.control=other
    denied=await act(ac,'oauth_pending',{'state':state})
    assert denied.status_code==409 and denied.json()['reconciliation_required']
    assert not (tmp_path/'other.json').exists() and calls==[action]
    text=json.dumps(receipt)
    for secret in ['a1-linked','owned-fixture-access','owned-fixture-refresh','fixture-secret']:
        assert secret not in text


@pytest.mark.asyncio
@pytest.mark.parametrize('phase',['UNKNOWN','APPLIED'])
async def test_legacy_unbound_link_is_never_adopted_into_current_namespace(client,tmp_path,phase):
    from van_gateway.trading.oauth_effects import fingerprint
    ac,app=client
    ctl=LocalAccountControl(str(tmp_path/'accounts.json'),str(tmp_path/'secrets'),operation_ledger=str(tmp_path/'native.sqlite'))
    app.state.onboarding.control=ctl
    state='legacy_oauth_original_state_123456';args={'state':state,'alias':'legacy_alias','loginid':'VRTC900'}
    digest=fingerprint({'state':state,'operation':'LINK','broker':'deriv','payload':args})
    effects=app.state.onboarding.pending.effects
    envelope={'schema':'van.oauth-effect-receipt/1','state':state,'operation':'LINK','broker':'deriv',
        'owner_device_id':'test-device','request_digest':digest,'result':{'account':{'alias':'legacy_alias'}}}
    encoded=effects.cipher.encrypt(json.dumps(envelope).encode()).decode() if phase=='APPLIED' else None
    await app.state.store.execute("INSERT INTO trading_oauth_effects VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (state,'LINK','deriv','test-device',digest,'account:legacy_alias',phase,'legacy-worker',encoded,None,1,1))
    result=await act(ac,'oauth_pending',{'state':state})
    assert result.status_code==200 and result.json()['scope_status']=='UNBOUND'
    assert result.json()['status']==('RECORDED_APPLIED_UNBOUND' if phase=='APPLIED' else 'OUTCOME_UNCONFIRMED')
    blocked=await act(ac,'deriv_oauth_link',args,expected_challenge_status=409)
    assert blocked.status_code==409 and not (tmp_path/'accounts.json').exists()
    row=await app.state.store.fetchone("SELECT phase,receipt_enc FROM trading_oauth_effects WHERE state=? AND operation='LINK'",(state,))
    assert row['phase']==phase and row['receipt_enc']==encoded


@pytest.mark.asyncio
async def test_partial_link_holds_original_and_only_proved_other_native_domain_is_independent(client,tmp_path,monkeypatch):
    import commander.accounts as native_module
    ac,app=client;peer=FakeDeriv()
    def control(label):return LocalAccountControl(str(tmp_path/(label+'.json')),str(tmp_path/(label+'-secrets')),
        operation_ledger=str(tmp_path/(label+'.sqlite')),deriv_connector=peer.connector)
    original=control('first');other=control('other');app.state.onboarding.control=original
    state=await owned_ready_deriv(ac);args={'state':state,'alias':'shared_alias','loginid':'VRTC900'}
    write=native_module._write_secrets
    def fail(path,values,**kwargs):
        if 'DERIV_API_TOKEN' in values:raise OSError('owned failure after registry effect')
        return write(path,values,**kwargs)
    monkeypatch.setattr(native_module,'_write_secrets',fail)
    prepared=await approved(ac,'deriv_oauth_link',args)
    original_version=original.resource_version('shared_alias')['resource_version']
    result=await ac.post('/v1/trading/accounts/action',json=prepared)
    assert result.status_code==409 and result.json()['effect_state']=='UNKNOWN'
    registry=AccountRegistry(tmp_path/'first.json')
    assert registry.get('shared_alias').login=='VRTC900' and registry.credentials('shared_alias')=={}
    monkeypatch.setattr(native_module,'_write_secrets',write)
    unknown=await act(ac,'oauth_pending',{'state':state})
    assert unknown.status_code==200 and unknown.json()['effect_state']=='UNKNOWN'
    assert unknown.json()['oauth_state']==state and unknown.json()['reconciliation_required']
    row_before=await app.state.store.fetchone("SELECT * FROM trading_oauth_effects WHERE state=? AND operation='LINK'",(state,))
    original_binding=app.state.onboarding.pending.effects._link_envelope(row_before)['native_binding']
    explicit={**args,'original_operation_id':original_binding['operation_id'],
        'original_approval_expires_at_unix':original_binding.get('original_expires_at_unix',original_binding['expires_at_unix']),
        'original_resource_version':original_version,'original_issued_at_unix':prepared['issued_at_unix'],
        'original_account_control_domain':original.domain()}
    assert (await act(ac,'deriv_oauth_link',explicit)).status_code==409
    row_after=await app.state.store.fetchone("SELECT phase,receipt_enc FROM trading_oauth_effects WHERE state=? AND operation='LINK'",(state,))
    assert row_after['phase']=='UNKNOWN' and row_after['receipt_enc']==row_before['receipt_enc']
    assert (await act(ac,'deriv_oauth_link',args)).status_code==409
    newstate=await owned_ready_deriv(ac)
    assert (await act(ac,'deriv_oauth_link',{**args,'state':newstate})).status_code==409
    assert sum('authorize' in m for m in peer.msgs)==1
    # A protected authenticated native state descriptor proves local-state
    # independence, never another remote customer or permission to trade.
    app.state.onboarding.control=other
    assert other.domain()!=original.domain()
    separate=await owned_ready_deriv(ac)
    applied=await act(ac,'deriv_oauth_link',{**args,'state':separate})
    assert applied.status_code==200 and applied.json()['account_control_domain']==other.domain(),applied.text
    assert AccountRegistry(tmp_path/'other.json').get('shared_alias').login=='VRTC900'
    row=await app.state.store.fetchone("SELECT * FROM trading_oauth_effects WHERE state=? AND operation='LINK'",(state,))
    assert row['phase']=='UNKNOWN'
    intent=app.state.onboarding.pending.effects._link_envelope(row)
    assert intent['record_type']=='INTENT' and 'result' not in intent
    assert intent['native_binding']['account_control_domain']==original.domain()
    assert sum('authorize' in m for m in peer.msgs)==2


@pytest.mark.asyncio
@pytest.mark.parametrize('field',['native_resource_version','account_control_domain','oauth_state'])
async def test_cached_receipt_fields_cannot_change_original_bound_scope(client,tmp_path,field):
    from backend.tests.test_trading_api import HDR,DEVICE_PEM
    ac,app=client;peer=FakeDeriv()
    ctl=LocalAccountControl(str(tmp_path/'accounts.json'),str(tmp_path/'secrets'),
        operation_ledger=str(tmp_path/'native.sqlite'),deriv_connector=peer.connector)
    app.state.onboarding.control=ctl
    state=await owned_ready_deriv(ac)
    result=await act(ac,'deriv_oauth_link',{'state':state,'alias':'linked_once','loginid':'VRTC900'})
    assert result.status_code==200,result.text
    ticket=await ac.post('/v1/devices/pairing-ticket',json={'label':'second','ttl_seconds':600},headers=HDR)
    paired=await ac.post('/v1/devices/pair',json={'pairing_token':ticket.json()['pairing_token'],'device_id':'second-device',
        'device_secret':'second-device-secret','public_key_pem':DEVICE_PEM,'label':'second'})
    headers={'X-Van-Ingress-Token':paired.json()['ingress_token'],'X-Van-Device-Token':paired.json()['device_access_token']}
    wrong=await act(ac,'oauth_pending',{'state':state},device='second-device',secret='second-device-secret',headers=headers)
    assert wrong.status_code==403
    invalid=await act(ac,'oauth_pending',{'state':state},headers={'X-Van-Device-Token':'invalid-current-token'})
    assert invalid.status_code in {401,403}
    # A validly encrypted storage fault still cannot change typed original
    # scope/version/state. The recorded APPLIED row is never rewritten.
    row=await app.state.store.fetchone("SELECT * FROM trading_oauth_effects WHERE state=? AND operation='LINK'",(state,))
    effects=app.state.onboarding.pending.effects;envelope=effects._link_envelope(row)
    envelope['result'][field]='f'*64 if field!='oauth_state' else 'another_oauth_state_123456789'
    encoded=effects.cipher.encrypt(json.dumps(envelope).encode()).decode()
    await app.state.store.execute("UPDATE trading_oauth_effects SET receipt_enc=? WHERE state=? AND operation='LINK'",(encoded,state))
    hold=await act(ac,'oauth_pending',{'state':state})
    assert hold.status_code==409 and hold.json()['effect_state']=='UNKNOWN'
    preserved=await app.state.store.fetchone("SELECT phase,receipt_enc FROM trading_oauth_effects WHERE state=? AND operation='LINK'",(state,))
    assert preserved['phase']=='APPLIED' and preserved['receipt_enc']==encoded
    assert sum('authorize' in m for m in peer.msgs)==1


@pytest.mark.asyncio
async def test_real_link_process_death_keeps_bound_original_unknown_without_native_resend(client,tmp_path,monkeypatch):
    import os,sys,subprocess,signal,asyncio
    ac,app=client
    ctl=LocalAccountControl(str(tmp_path/'accounts.json'),str(tmp_path/'secrets'),operation_ledger=str(tmp_path/'native.sqlite'))
    app.state.onboarding.control=ctl
    state=await owned_ready_deriv(ac);args={'state':state,'alias':'process_link','loginid':'VRTC900'}
    body=await approved(ac,'deriv_oauth_link',args);original=body['approval_proof']['challenge_id'];domain=ctl.domain()
    script='''import os,json
from fastapi.testclient import TestClient
from van_gateway.app import create_app
from van_gateway.trading.accounts import LocalAccountControl
app=create_app()
control=LocalAccountControl(os.environ['LINK_REGISTRY'],os.environ['LINK_SECRETS'],operation_ledger=os.environ['LINK_LEDGER'])
run=control.run
def exit_after_claim(command,args):
 if command=='deriv_oauth_link':os._exit(73)
 return run(command,args)
control.run=exit_after_claim
app.state.onboarding.control=control
with TestClient(app) as client:
 response=client.post('/v1/trading/accounts/action',json=json.loads(os.environ['LINK_BODY']),headers=json.loads(os.environ['LINK_HEADERS']))
 raise SystemExit(74)
'''
    env=dict(os.environ,LINK_REGISTRY=str(tmp_path/'accounts.json'),LINK_SECRETS=str(tmp_path/'secrets'),
        LINK_LEDGER=str(tmp_path/'native.sqlite'),LINK_BODY=json.dumps(body),
        LINK_HEADERS=json.dumps({key:value for key,value in ac.headers.items() if key.lower().startswith('x-van-')}))
    child=subprocess.Popen([sys.executable,'-c',script],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,start_new_session=True)
    waiting=asyncio.create_task(asyncio.to_thread(child.communicate,timeout=30))
    try:
        _,error=await asyncio.shield(waiting)
        assert len(error)<65536 and child.returncode==73,error.decode()
    finally:
        if child.poll() is None:
            os.killpg(child.pid,signal.SIGKILL)
            await asyncio.to_thread(child.wait,timeout=5)
        try:await asyncio.shield(waiting)
        except subprocess.TimeoutExpired:await asyncio.to_thread(child.communicate)
    row=await app.state.store.fetchone("SELECT * FROM trading_oauth_effects WHERE state=? AND operation='LINK'",(state,))
    assert row['phase']=='IN_FLIGHT'
    intent=app.state.onboarding.pending.effects._link_envelope(row)
    assert intent['record_type']=='INTENT' and intent['native_binding']['operation_id']==original
    assert intent['native_binding']['account_control_domain']==domain
    assert not (tmp_path/'accounts.json').exists()
    run=ctl.run
    def no_resend(command,values):
        assert command!='deriv_oauth_link','Original unknown link was resent'
        return run(command,values)
    monkeypatch.setattr(ctl,'run',no_resend)
    read=await act(ac,'oauth_pending',{'state':state})
    assert read.status_code==200 and read.json()['effect_state']=='UNKNOWN'
    assert read.json()['operation_id']==original and read.json()['native_reconciliation_required']
    assert (await act(ac,'deriv_oauth_link',args)).status_code==409
    assert not (tmp_path/'accounts.json').exists()


@pytest.mark.asyncio
async def test_authorization_readiness_is_not_link_completion_and_expired_prepared_grant_can_be_reconfirmed(client,tmp_path,monkeypatch):
    import time
    from types import SimpleNamespace
    import commander.accounts as native_module
    import van_gateway.approval.service as approval_module
    from van_gateway.approval.service import OwnerApprovalError
    from van_gateway.trading.accounts import account_approval_text
    ac,app=client;peer=FakeDeriv();clock=[int(time.time())]
    monkeypatch.setattr(approval_module,'time',SimpleNamespace(time=lambda:clock[0]))
    monkeypatch.setattr(native_module,'time',SimpleNamespace(time=lambda:clock[0]))
    ctl=LocalAccountControl(str(tmp_path/'accounts.json'),str(tmp_path/'secrets'),operation_ledger=str(tmp_path/'native.sqlite'),deriv_connector=peer.connector)
    app.state.onboarding.control=ctl
    state=await owned_ready_deriv(ac);args={'state':state,'alias':'prepared_link','loginid':'VRTC900'}
    original=await approved(ac,'deriv_oauth_link',args);identity=original['approval_proof']['challenge_id']
    domain=ctl.domain();version=ctl.resource_version('prepared_link')['resource_version']
    row=await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',('owner_approval:'+identity,))
    record=json.loads(row['value']);original_expiry=record['expires_at_unix']
    read=await act(ac,'oauth_pending',{'state':state})
    assert read.status_code==200 and read.json()['ready'] is True
    assert all(field not in read.json() for field in ('effect_state','operation_id','account','result'))
    assert await app.state.store.fetchone("SELECT 1 FROM trading_oauth_effects WHERE state=? AND operation='LINK'",(state,)) is None
    assert not (tmp_path/'accounts.json').exists() and peer.msgs==[]
    # The client PREPARED stage is proved by its durable no-network producer,
    # never by this missing row/readiness. A fresh real permission is required.
    clock[0]=original_expiry+1
    # Historical commitment remains readable after expiry, without renewing it.
    read_fact=await act(ac,'oauth_pending',{'state':state,'original_binding':{
        'operation_id':identity,'action':'deriv_oauth_link','issued_at_unix':original['issued_at_unix'],'semantic_args':args}})
    assert read_fact.status_code==200,read_fact.text
    fact=read_fact.json()['original_link_binding']
    assert fact['resource_version']==version and fact['execution_authority'] is False
    assert (await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',('owner_approval:'+identity,)))['value']==row['value']
    resume={**args,'original_operation_id':identity,'original_approval_expires_at_unix':original_expiry,
        'original_resource_version':version,'original_issued_at_unix':original['issued_at_unix'],
        'original_account_control_domain':domain}
    fresh=await approved(ac,'deriv_oauth_link',resume);fresh_grant=fresh['approval_proof']['challenge_id']
    assert fresh_grant!=identity
    completed=await ac.post('/v1/trading/accounts/action',json=fresh)
    assert completed.status_code==200,completed.text
    assert completed.json()['operation_id']==identity and completed.json()['oauth_state']==state
    intentrow=await app.state.store.fetchone("SELECT * FROM trading_oauth_effects WHERE state=? AND operation='LINK'",(state,))
    binding=app.state.onboarding.pending.effects._link_envelope(intentrow)['native_binding']
    assert binding['operation_id']==identity and binding['original_expires_at_unix']==original_expiry
    assert binding['approval_operation_id']==fresh_grant and binding['expires_at_unix']>clock[0]
    assert (await act(ac,'oauth_pending',{'state':state})).json()['operation_id']==identity
    assert sum('authorize' in m for m in peer.msgs)==1
    assert AccountRegistry(tmp_path/'accounts.json').get('prepared_link').login=='VRTC900'


@pytest.mark.asyncio
@pytest.mark.parametrize('original_first',[True,False])
async def test_delayed_original_and_explicit_resume_arbitrate_one_immutable_original(client,tmp_path,original_first):
    ac,app=client;peer=FakeDeriv()
    ctl=LocalAccountControl(str(tmp_path/'accounts.json'),str(tmp_path/'secrets'),operation_ledger=str(tmp_path/'native.sqlite'),deriv_connector=peer.connector)
    app.state.onboarding.control=ctl
    state=await owned_ready_deriv(ac);args={'state':state,'alias':'same_original','loginid':'VRTC900'}
    original=await approved(ac,'deriv_oauth_link',args);identity=original['approval_proof']['challenge_id']
    row=await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',('owner_approval:'+identity,))
    expiry=json.loads(row['value'])['expires_at_unix']
    resume={**args,'original_operation_id':identity,'original_approval_expires_at_unix':expiry,
        'original_resource_version':ctl.resource_version(args['alias'])['resource_version'],
        'original_issued_at_unix':original['issued_at_unix'],'original_account_control_domain':ctl.domain()}
    renewed=await approved(ac,'deriv_oauth_link',resume)
    order=[original,renewed] if original_first else [renewed,original]
    results=[await ac.post('/v1/trading/accounts/action',json=body) for body in order]
    assert all(result.status_code==200 for result in results),[result.text for result in results]
    assert results[0].json()==results[1].json() and results[0].json()['operation_id']==identity
    assert sum('authorize' in m for m in peer.msgs)==1
    mismatched={**resume,'original_operation_id':'wrong_original_operation_12345'}
    assert (await act(ac,'deriv_oauth_link',mismatched,expected_challenge_status=409)).status_code==409
    assert (await act(ac,'deriv_oauth_link',{**resume,'alias':'wrong_semantic_alias'},expected_challenge_status=409)).status_code==409
    assert sum('authorize' in m for m in peer.msgs)==1


@pytest.mark.asyncio
async def test_resume_id_cannot_adopt_a_different_original_winning_before_sql_claim(client,tmp_path,monkeypatch):
    ac,app=client;peer=FakeDeriv()
    ctl=LocalAccountControl(str(tmp_path/'accounts.json'),str(tmp_path/'secrets'),operation_ledger=str(tmp_path/'native.sqlite'),deriv_connector=peer.connector)
    app.state.onboarding.control=ctl
    state=await owned_ready_deriv(ac);args={'state':state,'alias':'arbitrated_link','loginid':'VRTC900'}
    prepared=await approved(ac,'deriv_oauth_link',args);identity=prepared['approval_proof']['challenge_id']
    row=await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',('owner_approval:'+identity,))
    expiry=json.loads(row['value'])['expires_at_unix']
    resume={**args,'original_operation_id':identity,'original_approval_expires_at_unix':expiry,
        'original_resource_version':ctl.resource_version(args['alias'])['resource_version'],
        'original_issued_at_unix':prepared['issued_at_unix'],'original_account_control_domain':ctl.domain()}
    renewed=await approved(ac,'deriv_oauth_link',resume)
    begin=app.state.onboarding.pending.effects.begin;winner=[]
    async def race(state_value,operation,broker,payload,**kwargs):
        if operation=='LINK' and payload.get('original_operation_id') and not winner:
            winner.append(True)
            actual=await act(ac,'deriv_oauth_link',args)
            assert actual.status_code==200,actual.text
            winner[0]=actual.json()['operation_id']
        return await begin(state_value,operation,broker,payload,**kwargs)
    monkeypatch.setattr(app.state.onboarding.pending.effects,'begin',race)
    refused=await ac.post('/v1/trading/accounts/action',json=renewed)
    assert refused.status_code==409 and winner[0]!=identity
    original=await act(ac,'oauth_pending',{'state':state})
    assert original.status_code==200 and original.json()['operation_id']==winner[0]
    assert sum('authorize' in m for m in peer.msgs)==1


@pytest.mark.asyncio
@pytest.mark.parametrize('fault',['generation','forged_generation','body','issued','domain','missing','canonical','parameters','device','legacy'])
async def test_prepared_resume_joins_immutable_actual_a4_without_rebasing(client,tmp_path,fault):
    ac,app=client;peer=FakeDeriv()
    ctl=LocalAccountControl(str(tmp_path/'accounts.json'),str(tmp_path/'secrets'),operation_ledger=str(tmp_path/'native.sqlite'),deriv_connector=peer.connector)
    app.state.onboarding.control=ctl
    state=await owned_ready_deriv(ac);args={'state':state,'alias':'original_generation','loginid':'VRTC900'}
    original=await approved(ac,'deriv_oauth_link',args);identity=original['approval_proof']['challenge_id']
    key='owner_approval:'+identity
    row=await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(key,))
    record=json.loads(row['value']);version=ctl.resource_version(args['alias'])['resource_version']
    resume={**args,'original_operation_id':identity,'original_approval_expires_at_unix':record['expires_at_unix'],
        'original_resource_version':version,'original_issued_at_unix':original['issued_at_unix'],
        'original_account_control_domain':ctl.domain()}
    if fault in {'generation','forged_generation'}:
        assert (await act(ac,'account_upsert',{'alias':args['alias'],'broker':'PAPER'})).status_code==200
        assert (await act(ac,'account_remove',{'alias':args['alias']})).status_code==200
        current=ctl.resource_version(args['alias'])['resource_version'];assert current!=version
        if fault=='forged_generation':resume['original_resource_version']=current
    elif fault=='body':resume['label']='Unapproved original meaning'
    elif fault=='issued':resume['original_issued_at_unix']+=1
    elif fault=='domain':resume['original_account_control_domain']='f'*64
    elif fault=='missing':await app.state.store.execute('DELETE FROM runtime_meta WHERE key=?',(key,))
    elif fault=='legacy':resume.pop('original_resource_version')
    else:
        if fault=='canonical':record['canonical']+='corrupt'
        elif fault=='parameters':record['parameters']={'invented':'not committed'}
        elif fault=='device':record['device_id']='another-owner'
        await app.state.store.execute('UPDATE runtime_meta SET value=? WHERE key=?',(json.dumps(record),key))
    before=await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(key,))
    denied=await act(ac,'deriv_oauth_link',resume,expected_challenge_status=409)
    assert denied.status_code==409,denied.text
    assert await app.state.store.fetchone("SELECT 1 FROM trading_oauth_effects WHERE state=? AND operation='LINK'",(state,)) is None
    assert not any('authorize' in msg for msg in peer.msgs)
    after=await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(key,))
    assert (dict(after) if after else None)==(dict(before) if before else None)
