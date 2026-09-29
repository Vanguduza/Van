"""Review I3 MAJOR-3, MINOR-1..MINOR-4 — each test is one of reviewer I3's probes
(review-i3/probes/*.py) turned into a regression.

* MAJOR-3 ``lease_race.py`` — two concurrent ``/step`` calls on the same task: step B saw
  "held by this task", took no lease, and kept actuating after step A's ``finally`` released
  the lease; task2 was then GRANTED the profile mid-actuation.
* MINOR-1 ``complete_inflight.py`` — ``/complete COMPLETED`` landed while a step was actuating
  (latest verdict VERIFIED from the previous step); the step then recorded FAILED under a
  sticky COMPLETED.
* MINOR-2 ``terminal_resurrect.py`` — a task CANCELLED mid-run was moved to WAITING_FOR_OWNER by
  the post-run bookkeeping (raw UPDATEs outside ``complete()``), then to COMPLETED.
* MINOR-3 ``watch_terminal.py`` — the watch runner's except-branch ``complete(FAILED)`` on an
  already-terminal task raised and aborted the whole job.
* MINOR-4 ``jev_gate.py`` — a one-line ``status: OWNER_APPROVED_EFFECT`` edit turned the Jev
  browser-effect capability GREEN with no owner signature and a null decision reference.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import re
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import test_browser_api as t
import test_browser_interaction_router as tr
from conftest_automation import make_store
from van_gateway.action.models import VerifierType
from van_gateway.attention.engine import AttentionEngine
from van_gateway.automation import production_gates
from van_gateway.automation.verifier import VerificationOutcome, VerificationResult
from van_gateway.browser.adapters import (
    BrowserAdapterError,
    HarnessLeaseFence,
    HttpBrowserHarnessAdapter,
    current_harness_lease_fence,
    harness_lease_fence,
)
from van_gateway.browser.api import BrowserApi
from van_gateway.browser.interaction_router import RouterStepLedger, build_interaction_routes
from van_gateway.browser.models import AutonomyTier, BrowserStrategy, BrowserTaskStatus
from van_gateway.browser.service import (
    BrowserSessionBroker,
    BrowserTaskNotVerified,
    BrowserTaskService,
    BrowserTaskTransitionRefused,
)
from van_gateway.browser.subagent import OwnerTakeoverRequired, ProposedAction
from van_gateway.config import get_settings
from van_gateway.decisions.service import DecisionService
from van_gateway.goals.models import WatchCreate, WatchSourceKind
from van_gateway.goals.service import GoalService
from van_gateway.goals.watch_runner import WatchRunner
from van_gateway.models import ActionClass

H = t.HEADERS
ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend" / "van_gateway"
HARNESS_SERVICE = ROOT / "deploy" / "van-browser-core" / "browser" / "harness_service.py"


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


class GatedExecutor:
    """Blocks inside ``execute`` until the test opens the gate, recording the lease fence."""

    def __init__(self) -> None:
        self.executed: list[tuple[str, str]] = []
        self.fences: list[HarnessLeaseFence | None] = []
        self.entered: asyncio.Queue[int] = asyncio.Queue()
        self.gates: list[asyncio.Event] = []

    async def execute(self, task, action):
        gate = asyncio.Event()
        self.gates.append(gate)
        self.fences.append(current_harness_lease_fence())
        await self.entered.put(len(self.gates))
        await gate.wait()
        self.executed.append((task.task_id, action.locator))
        return {}


class SeqVerifier:
    def __init__(self, seq) -> None:
        self.seq = list(seq)

    async def verify(self, task, action, postcondition, *, claimed_done):
        return VerificationResult(outcome=self.seq.pop(0), verifier_type=VerifierType.READ_BACK)


class GatedWorker(t._ScriptedWorker):
    """An /assignments worker that parks in ``propose`` until released."""

    def __init__(self) -> None:
        super().__init__([])
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def propose(self, assignment, history):
        self.entered.set()
        await self.release.wait()
        return await super().propose(assignment, history)


async def _app(tmp_path, *, executor=None, worker=None, **router_kw):
    store = await make_store(tmp_path)
    api = BrowserApi(store, get_settings(), worker=worker or t._ScriptedWorker([]),
                     decisions=DecisionService(store, AttentionEngine(store)), verifier=t._Verdict())
    executor = executor or GatedExecutor()

    async def observe(task):
        return {"url": "https://docs.example.com"}

    router_kw.setdefault("observer", observe)
    router_kw.setdefault("semantic_fallback", tr.FakeStagehand(None))
    router = tr.make_router(executor=executor, **router_kw)
    app = FastAPI()
    app.include_router(api.router)
    app.include_router(build_interaction_routes(api, router))
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test"), store, api, executor


async def _bounded(awaitable, seconds: float = 5):
    """A broken fence must fail these tests, not hang them: every await that a regression
    could leave blocked on the gated executor is bounded."""
    return await asyncio.wait_for(awaitable, seconds)


def _step(tid):
    return {"task_id": tid, "action_class_ceiling": "A2",
            "deterministic_action": {"operation": "click", "locator": "#go"},
            "postcondition": {"kind": "READ_BACK", "field": "title", "expected": "x"}}


async def _lease_row(store):
    return await store.fetchone(
        "SELECT lease_holder, lease_holder_id, lease_generation FROM browser_profiles "
        "WHERE profile_alias = 'public_research'"
    )


async def _status(ac, tid):
    return (await ac.get(f"/v1/browser/tasks/{tid}", headers=H)).json()["task"]["status"]


# ----------------------------------------------------------------------------- MAJOR-3


async def test_a_second_step_on_a_task_with_a_step_in_flight_is_refused(tmp_path):
    """Probe lease_race.py: step B is 409, never actuates, and the lease is not dropped under it."""
    ac, store, _api, ex = await _app(tmp_path)
    async with ac:
        one = (await t._make_task(ac))["task_id"]
        two = (await t._make_task(ac))["task_id"]
        a = asyncio.create_task(ac.post("/v1/browser/interaction/step", headers=H, json=_step(one)))
        await asyncio.wait_for(ex.entered.get(), 5)
        b = await _bounded(ac.post("/v1/browser/interaction/step", headers=H, json=_step(one)))
        assert (b.status_code, b.json()["detail"]) == (409, "BROWSER_TASK_RUN_IN_FLIGHT:STEP")
        # Still step A's lease; another task cannot take the profile while A actuates.
        assert (await _lease_row(store))["lease_holder_id"] == one
        denied = await ac.post("/v1/browser/leases", headers=H, json={"profile_alias": "public_research", "task_id": two})
        assert denied.status_code == 409
        ex.gates[0].set()
        ra = await _bounded(a)
        assert ra.status_code == 200, ra.text
        assert (await _lease_row(store))["lease_holder"] is None
        # The marker is released with the step: the next step on the task runs.
        c = asyncio.create_task(ac.post("/v1/browser/interaction/step", headers=H, json=_step(one)))
        await asyncio.wait_for(ex.entered.get(), 5)
        ex.gates[1].set()
        assert (await _bounded(c)).status_code == 200
    assert ex.executed == [(one, "#go"), (one, "#go")]


async def test_step_and_assignment_on_the_same_task_do_not_overlap(tmp_path):
    worker = GatedWorker()
    ac, _store, _api, ex = await _app(tmp_path, worker=worker)
    async with ac:
        tid = (await t._make_task(ac))["task_id"]
        run = asyncio.create_task(ac.post("/v1/browser/assignments", headers=H, json={
            "task_id": tid, "turn_id": "t1", "command_id": "cmd-owner-1",
            "goal": "read the statement total", "allowed_domains": [t.DOMAIN]}))
        await asyncio.wait_for(worker.entered.wait(), 5)
        s = await _bounded(ac.post("/v1/browser/interaction/step", headers=H, json=_step(tid)))
        assert (s.status_code, s.json()["detail"]) == (409, "BROWSER_TASK_RUN_IN_FLIGHT:ASSIGNMENT")
        worker.release.set()
        assert (await _bounded(run)).status_code == 200
        # And the other way round.
        tid2 = (await t._make_task(ac))["task_id"]
        st = asyncio.create_task(ac.post("/v1/browser/interaction/step", headers=H, json=_step(tid2)))
        await asyncio.wait_for(ex.entered.get(), 5)
        r = await _bounded(ac.post("/v1/browser/assignments", headers=H, json={
            "task_id": tid2, "turn_id": "t2", "command_id": "cmd-owner-1",
            "goal": "read the statement total", "allowed_domains": [t.DOMAIN]}))
        assert (r.status_code, r.json()["detail"]) == (409, "BROWSER_TASK_RUN_IN_FLIGHT:STEP")
        ex.gates[0].set()
        assert (await _bounded(st)).status_code == 200
    assert ex.executed == [(tid2, "#go")]


async def test_step_actions_carry_the_lease_generation_they_run_under(tmp_path):
    ac, store, _api, ex = await _app(tmp_path)
    async with ac:
        tid = (await t._make_task(ac))["task_id"]
        a = asyncio.create_task(ac.post("/v1/browser/interaction/step", headers=H, json=_step(tid)))
        await asyncio.wait_for(ex.entered.get(), 5)
        row = await _lease_row(store)
        ex.gates[0].set()
        await _bounded(a)
    assert ex.fences == [HarnessLeaseFence("public_research", tid, int(row["lease_generation"]))]
    assert current_harness_lease_fence() is None


async def test_release_if_held_never_drops_another_holders_lease(tmp_path):
    store = await make_store(tmp_path)
    broker = BrowserSessionBroker(store)
    await broker.register_profile(profile_alias="public_research", now_ms=1)
    mine = await broker.acquire_lease(profile_alias="public_research", task_id="task-a", now_ms=1_000)
    # Lapsed, and the profile was leased again to someone else.
    theirs = await broker.acquire_lease(profile_alias="public_research", task_id="task-b", now_ms=10_000_000)
    assert await broker.release_lease_if_held(mine) is False
    row = await _lease_row(store)
    assert (row["lease_holder"], row["lease_holder_id"]) == (theirs.lease_id, "task-b")
    assert await broker.release_lease_if_held(theirs) is True
    assert (await _lease_row(store))["lease_holder"] is None


def _load_harness_service():
    spec = importlib.util.spec_from_file_location("van_harness_service_under_test", HARNESS_SERVICE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def harness_worker(monkeypatch, tmp_path):
    """The real Harness worker HTTP handler on an ephemeral loopback port, with the browser
    operation stubbed (no Chromium) so the fence is what is under test. The fence persists
    its state under a per-test directory (review I4 MINOR-A)."""
    monkeypatch.setenv("VAN_HARNESS_STATE_ROOT", str(tmp_path / "harness-state"))
    module = _load_harness_service()
    clicks: list[str] = []

    def click(body, alias, domain):
        clicks.append(str(body.get("locator")))
        return {"ok": True}

    monkeypatch.setitem(module.OPERATIONS, "/click", click)
    server = ThreadingHTTPServer(("127.0.0.1", 0), module.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", clicks
    finally:
        server.shutdown()
        server.server_close()


def _task(profile="public_research"):
    return tr._task().model_copy(update={"profile_alias": profile, "target_domain": "docs.example.com"})


async def test_the_harness_worker_refuses_a_stale_lease_generation(harness_worker):
    base_url, clicks = harness_worker
    harness = HttpBrowserHarnessAdapter(None, base_url=base_url, enabled=True)
    task = _task()
    with harness_lease_fence(HarnessLeaseFence("public_research", "task-a", 4)):
        await harness.click(task, "#one")
    with harness_lease_fence(HarnessLeaseFence("public_research", "task-b", 5)):
        await harness.click(task, "#two")
    # task-a still believes it holds generation 4: refused, not applied to task-b's page.
    with harness_lease_fence(HarnessLeaseFence("public_research", "task-a", 4)):
        with pytest.raises(BrowserAdapterError) as stale:
            await harness.click(task, "#three")
    # One generation, one holder.
    with harness_lease_fence(HarnessLeaseFence("public_research", "task-a", 5)):
        with pytest.raises(BrowserAdapterError) as other:
            await harness.click(task, "#four")
    assert stale.value.code == other.value.code == "BROWSER_HARNESS_LEASE_GENERATION_STALE"
    assert clicks == ["#one", "#two"]
    # The fence is per profile.
    with harness_lease_fence(HarnessLeaseFence("owner_research", "task-c", 1)):
        await harness.click(_task("owner_research"), "#five")
    assert clicks == ["#one", "#two", "#five"]


def test_the_harness_worker_rejects_a_malformed_generation(harness_worker):
    base_url, clicks = harness_worker
    envelope = {"mode": "PRODUCTION_ACTUATOR", "allow_helper_authoring": False,
                "profile_alias": "public_research", "target_domain": "docs.example.com", "locator": "#x"}
    for extra in ({"lease_generation": 0, "lease_holder_id": "a"}, {"lease_generation": "7", "lease_holder_id": "a"},
                  {"lease_generation": True, "lease_holder_id": "a"}, {"lease_generation": 3}):
        r = httpx.post(f"{base_url}/click", json={**envelope, **extra})
        assert r.status_code == 422, (extra, r.text)
    assert clicks == []


# ----------------------------------------------------------------------------- MINOR-1


async def test_complete_is_refused_while_a_step_is_in_flight(tmp_path):
    """Probe complete_inflight.py: step 1 VERIFIED, /complete COMPLETED during step 2."""
    store = await make_store(tmp_path)
    api = BrowserApi(store, get_settings(), worker=t._ScriptedWorker([]),
                     decisions=DecisionService(store, AttentionEngine(store)), verifier=t._Verdict())
    ex = GatedExecutor()
    router = tr.make_router(
        executor=ex, eligibility_classifier=None, semantic_fallback=tr.FakeStagehand(None),
        verifier=SeqVerifier([VerificationOutcome.VERIFIED, VerificationOutcome.FAILED]),
        ledger=RouterStepLedger(store),
    )
    app = FastAPI()
    app.include_router(api.router)
    app.include_router(build_interaction_routes(api, router))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        tid = (await t._make_task(ac))["task_id"]
        first = asyncio.create_task(ac.post("/v1/browser/interaction/step", headers=H, json=_step(tid)))
        await asyncio.wait_for(ex.entered.get(), 5)
        ex.gates[0].set()
        assert (await _bounded(first)).json()["state"] == "VERIFIED_SUCCESS"
        second = asyncio.create_task(ac.post("/v1/browser/interaction/step", headers=H, json=_step(tid)))
        await asyncio.wait_for(ex.entered.get(), 5)
        c = await _bounded(ac.post(f"/v1/browser/tasks/{tid}/complete", headers=H, json={"status": "COMPLETED"}))
        assert (c.status_code, c.json()["detail"]) == (
            409, "BROWSER_TASK_TRANSITION_REFUSED:RUN_IN_FLIGHT_STEP:UNKNOWN->COMPLETED")
        ex.gates[1].set()
        await _bounded(second)
        assert await _status(ac, tid) != "COMPLETED"
        assert await BrowserTaskService(store).latest_verification(tid) == "FAILED"
        # Nothing in flight now, and the latest verdict is FAILED: still refused.
        again = await ac.post(f"/v1/browser/tasks/{tid}/complete", headers=H, json={"status": "COMPLETED"})
        assert (again.status_code, again.json()["detail"]) == (409, "BROWSER_TASK_NOT_VERIFIED:FAILED")


async def _plain_task(tasks: BrowserTaskService):
    await tasks.broker.register_profile(profile_alias="public_research")
    return await tasks.create_task(
        profile_alias="public_research", strategy=BrowserStrategy.HARNESS,
        autonomy_tier=AutonomyTier.L1_HARNESS_DETERMINISTIC, action_class=ActionClass.A1,
        target_domain="docs.example.com", goal="read one page",
    )


async def test_completion_is_conditional_on_the_verdict_it_read(tmp_path, monkeypatch):
    """A verdict appended between complete()'s check and its write refuses the completion."""
    store = await make_store(tmp_path)
    tasks = BrowserTaskService(store)
    task = await _plain_task(tasks)
    await tasks.record_verification(task=task, outcome="VERIFIED", verifier="test")
    real = tasks._latest_verdict

    async def checked_then_overtaken(task_id):
        seen = await real(task_id)
        await tasks.record_verification(task=task, outcome="FAILED", verifier="test")
        return seen

    monkeypatch.setattr(tasks, "_latest_verdict", checked_then_overtaken)
    with pytest.raises(BrowserTaskNotVerified) as refused:
        await tasks.complete(task_id=task.task_id, status=BrowserTaskStatus.COMPLETED)
    assert refused.value.latest == "FAILED"
    row = await store.fetchone("SELECT status FROM browser_tasks WHERE task_id = ?", (task.task_id,))
    assert row["status"] == "PENDING"


