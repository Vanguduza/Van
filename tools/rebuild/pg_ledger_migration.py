#!/usr/bin/env python3
"""Explicit native operator migration; connection supplied through environment.

  VATI_PG_MIGRATION_DSN=<bound setting> python tools/rebuild/pg_ledger_migration.py --check
  ... --apply   # privileged native operation; never run by runtime startup

Do not paste credentials into a chat, command argument, receipt or log. An
explicit --apply here is an execution switch, not a substitute for deployment
admission, backup policy, owner authority or independent native verification.
"""
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/"trading"))


def main():
    if sys.argv[1:] not in (["--check"], ["--apply"]):
        raise SystemExit("Use --check or --apply")
    import psycopg
    from vati.core.ledger import LedgerError
    from vati.core.ledger_pg_migration import migrate_legacy_scope
    dsn = os.environ.get("VATI_PG_MIGRATION_DSN")
    if not dsn:
        raise SystemExit("VATI_PG_MIGRATION_DSN must be bound through environment settings")
    try:
        with psycopg.connect(dsn, autocommit=True, connect_timeout=5) as connection:
            report = migrate_legacy_scope(connection, apply=sys.argv[1] == "--apply")
    except LedgerError as exc:
        print(json.dumps({"status":"BLOCKED", "reason":str(exc), "changed":False}))
        return 1
    except Exception as exc:
        # Connection diagnostics may echo credentials. Preserve only the type.
        print(json.dumps({"status":"FAILED", "error_type":type(exc).__name__}))
        return 1
    print(json.dumps(report,indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
