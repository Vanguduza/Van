"""Review I M-4 — owner takeover preempts the assignment path, not only the B5 router.

Owner decision 2026-09-29 §9: "Owner takeover preempts automation." Before the fix,
``BrowserSubagentRunner.run`` and ``HybridBrowserWorker`` never consulted owner control:
with an ACTIVE interactive session whose ``control_holder`` was ``OWNER``, the router's
``OwnerControlProbe`` said True while the assignment path clicked anyway
(review-i/probes/owner.py: ``stop GOAL_ACHIEVED harness calls: ['click:#q', 'page_info']``).
"""

from __future__ import annotations

import time

import pytest
from cryptography.fernet import Fernet

from conftest_automation import make_store
from test_browser_semantic_worker import DOMAIN, FakeHarness, FakeStagehand, _assignment, _Verdict
from van_gateway.browser.interaction_router import OwnerControlProbe
from van_gateway.browser.models import AutonomyTier, BrowserStrategy
from van_gateway.browser.policy import BrowserPolicyEngine
from van_gateway.browser.service import BrowserTaskService
from van_gateway.browser.subagent import BrowserSubagentRunner, SubagentStop
from van_gateway.browser.worker import HybridBrowserWorker
from van_gateway.config import get_settings
from van_gateway.models import ActionClass

CONTROL = [{"method": "click", "selector": "#q", "description": "Open report", "arguments": []}]
#: What the Harness reports at "#q" (reviewer I2 N-2: the target must resolve to be classified).
ELEMENTS = [{"ref": "#q", "role": "link", "name": "Quarterly report"}]


async def _task(tmp_path):
    store = await make_store(tmp_path)
    service = BrowserTaskService(store)
    await service.broker.register_profile(profile_alias="public_research")
    task = await service.create_task(
        profile_alias="public_research", strategy=BrowserStrategy.STAGEHAND,
        autonomy_tier=AutonomyTier.L5_STAGEHAND_AGENT, action_class=ActionClass.A2,
        target_domain=DOMAIN, goal="find the quarterly report",
    )
    return store, task


async def _owner_takes_control(store, profile_alias="public_research"):
    now = int(time.time() * 1000)
    await store.execute(
        "INSERT INTO browser_interactive_sessions (session_id, owner_device_id, profile_alias, state, "
        "viewport_width, viewport_height, device_scale_factor, requested_fps, control_holder, "
        "control_generation, created_at_ms, expires_at_ms) "
        "VALUES ('s1','dev',?,'ACTIVE',1,1,1.0,30,'OWNER',1,?,?)",
        (profile_alias, now, now + 600_000),
    )


async def test_owner_holding_control_preempts_before_any_proposal(tmp_path):
    """The reviewer's probe, as a regression test."""
    store, task = await _task(tmp_path)
    await _owner_takes_control(store)
    probe = OwnerControlProbe(store)
    assert await probe(task) is True

    harness, stagehand = FakeHarness(), FakeStagehand([CONTROL, []])
    result = await BrowserSubagentRunner(BrowserPolicyEngine(), owner_control_probe=probe).run(
        assignment=_assignment(task), worker=HybridBrowserWorker(harness, stagehand, task=task),
        task=task, verifier=_Verdict("VERIFIED"),
    )
    assert result.stop_reason is SubagentStop.OWNER_TAKEOVER
    assert result.detail == "OWNER_HAS_CONTROL"
    assert result.succeeded is False
    assert harness.calls == []
    assert stagehand.observed == []  # not even a proposal


async def test_owner_taking_control_mid_step_preempts_before_execute(tmp_path):
    store, task = await _task(tmp_path)
    answers = iter([False, True])

    async def probe(_task):
        return next(answers)

    harness, stagehand = FakeHarness(ELEMENTS), FakeStagehand([CONTROL, []])
    result = await BrowserSubagentRunner(owner_control_probe=probe).run(
        assignment=_assignment(task), worker=HybridBrowserWorker(harness, stagehand, task=task),
        task=task, verifier=_Verdict("VERIFIED"),
    )
    assert result.stop_reason is SubagentStop.OWNER_TAKEOVER
    assert len(stagehand.observed) == 1  # proposed once
    assert harness.actuations == []  # but never actuated


