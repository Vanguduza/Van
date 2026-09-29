"""Review I2 N-6, N-7, N-8, N-10 — the interaction router's lanes and gates.

Each test is one of reviewer I2's probes (review-i2/probes/*.py) turned into a regression:

* N-6 ``determ.py`` — the deterministic lane executed ``click #pay-now``,
  ``click xpath=//button[@id='checkout-purchase']`` and ``fill #card-number`` for an A1 (and an
  A0) task: the action had ``action_class=None`` and the payment boundary read only its
  (absent) description, never the locator.
* N-7 ``jev_effect.py`` — a dial-jev response claiming ``ACTIVE`` + ``apply_effect: true`` was
  executed on dial-jev's word alone (``route: JEV VERIFIED_SUCCESS executed: [('JEV', 'click',
  'a#install')]``).
* N-8 ``cap_vs_global.py`` — health judged Stagehand on its capability slice of the gate model
  (``stagehand capability permitted: True``) while the lane gate read the global flag
  (``lane gate verdict: (False, 'PRODUCTION_GATES_NOT_GREEN:VAN-ADOPT-N8N-001.yaml:...')``).
* N-10 ``sh_lane_stale.py`` — a fresh Stagehand adapter was refused as UNCONFIGURED on the first
  step (its ``configured`` was the verdict of a gate evaluation that had not happened yet), and
  a step read the worker's ``/health`` three times.
"""

from __future__ import annotations

import hashlib
import json
import types
from pathlib import Path

import httpx
import pytest

import test_browser_interaction_router as tr
import van_gateway.automation.health as health
import van_gateway.automation.placement as placement
import van_gateway.automation.production_gates as production_gates
from conftest_automation import make_store
from van_gateway.automation.external_runtime import ExternalRuntimeRegistry
from van_gateway.browser.adapters import StagehandAdapter
from van_gateway.browser.interaction_router import (
    DeterministicAction,
    RouterLane,
    StagehandSemanticFallback,
    StepState,
    build_interaction_router,
)
from van_gateway.browser.lane_gates import load_jev_browser_effect_gate, load_stagehand_production_gate
from van_gateway.config import Settings
from van_gateway.models import ActionClass

# ------------------------------------------------------------------------------ N-6

PROBE_ACTIONS = [
    DeterministicAction(operation="click", locator="#pay-now"),
    DeterministicAction(operation="click", locator="xpath=//button[@id='checkout-purchase']"),
    DeterministicAction(operation="fill", locator="#card-number", value_ref="secretref://browser/card"),
]


@pytest.mark.parametrize("task_class", ["A1", "A0"])
@pytest.mark.parametrize("det", PROBE_ACTIONS, ids=lambda d: f"{d.operation}:{d.locator}")
async def test_a_payment_or_irreversible_deterministic_action_goes_to_the_owner(task_class, det):
    """Probe determ.py. Unresolved by the Harness, so classified on the locator's words."""
    ex = tr.FakeExecutor()
    router = tr.make_router(executor=ex)
    s = tr.step(action_class_ceiling="A1", deterministic_action=det)
    s.task = s.task.model_copy(update={"action_class": ActionClass(task_class)} if task_class != "A0"
                               else {"action_class": "A0"})
    result = await router.route(s)
    assert "DETERMINISTIC_ACTION_NOT_AUTOMATABLE:A4" in result.reasons
    assert ex.executed == []
    if det.locator == "#pay-now":
        # Payments first (review I4 MAJOR-A): the payment boundary reads "pay now" in the
        # locator words and refuses it as a payment before the ordinary takeover.
        assert result.lane is RouterLane.POLICY_REFUSAL and result.state is StepState.POLICY_REFUSED
        assert any("automated_payment_prohibited" in r for r in result.reasons)
    else:
        assert result.lane is RouterLane.OWNER_TAKEOVER and result.state is StepState.OWNER_TAKEOVER


