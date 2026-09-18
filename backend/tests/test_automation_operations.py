"""Rev 1.3 §§76-78, 101-102, 243-246 — operating the fabric, not just building it.

The properties worth holding onto:

* degradation happens by itself, from what runs actually did (§77);
* a transient timeout is not a health event and never triggers regeneration
  (§244) — otherwise a flaky network would rewrite working workflows;
* a repair never mutates the admitted artifact; it promotes a new version and
  supersedes the old one, which is what makes rollback possible (§§78, 245);
* bounded retry ends in a dead letter with a stated next action, never in an
  infinite retry (§246);
* the HOT hit rate is measured rather than asserted (§102).
"""

from __future__ import annotations

import pytest

from conftest_automation import make_store, sample_artifact, sample_capability
from van_gateway.automation.deadletter import DeadLetterService, NextAction
from van_gateway.automation.models import IntentSignature, WorkflowLifecycle
from van_gateway.automation.registry import AutomationRegistry, HotWorkflowIndex, RegistryError
from van_gateway.automation.repair import RepairDecision, RepairService, decide
from van_gateway.automation.router import CapabilityRouter, ExecutionMedium, RouteRequest
from van_gateway.automation.telemetry import (
    CacheState,
    GenerationEvent,
    RunTiming,
    TelemetryService,
)
from van_gateway.automation.workflow_health import (
    FailureClass,
    HealthStatus,
    WorkflowHealthService,
    percentile,
)
from van_gateway.models import ActionClass

CAP = "wfcap_statements"
SIGNATURE = IntentSignature(
    goal_class="BROKER_STATEMENT_COLLECTION", source_class="EMAIL",
    destination_class="VATI", mutation_class=ActionClass.A2,
)


# ---------------------------------------------------------------- health model


async def test_a_verified_success_is_the_only_thing_that_heals(tmp_path):
    """§17 — an unverified run is not evidence either way, so it neither
    degrades the workflow nor clears its failure streak."""
    health = WorkflowHealthService(await make_store(tmp_path))
    await health.record_failure(
        capability_id=CAP, workflow_version=1, failure_class=FailureClass.SCHEMA
    )
    state = await health.record_failure(
        capability_id=CAP, workflow_version=1, failure_class=FailureClass.SCHEMA
    )
    assert state.status is HealthStatus.DEGRADED

    unverified = await health.record_success(
        capability_id=CAP, workflow_version=1, duration_ms=100, verified=False
    )
    assert unverified.status is HealthStatus.DEGRADED
    assert unverified.consecutive_failures == 2

    verified = await health.record_success(
        capability_id=CAP, workflow_version=1, duration_ms=100, verified=True
    )
    assert verified.status is HealthStatus.GREEN
    assert verified.consecutive_failures == 0


async def test_a_transient_failure_is_not_a_health_event(tmp_path):
    """§244 — a timeout must never be what rewrites a working workflow."""
    health = WorkflowHealthService(await make_store(tmp_path))
    for _ in range(10):
        state = await health.record_failure(
            capability_id=CAP, workflow_version=1, failure_class=FailureClass.TRANSIENT
        )
    assert state.status is HealthStatus.GREEN
    assert state.consecutive_failures == 0
    # It is still counted as a run and a failure; it just does not degrade.
    assert state.runs == 10
    assert state.failures == 10


async def test_a_verification_failure_degrades_fastest(tmp_path):
    """§80 — the engine said it worked and the world disagreed. That is the worst
    kind of failure, so it takes one to degrade and two to need repair."""
    health = WorkflowHealthService(await make_store(tmp_path))
    first = await health.record_failure(
        capability_id=CAP, workflow_version=1, failure_class=FailureClass.VERIFICATION
    )
    assert first.status is HealthStatus.DEGRADED
    second = await health.record_failure(
        capability_id=CAP, workflow_version=1, failure_class=FailureClass.VERIFICATION
    )
    assert second.status is HealthStatus.REPAIR_REQUIRED


