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

#: Digest of `docs/SECURITY_POLICY.md` after the owner-approved
#: VAN-AMEND-SECURITY-POLICY-001 amendment of 2026-09-18. If this assertion fails,
#: either the owner accepted a further amendment (and this constant should be
#: updated in the same commit that records the approval), or an agent edited a
#: locked authority on its own initiative.
SECURITY_POLICY_SHA256 = "bea251efba7e04ac4b813abe29aa44a2a7243c6830b54b252b1ed32e635206e8"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_all_adoption_decisions_record_an_owner_decision():
    """§365 — every decision must carry a signature status and, once signed, provenance.

    An agent may not invent the signature; when it is SIGNED there must be a
    recorded owner decision saying who decided and on what basis.
    """
    for name in ADOPTION_DECISIONS:
        path = DECISIONS / name
        assert path.is_file(), f"missing adoption decision: {name}"
        text = path.read_text(encoding="utf-8")
        assert "owner_signature_status: SIGNED" in text, name
        assert "owner_decision_record:" in text, f"{name} is SIGNED without provenance"
        assert "provenance:" in text, name
        assert "owner_signature_evidence_ref: evidence://" in text, name


def test_payment_prohibition_is_recorded_in_the_n8n_decision():
    """The owner's 2026-09-18 constraint: passwords yes, payments never."""
    text = (DECISIONS / "VAN-ADOPT-N8N-001.yaml").read_text(encoding="utf-8")
    assert "prohibited_absolutely:" in text
    assert "payment execution by any automation" in text
    assert "standing_authority: PROHIBITED" in text


def test_browser_subagent_decision_is_recorded():
    """The owner's 2026-09-18 constraint: autonomous, but managed by Hermes."""
    text = (DECISIONS / "VAN-ADOPT-STAGEHAND-001.yaml").read_text(encoding="utf-8")
    assert "HERMES_MANAGED_SUBAGENT" in text
    assert "production_default_max_tier: L5" in text
    assert "subagent_invariants:" in text


#: sha256 of VAN-ADOPT-STAGEHAND-001.yaml as the owner's 2026-09-18 decision left it. Later
#: reconciliations are appended after the marker below; the approved text above it is frozen.
STAGEHAND_2026_09_18_SHA256 = "0553d1bdc5b2285218c7f1667808a6ee0d6fc7fede1fb538d03d353b99b6e9d6"
STAGEHAND_APPEND_MARKER = (
    "\n# ====================================================================================="
    "\n# APPENDED 2026-09-29"
)


def test_stagehand_reconciliation_is_append_only_and_keeps_production_pending():
    """Programme B: the 2026-09-18 approval is preserved; production stays PENDING.

    The approval authorises the architecture. It is not signed-ingress evidence and does not
    choose a host, so the appended production gate must stay PENDING until the owner resolves
    the open questions, and the Jev lane must precede Stagehand in the B5 order.
    """
    import yaml

    text = (DECISIONS / "VAN-ADOPT-STAGEHAND-001.yaml").read_text(encoding="utf-8")
    assert STAGEHAND_APPEND_MARKER in text
    approved = text.split(STAGEHAND_APPEND_MARKER, 1)[0]
    assert hashlib.sha256(approved.encode("utf-8")).hexdigest() == STAGEHAND_2026_09_18_SHA256, (
        "the owner's 2026-09-18 Stagehand decision text was edited; append instead"
    )

    rec = yaml.safe_load(text)["reconciliation_20260929"]
    assert rec["owner_approval_2026_09_18"]["preserved_unchanged"] is True
    assert rec["owner_approval_2026_09_18"]["evidence_absent"], "absent evidence must be stated"
    assert rec["production_gate"]["status"] == "PENDING"
    order = rec["programme_b_router_position"]["order"]
    assert [i for i, lane in enumerate(order) if "PROPOSE_ACTION" in lane] == [1]
    assert "Stagehand" in order[2] and "owner takeover" in order[3]
    ids = {q["id"] for q in rec["owner_decisions_required"]}
    assert {"OQ-STAGEHAND-HOST", "OQ-STAGEHAND-SIGNED-INGRESS", "OQ-VAN-PRIVATE-PLANE-HOST"} <= ids
    for q in rec["owner_decisions_required"]:
        assert "decision" not in q, "open questions must not carry a decision"


