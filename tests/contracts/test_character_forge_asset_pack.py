from __future__ import annotations

from pathlib import Path
import json
import yaml

from tools.character_forge.svg_lint import REQUIRED_GROUPS

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "visual-authority" / "character-forge" / "00-source" / "asset-pack"


def _yaml(name: str):
    return yaml.safe_load((PACK / name).read_text(encoding="utf-8"))


def test_asset_pack_matches_public_rive_contract():
    contract = json.loads((ROOT / "visual-authority" / "rive_contract.json").read_text(encoding="utf-8"))
    rig = _yaml("RIG_SPEC.yaml")

    assert rig["artboard"] == contract["artboard"]
    assert rig["state_machine"] == contract["state_machine"]
    assert rig["public_surface"]["inputs"] == contract["inputs"]
    assert rig["public_surface"]["triggers"] == contract["triggers"]


def test_asset_pack_layer_groups_match_svg_linter():
    layers = _yaml("LAYER_SPEC.yaml")
    assert tuple(layers["required_root_groups"]) == REQUIRED_GROUPS
    assert layers["rules"]["raster_images_forbidden"] is True
    assert layers["rules"]["text_fonts_forbidden"] is True
    assert layers["rules"]["additional_root_groups_prefix"] == "extra_"


def test_asset_pack_state_action_codes_match_contract():
    contract = json.loads((ROOT / "visual-authority" / "rive_contract.json").read_text(encoding="utf-8"))
    matrix = _yaml("STATE_ACTION_MATRIX.yaml")

    assert {name: row["code"] for name, row in matrix["states"].items()} == contract["durable_states"]
    assert {name: row["code"] for name, row in matrix["actions"].items()} == contract["finite_actions"]


def test_asset_pack_core_scope_is_exact():
    rig = _yaml("RIG_SPEC.yaml")
    assert rig["core_m2"]["durable_states"] == ["IDLE", "LISTENING", "THINKING", "SPEAKING"]
    assert rig["core_m2"]["finite_actions"] == ["HELLO_WAVE", "ACK_NOD", "POINT_TARGET"]
    assert rig["architecture"]["single_character_rig"] is True
    assert rig["artboard"]["aura_in_rive_forbidden"] is True


def test_asset_pack_sources_exist_without_duplicate_copies():
    manifest = _yaml("ASSET_PACK_MANIFEST.yaml")
    paths = []
    for section in ("source_art", "owner_boards", "derived_reference_only"):
        paths.extend(row["path"] for row in manifest[section])
    paths.extend(row["path"] for row in manifest["authority"]["highest"])
    paths.extend(row["path"] for row in manifest["authority"]["contracts"] if "path" in row)

    for rel in paths:
        assert (ROOT / rel).exists(), rel

    # Rev 2 explicitly forbids copying the owner source images into 00-source.
    copied_images = list(PACK.rglob("*.png")) + list(PACK.rglob("*.jpg")) + list(PACK.rglob("*.jpeg"))
    assert copied_images == []


def test_asset_pack_speech_and_validation_requirements():
    speech = _yaml("SPEECH_SPEC.yaml")
    validation = _yaml("VALIDATION_MATRIX.yaml")
    assert list(speech["visemes"].keys()) == [0, 1, 2, 3, 4]
    assert speech["timing_authority"]["do_not_embed_tts_timing_in_rive"] is True
    assert validation["contract_surface"]["exact_public_input_count"] == 9
    assert validation["contract_surface"]["exact_trigger_count"] == 8
    assert validation["full_evidence"]["state_frames"] == 18
    assert validation["full_evidence"]["action_frames"] == 14
