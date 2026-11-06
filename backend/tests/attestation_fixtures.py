"""Synthetic signed PKI for testing the real attestation validation boundary."""
import datetime as dt

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from van_gateway.auth.device_proof import ATTESTATION_OID


def signed_attestation_chain(public_key_pem, extension, *, expired=False, issuer_ca=True):
    now = dt.datetime.now(dt.timezone.utc)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test-only attestation root")])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name)
          .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(now-dt.timedelta(days=1)).not_valid_after(now+dt.timedelta(days=3))
          .add_extension(x509.BasicConstraints(ca=issuer_ca, path_length=None), critical=True)
          .sign(ca_key, hashes.SHA256()))
    leaf = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test-only device")]))
            .issuer_name(ca_name).public_key(serialization.load_pem_public_key(public_key_pem.encode()))
            .serial_number(x509.random_serial_number()).not_valid_before(now-dt.timedelta(days=2))
            .not_valid_after(now-dt.timedelta(days=1) if expired else now+dt.timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.UnrecognizedExtension(x509.ObjectIdentifier(ATTESTATION_OID), extension), critical=False)
            .sign(ca_key, hashes.SHA256()))
    return [c.public_bytes(serialization.Encoding.DER) for c in (leaf,ca)], ca.fingerprint(hashes.SHA256()).hex()