#: sha256 of VAN-ADOPT-STAGEHAND-001.yaml through the end of reconciliation_20260929 (H's
#: append, commit 379d6ab). The owner decisions of 2026-09-29 are appended after the marker
#: below; nothing above it may change.
STAGEHAND_RECONCILED_SHA256 = "e667a5b3b3bac824d51bca238e8a3c833c9e7e1f60dadbaa8130863fcdf51152"
STAGEHAND_OWNER_DECISIONS_MARKER = (
    "\n\n# ====================================================================================="
    "\n# APPENDED 2026-09-29 (second append)"
)
OWNER_DECISIONS_20260929 = DECISIONS / "OWNER-DECISIONS-20260929-STAGEHAND-PRIVATE-PLANE.md"
OWNER_DECISIONS_20260929_SHA256 = "64f1c0560ef88776d0d199392d315767ea3576827e335ba2da8081d12e307c81"
STAGEHAND_LOCK = ROOT / "deploy" / "van-trading-core" / "browser" / "package-lock.json"


def test_stagehand_owner_decisions_20260929_are_appended_truthfully():
    """Owner decisions 2026-09-29 §§1-8: recorded append-only, with nothing overstated.

    Intent is approved but signed ingress is still pending (not waived); the host is
    van-browser-core and Stagehand is PRODUCTION_DISABLED while it is unprovisioned; the
    model pin is not claimed; 4.1.0 is the release commit, not upstream HEAD; the router
    findings are blockers; the five open questions are closed by reference, not by editing.
    """
    import yaml

    assert hashlib.sha256(OWNER_DECISIONS_20260929.read_bytes()).hexdigest() == (
        OWNER_DECISIONS_20260929_SHA256
    ), "the committed owner decision text must stay verbatim"

    text = (DECISIONS / "VAN-ADOPT-STAGEHAND-001.yaml").read_text(encoding="utf-8")
    assert STAGEHAND_OWNER_DECISIONS_MARKER in text
    prior = text.split(STAGEHAND_OWNER_DECISIONS_MARKER, 1)[0] + "\n"
    assert hashlib.sha256(prior.encode("utf-8")).hexdigest() == STAGEHAND_RECONCILED_SHA256, (
        "text above the 2026-09-29 owner-decisions append was edited; append instead"
    )

    doc = yaml.safe_load(text)
    dec = doc["owner_decisions_20260929"]
    assert dec["record_sha256"] == OWNER_DECISIONS_20260929_SHA256
    assert dec["signature_claimed"] == "none"
    assert dec["owner_intent"] == "OWNER_INTENT_APPROVED"
    assert dec["signed_ingress"]["status"] == "SIGNED_INGRESS_PENDING"
    assert dec["signed_ingress"]["waived"] is False

    host = dec["hosting"]
    assert host["production_host"] == "van-browser-core"
    assert set(host["forbidden_production_hosts"]) == {
        "van-trading-core", "dial-control", "van-private-core"
    }
    assert host["when_zone_unavailable"] == "PRODUCTION_DISABLED"
    if host["zone_status"] != "AVAILABLE":
        assert host["stagehand_production_state"] == "PRODUCTION_DISABLED"
    assert "Stagehand" in dec["private_plane"]["must_not_host"]

    model = dec["model"]
    assert (model["provider"], model["model"]) == ("anthropic", "claude-sonnet-5")
    # No immutable revision may be recorded unless one was actually observed and pinned.
    if model["pin_status"] != "PINNED_IMMUTABLE_REVISION":
        assert model["immutable_revision_id"] is None

    version = dec["version"]
    assert version["adopted_version"] == "4.1.0"
    assert version["release_commit"] == "cd7b230778cf92269e4cb90e80d97f5113781c51"
    assert version["not_the_adopted_artifact"]["commit"].startswith("ad2bf12e")
    lock = json.loads(STAGEHAND_LOCK.read_text(encoding="utf-8"))
    entry = lock["packages"]["node_modules/@browserbasehq/stagehand"]
    assert entry["version"] == version["adopted_version"]
    assert entry["integrity"] == version["npm_integrity"]

    assert dec["production_gate"]["status"] == "PENDING"
    for finding in dec["blockers"].values():
        assert finding["severity"] == "BLOCKER"

    open_ids = {q["id"] for q in doc["reconciliation_20260929"]["owner_decisions_required"]}
    closed = {q["id"]: q for q in dec["open_questions_closed"]}
    assert open_ids == set(closed)
    for q in closed.values():
        assert q["status"] == "DECIDED" and q["decision_ref"].startswith("owner_decisions_20260929.")


