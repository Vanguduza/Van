"""Machine callbacks over the real public TLS listener retain canonical authority."""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
import uvicorn
from cryptography import x509
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from test_automation_worker_runtime import build
from test_mtls_live import client_ctx, pki_dir, pair, auth_headers
from van_gateway.app import create_app
from van_gateway.browser.interactive_models import Viewport
from van_gateway.browser.producer_service import credential_principal
from van_gateway.browser.stream_grants import generate_signing_key
from van_gateway.config import get_settings
from van_gateway.mtls.serve import _loopback_config, _public_config
from van_gateway.mtls.transport import is_https_machine_route, mtls_device_id

WORKER = "machine-worker-token-0123456789abcdef"
AUTOMATION = "machine-management-token-0123456789abcdef"
STREAM = "machine-stream-token-0123456789abcdef"
CONTROL = "machine-control-token-0123456789abcdef"
ISSUER = "machine-issuer-token-0123456789abcdef"
INGRESS = "mtls-ingress-token-0123456789"
PID = "producer_machine_ingress_0123456789"


@pytest_asyncio.fixture
async def machine_gateway(tmp_path, pki_dir, monkeypatch):
    canonical = tmp_path / "canonical"
    canonical.mkdir()
    _worker, store, body = await build(canonical)
    signing_key = tmp_path / "stream.pem"
    signing_key.write_text(generate_signing_key("tls-machine-test").private_pem)
    env = {
        "VAN_DATABASE_PATH": store.path,
        "VAN_HERMES_BASE_URL": "http://hermes.invalid",
        "VAN_GOOGLE_TOKEN_FERNET_KEY": Fernet.generate_key().decode(),
        "VAN_DEVICE_SECRET_FERNET_KEY": Fernet.generate_key().decode(),
        "VAN_INGRESS_TOKEN": INGRESS,
        "VAN_INTERNAL_CONTROL_TOKEN": "",
        "VAN_INTERNAL_CONTROL_SCOPED_TOKENS": (
            f"automation_worker:{WORKER};automation:{AUTOMATION};browser:{ISSUER};"
            f"browser_stream_producer:{STREAM};browser_stream_producer:{CONTROL}"),
        "VAN_AUTOMATION_ENABLED": "true",
        "VAN_AUTOMATION_GRANT_SIGNING_KEY": "worker-test-signing-key",
        "VAN_AUTOMATION_WORKER_ENDPOINT": "https://127.0.0.1/v1/automation/worker/step",
        "VAN_BROWSER_STREAM_SIGNING_KEY_FILE": str(signing_key),
        "VAN_BROWSER_STREAM_SIGNAL_URL": "https://stream.example/rtc",
        "VAN_BROWSER_CONTROL_PROXY_BINDINGS": json.dumps({credential_principal(CONTROL): ["van-trading-core"]}),
        "VAN_MTLS_ENABLED": "true", "VAN_MTLS_DIR": str(pki_dir),
        "VAN_MTLS_BIND": "127.0.0.1", "VAN_MTLS_PORT": "0",
    }
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    app = create_app()
    identities = []
    @app.middleware("http")
    async def capture_machine_identity(request, call_next):
        response = await call_next(request)
        if request.url.path == "/v1/automation/worker/step" or "producer" in request.url.path:
            identities.append((request.url.path, mtls_device_id(request.scope),
                getattr(request.state, "van_device_id", None)))
        return response
    try:
        async with app.router.lifespan_context(app):
            server = uvicorn.Server(_public_config(app, get_settings()))
            task = asyncio.create_task(server._serve())
            while not server.started:
                if task.done():
                    await task
                await asyncio.sleep(0.02)
            port = server.servers[0].sockets[0].getsockname()[1]
            try:
                yield SimpleNamespace(app=app, port=port, pki=pki_dir, store=store,
                    body=body, identities=identities)
            finally:
                server.should_exit = True
                await task
    finally:
        get_settings.cache_clear()


