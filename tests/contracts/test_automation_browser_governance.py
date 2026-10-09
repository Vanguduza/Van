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
STAGEHAND_LOCK = ROOT / "deploy" / "van-browser-core" / "browser" / "package-lock.json"


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


#: sha256 of VAN-ADOPT-STAGEHAND-001.yaml through the end of owner_decisions_20260929 (the
#: second append; VAN f55d360d). The blocker closure (unit G4b, review I3) is appended after
#: the marker below; nothing above it may change.
STAGEHAND_OWNER_DECISIONS_SHA256 = "d46d8618253fac1819c7bd7d4c7c65d34998ab98f6b078eaf789c622f0dd82bc"
STAGEHAND_BLOCKER_CLOSURE_MARKER = (
    "\n\n# ====================================================================================="
    "\n# APPENDED 2026-09-29 (third append)"
)
STAGEHAND_VERIFIER_GAP_LIMITATION = (
    'CLOSED (review I3, VAN f55d360d). On /assignments, /interaction/step, the watch runner, '
    'the notebook consumer and automation dispatch, no lane result (done=True, GOAL_ACHIEVED,'
    ' empty Stagehand controls, Jev done, engine success) yields COMPLETED/VERIFIED_SUCCESS; '
    'only WorkflowVerifier VERIFIED over a declared predicate (field/expected other than '
    '`exists`, or correlation keys each with a caller-declared expected value) does. '
    'BrowserTaskService.complete(COMPLETED) requires the latest recorded verdict to be '
    'VERIFIED; dispatch additionally requires the action receipt VERIFIED_SUCCESS with the '
    'engine execution id independently observed. Limits: (1) READ_BACK observes a page the '
    'site controls, so a declared title/URL/text proves what the page shows, not the '
    'server-side effect; (2) automation dispatch has no production observer, so every run is '
    'UNVERIFIABLE until one is qualified; (3) completion is refused while a router step or '
    'assignment run is in flight on the task, and is written only if the verdict it checked '
    "is still the task's latest (I3 MINOR-1, fixed by unit G4b; the in-flight marker is per "
    'gateway process).'
)
STAGEHAND_DIRECT_ACTUATION_LIMITATION = (
    'CLOSED (review I3, VAN f55d360d). On every production caller Stagehand is used only via '
    'observe(); router lane 3 and HybridBrowserWorker turn one observed candidate into a '
    'typed click/fill/press/scroll that VAN classifies from the Harness-observed element and '
    'the Browser Harness executes. StagehandAdapter.act() refuses unless actuation_enabled, '
    'which production wiring never sets; the worker serves /act only on a HISTORICAL_DEV_ONLY'
    ' placement, and the gate refuses a worker whose /health reports act_endpoint_enabled. '
    'Limits: (1) separation is process policy, not capability: the Stagehand 4.1.0 worker '
    'still attaches to the Harness-owned Chromium over a full CDP connection '
    "(stagehand_service.mjs:335), so a compromised worker could actuate; (2) Stagehand's "
    'autonomous act/agent modes stay outside production, which makes the NotebookLM consumer '
    '(notebook.py → act) non-functional in production; (3) the live Harness reports no '
    'element list, so every targeted Stagehand proposal currently goes to owner takeover.'
)


