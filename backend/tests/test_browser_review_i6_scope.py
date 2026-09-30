"""Review I6 — task scope where the browser actually lands, and the residual leaks.

M3  the shared URL rule (WHATWG normalisation) checked against real Chromium's own parser;
    navigate traversal refused by the gateway *and* by the Harness on its own; runtime
    destinations (onclick ``location=``, an href swapped on pointerdown) land out of scope
    and become NOT_SATISFIED -> lane 4 with the page closed; a page that poisons
    ``window.URL`` / ``Element.prototype.getAttribute`` cannot make /describe lie (the
    describe script runs in a CDP isolated world).
m1  an owner approval widens a task's scope by the approved delta only, and only while the
    authorization is ACTIVE and unexpired.
m2  the Harness refuses /navigate, /scroll and /upload without a task scope.
m3  a token in a link's text is masked in the accessible name (page script and sanitizer),
    B2 keeps the page ineligible, and R11 sends a masked name to A4.
m4  the step ledger keeps codes from a closed vocabulary only.

Every Chromium case drives the real Harness HTTP handler against headless Chromium serving
the pages below at https://docs.example.com/.
"""

from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

import test_browser_api as _t  # noqa: F401
from test_browser_api import _settings  # noqa: F401 - autouse: the API settings the routes need
import test_browser_interaction_router as tr
import test_harness_elements as he
from van_gateway.browser.action_risk import assess_action
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
    RouterStepLedger,
    StepState,
    harness_page_to_jev_observation,
    ledger_reasons,
    unresolved_reason,
)
from van_gateway.browser.jev_eligibility import JevEligibilityPolicy, classify_observation
from van_gateway.browser.task_scope import TaskScopeError, parse_scope_entry, scope_for_new_task

DOMAIN = he.DOMAIN
VECTORS = json.loads((Path(__file__).resolve().parent / "fixtures" / "task_scope" / "url_vectors.v1.json").read_text(encoding="utf-8"))
LOG = """<script>
window.__van = [];
window.money = (w) => window.__van.push('money:' + w);
document.addEventListener('submit', (e) => { window.__van.push('submit:' + e.target.getAttribute('action')); e.preventDefault(); }, true);
</script>"""
PAGES = {
    "/docs/start": '<a id="a" href="/docs/next">Read guide</a>',
    "/docs/next": "<p>next</p>",
    "/checkout/pay": "<p>pay</p>",
    # Runtime destinations: the element classified is a benign in-scope control.
    "/docs/onclick_out": '<button id="b" onclick="location.href=\'/checkout/pay\'">Read guide</button>',
    "/docs/onclick_in": '<button id="b" onclick="location.href=\'/docs/next\'">Read guide</button>',
    "/docs/href_swap": '<a id="a" href="/docs/next" onpointerdown="this.href=\'/checkout/pay\'">Read guide</a>',
    # Page-poisoned built-ins that made the main-world describe report a false href.
    "/docs/url_poison": '<script>(()=>{const R=URL;function F(u,b){const x=new R(u,b);return x.pathname.startsWith("/checkout")?new R("/docs/next",x.origin):x;}F.prototype=R.prototype;window.URL=F;})()</script><a id="a" href="/checkout/pay">Read guide</a>',
    "/docs/getattr_poison": '<script>(()=>{const g=Element.prototype.getAttribute;Element.prototype.getAttribute=function(n){const v=g.call(this,n);return (n==="href"&&v&&v.startsWith("/checkout"))?"/docs/next":v;};})()</script><a id="a" href="/checkout/pay">Read guide</a>',
    "/docs/token": '<a id="a" href="/docs/next">Code tok_9f8e7d6c5b4a</a>',
    "/docs/role": '<button id="b" role="acct-0012345678">Open</button>',
}