async def test_a_security_failure_quarantines_immediately(tmp_path):
    """§47 — a security failure does not degrade gracefully."""
    health = WorkflowHealthService(await make_store(tmp_path))
    state = await health.record_failure(
        capability_id=CAP, workflow_version=1, failure_class=FailureClass.SECURITY
    )
    assert state.status is HealthStatus.QUARANTINED
    # And nothing heals out of quarantine by simply succeeding again.
    healed = await health.record_success(
        capability_id=CAP, workflow_version=1, duration_ms=10, verified=True
    )
    assert healed.status is HealthStatus.QUARANTINED


async def test_health_is_tracked_per_version_not_per_capability(tmp_path):
    """A repaired workflow must not inherit the failure record it was written to fix."""
    health = WorkflowHealthService(await make_store(tmp_path))
    for _ in range(3):
        await health.record_failure(
            capability_id=CAP, workflow_version=1, failure_class=FailureClass.SCHEMA
        )
    v1 = await health.get(CAP, 1)
    assert v1 is not None and v1.status is HealthStatus.REPAIR_REQUIRED

    v2 = await health.record_success(
        capability_id=CAP, workflow_version=2, duration_ms=50, verified=True
    )
    assert v2.status is HealthStatus.GREEN
    assert v2.runs == 1


async def test_p95_is_exact_on_the_sample_window(tmp_path):
    health = WorkflowHealthService(await make_store(tmp_path))
    for ms in range(1, 21):
        await health.record_success(
            capability_id=CAP, workflow_version=1, duration_ms=ms * 10, verified=True
        )
    state = await health.get(CAP, 1)
    assert state is not None
    assert state.p95_duration_ms == 190
    assert state.mean_duration_ms == 105
    assert state.verified_success_rate == 1.0


def test_percentile_handles_the_degenerate_cases():
    assert percentile([], 95) is None
    assert percentile([7], 95) == 7
    assert percentile([1, 2, 3, 4], 50) == 2


# ---------------------------------------------------------------------- router


async def test_the_router_stops_sending_work_to_a_degraded_workflow(tmp_path):
    """§77 — and withdraws it, so the health check is not a per-request cost."""
    store = await make_store(tmp_path)
    registry = AutomationRegistry(store)
    await registry.upsert_capability(
        sample_capability(action_class=ActionClass.A2, lifecycle=WorkflowLifecycle.HOT)
    )
    await registry.record_artifact(sample_artifact(lifecycle=WorkflowLifecycle.ADMITTED))
    health = WorkflowHealthService(store)
    index = HotWorkflowIndex()
    index.publish(SIGNATURE, CAP, 1, "n8n-wf-1")
    router = CapabilityRouter(registry=registry, hot_index=index, health=health)

    hot = await router.route(RouteRequest(goal="collect statements", signature=SIGNATURE))
    assert hot.medium is ExecutionMedium.N8N_HOT

    await health.record_failure(
        capability_id=CAP, workflow_version=1, failure_class=FailureClass.VERIFICATION
    )
    degraded = await router.route(
        RouteRequest(
            goal="collect statements", signature=SIGNATURE,
            native_capability_id="native.statements",
        )
    )
    assert degraded.medium is ExecutionMedium.NATIVE
    assert degraded.reason.value == "HOT_CAPABILITY_DEGRADED"
    assert "DEGRADED" in (degraded.detail or "")
    assert index.size == 0


async def test_a_degraded_workflow_falls_back_to_warm_when_there_is_no_native(tmp_path):
    store = await make_store(tmp_path)
    registry = AutomationRegistry(store)
    await registry.upsert_capability(
        sample_capability(action_class=ActionClass.A2, lifecycle=WorkflowLifecycle.HOT)
    )
    await registry.record_artifact(sample_artifact(lifecycle=WorkflowLifecycle.ADMITTED))
    health = WorkflowHealthService(store)
    await health.record_failure(
        capability_id=CAP, workflow_version=1, failure_class=FailureClass.VERIFICATION
    )
    index = HotWorkflowIndex()
    index.publish(SIGNATURE, CAP, 1, "n8n-wf-1")
    router = CapabilityRouter(registry=registry, hot_index=index, health=health)

    decision = await router.route(RouteRequest(goal="collect statements", signature=SIGNATURE))
    assert decision.medium is ExecutionMedium.N8N_WARM
    assert decision.template_id == "collect_normalise_ingest.v1"


