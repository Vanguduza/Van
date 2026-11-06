"""Real competing SQLite writers must not extend expired pairing authority."""
import asyncio
from types import SimpleNamespace
import aiosqlite
import pytest
from cryptography.fernet import Fernet
from van_gateway.auth import service
from van_gateway.auth.service import AuthError, AuthService
from van_gateway.storage.db import Store

@pytest.mark.asyncio
@pytest.mark.parametrize('operation', ['pair', 'renew'])
async def test_authority_expiring_while_waiting_for_sql_writer_is_refused(tmp_path, monkeypatch, operation):
    clock = [1000]
    monkeypatch.setattr(service, 'time', SimpleNamespace(time=lambda: clock[0]))
    store = Store(str(tmp_path / 'authority.sqlite'))
    await store.migrate()
    auth = AuthService(store, Fernet.generate_key().decode())
    ticket = await auth.create_pairing_ticket(ttl_seconds=60)
    if operation == 'renew':
        await auth.enroll('phone', 'secret', 'PEM')
        await store.execute('UPDATE capability_grants SET expires_at_unix = 1060')
    started = asyncio.Event()
    original = aiosqlite.Connection.execute
    async def observed(db, sql, *args, **kwargs):
        if sql == 'BEGIN IMMEDIATE' or sql.startswith('UPDATE capability_grants SET expires_at_unix'):
            started.set()
        return await original(db, sql, *args, **kwargs)
    async with store.connection() as writer:
        await writer.execute('BEGIN IMMEDIATE')
        monkeypatch.setattr(aiosqlite.Connection, 'execute', observed)
        task = asyncio.create_task(auth.pair_device(ticket.token, 'phone', 'secret', 'PEM') if operation == 'pair' else auth.renew_grant('phone'))
        try:
            await asyncio.wait_for(started.wait(), 2)
            assert not task.done()
            clock[0] = 1060
            await writer.commit()
            with pytest.raises(AuthError) as error:
                await asyncio.wait_for(task, 3)
            assert error.value.code == ('pairing_ticket_invalid' if operation == 'pair' else 'grant_not_renewable')
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    if operation == 'pair':
        assert await store.fetchone('SELECT * FROM devices') is None
        assert (await store.fetchone('SELECT used_at_unix FROM pairing_tickets'))['used_at_unix'] is None
    else:
        assert (await store.fetchone('SELECT expires_at_unix FROM capability_grants'))['expires_at_unix'] == 1060

@pytest.mark.asyncio
@pytest.mark.parametrize('target', ['devices', 'capability_grants'])
async def test_queued_renewal_cannot_outlive_committed_revocation(tmp_path, monkeypatch, target):
    store = Store(str(tmp_path / 'revocation.sqlite'))
    await store.migrate()
    auth = AuthService(store, Fernet.generate_key().decode())
    await auth.enroll('phone', 'secret', 'PEM')
    before = dict(await store.fetchone('SELECT * FROM capability_grants'))
    started = asyncio.Event()
    original = aiosqlite.Connection.execute
    async def observed(db, sql, *args, **kwargs):
        if sql == 'BEGIN IMMEDIATE': started.set()
        return await original(db, sql, *args, **kwargs)
    async with store.connection() as writer:
        await writer.execute('BEGIN IMMEDIATE')
        await writer.execute(f'UPDATE {target} SET revoked_at_unix = 1')
        monkeypatch.setattr(aiosqlite.Connection, 'execute', observed)
        task = asyncio.create_task(auth.renew_grant('phone'))
        try:
            await asyncio.wait_for(started.wait(), 2)
            assert not task.done()
            await writer.commit()
            with pytest.raises(AuthError) as error: await asyncio.wait_for(task, 3)
            assert error.value.code == 'grant_not_renewable'
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    assert (await store.fetchone('SELECT expires_at_unix FROM capability_grants'))['expires_at_unix'] == before['expires_at_unix']

