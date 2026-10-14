"""Two owner clients, one provider ledger; all examples are explicitly fixture evidence."""
import asyncio
import base64
import json
import time
from types import SimpleNamespace
import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from fastapi import FastAPI, Request
from httpx import AsyncClient, ASGITransport
from van_gateway.storage.db import Store
from van_gateway.muse.models import Action, MuseError, Outcome, Snapshot, digest, canonical
from van_gateway.muse.service import MuseService
from van_gateway.muse.api import build_muse_router
from van_gateway.muse.security import verify_site, signer

NOW = 1791810000000


def snapshot(seq=1, **changes):
    data = dict(schema_version=1, producer_id="fixture-browser", sequence=seq, observed_at_ms=NOW,
                health="GREEN",watchdog="GREEN",complete=True,sessions=[dict(
                    session_id="session-fixture",thread_id="thread-fixture",task_id="task-fixture",project_id="van",
                    scope_binding_sha256="a"*64,control_generation=3,revision=1,title="Fixture task",state="WAITING_OWNER",
                    current_job_only=True,can_send=True,messages=[dict(id="message-1",role="assistant",text="Fixture response")],
                    approvals=[dict(id="approval-fixture",revision=1,action_fingerprint="b"*64,element_ref="element-fixture",
                                    description="Fixture permission only",allowed_actions=["ALLOW_ONCE","DENY"],action_class="A2",expires_at_epoch_ms=NOW+60000)]
                )])
    data.update(changes)
    return Snapshot.model_validate(data)


def action(**changes):
    d=dict(action="DECIDE_APPROVAL",idempotency_key="fixture-request-1",session_id="session-fixture",thread_id="thread-fixture",
           task_id="task-fixture",project_id="van",scope_binding_sha256="a"*64,control_generation=3,
           expected_revision=1,approval_id="approval-fixture",action_fingerprint="b"*64,choice="ALLOW_ONCE")
    d.update(changes)
    return Action.model_validate(d)


@pytest_asyncio.fixture
async def broker(tmp_path):
    store=Store(str(tmp_path/'muse.db'));await store.migrate()
    service=MuseService(store,producer_id="fixture-browser",now=lambda:NOW,classification_policy=lambda prompt:prompt.action_class)
    await service.ingest(snapshot())
    return service


@pytest.mark.asyncio
async def test_migration_keeps_existing_event_sequence(tmp_path, monkeypatch):
    import van_gateway.storage.db as db_module
    store=Store(str(tmp_path/'upgrade.db'))
    current_version=db_module.SCHEMA_VERSION
    monkeypatch.setattr(db_module,'SCHEMA_VERSION',31)
    await store.migrate()
    service=MuseService(store,producer_id="fixture-browser",now=lambda:NOW,
        classification_policy=lambda prompt:prompt.action_class)
    await service.ingest(snapshot())
    before=(await service.overview())['event_cursor']
    assert before>0
    monkeypatch.setattr(db_module,'SCHEMA_VERSION',current_version)
    await store.migrate()
    assert (await store.fetchone("SELECT version FROM schema_migrations WHERE version=31"))['version']==31
    assert (await store.fetchone("SELECT MAX(version) AS v FROM schema_migrations"))['v']==current_version
    assert (await service.overview())['event_cursor']==before
    await service.enqueue(action(),'device:owner')
    assert (await service.overview())['event_cursor']>before


@pytest.mark.asyncio
async def test_cross_surface_decision_is_atomic(broker):
    async def submit(principal, key):
        try:return await broker.enqueue(action(idempotency_key=key),principal)
        except MuseError as exc:return exc.code
    outcomes=await asyncio.gather(submit('device:owner','native-attempt'),submit('site:owner','site-attempt'))
    assert sum(isinstance(x,dict) for x in outcomes)==1
    assert 'approval_already_handled_or_unknown' in outcomes
    assert (await broker.overview())['approvals'][0]['state']=='DISPATCHED'
    assert len(await broker.claim())==1
    assert await broker.claim()==[]


@pytest.mark.asyncio
async def test_same_request_returns_one_receipt(broker):
    first=await broker.enqueue(action(),'device:owner')
    second=await broker.enqueue(action(),'device:owner')
    assert first==second
    with pytest.raises(MuseError,match='idempotency_conflict'):
        await broker.enqueue(action(choice='DENY'),'device:owner')


@pytest.mark.asyncio
@pytest.mark.parametrize('change,code',[
 ({'project_id':'other'},'session_scope_mismatch'),
 ({'thread_id':'other'},'session_scope_mismatch'),
 ({'task_id':'other'},'session_scope_mismatch'),
 ({'control_generation':4},'session_scope_mismatch'),
 ({'action_fingerprint':'c'*64},'approval_changed'),
 ({'expected_revision':2},'approval_changed'),
])
async def test_stale_and_cross_project_refused(broker,change,code):
    with pytest.raises(MuseError,match=code):await broker.enqueue(action(**change),'device:owner')
    assert await broker.claim()==[]


