"""Unit G11 (review I7) — the network-effect guard lives as long as the page lease.

Review I7 MAJOR-1: the guard was on for ~1.8 s around each action. A write the page issued
after that — a 2.5 s or 6 s timer, a retry after the block, a service worker's or dedicated
worker's delayed fetch, a popup's timer — reached the server. Now the guard is kept on for the
whole lease (between calls the worker's guard thread answers paused requests), fails every
write outside an action window, freezes the page on any block, and is ended — page frozen,
interception removed — when the lease is given back.

Every case drives the real Harness worker HTTP handler against headless Chromium 1194 with the
worker's guard flags (``cdp_harness_kit``). The instrument is the fixture HTTPS server's request
log, outside the browser, read at least 8 s after the step.
"""
from __future__ import annotations

import pathlib
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
from typing import Any

import pytest

import cdp_harness_kit as kit
import test_browser_api as t
from test_browser_api import _settings  # noqa: F401 - autouse: the API settings the routes need
import test_browser_interaction_router as tr
import test_harness_elements as he
from van_gateway.browser.adapters import BrowserAdapterError, HarnessLeaseFence, HttpBrowserHarnessAdapter, harness_lease_fence
from van_gateway.browser.interaction_router import DeterministicAction, HarnessActionExecutor, HarnessTargetResolver, StepState
from van_gateway.browser.task_scope import scope_for_new_task

pytestmark = pytest.mark.skipif(not kit.chromium_available(), reason="no Chromium for the network-effect guard")

DOMAIN = he.DOMAIN
PAY = "fetch('/api/pay',{method:'POST',body:'amount=500'})"
#: Review I7's instrument wait: a write that escapes is on the server log by then.
LATE_WRITE_WAIT_SECONDS = 8.5

PAGES: dict[str, Any] = {
    # --- the six review I7 MAJOR-1 escapes
    "/docs/delay2500": f'<button id="b" onclick="setTimeout(()=>{PAY},2500)">Next</button>',
    "/docs/delay6000": f'<button id="b" onclick="setTimeout(()=>{PAY},6000)">Next</button>',
    "/docs/retry": "<button id=\"b\" onclick=\"fetch('/api/pay',{method:'POST',body:'a'}).catch(()=>setTimeout(()=>"
                   "fetch('/api/pay',{method:'POST',body:'retry'}),3000))\">Next</button>",
    "/docs/sw_delay": "<button id=\"b\" onclick=\"navigator.serviceWorker.controller.postMessage('pay')\">Next</button>"
                      "<script>navigator.serviceWorker.register('/docs/swd.js')</script>",
    "/docs/swd.js": ("text/javascript", "self.addEventListener('install',e=>self.skipWaiting());"
                     "self.addEventListener('activate',e=>e.waitUntil(clients.claim()));"
                     "self.addEventListener('message',e=>e.waitUntil(new Promise(r=>setTimeout(()=>"
                     "fetch('/api/pay',{method:'POST',body:'sw'}).finally(r),3000))));"),
    "/docs/dworker": "<script>window.__w=new Worker(URL.createObjectURL(new Blob([\"onmessage=()=>setTimeout(()=>"
                     "fetch('https://docs.example.com/api/pay',{method:'POST',body:'dw'}),3000)\"])))</script>"
                     "<button id=\"b\" onclick=\"window.__w.postMessage(1)\">Next</button>",
    "/docs/open_blank_delay": "<button id=\"b\" onclick=\"const w=window.open('');w.setTimeout(()=>"
                              "w.fetch('https://docs.example.com/api/pay',{method:'POST',body:'w'}),4000)\">Next</button>",
    # --- owner answer after review I7: background writes of a read-only task
    "/docs/analytics": "<script>navigator.sendBeacon('/collect','pageview');"
                       "fetch('/collect',{method:'POST',body:'load'})</script><a id=\"b\" href=\"/docs/next\">Next</a>",
    "/docs/next": "<p>next</p>",
    "/docs/to_analytics": '<a id="b" href="/docs/analytics">Next</a>',
    "/docs/websocket": "<button id=\"b\" onclick=\"window.__ws=new WebSocket('wss://docs.example.com/api/ws')\">Next</button>",
    # --- the settle window on its own (review I7 minor 11)
    "/docs/timeout300": f'<button id="b" onclick="setTimeout(()=>{PAY},300)">Next</button>',
    # --- a quiet page: what still works between actions under the guard
    "/docs/get_later": "<button id=\"b\" onclick=\"setTimeout(()=>fetch('/docs/data').then(r=>r.text())"
                       ".then(()=>document.title='got'),2500)\">Next</button>",
}
#: review I7 minor 6 — an out-of-scope document that rewrites its URL into the scope.
CHECKOUT = ("<!doctype html><html><head><title>Receipt</title></head><body>"
            "<script>window.__real='CHECKOUT';window.__van=[];history.replaceState({},'','/docs/receipt')</script>"
            "<button id=\"b\" onclick=\"window.__van.push('acted-on:'+window.__real)\">Next</button></body></html>")