# ---------------------------------------------------------------------- repair


@pytest.mark.parametrize(
    ("failure_class", "expected"),
    [
        (FailureClass.SECURITY, RepairDecision.SECURITY_REVIEW_REQUIRED),
        (FailureClass.CREDENTIAL, RepairDecision.REFRESH_CREDENTIAL),
        (FailureClass.CONNECTOR, RepairDecision.CONNECTOR_DEGRADED),
        (FailureClass.SCHEMA, RepairDecision.EXTERNAL_API_CHANGED),
        (FailureClass.VERIFICATION, RepairDecision.IR_REPAIR_REQUIRED),
    ],
)
async def test_the_decision_follows_the_failure_class(tmp_path, failure_class, expected):
    store = await make_store(tmp_path)
    registry = AutomationRegistry(store)
    await registry.upsert_capability(sample_capability())
    artifact = await registry.record_artifact(
        sample_artifact(lifecycle=WorkflowLifecycle.ADMITTED)
    )
    service = RepairService(store, registry=registry)
    packet = await service.build_packet(
        capability_id=CAP, failing_artifact_id=artifact.artifact_id,
        failure_class=failure_class, error_code="E1",
    )
    assert decide(packet) is expected


async def test_a_transient_failure_gets_one_retry_and_then_stops_being_transient(tmp_path):
    """§244 — never regenerate a whole workflow for a timeout."""
    store = await make_store(tmp_path)
    registry = AutomationRegistry(store)
    await registry.upsert_capability(sample_capability())
    artifact = await registry.record_artifact(
        sample_artifact(lifecycle=WorkflowLifecycle.ADMITTED)
    )
    service = RepairService(store, registry=registry)
    packet = await service.build_packet(
        capability_id=CAP, failing_artifact_id=artifact.artifact_id,
        failure_class=FailureClass.TRANSIENT, error_code="N8N_TIMEOUT",
    )
    assert decide(packet, attempt=1) is RepairDecision.RETRY_NO_CHANGE
    assert decide(packet, attempt=2) is RepairDecision.CONNECTOR_DEGRADED
    # Neither outcome asks for a new IR.
    assert not decide(packet, attempt=1).needs_new_ir
    assert not decide(packet, attempt=2).needs_new_ir


async def test_the_repair_packet_carries_shapes_not_secrets(tmp_path):
    """§243 — digests, error codes and catalog state. No owner memory, no values."""
    store = await make_store(tmp_path)
    registry = AutomationRegistry(store)
    await registry.upsert_capability(sample_capability())
    artifact = await registry.record_artifact(
        sample_artifact(lifecycle=WorkflowLifecycle.ADMITTED)
    )
    service = RepairService(store, registry=registry)
    packet = await service.build_packet(
        capability_id=CAP, failing_artifact_id=artifact.artifact_id,
        failure_class=FailureClass.SCHEMA, error_code="SCHEMA_MISMATCH",
        failing_node="s_http02",
    )
    payload = packet.as_diagnosis_input()
    assert payload["failing_node"] == "s_http02"
    assert payload["compiler_version"]
    assert set(payload) == {
        "capability_id", "failure_class", "error_code", "failing_node",
        "input_schema_digest", "output_schema_digest", "node_catalog_version",
        "compiler_version", "policy_version", "previous_successful_artifact_id",
        "external_observations", "repair_patterns",
    }


