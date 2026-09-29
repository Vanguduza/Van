"""Review I B-1 — the Stagehand production gate lives inside the adapter.

Before the fix, ``Settings(browser_enabled=True)`` with every other value at its default
(zone undeclared, loopback endpoint) let the L2-L5 ``/v1/browser/assignments`` path call
Stagehand ``/observe``: the placement and production gates were only consulted by the B5
interaction router, and ``HybridBrowserWorker`` / the NotebookLM consumer hold the adapter
directly. The adapter now evaluates the router's own composition (placement with live
worker ``/health`` AND ``evaluate_production_gates``) before every worker call, so there
is no consumer that can go around it.
"""

from __future__ import annotations

import httpx
import pytest

import van_gateway.automation.placement as placement
import van_gateway.automation.production_gates as production_gates
from conftest_automation import make_store
from van_gateway.automation.external_runtime import ExternalRuntimeRegistry, RuntimeState
from van_gateway.browser.adapters import BrowserAdapterError, StagehandAdapter
from van_gateway.browser.models import AutonomyTier, BrowserStrategy
from van_gateway.browser.policy import BrowserPolicyEngine
from van_gateway.browser.service import BrowserTaskService
from van_gateway.browser.subagent import BrowserSubagentRunner, SubagentAssignment, SubagentStop
from van_gateway.browser.worker import BrowserTaskPlan, HybridBrowserWorker, PlannedStep
from van_gateway.config import Settings
from van_gateway.models import ActionClass


async def _no_owner_control(_task) -> bool:
    """Review I M-4: the runner fails closed without an owner-control probe; these
    tests are about other bounds, so the owner is explicitly not holding control."""
    return False

DOMAIN = "research.example.com"


class _Recorder:
    def __init__(self) -> None:
        self.paths: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.paths.append(request.url.path)
        if request.url.path.endswith("/health"):
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(200, json={"controls": [], "extraction": {}})


async def _task(tmp_path, tier=AutonomyTier.L5_STAGEHAND_AGENT):
    store = await make_store(tmp_path)
    service = BrowserTaskService(store)
    await service.broker.register_profile(profile_alias="public_research")
    strategy = BrowserStrategy.HARNESS if tier is AutonomyTier.L1_HARNESS_DETERMINISTIC else BrowserStrategy.STAGEHAND
    task = await service.create_task(
        profile_alias="public_research", strategy=strategy,
        autonomy_tier=tier, action_class=ActionClass.A2, target_domain=DOMAIN, goal="g",
    )
    return store, task


def _adapter(store, recorder, **kwargs) -> StagehandAdapter:
    return StagehandAdapter(
        ExternalRuntimeRegistry(store), base_url="http://127.0.0.1:9140", enabled=True,
        model_provider="anthropic", model_name="claude-sonnet-5",
        transport=httpx.MockTransport(recorder), **kwargs,
    )


def _assignment(task, **overrides) -> SubagentAssignment:
    values = dict(
        turn_id="t", command_id="c", task_id=task.task_id, goal="g", allowed_domains=[DOMAIN],
        action_class_ceiling=ActionClass.A2, autonomy_tier=AutonomyTier.L5_STAGEHAND_AGENT, max_steps=3,
    )
    values.update(overrides)
    return SubagentAssignment(**values)


async def test_assignment_path_never_reaches_stagehand_with_default_settings(tmp_path):
    """The reviewer's probe: browser_enabled only, zone undeclared, loopback endpoint."""
    store, task = await _task(tmp_path)
    recorder = _Recorder()
    settings = Settings(browser_enabled=True)
    assert placement.stagehand_production_enabled(settings, worker_health={"ok": True})[0] is False
    stagehand = _adapter(store, recorder, settings=settings)
    worker = HybridBrowserWorker(harness=None, stagehand=stagehand, task=task)  # type: ignore[arg-type]

    result = await BrowserSubagentRunner(BrowserPolicyEngine(), owner_control_probe=_no_owner_control).run(
        assignment=_assignment(task), worker=worker, task=task,
    )

    assert result.stop_reason is SubagentStop.WORKER_ERROR
    assert result.succeeded is False
    # Settings alone close the gate, so the worker is not contacted at all (not even /health).
    assert recorder.paths == []
    assert stagehand.configured is False
    assert stagehand.production_gate_state == (False, "STAGEHAND_ZONE_UNDECLARED")


