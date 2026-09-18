"""Owner decision 2026-09-18 — the browser worker as a Hermes-managed subagent.

In the owner's words: *"Web browsing should think for itself during assigned tasks
but with hermes as the main brain or manager so in essence it becomes hermes's
subagent."*

`docs/SECURITY_POLICY.md` keeps "Hermes profile `van` is the sole agent runtime"
literally true by defining what a subagent is: Hermes assigns the goal, the domain
scope and the step budget; the worker chooses actions inside them and cannot widen
them. That is the difference between a subordinate and an independent agent loop,
and this module is where it is enforced rather than asserted.

Every one of the following ends the task rather than escalating it:

* a step that leaves the assigned domain scope
* a step whose action class exceeds the assignment
* the step budget or the deadline running out
* the worker proposing a different goal
* anything that looks like a payment (payments are never autonomous)
"""

from __future__ import annotations

import ipaddress
import re
import time
import uuid
from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel, Field

from van_gateway.automation.canonical import digest
from van_gateway.automation.payments import PaymentBoundaryError, assert_not_automated_payment
from van_gateway.browser.models import (
    BrowserBoundaryType,
    AutonomyTier,
    BrowserObservation,
    BrowserTask,
    InjectionAssessment,
)
from van_gateway.browser.policy import BrowserPolicyEngine, BrowserPolicyError
from van_gateway.models import ActionClass

_RANK = {ActionClass.A1: 1, ActionClass.A2: 2, ActionClass.A3: 3, ActionClass.A4: 4, ActionClass.A5: 5}


class SubagentStop(str, Enum):
    """Why an autonomous run ended. Every one is terminal — none escalates."""

    GOAL_ACHIEVED = "GOAL_ACHIEVED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    DEADLINE_REACHED = "DEADLINE_REACHED"
    SCOPE_VIOLATION = "SCOPE_VIOLATION"
    ACTION_CLASS_VIOLATION = "ACTION_CLASS_VIOLATION"
    GOAL_DRIFT = "GOAL_DRIFT"
    PAYMENT_REFUSED = "PAYMENT_REFUSED"
    INJECTION_REFUSED = "INJECTION_REFUSED"
    WORKER_ERROR = "WORKER_ERROR"
    NO_PROGRESS = "NO_PROGRESS"


class SubagentAssignment(BaseModel):
    """What Hermes hands the worker. The worker cannot change any of it."""

    assignment_id: str = Field(default_factory=lambda: f"bsub_{uuid.uuid4().hex}")
    #: The Hermes turn that assigned this. Every step is attributed to it.
    turn_id: str
    command_id: str
    task_id: str

    goal: str
    #: Domains the worker may touch. Leaving them ends the task.
    allowed_domains: list[str]
    #: Ceiling for any action the worker selects.
    action_class_ceiling: ActionClass = ActionClass.A2
    autonomy_tier: AutonomyTier = AutonomyTier.L4_STAGEHAND_ACT

    #: Hard bounds. The worker cannot extend either.
    max_steps: int = Field(default=12, ge=1, le=50)
    deadline_ms: int | None = None
    #: Ends the task when the page stops changing, so a loop cannot spin the budget.
    max_steps_without_progress: int = Field(default=3, ge=1, le=10)

    @property
    def goal_digest(self) -> str:
        return digest({"goal": self.goal})


class SubagentStep(BaseModel):
    """One action the worker selected, with the attribution that makes it traceable."""

    index: int
    assignment_id: str
    turn_id: str
    kind: str
    domain: str
    action_class: ActionClass
    rationale: str | None = None
    observation_digest: str | None = None
    at_ms: int


class SubagentResult(BaseModel):
    assignment_id: str
    task_id: str
    stop_reason: SubagentStop
    steps: list[SubagentStep] = Field(default_factory=list)
    extraction: dict[str, Any] = Field(default_factory=dict)
    detail: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.stop_reason is SubagentStop.GOAL_ACHIEVED

    @property
    def step_count(self) -> int:
        return len(self.steps)


class ProposedAction(BaseModel):
    """What the worker wants to do next. A proposal, never a decision."""

    kind: str
    domain: str
    action_class: ActionClass = ActionClass.A2
    url: str | None = None
    instruction: str | None = None
    rationale: str | None = None
    #: Set when the worker believes the goal is met.
    done: bool = False
    #: If the worker restates its goal, drift is detected against the assignment.
    restated_goal: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class SubagentWorker(Protocol):
    """The semantic worker. Proposes; it does not decide."""

    async def propose(
        self, assignment: SubagentAssignment, history: list[SubagentStep]
    ) -> ProposedAction:
        ...

    async def execute(
        self, assignment: SubagentAssignment, action: ProposedAction
    ) -> BrowserObservation:
        ...