@pytest.mark.asyncio
async def test_source_replay_cannot_make_old_data_fresh(broker):
    assert (await broker.ingest(snapshot()))['replayed']
    with pytest.raises(MuseError,match='source_sequence_conflict'):
        await broker.ingest(snapshot(health='DEGRADED'))
    broker.now=lambda:NOW+90001
    with pytest.raises(MuseError,match='source_stale'):await broker.enqueue(action(),'device:owner')
    assert (await broker.overview())['relay']['state']=='stale'


@pytest.mark.asyncio
async def test_incomplete_source_never_enables_controls(broker):
    await broker.ingest(snapshot(2,complete=False))
    assert not (await broker.overview())['capabilities']['approvals']
    with pytest.raises(MuseError,match='source_not_qualified'):await broker.enqueue(action(),'device:owner')


@pytest.mark.asyncio
async def test_confirmed_receipt_requires_claim_and_exact_digest(broker):
    command=await broker.enqueue(action(),'device:owner')
    result=Outcome(command_id=command['command_id'],command_digest=digest(action().intent()),state='CONFIRMED',observed_at_ms=NOW,evidence_digest='c'*64,reason='fixture_observed')
    with pytest.raises(MuseError,match='command_not_claimed'):await broker.complete(result)
    await broker.claim()
    with pytest.raises(MuseError,match='outcome_command_mismatch'):
        await broker.complete(result.model_copy(update={'command_digest':'d'*64}))
    done=await broker.complete(result)
    assert done['state']=='CONFIRMED' and not done['is_work_outcome']
    assert await broker.complete(result)==done
    await broker.ingest(snapshot(2))
    assert (await broker.overview())['approvals']==[]


@pytest.mark.asyncio
async def test_crash_after_claim_never_requeues(broker):
    await broker.enqueue(action(),'device:owner')
    assert len(await broker.claim())==1
    restarted=MuseService(broker.store,producer_id='fixture-browser',now=lambda:NOW)
    assert await restarted.claim()==[]


@pytest.mark.asyncio
async def test_message_is_bound_and_idempotent(broker):
    a=action(action='SEND_MESSAGE',text='Fixture message',approval_id=None,action_fingerprint=None,choice=None)
    first=await broker.enqueue(a,'site:owner')
    assert first==await broker.enqueue(a,'site:owner')
    [command]=await broker.claim()
    assert command['intent']['thread_id']=='thread-fixture'
    assert command['prompt'] is None


@pytest.mark.asyncio
async def test_unknown_permission_requires_bound_stepup_even_from_site(broker):
    s=snapshot(2);s.sessions[0].revision=2;s.sessions[0].approvals[0].revision=2;s.sessions[0].approvals[0].action_class='UNCLASSIFIED'
    await broker.ingest(s)
    receipt=await broker.enqueue(action(expected_revision=2),'site:owner')
    assert receipt['state']=='AWAITING_OWNER_VERIFICATION'
    assert await broker.claim()==[]
    # Deny does not confer privilege.
    assert (await broker.enqueue(action(expected_revision=2,choice='DENY',idempotency_key='site-deny-distinct'),'site:owner'))['state']=='QUEUED'


@pytest.mark.asyncio
async def test_fresh_native_biometric_challenge_binds_exact_action(broker):
    private=ec.generate_private_key(ec.SECP256R1())
    public=private.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    await broker.store.execute("INSERT INTO devices(device_id,public_key_pem,enrolled_at_unix) VALUES(?,?,?)",('owner',public,NOW//1000))
    s=snapshot(2);s.sessions[0].revision=2;s.sessions[0].approvals[0].revision=2;s.sessions[0].approvals[0].action_class='A4'
    await broker.ingest(s)
    a=action(expected_revision=2)
    challenge=await broker.challenge(a,'owner')
    signature=base64.b64encode(private.sign(challenge['canonical'].encode(),ec.ECDSA(hashes.SHA256()))).decode()
    proved=a.model_copy(update={'challenge_id':challenge['challenge_id'],'signature_b64':signature})
    assert (await broker.enqueue(proved,'device:owner',device_id='owner'))['state']=='QUEUED'
    assert (await broker.enqueue(proved,'device:owner',device_id='owner'))['state']=='QUEUED'


@pytest.mark.asyncio
async def test_api_relay_cannot_use_owner_route_and_native_cannot_ingest(broker,tmp_path):
    token=tmp_path/'relay';token.write_text('r'*48);token.chmod(0o600)
    settings=SimpleNamespace(muse_enabled=True,muse_actuation_enabled=True,muse_relay_token_file=str(token),muse_command_signing_key_file='',muse_site_policy_file='')
    app=FastAPI();app.include_router(build_muse_router(broker,settings))
    @app.middleware('http')
    async def fixture_identity(request:Request,call_next):
        if request.headers.get('X-Fixture-Owner')=='yes':
            request.state.van_device_id='owner';request.state.van_device_proved=request.headers.get('X-Fixture-Proof')=='yes'
        return await call_next(request)
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://fixture') as client:
        assert (await client.post('/v1/muse/actions',json=action().model_dump(),headers={'X-Muse-Relay-Token':'r'*48})).status_code==401
        assert (await client.post('/v1/muse/actions',json=action().model_dump(),headers={'X-Fixture-Owner':'yes'})).status_code==403
        assert (await client.post('/v1/muse/relay',json={'operation':'claim','arguments':{}},headers={'X-Fixture-Owner':'yes','X-Fixture-Proof':'yes'})).status_code==403
        response=await client.post('/v1/muse/actions',json=action().model_dump(),headers={'X-Fixture-Owner':'yes','X-Fixture-Proof':'yes'})
        assert response.status_code==202 and response.json()['state']=='QUEUED'


def test_dispatch_signature_is_not_an_unsigned_owner_assertion(tmp_path):
    key=ed25519.Ed25519PrivateKey.generate();path=tmp_path/'signer.pem'
    path.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()));path.chmod(0o600)
    body={'command_id':'fixture-command','intent':{'choice':'DENY'}}
    signed=signer(str(path))(body)
    key.public_key().verify(base64.urlsafe_b64decode(signed['signature']+'=='),canonical(body).encode())
    path.chmod(0o644)
    with pytest.raises(MuseError,match='configuration_permissions'):signer(str(path))


