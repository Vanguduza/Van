"""Assert Hermes van profile pack layout and SOUL authority content."""

from __future__ import annotations

from pathlib import Path

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
]

SKILL_NAMES = [
    "owner-briefing",
    "google-workspace",
    "project-steering",
    "research",
    "decision-support",
    "document-work",
    "notification-triage",
    "infrastructure-diagnostics",
    "hermes-administration",
]

# Authority order phrases from docs/PROJECT_TRUTH_PROTOCOL.md (descending)
AUTHORITY_ORDER_MARKERS = [
    "Owner-signed instruction",
    "Project Truth",
    "Explicit capability grants",
    "Deterministic system state",
    "Hermes curated profile memory",
    "Conversational history",
    "External/untrusted content",
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


def test_profile_name_in_config():
    config = (PROFILE_ROOT / "config.yaml").read_text(encoding="utf-8")
    assert "profile: van" in config


def test_soul_mentions_project_truth_authority_order():
    soul = (PROFILE_ROOT / "SOUL.md").read_text(encoding="utf-8")
    assert "Project Truth" in soul
    for marker in AUTHORITY_ORDER_MARKERS:
        assert marker in soul, f"SOUL.md missing authority marker: {marker}"
    # Owner-signed instruction must outrank Project Truth in document order
    owner_idx = soul.index("Owner-signed instruction")
    truth_idx = soul.index("Project Truth")
    assert owner_idx < truth_idx, "Authority order: owner-signed must precede Project Truth"


def test_install_scripts_exist():
    install = REPO_ROOT / "tools" / "hermes" / "install_van_profile.sh"
    doctor = REPO_ROOT / "tools" / "hermes" / "doctor_van_profile.sh"
    assert install.is_file(), "install_van_profile.sh missing"
    assert doctor.is_file(), "doctor_van_profile.sh missing"
