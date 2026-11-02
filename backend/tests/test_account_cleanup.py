"""Actual native child composition, SOURCE temporary stores/no hardware qualification."""
import asyncio
from contextlib import closing
import hashlib
import time

import pytest
from backend.tests.test_account_unlink_review import client,_env,isolate,paper,challenge
from backend.tests.test_account_cleanup_reauth import setup,sign
from van_gateway.trading.accounts import account_approval_text
from van_gateway.approval.account_reauth import ACTION
from commander.account_effects import AccountEffectJournal,AccountEffectIntent,AccountEffectUnknown
from commander.account_cleanup import UnlinkRecoveryBook
from vati.core import Ledger,EventKind
from vati.core.canonical import canonical_hash


@pytest.mark.asyncio
async def test_genuine_prospective_parent_unknown_new_two_proof_child_and_separate_resolution(client,tmp_path,monkeypatch):
    ac,app=client;await paper(ac)
    original,_=await challenge(ac,'account_remove',{'alias':'paper_owner'})
    parent_id=original['approval_proof']['challenge_id'];complete=AccountEffectJournal.complete
    def fail_original(self,claim,*a,**kw):
        if claim.intent.operation_id==parent_id:raise OSError('SOURCE lost original completion')
        return complete(self,claim,*a,**kw)
    with monkeypatch.context() as patch:
        patch.setattr(AccountEffectJournal,'complete',fail_original)
        result=await ac.post('/v1/trading/accounts/action',json=original)
        assert result.status_code==409 and result.json()['effect_state']=='UNKNOWN',result.text
    native_path=tmp_path/'vati.sqlite'
    with closing(Ledger(native_path)) as ledger:
        parent=AccountEffectJournal(ledger).status(parent_id,'test-device')
        assert parent.phase=='UNKNOWN' and parent.result is None
        plan_ref=UnlinkRecoveryBook(ledger,secrets_root=tmp_path/'secrets')._history(parent_id)['plan'].hash
        before=ledger.count(EventKind.ACCOUNT_OPERATION)
    loop=asyncio.get_running_loop();token=ac.headers['X-Van-Device-Token']
    def actual_read_scope():
        device=asyncio.run_coroutine_threadsafe(app.state.auth.require_access_token(token),loop).result(5)
        assert device.device_id=='test-device'
    control=app.state.onboarding.control
    args={'alias':'paper_owner','variant':'PENDING_CLEANUP','parent_operation_id':parent_id,'plan_ref':plan_ref,
          'retire_parent_safety_obligation':True}
    review=await asyncio.to_thread(control.cleanup_review,args,'test-device',actual_read_scope)
    _,reauth,who,_=await setup(client)
    context={'alias':args['alias'],'parent_operation_id':parent_id,'plan_ref':plan_ref,
        'account_control_domain':review['view']['account_control_domain'],'original_device_id':'test-device',
        'review_digest':review['context_digest'],'resource_version':review['resource_version'],
        'remaining_steps':review['view']['remaining_steps'],'retire_parent_safety_obligation':True}
    identity=await reauth.issue(who,context)
    fact=await reauth.verify(who,context,identity['challenge_id'],sign(identity['canonical']))
    child_args=args|{'reauth_fact_id':fact['reauth_fact_id'],'reauth_fact_digest':fact['fact_digest']}
    child_review=await asyncio.to_thread(control.cleanup_review,child_args,'test-device',actual_read_scope)
    assert child_review['context_digest']==review['context_digest']
    issued=int(time.time());domain=context['account_control_domain']
    text=account_approval_text('test-device',issued,'account_remove',child_args,child_review['resource_version'],domain)
    parameters={'cleanup_review':child_review,'reauth_fact_digest':fact['fact_digest']}
    permission=await reauth.approvals.issue(device_id='test-device',source_command_id='account:account_remove',turn_id=None,
        action_id=ACTION,text=text,project_id=None,parameters=parameters,_expiry_cap=fact['expires_at_unix'])
    admitted,winner=await reauth.admit(who,context,fact['reauth_fact_id'],challenge_id=permission.challenge_id,
        signature_b64=sign(permission.canonical),text=text,parameters=parameters,current_request_deadline=issued+300)
    assert winner
    native_args={**child_args,'_expected_resource_version':child_review['resource_version'],
        '_expected_review_digest':child_review['review_digest'],'_expected_account_control_domain':domain,
        '_native_operation':{'operation_id':admitted['operation_id'],'device_id':'test-device',
            'authority_ref':admitted['authority_ref']+'::review:'+child_review['review_digest'],
            'request_digest':canonical_hash(child_args),'expires_at_unix':admitted['expires_at_unix']},
        '_account_dispatch_guard':actual_read_scope}
    result=await asyncio.to_thread(control.run,'account_remove',native_args)
    assert result['cleanup_parent_operation_id']==parent_id and result['parent_original_unchanged'] is True
    with closing(Ledger(native_path)) as ledger:
        journal=AccountEffectJournal(ledger,cleanup_secrets_root=tmp_path/'secrets');parent=journal.status(parent_id,'test-device');child=journal.status(admitted['operation_id'],'test-device')
        assert parent.phase=='UNKNOWN' and parent.result is None
        assert child.phase=='APPLIED' and child.result==result
        recovery=UnlinkRecoveryBook(ledger,secrets_root=tmp_path/'secrets');assert recovery.resolved(parent_id)
        summary=recovery.summary(parent_id,'test-device')
        assert summary['linked_resolution_ref'] and summary['parent_phase']=='UNKNOWN'
        assert ledger.count(EventKind.ACCOUNT_OPERATION)==before+2
        with pytest.raises(AccountEffectUnknown):journal.claim(parent.intent)
        journal.require_clear_targets(parent.intent.targets)
    assert await asyncio.to_thread(control.run,'account_remove',native_args)==result


