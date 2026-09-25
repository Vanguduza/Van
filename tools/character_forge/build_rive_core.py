#!/usr/bin/env python3
"""M2 — the VAN core rig as an RML project, generated from the admitted raster layer set.

The Rive CLI (pinned in TOOLS.yaml) is the build authority; this writes the project it builds:

    visual-authority/character-forge/09-rive-working/rml/van_core/
        rive.yaml, scene.rml, layers/NN_name.png (copied byte for byte from the admitted set)

How the rig is made, and why:

* **A skeleton of invisible joints, and the art as flat followers.** Rive draws the first
  sibling on top, and a group's children draw together, so parenting the images into a joint
  hierarchy would break Candidate B's stacking (the back of the hair would land in front of
  the jacket). Instead the joints are ``Node``s in a hierarchy at the rig's pivots, and each
  layer is an ``Image`` inside its own follower ``Node`` that copies one joint's world
  transform (``TransformConstraint``). The followers are siblings in the admitted layer order,
  so the neutral pose is the admitted set exactly and every part still moves with its joint.
* **Each state machine layer owns its own joints.** Layers run together and a keyed value
  persists until something keys it again, so the states, actions, gaze, blink, breathing,
  mouth and viseme layers each drive a separate node in the chain (the head's tilt, nod and
  gaze turn are three nested nodes), and every pose in a layer keys the same properties.
* **Public surface exactly as the contract.** Artboard ``Van``, state machine ``VanRuntime``,
  the nine inputs and eight triggers of ``visual-authority/rive_contract.json``, in its order.
* **Core scope (VAN_CORE_RIG_TASK.md).** IDLE (2), LISTENING (4), THINKING (5), SPEAKING (9);
  HELLO_WAVE (1), ACK_NOD (2), POINT_TARGET (7), each by trigger or by ``action_code``; gaze
  from ``attention_x/y``; blinks; ``mouth_open`` and visemes 0–4; breathing; orb drift. Any
  other state value holds IDLE. The artboard is transparent and carries no aura.
* **Two parts she was never painted with.** Candidate B's mouth is a closed smile and her
  eyes are open. The mouth interior (dark mouth, tongue, teeth; sized per viseme, opened by
  ``mouth_open``) is a small vector shape. The upper eyelids are her own skin painted over
  each eye by ``build_eyelids`` (``02-ai-working/rig``, pinned by hash), hung from the top of
  the opening with the closed lash line along their lower edge, and sliding down to blink. A
  few lash pixels of the open eye sit in the goggle-frame and hair layers, in front of any
  lid; a small patch of lid covers them only while the lid is down. The frame layer also
  holds the open eye's liner ring, whose scaled edge would show the sclera's white beneath, so
  while the eye is open her own pixels there are drawn in front of it. Everything else is
  Candidate B's own pixels.

    python3 -m tools.character_forge.build_rive_core
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
from pathlib import Path
from xml.sax.saxutils import quoteattr

import yaml

ROOT = Path(__file__).resolve().parents[2]
LAYER_SET = ROOT / "visual-authority" / "character-forge" / "06-raster-clean" / "candidate_b_front"
FEATURES = ROOT / "visual-authority" / "character-forge" / "03-masks" / "candidate_b_front_features.json"
PIVOTS = ROOT / "visual-authority" / "character-forge" / "00-source" / "reference-pack" / "RIG_PIVOTS.yaml"
CONTRACT = ROOT / "visual-authority" / "rive_contract.json"
PROJECT = ROOT / "visual-authority" / "character-forge" / "09-rive-working" / "rml" / "van_core"
EYELIDS = ROOT / "visual-authority" / "character-forge" / "02-ai-working" / "rig"

X, Y, ROT, SX, SY, OPACITY = 13, 14, 15, 16, 17, 18
FPS = 60
#: An open eyelid: folded almost flat onto the lash line (a zero scale would be singular).
LID_OPEN = 0.02
#: How far the closed lash line sags from the eye's corners towards its lower edge.
CLOSED_LASH_SAG = 0.5
#: Rest local position of every keyed joint. Keyframes on x/y are absolute local positions,
#: so the rig keys offsets from rest and this adds the rest back when writing them.
REST_XY: dict[str, tuple[float, float]] = {}
#: POINT_TARGET's held pose: right shoulder, elbow and wrist rotation (radians).
POINT_POSE = (-1.2, -1.1, -0.15)
#: Every pose must keep the whole figure this far (px) inside the artboard.
FRAME_MARGIN = 24

#: Which joint each admitted layer follows.
FOLLOWS = {
    "hair_back": "head", "jacket_back": "torso", "underlayer": "torso",
    "leg_l_upper": "body", "leg_l_lower": "body", "boot_l": "body",
    "leg_r_upper": "body", "leg_r_lower": "body", "boot_r": "body",
    "neck": "torso", "jacket": "torso",
    "arm_l_upper": "shoulder_l", "arm_l_fore": "elbow_l", "hand_l": "wrist_l",
    "arm_r_upper": "shoulder_r", "arm_r_fore": "elbow_r", "hand_r": "wrist_r",
    "face": "head", "sclera_l": "eye_l", "eye_l": "iris_l", "lid_l": "eye_l",
    "sclera_r": "eye_r", "eye_r": "iris_r", "lid_r": "eye_r",
    "brow_l": "brow_l", "brow_r": "brow_r", "mouth": "mouth",
    "visor_lens": "head", "visor_frame": "head", "hair": "head",
    "orb_shell": "orb", "orb_core": "orb",
}


class Ids:
    def __init__(self, start: int = 10) -> None:
        self.n = start

    def __call__(self) -> str:
        self.n += 1
        return f"0:{self.n}"


def attrs(**kw) -> str:
    return " ".join(f"{k}={quoteattr(str(v))}" for k, v in kw.items() if v is not None)


def num(v: float) -> str:
    return f"{v:.4f}".rstrip("0").rstrip(".") if abs(v) > 1e-9 else "0"


def polygon_centroid(points) -> tuple[float, float]:
    return (sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points))


class Rig:
    """Joints: name -> (parent, world rest position)."""

    def __init__(self, pivots: dict, feats: dict) -> None:
        p = pivots
        eye = {}
        for side in ("l", "r"):
            pts = feats["eyes"][side]["opening"]
            ys = [q[1] for q in pts]
            cx, _ = polygon_centroid(pts)
            eye[side] = (cx, min(ys) + 0.55 * (max(ys) - min(ys)))
            eye["top_" + side] = (cx, float(min(ys)))
        iris = {s: (feats["eyes"][s]["iris"]["cx"], feats["eyes"][s]["iris"]["cy"]) for s in ("l", "r")}
        brow = {s: polygon_centroid(feats["brows"][s]) for s in ("l", "r")}
        mouth = polygon_centroid(feats["mouth"])
        self.joints: dict[str, tuple[str | None, tuple[float, float]]] = {
            "body": (None, p["hips"]),
            "chest": ("body", p["chest"]),
            "torso": ("chest", p["chest"]),          # breathing scale, leaf
            "head_bob": ("chest", p["neck"]),         # breathing bob
            "neck": ("head_bob", p["neck"]),          # state tilt
            "nod": ("neck", p["neck"]),               # action nod
            "talk": ("nod", p["neck"]),               # speech lift with mouth_open
            "head": ("talk", p["neck"]),              # gaze turn; the face follows this
            "eye_l": ("head", eye["l"]), "eye_r": ("head", eye["r"]),
            "eyelid_l": ("head", eye["top_l"]), "eyelid_r": ("head", eye["top_r"]),  # blink
            "look_l": ("eye_l", iris["l"]), "look_r": ("eye_r", iris["r"]),  # state look
            "iris_l": ("look_l", iris["l"]), "iris_r": ("look_r", iris["r"]),  # gaze
            "brow_l": ("head", brow["l"]), "brow_r": ("head", brow["r"]),
            "mouth": ("head", mouth),
            "viseme": ("mouth", mouth),               # viseme width
            "mouth_open": ("viseme", mouth),          # opening height
            "shoulder_l": ("chest", p["shoulder_l"]), "elbow_l": ("shoulder_l", p["elbow_l"]),
            "wrist_l": ("elbow_l", p["wrist_l"]),
            "shoulder_r": ("chest", p["shoulder_r"]), "elbow_r": ("shoulder_r", p["elbow_r"]),
            "wrist_r": ("elbow_r", p["wrist_r"]),
            "orb_home": ("body", p["orb_anchor"]),    # state offset
            "orb": ("orb_home", p["orb_anchor"]),     # idle drift
        }


def load_inputs():
    manifest = json.loads((LAYER_SET / "LAYERS.json").read_text(encoding="utf-8"))
    feats = json.loads(FEATURES.read_text(encoding="utf-8"))
    raw = yaml.safe_load(PIVOTS.read_text(encoding="utf-8"))["pivots"]
    k = 1.0 / float(manifest["px_to_artboard"])
    pivots = {n: (v["artboard"][0] * k, v["artboard"][1] * k) for n, v in raw.items()}
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    return manifest, feats, pivots, contract


class Anim:
    """A LinearAnimation: keys[(object_id, property)] = [(frame, value), ...]."""

    def __init__(self, name: str, frames: int, loop: str = "oneShot") -> None:
        self.name, self.frames, self.loop = name, frames, loop
        self.keys: dict[tuple[str, int], list[tuple[int, float]]] = {}

    def key(self, obj: str, prop: int, *pts: tuple[float, float]) -> "Anim":
        self.keys[(obj, prop)] = [(int(round(t * FPS)), v) for t, v in pts]
        return self

    def rml(self, aid: str) -> str:
        out = [f'<LinearAnimation {attrs(loopValue=self.loop, fps=FPS, duration=max(self.frames, 1), name=self.name, id=aid)}>']
        by_obj: dict[str, list[tuple[int, list]]] = {}
        for (obj, prop), pts in self.keys.items():
            by_obj.setdefault(obj, []).append((prop, pts))
        for obj, props in by_obj.items():
            out.append(f'  <KeyedObject objectId="{obj}">')
            for prop, pts in props:
                out.append(f'    <KeyedProperty propertyKey="{prop}">')
                base = REST_XY.get(obj, (0.0, 0.0))[prop - X] if prop in (X, Y) else 0.0
                for i, (frame, value) in enumerate(pts):
                    value += base
                    if i < len(pts) - 1:
                        out.append(f'      <KeyFrameDouble value="{num(value)}" frame="{frame}" interpolationType="cubic">'
                                   '<CubicEaseInterpolator x1="0.42" y1="0" x2="0.58" y2="1"/></KeyFrameDouble>')
                    else:
                        out.append(f'      <KeyFrameDouble value="{num(value)}" frame="{frame}"/>')
                out.append('    </KeyedProperty>')
            out.append('  </KeyedObject>')
        out.append('</LinearAnimation>')
        return "\n".join(out)


def build(project: Path = PROJECT) -> dict:
    manifest, feats, pivots, contract = load_inputs()
    rig = Rig(pivots, feats)
    ids = Ids()
    project.mkdir(parents=True, exist_ok=True)
    (project / "layers").mkdir(exist_ok=True)
    (project / "rive.yaml").write_text("name: van_core\n", encoding="utf-8")

    artboard_id, style_id, sm_id = ids(), ids(), ids()
    joint_id = {name: ids() for name in rig.joints}
    world = {name: pos for name, (_parent, pos) in rig.joints.items()}
    REST_XY.clear()
    for name, (parent, pos) in rig.joints.items():
        px, py = (0.0, 0.0) if parent is None else world[parent]
        REST_XY[joint_id[name]] = (pos[0] - px, pos[1] - py)

    # --- the skeleton (draws nothing) -------------------------------------------------------
    def joint_xml(name: str, depth: int) -> list[str]:
        parent, pos = rig.joints[name]
        px, py = (0.0, 0.0) if parent is None else world[parent]
        pad = "  " * depth
        kids = [n for n, (p, _) in rig.joints.items() if p == name]
        rest_sy = LID_OPEN if name.startswith("eyelid_") else None
        head = f'{pad}<Node {attrs(x=num(pos[0] - px), y=num(pos[1] - py), scaleY=rest_sy, name="rig_" + name, id=joint_id[name])}'
        if not kids:
            return [head + "/>"]
        lines = [head + ">"]
        for k in kids:
            lines += joint_xml(k, depth + 1)
        return lines + [f"{pad}</Node>"]

    # --- the art: one follower per layer, front to back -----------------------------------
    assets, drawables, clip_shapes = [], [], []
    drawn = [r for r in manifest["layers"] if not r.get("empty")]
    asset_id = {}
    for r in drawn:
        src = LAYER_SET / r["file"]
        dst = project / "layers" / r["file"]
        shutil.copyfile(src, dst)
        if hashlib.sha256(dst.read_bytes()).hexdigest() != r["sha256"]:
            raise ValueError(f"{r['file']}: copy does not match the admitted hash")
        asset_id[r["name"]] = ids()
        assets.append(f'<ImageAsset {attrs(file="layers/" + r["file"], name=r["name"], id=asset_id[r["name"]])}/>')

    # Iris clip: the eye opening, following the blink joint, so an iris never leaves the eye.
    clip_id = {}
    for side in ("l", "r"):
        jx, jy = world[f"eye_{side}"]
        verts = "".join(f'<StraightVertex x="{num(x - jx)}" y="{num(y - jy)}"/>' for x, y in feats["eyes"][side]["opening"])
        shape_id = clip_id[side] = ids()
        clip_shapes.append(
            f'<Node name="follow_clip_{side}"><TransformConstraint targetId="{joint_id["eye_" + side]}" name="c"/>'
            f'<Shape name="eye_opening_{side}" id="{shape_id}"><PointsPath isClosed="true" name="p">{verts}</PointsPath></Shape></Node>')

    inner_mouth = inner_mouth_xml(world["mouth_open"], joint_id["mouth_open"])
    lids = load_eyelids(manifest)
    eyelids, sockets, overs = {}, {}, []
    for side in ("l", "r"):
        lid = lids[side]
        for key, row in (("eyelid_" + side, lid), ("eyelid_over_" + side, lid.get("over")),
                         ("eye_cover_" + side, lid.get("cover"))):
            if row is None:
                continue
            shutil.copyfile(EYELIDS / row["file"], project / "layers" / row["file"])
            asset_id[key] = ids()
            assets.append(f'<ImageAsset {attrs(file="layers/" + row["file"], name=key, id=asset_id[key])}/>')
        sockets[side] = eye_socket_xml(side, lid, world["eye_" + side], joint_id["eye_" + side], asset_id["eyelid_" + side])
        eyelids[side] = eyelid_xml(side, feats["eyes"][side]["opening"], world["eyelid_" + side],
                                   joint_id["eyelid_" + side], lid, asset_id["eyelid_" + side])
        for key, opacity in (("over", 0), ("cover", 1)):
            name = ("eyelid_over_" if key == "over" else "eye_cover_") + side
            if key in lid:
                joint_id[name] = ids()
                overs.append(head_patch_xml(name, lid[key], world["head"], joint_id["head"], joint_id[name],
                                            asset_id[name], opacity))
    for r in reversed(drawn):  # front to back: the first sibling draws on top
        name = r["name"]
        joint = FOLLOWS[name]
        jx, jy = world[joint]
        cx = r["offset_px"][0] + r["size_px"][0] / 2.0
        cy = r["offset_px"][1] + r["size_px"][1] / 2.0
        clip = f'<ClippingShape sourceId="{clip_id[name[-1]]}" name="clip"/>' if name in ("eye_l", "eye_r") else ""
        drawables.append(
            f'<Node name="follow_{name}"><TransformConstraint targetId="{joint_id[joint]}" name="c"/>'
            f'<Image {attrs(x=num(cx - jx), y=num(cy - jy), assetId=asset_id[name], name=name)}>{clip}</Image></Node>')
        if name == "visor_lens":
            drawables.append(inner_mouth)  # above the mouth layer, beneath the lens
        if name.startswith("lid_"):
            drawables.insert(len(drawables) - 1, eyelids[name[-1]])  # in front of the lash line
        if name == "hair":
            drawables[-1:-1] = overs  # in front of the frame and hair, which hold the strays
        if name.startswith("sclera_"):
            drawables.append(sockets[name[-1]])  # behind the eye, in front of the face

    animations, machine = state_machine(contract, joint_id, ids)

    doc = ['<Rive version="1" kind="fragment">',
           f'<Artboard {attrs(defaultStateMachineId=sm_id, styleId=style_id, width=manifest["canvas_px"][0], height=manifest["canvas_px"][1], name=contract["artboard"], id=artboard_id)}>',
           f'<LayoutComponentStyle name="Artboard Style" id="{style_id}"/>']
    doc += drawables + clip_shapes
    doc += joint_xml("body", 0)
    doc.append(machine.replace("__SM_ID__", sm_id))
    doc += [a for a in animations]
    doc.append("</Artboard>")
    doc += assets
    doc.append("</Rive>")
    (project / "scene.rml").write_text("\n".join(doc) + "\n", encoding="utf-8")
    return {"project": str(project), "layers": len(drawn),
            "animations": len(animations), "joints": len(rig.joints)}


def arm_extent(manifest: dict, pivots: dict, side: str, pose: tuple[float, float, float]) -> tuple[float, float, float, float]:
    """Bounding box (x0, x1, y0, y1) of one arm's layer rectangles with its shoulder, elbow and
    wrist rotated by ``pose`` (radians): forward kinematics over the rig's pivots."""
    layers = {r["name"]: r for r in manifest["layers"]}
    chain = [("shoulder", pose[0]), ("elbow", pose[1]), ("wrist", pose[2])]
    xs, ys = [], []
    for part, depth in ((f"arm_{side}_upper", 1), (f"arm_{side}_fore", 2), (f"hand_{side}", 3)):
        x, y = layers[part]["offset_px"]
        w, h = layers[part]["size_px"]
        pts = [(x, y), (x + w, y), (x, y + h), (x + w, y + h)]
        for joint, angle in reversed(chain[:depth]):
            cx, cy = pivots[f"{joint}_{side}"]
            c, s = math.cos(angle), math.sin(angle)
            pts = [(cx + (px - cx) * c - (py - cy) * s, cy + (px - cx) * s + (py - cy) * c) for px, py in pts]
        xs += [p[0] for p in pts]
        ys += [p[1] for p in pts]
    return min(xs), max(xs), min(ys), max(ys)


