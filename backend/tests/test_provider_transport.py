"""Provider authority comes from the exact TLS certificate and current target pin."""
from __future__ import annotations

import asyncio
import hashlib
import json
import ssl
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import uvicorn
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from fastapi import FastAPI, HTTPException, Request

from van_gateway.auth.provider_transport import (
    PURPOSE, STATE_PRINCIPAL, ProviderPrincipal, ProviderTransportAuthenticator,
    ProviderTransportBinding, ProviderTransportMiddleware, is_artifact_provider_route,
    is_https_artifact_provider_route, require_provider_target,
    load_artifact_transport_bindings,
)
from van_gateway.mtls.pki import DeviceCA, init_ca
from van_gateway.mtls.transport import EXTENSION, PeerCertificateH11Protocol, build_ssl_context

PATH = "/v1/browser/artifact-provider/admissions/bfa_exact/claim"


def certificate(*, expired=False, future=False, ca=False, client=True):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "provider-fixture")])
    now = datetime.now(timezone.utc)
    leaf = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now + timedelta(hours=1) if future else now - timedelta(days=2))
        .not_valid_after(now - timedelta(hours=1) if expired else now + timedelta(days=2))
        .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH if client else ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(key, hashes.SHA256()))
    return leaf.public_bytes(serialization.Encoding.DER)


def binding(der):
    return ProviderTransportBinding(hashlib.sha256(der).hexdigest(), "oracle-artifact-service",
        "ORACLE_OWNER_ARCHIVE", "owner_exact", "project_exact")


def scope(der=None, **changes):
    value = {"type": "http", "scheme": "https", "method": "POST", "path": PATH,
        "headers": [], "query_string": b"", "extensions": {EXTENSION: {"client_cert_der": der}}}
    value.update(changes)
    return value


def test_exact_tls_pin_yields_configured_scope_without_owner_identity():
    der = certificate()
    expected = binding(der)
    principal = ProviderTransportAuthenticator(lambda: [expected]).authenticate_scope(scope(der))
    assert principal == ProviderPrincipal(**expected.__dict__)
    assert not hasattr(principal, "device_id")
    require_provider_target(principal, provider=expected.provider, provider_identity=expected.provider_identity,
        owner_namespace=expected.owner_namespace, project_namespace=expected.project_namespace)


@pytest.mark.parametrize("changed", [{"provider": "VEKL_OWNER_CANDIDATE_INGRESS"},
    {"provider_identity": "different-provider"}, {"owner_namespace": "other-owner"},
    {"project_namespace": "other-project"}])
def test_certificate_never_widens_to_different_provider_or_namespace(changed):
    der = certificate()
    expected = binding(der)
    principal = ProviderTransportAuthenticator(lambda: [expected]).authenticate_scope(scope(der))
    target = dict(provider=expected.provider, provider_identity=expected.provider_identity,
        owner_namespace=expected.owner_namespace, project_namespace=expected.project_namespace)
    target.update(changed)
    with pytest.raises(HTTPException) as denied:
        require_provider_target(principal, **target)
    assert denied.value.status_code == 403


@pytest.mark.parametrize("changes", [{"extensions": {}}, {"extensions": {EXTENSION: {}}},
    {"extensions": {EXTENSION: {"client_cert_der": "caller-certificate"}}},
    {"scheme": "http"}, {"query_string": b"provider=oracle"}])
def test_headers_and_owner_state_cannot_replace_tls_certificate(changes):
    der = certificate()
    claimed = scope(None, headers=[(b"x-forwarded-proto", b"https"), (b"x-provider-identity", b"oracle-artifact-service"),
        (b"x-van-internal-token", b"browser-stream-bearer"), (b"authorization", b"Bearer admission")],
        state={"van_mtls_device_id": "owner", STATE_PRINCIPAL: ProviderPrincipal(**binding(der).__dict__)})
    claimed.update(changes)
    with pytest.raises(HTTPException) as denied:
        ProviderTransportAuthenticator(lambda: [binding(der)]).authenticate_scope(claimed)
    assert denied.value.status_code == 403


@pytest.mark.parametrize("certificate_args", [{"expired": True}, {"future": True}, {"ca": True}, {"client": False}])
def test_pin_does_not_bypass_certificate_validity_or_leaf_usage(certificate_args):
    der = certificate(**certificate_args)
    with pytest.raises(HTTPException) as denied:
        ProviderTransportAuthenticator(lambda: [binding(der)]).authenticate_scope(scope(der))
    assert denied.value.status_code == 403 and denied.value.detail == "artifact_provider_certificate_invalid"


