"""Rev 1 §§3-6, 34, 55 — Mission Core.

§6 asks for regression tests that *explicitly attempt to forge success without
verifier receipts*, so those are written as attacks rather than as happy paths.
There are three distinct ways to arrive at an unearned VERIFIED_SUCCESS and each
gets its own test, because closing two of three would look green and mean
nothing.

Since P0-VERIFY-001 there is a fourth, which the earlier three could not catch: bring a
receipt that says everything the gate checks for, and write it yourself. The audit did
exactly that with `verifier_version: "i-say-so/1.0"`. `transition` no longer takes a
receipt at all — it runs the verifier the mission's own contract names — so these tests
now set up a registry instead of handing one in, and the attacks below are attempts to
make that registry lie.
"""

from __future__ import annotations

import pytest

from conftest_automation import make_store
from van_gateway.mission.models import (
    LEGAL_TRANSITIONS,
    TERMINAL_STATES,
    ActivityState,
    AuthorityEnvelope,
    MissionEventType,
    MissionOrigin,
    MissionState,
    SuccessContract,
    VerificationRecord,
    VerificationStatus,
)
from van_gateway.mission.service import MissionError, MissionService
from van_gateway.mission.verifiers import ObservationVerifier, VerifierRegistry
from van_gateway.models import ActionClass, OriginChannel, PrincipalType

CHECKABLE = SuccessContract(
    postconditions={"notebook_exists": True, "minimum_sources": 5},
    verifier_class="notebook.readback",
)
def _registry(observed: dict | None = None, *, raises: Exception | None = None) -> VerifierRegistry:
    """A registry whose adapter observes whatever the test wants the world to look like.

    The adapter still does the comparing and still writes the receipt, so a test can make
    the *world* look any way at all and never make the *verdict* whatever it likes.
    """

    async def observe(context):
        if raises is not None:
            raise raises
        return dict(observed or {})

    registry = VerifierRegistry()
    registry.register(
        "notebook.readback",
        ObservationVerifier(observe, verifier_version="notebook.readback/1",
                            evidence_prefix="provider-readback://"),
    )
    return registry


#: What a genuine readback of a satisfied contract looks like.
GOOD_OBSERVATION = {
    "notebook_exists": True,
    "minimum_sources": 7,
    "evidence_refs": ["provider-readback://nb-1"],
}


async def _service(tmp_path, registry: VerifierRegistry | None = None) -> MissionService:
    return MissionService(await make_store(tmp_path), verifiers=registry)


async def _mission(svc: MissionService, **overrides):
    body = dict(
        owner_principal_id="owner",
        origin=MissionOrigin.OWNER_VOICE,
        origin_channel=OriginChannel.VOICE,
        title="Research X",
        goal="research X and put the useful findings into my project",
    )
    body.update(overrides)
    return await svc.create(**body)


async def _drive_to_verifying(svc, mission):
    for target in (MissionState.UNDERSTOOD, MissionState.PLANNED, MissionState.AUTHORIZED,
                   MissionState.RUNNING, MissionState.VERIFYING):
        mission = await svc.transition(mission.mission_id, target=target)
    return mission


# ------------------------------------------------------- the state machine


def test_the_state_machine_is_total_and_terminals_are_sinks():
    """Every state has an entry, and no terminal state has a way out."""
    assert set(LEGAL_TRANSITIONS) == set(MissionState)
    for state in TERMINAL_STATES:
        assert LEGAL_TRANSITIONS[state] == frozenset(), state


def test_waiting_for_owner_is_not_terminal():
    """§3.2 says so explicitly, and the silent-death failure mode is the reason."""
    assert MissionState.WAITING_FOR_OWNER not in TERMINAL_STATES
    assert MissionState.RESUME_AUTHORIZED in LEGAL_TRANSITIONS[MissionState.WAITING_FOR_OWNER]


def test_no_state_reaches_a_success_outcome_except_through_verifying():
    """The only door to success is verification, structurally."""
    for state, targets in LEGAL_TRANSITIONS.items():
        if state is MissionState.VERIFYING:
            continue
        assert MissionState.VERIFIED_SUCCESS not in targets, state
        assert MissionState.PARTIAL_SUCCESS not in targets, state