def load_eyelids(manifest: dict) -> dict:
    """The painted upper lids (``build_eyelids``), checked against their record and the art."""
    record = json.loads((EYELIDS / "EYELIDS.json").read_text(encoding="utf-8"))
    source = hashlib.sha256((ROOT / manifest["source"]).read_bytes()).hexdigest()
    if record["source_sha256"] != source:
        raise ValueError("EYELIDS.json was painted from another source than the admitted layer set")
    for side in ("l", "r"):
        lid = record["lids"][side]
        for row in (lid, lid.get("over"), lid.get("cover")):
            if row and hashlib.sha256((EYELIDS / row["file"]).read_bytes()).hexdigest() != row["sha256"]:
                raise ValueError(f"{row['file']}: does not match EYELIDS.json")
    return record["lids"]


def eyelid_xml(side: str, opening, pos, joint: str, lid: dict, asset: str) -> str:
    """The upper lid: her painted skin over the eye, hung from the top of the opening, closed at
    scaleY=1, with the closed lash line along the opening's lower edge."""
    rel = [(x - pos[0], y - pos[1]) for x, y in opening]
    # The closed lash line: a smooth arc between the eye's corners, sagging part of the way to
    # the opening's lower edge (following the opening's own outline drew an angular U).
    left, right = min(rel), max(rel)
    sag = CLOSED_LASH_SAG * (max(y for _x, y in rel) - (left[1] + right[1]) / 2)
    arc = [(left[0] + (right[0] - left[0]) * t, left[1] + (right[1] - left[1]) * t + 4 * sag * t * (1 - t))
           for t in (i / 16 for i in range(17))]
    lash = "".join(f'<StraightVertex x="{num(x)}" y="{num(y)}"/>' for x, y in arc)
    cx = lid["offset_px"][0] + lid["size_px"][0] / 2.0 - pos[0]
    cy = lid["offset_px"][1] + lid["size_px"][1] / 2.0 - pos[1]
    return (f'<Node name="follow_eyelid_{side}"><TransformConstraint targetId="{joint}" name="c"/>'
            f'<Node name="eyelid_{side}_hinge">'
            f'<Shape name="eyelid_{side}_lash"><PointsPath isClosed="false" name="p">{lash}</PointsPath>'
            f'<Stroke thickness="1.6" cap="round" join="round" name="lash"><SolidColor colorValue="FF2B1714" name="c"/></Stroke></Shape>'
            f'<Image {attrs(x=num(cx), y=num(cy), assetId=asset, name="eyelid_" + side)}/></Node></Node>')


