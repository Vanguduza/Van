"""Review I4 MINOR-A — the lease fence works both ways.

Before: only ``/interaction/step`` sent a lease generation; ``/assignments``, the watch
runner and the notebook consumer sent none; the Harness accepted unfenced envelopes and kept
its fence in memory; ``/step`` never re-checked its lease with the broker. So a stale step
kept clicking on the next holder's page, and a stale generation was re-admitted after an
unfenced new holder or a Harness restart (probe review-i4/probes/test_i4_fence.py).
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest

import test_browser_api as t
from test_browser_review_i3 import _app, _bounded, _env, _lease_row, _step, GatedExecutor  # noqa: F401
from van_gateway.attention.engine import AttentionEngine
from van_gateway.browser.adapters import (
    BrowserAdapterError,
    HarnessLeaseFence,
    HttpBrowserHarnessAdapter,
    current_harness_lease_fence,
    harness_lease_fence,
)
from van_gateway.browser import interaction_router as ir
from van_gateway.browser.interaction_router import HarnessActionExecutor
from van_gateway.browser.service import BrowserSessionBroker, BrowserTaskService
from van_gateway.browser.worker import HybridBrowserWorker
from van_gateway.goals.models import WatchCreate, WatchSourceKind
from van_gateway.goals.service import GoalService
from van_gateway.goals.watch_runner import WatchRunner
from conftest_automation import make_store

H = t.HEADERS
ROOT = Path(__file__).resolve().parents[2]
HARNESS_SERVICE = ROOT / "deploy" / "van-browser-core" / "browser" / "harness_service.py"


class RecordingTransport(httpx.AsyncBaseTransport):
    """The Harness HTTP endpoint as the adapter sees it: records what reached it."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, int | None]] = []

    async def handle_async_request(self, request):
        body = json.loads(request.content or b"{}")
        self.requests.append((request.url.path, body.get("lease_generation")))
        return httpx.Response(200, json={"url": "https://docs.example.com/", "title": "x", "elements": []})


class GateThenHarness:
    """Parks like GatedExecutor, then executes through the real Harness executor + adapter."""

    def __init__(self, adapter) -> None:
        self.inner = HarnessActionExecutor(adapter)
        self.entered: asyncio.Queue[int] = asyncio.Queue()
        self.gates: list[asyncio.Event] = []

    async def execute(self, task, action):
        gate = asyncio.Event()
        self.gates.append(gate)
        await self.entered.put(len(self.gates))
        await gate.wait()
        return await self.inner.execute(task, action)


def _adapter(transport):
    return HttpBrowserHarnessAdapter(None, base_url="http://harness.test", enabled=True, transport=transport)


# --------------------------------------------------------------------------- /step


async def test_a_step_whose_lease_was_retaken_never_reaches_the_harness(tmp_path):
    """Probe test_i4_fence.py #1 through the real executor and adapter."""
    transport = RecordingTransport()
    ex = GateThenHarness(_adapter(transport))
    ac, store, _api, _ = await _app(tmp_path, executor=ex)
    async with ac:
        t1 = (await t._make_task(ac))["task_id"]
        t2 = (await t._make_task(ac))["task_id"]
        a = asyncio.create_task(ac.post("/v1/browser/interaction/step", headers=H, json=_step(t1)))
        await _bounded(ex.entered.get())
        await store.execute("UPDATE browser_profiles SET lease_expires_at_ms = 1 WHERE profile_alias = 'public_research'")
        l2 = await ac.post("/v1/browser/leases", headers=H, json={"profile_alias": "public_research", "task_id": t2})
        assert l2.status_code == 200
        ex.gates[0].set()
        ra = await _bounded(a)
        after = dict(await _lease_row(store))
    assert ra.status_code == 200, ra.text
    assert ra.json()["state"] == "EXECUTION_FAILED"
    assert "EXECUTION_FAILED:BROWSER_HARNESS_LEASE_LOST" in ra.json()["reasons"]
    # Nothing reached the Harness, and task2's lease is untouched.
    assert transport.requests == []
    assert after["lease_holder_id"] == t2 and after["lease_generation"] == 2


