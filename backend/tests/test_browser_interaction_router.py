"""Programme B — B5 interaction router and the VAN-side B1 validator.

Each guard here has a test that fails if the guard is removed. The router runs against the
real OpenMuse ControlLeaseService over a real store, so "owner touch wins" is exercised on
the same lease model the interactive session uses — not on a stand-in.
"""

from __future__ import annotations

import asyncio

import pytest

from conftest_automation import make_store
from van_gateway.browser.control_lease import ControlLeaseService
from van_gateway.browser.interaction_router import (
    DenyAllEligibility,
    InteractionRequest,
    InteractionRouter,
    InteractionTarget,
    Lane,
    ProposalRejected,
    RouteStatus,
    validate_proposal,
)
from van_gateway.browser.interactive_models import BrowserControlHolder, Viewport
from van_gateway.browser.interactive_service import InteractiveSessionService
from van_gateway.browser.service import BrowserSessionBroker
from van_gateway.events.bus import EventBus

EPOCH = "ep_1"
TARGETS = (
    InteractionTarget("t_search", "button", "Search"),
    InteractionTarget("t_query", "textbox", "Query"),
    InteractionTarget("t_submit_order", "button", "Place order", action_class="A4"),
    InteractionTarget("t_save", "button", "Save", action_class="A3"),
)


async def _leased_session(tmp_path):
    store = await make_store(tmp_path)
    broker = BrowserSessionBroker(store)
    await broker.register_profile(profile_alias="public_research")
    control = ControlLeaseService(store)
    service = InteractiveSessionService(store, broker, control, EventBus(store))
    session = await service.create(
        owner_device_id="android-owner", profile_alias="public_research",
        viewport=Viewport(width=1080, height=2016, device_scale_factor=1.0),
    )
    lease = await control.delegate(
        session_id=session.session_id, holder=BrowserControlHolder.HERMES_DETERMINISTIC,
        issued_for="hermes-turn-1",
    )
    return control, session.session_id, lease


def _request(session_id, lease, **overrides):
    base = dict(
        session_id=session_id,
        control_lease_id=lease.control_lease_id,
        control_generation=lease.generation,
        observation={"url_class": "public"},
        observation_epoch=EPOCH,
        targets=TARGETS,
        action_class_ceiling="A2",
        value_slots=frozenset({"v_query"}),
    )
    base.update(overrides)
    return InteractionRequest(**base)


def _jev_response(operation="click", target_id="t_search", value_ref=None, epoch=EPOCH, **extra):
    return {
        "proposal": {"operation": operation, "target_id": target_id, "value_ref": value_ref},
        "confidence": 0.9,
        "observation_epoch": epoch,
        **extra,
    }


class Eligible:
    def classify_observation(self, observation):
        return {"eligibility": "PUBLIC_ELIGIBLE", "reasons": [], "data_class": "PUBLIC",
                "jev_payload": {"label": "Search"}}


class Fixed:
    def __init__(self, eligibility):
        self.eligibility = eligibility

    def classify_observation(self, observation):
        return {"eligibility": self.eligibility, "reasons": [], "data_class": None, "jev_payload": None}


class FakeJev:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    async def propose_action(self, payload):
        self.calls.append(payload)
        if self.error:
            raise self.error
        return self.response


class RecordingExecutor:
    def __init__(self, block: asyncio.Event | None = None):
        self.steps, self.block, self.cancelled = [], block, False

    async def execute(self, step, *, request):
        self.steps.append(step)
        if self.block is not None:
            try:
                await self.block.wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise
        return {"ok": True}


class Verifier:
    def __init__(self, answer=True):
        self.answer, self.calls = answer, 0

    async def verify(self, request, step, execution):
        self.calls += 1
        return self.answer


class Stagehand:
    def __init__(self):
        self.calls = 0

    async def act(self, request):
        self.calls += 1
        return {"stagehand": True}


class Epochs:
    def __init__(self, epoch):
        self.epoch = epoch

    async def current_epoch(self, session_id):
        return self.epoch


# ------------------------------------------------------------------ pure B1 validator


