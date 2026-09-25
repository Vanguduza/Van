"""The direct mutual-TLS link, driven over real sockets.

The public listener is started exactly as `van_gateway.mtls.serve` configures it, on an
ephemeral loopback port, with a throwaway device CA. Every claim here is about what a client
on the network can and cannot do, so nothing is asserted through the ASGI app directly
except the one test that shows the loopback listener is unchanged.
"""

from __future__ import annotations

import asyncio
import json
import ssl
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
import uvicorn
from cryptography import x509
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from websockets.asyncio.client import connect as ws_connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

from van_gateway.app import create_app
from van_gateway.config import get_settings
from van_gateway.mtls.pki import DeviceCA, init_ca
from van_gateway.mtls.serve import _public_config

INGRESS = "mtls-ingress-token-0123456789"
INTERNAL = "mtls-internal-token-0123456789"
ENROLMENT = "mtls-enrolment-token-0123456789"


@pytest.fixture
def pki_dir(tmp_path) -> Path:
    d = tmp_path / "tls"
    init_ca(d)
    DeviceCA(d).issue_server("IP:127.0.0.1")
    return d


@pytest_asyncio.fixture
async def gateway(tmp_path, pki_dir, monkeypatch):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "mtls.sqlite3"))
    monkeypatch.setenv("VAN_HERMES_BASE_URL", "http://hermes.invalid")
    monkeypatch.setenv("VAN_GOOGLE_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", INGRESS)
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", INTERNAL)
    monkeypatch.setenv("VAN_DEVICE_ENROLMENT_TOKEN", ENROLMENT)
    monkeypatch.setenv("VAN_MTLS_ENABLED", "true")
    monkeypatch.setenv("VAN_MTLS_DIR", str(pki_dir))
    monkeypatch.setenv("VAN_MTLS_BIND", "127.0.0.1")
    monkeypatch.setenv("VAN_MTLS_PORT", "0")
    get_settings.cache_clear()
    settings = get_settings()
    app = create_app()
    assert app.state.device_ca is not None
    async with app.router.lifespan_context(app):
        server = uvicorn.Server(_public_config(app, settings))
        task = asyncio.create_task(server._serve())
        while not server.started:
            await asyncio.sleep(0.02)
        port = server.servers[0].sockets[0].getsockname()[1]
        try:
            yield app, port, pki_dir
        finally:
            server.should_exit = True
            await task
    get_settings.cache_clear()


def client_ctx(pki_dir: Path, cert: Path | None = None, key: Path | None = None, *, tls12: bool = False) -> ssl.SSLContext:
    ctx = ssl.create_default_context(cafile=str(pki_dir / "ca.crt"))
    if tls12:
        ctx.maximum_version = ssl.TLSVersion.TLSv1_2
    if cert is not None:
        ctx.load_cert_chain(str(cert), str(key))
    return ctx


async def pair(app, label: str):
    ticket = await app.state.auth.create_pairing_ticket(label)
    return await app.state.auth.pair_device(ticket.token, label, "s" * 32, "PEM", label)


async def enrol(port: int, pki_dir: Path, device, out: Path) -> tuple[Path, Path]:
    """What the phone does: key in its keystore, CSR naming itself, POST with no client cert."""
    key = ec.generate_private_key(ec.SECP256R1())
    csr = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, device.device.device_id)])
    ).sign(key, hashes.SHA256()).public_bytes(serialization.Encoding.PEM).decode()
    async with httpx.AsyncClient(verify=client_ctx(pki_dir), base_url=f"https://127.0.0.1:{port}") as c:
        r = await c.post("/v1/devices/tls-certificate", json={"csr_pem": csr}, headers={
            "X-Van-Ingress-Token": INGRESS, "X-Van-Device-Token": device.access_token})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["device_id"] == device.device.device_id
    assert body["ca_pem"] == (pki_dir / "ca.crt").read_text()
    cert_path, key_path = out / f"{device.device.device_id}.crt", out / f"{device.device.device_id}.key"
    cert_path.write_text(body["certificate_pem"])
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
    return cert_path, key_path


def auth_headers(device) -> dict:
    return {"X-Van-Ingress-Token": INGRESS, "X-Van-Device-Token": device.access_token}


