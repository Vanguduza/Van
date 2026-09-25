"""The M1 lane candidate builder: blockout topology kept, lock-clean, and never admitted.

The candidate is traced from the native Candidate B cut-out. What must hold regardless of how
good the trace looks is structural: every blockout group, in the blockout's stacking order
(the rig depends on it), plus per-arm accent layers directly above their arm segment; nothing
the lint refuses; output only in the lane directory; and no path that would promote it.
"""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from tools.character_forge import build_layer_candidate as builder
from tools.character_forge.svg_lint import lint_svg

vtracer = pytest.importorskip("vtracer")


@pytest.fixture(scope="module")
def candidate(tmp_path_factory) -> tuple[Path, dict]:
    out = tmp_path_factory.mktemp("m1") / "van_layers_traced_candidate.svg"
    return out, builder.build(out)


def _group_ids(path: Path) -> list[str]:
    root = ET.parse(path).getroot()
    return [g.attrib["id"] for g in root if g.tag.endswith("g")]


def test_the_blockout_topology_and_order_are_kept(candidate) -> None:
    out, _ = candidate
    blockout = _group_ids(builder.BLOCKOUT)
    produced = _group_ids(out)
    assert [g for g in produced if g not in builder.ARM_ACCENTS] == blockout
    for accent in builder.ARM_ACCENTS:
        arm = accent.removeprefix("extra_accents_cyan_")
        assert produced.index(accent) == produced.index(arm) + 1


def test_the_candidate_passes_the_static_lint(candidate) -> None:
    out, result = candidate
    report = lint_svg(out, require_geometry=False)
    assert report.findings == [], report.findings
    assert result["total_numeric_nodes"] <= report.metrics["hard_total_numeric_nodes"]


def test_every_visible_layer_is_traced_and_only_hidden_parts_stay_primitive(candidate) -> None:
    _, result = candidate
    primitive = {g for g, r in result["groups"].items() if r["source"] == "blockout_primitive"}
    # Hidden-in-neutral parts and rig helpers by design; the rest had no pixels to trace.
    allowed = builder.PRIMITIVE_ONLY | {"extra_face_shadow", "extra_jaw", "mouth_upper",
                                        "mouth_lower", "extra_catchlight_l", "extra_catchlight_r"}
    assert primitive <= allowed, primitive - allowed
    for core in ("hair", "face", "jacket", "orb_shell", "hand_l", "hand_r", "visor_frame"):
        assert result["groups"][core]["source"] == "traced"


def test_it_writes_a_lane_candidate_and_says_so() -> None:
    assert builder.OUT_DIR.name == "05-vectors-candidate"
    text = (Path(builder.__file__)).read_text(encoding="utf-8")
    assert "vectors admit" in text and "06-vectors-clean" not in text.split('"""', 2)[2]
