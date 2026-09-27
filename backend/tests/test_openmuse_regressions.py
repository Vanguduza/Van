"""OMV-009 regression harvest from OpenMuse failure classes.

These are VAN-native assertions. They do not create an OpenMuse execution path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest_automation import make_action_runtime, make_store
from van_gateway.action.models import ExecutionStatus, VerificationObservation
from van_gateway.browser.interactive_models import InteractiveBrowserSession, Viewport
from van_gateway.browser.models import BrowserEvidence
from van_gateway.models import PrincipalType


@pytest.mark.asyncio
async def test_terminal_reviewed_action_never_reverts_to_pending_on_replay(tmp_path):
    store = await make_store(tmp_path)
    runtime = await make_action_runtime(store)
    execution = await runtime.begin(
        execution_id="exec-1", command_id="cmd-1", turn_id="turn-1",
        action_id="research.web.search", principal_type=PrincipalType.OWNER_DEVICE,
        requested_by="device-1", idempotency_key="idem-1",
        parameters={"query": "test"}, snapshot_id=None, owner_approved=False,
    )
    await runtime.mark_executing(execution.execution_id)
    await runtime.mark_submitted(
        execution.execution_id, correlation={"request": "r1"}, evidence_pointer="ev://submit"
    )
    await runtime.mark_verifying(execution.execution_id)
    receipt = await runtime.verify(VerificationObservation(
        execution_id=execution.execution_id, success=True,
        correlation={"request": "r1"}, evidence_pointer="ev://verified",
    ))
    assert receipt.status is ExecutionStatus.VERIFIED_SUCCESS

    replay = await runtime.begin(
        execution_id="exec-new", command_id="cmd-1", turn_id="turn-2",
        action_id="research.web.search", principal_type=PrincipalType.OWNER_DEVICE,
        requested_by="device-1", idempotency_key="idem-1",
        parameters={"query": "test"}, snapshot_id=None, owner_approved=False,
    )
    assert replay.execution_id == "exec-1"
    assert replay.status is ExecutionStatus.VERIFIED_SUCCESS
    assert replay.terminal is True


def test_browser_evidence_identity_is_not_live_session_identity():
    evidence = BrowserEvidence(
        evidence_id="evidence-1", task_id="task-1", kind="snapshot",
        url_digest="a" * 64, screenshot_digest="b" * 64, created_at_ms=1,
    )
    session = InteractiveBrowserSession(
        session_id="session-1", owner_device_id="device-1",
        profile_alias="public_research", viewport=Viewport(width=1080, height=2400),
    )
    assert evidence.evidence_id != session.session_id
    assert "session_id" not in BrowserEvidence.model_fields
    assert "evidence_id" not in InteractiveBrowserSession.model_fields


def test_openmuse_convergence_never_adds_a_peer_agent_runtime():
    root = Path(__file__).resolve().parents[2]
    security = (root / "docs" / "SECURITY_POLICY.md").read_text(encoding="utf-8")
    pack = (root / "docs" / "OPENMUSE_VAN_CONVERGENCE_DEVELOPMENT_PACK_REV_1.md").read_text(encoding="utf-8")
    assert "Hermes profile `van` is the sole agent runtime" in security
    assert "Hermes profile `van` remains VAN's sole agent runtime" in pack
    assert "OpenMuse agent peer" not in pack