async def test_a_mission_always_starts_captured(tmp_path):
    svc = await _service(tmp_path)
    mission = await _mission(svc)
    assert mission.state is MissionState.CAPTURED
    assert mission.verification_state is VerificationStatus.PENDING
    events = await svc.events(mission.mission_id)
    assert [e.event_type for e in events] == [MissionEventType.MISSION_CREATED]


async def test_an_illegal_transition_fails_closed(tmp_path):
    svc = await _service(tmp_path)
    mission = await _mission(svc)
    with pytest.raises(MissionError, match="ILLEGAL_TRANSITION"):
        await svc.transition(mission.mission_id, target=MissionState.RUNNING)
    assert (await svc.get(mission.mission_id)).state is MissionState.CAPTURED


async def test_a_stale_expectation_is_a_conflict_not_an_overwrite(tmp_path):
    svc = await _service(tmp_path)
    mission = await _mission(svc)
    await svc.transition(mission.mission_id, target=MissionState.UNDERSTOOD)
    with pytest.raises(MissionError, match="PRECONDITION_FAILED"):
        await svc.transition(
            mission.mission_id, target=MissionState.PLANNED, expected=MissionState.CAPTURED
        )


async def test_a_terminal_mission_cannot_be_moved(tmp_path):
    svc = await _service(tmp_path)
    mission = await _mission(svc)
    await svc.transition(mission.mission_id, target=MissionState.CANCELLED)
    with pytest.raises(MissionError, match="TERMINAL"):
        await svc.transition(mission.mission_id, target=MissionState.UNDERSTOOD)


# ------------------------------------------- §6/§55: forging success fails


async def test_success_cannot_be_claimed_without_a_receipt(tmp_path):
    """Attack 1: just assert it. "The worker returned OK".

    With no registry the default is EngineReportVerifier, which is always UNVERIFIABLE,
    so an unwired capability cannot reach success however loudly its executor claims to.
    """
    svc = await _service(tmp_path)
    mission = await _drive_to_verifying(svc, await _mission(svc, success_contract=CHECKABLE))
    with pytest.raises(MissionError, match="VERIFICATION_INSUFFICIENT"):
        await svc.transition(mission.mission_id, target=MissionState.VERIFIED_SUCCESS)
    assert (await svc.get(mission.mission_id)).state is MissionState.VERIFYING


@pytest.mark.parametrize(
    ("observed", "why"),
    [
        (
            {"notebook_exists": True, "minimum_sources": 7},
            "every postcondition satisfied but nothing citable to point at",
        ),
        (
            {"notebook_exists": True, "evidence_refs": ["provider-readback://nb-1"]},
            "evidence that does not cover every postcondition",
        ),
        (
            {"notebook_exists": True, "minimum_sources": 2,
             "evidence_refs": ["provider-readback://nb-1"]},
            "a numeric postcondition the observation falls short of",
        ),
        (
            {"notebook_exists": False, "minimum_sources": 7,
             "evidence_refs": ["provider-readback://nb-1"]},
            "the thing that was supposed to exist does not",
        ),
    ],
)
async def test_success_cannot_be_claimed_with_a_hollow_receipt(tmp_path, observed, why):
    """Attack 2: make the observation say something, but not enough."""
    svc = await _service(tmp_path, _registry(observed))
    mission = await _drive_to_verifying(svc, await _mission(svc, success_contract=CHECKABLE))
    with pytest.raises(MissionError, match="VERIFICATION_INSUFFICIENT"):
        await svc.transition(mission.mission_id, target=MissionState.VERIFIED_SUCCESS)


async def test_an_unreachable_target_is_not_a_pass(tmp_path):
    """Attack 2b: make the check impossible and hope silence reads as consent."""
    svc = await _service(tmp_path, _registry(raises=ConnectionError("provider down")))
    mission = await _drive_to_verifying(svc, await _mission(svc, success_contract=CHECKABLE))
    with pytest.raises(MissionError, match="VERIFICATION_INSUFFICIENT"):
        await svc.transition(mission.mission_id, target=MissionState.VERIFIED_SUCCESS)


