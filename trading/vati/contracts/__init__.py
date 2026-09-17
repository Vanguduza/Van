"""JSON Schema contracts for VATI core events (Rev 2 §41)."""

from __future__ import annotations

import json
from pathlib import Path

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"

SCHEMA_NAMES = (
    "trading_mandate",
    "symbol_contract",
    "risk_snapshot",
    "trade_intent",
    "risk_decision",
    "execution_receipt",
    "strategy_capsule",
)


def load_schema(name: str) -> dict:
    if name not in SCHEMA_NAMES:
        raise KeyError(f"unknown VATI schema: {name}")
    return json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))


def required_keys(name: str) -> set[str]:
    return set(load_schema(name).get("required", []))
