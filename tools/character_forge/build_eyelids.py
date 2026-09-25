#!/usr/bin/env python3
"""The core rig's upper eyelids: Candidate B's own lid skin, painted where her open eyes are.

Candidate B is drawn with her eyes open, so a blink needs a lid that was never painted. A flat
vector lid read as a sticker. Instead each eye opening (and its lash ring) is inpainted by the
pinned big-lama model from the skin around it in the approved art, the same model and pinning
as the layers' hidden regions (CF-D-09-HYBRID). Goggle-frame pixels are kept out of its context
so no rim bleeds into the skin. The lid is drawn beneath the lens layer, so the lens tint is
taken back off, exactly as for the face layer under the lens.

Her left eye is ringed by the goggle frame on three sides, so the model sees almost no skin
there and painted eye and strand remnants. The left lid is therefore the right lid's painted
skin mirrored across the face, aligned on the two iris centres, and cut to the left opening.

Writes ``02-ai-working/rig/eyelid_{l,r}.png`` and ``EYELIDS.json`` (model hash, placement).
The rig generator reads these; it never needs torch.

    VAN_FORGE_LAMA=/path/big-lama.pt python3 -m tools.character_forge.build_eyelids
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

from . import underlap_fill

ROOT = Path(__file__).resolve().parents[2]
LAYER_SET = ROOT / "visual-authority" / "character-forge" / "06-raster-clean" / "candidate_b_front"
FEATURES = ROOT / "visual-authority" / "character-forge" / "03-masks" / "candidate_b_front_features.json"
OUT_DIR = ROOT / "visual-authority" / "character-forge" / "02-ai-working" / "rig"
#: How far (native px) past the eye opening the lid reaches: over the lash line, and no further
#: (a wider hole let a hair strand smear into the skin). The lid also covers every pixel of the
#: eye's own layers (sclera, iris, lashes), so no lash tip shows past a closed lid.
LID_GROW = 2
#: Context window (native px) around the opening the model paints from.
CONTEXT = 30
#: Ring (native px) outside the lid whose skin the lid's colour is blended to.
BLEND_RING = 2
EYE_PARTS = ("sclera", "eye", "lid")
#: Darker than this (luma, beneath the lens) is liner or lash, not skin.
SKIN_MIN_LUMA = 0.36
#: How far (native px) outside the eye the liner reaches.
LINER_PX = 3
#: Frame or hair pixels over an eye darker than this (luma) are the open eye's lashes.
STRAY_MAX_LUMA = 0.5
#: Size (native px) of the closing that evens out the lens alpha over the eyes.
LENS_CLOSE = 7


def _layer(manifest: dict, name: str, shape) -> np.ndarray:
    row = next(r for r in manifest["layers"] if r["name"] == name)
    img = np.asarray(Image.open(LAYER_SET / row["file"]).convert("RGBA")).astype(np.float32) / 255.0
    plane = np.zeros(shape + (4,), np.float32)
    x, y = row["offset_px"]
    plane[y:y + img.shape[0], x:x + img.shape[1]] = img
    return plane


def _mirror_right(skin: np.ndarray, hole: np.ndarray, eyes: dict, shape) -> np.ndarray:
    """The right lid's skin mirrored onto the left eye, the iris centres mapped onto each other."""
    left, right = eyes["l"]["iris"], eyes["r"]["iris"]
    yy, xx = np.mgrid[0:shape[0], 0:shape[1]].astype(np.float32)
    sx = left["cx"] + right["cx"] - xx
    sy = yy - left["cy"] + right["cy"]
    # Only the lid's interior is sampled (its rim continues the right eye's own liner), spread
    # outward first, so bilinear taps at its edge never pick up the open eye around it.
    _, (iy, ix) = ndimage.distance_transform_edt(~ndimage.binary_erosion(hole, iterations=3), return_indices=True)
    filled = skin[iy, ix]
    return np.stack([ndimage.map_coordinates(filled[..., c], [sy, sx], order=1, mode="nearest") for c in range(3)], -1)


