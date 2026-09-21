"""Rev 1.5 §§6, 34 — the interactive browser routes, driven through the ingress.

Protocol rule 19: these drive the HTTP surface rather than calling the service, because the
two questions are different. `test_interactive_browser_session.py` asks whether the session
logic is right. This asks whether the owner's phone can reach it, whether anyone else can,
and whether the route classifier agrees with itself — the exact seam where `P0-SEC-001`
found a Hermes-only surface reachable with a device token, and where `P2-GOOG-004` found six
routes outside the scope set.

The important cases here are the refusals:

* a second paired device may not touch the owner's session;
* Hermes' internal control credential is not a substitute for the owner's device on these
  routes, and the owner's device is not a substitute for Hermes on the others;
* with no signing key configured, the routes do not exist at all rather than issuing a
  credential no stream host can verify.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from van_gateway.app import create_app
from van_gateway.browser.interactive_api import is_interactive_browser_owner_route
from van_gateway.browser.stream_grants import (
    StreamGrantVerifier,
    generate_signing_key,
)
from van_gateway.config import get_settings

INGRESS = "interactive-ingress-token-0123456789"
INTERNAL = "interactive-internal-token-0123456789"
SIGNING_KID = "browser-stream-signing-test"
SESSIONS = "/v1/browser/interactive-sessions"


@pytest.fixture
def signing_key(tmp_path):
    key = generate_signing_key(SIGNING_KID)
    path = tmp_path / "stream-signing.pem"
    path.write_text(key.private_pem)
    return key, path


@pytest.fixture
def _settings(tmp_path, monkeypatch, signing_key):
    _, key_path = signing_key
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "interactive.sqlite3"))
    monkeypatch.setenv("VAN_HERMES_BASE_URL", "http://hermes.invalid")
    monkeypatch.setenv("VAN_GOOGLE_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", INGRESS)
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", INTERNAL)
    monkeypatch.setenv("VAN_BROWSER_STREAM_SIGNING_KEY_FILE", str(key_path))
    monkeypatch.setenv("VAN_BROWSER_STREAM_SIGNING_KID", SIGNING_KID)
    monkeypatch.setenv("VAN_BROWSER_STREAM_SIGNAL_URL", "https://stream.example/rtc")
    monkeypatch.setenv(
        "VAN_BROWSER_STREAM_ICE_SERVERS", '[{"urls": ["stun:stun.example:3478"]}]'
    )
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def client(_settings):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        async with app.router.lifespan_context(app):
            await app.state.browser.broker.register_profile(profile_alias="public_research")
            await app.state.browser.broker.register_profile(profile_alias="authenticated_owner")
            yield ac, app


async def _device(app, label="owner-phone"):
    ticket = await app.state.auth.create_pairing_ticket(label)
    return await app.state.auth.pair_device(
        ticket.token, label, "s" * 32, "PEM", label
    )


def _headers(enrolled):
    return {"X-Van-Ingress-Token": INGRESS, "X-Van-Device-Token": enrolled.access_token}


async def _create(ac, enrolled, **body):
    payload = {
        "profile_alias": "authenticated_owner",
        "viewport": {"width": 1080, "height": 2016, "device_scale_factor": 1.0},
    }
    payload.update(body)
    return await ac.post(SESSIONS, json=payload, headers=_headers(enrolled))


# --------------------------------------------------------------------------- classifier


class TestRouteClassification:
    def test_the_owner_route_predicate_covers_the_whole_surface(self):
        assert is_interactive_browser_owner_route(SESSIONS)
        assert is_interactive_browser_owner_route(f"{SESSIONS}/ibs_1")
        assert is_interactive_browser_owner_route(f"{SESSIONS}/ibs_1/take-control")

    def test_it_does_not_swallow_the_rest_of_the_browser_surface(self):
        """The Hermes-only routes must stay Hermes-only.

        A predicate that matched `/v1/browser/` would hand the entire Browser Fabric to
        anything holding a device token, which is the fall-through P0-SEC-001 closed.
        """
        assert not is_interactive_browser_owner_route("/v1/browser/assignments")
        assert not is_interactive_browser_owner_route("/v1/browser/tasks")
        assert not is_interactive_browser_owner_route("/v1/browser/health")
        # A path that merely starts with the same characters is not the same surface.
        assert not is_interactive_browser_owner_route("/v1/browser/interactive-sessions-export")


@pytest.mark.asyncio
class TestTheClassifierAgreesWithTheRoutes:
    """The invariant, over the routes that actually exist.

    Asserting it per-route rather than per-string is what stops the two halves drifting:
    every mounted interactive path must be owner-authenticated, and every other browser
    mutation must still be Hermes-only. A second classifier that disagreed with this one
    used to live in app.py; it had no callers and was deleted when a mutation to it changed
    nothing.
    """

    async def test_every_mounted_interactive_route_is_owner_authenticated(self, client):
        _, app = client
        paths = [p for p in app.openapi()["paths"] if "interactive-sessions" in p]
        assert paths, "the routes must be mounted for this to mean anything"
        for path in paths:
            concrete = path.replace("{session_id}", "ibs_probe")
            assert is_interactive_browser_owner_route(concrete), path

    async def test_the_rest_of_the_browser_surface_is_still_hermes_only(self, client):
        ac, app = client
        device = await _device(app, "probe-phone")
        others = [
            p for p in app.openapi()["paths"]
            if p.startswith("/v1/browser/") and "interactive-sessions" not in p
        ]
        assert others, "there must be other browser routes for this to mean anything"
        refused = []
        for path in others:
            spec = app.openapi()["paths"][path]
            if "post" not in spec:
                continue
            resp = await ac.post(path.replace("{task_id}", "t").replace("{escalation_id}", "e"),
                                 json={}, headers=_headers(device))
            refused.append((path, resp.status_code))
        assert refused, "no browser POST route was probed"
        assert all(code == 403 for _, code in refused), refused


# --------------------------------------------------------------------------- the routes


@pytest.mark.asyncio
class TestOwnerSurface:
    async def test_the_owner_can_open_a_session(self, client):
        ac, app = client
        device = await _device(app)
        resp = await _create(ac, device)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["state"] == "AUTHORIZED"
        assert body["control_holder"] == "OWNER"
        assert body["owner_readable_state"] == "Allowed, not started"
        # §5.2 — the response says outright that this is not a work outcome.
        assert body["is_work_outcome"] is False

    async def test_a_session_needs_a_device_identity(self, client):
        """Ingress alone is the tunnel's credential, not the owner's."""
        ac, _ = client
        resp = await ac.post(
            SESSIONS,
            json={"profile_alias": "public_research",
                  "viewport": {"width": 1080, "height": 2016}},
            headers={"X-Van-Ingress-Token": INGRESS},
        )
        assert resp.status_code == 401

    async def test_hermes_internal_control_is_not_an_owner_device(self, client):
        """These routes are the owner's. An internal credential does not stand in for one.

        The reverse case — an owner device reaching a Hermes browser route — is asserted
        below, because the classifier has to be wrong in only one direction to be a hole.
        """
        ac, _ = client
        resp = await ac.post(
            SESSIONS,
            json={"profile_alias": "public_research",
                  "viewport": {"width": 1080, "height": 2016}},
            headers={"X-Van-Ingress-Token": INGRESS, "X-Van-Internal-Token": INTERNAL},
        )
        assert resp.status_code == 401

    async def test_an_owner_device_still_cannot_reach_the_hermes_browser_surface(self, client):
        ac, app = client
        device = await _device(app)
        resp = await ac.post(
            "/v1/browser/tasks", json={}, headers=_headers(device)
        )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "internal_control_unauthorized"

    async def test_a_second_device_cannot_see_or_drive_the_session(self, client):
        """Pairing grants an identity, not the right to drive another device's browser."""
        ac, app = client
        owner = await _device(app, "owner-phone")
        other = await _device(app, "second-phone")
        session_id = (await _create(ac, owner)).json()["session_id"]

        read = await ac.get(f"{SESSIONS}/{session_id}", headers=_headers(other))
        assert read.status_code == 404, "a stranger's session must not even be visible"

        take = await ac.post(f"{SESSIONS}/{session_id}/take-control", headers=_headers(other))
        assert take.status_code == 404

    async def test_a_leased_profile_answers_conflict_rather_than_bad_request(self, client):
        ac, app = client
        owner = await _device(app)
        assert (await _create(ac, owner)).status_code == 200
        second = await _create(ac, owner)
        assert second.status_code == 409

    async def test_an_invented_profile_alias_is_refused(self, client):
        """§0A/B3 — the alias list is owner-approved policy, not a client parameter."""
        ac, app = client
        owner = await _device(app)
        resp = await _create(ac, owner, profile_alias="dial-development")
        assert resp.status_code == 400

    async def test_a_retry_with_the_same_idempotency_key_is_the_same_session(self, client):
        ac, app = client
        owner = await _device(app)
        first = await _create(ac, owner, idempotency_key="phone-retry-1")
        second = await _create(ac, owner, idempotency_key="phone-retry-1")
        assert first.status_code == second.status_code == 200
        assert first.json()["session_id"] == second.json()["session_id"]


