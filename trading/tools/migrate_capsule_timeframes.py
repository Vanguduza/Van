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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="verify without writing")
    a = ap.parse_args(argv)

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
        if not a.check:
            path.write_text(json.dumps(new, indent=2, sort_keys=True) + "\n")
        print(f"{'would migrate' if a.check else 'migrated'} {path.name}: {new['timeframe_contract']}")

    if failures:
        for f in failures:
            print(f"REFUSED {f}", file=sys.stderr)
        return 1
    if records and not a.check:
        RECORDS.parent.mkdir(parents=True, exist_ok=True)
        existing = json.loads(RECORDS.read_text()) if RECORDS.exists() else []
        RECORDS.write_text(json.dumps(existing + records, indent=2, sort_keys=True) + "\n")
    if not records:
        print("registry already migrated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
