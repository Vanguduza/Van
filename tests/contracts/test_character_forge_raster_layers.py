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
                 "visor_lens", "orb_shell", "orb_core", "boot_l", "boot_r", "brow_l", "brow_r",
                 "mouth", "lid_l", "lid_r", "sclera_l", "sclera_r"}
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


def test_the_lint_passes_the_built_set_and_catches_tampering(built, tmp_path) -> None:
    import shutil

    from tools.character_forge.raster_lint import lint_raster_set

    out, _ = built
    report = lint_raster_set(out)
    assert report.ok, report.findings
    assert report.metrics["recomposite_max_error_outside_lens"] == 0
    tampered = tmp_path / "tampered"
    shutil.copytree(out, tampered)
    # The top layer, so the changed pixel is visible in the composite.
    face = next(tampered.glob("*_orb_core.png"))
    img = Image.open(face).convert("RGBA")
    px = np.asarray(img).copy()
    ys, xs = np.nonzero(px[..., 3] == 255)
    px[ys[0], xs[0], :3] = 255 - px[ys[0], xs[0], :3]
    Image.fromarray(px).save(face)
    findings = lint_raster_set(tampered).findings
    assert "LAYER_HASH_MISMATCH:orb_core" in findings
    assert any(f.startswith("RECOMPOSITE_NOT_EXACT") for f in findings)


def test_hidden_regions_come_from_the_committed_ai_fills(built) -> None:
    # A layer that fell back to propagation means the cut changed and the cached fills in
    # 02-ai-working are stale: rebuild with --inpaint on the forge host and commit them.
    _, manifest = built
    allowed = {"big-lama", "sclera_white", "skin_rim", "lens_tint"}
    for layer in manifest["layers"]:
        if layer.get("underlap_pixels"):
            assert layer.get("underlap_fill") in allowed, (layer["name"], layer.get("underlap_fill"))
    assert manifest["underlap_fill_model"]["sha256"] == raster.underlap_fill.MODEL_SHA256


def test_the_built_lane_matches_a_fresh_build(built) -> None:
    out, manifest = built
    lane = raster.OUT_DIR
    committed = json.loads((lane / "LAYERS.json").read_text(encoding="utf-8"))
    assert committed == manifest
    for layer in manifest["layers"]:
        assert (lane / layer["file"]).read_bytes() == (out / layer["file"]).read_bytes(), layer["name"]


def test_face_features_are_bound_to_the_approved_source(tmp_path) -> None:
    feats = json.loads(raster.FEATURES.read_text(encoding="utf-8"))
    assert feats["source_sha256"] == hashlib.sha256(raster.seg.SOURCE.read_bytes()).hexdigest()
    other = tmp_path / "other.png"
    Image.new("RGBA", (593, 593)).save(other)
    with pytest.raises(ValueError):
        raster.load_features(other)


def test_a_stale_fill_is_never_used(tmp_path) -> None:
    cache = raster.underlap_fill.FillCache(tmp_path)
    hidden = np.zeros((20, 20), bool)
    hidden[5:9, 5:9] = True
    rgb = np.full((20, 20, 3), 0.5, np.float32)
    key = raster.underlap_fill.fill_key("face", rgb, ~hidden, hidden)
    painted = cache.put("face", key, np.full((20, 20, 3), 0.25, np.float32), hidden)
    assert painted is not None and abs(float(painted[6, 6, 0]) - 64 / 255) < 1e-6
    changed = hidden.copy()
    changed[10, 10] = True
    assert cache.get("face", raster.underlap_fill.fill_key("face", rgb, ~changed, changed), changed) is None
    (tmp_path / "face.png").write_bytes(b"tampered")
    assert raster.underlap_fill.FillCache(tmp_path).get("face", key, hidden) is None


def test_the_lint_refuses_unlabelled_fill(built, tmp_path) -> None:
    import shutil

    from tools.character_forge.raster_lint import lint_raster_set

    out, _ = built
    copy = tmp_path / "unlabelled"
    shutil.copytree(out, copy)
    data = json.loads((copy / "LAYERS.json").read_text(encoding="utf-8"))
    for layer in data["layers"]:
        if layer["name"] == "jacket":
            layer["underlap_fill"] = None
    (copy / "LAYERS.json").write_text(json.dumps(data), encoding="utf-8")
    assert "UNDERLAP_FILL_UNLABELLED:jacket" in lint_raster_set(copy).findings
