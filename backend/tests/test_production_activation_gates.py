"""Owner decision 2026-09-29 §6 — the production activation gate model fails closed.

The health surface once reported production activation as permitted because no required
decision carried the literal ``owner_signature_status: PENDING``. These regressions pin the
replacement: activation is permitted only when every governance and production gate in the
explicit model is GREEN, and anything unknown, missing or unparseable is not GREEN.

Each case builds a throwaway repository (gate model + decision records) so the verdict is
driven by the records alone; the last cases run the real repository.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from van_gateway.automation import health
from van_gateway.automation.production_gates import GATE_MODEL, evaluate_production_gates

OWNER = {"id": "owner_decision", "kind": "owner_decision", "path": "owner_signature_status",
         "green": ["SIGNED"], "pending": ["PENDING"]}
INTENT = {"id": "owner_intent", "kind": "owner_decision", "path": "decisions.owner_intent",
          "green": ["OWNER_INTENT_APPROVED"], "pending": ["PENDING"]}
PRODUCTION = {"id": "production_gate", "kind": "production", "path": "decisions.production_gate.status",
              "green": ["GREEN"], "pending": ["PENDING"], "blocked": ["BLOCKED"]}
LIVE = {"id": "live_qualification", "kind": "production",
        "path": "decisions.live_qualification.status",
        "green": ["GREEN"], "pending": ["PENDING"], "blocked": ["FAILED"]}
INGRESS = {"id": "signed_ingress", "kind": "production", "path": "decisions.signed_ingress.status",
           "green": ["SIGNED_INGRESS_VERIFIED"], "pending": ["SIGNED_INGRESS_PENDING"]}


def _record(owner="SIGNED", intent="OWNER_INTENT_APPROVED", production="GREEN", live="GREEN",
            ingress="SIGNED_INGRESS_VERIFIED") -> str:
    return (
        f"decision_id: X-001\nowner_signature_status: {owner}\n"
        "decisions:\n"
        f"  owner_intent: {intent}\n"
        f"  production_gate:\n    status: {production}\n"
        f"  live_qualification:\n    status: {live}\n"
        f"  signed_ingress:\n    status: {ingress}\n"
    )


def _repo(tmp_path: Path, record: str | None, gates=(OWNER, INTENT, PRODUCTION, LIVE, INGRESS),
          extra: list[dict] | None = None) -> Path:
    (tmp_path / "docs" / "decisions").mkdir(parents=True)
    if record is not None:
        (tmp_path / "docs" / "decisions" / "X-001.yaml").write_text(record, encoding="utf-8")
    model = {
        "schema_version": 1,
        "decisions_dir": "docs/decisions",
        "required_decisions": [{"decision": "X-001.yaml", "format": "yaml", "gates": list(gates)}]
        + (extra or []),
    }
    path = tmp_path / "gates.json"
    path.write_text(json.dumps(model), encoding="utf-8")
    return path


def _eval(tmp_path: Path, model: Path) -> dict:
    return evaluate_production_gates(model_path=model, repo_root=tmp_path)


def _status(result: dict, gate: str) -> str:
    return next(g["status"] for g in result["gates"] if g["gate"] == gate)


# --------------------------------------------------------------- the §6 required regressions


def test_owner_intent_approved_with_production_gate_pending_is_not_permitted(tmp_path):
    """§6 regression 1 — the exact shape of the bypass: intent approved, production PENDING."""
    result = _eval(tmp_path, _repo(tmp_path, _record(production="PENDING")))
    assert _status(result, "owner_intent") == "GREEN"
    assert _status(result, "production_gate") == "PENDING"
    assert result["owner_decisions_pending"] == []  # the owner half is satisfied...
    assert result["production_activation_permitted"] is False  # ...and that is not enough
    assert result["production_gates_not_green"] == ["X-001.yaml:production_gate"]


def test_signed_owner_decision_with_live_qualification_pending_is_not_permitted(tmp_path):
    """§6 regression 2 — a signature authorizes; it does not qualify a live runtime."""
    result = _eval(tmp_path, _repo(tmp_path, _record(owner="SIGNED", live="PENDING")))
    assert _status(result, "owner_decision") == "GREEN"
    assert _status(result, "live_qualification") == "PENDING"
    assert result["production_activation_permitted"] is False


def test_all_required_gates_green_is_permitted(tmp_path):
    """§6 regression 3 — the model is not a constant False; all GREEN opens it."""
    result = _eval(tmp_path, _repo(tmp_path, _record()))
    assert {g["status"] for g in result["gates"]} == {"GREEN"}
    assert result["production_gates_not_green"] == []
    assert result["production_activation_permitted"] is True


# ------------------------------------------------------------------------- fail closed


def test_missing_decision_file_is_not_permitted(tmp_path):
    result = _eval(tmp_path, _repo(tmp_path, None))
    assert result["owner_decisions_missing"] == ["X-001.yaml"]
    assert {g["status"] for g in result["gates"]} == {"UNKNOWN"}
    assert result["production_activation_permitted"] is False


def test_unknown_status_value_is_not_permitted(tmp_path):
    """A value outside the declared vocabulary — even a hopeful one — is UNKNOWN."""
    result = _eval(tmp_path, _repo(tmp_path, _record(ingress="WAIVED")))
    assert _status(result, "signed_ingress") == "UNKNOWN"
    assert result["production_activation_permitted"] is False


def test_missing_gate_path_is_not_permitted(tmp_path):
    record = "decision_id: X-001\nowner_signature_status: SIGNED\n"
    result = _eval(tmp_path, _repo(tmp_path, record))
    assert _status(result, "owner_decision") == "GREEN"
    assert _status(result, "production_gate") == "UNKNOWN"
    assert result["production_activation_permitted"] is False


def test_unparseable_decision_is_not_permitted(tmp_path):
    result = _eval(tmp_path, _repo(tmp_path, "owner_signature_status: [SIGNED\n  : :"))
    assert {g["status"] for g in result["gates"]} == {"UNKNOWN"}
    assert result["production_activation_permitted"] is False


@pytest.mark.parametrize("model_text", [None, "{not json", json.dumps({"required_decisions": []})])
def test_missing_unreadable_or_empty_model_is_not_permitted(tmp_path, model_text):
    """An empty model must not be vacuously GREEN."""
    path = tmp_path / "gates.json"
    if model_text is not None:
        path.write_text(model_text, encoding="utf-8")
    result = _eval(tmp_path, path)
    assert result["gate_model_error"]
    assert result["production_activation_permitted"] is False


def test_decision_with_no_declared_gates_is_not_permitted(tmp_path):
    model = _repo(tmp_path, _record(), extra=[{"decision": "Y-001.yaml", "gates": []}])
    result = _eval(tmp_path, model)
    assert result["production_activation_permitted"] is False


def test_markdown_status_is_read_as_a_field_not_a_substring(tmp_path):
    """A Markdown record's `**Status:**` field is parsed, not grepped anywhere in the text."""
    (tmp_path / "docs" / "decisions").mkdir(parents=True)
    (tmp_path / "docs" / "decisions" / "M.md").write_text(
        "# M\n\n**Status:** `PROPOSED`\n\nOnce approved this becomes OWNER_APPROVED.\n",
        encoding="utf-8",
    )
    spec = {"id": "owner_decision", "kind": "owner_decision", "path": "Status",
            "green": ["OWNER_APPROVED"], "pending": ["PROPOSED"]}
    model = tmp_path / "gates.json"
    model.write_text(json.dumps({"required_decisions": [
        {"decision": "M.md", "format": "markdown", "gates": [spec]}]}), encoding="utf-8")
    result = _eval(tmp_path, model)
    assert _status(result, "owner_decision") == "PENDING"
    assert result["owner_decisions_pending"] == ["M.md"]
    assert result["production_activation_permitted"] is False


