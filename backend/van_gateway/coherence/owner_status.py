"""One owner-facing work status, and a total mapping onto it from every subsystem.

P2-COH-001: eleven vocabularies describe work in progress — MissionState, ActivityState,
ExecutionStatus, RunStatus, BrowserTaskStatus, DecisionStatus, IdempotencyStatus,
AttentionState, KnowledgeOperationStatus, OperationState and the Android command status.
Nothing projected them onto anything the owner could read, so every surface invented its
own rendering and the renderings disagreed.

Two rules make this a control rather than another vocabulary:

**The mapping is total and CI proves it.** Every member of every projected enum has an
entry. A test iterates the enums themselves, so adding a status without deciding what it
means to the owner fails the build. That is the only way a projection stays true as the
subsystems grow.

**There is no benign default.** A status this module does not recognise projects to
`UNKNOWN`, never to something reassuring. Finding P0-EXEC-003 is exactly the other
behaviour on the device — an unrecognised gateway status fell through to `ACCEPTED`, so
every unmapped state read to the owner as "under way". A projection that guesses in the
optimistic direction is worse than no projection, because it is confidently wrong.

The distinctions kept here are the ones the owner acts on differently, no more: whether
they must do something, whether work is under way, whether it finished, and — separately,
because the audit proved the difference is where success claims go wrong — whether
finishing was *verified*, only partly achieved, or could not be checked at all.
"""

from __future__ import annotations

from enum import Enum

from van_gateway.action.models import ExecutionStatus
from van_gateway.automation.models import RunStatus
from van_gateway.browser.models import BrowserTaskStatus
from van_gateway.computer_use.fabric import OperationState
from van_gateway.decisions.service import DecisionStatus
from van_gateway.knowledge.models import KnowledgeOperationStatus
from van_gateway.mission.models import ActivityState, MissionState
from van_gateway.models import AttentionState


class OwnerWorkStatus(str, Enum):
    """What VAN tells the owner about a piece of work."""

    WAITING_ON_YOU = "WAITING_ON_YOU"
    WORKING = "WORKING"
    WAITING_ON_SOMETHING_ELSE = "WAITING_ON_SOMETHING_ELSE"
    DONE = "DONE"
    DONE_WITH_GAPS = "DONE_WITH_GAPS"
    COULD_NOT_VERIFY = "COULD_NOT_VERIFY"
    FAILED = "FAILED"
    STOPPED = "STOPPED"
    #: P0-EXEC-002 — VAN handed the work to something and the deadline passed with no
    #: result. Deliberately not STOPPED: "stopped before finishing" tells the owner that
    #: something ended it, and STOPPED is not in NEEDS_OWNER, so a command that simply
    #: vanished would never reach their attention queue — which is exactly the silent
    #: non-execution this exists to make visible. Deliberately not FAILED either: VAN does
    #: not know that it failed. It knows it never heard back.
    NEVER_HEARD_BACK = "NEVER_HEARD_BACK"
    REFUSED = "REFUSED"
    UNKNOWN = "UNKNOWN"


#: One sentence per status, in the second person, describing the owner's actual situation.
#: Kept here rather than on the device so every surface says the same thing.
SENTENCE: dict[OwnerWorkStatus, str] = {
    OwnerWorkStatus.WAITING_ON_YOU: "Waiting for you",
    OwnerWorkStatus.WORKING: "Working on it",
    OwnerWorkStatus.WAITING_ON_SOMETHING_ELSE: "Waiting on something outside VAN",
    OwnerWorkStatus.DONE: "Done, and checked",
    OwnerWorkStatus.DONE_WITH_GAPS: "Partly done — some of it did not happen",
    OwnerWorkStatus.COULD_NOT_VERIFY: "Finished, but VAN could not confirm it worked",
    OwnerWorkStatus.FAILED: "Did not work",
    OwnerWorkStatus.STOPPED: "Stopped before finishing",
    OwnerWorkStatus.NEVER_HEARD_BACK: "VAN handed this over and never heard back",
    OwnerWorkStatus.REFUSED: "Refused — VAN would not do this",
    OwnerWorkStatus.UNKNOWN: "VAN does not know the state of this",
}