async def test_a_security_failure_quarantines_the_failing_version(tmp_path):
    store = await make_store(tmp_path)
    registry = AutomationRegistry(store)
    await registry.upsert_capability(sample_capability())
    artifact = await registry.record_artifact(
        sample_artifact(lifecycle=WorkflowLifecycle.ADMITTED)
    )
    health = WorkflowHealthService(store)
    service = RepairService(store, registry=registry, health=health)
    packet = await service.build_packet(
        capability_id=CAP, failing_artifact_id=artifact.artifact_id,
        failure_class=FailureClass.SECURITY, error_code="GRANT_REPLAYED",
    )
    _repair_id, decision = await service.open(packet)
    assert decision is RepairDecision.SECURITY_REVIEW_REQUIRED
    state = await health.get(CAP, artifact.version)
    assert state is not None and state.status is HealthStatus.QUARANTINED


async def test_promotion_supersedes_the_old_artifact_and_keeps_it(tmp_path):
    """§§78, 245 — never mutate in place; rollback needs the old version to exist."""
    store = await make_store(tmp_path)
    registry = AutomationRegistry(store)
    await registry.upsert_capability(sample_capability())
    failing = await registry.record_artifact(
        sample_artifact(lifecycle=WorkflowLifecycle.ADMITTED, version=1)
    )
    candidate = await registry.record_artifact(
        sample_artifact(lifecycle=WorkflowLifecycle.ADMITTED, version=2)
    )
    health = WorkflowHealthService(store)
    service = RepairService(store, registry=registry, health=health)
    packet = await service.build_packet(
        capability_id=CAP, failing_artifact_id=failing.artifact_id,
        failure_class=FailureClass.VERIFICATION,
    )
    repair_id, decision = await service.open(packet)
    assert decision is RepairDecision.IR_REPAIR_REQUIRED

    promoted = await service.promote(
        repair_id=repair_id, candidate_artifact_id=candidate.artifact_id
    )
    assert promoted.version == 2

    old = await registry.get_artifact(failing.artifact_id)
    assert old is not None
    assert old.lifecycle_state is WorkflowLifecycle.SUPERSEDED

    new_health = await health.get(CAP, 2)
    assert new_health is not None
    assert new_health.repair_count == 1
    assert new_health.status is HealthStatus.GREEN

    # A repair is promoted once.
    with pytest.raises(RegistryError, match="already_promoted"):
        await service.promote(repair_id=repair_id, candidate_artifact_id=candidate.artifact_id)


async def test_an_unadmitted_candidate_cannot_be_promoted(tmp_path):
    """§245 — promotion happens after validation and admission, not instead of it."""
    store = await make_store(tmp_path)
    registry = AutomationRegistry(store)
    await registry.upsert_capability(sample_capability())
    failing = await registry.record_artifact(
        sample_artifact(lifecycle=WorkflowLifecycle.ADMITTED, version=1)
    )
    candidate = await registry.record_artifact(
        sample_artifact(lifecycle=WorkflowLifecycle.PROPOSED, version=2)
    )
    service = RepairService(store, registry=registry)
    packet = await service.build_packet(
        capability_id=CAP, failing_artifact_id=failing.artifact_id,
        failure_class=FailureClass.VERIFICATION,
    )
    repair_id, _ = await service.open(packet)
    with pytest.raises(RegistryError, match="candidate_not_admitted"):
        await service.promote(repair_id=repair_id, candidate_artifact_id=candidate.artifact_id)
    # The failing artifact is untouched by the refused promotion.
    still = await registry.get_artifact(failing.artifact_id)
    assert still is not None and still.lifecycle_state is WorkflowLifecycle.ADMITTED


# ----------------------------------------------------------------- dead letter


async def test_a_dead_letter_always_states_a_next_action(tmp_path):
    """§246 — an unactionable dead letter is the same bug as a silent drop."""
    service = DeadLetterService(await make_store(tmp_path))
    letter = await service.record(
        run_id="run-1", capability_id=CAP, failure_class=FailureClass.CREDENTIAL,
        attempt_count=3, last_error_code="CREDENTIAL_REJECTED",
    )
    assert letter.next_action is NextAction.CREDENTIAL_REFRESH
    assert letter.open is True
    assert await service.open_count() == 1


