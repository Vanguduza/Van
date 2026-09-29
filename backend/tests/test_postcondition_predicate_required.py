"""Reviewer I M-1 — a postcondition that names no predicate is never VERIFIED.

The probe (review-i/probes/vacuous.py): ``{"kind": "READ_BACK"}`` with no field, expected
value or correlation key was VERIFIED whenever the Harness could read the page, because the
read-back observer reports ``exists: bool(page)``. The fix lives in ``WorkflowVerifier`` so
every caller inherits it: the browser interaction router, the subagent assignment path
(``BrowserSubagentRunner`` via ``IndependentPostconditionVerifier``) and automation dispatch
(covered in ``test_automation_dispatch.py``).
"""

from __future__ import annotations

import pytest

from test_browser_semantic_worker import FakeHarness, FakeStagehand, _assignment, _task
from van_gateway.action.models import VerifierType
from van_gateway.automation.verifier import (
    PostconditionSpec,
    VerificationOutcome,
    WorkflowVerifier,
)
from van_gateway.browser.interaction_router import (
    BrowserInteractionRouter,
    DeterministicAction,
    HarnessActionExecutor,
    IndependentPostconditionVerifier,
    InteractionStep,
    StepState,
)
from van_gateway.browser.policy import BrowserPolicyEngine
from van_gateway.browser.subagent import BrowserSubagentRunner
from van_gateway.browser.worker import HybridBrowserWorker

VACUOUS = (
    PostconditionSpec(kind="READ_BACK"),
    PostconditionSpec(kind="READ_BACK", field="title"),
    PostconditionSpec(kind="READ_BACK", expected="Report"),
    PostconditionSpec(kind="READ_BACK", field="exists", expected=True),
)


class _CountingObserver:
    def __init__(self) -> None:
        self.calls = 0

    async def observe(self, spec, context):
        self.calls += 1
        return {"exists": True, "title": "Report"}


@pytest.mark.parametrize("spec", VACUOUS, ids=lambda s: s.model_dump_json(exclude_defaults=True))
async def test_workflow_verifier_refuses_a_spec_with_no_predicate(spec):
    observer = _CountingObserver()
    result = await WorkflowVerifier({"READ_BACK": observer}).verify(
        spec=spec, verifier_type=VerifierType.READ_BACK, engine_reported_success=True,
    )
    assert result.outcome is VerificationOutcome.UNVERIFIABLE
    assert "no predicate" in (result.detail or "")
    assert observer.calls == 0


@pytest.mark.parametrize(
    ("spec", "outcome"),
    [
        (PostconditionSpec(kind="READ_BACK", field="title", expected="Report"), VerificationOutcome.VERIFIED),
        (PostconditionSpec(kind="READ_BACK", field="title", expected="Nope"), VerificationOutcome.FAILED),
        (PostconditionSpec(kind="READ_BACK", correlation_keys=["title"]), VerificationOutcome.VERIFIED),
        (PostconditionSpec(kind="READ_BACK", correlation_keys=["receipt"]), VerificationOutcome.PARTIAL),
    ],
)
async def test_a_real_predicate_is_still_judged(spec, outcome):
    result = await WorkflowVerifier({"READ_BACK": _CountingObserver()}).verify(
        spec=spec, verifier_type=VerifierType.READ_BACK, engine_reported_success=True,
    )
    assert result.outcome is outcome


async def _owner_free(_task):
    return False


async def test_router_done_with_a_kind_only_postcondition_is_unverifiable(tmp_path):
    """The probe's router line: deterministic ``done`` + ``{kind: READ_BACK}`` on a readable page."""
    task = await _task(tmp_path)
    harness = FakeHarness()
    router = BrowserInteractionRouter(
        enabled=True, executor=HarnessActionExecutor(harness),
        verifier=IndependentPostconditionVerifier(harness), owner_control_probe=_owner_free,
    )
    result = await router.route(InteractionStep(
        task=task, action_class_ceiling="A1",
        deterministic_action=DeterministicAction(operation="done"),
        postcondition=PostconditionSpec(kind="READ_BACK"),
    ))
    assert result.state is StepState.UNVERIFIABLE
    assert result.escalated is True
    assert not result.verified_success


async def test_router_done_with_a_true_predicate_is_verified(tmp_path):
    task = await _task(tmp_path)
    harness = FakeHarness()
    router = BrowserInteractionRouter(
        enabled=True, executor=HarnessActionExecutor(harness),
        verifier=IndependentPostconditionVerifier(harness), owner_control_probe=_owner_free,
    )
    result = await router.route(InteractionStep(
        task=task, action_class_ceiling="A1",
        deterministic_action=DeterministicAction(operation="done"),
        postcondition=PostconditionSpec(kind="READ_BACK", field="title", expected="Report"),
    ))
    assert result.state is StepState.VERIFIED_SUCCESS


async def test_subagent_assignment_path_inherits_the_rule_through_the_verifier(tmp_path):
    """The /assignments path (worker + subagent, owned by unit G2a) calls the same verifier."""
    task = await _task(tmp_path)
    harness = FakeHarness()
    stagehand = FakeStagehand([[]])  # no controls: the worker claims it is done
    worker = HybridBrowserWorker(harness, stagehand, task=task)
    result = await BrowserSubagentRunner(BrowserPolicyEngine()).run(
        assignment=_assignment(task), worker=worker, task=task,
        verifier=IndependentPostconditionVerifier(harness),
        postcondition=PostconditionSpec(kind="READ_BACK"),
    )
    assert result.succeeded is False
    assert result.verification_outcome == VerificationOutcome.UNVERIFIABLE.value
    assert result.stop_reason.value == "UNVERIFIABLE"
