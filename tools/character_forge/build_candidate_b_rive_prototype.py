"""Build a non-canonical articulated Rive prototype from the locked Candidate B artwork.

This intentionally stays outside the M1/M2 production lanes. It proves the mechanics
architecture without promoting raster cut-outs to production vector authority.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

from PIL import Image, ImageChops
import yaml
import vtracer

from .build_reference_pack import BOARD, interim_cutout
from .build_key_poses import (
    ACTIONS, STATES, ELBOW_L, ELBOW_R, FOREARM_L_BOX, FOREARM_R_BOX,
    HEAD_POLY, NECK, ORB, _cut, _mask_from_poly, _soft_ellipse,
)

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "visual-authority" / "character-forge" / "08-prototypes" / "candidate-b-mechanics"
CONTRACT = ROOT / "visual-authority" / "rive_contract.json"
IDENTITY_LOCK = ROOT / "visual-authority" / "character-forge" / "00-source" / "asset-pack" / "APPROVED_IDENTITY_LOCK.yaml"
KEY_POSES = ROOT / "visual-authority" / "character-forge" / "00-source" / "reference-pack" / "keyposes" / "KEY_POSES.yaml"
RIVE_BIN = shutil.which("rive") or "rive"
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _assert_candidate_b() -> dict:
    lock = yaml.safe_load(IDENTITY_LOCK.read_text(encoding="utf-8"))
    canonical = lock["canonical_visual"]
    source = ROOT / canonical["path"]
    observed = sha256_file(source)
    if observed != canonical["sha256"]:
        raise RuntimeError(f"Candidate B hash drift: {observed}")
    if source.resolve() != BOARD.resolve():
        raise RuntimeError("build_reference_pack.BOARD no longer points at Candidate B")
    return lock


def _rect_mask(size: tuple[int, int], box: tuple[int, int, int, int]) -> Image.Image:
    return _mask_from_poly(size, [
        (box[0], box[1]), (box[2], box[1]), (box[2], box[3]), (box[0], box[3])
    ])


def build_parts() -> tuple[dict[str, Path], dict[str, tuple[float, float]], int]:
    board = Image.open(BOARD).convert("RGB")
    figure, mapping = interim_cutout(board)
    ox, oy = mapping["board_origin_in_square"]
    size = figure.size
    head_m = _mask_from_poly(size, [(x + ox, y + oy) for x, y in HEAD_POLY])
    fl_m = _rect_mask(size, (FOREARM_L_BOX[0] + ox, FOREARM_L_BOX[1] + oy,
                              FOREARM_L_BOX[2] + ox, FOREARM_L_BOX[3] + oy))
    fr_m = _rect_mask(size, (FOREARM_R_BOX[0] + ox, FOREARM_R_BOX[1] + oy,
                              FOREARM_R_BOX[2] + ox, FOREARM_R_BOX[3] + oy))
    orb_m = _soft_ellipse(size, (ORB[0] - ORB[2] + ox, ORB[1] - ORB[2] + oy,
                                  ORB[0] + ORB[2] + ox, ORB[1] + ORB[2] + oy), 0.6)
    head_m = ImageChops.subtract(head_m, orb_m)
    rest_m = Image.new("L", size, 255)
    for mask in (head_m, fl_m, fr_m, orb_m):
        rest_m = ImageChops.subtract(rest_m, mask)

    assets = OUT / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    parts = {
        "body": _cut(figure, rest_m),
        "head": _cut(figure, head_m),
        "forearm_l": _cut(figure, fl_m),
        "forearm_r": _cut(figure, fr_m),
        "orb": _cut(figure, orb_m),
    }
    paths: dict[str, Path] = {}
    for name, image in parts.items():
        path = assets / f"{name}.png"
        image.save(path, format="PNG", optimize=False, compress_level=9)
        paths[name] = path

    pivots = {
        "head": (NECK[0] + ox, NECK[1] + oy),
        "forearm_l": (ELBOW_L[0] + ox, ELBOW_L[1] + oy),
        "forearm_r": (ELBOW_R[0] + ox, ELBOW_R[1] + oy),
        "orb": (ORB[0] + ox, ORB[1] + oy),
        "mouth": (193.0 + ox, 153.0 + oy),
    }
    return paths, pivots, size[0]


def trace_parts(paths: dict[str, Path]) -> dict[str, Path]:
    vector_dir = OUT / "vectors"
    vector_dir.mkdir(parents=True, exist_ok=True)
    traced: dict[str, Path] = {}
    for name, source in paths.items():
        out = vector_dir / f"{name}.svg"
        vtracer.convert_image_to_svg_py(
            str(source), str(out), colormode="color", hierarchical="stacked",
            mode="spline", filter_speckle=12, color_precision=5,
            layer_difference=24, corner_threshold=60, length_threshold=6,
            max_iterations=10, splice_threshold=45, path_precision=2,
        )
        traced[name] = out
    return traced


_NUM = r"[-+]?(?:\d*\.\d+|\d+)"
_TOKEN_RE = re.compile(rf"[MCZ]|{_NUM}")


def _parse_cubic_path(d: str):
    tokens = _TOKEN_RE.findall(d)
    i, cmd = 0, None
    start = current = None
    segments = []
    while i < len(tokens):
        if tokens[i] in ("M", "C", "Z"):
            cmd = tokens[i]
            i += 1
        if cmd == "M":
            current = (float(tokens[i]), float(tokens[i + 1]))
            start = current
            i += 2
            cmd = None
        elif cmd == "C":
            vals = list(map(float, tokens[i:i + 6]))
            if len(vals) != 6:
                raise ValueError("truncated cubic segment")
            i += 6
            end = (vals[4], vals[5])
            segments.append((current, (vals[0], vals[1]), (vals[2], vals[3]), end))
            current = end
            cmd = "C" if i < len(tokens) and tokens[i] not in ("M", "C", "Z") else None
        elif cmd == "Z":
            break
        else:
            raise ValueError(f"unsupported SVG path sequence near token {i}")
    if not segments or start is None:
        raise ValueError("empty traced path")
    if math.hypot(current[0] - start[0], current[1] - start[1]) > 0.05:
        raise ValueError("VTracer path is not cubic-closed")
    return segments
def _handle(origin, control) -> tuple[float, float]:
    dx, dy = control[0] - origin[0], control[1] - origin[1]
    return math.atan2(dy, dx), math.hypot(dx, dy)


def _translate_from_svg(value: str | None) -> tuple[float, float]:
    if not value:
        return 0.0, 0.0
    m = re.fullmatch(r"translate\(([-+0-9.]+)(?:[ ,]+)([-+0-9.]+)\)", value.strip())
    if not m:
        raise ValueError(f"unsupported SVG transform: {value}")
    return float(m.group(1)), float(m.group(2))


def _svg_path_to_points(d: str, tx: float, ty: float, pivot: tuple[float, float]) -> str:
    segments = _parse_cubic_path(d)
    vertices = []
    n = len(segments)
    for i, seg in enumerate(segments):
        point = seg[0]
        prev = segments[(i - 1) % n]
        in_rot, in_dist = _handle(point, prev[2])
        out_rot, out_dist = _handle(point, seg[1])
        x = point[0] + tx - pivot[0]
        y = point[1] + ty - pivot[1]
        vertices.append(
            f'<CubicDetachedVertex x="{x:.3f}" y="{y:.3f}" '
            f'inRotation="{in_rot:.7f}" inDistance="{in_dist:.3f}" '
            f'outRotation="{out_rot:.7f}" outDistance="{out_dist:.3f}"/>'
        )
    return '<PointsPath isClosed="true" name="Path">' + "".join(vertices) + '</PointsPath>'


def vector_node(name: str, rid: int, svg: Path, pivot: tuple[float, float], extra: str = "") -> tuple[str, int]:
    root = ET.fromstring(svg.read_text(encoding="utf-8"))
    paths = []
    for el in root:
        if el.tag.rsplit("}", 1)[-1] != "path":
            continue
        d = el.attrib.get("d")
        if not d:
            continue
        fill = (el.attrib.get("fill") or "#000000").lstrip("#").upper()
        if len(fill) != 6:
            raise ValueError(f"unsupported fill {fill!r}")
        tx, ty = _translate_from_svg(el.attrib.get("transform"))
        points = _svg_path_to_points(d, tx, ty, pivot)
        paths.append(
            '<Shape name="trace">' + points +
            f'<Fill><SolidColor colorValue="FF{fill}"/></Fill></Shape>'
        )
    # SVG paints later siblings on top; Rive paints earlier siblings on top.
    paths.reverse()
    x, y = pivot
    node = f'<Node x="{x:.3f}" y="{y:.3f}" name="{name}" id="0:{rid}">' + "".join(paths) + extra + '</Node>'
    return node, len(paths)


def _img(name: str, rid: int, aid: int, pivot: tuple[float, float], side: int) -> str:
    px, py = pivot
    return (
        f'<Image x="{px:.3f}" y="{py:.3f}" originX="{px/side:.7f}" originY="{py/side:.7f}" '
        f'assetId="0:{aid}" name="{name}" id="0:{rid}"/>'
    )


def _keyed(obj: int, prop: int, values: list[tuple[int, float]]) -> str:
    keys = "".join(
        f'<KeyFrameDouble value="{value:.7f}" interpolationType="linear"' + (f' frame="{frame}"' if frame else "") + '/>'
        for frame, value in values
    )
    return f'<KeyedObject objectId="0:{obj}"><KeyedProperty propertyKey="{prop}">{keys}</KeyedProperty></KeyedObject>'
def _pose_animation(name: str, aid: int, pose, pivots: dict[str, tuple[float, float]], action: bool = False) -> str:
    duration = 60 if action else 90
    items: list[str] = []
    if action:
        mid = 22
        end = duration
        if pose.forearm_l:
            items.append(_keyed(12, 15, [(0, 0), (mid, math.radians(pose.forearm_l)), (end, 0)]))
        if pose.forearm_r:
            items.append(_keyed(13, 15, [(0, 0), (mid, math.radians(pose.forearm_r)), (end, 0)]))
        if pose.head_tilt:
            items.append(_keyed(11, 15, [(0, 0), (mid, math.radians(pose.head_tilt)), (end, 0)]))
        if pose.head_drop:
            y = pivots["head"][1]
            items.append(_keyed(11, 14, [(0, y), (mid, y + pose.head_drop), (end, y)]))
        if pose.orb_dx:
            x = pivots["orb"][0]
            items.append(_keyed(14, 13, [(0, x), (mid, x + pose.orb_dx), (end, x)]))
        if pose.orb_dy:
            y = pivots["orb"][1]
            items.append(_keyed(14, 14, [(0, y), (mid, y + pose.orb_dy), (end, y)]))
    else:
        head_y = pivots["head"][1] + pose.head_drop
        orb_x = pivots["orb"][0] + pose.orb_dx
        orb_y = pivots["orb"][1] + pose.orb_dy
        items.extend([
            _keyed(11, 15, [(0, math.radians(pose.head_tilt)), (45, math.radians(pose.head_tilt) + 0.012), (90, math.radians(pose.head_tilt))]),
            _keyed(11, 14, [(0, head_y), (45, head_y - 1.5), (90, head_y)]),
            _keyed(12, 15, [(0, math.radians(pose.forearm_l))]),
            _keyed(13, 15, [(0, math.radians(pose.forearm_r))]),
            _keyed(14, 13, [(0, orb_x)]),
            _keyed(14, 14, [(0, orb_y), (45, orb_y - 2.5), (90, orb_y)]),
        ])
    if not items:
        items.append(_keyed(11, 18, [(0, 1)]))
    loop = "0" if action else "1"
    return f'<LinearAnimation loopValue="{loop}" duration="{duration}" name="{name}" id="0:{aid}">' + "".join(items) + "</LinearAnimation>"


def _viseme_shapes(mx: float, my: float) -> str:
    specs = [
        (500, "viseme_0", "Rectangle", 'width="20" height="2"'),
        (501, "viseme_1", "Ellipse", 'width="18" height="7"'),
        (502, "viseme_2", "Ellipse", 'width="24" height="13"'),
        (503, "viseme_3", "Ellipse", 'width="27" height="19"'),
        (504, "viseme_4", "Ellipse", 'width="11" height="18"'),
    ]
    out = [
        f'<Shape x="{mx:.2f}" y="{my:.2f}" name="MouthCover" id="0:490"><Ellipse width="45" height="22" originX="0.5" originY="0.5"/><Fill><SolidColor colorValue="FFAF6A53"/></Fill></Shape>'
    ]
    for rid, name, geom, attrs in specs:
        out.append(
            f'<Shape x="{mx:.2f}" y="{my:.2f}" opacity="0" name="{name}" id="0:{rid}">'
            f'<{geom} {attrs} originX="0.5" originY="0.5"/><Fill><SolidColor colorValue="FF4A2A1A"/></Fill></Shape>'
        )
    return "".join(out)
def _viseme_animations() -> tuple[str, str]:
    animations = []
    states = []
    for i in range(5):
        aid = 600 + i
        sid = 650 + i
        keyed = "".join(_keyed(500 + j, 18, [(0, 1 if i == j else 0)]) for j in range(5))
        animations.append(f'<LinearAnimation loopValue="1" duration="1" name="VISEME_{i}" id="0:{aid}">{keyed}</LinearAnimation>')
        states.append(f'<AnimationState x="{i*150}" y="80" animationId="0:{aid}" stateName="VISEME_{i}" id="0:{sid}"/>')
    transitions = "".join(
        f'<StateTransition stateToId="0:{650+i}"><TransitionNumberCondition inputId="0:108" opValue="equal" value="{i}"/></StateTransition>'
        for i in range(5)
    )
    layer = (
        '<StateMachineLayer name="SpeechViseme" id="0:640">'
        '<EntryState x="-220" y="0"><StateTransition stateToId="0:650"/></EntryState>'
        f'<AnyState x="-220" y="-120">{transitions}</AnyState><ExitState x="900" y="-120"/>' + "".join(states) + '</StateMachineLayer>'
    )
    return "".join(animations), layer




def _gaze_shapes(pivots: dict[str, tuple[float, float]]) -> str:
    """Candidate-B-colour iris overlays used only to prove the public gaze inputs."""
    head_x, head_y = pivots["head"]
    eyes = ((158.0, 122.0), (220.0, 122.0))
    # build_reference_pack maps the native front-board into the square with this offset.
    board = Image.open(BOARD).convert("RGB")
    _, mapping = interim_cutout(board)
    ox, oy = mapping["board_origin_in_square"]
    out = []
    for idx, (bx, by) in enumerate(eyes):
        rid = 700 + idx
        x, y = bx + ox - head_x, by + oy - head_y
        out.append(
            f'<Node x="{x:.3f}" y="{y:.3f}" name="GazeEye{idx}" id="0:{rid}">'
            '<Shape name="Iris"><Ellipse width="17" height="17" originX="0.5" originY="0.5"/>'
            '<Fill><SolidColor colorValue="FF1E88E5"/></Fill></Shape>'
            '<Shape name="Pupil"><Ellipse width="8" height="8" originX="0.5" originY="0.5"/>'
            '<Fill><SolidColor colorValue="FF0D47A1"/></Fill></Shape>'
            '<Shape x="-2.5" y="-3" name="Catchlight"><Ellipse width="3.5" height="3.5" originX="0.5" originY="0.5"/>'
            '<Fill><SolidColor colorValue="FFF2F6FA"/></Fill></Shape>'
            '</Node>'
        )
    return "".join(out)


def _gaze_layers(input_ids: dict[str, int], pivots: dict[str, tuple[float, float]]) -> tuple[str, str]:
    board = Image.open(BOARD).convert("RGB")
    _, mapping = interim_cutout(board)
    ox, oy = mapping["board_origin_in_square"]
    hx, hy = pivots["head"]
    base = [(158.0 + ox - hx, 122.0 + oy - hy), (220.0 + ox - hx, 122.0 + oy - hy)]
    anims = []
    # X: left / centre / right. Y: up / centre / down. Deliberately small so Candidate B stays on-model.
    for j, dx in enumerate((-4.5, 0.0, 4.5)):
        aid = 710 + j
        keyed = "".join(_keyed(700+i, 13, [(0, x+dx)]) for i, (x, _) in enumerate(base))
        anims.append(f'<LinearAnimation loopValue="1" duration="1" name="GAZE_X_{j}" id="0:{aid}">{keyed}</LinearAnimation>')
    for j, dy in enumerate((-3.5, 0.0, 3.5)):
        aid = 713 + j
        keyed = "".join(_keyed(700+i, 14, [(0, y+dy)]) for i, (_, y) in enumerate(base))
        anims.append(f'<LinearAnimation loopValue="1" duration="1" name="GAZE_Y_{j}" id="0:{aid}">{keyed}</LinearAnimation>')

    def layer(axis: str, lid: int, sid: int, aid: int, input_id: int) -> str:
        neg, neutral, pos = sid, sid+1, sid+2
        any_transitions = (
            f'<StateTransition stateToId="0:{neg}" duration="70"><TransitionNumberCondition inputId="0:{input_id}" opValue="lessThan" value="-0.33"/></StateTransition>'
            f'<StateTransition stateToId="0:{pos}" duration="70"><TransitionNumberCondition inputId="0:{input_id}" opValue="greaterThan" value="0.33"/></StateTransition>'
            f'<StateTransition stateToId="0:{neutral}" duration="70"><TransitionNumberCondition inputId="0:{input_id}" opValue="greaterThanOrEqual" value="-0.33"/><TransitionNumberCondition inputId="0:{input_id}" opValue="lessThanOrEqual" value="0.33"/></StateTransition>'
        )
        return (
            f'<StateMachineLayer name="Gaze{axis}" id="0:{lid}">'
            f'<EntryState x="0" y="0"><StateTransition stateToId="0:{neutral}"/></EntryState>'
            f'<AnyState x="0" y="-100">{any_transitions}</AnyState><ExitState x="600" y="-100"/>'
            f'<AnimationState x="120" y="80" animationId="0:{aid}" id="0:{neg}"/>'
            f'<AnimationState x="300" y="80" animationId="0:{aid+1}" id="0:{neutral}"/>'
            f'<AnimationState x="480" y="80" animationId="0:{aid+2}" id="0:{pos}"/>'
            '</StateMachineLayer>'
        )
    layers = layer("X", 720, 721, 710, input_ids["attention_x"]) + layer("Y", 730, 731, 713, input_ids["attention_y"])
    return "".join(anims), layers


def _mouth_open_layer(input_ids: dict[str, int]) -> tuple[str, str]:
    # MouthRig (489) owns the five viseme shapes. Viseme selection changes child opacity;
    # this orthogonal layer changes the whole mouth aperture, matching SPEECH_SPEC's additive jaw drive.
    closed = '<LinearAnimation loopValue="1" duration="1" name="MOUTH_CLOSED" id="0:740">' + _keyed(489, 17, [(0, 0.45)]) + '</LinearAnimation>'
    open_ = '<LinearAnimation loopValue="1" duration="1" name="MOUTH_OPEN" id="0:741">' + _keyed(489, 17, [(0, 1.28)]) + '</LinearAnimation>'
    m = input_ids["mouth_open"]
    speaking = input_ids["speaking"]
    layer = (
        '<StateMachineLayer name="MouthOpen" id="0:749">'
        '<EntryState x="0" y="0"><StateTransition stateToId="0:750"/></EntryState>'
        '<AnyState x="0" y="-100">'
        f'<StateTransition stateToId="0:751" duration="70"><TransitionBoolCondition inputId="0:{speaking}" opValue="equal"/><TransitionNumberCondition inputId="0:{m}" opValue="greaterThanOrEqual" value="0.35"/></StateTransition>'
        f'<StateTransition stateToId="0:750" duration="70"><TransitionNumberCondition inputId="0:{m}" opValue="lessThan" value="0.35"/></StateTransition>'
        f'<StateTransition stateToId="0:750" duration="70"><TransitionBoolCondition inputId="0:{speaking}" opValue="notEqual"/></StateTransition>'
        '</AnyState><ExitState x="520" y="-100"/>'
        '<AnimationState x="160" y="80" animationId="0:740" id="0:750"/>'
        '<AnimationState x="360" y="80" animationId="0:741" id="0:751"/>'
        '</StateMachineLayer>'
    )
    return closed + open_, layer


def build_rml(vectors: dict[str, Path], pivots: dict[str, tuple[float, float]], side: int) -> tuple[str, int]:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    input_tags = []
    next_id = 101
    input_ids: dict[str, int] = {}
    for item in contract["inputs"]:
        input_ids[item["name"]] = next_id
        typ = {"number": "StateMachineNumber", "boolean": "StateMachineBool"}[item["type"]]
        default = ' value="2"' if item["name"] == "state" else ""
        input_tags.append(f'<{typ} name="{item["name"]}"{default} id="0:{next_id}"/>')
        next_id += 1
    trigger_ids = {}
    for trig in contract["triggers"]:
        trigger_ids[trig] = next_id
        input_tags.append(f'<StateMachineTrigger name="{trig}" id="0:{next_id}"/>')
        next_id += 1

    state_animations, state_nodes, state_transitions = [], [], []
    for idx, (name, code) in enumerate(contract["durable_states"].items()):
        aid, sid = 300 + idx, 350 + idx
        state_animations.append(_pose_animation(name, aid, STATES[name], pivots, action=False))
        state_nodes.append(f'<AnimationState x="{(idx%6)*180}" y="{(idx//6)*120}" animationId="0:{aid}" stateName="{name}" id="0:{sid}"/>')
        state_transitions.append(f'<StateTransition stateToId="0:{sid}"><TransitionNumberCondition inputId="0:{input_ids["state"]}" opValue="equal" value="{code}"/></StateTransition>')
    action_animations, action_nodes, action_transitions = [], [], []
    for idx, (name, code) in enumerate(contract["finite_actions"].items()):
        aid, sid = 400 + idx, 450 + idx
        action_animations.append(_pose_animation(name, aid, ACTIONS[name], pivots, action=True))
        action_nodes.append(f'<AnimationState x="{(idx%5)*180}" y="{120+(idx//5)*120}" animationId="0:{aid}" stateName="{name}" id="0:{sid}"><StateTransition stateToId="0:449" flags="12" exitTime="100"/></AnimationState>')
        action_transitions.append(f'<StateTransition stateToId="0:{sid}"><TransitionNumberCondition inputId="0:{input_ids["action_code"]}" opValue="equal" value="{code}"/></StateTransition>')

    trigger_map = {"wave":"HELLO_WAVE","ack":"ACK_NOD","point":"POINT_TARGET","celebrate":"CELEBRATE","warning":"CAUTION","shrug":"SHRUG","present":"PRESENT_CARD","panel":"OPEN_PANEL"}
    for trig, action in trigger_map.items():
        sid = 450 + list(contract["finite_actions"]).index(action)
        action_transitions.append(f'<StateTransition stateToId="0:{sid}"><TransitionTriggerCondition inputId="0:{trigger_ids[trig]}"/></StateTransition>')

    viseme_animations, viseme_layer = _viseme_animations()
    gaze_animations, gaze_layers = _gaze_layers(input_ids, pivots)
    mouth_animations, mouth_layer = _mouth_open_layer(input_ids)
    head_extra = (
        _gaze_shapes(pivots) +
        '<Node name="MouthRig" id="0:489">' +
        _viseme_shapes(
            pivots["mouth"][0] - pivots["head"][0],
            pivots["mouth"][1] - pivots["head"][1],
        ) +
        '</Node>'
    )
    body, body_paths = vector_node("CandidateBBody", 10, vectors["body"], (0.0, 0.0))
    head, head_paths = vector_node("CandidateBHead", 11, vectors["head"], pivots["head"], head_extra)
    forearm_l, fl_paths = vector_node("CandidateBForearmL", 12, vectors["forearm_l"], pivots["forearm_l"])
    forearm_r, fr_paths = vector_node("CandidateBForearmR", 13, vectors["forearm_r"], pivots["forearm_r"])
    orb, orb_paths = vector_node("CandidateBOrb", 14, vectors["orb"], pivots["orb"])
    nodes = [orb, head, forearm_r, forearm_l, body]
    trace_path_count = body_paths + head_paths + fl_paths + fr_paths + orb_paths
    durable_layer = '<StateMachineLayer name="DurablePose" id="0:120"><EntryState x="-240" y="0"><StateTransition stateToId="0:352"/></EntryState><AnyState x="-240" y="-140">' + "".join(state_transitions) + '</AnyState><ExitState x="1200" y="-140"/>' + "".join(state_nodes) + '</StateMachineLayer>'
    action_layer = '<StateMachineLayer name="FiniteAction" id="0:440"><EntryState x="-240" y="0"><StateTransition stateToId="0:449"/></EntryState><AnyState x="-240" y="-140">' + "".join(action_transitions) + '</AnyState><ExitState x="1200" y="-140"/><AnimationState x="0" y="0" animationId="0:549" stateName="NO_ACTION" id="0:449"/>' + "".join(action_nodes) + '</StateMachineLayer>'
    neutral_animation = '<LinearAnimation loopValue="1" duration="1" name="NO_ACTION" id="0:549"><KeyedObject objectId="0:10"><KeyedProperty propertyKey="18"><KeyFrameDouble value="1"/></KeyedProperty></KeyedObject></LinearAnimation>'
    rml = (
        '<Rive version="1" kind="fragment"><Artboard defaultStateMachineId="0:100" '
        f'width="{side}" height="{side}" styleId="0:5" name="Van" id="0:2"><LayoutComponentStyle name="Artboard Style" id="0:5"/>' + "".join(nodes) +
        '<StateMachine name="VanRuntime" id="0:100">' + "".join(input_tags) +
        durable_layer + action_layer + viseme_layer + gaze_layers + mouth_layer + '</StateMachine>' +
        "".join(state_animations) + "".join(action_animations) + neutral_animation + viseme_animations + gaze_animations + mouth_animations +
        '</Artboard></Rive>\n'
    )
    return rml, trace_path_count


def main() -> int:
    lock = _assert_candidate_b()
    OUT.mkdir(parents=True, exist_ok=True)
    paths, pivots, side = build_parts()
    vectors = trace_parts(paths)
    rml, trace_path_count = build_rml(vectors, pivots, side)
    (OUT / "rive.yaml").write_text("name: van_candidate_b_mechanics_proto\nentry: scene.rml\n", encoding="utf-8")
    (OUT / "scene.rml").write_text(rml, encoding="utf-8")
    verify = subprocess.run([RIVE_BIN, str(OUT), "--verify", "--format=json"], text=True, capture_output=True)
    if verify.returncode:
        raise RuntimeError(verify.stdout + "\n" + verify.stderr)
    build = subprocess.run([RIVE_BIN, str(OUT), "--once", "--format=json"], text=True, capture_output=True)
    if build.returncode:
        raise RuntimeError(build.stdout + "\n" + build.stderr)
    built = OUT / "build" / "van_candidate_b_mechanics_proto.riv"
    receipt = {
        "schema_version": 1,
        "status": "NON_CANONICAL_MECHANICS_PROTOTYPE",
        "candidate_b_sha256": lock["canonical_visual"]["sha256"],
        "scene_sha256": sha256_file(OUT / "scene.rml"),
        "rive_sha256": sha256_file(built),
        "rive_version": subprocess.check_output([RIVE_BIN, "--version"], text=True).strip(),
        "artboard": "Van",
        "state_machine": "VanRuntime",
        "durable_states": 18,
        "finite_actions": 14,
        "visemes": 5,
        "trace_paths": trace_path_count,
        "vector_trace_sha256": {name: sha256_file(path) for name, path in vectors.items()},
        "aura_embedded": False,
        "production_admissible": False,
        "note": "Candidate-B cut-out traced to non-canonical vectors for mechanics proof; M1 reviewed semantic vectors and M2 owner pass remain mandatory.",
    }
    (OUT / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