def request_body(args,**changes):
    import hmac
    from van_gateway.trading.accounts import canonical_action
    issued=int(time.time())
    body={'device_id':'test-device','issued_at_unix':issued,'action':'account_remove','args':args}
    body['signature']=hmac.new(b'test-device-secret',canonical_action('test-device',issued,'account_remove',args).encode(),hashlib.sha256).hexdigest()
    return body|changes


@pytest.mark.asyncio
async def test_actual_http_distinct_reauth_data_then_substantive_a4_new_child_original_readback(client,tmp_path,monkeypatch):
    ac,app=client;await paper(ac)
    original,_=await challenge(ac,'account_remove',{'alias':'paper_owner'});parent_id=original['approval_proof']['challenge_id']
    complete=AccountEffectJournal.complete
    def fail_original(self,claim,*a,**kw):
        if claim.intent.operation_id==parent_id:raise OSError('SOURCE original completion ACK lost')
        return complete(self,claim,*a,**kw)
    with monkeypatch.context() as patch:
        patch.setattr(AccountEffectJournal,'complete',fail_original)
        lost=await ac.post('/v1/trading/accounts/action',json=original)
        assert lost.status_code==409,lost.text
    old=await ac.get('/v1/trading/accounts/operations/'+parent_id)
    assert old.status_code==200 and old.json()['effect_state']=='UNKNOWN' and old.json()['result'] is None
    args={'alias':'paper_owner','variant':'PENDING_CLEANUP','parent_operation_id':parent_id,
          'plan_ref':old.json()['cleanup_recovery']['plan_ref'],'retire_parent_safety_obligation':True}
    req=request_body(args)
    issued=await ac.post('/v1/trading/accounts/cleanup/reauth/challenge',json=req)
    assert issued.status_code==200,issued.text
    assert issued.json()['execution_authority'] is False
    identity_proof={'algorithm':'ECDSA_P256_SHA256','challenge_id':issued.json()['challenge_id'],'signature_b64':sign(issued.json()['canonical'])}
    verified=await ac.post('/v1/trading/accounts/cleanup/reauth/verify',json=req|{'approval_proof':identity_proof})
    assert verified.status_code==200,verified.text
    fact=verified.json();assert fact['execution_authority'] is False
    args|={'reauth_fact_id':fact['reauth_fact_id'],'reauth_fact_digest':fact['fact_digest']}
    approved=await ac.post('/v1/trading/accounts/challenge',json=request_body(args))
    assert approved.status_code==200,approved.text
    assert approved.json()['approval_challenge_id']!=identity_proof['challenge_id']
    assert approved.json()['approval_expires_at_unix']<=fact['expires_at_unix']
    child_req=request_body(args,approval_proof={'algorithm':'ECDSA_P256_SHA256',
        'challenge_id':approved.json()['approval_challenge_id'],'signature_b64':sign(approved.json()['approval_challenge'])})
    # Challenge text binds the original issued_at; use the exact challenge's clock.
    child_req['issued_at_unix']=approved.json()['issued_at_unix']
    import hmac
    from van_gateway.trading.accounts import canonical_action
    child_req['signature']=hmac.new(b'test-device-secret',canonical_action('test-device',child_req['issued_at_unix'],'account_remove',args).encode(),hashlib.sha256).hexdigest()
    response=await ac.post('/v1/trading/accounts/action',json=child_req)
    assert response.status_code==200,response.text
    body=response.json();assert body['child_state']=='APPLIED' and body['original_parent']['effect_state']=='UNKNOWN'
    assert body['original_parent']['result'] is None and body['child']['result']['remote_account_closed'] is False
    assert body['child']['cleanup_recovery']['linked_resolution_ref']
    again=await ac.post('/v1/trading/accounts/action',json=child_req)
    assert again.status_code==200 and again.json()==body,again.text
    native=app.state.onboarding.control
    current=await asyncio.to_thread(native.operation,parent_id,'test-device',approved.json()['account_control_domain'])
    assert current['effect_state']=='UNKNOWN' and current['result'] is None
    assert not app.state.account_cleanup.tasks


async def prepare_new_cleanup(ac,args):
    req=request_body(args)
    issued=await ac.post('/v1/trading/accounts/cleanup/reauth/challenge',json=req)
    assert issued.status_code==200,issued.text
    proof={'algorithm':'ECDSA_P256_SHA256','challenge_id':issued.json()['challenge_id'],'signature_b64':sign(issued.json()['canonical'])}
    verified=await ac.post('/v1/trading/accounts/cleanup/reauth/verify',json=req|{'approval_proof':proof})
    assert verified.status_code==200,verified.text
    fact=verified.json();args=args|{'reauth_fact_id':fact['reauth_fact_id'],'reauth_fact_digest':fact['fact_digest']}
    request=request_body(args)
    approved=await ac.post('/v1/trading/accounts/challenge',json=request)
    assert approved.status_code==200,approved.text
    action=request|{'approval_proof':{'algorithm':'ECDSA_P256_SHA256','challenge_id':approved.json()['approval_challenge_id'],
                                    'signature_b64':sign(approved.json()['approval_challenge'])}}
    return action,fact


async def submit_new_cleanup(ac,args):
    action,fact=await prepare_new_cleanup(ac,args)
    result=await ac.post('/v1/trading/accounts/action',json=action)
    assert result.status_code==200,result.text
    return action,result.json(),fact


