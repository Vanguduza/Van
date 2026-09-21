"""GAP-F-007 — every DegradedCode has a CATALOG entry and /health survives any of them."""
from __future__ import annotations

import pytest

from van_gateway.degraded.registry import CATALOG, DegradedRegistry
from van_gateway.models import DegradedCode


def test_every_degraded_code_is_catalogued():
    missing = [c.value for c in DegradedCode if c not in CATALOG]
    assert missing == [], f"DegradedCode members without a CATALOG entry: {missing}"


@pytest.mark.parametrize("code", list(DegradedCode))
def test_snapshot_never_raises_for_any_code(code):
    registry = DegradedRegistry()
    registry.set(code, True)
    snap = registry.snapshot()
    assert any(entry.code is code for entry in snap)
