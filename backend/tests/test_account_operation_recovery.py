"""Real paired-device/A4 gateway producer and native persistence, without brokers."""
import json
import secrets

import pytest

from test_trading_api import client, _env
from test_trading_oauth_scope import act
from test_account_resource_binding import approved


@pytest.fixture(autouse=True)
def isolated_account_files(tmp_path, monkeypatch, _env):
    from van_gateway.config import get_settings
    monkeypatch.setenv('VAN_VATI_ACCOUNTS_REGISTRY', str(tmp_path/'accounts.json'))
    monkeypatch.setenv('VAN_VATI_SECRETS_DIR', str(tmp_path/'secrets'))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_lost_reply_is_unknown_then_native_readback_confirms_original_issue(client,tmp_path,monkeypatch):
    ac,app=client
    args={'alias':'owner_mt5','server':'Broker-Demo','login':'12345678'}
    body=await approved(ac,'mt5_ea_issue_key',args)
    operation_id=body['approval_proof']['challenge_id']
    run=app.state.onboarding.control.run; calls=[]
    def lose_reply(command,values):
        result=run(command,values)
        calls.append(command)
        if command=='mt5_ea_issue_key': raise TimeoutError('fixture-private-lost-native-reply')
        return result
    with monkeypatch.context() as m:
        m.setattr(app.state.onboarding.control,'run',lose_reply)
        response=await ac.post('/v1/trading/accounts/action',json=body)
    assert response.status_code==409,response.text
    assert response.json()['effect_state']=='UNKNOWN' and response.json()['operation_id']==operation_id
    assert response.json()['reconciliation_required'] is True and 'fixture-private' not in response.text
    before=(tmp_path/'secrets/owner_mt5.env').read_bytes()
    readback=await ac.get('/v1/trading/accounts/operations/'+operation_id)
    assert readback.status_code==200,readback.text
    assert readback.json()['effect_state']=='APPLIED'
    assert readback.json()['result']['account']['alias']=='owner_mt5'
    assert readback.json()['result']['credential_export_available'] is False
    assert 'signing_key' not in readback.text
    assert calls==['mt5_ea_issue_key']
    assert (tmp_path/'secrets/owner_mt5.env').read_bytes()==before
    # Approval remains one-use. Outcome readback does not reauthorize execution.
    repeat=await ac.post('/v1/trading/accounts/action',json=body)
    assert repeat.status_code in (403,409),repeat.text
    assert (tmp_path/'secrets/owner_mt5.env').read_bytes()==before


@pytest.mark.asyncio
async def test_failed_native_completion_blocks_new_approval_but_disjoint_account_works(client,tmp_path,monkeypatch):
    from commander.account_effects import AccountEffectJournal
    ac,_=client
    body=await approved(ac,'account_upsert',{'alias':'paper_owner','broker':'PAPER'})
    def fail(*args,**kwargs): raise OSError('fixture-native-completion-failed')
    with monkeypatch.context() as m:
        m.setattr(AccountEffectJournal,'complete',fail)
        first=await ac.post('/v1/trading/accounts/action',json=body)
    assert first.status_code==409 and first.json()['effect_state']=='UNKNOWN',first.text
    blocked=await act(ac,'account_upsert',{'alias':'paper_owner','broker':'PAPER','label':'Must not overwrite'})
    assert blocked.status_code==409 and blocked.json()['reconciliation_required'] is True,blocked.text
    from vati.accounts import AccountRegistry
    assert AccountRegistry(tmp_path/'accounts.json').get('paper_owner').label=='paper_owner'
    other=await act(ac,'account_upsert',{'alias':'paper_other','broker':'PAPER'})
    assert other.status_code==200,other.text


@pytest.mark.asyncio
async def test_absence_of_a_native_record_is_never_evidence_of_no_effect(client):
    ac,_=client
    operation_id=secrets.token_urlsafe(24)
    response=await ac.get('/v1/trading/accounts/operations/'+operation_id)
    assert response.status_code==409,response.text
    assert response.json()['effect_state']=='UNKNOWN' and response.json()['operation_id']==operation_id
    assert response.json()['reconciliation_required'] is True


@pytest.mark.asyncio
async def test_operation_readback_uses_current_authenticated_device_not_a_query_override(client):
    ac,_=client
    response=await act(ac,'account_upsert',{'alias':'paper_owner','broker':'PAPER'})
    assert response.status_code==200,response.text
    # Obtain the issued identity from native public history, not from a new act.
    from vati.core.ledger import Ledger
    from vati.core.events import EventKind
    from van_gateway.config import get_settings
    led=Ledger(get_settings().vati_ledger_path)
    try: operation_id=list(led.iter(EventKind.ACCOUNT_OPERATION))[0].correlation_id
    finally: led.close()
    observed=[]
    control=ac._transport.app.state.onboarding.control
    original=control.operation
    def watched(operation_id,device_id):
        observed.append(device_id)
        return original(operation_id,device_id)
    control.operation=watched
    response=await ac.get('/v1/trading/accounts/operations/'+operation_id,params={'device_id':'foreign-device'})
    assert response.status_code==200 and observed==['test-device'],response.text


