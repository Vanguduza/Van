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
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", "test-ingress-token-0123456789abcdef")
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", "test-internal-token")
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
    async with AsyncClient(transport=transport, base_url="http://test", headers={"X-Van-Ingress-Token": "test-ingress-token-0123456789abcdef"}) as ac:
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
async def test_project_truth_put_requires_internal_token(client):
    ac, _app = client
    denied = await ac.put(
        "/v1/projects/dde/truth",
        json={"truth": {"project": "dde", "rules": ["fail_closed"]}, "truth_sha": "abc", "repo_sha": "def"},
    )
    assert denied.status_code in {403, 503}
    put = await ac.put(
        "/v1/projects/dde/truth",
        headers={"X-Van-Internal-Token": "test-internal-token"},
        json={"truth": {"project": "dde", "rules": ["fail_closed"]}, "truth_sha": "abc", "repo_sha": "def"},
    )
    assert put.status_code == 200
    assert put.json()["ok"] is True
    loaded = await ac.get("/v1/projects/dde/truth")
    assert loaded.json()["truth_sha"] == "abc"


@pytest.mark.asyncio
async def test_health_ok_false_when_hermes_offline(client, monkeypatch):
    ac, app = client

    async def offline():
        return {"ok": False, "degraded": "HERMES_OFFLINE"}

    monkeypatch.setattr(app.state.orchestrator.hermes, "health", offline)
    body = (await ac.get("/health")).json()
    assert body["ok"] is False
    assert body["hermes"]["ok"] is False
    assert any(item["code"] == "HERMES_OFFLINE" for item in body["degraded"])


@pytest.mark.asyncio
async def test_project_truth_put_enables_mutation_gate(client):
    ac, _app = client
    put = await ac.put(
        "/v1/projects/dde/truth",
        headers={"X-Van-Internal-Token": "test-internal-token"},
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
    ac, _app = client
    headers = {"X-Van-Internal-Token": "test-internal-token"}
    connected = await ac.post(
        "/v1/google/connect",
        headers=headers,
        json={
            "refresh_token": "refresh-xyz",
            "scopes": [
                "https://www.googleapis.com/auth/gmail.readonly",
                "https://www.googleapis.com/auth/gmail.send",
            ],
        },
    )
    assert connected.status_code == 200
    enabled = await ac.post("/v1/google/test-transport", headers=headers)
    assert enabled.status_code == 200
    denied = await ac.post("/v1/google/gmail/send", headers=headers, params={"draft_id": "d1", "approved": False})
    assert denied.status_code == 403
    ok = await ac.post("/v1/google/gmail/send", headers=headers, params={"draft_id": "d1", "approved": True})
    assert ok.status_code == 200
    scrubbed = GoogleService.scrub_for_prompt({"access_token": "tok", "snippet": "hi"})
    assert "access_token" not in scrubbed
    assert scrubbed["snippet"] == "hi"


@pytest.mark.asyncio
async def test_google_control_plane_rejects_missing_internal_token(client):
    ac, _app = client
    response = await ac.post(
        "/v1/google/connect",
        json={"refresh_token": "refresh-xyz", "scopes": ["https://www.googleapis.com/auth/gmail.readonly"]},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_migration_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "mig.sqlite3"))
    get_settings.cache_clear()
    store = Store(str(tmp_path / "mig.sqlite3"))
    await store.migrate()
    await store.migrate()
    row = await store.fetchone("SELECT COUNT(*) AS c FROM schema_migrations")
    assert int(row["c"]) >= 1


@pytest.mark.asyncio
async def test_internal_control_token_is_not_general_ingress(client):
    _ac, app = client
    transport = ASGITransport(app=app)
    headers = {"X-Van-Internal-Token": "test-internal-token"}
    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as internal:
        put = await internal.put(
            "/v1/projects/dde/truth",
            json={"truth": {"project": "dde"}, "truth_sha": "abc", "repo_sha": "def"},
        )
        assert put.status_code == 200

        general = await internal.get("/v1/projects")
        assert general.status_code == 401
        assert general.json()["detail"] == "ingress_auth_failed"
