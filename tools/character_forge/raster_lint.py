"""CF-D-09 — lint for a raster layer set, the M1 artifact when the art is Candidate B's pixels.

A raster set is a directory holding ``LAYERS.json`` and one PNG per rig layer, as written by
``build_raster_layers``. The lint re-derives everything it checks from the files on disk; it
never takes the manifest's word for a property it can measure:

* **integrity**: every layer PNG exists and matches the SHA-256 the manifest pins, and sits
  inside the canvas;
* **source**: the set was cut from the approved cut-out, byte for byte;
* **completeness**: every layer the rig drives exists and draws something;
* **fidelity**: composited in order, the layers reproduce the approved art. Outside the lens
  that is exact. Inside it a uniform tint cannot undo the very darkest pixels; at most
  ``LENS_MAX_PIXELS_OVER_8`` may differ by more than 8/255, and none by more than
  ``LENS_MAX_ERROR``;
* **provenance of hidden pixels**: every layer that carries pixels beyond its own says how
  they were made (``big-lama`` for AI-painted fill, ``sclera_white``, ``skin_rim``,
  ``lens_tint``, ``propagate``), and the totals are reported so a reviewer sees how much of
  the set is generated;
* **proportion**: crown-to-sole over crown-to-chin, measured from what the composite shows
  (the face layer's lowest visible row is the chin), is inside the identity lock.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from . import proportions

ROOT = Path(__file__).resolve().parents[2]
APPROVED_SOURCE = ROOT / "visual-authority" / "character-forge" / "00-source" / "reference-pack" / "interim" / "van_candidate_b_front.png"
#: The layers the rig drives; each must exist and draw something.
REQUIRED_RASTER_LAYERS = (
    "hair", "face", "neck", "jacket", "underlayer", "arm_l_upper", "arm_l_fore", "hand_l",
    "arm_r_upper", "arm_r_fore", "hand_r", "sclera_l", "eye_l", "lid_l", "sclera_r", "eye_r",
    "lid_r", "brow_l", "brow_r", "mouth", "visor_frame", "visor_lens", "orb_shell", "orb_core", "leg_l_upper",
    "leg_l_lower", "boot_l", "leg_r_upper", "leg_r_lower", "boot_r",
)
LENS_MAX_PIXELS_OVER_8 = 60
LENS_MAX_ERROR = 40
SCHEMA_VERSION = 1


@dataclass
class RasterLintReport:
    path: str
    findings: list[str]
    metrics: dict[str, Any]

    @property
    def ok(self) -> bool:
        return not self.findings

    def as_dict(self) -> dict[str, Any]:
        return {"path": self.path, "ok": self.ok, "findings": self.findings, "metrics": self.metrics}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def lint_raster_set(directory: Path, *, approved_source: Path = APPROVED_SOURCE) -> RasterLintReport:
    directory = Path(directory)
    findings: list[str] = []
    manifest_path = directory / "LAYERS.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return RasterLintReport(str(directory), [f"LAYERS_MANIFEST_UNREADABLE:{exc}"], {})
    if manifest.get("schema_version") != SCHEMA_VERSION:
        findings.append("LAYERS_SCHEMA_UNSUPPORTED")
    if manifest.get("decision") != "CF-D-09":
        findings.append("LAYERS_NOT_UNDER_CF_D_09")
    if not approved_source.is_file() or manifest.get("source_sha256") != _sha(approved_source):
        findings.append("SOURCE_IS_NOT_THE_APPROVED_CUTOUT")
    try:
        w, h = (int(x) for x in manifest["canvas_px"])
    except (KeyError, TypeError, ValueError):
        return RasterLintReport(str(directory), findings + ["CANVAS_UNDECLARED"], {})

    layers = manifest.get("layers") or []
    names = [str(layer.get("name")) for layer in layers]
    drawn: dict[str, np.ndarray] = {}
    order: list[str] = []
    for layer in layers:
        name = str(layer.get("name"))
        if layer.get("empty"):
            continue
        path = directory / str(layer.get("file") or "")
        if not path.is_file():
            findings.append(f"LAYER_FILE_MISSING:{name}")
            continue
        if _sha(path) != layer.get("sha256"):
            findings.append(f"LAYER_HASH_MISMATCH:{name}")
        img = np.asarray(Image.open(path).convert("RGBA")).astype(np.float64) / 255.0
        x, y = (int(v) for v in layer.get("offset_px") or (0, 0))
        if x < 0 or y < 0 or x + img.shape[1] > w or y + img.shape[0] > h:
            findings.append(f"LAYER_OUTSIDE_CANVAS:{name}")
            continue
        plane = np.zeros((h, w, 4))
        plane[y:y + img.shape[0], x:x + img.shape[1]] = img
        drawn[name] = plane
        order.append(name)
    fill_pixels: dict[str, int] = {}
    for layer in layers:
        extra = int(layer.get("underlap_pixels") or 0)
        if extra and not layer.get("underlap_fill"):
            findings.append(f"UNDERLAP_FILL_UNLABELLED:{layer.get('name')}")
        elif extra:
            fill_pixels[str(layer["underlap_fill"])] = fill_pixels.get(str(layer["underlap_fill"]), 0) + extra
    for name in REQUIRED_RASTER_LAYERS:
        if name not in names:
            findings.append(f"MISSING_LAYER:{name}")
        elif name not in drawn or not (drawn[name][..., 3] > 0).any():
            findings.append(f"EMPTY_LAYER:{name}")

    metrics: dict[str, Any] = {"layers": len(layers), "drawn": len(drawn), "canvas_px": [w, h],
                               "underlap_fill_pixels": dict(sorted(fill_pixels.items()))}
    if drawn:
        comp = np.zeros((h, w, 4))
        top = np.full((h, w), -1, dtype=np.int32)
        for i, name in enumerate(order):
            plane = drawn[name]
            a = plane[..., 3:4]
            comp[..., :3] = plane[..., :3] * a + comp[..., :3] * (1 - a)
            comp[..., 3:4] = a + comp[..., 3:4] * (1 - a)
            top[plane[..., 3] > 0.5] = i
        if approved_source.is_file():
            src = np.asarray(Image.open(approved_source).convert("RGBA")).astype(np.float64) / 255.0
            if src.shape[:2] != (h, w):
                findings.append("CANVAS_DOES_NOT_MATCH_SOURCE")
            else:
                src_pm = np.concatenate([src[..., :3] * src[..., 3:4], src[..., 3:4]], -1)
                err = np.abs(np.round(comp * 255) - np.round(src_pm * 255)).max(-1)
                lens = drawn["visor_lens"][..., 3] > 0 if "visor_lens" in drawn else np.zeros((h, w), bool)
                outside, inside = err[~lens], err[lens]
                metrics.update({
                    "recomposite_max_error_outside_lens": int(outside.max()) if outside.size else 0,
                    "recomposite_lens_pixels_over_8": int((inside > 8).sum()),
                    "recomposite_lens_max_error": int(inside.max()) if inside.size else 0,
                })
                if metrics["recomposite_max_error_outside_lens"] > 0:
                    findings.append(f"RECOMPOSITE_NOT_EXACT:{metrics['recomposite_max_error_outside_lens']}")
                if metrics["recomposite_lens_pixels_over_8"] > LENS_MAX_PIXELS_OVER_8 or \
                        metrics["recomposite_lens_max_error"] > LENS_MAX_ERROR:
                    findings.append("RECOMPOSITE_LENS_ERROR_OVER_BUDGET")
        # Proportion, measured from what is visible.
        visible = comp[..., 3] > 0.5
        hair_rows = [np.nonzero((drawn[n][..., 3] > 0.5).any(1))[0] for n in ("hair", "hair_back") if n in drawn]
        face_i = order.index("face") if "face" in order else -1
        face_rows = np.nonzero((top == face_i).any(1))[0] if face_i >= 0 else np.array([])
        body_rows = np.nonzero(visible.any(1))[0]
        if any(r.size for r in hair_rows) and face_rows.size and body_rows.size:
            crown = min(int(r.min()) for r in hair_rows if r.size)
            chin, sole = int(face_rows.max()) + 1, int(body_rows.max()) + 1
            try:
                value = proportions.head_count(crown, chin, sole)
                metrics["head_count"] = round(value, 3)
                problem = proportions.check(value)
                if problem:
                    findings.append(problem)
            except ValueError as exc:
                findings.append(f"PROPORTION_UNMEASURABLE:{exc}")
        else:
            findings.append("PROPORTION_UNMEASURABLE:hair_or_face_missing")
    return RasterLintReport(str(directory), sorted(set(findings)), metrics)