@pytest.mark.asyncio
@pytest.mark.parametrize('during_read',['healthy','new_shared_reference','new_file_generation'])
async def test_actual_original_managed_credentials_read_only_native_observation_and_cleanup(client,tmp_path,monkeypatch,during_read):
    from threading import Thread,Event
    from pathlib import Path
    from vati.accounts import Account,AccountRegistry,CredentialRef
    from vati.core.file_lock import exclusive_state_lock
    from commander.accounts import _write_secrets
    from van_gateway.trading.accounts import LocalAccountControl
    from test_retirement_venue_observations import FundsTransport
    ac,app=client
    path=tmp_path/'secrets'/'fx_primary.env'
    _write_secrets(path,{'CTRADER_CLIENT_ID':'source-fixture','CTRADER_CLIENT_SECRET':'source-fixture-private',
                         'CTRADER_ACCESS_TOKEN':'source-fixture-access'})
    registry=AccountRegistry(tmp_path/'accounts.json')
    registry.add(Account('fx_primary','CTRADER','OBSERVE','EUR',login='12345',demo=True,
                         credential_ref=CredentialRef(secrets_file=str(path))))
    Ledger(tmp_path/'vati.sqlite').close();calls=[];lock_probes=[];changed=[]
    class ReadTransport(FundsTransport):
        host='demo.ctraderapi.com'
        connection_id=1
        def connect(self):self.connected=True
        def close(self):self.connected=False
        def heartbeat_if_due(self):pass
        def call(self,name,body):
            calls.append(name)  # No credential values retained in the fixture log.
            if name=='ProtoOAApplicationAuthReq':return 'ProtoOAApplicationAuthRes',{}
            if name=='ProtoOAAccountAuthReq':return 'ProtoOAAccountAuthRes',{'ctidTraderAccountId':12345}
            if name=='ProtoOASymbolsListReq':return 'ProtoOASymbolsListRes',{'ctidTraderAccountId':12345,'symbol':[]}
            if name=='ProtoOAGetAccountListByAccessTokenReq':return 'ProtoOAGetAccountListByAccessTokenRes',{'ctidTraderAccount':[{'ctidTraderAccountId':12345}]}
            if name=='ProtoOATraderReq':
                acquired=Event()
                def local_writer():
                    with AccountRegistry(tmp_path/'accounts.json')._mutation_lock(),exclusive_state_lock(path):
                        current=AccountRegistry(tmp_path/'accounts.json')
                        if 'fx_primary' not in current.accounts and not changed and during_read!='healthy':
                            if during_read=='new_shared_reference':
                                current.add(Account('other_owner','CTRADER','OBSERVE','EUR',login='54321',demo=True,
                                    credential_ref=CredentialRef(secrets_file=str(path))))
                            else:
                                _write_secrets(path,{'CTRADER_CLIENT_ID':'source-fixture','CTRADER_CLIENT_SECRET':'source-fixture-private',
                                                     'CTRADER_ACCESS_TOKEN':'source-fixture-access'},merge=False)
                            changed.append(during_read)
                        acquired.set()
                worker=Thread(target=local_writer);worker.start()
                try:assert acquired.wait(2),'Provider I/O inherited a registry/credential writer lock'
                finally:worker.join(3)
                assert not worker.is_alive();lock_probes.append(True)
            return super().call(name,body)
    app.state.onboarding.control=LocalAccountControl(str(tmp_path/'accounts.json'),str(tmp_path/'secrets'),
        operation_ledger=str(tmp_path/'vati.sqlite'),ctrader_transport_factory=lambda _:ReadTransport())
    try:original,_=await challenge(ac,'account_remove',{'alias':'fx_primary'})
    except AssertionError as failure:raise AssertionError('SOURCE readonly protocol names: '+repr(calls)) from failure
    parent_id=original['approval_proof']['challenge_id']
    step=UnlinkRecoveryBook.step
    def die_after_registry(self,*a,**kw):
        result=step(self,*a,**kw)
        if a[0]==parent_id and a[4:]==('REGISTRY_REMOVE','DONE'):raise OSError('SOURCE crash window after registry removal')
        return result
    with monkeypatch.context() as patch:
        patch.setattr(UnlinkRecoveryBook,'step',die_after_registry)
        unknown=await ac.post('/v1/trading/accounts/action',json=original)
        assert unknown.status_code==409 and unknown.json()['effect_state']=='UNKNOWN',unknown.text
    assert path.is_file() and 'fx_primary' not in AccountRegistry(tmp_path/'accounts.json').accounts
    with pytest.raises(Exception):AccountRegistry(tmp_path/'accounts.json').credentials('fx_primary')
    parent=await ac.get('/v1/trading/accounts/operations/'+parent_id)
    assert parent.json()['result'] is None
    args={'alias':'fx_primary','variant':'PENDING_CLEANUP','parent_operation_id':parent_id,
        'plan_ref':parent.json()['cleanup_recovery']['plan_ref'],'retire_parent_safety_obligation':True}
    if during_read!='healthy':
        import sqlite3
        with sqlite3.connect(tmp_path/'vati.sqlite') as db:count=db.execute('SELECT COUNT(*) FROM account_unlink_facts').fetchone()[0]
        refused=await ac.post('/v1/trading/accounts/cleanup/reauth/challenge',json=request_body(args))
        assert refused.status_code==409 and changed==[during_read],refused.text
        assert path.is_file() and 'fx_primary' not in AccountRegistry(tmp_path/'accounts.json').accounts
        if during_read=='new_shared_reference':assert AccountRegistry(tmp_path/'accounts.json').get('other_owner')
        with sqlite3.connect(tmp_path/'vati.sqlite') as db:assert db.execute('SELECT COUNT(*) FROM account_unlink_facts').fetchone()[0]==count
        assert not {'ProtoOANewOrderReq','ProtoOACancelOrderReq','ProtoOAWithdrawReq'}.intersection(calls)
        old=await ac.get('/v1/trading/accounts/operations/'+parent_id)
        assert old.status_code==200 and old.json()['effect_state']=='UNKNOWN' and old.json()['result'] is None
        return
    action,result,fact=await submit_new_cleanup(ac,args)
    assert result['child_state']=='APPLIED' and result['original_parent']['effect_state']=='UNKNOWN',result
    assert result['child']['result']['retained_remote_funds']=={'balance':'100.25','equity':'100.25','currency':'EUR'}
    assert not path.exists() and lock_probes
    assert not {'ProtoOANewOrderReq','ProtoOACancelOrderReq','ProtoOAWithdrawReq'}.intersection(calls)
    assert 'fx_primary' not in AccountRegistry(tmp_path/'accounts.json').accounts
    with pytest.raises(Exception):AccountRegistry(tmp_path/'accounts.json').credentials('fx_primary')
    read=await ac.get('/v1/trading/accounts/cleanup/operations/'+result['operation_id'])
    assert read.status_code==200 and read.json()==result,read.text
    spent=await ac.get('/v1/trading/accounts/cleanup/reauth/facts/'+fact['reauth_fact_id'])
    assert spent.status_code==200 and spent.json()['state']=='SPENT_DATA' and spent.headers['cache-control']=='no-store'
    assert 'source-fixture-private' not in json_text(result)


