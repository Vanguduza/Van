"""How long the private PKI has left, as a number something can alert on.

P3-OPS-003 has two halves. The renewal path was the first and is now in
`make-bridge-pki.sh`, which re-issues anything inside its renewal window instead
of returning early because the file exists. This module is the second half:
a monitor has to be able to *ask*, and "run a shell script and parse its stdout"
is not something an alert rule can do.

`scan()` reads the certificates directly and reports days remaining per
certificate and the minimum across all of them. That minimum is the
`pki_days_remaining` fact the `PKI_EXPIRING` alert rule reads, so expiry becomes
a page thirty days out rather than an outage on the day.

An absent certificate directory is reported as `present=False` with no expiry
facts, not as zero days remaining. A gateway that has never been given the
trading PKI is not a gateway whose PKI has expired, and conflating the two would
page an operator about a system they do not run.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes

#: Where the bridge PKI lands by default; matches `OUT` in make-bridge-pki.sh.
DEFAULT_PKI_DIR = "/opt/van-trading/secrets/pki"

#: The certificates the trading estate's two TLS seams need. Named rather than
#: globbed so a missing file is a reported absence instead of a shorter list.
EXPECTED = ("ca", "commander", "mt5-worker", "client")


@dataclass(frozen=True)
class CertificateStatus:
    name: str
    subject: str
    not_after_unix: int
    days_remaining: int
    fingerprint_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "subject": self.subject,
            "not_after_unix": self.not_after_unix,
            "days_remaining": self.days_remaining,
            "fingerprint_sha256": self.fingerprint_sha256,
        }


def _load(path: Path) -> x509.Certificate:
    return x509.load_pem_x509_certificate(path.read_bytes())


def _not_after_unix(certificate: x509.Certificate) -> int:
    # `not_valid_after_utc` on modern cryptography; the naive property is
    # deprecated and warns. Fall back so this works on either.
    value = getattr(certificate, "not_valid_after_utc", None)
    if value is None:
        value = certificate.not_valid_after.replace(tzinfo=_dt.timezone.utc)
    return int(value.timestamp())


def scan(pki_dir: str | Path = DEFAULT_PKI_DIR, *, now_unix: int | None = None) -> dict[str, Any]:
    """Report expiry for every expected certificate, and the soonest of them."""
    now = now_unix if now_unix is not None else int(_dt.datetime.now(_dt.timezone.utc).timestamp())
    root = Path(pki_dir)
    if not root.is_dir():
        return {
            "present": False,
            "pki_dir": str(root),
            "certificates": [],
            "missing": list(EXPECTED),
            "unreadable": [],
            "days_remaining": None,
        }
    certificates: list[CertificateStatus] = []
    missing: list[str] = []
    unreadable: list[str] = []
    for name in EXPECTED:
        path = root / f"{name}.crt"
        if not path.exists():
            missing.append(name)
            continue
        try:
            certificate = _load(path)
        except Exception as exc:  # noqa: BLE001 - any parse failure is the same fact
            unreadable.append(f"{name}: {type(exc).__name__}")
            continue
        not_after = _not_after_unix(certificate)
        certificates.append(CertificateStatus(
            name=name,
            subject=certificate.subject.rfc4514_string(),
            not_after_unix=not_after,
            days_remaining=int((not_after - now) // 86400),
            fingerprint_sha256=certificate.fingerprint(hashes.SHA256()).hex(),
        ))
    return {
        "present": True,
        "pki_dir": str(root),
        "certificates": [status.as_dict() for status in certificates],
        "missing": missing,
        "unreadable": unreadable,
        # A missing certificate is more urgent than any expiry, so it reports as
        # already past due rather than being left out of the minimum.
        "days_remaining": (
            -1 if (missing or unreadable)
            else min((status.days_remaining for status in certificates), default=None)
        ),
    }


__all__ = ["DEFAULT_PKI_DIR", "EXPECTED", "CertificateStatus", "scan"]
