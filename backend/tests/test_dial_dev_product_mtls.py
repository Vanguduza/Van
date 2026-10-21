"""Real TLS boundary plus production route refusals for the DEC-056 product proxy."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
from pathlib import Path
import ssl
import threading

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
import httpx
import pytest

from van_gateway.dial_dev.client import DialDevClient, DialDevUnavailable
from van_gateway.dial_dev.config import DialDevConfig
from van_gateway.config import Settings


def _ca(name):
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=1), critical=True)
            .sign(key, hashes.SHA256()))
    return key, cert


def _leaf(name, ca_key, ca_cert, *, server=False):
    key = ec.generate_private_key(ec.SECP256R1())
    now = datetime.now(timezone.utc)
    builder = (x509.CertificateBuilder()
               .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)]))
               .issuer_name(ca_cert.subject).public_key(key.public_key())
               .serial_number(x509.random_serial_number())
               .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(days=1))
               .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
               .add_extension(x509.ExtendedKeyUsage([
                   ExtendedKeyUsageOID.SERVER_AUTH if server else ExtendedKeyUsageOID.CLIENT_AUTH,
               ]), critical=False))
    if server:
        builder = builder.add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
            critical=False,
        )
    return key, builder.sign(ca_key, hashes.SHA256())


def _write_pair(directory, name, key, cert):
    certificate = directory / f"{name}.crt"
    private_key = directory / f"{name}.key"
    certificate.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    private_key.write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    private_key.chmod(0o600)
    return certificate, private_key


@pytest.fixture
def tls_gateway(tmp_path):
    ca_key, ca_cert = _ca("product-ca")
    ca = tmp_path / "product-ca.crt"
    ca.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    server_cert, server_key = _write_pair(tmp_path, "gateway", *_leaf("gateway", ca_key, ca_cert, server=True))
    client_cert, client_key = _write_pair(tmp_path, "van", *_leaf("van", ca_key, ca_cert))
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            peer = self.connection.getpeercert()
            seen.append((self.path, self.headers.get("Authorization"), peer))
            body = b"data: {\"projection_revision\":\"rev1\"}\n\n" if self.path.endswith("events") else b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream" if self.path.endswith("events") else "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_verify_locations(cafile=str(ca))
    context.load_cert_chain(server_cert, server_key)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    token = tmp_path / "product.token"
    token.write_text("test-product-token-0123456789abcdef0123456789")
    config = DialDevConfig(
        enabled=True, base_url=f"https://127.0.0.1:{server.server_port}",
        token_file=str(token), tls_ca_file=str(ca), tls_client_cert_file=str(client_cert),
        tls_client_key_file=str(client_key), timeout_s=1,
    )
    yield config, seen, ca_key, ca_cert, tmp_path
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


@pytest.mark.asyncio
async def test_actual_read_and_sse_present_product_certificate_and_bearer(tls_gateway):
    config, seen, *_ = tls_gateway
    client = DialDevClient(config)
    response = await client.get("/v1/dev/projects")
    assert response.status_code == 200 and response.body == b'{"ok":true}'
    stream = await client.open_stream("/v1/dev/events")
    try:
        assert [line async for line in stream.lines()][0].startswith("data: ")
    finally:
        await stream.close()
    assert len(seen) == 2
    for path, authorization, peer in seen:
        assert path.startswith("/v1/dev/")
        assert authorization.startswith("Bearer test-product-token-")
        assert (("commonName", "van"),) in peer["subject"]


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["wrong_ca", "untrusted_client", "missing_client", "wrong_hostname"])
@pytest.mark.parametrize("operation", ["get", "stream"])
async def test_tls_identity_failure_is_unavailable_without_http_effect(tls_gateway, defect, operation):
    config, seen, _, _, directory = tls_gateway
    other_key, other_ca = _ca("other-ca")
    if defect == "wrong_ca":
        ca = directory / "wrong-ca.crt"
        ca.write_bytes(other_ca.public_bytes(serialization.Encoding.PEM))
        config = replace(config, tls_ca_file=str(ca))
    elif defect == "untrusted_client":
        cert, key = _write_pair(directory, "wrong-client", *_leaf("van", other_key, other_ca))
        config = replace(config, tls_client_cert_file=str(cert), tls_client_key_file=str(key))
    elif defect == "missing_client":
        config = replace(config, tls_client_cert_file="", tls_client_key_file="")
    else:
        config = replace(config, base_url=config.base_url.replace("127.0.0.1", "localhost"))
    client = DialDevClient(config)
    with pytest.raises(DialDevUnavailable) as failure:
        if operation == "get":
            await client.get("/v1/dev/projects")
        else:
            stream = await client.open_stream("/v1/dev/events")
            await stream.close()
    assert failure.value.reason in {"unconfigured", "unreachable"}
    assert seen == []


@pytest.mark.asyncio
@pytest.mark.parametrize("route", [
    "http://10.77.0.1:9136", "https://10.77.0.1:9136", "http://10.77.0.2:8443",
    "https://10.77.0.2:8444", "https://user@10.77.0.2:8443", "https://10.77.0.2:8443/dev",
    "https://10.77.0.2:8443?", "https://10.77.0.2:8443#", "https://evil.test:8443",
])
async def test_production_bad_route_refuses_before_transport(tls_gateway, route):
    config, *_ = tls_gateway
    requests = []
    transport = httpx.MockTransport(lambda request: requests.append(request) or httpx.Response(200))
    with pytest.raises(DialDevUnavailable, match="unconfigured"):
        await DialDevClient(replace(config, production=True, base_url=route), transport=transport).get("/v1/dev/projects")
    assert requests == []


def test_production_gateway_needs_complete_private_tls_binding(tls_gateway):
    config, *_ = tls_gateway
    valid = replace(config, production=True, base_url="https://10.77.0.2:8443")
    assert valid.configured
    assert not replace(valid, tls_ca_file="").configured
    assert not replace(valid, tls_client_cert_file="").configured
    assert not replace(valid, tls_client_key_file="").configured
    Path(valid.tls_client_key_file).chmod(0o644)
    assert not valid.configured


def test_real_settings_wire_production_product_identity(tls_gateway):
    config, *_ = tls_gateway
    settings = Settings(
        _env_file=None, van_env="production", require_device_binding=True,
        hermes_base_url="http://10.77.0.1:8642", van_public_base_url="https://van.example:9443",
        dial_dev_enabled=True, dial_dev_base_url="https://10.77.0.2:8443",
        dial_dev_token_file=config.token_file, dial_dev_tls_ca_file=config.tls_ca_file,
        dial_dev_tls_client_cert_file=config.tls_client_cert_file,
        dial_dev_tls_client_key_file=config.tls_client_key_file,
    )
    actual = DialDevConfig.from_settings(settings)
    assert actual.production and actual.configured
    assert actual.tls_client_cert_file == config.tls_client_cert_file


@pytest.mark.asyncio
async def test_malformed_tls_binding_fails_without_falling_back(tls_gateway):
    config, seen, *_ = tls_gateway
    Path(config.tls_client_key_file).write_text("not-a-private-key")
    with pytest.raises(DialDevUnavailable, match="unconfigured"):
        await DialDevClient(config).get("/v1/dev/projects")
    assert seen == []