def json_text(value):return __import__('json').dumps(value,sort_keys=True)


async def pending_paper(client,tmp_path,monkeypatch):
    from vati.accounts import AccountRegistry
    ac,app=client;await paper(ac)
    account=AccountRegistry(tmp_path/'accounts.json').get('paper_owner')
    original,_=await challenge(ac,'account_remove',{'alias':'paper_owner'});parent=original['approval_proof']['challenge_id']
    complete=AccountEffectJournal.complete
    def unknown(self,claim,*a,**kw):
        if claim.intent.operation_id==parent:raise OSError('SOURCE parent completion unconfirmed')
        return complete(self,claim,*a,**kw)
    with monkeypatch.context() as patch:
        patch.setattr(AccountEffectJournal,'complete',unknown)
        response=await ac.post('/v1/trading/accounts/action',json=original)
        assert response.status_code==409,response.text
    read=await ac.get('/v1/trading/accounts/operations/'+parent)
    assert read.json()['effect_state']=='UNKNOWN' and read.json()['result'] is None
    args={'alias':'paper_owner','variant':'PENDING_CLEANUP','parent_operation_id':parent,
        'plan_ref':read.json()['cleanup_recovery']['plan_ref'],'retire_parent_safety_obligation':True}
    return args,account


@pytest.mark.asyncio
@pytest.mark.parametrize('fault',['wrong_plan','wrong_parent','recreated_same_account','missing_domain_key','corrupt_plan'])
async def test_actual_http_unqualified_original_state_holds_without_new_fact_or_key_restore(client,tmp_path,monkeypatch,fault):
    import sqlite3
    from vati.accounts import AccountRegistry
    from van_gateway.approval.account_reauth import EPHEMERAL
    ac,app=client;args,account=await pending_paper(client,tmp_path,monkeypatch)
    domain=tmp_path/'secrets'/'.account-control-domain.env'
    if fault=='wrong_plan':args['plan_ref']='0'*64
    elif fault=='wrong_parent':args['parent_operation_id']='unknown_original_parent_0001'
    elif fault=='recreated_same_account':AccountRegistry(tmp_path/'accounts.json').add(account)
    elif fault=='missing_domain_key':domain.unlink()
    elif fault=='corrupt_plan':
        with sqlite3.connect(tmp_path/'vati.sqlite') as db:
            db.execute('UPDATE account_unlink_facts SET body_json=? WHERE operation_id=? AND seq=1',('[]',args['parent_operation_id']))
    with closing(Ledger(tmp_path/'vati.sqlite')) as ledger:before=ledger.count(EventKind.ACCOUNT_OPERATION)
    result=await ac.post('/v1/trading/accounts/cleanup/reauth/challenge',json=request_body(args))
    assert result.status_code==409,result.text
    assert not await app.state.store.fetchall('SELECT key FROM runtime_meta WHERE key GLOB ?',(EPHEMERAL+'*',))
    with closing(Ledger(tmp_path/'vati.sqlite')) as ledger:
        assert ledger.count(EventKind.ACCOUNT_OPERATION)==before
        original=AccountEffectJournal(ledger).status((await ac.get('/v1/trading/accounts/operations/'+args['parent_operation_id'])).json().get('operation_id',args['parent_operation_id']),'test-device')
        if original is not None:assert original.phase=='UNKNOWN' and original.result is None
    if fault=='missing_domain_key':
        assert not domain.exists()
        assert (await ac.get('/v1/trading/accounts/operations/'+args['parent_operation_id'])).status_code==409
        assert not domain.exists()
    if fault=='recreated_same_account':assert AccountRegistry(tmp_path/'accounts.json').get(account.alias)==account


@pytest.mark.asyncio
async def test_actual_http_hard_purpose_lockout_restart_and_valid_proof_no_bypass(client,tmp_path,monkeypatch):
    from van_gateway.approval.account_reauth import AccountReauthentication
    from van_gateway.storage.db import Store
    ac,app=client;args,_=await pending_paper(client,tmp_path,monkeypatch);req=request_body(args)
    issued=await ac.post('/v1/trading/accounts/cleanup/reauth/challenge',json=req)
    assert issued.status_code==200,issued.text
    for number in range(5):
        result=await ac.post('/v1/trading/accounts/cleanup/reauth/verify',json=req|{'approval_proof':{
            'algorithm':'ECDSA_P256_SHA256','challenge_id':issued.json()['challenge_id'],'signature_b64':'YmFk'}})
        assert result.status_code==(429 if number==4 else 403),result.text
    locked=result.json()['detail']['locked_until']
    assert 0<int(result.headers['retry-after'])<=900
    app.state.account_cleanup.reauth=AccountReauthentication(Store(app.state.store.path),app.state.account_cleanup.authorize)
    current=await ac.post('/v1/trading/accounts/cleanup/reauth/verify',json=req|{'approval_proof':{
        'algorithm':'ECDSA_P256_SHA256','challenge_id':issued.json()['challenge_id'],'signature_b64':sign(issued.json()['canonical'])}})
    assert current.status_code==429 and current.json()['detail']['locked_until']==locked,current.text
    again=await ac.post('/v1/trading/accounts/cleanup/reauth/challenge',json=request_body(args))
    assert again.status_code==429 and again.json()['detail']['locked_until']==locked


