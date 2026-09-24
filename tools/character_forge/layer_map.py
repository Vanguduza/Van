from __future__ import annotations

from pathlib import Path
from typing import Any
import re
import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MAP = ROOT / "visual-authority" / "character-forge" / "00-source" / "production-v3" / "SEE_THROUGH_LAYER_MAP.yaml"


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def load_mapping(path: Path = DEFAULT_MAP) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("layer mapping is not a mapping")
    return data


def map_layer_names(names: list[str], path: Path = DEFAULT_MAP) -> dict[str, Any]:
    config = load_mapping(path)
    mapping = config.get("mapping") or {}
    aliases: dict[str, list[tuple[str, list[str]]]] = {}
    for semantic, row in mapping.items():
        for alias in row.get("aliases") or []:
            aliases.setdefault(_norm(str(alias)), []).append((semantic, list(row.get("target_groups") or [])))

    result = {"mapped": [], "unmapped": [], "ambiguous": []}
    for source in names:
        normalized = _norm(source)
        candidates: list[tuple[str, list[str]]] = []
        for alias, rows in aliases.items():
            if normalized == alias or normalized.startswith(alias + "_") or alias in normalized.split("_"):
                candidates.extend(rows)
        unique = {(semantic, tuple(targets)) for semantic, targets in candidates}
        if not unique:
            result["unmapped"].append(source)
        elif len(unique) > 1:
            result["ambiguous"].append({"source": source, "candidates": [
                {"semantic": semantic, "target_groups": list(targets)}
                for semantic, targets in sorted(unique)
            ]})
        else:
            semantic, targets = next(iter(unique))
            result["mapped"].append({
                "source": source,
                "semantic": semantic,
                "target_groups": list(targets),
                "visible_provenance": "DERIVED_VISIBLE",
                "hidden_provenance": "INFERRED_OCCLUSION",
            })
    result["ok"] = not result["unmapped"] and not result["ambiguous"]
    return result
