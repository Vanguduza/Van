"""P2-SEC-008: nothing expired and nothing was rotated.

Enrolment grants were minted with a ten-year expiry — a standing grant with a number
attached. The ingress token, the internal control token, device secrets and the commander
tokens were never rotated at all, and `make-bridge-pki.sh` returned early whenever the
certificate file existed, so an 825-day private PKI was minted once and never looked at
again.

The three halves are tested here: grants expire and can be renewed, credential age is
visible, and the PKI script has a renewal path that reports.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet

from van_gateway.auth.rotation import (
    ROTATION_POLICY_SECONDS,
    ROTATION_WARNING_SECONDS,
    CredentialRotation,
    fingerprint,
)
from van_gateway.auth.service import (
    ENROLMENT_GRANT_SECONDS,
    GRANT_RENEWAL_WINDOW_SECONDS,
    AuthError,
    AuthService,
)
from van_gateway.config import get_settings
from van_gateway.storage.db import Store

REPO = Path(__file__).resolve().parents[2]
PKI = REPO / "deploy" / "van-trading-core" / "pki" / "make-bridge-pki.sh"


@pytest.fixture(autouse=True)
def _settings(tmp_path, monkeypatch):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "rot.sqlite3"))
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_GOOGLE_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def store(tmp_path):
    s = Store(str(tmp_path / "rot.sqlite3"))
    await s.migrate()
    return s


@pytest_asyncio.fixture
async def auth(store):
    return AuthService(store, Fernet.generate_key().decode())


@pytest.mark.asyncio
class TestEnrolmentGrantsExpire:
    async def test_a_grant_is_a_year_not_a_decade(self, auth):
        await auth.enroll("dev-1", "s" * 32, "PEM", "phone")
        status = await auth.grant_status("dev-1")
        assert status["state"] == "VALID"
        assert ENROLMENT_GRANT_SECONDS == 365 * 24 * 3600
        assert status["seconds_remaining"] <= ENROLMENT_GRANT_SECONDS

    async def test_a_grant_says_when_it_is_due_for_renewal(self, auth):
        await auth.enroll("dev-2", "s" * 32, "PEM", "phone")
        now = int(time.time())
        soon = now + ENROLMENT_GRANT_SECONDS - GRANT_RENEWAL_WINDOW_SECONDS + 60
        assert (await auth.grant_status("dev-2", now=soon))["state"] == "RENEW_SOON"

    async def test_a_grant_expires(self, auth):
        await auth.enroll("dev-3", "s" * 32, "PEM", "phone")
        later = int(time.time()) + ENROLMENT_GRANT_SECONDS + 1
        assert (await auth.grant_status("dev-3", now=later))["state"] == "EXPIRED"

    async def test_renewal_extends_a_live_grant(self, auth):
        await auth.enroll("dev-4", "s" * 32, "PEM", "phone")
        now = int(time.time())
        before = (await auth.grant_status("dev-4", now=now))["expires_at_unix"]
        renewed = await auth.renew_grant("dev-4", now=now + 86400)
        assert renewed["expires_at_unix"] > before
        assert renewed["state"] == "VALID"

    async def test_an_expired_grant_is_not_quietly_revived(self, auth):
        """Re-pairing is the path back. Renewing a lapsed grant makes the expiry decorative."""
        await auth.enroll("dev-5", "s" * 32, "PEM", "phone")
        later = int(time.time()) + ENROLMENT_GRANT_SECONDS + 1
        with pytest.raises(AuthError) as caught:
            await auth.renew_grant("dev-5", now=later)
        assert caught.value.code == "grant_not_renewable"

    async def test_a_revoked_grant_is_not_renewable(self, auth):
        await auth.enroll("dev-6", "s" * 32, "PEM", "phone")
        await auth.revoke("dev-6")
        with pytest.raises(AuthError):
            await auth.renew_grant("dev-6")

    async def test_expiring_grants_are_reportable_before_they_bite(self, auth):
        await auth.enroll("dev-7", "s" * 32, "PEM", "phone")
        now = int(time.time())
        assert await auth.expiring_grants(now=now) == []
        soon = now + ENROLMENT_GRANT_SECONDS - GRANT_RENEWAL_WINDOW_SECONDS + 60
        reported = await auth.expiring_grants(now=soon)
        assert [g["device_id"] for g in reported] == ["dev-7"]


@pytest.mark.asyncio
class TestCredentialAgeIsVisible:
    async def test_a_fresh_credential_is_valid(self, store):
        rot = CredentialRotation(store)
        age = await rot.observe("ingress_token", "t" * 40)
        assert age.state == "VALID" and age.age_seconds == 0

    async def test_an_unrotated_credential_eventually_says_so(self, store):
        rot = CredentialRotation(store)
        now = int(time.time())
        await rot.observe("ingress_token", "t" * 40, now=now)
        policy = ROTATION_POLICY_SECONDS["ingress_token"]
        assert (await rot.observe("ingress_token", "t" * 40, now=now + policy + 1)).state == "OVERDUE"
        warned = await rot.observe(
            "ingress_token", "t" * 40, now=now + policy - ROTATION_WARNING_SECONDS + 60
        )
        assert warned.state == "ROTATE_SOON" and warned.needs_owner

    async def test_a_changed_value_restarts_the_clock_without_being_told(self, store):
        """An operator reliably forgets to tell a system what they did."""
        rot = CredentialRotation(store)
        now = int(time.time())
        await rot.observe("ingress_token", "old-token-value-0123456789", now=now)
        policy = ROTATION_POLICY_SECONDS["ingress_token"]
        rotated = await rot.observe(
            "ingress_token", "new-token-value-0123456789", now=now + policy + 1
        )
        assert rotated.state == "VALID" and rotated.age_seconds == 0

    async def test_the_stored_row_does_not_contain_the_credential(self, store):
        rot = CredentialRotation(store)
        secret = "a-very-secret-ingress-token-value"
        await rot.observe("ingress_token", secret)
        rows = await store.fetchall("SELECT key, value FROM runtime_meta", ())
        blob = " ".join(f"{r['key']}{r['value']}" for r in rows)
        assert secret not in blob
        assert fingerprint(secret) in blob

    async def test_an_unconfigured_credential_is_not_reported_as_fresh(self, store):
        rot = CredentialRotation(store)
        assert (await rot.observe("ingress_token", "")).state == "UNCONFIGURED"

    async def test_the_report_names_what_its_age_actually_measures(self, store):
        """A static token has no issue date; claiming precision here would be a lie."""
        rot = CredentialRotation(store)
        report = await rot.report({"ingress_token": "t" * 40})
        assert "first seen" in report["age_basis"]
        assert report["needs_owner"] == []

    async def test_every_tracked_credential_has_a_policy(self):
        for name, seconds in ROTATION_POLICY_SECONDS.items():
            assert 0 < seconds <= 365 * 24 * 3600, name


class TestThePkiHasARenewalPath:
    def test_the_script_no_longer_returns_early_on_mere_existence(self):
        source = PKI.read_text(encoding="utf-8")
        assert '[[ -f "$name.crt" ]] && return 0' not in source, (
            "issue() returned early whenever the file existed, which is what made this "
            "script a one-shot"
        )
        assert "checkend" in source, "nothing checks how long a certificate has left"

    @pytest.mark.skipif(not PKI.is_file(), reason="pki script absent")
    def test_check_reports_and_exits_non_zero_when_renewal_is_due(self, tmp_path):
        env = {"OUT": str(tmp_path / "pki"), "PATH": "/usr/bin:/bin:/usr/local/bin"}
        made = subprocess.run(["bash", str(PKI)], env=env, capture_output=True, text=True)
        assert made.returncode == 0, made.stderr

        fresh = subprocess.run(
            ["bash", str(PKI), "--check"], env=env, capture_output=True, text=True
        )
        assert fresh.returncode == 0, fresh.stdout
        assert "OK commander" in fresh.stdout

        due = subprocess.run(
            ["bash", str(PKI), "--check"],
            env={**env, "RENEW_WITHIN_DAYS": "99999"},
            capture_output=True, text=True,
        )
        assert due.returncode == 1, "a monitor could not tell that renewal was due"
        assert "RENEW commander" in due.stdout

    @pytest.mark.skipif(not PKI.is_file(), reason="pki script absent")
    def test_a_certificate_inside_the_window_is_actually_reissued(self, tmp_path):
        env = {"OUT": str(tmp_path / "pki"), "PATH": "/usr/bin:/bin:/usr/local/bin"}
        subprocess.run(["bash", str(PKI)], env=env, capture_output=True, text=True)
        before = (tmp_path / "pki" / "commander.crt").read_bytes()

        subprocess.run(
            ["bash", str(PKI)],
            env={**env, "RENEW_WITHIN_DAYS": "99999"},
            capture_output=True, text=True,
        )
        after = (tmp_path / "pki" / "commander.crt").read_bytes()
        assert after != before, "the certificate was inside the renewal window and was not reissued"
