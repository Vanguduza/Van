"""Run the real rollback helper on isolated files/SQLite, with only service effects mocked."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/runtime/rollback_owner_core.py"
SHA = "a" * 40


@pytest.fixture
def setup(tmp_path):
    state, config, home = tmp_path / "state", tmp_path / "config", tmp_path / "home"
    config.mkdir()
    (home / ".config/systemd/user").mkdir(parents=True)
    for name in ("runtime", "runtime.previous"):
        runtime = state / name
        (runtime / "backend/van_gateway/storage").mkdir(parents=True)
        (runtime / "backend/van_gateway/storage/db.py").write_text("SCHEMA_VERSION = 34\n")
        (runtime / "backend/requirements.lock").write_text("same-synthetic-lock\n")
        (runtime / "van-gateway.service").write_text(name + "-synthetic-unit\n")
    database = state / "owner.sqlite3"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY)")
        db.execute("INSERT INTO schema_migrations VALUES(34)")
        db.execute("CREATE TABLE owner_record(value TEXT)")
        db.execute("INSERT INTO owner_record VALUES('preserve-owner-data')")
    (config / "gateway.env").write_text("")
    (config / "google-workspace.env").write_text("")
    (config / "owner-core.env").write_text(f'VAN_DATABASE_PATH="{database}"\n')
    previous = state / "runtime.previous"
    lock_sha = hashlib.sha256((previous / "backend/requirements.lock").read_bytes()).hexdigest()
    interpreter = state / "venvs" / lock_sha / "bin/python"
    interpreter.parent.mkdir(parents=True)
    interpreter.write_text("synthetic-interpreter")
    interpreter.parent.parent.joinpath("VAN_REQUIREMENTS.lock").write_bytes((previous / "backend/requirements.lock").read_bytes())
    (previous / "RUNTIME_PYTHON_PATH").write_text(str(interpreter) + "\n")
    metadata = {"repository_sha": SHA, "source_clean": True,
                "runtime_python": str(interpreter), "requirements_sha256": lock_sha,
                "runtime_sha256": {str(path.relative_to(previous)): hashlib.sha256(path.read_bytes()).hexdigest()
                                   for path in previous.rglob("*") if path.is_file()},
                "configuration_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in config.iterdir()}}
    (previous / "DEPLOYED_SOURCE.json").write_text(json.dumps(metadata))
    binaries = tmp_path / "bin"
    binaries.mkdir()
    systemctl = binaries / "systemctl"
    systemctl.write_text("#!/bin/sh\nexit 0\n")
    systemctl.chmod(0o755)
    env = {**os.environ, "HOME": str(home), "PATH": str(binaries) + os.pathsep + os.environ["PATH"]}
    return state, config, database, home, systemctl, env


def run(setup, *extra):
    state, config, _, _, _, env = setup
    return subprocess.run([sys.executable, str(TOOL), "--state-root", str(state), "--config-root", str(config),
                           "--expected-previous-sha", SHA, *extra], env=env, capture_output=True, text=True, timeout=30)


def test_default_rollback_is_a_read_only_plan_and_preserves_owner_database(setup):
    state, _, database, *_ = setup
    before = database.read_bytes()
    result = run(setup)
    assert result.returncode == 0, result.stdout + result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["status"] == "PLAN_READY" and receipt["applied"] is False
    assert receipt["deployment_authority_verified"] is receipt["live_qualified"] is False
    assert database.read_bytes() == before and (state / "runtime.previous").is_dir()


@pytest.mark.parametrize("defect", ["schema", "runtime", "configuration", "dependencies"])
def test_unsafe_rollback_refuses_before_service_or_file_changes(setup, defect):
    state, config, database, *_ = setup
    if defect == "schema":
        (state / "runtime/backend/van_gateway/storage/db.py").write_text("SCHEMA_VERSION = 35\n")
    elif defect == "runtime":
        (state / "runtime.previous/backend/van_gateway/storage/db.py").write_text("SCHEMA_VERSION = 33\n")
    elif defect == "configuration":
        (config / "gateway.env").write_text("VAN_INGRESS_TOKEN=changed-synthetic-value\n")
    else:
        (state / "runtime/backend/requirements.lock").write_text("changed-synthetic-dependency\n")
    before = database.read_bytes()
    result = run(setup, "--apply")
    receipt = json.loads(result.stdout)
    assert result.returncode == 2 and receipt["status"] == "BLOCKED"
    assert receipt["mutation_started"] is False and (state / "runtime.previous").is_dir()
    assert database.read_bytes() == before


def test_same_contract_rollback_swaps_only_gateway_files_not_authority_data(setup):
    state, _, database, home, _, _ = setup
    before = database.read_bytes()
    result = run(setup, "--apply")
    assert result.returncode == 0, result.stdout + result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["status"] == "ROLLBACK_RESTARTED_HEALTH_UNVERIFIED"
    assert receipt["applied"] is True and receipt["database_restored"] is False
    assert (state / "runtime/van-gateway.service").read_text() == "runtime.previous-synthetic-unit\n"
    assert (home / ".config/systemd/user/van-gateway.service").read_text() == "runtime.previous-synthetic-unit\n"
    assert len(list(state.glob("runtime.rollback-from-*"))) == 1
    assert database.read_bytes() == before


def test_failed_service_stop_reports_started_operation_without_false_no_effect(setup):
    state, _, _, _, systemctl, _ = setup
    systemctl.write_text("#!/bin/sh\nexit 1\n")
    result = run(setup, "--apply")
    receipt = json.loads(result.stdout)
    assert result.returncode == 2 and receipt["status"] == "ROLLBACK_FAILED_RECONCILE"
    assert receipt["mutation_started"] is True and receipt["phase"] == "STOP_REQUESTED"
    assert receipt["applied"] is False and (state / "runtime.previous").is_dir()