@pytest.mark.asyncio
class TestStreamGrantRoute:
    async def test_the_grant_verifies_against_the_configured_key(self, client, signing_key):
        ac, app = client
        key, _ = signing_key
        owner = await _device(app)
        session_id = (await _create(ac, owner)).json()["session_id"]

        resp = await ac.post(f"{SESSIONS}/{session_id}/stream-grant", headers=_headers(owner))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["signal_url"] == "https://stream.example/rtc"
        assert body["ice_servers"] == [{"urls": ["stun:stun.example:3478"]}]

        claims = StreamGrantVerifier({key.kid: key.public_pem()}).verify(body["stream_grant"])
        assert claims["session_id"] == session_id
        # The grant names the device the Gateway authenticated, not one the client chose.
        assert claims["device_id"] == "owner-phone"
        # The grant authorises this viewport, so a client cannot ask the stream host for a
        # surface the Gateway never approved.
        assert claims["max_width"] == 1080

    async def test_the_grant_is_not_for_another_device(self, client):
        ac, app = client
        owner = await _device(app, "owner-phone")
        other = await _device(app, "second-phone")
        session_id = (await _create(ac, owner)).json()["session_id"]
        resp = await ac.post(f"{SESSIONS}/{session_id}/stream-grant", headers=_headers(other))
        assert resp.status_code == 404

    async def test_an_ended_session_mints_no_further_grants(self, client):
        ac, app = client
        owner = await _device(app)
        session_id = (await _create(ac, owner)).json()["session_id"]
        assert (await ac.delete(f"{SESSIONS}/{session_id}", headers=_headers(owner))).status_code == 200
        resp = await ac.post(f"{SESSIONS}/{session_id}/stream-grant", headers=_headers(owner))
        assert resp.status_code == 409


