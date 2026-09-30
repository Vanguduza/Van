"""Review I5 + owner decision 2026-09-30 — task-truth scope and the target actually acted on.

Every Chromium case routes one step through the real router (HarnessTargetResolver +
HarnessActionExecutor) over the real Harness HTTP handler driving headless Chromium on the
local fixtures in ``fixtures/review_i5``, and records what the *page* saw: ``money:*`` when a
money/commitment control's handler ran, ``submit:*`` for a form submission, ``benign:*``
for the benign controls. A money control must never fire; the benign ones must still run.

Part 1 — the scope rule (``browser/task_scope.py``): an action runs at the task's admitted
class only when the page (origin, and path where the task declares one) and any link/submit
destination are inside the scope recorded with the task, and the target is the node the
Harness bound. A task with no scope fails closed. Part 2 — review I5 MAJOR-1..6.
"""

from __future__ import annotations

import json
import pathlib
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

import test_browser_api as t
from test_browser_api import _settings  # noqa: F401 - autouse: the API settings the routes need
import test_browser_interaction_router as tr
import test_harness_elements as he
from van_gateway.browser.action_risk import assess_action, assess_key_press, risk_stem_hits
from van_gateway.browser.adapters import (
    BrowserAdapterError,
    HarnessLeaseFence,
    HttpBrowserHarnessAdapter,
    harness_lease_fence,
)
from van_gateway.browser.interaction_router import (
    DeterministicAction,
    HarnessActionExecutor,
    HarnessTargetResolver,
    RouterAction,
    RouterLane,
    StepState,
)
from van_gateway.browser.task_scope import (
    TaskScope,
    load_scope,
    scope_for_new_task,
    task_scope_gate,
    url_scope_violation,
)

DOMAIN = he.DOMAIN
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "review_i5"
LOG = """<script>
window.__van = [];
window.money = (w) => { (window.parent !== window ? window.parent : window).__van.push('money:' + w); };
document.addEventListener('submit', (e) => { window.__van.push('submit:' + e.target.getAttribute('action')); e.preventDefault(); }, true);
document.addEventListener('click', (e) => { const a = e.composedPath()[0].closest && e.composedPath()[0].closest('a[href]'); if (a) { window.__van.push('nav:' + a.getAttribute('href')); e.preventDefault(); } }, true);
</script>"""


# ------------------------------------------------------------------ real Chromium fixture


class _Pages(he._PlaywrightPage):
    """Headless Chromium serving ``fixtures/review_i5/<name>.html`` at /i5/<name>."""

    def _run(self, executable: str) -> None:
        from playwright.sync_api import sync_playwright

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path=executable)
                page = browser.new_page()

                def serve(route):
                    path = "/" + route.request.url.split("/", 3)[-1].split("?")[0]
                    name = path.rsplit("/", 1)[-1]
                    file = FIXTURES / f"{name}.html"
                    if not path.startswith("/i5/") or not file.is_file():
                        route.fulfill(status=404, body="missing")
                        return
                    body = file.read_text(encoding="utf-8")
                    head = "" if name == "payframe" else LOG
                    route.fulfill(status=200, content_type="text/html",
                                  body=f"<!doctype html><html><head><title>{name}</title>{head}</head><body>{body}</body></html>")

                page.route(f"https://{DOMAIN}/**", serve)
                cdp = page.context.new_cdp_session(page)
                self.page, self.cdp = page, cdp
                self.ready.set()
                while True:
                    job = self.jobs.get()
                    if job is None:
                        break
                    fn, box, done = job
                    try:
                        box["value"] = fn(page, cdp)
                    except BaseException as exc:  # noqa: BLE001 - handed back to the caller
                        box["error"] = exc
                    done.set()
                browser.close()
        except BaseException as exc:  # noqa: BLE001
            self.error = exc
            self.ready.set()