class BrowserSubagentRunner:
    """Runs an assignment to completion or to a bounded stop.

    The loop is the enforcement point. Each proposed action is checked against the
    assignment *before* it executes, so a worker that drifts is stopped rather than
    corrected-and-continued.
    """

    def __init__(self, policy: BrowserPolicyEngine | None = None) -> None:
        self.policy = policy or BrowserPolicyEngine()

    async def run(
        self,
        *,
        assignment: SubagentAssignment,
        worker: SubagentWorker,
        task: BrowserTask,
        now_ms: int | None = None,
    ) -> SubagentResult:
        # The ladder cap is a policy decision, checked once before any step.
        try:
            self.policy.check_tier(assignment.autonomy_tier)
        except BrowserPolicyError as exc:
            return SubagentResult(
                assignment_id=assignment.assignment_id, task_id=task.task_id,
                stop_reason=SubagentStop.SCOPE_VIOLATION, detail=str(exc),
            )
        if assignment.action_class_ceiling in (ActionClass.A4, ActionClass.A5):
            # An autonomous task never carries A4. That needs a fresh owner approval
            # bound to the exact action, which by definition is not autonomous.
            return SubagentResult(
                assignment_id=assignment.assignment_id, task_id=task.task_id,
                stop_reason=SubagentStop.ACTION_CLASS_VIOLATION,
                detail=f"assignment_ceiling_prohibited:{assignment.action_class_ceiling.value}",
            )

        steps: list[SubagentStep] = []
        extraction: dict[str, Any] = {}
        last_observation: str | None = None
        stagnant = 0
        now = int(time.time() * 1000) if now_ms is None else now_ms

        for index in range(assignment.max_steps):
            if assignment.deadline_ms is not None and now >= assignment.deadline_ms:
                return self._stop(assignment, task, steps, extraction, SubagentStop.DEADLINE_REACHED)

            try:
                action = await worker.propose(assignment, list(steps))
            except Exception as exc:  # noqa: BLE001 - a worker fault ends the task
                return self._stop(
                    assignment, task, steps, extraction, SubagentStop.WORKER_ERROR,
                    detail=f"{type(exc).__name__}",
                )

            if action.done:
                return self._stop(assignment, task, steps, extraction, SubagentStop.GOAL_ACHIEVED)

            violation = self._check(assignment, action)
            if violation is not None:
                stop, detail = violation
                return self._stop(assignment, task, steps, extraction, stop, detail=detail)

            try:
                observation = await worker.execute(assignment, action)
            except Exception as exc:  # noqa: BLE001
                return self._stop(
                    assignment, task, steps, extraction, SubagentStop.WORKER_ERROR,
                    detail=f"{type(exc).__name__}",
                )

            # Page content is data. It cannot raise the class or carry secrets, and
            # a page that tries to redirect the task ends it.
            try:
                observation = self.policy.sanitize_observation(
                    observation, task_action_class=assignment.action_class_ceiling
                )
            except BrowserPolicyError as exc:
                return self._stop(
                    assignment, task, steps, extraction, SubagentStop.INJECTION_REFUSED,
                    detail=str(exc),
                )
            if observation.injection_assessment is InjectionAssessment.CONFIRMED_INJECTION:
                return self._stop(
                    assignment, task, steps, extraction, SubagentStop.INJECTION_REFUSED,
                    detail="confirmed injection on page",
                )

            observation_digest = digest(observation.model_dump(mode="json"))
            steps.append(
                SubagentStep(
                    index=index, assignment_id=assignment.assignment_id,
                    turn_id=assignment.turn_id, kind=action.kind, domain=action.domain,
                    action_class=action.action_class, rationale=action.rationale,
                    observation_digest=observation_digest, at_ms=now,
                )
            )
            if observation.extraction:
                extraction.update(observation.extraction)

            stagnant = stagnant + 1 if observation_digest == last_observation else 0
            if stagnant >= assignment.max_steps_without_progress:
                return self._stop(assignment, task, steps, extraction, SubagentStop.NO_PROGRESS)
            last_observation = observation_digest
            now += 1

        return self._stop(assignment, task, steps, extraction, SubagentStop.BUDGET_EXHAUSTED)

    def _check(
        self, assignment: SubagentAssignment, action: ProposedAction
    ) -> tuple[SubagentStop, str] | None:
        """Every bound the worker cannot widen, checked before the action runs."""
        if action.domain not in assignment.allowed_domains:
            return SubagentStop.SCOPE_VIOLATION, f"domain_outside_assignment:{action.domain}"
        if _RANK[action.action_class] > _RANK[assignment.action_class_ceiling]:
            return (
                SubagentStop.ACTION_CLASS_VIOLATION,
                f"{action.action_class.value}>{assignment.action_class_ceiling.value}",
            )
        if action.restated_goal and digest({"goal": action.restated_goal}) != assignment.goal_digest:
            return SubagentStop.GOAL_DRIFT, "worker restated a different goal"
        try:
            assert_not_automated_payment(
                operation=action.kind, goal=action.instruction or "", url=action.url or "",
                domain=action.domain, context="subagent_action",
            )
        except PaymentBoundaryError as exc:
            return SubagentStop.PAYMENT_REFUSED, str(exc)
        return None

    @staticmethod
    def _stop(
        assignment: SubagentAssignment,
        task: BrowserTask,
        steps: list[SubagentStep],
        extraction: dict[str, Any],
        reason: SubagentStop,
        *,
        detail: str | None = None,
    ) -> SubagentResult:
        return SubagentResult(
            assignment_id=assignment.assignment_id, task_id=task.task_id,
            stop_reason=reason, steps=steps, extraction=extraction, detail=detail,
        )