def _blend_to_ring(lid: np.ndarray, hole: np.ndarray, target: np.ndarray, ring: np.ndarray) -> np.ndarray:
    """Seamless blend: the lid's colour offset from the skin on ``ring``, relaxed smoothly inside.

    The offset is fixed on the ring pixels and solved as a membrane (Laplace) over the lid, so the
    lid meets the surrounding skin exactly at its edge and keeps its own shading inside.
    """
    region = hole | ring
    ys, xs = np.nonzero(region)
    y0, y1, x0, x1 = ys.min() - 1, ys.max() + 2, xs.min() - 1, xs.max() + 2
    reg, fixed = region[y0:y1, x0:x1], ring[y0:y1, x0:x1]
    _, (iy, ix) = ndimage.distance_transform_edt(~hole, return_indices=True)
    ext = lid[iy, ix][y0:y1, x0:x1]
    offset = np.where(fixed[..., None], target[y0:y1, x0:x1] - ext, 0.0)
    offset[~fixed] = (target[y0:y1, x0:x1][fixed] - ext[fixed]).mean(0)
    free = reg & ~fixed
    w = reg.astype(np.float32)
    for _ in range(2000):
        pad = np.pad(offset * w[..., None], ((1, 1), (1, 1), (0, 0)))
        wp = np.pad(w, 1)
        num = pad[:-2, 1:-1] + pad[2:, 1:-1] + pad[1:-1, :-2] + pad[1:-1, 2:]
        den = wp[:-2, 1:-1] + wp[2:, 1:-1] + wp[1:-1, :-2] + wp[1:-1, 2:]
        offset[free] = (num / np.maximum(den, 1.0)[..., None])[free]
    out = lid.copy()
    out[y0:y1, x0:x1] += np.where(hole[y0:y1, x0:x1, None], offset, 0.0)
    return np.clip(out, 0.0, 1.0)


