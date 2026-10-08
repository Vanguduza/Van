"""The worker that actually drives a browser, instead of a caller describing one.

P2-BROW-001. Neither `browser/api.py`, `browser/service.py` nor `browser/subagent.py`
imported `browser/adapters.py`. `SubagentWorker` was a Protocol with no implementation and
`create_app` passed `worker=None`, so `POST /v1/browser/assignments` answered 503 and the
only way a browser task ever acquired evidence was for its caller to hand the evidence in.
A page snapshot in the evidence table was whatever somebody said it was.

This is the missing implementation: a worker that proposes from a plan and executes by
calling the harness adapter, so the observation the subagent loop grades is a report of
what the page did rather than a report of what the caller claimed.

Three things it deliberately does not do.

**It does not decide.** `BrowserSubagentRunner` checks every proposal against the
assignment's bounds before it executes, and that is the enforcement point. This worker
proposes; the runner decides. Putting a policy check in here would be a second copy of the
one that already works.

**It does not invent a plan.** A deterministic (L1/L2) assignment carries its steps, and
this worker walks them. Semantic tiers need a model to choose the next action, and the
model is Stagehand, which is an external runtime — `SemanticWorkerUnavailable` says so
rather than degrading to a guess.

**It does not soften an adapter failure.** A browser that could not navigate did not
navigate; the observation says so and the runner ends the task. An adapter error turned
into an empty-but-successful observation is how "the task completed" comes to mean nothing.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from van_gateway.automation.payments import looks_like_payment
from van_gateway.browser.adapters import (
    BrowserAdapterError,
    BrowserHarnessAdapter,
    StagehandAdapter,
)
from van_gateway.browser.models import (
    AutonomyTier,
    BrowserObservation,
    BrowserTask,
    InjectionAssessment,
)
from van_gateway.browser.action_risk import assess_key_press, key_activates
from van_gateway.browser.interaction_router import (
    TARGETLESS_OPERATIONS,
    HarnessTargetResolver,
    default_action_classifier,
    judged_text,
    observed_element_text,
    observed_target,
    resolve_focused_target,
    resolve_stagehand_target,
    supplementary_action_class,
)
from van_gateway.browser.task_scope import task_scope_gate
from van_gateway.browser.policy import BrowserPolicyError
from van_gateway.browser.stagehand_proposal import (
    SemanticProposalRefused,
    typed_action_from_stagehand,
)
from van_gateway.browser.subagent import (
    OwnerTakeoverRequired,
    ProposedAction,
    SubagentAssignment,
    SubagentStep,
)
from van_gateway.models import ActionClass


#: Plan-step kinds that act on a page element and so have a class of their own.
TARGETED_PLAN_KINDS = frozenset({"click", "fill", "select"})


def classify_target(
    operation: str, observed_text: str, description: str, *, target: dict[str, Any] | None = None,
) -> ActionClass:
    """The stricter of the class of the Harness-observed target and of the description.

    ``target`` is ``interaction_router.observed_target`` (the Harness element or the reason
    it did not resolve, plus the locator), so the fail-safe structural rules (review I4
    MAJOR-A, ``action_risk``) see the element's type, inputmode, maxlength and placeholder,
    not only its text. The description can only make the class stricter; an empty one is
    neutral. The router's classifier answers ``A0`` for a change-nothing operation; the
    subagent's ``ActionClass`` starts at A1, so A0 is proposed as A1. A4/A5 are returned as
    such; the caller decides whether that is an owner takeover or a runner refusal.
    """
    if target is not None:
        observed = default_action_classifier(operation, target, None)
    elif observed_text:
        observed = default_action_classifier(operation, {"label": observed_text}, None)
    else:
        observed = "A0"
    classes = [observed, supplementary_action_class(operation, description)]
    ranks = {"A0": 0, **{cls.value: index + 1 for index, cls in enumerate(ActionClass)}}
    if any(value not in ranks for value in classes):
        raise OwnerTakeoverRequired(f"ACTION_UNCLASSIFIABLE:CLASS:{classes}")
    strictest = max(classes, key=ranks.__getitem__)
    return ActionClass.A1 if strictest == "A0" else ActionClass(strictest)


def _within_ceiling(action_class: ActionClass, ceiling: ActionClass) -> bool:
    """Below A4 and within the assignment ceiling: the runner's own refusals (payment first,
    then ACTION_CLASS_VIOLATION) decide everything else before the task-scope gate."""
    order = list(ActionClass)
    return action_class not in (ActionClass.A4, ActionClass.A5) and order.index(action_class) <= order.index(ceiling)


def _binding_of(element: Any) -> dict[str, Any] | None:
    binding = element.get("binding") if isinstance(element, dict) else None
    return binding if isinstance(binding, dict) else None


def enforce_task_scope(
    task: BrowserTask | None, *, operation: str, element: dict[str, Any] | None = None,
    navigate_url: str | None = None, key: str | None = None,
) -> None:
    """Owner decision 2026-09-30 — the task-scope gate on the /assignments path. A step on a
    page (or to a destination) outside the task's recorded scope, or on a target the Harness
    did not bind, is handed to the owner (lane 4); a task with no scope fails closed."""
    violation = task_scope_gate(
        getattr(task, "scope", None), operation=operation, element=element,
        navigate_url=navigate_url, activates=key_activates(key) if operation == "press_key" else True,
    )
    if violation is not None:
        raise OwnerTakeoverRequired(f"TASK_SCOPE:{violation}")


async def _harness_act(harness: Any, method: str, *args: Any, binding: dict[str, Any] | None) -> Any:
    """Call a bound Harness actuation; a Harness refusal (the target moved, changed, was
    covered, lost focus, or the page left the task scope) is an owner takeover, not a
    worker error — nothing was actuated."""
    try:
        return await getattr(harness, method)(*args, binding=binding)
    except BrowserAdapterError as exc:
        if exc.code.endswith("_REFUSED"):
            raise OwnerTakeoverRequired(f"HARNESS_REFUSED:{exc.detail or exc.code}") from exc
        raise


async def _harness_unbound(harness: Any, method: str, *args: Any) -> Any:
    """An unbound Harness actuation (navigate, scroll). A Harness refusal — the network-effect
    guard blocked a write (owner decision 2026-09-30, ``NETWORK_WRITE_BLOCKED:<kind>``) or
    the page left the task scope — is an owner takeover, as for the bound operations."""
    try:
        return await getattr(harness, method)(*args)
    except BrowserAdapterError as exc:
        if exc.code.endswith("_REFUSED"):
            raise OwnerTakeoverRequired(f"HARNESS_REFUSED:{exc.detail or exc.code}") from exc
        raise


class SemanticWorkerUnavailable(RuntimeError):
    """A semantic tier was assigned and no semantic runtime is configured.

    Raised rather than falling back to the deterministic plan: an L4 assignment asks for
    judgement about a page, and walking a fixed list instead would be answering a different
    question while reporting success on this one.
    """


class PlannedStep(BaseModel):
    """One step of a deterministic assignment. Mirrors `ProposedAction`'s shape, because
    the runner grades the proposal and the plan has to be gradeable in the same terms."""

    kind: str
    domain: str
    url: str | None = None
    locator: str | None = None
    value_ref: str | None = None
    instruction: str | None = None
    rationale: str | None = None


class BrowserTaskPlan(BaseModel):
    """What a deterministic assignment is going to do, in order."""

    steps: list[PlannedStep] = Field(default_factory=list)


#: Tiers whose next action comes from a plan rather than from a model.
#:
#: §88's ladder keeps L0-L3 deterministic, but L2 and L3 are *Stagehand* tiers: the actions
#: are replayed or observed by the semantic runtime even though selection is fixed. This
#: worker drives the harness, so it covers the two tiers that need no Stagehand at all.
DETERMINISTIC_TIERS = frozenset({
    AutonomyTier.L0_API,
    AutonomyTier.L1_HARNESS_DETERMINISTIC,
})


class AdapterBackedWorker:
    """`SubagentWorker` over a real `BrowserHarnessAdapter`."""

    def __init__(
        self,
        adapter: BrowserHarnessAdapter,
        *,
        plan: BrowserTaskPlan | None = None,
        task: BrowserTask | None = None,
    ) -> None:
        self.adapter = adapter
        self.plan = plan or BrowserTaskPlan()
        self.task = task

    def for_task(self, task: BrowserTask, plan: BrowserTaskPlan | None) -> "AdapterBackedWorker":
        """A worker bound to one task and its plan.

        The adapter is long-lived (it holds the connection to the browser worker) and the
        task and plan are per-assignment, so binding returns a new object rather than
        mutating a shared one: two assignments running concurrently must not be able to
        overwrite each other's task id.
        """
        return AdapterBackedWorker(self.adapter, plan=plan, task=task)

    # ---------------------------------------------------------------- propose

    async def propose(
        self, assignment: SubagentAssignment, history: list[SubagentStep]
    ) -> ProposedAction:
        if assignment.autonomy_tier not in DETERMINISTIC_TIERS:
            raise SemanticWorkerUnavailable(
                f"{assignment.autonomy_tier.value} needs a semantic runtime; none is configured"
            )
        index = len(history)
        if index >= len(self.plan.steps):
            # The plan is finished. `done` is the worker's belief, and the runner still
            # decides whether the goal was achieved.
            return ProposedAction(
                kind="finish",
                domain=assignment.allowed_domains[0] if assignment.allowed_domains else "",
                action_class=assignment.action_class_ceiling,
                done=True,
                rationale="every planned step has run",
            )
        step = self.plan.steps[index]
        if step.kind == "navigate" and step.domain in assignment.allowed_domains:
            # (A step declaring a domain outside the assignment is the runner's
            # SCOPE_VIOLATION, which may ask the owner to widen the task.)
            enforce_task_scope(self.task, operation="navigate", navigate_url=step.url)
        if step.kind not in TARGETED_PLAN_KINDS:
            return ProposedAction(
                kind=step.kind,
                domain=step.domain,
                action_class=assignment.action_class_ceiling,
                url=step.url,
                instruction=step.instruction,
                rationale=step.rationale or f"planned step {index + 1}",
                payload={"plan_index": index},
            )
        # Review I3 MAJOR-1 — a planned click/fill/select was stamped with the assignment
        # ceiling and the runner's payment check read only the step's `instruction`, so
        # `click #pay-now` "Continue", `click #delete-account` and `fill #card-number` ran as
        # A2. The shared rule applies here as on router lane 1: classify what the Harness
        # observes of the target plus the locator's words (the locator alone when the
        # Harness does not report the element); the instruction can only make it stricter.
        target = await self._observed_target(step.kind, step.locator)
        observed_text = target["label"]
        instruction = step.instruction or ""
        action_class = classify_target(step.kind, observed_text, instruction, target=target)
        # The payment boundary in BrowserSubagentRunner._check reads `instruction`: give it
        # the locator and the observed target too, raw and folded, not only the plan's own
        # words (review I4 MAJOR-A: "Páy now", "#pɑy-now" reach it as "pay now").
        judged = judged_text(instruction, observed_text)
        if action_class in (ActionClass.A4, ActionClass.A5) and looks_like_payment(
            operation=step.kind, goal=judged,
        ) is None:
            # A commitment (delete an account, a card field, a pay button the payment
            # boundary cannot read) is never autonomous: hand the run to the owner. A
            # payment is left to the runner, which refuses it as PAYMENT_REFUSED first.
            raise OwnerTakeoverRequired(
                f"PLANNED_ACTION_REQUIRES_OWNER:{action_class.value}:step {index + 1}"
            )
        if _within_ceiling(action_class, assignment.action_class_ceiling):
            # A payment (A4 the boundary reads) is left to the runner, which refuses it as
            # PAYMENT_REFUSED first, and a class above the ceiling to its
            # ACTION_CLASS_VIOLATION; everything else must be a bound target in scope.
            enforce_task_scope(self.task, operation=step.kind, element=target.get("element"))
        return ProposedAction(
            kind=step.kind,
            domain=step.domain,
            # The class VAN derived, never the ceiling: the runner refuses anything above
            # the assignment's ceiling (ACTION_CLASS_VIOLATION) rather than clamping it.
            action_class=action_class,
            url=step.url,
            instruction=judged or None,
            rationale=step.rationale or f"planned step {index + 1}",
            payload={
                "plan_index": index, "harness_observed_target": observed_text or None,
                "binding": _binding_of(target.get("element")),
            },
        )

    async def _observed_target(self, operation: str, locator: str | None) -> dict[str, Any]:
        """The classifier target for the Harness-resolved element, or for the bare locator
        when the Harness does not report it — the same rule router lane 1 uses for an
        unresolved target (``action_risk`` R6: a plain-ASCII click may run, a write may not)."""
        if not locator:
            raise OwnerTakeoverRequired(f"PLANNED_ACTION_UNCLASSIFIABLE:NO_LOCATOR:{operation}")
        element = await resolve_stagehand_target(HarnessTargetResolver(self.adapter), self.task, locator)
        return observed_target(operation, element, locator)

    # ---------------------------------------------------------------- execute

    async def execute(
        self, assignment: SubagentAssignment, action: ProposedAction
    ) -> BrowserObservation:
        task = self.task
        if task is None:
            raise BrowserAdapterError("BROWSER_WORKER_TASK_MISSING", assignment.task_id)
        step = None
        plan_index = action.payload.get("plan_index") if action.payload else None
        if isinstance(plan_index, int) and not isinstance(plan_index, bool):
            # The step that was proposed (and classified) is the step that runs: the first
            # step of the same kind and domain may carry a different locator.
            if 0 <= plan_index < len(self.plan.steps):
                candidate = self.plan.steps[plan_index]
                if candidate.kind == action.kind and candidate.domain == action.domain:
                    step = candidate
        else:
            for candidate in self.plan.steps:
                if candidate.kind == action.kind and candidate.domain == action.domain:
                    step = candidate
                    break

        # An adapter failure is a failed action. Let the runner stop the assignment;
        # packaging the failure as an observation let plan exhaustion report success.
        payload = await self._dispatch(task, action, step)
        return self._observation(task, action, payload)

    async def _dispatch(
        self, task: BrowserTask, action: ProposedAction, step: PlannedStep | None
    ) -> dict[str, Any]:
        kind = action.kind
        if kind == "navigate":
            if not action.url:
                raise BrowserAdapterError("BROWSER_NAVIGATE_URL_MISSING", action.kind)
            await _harness_unbound(self.adapter, "navigate", task, action.url)
            return await self.adapter.page_info(task)
        binding = (action.payload or {}).get("binding") if action.payload else None
        if kind == "click":
            if step is None or not step.locator:
                raise BrowserAdapterError("BROWSER_LOCATOR_MISSING", kind)
            await _harness_act(self.adapter, "click", task, step.locator, binding=binding)
            return await self.adapter.page_info(task)
        if kind == "fill":
            if step is None or not step.locator or not step.value_ref:
                raise BrowserAdapterError("BROWSER_FILL_REF_MISSING", kind)
            # `fill_ref`, never a literal: §367.3 forbids secret material crossing this
            # boundary, and a reference the session broker resolves is how a password is
            # typed without VAN ever holding it.
            await _harness_act(self.adapter, "fill_ref", task, step.locator, step.value_ref, binding=binding)
            return await self.adapter.page_info(task)
        if kind == "read" or kind == "observe" or kind == "finish":
            return await self.adapter.page_info(task)
        if kind == "screenshot":
            return await self.adapter.screenshot(task)
        if kind == "network_observe":
            return await self.adapter.network_candidates(task)
        raise BrowserAdapterError("BROWSER_ACTION_UNSUPPORTED", kind)

    @staticmethod
    def _observation(
        task: BrowserTask, action: ProposedAction, payload: dict[str, Any]
    ) -> BrowserObservation:
        """Build the observation from what the adapter reported.

        `proposed_action_class` is deliberately left as whatever the *page* asked for, not
        as what the worker wants: the policy engine clamps it against the task's ceiling,
        and a worker that pre-clamped it would hide the fact that a page asked.
        """
        extraction = dict(payload.get("extraction") or {})
        # The page's own identity belongs in the observation: the runner digests the whole
        # thing per step, and an observation that omits the URL cannot distinguish "the
        # page did not change" from "we are on a different page that looks the same".
        for key in ("url", "title"):
            value = payload.get(key)
            if value is not None:
                extraction.setdefault(key, str(value))
        return BrowserObservation(
            task_id=task.task_id,
            controls=list(payload.get("controls") or []),
            extraction=extraction,
            # NONE_DETECTED is the worker's claim and the policy engine re-scans and takes
            # the stronger verdict (P1-BROW-002), so a worker cannot clear a page.
            injection_assessment=InjectionAssessment.NONE_DETECTED,
            proposed_action_class=None,
        )


class HybridBrowserWorker:
    """One worker surface for deterministic Harness and semantic Stagehand tiers.

    Owner decision 2026-09-29 §8: Stagehand must not actuate. At a semantic tier Stagehand
    ``observe()`` proposes one observed action per gateway step; ``typed_action_from_stagehand`` turns it into a
    typed Harness operation (or refuses it); BrowserSubagentRunner checks the proposal
    against Hermes's immutable assignment; then the **Browser Harness** performs it and reads
    the page back. Stagehand ``act()`` is not called on this path.

    An empty control set is a "done" *claim* (§7): the runner sends it to the independent
    verifier, and only VERIFIED ends the run as GOAL_ACHIEVED.
    """

    def __init__(
        self,
        harness: BrowserHarnessAdapter,
        stagehand: StagehandAdapter,
        *,
        plan: BrowserTaskPlan | None = None,
        task: BrowserTask | None = None,
    ) -> None:
        self.harness = harness
        self.stagehand = stagehand
        self.plan = plan or BrowserTaskPlan()
        self.task = task
        self._deterministic = AdapterBackedWorker(harness, plan=self.plan, task=task)

    def for_task(self, task: BrowserTask, plan: BrowserTaskPlan | None) -> "HybridBrowserWorker":
        return HybridBrowserWorker(
            self.harness, self.stagehand, plan=plan, task=task
        )

    async def propose(
        self, assignment: SubagentAssignment, history: list[SubagentStep]
    ) -> ProposedAction:
        if assignment.autonomy_tier in DETERMINISTIC_TIERS:
            return await self._deterministic.propose(assignment, history)
        task = self.task
        if task is None:
            raise BrowserAdapterError("BROWSER_WORKER_TASK_MISSING", assignment.task_id)

        instruction = (
            "Choose the single best next browser action for this assigned goal. "
            "If the goal is already satisfied, return no actions. "
            f"Goal: {assignment.goal}. "
            f"Step: {len(history) + 1} of {assignment.max_steps}."
        )
        observation = await self.stagehand.observe(task, instruction)
        if not observation.controls:
            # A claim, not a result: the runner verifies it before anything completes.
            return ProposedAction(
                kind="finish",
                domain=task.target_domain,
                action_class=assignment.action_class_ceiling,
                done=True,
                rationale="semantic runtime found no further action for the assigned goal",
            )

        candidate = dict(observation.controls[0])
        try:
            typed = typed_action_from_stagehand(candidate)
        except SemanticProposalRefused as exc:
            # Refused rather than replayed through Stagehand: the runner ends the run with
            # WORKER_ERROR and nothing actuated.
            raise BrowserPolicyError(f"stagehand_proposal_not_harness_executable:{exc.code}") from exc
        description = typed.description or ""
        # Reviewer I2 N-2 (the M-5 fix, on the /v1/browser/assignments path) — the class and
        # the payment boundary were judged on Stagehand's own description, and the class was
        # simply the assignment ceiling, so `//button[@id='pay-now']` described as "Continue"
        # and `#delete-account` described as "Next" were clicked as A2. The router's rule
        # applies here too: classify what the *Harness* observes of the target together with
        # the locator words; the description can only make the answer stricter.
        observed_text = ""
        target = None
        bound: dict[str, Any] | None = None
        if typed.operation == "press_key":
            # Review I5 MAJOR-3: the key goes to the focused element; classify against it.
            focused = await resolve_focused_target(HarnessTargetResolver(self.harness), task)
            if isinstance(focused, str):
                raise OwnerTakeoverRequired(f"STAGEHAND_ACTION_UNCLASSIFIABLE:{focused}")
            bound = focused
            observed_text = observed_element_text(focused, None)
            key_class = assess_key_press(typed.key, focused, resolved=True).action_class
            action_class = classify_target("click", observed_text, description, target=None)
            ranks = {c.value: i for i, c in enumerate(ActionClass)}
            if key_class not in ranks:
                raise OwnerTakeoverRequired(f"ACTION_UNCLASSIFIABLE:KEY:{key_class}")
            if ranks[key_class] > ranks[action_class.value]:
                action_class = ActionClass(key_class)
        else:
            if typed.operation not in TARGETLESS_OPERATIONS:
                element = await self._resolve_target(task, typed.selector)
                bound = element
                target = observed_target(typed.operation, element, typed.selector)
                observed_text = target["label"]
            action_class = self._classify(typed.operation, observed_text, description, target=target)
        # The payment boundary in BrowserSubagentRunner._check reads `instruction`, so it runs
        # over the same Harness-observed text the class was judged on, raw and folded.
        judged = judged_text(description, observed_text)
        if _within_ceiling(action_class, assignment.action_class_ceiling):
            enforce_task_scope(task, operation=typed.operation, element=bound, key=typed.key)
        return ProposedAction(
            kind=typed.operation,
            domain=task.target_domain,
            # The class VAN derived, never the ceiling: the runner refuses anything above
            # the assignment's ceiling (ACTION_CLASS_VIOLATION), so the ceiling caps it.
            action_class=action_class,
            instruction=judged or instruction,
            rationale=description or "Stagehand semantic proposal",
            payload={
                "stagehand_action": candidate,
                "typed": {"operation": typed.operation, "selector": typed.selector, "key": typed.key},
                "harness_observed_target": observed_text or None,
                "binding": _binding_of(bound),
            },
        )

    async def _resolve_target(self, task: BrowserTask, locator: str | None) -> dict[str, Any]:
        """The element the Harness itself reports for ``locator``; otherwise owner takeover.

        The rule is ``interaction_router.resolve_stagehand_target`` — the one the router's
        lanes use (unit G3b) — so the two paths cannot drift apart. A target VAN cannot
        observe cannot be classified, and an unclassifiable step goes to the owner.
        """
        element = await resolve_stagehand_target(HarnessTargetResolver(self.harness), task, locator)
        if isinstance(element, str):
            raise OwnerTakeoverRequired(f"STAGEHAND_ACTION_UNCLASSIFIABLE:{element}")
        return element

    @staticmethod
    def _classify(
        operation: str, observed_text: str, description: str, *, target: dict[str, Any] | None = None,
    ) -> ActionClass:
        """The stricter of the Harness-observed class and the description's class
        (``classify_target``, shared with the deterministic plan path)."""
        return classify_target(operation, observed_text, description, target=target)

    async def execute(
        self, assignment: SubagentAssignment, action: ProposedAction
    ) -> BrowserObservation:
        if assignment.autonomy_tier in DETERMINISTIC_TIERS:
            return await self._deterministic.execute(assignment, action)
        task = self.task
        if task is None:
            raise BrowserAdapterError("BROWSER_WORKER_TASK_MISSING", assignment.task_id)
        typed = action.payload.get("typed")
        if not isinstance(typed, dict) or not typed.get("operation"):
            raise BrowserAdapterError("STAGEHAND_TYPED_ACTION_MISSING", action.kind)
        operation = typed["operation"]
        binding = action.payload.get("binding")
        # The Harness is the single executor; Stagehand only proposed. It acts on the node it
        # bound when VAN classified the target (review I5 MAJOR-2/-3).
        if operation == "click":
            await _harness_act(self.harness, "click", task, str(typed["selector"]), binding=binding)
        elif operation == "press_key":
            await _harness_act(self.harness, "press", task, str(typed["key"]), binding=binding)
        elif operation == "scroll":
            await _harness_unbound(self.harness, "scroll", task, {"selector": typed.get("selector"), "direction": "down"})
        else:
            raise BrowserAdapterError("BROWSER_ACTION_UNSUPPORTED", operation)
        payload = await self.harness.page_info(task)
        return AdapterBackedWorker._observation(task, action, payload)


__all__ = [
    "DETERMINISTIC_TIERS",
    "AdapterBackedWorker",
    "HybridBrowserWorker",
    "BrowserTaskPlan",
    "PlannedStep",
    "SemanticWorkerUnavailable",
]