# ------------------------------------------------------------------- the real repository


def test_real_repository_is_not_permitted_today():
    """Project Truth on 2026-09-29: owner intent approved, Stagehand production PENDING."""
    state = health.governance_state()
    assert state["gate_model_error"] is None
    assert state["owner_decisions_pending"] == []
    assert state["owner_decisions_missing"] == []
    assert state["production_activation_permitted"] is False
    by_id = {(g["decision"], g["gate"]): g for g in state["gates"]}
    stagehand = "VAN-ADOPT-STAGEHAND-001.yaml"
    assert by_id[(stagehand, "owner_intent")]["status"] == "GREEN"
    assert by_id[(stagehand, "production_gate")]["status"] == "PENDING"
    assert by_id[(stagehand, "signed_ingress")]["raw_value"] == "SIGNED_INGRESS_PENDING"
    # Closed by the blocker_closure_20260929 append (review I3 at VAN f55d360d); the other
    # Stagehand gates stay pending, so neither the global summary nor Stagehand is permitted.
    for blocker in ("blocker_verifier_gap", "blocker_direct_actuation"):
        assert by_id[(stagehand, blocker)]["status"] == "GREEN"
        assert by_id[(stagehand, blocker)]["path"].startswith("blocker_closure_20260929.blockers.")
    assert state["capabilities"]["stagehand"]["production_activation_permitted"] is False
    assert {"VAN-ADOPT-STAGEHAND-001.yaml:production_gate", "VAN-ADOPT-STAGEHAND-001.yaml:signed_ingress",
            "VAN-ADOPT-STAGEHAND-001.yaml:production_host", "VAN-ADOPT-STAGEHAND-001.yaml:model_pin",
            "VAN-ADOPT-STAGEHAND-001.yaml:live_qualification"} <= set(state["production_gates_not_green"])


