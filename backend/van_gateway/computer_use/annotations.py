"""Data-only annotation of existing typed ComputerInteractionFabric candidates.

A model can reorder caller candidates and attach bounded notes. This module has
no client, executor or authority surface, and never creates an operation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class FabricAnnotation:
    candidate_id: str
    rank: int
    note: str | None = None


def annotate_fabric_operations(
    candidate_ids: Sequence[str], jev_response: Any,
) -> list[FabricAnnotation]:
    if (len(candidate_ids) > 512 or any(not isinstance(cid, str) or not cid for cid in candidate_ids)
            or len(set(candidate_ids)) != len(candidate_ids)):
        raise ValueError("INVALID_CALLER_CANDIDATES")
    original = [FabricAnnotation(cid, index) for index, cid in enumerate(candidate_ids)]
    if not isinstance(jev_response, Mapping) or set(jev_response) != {"ranking"}:
        return original
    ranking = jev_response.get("ranking")
    if not isinstance(ranking, list) or len(ranking) > len(candidate_ids):
        return original
    known, seen = set(candidate_ids), set()
    ordered = []
    for entry in ranking:
        if not isinstance(entry, Mapping) or set(entry) - {"candidate_id", "note"}:
            return original
        cid, note = entry.get("candidate_id"), entry.get("note")
        if (not isinstance(cid, str) or cid not in known or cid in seen
                or (note is not None and not isinstance(note, str))):
            return original
        seen.add(cid)
        ordered.append(FabricAnnotation(cid, len(ordered), note[:200] if note else None))
    for cid in candidate_ids:
        if cid not in seen:
            ordered.append(FabricAnnotation(cid, len(ordered)))
    return ordered