@pytest.fixture
def chromium(monkeypatch, tmp_path):
    executable = he._chromium()
    if executable is None:
        pytest.skip("no Chromium/Playwright available")
    module = he._load(monkeypatch, tmp_path)
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    (secrets / "q").write_text("install guide", encoding="utf-8")
    monkeypatch.setattr(module, "SECRET_ROOT", secrets)
    pw = _Pages(executable)

    def run_harness(alias, script, extra=None):
        def job(page, cdp):
            return he._exec_script(script, {
                "page_info": lambda: {"url": page.url, "title": page.title()},
                "js": lambda expression: page.evaluate(expression),
                "cdp": lambda method, **params: cdp.send(method, params),
                "click_at_xy": lambda x, y: page.mouse.click(x, y),
                "press_key": lambda key: page.keyboard.press(key),
            }, extra)
        return pw.call(job)

    monkeypatch.setattr(module, "run_harness", run_harness)
    server = ThreadingHTTPServer(("127.0.0.1", 0), module.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield module, pw, HttpBrowserHarnessAdapter(None, base_url=f"http://127.0.0.1:{server.server_address[1]}", enabled=True)
    finally:
        server.shutdown()
        server.server_close()
        pw.close()


def _task(scope: TaskScope | None | str = "ORIGIN"):
    task = he._task()
    if scope == "ORIGIN":
        scope = scope_for_new_task(DOMAIN, None)
    return task.model_copy(update={"scope": scope})


def _goto(pw, path):
    pw.call(lambda page, cdp: page.goto(f"https://{DOMAIN}{path}"))
    pw.call(lambda page, cdp: page.wait_for_timeout(100))


def _seen(pw):
    return pw.call(lambda page, cdp: page.evaluate("window.__van || []"))


async def _route(pw, harness, path, *, task=None, **kw):
    _goto(pw, path)
    router = tr.make_router(target_resolver=HarnessTargetResolver(harness), executor=HarnessActionExecutor(harness),
                            semantic_fallback=kw.pop("stagehand", tr.FakeStagehand(None)), jev_client=None)
    step = tr.step(**kw)
    step.task = task or _task()
    with harness_lease_fence(HarnessLeaseFence("public_research", step.task.task_id, 1)):
        result = await router.route(step)
    return result, _seen(pw)


def _det(op, loc=None, key=None):
    return {"deterministic_action": DeterministicAction(operation=op, locator=loc, value_ref=key)}


def _sh(loc, desc):
    return {"stagehand": tr.FakeStagehand(RouterAction(
        lane=RouterLane.STAGEHAND, operation="click", locator=loc, value_ref=None, action_class=None,
        semantic_action={"method": "click", "description": desc}, description=desc))}


def _lane4(result):
    return result.state in (StepState.OWNER_TAKEOVER, StepState.POLICY_REFUSED)


def _money(seen):
    return [s for s in seen if s.startswith(("money:", "submit:"))]


# ------------------------------------------------------------------ Part 1: the scope rule


def test_scope_rule_origin_path_and_missing_scope():
    scope = TaskScope.model_validate({"entries": [{"origin": "https://docs.example.com", "path_prefix": "/guide"}]})
    assert url_scope_violation(scope, "https://docs.example.com/guide") is None
    assert url_scope_violation(scope, "https://docs.example.com/guide/install?x=1") is None
    assert url_scope_violation(scope, "https://docs.example.com/guidebook") == "TASK_SCOPE_PAGE_PATH_OUTSIDE"
    assert url_scope_violation(scope, "https://docs.example.com:8443/guide") == "TASK_SCOPE_PAGE_ORIGIN_OUTSIDE"
    assert url_scope_violation(scope, "http://docs.example.com/guide") == "TASK_SCOPE_PAGE_ORIGIN_OUTSIDE"
    assert url_scope_violation(scope, "https://evil.example.com/guide") == "TASK_SCOPE_PAGE_ORIGIN_OUTSIDE"
    assert url_scope_violation(scope, "javascript:pay()") == "TASK_SCOPE_PAGE_URL_NOT_HTTP"
    # No scope in the task truth: out of scope, whatever the page.
    assert url_scope_violation(None, "https://docs.example.com/guide") == "TASK_SCOPE_MISSING"
    assert load_scope(None) is None and load_scope("not json") is None and load_scope('{"entries": []}') is None
    element = tr.bound({"role": "link", "name": "Install", "attributes": {"href": "https://docs.example.com/guide/i"}},
                       page_url="https://docs.example.com/guide/")
    assert task_scope_gate(scope, operation="click", element=element) is None
    assert task_scope_gate(None, operation="click", element=element) == "TASK_SCOPE_MISSING"
    assert task_scope_gate(None, operation="scroll") == "TASK_SCOPE_MISSING"
    unbound = {k: v for k, v in element.items() if k != "binding"}
    assert task_scope_gate(scope, operation="click", element=unbound) == "TASK_SCOPE_TARGET_NOT_BOUND"
    off = {**element, "attributes": {"href": "/admin/billing"}}
    assert task_scope_gate(scope, operation="click", element=off) == "TASK_SCOPE_DESTINATION_PATH_OUTSIDE"
    # A submit's destination is its form action; Enter in a field submits the field's form.
    submit = tr.bound({"role": "button", "name": "Go", "submits": True,
                       "form": {"action": "https://docs.example.com/checkout/pay", "formaction": ""}},
                      page_url="https://docs.example.com/guide/")
    assert task_scope_gate(scope, operation="click", element=submit) == "TASK_SCOPE_DESTINATION_PATH_OUTSIDE"
    field = tr.bound({"role": "textbox", "name": "q", "form": {"action": "https://other.example.net/s"}},
                     page_url="https://docs.example.com/guide/")
    assert task_scope_gate(scope, operation="press_key", element=field, activates=True) == "TASK_SCOPE_DESTINATION_ORIGIN_OUTSIDE"
    assert task_scope_gate(scope, operation="press_key", element=field, activates=False) is None


def test_scope_is_recorded_from_the_task_never_an_allowlist():
    assert scope_for_new_task("docs.example.com", None).to_wire() == {
        "entries": [{"origin": "https://docs.example.com", "path_prefix": None}]}
    declared = scope_for_new_task("example.com", ["https://www.example.com/help/", "https://example.com"])
    assert declared.to_wire()["entries"] == [
        {"origin": "https://www.example.com", "path_prefix": "/help/"},
        {"origin": "https://example.com", "path_prefix": None}]
    for bad in ("https://example.org/", "ftp://example.com/", "https://example.com/?q=1", "https://u:p@example.com/"):
        with pytest.raises(ValueError):
            scope_for_new_task("example.com", [bad])


async def test_creation_path_records_scope_and_legacy_rows_fail_closed(tmp_path):
    ac, api, store = await t._client(tmp_path)
    async with ac:
        default = await t._make_task(ac)
        declared = await t._make_task(ac, scope=[f"https://{t.DOMAIN}/statements/"])
        refused = await ac.post("/v1/browser/tasks", headers=t.HEADERS, json={
            "profile_alias": "public_research", "strategy": "HARNESS", "autonomy_tier": "L1_HARNESS_DETERMINISTIC",
            "action_class": "A2", "target_domain": t.DOMAIN, "goal": "g", "scope": ["https://elsewhere.example.org/"]})
        row = await store.fetchone("SELECT scope_json FROM browser_tasks WHERE task_id = ?", (default["task_id"],))
        loaded = await api._load_task(declared["task_id"])
        # A pre-migration row with no scope stays without one: fail closed.
        await store.execute("UPDATE browser_tasks SET scope_json = NULL WHERE task_id = ?", (default["task_id"],))
        legacy = await api._load_task(default["task_id"])
    assert json.loads(row["scope_json"])["entries"] == [
        {"origin": f"https://{t.DOMAIN}", "path_prefix": None, "source": "TARGET_DOMAIN"}]
    assert default["scope"]["entries"][0]["origin"] == f"https://{t.DOMAIN}"
    assert [(e.origin, e.path_prefix) for e in loaded.scope.entries] == [(f"https://{t.DOMAIN}", "/statements/")]
    assert refused.status_code == 422 and "TASK_SCOPE_OUTSIDE_TARGET_DOMAIN" in refused.text
    assert legacy.scope is None


async def test_an_owner_approval_widens_that_tasks_scope(tmp_path):
    """The owner's answer to a scope escalation is part of the task truth the gate reads."""
    import test_browser_review_i2_lifecycle as lc

    ac, store, _ex, api = await lc._setup(tmp_path, lc.OUT_OF_SCOPE)
    async with ac:
        tid, decision_id = await lc._escalate(ac, store)
        before = await api._load_task(tid)
        await store.execute("UPDATE decisions SET status = 'APPROVED' WHERE id = ?", (decision_id,))
        await api._sync_waiting_owner_decision(before)
        after = await api._load_task(tid)
    assert [e.origin for e in before.scope.entries] == [f"https://{t.DOMAIN}"]
    widened = [(e.origin, e.source.split(":")[0]) for e in after.scope.entries]
    assert widened == [(f"https://{t.DOMAIN}", "TARGET_DOMAIN"), ("https://outside.example.net", "OWNER_APPROVED")]


async def test_real_chromium_no_scope_fails_closed_and_path_scope_holds(chromium):
    _m, pw, harness = chromium
    # The same benign click, three task truths.
    ok, seen = await _route(pw, harness, "/i5/links", **_det("click", "#stay"))
    assert ok.state is StepState.VERIFIED_SUCCESS and seen == ["benign:stay"], ok.reasons
    none, seen = await _route(pw, harness, "/i5/links", task=_task(None), **_det("click", "#stay"))
    assert _lane4(none) and "TASK_SCOPE:TASK_SCOPE_MISSING" in none.reasons and seen == []
    guide = scope_for_new_task(DOMAIN, [f"https://{DOMAIN}/guide/"])
    out, seen = await _route(pw, harness, "/i5/links", task=_task(guide), **_det("click", "#stay"))
    assert _lane4(out) and "TASK_SCOPE:TASK_SCOPE_PAGE_PATH_OUTSIDE" in out.reasons and seen == []
    # Lane 3 goes through the same gate.
    sh, seen = await _route(pw, harness, "/i5/links", task=_task(None), **_sh("#stay", "Show more"))
    assert _lane4(sh) and "TASK_SCOPE:TASK_SCOPE_MISSING" in sh.reasons and seen == []


async def test_real_chromium_link_destination_must_be_in_scope(chromium):
    _m, pw, harness = chromium
    scope = scope_for_new_task(DOMAIN, [f"https://{DOMAIN}/i5/"])
    ok, seen = await _route(pw, harness, "/i5/links", task=_task(scope), **_det("click", "#inscope"))
    assert ok.state is StepState.VERIFIED_SUCCESS and seen == ["nav:/i5/links?page=2"], ok.reasons
    for loc, code in (("#outpath", "TASK_SCOPE_DESTINATION_PATH_OUTSIDE"), ("#outorigin", "TASK_SCOPE_DESTINATION_ORIGIN_OUTSIDE")):
        result, seen = await _route(pw, harness, "/i5/links", task=_task(scope), **_det("click", loc))
        assert _lane4(result) and f"TASK_SCOPE:{code}" in result.reasons and seen == [], (loc, result.reasons)


async def test_real_chromium_harness_rechecks_scope_and_binding_at_the_click(chromium):
    """The gateway's check is not the only one: the Harness refuses on its own."""
    _m, pw, harness = chromium
    _goto(pw, "/i5/links")
    described = await harness.describe(_task(), "#stay")
    binding = described["binding"]
    with harness_lease_fence(HarnessLeaseFence("public_research", _task().task_id, 1)):
        narrow = _task(scope_for_new_task(DOMAIN, [f"https://{DOMAIN}/guide/"]))
        with pytest.raises(BrowserAdapterError) as scoped:
            await harness.click(narrow, "#stay", binding=binding)
        with pytest.raises(BrowserAdapterError) as unscoped:
            await harness.click(_task(None), "#stay", binding=binding)
        with pytest.raises(BrowserAdapterError) as unbound:
            await harness.click(_task(), "#stay", binding=None)
        forged = {**binding, "digest": "f" * 64}
        with pytest.raises(BrowserAdapterError) as changed:
            await harness.click(_task(), "#stay", binding=forged)
    assert scoped.value.code == "BROWSER_HARNESS_REFUSED" and scoped.value.detail == "TASK_SCOPE_PAGE_PATH_OUTSIDE"
    assert unscoped.value.detail == "TASK_SCOPE_REQUIRED"
    assert unbound.value.detail == "TARGET_BINDING_REQUIRED"
    assert changed.value.detail == "TARGET_CHANGED"
    assert _seen(pw) == []


async def test_assignment_paths_apply_the_scope_rule(tmp_path):
    """/assignments plan + Hybrid: a task whose truth lacks a scope is handed to the owner,
    and a plan step on a page outside the recorded scope is too."""
    from test_browser_review_i4_fail_safe_classifier import _PlanHarness
    from van_gateway.browser.worker import HybridBrowserWorker

    element = {"locator": "#next", "role": "link", "name": "Next page"}

    async def run(scope_json_sql=None, declared=None, page="/x"):
        harness = _PlanHarness([element])
        base = harness.describe

        async def describe(task, loc):
            out = await base(task, loc)
            out["page_url"] = f"https://{t.DOMAIN}{page}"
            return out

        harness.describe = describe
        ac, _api, store = await t._client(pathlib.Path(tempfile.mkdtemp()), worker=HybridBrowserWorker(harness, None),
                                          verifier=t._Verdict())
        async with ac:
            extra = {"scope": declared} if declared else {}
            task = await t._make_task(ac, strategy="HARNESS", autonomy_tier="L1_HARNESS_DETERMINISTIC", **extra)
            if scope_json_sql is not None:
                await store.execute("UPDATE browser_tasks SET scope_json = NULL WHERE task_id = ?", (task["task_id"],))
            r = await ac.post("/v1/browser/assignments", headers=t.HEADERS, json={
                "task_id": task["task_id"], "turn_id": "t1", "command_id": "cmd-owner-1", "goal": "read",
                "allowed_domains": [t.DOMAIN], "action_class_ceiling": "A2", "autonomy_tier": "L1_HARNESS_DETERMINISTIC",
                "plan": {"steps": [{"kind": "click", "domain": t.DOMAIN, "locator": "#next", "instruction": "Next page"}]},
                "postcondition": {"kind": "READ_BACK", "field": "title", "expected": "Statement"}})
        return r.json(), harness

    ok, harness = await run()
    assert ok["stop_reason"] == "GOAL_ACHIEVED" and harness.calls == [("click", "#next")]
    missing, harness = await run(scope_json_sql=True)
    assert (missing["stop_reason"], missing["detail"]) == ("OWNER_TAKEOVER", "TASK_SCOPE:TASK_SCOPE_MISSING")
    assert harness.calls == []
    outside, harness = await run(declared=[f"https://{t.DOMAIN}/statements/"], page="/admin")
    assert (outside["stop_reason"], outside["detail"]) == ("OWNER_TAKEOVER", "TASK_SCOPE:TASK_SCOPE_PAGE_PATH_OUTSIDE")
    assert harness.calls == []


# ------------------------------------------------------------------ Part 2: I5 MAJOR-1


async def test_major1_visible_text_is_reported_and_classified(chromium):
    _m, pw, harness = chromium
    _goto(pw, "/i5/spoof")
    s2 = (await harness.describe(_task(), "#s2"))["element"]
    assert (s2["name"], s2["text"]) == ("Next", "Pay 500 now")
    icon = (await harness.describe(_task(), "#icon"))["element"]
    assert (icon["name"], icon["text"]) == ("", "Pay now")
    for kw in (_det("click", "#s1"), _det("click", "#s2"), _sh("#s1", "Show details"), _det("click", "#icon")):
        result, seen = await _route(pw, harness, "/i5/spoof", **kw)
        assert _lane4(result) and _money(seen) == [], (kw, result.reasons)
    ok, seen = await _route(pw, harness, "/i5/spoof", **_det("click", "#ok"))
    assert ok.state is StepState.VERIFIED_SUCCESS and seen == ["benign:ok"], ok.reasons


def test_major1_name_content_mismatch_rule():
    el = {"role": "button", "name": "Next", "text": "Next  page", "tag": "button"}
    assert "R7_NAME_CONTENT_MISMATCH" in assess_action("click", element=el).rules
    same = {"role": "button", "name": "Next page", "text": "Next page", "tag": "button"}
    assert assess_action("click", element=same).action_class == "A2"
    # Only name-from-content roles: a textbox's label is not its content.
    box = {"role": "textbox", "name": "Search", "text": "Search docs", "tag": "input"}
    assert "R7_NAME_CONTENT_MISMATCH" not in assess_action("click", element=box).rules


# ------------------------------------------------------------------ MAJOR-2


async def test_major2_unresolved_structures_are_a4(chromium):
    _m, pw, harness = chromium
    cases = {
        "#wrapper": "TARGET_OCCLUDED",          # its centre is the pay button inside it
        "#next": "TARGET_OCCLUDED",             # an opacity:0 pay layer over it
        "#generic": "TARGET_NOT_A_CONTROL:generic",
        "#host": "TARGET_IS_SHADOW_HOST",
        "#frame": "TARGET_IS_FRAME",
    }
    for loc, reason in cases.items():
        result, seen = await _route(pw, harness, "/i5/structure", **_det("click", loc))
        assert _lane4(result) and _money(seen) == [], (loc, result.reasons, seen)
        assert f"DETERMINISTIC_TARGET_UNRESOLVED:{reason}" in result.reasons, (loc, result.reasons)
    wrapped, seen = await _route(pw, harness, "/i5/structure", **_sh("#wrapper", "the panel"))
    assert _lane4(wrapped) and _money(seen) == []


async def test_major2_hit_test_refuses_an_overlay_the_describe_did_not_see(chromium):
    """The overlay appears after /describe: the Harness hit test at the click refuses."""
    _m, pw, harness = chromium
    _goto(pw, "/i5/race")
    described = await harness.describe(_task(), "#read")
    pw.call(lambda page, cdp: page.evaluate(
        "(() => { const p = document.getElementById('payx'), r = document.getElementById('read').getBoundingClientRect();"
        " p.style.left = r.left + 'px'; p.style.top = (r.top + scrollY) + 'px'; p.style.zIndex = 99; })()"))
    with harness_lease_fence(HarnessLeaseFence("public_research", _task().task_id, 1)):
        with pytest.raises(BrowserAdapterError) as refused:
            await harness.click(_task(), "#read", binding=described["binding"])
    assert refused.value.detail == "TARGET_NOT_HIT"
    assert _money(_seen(pw)) == []


async def test_major2_swap_during_the_click_is_cancelled(chromium):
    """test_i5_swap, deterministic: "Read more" is classified A2, passes the hit test, and when
    the pointer arrives the page moves the pay button under it. The guard cancels the events
    that land on the pay button (without the guard its handler runs: induced in G6a)."""
    _m, pw, harness = chromium
    for _ in range(5):
        pw.call(lambda page, cdp: page.mouse.move(0, 0))  # the pointer arrives fresh each time
        result, seen = await _route(pw, harness, "/i5/race", **_det("click", "#read"))
        assert _money(seen) == [], seen
        assert result.state is StepState.OWNER_TAKEOVER, result.reasons
        assert any(r.startswith("HARNESS_REFUSED:TARGET_MOVED_DURING_ACTUATION") for r in result.reasons), result.reasons


async def test_major2_binding_survives_a_selector_swap_and_refuses_a_replaced_node(chromium):
    """The Harness acts on the bound node, never a re-queried selector."""
    _m, pw, harness = chromium
    _goto(pw, "/i5/spoof")
    ok = await harness.describe(_task(), "#ok")
    # The page gives the pay button the same id and puts it first: "#ok" now matches it.
    pw.call(lambda page, cdp: page.evaluate(
        "(() => { const p = document.getElementById('s1'); p.id = 'ok'; document.body.prepend(p); })()"))
    assert pw.call(lambda page, cdp: page.evaluate("document.querySelector('#ok').textContent")) == "Pay 500 now"
    with harness_lease_fence(HarnessLeaseFence("public_research", _task().task_id, 1)):
        await harness.click(_task(), "#ok", binding=ok["binding"])
        assert _seen(pw) == ["benign:ok"]  # the node described, not the one "#ok" now matches
        pw.call(lambda page, cdp: page.evaluate("document.querySelectorAll('#ok')[1].replaceWith(document.createElement('b'))"))
        with pytest.raises(BrowserAdapterError) as gone:
            await harness.click(_task(), "#ok", binding=ok["binding"])
    assert gone.value.detail == "TARGET_BINDING_LOST"
    assert _money(_seen(pw)) == []


async def test_major2_a_label_changed_after_classification_is_refused(chromium):
    _m, pw, harness = chromium
    _goto(pw, "/i5/spoof")
    ok = await harness.describe(_task(), "#ok")
    pw.call(lambda page, cdp: page.evaluate(
        "(() => { const b = document.getElementById('ok'); b.textContent = 'Pay 500 now'; b.onclick = () => money('relabel'); })()"))
    with harness_lease_fence(HarnessLeaseFence("public_research", _task().task_id, 1)):
        with pytest.raises(BrowserAdapterError) as changed:
            await harness.click(_task(), "#ok", binding=ok["binding"])
    assert changed.value.detail == "TARGET_CHANGED" and _seen(pw) == []


# ------------------------------------------------------------------ MAJOR-3


async def test_major3_press_key_is_classified_against_the_focused_element(chromium):
    _m, pw, harness = chromium
    for key in ("Enter", " "):
        result, seen = await _route(pw, harness, "/i5/focus", **_det("press_key", None, key))
        assert _lane4(result) and _money(seen) == [], (key, result.reasons)
        assert any("KEY_ACTIVATES_FOCUSED" in r for r in result.reasons)
    # A letter on a focused button is not a fill of anything: A4.
    letter, seen = await _route(pw, harness, "/i5/focus?f=docs", **_det("press_key", None, "p"))
    assert _lane4(letter) and any("R10_KEY_OUTSIDE_FIELD" in r for r in letter.reasons)
    # Benign: Enter on a focused in-scope link, Tab anywhere.
    link, seen = await _route(pw, harness, "/i5/focus?f=docs", **_det("press_key", None, "Enter"))
    assert link.state is StepState.VERIFIED_SUCCESS and seen == ["nav:/i5/links"], link.reasons
    tab, seen = await _route(pw, harness, "/i5/focus?f=docs", **_det("press_key", None, "Tab"))
    assert tab.state is StepState.VERIFIED_SUCCESS and seen == [], tab.reasons


async def test_major3_unknown_focus_and_moved_focus(chromium):
    _m, pw, harness = chromium
    _goto(pw, "/i5/structure")
    pw.call(lambda page, cdp: page.focus("#frame"))
    unknown = await _route_focused(pw, harness, "Enter")
    assert _lane4(unknown) and any("FOCUS_UNRESOLVED:TARGET_IS_FRAME" in r for r in unknown.reasons)
    _goto(pw, "/i5/focus?f=docs")
    focused = await harness.describe_focus(_task())
    pw.call(lambda page, cdp: page.focus("#pay"))
    with harness_lease_fence(HarnessLeaseFence("public_research", _task().task_id, 1)):
        with pytest.raises(BrowserAdapterError) as moved:
            await harness.press(_task(), "Enter", binding=focused["binding"])
    assert moved.value.detail == "FOCUS_CHANGED" and _money(_seen(pw)) == []


async def _route_focused(pw, harness, key):
    router = tr.make_router(target_resolver=HarnessTargetResolver(harness), executor=HarnessActionExecutor(harness),
                            semantic_fallback=tr.FakeStagehand(None), jev_client=None)
    step = tr.step(**_det("press_key", None, key))
    step.task = _task()
    with harness_lease_fence(HarnessLeaseFence("public_research", step.task.task_id, 1)):
        return await router.route(step)


def test_major3_key_classifier():
    field = {"role": "searchbox", "name": "Search docs", "tag": "input", "type": "search"}
    assert assess_key_press("a", field).action_class == "A3"                 # typing = a fill
    assert assess_key_press("Enter", None, resolved=False).rules == ("R6_UNRESOLVED_FOCUS",)
    assert assess_key_press("Enter", {"role": "generic", "name": "", "tag": "body"}).action_class == "A4"
    assert assess_key_press("PageDown", {"role": "generic", "name": "", "tag": "body"}).action_class == "A2"


# ------------------------------------------------------------------ MAJOR-4


async def test_major4_form_context_is_reported_and_judged(chromium):
    _m, pw, harness = chromium
    _goto(pw, "/i5/forms")
    go = (await harness.describe(_task(), "#go"))["element"]
    assert (go["type"], go["effective_type"], go["submits"]) == ("", "submit", True)
    assert go["form"]["action"] == f"https://{DOMAIN}/checkout/pay" and go["form"]["method"] == "post"
    for kw in (_det("click", "#go"), _sh("#go", "Next")):
        result, seen = await _route(pw, harness, "/i5/forms", **kw)
        assert _lane4(result) and _money(seen) == [], result.reasons
    # A submit into a benign in-scope form is still a submit (R3, documented trade-off).
    find, seen = await _route(pw, harness, "/i5/forms", **_det("click", "#find"))
    assert _lane4(find) and any("R3_RISKY_ROLE:submit" in r for r in find.reasons) and seen == []
    # A non-submitting button beside the forms runs.
    plain, seen = await _route(pw, harness, "/i5/forms", **_det("click", "#plain"))
    assert plain.state is StepState.VERIFIED_SUCCESS and seen == ["benign:plain"], plain.reasons


async def test_major4_fill_in_a_form_goes_to_the_bound_field(chromium):
    _m, pw, harness = chromium
    result, seen = await _route(pw, harness, "/i5/forms", action_class_ceiling="A3",
                                **_det("fill", "#q", "secretref://browser/q"))
    task_class = result.reasons
    value = pw.call(lambda page, cdp: page.evaluate("document.getElementById('q').value"))
    # The fixture task is admitted at A2, so the A3 fill is refused above its class; with an
    # A3 task it fills the bound field.
    assert result.state is StepState.POLICY_REFUSED and value == "", task_class
    a3 = _task().model_copy(update={"action_class": "A3"})
    result, seen = await _route(pw, harness, "/i5/forms", task=a3, action_class_ceiling="A3",
                                **_det("fill", "#q", "secretref://browser/q"))
    value = pw.call(lambda page, cdp: page.evaluate("document.getElementById('q').value"))
    assert result.state is StepState.VERIFIED_SUCCESS and value == "install guide", result.reasons
    assert _money(seen) == []


# ------------------------------------------------------------------ MAJOR-5


async def test_major5_image_and_css_names_are_text_and_empty_names_are_a4(chromium):
    _m, pw, harness = chromium
    _goto(pw, "/i5/media")
    img = (await harness.describe(_task(), "#imgbtn"))["element"]
    assert "pay-now.png" in img["media"]
    assert "checkout-button.svg" in (await harness.describe(_task(), "#bg"))["element"]["media"]
    assert "Pay" in (await harness.describe(_task(), "#css"))["element"]["media"]
    for loc in ("#imgbtn", "#bg", "#css"):
        result, seen = await _route(pw, harness, "/i5/media", **_det("click", loc))
        assert _lane4(result) and _money(seen) == [], (loc, result.reasons)
        assert any("R8_EMPTY_NAME" in r for r in result.reasons), result.reasons
    ok, seen = await _route(pw, harness, "/i5/media", **_det("click", "#imgok"))
    assert ok.state is StepState.VERIFIED_SUCCESS and seen == ["benign:imgok"], ok.reasons


# ------------------------------------------------------------------ MAJOR-6


MAJOR6_COMMITMENTS = [
    "Yes, charge me", "Charge card", "Bid now", "Place bid", "Pledge", "Contribute", "Invest now", "Sell all",
    "Trade", "Execute trade", "Stake", "Top up", "Start free trial", "Unlock for 5 dollars", "Complete",
    "Finish", "Proceed", "Place my 0rder now", "Commit", "Finalize", "Finalise", "Wire funds", "Redeem",
    "Claim", "Rent", "Hire", "Lend", "Swap", "Mint", "Add to cart", "Add to basket", "Continue", "Five dollars",
]
#: Words the classifier cannot tell from benign navigation: held only by the task scope.
MAJOR6_RESIDUAL = ["Next", "Go", "Ok", "Yes", "I understand", "Let's go"]
#: Documented false positives of the new stems/words (A4 -> the owner, the fail-safe way).
MAJOR6_FALSE_POSITIVES = [
    "Continue reading", "Complete profile", "Industrial design", "Proceedings 2025", "Place of birth",
    "Claim a username", "Swap panels", "Investigate logs", "Executive summary", "Discharge summary",
    "Desktop update", "Euro 2024 results",
]
MAJOR6_STILL_BENIGN = [
    "Next page", "Read more", "Install guide", "Search", "Bestseller list", "Marketplace", "Trademark notice",
    "Mistake report", "Calendar", "Committee", "Wireless setup", "Forbidden city", "Current release",
]


@pytest.mark.parametrize("label", MAJOR6_COMMITMENTS)
def test_major6_commitment_verbs_are_a4(label):
    el = {"role": "button", "name": label, "text": label, "tag": "button"}
    assert assess_action("click", element=el).action_class == "A4", risk_stem_hits([label])


@pytest.mark.parametrize("label", MAJOR6_FALSE_POSITIVES)
def test_major6_documented_false_positives(label):
    assert risk_stem_hits([label]), label


@pytest.mark.parametrize("label", MAJOR6_STILL_BENIGN + MAJOR6_RESIDUAL)
def test_major6_word_matching_keeps_ordinary_words_benign(label):
    el = {"role": "link", "name": label, "text": label, "tag": "a"}
    assert assess_action("click", element=el).action_class == "A2", risk_stem_hits([label])