# ----------------------------------------------------------------------------- MINOR-2


class CancelMidRun(t._ScriptedWorker):
    """The task is ended elsewhere (``/complete CANCELLED``) while the run is in flight."""

    def __init__(self, api, then: str) -> None:
        super().__init__([])
        self.api = api
        self.then = then

    async def propose(self, assignment, history):
        await self.api.tasks.complete(task_id=assignment.task_id, status=BrowserTaskStatus.CANCELLED)
        if self.then == "scope":
            return ProposedAction(kind="navigate", domain="outside.example.net", url="https://outside.example.net/")
        raise OwnerTakeoverRequired("STAGEHAND_ACTION_UNCLASSIFIABLE:x")


@pytest.mark.parametrize("then", ["scope", "takeover"])
async def test_a_task_cancelled_mid_run_stays_cancelled(tmp_path, then):
    """Probe terminal_resurrect.py: no WAITING_FOR_OWNER, no owner question, no COMPLETED."""
    ac, api, store = await t._client(tmp_path, verifier=t._Verdict())
    api.worker = CancelMidRun(api, then)
    async with ac:
        tid = (await t._make_task(ac))["task_id"]
        r = await ac.post("/v1/browser/assignments", headers=H, json={
            "task_id": tid, "turn_id": "t1", "command_id": "cmd-owner-1",
            "goal": "read the statement total", "allowed_domains": [t.DOMAIN]})
        assert (r.status_code, r.json()["detail"]) == (409, "BROWSER_TASK_ENDED_DURING_RUN:CANCELLED")
        assert await _status(ac, tid) == "CANCELLED"
        escalations = await store.fetchone("SELECT COUNT(*) AS n FROM browser_escalations WHERE task_id = ?", (tid,))
        assert escalations["n"] == 0
        api.worker = t._ScriptedWorker([])
        again = await ac.post("/v1/browser/assignments", headers=H, json={
            "task_id": tid, "turn_id": "t2", "command_id": "cmd-owner-1",
            "goal": "read the statement total", "allowed_domains": [t.DOMAIN],
            "postcondition": {"kind": "READ_BACK", "field": "title", "expected": "x"}})
        assert (again.status_code, again.json()["detail"]) == (409, "BROWSER_TASK_NOT_RUNNABLE:CANCELLED")
        assert await _status(ac, tid) == "CANCELLED"