#: Statuses that should surface in the owner's attention queue rather than sit in a list.
NEEDS_OWNER = frozenset({
    OwnerWorkStatus.WAITING_ON_YOU,
    OwnerWorkStatus.DONE_WITH_GAPS,
    OwnerWorkStatus.COULD_NOT_VERIFY,
    OwnerWorkStatus.FAILED,
    OwnerWorkStatus.NEVER_HEARD_BACK,
    OwnerWorkStatus.REFUSED,
    OwnerWorkStatus.UNKNOWN,
})

#: Statuses that mean the work is over, however it ended.
FINISHED = frozenset({
    OwnerWorkStatus.DONE,
    OwnerWorkStatus.DONE_WITH_GAPS,
    OwnerWorkStatus.COULD_NOT_VERIFY,
    OwnerWorkStatus.FAILED,
    OwnerWorkStatus.STOPPED,
    OwnerWorkStatus.NEVER_HEARD_BACK,
    OwnerWorkStatus.REFUSED,
})

_W = OwnerWorkStatus

MISSION: dict[MissionState, OwnerWorkStatus] = {
    MissionState.CAPTURED: _W.WORKING,
    MissionState.UNDERSTOOD: _W.WORKING,
    MissionState.PLANNED: _W.WORKING,
    MissionState.AUTHORIZED: _W.WORKING,
    MissionState.RUNNING: _W.WORKING,
    MissionState.WAITING_EXTERNAL: _W.WAITING_ON_SOMETHING_ELSE,
    MissionState.WAITING_FOR_OWNER: _W.WAITING_ON_YOU,
    MissionState.RESUME_AUTHORIZED: _W.WORKING,
    MissionState.VERIFYING: _W.WORKING,
    MissionState.VERIFIED_SUCCESS: _W.DONE,
    MissionState.PARTIAL_SUCCESS: _W.DONE_WITH_GAPS,
    MissionState.FAILED: _W.FAILED,
    MissionState.CANCELLED: _W.STOPPED,
    MissionState.EXPIRED: _W.NEVER_HEARD_BACK,
    MissionState.BLOCKED_POLICY: _W.REFUSED,
    MissionState.BLOCKED_UNSAFE: _W.REFUSED,
    MissionState.UNVERIFIABLE: _W.COULD_NOT_VERIFY,
}

ACTIVITY: dict[ActivityState, OwnerWorkStatus] = {
    ActivityState.PENDING: _W.WORKING,
    ActivityState.RUNNING: _W.WORKING,
    ActivityState.CHECKPOINTED: _W.WORKING,
    ActivityState.WAITING: _W.WAITING_ON_SOMETHING_ELSE,
    ActivityState.COMPLETED: _W.DONE,
    ActivityState.FAILED: _W.FAILED,
    # A skipped step is not a success and not a failure; the mission it belongs to is
    # where the owner learns whether that mattered.
    ActivityState.SKIPPED: _W.STOPPED,
}

