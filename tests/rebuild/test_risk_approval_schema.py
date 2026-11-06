"""Wire-level version admission, using the real JSON Schema validator."""
import itertools
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

SCHEMA = Path(__file__).resolve().parents[2] / "trading/vati/contracts/schemas/risk_decision.schema.json"
BINDINGS = {"intent_hash": "a" * 64, "mandate_hash": "b" * 64, "approval_schema_version": 2}


def historical_body():
    return {
        "trade_intent_id": "recorded-trade", "decision": "APPROVED", "reason_code": "OK", "reason_detail": "",
        "approved_size": "0.10", "approved_risk_pct": "0.001", "requested_risk_pct": "0.001",
        "portfolio_heat_before": "0", "portfolio_heat_after": "0.001", "constraints": [],
        "risk_policy_version": "risk-policy/2.0.0", "mandate_id": "recorded-mandate", "mandate_version": "1.0.0",
        "risk_snapshot_hash": "c" * 64, "decision_hash": "d" * 64,
    }


@pytest.mark.parametrize("present", list(itertools.product((False, True), repeat=3)))
def test_only_historical_or_complete_v2_bodies_are_admitted(present):
    schema = json.loads(SCHEMA.read_text())
    Draft202012Validator.check_schema(schema)
    body = historical_body() | {key: value for (key, value), included in zip(BINDINGS.items(), present) if included}
    assert Draft202012Validator(schema).is_valid(body) == (all(present) or not any(present))


@pytest.mark.parametrize("change", [
    {"approval_schema_version": 3}, {"intent_hash": "unsealed"}, {"mandate_hash": ""}, {"extra_authority": True},
])
def test_future_or_malformed_bindings_are_not_current_authority(change):
    validator = Draft202012Validator(json.loads(SCHEMA.read_text()))
    assert not validator.is_valid(historical_body() | BINDINGS | change)
