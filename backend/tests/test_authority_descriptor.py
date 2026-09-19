"""P1-COH-003 — one descriptor for what an action may do, checked against what is enforced.

Seven vocabularies describe an action's authority, each locally sensible and none
canonical. The consequence is not that any one is wrong; it is that the mapping from an
action to its class and its required gate is re-derived at every boundary, so two
boundaries can disagree and nothing notices. A disagreement about what an action may do is
a disagreement about whether the owner had to be asked.

The risk in closing it is obvious and worth stating: a "canonical descriptor" that drifts
from the code is worse than none, because it is a seventh vocabulary wearing the word
canonical. So the load-bearing class here is the one that reads the orchestrator's own
enforcement and asserts the descriptor says the same thing — not a test of the descriptor
against itself.
"""

from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import pytest
import pytest_asyncio

from van_gateway.action.models import VerifierType
from van_gateway.action.registry import BUILTIN_ACTIONS
from van_gateway.authority.descriptor import (
    ACTION_REVERSIBILITY,
    GATE_RANK,
    VERIFICATION_ALIASES,
    EgressClass,
    Gate,
    Reversibility,
    canonical_verification,
    describe_action,
    describe_capability,
    gate_for,
)
from van_gateway.capability.models import CapabilityDeclaration, VerificationStrategy
from van_gateway.models import ActionClass
from van_gateway import orchestrator as orchestrator_module
from van_gateway.verification.production import (
    DECLARED_BUT_UNOBSERVABLE_STRATEGIES,
    WIRED_MISSION_STRATEGIES,
)

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = json.loads((ROOT / "registries" / "capabilities.json").read_text(encoding="utf-8"))
DECLARATIONS = [CapabilityDeclaration.model_validate(row) for row in REGISTRY["capabilities"]]


class TestTheDescriptorAgreesWithWhatIsEnforced:
    """The test that makes this canonical instead of an eighth vocabulary."""

    @staticmethod
    def _orchestrator_source() -> str:
        """The handler's source with comments stripped.

        Stripped because a comment naming A4 would satisfy a substring check while the
        branch that enforces it was gone — the mistake that let two contract tests pass on
        commented-out code earlier in this programme.
        """
        source = inspect.getsource(orchestrator_module)
        return "\n".join(line.split("#", 1)[0] for line in source.splitlines())

    def test_a5_is_refused_and_the_orchestrator_refuses_it(self):
        assert gate_for(ActionClass.A5) is Gate.FORBIDDEN
        source = self._orchestrator_source()
        assert "effective_action_class == ActionClass.A5" in source

    def test_a4_needs_owner_approval_and_the_orchestrator_requires_it(self):
        assert gate_for(ActionClass.A4) is Gate.OWNER_APPROVAL
        source = self._orchestrator_source()
        assert "effective_action_class == ActionClass.A4" in source
        # And the approval is verified rather than accepted on presentation.
        assert "verify_and_consume" in source

    def test_nothing_below_a4_is_described_as_needing_an_approval(self):
        """A descriptor that over-claims is as wrong as one that under-claims: it would
        make an owner prompt look mandatory where the code never raises one."""
        for action_class in (ActionClass.A1, ActionClass.A2, ActionClass.A3):
            assert gate_for(action_class) is Gate.DEVICE_SIGNATURE

    def test_a_disabled_action_is_forbidden_whatever_its_class(self):
        disabled = next(d for d in BUILTIN_ACTIONS if not d.enabled)
        descriptor = describe_action(disabled)
        assert descriptor.gate is Gate.FORBIDDEN
        assert descriptor.enabled is False

    def test_the_gate_ladder_is_ordered(self):
        """`needs_owner_in_the_loop` is a comparison, so the order has to be real."""
        assert (
            GATE_RANK[Gate.NONE]
            < GATE_RANK[Gate.DEVICE_SIGNATURE]
            < GATE_RANK[Gate.OWNER_APPROVAL]
            < GATE_RANK[Gate.FORBIDDEN]
        )


