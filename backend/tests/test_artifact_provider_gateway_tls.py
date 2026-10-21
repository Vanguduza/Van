"""Actual listener composition, without claiming a live provider effect.

Only the admission handler is replaced by a recording observer. The app's
middleware, TLS handshake, peer certificate plumbing and machine/device gates
are production code. No fixture receipt qualifies a deployment or handset.
"""
import hashlib

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from test_mtls_machine_ingress import machine_gateway  # noqa: F401
from test_mtls_live import pki_dir, client_ctx, pair, auth_headers  # noqa: F401
from van_gateway.auth.provider_transport import ProviderTransportBinding, ProviderPrincipal


async def provider_client(f, tmp_path):
    key = ec.generate_private_key(ec.SECP256R1())
    name = "artifact-provider-test-only"
    csr = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    ).sign(key, hashes.SHA256()).public_bytes(serialization.Encoding.PEM).decode()
    issued = f.app.state.device_ca.issue_client(csr, name)
    certificate, private = tmp_path / "provider.crt", tmp_path / "provider.key"
    certificate.write_text(issued.certificate_pem)
    private.write_bytes(key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    der = x509.load_pem_x509_certificate(certificate.read_bytes()).public_bytes(serialization.Encoding.DER)
    binding = ProviderTransportBinding(certificate_sha256=hashlib.sha256(der).hexdigest(),
        provider_identity="fixture-provider", provider="ORACLE_OWNER_ARCHIVE",
        owner_namespace="fixture_owner", project_namespace="fixture_project")
    return client_ctx(f.pki, certificate, private), binding


async def test_actual_app_claim_lane_requires_certificate_and_never_assigns_phone_identity(machine_gateway, tmp_path, monkeypatch):
    f = machine_gateway
    context, binding = await provider_client(f, tmp_path)
    current = [binding]
    monkeypatch.setattr(f.app.state.artifact_provider_auth, "bindings_provider", lambda: current)
    observed = []

    async def record(**kwargs):
        observed.append(kwargs)
        return {"admitted": False, "claimed": False, "fixture_observer_only": True}

    monkeypatch.setattr(f.app.state.browser_artifacts, "introspect", record)
    path = "/v1/browser/artifact-provider/admissions/bfadmission_test/claim"
    body = {"signed_admission": "test-only-not-authority-" + "x" * 32}
    async with httpx.AsyncClient(verify=client_ctx(f.pki), base_url=f"https://127.0.0.1:{f.port}") as client:
        denied = await client.post(path, json=body)
        assert denied.status_code == 403 and "certificate" in denied.json()["detail"]
    assert not observed
    async with httpx.AsyncClient(verify=context, base_url=f"https://127.0.0.1:{f.port}") as client:
        accepted_transport = await client.post(path, json=body)
        assert accepted_transport.status_code == 200, accepted_transport.text
        assert accepted_transport.json()["admitted"] is False
        assert len(observed) == 1
        principal = observed[0]["principal"]
        assert isinstance(principal, ProviderPrincipal)
        assert principal.certificate_sha256 == binding.certificate_sha256
        assert (principal.owner_namespace, principal.project_namespace) == ("fixture_owner", "fixture_project")
        phone = await pair(f.app, "provider-lane-owner-test")
        owner_request = await client.post("/v1/session/open", json={}, headers=auth_headers(phone))
        assert owner_request.status_code == 403
        assert owner_request.json()["detail"] == "client_certificate_device_mismatch"
        current.clear()
        revoked = await client.post(path, json=body)
        assert revoked.status_code == 503
        assert len(observed) == 1


async def test_owner_and_legacy_machine_tokens_cannot_bypass_provider_tls(machine_gateway):
    f = machine_gateway
    from httpx import ASGITransport
    path = "/v1/browser/artifact-provider/admissions/bfadmission_test/introspect"
    phone = await pair(f.app, "provider-http-owner-test")
    async with httpx.AsyncClient(transport=ASGITransport(app=f.app), base_url="http://fixture") as client:
        response = await client.post(path, json={"signed_admission": "x" * 64}, headers={
            **auth_headers(phone), "X-Van-Internal-Token": "machine-issuer-token-0123456789abcdef",
            "X-Forwarded-Proto": "https", "X-Van-Provider-Principal": "fixture-provider"})
    assert response.status_code == 403
    assert response.json()["detail"] == "artifact_provider_transport_required"