def test_stagehand_blocker_closure_is_appended_and_reads_closed():
    """Review I3 at VAN f55d360d: both Programme B blockers CLOSED, OWNER_DERIVED, append-only.

    The earlier blocks are byte-for-byte what they were (their OPEN statuses included); the
    gate model reads the blocker statuses from the new block, and nothing else about
    Stagehand's production posture changes.
    """
    import yaml

    text = (DECISIONS / "VAN-ADOPT-STAGEHAND-001.yaml").read_text(encoding="utf-8")
    assert text.count(STAGEHAND_BLOCKER_CLOSURE_MARKER) == 1
    prior = text.split(STAGEHAND_BLOCKER_CLOSURE_MARKER, 1)[0] + "\n"
    assert hashlib.sha256(prior.encode("utf-8")).hexdigest() == STAGEHAND_OWNER_DECISIONS_SHA256, (
        "text above the blocker-closure append was edited; append instead"
    )

    doc = yaml.safe_load(text)
    # The recorded-at-the-time statuses stay OPEN; closure is a later statement, not an edit.
    for blocker in doc["owner_decisions_20260929"]["blockers"].values():
        assert blocker["status"] == "OPEN"
    closure = doc["blocker_closure_20260929"]
    assert closure["authority_class"] == "OWNER_DERIVED"
    assert closure["signature_claimed"] == "none"
    assert closure["authority_basis"]["owner_record_sha256"] == OWNER_DECISIONS_20260929_SHA256
    assert closure["authority_basis"]["owner_sections"] == [7, 8, 10]
    review = closure["independent_review"]
    assert (review["id"], review["reviewed_commit"][:8], review["verdict_on_these_blockers"]) == (
        "I3", "f55d360d", "CLOSED")
    blockers = closure["blockers"]
    assert set(blockers) == {"STAGEHAND-VERIFIER-GAP-20260929", "STAGEHAND-DIRECT-ACTUATION-20260929"}
    assert all(b["status"] == "CLOSED" for b in blockers.values())
    assert blockers["STAGEHAND-VERIFIER-GAP-20260929"]["limitation"] == STAGEHAND_VERIFIER_GAP_LIMITATION
    assert blockers["STAGEHAND-DIRECT-ACTUATION-20260929"]["limitation"] == STAGEHAND_DIRECT_ACTUATION_LIMITATION
    for blocker_id, blocker in blockers.items():
        assert blocker["closes"] == f"owner_decisions_20260929.blockers.{blocker_id}"

    # The gate model reads the new block, and only the two blocker gates moved.
    model = json.loads((ROOT / "registries" / "production_activation_gates.json").read_text(encoding="utf-8"))
    stagehand = next(d for d in model["required_decisions"] if d["decision"] == "VAN-ADOPT-STAGEHAND-001.yaml")
    paths = {g["id"]: g["path"] for g in stagehand["gates"]}
    assert paths["blocker_verifier_gap"] == (
        "blocker_closure_20260929.blockers.STAGEHAND-VERIFIER-GAP-20260929.status")
    assert paths["blocker_direct_actuation"] == (
        "blocker_closure_20260929.blockers.STAGEHAND-DIRECT-ACTUATION-20260929.status")
    assert paths["production_gate"] == "owner_decisions_20260929.production_gate.status"
    assert paths["signed_ingress"] == "owner_decisions_20260929.signed_ingress.status"

    # And Stagehand's production posture is unchanged by the closure.
    dec = doc["owner_decisions_20260929"]
    assert dec["production_gate"]["status"] == "PENDING"
    assert dec["signed_ingress"]["status"] == "SIGNED_INGRESS_PENDING"
    assert dec["hosting"]["stagehand_production_state"] == "PRODUCTION_DISABLED"
    assert dec["model"]["pin_status"] == "UNVERIFIED"
    assert dec["version"]["live_qualification"]["status"] == "PENDING"


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
        (ROOT / "deploy" / "van-browser-core" / "browser" / "package.json").read_text(encoding="utf-8")
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
    # Owner decision 2026-09-29 §1: the production package is deploy/van-browser-core; the
    # historical deploy/van-trading-core/browser placement is development-only
    # (tests/contracts/test_van_browser_core_zone.py).
    zone = ROOT / "deploy" / "van-browser-core"
    browser = zone / "browser"
    harness = (browser / "harness_service.py").read_text(encoding="utf-8")
    stagehand = (browser / "stagehand_service.mjs").read_text(encoding="utf-8")
    bootstrap = (zone / "bootstrap.sh").read_text(encoding="utf-8")
    env = (zone / "runtime.env.example").read_text(encoding="utf-8")
    harness_unit = (zone / "systemd" / "van-browser-harness.service").read_text(encoding="utf-8")
    stagehand_unit = (zone / "systemd" / "van-stagehand.service").read_text(encoding="utf-8")

    assert "browser-harness==0.1.13" in bootstrap
    assert "VAN_BROWSER_CORE_WORKERS_GREEN" in bootstrap
    assert "van-browser-harness.service" in bootstrap
    assert "127.0.0.1" in harness
    assert "allow_helper_authoring" in harness
    assert "cdp-endpoint.json" in harness
    # Review I8 MINOR-4: group-readable (0640) for the Stagehand user, which has its own uid.
    assert "os.chmod(tmp, 0o640)" in harness
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
    assert 's["runtime_version"] == "4.1.0"' in bootstrap
    assert "VAN_BROWSER_CORE_INSTALLED_PENDING_QUALIFY_AND_GATES" in bootstrap
    assert "User=van-stagehand\n" in stagehand_unit and "User=van-browser\n" not in stagehand_unit
    assert "Requires=van-browser-harness.service" in stagehand_unit
    assert "NoNewPrivileges=true" in stagehand_unit

    # The credential is a file-backed secret reference. Neither service file nor bootstrap
    # may contain a provider key literal.
    for text in (stagehand, bootstrap, env, stagehand_unit):
        assert "sk-ant-" not in text
        assert "sk-proj-" not in text


