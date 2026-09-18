"""Rev 1 §§7-8 — the canonical capability registry and router.

The reconciliation this proves: VAN had two things called a capability registry
before this existed, and the risk was creating a third source of truth for "can
VAN do this right now". These tests pin the property that makes that not happen
— the canonical registry stores declarations and *asks* the existing subsystems
for readiness, so a capability withdrawn in the automation fabric or a Google
connection that drops stops being routable here with no synchronisation step.

The other property under test is determinism: same manifest, same constraints,
same answer and same ranking, every time.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from conftest_automation import make_store
from van_gateway.automation.external_runtime import ExternalRuntimeRegistry, ReadinessEvidence
from van_gateway.capability.models import (
    CapabilityClass,
    CapabilityDeclaration,
    ReadinessSource,
    RoutabilityReason,
    RoutingConstraints,
)
from van_gateway.capability.readiness import (
    AutomationReadiness,
    ExternalRuntimeReadiness,
    GoogleMeshReadiness,
)
from van_gateway.capability.registry import (
    DEFAULT_MANIFEST,
    CapabilityRegistry,
    CapabilityRegistryError,
)
from van_gateway.capability.router import CapabilityRouter, score
from van_gateway.models import ActionClass

A3 = RoutingConstraints(max_action_class=ActionClass.A3)


async def _registry(tmp_path, *, probes=None, manifest=None):
    store = await make_store(tmp_path)
    registry = CapabilityRegistry(store, manifest_path=manifest, probes=probes)
    registry.load()
    return store, registry


def _write_manifest(tmp_path, capabilities, version="1.0.0") -> pathlib.Path:
    path = tmp_path / "capabilities.json"
    path.write_text(json.dumps({"version": version, "capabilities": capabilities}))
    return path


_MINIMAL = {
    "capability_id": "native.read",
    "provider": "van", "executor": "GATEWAY",
    "capability_class": "NATIVE_READ", "authority_class": "A1",
    "verification_strategy": "NONE", "readiness_source": "STATIC",
}


# ------------------------------------------------------- the shipped manifest


async def test_the_shipped_manifest_loads_and_is_sealed(tmp_path):
    _store, registry = await _registry(tmp_path)
    assert registry.manifest_digest.startswith("sha256:")
    assert "automation.workflow.execute" in registry.capability_ids
    assert "trading.vati.submit_order" in registry.capability_ids


async def test_the_digest_is_over_declarations_not_file_bytes(tmp_path):
    """Reformatting the manifest must not look like a change to the capability set."""
    original = json.loads(DEFAULT_MANIFEST.read_text())
    _store, canonical = await _registry(tmp_path)

    reordered = dict(original)
    reordered["capabilities"] = list(reversed(original["capabilities"]))
    path = tmp_path / "reordered.json"
    path.write_text(json.dumps(reordered, indent=8))
    _store2, shuffled = await _registry(tmp_path, manifest=path)

    assert shuffled.manifest_digest == canonical.manifest_digest


async def test_syncing_twice_is_idempotent(tmp_path):
    store, registry = await _registry(tmp_path)
    first = await registry.sync()
    rows_before = await store.fetchall("SELECT * FROM capability_registry")
    second = await registry.sync()
    rows_after = await store.fetchall("SELECT * FROM capability_registry")
    assert first == second
    assert len(rows_before) == len(rows_after) == len(registry.capability_ids)
    assert all(r["withdrawn_at_ms"] is None for r in rows_after)


async def test_a_capability_dropped_from_the_manifest_is_withdrawn_not_deleted(tmp_path):
    """The row survives so the removal is auditable; it stops being routable."""
    store, registry = await _registry(tmp_path)
    await registry.sync()

    smaller = CapabilityRegistry(
        store, manifest_path=_write_manifest(tmp_path, [_MINIMAL], version="2.0.0")
    )
    smaller.load()
    await smaller.sync()

    withdrawn = await store.fetchall(
        "SELECT capability_id FROM capability_registry WHERE withdrawn_at_ms IS NOT NULL"
    )
    assert len(withdrawn) == len(registry.capability_ids)
    assert await smaller.routability("automation.workflow.execute") == await smaller.routability(
        "automation.workflow.execute"
    )
    verdict = await smaller.routability("automation.workflow.execute")
    assert verdict.reason is RoutabilityReason.NOT_DECLARED


# ------------------------------------------------- declaration-set validation


async def test_a_fallback_must_be_declared(tmp_path):
    manifest = _write_manifest(tmp_path, [dict(_MINIMAL, fallback_capabilities=["ghost"])])
    with pytest.raises(CapabilityRegistryError, match="FALLBACK_UNDECLARED"):
        await _registry(tmp_path, manifest=manifest)


async def test_a_fallback_may_not_escalate_authority(tmp_path):
    """§8 — a fallback that can do more than what it stands in for is an
    escalation wearing a fallback's clothes."""
    manifest = _write_manifest(tmp_path, [
        dict(_MINIMAL, capability_id="weak", authority_class="A1",
             fallback_capabilities=["strong"]),
        dict(_MINIMAL, capability_id="strong", authority_class="A3",
             verification_strategy="API_READBACK"),
    ])
    with pytest.raises(CapabilityRegistryError, match="FALLBACK_ESCALATES"):
        await _registry(tmp_path, manifest=manifest)


