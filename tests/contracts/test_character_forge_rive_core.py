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

import pytest

pytest.importorskip("PIL")  # lid colours are sampled from the art; a forge-host dependency

from tools.character_forge import build_rive_core as core  # noqa: E402
from tools.character_forge.manifest import sha256_file, source_tree_sha256  # noqa: E402

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


def test_the_receipt_binds_this_project_and_candidate() -> None:
    receipt = json.loads((WORKING / "van_core_01.receipt.json").read_text(encoding="utf-8"))
    tree, count = source_tree_sha256(core.PROJECT)
    assert receipt["source_tree_sha256"] == tree and receipt["source_file_count"] == count
    assert receipt["candidate_sha256"] == sha256_file(ROOT / receipt["candidate_path"])
    assert receipt["svg_sha256"] == sha256_file(core.LAYER_SET / "LAYERS.json")
    assert receipt["stage"] == "core_rig" and receipt["authoring_version"] == "1.1.1"