async def test_worker_https_machine_credential_and_mac_reach_current_canonical_fences(machine_gateway):
    f = machine_gateway
    async with httpx.AsyncClient(verify=client_ctx(f.pki), base_url=f"https://127.0.0.1:{f.port}") as client:
        request = await f.body("__admit__")
        accepted = await client.post("/v1/automation/worker/step", json=request.model_dump(mode="json"),
            headers={"X-Van-Internal-Token": WORKER})
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["admitted"] is True
        row = await f.store.fetchone("SELECT state FROM automation_worker_steps WHERE run_id='run' AND step_id='__admit__'")
        assert row["state"] == "COMPLETED"
        assert f.identities[-1][1:] == (None, None)

        current = await f.body("__admit__")
        await f.store.execute("UPDATE devices SET revoked_at_unix=1 WHERE device_id='dev-owner-1'")
        refused = await client.post("/v1/automation/worker/step", json=current.model_dump(mode="json"),
            headers={"X-Van-Internal-Token": WORKER})
        assert refused.status_code == 403
        assert "revoked" in json.dumps(refused.json()).lower()
        nonce = await f.store.fetchone("SELECT use_count FROM automation_run_nonces WHERE grant_id=?", (current.grant.grant_id,))
        assert nonce["use_count"] == 0


async def test_real_loopback_forwarded_https_cannot_admit_worker_effect(machine_gateway):
    f = machine_gateway
    config = _loopback_config(f.app, SimpleNamespace(loopback_host="127.0.0.1", loopback_port=0))
    config.lifespan = "off"
    server = uvicorn.Server(config)
    task = asyncio.create_task(server._serve())
    try:
        while not server.started:
            if task.done():
                await task
            await asyncio.sleep(0.02)
        port = server.servers[0].sockets[0].getsockname()[1]
        request = await f.body("__admit__")
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as client:
            response = await client.post("/v1/automation/worker/step",
                json=request.model_dump(mode="json"), headers={
                    "X-Van-Internal-Token": WORKER, "X-Forwarded-Proto": "https",
                    "X-Forwarded-Host": "127.0.0.1"})
        assert response.status_code == 403, response.text
        assert await f.store.fetchone("SELECT * FROM automation_worker_steps") is None
        nonce = await f.store.fetchone("SELECT use_count FROM automation_run_nonces WHERE grant_id=?",
            (request.grant.grant_id,))
        assert nonce["use_count"] == 0
    finally:
        server.should_exit = True
        await task


async def test_worker_https_rejects_wrong_scope_mac_and_owner_credentials(machine_gateway):
    f = machine_gateway
    phone = await pair(f.app, "machine-test-owner")
    request = await f.body("__admit__")
    payload = request.model_dump(mode="json")
    async with httpx.AsyncClient(verify=client_ctx(f.pki), base_url=f"https://127.0.0.1:{f.port}") as client:
        for token in (AUTOMATION, STREAM, ISSUER):
            response = await client.post("/v1/automation/worker/step", json=payload,
                headers={"X-Van-Internal-Token": token})
            assert response.status_code == 403
            assert response.json()["required_scope"] == "automation_worker"
        response = await client.post("/v1/automation/worker/step", json=payload, headers=auth_headers(phone))
        assert response.status_code == 403
        tampered = dict(payload)
        nonce, mac = tampered["capability_grant"].split(".")
        tampered["capability_grant"] = nonce + "." + ("0" if mac[0] != "0" else "1") + mac[1:]
        response = await client.post("/v1/automation/worker/step", json=tampered,
            headers={"X-Van-Internal-Token": WORKER})
        assert response.status_code == 403
        assert "GRANT_SIGNATURE_INVALID" in json.dumps(response.json())
        assert await f.store.fetchone("SELECT * FROM automation_worker_steps") is None
        stored = await f.store.fetchone("SELECT use_count FROM automation_run_nonces WHERE grant_id=?", (request.grant.grant_id,))
        assert stored["use_count"] == 0


async def test_machine_lane_is_exact_and_owner_paths_still_need_device_certificate(machine_gateway):
    f = machine_gateway
    phone = await pair(f.app, "machine-test-owner")
    async with httpx.AsyncClient(verify=client_ctx(f.pki), base_url=f"https://127.0.0.1:{f.port}") as client:
        for path, method in (("/v1/automation/worker/step", "GET"),
                ("/v1/automation/worker/step/extra", "POST"),
                ("/v1/automation/workflows", "POST"),
                ("/v1/browser/interactive-sessions", "POST"),
                (f"/v1/browser/stream-producer/{PID}/unknown", "POST"),
                ("/v1/session/open", "POST")):
            response = await client.request(method, path, json={}, headers={
                **auth_headers(phone), "X-Van-Internal-Token": WORKER})
            assert response.status_code == 403
            assert response.json()["detail"] == "client_certificate_required"