def test_real_model_covers_every_required_decision_with_owner_and_production_gates():
    """The four §368 decisions stay required, and each Stagehand production gate is modelled."""
    model = json.loads(GATE_MODEL.read_text(encoding="utf-8"))
    decisions = {d["decision"]: d for d in model["required_decisions"]}
    assert set(decisions) == {
        "VAN-ADOPT-N8N-001.yaml",
        "VAN-ADOPT-STAGEHAND-001.yaml",
        "VAN-ADOPT-BROWSER-HARNESS-001.yaml",
        "VAN-AMEND-SECURITY-POLICY-001.md",
    }
    assert set(health.REQUIRED_DECISIONS) == set(decisions)
    for entry in decisions.values():
        assert any(g["kind"] == "owner_decision" for g in entry["gates"])
    stagehand_gates = {g["id"] for g in decisions["VAN-ADOPT-STAGEHAND-001.yaml"]["gates"]}
    assert {"production_gate", "signed_ingress", "production_host", "model_pin",
            "live_qualification"} <= stagehand_gates
    # No gate may accept a waiver of signed ingress as GREEN (owner decision §2).
    ingress = next(g for g in decisions["VAN-ADOPT-STAGEHAND-001.yaml"]["gates"]
                   if g["id"] == "signed_ingress")
    assert all("WAIV" not in v for v in ingress["green"])


# --------------------------------------------------------------- reviewer I minor 2


APPENDED_ALL_GREEN = (
    "decisions:\n"
    "  owner_intent: OWNER_INTENT_APPROVED\n"
    "  production_gate:\n    status: GREEN\n"
    "  live_qualification:\n    status: GREEN\n"
    "  signed_ingress:\n    status: SIGNED_INGRESS_VERIFIED\n"
)


