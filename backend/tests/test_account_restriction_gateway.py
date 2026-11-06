"""Actual enrolled-device HTTP -> Store -> native PAPER restriction metadata."""
import base64,hashlib,hmac,time
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from backend.tests.test_trading_api import client,_env,DEVICE_KEY,_approval_proof
from backend.tests.test_account_update_review import isolate
from backend.tests.test_account_unlink_review import paper
from van_gateway.trading.accounts import canonical_action
from vati.accounts import AccountRegistry

BASE='/v1/trading/accounts/restrictions'
def body(args):
    issued=int(time.time());action='account_restrict'
    return {'device_id':'test-device','issued_at_unix':issued,'action':action,'args':args,
        'signature':hmac.new(b'test-device-secret',canonical_action('test-device',issued,action,args).encode(),hashlib.sha256).hexdigest()}

async def approved(ac,args):
    if args['variant']!='RESTRICT':
        b=body(args);issued=await ac.post(BASE+'/reauth/challenge',json=b)
        assert issued.status_code==200,issued.text
        proof={'challenge_id':issued.json()['challenge_id'],'algorithm':'ECDSA_P256_SHA256',
            'signature_b64':base64.b64encode(DEVICE_KEY.sign(issued.json()['canonical'].encode(),ec.ECDSA(hashes.SHA256()))).decode()}
        fact=await ac.post(BASE+'/reauth/verify',json=b|{'approval_proof':proof})
        assert fact.status_code==200,fact.text
        args=args|{'reauth_fact_id':fact.json()['reauth_fact_id'],'reauth_fact_digest':fact.json()['fact_digest']}
    b=body(args);issued=await ac.post(BASE+'/challenge',json=b)
    assert issued.status_code==200,issued.text
    return b|{'approval_proof':_approval_proof(issued.json())}

@pytest.mark.asyncio
async def test_generic_onboarding_routes_cannot_issue_or_execute_restriction(client):
    ac, _ = client
    request = body({'alias':'paper_owner','variant':'RESTRICT','reason_code':'OWNER_REQUEST'})
    for route in ['/v1/trading/accounts/challenge','/v1/trading/accounts/action']:
        refused = await ac.post(route, json=request)
        assert refused.status_code == 422, refused.text
        assert refused.json()['detail']['code'] == 'RESTRICTION_PURPOSE_ROUTE_REQUIRED'


@pytest.mark.asyncio
async def test_actual_paper_restriction_reauth_readonly_never_grants_entry_or_mode(client,tmp_path,monkeypatch):
    ac,app=client;await paper(ac)
    # isolate replaces the native settings after app construction.
    app.state.account_restriction.bind_local_verifiers()
    original=AccountRegistry(tmp_path/'accounts.json').get('paper_owner')
    args={'alias':'paper_owner','variant':'RESTRICT','reason_code':'OWNER_REQUEST'}
    first=await approved(ac,args);result=await ac.post(BASE+'/action',json=first)
    assert result.status_code==200,result.text
    assert result.json()['effect_state']=='APPLIED',result.text
    for variant in ['BEGIN_REAUTH','COMPLETE_REAUTH']:
        current=await ac.get(BASE+'/records/paper_owner');assert current.status_code==200,current.text
        row=current.json()['restriction']
        args={'alias':'paper_owner','variant':variant,'restriction_id':row['restriction_id'],
            'expected_revision':row['revision'],'expected_digest':row['record_digest']}
        b=await approved(ac,args);result=await ac.post(BASE+'/action',json=b)
        assert result.status_code==200,result.text
        assert result.json()['effect_state']=='APPLIED',result.text
    row=result.json()['result']['restriction']
    assert row['phase']=='LINKED_READ_ONLY' and row['revision']==3
    assert row['device_id']=='test-device' and row['reason']=='Owner requested a restriction.'
    account=AccountRegistry(tmp_path/'accounts.json').get('paper_owner')
    assert account.enabled is False and account.mode==original.mode and account.mandate_ref==original.mandate_ref
    assert result.json()['result']['entry_permitted'] is False
    from backend.tests.test_trading_oauth_scope import act
    enabled=await act(ac,'account_upsert',{'alias':'paper_owner','enabled':True},expected_challenge_status=409)
    assert enabled.json()['detail']['code']=='RESTRICTION_ENTRY_ACTIVATION_REQUIRES_EXISTING_GOVERNED_CONTROL'
    assert AccountRegistry(tmp_path/'accounts.json').get('paper_owner').enabled is False

    replay=await ac.post(BASE+'/action',json=b);assert replay.json()==result.json()
    old=await ac.post(BASE+'/action',json=first)
    assert old.status_code==200 and old.json()['result']['restriction']['phase']=='RESTRICTED'
    # Independently validate cached native evidence, even when its public hash
    # has been consistently recomputed by a malformed native response.
    from copy import deepcopy
    from vati.core.canonical import canonical_hash
    native=app.state.onboarding.control.operation
    for change in [{'broker':'DERIV'},{'source_nonce_ref':'a'*64}]:
        def malformed(*args,**kwargs):
            receipt=deepcopy(native(*args,**kwargs));proof=receipt['result']['native_identity'];proof.update(change)
            proof['observation_ref']=canonical_hash({k:v for k,v in proof.items() if k!='observation_ref'})
            return receipt
        monkeypatch.setattr(app.state.onboarding.control,'operation',malformed)
        read=await ac.get(BASE+'/operations/'+b['approval_proof']['challenge_id'])
        assert read.status_code==200 and read.json()['effect_state']=='UNKNOWN' and read.json()['result'] is None,read.text
    monkeypatch.setattr(app.state.onboarding.control,'operation',native)