def test_different_certificate_with_same_subject_is_not_the_pinned_principal():
    der, other = certificate(), certificate()
    with pytest.raises(HTTPException) as denied:
        ProviderTransportAuthenticator(lambda: [binding(der)]).authenticate_scope(scope(other))
    assert denied.value.detail == "artifact_provider_certificate_not_bound"


def test_malformed_der_is_refused_even_when_pin_matches():
    der = b"unparseable-certificate"
    with pytest.raises(HTTPException) as denied:
        ProviderTransportAuthenticator(lambda: [binding(der)]).authenticate_scope(scope(der))
    assert denied.value.detail == "artifact_provider_certificate_invalid"


@pytest.mark.parametrize("changes", [{"certificate_sha256": "*"}, {"owner_namespace": "*"},
    {"project_namespace": "../project"}, {"provider": "arbitrary"}, {"purpose": "device_enrolment"},
    {"provider_identity": " oracle "}])
def test_misconfigured_targets_are_unavailable(changes):
    der = certificate()
    with pytest.raises(HTTPException) as denied:
        ProviderTransportAuthenticator(lambda: [replace(binding(der), **changes)]).authenticate_scope(scope(der))
    assert denied.value.status_code == 503


def test_unconfigured_and_ambiguous_certificate_targets_have_no_authority():
    der = certificate()
    for values in (None, [], [binding(der), replace(binding(der), project_namespace="another_project")]):
        with pytest.raises(HTTPException) as denied:
            ProviderTransportAuthenticator(lambda: values).authenticate_scope(scope(der))
        assert denied.value.status_code == 503


async def test_removed_binding_is_rechecked_in_handler_and_cannot_use_cached_middleware_state():
    der = certificate()
    active = [binding(der)]
    auth = ProviderTransportAuthenticator(lambda: active)
    request = Request(scope(der))
    request.scope["state"] = {STATE_PRINCIPAL: await auth.authenticate(request)}
    active.clear()
    with pytest.raises(HTTPException) as denied:
        await auth.authenticate(request)
    assert denied.value.status_code == 503


@pytest.mark.parametrize("changes", [{"method": "GET"}, {"type": "websocket"},
    {"path": PATH + "/extra"}, {"path": PATH.replace("claim", "mint")},
    {"path": PATH.replace("bfa_exact", "*")}, {"path": "/v1/browser/interactive-sessions"}])
def test_private_machine_lane_has_no_prefix_or_method_expansion(changes):
    assert not is_artifact_provider_route(scope(**changes))
    assert not is_https_artifact_provider_route(scope(**changes))


def test_public_tls_lane_requires_actual_https_scope():
    assert is_artifact_provider_route(scope(scheme="http"))
    assert not is_https_artifact_provider_route(scope(scheme="http", headers=[(b"x-forwarded-proto", b"https")]))


def config_row(der):
    bound = binding(der)
    return {"provider": bound.provider, "origin": "https://provider.example", "ca_file": "/unopened/ca.crt",
        "client_cert_file": "/unopened/client.crt", "client_key_file": "/unopened/client.key",
        "provider_identity": bound.provider_identity, "capability_receipt_sha256": "1" * 64,
        "owner_namespace": bound.owner_namespace, "project_namespace": bound.project_namespace,
        "provider_principal_sha256": bound.certificate_sha256}


async def test_public_binding_reload_does_not_open_private_keys_and_removal_immediately_refuses(tmp_path):
    der = certificate()
    config = tmp_path / "provider.json"
    config.write_text(json.dumps({"schema_version": 1, "providers": [config_row(der)], "source_clients": {},
        "signer": {"private_key_file": "/unopened/admission.key"}}))
    assert load_artifact_transport_bindings(config) == (binding(der),)
    auth = ProviderTransportAuthenticator(lambda: load_artifact_transport_bindings(config))
    request = Request(scope(der))
    assert (await auth.authenticate(request)).certificate_sha256 == binding(der).certificate_sha256
    config.write_text(json.dumps({"schema_version": 1, "providers": []}))
    with pytest.raises(HTTPException) as removed:
        await auth.authenticate(request)
    assert removed.value.status_code == 503
    config.unlink()
    with pytest.raises(HTTPException) as missing:
        await auth.authenticate(request)
    assert missing.value.status_code == 503


@pytest.mark.parametrize("content", [b"not json", b"[]", b'{"schema_version":1,"providers":[],"unknown":true}',
    b'{"schema_version":1,"providers":[],"providers":[]}', b'{"schema_version":1,"providers":{}}', b'{"schema_version":1,"providers":[{}]}',
    b'{"schema_version":true,"providers":[]}', b'{"schema_version":2,"providers":[]}',
    b"[" * 1100 + b"]" * 1100, b"x" * 65537])
