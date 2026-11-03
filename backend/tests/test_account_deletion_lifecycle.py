"""Actual paired HTTP -> native journal/registry -> cold readback. SOURCE only."""
import asyncio,hashlib,hmac,json,time
from contextlib import closing
from dataclasses import replace
from pathlib import Path
import pytest
from backend.tests.test_account_unlink_review import client,_env,isolate,paper
from backend.tests.test_trading_api import _approval_proof
from backend.tests.test_account_cleanup_reauth import sign
from van_gateway.trading.accounts import canonical_action
from commander.accounts import AccountControlSettings,build_account_handlers
from vati.accounts import AccountRegistry
from vati.core import Ledger,EventKind


def body(args):
    issued=int(time.time());action='account_remove'
    return {'device_id':'test-device','issued_at_unix':issued,'action':action,'args':args,
        'signature':hmac.new(b'test-device-secret',canonical_action('test-device',issued,action,args).encode(),hashlib.sha256).hexdigest()}

async def configure(client,tmp_path):
    ac,app=client;await paper(ac)
    config=tmp_path/'session.json'
    config.write_text(json.dumps({'account_alias':'paper_owner','symbol':'EURUSD','base':'EUR','quote':'USD','timeframe':'M5',
        'contract':{},'mandate':{},'capsules':['fx_trend_pullback-v1'],'registry_path':str(tmp_path/'accounts.json')}))
    settings=AccountControlSettings(registry_path=str(tmp_path/'accounts.json'),secrets_dir=str(tmp_path/'secrets'),
        operation_ledger=str(tmp_path/'vati.sqlite'),lifecycle_session_sources=((str(config),hashlib.sha256(config.read_bytes()).hexdigest()),))
    app.state.onboarding.control.settings=settings
    app.state.onboarding.control.handlers=build_account_handlers(settings)
    app.state.account_lifecycle.bind_local_admission_verifier()
    return ac,app,settings,config

async def approved(ac,args,reauth_family="lifecycle"):
    b=body(args)
    first=await ac.post('/v1/trading/accounts/'+reauth_family+'/reauth/challenge',json=b)
    assert first.status_code==200,first.text
    issued=first.json()
    proof={'challenge_id':issued['challenge_id'],'signature_b64':sign(issued['canonical']),'algorithm':'ECDSA_P256_SHA256'}
    fact=await ac.post('/v1/trading/accounts/'+reauth_family+'/reauth/verify',json=b|{'approval_proof':proof})
    assert fact.status_code==200,fact.text
    args=args|{'reauth_fact_id':fact.json()['reauth_fact_id'],'reauth_fact_digest':fact.json()['fact_digest']}
    b=body(args);challenge=await ac.post('/v1/trading/accounts/challenge',json=b)
    assert challenge.status_code==200,challenge.text
    assert challenge.json()['approval_challenge_id']!=issued['challenge_id']
    return b|{'approval_proof':_approval_proof(challenge.json())}

async def deletion(ac,grace=600,alias="paper_owner"):
    res=await ac.post('/v1/trading/accounts/lifecycle/prepare',json=body({'alias':alias,'variant':'DELETE_GRACE','grace_seconds':grace}))
    assert res.status_code==200,res.text
    return await approved(ac,res.json()['args'])

@pytest.mark.asyncio
async def test_actual_two_proof_delete_cancel_cold_readback_never_restores_strategy(client,tmp_path):
    ac,app,settings,config=await configure(client,tmp_path)
    b=await deletion(ac);result=await ac.post('/v1/trading/accounts/action',json=b)
    assert result.status_code==200 and result.json()['effect_state']=='APPLIED',result.text
    original=b['approval_proof']['challenge_id']
    cold=AccountRegistry(tmp_path/'accounts.json')
    assert 'paper_owner' not in cold.accounts
    assert cold._lifecycles['paper_owner']['operation_id']==original
    state=await ac.get('/v1/trading/accounts/lifecycle/records/paper_owner')
    assert state.status_code==200,state.text
    row=state.json();assert row['phase']=='PENDING_ARCHIVE' and row['grace_seconds']==600
    assert row['strategies']==['fx_trend_pullback-v1'] and row['execution_authority'] is False
    replay=await ac.post('/v1/trading/accounts/action',json=b)
    assert replay.json()==result.json()
    cancel=await approved(ac,{'alias':'paper_owner','variant':'CANCEL_DELETE','lifecycle_id':original,
        'expected_revision':row['revision'],'expected_digest':row['record_digest']})
    cancelled=await ac.post('/v1/trading/accounts/action',json=cancel)
    assert cancelled.json()['effect_state']=='APPLIED',cancelled.text
    cold=AccountRegistry(tmp_path/'accounts.json');restored=cold.get('paper_owner')
    assert restored.mode=='OBSERVE' and restored.enabled is False and restored.mandate_ref==''
    assert cold._lifecycles['paper_owner']['phase']=='RELINK_REQUIRED'
    assert cold._lifecycles['paper_owner']['restore'] is None
    assert config.read_text().find('fx_trend_pullback-v1')>=0 # config is not rewritten as authority
    with closing(Ledger(tmp_path/'vati.sqlite')) as led:
        assert led.verify_chain()[0]
        from commander.account_effects import AccountEffectJournal
        assert AccountEffectJournal(led).status(original,'test-device').phase=='APPLIED'

@pytest.mark.asyncio
async def test_grace_expiry_archives_only_metadata_after_owner_permission_expires(client,tmp_path,monkeypatch):
    ac,app,settings,_=await configure(client,tmp_path)
    b=await deletion(ac,grace=1);res=await ac.post('/v1/trading/accounts/action',json=b)
    assert res.json()['effect_state']=='APPLIED',res.text
    before=AccountRegistry(tmp_path/'accounts.json')._lifecycles['paper_owner']
    with closing(Ledger(tmp_path/'vati.sqlite')) as led:chain=led.count(EventKind.ACCOUNT_OPERATION)
    from commander.account_lifecycle import NativeLifecycle
    monkeypatch.setattr(NativeLifecycle,'__init__',late_init:=lambda self,*a,**kw:old_init(self,*a,**kw,clock=lambda:before['archive_at_unix']+10000))
    # Original effect authority has expired, but the only later transition is DATA.
    get=await ac.get('/v1/trading/accounts/lifecycle/records/paper_owner')
    assert get.status_code==200 and get.json()['phase']=='ARCHIVED',get.text
    cold=AccountRegistry(tmp_path/'accounts.json');row=cold._lifecycles['paper_owner']
    assert row['restore'] is None and row['session_sources']==[] and row['detached'] is True
    with closing(Ledger(tmp_path/'vati.sqlite')) as led:assert led.count(EventKind.ACCOUNT_OPERATION)==chain and led.verify_chain()[0]

