"""Rev 1.3 §§365-369, 415, 419 — governance contract tests.

These guard the boundary the Rev 1.2 review found broken: an implementation
agent must not widen locked authority on its own initiative. They fail if a
future change silently edits `docs/SECURITY_POLICY.md`, promotes a stack-lock
layer without a recorded owner decision, or marks an external gate READY without
evidence.

`PROJECT_CANONICAL_STATE.json` sets `agent_self_authorization_forbidden: true`;
this file turns that policy into something CI can check.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DECISIONS = ROOT / "docs" / "decisions"
PREFLIGHT = ROOT / "docs" / "project-state" / "AUTOMATION_BROWSER_FABRIC_PREFLIGHT.md"
SECURITY_POLICY = ROOT / "docs" / "SECURITY_POLICY.md"
EXTERNAL_GATES = ROOT / "docs" / "EXTERNAL_GATES.md"
STACK_LOCK = ROOT / "trading" / "architecture" / "stack_lock.json"
PROPOSAL = ROOT / "trading" / "architecture" / "proposed" / "automation_browser_fabric_layers.json"
MANIFEST = ROOT / "registries" / "automation_browser_dependencies.json"

ADOPTION_DECISIONS = (
    "VAN-ADOPT-N8N-001.yaml",
    "VAN-ADOPT-STAGEHAND-001.yaml",
    "VAN-ADOPT-BROWSER-HARNESS-001.yaml",
)

#: Digest of `docs/SECURITY_POLICY.md` as this branch found it. The Automation &
#: Browser Fabric proposes amendments in `docs/decisions/`; it does not apply
#: them. If this assertion fails, either the owner accepted the amendment (and
#: this constant should be updated in the same commit that records the
#: approval), or an agent edited a locked authority on its own initiative.
SECURITY_POLICY_SHA256 = "cf303cb9aa1cc48432da77bc16cb33f400afcfc8d7f286a148be940cc2331eb5"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_all_adoption_decisions_exist_and_are_unsigned():
    """§365 — an implementation agent creates these; it never signs them."""
    for name in ADOPTION_DECISIONS:
        path = DECISIONS / name
        assert path.is_file(), f"missing adoption decision: {name}"
        text = path.read_text(encoding="utf-8")
        assert "owner_signature_status: PENDING" in text, name
        assert "owner_signed_at: null" in text, name


def test_security_policy_amendment_is_a_proposal_not_an_edit():
    """§§367-368 — the amendment package exists and the locked policy is untouched."""
    amendment = DECISIONS / "VAN-AMEND-SECURITY-POLICY-001.md"
    assert amendment.is_file()
    text = amendment.read_text(encoding="utf-8")
    assert "owner_signature_status: PENDING" in text
    assert "PENDING_OWNER" in text


def test_locked_security_policy_is_unmodified():
    """The locked authority named in PROJECT_CANONICAL_STATE.json stays byte-identical."""
    state = json.loads((ROOT / "PROJECT_CANONICAL_STATE.json").read_text(encoding="utf-8"))
    assert "docs/SECURITY_POLICY.md" in state["canonical_state"]["locked_authorities"]
    assert _sha256(SECURITY_POLICY) == SECURITY_POLICY_SHA256, (
        "docs/SECURITY_POLICY.md changed. Amendments belong in "
        "docs/decisions/VAN-AMEND-SECURITY-POLICY-001.md until the owner approves them."
    )


def test_stack_lock_is_not_mutated_before_owner_decision():
    """§366 — stack-lock mutation is blocked until the decision is recorded."""
    lock = json.loads(STACK_LOCK.read_text(encoding="utf-8"))
    admitted = {layer["layer"] for layer in lock["layers"]}
    proposed = {
        layer["layer"]
        for layer in json.loads(PROPOSAL.read_text(encoding="utf-8"))["layers"]
    }
    overlap = admitted & proposed
    assert not overlap, (
        f"layers {sorted(overlap)} were promoted into stack_lock.json while their adoption "
        "decision is still PENDING"
    )


def test_external_gates_record_automation_browser_rows_as_pending():
    """§369 — the gates exist and start truthful."""
    text = EXTERNAL_GATES.read_text(encoding="utf-8")
    assert "## Automation & Browser Fabric gates" in text
    for gate in (
        "n8n self-hosted runtime",
        "n8n workflow generation",
        "n8n security",
        "n8n backup/restore",
        "Automation webhook ingress",
        "Standing automation",
        "Stagehand local semantic browser",
        "Browser Harness",
        "Browser authenticated profile",
        "Browser prompt-injection containment",
        "Trading Core isolation",
        "Browser→automation optimization",
    ):
        assert gate in text, f"missing external gate row: {gate}"


def test_no_automation_gate_claims_ready():
    """§369 — no gate may become READY solely because code exists."""
    text = EXTERNAL_GATES.read_text(encoding="utf-8")
    section = text.split("## Automation & Browser Fabric gates", 1)[1]
    section = section.split("## Google certification rules", 1)[0]
    for line in section.splitlines():
        if not line.startswith("|") or "PENDING_LIVE" in line:
            continue
        assert "READY" not in line, f"automation gate claims READY without evidence: {line}"


def test_preflight_artifact_exists_and_records_base():
    """§420 — the agent must not silently resolve governance ambiguity."""
    assert PREFLIGHT.is_file()
    text = PREFLIGHT.read_text(encoding="utf-8")
    for required in (
        "Resolved implementation-base SHA",
        "Rev 3.1 interface existence",
        "Schema version before migration",
        "Blocked work in this branch",
    ):
        assert required in text, f"preflight missing section: {required}"


def test_dependency_manifest_pins_are_declared():
    """§419 — CI compares runtime evidence against this manifest."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))["automation_browser_fabric"]
    assert manifest["n8n"]["licence_class"] == "SOURCE_AVAILABLE"
    assert manifest["n8n"]["adoption_decision_ref"] == "docs/decisions/VAN-ADOPT-N8N-001.yaml"
    assert manifest["stagehand"]["licence_class"] == "PERMISSIVE"
    assert manifest["browser_harness"]["licence_class"] == "PERMISSIVE"
    for name, entry in manifest.items():
        assert entry.get("version"), f"{name} has no declared version"
        assert entry["version"] != "latest", f"{name} must not pin 'latest'"