def test_loader_bounded_invalid_configuration_fails_closed_without_path_leak(tmp_path, content):
    config = tmp_path / "sensitive-provider-config.json"
    config.write_bytes(content)
    auth = ProviderTransportAuthenticator(lambda: load_artifact_transport_bindings(config))
    with pytest.raises(HTTPException) as denied:
        auth.authenticate_scope(scope(certificate()))
    assert denied.value.status_code == 503
    assert denied.value.detail == "artifact_provider_transport_configuration_invalid"
    assert str(config) not in denied.value.detail


@pytest.mark.parametrize("changes", [{"provider_principal_sha256": None}, {"owner_namespace": "*"},
    {"project_namespace": 7}, {"certificate_sha256": "0" * 64}])
def test_loader_refuses_incomplete_or_claimed_transport_bindings(tmp_path, changes):
    der = certificate()
    row = config_row(der)
    row.update(changes)
    config = tmp_path / "provider.json"
    config.write_text(json.dumps({"schema_version": 1, "providers": [row]}))
    with pytest.raises(ValueError, match="artifact_provider_transport_configuration_invalid"):
        load_artifact_transport_bindings(config)


async def test_middleware_denies_before_route_and_leaves_other_routes_alone():
    app = FastAPI()
    reached = []
    @app.post(PATH)
    async def claim():
        reached.append("claim")
        return {"claimed": True}
    @app.get("/unrelated")
    async def unrelated(): return {"owner_route": True}
    wrapped = ProviderTransportMiddleware(app, ProviderTransportAuthenticator())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=wrapped), base_url="https://test") as client:
        denied = await client.post(PATH, headers={"Authorization": "Bearer browser-stream-token"})
        assert denied.status_code == 503 and not reached
        assert (await client.get("/unrelated")).json() == {"owner_route": True}


async def test_actual_local_tls_handshake_establishes_provider_principal(tmp_path):
    """Throwaway local fixtures prove the protocol extension, not a claimed header."""
    pki = tmp_path / "pki"
    init_ca(pki)
    ca = DeviceCA(pki)
    ca.issue_server("IP:127.0.0.1")
    provider_pki = tmp_path / "provider-pki"
    init_ca(provider_pki)
    provider_ca = DeviceCA(provider_pki)
    key = ec.generate_private_key(ec.SECP256R1())
    csr = (x509.CertificateSigningRequestBuilder().subject_name(x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "provider-fixture")])).sign(key, hashes.SHA256()))
    issued = provider_ca.issue_client(csr.public_bytes(serialization.Encoding.PEM).decode(), "provider-fixture")
    leaf = x509.load_pem_x509_certificate(issued.certificate_pem.encode())
    bound = binding(leaf.public_bytes(serialization.Encoding.DER))
    cert_file, key_file = tmp_path / "provider.crt", tmp_path / "provider.key"
    cert_file.write_text(issued.certificate_pem)
    key_file.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    auth = ProviderTransportAuthenticator(lambda: [bound])
    app = FastAPI()
    @app.post(PATH)
    async def claim(request: Request):
        principal = await auth.authenticate(request)
        return {"certificate_sha256": principal.certificate_sha256, "provider": principal.provider,
            "purpose": principal.purpose, "owner_identity": request.scope.get("state", {}).get("van_mtls_device_id")}
    app.add_middleware(ProviderTransportMiddleware, authenticator=auth)
    config = uvicorn.Config(app, host="127.0.0.1", port=0, http=PeerCertificateH11Protocol,
        ssl_context_factory=lambda _config, _default: build_ssl_context(pki, machine_client_ca_file=provider_pki / "ca.crt"),
        proxy_headers=False, log_level="error", lifespan="off")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server._serve())
    try:
        async with asyncio.timeout(10):
            while not server.started:
                if task.done(): await task
                await asyncio.sleep(0.01)
        port = server.servers[0].sockets[0].getsockname()[1]
        context = ssl.create_default_context(cafile=str(pki / "ca.crt"))
        async with httpx.AsyncClient(verify=context, base_url=f"https://127.0.0.1:{port}") as client:
            refused = await client.post(PATH, headers={"X-Provider-Identity": bound.provider_identity})
            assert refused.status_code == 403
        context.load_cert_chain(cert_file, key_file)
        async with httpx.AsyncClient(verify=context, base_url=f"https://127.0.0.1:{port}") as client:
            admitted = await client.post(PATH)
            assert admitted.status_code == 200, admitted.text
            assert admitted.json() == {"certificate_sha256": bound.certificate_sha256,
                "provider": bound.provider, "purpose": PURPOSE, "owner_identity": None}
    finally:
        server.should_exit = True
        await task
