"""The Rive reference pack must stay traceable to Candidate B (CF-D-05-REV2_1) and in step with
the code and specs it summarises."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from tools.character_forge import build_reference_pack as pack
from tools.character_forge import proportions
from tools.character_forge.svg_lint import REQUIRED_GROUPS, lint_svg

ASSET_PACK = pack.ROOT / "visual-authority" / "character-forge" / "00-source" / "asset-pack"
CONTRACT = json.loads((pack.ROOT / "visual-authority" / "rive_contract.json").read_text(encoding="utf-8"))


def _yaml(name: str):
    return yaml.safe_load((pack.PACK / name).read_text(encoding="utf-8"))


def test_every_pack_file_matches_the_manifest_and_the_authority_board():
    assert pack.check() == []


def test_aura_table_is_what_the_shipping_code_says():
    committed = _yaml("AURA_STATE_TABLE.yaml")
    fresh = pack.aura_table()
    assert committed["states"] == fresh["states"], "VanAuraSpec/VanStatusPalette changed: rebuild the reference pack"
    assert committed["constants"] == fresh["constants"]
    assert set(committed["states"]) == set(CONTRACT["durable_states"])


def test_overlay_composition_matches_visual_authority():
    committed = _yaml("OVERLAY_COMPOSITION.yaml")
    fresh = pack.overlay_spec()
    for key, value in fresh.items():
        assert committed[key] == value, key
    assert committed["resting_avatar_dp"] * 1.70 <= committed["resting_hit_dp"]


def test_blockout_is_lint_clean_and_carries_the_full_layer_topology():
    svg = pack.PACK / "blockout" / "van_layers_blockout.svg"
    report = lint_svg(svg, require_geometry=False)
    assert report.ok, report.findings
    text = svg.read_text(encoding="utf-8")
    layer_spec = yaml.safe_load((ASSET_PACK / "LAYER_SPEC.yaml").read_text(encoding="utf-8"))
    for group in list(REQUIRED_GROUPS) + list(layer_spec["required_for_m2_extra_groups"]):
        assert f'id="{group}"' in text, group
    for forbidden in layer_spec["explicitly_forbidden_groups"]:
        assert f'id="{forbidden}"' not in text, forbidden
    assert "NOT admitted art" in text


def test_every_contract_state_and_action_has_references_or_an_explicit_gap():
    ref_map = _yaml("STATE_ACTION_REFERENCE_MAP.yaml")
    assert {k: v["code"] for k, v in ref_map["states"].items()} == CONTRACT["durable_states"]
    assert {k: v["code"] for k, v in ref_map["actions"].items()} == CONTRACT["finite_actions"]
    for row in list(ref_map["states"].values()) + list(ref_map["actions"].values()):
        assert row["references"] or row.get("gap")
        for ref in row["references"]:
            assert (pack.ROOT / ref).is_file(), ref


def test_measured_palette_keeps_the_lock_inside_its_own_tolerance():
    palette = _yaml("PALETTE_MEASURED.yaml")
    lock = yaml.safe_load((ASSET_PACK / "APPROVED_IDENTITY_LOCK.yaml").read_text(encoding="utf-8"))["identity"]
    assert palette["identity_lock_tokens"]["skin"] == lock["skin"]["canonical_token"]
    assert palette["checks_delta_e2000"]["lock_skin_vs_measured_mid"] <= lock["skin"]["render_delta_e2000_max"]


def test_pack_references_only_the_approved_authority():
    index = json.loads((pack.PACK / "REFERENCE_INDEX.json").read_text(encoding="utf-8"))
    assert index["authority"]["path"] == "visual-authority/character-forge/01-master-candidates/van_master_source_candidate_b.png"
    assert all("/production-v3/" not in crop["file"] for crop in index["crops"]), "off-model sheets are never cropped into the pack"
    deny = yaml.safe_load((ASSET_PACK / "LEGACY_ASSET_DENYLIST.yaml").read_text(encoding="utf-8"))["paths"]
    blob = json.dumps(index) + (pack.PACK / "README.md").read_text(encoding="utf-8")
    for path in deny:
        assert path not in blob, path


def test_crops_regenerate_byte_identically_from_the_board():
    PIL = pytest.importorskip("PIL.Image")
    board = PIL.open(pack.BOARD).convert("RGB")
    index = json.loads((pack.PACK / "REFERENCE_INDEX.json").read_text(encoding="utf-8"))
    for crop in index["crops"]:
        expected = PIL.open(pack.ROOT / crop["file"]).convert("RGB")
        assert board.crop(tuple(crop["board_box"])).tobytes() == expected.tobytes(), crop["file"]


def test_candidate_b_landmarks_keep_the_locked_head_count():
    data = _yaml("PROPORTIONS.yaml")
    lm = data["landmarks_board_px"]
    measured = proportions.head_count(lm["hair_crown"], lm["chin"], lm["sole"])
    low, high = proportions.locked_range()
    assert low <= measured <= high
    assert data["within_lock"] is True and data["head_count"] == round(measured, 2)
    lock = yaml.safe_load((ASSET_PACK / "APPROVED_IDENTITY_LOCK.yaml").read_text(encoding="utf-8"))["identity"]
    assert abs(data["orb_diameter_over_head_height"] - lock["companion"]["size_heads"]) <= 0.05


def test_state_action_map_marks_supporting_sheets_as_semantic_only():
    ref_map = _yaml("STATE_ACTION_REFERENCE_MAP.yaml")
    assert ref_map["reference_policy"].startswith("OFF_MODEL_SEMANTIC_ONLY")
    assert ref_map["on_model_reference"] == json.loads((pack.PACK / "REFERENCE_INDEX.json").read_text(encoding="utf-8"))["authority"]["path"]