def test_an_appended_duplicate_block_cannot_override_the_record(tmp_path):
    """Probe review-i/probes/gates.py: appending a second all-GREEN block under the same key
    to the real Stagehand record made safe_load keep the last one -> permitted: True."""
    record = _record(production="PENDING", live="PENDING", ingress="SIGNED_INGRESS_PENDING")
    result = _eval(tmp_path, _repo(tmp_path, record + APPENDED_ALL_GREEN))
    assert result["production_activation_permitted"] is False
    assert {g["status"] for g in result["gates"]} == {"UNKNOWN"}
    assert all("duplicate key 'decisions'" in (g["reason"] or "") for g in result["gates"])


@pytest.mark.parametrize("record", [
    _record() + "owner_signature_status: SIGNED\n",                        # top level
    _record().replace("  owner_intent: OWNER_INTENT_APPROVED\n",
                      "  owner_intent: PENDING\n  owner_intent: OWNER_INTENT_APPROVED\n"),  # nested
    "base: &b\n  owner_signature_status: SIGNED\n" + _record().replace(
        "decision_id: X-001\n", "decision_id: X-001\n<<: *b\n"),        # merge key vs stated key
])
def test_any_repeated_key_is_unknown_even_when_every_value_is_green(tmp_path, record):
    result = _eval(tmp_path, _repo(tmp_path, record))
    assert result["production_activation_permitted"] is False
    assert "UNKNOWN" in {g["status"] for g in result["gates"]}


def test_the_real_decision_records_have_no_repeated_keys():
    from van_gateway.automation.production_gates import REPO_ROOT, _unique_key_yaml_load

    model = json.loads(GATE_MODEL.read_text(encoding="utf-8"))
    for entry in model["required_decisions"]:
        if entry.get("format", "yaml") == "yaml":
            path = REPO_ROOT / model["decisions_dir"] / entry["decision"]
            assert isinstance(_unique_key_yaml_load(path.read_text(encoding="utf-8")), dict)


# --------------------------------------------------------------- reviewer I minor 8


def _capability_repo(tmp_path: Path, *, stagehand="PENDING", harness="SIGNED", n8n="SIGNED",
                     drop: str | None = None) -> Path:
    decisions = tmp_path / "docs" / "decisions"
    decisions.mkdir(parents=True)
    simple = {"id": "owner_decision", "kind": "owner_decision", "path": "owner_signature_status",
              "green": ["SIGNED"], "pending": ["PENDING"]}
    prod = {"id": "production_gate", "kind": "production", "path": "production_gate",
            "green": ["GREEN"], "pending": ["PENDING"]}
    records = {
        "VAN-ADOPT-N8N-001.yaml": (f"owner_signature_status: {n8n}\n", [simple]),
        "VAN-ADOPT-BROWSER-HARNESS-001.yaml": (f"owner_signature_status: {harness}\n", [simple]),
        "VAN-ADOPT-STAGEHAND-001.yaml": (f"owner_signature_status: SIGNED\nproduction_gate: {stagehand}\n",
                                         [simple, prod]),
        # Unit G12: the egress qualification the browser capabilities inherit (GREEN stand-in).
        "VAN-BROWSER-CORE-EGRESS-001.yaml": ("owner_signature_status: SIGNED\n", [simple]),
    }
    required = []
    for name, (text, gates) in records.items():
        (decisions / name).write_text(text, encoding="utf-8")
        if name != drop:
            required.append({"decision": name, "format": "yaml", "gates": gates})
    (decisions / "VAN-AMEND-SECURITY-POLICY-001.md").write_text("**Status:** `OWNER_APPROVED`\n", encoding="utf-8")
    required.append({"decision": "VAN-AMEND-SECURITY-POLICY-001.md", "format": "markdown",
                     "gates": [{"id": "owner_decision", "kind": "owner_decision", "path": "Status",
                                "green": ["OWNER_APPROVED"]}]})
    path = tmp_path / "gates.json"
    path.write_text(json.dumps({"decisions_dir": "docs/decisions", "required_decisions": required}), encoding="utf-8")
    return path