# --------------------------------------------------------------------------- coherence
#
# Decision-record signature vocabulary. In docs/decisions, `owner_signature_status: SIGNED`
# means an owner decision recorded through the Project Truth process (PROJECT_TRUTH_PROTOCOL
# authority tier 2, `owner_instruction_is_project_truth_authority`). A device-authenticated,
# replay-protected owner-signed instruction (tier 1) arrives only through signed ingress.
# A record must never let the first be read as the second, and must never contradict itself.

import re

import pytest
import yaml

_SIGNED_INGRESS_PRESENT = {"PRESENT", "SATISFIED"}
_SIGNED_INGRESS_ABSENT = {"ABSENT", "PENDING"}
_GATE_STATUSES = {"PENDING", "SATISFIED"}
_HEADER_DENIES_SIGNATURE = re.compile(
    r"not\s+owner[- ]signed|\bproposal\b|must\s+not\s+mark\s+this\s+owner[- ]signed",
    re.IGNORECASE,
)

# These are measured historical bytes, not authorization allowlists. Only these
# exact recorded owner-intent prefixes can clarify their stale SIGNED/proposal
# vocabulary. The append is explicitly not a signature or trusted intake record.
_HISTORICAL_SIGNATURE_SCOPE_PREFIXES = {
    "VAN-ADOPT-STAGEHAND-001": (
        "2026-10-08", "2026-09-29",
        "f8f70698a9cfb4771a91aa9b4da23ccee805d540c3628166790e1e717d8576f5",
    ),
    "VAN-ADOPT-N8N-001": (
        "2026-10-09", "2026-10-09",
        "bf61cc54cc7db78d8c11c5f2a08bb10cbe80cad6ec1039fe72cb1811fbac49d2",
    ),
    "VAN-ADOPT-BROWSER-HARNESS-001": (
        "2026-10-09", "2026-10-09",
        "e5b2eb0fce7c43a87a12479bad9c1c4171fae6d74257debd876d90ec2bbd8c3b",
    ),
}


