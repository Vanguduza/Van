"""Review I5 E1, E2 — element-report value leaks and login-state facts.

Before (probe review-i5/probes/test_i5_report.py at fbe5502e):

* E1 — data-* attributes mirroring field values (data-value, data-pan, data-cc, data-state)
  carried card numbers and a typed password; a reset token in an href path was reported.
* E2 — ``authenticated`` was False (NO_SESSION_STATE) with a session cookie scoped to
  another path, an SSO cookie on a sibling host, or a page overriding
  ``Storage.prototype.length`` to hide a JWT in localStorage.
"""

from __future__ import annotations

import json

import pytest

import test_harness_elements as he
from test_harness_elements import chromium_harness, hs  # noqa: F401

DOMAIN = he.DOMAIN
LEAK = (
    '<form><input id="c1" name="field1" value="4111111111111111" data-value="4111111111111111">'
    '<input id="c2" data-pan="5500000000000004" data-cc="4000056655665556" data-kind="money" data-step="2" value="x">'
    '<input id="c3" aria-label="Notes" data-state="" value="">'
    '<a id="reset" href="https://docs.example.com/reset/tok_9f8e7d6c5b4a/confirm?code=1">Reset</a>'
    '<a id="plain" href="https://docs.example.com/help/billing/faq?page=2">Help</a>'
    '<button id="b" title="Card 4242 4242 4242 4242">Use saved card</button>'
    '<input type="hidden" name="csrf" value="csrf-hidden-9x8y7z">'
    '<input id="user" aria-label="Username" value="orchid-lane"><a id="me" href="/u/orchid-lane/edit">Me</a>'
    '<button id="m" data-ref="csrf-hidden-9x8y7z">Mirror</button>'
    '</form><script>document.getElementById("c3").addEventListener("input",e=>e.target.dataset.state=e.target.value)</script>'
)
SECRETS = ("4111111111111111", "5500000000000004", "4000056655665556", "hunter2-typed",
           "tok_9f8e7d6c5b4a", "4242 4242", "csrf-hidden-9x8y7z")


def _serve(page, path, body):
    page.route(f"https://{DOMAIN}{path}", lambda route: route.fulfill(status=200, content_type="text/html", body=body))


async def test_real_chromium_redacts_mirrored_values_and_url_tokens(chromium_harness):
    _m, pw, harness = chromium_harness
    pw.call(lambda page, cdp: _serve(page, "/leak", LEAK))
    pw.call(lambda page, cdp: page.goto(f"https://{DOMAIN}/leak"))
    pw.call(lambda page, cdp: page.fill("#c3", "hunter2-typed"))  # the page mirrors it into data-state
    info = await harness.page_info(he._task())
    described = [await harness.describe(he._task(), loc) for loc in ("#c1", "#c2", "#c3", "#reset", "#b", "#m")]
    blob = json.dumps(info["elements"]) + json.dumps(described)
    for secret in SECRETS:
        assert secret not in blob, secret
    els = he._by_locator(info["elements"])
    assert els["#c1"]["attributes"]["data-value"] == "[REDACTED]"
    assert els["#c2"]["attributes"] == {"id": "c2", "data-pan": "[REDACTED]", "data-cc": "[REDACTED]",
                                        "data-kind": "money", "data-step": "2"}
    assert els["#c3"]["attributes"]["data-state"] == "[REDACTED]"
    assert els["#m"]["attributes"]["data-ref"] == "[REDACTED]"  # equals a hidden field's value
    assert els["#reset"]["attributes"]["href"] == f"https://{DOMAIN}/reset/[REDACTED]/confirm?code"
    assert els["#plain"]["attributes"]["href"] == f"https://{DOMAIN}/help/billing/faq?page"
    # Only the page script knows field values: a path segment equal to one is redacted there.
    assert els["#me"]["attributes"]["href"] == f"https://{DOMAIN}/u/[REDACTED]/edit"
    assert els["#b"]["attributes"]["title"] == "[REDACTED]" and els["#b"]["name"] == "Use saved card"


