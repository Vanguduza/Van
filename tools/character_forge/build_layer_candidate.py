#!/usr/bin/env python3
"""M1 lane candidate: a traced, layered vector of Candidate B (candidates only, never admitted).

Rev 2 §7: automated lanes write *candidates* under ``05-vectors-candidate/`` and nothing else.
The file this produces enters the critical path only if the vector artist admits it with
``cli vectors admit`` (pinned Inkscape) and an independent reviewer or the owner passes it.

What it does, in order:

1. rasterises every group of the measured blockout (``reference-pack/blockout``) into a mask
   on the 1000-unit artboard. The blockout's groups, their order (the rig's stacking order)
   and their ids are the layer topology; this tool keeps all three exactly;
2. assigns every opaque pixel of the native Candidate B cut-out to the topmost blockout group
   that covers it (nearest group for pixels the blockout misses), then corrects the
   assignment by colour where geometry alone is wrong: silver hair over the face, skin under
   the fringe, the visor's cyan frame, the eyes behind the lens, cyan jacket/glove accents
   that the identity lock keeps out of neutral groups;
3. gives each group underlap: where a higher layer hides it and its blockout primitive says
   it continues, it is filled with its own base colour, so a limb can rotate without opening
   a hole;
4. quantises each group to a few flat tones, clamps them into the identity lock's colour
   families (``svg_lint.COLOR_GROUPS``), and traces them with vtracer (stacked splines),
   raising the speckle filter until the group fits its topology budget;
5. writes one SVG whose groups are exactly the blockout's, falling back to the blockout
   primitive for any group with nothing to trace (hidden-in-neutral parts: mouth interior,
   teeth, lids, the eye-look helpers, the visor lens).

It is deterministic for a given input and parameters. It does not draw the hidden geometry a
human artist would (occluded hair back, the far side of the orb); underlap is the base colour
of the blockout primitive, which is the part M1's artist is expected to redraw.

    python3 -m tools.character_forge.build_layer_candidate
"""

from __future__ import annotations

import argparse
import colorsys
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

from .svg_lint import COLOR_GROUPS, NUMBERS, _allowed, _topology_budgets

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "visual-authority" / "character-forge" / "00-source" / "reference-pack"
BLOCKOUT = PACK / "blockout" / "van_layers_blockout.svg"
SOURCE = PACK / "interim" / "van_candidate_b_front.png"
OUT_DIR = ROOT / "visual-authority" / "character-forge" / "05-vectors-candidate"
N = 1000  # artboard units; the blockout's viewBox and the unit square both map onto it

#: Groups kept as their blockout primitive: parts hidden in the neutral pose, rig helpers and
#: the translucent lens. Tracing them from a single front image would invent geometry.
PRIMITIVE_ONLY = {
    "eye_l", "eye_r", "mouth_inner", "extra_teeth", "extra_tongue", "visor_lens",
    "brow_l", "brow_r", "extra_brow_inner_l", "extra_brow_outer_l", "extra_brow_inner_r",
    "extra_brow_outer_r",
    "extra_lid_upper_l", "extra_lid_lower_l", "extra_lid_upper_r", "extra_lid_lower_r",
    "extra_visor_glint", "extra_orb_eyes", "extra_orb_rim",
}
#: Groups that get underlap where higher layers cover their blockout primitive.
UNDERLAP = re.compile(r"^(arm_|hand_|extra_fingers_|extra_glove_|extra_leg_|extra_boot_|neck$|face$|"
                      r"underlayer$|jacket$|extra_jacket_back$|extra_hair_back$|orb_shell$)")
HEAD = {"hair", "extra_hair_back", "extra_hair_lock_l", "extra_hair_lock_r", "face", "extra_face_shadow",
        "extra_jaw", "extra_ear_l", "extra_ear_r", "brow_l", "brow_r", "extra_brow_inner_l",
        "extra_brow_outer_l", "extra_brow_inner_r", "extra_brow_outer_r"}
EYE_PARTS = ("sclera", "iris", "pupil", "catchlight")
#: Where cyan pixels go when their geometric owner may not hold cyan (identity lock §11.2).
CYAN_HOME = {"jacket": "extra_accents_cyan", "underlayer": "extra_accents_cyan",
             "extra_jacket_collar": "extra_accents_cyan", "hand_l": "extra_glove_l",
             "hand_r": "extra_glove_r", "neck": "extra_jacket_collar",
             **{f"arm_{s}_{seg}": f"extra_accents_cyan_arm_{s}_{seg}" for s in "lr" for seg in ("upper", "fore")}}