@pytest.mark.parametrize("decision", ["APPROVED", "REJECTED"])
async def test_the_owner_decision_sync_never_moves_a_task_out_of_an_end_state(tmp_path, decision):
    """An escalation answered after the task ended elsewhere: the sync writes nothing."""
    out = [ProposedAction(kind="navigate", domain="outside.example.net", url="https://outside.example.net/")]
    ac, api, store = await t._client(tmp_path, worker=t._ScriptedWorker(out), verifier=t._Verdict())
    async with ac:
        tid = (await t._make_task(ac))["task_id"]
        r = await ac.post("/v1/browser/assignments", headers=H, json={
            "task_id": tid, "turn_id": "t1", "command_id": "cmd-owner-1",
            "goal": "read the statement total", "allowed_domains": [t.DOMAIN]})
        assert r.json()["stop_reason"] == "SCOPE_VIOLATION"
        dec = await store.fetchone("SELECT decision_id FROM browser_escalations WHERE task_id = ?", (tid,))
        assert (await ac.post(f"/v1/browser/tasks/{tid}/complete", headers=H, json={"status": "FAILED"})).status_code == 200
        await store.execute("UPDATE decisions SET status = ? WHERE id = ?", (decision, dec["decision_id"]))
        task = await api._load_task(tid)
        # The sync is only reached from WAITING_FOR_OWNER; call it as a racing reader would.
        stale = task.model_copy(update={"status": BrowserTaskStatus.WAITING_FOR_OWNER})
        assert await api._sync_waiting_owner_decision(stale) is BrowserTaskStatus.FAILED
        assert await _status(ac, tid) == "FAILED"


