"""Rev 1 §7 — the canonical capability declaration.

The reconciliation problem this solves: the repository already had two things
called a capability registry. `automation_capabilities` knows the admission
lifecycle of a compiled n8n workflow; `GoogleCapabilityRegistry` knows which
Google capability binds to which identity and whether that principal is
connected. Adding a third store of the same facts would have produced three
answers to "can VAN do this right now" and no authority over any of them.

They are not rivals, because they answer a different question from this one.
They answer *readiness* — a live, per-principal, per-artifact fact that changes
without anyone editing a file. This registry answers *declaration* — what a
capability is, what contract it must meet, what verifies it, what it may fall
back to. That is static, reviewable, and belongs in git.

So the split is:

    declaration   -> registries/capabilities.json, sealed by digest (here)
    readiness     -> whichever subsystem already owns it (readiness_source)
    routability   -> a pure function of the two, plus policy

`readiness_source` is the load-bearing field. It makes this registry *point at*
the existing authorities instead of copying them, which is the whole reason it
can be canonical without being a third source of truth.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from van_gateway.models import ActionClass


class CapabilityClass(str, Enum):
    """§7 — the coverage the registry must span."""

    NATIVE_READ = "NATIVE_READ"
    KNOWLEDGE_RETRIEVAL = "KNOWLEDGE_RETRIEVAL"
    WEB_RESEARCH = "WEB_RESEARCH"
    BROWSER_INTERACTION = "BROWSER_INTERACTION"
    GOOGLE_WORKSPACE = "GOOGLE_WORKSPACE"
    NOTEBOOK = "NOTEBOOK"
    AUTOMATION = "AUTOMATION"
    DEVELOPER = "DEVELOPER"
    REPOSITORY = "REPOSITORY"
    COMPUTER_USE = "COMPUTER_USE"
    NOTIFICATION = "NOTIFICATION"
    TRADING_ANALYSIS = "TRADING_ANALYSIS"
    TRADING_EXECUTION = "TRADING_EXECUTION"


class ReadinessSource(str, Enum):
    """Which existing authority answers "is this ready right now".

    Every value except STATIC and NEVER_ROUTABLE delegates to a subsystem that
    was already authoritative before this registry existed.
    """

    STATIC = "STATIC"
    AUTOMATION_REGISTRY = "AUTOMATION_REGISTRY"
    GOOGLE_MESH = "GOOGLE_MESH"
    EXTERNAL_RUNTIME = "EXTERNAL_RUNTIME"
    NEVER_ROUTABLE = "NEVER_ROUTABLE"


class VerificationStrategy(str, Enum):
    """§34 — how a side effect proves it happened."""

    NONE = "NONE"
    API_READBACK = "API_READBACK"
    PROVIDER_RECEIPT = "PROVIDER_RECEIPT"
    SCREENSHOT = "SCREENSHOT"
    REPOSITORY_SHA = "REPOSITORY_SHA"
    CI_RUN = "CI_RUN"
    LEDGER_EVENT = "LEDGER_EVENT"


class Idempotency(str, Enum):
    IDEMPOTENT = "IDEMPOTENT"
    IDEMPOTENT_WITH_KEY = "IDEMPOTENT_WITH_KEY"
    NON_IDEMPOTENT = "NON_IDEMPOTENT"
    NEVER_RETRY = "NEVER_RETRY"


class LatencyClass(str, Enum):
    INTERACTIVE = "INTERACTIVE"
    SECONDS = "SECONDS"
    MINUTES = "MINUTES"
    LONG_RUNNING = "LONG_RUNNING"


class CostClass(str, Enum):
    FREE = "FREE"
    CHEAP = "CHEAP"
    METERED = "METERED"
    EXPENSIVE = "EXPENSIVE"


class PrivacyClass(str, Enum):
    """Whether using this capability discloses owner data outside VAN."""

    OWNER_PRIVATE = "OWNER_PRIVATE"
    EXTERNAL_DISCLOSING = "EXTERNAL_DISCLOSING"


#: Ranking used wherever "stronger class" must be compared deterministically.
CLASS_RANK = {
    ActionClass.A1: 1, ActionClass.A2: 2, ActionClass.A3: 3,
    ActionClass.A4: 4, ActionClass.A5: 5,
}


class CapabilityDeclaration(BaseModel):
    """One row of `registries/capabilities.json`, validated."""

    capability_id: str
    provider: str
    executor: str
    capability_class: CapabilityClass
    authority_class: ActionClass
    requires_network: bool = False
    requires_owner_presence: bool = False
    data_domains: list[str] = Field(default_factory=list)
    side_effects: list[str] = Field(default_factory=list)
    idempotency: Idempotency = Idempotency.IDEMPOTENT
    supports_checkpoint: bool = False
    supports_resume: bool = False
    verification_strategy: VerificationStrategy = VerificationStrategy.NONE
    latency_class: LatencyClass = LatencyClass.SECONDS
    cost_class: CostClass = CostClass.FREE
    privacy_class: PrivacyClass = PrivacyClass.OWNER_PRIVATE
    readiness_source: ReadinessSource = ReadinessSource.STATIC
    health_probe: str | None = None
    fallback_capabilities: list[str] = Field(default_factory=list)
    never_routable_reason: str | None = None
    #: Why this capability deliberately has no fallback, when that is a
    #: decision rather than an omission.
    no_fallback_reason: str | None = None

    @property
    def mutates(self) -> bool:
        return CLASS_RANK[self.authority_class] >= CLASS_RANK[ActionClass.A3]

    @property
    def requires_evidence(self) -> bool:
        """§34 — a side-effecting capability must be able to prove what it did.

        Read-only capabilities are exempt; anything that mutates is not, which is
        why a declaration that mutates with NONE is refused at load time.
        """
        return self.mutates or bool(self.side_effects) and self.side_effects != ["NETWORK_READ"]


class RoutabilityReason(str, Enum):
    """Why a capability may or may not be routed, as a closed set.

    A closed set rather than free text because §8 requires the routing decision
    to be persisted as evidence, and evidence you cannot group is evidence you
    cannot audit.
    """

    ROUTABLE = "ROUTABLE"
    NOT_DECLARED = "NOT_DECLARED"
    NEVER_ROUTABLE = "NEVER_ROUTABLE"
    NOT_READY = "NOT_READY"
    ABOVE_AUTHORITY_CEILING = "ABOVE_AUTHORITY_CEILING"
    OWNER_PRESENCE_REQUIRED = "OWNER_PRESENCE_REQUIRED"
    PRIVACY_NOT_PERMITTED = "PRIVACY_NOT_PERMITTED"
    CLASS_NOT_PERMITTED = "CLASS_NOT_PERMITTED"


class Routability(BaseModel):
    capability_id: str
    routable: bool
    reason: RoutabilityReason
    detail: str | None = None
    readiness_source: ReadinessSource | None = None

    @property
    def ok(self) -> bool:
        return self.routable


class RoutingConstraints(BaseModel):
    """What the caller is allowed to reach — normally a Mission's envelope.

    Policy is a hard filter (§8: "No model score may override policy"), so these
    are applied before any scoring happens rather than as a tie-break.
    """

    max_action_class: ActionClass = ActionClass.A2
    allowed_capability_classes: list[CapabilityClass] = Field(default_factory=list)
    owner_present: bool = False
    permit_external_disclosure: bool = True

    @classmethod
    def from_envelope(cls, envelope, *, owner_present: bool = False) -> RoutingConstraints:
        """Build from a Mission's AuthorityEnvelope without importing it here.

        Kept duck-typed so the capability package does not depend on the mission
        package; the dependency runs the other way, since a Mission binds work to
        capabilities rather than capabilities knowing about Missions.
        """
        classes = []
        for name in getattr(envelope, "allowed_capability_classes", []) or []:
            try:
                classes.append(CapabilityClass(name))
            except ValueError:
                continue
        return cls(
            max_action_class=getattr(envelope, "max_action_class", ActionClass.A2),
            allowed_capability_classes=classes,
            owner_present=owner_present,
        )


__all__ = [
    "CLASS_RANK",
    "CapabilityClass",
    "CapabilityDeclaration",
    "CostClass",
    "Idempotency",
    "LatencyClass",
    "PrivacyClass",
    "ReadinessSource",
    "Routability",
    "RoutabilityReason",
    "RoutingConstraints",
    "VerificationStrategy",
]