def test_stagehand_gates_do_not_make_the_harness_path_look_not_permitted(tmp_path):
    result = _eval(tmp_path, _capability_repo(tmp_path, stagehand="PENDING"))
    assert result["production_activation_permitted"] is False  # global meaning unchanged
    caps = result["capabilities"]
    assert caps["browser_harness"]["production_activation_permitted"] is True
    assert caps["n8n"]["production_activation_permitted"] is True
    assert caps["stagehand"]["production_activation_permitted"] is False
    assert caps["stagehand"]["gates_not_green"] == ["VAN-ADOPT-STAGEHAND-001.yaml:production_gate"]


def test_stagehand_inherits_the_harness_decision(tmp_path):
    caps = _eval(tmp_path, _capability_repo(tmp_path, stagehand="GREEN", harness="PENDING"))["capabilities"]
    assert caps["browser_harness"]["production_activation_permitted"] is False
    assert caps["stagehand"]["production_activation_permitted"] is False
    assert caps["n8n"]["production_activation_permitted"] is True


def test_a_capability_whose_decision_the_model_does_not_require_is_not_permitted(tmp_path):
    caps = _eval(tmp_path, _capability_repo(tmp_path, drop="VAN-ADOPT-N8N-001.yaml"))["capabilities"]
    assert caps["n8n"]["production_activation_permitted"] is False
    assert "VAN-ADOPT-N8N-001.yaml" in caps["n8n"]["error"]


def test_an_unreadable_model_permits_no_capability(tmp_path):
    result = _eval(tmp_path, tmp_path / "missing.json")
    assert all(c["production_activation_permitted"] is False for c in result["capabilities"].values())


def test_health_governance_keeps_its_keys_and_adds_per_capability_fields():
    state = health.governance_state()
    assert {"owner_decisions_pending", "owner_decisions_missing", "production_activation_permitted",
            "production_gates_not_green", "gates", "gate_model", "gate_model_error"} <= set(state)
    assert set(state["production_activation_permitted_by_capability"]) == {"n8n", "browser_harness", "stagehand", "jev_browser_effect"}
    assert state["production_activation_permitted"] is False


# --------------------------------------------------------------- unit G12: egress qualification
EGRESS = "VAN-BROWSER-CORE-EGRESS-001.yaml"


def _egress_gate() -> dict:
    model = json.loads(GATE_MODEL.read_text(encoding="utf-8"))
    return next(d for d in model["capability_decisions"] if d["decision"] == EGRESS)["gates"][0]


def test_real_model_gates_every_browser_capability_on_egress_qualification_and_it_is_pending():
    from van_gateway.automation.production_gates import BROWSER_EGRESS_DECISION, CAPABILITY_DECISIONS

    assert BROWSER_EGRESS_DECISION == EGRESS
    for capability in ("browser_harness", "stagehand", "jev_browser_effect"):
        assert EGRESS in CAPABILITY_DECISIONS[capability]
    assert EGRESS not in CAPABILITY_DECISIONS["n8n"]
    gate = _egress_gate()
    assert gate["kind"] == "qualify_report" and gate["zone"] == "van-browser-core"
    assert set(gate["required_checks"]) == {
        "firewall_loaded", "browser_udp_blocked", "browser_tcp_bypass_blocked", "egress_proxy_active",
        "egress_refuses_without_policy", "egress_policy_mac_enforced", "egress_refuses_websocket_and_write",
        "harness_uses_egress_proxy", "network_guard_canary", "egress_refuses_smuggling", "egress_refuses_other_users",
        "stagehand_isolated"}
    state = evaluate_production_gates()
    gates = {(g["decision"], g["gate"]): g for g in state["capability_gates"]}
    assert gates[(EGRESS, "egress_qualification")]["status"] == "PENDING"
    for capability in ("browser_harness", "stagehand", "jev_browser_effect"):
        assert f"{EGRESS}:egress_qualification" in state["capabilities"][capability]["gates_not_green"]
        assert state["capabilities"][capability]["production_activation_permitted"] is False
    # Every check the gate requires is one qualify.sh emits and requires.
    qualify = (GATE_MODEL.parents[1] / "deploy/van-browser-core/qualify.sh").read_text(encoding="utf-8")
    for check in gate["required_checks"]:
        assert f"add {check} GREEN" in qualify and f"add {check} RED" in qualify, check