def eye_socket_xml(side: str, lid: dict, pos, joint: str, asset: str) -> str:
    """The painted lid skin, whole, beneath the eye's layers. Scaled on a phone, the soft edges
    of the sclera and lash images let the face layer's pale fill under the eye show as a thin
    light line round each eye; with her skin behind them, any seam shows skin instead."""
    cx = lid["offset_px"][0] + lid["size_px"][0] / 2.0 - pos[0]
    cy = lid["offset_px"][1] + lid["size_px"][1] / 2.0 - pos[1]
    return (f'<Node name="follow_eye_socket_{side}"><TransformConstraint targetId="{joint}" name="c"/>'
            f'<Image {attrs(x=num(cx), y=num(cy), assetId=asset, name="eye_socket_" + side)}/></Node>')


def head_patch_xml(name: str, patch: dict, head, joint: str, node_id: str, asset: str, opacity: int) -> str:
    """A patch drawn in front of the goggle frame and hair, following the head: ``eyelid_over``
    (the lid seen through the lens, over the open eye's lash pixels in those layers; shown only
    while the lid is down) or ``eye_cover`` (her open-eye pixels over the frame's liner ring,
    so its scaled edge never shows the sclera beneath; hidden while the lid is down)."""
    cx = patch["offset_px"][0] + patch["size_px"][0] / 2.0 - head[0]
    cy = patch["offset_px"][1] + patch["size_px"][1] / 2.0 - head[1]
    return (f'<Node name="follow_{name}" opacity="{opacity}" id="{node_id}"><TransformConstraint targetId="{joint}" name="c"/>'
            f'<Image {attrs(x=num(cx), y=num(cy), assetId=asset, name=name)}/></Node>')


