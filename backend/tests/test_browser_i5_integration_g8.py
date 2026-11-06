"""Integration G8 — unit G6b's review-I5 hardening applied to unit G6a's new surface.

G6b (F1 profile lock, F3 fence MAC, E1 redaction) and G6a (task scope, CDP node binding,
bound click/press/fill, text/media/form/effective_type) were built side by side on ff1c3066.
These tests hold the combination:

* E1 x G6a — ``text``, ``media``, the form owner (``action``/``formaction``/names) and
  ``effective_type`` are redacted, in the page script and again by the Python sanitizer, and a
  redacted text/media/form entry makes the target A4 (``R11_REDACTED_CONTENT``) so a mask can
  never hide a risk word from the classifier;
* F3 x G6a — the fence MAC is sent on the bound click/press/fill and on fenced describes, and
  a keyed Harness refuses the bound operations without it;
* F1 x G6a — the Harness profile lock covers the bound click: a newer generation is not
  admitted while the bound click is running.
"""

from __future__ import annotations

import json
import threading
import time

import httpx
import pytest

import test_browser_interaction_router as tr
import test_harness_elements as he
from test_browser_api import _settings  # noqa: F401 - autouse: the API settings the routes need
from test_browser_review_i5_task_scope import _goto, _lane4, _route, _seen, _task, _det, chromium  # noqa: F401
from test_harness_elements import hs  # noqa: F401
from van_gateway.browser.action_risk import assess_action, redacted_content
from van_gateway.browser.adapters import (
    BrowserAdapterError,
    HarnessLeaseFence,
    HttpBrowserHarnessAdapter,
    harness_fence_mac,
    harness_lease_fence,
)
from van_gateway.browser.interaction_router import StepState

KEY = b"g8" * 16 + b"0123456789abcdef"
SECRETS = ("4111 1111", "4111111111111111", "5500000000000004", "tok_9f8e7d6c5b4a",
           "hunter2-typed-x", "ROLETEXT-secret-value", "OUTVAL-777")
#: Plain ``id``/``name``/``class`` attribute values are reported verbatim (G6b E1 left them
#: out of scope); the form owner's name that G6a added is masked.
FORM_NAME_SECRET = "12345678"


# ------------------------------------------------------------------ E1 x G6a: redaction


def test_the_python_sanitizer_redacts_the_g6a_fields(hs):
    raw = he._raw(
        1, text="Pay 4111 1111 1111 1111 now", media=["Card 4242424242424242", "tok_9f8e7d6c5b4a.png", "arrow"],
        effective_type="4111111111111111", submits=True,
        form={"action": "https://docs.example.com/reset/tok_9f8e7d6c5b4a/confirm?code=123456",
              "formaction": "javascript:steal(4111111111111111)", "method": "POST",
              "formmethod": "tok_9f8e7d6c5b4a", "target": "_blank", "id": "acct-12345678", "name": "checkout"},
    )
    element = hs.sanitize_element(raw)
    blob = json.dumps(element)
    for secret in ("4111", "4242", "tok_9f8e", "12345678", "123456", "steal"):
        assert secret not in blob, secret
    assert element["text"] == "Pay [REDACTED] now"
    assert element["media"] == ["Card [REDACTED]", "[REDACTED]", "arrow"]
    assert element["effective_type"] == ""
    assert element["form"] == {
        "action": "https://docs.example.com/reset/[REDACTED]/confirm?code", "formaction": "javascript:",
        "method": "post", "formmethod": "other", "target": "_blank", "id": "acct-[REDACTED]", "name": "checkout",
    }
    # Benign values pass through unchanged.
    plain = hs.sanitize_element(he._raw(2, text="Show more", media=["chevron.svg"], effective_type="submit",
                                        form={"action": "https://docs.example.com/i5/search?q=x", "method": "get"}))
    assert (plain["text"], plain["media"], plain["effective_type"]) == ("Show more", ["chevron.svg"], "submit")
    assert plain["form"]["action"] == "https://docs.example.com/i5/search?q" and plain["form"]["method"] == "get"


