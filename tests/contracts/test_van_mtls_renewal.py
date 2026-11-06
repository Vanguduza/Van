"""Exercise server renewal with real temporary certificates and mocked host effects."""

import datetime as dt
import os
from pathlib import Path
import subprocess
import sys

import pytest
from cryptography import x509

from van_gateway.mtls import pki


ROOT = Path(__file__).resolve().parents[2]


def _executable(path, source):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)
    path.chmod(0o755)


@pytest.mark.parametrize("remaining", [None, 825, 15, -5])
def test_same_san_renewal_keeps_ca_and_existing_issuance_record(tmp_path, monkeypatch, remaining):
    state, config, binaries = tmp_path / "state with space", tmp_path / "config", tmp_path / "mock-bin"
    config.mkdir()
    directory = state / "mtls"
    pki.init_ca(directory)
    ca = pki.DeviceCA(directory)
    if remaining is not None:
        if remaining < 0:
            with monkeypatch.context() as patch:
                past = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=10)
                patch.setattr(pki, "_now", lambda: past)
                ca.issue_server("IP:203.0.113.7", days=5)
        else:
            ca.issue_server("IP:203.0.113.7", days=remaining)
    (directory / "server.san").write_text("IP:203.0.113.7\n")
    record = '{"certificates": {"existing": {"device_id": "existing-phone"}}}\n'
    (directory / "issued.json").write_text(record)
    original_ca = (directory / "ca.crt").read_bytes()
    original_key = (directory / "ca.key").read_bytes()
    original_server = (directory / "server.crt").read_bytes() if remaining is not None else None
    owner_configuration = "OWNER_CONFIGURATION=preserve-this-line\n"
    (config / "gateway.env").write_text(owner_configuration)
    (state / "runtime").mkdir()
    (state / "runtime/backend").symlink_to(ROOT / "backend", target_is_directory=True)
    mock = tmp_path / "python-wrapper.py"
    mock.write_text("""
import os, sys
if sys.argv[1:] == ['-']:
    source = sys.stdin.read()
    if 'socket.create_connection' in source:
        print('MOCKED_HOST_TLS_PROBE')
    else:
        sys.path.insert(0, os.getcwd())
        exec(compile(source, '<renewal-check>', 'exec'), {'__name__': '__main__'})
else:
    os.execv(sys.executable, [sys.executable, *sys.argv[1:]])
""")
    _executable(state / "venv/bin/python", f'#!/bin/sh\nexec "{sys.executable}" "{mock}" "$@"\n')
    for name, status in (("systemctl", 0), ("sleep", 0), ("sudo", 1)):
        _executable(binaries / name, f"#!/bin/sh\nexit {status}\n")
    env = {**os.environ, "VAN_STATE_ROOT": str(state), "VAN_CONFIG_ROOT": str(config),
           "PATH": str(binaries) + os.pathsep + os.environ["PATH"]}
    command = ["bash", str(ROOT / "tools/runtime/enable_van_mtls.sh"), "--san", "IP:203.0.113.7",
               "--bind", "127.0.0.1"]
    first = subprocess.run(command, env=env, capture_output=True, text=True, timeout=30)
    assert first.returncode == 0, first.stdout + first.stderr
    current = (directory / "server.crt").read_bytes()
    if remaining == 825:
        assert current == original_server
        assert "van_server_certificate_kept" in first.stdout
    else:
        assert current != original_server
        certificate = x509.load_pem_x509_certificate(current)
        assert certificate.not_valid_after_utc > dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=800)
    again = subprocess.run(command, env=env, capture_output=True, text=True, timeout=30)
    assert again.returncode == 0, again.stdout + again.stderr
    assert (directory / "server.crt").read_bytes() == current
    assert (directory / "ca.crt").read_bytes() == original_ca
    assert (directory / "ca.key").read_bytes() == original_key
    assert (directory / "issued.json").read_text() == record
    assert (config / "gateway.env").read_text().startswith(owner_configuration)
