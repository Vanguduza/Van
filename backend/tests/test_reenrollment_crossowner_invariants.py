"""Original reenrollment audit/retention boundaries on real SQLite fixtures."""
import asyncio
import json

import pytest

from test_owner_device_reenrollment_recovery import setup
from van_gateway.audit.service import AuditService
from van_gateway.auth.device_binding import DeviceBindingError
from van_gateway.context.forget import FORGETTABLE, OwnerMemory
from van_gateway.ops.retention import RetentionService

pytestmark=pytest.mark.asyncio


async def test_original_rebind_audit_commits_once_with_intent_and_lost_ack_replays_without_credentials(tmp_path,monkeypatch):
    f=await setup(tmp_path);recover=f.service.recover
    async def lost_ack(**kwargs):raise OSError('synthetic original committed response lost')
    monkeypatch.setattr(f.service,'recover',lost_ack)
    with pytest.raises(OSError):await f.service.start(**f.request)
    original=await f.store.fetchone("SELECT * FROM audit WHERE capability='device.rebind'")
    assert original is not None and original['result']=='accepted'
    body=json.loads(original['after_json'])
    assert body['operation_id']==f.request['operation_id'] and body['phase']=='RETIRING'
    assert set(body)=={'operation_id','original_binding_id','original_bound_at_ms','native_operation_id','phase'}
    assert all(word not in original['after_json'] for word in ['bootstrap_token','pairing','attestation_challenge','encrypted_response'])
    monkeypatch.setattr(f.service,'recover',recover)
    await asyncio.gather(*(f.service.start(**f.request) for _ in range(3)))
    await f.service.recover(operation_id=f.request['operation_id'],operator_id=f.request['operator_id'],reconcile=False)
    rows=await f.store.fetchall("SELECT * FROM audit WHERE capability='device.rebind'")
    assert len(rows)==1 and dict(rows[0])==dict(original)
    assert (await AuditService(f.store).verify_chain())['ok']


async def test_audit_append_failure_rolls_back_original_retirement_and_receipt(tmp_path,monkeypatch):
    f=await setup(tmp_path)
    async def unavailable(*args,**kwargs):raise OSError('synthetic original audit writer failure')
    monkeypatch.setattr(AuditService,'record_in_transaction',unavailable)
    with pytest.raises(OSError):await f.service.start(**f.request)
    assert (await f.bindings.active()).binding_id==f.binding.binding_id
    assert (await f.auth.require_device('original-phone')).revoked_at_unix is None
    assert not await f.store.fetchall('SELECT * FROM owner_device_reenrollments')
    assert not await f.store.fetchall('SELECT * FROM device_certificate_retirements')
    assert not await f.store.fetchall("SELECT * FROM audit WHERE capability='device.rebind'")
    assert await f.bindings.challenge_for(f.old_unspent)


async def test_age_prune_and_inferred_memory_forget_do_not_erase_pending_original_security_fences(tmp_path):
    f=await setup(tmp_path);original=await f.service.start(**f.request)
    before=await f.store.fetchone('SELECT * FROM owner_device_reenrollments')
    retirement=await f.store.fetchone('SELECT * FROM device_certificate_retirements')
    future=original['expires_at_ms']+366*86400000
    await RetentionService(f.store).prune(now_ms=future,tables=('owner_device_reenrollments','device_certificate_retirements'))
    report=await OwnerMemory(f.store).forget_all()
    assert set(report['removed'])=={entry.table for entry in FORGETTABLE}
    assert 'owner_device_reenrollments' not in report['removed'] and 'device_certificate_retirements' not in report['removed']
    assert dict(await f.store.fetchone('SELECT * FROM owner_device_reenrollments'))==dict(before)
    assert dict(await f.store.fetchone('SELECT * FROM device_certificate_retirements'))==dict(retirement)
    expired=await f.service.start(**f.request,now_ms=future)
    assert expired['phase']=='RETIRING' and expired['bootstrap_token'] is None
    assert expired['expires_at_ms']==original['expires_at_ms']
    with pytest.raises(DeviceBindingError,match='retirement_pending'):
        await f.bindings.create_bootstrap_token()
