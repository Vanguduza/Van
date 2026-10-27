"""Real SQL waits cannot extend an original one-use A4 approval window."""
import asyncio
from contextlib import asynccontextmanager

import pytest

from test_owner_approval_parameters import _approval
from van_gateway.approval.service import OwnerApprovalError


@pytest.mark.asyncio
@pytest.mark.parametrize('durable_receipt', [None, {'request_id': 'original-recovery-request'}])
@pytest.mark.parametrize('boundary', ['sql_writer', 'device_read'])
async def test_expiry_rechecked_after_actual_writer_wait_and_before_consumption(
        tmp_path, monkeypatch, durable_receipt, boundary):
    parameters = {'account': 'Demo', 'scope': 'autonomous'}
    service, challenge, identity, proof = await _approval(tmp_path, parameters)
    clock = [1001]
    monkeypatch.setattr('van_gateway.approval.service.time.time', lambda: clock[0])
    original_connection = service.store.connection
    connection_ready, permit_begin, begin_requested = (asyncio.Event() for _ in range(3))
    device_read, permit_device_result = asyncio.Event(), asyncio.Event()
    loop = asyncio.get_running_loop()

    @asynccontextmanager
    async def observed_connection():
        async with original_connection() as db:
            await db.set_trace_callback(lambda sql: loop.call_soon_threadsafe(begin_requested.set)
                                        if sql.strip().upper() == 'BEGIN IMMEDIATE' else None)
            original_execute = db.execute

            async def execute(sql, *args, **kwargs):
                cursor = await original_execute(sql, *args, **kwargs)
                if 'SELECT public_key_pem, revoked_at_unix FROM devices' in sql:
                    device_read.set()
                    await permit_device_result.wait()
                return cursor

            db.execute = execute
            connection_ready.set()
            await permit_begin.wait()
            yield db

    monkeypatch.setattr(service.store, 'connection', observed_connection)
    task = asyncio.create_task(service.verify_and_consume(
        **identity, challenge_id=challenge.challenge_id, signature_b64=proof,
        parameters=parameters, durable_receipt=durable_receipt))
    try:
        await asyncio.wait_for(connection_ready.wait(), 5)
        if boundary == 'sql_writer':
            async with original_connection() as blocker:
                await blocker.execute('BEGIN IMMEDIATE')
                permit_begin.set()
                await asyncio.wait_for(begin_requested.wait(), 5)
                assert not task.done()
                clock[0] = challenge.expires_at_unix
                permit_device_result.set()
                await blocker.rollback()
        else:
            permit_begin.set()
            await asyncio.wait_for(device_read.wait(), 5)
            clock[0] = challenge.expires_at_unix
            permit_device_result.set()
        with pytest.raises(OwnerApprovalError, match='approval_challenge_expired'):
            await asyncio.wait_for(task, 5)
    finally:
        permit_begin.set()
        permit_device_result.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    # Use the independent original connection, outside the observing wrapper.
    async with original_connection() as db:
        cursor = await db.execute('SELECT key FROM runtime_meta WHERE key=?',
                                  (service.PREFIX + challenge.challenge_id,))
        assert await cursor.fetchone() is None
        cursor = await db.execute('SELECT key FROM runtime_meta WHERE key=?',
                                  ('owner_approval_receipt:' + challenge.challenge_id,))
        assert await cursor.fetchone() is None


@pytest.mark.asyncio
async def test_original_window_remains_usable_until_half_open_expiry(tmp_path):
    parameters = {'account': 'Demo', 'scope': 'autonomous'}
    service, challenge, identity, proof = await _approval(tmp_path, parameters)
    receipt = await service.verify_and_consume(
        **identity, challenge_id=challenge.challenge_id, signature_b64=proof,
        parameters=parameters, now_unix=challenge.expires_at_unix - 1,
        durable_receipt={'request_id': 'original-recovery-request'})
    assert receipt['operation_id'] == challenge.challenge_id
    assert receipt['expires_at_unix'] == challenge.expires_at_unix
    with pytest.raises(OwnerApprovalError, match='approval_challenge_unknown_or_consumed'):
        await service.verify_and_consume(
            **identity, challenge_id=challenge.challenge_id, signature_b64=proof,
            parameters=parameters, now_unix=challenge.expires_at_unix - 1)
