"""Review I2 N-3, N-4, N-5, N-11 — task lifecycle authority on the browser surface.

Each test is one of reviewer I2's probes (review-i2/probes/*.py) turned into a regression:

* N-3 ``lifecycle.py`` [A]/[B], ``lifecycle_assign.py`` — ``POST /tasks/{id}/complete`` set any
  status. ``{"status": "RESUME_AUTHORIZED"}`` on a task waiting for the owner self-authorized it
  (``/complete RESUME_AUTHORIZED: 200`` then ``/step ... 200 VERIFIED_SUCCESS executed:
  [('click', '#go')]``), and ``{"status": "PENDING"}`` reopened a task the owner had rejected,
  after which both ``/step`` and ``/assignments`` drove it.
* N-4 ``lifecycle.py`` [C] — ``/step`` on a RESUME_AUTHORIZED task ignored the owner's
  authorization: with an approved ceiling of A1, two A2 steps executed and the authorization
  stayed ACTIVE.
* N-5 ``lease.py`` — ``/step`` ran task2 while task1 held the profile's page lease.
* N-11 ``forge_step.py`` — ``seal_evidence(kind="interaction_router_step")`` was accepted and
  listed by ``RouterStepLedger.steps_for_task`` as a step the router took.
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import test_browser_api as t
import test_browser_interaction_router as tr
from conftest_automation import make_store
from van_gateway.attention.engine import AttentionEngine
from van_gateway.browser.api import BrowserApi
from van_gateway.browser.interaction_router import (
    ROUTER_STEP_EVIDENCE_KIND,
    RouterStepLedger,
    build_interaction_routes,
)
from van_gateway.browser.models import AutonomyTier, BrowserStrategy, BrowserTaskStatus
from van_gateway.browser.policy import BrowserPolicyError
from van_gateway.browser.service import (
    TERMINAL_TASK_STATUSES,
    BrowserTaskService,
    BrowserTaskTransitionRefused,
)
from van_gateway.browser.subagent import ProposedAction
from van_gateway.config import get_settings
from van_gateway.decisions.service import DecisionService
from van_gateway.models import ActionClass

H = t.HEADERS
OUT_OF_SCOPE = [ProposedAction(kind="navigate", domain="outside.example.net", url="https://outside.example.net/")]


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "browser.sqlite3"))
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", t.INGRESS)
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", t.INTERNAL)
    monkeypatch.setenv("VAN_DEVICE_ENROLMENT_TOKEN", t.INTERNAL)
    monkeypatch.setenv("VAN_BROWSER_ENABLED", "1")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _setup(tmp_path, actions=None):
    store = await make_store(tmp_path)
    api = BrowserApi(store, get_settings(), worker=t._ScriptedWorker(list(actions or [])),
                     decisions=DecisionService(store, AttentionEngine(store)), verifier=t._Verdict())
    ex = tr.FakeExecutor()

    async def observe(task):
        return {"url": "https://docs.example.com"}

    # Review I5: the Harness binds "#go" on a page of the task's own domain (its scope).
    resolver = tr.FakeResolver({"#go": tr.bound({"ref": "#go", "role": "button", "label": "Go"},
                                                page_url=f"https://{t.DOMAIN}/statement")})
    router = tr.make_router(executor=ex, observer=observe, semantic_fallback=tr.FakeStagehand(None),
                            target_resolver=resolver)
    app = FastAPI()
    app.include_router(api.router)
    app.include_router(build_interaction_routes(api, router))
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test"), store, ex, api


async def _status(ac, tid):
    return (await ac.get(f"/v1/browser/tasks/{tid}", headers=H)).json()["task"]["status"]


def _step(tid, ceiling="A2", **extra):
    body = {"task_id": tid, "action_class_ceiling": ceiling,
            "deterministic_action": {"operation": "click", "locator": "#go"},
            "postcondition": {"kind": "READ_BACK", "field": "title", "expected": "x"}}
    body.update(extra)
    return body


async def _escalate(ac, store, ceiling="A2"):
    """An assignment that leaves its domain scope -> WAITING_FOR_OWNER with an owner decision."""
    task = await t._make_task(ac, target_domain=t.DOMAIN)
    tid = task["task_id"]
    r = await ac.post("/v1/browser/assignments", headers=H, json={
        "task_id": tid, "turn_id": "t1", "command_id": "cmd-owner-1",
        "goal": "read the statement total", "allowed_domains": [t.DOMAIN], "action_class_ceiling": ceiling})
    assert r.json()["stop_reason"] == "SCOPE_VIOLATION"
    row = await store.fetchone("SELECT decision_id FROM browser_escalations WHERE task_id = ?", (tid,))
    return tid, row["decision_id"]


# ------------------------------------------------------------------------------ N-3


async def test_complete_cannot_self_authorize_a_task_waiting_for_the_owner(tmp_path):
    """Probe lifecycle.py [A]."""
    ac, store, ex, _api = await _setup(tmp_path, OUT_OF_SCOPE)
    async with ac:
        tid, _ = await _escalate(ac, store)
        assert await _status(ac, tid) == "WAITING_FOR_OWNER"
        c = await ac.post(f"/v1/browser/tasks/{tid}/complete", headers=H, json={"status": "RESUME_AUTHORIZED"})
        assert c.status_code == 409
        assert c.json()["detail"].startswith("BROWSER_TASK_TRANSITION_REFUSED:NOT_A_TERMINAL_STATUS")
        assert await _status(ac, tid) == "WAITING_FOR_OWNER"
        r = await ac.post("/v1/browser/interaction/step", headers=H, json=_step(tid))
        assert (r.status_code, r.json()["detail"]) == (409, "BROWSER_TASK_NOT_RUNNABLE:WAITING_FOR_OWNER")
    assert ex.executed == []


async def test_complete_cannot_reopen_a_task_the_owner_rejected(tmp_path):
    """Probes lifecycle.py [B] and lifecycle_assign.py (same root cause: /complete PENDING)."""
    ac, store, ex, api = await _setup(tmp_path, OUT_OF_SCOPE)
    async with ac:
        tid, decision_id = await _escalate(ac, store)
        await store.execute("UPDATE decisions SET status = 'REJECTED' WHERE id = ?", (decision_id,))
        r = await ac.post("/v1/browser/interaction/step", headers=H, json=_step(tid))
        assert r.json()["detail"] == "BROWSER_TASK_NOT_RUNNABLE:CANCELLED"
        c = await ac.post(f"/v1/browser/tasks/{tid}/complete", headers=H, json={"status": "PENDING"})
        assert c.status_code == 409
        assert await _status(ac, tid) == "CANCELLED"
        r = await ac.post("/v1/browser/interaction/step", headers=H, json=_step(tid))
        assert (r.status_code, r.json()["detail"]) == (409, "BROWSER_TASK_NOT_RUNNABLE:CANCELLED")
        a = await ac.post("/v1/browser/assignments", headers=H, json={
            "task_id": tid, "turn_id": "t2", "command_id": "cmd-owner-1",
            "goal": "read the statement total", "allowed_domains": [t.DOMAIN]})
        assert (a.status_code, a.json()["detail"]) == (409, "BROWSER_TASK_NOT_RUNNABLE:CANCELLED")
        # Another end state is not a way back either.
        f = await ac.post(f"/v1/browser/tasks/{tid}/complete", headers=H, json={"status": "FAILED"})
        assert f.status_code == 409 and "TASK_ALREADY_TERMINAL:CANCELLED->FAILED" in f.json()["detail"]
    assert ex.executed == [] and api.worker.executed == 0


async def _service_task(tmp_path):
    store = await make_store(tmp_path)
    service = BrowserTaskService(store)
    await service.broker.register_profile(profile_alias="public_research")
    task = await service.create_task(
        profile_alias="public_research", strategy=BrowserStrategy.HARNESS,
        autonomy_tier=AutonomyTier.L1_HARNESS_DETERMINISTIC, action_class=ActionClass.A1,
        target_domain="research.example.com", goal="read",
    )
    return store, service, task


@pytest.mark.parametrize("status", [s for s in BrowserTaskStatus if s not in TERMINAL_TASK_STATUSES])
async def test_the_service_sets_only_end_states(tmp_path, status):
    """The rule lives in BrowserTaskService.complete — the single choke point."""
    store, service, task = await _service_task(tmp_path)
    with pytest.raises(BrowserTaskTransitionRefused, match="NOT_A_TERMINAL_STATUS"):
        await service.complete(task_id=task.task_id, status=status)
    row = await store.fetchone("SELECT status FROM browser_tasks WHERE task_id = ?", (task.task_id,))
    assert row["status"] == "PENDING"


@pytest.mark.parametrize("first", sorted(TERMINAL_TASK_STATUSES - {BrowserTaskStatus.COMPLETED}, key=lambda s: s.value))
async def test_nothing_leaves_an_end_state(tmp_path, first):
    store, service, task = await _service_task(tmp_path)
    await service.complete(task_id=task.task_id, status=first)
    await service.record_verification(task=task, outcome="VERIFIED", verifier="v")
    for later in (BrowserTaskStatus.COMPLETED, BrowserTaskStatus.FAILED, BrowserTaskStatus.CANCELLED):
        if later is first:
            continue
        with pytest.raises(BrowserTaskTransitionRefused, match="TASK_ALREADY_TERMINAL"):
            await service.complete(task_id=task.task_id, status=later)
    with pytest.raises(BrowserTaskTransitionRefused):
        await service.hold_for_verification(task_id=task.task_id)
    row = await store.fetchone("SELECT status FROM browser_tasks WHERE task_id = ?", (task.task_id,))
    assert row["status"] == first.value


# ------------------------------------------------------------------------------ N-4


async def test_advisory_approval_cannot_resume_step_above_requested_class(tmp_path):
    """Probe lifecycle.py [C]: approved ceiling A1, steps asked for A2."""
    ac, store, ex, _api = await _setup(tmp_path, OUT_OF_SCOPE)
    async with ac:
        tid, decision_id = await _escalate(ac, store, ceiling="A1")
        await store.execute("UPDATE decisions SET status = 'APPROVED' WHERE id = ?", (decision_id,))
        body = {"task_id": tid, "action_class_ceiling": "A2",
                "postcondition": {"kind": "READ_BACK", "field": "title", "expected": "x"}}
        first = await ac.post("/v1/browser/interaction/step", headers=H, json=body)
        second = await ac.post("/v1/browser/interaction/step", headers=H, json=body)
        auth = await store.fetchone(
            "SELECT approved_action_class_ceiling, status FROM browser_scope_authorizations WHERE task_id = ?", (tid,))
    assert first.status_code == second.status_code == 409
    assert first.json()["detail"] == second.json()["detail"] == "BROWSER_TASK_NOT_RUNNABLE:WAITING_FOR_OWNER"
    assert auth is None
    assert ex.executed == []


async def test_advisory_approval_cannot_resume_step_within_requested_class(tmp_path):
    ac, store, ex, _api = await _setup(tmp_path, OUT_OF_SCOPE)
    async with ac:
        tid, decision_id = await _escalate(ac, store, ceiling="A2")
        await store.execute("UPDATE decisions SET status = 'APPROVED' WHERE id = ?", (decision_id,))
        ran = await ac.post("/v1/browser/interaction/step", headers=H, json=_step(tid))
        again = await ac.post("/v1/browser/interaction/step", headers=H, json=_step(tid))
    assert ran.status_code == again.status_code == 409
    assert ran.json()["detail"] == again.json()["detail"] == "BROWSER_TASK_NOT_RUNNABLE:WAITING_FOR_OWNER"
    assert ex.executed == []
    assert await store.fetchall("SELECT * FROM browser_scope_authorizations WHERE task_id=?", (tid,)) == []


# ------------------------------------------------------------------------------ N-5


async def _two_tasks(ac):
    one = (await t._make_task(ac))["task_id"]
    two = (await t._make_task(ac))["task_id"]
    return one, two


async def test_step_refuses_while_another_task_holds_the_profile_lease(tmp_path):
    """Probe lease.py."""
    ac, _store, ex, _api = await _setup(tmp_path)
    async with ac:
        one, two = await _two_tasks(ac)
        held = await ac.post("/v1/browser/leases", headers=H, json={"profile_alias": "public_research", "task_id": one})
        assert held.status_code == 200
        r = await ac.post("/v1/browser/interaction/step", headers=H, json=_step(two))
    assert (r.status_code, r.json()["detail"]) == (409, "browser_profile_leased:public_research")
    assert ex.executed == []


async def test_step_runs_under_its_own_lease_and_takes_and_returns_a_free_one(tmp_path):
    ac, store, ex, _api = await _setup(tmp_path)
    async with ac:
        one, two = await _two_tasks(ac)
        # Free profile: the step takes the lease for itself and gives it back.
        free = await ac.post("/v1/browser/interaction/step", headers=H, json=_step(two))
        row = await store.fetchone("SELECT lease_holder FROM browser_profiles WHERE profile_alias = 'public_research'")
        assert free.status_code == 200, free.text
        assert row["lease_holder"] is None
        # The task's own live lease: used, and still held by it afterwards.
        held = await ac.post("/v1/browser/leases", headers=H, json={"profile_alias": "public_research", "task_id": one})
        own = await ac.post("/v1/browser/interaction/step", headers=H, json=_step(one))
        row = await store.fetchone("SELECT lease_holder FROM browser_profiles WHERE profile_alias = 'public_research'")
    assert own.status_code == 200, own.text
    assert row["lease_holder"] == held.json()["lease_id"]
    assert len(ex.executed) == 2


# ------------------------------------------------------------------------------ N-11


@pytest.mark.parametrize("kind", [
    ROUTER_STEP_EVIDENCE_KIND, "Interaction_Router_Step", " INTERACTION_ROUTER_STEP ",
    "POSTCONDITION_VERIFICATION", "Postcondition_Verification",
])
async def test_router_step_and_verdict_kinds_cannot_be_sealed_by_a_caller(tmp_path, kind):
    """Probe forge_step.py."""
    store, service, task = await _service_task(tmp_path)
    with pytest.raises(BrowserPolicyError, match="reserved"):
        await service.seal_evidence(task=task, kind=kind, url="https://docs.example.com",
                                    extraction={"state": "VERIFIED_SUCCESS"})
    assert await RouterStepLedger(store).steps_for_task(task.task_id) == []


async def test_router_step_kind_is_refused_over_http(tmp_path):
    ac, _store, _ex, _api = await _setup(tmp_path)
    async with ac:
        tid = (await t._make_task(ac))["task_id"]
        r = await ac.post(f"/v1/browser/tasks/{tid}/evidence", headers=H,
                          json={"kind": ROUTER_STEP_EVIDENCE_KIND, "url": "https://docs.example.com/",
                                "extraction": {"state": "VERIFIED_SUCCESS"}})
    assert r.status_code == 422
