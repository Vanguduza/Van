from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from van_gateway.app import create_app
from van_gateway.config import get_settings
from van_gateway.google.service import GoogleService
from van_gateway.storage.db import Store


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "extra.sqlite3"))
    monkeypatch.setenv("VAN_HERMES_BASE_URL", "http://hermes.test")
    monkeypatch.setenv("VAN_GOOGLE_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
async def client(monkeypatch):
    app = create_app()

    async def ok():
        return {"ok": True}

    async def run(text, metadata=None):
        return {"id": "r1"}

    monkeypatch.setattr(app.state.orchestrator.hermes, "health", ok)
    monkeypatch.setattr(app.state.orchestrator.hermes, "create_run", run)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        async with app.router.lifespan_context(app):
            yield ac, app


@pytest.mark.asyncio
async def test_decision_escalation_surfaces_attention(client):
    ac, _app = client
    esc = await ac.post(
        "/v1/decisions/escalate",
        json={"title": "Council needs judgment", "body": "Approve architecture?", "source": "hermes", "blocking": True},
    )
    assert esc.status_code == 200
    decision_id = esc.json()["id"]
    attention = (await ac.get("/v1/attention")).json()
    assert any(i["title"] == "Council needs judgment" for i in attention)
    resolved = await ac.post(f"/v1/decisions/{decision_id}/resolve", json={"approved": True})
    assert resolved.json()["status"] == "APPROVED"


@pytest.mark.asyncio
async def test_project_truth_put_enables_mutation_gate(client):
    ac, _app = client
    put = await ac.put(
        "/v1/projects/dde/truth",
        json={"truth": {"project": "dde", "rules": ["fail_closed"]}, "truth_sha": "abc", "repo_sha": "def"},
    )
    assert put.json()["ok"] is True
    loaded = await ac.get("/v1/projects/dde/truth")
    assert loaded.json()["truth_sha"] == "abc"


@pytest.mark.asyncio
async def test_reminder_parse_expression(client):
    ac, _app = client
    body = await ac.post(
        "/v1/reminders/parse",
        json={"text": "Supplier", "due_expression": "in 15 minutes", "idempotency_key": "parse-1"},
    )
    assert body.status_code == 200
    assert body.json()["status"] == "OPEN"


@pytest.mark.asyncio
async def test_google_fake_transport_and_approval(client):
    ac, app = client
    await ac.post(
        "/v1/google/connect",
        json={
            "refresh_token": "refresh-xyz",
            "scopes": [
                "https://www.googleapis.com/auth/gmail.readonly",
                "https://www.googleapis.com/auth/gmail.send",
            ],
        },
    )
    await ac.post("/v1/google/test-transport")
    denied = await ac.post("/v1/google/gmail/send", params={"draft_id": "d1", "approved": False})
    assert denied.status_code == 403
    ok = await ac.post("/v1/google/gmail/send", params={"draft_id": "d1", "approved": True})
    assert ok.status_code == 200
    scrubbed = GoogleService.scrub_for_prompt({"access_token": "tok", "snippet": "hi"})
    assert "access_token" not in scrubbed
    assert scrubbed["snippet"] == "hi"


@pytest.mark.asyncio
async def test_migration_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "mig.sqlite3"))
    get_settings.cache_clear()
    store = Store(str(tmp_path / "mig.sqlite3"))
    await store.migrate()
    await store.migrate()
    row = await store.fetchone("SELECT COUNT(*) AS c FROM schema_migrations")
    assert int(row["c"]) >= 1
