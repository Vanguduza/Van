"""Rev 1.3 §§141-142 — shared canonical hashing and the VAN identifier namespace.

Every cross-service automation artifact is hashed from deterministic JSON so the
same semantic artifact produces the same digest on every runtime. This is what
lets workflow lineage live in VAN rather than in n8n's mutable workflow IDs
(§50): an artifact is identified by what it *means*, not by where it happens to
be deployed.
"""

from __future__ import annotations

import hashlib
import uuid
from decimal import Decimal
from typing import Any

import json

#: §148 — the compiler backend mapping is versioned independently of the IR.
NODE_CATALOG_VERSION = "van-n8n-catalog-1"
COMPILER_VERSION = "van-automation-compiler-1"

_PREFIXES = {
    "capability": "wfcap",
    "ir": "wfir",
    "artifact": "wfart",
    "run": "wfrun",
    "evidence": "wfev",
    "event": "ext",
    "browser_task": "btask",
    "browser_evidence": "bevd",
    "browser_capsule": "bwf",
    "intent": "intent",
    "proposal": "apro",
    "repair": "wfrep",
    "deadletter": "wfdl",
    "generation": "wfgen",
}


def _normalise(value: Any) -> Any:
    """Normalise before serialising so equal meanings hash equally (§141).

    Decimals become decimal strings rather than lossy floats, UUIDs become
    lower-case canonical strings, and sets become sorted lists. NaN/Infinity are
    rejected outright by ``allow_nan=False`` below.
    """
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, uuid.UUID):
        return str(value).lower()
    if isinstance(value, dict):
        return {str(k): _normalise(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalise(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_normalise(v) for v in value)
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("non_finite_float_in_canonical_artifact")
        return value
    return value


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        _normalise(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def digest(value: Any) -> str:
    """Prefixed digest, e.g. ``sha256:ab12...``."""
    return "sha256:" + hashlib.sha256(canonical_json(value)).hexdigest()


def new_id(kind: str) -> str:
    """Mint a stable prefixed identifier (§142).

    n8n workflow IDs are foreign runtime references and are never canonical VAN
    identifiers, so they never pass through here.
    """
    try:
        prefix = _PREFIXES[kind]
    except KeyError as exc:  # pragma: no cover - programming error
        raise ValueError(f"unknown identifier kind: {kind}") from exc
    return f"{prefix}_{uuid.uuid4().hex}"


__all__ = ["COMPILER_VERSION", "NODE_CATALOG_VERSION", "canonical_json", "digest", "new_id"]