def inner_mouth_xml(pos, joint) -> str:
    """The mouth interior, closed at scaleY≈0: a dark mouth with tongue and a strip of teeth."""
    w, h = 24.0, 12.0
    return (f'<Node name="follow_inner_mouth"><TransformConstraint targetId="{joint}" name="c"/>'
            f'<Node name="inner_mouth">'
            f'<Shape name="teeth" y="{num(-h * 0.32)}"><Rectangle width="{num(w * 0.62)}" height="{num(h * 0.22)}" cornerRadiusTL="1" cornerRadiusTR="1" cornerRadiusBL="1" cornerRadiusBR="1" originX="0.5" originY="0.5" name="p"/>'
            f'<Fill name="f"><SolidColor colorValue="FFF1ECE6" name="c"/></Fill></Shape>'
            f'<Shape name="tongue" y="{num(h * 0.22)}"><Ellipse width="{num(w * 0.62)}" height="{num(h * 0.45)}" originX="0.5" originY="0.5" name="p"/>'
            f'<Fill name="f"><SolidColor colorValue="FFB9575C" name="c"/></Fill></Shape>'
            f'<Shape name="mouth_dark"><Ellipse width="{num(w)}" height="{num(h)}" originX="0.5" originY="0.5" name="p"/>'
            f'<Fill name="f"><SolidColor colorValue="FF4A1B1E" name="c"/></Fill></Shape>'
            f'</Node></Node>')