async def test_browser_producer_https_uses_machine_binding_without_owner_identity(machine_gateway):
    f = machine_gateway
    await f.app.state.browser.broker.register_profile(profile_alias="public_research")
    session = await f.app.state.interactive_sessions.create(owner_device_id="dev-owner-1",
        profile_alias="public_research", viewport=Viewport(width=540, height=960, device_scale_factor=1))
    grant, _ = await f.app.state.browser_stream_grants.mint(session_id=session.session_id,
        device_id="dev-owner-1", profile_alias="public_research",
        scope=["webrtc.signal", "browser.view", "browser.owner_input"],
        max_width=540, max_height=960, max_fps=60)
    async with httpx.AsyncClient(verify=client_ctx(f.pki), base_url=f"https://127.0.0.1:{f.port}") as client:
        payload = {"stream_grant": grant, "producer_session_id": PID}
        for token in (WORKER, ISSUER):
            response = await client.post("/v1/browser/stream-producer/redeem", json=payload,
                headers={"X-Van-Internal-Token": token})
            assert response.status_code == 403
        response = await client.post("/v1/browser/stream-producer/redeem", json=payload,
            headers={"X-Van-Internal-Token": STREAM})
        assert response.status_code == 200, response.text
        assert response.json()["authenticated_principal_kind"] == "STREAM_GRANT_BEARER"
        response = await client.post(f"/v1/browser/stream-producer/{PID}/authority", json={},
            headers={"X-Van-Internal-Token": STREAM})
        assert response.status_code == 200
        assert response.json()["session_id"] == session.session_id
        call = {"caller_common_name": "van-trading-core", "operation": "query_dom",
            "session_id": session.session_id, "target_id": "tab", "task_id": "missing",
            "lease_id": session.control_lease_id, "lease_generation": session.control_generation}
        response = await client.post("/v1/browser/control-producer/validate-call", json=call,
            headers={"X-Van-Internal-Token": CONTROL})
        assert response.status_code == 404 and response.json()["detail"] == "control_grant_unknown"
        assert all(mtls is None and owner is None for _, mtls, owner in f.identities)


async def test_optional_service_certificate_never_becomes_a_machine_owner_identity(machine_gateway, tmp_path):
    f = machine_gateway
    key = ec.generate_private_key(ec.SECP256R1())
    service_name = "native-machine-service"
    csr = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, service_name)])
    ).sign(key, hashes.SHA256()).public_bytes(serialization.Encoding.PEM).decode()
    issued = f.app.state.device_ca.issue_client(csr, service_name)
    cert, private = tmp_path / "service.crt", tmp_path / "service.key"
    cert.write_text(issued.certificate_pem)
    private.write_bytes(key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    assert await f.store.fetchone("SELECT device_id FROM devices WHERE device_id=?", (service_name,)) is None
    request = await f.body("__admit__")
    phone = await pair(f.app, "certificate-test-owner")
    async with httpx.AsyncClient(verify=client_ctx(f.pki, cert, private),
            base_url=f"https://127.0.0.1:{f.port}") as client:
        response = await client.post("/v1/automation/worker/step", json=request.model_dump(mode="json"),
            headers={"X-Van-Internal-Token": WORKER})
        assert response.status_code == 200 and response.json()["admitted"] is True
        assert f.identities[-1][1:] == (None, None)
        response = await client.post("/v1/session/open", json={}, headers=auth_headers(phone))
        assert response.status_code == 403
        assert response.json()["detail"] == "client_certificate_device_mismatch"


@pytest.mark.parametrize("scheme,method,path", [("http", "POST", "/v1/automation/worker/step"),
    ("https", "GET", "/v1/automation/worker/step"),
    ("https", "POST", "/v1/automation/worker/step/extra"),
    ("https", "POST", "/v1/browser/stream-producer/short/authority"),
    ("https", "POST", "/v1/browser/control-producer/grants/extra")])
def test_machine_gate_does_not_accept_forwarded_https_methods_or_prefixes(scheme, method, path):
    assert not is_https_machine_route({"type": "http", "scheme": scheme, "method": method,
        "path": path, "headers": [(b"x-forwarded-proto", b"https")]})

