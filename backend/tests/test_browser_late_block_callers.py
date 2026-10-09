"""Unit G15 (review I8 MAJOR-2) — every caller that gives a page lease back reads what the
Harness's ``/release`` answer reports.

Owner decision 2026-09-30 (network-effect guard): "A blocked request goes to you." A write the
lease's guard blocks after a caller's last Harness call is reported only in the ``/release``
answer (``blocked``). Before G15 only ``/interaction/step`` read it (``_with_late_block``);
``/assignments``, ``/leases/release``, the watch runner and the notebook consumer threw it away
(review I8 measured ``/assignments`` -> COMPLETED and ``/leases/release`` -> PENDING with the
Harness answering ``NETWORK_WRITE_BLOCKED:POST``). Now each hands the task to the owner
(WAITING_FOR_OWNER, ``OWNER_TAKEOVER:...<code>``) and gives the lease back *before* writing
any end state, since nothing moves a task out of one. A read-only watch, which never acts,
still continues over background writes the guard dropped (owner answer after review I7,
"Block silently, continue").

Gateway cases answer the release with exactly what the real Harness answers (the shape review
I8 measured). The ``real`` cases drive the real Harness worker, egress proxy and Chromium.
"""
from __future__ import annotations

import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import cdp_harness_kit as kit
import test_browser_api as t
import test_browser_egress_proxy as ep
from conftest_automation import make_store
from test_browser_api import _settings  # noqa: F401 - autouse: the API settings the routes need
from van_gateway.attention.engine import AttentionEngine
from van_gateway.browser.adapters import HttpBrowserHarnessAdapter
from van_gateway.browser.api import BrowserApi
from van_gateway.browser.models import AutonomyTier, BrowserStrategy, BrowserTaskStatus
from van_gateway.browser.subagent import ProposedAction
from van_gateway.models import ActionClass
from van_gateway.browser.service import BrowserSessionBroker, BrowserTaskService, LeaseRelease, network_owner_code
from van_gateway.config import get_settings
from van_gateway.decisions.service import DecisionService

LATE = {"released": True, "blocked": "NETWORK_WRITE_BLOCKED:POST", "frozen": True, "guard": "ENDED", "dropped": []}
CLEAN = {"released": True, "blocked": None, "frozen": True, "guard": "ENDED", "dropped": []}

chromium = pytest.mark.skipif(
    not kit.chromium_available() or not Path("/usr/bin/openssl").is_file(),
    reason="needs the pinned Chromium and openssl",
)


async def _api(tmp_path, answer: dict, calls: list):
    store = await make_store(tmp_path)
    api = BrowserApi(store, get_settings(), worker=t._ScriptedWorker([ProposedAction(kind="extract", domain=t.DOMAIN, instruction="read the statement")]),
                     decisions=DecisionService(store, AttentionEngine(store)), verifier=t._Verdict())

    async def hook(**kw):
        calls.append(kw)
        return dict(answer)

    api.broker.page_release_hook = hook
    return api, store


async def _task(ac, task_id: str) -> dict:
    return (await ac.get(f"/v1/browser/tasks/{task_id}", headers=t.HEADERS)).json()["task"]


ASSIGNMENT = {"turn_id": "turn-1", "command_id": "cmd-owner-1", "goal": "read the statement total",
              "allowed_domains": [t.DOMAIN], "postcondition": {"kind": "READ_BACK"}}


def test_the_owner_code_is_the_closed_vocabulary_only():
    assert network_owner_code(LATE) == "NETWORK_WRITE_BLOCKED:POST"
    assert network_owner_code(CLEAN) is None and network_owner_code(None) is None
    assert network_owner_code({"blocked": "SOMETHING_ELSE"}) is None
    # A Harness answer under an owner prefix but outside the vocabulary is still the owner's.
    assert network_owner_code({"blocked": "NETWORK_WRITE_BLOCKED:https://x/pay?amount=5"}) == "NETWORK_GUARD_UNAVAILABLE"
    assert LeaseRelease(True, LATE).owner_code == "NETWORK_WRITE_BLOCKED:POST"