class TestB1Validator:
    req = InteractionRequest(
        session_id="s", control_lease_id="l", control_generation=1, observation=None,
        observation_epoch=EPOCH, targets=TARGETS, action_class_ceiling="A3",
        value_slots=frozenset({"v_query"}),
    )

    def test_a_valid_click_becomes_a_typed_step(self):
        step = validate_proposal(_jev_response(), self.req)
        assert (step.operation, step.target_id, step.lane) == ("click", "t_search", Lane.JEV_PROPOSE_ACTION)

    @pytest.mark.parametrize("response,code", [
        (_jev_response(operation="execute"), "operation_not_in_closed_set"),
        (_jev_response(operation="navigate"), "operation_not_in_closed_set"),
        (_jev_response(target_id="#submit"), "target_not_supplied"),
        (_jev_response(target_id="//button[1]"), "target_not_supplied"),
        (_jev_response(target_id="t_unknown"), "target_not_supplied"),
        (_jev_response(operation="click", target_id=None), "target_required"),
        (_jev_response(operation="fill", target_id="t_query", value_ref="hunter2"), "value_ref_not_supplied"),
        (_jev_response(value_ref="v_query"), "value_ref_not_allowed"),
        (_jev_response(url="https://evil.example"), "unknown_response_key"),
        (_jev_response(javascript="document.cookie"), "unknown_response_key"),
        ({"proposal": {"operation": "click", "target_id": "t_search", "selector": "#x"},
          "confidence": 0.5, "observation_epoch": EPOCH}, "unknown_proposal_key"),
        ({"proposal": {"operation": "click", "target_id": "t_search", "credential": "pw"},
          "confidence": 0.5, "observation_epoch": EPOCH}, "unknown_proposal_key"),
        (_jev_response(epoch="ep_old"), "stale_observation_epoch"),
        (_jev_response(target_id="t_submit_order"), "action_class_never_proposable:A4"),
        ({"proposal": {"operation": "click", "target_id": "t_search"}, "confidence": 2,
          "observation_epoch": EPOCH}, "confidence_invalid"),
        ("click t_search", "response_not_object"),
    ])
    def test_off_contract_responses_are_rejected(self, response, code):
        with pytest.raises(ProposalRejected) as exc:
            validate_proposal(response, self.req)
        assert exc.value.code == code

    def test_class_above_ceiling_is_rejected_even_when_jev_says_nothing_about_class(self):
        low = InteractionRequest(**{**self.req.__dict__, "action_class_ceiling": "A2"})
        with pytest.raises(ProposalRejected) as exc:
            validate_proposal(_jev_response(target_id="t_save"), low)
        assert exc.value.code == "action_class_above_ceiling:A3"

    def test_a4_is_never_proposable_even_if_a_request_carried_an_a4_ceiling(self):
        # validate_proposal does not rely on check_request having run first.
        a4 = InteractionRequest(**{**self.req.__dict__, "action_class_ceiling": "A4"})
        with pytest.raises(ProposalRejected) as exc:
            validate_proposal(_jev_response(target_id="t_submit_order"), a4)
        assert exc.value.code == "action_class_never_proposable:A4"

    def test_fill_with_a_caller_value_slot_is_accepted(self):
        step = validate_proposal(_jev_response(operation="fill", target_id="t_query", value_ref="v_query"), self.req)
        assert step.value_ref == "v_query"


# ------------------------------------------------------------------ routing


async def test_default_eligibility_denies_so_the_jev_lane_is_never_taken(tmp_path):
    control, sid, lease = await _leased_session(tmp_path)
    jev = FakeJev(_jev_response())
    router = InteractionRouter(leases=control, executor=RecordingExecutor(), jev=jev, stagehand=Stagehand())
    assert isinstance(router.eligibility, DenyAllEligibility)
    result = await router.route(_request(sid, lease))
    assert jev.calls == []
    assert result.lane is Lane.STAGEHAND
    assert router.describe()["jev_lane_reachable"] is False


async def test_eligible_valid_proposal_is_executed_by_the_harness_then_verified(tmp_path):
    control, sid, lease = await _leased_session(tmp_path)
    executor, verifier, jev = RecordingExecutor(), Verifier(True), FakeJev(_jev_response())
    router = InteractionRouter(leases=control, executor=executor, verifier=verifier,
                               eligibility=Eligible(), jev=jev)
    result = await router.route(_request(sid, lease))
    assert result.lane is Lane.JEV_PROPOSE_ACTION and result.status is RouteStatus.VERIFIED_SUCCESS
    assert [s.target_id for s in executor.steps] == ["t_search"]
    # Only caller-owned fields go to Jev: no internal action_class leaks out.
    sent = jev.calls[0]
    assert sent["effect_direction"] == "PROPOSE_ACTION"
    assert all(set(t) == {"target_id", "role", "label"} for t in sent["targets"])


