"""Assert Hermes VAN profile pack, authority content and Google mesh layout."""

from __future__ import annotations

from pathlib import Path
import json

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


def test_install_scripts_exist():
    assert (REPO_ROOT / "tools" / "hermes" / "install_van_profile.sh").is_file()
    assert (REPO_ROOT / "tools" / "hermes" / "doctor_van_profile.sh").is_file()
