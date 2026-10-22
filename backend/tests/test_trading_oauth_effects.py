"""OAuth native persistence/control boundaries with isolated provider responses."""
import asyncio
import pytest

from test_trading_api import client, _env
from test_trading_oauth_scope import act


@pytest.fixture(autouse=True)
def isolated_account_files(tmp_path,monkeypatch,_env):
    from van_gateway.config import get_settings
    monkeypatch.setenv("VAN_VATI_ACCOUNTS_REGISTRY",str(tmp_path/"accounts.json"))
    monkeypatch.setenv("VAN_VATI_SECRETS_DIR",str(tmp_path/"secrets"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def isolated_native_deriv_authorization(client, tmp_path):
    # The real control now reads native identity before persistence. Exercise it
    # through actual websocket framing; never contact a provider in source tests.
    from van_gateway.trading.accounts import LocalAccountControl
    from test_deriv_native_identity import Socket, native
    _,app=client
    app.state.onboarding.control=LocalAccountControl(str(tmp_path/"accounts.json"),str(tmp_path/"secrets"),
        deriv_connector=lambda url: Socket(native()))


@pytest.mark.asyncio
async def test_exact_callback_retry_does_not_exchange_a_provider_code_twice(client, monkeypatch):
    ac, app = client; calls=[]
    def control(command,args):
        assert command == 'ctrader_oauth_exchange'
        calls.append(args['code'])
        return {'access_token':'fixture-access','refresh_token':'fixture-refresh'}
    monkeypatch.setattr(app.state.onboarding.control,'run',control)
    started = await act(ac,'oauth_start',{'broker':'ctrader','client_id':'fixture-app','client_secret':'fixture-secret'})
    query={'state':started.json()['state'],'code':'fixture-code'}
    for _ in range(2):
        response = await ac.get('/v1/trading/oauth/ctrader/callback',params=query)
        assert response.status_code == 200, response.text
    assert calls == ['fixture-code']


@pytest.mark.asyncio
async def test_conflicting_callback_cannot_replace_the_first_accepted_credentials(client):
    ac, app = client
    state = (await act(ac,'oauth_start',{'broker':'deriv'})).json()['state']
    first = {'state':state,'acct1':'VRTC900','token1':'fixture-first','cur1':'USD'}
    assert (await ac.get('/v1/trading/oauth/deriv/callback',params=first)).status_code == 200
    changed = await ac.get('/v1/trading/oauth/deriv/callback',params={**first,'token1':'fixture-conflict'})
    assert changed.status_code == 409
    pending = await app.state.onboarding.pending.get(state)
    assert pending['accounts'][0]['token'] == 'fixture-first'


@pytest.mark.asyncio
async def test_link_retry_after_a_lost_reply_returns_receipt_without_repeating_the_local_effect(client, monkeypatch):
    ac, app = client
    state = (await act(ac,'oauth_start',{'broker':'deriv'})).json()['state']
    assert (await ac.get('/v1/trading/oauth/deriv/callback',params={'state':state,
        'acct1':'VRTC900','token1':'fixture-access','cur1':'USD'})).status_code == 200
    control = app.state.onboarding.control.run; calls=[]
    def observed(command,args):
        calls.append(command)
        return control(command,args)
    monkeypatch.setattr(app.state.onboarding.control,'run',observed)
    args={'state':state,'loginid':'VRTC900','alias':'linked_once'}
    first = await act(ac,'deriv_oauth_link',args)
    assert first.status_code == 200, first.text
    second = await act(ac,'deriv_oauth_link',args)
    assert second.status_code == 200, second.text
    assert first.json() == second.json()
    assert calls == ['deriv_oauth_link']


async def start_flow(ac, broker='deriv'):
    args={'broker':broker}
    if broker=='ctrader':
        args.update(client_id='fixture-app',client_secret='fixture-secret')
    response=await act(ac,'oauth_start',args)
    assert response.status_code==200,response.text
    return response.json()['state']


async def ready_deriv(ac):
    state=await start_flow(ac)
    response=await ac.get('/v1/trading/oauth/deriv/callback',params={'state':state,
        'acct1':'VRTC900','token1':'fixture-access','cur1':'USD'})
    assert response.status_code==200,response.text
    return state


@pytest.mark.asyncio
async def test_concurrent_callback_is_refused_while_owner_polling_and_event_loop_remain_responsive(client,monkeypatch):
    from threading import Event
    ac,app=client; started,release=Event(),Event();calls=[]
    def control(command,args):
        calls.append(command);started.set()
        assert release.wait(timeout=5)
        return {'access_token':'fixture-access','refresh_token':'fixture-refresh'}
    monkeypatch.setattr(app.state.onboarding.control,'run',control)
    state=await start_flow(ac,'ctrader');query={'state':state,'code':'fixture-code'}
    first=asyncio.create_task(ac.get('/v1/trading/oauth/ctrader/callback',params=query))
    try:
        assert await asyncio.to_thread(started.wait,2)
        await asyncio.sleep(0)
        assert not first.done()
        pending=await act(ac,'oauth_pending',{'state':state})
        assert pending.json()['status']=='IN_PROGRESS' and pending.json()['ready'] is False
        duplicate=await ac.get('/v1/trading/oauth/ctrader/callback',params=query)
        assert duplicate.status_code==409 and calls==['ctrader_oauth_exchange']
    finally:
        release.set()
        response=await asyncio.wait_for(first,5)
    assert response.status_code==200,response.text
    assert (await ac.get('/v1/trading/oauth/ctrader/callback',params=query)).status_code==200
    assert len(calls)==1


@pytest.mark.asyncio
async def test_cancelled_token_exchange_keeps_unknown_and_a_new_state_cannot_reuse_the_code(client,monkeypatch):
    from threading import Event
    ac,app=client;started,release,finished=Event(),Event(),Event();calls=[]
    def control(command,args):
        calls.append(command);started.set()
        try:
            assert release.wait(timeout=5)
            return {'access_token':'fixture-access','refresh_token':'fixture-refresh'}
        finally:
            finished.set()
    monkeypatch.setattr(app.state.onboarding.control,'run',control)
    state=await start_flow(ac,'ctrader');query={'state':state,'code':'fixture-code'}
    task=asyncio.create_task(app.state.onboarding.oauth_callback('ctrader',query))
    try:
        assert await asyncio.wait_for(asyncio.to_thread(started.wait,2),3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        release.set()
        assert await asyncio.wait_for(asyncio.to_thread(finished.wait,2),3)
    pending=await act(ac,'oauth_pending',{'state':state})
    assert pending.json()['status']=='OUTCOME_UNCONFIRMED'
    assert pending.json()['native_reconciliation_required'] is True
    assert (await ac.get('/v1/trading/oauth/ctrader/callback',params=query)).status_code==409
    other=await start_flow(ac,'ctrader')
    assert (await ac.get('/v1/trading/oauth/ctrader/callback',params={'state':other,'code':'fixture-code'})).status_code==409
    assert len(calls)==1


@pytest.mark.asyncio
@pytest.mark.parametrize('stage',['after_material_before_receipt','after_receipt_before_commit'])
async def test_link_effect_without_a_committed_receipt_is_not_repeated_or_bypassed_by_new_state(client,monkeypatch,stage):
    from pathlib import Path
    ac,app=client;state=await ready_deriv(ac);calls=[]
    real=app.state.onboarding.control.run
    def control(command,args):
        calls.append(command)
        return real(command,args)
    monkeypatch.setattr(app.state.onboarding.control,'run',control)
    def fail(point):
        if point==stage:
            raise RuntimeError('induced transaction fault')
    app.state.onboarding.pending.effects.fault=fail
    args={'state':state,'loginid':'VRTC900','alias':'uncertain_link'}
    first=await act(ac,'deriv_oauth_link',args)
    assert first.status_code==409
    assert first.json()['effect_state']=='UNKNOWN' and first.json()['reconciliation_required'] is True
    audit=await app.state.store.fetchone("SELECT result FROM audit WHERE capability='trading.account.deriv_oauth_link' ORDER BY created_at_unix DESC,rowid DESC LIMIT 1")
    assert audit['result']=='unknown'
    app.state.onboarding.pending.effects.fault=None
    row=await app.state.store.fetchone("SELECT phase,receipt_enc FROM trading_oauth_effects WHERE state=? AND operation='LINK'",(state,))
    assert row['phase']=='UNKNOWN' and row['receipt_enc'] is None
    assert await app.state.onboarding.pending.get(state) is not None
    assert (await act(ac,'deriv_oauth_link',args)).status_code==409
    second=await ready_deriv(ac)
    assert (await act(ac,'deriv_oauth_link',{**args,'state':second})).status_code==409
    assert calls==['deriv_oauth_link']
    from van_gateway.config import get_settings
    assert (Path(get_settings().vati_secrets_dir)/'uncertain_link.env').exists()


@pytest.mark.asyncio
async def test_committed_link_receipt_survives_a_lost_response_and_a_new_reader(client,monkeypatch):
    from van_gateway.config import get_settings
    from van_gateway.storage.db import Store
    from van_gateway.trading.accounts import AccountOnboarding,OAuthPending
    ac,app=client;state=await ready_deriv(ac);calls=[];real=app.state.onboarding.control.run
    def control(command,args):
        calls.append(command)
        return real(command,args)
    monkeypatch.setattr(app.state.onboarding.control,'run',control)
    def fail(point):
        if point=='after_commit_before_reply':
            raise RuntimeError('induced lost response')
    app.state.onboarding.pending.effects.fault=fail
    args={'state':state,'loginid':'VRTC900','alias':'durable_link'}
    recovered=await act(ac,'deriv_oauth_link',args)
    assert recovered.status_code==200 and recovered.json()['account']['alias']=='durable_link'
    row=await app.state.store.fetchone("SELECT phase FROM trading_oauth_effects WHERE state=? AND operation='LINK'",(state,))
    assert row['phase']=='APPLIED'
    cold=AccountOnboarding(app.state.onboarding.control,
        OAuthPending(Store(app.state.store.path),get_settings().google_token_fernet_key),app.state.onboarding.public_base_url)
    result=await cold.run('deriv_oauth_link',args,owner_device_id='test-device')
    assert result['account']['alias']=='durable_link' and calls==['deriv_oauth_link']
    assert (await act(ac,'deriv_oauth_link',{**args,'alias':'different_alias'})).status_code==409
    pending=await act(ac,'oauth_pending',{'state':state})
    assert pending.json()=={'ready':False,'expired':True}


@pytest.mark.asyncio
async def test_real_process_death_after_claim_leaves_unconfirmed_work_without_reexchange(client,monkeypatch):
    import os,sys
    from van_gateway.config import get_settings
    from van_gateway.trading.accounts import OAuthPending
    from van_gateway.storage.db import Store
    ac,app=client;state=await start_flow(ac,'ctrader')
    script='''import asyncio,os
from van_gateway.storage.db import Store
from van_gateway.trading.accounts import OAuthPending
async def main():
 p=OAuthPending(Store(os.environ['OAUTH_FIXTURE_DB']),os.environ['OAUTH_FIXTURE_KEY'])
 await p.effects.begin(os.environ['OAUTH_FIXTURE_STATE'],'CALLBACK','ctrader',{'code':'fixture-code'})
 os._exit(73)
asyncio.run(main())
'''
    env=dict(os.environ,OAUTH_FIXTURE_DB=app.state.store.path,
        OAUTH_FIXTURE_KEY=get_settings().google_token_fernet_key,OAUTH_FIXTURE_STATE=state)
    child=await asyncio.create_subprocess_exec(sys.executable,'-c',script,env=env,
        stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.PIPE)
    _,error=await asyncio.wait_for(child.communicate(),10)
    assert child.returncode==73,error.decode()
    cold=OAuthPending(Store(app.state.store.path),get_settings().google_token_fernet_key)
    pending=await cold.effects.unconfirmed(state,'test-device')
    assert pending['status']=='OUTCOME_UNCONFIRMED' and pending['native_reconciliation_required'] is True
    def forbidden(*args):
        raise AssertionError('unknown provider effect was repeated')
    monkeypatch.setattr(app.state.onboarding.control,'run',forbidden)
    response=await ac.get('/v1/trading/oauth/ctrader/callback',params={'state':state,'code':'fixture-code'})
    assert response.status_code==409
    row=await app.state.store.fetchone("SELECT phase FROM trading_oauth_effects WHERE state=? AND operation='CALLBACK'",(state,))
    assert row['phase']=='IN_FLIGHT'


@pytest.mark.asyncio
async def test_invalid_link_alias_is_refused_before_claim_and_can_be_corrected(client):
    ac,app=client;state=await ready_deriv(ac)
    args={'state':state,'loginid':'VRTC900','alias':'invalid alias'}
    invalid=await act(ac,'deriv_oauth_link',args,expected_challenge_status=422)
    assert invalid.status_code==422
    row=await app.state.store.fetchone("SELECT phase FROM trading_oauth_effects WHERE state=? AND operation='LINK'",(state,))
    assert row is None
    repaired=await act(ac,'deriv_oauth_link',{**args,'alias':'corrected_alias'})
    assert repaired.status_code==200,repaired.text


@pytest.mark.asyncio
async def test_incomplete_provider_token_response_stays_unknown_and_cannot_be_reexchanged(client,monkeypatch):
    ac,app=client;state=await start_flow(ac,'ctrader');calls=[]
    def control(command,args):
        calls.append(command)
        return {'access_token':''}
    monkeypatch.setattr(app.state.onboarding.control,'run',control)
    query={'state':state,'code':'fixture-code'}
    assert (await ac.get('/v1/trading/oauth/ctrader/callback',params=query)).status_code==409
    assert (await act(ac,'oauth_pending',{'state':state})).json()['status']=='OUTCOME_UNCONFIRMED'
    assert (await ac.get('/v1/trading/oauth/ctrader/callback',params=query)).status_code==409
    assert calls==['ctrader_oauth_exchange']


@pytest.mark.asyncio
@pytest.mark.parametrize('field',['acct1','token1','cur1'])
async def test_missing_native_authorization_material_cannot_create_a_ready_account(field,client):
    ac,app=client;state=await start_flow(ac)
    query={'state':state,'acct1':'VRTC900','token1':'fixture-access','cur1':'USD'}
    query[field]=''
    assert (await ac.get('/v1/trading/oauth/deriv/callback',params=query)).status_code==400
    row=await app.state.store.fetchone("SELECT phase FROM trading_oauth_effects WHERE state=?",(state,))
    assert row is None
    assert (await act(ac,'oauth_pending',{'state':state})).json()=={'ready':False}


@pytest.mark.asyncio
async def test_an_encrypted_receipt_cannot_be_transplanted_to_another_link(client,monkeypatch):
    ac,app=client;states=[];calls=[];real=app.state.onboarding.control.run
    def observed(command,args):
        calls.append(command)
        return real(command,args)
    monkeypatch.setattr(app.state.onboarding.control,'run',observed)
    for alias in ('first_link','second_link'):
        state=await ready_deriv(ac);states.append(state)
        assert (await act(ac,'deriv_oauth_link',{'state':state,'loginid':'VRTC900','alias':alias})).status_code==200
    rows=[await app.state.store.fetchone("SELECT receipt_enc FROM trading_oauth_effects WHERE state=? AND operation='LINK'",(state,)) for state in states]
    await app.state.store.execute("UPDATE trading_oauth_effects SET receipt_enc=? WHERE state=? AND operation='LINK'",(rows[1]['receipt_enc'],states[0]))
    response=await act(ac,'deriv_oauth_link',{'state':states[0],'loginid':'VRTC900','alias':'first_link'})
    assert response.status_code==409
    assert calls==['deriv_oauth_link','deriv_oauth_link']


@pytest.mark.asyncio
async def test_encrypted_authorization_material_cannot_move_to_a_different_state(client):
    ac,app=client;ready=await ready_deriv(ac);other=await start_flow(ac)
    original=await app.state.store.fetchone('SELECT payload_enc FROM trading_oauth_pending WHERE state=?',(ready,))
    await app.state.store.execute('UPDATE trading_oauth_pending SET payload_enc=? WHERE state=?',(original['payload_enc'],other))
    response=await act(ac,'oauth_pending',{'state':other})
    assert response.status_code==409


@pytest.mark.asyncio
@pytest.mark.parametrize('change',[{'alias':'wrong_alias'},{'broker':'MT5'},{'mode':'AUTONOMOUS_LIVE'}])
async def test_mismatched_native_link_receipt_stays_unconfirmed(client,monkeypatch,change):
    ac,app=client;state=await ready_deriv(ac);calls=[];real=app.state.onboarding.control.run
    def changed(command,args):
        calls.append(command)
        receipt=real(command,args)
        return {**receipt,'account':{**receipt['account'],**change}}
    monkeypatch.setattr(app.state.onboarding.control,'run',changed)
    args={'state':state,'loginid':'VRTC900','alias':'receipt_bound'}
    assert (await act(ac,'deriv_oauth_link',args)).status_code==409
    assert (await act(ac,'oauth_pending',{'state':state})).json()['status']=='OUTCOME_UNCONFIRMED'
    assert (await act(ac,'deriv_oauth_link',args)).status_code==409
    assert calls==['deriv_oauth_link']
