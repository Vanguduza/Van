"""Builds the VAN Rive reference pack from the single approved visual authority.

Every image in the pack is a crop (or a guide drawn over a crop) of Candidate B,
`visual-authority/character-forge/01-master-candidates/van_master_source_candidate_b.png`
(native 1536x1024, CF-D-05-REV2_1), addressed by exact pixel boxes so any crop can be regenerated
and audited. Nothing here invents identity: measured palettes, proportions and aura parameters are
*read* from Candidate B and from the shipping Android code. The production-v3 expression, pose,
viseme and hand sheets are off-model (tall figure, glowing visor, cyan face orb); the state/action
map cites them for meaning only and never crops them.

The layered blockout SVG is a construction scaffold (pivots, layer topology, proportions,
identity palette) for the M1 vector artist. It is a CANDIDATE, never admitted art.

    python -m tools.character_forge.build_reference_pack          # (re)build the pack
    python -m tools.character_forge.build_reference_pack --check  # verify manifest hashes only
"""
from __future__ import annotations

import argparse
import colorsys
import hashlib
import json
import math
import re
import sys
from pathlib import Path

from . import proportions as proportion_rule

ROOT = Path(__file__).resolve().parents[2]
BOARD = ROOT / "visual-authority" / "character-forge" / "01-master-candidates" / "van_master_source_candidate_b.png"
PACK = ROOT / "visual-authority" / "character-forge" / "00-source" / "reference-pack"
SUPPORTING = ROOT / "visual-authority" / "character-forge" / "00-source" / "production-v3" / "artwork"
AURA_SPEC = ROOT / "android" / "app" / "src" / "main" / "java" / "com" / "dial" / "van" / "visual" / "VanAuraSpec.kt"
GLASS_TOKENS = ROOT / "android" / "app" / "src" / "main" / "java" / "com" / "dial" / "van" / "visual" / "VanGlassTokens.kt"
STATUS_PALETTE = ROOT / "android" / "app" / "src" / "main" / "java" / "com" / "dial" / "van" / "visual" / "VanStatusPalette.kt"
AUTHORITY_V2 = ROOT / "visual-authority" / "van-visual-authority-v2.yaml"
IDENTITY_LOCK = ROOT / "visual-authority" / "character-forge" / "00-source" / "asset-pack" / "APPROVED_IDENTITY_LOCK.yaml"
MANIFEST = PACK / "PACK_MANIFEST.json"

# ── Candidate B regions (x0, y0, x1, y1) in native px, calibrated on a labelled grid ──────────
TURNAROUND = {
    "front": (40, 0, 330, 525),
    "three_quarter_front": (380, 0, 600, 525),
    "side": (695, 0, 860, 525),
    "three_quarter_rear": (945, 0, 1150, 525),
    "rear": (1230, 0, 1460, 525),
}
REGIONS = {
    "orb_front": (18, 118, 122, 212),
    "orb_three_quarter_front": (560, 145, 655, 240),
    "orb_side": (845, 165, 940, 262),
    "orb_three_quarter_rear": (1143, 148, 1242, 242),
    "orb_rear": (1435, 118, 1530, 212),
    "detail_head_front": (0, 555, 345, 968),
    "detail_head_three_quarter": (348, 555, 660, 968),
    "detail_visor": (675, 560, 1122, 695),
    "detail_gloves": (1128, 560, 1536, 695),
    "detail_jacket": (675, 700, 1122, 948),
    "detail_orb": (1128, 700, 1536, 840),
    "detail_boots": (1098, 845, 1536, 970),
}

# Off-model production-v3 sheets: semantic references only (what a state/action means), never shape.
SEMANTIC_SHEETS = {
    "expressions": "van_expression_and_facial_acting_sheet.png",
    "poses": "van_states_and_actions_pose_pack.png",
    "visemes": "van_ai_assistant_viseme_construction_sheet.png",
    "hands": "van_hand_and_glove_gesture_reference_sheet.png",
    "aura": "van_aura_runtime_field_guide.png",
}
SEMANTIC_STATES = {  # contract state -> sheets whose labelled panel shows its meaning
    "IDLE": ["expressions", "poses"], "ATTENTIVE": ["expressions"], "LISTENING": ["expressions", "poses"],
    "THINKING": ["expressions", "poses"], "SPEAKING": ["expressions", "poses", "visemes"], "WORKING": ["poses"],
    "WAITING_FOR_OWNER": ["poses"], "WARNING": ["expressions", "poses"], "ERROR": ["expressions", "poses"],
    "SUCCESS": ["expressions", "poses"], "URGENT": ["expressions", "poses"], "SLEEPING": ["expressions", "poses"],
}
SEMANTIC_ACTIONS = {
    "HELLO_WAVE": ["poses", "hands"], "ACK_NOD": ["poses"], "POINT_TARGET": ["poses", "hands"], "CELEBRATE": ["poses"],
    "CAUTION": ["poses", "hands"], "CONFIRM": ["poses", "hands"], "SHRUG": ["poses"], "PRESENT_CARD": ["poses", "hands"],
}

# Front-figure landmarks (Candidate B px), read on a 2x grid of the front view.
LANDMARKS = {
    "centre_x": 200, "face_cx": 190, "hair_crown": 8, "skull_top": 45, "brow_line": 97, "eye_line": 122,
    "mouth_line": 153, "chin": 170, "collar": 185, "shoulder_line": 200, "belt": 305, "crotch": 345,
    "fingertips": 390, "knee": 410, "boot_top": 450, "sole": 518, "face_left": 125, "face_right": 255,
    "shoulder_left": 105, "shoulder_right": 300,
}
ORB = {"cx": 67, "cy": 171, "r": 50}
PALETTE_SAMPLES = {  # material -> list of Candidate B boxes whose pixels are filtered by `family`
    "skin": ([(60, 790, 130, 870), (215, 790, 285, 870), (140, 885, 210, 925)], "skin"),
    "hair": ([(40, 570, 300, 660)], "silver"),
    "visor_lens": ([(700, 585, 900, 650)], "cyan"),
    "jacket_white": ([(690, 720, 760, 860)], "white"),
    "glove": ([(1160, 580, 1240, 660)], "dark"),
    "orb_shell": ([(1140, 700, 1260, 820)], "dark"),
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


# ── Colour science (sRGB -> CIELAB D65, CIEDE2000) ─────────────────────────────────────────────
def _hex(rgb) -> str:
    return "#%02X%02X%02X" % tuple(int(round(c)) for c in rgb)


def _lab(hex_or_rgb):
    if isinstance(hex_or_rgb, str):
        h = hex_or_rgb.lstrip("#")
        rgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    else:
        rgb = [c / 255 for c in hex_or_rgb]
    lin = [((c + 0.055) / 1.055) ** 2.4 if c > 0.04045 else c / 12.92 for c in rgb]
    x = (lin[0] * .4124 + lin[1] * .3576 + lin[2] * .1805) / .95047
    y = lin[0] * .2126 + lin[1] * .7152 + lin[2] * .0722
    z = (lin[0] * .0193 + lin[1] * .1192 + lin[2] * .9505) / 1.08883
    f = lambda t: t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    return 116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))


