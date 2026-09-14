"""Unit tests for VAN policy hook."""

from __future__ import annotations

import sys
from pathlib import Path

POLICY_DIR = Path(__file__).resolve().parents[1]
if str(POLICY_DIR) not in sys.path:
    sys.path.insert(0, str(POLICY_DIR))

import van_policy_hook as hook  # noqa: E402


def test_a5_explicit_denied():
    result = hook.evaluate({"action_class": "A5", "name": "anything"})
    assert result["decision"] == "deny" and result["code"] == "a5_denied"


def test_a5_pattern_disable_audit():
    result = hook.evaluate({"action_class": "A3", "name": "disable_audit"})
    assert result["decision"] == "deny" and result["code"] == "a5_prohibited"


def test_google_session_export_is_a5():
    result = hook.evaluate({"action_class": "A3", "name": "export_google_session"})
    assert result["decision"] == "deny" and result["code"] == "a5_prohibited"


def test_workspace_oauth_cannot_be_reused_for_gemini():
    result = hook.evaluate({"action_class": "A3", "intent": "reuse_workspace_oauth_as_gemini"})
    assert result["decision"] == "deny" and result["code"] == "a5_prohibited"


def test_google_broker_is_protected():
    result = hook.evaluate({"action_class": "A3", "target": "google_identity_broker", "operation": "write", "mutating": True})
    assert result["decision"] == "deny" and result["code"] == "protected_surface"


def test_a4_requires_approval():
    assert hook.evaluate({"action_class": "A4", "name": "send_email_as_owner", "mutating": True})["decision"] == "approval_required"


def test_a4_allowed_with_approval():
    assert hook.evaluate({"action_class": "A4", "name": "send_email_as_owner", "owner_approval": True})["decision"] == "allow"


def test_protected_truth_mutation_denied_without_owner():
    result = hook.evaluate({"action_class": "A3", "operation": "write", "path": "docs/PROJECT_TRUTH_PROTOCOL.md", "mutating": True})
    assert result["decision"] == "deny" and result["code"] == "protected_surface"


def test_protected_truth_mutation_allowed_when_owner_signed():
    result = hook.evaluate({"action_class": "A3", "operation": "write", "path": "docs/PROJECT_TRUTH_PROTOCOL.md", "owner_signed": True, "truth_authority_verified": True})
    assert result["decision"] == "allow"


def test_mutating_missing_action_class_fail_closed():
    assert hook.evaluate({"name": "write_file", "mutating": True})["decision"] == "deny"


def test_a1_read_allowed():
    assert hook.evaluate({"action_class": "A1", "name": "read_local_state"})["decision"] == "allow"


def test_register_hook():
    registry: dict = {}
    hook.register_hook(registry)
    assert registry["van"] is hook.evaluate
