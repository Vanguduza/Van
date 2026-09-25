"""VAN device CA.

One private CA (EC P-256) signs:
* the gateway's server certificate: the app pins this CA, so no public CA or ACME is involved;
* one client certificate per enrolled device, issued from a CSR the phone generates inside its
  Android Keystore (the private key never leaves the device).

Revocation is enforced by the gateway itself: a client certificate is admitted only if its
serial is recorded here as issued and not revoked. A certificate that chains to the CA but is
unknown to this store (for example after the store was lost) is refused, so the store fails
closed. Issuing a new certificate to a device revokes that device's previous ones.

CLI (run as the gateway's service user):
    python -m van_gateway.mtls.pki init --dir DIR
    python -m van_gateway.mtls.pki issue-server --dir DIR --san DNS:host,IP:1.2.3.4
    python -m van_gateway.mtls.pki revoke --dir DIR --device-id ID
    python -m van_gateway.mtls.pki list --dir DIR
"""

from __future__ import annotations

import argparse
import datetime as dt
import ipaddress
import json
import os
import re
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

#: Device ids are chosen by the phone at pairing; this is the character set a certificate
#: subject may carry for one. Anything else is refused rather than escaped.
DEVICE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
CA_DAYS = 3650
SERVER_DAYS = 825
MAX_CLIENT_DAYS = 825

CA_CERT, CA_KEY = "ca.crt", "ca.key"
SERVER_CERT, SERVER_KEY = "server.crt", "server.key"
STATE = "issued.json"