EXECUTION: dict[ExecutionStatus, OwnerWorkStatus] = {
    ExecutionStatus.RECEIVED: _W.WORKING,
    ExecutionStatus.RESOLVING: _W.WORKING,
    ExecutionStatus.CONTEXT_READY: _W.WORKING,
    ExecutionStatus.PLANNED: _W.WORKING,
    ExecutionStatus.AUTHORIZED: _W.WORKING,
    ExecutionStatus.PREFLIGHT_PASSED: _W.WORKING,
    ExecutionStatus.EXECUTING: _W.WORKING,
    ExecutionStatus.SUBMITTED: _W.WAITING_ON_SOMETHING_ELSE,
    ExecutionStatus.VERIFYING: _W.WORKING,
    ExecutionStatus.VERIFIED_SUCCESS: _W.DONE,
    ExecutionStatus.UNVERIFIABLE: _W.COULD_NOT_VERIFY,
    ExecutionStatus.CONTEXT_INSUFFICIENT: _W.WAITING_ON_YOU,
    ExecutionStatus.AUTHORIZATION_REQUIRED: _W.WAITING_ON_YOU,
    ExecutionStatus.PRECONDITION_FAILED: _W.FAILED,
    ExecutionStatus.EXECUTION_FAILED: _W.FAILED,
    # The action ran and the check did not pass. That is not "failed to run", and the
    # owner needs to know the difference before deciding whether to retry.
    ExecutionStatus.VERIFICATION_FAILED: _W.COULD_NOT_VERIFY,
    ExecutionStatus.PARTIAL_SUCCESS: _W.DONE_WITH_GAPS,
    ExecutionStatus.CONFLICTED_STATE: _W.WAITING_ON_YOU,
    ExecutionStatus.RETRYABLE_FAILURE: _W.FAILED,
    ExecutionStatus.DENIED: _W.REFUSED,
    ExecutionStatus.EXPIRED: _W.NEVER_HEARD_BACK,
    ExecutionStatus.REVOKED: _W.STOPPED,
}

AUTOMATION_RUN: dict[RunStatus, OwnerWorkStatus] = {
    RunStatus.PENDING: _W.WORKING,
    RunStatus.DISPATCHED: _W.WORKING,
    RunStatus.SUBMITTED: _W.WAITING_ON_SOMETHING_ELSE,
    RunStatus.VERIFYING: _W.WORKING,
    RunStatus.VERIFIED_SUCCESS: _W.DONE,
    RunStatus.UNVERIFIABLE: _W.COULD_NOT_VERIFY,
    RunStatus.PARTIAL_SUCCESS: _W.DONE_WITH_GAPS,
    RunStatus.FAILED: _W.FAILED,
    RunStatus.CANCELLED: _W.STOPPED,
    # A run that exhausted its retries and was set aside is a failure the owner owns now.
    RunStatus.DEAD_LETTER: _W.FAILED,
}

BROWSER_TASK: dict[BrowserTaskStatus, OwnerWorkStatus] = {
    BrowserTaskStatus.PENDING: _W.WORKING,
    BrowserTaskStatus.LEASED: _W.WORKING,
    BrowserTaskStatus.RUNNING: _W.WORKING,
    BrowserTaskStatus.WAITING_FOR_OWNER: _W.WAITING_ON_YOU,
    BrowserTaskStatus.RESUME_AUTHORIZED: _W.WORKING,
    BrowserTaskStatus.VERIFYING: _W.WORKING,
    # COMPLETED here means the browser finished its task, not that a verifier confirmed
    # the outcome. The mission that owns the task is where a verified success is claimed.
    BrowserTaskStatus.COMPLETED: _W.DONE,
    BrowserTaskStatus.FAILED: _W.FAILED,
    BrowserTaskStatus.DENIED: _W.REFUSED,
    BrowserTaskStatus.BLOCKED_POLICY: _W.REFUSED,
    BrowserTaskStatus.BLOCKED_UNSAFE: _W.REFUSED,
    BrowserTaskStatus.CANCELLED: _W.STOPPED,
    BrowserTaskStatus.EXPIRED: _W.STOPPED,
}

COMPUTER_OPERATION: dict[OperationState, OwnerWorkStatus] = {
    OperationState.PENDING: _W.WORKING,
    OperationState.RUNNING: _W.WORKING,
    OperationState.CHECKPOINTED: _W.WORKING,
    OperationState.COMPLETED: _W.DONE,
    OperationState.FAILED: _W.FAILED,
    OperationState.BLOCKED_POLICY: _W.REFUSED,
    OperationState.BLOCKED_UNSAFE: _W.REFUSED,
}

