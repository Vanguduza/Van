"""Adopt timeframe contracts across the capsule registry (§6.8, TRD-ENH-005).

Every capsule gains a `timeframe_contract` and therefore a new `capsule_hash`.
That rehash is indistinguishable from `silent_strategy_mutation` unless it
carries provenance, so each migration is verified field-by-field and writes a
record beside the registry.

Run with --check in CI to prove the registry and the records agree.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vati.core.canonical import canonical_hash  # noqa: E402
from vati.strategies.migration import MigrationError, verify_migration  # noqa: E402

REGISTRY = Path("trading/strategies/registry")
RECORDS = Path("trading/strategies/migrations/capsule_migrations.json")

#: Horizon → timeframe roles. A SWING capsule structures on H4 and times on M5;
#: a POSITION capsule works off daily structure. Derived from the capsule's own
#: declared horizon rather than guessed per strategy.
BY_HORIZON: dict[str, dict[str, str]] = {
    "SCALP":     {"structural": "H1",  "regime": "M15", "setup": "M5",  "execution": "M1"},
    "INTRADAY":  {"structural": "H4",  "regime": "H1",  "setup": "M15", "execution": "M5"},
    "SESSION":   {"structural": "H4",  "regime": "H1",  "setup": "M15", "execution": "M5"},
    "OVERNIGHT": {"structural": "D1",  "regime": "H4",  "setup": "H1",  "execution": "M15"},
    "SWING":     {"structural": "H4",  "regime": "H1",  "setup": "M15", "execution": "M5"},
    "POSITION":  {"structural": "D1",  "regime": "D1",  "setup": "H4",  "execution": "H1"},
}

#: End-of-day venues have one meaningful timeframe; pretending otherwise would
#: invent intraday structure the market does not have.
EOD_VENUES = ("ZSE", "VFEX")


def contract_for(doc: dict) -> dict[str, str]:
    disc = str(doc.get("discipline", ""))
    if any(v in disc.upper() for v in EOD_VENUES) or str(doc.get("strategy_id", "")).startswith(EOD_VENUES):
        return {"primary": "D1"}
    horizons = [str(h) for h in doc.get("horizons", [])]
    for h in ("POSITION", "SWING", "SESSION", "INTRADAY", "OVERNIGHT", "SCALP"):
        if h in horizons:
            return dict(BY_HORIZON[h])
    return {"primary": "H1"}


def migrate_one(doc: dict, *, now_unix: int) -> tuple[dict, dict]:
    new = copy.deepcopy(doc)
    new["timeframe_contract"] = contract_for(doc)
    body = {k: v for k, v in new.items() if k != "capsule_hash"}
    new["capsule_hash"] = canonical_hash(body)
    record = verify_migration(doc, new, migration_reason="MTF_SCHEMA_ADOPTION", migrated_at_unix=now_unix)
    return new, record.as_dict() | {"record_hash": record.record_hash}


def _record_body_hash(record: dict) -> str:
    body = {k: v for k, v in record.items() if k != "record_hash"}
    return canonical_hash(body)


def _verify_settled_registry() -> list[str]:
    """Return reconciliation failures for the already-migrated registry."""
    failures: list[str] = []
    records = json.loads(RECORDS.read_text()) if RECORDS.exists() else []
    by_strategy = {}
    for record in records:
        sid = str(record.get("strategy_id", ""))
        if not sid:
            failures.append("migration record without strategy_id")
            continue
        if record.get("record_hash") != _record_body_hash(record):
            failures.append(f"{sid}: migration record hash mismatch")
        by_strategy.setdefault(sid, []).append(record)

    for path in sorted(REGISTRY.glob("*.json")):
        if path.name.startswith("_"):
            continue
        doc = json.loads(path.read_text())
        sid = str(doc.get("strategy_id", path.stem))
        body = {k: v for k, v in doc.items() if k != "capsule_hash"}
        actual_hash = canonical_hash(body)
        if doc.get("capsule_hash") != actual_hash:
            failures.append(f"{sid}: current capsule_hash does not match current body")
            continue
        if "timeframe_contract" not in doc:
            failures.append(f"{sid}: timeframe_contract missing after migration")
            continue
        expected_contract = contract_for(doc)
        if doc["timeframe_contract"] != expected_contract:
            failures.append(
                f"{sid}: timeframe_contract drifted from deterministic migration rule "
                f"{doc['timeframe_contract']} != {expected_contract}")
        matching = [
            r for r in by_strategy.get(sid, ())
            if r.get("new_capsule_hash") == doc.get("capsule_hash")
        ]
        if not matching:
            failures.append(
                f"{sid}: current capsule hash {str(doc.get('capsule_hash'))[:12]} "
                "has no matching migration provenance")
        elif len(matching) > 1:
            failures.append(f"{sid}: duplicate migration provenance for current capsule")
    return failures


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="verify without writing")
    a = ap.parse_args(argv)

    if a.check:
        failures = _verify_settled_registry()
        if failures:
            for failure in failures:
                print(f"REFUSED {failure}", file=sys.stderr)
            return 1
        print("registry migration provenance reconciled")
        return 0

    now = int(time.time())
    records: list[dict] = []
    failures: list[str] = []

    for path in sorted(REGISTRY.glob("*.json")):
        if path.name.startswith("_"):
            continue
        doc = json.loads(path.read_text())
        if "timeframe_contract" in doc:
            continue
        try:
            new, record = migrate_one(doc, now_unix=now)
        except MigrationError as exc:
            failures.append(f"{path.name}: {exc}")
            continue
        records.append(record)
        path.write_text(json.dumps(new, indent=2, sort_keys=True) + "\n")
        print(f"migrated {path.name}: {new['timeframe_contract']}")

    if failures:
        for failure in failures:
            print(f"REFUSED {failure}", file=sys.stderr)
        return 1
    if records:
        RECORDS.parent.mkdir(parents=True, exist_ok=True)
        existing = json.loads(RECORDS.read_text()) if RECORDS.exists() else []
        RECORDS.write_text(json.dumps(existing + records, indent=2, sort_keys=True) + "\n")

    settled = _verify_settled_registry()
    if settled:
        for failure in settled:
            print(f"REFUSED {failure}", file=sys.stderr)
        return 1
    print("registry migration provenance reconciled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
