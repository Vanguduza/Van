from __future__ import annotations

import json
import time

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from van_gateway.app import create_app
from van_gateway.auth.service import AuthService
from van_gateway.config import get_settings


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "iso.sqlite3"))
    monkeypatch.setenv("VAN_HERMES_BASE_URL", "http://hermes.test")
    monkeypatch.setenv("VAN_GOOGLE_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", "test-internal-token")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
async def client(monkeypatch):
    app = create_app()

    async def ok():
        return {"ok": True, "profile": "van"}

    async def run(text, metadata=None):
        return {"id": "r1", "status": "accepted", "input": text, "metadata": metadata or {}}

    monkeypatch.setattr(app.state.orchestrator.hermes, "health", ok)
    monkeypatch.setattr(app.state.orchestrator.hermes, "create_run", run)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        async with app.router.lifespan_context(app):
            yield ac, app


HEADERS = {"X-Van-Internal-Token": "test-internal-token"}


async def _enroll(ac, app, device_id: str, secret: str) -> None:
    await ac.post(
        "/v1/devices/enroll",
        json={"device_id": device_id, "device_secret": secret, "public_key_pem": "PEM"},
    )
    app.state.auth.remember_secret(device_id, secret)


async def _put_truth(ac, project_id: str, sha: str = "truth-sha") -> None:
    resp = await ac.put(
        f"/v1/projects/{project_id}/truth",
        headers=HEADERS,
        json={"truth": {"project_id": project_id, "rules": ["fail_closed"]}, "truth_sha": sha, "repo_sha": "repo"},
    )
    assert resp.status_code == 200


async def _a3(ac, app, *, device_id: str, secret: str, project_id: str, command_id: str, key: str):
    issued = int(time.time())
    text = f"mutate {project_id}"
    canonical = AuthService.canonical_command(command_id, key, device_id, issued, text, "A3", project_id)
    req = {
        "command_id": command_id,
        "idempotency_key": key,
        "device_id": device_id,
        "issued_at_unix": issued,
        "signature": app.state.auth.sign(device_id, canonical),
        "text": text,
        "action_class": "A3",
        "project_id": project_id,
    }
    return (await ac.post("/v1/commands", json=req)).json()


@pytest.mark.asyncio
async def test_unknown_project_truth_get_is_rejected(client):
    ac, _app = client
    body = (await ac.get("/v1/projects/notaproject/truth")).json()
    assert body["ok"] is False
    assert body["error"] == "unknown_project"
    assert body["degraded"] == "REPO_UNAVAILABLE"


@pytest.mark.asyncio
async def test_unknown_project_truth_put_is_404(client):
    ac, _app = client
    r = await ac.put(
        "/v1/projects/notaproject/truth",
        headers=HEADERS,
        json={"truth": {"project_id": "notaproject"}, "truth_sha": "abc", "repo_sha": "def"},
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "unknown_project"


@pytest.mark.asyncio
async def test_truth_body_project_mismatch_rejected(client):
    ac, _app = client
    r = await ac.put(
        "/v1/projects/gtr/truth",
        headers=HEADERS,
        json={"truth": {"project_id": "dde"}, "truth_sha": "abc", "repo_sha": "def"},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "truth_project_mismatch"


@pytest.mark.asyncio
async def test_a3_mutation_for_unknown_project_is_degraded(client, monkeypatch):
    ac, app = client
    await _enroll(ac, app, "dev-iso-1", "s1")
    called = {"n": 0}

    async def run(text, metadata=None):
        called["n"] += 1
        return {"id": "should-not-run"}

    monkeypatch.setattr(app.state.orchestrator.hermes, "create_run", run)
    body = await _a3(ac, app, device_id="dev-iso-1", secret="s1", project_id="notaproject", command_id="c-iso-1", key="k-iso-1")
    assert body["status"] == "degraded"
    assert "REPO_UNAVAILABLE" in body["degraded"]
    assert called["n"] == 0


@pytest.mark.asyncio
async def test_a4_with_approval_still_requires_project_truth(client):
    ac, app = client
    await _enroll(ac, app, "dev-iso-2", "s2")
    issued = int(time.time())
    text = "wipe staging"
    canonical = AuthService.canonical_command("c-iso-a4", "k-iso-a4", "dev-iso-2", issued, text, "A4", "gtr")
    req = {
        "command_id": "c-iso-a4",
        "idempotency_key": "k-iso-a4",
        "device_id": "dev-iso-2",
        "issued_at_unix": issued,
        "signature": app.state.auth.sign("dev-iso-2", canonical),
        "text": text,
        "action_class": "A4",
        "project_id": "gtr",
        "approval_token": "owner-approved",
    }
    body = (await ac.post("/v1/commands", json=req)).json()
    assert body["status"] == "degraded"
    assert "STALE_PROJECT_TRUTH" in body["degraded"]


@pytest.mark.asyncio
async def test_project_a_truth_does_not_authorize_project_b_mutation(client):
    ac, app = client
    await _enroll(ac, app, "dev-iso-3", "s3")
    await _put_truth(ac, "dde", "dde-sha")
    gtr = await _a3(ac, app, device_id="dev-iso-3", secret="s3", project_id="gtr", command_id="c-gtr", key="k-gtr")
    assert gtr["status"] == "degraded"
    assert "STALE_PROJECT_TRUTH" in gtr["degraded"]
    dde = await _a3(ac, app, device_id="dev-iso-3", secret="s3", project_id="dde", command_id="c-dde", key="k-dde")
    assert dde["status"] == "accepted"


@pytest.mark.asyncio
async def test_audit_records_before_and_after_for_accepted_mutation(client):
    ac, app = client
    await _enroll(ac, app, "dev-iso-4", "s4")
    await _put_truth(ac, "dde", "audit-sha")
    body = await _a3(ac, app, device_id="dev-iso-4", secret="s4", project_id="dde", command_id="c-aud", key="k-aud")
    assert body["status"] == "accepted"
    row = await app.state.store.fetchone(
        "SELECT project_id, capability, before_json, after_json FROM audit WHERE command_id = ? AND result = 'accepted'",
        ("c-aud",),
    )
    assert row is not None
    assert row["project_id"] == "dde"
    assert row["capability"] == "A3"
    before = json.loads(row["before_json"])
    after = json.loads(row["after_json"])
    assert before["truth_sha"] == "audit-sha"
    assert after["hermes_run"]["id"] == "r1"


@pytest.mark.asyncio
async def test_audit_records_before_snapshot_on_truth_gate_denial(client):
    ac, app = client
    await _enroll(ac, app, "dev-iso-5", "s5")
    body = await _a3(ac, app, device_id="dev-iso-5", secret="s5", project_id="aeci", command_id="c-den", key="k-den")
    assert body["status"] == "degraded"
    row = await app.state.store.fetchone(
        "SELECT failure_reason, before_json, after_json FROM audit WHERE command_id = ? AND result = 'degraded'",
        ("c-den",),
    )
    assert row is not None
    assert row["failure_reason"] == "truth_gate"
    before = json.loads(row["before_json"])
    assert before["error"] in {"truth_missing", "truth_stale"}
    assert row["after_json"] in (None, "", "{}") or json.loads(row["after_json"] or "{}") == {}