async def test_the_harness_observed_element_decides_not_an_innocent_locator():
    elements = {"#b1": {"ref": "#b1", "role": "button", "label": "Pay now"},
                "#b2": {"ref": "#b2", "role": "button", "label": "Continue"}}
    ex = tr.FakeExecutor()
    router = tr.make_router(executor=ex, target_resolver=tr.FakeResolver(elements))
    paying = await router.route(tr.step(deterministic_action=DeterministicAction(operation="click", locator="#b1")))
    # Payments first (review I4 MAJOR-A): refused as a payment, never executed.
    assert paying.state is StepState.POLICY_REFUSED and ex.executed == []
    assert any("automated_payment_prohibited" in r for r in paying.reasons)
    fine = await router.route(tr.step(deterministic_action=DeterministicAction(operation="click", locator="#b2")))
    assert fine.state is StepState.VERIFIED_SUCCESS
    assert [(a.locator, a.action_class) for a in ex.executed] == [("#b2", "A2")]


async def test_a_deterministic_action_above_the_step_ceiling_is_refused():
    ex = tr.FakeExecutor()
    router = tr.make_router(executor=ex)
    result = await router.route(tr.step(action_class_ceiling="A1",
                                         deterministic_action=DeterministicAction(operation="click", locator="#go")))
    assert result.state is StepState.POLICY_REFUSED
    assert "DETERMINISTIC_ACTION_ABOVE_CEILING:A2>A1" in result.reasons
    assert ex.executed == []


async def test_the_payment_boundary_reads_the_locator_even_if_the_classifier_is_permissive():
    ex = tr.FakeExecutor()
    router = tr.make_router(executor=ex, action_classifier=lambda op, target, entry: "A1")
    result = await router.route(tr.step(action_class_ceiling="A1",
                                        deterministic_action=DeterministicAction(operation="click", locator="#pay-now")))
    assert result.state is StepState.POLICY_REFUSED
    assert any("payment" in r.lower() for r in result.reasons), result.reasons
    assert ex.executed == []


# ------------------------------------------------------------------------------ N-7


def _effect_router(**kw):
    ex = tr.FakeExecutor()
    kw.setdefault("jev_client", tr.FakeJev(tr.proposes("click", tr.T_LINK)))  # ACTIVE + apply_effect
    return ex, tr.make_router(executor=ex, semantic_fallback=tr.FakeStagehand(None), **kw)


def _raise():
    raise RuntimeError("gate down")


@pytest.mark.parametrize("gate, why", [
    (None, "JEV_EFFECT_GATE_MISSING"),
    (lambda: (False, "PRODUCTION_GATES_NOT_GREEN:VAN-JEV-BROWSER-EFFECT-001.yaml:jev_browser_effect"),
     "PRODUCTION_GATES_NOT_GREEN:VAN-JEV-BROWSER-EFFECT-001.yaml:jev_browser_effect"),
    (lambda: ("yes", "truthy is not True"), "truthy is not True"),
    (_raise, "JEV_EFFECT_GATE_FAILED:RuntimeError"),
])
async def test_an_active_apply_effect_response_is_a_shadow_until_the_van_gate_is_green(gate, why):
    """Probe jev_effect.py: dial-jev's own ACTIVE + apply_effect is not enough."""
    ex, router = _effect_router(jev_effect_gate=gate)
    result = await router.route(tr.step())
    assert f"JEV_EFFECT_NOT_PERMITTED_BY_VAN:{why}" in result.reasons
    assert "JEV_SHADOW_NOT_EXECUTED:VAN_JEV_EFFECT_GATE" in result.reasons
    assert result.shadow_jev is not None and result.shadow_jev["valid"] is True
    assert ex.executed == []


async def test_a_green_van_gate_lets_an_effect_carrying_proposal_execute():
    ex, router = _effect_router(jev_effect_gate=lambda: (True, "JEV_BROWSER_EFFECT_GATES_GREEN"))
    result = await router.route(tr.step())
    assert result.lane is RouterLane.JEV and result.state is StepState.VERIFIED_SUCCESS
    assert [(a.lane, a.locator) for a in ex.executed] == [(RouterLane.JEV, "a#install")]


