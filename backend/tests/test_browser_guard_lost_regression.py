"""Unit G15 (review I8 MAJOR-1) — a page cannot switch the lease's network guard off.

Review I8 measured it: a click handler that keeps the renderer busy for 20 s makes the guard
thread's adopt (``Page.getFrameTree``) time out. The adopt then removed interception, the tick
(which does not require a guard) swallowed the refusal, ``GuardLease.absorb(None)`` cleared the
lease's state without recording anything, and the next tick started a fresh guard that had
never acted. The page's POST after the busy loop then reached the server for a task admitted
as mutating, and for a read-only task the proxy refused it but the owner was never told
(``release=ENDED/None``).

Now a lost guard breaks the lease: NETWORK_GUARD_UNAVAILABLE on its next call and in its
``/release`` answer, the page frozen, the egress policy revoked for good, and no guard started
later in the lease forgets that the task acted.

The busy-renderer cases drive the real Harness worker handler, the real egress proxy and
Chromium (``test_browser_egress_proxy.EgressRig``). The instrument is the fixture HTTPS
server's own request log, outside the browser and the proxy.
"""
from __future__ import annotations

import importlib.util
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

import cdp_harness_kit as kit
import test_browser_egress_proxy as ep
import test_browser_interaction_router as tr
import test_harness_elements as he
from test_browser_api import _settings  # noqa: F401 - the API settings the gateway adapter's router needs
from van_gateway.browser.adapters import HarnessLeaseFence, HttpBrowserHarnessAdapter, harness_lease_fence
from van_gateway.browser.interaction_router import DeterministicAction, HarnessActionExecutor, HarnessTargetResolver
from van_gateway.browser.task_scope import scope_for_new_task

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "deploy/van-browser-core/browser/harness_service.py"
OWNER_CODES = ("NETWORK_WRITE_BLOCKED", "NETWORK_WRITE_DETECTED", "NETWORK_GUARD_")

chromium = pytest.mark.skipif(
    not kit.chromium_available() or not Path("/usr/bin/openssl").is_file(),
    reason="needs the pinned Chromium and openssl",
)

#: Review I8's page: 1.5 s after the click the handler spins the renderer for BUSY ms, then
#: writes. The click first requests an out-of-scope marker host (a GET: the guard lets it pass,
#: the proxy refuses it and logs the host), so the proxy's log shows the handler ran. (A marker
#: after the busy loop is no instrument: the freeze cancels it with the write.)
BUSY_PAGE = ("<button id=\"b\" onclick=\"new Image().src='https://ran-busy.marker.example.org/m';"
             "setTimeout(()=>{const t=Date.now();while(Date.now()-t<__BUSY__){};"
             "fetch('__WRITE__',{method:'POST',body:'after-busy'})},1500)\">Next</button>")
PAGES: dict[str, str] = {}


def _pages(host: str, path: str) -> Any:
    if host.startswith(("evil", "ran-")):
        return None
    page = PAGES.get(path)
    if page is None:
        return None
    return f"<!doctype html><html><head><title>{path}</title></head><body>{page}</body></html>"


@pytest.fixture
def g(monkeypatch, tmp_path):
    monkeypatch.setattr(ep, "_pages", _pages)
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
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        yield module, rig, session, HttpBrowserHarnessAdapter(None, base_url=base, enabled=True, fence_key=ep.KEY)
    finally:
        module.NET_GUARDS.close()
        server.shutdown()
        server.server_close()
        rig.close()


@chromium
@pytest.mark.parametrize(("busy_ms", "mutating"), [(3000, False), (20000, False), (20000, True)],
                         ids=["control-3s-read-only", "busy-20s-read-only", "busy-20s-mutating"])
