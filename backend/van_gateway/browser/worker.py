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
from van_gateway.browser.subagent import ProposedAction, SubagentAssignment, SubagentStep


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
        return ProposedAction(
            kind=step.kind,
            domain=step.domain,
            # Never above the assignment's ceiling. The runner enforces this too; proposing
            # something it will refuse is a wasted step and a confusing stop reason.
            action_class=assignment.action_class_ceiling,
            url=step.url,
            instruction=step.instruction,
            rationale=step.rationale or f"planned step {index + 1}",
        )

    # ---------------------------------------------------------------- execute

    async def execute(
        self, assignment: SubagentAssignment, action: ProposedAction
    ) -> BrowserObservation:
        task = self.task
        if task is None:
            raise BrowserAdapterError("BROWSER_WORKER_TASK_MISSING", assignment.task_id)
        index = 0  # resolved below for the steps that need their plan entry
        step = None
        for candidate_index, candidate in enumerate(self.plan.steps):
            if candidate.kind == action.kind and candidate.domain == action.domain:
                step, index = candidate, candidate_index
                break

        try:
            payload = await self._dispatch(task, action, step)
        except BrowserAdapterError as exc:
            # A browser that could not act did not act. Reporting an empty-but-successful
            # observation is how "the task completed" comes to mean nothing.
            return BrowserObservation(
                task_id=task.task_id,
                controls=[],
                extraction={"adapter_error": exc.code, "detail": exc.detail or ""},
                injection_assessment=InjectionAssessment.NONE_DETECTED,
                proposed_action_class=None,
            )
        return self._observation(task, action, payload)

    async def _dispatch(
        self, task: BrowserTask, action: ProposedAction, step: PlannedStep | None
    ) -> dict[str, Any]:
        kind = action.kind
        if kind == "navigate":
            if not action.url:
                raise BrowserAdapterError("BROWSER_NAVIGATE_URL_MISSING", action.kind)
            await self.adapter.navigate(task, action.url)
            return await self.adapter.page_info(task)
        if kind == "click":
            if step is None or not step.locator:
                raise BrowserAdapterError("BROWSER_LOCATOR_MISSING", kind)
            await self.adapter.click(task, step.locator)
            return await self.adapter.page_info(task)
        if kind == "fill":
            if step is None or not step.locator or not step.value_ref:
                raise BrowserAdapterError("BROWSER_FILL_REF_MISSING", kind)
            # `fill_ref`, never a literal: §367.3 forbids secret material crossing this
            # boundary, and a reference the session broker resolves is how a password is
            # typed without VAN ever holding it.
            await self.adapter.fill_ref(task, step.locator, step.value_ref)
            return await self.adapter.page_info(task)
        if kind == "read" or kind == "observe" or kind == "finish":
            return await self.adapter.page_info(task)
        if kind == "screenshot":
            return await self.adapter.screenshot(task)
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

    Stagehand never gets an opaque autonomous loop here. It proposes exactly one observed
    action, BrowserSubagentRunner checks that proposal against Hermes's immutable
    assignment, and only then does this worker replay that one observed action. The page is
    read back through Browser Harness after execution, so Stagehand cannot certify its own
    effect.

    L5 therefore means repeated semantic proposal under the gateway runner's hard bounds,
    not handing the browser to a second independent agent until it says it is finished.
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
            return ProposedAction(
                kind="finish",
                domain=task.target_domain,
                action_class=assignment.action_class_ceiling,
                done=True,
                rationale="semantic runtime found no further action for the assigned goal",
            )

        candidate = dict(observation.controls[0])
        method = str(candidate.get("method") or "act").strip().lower()
        kind = {
            "type": "fill",
            "input": "fill",
            "tap": "click",
        }.get(method, method)
        if not kind or len(kind) > 64:
            kind = "act"
        description = str(candidate.get("description") or "")[:2000]
        return ProposedAction(
            kind=kind,
            domain=task.target_domain,
            action_class=assignment.action_class_ceiling,
            instruction=description or instruction,
            rationale=description or "Stagehand semantic proposal",
            payload={"stagehand_action": candidate},
        )

    async def execute(
        self, assignment: SubagentAssignment, action: ProposedAction
    ) -> BrowserObservation:
        if assignment.autonomy_tier in DETERMINISTIC_TIERS:
            return await self._deterministic.execute(assignment, action)
        task = self.task
        if task is None:
            raise BrowserAdapterError("BROWSER_WORKER_TASK_MISSING", assignment.task_id)
        observed = action.payload.get("stagehand_action")
        if not isinstance(observed, dict) or not observed:
            raise BrowserAdapterError("STAGEHAND_OBSERVED_ACTION_MISSING", action.kind)

        await self.stagehand.act(task, dict(observed))
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