async def test_the_real_gate_model_keeps_jev_effect_shadow_only():
    permitted, reason = await load_jev_browser_effect_gate()()
    assert permitted is False
    # The lane gate's reason is capped at 200 characters; since review I3 MINOR-4 the record
    # carries three gates, so the full list is read from the evaluator below.
    assert "VAN-JEV-BROWSER-EFFECT-001.yaml:" in reason
    state = production_gates.evaluate_production_gates()
    assert state["capability_decisions"] == ["VAN-JEV-BROWSER-EFFECT-001.yaml"]
    gates = {g["gate"]: g for g in state["capability_gates"]}
    assert (gates["jev_browser_effect"]["status"], gates["jev_browser_effect"]["raw_value"]) == ("PENDING", "SHADOW_ONLY")
    # Review I3 MINOR-4: effect also needs the owner's signature and decision reference.
    assert gates["owner_decision"]["status"] == "PENDING"
    assert gates["owner_decision_reference"]["status"] == "UNKNOWN"
    assert "VAN-JEV-BROWSER-EFFECT-001.yaml:jev_browser_effect" in (
        state["capabilities"]["jev_browser_effect"]["gates_not_green"])


def test_production_wiring_has_the_van_jev_effect_gate():
    router = build_interaction_router(settings=Settings(), harness=object(), stagehand=object(), jev_client=None)
    assert router.jev_effect_gate is not None


def _jev_repo(tmp_path: Path, *, jev: str, harness: str = "SIGNED") -> Path:
    decisions = tmp_path / "docs" / "decisions"
    decisions.mkdir(parents=True)
    simple = {"id": "owner_decision", "kind": "owner_decision", "path": "owner_signature_status",
              "green": ["SIGNED"], "pending": ["PENDING"]}
    for name, sig in (("VAN-ADOPT-N8N-001.yaml", "SIGNED"), ("VAN-ADOPT-BROWSER-HARNESS-001.yaml", harness),
                      ("VAN-ADOPT-STAGEHAND-001.yaml", "SIGNED")):
        (decisions / name).write_text(f"owner_signature_status: {sig}\n", encoding="utf-8")
    (decisions / "VAN-AMEND-SECURITY-POLICY-001.md").write_text("**Status:** `OWNER_APPROVED`\n", encoding="utf-8")
    # Review I3 MINOR-4 / I4 MINOR-B: the capability also needs the owner signature and a
    # resolved, sha256-pinned, authorized decision reference; this matrix is about the status
    # vocabulary and inheritance, so all of those are present here.
    ref = "docs/decisions/OWNER-DECISIONS-20261001-JEV.md"
    (tmp_path / ref).write_text("# owner decision (test fixture)\n", encoding="utf-8")
    auths = tmp_path / "docs" / "project-state" / "authorizations"
    auths.mkdir(parents=True)
    (auths / "auth-20261001-jev.json").write_text(json.dumps({
        "authorization_id": "auth-20261001-jev", "authority": "OWNER_EXPLICIT",
        "owner_instruction_record": ref, "revoked": False,
        "authorized_paths": ["docs/decisions/VAN-JEV-BROWSER-EFFECT-001.yaml"]}), encoding="utf-8")
    sha = hashlib.sha256((tmp_path / ref).read_bytes()).hexdigest()
    (decisions / "VAN-JEV-BROWSER-EFFECT-001.yaml").write_text(
        "owner_signature_status: SIGNED\njev_browser_effect:\n  status: "
        f"{jev}\n  owner_decision_reference: {ref}\n  owner_decision_sha256: '{sha}'\n"
        "  owner_decision_authorization_id: auth-20261001-jev\n",
        encoding="utf-8")
    required = [{"decision": n, "format": "yaml", "gates": [simple]} for n in (
        "VAN-ADOPT-N8N-001.yaml", "VAN-ADOPT-BROWSER-HARNESS-001.yaml", "VAN-ADOPT-STAGEHAND-001.yaml")]
    required.append({"decision": "VAN-AMEND-SECURITY-POLICY-001.md", "format": "markdown",
                     "gates": [{"id": "owner_decision", "kind": "owner_decision", "path": "Status",
                                "green": ["OWNER_APPROVED"]}]})
    model = json.loads((production_gates.GATE_MODEL).read_text(encoding="utf-8"))
    path = tmp_path / "gates.json"
    path.write_text(json.dumps({"decisions_dir": "docs/decisions", "required_decisions": required,
                                "capability_decisions": model["capability_decisions"]}), encoding="utf-8")
    return path