@pytest.mark.asyncio
@pytest.mark.parametrize('lost_final',[False,True])
async def test_actual_unknown_parent_unknown_metadata_child_selected_ancestor_recovery(client,tmp_path,monkeypatch,lost_final):
    from commander.account_effects import AccountEffectJournal
    from vati.core import Ledger
    ac,app=client;await paper(ac);app.state.account_restriction.bind_local_verifiers()
    p=await approved(ac,{'alias':'paper_owner','variant':'RESTRICT','reason_code':'OWNER_REQUEST'})
    pid=p['approval_proof']['challenge_id'];complete=AccountEffectJournal.complete;lost_ids={pid}
    def lost_completion(journal,claim,result,**kwargs):
        if claim.intent.operation_id in lost_ids:raise RuntimeError('controlled metadata completion acknowledgement loss')
        return complete(journal,claim,result,**kwargs)
    monkeypatch.setattr(AccountEffectJournal,'complete',lost_completion)
    parent=await ac.post(BASE+'/action',json=p)
    assert parent.status_code==409 and parent.json()['effect_state']=='UNKNOWN' and parent.json()['result'] is None,parent.text
    row=(await ac.get(BASE+'/records/paper_owner')).json()['restriction']
    cargs={'alias':'paper_owner','variant':'RECONCILE_DATA','parent_operation_id':pid,'restriction_id':row['restriction_id'],
        'expected_revision':row['revision'],'expected_digest':row['record_digest']}
    c=await approved(ac,cargs);cid=c['approval_proof']['challenge_id']
    append=AccountEffectJournal.append_restriction_resolution
    def interrupted(journal,claim,*args,**kwargs):
        if claim.intent.operation_id==cid:raise RuntimeError('controlled pre-technical metadata interruption')
        return append(journal,claim,*args,**kwargs)
    monkeypatch.setattr(AccountEffectJournal,'append_restriction_resolution',interrupted)
    child=await ac.post(BASE+'/action',json=c)
    assert child.status_code==409 and child.json()['effect_state']=='UNKNOWN' and child.json()['result'] is None,child.text
    g=await approved(ac,cargs|{'parent_operation_id':cid});gid=g['approval_proof']['challenge_id']
    if lost_final:lost_ids.add(gid)
    result=await ac.post(BASE+'/action',json=g)
    assert result.status_code==(409 if lost_final else 200),result.text
    assert result.json()['effect_state']==('UNKNOWN' if lost_final else 'APPLIED'),result.text
    if lost_final:
        assert result.json()['result'] is None
        proof=result.json()['data_resolution']
    else:proof=result.json()['result']['data_resolution']
    assert proof['resolution_child_operation_id']==gid
    assert proof['selected_parent_operation_id']==cid and proof['anchor_operation_id']==pid
    assert proof['resolved_operations']==sorted([pid,cid])
    for operation in [pid,cid]+([gid] if lost_final else []):
        read=await ac.get(BASE+'/operations/'+operation)
        assert read.status_code==200 and read.json()['effect_state']=='UNKNOWN' and read.json()['result'] is None,read.text
        assert read.json()['data_resolution']==proof
    cold=Ledger(str(tmp_path/'vati.sqlite'))
    try:
        journal=AccountEffectJournal(cold)
        assert journal.status(pid,'test-device').phase=='UNKNOWN' and journal.status(pid,'test-device').result is None
        assert journal.status(cid,'test-device').phase=='UNKNOWN' and journal.status(cid,'test-device').result is None
        assert journal.restriction_resolution(pid,'test-device')==proof
    finally:cold.close()
    replay=await ac.post(BASE+'/action',json=g);assert replay.json()==result.json()