async def test_only_tls13_and_only_the_device_ca(gateway, tmp_path):
    app, port, pki_dir = gateway
    with pytest.raises(httpx.ConnectError):
        async with httpx.AsyncClient(verify=client_ctx(pki_dir, tls12=True)) as c:
            await c.get(f"https://127.0.0.1:{port}/health")

    # A client certificate from a different CA is rejected in the handshake.
    rogue = tmp_path / "rogue"
    init_ca(rogue)
    key = ec.generate_private_key(ec.SECP256R1())
    csr = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "owner-phone")])).sign(key, hashes.SHA256())
    issued = DeviceCA(rogue).issue_client(csr.public_bytes(serialization.Encoding.PEM).decode(), "owner-phone")
    (rogue / "c.crt").write_text(issued.certificate_pem)
    (rogue / "c.key").write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                    serialization.NoEncryption()))
    with pytest.raises(httpx.HTTPError):
        async with httpx.AsyncClient(verify=client_ctx(pki_dir, rogue / "c.crt", rogue / "c.key")) as c:
            await c.get(f"https://127.0.0.1:{port}/health", headers={"X-Van-Ingress-Token": INGRESS})


async def test_without_a_certificate_only_pre_enrolment_routes_answer(gateway):
    app, port, pki_dir = gateway
    async with httpx.AsyncClient(verify=client_ctx(pki_dir), base_url=f"https://127.0.0.1:{port}") as c:
        r = await c.get("/health", headers={"X-Van-Ingress-Token": INGRESS})
        assert (r.status_code, r.json()["detail"]) == (403, "client_certificate_required")
        r = await c.post("/v1/commands", json={}, headers={"X-Van-Ingress-Token": INGRESS})
        assert r.json()["detail"] == "client_certificate_required"
        r = await c.post("/v1/devices/pair", json={})
        assert r.status_code != 403  # reaches the pairing handler (which refuses the empty body itself)
    with pytest.raises(InvalidStatus):
        async with ws_connect(f"wss://127.0.0.1:{port}/v1/session/ws?van_session_id=x&device_token=y",
                              ssl=client_ctx(pki_dir)):
            pass


async def test_enrolled_phone_holds_a_two_way_session_socket(gateway, tmp_path):
    app, port, pki_dir = gateway
    phone = await pair(app, "owner-phone")
    cert, key = await enrol(port, pki_dir, phone, tmp_path)
    ctx = client_ctx(pki_dir, cert, key)
    async with httpx.AsyncClient(verify=ctx, base_url=f"https://127.0.0.1:{port}") as c:
        assert (await c.get("/health", headers={"X-Van-Ingress-Token": INGRESS})).status_code == 200
        opened = await c.post("/v1/session/open", json={}, headers=auth_headers(phone))
        assert opened.status_code == 200, opened.text
        session_id = opened.json()["van_session_id"]

    url = f"wss://127.0.0.1:{port}/v1/session/ws?van_session_id={session_id}&device_token={phone.access_token}"
    async with ws_connect(url, ssl=ctx) as ws:
        await ws.send(json.dumps({"message_id": "m-1"}))  # upstream: an envelope missing fields
        reply = json.loads(await asyncio.wait_for(ws.recv(), 5))  # downstream: the gateway answers
        assert reply == {"accepted": False, "refusal": "session_envelope_invalid"}


async def test_a_certificate_only_speaks_for_its_own_device(gateway, tmp_path):
    app, port, pki_dir = gateway
    phone = await pair(app, "owner-phone")
    other = await pair(app, "other-phone")
    cert, key = await enrol(port, pki_dir, phone, tmp_path)
    ctx = client_ctx(pki_dir, cert, key)
    async with httpx.AsyncClient(verify=ctx, base_url=f"https://127.0.0.1:{port}") as c:
        r = await c.post("/v1/session/open", json={}, headers=auth_headers(other))
        assert (r.status_code, r.json()["detail"]) == (403, "client_certificate_device_mismatch")
    # The other device's own, valid session (opened on the loopback listener) is the only
    # thing a stolen token would need; holding this phone's certificate must not be enough.
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://loopback") as c:
        opened = await c.post("/v1/session/open", json={}, headers=auth_headers(other))
        assert opened.status_code == 200, opened.text
        session_id = opened.json()["van_session_id"]
    with pytest.raises((InvalidStatus, ConnectionClosed)):
        async with ws_connect(
            f"wss://127.0.0.1:{port}/v1/session/ws?van_session_id={session_id}&device_token={other.access_token}",
            ssl=ctx,
        ) as ws:
            await asyncio.wait_for(ws.recv(), 5)