def test_manifest_matches_deployment_env_pins():
    """The manifest and the deployment branch's env must not drift apart."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))["automation_browser_fabric"]
    env = (ROOT / "deploy" / "van-trading-core" / "automation" / "runtime.env.example").read_text(
        encoding="utf-8"
    )
    assert f"N8N_VERSION={manifest['n8n']['version']}" in env

    package = json.loads(
        (ROOT / "deploy" / "van-trading-core" / "browser" / "package.json").read_text(encoding="utf-8")
    )
    assert package["dependencies"]["@browserbasehq/stagehand"] == manifest["stagehand"]["version"]


def test_config_policy_files_are_present():
    """§346 — the policy surface the gateway reads must exist in the repo."""
    for relative in (
        "config/automation/policy.yaml",
        "config/automation/domains.yaml",
        "config/automation/node_allowlist.json",
        "config/automation/resource_policy.yaml",
        "config/automation/credentials.yaml.example",
        "config/browser/profiles.yaml",
        "config/browser/domains.yaml",
    ):
        assert (ROOT / relative).is_file(), f"missing policy file: {relative}"


def test_no_secret_material_in_repository_config():
    """§346 — secrets never appear in repository configuration."""
    suspicious = ("BEGIN PRIVATE KEY", "BEGIN RSA PRIVATE KEY", "xoxb-", "sk-live")
    for path in (ROOT / "config").rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for marker in suspicious:
            assert marker not in text, f"{path} appears to contain secret material"


def test_automation_feature_flags_default_off():
    """§368 — repository-side code ships fail-closed behind disabled gates."""
    import sys

    sys.path.insert(0, str(ROOT / "backend"))
    from van_gateway.config import Settings

    settings = Settings(_env_file=None)
    assert settings.automation_enabled is False
    assert settings.automation_ingress_enabled is False
    assert settings.automation_egress_enabled is False
    assert settings.browser_enabled is False
    assert settings.browser_semantic_max_tier == "L3"
    assert settings.automation_n8n_api_key == ""
    assert settings.automation_grant_signing_key == ""
