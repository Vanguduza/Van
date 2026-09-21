"""ADR-RB-025 — the binding has to cost an attacker something, driven through the ingress.

`OwnerDeviceBindingService.require_proof` was written, tested against itself, and called by
nothing. That is the exact shape of a green implementation over a false outcome: the
attestation parser was correct, the policy was correct, the proof verifier was correct, and
a stolen device token still reached every owner route, while `/v1/device-binding/status`
answered `bound: true`. The counterexample that the unit tests could never see is the one
this file starts with: a request with **no proof header at all**.

So these drive the HTTP surface rather than the service. The questions are:

* does a bound device's unsigned privileged request get refused;
* can a valid proof be lifted from one request onto another;
* is a read still a read, or has a Keystore signature been put in the polling path;
* does the handler still see its body after the middleware has read it to verify the proof.

The last one is not a security property but it is the one most likely to break everything
at once, and it is invisible to any test that only checks status codes on refusals.
"""

from __future__ import annotations

import base64
import hashlib
import json

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils as asym_utils
from httpx import ASGITransport, AsyncClient

from test_owner_device_binding import PACKAGE, SIGNING_CERT, _attestation, _keypair
from van_gateway.app import create_app
from van_gateway.auth.device_proof import request_signing_input
from van_gateway.browser.stream_grants import generate_signing_key
from van_gateway.config import get_settings

INGRESS = "proof-ingress-token-0123456789"
INTERNAL = "proof-internal-token-0123456789"
SIGNING_KID = "browser-stream-signing-test"
SESSIONS = "/v1/browser/interactive-sessions"


@pytest.fixture
def _settings(tmp_path, monkeypatch):
    key = generate_signing_key(SIGNING_KID)
    key_path = tmp_path / "stream-signing.pem"
    key_path.write_text(key.private_pem)
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "proof.sqlite3"))
    monkeypatch.setenv("VAN_HERMES_BASE_URL", "http://hermes.invalid")
    monkeypatch.setenv("VAN_GOOGLE_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", INGRESS)
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", INTERNAL)
    monkeypatch.setenv("VAN_BROWSER_STREAM_SIGNING_KEY_FILE", str(key_path))
    monkeypatch.setenv("VAN_BROWSER_STREAM_SIGNING_KID", SIGNING_KID)
    monkeypatch.setenv("VAN_BROWSER_STREAM_SIGNAL_URL", "https://stream.example/rtc")
    monkeypatch.setenv("VAN_BROWSER_STREAM_ICE_SERVERS", "[]")
    monkeypatch.setenv("VAN_OWNER_DEVICE_PACKAGE", PACKAGE)
    monkeypatch.setenv("VAN_OWNER_DEVICE_SIGNING_CERT_SHA256", SIGNING_CERT)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def client(_settings):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        async with app.router.lifespan_context(app):
            await app.state.browser.broker.register_profile(profile_alias="authenticated_owner")
            yield ac, app


async def _paired(app, label="owner-phone"):
    ticket = await app.state.auth.create_pairing_ticket(label)
    return await app.state.auth.pair_device(ticket.token, label, "s" * 32, "PEM", label)


async def _bind(app, device_id: str):
    """Enrol `device_id` the way the phone does, and keep its private key."""
    service = app.state.owner_device_bindings
    token, challenge = await service.create_bootstrap_token()
    pem, private_key = _keypair()
    await service.bind(
        token=token,
        device_id=device_id,
        public_key_pem=pem,
        attestation_extension=_attestation(challenge.encode()),
    )
    return private_key


def _proof_headers(private_key, *, method: str, path: str, device_id: str, body: bytes):
    """What `DeviceProofSigner` on the phone produces for this request."""
    issued_at_ms = int(__import__("time").time() * 1000)
    signing_input = request_signing_input(
        method=method,
        path=path,
        device_id=device_id,
        issued_at_ms=issued_at_ms,
        body_sha256=hashlib.sha256(body).hexdigest(),
    )
    der = private_key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
    r, s = asym_utils.decode_dss_signature(der)
    raw = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    return {
        "X-Van-Device-Proof": base64.b64encode(raw).decode("ascii"),
        "X-Van-Device-Proof-Issued-At": str(issued_at_ms),
    }


def _base_headers(enrolled):
    return {"X-Van-Ingress-Token": INGRESS, "X-Van-Device-Token": enrolled.access_token}


CREATE_BODY = {
    "profile_alias": "authenticated_owner",
    "viewport": {"width": 1080, "height": 2016, "device_scale_factor": 1.0},
}