async def test_set_working_status_refuses_end_states_and_out_of_order_resume(tmp_path):
    store = await make_store(tmp_path)
    tasks = BrowserTaskService(store)
    task = await _plain_task(tasks)
    with pytest.raises(BrowserTaskTransitionRefused) as not_working:
        await tasks.set_working_status(task_id=task.task_id, status=BrowserTaskStatus.COMPLETED)
    assert not_working.value.why == "NOT_A_WORKING_STATUS"
    with pytest.raises(BrowserTaskTransitionRefused) as resume:
        await tasks.set_working_status(task_id=task.task_id, status=BrowserTaskStatus.RESUME_AUTHORIZED)
    assert resume.value.why == "REQUIRES_WAITING_FOR_OWNER"
    await tasks.complete(task_id=task.task_id, status=BrowserTaskStatus.CANCELLED)
    for status in (BrowserTaskStatus.WAITING_FOR_OWNER, BrowserTaskStatus.VERIFYING):
        with pytest.raises(BrowserTaskTransitionRefused) as ended:
            await tasks.set_working_status(task_id=task.task_id, status=status)
        assert ended.value.why == "TASK_ALREADY_TERMINAL"
    row = await store.fetchone("SELECT status FROM browser_tasks WHERE task_id = ?", (task.task_id,))
    assert row["status"] == "CANCELLED"