async def test_a_step_with_its_lease_intact_reaches_the_harness_fenced(tmp_path):
    """The control for the test above: the same path does act when the lease is live."""
    transport = RecordingTransport()
    ex = GateThenHarness(_adapter(transport))
    ac, store, _api, _ = await _app(tmp_path, executor=ex)
    async with ac:
        t1 = (await t._make_task(ac))["task_id"]
        a = asyncio.create_task(ac.post("/v1/browser/interaction/step", headers=H, json=_step(t1)))
        await _bounded(ex.entered.get())
        gen = (await _lease_row(store))["lease_generation"]
        ex.gates[0].set()
        ra = await _bounded(a)
    assert ra.json()["state"] == "VERIFIED_SUCCESS", ra.text
    assert transport.requests == [("/click", gen)]


async def test_the_step_deadline_is_shorter_than_the_lease(tmp_path):
    ac, store, api, _ex = await _app(tmp_path)
    async with ac:
        task = await api._load_task((await t._make_task(ac))["task_id"])
        acquired, fence, deadline = await ir._step_page_lease(api, task)
        row = await store.fetchone("SELECT lease_expires_at_ms FROM browser_profiles WHERE profile_alias = 'public_research'")
    remaining = (int(row["lease_expires_at_ms"]) - int(time.time() * 1000)) / 1000
    assert acquired is not None and fence.generation == acquired.generation
    assert 0 < deadline <= remaining - ir.STEP_LEASE_MARGIN_MS / 1000 + 0.5, (deadline, remaining)


async def test_a_step_past_its_deadline_is_stopped(tmp_path, monkeypatch):
    real = ir._step_page_lease

    async def short(browser_api, task):
        acquired, fence, _deadline = await real(browser_api, task)
        return acquired, fence, 0.3

    monkeypatch.setattr(ir, "_step_page_lease", short)
    ac, store, _api, ex = await _app(tmp_path)
    async with ac:
        tid = (await t._make_task(ac))["task_id"]
        r = await _bounded(ac.post("/v1/browser/interaction/step", headers=H, json=_step(tid)))
        for gate in ex.gates:
            gate.set()
        row = await _lease_row(store)
    assert (r.status_code, r.json()["detail"]) == (504, "BROWSER_STEP_DEADLINE_EXCEEDED")
    assert ex.executed == []
    assert row["lease_holder"] is None  # the step's own lease is still given back


async def test_a_step_renews_a_lease_that_is_due(tmp_path):
    ac, store, _api, ex = await _app(tmp_path)
    async with ac:
        tid = (await t._make_task(ac))["task_id"]
        await ac.post("/v1/browser/leases", headers=H, json={"profile_alias": "public_research", "task_id": tid})
        now = int(time.time() * 1000)
        await store.execute(
            "UPDATE browser_profiles SET lease_expires_at_ms = ?, lease_acquired_at_ms = ? WHERE profile_alias = 'public_research'",
            (now + 60_000, now - 240_000))  # a 300 s lease with 60 s left
        gen = (await _lease_row(store))["lease_generation"]
        a = asyncio.create_task(ac.post("/v1/browser/interaction/step", headers=H, json=_step(tid)))
        await _bounded(ex.entered.get())
        row = await store.fetchone(
            "SELECT lease_expires_at_ms, lease_generation, lease_holder_id FROM browser_profiles WHERE profile_alias = 'public_research'")
        ex.gates[0].set()
        assert (await _bounded(a)).status_code == 200
    assert int(row["lease_expires_at_ms"]) > now + 250_000
    assert (row["lease_generation"], row["lease_holder_id"]) == (gen, tid)  # renewal never moves the fence


# ---------------------------------------------------------------------- /assignments


def _assignment(tid):
    return {"task_id": tid, "turn_id": "t1", "command_id": "cmd-owner-1", "goal": "read",
            "allowed_domains": [t.DOMAIN], "action_class_ceiling": "A2",
            "autonomy_tier": "L1_HARNESS_DETERMINISTIC",
            "plan": {"steps": [{"kind": "click", "domain": t.DOMAIN, "locator": "#go", "instruction": "Next"}]},
            "postcondition": {"kind": "READ_BACK", "field": "title", "expected": "Statement"}}


