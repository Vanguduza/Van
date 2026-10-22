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
def test_importing_the_deployed_entry_point_never_opens_storage(tmp_path, working_directory):
    root = Path(__file__).resolve().parents[2]
    # A fresh interpreter also catches import-time effects hidden by pytest's cache.
    probe = """
import sys
events = []
def audit(event, args):
    if event in {'sqlite3.connect', 'os.mkdir'}:
        events.append((event, str(args[0])))
sys.addaudithook(audit)
import van_gateway.app
assert events == [], events
"""
    result = subprocess.run(
        [sys.executable, "-c", probe], cwd=root / working_directory,
        env={**os.environ, "PYTHONPATH": str(root / "backend") + os.pathsep + str(root),
             "PYTHONDONTWRITEBYTECODE": "1", "VAN_DATABASE_PATH": str(tmp_path / "never-created" / "db.sqlite3")},
        text=True, capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert not (tmp_path / "never-created").exists()


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
