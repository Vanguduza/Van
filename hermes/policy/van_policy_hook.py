"""
VAN Hermes policy hook — fail closed.

Deny A5, require approval for A4, protect audit/truth/security surfaces.

Hermes invokes: evaluate(action) -> PolicyDecision dict
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, MutableMapping, Optional

# Canonical action classes — see docs/SECURITY_POLICY.md
A1 = "A1"
A2 = "A2"
A3 = "A3"
A4 = "A4"
A5 = "A5"

VALID_CLASSES = frozenset({A1, A2, A3, A4, A5})

# Targets whose mutation without owner-signed authority is blocked
PROTECTED_SURFACES = frozenset(
    {
        "audit",
        "audit_log",
        "approvals",
        "approval_chain",
        "authority_checks",
        "security_hooks",
        "policy_hook",
        "project_truth",
        "truth_protocol",
        "host_role_guards",
    }
)

# Tool/action names or flags that imply disabling protections (always A5)
A5_PATTERNS = frozenset(
    {
        "disable_audit",
        "disable_approvals",
        "disable_authority_checks",
        "disable_security_hooks",
        "disable_policy_hook",
        "bypass_project_truth",
        "bypass_truth",
        "skip_truth_check",
        "ignore_project_truth",
        "disable_host_role_guards",
        "no_audit",
        "silent_success",
    }
)


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
        out: dict[str, Any] = {
            "decision": self.decision.value,
            "reason": self.reason,
        }
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
    if target in PROTECTED_SURFACES:
        return True
    resource = str(action.get("resource") or "").lower()
    for surface in PROTECTED_SURFACES:
        if surface in target or surface in resource:
            return True
    path = str(action.get("path") or "").lower()
    truth_markers = ("project_truth", "truth_protocol", "security_policy")
    if any(m in path for m in truth_markers):
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


def evaluate(action: Mapping[str, Any]) -> dict[str, Any]:
    """
    Evaluate a proposed action against VAN policy.

    Returns dict with keys: decision (allow|deny|approval_required), reason,
    and optionally action_class, code.
    """
    try:
        act = _normalize_action(action)
    except TypeError as exc:
        return PolicyResult(
            decision=Decision.DENY,
            reason=str(exc),
            code="invalid_action",
        ).to_dict()

    action_class = _infer_action_class(act)

    # Unknown action class on mutating tools → fail closed
    if action_class is None and act.get("mutating", act.get("writes", False)):
        return PolicyResult(
            decision=Decision.DENY,
            reason="Mutating action missing action_class; fail closed",
            code="missing_action_class",
        ).to_dict()

    if action_class is not None and action_class not in VALID_CLASSES:
        return PolicyResult(
            decision=Decision.DENY,
            reason=f"Invalid action_class: {action_class}",
            action_class=action_class,
            code="invalid_action_class",
        ).to_dict()

    pattern = _matches_a5_pattern(act)
    if pattern is not None:
        return PolicyResult(
            decision=Decision.DENY,
            reason=f"Prohibited A5 pattern detected: {pattern}",
            action_class=A5,
            code="a5_prohibited",
        ).to_dict()

    if action_class == A5:
        return PolicyResult(
            decision=Decision.DENY,
            reason="Action class A5 is prohibited",
            action_class=A5,
            code="a5_denied",
        ).to_dict()

    if _targets_protected_surface(act) and not act.get("owner_signed"):
        return PolicyResult(
            decision=Decision.DENY,
            reason="Protected audit/truth/security surface requires owner-signed authority",
            action_class=action_class or A5,
            code="protected_surface",
        ).to_dict()

    if action_class == A4:
        if act.get("owner_approval") or act.get("approval_granted"):
            return PolicyResult(
                decision=Decision.ALLOW,
                reason="A4 action with recorded owner approval",
                action_class=A4,
                code="a4_approved",
            ).to_dict()
        return PolicyResult(
            decision=Decision.APPROVAL_REQUIRED,
            reason="Destructive/irreversible/send-as-owner action requires explicit owner approval",
            action_class=A4,
            code="a4_approval_required",
        ).to_dict()

    # A1–A3 default allow at policy layer; gateway still enforces grants
    return PolicyResult(
        decision=Decision.ALLOW,
        reason="Policy check passed",
        action_class=action_class,
        code="allowed",
    ).to_dict()


def register_hook(registry: MutableMapping[str, Any]) -> None:
    """Optional Hermes registration helper."""
    registry["van"] = evaluate
