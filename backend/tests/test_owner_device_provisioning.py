"""Rev 1.5 ADR-RB-026 — the installer's one call, driven through the ingress.

The payload travels to the phone over ADB, through a shell, and can reach a device log.
ADR-RB-026 makes that acceptable by requiring three things of it at once, and this file
exists because all three are decided here rather than on the device:

* it is **short-lived** — the Gateway sets the expiry, not the caller;
* it is **single-use** — the Gateway mints fresh credentials per call and consumes them;
* it is **not sufficient on its own** — what it carries earns an enrolment that must be
  attested by a hardware key (§0D.3), rather than being a credential itself.

Remove any one and the channel stops being defensible, so each has a test that fails if it
is relaxed. The fourth group is about what the payload must never carry, which is the
distinction between a credential consumed once and one that outlives enrolment.
"""

from __future__ import annotations

import time

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from van_gateway.app import create_app
from van_gateway.config import get_settings
from van_gateway.connectivity.config import FORBIDDEN_MANIFEST_FIELDS
from van_gateway.connectivity.provisioning import (
    FORBIDDEN_PAYLOAD_FIELDS,
    PROVISIONING_PAYLOAD_VERSION,
    PROVISIONING_TTL_MS,
    ProvisioningError,
    build_provisioning_payload,
    sign_provisioning_payload,
    verify_provisioning_payload,
)

INGRESS = "provisioning-ingress-token-0123456789"
INTERNAL = "provisioning-internal-token-0123456789"
#: Its own credential. `DEFAULT_SCOPES` deliberately withholds `device_enrolment` from the
#: legacy token, because the scope that can mint owner-device authority is granted on
#: purpose — which is exactly the property the installer depends on.
ENROLMENT = "provisioning-enrolment-token-0123456789"
SIGNING_KID = "connectivity-test-key"
ROUTE = "/v1/devices/provisioning-payload"


@pytest.fixture
def signing_key(tmp_path):
    key = ec.generate_private_key(ec.SECP256R1())
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    path = tmp_path / "connectivity.pem"
    path.write_text(private_pem)
    return private_pem, public_pem, path


@pytest.fixture
def _settings(tmp_path, monkeypatch, signing_key):
    _, _, key_path = signing_key
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "provisioning.sqlite3"))
    monkeypatch.setenv("VAN_HERMES_BASE_URL", "http://hermes.invalid")
    monkeypatch.setenv("VAN_GOOGLE_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", INGRESS)
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", INTERNAL)
    monkeypatch.setenv("VAN_DEVICE_ENROLMENT_TOKEN", ENROLMENT)
    monkeypatch.setenv("VAN_CONNECTIVITY_SIGNING_KEY_FILE", str(key_path))
    monkeypatch.setenv("VAN_CONNECTIVITY_SIGNING_KID", SIGNING_KID)
    monkeypatch.setenv("VAN_OWNER_DEVICE_SIGNING_CERT_SHA256", "a" * 64)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def client(_settings):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        async with app.router.lifespan_context(app):
            yield ac, app


def _headers():
    return {"X-Van-Ingress-Token": INGRESS, "X-Van-Internal-Token": ENROLMENT}


async def _issue(ac, gateway_url="https://van.example", **extra):
    return await ac.post(
        ROUTE, json={"gateway_url": gateway_url, **extra}, headers=_headers()
    )


# --------------------------------------------------------------------------- the route


