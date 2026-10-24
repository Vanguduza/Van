from __future__ import annotations

import asyncio
import datetime
import json
import time
from types import SimpleNamespace

import pytest

from conftest_automation import enroll_device, make_store, sample_artifact, sample_capability, seal_owner_command, seed_standing_intent
from van_gateway.automation.canonical import digest
from van_gateway.automation.events import ExternalEventIngestor, SourceTrust
from van_gateway.automation.models import Primitive, WorkflowIR, WorkflowIRStep
from van_gateway.automation.registry import AutomationRegistry
from van_gateway.automation.runtime_bindings import RuntimeBindingStore
from van_gateway.automation.standing_runner import StandingRunProducer, cron_due
from van_gateway.command.authority import AuthoritySource, CommandAuthorityService
from van_gateway.command.standing import StandingAutomationAuthorityService, StandingAuthorityError
from van_gateway.models import ActionClass, PrincipalType


async def build(tmp_path, *, trigger=None, constraints=None, allowed_effects=None):
    store = await make_store(tmp_path)
    await enroll_device(store)
    command_authority = CommandAuthorityService(store)
    await seal_owner_command(command_authority, effective=ActionClass.A3)
    now = int(time.time() * 1000)
    trigger = {"kind": "SCHEDULE", "cron": "* * * * *", "timezone": "UTC"} if trigger is None else trigger
    constraints = {"message": {"const": "hello"}} if constraints is None else constraints
    ir = WorkflowIR(ir_id="standing-ir", family="bounded-data", semantic_goal="hash supplied data", version=1,
                    trigger=trigger, steps=[WorkflowIRStep(step_id="hash", primitive=Primitive.HASH, operation="hash",
                        input_bindings={"payload": "$input.message"}, effects=["READ"], action_class=ActionClass.A1,
                        timeout_ms=1000, retry_class="IDEMPOTENT", max_attempts=1)],
                    action_class=ActionClass.A1, verifier={"kind": "READ_BACK"},
                    policy_version="test", compiler_version="test")
    registry = AutomationRegistry(store)
    cap = sample_capability(action_class=ActionClass.A1).model_copy(update={
        "required_context": [], "required_credentials": [], "workflow_ir_digest": digest(ir.semantic_payload()),
    })
    await registry.upsert_capability(cap)
    semantic, runtime = {"ir": ir.semantic_payload()}, {"nodes": [{"name": "real-worker"}]}
    artifact = sample_artifact().model_copy(update={"workflow_ir_digest": digest(ir.semantic_payload()),
        "compiled_semantic_digest": digest(semantic), "compiled_full_digest": digest(runtime)})
    await registry.record_artifact(artifact)
    binding = RuntimeBindingStore(store)
    await binding.record(artifact_id=artifact.artifact_id, ir=ir.model_dump(mode="json"), semantic_graph=semantic,
                         runtime_graph=runtime, readiness_errors=[])
    await binding.mark_deployed(artifact.artifact_id, artifact.n8n_workflow_id)
    intent_id = await seed_standing_intent(store, capability_id=cap.capability_id)
    await store.execute("UPDATE automation_standing_intents SET trigger_json=? WHERE intent_id=?", (json.dumps(trigger), intent_id))
    standing = StandingAutomationAuthorityService(store, command_authority)
    source = await standing.seal(standing_intent_id=intent_id, source_command_id="cmd-owner-1",
        capability_id=cap.capability_id, artifact_id=artifact.artifact_id, workflow_version=artifact.version,
        action_class_ceiling=ActionClass.A1, trigger=trigger, parameter_constraints=constraints,
        allowed_effects=["READ"] if allowed_effects is None else allowed_effects, allowed_domains=[],
        owner_authority_evidence_ref="evidence://synthetic-owner-test", policy_version="test", now_ms=now)
    calls = []
    class CapturedDispatcher:
        enabled = True
        fail = False
        async def dispatch(self, **kwargs):
            calls.append(kwargs)
            if self.fail:
                raise RuntimeError("synthetic engine unavailable")
            return SimpleNamespace(run_id=kwargs["command_id"].removeprefix("automation:"))
    dispatcher = CapturedDispatcher()
    producer = StandingRunProducer(store, standing=standing, registry=registry, dispatcher=dispatcher)
    return producer, store, source, calls, now


