"""P2-COH-001: one owner-facing work status, mapped from every subsystem.

Eleven vocabularies described work in progress and nothing projected them onto anything
the owner could read. These tests do two jobs: assert the projection is *total*, so a
status added to any subsystem without deciding what it means to the owner fails CI; and
assert there is no benign default, because the device's version of this defect
(P0-EXEC-003) was an unrecognised status falling through to ACCEPTED.
"""

from __future__ import annotations

from enum import Enum

import pytest

from van_gateway.action.models import ExecutionStatus
from van_gateway.automation.models import RunStatus
from van_gateway.browser.models import BrowserTaskStatus
from van_gateway.coherence import owner_status as proj
from van_gateway.coherence.owner_status import OwnerWorkStatus
from van_gateway.computer_use.fabric import OperationState
from van_gateway.decisions.service import DecisionStatus
from van_gateway.idempotency.service import IdempotencyStatus
from van_gateway.knowledge.models import KnowledgeOperationStatus
from van_gateway.mission.models import ActivityState, MissionState
from van_gateway.models import AttentionState

#: Vocabulary name -> the enum it projects. Driven off the enums themselves, which is what
#: makes the totality check bite when a subsystem grows.
VOCABULARIES: dict[str, type[Enum]] = {
    "mission": MissionState,
    "activity": ActivityState,
    "execution": ExecutionStatus,
    "automation_run": RunStatus,
    "browser_task": BrowserTaskStatus,
    "computer_operation": OperationState,
    "knowledge_operation": KnowledgeOperationStatus,
    "decision": DecisionStatus,
    "attention": AttentionState,
}


@pytest.mark.parametrize("name,enum_cls", sorted(VOCABULARIES.items()))
def test_every_member_of_every_vocabulary_is_mapped(name, enum_cls):
    """The whole point. An unmapped member is a status nobody decided how to show."""
    unmapped = [
        member.name
        for member in enum_cls
        if proj.project(name, member) is OwnerWorkStatus.UNKNOWN
    ]
    assert not unmapped, (
        f"{enum_cls.__name__} members with no owner projection: {unmapped}. "
        "Adding a subsystem status means deciding what it means to the owner."
    )


@pytest.mark.parametrize("name,enum_cls", sorted(VOCABULARIES.items()))
def test_a_projection_table_has_no_entries_for_members_that_no_longer_exist(name, enum_cls):
    """A stale entry is a mapping for a state the system can never be in."""
    table = proj.PROJECTIONS[name]
    stale = [key for key in table if key not in set(enum_cls)]
    assert not stale, f"{name} maps states {stale} that {enum_cls.__name__} no longer has"


def test_every_vocabulary_the_audit_named_is_either_projected_or_explicitly_excluded():
    """Eleven were found. Ten are owner work; the eleventh is named and reasoned about."""
    assert set(proj.PROJECTIONS) == set(VOCABULARIES)
    assert "idempotency" in proj.NOT_OWNER_WORK
    assert proj.NOT_OWNER_WORK["idempotency"]


def test_idempotency_status_is_not_reachable_through_the_projection():
    """IdempotencyStatus.COMPLETED means the request was handled, not that it worked."""
    for member in IdempotencyStatus:
        assert proj.project("idempotency", member) is OwnerWorkStatus.UNKNOWN


class TestNoBenignDefault:
    """P0-EXEC-003's defect, asserted against the projection that replaces it."""

    def test_an_unknown_status_is_unknown_not_working(self):
        assert proj.project("mission", "SOMETHING_NEW") is OwnerWorkStatus.UNKNOWN

    def test_an_unknown_vocabulary_is_unknown_not_working(self):
        assert proj.project("not_a_subsystem", MissionState.RUNNING) is OwnerWorkStatus.UNKNOWN

    def test_none_is_unknown(self):
        assert proj.project("mission", None) is OwnerWorkStatus.UNKNOWN

    def test_unknown_reaches_the_owner_rather_than_sitting_in_a_list(self):
        assert OwnerWorkStatus.UNKNOWN in proj.NEEDS_OWNER

    def test_unknown_is_not_treated_as_finished(self):
        assert OwnerWorkStatus.UNKNOWN not in proj.FINISHED


class TestTheDistinctionsThatMatter:
    """The audit's central failure was success claimed without proof. The projection must
    not quietly re-merge the states that distinguish it."""

    def test_verified_partial_and_unverifiable_stay_three_different_answers(self):
        assert len({
            proj.project("mission", MissionState.VERIFIED_SUCCESS),
            proj.project("mission", MissionState.PARTIAL_SUCCESS),
            proj.project("mission", MissionState.UNVERIFIABLE),
        }) == 3

    def test_only_a_verified_outcome_projects_to_done_for_a_mission(self):
        done = [s for s in MissionState if proj.project("mission", s) is OwnerWorkStatus.DONE]
        assert done == [MissionState.VERIFIED_SUCCESS]

    def test_an_unverifiable_result_asks_for_the_owner(self):
        assert proj.project("mission", MissionState.UNVERIFIABLE) in proj.NEEDS_OWNER

    def test_a_partial_success_asks_for_the_owner(self):
        assert proj.project("mission", MissionState.PARTIAL_SUCCESS) in proj.NEEDS_OWNER

    def test_a_refusal_is_not_a_failure(self):
        """'VAN would not do this' and 'this did not work' call for different owner action."""
        assert proj.project("mission", MissionState.BLOCKED_POLICY) is OwnerWorkStatus.REFUSED
        assert proj.project("mission", MissionState.FAILED) is OwnerWorkStatus.FAILED

    def test_verification_failed_is_not_reported_as_the_action_failing(self):
        """The action ran; the check did not pass. Retrying blindly could double an effect."""
        assert proj.project("execution", ExecutionStatus.VERIFICATION_FAILED) is (
            OwnerWorkStatus.COULD_NOT_VERIFY
        )
        assert proj.project("execution", ExecutionStatus.EXECUTION_FAILED) is (
            OwnerWorkStatus.FAILED
        )

    def test_a_stale_attention_item_is_not_reported_as_handled(self):
        assert proj.project("attention", AttentionState.STALE) is OwnerWorkStatus.STOPPED
        assert proj.project("attention", AttentionState.HANDLED) is OwnerWorkStatus.DONE

    def test_a_dead_lettered_run_is_a_failure_the_owner_owns(self):
        assert proj.project("automation_run", RunStatus.DEAD_LETTER) is OwnerWorkStatus.FAILED


class TestRenderingContract:
    def test_every_owner_status_has_a_sentence(self):
        for status in OwnerWorkStatus:
            assert proj.SENTENCE[status].strip()

    def test_the_sentences_are_distinct(self):
        assert len(set(proj.SENTENCE.values())) == len(OwnerWorkStatus)

    def test_describe_gives_a_surface_everything_it_needs(self):
        described = proj.describe("mission", MissionState.WAITING_FOR_OWNER)
        assert described == {
            "owner_status": "WAITING_ON_YOU",
            "owner_sentence": "Waiting for you",
            "needs_owner": True,
            "finished": False,
        }

    def test_no_status_is_both_finished_and_working(self):
        assert OwnerWorkStatus.WORKING not in proj.FINISHED
        assert OwnerWorkStatus.WAITING_ON_YOU not in proj.FINISHED
        assert OwnerWorkStatus.WAITING_ON_SOMETHING_ELSE not in proj.FINISHED