def delta_e2000(a, b) -> float:
    L1, a1, b1 = _lab(a); L2, a2, b2 = _lab(b)
    C1 = math.hypot(a1, b1); C2 = math.hypot(a2, b2); Cb = (C1 + C2) / 2
    G = .5 * (1 - math.sqrt(Cb ** 7 / (Cb ** 7 + 25 ** 7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1 = math.degrees(math.atan2(b1, a1p)) % 360; h2 = math.degrees(math.atan2(b2, a2p)) % 360
    dL, dC, dh = L2 - L1, C2p - C1p, h2 - h1
    if abs(dh) > 180: dh -= 360 * math.copysign(1, dh)
    dH = 2 * math.sqrt(C1p * C2p) * math.sin(math.radians(dh / 2))
    Lb, Cbp = (L1 + L2) / 2, (C1p + C2p) / 2
    hb = (h1 + h2) / 2 if abs(h1 - h2) <= 180 else (h1 + h2 + 360) / 2
    T = 1 - .17 * math.cos(math.radians(hb - 30)) + .24 * math.cos(math.radians(2 * hb)) + .32 * math.cos(math.radians(3 * hb + 6)) - .2 * math.cos(math.radians(4 * hb - 63))
    SL = 1 + .015 * (Lb - 50) ** 2 / math.sqrt(20 + (Lb - 50) ** 2); SC = 1 + .045 * Cbp; SH = 1 + .015 * Cbp * T
    RT = -2 * math.sqrt(Cbp ** 7 / (Cbp ** 7 + 25 ** 7)) * math.sin(math.radians(60 * math.exp(-((hb - 275) / 25) ** 2)))
    return math.sqrt((dL / SL) ** 2 + (dC / SC) ** 2 + (dH / SH) ** 2 + RT * (dC / SC) * (dH / SH))


def _family(name: str, rgb) -> bool:
    r, g, b = rgb
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255); deg = h * 360
    return {
        "skin": 0 <= deg <= 45 and .30 <= s <= .85 and .30 <= v <= .95 and r > g > b,
        "silver": s <= .18 and v >= .62,
        "cyan": 180 <= deg <= 215 and s >= .45 and v >= .45,
        "white": s <= .08 and v >= .80,
        "dark": v <= .22,
    }[name]


def measured_palette(board) -> dict:
    out = {}
    for material, (boxes, family) in PALETTE_SAMPLES.items():
        pix = [board.getpixel((x, y)) for x0, y0, x1, y1 in boxes for x in range(x0, x1) for y in range(y0, y1)]
        pix = sorted((p for p in pix if _family(family, p)), key=lambda p: colorsys.rgb_to_hsv(*[c / 255 for c in p])[2])
        if not pix:
            continue
        pick = lambda f: pix[int(f * (len(pix) - 1))]
        mean = [sum(p[i] for p in pix) / len(pix) for i in range(3)]
        out[material] = {
            "sample_boxes": [list(b) for b in boxes], "pixels": len(pix), "family_filter": family,
            "shadow_p10": _hex(pick(.10)), "mid_p50": _hex(pick(.50)), "lit_p90": _hex(pick(.90)), "mean": _hex(mean),
        }
    return out


# ── Code-sourced aura and overlay truth ────────────────────────────────────────────────────────
def aura_table() -> dict:
    text = AURA_SPEC.read_text(encoding="utf-8")
    tokens = {m.group(1): "#" + m.group(2)[2:] for m in re.finditer(r"const val (ACCENT_\w+) = 0x([0-9A-Fa-f]{8})", GLASS_TOKENS.read_text(encoding="utf-8"))}
    body = text[text.index("object VanAuraSpecs"):]
    rows = {}
    for m in re.finditer(r"VanDurableState\.(\w+) -> spec\((.*?)\n            \)", body, re.S):
        state, args = m.group(1), m.group(2)
        num = lambda k: float(re.search(rf"\b{k} = (-?[0-9.]+)f?", args).group(1))
        sem = re.search(r"semantic = (?:VanGlassTokens\.)?(\w+)", args).group(1)
        rows[state] = {
            "intensity": num("intensity"), "arc": num("arc"), "spark": num("spark"), "ground": num("ground"), "orb": num("orb"),
            "filaments": int(num("filaments")), "asymmetry": num("asymmetry"), "deform": num("deform"),
            "envelope_scale": num("envelopeScale"), "envelope_alpha": num("envelopeAlpha"),
            "semantic_colour": None if sem == "null" else tokens.get(sem, sem),
            "envelope_segments": [
                {"centre_deg": float(a), "sweep_deg": float(b), "node": bool(n)}
                for a, b, n in re.findall(r"VanAuraEnvelopeSegment\((-?[0-9.]+)f, (-?[0-9.]+)f(, node = true)?\)", args)
            ],
        }
    consts = {k: float(v) for k, v in re.findall(r"const val (\w+(?:SCALE|_DEG|INTENSITY))\s*=\s*([0-9.]+)f", text)}
    accents = {}
    for state, colour in re.findall(r"VanDurableState\.(\w+) -> palette\((\w+),", STATUS_PALETTE.read_text(encoding="utf-8")):
        m = re.search(rf"const val {colour} = 0x([0-9A-Fa-f]{{8}})L", STATUS_PALETTE.read_text(encoding="utf-8"))
        accents[state] = "#" + m.group(1)[2:] if m else colour
    for state in rows:
        rows[state]["status_accent"] = accents.get(state)
    return {"constants": consts, "states": rows}


def overlay_spec() -> dict:
    text = AUTHORITY_V2.read_text(encoding="utf-8")
    get = lambda k: float(re.search(rf"{k}:\s*([0-9.]+)", text).group(1))
    return {
        "resting_avatar_dp": get("resting_avatar_dp"), "resting_hit_dp": get("resting_hit_dp"),
        "dock_character_dp": get("dock_character_dp"), "dock_hit_dp": get("dock_hit_dp"),
        "compact_width_dp": get("compact_width_dp"), "van_glass_overlap_dp": get("van_glass_overlap_dp"),
        "aura_zone_scales": {"inner_presence": 1.00, "mid_interaction": 1.12, "outer_semantic_min": 1.35, "outer_semantic_max": 1.70},
        "outer_semantic_max_coverage_deg": get("max_total_coverage_degrees"),
    }


# ── Artboard geometry: board px -> artboard units (1000 x 1000, 6% margin, feet on the floor) ───
ART = 1000.0
_SCALE = (ART * 0.86) / (LANDMARKS["sole"] - LANDMARKS["hair_crown"])  # character height = 86% of artboard


def P(x: float, y: float) -> tuple[float, float]:
    return (round((x - LANDMARKS["centre_x"]) * _SCALE + ART / 2, 1), round((y - LANDMARKS["hair_crown"]) * _SCALE + ART * 0.07, 1))


def L(y: float) -> float:
    return P(0, y)[1]


def W(dx: float) -> float:
    return round(dx * _SCALE, 1)


def rig_pivots() -> dict:
    lm = LANDMARKS; cx = lm["centre_x"]
    pts = {
        "root": (cx, lm["sole"]), "hips": (cx, lm["crotch"] - 12), "spine": (cx, lm["belt"]),
        "chest": (cx, lm["shoulder_line"] + 30), "neck": (lm["face_cx"], lm["collar"]), "head": (lm["face_cx"], lm["chin"] - 6),
        "shoulder_l": (lm["shoulder_left"] + 25, lm["shoulder_line"]), "shoulder_r": (lm["shoulder_right"] - 20, lm["shoulder_line"]),
        "elbow_l": (100, 255), "elbow_r": (298, 262), "wrist_l": (80, 280), "wrist_r": (302, 318),
        "hip_l": (165, lm["crotch"] - 12), "hip_r": (240, lm["crotch"] - 12), "knee_l": (152, lm["knee"]), "knee_r": (250, lm["knee"]),
        "ankle_l": (140, 462), "ankle_r": (268, 462),
        "eye_l_centre": (158, lm["eye_line"]), "eye_r_centre": (220, lm["eye_line"]),
        "jaw": (lm["face_cx"], lm["chin"] - 4), "orb_anchor": (ORB["cx"], ORB["cy"]),
    }
    return {k: {"artboard": list(P(*v)), "board_px": list(v)} for k, v in pts.items()}


# ── Layered blockout (construction scaffold for M1) ────────────────────────────────────────────
C = {"hair": "#E9EDF3", "hair_shadow": "#B1A3A8", "skin": "#AF6A53", "skin_shadow": "#774137", "iris": "#1E88E5",
     "pupil": "#0D47A1", "sclera": "#F2F6FA", "visor": "#3F8ACE", "visor_frame": "#00E5FF", "visor_pod": "#1F212A",
     "jacket_light": "#EDEFF3", "jacket_dark": "#15181C", "under": "#2B3138", "glove": "#111820", "accent": "#00E5FF",
     "orb_shell": "#020C1C", "orb_core": "#00E5FF", "mouth": "#5A2E24", "teeth": "#F2F2F0", "tongue": "#B4545A", "brow": "#3A2A26"}


def _poly(points, fill, extra="") -> str:
    return f'<path fill="{fill}"{extra} d="M ' + " L ".join(f"{x} {y}" for x, y in points) + ' Z"/>'


def _bpoly(points, fill, extra="") -> str:
    """Polygon given in Candidate B px."""
    return _poly([P(x, y) for x, y in points], fill, extra)


def _ell(cx, cy, rx, ry, fill, extra="") -> str:
    return f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="{fill}"{extra}/>'


def _bell(x, y, rx, ry, fill, extra="") -> str:
    """Ellipse given in Candidate B px."""
    px, py = P(x, y)
    return _ell(px, py, W(rx), W(ry), fill, extra)


def _g(gid, *children) -> str:
    return f'<g id="{gid}">' + "".join(children) + "</g>"


def blockout_svg() -> str:
    """Candidate B front view, redrawn as flat construction shapes in its own pixel coordinates.
    `_l` is the viewer's left, matching the turnaround crops."""
    lm = LANDMARKS; fx = lm["face_cx"]; ey = lm["eye_line"]
    groups = []
    # Order is paint order: back to front.
    groups.append(_g("extra_hair_back", _bell(fx, 78, 96, 72, C["hair_shadow"])))
    groups.append(_g("extra_jacket_back", _bpoly([(128, 168), (262, 168), (292, 222), (108, 222)], C["jacket_dark"])))
    groups.append(_g("underlayer", _bpoly([(150, 185), (250, 185), (246, 332), (154, 332)], C["under"])))
    # Legs and boots are absent from LAYER_SPEC (OWNER-DEC-004) but Candidate B and the motion spec
    # (SLEEPING slump, CELEBRATE crouch) need them; carried as extra_ layers so knees can bend.
    for side, hx, kx, ax, toe in (("l", 165, 152, 140, -1), ("r", 240, 250, 268, 1)):
        groups.append(_g(f"extra_leg_{side}_upper", _bpoly([(hx - 30, 330), (hx + 30, 330), (kx + 27, lm["knee"] + 4), (kx - 27, lm["knee"] + 4)], C["jacket_dark"])))
        groups.append(_g(f"extra_leg_{side}_lower", _bpoly([(kx - 26, lm["knee"]), (kx + 26, lm["knee"]), (ax + 24, 458), (ax - 24, 458)], C["jacket_dark"]),
                         _bell(kx, lm["knee"], 20, 10, C["under"])))
        bx0, bx1 = (82, 190) if side == "l" else (232, 312)
        heel, tip = (bx1, bx0) if toe < 0 else (bx0, bx1)
        groups.append(_g(f"extra_boot_{side}",
                         _bpoly([(ax - 26, lm["boot_top"] - 5), (ax + 26, lm["boot_top"] - 5), (heel, 490), (heel, lm["sole"]), (tip, lm["sole"]), (tip, 492)], C["jacket_light"]),
                         _bpoly([(heel, 505), (heel, lm["sole"]), (tip, lm["sole"]), (tip, 505)], C["jacket_dark"]),
                         _bpoly([(ax - 8, 462), (ax + 8, 462), (ax, 474)], C["accent"])))
    groups.append(_g("neck", _bpoly([(176, 158), (206, 158), (210, 192), (172, 192)], C["skin"])))
    groups.append(_g("jacket",
                     _bpoly([(142, 182), (185, 192), (185, 340), (106, 340), (98, 250)], C["jacket_light"]),
                     _bpoly([(262, 182), (215, 192), (215, 340), (312, 340), (306, 250)], C["jacket_light"]),
                     _bpoly([(150, 190), (185, 196), (185, 290), (140, 300)], C["jacket_dark"]),
                     _bpoly([(252, 190), (215, 196), (215, 290), (262, 290)], C["jacket_dark"])))
    groups.append(_g("extra_jacket_collar", _bpoly([(134, 180), (176, 164), (188, 204), (150, 212)], C["jacket_dark"]),
                     _bpoly([(266, 180), (212, 164), (206, 204), (252, 212)], C["jacket_dark"])))
    groups.append(_g("extra_accents_cyan", _bpoly([(184, 196), (188, 196), (188, 335), (184, 335)], C["accent"]),
                     _bpoly([(146, 204), (150, 204), (150, 320), (146, 320)], C["accent"]),
                     _bpoly([(200, 228), (242, 228), (242, 240), (200, 240)], C["accent"])))
    # Viewer-left arm reaches out palm-up under the orb; viewer-right arm hangs at the side.
    for side, sh, el, wr, hand, fingers in (
        ("l", (130, 200), (100, 255), (80, 280), (50, 262, 30, 18), ((22, 268), (24, 252), (40, 244))),
        ("r", (280, 200), (298, 262), (302, 318), (302, 348, 20, 32), ((296, 382), (310, 384), (284, 364))),
    ):
        groups.append(_g(f"arm_{side}_upper", _bpoly([(sh[0] - 18, sh[1]), (sh[0] + 18, sh[1]), (el[0] + 17, el[1]), (el[0] - 17, el[1])], C["jacket_light"])))
        groups.append(_g(f"arm_{side}_fore", _bpoly([(el[0] - 16, el[1]), (el[0] + 16, el[1]), (wr[0] + 14, wr[1]), (wr[0] - 14, wr[1])], C["jacket_dark"])))
        groups.append(_g(f"hand_{side}", _bell(*hand, C["glove"])))
        groups.append(_g(f"extra_glove_{side}", _bpoly([(wr[0] - 16, wr[1] - 8), (wr[0] + 16, wr[1] - 8), (wr[0] + 14, wr[1] + 8), (wr[0] - 14, wr[1] + 8)], C["glove"]),
                         _bpoly([(wr[0] - 12, wr[1] - 2), (wr[0] + 12, wr[1] - 2), (wr[0] + 12, wr[1] + 2), (wr[0] - 12, wr[1] + 2)], C["accent"])))
        for finger, (fx_, fy_) in zip(("index", "mid_ring_pinky", "thumb"), fingers):
            # Full black technical gloves (CF-D-05-REV2_1): no skin on the fingers.
            groups.append(_g(f"extra_fingers_{side}_{finger}", _bell(fx_, fy_, 7, 6, C["glove"])))
    groups.append(_g("face", _bell(fx, 116, 64, 54, C["skin"])))
    groups.append(_g("extra_face_shadow", _bell(fx, 162, 34, 6, C["skin_shadow"], ' opacity="0.35"')))
    groups.append(_g("extra_jaw", _bell(fx, 163, 30, 7, C["skin"])))
    groups.append(_g("extra_ear_l", _bell(126, 128, 9, 14, C["skin"])))
    groups.append(_g("extra_ear_r", _bell(256, 128, 9, 14, C["skin"])))
    for side, x in (("l", 158), ("r", 220)):
        sgn = -1 if side == "l" else 1
        groups.append(_g(f"extra_sclera_{side}", _bell(x, ey, 17, 13, C["sclera"])))
        groups.append(_g(f"extra_iris_{side}", _bell(x + sgn * 1, ey + 1, 11, 12, C["iris"])))
        groups.append(_g(f"extra_pupil_{side}", _bell(x + sgn * 1, ey + 1, 5, 6, C["pupil"])))
        groups.append(_g(f"extra_catchlight_{side}", _bell(x - 4, ey - 5, 3, 3, C["sclera"])))
        groups.append(_g(f"eye_{side}", _bell(x, ey + 1, 11, 12, C["iris"], ' opacity="0"')))
        groups.append(_g(f"extra_lid_upper_{side}", _bpoly([(x - 19, ey - 11), (x + 19, ey - 11), (x + 19, ey - 14), (x - 19, ey - 14)], C["skin_shadow"])))
        groups.append(_g(f"extra_lid_lower_{side}", _bpoly([(x - 15, ey + 13), (x + 15, ey + 13), (x + 15, ey + 15), (x - 15, ey + 15)], C["skin"])))
        by = lm["brow_line"]
        groups.append(_g(f"brow_{side}", _bpoly([(x - 18, by + 2), (x + 18, by - 1), (x + 18, by + 3), (x - 18, by + 6)], C["brow"])))
        groups.append(_g(f"extra_brow_inner_{side}", _bell(x - sgn * 14, by + 3, 4, 2, C["brow"])))
        groups.append(_g(f"extra_brow_outer_{side}", _bell(x + sgn * 14, by + 1, 4, 2, C["brow"])))
    my = lm["mouth_line"]
    groups.append(_g("mouth_inner", _bell(fx + 3, my, 12, 3, C["mouth"])))
    groups.append(_g("extra_teeth", _bpoly([(fx - 7, my - 2), (fx + 13, my - 2), (fx + 13, my), (fx - 7, my)], C["teeth"])))
    groups.append(_g("extra_tongue", _bell(fx + 3, my + 2, 5, 1, C["tongue"])))
    groups.append(_g("mouth_upper", _bpoly([(fx - 12, my - 3), (fx + 18, my - 3), (fx + 15, my - 5), (fx - 9, my - 5)], C["skin_shadow"])))
    groups.append(_g("mouth_lower", _bpoly([(fx - 9, my + 3), (fx + 15, my + 3), (fx + 11, my + 5), (fx - 5, my + 5)], C["skin_shadow"])))
    # Clear wraparound goggle: cyan trim frame, blue-clear lens, dark side pods.
    groups.append(_g("visor_frame", _bpoly([(122, 102), (258, 98), (262, 136), (236, 146), (150, 146), (124, 138)], "none", f' stroke="{C["visor_frame"]}" stroke-width="{W(3)}" stroke-linejoin="round"')))
    groups.append(_g("visor_lens", _bpoly([(128, 106), (254, 102), (256, 133), (234, 141), (152, 141), (130, 134)], C["visor"], ' fill-opacity="0.42"')))
    groups.append(_g("extra_visor_pods", _bell(122, 122, 7, 14, C["visor_pod"]), _bell(261, 118, 7, 14, C["visor_pod"])))
    groups.append(_g("extra_visor_glint", _bpoly([(140, 110), (180, 108), (174, 114), (138, 116)], C["sclera"], ' fill-opacity="0.55"')))
    # Spiky voluminous silver hair: crown at the landmark, fringe falling over the brow.
    groups.append(_g("hair", _bpoly([
        (104, 118), (96, 92), (112, 70), (104, 52), (128, 44), (126, 22), (156, 26), (170, lm["hair_crown"]),
        (196, 20), (222, 10), (232, 34), (262, 34), (258, 56), (284, 70), (266, 84), (276, 104), (256, 100),
        (244, 76), (222, 94), (214, 72), (196, 98), (186, 70), (164, 96), (160, 72), (138, 98), (124, 96), (116, 120)], C["hair"])))
    groups.append(_g("extra_hair_lock_l", _bpoly([(112, 84), (132, 90), (110, 140), (100, 112)], C["hair"])))
    groups.append(_g("extra_hair_lock_r", _bpoly([(250, 80), (272, 88), (286, 124), (262, 108)], C["hair"])))
    # Dark orb, cyan rim and two vertical bar eyes, no mouth.
    ox, oy, r = ORB["cx"], ORB["cy"], ORB["r"]
    groups.append(_g("orb_shell", _bell(ox, oy, r, r, C["orb_shell"])))
    groups.append(_g("extra_orb_rim", _bell(ox, oy, r - 3, r - 3, "none", f' stroke="{C["accent"]}" stroke-width="{W(2)}" stroke-opacity="0.8"')))
    groups.append(_g("extra_orb_face", _bell(ox + 10, oy - 2, 32, 30, "#07111F")))
    groups.append(_g("orb_core", _bpoly([(ox + 1, oy - 14), (ox + 7, oy - 14), (ox + 7, oy + 10), (ox + 1, oy + 10)], C["orb_core"]),
                     _bpoly([(ox + 19, oy - 14), (ox + 25, oy - 14), (ox + 25, oy + 10), (ox + 19, oy + 10)], C["orb_core"])))
    groups.append(_g("extra_orb_eyes", _bell(ox + 4, oy - 2, 6, 15, C["orb_core"], ' fill-opacity="0.3"'), _bell(ox + 22, oy - 2, 6, 15, C["orb_core"], ' fill-opacity="0.3"')))
    header = ('<?xml version="1.0" encoding="UTF-8"?>\n'
              '<!-- VAN layered BLOCKOUT — construction scaffold, NOT admitted art. Generated by\n'
              '     tools/character_forge/build_reference_pack.py from measured landmarks of the front\n'
              '     view of Candidate B (CF-D-05-REV2_1). Proportions, pivots, layer topology and identity\n'
              '     palette are authoritative inputs; every silhouette must be redrawn over\n'
              '     reference/turnaround/turnaround_front.png by the M1 vector artist. -->\n')
    return header + f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {int(ART)} {int(ART)}" width="{int(ART)}" height="{int(ART)}">' + "".join(groups) + "</svg>\n"


# ── Overlay / aura composition template ────────────────────────────────────────────────────────
def overlay_template_svg(overlay: dict) -> str:
    cx, cy = P(LANDMARKS["centre_x"], (LANDMARKS["hair_crown"] + LANDMARKS["sole"]) / 2)
    body_r = (L(LANDMARKS["sole"]) - L(LANDMARKS["hair_crown"])) / 2  # inner presence radius = half character height
    head_c = P(LANDMARKS["face_cx"], (LANDMARKS["skull_top"] + LANDMARKS["chin"]) / 2)
    s = overlay["aura_zone_scales"]
    parts = [
        f'<rect x="0" y="0" width="{ART}" height="{ART}" fill="none" stroke="#00E5FF" stroke-width="4"/>',
        f'<rect x="{ART*.06}" y="{ART*.06}" width="{ART*.88}" height="{ART*.88}" fill="none" stroke="#00E5FF" stroke-dasharray="12 8" stroke-width="2"/>',
        f'<text x="{ART*.06+8}" y="{ART*.06+26}" font-size="22" fill="#00E5FF">6% gesture-safe margin (character + gestures stay inside)</text>',
        f'<line x1="{cx}" y1="0" x2="{cx}" y2="{ART}" stroke="#62EAF7" stroke-width="1"/>',
        f'<line x1="0" y1="{L(LANDMARKS["sole"])}" x2="{ART}" y2="{L(LANDMARKS["sole"])}" stroke="#62EAF7" stroke-width="1"/>',
    ]
    for key, label, colour in (("inner_presence", "Zone A inner presence 1.00×", "#00E5FF"), ("mid_interaction", "Zone B mid interaction 1.12×", "#3BA7FF"),
                               ("outer_semantic_min", "Zone C semantic 1.35×", "#8B5CF6"), ("outer_semantic_max", "Zone C semantic 1.70× (max)", "#8B5CF6")):
        r = body_r * s[key]
        parts.append(f'<circle cx="{cx}" cy="{cy}" r="{round(r,1)}" fill="none" stroke="{colour}" stroke-width="2" stroke-dasharray="6 6"/>')
        parts.append(f'<text x="{cx + r*0.71 + 6}" y="{cy - r*0.71}" font-size="20" fill="{colour}">{label} — ANDROID-NATIVE, never in .riv</text>')
    for dp, label in ((48, "48 dp minimized portrait crop"), (96, "96 dp overlay read")):
        r = 0.5 * ART * (48 / 96 if dp == 48 else 0.62)
        parts.append(f'<circle cx="{head_c[0]}" cy="{head_c[1]}" r="{round(r if dp==96 else W(80),1)}" fill="none" stroke="#F59E0B" stroke-width="2"/>')
        parts.append(f'<text x="{head_c[0] + W(82)}" y="{head_c[1] - (W(80) if dp==48 else r) + 20}" font-size="20" fill="#F59E0B">{label}</text>')
    for name, piv in rig_pivots().items():
        x, y = piv["artboard"]
        parts.append(f'<circle cx="{x}" cy="{y}" r="5" fill="#EF4444"/><text x="{x+8}" y="{y+5}" font-size="14" fill="#EF4444">{name}</text>')
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<!-- Artboard `Van` composition template: guides only (import as a locked, non-exported guide layer).\n'
            '     Zones A–C are drawn by Android (VanFieldGeometryEngine) AROUND the artboard; the .riv stays transparent. -->\n'
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{-ART*0.5} {-ART*0.5} {ART*2} {ART*2}" width="{int(ART*2)}" height="{int(ART*2)}">'
            f'<rect x="{-ART*0.5}" y="{-ART*0.5}" width="{ART*2}" height="{ART*2}" fill="#0B0F14"/>' + "".join(parts) + "</svg>\n")


# ── Interim character art (CF-D-05-REV2_1 owner choice: real Candidate B art until van.riv) ───
INTERIM_ROI = (0, 0, 360, 520)          # Candidate B front figure incl. the orb, board px
INTERIM_GAP_SEEDS = ((212, 430), (214, 470), (208, 500), (205, 512))  # enclosed background between the legs
INTERIM_ASSET = ROOT / "android" / "app" / "src" / "main" / "res" / "drawable-nodpi" / "van_candidate_b_front.png"


def interim_cutout(board):
    """Candidate B's front figure cut from its light background, at native resolution, placed in
    the same unit-square framing as the Rive artboard (see PROPORTIONS.yaml artboard_mapping).

    The background is flood-filled from the region's edges (the line art stops the fill) and
    from the enclosed gap between the legs; the mask is eroded one pixel to drop the halo and
    feathered for anti-aliasing. No upscaling: one output pixel is one Candidate B pixel."""
    from PIL import Image, ImageDraw, ImageFilter
    im = board.crop(INTERIM_ROI)
    marker = (255, 0, 255)
    work = im.copy()
    w, h = work.size
    seeds = [(x, 0) for x in range(0, w, 6)] + [(0, y) for y in range(0, h, 6)] + \
            [(w - 1, y) for y in range(0, h, 6)] + [(x, h - 1) for x in range(0, w, 6)] + list(INTERIM_GAP_SEEDS)
    for seed in seeds:
        if work.getpixel(seed) != marker:
            ImageDraw.floodfill(work, seed, marker, thresh=40)
    mask = Image.new("L", (w, h), 0)
    src, dst = work.load(), mask.load()
    for y in range(h):
        for x in range(w):
            if src[x, y] != marker:
                dst[x, y] = 255
    mask = mask.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.7))
    cut = im.convert("RGBA")
    cut.putalpha(mask)
    side = round(1 / _K)
    ox, oy = round(0.5 / _K - LANDMARKS["centre_x"]), round(0.07 / _K - LANDMARKS["hair_crown"])
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(cut, (INTERIM_ROI[0] + ox, INTERIM_ROI[1] + oy))
    return square, {"unit_square_px": side, "board_origin_in_square": [ox, oy], "roi_board_px": list(INTERIM_ROI)}


