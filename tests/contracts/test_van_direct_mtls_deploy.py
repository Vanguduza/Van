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
