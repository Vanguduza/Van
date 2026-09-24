from __future__ import annotations

import json
from pathlib import Path
import yaml

from tools.character_forge.asset_pack_check import PACK, validate
from tools.character_forge.svg_lint import COLOR_GROUPS, REQUIRED_GROUPS
from tools.character_forge.manifest import sha256_file

ROOT = Path(__file__).resolve().parents[2]


def y(name: str):
    return yaml.safe_load((PACK / name).read_text(encoding="utf-8"))


def test_approved_asset_pack_is_green():
    assert validate() == []


def test_public_rive_surface_is_exact():
    contract = json.loads((ROOT / "visual-authority" / "rive_contract.json").read_text(encoding="utf-8"))
    rig = y("RIG_SPEC.yaml")
    assert rig["artboard"] == contract["artboard"] == "Van"
    assert rig["state_machine"] == contract["state_machine"] == "VanRuntime"
    assert rig["public_surface"]["inputs"] == contract["inputs"]
    assert rig["public_surface"]["triggers"] == contract["triggers"]


def test_identity_authority_is_single_and_rejected_visuals_are_absent():
    manifest = y("ASSET_PACK_MANIFEST.yaml")
    assert manifest["authority"]["primary_visual"]["path"] == "visual-authority/character-forge/01-master-candidates/van_master_source_candidate_b.png"
    deny = y("LEGACY_ASSET_DENYLIST.yaml")
    assert len(deny["paths"]) >= 20
    for rel in deny["paths"]:
        assert not (ROOT / rel).exists(), rel


def test_identity_lock_closes_known_audit_conflicts():
    lock = y("APPROVED_IDENTITY_LOCK.yaml")["identity"]
    assert lock["skin"]["family"] == "medium_brown"
    assert lock["headband"]["disposition"] == "FORBIDDEN"
    assert lock["clothing"]["gloves"] == "black_technical"
    assert lock["proportions"]["head_count_target"] == 3.2
    assert lock["proportions"]["tall_realistic_proportions_forbidden"] is True
    assert lock["companion"]["type"] == "dark_orb_cyan_bar_eyes"


def test_layer_spec_matches_linter_and_gloves():
    layers = y("LAYER_SPEC.yaml")
    assert tuple(layers["required_root_groups"]) == REQUIRED_GROUPS
    assert COLOR_GROUPS["hand_l"] == COLOR_GROUPS["hand_r"] == "neutral"
    assert layers["identity_roles"]["hand_l"] == "black_technical_glove"
    assert "headband" in layers["explicitly_forbidden_groups"]
    assert "extra_headband" in layers["explicitly_forbidden_groups"]


def test_state_action_matrix_matches_contract():
    contract = json.loads((ROOT / "visual-authority" / "rive_contract.json").read_text(encoding="utf-8"))
    matrix = y("STATE_ACTION_MATRIX.yaml")
    assert {k:v["code"] for k,v in matrix["states"].items()} == contract["durable_states"]
    assert {k:v["code"] for k,v in matrix["actions"].items()} == contract["finite_actions"]
    for row in matrix["actions"].values():
        assert 600 <= row["duration_ms"] <= 1800


def test_aura_stays_out_of_rive():
    rig = y("RIG_SPEC.yaml")
    aura = y("AURA_HANDOFF_SPEC.yaml")
    assert rig["artboard_policy"]["aura_in_rive_forbidden"] is True
    assert aura["ownership"] == "ANDROID_NATIVE"
    assert aura["rive_boundary"]["full_ring_inside_riv"] == "FORBIDDEN"


def test_v3_artwork_manifest_is_hash_locked_and_reference_only():
    v3 = ROOT / "visual-authority" / "character-forge" / "00-source" / "production-v3"
    artwork = yaml.safe_load((v3 / "ARTWORK_MANIFEST.yaml").read_text(encoding="utf-8"))
    assert artwork["status"] == "HASH_LOCKED"
    selected = artwork["selected_master"]
    approved = ROOT / selected["path"]
    assert approved.is_file()
    assert sha256_file(approved) == selected["sha256"] == "42474ee9595f09f4ef59c060faf756e1db4222234b827fae0311007248b9b9e7"

    required = {
        "expression_reference",
        "viseme_reference",
        "glove_gesture_reference",
        "state_action_reference",
        "aura_reference",
    }
    by_id = {row["id"]: row for row in artwork["assets"]}
    assert required.issubset(by_id)
    for asset_id in required:
        row = by_id[asset_id]
        path = ROOT / row["path"]
        assert path.is_file(), row["path"]
        assert sha256_file(path) == row["sha256"], asset_id
        assert row["admission_class"] == "GENERATIVE_REFERENCE_ONLY"
        assert row["identity_authority"] is False


def test_v3_provenance_graph_keeps_supporting_art_below_master_authority():
    graph_path = ROOT / "visual-authority" / "character-forge" / "00-source" / "production-v3" / "PROVENANCE_GRAPH.yaml"
    graph = yaml.safe_load(graph_path.read_text(encoding="utf-8"))
    assert graph["status"] == "HASH_LOCKED"
    assert graph["nodes"]["approved_master"]["sha256"] == "42474ee9595f09f4ef59c060faf756e1db4222234b827fae0311007248b9b9e7"
    for name in ("expression_reference","viseme_reference","glove_reference","state_action_reference","aura_reference"):
        assert graph["nodes"][name]["type"] == "SUPPORTING_REFERENCE_ONLY"
    assert "approved_master_is_the_only_high_resolution_rigging_geometry_authority" in graph["invariants"]


def test_owner_approved_master_is_exact_candidate_b_binary():
    master_root = ROOT / "visual-authority" / "character-forge"
    candidate = master_root / "01-master-candidates" / "van_master_highres_v1.png"
    approved = master_root / "01-master-approved" / "van_master_highres.png"
    approval = yaml.safe_load((ROOT / "docs" / "character_forge" / "HIGHRES_MASTER_APPROVAL.yaml").read_text(encoding="utf-8"))
    expected = "42474ee9595f09f4ef59c060faf756e1db4222234b827fae0311007248b9b9e7"
    assert candidate.is_file() and approved.is_file()
    assert sha256_file(candidate) == sha256_file(approved) == expected
    assert approval["decision"] == "APPROVE"
    assert approval["authority"] == "owner"
    assert approval["candidate_sha256"] == expected
