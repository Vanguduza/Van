"""Semantic Browser Fabric closure: Stagehand proposes, VAN decides, Harness observes."""

from __future__ import annotations

import pytest

from conftest_automation import make_store
from van_gateway.browser.models import (
    AutonomyTier,
    BrowserObservation,
    BrowserStrategy,
)
from van_gateway.browser.service import BrowserTaskService
from van_gateway.browser.subagent import (
    BrowserSubagentRunner,
    SubagentAssignment,
    SubagentStop,
)
from van_gateway.browser.worker import HybridBrowserWorker
from van_gateway.models import ActionClass

DOMAIN = "research.example.com"


class FakeHarness:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def page_info(self, task):
        self.calls.append("page_info")
        return {
            "url": f"https://{DOMAIN}/report",
            "title": "Report",
            "extraction": {"visible_text": "Quarterly report 2026"},
        }


class FakeStagehand:
    def __init__(self, controls: list[list[dict]]) -> None:
        self.controls = list(controls)
        self.observed: list[str] = []
        self.acted: list[dict] = []

    async def observe(self, task, instruction):
        self.observed.append(instruction)
        controls = self.controls.pop(0) if self.controls else []
        return BrowserObservation(task_id=task.task_id, controls=controls)

    async def act(self, task, action):
        self.acted.append(dict(action))
        return {"acted": True}


async def _task(tmp_path):
    store = await make_store(tmp_path)
    service = BrowserTaskService(store)
    await service.broker.register_profile(profile_alias="public_research")
    return await service.create_task(
        profile_alias="public_research",
        strategy=BrowserStrategy.STAGEHAND,
        autonomy_tier=AutonomyTier.L5_STAGEHAND_AGENT,
        action_class=ActionClass.A2,
        target_domain=DOMAIN,
        goal="find the quarterly report",
    )


def _assignment(task, **overrides):
    values = dict(
        turn_id="turn-semantic",
        command_id="cmd-semantic",
        task_id=task.task_id,
        goal="find the quarterly report",
        allowed_domains=[DOMAIN],
        action_class_ceiling=ActionClass.A2,
        autonomy_tier=AutonomyTier.L5_STAGEHAND_AGENT,
        max_steps=5,
    )
    values.update(overrides)
    return SubagentAssignment(**values)


@pytest.mark.asyncio
async def test_semantic_assignment_is_one_stagehand_action_per_gateway_step(tmp_path):
    task = await _task(tmp_path)
    action = {
        "description": "Open the quarterly report",
        "method": "click",
        "arguments": [],
        "selector": "xpath=//a[@id='quarterly-report']",
    }
    stagehand = FakeStagehand([[action], []])
    harness = FakeHarness()
    worker = HybridBrowserWorker(harness, stagehand, task=task)  # type: ignore[arg-type]

    result = await BrowserSubagentRunner().run(
        assignment=_assignment(task), worker=worker, task=task
    )

    assert result.stop_reason is SubagentStop.GOAL_ACHIEVED
    assert result.step_count == 1
    assert stagehand.acted == [action]
    assert harness.calls == ["page_info"]
    assert len(stagehand.observed) == 2
    assert "Step: 1 of 5" in stagehand.observed[0]
    assert "Step: 2 of 5" in stagehand.observed[1]


@pytest.mark.asyncio
async def test_stagehand_payment_proposal_is_refused_before_it_can_act(tmp_path):
    task = await _task(tmp_path)
    stagehand = FakeStagehand([[
        {
            "description": "Complete checkout and pay for the subscription",
            "method": "click",
            "arguments": [],
            "selector": "xpath=//button[@id='pay']",
        }
    ]])
    worker = HybridBrowserWorker(FakeHarness(), stagehand, task=task)  # type: ignore[arg-type]

    result = await BrowserSubagentRunner().run(
        assignment=_assignment(task), worker=worker, task=task
    )

    assert result.stop_reason is SubagentStop.PAYMENT_REFUSED
    assert stagehand.acted == []


@pytest.mark.asyncio
async def test_stagehand_cannot_supply_a_second_domain_through_its_action_payload(tmp_path):
    task = await _task(tmp_path)
    stagehand = FakeStagehand([[
        {
            "description": "Open the result",
            "method": "click",
            "selector": "xpath=//a",
            "domain": "evil.example",
        }
    ]])
    worker = HybridBrowserWorker(FakeHarness(), stagehand, task=task)  # type: ignore[arg-type]
    proposal = await worker.propose(_assignment(task), [])

    assert proposal.domain == DOMAIN
    assert proposal.payload["stagehand_action"]["domain"] == "evil.example"
    # Only the canonical proposal field is authority-bearing; payload is replay data.
    assert proposal.action_class is ActionClass.A2


def test_stagehand_internal_agent_loop_is_not_the_gateway_worker():
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1]
        / "van_gateway" / "browser" / "worker.py"
    ).read_text(encoding="utf-8")
    assert ".agent(" not in source
    assert "one observed action" in source
