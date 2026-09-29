"""Review I3 MAJOR-1 — planned steps on the deterministic ``/v1/browser/assignments`` path.

``AdapterBackedWorker.propose`` stamped every planned step with the assignment ceiling and
the runner's payment check read only the step's ``instruction``, so ``click #pay-now``
("Continue"), ``click #delete-account`` and ``fill #card-number`` ran and the run ended
GOAL_ACHIEVED (review-i3/probes/assign_plan_pay.py). A planned click/fill/select is now
classified by the shared rule (``resolve_stagehand_target`` -> ``observed_element_text`` ->
``default_action_classifier``, the locator's words when the Harness does not report the
element); the payment check reads the locator too; A4/A5 goes to the owner (a payment is
refused first); anything else above the ceiling is refused.
"""

from __future__ import annotations

import pytest

from test_browser_semantic_worker import DOMAIN, _task, _Verdict
from van_gateway.browser.models import AutonomyTier
from van_gateway.browser.policy import BrowserPolicyEngine
from van_gateway.browser.subagent import BrowserSubagentRunner, SubagentAssignment, SubagentStop
from van_gateway.browser.worker import AdapterBackedWorker, BrowserTaskPlan, PlannedStep
from van_gateway.models import ActionClass


class Harness:
    def __init__(self, elements: list[dict] | None = None) -> None:
        self.calls: list[str] = []
        self.elements = elements

    async def navigate(self, task, url):
        self.calls.append(f"navigate:{url}")
        return {}

    async def click(self, task, locator):
        self.calls.append(f"click:{locator}")
        return {}

    async def fill_ref(self, task, locator, ref):
        self.calls.append(f"fill:{locator}")
        return {}

    async def page_info(self, task):
        page = {"url": f"https://{DOMAIN}/statement", "title": "Statement", "extraction": {}}
        if self.elements is not None:
            page["elements"] = [dict(e) for e in self.elements]
        return page


async def _run(tmp_path, steps, *, elements=None, ceiling=ActionClass.A2):
    task = await _task(tmp_path)
    harness = Harness(elements)
    assignment = SubagentAssignment(
        turn_id="t1", command_id="cmd-1", task_id=task.task_id, goal="read the statement total",
        allowed_domains=[DOMAIN], action_class_ceiling=ceiling,
        autonomy_tier=AutonomyTier.L1_HARNESS_DETERMINISTIC, max_steps=5,
    )
    worker = AdapterBackedWorker(harness, task=task, plan=BrowserTaskPlan(steps=[
        PlannedStep(domain=DOMAIN, **s) for s in steps
    ]))
    result = await BrowserSubagentRunner(BrowserPolicyEngine(), owner_control_probe=_owner_free).run(
        assignment=assignment, worker=worker, task=task, verifier=_Verdict("VERIFIED"), postcondition=None,
    )
    return result, harness


async def _owner_free(_task):
    return False


FILL = {"value_ref": "secretref://owner/x"}


@pytest.mark.parametrize(("step", "stop"), [
    # I3's probe, locator-only (the live Harness reports no elements).
    ({"kind": "click", "locator": "#pay-now", "instruction": "Continue"}, SubagentStop.PAYMENT_REFUSED),
    ({"kind": "click", "locator": "#delete-account", "instruction": "Next"}, SubagentStop.OWNER_TAKEOVER),
    ({"kind": "fill", "locator": "#card-number", "instruction": "Enter number", **FILL}, SubagentStop.OWNER_TAKEOVER),
    # MAJOR-2 spellings on this path too.
    ({"kind": "click", "locator": "#paynow", "instruction": "Continue"}, SubagentStop.OWNER_TAKEOVER),
    ({"kind": "click", "locator": "button.submitorder", "instruction": "Continue"}, SubagentStop.OWNER_TAKEOVER),
    ({"kind": "fill", "locator": "#cardnum", "instruction": "Enter", **FILL}, SubagentStop.OWNER_TAKEOVER),
    # The unchanged control: a pay instruction is still a payment refusal.
    ({"kind": "click", "locator": "#b", "instruction": "Pay now"}, SubagentStop.PAYMENT_REFUSED),
])
@pytest.mark.parametrize("ceiling", [ActionClass.A2, ActionClass.A3])
async def test_planned_commitments_are_never_executed(tmp_path, step, stop, ceiling):
    result, harness = await _run(tmp_path, [step], ceiling=ceiling)
    assert result.stop_reason is stop
    assert not result.succeeded
    assert harness.calls == []


async def test_the_harness_observed_element_decides_not_an_innocent_locator(tmp_path):
    elements = [{"ref": "#b1", "role": "button", "label": "Pay now"},
                {"ref": "#f1", "role": "textbox", "label": "Number", "autocomplete": "cc-number"}]
    paying, harness = await _run(tmp_path, [{"kind": "click", "locator": "#b1", "instruction": "Continue"}],
                                 elements=elements)
    assert paying.stop_reason is SubagentStop.PAYMENT_REFUSED and harness.calls == []
    card, harness = await _run(tmp_path, [{"kind": "fill", "locator": "#f1", "instruction": "Enter", **FILL}],
                               elements=elements, ceiling=ActionClass.A3)
    assert card.stop_reason is SubagentStop.OWNER_TAKEOVER and harness.calls == []


async def test_a_class_above_the_ceiling_is_refused_not_stamped(tmp_path):
    """A fill is A3; under an A2 ceiling it is refused (it used to run as the A2 ceiling)."""
    result, harness = await _run(tmp_path, [{"kind": "fill", "locator": "#email", "instruction": "Email", **FILL}])
    assert result.stop_reason is SubagentStop.ACTION_CLASS_VIOLATION
    assert result.detail == "A3>A2"
    assert harness.calls == []


async def test_an_innocuous_planned_step_is_classified_and_runs(tmp_path):
    elements = [{"ref": "#report", "role": "link", "label": "Quarterly report"}]
    result, harness = await _run(tmp_path, [{"kind": "click", "locator": "#report", "instruction": "Open"}],
                                 elements=elements, ceiling=ActionClass.A3)
    assert result.stop_reason is SubagentStop.GOAL_ACHIEVED and result.succeeded
    assert [s.action_class for s in result.steps] == [ActionClass.A2]
    assert harness.calls == ["click:#report"]


async def test_the_classified_step_is_the_step_that_runs(tmp_path):
    """Execution is bound to the proposed plan index, not the first step of the same kind."""
    result, harness = await _run(tmp_path, [
        {"kind": "click", "locator": "#first", "instruction": "Open"},
        {"kind": "click", "locator": "#second", "instruction": "Open"},
    ])
    assert result.succeeded
    assert harness.calls == ["click:#first", "click:#second"]