def test_a_redacted_text_media_or_form_entry_is_a4():
    base = {"role": "button", "name": "Next", "text": "Next", "media": [], "tag": "button", "form": None}
    assert assess_action("click", element=base).action_class == "A2"
    for update in ({"text": "Next [REDACTED]", "name": "Next [REDACTED]"}, {"media": ["[REDACTED]"]},
                   {"form": {"action": "https://docs.example.com/[REDACTED]/go", "formaction": ""}}):
        element = {**base, **update}
        assert redacted_content(element), update
        assessed = assess_action("click", element=element)
        assert assessed.action_class == "A4" and "R11_REDACTED_CONTENT" in assessed.rules, update
    # A redacted attribute copy (G6b E1: data-*, href tokens) is not shown content.
    assert not redacted_content({**base, "attributes": {"data-ref": "[REDACTED]"}})


async def test_real_chromium_redacts_text_media_and_form_and_routes_them_to_a4(chromium):
    _m, pw, harness = chromium
    _goto(pw, "/i5/g8redact")
    info = await harness.page_info(_task())
    described = [await harness.describe(_task(), loc) for loc in ("#b", "#m", "#echo", "#rt", "#send", "#pw")]
    blob = json.dumps(info["elements"]) + json.dumps(described)
    for secret in SECRETS:
        assert secret not in blob, secret
    b, m, echo, rt, send, _pw = (d["element"] for d in described)
    assert b["name"] == "Use saved card" and b["text"] == "Card [REDACTED]"
    assert m["media"] == ["card [REDACTED]", "[REDACTED]"] or set(m["media"]) == {"card [REDACTED]", "[REDACTED]"}
    assert echo["text"] == "You typed [REDACTED]"
    assert rt["text"] == ""  # an ARIA textbox's text content is its value
    assert send["form"]["action"] == f"https://{he.DOMAIN}/reset/[REDACTED]/confirm?code"
    assert send["form"]["name"] == "acct-[REDACTED]" and send["effective_type"] == "submit"
    assert FORM_NAME_SECRET not in json.dumps([e.get("form") for e in info["elements"]] + [d["element"]["form"] for d in described])
    for loc in ("#b", "#m"):
        result, seen = await _route(pw, harness, "/i5/g8redact", **_det("click", loc))
        assert _lane4(result) and seen == [], (loc, result.reasons)
        assert any("R11_REDACTED_CONTENT" in r for r in result.reasons), result.reasons
    # Nothing redacted: the benign control still runs.
    plain, seen = await _route(pw, harness, "/i5/g8redact", **_det("click", "#plain"))
    assert plain.state is StepState.VERIFIED_SUCCESS and seen == ["benign:plain"], plain.reasons


# ------------------------------------------------------------------ F3 x G6a: the fence MAC


def _keyed(module, tmp_path):
    module.FENCE = module.LeaseFence(tmp_path / "fence-state", key=KEY, require_mac=True)