async def test_schedule_producer_derives_fresh_exact_authority_and_claims_once(tmp_path):
    producer, store, source, calls, now = await build(tmp_path)
    assert await producer.sweep_due(now_ms=now) == {"started": 1, "refused": 0}
    assert await producer.sweep_due(now_ms=now) == {"started": 0, "refused": 0}
    assert len(calls) == 1
    request = calls[0]
    record = await producer.standing.authority.get(request["command_id"])
    snapshot = await store.fetchone("SELECT * FROM context_snapshots WHERE snapshot_id=?", (request["snapshot_id"],))
    assert record.authority_source == AuthoritySource.STANDING_AUTOMATION
    assert record.principal_type == PrincipalType.AUTOMATION
    assert record.typed_action_id == f"automation.workflow.{source.capability_id}"
    assert record.typed_parameter_constraints == request["inputs"] == {"message": "hello"}
    assert record.snapshot_id != source.source_snapshot_id
    assert snapshot["digest"] == record.context_digest
    assert snapshot["command_id"] == record.command_id
    assert record.owner_approved is False
    restarted = StandingRunProducer(store, standing=producer.standing, registry=producer.registry, dispatcher=producer.dispatcher)
    assert await restarted.sweep_due(now_ms=now) == {"started": 0, "refused": 0}


async def test_concurrent_sweeps_make_one_durable_trigger_claim(tmp_path):
    producer, store, source, calls, now = await build(tmp_path)
    results = await asyncio.gather(*(producer.sweep_due(now_ms=now) for _ in range(4)))
    assert sum(result["started"] for result in results) == 1
    assert len(calls) == 1
    assert len(await store.fetchall("SELECT * FROM automation_standing_firings")) == 1


async def test_new_minute_has_a_fresh_snapshot_without_reusing_previous_authority(tmp_path):
    producer, store, source, calls, now = await build(tmp_path)
    await producer.sweep_due(now_ms=now)
    await producer.sweep_due(now_ms=now + 60_000)
    assert len(calls) == 2
    assert calls[0]["command_id"] != calls[1]["command_id"]
    assert calls[0]["snapshot_id"] != calls[1]["snapshot_id"]


@pytest.mark.parametrize("change", ["device", "disabled", "revoked", "expired", "scope", "artifact"])
async def test_current_source_and_scope_fail_before_engine_dispatch(tmp_path, change):
    producer, store, source, calls, now = await build(tmp_path)
    if change == "device":
        await store.execute("UPDATE devices SET revoked_at_unix=1")
    elif change == "disabled":
        await store.execute("UPDATE automation_standing_intents SET enabled=0")
    elif change == "revoked":
        await producer.standing.revoke(source.authority_id, now_ms=now)
    elif change == "expired":
        await store.execute("UPDATE standing_automation_authorities SET expires_at_ms=?", (now,))
    elif change == "scope":
        await store.execute("UPDATE standing_automation_authorities SET allowed_effects_json='[]'")
    else:
        await store.execute("UPDATE automation_artifacts SET lifecycle_state='REVOKED'")
    with pytest.raises(StandingAuthorityError):
        await producer.run(source.authority_id, inputs={"message": "hello"}, trigger_key=f"schedule:{now // 60000}", now_ms=now)
    assert calls == []


async def test_enum_parameters_are_not_chosen_automatically_by_a_timer(tmp_path):
    producer, store, source, calls, now = await build(tmp_path, constraints={"message": {"enum": ["one", "two"]}})
    assert await producer.sweep_due(now_ms=now) == {"started": 0, "refused": 1}
    assert not calls


