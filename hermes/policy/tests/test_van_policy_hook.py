"""Unit tests for van_policy_hook — deny A5, approval A4, protect truth/audit."""

from __future__ import annotations

import sys
from pathlib import Path

# Allow import from policy directory when run via pytest from repo root
POLICY_DIR = Path(__file__).resolve().parents[1]
if str(POLICY_DIR) not in sys.path:
    sys.path.insert(0, str(POLICY_DIR))

import van_policy_hook as hook  # noqa: E402


def test_a5_explicit_denied():
    result = hook.evaluate({"action_class": "A5", "name": "anything"})
    assert result["decision"] == "deny"
    assert result["code"] == "a5_denied"


def test_a5_pattern_disable_audit():
    result = hook.evaluate({"action_class": "A3", "name": "disable_audit"})
    assert result["decision"] == "deny"
    assert result["code"] == "a5_prohibited"


def test_a4_requires_approval():
    result = hook.evaluate(
        {"action_class": "A4", "name": "send_email_as_owner", "mutating": True}
    )
    assert result["decision"] == "approval_required"
    assert result["code"] == "a4_approval_required"


def test_a4_allowed_with_approval():
    result = hook.evaluate(
        {
            "action_class": "A4",
            "name": "send_email_as_owner",
            "owner_approval": True,
        }
    )
    assert result["decision"] == "allow"
    assert result["code"] == "a4_approved"


def test_protected_truth_mutation_denied_without_owner():
    result = hook.evaluate(
        {
            "action_class": "A3",
            "operation": "write",
            "path": "docs/PROJECT_TRUTH_PROTOCOL.md",
            "mutating": True,
        }
    )
    assert result["decision"] == "deny"
    assert result["code"] == "protected_surface"


def test_protected_truth_mutation_allowed_when_owner_signed():
    result = hook.evaluate(
        {
            "action_class": "A3",
            "operation": "write",
            "path": "docs/PROJECT_TRUTH_PROTOCOL.md",
            "owner_signed": True,
            "truth_authority_verified": True,
        }
    )
    assert result["decision"] == "allow"


def test_mutating_missing_action_class_fail_closed():
    result = hook.evaluate({"name": "write_file", "mutating": True})
    assert result["decision"] == "deny"
    assert result["code"] == "missing_action_class"


def test_a1_read_allowed():
    result = hook.evaluate({"action_class": "A1", "name": "read_local_state"})
    assert result["decision"] == "allow"


def test_register_hook():
    registry: dict = {}
    hook.register_hook(registry)
    assert registry["van"] is hook.evaluate