@pytest.mark.asyncio
@pytest.mark.parametrize('mode',['ADVISOR','SHADOW_TRADER'])
async def test_existing_admitted_mode_can_be_restricted_without_mode_rewrite(client,tmp_path,mode):
    from dataclasses import replace
    ac,app=client;await paper(ac);app.state.account_restriction.bind_local_verifiers()
    registry=AccountRegistry(tmp_path/'accounts.json')
    # Existing admitted-account fixture; this primitive seeds no new-account
    # or mode-promotion authority in production.
    registry.replace(replace(registry.get('paper_owner'),mode=mode))
    b=await approved(ac,{'alias':'paper_owner','variant':'RESTRICT','reason_code':'KILL_SWITCH'})
    result=await ac.post(BASE+'/action',json=b)
    assert result.status_code==200 and result.json()['effect_state']=='APPLIED',result.text
    assert AccountRegistry(tmp_path/'accounts.json').get('paper_owner').mode==mode
    assert result.json()['result']['restriction']['reason']=='Owner activated the entry restriction.'

@pytest.mark.asyncio
async def test_refused_metadata_child_does_not_block_fresh_parent_recovery(client,tmp_path,monkeypatch):
    from commander.account_effects import AccountEffectJournal
    from fastapi import HTTPException
    ac,app=client;await paper(ac);app.state.account_restriction.bind_local_verifiers()
    p=await approved(ac,{'alias':'paper_owner','variant':'RESTRICT','reason_code':'OWNER_REQUEST'})
    pid=p['approval_proof']['challenge_id'];complete=AccountEffectJournal.complete
    def lose(journal,claim,result,**kwargs):
        if claim.intent.operation_id==pid:raise RuntimeError('controlled metadata completion loss')
        return complete(journal,claim,result,**kwargs)
    monkeypatch.setattr(AccountEffectJournal,'complete',lose)
    response=await ac.post(BASE+'/action',json=p)
    assert response.status_code==409 and response.json()['effect_state']=='UNKNOWN',response.text
    row=(await ac.get(BASE+'/records/paper_owner')).json()['restriction']
    args={'alias':'paper_owner','variant':'RECONCILE_DATA','parent_operation_id':pid,'restriction_id':row['restriction_id'],
        'expected_revision':row['revision'],'expected_digest':row['record_digest']}
    c=await approved(ac,args);cid=c['approval_proof']['challenge_id'];append=AccountEffectJournal.append_restriction_resolution
    def refuse(journal,claim,*args,**kwargs):
        if claim.intent.operation_id==cid:raise HTTPException(409,{'code':'CONTROLLED_PRE_EFFECT_METADATA_REFUSAL'})
        return append(journal,claim,*args,**kwargs)
    monkeypatch.setattr(AccountEffectJournal,'append_restriction_resolution',refuse)
    child=await ac.post(BASE+'/action',json=c)
    assert child.status_code==409 and child.json()['effect_state']=='REFUSED',child.text
    g=await approved(ac,args);result=await ac.post(BASE+'/action',json=g)
    assert result.status_code==200 and result.json()['effect_state']=='APPLIED',result.text
    proof=result.json()['result']['data_resolution']
    assert proof['resolved_operations']==[pid] and proof['anchor_operation_id']==pid
    native=app.state.onboarding.control.run
    def transplant(command,values):
        answer=native(command,values)
        if command=='account_review' and values.get('action')=='account_restriction_resolution':
            from copy import deepcopy
            answer=deepcopy(answer);answer['resolution']['resolved_operations']=['unrelated_operation_00000001']
            answer['resolution']['selected_parent_operation_id']='unrelated_operation_00000001'
            answer['resolution']['resolution_child_operation_id']='unrelated_child_operation_00000001'
        return answer
    monkeypatch.setattr(app.state.onboarding.control,'run',transplant)
    read=await ac.get(BASE+'/operations/'+pid)
    assert read.status_code==200 and read.json()['effect_state']=='UNKNOWN' and read.json()['result'] is None,read.text
    assert read.json()['data_resolution'] is None

