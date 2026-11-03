"""Real native journal/registry/transport; all provider sockets are owned fixtures."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

import pytest
from fastapi import HTTPException

from commander.accounts import AccountControlSettings, build_account_handlers
from commander.account_effects import AccountEffectJournal, AccountOperationUnconfirmed
from vati.accounts import AccountRegistry
from vati.core.canonical import canonical_hash
from vati.core.events import EventKind
from vati.core.ledger import Ledger


class DemoPeer:
    def __init__(self, fail=''):
        self.fail=fail; self.creates=0; self.auths=0; self.reply=None; self.closed=0
    def connector(self,url):return self
    def send(self,raw):
        value=json.loads(raw); self.reply={'req_id':value['req_id']}
        if 'new_account_virtual' in value:
            self.creates+=1
            self.reply['new_account_virtual']={'client_id':'VRTC900','oauth_token':'fixture-private-native-token','currency':'USD'}
        else:
            assert value.get('authorize')=='fixture-private-native-token'
            self.auths+=1
            self.reply['authorize']={'loginid':'VRTC900','currency':'USD','balance':'10000.00','is_virtual':1,'scopes':['read','trade']}
    def recv(self):
        if self.fail=='reply' or self.fail=='identity' and self.auths:
            raise TimeoutError('owned private socket fault')
        return json.dumps(self.reply)
    def close(self):self.closed+=1


def handlers(root,peer):
    return build_account_handlers(AccountControlSettings(str(root/'accounts.json'),str(root/'secrets'),
        operation_ledger=str(root/'native.sqlite'),deriv_connector=peer.connector))


def prepare(h, **changes):
    values={'alias':'demo_owner','email':'owner@example.com','verification_code':'fixture-private-code',
        'client_password':'fixture-private-password','residence':'zw',**changes}
    values['_expected_resource_version']=h['account_revision']({'alias':values['alias']})['resource_version']
    values['_native_operation']={'operation_id':secrets.token_urlsafe(24),'device_id':'owner-device',
        'authority_ref':'fixture-consumed-approval','expires_at_unix':int(time.time())+60,
        'request_digest':canonical_hash({k:v for k,v in values.items() if not k.startswith('_')})}
    return values


def outcome(h,args):
    return h['account_operation']({'operation_id':args['_native_operation']['operation_id'],'device_id':'owner-device'})


def test_healthy_original_is_independently_verified_and_never_creates_again(tmp_path):
    peer=DemoPeer(); h=handlers(tmp_path,peer); args=prepare(h)
    first=h['deriv_create_demo'](args)
    assert first['account']['broker']=='DERIV' and first['account']['safety_identity']=='READ ONLY'
    assert first['account']['mode']=='OBSERVE' and first['account']['demo'] is True
    assert peer.creates==1 and peer.auths==2 and peer.closed>=3
    assert AccountRegistry(tmp_path/'accounts.json').get('demo_owner').login=='VRTC900'
    cold=handlers(tmp_path,peer)
    assert cold['deriv_create_demo'](args)==first
    assert outcome(cold,args)['effect_state']=='APPLIED' and peer.creates==1
    ledger=Ledger(tmp_path/'native.sqlite')
    try:
        events=list(ledger.iter(EventKind.ACCOUNT_OPERATION)); text=json.dumps([asdict(e) for e in events])
        original=AccountEffectJournal(ledger).business_events()
        assert len(original)==2
        assert len(events)==3 and len([event for event in events if AccountEffectJournal.internal_namespace_metadata(event)])==1
        assert original[0].payload['intent']['request_digest']!=args['_native_operation']['request_digest']
        assert original[0].payload['intent']['authority_ref']!=args['_native_operation']['authority_ref']
        assert all(value not in text for value in ['fixture-private-code','fixture-private-password','fixture-private-native-token','owner@example.com'])
    finally:ledger.close()


@pytest.mark.parametrize('fault',['reply','identity','credentials','registry','completion'])
def test_uncertain_remote_or_local_completion_fences_original_and_new_approval(tmp_path,monkeypatch,fault):
    peer=DemoPeer(fault); h=handlers(tmp_path,peer); args=prepare(h)
    import commander.accounts as module
    if fault=='credentials':
        original=module._write_secrets
        def fail(path,values,**kwargs):
            if values.get('DERIV_API_TOKEN'):raise OSError('private credential fault')
            return original(path,values,**kwargs)
        monkeypatch.setattr(module,'_write_secrets',fail)
    if fault=='registry':
        monkeypatch.setattr(AccountRegistry,'add',lambda *a,**k:(_ for _ in ()).throw(OSError('registry fault')))
    if fault=='completion':
        monkeypatch.setattr(AccountEffectJournal,'complete',lambda *a,**k:(_ for _ in ()).throw(OSError('commit fault')))
    with pytest.raises(AccountOperationUnconfirmed):h['deriv_create_demo'](args)
    assert outcome(h,args)['effect_state']=='UNKNOWN' and peer.creates==1
    cold=handlers(tmp_path,peer)
    for retry in [args,prepare(cold,alias='another_alias',email=' OWNER@EXAMPLE.COM ',verification_code='rotated-code',client_password='rotated-password'),
                  prepare(cold,alias='another_alias',email='',verification_code='rotated-code'),
                  prepare(cold,alias=' DEMO_OWNER ',email='other@example.com',verification_code='rotated-code',app_id='9999',label='Other profile')]:
        with pytest.raises(HTTPException):cold['deriv_create_demo'](retry)
    assert peer.creates==1


@pytest.mark.parametrize('first_email,retry_email',[(None,'owner@example.com'),('owner@example.com',None),('owner@example.com','bad-email')])
def test_ambiguous_provider_subject_overlaps_unresolved_known_subject(tmp_path,first_email,retry_email):
    peer=DemoPeer('reply'); h=handlers(tmp_path,peer)
    args=prepare(h,email=first_email)
    with pytest.raises(AccountOperationUnconfirmed):h['deriv_create_demo'](args)
    with pytest.raises(HTTPException):h['deriv_create_demo'](prepare(h,alias='new_alias',email=retry_email,verification_code='new-code'))
    assert peer.creates==1


def test_unverified_different_email_cannot_escape_but_unrelated_account_stays_operable(tmp_path):
    peer=DemoPeer('reply'); h=handlers(tmp_path,peer)
    with pytest.raises(AccountOperationUnconfirmed):h['deriv_create_demo'](prepare(h))
    peer.fail=''
    with pytest.raises(HTTPException):h['deriv_create_demo'](prepare(h,alias='independent',email='other@example.com'))
    assert peer.creates==1
    # This command does not share an unresolved account or provisioning target.
    from test_native_account_effects import prepared
    assert h['mt5_ea_issue_key'](prepared(h))['account']['alias']=='mt5_owner'


@pytest.mark.parametrize('key_fault',['missing','malformed','replaced','permissions'])
def test_lost_or_changed_vault_cannot_rekey_unresolved_creation(tmp_path,key_fault):
    peer=DemoPeer('reply'); h=handlers(tmp_path,peer); args=prepare(h)
    with pytest.raises(AccountOperationUnconfirmed):h['deriv_create_demo'](args)
    key=tmp_path/'secrets/.demo-operation-digest.env'
    if key_fault=='missing':key.unlink()
    elif key_fault=='permissions':key.chmod(0o644)
    else:key.write_text('DEMO_DIGEST_KEY='+('broken' if key_fault=='malformed' else 'a'*64)+'\n')
    with pytest.raises(HTTPException) as blocked:handlers(tmp_path,peer)['deriv_create_demo'](prepare(h,alias='new_alias',email='independent@example.com'))
    assert blocked.value.reconciliation_required
    assert outcome(h,args)['effect_state']=='UNKNOWN' and peer.creates==1


def test_completed_history_remains_readable_without_vault_key(tmp_path):
    peer=DemoPeer(); h=handlers(tmp_path,peer); args=prepare(h)
    first=h['deriv_create_demo'](args)
    (tmp_path/'secrets/.demo-operation-digest.env').unlink()
    assert outcome(handlers(tmp_path,peer),args)['result']==first
    assert peer.creates==1


def test_authenticated_namespace_is_current_state_data_without_business_effect_or_revision(tmp_path):
    from vati.accounts.resource_version import resource_snapshot
    peer=DemoPeer();h=handlers(tmp_path,peer)
    before=resource_snapshot(AccountRegistry(tmp_path/'accounts.json'),'demo_owner')['resource_version']
    first=h['account_revision']({'alias':'demo_owner'})
    assert first['resource_version']==before
    domain=first['account_control_domain']
    assert len(domain)==64 and h['account_revision']({})['account_control_domain']==domain
    assert handlers(tmp_path,peer)['account_revision']({})['account_control_domain']==domain
    assert peer.creates==0 and not (tmp_path/'accounts.json').exists()
    ledger=Ledger(tmp_path/'native.sqlite')
    try:
        assert AccountEffectJournal(ledger).business_events()==[]
        rows=list(ledger.iter(EventKind.ACCOUNT_OPERATION))
        assert len(rows)==1 and ledger.count(EventKind.ACCOUNT_OPERATION)==1
        assert rows[0].payload=={'schema':'vati.native-account-operation/1','record_type':'INTERNAL_NAMESPACE_METADATA',
            'account_control_domain':domain,'legacy_originals_bound':False,'authority_issued':False}
        assert ledger.verify_chain()[0]
    finally:ledger.close()


@pytest.mark.parametrize('fault',['missing','malformed','conflicting','missing_hint'])
def test_namespace_vault_continuity_never_mints_an_independent_replacement(tmp_path,fault):
    from commander.account_effects import PRODUCER,SCHEMA
    from vati.core.events import make_event
    peer=DemoPeer();h=handlers(tmp_path,peer);domain=h['account_revision']({})['account_control_domain']
    path=tmp_path/'secrets/.account-control-domain.env'
    if fault=='missing':
        path.unlink()
        assert handlers(tmp_path,peer)['account_revision']({})['account_control_domain']==domain
    else:
        if fault=='malformed':path.write_text('ACCOUNT_CONTROL_DOMAIN=broken\n')
        elif fault=='missing_hint':
            (tmp_path/'native.sqlite').rename(tmp_path/'preserved-original-native.sqlite')
            Ledger(tmp_path/'native.sqlite').close()
        else:
            ledger=Ledger(tmp_path/'native.sqlite')
            try:ledger.append(make_event(EventKind.ACCOUNT_OPERATION,PRODUCER,{'schema':SCHEMA,
                'record_type':'INTERNAL_NAMESPACE_METADATA','account_control_domain':'f'*64,
                'legacy_originals_bound':False,'authority_issued':False},event_time_ms=1,received_time_ms=1))
            finally:ledger.close()
        with pytest.raises(HTTPException) as blocked:handlers(tmp_path,peer)['account_revision']({})
        assert blocked.value.reconciliation_required
    assert peer.creates==0


@pytest.mark.parametrize('fault',['vault_write','commit_ack'])
def test_namespace_commit_or_vault_write_loss_recovers_only_same_immutable_hint(tmp_path,monkeypatch,fault):
    from contextlib import contextmanager
    peer=DemoPeer();h=handlers(tmp_path,peer)
    with monkeypatch.context() as patch:
        if fault=='vault_write':
            import commander.accounts as module
            write=module._write_secrets
            def fail(path,values,**kw):
                if 'ACCOUNT_CONTROL_DOMAIN' in values:raise OSError('owned lost namespace vault write')
                return write(path,values,**kw)
            patch.setattr(module,'_write_secrets',fail)
        else:
            atomic=Ledger.atomic
            @contextmanager
            def lose_ack(self):
                outer=not self._conn.in_transaction
                with atomic(self):yield self
                if outer:raise OSError('owned lost committed metadata acknowledgement')
            patch.setattr(Ledger,'atomic',lose_ack)
        with pytest.raises(HTTPException):h['account_revision']({})
    ledger=Ledger(tmp_path/'native.sqlite')
    try:
        rows=list(ledger.iter(EventKind.ACCOUNT_OPERATION));assert len(rows)==1
        domain=rows[0].payload['account_control_domain']
        assert AccountEffectJournal(ledger).business_events()==[]
    finally:ledger.close()
    assert h['account_revision']({})['account_control_domain']==domain
    assert peer.creates==0


def test_legacy_original_is_never_retroactively_bound_and_its_provider_fence_remains(tmp_path):
    from test_native_account_effects import intent
    ledger=Ledger(tmp_path/'native.sqlite')
    old=intent(command='deriv_create_demo',targets=('account:legacy_demo','deriv-demo-provisioning'))
    try:
        journal=AccountEffectJournal(ledger);claim=journal.claim(old);journal.uncertain(claim)
    finally:ledger.close()
    peer=DemoPeer();h=handlers(tmp_path,peer)
    assert h['account_revision']({})['account_control_domain']
    legacy=h['account_operation']({'operation_id':old.operation_id,'device_id':old.device_id})
    assert legacy['account_control_domain'] is None and legacy['effect_state']=='UNKNOWN'
    with pytest.raises(HTTPException):h['deriv_create_demo'](prepare(h,alias='new_alias'))
    assert peer.creates==0


def test_backup_namespace_continuity_and_independent_authenticated_native_stores(tmp_path):
    import shutil
    peer=DemoPeer();a=tmp_path/'state_a';a.mkdir();h=handlers(a,peer)
    domain=h['account_revision']({})['account_control_domain']
    b=tmp_path/'backup';shutil.copytree(a,b)
    assert handlers(b,peer)['account_revision']({})['account_control_domain']==domain
    (b/'secrets/.account-control-domain.env').unlink()
    assert handlers(b,peer)['account_revision']({})['account_control_domain']==domain
    c=tmp_path/'independent';c.mkdir()
    assert handlers(c,peer)['account_revision']({})['account_control_domain']!=domain
    args=prepare(h);args['_expected_account_control_domain']='f'*64
    with pytest.raises(HTTPException):h['deriv_create_demo'](args)
    assert peer.creates==0


def test_original_demo_result_cannot_be_read_or_reassigned_by_another_device(tmp_path):
    peer=DemoPeer();h=handlers(tmp_path,peer);args=prepare(h)
    h['deriv_create_demo'](args)
    with pytest.raises(HTTPException):h['account_operation']({'operation_id':args['_native_operation']['operation_id'],'device_id':'foreign-device'})
    args['_native_operation']['device_id']='foreign-device'
    with pytest.raises(HTTPException):h['deriv_create_demo'](args)
    assert peer.creates==1


@pytest.mark.parametrize('missing',['client_id','currency','oauth_token'])
def test_missing_original_creation_identity_cannot_invent_a_completed_account(tmp_path,missing):
    peer=DemoPeer(); original=peer.send
    def incomplete(raw):
        original(raw)
        if 'new_account_virtual' in peer.reply:peer.reply['new_account_virtual'].pop(missing)
    peer.send=incomplete
    h=handlers(tmp_path,peer);args=prepare(h)
    with pytest.raises(AccountOperationUnconfirmed):h['deriv_create_demo'](args)
    assert outcome(h,args)['effect_state']=='UNKNOWN' and peer.creates==1
    assert not (tmp_path/'accounts.json').exists()


def test_registered_signed_owner_current_key_is_rechecked_after_native_claim(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from commander.app import CommanderSettings,create_app
    from commander.auth import sign_headers
    peer=DemoPeer(); h=handlers(tmp_path,peer); args=prepare(h)
    token='current-native-fixture-token-'*3
    settings=CommanderSettings(tokens={'van-gateway':token},ledger=str(tmp_path/'native.sqlite'),
        log_dir=str(tmp_path/'log'),units=(),account_control=AccountControlSettings(str(tmp_path/'accounts.json'),
        str(tmp_path/'secrets'),deriv_connector=peer.connector))
    original=AccountEffectJournal.claim
    def rotate_after_claim(self,intent,**kwargs):
        result=original(self,intent,**kwargs)
        settings.tokens={'van-gateway':'rotated-native-fixture-token-'*3}
        return result
    monkeypatch.setattr(AccountEffectJournal,'claim',rotate_after_claim)
    path='/v1/cmd/deriv_create_demo'; body=json.dumps({'args':args,'requested_by':'van-gateway'}).encode()
    with TestClient(create_app(settings)) as client:
        response=client.post(path,content=body,headers={**sign_headers(token,'POST',path,body),'content-type':'application/json'})
        assert response.status_code==401,response.text
    assert peer.creates==0 and outcome(h,args)['effect_state']=='REFUSED'


@pytest.mark.parametrize('change',['expiry','namespace','version'])
def test_last_wire_guard_rechecks_after_slow_provider_connect(tmp_path,monkeypatch,change):
    from vati.accounts import Account
    import commander.account_effects as effects
    peer=DemoPeer();h=handlers(tmp_path,peer);args=prepare(h)
    path=tmp_path/'secrets/.account-control-domain.env';saved=path.read_bytes()
    clock=effects.time.time
    def delayed(url):
        if change=='expiry':monkeypatch.setattr(effects.time,'time',lambda:args['_native_operation']['expires_at_unix']+1)
        elif change=='namespace':path.write_text('ACCOUNT_CONTROL_DOMAIN='+'f'*64+'\n')
        else:AccountRegistry(tmp_path/'accounts.json').add(Account(alias='demo_owner',broker='PAPER',mode='OBSERVE',currency='USD'))
        return peer
    peer.connector=delayed;h=handlers(tmp_path,peer)
    try:
        with pytest.raises(HTTPException):h['deriv_create_demo'](args)
        assert peer.creates==0
    finally:
        monkeypatch.setattr(effects.time,'time',clock)
        path.write_bytes(saved)
    assert outcome(h,args)['effect_state']=='REFUSED'


def test_signed_current_token_is_rechecked_at_wire_after_connect(tmp_path):
    from fastapi.testclient import TestClient
    from commander.app import CommanderSettings,create_app
    from commander.auth import sign_headers
    peer=DemoPeer();h=handlers(tmp_path,peer);args=prepare(h)
    token='before-connect-current-token-'*3
    settings=CommanderSettings(tokens={'van-gateway':token},ledger=str(tmp_path/'native.sqlite'),
        log_dir=str(tmp_path/'log'),units=(),account_control=AccountControlSettings(str(tmp_path/'accounts.json'),
        str(tmp_path/'secrets'),deriv_connector=lambda url:connect(url)))
    def connect(url):
        settings.tokens={'van-gateway':'after-connect-rotated-token-'*3}
        return peer
    path='/v1/cmd/deriv_create_demo';body=json.dumps({'args':args}).encode()
    with TestClient(create_app(settings)) as client:
        response=client.post(path,content=body,headers={**sign_headers(token,'POST',path,body),'content-type':'application/json'})
        assert response.status_code==401,response.text
    assert peer.creates==0 and outcome(h,args)['effect_state']=='REFUSED'


def test_transport_hook_is_per_call_and_refusal_does_not_leak_into_default_read_path():
    from test_commander_accounts import FakeDeriv
    from vati.execution.transports.deriv_ws import DerivWebSocketTransport
    peer=FakeDeriv();seen=[]
    transport=DerivWebSocketTransport(app_id='1089',token_provider=lambda:'a1-virtualtoken',connector=peer.connector)
    def refuse():
        seen.append('portfolio-only')
        raise HTTPException(403,'owned original currentness refusal before send')
    try:
        with pytest.raises(HTTPException) as error:transport({'portfolio':1},before_send=refuse)
        assert error.value.status_code==403
        assert [message for message in peer.msgs if 'portfolio' in message]==[]
        assert len([message for message in peer.msgs if 'authorize' in message])==1
        assert transport({'portfolio':1})['portfolio']=={'contracts':[]}
        assert len([message for message in peer.msgs if 'portfolio' in message])==1
        assert seen==['portfolio-only']
    finally:transport.close()


@pytest.mark.parametrize('fault',['none','provider_reply','completed_reply'])
def test_legacy_signed_current_owner_without_private_metadata_has_original_intent(tmp_path,fault):
    from fastapi.testclient import TestClient
    from commander.app import CommanderSettings,create_app
    from commander.auth import sign_headers
    peer=DemoPeer('reply' if fault=='provider_reply' else '')
    token='legacy-current-native-fixture-token-'*3
    settings=CommanderSettings(tokens={'van-gateway':token,'hermes':'foreign-principal-fixture-token-'*3},
        ledger=str(tmp_path/'native.sqlite'),log_dir=str(tmp_path/'log'),units=(),
        account_control=AccountControlSettings(str(tmp_path/'accounts.json'),str(tmp_path/'secrets'),deriv_connector=peer.connector))
    app=create_app(settings)
    with TestClient(app) as client:
        drop=fault=='completed_reply'
        def call(name,args,*,token=token,headers=None):
            nonlocal drop
            path='/v1/cmd/'+name;body=json.dumps({'args':args}).encode()
            response=client.post(path,content=body,headers={**(headers or sign_headers(token,'POST',path,body)),'content-type':'application/json'})
            if name=='deriv_create_demo' and response.status_code==200 and drop:
                drop=False
                raise TimeoutError('owned transport drops completed native HTTP acknowledgement')
            return response
        args={'alias':'legacy_demo','verification_code':'fixture-private-code','client_password':'fixture-private-password','residence':'zw'}
        version=call('account_revision',{'alias':args['alias']}).json()['result']['resource_version']
        args['_expected_resource_version']=version
        path='/v1/cmd/deriv_create_demo';body=json.dumps({'args':args}).encode()
        signed=sign_headers(token,'POST',path,body)
        first=None
        if fault=='completed_reply':
            with pytest.raises(TimeoutError):call('deriv_create_demo',args,headers=signed)
        else:
            first=call('deriv_create_demo',args,headers=signed)
            assert first.status_code==(409 if fault=='provider_reply' else 200),first.text
        assert peer.creates==1
        assert call('deriv_create_demo',args,headers=signed).status_code==401
        assert call('deriv_create_demo',args,token='foreign-principal-fixture-token-'*3).status_code==403
        # Fresh transport request preserves the original after an unknown
        # response, or independently reads its completed result after lost ACK.
        retry=call('deriv_create_demo',args)
        assert retry.status_code==(409 if fault=='provider_reply' else 200),retry.text
        repeated=(retry.json()['detail']['operation_id'] if fault=='provider_reply' else retry.json()['result']['operation_id'])
        ledger=Ledger(tmp_path/'native.sqlite')
        try:original=AccountEffectJournal(ledger).business_events()[0].correlation_id
        finally:ledger.close()
        assert repeated==original and peer.creates==1
        state=call('account_operation',{'operation_id':repeated,'device_id':'commander:van-gateway'})
        assert state.status_code==200 and state.json()['result']['effect_state']==('UNKNOWN' if fault=='provider_reply' else 'APPLIED')
        if fault!='provider_reply':
            # Reconstruct the actual registered owner and reopen its durable
            # stores. The historical request keeps its pre-creation version.
            with TestClient(create_app(settings)) as rebuilt:
                recovered=rebuilt.post(path,content=body,headers={**sign_headers(token,'POST',path,body),'content-type':'application/json'})
                assert recovered.status_code==200,recovered.text
                assert recovered.json()['result']==retry.json()['result']
            current=call('account_revision',{'alias':args['alias']}).json()['result']
            assert current['resource_version']!=version
            for changed in (
                {**args,'_expected_resource_version':'1'*64},
                {**args,'_expected_resource_version':current['resource_version']},
                {**args,'client_password':'different-private-password'},
                {**args,'_expected_account_control_domain':'f'*64},
            ):
                mismatch=call('deriv_create_demo',changed)
                assert mismatch.status_code==409,mismatch.text
                assert peer.creates==1
        if fault=='provider_reply':
            args['alias']='new_alias';args['verification_code']='rotated-private-code'
            args['_expected_resource_version']=call('account_revision',{'alias':'new_alias'}).json()['result']['resource_version']
            blocked=call('deriv_create_demo',args)
            assert blocked.status_code==409 and blocked.json()['detail']['operation_id']==original
            assert peer.creates==1


@pytest.mark.parametrize('refusal',['expired','version','digest','dispatch-revoked','late-expiry','malformed'])
def test_refusal_and_currentness_checks_precede_first_provider_send(tmp_path,refusal,monkeypatch):
    peer=DemoPeer(); h=handlers(tmp_path,peer); args=prepare(h)
    if refusal=='expired':args['_native_operation']['expires_at_unix']=1
    elif refusal=='version':args['_expected_resource_version']='1'*64
    elif refusal=='digest':args['client_password']='changed-after-approval'
    elif refusal=='malformed':
        args=prepare(h,residence='invalid')
    elif refusal=='dispatch-revoked':
        def refuse():raise HTTPException(401,'current owner dispatch authority revoked')
        args['_account_dispatch_guard']=refuse
    elif refusal=='late-expiry':
        original=AccountEffectJournal.claim
        def late(self,intent,**kwargs):
            state=original(self,intent,**kwargs)
            monkeypatch.setattr('commander.account_effects.time.time',lambda:intent.expires_at_unix)
            return state
        monkeypatch.setattr(AccountEffectJournal,'claim',late)
    with pytest.raises((HTTPException,ValueError)):h['deriv_create_demo'](args)
    assert peer.creates==0 and not (tmp_path/'accounts.json').exists()


def test_real_process_death_after_send_retains_original_claim_and_never_resends(tmp_path):
    peer=DemoPeer(); h=handlers(tmp_path,peer); args=prepare(h)
    source='''import json,os,sys
from pathlib import Path
from commander.accounts import AccountControlSettings,build_account_handlers
root=Path(sys.argv[1])
class Socket:
 def send(self,raw):
  with (root/'sends').open('a') as stream: stream.write('CREATE\\n'); stream.flush(); os.fsync(stream.fileno())
  os._exit(75)
 def recv(self):raise AssertionError('unreachable')
 def close(self):pass
h=build_account_handlers(AccountControlSettings(str(root/'accounts.json'),str(root/'secrets'),operation_ledger=str(root/'native.sqlite'),deriv_connector=lambda url:Socket()))
h['deriv_create_demo'](json.loads(sys.stdin.read()))
'''
    result=subprocess.run([sys.executable,'-c',source,str(tmp_path)],input=json.dumps(args),capture_output=True,text=True,timeout=10)
    assert result.returncode==75,result.stderr
    assert (tmp_path/'sends').read_text()=='CREATE\n'
    cold=handlers(tmp_path,peer)
    assert outcome(cold,args)['native_phase']=='IN_FLIGHT'
    for retry in [args,prepare(cold,alias='new_alias',email=' OWNER@EXAMPLE.COM ',verification_code='new-code'),
                  prepare(cold,alias='demo_owner',email=None)]:
        with pytest.raises(HTTPException):cold['deriv_create_demo'](retry)
    assert peer.creates==0 and (tmp_path/'sends').read_text()=='CREATE\n'


@pytest.mark.parametrize('same_subject',[True,False])
def test_real_process_key_race_and_provider_subject_arbitration(tmp_path,same_subject):
    peer=DemoPeer(); h=handlers(tmp_path,peer)
    # Initialize only the existing SQL schema; key creation remains concurrent.
    Ledger(tmp_path/'native.sqlite').close()
    inputs=[prepare(h,alias='alias_'+str(i),email='owner@example.com' if same_subject else f'owner{i}@example.com') for i in range(2)]
    source='''import json,sys,time,os
from pathlib import Path
from fastapi import HTTPException
from commander.accounts import AccountControlSettings,build_account_handlers
root=Path(sys.argv[1]); args=json.loads(sys.stdin.read())
while not (root/'start').exists():time.sleep(.01)
class Socket:
 def send(self,raw):
  with (root/'sends').open('a') as stream:stream.write('CREATE\\n');stream.flush();os.fsync(stream.fileno())
 def recv(self):raise TimeoutError('owned lost reply')
 def close(self):pass
h=build_account_handlers(AccountControlSettings(str(root/'accounts.json'),str(root/'secrets'),operation_ledger=str(root/'native.sqlite'),deriv_connector=lambda url:Socket()))
try:h['deriv_create_demo'](args)
except HTTPException as error:
 assert error.status_code==409
else:raise AssertionError('fixture must remain uncertain')
'''
    workers=[]
    try:
        for args in inputs:
            worker=subprocess.Popen([sys.executable,'-c',source,str(tmp_path)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            worker.stdin.write(json.dumps(args));worker.stdin.close();worker.stdin=None
            workers.append(worker)
        (tmp_path/'start').touch()
        for worker in workers:
            _,error=worker.communicate(timeout=12)
            assert worker.returncode==0,error
    finally:
        for worker in workers:
            if worker.poll() is None:worker.kill();worker.wait(timeout=3)
    assert (tmp_path/'sends').read_text().count('CREATE')==1
    key=(tmp_path/'secrets/.demo-operation-digest.env')
    assert key.stat().st_mode & 0o077==0
    ledger=Ledger(tmp_path/'native.sqlite')
    try:
        claims=[event.payload['intent'] for event in AccountEffectJournal(ledger).business_events() if event.payload['phase']=='IN_FLIGHT']
        assert len(claims)==1
        assert len({next(t for t in claim['targets'] if t.startswith('deriv-demo-key:')) for claim in claims})==1
    finally:ledger.close()
