"""On-model key poses for every contract state and action, made from Candidate B itself.

Candidate B has one pose. Rather than draw VAN again (which drifts off-model), this builds a
cut-out puppet from the native Candidate B front view — head, forearms, orb and body — and
poses it about the rig pivots in RIG_PIVOTS.yaml. It is exactly what the Rive rig will do, so
each key pose doubles as a spec: the YAML beside it lists the bone rotations that produce it.

Faces change by feathered edits in Candidate B's own sampled colours: closed lids, brow
angles and mouth shapes (including the five visemes). These are construction references for
the rig author, not final art; the M2/M3 reviews judge the authored rig, not these images.

    python -m tools.character_forge.build_key_poses   # also run by build_reference_pack
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from .build_reference_pack import BOARD, PACK, interim_cutout, _rel

OUT = PACK / "keyposes"

# Pivots and part regions, Candidate B board px (front view).
NECK = (190.0, 176.0)
ELBOW_L = (100.0, 272.0)   # viewer-left: the open hand under the orb
ELBOW_R = (298.0, 292.0)   # viewer-right: the hanging arm
ORB = (67.0, 171.0, 54.0)
HEAD_POLY = [(92, 0), (300, 0), (300, 118), (268, 150), (238, 172), (200, 180), (165, 176),
             (136, 162), (122, 142), (100, 120)]
FOREARM_L_BOX = (0, 222, 101, 308)
FOREARM_R_BOX = (268, 290, 340, 400)

SKIN = (175, 106, 83)
SKIN_SHADE = (119, 65, 55)
BROW = (58, 42, 38)
MOUTH = (74, 42, 26)
TONGUE = (201, 120, 110)
TEETH = (242, 242, 240)
EYES = ((158.0, 122.0), (220.0, 122.0))


@dataclass
class Pose:
    """Bone rotations in degrees (counter-clockwise on screen), offsets in board px."""
    forearm_l: float = 0.0
    forearm_r: float = 0.0
    head_tilt: float = 0.0
    head_drop: float = 0.0
    orb_dx: float = 0.0
    orb_dy: float = 0.0
    orb_dim: float = 0.0
    eyes: str = "open"          # open | closed | half | up | side
    brows: str = "neutral"      # neutral | raised | concerned | focused | sad | alert
    mouth: str = "smile"        # smile | grin | flat | frown | o | viseme_0..viseme_4
    desaturate: float = 0.0
    prop: str | None = None     # card | panel
    note: str = ""

    def rig(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v not in (0.0, None, "") or k in ("eyes", "brows", "mouth")}


STATES: dict[str, Pose] = {
    "OFFLINE": Pose(eyes="closed", mouth="flat", head_drop=4, orb_dim=0.8, orb_dy=10, desaturate=0.85,
                    note="Powered down: eyes shut, orb dark and sunk; the aura is almost out."),
    "CONNECTING": Pose(eyes="up", brows="raised", mouth="flat", orb_dy=-6,
                       note="Lifting from OFFLINE: eyes up to the orb as it rises."),
    "IDLE": Pose(note="Candidate B's own pose: palm open under the orb, easy smile."),
    "ATTENTIVE": Pose(head_tilt=-3, brows="raised", mouth="smile", note="Brows up, head squared to the owner."),
    "LISTENING": Pose(head_tilt=7, brows="raised", mouth="flat", note="Head cocked to listen; mouth closed."),
    "THINKING": Pose(eyes="up", brows="focused", mouth="flat", head_tilt=-5, orb_dy=-8,
                     note="Eyes up and aside, one brow working; orb drifts up."),
    "SEARCHING": Pose(eyes="side", brows="focused", mouth="flat", head_tilt=-4, orb_dx=-14,
                      note="Scanning sideways; orb pushed forward as a lens."),
    "WORKING": Pose(forearm_l=-18, brows="focused", mouth="flat", note="Focused brows, hand working the orb."),
    "DELEGATING": Pose(forearm_r=75, orb_dx=-22, orb_dy=-10, mouth="smile",
                       note="Hand out, handing the task on; orb travels outward."),
    "SPEAKING": Pose(mouth="viseme_2", brows="raised", note="Mouth driven by visemes (see visemes/)."),
    "WAITING": Pose(brows="neutral", mouth="flat", head_tilt=3, note="Patient: flat mouth, slight tilt."),
    "WAITING_FOR_OWNER": Pose(forearm_r=100, brows="raised", mouth="flat", prop="card",
                              note="Holds the decision card up to the owner."),
    "DEGRADED": Pose(brows="concerned", mouth="flat", desaturate=0.35, note="Muted, uneasy; health shown by the aura."),
    "WARNING": Pose(brows="concerned", mouth="flat", head_tilt=-3, note="Concerned brows, lips pressed."),
    "ERROR": Pose(brows="sad", mouth="frown", head_drop=3, note="Apologetic: brows up in the middle, frown."),
    "SUCCESS": Pose(forearm_r=160, brows="raised", mouth="grin", note="Fist up, big grin."),
    "URGENT": Pose(brows="alert", mouth="o", head_tilt=-2, note="Alert brows, mouth open to speak up."),
    "SLEEPING": Pose(eyes="closed", mouth="flat", head_tilt=8, head_drop=8, orb_dim=0.6, orb_dy=14,
                     note="Dozing: head slumped, eyes shut, orb resting low."),
}

ACTIONS: dict[str, Pose] = {
    "HELLO_WAVE": Pose(forearm_r=170, mouth="grin", brows="raised", note="Forearm up, open hand waving at the elbow."),
    "ACK_NOD": Pose(head_drop=7, head_tilt=0, mouth="smile", eyes="half", note="Key pose of the nod: chin down."),
    "POINT_LEFT": Pose(forearm_l=-12, mouth="flat", eyes="side", note="Left arm leads out to the left."),
    "POINT_RIGHT": Pose(forearm_r=90, mouth="flat", note="Right forearm swung out horizontal."),
    "POINT_UP": Pose(forearm_r=178, eyes="up", mouth="flat", note="Right forearm straight up."),
    "POINT_DOWN": Pose(forearm_r=-28, mouth="flat", head_drop=3, note="Right forearm angled down and out."),
    "POINT_TARGET": Pose(forearm_r=125, mouth="flat", brows="focused", note="Aimed by attention_x/y (IK)."),
    "CELEBRATE": Pose(forearm_l=-115, forearm_r=175, head_tilt=4, mouth="grin", brows="raised",
                      note="Both hands up."),
    "CAUTION": Pose(forearm_r=150, brows="concerned", mouth="flat", note="Palm raised: hold on."),
    "CONFIRM": Pose(forearm_r=112, mouth="smile", brows="raised", note="Hand up in a thumbs-up position."),
    "SHRUG": Pose(forearm_l=-22, forearm_r=80, head_tilt=8, brows="raised", mouth="flat", note="Palms out, head tilted."),
    "PRESENT_CARD": Pose(forearm_r=78, prop="card", mouth="smile", note="Offers a card forward."),
    "OPEN_PANEL": Pose(forearm_l=-8, forearm_r=85, prop="panel", mouth="smile", note="Hands spread a panel open."),
    "CLOSE_PANEL": Pose(forearm_l=-55, forearm_r=35, mouth="flat", note="Hands come in to fold it away."),
}

VISEMES = {f"viseme_{i}": Pose(mouth=f"viseme_{i}", brows="raised") for i in range(5)}


def _rotate_part(part: Image.Image, pivot: tuple[float, float], degrees: float) -> Image.Image:
    if abs(degrees) < 0.01:
        return part
    return part.rotate(degrees, resample=Image.BICUBIC, center=pivot)


def _mask_from_poly(size, poly) -> Image.Image:
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).polygon(poly, fill=255)
    return m


def _cut(figure: Image.Image, mask: Image.Image) -> Image.Image:
    part = figure.copy()
    part.putalpha(ImageChops.multiply(figure.getchannel("A"), mask))
    return part


def _soft_ellipse(size, box, blur=1.2) -> Image.Image:
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).ellipse(box, fill=255)
    return m.filter(ImageFilter.GaussianBlur(blur))


def _paint(img: Image.Image, colour, mask: Image.Image) -> None:
    img.paste(Image.new("RGBA", img.size, colour + (255,)), (0, 0), ImageChops.multiply(mask, img.getchannel("A")))


def _face(head: Image.Image, pose: Pose, origin: tuple[int, int]) -> None:
    """Face edits in board px, shifted into the cut-out's frame by [origin]."""
    d = ImageDraw.Draw(head)
    size = head.size
    fx, fy = origin
    # Eyes (under the clear goggle: tint the lid with the lens colour so it sits behind it).
    lid = (150, 118, 125)
    for bx, by in EYES:
        ex, ey = bx + fx, by + fy
        if pose.eyes in ("closed", "half"):
            top = ey - 15 if pose.eyes == "closed" else ey - 15
            bottom = ey + 13 if pose.eyes == "closed" else ey + 1
            _paint(head, lid, _soft_ellipse(size, (ex - 19, top, ex + 19, bottom), 1.0))
            d.arc((ex - 17, ey - 12, ex + 17, ey + (8 if pose.eyes == "closed" else -2)), 20, 160, fill=(40, 30, 34), width=3)
        elif pose.eyes in ("up", "side"):
            # Shift the iris: repaint sclera, then a new iris in B's blue.
            _paint(head, (236, 240, 246), _soft_ellipse(size, (ex - 14, ey - 11, ex + 14, ey + 11), 0.8))
            ox, oy = (0, -5) if pose.eyes == "up" else (-6, 1)
            d.ellipse((ex + ox - 10, ey + oy - 10, ex + ox + 10, ey + oy + 10), fill=(33, 110, 196))
            d.ellipse((ex + ox - 5, ey + oy - 5, ex + ox + 5, ey + oy + 5), fill=(16, 35, 58))
            d.ellipse((ex + ox - 7, ey + oy - 8, ex + ox - 2, ey + oy - 3), fill=(255, 255, 255))
    # Brows: angle per mood, drawn over B's own brows in its brow colour.
    tilt = {"neutral": 0, "raised": 0, "concerned": 7, "focused": 5, "sad": -7, "alert": -4}[pose.brows]
    lift = {"neutral": 0, "raised": -4, "concerned": 0, "focused": 2, "sad": -2, "alert": -5}[pose.brows]
    if pose.brows != "neutral":
        for (bx, _), side in zip(EYES, (-1, 1)):
            ex = bx + fx
            inner = (ex - side * 14, 97 + fy + lift + tilt)
            outer = (ex + side * 18, 94 + fy + lift - tilt * 0.4)
            d.line([inner, outer], fill=BROW, width=5)
    # Mouth: cover B's smile with sampled skin, then draw the new shape.
    mx, my = 193.0 + fx, 153.0 + fy
    if pose.mouth != "smile":
        _paint(head, SKIN, _soft_ellipse(size, (mx - 20, my - 8, mx + 20, my + 8), 1.6))
    shapes = {
        "grin": lambda: (d.chord((mx - 16, my - 9, mx + 16, my + 9), 0, 180, fill=MOUTH),
                         d.chord((mx - 13, my - 6, mx + 13, my + 1), 0, 180, fill=TEETH)),
        "flat": lambda: d.line([(mx - 11, my + 1), (mx + 11, my + 1)], fill=MOUTH, width=3),
        "frown": lambda: d.arc((mx - 13, my - 1, mx + 13, my + 13), 200, 340, fill=MOUTH, width=3),
        "o": lambda: d.ellipse((mx - 6, my - 6, mx + 6, my + 7), fill=MOUTH),
        "viseme_0": lambda: d.line([(mx - 10, my + 1), (mx + 10, my + 1)], fill=MOUTH, width=3),
        "viseme_1": lambda: d.ellipse((mx - 9, my - 3, mx + 9, my + 4), fill=MOUTH),
        "viseme_2": lambda: (d.ellipse((mx - 11, my - 5, mx + 11, my + 8), fill=MOUTH),
                             d.ellipse((mx - 6, my + 2, mx + 6, my + 7), fill=TONGUE)),
        "viseme_3": lambda: (d.ellipse((mx - 13, my - 7, mx + 13, my + 11), fill=MOUTH),
                             d.chord((mx - 10, my - 6, mx + 10, my + 2), 180, 360, fill=TEETH),
                             d.ellipse((mx - 7, my + 3, mx + 7, my + 10), fill=TONGUE)),
        "viseme_4": lambda: d.ellipse((mx - 5, my - 7, mx + 5, my + 9), fill=MOUTH),
    }
    if pose.mouth in shapes:
        shapes[pose.mouth]()