def test_the_python_sanitizer_redacts_what_a_hostile_page_script_reports(hs):
    raw = he._raw(1, description="Card 4242 4242 4242 4242 on file", attributes={
        "id": "e1", "data-value": "4111111111111111", "data-ssn": "078-05-1120", "data-ref": "tok_9f8e7d6c5b4a",
        "data-jwt": "eyJhbGciOiJIUzI1NiJ9abcdefghijklmnopqrstuvwxyz", "data-kind": "money", "data-step": "2",
        "href": "https://user:pw@docs.example.com/reset/tok_9f8e7d6c5b4a/confirm?code=123456#frag",
        "action": "https://docs.example.com/orders/1234567/pay?id=99", "formaction": "javascript:steal(4111111111111111)",
        "title": "Account 12345678", "aria-label": "Pay 500 now",
    })
    element = hs.sanitize_element(raw)
    blob = json.dumps(element)
    for secret in ("4111", "078-05", "tok_9f8e", "eyJhbGci", "4242", "12345678", "1234567", "123456", "pw@", "frag", "steal"):
        assert secret not in blob, secret
    a = element["attributes"]
    assert a["href"] == "https://docs.example.com/reset/[REDACTED]/confirm?code"
    assert a["action"] == "https://docs.example.com/orders/[REDACTED]/pay?id"
    assert a["formaction"] == "javascript:"
    assert (a["data-kind"], a["data-step"], a["aria-label"]) == ("money", "2", "Pay 500 now")
    assert element["description"] == "Card [REDACTED] on file"


async def test_real_chromium_login_state_is_unknown_with_any_site_state(chromium_harness):
    _m, pw, harness = chromium_harness
    pw.call(lambda page, cdp: _serve(page, "/public", '<a href="/x">Public page</a>'))

    def reset(page, cdp):
        page.context.clear_cookies()
        page.goto(f"https://{DOMAIN}/public")
        page.evaluate("localStorage.clear(); sessionStorage.clear(); true")

    async def facts():
        info = await harness.page_info(he._task())
        return info["authenticated"], info["cookies_present"], info["authentication_basis"]

    pw.call(reset)
    assert await facts() == (False, False, "NO_SESSION_STATE")
    # A cookie for an unrelated site is not this site's session.
    pw.call(lambda page, cdp: page.context.add_cookies([{"name": "x", "value": "1", "domain": "other.org", "path": "/"}]))
    assert await facts() == (False, False, "NO_SESSION_STATE")

    pw.call(reset)
    pw.call(lambda page, cdp: page.context.add_cookies([{"name": "sid", "value": "S", "domain": DOMAIN, "path": "/app",
                                                          "httpOnly": True, "secure": True}]))
    assert await facts() == (None, True, "UNKNOWN")

    pw.call(reset)
    pw.call(lambda page, cdp: page.context.add_cookies([{"name": "sso", "value": "S", "domain": "auth.example.com", "path": "/"}]))
    assert await facts() == (None, True, "UNKNOWN")

    pw.call(reset)
    pw.call(lambda page, cdp: page.evaluate(
        "localStorage.setItem('jwt','eyJ'); Object.defineProperty(Storage.prototype,'length',{get(){return 0}});"
        "indexedDB.databases=async()=>[]; true"))
    assert await facts() == (None, False, "UNKNOWN")


@pytest.mark.parametrize("usage,expected", [(0, (False, "NO_SESSION_STATE")), (512, (None, "UNKNOWN")),
                                            (None, (None, "UNKNOWN"))])
def test_other_origin_storage_or_an_unreadable_count_is_unknown(hs, usage, expected):
    snap = {"sign_out_control": False, "storage_entries": 0, "indexeddb_databases": 0, "storage_usage_bytes": usage}
    facts = hs.session_facts(snap, "", False)
    assert (facts["authenticated"], facts["authentication_basis"]) == expected
