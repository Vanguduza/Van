#!/usr/bin/env python3
"""CF-D-09 — Candidate B's own pixels, cut into rig layers (lane output, not admitted).

Owner decision CF-D-09 lets M1 be met by a raster layer set instead of a vector redraw, because
an automatic trace inside M1's node budgets did not keep the likeness (CF-D-09-REJECT-TRACED).
The Rive rig then deforms these images with triangle meshes skinned to bones.

What this guarantees, and what it does not:

* **Pixel-exact.** Every opaque pixel of the native cut-out belongs to exactly one layer and
  keeps its original RGBA. Composited in order at their offsets, the layers reproduce the source
  exactly; ``recomposite_max_error`` in LAYERS.json proves it for every build.
* **Cut on the painting, not the blockout.** The blockout's primitives do not sit on Candidate
  B's painted features, so the eyes (opening and iris disc), brows, mouth, sleeves, the torso
  behind the arms and where hair ends are hand-placed on the approved cut-out
  (``03-masks/candidate_b_front_features.json``, bound to its SHA-256).
* **Underlap, AI-painted (owner, 2026-09-25: a hybrid of a better cut and generative fill).**
  Where a higher layer hides part of a lower one (a torso under an arm, a thigh under the
  jacket hem), the lower layer continues beneath it, painted by an inpainting network from
  that layer's own visible pixels (``underlap_fill``). It is generated, not drawn: every layer
  records its fill method, and it only shows when a part moves.
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
from PIL import Image, ImageDraw
from scipy import ndimage

from . import build_layer_candidate as seg
from . import underlap_fill

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "visual-authority" / "character-forge" / "04-raster-layers" / "candidate_b_front"
ARTBOARD = 1000.0
#: Hand-placed eye, brow and mouth geometry for the approved cut-out (the blockout primitives do
#: not sit on Candidate B's painted features).
FEATURES = ROOT / "visual-authority" / "character-forge" / "03-masks" / "candidate_b_front_features.json"

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
            "eye_l", "eye_r", "orb_shell"}
#: How far (native px) each limb's blockout mask is widened before pixels are assigned.
LIMB_WIDEN = {"arm_l_upper": 10, "arm_r_upper": 10, "arm_l_fore": 9, "arm_r_fore": 9,
              "hand_l": 4, "hand_r": 4}
#: How far (native px) a moving layer continues beneath the layers above it, beyond its
#: blockout outline. Torso-scale parts reveal the most when a limb or the head moves.
UNDERLAP_GROW = {"jacket": 40, "jacket_back": 40, "underlayer": 40, "neck": 26, "face": 18,
                 "hair_back": 18, "orb_shell": 8, "sclera_l": 3, "sclera_r": 3,
                 # An iris continues only to its fitted disc, which is its reach already.
                 "eye_l": 0, "eye_r": 0}
#: Layers whose own visible pixels are too few to continue from, and the layer whose texture
#: their hidden part shares (the back of the hair is hair; the jacket's back is jacket).
FILL_CONTEXT = {"hair_back": "hair", "jacket_back": "jacket"}
#: Inside the eye openings the iris slides over the white, so the lens there is one opacity.
EYE_INTERIOR = ("eye_l", "eye_r", "sclera_l", "sclera_r")
TORSO = {"jacket", "jacket_back", "underlayer"}
#: Small face parts carry a rim (native px) of the skin around them. Each layer is resampled on
#: its own when the head turns, so a bare edge would show the fill painted beneath it as a
#: dashed seam; with the rim, the edge falls on skin over the same skin.
SKIN_RIM = {"mouth": 3, "brow_l": 2, "brow_r": 2}
#: How deep (native px) beneath the layers in front a fill goes, for layers that only ever show
#: a rim of it: the back of the hair around a turning head, the forehead under a swaying fringe.
#: Deeper than this is always covered, and a network asked to invent it paints mush.
REVEAL_DEPTH = {"hair_back": 26, "face": 14}
HEAD_GROUPS = ("face", "extra_jaw", "extra_ear_l", "extra_ear_r", "hair", "extra_hair_lock_l", "extra_hair_lock_r")
UNDERLAP_GROW_LIMB = 14
#: The visor lens as the rig draws it: the lock's lens colour at a fixed opacity.
LENS_TINT = np.array([0x3F, 0x8A, 0xCE], dtype=np.float32) / 255.0
LENS_ALPHA = 0.12
#: See build(): uniform opacity avoids a ghost iris; the price is measured, not assumed.
LENS_UNIFORM = True


def load_native(path: Path = seg.SOURCE) -> np.ndarray:
    """The approved cut-out at its native resolution, RGBA float in [0, 1]."""
    return np.asarray(Image.open(path).convert("RGBA")).astype(np.float32) / 255.0


def load_features(source: Path = seg.SOURCE, path: Path = FEATURES) -> dict:
    """The hand-placed face features, refused unless they were placed on this exact source."""
    feats = json.loads(path.read_text(encoding="utf-8"))
    if feats.get("source_sha256") != hashlib.sha256(source.read_bytes()).hexdigest():
        raise ValueError(f"{path.name} was placed on another source image")
    return feats


def polygon_mask(points, shape) -> np.ndarray:
    img = Image.new("L", (shape[1], shape[0]), 0)
    ImageDraw.Draw(img).polygon([(float(x), float(y)) for x, y in points], fill=1)
    return np.asarray(img, dtype=bool)


def disc_mask(circle: dict, shape) -> np.ndarray:
    yy, xx = np.mgrid[0:shape[0], 0:shape[1]]
    return (yy - circle["cy"]) ** 2 + (xx - circle["cx"]) ** 2 <= circle["r"] ** 2


def label_map(rgba: np.ndarray, groups: list[seg.Group], feats: dict | None = None) -> np.ndarray:
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
    features = apply_features(label, rgba, groups, feats if feats is not None else load_features())
    reclaim_visor(label, rgba, groups, keep=features)
    return label


def apply_features(label: np.ndarray, rgba: np.ndarray, groups: list[seg.Group], feats: dict) -> np.ndarray:
    """Cut the eyes, brows and mouth from their hand-placed geometry; return what they cover.

    Inside each eye opening, the fitted iris disc moves as one; the dark upper lash line, and
    dark pixels outside the disc, are lid; the rest is the white. Lashes drawn just outside the
    opening stay with the lid. A brow is the dark paint inside its outline (strands of hair
    that cross it stay hair), and the mouth is what is darker than the skin around it.
    Inside ``not_hair`` nothing is hair.
    """
    index = {g.gid: i for i, g in enumerate(groups)}
    _h, _s, v = seg.hsv_arrays(rgba[..., :3])
    shape = label.shape
    fg = rgba[..., 3] > 0.0
    rows = np.mgrid[0:shape[0], 0:shape[1]][0]
    covered = np.zeros(shape, dtype=bool)
    # No hair is painted inside the face below the goggle's top edge; what the colour segmenter
    # put in the hair there (the cut-out's pale silhouette fringe, lens-tinted skin) goes to
    # the nearest layer that is not hair.
    stray = polygon_mask(feats["not_hair"], shape) & (label == index["hair"])
    other = (label >= 0) & (label != index["hair"])
    if stray.any() and other.any():
        _, (iy, ix) = ndimage.distance_transform_edt(~other, return_indices=True)
        label[stray] = label[iy[stray], ix[stray]]
    hair = label == index["hair"]
    # Sleeves: inside each hand-placed outline, what the segmenter gave the torso or the other
    # arm segments belongs to that arm segment.
    body = np.isin(label, [index[g] for g in index if g.startswith(("jacket", "extra_jacket", "underlayer", "arm_", "extra_accents"))])
    for gid, outline in feats.get("sleeves", {}).items():
        sleeve = polygon_mask(outline, shape) & fg & body
        label[sleeve] = index[gid]
        _MASKS[gid] = _MASKS.get(gid, np.zeros(shape, dtype=bool)) | sleeve
    for side in ("l", "r"):
        eye = feats["eyes"][side]
        opening = polygon_mask(eye["opening"], shape) & fg
        disc = disc_mask(eye["iris"], shape)
        dark = v < 0.30
        edge = opening & ~ndimage.binary_erosion(opening, iterations=4)
        upper = rows < eye["iris"]["cy"] - 0.4 * eye["iris"]["r"]
        lid = opening & dark & (~disc | (edge & upper))
        ring = ndimage.binary_dilation(opening, iterations=3) & ~opening & fg & dark & ~hair
        label[opening & disc & ~lid] = index[f"extra_iris_{side}"]
        label[opening & ~disc & ~lid] = index[f"extra_sclera_{side}"]
        label[lid | ring] = index[f"extra_lid_upper_{side}"]
        # The iris's reach is its whole disc; the white's is the opening.
        _MASKS[f"extra_iris_{side}"] = disc
        _MASKS[f"extra_sclera_{side}"] = opening
        covered |= opening | ring
        brow = polygon_mask(feats["brows"][side], shape) & fg & (v < 0.42) & ~hair
        label[brow] = index[f"brow_{side}"]
        _MASKS[f"brow_{side}"] = brow
        covered |= brow
    # Pixels the colour segmenter gave an eye part outside both openings (the goggle rim is
    # the iris's blue) are not eye; they rejoin their neighbours, and the visor reclaims its own.
    eye_ids = [index[f"extra_{part}_{side}"] for side in ("l", "r")
               for part in ("sclera", "iris", "pupil", "catchlight", "lid_upper", "lid_lower")]
    stale = np.isin(label, eye_ids) & ~covered
    rest = (label >= 0) & ~np.isin(label, eye_ids)
    if stale.any() and rest.any():
        _, (iy, ix) = ndimage.distance_transform_edt(~rest, return_indices=True)
        label[stale] = label[iy[stale], ix[stale]]
    mouth_zone = polygon_mask(feats["mouth"], shape) & fg
    ring = ndimage.binary_dilation(mouth_zone, iterations=4) & ~mouth_zone & fg
    skin_v = float(np.median(v[ring])) if ring.any() else 0.7
    mouth = mouth_zone & (v < skin_v - 0.10)
    mouth = ndimage.binary_dilation(mouth, iterations=1) & mouth_zone
    label[mouth] = index["mouth_upper"]
    _MASKS["mouth_upper"] = mouth
    covered |= mouth
    return covered


def reclaim_visor(label: np.ndarray, rgba: np.ndarray, groups: list[seg.Group], keep: np.ndarray | None = None) -> None:
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
    if keep is not None:
        take &= ~ndimage.binary_dilation(keep, iterations=1)
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


def build(out_dir: Path = OUT_DIR, source: Path = seg.SOURCE, *, inpaint: bool = False,
          model: Path | None = None, cache_dir: Path = underlap_fill.CACHE_DIR) -> dict:
    """Cut the layers. Hidden regions use the cached AI fills; ``inpaint`` paints missing ones."""
    rgba = load_native(source)
    size = rgba.shape[0]
    scale = ARTBOARD / size
    groups = seg.load_blockout()
    _MASKS.clear()
    feats = load_features(source)
    label = label_map(rgba, groups, feats)
    index = {g.gid: i for i, g in enumerate(groups)}
    for g in groups:
        _MASKS.setdefault(g.gid, g.mask)
    cache = underlap_fill.FillCache(cache_dir)
    inpainter = underlap_fill.Inpainter(model or underlap_fill.DEFAULT_MODEL) if inpaint else None
    orb_core_split(label, rgba, index)

    lens = _mask_of(index, "visor_lens", label.shape) & (rgba[..., 3] > 0.0)
    layer_of = np.full(label.shape, -1, dtype=np.int32)
    for li, (_name, members) in enumerate(LAYERS):
        for gid in members:
            if gid in index:
                layer_of[label == index[gid]] = li
    # Per-pixel lens opacity: at most LENS_ALPHA, and never more than can be undone exactly.
    # Where the art under the lens is darker than the tint (a pupil), a uniform 22% could not be
    # removed without clipping, and the neutral pose would no longer match the source.
    c = rgba[..., :3]
    with np.errstate(divide="ignore", invalid="ignore"):
        low = np.where(LENS_TINT > 0, c / LENS_TINT, np.inf).min(-1)          # keeps result >= 0
        high = np.where(LENS_TINT < 1, (1 - c) / (1 - LENS_TINT), np.inf).min(-1)  # keeps <= 1
    exact = np.clip(np.minimum(LENS_ALPHA, np.minimum(low, high)), 0.0, LENS_ALPHA)
    if LENS_UNIFORM:
        # One opacity over the eyes: a per-pixel opacity dips over the original pupils (and
        # over the brightest white) and that dip stays behind as a ghost when the iris moves.
        # The cost is the few pixels darker or brighter than the tint allows, reported as
        # recomposite error inside the lens.
        # Elsewhere (lashes, lid lines) nothing slides out from under the lens, so the opacity
        # there is lowered to what can be undone exactly.
        moving = np.isin(layer_of, [i for i, (n, _m) in enumerate(LAYERS) if n in EYE_INTERIOR])
        lens_alpha = np.where(moving, np.float32(LENS_ALPHA), exact).astype(np.float32)
    else:
        lens_alpha = exact
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
    lens_index = next(i for i, (n, _m) in enumerate(LAYERS) if n == "visor_lens")
    # The lens tints what lies beneath it in the stack and nothing above it (the frame and the
    # fringe are drawn over the lens), so only pixels owned by lower layers are de-tinted.
    lens_over = lens & solid & (layer_of < lens_index) & (layer_of >= 0)
    # What each layer's visible pixels look like with the lens taken off: the fill continues these.
    base = rgba[..., :3].copy()
    base[lens_over] = detinted[lens_over, :3]
    layer_index = {n: i for i, (n, _m) in enumerate(LAYERS)}
    head_zone = np.zeros(label.shape, dtype=bool)
    for gid in HEAD_GROUPS:
        head_zone |= _mask_of(index, gid, label.shape)
    head_zone |= np.isin(layer_of, [layer_index[n] for n in ("face", "hair")])
    torso_outline = polygon_mask(feats["torso"], label.shape)
    records, planes = [], []
    for li, (name, members) in enumerate(LAYERS):
        own = layer_of == li
        plane = np.zeros_like(rgba)
        method = None
        if name == "visor_lens":
            plane[lens_over, :3] = LENS_TINT
            plane[lens_over, 3] = lens_alpha[lens_over]
            method = "lens_tint"
        else:
            plane[own] = rgba[own]
            if name in SKIN_RIM and own.any():
                rim = (ndimage.binary_dilation(own, iterations=SKIN_RIM[name]) & ~own & solid
                       & (layer_of == layer_index["face"]))
                plane[rim, :3] = base[rim]
                plane[rim, 3] = 1.0
                method = "skin_rim"
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
                if own.any() and grow > 0:  # iterations=0 would dilate to the whole image
                    reach |= ndimage.binary_dilation(own, iterations=grow)
                if name == "hair_back":
                    reach[int(feats["hair_floor_y"]):] = False
                if name in TORSO:
                    # What a turning head reveals is neck, not jacket: the torso stops at the
                    # head's outline and the neck layer fills beneath the chin. And a swung arm
                    # reveals the torso's side, not a flap of jacket out where the arm hung:
                    # the torso continues only inside its hand-placed outline.
                    reach &= ~head_zone & torso_outline
                hidden = reach & solid & (layer_of > li) & ~own
                if name in REVEAL_DEPTH and hidden.any():
                    hidden &= ndimage.distance_transform_edt(hidden) <= REVEAL_DEPTH[name]
                known = own | (layer_of == layer_index[FILL_CONTEXT[name]]) if name in FILL_CONTEXT else own
                if hidden.any() and known.any():
                    if name.startswith("sclera"):
                        # Beneath the iris is the white of the eye, not the lash-shadowed edge
                        # the propagation would carry in.
                        whites = own & (plane[..., :3].min(-1) > 0.75)
                        white = (np.median(plane[whites, :3], axis=0) if whites.any()
                                 else np.array([0xF2, 0xF6, 0xFA]) / 255.0)
                        plane[hidden, :3] = white
                        method = "sclera_white"
                    else:
                        key = underlap_fill.fill_key(name, base, known, hidden)
                        painted = cache.get(name, key, hidden)
                        if painted is None and inpainter is not None:
                            painted = cache.put(name, key, inpainter(base, known, hidden), hidden)
                        if painted is not None:
                            plane[hidden, :3] = painted[hidden]
                            method = underlap_fill.MODEL_NAME
                        else:
                            filled = propagate(base, known, hidden)
                            plane[hidden, :3] = filled[hidden]
                            method = "propagate"
                    plane[hidden, 3] = 1.0
        planes.append(plane)
        fill_method = method
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
            "underlap_fill": fill_method,
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
        "underlap_fill_model": {"name": underlap_fill.MODEL_NAME, "sha256": underlap_fill.MODEL_SHA256,
                                "url": underlap_fill.MODEL_URL},
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
    parser.add_argument("--inpaint", action="store_true", help="paint hidden regions missing from the fill cache (needs torch)")
    parser.add_argument("--model", type=Path, default=None, help="big-lama TorchScript file (default $VAN_FORGE_LAMA)")
    args = parser.parse_args(argv)
    m = build(args.out, inpaint=args.inpaint, model=args.model)
    print(json.dumps({"out": str(args.out), "layers": sum(1 for r in m["layers"] if not r.get("empty")),
                      "empty": [r["name"] for r in m["layers"] if r.get("empty")],
                      "recomposite_max_error": m["recomposite_max_error"],
                      "recomposite_mean_error": m["recomposite_mean_error"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