#: Accent layers the blockout does not have: a sleeve stripe must rotate with its arm, so each
#: arm segment gets its own, stacked directly above it.
ARM_ACCENTS = [f"extra_accents_cyan_arm_{s}_{seg}" for s in "lr" for seg in ("upper", "fore")]
#: Flat tones per group before tracing. More tones read better and cost paths.
TONES = {"hair": 5, "extra_boot_l": 4, "extra_boot_r": 4, "jacket": 6, "face": 3, "extra_face_shadow": 2, "underlayer": 3, "orb_shell": 4}
DEFAULT_TONES = 3
#: Floor for a shrunk extra: below this a visible part would fall back to its blockout
#: primitive, which is larger than the art (the hair-back ellipse showed as a disc).
MIN_EXTRA_NODES = 240
#: Tone-map smoothing window (artboard units).
SMOOTH = 7


@dataclass
class Primitive:
    kind: str                     # "ellipse" | "path"
    attrs: dict[str, str]
    points: list[tuple[float, float]] = field(default_factory=list)


@dataclass
class Group:
    gid: str
    primitives: list[Primitive]
    raw: str                      # the group's original XML, the fallback
    mask: np.ndarray | None = None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


SVG_NS = "http://www.w3.org/2000/svg"


def load_blockout(path: Path = BLOCKOUT) -> list[Group]:
    # Serialise SVG elements without an `ns0:` prefix, so a group's XML can be re-wrapped.
    ET.register_namespace("", SVG_NS)
    root = ET.parse(path).getroot()
    groups = []
    for g in root:
        if _local(g.tag) != "g":
            continue
        prims = []
        for el in g:
            tag = _local(el.tag)
            attrs = dict(el.attrib)
            if tag == "ellipse":
                prims.append(Primitive("ellipse", attrs))
            elif tag == "path":
                nums = [float(x) for x in NUMBERS.findall(attrs.get("d", ""))]
                prims.append(Primitive("path", attrs, list(zip(nums[0::2], nums[1::2]))))
        raw = ET.tostring(g, encoding="unicode").replace(' xmlns="http://www.w3.org/2000/svg"', "")
        groups.append(Group(g.attrib["id"], prims, raw))
        accent = f"extra_accents_cyan_{g.attrib['id']}"
        if accent in ARM_ACCENTS:
            groups.append(Group(accent, [], ""))
    return groups


def rasterise(group: Group) -> np.ndarray:
    img = Image.new("L", (N, N), 0)
    if not group.primitives:
        return np.asarray(img) > 127
    draw = ImageDraw.Draw(img)
    for p in group.primitives:
        filled = p.attrs.get("fill", "#000") not in ("none", "")
        width = max(1, round(float(p.attrs.get("stroke-width", "0") or 0)))
        if p.kind == "ellipse":
            cx, cy = float(p.attrs["cx"]), float(p.attrs["cy"])
            rx, ry = float(p.attrs["rx"]), float(p.attrs["ry"])
            box = [cx - rx, cy - ry, cx + rx, cy + ry]
            draw.ellipse(box, fill=255 if filled else None, outline=None if filled else 255, width=width)
        elif len(p.points) >= 3:
            if filled:
                draw.polygon(p.points, fill=255)
            else:
                draw.line(p.points + p.points[:1], fill=255, width=width, joint="curve")
    return np.asarray(img) > 127


#: The lint's floor for a layer's height is 0.5% of the artboard (5 units); lips drawn thinner
#: than that are both refused and unriggable, so primitives get at least this much height.
MIN_PRIMITIVE_HEIGHT = 6.0


