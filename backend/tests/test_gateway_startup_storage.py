"""Import and runtime storage boundaries, including the actual ASGI entry point."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from van_gateway.config import Settings, get_settings


@pytest.mark.parametrize("working_directory", [".", "backend"])
@pytest.mark.parametrize("explicit_database", [False, True])
def test_importing_the_deployed_entry_point_never_opens_storage(tmp_path, working_directory, explicit_database):
    root = Path(__file__).resolve().parents[2]
    # A fresh interpreter also catches import-time effects hidden by pytest's cache.
    probe = """
import sys, os
from pathlib import Path
events = []
def audit(event, args):
    denied = event in {'sqlite3.connect', 'os.mkdir', 'socket.connect', 'socket.bind',
                      'subprocess.Popen', 'os.system', 'os.exec', 'os.fork', 'os.posix_spawn'}
    if event == 'open':
        name, mode, flags = args
        denied = ((isinstance(mode, str) and any(c in mode for c in 'wax+')) or
                  (isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)))
        if not isinstance(name, int):
            path = Path(os.fsdecode(name)).absolute()
            denied = denied or path.name == '.env' or path.is_relative_to(Path.home())
    if denied:
        events.append((event, str(args[0])))
        raise AssertionError('import attempted an effect before startup: ' + event)
sys.addaudithook(audit)
import van_gateway.app as gateway
assert Path(gateway.__file__).resolve() == Path(sys.argv[1]) / 'backend/van_gateway/app.py'
assert events == [], events
"""
    environment = {**os.environ, "PYTHONPATH": str(root / "backend") + os.pathsep + str(root),
                   "PYTHONDONTWRITEBYTECODE": "1"}
    environment.pop("VAN_DATABASE_PATH", None)
    if explicit_database:
        environment["VAN_DATABASE_PATH"] = str(tmp_path / "never-created" / "db.sqlite3")
    result = subprocess.run(
        [sys.executable, "-B", "-c", probe, str(root)], cwd=root / working_directory,
        env=environment, text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert not (tmp_path / "never-created").exists()


def test_only_the_owned_store_produces_its_wal_and_recovers_after_close(tmp_path):
    """A known producer/absolute fixture, not attribution of historical sidecars."""
    import asyncio
    from van_gateway.storage.db import Store

    database = (tmp_path / "runtime" / "fixture.sqlite3").resolve()
    wal, shm = Path(str(database)+"-wal"), Path(str(database)+"-shm")
    store = Store(str(database))
    assert not database.parent.exists()

    async def lifecycle():
        async with store.connection() as connection:
            await connection.execute("CREATE TABLE owned_probe(value TEXT)")
            await connection.execute("INSERT INTO owned_probe VALUES (?)", ("retained original",))
            await connection.commit()
            assert database.is_file() and wal.is_file() and shm.is_file()
        assert database.is_file() and not wal.exists() and not shm.exists()
        async with store.connection() as connection:
            row = await (await connection.execute("SELECT value FROM owned_probe")).fetchone()
            assert row[0] == "retained original"
        assert not wal.exists() and not shm.exists()

    asyncio.run(lifecycle())


def test_development_default_is_absolute_and_not_the_checkout(monkeypatch):
    monkeypatch.delenv("VAN_DATABASE_PATH", raising=False)
    settings = Settings(_env_file=None)
    assert Path(settings.database_path).is_absolute()
    assert Path(settings.database_path) != Path("data/van_gateway.sqlite3").resolve()


@pytest.mark.parametrize("database", [None, "data/van_gateway.sqlite3", "", ":memory:"])
def test_production_refuses_missing_or_relative_storage(monkeypatch, database):
    monkeypatch.delenv("VAN_DATABASE_PATH", raising=False)
    values = dict(_env_file=None, van_env="production", require_device_binding=True,
                  hermes_base_url="https://hermes.example", VAN_PUBLIC_BASE_URL="https://van.example")
    if database is not None:
        values["database_path"] = database
    with pytest.raises(ValueError, match="VAN_DATABASE_PATH"):
        Settings(**values)


def test_actual_lazy_asgi_start_migrates_only_the_configured_store(tmp_path, monkeypatch):
    from van_gateway.app import create_app
    from van_gateway.lazy_app import LazyGateway

    database = tmp_path / "runtime" / "gateway.sqlite3"
    monkeypatch.setenv("VAN_DATABASE_PATH", str(database))
    monkeypatch.setenv("VAN_SCHEDULER_ENABLED", "false")
    monkeypatch.setenv("VAN_INGRESS_TOKEN", "startup-test-ingress")
    get_settings.cache_clear()
    try:
        gateway = LazyGateway(create_app)
        assert not database.parent.exists()
        with TestClient(gateway) as client:
            response = client.get("/health", headers={"X-Van-Ingress-Token": "startup-test-ingress"})
            assert response.status_code == 200, response.text
            assert database.is_file()
            assert client.get("/health").status_code == 401
        assert gateway.state.store.path == str(database)
    finally:
        get_settings.cache_clear()