def test_no_provenance_pairs_unreleased_stagehand_head_with_4_1_0():
    """Owner decision §5: ad2bf12e is later unreleased work, never "Stagehand 4.1.0"."""
    row = next(
        line
        for line in (ROOT / "docs" / "project-state" / "MISSION_PROVENANCE_MEMORY_FABRIC_JEV_20260929.md")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.startswith("| browserbase/stagehand |")
    )
    assert "not** 4.1.0" in row and "cd7b230778cf92269e4cb90e80d97f5113781c51" in row


def test_security_policy_amendment_was_applied():
    """§368 — the amendment is owner-approved and now lives in the locked policy."""
    amendment = (DECISIONS / "VAN-AMEND-SECURITY-POLICY-001.md").read_text(encoding="utf-8")
    assert "OWNER_APPROVED" in amendment
    assert "Owner decision (2026-09-18)" in amendment

    policy = SECURITY_POLICY.read_text(encoding="utf-8")
    for section in (
        "## Automation Fabric boundary",
        "## Payments",
        "## Credential isolation",
        "## Browser session sovereignty",
        "## External egress and webhook ingress",
    ):
        assert section in policy, f"amendment section not applied: {section}"


def test_policy_states_payments_are_never_automated():
    policy = SECURITY_POLICY.read_text(encoding="utf-8")
    assert "prohibited by default and cannot be automated" in policy
    assert "Payment instruments are **never stored**" in policy
    assert "A standing authority can never carry it" in policy


def test_policy_defines_browser_subagent_without_weakening_sole_runtime():
    """The sole-agent-runtime sentence must survive the subagent amendment."""
    policy = SECURITY_POLICY.read_text(encoding="utf-8")
    assert "Hermes profile `van` is the sole agent runtime." in policy
    assert "permitted **subagent**" in policy
    assert "A subagent is not an independent agent loop" in policy


def test_locked_security_policy_is_unmodified():
    """The locked authority named in PROJECT_CANONICAL_STATE.json stays byte-identical."""
    state = json.loads((ROOT / "PROJECT_CANONICAL_STATE.json").read_text(encoding="utf-8"))
    assert "docs/SECURITY_POLICY.md" in state["canonical_state"]["locked_authorities"]
    assert _sha256(SECURITY_POLICY) == SECURITY_POLICY_SHA256, (
        "docs/SECURITY_POLICY.md changed. Amendments belong in "
        "docs/decisions/VAN-AMEND-SECURITY-POLICY-001.md until the owner approves them."
    )


def test_no_layer_is_admitted_without_a_signed_decision():
    """§366 — the durable invariant: admission requires a recorded owner decision.

    This is the conditional form of "do not mutate the lock before approval". It
    held before the 2026-09-18 promotion because nothing was admitted, and it holds
    after because each admitted layer names a decision that is SIGNED. It fails if
    anyone admits a layer whose decision is still PENDING.
    """
    proposal = json.loads(PROPOSAL.read_text(encoding="utf-8"))
    lock = json.loads(STACK_LOCK.read_text(encoding="utf-8"))
    admitted = {layer["layer"]: layer for layer in lock["layers"]}

    for name, ref in proposal["adoption_decision_refs"].items():
        if name not in admitted:
            continue
        decision = (ROOT / ref).read_text(encoding="utf-8")
        assert "owner_signature_status: SIGNED" in decision, (
            f"{name} is admitted in stack_lock.json but {ref} is not owner-signed"
        )
        assert admitted[name].get("adoption_decision_ref") == ref, (
            f"{name} is admitted without naming its adoption decision"
        )


