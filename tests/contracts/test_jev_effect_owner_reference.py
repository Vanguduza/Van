"""Review I4 MINOR-B — the Jev browser effect gate must not be satisfiable by plain-text edits.

Probe ``review-i4/probes/jev_spoof.py``: three edits to ``VAN-JEV-BROWSER-EFFECT-001.yaml``
(``owner_signature_status: SIGNED``, ``status: OWNER_APPROVED_EFFECT`` and an
``owner_decision_reference`` naming a docs/decisions/OWNER-DECISIONS-*.md file that does not
exist) made the ``jev_browser_effect`` capability GREEN, because the gate checked only the
reference's shape. The gate is now an ``owner_reference`` gate: the reference must resolve to
an existing file, the record must pin that file's sha256, and it must name an existing,
unrevoked OWNER_EXPLICIT Project Truth authorization record for that file.

These run against copies of the *real* registry, decision records and authorization records,
so they fail if the committed gate model is loosened again.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

import yaml

from van_gateway.automation import production_gates

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "registries" / "production_activation_gates.json"
JEV = "VAN-JEV-BROWSER-EFFECT-001.yaml"
K_AUTH = "auth-20260929-owner-stagehand-private-plane-gates"
MISSING_REF = "docs/decisions/OWNER-DECISIONS-20990101-DOES-NOT-EXIST.md"


def _copy_repo(tmp_path: Path) -> Path:
    for rel in ("docs/decisions", "docs/project-state/authorizations"):
        shutil.copytree(ROOT / rel, tmp_path / rel)
    (tmp_path / "registries").mkdir()
    shutil.copy(REGISTRY, tmp_path / "registries")
    # The probe also turns the inherited Harness and Security Policy decisions GREEN, so that
    # only the Jev record's own gates can hold the capability back.
    harness = tmp_path / "docs/decisions/VAN-ADOPT-BROWSER-HARNESS-001.yaml"
    data = yaml.safe_load(harness.read_text(encoding="utf-8"))
    data["owner_signature_status"] = "SIGNED"
    data.setdefault("observed_runtime", {})["pin_status"] = "PINNED_DIGEST_VERIFIED"
    harness.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    policy = tmp_path / "docs/decisions/VAN-AMEND-SECURITY-POLICY-001.md"
    policy.write_text(re.sub(r"^\*\*Status:\*\*\s*`[^`]+`", "**Status:** `OWNER_APPROVED`",
                             policy.read_text(encoding="utf-8"), count=1, flags=re.M), encoding="utf-8")
    return tmp_path


def _spoof(root: Path, *, sha: str | None = None, auth_id: str | None = None) -> None:
    path = root / "docs/decisions" / JEV
    text = path.read_text(encoding="utf-8")
    for old, new in (
        ("owner_signature_status: NOT_APPLICABLE_RECORDS_EXISTING_CAP", "owner_signature_status: SIGNED"),
        ("  status: SHADOW_ONLY", "  status: OWNER_APPROVED_EFFECT"),
        ("  owner_decision_reference: null", f"  owner_decision_reference: {MISSING_REF}"),
    ):
        assert old in text, old
        text = text.replace(old, new)
    if sha is not None:
        text = text.replace("  owner_decision_sha256: null", f'  owner_decision_sha256: "{sha}"')
    if auth_id is not None:
        text = text.replace("  owner_decision_authorization_id: null", f"  owner_decision_authorization_id: {auth_id}")
    path.write_text(text, encoding="utf-8")


def _jev(root: Path) -> tuple[dict, dict]:
    state = production_gates.evaluate_production_gates(root / "registries" / REGISTRY.name, root)
    gates = {g["gate"]: g for g in state["capability_gates"]}
    return state["capabilities"]["jev_browser_effect"], gates


def test_the_real_repository_does_not_permit_jev_effect():
    state = production_gates.evaluate_production_gates()
    cap = state["capabilities"]["jev_browser_effect"]
    assert cap["production_activation_permitted"] is False
    gates = {g["gate"]: g for g in state["capability_gates"]}
    assert (gates["jev_browser_effect"]["status"], gates["jev_browser_effect"]["raw_value"]) == ("PENDING", "SHADOW_ONLY")
    assert gates["owner_decision_reference"]["status"] == "UNKNOWN"
    assert gates["owner_decision_reference"]["kind"] == "owner_reference"


def test_the_committed_jev_reference_gate_resolves_pins_and_authorizes():
    model = json.loads(REGISTRY.read_text(encoding="utf-8"))
    entry = next(d for d in model["capability_decisions"] if d["decision"] == JEV)
    gate = next(g for g in entry["gates"] if g["id"] == "owner_decision_reference")
    assert gate["kind"] == "owner_reference"
    assert gate["reference_dir"] == "docs/decisions"
    assert gate["authorizations_dir"] == "docs/project-state/authorizations"
    assert gate["authorization_authority"] == ["OWNER_EXPLICIT"]
    # No gate anywhere in the model may reach GREEN on a pattern alone.
    for decision in model["required_decisions"] + model["capability_decisions"]:
        for g in decision["gates"]:
            assert "green_pattern" not in g or g["kind"] == "owner_reference", (decision["decision"], g["id"])


def test_probe_jev_spoof_three_text_edits_citing_a_missing_file_are_not_permitted(tmp_path):
    root = _copy_repo(tmp_path)
    _spoof(root)
    assert not (root / MISSING_REF).exists()
    cap, gates = _jev(root)
    assert cap["production_activation_permitted"] is False, cap
    assert cap["gates_not_green"] == [f"{JEV}:owner_decision_reference"]
    assert gates["owner_decision_reference"]["status"] == "UNKNOWN"


def test_spoof_citing_a_real_owner_record_and_k_authorization_is_not_permitted(tmp_path):
    """The spoof, upgraded: cite a real owner decision file with its correct sha256 and K's real
    authorization, which is for that very file. K's authorization does not authorize the Jev
    record, so the reference gate stays UNKNOWN."""
    root = _copy_repo(tmp_path)
    real = "docs/decisions/OWNER-DECISIONS-20260929-STAGEHAND-PRIVATE-PLANE.md"
    auth = json.loads((root / "docs/project-state/authorizations" / f"{K_AUTH}.json").read_text(encoding="utf-8"))
    assert auth["owner_instruction_record"] == real and auth["revoked"] is False
    sha = hashlib.sha256((root / real).read_bytes()).hexdigest()
    _spoof(root, sha=sha, auth_id=K_AUTH)
    path = root / "docs/decisions" / JEV
    path.write_text(path.read_text(encoding="utf-8").replace(MISSING_REF, real), encoding="utf-8")
    cap, gates = _jev(root)
    assert cap["production_activation_permitted"] is False, cap
    assert cap["gates_not_green"] == [f"{JEV}:owner_decision_reference"]
    assert gates["owner_decision_reference"]["reason"] == (
        f"authorization record does not authorize docs/decisions/{JEV}")


def test_spoof_with_a_mismatched_pin_is_not_permitted(tmp_path):
    root = _copy_repo(tmp_path)
    real = "docs/decisions/OWNER-DECISIONS-20260929-STAGEHAND-PRIVATE-PLANE.md"
    _spoof(root, sha="0" * 64, auth_id=K_AUTH)
    path = root / "docs/decisions" / JEV
    path.write_text(path.read_text(encoding="utf-8").replace(MISSING_REF, real), encoding="utf-8")
    cap, gates = _jev(root)
    assert cap["production_activation_permitted"] is False
    assert "sha256 mismatch" in gates["owner_decision_reference"]["reason"]