async def test_every_primitive_is_refused_while_the_gate_is_closed(tmp_path):
    store, task = await _task(tmp_path)
    recorder = _Recorder()
    stagehand = _adapter(store, recorder, settings=Settings(browser_enabled=True), actuation_enabled=True)
    with pytest.raises(BrowserAdapterError) as observed:
        await stagehand.observe(task, "look")
    assert observed.value.code == "STAGEHAND_PRODUCTION_DISABLED"
    with pytest.raises(BrowserAdapterError, match="STAGEHAND_PRODUCTION_DISABLED"):
        await stagehand.extract(task, "read", {"type": "object", "properties": {}})
    # Even an adapter explicitly built with actuation enabled cannot act past the gate.
    with pytest.raises(BrowserAdapterError, match="STAGEHAND_PRODUCTION_DISABLED"):
        await stagehand.act(task, {"kind": "click"})
    assert [p for p in recorder.paths if not p.endswith("/health")] == []


async def test_missing_gate_fails_closed(tmp_path):
    store, task = await _task(tmp_path)
    recorder = _Recorder()
    stagehand = _adapter(store, recorder, production_gate=None)
    with pytest.raises(BrowserAdapterError) as exc:
        await stagehand.observe(task, "look")
    assert (exc.value.code, exc.value.detail) == (
        "STAGEHAND_PRODUCTION_DISABLED", "STAGEHAND_PRODUCTION_GATE_MISSING",
    )
    assert recorder.paths == []


@pytest.mark.parametrize(
    "gate",
    [
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
        lambda: "not-a-tuple",
        lambda: ("yes", "truthy is not True"),
        lambda: (1, "one is not True"),
    ],
)
async def test_faulty_or_non_boolean_gate_fails_closed(tmp_path, gate):
    store, task = await _task(tmp_path)
    recorder = _Recorder()
    stagehand = _adapter(store, recorder, production_gate=gate)
    with pytest.raises(BrowserAdapterError, match="STAGEHAND_PRODUCTION_DISABLED"):
        await stagehand.observe(task, "look")
    assert recorder.paths == []


async def test_canonical_gate_is_placement_with_live_health_and_production_gates(tmp_path, monkeypatch):
    """Same composition as the router: placement(worker /health) AND the gate model."""
    store, task = await _task(tmp_path)
    recorder = _Recorder()
    seen: dict = {}

    def fake_placement(settings, *, worker_health=None):
        seen["health"] = worker_health
        return True, "PLACEMENT_OK"

    monkeypatch.setattr(placement, "stagehand_production_enabled", fake_placement)
    monkeypatch.setattr(production_gates, "evaluate_production_gates", lambda: {
        "production_activation_permitted": False, "production_gates_not_green": ["D:signed_ingress"],
    })
    stagehand = _adapter(store, recorder, settings=Settings(browser_enabled=True))

    with pytest.raises(BrowserAdapterError) as exc:
        await stagehand.observe(task, "look")
    assert exc.value.detail == "PRODUCTION_GATES_NOT_GREEN:D:signed_ingress"
    assert seen["health"] == {"ok": True}  # the live worker /health was read
    assert recorder.paths == ["/health"]

    monkeypatch.setattr(production_gates, "evaluate_production_gates", lambda: {"production_activation_permitted": True})
    await stagehand.observe(task, "look")
    assert recorder.paths == ["/health", "/health", "/observe"]
    assert stagehand.configured is True


