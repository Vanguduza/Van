"""Rev 1.3 §§182-189, 219, 379 — the Browser Fabric control surface.

The owner granted the browser worker autonomy *as Hermes's subagent*. These
tests pin the part of that sentence that is easy to lose: there is no route that
starts a worker without an assignment, and every bound in the assignment is
enforced by the runner rather than by the worker being bounded.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tests.conftest_automation import make_store
from van_gateway.browser.api import BrowserApi
from van_gateway.browser.models import (
    BrowserObservation,
    BrowserTaskStatus,
    InjectionAssessment,
)
from van_gateway.browser.subagent import ProposedAction
from van_gateway.config import get_settings
from van_gateway.models import ActionClass

INGRESS = "test-ingress-token-0123456789abcdef"
INTERNAL = "test-internal-token"
HEADERS = {"X-Van-Internal-Token": INTERNAL}
DOMAIN = "portal.example.com"


@pytest.fixture(autouse=True)
def _settings(monkeypatch, tmp_path):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "browser.sqlite3"))
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", INGRESS)
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", INTERNAL)
    monkeypatch.setenv("VAN_BROWSER_ENABLED", "1")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class _ScriptedWorker:
    """Proposes a fixed script. It cannot decide anything; the runner does."""

    def __init__(self, actions: list[ProposedAction]) -> None:
        self.actions = list(actions)
        self.proposed = 0
        self.executed = 0

    async def propose(self, assignment, history):
        self.proposed += 1
        if not self.actions:
            return ProposedAction(kind="done", domain=DOMAIN, done=True)
        return self.actions.pop(0)

    async def execute(self, assignment, action):
        self.executed += 1
        return BrowserObservation(
            task_id=assignment.task_id,
            extraction={"step": self.executed, "seen": action.instruction or action.kind},
            injection_assessment=InjectionAssessment.NONE_DETECTED,
        )


async def _client(tmp_path, worker=None):
    store = await make_store(tmp_path)
    api = BrowserApi(store, get_settings(), worker=worker)
    app = FastAPI()
    app.include_router(api.router)
    ac = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    return ac, api, store


@pytest_asyncio.fixture
async def fabric(tmp_path):
    ac, api, store = await _client(tmp_path)
    async with ac:
        yield ac, api, store


async def _make_task(ac, **overrides) -> dict:
    await ac.post("/v1/browser/profiles", headers=HEADERS, json={"profile_alias": "public_research"})
    body = {
        "profile_alias": "public_research",
        "strategy": "STAGEHAND",
        "autonomy_tier": "L4_STAGEHAND_ACT",
        "action_class": "A2",
        "target_domain": DOMAIN,
        "goal": "find this month's statement and read its total",
        "command_id": "cmd-owner-1",
    }
    body.update(overrides)
    response = await ac.post("/v1/browser/tasks", headers=HEADERS, json=body)
    assert response.status_code == 200, response.text
    return response.json()


# ------------------------------------------------------------- ingress gate


async def test_the_browser_surface_is_internal_control_only():
    from van_gateway.app import create_app

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test",
        headers={"X-Van-Ingress-Token": INGRESS},
    ) as ac:
        async with app.router.lifespan_context(app):
            for path in (
                "/v1/browser/profiles",
                "/v1/browser/tasks",
                "/v1/browser/leases",
                "/v1/browser/assignments",
            ):
                response = await ac.post(path, json={})
                assert response.status_code in (401, 403), (path, response.status_code)


# ------------------------------------------------------- profiles and leases


async def test_a_profile_records_a_reference_never_a_credential(fabric):
    """§407 — a literal cookie is refused rather than stored."""
    ac, _api, _store = fabric
    ok = await ac.post(
        "/v1/browser/profiles",
        headers=HEADERS,
        json={
            "profile_alias": "authenticated_owner",
            "secret_ref": "secretref://browser/google-primary",
        },
    )
    assert ok.status_code == 200
    assert ok.json()["authentication"] == "external_secret_reference"

    refused = await ac.post(
        "/v1/browser/profiles",
        headers=HEADERS,
        json={"profile_alias": "authenticated_owner", "secret_ref": "cookie=abc123"},
    )
    assert refused.status_code == 422
    assert "secret_reference" in refused.json()["detail"]


async def test_a_lease_is_exclusive_while_it_is_live(fabric):
    """§183 — the second holder is refused, not queued behind the first."""
    ac, _api, _store = fabric
    await ac.post("/v1/browser/profiles", headers=HEADERS, json={"profile_alias": "public_research"})
    first = await ac.post(
        "/v1/browser/leases",
        headers=HEADERS,
        json={"profile_alias": "public_research", "task_id": "t1"},
    )
    assert first.status_code == 200

    second = await ac.post(
        "/v1/browser/leases",
        headers=HEADERS,
        json={"profile_alias": "public_research", "task_id": "t2"},
    )
    assert second.status_code == 409

    released = await ac.post(
        "/v1/browser/leases/release",
        headers=HEADERS,
        json={
            "lease_id": first.json()["lease_id"],
            "profile_alias": "public_research",
            "task_id": "t1",
        },
    )
    assert released.status_code == 200
    retry = await ac.post(
        "/v1/browser/leases",
        headers=HEADERS,
        json={"profile_alias": "public_research", "task_id": "t2"},
    )
    assert retry.status_code == 200


# --------------------------------------------------------------------- tasks


async def test_a_task_cannot_be_created_at_a4(fabric):
    """§§108, 391 — the browser is never an A4 execution surface."""
    ac, _api, _store = fabric
    await ac.post("/v1/browser/profiles", headers=HEADERS, json={"profile_alias": "public_research"})
    response = await ac.post(
        "/v1/browser/tasks",
        headers=HEADERS,
        json={
            "profile_alias": "public_research",
            "strategy": "STAGEHAND",
            "autonomy_tier": "L4_STAGEHAND_ACT",
            "action_class": "A4",
            "target_domain": DOMAIN,
            "goal": "confirm the transfer",
        },
    )
    assert response.status_code == 422
    assert "action_class_prohibited" in response.json()["detail"]


async def test_a_mutating_task_needs_an_admitted_domain(fabric):
    """config/browser/domains.yaml: mutate is deny_until_explicitly_admitted."""
    ac, _api, _store = fabric
    await ac.post(
        "/v1/browser/profiles",
        headers=HEADERS,
        json={
            "profile_alias": "authenticated_owner",
            "secret_ref": "secretref://browser/google-primary",
        },
    )
    response = await ac.post(
        "/v1/browser/tasks",
        headers=HEADERS,
        json={
            "profile_alias": "authenticated_owner",
            "strategy": "STAGEHAND",
            "autonomy_tier": "L4_STAGEHAND_ACT",
            "action_class": "A3",
            "target_domain": DOMAIN,
            "goal": "update the delivery address",
            "mutating": True,
        },
    )
    assert response.status_code == 422
    assert "domain_not_admitted" in response.json()["detail"]


async def test_task_inputs_carrying_a_secret_are_refused(fabric):
    """§407 — refuse loudly rather than quietly redacting."""
    ac, _api, _store = fabric
    await ac.post("/v1/browser/profiles", headers=HEADERS, json={"profile_alias": "public_research"})
    response = await ac.post(
        "/v1/browser/tasks",
        headers=HEADERS,
        json={
            "profile_alias": "public_research",
            "strategy": "STAGEHAND",
            "autonomy_tier": "L4_STAGEHAND_ACT",
            "action_class": "A2",
            "target_domain": DOMAIN,
            "goal": "read the statement",
            "inputs": {"password": "hunter2-not-a-reference"},
        },
    )
    assert response.status_code == 422


async def test_evidence_is_digest_only(fabric):
    """§§184-185 — nothing raw is stored, and the page is untrusted by default."""
    ac, _api, _store = fabric
    task = await _make_task(ac)
    response = await ac.post(
        f"/v1/browser/tasks/{task['task_id']}/evidence",
        headers=HEADERS,
        json={
            "kind": "extraction",
            "url": f"https://{DOMAIN}/statements/september",
            "dom": "<html><body>Statement total 1,240.00</body></html>",
            "extraction": {"total": "1240.00"},
        },
    )
    assert response.status_code == 200, response.text
    evidence = response.json()
    assert evidence["url_digest"].startswith("sha256:")
    assert evidence["dom_digest"].startswith("sha256:")
    assert evidence["source_trust"] == "UNTRUSTED_EXTERNAL"
    assert evidence["contains_secrets"] is False
    # The raw page must not be echoed back anywhere in the response.
    assert "Statement total" not in response.text

    fetched = await ac.get(f"/v1/browser/tasks/{task['task_id']}", headers=HEADERS)
    assert fetched.status_code == 200
    assert len(fetched.json()["evidence"]) == 1


async def test_an_unknown_task_is_a_404(fabric):
    ac, _api, _store = fabric
    assert (await ac.get("/v1/browser/tasks/nope", headers=HEADERS)).status_code == 404


# ---------------------------------------------------------------- assignments


async def test_no_worker_means_no_run(fabric):
    """An unconfigured worker is refused, never simulated."""
    ac, _api, _store = fabric
    task = await _make_task(ac)
    response = await ac.post(
        "/v1/browser/assignments",
        headers=HEADERS,
        json={
            "task_id": task["task_id"], "turn_id": "turn-1", "command_id": "cmd-owner-1",
            "goal": "read the statement total", "allowed_domains": [DOMAIN],
        },
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "BROWSER_WORKER_UNCONFIGURED"


async def test_an_assignment_cannot_omit_its_bounds(fabric):
    """§379 — no turn, no goal, no domain scope, no run. There is no 'unbounded'."""
    ac, _api, _store = fabric
    task = await _make_task(ac)
    for missing in ("turn_id", "command_id", "goal", "allowed_domains"):
        body = {
            "task_id": task["task_id"], "turn_id": "turn-1", "command_id": "cmd-owner-1",
            "goal": "read the statement total", "allowed_domains": [DOMAIN],
        }
        body.pop(missing)
        response = await ac.post("/v1/browser/assignments", headers=HEADERS, json=body)
        assert response.status_code == 422, missing

    # An empty domain scope is not a wildcard either.
    empty = await ac.post(
        "/v1/browser/assignments",
        headers=HEADERS,
        json={
            "task_id": task["task_id"], "turn_id": "turn-1", "command_id": "cmd-owner-1",
            "goal": "read the statement total", "allowed_domains": [],
        },
    )
    assert empty.status_code == 422

    # And the step budget has a hard ceiling the caller cannot raise.
    unbounded = await ac.post(
        "/v1/browser/assignments",
        headers=HEADERS,
        json={
            "task_id": task["task_id"], "turn_id": "turn-1", "command_id": "cmd-owner-1",
            "goal": "read the statement total", "allowed_domains": [DOMAIN],
            "max_steps": 5000,
        },
    )
    assert unbounded.status_code == 422


async def test_a_worker_runs_inside_its_assignment_and_the_task_closes(tmp_path):
    """The happy path: the worker selects its own actions, then declares done."""
    worker = _ScriptedWorker(
        [
            ProposedAction(kind="navigate", domain=DOMAIN, url=f"https://{DOMAIN}/statements",
                           instruction="open the statements page"),
            ProposedAction(kind="extract", domain=DOMAIN, instruction="read the total"),
            ProposedAction(kind="done", domain=DOMAIN, done=True),
        ]
    )
    ac, _api, store = await _client(tmp_path, worker=worker)
    async with ac:
        task = await _make_task(ac)
        response = await ac.post(
            "/v1/browser/assignments",
            headers=HEADERS,
            json={
                "task_id": task["task_id"], "turn_id": "turn-7", "command_id": "cmd-owner-1",
                "goal": "read the statement total", "allowed_domains": [DOMAIN],
                "max_steps": 6,
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["stop_reason"] == "GOAL_ACHIEVED"
        assert body["succeeded"] is True
        assert body["step_count"] == 2
        # §379 — every step is attributed to the assigning Hermes turn.
        assert {step["turn_id"] for step in body["steps"]} == {"turn-7"}
        assert body["assigned_by_turn"] == "turn-7"
        assert body["bounds"]["max_steps"] == 6

        fetched = await ac.get(f"/v1/browser/tasks/{task['task_id']}", headers=HEADERS)
        assert fetched.json()["task"]["status"] == BrowserTaskStatus.COMPLETED.value


@pytest.mark.parametrize(
    ("action", "stop_reason"),
    [
        (
            ProposedAction(kind="navigate", domain="somewhere-else.example.net",
                           url="https://somewhere-else.example.net/"),
            "SCOPE_VIOLATION",
        ),
        (
            ProposedAction(kind="submit", domain=DOMAIN, action_class=ActionClass.A3),
            "ACTION_CLASS_VIOLATION",
        ),
        (
            ProposedAction(kind="act", domain=DOMAIN, restated_goal="do something else entirely"),
            "GOAL_DRIFT",
        ),
        (
            ProposedAction(kind="act", domain=DOMAIN,
                           instruction="proceed to checkout and pay the invoice"),
            "PAYMENT_REFUSED",
        ),
    ],
)
async def test_a_worker_that_leaves_its_assignment_is_stopped(tmp_path, action, stop_reason):
    """Every violation ends the task. None of them escalates or asks for more."""
    worker = _ScriptedWorker([action])
    ac, _api, _store = await _client(tmp_path, worker=worker)
    async with ac:
        task = await _make_task(ac)
        body = (
            await ac.post(
                "/v1/browser/assignments",
                headers=HEADERS,
                json={
                    "task_id": task["task_id"], "turn_id": "turn-1",
                    "command_id": "cmd-owner-1", "goal": "read the statement total",
                    "allowed_domains": [DOMAIN],
                },
            )
        ).json()
        assert body["stop_reason"] == stop_reason
        assert body["succeeded"] is False
        # Nothing was executed: the check happens before the action runs.
        assert worker.executed == 0

        fetched = await ac.get(f"/v1/browser/tasks/{task['task_id']}", headers=HEADERS)
        task_row = fetched.json()["task"]
        assert task_row["status"] == BrowserTaskStatus.FAILED.value
        assert task_row["error_code"] == stop_reason


async def test_an_assignment_cannot_carry_an_a4_ceiling(tmp_path):
    """§391 — A4 needs a fresh owner approval, which by definition is not autonomous."""
    worker = _ScriptedWorker([])
    ac, _api, _store = await _client(tmp_path, worker=worker)
    async with ac:
        task = await _make_task(ac)
        body = (
            await ac.post(
                "/v1/browser/assignments",
                headers=HEADERS,
                json={
                    "task_id": task["task_id"], "turn_id": "turn-1",
                    "command_id": "cmd-owner-1", "goal": "read the statement total",
                    "allowed_domains": [DOMAIN], "action_class_ceiling": "A4",
                },
            )
        ).json()
        assert body["stop_reason"] == "ACTION_CLASS_VIOLATION"
        assert worker.proposed == 0


async def test_a_run_cannot_be_started_twice(tmp_path):
    """A completed task is terminal; a second assignment does not resume it."""
    worker = _ScriptedWorker([ProposedAction(kind="done", domain=DOMAIN, done=True)])
    ac, _api, _store = await _client(tmp_path, worker=worker)
    async with ac:
        task = await _make_task(ac)
        body = {
            "task_id": task["task_id"], "turn_id": "turn-1", "command_id": "cmd-owner-1",
            "goal": "read the statement total", "allowed_domains": [DOMAIN],
        }
        first = await ac.post("/v1/browser/assignments", headers=HEADERS, json=body)
        assert first.status_code == 200
        second = await ac.post("/v1/browser/assignments", headers=HEADERS, json=body)
        assert second.status_code == 409
        assert second.json()["detail"] == "BROWSER_TASK_NOT_PENDING"