class _FenceSeeingHarness:
    def __init__(self) -> None:
        self.seen: list[tuple[str, HarnessLeaseFence | None]] = []

    async def navigate(self, task, url):
        self.seen.append(("navigate", current_harness_lease_fence()))
        return {}

    async def page_info(self, task):
        return {"url": f"https://{t.DOMAIN}/x", "title": "Statement", "extraction": {}}

    async def describe(self, task, loc):
        # Review I5: the plan's target is the element the Harness binds (a read, unfenced).
        return {"element": {"locator": loc, "role": "button", "name": "Next", "text": "Next", "tag": "button"},
                "matches": 1, "page_url": f"https://{t.DOMAIN}/x",
                "binding": {"backend_node_id": 4, "digest": "0" * 64}}

    async def click(self, task, loc, *, binding=None):
        self.seen.append(("click", current_harness_lease_fence()))
        return {}


async def test_assignment_harness_calls_carry_the_task_lease_generation(tmp_path):
    """Probe test_i4_fence.py #2."""
    harness = _FenceSeeingHarness()
    ac, _api, store = await t._client(tmp_path, worker=HybridBrowserWorker(harness, None), verifier=t._Verdict())
    async with ac:
        task = await t._make_task(ac, strategy="HARNESS", autonomy_tier="L1_HARNESS_DETERMINISTIC")
        await ac.post("/v1/browser/leases", headers=H, json={"profile_alias": task["profile_alias"], "task_id": task["task_id"]})
        gen = (await _lease_row(store))["lease_generation"]
        r = await ac.post("/v1/browser/assignments", headers=H, json=_assignment(task["task_id"]))
        assert r.status_code == 200, r.text
    assert harness.seen == [("click", HarnessLeaseFence("public_research", task["task_id"], gen))]
    assert harness.seen[0][1].guard is not None


async def test_assignment_takes_and_returns_a_lease_and_refuses_a_held_profile(tmp_path):
    harness = _FenceSeeingHarness()
    ac, _api, store = await t._client(tmp_path, worker=HybridBrowserWorker(harness, None), verifier=t._Verdict())
    async with ac:
        mine = await t._make_task(ac, strategy="HARNESS", autonomy_tier="L1_HARNESS_DETERMINISTIC")
        r = await ac.post("/v1/browser/assignments", headers=H, json=_assignment(mine["task_id"]))
        assert r.status_code == 200, r.text
        assert harness.seen[0][1] is not None and harness.seen[0][1].holder_id == mine["task_id"]
        assert (await _lease_row(store))["lease_holder"] is None  # the run's own lease was given back
        other = await t._make_task(ac, strategy="HARNESS", autonomy_tier="L1_HARNESS_DETERMINISTIC")
        await ac.post("/v1/browser/leases", headers=H, json={"profile_alias": "public_research", "task_id": other["task_id"]})
        third = await t._make_task(ac, strategy="HARNESS", autonomy_tier="L1_HARNESS_DETERMINISTIC")
        refused = await ac.post("/v1/browser/assignments", headers=H, json=_assignment(third["task_id"]))
    assert refused.status_code == 409 and "browser_profile_leased" in refused.json()["detail"]
    assert len(harness.seen) == 1


# ---------------------------------------------------------------------- watch runner


async def test_watch_runner_navigation_is_fenced(tmp_path):
    store = await make_store(tmp_path)
    goals = GoalService(store, AttentionEngine(store))
    await goals.create_watch(WatchCreate(
        title="w", source_kind=WatchSourceKind.BROWSER, target="https://example.com/0",
        condition={"kind": "TEXT_CONTAINS", "text": "available"}, interval_seconds=60), now_ms=1000)
    broker = BrowserSessionBroker(store)
    seen = []

    class Harness:
        async def status(self):
            return type("S", (), {"ready": True})()

        async def navigate(self, task, url):
            fence = current_harness_lease_fence()
            seen.append(fence)
            await fence.guard()  # the lease is live while the watch reads
            return {"url": url, "extraction": {"visible_text": "available"}}

    now = int(time.time() * 1000)
    result = await WatchRunner(goals, tasks=BrowserTaskService(store, broker), broker=broker, harness=Harness()).run(now_ms=now)
    assert result["checked"] == 1, result
    assert len(seen) == 1 and seen[0].profile_alias == "public_research" and seen[0].generation == 1


# ------------------------------------------------------------------- Harness worker


