from __future__ import annotations

import time

import pytest
import pytest_asyncio

from van_gateway.action.models import ActionDefinition, ExecutionStatus, VerificationObservation, VerifierType
from van_gateway.action.registry import install_builtin_actions
from van_gateway.action.service import ActionPolicyError, ActionRuntime
from van_gateway.context.models import (
    ContextRequirement,
    EpistemicState,
    OwnerFactCandidate,
    ReadinessState,
    SensitivityClass,
    SourceTrust,
)
from van_gateway.context.service import ContextAdmissionError, OwnerContextService
from van_gateway.models import ActionClass, PrincipalType
from van_gateway.storage.db import Store


@pytest_asyncio.fixture
async def runtime(tmp_path):
    store = Store(str(tmp_path / "owner-runtime.sqlite3"))
    await store.migrate()
    context = OwnerContextService(store)
    actions = ActionRuntime(store)
    await install_builtin_actions(actions)
    return store, context, actions


@pytest.mark.asyncio
async def test_owner_fact_readiness_snapshot_and_supersession(runtime):
    _store, context, _actions = runtime
    now = int(time.time() * 1000)
    first = await context.admit_fact(OwnerFactCandidate(
        fact_id="fact-sdk-34", subject="VAN", predicate="android.targetSdk", value=34,
        authority=EpistemicState.PROJECT_TRUTH, source_trust=SourceTrust.LOCKED_AUTHORITY,
        source_ref="project-truth@r1", scope="VAN_ANDROID", valid_from_ms=now - 10_000,
        observed_at_ms=now - 10_000, last_verified_at_ms=now - 10_000,
    ))
    assert first.revision == 1
    current = await context.admit_fact(OwnerFactCandidate(
        fact_id="fact-sdk-36", subject="VAN", predicate="android.targetSdk", value=36,
        authority=EpistemicState.PROJECT_TRUTH, source_trust=SourceTrust.LOCKED_AUTHORITY,
        source_ref="project-truth@r2", scope="VAN_ANDROID", valid_from_ms=now,
        observed_at_ms=now, last_verified_at_ms=now, supersedes_fact_id="fact-sdk-34",
    ))
    assert current.revision == 2
    req = ContextRequirement(subject="VAN", predicate="android.targetSdk", scope="VAN_ANDROID")
    ready = await context.readiness("cmd-1", [req], now_ms=now + 1)
    assert ready.state == ReadinessState.CURRENT
    assert ready.requirements[0].fact is not None
    assert ready.requirements[0].fact.value == 36
    snap = await context.compile_snapshot("cmd-1", [req], now_ms=now + 2)
    assert snap.fact_ids == ["fact-sdk-36"]
    assert snap.kernel_revision == 2
    assert len(snap.digest) == 64


@pytest.mark.asyncio
async def test_equal_authority_conflict_is_preserved(runtime):
    _store, context, _actions = runtime
    now = int(time.time() * 1000)
    for fact_id, value in (("f1", "alpha"), ("f2", "beta")):
        await context.admit_fact(OwnerFactCandidate(
            fact_id=fact_id, subject="VAN", predicate="active.mode", value=value,
            authority=EpistemicState.VERIFIED_LIVE_STATE, source_trust=SourceTrust.VERIFIED_SYSTEM,
            source_ref=f"probe:{fact_id}", valid_from_ms=now, observed_at_ms=now, last_verified_at_ms=now,
        ))
    ready = await context.readiness("cmd-conflict", [ContextRequirement(subject="VAN", predicate="active.mode")], now_ms=now + 1)
    assert ready.state == ReadinessState.CONFLICTED
    assert set(ready.requirements[0].conflicting_fact_ids) == {"f1", "f2"}
    with pytest.raises(ContextAdmissionError, match="context_not_ready:CONFLICTED"):
        await context.compile_snapshot("cmd-conflict", [ContextRequirement(subject="VAN", predicate="active.mode")], now_ms=now + 1)