def _historical_signature_scope_clarified(text: str, body: dict) -> bool:
    binding = _HISTORICAL_SIGNATURE_SCOPE_PREFIXES.get(body.get("decision_id"))
    if binding is None:
        return False
    appended_on, reconciled_on, expected_prefix_sha256 = binding
    marker = f"\n# APPENDED {appended_on} — signature scope clarification; historical text is frozen.\n"
    clarification = body.get("reconciliation_record")
    semantics = body.get("owner_signature_semantics")
    ingress = body.get("signed_ingress")
    if not all(isinstance(value, dict) for value in (clarification, semantics, ingress)):
        return False
    prefix_sha256 = hashlib.sha256(text.split(marker, 1)[0].encode("utf-8")).hexdigest()
    clarified = (
        text.count(marker) == 1
        and prefix_sha256 == expected_prefix_sha256
        and clarification.get("preserved_prefix_sha256") == expected_prefix_sha256
        and str(clarification.get("reconciled_on")) == reconciled_on
        and clarification.get("header_status") == "HISTORICAL_HEADER_SUPERSEDED_BY_SIGNATURE_SCOPE_CLARIFICATION"
        and semantics.get("basis") == "PROJECT_TRUTH_OWNER_INSTRUCTION"
        and semantics.get("device_signed") is False
        and ingress.get("status") == "ABSENT"
        and ingress.get("evidence_ref") is None
    )
    if appended_on == "2026-10-09":
        clarified = clarified and (
            clarification.get("decision_id") == body.get("decision_id")
            and clarification.get("signature_claimed") == "none"
            and clarification.get("authority_granted") == "none"
            and clarification.get("creates_new_approval") is False
            and clarification.get("production_gate_changed") is False
        )
    return clarified


def decision_coherence_violations(text: str) -> list[str]:
    """Return every signature/status incoherence in one decision record."""
    violations: list[str] = []
    header = []
    for line in text.splitlines():
        if not line.startswith("#"):
            break
        header.append(line)
    body = yaml.safe_load(text) or {}
    status = body.get("owner_signature_status")

    if status == "SIGNED" and (
        _HEADER_DENIES_SIGNATURE.search("\n".join(header))
        or body.get("decision_id") in _HISTORICAL_SIGNATURE_SCOPE_PREFIXES
    ):
        if not _historical_signature_scope_clarified(text, body):
            violations.append("header says NOT owner-signed but owner_signature_status is SIGNED")

    ingress = body.get("signed_ingress")
    semantics = body.get("owner_signature_semantics")
    claims_device_signature = (
        isinstance(semantics, dict) and semantics.get("basis") == "DEVICE_SIGNED_INGRESS"
    ) or (isinstance(semantics, dict) and semantics.get("device_signed") is True) or body.get("device_signed") is True

    if status == "SIGNED" and not isinstance(ingress, dict):
        violations.append(
            "SIGNED without a signed_ingress block: an unqualified SIGNED reads as a "
            "device-signed claim with no signed-ingress evidence reference"
        )
    if status == "SIGNED" and not isinstance(semantics, dict):
        violations.append("SIGNED without owner_signature_semantics stating its basis")
    if (status == "SIGNED" and isinstance(semantics, dict)
            and semantics.get("basis") == "PROJECT_TRUTH_OWNER_INSTRUCTION"
            and semantics.get("device_signed") is not False):
        violations.append("recorded session intent must explicitly deny a device signature")

    if isinstance(ingress, dict):
        ingress_status = ingress.get("status")
        ref = ingress.get("evidence_ref")
        has_ref = isinstance(ref, str) and ref.startswith("evidence://")
        if ingress_status not in _SIGNED_INGRESS_PRESENT | _SIGNED_INGRESS_ABSENT:
            violations.append(f"signed_ingress.status {ingress_status!r} is not a known value")
        if ingress_status in _SIGNED_INGRESS_PRESENT and not has_ref:
            violations.append("signed ingress claimed PRESENT without an evidence:// reference")
        if ingress_status in _SIGNED_INGRESS_ABSENT and ref:
            violations.append("signed ingress ABSENT/PENDING yet carries an evidence reference")
        if claims_device_signature and ingress_status not in _SIGNED_INGRESS_PRESENT:
            violations.append("device-signed basis claimed while signed ingress is not PRESENT")
    elif claims_device_signature:
        violations.append("device-signed basis claimed without a signed-ingress evidence reference")

    for gate_name, gate in (body.get("production_gates") or {}).items():
        components = gate.get("components") or {}
        for name, component in components.items():
            cstatus = component.get("status")
            if cstatus not in _GATE_STATUSES:
                violations.append(f"{gate_name}.{name}: status {cstatus!r} is not PENDING/SATISFIED")
            if cstatus == "SATISFIED" and not component.get("evidence"):
                violations.append(f"{gate_name}.{name}: SATISFIED without evidence")
        all_satisfied = bool(components) and all(
            c.get("status") == "SATISFIED" for c in components.values()
        )
        if gate.get("status") == "SATISFIED" and not all_satisfied:
            violations.append(f"{gate_name}: SATISFIED while a component is not SATISFIED")
        if gate.get("status") != "SATISFIED" and all_satisfied:
            violations.append(f"{gate_name}: every component SATISFIED but gate not SATISFIED")
    return violations