async def test_a_mutation_without_a_verifier_is_refused(tmp_path):
    """§34 — a side effect that cannot prove it happened cannot be admitted."""
    manifest = _write_manifest(tmp_path, [
        dict(_MINIMAL, capability_id="blind.write", authority_class="A3",
             verification_strategy="NONE"),
    ])
    with pytest.raises(CapabilityRegistryError, match="MUTATION_WITHOUT_VERIFIER"):
        await _registry(tmp_path, manifest=manifest)


async def test_never_routable_must_say_why(tmp_path):
    manifest = _write_manifest(tmp_path, [
        dict(_MINIMAL, capability_id="forbidden", readiness_source="NEVER_ROUTABLE"),
    ])
    with pytest.raises(CapabilityRegistryError, match="NEVER_ROUTABLE_WITHOUT_REASON"):
        await _registry(tmp_path, manifest=manifest)


async def test_a_duplicate_declaration_is_refused(tmp_path):
    manifest = _write_manifest(tmp_path, [_MINIMAL, dict(_MINIMAL)])
    with pytest.raises(CapabilityRegistryError, match="DECLARED_TWICE"):
        await _registry(tmp_path, manifest=manifest)


# ------------------------------------------------------------- routability


async def test_an_undeclared_capability_is_never_routable(tmp_path):
    """§7's rule, stated directly."""
    _store, registry = await _registry(tmp_path)
    verdict = await registry.routability("something.nobody.declared")
    assert verdict.routable is False
    assert verdict.reason is RoutabilityReason.NOT_DECLARED
    with pytest.raises(CapabilityRegistryError, match="NOT_ROUTABLE"):
        await registry.assert_routable_for_mutation("something.nobody.declared")


async def test_vati_execution_is_declared_and_structurally_unroutable(tmp_path):
    """§2.4 — the generic fabric must not reach broker order submission.

    Declared rather than omitted so the boundary is auditable: an absent
    capability looks like an oversight, NEVER_ROUTABLE is a decision.
    """
    _store, registry = await _registry(tmp_path)
    declaration = registry.require("trading.vati.submit_order")
    assert declaration.readiness_source is ReadinessSource.NEVER_ROUTABLE
    assert declaration.never_routable_reason

    for constraints in (
        RoutingConstraints(max_action_class=ActionClass.A4, owner_present=True),
        RoutingConstraints(max_action_class=ActionClass.A5, owner_present=True),
    ):
        verdict = await registry.routability(
            "trading.vati.submit_order", constraints=constraints
        )
        assert verdict.routable is False
        assert verdict.reason is RoutabilityReason.NEVER_ROUTABLE


async def test_policy_is_checked_before_readiness(tmp_path):
    """A capability the caller was never allowed to use reports a policy refusal,
    not a health problem — otherwise someone "fixes" it by restarting a worker."""
    _store, registry = await _registry(tmp_path)
    verdict = await registry.routability(
        "google.gmail.send", constraints=RoutingConstraints(max_action_class=ActionClass.A2)
    )
    assert verdict.reason is RoutabilityReason.ABOVE_AUTHORITY_CEILING


async def test_owner_presence_and_privacy_are_hard_filters(tmp_path):
    _store, registry = await _registry(tmp_path)
    absent = await registry.routability(
        "google.gmail.send",
        constraints=RoutingConstraints(max_action_class=ActionClass.A4, owner_present=False),
    )
    assert absent.reason is RoutabilityReason.OWNER_PRESENCE_REQUIRED

    private_only = await registry.routability(
        "research.exa.search",
        constraints=RoutingConstraints(
            max_action_class=ActionClass.A2, permit_external_disclosure=False
        ),
    )
    assert private_only.reason is RoutabilityReason.PRIVACY_NOT_PERMITTED


async def test_a_missing_readiness_probe_is_not_ready(tmp_path):
    """A wiring bug must not present as a healthy capability that fails later."""
    _store, registry = await _registry(tmp_path)  # no probes but STATIC
    verdict = await registry.routability("automation.workflow.execute", constraints=A3)
    assert verdict.routable is False
    assert verdict.reason is RoutabilityReason.NOT_READY
    assert "no readiness probe" in (verdict.detail or "")


