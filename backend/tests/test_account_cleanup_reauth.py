"""Real enrolled ECDSA/SQL purpose facts; native context here is a SOURCE fixture."""
import asyncio
import base64
from contextlib import asynccontextmanager
import json
import time

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from backend.tests.test_trading_api import client,_env,DEVICE_KEY
from van_gateway.approval.service import OwnerApprovalService,OwnerApprovalError
from van_gateway.approval.account_reauth import AccountReauthentication,ReauthError,EPHEMERAL,ADMISSIONS,USED,ACTION


def sign(canonical):return base64.b64encode(DEVICE_KEY.sign(canonical.encode(),ec.ECDSA(hashes.SHA256()))).decode()


async def setup(client):
    _,app=client
    row=await app.state.store.fetchone("SELECT access_token_hash FROM devices WHERE device_id='test-device'")
    who={'owner_id':'owner','device_id':'test-device','access_token_hash':row['access_token_hash']}
    async def authorize(db,caller):
        row=await (await db.execute('SELECT access_token_hash,public_key_pem,revoked_at_unix FROM devices WHERE device_id=?',(caller['device_id'],))).fetchone()
        if caller['owner_id']!='owner' or not row or row['revoked_at_unix'] is not None or row['access_token_hash']!=caller['access_token_hash']:
            raise ReauthError('CURRENT_OWNER_REFUSED',403)
        return __import__('hashlib').sha256(row['public_key_pem'].encode()).hexdigest()
    service=AccountReauthentication(app.state.store,authorize)
    context={'alias':'source_owner','parent_operation_id':'original_parent_operation_0001','plan_ref':'1'*64,
        'account_control_domain':'2'*64,'original_device_id':'test-device','review_digest':'3'*64,'resource_version':'4'*64,
        'remaining_steps':['CREDENTIAL_OVERWRITE','CREDENTIAL_UNLINK'],'retire_parent_safety_obligation':True}
    return app,service,who,context


async def factor(service,who,context):
    issued=await service.issue(who,context)
    fact=await service.verify(who,context,issued['challenge_id'],sign(issued['canonical']))
    return issued,fact


async def permission(service,who,context,fact):
    text='Explicit pending local cleanup and specific old safety-obligation retirement '+fact['fact_digest']
    parameters={'native_review':context,'reauth_fact_digest':fact['fact_digest']}
    challenge=await service.approvals.issue(device_id=who['device_id'],source_command_id='account:account_remove',
        turn_id=None,action_id=ACTION,text=text,project_id=None,parameters=parameters,
        _expiry_cap=fact['expires_at_unix'])
    return {'challenge_id':challenge.challenge_id,'signature_b64':sign(challenge.canonical),'text':text,'parameters':parameters,
            'current_request_deadline':int(time.time())+300}


@pytest.mark.asyncio
async def test_two_distinct_actual_proofs_one_atomic_admission_and_original_replay(client):
    app,service,who,context=await setup(client)
    issued,fact=await factor(service,who,context)
    assert issued['execution_authority'] is fact['execution_authority'] is False
    proof=await permission(service,who,context,fact)
    assert proof['challenge_id']!=issued['challenge_id']
    first,winner=await service.admit(who,context,fact['reauth_fact_id'],**proof)
    assert winner and first['state']=='ADMITTED_NOT_NATIVE_COMPLETION'
    replay,new=await service.admit(who,context,fact['reauth_fact_id'],**proof)
    assert not new and replay==first and first['expires_at_unix']<=fact['expires_at_unix']
    assert not await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(EPHEMERAL+'fact:'+fact['reauth_fact_id'],))
    assert not await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(service.approvals.PREFIX+proof['challenge_id'],))
    assert await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(USED+fact['reauth_fact_id'],))


