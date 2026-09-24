from __future__ import annotations

import json
from pathlib import Path
import yaml

from tools.character_forge.asset_pack_check import PACK, validate
from tools.character_forge.svg_lint import COLOR_GROUPS, REQUIRED_GROUPS

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
    assert manifest["authority"]["primary_visual"]["path"] == "visual-authority/assets/pack/owner_board_visual_authority.png"
    deny = y("LEGACY_ASSET_DENYLIST.yaml")
    assert len(deny["paths"]) >= 20
    for rel in deny["paths"]:
        assert not (ROOT / rel).exists(), rel


def test_identity_lock_closes_known_audit_conflicts():
    lock = y("APPROVED_IDENTITY_LOCK.yaml")["identity"]
    assert lock["skin"]["family"] == "medium_brown"
    assert lock["headband"]["disposition"] == "FORBIDDEN"
    assert lock["clothing"]["gloves"] == "black_technical"
    assert lock["proportions"]["head_count_target"] == 5.75
    assert lock["proportions"]["three_head_chibi_forbidden"] is True


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
