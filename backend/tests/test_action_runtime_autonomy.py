"""GAP-F-008 — `DomainTrust`/`ProactivePolicyService` get a caller in the action path.

`ActionRuntime.begin` revalidated class/principal/idempotency/verifier rules and never
asked whether the domain had actually earned the unprompted principal's right to run the
action — an agent principal's authority was exactly what its `allowed_principals` grant
said, with no ceiling underneath that evidence or an owner grant could move. These tests
construct `ActionRuntime` directly, with and without the autonomy hook wired, so the
before/after is explicit rather than inferred from an integration test.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from conftest_automation import make_store
from van_gateway.action.models import ActionDefinition, ExecutionStatus, VerifierType
from van_gateway.action.service import ActionPolicyError, ActionRuntime
from van_gateway.models import ActionClass, PrincipalType
from van_gateway.proactive.autonomy import (
    ActionAutonomyGate,
    AutonomyLevel,
    AutonomyVerdict,
    DomainTrustService,
)

NOW = 1_800_000_000_000

READ_ACTION = ActionDefinition(
    action_id="calendar.events.list",
    action_class=ActionClass.A1,
    mutates_state=False,
    allowed_principals={PrincipalType.OWNER_DEVICE, PrincipalType.HERMES_AGENT},
    verifier_type=VerifierType.NONE,
)

MUTATING_ACTION = ActionDefinition(
    action_id="calendar.events.create",
    action_class=ActionClass.A3,
    mutates_state=True,
    allowed_principals={PrincipalType.OWNER_DEVICE, PrincipalType.HERMES_AGENT},
    verifier_type=VerifierType.NONE,
)

SYSTEM_ACTION = ActionDefinition(
    action_id="calendar.events.create",
    action_class=ActionClass.A3,
    mutates_state=True,
    allowed_principals={PrincipalType.OWNER_DEVICE, PrincipalType.SYSTEM},
    verifier_type=VerifierType.NONE,
)


@pytest_asyncio.fixture
async def store(tmp_path):
    return await make_store(tmp_path)


async def _begin(runtime, *, definition, principal_type, execution_id="exec-1", requested_by="hermes-1"):
    await runtime.register(definition)
    return await runtime.begin(
        execution_id=execution_id, command_id="cmd-1", turn_id=None,
        action_id=definition.action_id, principal_type=principal_type,
        requested_by=requested_by, idempotency_key=f"idem-{execution_id}",
        parameters={}, snapshot_id=None, owner_approved=False,
    )


@pytest.mark.asyncio
class TestWithoutAnAutonomyHookNothingChanges:
    async def test_a_hermes_agent_mutation_authorizes_exactly_as_before(self, store):
        """Backward compatibility: `autonomy=None` (the default) is a no-op."""
        runtime = ActionRuntime(store)
        execution = await _begin(
            runtime, definition=MUTATING_ACTION, principal_type=PrincipalType.HERMES_AGENT,
        )
        assert execution.status is ExecutionStatus.AUTHORIZED


@pytest.mark.asyncio
class TestWithTheHookWiredAgentPrincipalsAreGated:
    async def test_an_untrusted_domain_refuses_a_mutating_action_from_hermes(self, store):
        gate = ActionAutonomyGate(DomainTrustService(store))
        runtime = ActionRuntime(store, autonomy=gate)
        execution = await _begin(
            runtime, definition=MUTATING_ACTION, principal_type=PrincipalType.HERMES_AGENT,
        )
        assert execution.status is ExecutionStatus.AUTHORIZATION_REQUIRED
        assert execution.error_code is not None
        assert execution.error_code.startswith("AUTONOMY_DENIED:")

    async def test_the_same_refusal_applies_to_a_system_principal(self, store):
        gate = ActionAutonomyGate(DomainTrustService(store))
        runtime = ActionRuntime(store, autonomy=gate)
        execution = await _begin(
            runtime, definition=SYSTEM_ACTION, principal_type=PrincipalType.SYSTEM,
        )
        assert execution.status is ExecutionStatus.AUTHORIZATION_REQUIRED

    async def test_owner_device_actions_are_never_gated(self, store):
        """§31's authority is the owner's own; nothing here narrows it."""
        gate = ActionAutonomyGate(DomainTrustService(store))
        runtime = ActionRuntime(store, autonomy=gate)
        execution = await _begin(
            runtime, definition=MUTATING_ACTION, principal_type=PrincipalType.OWNER_DEVICE,
        )
        assert execution.status is ExecutionStatus.AUTHORIZED

    async def test_a_read_action_is_never_gated(self, store):
        gate = ActionAutonomyGate(DomainTrustService(store))
        runtime = ActionRuntime(store, autonomy=gate)
        execution = await _begin(
            runtime, definition=READ_ACTION, principal_type=PrincipalType.HERMES_AGENT,
        )
        assert execution.status is ExecutionStatus.AUTHORIZED

    async def test_earned_evidence_raises_the_ceiling_enough_to_permit_it(self, store):
        """§31 — trust grows from verified evidence, and the gate reads the ceiling it
        produces rather than granting anything of its own."""
        trust = DomainTrustService(store)
        # calendar.events -> domain "calendar.events"; enough verified successes to
        # reach S2_PREPARE, which A3 requires.
        for _ in range(12):
            await trust.record("calendar.events", verified_success=1, now_ms=NOW)
        gate = ActionAutonomyGate(trust)
        runtime = ActionRuntime(store, autonomy=gate)
        execution = await _begin(
            runtime, definition=MUTATING_ACTION, principal_type=PrincipalType.HERMES_AGENT,
        )
        assert execution.status is ExecutionStatus.AUTHORIZED

    async def test_an_owner_grant_also_permits_it(self, store):
        trust = DomainTrustService(store)
        await trust.grant(
            "calendar.events", level=AutonomyLevel.S3_REVERSIBLE_EXECUTION,
            evidence_ref="decision://owner-1", now_ms=NOW,
        )
        gate = ActionAutonomyGate(trust)
        runtime = ActionRuntime(store, autonomy=gate)
        execution = await _begin(
            runtime, definition=MUTATING_ACTION, principal_type=PrincipalType.HERMES_AGENT,
        )
        assert execution.status is ExecutionStatus.AUTHORIZED

    async def test_a_false_success_suspends_a_standing_grant(self, store):
        """§31's other asymmetry, reached through the same gate: demonstrated
        unreliability overrides a standing grant until the domain recovers."""
        trust = DomainTrustService(store)
        await trust.grant(
            "calendar.events", level=AutonomyLevel.S3_REVERSIBLE_EXECUTION,
            evidence_ref="decision://owner-1", now_ms=NOW,
        )
        await trust.record("calendar.events", verified_success=1, false_success=1, now_ms=NOW)
        gate = ActionAutonomyGate(trust)
        runtime = ActionRuntime(store, autonomy=gate)
        execution = await _begin(
            runtime, definition=MUTATING_ACTION, principal_type=PrincipalType.HERMES_AGENT,
        )
        assert execution.status is ExecutionStatus.AUTHORIZATION_REQUIRED

    async def test_a_refusal_never_persists_a_success_status(self, store):
        gate = ActionAutonomyGate(DomainTrustService(store))
        runtime = ActionRuntime(store, autonomy=gate)
        execution = await _begin(
            runtime, definition=MUTATING_ACTION, principal_type=PrincipalType.HERMES_AGENT,
        )
        assert execution.status not in (
            ExecutionStatus.AUTHORIZED, ExecutionStatus.VERIFIED_SUCCESS,
        )
        # And it is durable: re-reading the persisted execution shows the same refusal.
        reread = await runtime.get_execution(execution.execution_id)
        assert reread is not None and reread.status is ExecutionStatus.AUTHORIZATION_REQUIRED

    async def test_principal_not_allowed_is_still_checked_before_autonomy(self, store):
        """The existing principal gate is not bypassed by wiring an autonomy hook."""
        owner_only = ActionDefinition(
            action_id="google.gmail.send", action_class=ActionClass.A4, mutates_state=True,
            allowed_principals={PrincipalType.OWNER_DEVICE}, verifier_type=VerifierType.NONE,
        )
        gate = ActionAutonomyGate(DomainTrustService(store))
        runtime = ActionRuntime(store, autonomy=gate)
        await runtime.register(owner_only)
        with pytest.raises(ActionPolicyError, match="principal_not_allowed"):
            await runtime.begin(
                execution_id="exec-2", command_id="cmd-1", turn_id=None,
                action_id=owner_only.action_id, principal_type=PrincipalType.HERMES_AGENT,
                requested_by="hermes-1", idempotency_key="idem-2", parameters={},
                snapshot_id=None, owner_approved=False,
            )


@pytest.mark.asyncio
class TestTheGateDirectly:
    async def test_the_domain_is_the_first_two_dotted_segments(self, store):
        gate = ActionAutonomyGate(DomainTrustService(store))
        verdict = await gate.permits(
            action_id="google.gmail.send", action_class=ActionClass.A4,
            principal_type=PrincipalType.HERMES_AGENT, requested_by="h1",
        )
        assert isinstance(verdict, AutonomyVerdict)
        assert verdict.allowed is False
        assert "google.gmail" in verdict.reason

    async def test_a_single_segment_action_id_is_its_own_domain(self, store):
        gate = ActionAutonomyGate(DomainTrustService(store))
        verdict = await gate.permits(
            action_id="trading", action_class=ActionClass.A4,
            principal_type=PrincipalType.SYSTEM, requested_by="s1",
        )
        assert "trading" in verdict.reason

    async def test_a1_is_always_a_read(self, store):
        gate = ActionAutonomyGate(DomainTrustService(store))
        verdict = await gate.permits(
            action_id="owner.context.read", action_class=ActionClass.A1,
            principal_type=PrincipalType.HERMES_AGENT, requested_by="h1",
        )
        assert verdict.allowed is True
