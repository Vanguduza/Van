"""Contract schemas parse, name the canonical fields, and stay aligned with the
dataclasses the Risk Authority actually consumes."""

from __future__ import annotations

import dataclasses
import json

import pytest

from vati.contracts import SCHEMA_DIR, SCHEMA_NAMES, load_schema, required_keys
from vati.risk import RiskDecision, RiskSnapshot, TradeIntent


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_schema_parses_and_is_closed(name):
    schema = load_schema(name)
    assert schema["$schema"].startswith("https://json-schema.org/")
    assert schema["additionalProperties"] is False
    assert schema["required"]


def test_no_unregistered_schema_files():
    on_disk = {p.stem.replace(".schema", "") for p in SCHEMA_DIR.glob("*.schema.json")}
    assert on_disk == set(SCHEMA_NAMES)


def test_risk_decision_schema_matches_dataclass():
    fields = {f.name for f in dataclasses.fields(RiskDecision)}
    assert fields == required_keys("risk_decision")


def test_risk_snapshot_schema_matches_dataclass():
    fields = {f.name for f in dataclasses.fields(RiskSnapshot)}
    assert fields == required_keys("risk_snapshot")


def test_trade_intent_dataclass_fields_exist_in_schema():
    props = set(load_schema("trade_intent")["properties"])
    fields = {f.name for f in dataclasses.fields(TradeIntent)}
    assert fields <= props, fields - props


def test_owner_authority_can_only_be_mandate():
    assert load_schema("trade_intent")["properties"]["owner_authority"]["enum"] == ["MANDATE"]


def test_mandate_fractions_are_decimal_strings_not_floats():
    schema = load_schema("trading_mandate")
    assert schema["$defs"]["fraction"]["type"] == "string"
    example = json.loads((SCHEMA_DIR.parent.parent.parent / "examples" / "mandate.fx_primary.example.json").read_text())
    from vati.risk import TradingMandate

    # P0-TRADE-001 — the example ships a placeholder and is refused at load, which is
    # correct: a committed file cannot carry a live owner signature, and one that appeared
    # to would be worse than one that does not.
    from vati.risk.mandate import MandateError

    with pytest.raises(MandateError, match="not owner-signed"):
        TradingMandate.from_mapping(example)

    from conftest import owner_authority

    example["owner_signature_ref"] = owner_authority().token(
        act="mandate-admit",
        subject=f"{example['mandate_id']}:{example['version']}",
        issued_at_unix=int(example["signed_at_unix"]),
        lifetime_seconds=int(example["expires_at_unix"]) - int(example["signed_at_unix"]),
    )
    m = TradingMandate.from_mapping(example)
    assert m.mode.value == "LIMITED_LIVE"