def _prop(canvas: Image.Image, kind: str, anchor: tuple[float, float]) -> None:
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x, y = anchor
    if kind == "card":
        d.rounded_rectangle((x - 10, y - 70, x + 62, y - 20), 8, fill=(0, 229, 255, 55), outline=(0, 229, 255, 220), width=3)
        d.line([(x + 2, y - 55), (x + 46, y - 55)], fill=(0, 229, 255, 200), width=3)
        d.line([(x + 2, y - 42), (x + 34, y - 42)], fill=(0, 229, 255, 160), width=3)
    else:
        d.rounded_rectangle((x - 150, y - 90, x - 10, y - 10), 10, fill=(0, 229, 255, 40), outline=(0, 229, 255, 200), width=3)
    canvas.alpha_composite(layer)


def _forearm_tip(pivot, degrees, length, base_deg):
    a = math.radians(base_deg + degrees)
    return pivot[0] + length * math.cos(a), pivot[1] - length * math.sin(a)


def render(figure: Image.Image, origin: tuple[int, int], pose: Pose) -> Image.Image:
    """Pose the puppet. [figure] is the interim cut-out (unit-square framing); [origin] is where
    board px (0, 0) sits in it."""
    ox, oy = origin
    size = figure.size
    shift = lambda pts: [(x + ox, y + oy) for x, y in pts]
    box = lambda b: shift([(b[0], b[1]), (b[2], b[1]), (b[2], b[3]), (b[0], b[3])])
    at = lambda p: (p[0] + ox, p[1] + oy)

    head_m = _mask_from_poly(size, shift(HEAD_POLY))
    fl_m = _mask_from_poly(size, box(FOREARM_L_BOX))
    fr_m = _mask_from_poly(size, box(FOREARM_R_BOX))
    orb_m = _soft_ellipse(size, (ORB[0] - ORB[2] + ox, ORB[1] - ORB[2] + oy, ORB[0] + ORB[2] + ox, ORB[1] + ORB[2] + oy), 0.6)
    head_m = ImageChops.subtract(head_m, orb_m)
    rest_m = Image.new("L", size, 255)
    for m in (head_m, fl_m, fr_m, orb_m):
        rest_m = ImageChops.subtract(rest_m, m)

    body = _cut(figure, rest_m)
    head = _cut(figure, head_m)
    forearm_l = _cut(figure, fl_m)
    forearm_r = _cut(figure, fr_m)
    orb = _cut(figure, orb_m)

    _face(head, pose, origin)
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    # Neck filler so a tilted head never shows a gap at the collar.
    ImageDraw.Draw(canvas).ellipse((at(NECK)[0] - 18, at(NECK)[1] - 22, at(NECK)[0] + 18, at(NECK)[1] + 8), fill=SKIN_SHADE + (255,))
    canvas.alpha_composite(body)
    canvas.alpha_composite(_rotate_part(forearm_l, at(ELBOW_L), pose.forearm_l))
    canvas.alpha_composite(_rotate_part(forearm_r, at(ELBOW_R), pose.forearm_r))
    head = _rotate_part(head, at(NECK), pose.head_tilt)
    canvas.alpha_composite(head, (0, int(round(pose.head_drop))))
    if pose.orb_dim:
        dark = Image.new("RGBA", size, (2, 12, 28, 0))
        dark.putalpha(orb.getchannel("A").point(lambda a: int(a * pose.orb_dim)))
        orb = Image.alpha_composite(orb, dark)
    canvas.alpha_composite(orb, (int(pose.orb_dx), int(pose.orb_dy)))
    if pose.prop:
        tip = _forearm_tip(at(ELBOW_R), pose.forearm_r, 78, -90)
        _prop(canvas, pose.prop, tip)
    if pose.desaturate:
        grey = canvas.convert("LA").convert("RGBA")
        canvas = Image.blend(canvas, grey, pose.desaturate)
    return canvas


