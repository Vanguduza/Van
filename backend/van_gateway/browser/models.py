"""Rev 1.3 §§181-189, 380-387 — Browser Fabric contracts.

Two dependencies sit behind one gateway: Browser Harness (deterministic local CDP
actuator) and Stagehand (semantic browser). Rev 1.3 §380 finally names Browser
Harness — ``browser-use/browser-harness``, MIT, T2 — which closes the Rev 1.2
review's blocking finding B5.

The determinism ladder (§88) is modelled explicitly because where a task sits on
it decides how much model involvement is permitted, and production is capped at
L3 until the owner amends the Hermes execution boundary.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from van_gateway.models import ActionClass


class AutonomyTier(str, Enum):
    """§88 — the Stagehand determinism ladder.

    L0-L3 keep action selection deterministic. L4/L5 place it inside the worker,
    which is why they are gated: `docs/SECURITY_POLICY.md` says Hermes is the sole
    agent runtime.
    """

    L0_API = "L0_API"
    L1_HARNESS_DETERMINISTIC = "L1_HARNESS_DETERMINISTIC"
    L2_STAGEHAND_CACHED = "L2_STAGEHAND_CACHED"
    L3_STAGEHAND_OBSERVE = "L3_STAGEHAND_OBSERVE"
    L4_STAGEHAND_ACT = "L4_STAGEHAND_ACT"
    L5_STAGEHAND_AGENT = "L5_STAGEHAND_AGENT"

    @property
    def ordinal(self) -> int:
        return _TIER_ORDER[self]

    @property
    def model_selects_actions(self) -> bool:
        return self.ordinal >= 4


_TIER_ORDER: dict["AutonomyTier", int] = {
    AutonomyTier.L0_API: 0,
    AutonomyTier.L1_HARNESS_DETERMINISTIC: 1,
    AutonomyTier.L2_STAGEHAND_CACHED: 2,
    AutonomyTier.L3_STAGEHAND_OBSERVE: 3,
    AutonomyTier.L4_STAGEHAND_ACT: 4,
    AutonomyTier.L5_STAGEHAND_AGENT: 5,
}

#: Maps the ``VAN_BROWSER_SEMANTIC_MAX_TIER`` policy string onto the ladder.
TIER_BY_POLICY_NAME = {
    "L0": AutonomyTier.L0_API,
    "L1": AutonomyTier.L1_HARNESS_DETERMINISTIC,
    "L2": AutonomyTier.L2_STAGEHAND_CACHED,
    "L3": AutonomyTier.L3_STAGEHAND_OBSERVE,
    "L4": AutonomyTier.L4_STAGEHAND_ACT,
    "L5": AutonomyTier.L5_STAGEHAND_AGENT,
}


class BrowserStrategy(str, Enum):
    DIRECT_HTTP = "DIRECT_HTTP"
    HARNESS = "HARNESS"
    STAGEHAND = "STAGEHAND"


class BrowserTaskStatus(str, Enum):
    PENDING = "PENDING"
    LEASED = "LEASED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    DENIED = "DENIED"
    CANCELLED = "CANCELLED"


class HarnessMode(str, Enum):
    """§381 — upstream can author helpers; production must not."""

    PRODUCTION_ACTUATOR = "PRODUCTION_ACTUATOR"
    DISCOVERY_QUARANTINE = "DISCOVERY_QUARANTINE"


class BrowserTask(BaseModel):
    """§181. ``value_ref`` inputs only — never a literal secret (§§367.3, 407)."""

    task_id: str
    command_id: str | None = None
    execution_id: str | None = None
    capability_id: str | None = None

    profile_alias: str
    strategy: BrowserStrategy
    autonomy_tier: AutonomyTier
    action_class: ActionClass
    target_domain: str
    goal: str

    inputs: dict[str, Any] = Field(default_factory=dict)
    status: BrowserTaskStatus = BrowserTaskStatus.PENDING
    evidence_pointer: str | None = None
    error_code: str | None = None

    started_at_ms: int
    completed_at_ms: int | None = None


class PageLease(BaseModel):
    """§183 — one holder at a time, time-bounded, so tasks cannot collide on a profile."""

    lease_id: str
    profile_alias: str
    task_id: str
    acquired_at_ms: int
    expires_at_ms: int

    def active(self, now_ms: int) -> bool:
        return now_ms < self.expires_at_ms


class InjectionAssessment(str, Enum):
    NONE_DETECTED = "NONE_DETECTED"
    SUSPECTED_INJECTION = "SUSPECTED_INJECTION"
    CONFIRMED_INJECTION = "CONFIRMED_INJECTION"


class BrowserEvidence(BaseModel):
    """§§184-185. Digests, never raw page secrets.

    ``contains_secrets`` must be False for evidence to be storable at all: §367.3
    forbids cookies, storage secrets or CDP bearer material from reaching evidence.
    """

    evidence_id: str
    task_id: str
    kind: str
    url_digest: str
    dom_digest: str | None = None
    screenshot_digest: str | None = None
    extraction_digest: str | None = None
    source_trust: str = "UNTRUSTED_EXTERNAL"
    injection_assessment: InjectionAssessment = InjectionAssessment.NONE_DETECTED
    contains_secrets: bool = False
    created_at_ms: int
    detail: dict[str, Any] = Field(default_factory=dict)


class BrowserObservation(BaseModel):
    """What a Stagehand observe/extract returns. Always untrusted external data."""

    task_id: str
    controls: list[dict[str, Any]] = Field(default_factory=list)
    extraction: dict[str, Any] = Field(default_factory=dict)
    injection_assessment: InjectionAssessment = InjectionAssessment.NONE_DETECTED
    #: §378 — semantic output can never raise the action class of a task.
    proposed_action_class: ActionClass | None = None


class BrowserWorkflowCapsule(BaseModel):
    """§§279-280 — a discovered browser process, admitted like any other capability."""

    capsule_id: str
    domain: str
    goal_class: str
    steps: list[dict[str, Any]] = Field(default_factory=list)
    autonomy_tier: AutonomyTier
    action_class: ActionClass
    admission_state: str = "PROPOSED"
    #: §§89-90 — set when a stable machine interface was discovered, so the
    #: capsule can migrate up the ladder to an n8n/API workflow.
    discovered_api_shadow: dict[str, Any] | None = None


__all__ = [
    "AutonomyTier",
    "BrowserEvidence",
    "BrowserObservation",
    "BrowserStrategy",
    "BrowserTask",
    "BrowserTaskStatus",
    "BrowserWorkflowCapsule",
    "HarnessMode",
    "InjectionAssessment",
    "PageLease",
    "TIER_BY_POLICY_NAME",
]