#: §§108, 391 — classes the browser is never an execution surface for. A worker
#: that proposes one is not asking for a wider assignment; it is asking for a
#: kind of authority this surface cannot hold at any scope.
_NEVER_ON_BROWSER = frozenset({ActionClass.A4, ActionClass.A5})

#: A requested domain is rendered to the owner in an approval prompt, so it has
#: to look like a hostname before it gets there. Anything else is a worker
#: handing us free text to display, which is how an approval prompt gets
#: written by the page instead of by VAN.
#:
#: The required dot is load-bearing twice over, and the second reason is easy to
#: mistake for an oversight: it also excludes single-label hosts, so `localhost`
#: and bare machine names can never become an escalation. That is deliberate —
#: owner decision, 2026-09-18. The browser fabric exists to read the public web
#: on the owner's behalf, and a worker reaching for the VAN host's own services
#: is far more likely to be a page that led it astray than a task drawn too
#: narrowly. Admitting a local target is therefore a policy change (an explicit
#: entry in `config/browser/domains.yaml`), never a loosening of this pattern:
#: dropping the dot to reach `localhost` would re-open the free-text hole above.
_HOSTNAME = re.compile(r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))+$")


def plausible_hostname(value: str) -> bool:
    """Whether a worker-supplied domain may be shown to the owner as a question."""
    candidate = value.strip()
    try:
        ipaddress.ip_address(candidate.strip("[]"))
    except ValueError:
        pass
    else:
        # A dotted quad satisfies the pattern above while meaning something quite
        # different from a domain name: `127.0.0.1` reaches exactly where
        # `localhost` does. `AutomationPolicy._reject_literal_ip` already holds
        # the house rule — a bare literal IP is never an admitted domain — and it
        # applies here for the same reason, on the public side too: a worker that
        # names an address instead of a host has stopped browsing the web.
        return False
    return bool(_HOSTNAME.match(candidate))


def classify_boundary(
    stop_reason: SubagentStop,
    *,
    requested_action_class: ActionClass | None = None,
    requested_domain: str | None = None,
) -> BrowserBoundaryType:
    """Decide what a stop *means* before anyone is asked to act on it.

    This is the gate between "the assignment was drawn slightly too narrow",
    which is worth the owner's attention, and "the page talked the worker into
    asking for something else", which is not. The distinction matters because an
    escalation is an approval prompt, and a prompt that page content can
    manufacture is an attack surface rather than a safety feature.

    Kept pure and separate from the API so the rule can be tested directly and
    read without a database in the way.
    """
    if stop_reason in (
        SubagentStop.PAYMENT_REFUSED,
        SubagentStop.INJECTION_REFUSED,
    ):
        # §34 and §387 — asking the owner to approve these is precisely the
        # outcome the refusal exists to prevent.
        return BrowserBoundaryType.POLICY_FORBIDDEN
    if stop_reason is SubagentStop.GOAL_DRIFT:
        return BrowserBoundaryType.AMBIGUOUS_OR_UNSAFE
    if stop_reason is SubagentStop.ACTION_CLASS_VIOLATION:
        if requested_action_class is None:
            return BrowserBoundaryType.AMBIGUOUS_OR_UNSAFE
        if requested_action_class in _NEVER_ON_BROWSER:
            # No owner approval can make the browser an A4 surface, so there is
            # nothing to ask. A4 needs a fresh approval bound to the exact
            # action, which is the opposite of widening a standing assignment.
            return BrowserBoundaryType.POLICY_FORBIDDEN
        return BrowserBoundaryType.OWNER_EXTENSION_REQUIRED
    if stop_reason is SubagentStop.SCOPE_VIOLATION:
        if requested_domain is None or not plausible_hostname(requested_domain):
            return BrowserBoundaryType.AMBIGUOUS_OR_UNSAFE
        return BrowserBoundaryType.OWNER_EXTENSION_REQUIRED
    return BrowserBoundaryType.BOUNDED_SAFE_EXTENSION


__all__ = [
    "BrowserSubagentRunner",
    "classify_boundary",
    "plausible_hostname",
    "ProposedAction",
    "SubagentAssignment",
    "SubagentResult",
    "SubagentStep",
    "SubagentStop",
    "SubagentWorker",
]
