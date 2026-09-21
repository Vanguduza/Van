"""TRD-ENH-005: a rehash cannot hide a logic change (blueprint Rev 1.1 §6.8)."""

from __future__ import annotations

import copy
import json

import pytest

from vati.strategies.migration import (
    LOGIC_FIELDS,
    CapsuleMigrationRecord,
    MigrationError,
    logic_unchanged,
    verify_migration,
)

CAPSULE = "trading/strategies/registry/FX-TREND-PULLBACK-01.json"


@pytest.fixture
def old():
    """The pre-migration shape. The registry is already migrated, so the
    contract is stripped to reconstruct what the migration ran against."""
    with open(CAPSULE) as fh:
        doc = json.load(fh)
    doc.pop("timeframe_contract", None)
    doc["capsule_hash"] = "pre-migration"
    return doc


@pytest.fixture
def migrated(old):
    new = copy.deepcopy(old)
    new["timeframe_contract"] = {"structural": "H4", "regime": "H1", "setup": "M15", "execution": "M5"}
    new["capsule_hash"] = "rehashed"
    return new


def test_clean_migration_is_accepted(old, migrated):
    r = verify_migration(old, migrated, migration_reason="MTF_SCHEMA_ADOPTION", migrated_at_unix=1)
    assert r.strategy_logic_changed is False
    assert r.migration_reason == "MTF_SCHEMA_ADOPTION"
    assert r.record_hash
    assert "timeframe_contract" in r.changed_fields


@pytest.mark.parametrize("field,value", [
    ("stop_model", "1 ATR"),
    ("target_model", "5 ATR"),
    ("entry_logic_ref", "vati.strategies.something_else"),
    ("eligible_regimes", ["RANGE"]),
    ("forbidden_regimes", []),
    ("risk_limits", {"max_risk_per_trade": "0.05"}),
    ("instruments", ["EURUSD"]),
])
def test_logic_change_is_refused(old, migrated, field, value):
    bad = copy.deepcopy(migrated)
    bad[field] = value
    with pytest.raises(MigrationError, match="strategy_logic_changed"):
        verify_migration(old, bad, migration_reason="MTF_SCHEMA_ADOPTION", migrated_at_unix=1)


def test_every_logic_field_is_checked(old, migrated):
    """The guard is only as good as its field list."""
    for field in LOGIC_FIELDS:
        bad = copy.deepcopy(migrated)
        bad[field] = "MUTATED" if not isinstance(old.get(field), (list, dict)) else ["MUTATED"]
        ok, moved = logic_unchanged(old, bad)
        assert not ok and field in moved, field


def test_non_migration_field_change_is_refused(old, migrated):
    bad = copy.deepcopy(migrated)
    bad["evidence_refs"] = ["fabricated"]
    with pytest.raises(MigrationError, match="non-migration fields"):
        verify_migration(old, bad, migration_reason="MTF_SCHEMA_ADOPTION", migrated_at_unix=1)


def test_unknown_reason_is_refused(old, migrated):
    with pytest.raises(MigrationError, match="unknown migration_reason"):
        verify_migration(old, migrated, migration_reason="BECAUSE", migrated_at_unix=1)


def test_strategy_id_cannot_change(old, migrated):
    bad = copy.deepcopy(migrated)
    bad["strategy_id"] = "FX-SOMETHING-ELSE-01"
    with pytest.raises(MigrationError, match="strategy_id"):
        verify_migration(old, bad, migration_reason="MTF_SCHEMA_ADOPTION", migrated_at_unix=1)


def test_field_order_cannot_disguise_a_change(old, migrated):
    """Canonical comparison, so reordering a dict is not a change and reordering
    a list still is."""
    reordered = copy.deepcopy(migrated)
    reordered["risk_limits"] = dict(reversed(list(reordered["risk_limits"].items())))
    verify_migration(old, reordered, migration_reason="MTF_SCHEMA_ADOPTION", migrated_at_unix=1)
