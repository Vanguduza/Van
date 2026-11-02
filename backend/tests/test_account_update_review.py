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


@pytest.mark.asyncio
@pytest.mark.parametrize('seam',['resolution','queued_writer','fsync'])
async def test_original_edit_expiry_is_checked_at_protected_writer_not_only_claim(client,tmp_path,monkeypatch,seam):
    import commander.accounts as native
    import commander.account_effects as effects
    import vati.accounts.registry as storage
    from types import SimpleNamespace
    ac,app=client;registry,original=seed(tmp_path)
    body,issued=await challenge(ac,'account_upsert',{'alias':original.alias,'label':'Expired edit'})
    identity=body['approval_proof']['challenge_id'];expiry=issued['approval_expires_at_unix'];clock=[int(time.time())]
    before=registry.path.read_bytes();version=app.state.onboarding.control.resource_version(original.alias)['resource_version']
    monkeypatch.setattr(effects,'time',SimpleNamespace(time=lambda:clock[0]))
    crossed=[]
    def expire():
        marker=effects._effect_started.get()
        if marker is not None and not marker[0]:clock[0]=expiry;crossed.append(True)
    if seam=='resolution':
        resolve=native.resolve_account_config
        def delayed(*a,**kw):
            result=resolve(*a,**kw);expire();return result
        monkeypatch.setattr(native,'resolve_account_config',delayed)
    elif seam=='queued_writer':
        from contextlib import contextmanager
        lock=storage.AccountRegistry._mutation_lock
        @contextmanager
        def delayed(self):
            with lock(self):
                expire();yield
        monkeypatch.setattr(storage.AccountRegistry,'_mutation_lock',delayed)
    else:
        fsync=storage.os.fsync
        def delayed(fd):
            fsync(fd);expire()
        monkeypatch.setattr(storage.os,'fsync',delayed)
    result=await ac.post('/v1/trading/accounts/action',json=body)
    assert crossed and result.status_code==403,result.text
    assert registry.path.read_bytes()==before
    assert app.state.onboarding.control.resource_version(original.alias)['resource_version']==version
    independent=await ac.get('/v1/trading/accounts/operations/'+identity)
    assert independent.status_code==200 and independent.json()['effect_state']=='REFUSED'
    assert not independent.json()['reconciliation_required']
    assert not (tmp_path/'secrets/owner_account.env').exists()
    assert list(tmp_path.glob('.accounts.json.*.tmp'))==[]