class TestEveryRegisteredActionHasOneDescriptor:
    def test_every_builtin_action_describes(self):
        for definition in BUILTIN_ACTIONS:
            descriptor = describe_action(definition)
            assert descriptor.subject_id == definition.action_id
            assert descriptor.action_class is definition.action_class

    def test_a_mutating_action_has_a_decided_reversibility(self):
        """UNDECLARED is the honest answer for something nobody has decided, and it must
        not be where a mutating action quietly lands.

        The alternative — inferring reversibility from the action class — would be wrong in
        both directions: an A3 note create is reversible and an A4 delete is not, and both
        would be guessed the same way.
        """
        undecided = [
            d.action_id for d in BUILTIN_ACTIONS
            if d.mutates_state
            and describe_action(d).reversibility is Reversibility.UNDECLARED
        ]
        assert undecided == [], f"reversibility undecided for {undecided}"

    def test_a_read_only_action_is_not_marked_reversible(self):
        """READ_ONLY and REVERSIBLE are different claims: one says there is nothing to
        undo, the other says undoing is possible."""
        for definition in BUILTIN_ACTIONS:
            if not definition.mutates_state:
                assert describe_action(definition).reversibility is Reversibility.READ_ONLY

    def test_the_reversibility_map_names_no_action_that_does_not_exist(self):
        known = {d.action_id for d in BUILTIN_ACTIONS}
        assert set(ACTION_REVERSIBILITY) <= known


class TestEveryDeclaredCapabilityHasOneDescriptor:
    def test_every_declaration_describes(self):
        assert DECLARATIONS
        for declaration in DECLARATIONS:
            descriptor = describe_capability(declaration)
            assert descriptor.subject_id == declaration.capability_id

    def test_a_capability_may_raise_its_gate_but_never_lower_it(self):
        """`requires_owner_presence` is the one place the capability registry is stricter
        than the action class. Allowing it to work the other way would let a capability
        declare its way out of an owner approval."""
        for declaration in DECLARATIONS:
            descriptor = describe_capability(declaration)
            floor = gate_for(declaration.authority_class)
            assert GATE_RANK[descriptor.gate] >= GATE_RANK[floor], declaration.capability_id

    def test_owner_presence_raises_the_gate_even_on_a_low_class(self):
        low = CapabilityDeclaration(
            capability_id="test.low", provider="p", executor="e",
            capability_class="NATIVE_READ", authority_class=ActionClass.A2,
            requires_owner_presence=True,
        )
        assert describe_capability(low).gate is Gate.OWNER_APPROVAL

    def test_an_externally_disclosing_capability_says_so(self):
        disclosing = [
            describe_capability(d) for d in DECLARATIONS
            if d.privacy_class.value == "EXTERNAL_DISCLOSING"
        ]
        for descriptor in disclosing:
            assert descriptor.egress is EgressClass.EXTERNAL_DISCLOSING


class TestTheThreeVerificationVocabulariesAgree:
    """The concrete half of the finding.

    `VerifierType.READ_BACK`, `VerificationStrategy.API_READBACK` and the mission strategy
    `api-readback` are the same thing in three spellings, and nothing translated between
    them — so a capability declaring one and an action declaring another looked unrelated.
    """

    def test_every_verifier_type_translates(self):
        for verifier_type in VerifierType:
            assert canonical_verification(verifier_type)

    def test_every_verification_strategy_translates(self):
        for strategy in VerificationStrategy:
            assert canonical_verification(strategy)

    def test_the_two_registries_agree_on_a_readback(self):
        assert canonical_verification(VerifierType.READ_BACK) == canonical_verification(
            VerificationStrategy.API_READBACK
        )

    def test_every_canonical_name_is_one_the_mission_registry_knows(self):
        """A translation that produced a name no verifier answers to would be a rename,
        not a reconciliation."""
        known = set(WIRED_MISSION_STRATEGIES) | set(DECLARED_BUT_UNOBSERVABLE_STRATEGIES)
        known |= {"none", "provider-receipt", "state-predicate", "domain-attestation"}
        unknown = {name for name in VERIFICATION_ALIASES.values() if name not in known}
        assert unknown == set(), unknown

    def test_an_unknown_strategy_raises_rather_than_passing_through(self):
        """Forwarding an untranslatable name is how an unverifiable action comes to look
        verified: something downstream would take it for a registered strategy."""
        with pytest.raises(ValueError, match="no canonical verification strategy"):
            canonical_verification("whatever-the-engine-said")

    def test_translation_is_idempotent(self):
        for name in set(VERIFICATION_ALIASES.values()):
            assert canonical_verification(name) == name


