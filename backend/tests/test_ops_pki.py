"""P3-OPS-003 — expiry that a monitor can ask about, not only a script it can run.

The renewal path lives in `make-bridge-pki.sh` (P2-SEC-008). This is the other
half: a number an alert rule can threshold on, produced by reading the real
certificates rather than by parsing a shell script's stdout.

The certificates here are generated in the test, so what is being verified is
that the module reads real X.509 rather than that it agrees with a fixture.
"""

from __future__ import annotations

import datetime as dt

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from van_gateway.ops.pki import EXPECTED, scan


def _write_certificate(path, *, common_name: str, days: int) -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = dt.datetime.now(dt.timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=days))
        .sign(key, hashes.SHA256())
    )
    path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))


def _full_pki(root, *, days: int = 825):
    root.mkdir(parents=True, exist_ok=True)
    for name in EXPECTED:
        _write_certificate(root / f"{name}.crt", common_name=name, days=days)
    return root


def test_days_remaining_is_read_from_the_certificates(tmp_path):
    root = _full_pki(tmp_path / "pki", days=825)
    report = scan(root)
    assert report["present"] is True
    assert report["missing"] == []
    assert len(report["certificates"]) == len(EXPECTED)
    assert report["days_remaining"] in (824, 825)
    for status in report["certificates"]:
        assert status["subject"].startswith("CN=")
        assert len(status["fingerprint_sha256"]) == 64


def test_the_soonest_expiry_is_the_one_that_matters(tmp_path):
    root = _full_pki(tmp_path / "pki", days=825)
    _write_certificate(root / "mt5-worker.crt", common_name="mt5-worker", days=12)
    report = scan(root)
    assert report["days_remaining"] in (11, 12)


def test_a_missing_certificate_is_more_urgent_than_any_expiry(tmp_path):
    root = _full_pki(tmp_path / "pki")
    (root / "client.crt").unlink()
    report = scan(root)
    assert report["missing"] == ["client"]
    assert report["days_remaining"] == -1


def test_an_unreadable_certificate_is_reported_rather_than_skipped(tmp_path):
    root = _full_pki(tmp_path / "pki")
    (root / "commander.crt").write_text("this is not a certificate", encoding="utf-8")
    report = scan(root)
    assert report["unreadable"] and "commander" in report["unreadable"][0]
    assert report["days_remaining"] == -1


def test_no_pki_at_all_is_absence_not_expiry(tmp_path):
    """A gateway that was never given the trading PKI is not one whose PKI has
    expired, and paging an operator about a system they do not run is how alerts
    get muted."""
    report = scan(tmp_path / "nowhere")
    assert report["present"] is False
    assert report["days_remaining"] is None


def test_an_already_expired_certificate_reports_negative_days(tmp_path):
    root = tmp_path / "pki"
    root.mkdir()
    for name in EXPECTED:
        _write_certificate(root / f"{name}.crt", common_name=name, days=90)
    # not_valid_before is one day back, so a -5 day certificate is still valid
    # input to the parser; build it explicitly instead.
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ca")])
    now = dt.datetime.now(dt.timezone.utc)
    expired = (
        x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=30))
        .not_valid_after(now - dt.timedelta(days=5))
        .sign(key, hashes.SHA256())
    )
    (root / "ca.crt").write_bytes(expired.public_bytes(serialization.Encoding.PEM))
    report = scan(root)
    assert report["days_remaining"] <= -5


def test_the_pki_number_reaches_the_alert_rules(tmp_path):
    """The whole reason this module exists rather than a shell script."""
    from van_gateway.observability.alerts import evaluate
    from van_gateway.observability.metrics import MetricsRegistry
    from van_gateway.ops.health import ops_facts

    root = _full_pki(tmp_path / "pki", days=10)
    facts = ops_facts({"pki": scan(root)})
    assert facts["pki_days_remaining"] in (9, 10)
    firing = {alert.rule for alert in evaluate(MetricsRegistry(), ops_facts=facts)}
    assert "PKI_EXPIRING" in firing