def _egress_repo(tmp_path: Path, *, status="QUALIFIED", checks=None, zone="van-browser-core",
                 reference=None, pin=None, gate=None, fails=0, generated=None, host="vbc-1",
                 measured=None) -> dict:
    import hashlib
    from datetime import datetime, timezone

    gate = gate or _egress_gate()
    digests = {}
    for name, source in gate.get("artifacts", {}).items():
        target = tmp_path / source
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"code of {name}\n", encoding="utf-8")
        digests[name] = hashlib.sha256(target.read_bytes()).hexdigest()
    digests.update(measured or {})
    stamp = generated if generated is not None else datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    decisions = tmp_path / "docs" / "decisions"
    decisions.mkdir(parents=True)
    report = tmp_path / gate["report_dir"] / "qualify-20261001.json"
    report.parent.mkdir(parents=True)
    rows = checks if checks is not None else [
        {"check": c, "status": "GREEN", "required": 1, "detail": ""} for c in gate["required_checks"]]
    report.write_text(json.dumps({"zone": zone, "generated_at_utc": stamp, "host": host, "artifacts": digests,
                                  "fails": fails, "checks": rows}), encoding="utf-8")

    sha = hashlib.sha256(report.read_bytes()).hexdigest()
    ref = reference if reference is not None else report.relative_to(tmp_path).as_posix()
    (decisions / EGRESS).write_text(
        f"egress_qualification:\n  status: {status}\n  qualify_report: {json.dumps(ref)}\n"
        f"  qualify_report_sha256: {json.dumps(pin if pin is not None else sha)}\n", encoding="utf-8")
    path = tmp_path / "gates.json"
    path.write_text(json.dumps({"decisions_dir": "docs/decisions", "required_decisions": [
        {"decision": EGRESS, "format": "yaml", "gates": [gate]}]}), encoding="utf-8")
    result = evaluate_production_gates(path, tmp_path)
    return result["gates"][0]


def test_egress_gate_is_green_only_with_a_pinned_all_green_report(tmp_path):
    assert _egress_repo(tmp_path)["status"] == "GREEN"


@pytest.mark.parametrize("label, kwargs, expected", [
    ("pending as committed", {"status": "PENDING"}, "PENDING"),
    ("QUALIFIED with no report", {"reference": ""}, "UNKNOWN"),
    ("report outside the report directory", {"reference": "docs/decisions/" + EGRESS}, "UNKNOWN"),
    ("report path climbing out", {"reference": "evidence/van-browser-core/qualify/../../../gates.json"}, "UNKNOWN"),
    ("pin does not match", {"pin": "0" * 64}, "UNKNOWN"),
    ("report for another zone", {"zone": "van-trading-core"}, "UNKNOWN"),
    ("a required check missing", {"checks": [{"check": "firewall_loaded", "status": "GREEN", "required": 1}]}, "UNKNOWN"),
    ("a required check RED", {"checks": None, "red": "browser_udp_blocked"}, "BLOCKED"),
    ("a required check GREEN but not required", {"checks": None, "optional": "egress_proxy_active"}, "UNKNOWN"),
    ("status outside the vocabulary", {"status": "GREEN"}, "UNKNOWN"),
    # Review I8 MINOR-1: the report as a whole must pass.
    ("fails > 0 although every listed check is GREEN", {"fails": 1}, "BLOCKED"),
    ("fails missing", {"fails": None}, "UNKNOWN"),
    ("fails not an integer", {"fails": True}, "UNKNOWN"),
    ("a required check outside the list RED", {"checks": None, "extra_red": "worker_health"}, "BLOCKED"),
])
def test_egress_gate_is_not_green_without_the_report(tmp_path, label, kwargs, expected):
    red, optional, extra_red = kwargs.pop("red", None), kwargs.pop("optional", None), kwargs.pop("extra_red", None)
    if red or optional or extra_red:
        rows = [{"check": c, "status": "RED" if c == red else "GREEN", "required": 0 if c == optional else 1}
                for c in _egress_gate()["required_checks"]]
        if extra_red:
            rows.append({"check": extra_red, "status": "RED", "required": 1})
        kwargs["checks"] = rows
    assert _egress_repo(tmp_path, **kwargs)["status"] == expected, label


