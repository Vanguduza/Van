"""Actual Auth writer ordering, cancellation and current-owner controls, SOURCE only."""
import asyncio
from contextlib import closing
import hashlib
import threading

import pytest
from test_funding_classification_api import label_client,post,PATH
from test_device_proof_enforcement import _settings,_base_headers,_paired
from van_gateway.trading.funding_classification_api import LabelError
from vati.core.ledger import Ledger
from vati.core.events import EventKind


def caller(client):
    device=client[2]
    return {'owner_id':'owner','device_id':device.device.device_id,
            'access_token_hash':hashlib.sha256(device.access_token.encode()).hexdigest(),'proved':False}


@pytest.mark.asyncio
async def test_revoked_token_changed_and_wrong_owner_refuse_under_actual_writer(label_client):
    service=label_client[1].state.funding_classifications;who=caller(label_client)
    for wrong in (who|{'owner_id':'foreign'},who|{'access_token_hash':'0'*64},who|{'device_id':'foreign-device'}):
        with pytest.raises(LabelError,match='CALLER_NOT_CURRENT'):await service.call('publish',wrong,body=label_client[4])
    async with label_client[1].state.store.connection() as db:
        await db.execute('UPDATE devices SET revoked_at_unix=1 WHERE device_id=?',(who['device_id'],));await db.commit()
    assert (await post(label_client)).status_code==401
    with closing(Ledger(label_client[5])) as ledger:assert ledger.count(EventKind.FUNDING_OWNER_CLASSIFICATION)==0


@pytest.mark.asyncio
async def test_strict_absent_binding_refuses_without_narrowing_legacy(label_client,monkeypatch):
    app=label_client[1]
    # The app policy consumes the actual Settings object, not a fabricated grant.
    from van_gateway.config import get_settings
    monkeypatch.setattr(get_settings(),'require_device_binding',True)
    r=await post(label_client);assert r.status_code in (401,403),r.text
    with closing(Ledger(label_client[5])) as ledger:assert ledger.count(EventKind.FUNDING_OWNER_CLASSIFICATION)==0


@pytest.mark.asyncio
async def test_queued_revocation_wins_auth_writer_no_annotation(label_client):
    app=label_client[1];service=app.state.funding_classifications;who=caller(label_client)
    async with app.state.store.connection() as db:
        await db.execute('BEGIN IMMEDIATE')
        pending=asyncio.create_task(service.call('publish',who,body=label_client[4]))
        await asyncio.sleep(.05)
        await db.execute('UPDATE devices SET revoked_at_unix=1 WHERE device_id=?',(who['device_id'],));await db.commit()
    with pytest.raises(LabelError,match='CALLER_NOT_CURRENT'):await pending
    with closing(Ledger(label_client[5])) as ledger:assert ledger.count(EventKind.FUNDING_OWNER_CLASSIFICATION)==0


@pytest.mark.asyncio
async def test_auth_fence_stays_held_during_ledger_wait_then_revocation(label_client,monkeypatch):
    app=label_client[1];service=app.state.funding_classifications;who=caller(label_client)
    entered=threading.Event();worker=service._worker
    def observed(*a,**k):entered.set();return worker(*a,**k)
    monkeypatch.setattr(service,'_worker',observed)
    with closing(Ledger(label_client[5])) as blocker:
        with blocker.atomic():
            pending=asyncio.create_task(service.call('publish',who,body=label_client[4]))
            assert await asyncio.to_thread(entered.wait,5)
            started=asyncio.Event()
            async def revoke():
                async with app.state.store.connection() as db:
                    started.set();await db.execute('BEGIN IMMEDIATE')
                    await db.execute('UPDATE devices SET revoked_at_unix=1 WHERE device_id=?',(who['device_id'],));await db.commit()
            revoker=asyncio.create_task(revoke());await started.wait();await asyncio.sleep(.05)
            assert not revoker.done()
        receipt=await pending
    await revoker
    assert receipt['state']=='ASSERTED'
    assert (await post(label_client)).status_code==401


@pytest.mark.asyncio
async def test_final_expiry_after_ledger_wait_never_uses_precomputed_clock(label_client,monkeypatch):
    app=label_client[1];service=app.state.funding_classifications;now=[1000];service.clock=lambda:now[0]
    entered=threading.Event();worker=service._worker
    def observed(*a,**k):entered.set();return worker(*a,**k)
    monkeypatch.setattr(service,'_worker',observed)
    with closing(Ledger(label_client[5])) as blocker:
        with blocker.atomic():
            pending=asyncio.create_task(service.call('publish',caller(label_client),body=label_client[4]))
            assert await asyncio.to_thread(entered.wait,5);now[0]=301000
        with pytest.raises(LabelError,match='REQUEST_EXPIRED'):await pending
    with closing(Ledger(label_client[5])) as ledger:assert ledger.count(EventKind.FUNDING_OWNER_CLASSIFICATION)==0


@pytest.mark.asyncio
async def test_pre_append_cancel_holds_auth_fence_until_thread_reaped(label_client,monkeypatch):
    app=label_client[1];service=app.state.funding_classifications
    entered=threading.Event();release=threading.Event();worker=service._worker
    def delayed(*a,**k):entered.set();assert release.wait(5);return worker(*a,**k)
    monkeypatch.setattr(service,'_worker',delayed)
    pending=asyncio.create_task(service.call('publish',caller(label_client),body=label_client[4]))
    assert await asyncio.to_thread(entered.wait,5);pending.cancel();await asyncio.sleep(.02)
    assert not pending.done();release.set()
    with pytest.raises(asyncio.CancelledError):await pending
    assert not service.tasks
    with closing(Ledger(label_client[5])) as ledger:assert ledger.count(EventKind.FUNDING_OWNER_CLASSIFICATION)==0


