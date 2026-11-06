"""Use real local TLS peers: network errors cannot prove certificate rejection."""
from __future__ import annotations

import datetime
import importlib.util
import ipaddress
from pathlib import Path
import socket
import ssl
import threading
import os
import json
import subprocess

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
import pytest


ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("van_qualify_tls", ROOT / "deploy/van-browser-stream/qualify_tls.py")
qualifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qualifier)


@pytest.fixture
def pki(tmp_path):
    def issue(name, issuer=None, ca=False, server=False):
        key = ec.generate_private_key(ec.SECP256R1())
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
        now = datetime.datetime.now(datetime.timezone.utc)
        builder = (x509.CertificateBuilder().subject_name(subject)
                   .issuer_name(issuer[0].subject if issuer else subject).public_key(key.public_key())
                   .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(minutes=1))
                   .not_valid_after(now + datetime.timedelta(days=1))
                   .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True))
        if not ca:
            builder = builder.add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH if server else ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
        if server:
            builder = builder.add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
        cert = builder.sign(issuer[1] if issuer else key, hashes.SHA256())
        cert_path, key_path = tmp_path / f"{name}.crt", tmp_path / f"{name}.key"
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        return cert, key, str(cert_path), str(key_path)

    ca = issue("ca", ca=True)
    foreign_ca = issue("foreign-ca", ca=True)
    return {"ca": ca, "server": issue("server", ca, server=True), "client": issue("client", ca),
            "foreign_ca": foreign_ca, "foreign_client": issue("foreign-client", foreign_ca)}


def _peer(pki, *, require_client=True):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = context.maximum_version = ssl.TLSVersion.TLSv1_3
    context.load_cert_chain(pki["server"][2], pki["server"][3])
    context.load_verify_locations(pki["ca"][2])
    context.verify_mode = ssl.CERT_REQUIRED if require_client else ssl.CERT_NONE
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(2)
    port = listener.getsockname()[1]
    observed = []

    def serve():
        try:
            with listener:
                raw, _ = listener.accept()
                with raw:
                    with context.wrap_socket(raw, server_side=True) as connection:
                        observed.append(connection.getpeercert())
                        connection.recv(4)
                        connection.sendall(b"x")
        except (OSError, ssl.SSLError) as exc:
            observed.append(getattr(exc, "reason", type(exc).__name__))

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    return port, thread, observed


@pytest.mark.parametrize("client_name,result", [("client", "ADMITTED"), (None, "DENIED"), ("foreign_client", "DENIED")])
def test_known_client_admission_and_explicit_negative_certificate_denials(pki, client_name, result):
    port, thread, observed = _peer(pki)
    kwargs = {} if client_name is None else {"cert_file": pki[client_name][2], "key_file": pki[client_name][3]}
    outcome = qualifier.probe_tls("127.0.0.1", port, pki["ca"][2], timeout=1, **kwargs)
    thread.join(timeout=3)
    assert not thread.is_alive() and outcome["result"] == result
    if result == "ADMITTED":
        assert observed[0] and outcome["reason"] == "verified_tls_handshake_completed"
    else:
        assert isinstance(observed[0], str) and outcome["reason"] == "peer_certificate_alert"


def test_unreachable_is_not_a_tls_denial(pki):
    socket_ = socket.socket()
    socket_.bind(("127.0.0.1", 0))
    port = socket_.getsockname()[1]
    socket_.close()
    result = qualifier.probe_tls("127.0.0.1", port, pki["ca"][2], timeout=0.2)
    assert result == {"result": "UNREACHABLE", "reason": "transport_unavailable"}


@pytest.mark.parametrize("fault", ["wrong_server_ca", "wrong_server_name"])
def test_local_server_verification_failure_is_not_peer_client_denial(pki, fault):
    port, thread, _ = _peer(pki)
    host = "localhost" if fault == "wrong_server_name" else "127.0.0.1"
    ca = pki["foreign_ca"][2] if fault == "wrong_server_ca" else pki["ca"][2]
    outcome = qualifier.probe_tls(host, port, ca, cert_file=pki["client"][2], key_file=pki["client"][3], timeout=1)
    thread.join(timeout=3)
    assert not thread.is_alive() and outcome["result"] == "TLS_ERROR"


def test_anonymous_application_data_exposes_missing_mtls_gate(pki):
    port, thread, observed = _peer(pki, require_client=False)
    outcome = qualifier.probe_tls("127.0.0.1", port, pki["ca"][2], timeout=1)
    thread.join(timeout=3)
    assert not thread.is_alive() and observed == [None]
    assert outcome["result"] == "ADMITTED"


def test_qualification_without_selected_profile_cannot_report_a_pass():
    environment = dict(os.environ)
    environment.pop("VAN_BROWSER_INSTANCE", None)
    result = subprocess.run(["bash", str(ROOT / "deploy/van-browser-stream/qualify.sh")],
                            env=environment, capture_output=True, text=True, check=False, timeout=5)
    assert result.returncode != 0
    checks = json.loads(result.stdout)["checks"]
    assert checks[0]["check"] == "profile_instance_selected" and checks[0]["status"] == "UNKNOWN"
