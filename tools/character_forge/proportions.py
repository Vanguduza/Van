"""VAN body-proportion rule shared by the identity lock, the source landmarks and the SVG lint.

The lock defines head count as (hair crown to sole) / (hair crown to chin). Measuring it the same
way everywhere is what lets CI fail both a source image and an M1 vector sheet that drift from
the locked proportions — the mismatch that let an approved master contradict the lock.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml

ROOT = Path(__file__).resolve().parents[2]
IDENTITY_LOCK = ROOT / "visual-authority" / "character-forge" / "00-source" / "asset-pack" / "APPROVED_IDENTITY_LOCK.yaml"
DEFINITION = "hair_crown_to_chin_over_crown_to_sole"

# Layer groups whose geometry defines each landmark in an M1 vector sheet.
CROWN_GROUPS = ("hair", "extra_hair_back", "extra_hair_lock_l", "extra_hair_lock_r")
CHIN_GROUPS = ("face", "extra_jaw")


def head_count(crown_y: float, chin_y: float, sole_y: float) -> float:
    head = chin_y - crown_y
    if head <= 0 or sole_y <= chin_y:
        raise ValueError(f"landmarks out of order: crown={crown_y} chin={chin_y} sole={sole_y}")
    return (sole_y - crown_y) / head


def locked_range(lock: Mapping[str, Any] | None = None) -> tuple[float, float]:
    if lock is None:
        lock = yaml.safe_load(IDENTITY_LOCK.read_text(encoding="utf-8"))
    rule = lock["identity"]["proportions"]
    if rule.get("head_count_definition") != DEFINITION:
        raise ValueError(f"identity lock head_count_definition is not {DEFINITION}")
    target, tolerance = float(rule["head_count_target"]), float(rule["head_count_tolerance"])
    return round(target - tolerance, 6), round(target + tolerance, 6)


def svg_head_count(bounds: Mapping[str, tuple[float, float, float, float]]) -> float:
    """Head count from Inkscape `--query-all` boxes (x, y, w, h), y growing downwards.
    Crown = top of the hair groups; chin = bottom of face/jaw; sole = lowest point of any group."""
    crowns = [bounds[g][1] for g in CROWN_GROUPS if g in bounds]
    chins = [bounds[g][1] + bounds[g][3] for g in CHIN_GROUPS if g in bounds]
    if not crowns or not chins:
        raise ValueError("hair or face/jaw bounds missing")
    sole = max(y + h for _x, y, _w, h in bounds.values())
    return head_count(min(crowns), max(chins), sole)


def check(value: float, lock: Mapping[str, Any] | None = None) -> str | None:
    low, high = locked_range(lock)
    if low <= value <= high:
        return None
    return f"PROPORTION_OUTSIDE_LOCK:{value:.2f}_heads_not_in_{low:.2f}-{high:.2f}"
