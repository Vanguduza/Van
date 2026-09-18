"""Rev 1.3 §§388-403 — standing automation authority.

These are the tests Rev 1.3 names explicitly: §399 event-to-run derivation, §400
revocation, §401 the A4 event. Together they close the Rev 1.2 review's blocking
finding B4 — that an AUTOMATION principal previously had no way to obtain command
authority for a scheduled or event-driven run.
"""

from __future__ import annotations

import time

import pytest

from conftest_automation import (
    DEVICE_ID,
    enroll_device,
    make_action_runtime,
    make_store,
    revoke_device,
    seal_owner_command,
    seed_standing_intent,
)
from van_gateway.action.service import ActionPolicyError
from van_gateway.command.authority import (
    AuthoritySource,
    CommandAuthorityError,
    CommandAuthorityService,
)
from van_gateway.command.standing import (
    StandingAuthorityError,
    StandingAutomationAuthorityService,
)
from van_gateway.models import ActionClass, OriginChannel, PrincipalType

TRIGGER = {"kind": "SCHEDULE", "cron": "0 6 * * 5", "source": "broker.statements"}
CONSTRAINTS = {
    "broker_alias": {"enum": ["primary_mt5"]},
    "document_type": {"enum": ["statement"]},
}


async def _seal_standing(store, *, ceiling=ActionClass.A2, expires_at_ms=None):
    authority = CommandAuthorityService(store)
    standing = StandingAutomationAuthorityService(store, authority)
    await enroll_device(store)
    await seal_owner_command(authority, effective=ActionClass.A3)
    intent_id = await seed_standing_intent(store)
    record = await standing.seal(
        standing_intent_id=intent_id,
        source_command_id="cmd-owner-1",
        capability_id="wfcap_statements",
        artifact_id="wfart_statements_1",
        workflow_version=1,
        action_class_ceiling=ceiling,
        trigger=TRIGGER,
        parameter_constraints=CONSTRAINTS,
        allowed_effects=["NETWORK_READ"],
        allowed_domains=["reports.example.com"],
        owner_authority_evidence_ref="evidence://owner/approval/1",
        policy_version="van-automation-policy-1",
        expires_at_ms=expires_at_ms,
    )
    return authority, standing, record


async def test_event_derives_ordinary_command_authority(tmp_path):
    """§399 — a timer/webhook run ends up holding a normal CommandAuthorityRecord."""
    store = await make_store(tmp_path)
    authority, standing, record = await _seal_standing(store)

    derived = await standing.derive_run_authority(
        record, run_id="wfrun_1", trigger=TRIGGER, artifact_id="wfart_statements_1",
        workflow_version=1, parameters={"broker_alias": "primary_mt5", "document_type": "statement"},
        run_snapshot_id="ctx-run-1", run_context_digest="sha256:runctx",
        operation_action_class=ActionClass.A2,
    )

    assert derived.authority.principal_type is PrincipalType.AUTOMATION
    assert derived.authority.origin_channel is OriginChannel.AUTOMATION
    assert derived.authority.authority_source is AuthoritySource.STANDING_AUTOMATION
    assert derived.authority.source_authority_id == record.authority_id
    # §392 — the owner device remains the revocation root.
    assert derived.authority.device_id == DEVICE_ID
    # §393 — never owner_approved, and no turn.
    assert derived.authority.owner_approved is False
    assert derived.authority.turn_id is None
    # §395 — a fresh snapshot, never the source snapshot.
    assert derived.run_snapshot_id == "ctx-run-1"
    assert derived.source_snapshot_id == "ctx-owner-1"
    assert derived.run_snapshot_id != derived.source_snapshot_id

    # And the derived record really does satisfy the ordinary authority check.
    actions = await make_action_runtime(store)
    definition = await actions.get_definition("research.web.search")
    resolved, _age = await authority.authorize_action(
        command_id=derived.command_id, action=definition,
        principal_type=PrincipalType.AUTOMATION, requested_by=derived.authority.requested_by,
        snapshot_id="ctx-run-1", turn_id=None,
    )
    assert resolved.command_id == derived.command_id


async def test_reusing_source_snapshot_is_refused(tmp_path):
    """§395 — a standing automation must not execute on the months-old snapshot."""
    store = await make_store(tmp_path)
    _authority, standing, record = await _seal_standing(store)
    with pytest.raises(StandingAuthorityError, match="STALE_SNAPSHOT"):
        await standing.derive_run_authority(
            record, run_id="wfrun_2", trigger=TRIGGER, artifact_id="wfart_statements_1",
            workflow_version=1, parameters={"broker_alias": "primary_mt5", "document_type": "statement"},
            run_snapshot_id=record.source_snapshot_id, run_context_digest="sha256:x",
            operation_action_class=ActionClass.A2,
        )