async def test_a_busy_renderer_cannot_make_the_lease_guard_forget_the_click(g, monkeypatch, busy_ms, mutating):
    module, rig, session, harness = g
    broken: list[Any] = []
    absorb = module.GuardLease.absorb

    def spy(self, guard, **kw):
        if isinstance(guard, dict) and guard.get("broken"):
            broken.append(guard["broken"])
        elif guard is None:
            broken.append("NO_GUARD_HANDED_BACK")
        return absorb(self, guard, **kw)

    monkeypatch.setattr(module.GuardLease, "absorb", spy)
    write = "/docs/pay" if mutating else "/api/pay"  # mutating: inside the scope, so only the window stops it
    PAGES["/docs/busy"] = BUSY_PAGE.replace("__BUSY__", str(busy_ms)).replace("__WRITE__", write)
    scope = scope_for_new_task(he.DOMAIN, [f"https://{he.DOMAIN}/docs/"])
    task = he._task().model_copy(update={"scope": scope, "mutating": mutating})
    with harness_lease_fence(HarnessLeaseFence(task.profile_alias, task.task_id, 1)):
        await harness.page_info(task)
        await harness.navigate(task, f"https://{he.DOMAIN}/docs/busy")
    rig.clear()
    router = tr.make_router(target_resolver=HarnessTargetResolver(harness), executor=HarnessActionExecutor(harness),
                            semantic_fallback=tr.FakeStagehand(None), jev_client=None)
    step = tr.step(deterministic_action=DeterministicAction(operation="click", locator="#b", value_ref=None))
    step.task = task
    with harness_lease_fence(HarnessLeaseFence(task.profile_alias, task.task_id, 1)):
        await router.route(step)
    first = module.NET_GUARDS.leases.get("public_research")
    acted: list[Any] = []
    deadline = time.monotonic() + busy_ms / 1000 + 12
    while time.monotonic() < deadline:
        lease = module.NET_GUARDS.leases.get("public_research")
        acted.append((lease is first, (lease.state or {}).get("acted") if lease else None, lease.acted if lease else None))
        time.sleep(0.5)
    lease = module.NET_GUARDS.leases.get("public_research")
    pending = lease.pending if lease else None
    # The page was frozen before the release (the freeze is retried until it lands).
    frame_url = session.cdp("Page.getFrameTree")["frameTree"]["frame"]["url"]
    report = await harness.release_page(profile_alias=task.profile_alias, holder_id=task.task_id, generation=1)
    time.sleep(1.0)
    writes = [e for e in rig.server_log() if e[0] not in kit.READ_METHODS or "pay" in e[2]]
    ran = any(d["origin"].startswith("ran-busy") for d in rig.decision_log())
    print(f"\nG15BUSY busy_ms={busy_ms} mutating={mutating} ran={ran} writes={writes} pending={pending} "
          f"release={report.get('guard')}/{report.get('blocked')} broken_seen={sorted(set(broken))} frame={frame_url} "
          f"acted_samples={sorted(set(map(str, acted)))}")
    # The instrument saw the click reach the page's handler.
    assert ran, "the page's handler never ran: the case measured nothing"
    # Nothing the page wrote reached the server.
    assert writes == []
    assert frame_url == "about:blank"
    # The lease never lost the click: one guard lease throughout, never a state with acted=False.
    assert all(same and state_acted is not False and lease_acted for same, state_acted, lease_acted in acted)
    # The owner is told, by the release answer (the gateway routes it to WAITING_FOR_OWNER).
    assert isinstance(report.get("blocked"), str) and report["blocked"].startswith(OWNER_CODES)
    if busy_ms > 15000:
        # The trigger happened: a script could not adopt the guard (the 15 s CDP timeout) and
        # handed it back broken — never nothing (review I8: absorb(None), then a fresh guard).
        assert "NETWORK_GUARD_UNAVAILABLE" in broken and "NO_GUARD_HANDED_BACK" not in broken
        # The lease is broken; its first code is the write the freeze caught after the busy
        # loop, or NETWORK_GUARD_UNAVAILABLE when the loop outlasted that script.
        assert pending in ("NETWORK_GUARD_UNAVAILABLE", "NETWORK_WRITE_BLOCKED:POST")
        assert report["blocked"] == pending
    else:
        assert broken == [] and report["blocked"] == "NETWORK_WRITE_BLOCKED:POST"