@pytest.mark.parametrize(
    "name", sorted(p.name for p in DECISIONS.glob("*.yaml"))
)
def test_decision_record_signature_status_is_coherent(name):
    violations = decision_coherence_violations((DECISIONS / name).read_text(encoding="utf-8"))
    assert violations == [], f"{name}: {violations}"


def test_coherence_check_rejects_the_known_bad_shapes():
    """The check must fail on each shape it exists to catch (induced failure)."""
    header_contradiction = "# proposal. NOT owner-signed.\nowner_signature_status: SIGNED\n"
    assert any("header" in v for v in decision_coherence_violations(header_contradiction))

    bare_signed = "owner_signature_status: SIGNED\n"
    assert any("signed_ingress" in v for v in decision_coherence_violations(bare_signed))

    forged_ingress = (
        "owner_signature_status: SIGNED\n"
        "owner_signature_semantics: {basis: DEVICE_SIGNED_INGRESS}\n"
        "signed_ingress: {status: PRESENT, evidence_ref: null}\n"
    )
    assert any("evidence://" in v for v in decision_coherence_violations(forged_ingress))

    gate_overclaim = (
        "production_gates:\n  G:\n    status: SATISFIED\n    components:\n"
        "      a: {status: PENDING}\n"
    )
    assert any("SATISFIED while" in v for v in decision_coherence_violations(gate_overclaim))


def test_stagehand_record_preserves_owner_intent_and_names_its_production_gate():
    body = yaml.safe_load((DECISIONS / "VAN-ADOPT-STAGEHAND-001.yaml").read_text(encoding="utf-8"))
    record = body["owner_decision_record"]
    assert record["decision"] == "APPROVED_AS_HERMES_SUBAGENT"
    assert str(record["decided_on"]) == "2026-09-18"
    assert body["owner_signature_evidence_ref"].startswith("evidence://owner/session/")
    assert body["owner_intent_status"] == "APPROVED"
    assert body["signed_ingress"]["status"] == "ABSENT"
    gate = body["production_gates"]["STAGEHAND_PRODUCTION_ADOPTION_RECONCILED"]
    assert set(gate["components"]) == {
        "owner_intent_preserved",
        "contradictory_metadata_corrected",
        "production_signed_ingress_evidence",
        "exact_version_and_digest_pinned",
        "local_cdp_runtime_qualification",
        "deployment_host_approved",
    }
    assert gate["status"] == "PENDING"

#: sha256 of VAN-ADOPT-STAGEHAND-001.yaml through the end of blocker_closure_20260929 (the
#: third append; VAN 65865d00). The review-I4 fence correction (unit G5b) is appended after
#: the marker below; nothing above it may change.
STAGEHAND_BLOCKER_CLOSURE_SHA256 = "6bc5a0a160519da45ce1990eeb5d2aadcb233b4ec819f86fc113ed57e5347d78"
STAGEHAND_FENCE_CORRECTION_MARKER = (
    "\n\n# ====================================================================================="
    "\n# APPENDED 2026-09-29 (fourth append)"
)