async def test_device_revocation_invalidates_future_runs(tmp_path):
    """§§392, 400 — revoking the originating device kills derived automation authority."""
    store = await make_store(tmp_path)
    _authority, standing, record = await _seal_standing(store)

    await standing.derive_run_authority(
        record, run_id="wfrun_a", trigger=TRIGGER, artifact_id="wfart_statements_1",
        workflow_version=1, parameters={"broker_alias": "primary_mt5", "document_type": "statement"},
        run_snapshot_id="ctx-run-a", run_context_digest="sha256:a",
        operation_action_class=ActionClass.A2,
    )

    await revoke_device(store)

    with pytest.raises(StandingAuthorityError, match="SOURCE_DEVICE_REVOKED"):
        await standing.derive_run_authority(
            record, run_id="wfrun_b", trigger=TRIGGER, artifact_id="wfart_statements_1",
            workflow_version=1,
            parameters={"broker_alias": "primary_mt5", "document_type": "statement"},
            run_snapshot_id="ctx-run-b", run_context_digest="sha256:b",
            operation_action_class=ActionClass.A2,
        )


async def test_revoking_standing_authority_blocks_runs(tmp_path):
    """§400 — explicit revocation of the standing authority itself."""
    store = await make_store(tmp_path)
    _authority, standing, record = await _seal_standing(store)
    assert await standing.revoke(record.authority_id) is True

    refreshed = await standing.get(record.authority_id)
    assert refreshed is not None and refreshed.revoked
    with pytest.raises(StandingAuthorityError, match="STANDING_AUTHORITY_REVOKED"):
        await standing.derive_run_authority(
            refreshed, run_id="wfrun_c", trigger=TRIGGER, artifact_id="wfart_statements_1",
            workflow_version=1,
            parameters={"broker_alias": "primary_mt5", "document_type": "statement"},
            run_snapshot_id="ctx-run-c", run_context_digest="sha256:c",
            operation_action_class=ActionClass.A2,
        )


async def test_disabled_standing_intent_blocks_runs(tmp_path):
    store = await make_store(tmp_path)
    _authority, standing, record = await _seal_standing(store)
    await store.execute(
        "UPDATE automation_standing_intents SET enabled = 0 WHERE intent_id = ?",
        (record.standing_intent_id,),
    )
    with pytest.raises(StandingAuthorityError, match="STANDING_INTENT_DISABLED"):
        await standing.derive_run_authority(
            record, run_id="wfrun_d", trigger=TRIGGER, artifact_id="wfart_statements_1",
            workflow_version=1,
            parameters={"broker_alias": "primary_mt5", "document_type": "statement"},
            run_snapshot_id="ctx-run-d", run_context_digest="sha256:d",
            operation_action_class=ActionClass.A2,
        )


async def test_a4_can_never_become_standing_authority(tmp_path):
    """§§391, 401 — an A4 mutation always needs a fresh owner approval."""
    store = await make_store(tmp_path)
    authority = CommandAuthorityService(store)
    standing = StandingAutomationAuthorityService(store, authority)
    await enroll_device(store)
    await seal_owner_command(authority, effective=ActionClass.A4, owner_approved=True)
    intent_id = await seed_standing_intent(store)

    with pytest.raises(StandingAuthorityError, match="action_class_prohibited"):
        await standing.seal(
            standing_intent_id=intent_id, source_command_id="cmd-owner-1",
            capability_id="wfcap_statements", artifact_id="wfart_statements_1",
            workflow_version=1, action_class_ceiling=ActionClass.A4, trigger=TRIGGER,
            parameter_constraints=CONSTRAINTS, allowed_effects=[], allowed_domains=[],
            owner_authority_evidence_ref="evidence://owner/approval/1",
            policy_version="van-automation-policy-1",
        )


async def test_a4_operation_refused_under_a3_standing_authority(tmp_path):
    """§401 — even a valid standing authority cannot execute an A4 operation."""
    store = await make_store(tmp_path)
    _authority, standing, record = await _seal_standing(store, ceiling=ActionClass.A3)
    with pytest.raises(StandingAuthorityError, match="ACTION_CLASS_PROHIBITED"):
        await standing.derive_run_authority(
            record, run_id="wfrun_e", trigger=TRIGGER, artifact_id="wfart_statements_1",
            workflow_version=1,
            parameters={"broker_alias": "primary_mt5", "document_type": "statement"},
            run_snapshot_id="ctx-run-e", run_context_digest="sha256:e",
            operation_action_class=ActionClass.A4,
        )


async def test_standing_authority_cannot_exceed_source_command(tmp_path):
    store = await make_store(tmp_path)
    authority = CommandAuthorityService(store)
    standing = StandingAutomationAuthorityService(store, authority)
    await enroll_device(store)
    await seal_owner_command(authority, effective=ActionClass.A1)
    intent_id = await seed_standing_intent(store)
    with pytest.raises(StandingAuthorityError, match="exceeds_source_command"):
        await standing.seal(
            standing_intent_id=intent_id, source_command_id="cmd-owner-1",
            capability_id="wfcap_statements", artifact_id="wfart_statements_1",
            workflow_version=1, action_class_ceiling=ActionClass.A3, trigger=TRIGGER,
            parameter_constraints=CONSTRAINTS, allowed_effects=[], allowed_domains=[],
            owner_authority_evidence_ref="evidence://owner/approval/1",
            policy_version="van-automation-policy-1",
        )