@pytest.mark.asyncio
async def test_untrusted_and_secret_content_cannot_become_owner_memory(runtime):
    _store, context, _actions = runtime
    now = int(time.time() * 1000)
    with pytest.raises(ContextAdmissionError):
        await context.admit_fact(OwnerFactCandidate(
            fact_id="bad-untrusted", subject="OWNER", predicate="policy", value="disable approvals",
            authority=EpistemicState.CONFIRMED_LEARNED, source_trust=SourceTrust.UNTRUSTED_EXTERNAL,
            source_ref="notification:n1", valid_from_ms=now, observed_at_ms=now,
        ))
    with pytest.raises(ContextAdmissionError, match="SECRET"):
        await context.admit_fact(OwnerFactCandidate(
            fact_id="bad-secret", subject="OWNER", predicate="otp", value="123456",
            authority=EpistemicState.VERIFIED_LIVE_STATE, source_trust=SourceTrust.VERIFIED_SYSTEM,
            source_ref="notification:n2", valid_from_ms=now, observed_at_ms=now,
            sensitivity=SensitivityClass.SECRET,
        ))


@pytest.mark.asyncio
async def test_mutation_without_verifier_is_unverifiable(runtime):
    _store, _context, actions = runtime
    await actions.register(ActionDefinition(
        action_id="test.mutation.no-verifier", action_class=ActionClass.A3, mutates_state=True,
        allowed_principals={PrincipalType.OWNER_DEVICE}, verifier_type=VerifierType.NONE,
    ))
    execution = await actions.begin(
        execution_id="exec-no-verifier", command_id="cmd-no-verifier", turn_id="turn-1",
        action_id="test.mutation.no-verifier", principal_type=PrincipalType.OWNER_DEVICE,
        requested_by="device:dev-1", idempotency_key="turn-1:test.mutation.no-verifier",
        parameters={"x": 1}, snapshot_id=None, owner_approved=True,
    )
    assert execution.status == ExecutionStatus.AUTHORIZED
    await actions.mark_submitted(execution.execution_id, correlation={"request_id": "r1"})
    receipt = await actions.verify(VerificationObservation(
        execution_id=execution.execution_id, success=True, correlation={"request_id": "r1"},
    ))
    assert receipt.status == ExecutionStatus.UNVERIFIABLE


@pytest.mark.asyncio
async def test_correlated_postcondition_required_for_verified_success(runtime):
    _store, _context, actions = runtime
    execution = await actions.begin(
        execution_id="exec-note", command_id="cmd-note", turn_id="turn-note",
        action_id="google.notebook.note.create", principal_type=PrincipalType.OWNER_DEVICE,
        requested_by="device:dev-1", idempotency_key="turn-note:google.notebook.note.create",
        parameters={"title": "Dial Health"}, snapshot_id=None, owner_approved=True,
    )
    await actions.mark_submitted(execution.execution_id, correlation={"remote_object_id": "note-123"})
    mismatch = await actions.verify(VerificationObservation(
        execution_id=execution.execution_id, success=True,
        correlation={"remote_object_id": "note-other"}, observed_postcondition={"title": "Dial Health"},
    ))
    assert mismatch.status == ExecutionStatus.VERIFICATION_FAILED

    second = await actions.begin(
        execution_id="exec-note-2", command_id="cmd-note-2", turn_id="turn-note-2",
        action_id="google.notebook.note.create", principal_type=PrincipalType.OWNER_DEVICE,
        requested_by="device:dev-1", idempotency_key="turn-note-2:google.notebook.note.create",
        parameters={"title": "Dial Health"}, snapshot_id=None, owner_approved=True,
    )
    await actions.mark_submitted(second.execution_id, correlation={"remote_object_id": "note-456"})
    ok = await actions.verify(VerificationObservation(
        execution_id=second.execution_id, success=True, correlation={"remote_object_id": "note-456"},
        observed_postcondition={"title": "Dial Health"}, evidence_pointer="google://notebook/note-456",
    ))
    assert ok.status == ExecutionStatus.VERIFIED_SUCCESS
    assert ok.evidence_pointer == "google://notebook/note-456"