@pytest.mark.asyncio
async def test_device_cannot_inject_a_native_operation_context(client):
    ac,_=client
    args={'alias':'paper_owner','broker':'PAPER','_native_operation':{'operation_id':'invented'}}
    response=await act(ac,'account_upsert',args,expected_challenge_status=422)
    assert response.status_code==422,response.text


@pytest.mark.asyncio
async def test_approval_response_preserves_original_timestamp_across_biometric_delay(client):
    import hashlib,hmac,time
    from test_trading_api import _approval_proof
    from van_gateway.trading.accounts import canonical_action
    ac,_=client
    issued=int(time.time())-8
    args={'alias':'delayed_owner','broker':'PAPER'}
    def body(timestamp):
        return {'device_id':'test-device','issued_at_unix':timestamp,'action':'account_upsert','args':args,
            'signature':hmac.new(b'test-device-secret',canonical_action('test-device',timestamp,'account_upsert',args).encode(),hashlib.sha256).hexdigest()}
    original=body(issued)
    challenge=await ac.post('/v1/trading/accounts/challenge',json=original)
    assert challenge.status_code==200 and challenge.json()['issued_at_unix']==issued,challenge.text
    proof=_approval_proof(challenge.json())
    changed=await ac.post('/v1/trading/accounts/action',json={**body(issued+8),'approval_proof':proof})
    assert changed.status_code==403,changed.text
    confirmed=await ac.post('/v1/trading/accounts/action',json={**original,'approval_proof':proof})
    assert confirmed.status_code==200,confirmed.text
    assert confirmed.json()['operation_id']==proof['challenge_id']


@pytest.mark.asyncio
@pytest.mark.parametrize('reply_fault',['lost','wrong-command'])
async def test_signed_remote_commander_lost_reply_is_recovered_by_original_native_identity(client,tmp_path,monkeypatch,reply_fault):
    import io
    from urllib.error import HTTPError,URLError
    from fastapi.testclient import TestClient
    from commander.app import create_app,CommanderSettings
    from van_gateway.trading.accounts import CommanderAccountControl
    ac,app=client
    token='native-test-gateway-token-'+'x'*40
    token_file=tmp_path/'commander.token'; token_file.write_text(token); token_file.chmod(0o600)
    st=CommanderSettings(tokens={'van-gateway':token},ledger=str(tmp_path/'remote.sqlite'),
        accounts_registry=str(tmp_path/'accounts.json'),secrets_dir=str(tmp_path/'secrets'),
        log_dir=str(tmp_path/'native-log'))
    native=TestClient(create_app(st)); lose=[True]; calls=[]
    class Reply:
        def __init__(self,body): self.body=body
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def read(self): return self.body
    def https(request,**kwargs):
        from urllib.parse import urlsplit
        path=urlsplit(request.full_url).path
        response=native.post(path,content=request.data,headers=dict(request.header_items()))
        calls.append(path)
        if response.status_code>=400:
            raise HTTPError(request.full_url,response.status_code,'native refusal',{},io.BytesIO(response.content))
        if path.endswith('/mt5_ea_issue_key') and lose.pop():
            if reply_fault=='lost': raise URLError('injected lost remote response')
            return Reply(json.dumps({**response.json(),'command':'different-native-command'}).encode())
        return Reply(response.content)
    monkeypatch.setattr('van_gateway.trading.accounts.urlopen',https)
    app.state.onboarding.control=CommanderAccountControl('https://native.example',str(token_file))
    with native:
        body=await approved(ac,'mt5_ea_issue_key',{'alias':'remote_owner','login':'12345','server':'Broker-Demo'})
        operation_id=body['approval_proof']['challenge_id']
        first=await ac.post('/v1/trading/accounts/action',json=body)
        assert first.status_code==409 and first.json()['effect_state']=='UNKNOWN',first.text
        before=(tmp_path/'secrets/remote_owner.env').read_bytes()
        result=await ac.get('/v1/trading/accounts/operations/'+operation_id)
        assert result.status_code==200 and result.json()['effect_state']=='APPLIED',result.text
        assert calls.count('/v1/cmd/mt5_ea_issue_key')==1
        assert (tmp_path/'secrets/remote_owner.env').read_bytes()==before
