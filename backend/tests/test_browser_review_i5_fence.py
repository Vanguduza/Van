"""Review I5 F1, F2, F3 — the Harness lease fence under a deadline, lost state and forgery.

Before (probe review-i5/probes/test_i5_fence.py at fbe5502e):

* F1 — a ``/step`` that hit its deadline released its lease while its click was still at the
  Harness; task2 took generation 2 and the Harness then applied task1's generation-1 click.
* F2 — deleting a profile's fence state file and restarting re-admitted a stale generation.
* F3 — the fence was unauthenticated: any local caller could send ``lease_generation=2**62``
  and lock the real holder out, across restarts.
"""

from __future__ import annotations

import asyncio
import importlib.util
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest

import test_browser_api as t
import test_browser_interaction_router as tr
from test_browser_review_i3 import _app, _bounded, _env, _lease_row  # noqa: F401
from van_gateway.browser import interaction_router as ir
from van_gateway.browser.adapters import (
    BrowserAdapterError,
    HarnessLeaseFence,
    HttpBrowserHarnessAdapter,
    harness_fence_mac,
    harness_lease_fence,
    load_harness_fence_key,
)
from van_gateway.browser.interaction_router import HarnessActionExecutor

H = t.HEADERS
ROOT = Path(__file__).resolve().parents[2]
HARNESS_SERVICE = ROOT / "deploy" / "van-browser-core" / "browser" / "harness_service.py"
KEY = b"k" * 16 + b"0123456789abcdef0123456789abcdef"