@pytest.mark.parametrize("jev, harness, expected", [
    ("SHADOW_ONLY", "SIGNED", False),
    ("REVOKED", "SIGNED", False),
    ("SOMETHING_ELSE", "SIGNED", False),
    ("OWNER_APPROVED_EFFECT", "PENDING", False),   # inherits the Harness decision
    ("OWNER_APPROVED_EFFECT", "SIGNED", True),
])
def test_jev_effect_capability_reads_its_own_record_and_not_the_global_summary(tmp_path, jev, harness, expected):
    state = production_gates.evaluate_production_gates(_jev_repo(tmp_path, jev=jev, harness=harness), tmp_path)
    assert state["capabilities"]["jev_browser_effect"]["production_activation_permitted"] is expected
    # SHADOW_ONLY is a legitimate posture: it never holds back the global summary.
    assert state["production_activation_permitted"] is (harness == "SIGNED")
    assert not any("JEV" in g for g in state["production_gates_not_green"])


# ------------------------------------------------------------------------------ N-8


def _fake_gates(*, global_ok: bool, stagehand_ok: bool):
    evaluation = {
        "owner_decisions_pending": [], "owner_decisions_missing": [], "gates": [],
        "gate_model": "fake", "gate_model_error": None,
        "production_activation_permitted": global_ok,
        "production_gates_not_green": [] if global_ok else ["VAN-ADOPT-N8N-001.yaml:live_qualification"],
        "capabilities": {
            name: {"production_activation_permitted": ok, "decisions": [], "error": None,
                   "gates_not_green": [] if ok else [f"{name}:gate"]}
            for name, ok in (("stagehand", stagehand_ok), ("browser_harness", True), ("n8n", global_ok),
                             ("jev_browser_effect", False))
        },
    }
    return lambda *a, **k: evaluation


@pytest.mark.parametrize("global_ok, stagehand_ok", [(False, True), (True, False), (True, True), (False, False)])
async def test_health_and_the_lane_gate_agree_on_stagehand(monkeypatch, global_ok, stagehand_ok):
    """Probe cap_vs_global.py: one scope (the Stagehand capability slice) for both."""
    fake = _fake_gates(global_ok=global_ok, stagehand_ok=stagehand_ok)
    monkeypatch.setattr(production_gates, "evaluate_production_gates", fake)
    monkeypatch.setattr(health, "evaluate_production_gates", fake)
    monkeypatch.setattr(placement, "stagehand_production_enabled",
                        lambda settings, worker_health=None: (True, "STAGEHAND_PLACEMENT_SATISFIED"))
    monkeypatch.setattr(placement, "stagehand_production_state",
                        lambda settings, worker_health=None: {"state": "PLACEMENT_SATISFIED"})
    settings = types.SimpleNamespace()
    lane_ok, _reason = await load_stagehand_production_gate(settings, None)()
    surface = await health.AutomationHealthApi._stagehand_production(
        types.SimpleNamespace(settings=settings, stagehand=None), health.governance_state())
    assert lane_ok is surface["production_activation_permitted"] is stagehand_ok


# ------------------------------------------------------------------------------ N-10


class _Worker:
    def __init__(self) -> None:
        self.paths: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.paths.append(request.url.path)
        if request.url.path.endswith("/health"):
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(200, json={"controls": [
            {"selector": "a.install", "method": "click", "description": "Install guide", "arguments": []}]})