@pytest.mark.parametrize("answer", [LATE, CLEAN], ids=["late-block", "control"])
async def test_assignments_hands_a_late_block_to_the_owner(tmp_path, answer):
    calls: list = []
    api, _store = await _api(tmp_path, answer, calls)
    app = FastAPI(); app.include_router(api.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        task = await t._make_task(ac)
        r = await ac.post("/v1/browser/assignments", headers=t.HEADERS, json={"task_id": task["task_id"], **ASSIGNMENT})
        after = await _task(ac, task["task_id"])
    body = r.json()
    print(f"\nG15CALLER /assignments answer={answer['blocked']} http={r.status_code} stop={body.get('stop_reason')} "
          f"hook_calls={len(calls)} task=({after['status']},{after.get('error_code')})")
    assert r.status_code == 200 and len(calls) >= 1
    if answer is LATE:
        assert body["stop_reason"] == "OWNER_TAKEOVER" and body["succeeded"] is False and body["needs_owner"] is True
        assert after["status"] == "WAITING_FOR_OWNER"
        assert after["error_code"] == "OWNER_TAKEOVER:HARNESS_REFUSED:NETWORK_WRITE_BLOCKED:POST"
    else:
        assert body["stop_reason"] == "GOAL_ACHIEVED" and after["status"] == "COMPLETED"


async def test_assignments_on_a_lease_the_task_holds_ends_the_page_before_the_outcome(tmp_path):
    """The task held its lease before the run (``acquired`` is None): the run does not give the
    broker lease back, but it ends the page before writing COMPLETED, so a late block is read
    while the task can still go to the owner."""
    calls: list = []
    api, store = await _api(tmp_path, LATE, calls)
    app = FastAPI(); app.include_router(api.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        task = await t._make_task(ac)
        held = (await ac.post("/v1/browser/leases", headers=t.HEADERS,
                              json={"profile_alias": "public_research", "task_id": task["task_id"]})).json()
        r = await ac.post("/v1/browser/assignments", headers=t.HEADERS, json={"task_id": task["task_id"], **ASSIGNMENT})
        after = await _task(ac, task["task_id"])
    assert calls and calls[0]["holder_id"] == task["task_id"] and held["lease_id"]
    assert r.json()["stop_reason"] == "OWNER_TAKEOVER"
    assert (after["status"], after["error_code"]) == ("WAITING_FOR_OWNER", "OWNER_TAKEOVER:HARNESS_REFUSED:NETWORK_WRITE_BLOCKED:POST")


async def test_assignments_that_raise_still_hand_a_late_block_to_the_owner(tmp_path):
    calls: list = []
    api, _store = await _api(tmp_path, LATE, calls)

    async def boom(**_kw):
        raise RuntimeError("runner fault")

    api.runner.run = boom
    app = FastAPI(); app.include_router(api.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        task = await t._make_task(ac)
        with pytest.raises(RuntimeError):
            await ac.post("/v1/browser/assignments", headers=t.HEADERS, json={"task_id": task["task_id"], **ASSIGNMENT})
        after = await _task(ac, task["task_id"])
    assert (after["status"], after["error_code"]) == ("WAITING_FOR_OWNER", "OWNER_TAKEOVER:NETWORK_WRITE_BLOCKED:POST")


@pytest.mark.parametrize("answer", [LATE, CLEAN], ids=["late-block", "control"])
async def test_leases_release_hands_a_late_block_to_the_owner(tmp_path, answer):
    calls: list = []
    api, _store = await _api(tmp_path, answer, calls)
    app = FastAPI(); app.include_router(api.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        task = await t._make_task(ac)
        held = (await ac.post("/v1/browser/leases", headers=t.HEADERS,
                              json={"profile_alias": "public_research", "task_id": task["task_id"]})).json()
        r = await ac.post("/v1/browser/leases/release", headers=t.HEADERS, json={
            "lease_id": held["lease_id"], "profile_alias": "public_research", "task_id": task["task_id"]})
        after = await _task(ac, task["task_id"])
    body = r.json()
    print(f"\nG15CALLER /leases/release answer={answer['blocked']} body={body} task=({after['status']},{after.get('error_code')})")
    assert r.status_code == 200 and len(calls) == 1
    if answer is LATE:
        assert body["blocked"] == "NETWORK_WRITE_BLOCKED:POST" and body["task_status"] == "WAITING_FOR_OWNER"
        assert (after["status"], after["error_code"]) == ("WAITING_FOR_OWNER", "OWNER_TAKEOVER:NETWORK_WRITE_BLOCKED:POST")
    else:
        assert "blocked" not in body and after["status"] == "PENDING"


async def test_complete_cannot_write_completed_over_a_late_block_on_a_held_lease(tmp_path):
    calls: list = []
    api, store = await _api(tmp_path, LATE, calls)
    app = FastAPI(); app.include_router(api.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        task = await t._make_task(ac)
        await ac.post("/v1/browser/leases", headers=t.HEADERS,
                      json={"profile_alias": "public_research", "task_id": task["task_id"]})
        await api.tasks.record_verification(task=await api._load_task(task["task_id"]), outcome="VERIFIED",
                                            verifier="test", detail="read back")
        r = await ac.post(f"/v1/browser/tasks/{task['task_id']}/complete", headers=t.HEADERS,
                          json={"status": "COMPLETED"})
        after = await _task(ac, task["task_id"])
    assert r.status_code == 409 and r.json()["detail"].startswith("BROWSER_TASK_HANDED_TO_OWNER:NETWORK_WRITE_BLOCKED:POST")
    assert after["status"] == "WAITING_FOR_OWNER" and len(calls) == 1


async def test_a_terminal_task_stays_terminal_and_the_release_still_reports_the_code(tmp_path):
    """Ordering: a caller that wrote an end state first cannot move the task afterwards (the
    guarded writer refuses) — the /leases/release answer still carries the code."""
    calls: list = []
    api, store = await _api(tmp_path, LATE, calls)
    app = FastAPI(); app.include_router(api.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        task = await t._make_task(ac)
        held = (await ac.post("/v1/browser/leases", headers=t.HEADERS,
                              json={"profile_alias": "public_research", "task_id": task["task_id"]})).json()
        await api.tasks.complete(task_id=task["task_id"], status=BrowserTaskStatus.CANCELLED)
        r = await ac.post("/v1/browser/leases/release", headers=t.HEADERS, json={
            "lease_id": held["lease_id"], "profile_alias": "public_research", "task_id": task["task_id"]})
        after = await _task(ac, task["task_id"])
    assert r.json()["blocked"] == "NETWORK_WRITE_BLOCKED:POST" and r.json()["task_status"] == "CANCELLED"
    assert after["status"] == "CANCELLED"


# ------------------------------------------------------------------ the notebook consumer


async def test_the_notebook_consumer_gives_the_lease_back_before_its_end_state(tmp_path):
    from van_gateway.knowledge.evidence import KnowledgeEvidenceStore
    from van_gateway.knowledge.notebook import NotebookConsumerProvider, NotebookProviderError

    store = await make_store(tmp_path)
    broker = BrowserSessionBroker(store)
    calls: list = []

    async def hook(**kw):
        calls.append(kw)
        return dict(LATE)

    broker.page_release_hook = hook
    tasks = BrowserTaskService(store, broker)
    provider = NotebookConsumerProvider(store, KnowledgeEvidenceStore(store), enabled=True, browser_tasks=tasks,
                                        profile_alias="public_research")
    provider._require_transport = lambda: (tasks, None, None)  # the consumer is UNAVAILABLE; its close is under test
    await broker.register_profile(profile_alias="public_research")
    task = await tasks.create_task(profile_alias="public_research", strategy=BrowserStrategy.HARNESS,
                                   autonomy_tier=AutonomyTier.L1_HARNESS_DETERMINISTIC, action_class=ActionClass.A1,
                                   target_domain="notebooklm.google.com", goal="read a notebook")
    lease = await broker.acquire_lease(profile_alias="public_research", task_id=task.task_id)
    with pytest.raises(NotebookProviderError, match="notebook_consumer_owner_takeover:NETWORK_WRITE_BLOCKED:POST"):
        await provider._close_task(task, lease, status=BrowserTaskStatus.COMPLETED)
    # The provider's error path closes the task again: nothing is written over the owner's state.
    await provider._close_task(task, lease, status=BrowserTaskStatus.FAILED, error_code="NotebookProviderError")
    row = await store.fetchone("SELECT status, error_code FROM browser_tasks WHERE task_id = ?", (task.task_id,))
    assert (row["status"], row["error_code"]) == ("WAITING_FOR_OWNER", "OWNER_TAKEOVER:NETWORK_WRITE_BLOCKED:POST")
    assert len(calls) == 1


# ------------------------------------------------------------------ the watch runner


async def _watch_run(tmp_path, harness, broker_hook, target: str):
    from van_gateway.goals.models import WatchCreate, WatchSourceKind
    from van_gateway.goals.service import GoalService
    from van_gateway.goals.watch_runner import WatchRunner
    from van_gateway.storage.db import Store

    store = Store(str(tmp_path / "van.sqlite3"))
    await store.migrate()
    service = GoalService(store, AttentionEngine(store))
    watch = await service.create_watch(WatchCreate(title="w", source_kind=WatchSourceKind.BROWSER, target=target,
                                                   condition={"kind": "TEXT_CONTAINS", "text": "available"},
                                                   interval_seconds=60), now_ms=int(time.time() * 1000) - 1000)
    broker = BrowserSessionBroker(store)
    broker.page_release_hook = broker_hook
    runner = WatchRunner(service, tasks=BrowserTaskService(store, broker), broker=broker, harness=harness)
    out = await runner.run()
    row = await store.fetchone("SELECT status, error_code FROM browser_tasks ORDER BY rowid DESC LIMIT 1")
    return out, (row["status"], row["error_code"]), watch.watch_id


class _Ready:
    ready = True


class _FakeHarness:
    def __init__(self, nav_error: Exception | None = None) -> None:
        self.nav_error = nav_error

    async def status(self):
        return _Ready()

    async def navigate(self, task, url):
        if self.nav_error is not None:
            raise self.nav_error
        return {"url": url, "title": "t", "extraction": {"visible_text": "release available"}}


@pytest.mark.parametrize(("answer", "expected"), [
    (LATE, ("WAITING_FOR_OWNER", "OWNER_TAKEOVER:NETWORK_WRITE_BLOCKED:POST")),
    ({**CLEAN, "dropped": ["BEACON", "POST"]}, ("COMPLETED", None)),  # background writes a watch never caused
    (CLEAN, ("COMPLETED", None)),
], ids=["late-block", "dropped-background", "control"])
async def test_the_watch_runner_reads_the_release_before_its_end_state(tmp_path, answer, expected):
    async def hook(**_kw):
        return dict(answer)

    out, task_row, _ = await _watch_run(tmp_path, _FakeHarness(), hook, "https://docs.example.com/docs/w")
    print(f"\nG15CALLER watch answer={answer['blocked']} dropped={answer['dropped']} run={out} task={task_row}")
    assert task_row == expected
    assert out["failed"] == (1 if answer is LATE else 0)


async def test_a_watch_whose_navigate_was_refused_still_hands_the_release_code_to_the_owner(tmp_path):
    from van_gateway.browser.adapters import BrowserAdapterError

    async def hook(**_kw):
        return {**LATE, "blocked": "NETWORK_WRITE_DETECTED:WEBSOCKET"}

    err = BrowserAdapterError("BROWSER_HARNESS_REFUSED", "NETWORK_WRITE_DETECTED:WEBSOCKET")
    out, task_row, _ = await _watch_run(tmp_path, _FakeHarness(err), hook, "https://docs.example.com/docs/w")
    assert task_row == ("WAITING_FOR_OWNER", "OWNER_TAKEOVER:NETWORK_WRITE_DETECTED:WEBSOCKET")


# ------------------------------------------------------------------ real worker, proxy and Chromium


def _real(monkeypatch, tmp_path, pages: dict[str, str]):
    def _p(host, path):
        page = pages.get(path)
        return f"<!doctype html><html><head><title>{path}</title></head><body>{page}</body></html>" if page else None

    monkeypatch.setattr(ep, "_pages", _p)
    rig = ep.EgressRig(monkeypatch, tmp_path)
    module = rig.hs
    session = rig.launch("public_research")
    lock = threading.Lock()

    def run_harness(_alias, script, extra=None):
        with lock:
            return kit.exec_script(session, script, extra)

    monkeypatch.setattr(module, "run_harness", run_harness)
    server = ThreadingHTTPServer(("127.0.0.1", 0), module.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    harness = HttpBrowserHarnessAdapter(None, base_url=f"http://127.0.0.1:{server.server_address[1]}", enabled=True,
                                        fence_key=ep.KEY)

    def close():
        module.NET_GUARDS.close(); server.shutdown(); server.server_close(); rig.close()

    return rig, harness, close


WPAGES = {
    "/docs/analytics": "<script>navigator.sendBeacon('/collect','pageview');fetch('/collect',{method:'POST',body:'load'})</script><p>release available</p>",
    "/docs/ws_after_load": "<script>setTimeout(()=>{window.__ws=new WebSocket('wss://docs.example.com/api/ws-pay?amount=500')},1500)</script><p>release available</p>",
    "/docs/post_after_load": "<script>setTimeout(()=>fetch('/api/pay',{method:'POST',body:'x'}),1500)</script><p>release available</p>",
}


@chromium
@pytest.mark.parametrize(("path", "expected"), [
    ("/docs/analytics", ("COMPLETED", None)),
    ("/docs/post_after_load", ("COMPLETED", None)),
    ("/docs/ws_after_load", ("WAITING_FOR_OWNER", "OWNER_TAKEOVER:NETWORK_WRITE_DETECTED:WEBSOCKET")),
])
async def test_the_watch_runner_real_harness(monkeypatch, tmp_path, path, expected):
    rig, harness, close = _real(monkeypatch, tmp_path, WPAGES)
    releases: list = []
    real_release = harness.release_page

    async def spy(**kw):
        out = await real_release(**kw)
        releases.append(out)
        return out

    async def _status():
        return _Ready()

    harness.status = _status  # the registry is not under test; the runtime is up
    try:
        rig.clear()
        out, task_row, _ = await _watch_run(tmp_path, harness, spy, f"https://docs.example.com{path}")
        time.sleep(3.0)
        writes = [e for e in rig.server_log() if e[0] not in kit.READ_METHODS or "pay" in e[2]]
        print(f"\nG15WATCH {path} run={out} task={task_row} release={releases} server_writes={writes}")
        assert writes == []
        assert task_row == expected
    finally:
        close()


@chromium
async def test_assignments_real_harness_late_write_goes_to_the_owner(monkeypatch, tmp_path):
    from van_gateway.browser.worker import AdapterBackedWorker

    pages = {"/docs/delay2500": "<button id=\"b\" onclick=\"setTimeout(()=>fetch('/api/pay',{method:'POST',body:'amount=500'}),2500)\">Next</button>"}
    rig, harness, close = _real(monkeypatch, tmp_path, pages)
    releases: list = []
    real_release = harness.release_page

    async def spy(**kw):
        out = await real_release(**kw)
        releases.append(out)
        return out

    try:
        store = await make_store(tmp_path)
        api = BrowserApi(store, get_settings(), worker=AdapterBackedWorker(harness),
                         decisions=DecisionService(store, AttentionEngine(store)), verifier=t._Verdict())
        api.broker.page_release_hook = spy
        app = FastAPI(); app.include_router(api.router)
        dom = "docs.example.com"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            task = await t._make_task(ac, target_domain=dom, scope=[f"https://{dom}/docs/"],
                                      autonomy_tier="L1_HARNESS_DETERMINISTIC", strategy="HARNESS")
            rig.clear()
            r = await ac.post("/v1/browser/assignments", headers=t.HEADERS, json={
                "task_id": task["task_id"], "turn_id": "turn-1", "command_id": "cmd-owner-1",
                "goal": "open the guide", "allowed_domains": [dom], "autonomy_tier": "L1_HARNESS_DETERMINISTIC",
                "plan": {"steps": [{"kind": "navigate", "domain": dom, "url": f"https://{dom}/docs/delay2500"},
                                   {"kind": "click", "domain": dom, "locator": "#b", "instruction": "Next"}]},
                "postcondition": {"kind": "READ_BACK"}})
            time.sleep(6.0)
            after = await _task(ac, task["task_id"])
        writes = [e for e in rig.server_log() if e[0] not in kit.READ_METHODS or "pay" in e[2]]
        body = r.json()
        print(f"\nG15CALLER /assignments(real) http={r.status_code} stop={body.get('stop_reason')} release={releases} "
              f"task=({after['status']},{after.get('error_code')}) server_writes={writes}")
        assert writes == []
        assert any(network_owner_code(x) for x in releases)
        assert body["stop_reason"] == "OWNER_TAKEOVER"
        assert after["status"] == "WAITING_FOR_OWNER" and "NETWORK_WRITE_BLOCKED" in (after.get("error_code") or "")
    finally:
        close()


async def test_a_release_the_harness_never_answered_goes_to_the_owner(tmp_path):
    """Review I9 MINOR-1: ``release_page`` swallowed a failed ``/release`` (a timeout on the
    busy renderer of review I8 MAJOR-1) and returned None, which reads as clean: the task
    COMPLETED and a write the guard blocked after the last call was never reported. What the
    guard saw is unknown, so the owner gets it as NETWORK_GUARD_UNAVAILABLE; the lease is still
    given back."""
    calls: list = []
    api, store = await _api(tmp_path, CLEAN, calls)

    async def timeout(**kw):
        calls.append(kw)
        raise TimeoutError("release timed out")

    api.broker.page_release_hook = timeout
    app = FastAPI(); app.include_router(api.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        task = await t._make_task(ac)
        r = await ac.post("/v1/browser/assignments", headers=t.HEADERS, json={"task_id": task["task_id"], **ASSIGNMENT})
        after = await _task(ac, task["task_id"])
    body = r.json()
    print(f"\nI9 /assignments release=TimeoutError http={r.status_code} stop={body.get('stop_reason')} "
          f"task=({after['status']},{after.get('error_code')})")
    assert calls and r.status_code == 200
    assert body["stop_reason"] == "OWNER_TAKEOVER" and body["needs_owner"] is True
    assert after["status"] == "WAITING_FOR_OWNER"
    assert after["error_code"].endswith("NETWORK_GUARD_UNAVAILABLE")
    held = await store.fetchone("SELECT lease_holder FROM browser_profiles WHERE profile_alias = ?", ("public_research",))
    assert held is None or held["lease_holder"] is None


async def test_a_failed_release_is_never_read_as_clean_by_the_broker(tmp_path):
    store = await make_store(tmp_path)
    broker = BrowserSessionBroker(store)
    await broker.register_profile(profile_alias="public_research")

    async def refuse(**_kw):
        raise ConnectionError("harness down")

    broker.page_release_hook = refuse
    lease = await broker.acquire_lease(profile_alias="public_research", task_id="task-i9")
    out = await broker.release_lease_if_held(lease)
    assert out.released is True and out.owner_code == "NETWORK_GUARD_UNAVAILABLE"
    # Without a Harness there is no guard and nothing to report.
    broker.page_release_hook = None
    lease = await broker.acquire_lease(profile_alias="public_research", task_id="task-i9b")
    assert (await broker.release_lease_if_held(lease)).owner_code is None
