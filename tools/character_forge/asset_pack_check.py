from __future__ import annotations

import json
from pathlib import Path
import sys

import yaml

from .manifest import ROOT
from .svg_lint import REQUIRED_GROUPS

PACK = ROOT / "visual-authority" / "character-forge" / "00-source" / "asset-pack"


def load_yaml(name: str):
    return yaml.safe_load((PACK / name).read_text(encoding="utf-8"))


def validate() -> list[str]:
    problems: list[str] = []

    contract = json.loads((ROOT / "visual-authority" / "rive_contract.json").read_text(encoding="utf-8"))
    rig = load_yaml("RIG_SPEC.yaml")
    layers = load_yaml("LAYER_SPEC.yaml")
    matrix = load_yaml("STATE_ACTION_MATRIX.yaml")
    speech = load_yaml("SPEECH_SPEC.yaml")
    manifest = load_yaml("ASSET_PACK_MANIFEST.yaml")
    gaps = load_yaml("SOURCE_GAP_REGISTER.yaml")

    if rig["artboard"] != contract["artboard"]:
        problems.append("ARTBOARD_DRIFT")
    if rig["state_machine"] != contract["state_machine"]:
        problems.append("STATE_MACHINE_DRIFT")
    if rig["public_surface"]["inputs"] != contract["inputs"]:
        problems.append("PUBLIC_INPUT_DRIFT")
    if rig["public_surface"]["triggers"] != contract["triggers"]:
        problems.append("TRIGGER_DRIFT")
    if tuple(layers["required_root_groups"]) != REQUIRED_GROUPS:
        problems.append("SVG_GROUP_DRIFT")
    if {name: row["code"] for name, row in matrix["states"].items()} != contract["durable_states"]:
        problems.append("STATE_CODE_DRIFT")
    if {name: row["code"] for name, row in matrix["actions"].items()} != contract["finite_actions"]:
        problems.append("ACTION_CODE_DRIFT")

    for name, row in matrix["actions"].items():
        duration = row["duration_ms"]
        if not isinstance(duration, int) or not 600 <= duration <= 1800:
            problems.append(f"ACTION_DURATION_OUTSIDE_CANON:{name}:{duration}")

    if list(speech["visemes"].keys()) != [0, 1, 2, 3, 4]:
        problems.append("VISEME_DRIFT")
    if not rig["artboard"]["aura_in_rive_forbidden"]:
        problems.append("AURA_BOUNDARY_DRIFT")
    if not rig["architecture"]["single_character_rig"]:
        problems.append("MULTI_RIG_DRIFT")

    source_paths: list[str] = []
    for section in ("source_art", "owner_boards", "derived_reference_only"):
        source_paths.extend(row["path"] for row in manifest[section])
    source_paths.extend(row["path"] for row in manifest["authority"]["highest"])
    source_paths.extend(row["path"] for row in manifest["authority"]["contracts"] if "path" in row)
    for rel in source_paths:
        if not (ROOT / rel).exists():
            problems.append(f"SOURCE_MISSING:{rel}")

    copied_images = list(PACK.rglob("*.png")) + list(PACK.rglob("*.jpg")) + list(PACK.rglob("*.jpeg"))
    if copied_images:
        problems.append("SOURCE_COPY_FORBIDDEN:" + ",".join(str(p.relative_to(ROOT)) for p in copied_images))

    registered = "\n".join(item["finding"] for item in gaps["register"])
    for required in (
        "turnaround.png and app_icon.png",
        "expressions.png and gestures.png",
        "command_centre.png and onboarding_hero.png",
    ):
        if required not in registered:
            problems.append(f"KNOWN_SOURCE_GAP_UNREGISTERED:{required}")

    return problems


def main() -> int:
    problems = validate()
    if problems:
        for item in problems:
            print(f"FAIL {item}")
        return 1
    print("ASSET_PACK_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
