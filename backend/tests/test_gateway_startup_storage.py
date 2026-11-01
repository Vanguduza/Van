"""Import and runtime storage boundaries, including the actual ASGI entry point."""
from __future__ import annotations

import os
import json
from pathlib import Path
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from van_gateway.config import Settings, get_settings


_IMPORT_GUARD = """
import sys, os, sysconfig, json
from pathlib import Path
events = []
root = Path(sys.argv[1]).resolve()
source_inputs = {Path(path).resolve() for path in json.loads(Path(sys.argv[2]).read_text())}
runtime_roots = tuple(Path(sysconfig.get_path(name)).resolve() for name in ('stdlib', 'purelib', 'platlib'))
protected = (root / 'data', root / 'backend/data')
runtime_archives = {Path(path).resolve() for path in sys.path if path and Path(path).suffix == '.zip'
                    and Path(path).resolve().is_relative_to(Path(sys.base_prefix).resolve())}
metadata_names = {'METADATA', 'PKG-INFO', 'WHEEL', 'RECORD', 'entry_points.txt', 'top_level.txt', 'namespace_packages.txt'}
def beneath(path, bases):
    return any(path == base or path.is_relative_to(base) for base in bases)
def legitimate_input(path):
    code = path.suffix in {'.py', '.pyc', '.so', '.pyd', '.zip'}
    original = path
    if path.suffix == '.pyc' and path.parent.name == '__pycache__':
        original = path.parent.parent / (path.name.split('.'+sys.implementation.cache_tag, 1)[0]+'.py')
    if path in source_inputs or path in runtime_archives:
        return True
    if code and (original in source_inputs or beneath(path, runtime_roots)):
        return True
    return (beneath(path, runtime_roots) and path.name in metadata_names
            and any(part.endswith(('.dist-info', '.egg-info')) for part in path.parts))
def audit(event, args):
    denied = event in {'sqlite3.connect', 'os.mkdir', 'socket.connect', 'socket.bind',
                      'subprocess.Popen', 'os.system', 'os.exec', 'os.fork', 'os.posix_spawn'}
    if event == 'open':
        name, mode, flags = args
        denied = ((isinstance(mode, str) and any(c in mode for c in 'wax+')) or
                  (isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)))
        if not isinstance(name, int):
            logical = Path(os.path.abspath(os.fsdecode(name)))
            physical = logical.resolve()
            denied = (denied or logical.name == '.env' or logical.name.startswith('.env.')
                      or beneath(logical, protected) or beneath(physical, tuple(p.resolve() for p in protected))
                      or not legitimate_input(physical))
    if denied:
        events.append((event, str(args[0])))
        raise AssertionError('import attempted an effect before startup: ' + event)
sys.addaudithook(audit)
"""

_IMPORT_PROBE = _IMPORT_GUARD + """
import van_gateway.app as gateway
assert Path(gateway.__file__).resolve() == (root / 'backend/van_gateway/app.py').resolve()
assert events == [], events
"""


def _source_module_inputs(root, fixture):
    # Bound to actual tracked source modules, not a home-prefix exemption.
    tracked = subprocess.check_output(['git', 'ls-files', '-z', '--',
        'backend/van_gateway', 'trading/vati', 'services', 'hermes', 'tools',
        'registries/production_activation_gates.json'], cwd=root).decode().split('\0')
    manifest = fixture / 'source-module-inputs.json'
    manifest.write_text(json.dumps([str((root / path).resolve()) for path in tracked
        if ((path.endswith('.py') and not any(part in {'tests', '__pycache__'} for part in Path(path).parts))
            or path == 'registries/production_activation_gates.json')]))
    return str(manifest)