def _spy_absorb(module, monkeypatch) -> list[Any]:
    seen: list[Any] = []
    absorb = module.GuardLease.absorb

    def spy(self, guard, **kw):
        seen.append(guard.get("broken") if isinstance(guard, dict) else "NO_GUARD_HANDED_BACK")
        return absorb(self, guard, **kw)

    monkeypatch.setattr(module.GuardLease, "absorb", spy)
    return seen


@chromium
async def test_a_navigation_started_outside_the_page_between_calls_keeps_its_guard(g, monkeypatch):
    """Found while fixing MAJOR-1 (test_browser_review_i5_task_scope's focus case, whose
    fixture navigates with Playwright between two Harness calls): a main-frame document
    request the guard has paused, for a navigation started over CDP (Page.navigate), holds
    Page.getFrameTree until it is answered, and the adopt read the frame tree before answering
    anything — a 15 s timeout. Before G15 the guard was then silently dropped (review I8's
    path); with the lost-guard rule alone the lease would break. The adopt now answers paused
    requests while it reads the frame tree: the navigation is served and the guard kept. (A
    navigation the page starts itself, location.href, never held the frame tree: the next case.)"""
    module, rig, session, harness = g
    seen = _spy_absorb(module, monkeypatch)
    PAGES["/docs/start"] = "<p>start</p>"
    PAGES["/docs/landed"] = "<p id='l'>landed</p>"
    scope = scope_for_new_task(he.DOMAIN, [f"https://{he.DOMAIN}/docs/"])
    task = he._task().model_copy(update={"scope": scope, "mutating": False})
    with harness_lease_fence(HarnessLeaseFence(task.profile_alias, task.task_id, 1)):
        await harness.page_info(task)
        await harness.navigate(task, f"https://{he.DOMAIN}/docs/start")
    first = module.NET_GUARDS.leases.get("public_research")
    # Another CDP client navigates the page while the lease is idle (the guard thread ticking).
    threading.Thread(target=lambda: session.send("Page.navigate", {"url": f"https://{he.DOMAIN}/docs/landed"},
                                                 session_id=session.session, timeout=30), daemon=True).start()
    time.sleep(18.0)  # longer than one CDP timeout: a deadlocked adopt would have failed by now
    lease = module.NET_GUARDS.leases.get("public_research")
    state = dict(lease.state or {}) if lease else {}
    frame_url = session.cdp("Page.getFrameTree")["frameTree"]["frame"]["url"]
    report = await harness.release_page(profile_alias=task.profile_alias, holder_id=task.task_id, generation=1)
    print(f"\nG15OUTSIDENAV frame={frame_url} same_lease={lease is first} pending={lease.pending if lease else None} "
          f"absorbed_broken={sorted(set(map(str, seen)))} release={report.get('blocked')}")
    assert lease is first and lease.pending is None and state.get("main_frame")
    assert set(seen) == {None}
    assert frame_url.endswith("/docs/landed")
    assert report.get("blocked") is None