from commander.account_lifecycle import NativeLifecycle
old_init=NativeLifecycle.__init__

@pytest.mark.parametrize('grace',[None,0,-1,True,'7',2**31])
@pytest.mark.asyncio
async def test_missing_invalid_grace_never_selects_default(client,tmp_path,grace):
    ac,app,_,_=await configure(client,tmp_path)
    a={'alias':'paper_owner','variant':'DELETE_GRACE'}
    if grace is not None:a['grace_seconds']=grace
    prepare=await ac.post('/v1/trading/accounts/lifecycle/prepare',json=body(a))
    if prepare.status_code==200:
        response=await ac.post('/v1/trading/accounts/lifecycle/reauth/challenge',json=body(prepare.json()['args']))
        assert response.status_code==422,response.text
    else:assert prepare.status_code==422,prepare.text
    assert AccountRegistry(tmp_path/'accounts.json').get('paper_owner')

@pytest.mark.asyncio
async def test_missing_native_config_scope_holds_before_either_proof(client,tmp_path):
    ac,app,settings,_=await configure(client,tmp_path)
    app.state.onboarding.control.handlers=build_account_handlers(replace(settings,lifecycle_session_sources=None))
    prepared=await ac.post('/v1/trading/accounts/lifecycle/prepare',json=body({'alias':'paper_owner','variant':'DELETE_GRACE','grace_seconds':600}))
    response=await ac.post('/v1/trading/accounts/lifecycle/reauth/challenge',json=body(prepared.json()['args']))
    assert response.status_code==409 and 'scope' in response.text.lower(),response.text
    assert AccountRegistry(tmp_path/'accounts.json').get('paper_owner')

@pytest.mark.asyncio
async def test_changed_native_config_after_two_proofs_refuses_no_native_effect(client,tmp_path):
    ac,app,_,config=await configure(client,tmp_path)
    b=await deletion(ac);config.write_text(config.read_text()+' ')
    response=await ac.post('/v1/trading/accounts/action',json=b)
    assert response.status_code==409,response.text
    assert AccountRegistry(tmp_path/'accounts.json').get('paper_owner')

@pytest.mark.asyncio
async def test_lost_native_ack_replays_original_read_only_and_preserves_original_id(client,tmp_path,monkeypatch):
    ac,app,_,_=await configure(client,tmp_path);b=await deletion(ac)
    control=app.state.onboarding.control;run=control.run;sent=[]
    def lost(command,args):
        result=run(command,args)
        if command=='account_remove':sent.append(args['_native_operation']['operation_id']);raise ConnectionError('SOURCE lost ACK')
        return result
    monkeypatch.setattr(control,'run',lost)
    first=await ac.post('/v1/trading/accounts/action',json=b);second=await ac.post('/v1/trading/accounts/action',json=b)
    assert first.json()['effect_state']==second.json()['effect_state']=='APPLIED'
    assert sent==[b['approval_proof']['challenge_id']]

@pytest.mark.asyncio
async def test_reauth_hard_counter_has_distinct_stable_purpose_and_cannot_reset_by_context(client,tmp_path):
    ac,app,_,_=await configure(client,tmp_path)
    prepared=await ac.post('/v1/trading/accounts/lifecycle/prepare',json=body({'alias':'paper_owner','variant':'DELETE_GRACE','grace_seconds':600}))
    args=prepared.json()['args']
    for n in range(5):
        b=body(args)
        challenge=await ac.post('/v1/trading/accounts/lifecycle/reauth/challenge',json=b)
        assert challenge.status_code==200,challenge.text
        proof={'challenge_id':challenge.json()['challenge_id'],'signature_b64':sign(challenge.json()['canonical']+'wrong'),
            'algorithm':'ECDSA_P256_SHA256'}
        fail=await ac.post('/v1/trading/accounts/lifecycle/reauth/verify',json=b|{'approval_proof':proof})
        assert fail.status_code==(429 if n==4 else 403),fail.text
    # A different grace/review cannot reset this purpose's scoped hard counter.
    args['grace_seconds']=601
    blocked=await ac.post('/v1/trading/accounts/lifecycle/reauth/challenge',json=body(args))
    assert blocked.status_code==429 and 'Retry-After' in blocked.headers,blocked.text
    from backend.tests.test_account_cleanup_reauth import setup
    _,old,who,context=await setup(client)
    independent=await old.issue(who,context)
    assert independent['purpose']=='ACCOUNT_PENDING_CLEANUP_REAUTH_DATA'
    assert AccountRegistry(tmp_path/'accounts.json').get('paper_owner')

@pytest.mark.asyncio
async def test_actual_duplicate_concurrent_http_actions_have_one_original_native_effect(client,tmp_path):
    ac,app,_,_=await configure(client,tmp_path);b=await deletion(ac)
    results=await asyncio.gather(*(ac.post('/v1/trading/accounts/action',json=b) for _ in range(2)))
    assert all(r.status_code==200 for r in results),[r.text for r in results]
    assert {r.json()['effect_state'] for r in results}<={'APPLIED','UNKNOWN'}
    final=await ac.get('/v1/trading/accounts/lifecycle/operations/'+b['approval_proof']['challenge_id'])
    assert final.json()['effect_state']=='APPLIED',final.text
    from commander.account_effects import AccountEffectJournal
    with closing(Ledger(tmp_path/'vati.sqlite')) as led:
        same=[e for e in AccountEffectJournal(led).business_events() if e.payload['intent']['operation_id']==b['approval_proof']['challenge_id']]
        assert len(same)==2 and [e.payload['phase'] for e in same]==['IN_FLIGHT','APPLIED']

@pytest.mark.asyncio
async def test_native_revoke_after_gateway_admission_prevents_first_registry_write(client,tmp_path,monkeypatch):
    ac,app,_,_=await configure(client,tmp_path);b=await deletion(ac)
    control=app.state.onboarding.control;run=control.run
    def late_revoke(command,args):
        if command=='account_remove':
            from fastapi import HTTPException
            args={**args,'_account_dispatch_guard':lambda:(_ for _ in ()).throw(HTTPException(403,'SOURCE current native transport actor revoked'))}
        return run(command,args)
    monkeypatch.setattr(control,'run',late_revoke)
    result=await ac.post('/v1/trading/accounts/action',json=b)
    assert result.json()['effect_state'] in {'REFUSED','UNKNOWN'},result.text
    assert AccountRegistry(tmp_path/'accounts.json').get('paper_owner')
    assert not AccountRegistry(tmp_path/'accounts.json')._lifecycles