async def test_the_bound_operations_carry_the_fence_mac_and_a_keyed_harness_requires_it(chromium, tmp_path):
    module, pw, harness = chromium
    _keyed(module, tmp_path)
    keyed = HttpBrowserHarnessAdapter(None, base_url=harness.base_url, enabled=True, fence_key=KEY)
    task = _task()
    a3 = task.model_copy(update={"action_class": "A3"})
    _goto(pw, "/i5/g8redact")
    fence = HarnessLeaseFence("public_research", task.task_id, 1)
    with harness_lease_fence(fence):
        # Fenced reads (describe, describe_focus) are checked like any other call.
        for call in (lambda a: a.describe(task, "#plain"), lambda a: a.describe_focus(task)):
            with pytest.raises(BrowserAdapterError) as forged:
                await call(harness)
            assert forged.value.detail == "403"
        plain = await keyed.describe(task, "#plain")
        field = await keyed.describe(task, "#q")
        # Unkeyed bound click/fill/press: refused, nothing reaches the page.
        refusals = []
        for call in (lambda a: a.click(task, "#plain", binding=plain["binding"]),
                     lambda a: a.fill_ref(a3, "#q", "secretref://browser/q", binding=field["binding"]),
                     lambda a: a.press(task, "Tab", binding=field["binding"])):
            with pytest.raises(BrowserAdapterError) as forged:
                await call(harness)
            refusals.append((forged.value.code, forged.value.detail))
        assert refusals == [("BROWSER_HARNESS_REQUEST_FAILED", "403")] * 3
        assert _seen(pw) == [] and pw.call(lambda page, cdp: page.evaluate("document.getElementById('q').value")) == ""
        # Keyed: the same bound operations run.
        await keyed.click(task, "#plain", binding=plain["binding"])
        await keyed.fill_ref(a3, "#q", "secretref://browser/q", binding=field["binding"])
        focused = await keyed.describe_focus(task)
        await keyed.press(task, "Tab", binding=focused["binding"])
    assert _seen(pw) == ["benign:plain"]
    assert pw.call(lambda page, cdp: page.evaluate("document.getElementById('q').value")) == "install guide"
    # The adapter MACs every fenced envelope, the new endpoints' included.
    envelope = keyed._envelope(task, binding=plain["binding"], task_scope=task.scope.to_wire())
    assert "lease_mac" not in envelope  # no fence set outside the context
    with harness_lease_fence(fence):
        envelope = keyed._envelope(task, binding=plain["binding"], task_scope=task.scope.to_wire())
    assert envelope["lease_mac"] == harness_fence_mac(KEY, "public_research", 1, task.task_id)


# ------------------------------------------------------------------ F1 x G6a: the profile lock


async def test_the_profile_lock_covers_the_bound_click(chromium, tmp_path):
    """A generation-2 call arriving while generation 1's bound click runs waits for it; the
    generation-1 holder is refused afterwards."""
    module, pw, harness = chromium
    module.FENCE = module.LeaseFence(tmp_path / "fence-state")
    task = _task()
    _goto(pw, "/i5/g8redact")
    plain = await harness.describe(task, "#plain")
    events: list[str] = []
    real = module.run_harness

    def slow(alias, script, extra=None):
        # Unit G11: the lease guard's own service scripts (its thread between calls, and ending
        # generation 1's guard when generation 2 arrives) are not operations; not counted.
        role = json.loads((extra or {}).get("VAN_BH_NETGUARD") or "{}").get("role")
        if role in ("tick", "end"):
            return real(alias, script, extra)
        bound = "_van_bind(" in script and "click_at_xy" in script
        events.append("start:" + ("bound-click" if bound else "other"))
        if bound:
            time.sleep(1.0)
        try:
            return real(alias, script, extra)
        finally:
            events.append("end:" + ("bound-click" if bound else "other"))

    module.run_harness = slow
    base = {"mode": "PRODUCTION_ACTUATOR", "allow_helper_authoring": False, "profile_alias": "public_research",
            "target_domain": he.DOMAIN, "task_id": task.task_id, "task_scope": task.scope.to_wire()}

    def post(path, **extra):
        r = httpx.post(harness.base_url + path, json={**base, **extra}, timeout=30)
        return r.status_code, r.json().get("error")

    first: dict = {}
    th = threading.Thread(target=lambda: first.setdefault("r", post(
        "/click", locator="#plain", binding=plain["binding"], lease_generation=1, lease_holder_id="task-a")))
    th.start()
    time.sleep(0.3)
    second = post("/page_info", lease_generation=2, lease_holder_id="task-b")
    th.join(20)
    assert first["r"] == (200, None) and second == (200, None)
    # The bound click, its landing check (review I6 M3) and its own page_info read, then
    # generation 2 — none of them interleaved.
    assert events == ["start:bound-click", "end:bound-click"] + ["start:other", "end:other"] * 3, events
    assert post("/click", locator="#plain", binding=plain["binding"], lease_generation=1,
                lease_holder_id="task-a") == (409, "LEASE_GENERATION_STALE")
    # Unit G11 (review I7 MAJOR-1): generation 2 reaching the worker ended generation 1's
    # network guard, which froze generation 1's page (about:blank) before generation 2 ran. The
    # generation-1 click itself answered 200, which it does only after its activation was seen
    # (TARGET_NOT_ACTIVATED otherwise).
    assert pw.call(lambda page, cdp: page.url) == "about:blank"