def state_machine(contract: dict, J: dict, ids: Ids) -> tuple[list[str], str]:
    inputs = {}
    lines = [f'<StateMachine name="{contract["state_machine"]}" id="__SM_ID__">']
    for row in contract["inputs"]:
        iid = inputs[row["name"]] = ids()
        if row["type"] == "boolean":
            lines.append(f'  <StateMachineBool name="{row["name"]}" id="{iid}"/>')
        else:
            default = 2 if row["name"] == "state" else 0
            lines.append(f'  <StateMachineNumber name="{row["name"]}" value="{default}" id="{iid}"/>')
    for t in contract["triggers"]:
        iid = inputs[t] = ids()
        lines.append(f'  <StateMachineTrigger name="{t}" id="{iid}"/>')

    anims: list[str] = []

    def anim(a: Anim) -> str:
        aid = ids()
        anims.append(a.rml(aid))
        return aid

    def layer(name: str, body: list[str], entry_to: str) -> None:
        lines.append(f'  <StateMachineLayer name="{name}" id="{ids()}">')
        lines.append('    <AnyState x="600" y="-120"/><ExitState x="800" y="-120"/>')
        lines.append(f'    <EntryState x="0" y="-120"><StateTransition stateToId="{entry_to}"/></EntryState>')
        lines.extend("    " + b for b in body)
        lines.append('  </StateMachineLayer>')

    # --- breathing and orb drift: always running ------------------------------------------
    idle = Anim("idle_breathe", 4 * FPS, "loop")
    idle.key(J["torso"], SY, (0, 1.0), (2.0, 1.012), (4.0, 1.0))
    idle.key(J["head_bob"], Y, (0, 0.0), (2.0, -0.6), (4.0, 0.0))
    idle.key(J["orb"], Y, (0, 0.0), (2.0, -1.5), (4.0, 0.0))
    idle.key(J["orb"], ROT, (0, 0.0), (2.0, 0.03), (4.0, 0.0))
    sid = ids()
    layer("Breathe", [f'<AnimationState animationId="{anim(idle)}" x="200" y="0" id="{sid}"/>'], sid)

    # --- blink: two blinks in a 6 s loop, away from the first second -----------------------
    blink = Anim("blink", 6 * FPS, "loop")
    for side in ("l", "r"):
        o = LID_OPEN
        blink.key(J["eyelid_" + side], SY, (0, o), (2.30, o), (2.37, 1.0), (2.46, o),
                  (4.60, o), (4.67, 1.0), (4.76, o), (6.0, o))
        if "eyelid_over_" + side in J:
            blink.key(J["eyelid_over_" + side], OPACITY, (0, 0.0), (2.33, 0.0), (2.37, 1.0), (2.42, 0.0),
                      (4.63, 0.0), (4.67, 1.0), (4.72, 0.0), (6.0, 0.0))
        if "eye_cover_" + side in J:
            blink.key(J["eye_cover_" + side], OPACITY, (0, 1.0), (2.30, 1.0), (2.34, 0.0), (2.42, 0.0), (2.46, 1.0),
                      (4.60, 1.0), (4.64, 0.0), (4.72, 0.0), (4.76, 1.0), (6.0, 1.0))
    sid = ids()
    layer("Blink", [f'<AnimationState animationId="{anim(blink)}" x="200" y="0" id="{sid}"/>'], sid)

    # --- durable states ---------------------------------------------------------------------
    def pose(name, tilt=0.0, brow=0.0, look_x=0.0, look_y=0.0, orb=0.0):
        a = Anim(name, 1)
        a.key(J["neck"], ROT, (0, tilt))
        for side in ("l", "r"):
            a.key(J["brow_" + side], Y, (0, brow))
            a.key(J["look_" + side], X, (0, look_x))
            a.key(J["look_" + side], Y, (0, look_y))
        a.key(J["orb_home"], Y, (0, orb))
        return a

    states = {
        2: pose("state_idle"),
        4: pose("state_listening", tilt=math.radians(5), brow=-2.0),
        5: pose("state_thinking", tilt=math.radians(-4), brow=-1.0, look_x=2.0, look_y=-2.2, orb=-8.0),
        9: pose("state_speaking", tilt=math.radians(2), brow=-1.5),
    }
    sids = {code: ids() for code in states}
    body = []
    for i, (code, a) in enumerate(states.items()):
        aid = anim(a)
        trans = []
        for other in states:
            if other == code:
                continue
            if other == 2:  # anything that is not a core state returns to IDLE
                conds = "".join(f'<TransitionNumberCondition inputId="{inputs["state"]}" opValue="notEqual" value="{c}"/>' for c in (4, 5, 9))
            else:
                conds = f'<TransitionNumberCondition inputId="{inputs["state"]}" opValue="equal" value="{other}"/>'
            trans.append(f'<StateTransition stateToId="{sids[other]}" duration="300">{conds}</StateTransition>')
        body.append(f'<AnimationState animationId="{aid}" x="{200 + 200 * i}" y="0" id="{sids[code]}">{"".join(trans)}</AnimationState>')
    layer("State", body, sids[2])

    # --- gaze: attention_x turns the head a little and moves the irises; attention_y the irises
    def gaze(name, axis, shift=0.0, turn=0.0):
        a = Anim(name, 1)
        for side in ("l", "r"):
            a.key(J["iris_" + side], X if axis == "x" else Y, (0, shift))
        if axis == "x":
            a.key(J["head"], ROT, (0, turn))
        return a

    for axis, inp, poses in (
        ("x", "attention_x", (gaze("gaze_x_neg", "x", -3.5, -0.04), gaze("gaze_x_mid", "x"), gaze("gaze_x_pos", "x", 3.5, 0.04))),
        ("y", "attention_y", (gaze("gaze_y_neg", "y", -2.0), gaze("gaze_y_mid", "y"), gaze("gaze_y_pos", "y", 2.0))),
    ):
        sid = ids()
        blends = "".join(f'<BlendAnimation1D animationId="{anim(a)}" value="{v}"/>' for a, v in zip(poses, (-1, 0, 1)))
        layer(f"Gaze {axis}", [f'<BlendState1DInput inputId="{inputs[inp]}" x="200" y="0" id="{sid}">{blends}</BlendState1DInput>'], sid)

    # --- viseme width and mouth_open height ------------------------------------------------
    widths = {0: 0.55, 1: 1.0, 2: 1.15, 3: 0.6, 4: 0.45}
    vids = {v: ids() for v in widths}
    body = []
    for i, (v, wscale) in enumerate(widths.items()):
        a = Anim(f"viseme_{v}", 1)
        a.key(J["viseme"], SX, (0, wscale))
        aid = anim(a)
        trans = "".join(f'<StateTransition stateToId="{vids[o]}" duration="60"><TransitionNumberCondition inputId="{inputs["viseme"]}" opValue="equal" value="{o}"/></StateTransition>'
                        for o in widths if o != v)
        body.append(f'<AnimationState animationId="{aid}" x="{200 + 200 * i}" y="0" id="{vids[v]}">{trans}</AnimationState>')
    layer("Viseme", body, vids[0])

    closed = Anim("mouth_closed", 1).key(J["mouth_open"], SY, (0, 0.0)).key(J["mouth_open"], OPACITY, (0, 0.0))
    # A mouth this size is a few pixels on a phone overlay, so speech also lifts the head a
    # little as the mouth opens: the motion that reads at 48 dp, and what the emulator's
    # whole-frame comparison of mouth_open 0 and 1 can see.
    closed.key(J["talk"], Y, (0, 0.0))
    ajar = (Anim("mouth_open", 1).key(J["mouth_open"], SY, (0, 1.0)).key(J["mouth_open"], OPACITY, (0, 1.0))
            .key(J["talk"], Y, (0, -2.0)))
    sid = ids()
    layer("Mouth", [f'<BlendState1DInput inputId="{inputs["mouth_open"]}" x="200" y="0" id="{sid}">'
                    f'<BlendAnimation1D animationId="{anim(closed)}" value="0"/><BlendAnimation1D animationId="{anim(ajar)}" value="1"/></BlendState1DInput>'], sid)

    # --- actions: by trigger or by action_code; each returns to rest --------------------------
    arm = ("shoulder_r", "elbow_r", "wrist_r")

    none = Anim("action_none", 1)
    for j in arm:
        none.key(J[j], ROT, (0, 0.0))
    none.key(J["nod"], Y, (0, 0.0)).key(J["nod"], ROT, (0, 0.0))

    wave = Anim("action_hello_wave", int(1.9 * FPS))
    wave.key(J["shoulder_r"], ROT, (0, 0), (0.25, -1.05), (1.55, -1.05), (1.9, 0))
    wave.key(J["elbow_r"], ROT, (0, 0), (0.25, -1.55), (0.45, -1.25), (0.65, -1.7), (0.85, -1.25),
             (1.05, -1.7), (1.25, -1.25), (1.55, -1.55), (1.9, 0))
    wave.key(J["wrist_r"], ROT, (0, 0), (0.25, 0.1), (1.55, 0.1), (1.9, 0))
    wave.key(J["nod"], Y, (0, 0), (1.9, 0)).key(J["nod"], ROT, (0, 0), (0.3, -0.03), (1.55, -0.03), (1.9, 0))

    nod = Anim("action_ack_nod", int(1.8 * FPS))
    # A nod reads from the eyes as much as the head: lids half down with the chin. It holds as
    # long as the other actions (to 1.3 s): the emulator settles from the rig's first drawn
    # frame, so a nod over by 1.2 s was captured back at rest.
    nod.key(J["nod"], Y, (0, 0), (0.2, 4.0), (1.3, 4.0), (1.45, 1.0), (1.6, 2.5), (1.8, 0))
    nod.key(J["nod"], ROT, (0, 0), (0.2, 0.05), (1.3, 0.05), (1.8, 0))
    for side in ("l", "r"):
        nod.key(J["eyelid_" + side], SY, (0, LID_OPEN), (0.2, 0.5), (1.3, 0.5), (1.8, LID_OPEN))
        if "eyelid_over_" + side in J:
            nod.key(J["eyelid_over_" + side], OPACITY, (0, 0.0), (0.2, 1.0), (1.3, 1.0), (1.8, 0.0))
        if "eye_cover_" + side in J:
            nod.key(J["eye_cover_" + side], OPACITY, (0, 1.0), (0.1, 0.0), (1.7, 0.0), (1.8, 1.0))
    for j in arm:
        nod.key(J[j], ROT, (0, 0), (1.8, 0))

    point = Anim("action_point_target", int(1.8 * FPS))
    # Up and out along a diagonal, the forearm raised: a straight arm out to the side put the
    # hand within a few pixels of the artboard edge, so framing cut it off.
    point.key(J["shoulder_r"], ROT, (0, 0), (0.25, POINT_POSE[0]), (1.45, POINT_POSE[0]), (1.8, 0))
    point.key(J["elbow_r"], ROT, (0, 0), (0.25, POINT_POSE[1]), (1.45, POINT_POSE[1]), (1.8, 0))
    point.key(J["wrist_r"], ROT, (0, 0), (0.25, POINT_POSE[2]), (1.45, POINT_POSE[2]), (1.8, 0))
    point.key(J["nod"], Y, (0, 0), (1.8, 0)).key(J["nod"], ROT, (0, 0), (0.25, 0.04), (1.45, 0.04), (1.8, 0))

    none_sid = ids()
    acts = {1: ("wave", wave), 2: ("ack", nod), 7: ("point", point)}
    act_sid = {code: ids() for code in acts}
    body_to = []
    for code, (trigger, _a) in acts.items():
        body_to.append(f'<StateTransition stateToId="{act_sid[code]}" duration="80"><TransitionTriggerCondition inputId="{inputs[trigger]}"/></StateTransition>')
        body_to.append(f'<StateTransition stateToId="{act_sid[code]}" duration="80"><TransitionNumberCondition inputId="{inputs["action_code"]}" opValue="equal" value="{code}"/></StateTransition>')
    body = [f'<AnimationState animationId="{anim(none)}" x="200" y="0" id="{none_sid}">{"".join(body_to)}</AnimationState>']
    for i, (code, (_t, a)) in enumerate(acts.items()):
        back = f'<StateTransition stateToId="{none_sid}" duration="120" enableExitTime="true" exitTimeIsPercetange="true" exitTime="100"/>'
        body.append(f'<AnimationState animationId="{anim(a)}" reset="true" x="{400 + 200 * i}" y="160" id="{act_sid[code]}">{back}</AnimationState>')
    layer("Action", body, none_sid)

    lines.append("</StateMachine>")
    return anims, "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=PROJECT)
    args = parser.parse_args(argv)
    print(json.dumps(build(args.out), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