async def test_owner_control_is_checked_before_every_step(tmp_path):
    store, task = await _task(tmp_path)
    seen: list[int] = []

    async def probe(_task):
        seen.append(1)
        return len(seen) > 3  # free for propose+execute of step 1 and propose of step 2

    harness, stagehand = FakeHarness(ELEMENTS), FakeStagehand([CONTROL, CONTROL, []])
    result = await BrowserSubagentRunner(owner_control_probe=probe).run(
        assignment=_assignment(task), worker=HybridBrowserWorker(harness, stagehand, task=task),
        task=task, verifier=_Verdict("VERIFIED"),
    )
    assert result.stop_reason is SubagentStop.OWNER_TAKEOVER
    assert harness.actuations == ["click:#q"]  # step 1 only; step 2 never executed
    assert len(seen) == 4


@pytest.mark.parametrize(
    "probe, detail",
    [
        (None, "OWNER_CONTROL_STATE_UNKNOWN"),
        ("raise", "OWNER_CONTROL_PROBE_FAILED:RuntimeError"),
        ("none", "OWNER_CONTROL_STATE_UNKNOWN"),
        ("truthy", "OWNER_CONTROL_STATE_UNKNOWN"),
    ],
)
async def test_unreadable_control_state_hands_over(tmp_path, probe, detail):
    store, task = await _task(tmp_path)

    async def raising(_task):
        raise RuntimeError("db gone")

    async def none(_task):
        return None

    async def truthy(_task):
        return 1

    fn = {None: None, "raise": raising, "none": none, "truthy": truthy}[probe]
    harness, stagehand = FakeHarness(), FakeStagehand([CONTROL, []])
    result = await BrowserSubagentRunner(owner_control_probe=fn).run(
        assignment=_assignment(task), worker=HybridBrowserWorker(harness, stagehand, task=task),
        task=task, verifier=_Verdict("VERIFIED"),
    )
    assert (result.stop_reason, result.detail) == (SubagentStop.OWNER_TAKEOVER, detail)
    assert harness.calls == [] and stagehand.observed == []


# ----------------------------------------------------------------- HTTP surface

INTERNAL = "test-internal-token"
HEADERS = {"X-Van-Internal-Token": INTERNAL}


@pytest.fixture
def _browser_env(monkeypatch, tmp_path):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "browser.sqlite3"))
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", "test-ingress-token-0123456789abcdef")
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", INTERNAL)
    monkeypatch.setenv("VAN_DEVICE_ENROLMENT_TOKEN", INTERNAL)
    monkeypatch.setenv("VAN_BROWSER_ENABLED", "1")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def test_assignment_endpoint_hands_over_to_the_owner(tmp_path, _browser_env):
    import test_browser_api as t
    from van_gateway.browser.subagent import ProposedAction

    worker = t._ScriptedWorker([ProposedAction(kind="read", domain=t.DOMAIN, instruction="read")])
    ac, _api, store = await t._client(tmp_path, worker=worker, verifier=t._Verdict("VERIFIED"))
    async with ac:
        task = await t._make_task(ac)
        await _owner_takes_control(store)
        r = await ac.post("/v1/browser/assignments", headers=HEADERS, json={
            "task_id": task["task_id"], "turn_id": "turn-o", "command_id": "cmd-owner-1",
            "goal": "read the statement total", "allowed_domains": [t.DOMAIN],
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["stop_reason"] == "OWNER_TAKEOVER"
        assert body["succeeded"] is False and body["needs_owner"] is True
        assert worker.proposed == 0 and worker.executed == 0
        status = (await ac.get(f"/v1/browser/tasks/{task['task_id']}", headers=HEADERS)).json()["task"]
        assert status["status"] == "WAITING_FOR_OWNER"
        assert status["error_code"] == "OWNER_TAKEOVER:OWNER_HAS_CONTROL"