async def test_a_fresh_stagehand_adapter_is_gated_once_per_step_and_not_refused_as_stale(tmp_path, monkeypatch):
    """Probe sh_lane_stale.py (capability slice forced GREEN, placement satisfied by live health)."""
    monkeypatch.setattr(placement, "stagehand_production_enabled",
                        lambda settings, worker_health=None: (True, "STAGEHAND_PLACEMENT_SATISFIED") if worker_health
                        else (False, "VAN_BROWSER_CORE_UNAVAILABLE:health_unverified"))
    monkeypatch.setattr(production_gates, "evaluate_production_gates",
                        _fake_gates(global_ok=False, stagehand_ok=True))
    store = await make_store(tmp_path)
    worker = _Worker()
    settings = Settings(browser_enabled=True)
    sh = StagehandAdapter(ExternalRuntimeRegistry(store), base_url="http://edge.test/stagehand", enabled=True,
                          model_provider="anthropic", model_name="claude-sonnet-5",
                          transport=httpx.MockTransport(worker), settings=settings)
    assert sh.production_gate_state[0] is False  # never evaluated: the stale verdict
    router = tr.make_router(eligibility_classifier=None, semantic_fallback=StagehandSemanticFallback(sh),
                            stagehand_gate=load_stagehand_production_gate(settings, sh))
    for n in (1, 2):
        worker.paths.clear()
        result = await router.route(tr.step())
        assert (result.lane, result.state) == (RouterLane.STAGEHAND, StepState.VERIFIED_SUCCESS), result.reasons
        assert worker.paths == ["/stagehand/health", "/stagehand/observe"], (n, worker.paths)


async def test_outside_a_router_step_the_adapter_still_evaluates_every_call(tmp_path, monkeypatch):
    """The per-step memo must not become a cache: the assignment path re-checks each call."""
    monkeypatch.setattr(placement, "stagehand_production_enabled",
                        lambda settings, worker_health=None: (True, "STAGEHAND_PLACEMENT_SATISFIED") if worker_health
                        else (False, "VAN_BROWSER_CORE_UNAVAILABLE:health_unverified"))
    monkeypatch.setattr(production_gates, "evaluate_production_gates",
                        _fake_gates(global_ok=False, stagehand_ok=True))
    store = await make_store(tmp_path)
    worker = _Worker()
    sh = StagehandAdapter(ExternalRuntimeRegistry(store), base_url="http://edge.test/stagehand", enabled=True,
                          model_provider="anthropic", model_name="claude-sonnet-5",
                          transport=httpx.MockTransport(worker), settings=Settings(browser_enabled=True))
    task = tr._task()
    await sh.observe(task, "a")
    await sh.observe(task, "b")
    assert worker.paths == ["/stagehand/health", "/stagehand/observe"] * 2


# ------------------------------------------------------- G3a request: one target rule


class _PageHarness:
    def __init__(self, elements):
        self.elements = elements

    async def page_info(self, task):
        return {"elements": self.elements}


@pytest.mark.parametrize("elements, locator, why", [
    ([], "#x", "TARGET_NOT_RESOLVED_BY_HARNESS"),
    ([{"ref": "#x", "role": "button", "label": "Go", "hidden": True}], "#x", "TARGET_HIDDEN"),
    ([{"ref": "#x", "href": "/a"}], "#x", "TARGET_HAS_NO_ROLE_OR_NAME"),
    ([], None, "NO_LOCATOR"),
])
async def test_router_lanes_and_the_assignment_worker_share_one_target_rule(elements, locator, why):
    from van_gateway.browser.interaction_router import HarnessTargetResolver, resolve_stagehand_target
    from van_gateway.browser.subagent import OwnerTakeoverRequired
    from van_gateway.browser.worker import HybridBrowserWorker

    harness = _PageHarness(elements)
    task = tr._task()
    assert await resolve_stagehand_target(HarnessTargetResolver(harness), task, locator) == why
    router = tr.make_router(target_resolver=HarnessTargetResolver(harness))
    assert await router._resolve_target(tr.step(), locator) == why
    worker = HybridBrowserWorker(harness=harness, stagehand=None, task=task)
    with pytest.raises(OwnerTakeoverRequired, match=f"STAGEHAND_ACTION_UNCLASSIFIABLE:{why}"):
        await worker._resolve_target(task, locator)