def test_stagehand_fence_correction_is_appended_and_leaves_the_blockers_closed():
    """Review I4 MINOR-A: the I3-MAJOR-3 disposition overstated the fence. The correction is
    a later append (the closure text stays byte-for-byte), both blockers stay CLOSED and the
    gate model still reads them from the closure block."""
    import yaml

    text = (DECISIONS / "VAN-ADOPT-STAGEHAND-001.yaml").read_text(encoding="utf-8")
    assert text.count(STAGEHAND_FENCE_CORRECTION_MARKER) == 1
    prior = text.split(STAGEHAND_FENCE_CORRECTION_MARKER, 1)[0] + "\n"
    assert hashlib.sha256(prior.encode("utf-8")).hexdigest() == STAGEHAND_BLOCKER_CLOSURE_SHA256, (
        "text above the fence-correction append was edited; append instead"
    )
    doc = yaml.safe_load(text)
    fix = doc["blocker_closure_correction_20260929"]
    assert (fix["authority_class"], fix["signature_claimed"]) == ("OWNER_DERIVED", "none")
    assert fix["authority_basis"]["owner_record_sha256"] == OWNER_DECISIONS_20260929_SHA256
    assert (fix["independent_review"]["id"], fix["independent_review"]["finding"]) == ("I4", "I4-MINOR-A")
    covers = fix["what_the_fence_covers_after_unit_g5b"]
    assert {"gateway_callers", "step_deadline", "harness_worker", "owner_interactive_input"} <= set(covers)
    for caller in ("/interaction/step", "/assignments", "watch runner", "notebook consumer", "assert_lease_active"):
        assert caller in covers["gateway_callers"], caller
    assert "LEASE_FENCE_REQUIRED" in covers["harness_worker"] and "VAN_HARNESS_STATE_ROOT" in covers["harness_worker"]
    notes = {c["corrects"]: c["note"] for c in fix["wording_corrections"]}
    watch = notes["blocker_closure_20260929.blockers.STAGEHAND-VERIFIER-GAP-20260929.limitation"]
    assert "verify_read_only_evidence" in watch and "not by WorkflowVerifier" in watch
    assert "WorkflowVerifier" in watch
    assert fix["blockers_status_unchanged"] == {
        "STAGEHAND-VERIFIER-GAP-20260929": "CLOSED", "STAGEHAND-DIRECT-ACTUATION-20260929": "CLOSED"}
    closure = doc["blocker_closure_20260929"]["blockers"]
    assert all(b["status"] == "CLOSED" for b in closure.values())
    model = json.loads((ROOT / "registries" / "production_activation_gates.json").read_text(encoding="utf-8"))
    stagehand = next(d for d in model["required_decisions"] if d["decision"] == "VAN-ADOPT-STAGEHAND-001.yaml")
    paths = {g["id"]: g["path"] for g in stagehand["gates"]}
    assert paths["blocker_verifier_gap"] == "blocker_closure_20260929.blockers.STAGEHAND-VERIFIER-GAP-20260929.status"
    assert paths["blocker_direct_actuation"] == (
        "blocker_closure_20260929.blockers.STAGEHAND-DIRECT-ACTUATION-20260929.status")


#: sha256 of VAN-ADOPT-STAGEHAND-001.yaml through the end of the fourth append
#: (blocker_closure_correction_20260929; VAN fbe5502e). The review-I5 correction (unit G6b)
#: is appended after the marker below; nothing above it may change.
STAGEHAND_FENCE_CORRECTION_SHA256 = "13d2a4d30c16144242fd91f797907576f93a1df44155f6df28274ba34b06b721"
STAGEHAND_I5_CORRECTION_MARKER = (
    "\n\n# ====================================================================================="
    "\n# APPENDED 2026-09-30 (fifth append)"
)