@pytest.mark.asyncio
async def test_real_account_secret_is_destroyed_now_and_cancel_holds_without_independent_open_fact(client,tmp_path,monkeypatch):
    ac,app,settings,config=await configure(client,tmp_path)
    from backend.tests.test_account_unlink_review import native_funds
    _,secret,account=native_funds(tmp_path,monkeypatch)
    data=json.loads(config.read_text());data['account_alias']=account.alias;config.write_text(json.dumps(data))
    settings=replace(settings,lifecycle_session_sources=((str(config),hashlib.sha256(config.read_bytes()).hexdigest()),))
    app.state.onboarding.control.handlers=build_account_handlers(settings)
    from commander import accounts as native_accounts
    real_shred=native_accounts._shred;primitive_errors=[]
    def observed_shred(*a,**kw):
        try:return real_shred(*a,**kw)
        except Exception as error:
            primitive_errors.append((type(error).__name__,str(error)))
            raise
    monkeypatch.setattr(native_accounts,'_shred',observed_shred)
    b=await deletion(ac,alias=account.alias)
    result=await ac.post('/v1/trading/accounts/action',json=b)
    assert result.json()['effect_state']=='APPLIED',(result.text,primitive_errors)
    assert not secret.exists() # grace has NOT elapsed; destruction is immediate
    row=(await ac.get('/v1/trading/accounts/lifecycle/records/'+account.alias)).json()
    args={'alias':account.alias,'variant':'CANCEL_DELETE','lifecycle_id':row['operation_id'],'expected_revision':row['revision'],'expected_digest':row['record_digest']}
    refusal=await ac.post('/v1/trading/accounts/lifecycle/reauth/challenge',json=body(args))
    assert refusal.status_code==409 and 'closure' in refusal.text.lower(),refusal.text
    def observation(ctx):return ctx|{'state':'CLOSED','source_ref':'8'*64,'observed_at_ms':int(time.time()*1000)}
    app.state.onboarding.control.handlers=build_account_handlers(replace(settings,lifecycle_remote_state_reader=observation))
    refused=await ac.post('/v1/trading/accounts/lifecycle/reauth/challenge',json=body(args))
    assert refused.status_code==409,refused.text
    def open_state(ctx):return ctx|{'state':'OPEN','source_ref':'8'*64,'observed_at_ms':int(time.time()*1000)}
    app.state.onboarding.control.handlers=build_account_handlers(replace(settings,lifecycle_remote_state_reader=open_state))
    cancel=await approved(ac,args);done=await ac.post('/v1/trading/accounts/action',json=cancel)
    assert done.json()['effect_state']=='APPLIED',done.text
    restored=AccountRegistry(tmp_path/'accounts.json').get(account.alias)
    assert not restored.enabled and restored.mode=='OBSERVE' and not secret.exists()

@pytest.mark.asyncio
async def test_oauth_exact_scope_unselected_attempt_survives_and_original_unknown_blocks_delete(client,tmp_path):
    ac,app,_,_=await configure(client,tmp_path)
    pending=app.state.onboarding.pending
    unselected=await pending.create('deriv',{'_owner_device_id':'test-device','app_id':'1089'})
    b=await deletion(ac)
    result=await ac.post('/v1/trading/accounts/action',json=b)
    assert result.json()['effect_state']=='APPLIED',result.text
    assert await pending.get(unselected) is not None
    # Independent alias's ambiguous original LINK is never erased or retried.
    await app.state.store.execute("INSERT INTO trading_oauth_effects(state,operation,broker,owner_device_id,request_digest,target_key,phase,worker_id,created_at_unix,updated_at_unix) VALUES(?,?,?,?,?,?,?,?,?,?)",
        ('unknown-original','LINK','deriv','test-device','1'*64,'account:other_owner','UNKNOWN','old',1,1))
    from van_gateway.trading.oauth_effects import OAuthEffectUnconfirmed
    with pytest.raises(OAuthEffectUnconfirmed):
        await pending.effects.lifecycle_plan('other_owner','test-device',await asyncio.to_thread(app.state.onboarding.control.domain))
    row=await app.state.store.fetchone("SELECT phase FROM trading_oauth_effects WHERE state='unknown-original'")
    assert row['phase']=='UNKNOWN' and await pending.get(unselected) is not None

@pytest.mark.asyncio
@pytest.mark.parametrize('window',['metadata_first','journal_completion'])
async def test_new_grace_original_uses_unchanged_genuine_pending_cleanup_child_then_metadata_only_reconciles(client,tmp_path,monkeypatch,window):
    ac,app,_,_=await configure(client,tmp_path);b=await deletion(ac)
    original=b['approval_proof']['challenge_id']
    from commander.account_effects import AccountEffectJournal
    with monkeypatch.context() as patch:
        if window=='metadata_first':
            update=AccountRegistry.lifecycle_update;seen=[]
            def interrupted(self,*a,**kw):
                value=update(self,*a,**kw);seen.append(True)
                # The reservation is DATA only; retain this oracle at the
                # original account-removal replacement, not its call ordinal.
                if 'paper_owner' not in self.accounts and self._lifecycles['paper_owner']['phase']=='DELETING':
                    raise OSError('SOURCE lost account-removal metadata replacement ACK')
                return value
            patch.setattr(AccountRegistry,'lifecycle_update',interrupted)
        else:
            complete=AccountEffectJournal.complete
            def interrupted(self,claim,*a,**kw):
                if claim.intent.operation_id==original:raise OSError('SOURCE lost original completion')
                return complete(self,claim,*a,**kw)
            patch.setattr(AccountEffectJournal,'complete',interrupted)
        result=await ac.post('/v1/trading/accounts/action',json=b)
        assert result.json()['effect_state']=='UNKNOWN',result.text
    held=await ac.get('/v1/trading/accounts/lifecycle/records/paper_owner')
    assert held.status_code==200 and held.json()['native_original_phase']=='UNKNOWN',held.text
    start=held.json()['created_at_unix'];deadline=held.json()['archive_at_unix']
    status=await ac.get('/v1/trading/accounts/operations/'+original)
    assert status.json()['effect_state']=='UNKNOWN' and status.json()['result'] is None,status.text
    plan=status.json()['cleanup_recovery']['plan_ref']
    child_args={'alias':'paper_owner','variant':'PENDING_CLEANUP','parent_operation_id':original,'plan_ref':plan,'retire_parent_safety_obligation':True}
    child=await approved(ac,child_args,reauth_family='cleanup')
    applied=await ac.post('/v1/trading/accounts/action',json=child)
    assert applied.status_code==200 and applied.json()['child_state']=='APPLIED',applied.text
    assert applied.json()['resolution_state']=='QUALIFIED_SEPARATE_FACT'
    observed=await ac.get('/v1/trading/accounts/lifecycle/records/paper_owner')
    assert observed.status_code==200 and observed.json()['phase']=='PENDING_ARCHIVE',observed.text
    assert observed.json()['created_at_unix']==start and observed.json()['archive_at_unix']==deadline
    assert observed.json()['native_original_phase']=='UNKNOWN' # historical original never rewritten
    with closing(Ledger(tmp_path/'vati.sqlite')) as led:
        original_state=AccountEffectJournal(led).status(original,'test-device')
        assert original_state.phase=='UNKNOWN' and original_state.result is None
    row=observed.json()
    cancel=await approved(ac,{'alias':'paper_owner','variant':'CANCEL_DELETE','lifecycle_id':original,
        'expected_revision':row['revision'],'expected_digest':row['record_digest']})
    done=await ac.post('/v1/trading/accounts/action',json=cancel)
    assert done.json()['effect_state']=='APPLIED',done.text
    assert not AccountRegistry(tmp_path/'accounts.json').get('paper_owner').enabled
    from backend.tests.test_account_update_review import immediate_challenge
    new_body,_=await immediate_challenge(ac,'paper_owner')
    fresh=await ac.post('/v1/trading/accounts/action',json=new_body)
    assert fresh.status_code==200 and fresh.json()['effect_state']=='APPLIED',fresh.text
    cold=AccountRegistry(tmp_path/'accounts.json')
    assert cold._lifecycle_history[original]['phase']=='RELINK_REQUIRED'
    with closing(Ledger(tmp_path/'vati.sqlite')) as led:
        old=AccountEffectJournal(led).status(original,'test-device')
        assert old.phase=='UNKNOWN' and old.result is None
    read=await ac.get('/v1/trading/accounts/lifecycle/operations/'+original)
    assert read.status_code==200 and read.json()['effect_state']=='UNKNOWN' and read.json()['native']['result'] is None

