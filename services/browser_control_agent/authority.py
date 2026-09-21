"""Rev 1.5 §13.2 — what the agent checks before anything touches the browser.

§13.2 lists six things: session id, control lease, control generation, task scope, step
budget, caller service identity. This is that list as code, and it is a separate module
from the CDP transport on purpose — the transport cannot be executed in this repository
and this can, so the part that decides is the part that is tested.

Every refusal below is a named reason rather than a boolean, because the agent's caller is
another service and "denied" with no reason is a service that retries forever.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class Operation(str, Enum):
    """The whole surface. Adding to this list is how the agent stops being narrow.

    Deliberately absent, per §13.2: an arbitrary shell, a raw CDP passthrough, a
    filesystem read, a Docker socket, and any unbounded JavaScript execution primitive.
    `query_dom` returns a structured extraction, not the result of `Runtime.evaluate`.
    """

    ATTACH = "attach"
    NAVIGATE = "navigate"
    DISPATCH_INPUT = "dispatch_input"
    QUERY_DOM = "query_dom"
    QUERY_ACCESSIBILITY = "query_accessibility"
    OBSERVE_NAVIGATION = "observe_navigation"
    OBSERVE_DOWNLOAD = "observe_download"
    CAPTURE_EVIDENCE = "capture_evidence"

    @property
    def actuates(self) -> bool:
        """Whether this operation changes the page rather than reading it.

        The distinction decides what needs a live control lease. A read that required one
        would mean evidence capture fails at exactly the moment something has gone wrong
        and the lease has been preempted — which is when the evidence matters most.
        """
        return self in {Operation.ATTACH, Operation.NAVIGATE, Operation.DISPATCH_INPUT}


class Scope(str, Enum):
    """What a task was granted. A scope is a promise about the *kind* of work."""

    #: Read the page. No actuation at all.
    OBSERVE = "browser.observe"
    #: Move around and click. The ordinary automation scope.
    ACTUATE = "browser.actuate"
    #: Collect evidence for a Mission.
    EVIDENCE = "browser.evidence"


#: Which scopes admit which operations. A table rather than a chain of `if`s, because the
#: question "what can this credential do" has to be answerable by reading one thing.
SCOPE_ALLOWS: dict[Scope, frozenset[Operation]] = {
    Scope.OBSERVE: frozenset(
        {
            Operation.ATTACH,
            Operation.QUERY_DOM,
            Operation.QUERY_ACCESSIBILITY,
            Operation.OBSERVE_NAVIGATION,
            Operation.OBSERVE_DOWNLOAD,
        }
    ),
    Scope.ACTUATE: frozenset(
        {
            Operation.ATTACH,
            Operation.NAVIGATE,
            Operation.DISPATCH_INPUT,
            Operation.QUERY_DOM,
            Operation.QUERY_ACCESSIBILITY,
            Operation.OBSERVE_NAVIGATION,
            Operation.OBSERVE_DOWNLOAD,
        }
    ),
    Scope.EVIDENCE: frozenset(
        {
            Operation.ATTACH,
            Operation.QUERY_DOM,
            Operation.QUERY_ACCESSIBILITY,
            Operation.CAPTURE_EVIDENCE,
        }
    ),
}


class Refusal(str, Enum):
    UNKNOWN_CALLER = "control_agent_unknown_caller"
    CALLER_NOT_PERMITTED = "control_agent_caller_not_permitted"
    UNKNOWN_SESSION = "control_agent_unknown_session"
    LEASE_UNKNOWN = "control_agent_lease_unknown"
    LEASE_EXPIRED = "control_agent_lease_expired"
    LEASE_SUPERSEDED = "control_agent_lease_superseded"
    LEASE_NOT_HELD = "control_agent_lease_not_held_by_caller"
    OUT_OF_SCOPE = "control_agent_operation_out_of_scope"
    STEP_BUDGET_EXHAUSTED = "control_agent_step_budget_exhausted"
    TASK_FINISHED = "control_agent_task_finished"


class ControlAgentRefused(Exception):
    def __init__(self, reason: Refusal) -> None:
        super().__init__(reason.value)
        self.reason = reason


@dataclass(frozen=True)
class ServiceIdentity:
    """Who is calling, as established by the mTLS client certificate.

    The name is read from the peer certificate, never from the request body. A caller that
    could name itself is not an identity, it is a field.
    """

    common_name: str
    scopes: frozenset[Scope]


@dataclass
class ControlLease:
    """The Gateway's lease, as the agent sees it (ADR-RB-006/007).

    The generation is the whole point. An owner preemption bumps it, and an agent that was
    mid-task continues to hold a lease id that is no longer current. Checking only the id
    would let that agent keep typing into a page the owner has taken back.
    """

    lease_id: str
    session_id: str
    generation: int
    holder: str
    expires_at_ms: int


@dataclass
class TaskGrant:
    """One unit of delegated work, and the budget it may spend.

    The step budget is not a rate limit. It is the answer to "how far can this go wrong
    before someone notices": an automation that loops is bounded by this and by nothing
    else, and the bound has to be per task rather than per second or a stuck loop simply
    runs slowly forever.
    """

    task_id: str
    session_id: str
    scope: Scope
    step_budget: int
    steps_used: int = 0
    finished: bool = False
    #: Every refusal and every admitted step, for the Mission's evidence trail.
    journal: list[tuple[int, str, str]] = field(default_factory=list)

    @property
    def steps_remaining(self) -> int:
        return max(0, self.step_budget - self.steps_used)


class ControlAuthority:
    """The six checks, in the order that leaks the least.

    Order matters for what an attacker learns. Caller identity first: a service that is not
    known does not get to find out whether a session exists. Session and lease before scope,
    so a caller with the wrong scope on a session it cannot see is told about the session it
    cannot see — never.
    """

    def __init__(
        self,
        *,
        callers: dict[str, ServiceIdentity],
        leases: dict[str, ControlLease],
        tasks: dict[str, TaskGrant],
    ) -> None:
        self._callers = callers
        self._leases = leases
        self._tasks = tasks

    def authorize(
        self,
        *,
        caller_common_name: str,
        operation: Operation,
        session_id: str,
        lease_id: str,
        lease_generation: int,
        task_id: str,
        now_ms: int | None = None,
    ) -> TaskGrant:
        """Admit one operation, or raise with the reason it was refused.

        Returns the task, with its step already counted. Counting here rather than at the
        call site is deliberate: a budget decremented by the caller is a budget the caller
        controls.
        """
        now = int(time.time() * 1000) if now_ms is None else now_ms

        caller = self._callers.get(caller_common_name)
        if caller is None:
            raise ControlAgentRefused(Refusal.UNKNOWN_CALLER)

        task = self._tasks.get(task_id)
        if task is None or task.session_id != session_id:
            # Same refusal for "no such task" and "that task is not on this session": a
            # caller that can distinguish them can enumerate tasks.
            raise ControlAgentRefused(Refusal.UNKNOWN_SESSION)
        if task.finished:
            raise ControlAgentRefused(Refusal.TASK_FINISHED)

        if task.scope not in caller.scopes:
            raise ControlAgentRefused(Refusal.CALLER_NOT_PERMITTED)
        if operation not in SCOPE_ALLOWS[task.scope]:
            self._record(task, operation, Refusal.OUT_OF_SCOPE)
            raise ControlAgentRefused(Refusal.OUT_OF_SCOPE)

        if operation.actuates:
            self._check_lease(
                task=task,
                operation=operation,
                session_id=session_id,
                lease_id=lease_id,
                lease_generation=lease_generation,
                caller=caller,
                now=now,
            )

        if task.steps_remaining == 0:
            self._record(task, operation, Refusal.STEP_BUDGET_EXHAUSTED)
            raise ControlAgentRefused(Refusal.STEP_BUDGET_EXHAUSTED)

        task.steps_used += 1
        task.journal.append((now, operation.value, "admitted"))
        return task

    def _check_lease(
        self,
        *,
        task: TaskGrant,
        operation: Operation,
        session_id: str,
        lease_id: str,
        lease_generation: int,
        caller: ServiceIdentity,
        now: int,
    ) -> None:
        lease = self._leases.get(lease_id)
        if lease is None or lease.session_id != session_id:
            self._record(task, operation, Refusal.LEASE_UNKNOWN)
            raise ControlAgentRefused(Refusal.LEASE_UNKNOWN)
        if lease.expires_at_ms <= now:
            self._record(task, operation, Refusal.LEASE_EXPIRED)
            raise ControlAgentRefused(Refusal.LEASE_EXPIRED)
        if lease.generation != lease_generation:
            # ADR-RB-007. The owner took control back and this caller has not noticed.
            # Refusing on the id alone would not catch it, because the id is still the
            # one it was given.
            self._record(task, operation, Refusal.LEASE_SUPERSEDED)
            raise ControlAgentRefused(Refusal.LEASE_SUPERSEDED)
        if lease.holder != caller.common_name:
            self._record(task, operation, Refusal.LEASE_NOT_HELD)
            raise ControlAgentRefused(Refusal.LEASE_NOT_HELD)

    @staticmethod
    def _record(task: TaskGrant, operation: Operation, reason: Refusal) -> None:
        task.journal.append((int(time.time() * 1000), operation.value, reason.value))