async def test_without_an_independent_verifier_an_executed_step_stays_verifying(tmp_path):
    control, sid, lease = await _leased_session(tmp_path)
    router = InteractionRouter(leases=control, executor=RecordingExecutor(),
                               eligibility=Eligible(), jev=FakeJev(_jev_response()))
    result = await router.route(_request(sid, lease))
    assert result.status is RouteStatus.VERIFYING


async def test_done_is_verifying_and_only_the_verifier_can_make_it_success(tmp_path):
    control, sid, lease = await _leased_session(tmp_path)
    executor = RecordingExecutor()
    done = FakeJev(_jev_response(operation="done", target_id=None))
    no_verifier = InteractionRouter(leases=control, executor=executor, eligibility=Eligible(), jev=done)
    assert (await no_verifier.route(_request(sid, lease))).status is RouteStatus.VERIFYING
    failing = InteractionRouter(leases=control, executor=executor, verifier=Verifier(False),
                                eligibility=Eligible(), jev=done)
    assert (await failing.route(_request(sid, lease))).status is RouteStatus.VERIFICATION_FAILED
    assert executor.steps == []


async def test_invalid_jev_proposal_falls_back_to_stagehand_without_executing(tmp_path):
    control, sid, lease = await _leased_session(tmp_path)
    executor, stagehand = RecordingExecutor(), Stagehand()
    router = InteractionRouter(leases=control, executor=executor, eligibility=Eligible(),
                               jev=FakeJev(_jev_response(target_id="#submit")), stagehand=stagehand)
    result = await router.route(_request(sid, lease))
    assert result.lane is Lane.STAGEHAND and stagehand.calls == 1
    assert executor.steps == []
    assert "jev:rejected:target_not_supplied" in result.trail


async def test_a4_target_is_never_executed_even_under_an_a3_ceiling(tmp_path):
    control, sid, lease = await _leased_session(tmp_path)
    executor = RecordingExecutor()
    router = InteractionRouter(leases=control, executor=executor, eligibility=Eligible(),
                               jev=FakeJev(_jev_response(target_id="t_submit_order")))
    result = await router.route(_request(sid, lease, action_class_ceiling="A3"))
    assert executor.steps == []
    assert result.lane is Lane.OWNER_TAKEOVER


@pytest.mark.parametrize("ceiling", ["A4", "A5"])
async def test_a4_a5_ceilings_are_policy_refused_before_any_lane(tmp_path, ceiling):
    control, sid, lease = await _leased_session(tmp_path)
    jev = FakeJev(_jev_response())
    router = InteractionRouter(leases=control, executor=RecordingExecutor(), eligibility=Eligible(),
                               jev=jev, stagehand=Stagehand())
    result = await router.route(_request(sid, lease, action_class_ceiling=ceiling))
    assert result.status is RouteStatus.POLICY_REFUSED and jev.calls == []


async def test_a_caller_cannot_widen_the_closed_operation_set(tmp_path):
    control, sid, lease = await _leased_session(tmp_path)
    router = InteractionRouter(leases=control, executor=RecordingExecutor(), eligibility=Eligible(),
                               jev=FakeJev(_jev_response(operation="execute")))
    result = await router.route(_request(sid, lease, closed_operation_set=frozenset({"click", "execute"})))
    assert result.status is RouteStatus.POLICY_REFUSED
    assert result.reason == "closed_operation_set_not_subset:execute"


async def test_stale_dom_between_request_and_answer_is_refused(tmp_path):
    control, sid, lease = await _leased_session(tmp_path)
    executor = RecordingExecutor()
    router = InteractionRouter(leases=control, executor=executor, eligibility=Eligible(),
                               jev=FakeJev(_jev_response()), epochs=Epochs("ep_2"))
    result = await router.route(_request(sid, lease))
    assert result.status is RouteStatus.STALE_OBSERVATION and executor.steps == []