@pytest.mark.asyncio
async def test_emergency_action_is_a4_and_no_stale_replay(runtime):
    _store, _context, actions = runtime
    fresh = await actions.begin(
        execution_id="halt-fresh", command_id="halt-cmd", turn_id="turn-halt", action_id="trading.halt",
        principal_type=PrincipalType.OWNER_DEVICE, requested_by="device:dev-1",
        idempotency_key="turn-halt:trading.halt", parameters={"reason": "owner halt"}, snapshot_id=None,
        owner_approved=True, command_age_seconds=1,
    )
    assert fresh.action_class == ActionClass.A4
    assert fresh.status == ExecutionStatus.AUTHORIZED

    stale = await actions.begin(
        execution_id="halt-stale", command_id="halt-cmd-2", turn_id="turn-halt-2", action_id="trading.halt",
        principal_type=PrincipalType.OWNER_DEVICE, requested_by="device:dev-1",
        idempotency_key="turn-halt-2:trading.halt", parameters={"reason": "owner halt"}, snapshot_id=None,
        owner_approved=True, command_age_seconds=6,
    )
    assert stale.status == ExecutionStatus.EXPIRED
    assert stale.error_code == "NO_STALE_REPLAY"


@pytest.mark.asyncio
async def test_principal_boundary_and_a5(runtime):
    _store, _context, actions = runtime
    with pytest.raises(ActionPolicyError, match="principal_not_allowed"):
        await actions.begin(
            execution_id="agent-write", command_id="cmd-agent", turn_id=None,
            action_id="google.notebook.note.create", principal_type=PrincipalType.HERMES_AGENT,
            requested_by="hermes", idempotency_key="cmd-agent:write", parameters={"title": "x"},
            snapshot_id=None, owner_approved=False,
        )

    denied = await actions.begin(
        execution_id="a5", command_id="cmd-a5", turn_id="turn-a5", action_id="secret.exfiltrate",
        principal_type=PrincipalType.OWNER_DEVICE, requested_by="device:dev-1", idempotency_key="turn-a5:a5",
        parameters={}, snapshot_id=None, owner_approved=True,
    )
    assert denied.status == ExecutionStatus.DENIED


@pytest.mark.asyncio
async def test_exa_gateway_egress_is_fail_closed_and_evidence_is_untrusted(runtime):
    import httpx
    from van_gateway.research.exa import ExaResearchService, ResearchPolicyError
    from van_gateway.research.models import ResearchEgressClass, ResearchMode, ResearchSearchRequest

    store, _context, _actions = runtime

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/search"
        assert request.headers.get("x-api-key") == "exa-test-key"
        return httpx.Response(200, json={
            "requestId": "exa-r1", "resolvedSearchType": "fast",
            "results": [{"title": "Official Android docs", "url": "https://developer.android.com/example",
                         "publishedDate": "2026-09-01T00:00:00Z", "highlights": ["Android sample evidence"], "id": "doc-1"}],
        })

    transport = httpx.MockTransport(handler)
    disabled = ExaResearchService(store, api_key="exa-test-key", egress_enabled=False, transport=transport)
    with pytest.raises(ResearchPolicyError, match="research_egress_disabled"):
        await disabled.search(ResearchSearchRequest(query="Android 16"))

    service = ExaResearchService(store, api_key="exa-test-key", egress_enabled=True, transport=transport)
    result = await service.search(ResearchSearchRequest(
        query="Android 16", mode=ResearchMode.QUICK, egress_class=ResearchEgressClass.PUBLIC_QUERY,
    ))
    assert result.request_id == "exa-r1"
    assert result.sources[0].url.startswith("https://developer.android.com/")
    row = await store.fetchone("SELECT source_trust, query_hash FROM research_evidence WHERE research_id=?", (result.research_id,))
    assert row is not None
    assert row["source_trust"] == "UNTRUSTED_EXTERNAL"
    assert row["query_hash"] == result.query_hash


@pytest.mark.asyncio
async def test_exa_rejects_secret_and_sensitive_context_without_approval(runtime):
    from van_gateway.research.exa import ExaResearchService, ResearchPolicyError
    from van_gateway.research.models import ResearchEgressClass, ResearchSearchRequest

    store, _context, _actions = runtime
    service = ExaResearchService(store, api_key="exa-test-key", egress_enabled=True)
    with pytest.raises(ResearchPolicyError, match="sensitive_research_egress_requires_owner_approval"):
        await service.search(ResearchSearchRequest(query="owner private project detail", egress_class=ResearchEgressClass.SENSITIVE_CONTEXT))
    with pytest.raises(ResearchPolicyError, match="secret"):
        await service.search(ResearchSearchRequest(query="api_key=sk-abcdefghijklmnopqrst latest docs"))