@pytest.mark.asyncio
async def test_renewal_write_failure_preserves_original_grant(tmp_path):
    store = Store(str(tmp_path / 'failed-write.sqlite'))
    await store.migrate()
    auth = AuthService(store, Fernet.generate_key().decode())
    await auth.enroll('phone', 'secret', 'PEM')
    before = dict(await store.fetchone('SELECT * FROM capability_grants'))
    await store.execute("CREATE TRIGGER deny_renewal BEFORE UPDATE ON capability_grants BEGIN SELECT RAISE(ABORT, 'test renewal refusal'); END")
    with pytest.raises(aiosqlite.IntegrityError, match='test renewal refusal'):
        await auth.renew_grant('phone', now=before['created_at_unix'] + 1)
    assert dict(await store.fetchone('SELECT * FROM capability_grants')) == before

@pytest.mark.asyncio
async def test_live_renewal_is_durable_and_never_shortens_existing_grant(tmp_path):
    store = Store(str(tmp_path / 'renew.sqlite'))
    await store.migrate()
    auth = AuthService(store, Fernet.generate_key().decode())
    await auth.enroll('phone', 'secret', 'PEM')
    before = await auth.grant_status('phone')
    grant = await store.fetchone('SELECT created_at_unix FROM capability_grants')
    now = grant['created_at_unix'] + 100
    renewed = await auth.renew_grant('phone', now=now)
    assert renewed['expires_at_unix'] > before['expires_at_unix']
    reopened = AuthService(Store(store.path))
    assert (await reopened.grant_status('phone', now=now)) == renewed
    older = await reopened.renew_grant('phone', now=now - 1)
    assert older['expires_at_unix'] == renewed['expires_at_unix']
    with pytest.raises(AuthError) as error:
        await reopened.renew_grant('phone', now=renewed['expires_at_unix'])
    assert error.value.code == 'grant_not_renewable'

@pytest.mark.asyncio
@pytest.mark.parametrize('phase', ['pair_device_read', 'pair_grant_write', 'renew_grant_write'])
async def test_original_authority_expiring_inside_transaction_rolls_back(tmp_path, monkeypatch, phase):
    clock = [1000]
    monkeypatch.setattr(service, 'time', SimpleNamespace(time=lambda: clock[0]))
    store = Store(str(tmp_path / 'mid-transaction.sqlite'))
    await store.migrate()
    key = Fernet.generate_key().decode()
    auth = AuthService(store, key)
    ticket = await auth.create_pairing_ticket(ttl_seconds=60)
    renewing = phase == 'renew_grant_write'
    if renewing:
        await auth.enroll('phone', 'secret', 'PEM')
        await store.execute('UPDATE capability_grants SET expires_at_unix=1060')
    before = [dict(r) for r in await store.fetchall('SELECT * FROM capability_grants')]
    execute = aiosqlite.Connection.execute
    intercepted = []
    async def elapsed(db, sql, *args, **kwargs):
        result = await execute(db, sql, *args, **kwargs)
        target = ((phase == 'pair_device_read' and sql == 'SELECT device_id, revoked_at_unix FROM devices WHERE device_id = ?')
                  or (phase == 'pair_grant_write' and sql.startswith('INSERT INTO capability_grants'))
                  or (phase == 'renew_grant_write' and sql.startswith('UPDATE capability_grants SET expires_at_unix')))
        if target:
            intercepted.append(phase)
            clock[0] = 1060
        return result
    monkeypatch.setattr(aiosqlite.Connection, 'execute', elapsed)
    with pytest.raises(AuthError) as error:
        if renewing: await auth.renew_grant('phone')
        else: await auth.pair_device(ticket.token, 'phone', 'secret', 'PEM')
    assert error.value.code == ('grant_not_renewable' if renewing else 'pairing_ticket_invalid')
    assert intercepted == [phase]
    reopened = Store(store.path)
    assert [dict(r) for r in await reopened.fetchall('SELECT * FROM capability_grants')] == before
    if not renewing:
        assert await reopened.fetchall('SELECT * FROM devices') == []
        assert (await reopened.fetchone('SELECT used_at_unix FROM pairing_tickets'))['used_at_unix'] is None
        assert await AuthService(reopened, key).load_persisted_secrets() == 0
        with pytest.raises(AuthError, match='not loaded'): auth.sign('phone', 'probe')