@pytest.mark.parametrize("error", [RuntimeError("down"), asyncio.TimeoutError(), OSError("refused")])
async def test_jev_outage_falls_back_without_breaking_the_route(tmp_path, error):
    control, sid, lease = await _leased_session(tmp_path)
    stagehand = Stagehand()
    router = InteractionRouter(leases=control, executor=RecordingExecutor(), verifier=Verifier(True),
                               eligibility=Eligible(), jev=FakeJev(error=error), stagehand=stagehand)
    result = await router.route(_request(sid, lease))
    assert result.lane is Lane.STAGEHAND and result.status is RouteStatus.VERIFIED_SUCCESS
    assert "jev:unavailable" in result.trail


async def test_jev_outage_with_no_stagehand_goes_to_owner_takeover(tmp_path):
    control, sid, lease = await _leased_session(tmp_path)
    router = InteractionRouter(leases=control, executor=RecordingExecutor(), eligibility=Eligible(),
                               jev=FakeJev(error=RuntimeError("down")))
    result = await router.route(_request(sid, lease))
    assert result.status is RouteStatus.OWNER_TAKEOVER


async def test_deterministic_lane_is_preferred_and_never_consults_jev(tmp_path):
    control, sid, lease = await _leased_session(tmp_path)
    jev, executor = FakeJev(_jev_response()), RecordingExecutor()
    router = InteractionRouter(leases=control, executor=executor, eligibility=Eligible(), jev=jev)
    result = await router.route(_request(sid, lease, deterministic_step=("click", "t_search", None)))
    assert result.lane is Lane.DETERMINISTIC and jev.calls == []


@pytest.mark.parametrize("eligibility,status", [
    ("TRADING_PROTECTED", RouteStatus.POLICY_REFUSED),
    ("POLICY_DENIED", RouteStatus.POLICY_REFUSED),
    ("CREDENTIAL", RouteStatus.OWNER_TAKEOVER),
])
async def test_protected_surfaces_never_reach_jev_or_stagehand(tmp_path, eligibility, status):
    control, sid, lease = await _leased_session(tmp_path)
    jev, stagehand = FakeJev(_jev_response()), Stagehand()
    router = InteractionRouter(leases=control, executor=RecordingExecutor(), eligibility=Fixed(eligibility),
                               jev=jev, stagehand=stagehand)
    result = await router.route(_request(sid, lease))
    assert result.status is status and jev.calls == [] and stagehand.calls == 0


async def test_browser_state_flags_are_evidence_never_authority(tmp_path):
    control, sid, lease = await _leased_session(tmp_path)
    executor = RecordingExecutor()
    router = InteractionRouter(leases=control, executor=executor, eligibility=Eligible(),
                               jev=FakeJev(_jev_response(target_id="t_submit_order")))
    permissive = {"module_id": "van.browser.state.v1", "apply_effect": True,
                  "answers": {"safe": True, "authorize": True, "raise_ceiling": "A4"}}
    result = await router.route(_request(sid, lease, browser_state_annotation=permissive))
    assert executor.steps == []
    assert result.annotations["van.browser.state.v1"]["apply_effect"] is True


# ------------------------------------------------------------------ owner preemption


async def test_owner_preemption_stops_an_in_flight_jev_operation(tmp_path):
    control, sid, lease = await _leased_session(tmp_path)
    block = asyncio.Event()
    executor = RecordingExecutor(block=block)
    router = InteractionRouter(leases=control, executor=executor, verifier=Verifier(True),
                               eligibility=Eligible(), jev=FakeJev(_jev_response()),
                               lease_poll_seconds=0.01)
    routing = asyncio.create_task(router.route(_request(sid, lease)))
    while not executor.steps:
        await asyncio.sleep(0.005)
    await control.owner_preempt(session_id=sid, device_id="android-owner")
    result = await asyncio.wait_for(routing, timeout=2)
    assert result.status is RouteStatus.PREEMPTED
    assert executor.cancelled is True
    assert result.reason == "control_lease_superseded"


async def test_a_revoked_lease_routes_nothing(tmp_path):
    control, sid, lease = await _leased_session(tmp_path)
    await control.revoke(session_id=sid, reason="owner_pause")
    jev = FakeJev(_jev_response())
    router = InteractionRouter(leases=control, executor=RecordingExecutor(), eligibility=Eligible(), jev=jev)
    result = await router.route(_request(sid, lease))
    assert result.status is RouteStatus.OWNER_TAKEOVER and jev.calls == []