async def test_revocation_takes_effect_on_the_next_connection(gateway, tmp_path):
    app, port, pki_dir = gateway
    phone = await pair(app, "owner-phone")
    cert, key = await enrol(port, pki_dir, phone, tmp_path)
    ctx = client_ctx(pki_dir, cert, key)
    async with httpx.AsyncClient(verify=ctx, base_url=f"https://127.0.0.1:{port}") as c:
        assert (await c.get("/health", headers={"X-Van-Ingress-Token": INGRESS})).status_code == 200
    revoked = await asyncio.to_thread(app.state.device_ca.revoke_device, phone.device.device_id)
    assert revoked == 1
    async with httpx.AsyncClient(verify=ctx, base_url=f"https://127.0.0.1:{port}") as c:
        r = await c.get("/health", headers={"X-Van-Ingress-Token": INGRESS})
        assert (r.status_code, r.json()["detail"]) == (403, "client_certificate_not_admitted")


async def test_revoking_the_device_revokes_its_certificate(gateway, tmp_path):
    app, port, pki_dir = gateway
    phone = await pair(app, "owner-phone")
    await enrol(port, pki_dir, phone, tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://loopback") as c:
        r = await c.post(f"/v1/devices/{phone.device.device_id}/revoke", headers={"X-Van-Internal-Token": ENROLMENT})
    assert r.status_code == 200, r.text
    assert r.json()["revoked_client_certificates"] == 1


async def test_the_loopback_listener_is_unchanged(gateway):
    app, _port, _pki = gateway
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8787") as c:
        r = await c.get("/health", headers={"X-Van-Ingress-Token": INGRESS})
    assert r.status_code == 200


def _free_port() -> int:
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_the_unit_entry_point_serves_both_listeners_and_stops_on_sigterm(tmp_path, pki_dir):
    """What deploy/systemd/van-gateway.service runs, as a process. The fixtures above build the
    public listener in-process; this is the only test that executes `serve._run` itself."""
    import os
    import signal
    import subprocess
    import sys
    import time

    loopback, public = _free_port(), _free_port()
    env = {
        **os.environ,
        "VAN_DATABASE_PATH": str(tmp_path / "proc.sqlite3"),
        "VAN_HERMES_BASE_URL": "http://hermes.invalid",
        "VAN_GOOGLE_TOKEN_FERNET_KEY": Fernet.generate_key().decode(),
        "VAN_DEVICE_SECRET_FERNET_KEY": Fernet.generate_key().decode(),
        "VAN_INGRESS_TOKEN": INGRESS,
        "VAN_MTLS_ENABLED": "true",
        "VAN_MTLS_DIR": str(pki_dir),
        "VAN_MTLS_BIND": "127.0.0.1",
        "VAN_MTLS_PORT": str(public),
        "VAN_LOOPBACK_PORT": str(loopback),
    }
    proc = subprocess.Popen([sys.executable, "-m", "van_gateway.mtls.serve"], env=env,
                            cwd=Path(__file__).resolve().parents[1],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + 30
        while True:
            try:
                r = httpx.get(f"http://127.0.0.1:{loopback}/health", headers={"X-Van-Ingress-Token": INGRESS}, timeout=1)
                p = httpx.get(f"https://127.0.0.1:{public}/health", headers={"X-Van-Ingress-Token": INGRESS},
                              verify=client_ctx(pki_dir), timeout=1)
                break
            except httpx.TransportError:
                assert proc.poll() is None, proc.stdout.read().decode()
                assert time.monotonic() < deadline, "listeners never came up"
                time.sleep(0.2)
        assert r.status_code == 200
        assert (p.status_code, p.json()["detail"]) == (403, "client_certificate_required")
    finally:
        proc.send_signal(signal.SIGTERM)
        output = proc.communicate(timeout=20)[0].decode()
    # uvicorn re-raises the captured SIGTERM once shutdown completes, as the plain `uvicorn`
    # CLI the unit ran before did; systemd counts that as a clean stop.
    assert proc.returncode in (0, -signal.SIGTERM), output
    assert "Application shutdown complete." in output
    for port in (loopback, public):
        with pytest.raises(httpx.TransportError):
            httpx.get(f"http://127.0.0.1:{port}/health", timeout=1)
