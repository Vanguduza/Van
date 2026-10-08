"""Reviewer I2 N-1 — a correlation key is a predicate only with a caller-declared value.

The M-1 fix accepted any non-empty ``correlation_keys`` as a predicate. The Harness read-back
observer supplies ``exists``, ``url``, ``title`` and ``visible_text`` on every read, so
``correlation_keys=["url"]`` asserted nothing: Stagehand returned no controls and the
assignment went VERIFIED -> GOAL_ACHIEVED -> COMPLETED (review-i2/probes/vacuous2.py and
complete2.py [3]). Every spelling the observer can satisfy by itself must now be
UNVERIFIABLE on all three surfaces: the verifier, the router and the subagent runner.
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
    HarnessReadBackObserver,
    IndependentPostconditionVerifier,
    InteractionStep,
    StepState,
)
from van_gateway.browser.policy import BrowserPolicyEngine
from van_gateway.browser.subagent import BrowserSubagentRunner
from van_gateway.browser.worker import HybridBrowserWorker

#: Every key the Harness read-back observer reports about itself.
OBSERVER_SIGNALS = ("exists", "url", "title", "visible_text")

UNDECLARED = [
    *(PostconditionSpec(kind="READ_BACK", correlation_keys=[key]) for key in OBSERVER_SIGNALS),
    PostconditionSpec(kind="READ_BACK", correlation_keys=["url", "title"]),
    # A real field predicate does not launder an undeclared correlation key alongside it.
    PostconditionSpec(kind="READ_BACK", field="title", expected="Report", correlation_keys=["url"]),
    # Declaring a value for one key does not cover another.
    PostconditionSpec(kind="READ_BACK", correlation_keys=["url", "title"],
                      expected_correlation={"title": "Report"}),
    # ``exists`` is the observer's own signal even with a declared value.
    PostconditionSpec(kind="READ_BACK", expected_correlation={"exists": True}),
]


def _id(spec: PostconditionSpec) -> str:
    return spec.model_dump_json(exclude_defaults=True)


async def _owner_free(_task):
    return False


async def test_the_harness_observer_supplies_every_signal_it_is_asked_about(tmp_path):
    """Instrument check: the vacuity is real only if the observer fills these keys itself."""
    task = await _task(tmp_path)
    observed = await HarnessReadBackObserver(FakeHarness()).observe(
        PostconditionSpec(kind="READ_BACK"), {"task": task}
    )
    for key in OBSERVER_SIGNALS:
        assert observed.get(key) not in (None, ""), key


@pytest.mark.parametrize("spec", UNDECLARED, ids=_id)
def test_undeclared_correlation_is_not_a_predicate(spec):
    assert spec.declares_predicate is False
    assert spec.undeclared_correlation_keys


@pytest.mark.parametrize("spec", UNDECLARED, ids=_id)
async def test_workflow_verifier_refuses_undeclared_correlation(spec):
    class _Observer:
        calls = 0

        async def observe(self, _spec, _context):
            _Observer.calls += 1
            return {"exists": True, "url": "https://x/report", "title": "Report", "visible_text": "t"}

    result = await WorkflowVerifier({"READ_BACK": _Observer()}).verify(
        spec=spec, verifier_type=VerifierType.READ_BACK, engine_reported_success=True,
    )
    assert result.outcome is VerificationOutcome.UNVERIFIABLE
    assert "undeclared correlation keys" in (result.detail or "")
    assert _Observer.calls == 0


@pytest.mark.parametrize("key", OBSERVER_SIGNALS)
async def test_router_done_with_an_observer_signal_key_is_not_verified(tmp_path, key):
    task = await _task(tmp_path)
    harness = FakeHarness()
    router = BrowserInteractionRouter(
        enabled=True, executor=HarnessActionExecutor(harness),
        verifier=IndependentPostconditionVerifier(harness), owner_control_probe=_owner_free,
    )
    result = await router.route(InteractionStep(
        task=task, action_class_ceiling="A1",
        deterministic_action=DeterministicAction(operation="done"),
        postcondition=PostconditionSpec(kind="READ_BACK", correlation_keys=[key]),
    ))
    assert result.state is StepState.UNVERIFIABLE
    assert not result.verified_success


@pytest.mark.parametrize("key", OBSERVER_SIGNALS)
async def test_stagehand_no_controls_with_an_observer_signal_key_does_not_succeed(tmp_path, key):
    """The probe's subagent line: Stagehand returns no controls (a done claim)."""
    task = await _task(tmp_path)
    harness = FakeHarness()
    runner = BrowserSubagentRunner(BrowserPolicyEngine(), owner_control_probe=_owner_free)
    result = await runner.run(
        assignment=_assignment(task), worker=HybridBrowserWorker(harness, FakeStagehand([[]]), task=task),
        task=task, verifier=IndependentPostconditionVerifier(harness),
        postcondition=PostconditionSpec(kind="READ_BACK", correlation_keys=[key]),
    )
    assert result.succeeded is False
    assert result.verification_outcome == VerificationOutcome.UNVERIFIABLE.value
    assert result.stop_reason.value == "UNVERIFIABLE"


@pytest.mark.parametrize(
    ("expected", "outcome", "state"),
    [
        ({"title": "Report"}, VerificationOutcome.VERIFIED, StepState.VERIFIED_SUCCESS),
        ({"url": "https://elsewhere.example/"}, VerificationOutcome.FAILED, None),
        ({"receipt_id": "r-1"}, VerificationOutcome.PARTIAL, None),
    ],
)
async def test_declared_correlation_is_matched_against_the_observation(tmp_path, expected, outcome, state):
    task = await _task(tmp_path)
    spec = PostconditionSpec(kind="READ_BACK", correlation_keys=list(expected), expected_correlation=expected)
    verdict = await IndependentPostconditionVerifier(FakeHarness()).verify(task, None, spec, claimed_done=True)
    assert verdict.outcome is outcome
    if state is not None:
        router = BrowserInteractionRouter(
            enabled=True, executor=HarnessActionExecutor(FakeHarness()),
            verifier=IndependentPostconditionVerifier(FakeHarness()), owner_control_probe=_owner_free,
        )
        routed = await router.route(InteractionStep(
            task=task, action_class_ceiling="A1",
            deterministic_action=DeterministicAction(operation="done"), postcondition=spec,
        ))
        assert routed.state is state