async def test_a_second_failure_updates_the_same_letter(tmp_path):
    """Otherwise the attempt count — the thing that says 'not transient' — is
    spread across a queue of near-identical rows."""
    service = DeadLetterService(await make_store(tmp_path))
    await service.record(
        run_id="run-1", failure_class=FailureClass.UNKNOWN, attempt_count=1,
    )
    second = await service.record(
        run_id="run-1", failure_class=FailureClass.UNKNOWN, attempt_count=4,
        last_error_code="STILL_BROKEN",
    )
    assert second.attempt_count == 4
    assert second.last_error_code == "STILL_BROKEN"
    assert await service.open_count() == 1


async def test_a_dead_letter_needs_a_run_or_an_event(tmp_path):
    service = DeadLetterService(await make_store(tmp_path))
    with pytest.raises(ValueError, match="requires_run_or_event"):
        await service.record(failure_class=FailureClass.UNKNOWN, attempt_count=1)


async def test_resolving_is_idempotent(tmp_path):
    service = DeadLetterService(await make_store(tmp_path))
    letter = await service.record(
        event_id="evt-1", failure_class=FailureClass.SCHEMA, attempt_count=2
    )
    assert letter.next_action is NextAction.AWAIT_REPAIR
    assert await service.resolve(letter.dead_letter_id, resolution="repaired in v2") is True
    assert await service.resolve(letter.dead_letter_id, resolution="again") is False
    assert await service.open_count() == 0


# ------------------------------------------------------------------ telemetry


async def test_van_overhead_excludes_waiting_on_someone_elses_api(tmp_path):
    """§57 — mixing external wait into the latency budget hides regressions."""
    timing = RunTiming(
        run_id="run-1", cache_state=CacheState.HOT, compile_time_ms=0,
        dispatch_time_ms=8, execution_time_ms=40, external_wait_ms=900,
        verification_time_ms=12,
    )
    assert timing.total_ms == 960
    assert timing.van_overhead_ms == 60


async def test_the_hot_hit_rate_is_measured(tmp_path):
    """§102 — the core success metric is a number, not a claim."""
    telemetry = TelemetryService(await make_store(tmp_path))
    for medium, outcome in (
        ("N8N_HOT", "SERVED"), ("N8N_HOT", "SERVED"), ("N8N_HOT", "SERVED"),
        ("N8N_WARM", "ADMITTED_CANDIDATE"),
        ("WORKFLOW_COMPILER", "REJECTED_BY_POLICY"),
    ):
        await telemetry.record_generation(
            GenerationEvent(
                goal_class="BROKER_STATEMENT_COLLECTION", medium=medium, outcome=outcome,
                first_use_latency_ms=100 if medium == "N8N_HOT" else 4000,
            )
        )
    metrics = await telemetry.ladder_metrics()
    assert metrics.total == 5
    assert metrics.hot_hit_rate == 0.6
    assert metrics.warm_specialisation_rate == 0.2
    assert metrics.cold_generation_rate == 0.2
    assert metrics.generation_failures == 1
    assert metrics.median_first_use_latency_ms == 100


async def test_run_latency_separates_the_ladder_rungs(tmp_path):
    telemetry = TelemetryService(await make_store(tmp_path))
    await telemetry.record_run(
        RunTiming(run_id="r1", cache_state=CacheState.HOT, execution_time_ms=10)
    )
    await telemetry.record_run(
        RunTiming(run_id="r2", cache_state=CacheState.COLD, execution_time_ms=3000)
    )
    # A re-record of the same run replaces it rather than double-counting.
    await telemetry.record_run(
        RunTiming(run_id="r1", cache_state=CacheState.HOT, execution_time_ms=12)
    )
    stats = await telemetry.run_latency()
    assert stats["runs"] == 2
    assert stats["by_cache_state"] == {"HOT": 1, "COLD": 1}
    assert stats["van_overhead_p95_ms"] == 3000