async def test_routability_is_deterministic(tmp_path):
    _store, registry = await _registry(tmp_path)
    answers = {
        (await registry.routability(c, constraints=A3)).model_dump_json()
        for c in registry.capability_ids
        for _ in range(3)
    }
    assert len(answers) == len(registry.capability_ids)


# ----------------------------------- readiness delegates, it does not copy


async def test_automation_readiness_follows_the_automation_fabric(tmp_path):
    """The point of the reconciliation: no synchronisation step in between."""
    from van_gateway.automation.models import WorkflowLifecycle
    from van_gateway.automation.registry import AutomationRegistry
    from conftest_automation import sample_artifact, sample_capability

    store = await make_store(tmp_path)
    registry = CapabilityRegistry(
        store, probes={ReadinessSource.AUTOMATION_REGISTRY: AutomationReadiness(store, enabled=True)}
    )
    registry.load()

    before = await registry.routability("automation.workflow.execute", constraints=A3)
    assert before.reason is RoutabilityReason.NOT_READY

    automation = AutomationRegistry(store)
    await automation.upsert_capability(sample_capability())
    await automation.record_artifact(sample_artifact(lifecycle=WorkflowLifecycle.ADMITTED))

    after = await registry.routability("automation.workflow.execute", constraints=A3)
    assert after.routable is True


async def test_external_runtime_readiness_requires_recorded_evidence(tmp_path):
    """§368 — CONFIGURED is not READY, and absence of evidence is not readiness."""
    store = await make_store(tmp_path)
    runtime = ExternalRuntimeRegistry(store)
    registry = CapabilityRegistry(
        store,
        probes={
            ReadinessSource.EXTERNAL_RUNTIME: ExternalRuntimeReadiness(runtime, enabled=True)
        },
    )
    registry.load()

    unproven = await registry.routability("browser.semantic.extract")
    assert unproven.reason is RoutabilityReason.NOT_READY
    assert "NO_READINESS_EVIDENCE" in (unproven.detail or "")

    await runtime.record_evidence(
        ReadinessEvidence(capability="stagehand", evidence_pointer="gateway://cert/1",
                          runtime_version="1.0.0")
    )
    assert (await registry.routability("browser.semantic.extract")).routable is True


async def test_a_disabled_fabric_reports_itself_rather_than_failing_later(tmp_path):
    store = await make_store(tmp_path)
    registry = CapabilityRegistry(
        store,
        probes={
            ReadinessSource.AUTOMATION_REGISTRY: AutomationReadiness(store, enabled=False),
            ReadinessSource.EXTERNAL_RUNTIME: ExternalRuntimeReadiness(
                ExternalRuntimeRegistry(store), enabled=False
            ),
            ReadinessSource.GOOGLE_MESH: GoogleMeshReadiness(None),
        },
    )
    registry.load()
    assert (await registry.routability("automation.workflow.execute", constraints=A3)).detail == (
        "AUTOMATION_FABRIC_DISABLED"
    )
    assert (await registry.routability("browser.semantic.extract")).detail == (
        "BROWSER_FABRIC_DISABLED"
    )
    assert (await registry.routability("google.gmail.search")).detail == (
        "GOOGLE_MESH_UNCONFIGURED"
    )


# ------------------------------------------------------------------ router


def test_scoring_is_pure_arithmetic_over_declared_facts():
    """No I/O, no model, no caller input — so the ranking is reproducible."""
    declaration = CapabilityDeclaration.model_validate(
        dict(_MINIMAL, capability_id="x", verification_strategy="API_READBACK")
    )
    first = score(declaration)
    assert first == score(declaration)
    assert first.breakdown["verification"] == 40
    assert first.score == sum(first.breakdown.values())


def test_owner_interruption_is_scored_as_a_cost():
    """§8 lists owner_interruption_cost as a routing factor, so it costs points."""
    quiet = CapabilityDeclaration.model_validate(dict(_MINIMAL, capability_id="q"))
    noisy = CapabilityDeclaration.model_validate(
        dict(_MINIMAL, capability_id="n", requires_owner_presence=True)
    )
    assert score(noisy).score < score(quiet).score


async def test_the_router_prefers_the_deterministic_local_read(tmp_path):
    """§8's order: deterministic local read before retrieval before the web."""
    store, registry = await _registry(tmp_path)
    router = CapabilityRouter(store, registry)
    decision = await router.route(
        goal_class="LOOKUP",
        candidate_classes=[
            CapabilityClass.NATIVE_READ,
            CapabilityClass.KNOWLEDGE_RETRIEVAL,
            CapabilityClass.WEB_RESEARCH,
        ],
        mission_id="msn_1",
    )
    assert decision.routed
    assert decision.selected_capability_id.startswith("native.")
    assert decision.manifest_digest == registry.manifest_digest