@pytest.mark.asyncio
class TestControlRoutes:
    async def test_delegating_and_taking_back_moves_the_generation(self, client):
        ac, app = client
        owner = await _device(app)
        session_id = (await _create(ac, owner)).json()["session_id"]

        delegated = await ac.post(
            f"{SESSIONS}/{session_id}/delegate-control",
            json={"holder": "HERMES_STAGEHAND", "issued_for": "hermes:van"},
            headers=_headers(owner),
        )
        assert delegated.status_code == 200, delegated.text
        assert delegated.json()["holder"] == "HERMES_STAGEHAND"

        taken = await ac.post(f"{SESSIONS}/{session_id}/take-control", headers=_headers(owner))
        assert taken.status_code == 200
        assert taken.json()["holder"] == "OWNER"
        assert taken.json()["control_generation"] > delegated.json()["control_generation"]

    async def test_an_unknown_holder_is_refused(self, client):
        ac, app = client
        owner = await _device(app)
        session_id = (await _create(ac, owner)).json()["session_id"]
        resp = await ac.post(
            f"{SESSIONS}/{session_id}/delegate-control",
            json={"holder": "SOMEONE_ELSE", "issued_for": "x"},
            headers=_headers(owner),
        )
        assert resp.status_code == 400

    async def test_the_viewport_handshake_is_two_steps(self, client):
        ac, app = client
        owner = await _device(app)
        session_id = (await _create(ac, owner)).json()["session_id"]

        proposed = await ac.post(
            f"{SESSIONS}/{session_id}/viewport",
            json={"width": 2016, "height": 1080, "device_scale_factor": 1.0},
            headers=_headers(owner),
        )
        assert proposed.status_code == 200
        revision = proposed.json()["viewport_revision"]
        assert revision == 2

        stale = await ac.post(
            f"{SESSIONS}/{session_id}/viewport/ack", json={"revision": 1},
            headers=_headers(owner),
        )
        assert stale.status_code == 409

        ok = await ac.post(
            f"{SESSIONS}/{session_id}/viewport/ack", json={"revision": revision},
            headers=_headers(owner),
        )
        assert ok.status_code == 200
        assert ok.json()["acked_viewport_revision"] == revision