async def test_a_caller_cannot_hand_in_its_own_receipt(tmp_path):
    """Attack 4, and the one the audit actually used: write the receipt yourself.

    The probe reached VERIFIED_SUCCESS with `verifier_version: "i-say-so/1.0"` and
    `evidence_refs: ["evidence://trust-me"]`. There is now no parameter to put that in.
    """
    svc = await _service(tmp_path, _registry(GOOD_OBSERVATION))
    mission = await _drive_to_verifying(svc, await _mission(svc, success_contract=CHECKABLE))
    forged = VerificationRecord(
        status=VerificationStatus.VERIFIED,
        observed_postconditions={"notebook_exists": True, "minimum_sources": 99},
        evidence_refs=["evidence://trust-me"],
        verifier_version="i-say-so/1.0",
        verified_at_ms=1,
    )
    with pytest.raises(TypeError):
        await svc.transition(
            mission.mission_id, target=MissionState.VERIFIED_SUCCESS, verification=forged
        )

    # And the receipt that does get stored is the adapter's, never the caller's.
    await svc.transition(mission.mission_id, target=MissionState.VERIFIED_SUCCESS)
    stored = await svc.verification_record(mission.mission_id)
    assert stored.verifier_version == "notebook.readback/1"
    assert stored.evidence_refs == ["provider-readback://nb-1"]


async def test_success_cannot_be_claimed_when_nothing_was_ever_checkable(tmp_path):
    """Attack 3: write a contract that asks nothing, then satisfy it.

    A mission with no checkable postcondition has finished, not succeeded — so
    the honest terminal is UNVERIFIABLE, and it is still reachable.
    """
    svc = await _service(tmp_path, _registry(GOOD_OBSERVATION))
    mission = await _drive_to_verifying(svc, await _mission(svc))
    with pytest.raises(MissionError, match="SUCCESS_CONTRACT_NOT_CHECKABLE"):
        await svc.transition(mission.mission_id, target=MissionState.VERIFIED_SUCCESS)
    unverifiable = await svc.transition(
        mission.mission_id, target=MissionState.UNVERIFIABLE
    )
    assert unverifiable.state is MissionState.UNVERIFIABLE
    assert (await svc.verification_record(mission.mission_id)).status is (
        VerificationStatus.UNVERIFIABLE
    )


async def test_an_earned_success_is_recorded_with_its_evidence(tmp_path):
    """And the receipt is retrievable afterwards, not just consulted once."""
    svc = await _service(tmp_path, _registry(GOOD_OBSERVATION))
    mission = await _drive_to_verifying(svc, await _mission(svc, success_contract=CHECKABLE))
    done = await svc.transition(
        mission.mission_id, target=MissionState.VERIFIED_SUCCESS,
        final_outcome="notebook created with 7 sources",
    )
    assert done.state is MissionState.VERIFIED_SUCCESS
    assert done.verification_state is VerificationStatus.VERIFIED
    assert done.final_outcome == "notebook created with 7 sources"

    stored = await svc.verification_record(mission.mission_id)
    assert stored is not None and stored.supports_success
    assert stored.evidence_refs == ["provider-readback://nb-1"]

    events = await svc.events(mission.mission_id)
    completed = [e for e in events if e.event_type is MissionEventType.MISSION_COMPLETED]
    assert len(completed) == 1
    assert completed[0].evidence_ref == "provider-readback://nb-1"


# ----------------------------------------------- activities and the timeline


async def test_an_activity_references_its_executor_rather_than_absorbing_it(tmp_path):
    """§5 — the specialist subsystem stays authoritative for its own detail."""
    svc = await _service(tmp_path)
    mission = await _mission(svc)
    activity = await svc.add_activity(
        mission_id=mission.mission_id, activity_type="browser.read",
        capability_id="browser.semantic.extract", executor="BROWSER_FABRIC",
        executor_ref="btask_abc123", authority_ref="cmd-owner-1",
    )
    assert activity.state is ActivityState.PENDING
    assert activity.executor_ref == "btask_abc123"
    assert [a.activity_id for a in await svc.activities(mission.mission_id)] == [
        activity.activity_id
    ]