def _pages(host: str, path: str):
    if host.startswith("evil"):
        return None
    if path == "/checkout/pay":
        return CHECKOUT
    page = PAGES.get(path)
    if isinstance(page, str):
        return f"<!doctype html><html><head><title>{path}</title></head><body>{page}</body></html>"
    return page


def _task(*, mutating: bool = False):
    scope = scope_for_new_task(DOMAIN, [f"https://{DOMAIN}/docs/"])
    return he._task().model_copy(update={"scope": scope, "mutating": mutating})


@pytest.fixture
def g(monkeypatch, tmp_path):
    module = he._load(monkeypatch, tmp_path)
    rig = kit.Rig(_pages, module.NETWORK_GUARD_CHROMIUM_FLAGS, tmp_path)
    monkeypatch.setattr(module, "run_harness", rig.run_harness)
    server = ThreadingHTTPServer(("127.0.0.1", 0), module.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        yield module, rig, HttpBrowserHarnessAdapter(None, base_url=base, enabled=True), base
    finally:
        module.NET_GUARDS.close()
        server.shutdown()
        server.server_close()
        rig.close()


def _pay_writes(rig) -> list[tuple[str, str, str]]:
    return [e for e in rig.server.writes() if "pay" in e[2]]


async def _click(g, path, *, task=None, prep=None, goto=True):
    module, rig, harness, _base = g
    if goto:
        rig.session.goto(f"https://{DOMAIN}{path}")
        time.sleep(0.2)
    if prep:
        prep(rig)
    rig.session.drain_events()
    rig.server.log.clear()
    task = task or _task()
    router = tr.make_router(target_resolver=HarnessTargetResolver(harness), executor=HarnessActionExecutor(harness),
                            semantic_fallback=tr.FakeStagehand(None), jev_client=None)
    step = tr.step(deterministic_action=DeterministicAction(operation="click", locator="#b", value_ref=None))
    step.task = task
    with harness_lease_fence(HarnessLeaseFence(task.profile_alias, task.task_id, 1)):
        result = await router.route(step)
    return result, task


def _sw_controls(rig):
    for _ in range(80):
        if rig.session.js("!!navigator.serviceWorker.controller"):
            return
        time.sleep(0.1)
        if _ % 10 == 9:
            rig.session.goto(rig.session.js("location.href"))
    raise AssertionError("service worker never controlled the page")


def _lease(module):
    return module.NET_GUARDS.leases.get("public_research")


# ------------------------------------------------------------------ review I7 MAJOR-1


@pytest.mark.parametrize("path", ["/docs/delay2500", "/docs/delay6000", "/docs/retry", "/docs/sw_delay",
                                  "/docs/dworker", "/docs/open_blank_delay"])
async def test_a_write_after_the_action_window_never_reaches_the_server(g, path):
    """I7's escapes: each of these reached the server before unit G11. Now each is failed by the
    lease's guard, the page is frozen, and the lease refuses further actions with the code."""
    module, rig, harness, _base = g
    result, task = await _click(g, path, prep=_sw_controls if path == "/docs/sw_delay" else None)
    time.sleep(LATE_WRITE_WAIT_SECONDS)
    assert _pay_writes(rig) == [], rig.server.log
    lease = _lease(module)
    assert lease is not None and lease.pending == "NETWORK_WRITE_BLOCKED:POST", (lease and lease.pending, result.reasons)
    assert lease.frozen and rig.session.js("location.href") == "about:blank"
    assert len([x for x in rig.session.send("Target.getTargets")["targetInfos"] if x["type"] == "page"]) == 1
    # The next action of the lease is refused with the code (and goes to the owner).
    with harness_lease_fence(HarnessLeaseFence(task.profile_alias, task.task_id, 1)):
        with pytest.raises(BrowserAdapterError) as refused:
            await harness.scroll(task, {"y": 10})
    assert (refused.value.code, refused.value.detail) == ("BROWSER_HARNESS_REFUSED", "NETWORK_WRITE_BLOCKED:POST")
    # Giving the lease back reports it and removes the lease's guard.
    report = await harness.release_page(profile_alias=task.profile_alias, holder_id=task.task_id, generation=1)
    assert (report["blocked"], report["guard"]) == ("NETWORK_WRITE_BLOCKED:POST", "ENDED")
    assert _lease(module) is None and _pay_writes(rig) == []


async def test_the_retry_after_a_block_is_stopped_by_the_freeze(g):
    """The first write is blocked in the action window (lane 4 at once); the page is frozen
    before the step returns, so the retry the page scheduled never runs."""
    module, rig, _h, _b = g
    result, _task_ = await _click(g, "/docs/retry")
    assert result.state is StepState.OWNER_TAKEOVER
    assert "HARNESS_REFUSED:NETWORK_WRITE_BLOCKED:POST" in result.reasons, result.reasons
    assert rig.session.js("location.href") == "about:blank"
    time.sleep(LATE_WRITE_WAIT_SECONDS)
    assert _pay_writes(rig) == []


async def test_releasing_the_lease_freezes_the_page_before_a_late_write(g):
    """The lease is given back 0.5 s after the step; the page's 6 s timer never fires."""
    module, rig, harness, _base = g
    result, task = await _click(g, "/docs/delay6000")
    assert result.state is StepState.VERIFIED_SUCCESS, result.reasons
    report = await harness.release_page(profile_alias=task.profile_alias, holder_id=task.task_id, generation=1)
    assert (report["blocked"], report["frozen"], report["guard"]) == (None, True, "ENDED")
    assert rig.session.js("location.href") == "about:blank"
    time.sleep(LATE_WRITE_WAIT_SECONDS)
    assert rig.server.writes() == []


async def test_a_newer_lease_ends_the_older_leases_guard_first(g):
    module, rig, harness, _base = g
    result, task = await _click(g, "/docs/delay6000")
    assert result.state is StepState.VERIFIED_SUCCESS
    newer = _task().model_copy(update={"task_id": "task-newer"})
    with harness_lease_fence(HarnessLeaseFence(newer.profile_alias, newer.task_id, 2)):
        info = await harness.page_info(newer)
    assert info["url"] == "about:blank"  # the older lease's page was frozen before gen 2 ran
    assert _lease(module).generation == 2
    time.sleep(LATE_WRITE_WAIT_SECONDS)
    assert rig.server.writes() == []


async def test_reads_between_actions_still_flow_under_the_guard(g):
    """The guard answers between calls: a read the page makes 2.5 s after the step completes."""
    module, rig, _h, _b = g
    result, _task_ = await _click(g, "/docs/get_later")
    assert result.state is StepState.VERIFIED_SUCCESS, result.reasons
    for _ in range(60):
        if rig.session.js("document.title") == "got":
            break
        time.sleep(0.1)
    assert rig.session.js("document.title") == "got"
    assert ("GET", DOMAIN, "/docs/data") in rig.server.log and _lease(module).pending is None


# ------------------------------------------------------------------ owner answer after review I7


async def test_a_load_time_beacon_on_a_read_only_watch_is_dropped_and_the_task_continues(g):
    """"Block silently, continue": a read-only task's navigate to a page that sends analytics on
    load succeeds; the writes are failed, reported by kind only, and nothing is frozen."""
    module, rig, harness, _base = g
    rig.session.goto(f"https://{DOMAIN}/docs/next")
    rig.server.log.clear()
    task = _task()
    with harness_lease_fence(HarnessLeaseFence(task.profile_alias, task.task_id, 1)):
        info = await harness.navigate(task, f"https://{DOMAIN}/docs/analytics")
        again = await harness.page_info(task)
    time.sleep(1.0)
    assert info["url"] == f"https://{DOMAIN}/docs/analytics" and again["url"] == info["url"]
    assert sorted(info.get("network_background_writes_dropped") or []) == ["BEACON", "POST"]
    assert "collect" not in str(info) and "pageview" not in str(info)
    assert rig.server.writes() == []
    lease = _lease(module)
    assert lease.pending is None and not lease.frozen


async def test_a_delayed_write_after_a_click_on_a_read_only_task_still_goes_to_the_owner(g):
    module, rig, harness, _base = g
    result, task = await _click(g, "/docs/delay2500")
    assert result.state is StepState.VERIFIED_SUCCESS  # the step itself ended before the write
    time.sleep(LATE_WRITE_WAIT_SECONDS)
    assert rig.server.writes() == []
    assert _lease(module).pending == "NETWORK_WRITE_BLOCKED:POST" and _lease(module).frozen


async def test_a_background_write_after_the_first_click_is_not_background(g):
    """Attribution: after the first automated input event, a load-time write of the next page
    is action-triggered: it goes to the owner."""
    module, rig, harness, _base = g
    result, _task_ = await _click(g, "/docs/to_analytics")
    assert result.state is StepState.OWNER_TAKEOVER, result.reasons
    assert any(r.startswith("HARNESS_REFUSED:NETWORK_WRITE_BLOCKED:") for r in result.reasons), result.reasons
    assert rig.server.writes() == [] and rig.session.js("location.href") == "about:blank"


# ------------------------------------------------------------------ review I7 minor 1


async def test_a_websocket_open_is_detected_named_so_and_the_page_is_closed(g):
    module, rig, _h, _b = g
    result, _task_ = await _click(g, "/docs/websocket")
    assert result.state is StepState.OWNER_TAKEOVER
    assert "HARNESS_REFUSED:NETWORK_WRITE_DETECTED:WEBSOCKET" in result.reasons, result.reasons
    assert not any("NETWORK_WRITE_BLOCKED:WEBSOCKET" in r for r in result.reasons)
    assert rig.session.js("location.href") == "about:blank"


# ------------------------------------------------------------------ review I7 minor 11


async def test_the_settle_window_alone_catches_a_write_between_the_action_and_the_landing(g, monkeypatch):
    """A write 300 ms after the click lands after the input dispatch returned and before any
    landing check. With the landing check and the lease-long service both switched off, the
    action script's own settle window is what blocks it."""
    module, rig, _h, _b = g
    monkeypatch.setattr(module, "_landing_check", lambda alias, body: None)
    monkeypatch.setattr(module.NET_GUARDS, "_ensure_thread", lambda: None)
    result, _task_ = await _click(g, "/docs/timeout300")
    assert result.state is StepState.OWNER_TAKEOVER, result.reasons
    assert "HARNESS_REFUSED:NETWORK_WRITE_BLOCKED:POST" in result.reasons, result.reasons
    assert rig.server.writes() == []


# ------------------------------------------------------------------ review I7 minor 6


@pytest.mark.parametrize("commit_seen", [True, False], ids=["frame-navigated", "navigation-timing"])
async def test_a_document_replacestated_into_the_scope_is_judged_by_its_real_url(g, commit_seen):
    """/checkout/pay (outside the /docs/ scope) rewrites its URL to /docs/receipt. The frame URL
    says /docs/receipt; the document is /checkout/pay. The click is refused, nothing acted."""
    module, rig, _h, _b = g
    rig.session.goto(f"https://{DOMAIN}/checkout/pay")
    assert rig.session.send("Page.getFrameTree", session_id=rig.session.session)["frameTree"]["frame"]["url"].endswith("/docs/receipt")
    if not commit_seen:
        rig.session._drain_all()  # the commit event is gone: the navigation timing entry decides
    result, _task_ = await _click(g, "/checkout/pay", goto=False)
    assert result.state is StepState.OWNER_TAKEOVER, result.reasons
    assert "HARNESS_REFUSED:TASK_SCOPE_PAGE_PATH_OUTSIDE" in result.reasons, result.reasons
    assert rig.session.js("window.__van") == []


# ------------------------------------------------------------------ the gateway gives the lease back


async def test_interaction_step_gives_the_lease_back_through_the_harness(g, tmp_path):
    """/interaction/step with a lease of its own: the broker's release ends the Harness guard
    (the page is frozen), so the page's 6 s write never happens."""
    module, rig, harness, _b = g
    rig.session.goto(f"https://{t.DOMAIN}/docs/delay6000")
    rig.server.log.clear()
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from conftest_automation import make_store
    from van_gateway.attention.engine import AttentionEngine
    from van_gateway.browser.api import BrowserApi
    from van_gateway.browser.interaction_router import build_interaction_routes
    from van_gateway.config import get_settings
    from van_gateway.decisions.service import DecisionService

    store = await make_store(tmp_path)
    api = BrowserApi(store, get_settings(), worker=t._ScriptedWorker([]),
                     decisions=DecisionService(store, AttentionEngine(store)), verifier=t._Verdict())
    api.broker.page_release_hook = harness.release_page
    calls: list[Any] = []
    real = harness.release_page

    async def spy(**kw):
        calls.append(kw)
        return await real(**kw)

    api.broker.page_release_hook = spy

    async def observe(task):
        return {"url": f"https://{t.DOMAIN}/docs/delay6000"}

    router = tr.make_router(executor=HarnessActionExecutor(harness), target_resolver=HarnessTargetResolver(harness),
                            jev_client=None, semantic_fallback=tr.FakeStagehand(None), observer=observe)
    app = FastAPI()
    app.include_router(api.router)
    app.include_router(build_interaction_routes(api, router))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        tid = (await t._make_task(ac, scope=[f"https://{t.DOMAIN}/docs/"]))["task_id"]
        r = await ac.post("/v1/browser/interaction/step", headers=t.HEADERS, json={
            "task_id": tid, "action_class_ceiling": "A2",
            "deterministic_action": {"operation": "click", "locator": "#b"},
            "postcondition": {"kind": "READ_BACK", "field": "title", "expected": "/docs/delay6000"}})
        profile = await store.fetchone("SELECT lease_holder FROM browser_profiles WHERE profile_alias = ?", ("public_research",))
    assert r.status_code == 200, r.text
    assert len(calls) == 1 and calls[0]["holder_id"] == tid
    assert profile["lease_holder"] is None
    assert rig.session.js("location.href") == "about:blank"
    time.sleep(LATE_WRITE_WAIT_SECONDS)
    assert rig.server.writes() == []


async def test_a_write_blocked_between_steps_of_a_held_lease_goes_to_the_owner_at_the_next_step(g, tmp_path):
    """The task holds its lease across steps. Step 1's page writes 2.5 s after the step
    returned: the lease's guard fails it and freezes the page. Step 2 learns of it on its first
    Harness call and the task goes to the owner with the closed code."""
    module, rig, harness, _b = g
    rig.session.goto(f"https://{t.DOMAIN}/docs/delay2500")
    rig.server.log.clear()
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from conftest_automation import make_store
    from van_gateway.attention.engine import AttentionEngine
    from van_gateway.browser.api import BrowserApi
    from van_gateway.browser.interaction_router import build_interaction_routes
    from van_gateway.config import get_settings
    from van_gateway.decisions.service import DecisionService

    store = await make_store(tmp_path)
    api = BrowserApi(store, get_settings(), worker=t._ScriptedWorker([]),
                     decisions=DecisionService(store, AttentionEngine(store)), verifier=t._Verdict())
    api.broker.page_release_hook = harness.release_page
    router = tr.make_router(executor=HarnessActionExecutor(harness), target_resolver=HarnessTargetResolver(harness),
                            jev_client=None, semantic_fallback=tr.FakeStagehand(None))
    app = FastAPI()
    app.include_router(api.router)
    app.include_router(build_interaction_routes(api, router))
    step = {"action_class_ceiling": "A2", "deterministic_action": {"operation": "click", "locator": "#b"},
            "postcondition": {"kind": "READ_BACK", "field": "title", "expected": "/docs/delay2500"}}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        tid = (await t._make_task(ac, scope=[f"https://{t.DOMAIN}/docs/"]))["task_id"]
        held = await ac.post("/v1/browser/leases", headers=t.HEADERS, json={"profile_alias": "public_research", "task_id": tid})
        first = await ac.post("/v1/browser/interaction/step", headers=t.HEADERS, json={"task_id": tid, **step})
        time.sleep(4.0)
        second = await ac.post("/v1/browser/interaction/step", headers=t.HEADERS, json={"task_id": tid, **step})
        task = (await ac.get(f"/v1/browser/tasks/{tid}", headers=t.HEADERS)).json()["task"]
    assert held.status_code == 200, held.text
    assert first.json()["state"] != "OWNER_TAKEOVER", first.json()
    assert second.json()["state"] == "OWNER_TAKEOVER", second.json()
    assert "HARNESS_REFUSED:NETWORK_WRITE_BLOCKED:POST" in second.json()["reasons"], second.json()["reasons"]
    assert (task["status"], task["error_code"]) == ("WAITING_FOR_OWNER", "OWNER_TAKEOVER:NETWORK_WRITE_BLOCKED:POST")
    time.sleep(LATE_WRITE_WAIT_SECONDS - 4.0)
    assert rig.server.writes() == []


def test_release_is_fenced(g):
    """A stale generation cannot end a newer lease's guard."""
    import httpx

    module, rig, _h, base = g
    envelope = {"mode": "PRODUCTION_ACTUATOR", "allow_helper_authoring": False, "profile_alias": "public_research"}
    assert httpx.post(f"{base}/release", json={**envelope, "lease_generation": 5, "lease_holder_id": "a"}, timeout=30).status_code == 200
    stale = httpx.post(f"{base}/release", json={**envelope, "lease_generation": 4, "lease_holder_id": "b"}, timeout=30)
    assert (stale.status_code, stale.json()["error"]) == (409, "LEASE_GENERATION_STALE")
    missing = httpx.post(f"{base}/release", json=envelope, timeout=30)
    assert (missing.status_code, missing.json()["error"]) == (428, "LEASE_FENCE_REQUIRED")


def test_the_mutating_flag_is_not_granted_by_a_read():
    """The unit's own guard policy: a read carrying a forged mutating flag cannot turn the lease
    mutating (under a key the MAC is checked; without one the flag is never honoured)."""
    module = he._load(pytest.MonkeyPatch(), pathlib.Path(tempfile.mkdtemp()))
    assert module.network_guard_policy({"mutating": True, "task_scope": {"entries": []}}, "a")["mutating"] is False
