"""Shared fixtures for Automation & Browser Fabric tests.

Kept out of ``conftest.py`` so the existing suites are untouched; imported
explicitly by the automation/browser test modules.
"""

from __future__ import annotations

import dataclasses
import time
from typing import Any

from van_gateway.action.registry import install_builtin_actions
from van_gateway.action.service import ActionRuntime
from van_gateway.automation.canonical import new_id
from van_gateway.automation.models import (
    AutomationWorkflowArtifact,
    Primitive,
    RetryClass,
    WorkflowCapability,
    WorkflowEngine,
    WorkflowIR,
    WorkflowIREdge,
    WorkflowIRStep,
    WorkflowLifecycle,
    WorkflowStepEffect,
)
from van_gateway.automation.policy import load_automation_policy
from van_gateway.command.authority import (
    AuthoritySource,
    CommandAuthorityRecord,
    CommandAuthorityService,
)
from van_gateway.models import ActionClass, OriginChannel, PrincipalType
from van_gateway.storage.db import Store

DEVICE_ID = "dev-owner-1"


def policy_with_domains(*domains: str):
    """The repository policy admits no external domain yet (correct default-deny).

    Tests that need a reachable domain inject one rather than loosening the
    shipped policy file.
    """
    base = load_automation_policy()
    return dataclasses.replace(
        base, domains=dataclasses.replace(base.domains, admitted=frozenset(domains))
    )


async def make_store(tmp_path) -> Store:
    store = Store(str(tmp_path / "van.sqlite3"))
    await store.migrate()
    return store


async def enroll_device(store: Store, device_id: str = DEVICE_ID) -> str:
    await store.execute(
        "INSERT INTO devices(device_id, public_key_pem, enrolled_at_unix, revoked_at_unix, label) "
        "VALUES (?, ?, ?, NULL, ?)",
        (device_id, "-----BEGIN PUBLIC KEY-----test-----END PUBLIC KEY-----", int(time.time()), "test"),
    )
    return device_id


async def revoke_device(store: Store, device_id: str = DEVICE_ID) -> None:
    await store.execute(
        "UPDATE devices SET revoked_at_unix = ? WHERE device_id = ?", (int(time.time()), device_id)
    )


async def seal_owner_command(
    authority: CommandAuthorityService,
    *,
    command_id: str = "cmd-owner-1",
    device_id: str = DEVICE_ID,
    snapshot_id: str = "ctx-owner-1",
    effective: ActionClass = ActionClass.A3,
    turn_id: str | None = "turn-1",
    owner_approved: bool = False,
) -> CommandAuthorityRecord:
    now = int(time.time())
    record = CommandAuthorityRecord(
        command_id=command_id,
        device_id=device_id,
        principal_type=PrincipalType.OWNER_DEVICE,
        requested_by=device_id,
        origin_channel=OriginChannel.VOICE,
        signed_action_class=effective,
        effective_action_class=effective,
        snapshot_id=snapshot_id,
        context_digest="sha256:ownerctx",
        issued_at_unix=now,
        expires_at_unix=now + 3600,
        owner_approved=owner_approved,
        turn_id=turn_id,
        sealed_at_unix_ms=now * 1000,
        authority_source=AuthoritySource.OWNER_COMMAND,
    )
    return await authority.seal(record)


async def make_action_runtime(store: Store) -> ActionRuntime:
    runtime = ActionRuntime(store)
    await install_builtin_actions(runtime)
    return runtime


async def seed_standing_intent(
    store: Store,
    *,
    intent_id: str = "intent-statements",
    capability_id: str = "wfcap_statements",
    workflow_version: int = 1,
    enabled: bool = True,
    expires_at_ms: int | None = None,
) -> str:
    now = int(time.time() * 1000)
    await store.execute(
        """
        INSERT INTO automation_standing_intents(
          intent_id, owner_goal, trigger_json, scope_json, allowed_effects_json, expires_at_ms,
          capability_id, workflow_version, action_class, owner_approval_ref, enabled,
          created_at_ms, updated_at_ms
        ) VALUES (?, ?, '{}', '{}', '[]', ?, ?, ?, 'A2', 'evidence://owner/approval/1', ?, ?, ?)
        """,
        (
            intent_id, "collect broker statements every Friday", expires_at_ms, capability_id,
            workflow_version, 1 if enabled else 0, now, now,
        ),
    )
    return intent_id