@pytest.mark.asyncio
async def test_rollback_after_two_consumptions_restores_both_without_partial_child(client,monkeypatch):
    app,service,who,context=await setup(client);_,fact=await factor(service,who,context);proof=await permission(service,who,context,fact)
    connection=app.state.store.connection
    @asynccontextmanager
    async def fail():
        async with connection() as db:
            execute=db.execute
            async def injected(sql,params=()):
                if sql.startswith('INSERT INTO runtime_meta') and params and str(params[0]).startswith(ADMISSIONS):raise OSError('SOURCE fixture commit-path failure')
                return await execute(sql,params)
            db.execute=injected
            yield db
    with monkeypatch.context() as patch:
        patch.setattr(app.state.store,'connection',fail)
        with pytest.raises(OSError):await service.admit(who,context,fact['reauth_fact_id'],**proof)
    assert await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(EPHEMERAL+'fact:'+fact['reauth_fact_id'],))
    assert await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(service.approvals.PREFIX+proof['challenge_id'],))
    assert not await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(USED+fact['reauth_fact_id'],))
    assert (await service.admit(who,context,fact['reauth_fact_id'],**proof))[1]


@pytest.mark.asyncio
async def test_distinct_children_cannot_consume_same_purpose_fact_twice(client):
    _,service,who,context=await setup(client);_,fact=await factor(service,who,context)
    proofs=await asyncio.gather(permission(service,who,context,fact),permission(service,who,context,fact))
    results=await asyncio.gather(*(service.admit(who,context,fact['reauth_fact_id'],**p) for p in proofs),return_exceptions=True)
    assert sum(isinstance(r,tuple) and r[1] for r in results)==1
    assert any(isinstance(r,ReauthError) and r.code=='CLEANUP_REAUTH_MISSING_OR_SPENT' for r in results)


@pytest.mark.asyncio
async def test_hard_purpose_lockout_survives_restart_and_valid_proof_cannot_bypass(client):
    app,service,who,context=await setup(client);issued=await service.issue(who,context)
    for number in range(5):
        with pytest.raises(ReauthError) as refused:await service.verify(who,context,issued['challenge_id'],base64.b64encode(b'bad-proof').decode())
        assert refused.value.status==(429 if number==4 else 403)
    replacement=AccountReauthentication(app.state.store,service.authorize)
    with pytest.raises(ReauthError) as valid:await replacement.verify(who,context,issued['challenge_id'],sign(issued['canonical']))
    assert valid.value.status==429 and 0<valid.value.retry_after<=900
    original_lock=valid.value.locked_until
    # A different parent/child nonce cannot rotate the stable domain/purpose subject.
    with pytest.raises(ReauthError) as again:await replacement.issue(who,context|{'review_digest':'5'*64})
    assert again.value.locked_until==original_lock
    assert await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(service.approvals.PREFIX+issued['challenge_id'],))


@pytest.mark.asyncio
async def test_expiry_wrong_purpose_and_unavailable_owner_do_not_count_auth_failures(client):
    app,service,who,context=await setup(client);issued=await service.issue(who,context)
    for selected in (context|{'review_digest':'5'*64},context|{'parent_operation_id':'different_parent_operation_0001'}):
        with pytest.raises(ReauthError):await service.verify(who,selected,issued['challenge_id'],sign(issued['canonical']))
    with pytest.raises(ReauthError):await service.issue(who|{'access_token_hash':'changed'},context)
    assert not await app.state.store.fetchall('SELECT key FROM runtime_meta WHERE key GLOB ?',(EPHEMERAL+'throttle:*',))
    assert await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(service.approvals.PREFIX+issued['challenge_id'],))


@pytest.mark.asyncio
async def test_new_hard_purpose_does_not_change_global_soft_approval_semantics(client):
    _,service,who,context=await setup(client);issued=await service.issue(who,context)
    for _ in range(5):
        with pytest.raises(ReauthError):await service.verify(who,context,issued['challenge_id'],'YmFk')
    # Ordinary approvals remain owned by the existing service, without this new lock.
    ordinary_owner=OwnerApprovalService(service.store)
    ordinary=await ordinary_owner.issue(device_id=who['device_id'],source_command_id='ordinary',turn_id=None,
        action_id='ordinary-owner-action',text='existing action',project_id=None)
    result=await ordinary_owner.verify_and_consume(challenge_id=ordinary.challenge_id,source_command_id='ordinary',
        signature_b64=sign(ordinary.canonical),device_id=who['device_id'],turn_id=None,action_id='ordinary-owner-action',
        text='existing action',project_id=None)
    assert result['operation_id']==ordinary.challenge_id


