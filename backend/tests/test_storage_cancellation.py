"""Shutdown waits for actual SQLite workers and rolls back interrupted writes."""
from __future__ import annotations

import asyncio
import threading

import aiosqlite
import pytest

from van_gateway.storage.db import Store


@pytest.mark.asyncio
async def test_cancel_during_open_waits_for_worker_and_closes_connection(tmp_path, monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    connections = []
    original = aiosqlite.connect

    def delayed_connect(path):
        connection = original(path)
        connector = connection._connector

        def delayed_connector():
            entered.set()
            assert release.wait(5)
            return connector()

        connection._connector = delayed_connector
        connections.append(connection)
        return connection

    monkeypatch.setattr(aiosqlite, "connect", delayed_connect)
    store = Store(str(tmp_path / "cancel-open.sqlite3"))

    async def operation():
        async with store.connection():
            pytest.fail("cancelled opening must not enter the caller's operation")

    task = asyncio.create_task(operation())
    try:
        assert await asyncio.to_thread(entered.wait, 3)
        task.cancel()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert not task.done()
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 3)
    connection = connections[0]
    await asyncio.to_thread(connection._thread.join, 1)
    assert not connection._thread.is_alive()
    assert connection._connection is None


@pytest.mark.asyncio
async def test_cancel_during_close_waits_for_cleanup_and_keeps_cancellation(tmp_path, monkeypatch):
    entered = asyncio.Event()
    release = asyncio.Event()
    connections = []
    original = aiosqlite.Connection.close

    async def delayed_close(connection):
        connections.append(connection)
        entered.set()
        await release.wait()
        await original(connection)

    monkeypatch.setattr(aiosqlite.Connection, "close", delayed_close)
    store = Store(str(tmp_path / "cancel-close.sqlite3"))

    async def operation():
        async with store.connection() as db:
            await db.execute("SELECT 1")

    task = asyncio.create_task(operation())
    await asyncio.wait_for(entered.wait(), 3)
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 3)
    assert len(connections) == 1
    connection = connections[0]
    await asyncio.to_thread(connection._thread.join, 1)
    assert not connection._thread.is_alive()
    assert connection._connection is None


@pytest.mark.asyncio
async def test_cancelled_transaction_rolls_back_and_releases_database(tmp_path):
    store = Store(str(tmp_path / "rollback.sqlite3"))
    async with store.connection() as db:
        await db.execute("CREATE TABLE entries(value TEXT)")
        await db.commit()
    inserted = asyncio.Event()

    async def operation():
        async with store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            await db.execute("INSERT INTO entries(value) VALUES('interrupted')")
            inserted.set()
            await asyncio.Event().wait()
            await db.commit()

    task = asyncio.create_task(operation())
    await asyncio.wait_for(inserted.wait(), 3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 3)
    async with store.connection() as db:
        cursor = await db.execute("SELECT COUNT(*) FROM entries")
        assert (await cursor.fetchone())[0] == 0
        await db.execute("INSERT INTO entries(value) VALUES('after-cancellation')")
        await db.commit()
        cursor = await db.execute("SELECT value FROM entries")
        assert (await cursor.fetchone())[0] == "after-cancellation"