def build(board: Image.Image | None = None) -> dict:
    import yaml
    board = board or Image.open(BOARD).convert("RGB")
    figure, mapping = interim_cutout(board)
    origin = tuple(mapping["board_origin_in_square"])
    index = {"source": _rel(BOARD), "method": "cut-out puppet of Candidate B posed about RIG_PIVOTS; faces edited in sampled B colours",
             "status": "CONSTRUCTION_REFERENCE_NOT_FINAL_ART", "pivots_board_px": {"neck": list(NECK), "elbow_l": list(ELBOW_L), "elbow_r": list(ELBOW_R)},
             "states": {}, "actions": {}, "visemes": {}}
    for group, poses in (("states", STATES), ("actions", ACTIONS), ("visemes", VISEMES)):
        for i, (name, pose) in enumerate(poses.items()):
            path = OUT / group / f"{i:02d}_{name.lower()}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            render(figure, origin, pose).save(path, format="PNG", optimize=False, compress_level=9)
            index[group][name] = {"file": _rel(path), "rig": pose.rig(), "note": pose.note}
    (OUT / "KEY_POSES.yaml").write_text(yaml.safe_dump(index, sort_keys=False, allow_unicode=True, width=140), encoding="utf-8")
    _contact_sheet(index)
    return index


def _contact_sheet(index: dict) -> None:
    cell, cols = 200, 8
    entries = [(g, n, v["file"]) for g in ("states", "actions", "visemes") for n, v in index[g].items()]
    rows = (len(entries) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * (cell + 18)), (8, 12, 18))
    d = ImageDraw.Draw(sheet)
    root = Path(__file__).resolve().parents[2]
    for i, (group, name, file) in enumerate(entries):
        im = Image.open(root / file).convert("RGBA")
        im.thumbnail((cell, cell), Image.LANCZOS)
        x, y = (i % cols) * cell, (i // cols) * (cell + 18)
        tile = Image.new("RGBA", (cell, cell), (8, 12, 18, 255))
        tile.alpha_composite(im, ((cell - im.width) // 2, (cell - im.height) // 2))
        sheet.paste(tile.convert("RGB"), (x, y))
        d.text((x + 4, y + cell + 3), f"{group[:-1]}: {name.lower()}"[:30], fill=(190, 225, 235))
    sheet.save(OUT / "KEY_POSES_contact_sheet.png", format="PNG", optimize=False, compress_level=9)


if __name__ == "__main__":
    idx = build()
    print(f"built {sum(len(idx[g]) for g in ('states', 'actions', 'visemes'))} key poses into {_rel(OUT)}")