_K = 0.86 / (LANDMARKS["sole"] - LANDMARKS["hair_crown"])  # unit-square length per board px


# ── Pack writers ───────────────────────────────────────────────────────────────────────────────
def _save_png(img, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="PNG", optimize=False, compress_level=9)


def build() -> dict:
    from PIL import Image, ImageDraw
    import yaml
    board = Image.open(BOARD).convert("RGB")
    board_sha = sha256_file(BOARD)
    index = {"authority": {"path": _rel(BOARD), "sha256": board_sha, "size": list(board.size)}, "crops": []}

    def crop(name: str, box, folder: str, role: str, maps=None):
        path = PACK / "reference" / folder / f"{name}.png"
        _save_png(board.crop(tuple(int(round(v)) for v in box)), path)
        index["crops"].append({"file": _rel(path), "board_box": [int(round(v)) for v in box], "role": role, **({"maps_to": maps} if maps else {})})

    for view, box in TURNAROUND.items():
        crop(f"turnaround_{view}", box, "turnaround", "construction view (silhouette, proportion, clothing)")
    for name, box in REGIONS.items():
        crop(name, box, "details", "orb turnaround view" if name.startswith("orb_") else "detail/material reference")

    # Proportion guide: 4x front view with landmark lines.
    fx0, fy0, fx1, fy1 = TURNAROUND["front"]; k = 2
    guide = board.crop((fx0, fy0, fx1, fy1)).resize(((fx1 - fx0) * k, (fy1 - fy0) * k), Image.LANCZOS)
    d = ImageDraw.Draw(guide)
    for key in ("hair_crown", "skull_top", "brow_line", "eye_line", "chin", "shoulder_line", "belt", "crotch", "fingertips", "knee", "boot_top", "sole"):
        y = (LANDMARKS[key] - fy0) * k
        d.line([(0, y), (guide.width, y)], fill=(255, 64, 64), width=2); d.text((4, y + 2), key, fill=(255, 235, 59))
    x = (LANDMARKS["centre_x"] - fx0) * k; d.line([(x, 0), (x, guide.height)], fill=(0, 229, 255), width=1)
    _save_png(guide, PACK / "guides" / "proportion_guide_front.png")

    lm = LANDMARKS; height = lm["sole"] - lm["hair_crown"]; head = lm["chin"] - lm["hair_crown"]
    head_count = proportion_rule.head_count(lm["hair_crown"], lm["chin"], lm["sole"])
    low, high = proportion_rule.locked_range()
    proportions = {
        "source": "reference/turnaround/turnaround_front.png", "landmarks_board_px": LANDMARKS,
        "character_height_px": height,
        "head_count_definition": proportion_rule.DEFINITION,
        "head_count": round(head_count, 2),
        "locked_range": [round(low, 2), round(high, 2)],
        "within_lock": low <= head_count <= high,
        "head_count_skull_top_to_chin_for_construction": round(height / (lm["chin"] - lm["skull_top"]), 2),
        "ratios_of_height": {k: round((lm[k] - lm["hair_crown"]) / height, 3) for k in ("brow_line", "eye_line", "chin", "shoulder_line", "belt", "crotch", "knee", "sole")},
        "shoulder_width_heads": round((lm["shoulder_right"] - lm["shoulder_left"]) / (lm["face_right"] - lm["face_left"]), 2),
        "orb_board_px": ORB,
        "orb_diameter_over_head_height": round(2 * ORB["r"] / head, 2),
        "artboard_mapping": {"artboard": [ART, ART], "character_height_fraction": 0.86, "scale_artboard_units_per_board_px": round(_SCALE, 4), "top_margin_fraction": 0.07},
    }
    pivots = rig_pivots()
    palette_measured = measured_palette(board)
    lock = yaml.safe_load(IDENTITY_LOCK.read_text(encoding="utf-8"))["identity"]
    skin_token = lock["skin"]["canonical_token"]
    palette = {
        "authority": _rel(BOARD), "measured_ramps": palette_measured,
        "identity_lock_tokens": {"skin": skin_token, "hair": lock["hair"]["base"], "hair_shadow": lock["hair"]["shadow"], "iris": lock["eyes"]["iris"],
                                 "visor_lens": lock["visor"]["lens"], "visor_frame": lock["visor"]["frame"], "visor_side_pods": lock["visor"]["side_pods"], "jacket_dark": lock["clothing"]["jacket_dark"],
                                 "jacket_light": lock["clothing"]["jacket_light"], "underlayer": lock["clothing"]["underlayer"], "glove": lock["clothing"]["glove_token"],
                                 "orb_shell": lock["companion"]["shell"], "orb_core": lock["companion"]["core"]},
        "checks_delta_e2000": {
            "lock_skin_vs_measured_mid": round(delta_e2000(skin_token, palette_measured["skin"]["mid_p50"]), 2),
            "lock_hair_vs_measured_lit": round(delta_e2000(lock["hair"]["base"], palette_measured["hair"]["lit_p90"]), 2),
            "lock_visor_lens_vs_measured_mid": round(delta_e2000(lock["visor"]["lens"], palette_measured["visor_lens"]["mid_p50"]), 2),
        },
        "vector_shading_rule": "Flat base = identity-lock token; shadow and highlight shapes use the measured shadow_p10 / lit_p90 of the same material. Never shade by opacity over the body (body is opaque).",
    }
    aura = {"source_of_truth": [_rel(AURA_SPEC), _rel(STATUS_PALETTE), _rel(GLASS_TOKENS)], "source_sha256": {p: sha256_file(ROOT / p) for p in (_rel(AURA_SPEC), _rel(STATUS_PALETTE), _rel(GLASS_TOKENS))},
            "ownership": "ANDROID_NATIVE — this table tells the Rive author where the field lives so the character never competes with it; nothing here is drawn in the .riv",
            **aura_table()}
    overlay = overlay_spec()
    overlay["artboard"] = {"name": "Van", "units": [ART, ART], "transparent": True, "gesture_safe_margin_fraction": 0.06,
                           "rendered_size_dp": {"floating_resting": overlay["resting_avatar_dp"], "docked": overlay["dock_character_dp"], "minimized_portrait": 48, "full_preview": 320},
                           "aura_reach_check": f"resting avatar {overlay['resting_avatar_dp']:.0f} dp × 1.70 outer semantic = {overlay['resting_avatar_dp']*1.70:.0f} dp ≤ hit area {overlay['resting_hit_dp']:.0f} dp"}
    overlay["inner_presence_radius_rule"] = "Zone radii scale from half the character height, centred on the character's vertical midpoint (see guides/artboard_overlay_template.svg)."

    for name, data in (("PROPORTIONS.yaml", proportions), ("RIG_PIVOTS.yaml", {"units": "artboard (1000×1000)", "source": "measured front turnaround", "pivots": pivots}),
                       ("PALETTE_MEASURED.yaml", palette), ("AURA_STATE_TABLE.yaml", aura), ("OVERLAY_COMPOSITION.yaml", overlay)):
        (PACK / name).write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=120), encoding="utf-8")
    (PACK / "guides").mkdir(parents=True, exist_ok=True)
    (PACK / "guides" / "artboard_overlay_template.svg").write_text(overlay_template_svg(overlay), encoding="utf-8")
    (PACK / "blockout").mkdir(parents=True, exist_ok=True)
    (PACK / "blockout" / "van_layers_blockout.svg").write_text(blockout_svg(), encoding="utf-8")

    # State/action -> reference map, with explicit gaps.
    states = {"OFFLINE": 0, "CONNECTING": 1, "IDLE": 2, "ATTENTIVE": 3, "LISTENING": 4, "THINKING": 5, "SEARCHING": 6, "WORKING": 7, "DELEGATING": 8,
              "SPEAKING": 9, "WAITING": 10, "WAITING_FOR_OWNER": 11, "DEGRADED": 12, "WARNING": 13, "ERROR": 14, "SUCCESS": 15, "URGENT": 16, "SLEEPING": 17}
    sheet = lambda key: _rel(SUPPORTING / SEMANTIC_SHEETS[key])
    gaps = {"OFFLINE": "no panel; SLEEPING face with the orb dimmed, health shown by the aura (Android)",
            "CONNECTING": "no panel; OFFLINE→IDLE lift per STATE_ACTION_MATRIX",
            "SEARCHING": "no panel; THINKING eyes + scan head turn, orb as forward lens",
            "DELEGATING": "no panel; WORKING face + PRESENT_CARD arm outward, orb travels outward",
            "WAITING": "no panel; ATTENTIVE face with slower breathing",
            "DEGRADED": "no panel; IDLE face with flatter brows; health is shown by the aura, not the body",
            "POINT_LEFT": "reuse the POINT_TARGET arm chain aimed left", "POINT_RIGHT": "reuse the POINT_TARGET arm chain aimed right",
            "POINT_UP": "reuse the POINT_TARGET arm chain aimed up", "POINT_DOWN": "reuse the POINT_TARGET arm chain aimed down",
            "OPEN_PANEL": "no panel; PRESENT_CARD sweep outward", "CLOSE_PANEL": "no panel; PRESENT_CARD sweep inward"}
    ref_map = {"reference_policy": "OFF_MODEL_SEMANTIC_ONLY — the cited production-v3 sheets show what a state or action MEANS; "
                                   "their figure is off-model (tall, glowing visor, cyan face orb). Shape, proportion and palette come only "
                                   "from Candidate B (reference/turnaround, reference/details, blockout).",
               "on_model_reference": _rel(BOARD), "states": {}, "actions": {}}
    for s_, code in states.items():
        refs = [sheet(k) for k in SEMANTIC_STATES.get(s_, [])]
        ref_map["states"][s_] = {"code": code, "references": refs, **({"gap": gaps[s_]} if not refs else {})}
    actions = {"HELLO_WAVE": 1, "ACK_NOD": 2, "POINT_LEFT": 3, "POINT_RIGHT": 4, "POINT_UP": 5, "POINT_DOWN": 6, "POINT_TARGET": 7, "CELEBRATE": 8,
               "CAUTION": 9, "CONFIRM": 10, "SHRUG": 11, "PRESENT_CARD": 12, "OPEN_PANEL": 13, "CLOSE_PANEL": 14}
    for a, code in actions.items():
        refs = [sheet(k) for k in SEMANTIC_ACTIONS.get(a, [])]
        ref_map["actions"][a] = {"code": code, "references": refs, **({"gap": gaps[a]} if not refs else {})}
    ref_map["speech_visemes"] = {"references": [sheet("visemes")], "note": "viseme 0–4 mouth shapes; redraw on Candidate B's face"}
    ref_map["aura"] = {"references": [sheet("aura")], "note": "Android-native field; never drawn in the .riv"}
    (PACK / "STATE_ACTION_REFERENCE_MAP.yaml").write_text(yaml.safe_dump(ref_map, sort_keys=False, width=140), encoding="utf-8")
    (PACK / "REFERENCE_INDEX.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")

    # Interim character art: the app shows real Candidate B art until van.riv exists.
    square, mapping = interim_cutout(board.convert("RGB"))
    _save_png(square, PACK / "interim" / "van_candidate_b_front.png")
    INTERIM_ASSET.parent.mkdir(parents=True, exist_ok=True)
    _save_png(square, INTERIM_ASSET)
    (PACK / "interim" / "INTERIM_ART.yaml").write_text(yaml.safe_dump({
        "decision": "Owner choice 2026-09-24: until van.riv lands, VAN is shown as real Candidate B art, not the procedural drawing.",
        "source": _rel(BOARD), "source_sha256": board_sha,
        "android_asset": _rel(INTERIM_ASSET), "android_asset_sha256": sha256_file(INTERIM_ASSET),
        "framing": "unit square identical to the Rive artboard: character 86% of height, 7% top margin",
        **mapping,
        "limits": "a still: no expressions, blinks or gestures; motion is a gentle bob only. Replaced by van.riv.",
    }, sort_keys=False, allow_unicode=True, width=120), encoding="utf-8")

    # Review contact sheet of the whole pack.
    tiles = [ROOT / c["file"] for c in index["crops"]]
    cell, cols = 200, 6
    sheet = Image.new("RGB", (cols * cell, ((len(tiles) + cols - 1) // cols) * (cell + 14)), (11, 15, 20))
    dd = ImageDraw.Draw(sheet)
    for i, p in enumerate(tiles):
        im = Image.open(p).convert("RGB"); im.thumbnail((cell - 6, cell - 6), Image.LANCZOS)
        x, y = (i % cols) * cell, (i // cols) * (cell + 14)
        sheet.paste(im, (x + (cell - im.width) // 2, y + 3)); dd.text((x + 3, y + cell - 2), p.stem[:20], fill=(200, 210, 220))
    _save_png(sheet, PACK / "guides" / "reference_contact_sheet.png")
    return write_manifest()


def write_manifest() -> dict:
    files = sorted(p for p in PACK.rglob("*") if p.is_file() and p.name != MANIFEST.name)
    manifest = {"pack": "VAN-RIVE-REFERENCE-PACK", "generator": "tools/character_forge/build_reference_pack.py",
                "authority": {"path": _rel(BOARD), "sha256": sha256_file(BOARD)},
                "files": {p.relative_to(PACK).as_posix(): sha256_file(p) for p in files}}
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def check() -> list[str]:
    problems = []
    if not MANIFEST.is_file():
        return ["PACK_MANIFEST_MISSING"]
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest["authority"]["sha256"] != sha256_file(BOARD):
        problems.append("AUTHORITY_BOARD_CHANGED: rebuild the pack from the new authority")
    listed = set(manifest["files"])
    actual = {p.relative_to(PACK).as_posix() for p in PACK.rglob("*") if p.is_file() and p.name != MANIFEST.name}
    problems += [f"UNLISTED_FILE:{f}" for f in sorted(actual - listed)]
    problems += [f"MISSING_FILE:{f}" for f in sorted(listed - actual)]
    for f in sorted(listed & actual):
        if sha256_file(PACK / f) != manifest["files"][f]:
            problems.append(f"HASH_MISMATCH:{f}")
    return problems


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="build_reference_pack")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        problems = check()
        for p in problems: print("FAIL", p)
        print("REFERENCE_PACK_OK" if not problems else "")
        return 1 if problems else 0
    manifest = build()
    print(f"built {len(manifest['files'])} files into {_rel(PACK)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