async def test_real_gate_model_keeps_stagehand_closed_even_with_placement_satisfied(tmp_path, monkeypatch):
    """Project Truth today: production gates PENDING, so placement alone is not enough."""
    store, task = await _task(tmp_path)
    recorder = _Recorder()
    monkeypatch.setattr(placement, "stagehand_production_enabled", lambda s, *, worker_health=None: (True, "OK"))
    assert production_gates.evaluate_production_gates()["production_activation_permitted"] is False
    stagehand = _adapter(store, recorder, settings=Settings(browser_enabled=True))
    with pytest.raises(BrowserAdapterError) as exc:
        await stagehand.observe(task, "look")
    assert exc.value.detail.startswith("PRODUCTION_GATES_NOT_GREEN:")
    assert "/observe" not in recorder.paths


async def test_status_reports_policy_disabled_not_configured_while_gate_closed(tmp_path):
    store, _task_ = await _task(tmp_path)
    stagehand = _adapter(store, _Recorder(), settings=Settings(browser_enabled=True))
    status = await stagehand.status()
    assert status.state is RuntimeState.POLICY_DISABLED
    assert status.configured is False
    assert status.detail == "STAGEHAND_PRODUCTION_DISABLED:STAGEHAND_ZONE_UNDECLARED"
    assert stagehand.configured is False

    opened = _adapter(store, _Recorder(), production_gate=lambda: (True, "OK"))
    assert (await opened.status()).state is RuntimeState.CONFIGURED
    assert opened.configured is True


async def test_deterministic_path_still_runs_with_stagehand_production_disabled(tmp_path):
    """§1: the deterministic Harness path continues under its own policy."""
    store, task = await _task(tmp_path, tier=AutonomyTier.L1_HARNESS_DETERMINISTIC)
    recorder = _Recorder()
    stagehand = _adapter(store, recorder, production_gate=None)

    class Harness:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def navigate(self, _task, url):
            self.calls.append(f"navigate:{url}")
            return {}

        async def page_info(self, _task):
            self.calls.append("page_info")
            return {"url": f"https://{DOMAIN}/a", "title": "A"}

    class Verified:
        async def verify(self, task, action, postcondition, *, claimed_done):
            from van_gateway.action.models import VerifierType
            from van_gateway.automation.verifier import VerificationOutcome, VerificationResult

            return VerificationResult(outcome=VerificationOutcome.VERIFIED, verifier_type=VerifierType.READ_BACK)

    harness = Harness()
    plan = BrowserTaskPlan(steps=[PlannedStep(kind="navigate", domain=DOMAIN, url=f"https://{DOMAIN}/a")])
    worker = HybridBrowserWorker(harness, stagehand, plan=plan, task=task)  # type: ignore[arg-type]
    result = await BrowserSubagentRunner(BrowserPolicyEngine(), owner_control_probe=_no_owner_control).run(
        assignment=_assignment(task, autonomy_tier=AutonomyTier.L1_HARNESS_DETERMINISTIC),
        worker=worker, task=task, verifier=Verified(),
    )
    assert result.stop_reason is SubagentStop.GOAL_ACHIEVED and result.succeeded
    assert harness.calls[0] == f"navigate:https://{DOMAIN}/a"
    assert recorder.paths == []


async def test_knowledge_runtime_builds_a_gated_adapter(tmp_path):
    """knowledge/service.py built the adapter the same ungated way; it now carries the gate."""
    from van_gateway.knowledge.service import KnowledgeRuntime

    store = await make_store(tmp_path)
    runtime = KnowledgeRuntime(store, Settings(browser_enabled=True))
    stagehand = runtime.notebook_consumer.stagehand
    assert isinstance(stagehand, StagehandAdapter)
    assert stagehand.production_gate is not None
    assert await stagehand.evaluate_production_gate() == (False, "STAGEHAND_ZONE_UNDECLARED")
    assert stagehand.configured is False