@pytest.mark.asyncio
async def test_full_context_guard_catches_native_strategy_scope_replacement_after_real_a4_admission(client,tmp_path,monkeypatch):
    ac,app,settings,config=await configure(client,tmp_path);b=await deletion(ac)
    control=app.state.onboarding.control;run=control.run
    def changed(command,args):
        if command=='account_remove':
            data=json.loads(config.read_text());data['capsules']=['different-native-strategy-v1'];config.write_text(json.dumps(data))
            current=replace(settings,lifecycle_session_sources=((str(config),hashlib.sha256(config.read_bytes()).hexdigest()),))
            control.handlers=build_account_handlers(current)
        return run(command,args)
    monkeypatch.setattr(control,'run',changed)
    result=await ac.post('/v1/trading/accounts/action',json=b)
    assert result.json()['effect_state']=='REFUSED',result.text
    assert AccountRegistry(tmp_path/'accounts.json').get('paper_owner')
    assert not AccountRegistry(tmp_path/'accounts.json')._lifecycles

@pytest.mark.asyncio
async def test_existing_retention_owner_only_prunes_new_raw_purpose_not_admissions_unknowns_or_financial_history(client,tmp_path):
    ac,app,_,_=await configure(client,tmp_path)
    prepared=await ac.post('/v1/trading/accounts/lifecycle/prepare',json=body({'alias':'paper_owner','variant':'DELETE_GRACE','grace_seconds':600}))
    args=prepared.json()['args'];b=body(args)
    issued=await ac.post('/v1/trading/accounts/lifecycle/reauth/challenge',json=b)
    proof={'challenge_id':issued.json()['challenge_id'],'signature_b64':sign(issued.json()['canonical']),'algorithm':'ECDSA_P256_SHA256'}
    raw=await ac.post('/v1/trading/accounts/lifecycle/reauth/verify',json=b|{'approval_proof':proof})
    assert raw.status_code==200,raw.text
    complete=await approved(ac,args);result=await ac.post('/v1/trading/accounts/action',json=complete)
    assert result.json()['effect_state']=='APPLIED',result.text
    from van_gateway.approval.account_lifecycle_reauth import EPHEMERAL,ADMISSIONS,USED
    from van_gateway.ops.retention import RetentionService
    unknown=EPHEMERAL+'fact:unreadable-original-source'
    await app.state.store.execute('INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?)',(unknown,'{}',1))
    with closing(Ledger(tmp_path/'vati.sqlite')) as led:before=[e.hash for e in led.iter()]
    await RetentionService(app.state.store).prune(now_ms=int(time.time()*1000)+8*86400*1000,tables=('runtime_meta',))
    assert not await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(EPHEMERAL+'fact:'+raw.json()['reauth_fact_id'],))
    assert await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(ADMISSIONS+complete['approval_proof']['challenge_id'],))
    assert await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(USED+complete['args']['reauth_fact_id'],))
    assert await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(unknown,))
    with closing(Ledger(tmp_path/'vati.sqlite')) as led:
        assert [e.hash for e in led.iter()]==before and led.verify_chain()[0]

@pytest.mark.asyncio
@pytest.mark.parametrize('fault',['healthy_pure_boundary','expires_after_fstat'])
async def test_actual_managed_shred_last_boundary_is_pure_and_rechecks_original_permission_clock(client,tmp_path,monkeypatch,fault):
    ac,app,settings,config=await configure(client,tmp_path)
    from backend.tests.test_account_unlink_review import native_funds
    _,secret,account=native_funds(tmp_path,monkeypatch);original_bytes=secret.read_bytes()
    data=json.loads(config.read_text());data['account_alias']=account.alias;config.write_text(json.dumps(data))
    settings=replace(settings,lifecycle_session_sources=((str(config),hashlib.sha256(config.read_bytes()).hexdigest()),))
    app.state.onboarding.control.handlers=build_account_handlers(settings)
    b=await deletion(ac,alias=account.alias)
    control=app.state.onboarding.control;run=control.run;stage={'after_fstat':False};last=[];expiry=[]
    def guarded_native(command,args):
        if command=='account_remove':
            expiry.append(args['_native_operation']['expires_at_unix']);actual=args['_account_dispatch_guard']
            def actor():
                assert not stage['after_fstat'],'A blocking current-actor read followed final credential identity check'
                actual()
            args={**args,'_account_dispatch_guard':actor}
        return run(command,args)
    monkeypatch.setattr(control,'run',guarded_native)
    from commander import accounts as native
    import commander.account_effects as effects
    shred=native._shred
    def observed(path,**kw):
        mark=kw['before_effect']
        def last_check():
            stage['after_fstat']=True;last.append(True)
            try:
                if fault=='expires_after_fstat':monkeypatch.setattr(effects,'time',NS(time=lambda:expiry[0]))
                mark()
            finally:stage['after_fstat']=False
        return shred(path,**{**kw,'before_effect':last_check})
    from types import SimpleNamespace as NS
    monkeypatch.setattr(native,'_shred',observed)
    result=await ac.post('/v1/trading/accounts/action',json=b)
    if fault=='healthy_pure_boundary':
        assert result.json()['effect_state']=='APPLIED' and not secret.exists(),result.text
        assert len(last)==2
    else:
        assert result.json()['effect_state']=='UNKNOWN' and secret.read_bytes()==original_bytes,result.text
        assert len(last)==1
        row=AccountRegistry(tmp_path/'accounts.json')._lifecycles[account.alias]
        assert row['phase']=='DELETING' and result.json()['native']['result'] is None

