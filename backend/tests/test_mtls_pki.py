"""The VAN device CA: what it will and will not sign, and that revocation is enforced by the record."""

from __future__ import annotations

import base64
import json
import stat

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import NameOID

from van_gateway.mtls.pki import DeviceCA, PkiError, init_ca, peer_identity


def csr_for(cn: str, key=None) -> tuple[str, object]:
    key = key or ec.generate_private_key(ec.SECP256R1())
    csr = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    ).sign(key, hashes.SHA256())
    return csr.public_bytes(serialization.Encoding.PEM).decode(), key


@pytest.fixture
def ca(tmp_path):
    init_ca(tmp_path)
    return DeviceCA(tmp_path)


def test_ca_key_is_private_and_init_refuses_to_overwrite(tmp_path):
    init_ca(tmp_path)
    assert stat.S_IMODE((tmp_path / "ca.key").stat().st_mode) == 0o600
    with pytest.raises(PkiError) as exc:
        init_ca(tmp_path)
    assert exc.value.code == "ca_exists"


def test_issues_a_client_certificate_bound_to_the_device_and_its_own_key(ca):
    csr, key = csr_for("owner-phone")
    issued = ca.issue_client(csr, "owner-phone", days=30)
    cert = x509.load_pem_x509_certificate(issued.certificate_pem.encode())
    assert cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == "owner-phone"
    assert cert.public_key().public_numbers() == key.public_key().public_numbers()
    eku = cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
    assert list(eku) == [x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH]
    assert not cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    der = cert.public_bytes(serialization.Encoding.DER)
    assert peer_identity(der) == (issued.serial_hex, "owner-phone")
    assert ca.admitted(issued.serial_hex, "owner-phone")
    assert not ca.admitted(issued.serial_hex, "someone-else")


@pytest.mark.parametrize("cn, device, code", [
    ("other-phone", "owner-phone", "csr_subject_mismatch"),
    ("owner-phone", "bad id with spaces", "device_id_invalid"),
])
def test_refuses_a_csr_that_does_not_name_the_authenticated_device(ca, cn, device, code):
    csr, _ = csr_for(cn)
    with pytest.raises(PkiError) as exc:
        ca.issue_client(csr, device)
    assert exc.value.code == code


def test_refuses_non_p256_keys_and_forged_csrs(ca):
    rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr, _ = csr_for("owner-phone", rsa_key)
    with pytest.raises(PkiError) as exc:
        ca.issue_client(csr, "owner-phone")
    assert exc.value.code == "csr_key_invalid"

    good, _ = csr_for("owner-phone")
    der = bytearray(x509.load_pem_x509_csr(good.encode()).public_bytes(serialization.Encoding.DER))
    der[-5] ^= 0x01  # corrupt the signature
    forged = x509.load_der_x509_csr(bytes(der)).public_bytes(serialization.Encoding.PEM).decode()
    with pytest.raises(PkiError) as exc:
        ca.issue_client(forged, "owner-phone")
    assert exc.value.code == "csr_signature_invalid"

    with pytest.raises(PkiError) as exc:
        ca.issue_client("not a csr", "owner-phone")
    assert exc.value.code == "csr_invalid"


def test_reissue_supersedes_and_revoke_withdraws(ca, tmp_path):
    first = ca.issue_client(csr_for("owner-phone")[0], "owner-phone")
    second = ca.issue_client(csr_for("owner-phone")[0], "owner-phone")
    assert not ca.admitted(first.serial_hex, "owner-phone")
    assert ca.admitted(second.serial_hex, "owner-phone")
    assert ca.revoke_device("owner-phone") == 1
    assert not ca.admitted(second.serial_hex, "owner-phone")
    # The record is the authority and survives a restart.
    reloaded = DeviceCA(tmp_path)
    assert not reloaded.admitted(second.serial_hex, "owner-phone")
    record = json.loads((tmp_path / "issued.json").read_text())
    assert {e["revoked_reason"] for e in record["certificates"].values()} == {"superseded", "revoked"}


def test_a_certificate_the_record_does_not_know_is_not_admitted(ca, tmp_path):
    issued = ca.issue_client(csr_for("owner-phone")[0], "owner-phone")
    (tmp_path / "issued.json").write_text('{"certificates": {}}')
    assert not DeviceCA(tmp_path).admitted(issued.serial_hex, "owner-phone")


def test_server_certificate_carries_the_requested_names(ca, tmp_path):
    ca.issue_server("DNS:van.example,IP:203.0.113.7")
    cert = x509.load_pem_x509_certificate((tmp_path / "server.crt").read_bytes())
    san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert san.get_values_for_type(x509.DNSName) == ["van.example"]
    assert [str(ip) for ip in san.get_values_for_type(x509.IPAddress)] == ["203.0.113.7"]
    assert stat.S_IMODE((tmp_path / "server.key").stat().st_mode) == 0o600
    with pytest.raises(PkiError):
        ca.issue_server("URI:https://nope")


def test_accepts_the_request_the_android_encoder_produces(ca):
    """The gateway's half of the enrolment contract; android/verification Pkcs10Test holds the other."""
    from pathlib import Path

    vector = json.loads((Path(__file__).resolve().parents[2] / "evidence/van-mtls/android_pkcs10_vector.json").read_text())
    issued = ca.issue_client(vector["csr_pem"], vector["device_id"])
    cert = x509.load_pem_x509_certificate(issued.certificate_pem.encode())
    assert cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == vector["device_id"]
    assert cert.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    ) == base64.b64decode(vector["public_key_spki_b64"])