KNOWLEDGE: dict[KnowledgeOperationStatus, OwnerWorkStatus] = {
    KnowledgeOperationStatus.PREFLIGHT: _W.WORKING,
    KnowledgeOperationStatus.SUBMITTED: _W.WAITING_ON_SOMETHING_ELSE,
    KnowledgeOperationStatus.VERIFYING: _W.WORKING,
    KnowledgeOperationStatus.VERIFIED_SUCCESS: _W.DONE,
    # Something the owner must set up. Not a failure of the work itself.
    KnowledgeOperationStatus.CONFIGURATION_REQUIRED: _W.WAITING_ON_YOU,
    KnowledgeOperationStatus.EXECUTION_FAILED: _W.FAILED,
    KnowledgeOperationStatus.VERIFICATION_FAILED: _W.COULD_NOT_VERIFY,
    KnowledgeOperationStatus.RETRYABLE_FAILURE: _W.FAILED,
    KnowledgeOperationStatus.CONFLICTED_STATE: _W.WAITING_ON_YOU,
}

DECISION: dict[DecisionStatus, OwnerWorkStatus] = {
    DecisionStatus.OPEN: _W.WAITING_ON_YOU,
    DecisionStatus.APPROVED: _W.DONE,
    DecisionStatus.REJECTED: _W.REFUSED,
    DecisionStatus.EXPIRED: _W.STOPPED,
}

ATTENTION: dict[AttentionState, OwnerWorkStatus] = {
    AttentionState.OPEN: _W.WAITING_ON_YOU,
    AttentionState.ACKNOWLEDGED: _W.WAITING_ON_YOU,
    AttentionState.SNOOZED: _W.WAITING_ON_YOU,
    AttentionState.WAITING_ON_OTHERS: _W.WAITING_ON_SOMETHING_ELSE,
    AttentionState.HANDLED: _W.DONE,
    # Nobody dealt with it and it aged out. Saying "done" would be the optimistic lie.
    AttentionState.STALE: _W.STOPPED,
    AttentionState.AUTO_RESOLVED: _W.DONE,
}

#: Every vocabulary that describes owner-visible work, by the name a caller uses.
PROJECTIONS: dict[str, dict] = {
    "mission": MISSION,
    "activity": ACTIVITY,
    "execution": EXECUTION,
    "automation_run": AUTOMATION_RUN,
    "browser_task": BROWSER_TASK,
    "computer_operation": COMPUTER_OPERATION,
    "knowledge_operation": KNOWLEDGE,
    "decision": DECISION,
    "attention": ATTENTION,
}

#: The eleventh vocabulary, excluded on purpose. IdempotencyStatus describes a claim on a
#: request key, not a piece of work: COMPLETED means the gateway finished handling the
#: request, which is true whether the command succeeded, was denied or was refused. Mapping
#: it onto an owner status would put a reassuring word next to a refusal. The exclusion is
#: named rather than silent so the next reader knows it was a decision.
NOT_OWNER_WORK = {
    "idempotency": "a claim on a request key, not a piece of work",
}


def project(vocabulary: str, status: object) -> OwnerWorkStatus:
    """The owner-facing status for a subsystem status, or UNKNOWN.

    Never guesses in the optimistic direction. An unrecognised vocabulary or an
    unrecognised member both yield UNKNOWN, which the owner surfaces as "VAN does not know
    the state of this" and which the attention queue picks up.
    """
    table = PROJECTIONS.get(vocabulary)
    if table is None:
        return OwnerWorkStatus.UNKNOWN
    return table.get(status, OwnerWorkStatus.UNKNOWN)


def describe(vocabulary: str, status: object) -> dict[str, object]:
    """The projection plus everything a surface needs to render it without deciding."""
    owner_status = project(vocabulary, status)
    return {
        "owner_status": owner_status.value,
        "owner_sentence": SENTENCE[owner_status],
        "needs_owner": owner_status in NEEDS_OWNER,
        "finished": owner_status in FINISHED,
    }


__all__ = [
    "ATTENTION",
    "ACTIVITY",
    "AUTOMATION_RUN",
    "BROWSER_TASK",
    "COMPUTER_OPERATION",
    "DECISION",
    "EXECUTION",
    "FINISHED",
    "KNOWLEDGE",
    "MISSION",
    "NEEDS_OWNER",
    "NOT_OWNER_WORK",
    "PROJECTIONS",
    "SENTENCE",
    "OwnerWorkStatus",
    "describe",
    "project",
]