@pytest.mark.asyncio
async def test_actual_catalog_exposes_both_legacy_and_typed_lifecycle_effect_contracts(client,tmp_path):
    ac,_,_,_=await configure(client,tmp_path)
    res=await ac.get('/v1/trading/accounts/catalog');assert res.status_code==200,res.text
    item=next(x for x in res.json()['actions'] if x['action']=='account_remove')
    variants=item['input_schema']['oneOf']
    assert len(variants)==4 and all('variant' in x['required'] for x in variants)
    assert variants[0]['properties']['variant']['enum']==['PENDING_CLEANUP']
    for variant in ('DELETE_GRACE','CANCEL_DELETE','IMMEDIATE_DISCONNECT'):
        schema=next(x for x in variants if x.get('properties',{}).get('variant',{}).get('const')==variant)
        assert schema['additionalProperties'] is False
        assert {'reauth_fact_id','reauth_fact_digest'}<=set(schema['required'])
        if variant=='DELETE_GRACE':assert {'grace_seconds','oauth_discard_digest'}<=set(schema['required'])
        if variant=='IMMEDIATE_DISCONNECT':assert 'oauth_discard_digest' in schema['required'] and 'grace_seconds' not in schema['properties']
    refused=await ac.post('/v1/trading/accounts/challenge',json=body({'alias':'paper_owner','variant':'unrecognized-delete'}))
    assert refused.status_code==422 and AccountRegistry(tmp_path/'accounts.json').get('paper_owner')

@pytest.mark.asyncio
@pytest.mark.parametrize('boundary',['REGISTRY_REMOVE','CREDENTIAL_OVERWRITE','CREDENTIAL_UNLINK'])
async def test_actual_config_change_after_committed_step_refuses_next_physical_effect(client,tmp_path,monkeypatch,boundary):
    """A committed technical step is a blocking wait, not fresh source review."""
    ac,app,settings,config=await configure(client,tmp_path)
    from backend.tests.test_account_unlink_review import native_funds
    from commander.account_cleanup import UnlinkRecoveryBook
    from commander.account_effects import AccountEffectJournal
    from commander.account_lifecycle import selected_sessions
    from fastapi import HTTPException
    _,secret,account=native_funds(tmp_path,monkeypatch)
    data=json.loads(config.read_text());data['account_alias']=account.alias;config.write_text(json.dumps(data))
    settings=replace(settings,lifecycle_session_sources=((str(config),hashlib.sha256(config.read_bytes()).hexdigest()),))
    app.state.onboarding.control.handlers=build_account_handlers(settings)
    request=await deletion(ac,alias=account.alias)
    original_id=request['approval_proof']['challenge_id']
    registry_before=(tmp_path/'accounts.json').read_bytes();secret_before=secret.read_bytes()
    from vati.accounts.resource_version import resource_snapshot
    logical_before=resource_snapshot(AccountRegistry(tmp_path/'accounts.json'),account.alias)
    with closing(Ledger(tmp_path/'vati.sqlite')) as led:
        business_before=[e.hash for e in led.iter() if e.kind!=EventKind.ACCOUNT_OPERATION]
    actual_step=UnlinkRecoveryBook.step;changed=[]
    def committed_step(self,*args,**kwargs):
        value=actual_step(self,*args,**kwargs)
        if args[4:]==(boundary,'MAY_BEGIN'):
            value_now=json.loads(config.read_text());value_now['capsules']=['unreviewed-after-commit-v1']
            config.write_text(json.dumps(value_now));changed.append(True)
        return value
    monkeypatch.setattr(UnlinkRecoveryBook,'step',committed_step)
    response=await ac.post('/v1/trading/accounts/action',json=request)
    with pytest.raises(HTTPException) as refused:selected_sessions(settings,account)
    assert refused.value.status_code==409 and changed==[True]
    cold=AccountRegistry(tmp_path/'accounts.json')
    with closing(Ledger(tmp_path/'vati.sqlite')) as led:
        original=AccountEffectJournal(led).status(original_id,'test-device')
        assert led.verify_chain()[0]
        assert [e.hash for e in led.iter() if e.kind!=EventKind.ACCOUNT_OPERATION]==business_before
    observation={'boundary':boundary,'http':response.status_code,'response':response.json(),
        'native_phase':original.phase,'native_result':original.result,
        'registry_unchanged':(tmp_path/'accounts.json').read_bytes()==registry_before,
        'account_present':account.alias in cold.accounts,'lifecycle_phase':cold._lifecycles.get(account.alias,{}).get('phase'),
        'secret_exists':secret.exists(),'secret_matches_original':secret.exists() and secret.read_bytes()==secret_before}
    (tmp_path/'SOURCE_CURRENTNESS_OBSERVATION.json').write_text(json.dumps(observation,indent=2))
    assert response.json().get('effect_state')!='APPLIED',observation
    if boundary=='REGISTRY_REMOVE':
        # Guarded reservation DATA already committed: physical registry bytes
        # changed, but no account removal or credential change is permitted.
        assert original.phase=='UNKNOWN' and original.result is None and observation['account_present'],observation
        assert not observation['registry_unchanged'] and cold._lifecycles[account.alias]['phase']=='DELETING'
        assert resource_snapshot(cold,account.alias)==logical_before and secret.read_bytes()==secret_before
    else:
        assert original.phase=='UNKNOWN' and original.result is None and not observation['account_present'],observation
        assert cold._lifecycles[account.alias]['phase']=='DELETING' and secret.exists(),observation
        if boundary=='CREDENTIAL_OVERWRITE':assert secret.read_bytes()==secret_before
        else:assert secret.read_bytes()!=secret_before and secret.stat().st_size==len(secret_before)
    # Repeating the original cannot resume a stale source or rewrite UNKNOWN.
    before_replay=secret.read_bytes();phase=original.phase;result=original.result
    await ac.post('/v1/trading/accounts/action',json=request)
    assert secret.read_bytes()==before_replay
    with closing(Ledger(tmp_path/'vati.sqlite')) as led:
        replay=AccountEffectJournal(led).status(original_id,'test-device')
        assert replay.phase==phase and replay.result==result