async def test_the_router_refuses_to_interpret_the_goal_itself(tmp_path):
    """§2.1 — goal interpretation is Hermes's, deterministic selection is the
    router's. Without a narrowing, scoring would return the best-verified
    capability in the registry regardless of what was actually asked."""
    store, registry = await _registry(tmp_path)
    router = CapabilityRouter(store, registry)
    with pytest.raises(CapabilityRegistryError, match="CANDIDATE_CLASSES_REQUIRED"):
        await router.route(goal_class="LOOKUP", candidate_classes=[])


async def test_the_router_never_selects_what_policy_refused(tmp_path):
    """Policy is a filter, not a weight — no score can promote the forbidden."""
    store, registry = await _registry(tmp_path)
    router = CapabilityRouter(store, registry)
    decision = await router.route(
        goal_class="TRADE",
        candidate_classes=[CapabilityClass.TRADING_EXECUTION],
        constraints=RoutingConstraints(max_action_class=ActionClass.A5, owner_present=True),
    )
    assert decision.routed is False
    assert [r.reason for r in decision.rejected] == [RoutabilityReason.NEVER_ROUTABLE]


async def test_the_route_decision_is_persisted_as_evidence(tmp_path):
    """§8 — candidates considered, candidates rejected, reason, policy version."""
    store, registry = await _registry(tmp_path)
    router = CapabilityRouter(store, registry)
    decision = await router.route(
        goal_class="RESEARCH",
        # Browser capabilities are in the pool but have no probe wired here, so
        # the decision records both what was chosen and what was passed over.
        candidate_classes=[
            CapabilityClass.WEB_RESEARCH,
            CapabilityClass.BROWSER_INTERACTION,
        ],
        mission_id="msn_7",
    )

    rows = await router.decisions_for("msn_7")
    assert len(rows) == 1
    row = rows[0]
    assert row["selected_capability_id"] == decision.selected_capability_id
    assert row["routing_policy_version"] == "van-capability-routing-1"
    assert row["manifest_digest"] == registry.manifest_digest
    rejected = json.loads(row["rejected_json"])
    assert rejected and all("reason" in r for r in rejected)
    candidates = json.loads(row["candidates_json"])
    assert candidates and "breakdown" in candidates[0]


async def test_routing_is_reproducible(tmp_path):
    """Same manifest, same constraints, same ranking — ties broken stably."""
    store, registry = await _registry(tmp_path)
    router = CapabilityRouter(store, registry)
    rankings = set()
    for _ in range(5):
        decision = await router.route(
            goal_class="LOOKUP",
            candidate_classes=[CapabilityClass.NATIVE_READ,
                               CapabilityClass.KNOWLEDGE_RETRIEVAL],
            persist=False,
        )
        rankings.add(tuple(c.capability_id for c in decision.candidates))
    assert len(rankings) == 1


async def test_a_fallback_may_not_disclose_what_the_original_kept_private(tmp_path):
    """The same error as authority escalation, in the other currency.

    Found by this rule in the shipped manifest during development: VEKL
    retrieval (owner-private) declared a fallback to web search
    (external-disclosing), which would have turned "what do I know about X" into
    "ask a third party about X" silently.
    """
    manifest = _write_manifest(tmp_path, [
        dict(_MINIMAL, capability_id="private.read", privacy_class="OWNER_PRIVATE",
             fallback_capabilities=["public.read"]),
        dict(_MINIMAL, capability_id="public.read", privacy_class="EXTERNAL_DISCLOSING"),
    ])
    with pytest.raises(CapabilityRegistryError, match="FALLBACK_DISCLOSES"):
        await _registry(tmp_path, manifest=manifest)


async def test_vekl_retrieval_has_no_silent_web_fallback(tmp_path):
    """The shipped manifest records that absence as a decision, not an omission."""
    _store, registry = await _registry(tmp_path)
    vekl = registry.require("knowledge.vekl.retrieve")
    assert vekl.fallback_capabilities == []
    assert vekl.no_fallback_reason


async def test_the_fallback_chain_only_offers_routable_capabilities(tmp_path):
    store, registry = await _registry(tmp_path)
    router = CapabilityRouter(store, registry)
    decision = await router.route(
        goal_class="RESEARCH",
        candidate_classes=[CapabilityClass.WEB_RESEARCH],
        persist=False,
    )
    assert decision.selected_capability_id == "research.exa.search"
    # browser.semantic.extract is a declared fallback but has no probe wired
    # here, so it is not offered as one.
    assert decision.fallback_chain == ()
