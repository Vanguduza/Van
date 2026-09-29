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
             action_class: str | None = None) -> ProposeActionResponse:
    return ProposeActionResponse(
        outcome="PROPOSE", state="VERIFYING" if operation == "done" else "PROPOSED",
        proposal={"operation": operation, "target_id": target_id, "value_ref": value_ref},
        confidence=0.9, reasons=(), action_class=action_class,
    )


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


def make_router(**kw: Any) -> BrowserInteractionRouter:
    kw.setdefault("enabled", True)
    kw.setdefault("executor", FakeExecutor())
    kw.setdefault("verifier", FakeVerifier())
    kw.setdefault("eligibility_classifier", eligible())
    kw.setdefault("jev_client", FakeJev(proposes("click", T_LINK)))
    kw.setdefault("semantic_fallback", FakeStagehand(STAGEHAND_ACTION))

    async def epoch_source(task, step):
        return EPOCH

    kw.setdefault("epoch_source", epoch_source)
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
    assert result.lane is RouterLane.STAGEHAND and result.state is StepState.UNVERIFIED
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
    router = make_router(jev_client=FakeJev(proposes("done", None)), verifier=verifier)
    result = await router.route(step())
    assert StepState.VERIFYING.value in result.trail
    assert result.state is StepState.VERIFICATION_FAILED
    assert router.executor.executed == []
    assert verifier.calls[0][1] is True  # claimed_done
    assert router.metrics.counts["jev_done_postcondition_failures"] == 1


async def test_jev_done_success_comes_only_from_the_verifier():
    router = make_router(jev_client=FakeJev(proposes("done", None)))
    result = await router.route(step())
    assert result.trail == ["PROPOSED", "VERIFYING", "VERIFIED_SUCCESS"]


@pytest.mark.parametrize("outcome,state", [
    (VerificationOutcome.UNVERIFIABLE, StepState.UNVERIFIED),
    (VerificationOutcome.PARTIAL, StepState.UNVERIFIED),
    (VerificationOutcome.FAILED, StepState.VERIFICATION_FAILED),
])
async def test_nothing_but_a_verified_outcome_is_success(outcome, state):
    router = make_router(verifier=FakeVerifier(outcome))
    result = await router.route(step())
    assert result.state is state and not result.verified_success


async def test_high_confidence_jev_proposal_is_still_not_success_without_verifier_verified():
    router = make_router(verifier=FakeVerifier(VerificationOutcome.UNVERIFIABLE))
    result = await router.route(step())
    assert result.lane is RouterLane.JEV and result.state is not StepState.VERIFIED_SUCCESS


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
    (lambda r: httpx.Response(200, json={**GOOD, "apply_effect": True}), "JEV_RESPONSE_APPLY_EFFECT_NOT_FALSE"),
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