@pytest.mark.asyncio
@pytest.mark.parametrize('fault',['rewritten_plan_and_head','lost_key','replaced_same_bytes_key','head_seal','domain_replay','unsealed_history','symlink_key'])
async def test_sealed_original_plan_holds_tamper_without_recreation_or_child(client,tmp_path,monkeypatch,fault):
    """SOURCE controlled private-state tamper; not a native rollback guarantee."""
    import json
    import os
    import sqlite3
    from commander.account_cleanup import CleanupFact,is_technical
    ac,app=client;args,_=await pending_paper(client,tmp_path,monkeypatch)
    key=tmp_path/'secrets'/'private.unlink-plan-integrity.env'
    assert key.stat().st_mode&0o777==0o600
    key_before=key.read_bytes();parent=args['parent_operation_id']
    with sqlite3.connect(tmp_path/'vati.sqlite') as db:
        before=db.execute('SELECT COUNT(*) FROM account_unlink_facts').fetchone()[0]
        if fault=='rewritten_plan_and_head':
            rows=db.execute('SELECT seq,body_json FROM account_unlink_facts WHERE operation_id=? ORDER BY seq',(parent,)).fetchall()
            previous='';plan_ref=None
            for seq,raw in rows:
                body=json.loads(raw);seal=body.pop('integrity');p=body['payload']
                p['previous_ref']=previous
                if p['kind']=='PLAN':p['data']['account_identity']['login']='forged-different-original'
                else:p['data']['plan_ref']=plan_ref
                ref=canonical_hash(body)
                if plan_ref is None:plan_ref=ref
                # Exact strict domain shape and all plain chain/head hashes now agree.
                assert is_technical(CleanupFact(p,body['received_at_ms'],ref))
                seal['context']['fact_ref']=ref
                body['integrity']=seal
                db.execute('UPDATE account_unlink_facts SET body_json=?,fact_ref=? WHERE operation_id=? AND seq=?',
                           (json.dumps(body),ref,parent,seq));previous=ref
            raw_head=json.loads(db.execute('SELECT integrity_json FROM account_unlink_heads WHERE operation_id=?',(parent,)).fetchone()[0])
            raw_head['context']['fact_ref']=previous
            db.execute('UPDATE account_unlink_heads SET fact_ref=?,integrity_json=? WHERE operation_id=?',(previous,json.dumps(raw_head),parent))
        elif fault=='head_seal':
            raw=json.loads(db.execute('SELECT integrity_json FROM account_unlink_heads WHERE operation_id=?',(parent,)).fetchone()[0]);raw['mac']='0'*64
            db.execute('UPDATE account_unlink_heads SET integrity_json=? WHERE operation_id=?',(json.dumps(raw),parent))
        elif fault=='unsealed_history':
            for seq,raw in db.execute('SELECT seq,body_json FROM account_unlink_facts WHERE operation_id=?',(parent,)).fetchall():
                body=json.loads(raw);del body['integrity']
                db.execute('UPDATE account_unlink_facts SET body_json=? WHERE operation_id=? AND seq=?',(json.dumps(body),parent,seq))
    if fault=='lost_key':key.unlink()
    elif fault=='replaced_same_bytes_key':
        replacement=key.with_suffix('.replacement');replacement.write_bytes(key_before);replacement.chmod(0o600);os.replace(replacement,key)
    elif fault=='symlink_key':
        foreign=tmp_path/'foreign_integrity_key.env';foreign.write_bytes(key_before);foreign.chmod(0o600)
        key.unlink();key.symlink_to(foreign)
    elif fault=='domain_replay':
        domain=tmp_path/'secrets'/'.account-control-domain.env'
        domain.write_text('ACCOUNT_CONTROL_DOMAIN='+'a'*64+'\n');domain.chmod(0o600)
    read=await ac.get('/v1/trading/accounts/operations/'+parent)
    assert read.status_code==409,read.text
    response=await ac.post('/v1/trading/accounts/cleanup/reauth/challenge',json=request_body(args))
    assert response.status_code==409,response.text
    with sqlite3.connect(tmp_path/'vati.sqlite') as db:assert db.execute('SELECT COUNT(*) FROM account_unlink_facts').fetchone()[0]==before
    with closing(Ledger(tmp_path/'vati.sqlite')) as ledger:
        original=AccountEffectJournal(ledger).status(parent,'test-device')
        assert original.phase=='UNKNOWN' and original.result is None
    if fault=='lost_key':assert not key.exists()  # neither status nor challenge regenerates
    else:assert key.read_bytes()==key_before
    if fault=='symlink_key':assert not foreign.with_name(foreign.name+'.lock').exists()
    assert await app.state.store.fetchone("SELECT key FROM runtime_meta WHERE key GLOB 'account_cleanup_ephemeral:*'") is None


@pytest.mark.asyncio
async def test_sealed_plan_restart_and_unrelated_demo_key_change_do_not_reseal_original(client,tmp_path,monkeypatch):
    from commander.accounts import _write_secrets
    ac,app=client;args,_=await pending_paper(client,tmp_path,monkeypatch)
    key=tmp_path/'secrets'/'private.unlink-plan-integrity.env';before=key.read_bytes()
    _write_secrets(tmp_path/'secrets'/'.demo-operation-digest.env',{'DEMO_DIGEST_KEY':'e'*64},merge=False)
    with closing(Ledger(tmp_path/'vati.sqlite')) as ledger:
        history=UnlinkRecoveryBook(ledger,initialize=False,secrets_root=tmp_path/'secrets')._history(args['parent_operation_id'])
        assert history['plan'].hash==args['plan_ref']
    read=await ac.get('/v1/trading/accounts/operations/'+args['parent_operation_id'])
    assert read.status_code==200 and read.json()['effect_state']=='UNKNOWN' and read.json()['result'] is None
    assert key.read_bytes()==before


