"""Real Chromium generated-content ownership, through the Harness HTTP worker.

CDP may hit a ::before/::after node whose JavaScript object has no parent link.
Only a pseudo directly owned by the bound target may be treated as that target.
These cases inspect the actual CDP hit, execute the unchanged guarded click,
and read the fixture's independent event log. No production endpoint is used.
"""

from __future__ import annotations

import copy

import pytest

from test_browser_api import _settings  # noqa: F401 - Harness API settings
from test_browser_review_i5_task_scope import _goto, _seen, _task, chromium  # noqa: F401
from van_gateway.browser.action_risk import assess_action
from van_gateway.browser.adapters import (
    BrowserAdapterError,
    HarnessLeaseFence,
    harness_lease_fence,
)


def _page(pw, pseudo="before"):
    """A named benign button whose entire center is covered by its own pseudo."""
    _goto(pw, "/i5/media")
    pw.call(lambda page, cdp: page.evaluate("""(pseudo) => {
      window.__van = [];
      document.body.innerHTML = '';
      const b = document.createElement('button');
      b.id = 'target'; b.type = 'button'; b.textContent = 'Read more';
      b.style = 'position:fixed;left:20px;top:100px;width:120px;height:40px';
      b.onclick = () => window.__van.push('benign:read');
      document.body.append(b);
      const s = document.createElement('style');
      s.textContent = '#target::' + pseudo + '{content:"Docs";position:absolute;inset:0}';
      document.head.append(s);
    }""", pseudo))


def _hit(pw, selector="#target"):
    """Independent CDP witness: the node Chromium actually hits at the center."""
    def inspect(page, cdp):
        r = page.locator(selector).bounding_box()
        at = cdp.send("DOM.getNodeForLocation", {
            "x": int(r["x"] + r["width"] / 2),
            "y": int(r["y"] + r["height"] / 2),
            "includeUserAgentShadowDOM": False,
        })
        return cdp.send("DOM.describeNode", {
            "backendNodeId": at["backendNodeId"], "depth": 0,
        })["node"]

    return pw.call(inspect)


def _blocker(pw, pseudo):
    pw.call(lambda page, cdp: page.evaluate("""(pseudo) => {
      const r = document.getElementById('target').getBoundingClientRect();
      const b = document.createElement('button');
      b.id = 'blocker'; b.type = 'button'; b.textContent = pseudo ? '' : 'Pay';
      b.style = `position:fixed;left:${r.x}px;top:${r.y}px;width:${r.width}px;height:${r.height}px;z-index:2147483647;margin:0;border:0;padding:0`;
      b.onclick = () => window.__van.push('money:overlay');
      document.body.append(b);
      if (pseudo) {
        const s = document.createElement('style');
        s.textContent = '#blocker::before{content:"Pay";position:absolute;inset:0}';
        document.head.append(s);
      }
    }""", pseudo))


def _nested_control(pw, pseudo):
    pw.call(lambda page, cdp: page.evaluate("""(pseudo) => {
      const original = document.getElementById('target');
      const w = document.createElement('div'); w.id = 'target';
      w.setAttribute('role', 'button'); w.setAttribute('aria-label', 'Read more');
      w.style = original.getAttribute('style');
      w.onclick = () => window.__van.push('benign:wrapper');
      original.replaceWith(w);
      const b = document.createElement('button');
      b.id = 'nested'; b.type = 'button'; b.textContent = pseudo ? '' : 'Pay';
      b.style = 'position:absolute;inset:0;width:120px;height:40px;z-index:2;border:0;padding:0';
      b.onclick = () => window.__van.push('money:nested'); w.append(b);
      if (pseudo) {
        const s = document.createElement('style');
        s.textContent = '#nested::before{content:"Pay";position:absolute;inset:0}';
        document.head.append(s);
      }
    }""", pseudo))


async def _click(harness, binding):
    task = _task()
    with harness_lease_fence(HarnessLeaseFence("public_research", task.task_id, 1)):
        return await harness.click(task, "#target", binding=binding)


async def _release(harness):
    await harness.release_page(
        profile_alias="public_research", holder_id=_task().task_id, generation=1,
    )


@pytest.mark.parametrize("pseudo", ["before", "after"])
async def test_direct_pseudo_owner_describes_and_activates_bound_button_once(chromium, pseudo):
    _module, pw, harness = chromium
    _page(pw, pseudo)
    hit = _hit(pw)
    assert hit["pseudoType"] == pseudo and hit["nodeName"] == "::" + pseudo
    described = await harness.describe(_task(), "#target")
    assert described["element"]["occluded"] is False
    assert described["element"]["name"] == "Read more"
    assert "Docs" in described["element"]["media"]
    assert assess_action("click", element=described["element"]).action_class == "A2"
    try:
        result = await _click(harness, described["binding"])
        assert result["url"] == described["page_url"]
        # A successful /click requires the existing event guard to observe activation.
        assert _seen(pw) == ["benign:read"]
    finally:
        await _release(harness)


