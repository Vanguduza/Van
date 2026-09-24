"""The locked head count is measured one way everywhere, and the SVG lint enforces it."""
from __future__ import annotations

import pytest

from tools.character_forge import proportions, svg_lint
from tools.character_forge.build_reference_pack import PACK

LOCK = {"identity": {"proportions": {"head_count_definition": proportions.DEFINITION, "head_count_target": 3.2, "head_count_tolerance": 0.3}}}


def test_head_count_is_crown_to_sole_over_crown_to_chin():
    assert proportions.head_count(0, 100, 320) == pytest.approx(3.2)
    with pytest.raises(ValueError):
        proportions.head_count(100, 50, 400)
    with pytest.raises(ValueError):
        proportions.head_count(0, 100, 90)


def test_check_accepts_the_band_and_names_the_drift():
    assert proportions.check(3.2, LOCK) is None
    assert proportions.check(2.9, LOCK) is None and proportions.check(3.5, LOCK) is None
    assert proportions.check(5.75, LOCK) == "PROPORTION_OUTSIDE_LOCK:5.75_heads_not_in_2.90-3.50"


def test_locked_range_refuses_a_different_definition():
    other = {"identity": {"proportions": {**LOCK["identity"]["proportions"], "head_count_definition": "skull_to_chin"}}}
    with pytest.raises(ValueError):
        proportions.locked_range(other)


def test_repository_lock_is_compact_chibi():
    low, high = proportions.locked_range()
    assert (low, high) == pytest.approx((2.9, 3.5))


def test_svg_head_count_reads_inkscape_boxes():
    bounds = {"extra_hair_back": (0, 10, 100, 60), "hair": (0, 0, 100, 50), "face": (10, 20, 80, 80), "extra_jaw": (30, 90, 40, 10),
              "extra_boot_l": (0, 280, 40, 40)}
    assert proportions.svg_head_count(bounds) == pytest.approx(3.2)
    with pytest.raises(ValueError):
        proportions.svg_head_count({"face": (0, 0, 10, 10)})


def _bounds_for(head_count: float) -> dict:
    chin = 100.0; sole = chin * head_count
    boxes = {name: (100.0, 100.0, 50.0, 50.0) for name in svg_lint.REQUIRED_GROUPS}
    boxes["hair"] = (100.0, 0.0, 200.0, 60.0); boxes["face"] = (120.0, 30.0, 160.0, chin - 30.0)
    boxes["extra_boot_l"] = (100.0, sole - 40.0, 60.0, 40.0)
    return boxes


@pytest.mark.parametrize("heads,expect_finding", [(3.15, False), (5.75, True)])
def test_lint_flags_off_lock_proportions_when_geometry_is_verified(monkeypatch, heads, expect_finding):
    monkeypatch.setattr(svg_lint, "_inkscape_bounds", lambda _path: _bounds_for(heads))
    report = svg_lint.lint_svg(PACK / "blockout" / "van_layers_blockout.svg", require_geometry=True)
    assert report.geometry_verified
    flagged = [f for f in report.findings if f.startswith("PROPORTION_OUTSIDE_LOCK")]
    assert bool(flagged) is expect_finding, report.findings


def test_lint_reports_unmeasurable_proportions(monkeypatch):
    boxes = _bounds_for(3.2)
    boxes["hair"] = (100.0, 300.0, 10.0, 10.0)  # crown below the chin: landmarks out of order
    monkeypatch.setattr(svg_lint, "_inkscape_bounds", lambda _path: boxes)
    report = svg_lint.lint_svg(PACK / "blockout" / "van_layers_blockout.svg", require_geometry=True)
    assert any(f.startswith("PROPORTION_UNMEASURABLE") for f in report.findings), report.findings