def _load(monkeypatch=None, **env):
    if monkeypatch is not None:
        for name, value in env.items():
            monkeypatch.setenv(name, value)
    spec = importlib.util.spec_from_file_location("van_harness_service_i5_fence", HARNESS_SERVICE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Worker:
    """The real Harness HTTP handler; ``restart()`` is a fresh process image on the same state."""

    def __init__(self, state_root: Path, *, click_seconds: float = 0.0, **fence_kw) -> None:
        self.state_root, self.click_seconds, self.fence_kw = state_root, click_seconds, fence_kw
        self.clicks: list[tuple[str, int | None]] = []
        self.events: list[tuple[float, str]] = []
        self.server = None
        self.restart()

    def restart(self) -> None:
        self.stop()
        module = _load()
        module.FENCE = module.LeaseFence(self.state_root, **self.fence_kw)

        def click(body, alias, domain):
            gen = body.get("lease_generation")
            self.events.append((time.monotonic(), f"start:{body['locator']}:{gen}"))
            time.sleep(self.click_seconds)
            self.clicks.append((body["locator"], gen))
            self.events.append((time.monotonic(), f"applied:{body['locator']}:{gen}"))
            return {"ok": True}

        module.OPERATIONS["/click"] = click
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
        r = httpx.post(f"{self.url}{path}", timeout=30, json={
            "mode": "PRODUCTION_ACTUATOR", "allow_helper_authoring": False,
            "profile_alias": "public_research", "target_domain": "docs.example.com", **extra})
        return r.status_code, r.json().get("error")

    def click(self, locator, gen, holder, key=None, **extra):
        if key is not None:
            extra["lease_mac"] = harness_fence_mac(key, "public_research", gen, holder)
            # Unit G11: the worker checks the network guard's effect MAC for every mutating
            # operation itself (it was checked inside the real /click this fake replaces).
            from van_gateway.browser.adapters import harness_effect_mac, harness_scope_digest

            extra.setdefault("effect_mac", harness_effect_mac(key, "public_research", gen, holder, "", False,
                                                              harness_scope_digest(None)))
        return self.post("/click", locator=locator, lease_generation=gen, lease_holder_id=holder, **extra)


@pytest.fixture
def workers():
    made: list[Worker] = []

    def make(state_root, **kw):
        made.append(Worker(state_root, **kw))
        return made[-1]

    yield make
    for w in made:
        w.stop()


# ------------------------------------------------------------------------------- F1


async def _deadline_step(tmp_path, monkeypatch, worker):
    real = ir._step_page_lease

    async def short(browser_api, task):
        acquired, fence, _d = await real(browser_api, task)
        return acquired, fence, 0.5  # the probe's timing: deadline 0.5 s, click 2.0 s

    monkeypatch.setattr(ir, "_step_page_lease", short)
    harness = HttpBrowserHarnessAdapter(None, base_url=worker.url, enabled=True)
    resolver = tr.FakeResolver({"#go": {"locator": "#go", "role": "button", "name": "Next page"}})
    return await _app(tmp_path, executor=HarnessActionExecutor(harness), target_resolver=resolver)


def _step_body(tid):
    return {"task_id": tid, "action_class_ceiling": "A2",
            "deterministic_action": {"operation": "click", "locator": "#go"},
            "postcondition": {"kind": "READ_BACK", "field": "title", "expected": "x"}}


async def test_a_step_past_its_deadline_keeps_its_lease_until_the_click_has_ended(tmp_path, monkeypatch, workers):
    worker = workers(tmp_path / "hs", click_seconds=2.0)
    ac, store, _api, _ = await _deadline_step(tmp_path, monkeypatch, worker)
    async with ac:
        t1 = (await t._make_task(ac))["task_id"]
        t2 = (await t._make_task(ac))["task_id"]
        step = asyncio.create_task(ac.post("/v1/browser/interaction/step", headers=H, json=_step_body(t1)))
        await asyncio.sleep(1.0)  # past the 0.5 s deadline, the click is still at the Harness
        early = await ac.post("/v1/browser/leases", headers=H, json={"profile_alias": "public_research", "task_id": t2})
        r1 = await _bounded(step, 10)
        acquired_at = time.monotonic()
        l2 = await ac.post("/v1/browser/leases", headers=H, json={"profile_alias": "public_research", "task_id": t2})
        row = dict(await _lease_row(store))
    assert (r1.status_code, r1.json()["detail"]) == (504, "BROWSER_STEP_DEADLINE_EXCEEDED")
    # While the click was in flight the profile stayed leased to task1.
    assert early.status_code == 409, early.text
    assert worker.clicks == [("#go", 1)]
    applied_at = next(ts for ts, e in worker.events if e == "applied:#go:1")
    assert applied_at < acquired_at
    assert l2.status_code == 200 and (row["lease_holder_id"], row["lease_generation"]) == (t2, 2)


async def test_a_call_with_no_response_leaves_the_lease_to_expire(tmp_path, monkeypatch):
    """A call that ended without a response may still be applying: the lease is not released."""
    class Dropping(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            raise httpx.ReadTimeout("no response", request=request)

    real = ir._step_page_lease
    monkeypatch.setattr(ir, "_step_page_lease", real)
    harness = HttpBrowserHarnessAdapter(None, base_url="http://harness.test", enabled=True, transport=Dropping())
    resolver = tr.FakeResolver({"#go": {"locator": "#go", "role": "button", "name": "Next page"}})
    ac, store, _api, _ = await _app(tmp_path, executor=HarnessActionExecutor(harness), target_resolver=resolver)
    async with ac:
        t1 = (await t._make_task(ac))["task_id"]
        await _bounded(ac.post("/v1/browser/interaction/step", headers=H, json=_step_body(t1)), 10)
        row = dict(await _lease_row(store))
    assert row["lease_holder_id"] == t1 and row["lease_generation"] == 1


def test_the_harness_applies_the_check_atomically_with_the_operation(tmp_path, workers):
    """Harness side of F1: a newer generation is not admitted while an older one is applying,
    and an older one arriving after the newer is refused."""
    worker = workers(tmp_path / "hs", click_seconds=1.0)
    first: dict = {}
    th = threading.Thread(target=lambda: first.setdefault("r", worker.click("#old", 1, "task-a")))
    th.start()
    time.sleep(0.3)  # gen 1 is applying
    second = worker.click("#new", 2, "task-b")
    th.join(10)
    assert first["r"] == (200, None) and second == (200, None)
    events = [e for _ts, e in worker.events]
    assert events == ["start:#old:1", "applied:#old:1", "start:#new:2", "applied:#new:2"], events
    assert worker.click("#old-again", 1, "task-a") == (409, "LEASE_GENERATION_STALE")


# ------------------------------------------------------------------------------- F2


def test_a_missing_state_file_for_a_fenced_profile_refuses_after_restart(tmp_path, workers):
    worker = workers(tmp_path / "hs")
    assert worker.click("#b1", 5, "task-b") == (200, None)
    assert worker.click("#a", 4, "task-a") == (409, "LEASE_GENERATION_STALE")
    (worker.state_root / "lease-fence-public_research.json").unlink()
    worker.restart()
    assert worker.click("#a-stale", 4, "task-a") == (503, "LEASE_FENCE_STATE_MISSING")
    assert worker.click("#b2", 6, "task-b") == (503, "LEASE_FENCE_STATE_MISSING")
    assert [c for c, _g in worker.clicks] == ["#b1"]


def test_a_lost_manifest_refuses_while_the_install_marker_exists(tmp_path, workers):
    marker = tmp_path / "harness-fence-installed"
    marker.write_text("2026-09-30T00:00:00Z\n")
    state = tmp_path / "hs"
    state.mkdir()
    (state / "lease-fence-manifest.json").write_text('{"schema_version":1,"aliases":[]}')
    worker = workers(state, install_marker=marker)
    # First boot after bootstrap: an empty manifest admits.
    assert worker.click("#first", 1, "task-a") == (200, None)
    for f in state.iterdir():
        f.unlink()  # the whole state directory is lost
    worker.restart()
    assert worker.click("#stale", 1, "task-a") == (503, "LEASE_FENCE_STATE_MISSING")
    assert worker.click("#other", 1, "task-z", profile_alias="owner_research") == (503, "LEASE_FENCE_STATE_MISSING")


def test_first_boot_without_a_marker_admits_and_starts_the_manifest(tmp_path, workers):
    worker = workers(tmp_path / "hs", install_marker=tmp_path / "absent-marker")
    assert worker.click("#one", 1, "task-a") == (200, None)
    import json

    assert json.loads((worker.state_root / "lease-fence-manifest.json").read_text())["aliases"] == ["public_research"]


# ------------------------------------------------------------------------------- F3


def test_a_keyed_harness_refuses_a_forged_fence_and_keeps_the_real_holder(tmp_path, workers):
    worker = workers(tmp_path / "hs", key=KEY)
    assert worker.click("#x", 2**62, "nobody") == (403, "LEASE_FENCE_MAC_INVALID")
    assert worker.click("#x", 2**62, "nobody", lease_mac="0" * 64) == (403, "LEASE_FENCE_MAC_INVALID")
    # A MAC for one generation does not cover another.
    mac2 = harness_fence_mac(KEY, "public_research", 2, "task-real")
    assert worker.click("#x", 2**62, "task-real", lease_mac=mac2) == (403, "LEASE_FENCE_MAC_INVALID")
    # A different key is a forgery too.
    assert worker.click("#x", 2**62, "nobody", key=b"z" * 32) == (403, "LEASE_FENCE_MAC_INVALID")
    assert worker.click("#real", 2, "task-real", key=KEY) == (200, None)
    worker.restart()
    assert worker.click("#real", 3, "task-real", key=KEY) == (200, None)
    assert [c for c, _g in worker.clicks] == ["#real", "#real"]


def test_a_harness_that_requires_a_mac_without_a_key_fails_closed(tmp_path, workers):
    worker = workers(tmp_path / "hs", require_mac=True)
    assert worker.click("#x", 1, "task-a", key=KEY) == (503, "LEASE_FENCE_KEY_UNCONFIGURED")
    assert worker.post("/page_info")[0] == 200  # unfenced reads carry no fence to verify
    assert worker.clicks == []


def test_the_production_worker_requires_its_key(tmp_path, monkeypatch):
    monkeypatch.setenv("VAN_HARNESS_STATE_ROOT", str(tmp_path / "hs"))
    monkeypatch.setenv("VAN_TRUST_ZONE", "van-browser-core")
    monkeypatch.delenv("VAN_HARNESS_FENCE_KEY_FILE", raising=False)
    module = _load()
    with pytest.raises(module.WorkerError) as refused:
        module.FENCE.check("public_research", {"lease_generation": 1, "lease_holder_id": "a"})
    assert refused.value.code == "LEASE_FENCE_KEY_UNCONFIGURED"
    with pytest.raises(SystemExit):
        module.main()
    # A configured but short key is refused as well; a good key file is used.
    short = tmp_path / "short.key"
    short.write_bytes(b"abc")
    monkeypatch.setenv("VAN_HARNESS_FENCE_KEY_FILE", str(short))
    with pytest.raises(SystemExit):
        _load().main()
    good = tmp_path / "fence.key"
    good.write_bytes(KEY + b"\n")
    monkeypatch.setenv("VAN_HARNESS_FENCE_KEY_FILE", str(good))
    module = _load()
    body = {"lease_generation": 1, "lease_holder_id": "a",
            "lease_mac": module.fence_mac(KEY, "public_research", 1, "a")}
    module.FENCE.check("public_research", body)


async def test_the_gateway_adapter_macs_the_fence_it_sends(tmp_path, workers):
    worker = workers(tmp_path / "hs", key=KEY)
    key_file = tmp_path / "gw-fence.key"
    key_file.write_bytes(KEY + b"\n")
    keyed = HttpBrowserHarnessAdapter(None, base_url=worker.url, enabled=True, fence_key=load_harness_fence_key(str(key_file)))
    unkeyed = HttpBrowserHarnessAdapter(None, base_url=worker.url, enabled=True)
    task = tr._task().model_copy(update={"profile_alias": "public_research", "target_domain": "docs.example.com"})
    with harness_lease_fence(HarnessLeaseFence("public_research", "task-a", 7)):
        await keyed.click(task, "#ok")
        with pytest.raises(BrowserAdapterError) as refused:
            await unkeyed.click(task, "#forged")
    assert refused.value.code == "BROWSER_HARNESS_REQUEST_FAILED" and refused.value.detail == "403"
    assert [c for c, _g in worker.clicks] == ["#ok"]
    with pytest.raises(ValueError):
        short = tmp_path / "short"
        short.write_bytes(b"x" * 8)
        load_harness_fence_key(str(short))
