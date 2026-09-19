#!/usr/bin/env python3
"""Operator CLI for VAN's backups (P3-OPS-002).

    tools/ops/backup.py create  --database data/van_gateway.sqlite3 --into /backups
    tools/ops/backup.py verify  /backups/20260919T120000Z
    tools/ops/backup.py restore /backups/20260919T120000Z --database /tmp/restored.sqlite3
    tools/ops/backup.py drill   --database data/van_gateway.sqlite3

`drill` is the one to put in a cron. It takes a backup, restores it somewhere
scratch, and compares the restored database to the original table by table and by
audit-chain tip. It exits non-zero when they differ, which is the only way to
find out that backups have been silently producing an empty file for a month
*before* the day you need one.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from van_gateway.ops import backup as ops_backup  # noqa: E402


def _default_config_paths(repo_root: Path) -> list[Path]:
    """Configuration worth restoring, and nothing that is a secret in itself.

    The gateway's `.env` is included because losing it means losing the Fernet
    keys that every stored credential is encrypted with — a database restored
    without them is a database of ciphertext. It is the operator's job to put the
    backup somewhere that deserves it; saying so in `--help` is more honest than
    quietly omitting the one file that makes a restore work.
    """
    return [repo_root / "backend" / ".env", repo_root / "registries" / "projects.json"]


def main(argv: list[str] | None = None) -> int:
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="write a new backup")
    create.add_argument("--database", required=True)
    create.add_argument("--into", required=True, help="parent directory for timestamped backups")

    check = sub.add_parser("verify", help="recompute every digest in a backup")
    check.add_argument("backup_dir")

    put_back = sub.add_parser("restore", help="restore a verified backup")
    put_back.add_argument("backup_dir")
    put_back.add_argument("--database", required=True)
    put_back.add_argument("--overwrite", action="store_true")

    run_drill = sub.add_parser("drill", help="back up, restore, and compare")
    run_drill.add_argument("--database", required=True)
    run_drill.add_argument("--workspace", default=None)

    args = parser.parse_args(argv)

    if args.command == "create":
        destination = Path(args.into) / time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        manifest = ops_backup.create_backup(
            database_path=args.database, destination=destination,
            configuration_paths=_default_config_paths(repo_root),
            evidence_dir=repo_root / "evidence",
            project_state_dir=repo_root / "docs" / "project-state",
        )
        print(json.dumps({"destination": str(destination),
                          "entries": len(manifest.entries),
                          "schema_version": manifest.schema_version}, indent=2))
        return 0

    if args.command == "verify":
        report = ops_backup.verify(args.backup_dir)
        print(json.dumps(report, indent=2))
        return 0 if report["ok"] else 1

    if args.command == "restore":
        print(json.dumps(ops_backup.restore(
            args.backup_dir, database_path=args.database, overwrite=args.overwrite
        ), indent=2))
        return 0

    workspace = args.workspace or tempfile.mkdtemp(prefix="van-restore-drill-")
    report = ops_backup.drill(
        database_path=args.database, workspace=workspace,
        configuration_paths=_default_config_paths(repo_root),
        evidence_dir=repo_root / "evidence",
        project_state_dir=repo_root / "docs" / "project-state",
    )
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
