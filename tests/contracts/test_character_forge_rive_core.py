"""M2 — the core rig's RML is exactly what the generator writes, and speaks the contract.

The candidate `.riv` is built by the pinned Rive CLI on the forge host from the committed RML
project, and its packaging receipt binds that project by digest. What is checked here, without
the CLI: regenerating the project from the admitted layer set reproduces the committed source
byte for byte; the state machine declares exactly the contract's inputs and triggers; every
layer copy is the admitted file; and the receipt names this project and this candidate.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

from tools.character_forge import build_rive_core as core
from tools.character_forge.manifest import sha256_file, source_tree_sha256

ROOT = Path(__file__).resolve().parents[2]
WORKING = ROOT / "visual-authority" / "character-forge" / "09-rive-working"


def test_the_committed_rml_is_the_generator_output(tmp_path) -> None:
    core.build(tmp_path / "van_core")
    for name in ("rive.yaml", "scene.rml"):
        assert (tmp_path / "van_core" / name).read_bytes() == (core.PROJECT / name).read_bytes(), name


def test_the_state_machine_speaks_the_contract() -> None:
    contract = json.loads(core.CONTRACT.read_text(encoding="utf-8"))
    root = ET.parse(core.PROJECT / "scene.rml").getroot()
    board = root.find("Artboard")
    assert board.get("name") == "Van"
    machine = board.find("StateMachine")
    assert machine.get("name") == "VanRuntime"
    assert board.get("defaultStateMachineId") == machine.get("id")
    kinds = {"StateMachineNumber": "number", "StateMachineBool": "boolean"}
    inputs = [(e.get("name"), kinds[e.tag]) for e in machine if e.tag in kinds]
    assert inputs == [(i["name"], i["type"]) for i in contract["inputs"]]
    assert [e.get("name") for e in machine if e.tag == "StateMachineTrigger"] == contract["triggers"]
    assert board.find("Fill") is None  # transparent: no background, no aura


def test_layer_copies_are_the_admitted_files() -> None:
    manifest = json.loads((core.LAYER_SET / "LAYERS.json").read_text(encoding="utf-8"))
    for layer in manifest["layers"]:
        if not layer.get("empty"):
            assert sha256_file(core.PROJECT / "layers" / layer["file"]) == layer["sha256"], layer["name"]


def test_the_staged_candidate_is_receipted_against_this_project() -> None:
    staged = json.loads((ROOT / "docs" / "character_forge" / "STATUS.json").read_text(encoding="utf-8"))["core_rig"]["candidate_sha256"]
    receipts = [json.loads(p.read_text(encoding="utf-8")) for p in WORKING.glob("van_core_*.receipt.json")]
    receipt = next(r for r in receipts if r["candidate_sha256"] == staged)
    assert sha256_file(ROOT / "android" / "app" / "src" / "androidTest" / "assets" / "van_candidate.riv") == staged
    tree, count = source_tree_sha256(core.PROJECT)
    assert receipt["source_tree_sha256"] == tree and receipt["source_file_count"] == count
    assert receipt["candidate_sha256"] == sha256_file(ROOT / receipt["candidate_path"])
    assert receipt["svg_sha256"] == sha256_file(core.LAYER_SET / "LAYERS.json")
    assert receipt["stage"] == "core_rig" and receipt["authoring_version"] == "1.1.1"


def test_the_held_arm_poses_stay_inside_the_artboard() -> None:
    """POINT_TARGET and HELLO_WAVE, held: the whole arm, hand included, stays in frame."""
    manifest, _feats, pivots, _contract = core.load_inputs()
    width, height = manifest["canvas_px"]
    held = [core.POINT_POSE] + [(-1.05, elbow, 0.1) for elbow in (-1.25, -1.55, -1.7)]
    for pose in held:
        x0, x1, y0, y1 = core.arm_extent(manifest, pivots, "r", pose)
        assert core.FRAME_MARGIN <= x0 and x1 <= width - core.FRAME_MARGIN, pose
        assert core.FRAME_MARGIN <= y0 and y1 <= height - core.FRAME_MARGIN, pose


def test_the_eyelids_are_the_painted_lids_and_blink() -> None:
    record = json.loads((core.EYELIDS / "EYELIDS.json").read_text(encoding="utf-8"))
    manifest = json.loads((core.LAYER_SET / "LAYERS.json").read_text(encoding="utf-8"))
    assert record["source_sha256"] == sha256_file(ROOT / manifest["source"])
    root = ET.parse(core.PROJECT / "scene.rml").getroot()
    images = {e.get("name"): e for e in root.iter("Image")}
    assets = {e.get("name"): e for e in root.iter("ImageAsset")}
    for side, lid in record["lids"].items():
        for name, row in ((f"eyelid_{side}", lid), (f"eyelid_over_{side}", lid.get("over")),
                          (f"eye_cover_{side}", lid.get("cover"))):
            if row is None:
                continue
            assert sha256_file(core.EYELIDS / row["file"]) == row["sha256"], name
            assert sha256_file(core.PROJECT / "layers" / row["file"]) == row["sha256"], name
            assert assets[name].get("file") == "layers/" + row["file"]
            assert images[name].get("assetId") == assets[name].get("id")
    # Both lids close in the blink loop.
    blink = next(a for a in root.iter("LinearAnimation") if a.get("name") == "blink")
    closes = [k for k in blink.iter() if k.tag.startswith("KeyFrame") and k.get("value") == "1"]
    assert closes, "the blink never closes a lid"
