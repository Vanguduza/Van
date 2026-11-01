"""Existing installer/admin registration plus actual HTTP enrollment consumers."""
from __future__ import annotations

import base64
from dataclasses import replace
import hashlib
import json

import pytest

from attestation_fixtures import signed_attestation_chain
from test_device_proof_enforcement import client, _settings, INTERNAL, INGRESS
from test_mtls_pki import csr_for
from test_bootstrap_recovery_api import _headers, _encoded, _attest
from test_owner_device_binding import _attestation, _keypair
from test_owner_device_reenrollment_recovery import NativeFixture
from van_gateway.browser.stream_grants import generate_signing_key
from van_gateway.config import get_settings
from van_gateway.mtls.pki import DeviceCA, init_ca

pytestmark = pytest.mark.asyncio
INSTALLER = "reenrollment-test-installer-0123456789"
HEADERS = {"X-Van-Internal-Token": INSTALLER}


@pytest.fixture(autouse=True)
def installer_settings(_settings, monkeypatch):
    monkeypatch.setenv("VAN_DEVICE_ENROLMENT_TOKEN", INSTALLER)
    monkeypatch.setenv("VAN_SCHEDULER_ENABLED", "false")
    get_settings.cache_clear()


async def original(app, tmp_path):
    pem, _ = _keypair()
    ticket = await app.state.auth.create_pairing_ticket("original")
    await app.state.auth.pair_device(ticket.token,"original-phone","s"*32,pem)
    token, challenge = await app.state.owner_device_bindings.create_bootstrap_token()
    binding = await app.state.owner_device_bindings.bind(token=token,device_id="original-phone",public_key_pem=pem,
        attestation_extension=_attestation(challenge.encode()),attestation_chain_verified=True)
    ca_dir = tmp_path / "reenrollment-ca"
    init_ca(ca_dir)
    app.state.device_ca = DeviceCA(ca_dir)
    native = NativeFixture()
    app.state.strategy_promotions.control = native
    signing = generate_signing_key("reenrollment-connectivity-fixture")
    app.state.connectivity_config.private_pem = signing.private_pem
    app.state.connectivity_config.kid = signing.kid
    request = dict(reason="lost handset",operation_id="replacement-http-original-0001",
        expected_binding_id=binding.binding_id,expected_bound_at_ms=binding.bound_at_ms,gateway_url="https://gateway.example")
    return request, native


