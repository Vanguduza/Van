"""Review I4 — Browser Harness element reporting.

The live Harness ``page_info`` returned no ``elements``, so ``HarnessTargetResolver``
resolved nothing (every targeted Stagehand action went to owner takeover), lane 1 classified
on locator words alone and B2 denied every page. These tests pin the element shape, its
bounds and its redaction, first against a stubbed page and then, when a Chromium binary is
available, against real headless Chromium through the Harness worker's own HTTP handler.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import queue
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

import test_browser_interaction_router as tr
from van_gateway.browser.adapters import HttpBrowserHarnessAdapter
from van_gateway.browser.interaction_router import (
    HarnessTargetResolver,
    harness_page_to_jev_observation,
    resolve_stagehand_target,
)
from van_gateway.browser.jev_eligibility import EligibilityClass, classify_observation

ROOT = Path(__file__).resolve().parents[2]
HARNESS_SERVICE = ROOT / "deploy" / "van-browser-core" / "browser" / "harness_service.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
DOMAIN = "docs.example.com"
#: Every value the fixture page holds in a field, attribute, URL or storage. None may leave
#: the Harness in any form.
SECRETS = (
    "4111", "hunter2", "private memo", "tok_live", "csrf-secret",
    "s3cr3t", "abc123", "acct-1", "250.00", "SESSIONCOOKIE",
)
#: Field contents the browser also *renders* (a selected option's text, a contenteditable's
#: text). The pre-existing ``extraction.visible_text`` (watch observations) is rendered page
#: text and carries them; no element or session field may.
RENDERED_FIELD_TEXT = ("typed owner notes", "Savings 12345678")
ELEMENT_KEYS = {
    "locator", "locator_kind", "role", "name", "description", "attributes", "type",
    "autocomplete", "placeholder", "inputmode", "maxlength", "pattern", "hidden", "tag",
    "landmark", "disabled", "checked", "sensitive", "value_present",
    # Review I5 (unit G6a): what the element shows and does.
    "text", "media", "effective_type", "submits", "form", "frame",
}


def _load(monkeypatch, tmp_path):
    monkeypatch.setenv("VAN_HARNESS_STATE_ROOT", str(tmp_path / "harness-state"))
    spec = importlib.util.spec_from_file_location("van_harness_service_elements", HARNESS_SERVICE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def hs(monkeypatch, tmp_path):
    return _load(monkeypatch, tmp_path)


def _task():
    return tr._task().model_copy(update={"profile_alias": "public_research", "target_domain": DOMAIN})


def _exec_script(script: str, namespace: dict[str, Any], extra: dict[str, str] | None = None) -> Any:
    """Run a Harness script the way browser-harness does: helpers in globals, JSON on stdout."""
    saved = {k: os.environ.get(k) for k in (extra or {})}
    os.environ.update(extra or {})
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            exec(compile(script, "<harness-script>", "exec"), dict(namespace))  # noqa: S102 - the fixed Harness script
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    for line in reversed(out.getvalue().splitlines()):
        if line.startswith("__VAN_JSON__"):
            return json.loads(line[len("__VAN_JSON__"):])
    raise AssertionError("script printed no result")


# ------------------------------------------------------------------ stubbed page


def _raw(i: int, **kw: Any) -> dict[str, Any]:
    base = {
        "locator": f"#e{i}", "locator_kind": "id", "role": "button", "name": f"Button {i}",
        "description": "", "attributes": {"id": f"e{i}"}, "type": "", "autocomplete": "",
        "placeholder": "", "inputmode": "", "maxlength": None, "pattern": "", "hidden": False,
        "tag": "button", "landmark": False, "disabled": False, "checked": None,
        "sensitive": False, "value_present": False,
    }
    base.update(kw)
    return base


def test_shape_bounds_the_list_and_never_carries_a_value(hs):
    hostile = [
        _raw(0, type="password", value="hunter2", attributes={
            "id": "pw", "value": "hunter2", "onclick": "steal()", "style": "x",
            "data-session-token": "tok_live_1", "data-kind": "login"}),
        # Words, not one 10,000-character run: a token-like run is masked (review I6 m3).
        _raw(1, name="Nn " * 5_000, autocomplete="cc-number", value="4111111111111111"),
        _raw(2, hidden="yes"),  # not a real bool: unknown visibility is hidden
        {"locator": "", "role": "button"},  # no locator: dropped
        "not-an-element",
    ] + [_raw(i) for i in range(3, 400)]
    result = hs.shape_page_info({"url": f"https://{DOMAIN}/", "title": "t",
                                 "__van_snapshot__": {"elements": hostile, "storage_entries": 0,
                                                      "indexeddb_databases": 0},
                                 "__van_cookies__": False})
    elements = result["elements"]
    assert len(elements) <= hs.MAX_ELEMENTS and result["elements_truncated"] is True
    assert len(json.dumps(elements, separators=(",", ":"))) <= hs.MAX_ELEMENTS_BYTES
    assert all(set(e) == ELEMENT_KEYS for e in elements)
    blob = json.dumps(result)
    assert "hunter2" not in blob and "4111" not in blob and "tok_live" not in blob and "steal()" not in blob
    pw, card, unknown = elements[0], elements[1], elements[2]
    assert pw["sensitive"] is True and pw["attributes"] == {
        "id": "pw", "data-session-token": "[REDACTED]", "data-kind": "login"}
    assert card["sensitive"] is True and len(card["name"]) == hs.MAX_ELEMENT_TEXT
    assert unknown["hidden"] is True
    assert "__van_snapshot__" not in result and "__van_cookies__" not in result


def test_both_bounds_hold(hs):
    small, truncated = hs.sanitize_elements([{"locator": f"#e{i}", "hidden": False} for i in range(400)])
    assert (len(small), truncated) == (hs.MAX_ELEMENTS, True)  # the count bound
    big, truncated = hs.sanitize_elements(
        [{"locator": f"#e{i}", "name": "x " * 500, "description": "y " * 500, "hidden": False} for i in range(400)])
    assert truncated and len(big) < hs.MAX_ELEMENTS  # the size bound, first
    assert len(json.dumps(big, separators=(",", ":"))) <= hs.MAX_ELEMENTS_BYTES


@pytest.mark.parametrize("snapshot,identity,cookies,expected", [
    ({"sign_out_control": False, "storage_entries": 0, "indexeddb_databases": 0}, "", False, (False, False, "NO_SESSION_STATE")),
    ({"sign_out_control": False, "storage_entries": 0, "indexeddb_databases": 0}, "owner@x", False, (True, False, "IDENTITY_MARKER")),
    ({"sign_out_control": True, "storage_entries": 0, "indexeddb_databases": 0}, "", False, (True, False, "SIGN_OUT_CONTROL")),
    ({"sign_out_control": False, "storage_entries": 0, "indexeddb_databases": 0}, "", True, (None, True, "UNKNOWN")),
    ({"sign_out_control": False, "storage_entries": 2, "indexeddb_databases": 0}, "", False, (None, False, "UNKNOWN")),
    # IndexedDB not enumerable (older engine): login state is not knowable, so unknown.
    ({"sign_out_control": False, "storage_entries": 0, "indexeddb_databases": None}, "", False, (None, False, "UNKNOWN")),
    ({"sign_out_control": False, "storage_entries": 0, "indexeddb_databases": 0, "document_cookie_present": True}, "", None, (None, True, "UNKNOWN")),
    ({"sign_out_control": False, "storage_entries": 0, "indexeddb_databases": 0}, "", None, (None, None, "UNKNOWN")),
])
def test_login_state_is_true_false_or_unknown_never_a_guess(hs, snapshot, identity, cookies, expected):
    facts = hs.session_facts(snapshot, identity, cookies)
    assert (facts["authenticated"], facts["cookies_present"], facts["authentication_basis"]) == expected


def test_page_info_script_reports_cookie_presence_not_contents(hs):
    """The fixed page_info script, run against a stubbed page and CDP."""
    snapshot = {"elements": [_raw(1)], "sign_out_control": False, "storage_entries": 0,
                "indexeddb_databases": 0, "document_cookie_present": False}
    seen: list[str] = []

    def js(expr):
        seen.append(expr)
        return snapshot if "elements_total" in expr else ""

    calls: list[tuple[str, dict]] = []

    def cdp(method, **params):
        # Review I5 E2 — cookies for the whole site and storage counts come from CDP.
        calls.append((method, params))
        if method == "Network.getAllCookies":
            return {"cookies": [{"name": "sid", "value": "SESSIONCOOKIE", "domain": DOMAIN, "path": "/app", "httpOnly": True}]}
        if method == "DOMStorage.getDOMStorageItems":
            assert params["storageId"]["securityOrigin"] == f"https://{DOMAIN}"
            return {"entries": []}
        if method == "IndexedDB.requestDatabaseNames":
            return {"databaseNames": []}
        if method == "Storage.getUsageAndQuota":
            return {"usage": 0, "quota": 1}
        raise AssertionError(method)

    raw = _exec_script(hs.PAGE_INFO_SCRIPT, {
        "page_info": lambda: {"url": f"https://{DOMAIN}/", "title": "Docs"}, "js": js, "cdp": cdp})
    result = hs.shape_page_info(raw)
    assert "SESSIONCOOKIE" not in json.dumps(result)
    assert (result["cookies_present"], result["authenticated"]) == (True, None)
    assert [e["locator"] for e in result["elements"]] == ["#e1"]
    assert [m for m, _p in calls] == ["Network.getAllCookies", "DOMStorage.getDOMStorageItems",
                                      "DOMStorage.getDOMStorageItems", "IndexedDB.requestDatabaseNames",
                                      "Storage.getUsageAndQuota"]
    # The in-page element expression is the module's own, not something assembled per call.
    assert hs.elements_expression("list") in seen


def test_a_native_dialog_reports_no_elements_and_unknown_login(hs):
    raw = _exec_script(hs.PAGE_INFO_SCRIPT, {
        "page_info": lambda: {"dialog": {"type": "alert"}},
        "js": lambda e: pytest.fail("the page JS thread is frozen under a dialog"),
        "cdp": lambda *a, **k: pytest.fail("no CDP under a dialog")})
    result = hs.shape_page_info(raw)
    assert result["elements"] == [] and result["authenticated"] is None and result["cookies_present"] is None


class _Harness:
    def __init__(self, elements, described=None):
        self.elements, self.described, self.describe_calls = elements, described, []

    async def page_info(self, task):
        return {"url": f"https://{DOMAIN}/", "elements": self.elements}

    async def describe(self, task, locator):
        self.describe_calls.append(locator)
        return {"element": self.described, "binding": getattr(self, "binding", None), "url": f"https://{DOMAIN}/"}


_describe = _Harness.describe


async def test_resolver_always_describes_and_carries_the_binding():
    """Review I5 MAJOR-2: the page_info list carries no binding, so the resolver always goes
    through /describe (the element classified must be the node acted on)."""
    listed = _raw(1, locator="#pay", name="Pay now")
    harness = _Harness([listed], described=_raw(9, locator="main > button:nth-of-type(3)", name="Read more"))
    harness.binding = {"backend_node_id": 12, "digest": "a" * 64}
    resolver = HarnessTargetResolver(harness)
    assert await resolver(_task(), "#pay") is None  # describe reported another locator
    assert harness.describe_calls == ["#pay"]
    found = await resolver(_task(), "main > button:nth-of-type(3)")
    assert found["name"] == "Read more" and harness.describe_calls[-1] == "main > button:nth-of-type(3)"
    assert found["binding"] == {"backend_node_id": 12, "digest": "a" * 64}
    assert found["page_url"] == f"https://{DOMAIN}/"
    # A Harness without /describe: the listed element is found but carries no binding, which
    # the task-scope gate refuses to act on.
    del _Harness.describe
    try:
        unbound = await HarnessTargetResolver(_Harness([listed]))(_task(), "#pay")
    finally:
        _Harness.describe = _describe
    assert unbound is listed and "binding" not in unbound
    # describe echoing another locator is not this target.
    harness.described = _raw(9, locator="#other")
    assert await resolver(_task(), "#missing") is None
    harness.described = None
    assert await resolver(_task(), "#missing") is None
    hidden = HarnessTargetResolver(_Harness([], described=_raw(2, locator="#ghost", hidden=True)))
    assert await resolve_stagehand_target(hidden, _task(), "#ghost") == "TARGET_HIDDEN"


def test_b2_observation_reads_the_harness_shape():
    page = {"url": f"https://{DOMAIN}/", "title": "Docs", "authenticated": False, "cookies_present": False,
            "elements": [
                _raw(1, locator="#q", role="searchbox", name="Search docs", type="search", tag="input",
                     value_present=True, attributes={"aria-label": "Search", "title": "Find"}),
                _raw(2, locator="#go", name="Go", type="submit", tag="button"),
            ]}
    obs = harness_page_to_jev_observation(page, profile_alias="public_research")
    q, go = obs.elements
    assert (q.ref, q.role, q.label, q.aria_label, q.title, q.input_type) == ("#q", "searchbox", "Search docs", "Search", "Find", "search")
    assert q.value == "[REDACTED]"  # value_present: B2 sees owner input without its content
    assert (go.ref, go.label, go.input_type) == ("#go", "Go", "")  # a <button type=submit> is no input
    assert (obs.authenticated, obs.cookies_present) == (False, False)
    # Legacy ``ref``/``label`` entries still map; missing visibility is hidden.
    legacy = harness_page_to_jev_observation({"elements": [{"ref": "#a", "role": "link", "label": "A"}]},
                                             profile_alias="public_research")
    assert legacy.elements[0].ref == "#a" and legacy.elements[0].hidden is True


# ------------------------------------------------------------------ real Chromium

CHROMIUM_CANDIDATES = (
    os.environ.get("VAN_TEST_CHROMIUM", ""),
    "/opt/pw-browsers/chromium",
    "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
)


def _chromium() -> str | None:
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        return None
    for path in CHROMIUM_CANDIDATES:
        if path and Path(path).is_file():
            return path
    return None


def _guard_flags() -> tuple[str, ...]:
    """The Chromium flags the Harness worker launches with for its network-effect guard."""
    import re

    source = HARNESS_SERVICE.read_text(encoding="utf-8")
    block = re.search(r"NETWORK_GUARD_CHROMIUM_FLAGS = \((.*?)\)", source, re.S)
    return tuple(re.findall(r'"(--[^"]+)"', block.group(1))) if block else ()


def _free_port() -> int:
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _PlaywrightPage:
    """One headless Chromium page on its own thread (Playwright's sync API is thread-bound),
    serving the fixture pages at https://docs.example.com/ through request interception.

    Unit G9c (network-effect guard): the Harness's fixed scripts need browser-harness's
    event stream (``drain_events``) and browser-level ``Target.*`` calls, which a Playwright
    CDP session cannot give. So Chromium also listens on a DevTools port, the scripts run on
    the caller's thread with the helper surface of ``cdp_harness_kit.HarnessSession`` over
    that port (``guarded_run_harness``), and this thread keeps servicing Playwright's route
    handlers while it waits for jobs (``_serve_jobs``)."""

    def launch_args(self) -> list[str]:
        self.debug_port = _free_port()
        return [f"--remote-debugging-port={self.debug_port}", *_guard_flags()]

    def _serve_jobs(self, page, cdp) -> None:
        while True:
            try:
                job = self.jobs.get_nowait()
            except queue.Empty:
                page.wait_for_timeout(5)  # services route handlers while idle
                continue
            if job is None:
                break
            fn, box, done = job
            try:
                box["value"] = fn(page, cdp)
            except BaseException as exc:  # noqa: BLE001 - handed back to the caller
                box["error"] = exc
            done.set()

    def harness_session(self):
        import urllib.request

        import cdp_harness_kit as kit

        if getattr(self, "_session", None) is None:
            with urllib.request.urlopen(f"http://127.0.0.1:{self.debug_port}/json/version", timeout=10) as r:
                self._session = kit.HarnessSession(json.loads(r.read())["webSocketDebuggerUrl"])
            # These fixtures were written against Playwright's mouse.click, which moves the
            # pointer to the point before pressing (the I5 race page reacts to that).
            self._session.move_before_click = True
        return self._session

    def __init__(self, executable: str) -> None:
        self._session = None
        self.jobs: queue.Queue = queue.Queue()
        self.ready = threading.Event()
        self.error: BaseException | None = None
        self.thread = threading.Thread(target=self._run, args=(executable,), daemon=True)
        self.thread.start()
        self.ready.wait(60)
        if self.error:
            raise self.error

    def _run(self, executable: str) -> None:
        from playwright.sync_api import sync_playwright

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path=executable, args=self.launch_args())
                page = browser.new_page()
                pages = {"/pay": (FIXTURES / "harness_elements.html").read_text(encoding="utf-8"),
                         "/docs": (FIXTURES / "harness_elements_benign.html").read_text(encoding="utf-8")}

                def serve(route):
                    path = "/" + route.request.url.split("/", 3)[-1].split("?")[0]
                    body = pages.get(path)
                    route.fulfill(status=200 if body else 404, content_type="text/html", body=body or "missing")

                page.route(f"https://{DOMAIN}/**", serve)
                cdp = page.context.new_cdp_session(page)
                self.page, self.cdp = page, cdp
                self.ready.set()
                self._serve_jobs(page, cdp)
                browser.close()
        except BaseException as exc:  # noqa: BLE001
            self.error = exc
            self.ready.set()

    def call(self, fn):
        box: dict[str, Any] = {}
        done = threading.Event()
        self.jobs.put((fn, box, done))
        assert done.wait(60), "Chromium call timed out"
        if "error" in box:
            raise box["error"]
        return box.get("value")

    def close(self):
        if self._session is not None:
            self._session.close()
        self.jobs.put(None)
        self.thread.join(30)


def guarded_run_harness(pw: _PlaywrightPage):
    """``run_harness`` for a Harness module under test: the fixed script runs on the calling
    thread with browser-harness's helper surface (``cdp_harness_kit``) on ``pw``'s page."""
    import cdp_harness_kit as kit

    lock = threading.Lock()

    def run_harness(alias, script, extra=None):
        with lock:
            return kit.exec_script(pw.harness_session(), script, extra)

    return run_harness


@pytest.fixture
def chromium_harness(monkeypatch, tmp_path):
    """The real Harness worker HTTP handler whose browser-harness child is replaced by the
    same fixed scripts run against real headless Chromium (js -> Runtime evaluation, cdp ->
    a CDP session on the page)."""
    executable = _chromium()
    if executable is None:
        pytest.skip("no Chromium/Playwright available for the real-browser element test")
    module = _load(monkeypatch, tmp_path)
    pw = _PlaywrightPage(executable)

    monkeypatch.setattr(module, "run_harness", guarded_run_harness(pw))
    server = ThreadingHTTPServer(("127.0.0.1", 0), module.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield module, pw, HttpBrowserHarnessAdapter(None, base_url=f"http://127.0.0.1:{server.server_address[1]}", enabled=True)
    finally:
        server.shutdown()
        server.server_close()
        pw.close()


def _by_locator(elements):
    return {e["locator"]: e for e in elements}


async def test_real_chromium_reports_roles_names_attributes_and_redacts(chromium_harness):
    module, pw, harness = chromium_harness
    pw.call(lambda page, cdp: page.goto(f"https://{DOMAIN}/pay"))
    pw.call(lambda page, cdp: page.evaluate("localStorage.setItem('k','SESSIONCOOKIE')"))
    info = await harness.page_info(_task())
    blob = json.dumps(info)
    for secret in SECRETS:
        assert secret not in blob, secret
    outside_visible_text = json.dumps({k: v for k, v in info.items() if k != "extraction"})
    for rendered in RENDERED_FIELD_TEXT:
        assert rendered not in outside_visible_text, rendered
    els = _by_locator(info["elements"])
    assert all(set(e) == ELEMENT_KEYS for e in info["elements"])

    card, pw_field, cvc = els["#card"], els["#pw"], els['input[name="cvc"]']
    assert (card["role"], card["name"], card["autocomplete"], card["inputmode"], card["maxlength"], card["pattern"]) == (
        "textbox", "Card number", "cc-number", "numeric", 19, "[0-9 ]*")
    assert card["sensitive"] and card["value_present"] and card["attributes"] == {"id": "card", "name": "cardnumber"}
    assert (pw_field["type"], pw_field["name"], pw_field["sensitive"], pw_field["value_present"]) == ("password", "Password", True, True)
    assert (cvc["name"], cvc["sensitive"]) == ("CVC", True)

    pay, transfer = els["#pay"], els['input[name="transfer"]']
    assert (pay["role"], pay["name"], pay["description"], pay["type"]) == (
        "button", "Pay now", "You will be charged immediately", "submit")
    assert (transfer["role"], transfer["name"]) == ("button", "Transfer funds")
    amount = els['input[name="amount"]']
    assert amount["name"] == "Amount to transfer" and amount["value_present"] is True
    assert amount["attributes"]["data-account-token"] == "[REDACTED]" and amount["attributes"]["data-kind"] == "money"
    docs = els['a[data-testid="docs-link"]']
    assert (docs["role"], docs["name"], docs["attributes"]["href"]) == ("link", "Docs", f"https://{DOMAIN}/docs?page&token")
    assert els["#payment"]["attributes"]["action"] == f"https://{DOMAIN}/checkout/pay?session"
    assert els["#payment"]["landmark"] is True and els["#payment"]["role"] == "form"
    assert els['button[data-testid="next"]']["name"] == "Next page"
    assert els["#agree"]["checked"] is True and els["#agree"]["name"] == "I agree"
    assert els["#ghost"]["hidden"] is True and els["#ghost2"]["hidden"] is True
    assert not any(e["attributes"].get("name") == "csrf" for e in info["elements"])  # type=hidden is not interactive
    roles = {e["role"] for e in info["elements"] if e["landmark"]}
    assert {"navigation", "main", "form", "banner", "contentinfo"} <= roles
    # A visible "Log out" control is positive sign-in evidence; storage is reported as a count only.
    assert info["authenticated"] is True and info["authentication_basis"] == "SIGN_OUT_CONTROL"

    # Every locator is one the Harness executes back: it selects exactly that element.
    counts = pw.call(lambda page, cdp: page.evaluate(
        "(ls) => ls.map((l) => document.querySelectorAll(l).length)", [e["locator"] for e in info["elements"]]))
    assert counts == [1] * len(info["elements"])

    # describe: a target the list omitted, reported under the locator exactly as given.
    described = await harness.describe(_task(), "main > button:nth-of-type(3)")
    assert described["element"]["locator"] == "main > button:nth-of-type(3)"
    assert (described["element"]["role"], described["element"]["name"], described["matches"]) == ("button", "Read more", 1)
    pwd = await harness.describe(_task(), "#pw")
    assert pwd["element"]["sensitive"] is True and "hunter2" not in json.dumps(pwd)

    # The gateway resolver and B2 now see real elements.
    resolver = HarnessTargetResolver(harness)
    assert (await resolver(_task(), "#pay"))["name"] == "Pay now"
    assert (await resolver(_task(), "main > button:nth-of-type(2)"))["name"] == "Read more"
    obs = harness_page_to_jev_observation(info, profile_alias="public_research")
    verdict = classify_observation(obs, action_class_ceiling="A2", closed_operation_set=["click"])
    assert verdict.eligibility_class is EligibilityClass.CREDENTIAL
    assert "CREDENTIAL_FIELD" in verdict.reasons and "CREDENTIAL_PAYMENT_CONTROL" in verdict.reasons


async def test_real_chromium_benign_public_page_is_classifiable(chromium_harness):
    _module, pw, harness = chromium_harness
    pw.call(lambda page, cdp: page.context.clear_cookies())
    pw.call(lambda page, cdp: page.goto(f"https://{DOMAIN}/docs"))
    info = await harness.page_info(_task())
    assert (info["authenticated"], info["cookies_present"], info["authentication_basis"]) == (False, False, "NO_SESSION_STATE")
    els = _by_locator(info["elements"])
    assert els["#install"]["name"] == "Install guide" and els['input[name="q"]']["role"] == "searchbox"
    obs = harness_page_to_jev_observation(info, profile_alias="public_research")
    verdict = classify_observation(obs, action_class_ceiling="A2", closed_operation_set=["click"])
    # B2 can now classify a real page on its facts instead of denying it for want of targets.
    assert "AMBIGUOUS_NO_TARGETS" not in verdict.reasons
    assert "OWNER_AUTHENTICATED_SESSION" not in verdict.reasons
    # A cookie set by the page flips cookies_present (presence only), and B2 then treats it as a session.
    pw.call(lambda page, cdp: page.context.add_cookies([{"name": "sid", "value": "SESSIONCOOKIE", "url": f"https://{DOMAIN}/"}]))
    again = await harness.page_info(_task())
    assert (again["cookies_present"], again["authenticated"]) == (True, None)
    assert "SESSIONCOOKIE" not in json.dumps(again)


async def test_real_chromium_in_page_snapshot_is_already_redacted(chromium_harness):
    """Both layers redact on their own: the in-page script (what leaves Chromium) and the
    worker's sanitizer (which does not trust the page). This checks the in-page layer alone."""
    module, pw, _harness = chromium_harness
    pw.call(lambda page, cdp: page.goto(f"https://{DOMAIN}/pay"))
    raw = pw.call(lambda page, cdp: page.evaluate(module.elements_expression("list")))
    blob = json.dumps(raw["elements"])
    for secret in SECRETS:
        assert secret not in blob, secret
    assert all("value" not in e for e in raw["elements"])
    amount = next(e for e in raw["elements"] if e["attributes"].get("name") == "amount")
    assert amount["attributes"]["data-account-token"] == "[REDACTED]"


_CLICK_LOG = """document.addEventListener('click', (e) => {
  (window.__vanClicks = window.__vanClicks || []).push(e.target.id || e.target.getAttribute('data-testid') || e.target.textContent);
  e.preventDefault();
}, true); true"""


async def _route_on_real_page(pw, harness, **step_kw):
    """One router step against the real fixture page, the Harness resolving and executing."""
    from van_gateway.browser.adapters import HarnessLeaseFence, harness_lease_fence
    from van_gateway.browser.interaction_router import HarnessActionExecutor

    pw.call(lambda page, cdp: page.goto(f"https://{DOMAIN}/pay"))
    pw.call(lambda page, cdp: page.evaluate(_CLICK_LOG))
    router = tr.make_router(
        target_resolver=HarnessTargetResolver(harness), executor=HarnessActionExecutor(harness),
        semantic_fallback=step_kw.pop("stagehand", tr.FakeStagehand(None)),
        # Lane 2 off: this test is about lanes 1 and 3 on the Harness-resolved element.
        jev_client=None,
    )
    step = tr.step(**step_kw)
    step.task = _task()
    with harness_lease_fence(HarnessLeaseFence("public_research", step.task.task_id, 1)):
        result = await router.route(step)
    clicks = pw.call(lambda page, cdp: page.evaluate("window.__vanClicks || []"))
    return result, clicks


def _det(locator):
    from van_gateway.browser.interaction_router import DeterministicAction

    return DeterministicAction(operation="click", locator=locator)


def _stagehand(locator, description):
    from van_gateway.browser.interaction_router import RouterAction, RouterLane

    return tr.FakeStagehand(RouterAction(
        lane=RouterLane.STAGEHAND, operation="click", locator=locator, value_ref=None, action_class=None,
        semantic_action={"method": "click", "description": description}, description=description))


async def test_real_page_benign_click_resolves_and_executes_pay_goes_to_takeover(chromium_harness):
    """End to end (integrator request): with real page_info elements, a resolved benign click
    executes through the Harness on the real page, and a resolved pay control never does."""
    _module, pw, harness = chromium_harness
    next_page = 'button[data-testid="next"]'

    ok, clicks = await _route_on_real_page(pw, harness, deterministic_action=_det(next_page))
    assert ok.state.value == "VERIFIED_SUCCESS", ok.reasons
    assert clicks == ["next"]

    ok, clicks = await _route_on_real_page(pw, harness, stagehand=_stagehand(next_page, "Next page"))
    assert ok.state.value == "VERIFIED_SUCCESS", ok.reasons
    assert clicks == ["next"]

    # "#pay" reads as a neutral locator; the Harness-reported element is the "Pay now" submit.
    for kw in ({"deterministic_action": _det("#pay")}, {"stagehand": _stagehand("#pay", "Continue")}):
        pay, clicks = await _route_on_real_page(pw, harness, **kw)
        assert pay.state.value in ("OWNER_TAKEOVER", "POLICY_REFUSED"), (kw, pay.state, pay.reasons)
        assert clicks == [], kw