@pytest.mark.asyncio
class TestProofIsActuallyRequired:

    async def test_a_bound_device_cannot_act_without_signing_the_request(self, client):
        ac, app = client
        enrolled = await _paired(app)
        await _bind(app, enrolled.device.device_id)

        response = await ac.post(SESSIONS, json=CREATE_BODY, headers=_base_headers(enrolled))

        assert response.status_code == 401
        assert response.json()["detail"] == "device_proof_required"

    async def test_a_signed_request_from_the_bound_device_is_admitted(self, client):
        """The other half: a gate that refused everything would also pass the test above."""
        ac, app = client
        enrolled = await _paired(app)
        private_key = await _bind(app, enrolled.device.device_id)
        body = json.dumps(CREATE_BODY).encode()

        response = await ac.post(
            SESSIONS,
            content=body,
            headers={
                **_base_headers(enrolled),
                "Content-Type": "application/json",
                **_proof_headers(
                    private_key, method="POST", path=SESSIONS,
                    device_id=enrolled.device.device_id, body=body,
                ),
            },
        )

        assert response.status_code == 200, response.text
        # The body survived being read in the middleware. This is the regression test for
        # that, not a redundant assertion: if Starlette ever stops caching a body read in
        # `dispatch`, every proved route starts failing as a 422 about a missing field,
        # several layers away from the cause.
        assert response.json()["profile_alias"] == "authenticated_owner"

    async def test_a_proof_cannot_be_lifted_onto_a_different_request(self, client):
        """The signature covers the body digest, so a replay onto other work fails."""
        ac, app = client
        enrolled = await _paired(app)
        private_key = await _bind(app, enrolled.device.device_id)
        signed_body = json.dumps(CREATE_BODY).encode()
        headers = _proof_headers(
            private_key, method="POST", path=SESSIONS,
            device_id=enrolled.device.device_id, body=signed_body,
        )

        other_body = json.dumps({**CREATE_BODY, "profile_alias": "public_research"}).encode()
        response = await ac.post(
            SESSIONS,
            content=other_body,
            headers={**_base_headers(enrolled), "Content-Type": "application/json", **headers},
        )

        assert response.status_code == 401
        assert response.json()["detail"] == "device_proof_invalid"

    async def test_a_proof_for_one_path_does_not_open_another(self, client):
        ac, app = client
        enrolled = await _paired(app)
        private_key = await _bind(app, enrolled.device.device_id)
        body = json.dumps(CREATE_BODY).encode()
        headers = _proof_headers(
            private_key, method="POST", path="/v1/commands",
            device_id=enrolled.device.device_id, body=body,
        )

        response = await ac.post(
            SESSIONS,
            content=body,
            headers={**_base_headers(enrolled), "Content-Type": "application/json", **headers},
        )

        assert response.status_code == 401

    async def test_a_second_device_cannot_borrow_the_owners_proof(self, client):
        """A stolen token plus a captured proof is still not the bound key.

        The proof names the device it was issued for, so presenting it under another
        device's token fails on the binding lookup rather than on the signature.
        """
        ac, app = client
        owner = await _paired(app, "owner-phone")
        private_key = await _bind(app, owner.device.device_id)
        intruder = await _paired(app, "second-phone")
        body = json.dumps(CREATE_BODY).encode()
        headers = _proof_headers(
            private_key, method="POST", path=SESSIONS,
            device_id=owner.device.device_id, body=body,
        )

        response = await ac.post(
            SESSIONS,
            content=body,
            headers={**_base_headers(intruder), "Content-Type": "application/json", **headers},
        )

        # The exact reason matters, and a looser assertion hid a real gap: with the
        # ownership check removed this still refused, as `device_not_bound`, because the
        # proof names the device it was issued for. Both refuse; they say different things,
        # and "you are not the owner's device" is the one an operator needs in the log.
        assert response.status_code == 403
        assert response.json()["detail"] == "device_not_owner_device"


@pytest.mark.asyncio
class TestWhatIsNotGated:

    async def test_a_read_does_not_need_a_hardware_signature(self, client):
        """A proof on every poll would put a Keystore operation in the battery path."""
        ac, app = client
        enrolled = await _paired(app)
        private_key = await _bind(app, enrolled.device.device_id)
        body = json.dumps(CREATE_BODY).encode()
        created = await ac.post(
            SESSIONS,
            content=body,
            headers={
                **_base_headers(enrolled), "Content-Type": "application/json",
                **_proof_headers(
                    private_key, method="POST", path=SESSIONS,
                    device_id=enrolled.device.device_id, body=body,
                ),
            },
        )
        session_id = created.json()["session_id"]

        response = await ac.get(f"{SESSIONS}/{session_id}", headers=_base_headers(enrolled))

        assert response.status_code == 200

    async def test_an_unbound_device_still_works_and_says_so(self, client):
        """The migration state, stated rather than silent.

        A deployment that already has a paired phone must not be locked out by shipping
        this. The downgrade is readable: `bound` is false, and `require_device_binding`
        turns the fallback off once enrolment has run.
        """
        ac, app = client
        enrolled = await _paired(app)

        created = await ac.post(SESSIONS, json=CREATE_BODY, headers=_base_headers(enrolled))
        status = await ac.get("/v1/device-binding/status", headers=_base_headers(enrolled))

        assert created.status_code == 200
        assert status.json() == {"configured": True, "bound": False}

    async def test_enrolment_itself_is_never_gated_on_a_key_it_is_creating(self, client):
        """Otherwise the first enrolment on a fresh device could never succeed."""
        ac, app = client
        service = app.state.owner_device_bindings
        token, challenge = await service.create_bootstrap_token()
        pem, _ = _keypair()

        response = await ac.post(
            "/v1/devices/bootstrap/attest",
            json={
                "token": token,
                "device_id": "s24-fresh",
                "public_key_pem": pem,
                "attestation_extension_b64": base64.b64encode(
                    _attestation(challenge.encode())
                ).decode(),
            },
        )

        assert response.status_code == 200, response.text


class TestTheGateCoversWhatItClaims:

    def test_the_predicate_names_the_mutating_owner_surfaces(self):
        """Read directly from the app so the list cannot drift from the middleware's."""
        from van_gateway.browser.interactive_api import is_interactive_browser_owner_route
        from van_gateway.session.api import is_session_owner_route

        assert is_interactive_browser_owner_route(f"{SESSIONS}/ibs_1/take-control")
        assert is_session_owner_route("/v1/session/submit")
        # And the surfaces that must stay outside it, because they have no bound key yet.
        assert not is_interactive_browser_owner_route("/v1/devices/bootstrap/attest")
        assert not is_session_owner_route("/v1/devices/bootstrap/challenge")