@pytest.mark.asyncio
async def test_actual_admission_cannot_be_reused_as_direct_local_or_effect_authority(client,tmp_path,monkeypatch):
    from fastapi import HTTPException
    from commander.account_restrictions import NativeRestriction
    from commander.accounts import build_account_handlers
    from vati.core import Ledger
    from vati.accounts.resource_version import resource_snapshot
    ac,app=client;await paper(ac);service=app.state.account_restriction;service.bind_local_verifiers()
    captured=[];control=app.state.onboarding.control;native=control.run
    def capture(command,args):
        if command=='account_restrict':captured.append(args)
        return native(command,args)
    monkeypatch.setattr(control,'run',capture)
    request=await approved(ac,{'alias':'paper_owner','variant':'RESTRICT','reason_code':'CREDENTIALS_EXPIRED'})
    response=await ac.post(BASE+'/action',json=request)
    assert response.status_code==200 and response.json()['effect_state']=='APPLIED',response.text
    assert len(captured)==1
    prior=(tmp_path/'accounts.json').read_bytes();ledger=Ledger(str(tmp_path/'vati.sqlite'))
    try:
        events=list(ledger.iter());last=events[-1].hash
        with pytest.raises(HTTPException) as denied:native('account_restrict',captured[0])
        assert denied.value.status_code==403
        effect=NativeRestriction(control.settings,ledger,lambda _:control.domain(),
            lambda alias:resource_snapshot(AccountRegistry(tmp_path/'accounts.json'),alias)['resource_version'])
        with pytest.raises(HTTPException) as denied:
            effect._apply(captured[0],captured[0]['_restriction_admission'],captured[0]['_restriction_admission']['native_review'])
        assert denied.value.status_code==403
        assert (tmp_path/'accounts.json').read_bytes()==prior and list(ledger.iter())[-1].hash==last
    finally:ledger.close()
    legacy=await ac.post('/v1/trading/accounts/action',json=request)
    assert legacy.status_code==422 and legacy.json()['detail']['code']=='RESTRICTION_PURPOSE_ROUTE_REQUIRED'

@pytest.mark.asyncio
async def test_unknown_before_registry_effect_resolves_only_preimage_then_allows_fresh_restriction(client,tmp_path,monkeypatch):
    ac,app=client;await paper(ac);app.state.account_restriction.bind_local_verifiers()
    p=await approved(ac,{'alias':'paper_owner','variant':'RESTRICT','reason_code':'BROKER_DISABLED'})
    pid=p['approval_proof']['challenge_id'];replace=AccountRegistry.restriction_update
    def interrupted(registry,*args,**kwargs):raise RuntimeError('controlled metadata interruption before registry effect')
    monkeypatch.setattr(AccountRegistry,'restriction_update',interrupted)
    prior=(tmp_path/'accounts.json').read_bytes();response=await ac.post(BASE+'/action',json=p)
    assert response.status_code==409 and response.json()['effect_state']=='UNKNOWN' and response.json()['result'] is None,response.text
    assert (tmp_path/'accounts.json').read_bytes()==prior
    monkeypatch.setattr(AccountRegistry,'restriction_update',replace)
    args={'alias':'paper_owner','variant':'RECONCILE_DATA','parent_operation_id':pid,'restriction_id':pid,'expected_revision':0}
    g=await approved(ac,args);result=await ac.post(BASE+'/action',json=g)
    assert result.status_code==200 and result.json()['effect_state']=='APPLIED',result.text
    assert result.json()['result']['restriction'] is None
    proof=result.json()['result']['data_resolution'];assert proof['outcome']=='CURRENT_PREIMAGE_OBSERVED' and proof['revision']==0
    assert (tmp_path/'accounts.json').read_bytes()==prior
    fresh=await approved(ac,{'alias':'paper_owner','variant':'RESTRICT','reason_code':'VERIFICATION_FAILED'})
    result=await ac.post(BASE+'/action',json=fresh)
    assert result.status_code==200 and result.json()['effect_state']=='APPLIED',result.text
    assert result.json()['result']['restriction']['restriction_id']==fresh['approval_proof']['challenge_id']!=pid