class _Pages(he._PlaywrightPage):
    def _run(self, executable: str) -> None:
        from playwright.sync_api import sync_playwright

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path=executable, args=self.launch_args())
                page = browser.new_page()

                def serve(route):
                    path = "/" + route.request.url.split("/", 3)[-1].split("?")[0].split("#")[0]
                    body = PAGES.get(path, f"<p>landed {path}</p>")
                    route.fulfill(status=200, content_type="text/html",
                                  body=f"<!doctype html><html><head><title>{path}</title>{LOG}</head><body>{body}</body></html>")

                page.route("**/*", serve)
                cdp = page.context.new_cdp_session(page)
                self.page, self.cdp = page, cdp
                self.ready.set()
                self._serve_jobs(page, cdp)  # unit G9c: keeps servicing routes while idle
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
    pw = _Pages(executable)

    # Unit G9c: the fixed scripts need browser-harness's event stream for the network guard.
    monkeypatch.setattr(module, "run_harness", he.guarded_run_harness(pw))
    server = ThreadingHTTPServer(("127.0.0.1", 0), module.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield module, pw, HttpBrowserHarnessAdapter(None, base_url=f"http://127.0.0.1:{server.server_address[1]}", enabled=True)
    finally:
        server.shutdown()
        server.server_close()
        pw.close()


DOCS = scope_for_new_task(DOMAIN, [f"https://{DOMAIN}/docs/"])


def _task(scope=DOCS):
    return he._task().model_copy(update={"scope": scope})


def _goto(pw, path):
    pw.call(lambda page, cdp: page.goto(f"https://{DOMAIN}{path}"))
    pw.call(lambda page, cdp: page.wait_for_timeout(100))


def _url(pw):
    return pw.call(lambda page, cdp: page.url)


async def _route(pw, harness, path, *, task=None, **kw):
    _goto(pw, path)
    router = tr.make_router(target_resolver=HarnessTargetResolver(harness), executor=HarnessActionExecutor(harness),
                            semantic_fallback=tr.FakeStagehand(None), jev_client=None)
    step = tr.step(**kw)
    step.task = task or _task()
    with harness_lease_fence(HarnessLeaseFence("public_research", step.task.task_id, 1)):
        result = await router.route(step)
    pw.call(lambda page, cdp: page.wait_for_timeout(200))
    return result


def _click(loc):
    return {"deterministic_action": DeterministicAction(operation="click", locator=loc)}


# ------------------------------------------------------------------ M3: the shared rule


async def test_m3_vectors_match_real_chromiums_whatwg_parser(chromium):
    """Every vector the shared rule parses, it parses as Chromium's URL parser does (origin,
    trailing host dot aside, and path). The ones it refuses are refused (fail closed)."""
    _m, pw, _h = chromium
    checked = 0
    for vector in VECTORS["vectors"]:
        if vector["parsed"] is None:
            continue
        got = pw.call(lambda page, cdp, v=vector: page.evaluate(
            "([i, b]) => { const u = b === null ? new URL(i) : new URL(i, b);"
            " return {origin: u.protocol + '//' + u.hostname.replace(/\\.$/, '') + (u.port ? ':' + u.port : ''), path: u.pathname}; }",
            [v["input"], v["base"]]))
        assert got == vector["parsed"], vector
        checked += 1
    assert checked >= 35


def test_m3_scope_entries_must_be_normal():
    for bad in ("https://docs.example.com/docs/../", "https://docs.example.com/docs/%2e%2e/x/",
                "https://docs.example.com/docs\\x/", "https://docs.example.com/a%2fb/"):
        with pytest.raises(TaskScopeError) as refused:
            parse_scope_entry(bad, DOMAIN)
        assert refused.value.code == "TASK_SCOPE_ENTRY_PATH_NOT_NORMAL", bad
    entry = parse_scope_entry("https://DOCS.example.com.:443/docs/", DOMAIN)
    assert (entry.origin, entry.path_prefix) == (f"https://{DOMAIN}", "/docs/")


@pytest.mark.parametrize("url", [
    f"https://{DOMAIN}/docs/../checkout/pay",
    f"https://{DOMAIN}/docs/%2e%2e/checkout/pay",
    f"https://{DOMAIN}/docs/..\\checkout/pay",
])
async def test_m3_harness_refuses_navigate_traversal_on_its_own(chromium, url):
    """The gateway refuses these too (vectors); here the Harness is called directly."""
    _m, pw, harness = chromium
    _goto(pw, "/docs/start")
    with harness_lease_fence(HarnessLeaseFence("public_research", _task().task_id, 1)):
        with pytest.raises(BrowserAdapterError) as refused:
            await harness.navigate(_task(), url)
    assert refused.value.detail == "TASK_SCOPE_NAVIGATE_PATH_OUTSIDE"
    assert _url(pw) == f"https://{DOMAIN}/docs/start"


async def test_m3_navigate_in_scope_still_lands(chromium):
    _m, pw, harness = chromium
    _goto(pw, "/docs/start")
    with harness_lease_fence(HarnessLeaseFence("public_research", _task().task_id, 1)):
        page = await harness.navigate(_task(), f"https://{DOMAIN}/docs/./next")
    assert page["url"] == f"https://{DOMAIN}/docs/next" == _url(pw)


# ------------------------------------------------------------------ M3: where it lands


@pytest.mark.parametrize("path,loc", [("/docs/onclick_out", "#b"), ("/docs/href_swap", "#a")])
async def test_m3_runtime_destination_out_of_scope_is_lane_4_and_closed(chromium, path, loc):
    _m, pw, harness = chromium
    result = await _route(pw, harness, path, **_click(loc))
    assert result.state is StepState.OWNER_TAKEOVER, result.reasons
    # Unit G9c: the network-effect guard now stops the out-of-scope navigation itself (lane 4,
    # NAVIGATION_OUT_OF_SCOPE) before the browser can land there; the landing check still
    # closes the page. Without the guard the landing check reports it (G9b's code).
    if "HARNESS_REFUSED:NETWORK_WRITE_BLOCKED:NAVIGATION_OUT_OF_SCOPE" not in result.reasons:
        assert "TASK_SCOPE:TASK_SCOPE_LANDED_PATH_OUTSIDE" in result.reasons, result.reasons
        assert result.trail[-2:] == [StepState.NOT_SATISFIED.value, StepState.OWNER_TAKEOVER.value]
    # The out-of-scope page was closed: nothing further runs on it.
    assert _url(pw) == "about:blank"


async def test_m3_control_runtime_destination_in_scope_succeeds(chromium):
    _m, pw, harness = chromium
    result = await _route(pw, harness, "/docs/onclick_in", **_click("#b"))
    assert result.state is StepState.VERIFIED_SUCCESS, result.reasons
    assert _url(pw) == f"https://{DOMAIN}/docs/next"


@pytest.mark.parametrize("path", ["/docs/url_poison", "/docs/getattr_poison"])
async def test_m3_describe_runs_in_an_isolated_world(chromium, path):
    """The page's own JS says the href is /docs/next; describe reports the DOM's /checkout/pay."""
    _m, pw, harness = chromium
    _goto(pw, path)
    lied = pw.call(lambda page, cdp: page.evaluate(
        "new URL(document.getElementById('a').getAttribute('href'), location.href).pathname"))
    assert lied == "/docs/next"  # the poisoning is live in the main world
    described = await harness.describe(_task(), "#a")
    assert described["element"]["attributes"]["href"] == f"https://{DOMAIN}/checkout/pay"
    assert described["page_url"] == f"https://{DOMAIN}{path}"
    result = await _route(pw, harness, path, **_click("#a"))
    assert result.state in (StepState.OWNER_TAKEOVER, StepState.POLICY_REFUSED), result.reasons
    assert _url(pw) == f"https://{DOMAIN}{path}"


# ------------------------------------------------------------------ m2


async def test_m2_harness_refuses_mutating_paths_without_a_scope(chromium):
    _m, pw, harness = chromium
    _goto(pw, "/docs/start")
    none = _task(None)
    with harness_lease_fence(HarnessLeaseFence("public_research", none.task_id, 1)):
        for call in (lambda: harness.navigate(none, f"https://{DOMAIN}/checkout/pay"),
                     lambda: harness.scroll(none, {"y": 100}),
                     lambda: harness.upload(none, "#a", "fileref://downloads/x.txt")):
            with pytest.raises(BrowserAdapterError) as refused:
                await call()
            assert refused.value.detail == "TASK_SCOPE_REQUIRED"
    assert _url(pw) == f"https://{DOMAIN}/docs/start"


# ------------------------------------------------------------------ m3


async def test_m3_token_in_link_text_is_masked_and_never_reaches_jev(chromium):
    _m, pw, harness = chromium
    _goto(pw, "/docs/token")
    info = await harness.page_info(_task())
    assert "tok_9f8e7d6c5b4a" not in json.dumps(info["elements"])
    link = next(e for e in info["elements"] if e["locator"] == "#a")
    assert link["name"] == "Code [REDACTED]"
    described = await harness.describe(_task(), "#a")
    assert described["element"]["name"] == "Code [REDACTED]"
    obs = harness_page_to_jev_observation(info, profile_alias="public_research")
    b2 = classify_observation(obs, closed_operation_set=("click", "abstain"), action_class_ceiling="A2",
                              policy=JevEligibilityPolicy())
    assert b2.eligibility_class.value == "OWNER_PRIVATE" and getattr(b2, "jev_payload", None) is None
    # R11: a masked name is never positively low-risk.
    assessment = assess_action("click", element={**described["element"], "text": "Open"}, locator="#a")
    assert "R11_REDACTED_CONTENT" in assessment.rules and assessment.action_class == "A4"


def test_m3_sanitizer_masks_name_and_description(monkeypatch, tmp_path):
    hs = he._load(monkeypatch, tmp_path)
    out = hs.sanitize_element({"locator": "#a", "name": "Code tok_9f8e7d6c5b4a", "description": "Ref ab12cd34ef56gh78",
                               "hidden": False})
    assert out["name"] == "Code [REDACTED]" and out["description"] == "Ref [REDACTED]"


# ------------------------------------------------------------------ m4


async def test_m4_page_role_never_reaches_the_step_ledger(chromium):
    _m, pw, harness = chromium
    task = _task(scope_for_new_task(DOMAIN, None))
    result = await _route(pw, harness, "/docs/role", task=task, **_click("#b"))
    step = tr.step(**_click("#b"))
    step.task = task
    record = json.dumps(RouterStepLedger._record_json(step, result, {}))
    assert "0012345678" not in record and "acct" not in record
    assert "DETERMINISTIC_TARGET_UNRESOLVED:TARGET_NOT_A_CONTROL:UNKNOWN_ROLE" in result.reasons


def test_m4_reason_sources_and_ledger_vocabulary():
    assert unresolved_reason({"role": "orchid.lane@example.org", "name": "x"}) == "TARGET_NOT_A_CONTROL:UNKNOWN_ROLE"
    assert unresolved_reason({"role": "generic", "name": "x"}) == "TARGET_NOT_A_CONTROL:generic"
    assert ledger_reasons([
        "POLICY_REFUSED:refused #det-locator-XYZ", "R1_NON_LATIN_OR_UNMAPPED:€",
        "DETERMINISTIC_ACTION_RISK:KEY_ACTIVATES_FOCUSED;R2_RISK_STEM:pay,checkout,word;R8_EMPTY_NAME",
        "STEP_CEILING_CAPPED_BY_TASK:A3->A2", "RESOLVER_FAILED:TimeoutError",
        "automated_payment_prohibited_in_interaction_router_deterministic:payment_intent_in_text",
        "X:orchid.lane@example.org",
    ]) == [
        "POLICY_REFUSED:OMITTED", "R1_NON_LATIN_OR_UNMAPPED:OMITTED",
        "DETERMINISTIC_ACTION_RISK:KEY_ACTIVATES_FOCUSED;R2_RISK_STEM:pay,checkout,word;R8_EMPTY_NAME",
        "STEP_CEILING_CAPPED_BY_TASK:A3->A2", "RESOLVER_FAILED:TimeoutError",
        "automated_payment_prohibited_in_interaction_router_deterministic:payment_intent_in_text",
        "X:OMITTED",
    ]


async def test_m4_executor_exception_text_is_not_a_reason():
    from van_gateway.browser.policy import BrowserPolicyError

    router = tr.make_router(executor=tr.FakeExecutor(error=BrowserPolicyError("refused #det-locator-XYZ")),
                            eligibility_classifier=None)
    result = await router.route(tr.step(**_click("#go")))
    assert "POLICY_REFUSED:BrowserPolicyError" in result.reasons
    assert not any("det-locator" in r for r in result.reasons)


# ------------------------------------------------------------------ m1


async def test_m1_approval_adds_only_the_delta_and_only_while_active(tmp_path):
    import test_browser_api as t
    import test_browser_review_i2_lifecycle as lc
    from van_gateway.browser.task_scope import url_scope_violation

    ac, store, _ex, api = await lc._setup(tmp_path, lc.OUT_OF_SCOPE)
    async with ac:
        tid, decision_id = await lc._escalate(ac, store)
        path_scope = scope_for_new_task(t.DOMAIN, [f"https://{t.DOMAIN}/statements/"])
        from conftest_automation import rewrite_task_truth

        await rewrite_task_truth(store, "UPDATE browser_tasks SET scope_json = ? WHERE task_id = ?", (path_scope.to_json(), tid))
        before = await api._load_task(tid)
        await store.execute("UPDATE decisions SET status = 'APPROVED' WHERE id = ?", (decision_id,))
        await api._sync_waiting_owner_decision(before)
        after = await api._load_task(tid)
        states = {}
        for status, expires in (("REVOKED", None), ("CONSUMED", None), ("EXPIRED", None), ("ACTIVE", 1)):
            await store.execute("UPDATE browser_scope_authorizations SET status = ?, expires_at_ms = ? WHERE task_id = ?",
                                (status, expires, tid))
            states[(status, expires)] = await api._load_task(tid)
        # A delta naming a domain the task already declares does not lift its path limit.
        await store.execute("UPDATE browser_scope_authorizations SET status = 'ACTIVE', expires_at_ms = NULL WHERE task_id = ?", (tid,))
        await store.execute("UPDATE browser_escalations SET requested_scope_delta_json = ? WHERE task_id = ?",
                            (json.dumps({"allowed_domain": t.DOMAIN}), tid))
        same_host = await api._load_task(tid)
    assert [(e.origin, e.path_prefix) for e in same_host.scope.entries] == [(f"https://{t.DOMAIN}", "/statements/")]
    entries = [(e.origin, e.path_prefix) for e in after.scope.entries]
    assert entries == [(f"https://{t.DOMAIN}", "/statements/"), ("https://outside.example.net", None)]
    assert url_scope_violation(after.scope, f"https://{t.DOMAIN}/checkout/pay") == "TASK_SCOPE_PAGE_PATH_OUTSIDE"
    for key, task in states.items():
        assert [(e.origin, e.path_prefix) for e in task.scope.entries] == [(f"https://{t.DOMAIN}", "/statements/")], key


async def test_m3_harness_itself_refuses_an_out_of_scope_landing(chromium):
    """The Harness's own landing check (CDP frame URL), without the router or gateway."""
    _m, pw, harness = chromium
    _goto(pw, "/docs/onclick_out")
    described = await harness.describe(_task(), "#b")
    with harness_lease_fence(HarnessLeaseFence("public_research", _task().task_id, 1)):
        with pytest.raises(BrowserAdapterError) as landed:
            await harness.click(_task(), "#b", binding=described["binding"])
    # Unit G9c: the guard blocks the navigation (NAVIGATION_OUT_OF_SCOPE) before it lands.
    assert landed.value.code == "BROWSER_HARNESS_REFUSED" and landed.value.detail in (
        "TASK_SCOPE_LANDED_PATH_OUTSIDE", "NETWORK_WRITE_BLOCKED:NAVIGATION_OUT_OF_SCOPE")
    assert _url(pw) == "about:blank"


async def test_m3_gateway_checks_the_page_the_harness_reports():
    """Defence in depth: a Harness reply on an out-of-scope page is not a success."""
    from van_gateway.browser.interaction_router import RouterAction, RouterLane

    class _Harness:
        async def click(self, task, locator, *, binding=None):
            return {"url": f"https://{DOMAIN}/checkout/pay"}

    action = RouterAction(lane=RouterLane.DETERMINISTIC, operation="click", locator="#a", value_ref=None, action_class="A1")
    with pytest.raises(BrowserAdapterError) as landed:
        await HarnessActionExecutor(_Harness()).execute(_task(), action)
    assert landed.value.detail == "TASK_SCOPE_LANDED_PATH_OUTSIDE"


def test_m4_the_ledger_record_filters_whatever_reaches_reasons():
    from van_gateway.browser.interaction_router import RouterLane, StepResult

    result = StepResult(lane=RouterLane.OWNER_TAKEOVER, state=StepState.OWNER_TAKEOVER,
                        reasons=["DETERMINISTIC_TARGET_UNRESOLVED:TARGET_NOT_A_CONTROL:acct-0012345678",
                                 "POLICY_REFUSED:orchid.lane@example.org"])
    step = tr.step()
    record = json.dumps(RouterStepLedger._record_json(step, result, {}))
    assert "0012345678" not in record and "orchid" not in record
    assert "TARGET_NOT_A_CONTROL:OMITTED" in record


async def test_m3_the_page_script_itself_masks_the_name(chromium):
    """Before the sanitizer: what the in-page script returns already has the name masked."""
    module, pw, _harness = chromium
    _goto(pw, "/docs/token")
    raw = pw.call(lambda page, cdp: page.evaluate(module.elements_expression("list")))
    link = next(e for e in raw["elements"] if e["locator"] == "#a")
    assert link["name"] == "Code [REDACTED]" and "tok_9f8e7d6c5b4a" not in json.dumps(raw["elements"])


async def test_m3_verifier_never_verifies_a_page_outside_the_scope():
    from van_gateway.automation.verifier import PostconditionSpec, VerificationOutcome
    from van_gateway.browser.interaction_router import IndependentPostconditionVerifier, RouterAction, RouterLane

    class _Harness:
        def __init__(self, url):
            self.url = url

        async def page_info(self, task):
            return {"url": self.url, "title": "t", "extraction": {"visible_text": "ok"}}

    action = RouterAction(lane=RouterLane.DETERMINISTIC, operation="click", locator="#a", value_ref=None, action_class="A1")
    spec = PostconditionSpec(kind="READ_BACK", field="title", expected="t")
    inside = await IndependentPostconditionVerifier(_Harness(f"https://{DOMAIN}/docs/next")).verify(_task(), action, spec, claimed_done=False)
    outside = await IndependentPostconditionVerifier(_Harness(f"https://{DOMAIN}/checkout/pay")).verify(_task(), action, spec, claimed_done=False)
    assert inside.outcome is VerificationOutcome.VERIFIED, inside
    assert outside.outcome is VerificationOutcome.FAILED and outside.detail == "TASK_SCOPE_LANDED_PATH_OUTSIDE"