def test_review_i8_lab_report_with_the_canary_red_is_blocked(tmp_path):
    """Review I8 MINOR-1, its gate-lab report: fails=2, network_guard_canary and worker_health
    RED, every other listed check GREEN. It was GREEN."""
    gate = _egress_gate()
    rows = [{"check": c, "status": "RED" if c == "network_guard_canary" else "GREEN", "required": 1}
            for c in gate["required_checks"]] + [{"check": "worker_health", "status": "RED", "required": 1}]
    result = _egress_repo(tmp_path, checks=rows, fails=2)
    assert result["status"] == "BLOCKED" and "network_guard_canary" in result["reason"]
    # The same report with the canary dropped from the model's list is still BLOCKED.
    other = tmp_path / "other"
    other.mkdir()
    thin = dict(gate, required_checks=[c for c in gate["required_checks"] if c != "network_guard_canary"])
    assert _egress_repo(other, checks=rows, fails=2, gate=thin)["status"] == "BLOCKED"


def test_a_qualify_report_gate_without_required_checks_is_unknown(tmp_path):
    gate = dict(_egress_gate(), required_checks=[])
    result = _egress_repo(tmp_path, gate=gate)
    assert result["status"] == "UNKNOWN" and "required_checks" in result["reason"]


@pytest.mark.parametrize("label, kwargs", [
    ("taken longer ago than max_age_hours", {"generated": "2026-01-01T00:00:00Z"}),
    ("stamped in the future", {"generated": "2099-01-01T00:00:00Z"}),
    ("no timestamp", {"generated": ""}),
    ("no host", {"host": ""}),
    ("measured on other code", {"measured": {"egress_proxy.py": "0" * 64}}),
    ("an artifact it could not read", {"measured": {"van-browser-core.nft": "missing"}}),
])
def test_review_i9_an_all_green_report_not_bound_to_now_and_this_code_is_unknown(tmp_path, label, kwargs):
    """Review I9 MINOR-2: the report was pinned by sha256 only, so a GREEN report of older
    code stayed GREEN forever. Now it must be fresh, name its host and have measured the
    repository's own proxy, Harness and firewall."""
    result = _egress_repo(tmp_path, **kwargs)
    assert result["status"] == "UNKNOWN", (label, result)


def test_review_i9_the_real_egress_gate_binds_freshness_and_the_zone_code():
    gate = _egress_gate()
    assert gate["max_age_hours"] == 168
    assert set(gate["artifacts"]) == {"harness_service.py", "egress_proxy.py", "van-browser-core.nft"}
    root = GATE_MODEL.parents[1]
    assert all((root / source).is_file() for source in gate["artifacts"].values())
    qualify = (root / "deploy/van-browser-core/qualify.sh").read_text(encoding="utf-8")
    assert '"generated_at_utc"' in qualify and '"host"' in qualify and '"artifacts"' in qualify
    for name in gate["artifacts"]:
        assert f'"{name}=' in qualify, name


@pytest.mark.parametrize("missing", ["max_age_hours", "artifacts"])
def test_review_i9_a_qualify_gate_without_freshness_or_artifacts_is_a_model_error(tmp_path, missing):
    gate = dict(_egress_gate())
    gate.pop(missing)
    assert _egress_repo(tmp_path, gate=gate)["status"] != "GREEN"