@pytest.mark.asyncio
async def test_separate_resolution_allows_fresh_ordinary_intent_but_never_parent_replay_or_other_unknown(client,tmp_path,monkeypatch):
    from dataclasses import replace
    from vati.accounts import AccountRegistry
    ac,app=client;args,_=await pending_paper(client,tmp_path,monkeypatch)
    action,child,_=await submit_new_cleanup(ac,args)
    assert child['child_state']=='APPLIED' and child['original_parent']['result'] is None
    await paper(ac)  # a genuinely new approved native account generation
    before=(tmp_path/'accounts.json').read_bytes()
    with closing(Ledger(tmp_path/'vati.sqlite')) as ledger:
        journal=AccountEffectJournal(ledger,cleanup_secrets_root=tmp_path/'secrets')
        old=journal.status(args['parent_operation_id'],'test-device')
        assert old.phase=='UNKNOWN' and old.result is None
        with pytest.raises(AccountEffectUnknown):journal.claim(old.intent)
    assert (tmp_path/'accounts.json').read_bytes()==before
    fresh,_=await challenge(ac,'account_remove',{'alias':'paper_owner'})
    removed=await ac.post('/v1/trading/accounts/action',json=fresh)
    assert removed.status_code==200,removed.text
    await paper(ac)
    # A different genuine durable original is never excused by the first resolution.
    with closing(Ledger(tmp_path/'vati.sqlite')) as ledger:
        journal=AccountEffectJournal(ledger,cleanup_secrets_root=tmp_path/'secrets')
        other=replace(old.intent,operation_id='other_unresolved_original_0001',request_digest='e'*64,expires_at_unix=int(time.time())+60)
        pending=journal.claim(other);journal.uncertain(pending)
    denied=await ac.post('/v1/trading/accounts/challenge',json=request_body({'alias':'paper_owner'}))
    assert denied.status_code==409,denied.text
    assert AccountRegistry(tmp_path/'accounts.json').get('paper_owner')
    with closing(Ledger(tmp_path/'vati.sqlite')) as ledger:
        journal=AccountEffectJournal(ledger)
        assert journal.status(args['parent_operation_id'],'test-device').phase=='UNKNOWN'
        assert journal.status(other.operation_id,'test-device').phase=='UNKNOWN'


@pytest.mark.asyncio
@pytest.mark.parametrize('ordering',['admitted_before_dispatch','applied_before_reply'])
async def test_gateway_cancellation_preserves_original_admission_and_never_resends(client,tmp_path,monkeypatch,ordering):
    import threading
    from van_gateway.approval.account_reauth import ADMISSIONS
    ac,app=client;args,_=await pending_paper(client,tmp_path,monkeypatch)
    action,_=await prepare_new_cleanup(ac,args)
    operation=action['approval_proof']['challenge_id'];control=app.state.onboarding.control
    run=control.run;sends=[];reached=asyncio.Event();release_async=asyncio.Event();release_thread=threading.Event()
    loop=asyncio.get_running_loop()
    def observed(command,values):
        if command=='account_remove' and values.get('variant')=='PENDING_CLEANUP':
            sends.append(values['_native_operation']['operation_id'])
            result=run(command,values)
            if ordering=='applied_before_reply':
                loop.call_soon_threadsafe(reached.set)
                assert release_thread.wait(5)
            return result
        return run(command,values)
    monkeypatch.setattr(control,'run',observed)
    admit=app.state.account_cleanup.reauth.admit
    if ordering=='admitted_before_dispatch':
        async def gated(*a,**kw):
            result=await admit(*a,**kw)
            reached.set();await release_async.wait()
            return result
        monkeypatch.setattr(app.state.account_cleanup.reauth,'admit',gated)
    task=asyncio.create_task(ac.post('/v1/trading/accounts/action',json=action))
    await asyncio.wait_for(reached.wait(),5)
    row=await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(ADMISSIONS+operation,))
    assert row is not None
    before=row['value'];task.cancel()
    # Let _finish record cancellation before releasing its already-owned worker.
    await asyncio.sleep(0)
    release_async.set();release_thread.set()
    with pytest.raises(asyncio.CancelledError):await task
    assert not app.state.account_cleanup.tasks
    assert (await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(ADMISSIONS+operation,)))['value']==before
    read=await ac.get('/v1/trading/accounts/cleanup/operations/'+operation)
    assert read.status_code==200,read.text
    expected='UNRESOLVED' if ordering=='admitted_before_dispatch' else 'APPLIED'
    assert read.json()['child_state']==expected,read.text
    repeated=await ac.post('/v1/trading/accounts/action',json=action)
    assert repeated.status_code==200 and repeated.json()==read.json(),repeated.text
    assert sends==([] if ordering=='admitted_before_dispatch' else [operation])
    parent=await ac.get('/v1/trading/accounts/operations/'+args['parent_operation_id'])
    assert parent.json()['effect_state']=='UNKNOWN' and parent.json()['result'] is None


@pytest.mark.asyncio
async def test_same_child_late_concurrent_original_recovers_winner_without_reselection(client,tmp_path,monkeypatch):
    ac,app=client;args,_=await pending_paper(client,tmp_path,monkeypatch)
    action,_=await prepare_new_cleanup(ac,args)
    service=app.state.account_cleanup;review=service.review
    reached=asyncio.Event();release=asyncio.Event();first=True;sends=[]
    async def delayed_review(*a,**kw):
        nonlocal first
        if first:
            first=False;reached.set();await release.wait()
        return await review(*a,**kw)
    run=app.state.onboarding.control.run
    def counted(command,values):
        if command=='account_remove' and values.get('variant')=='PENDING_CLEANUP':sends.append(values['_native_operation']['operation_id'])
        return run(command,values)
    monkeypatch.setattr(service,'review',delayed_review)
    monkeypatch.setattr(app.state.onboarding.control,'run',counted)
    late=asyncio.create_task(ac.post('/v1/trading/accounts/action',json=action))
    await asyncio.wait_for(reached.wait(),5)
    try:
        winner=await ac.post('/v1/trading/accounts/action',json=action)
        assert winner.status_code==200 and winner.json()['child_state']=='APPLIED',winner.text
    finally:release.set()
    loser=await late
    assert loser.status_code==200 and loser.json()==winner.json(),loser.text
    assert sends==[action['approval_proof']['challenge_id']]