def _thicken(group: Group) -> str:
    """The group's blockout XML, stretched about its centre to MIN_PRIMITIVE_HEIGHT if thinner."""
    # Exact geometry, not the rasterised mask: pixel rounding left a 3.3-unit lip at 4.95.
    ys: list[float] = []
    for p in group.primitives:
        if p.kind == "ellipse":
            cy, ry = float(p.attrs["cy"]), float(p.attrs["ry"])
            ys += [cy - ry, cy + ry]
        else:
            ys += [y for _x, y in p.points]
    if not ys:
        return group.raw
    height = max(ys) - min(ys)
    if height >= MIN_PRIMITIVE_HEIGHT:
        return group.raw
    k = MIN_PRIMITIVE_HEIGHT / max(height, 0.5)
    centre = (max(ys) + min(ys)) / 2.0
    inner = group.raw.split(">", 1)[1].rsplit("</g>", 1)[0]
    # On each shape rather than a wrapper group: the lint refuses a group without an id.
    transform = f'transform="matrix(1,0,0,{k:.4g},0,{centre * (1 - k):.4g})" '
    inner = re.sub(r"<(path|ellipse) ", lambda m: f"<{m.group(1)} {transform}", inner)
    return f'<g id="{group.gid}">{inner}</g>'


def load_source(path: Path = SOURCE) -> tuple[np.ndarray, np.ndarray]:
    img = Image.open(path).convert("RGBA").resize((N, N), Image.LANCZOS)
    arr = np.asarray(img).astype(np.float32) / 255.0
    return arr[..., :3], arr[..., 3] > 0.5