async def test_derived_authority_cannot_seed_another_standing_authority(tmp_path):
    """§390 — no authority laundering: a derived record cannot beget a new grant."""
    store = await make_store(tmp_path)
    _authority, standing, record = await _seal_standing(store)
    derived = await standing.derive_run_authority(
        record, run_id="wfrun_f", trigger=TRIGGER, artifact_id="wfart_statements_1",
        workflow_version=1, parameters={"broker_alias": "primary_mt5", "document_type": "statement"},
        run_snapshot_id="ctx-run-f", run_context_digest="sha256:f",
        operation_action_class=ActionClass.A2,
    )
    with pytest.raises(StandingAuthorityError, match="requires_owner_command"):
        await standing.seal(
            standing_intent_id=record.standing_intent_id,
            source_command_id=derived.command_id, capability_id="wfcap_statements",
            artifact_id="wfart_statements_1", workflow_version=1,
            action_class_ceiling=ActionClass.A2, trigger=TRIGGER,
            parameter_constraints=CONSTRAINTS, allowed_effects=[], allowed_domains=[],
            owner_authority_evidence_ref="evidence://owner/approval/1",
            policy_version="van-automation-policy-1",
        )


async def test_broadened_trigger_is_refused(tmp_path):
    """§397 — weekly cannot silently become every minute."""
    store = await make_store(tmp_path)
    _authority, standing, record = await _seal_standing(store)
    broadened = {**TRIGGER, "cron": "* * * * *"}
    with pytest.raises(StandingAuthorityError, match="TRIGGER_MISMATCH"):
        await standing.derive_run_authority(
            record, run_id="wfrun_g", trigger=broadened, artifact_id="wfart_statements_1",
            workflow_version=1,
            parameters={"broker_alias": "primary_mt5", "document_type": "statement"},
            run_snapshot_id="ctx-run-g", run_context_digest="sha256:g",
            operation_action_class=ActionClass.A2,
        )


async def test_parameters_outside_constraints_are_refused(tmp_path):
    """§398 — STANDING_AUTHORITY_PARAMETER_MISMATCH."""
    store = await make_store(tmp_path)
    _authority, standing, record = await _seal_standing(store)
    with pytest.raises(StandingAuthorityError, match="PARAMETER_MISMATCH"):
        await standing.derive_run_authority(
            record, run_id="wfrun_h", trigger=TRIGGER, artifact_id="wfart_statements_1",
            workflow_version=1,
            parameters={"broker_alias": "some_other_broker", "document_type": "statement"},
            run_snapshot_id="ctx-run-h", run_context_digest="sha256:h",
            operation_action_class=ActionClass.A2,
        )


async def test_changed_workflow_version_does_not_inherit_authority(tmp_path):
    """§396 — a repaired workflow cannot silently inherit a standing grant."""
    store = await make_store(tmp_path)
    _authority, standing, record = await _seal_standing(store)
    with pytest.raises(StandingAuthorityError, match="WORKFLOW_VERSION_MISMATCH"):
        await standing.derive_run_authority(
            record, run_id="wfrun_i", trigger=TRIGGER, artifact_id="wfart_statements_1",
            workflow_version=2,
            parameters={"broker_alias": "primary_mt5", "document_type": "statement"},
            run_snapshot_id="ctx-run-i", run_context_digest="sha256:i",
            operation_action_class=ActionClass.A2,
        )


async def test_expired_standing_authority_is_refused(tmp_path):
    store = await make_store(tmp_path)
    past = int(time.time() * 1000) - 1000
    _authority, standing, record = await _seal_standing(store, expires_at_ms=past)
    with pytest.raises(StandingAuthorityError, match="EXPIRED"):
        await standing.derive_run_authority(
            record, run_id="wfrun_j", trigger=TRIGGER, artifact_id="wfart_statements_1",
            workflow_version=1,
            parameters={"broker_alias": "primary_mt5", "document_type": "statement"},
            run_snapshot_id="ctx-run-j", run_context_digest="sha256:j",
            operation_action_class=ActionClass.A2,
        )


async def test_old_authority_records_still_validate(tmp_path):
    """§394 — records serialized before authority_source existed keep working."""
    store = await make_store(tmp_path)
    await enroll_device(store)
    authority = CommandAuthorityService(store)
    legacy = (
        '{"command_id":"cmd-legacy","device_id":"dev-owner-1","principal_type":"OWNER_DEVICE",'
        '"requested_by":"dev-owner-1","origin_channel":"VOICE","signed_action_class":"A2",'
        '"effective_action_class":"A2","typed_action_id":null,"snapshot_id":"ctx-legacy",'
        '"context_digest":"sha256:legacy","issued_at_unix":1,"expires_at_unix":null,'
        '"no_stale_replay":false,"owner_approved":false,"turn_id":null,"sealed_at_unix_ms":1000}'
    )
    await store.execute(
        "INSERT INTO runtime_meta(key, value, updated_at_unix_ms) VALUES (?, ?, ?)",
        ("command_authority:cmd-legacy", legacy, 1000),
    )
    record = await authority.get("cmd-legacy")
    assert record is not None
    assert record.authority_source is AuthoritySource.OWNER_COMMAND
    assert record.source_authority_id is None