@pytest.mark.asyncio
@pytest.mark.parametrize('window',['registry_may_begin','registry_done','completion'])
async def test_actual_original_process_death_new_child_and_late_epoch_original_never_reopens(client,tmp_path,monkeypatch,window):
    """Paired gateway original; real owned native process death/temp PAPER DB.

    Existing trusted LocalAccountControl child harness, not deployed/hardware
    authority or a provider/remote-effect qualification.
    """
    import subprocess,sys,json
    from van_gateway.trading.accounts import LocalAccountControl
    ac,app=client;await paper(ac)
    original,_=await challenge(ac,'account_remove',{'alias':'paper_owner'})
    parent=original['approval_proof']['challenge_id'];native=app.state.onboarding.control.run;children=[]
    source='''import json,os,sys
from commander.accounts import AccountControlSettings,build_account_handlers
from commander.account_effects import AccountEffectJournal
from commander.account_cleanup import UnlinkRecoveryBook
root,window=sys.argv[1:3]
step=UnlinkRecoveryBook.step
def crashing_step(self,*a,**kw):
 result=step(self,*a,**kw)
 if (window=='registry_may_begin' and a[4:]==('REGISTRY_REMOVE','MAY_BEGIN') or window=='registry_done' and a[4:]==('REGISTRY_REMOVE','DONE')):os._exit(74)
 return result
UnlinkRecoveryBook.step=crashing_step
if window=='completion':AccountEffectJournal.complete=lambda *a,**kw:os._exit(74)
handlers=build_account_handlers(AccountControlSettings(root+'/accounts.json',root+'/secrets',operation_ledger=root+'/vati.sqlite'))
handlers['account_remove'](json.loads(sys.argv[3]))
'''
    def killed(command,args):
        if command!='account_remove':return native(command,args)
        child=subprocess.run([sys.executable,'-c',source,str(tmp_path),window,json.dumps(args)],capture_output=True,timeout=12)
        children.append(child.returncode)
        assert child.returncode==74,child.stderr.decode()[:400]
        raise ConnectionError('SOURCE actual original process terminated before result ACK')
    with monkeypatch.context() as patch:
        patch.setattr(app.state.onboarding.control,'run',killed)
        response=await ac.post('/v1/trading/accounts/action',json=original)
        assert response.status_code==409 and response.json()['effect_state']=='UNKNOWN',response.text
    assert children==[74]
    app.state.onboarding.control=LocalAccountControl(str(tmp_path/'accounts.json'),str(tmp_path/'secrets'),operation_ledger=str(tmp_path/'vati.sqlite'))
    read=await ac.get('/v1/trading/accounts/operations/'+parent)
    assert read.status_code==200 and read.json()['result'] is None,read.text
    args={'alias':'paper_owner','variant':'PENDING_CLEANUP','parent_operation_id':parent,
          'plan_ref':read.json()['cleanup_recovery']['plan_ref'],'retire_parent_safety_obligation':True}
    from vati.app.sqlite_lease import SQLiteLeaseStore
    lease_store=SQLiteLeaseStore(tmp_path/'vati.sqlite')
    try:old_lease=lease_store.read('paper_owner')
    finally:lease_store.close()
    assert old_lease is not None
    if old_lease.live_at(int(time.time()*1000)):
        held=await ac.post('/v1/trading/accounts/cleanup/reauth/challenge',json=request_body(args))
        assert held.status_code==409,held.text  # PID absence is NOT lease/authority absence
        wait=max(0,(old_lease.expires_at_ms-int(time.time()*1000))/1000)+.05
        assert wait<=31
        await asyncio.sleep(wait)  # actual expiry, not a future clock or PID bypass
    else:
        # The completion-ACK crash occurs AFTER the original finally released
        # its lease. Do not invent a new live lease or delay fresh owner intent.
        assert old_lease.expires_at_ms<=int(time.time()*1000)
    action,result,_=await submit_new_cleanup(ac,args)
    assert result['child_state']=='APPLIED' and result['original_parent']['effect_state']=='UNKNOWN'
    with closing(Ledger(tmp_path/'vati.sqlite')) as ledger:
        book=UnlinkRecoveryBook(ledger,initialize=False,secrets_root=tmp_path/'secrets')
        history=book._history(parent);assert history['epoch']==2 and history['resolution'] is not None
        with pytest.raises(AccountEffectUnknown):book.require_epoch(parent,args['plan_ref'],1,parent)
        journal=AccountEffectJournal(ledger,cleanup_secrets_root=tmp_path/'secrets')
        old=journal.status(parent,'test-device');assert old.phase=='UNKNOWN' and old.result is None
        before=ledger.count(EventKind.ACCOUNT_OPERATION)
        with pytest.raises(AccountEffectUnknown):journal.claim(old.intent)
        assert ledger.count(EventKind.ACCOUNT_OPERATION)==before
    again=await ac.post('/v1/trading/accounts/action',json=action)
    assert again.status_code==200 and again.json()==result,again.text
    assert children==[74]


