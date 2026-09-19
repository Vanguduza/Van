"""P1-SEC-004: which trading actions need owner approval, agreed across the wire.

Trading account and credential changes were guarded by a BiometricPrompt with no
CryptoObject — a prompt whose only output was that it had succeeded, which the gateway
never saw and which nothing bound to the action. The strong, challenge-signing path
already existed for A4 owner commands; the surface that issues broker signing keys was on
the weak one.

The gateway now refuses those actions without a verified proof, so the device cannot be
the only thing enforcing this. But the device holds a copy of the list so it does not send
a request it knows will be refused, and two copies of a security rule drift. This test
parses the Kotlin and compares.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from van_gateway.trading.accounts import ACTIONS, READ_ONLY_ACTIONS, requires_owner_approval

ROOT = Path(__file__).resolve().parents[2]
KOTLIN = ROOT / "android/app/src/main/java/com/dial/van/trading/AccountOnboarding.kt"
GATE = ROOT / "android/app/src/main/java/com/dial/van/security/BiometricGate.kt"


@pytest.fixture(scope="module")
def kotlin() -> str:
    assert KOTLIN.is_file()
    return KOTLIN.read_text(encoding="utf-8")


def test_the_read_only_sets_agree(kotlin):
    block = re.search(r"val READ_ONLY_ACTIONS = setOf\((.*?)\)", kotlin, re.S)
    assert block, "the device has no read-only action list"
    assert set(re.findall(r'"([a-z0-9_]+)"', block.group(1))) == set(READ_ONLY_ACTIONS)


def test_the_action_lists_agree(kotlin):
    block = re.search(r"val ACTIONS = (?:setOf|listOf)\((.*?)\)", kotlin, re.S)
    assert block, "the device has no action list"
    assert set(re.findall(r'"([a-z0-9_]+)"', block.group(1))) == set(ACTIONS)


def test_a_new_action_is_guarded_by_default():
    """Stated as the read-only complement, so forgetting fails closed."""
    assert requires_owner_approval("some_action_added_next_year") is False, (
        "an unknown action is not a known action"
    )
    for action in ACTIONS:
        assert requires_owner_approval(action) is (action not in READ_ONLY_ACTIONS)


def test_the_credential_bearing_actions_are_all_guarded():
    """The ones that store or hand back a secret. Naming them keeps the list honest."""
    for action in ("account_credentials", "mt5_ea_issue_key", "deriv_create_demo",
                   "deriv_oauth_link", "ctrader_link", "account_upsert", "account_remove"):
        assert requires_owner_approval(action), action


def test_the_read_only_actions_really_are_read_only():
    """A read that got into this set would be an approval quietly removed."""
    assert READ_ONLY_ACTIONS == {"account_verify", "oauth_pending", "ctrader_discover"}


def test_the_weak_biometric_path_is_gone():
    """A prompt returning a boolean produces nothing the gateway can check."""
    source = GATE.read_text(encoding="utf-8")
    assert "fun requestA4Approval(" not in source, (
        "the weak prompt is back; there is no correct caller for it"
    )
    assert "fun requestA4CommandApproval(" in source
    assert "CryptoObject" in source


def test_nothing_in_the_app_calls_the_weak_path():
    hits = [
        p for p in (ROOT / "android/app/src/main/java").rglob("*.kt")
        if "requestA4Approval(" in p.read_text(encoding="utf-8")
    ]
    assert not hits, f"still calling the deleted weak path: {[str(p) for p in hits]}"


def test_the_device_sends_a_proof_for_a_guarded_action(kotlin):
    assert "requiresOwnerApproval" in kotlin
    screen = (
        ROOT / "android/app/src/main/java/com/dial/van/trading/ui/AccountOnboardingScreen.kt"
    ).read_text(encoding="utf-8")
    assert "tradingAccountChallenge" in screen
    assert "requestA4CommandApproval" in screen
    assert "approval_challenge" in screen