@chromium
async def test_a_freeze_that_did_not_land_is_retried(g, monkeypatch):
    """A freeze whose navigation to about:blank did not land (the renderer did not answer)
    is tried again by the lease's next script, until the page is on about:blank."""
    module, rig, session, harness = g
    PAGES["/docs/write_now"] = "<button id=\"b\" onclick=\"fetch('/api/pay',{method:'POST',body:'x'})\">Next</button>"
    scope = scope_for_new_task(he.DOMAIN, [f"https://{he.DOMAIN}/docs/"])
    task = he._task().model_copy(update={"scope": scope, "mutating": False})
    with harness_lease_fence(HarnessLeaseFence(task.profile_alias, task.task_id, 1)):
        await harness.page_info(task)
        await harness.navigate(task, f"https://{he.DOMAIN}/docs/write_now")
    failed: list[str] = []

    def fail_once(params):
        if params.get("url") == "about:blank" and not failed:
            failed.append(params["url"])
            raise RuntimeError("renderer did not answer")

    session.fail["Page.navigate"] = fail_once
    router = tr.make_router(target_resolver=HarnessTargetResolver(harness), executor=HarnessActionExecutor(harness),
                            semantic_fallback=tr.FakeStagehand(None), jev_client=None)
    step = tr.step(deterministic_action=DeterministicAction(operation="click", locator="#b", value_ref=None))
    step.task = task
    with harness_lease_fence(HarnessLeaseFence(task.profile_alias, task.task_id, 1)):
        await router.route(step)
    lease = module.NET_GUARDS.leases.get("public_research")
    time.sleep(3.0)  # the guard thread's next ticks
    frame_url = session.cdp("Page.getFrameTree")["frameTree"]["frame"]["url"]
    state = dict(lease.state or {})
    report = await harness.release_page(profile_alias=task.profile_alias, holder_id=task.task_id, generation=1)
    writes = [e for e in rig.server_log() if e[0] not in kit.READ_METHODS or "pay" in e[2]]
    print(f"\nG15FREEZE failed_first={failed} frame={frame_url} state_frozen={state.get('frozen')} "
          f"blanked={state.get('blanked')} release={report.get('blocked')} writes={writes}")
    assert failed == ["about:blank"]  # the first freeze's navigation was refused
    assert frame_url == "about:blank" and state.get("blanked") is True
    assert report.get("blocked") == "NETWORK_WRITE_BLOCKED:POST" and writes == []


@chromium
async def test_a_page_that_navigates_itself_between_calls_keeps_its_guard(g, monkeypatch):
    """Control: a navigation the page starts itself between two calls is served and the guard
    kept (it never held Page.getFrameTree; measured with the frame read first as well)."""
    module, rig, session, harness = g
    seen = _spy_absorb(module, monkeypatch)
    PAGES["/docs/selfnav"] = "<p>x</p><script>setTimeout(()=>{location.href='/docs/landed'},1500)</script>"
    PAGES["/docs/landed"] = "<p id='l'>landed</p>"
    scope = scope_for_new_task(he.DOMAIN, [f"https://{he.DOMAIN}/docs/"])
    task = he._task().model_copy(update={"scope": scope, "mutating": False})
    with harness_lease_fence(HarnessLeaseFence(task.profile_alias, task.task_id, 1)):
        await harness.page_info(task)
        await harness.navigate(task, f"https://{he.DOMAIN}/docs/selfnav")
    first = module.NET_GUARDS.leases.get("public_research")
    time.sleep(18.0)  # longer than one CDP timeout: a deadlocked adopt would have failed by now
    lease = module.NET_GUARDS.leases.get("public_research")
    state = dict(lease.state or {}) if lease else {}
    frame_url = session.cdp("Page.getFrameTree")["frameTree"]["frame"]["url"]
    with harness_lease_fence(HarnessLeaseFence(task.profile_alias, task.task_id, 1)):
        info = await harness.page_info(task)
    report = await harness.release_page(profile_alias=task.profile_alias, holder_id=task.task_id, generation=1)
    print(f"\nG15SELFNAV frame={frame_url} page_info={info.get('url')} same_lease={lease is first} "
          f"pending={lease.pending if lease else None} absorbed_broken={sorted(set(map(str, seen)))} release={report.get('blocked')}")
    assert lease is first and lease.pending is None and state.get("main_frame")
    assert set(seen) == {None}
    assert frame_url.endswith("/docs/landed") and str(info.get("url", "")).endswith("/docs/landed")
    assert report.get("blocked") is None


