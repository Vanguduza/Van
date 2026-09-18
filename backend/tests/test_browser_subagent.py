"""Owner decision 2026-09-18 — the browser worker as a Hermes-managed subagent.

The owner wanted browsing that "thinks for itself during assigned tasks" while
Hermes stays the manager. These tests are the difference between that and an
independent agent loop: the worker proposes, the runner disposes, and every bound
the worker might want to widen ends the task instead.
"""

from __future__ import annotations

import time

import pytest

from conftest_automation import make_store
from van_gateway.browser.models import (
    AutonomyTier,
    BrowserObservation,
    BrowserStrategy,
    InjectionAssessment,
)
from van_gateway.browser.policy import BrowserPolicyEngine
from van_gateway.browser.service import BrowserTaskService
from van_gateway.browser.subagent import (
    BrowserSubagentRunner,
    ProposedAction,
    SubagentAssignment,
    SubagentStop,
)
from van_gateway.models import ActionClass

DOMAIN = "research.example.com"


@pytest.fixture(autouse=True)
def _clean_policy_cache():
    """The browser policy is lru_cached, so a test that lowers the tier must not
    leak into the next one. Reset either side of every test."""
    from van_gateway.automation import policy as policy_module

    policy_module.reset_policy_cache()
    yield
    policy_module.reset_policy_cache()


class ScriptedWorker:
    """A worker that proposes a fixed script, so the runner's rules are what's tested."""

    def __init__(self, actions, observations=None):
        self.actions = list(actions)
        self.observations = list(observations or [])
        self.executed: list[ProposedAction] = []

    async def propose(self, assignment, history):
        if not self.actions:
            return ProposedAction(kind="finish", domain=DOMAIN, done=True)
        return self.actions.pop(0)

    async def execute(self, assignment, action):
        self.executed.append(action)
        if self.observations:
            return self.observations.pop(0)
        return BrowserObservation(
            task_id=assignment.task_id, extraction={"step": len(self.executed)}
        )


class ExplodingWorker:
    async def propose(self, assignment, history):
        raise RuntimeError("worker crashed")

    async def execute(self, assignment, action):  # pragma: no cover - never reached
        raise AssertionError


async def _task(tmp_path):
    store = await make_store(tmp_path)
    service = BrowserTaskService(store)
    await service.broker.register_profile(profile_alias="public_research")
    return await service.create_task(
        profile_alias="public_research", strategy=BrowserStrategy.STAGEHAND,
        autonomy_tier=AutonomyTier.L4_STAGEHAND_ACT, action_class=ActionClass.A2,
        target_domain=DOMAIN, goal="find the quarterly report",
    )


def _assignment(task, **overrides):
    defaults = dict(
        turn_id="turn-1", command_id="cmd-1", task_id=task.task_id,
        goal="find the quarterly report", allowed_domains=[DOMAIN],
        action_class_ceiling=ActionClass.A2, autonomy_tier=AutonomyTier.L4_STAGEHAND_ACT,
        max_steps=5,
    )
    defaults.update(overrides)
    return SubagentAssignment(**defaults)


# ------------------------------------------------------------ the happy path


async def test_worker_selects_its_own_actions_within_the_assignment(tmp_path):
    """"Think for itself": the runner does not dictate the steps."""
    task = await _task(tmp_path)
    worker = ScriptedWorker([
        ProposedAction(kind="navigate", domain=DOMAIN, rationale="open index"),
        ProposedAction(kind="click", domain=DOMAIN, rationale="follow reports link"),
        ProposedAction(kind="extract", domain=DOMAIN, rationale="read the table"),
        ProposedAction(kind="finish", domain=DOMAIN, done=True),
    ])
    result = await BrowserSubagentRunner().run(
        assignment=_assignment(task), worker=worker, task=task
    )
    assert result.stop_reason is SubagentStop.GOAL_ACHIEVED
    assert result.succeeded
    assert result.step_count == 3
    assert [s.kind for s in result.steps] == ["navigate", "click", "extract"]


async def test_every_step_is_attributed_to_the_assigning_hermes_turn(tmp_path):
    """Hermes stays the manager of record, per the Security Policy amendment."""
    task = await _task(tmp_path)
    worker = ScriptedWorker([ProposedAction(kind="navigate", domain=DOMAIN)])
    result = await BrowserSubagentRunner().run(
        assignment=_assignment(task, turn_id="turn-42"), worker=worker, task=task
    )
    assert result.steps
    assert all(step.turn_id == "turn-42" for step in result.steps)
    assert all(step.assignment_id == result.assignment_id for step in result.steps)