class PkiError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class IssuedCertificate:
    serial_hex: str
    device_id: str
    certificate_pem: str
    not_after_unix: int


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _write_private(path: Path, data: bytes, mode: int = 0o600) -> None:
    """Atomic write, created with its final mode (never world-readable, not even briefly)."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _name(cn: str) -> x509.Name:
    return x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "VAN"),
        x509.NameAttribute(NameOID.COMMON_NAME, cn),
    ])


def init_ca(directory: str | os.PathLike[str]) -> str:
    """Create the CA. Refuses to overwrite one. Returns the CA certificate's SHA-256."""
    d = Path(directory)
    if (d / CA_KEY).exists():
        raise PkiError("ca_exists", f"a CA already exists in {d}")
    key = ec.generate_private_key(ec.SECP256R1())
    now = _now()
    ski = x509.SubjectKeyIdentifier.from_public_key(key.public_key())
    cert = (
        x509.CertificateBuilder()
        .subject_name(_name("VAN Device CA"))
        .issuer_name(_name("VAN Device CA"))
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=CA_DAYS))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=False, content_commitment=False, key_encipherment=False,
            data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True,
            encipher_only=False, decipher_only=False), critical=True)
        .add_extension(ski, critical=False)
        .sign(key, hashes.SHA256())
    )
    _write_private(d / CA_KEY, key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    _write_private(d / CA_CERT, cert.public_bytes(serialization.Encoding.PEM), 0o644)
    _write_private(d / STATE, b'{"certificates": {}}\n')
    return cert.fingerprint(hashes.SHA256()).hex()


def _parse_san(spec: str) -> list[x509.GeneralName]:
    names: list[x509.GeneralName] = []
    for part in [p.strip() for p in spec.split(",") if p.strip()]:
        kind, _, value = part.partition(":")
        if kind == "DNS" and re.fullmatch(r"[A-Za-z0-9.-]{1,253}", value):
            names.append(x509.DNSName(value))
        elif kind == "IP":
            names.append(x509.IPAddress(ipaddress.ip_address(value)))
        else:
            raise PkiError("san_invalid", f"invalid subjectAltName entry {part!r}")
    if not names:
        raise PkiError("san_invalid", "at least one DNS: or IP: entry is required")
    return names


class DeviceCA:
    """The CA plus its issuance record. Thread-safe; one instance per process."""

    def __init__(self, directory: str | os.PathLike[str]):
        self.dir = Path(directory)
        self._lock = threading.Lock()
        try:
            self._ca_cert = x509.load_pem_x509_certificate((self.dir / CA_CERT).read_bytes())
            self._ca_key = serialization.load_pem_private_key((self.dir / CA_KEY).read_bytes(), None)
        except FileNotFoundError as exc:
            raise PkiError("ca_missing", f"device CA not initialised in {self.dir}") from exc
        if not isinstance(self._ca_key, ec.EllipticCurvePrivateKey):
            raise PkiError("ca_invalid", "device CA key must be EC")
        self._state = self._load_state()

    # ---- record ------------------------------------------------------------------------------
    def _load_state(self) -> dict:
        path = self.dir / STATE
        if not path.exists():
            return {"certificates": {}}
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data.get("certificates"), dict):
            raise PkiError("state_invalid", f"{path} is not a device certificate record")
        return data

    def _save_state(self) -> None:
        _write_private(self.dir / STATE, (json.dumps(self._state, indent=2, sort_keys=True) + "\n").encode())

    @property
    def ca_pem(self) -> str:
        return self._ca_cert.public_bytes(serialization.Encoding.PEM).decode()

    def admitted(self, serial_hex: str, device_id: str) -> bool:
        """True only for a certificate this CA issued to `device_id` and has not revoked."""
        entry = self._state["certificates"].get(serial_hex.lower())
        return bool(entry) and entry.get("device_id") == device_id and not entry.get("revoked_at_unix")

    # ---- server ------------------------------------------------------------------------------
    def issue_server(self, san: str, days: int = SERVER_DAYS) -> None:
        key = ec.generate_private_key(ec.SECP256R1())
        now = _now()
        cert = (
            x509.CertificateBuilder()
            .subject_name(_name("van-gateway"))
            .issuer_name(self._ca_cert.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(minutes=5))
            .not_valid_after(now + dt.timedelta(days=days))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(
                digital_signature=True, content_commitment=False, key_encipherment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=False, crl_sign=False,
                encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(x509.SubjectAlternativeName(_parse_san(san)), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(self._ca_key.public_key()), critical=False)
            .sign(self._ca_key, hashes.SHA256())
        )
        _write_private(self.dir / SERVER_KEY, key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        _write_private(self.dir / SERVER_CERT, cert.public_bytes(serialization.Encoding.PEM), 0o644)

    # ---- clients -----------------------------------------------------------------------------
    def issue_client(self, csr_pem: str, device_id: str, days: int = 365) -> IssuedCertificate:
        if not DEVICE_ID_RE.fullmatch(device_id or ""):
            raise PkiError("device_id_invalid", "device id is not certificate-safe")
        if not 1 <= int(days) <= MAX_CLIENT_DAYS:
            raise PkiError("validity_invalid", f"validity must be 1..{MAX_CLIENT_DAYS} days")
        try:
            csr = x509.load_pem_x509_csr(csr_pem.encode("utf-8"))
        except Exception as exc:
            raise PkiError("csr_invalid", "CSR is not a PEM PKCS#10 request") from exc
        if not csr.is_signature_valid:
            raise PkiError("csr_signature_invalid", "CSR signature does not verify")
        public_key = csr.public_key()
        if not isinstance(public_key, ec.EllipticCurvePublicKey) or not isinstance(public_key.curve, ec.SECP256R1):
            raise PkiError("csr_key_invalid", "CSR key must be EC P-256")
        cns = csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        if len(cns) != 1 or cns[0].value != device_id:
            raise PkiError("csr_subject_mismatch", "CSR commonName must be exactly the enrolled device id")

        now = _now()
        not_after = now + dt.timedelta(days=int(days))
        serial = x509.random_serial_number()
        cert = (
            x509.CertificateBuilder()
            .subject_name(_name(device_id))
            .issuer_name(self._ca_cert.subject)
            .public_key(public_key)
            .serial_number(serial)
            .not_valid_before(now - dt.timedelta(minutes=5))
            .not_valid_after(not_after)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(
                digital_signature=True, content_commitment=False, key_encipherment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=False, crl_sign=False,
                encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(public_key), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(self._ca_key.public_key()), critical=False)
            .sign(self._ca_key, hashes.SHA256())
        )
        serial_hex = format(serial, "x")
        with self._lock:
            revoked_at = int(now.timestamp())
            for entry in self._state["certificates"].values():
                if entry.get("device_id") == device_id and not entry.get("revoked_at_unix"):
                    entry["revoked_at_unix"] = revoked_at
                    entry["revoked_reason"] = "superseded"
            self._state["certificates"][serial_hex] = {
                "device_id": device_id,
                "issued_at_unix": int(now.timestamp()),
                "not_after_unix": int(not_after.timestamp()),
            }
            self._save_state()
        return IssuedCertificate(
            serial_hex=serial_hex,
            device_id=device_id,
            certificate_pem=cert.public_bytes(serialization.Encoding.PEM).decode(),
            not_after_unix=int(not_after.timestamp()),
        )

    def revoke_device(self, device_id: str, reason: str = "revoked") -> int:
        with self._lock:
            count = 0
            now = int(_now().timestamp())
            for entry in self._state["certificates"].values():
                if entry.get("device_id") == device_id and not entry.get("revoked_at_unix"):
                    entry["revoked_at_unix"] = now
                    entry["revoked_reason"] = reason
                    count += 1
            if count:
                self._save_state()
            return count

    def listing(self) -> list[dict]:
        with self._lock:
            return [dict(serial=s, **e) for s, e in sorted(self._state["certificates"].items())]


def peer_identity(der: bytes | None) -> tuple[str, str] | None:
    """(serial_hex, device_id) from a verified client certificate, or None."""
    if not der:
        return None
    cert = x509.load_der_x509_certificate(der)
    cns = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    if len(cns) != 1:
        return None
    return format(cert.serial_number, "x"), str(cns[0].value)


def _main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m van_gateway.mtls.pki")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("init", "issue-server", "revoke", "list"):
        sp = sub.add_parser(name)
        sp.add_argument("--dir", required=True)
        if name == "issue-server":
            sp.add_argument("--san", required=True)
        if name == "revoke":
            sp.add_argument("--device-id", required=True)
    a = p.parse_args(argv)
    try:
        if a.cmd == "init":
            print(f"CA_READY sha256={init_ca(a.dir)}")
        elif a.cmd == "issue-server":
            DeviceCA(a.dir).issue_server(a.san)
            print(f"SERVER_CERT_READY san={a.san}")
        elif a.cmd == "revoke":
            print(f"REVOKED device={a.device_id} certificates={DeviceCA(a.dir).revoke_device(a.device_id)}")
        else:
            for row in DeviceCA(a.dir).listing():
                state = "REVOKED" if row.get("revoked_at_unix") else "VALID"
                print(f"{state} serial={row['serial']} device={row['device_id']} not_after={row['not_after_unix']}")
    except PkiError as exc:
        print(f"VAN_PKI_REFUSED {exc.code}: {exc.message}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