@pytest.mark.asyncio
async def test_scoped_seven_day_raw_retention_preserves_active_corrupt_and_durable_original_refs(client,monkeypatch):
    from van_gateway.approval.account_reauth import prune_ephemeral
    app,service,who,context=await setup(client)
    now=int(time.time());old=now-9*86400
    from types import SimpleNamespace
    import van_gateway.approval.service as approval_module
    service.clock=lambda:old
    monkeypatch.setattr(approval_module,'time',SimpleNamespace(time=lambda:old))
    issued,fact=await factor(service,who,context)
    unspent=await service.issue(who,context)
    rows={EPHEMERAL+'fact:malformed':{'created_at_unix':old,'expires_at_unix':old+60},
          EPHEMERAL+'fact:active':{'created_at_unix':old,'expires_at_unix':now+60},
          EPHEMERAL+'throttle:active':{'failures':[],'locked_until':now+900},
          EPHEMERAL+'throttle:expired':{'failures':[old],'locked_until':old+900},
          USED+'original_used_reference_0001':{'parent_operation_id':context['parent_operation_id']},
          ADMISSIONS+'original_child_reference_0001':{'parent_operation_id':context['parent_operation_id']},
          'unrelated_owner_record':{'created_at_unix':old,'expires_at_unix':old+60}}
    for key,value in rows.items():
        await app.state.store.execute('INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?)',(key,json.dumps(value),old*1000))
    async with app.state.store.connection() as db:
        await db.execute('BEGIN IMMEDIATE')
        assert await prune_ephemeral(db,now*1000)==4  # expired fact, challenge, two expired counters
        await db.commit()
    assert not await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(EPHEMERAL+'fact:'+fact['reauth_fact_id'],))
    assert not await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(service.approvals.PREFIX+unspent['challenge_id'],))
    for key in rows:
        assert bool(await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(key,)))==(key!=EPHEMERAL+'throttle:expired')
    service.clock=lambda:now
    monkeypatch.setattr(approval_module,'time',SimpleNamespace(time=lambda:now))
    async with app.state.store.connection() as db:
        await db.execute('BEGIN')
        try:
            actor=await service.current_actor(db,who)
            with pytest.raises(ReauthError):await service.require_fact(db,who,context,fact['reauth_fact_id'],actor)
        finally:await db.rollback()


@pytest.mark.asyncio
@pytest.mark.parametrize('change',['expiry','revocation','approval_key'])
async def test_queued_atomic_admission_rereads_current_owner_key_and_deadline(client,change):
    app,service,who,context=await setup(client);_,fact=await factor(service,who,context)
    proof=await permission(service,who,context,fact)
    counter_before=[dict(row) for row in await app.state.store.fetchall('SELECT key,value FROM runtime_meta WHERE key GLOB ? ORDER BY key',(EPHEMERAL+'throttle:*',))]
    async with app.state.store.connection() as db:
        await db.execute('BEGIN IMMEDIATE')
        waiter=asyncio.create_task(service.admit(who,context,fact['reauth_fact_id'],**proof))
        await asyncio.sleep(0)
        if change=='expiry':
            service.clock=lambda:fact['expires_at_unix']
        elif change=='revocation':
            await db.execute("UPDATE devices SET revoked_at_unix=? WHERE device_id='test-device'",(int(time.time()),))
        else:
            from cryptography.hazmat.primitives import serialization
            replacement=ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
            await db.execute("UPDATE devices SET public_key_pem=? WHERE device_id='test-device'",(replacement,))
        await db.commit()
    with pytest.raises(ReauthError):await waiter
    assert not await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(ADMISSIONS+proof['challenge_id'],))
    assert not await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(USED+fact['reauth_fact_id'],))
    assert await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(EPHEMERAL+'fact:'+fact['reauth_fact_id'],))
    assert await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(service.approvals.PREFIX+proof['challenge_id'],))
    assert [dict(row) for row in await app.state.store.fetchall('SELECT key,value FROM runtime_meta WHERE key GLOB ? ORDER BY key',(EPHEMERAL+'throttle:*',))]==counter_before