@pytest.mark.asyncio
async def test_recovery_requires_distinct_current_reauth_and_exact_state_before_a4(client,tmp_path):
    ac,app=client;await paper(ac);app.state.account_restriction.bind_local_verifiers()
    p=await approved(ac,{'alias':'paper_owner','variant':'RESTRICT','reason_code':'OWNER_REQUEST'})
    result=await ac.post(BASE+'/action',json=p);assert result.status_code==200,result.text
    row=result.json()['result']['restriction'];prior=(tmp_path/'accounts.json').read_bytes()
    args={'alias':'paper_owner','variant':'BEGIN_REAUTH','restriction_id':row['restriction_id'],
        'expected_revision':row['revision'],'expected_digest':row['record_digest']}
    one=await ac.post(BASE+'/challenge',json=body(args))
    assert one.status_code==422 and one.json()['detail']['code']=='RESTRICTION_REAUTH_INPUT_MISMATCH',one.text
    invalid=await ac.post(BASE+'/reauth/challenge',json=body(args|{'expected_revision':row['revision']+1}))
    assert invalid.status_code==409 and invalid.json()['detail']['code']=='RESTRICTION_REVIEW_CHANGED',invalid.text
    assert (tmp_path/'accounts.json').read_bytes()==prior
    unauth=await ac.get(BASE+'/records/paper_owner',headers={'X-Van-Device-Id':'foreign-device','X-Van-Device-Token':'invalid'})
    assert unauth.status_code in {401,403}
    assert (tmp_path/'accounts.json').read_bytes()==prior

@pytest.mark.asyncio
@pytest.mark.parametrize('fault',['revoked','expired'])
async def test_actual_current_store_and_expiry_rechecked_at_final_metadata_writer(client,tmp_path,monkeypatch,fault):
    import asyncio
    from commander.account_restrictions import NativeRestriction
    ac,app=client;await paper(ac);app.state.account_restriction.bind_local_verifiers()
    b=await approved(ac,{'alias':'paper_owner','variant':'RESTRICT','reason_code':'OWNER_REQUEST'})
    before=(tmp_path/'accounts.json').read_bytes();loop=asyncio.get_running_loop();injected=[];instances=[];expired={'value':False}
    initial=NativeRestriction.__init__
    def observe_instance(self,*args,**kwargs):
        initial(self,*args,**kwargs);instances.append(self)
        self.clock=lambda:int(time.time()) if not expired['value'] else int(time.time())+10000
    monkeypatch.setattr(NativeRestriction,'__init__',observe_instance)
    update=AccountRegistry.restriction_update
    def final_writer(registry,alias,change,*,before_replace=None):
        def boundary():
            injected.append(True)
            if fault=='revoked':
                future=asyncio.run_coroutine_threadsafe(app.state.store.execute(
                    "UPDATE devices SET revoked_at_unix=? WHERE device_id='test-device'",(int(time.time()),)),loop)
                future.result(5)
            else:expired['value']=True
            before_replace()
        return update(registry,alias,change,before_replace=boundary)
    monkeypatch.setattr(AccountRegistry,'restriction_update',final_writer)
    response=await ac.post(BASE+'/action',json=b)
    assert injected==[True] and instances,response.text
    assert response.status_code==409 and response.json()['effect_state']=='REFUSED',response.text
    assert response.json()['result']['status_code']==403
    assert (tmp_path/'accounts.json').read_bytes()==before and not AccountRegistry(tmp_path/'accounts.json')._restrictions