def _load(state_root):
    spec = importlib.util.spec_from_file_location("van_harness_service_fence", HARNESS_SERVICE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.FENCE = module.LeaseFence(state_root)
    return module


class _Worker:
    """The real Harness worker handler; ``restart()`` starts a fresh process image on the
    same state directory (what a systemd restart does)."""

    def __init__(self, state_root: Path) -> None:
        self.state_root = state_root
        self.clicks: list[str] = []
        self.server = None
        self.restart()

    def restart(self) -> None:
        self.stop()
        module = _load(self.state_root)
        module.OPERATIONS["/click"] = lambda body, alias, domain: self.clicks.append(body["locator"]) or {"ok": True}
        module.page_info_result = lambda alias, domain: {"url": "", "elements": []}
        self.module = module
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), module.Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def stop(self) -> None:
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()

    def post(self, path, **extra):
        return httpx.post(f"{self.url}{path}", json={
            "mode": "PRODUCTION_ACTUATOR", "allow_helper_authoring": False,
            "profile_alias": "public_research", "target_domain": "docs.example.com", **extra})


@pytest.fixture
def worker(tmp_path):
    w = _Worker(tmp_path / "harness-state")
    yield w
    w.stop()


def _task():
    import test_browser_interaction_router as tr

    return tr._task().model_copy(update={"profile_alias": "public_research", "target_domain": "docs.example.com"})


def test_the_harness_refuses_an_unfenced_mutation_and_allows_an_unfenced_read(worker):
    for path in ("/click", "/navigate", "/fill", "/press", "/scroll", "/upload"):
        r = worker.post(path, locator="#x", url="https://docs.example.com/")
        assert (r.status_code, r.json()["error"]) == (428, "LEASE_FENCE_REQUIRED"), path
    assert worker.clicks == []
    assert worker.post("/page_info").status_code == 200


async def test_the_adapter_never_sends_an_unfenced_mutation():
    transport = RecordingTransport()
    harness = _adapter(transport)
    with pytest.raises(BrowserAdapterError) as refused:
        await harness.click(_task(), "#x")
    assert refused.value.code == "BROWSER_HARNESS_LEASE_FENCE_REQUIRED"
    await harness.page_info(_task())  # reads need no fence
    assert transport.requests == [("/page_info", None)]


async def test_a_stale_generation_stays_refused_after_an_unfenced_holder_and_a_restart(worker):
    """Probe test_i4_fence.py #3, and the restart case."""
    harness = HttpBrowserHarnessAdapter(None, base_url=worker.url, enabled=True)
    task = _task()
    with harness_lease_fence(HarnessLeaseFence("public_research", "task-a", 4)):
        await harness.click(task, "#stepA-1")
    # The new holder cannot act unfenced any more ...
    assert worker.post("/click", locator="#taskB-unfenced").status_code == 428
    # ... so it acts fenced, which advances the fence.
    with harness_lease_fence(HarnessLeaseFence("public_research", "task-b", 5)):
        await harness.click(task, "#taskB-1")
    worker.restart()
    harness = HttpBrowserHarnessAdapter(None, base_url=worker.url, enabled=True)
    with harness_lease_fence(HarnessLeaseFence("public_research", "task-a", 4)):
        with pytest.raises(BrowserAdapterError) as stale:
            await harness.click(task, "#stepA-2-stale")
    assert stale.value.code == "BROWSER_HARNESS_LEASE_GENERATION_STALE"
    with harness_lease_fence(HarnessLeaseFence("public_research", "task-b", 5)):
        await harness.click(task, "#taskB-2")
    assert worker.clicks == ["#stepA-1", "#taskB-1", "#taskB-2"]
    state = json.loads((worker.state_root / "lease-fence-public_research.json").read_text())
    assert (state["generation"], state["holder_id"]) == (5, "task-b")


def test_unreadable_fence_state_refuses_rather_than_resets(worker):
    worker.state_root.mkdir(parents=True, exist_ok=True)
    (worker.state_root / "lease-fence-public_research.json").write_text("{not json")
    worker.restart()
    r = worker.post("/click", locator="#x", lease_generation=1, lease_holder_id="task-a")
    assert (r.status_code, r.json()["error"]) == (503, "LEASE_FENCE_STATE_INVALID")
    assert worker.clicks == []