@pytest.mark.asyncio
class TestTheInstallerAsksForAlmostNothing:

    async def test_one_call_returns_a_verifiable_signed_envelope(self, client, signing_key):
        _, public_pem, _ = signing_key
        ac, _ = client
        issued = await _issue(ac)
        assert issued.status_code == 200, issued.text
        body = issued.json()
        # The device's check, run here: the Gateway is the last place a payload the phone
        # cannot verify can be caught, and the phone cannot be fixed remotely.
        verify_provisioning_payload(
            body["payload"], body["signature"],
            trusted_keys={SIGNING_KID: public_pem}, kid=body["kid"],
        )

    async def test_the_caller_names_only_the_gateway(self, client):
        """Everything else is the Gateway's to mint, and that is the point.

        An installer that supplied the expiry could extend a provisioning window; one that
        supplied a token could reuse it. The body has one field, so it can do neither.
        """
        from van_gateway.app import ProvisioningPayloadBody

        assert set(ProvisioningPayloadBody.model_fields) == {"gateway_url", "note"}

    async def test_it_carries_both_single_use_credentials(self, client):
        """§0D.3 needs both, and a payload with one is a half-provisioned phone.

        Pairing alone leaves working tokens on a handset with no hardware identity —
        an APK copied elsewhere would work, which is the failure that section is about.
        """
        ac, _ = client
        payload = (await _issue(ac)).json()["payload"]
        assert len(payload["pairing_token"]) >= 32
        assert len(payload["bootstrap_token"]) >= 32
        assert payload["pairing_token"] != payload["bootstrap_token"]
        assert payload["attestation_challenge"]

    async def test_every_call_mints_fresh_credentials(self, client):
        """Single-use, and therefore never the same twice.

        A Gateway that cached a payload for the window would hand two installations the
        same token, and the second would fail in a way that looks like a device fault.
        """
        ac, _ = client
        first = (await _issue(ac)).json()["payload"]
        second = (await _issue(ac)).json()["payload"]
        assert first["provisioning_id"] != second["provisioning_id"]
        assert first["bootstrap_token"] != second["bootstrap_token"]
        assert first["pairing_token"] != second["pairing_token"]

    async def test_the_window_is_minutes_not_hours(self, client):
        ac, _ = client
        payload = (await _issue(ac)).json()["payload"]
        window = payload["expires_at_ms"] - payload["issued_at_ms"]
        assert window == PROVISIONING_TTL_MS
        assert window <= 15 * 60_000, "the ADB channel does not survive a long window"

    async def test_a_plain_http_gateway_is_refused(self, client):
        ac, _ = client
        refused = await _issue(ac, gateway_url="http://van.example")
        assert refused.status_code == 400
        assert refused.json()["detail"] == "provisioning_url_must_use_https"

    async def test_the_route_needs_the_enrolment_scope(self, client):
        """Not any control credential — the one scope that can mint owner authority.

        `DEFAULT_SCOPES` withholds `device_enrolment` from the legacy token on purpose,
        and provisioning mints both the pairing ticket and the bootstrap token, so it sits
        behind the same gate as enrolment itself.
        """
        ac, _ = client
        for headers in (
            {"X-Van-Ingress-Token": INGRESS},
            {"X-Van-Ingress-Token": INGRESS, "X-Van-Internal-Token": INTERNAL},
        ):
            refused = await ac.post(
                ROUTE, json={"gateway_url": "https://van.example"}, headers=headers,
            )
            assert refused.status_code in {401, 403}, refused.text
            assert refused.json()["required_scope"] == "device_enrolment"

    async def test_the_audit_row_does_not_carry_the_token(self, client):
        """An audit row with the bootstrap token in it is a second copy of the one
        credential that can bind a new device, in the table a backup copies."""
        ac, app = client
        payload = (await _issue(ac, note="bench-1")).json()["payload"]
        rows = await app.state.store.fetchall(
            "SELECT * FROM audit WHERE capability = ?", ("device.provisioning.issue",)
        )
        assert rows, "the issue was not audited"
        blob = "".join(str(dict(row)) for row in rows)
        assert payload["bootstrap_token"] not in blob
        assert payload["pairing_token"] not in blob
        assert payload["provisioning_id"] in blob


# --------------------------------------------------------------------------- the payload