class TestTheDescriptorIsADerivationNotAStore:
    """The design constraint, asserted so it cannot quietly stop holding.

    The whole reason a canonical view can be canonical is that it points at the existing
    authorities instead of copying them. A descriptor module that grew its own table of
    action classes would be the eighth vocabulary this finding is about.
    """

    def test_it_declares_no_action_class_of_its_own(self):
        source = (
            Path(__file__).resolve().parents[1]
            / "van_gateway" / "authority" / "descriptor.py"
        ).read_text(encoding="utf-8")
        body = "\n".join(line.split("#", 1)[0] for line in source.splitlines())
        # It may import ActionClass; it may not define one.
        assert not re.search(r"^class\s+ActionClass\b", body, re.M)
        assert "from van_gateway.models import ActionClass" in body

    def test_it_holds_no_database_table(self):
        source = (
            Path(__file__).resolve().parents[1]
            / "van_gateway" / "authority" / "descriptor.py"
        ).read_text(encoding="utf-8")
        for verb in ("INSERT INTO", "UPDATE ", "CREATE TABLE", "SELECT "):
            assert verb not in source.upper().replace("UPDATED", ""), verb

    def test_every_class_it_does_define_had_no_vocabulary_before(self):
        """Gate and Reversibility are the two additions, and they are additions because
        "what must happen before this runs" was an `if` in the orchestrator and
        reversibility was nowhere at all."""
        from van_gateway.authority import descriptor

        defined = {
            name for name, value in vars(descriptor).items()
            if isinstance(value, type) and value.__module__ == descriptor.__name__
        }
        assert defined == {"Gate", "Reversibility", "EgressClass", "ActionDescriptor"}


@pytest.mark.asyncio
class TestTheRouterAndTheDescriptorCannotDisagree:
    """The property the finding is actually about.

    Two boundaries deriving the same rule separately is fine right up until they differ,
    and nothing would notice. So rather than rewriting the routability gate to call the
    descriptor — churn with real risk in the one place that decides whether the owner gets
    asked — these assert the two say the same thing for every declared capability.
    """

    @staticmethod
    async def _registry(store):
        from van_gateway.capability.registry import CapabilityRegistry

        return CapabilityRegistry(store)

    async def test_owner_presence_is_refused_exactly_where_the_gate_says_approval(self, store):
        from van_gateway.capability.models import RoutingConstraints, RoutabilityReason

        registry = await self._registry(store)
        for capability_id in registry.capability_ids:
            declaration = registry.require(capability_id)
            descriptor = describe_capability(declaration)
            verdict = await registry.routability(
                capability_id,
                constraints=RoutingConstraints(
                    max_action_class=declaration.authority_class, owner_present=False
                ),
            )
            if verdict.reason is RoutabilityReason.OWNER_PRESENCE_REQUIRED:
                assert descriptor.gate is Gate.OWNER_APPROVAL, capability_id

    async def test_the_authority_ceiling_refuses_exactly_where_the_class_exceeds_it(self, store):
        from van_gateway.capability.models import RoutingConstraints, RoutabilityReason

        registry = await self._registry(store)
        for capability_id in registry.capability_ids:
            declaration = registry.require(capability_id)
            descriptor = describe_capability(declaration)
            verdict = await registry.routability(
                capability_id,
                constraints=RoutingConstraints(
                    max_action_class=ActionClass.A1, owner_present=True
                ),
            )
            exceeds = descriptor.action_class is not ActionClass.A1
            if exceeds:
                assert verdict.reason is RoutabilityReason.ABOVE_AUTHORITY_CEILING, capability_id

    async def test_external_disclosure_is_refused_exactly_where_the_egress_says_so(self, store):
        from van_gateway.capability.models import RoutingConstraints, RoutabilityReason

        registry = await self._registry(store)
        for capability_id in registry.capability_ids:
            declaration = registry.require(capability_id)
            descriptor = describe_capability(declaration)
            verdict = await registry.routability(
                capability_id,
                constraints=RoutingConstraints(
                    max_action_class=declaration.authority_class,
                    owner_present=True,
                    permit_external_disclosure=False,
                ),
            )
            if verdict.reason is RoutabilityReason.PRIVACY_NOT_PERMITTED:
                assert descriptor.egress is EgressClass.EXTERNAL_DISCLOSING, capability_id


@pytest_asyncio.fixture
async def store(tmp_path):
    from van_gateway.storage.db import Store

    s = Store(str(tmp_path / "authority.sqlite3"))
    await s.migrate()
    return s
