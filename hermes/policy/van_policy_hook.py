"""
VAN Hermes policy hook — fail closed.

Deny A5, require approval for A4, protect audit/truth/security and Google
identity/credential isolation surfaces, and preserve the Rev 3.1 boundary:
Hermes may interpret/plan, but the gateway owns typed action class and execution
authority.

Hermes invokes: evaluate(action) -> PolicyDecision dict
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, MutableMapping, Optional

A1 = "A1"
A2 = "A2"
A3 = "A3"
A4 = "A4"
A5 = "A5"
VALID_CLASSES = frozenset({A1, A2, A3, A4, A5})
EXACT_ACTION = "EXACT_ACTION"
HERMES_INTERPRETATION_REQUIRED = "HERMES_INTERPRETATION_REQUIRED"
VALID_RESOLUTION_MODES = frozenset({EXACT_ACTION, HERMES_INTERPRETATION_REQUIRED})

PROTECTED_SURFACES = frozenset({"audit","audit_log","approvals","approval_chain","authority_checks","security_hooks","policy_hook","project_truth","truth_protocol","host_role_guards","google_identity_broker","google_capability_registry","google_credential_planes"})

A5_PATTERNS = frozenset({"disable_audit","disable_approvals","disable_authority_checks","disable_security_hooks","disable_policy_hook","bypass_project_truth","bypass_truth","skip_truth_check","ignore_project_truth","disable_host_role_guards","no_audit","silent_success","bypass_google_broker","export_google_session","copy_google_session_cookie","copy_session_cookie","reuse_workspace_oauth_as_gemini","disable_google_credential_isolation"})


class Decision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    APPROVAL_REQUIRED = "approval_required"


@dataclass(frozen=True)
class PolicyResult:
    decision: Decision
    reason: str
    action_class: Optional[str] = None
    code: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"decision": self.decision.value, "reason": self.reason}
        if self.action_class is not None:
            out["action_class"] = self.action_class
        if self.code is not None:
            out["code"] = self.code
        return out


def _normalize_action(action: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(action, Mapping):
        raise TypeError("action must be a mapping")
    return dict(action)


def _infer_action_class(action: Mapping[str, Any]) -> Optional[str]:
    explicit = action.get("action_class") or action.get("class")
    if explicit is None:
        return None
    normalized = str(explicit).upper()
    if normalized.startswith("A") and len(normalized) == 2:
        return normalized
    return None


def _targets_protected_surface(action: Mapping[str, Any]) -> bool:
    target = str(action.get("target") or action.get("surface") or "").lower()
    resource = str(action.get("resource") or "").lower()
    if target in PROTECTED_SURFACES:
        return True
    for surface in PROTECTED_SURFACES:
        if surface in target or surface in resource:
            return True
    path = str(action.get("path") or "").lower()
    protected_markers = ("project_truth", "truth_protocol", "security_policy", "google_capabilities.json", "google_intelligence_mesh")
    if any(marker in path for marker in protected_markers):
        if action.get("operation") in ("write", "delete", "modify", "patch"):
            if not action.get("owner_signed") and not action.get("truth_authority_verified"):
                return True
    return False


def _matches_a5_pattern(action: Mapping[str, Any]) -> Optional[str]:
    name = str(action.get("name") or action.get("tool") or "").lower()
    for pattern in A5_PATTERNS:
        if pattern in name:
            return pattern
    flags = action.get("flags") or action.get("options") or {}
    if isinstance(flags, Mapping):
        for key, val in flags.items():
            key_l = str(key).lower()
            if key_l in A5_PATTERNS or (isinstance(val, bool) and val and key_l in A5_PATTERNS):
                return key_l
            if isinstance(val, str) and val.lower() in A5_PATTERNS:
                return val.lower()
    intent = str(action.get("intent") or "").lower()
    for pattern in A5_PATTERNS:
        if pattern in intent:
            return pattern
    return None


def _gateway_resolution_guard(action: Mapping[str, Any], action_class: Optional[str]) -> Optional[PolicyResult]:
    mode_raw = action.get("resolution_mode")
    if mode_raw is None:
        return None  # legacy/internal callers retain the established policy path
    mode = str(mode_raw)
    if mode not in VALID_RESOLUTION_MODES:
        return PolicyResult(Decision.DENY, "Unknown typed resolution mode", action_class=action_class, code="invalid_resolution_mode")

    gateway_authorized = bool(action.get("gateway_authorized"))
    mutating = bool(action.get("mutating", action.get("writes", False)))

    if mode == HERMES_INTERPRETATION_REQUIRED:
        if mutating and not gateway_authorized:
            return PolicyResult(
                Decision.DENY,
                "Ambiguous owner intent is proposal-only until gateway action authorization",
                action_class=action_class,
                code="proposal_only",
            )
        return None

    canonical_action_id = str(action.get("canonical_action_id") or "").strip()
    canonical_class = str(action.get("canonical_action_class") or "").upper().strip()
    if not canonical_action_id or canonical_class not in VALID_CLASSES:
        return PolicyResult(
            Decision.DENY,
            "Exact typed action is missing canonical gateway identity/class",
            action_class=action_class,
            code="missing_canonical_action",
        )
    if action_class is not None and action_class != canonical_class:
        return PolicyResult(
            Decision.DENY,
            "Hermes action class differs from gateway canonical class",
            action_class=action_class,
            code="canonical_class_mismatch",
        )
    proposed_action_id = str(action.get("action_id") or action.get("name") or "").strip()
    if proposed_action_id and proposed_action_id != canonical_action_id:
        return PolicyResult(
            Decision.DENY,
            "Hermes action identity differs from gateway canonical action",
            action_class=canonical_class,
            code="canonical_action_mismatch",
        )
    if mutating and not gateway_authorized:
        return PolicyResult(
            Decision.DENY,
            "Typed mutation requires gateway action-runtime authorization",
            action_class=canonical_class,
            code="gateway_authorization_required",
        )
    return None


def evaluate(action: Mapping[str, Any]) -> dict[str, Any]:
    try:
        act = _normalize_action(action)
    except TypeError as exc:
        return PolicyResult(Decision.DENY, str(exc), code="invalid_action").to_dict()
    action_class = _infer_action_class(act)
    if action_class is None and act.get("mutating", act.get("writes", False)):
        return PolicyResult(Decision.DENY, "Mutating action missing action_class; fail closed", code="missing_action_class").to_dict()
    if action_class is not None and action_class not in VALID_CLASSES:
        return PolicyResult(Decision.DENY, f"Invalid action_class: {action_class}", action_class=action_class, code="invalid_action_class").to_dict()
    pattern = _matches_a5_pattern(act)
    if pattern is not None:
        return PolicyResult(Decision.DENY, f"Prohibited A5 pattern detected: {pattern}", action_class=A5, code="a5_prohibited").to_dict()
    if action_class == A5:
        return PolicyResult(Decision.DENY, "Action class A5 is prohibited", action_class=A5, code="a5_denied").to_dict()

    resolution_denial = _gateway_resolution_guard(act, action_class)
    if resolution_denial is not None:
        return resolution_denial.to_dict()

    if _targets_protected_surface(act) and not act.get("owner_signed"):
        return PolicyResult(Decision.DENY, "Protected audit/truth/security/Google authority surface requires owner-signed authority", action_class=action_class or A5, code="protected_surface").to_dict()
    if action_class == A4:
        if act.get("owner_approval") or act.get("approval_granted"):
            return PolicyResult(Decision.ALLOW, "A4 action with recorded owner approval", action_class=A4, code="a4_approved").to_dict()
        return PolicyResult(Decision.APPROVAL_REQUIRED, "Destructive/irreversible/send-as-owner action requires explicit owner approval", action_class=A4, code="a4_approval_required").to_dict()
    return PolicyResult(Decision.ALLOW, "Policy check passed", action_class=action_class, code="allowed").to_dict()


def register_hook(registry: MutableMapping[str, Any]) -> None:
    registry["van"] = evaluate