@pytest.mark.asyncio
@pytest.mark.parametrize('change',['key_replacement','device_revocation','token_rotation'])
async def test_admitted_original_actor_proof_and_current_owner_guards_after_native_sql_wait(client,tmp_path,monkeypatch,change):
    """Root continuity decision: mere key replacement is not issued-grant revocation.

    Trusted SOURCE state changes, not a new production rotation/enrollment route.
    """
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from van_gateway.approval.account_reauth import ADMISSIONS
    from van_gateway.approval.service import OwnerApprovalService,OwnerApprovalError
    import base64
    from cryptography.hazmat.primitives import hashes
    ac,app=client;args,_=await pending_paper(client,tmp_path,monkeypatch)
    action,_=await prepare_new_cleanup(ac,args);loop=asyncio.get_running_loop()
    begin=UnlinkRecoveryBook.begin_child;changed=[];original_record=[];sends=[]
    replacement=ec.generate_private_key(ec.SECP256R1())
    key=replacement.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    run=app.state.onboarding.control.run
    def counted(command,values):
        if command=='account_remove' and values.get('variant')=='PENDING_CLEANUP':sends.append(values['_native_operation']['operation_id'])
        return run(command,values)
    monkeypatch.setattr(app.state.onboarding.control,'run',counted)
    def changed_after_committed_epoch(self,*a,**kw):
        epoch=begin(self,*a,**kw)
        record=asyncio.run_coroutine_threadsafe(app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',
            (ADMISSIONS+action['approval_proof']['challenge_id'],)),loop).result(5)
        original_record.append(record['value'])
        if change=='key_replacement':sql,params="UPDATE devices SET public_key_pem=? WHERE device_id='test-device'",(key,)
        elif change=='device_revocation':sql,params="UPDATE devices SET revoked_at_unix=? WHERE device_id='test-device'",(int(time.time()),)
        else:sql,params="UPDATE devices SET access_token_hash=? WHERE device_id='test-device'",('a'*64,)
        asyncio.run_coroutine_threadsafe(app.state.store.execute(sql,params),loop).result(5)
        changed.append(epoch)
        return epoch
    monkeypatch.setattr(UnlinkRecoveryBook,'begin_child',changed_after_committed_epoch)
    response=await ac.post('/v1/trading/accounts/action',json=action)
    assert response.status_code==200 and changed==[2],response.text
    permitted=change=='key_replacement'
    assert response.json()['child_state']==('APPLIED' if permitted else 'REFUSED'),response.text
    assert response.json()['resolution_state']==('QUALIFIED_SEPARATE_FACT' if permitted else 'HELD')
    assert response.json()['original_parent']['result'] is None
    current=await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(ADMISSIONS+action['approval_proof']['challenge_id'],))
    assert current['value']==original_record[0]  # no actor rewrite, receipt/expiry extension
    with closing(Ledger(tmp_path/'vati.sqlite')) as ledger:
        book=UnlinkRecoveryBook(ledger,initialize=False,secrets_root=tmp_path/'secrets')
        assert book.resolved(args['parent_operation_id']) is permitted
    replay=await ac.post('/v1/trading/accounts/action',json=action)
    if permitted:
        assert replay.status_code==200 and replay.json()==response.json()
        # A NEW proof uses the NEW currently enrolled key; old-key authentication
        # is not revived by preserving the previous immutable issued permission.
        approvals=OwnerApprovalService(app.state.store)
        issued=await approvals.issue(device_id='test-device',source_command_id='account:account_remove',turn_id=None,
            action_id=ACTION,text='SOURCE exact current-key verification only',project_id=None)
        values=dict(challenge_id=issued.challenge_id,source_command_id='account:account_remove',device_id='test-device',
            turn_id=None,action_id=ACTION,text='SOURCE exact current-key verification only',project_id=None)
        with pytest.raises(OwnerApprovalError,match='approval_signature_invalid'):
            await approvals.verify_and_consume(**values,signature_b64=sign(issued.canonical))
        signature=base64.b64encode(replacement.sign(issued.canonical.encode(),ec.ECDSA(hashes.SHA256()))).decode()
        assert (await approvals.verify_and_consume(**values,signature_b64=signature))['operation_id']==issued.challenge_id
    else:assert replay.status_code==401,replay.text
    assert sends==[action['approval_proof']['challenge_id']]


def test_cleanup_imports_preserve_actual_existing_private_core_import_guard(tmp_path,monkeypatch):
    """Execute the unchanged original guard, with scratch-only child resources.

    Authentication fixture settings and every original import/refusal assertion
    remain the existing guard's; only bytecode/cache/temp routing is supplied.
    """
    import importlib.util,subprocess,sys,os
    from pathlib import Path
    path=Path(__file__).resolve().parents[2]/'tests/contracts/test_van_private_core_topology.py'
    spec=importlib.util.spec_from_file_location('owned_actual_private_core_contract',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    run=subprocess.run;calls=[]
    scratch_tmp=tmp_path/'private-import-temp';scratch_tmp.mkdir()
    scratch_cache=tmp_path/'private-import-cache';scratch_cache.mkdir()
    def scratch_run(argv,*a,**kw):
        assert argv[0]==sys.executable and argv[1]=='-c'
        original=dict(kw['env']);assert original=={'VAN_INTERNAL_CONTROL_SCOPED_TOKENS':'','PATH':'/usr/bin:/bin'}
        kw['env']={**original,'PYTHONDONTWRITEBYTECODE':'1','TMPDIR':str(scratch_tmp),'XDG_CACHE_HOME':str(scratch_cache)}
        calls.append(tuple(argv[:2]))
        return run(argv,*a,**kw)
    monkeypatch.setattr(module.subprocess,'run',scratch_run)
    module.test_private_core_app_import_closure_excludes_forbidden_code()
    assert calls==[(sys.executable,'-c')]


@pytest.mark.asyncio
async def test_current_paired_cleanup_and_published_fixture_consumers_share_canonical_signing_owner(client):
    """Actual enrollment/proof provenance, including all four reviewed consumers."""
    import importlib,sys
    canonical=importlib.import_module('backend.tests.test_trading_api')
    for name in ('test_account_operation_recovery','test_account_resource_binding','test_stateful_link_binding','test_trading_oauth_effects'):
        consumer=importlib.import_module('backend.tests.'+name)
        assert consumer.client is canonical.client and consumer._env is canonical._env
        if hasattr(consumer,'_approval_proof'):assert consumer._approval_proof is canonical._approval_proof
    assert sign.__globals__['DEVICE_KEY'] is canonical.DEVICE_KEY
    assert not any(name=='test_trading_api' and module is not canonical for name,module in sys.modules.items())
    ac,app=client
    device=await app.state.store.fetchone("SELECT public_key_pem FROM devices WHERE device_id='test-device'")
    assert device['public_key_pem']==canonical.DEVICE_PEM
    assert (await ac.get('/v1/trading/accounts')).status_code==200