@pytest.mark.asyncio
@pytest.mark.parametrize('window',['plan_commit','registry_may_begin'])
@pytest.mark.parametrize('managed',[False,True])
async def test_actual_pre_registry_crash_child_cannot_drop_original_detachment(client,tmp_path,monkeypatch,window,managed):
    """Actual committed plan/step, genuine child and a fresh alias incarnation."""
    ac,app,settings,config=await configure(client,tmp_path)
    alias='paper_owner';secret=None
    if managed:
        from backend.tests.test_account_unlink_review import native_funds
        _,secret,account=native_funds(tmp_path,monkeypatch);alias=account.alias
        data=json.loads(config.read_text());data['account_alias']=alias;config.write_text(json.dumps(data))
        settings=replace(settings,lifecycle_session_sources=((str(config),hashlib.sha256(config.read_bytes()).hexdigest()),))
        app.state.onboarding.control.handlers=build_account_handlers(settings)
    from commander.account_cleanup import UnlinkRecoveryBook
    from commander.account_effects import AccountEffectJournal
    from vati.accounts.access import entry_fence
    from vati.accounts.registry import AccountRegistryError
    before=AccountRegistry(tmp_path/'accounts.json')
    if not managed:
        with entry_fence(before,before.get(alias)):pass # Healthy sending-mode PAPER source control.
    else:
        assert before.get(alias).mode=='OBSERVE' # Managed retirement fixture is deliberately read-only.
    request=await deletion(ac,alias=alias);identity=request['approval_proof']['challenge_id']
    actual_prepare=UnlinkRecoveryBook.prepare;actual_step=UnlinkRecoveryBook.step;boundary=[]
    with monkeypatch.context() as patch:
        def interrupted_prepare(self,*args,**kwargs):
            value=actual_prepare(self,*args,**kwargs)
            if window=='plan_commit' and args[0].operation_id==identity:
                boundary.append(window);raise OSError('SOURCE lost reply after actual committed plan')
            return value
        def interrupted_step(self,*args,**kwargs):
            value=actual_step(self,*args,**kwargs)
            if window=='registry_may_begin' and args[0]==identity and args[4:]==('REGISTRY_REMOVE','MAY_BEGIN'):
                boundary.append(window);raise OSError('SOURCE lost reply after actual committed registry MAY_BEGIN')
            return value
        patch.setattr(UnlinkRecoveryBook,'prepare',interrupted_prepare);patch.setattr(UnlinkRecoveryBook,'step',interrupted_step)
        response=await ac.post('/v1/trading/accounts/action',json=request)
    assert boundary==[window] and response.json()['effect_state']=='UNKNOWN',response.text
    original_marker=alias in AccountRegistry(tmp_path/'accounts.json')._lifecycles
    status=await ac.get('/v1/trading/accounts/operations/'+identity)
    assert status.status_code==200 and status.json()['result'] is None,status.text
    plan=status.json()['cleanup_recovery']['plan_ref'];assert plan
    if window=='plan_commit':
        # The unchanged sealed owner requires an actual step before a child is
        # eligible. A plan alone must HOLD, never gain a fabricated MAY_BEGIN.
        args={'alias':alias,'variant':'PENDING_CLEANUP','parent_operation_id':identity,
            'plan_ref':plan,'retire_parent_safety_obligation':True}
        refused=await ac.post('/v1/trading/accounts/cleanup/reauth/challenge',json=body(args))
        assert refused.status_code==409 and 'CLEANUP_NATIVE_HOLD' in refused.text,refused.text
        state=await ac.get('/v1/trading/accounts/lifecycle/records/'+alias)
        cold=AccountRegistry(tmp_path/'accounts.json')
        observation={'window':window,'managed':managed,'marker_after_original':original_marker,
            'child_eligibility':'HOLD_NO_ACTUAL_STEP','lifecycle_http':state.status_code,
            'account_present':alias in cold.accounts}
        (tmp_path/'PARTIAL_DETACHMENT_OBSERVATION.json').write_text(json.dumps(observation,indent=2))
        assert original_marker and alias in cold._lifecycles and alias in cold.accounts,observation
        assert state.status_code==200 and state.json()['phase']=='DELETING' and state.json()['native_original_phase']=='UNKNOWN',state.text
        with pytest.raises(AccountRegistryError):
            with entry_fence(cold,cold.get(alias)):pass
        return
    child=await approved(ac,{'alias':alias,'variant':'PENDING_CLEANUP','parent_operation_id':identity,
        'plan_ref':plan,'retire_parent_safety_obligation':True},reauth_family='cleanup')
    result=await ac.post('/v1/trading/accounts/action',json=child)
    assert result.status_code==200 and result.json()['child_state']=='APPLIED',result.text
    assert result.json()['resolution_state']=='QUALIFIED_SEPARATE_FACT'
    if managed:assert not secret.exists()
    after=AccountRegistry(tmp_path/'accounts.json');marker_after_child=alias in after._lifecycles
    state=await ac.get('/v1/trading/accounts/lifecycle/records/'+alias)
    # A new A4-approved record is deliberately not strategy reassignment.
    from backend.tests.test_trading_oauth_scope import act
    reused=await act(ac,'account_upsert',{'alias':alias,'broker':'PAPER','mode':'DEMO_TRADER'})
    assert reused.status_code==200,reused.text
    cold=AccountRegistry(tmp_path/'accounts.json');permitted=False
    try:
        with entry_fence(cold,cold.get(alias)):permitted=True
    except AccountRegistryError:pass
    with closing(Ledger(tmp_path/'vati.sqlite')) as led:
        parent=AccountEffectJournal(led).status(identity,'test-device')
        assert parent.phase=='UNKNOWN' and parent.result is None and led.verify_chain()[0]
    observation={'window':window,'managed':managed,'marker_after_original':original_marker,
        'marker_after_child':marker_after_child,'lifecycle_http':state.status_code,'entry_after_reuse_permitted':permitted,
        'parent_phase':parent.phase,'parent_result':parent.result,'child_phase':result.json()['child_state'],
        'resolution':result.json()['resolution_state'],'marker_after_alias_reuse':alias in cold._lifecycles}
    (tmp_path/'PARTIAL_DETACHMENT_OBSERVATION.json').write_text(json.dumps(observation,indent=2))
    assert original_marker and marker_after_child and alias in cold._lifecycles and not permitted,observation
    assert state.status_code==200 and state.json()['phase']=='PENDING_ARCHIVE',state.text
    assert state.json()['native_original_phase']=='UNKNOWN'