@pytest.mark.parametrize("pseudo", [False, True], ids=["regular-overlay", "pseudo-overlay"])
async def test_foreign_overlay_is_occluded_and_never_activated(chromium, pseudo):
    _module, pw, harness = chromium
    _page(pw)
    _blocker(pw, pseudo)
    hit = _hit(pw)
    assert (hit.get("pseudoType") == "before") is pseudo
    described = await harness.describe(_task(), "#target")
    assert described["element"]["occluded"] is True
    try:
        with pytest.raises(BrowserAdapterError) as refused:
            await _click(harness, described["binding"])
        assert refused.value.detail == "TARGET_NOT_HIT"
        assert _seen(pw) == []
    finally:
        await _release(harness)


@pytest.mark.parametrize("pseudo", [False, True], ids=["nested-control", "nested-control-pseudo"])
async def test_nested_interactive_control_cannot_be_normalized_to_wrapper(chromium, pseudo):
    _module, pw, harness = chromium
    _page(pw)
    _nested_control(pw, pseudo)
    hit = _hit(pw)
    assert (hit.get("pseudoType") == "before") is pseudo
    described = await harness.describe(_task(), "#target")
    assert described["element"]["occluded"] is True
    try:
        with pytest.raises(BrowserAdapterError) as refused:
            await _click(harness, described["binding"])
        assert refused.value.detail == "TARGET_NOT_HIT"
        assert _seen(pw) == []
    finally:
        await _release(harness)


@pytest.mark.parametrize("pseudo", [False, True], ids=["late-regular-overlay", "late-pseudo-overlay"])
async def test_ownership_and_hit_are_fresh_after_successful_description(chromium, pseudo):
    _module, pw, harness = chromium
    _page(pw)
    own_hit = _hit(pw)
    assert own_hit["pseudoType"] == "before"
    described = await harness.describe(_task(), "#target")
    assert described["element"]["occluded"] is False
    _blocker(pw, pseudo)
    assert _hit(pw)["backendNodeId"] != own_hit["backendNodeId"]
    try:
        with pytest.raises(BrowserAdapterError) as refused:
            await _click(harness, described["binding"])
        assert refused.value.detail == "TARGET_NOT_HIT"
        assert _seen(pw) == []
    finally:
        await _release(harness)


_FAULTS = (
    ("descriptor-error", "TARGET_HIT_TEST_FAILED"),
    ("missing-node", "TARGET_HIT_TEST_FAILED"),
    ("missing-pseudos", "TARGET_NOT_HIT"),
    ("noninteger-pseudo-id", "TARGET_NOT_HIT"),
    ("unknown-pseudo-type", "TARGET_NOT_HIT"),
    ("boolean-hit-id", "TARGET_HIT_TEST_FAILED"),
    ("floating-hit-id", "TARGET_HIT_TEST_FAILED"),
    ("string-hit-id", "TARGET_HIT_TEST_FAILED"),
    ("zero-hit-id", "TARGET_HIT_TEST_FAILED"),
)


@pytest.mark.parametrize("fault, expected", _FAULTS, ids=[f[0] for f in _FAULTS])
async def test_cdp_ownership_faults_fail_closed_on_real_pseudo_hit(chromium, monkeypatch, fault, expected):
    """Alter only the selected live CDP receipt; all other browser calls stay real."""
    _module, pw, harness = chromium
    _page(pw)
    assert _hit(pw)["pseudoType"] == "before"
    admitted = await harness.describe(_task(), "#target")
    assert admitted["element"]["occluded"] is False
    session = pw.harness_session()
    original_cdp = session.cdp
    touched = []

    def faulty_cdp(method, session_id=None, **params):
        result = original_cdp(method, session_id=session_id, **params)
        descriptor = method == "DOM.describeNode" and params.get("depth") == 0 and "objectId" in params
        location = method == "DOM.getNodeForLocation"
        if descriptor and fault in {"descriptor-error", "missing-node", "missing-pseudos", "noninteger-pseudo-id", "unknown-pseudo-type"}:
            touched.append(method)
            if fault == "descriptor-error":
                raise RuntimeError("bounded live-CDP descriptor fault")
            result = copy.deepcopy(result)
            if fault == "missing-node":
                result["node"] = None
            elif fault == "missing-pseudos":
                result["node"].pop("pseudoElements", None)
            else:
                for node in result["node"].get("pseudoElements", []):
                    if fault == "noninteger-pseudo-id":
                        node["backendNodeId"] = float(node["backendNodeId"])
                    else:
                        node["pseudoType"] = "unrecognized-generated-content"
        elif location and fault in {"boolean-hit-id", "floating-hit-id", "string-hit-id", "zero-hit-id"}:
            touched.append(method)
            result = copy.deepcopy(result)
            actual = result["backendNodeId"]
            result["backendNodeId"] = {
                "boolean-hit-id": True, "floating-hit-id": float(actual),
                "string-hit-id": str(actual), "zero-hit-id": 0,
            }[fault]
        return result

    try:
        with monkeypatch.context() as patch:
            patch.setattr(session, "cdp", faulty_cdp)
            rejected = await harness.describe(_task(), "#target")
            assert rejected["element"]["occluded"] is True
            with pytest.raises(BrowserAdapterError) as refused:
                await _click(harness, admitted["binding"])
            assert refused.value.detail == expected
            assert len(touched) >= 2  # the independent description and click both saw the fault
            assert _seen(pw) == []
    finally:
        await _release(harness)
