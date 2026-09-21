"""GAP-F-024 — the owner can revoke Google from the phone; GAP-F-020 — payload scrubbing is
live on every Google read the Hermes shim can call."""
from __future__ import annotations

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from van_gateway.app import create_app
from van_gateway.config import get_settings
from van_gateway.google.transport import FakeGoogleTransport

INGRESS = "test-ingress-token-0123456789abcdef"
INTERNAL = "test-internal-token-0123456789abcdef0123"


@pytest.fixture(autouse=True)
def _settings(tmp_path, monkeypatch):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "g.sqlite3"))
    monkeypatch.setenv("VAN_HERMES_BASE_URL", "http://hermes.invalid")
    monkeypatch.setenv("VAN_GOOGLE_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", INGRESS)
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", INTERNAL)
    monkeypatch.setenv("VAN_DEVICE_ENROLMENT_TOKEN", INTERNAL)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def client():
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test",
        headers={"X-Van-Ingress-Token": INGRESS},
    ) as ac:
        async with app.router.lifespan_context(app):
            ticket = await app.state.auth.create_pairing_ticket("phone")
            paired = await app.state.auth.pair_device(ticket.token, "phone", "phone-secret", "PEM", "phone")
            ac.headers.update({"X-Van-Device-Token": paired.access_token})
            yield ac, app


class LeakyTransport(FakeGoogleTransport):
    """A provider answer that (wrongly) carries credential-shaped keys."""

    async def gmail_search(self, token, q):
        return [{"id": "m1", "snippet": "hello", "access_token": "LEAK", "nested": {"api_key": "LEAK", "ok": 1}}]

    async def calendar_agenda(self, token):
        return [{"id": "e1", "summary": "standup", "authorization": "LEAK"}]


@pytest.mark.asyncio
async def test_owner_device_can_revoke_google(client):
    ac, app = client
    await app.state.google.store_refresh_token("owner", "refresh-token-value", ["https://www.googleapis.com/auth/gmail.readonly"])
    before = await ac.get("/v1/google/status")
    assert before.json()["connected"] is True
    r = await ac.post("/v1/google/owner-revoke")
    assert r.status_code == 200, r.text
    assert r.json()["connected"] is False
    rows = await app.state.store.fetchall("SELECT status, encrypted_refresh_token FROM google_connections WHERE owner_id = 'owner'")
    assert rows and rows[0]["status"] == "revoked" and rows[0]["encrypted_refresh_token"] == ""


@pytest.mark.asyncio
async def test_owner_revoke_needs_a_paired_device(client):
    ac, app = client
    r = await ac.post("/v1/google/owner-revoke", headers={"X-Van-Device-Token": "not-a-device"})
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_google_reads_are_scrubbed_before_leaving_the_gateway(client):
    ac, app = client
    await app.state.google.store_refresh_token("owner", "refresh-token-value", [
        "https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/calendar",
    ])
    app.state.google.transport = LeakyTransport()
    headers = {"X-Van-Internal-Token": INTERNAL}
    r = await ac.get("/v1/google/gmail/search", params={"q": "x"}, headers=headers)
    assert r.status_code == 200, r.text
    text = r.text.lower()
    assert "leak" not in text, text
    assert r.json()["messages"][0]["nested"]["ok"] == 1
    r = await ac.get("/v1/google/calendar/agenda", headers=headers)
    assert r.status_code == 200, r.text
    assert "leak" not in r.text.lower()