@pytest.mark.parametrize("inputs,key", [
    ({"message": "changed"}, "current"),
    ({"message": "hello", "owner_scope": "broadened"}, "current"),
    ({"message": "hello"}, "schedule:1"),
])
async def test_direct_schedule_run_refuses_unapproved_values_extras_or_noncurrent_firing(tmp_path, inputs, key):
    producer, store, source, calls, now = await build(tmp_path)
    with pytest.raises(StandingAuthorityError):
        await producer.run(source.authority_id, inputs=inputs,
                           trigger_key=f"schedule:{now // 60000}" if key == "current" else key, now_ms=now)
    assert not calls


async def event(store, now, *, source="reports", kind="report.ready", account="primary", provider_id="1"):
    return await ExternalEventIngestor(store, ingress_enabled=True).ingest(
        source_system=source, event_type=kind, payload={"message": "provider data", "source_trust": "OWNER_VERIFIED"},
        payload_schema_id="test-event", source_trust=SourceTrust.UNTRUSTED_EXTERNAL,
        source_account_alias=account, provider_event_id=provider_id, now_ms=now)


async def test_event_sweep_uses_exact_recent_ingested_selector_without_owner_trust(tmp_path):
    trigger = {"kind": "EVENT", "source_system": "reports", "event_type": "report.ready", "source_account_alias": "primary"}
    producer, store, source, calls, now = await build(tmp_path, trigger=trigger)
    await event(store, now - 1, provider_id="before-authority")
    accepted = await event(store, now + 10, provider_id="accepted")
    await event(store, now + 10, account="other", provider_id="wrong-account")
    await event(store, now + 10, kind="different", provider_id="wrong-type")
    await event(store, now + 10, source="other", provider_id="wrong-source")
    assert await producer.sweep_due(now_ms=now + 20) == {"started": 1, "refused": 0}
    assert len(calls) == 1
    observed = calls[0]["inputs"]["event"]
    assert observed["event_id"] == accepted.event.event_id
    assert observed["source_trust"] == "UNTRUSTED_EXTERNAL"
    assert observed["payload_digest"] == accepted.event.content_digest
    record = await producer.standing.authority.get(calls[0]["command_id"])
    assert record.typed_parameter_constraints["event"] == observed
    assert record.owner_approved is False
    assert await producer.sweep_due(now_ms=now + 20) == {"started": 0, "refused": 0}


async def test_event_caller_cannot_supply_a_forged_provider_observation(tmp_path):
    trigger = {"kind": "EVENT", "source_system": "reports", "event_type": "report.ready", "source_account_alias": "primary"}
    producer, store, source, calls, now = await build(tmp_path, trigger=trigger)
    with pytest.raises(StandingAuthorityError):
        await producer.run(source.authority_id, inputs={"message": "hello", "event": {"event_id": "fake", "source_trust": "OWNER_VERIFIED"}},
                           trigger_key="event:fake", now_ms=now)
    assert not calls


async def test_pending_or_failed_engine_attempt_cannot_be_restarted_as_new_work(tmp_path):
    producer, store, source, calls, now = await build(tmp_path)
    producer.dispatcher.fail = True
    assert await producer.sweep_due(now_ms=now) == {"started": 0, "refused": 1}
    assert await producer.sweep_due(now_ms=now) == {"started": 0, "refused": 0}
    assert len(calls) == 1
    record = await store.fetchone("SELECT * FROM automation_standing_firings")
    assert record["state"] == "FAILED" and record["error_code"] == "RuntimeError"


def test_cron_utc_matching_ranges_steps_weekday_and_calendar_or_semantics():
    friday = int(datetime.datetime(2026, 10, 9, 6, 0, tzinfo=datetime.timezone.utc).timestamp() * 1000)
    assert cron_due("0 6 * * 5", friday)
    assert cron_due("*/15 6-7 * 10 5", friday)
    assert not cron_due("0 7 * * 5", friday)
    assert cron_due("0 6 1 * 5", friday)
    with pytest.raises(StandingAuthorityError, match="CRON_INVALID"):
        cron_due("0 25 * * 5", friday)