@pytest.mark.asyncio
async def test_actual_reservation_ack_loss_holds_without_plan_or_logical_identity_change(client,tmp_path,monkeypatch):
    ac,app,settings,config=await configure(client,tmp_path)
    from backend.tests.test_account_unlink_review import native_funds
    from commander.account_cleanup import UnlinkRecoveryBook
    from commander.account_effects import AccountEffectJournal
    from commander.account_lifecycle import NativeLifecycle
    from commander.accounts import _file_generation
    from vati.accounts.resource_version import resource_snapshot
    from vati.accounts.access import entry_fence
    from vati.accounts.registry import AccountRegistryError
    _,secret,account=native_funds(tmp_path,monkeypatch)
    data=json.loads(config.read_text());data['account_alias']=account.alias;config.write_text(json.dumps(data))
    settings=replace(settings,lifecycle_session_sources=((str(config),hashlib.sha256(config.read_bytes()).hexdigest()),))
    app.state.onboarding.control.handlers=build_account_handlers(settings)
    request=await deletion(ac,alias=account.alias);identity=request['approval_proof']['challenge_id']
    before=AccountRegistry(tmp_path/'accounts.json');logical_before=resource_snapshot(before,account.alias)
    registry_bytes=(tmp_path/'accounts.json').read_bytes();secret_bytes=secret.read_bytes();credential_identity=_file_generation(secret.stat())
    actual=AccountRegistry.lifecycle_update;plan=UnlinkRecoveryBook.prepare;observed=[];prepared=[]
    with monkeypatch.context() as patch:
        def lost(self,*a,**kw):
            value=actual(self,*a,**kw)
            if account.alias in self.accounts and self._lifecycles.get(account.alias,{}).get('operation_id')==identity:
                observed.append(True);raise OSError('SOURCE lost durable reservation ACK before plan')
            return value
        def prepare(self,*a,**kw):prepared.append(True);return plan(self,*a,**kw)
        patch.setattr(AccountRegistry,'lifecycle_update',lost);patch.setattr(UnlinkRecoveryBook,'prepare',prepare)
        response=await ac.post('/v1/trading/accounts/action',json=request)
    assert observed==[True] and not prepared and response.json()['effect_state']=='UNKNOWN',response.text
    cold=AccountRegistry(tmp_path/'accounts.json');row=cold._lifecycles[account.alias]
    assert cold.get(account.alias)==account and resource_snapshot(cold,account.alias)==logical_before
    assert secret.read_bytes()==secret_bytes and _file_generation(secret.stat())==credential_identity
    assert (tmp_path/'accounts.json').read_bytes()!=registry_bytes and json.loads((tmp_path/'accounts.json').read_text())['schema_version']==2
    assert row['phase']=='DELETING' and row['archive_at_unix']==row['created_at_unix']+row['grace_seconds']
    with closing(Ledger(tmp_path/'vati.sqlite')) as led:
        original=AccountEffectJournal(led).status(identity,'test-device')
        assert original.phase=='UNKNOWN' and original.result is None
    # Even after the bound deadline this is unresolved DATA, not archive/cancel
    # permission or a guessed private plan. Read-only owner observation is safe.
    init=NativeLifecycle.__init__
    def past_deadline(self,*a,**kw):init(self,*a,**{**kw,'clock':lambda:row['archive_at_unix']+1})
    monkeypatch.setattr(NativeLifecycle,'__init__',past_deadline)
    state=await ac.get('/v1/trading/accounts/lifecycle/records/'+account.alias)
    assert state.status_code==200 and state.json()['phase']=='DELETING' and state.json()['native_original_phase']=='UNKNOWN',state.text
    assert state.json()['metadata_hold']=='ORIGINAL_OUTCOME_REQUIRES_RECONCILIATION'
    cancelled=await ac.post('/v1/trading/accounts/lifecycle/reauth/challenge',json=body({'alias':account.alias,'variant':'CANCEL_DELETE',
        'lifecycle_id':identity,'expected_revision':state.json()['revision'],'expected_digest':state.json()['record_digest']}))
    assert cancelled.status_code==409,cancelled.text
    cold=AccountRegistry(tmp_path/'accounts.json');assert cold._lifecycles[account.alias]==row
    assert cold.get(account.alias)==account and resource_snapshot(cold,account.alias)==logical_before
    assert secret.read_bytes()==secret_bytes and _file_generation(secret.stat())==credential_identity
    with pytest.raises(AccountRegistryError):
        with entry_fence(cold,cold.get(account.alias)):pass
    with closing(Ledger(tmp_path/'vati.sqlite')) as led:
        final=AccountEffectJournal(led).status(identity,'test-device')
        assert final.phase=='UNKNOWN' and final.result is None and led.verify_chain()[0]


@pytest.mark.asyncio
async def test_immediate_disconnect_real_two_proofs_paper_metadata_and_original_readback(client,tmp_path):
    ac,app,_,config=await configure(client,tmp_path)
    raw={'alias':'paper_owner','variant':'IMMEDIATE_DISCONNECT'}
    prepare=await ac.post('/v1/trading/accounts/lifecycle/prepare',json=body(raw))
    assert prepare.status_code==200,prepare.text
    assert set(prepare.json()['args'])=={'alias','variant','oauth_discard_digest'}
    approved_body=await approved(ac,prepare.json()['args'])
    response=await ac.post('/v1/trading/accounts/action',json=approved_body)
    assert response.status_code==200,response.text
    result=response.json();assert result['effect_state']=='APPLIED' and result['removed'] is True
    assert result['remote_account_closed'] is False and result['historical_data_retained'] is True
    assert result['retained_remote_funds'] is None and result['credential_cleanup']=='NONE'
    cold=AccountRegistry(tmp_path/'accounts.json');row=cold._lifecycles['paper_owner']
    assert row['phase']=='DISCONNECTED' and row['restore'] is None
    assert row['grace_seconds'] is None and row['archive_at_unix'] is None
    assert row['original_request']['variant']=='IMMEDIATE_DISCONNECT' and 'grace_seconds' not in row['original_request']
    assert row['detached'] is True and 'paper_owner' not in cold.accounts
    assert config.exists() and json.loads(config.read_text())['capsules']==['fx_trend_pullback-v1']
    state=await ac.get('/v1/trading/accounts/lifecycle/records/paper_owner')
    assert state.status_code==200,state.text
    assert state.json()['variant']=='IMMEDIATE_DISCONNECT' and state.json()['phase']=='DISCONNECTED'
    assert state.json()['grace_seconds'] is None and state.json()['archive_at_unix'] is None
    assert (await ac.post('/v1/trading/accounts/action',json=approved_body)).json()==result
    with closing(Ledger(tmp_path/'vati.sqlite')) as ledger:
        from commander.account_effects import AccountEffectJournal
        original=AccountEffectJournal(ledger).status(approved_body['approval_proof']['challenge_id'],'test-device')
        assert original.phase=='APPLIED' and ledger.verify_chain()[0]