async def test_scoped_original_http_recovery_then_actual_attestation_pair_and_status(client,tmp_path):
    ac, app = client
    request, native = await original(app,tmp_path)
    wrong = await ac.post("/v1/devices/rebind",json=request,headers={"X-Van-Internal-Token":INTERNAL})
    assert wrong.status_code == 403
    assert await app.state.owner_device_bindings.active()
    pending = await ac.post("/v1/devices/rebind",json=request,headers=HEADERS)
    assert pending.status_code == 200,pending.text
    assert pending.json()["phase"] == "RETIRING" and pending.json()["envelope"] is None
    assert pending.headers["cache-control"] == "no-store"
    calls = len(native.calls)
    before = [dict(row) for row in await app.state.store.fetchall("SELECT * FROM owner_device_reenrollments")]
    read = await ac.get("/v1/devices/rebindings/"+request["operation_id"],headers=HEADERS)
    assert read.status_code == 200 and len(native.calls) == calls
    assert [dict(row) for row in await app.state.store.fetchall("SELECT * FROM owner_device_reenrollments")] == before
    ordinary = await ac.post("/v1/devices/bootstrap/create",json={},headers=HEADERS)
    assert ordinary.status_code == 409 and ordinary.json()["detail"] == "device_retirement_pending"
    native.available = True
    ready = await ac.post("/v1/devices/rebind",json=request,headers=HEADERS)
    assert ready.status_code == 200,ready.text
    response = ready.json()
    assert response["phase"] == "READY"
    assert response["expires_at_ms"] == pending.json()["expires_at_ms"]
    assert (await ac.post("/v1/devices/rebind",json={**request,"reason":"different"},headers=HEADERS)).status_code == 409
    # The signed original replacement envelope feeds the existing public consumers.
    payload = response["envelope"]["payload"]
    pem,key = _keypair()
    extension = _attestation(payload["attestation_challenge"].encode())
    chain,root = signed_attestation_chain(pem,extension)
    bindings = app.state.owner_device_bindings
    bindings.policy = replace(bindings.policy,allowed_root_fingerprints=frozenset({root}))
    enrollment = dict(token=payload["bootstrap_token"],device_id="replacement-phone",public_key_pem=pem,
        attestation_extension_b64=base64.b64encode(extension).decode(),
        attestation_chain_b64=[base64.b64encode(c).decode() for c in chain])
    await _attest(ac,enrollment,key)
    pair = dict(pairing_token=payload["pairing_token"],device_id="replacement-phone",device_secret="r"*32,
        public_key_pem=pem,device_access_token="a"*32)
    body = _encoded(pair)
    paired = await ac.post("/v1/devices/pair",content=body,
        headers=_headers(key,"/v1/devices/pair","replacement-phone",body))
    assert paired.status_code == 200,paired.text
    status = await ac.post("/v1/devices/provisioning-status",json={"bootstrap_token":payload["bootstrap_token"]},headers=HEADERS)
    assert status.status_code == 200,status.text
    assert status.json()["state"] == "NEEDS_TLS_CERTIFICATE"
    assert status.json()["steps"]["binding"] is True and status.json()["steps"]["pairing"] is True
    owner_headers = {"X-Van-Ingress-Token":INGRESS,"X-Van-Device-Token":"a"*32}
    csr,_ = csr_for("replacement-phone")
    certificate_body = _encoded({"csr_pem":csr})
    certificate = await ac.post("/v1/devices/tls-certificate",content=certificate_body,
        headers=_headers(key,"/v1/devices/tls-certificate","replacement-phone",certificate_body,authenticated=owner_headers))
    assert certificate.status_code == 200,certificate.text
    session_body = _encoded({"open_request_id":"replacement-session-original-0001"})
    session = await ac.post("/v1/session/open",content=session_body,
        headers=_headers(key,"/v1/session/open","replacement-phone",session_body,authenticated=owner_headers))
    assert session.status_code == 200,session.text
    transport = await ac.post("/v1/devices/provisioning-status",json={"bootstrap_token":payload["bootstrap_token"]},headers=HEADERS)
    assert transport.json()["state"] == "NEEDS_SESSION_ADMISSION"
    assert transport.json()["steps"]["tls_certificate"] is True
    # HTTP opening alone never claims actual transport/owner/Hermes acceptance.
    assert transport.json()["steps"]["session_admitted"] is False
    assert transport.json()["owner_e2e_verified"] is False
    current = await bindings.active()
    replay = await ac.post("/v1/devices/rebind",json=request,headers=HEADERS)
    assert replay.status_code == 200 and replay.json()["envelope"] == response["envelope"]
    assert (await bindings.active()).binding_id == current.binding_id


@pytest.mark.parametrize("update", [{"operation_id":None,"expected_binding_id":"wrong"},
    {"expected_binding_id":"wrong"},{"expected_bound_at_ms":0}])
async def test_missing_or_stale_original_preconditions_refuse_without_retiring(client,tmp_path,update):
    ac,app = client
    request,_ = await original(app,tmp_path)
    response = await ac.post("/v1/devices/rebind",json={**request,**update},headers=HEADERS)
    assert response.status_code == 409,response.text
    assert (await app.state.owner_device_bindings.active()).binding_id == request["expected_binding_id"]
    assert not await app.state.store.fetchall("SELECT * FROM device_certificate_retirements")


async def test_normal_revoke_attempts_native_retirement_despite_ca_error(client,tmp_path,monkeypatch):
    ac,app=client
    request,native=await original(app,tmp_path)
    native.available=True
    def unavailable(*args,**kwargs):
        raise OSError("synthetic CA owner unavailable")
    monkeypatch.setattr(app.state.device_ca,"revoke_device",unavailable)
    response=await ac.post("/v1/devices/original-phone/revoke",headers=HEADERS)
    assert response.status_code==200,response.text
    assert response.json()["certificate_retirement_phase"]=="UNKNOWN"
    assert response.json()["native_authority_revocation"]["phase"]=="APPLIED"
    assert (await app.state.owner_device_bindings.for_device("original-phone")).status.value=="REVOKED"
    denied=await ac.post("/v1/devices/bootstrap/create",json={},headers=HEADERS)
    assert denied.status_code==409 and denied.json()["detail"]=="device_retirement_pending"