def test_no_status_write_bypasses_the_guarded_writer():
    """Every ``UPDATE browser_tasks ... status`` in VAN is BrowserTaskService._write_status."""
    # Whole-file, so SQL split over lines is caught too; ``UPDATE ...`` in backticks is prose.
    pattern = re.compile(r"(?<!`)\bUPDATE\s+browser_tasks\s+SET\b", re.IGNORECASE)
    hits = []
    for path in BACKEND.rglob("*.py"):
        for match in pattern.finditer(path.read_text(encoding="utf-8")):
            hits.append(f"{path.relative_to(BACKEND).as_posix()}:{match.start()}")
    assert len(hits) == 1 and hits[0].startswith("browser/service.py:"), hits


# ----------------------------------------------------------------------------- MINOR-3


class _Ready:
    ready = True


class _CancellingHarness:
    def __init__(self, tasks: BrowserTaskService) -> None:
        self.tasks = tasks
        self.calls: list[str] = []

    async def status(self):
        return _Ready()

    async def navigate(self, task, url):
        self.calls.append(url)
        if len(self.calls) == 1:
            await self.tasks.complete(task_id=task.task_id, status=BrowserTaskStatus.CANCELLED)
        return {"url": url, "title": "t", "extraction": {"visible_text": "available"}}