def sample_ir(*, domain: str = "reports.example.com", version: int = 1) -> WorkflowIR:
    """A realistic three-step collect → fetch → seal workflow."""
    return WorkflowIR(
        ir_id=new_id("ir"),
        family="collect_normalise_ingest",
        semantic_goal="collect broker statements",
        version=version,
        trigger={"kind": "SCHEDULE", "cron": "0 6 * * 5"},
        inputs_schema={"properties": {"broker_alias": {"type": "string"}}},
        steps=[
            WorkflowIRStep(
                step_id="s_trig01", primitive=Primitive.SCHEDULE_TRIGGER, operation="fire",
                input_bindings={"rule": {"cron": "0 6 * * 5"}},
                effects=[WorkflowStepEffect.READ], action_class=ActionClass.A1,
                timeout_ms=5000, retry_class=RetryClass.IDEMPOTENT, max_attempts=1,
            ),
            WorkflowIRStep(
                step_id="s_http02", primitive=Primitive.HTTP_GET, operation="fetch",
                input_bindings={"url": f"https://{domain}/statements"},
                external_domain=domain, credential_alias="connector://broker/primary",
                effects=[WorkflowStepEffect.NETWORK_READ], action_class=ActionClass.A2,
                timeout_ms=20000, retry_class=RetryClass.IDEMPOTENT, max_attempts=3,
                output_name="raw",
            ),
            WorkflowIRStep(
                step_id="s_evid03", primitive=Primitive.VAN_EVIDENCE, operation="seal_artifact",
                input_bindings={"payload": "$raw"}, effects=[WorkflowStepEffect.WRITE],
                action_class=ActionClass.A3, timeout_ms=10000,
                retry_class=RetryClass.IDEMPOTENT_WITH_KEY, max_attempts=2,
                idempotency_key_expr="$raw.digest",
                postcondition={"kind": "READ_BACK", "field": "evidence_pointer"},
            ),
        ],
        edges=[
            WorkflowIREdge(from_step="s_trig01", to_step="s_http02"),
            WorkflowIREdge(from_step="s_http02", to_step="s_evid03"),
        ],
        credential_requirements=["connector://broker/primary"],
        external_domains=[domain],
        verifier={"kind": "READ_BACK"},
        action_class=ActionClass.A3,
        policy_version="van-automation-policy-1",
        compiler_version="van-automation-compiler-1",
    )


def sample_capability(
    capability_id: str = "wfcap_statements", *, action_class: ActionClass = ActionClass.A2,
    mutates: bool = False, lifecycle: WorkflowLifecycle = WorkflowLifecycle.ADMITTED,
) -> WorkflowCapability:
    now = int(time.time() * 1000)
    return WorkflowCapability(
        capability_id=capability_id,
        semantic_name="BROKER_STATEMENT_COLLECTION.EMAIL.VATI",
        engine=WorkflowEngine.N8N,
        action_class=action_class,
        mutates_state=mutates,
        allowed_principals=["OWNER_DEVICE", "HERMES_AGENT", "AUTOMATION"],
        allowed_origin_channels=["VOICE", "AUTOMATION"],
        latency_class="T3",
        duration_class="SECONDS",
        required_context=["emit_event"],
        required_credentials=["connector://broker/primary"],
        verifier_type="READ_BACK",
        idempotency_policy="IDEMPOTENT_WITH_KEY",
        evidence_policy="SEAL",
        lifecycle_state=lifecycle,
        workflow_ir_digest="sha256:ir",
        policy_version="van-automation-policy-1",
        compiler_version="van-automation-compiler-1",
        created_at_ms=now,
        updated_at_ms=now,
    )


def sample_artifact(
    capability_id: str = "wfcap_statements", *, version: int = 1,
    lifecycle: WorkflowLifecycle = WorkflowLifecycle.ADMITTED, n8n_workflow_id: str | None = "n8n-1",
) -> AutomationWorkflowArtifact:
    now = int(time.time() * 1000)
    return AutomationWorkflowArtifact(
        artifact_id=f"wfart_{capability_id}_{version}",
        capability_id=capability_id,
        version=version,
        workflow_ir_digest="sha256:ir",
        compiled_semantic_digest="sha256:semantic",
        compiled_full_digest="sha256:full",
        n8n_workflow_id=n8n_workflow_id,
        compiler_version="van-automation-compiler-1",
        node_catalog_version="van-n8n-catalog-1",
        policy_version="van-automation-policy-1",
        source_refs=[],
        lifecycle_state=lifecycle,
        created_at_ms=now,
        admitted_at_ms=now if lifecycle is WorkflowLifecycle.ADMITTED else None,
    )


__all__ = [
    "DEVICE_ID",
    "enroll_device",
    "make_action_runtime",
    "make_store",
    "policy_with_domains",
    "revoke_device",
    "sample_artifact",
    "sample_capability",
    "sample_ir",
    "seal_owner_command",
    "seed_standing_intent",
]
