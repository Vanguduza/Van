"""Rev 1.3 §§67, 182-185, 378-379, 387, 407, 416 — browser policy enforcement.

Three boundaries are enforced here, each of which the Rev 1.2 review flagged:

* **the autonomy ladder cap** — production stops at L3 (observe → deterministic
  action). L4/L5 put action selection inside the worker, which conflicts with the
  locked *Hermes execution boundary* until the owner amends it;
* **secret containment** — browser session material is referenced by alias and
  may never appear in evidence, prompts, logs or workflow artifacts (§367.3);
* **no authority escalation from page content** — an observation is untrusted
  external data and can never raise a task's action class (§378).
"""

from __future__ import annotations

import json
import re
from typing import Any

from van_gateway.automation.policy import BrowserPolicy, PolicyError, load_browser_policy
from van_gateway.browser.models import (
    TIER_BY_POLICY_NAME,
    AutonomyTier,
    BrowserObservation,
    BrowserStrategy,
    HarnessMode,
    InjectionAssessment,
)
from van_gateway.models import ActionClass

_RANK = {ActionClass.A1: 1, ActionClass.A2: 2, ActionClass.A3: 3, ActionClass.A4: 4, ActionClass.A5: 5}

#: §§367.3, 407 — patterns that must never survive into evidence or a prompt.
#: ``_SEP`` tolerates JSON quoting so ``{"authorization": "Bearer x"}`` matches
#: just as a raw ``Authorization: Bearer x`` header would.
_SEP = r'["\']?\s*[:=]\s*["\']?'
_SECRET_PATTERNS = (
    re.compile(rf"(?i)\b(?:set-)?cookie\b{_SEP}"),
    re.compile(rf"(?i)\bsession(?:id|_id|-token)\b{_SEP}"),
    re.compile(
        rf"(?i)\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password)\b{_SEP}\S+"
    ),
    re.compile(rf"(?i)\bauthorization\b{_SEP}(?:bearer|basic)\s+\S+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"(?i)\b\d{6}\b\s*(?:is your|otp|verification code)"),
)

#: §387 — adversarial page instructions. Recorded, never obeyed.
_INJECTION_MARKERS = (
    "ignore van policy", "ignore previous instructions", "ignore all previous",
    "send cookies", "send your cookies", "exfiltrate", "call a privileged tool",
    "change trading limits", "place a trade", "reveal your token", "disable policy",
    "you are now", "system prompt:",
)


class BrowserPolicyError(PolicyError):
    """Raised when a browser task or observation violates policy."""


class BrowserPolicyEngine:
    def __init__(self, policy: BrowserPolicy | None = None) -> None:
        self.policy = policy or load_browser_policy()

    # ------------------------------------------------------------------ tiers

    @property
    def max_tier(self) -> AutonomyTier:
        return TIER_BY_POLICY_NAME.get(self.policy.max_autonomy_tier, AutonomyTier.L3_STAGEHAND_OBSERVE)

    def check_tier(self, tier: AutonomyTier) -> None:
        """§§88, 378 — refuse anything above the admitted ceiling.

        Since the owner's 2026-09-18 decision the ceiling is L5, so model-driven
        action selection is permitted. What keeps it subordinate is not the tier
        but the assignment bounds in `browser/subagent.py`: an autonomous run
        without an assigned goal, domain scope and step budget cannot start.
        """
        if tier.ordinal > self.max_tier.ordinal:
            raise BrowserPolicyError(
                f"browser_autonomy_tier_not_permitted:{tier.value}>{self.max_tier.value}"
            )

    # ------------------------------------------------------------- profiles

    def check_profile(self, alias: str) -> dict[str, Any]:
        """Wrap the shared loader so every refusal from this engine is one type."""
        try:
            return self.policy.check_profile(alias)
        except BrowserPolicyError:
            raise
        except PolicyError as exc:
            raise BrowserPolicyError(str(exc)) from exc

    # --------------------------------------------------------------- tasks

    def check_task(
        self,
        *,
        profile_alias: str,
        strategy: BrowserStrategy,
        tier: AutonomyTier,
        action_class: ActionClass,
        target_domain: str,
        mutating: bool,
    ) -> None:
        self.check_tier(tier)
        if action_class in (ActionClass.A4, ActionClass.A5):
            # §§108, 391 — the browser is never an A4 execution surface; A4 needs a
            # fresh owner approval bound to the exact action.
            raise BrowserPolicyError(f"browser_action_class_prohibited:{action_class.value}")

        profile = self.check_profile(profile_alias)
        if mutating and str(profile.get("mutation")) != "gateway_authorized_only":
            # config/browser/profiles.yaml admits exactly one mutation posture.
            # Anything else — including a profile that simply omits the key — is
            # treated as forbidden rather than as permission by default.
            raise BrowserPolicyError(f"browser_profile_mutation_forbidden:{profile_alias}")

        if not target_domain:
            raise BrowserPolicyError("browser_target_domain_missing")
        if mutating and target_domain not in self.policy.admitted_domains:
            # config/browser/domains.yaml: mutate is deny_until_explicitly_admitted.
            raise BrowserPolicyError(f"browser_mutation_domain_not_admitted:{target_domain}")
        if strategy is BrowserStrategy.STAGEHAND and tier.ordinal < 2:
            raise BrowserPolicyError("stagehand_requires_semantic_tier")

    # ----------------------------------------------------------- harness mode

    @staticmethod
    def check_harness_mode(mode: HarnessMode, *, writing_helpers: bool) -> None:
        """§§381, 416 — production may not author or import helpers at runtime."""
        if mode is HarnessMode.PRODUCTION_ACTUATOR and writing_helpers:
            raise BrowserPolicyError("production_harness_helper_authoring_forbidden")

    # ------------------------------------------------------------ containment

    @staticmethod
    def scan_for_secrets(payload: Any) -> list[str]:
        """Return the patterns that matched. Empty means safe to persist."""
        blob = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, default=str)
        return [pattern.pattern for pattern in _SECRET_PATTERNS if pattern.search(blob)]

    @classmethod
    def assert_no_secrets(cls, payload: Any, *, context: str) -> None:
        """§367.3 — refuse rather than redact, so a leak is a loud failure."""
        hits = cls.scan_for_secrets(payload)
        if hits:
            raise BrowserPolicyError(f"browser_secret_material_in_{context}")

    @staticmethod
    def assess_injection(payload: Any) -> InjectionAssessment:
        """§387 — record what the page tried; never act on it."""
        blob = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, default=str)
        lowered = blob.lower()
        if any(marker in lowered for marker in _INJECTION_MARKERS):
            return InjectionAssessment.SUSPECTED_INJECTION
        return InjectionAssessment.NONE_DETECTED

    # ------------------------------------------------------------ observation

    def sanitize_observation(
        self, observation: BrowserObservation, *, task_action_class: ActionClass
    ) -> BrowserObservation:
        """§378 — semantic output cannot raise the action class or carry secrets.

        A page that asks for a stronger action gets its request recorded and
        clamped, not honoured: page content is data, never authority.
        """
        self.assert_no_secrets(observation.controls, context="observation_controls")
        self.assert_no_secrets(observation.extraction, context="observation_extraction")

        assessment = observation.injection_assessment
        if assessment is InjectionAssessment.NONE_DETECTED:
            assessment = self.assess_injection(
                {"controls": observation.controls, "extraction": observation.extraction}
            )

        proposed = observation.proposed_action_class
        if proposed is not None and _RANK[proposed] > _RANK[task_action_class]:
            proposed = task_action_class

        return observation.model_copy(
            update={"injection_assessment": assessment, "proposed_action_class": proposed}
        )


__all__ = ["BrowserPolicyEngine", "BrowserPolicyError"]