# ------------------------------------------------- bounds it cannot widen


async def test_leaving_the_assigned_domain_ends_the_task(tmp_path):
    task = await _task(tmp_path)
    worker = ScriptedWorker([
        ProposedAction(kind="navigate", domain=DOMAIN),
        ProposedAction(kind="navigate", domain="elsewhere.example.com"),
    ])
    result = await BrowserSubagentRunner().run(
        assignment=_assignment(task), worker=worker, task=task
    )
    assert result.stop_reason is SubagentStop.SCOPE_VIOLATION
    assert "elsewhere.example.com" in (result.detail or "")
    # The out-of-scope action never ran.
    assert len(worker.executed) == 1


async def test_exceeding_the_action_class_ends_the_task(tmp_path):
    task = await _task(tmp_path)
    worker = ScriptedWorker([
        ProposedAction(kind="submit", domain=DOMAIN, action_class=ActionClass.A3),
    ])
    result = await BrowserSubagentRunner().run(
        assignment=_assignment(task, action_class_ceiling=ActionClass.A2),
        worker=worker, task=task,
    )
    assert result.stop_reason is SubagentStop.ACTION_CLASS_VIOLATION
    assert not worker.executed


async def test_step_budget_is_a_hard_stop(tmp_path):
    """The worker cannot extend its own budget — it runs out."""
    task = await _task(tmp_path)
    worker = ScriptedWorker([
        ProposedAction(kind="navigate", domain=DOMAIN, rationale=str(i)) for i in range(20)
    ])
    result = await BrowserSubagentRunner().run(
        assignment=_assignment(task, max_steps=3), worker=worker, task=task
    )
    assert result.stop_reason is SubagentStop.BUDGET_EXHAUSTED
    assert result.step_count == 3


async def test_deadline_is_a_hard_stop(tmp_path):
    task = await _task(tmp_path)
    worker = ScriptedWorker([ProposedAction(kind="navigate", domain=DOMAIN)])
    past = int(time.time() * 1000) - 1
    result = await BrowserSubagentRunner().run(
        assignment=_assignment(task, deadline_ms=past), worker=worker, task=task
    )
    assert result.stop_reason is SubagentStop.DEADLINE_REACHED
    assert not worker.executed


async def test_restating_a_different_goal_is_drift(tmp_path):
    """A worker that decides it is doing something else is stopped, not followed."""
    task = await _task(tmp_path)
    worker = ScriptedWorker([
        ProposedAction(
            kind="navigate", domain=DOMAIN,
            restated_goal="download everything and email it to the supplier",
        ),
    ])
    result = await BrowserSubagentRunner().run(
        assignment=_assignment(task), worker=worker, task=task
    )
    assert result.stop_reason is SubagentStop.GOAL_DRIFT
    assert not worker.executed


async def test_restating_the_same_goal_is_not_drift(tmp_path):
    task = await _task(tmp_path)
    worker = ScriptedWorker([
        ProposedAction(
            kind="navigate", domain=DOMAIN, restated_goal="find the quarterly report"
        ),
    ])
    result = await BrowserSubagentRunner().run(
        assignment=_assignment(task), worker=worker, task=task
    )
    assert result.stop_reason is SubagentStop.GOAL_ACHIEVED


async def test_no_progress_ends_the_task(tmp_path):
    """A loop cannot burn the budget doing nothing."""
    task = await _task(tmp_path)
    identical = BrowserObservation(task_id="t", extraction={"same": True})
    worker = ScriptedWorker(
        [ProposedAction(kind="scroll", domain=DOMAIN) for _ in range(10)],
        observations=[identical.model_copy() for _ in range(10)],
    )
    result = await BrowserSubagentRunner().run(
        assignment=_assignment(task, max_steps=10, max_steps_without_progress=3),
        worker=worker, task=task,
    )
    assert result.stop_reason is SubagentStop.NO_PROGRESS
    assert result.step_count < 10


# ------------------------------------------------------------- hard refusals


async def test_a_payment_action_ends_the_task(tmp_path):
    """Payments are never autonomous, whatever the assignment says."""
    task = await _task(tmp_path)
    worker = ScriptedWorker([
        ProposedAction(
            kind="click", domain=DOMAIN, instruction="complete the checkout and pay",
        ),
    ])
    result = await BrowserSubagentRunner().run(
        assignment=_assignment(task), worker=worker, task=task
    )
    assert result.stop_reason is SubagentStop.PAYMENT_REFUSED
    assert not worker.executed