@pytest.mark.asyncio
async def test_gateway_policy_ignores_untrusted_source_risk_label(broker):
    broker.classification_policy=lambda prompt:'UNCLASSIFIED'
    changed=snapshot(2);changed.sessions[0].revision=2;changed.sessions[0].approvals[0].revision=2
    await broker.ingest(changed)
    with pytest.raises(MuseError,match='bound_owner_step_up_required'):
        await broker.enqueue(action(expected_revision=2),'device:owner')


@pytest.mark.asyncio
async def test_unknown_capture_does_not_publish_content(broker):
    changed=snapshot(2);changed.sessions[0].current_job_only=False
    with pytest.raises(MuseError,match='unqualified_content_refused'):await broker.ingest(changed)


@pytest.mark.asyncio
async def test_old_receipt_reconciliation_does_not_refresh_source(broker):
    broker.now=lambda:NOW+300000
    assert (await broker.ingest(snapshot()))['replayed']
    assert (await broker.overview())['relay']['state']=='stale'


@pytest.mark.asyncio
async def test_original_receipt_is_scoped_to_the_owner_principal(broker):
    first=await broker.enqueue(action(),'device:owner')
    assert first==await broker.receipt_by_key(action().idempotency_key,'device:owner')
    with pytest.raises(MuseError,match='command_unknown'):
        await broker.receipt_by_key(action().idempotency_key,'site:other')


@pytest.mark.asyncio
async def test_site_request_only_completes_after_independent_native_proof(broker):
    private=ec.generate_private_key(ec.SECP256R1())
    public=private.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    await broker.store.execute("INSERT INTO devices(device_id,public_key_pem,enrolled_at_unix) VALUES(?,?,?)",('owner',public,NOW//1000))
    changed=snapshot(2);changed.sessions[0].revision=2;changed.sessions[0].approvals[0].revision=2;changed.sessions[0].approvals[0].action_class='A4'
    await broker.ingest(changed)
    requested=await broker.enqueue(action(expected_revision=2),'site:owner')
    assert await broker.claim()==[]
    native=action(expected_revision=2,idempotency_key='native-independent-request')
    challenge=await broker.challenge(native,'owner')
    signature=base64.b64encode(private.sign(challenge['canonical'].encode(),ec.ECDSA(hashes.SHA256()))).decode()
    allowed=await broker.enqueue(native.model_copy(update={'challenge_id':challenge['challenge_id'],'signature_b64':signature}),'device:owner',device_id='owner')
    assert (await broker.receipt(requested['command_id'],'site:owner'))['linked_command_id']==allowed['command_id']
    [command]=await broker.claim()
    assert command['principal']=='device:owner'
    await broker.complete(Outcome(command_id=command['command_id'],command_digest=command['command_digest'],state='CONFIRMED',observed_at_ms=NOW,evidence_digest='d'*64,reason='fixture_only'))
    receipt=await broker.receipt(requested['command_id'],'site:owner')
    assert receipt['state']=='CONFIRMED' and receipt['verified_on_owner_device']


@pytest.mark.asyncio
async def test_site_verification_cannot_turn_native_denial_into_allow(broker):
    changed=snapshot(2);changed.sessions[0].revision=2;changed.sessions[0].approvals[0].revision=2;changed.sessions[0].approvals[0].action_class='A4'
    await broker.ingest(changed)
    request=await broker.enqueue(action(expected_revision=2),'site:owner')
    await broker.enqueue(action(expected_revision=2,choice='DENY',idempotency_key='native-denial'),'device:owner')
    assert (await broker.receipt(request['command_id'],'site:owner'))['state']=='SUPERSEDED'
    [command]=await broker.claim()
    assert command['intent']['choice']=='DENY'


def test_retention_preserves_muse_replay_and_owner_intent_fences():
    from van_gateway.ops.retention import BY_TABLE, RetentionClass, RETENTION_DAYS
    for table in ("muse_sources", "muse_sessions", "muse_approvals", "muse_commands"):
        assert BY_TABLE[table].retention == RetentionClass.OWNER_STATE
        assert RETENTION_DAYS[BY_TABLE[table].retention] is None