@pytest.mark.asyncio
@pytest.mark.parametrize('extra',[{'grace_seconds':None},{'grace_seconds':0},{'grace_seconds':7},{'archive_at_unix':None}])
async def test_immediate_disconnect_strict_no_grace_input(client,tmp_path,extra):
    ac,_,_,_=await configure(client,tmp_path)
    response=await ac.post('/v1/trading/accounts/lifecycle/prepare',json=body({'alias':'paper_owner','variant':'IMMEDIATE_DISCONNECT',**extra}))
    assert response.status_code==422,response.text
    cold=AccountRegistry(tmp_path/'accounts.json');assert 'paper_owner' in cold.accounts and not cold._lifecycles

@pytest.mark.asyncio
async def test_alias_only_one_proof_disconnect_is_typed_refusal(client,tmp_path):
    ac,_,_,_=await configure(client,tmp_path)
    response=await ac.post('/v1/trading/accounts/challenge',json=body({'alias':'paper_owner'}))
    assert response.status_code==422 and 'IMMEDIATE_DISCONNECT' in response.text
    assert 'paper_owner' in AccountRegistry(tmp_path/'accounts.json').accounts

@pytest.mark.asyncio
async def test_same_alias_new_generation_keeps_exact_lifecycle_history_and_old_controls(client,tmp_path,monkeypatch):
    ac,app,_,_=await configure(client,tmp_path)
    first=await deletion(ac,grace=600)
    before=await ac.post('/v1/trading/accounts/action',json=first)
    assert before.status_code==200 and before.json()['effect_state']=='APPLIED',before.text
    old_id=first['approval_proof']['challenge_id']
    old=AccountRegistry(tmp_path/'accounts.json')._lifecycles['paper_owner']
    await paper(ac)
    from backend.tests.test_account_update_review import immediate_challenge
    next_body,_=await immediate_challenge(ac,'paper_owner')
    second=await ac.post('/v1/trading/accounts/action',json=next_body)
    assert second.status_code==200 and second.json()['effect_state']=='APPLIED',second.text
    current=AccountRegistry(tmp_path/'accounts.json')
    assert current._schema_version==3 and current._lifecycle_history[old_id]==old
    assert current._lifecycles['paper_owner']['operation_id']==next_body['approval_proof']['challenge_id']
    assert current._lifecycles['paper_owner']['incarnation']!=old['incarnation']
    historical=await ac.get('/v1/trading/accounts/lifecycle/records/paper_owner/'+old_id)
    assert historical.status_code==200 and historical.json()['operation_id']==old_id,historical.text
    wrong_domain=await ac.get('/v1/trading/accounts/lifecycle/records/paper_owner/'+old_id,
        headers={'X-Van-Account-Control-Domain':'0'*64})
    assert wrong_domain.status_code==409 and 'LIFECYCLE_DOMAIN_CHANGED' in wrong_domain.text
    stale=await ac.post('/v1/trading/accounts/lifecycle/reauth/challenge',json=body({'alias':'paper_owner','variant':'CANCEL_DELETE',
        'lifecycle_id':old_id,'expected_revision':old['revision'],'expected_digest':historical.json()['record_digest']}))
    assert stale.status_code==409 and 'newer account generation' in stale.text
    replay=await ac.post('/v1/trading/accounts/action',json=first)
    assert replay.json()==before.json()
    assert AccountRegistry(tmp_path/'accounts.json')._lifecycle_history[old_id]==old

    latest=current._lifecycles['paper_owner']
    original_init=NativeLifecycle.__init__
    def expired(self,*args,**kwargs):return original_init(self,*args,**kwargs,clock=lambda:old['archive_at_unix']+1)
    monkeypatch.setattr(NativeLifecycle,'__init__',expired)
    archived=await ac.get('/v1/trading/accounts/lifecycle/records/paper_owner/'+old_id)
    assert archived.status_code==200 and archived.json()['phase']=='ARCHIVED',archived.text
    cold=AccountRegistry(tmp_path/'accounts.json')
    assert cold._lifecycles['paper_owner']==latest
    assert cold._lifecycle_history[old_id]['restore'] is None and cold._lifecycle_history[old_id]['session_sources']==[]
    original=await ac.get('/v1/trading/accounts/lifecycle/operations/'+old_id)
    assert original.status_code==200 and original.json()['native']['result']['lifecycle']['phase']=='PENDING_ARCHIVE'


@pytest.mark.asyncio
async def test_original_sealed_restore_metadata_tamper_refuses_before_cancel_observer(client,tmp_path,monkeypatch):
    ac,_,_,_=await configure(client,tmp_path)
    signed=await deletion(ac)
    applied=await ac.post('/v1/trading/accounts/action',json=signed)
    assert applied.status_code==200 and applied.json()['effect_state']=='APPLIED',applied.text
    path=tmp_path/'accounts.json';value=json.loads(path.read_text())
    row=value['account_lifecycles']['paper_owner'];row['restore']['notes']='tampered nonsecret metadata'
    path.write_text(json.dumps(value))
    observed=[]
    def forbidden(*args):observed.append(True);raise AssertionError('unverified restore reached broker observer')
    monkeypatch.setattr(NativeLifecycle,'remote_state',forbidden)
    from vati.core.canonical import canonical_hash
    response=await ac.post('/v1/trading/accounts/lifecycle/reauth/challenge',json=body({'alias':'paper_owner','variant':'CANCEL_DELETE',
        'lifecycle_id':signed['approval_proof']['challenge_id'],'expected_revision':row['revision'],'expected_digest':canonical_hash(row)}))
    assert response.status_code==409 and 'requires reconciliation' in response.text,response.text
    assert not observed and AccountRegistry(path)._lifecycles['paper_owner']['restore']['notes']=='tampered nonsecret metadata'
