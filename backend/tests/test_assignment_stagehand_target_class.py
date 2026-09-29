"""Reviewer I2 N-2 — the M-5 fix on the ``/v1/browser/assignments`` path.

``HybridBrowserWorker.propose`` set ``action_class`` to the assignment ceiling and the
runner's payment check read only Stagehand's description, so a pay-now button described as
"Continue" and ``#delete-account`` described as "Next" were clicked as A2
(review-i2/probes/assign_shclass.py). The worker now classifies from what the Harness
observes of the target plus the locator words, with the router's own resolver and
classifier; the payment boundary runs over that same text; an unresolvable target is owner
takeover; the ceiling caps the class (above it is refused, never clamped down).
"""

from __future__ import annotations

import pytest

from test_browser_semantic_worker import FakeHarness, FakeStagehand, _assignment, _task, _Verdict
from van_gateway.browser.policy import BrowserPolicyEngine
from van_gateway.browser.subagent import BrowserSubagentRunner, SubagentStop
from van_gateway.browser.worker import HybridBrowserWorker
from van_gateway.models import ActionClass

PAY = "xpath=//button[@id='pay-now']"
DELETE = "#delete-account"
REPORT = "xpath=//a[@id='quarterly-report']"
#: The Harness sees the same innocuous names Stagehand used; only the locator words differ.
ELEMENTS = [
    {"ref": PAY, "role": "button", "name": "Continue"},
    {"ref": DELETE, "role": "button", "name": "Next"},
    {"ref": REPORT, "role": "link", "name": "Quarterly report"},
]


async def _owner_free(_task):
    return False


async def _run(tmp_path, selector, description, *, elements=ELEMENTS, ceiling=ActionClass.A2):
    task = await _task(tmp_path)
    harness = FakeHarness(elements)
    control = {"method": "click", "selector": selector, "description": description, "arguments": []}
    stagehand = FakeStagehand([[control], []])
    result = await BrowserSubagentRunner(BrowserPolicyEngine(), owner_control_probe=_owner_free).run(
        assignment=_assignment(task, action_class_ceiling=ceiling),
        worker=HybridBrowserWorker(harness, stagehand, task=task), task=task,
        verifier=_Verdict("VERIFIED"), postcondition=None,
    )
    return result, harness


@pytest.mark.parametrize(("selector", "description", "stop"), [
    (PAY, "Continue", SubagentStop.PAYMENT_REFUSED),
    (PAY, "Pay now", SubagentStop.PAYMENT_REFUSED),
    (DELETE, "Next", SubagentStop.ACTION_CLASS_VIOLATION),
])
async def test_probe_controls_are_never_clicked(tmp_path, selector, description, stop):
    result, harness = await _run(tmp_path, selector, description)
    assert result.stop_reason is stop
    assert harness.actuations == []
    assert not result.succeeded


@pytest.mark.parametrize("ceiling", [ActionClass.A2, ActionClass.A3])
async def test_delete_is_a4_whatever_the_ceiling(tmp_path, ceiling):
    result, harness = await _run(tmp_path, DELETE, "Next", ceiling=ceiling)
    assert result.stop_reason is SubagentStop.ACTION_CLASS_VIOLATION
    assert result.detail == f"A4>{ceiling.value}"
    assert harness.actuations == []


async def test_an_innocuous_target_is_classified_not_given_the_ceiling(tmp_path):
    result, harness = await _run(tmp_path, REPORT, "Open the report", ceiling=ActionClass.A3)
    assert result.stop_reason is SubagentStop.GOAL_ACHIEVED
    # A2 from the classifier, not the A3 ceiling the old code stamped on every proposal.
    assert [s.action_class for s in result.steps] == [ActionClass.A2]
    assert harness.actuations == [f"click:{REPORT}"]


async def test_a_class_above_the_ceiling_is_refused_not_clamped(tmp_path):
    result, harness = await _run(tmp_path, REPORT, "Open the report", ceiling=ActionClass.A1)
    assert result.stop_reason is SubagentStop.ACTION_CLASS_VIOLATION
    assert result.detail == "A2>A1"
    assert harness.actuations == []


@pytest.mark.parametrize(("elements", "reason"), [
    (None, "TARGET_NOT_RESOLVED_BY_HARNESS"),  # the live Harness reports no elements today
    ([{"ref": "#other", "role": "button", "name": "Continue"}], "TARGET_NOT_RESOLVED_BY_HARNESS"),
    ([{"ref": PAY, "role": "button", "name": "Continue", "hidden": True}], "TARGET_HIDDEN"),
    ([{"ref": PAY, "id": "pay-now"}], "TARGET_HAS_NO_ROLE_OR_NAME"),
])
async def test_an_unresolvable_target_is_owner_takeover(tmp_path, elements, reason):
    result, harness = await _run(tmp_path, PAY, "Continue", elements=elements)
    assert result.stop_reason is SubagentStop.OWNER_TAKEOVER
    assert result.detail == f"STAGEHAND_ACTION_UNCLASSIFIABLE:{reason}"
    assert harness.actuations == []


async def test_a_resolver_fault_is_owner_takeover(tmp_path):
    class _Broken(FakeHarness):
        async def page_info(self, task):
            raise RuntimeError("harness down")

    task = await _task(tmp_path)
    harness = _Broken()
    stagehand = FakeStagehand([[{"method": "click", "selector": PAY, "description": "Continue"}]])
    result = await BrowserSubagentRunner(BrowserPolicyEngine(), owner_control_probe=_owner_free).run(
        assignment=_assignment(task), worker=HybridBrowserWorker(harness, stagehand, task=task), task=task,
        verifier=_Verdict("VERIFIED"),
    )
    assert result.stop_reason is SubagentStop.OWNER_TAKEOVER
    assert result.detail == "STAGEHAND_ACTION_UNCLASSIFIABLE:RESOLVER_FAILED:RuntimeError"
    assert harness.actuations == []


async def test_the_proposal_carries_the_harness_observed_text(tmp_path):
    task = await _task(tmp_path)
    stagehand = FakeStagehand([[{"method": "click", "selector": PAY, "description": "Continue"}]])
    worker = HybridBrowserWorker(FakeHarness(ELEMENTS), stagehand, task=task)
    proposal = await worker.propose(_assignment(task), [])
    assert proposal.action_class is ActionClass.A4
    assert "pay now" in (proposal.instruction or "")
    assert "pay now" in proposal.payload["harness_observed_target"]