async def test_a_watch_task_ended_mid_run_does_not_abort_the_other_watches(tmp_path):
    """Probe watch_terminal.py."""
    store = await make_store(tmp_path)
    goals = GoalService(store, AttentionEngine(store))
    for i in range(2):
        await goals.create_watch(WatchCreate(
            title=f"w{i}", source_kind=WatchSourceKind.BROWSER, target=f"https://example.com/{i}",
            condition={"kind": "TEXT_CONTAINS", "text": "available"}, interval_seconds=60), now_ms=1000)
    broker = BrowserSessionBroker(store)
    tasks = BrowserTaskService(store, broker)
    harness = _CancellingHarness(tasks)
    result = await WatchRunner(goals, tasks=tasks, broker=broker, harness=harness).run(now_ms=1000)
    assert result == {"due": 2, "checked": 1, "triggered": 1, "failed": 1}
    assert harness.calls == ["https://example.com/0", "https://example.com/1"]
    statuses = [r["status"] for r in await store.fetchall(
        "SELECT status FROM browser_tasks ORDER BY started_at_ms, rowid")]
    assert sorted(statuses) == ["CANCELLED", "COMPLETED"]


# ----------------------------------------------------------------------------- MINOR-4


def _jev_capability(tmp_path: Path, record: str) -> dict:
    """The real gate model's Jev capability decision over a Jev record, the rest GREEN."""
    decisions = tmp_path / "docs" / "decisions"
    decisions.mkdir(parents=True)
    simple = {"id": "owner_decision", "kind": "owner_decision", "path": "owner_signature_status",
              "green": ["SIGNED"], "pending": ["PENDING"]}
    for name in ("VAN-ADOPT-N8N-001.yaml", "VAN-ADOPT-BROWSER-HARNESS-001.yaml", "VAN-ADOPT-STAGEHAND-001.yaml"):
        (decisions / name).write_text("owner_signature_status: SIGNED\n", encoding="utf-8")
    (decisions / "VAN-AMEND-SECURITY-POLICY-001.md").write_text("**Status:** `OWNER_APPROVED`\n", encoding="utf-8")
    (decisions / "VAN-JEV-BROWSER-EFFECT-001.yaml").write_text(record, encoding="utf-8")
    required = [{"decision": n, "format": "yaml", "gates": [simple]} for n in (
        "VAN-ADOPT-N8N-001.yaml", "VAN-ADOPT-BROWSER-HARNESS-001.yaml", "VAN-ADOPT-STAGEHAND-001.yaml")]
    required.append({"decision": "VAN-AMEND-SECURITY-POLICY-001.md", "format": "markdown",
                     "gates": [{"id": "owner_decision", "kind": "owner_decision", "path": "Status",
                                "green": ["OWNER_APPROVED"]}]})
    model = json.loads(production_gates.GATE_MODEL.read_text(encoding="utf-8"))
    path = tmp_path / "gates.json"
    path.write_text(json.dumps({"decisions_dir": "docs/decisions", "required_decisions": required,
                                "capability_decisions": model["capability_decisions"]}), encoding="utf-8")
    return production_gates.evaluate_production_gates(path, tmp_path)["capabilities"]["jev_browser_effect"]


