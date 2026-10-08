"""The fixed browser client can read task projections using only browser scope.

These tests use create_app and its real authentication middleware. Mounting the
BrowserApi router alone misses the ingress/device gate that blocked assignment
preflight and sealed-evidence readback in production.
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from van_gateway.app import create_app
from van_gateway.browser.worker import AdapterBackedWorker
from van_gateway.config import get_settings

INGRESS = "browser-read-ingress-0123456789abcdef012345"
BROWSER = "browser-read-control-0123456789abcdef012345"
RUNTIME = "browser-read-runtime-0123456789abcdef012345"
WRONG = "browser-read-unknown-0123456789abcdef012345"
HEADERS = {"X-Van-Internal-Token": BROWSER}
DOMAIN = "portal.example.com"
GOAL = "Read the public notes page and report its actual URL and title."
COMMAND_ID = "browser-read-auth-command"


class _Harness:
    async def navigate(self, task, url):
        self.url = url

    async def page_info(self, task):
        return {
            "url": self.url,
            "title": "Public notes",
            "extraction": {"visible_text": "The public notes are available."},
        }


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "browser-read-auth.sqlite3"))
    monkeypatch.setenv("VAN_HERMES_BASE_URL", "http://hermes.invalid")
    monkeypatch.setenv("VAN_GOOGLE_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", INGRESS)
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", "")
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_SCOPED_TOKENS", f"browser:{BROWSER}; runtime:{RUNTIME}")
    monkeypatch.setenv("VAN_DEVICE_ENROLMENT_TOKEN", "")
    monkeypatch.setenv("VAN_OBSERVABILITY_TOKEN", "")
    monkeypatch.setenv("VAN_BROWSER_ENABLED", "1")
    get_settings.cache_clear()
    try:
        app = create_app()
        app.state.browser.worker = AdapterBackedWorker(_Harness())
        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                yield ac, app
    finally:
        get_settings.cache_clear()


async def _create_task(ac):
    response = await ac.post("/v1/browser/tasks", headers=HEADERS, json={
        "profile_alias": "public_research",
        "strategy": "HARNESS",
        "autonomy_tier": "L1_HARNESS_DETERMINISTIC",
        "action_class": "A1",
        "target_domain": DOMAIN,
        "goal": GOAL,
        "mutating": False,
        "command_id": COMMAND_ID,
    })
    assert response.status_code == 200, response.text
    return response.json()


async def _owner_headers(app):
    ticket = await app.state.auth.create_pairing_ticket("browser-read-owner")
    owner = await app.state.auth.pair_device(
        ticket.token, "browser-read-owner", "s" * 32, "PEM", "Browser read owner"
    )
    return {"X-Van-Ingress-Token": INGRESS, "X-Van-Device-Token": owner.access_token}


def _read_paths(task):
    path = f"/v1/browser/tasks/{task['task_id']}"
    return path, path + "/evidence"


@pytest.mark.asyncio
async def test_browser_scope_reaches_assignment_preflight_and_sealed_readback(client):
    ac, _app = client
    task = await _create_task(ac)
    status_path, evidence_path = _read_paths(task)

    # These are the exact fields Global DIAL binds before it dispatches an
    # assignment. The client has no ingress or owner-device credential.
    preflight = await ac.get(status_path, headers=HEADERS)
    assert preflight.status_code == 200, preflight.text
    projection = preflight.json()["task"]
    assert projection["task_id"] == task["task_id"]
    assert projection["status"] == "PENDING"
    assert projection["command_id"] == COMMAND_ID
    assert projection["goal"] == GOAL
    assert projection["target_domain"] == DOMAIN
    assert projection["action_class"] == "A1"
    assert projection["autonomy_tier"] == "L1_HARNESS_DETERMINISTIC"
    before = await ac.get(evidence_path, headers=HEADERS)
    assert before.status_code == 200, before.text
    assert before.json() == []

    assigned = await ac.post("/v1/browser/assignments", headers=HEADERS, json={
        "task_id": projection["task_id"],
        "turn_id": "browser-read-auth-turn",
        "command_id": projection["command_id"],
        "goal": projection["goal"],
        "allowed_domains": [projection["target_domain"]],
        "action_class_ceiling": projection["action_class"],
        "autonomy_tier": projection["autonomy_tier"],
        "max_steps": 4,
        "max_steps_without_progress": 2,
        "plan": {"steps": [
            {"kind": "navigate", "domain": DOMAIN, "url": f"https://{DOMAIN}/notes"},
            {"kind": "read", "domain": DOMAIN},
        ]},
    })
    assert assigned.status_code == 200, assigned.text
    result = assigned.json()
    assert result["succeeded"] is True
    assert result["stop_reason"] == "GOAL_ACHIEVED"
    assert result["session_lease_released"] is True
    evidence_id = result["evidence"]["evidence_id"]

    completed = await ac.get(status_path, headers=HEADERS)
    assert completed.status_code == 200, completed.text
    assert completed.json()["task"]["status"] == "COMPLETED"
    assert completed.json()["task"]["evidence_pointer"] == f"browser-evidence://{evidence_id}"
    evidence = await ac.get(evidence_path, headers=HEADERS)
    assert evidence.status_code == 200, evidence.text
    assert [row["evidence_id"] for row in evidence.json()] == [evidence_id]
    assert evidence.json()[0]["extraction_digest"] == result["evidence"]["extraction_digest"]


@pytest.mark.asyncio
@pytest.mark.parametrize("token", [RUNTIME, WRONG])
async def test_wrong_internal_scope_is_terminal_even_with_valid_owner_credentials(client, token):
    ac, app = client
    task = await _create_task(ac)
    owner_headers = await _owner_headers(app)
    for path in _read_paths(task):
        response = await ac.get(
            path, headers={**owner_headers, "X-Van-Internal-Token": token}
        )
        assert response.status_code == 403, (path, response.text)
        assert response.json() == {
            "detail": "internal_control_unauthorized", "required_scope": "browser"
        }


@pytest.mark.asyncio
async def test_absent_internal_header_preserves_ingress_and_owner_device_auth(client):
    ac, app = client
    task = await _create_task(ac)
    owner_headers = await _owner_headers(app)
    for path in _read_paths(task):
        anonymous = await ac.get(path)
        assert anonymous.status_code == 401
        assert anonymous.json()["detail"] == "ingress_auth_failed"
        ingress_only = await ac.get(path, headers={"X-Van-Ingress-Token": INGRESS})
        assert ingress_only.status_code == 401
        assert ingress_only.json()["detail"] == "device_access_denied"
        owner = await ac.get(path, headers=owner_headers)
        assert owner.status_code == 200, (path, owner.text)


@pytest.mark.asyncio
async def test_browser_scope_does_not_open_other_browser_get_routes(client):
    ac, _app = client
    for path in (
        "/v1/browser/profiles",
        "/v1/browser/sessions/not-a-session",
        "/v1/browser/tasks/not-a-task/evidence/extra",
    ):
        response = await ac.get(path, headers=HEADERS)
        assert response.status_code == 401, (path, response.text)
        assert response.json()["detail"] == "ingress_auth_failed"
    health = await ac.get("/v1/browser/health", headers=HEADERS)
    assert health.status_code == 403
    assert health.json()["required_scope"] == "runtime"
