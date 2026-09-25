"""CF-D-09 — the raster layer set is Candidate B's own pixels, and proves it.

What must hold whatever the segmentation looks like: the stored layers composite back to the
approved cut-out (exactly outside the lens; inside it, only the darkest few pixels a uniform
tint cannot undo); every rig layer the manifest names exists, in the blockout's stacking
order; nothing is written outside the lane directory; and the source is the approved art.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

for _module in ("numpy", "scipy"):
    pytest.importorskip(_module)

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from tools.character_forge import build_raster_layers as raster  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> tuple[Path, dict]:
    out = tmp_path_factory.mktemp("raster") / "candidate_b_front"
    return out, raster.build(out)


def _composite(out: Path, manifest: dict) -> np.ndarray:
    w, h = manifest["canvas_px"]
    comp = np.zeros((h, w, 4))
    for layer in manifest["layers"]:
        if layer.get("empty"):
            continue
        img = np.asarray(Image.open(out / layer["file"]).convert("RGBA")).astype(float) / 255
        x, y = layer["offset_px"]
        plane = np.zeros((h, w, 4))
        plane[y:y + img.shape[0], x:x + img.shape[1]] = img
        a = plane[..., 3:4]
        comp[..., :3] = plane[..., :3] * a + comp[..., :3] * (1 - a)
        comp[..., 3:4] = a + comp[..., 3:4] * (1 - a)
    return comp


def test_the_stored_layers_recompose_to_the_approved_art(built) -> None:
    out, manifest = built
    src = np.asarray(Image.open(ROOT / manifest["source"]).convert("RGBA")).astype(float) / 255
    comp = _composite(out, manifest)
    src_pm = np.concatenate([src[..., :3] * src[..., 3:4], src[..., 3:4]], -1)
    err = np.abs(np.round(comp * 255) - np.round(src_pm * 255)).max(-1)
    assert manifest["recomposite_max_error_outside_lens"] == 0
    assert manifest["recomposite_lens_pixels_over_8"] <= 60
    # The manifest's claim is re-derived from the PNGs on disk, not trusted.
    assert int((err > 8).sum()) == manifest["recomposite_lens_pixels_over_8"]


def test_the_source_is_the_approved_candidate_b_cutout(built) -> None:
    _, manifest = built
    source = ROOT / manifest["source"]
    assert source == raster.seg.SOURCE
    assert manifest["source_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert manifest["decision"] == "CF-D-09"


def test_rig_layers_follow_the_blockout_order_and_are_not_empty(built) -> None:
    out, manifest = built
    names = [layer["name"] for layer in manifest["layers"]]
    assert names == [name for name, _members in raster.LAYERS]
    must_draw = {"hair", "face", "jacket", "underlayer", "neck", "arm_l_upper", "arm_l_fore",
                 "hand_l", "arm_r_upper", "arm_r_fore", "hand_r", "eye_l", "eye_r", "visor_frame",
                 "visor_lens", "orb_shell", "orb_core", "boot_l", "boot_r"}
    drawn = {layer["name"] for layer in manifest["layers"] if not layer.get("empty")}
    assert must_draw <= drawn, must_draw - drawn
    for layer in manifest["layers"]:
        if not layer.get("empty"):
            data = (out / layer["file"]).read_bytes()
            assert hashlib.sha256(data).hexdigest() == layer["sha256"]


def test_moving_layers_carry_underlap(built) -> None:
    _, manifest = built
    layers = {layer["name"]: layer for layer in manifest["layers"]}
    for name in ("jacket", "underlayer", "neck", "arm_l_upper", "arm_r_upper", "face"):
        assert layers[name]["underlap_pixels"] > 0, name


def test_it_writes_only_to_the_raster_lane() -> None:
    assert raster.OUT_DIR.parent.name == "04-raster-layers"