def test_promotion_preserved_the_trading_invariants():
    """Admitting three layers must not have widened what may send an order."""
    lock = json.loads(STACK_LOCK.read_text(encoding="utf-8"))
    senders = {layer["layer"] for layer in lock["layers"] if layer["executes_live_orders"]}
    assert senders == {"trading_kernel", "mt5_execution", "deriv_execution", "ctrader_execution"}

    t0 = {layer["layer"] for layer in lock["layers"] if layer["latency_tier"] == "T0"}
    assert t0 == senders


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
    assert settings.automation_n8n_api_key == ""
    assert settings.automation_grant_signing_key == ""
    # The autonomy ceiling deliberately lives in one place only —
    # ``load_browser_policy()`` — so there is no second knob to drift from it.
    assert not hasattr(settings, "browser_semantic_max_tier")


def test_browser_autonomy_ceiling_never_widens_by_accident(monkeypatch):
    """§§88, 378 — L5 is the owner's decision; a typo must not be read as consent."""
    import sys

    sys.path.insert(0, str(ROOT / "backend"))
    from van_gateway.automation.policy import load_browser_policy, reset_policy_cache

    monkeypatch.delenv("VAN_BROWSER_SEMANTIC_MAX_TIER", raising=False)
    reset_policy_cache()
    assert load_browser_policy().max_autonomy_tier == "L5"

    # An unrecognised value falls back to the deterministic tier, not the ceiling.
    monkeypatch.setenv("VAN_BROWSER_SEMANTIC_MAX_TIER", "L9")
    reset_policy_cache()
    assert load_browser_policy().max_autonomy_tier == "L3"

    monkeypatch.setenv("VAN_BROWSER_SEMANTIC_MAX_TIER", "L2")
    reset_policy_cache()
    assert load_browser_policy().max_autonomy_tier == "L2"
    reset_policy_cache()


def test_private_browser_workers_are_real_and_fail_closed():
    """Repository closure means deployable workers, not just gateway adapters.

    Live identity/model/profile qualification remains an external gate, but CI prevents the
    private worker processes from silently collapsing back into "environment prepared".
    """
    browser = ROOT / "deploy" / "van-trading-core" / "browser"
    harness = (browser / "harness_service.py").read_text(encoding="utf-8")
    stagehand = (browser / "stagehand_service.mjs").read_text(encoding="utf-8")
    bootstrap = (browser / "bootstrap-browser-runtime.sh").read_text(encoding="utf-8")
    env = (browser / "runtime.env.example").read_text(encoding="utf-8")
    harness_unit = (
        ROOT / "deploy" / "van-trading-core" / "systemd" / "vati-browser-harness.service"
    ).read_text(encoding="utf-8")
    stagehand_unit = (
        ROOT / "deploy" / "van-trading-core" / "systemd" / "vati-stagehand.service"
    ).read_text(encoding="utf-8")

    assert "browser-harness==0.1.13" in bootstrap
    assert "BROWSER_HARNESS_RUNTIME_GREEN" in bootstrap
    assert "vati-browser-harness.service" in bootstrap
    assert "127.0.0.1" in harness
    assert "allow_helper_authoring" in harness
    assert "cdp-endpoint.json" in harness
    assert "os.chmod(tmp, 0o600)" in harness
    assert "User=van-browser" in harness_unit

    assert '@browserbasehq/stagehand' in (browser / "package.json").read_text(encoding="utf-8")
    assert "Stagehand.create" in stagehand
    assert "localBrowser.connect" in stagehand
    assert 'req.url === "/agent"' in stagehand
    assert "DIRECT_STAGEHAND_AGENT_LOOP_FORBIDDEN" in stagehand
    assert "allow_model_self_selection !== false" in stagehand
    assert "allow_unbounded_agent_loop !== false" in stagehand
    assert "VAN_STAGEHAND_MODEL_KEY_REF" in env
    assert "secretref://browser/stagehand-model" in env
    assert "STAGEHAND_RUNTIME_GREEN" in bootstrap
    assert "HARNESS_AND_STAGEHAND_IMPLEMENTED_PENDING_LIVE_QUALIFICATION" in bootstrap
    assert "User=van-browser" in stagehand_unit
    assert "Requires=vati-browser-harness.service" in stagehand_unit
    assert "NoNewPrivileges=true" in stagehand_unit

    # The credential is a file-backed secret reference. Neither service file nor bootstrap
    # may contain a provider key literal.
    for text in (stagehand, bootstrap, env, stagehand_unit):
        assert "sk-ant-" not in text
        assert "sk-proj-" not in text
