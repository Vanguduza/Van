from __future__ import annotations

import json
from pathlib import Path

import yaml

from .manifest import ROOT
from .svg_lint import COLOR_GROUPS, REQUIRED_GROUPS

PACK = ROOT / "visual-authority" / "character-forge" / "00-source" / "asset-pack"


def _yaml(name: str):
    return yaml.safe_load((PACK / name).read_text(encoding="utf-8"))


def validate() -> list[str]:
    problems: list[str] = []
    contract = json.loads((ROOT / "visual-authority" / "rive_contract.json").read_text(encoding="utf-8"))
    identity = _yaml("APPROVED_IDENTITY_LOCK.yaml")
    manifest = _yaml("ASSET_PACK_MANIFEST.yaml")
    layers = _yaml("LAYER_SPEC.yaml")
    rig = _yaml("RIG_SPEC.yaml")
    matrix = _yaml("STATE_ACTION_MATRIX.yaml")
    aura = _yaml("AURA_HANDOFF_SPEC.yaml")
    deny = _yaml("LEGACY_ASSET_DENYLIST.yaml")

    primary = manifest["authority"]["primary_visual"]["path"]
    if primary != "visual-authority/assets/pack/owner_board_visual_authority.png":
        problems.append("PRIMARY_VISUAL_DRIFT")
    if not (ROOT / primary).is_file():
        problems.append("PRIMARY_VISUAL_MISSING")

    if rig["artboard"] != contract["artboard"]:
        problems.append("ARTBOARD_DRIFT")
    if rig["state_machine"] != contract["state_machine"]:
        problems.append("STATE_MACHINE_DRIFT")
    if rig["public_surface"]["inputs"] != contract["inputs"]:
        problems.append("PUBLIC_INPUT_DRIFT")
    if rig["public_surface"]["triggers"] != contract["triggers"]:
        problems.append("TRIGGER_DRIFT")

    state_codes = {name: row["code"] for name, row in matrix["states"].items()}
    action_codes = {name: row["code"] for name, row in matrix["actions"].items()}
    if state_codes != contract["durable_states"]:
        problems.append("STATE_CODE_DRIFT")
    if action_codes != contract["finite_actions"]:
        problems.append("ACTION_CODE_DRIFT")

    if tuple(layers["required_root_groups"]) != REQUIRED_GROUPS:
        problems.append("SVG_GROUP_DRIFT")
    if COLOR_GROUPS.get("hand_l") != "neutral" or COLOR_GROUPS.get("hand_r") != "neutral":
        problems.append("GLOVE_LINTER_DRIFT")
    if layers["identity_roles"]["hand_l"] != "black_technical_glove":
        problems.append("LEFT_GLOVE_DRIFT")
    if layers["identity_roles"]["hand_r"] != "black_technical_glove":
        problems.append("RIGHT_GLOVE_DRIFT")
    forbidden_groups = set(layers.get("explicitly_forbidden_groups") or [])
    if "headband" not in forbidden_groups or "extra_headband" not in forbidden_groups:
        problems.append("HEADBAND_NOT_FORBIDDEN")

    lock = contract["identity_lock"]
    expected = identity["identity"]
    checks = {
        "hair": expected["hair"]["form"],
        "skin": expected["skin"]["family"],
        "eyes": "blue",
        "visor": expected["visor"]["family"],
        "jacket": expected["clothing"]["jacket"],
        "underlayer": "charcoal_technical",
        "accents": "dial_cyan",
        "companion": expected["companion"]["type"],
    }
    for key, value in checks.items():
        if lock.get(key) != value:
            problems.append(f"IDENTITY_CONTRACT_DRIFT:{key}")
    if lock.get("headband") != "forbidden":
        problems.append("HEADBAND_CONTRACT_DRIFT")
    if lock.get("gloves") != "black_technical":
        problems.append("GLOVE_CONTRACT_DRIFT")

    if rig["artboard_policy"]["aura_in_rive_forbidden"] is not True:
        problems.append("RIVE_AURA_BOUNDARY_DRIFT")
    if aura["ownership"] != "ANDROID_NATIVE":
        problems.append("AURA_OWNERSHIP_DRIFT")

    for rel in deny["paths"]:
        if (ROOT / rel).exists():
            problems.append(f"DENYLISTED_ASSET_PRESENT:{rel}")

    serialized = yaml.safe_dump(manifest, sort_keys=False)
    for token in ("owner_visual_lock_sheet.jpg", "visual-authority/assets/derived/", "visual-authority/assets/turnaround.png"):
        if token in serialized:
            problems.append(f"LEGACY_SOURCE_REFERENCED:{token}")

    return sorted(set(problems))


def main() -> int:
    problems = validate()
    if problems:
        for item in problems:
            print(f"FAIL {item}")
        return 1
    print("APPROVED_ASSET_PACK_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