@pytest.mark.asyncio
@pytest.mark.parametrize('fault',['current_key','namespace','partial_credentials','empty_credential_expiry','healthy_cached'])
async def test_actual_registered_writer_preserves_authority_partial_and_cached_history(client,tmp_path,monkeypatch,fault):
    import io,os
    from urllib.error import HTTPError
    from urllib.parse import urlsplit
    from fastapi.testclient import TestClient
    from commander.app import CommanderSettings,create_app
    from commander.accounts import AccountControlSettings
    from commander.auth import sign_headers
    import commander.account_effects as effects
    import vati.accounts.registry as storage
    from van_gateway.trading.accounts import CommanderAccountControl
    from van_gateway.config import get_settings
    from types import SimpleNamespace
    ac,app=client
    if fault not in {'partial_credentials','empty_credential_expiry'}:registry,original=seed(tmp_path)
    alias='new_native' if fault in {'partial_credentials','empty_credential_expiry'} else original.alias
    token='owned-native-current-key-'*3;replacement='owned-native-replacement-key-'*3
    token_file=tmp_path/'native-token';token_file.write_text(token);token_file.chmod(0o600)
    settings=CommanderSettings(tokens={'van-gateway':token},ledger=get_settings().vati_ledger_path,
        log_dir=str(tmp_path/'native-log'),units=(),account_control=AccountControlSettings(str(tmp_path/'accounts.json'),str(tmp_path/'secrets')))
    native=TestClient(create_app(settings));captured=[]
    class Reply:
        def __init__(self,data):self.data=data
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def read(self):return self.data
    def controlled_http(request,**kw):
        path=urlsplit(request.full_url).path
        if path.endswith('/account_upsert'):captured.append(json.loads(request.data)['args'])
        result=native.post(path,content=request.data,headers=dict(request.header_items()))
        if result.status_code>=400:raise HTTPError(request.full_url,result.status_code,'owned refusal',{},io.BytesIO(result.content))
        return Reply(result.content)
    monkeypatch.setattr('van_gateway.trading.accounts.urlopen',controlled_http)
    app.state.onboarding.control=CommanderAccountControl('https://native.fixture',str(token_file))
    with native:
        args={'alias':alias,'broker':'DERIV'} if fault in {'partial_credentials','empty_credential_expiry'} else {'alias':alias,'label':'Native reviewed label'}
        body,issued=await challenge(ac,'account_upsert',args);identity=body['approval_proof']['challenge_id']
        before=(tmp_path/'accounts.json').read_bytes() if (tmp_path/'accounts.json').exists() else None
        expiry=issued['approval_expires_at_unix'];clock=[int(time.time())]
        monkeypatch.setattr(effects,'time',SimpleNamespace(time=lambda:clock[0]))
        fsync=storage.os.fsync;crossed=[]
        def delayed(fd):
            fsync(fd)
            marker=effects._effect_started.get()
            if marker is not None and ('.accounts.json.' in os.readlink('/proc/self/fd/'+str(fd)) or
                fault=='empty_credential_expiry' and '.new_native.env.' in os.readlink('/proc/self/fd/'+str(fd))):
                crossed.append(True)
                if fault=='current_key':settings.tokens['van-gateway']=replacement
                elif fault=='namespace':(tmp_path/'secrets/.account-control-domain.env').write_text('owned-malformed-current-namespace')
                elif fault in {'partial_credentials','empty_credential_expiry'}:clock[0]=expiry
        monkeypatch.setattr(storage.os,'fsync',delayed)
        result=await ac.post('/v1/trading/accounts/action',json=body)
        assert crossed
        if fault in {'current_key','namespace'}:
            assert result.status_code in {401,409},result.text
            assert (tmp_path/'accounts.json').read_bytes()==before
            from vati.core.ledger import Ledger
            from commander.account_effects import AccountEffectJournal
            led=Ledger(get_settings().vati_ledger_path)
            try:state=AccountEffectJournal(led).status(identity,'test-device')
            finally:led.close()
            assert state.phase=='REFUSED'
        elif fault=='empty_credential_expiry':
            assert result.status_code==403,result.text
            assert not (tmp_path/'accounts.json').exists() and not (tmp_path/'secrets/new_native.env').exists()
            read=await ac.get('/v1/trading/accounts/operations/'+identity)
            assert read.json()['effect_state']=='REFUSED' and not read.json()['reconciliation_required']
        elif fault=='partial_credentials':
            assert result.status_code==409 and result.json()['effect_state']=='UNKNOWN',result.text
            assert not (tmp_path/'accounts.json').exists() and (tmp_path/'secrets/new_native.env').stat().st_size==0
            read=await ac.get('/v1/trading/accounts/operations/'+identity)
            assert read.json()['effect_state']=='UNKNOWN' and read.json()['operation_id']==identity
            clock[0]=int(time.time())
            retry=await act(ac,'account_upsert',args)
            assert retry.status_code==409 and not (tmp_path/'accounts.json').exists()
        else:
            assert result.status_code==200 and result.json()['effect_state']=='APPLIED',result.text
            clock[0]=expiry+1
            original_args=captured[0];path='/v1/cmd/account_upsert';raw=json.dumps({'args':original_args}).encode()
            replay=native.post(path,content=raw,headers={**sign_headers(token,'POST',path,raw),'content-type':'application/json'})
            assert replay.status_code==200,replay.text
            assert replay.json()['result']['account']==result.json()['account']
            historical=await ac.get('/v1/trading/accounts/operations/'+identity)
            assert historical.json()['effect_state']=='APPLIED' and historical.json()['operation_id']==identity
            assert AccountRegistry(tmp_path/'accounts.json').get(alias).label=='Native reviewed label'


@pytest.mark.asyncio
async def test_real_queued_registry_writer_cannot_outwait_original_authority(client,tmp_path,monkeypatch):
    from contextlib import contextmanager
    from threading import Thread,Event
    from types import SimpleNamespace
    import commander.account_effects as effects
    from vati.accounts.registry import AccountRegistry as Registry
    ac,app=client;registry,original=seed(tmp_path)
    body,issued=await challenge(ac,'account_upsert',{'alias':original.alias,'label':'Queued expired edit'})
    expiry=issued['approval_expires_at_unix'];clock=[int(time.time())];before=registry.path.read_bytes()
    monkeypatch.setattr(effects,'time',SimpleNamespace(time=lambda:clock[0]))
    lock=Registry._mutation_lock;mutate=Registry._mutate;acquired=Event();attempted=Event();finished=Event();failures=[];workers=[]
    def holder():
        try:
            with lock(Registry(registry.path)):
                acquired.set()
                assert attempted.wait(5),'owned writer never attempted held global lock'
                clock[0]=expiry
        except BaseException as error:failures.append(error)
        finally:finished.set()
    @contextmanager
    def observed_lock(self):
        if effects._effect_started.get() is not None and workers:attempted.set()
        with lock(self):yield
    def queued(self,*a,**kw):
        if effects._effect_started.get() is not None and not workers:
            worker=Thread(target=holder,name='owned-upsert-registry-holder');workers.append(worker);worker.start()
            assert acquired.wait(5)
        return mutate(self,*a,**kw)
    monkeypatch.setattr(Registry,'_mutation_lock',observed_lock);monkeypatch.setattr(Registry,'_mutate',queued)
    try:result=await ac.post('/v1/trading/accounts/action',json=body)
    finally:
        attempted.set()
        for worker in workers:worker.join(timeout=6)
    assert workers and all(not worker.is_alive() for worker in workers) and not failures
    assert finished.is_set() and result.status_code==403,result.text
    assert registry.path.read_bytes()==before
    original_read=await ac.get('/v1/trading/accounts/operations/'+body['approval_proof']['challenge_id'])
    assert original_read.json()['effect_state']=='REFUSED' and not original_read.json()['reconciliation_required']