class TestWhatThePayloadMayAndMayNotCarry:

    def _payload(self, **extra):
        payload = build_provisioning_payload(
            gateway_url="https://van.example",
            pairing_token="p" * 40,
            bootstrap_token="b" * 40,
            attestation_challenge="chal",
        )
        payload.update(extra)
        return payload

    def test_a_standing_credential_is_refused_at_signing(self, signing_key):
        """Refused where it is introduced, not only where it is read.

        The device refuses it too. Both, because the device's refusal is the one that
        cannot be shipped around and the Gateway's is the one that catches the mistake
        before a phone ever sees it.
        """
        private_pem, _, _ = signing_key
        with pytest.raises(ProvisioningError) as caught:
            sign_provisioning_payload(
                self._payload(ingress_token="t" * 40), private_pem=private_pem
            )
        assert caught.value.reason.startswith("provisioning_carries_standing_credential:")

    def test_every_forbidden_field_is_actually_refused(self, signing_key):
        private_pem, _, _ = signing_key
        for field in FORBIDDEN_PAYLOAD_FIELDS:
            with pytest.raises(ProvisioningError):
                sign_provisioning_payload(self._payload(**{field: "v"}), private_pem=private_pem)

    def test_the_two_single_use_tokens_are_not_forbidden(self):
        """Carrying them is the payload's job. The asymmetry with a manifest is deliberate."""
        assert "pairing_token" not in FORBIDDEN_PAYLOAD_FIELDS
        assert "bootstrap_token" not in FORBIDDEN_PAYLOAD_FIELDS
        # And a manifest, which is long-lived and cached, still refuses one.
        assert "pairing_token" in FORBIDDEN_MANIFEST_FIELDS

    def test_an_expired_payload_is_refused_however_well_signed(self, signing_key):
        private_pem, public_pem, _ = signing_key
        payload = self._payload()
        signature = sign_provisioning_payload(payload, private_pem=private_pem)
        with pytest.raises(ProvisioningError) as caught:
            verify_provisioning_payload(
                payload, signature, trusted_keys={SIGNING_KID: public_pem},
                kid=SIGNING_KID, now_ms=payload["expires_at_ms"] + 1,
            )
        assert caught.value.reason == "provisioning_payload_expired"

    def test_a_payload_with_no_expiry_is_refused_rather_than_immortal(self, signing_key):
        private_pem, public_pem, _ = signing_key
        payload = self._payload()
        payload.pop("expires_at_ms")
        signature = sign_provisioning_payload(payload, private_pem=private_pem)
        with pytest.raises(ProvisioningError) as caught:
            verify_provisioning_payload(
                payload, signature, trusted_keys={SIGNING_KID: public_pem}, kid=SIGNING_KID,
            )
        assert caught.value.reason == "provisioning_payload_has_no_expiry"

    def test_an_unknown_kid_is_refused_before_anything_is_read(self, signing_key):
        private_pem, public_pem, _ = signing_key
        payload = self._payload()
        signature = sign_provisioning_payload(payload, private_pem=private_pem)
        with pytest.raises(ProvisioningError) as caught:
            verify_provisioning_payload(
                payload, signature, trusted_keys={SIGNING_KID: public_pem}, kid="other",
            )
        assert caught.value.reason == "provisioning_unknown_kid"

    def test_a_payload_altered_after_signing_is_refused(self, signing_key):
        private_pem, public_pem, _ = signing_key
        payload = self._payload()
        signature = sign_provisioning_payload(payload, private_pem=private_pem)
        payload["gateway_url"] = "https://attacker.example"
        with pytest.raises(ProvisioningError) as caught:
            verify_provisioning_payload(
                payload, signature, trusted_keys={SIGNING_KID: public_pem}, kid=SIGNING_KID,
            )
        assert caught.value.reason == "provisioning_signature_invalid"

    def test_an_unsupported_version_is_refused_rather_than_parsed(self, signing_key):
        private_pem, public_pem, _ = signing_key
        payload = self._payload(payload_version=PROVISIONING_PAYLOAD_VERSION + 1)
        signature = sign_provisioning_payload(payload, private_pem=private_pem)
        with pytest.raises(ProvisioningError) as caught:
            verify_provisioning_payload(
                payload, signature, trusted_keys={SIGNING_KID: public_pem}, kid=SIGNING_KID,
            )
        assert caught.value.reason == "provisioning_payload_version_unsupported"

    def test_a_short_token_is_refused_at_construction(self):
        for kwargs, reason in (
            ({"pairing_token": "short"}, "provisioning_pairing_token_too_short"),
            ({"bootstrap_token": "short"}, "provisioning_bootstrap_token_too_short"),
            ({"attestation_challenge": "  "}, "provisioning_challenge_missing"),
        ):
            base = dict(
                gateway_url="https://van.example", pairing_token="p" * 40,
                bootstrap_token="b" * 40, attestation_challenge="chal",
            )
            base.update(kwargs)
            with pytest.raises(ProvisioningError) as caught:
                build_provisioning_payload(**base)
            assert caught.value.reason == reason