@pytest.mark.asyncio
async def test_cancel_after_commit_original_receipt_recovers_no_replacement(label_client,monkeypatch):
    service=label_client[1].state.funding_classifications;worker=service._worker
    committed=threading.Event();release=threading.Event()
    def delayed(*a,**k):
        result=worker(*a,**k);committed.set();assert release.wait(5);return result
    monkeypatch.setattr(service,'_worker',delayed)
    pending=asyncio.create_task(service.call('publish',caller(label_client),body=label_client[4]))
    assert await asyncio.to_thread(committed.wait,5);pending.cancel();await asyncio.sleep(.02)
    assert not pending.done();release.set()
    with pytest.raises(asyncio.CancelledError):await pending
    monkeypatch.setattr(service,'_worker',worker)
    receipt=await service.call('publish',caller(label_client),body=label_client[4])
    read=await service.call('inspect',caller(label_client),operation_id=label_client[4]['operation_id'])
    assert read['receipt']==receipt
    with closing(Ledger(label_client[5])) as ledger:assert ledger.count(EventKind.FUNDING_OWNER_CLASSIFICATION)==1


@pytest.mark.asyncio
async def test_actual_verified_old_key_fact_refuses_then_current_new_key_proof_succeeds(label_client,monkeypatch):
    """Trusted key-replacement SOURCE model, no production rotation API claim."""
    from test_device_proof_enforcement import _bind
    from test_owner_device_binding import _keypair
    from van_gateway.auth.device_binding import key_fingerprint
    ac,app,device,_,body,path=label_client
    old=await _bind(app,device.device.device_id);pem,new=_keypair()
    service=app.state.funding_classifications;call=service.call;seen=[]
    async def replaced(operation,who,**kwargs):
        if operation=='publish' and not seen:
            assert who['proved'] is True and len(who['verified_binding_identity'])==64
            binding=await app.state.owner_device_bindings.active()
            await app.state.store.execute('UPDATE owner_device_bindings SET public_key_pem=?,device_key_fingerprint=? WHERE binding_id=?',
                (pem,key_fingerprint(pem),binding.binding_id));seen.append(who['verified_binding_identity'])
        return await call(operation,who,**kwargs)
    monkeypatch.setattr(service,'call',replaced)
    refused=await post(label_client,key=old)
    assert refused.status_code==403 and refused.json()['detail']['code']=='FUNDING_LABEL_PROOF_BINDING_CHANGED'
    with closing(Ledger(path)) as ledger:assert ledger.count(EventKind.FUNDING_OWNER_CLASSIFICATION)==0
    assert (await post(label_client,key=old)).status_code==401
    current=await post(label_client,key=new);assert current.status_code==200,current.text
    assert (await post(label_client,key=new)).json()==current.json()
    assert (await ac.get(PATH+'/'+body['operation_id'],headers=_base_headers(device))).json()['receipt']==current.json()
    nonces=await app.state.store.fetchall('SELECT nonce FROM command_nonces WHERE device_id=?',(device.device.device_id,))
    assert len(nonces)==3  # old verified request + two distinct new-key requests, no second verifier pass
    with closing(Ledger(path)) as ledger:assert ledger.count(EventKind.FUNDING_OWNER_CLASSIFICATION)==1


@pytest.mark.asyncio
async def test_capture_comes_from_actual_validator_result_not_later_lookup(label_client,monkeypatch):
    from test_device_proof_enforcement import _bind
    from test_owner_device_binding import _keypair
    from van_gateway.auth.device_binding import key_fingerprint
    app=label_client[1];device=label_client[2]
    old=await _bind(app,device.device.device_id);pem,_=_keypair()
    validator=app.state.owner_device_bindings.require_proof;seen=[]
    async def verify_then_replace(**kwargs):
        verified=await validator(**kwargs)  # real signature validation, once
        if not seen:
            await app.state.store.execute('UPDATE owner_device_bindings SET public_key_pem=?,device_key_fingerprint=? WHERE binding_id=?',
                (pem,key_fingerprint(pem),verified.binding_id));seen.append(True)
        return verified  # immutable original key, never the newly current key
    monkeypatch.setattr(app.state.owner_device_bindings,'require_proof',verify_then_replace)
    result=await post(label_client,key=old)
    assert seen and result.status_code==403,result.text
    with closing(Ledger(label_client[5])) as ledger:assert ledger.count(EventKind.FUNDING_OWNER_CLASSIFICATION)==0


@pytest.mark.asyncio
async def test_proof_use_timestamp_is_not_a_key_generation(label_client,monkeypatch):
    from test_device_proof_enforcement import _bind
    app=label_client[1];device=label_client[2]
    key=await _bind(app,device.device.device_id);service=app.state.funding_classifications;call=service.call
    async def used(operation,who,**kwargs):
        if operation=='publish':
            await app.state.store.execute('UPDATE owner_device_bindings SET last_proof_at_ms=last_proof_at_ms+1 WHERE device_id=?',(device.device.device_id,))
        return await call(operation,who,**kwargs)
    monkeypatch.setattr(service,'call',used)
    result=await post(label_client,key=key)
    assert result.status_code==200,result.text


@pytest.mark.asyncio
async def test_boolean_alone_cannot_replace_actual_proof_fact_for_bound_writer(label_client):
    from test_device_proof_enforcement import _bind
    app=label_client[1];device=label_client[2]
    await _bind(app,device.device.device_id)
    with pytest.raises(LabelError,match='PROOF_BINDING_CHANGED'):
        await app.state.funding_classifications.call('publish',caller(label_client)|{'proved':True},body=label_client[4])
    with closing(Ledger(label_client[5])) as ledger:assert ledger.count(EventKind.FUNDING_OWNER_CLASSIFICATION)==0
