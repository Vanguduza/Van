"""Rev 1.3 §§160-161, 412 — run capability grants and durable replay protection.

§412 lists the required cases explicitly and adds a rule that shapes the whole
design: *"No in-memory-only replay protection is acceptable."* Every test below
therefore goes through the database, and the restart case rebuilds the service
from scratch to prove a consumed nonce cannot come back.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from conftest_automation import enroll_device, make_store, seal_owner_command
from van_gateway.automation.grants import (
    GrantDenied,
    GrantKind,
    RunGrantService,
)
from van_gateway.command.authority import CommandAuthorityService
from van_gateway.models import ActionClass

SIGNING_KEY = "test-grant-signing-key-not-a-real-secret"


async def _mint(store, *, kind=GrantKind.SINGLE_USE_MUTATION, max_uses=1, ttl=300, ceiling=ActionClass.A3):
    authority = CommandAuthorityService(store)
    await enroll_device(store)
    await seal_owner_command(authority, effective=ActionClass.A3)
    grants = RunGrantService(store, signing_key=SIGNING_KEY)
    minted = await grants.mint(
        run_id="wfrun_1", command_id="cmd-owner-1", capability_id="wfcap_statements",
        artifact_id="wfart_statements_1", artifact_version=1, context_snapshot_id="ctx-run-1",
        input_digest="sha256:input", action_class_ceiling=ceiling,
        allowed_gateway_operations=["seal_evidence", "emit_event"],
        allowed_external_domains=["reports.example.com"], grant_kind=kind, max_uses=max_uses,
        ttl_seconds=ttl,
    )
    return grants, minted


async def test_single_use_nonce_consumes_once(tmp_path):
    """§412 — single mutation nonce consumes once."""
    store = await make_store(tmp_path)
    grants, minted = await _mint(store)

    await grants.redeem(
        token=minted.token, grant=minted.grant, requested_operation="seal_evidence",
        requested_action_class=ActionClass.A3,
    )
    with pytest.raises(GrantDenied) as exc:
        await grants.redeem(
            token=minted.token, grant=minted.grant, requested_operation="seal_evidence",
            requested_action_class=ActionClass.A3,
        )
    assert exc.value.reason == "GRANT_REPLAYED"


async def test_parallel_replay_exactly_one_succeeds(tmp_path):
    """§412 — parallel replay: exactly one succeeds."""
    store = await make_store(tmp_path)
    grants, minted = await _mint(store)

    async def attempt() -> bool:
        try:
            await grants.redeem(
                token=minted.token, grant=minted.grant, requested_operation="seal_evidence",
                requested_action_class=ActionClass.A3,
            )
            return True
        except GrantDenied:
            return False

    results = await asyncio.gather(*(attempt() for _ in range(8)))
    assert sum(results) == 1, "exactly one concurrent redemption may win"


async def test_expired_nonce_denied(tmp_path):
    store = await make_store(tmp_path)
    grants, minted = await _mint(store, ttl=30)
    future = int(time.time() * 1000) + 60_000
    with pytest.raises(GrantDenied) as exc:
        await grants.redeem(
            token=minted.token, grant=minted.grant, requested_operation="seal_evidence",
            requested_action_class=ActionClass.A3, now_ms=future,
        )
    assert exc.value.reason == "GRANT_EXPIRED"


async def test_revoked_nonce_denied(tmp_path):
    store = await make_store(tmp_path)
    grants, minted = await _mint(store)
    assert await grants.revoke_run("wfrun_1") == 1
    with pytest.raises(GrantDenied) as exc:
        await grants.redeem(
            token=minted.token, grant=minted.grant, requested_operation="seal_evidence",
            requested_action_class=ActionClass.A3,
        )
    assert exc.value.reason == "SOURCE_AUTHORITY_REVOKED"


async def test_restart_does_not_resurrect_consumed_nonce(tmp_path):
    """§412 — the case that makes in-memory protection unacceptable."""
    store = await make_store(tmp_path)
    grants, minted = await _mint(store)
    await grants.redeem(
        token=minted.token, grant=minted.grant, requested_operation="seal_evidence",
        requested_action_class=ActionClass.A3,
    )

    # Simulate a process restart: brand-new service, same durable store.
    restarted = RunGrantService(store, signing_key=SIGNING_KEY)
    with pytest.raises(GrantDenied) as exc:
        await restarted.redeem(
            token=minted.token, grant=minted.grant, requested_operation="seal_evidence",
            requested_action_class=ActionClass.A3,
        )
    assert exc.value.reason == "GRANT_REPLAYED"


async def test_wrong_run_id_denied(tmp_path):
    store = await make_store(tmp_path)
    grants, minted = await _mint(store)
    tampered = minted.grant.model_copy(update={"run_id": "wfrun_other"})
    with pytest.raises(GrantDenied) as exc:
        await grants.redeem(
            token=minted.token, grant=tampered, requested_operation="seal_evidence",
            requested_action_class=ActionClass.A3,
        )
    # The MAC covers run_id, so tampering is caught before the row is read.
    assert exc.value.reason == "GRANT_SIGNATURE_INVALID"


async def test_wrong_grant_id_denied(tmp_path):
    store = await make_store(tmp_path)
    grants, minted = await _mint(store)
    tampered = minted.grant.model_copy(update={"grant_id": "grant_forged"})
    with pytest.raises(GrantDenied) as exc:
        await grants.redeem(
            token=minted.token, grant=tampered, requested_operation="seal_evidence",
            requested_action_class=ActionClass.A3,
        )
    assert exc.value.reason == "GRANT_SIGNATURE_INVALID"


async def test_artifact_version_mismatch_denied(tmp_path):
    """§161 step 4 — ARTIFACT_VERSION_MISMATCH."""
    store = await make_store(tmp_path)
    grants, minted = await _mint(store)
    # Re-sign so the MAC passes and the *stored binding* is what rejects it,
    # proving the check is not merely signature-dependent.
    tampered = minted.grant.model_copy(update={"artifact_version": 2})
    token = f"{minted.token.split('.')[0]}.{grants._mac(minted.token.split('.')[0], tampered.canonical())}"
    with pytest.raises(GrantDenied) as exc:
        await grants.redeem(
            token=token, grant=tampered, requested_operation="seal_evidence",
            requested_action_class=ActionClass.A3,
        )
    assert exc.value.reason == "ARTIFACT_VERSION_MISMATCH"


async def test_context_binding_mismatch_denied(tmp_path):
    store = await make_store(tmp_path)
    grants, minted = await _mint(store)
    tampered = minted.grant.model_copy(update={"context_snapshot_id": "ctx-other"})
    nonce = minted.token.split(".")[0]
    token = f"{nonce}.{grants._mac(nonce, tampered.canonical())}"
    with pytest.raises(GrantDenied) as exc:
        await grants.redeem(
            token=token, grant=tampered, requested_operation="seal_evidence",
            requested_action_class=ActionClass.A3,
        )
    assert exc.value.reason == "CONTEXT_BINDING_MISMATCH"


async def test_operation_outside_grant_scope_denied(tmp_path):
    store = await make_store(tmp_path)
    grants, minted = await _mint(store)
    with pytest.raises(GrantDenied) as exc:
        await grants.redeem(
            token=minted.token, grant=minted.grant, requested_operation="write_project_truth",
            requested_action_class=ActionClass.A3,
        )
    assert exc.value.reason == "GRANT_SCOPE_MISMATCH"


async def test_action_class_above_ceiling_denied(tmp_path):
    store = await make_store(tmp_path)
    grants, minted = await _mint(store, ceiling=ActionClass.A2)
    with pytest.raises(GrantDenied) as exc:
        await grants.redeem(
            token=minted.token, grant=minted.grant, requested_operation="seal_evidence",
            requested_action_class=ActionClass.A3,
        )
    assert exc.value.reason == "GRANT_SCOPE_MISMATCH"


async def test_domain_outside_grant_scope_denied(tmp_path):
    store = await make_store(tmp_path)
    grants, minted = await _mint(store)
    with pytest.raises(GrantDenied) as exc:
        await grants.redeem(
            token=minted.token, grant=minted.grant, requested_operation="seal_evidence",
            requested_action_class=ActionClass.A3, requested_domain="evil.example.com",
        )
    assert exc.value.reason == "GRANT_SCOPE_MISMATCH"


async def test_source_device_revocation_denies_grant(tmp_path):
    """§161 step 11 — SOURCE_DEVICE_REVOKED."""
    store = await make_store(tmp_path)
    grants, minted = await _mint(store)
    await store.execute(
        "UPDATE devices SET revoked_at_unix = ? WHERE device_id = ?", (int(time.time()), "dev-owner-1")
    )
    with pytest.raises(GrantDenied) as exc:
        await grants.redeem(
            token=minted.token, grant=minted.grant, requested_operation="seal_evidence",
            requested_action_class=ActionClass.A3,
        )
    assert exc.value.reason == "SOURCE_DEVICE_REVOKED"


async def test_bounded_read_session_allows_counted_reuse(tmp_path):
    """§161 — read-only runs may make several calls, but never unbounded."""
    store = await make_store(tmp_path)
    grants, minted = await _mint(
        store, kind=GrantKind.BOUNDED_READ_SESSION, max_uses=3, ceiling=ActionClass.A2
    )
    for _ in range(3):
        await grants.redeem(
            token=minted.token, grant=minted.grant, requested_operation="emit_event",
            requested_action_class=ActionClass.A2,
        )
    with pytest.raises(GrantDenied) as exc:
        await grants.redeem(
            token=minted.token, grant=minted.grant, requested_operation="emit_event",
            requested_action_class=ActionClass.A2,
        )
    assert exc.value.reason == "GRANT_REPLAYED"


async def test_a4_grant_cannot_be_minted(tmp_path):
    """§160 — a run grant never carries A4; that needs a fresh owner approval."""
    store = await make_store(tmp_path)
    await enroll_device(store)
    grants = RunGrantService(store, signing_key=SIGNING_KEY)
    with pytest.raises(GrantDenied) as exc:
        await grants.mint(
            run_id="wfrun_x", command_id="cmd-owner-1", capability_id="c", artifact_id="a",
            artifact_version=1, context_snapshot_id="ctx", input_digest="d",
            action_class_ceiling=ActionClass.A4, allowed_gateway_operations=["x"],
            allowed_external_domains=[],
        )
    assert exc.value.reason == "GRANT_ACTION_CLASS_PROHIBITED"


async def test_unconfigured_signing_key_fails_closed(tmp_path):
    store = await make_store(tmp_path)
    grants = RunGrantService(store, signing_key="")
    with pytest.raises(GrantDenied) as exc:
        await grants.mint(
            run_id="r", command_id="c", capability_id="c", artifact_id="a", artifact_version=1,
            context_snapshot_id="ctx", input_digest="d", action_class_ceiling=ActionClass.A2,
            allowed_gateway_operations=[], allowed_external_domains=[],
        )
    assert exc.value.reason == "GRANT_SIGNING_KEY_UNCONFIGURED"
