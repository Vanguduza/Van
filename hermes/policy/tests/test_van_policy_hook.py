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


# --- VATI trading prohibitions (Rev 2 §37–§39) -------------------------------

import pytest


@pytest.mark.parametrize(
    "name",
    [
        "bypass_risk_authority", "skip_risk_check", "direct_broker_order", "llm_broker_order",
        "remove_stop_loss", "widen_protective_stop", "martingale", "unlimited_grid",
        "revenge_risk_increase", "disable_kill_switch", "trade_unverified_account",
        "trade_stale_data", "silent_strategy_mutation", "unvalidated_research_to_live", "broker_token_in_prompt",
    ],
)
def test_trading_forbidden_behaviours_are_a5(name):
    result = hook.evaluate({"action_class": "A3", "name": name, "mutating": True})
    assert result["decision"] == "deny" and result["code"] == "a5_prohibited", result


def test_trading_forbidden_behaviour_is_a5_even_with_owner_approval():
    result = hook.evaluate({"action_class": "A4", "name": "remove_stop_loss", "owner_approval": True})
    assert result["decision"] == "deny" and result["code"] == "a5_prohibited"


@pytest.mark.parametrize("target", ["risk_authority", "trading_mandate", "kill_switch", "trading_ledger", "strategy_registry", "platform_risk_ceilings"])
def test_trading_authority_surfaces_require_owner_signature(target):
    result = hook.evaluate({"action_class": "A3", "target": target, "operation": "write", "mutating": True})
    assert result["decision"] == "deny" and result["code"] == "protected_surface"
    signed = hook.evaluate({"action_class": "A4", "target": target, "operation": "write", "mutating": True, "owner_signed": True, "owner_approval": True})
    assert signed["decision"] == "allow"


def test_kill_switch_reset_needs_owner_signature():
    result = hook.evaluate({"action_class": "A4", "name": "reset_kill_switch", "target": "kill_switch", "mutating": True})
    assert result["decision"] == "deny" and result["code"] == "protected_surface"


def test_mandate_file_write_is_protected_path():
    result = hook.evaluate({"action_class": "A3", "operation": "write", "path": "trading/mandates/mandate.fx_primary.json", "mutating": True})
    assert result["decision"] == "deny" and result["code"] == "protected_surface"


def test_risk_authority_code_write_requires_truth_verified_owner_signature():
    result = hook.evaluate({"action_class": "A3", "operation": "patch", "path": "trading/vati/risk/authority.py", "mutating": True})
    assert result["decision"] == "deny"
    ok = hook.evaluate({"action_class": "A3", "operation": "patch", "path": "trading/vati/risk/authority.py", "mutating": True, "owner_signed": True, "truth_authority_verified": True})
    assert ok["decision"] == "allow"


def test_ordinary_trade_intent_submission_is_allowed_under_mandate():
    result = hook.evaluate({"action_class": "A3", "name": "submit_trade_intent", "target": "opportunity_engine", "mutating": True})
    assert result["decision"] == "allow"