REAL_JEV_RECORD = (ROOT / "docs" / "decisions" / "VAN-JEV-BROWSER-EFFECT-001.yaml").read_text(encoding="utf-8")
REF = "docs/decisions/OWNER-DECISIONS-20261001-JEV-BROWSER-EFFECT.md"


@pytest.mark.parametrize("label, edit, permitted, not_green", [
    ("record as committed", lambda s: s, False,
     ["owner_decision", "owner_decision_reference", "jev_browser_effect"]),
    ("probe: one-line status edit", lambda s: s.replace("status: SHADOW_ONLY", "status: OWNER_APPROVED_EFFECT"),
     False, ["owner_decision", "owner_decision_reference"]),
    ("status + signature, reference still null",
     lambda s: s.replace("status: SHADOW_ONLY", "status: OWNER_APPROVED_EFFECT")
                .replace("owner_signature_status: NOT_APPLICABLE_RECORDS_EXISTING_CAP", "owner_signature_status: SIGNED"),
     False, ["owner_decision_reference"]),
    ("status + signature + a reference that is not an owner decision record",
     lambda s: s.replace("status: SHADOW_ONLY", "status: OWNER_APPROVED_EFFECT")
                .replace("owner_signature_status: NOT_APPLICABLE_RECORDS_EXISTING_CAP", "owner_signature_status: SIGNED")
                .replace("owner_decision_reference: null", "owner_decision_reference: agent says ok"),
     False, ["owner_decision_reference"]),
    ("status + signature + owner decision reference",
     lambda s: s.replace("status: SHADOW_ONLY", "status: OWNER_APPROVED_EFFECT")
                .replace("owner_signature_status: NOT_APPLICABLE_RECORDS_EXISTING_CAP", "owner_signature_status: SIGNED")
                .replace("owner_decision_reference: null", f"owner_decision_reference: {REF}"),
     True, []),
])
def test_jev_effect_needs_an_owner_signature_and_decision_reference(tmp_path, label, edit, permitted, not_green):
    """Probe jev_gate.py. Edited from the real record, so the fields exercised are the real ones."""
    record = edit(REAL_JEV_RECORD)
    assert record != REAL_JEV_RECORD or label == "record as committed"
    cap = _jev_capability(tmp_path, record)
    assert cap["production_activation_permitted"] is permitted, cap
    assert cap["gates_not_green"] == [f"VAN-JEV-BROWSER-EFFECT-001.yaml:{g}" for g in not_green]