async def test_activity_states_write_the_owner_timeline(tmp_path):
    svc = await _service(tmp_path)
    mission = await _mission(svc)
    activity = await svc.add_activity(
        mission_id=mission.mission_id, activity_type="research.search",
        capability_id="research.exa", executor="RESEARCH",
    )
    await svc.set_activity_state(activity.activity_id, state=ActivityState.RUNNING)
    await svc.set_activity_state(
        activity.activity_id, state=ActivityState.COMPLETED,
        evidence_ref="research-evidence://r1",
    )
    types = [e.event_type for e in await svc.events(mission.mission_id)]
    assert MissionEventType.ACTIVITY_STARTED in types
    assert MissionEventType.ACTIVITY_COMPLETED in types
    stored = (await svc.activities(mission.mission_id))[0]
    assert stored.state is ActivityState.COMPLETED
    assert stored.ended_at_ms is not None


async def test_a_terminal_mission_accepts_no_new_work(tmp_path):
    svc = await _service(tmp_path)
    mission = await _mission(svc)
    await svc.transition(mission.mission_id, target=MissionState.CANCELLED)
    with pytest.raises(MissionError, match="TERMINAL"):
        await svc.add_activity(
            mission_id=mission.mission_id, activity_type="x", capability_id="y", executor="z"
        )


# -------------------------------------------------------------- read models


async def test_needs_owner_feeds_the_unified_decision_surface(tmp_path):
    """§33 — Needs You reads missions waiting on the owner, nothing else."""
    svc = await _service(tmp_path)
    waiting = await _mission(svc, title="waiting")
    for target in (MissionState.UNDERSTOOD, MissionState.PLANNED, MissionState.AUTHORIZED,
                   MissionState.RUNNING, MissionState.WAITING_FOR_OWNER):
        await svc.transition(waiting.mission_id, target=target)
    running = await _mission(svc, title="running")
    for target in (MissionState.UNDERSTOOD, MissionState.PLANNED, MissionState.AUTHORIZED,
                   MissionState.RUNNING):
        await svc.transition(running.mission_id, target=target)

    needs = await svc.needs_owner()
    assert [m.title for m in needs] == ["waiting"]
    assert needs[0].needs_owner is True
    # And the wait is resumable, which is the whole point of it being non-terminal.
    resumed = await svc.transition(
        waiting.mission_id, target=MissionState.RESUME_AUTHORIZED,
        actor=PrincipalType.OWNER_DEVICE,
    )
    assert resumed.state is MissionState.RESUME_AUTHORIZED
    assert await svc.needs_owner() == []


async def test_missions_are_listable_by_owner_and_state(tmp_path):
    svc = await _service(tmp_path)
    await _mission(svc, title="mine", owner_principal_id="owner")
    await _mission(svc, title="theirs", owner_principal_id="someone-else")
    mine = await svc.list_missions(owner_principal_id="owner")
    assert [m.title for m in mine] == ["mine"]
    captured = await svc.list_missions(states=[MissionState.CAPTURED])
    assert len(captured) == 2


async def test_the_authority_envelope_is_carried_not_granted(tmp_path):
    """§2.2 — the Gateway stays authoritative; this is a record, not a grant."""
    svc = await _service(tmp_path)
    mission = await _mission(
        svc,
        authority_envelope=AuthorityEnvelope(
            max_action_class=ActionClass.A3, source_command_id="cmd-owner-1",
            allowed_domains=["reports.example.com"],
        ),
    )
    stored = await svc.get(mission.mission_id)
    assert stored.authority_envelope.max_action_class is ActionClass.A3
    assert stored.authority_envelope.source_command_id == "cmd-owner-1"
    assert stored.authority_envelope.permits_mutation is True


async def test_a_goal_is_required(tmp_path):
    svc = await _service(tmp_path)
    with pytest.raises(MissionError, match="GOAL_REQUIRED"):
        await _mission(svc, goal="   ")