def test_stagehand_i5_fence_correction_is_appended_and_corrects_the_three_statements():
    """Review I5 R1: the fourth append overstated the fence (a /step kept inside its lease; a
    restart never re-admitting a stale generation; "at least" a quarter). The correction is a
    later append, the text above stays byte-for-byte and both blockers stay CLOSED."""
    import yaml

    text = (DECISIONS / "VAN-ADOPT-STAGEHAND-001.yaml").read_text(encoding="utf-8")
    assert text.count(STAGEHAND_I5_CORRECTION_MARKER) == 1
    prior = text.split(STAGEHAND_I5_CORRECTION_MARKER, 1)[0] + "\n"
    assert hashlib.sha256(prior.encode("utf-8")).hexdigest() == STAGEHAND_FENCE_CORRECTION_SHA256, (
        "text above the review-I5 append was edited; append instead"
    )
    doc = yaml.safe_load(text)
    fix = doc["fence_correction_review_i5_20260930"]
    assert (fix["authority_class"], fix["signature_claimed"]) == ("OWNER_DERIVED", "none")
    assert fix["authority_basis"]["owner_record_sha256"] == OWNER_DECISIONS_20260929_SHA256
    assert fix["independent_review"]["id"] == "I5"
    by_target = {c["corrects"]: c for c in fix["statement_corrections"]}
    prior_block = doc["blocker_closure_correction_20260929"]
    step = by_target["blocker_closure_correction_20260929.limits_after_unit_g5b[1]"]
    assert step["overstated"] in prior_block["limits_after_unit_g5b"][1]
    restart = by_target["blocker_closure_correction_20260929.what_the_fence_covers_after_unit_g5b.harness_worker"]
    assert restart["overstated"] in prior_block["what_the_fence_covers_after_unit_g5b"]["harness_worker"]
    assert "LEASE_FENCE_STATE_MISSING" in restart["after_unit_g6b"]
    quarter = by_target["blocker_closure_correction_20260929.what_the_fence_covers_after_unit_g5b.step_deadline"]
    assert quarter["overstated"] in prior_block["what_the_fence_covers_after_unit_g5b"]["step_deadline"]
    assert "at most a quarter" in quarter["correct_wording"]
    assert "LEASE_FENCE_MAC_INVALID" in fix["added_after_unit_g6b"]["fence_authentication"]
    assert fix["blockers_status_unchanged"] == {
        "STAGEHAND-VERIFIER-GAP-20260929": "CLOSED", "STAGEHAND-DIRECT-ACTUATION-20260929": "CLOSED"}
    assert all(b["status"] == "CLOSED" for b in doc["blocker_closure_20260929"]["blockers"].values())

def test_append_header_clarification_requires_the_frozen_prefix_digest():
    text = (DECISIONS / "VAN-ADOPT-STAGEHAND-001.yaml").read_text()
    assert decision_coherence_violations(text) == []
    body = yaml.safe_load(text)
    digest = body["reconciliation_record"]["preserved_prefix_sha256"]
    assert any("header" in v for v in decision_coherence_violations(
        text.replace(digest, "0" * 64)))


@pytest.mark.parametrize("decision_id", ["VAN-ADOPT-N8N-001", "VAN-ADOPT-BROWSER-HARNESS-001"])
def test_legacy_adoption_clarification_preserves_every_original_byte_and_status(decision_id):
    text = (DECISIONS / (decision_id + ".yaml")).read_text()
    appended_on, reconciled_on, original_sha256 = _HISTORICAL_SIGNATURE_SCOPE_PREFIXES[decision_id]
    marker = f"\n# APPENDED {appended_on} — signature scope clarification; historical text is frozen.\n"
    original = text.split(marker, 1)[0]
    assert hashlib.sha256(original.encode("utf-8")).hexdigest() == original_sha256
    original_body, current_body = yaml.safe_load(original), yaml.safe_load(text)
    assert all(current_body[key] == value for key, value in original_body.items())
    assert current_body["owner_signature_status"] == "SIGNED"
    assert current_body["owner_decision_record"] == original_body["owner_decision_record"]
    assert current_body["owner_signature_evidence_ref"] == original_body["owner_signature_evidence_ref"]
    assert current_body.get("production_gates") == original_body.get("production_gates")
    assert current_body["signed_ingress"]["status"] == "ABSENT"
    assert current_body["signed_ingress"]["evidence_ref"] is None
    assert current_body["owner_signature_semantics"]["device_signed"] is False
    assert str(current_body["reconciliation_record"]["reconciled_on"]) == reconciled_on
    assert _historical_signature_scope_clarified(text, current_body)
    assert decision_coherence_violations(text) == []