@pytest.mark.asyncio
class TestSessionLifecycleRoutes:
    async def test_closing_a_session_is_idempotent(self, client):
        ac, app = client
        owner = await _device(app)
        session_id = (await _create(ac, owner)).json()["session_id"]
        first = await ac.delete(f"{SESSIONS}/{session_id}", headers=_headers(owner))
        second = await ac.delete(f"{SESSIONS}/{session_id}", headers=_headers(owner))
        assert first.status_code == second.status_code == 200
        assert second.json()["state"] == "TERMINATED"

    async def test_tabs_and_downloads_are_readable_and_empty_rather_than_absent(self, client):
        ac, app = client
        owner = await _device(app)
        session_id = (await _create(ac, owner)).json()["session_id"]
        tabs = await ac.get(f"{SESSIONS}/{session_id}/tabs", headers=_headers(owner))
        downloads = await ac.get(f"{SESSIONS}/{session_id}/downloads", headers=_headers(owner))
        assert tabs.status_code == downloads.status_code == 200
        assert tabs.json()["tabs"] == []
        assert downloads.json()["downloads"] == []

    async def test_the_session_event_log_records_the_creation(self, client):
        ac, app = client
        owner = await _device(app)
        session_id = (await _create(ac, owner)).json()["session_id"]
        events = await ac.get(f"{SESSIONS}/{session_id}/events", headers=_headers(owner))
        assert events.status_code == 200
        kinds = {e["event_type"] for e in events.json()["events"]}
        assert "session.created" in kinds


@pytest.mark.asyncio
class TestUnconfiguredDeployment:
    async def test_without_a_signing_key_the_routes_do_not_exist(self, tmp_path, monkeypatch):
        """§42.5 — no route is better than a route that issues an unverifiable credential.

        This is the state of every deployment until the owner provisions a stream host, and
        it must be visibly absent rather than quietly broken.
        """
        monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "unconfigured.sqlite3"))
        monkeypatch.setenv("VAN_HERMES_BASE_URL", "http://hermes.invalid")
        monkeypatch.setenv("VAN_GOOGLE_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
        monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
        monkeypatch.setenv("VAN_INGRESS_TOKEN", INGRESS)
        monkeypatch.setenv("VAN_BROWSER_STREAM_SIGNING_KEY_FILE", "")
        get_settings.cache_clear()
        app = create_app()
        try:
            paths = {p for p in app.openapi()["paths"] if "interactive-sessions" in p}
            assert paths == set()
        finally:
            get_settings.cache_clear()