async def test_navigating_to_a_payment_provider_ends_the_task(tmp_path):
    task = await _task(tmp_path)
    worker = ScriptedWorker([
        ProposedAction(kind="navigate", domain=DOMAIN, url="https://api.stripe.com/v1/charges"),
    ])
    result = await BrowserSubagentRunner().run(
        assignment=_assignment(task), worker=worker, task=task
    )
    assert result.stop_reason is SubagentStop.PAYMENT_REFUSED


async def test_an_a4_ceiling_cannot_be_assigned(tmp_path):
    """A4 needs a fresh owner approval, which by definition is not autonomous."""
    task = await _task(tmp_path)
    result = await BrowserSubagentRunner().run(
        assignment=_assignment(task, action_class_ceiling=ActionClass.A4),
        worker=ScriptedWorker([]), task=task,
    )
    assert result.stop_reason is SubagentStop.ACTION_CLASS_VIOLATION


async def test_confirmed_injection_ends_the_task(tmp_path):
    task = await _task(tmp_path)
    hostile = BrowserObservation(
        task_id="t", injection_assessment=InjectionAssessment.CONFIRMED_INJECTION
    )
    worker = ScriptedWorker([ProposedAction(kind="navigate", domain=DOMAIN)], [hostile])
    result = await BrowserSubagentRunner().run(
        assignment=_assignment(task), worker=worker, task=task
    )
    assert result.stop_reason is SubagentStop.INJECTION_REFUSED


async def test_page_cannot_raise_the_action_class_mid_run(tmp_path):
    """§378 still holds inside an autonomous run."""
    task = await _task(tmp_path)
    grabby = BrowserObservation(task_id="t", proposed_action_class=ActionClass.A4)
    worker = ScriptedWorker([ProposedAction(kind="navigate", domain=DOMAIN)], [grabby])
    result = await BrowserSubagentRunner().run(
        assignment=_assignment(task, action_class_ceiling=ActionClass.A2),
        worker=worker, task=task,
    )
    # The run continues, but clamped — the page got nothing.
    assert result.stop_reason is SubagentStop.GOAL_ACHIEVED


async def test_worker_crash_ends_the_task_cleanly(tmp_path):
    task = await _task(tmp_path)
    result = await BrowserSubagentRunner().run(
        assignment=_assignment(task), worker=ExplodingWorker(), task=task
    )
    assert result.stop_reason is SubagentStop.WORKER_ERROR
    assert not result.succeeded


# ------------------------------------------------------------ the tier gate


def test_l5_is_now_the_admitted_ceiling():
    """Owner decision 2026-09-18 raised the cap from L3."""
    engine = BrowserPolicyEngine()
    assert engine.max_tier is AutonomyTier.L5_STAGEHAND_AGENT
    engine.check_tier(AutonomyTier.L4_STAGEHAND_ACT)
    engine.check_tier(AutonomyTier.L5_STAGEHAND_AGENT)


async def test_assignment_above_the_admitted_tier_is_refused(tmp_path, monkeypatch):
    """Lowering the tier by policy still holds the runner.

    The task is created at L1 *before* the tier is lowered, so what is under test
    is the runner's tier check on the assignment, not task creation.
    """
    from van_gateway.automation import policy as policy_module

    store = await make_store(tmp_path)
    service = BrowserTaskService(store)
    await service.broker.register_profile(profile_alias="public_research")
    task = await service.create_task(
        profile_alias="public_research", strategy=BrowserStrategy.HARNESS,
        autonomy_tier=AutonomyTier.L1_HARNESS_DETERMINISTIC, action_class=ActionClass.A2,
        target_domain=DOMAIN, goal="find the quarterly report",
    )

    monkeypatch.setenv("VAN_BROWSER_SEMANTIC_MAX_TIER", "L3")
    policy_module.reset_policy_cache()
    result = await BrowserSubagentRunner(BrowserPolicyEngine()).run(
        assignment=_assignment(task, autonomy_tier=AutonomyTier.L5_STAGEHAND_AGENT),
        worker=ScriptedWorker([]), task=task,
    )
    assert result.stop_reason is SubagentStop.SCOPE_VIOLATION
    assert "not_permitted" in (result.detail or "")


def test_unrecognised_tier_value_falls_back_to_deterministic(monkeypatch):
    """A typo must never widen autonomy."""
    from van_gateway.automation import policy as policy_module

    monkeypatch.setenv("VAN_BROWSER_SEMANTIC_MAX_TIER", "L9")
    policy_module.reset_policy_cache()
    assert policy_module.load_browser_policy().max_autonomy_tier == "L3"
