"""Canonical JSON and hashing shared by every VATI component.

Determinism rule: the same object always serialises to the same bytes.
Decimals become strings, enums their values, sets sorted lists, dataclasses
dicts. Floats are refused in money/price fields by convention; if a float
reaches here it is serialised with repr() so it is at least stable."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from enum import Enum
from typing import Any


def dec(value: Any) -> Decimal:
    """Parse to Decimal via str() so floats never leak binary noise."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _default(o: Any) -> Any:
    if isinstance(o, Decimal):
        return str(o)
    if isinstance(o, Enum):
        return o.value
    if isinstance(o, (set, frozenset)):
        return sorted(str(x) for x in o)
    if is_dataclass(o) and not isinstance(o, type):
        return asdict(o)
    if isinstance(o, (bytes, bytearray)):
        return o.hex()
    if isinstance(o, float):
        return repr(o)
    raise TypeError(f"not canonicalisable: {type(o)!r}")


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=_default, ensure_ascii=True)


def canonical_hash(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()
