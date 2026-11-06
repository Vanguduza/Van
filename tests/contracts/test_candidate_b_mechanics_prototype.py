from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
PROTO = ROOT / "visual-authority" / "character-forge" / "08-prototypes" / "candidate-b-mechanics"
LOCK = ROOT / "visual-authority" / "character-forge" / "00-source" / "asset-pack" / "APPROVED_IDENTITY_LOCK.yaml"
CONTRACT = ROOT / "visual-authority" / "rive_contract.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_candidate_b_mechanics_prototype_is_identity_bound_and_noncanonical():
    receipt = json.loads((PROTO / "receipt.json").read_text(encoding="utf-8"))
    lock = yaml.safe_load(LOCK.read_text(encoding="utf-8"))
    riv = PROTO / "build" / "van_candidate_b_mechanics_proto.riv"
    assert receipt["status"] == "NON_CANONICAL_MECHANICS_PROTOTYPE"
    assert receipt["production_admissible"] is False
    assert receipt["aura_embedded"] is False
    assert receipt["candidate_b_sha256"] == lock["canonical_visual"]["sha256"]
    assert receipt["rive_sha256"] == _sha256(riv)
    assert receipt["scene_sha256"] == _sha256(PROTO / "scene.rml")


def test_candidate_b_mechanics_prototype_preserves_exact_wire_surface():
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    scene = (PROTO / "scene.rml").read_text(encoding="utf-8")
    assert 'name="Van"' in scene
    assert 'name="VanRuntime"' in scene
    for item in contract["inputs"]:
        assert f'name="{item["name"]}"' in scene
    for trigger in contract["triggers"]:
        assert f'name="{trigger}"' in scene
    assert len(contract["durable_states"]) == 18
    assert len(contract["finite_actions"]) == 14
    assert "aura" not in scene.lower()
    assert "halo" not in scene.lower()


def test_candidate_b_mechanics_donor_policy_imports_no_third_party_character_art():
    donor = yaml.safe_load((PROTO / "DONOR_MECHANICS_MANIFEST.yaml").read_text(encoding="utf-8"))
    assert donor["status"] == "NON_CANONICAL_REFERENCE_ONLY"
    assert donor["policy"]["third_party_asset_bytes_imported"] is False
    assert donor["policy"]["third_party_character_art_imported"] is False
    assert donor["policy"]["mechanics_only"] is True
    assert donor["policy"]["identity_override"] == "forbidden"
    assert donor["policy"]["aura_inside_rive"] == "forbidden"
