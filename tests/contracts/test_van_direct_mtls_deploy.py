"""The deployed shape of the phone's direct mutual-TLS link (backend/van_gateway/mtls)."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENABLE = ROOT / "tools/runtime/enable_van_mtls.sh"


def test_the_unit_runs_both_listeners_from_one_process():
    service = (ROOT / "deploy/systemd/van-gateway.service").read_text(encoding="utf-8")
    exec_start = [line for line in service.splitlines() if line.startswith("ExecStart=")]
    assert exec_start == ["ExecStart=%h/.local/share/van/venv/bin/python -m van_gateway.mtls.serve"]
    # The CA record (issued.json) is rewritten on enrolment and revocation.
    assert "ReadWritePaths=%h/.local/share/van " in service


def test_enabling_never_recreates_the_ca_and_never_prints_its_key():
    script = ENABLE.read_text(encoding="utf-8")
    assert 'if [[ ! -f "$MTLS_DIR/ca.crt" ]]; then\n  pki init' in script
    assert "ca.key" not in script
    assert 'base64 -w0 "$MTLS_DIR/ca.crt"' in script


def test_enabling_refuses_a_privileged_port(tmp_path):
    result = subprocess.run(["bash", str(ENABLE), "--san", "IP:203.0.113.7", "--port", "443"],
                            capture_output=True, text=True, env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"})
    assert result.returncode == 2
    assert "port_must_be_unprivileged:443" in result.stderr


INSTALL = ROOT / "tools/runtime/install_van_gateway_service.sh"


def _stage(tmp_path):
    """Run the real installer up to and including its pre-flight, against a throwaway home."""
    import os
    import sys

    from cryptography.fernet import Fernet

    state, config = tmp_path / "state", tmp_path / "config"
    (state / "venv/bin").mkdir(parents=True)
    # A wrapper, not a symlink: a symlinked venv python loses its pyvenv.cfg and its packages.
    wrapper = state / "venv/bin/python"
    wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
    wrapper.chmod(0o755)
    config.mkdir()
    (config / "google-workspace.env").write_text(f"VAN_GOOGLE_TOKEN_FERNET_KEY={Fernet.generate_key().decode()}\n")
    (config / "gateway.env").write_text(
        f"VAN_DATABASE_PATH={tmp_path}/db/van.sqlite3\nVAN_HERMES_BASE_URL=http://hermes.invalid\n")
    env = {"HOME": str(tmp_path), "PATH": os.environ["PATH"], "VAN_STATE_ROOT": str(state),
           "VAN_CONFIG_ROOT": str(config), "VAN_INSTALL_STAGE_ONLY": "1"}
    return subprocess.run(["bash", str(INSTALL)], capture_output=True, text=True, env=env, timeout=300), state


def test_the_installer_ships_a_runtime_that_starts(tmp_path):
    result, state = _stage(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS van_gateway_preflight" in result.stdout
    runtime = state / "runtime"
    # accounts.py imports `commander` from <runtime>/trading at startup.
    assert (runtime / "trading/commander/accounts.py").is_file()
    assert not (runtime / "trading/tests").exists()
    assert (runtime / "backend/van_gateway/mtls/serve.py").is_file()