def hsv_arrays(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx, mn = rgb.max(-1), rgb.min(-1)
    d = mx - mn
    h = np.zeros_like(mx)
    nz = d > 1e-6
    rm = nz & (mx == r)
    gm = nz & (mx == g) & ~rm
    bm = nz & ~rm & ~gm
    h[rm] = ((g - b)[rm] / d[rm]) % 6
    h[gm] = (b - r)[gm] / d[gm] + 2
    h[bm] = (r - g)[bm] / d[bm] + 4
    s = np.where(mx > 1e-6, d / np.maximum(mx, 1e-6), 0)
    return h * 60.0, s, mx


def assign(groups: list[Group], rgb: np.ndarray, fg: np.ndarray) -> np.ndarray:
    index = {g.gid: i for i, g in enumerate(groups)}
    label = np.full((N, N), -1, dtype=np.int32)
    for i, g in enumerate(groups):
        if g.gid in PRIMITIVE_ONLY:
            continue
        label[g.mask & fg] = i
    # Pixels the blockout misses belong to the nearest group that was assigned.
    missing = fg & (label < 0)
    if missing.any():
        _, (iy, ix) = ndimage.distance_transform_edt(label < 0, return_indices=True)
        label[missing] = label[iy[missing], ix[missing]]

    h, s, v = hsv_arrays(rgb)
    cyan = (h >= 168) & (h <= 205) & (s > 0.45) & (v > 0.45)
    silver = (s < 0.24) & (v > 0.55)
    skin = (h >= 4) & (h <= 40) & (s > 0.28) & (v > 0.22) & ~silver
    name = np.array([g.gid for g in groups] + [""], dtype=object)

    def at(gid: str) -> np.ndarray:
        return label == index[gid]

    def move(where: np.ndarray, gid: str) -> None:
        if gid in index:
            label[where & fg] = index[gid]

    # Head: colour decides between hair and skin; the blockout's head ellipse is only a hint.
    head = np.isin(label, [index[g] for g in HEAD if g in index])
    for side in ("l", "r"):
        for part in EYE_PARTS:
            gid = f"extra_{part}_{side}"
            if gid in index:
                head &= ~groups[index[gid]].mask
    move(head & silver, "hair")
    move(head & skin, "face")
    # What the hair group still holds that is neither silver nor a plausible hair shadow is the
    # skin or visor behind the fringe; it goes to the face beneath rather than muddying the hair.
    hair_shadow = (s < 0.32) & (v > 0.35)
    move(at("hair") & ~silver & ~hair_shadow, "face")
    visor_band = groups[index["visor_frame"]].mask | groups[index["visor_lens"]].mask
    visor_band = ndimage.binary_dilation(visor_band, iterations=6)
    move(visor_band & cyan, "visor_frame")

    # Eyes behind the lens: colour picks the part inside each sclera.
    for side in ("l", "r"):
        sclera = groups[index[f"extra_sclera_{side}"]].mask & fg
        blue = sclera & (h >= 185) & (h <= 245) & (s > 0.3) & (v > 0.25)
        dark = sclera & (v < 0.22)
        bright = sclera & (s < 0.16) & (v > 0.82)
        label[sclera & skin] = index["face"]
        label[sclera & ~skin] = index[f"extra_sclera_{side}"]
        label[blue] = index[f"extra_iris_{side}"]
        label[dark] = index[f"extra_pupil_{side}"]
        iris_zone = ndimage.binary_dilation(blue, iterations=3)
        label[bright & iris_zone] = index[f"extra_catchlight_{side}"]

    # Cyan the identity lock keeps out of neutral groups goes to that group's accent layer.
    for owner, home in CYAN_HOME.items():
        if owner in index and home in index:
            label[at(owner) & cyan] = index[home]
    # Skin showing through a glove group (the open palm's wrist) belongs to the arm's accent.
    for side in ("l", "r"):
        for gid in (f"hand_{side}",):
            label[at(gid) & skin] = index[f"extra_glove_{side}"]
    label[~fg] = -1
    return label


def _clamp(rgb: tuple[float, float, float], family: str | None) -> tuple[float, float, float]:
    if family is None or _allowed(family, rgb):
        return rgb
    h, s, v = colorsys.rgb_to_hsv(*rgb)
    deg = h * 360
    if family == "silver":
        s, v = min(s, 0.28), max(v, 0.57)
    elif family in ("cyan", "blue"):
        lo, hi = (168, 222) if family == "cyan" else (188, 242)
        deg = min(max(deg, lo), hi)
        s, v = max(s, 0.3), max(v, 0.4 if family == "cyan" else 0.33)
    elif family == "skin":
        deg = min(max(deg, 11), 44)
        s, v = min(max(s, 0.40), 0.76), min(max(v, 0.47), 0.80)
    elif family == "neutral":
        if v > 0.38:
            s = min(s, 0.16)
    out = colorsys.hsv_to_rgb((deg % 360) / 360, s, v)
    return out if _allowed(family, out) else rgb


def _hex(rgb) -> str:
    return "#%02x%02x%02x" % tuple(int(round(c * 255)) for c in rgb)


def group_image(i: int, g: Group, label: np.ndarray, rgb: np.ndarray, fg: np.ndarray,
                tones: int | None = None) -> tuple[Image.Image | None, tuple[int, int]]:
    """The group's pixels, quantised and clamped, cropped to its box; None if empty."""
    own = label == i
    cover = own.copy()
    if UNDERLAP.match(g.gid) and g.mask is not None:
        cover |= g.mask & fg & (label > i)
    if cover.sum() < 12:
        return None, (0, 0)
    family = COLOR_GROUPS.get(g.gid)
    base_src = rgb[own] if own.sum() >= 12 else None
    if base_src is None:
        fill = next((p.attrs.get("fill") for p in g.primitives if p.attrs.get("fill", "none") != "none"), "#808080")
        base = tuple(int(fill[k:k + 2], 16) / 255 for k in (1, 3, 5))
    else:
        base = tuple(np.median(base_src, axis=0))
    canvas = np.zeros((N, N, 4), dtype=np.uint8)
    colours = np.where(own[..., None], rgb, np.array(base, dtype=np.float32))
    canvas[..., :3] = (colours * 255).astype(np.uint8)
    canvas[..., 3] = np.where(cover, 255, 0).astype(np.uint8)
    ys, xs = np.nonzero(cover)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    crop = Image.fromarray(canvas[y0:y1, x0:x1], "RGBA")
    tones = tones or TONES.get(g.gid, DEFAULT_TONES)
    q = crop.convert("RGB").quantize(colors=tones, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    pal = q.getpalette()[: tones * 3]
    clamped = []
    for k in range(tones):
        c = tuple(x / 255 for x in pal[k * 3:k * 3 + 3])
        clamped.extend(int(round(x * 255)) for x in _clamp(c, family))
    q.putpalette(clamped + [0] * (768 - len(clamped)))
    # Mode-filter the tone map and close the coverage mask before tracing: vtracer spends
    # coordinates on every jagged pixel step, so noise here is paid for in the node budget.
    idx = np.asarray(q)
    counts = np.stack([ndimage.uniform_filter((idx == k).astype(np.float32), size=SMOOTH)
                       for k in range(tones)])
    idx = counts.argmax(0).astype(np.uint8)
    rgba = np.zeros((*idx.shape, 4), dtype=np.uint8)
    lut = np.array(clamped + [0] * (768 - len(clamped)), dtype=np.uint8).reshape(256, 3)
    rgba[..., :3] = lut[idx]
    alpha = np.asarray(crop)[..., 3] > 127
    alpha = ndimage.binary_opening(ndimage.binary_closing(alpha, iterations=2), iterations=1)
    rgba[..., 3] = np.where(alpha, 255, 0).astype(np.uint8)
    out = Image.fromarray(rgba, "RGBA")
    return out, (int(x0), int(y0))


PATH_RE = re.compile(r'<path d="([^"]+)" fill="(#[0-9A-Fa-f]{6})" transform="translate\(([-\d.]+),([-\d.]+)\)"\s*/>')


def trace(img: Image.Image, offset: tuple[int, int], speckle: int, scale: float = 1.0) -> list[str]:
    """Trace at `scale` (nearest-neighbour, so no new colours), then map back to the artboard."""
    import vtracer

    if scale != 1.0:
        size = (max(2, round(img.width * scale)), max(2, round(img.height * scale)))
        img = img.resize(size, Image.NEAREST)
    k = img.width and (1.0 / scale)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    svg = vtracer.convert_raw_image_to_svg(
        buf.getvalue(), img_format="png", colormode="color", hierarchical="stacked", mode="spline",
        filter_speckle=speckle, color_precision=8, layer_difference=8, corner_threshold=60,
        length_threshold=4.0, max_iterations=10, splice_threshold=45, path_precision=1,
    )
    paths = []
    for d, fill, tx, ty in PATH_RE.findall(svg):
        e, f = offset[0] + float(tx) * k, offset[1] + float(ty) * k
        transform = f"translate({e:g},{f:g})" if k == 1.0 else f"matrix({k:.4g},0,0,{k:.4g},{e:.4g},{f:.4g})"
        paths.append(f'<path d="{d.strip()}" fill="{fill.lower()}" transform="{transform}"/>')
    return paths


SCALES = (1.0, 0.75, 0.55, 0.42, 0.32, 0.24, 0.18)
SPECKLES = (4, 8, 14, 24, 40)
#: Small features (logo letters, accent stripes) matter more than edge precision, so lose
#: resolution before losing small shapes: every scale at a light speckle filter first.
SEARCH = [(sp, sc) for sp in SPECKLES[:2] for sc in SCALES] + [(sp, sc) for sp in SPECKLES[2:] for sc in SCALES]


def fit(i: int, g: Group, label, rgb, fg, max_paths: int, max_nodes: int):
    """The most detailed trace that fits the group's budget: highest scale first, then the
    lightest speckle filter, then fewer tones. None when nothing fits."""
    base_tones = TONES.get(g.gid, DEFAULT_TONES)
    for tones in sorted({base_tones, 2, 1}, reverse=True):
        img, offset = group_image(i, g, label, rgb, fg, tones)
        if img is None:
            return None
        for speckle, scale in SEARCH:
                paths = trace(img, offset, speckle, scale)
                p, n = _cost(paths)
                if paths and p <= max_paths and n <= max_nodes:
                    return paths, {"tones": tones, "scale": scale, "speckle": speckle}
    return None


def _budget(gid: str, cfg: dict) -> tuple[int, int]:
    b = (cfg.get("groups") or {}).get(gid)
    if b is None:
        extra = cfg.get("extra_group_policy") or {}
        return int(extra.get("default_max_paths", 24)), int(extra.get("default_max_numeric_nodes", 900))
    return int(b["max_paths"]), int(b["max_numeric_nodes"])


def _cost(paths: list[str]) -> tuple[int, int]:
    return len(paths), sum(len(NUMBERS.findall(p.split('d="', 1)[1].split('"', 1)[0])) for p in paths)


def build(out: Path, *, label_png: Path | None = None) -> dict:
    groups = load_blockout()
    for g in groups:
        g.mask = rasterise(g)
    rgb, fg = load_source()
    label = assign(groups, rgb, fg)
    cfg = _topology_budgets()
    hard_nodes = int((cfg.get("policy") or {}).get("hard_total_numeric_nodes", 30000))
    fitted: dict[str, tuple[list[str], dict]] = {}
    required = set((cfg.get("groups") or {}).keys())
    area = {g.gid: int((label == i).sum()) for i, g in enumerate(groups)}

    def fit_all(extra_shrink: float, core_shrink: float, only: set[str] | None = None) -> int:
        for i, g in enumerate(groups):
            if g.gid in PRIMITIVE_ONLY or (only is not None and g.gid not in only):
                continue
            max_paths, max_nodes = _budget(g.gid, cfg)
            # A boot is not a catchlight: an extra's share of the shrink follows its size.
            factor = core_shrink if g.gid in required else min(
                1.0, extra_shrink * max(0.5, float(np.sqrt(area.get(g.gid, 0) / 1500.0))))
            result = fit(i, g, label, rgb, fg, max_paths, max(MIN_EXTRA_NODES, int(max_nodes * factor)))
            if result:
                fitted[g.gid] = result
            else:
                fitted.pop(g.gid, None)
        return sum(_cost(p)[1] for p, _ in fitted.values())

    # The per-group budgets sum past the file's hard budget. The identity-bearing groups keep
    # theirs; the ~50 construction extras yield first, and only then does everything shrink.
    ceiling = hard_nodes * 0.92
    extra_shrink = core_shrink = 1.0
    extras = {g.gid for g in groups} - required
    total_nodes = fit_all(1.0, 1.0)
    while total_nodes > ceiling and extra_shrink > 0.35:
        extra_shrink *= 0.85
        total_nodes = fit_all(extra_shrink, core_shrink, only=extras)
    while total_nodes > ceiling and core_shrink > 0.4:
        core_shrink *= 0.9
        total_nodes = fit_all(extra_shrink, core_shrink, only=required)
    shrink = {"extras": round(extra_shrink, 3), "core": round(core_shrink, 3)}
    body, report = [], {}
    for g in groups:
        if g.gid in fitted:
            paths, params = fitted[g.gid]
            body.append(f'<g id="{g.gid}">' + "".join(paths) + "</g>")
            report[g.gid] = {"source": "traced", **params,
                             "paths": _cost(paths)[0], "numeric_nodes": _cost(paths)[1]}
        elif g.raw:
            body.append(_thicken(g))
            report[g.gid] = {"source": "blockout_primitive"}
        else:
            # An added layer with nothing to hold (an arm segment with no cyan stripe) stays in
            # the file empty, so the rig sees the same layer list whatever the art contains.
            body.append(f'<g id="{g.gid}"/>')
            report[g.gid] = {"source": "empty"}
    if total_nodes > hard_nodes:
        raise SystemExit(f"refused: {total_nodes} numeric nodes exceeds the hard budget {hard_nodes}")
    header = (
        "<!-- VAN M1 LANE CANDIDATE: traced from the native Candidate B cut-out by\n"
        "     tools/character_forge/build_layer_candidate.py over the measured blockout's layer\n"
        "     topology. NOT admitted art: it enters M1 only through `cli vectors admit` by the\n"
        "     vector artist and an independent/owner review. Underlap is blockout base colour;\n"
        "     hidden-in-neutral parts are blockout primitives. -->\n"
    )
    svg = ('<?xml version="1.0" encoding="UTF-8"?>\n' + header +
           '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000" width="1000" height="1000">'
           + "".join(body) + "</svg>\n")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg, encoding="utf-8")
    if label_png is not None:
        rng = np.random.default_rng(7)
        colours = rng.integers(40, 255, size=(len(groups) + 1, 3), dtype=np.uint8)
        colours[-1] = 255
        Image.fromarray(colours[label]).save(label_png)
    return {"output": str(out), "groups": report, "budget_shrink": shrink,
            "traced": sum(r["source"] == "traced" for r in report.values()),
            "primitive": sum(r["source"] == "blockout_primitive" for r in report.values()),
            "total_numeric_nodes": total_nodes}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=OUT_DIR / "van_layers_traced_candidate.svg")
    parser.add_argument("--label-map", type=Path, default=None, help="also write the pixel→layer map as PNG")
    args = parser.parse_args(argv)
    result = build(args.out, label_png=args.label_map)
    print(json.dumps({k: v for k, v in result.items() if k != "groups"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
