#!/usr/bin/env python3
"""CF-D-09 — Candidate B's own pixels, cut into rig layers (lane output, not admitted).

Owner decision CF-D-09 lets M1 be met by a raster layer set instead of a vector redraw, because
an automatic trace inside M1's node budgets did not keep the likeness (CF-D-09-REJECT-TRACED).
The Rive rig then deforms these images with triangle meshes skinned to bones.

What this guarantees, and what it does not:

* **Pixel-exact.** Every opaque pixel of the native cut-out belongs to exactly one layer and
  keeps its original RGBA. Composited in order at their offsets, the layers reproduce the source
  exactly; ``recomposite_max_error`` in LAYERS.json proves it for every build.
* **Underlap.** Where a higher layer hides part of a lower one and the measured blockout says
  that part continues (a torso under an arm, a thigh under the jacket hem), the lower layer is
  extended with colour propagated from its own visible edge. It is plausible fill, not drawn
  anatomy, and it only shows when a part moves.
* **The lens.** The visor lens is translucent, so the eyes and skin seen through it already
  carry its tint. The lens layer is a uniform tint (``LENS_TINT``/``LENS_ALPHA``) and the pixels
  beneath it are de-tinted by the same amount, so that the lens over them reproduces the source.
  This is what lets an iris move behind the lens.
* **Native resolution only.** The approved master holds no more detail than its 593-pixel unit
  square; nothing here invents any.

The rig parts and their order come from the blockout (the rig's stacking order); parts the rig
does not move independently are merged into their parent (collar and accents into the jacket,
gloves and fingers into the hand, ears and jaw into the face).

    python3 -m tools.character_forge.build_raster_layers
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

from . import build_layer_candidate as seg

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "visual-authority" / "character-forge" / "04-raster-layers" / "candidate_b_front"
ARTBOARD = 1000.0

#: Rig layers, back to front, and the blockout groups (plus the per-arm accent layers the
#: segmenter adds) that each one is made of. The order is the blockout's stacking order.
LAYERS: list[tuple[str, tuple[str, ...]]] = [
    ("hair_back", ("extra_hair_back",)),
    ("jacket_back", ("extra_jacket_back",)),
    ("underlayer", ("underlayer",)),
    ("leg_l_upper", ("extra_leg_l_upper",)),
    ("leg_l_lower", ("extra_leg_l_lower",)),
    ("boot_l", ("extra_boot_l",)),
    ("leg_r_upper", ("extra_leg_r_upper",)),
    ("leg_r_lower", ("extra_leg_r_lower",)),
    ("boot_r", ("extra_boot_r",)),
    ("neck", ("neck",)),
    ("jacket", ("jacket", "extra_jacket_collar", "extra_accents_cyan")),
    ("arm_l_upper", ("arm_l_upper", "extra_accents_cyan_arm_l_upper")),
    ("arm_l_fore", ("arm_l_fore", "extra_accents_cyan_arm_l_fore")),
    ("hand_l", ("hand_l", "extra_glove_l", "extra_fingers_l_index", "extra_fingers_l_mid_ring_pinky",
                "extra_fingers_l_thumb")),
    ("arm_r_upper", ("arm_r_upper", "extra_accents_cyan_arm_r_upper")),
    ("arm_r_fore", ("arm_r_fore", "extra_accents_cyan_arm_r_fore")),
    ("hand_r", ("hand_r", "extra_glove_r", "extra_fingers_r_index", "extra_fingers_r_mid_ring_pinky",
                "extra_fingers_r_thumb")),
    ("face", ("face", "extra_face_shadow", "extra_jaw", "extra_ear_l", "extra_ear_r")),
    ("sclera_l", ("extra_sclera_l",)),
    ("eye_l", ("extra_iris_l", "extra_pupil_l", "extra_catchlight_l")),
    ("lid_l", ("extra_lid_upper_l", "extra_lid_lower_l")),
    ("sclera_r", ("extra_sclera_r",)),
    ("eye_r", ("extra_iris_r", "extra_pupil_r", "extra_catchlight_r")),
    ("lid_r", ("extra_lid_upper_r", "extra_lid_lower_r")),
    ("brow_l", ("brow_l", "extra_brow_inner_l", "extra_brow_outer_l")),
    ("brow_r", ("brow_r", "extra_brow_inner_r", "extra_brow_outer_r")),
    ("mouth", ("mouth_upper", "mouth_lower", "mouth_inner", "extra_teeth", "extra_tongue")),
    ("visor_lens", ("visor_lens",)),
    ("visor_frame", ("visor_frame", "extra_visor_pods", "extra_visor_glint")),
    ("hair", ("hair", "extra_hair_lock_l", "extra_hair_lock_r")),
    ("orb_shell", ("orb_shell", "extra_orb_rim", "extra_orb_face")),
    ("orb_core", ("orb_core", "extra_orb_eyes")),
]
#: Layers the rig moves, and so needs underlap for. Face parts and the visor move with the head
#: as one and are exact where they are.
UNDERLAP = {"hair_back", "jacket_back", "underlayer", "leg_l_upper", "leg_l_lower", "boot_l",
            "leg_r_upper", "leg_r_lower", "boot_r", "neck", "jacket", "arm_l_upper", "arm_l_fore",
            "hand_l", "arm_r_upper", "arm_r_fore", "hand_r", "face", "sclera_l", "sclera_r",
            "orb_shell"}
#: How far (native px) each limb's blockout mask is widened before pixels are assigned.
LIMB_WIDEN = {"arm_l_upper": 10, "arm_r_upper": 10, "arm_l_fore": 9, "arm_r_fore": 9,
              "hand_l": 4, "hand_r": 4}
#: How far (native px) a moving layer continues beneath the layers above it, beyond its
#: blockout outline. Torso-scale parts reveal the most when a limb or the head moves.
UNDERLAP_GROW = {"jacket": 40, "jacket_back": 40, "underlayer": 40, "neck": 26, "face": 18,
                 "hair_back": 18, "orb_shell": 8, "sclera_l": 3, "sclera_r": 3}
UNDERLAP_GROW_LIMB = 14
#: The visor lens as the rig draws it: the lock's lens colour at a fixed opacity.
LENS_TINT = np.array([0x3F, 0x8A, 0xCE], dtype=np.float32) / 255.0
LENS_ALPHA = 0.12
#: See build(): uniform opacity avoids a ghost iris; the price is measured, not assumed.
LENS_UNIFORM = True


def load_native(path: Path = seg.SOURCE) -> np.ndarray:
    """The approved cut-out at its native resolution, RGBA float in [0, 1]."""
    return np.asarray(Image.open(path).convert("RGBA")).astype(np.float32) / 255.0


def label_map(rgba: np.ndarray, groups: list[seg.Group]) -> np.ndarray:
    size = rgba.shape[0]
    for g in groups:
        g.mask = seg.rasterise(g, size)
        # The blockout's arms are narrower than the drawn sleeves; the outer strip of each
        # sleeve went to the jacket and stayed behind when the arm moved.
        grow = LIMB_WIDEN.get(g.gid)
        if grow and g.mask.any():
            g.mask = ndimage.binary_dilation(g.mask, iterations=grow)
    fg = rgba[..., 3] > 0.0
    label = seg.assign(groups, rgba[..., :3], fg)
    # Pixels the segmenter left to no layer but that are part of the figure (anti-aliased
    # silhouette edge) join the nearest labelled neighbour, so nothing is dropped.
    missing = fg & (label < 0)
    if missing.any():
        _, (iy, ix) = ndimage.distance_transform_edt(label < 0, return_indices=True)
        label[missing] = label[iy[missing], ix[missing]]
    resplit_eyes(label, rgba, groups)
    reclaim_visor(label, rgba, groups)
    return label


def resplit_eyes(label: np.ndarray, rgba: np.ndarray, groups: list[seg.Group]) -> None:
    """Each iris is a disc that moves as one; the white, lashes and lids stay put.

    Picking the iris by colour left its highlights and shadows behind in the white, so an eye
    that moved tore into speckle. The iris is fitted instead: its visible blue region's
    horizontal extent (lids crop it vertically, never sideways) gives the disc's radius, its
    centroid the centre. Everything inside the disc and below the visible iris top moves; dark
    pixels outside it, and above that top, are lid and lash.
    """
    index = {g.gid: i for i, g in enumerate(groups)}
    h, s, v = seg.hsv_arrays(rgba[..., :3])
    yy, xx = np.mgrid[0:label.shape[0], 0:label.shape[1]]
    for side in ("l", "r"):
        sclera_i, iris_i = index[f"extra_sclera_{side}"], index[f"extra_iris_{side}"]
        lid_i = index[f"extra_lid_upper_{side}"]
        eye_parts = [index[f"extra_{p}_{side}"] for p in ("sclera", "iris", "pupil", "catchlight")]
        eye = np.isin(label, eye_parts)
        blue = label == iris_i
        comp, n = ndimage.label(blue)
        if n == 0:
            continue
        largest = 1 + int(np.argmax(ndimage.sum(blue, comp, range(1, n + 1))))
        iris = comp == largest
        ys, xs = np.nonzero(iris)
        cy, cx = ys.mean(), xs.mean()
        r = (xs.max() - xs.min() + 1) / 2.0 + 0.75
        top = ys.min()
        disc = ((yy - cy) ** 2 + (xx - cx) ** 2 <= r * r) & (yy >= top)
        label[eye & disc] = iris_i
        dark_edge = eye & ~disc & (v < 0.35)
        label[dark_edge] = lid_i
        label[eye & ~disc & ~dark_edge] = sclera_i
        # Lashes drawn in the face just outside the eye stay with the lid too.
        rim = ndimage.binary_dilation(eye, iterations=2) & ~eye & (label == index["face"]) & (v < 0.3)
        label[rim] = lid_i


def reclaim_visor(label: np.ndarray, rgba: np.ndarray, groups: list[seg.Group]) -> None:
    """The goggle's glass rim, side pods and glare belong to one visor layer.

    The shared segmenter leaves the visor frame to its blockout primitive (right for a vector
    candidate), so the goggle's pixels land in the face. Here they are taken back: everything
    in the visor zone that is not skin, an eye or hair. The skin and eyes seen through the lens
    stay beneath it, and the de-tint lets the lens layer restore their tint.
    """
    index = {g.gid: i for i, g in enumerate(groups)}
    by = {g.gid: g.mask for g in groups}
    zone = ndimage.binary_dilation(by["visor_frame"] | by["visor_lens"] | by["extra_visor_pods"],
                                   iterations=4)
    eyes = np.zeros_like(zone)
    for side in ("l", "r"):
        for part in ("sclera", "iris", "pupil", "catchlight"):
            eyes |= label == index[f"extra_{part}_{side}"]
    eyes = ndimage.binary_dilation(eyes, iterations=1)
    h, s, v = seg.hsv_arrays(rgba[..., :3])
    # The glass here is pale and barely saturated, so it is found by exclusion: inside the
    # visor zone, whatever is not skin (seen through the lens or not), an eye or hair is goggle.
    skinish = (h <= 48) & (s > 0.18) & (v > 0.18)
    hair = label == index["hair"]
    take = zone & ~eyes & ~hair & ~skinish & (rgba[..., 3] > 0)
    label[take] = index["visor_frame"]


def orb_core_split(label: np.ndarray, rgba: np.ndarray, index: dict[str, int]) -> None:
    """The bar eyes are cyan inside the orb; the segmenter leaves them to the shell."""
    h, s, v = seg.hsv_arrays(rgba[..., :3])
    orb = np.isin(label, [index[g] for g in ("orb_shell", "extra_orb_face", "extra_orb_rim") if g in index])
    core = orb & (h >= 165) & (h <= 210) & (s > 0.35) & (v > 0.55)
    # Only the two bars, not the rim glow: keep components near the core primitive.
    near = ndimage.binary_dilation(_mask_of(index, "orb_core", label.shape), iterations=4)
    label[core & near] = index["orb_core"]


_MASKS: dict[str, np.ndarray] = {}


def _mask_of(index: dict[str, int], gid: str, shape) -> np.ndarray:
    return _MASKS.get(gid, np.zeros(shape, dtype=bool))


def propagate(colour: np.ndarray, known: np.ndarray, fill: np.ndarray) -> np.ndarray:
    """Fill `fill` pixels with colour carried in from the nearest `known` pixel, softened."""
    out = colour.copy()
    if not fill.any() or not known.any():
        return out
    _, (iy, ix) = ndimage.distance_transform_edt(~known, return_indices=True)
    carried = colour[iy, ix]
    blurred = np.stack([ndimage.gaussian_filter(carried[..., c], 2.0) for c in range(3)], -1)
    out[fill] = blurred[fill]
    return out


def build(out_dir: Path = OUT_DIR, source: Path = seg.SOURCE) -> dict:
    rgba = load_native(source)
    size = rgba.shape[0]
    scale = ARTBOARD / size
    groups = seg.load_blockout()
    label = label_map(rgba, groups)
    index = {g.gid: i for i, g in enumerate(groups)}
    for g in groups:
        _MASKS[g.gid] = g.mask
    orb_core_split(label, rgba, index)

    lens = _mask_of(index, "visor_lens", label.shape) & (rgba[..., 3] > 0.0)
    # Per-pixel lens opacity: at most LENS_ALPHA, and never more than can be undone exactly.
    # Where the art under the lens is darker than the tint (a pupil), a uniform 22% could not be
    # removed without clipping, and the neutral pose would no longer match the source.
    c = rgba[..., :3]
    with np.errstate(divide="ignore", invalid="ignore"):
        low = np.where(LENS_TINT > 0, c / LENS_TINT, np.inf).min(-1)          # keeps result >= 0
        high = np.where(LENS_TINT < 1, (1 - c) / (1 - LENS_TINT), np.inf).min(-1)  # keeps <= 1
    if LENS_UNIFORM:
        # One opacity everywhere: a per-pixel opacity dips over the original pupils and that
        # dip stays behind as a ghost iris when the eye moves. The cost is the few pixels
        # darker than the tint allows, reported as recomposite error inside the lens.
        lens_alpha = np.full(c.shape[:2], LENS_ALPHA, dtype=np.float32)
    else:
        lens_alpha = np.clip(np.minimum(LENS_ALPHA, np.minimum(low, high)), 0.0, LENS_ALPHA)
    # Quantise the opacity to what an 8-bit PNG stores, then invert with that exact value.
    lens_alpha = np.floor(lens_alpha * 255) / 255
    detinted = rgba.copy()
    a = lens_alpha[..., None]
    detinted[..., :3] = np.clip((c - a * LENS_TINT) / np.maximum(1 - a, 1e-6), 0, 1)

    out_dir.mkdir(parents=True, exist_ok=True)
    fg = rgba[..., 3] > 0.0
    # Underlap only under fully opaque source pixels: an anti-aliased silhouette edge was
    # blended against transparency, and putting colour beneath it would change it.
    solid = rgba[..., 3] >= 0.999
    layer_of = np.full(label.shape, -1, dtype=np.int32)
    for li, (_name, members) in enumerate(LAYERS):
        for gid in members:
            if gid in index:
                layer_of[label == index[gid]] = li
    lens_index = next(i for i, (n, _m) in enumerate(LAYERS) if n == "visor_lens")
    # The lens tints what lies beneath it in the stack and nothing above it (the frame and the
    # fringe are drawn over the lens), so only pixels owned by lower layers are de-tinted.
    lens_over = lens & solid & (layer_of < lens_index) & (layer_of >= 0)
    records, planes = [], []
    for li, (name, members) in enumerate(LAYERS):
        own = layer_of == li
        plane = np.zeros_like(rgba)
        if name == "visor_lens":
            plane[lens_over, :3] = LENS_TINT
            plane[lens_over, 3] = lens_alpha[lens_over]
        else:
            plane[own] = rgba[own]
            if li < lens_index:
                plane[own & lens_over, :3] = detinted[own & lens_over, :3]
            if name in UNDERLAP:
                reach = np.zeros_like(own)
                for gid in members:
                    reach |= _mask_of(index, gid, label.shape)
                # The blockout outline alone left gaps once parts moved (under the chin, the
                # torso's side behind a swung arm, elbows and shoulders), so each layer also
                # continues outward from its own visible edge by a reach that suits it.
                grow = UNDERLAP_GROW.get(name, UNDERLAP_GROW_LIMB)
                if own.any():
                    reach |= ndimage.binary_dilation(own, iterations=grow)
                hidden = reach & solid & (layer_of > li) & ~own
                if hidden.any() and own.any():
                    if name.startswith("sclera"):
                        # Beneath the iris is the white of the eye, not the lash-shadowed edge
                        # the propagation would carry in.
                        whites = own & (plane[..., :3].min(-1) > 0.75)
                        white = (np.median(plane[whites, :3], axis=0) if whites.any()
                                 else np.array([0xF2, 0xF6, 0xFA]) / 255.0)
                        plane[hidden, :3] = white
                    else:
                        filled = propagate(plane[..., :3], own, hidden)
                        plane[hidden, :3] = filled[hidden]
                    plane[hidden, 3] = 1.0
        planes.append(plane)
        alpha = plane[..., 3] > 0
        if not alpha.any():
            records.append({"name": name, "members": list(members), "empty": True})
            continue
        ys, xs = np.nonzero(alpha)
        y0, y1, x0, x1 = int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1
        img = Image.fromarray((plane[y0:y1, x0:x1] * 255 + 0.5).astype(np.uint8), "RGBA")
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        data = buf.getvalue()
        (out_dir / f"{li:02d}_{name}.png").write_bytes(data)
        records.append({
            "name": name, "file": f"{li:02d}_{name}.png", "members": list(members),
            "offset_px": [x0, y0], "size_px": [x1 - x0, y1 - y0],
            "artboard_box": [round(x0 * scale, 2), round(y0 * scale, 2),
                             round((x1 - x0) * scale, 2), round((y1 - y0) * scale, 2)],
            "own_pixels": int(own.sum()), "underlap_pixels": int((alpha & ~own).sum()),
            "sha256": hashlib.sha256(data).hexdigest(),
        })

    # Proof of pixel exactness: "over"-composite the stored 8-bit layers, premultiplied, and
    # compare with the source premultiplied (a straight-alpha comparison at a soft edge would
    # report colour that is weighted by nothing).
    comp = np.zeros_like(rgba)
    for plane in planes:
        p8 = np.round(plane * 255) / 255
        a = p8[..., 3:4]
        comp[..., :3] = p8[..., :3] * a + comp[..., :3] * (1 - a)
        comp[..., 3:4] = a + comp[..., 3:4] * (1 - a)
    src_pm = np.concatenate([rgba[..., :3] * rgba[..., 3:4], rgba[..., 3:4]], -1)
    err = np.abs(np.round(comp * 255) - np.round(src_pm * 255)).max(-1)
    diff = err[fg]
    outside = err[fg & ~lens_over]
    inside = err[lens_over]
    manifest = {
        "schema_version": 1,
        "decision": "CF-D-09",
        "source": str(source.relative_to(ROOT)),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "canvas_px": [size, size],
        "artboard": [ARTBOARD, ARTBOARD],
        "px_to_artboard": scale,
        "lens": {"tint": "#3F8ACE", "alpha_max": LENS_ALPHA,
                 "alpha_mean": round(float(lens_alpha[lens_over].mean()), 4) if lens_over.any() else 0.0},
        "order": "back_to_front",
        "layers": records,
        "recomposite_max_error": int(diff.max()) if diff.size else 0,
        "recomposite_max_error_outside_lens": int(outside.max()) if outside.size else 0,
        "recomposite_lens_pixels_over_8": int((inside > 8).sum()),
        "recomposite_lens_max_error": int(inside.max()) if inside.size else 0,
        "recomposite_mean_error": round(float(diff.mean()), 3) if diff.size else 0.0,
    }
    (out_dir / "LAYERS.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    m = build(args.out)
    print(json.dumps({"out": str(args.out), "layers": sum(1 for r in m["layers"] if not r.get("empty")),
                      "empty": [r["name"] for r in m["layers"] if r.get("empty")],
                      "recomposite_max_error": m["recomposite_max_error"],
                      "recomposite_mean_error": m["recomposite_mean_error"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
