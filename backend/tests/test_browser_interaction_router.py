"""Programme B contract B5 — the browser interaction router.

Pins: lane order; an ineligible observation never reaches Jev; VAN re-applies B1 to every
Jev proposal; a Jev `done` is VERIFYING; only the independent verifier yields
VERIFIED_SUCCESS; the flag defaults off; missing dependencies disable the Jev lane with a
recorded reason; §8 metrics carry denominators; the dial-jev client turns every failure
into ABSTAIN.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tests.conftest_automation import make_store
from van_gateway.automation.verifier import (
    PostconditionSpec,
    VerificationOutcome,
    VerificationResult,
)
from van_gateway.action.models import VerifierType
from van_gateway.browser.adapters import BrowserAdapterError
from van_gateway.browser.api import BrowserApi
from van_gateway.browser.interaction_router import (
    BrowserInteractionRouter,
    DeterministicAction,
    HarnessActionExecutor,
    StagehandSemanticFallback,
    InteractionStep,
    RouterAction,
    RouterLane,
    StepState,
    build_interaction_router,
    build_interaction_routes,
    default_action_classifier,
)
from van_gateway.browser.models import (
    AutonomyTier,
    BrowserObservation,
    BrowserStrategy,
    BrowserTask,
    BrowserTaskStatus,
)
from van_gateway.config import Settings, get_settings
from van_gateway.jev.client import (
    JevProposeActionClient,
    ProposeActionResponse,
    parse_propose_action_response,
)
from van_gateway.models import ActionClass

T_SEARCH = "t_00000000000000a1"
T_LINK = "t_00000000000000b2"
T_PAY = "t_00000000000000c3"
EPOCH = "ep_1"
INTERNAL = "test-internal-token"
HEADERS = {"X-Van-Internal-Token": INTERNAL}


def _task() -> BrowserTask:
    return BrowserTask(
        task_id="browser_task_1", profile_alias="public", strategy=list(BrowserStrategy)[0],
        autonomy_tier=AutonomyTier.L1_HARNESS_DETERMINISTIC, action_class=ActionClass.A2,
        target_domain="docs.example.com", goal="find the install page",
        status=BrowserTaskStatus.PENDING, started_at_ms=0,
    )


def _payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "payload_schema": "van.browser.action_payload.v1",
        "effect_direction": "PROPOSE_ACTION",
        "closed_operation_set": ["click", "scroll", "done", "abstain"],
        "origin_class": "PUBLIC_ALLOWLISTED",
        "targets": [
            {"target_id": T_SEARCH, "role": "searchbox", "label": "Search docs"},
            {"target_id": T_LINK, "role": "link", "label": "Install guide"},
            {"target_id": T_PAY, "role": "button", "label": "Pay now"},
        ],
        "action_class_ceiling": "A2",
        "observation_epoch": EPOCH,
    }
    payload.update(overrides)
    return payload


@dataclass
class FakeEligibility:
    eligibility_class: str
    reasons: list[str] = field(default_factory=list)
    jev_payload: dict[str, Any] | None = None
    target_map: dict[str, Any] = field(default_factory=dict)
    observation_epoch: str | None = EPOCH


class FakeClassifier:
    def __init__(self, result: FakeEligibility) -> None:
        self.result = result
        self.calls = 0

    def __call__(self, observation, *, closed_operation_set, action_class_ceiling, policy=None):
        self.calls += 1
        return self.result


def eligible(**payload_overrides: Any) -> FakeClassifier:
    return FakeClassifier(FakeEligibility(
        eligibility_class="PUBLIC_ELIGIBLE",
        jev_payload=_payload(**payload_overrides),
        target_map={T_SEARCH: {"locator": "#q"}, T_LINK: "a#install", T_PAY: {"locator": "#pay"}},
    ))


class FakeJev:
    configured = True

    def __init__(self, response: ProposeActionResponse | Exception | None = None) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    async def propose_action(self, *, request, caller_action_classes, current_epoch):
        self.calls.append({
            "request": request, "caller_action_classes": caller_action_classes,
            "current_epoch": current_epoch,
        })
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def proposes(operation: str, target_id: str | None, value_ref: str | None = None,
             action_class: str | None = None, *, lifecycle_state: str = "ACTIVE",
             apply_effect: bool = True) -> ProposeActionResponse:
    """A dial-jev proposal. Defaults to a *fake* ACTIVE module with ``apply_effect: true``
    so the lane's execute/verify path can be exercised; no real Jev module can carry effect
    today (blueprint §11). Pass ``lifecycle_state="SHADOW", apply_effect=False`` for what
    DDS actually returns."""
    return ProposeActionResponse(
        outcome="PROPOSE", state="VERIFYING" if operation == "done" else "PROPOSED",
        proposal={"operation": operation, "target_id": target_id, "value_ref": value_ref},
        confidence=0.9, reasons=(), action_class=action_class,
        apply_effect=apply_effect, lifecycle_state=lifecycle_state,
    )


def shadow(operation: str, target_id: str | None, value_ref: str | None = None,
           action_class: str | None = None) -> ProposeActionResponse:
    """What DDS returns today: a proposal from a SHADOW module, ``apply_effect: false``."""
    return proposes(operation, target_id, value_ref, action_class,
                    lifecycle_state="SHADOW", apply_effect=False)


class FakeExecutor:
    def __init__(self, error: Exception | None = None) -> None:
        self.executed: list[RouterAction] = []
        self.error = error

    async def execute(self, task, action):
        if self.error is not None:
            raise self.error
        self.executed.append(action)
        return {"url": "https://docs.example.com/install"}


class FakeVerifier:
    def __init__(self, outcome: VerificationOutcome = VerificationOutcome.VERIFIED) -> None:
        self.outcome = outcome
        self.calls: list[tuple[RouterAction, bool]] = []

    async def verify(self, task, action, postcondition, *, claimed_done):
        self.calls.append((action, claimed_done))
        return VerificationResult(outcome=self.outcome, verifier_type=VerifierType.READ_BACK)


class FakeStagehand:
    def __init__(self, action: RouterAction | None = None) -> None:
        self.action = action
        self.calls = 0

    async def propose(self, task, step):
        self.calls += 1
        return self.action


STAGEHAND_ACTION = RouterAction(
    lane=RouterLane.STAGEHAND, operation="click", locator="a.install", value_ref=None,
    action_class=None, semantic_action={"method": "click", "description": "Install guide"},
    description="Install guide",
)


#: What the Harness observes for the locators the fake Stagehand proposes (reviewer I M-5:
#: Stagehand actions are classified from this, not from Stagehand's description).
HARNESS_ELEMENTS: dict[str, dict[str, Any]] = {
    "a.install": {"ref": "a.install", "role": "link", "label": "Install guide", "href": "/install"},
    "a#install": {"ref": "a#install", "role": "link", "label": "Install guide", "href": "/install"},
    "#pay": {"ref": "#pay", "role": "button", "label": "Pay now"},
}


class FakeResolver:
    def __init__(self, elements: dict[str, dict[str, Any]] | None = None, error: Exception | None = None) -> None:
        self.elements = HARNESS_ELEMENTS if elements is None else elements
        self.error = error
        self.calls: list[str] = []

    async def __call__(self, task, locator):
        self.calls.append(locator)
        if self.error is not None:
            raise self.error
        return self.elements.get(locator)


def make_router(**kw: Any) -> BrowserInteractionRouter:
    kw.setdefault("enabled", True)
    kw.setdefault("target_resolver", FakeResolver())
    kw.setdefault("executor", FakeExecutor())
    kw.setdefault("verifier", FakeVerifier())
    kw.setdefault("eligibility_classifier", eligible())
    kw.setdefault("jev_client", FakeJev(proposes("click", T_LINK)))
    kw.setdefault("semantic_fallback", FakeStagehand(STAGEHAND_ACTION))

    async def epoch_source(task, step):
        return EPOCH

    kw.setdefault("epoch_source", epoch_source)

    async def owner_idle(task):
        return False

    kw.setdefault("owner_control_probe", owner_idle)
    kw.setdefault("stagehand_gate", lambda: (True, "TEST_PERMITTED"))
    return BrowserInteractionRouter(**kw)


def step(**kw: Any) -> InteractionStep:
    kw.setdefault("action_class_ceiling", "A2")
    kw.setdefault("observation", {"url": "https://docs.example.com", "controls": []})
    kw.setdefault("postcondition", PostconditionSpec(kind="READ_BACK"))
    return InteractionStep(task=_task(), **kw)


# ---------------------------------------------------------------- lane order


async def test_deterministic_lane_runs_first_and_jev_is_not_consulted():
    jev, classifier = FakeJev(proposes("click", T_LINK)), eligible()
    router = make_router(jev_client=jev, eligibility_classifier=classifier)
    result = await router.route(step(deterministic_action=DeterministicAction(operation="click", locator="#go")))
    assert result.lane is RouterLane.DETERMINISTIC
    assert result.state is StepState.VERIFIED_SUCCESS
    assert jev.calls == [] and classifier.calls == 0
    assert router.executor.executed[0].locator == "#go"


async def test_jev_lane_second_when_eligible_and_no_deterministic_action():
    stagehand = FakeStagehand(STAGEHAND_ACTION)
    router = make_router(semantic_fallback=stagehand)
    result = await router.route(step())
    assert result.lane is RouterLane.JEV
    assert result.state is StepState.VERIFIED_SUCCESS
    assert stagehand.calls == 0
    executed = router.executor.executed[0]
    # The executor gets the fabric's locator from the target map, never a Jev string.
    assert executed.locator == "a#install" and executed.target_id == T_LINK


async def test_stagehand_third_when_jev_abstains():
    abstain = ProposeActionResponse(outcome="ABSTAIN", state="ABSTAINED", proposal=None,
                                    confidence=None, reasons=("JEV_ABSTAINED",))
    router = make_router(jev_client=FakeJev(abstain))
    result = await router.route(step())
    assert result.lane is RouterLane.STAGEHAND
    assert "JEV:JEV_ABSTAINED" in result.reasons


async def test_owner_takeover_last_when_nothing_proposes():
    router = make_router(jev_client=FakeJev(None), semantic_fallback=FakeStagehand(None))
    result = await router.route(step())
    assert result.lane is RouterLane.OWNER_TAKEOVER
    assert result.state is StepState.OWNER_TAKEOVER
    assert router.executor.executed == []


async def test_payment_boundary_refuses_even_when_the_class_check_is_permissive():
    # A permissive injected classifier lets "Pay now" through B1; the payment boundary,
    # checked before the executor is ever called, still refuses it.
    router = make_router(jev_client=FakeJev(proposes("click", T_PAY)),
                         action_classifier=lambda op, target, entry: "A1")
    result = await router.route(step())
    assert result.state is StepState.POLICY_REFUSED and result.lane is RouterLane.POLICY_REFUSAL
    assert router.executor.executed == []


async def test_never_proposable_step_ceiling_is_policy_refusal():
    router = make_router()
    refused = await router.route(step(action_class_ceiling="A4"))
    assert refused.state is StepState.POLICY_REFUSED and router.executor.executed == []


async def test_stagehand_action_above_ceiling_goes_to_owner_not_executor():
    pay = RouterAction(lane=RouterLane.STAGEHAND, operation="click", locator="#pay", value_ref=None,
                       action_class=None, semantic_action={"method": "click"},
                       description="Pay now with saved card")
    router = make_router(jev_client=FakeJev(None), semantic_fallback=FakeStagehand(pay))
    result = await router.route(step())
    assert result.lane is RouterLane.OWNER_TAKEOVER and router.executor.executed == []
    assert "STAGEHAND_ACTION_ABOVE_CEILING:A4" in result.reasons


async def test_stagehand_result_is_success_only_through_the_verifier():
    router = make_router(jev_client=FakeJev(None), verifier=FakeVerifier(VerificationOutcome.UNVERIFIABLE))
    result = await router.route(step())
    assert result.lane is RouterLane.STAGEHAND and result.state is StepState.UNVERIFIABLE
    router.verifier = FakeVerifier(VerificationOutcome.VERIFIED)
    assert (await router.route(step())).state is StepState.VERIFIED_SUCCESS


class _Obs:
    def __init__(self, controls):
        self.controls = controls


class _FakeStagehandAdapter:
    configured = True
    enabled = True

    def __init__(self, controls):
        self.controls = controls
        self.acted = 0

    async def observe(self, task, instruction):
        return _Obs(self.controls)

    async def act(self, task, action):  # must never be called by the router
        self.acted += 1


async def test_stagehand_no_controls_is_owner_takeover_never_success():
    """STAGEHAND-VERIFIER-GAP-20260929: "nothing left to do" is not success."""
    adapter = _FakeStagehandAdapter([])
    router = make_router(jev_client=FakeJev(None), semantic_fallback=StagehandSemanticFallback(adapter))
    result = await router.route(step())
    assert result.state is StepState.OWNER_TAKEOVER and "STAGEHAND_NO_ACTION" in result.reasons
    assert router.verifier.calls == []


@pytest.mark.parametrize("control,code", [
    ({"method": "fill", "selector": "#q", "arguments": ["hello"]}, "METHOD_NOT_HARNESS_EXECUTABLE:fill"),
    ({"method": "type", "selector": "#q"}, "METHOD_NOT_HARNESS_EXECUTABLE:type"),
    ({"method": "click"}, "SELECTOR_MISSING"),
    ({"method": "press", "selector": "#q", "arguments": []}, "KEY_MISSING"),
])
async def test_stagehand_actions_harness_cannot_perform_are_refused(control, code):
    adapter = _FakeStagehandAdapter([control])
    router = make_router(jev_client=FakeJev(None), semantic_fallback=StagehandSemanticFallback(adapter))
    result = await router.route(step())
    assert f"STAGEHAND_PROPOSAL_REFUSED:{code}" in result.reasons
    assert result.lane is RouterLane.OWNER_TAKEOVER and router.executor.executed == []


async def test_stagehand_click_is_executed_by_the_harness_executor_not_stagehand_act():
    adapter = _FakeStagehandAdapter([{"method": "click", "selector": "a.install", "description": "Install"}])
    router = make_router(jev_client=FakeJev(None), semantic_fallback=StagehandSemanticFallback(adapter))
    result = await router.route(step())
    assert result.lane is RouterLane.STAGEHAND and result.state is StepState.VERIFIED_SUCCESS
    assert adapter.acted == 0
    assert router.executor.executed[0].locator == "a.install"


async def test_harness_executor_maps_operations_to_the_typed_harness_surface():
    calls = []

    class Harness:
        async def click(self, task, locator):
            calls.append(("click", locator))
            return {}

        async def fill_ref(self, task, locator, value_ref):
            calls.append(("fill", locator, value_ref))
            return {}

        async def press(self, task, key):
            calls.append(("press", key))
            return {}

        async def scroll(self, task, request):
            calls.append(("scroll",))
            return {}

    ex = HarnessActionExecutor(Harness())
    for op, loc, val in [("click", "#a", None), ("fill", "#b", "secretref://x"), ("press_key", None, "Enter"),
                         ("scroll", None, None)]:
        await ex.execute(_task(), RouterAction(lane=RouterLane.JEV, operation=op, locator=loc,
                                               value_ref=val, action_class="A1"))
    assert calls == [("click", "#a"), ("fill", "#b", "secretref://x"), ("press", "Enter"), ("scroll",)]
    with pytest.raises(BrowserAdapterError):
        await ex.execute(_task(), RouterAction(lane=RouterLane.JEV, operation="select", locator="#s",
                                               value_ref=None, action_class="A1"))


# ---------------------------------------------------------------- eligibility


@pytest.mark.parametrize("cls", ["OWNER_PRIVATE", "CREDENTIAL", "TRADING_PROTECTED", "POLICY_DENIED", "UNKNOWN"])
async def test_ineligible_observation_never_reaches_jev(cls):
    jev = FakeJev(proposes("click", T_LINK))
    classifier = FakeClassifier(FakeEligibility(eligibility_class=cls, jev_payload=_payload()))
    router = make_router(jev_client=jev, eligibility_classifier=classifier)
    result = await router.route(step())
    assert len(jev.calls) == 0
    assert result.lane is RouterLane.STAGEHAND
    assert router.metrics.counts["b2_privacy_rejections"] == 1


async def test_eligible_class_without_payload_never_reaches_jev():
    jev = FakeJev(proposes("click", T_LINK))
    classifier = FakeClassifier(FakeEligibility(eligibility_class="SANITIZABLE_ELIGIBLE", jev_payload=None))
    router = make_router(jev_client=jev, eligibility_classifier=classifier)
    await router.route(step())
    assert len(jev.calls) == 0


async def test_enum_eligibility_class_is_read_by_value():
    from enum import Enum

    class EligibilityClass(str, Enum):
        SANITIZABLE_ELIGIBLE = "SANITIZABLE_ELIGIBLE"

    classifier = FakeClassifier(FakeEligibility(
        eligibility_class=EligibilityClass.SANITIZABLE_ELIGIBLE, jev_payload=_payload(),
        target_map={T_LINK: "a#install"},
    ))
    jev = FakeJev(proposes("click", T_LINK))
    result = await make_router(jev_client=jev, eligibility_classifier=classifier).route(step())
    assert len(jev.calls) == 1 and result.lane is RouterLane.JEV


async def test_request_sent_to_jev_is_payload_minus_schema_and_origin_with_van_classes():
    jev = FakeJev(proposes("click", T_LINK))
    await make_router(jev_client=jev).route(step())
    call = jev.calls[0]
    assert "payload_schema" not in call["request"] and "origin_class" not in call["request"]
    assert call["current_epoch"] == EPOCH
    classes = {(c["operation"], c["target_id"]): c["action_class"] for c in call["caller_action_classes"]}
    assert classes[("click", T_PAY)] == "A4"  # payment-shaped label: never proposable
    assert classes[("click", T_LINK)] == "A2"
    assert classes[("done", None)] == "A0" and classes[("scroll", None)] == "A0"
    assert not any(c["operation"] == "abstain" for c in call["caller_action_classes"])


async def test_van_rejects_malformed_payload_before_calling_jev():
    jev = FakeJev(proposes("click", T_LINK))
    router = make_router(jev_client=jev, eligibility_classifier=eligible(extra_field="x"))
    result = await router.route(step())
    assert jev.calls == []
    assert any(r.startswith("JEV_REQUEST_REJECTED_BY_VAN:PAYLOAD_UNKNOWN_KEY") for r in result.reasons)


async def test_payload_ceiling_above_step_ceiling_is_rejected_before_jev():
    jev = FakeJev(proposes("click", T_LINK))
    router = make_router(jev_client=jev, eligibility_classifier=eligible(action_class_ceiling="A3"))
    await router.route(step(action_class_ceiling="A2"))
    assert jev.calls == []


async def test_stale_page_before_call_does_not_consult_jev():
    jev = FakeJev(proposes("click", T_LINK))

    async def moved(task, step):
        return "ep_2"

    router = make_router(jev_client=jev, epoch_source=moved)
    result = await router.route(step())
    assert jev.calls == [] and "JEV_NOT_CALLED:OBSERVATION_STALE_BEFORE_CALL" in result.reasons


# ---------------------------------------------------------------- VAN B1 re-validation


BAD_PROPOSALS = [
    ("op_outside_closed_set", proposes("fill", T_SEARCH), "OPERATION_NOT_IN_CLOSED_SET"),
    ("target_not_supplied", proposes("click", "t_ffffffffffffffff"), "TARGET_NOT_SUPPLIED"),
    ("target_required", proposes("click", None), "TARGET_REQUIRED"),
    ("value_ref_not_supplied", proposes("click", T_LINK, value_ref="v_x"), "VALUE_REF_NOT_SUPPLIED"),
    ("a4_never", proposes("click", T_PAY), "ACTION_CLASS_NEVER_PROPOSABLE"),
    ("class_disagrees", proposes("click", T_LINK, action_class="A1"), "ACTION_CLASS_DISAGREES_WITH_JEV"),
    ("abstain_op", proposes("abstain", None), "JEV_ABSTAINED"),
]


@pytest.mark.parametrize("name,response,code", BAD_PROPOSALS, ids=[b[0] for b in BAD_PROPOSALS])
async def test_van_revalidation_rejects_bad_proposal_and_never_executes_it(name, response, code):
    router = make_router(jev_client=FakeJev(response), semantic_fallback=FakeStagehand(None))
    result = await router.route(step())
    assert f"JEV_PROPOSAL_REJECTED_BY_VAN:{code}" in result.reasons
    assert router.executor.executed == []
    assert result.lane is RouterLane.OWNER_TAKEOVER


async def test_van_revalidation_rejects_class_above_ceiling():
    router = make_router(jev_client=FakeJev(proposes("click", T_LINK)),
                         semantic_fallback=FakeStagehand(None),
                         eligibility_classifier=eligible(action_class_ceiling="A1"))
    result = await router.route(step(action_class_ceiling="A1"))
    assert "JEV_PROPOSAL_REJECTED_BY_VAN:ACTION_CLASS_ABOVE_CEILING" in result.reasons
    assert router.executor.executed == []


async def test_van_revalidation_rejects_stale_epoch_at_execution_time():
    epochs = iter([EPOCH, "ep_2"])  # fresh at call, moved before execution

    async def moving(task, step):
        return next(epochs)

    router = make_router(epoch_source=moving, semantic_fallback=FakeStagehand(None))
    result = await router.route(step())
    assert "JEV_PROPOSAL_REJECTED_BY_VAN:STALE_OBSERVATION_EPOCH" in result.reasons
    assert router.executor.executed == []
    assert router.metrics.counts["jev_stale_rejections"] == 1


async def test_unresolvable_target_is_rejected():
    classifier = FakeClassifier(FakeEligibility(eligibility_class="PUBLIC_ELIGIBLE",
                                                jev_payload=_payload(), target_map={}))
    router = make_router(eligibility_classifier=classifier, semantic_fallback=FakeStagehand(None))
    result = await router.route(step())
    assert "JEV_PROPOSAL_REJECTED_BY_VAN:TARGET_NOT_RESOLVABLE" in result.reasons
    assert router.executor.executed == []


# ---------------------------------------------------------------- done / verifier


async def test_jev_done_is_verifying_and_executes_nothing():
    verifier = FakeVerifier(VerificationOutcome.FAILED)
    router = make_router(jev_client=FakeJev(proposes("done", None)), verifier=verifier,
                         semantic_fallback=FakeStagehand(None))
    result = await router.route(step())
    [attempt] = result.attempts
    assert attempt["lane"] == "JEV" and "VERIFYING" in attempt["trail"]
    assert attempt["state"] == "NOT_SATISFIED"
    # NOT_SATISFIED -> fallback; with nothing further, the owner decides.
    assert result.state is StepState.OWNER_TAKEOVER
    assert router.executor.executed == []
    assert verifier.calls[0][1] is True  # claimed_done
    assert router.metrics.counts["jev_done_postcondition_failures"] == 1


async def test_jev_done_success_comes_only_from_the_verifier():
    router = make_router(jev_client=FakeJev(proposes("done", None)))
    result = await router.route(step())
    assert result.trail == ["PROPOSED", "VERIFYING", "VERIFIED_SUCCESS"]


@pytest.mark.parametrize("outcome,state", [
    (VerificationOutcome.UNVERIFIABLE, StepState.UNVERIFIABLE),
    (VerificationOutcome.PARTIAL, StepState.UNVERIFIABLE),
    (VerificationOutcome.FAILED, StepState.OWNER_TAKEOVER),  # NOT_SATISFIED everywhere
])
async def test_nothing_but_a_verified_outcome_is_success(outcome, state):
    router = make_router(verifier=FakeVerifier(outcome))
    result = await router.route(step())
    assert result.state is state and not result.verified_success


async def test_unverifiable_is_terminal_and_escalated():
    stagehand = FakeStagehand(STAGEHAND_ACTION)
    router = make_router(verifier=FakeVerifier(VerificationOutcome.UNVERIFIABLE), semantic_fallback=stagehand)
    result = await router.route(step())
    assert result.state is StepState.UNVERIFIABLE and result.escalated
    assert "ESCALATED:UNVERIFIABLE" in result.reasons
    assert stagehand.calls == 0  # no further automation on a page nobody can read


async def test_not_satisfied_falls_back_to_the_next_lane():
    class FirstFailsThenPasses(FakeVerifier):
        async def verify(self, task, action, postcondition, *, claimed_done):
            self.calls.append((action, claimed_done))
            outcome = VerificationOutcome.FAILED if len(self.calls) == 1 else VerificationOutcome.VERIFIED
            return VerificationResult(outcome=outcome, verifier_type=VerifierType.READ_BACK)

    observed = []

    async def observer(task):
        observed.append(1)
        return {"url": "https://docs.example.com/after"}

    router = make_router(verifier=FirstFailsThenPasses(), observer=observer)
    result = await router.route(step(deterministic_action=DeterministicAction(operation="click", locator="#go")))
    # The pre-action observation is discarded; the Jev lane re-reads the page.
    assert observed == [1]
    assert [a["lane"] for a in result.attempts] == ["DETERMINISTIC"]
    assert result.lane is RouterLane.JEV and result.state is StepState.VERIFIED_SUCCESS
    assert "DETERMINISTIC_NOT_SATISFIED" in result.reasons


async def test_verifier_unavailable_is_never_success():
    router = make_router(verifier=None)  # also disables the Jev lane
    result = await router.route(step(deterministic_action=DeterministicAction(operation="click", locator="#go")))
    assert result.state is StepState.UNVERIFIABLE and not result.verified_success


async def test_verifier_exception_is_never_success():
    class Boom(FakeVerifier):
        async def verify(self, *a, **k):
            raise RuntimeError("observer down")

    result = await make_router(verifier=Boom()).route(step())
    assert result.state is StepState.UNVERIFIABLE


# ---------------------------------------------------------------- owner takeover preempts


async def test_owner_takeover_preempts_before_any_lane():
    async def owner(task):
        return True

    jev = FakeJev(proposes("click", T_LINK))
    router = make_router(owner_control_probe=owner, jev_client=jev)
    result = await router.route(step(deterministic_action=DeterministicAction(operation="click", locator="#go")))
    assert result.state is StepState.OWNER_TAKEOVER and "OWNER_TAKEOVER:OWNER_HAS_CONTROL" in result.reasons
    assert router.executor.executed == [] and jev.calls == []


async def test_owner_takeover_preempts_between_proposal_and_execution():
    seen = []

    async def owner_arrives(task):
        seen.append(1)
        return len(seen) >= 2  # idle at lane entry, owner grabs control before execution

    router = make_router(owner_control_probe=owner_arrives)
    result = await router.route(step())
    assert result.state is StepState.OWNER_TAKEOVER and router.executor.executed == []


async def test_missing_owner_control_probe_fails_closed():
    router = make_router(owner_control_probe=None)
    result = await router.route(step())
    assert result.state is StepState.OWNER_TAKEOVER
    assert "OWNER_TAKEOVER:OWNER_CONTROL_STATE_UNKNOWN" in result.reasons


# ---------------------------------------------------------------- Stagehand production gate


@pytest.mark.parametrize("gate,reason", [
    (None, "STAGEHAND_LANE_DISABLED:PRODUCTION_GATE_MISSING"),
    (lambda: (False, "PRODUCTION_DISABLED"), "STAGEHAND_LANE_DISABLED:PRODUCTION_DISABLED"),
])
async def test_stagehand_gate_absent_or_false_skips_to_owner(gate, reason):
    stagehand = FakeStagehand(STAGEHAND_ACTION)
    router = make_router(jev_client=FakeJev(None), semantic_fallback=stagehand, stagehand_gate=gate)
    result = await router.route(step())
    assert reason in result.reasons and result.lane is RouterLane.OWNER_TAKEOVER
    assert stagehand.calls == 0


async def test_high_confidence_jev_proposal_is_still_not_success_without_verifier_verified():
    router = make_router(verifier=FakeVerifier(VerificationOutcome.UNVERIFIABLE))
    result = await router.route(step())
    assert result.lane is RouterLane.JEV and result.state is not StepState.VERIFIED_SUCCESS


async def test_stagehand_says_done_is_never_success_without_the_verifier():
    done = RouterAction(lane=RouterLane.STAGEHAND, operation="done", locator=None, value_ref=None,
                        action_class=None, description="task complete")
    router = make_router(jev_client=FakeJev(None), semantic_fallback=FakeStagehand(done),
                         verifier=FakeVerifier(VerificationOutcome.UNVERIFIABLE))
    result = await router.route(step())
    assert result.state is StepState.UNVERIFIABLE and router.executor.executed == []


async def test_executor_failure_is_execution_failed_not_success():
    router = make_router(executor=FakeExecutor(BrowserAdapterError("BROWSER_HARNESS_UNAVAILABLE")))
    result = await router.route(step())
    assert result.state is StepState.EXECUTION_FAILED


# ---------------------------------------------------------------- flag and fail-closed deps


def test_flag_defaults_off():
    assert Settings.model_fields["browser_interaction_router_enabled"].default is False


async def test_disabled_router_refuses_to_route():
    router = make_router(enabled=False)
    with pytest.raises(RuntimeError, match="BROWSER_INTERACTION_ROUTER_DISABLED"):
        await router.route(step())


@pytest.mark.parametrize("missing,reason", [
    ("eligibility_classifier", "JEV_LANE_DISABLED:ELIGIBILITY_CLASSIFIER_MISSING"),
    ("verifier", "JEV_LANE_DISABLED:VERIFIER_MISSING"),
    ("jev_client", "JEV_LANE_DISABLED:JEV_CLIENT_MISSING"),
])
async def test_missing_dependency_disables_jev_lane_with_a_recorded_reason(missing, reason):
    jev = FakeJev(proposes("click", T_LINK))
    kw = {"jev_client": jev, missing: None}
    router = make_router(**kw)
    assert reason in router.jev_lane_disabled_reasons()
    result = await router.route(step())
    assert reason in result.reasons
    assert jev.calls == []
    assert result.lane is not RouterLane.JEV
    assert router.metrics.counts["jev_lane_disabled_steps"] == 1


async def test_unconfigured_client_disables_lane():
    class Unconfigured(FakeJev):
        configured = False

    jev = Unconfigured(proposes("click", T_LINK))
    router = make_router(jev_client=jev)
    result = await router.route(step())
    assert "JEV_LANE_DISABLED:JEV_CLIENT_UNCONFIGURED" in result.reasons and jev.calls == []


def test_production_builder_without_unit_f_disables_jev_lane(monkeypatch):
    import van_gateway.browser.interaction_router as mod

    monkeypatch.setattr(mod, "load_eligibility_classifier", lambda: None)
    router = build_interaction_router(
        settings=Settings(), harness=object(), stagehand=object(),
        jev_client=JevProposeActionClient(base_url="http://127.0.0.1:6791", token_file="", enabled=False),
    )
    assert router.enabled is False
    reasons = router.jev_lane_disabled_reasons()
    assert "JEV_LANE_DISABLED:ELIGIBILITY_CLASSIFIER_MISSING" in reasons
    assert "JEV_LANE_DISABLED:JEV_CLIENT_UNCONFIGURED" in reasons


def test_default_action_classifier_is_conservative():
    assert default_action_classifier("done", None, None) == "A0"
    assert default_action_classifier("click", {"label": "Delete account"}, None) == "A4"
    assert default_action_classifier("fill", {"label": "Name"}, None) == "A3"
    assert default_action_classifier("click", {"label": "Docs"}, {"action_class": "A5"}) == "A5"
    # A declared class can raise, never lower.
    assert default_action_classifier("click", {"label": "Delete"}, {"action_class": "A1"}) == "A4"


# ---------------------------------------------------------------- metrics


async def test_metrics_carry_denominators():
    router = make_router()
    await router.route(step())  # Jev executed + verified
    router.eligibility_classifier = FakeClassifier(FakeEligibility(eligibility_class="OWNER_PRIVATE"))
    await router.route(step())  # B2 rejection -> Stagehand
    router.eligibility_classifier = eligible()
    router.jev_client = FakeJev(proposes("done", None))
    router.verifier = FakeVerifier(VerificationOutcome.FAILED)
    await router.route(step())  # done -> postcondition failure
    await router.route(step(deterministic_action=DeterministicAction(operation="scroll")))
    m = router.metrics.snapshot()["metrics"]
    assert m["total_steps"] == 4
    assert m["eligibility_rate"] == {"numerator": 2, "denominator": 4, "rate": 0.5}
    assert m["privacy_rejection_rate"] == {"numerator": 1, "denominator": 4, "rate": 0.25}
    assert m["success_on_eligible_set"] == {"numerator": 1, "denominator": 1, "rate": 1.0}
    assert m["postcondition_failure_rate"] == {"numerator": 1, "denominator": 1, "rate": 1.0}
    assert m["fallback_rate"] == {"numerator": 0, "denominator": 2, "rate": 0.0}
    assert m["stale_action_rate"]["denominator"] == 2
    assert m["wrong_action_rate"] == {"numerator": 0, "denominator": 1, "rate": 0.0}


async def test_empty_metrics_report_none_rate_not_zero():
    m = make_router().metrics.snapshot()["metrics"]
    assert m["fallback_rate"] == {"numerator": 0, "denominator": 0, "rate": None}


async def test_wrong_action_counts_verifier_failure_on_executed_proposal():
    router = make_router(verifier=FakeVerifier(VerificationOutcome.FAILED))
    await router.route(step())
    router.verifier = FakeVerifier(VerificationOutcome.VERIFIED)
    await router.route(step())
    router.metrics.record_owner_judged_wrong()  # the owner overrules the verified one
    assert router.metrics.snapshot()["metrics"]["wrong_action_rate"] == {
        "numerator": 2, "denominator": 2, "rate": 1.0,
    }


# ---------------------------------------------------------------- dial-jev client


def _client(handler) -> JevProposeActionClient:
    return JevProposeActionClient(
        base_url="http://jev.test", token_file=_client.token, enabled=True,
        transport=httpx.MockTransport(handler),
    )


@pytest.fixture
def token_file(tmp_path):
    path = tmp_path / "jev-token"
    path.write_text("tok\n")
    _client.token = str(path)
    return path


GOOD = {
    "outcome": "PROPOSED", "state": "PROPOSED",
    "proposal": {"operation": "click", "target_id": T_LINK, "value_ref": None},
    "confidence": 0.8, "reasons": [], "executes": False, "verified_success": False,
    "action_class": "A2", "apply_effect": False, "lifecycle_state": "SHADOW",
}


async def _ask(client):
    return await client.propose_action(request={"x": 1}, caller_action_classes=[], current_epoch=EPOCH)


async def test_client_sends_contract_body_and_parses_proposal(token_file):
    seen = {}

    def handler(request: httpx.Request):
        import json
        seen["path"] = request.url.path
        seen["token"] = request.headers.get("X-Dial-Jev-Token")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=GOOD)

    response = await _ask(_client(handler))
    assert seen["path"] == "/v1/judgments/propose-action" and seen["token"] == "tok"
    assert set(seen["body"]) == {"project_id", "module_id", "request", "caller_action_classes", "current_epoch"}
    assert seen["body"]["module_id"] == "van.browser.ultrafast.action.v1"
    assert response.proposes and response.transport_ok and response.action_class == "A2"


@pytest.mark.parametrize("handler,reason", [
    (lambda r: (_ for _ in ()).throw(httpx.ConnectError("down")), "JEV_TRANSPORT_ERROR"),
    (lambda r: (_ for _ in ()).throw(httpx.ReadTimeout("slow")), "JEV_TIMEOUT"),
    (lambda r: httpx.Response(400, json={"error": "bad"}), "JEV_HTTP_400"),
    (lambda r: httpx.Response(503), "JEV_HTTP_503"),
    (lambda r: httpx.Response(200, text="nope"), "JEV_RESPONSE_NOT_JSON"),
    (lambda r: httpx.Response(200, json={**GOOD, "surprise": 1}), "JEV_RESPONSE_UNKNOWN_KEY:surprise"),
    (lambda r: httpx.Response(200, json={**GOOD, "executes": True}), "JEV_RESPONSE_CLAIMS_EXECUTION"),
    (lambda r: httpx.Response(200, json={**GOOD, "verified_success": True}), "JEV_RESPONSE_CLAIMS_VERIFIED_SUCCESS"),
    (lambda r: httpx.Response(200, json={**GOOD, "apply_effect": True}),
     "JEV_RESPONSE_APPLY_EFFECT_WITHOUT_ACTIVE_LIFECYCLE"),
    (lambda r: httpx.Response(200, json={**GOOD, "apply_effect": True, "lifecycle_state": "CANDIDATE"}),
     "JEV_RESPONSE_APPLY_EFFECT_WITHOUT_ACTIVE_LIFECYCLE"),
    (lambda r: httpx.Response(200, json={k: v for k, v in {**GOOD, "apply_effect": True}.items()
                                         if k != "lifecycle_state"}),
     "JEV_RESPONSE_APPLY_EFFECT_WITHOUT_ACTIVE_LIFECYCLE"),
    (lambda r: httpx.Response(200, json={**GOOD, "apply_effect": "true", "lifecycle_state": "ACTIVE"}),
     "JEV_RESPONSE_APPLY_EFFECT_INVALID"),
    (lambda r: httpx.Response(200, json={**GOOD, "lifecycle_state": 3}), "JEV_RESPONSE_LIFECYCLE_STATE_INVALID"),
    # An ACTIVE, effect-carrying response is still validated like any other.
    (lambda r: httpx.Response(200, json={**GOOD, "apply_effect": True, "lifecycle_state": "ACTIVE",
                                         "executes": True}), "JEV_RESPONSE_CLAIMS_EXECUTION"),
    (lambda r: httpx.Response(200, json={**GOOD, "apply_effect": True, "lifecycle_state": "ACTIVE_GATED",
                                         "proposal": {"operation": "click"}}),
     "JEV_RESPONSE_PROPOSAL_SHAPE_INVALID"),
    (lambda r: httpx.Response(200, json={k: v for k, v in GOOD.items() if k != "reasons"}), "JEV_RESPONSE_KEY_MISSING:reasons"),
])
async def test_client_failures_are_abstain(token_file, handler, reason):
    response = await _ask(_client(handler))
    assert response.outcome == "ABSTAIN" and not response.transport_ok and not response.proposes
    assert response.reasons == (reason,)


async def test_client_disabled_never_calls(token_file):
    calls = []
    client = JevProposeActionClient(
        base_url="http://jev.test", token_file=str(token_file), enabled=False,
        transport=httpx.MockTransport(lambda r: calls.append(r) or httpx.Response(200, json=GOOD)),
    )
    response = await _ask(client)
    assert calls == [] and response.reasons == ("JEV_CLIENT_UNCONFIGURED",)


def test_well_formed_abstention_keeps_reasons():
    parsed = parse_propose_action_response({
        **GOOD, "outcome": "ABSTAIN", "state": "ABSTAINED", "proposal": None,
        "confidence": None, "reasons": ["STALE_OBSERVATION_EPOCH"],
    })
    assert parsed.transport_ok and not parsed.proposes and parsed.reasons == ("STALE_OBSERVATION_EPOCH",)


# ---------------------------------------------------------------- HTTP wiring


@pytest.fixture
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "router.sqlite3"))
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", "test-ingress-token-0123456789abcdef")
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", INTERNAL)
    monkeypatch.setenv("VAN_DEVICE_ENROLMENT_TOKEN", INTERNAL)
    monkeypatch.setenv("VAN_BROWSER_ENABLED", "1")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _http(tmp_path, router):
    store = await make_store(tmp_path)
    api = BrowserApi(store, get_settings())
    app = FastAPI()
    app.include_router(api.router)
    app.include_router(build_interaction_routes(api, router))
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test"), api


async def test_route_is_503_when_flag_off(_env, tmp_path):
    ac, _ = await _http(tmp_path, make_router(enabled=False))
    async with ac:
        response = await ac.post("/v1/browser/interaction/step", json={"task_id": "x"}, headers=HEADERS)
    assert response.status_code == 503 and response.json()["detail"] == "BROWSER_INTERACTION_ROUTER_DISABLED"


async def test_route_runs_router_against_a_real_task_when_flag_on(_env, tmp_path):
    router = make_router()

    async def observe(task):
        return {"url": "https://docs.example.com"}

    router.observer = observe
    ac, api = await _http(tmp_path, router)
    async with ac:
        await ac.post("/v1/browser/profiles", json={"profile_alias": "public_research"}, headers=HEADERS)
        created = await ac.post("/v1/browser/tasks", json={
            "profile_alias": "public_research", "strategy": "STAGEHAND",
            "autonomy_tier": "L4_STAGEHAND_ACT", "action_class": "A2",
            "target_domain": "docs.example.com", "goal": "find the install page",
        }, headers=HEADERS)
        if created.status_code != 200:  # the task must really exist
            raise AssertionError(created.text)
        task_id = created.json()["task_id"]
        response = await ac.post("/v1/browser/interaction/step", json={
            "task_id": task_id, "action_class_ceiling": "A2",
            "postcondition": {"kind": "READ_BACK"},
        }, headers=HEADERS)
        metrics = await ac.get("/v1/browser/interaction/metrics", headers=HEADERS)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["lane"] == "JEV" and body["state"] == "VERIFIED_SUCCESS"
    assert metrics.json()["metrics"]["total_steps"] == 1


async def test_create_app_wires_router_off_by_default(_env):
    from van_gateway.app import create_app

    app = create_app()
    router = app.state.browser_interaction
    assert app.state.browser.interaction_router is router
    assert router.enabled is False
    assert router.verifier is not None and router.executor is not None
    assert router.semantic_fallback is not None
    assert router.jev_lane_disabled_reasons()  # Jev off by default too


# ---------------------------------------------------------------- against unit F's real B2


PUBLIC_PAGE = {
    "url": "https://docs.python.org/3/library/json.html", "title": "json",
    "authenticated": False, "cookies_present": False,
    "elements": [
        {"ref": "a#next", "role": "link", "label": "Next topic"},
        {"ref": "#qs", "role": "searchbox", "label": "Quick search"},
    ],
}


class LabelPickingJev(FakeJev):
    """Proposes a click on the target with this label, using whatever id B2 minted."""

    def __init__(self, label: str, forged_id: str | None = None) -> None:
        super().__init__()
        self.label, self.forged_id = label, forged_id

    async def propose_action(self, *, request, caller_action_classes, current_epoch):
        self.calls.append({"request": request, "current_epoch": current_epoch})
        tid = self.forged_id or next(t["target_id"] for t in request["targets"] if t["label"] == self.label)
        return proposes("click", tid)


def real_b2_router(pages, jev, **kw):
    from van_gateway.browser.interaction_router import harness_page_to_jev_observation
    from van_gateway.browser.jev_eligibility import classify_observation

    pages = list(pages)

    async def observer(task):
        page = pages.pop(0) if len(pages) > 1 else pages[0]
        return harness_page_to_jev_observation(page, profile_alias="public_research")

    kw.setdefault("semantic_fallback", FakeStagehand(None))
    return make_router(
        eligibility_classifier=classify_observation, jev_client=jev, observer=observer,
        epoch_source=None, **kw,
    )


def _real_step(**kw):
    kw.setdefault("closed_operation_set", ("click", "scroll", "done", "abstain"))
    return step(observation=None, **kw)


async def test_real_b2_harness_page_without_auth_state_never_reaches_jev():
    jev = LabelPickingJev("Next topic")
    bare = {"url": PUBLIC_PAGE["url"], "title": "json"}  # what Harness page_info returns today
    router = real_b2_router([bare], jev)
    result = await router.route(_real_step())
    assert jev.calls == [] and "B2:OWNER_PRIVATE" in result.reasons


async def test_real_b2_eligible_page_round_trips_to_the_element_ref():
    jev = LabelPickingJev("Next topic")
    router = real_b2_router([PUBLIC_PAGE], jev)
    result = await router.route(_real_step())
    assert "B2:SANITIZABLE_ELIGIBLE" in result.reasons
    sent = jev.calls[0]["request"]
    assert "payload_schema" not in sent and "origin_class" not in sent
    assert sent["observation_epoch"] == jev.calls[0]["current_epoch"]
    assert result.lane is RouterLane.JEV and result.state is StepState.VERIFIED_SUCCESS
    assert router.executor.executed[0].locator == "a#next"


async def test_real_b2_page_change_makes_the_proposal_stale():
    moved = {**PUBLIC_PAGE, "url": "https://docs.python.org/3/library/csv.html"}
    jev = LabelPickingJev("Next topic")
    # classify, epoch at call (same page), epoch before execution (page moved)
    router = real_b2_router([PUBLIC_PAGE, PUBLIC_PAGE, moved], jev)
    result = await router.route(_real_step())
    assert len(jev.calls) == 1
    assert "JEV_PROPOSAL_REJECTED_BY_VAN:STALE_OBSERVATION_EPOCH" in result.reasons
    assert router.executor.executed == []


async def test_real_b2_forged_target_id_is_invalid():
    jev = LabelPickingJev("Next topic", forged_id="t_0123456789abcdef")
    router = real_b2_router([PUBLIC_PAGE], jev)
    result = await router.route(_real_step())
    assert "JEV_PROPOSAL_REJECTED_BY_VAN:TARGET_NOT_SUPPLIED" in result.reasons
    assert router.executor.executed == []


def test_harness_adapter_never_guesses_permissively():
    from van_gateway.browser.interaction_router import harness_page_to_jev_observation

    obs = harness_page_to_jev_observation(
        {**PUBLIC_PAGE, "account_identity": "someone", "cookies_present": "yes"},
        profile_alias="public_research",
    )
    assert obs.authenticated is True       # an identity marker means signed in
    assert obs.cookies_present is None     # not a bool -> unknown
    assert [e.ref for e in obs.elements] == ["a#next", "#qs"]
    assert harness_page_to_jev_observation({}, profile_alias="p").elements == ()


# ---------------------------------------------------------------- Stagehand production gate (M + K)


async def test_async_gate_is_awaited():
    async def gate():
        return False, "STAGEHAND_PROVIDER_KEY_ENTERS_BROWSER_MEMORY"

    stagehand = FakeStagehand(STAGEHAND_ACTION)
    router = make_router(jev_client=FakeJev(None), semantic_fallback=stagehand, stagehand_gate=gate)
    result = await router.route(step())
    assert "STAGEHAND_LANE_DISABLED:STAGEHAND_PROVIDER_KEY_ENTERS_BROWSER_MEMORY" in result.reasons
    assert stagehand.calls == 0


async def test_production_gate_without_placement_module_fails_closed(monkeypatch):
    import sys
    from van_gateway.browser.interaction_router import load_stagehand_production_gate

    monkeypatch.setitem(sys.modules, "van_gateway.automation.placement", None)  # import fails
    import van_gateway.automation as pkg
    monkeypatch.delattr(pkg, "placement", raising=False)
    assert await load_stagehand_production_gate(Settings())() == (False, "PLACEMENT_GATE_MISSING")


def _fake_placement(monkeypatch, verdict):
    import sys
    import types

    seen = {}

    def stagehand_production_enabled(settings, *, worker_health=None):
        seen["health"] = worker_health
        return verdict(worker_health)

    mod = types.ModuleType("van_gateway.automation.placement")
    mod.stagehand_production_enabled = stagehand_production_enabled
    monkeypatch.setitem(sys.modules, "van_gateway.automation.placement", mod)
    import van_gateway.automation as pkg
    monkeypatch.setattr(pkg, "placement", mod, raising=False)
    return seen


class _EdgeStagehand:
    def __init__(self, health: dict | None, status: int = 200):
        self.base_url = "http://edge.test/stagehand"
        body = health

        def handler(request):
            assert request.url.path == "/stagehand/health"
            return httpx.Response(status, json=body)

        self.transport = httpx.MockTransport(handler)


async def test_gate_passes_live_worker_health_and_ands_with_production_gates(monkeypatch):
    from van_gateway.browser.interaction_router import load_stagehand_production_gate

    # The real placement contract: with settings satisfied and no health yet, the reason is
    # VAN_BROWSER_CORE_UNAVAILABLE:..., the only verdict on which /health is then read.
    seen = _fake_placement(
        monkeypatch,
        lambda h: (True, "PLACEMENT_OK") if h else (False, "VAN_BROWSER_CORE_UNAVAILABLE:health_unverified"),
    )
    import van_gateway.automation.production_gates as pg

    monkeypatch.setattr(pg, "evaluate_production_gates", lambda: {
        "production_activation_permitted": False, "production_gates_not_green": ["X:signed_ingress"],
    })
    gate = load_stagehand_production_gate(Settings(), _EdgeStagehand({"status": "ok", "version": "4.1.0"}))
    ok, reason = await gate()
    assert seen["health"] == {"status": "ok", "version": "4.1.0"}
    assert ok is False and reason == "PRODUCTION_GATES_NOT_GREEN:X:signed_ingress"

    monkeypatch.setattr(pg, "evaluate_production_gates", lambda: {"production_activation_permitted": True})
    assert await gate() == (True, "PLACEMENT_OK")


async def test_gate_without_worker_health_fails_closed(monkeypatch):
    from van_gateway.browser.interaction_router import load_stagehand_production_gate

    seen = _fake_placement(monkeypatch, lambda h: (False, "WORKER_HEALTH_UNAVAILABLE") if h is None else (True, "OK"))
    ok, reason = await load_stagehand_production_gate(Settings(), _EdgeStagehand(None, status=503))()
    assert seen["health"] is None and (ok, reason) == (False, "WORKER_HEALTH_UNAVAILABLE")


def test_stagehand_adapter_model_comes_from_settings_never_a_code_default(monkeypatch):
    from van_gateway.automation.external_runtime import ExternalRuntimeRegistry
    from van_gateway.browser.adapters import StagehandAdapter

    monkeypatch.setenv("VAN_BROWSER_STAGEHAND_MODEL_PROVIDER", "anthropic")
    monkeypatch.setenv("VAN_BROWSER_STAGEHAND_MODEL_NAME", "claude-sonnet-5")
    get_settings.cache_clear()
    try:
        adapter = StagehandAdapter(ExternalRuntimeRegistry.__new__(ExternalRuntimeRegistry))
        assert (adapter.model_provider, adapter.model_name) == ("anthropic", "claude-sonnet-5")
    finally:
        get_settings.cache_clear()
    monkeypatch.delenv("VAN_BROWSER_STAGEHAND_MODEL_PROVIDER")
    monkeypatch.delenv("VAN_BROWSER_STAGEHAND_MODEL_NAME")
    get_settings.cache_clear()
    try:
        bare = StagehandAdapter(ExternalRuntimeRegistry.__new__(ExternalRuntimeRegistry), base_url="http://x")
        # Nothing configured => unconfigured, not some other model.
        assert bare.model_name in ("", "claude-sonnet-5") and not (bare.model_name and "sonnet-4" in bare.model_name)
    finally:
        get_settings.cache_clear()


# ---------------------------------------------------------------- reviewer I M-3: SHADOW


async def test_shadow_proposal_is_recorded_and_never_executed():
    """PRD Rev 2.1 "SHADOW: Jev runs; consumer ignores result"; blueprint §11."""
    router = make_router(jev_client=FakeJev(shadow("click", T_LINK)), semantic_fallback=FakeStagehand(None))
    result = await router.route(step())
    assert router.executor.executed == []
    assert result.lane is RouterLane.OWNER_TAKEOVER
    assert "JEV_SHADOW_NOT_EXECUTED:SHADOW" in result.reasons
    assert result.jev_consulted is True
    assert result.shadow_jev == {
        "lifecycle_state": "SHADOW", "apply_effect": False, "operation": "click",
        "target_id": T_LINK, "valid": True, "action_class": "A2",
    }
    counters = router.metrics.snapshot()["counters"]
    assert counters["jev_shadow_proposals"] == 1 and counters["jev_shadow_valid"] == 1
    assert counters["jev_executed"] == 0 and counters["jev_executed_verified_success"] == 0
    assert counters["jev_proposals_received"] == 1


@pytest.mark.parametrize("apply_effect,lifecycle", [
    (False, "SHADOW"), (False, "ACTIVE"), (False, "ACTIVE_GATED"), (False, None), (True, None),
    (True, "SHADOW"), (True, "CANDIDATE"),
])
async def test_only_effect_under_an_active_lifecycle_executes(apply_effect, lifecycle):
    response = proposes("click", T_LINK, lifecycle_state=lifecycle, apply_effect=apply_effect)
    router = make_router(jev_client=FakeJev(response), semantic_fallback=FakeStagehand(None))
    result = await router.route(step())
    assert router.executor.executed == []
    assert result.lane is not RouterLane.JEV


@pytest.mark.parametrize("lifecycle", ["ACTIVE", "ACTIVE_GATED"])
async def test_a_fake_active_module_with_effect_executes_through_the_harness(lifecycle):
    router = make_router(jev_client=FakeJev(proposes("click", T_LINK, lifecycle_state=lifecycle)))
    result = await router.route(step())
    assert result.lane is RouterLane.JEV and result.state is StepState.VERIFIED_SUCCESS
    assert [a.locator for a in router.executor.executed] == ["a#install"]
    assert result.shadow_jev is None


async def test_shadow_proposal_is_compared_with_what_the_next_lane_did():
    agree = RouterAction(lane=RouterLane.STAGEHAND, operation="click", locator="a#install",
                         value_ref=None, action_class=None, description="Install guide")
    router = make_router(jev_client=FakeJev(shadow("click", T_LINK)), semantic_fallback=FakeStagehand(agree))
    result = await router.route(step())
    assert result.lane is RouterLane.STAGEHAND
    assert result.shadow_jev["agreed"] is True and result.shadow_jev["compared_with_lane"] == "STAGEHAND"
    router2 = make_router(jev_client=FakeJev(shadow("click", T_SEARCH)), semantic_fallback=FakeStagehand(agree))
    result2 = await router2.route(step())
    assert result2.shadow_jev["agreed"] is False
    for r, agreements in ((router, 1), (router2, 0)):
        rates = r.metrics.snapshot()["metrics"]["shadow_agreement_rate"]
        assert rates == {"numerator": agreements, "denominator": 1, "rate": float(agreements)}


async def test_a_shadow_proposal_van_rejects_is_counted_invalid():
    router = make_router(jev_client=FakeJev(shadow("click", "t_notsupplied00001")),
                         semantic_fallback=FakeStagehand(None))
    result = await router.route(step())
    assert result.shadow_jev["valid"] is False
    assert "JEV_PROPOSAL_REJECTED_BY_VAN:TARGET_NOT_SUPPLIED" in result.reasons
    assert router.metrics.snapshot()["metrics"]["shadow_validity_rate"]["rate"] == 0.0


async def test_the_real_dds_response_shape_through_the_client_is_shadow(token_file):
    """The probe (review-i/probes/x/step_live.py) against DDS d390afa returned exactly this
    shape — PROPOSED, apply_effect false, lifecycle SHADOW — and VAN executed it."""

    def handler(request: httpx.Request):
        import json
        body = json.loads(request.content)
        target = next(t["target_id"] for t in body["request"]["targets"] if t["label"] == "Next topic")
        return httpx.Response(200, json={
            "outcome": "PROPOSED", "state": "PROPOSED",
            "proposal": {"operation": "click", "target_id": target, "value_ref": None},
            "action_class": "A2", "confidence": 0.7, "reasons": [], "executes": False,
            "verified_success": False, "apply_effect": False, "lifecycle_state": "SHADOW",
        })

    router = real_b2_router([PUBLIC_PAGE], _client(handler))
    result = await router.route(_real_step())
    assert router.executor.executed == []
    assert "JEV_SHADOW_NOT_EXECUTED:SHADOW" in result.reasons
    assert result.shadow_jev["valid"] is True


# ---------------------------------------------------------------- reviewer I M-5: Stagehand class


class _Controls:
    configured = True
    enabled = True

    def __init__(self, control):
        self.control = control

    async def observe(self, task, instruction):
        return BrowserObservation(task_id=task.task_id, controls=[self.control])


PAY_XPATH = "xpath=//button[@id='pay-now']"


def _stagehand_router(control, elements=None, **kw):
    kw.setdefault("jev_client", FakeJev(None))
    return make_router(
        semantic_fallback=StagehandSemanticFallback(_Controls(control)),
        target_resolver=kw.pop("target_resolver", FakeResolver(elements if elements is not None else {})),
        **kw,
    )


@pytest.mark.parametrize("element", [
    # The probe (review-i/probes/shclass.py): the Harness sees the id; the text says Continue.
    {"ref": PAY_XPATH, "role": "button", "label": "Continue", "id": "pay-now"},
    # Even with no id reported, the selector itself names the payment control.
    {"ref": PAY_XPATH, "role": "button", "label": "Continue"},
    # The accessible name the Harness reads disagrees with Stagehand's description.
    {"ref": PAY_XPATH, "role": "button", "label": "Place order"},
    {"ref": PAY_XPATH, "role": "button", "label": "Go", "attributes": {"data-action": "checkoutSubmit"}},
])
async def test_stagehand_class_comes_from_the_harness_observed_element(element):
    router = _stagehand_router(
        {"method": "click", "selector": PAY_XPATH, "description": "Continue", "arguments": []},
        {PAY_XPATH: element},
    )
    result = await router.route(step(action_class_ceiling="A2"))
    assert router.executor.executed == []
    assert result.lane is not RouterLane.STAGEHAND
    assert "STAGEHAND_ACTION_ABOVE_CEILING:A4" in result.reasons


async def test_the_payment_boundary_reads_the_observed_element_and_selector():
    # A permissive classifier lets the click through B1; the boundary still reads what the
    # Harness saw ("Pay now"), not what Stagehand called it ("Continue").
    router = _stagehand_router(
        {"method": "click", "selector": "#b1", "description": "Continue", "arguments": []},
        {"#b1": {"ref": "#b1", "role": "button", "label": "Pay now"}},
        action_classifier=lambda op, target, entry: "A1",
    )
    result = await router.route(step(action_class_ceiling="A2"))
    assert result.state is StepState.POLICY_REFUSED and router.executor.executed == []
    router2 = _stagehand_router(
        {"method": "click", "selector": PAY_XPATH, "description": "Continue", "arguments": []},
        {PAY_XPATH: {"ref": PAY_XPATH, "role": "button", "label": "Continue"}},
        action_classifier=lambda op, target, entry: "A1",
    )
    result2 = await router2.route(step(action_class_ceiling="A2"))
    assert result2.state is StepState.POLICY_REFUSED and router2.executor.executed == []


@pytest.mark.parametrize("resolver,code", [
    (None, "NO_TARGET_RESOLVER"),
    (FakeResolver({}), "TARGET_NOT_RESOLVED_BY_HARNESS"),
    (FakeResolver(error=BrowserAdapterError("BROWSER_HARNESS_UNAVAILABLE")), "RESOLVER_FAILED:BrowserAdapterError"),
    (FakeResolver({"#b1": {"ref": "#b1", "role": "button", "label": "Next", "hidden": True}}), "TARGET_HIDDEN"),
    (FakeResolver({"#b1": {"ref": "#b1"}}), "TARGET_HAS_NO_ROLE_OR_NAME"),
])
async def test_an_unresolvable_stagehand_target_is_owner_takeover(resolver, code):
    router = _stagehand_router(
        {"method": "click", "selector": "#b1", "description": "Next page", "arguments": []},
        target_resolver=resolver,
    )
    result = await router.route(step(action_class_ceiling="A2"))
    assert result.lane is RouterLane.OWNER_TAKEOVER and result.escalated
    assert f"STAGEHAND_ACTION_UNCLASSIFIABLE:{code}" in result.reasons
    assert "OWNER_TAKEOVER:STAGEHAND_ACTION_UNCLASSIFIABLE" in result.reasons
    assert router.executor.executed == []


async def test_a_benign_resolved_stagehand_target_still_runs():
    router = _stagehand_router(
        {"method": "click", "selector": "#next", "description": "Next page", "arguments": []},
        {"#next": {"ref": "#next", "role": "link", "label": "Next page", "href": "/p/2"}},
    )
    result = await router.route(step(action_class_ceiling="A2"))
    assert result.lane is RouterLane.STAGEHAND and result.state is StepState.VERIFIED_SUCCESS
    assert [(a.locator, a.action_class) for a in router.executor.executed] == [("#next", "A2")]


async def test_harness_target_resolver_reads_only_the_harness_element_list():
    from van_gateway.browser.interaction_router import HarnessTargetResolver

    class Harness:
        def __init__(self, page):
            self.page = page

        async def page_info(self, task):
            return self.page

    element = {"ref": "#next", "role": "link", "label": "Next"}
    assert await HarnessTargetResolver(Harness({"elements": [element]}))(_task(), "#next") == element
    assert await HarnessTargetResolver(Harness({"elements": [element]}))(_task(), "#other") is None
    # What the live Harness page_info returns today: no element list -> nothing resolves.
    assert await HarnessTargetResolver(Harness({"url": "https://x.example", "title": "x"}))(_task(), "#next") is None


def test_production_wiring_resolves_stagehand_targets_through_the_harness():
    from van_gateway.browser.interaction_router import HarnessTargetResolver

    harness = object()
    router = build_interaction_router(settings=Settings(), harness=harness, stagehand=object(), jev_client=None)
    assert isinstance(router.target_resolver, HarnessTargetResolver)
    assert router.target_resolver.harness is harness


@pytest.mark.parametrize("selector,element", [
    ("button#pay_now", {"role": "button", "label": "Continue"}),
    ("#b2", {"role": "button", "label": "Go", "attributes": {"data-action": "checkoutSubmit"}}),
    ("[data-testid=placeOrderBtn]", {"role": "button", "label": "Next"}),
])
async def test_selector_and_attribute_words_hidden_by_punctuation_or_case_are_read(selector, element):
    router = _stagehand_router(
        {"method": "click", "selector": selector, "description": "Continue", "arguments": []},
        {selector: {"ref": selector, **element}},
    )
    result = await router.route(step(action_class_ceiling="A2"))
    assert router.executor.executed == []
    assert "STAGEHAND_ACTION_ABOVE_CEILING:A4" in result.reasons


# ---------------------------------------------------------------- reviewer I M-8: task class + lifecycle


def _fill_router():
    return make_router(
        eligibility_classifier=eligible(action_class_ceiling="A3", closed_operation_set=["click", "fill", "abstain"],
                                        value_slots=["v_q"]),
        jev_client=FakeJev(proposes("fill", T_SEARCH, "v_q")), semantic_fallback=FakeStagehand(None),
    )


def _fill_step(task_class=ActionClass.A2, status=BrowserTaskStatus.PENDING):
    s = step(action_class_ceiling="A3", closed_operation_set=("click", "fill", "abstain"),
             value_slots={"v_q": "secretref://browser/q"})
    s.task = s.task.model_copy(update={"action_class": task_class, "status": status})
    return s


async def test_step_ceiling_is_capped_at_the_task_admitted_class():
    """Probe review-i/probes/ceiling.py: an A3 step on an A2 task executed an A3 fill."""
    router = _fill_router()
    s = _fill_step(ActionClass.A2)
    result = await router.route(s)
    assert router.executor.executed == []
    assert "STEP_CEILING_CAPPED_BY_TASK:A3->A2" in result.reasons
    assert s.action_class_ceiling == "A2"


async def test_an_a3_task_still_permits_an_a3_step():
    router = _fill_router()
    result = await router.route(_fill_step(ActionClass.A3))
    assert result.lane is RouterLane.JEV and [a.action_class for a in router.executor.executed] == ["A3"]
    assert not any(r.startswith("STEP_CEILING_CAPPED_BY_TASK") for r in result.reasons)


async def test_a_lower_step_ceiling_is_never_raised_by_the_task():
    router = make_router(jev_client=FakeJev(proposes("click", T_LINK)))
    s = step(action_class_ceiling="A1")
    s.task = s.task.model_copy(update={"action_class": ActionClass.A5})
    result = await router.route(s)
    assert s.action_class_ceiling == "A1" and router.executor.executed == []


@pytest.mark.parametrize("status", [
    s for s in BrowserTaskStatus if s not in (BrowserTaskStatus.PENDING, BrowserTaskStatus.RESUME_AUTHORIZED)
])
async def test_a_task_that_is_not_runnable_is_refused(status):
    router = make_router(jev_client=FakeJev(proposes("click", T_LINK)))
    s = step(deterministic_action=DeterministicAction(operation="click", locator="#go"))
    s.task = s.task.model_copy(update={"status": status})
    result = await router.route(s)
    assert result.state is StepState.POLICY_REFUSED
    assert result.reasons == [f"BROWSER_TASK_NOT_RUNNABLE:{status.value}"]
    assert router.executor.executed == []


async def test_a_resume_authorized_task_is_runnable():
    router = make_router()
    s = step(deterministic_action=DeterministicAction(operation="click", locator="#go"))
    s.task = s.task.model_copy(update={"status": BrowserTaskStatus.RESUME_AUTHORIZED})
    assert (await router.route(s)).state is StepState.VERIFIED_SUCCESS


async def test_route_is_409_for_a_completed_task_and_caps_the_ceiling(_env, tmp_path):
    router = make_router(
        eligibility_classifier=eligible(action_class_ceiling="A3", closed_operation_set=["click", "fill", "abstain"],
                                        value_slots=["v_q"]),
        jev_client=FakeJev(proposes("fill", T_SEARCH, "v_q")), semantic_fallback=FakeStagehand(None),
    )
    ac, api = await _http(tmp_path, router)
    async with ac:
        await ac.post("/v1/browser/profiles", json={"profile_alias": "public_research"}, headers=HEADERS)
        created = await ac.post("/v1/browser/tasks", json={
            "profile_alias": "public_research", "strategy": "STAGEHAND",
            "autonomy_tier": "L4_STAGEHAND_ACT", "action_class": "A2",
            "target_domain": "docs.example.com", "goal": "find the install page",
        }, headers=HEADERS)
        assert created.status_code == 200, created.text
        task_id = created.json()["task_id"]
        body = {"task_id": task_id, "action_class_ceiling": "A3",
                "closed_operation_set": ["click", "fill", "abstain"],
                "value_slots": {"v_q": "secretref://browser/q"},
                "observation": None, "postcondition": {"kind": "READ_BACK", "field": "title", "expected": "x"}}
        capped = await ac.post("/v1/browser/interaction/step", json=body, headers=HEADERS)
        # G2a: COMPLETED needs a recorded VERIFIED verdict first.
        await api.tasks.record_verification(task=await api._load_task(task_id), outcome="VERIFIED",
                                            verifier="test")
        await api.tasks.complete(task_id=task_id, status=BrowserTaskStatus.COMPLETED)
        refused = await ac.post("/v1/browser/interaction/step", json=body, headers=HEADERS)
    assert capped.status_code == 200, capped.text
    assert "STEP_CEILING_CAPPED_BY_TASK:A3->A2" in capped.json()["reasons"]
    assert router.executor.executed == []
    assert refused.status_code == 409
    assert refused.json()["detail"] == "BROWSER_TASK_NOT_RUNNABLE:COMPLETED"


async def test_gate_closes_on_settings_without_contacting_the_endpoint(monkeypatch):
    """Unit G2a request: an undeclared/loopback/plain-HTTP endpoint is never contacted."""
    from van_gateway.browser.interaction_router import load_stagehand_production_gate

    calls = []

    class Loopback:
        base_url = "http://127.0.0.1:9/stagehand"
        transport = httpx.MockTransport(lambda r: calls.append(r) or httpx.Response(200, json={"ok": True}))

    settings = Settings(browser_enabled=True, browser_stagehand_zone="van-browser-core",
                        browser_stagehand_base_url="http://127.0.0.1:9/stagehand")
    ok, reason = await load_stagehand_production_gate(settings, Loopback())()
    assert ok is False and reason == "STAGEHAND_ENDPOINT_NOT_CROSS_ZONE_MTLS"
    ok, reason = await load_stagehand_production_gate(Settings(), Loopback())()
    assert ok is False and reason == "BROWSER_FABRIC_DISABLED"
    assert calls == []
