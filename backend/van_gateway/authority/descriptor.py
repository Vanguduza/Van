"""P1-COH-003 — one descriptor for what an action is allowed to do.

Seven vocabularies describe that today, each locally sensible and none canonical:

  * `ActionClass` A1-A5 on a signed command and on a registered action;
  * `Sensitivity` on a mission (ROUTINE / PERSONAL / FINANCIAL / SECURITY);
  * `AutonomyLevel` S0-S5 on a domain, for what VAN may do unprompted;
  * `ControlScope` on a route, for which machine credential reaches it;
  * browser autonomy tiers and `BrowserBoundaryType` on a browsing surface;
  * `GrantKind` on a standing automation authority;
  * VATI's own risk authority, which is a separate process entirely.

The consequence is not that any one of them is wrong. It is that the mapping from an
action to its authority class and its required gate is *re-derived at every boundary*, so
two boundaries can disagree and nothing notices. That is the same shape as P2-COH-001's
eleven work-status vocabularies, one layer down and with worse consequences: a disagreement
about what an action may do is a disagreement about whether the owner had to be asked.

**This module is deliberately not an eighth vocabulary.** It introduces no store and no new
enum for anything that already has one. It is a *derivation*: one function that reads the
authorities that already exist and answers the question none of them answers on its own.
That is the pattern `capability/models.py` already established with `readiness_source` —
point at the existing authority rather than copying it, which is the only way a canonical
view can be canonical without becoming a rival source of truth.

What it does add is `Gate` and `Reversibility`, because those genuinely had no vocabulary:
"what must happen before this runs" was expressed as `if effective_action_class ==
ActionClass.A4` in the orchestrator, `requires_owner_presence` on a capability, and
`no_stale_replay` on an action, with nothing relating the three.

The load-bearing test is `test_authority_descriptor.py::TestTheDescriptorAgreesWithWhat
IsEnforced`: for every registered action and every declared capability, the gate this
module names must be the gate the orchestrator actually applies. A descriptor that drifts
from the code is worse than none, because it is a seventh vocabulary wearing the word
canonical.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from van_gateway.action.models import ActionDefinition, VerifierType
from van_gateway.capability.models import (
    CLASS_RANK,
    CapabilityDeclaration,
    PrivacyClass,
    VerificationStrategy,
)
from van_gateway.models import ActionClass


class Gate(str, Enum):
    """What must happen before an action runs. Ordered from open to closed."""

    #: Nothing. The action is a read and carries no side effect.
    NONE = "NONE"
    #: The command must be signed by a paired device. Every action clears this at minimum;
    #: it is named rather than assumed so a descriptor never reads as "no check at all".
    DEVICE_SIGNATURE = "DEVICE_SIGNATURE"
    #: An owner-signed, single-use approval challenge bound to this exact intent.
    OWNER_APPROVAL = "OWNER_APPROVAL"
    #: Refused whatever anyone signs. A5 is not a gate that can be passed.
    FORBIDDEN = "FORBIDDEN"


GATE_RANK = {Gate.NONE: 0, Gate.DEVICE_SIGNATURE: 1, Gate.OWNER_APPROVAL: 2, Gate.FORBIDDEN: 3}


class Reversibility(str, Enum):
    """Whether the owner can undo this, which is a different question from its class.

    An A3 that writes a note is reversible; an A4 that deletes a notebook is not. Nothing
    expressed this, so "reversible execution" in the autonomy ladder had no referent on the
    action side of the system.
    """

    READ_ONLY = "READ_ONLY"
    REVERSIBLE = "REVERSIBLE"
    IRREVERSIBLE = "IRREVERSIBLE"
    #: Stated rather than guessed. An action whose reversibility nobody has decided is not
    #: assumed reversible, because that is the assumption that costs something.
    UNDECLARED = "UNDECLARED"


class EgressClass(str, Enum):
    """Whether running this discloses owner data outside VAN."""

    NONE = "NONE"
    OWNER_PRIVATE = "OWNER_PRIVATE"
    EXTERNAL_DISCLOSING = "EXTERNAL_DISCLOSING"


#: The three spellings of the same verification vocabulary, reduced to one.
#:
#: `VerifierType` (action registry), `VerificationStrategy` (capability registry) and the
#: mission `verifier_class` strings each name the same small set of ways a side effect can
#: prove it happened, in three different spellings. Nothing translated between them, so a
#: capability declaring API_READBACK and an action declaring READ_BACK looked unrelated.
VERIFICATION_ALIASES: dict[str, str] = {
    # action registry
    VerifierType.NONE.value: "none",
    VerifierType.READ_BACK.value: "api-readback",
    VerifierType.RECEIPT.value: "provider-receipt",
    VerifierType.STATE_PREDICATE.value: "state-predicate",
    VerifierType.DOMAIN_ATTESTATION.value: "domain-attestation",
    # capability registry
    VerificationStrategy.NONE.value: "none",
    VerificationStrategy.API_READBACK.value: "api-readback",
    VerificationStrategy.PROVIDER_RECEIPT.value: "provider-receipt",
    VerificationStrategy.SCREENSHOT.value: "browser-evidence",
    VerificationStrategy.REPOSITORY_SHA.value: "repository-sha",
    VerificationStrategy.CI_RUN.value: "ci-run",
    VerificationStrategy.LEDGER_EVENT.value: "ledger-event",
    # Mission strategies, already canonical. Listed so translation is idempotent: a name
    # that has been translated once must survive being translated again, or a caller that
    # normalises twice gets an exception on the second pass.
    "none": "none",
    "api-readback": "api-readback",
    "provider-receipt": "provider-receipt",
    "state-predicate": "state-predicate",
    "domain-attestation": "domain-attestation",
    "browser-evidence": "browser-evidence",
    # P1-VERIFY-004 — a source mutation is read back per source, which is a narrower
    # question than the notebook readback and is not the same claim.
    "notebook-source-readback": "notebook-source-readback",
    "ledger-event": "ledger-event",
    "repository-sha": "repository-sha",
    "ci-run": "ci-run",
    # `trading-halt` is the mission registry's name for a halt read back from the VATI
    # ledger, which is the same kind of observation as a fill: the ledger says so.
    "trading-halt": "ledger-event",
}


#: Reversibility per registered action, decided rather than inferred.
#:
#: Inferring it from the action class would be wrong in both directions: an A3 note create
#: is reversible and an A4 delete is not, and both would be guessed the same way. An action
#: absent from this map is UNDECLARED, which is the honest answer and is what the test
#: refuses to let accumulate silently for a mutating action.
ACTION_REVERSIBILITY: dict[str, Reversibility] = {
    "owner.context.read": Reversibility.READ_ONLY,
    "research.web.search": Reversibility.READ_ONLY,
    "google.notebook.note.create": Reversibility.REVERSIBLE,
    "google.notebook.enterprise.create": Reversibility.REVERSIBLE,
    "google.notebook.enterprise.sources.add": Reversibility.REVERSIBLE,
    # A deleted notebook does not come back, which is why it is A4 and why the distinction
    # is worth carrying separately from the class.
    "google.notebook.enterprise.delete": Reversibility.IRREVERSIBLE,
    "google.notebook.enterprise.sources.delete": Reversibility.IRREVERSIBLE,
    # Halting is reversible by resuming; the owner is never stuck with it.
    "trading.halt": Reversibility.REVERSIBLE,
    "secret.exfiltrate": Reversibility.IRREVERSIBLE,
}


@dataclass(frozen=True)
class ActionDescriptor:
    """One answer to "what is this allowed to do, and what must happen first"."""

    subject_id: str
    action_class: ActionClass
    gate: Gate
    reversibility: Reversibility
    egress: EgressClass
    verification: str
    #: Which authority this was derived from, so a reader can go and check.
    derived_from: str
    #: True where the subject is declared but may never run at all.
    enabled: bool = True

    @property
    def mutates(self) -> bool:
        return CLASS_RANK[self.action_class] >= CLASS_RANK[ActionClass.A3]

    @property
    def needs_owner_in_the_loop(self) -> bool:
        return GATE_RANK[self.gate] >= GATE_RANK[Gate.OWNER_APPROVAL]


def gate_for(action_class: ActionClass, *, enabled: bool = True) -> Gate:
    """The gate the orchestrator applies, expressed once.

    This is the whole finding in four lines: the rule existed only as branches in
    `orchestrator.handle`, so every other boundary re-derived it and could differ. Read it
    against orchestrator.py — A5 is refused before anything else, A4 requires a verified
    approval proof bound to the command, and everything below is reached only by a
    correctly signed command.
    """
    if not enabled or action_class is ActionClass.A5:
        return Gate.FORBIDDEN
    if action_class is ActionClass.A4:
        return Gate.OWNER_APPROVAL
    if action_class is ActionClass.A1:
        return Gate.DEVICE_SIGNATURE
    return Gate.DEVICE_SIGNATURE


def describe_action(definition: ActionDefinition) -> ActionDescriptor:
    """The descriptor for a registered action."""
    return ActionDescriptor(
        subject_id=definition.action_id,
        action_class=definition.action_class,
        gate=gate_for(definition.action_class, enabled=definition.enabled),
        reversibility=ACTION_REVERSIBILITY.get(
            definition.action_id,
            Reversibility.READ_ONLY if not definition.mutates_state
            else Reversibility.UNDECLARED,
        ),
        # The action registry does not model egress; a read of the owner's own context
        # discloses nothing and everything else is decided by the capability that runs it.
        egress=EgressClass.NONE if not definition.mutates_state else EgressClass.OWNER_PRIVATE,
        verification=VERIFICATION_ALIASES[definition.verifier_type.value],
        derived_from="action.registry",
        enabled=definition.enabled,
    )


def describe_capability(declaration: CapabilityDeclaration) -> ActionDescriptor:
    """The descriptor for a declared capability.

    `requires_owner_presence` raises the gate above what the class alone implies, which is
    the one case where the capability registry is stricter than the action class. It is
    never allowed to lower it: a capability cannot declare its way out of an owner
    approval, and the test asserts that directly.
    """
    gate = gate_for(declaration.authority_class)
    if declaration.requires_owner_presence and GATE_RANK[gate] < GATE_RANK[Gate.OWNER_APPROVAL]:
        gate = Gate.OWNER_APPROVAL
    return ActionDescriptor(
        subject_id=declaration.capability_id,
        action_class=declaration.authority_class,
        gate=gate,
        reversibility=(
            Reversibility.READ_ONLY if not declaration.mutates
            else Reversibility.UNDECLARED
        ),
        egress=(
            EgressClass.EXTERNAL_DISCLOSING
            if declaration.privacy_class is PrivacyClass.EXTERNAL_DISCLOSING
            else EgressClass.OWNER_PRIVATE if declaration.mutates or declaration.requires_network
            else EgressClass.NONE
        ),
        verification=VERIFICATION_ALIASES[declaration.verification_strategy.value],
        derived_from="capability.registry",
    )


def canonical_verification(name: str | Any) -> str:
    """Translate any of the three spellings into the one the mission registry uses.

    Raises on an unknown name rather than passing it through: a strategy nothing can
    translate is a strategy nothing will verify, and silently forwarding it is how an
    unverifiable action comes to look verified.
    """
    key = name.value if isinstance(name, Enum) else str(name)
    try:
        return VERIFICATION_ALIASES[key]
    except KeyError as exc:
        raise ValueError(f"no canonical verification strategy for {key!r}") from exc


__all__ = [
    "ACTION_REVERSIBILITY",
    "GATE_RANK",
    "VERIFICATION_ALIASES",
    "ActionDescriptor",
    "EgressClass",
    "Gate",
    "Reversibility",
    "canonical_verification",
    "describe_action",
    "describe_capability",
    "gate_for",
]