# ------------------------------------------------------------------ the worker's lease record


@pytest.fixture
def hs(monkeypatch, tmp_path):
    """The worker module with a scripted browser: no Chromium, no proxy (revocation is a no-op
    without VAN_BROWSER_EGRESS_CONTROL_SOCKET; ``revoked`` records each call)."""
    for name in ("VAN_BROWSER_EGRESS_CONTROL_SOCKET", "VAN_TRUST_ZONE", "VAN_HARNESS_FENCE_KEY_FILE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("VAN_HARNESS_STATE_ROOT", str(tmp_path / "state"))
    spec = importlib.util.spec_from_file_location("van_harness_g15", HARNESS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    revoked: list[tuple] = []
    monkeypatch.setattr(module, "revoke_egress_policy",
                        lambda alias, generation, holder, *, final: revoked.append((alias, generation, holder, final)))
    module.revoked = revoked
    # The guard thread is started only where a case drives it (it would consume scripted answers).
    module.NET_GUARDS._ensure_thread = lambda: None
    yield module
    module.NET_GUARDS.close()


STATE = {"browser_sid": "b", "main_frame": "m", "children": {}, "form_frames": [], "acted": True, "frozen": False,
         "blanked": False, "doc_url": "https://docs.example.com/docs/x"}


def _guard(state=STATE, **kw):
    return {"state": state, "blocked": [], "detected": [], "dropped": [], "broken": None, "acted": True,
            "frozen": False, **kw}


def test_a_lease_whose_guard_hands_back_nothing_mid_lease_is_broken_not_restarted(hs, monkeypatch):
    envs: list[dict] = []
    answers = [{"ok": 1, "__guard__": _guard()}, {"serviced": False}, {"ok": 1, "__guard__": _guard()}]

    def run_harness(alias, script, extra=None):
        envs.append(dict(extra or {}))
        return answers.pop(0)

    monkeypatch.setattr(hs, "run_harness", run_harness)
    lease = hs.NET_GUARDS.bind("a", {"lease_generation": 1, "lease_holder_id": "h", "task_id": "t"})
    with hs.NET_GUARDS.using(lease):
        hs._run("a", "print(1)", required=True)
        assert lease.acted and lease.started and lease.pending is None
        hs._run("a", hs.GUARD_WRAPPER_TICK, role="tick")  # the tick's guard was lost: no __guard__
    assert lease.pending == "NETWORK_GUARD_UNAVAILABLE"
    assert ("a", 1, "h", True) in hs.revoked  # the egress policy is revoked for good
    with hs.NET_GUARDS.using(lease):
        hs._run("a", "print(1)")
    # The next script's guard is told the lease acted and has a code pending (it freezes at once).
    policy = __import__("json").loads(envs[-1]["VAN_BH_NETGUARD"])
    assert policy["acted"] is True and policy["pending"] is True and policy["midlease"] is True
    # The code stays pending whatever the later scripts report.
    assert lease.pending == "NETWORK_GUARD_UNAVAILABLE"


def test_a_guard_handed_back_broken_by_the_tick_is_recorded(hs, monkeypatch):
    monkeypatch.setattr(hs, "run_harness", lambda *a, **k: {"serviced": False, "__guard__": _guard(
        broken="NETWORK_GUARD_UNAVAILABLE", frozen=True)})
    lease = hs.NET_GUARDS.bind("a", {"lease_generation": 1, "lease_holder_id": "h", "task_id": "t"})
    with hs.NET_GUARDS.using(lease):
        hs._run("a", hs.GUARD_WRAPPER_TICK, role="tick")
    assert lease.pending == "NETWORK_GUARD_UNAVAILABLE" and lease.frozen
    assert ("a", 1, "h", True) in hs.revoked


def test_a_lease_the_guard_thread_gave_up_on_is_reported_at_release_and_resumed_not_replaced(hs, monkeypatch):
    lease = hs.NET_GUARDS.bind("a", {"lease_generation": 3, "lease_holder_id": "h", "task_id": "t"})
    lease.acted, lease.started = True, True

    def boom(*a, **k):
        raise hs.WorkerError("BROWSER_HARNESS_REQUEST_FAILED", 502)

    monkeypatch.setattr(hs, "run_harness", boom)
    monkeypatch.setattr(hs, "NETGUARD_TICK_FAILURE_LIMIT", 2)
    monkeypatch.setattr(hs, "NETGUARD_TICK_PAUSE_SECONDS", 0.01)
    type(hs.NET_GUARDS)._ensure_thread(hs.NET_GUARDS)
    deadline = time.monotonic() + 5
    while "a" in hs.NET_GUARDS.leases and time.monotonic() < deadline:
        time.sleep(0.02)
    assert "a" not in hs.NET_GUARDS.leases
    assert lease.pending == "NETWORK_GUARD_UNAVAILABLE"
    # The same lease calls again: the retired record is resumed (acted, pending), never a fresh one.
    again = hs.NET_GUARDS.bind("a", {"lease_generation": 3, "lease_holder_id": "h", "task_id": "t"})
    assert again is lease and again.acted and again.pending == "NETWORK_GUARD_UNAVAILABLE"
    with hs.NET_GUARDS.lock:
        del hs.NET_GUARDS.leases["a"]
    hs.NET_GUARDS._retire("a", lease)
    # Its release reports the code (the END script cannot run: the browser went away).
    report = hs.NET_GUARDS.release("a", {"lease_generation": 3, "lease_holder_id": "h"})
    assert report["blocked"] == "NETWORK_GUARD_UNAVAILABLE" and report["guard"] == "ENDED"
    assert hs.NET_GUARDS.retired.get("a", {}) == {}


def test_a_retired_lease_released_under_a_newer_lease_does_not_freeze_the_newer_page(hs, monkeypatch):
    calls: list[str] = []

    def run_harness(alias, script, extra=None):
        calls.append(__import__("json").loads((extra or {}).get("VAN_BH_NETGUARD", "{}")).get("role", "raw"))
        return {"ended": True, "__guard__": _guard(state=None, frozen=True)}

    monkeypatch.setattr(hs, "run_harness", run_harness)
    old = hs.NET_GUARDS.bind("a", {"lease_generation": 1, "lease_holder_id": "h1", "task_id": "t"})
    old.pending = "NETWORK_WRITE_BLOCKED:POST"
    hs.NET_GUARDS.bind("a", {"lease_generation": 2, "lease_holder_id": "h2", "task_id": "t2"})  # ends lease 1
    ends = calls.count("end")
    report = hs.NET_GUARDS.release("a", {"lease_generation": 1, "lease_holder_id": "h1"})
    assert report["blocked"] == "NETWORK_WRITE_BLOCKED:POST"
    assert calls.count("end") == ends  # lease 2's page was not frozen by lease 1's release
    assert hs.NET_GUARDS.leases["a"].generation == 2


def test_the_in_script_guard_carries_acted_and_pending_into_a_fresh_start(hs):
    ns: dict[str, Any] = {}
    exec(compile(hs.VAN_HELPERS_PY + "\nclass _VanRefused(Exception):\n    pass\n" + hs.NETWORK_GUARD_PY, "<g>", "exec"), ns)  # noqa: S102
    fresh = ns["_VanNetGuard"]({"mutating": False, "scope": {}})
    assert fresh.acted is False and fresh.freeze_due is False
    carried = ns["_VanNetGuard"]({"mutating": False, "scope": {}, "acted": True, "pending": True})
    assert carried.acted is True and carried.freeze_due is True
    # A read-only task's write after the carried click is the owner's, not dropped background.
    carried._record("POST")
    assert carried.blocked == ["POST"] and carried.dropped == []
