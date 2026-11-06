"""Signed HTTP pairing retains exact expiry while SQL writer acquisition waits."""
import asyncio
import time
from types import SimpleNamespace
import aiosqlite
import pytest
from test_pairing_recovery import _settings, client, proofs, _pending, _post, _counts
from van_gateway.auth import service

@pytest.mark.asyncio
@pytest.mark.parametrize('expire', [False, True])
async def test_signed_pairing_writer_wait_and_original_durable_result(client, proofs, monkeypatch, expire):
    ac, app = client
    payload, key = await _pending(app)
    clock = [int(time.time())]
    monkeypatch.setattr(service, 'time', SimpleNamespace(time=lambda: clock[0]))
    ticket = await app.state.store.fetchone('SELECT expires_at_unix FROM pairing_tickets')
    original_pair = app.state.auth.pair_device
    original_execute = aiosqlite.Connection.execute
    waiting = asyncio.Event()
    async def execute(db, sql, *args, **kwargs):
        if sql == 'BEGIN IMMEDIATE': waiting.set()
        return await original_execute(db, sql, *args, **kwargs)
    async def contended(*args, **kwargs):
        async with app.state.store.connection() as blocker:
            await blocker.execute('BEGIN IMMEDIATE')
            with monkeypatch.context() as local:
                local.setattr(aiosqlite.Connection, 'execute', execute)
                task = asyncio.create_task(original_pair(*args, **kwargs))
                try:
                    await asyncio.wait_for(waiting.wait(), 2)
                    assert not task.done()
                    if expire: clock[0] = int(ticket['expires_at_unix'])
                    await blocker.commit()
                    return await asyncio.wait_for(task, 3)
                finally:
                    if not task.done():
                        task.cancel()
                        await asyncio.gather(task, return_exceptions=True)
    monkeypatch.setattr(app.state.auth, 'pair_device', contended)
    response = await _post(ac, payload, key, proofs)
    if expire:
        assert response.status_code == 400, response.text
        assert response.json() == {'detail': 'Pairing ticket invalid or expired'}
        assert await _counts(app) == (0, 0, 0)
        assert (await app.state.store.fetchone('SELECT used_at_unix FROM pairing_tickets'))['used_at_unix'] is None
    else:
        assert response.status_code == 200, response.text
        assert await _counts(app) == (1, 1, 1)
        monkeypatch.setattr(app.state.auth, 'pair_device', original_pair)
        clock[0] = int(ticket['expires_at_unix']) + 1
        recovered = await _post(ac, payload, key, proofs)
        assert recovered.status_code == 200, recovered.text
        assert recovered.json() == response.json()
        assert await _counts(app) == (1, 1, 1)
