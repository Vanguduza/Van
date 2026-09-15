"""Assert Hermes VAN profile pack, authority content and Google mesh layout."""

from __future__ import annotations

from pathlib import Path
import json
import os
import subprocess

REPO_ROOT = Path(__file__).resolve().parents[2]
HERMES_ROOT = REPO_ROOT / "hermes"
PROFILE_ROOT = HERMES_ROOT / "profile" / "van"

REQUIRED_FILES = [
    HERMES_ROOT / "VERSION",
    PROFILE_ROOT / "SOUL.md",
    PROFILE_ROOT / "AGENTS.md",
    PROFILE_ROOT / "config.yaml",
    HERMES_ROOT / "policy" / "van_policy_hook.py",
    HERMES_ROOT / "policy" / "tests" / "test_van_policy_hook.py",
    HERMES_ROOT / "mcp" / "README.md",
    HERMES_ROOT / "bot" / "BOT_CHAT.md",
    HERMES_ROOT / "bot" / "message_agent.md",
    HERMES_ROOT / "bot" / "councils.md",
    HERMES_ROOT / "providers" / "gemini.md",
    REPO_ROOT / "registries" / "google_capabilities.json",
    REPO_ROOT / "docs" / "GOOGLE_INTELLIGENCE_MESH.md",
]

SKILL_NAMES = [
    "owner-briefing", "google-workspace", "google-intelligence", "gemini-notebook",
    "google-design", "google-development", "project-steering", "research",
    "decision-support", "document-work", "notification-triage",
    "infrastructure-diagnostics", "hermes-administration",
]

AUTHORITY_ORDER_MARKERS = [
    "Owner-signed instruction", "Project Truth", "Explicit capability grants",
    "Deterministic system state", "Hermes curated profile memory",
    "Conversational history", "External/untrusted content",
]


def test_required_files_exist():
    missing = [str(p.relative_to(REPO_ROOT)) for p in REQUIRED_FILES if not p.is_file()]
    assert not missing, f"Missing required Hermes pack files: {missing}"


def test_skills_exist():
    missing = []
    for name in SKILL_NAMES:
        skill_md = HERMES_ROOT / "skills" / name / "SKILL.md"
        if not skill_md.is_file():
            missing.append(str(skill_md.relative_to(REPO_ROOT)))
    assert not missing, f"Missing skills: {missing}"


def test_profile_name_and_sole_runtime_in_config():
    config = (PROFILE_ROOT / "config.yaml").read_text(encoding="utf-8")
    assert "profile: van" in config
    assert "runtime: hermes" in config
    assert "secondary_agent_allowed: false" in config


def test_van_primary_model_is_claude_sonnet_5():
    config = (PROFILE_ROOT / "config.yaml").read_text(encoding="utf-8")
    assert "model:" in config
    assert "provider: anthropic" in config
    assert "default: claude-sonnet-5" in config


def test_google_runtime_is_gemini_and_owner_account_rooted():
    config = (PROFILE_ROOT / "config.yaml").read_text(encoding="utf-8")
    assert "google_runtime:" in config
    assert "provider: gemini" in config
    assert "identity_root: owner_google_account" in config
    assert "account_owned_runtime_required: true" in config
    assert "prefer_gemini_for_google_ai: true" in config
    assert "primary_hermes_model_override_allowed: false" in config
    assert "workspace_oauth_reuse_for_gemini: false" in config


def test_soul_mentions_project_truth_authority_order():
    soul = (PROFILE_ROOT / "SOUL.md").read_text(encoding="utf-8")
    for marker in AUTHORITY_ORDER_MARKERS:
        assert marker in soul, f"SOUL.md missing authority marker: {marker}"
    assert soul.index("Owner-signed instruction") < soul.index("Project Truth")


def test_google_account_sovereignty_and_credential_isolation_declared():
    soul = (PROFILE_ROOT / "SOUL.md").read_text(encoding="utf-8")
    assert "Google Account Sovereignty" in soul
    assert "Workspace OAuth" in soul
    assert "Gemini runtime" in soul
    assert "Cloud/service" in soul
    assert "consumer Google sessions" in soul
    assert "sole agent runtime" in soul


def test_google_capability_registry_is_versioned_and_hermes_owned():
    registry = json.loads((REPO_ROOT / "registries" / "google_capabilities.json").read_text(encoding="utf-8"))
    assert registry["version"]
    ids = [item["id"] for item in registry["capabilities"]]
    for required in ("gemini", "gemini_live", "deep_research", "gemini_notebook", "mixboard", "stitch", "antigravity", "jules", "workspace_api", "nano_banana", "veo"):
        assert required in ids


def test_antigravity_uses_isolated_delegated_google_identity():
    registry = json.loads((REPO_ROOT / "registries" / "google_capabilities.json").read_text(encoding="utf-8"))
    policy = registry["identity_policy"]
    assert policy["canonical_identity"] == "owner_google_account"
    delegated = policy["delegated_identities"]["antigravity_worker_account"]
    assert delegated["allowed_capabilities"] == ["antigravity"]
    assert delegated["owner_authority"] is False
    assert delegated["workspace_access"] is False
    by_id = {item["id"]: item for item in registry["capabilities"]}
    assert by_id["antigravity"]["identity_alias"] == "antigravity_worker_account"
    assert all(item["identity_alias"] == "owner_google_account" for cid, item in by_id.items() if cid != "antigravity")
    wrapper = PROFILE_ROOT / "bin" / "antigravity-worker"
    text = wrapper.read_text(encoding="utf-8")
    assert wrapper.is_file()
    assert "VAN_ANTIGRAVITY_HOME" in text
    assert "export HOME" in text


def test_antigravity_wrapper_uses_only_worker_home(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake = fake_bin / "antigravity"
    fake.write_text('#!/usr/bin/env bash\nprintf "%s" "$HOME"\n', encoding="utf-8")
    fake.chmod(0o755)
    worker_home = tmp_path / "worker-home"
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
    env["HOME"] = str(tmp_path / "canonical-home")
    env["VAN_ANTIGRAVITY_HOME"] = str(worker_home)
    wrapper = PROFILE_ROOT / "bin" / "antigravity-worker"
    result = subprocess.run([str(wrapper), "models"], check=True, text=True, capture_output=True, env=env)
    assert result.stdout == str(worker_home)
    assert worker_home.stat().st_mode & 0o777 == 0o700


def test_antigravity_wrapper_falls_back_to_host_local_bin(tmp_path):
    canonical_home = tmp_path / "canonical-home"
    local_bin = canonical_home / ".local" / "bin"
    local_bin.mkdir(parents=True)
    fake = local_bin / "antigravity"
    fake.write_text('#!/usr/bin/env bash\nprintf "%s" "$HOME"\n', encoding="utf-8")
    fake.chmod(0o755)
    worker_home = tmp_path / "worker-home"
    env = os.environ.copy()
    env["PATH"] = "/usr/bin:/bin"
    env["HOME"] = str(canonical_home)
    env["VAN_ANTIGRAVITY_HOME"] = str(worker_home)
    wrapper = PROFILE_ROOT / "bin" / "antigravity-worker"
    result = subprocess.run([str(wrapper), "--version"], check=True, text=True, capture_output=True, env=env)
    assert result.stdout == str(worker_home)



def test_install_scripts_exist():
    assert (REPO_ROOT / "tools" / "hermes" / "install_van_profile.sh").is_file()
    assert (REPO_ROOT / "tools" / "hermes" / "doctor_van_profile.sh").is_file()