@pytest.mark.parametrize("decision_id", sorted(_HISTORICAL_SIGNATURE_SCOPE_PREFIXES))
@pytest.mark.parametrize("mutation", [
    "altered_history", "altered_history_and_rehashed_claim", "removed_historical_header",
    "wrong_prefix_digest", "missing_marker", "duplicate_marker", "wrong_append_date",
    "wrong_reconciliation_date", "different_decision", "forged_device_signature",
    "numeric_device_signature_denial", "forged_device_basis", "forged_present_ingress",
])
def test_historical_signature_clarification_cannot_excuse_tampered_or_forged_records(decision_id, mutation):
    text = (DECISIONS / (decision_id + ".yaml")).read_text()
    appended_on, reconciled_on, original_sha256 = _HISTORICAL_SIGNATURE_SCOPE_PREFIXES[decision_id]
    marker = f"\n# APPENDED {appended_on} — signature scope clarification; historical text is frozen.\n"
    prefix, append = text.split(marker, 1)
    if mutation in {"altered_history", "altered_history_and_rehashed_claim"}:
        altered = prefix.replace("subject: ", "subject: forged ", 1)
        text = altered + marker + append
        if mutation == "altered_history_and_rehashed_claim":
            text = text.replace(original_sha256, hashlib.sha256(altered.encode("utf-8")).hexdigest())
    elif mutation == "removed_historical_header":
        text = prefix[prefix.index("decision_id:"):] + marker + append
    elif mutation == "wrong_prefix_digest":
        text = text.replace(original_sha256, "0" * 64)
    elif mutation == "missing_marker":
        text = text.replace(marker, "\n# clarification marker removed\n")
    elif mutation == "duplicate_marker":
        text += marker + "# duplicate clarification marker\n"
    elif mutation == "wrong_append_date":
        text = text.replace(marker, marker.replace(appended_on, "2026-10-10"))
    elif mutation == "wrong_reconciliation_date":
        text = prefix + marker + append.replace("reconciled_on: " + reconciled_on, "reconciled_on: 2026-10-10")
    elif mutation == "different_decision":
        text = text.replace(decision_id, "VAN-ADOPT-UNRECORDED-001")
    elif mutation == "forged_device_signature":
        text = text.replace("device_signed: false", "device_signed: true")
    elif mutation == "numeric_device_signature_denial":
        text = text.replace("device_signed: false", "device_signed: 0")
    elif mutation == "forged_device_basis":
        text = text.replace("basis: PROJECT_TRUTH_OWNER_INSTRUCTION", "basis: DEVICE_SIGNED_INGRESS")
    else:
        text = text.replace("status: ABSENT", "status: PRESENT").replace(
            "evidence_ref: null", "evidence_ref: evidence://forged/device-signature")
    assert decision_coherence_violations(text), (decision_id, mutation)


@pytest.mark.parametrize("decision_id", ["VAN-ADOPT-N8N-001", "VAN-ADOPT-BROWSER-HARNESS-001"])
@pytest.mark.parametrize("mutation", [
    "wrong_append_decision", "signature_claim", "authority_claim", "approval_claim", "production_gate_claim",
])
def test_new_legacy_clarification_is_bound_and_cannot_grant_authority(decision_id, mutation):
    text = (DECISIONS / (decision_id + ".yaml")).read_text()
    marker = "\n# APPENDED 2026-10-09 — signature scope clarification; historical text is frozen.\n"
    prefix, append = text.split(marker, 1)
    original, replacement = {
        "wrong_append_decision": ("decision_id: " + decision_id, "decision_id: VAN-ADOPT-UNRECORDED-001"),
        "signature_claim": ("signature_claimed: none", "signature_claimed: device"),
        "authority_claim": ("authority_granted: none", "authority_granted: owner"),
        "approval_claim": ("creates_new_approval: false", "creates_new_approval: true"),
        "production_gate_claim": ("production_gate_changed: false", "production_gate_changed: true"),
    }[mutation]
    assert original in append
    assert decision_coherence_violations(prefix + marker + append.replace(original, replacement))
