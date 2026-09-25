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
    assert not (state / "runtime").exists(), "stage-only must never replace the live runtime"
    runtime = state / "runtime.staged"
    # accounts.py imports `commander` from <runtime>/trading at startup.
    assert (runtime / "trading/commander/accounts.py").is_file()
    assert not (runtime / "trading/tests").exists()
    assert (runtime / "backend/van_gateway/mtls/serve.py").is_file()


def _committed_gateway() -> dict:
    props = {}
    for line in (ROOT / "android/van-gateway.properties").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            props[key.strip()] = value.strip()
    return props


def test_the_app_ships_configured_for_the_direct_link():
    """android/van-gateway.properties is what every build pins unless overridden."""
    import base64
    from datetime import datetime, timezone
    from urllib.parse import urlsplit

    from cryptography import x509
    from cryptography.hazmat.primitives.asymmetric import ec

    props = _committed_gateway()
    url = urlsplit(props["VAN_GATEWAY_BASE_URL"])
    assert url.scheme == "https" and url.hostname and url.port, props["VAN_GATEWAY_BASE_URL"]
    assert url.path in ("", "/")
    ca = x509.load_pem_x509_certificate(base64.b64decode(props["VAN_GATEWAY_CA_PEM_B64"], validate=True))
    assert ca.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    assert isinstance(ca.public_key(), ec.EllipticCurvePublicKey) and ca.public_key().curve.name == "secp256r1"
    assert ca.not_valid_before_utc <= datetime.now(timezone.utc) < ca.not_valid_after_utc
    assert "PRIVATE KEY" not in (ROOT / "android/van-gateway.properties").read_text(encoding="utf-8")
    gradle = (ROOT / "android/app/build.gradle.kts").read_text(encoding="utf-8")
    assert 'rootProject.file("van-gateway.properties")' in gradle


def test_the_phone_and_the_gateway_agree_on_the_routes_that_need_no_certificate():
    import re
    import sys

    sys.path.insert(0, str(ROOT / "backend"))
    from van_gateway.mtls.transport import _NO_CERT_POSTS

    kotlin = (ROOT / "android/app/src/main/java/com/dial/van/security/MutualTlsScope.kt").read_text(encoding="utf-8")
    block = kotlin[kotlin.index("PRE_ENROLMENT_PATHS"):]
    block = block[: block.index(")")]
    assert set(re.findall(r'"(/v1/[^"]+)"', block)) == set(_NO_CERT_POSTS)
