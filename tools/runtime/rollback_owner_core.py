#!/usr/bin/env python3
"""Review or apply a same-schema, same-configuration gateway rollback; never restore owner data."""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import time

from preflight_owner_core import effective_environment


def schema_version(runtime: Path) -> int:
    tree = ast.parse((runtime / "backend/van_gateway/storage/db.py").read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "SCHEMA_VERSION" for target in node.targets):
            value = ast.literal_eval(node.value)
            if type(value) is int:
                return value
    raise ValueError("schema_version_unavailable")


def runtime_verified(runtime: Path, metadata: dict, expected: str) -> bool:
    hashes = metadata.get("runtime_sha256", {})
    if not (re.fullmatch(r"[0-9a-f]{40}", expected) and metadata.get("repository_sha") == expected
            and metadata.get("source_clean") is True and hashes):
        return False
    for name, digest in hashes.items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or hashlib.sha256((runtime / relative).read_bytes()).hexdigest() != digest:
            return False
    return True


def inspect(state: Path, config: Path, expected: str) -> dict:
    previous, current = state / "runtime.previous", state / "runtime"
    metadata = json.loads((previous / "DEPLOYED_SOURCE.json").read_text())
    checks = {"previous_clean_exact_source_and_files": runtime_verified(previous, metadata, expected),
              "previous_unit_present": (previous / "van-gateway.service").is_file(),
              "same_locked_dependencies": (previous / "backend/requirements.lock").read_bytes() == (current / "backend/requirements.lock").read_bytes()}
    interpreter = Path(metadata.get("runtime_python", ""))
    lock_sha = hashlib.sha256((previous / "backend/requirements.lock").read_bytes()).hexdigest()
    selected = state.resolve() / "venvs" / lock_sha / "bin/python"
    checks["previous_immutable_interpreter_available"] = (
        interpreter.is_absolute() and interpreter == selected and interpreter.is_file()
        and metadata.get("requirements_sha256") == lock_sha
        and (previous / "RUNTIME_PYTHON_PATH").read_text().strip() == str(interpreter)
        and (interpreter.parent.parent / "VAN_REQUIREMENTS.lock").read_bytes()
            == (previous / "backend/requirements.lock").read_bytes())
    config_hashes = metadata.get("configuration_sha256", {})
    checks["unchanged_configurations"] = bool(config_hashes) and all(
        name in {"google-workspace.env", "gateway.env", "owner-core.env", "trading-commander.env"}
        and hashlib.sha256((config / name).read_bytes()).hexdigest() == digest for name, digest in config_hashes.items())
    checks["same_database_schema_contract"] = schema_version(previous) == schema_version(current)
    values = effective_environment(config / "google-workspace.env", config / "gateway.env",
                                   config / "trading-commander.env", config / "owner-core.env")
    database = Path(values["VAN_DATABASE_PATH"]).resolve()
    checks["persistent_database_outside_runtime"] = database.is_relative_to(state.resolve()) and not database.is_relative_to(current.resolve())
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as db:
        observed = db.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations").fetchone()[0]
    checks["running_database_schema_matches_previous"] = observed == schema_version(previous)
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--config-root", type=Path, required=True)
    parser.add_argument("--expected-previous-sha", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    applied = False
    mutation_started = False
    phase = "PLAN"
    try:
        checks = inspect(args.state_root, args.config_root, args.expected_previous_sha)
        ok = all(checks.values())
        if ok and args.apply:
            # Invoke only inside the admitted gateway deployment recipe, under its
            # deployment lock with owner ingress quiesced. Never touch VATI units/DB.
            mutation_started = True
            phase = "STOP_REQUESTED"
            subprocess.run(["systemctl", "--user", "stop", "van-gateway.service"], check=True)
            failed = args.state_root / ("runtime.rollback-from-" + str(time.time_ns()))
            os.replace(args.state_root / "runtime", failed)
            phase = "CURRENT_RUNTIME_ARCHIVED"
            applied = True
            os.replace(args.state_root / "runtime.previous", args.state_root / "runtime")
            phase = "PREVIOUS_RUNTIME_SELECTED"
            unit = Path.home() / ".config/systemd/user/van-gateway.service"
            shutil.copy2(args.state_root / "runtime/van-gateway.service", unit)
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
            subprocess.run(["systemctl", "--user", "restart", "van-gateway.service"], check=True)
            phase = "RESTARTED_HEALTH_UNVERIFIED"
    except (OSError, ValueError, KeyError, sqlite3.Error, subprocess.SubprocessError):
        checks = {"rollback_inputs_or_operation_failed": False}
        ok = False
    print(json.dumps({"status": "ROLLBACK_FAILED_RECONCILE" if mutation_started and not ok else "ROLLBACK_RESTARTED_HEALTH_UNVERIFIED" if applied else "PLAN_READY" if ok else "BLOCKED",
                      "checks": checks, "applied": applied, "mutation_started": mutation_started,
                      "phase": phase, "database_restored": False,
                      "live_qualified": False, "deployment_authority_verified": False}))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