@pytest.mark.parametrize("working_directory", [".", "backend"])
@pytest.mark.parametrize("explicit_database", [False, True])
def test_importing_the_deployed_entry_point_never_opens_storage(tmp_path, working_directory, explicit_database):
    root = Path(__file__).resolve().parents[2]
    # A fresh interpreter also catches import-time effects hidden by pytest's cache.
    probe = _IMPORT_PROBE
    environment = {**os.environ, "PYTHONPATH": str(root / "backend") + os.pathsep + str(root),
                   "PYTHONDONTWRITEBYTECODE": "1"}
    environment.pop("VAN_DATABASE_PATH", None)
    if explicit_database:
        environment["VAN_DATABASE_PATH"] = str(tmp_path / "never-created" / "db.sqlite3")
    result = subprocess.run(
        [sys.executable, "-B", "-c", probe, str(root), _source_module_inputs(root, tmp_path)], cwd=root / working_directory,
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


def _owned_checkout_under_modeled_home(tmp_path):
    """Real source import through an owned nested-home layout; HOME stays real."""
    actual = Path(__file__).resolve().parents[2]
    home = tmp_path / 'SOURCE-runner-home'
    root = home / 'work' / 'Van'
    (root / 'backend').mkdir(parents=True)
    (root / 'backend' / 'van_gateway').symlink_to(actual / 'backend' / 'van_gateway', target_is_directory=True)
    return actual, home, root


def test_actual_source_import_beneath_modeled_home_is_read_only_not_private_state(tmp_path):
    actual, home, root = _owned_checkout_under_modeled_home(tmp_path)
    environment = {**os.environ, 'PYTHONPATH': str(root / 'backend') + os.pathsep + str(root),
                   'PYTHONDONTWRITEBYTECODE': '1'}
    original_home = environment.get('HOME')
    environment.pop('VAN_DATABASE_PATH', None)
    source_inputs = _source_module_inputs(actual, tmp_path)
    for cwd in (root, root / 'backend'):
        result = subprocess.run([sys.executable, '-B', '-c', _IMPORT_PROBE, str(root), source_inputs],
            cwd=cwd, env=environment, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stdout + result.stderr
    assert root.is_relative_to(home)
    assert environment.get('HOME') == original_home  # No HOME fallback/repurposing.
    assert not (root / 'data').exists() and not (root / 'backend' / 'data').exists()


@pytest.mark.parametrize('effect', ['write', 'sqlite', 'mkdir', 'network', 'process', 'dotenv',
    'private-state', 'source-looking-private-state', 'protected-root', 'protected-backend'])
def test_import_probe_keeps_effects_private_inputs_and_both_data_trees_forbidden(tmp_path, effect):
    actual, home, root = _owned_checkout_under_modeled_home(tmp_path)
    private = home / 'private-state.json'
    private.write_text('SOURCE private canary; never owner state')
    dotenv = root / '.env'
    dotenv.write_text('SOURCE synthetic env canary')
    untracked = root / 'backend' / 'private_state.py'
    untracked.write_text('SOURCE private state with a misleading module suffix')
    for name in ('data', 'backend/data'):
        (root / name).mkdir()
        (root / name / 'original').write_bytes(b'SOURCE protected canary')
    target = tmp_path / 'never-created-effect'
    actions = {
        'write': 'open(target, "w")',
        'sqlite': '__import__("sqlite3").connect(target)',
        'mkdir': 'os.mkdir(target)',
        'network': '__import__("socket").socket().connect(("127.0.0.1", 9))',
        'process': '__import__("subprocess").Popen([sys.executable, "-c", "raise SystemExit(0)"])',
        'dotenv': 'open(root / ".env").read()',
        'private-state': 'open(root.parents[1] / "private-state.json").read()',
        'source-looking-private-state': 'open(root / "backend/private_state.py").read()',
        'protected-root': 'open(root / "data/original").read()',
        'protected-backend': 'open(root / "backend/data/original").read()',
    }
    # This exercises the same hook as the original four real entrypoint cases.
    probe = _IMPORT_GUARD + '\ntarget = sys.argv[3]\ntry:\n    ' + actions[effect] + '\nexcept AssertionError:\n    assert len(events) == 1\nelse:\n    raise AssertionError("SOURCE forbidden effect/input was accepted")\n'
    environment = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
    result = subprocess.run([sys.executable, '-B', '-c', probe, str(root), _source_module_inputs(actual, tmp_path), str(target)],
        cwd=root, env=environment, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not target.exists()
    assert private.read_text() == 'SOURCE private canary; never owner state'
    assert dotenv.read_text() == 'SOURCE synthetic env canary'
    for name in ('data', 'backend/data'):
        assert (root / name / 'original').read_bytes() == b'SOURCE protected canary'
