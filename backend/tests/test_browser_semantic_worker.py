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


async def _no_owner_control(_task) -> bool:
    """Review I M-4: the runner fails closed without an owner-control probe; these
    tests are about other bounds, so the owner is explicitly not holding control."""
    return False

DOMAIN = "research.example.com"


class FakeHarness:
    def __init__(self, elements: list[dict] | None = None) -> None:
        self.calls: list[str] = []
        #: What the Harness reports of the page's elements (``ref`` = the locator it acts on).
        #: Reviewer I2 N-2: a Stagehand target is classified on this, so a test that expects
        #: a click to run has to say what the Harness sees there. None = reports nothing.
        self.elements = elements

    async def describe(self, task, locator):
        """Review I5: the Harness /describe reports the element bound to its node."""
        for e in self.elements or ():
            if locator in (e.get("locator"), e.get("ref")):
                return {"element": dict(e), "matches": 1, "page_url": f"https://{DOMAIN}/report",
                        "binding": {"backend_node_id": 5, "digest": "0" * 64}}
        return {"element": None, "matches": 0}

    async def click(self, task, locator, *, binding=None):
        self.calls.append(f"click:{locator}")
        return {}

    async def press(self, task, key, *, binding=None):
        self.calls.append(f"press:{key}")
        return {}

    async def scroll(self, task, request):
        self.calls.append("scroll")
        return {}

    async def page_info(self, task):
        self.calls.append("page_info")
        page = {
            "url": f"https://{DOMAIN}/report",
            "title": "Report",
            "extraction": {"visible_text": "Quarterly report 2026"},
        }
        if self.elements is not None:
            page["elements"] = [dict(e) for e in self.elements]
        return page

    @property
    def actuations(self) -> list[str]:
        """Calls that changed the page; ``page_info`` is a read (the target resolver uses it)."""
        return [c for c in self.calls if c != "page_info"]


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


class _Verdict:
    """Independent postcondition verifier stand-in (owner decision 2026-09-29 §7)."""

    def __init__(self, outcome: str = "VERIFIED") -> None:
        self.outcome = outcome
        self.calls = 0

    async def verify(self, task, action, postcondition, *, claimed_done):
        from van_gateway.action.models import VerifierType
        from van_gateway.automation.verifier import VerificationOutcome, VerificationResult

        self.calls += 1
        return VerificationResult(outcome=VerificationOutcome(self.outcome), verifier_type=VerifierType.READ_BACK)


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
    harness = FakeHarness([{"ref": "xpath=//a[@id='quarterly-report']", "role": "link", "name": "Quarterly report"}])
    worker = HybridBrowserWorker(harness, stagehand, task=task)  # type: ignore[arg-type]

    verifier = _Verdict("VERIFIED")
    result = await BrowserSubagentRunner(owner_control_probe=_no_owner_control).run(
        assignment=_assignment(task), worker=worker, task=task, verifier=verifier,
    )

    assert result.stop_reason is SubagentStop.GOAL_ACHIEVED and result.succeeded
    assert verifier.calls == 1
    assert result.step_count == 1
    # Owner decision 2026-09-29 §8: Stagehand proposed, the Harness executed.
    assert stagehand.acted == []
    # The Harness click on the node /describe bound (review I5: the resolver always
    # describes; the page_info list carries no binding), then the read-back.
    assert harness.calls == ["click:xpath=//a[@id='quarterly-report']", "page_info"]
    assert result.steps[0].action_class is ActionClass.A2
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
    harness = FakeHarness([{"ref": "xpath=//button[@id='pay']", "role": "button", "name": "Pay"}])
    worker = HybridBrowserWorker(harness, stagehand, task=task)  # type: ignore[arg-type]

    result = await BrowserSubagentRunner(owner_control_probe=_no_owner_control).run(
        assignment=_assignment(task), worker=worker, task=task
    )

    assert result.stop_reason is SubagentStop.PAYMENT_REFUSED
    assert stagehand.acted == []
    assert harness.actuations == []


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
    harness = FakeHarness([{"ref": "xpath=//a", "role": "link", "name": "Result"}])
    worker = HybridBrowserWorker(harness, stagehand, task=task)  # type: ignore[arg-type]
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
    assert ".act(" not in source  # owner decision 2026-09-29 §8
    assert "one observed action" in source


# ---- owner decision 2026-09-29 §7: none of these may produce success -------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("verifier,expected", [
    (None, SubagentStop.UNVERIFIABLE),               # verifier unavailable
    (_Verdict("FAILED"), SubagentStop.NOT_SATISFIED),  # postcondition false
    (_Verdict("UNVERIFIABLE"), SubagentStop.UNVERIFIABLE),
    (_Verdict("PARTIAL"), SubagentStop.UNVERIFIABLE),
])
async def test_stagehand_no_controls_is_a_claim_not_success(tmp_path, verifier, expected):
    task = await _task(tmp_path)
    stagehand = FakeStagehand([[]])  # Stagehand returns no controls == "done"
    worker = HybridBrowserWorker(FakeHarness(), stagehand, task=task)  # type: ignore[arg-type]
    result = await BrowserSubagentRunner(owner_control_probe=_no_owner_control).run(
        assignment=_assignment(task), worker=worker, task=task, verifier=verifier,
    )
    assert result.stop_reason is expected
    assert not result.succeeded


@pytest.mark.asyncio
async def test_stagehand_fill_is_refused_not_replayed(tmp_path):
    task = await _task(tmp_path)
    stagehand = FakeStagehand([[{"method": "fill", "selector": "#q", "arguments": ["x"]}]])
    harness = FakeHarness()
    worker = HybridBrowserWorker(harness, stagehand, task=task)  # type: ignore[arg-type]
    result = await BrowserSubagentRunner(owner_control_probe=_no_owner_control).run(
        assignment=_assignment(task), worker=worker, task=task, verifier=_Verdict("VERIFIED"),
    )
    assert result.stop_reason is SubagentStop.WORKER_ERROR
    assert stagehand.acted == [] and harness.calls == []


@pytest.mark.asyncio
async def test_stagehand_adapter_act_is_disabled_by_default():
    from van_gateway.automation.external_runtime import ExternalRuntimeRegistry
    from van_gateway.browser.adapters import StagehandAdapter
    from van_gateway.browser.policy import BrowserPolicyError

    adapter = StagehandAdapter.__new__(StagehandAdapter)
    StagehandAdapter.__init__(adapter, ExternalRuntimeRegistry.__new__(ExternalRuntimeRegistry),
                              base_url="http://127.0.0.1:9140", enabled=True,
                              model_provider="anthropic", model_name="claude-sonnet-5")
    task = await _task_for_adapter()
    with pytest.raises(BrowserPolicyError, match="stagehand_direct_actuation_disabled"):
        await adapter.act(task, {"kind": "click"})


async def _task_for_adapter():
    from van_gateway.browser.models import BrowserTask, BrowserTaskStatus

    return BrowserTask(
        task_id="t", profile_alias="public_research", strategy=BrowserStrategy.STAGEHAND,
        autonomy_tier=AutonomyTier.L4_STAGEHAND_ACT, action_class=ActionClass.A2,
        target_domain=DOMAIN, goal="g", status=BrowserTaskStatus.PENDING, started_at_ms=0,
    )