def build(out_dir: Path = OUT_DIR, model: Path | None = None) -> dict:
    manifest = json.loads((LAYER_SET / "LAYERS.json").read_text(encoding="utf-8"))
    feats = json.loads(FEATURES.read_text(encoding="utf-8"))
    source = ROOT / manifest["source"]
    src = np.asarray(Image.open(source).convert("RGBA")).astype(np.float32) / 255.0
    shape = src.shape[:2]
    lens = _layer(manifest, "visor_lens", shape)
    a = lens[..., 3:4]
    # The approved art beneath the lens (its tint taken back off), which the lid sits into.
    base = np.clip((src[..., :3] - a * lens[..., :3]) / np.maximum(1.0 - a, 1e-6), 0.0, 1.0)
    # The lens layer's alpha dips where the open eye's lashes were; a closed lid must look like
    # skin behind an even lens, so the lid is seen through the lens with those dips closed, and
    # its stored colour is pre-compensated for the real lens drawn over it.
    lens_even = ndimage.grey_closing(lens[..., 3], size=(LENS_CLOSE, LENS_CLOSE))[..., None]
    _, (iy, ix) = ndimage.distance_transform_edt(lens[..., 3] < 0.05, return_indices=True)
    lens_rgb = lens[..., :3][iy, ix]
    frame_rgba = _layer(manifest, "visor_frame", shape)
    hair_rgba = _layer(manifest, "hair", shape)
    frame, hair = frame_rgba[..., 3] > 0, hair_rgba[..., 3] > 0
    # Skin only: no liner or lash (dark), no goggle glow (blue), so neither is continued.
    lum = base @ np.array([0.299, 0.587, 0.114], np.float32)
    skinlike = (src[..., 3] > 0.99) & (lum > SKIN_MIN_LUMA) & (base[..., 0] > base[..., 2] + 0.08)
    inpaint = underlap_fill.Inpainter(model or underlap_fill.DEFAULT_MODEL)
    out_dir.mkdir(parents=True, exist_ok=True)
    record = {"model": underlap_fill.MODEL_NAME, "model_sha256": underlap_fill.MODEL_SHA256,
              "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "lid_grow_px": LID_GROW, "lids": {}}
    holes: dict[str, np.ndarray] = {}
    parts_of: dict[str, np.ndarray] = {}
    for side in ("r", "l"):
        mask = Image.new("L", (shape[1], shape[0]), 0)
        ImageDraw.Draw(mask).polygon([tuple(p) for p in feats["eyes"][side]["opening"]], fill=1, outline=1)
        parts = np.zeros(shape, bool)
        for part in EYE_PARTS:
            parts |= _layer(manifest, f"{part}_{side}", shape)[..., 3] > 0
        parts_of[side] = parts
        hole = ndimage.binary_dilation(np.asarray(mask, bool), iterations=LID_GROW) | parts
        # The liner hugging the eye goes with it: dark pixels just outside are covered too.
        hole |= ndimage.binary_dilation(hole, iterations=LINER_PX) & ~skinlike & ~frame & ~hair
        # One smooth outline, not a ragged pixel edge.
        holes[side] = ndimage.binary_fill_holes(ndimage.binary_closing(hole, iterations=2))
    eye_parts = holes["l"] | holes["r"]
    skin: dict[str, np.ndarray] = {}
    for side in ("r", "l"):
        hole = holes[side]
        if side == "r":
            ys, xs = np.nonzero(hole)
            window = np.zeros(shape, bool)
            window[ys.min() - CONTEXT:ys.max() + CONTEXT, xs.min() - CONTEXT:xs.max() + CONTEXT] = True
            known = window & ~hole & ~frame & skinlike
            painted = inpaint(src[..., :3], known, hole)
            # Beneath the lens: take its (even) tint back off.
            lid = np.clip((painted - lens_even * lens_rgb) / np.maximum(1.0 - lens_even, 1e-6), 0.0, 1.0)
            skin["r"] = lid
        else:
            lid = _mirror_right(skin["r"], holes["r"], feats["eyes"], shape)
        ring = ndimage.binary_dilation(hole, iterations=BLEND_RING) & ~hole
        ring &= ~frame & ~hair & ~eye_parts & skinlike
        # The ring's colour, smoothed along it, so its pixel grain is not copied into the lid edge.
        wsum = ndimage.gaussian_filter(ring.astype(np.float32), 1.5)
        smooth = np.stack([ndimage.gaussian_filter(base[..., c] * ring, 1.5) for c in range(3)], -1)
        target = smooth / np.maximum(wsum, 1e-6)[..., None]
        lid = _blend_to_ring(lid, hole, target, ring)
        # A soft edge (two pixels) so the lid sits into the skin rather than on it.
        alpha = np.clip(ndimage.gaussian_filter(hole.astype(np.float32), 1.0) * 1.4, 0.0, 1.0)
        alpha[hole] = 1.0
        alpha[~ndimage.binary_dilation(hole, iterations=2)] = 0.0
        _, (iy, ix) = ndimage.distance_transform_edt(~hole, return_indices=True)
        lid = lid[iy, ix]
        seen = lid * (1.0 - lens_even) + lens_rgb * lens_even
        stored = np.clip((seen - a * lens_rgb) / np.maximum(1.0 - a, 1e-6), 0.0, 1.0)
        hy, hx = np.nonzero(alpha > 0)
        y0, y1, x0, x1 = hy.min(), hy.max() + 1, hx.min(), hx.max() + 1
        tile = np.concatenate([stored[y0:y1, x0:x1], alpha[y0:y1, x0:x1, None]], -1)
        path = out_dir / f"eyelid_{side}.png"
        Image.fromarray((tile * 255 + 0.5).astype(np.uint8), "RGBA").save(path, format="PNG", optimize=True)
        entry = {"method": "big-lama" if side == "r" else "mirror_of_r", "file": path.name,
                 "offset_px": [int(x0), int(y0)], "size_px": [int(x1 - x0), int(y1 - y0)],
                 "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        # The goggle-frame and hair layers carry a few lash pixels of the open eye (dark, never
        # blue or strand-white); drawn in front of the lid they would stay as specks. A patch of
        # the lid seen through the lens is drawn in front of them, over exactly those pixels.
        stray = np.zeros(shape, np.float32)
        for plane in (frame_rgba, hair_rgba):
            pl = plane[..., :3] @ np.array([0.299, 0.587, 0.114], np.float32)
            dark = (plane[..., 3] > 0) & (pl < STRAY_MAX_LUMA) & (plane[..., 0] > plane[..., 2])
            stray = np.maximum(stray, np.where(dark & hole, plane[..., 3], 0.0))
        if stray.any():
            sy, sx = np.nonzero(stray > 0)
            v0, v1, u0, u1 = sy.min(), sy.max() + 1, sx.min(), sx.max() + 1
            over = np.concatenate([seen[v0:v1, u0:u1], stray[v0:v1, u0:u1, None]], -1)
            opath = out_dir / f"eyelid_{side}_over.png"
            Image.fromarray((over * 255 + 0.5).astype(np.uint8), "RGBA").save(opath, format="PNG", optimize=True)
            entry["over"] = {"file": opath.name, "offset_px": [int(u0), int(v0)], "size_px": [int(u1 - u0), int(v1 - v0)],
                             "pixels": int((stray > 0).sum()), "sha256": hashlib.sha256(opath.read_bytes()).hexdigest()}
        # The frame layer also holds the open eye's liner ring. Scaled on a phone, that ring's
        # soft edge lets the sclera's white beneath show as a pale line round the eye; while the
        # eye is open, her own final pixels there (a pixel wider) are drawn in front of it.
        ring = ndimage.binary_dilation(frame & ndimage.binary_dilation(parts_of[side], iterations=1), iterations=1)
        if ring.any():
            cy_, cx_ = np.nonzero(ring)
            v0, v1, u0, u1 = cy_.min(), cy_.max() + 1, cx_.min(), cx_.max() + 1
            cover = np.concatenate([src[v0:v1, u0:u1, :3], ring[v0:v1, u0:u1, None].astype(np.float32)], -1)
            cpath = out_dir / f"eye_cover_{side}.png"
            Image.fromarray((cover * 255 + 0.5).astype(np.uint8), "RGBA").save(cpath, format="PNG", optimize=True)
            entry["cover"] = {"file": cpath.name, "offset_px": [int(u0), int(v0)], "size_px": [int(u1 - u0), int(v1 - v0)],
                              "pixels": int(ring.sum()), "sha256": hashlib.sha256(cpath.read_bytes()).hexdigest()}
        record["lids"][side] = entry
    (out_dir / "EYELIDS.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
