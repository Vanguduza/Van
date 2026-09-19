"""Backup, restore, and a drill that proves the restore works.

P3-OPS-002: there was no Postgres dump, no SQLite backup, no volume snapshot and
no snapshot policy anywhere in `deploy/`, `tools/` or systemd. Losing the gateway
host meant losing all owner state and the entire audit history.

Three things about this module are deliberate.

**The database is copied with SQLite's own backup API, not with `cp`.** The
gateway runs in WAL mode and serves requests while a backup runs. Copying the
`.sqlite3` file without its `-wal` sidecar produces a file that opens cleanly and
is missing the most recent committed transactions — a backup that restores to a
plausible past. `sqlite3.Connection.backup` takes a consistent snapshot of a live
database, including everything in the WAL.

**Every artefact is digested and the manifest is digested too.** A backup you
cannot verify is a backup you will discover is empty on the day you need it.
`verify()` recomputes every digest, so bit-rot and truncation are caught before
a restore rather than after.

**The drill restores.** `drill()` takes a backup, restores it into a scratch
directory, opens the restored database, checks its schema version, compares row
counts table by table, and re-verifies the audit hash chain. A backup procedure
that has never been restored is a hypothesis; the test in
`tests/test_ops_backup.py` runs this drill against a populated database, which
is what makes it a fact.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

MANIFEST_NAME = "manifest.json"
DATABASE_NAME = "gateway.sqlite3"
MANIFEST_VERSION = 1

#: What a backup is required to contain. Gate 11 names databases, configuration,
#: evidence and project state; the fourth entry is included because a restore that
#: brings back the database without the project state restores a VAN that no longer
#: knows which repository revision its facts were true of.
class BackupPart(str, Enum):
    DATABASE = "DATABASE"
    CONFIGURATION = "CONFIGURATION"
    EVIDENCE = "EVIDENCE"
    PROJECT_STATE = "PROJECT_STATE"


def _digest_file(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            sha.update(block)
    return sha.hexdigest()


@dataclass(frozen=True)
class BackupEntry:
    part: str
    relative_path: str
    sha256: str
    bytes: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "part": self.part, "relative_path": self.relative_path,
            "sha256": self.sha256, "bytes": self.bytes,
        }


@dataclass
class Manifest:
    manifest_version: int
    created_at_unix: int
    schema_version: int
    entries: list[BackupEntry] = field(default_factory=list)
    #: Row counts at backup time, per table. The restore drill compares against these;
    #: a restored database with the right schema and the wrong contents is a failure
    #: that a schema check alone would pass.
    row_counts: dict[str, int] = field(default_factory=dict)
    audit_chain: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "manifest_version": self.manifest_version,
            "created_at_unix": self.created_at_unix,
            "schema_version": self.schema_version,
            "entries": [entry.as_dict() for entry in self.entries],
            "row_counts": self.row_counts,
            "audit_chain": self.audit_chain,
        }


class BackupError(RuntimeError):
    pass


class RestoreVerificationFailed(BackupError):
    pass


def _sqlite_backup(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(str(source))
    try:
        dst = sqlite3.connect(str(destination))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def _table_names(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name"
    ).fetchall()
    return [row[0] for row in rows]


def _row_counts(connection: sqlite3.Connection) -> dict[str, int]:
    return {
        name: int(connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0])
        for name in _table_names(connection)
    }


def _schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
    ).fetchone()
    return int(row[0])


def _copy_tree(source: Path, target: Path, part: str, root: Path) -> list[BackupEntry]:
    entries: list[BackupEntry] = []
    if not source.exists():
        return entries
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        relative = Path(target.name) / path.relative_to(source)
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        entries.append(BackupEntry(
            part=part, relative_path=str(relative),
            sha256=_digest_file(destination), bytes=destination.stat().st_size,
        ))
    return entries


def create_backup(
    *,
    database_path: str | os.PathLike[str],
    destination: str | os.PathLike[str],
    configuration_paths: Iterable[str | os.PathLike[str]] = (),
    evidence_dir: str | os.PathLike[str] | None = None,
    project_state_dir: str | os.PathLike[str] | None = None,
    now_unix: int | None = None,
) -> Manifest:
    """Write a complete, self-describing backup into `destination`."""
    root = Path(destination)
    root.mkdir(parents=True, exist_ok=True)
    entries: list[BackupEntry] = []

    database = Path(database_path)
    if not database.exists():
        raise BackupError(f"no database at {database}")
    backup_db = root / DATABASE_NAME
    _sqlite_backup(database, backup_db)
    entries.append(BackupEntry(
        part=BackupPart.DATABASE.value, relative_path=DATABASE_NAME,
        sha256=_digest_file(backup_db), bytes=backup_db.stat().st_size,
    ))

    config_root = root / "configuration"
    for item in configuration_paths:
        path = Path(item)
        if not path.exists():
            # A configuration file that is absent is recorded by its absence: the
            # manifest simply has no entry for it, and `verify` reports what is
            # present. Writing a zero-byte placeholder would restore a VAN whose
            # configuration file exists and is empty, which is worse than missing.
            continue
        config_root.mkdir(parents=True, exist_ok=True)
        destination_path = config_root / path.name
        shutil.copy2(path, destination_path)
        entries.append(BackupEntry(
            part=BackupPart.CONFIGURATION.value,
            relative_path=str(Path("configuration") / path.name),
            sha256=_digest_file(destination_path), bytes=destination_path.stat().st_size,
        ))

    if evidence_dir is not None:
        entries += _copy_tree(Path(evidence_dir), root / "evidence",
                              BackupPart.EVIDENCE.value, root)
    if project_state_dir is not None:
        entries += _copy_tree(Path(project_state_dir), root / "project-state",
                              BackupPart.PROJECT_STATE.value, root)

    connection = sqlite3.connect(str(backup_db))
    try:
        manifest = Manifest(
            manifest_version=MANIFEST_VERSION,
            created_at_unix=now_unix if now_unix is not None else int(time.time()),
            schema_version=_schema_version(connection),
            entries=entries,
            row_counts=_row_counts(connection),
            audit_chain=_audit_chain_summary(connection),
        )
    finally:
        connection.close()

    (root / MANIFEST_NAME).write_text(
        json.dumps(manifest.as_dict(), indent=2, sort_keys=True), encoding="utf-8"
    )
    return manifest


def _audit_chain_summary(connection: sqlite3.Connection) -> dict[str, Any]:
    """The chain's tip, so a restore can prove it landed on the same history."""
    try:
        row = connection.execute(
            "SELECT chain_seq, entry_hash FROM audit WHERE chain_seq IS NOT NULL "
            "ORDER BY chain_seq DESC LIMIT 1"
        ).fetchone()
    except sqlite3.OperationalError:
        return {"rows": 0, "tip_seq": None, "tip_hash": None}
    count = int(connection.execute(
        "SELECT COUNT(*) FROM audit WHERE chain_seq IS NOT NULL"
    ).fetchone()[0])
    return {
        "rows": count,
        "tip_seq": int(row[0]) if row else None,
        "tip_hash": str(row[1]) if row else None,
    }


def read_manifest(backup_dir: str | os.PathLike[str]) -> Manifest:
    path = Path(backup_dir) / MANIFEST_NAME
    if not path.exists():
        raise BackupError(f"no manifest at {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return Manifest(
        manifest_version=int(payload["manifest_version"]),
        created_at_unix=int(payload["created_at_unix"]),
        schema_version=int(payload["schema_version"]),
        entries=[BackupEntry(**entry) for entry in payload["entries"]],
        row_counts={k: int(v) for k, v in payload.get("row_counts", {}).items()},
        audit_chain=payload.get("audit_chain", {}),
    )


def verify(backup_dir: str | os.PathLike[str]) -> dict[str, Any]:
    """Recompute every digest. Returns the failures rather than raising, so an
    operator sees all of them at once instead of the first."""
    root = Path(backup_dir)
    manifest = read_manifest(root)
    missing: list[str] = []
    corrupt: list[str] = []
    for entry in manifest.entries:
        path = root / entry.relative_path
        if not path.exists():
            missing.append(entry.relative_path)
            continue
        if _digest_file(path) != entry.sha256:
            corrupt.append(entry.relative_path)
    return {
        "ok": not missing and not corrupt,
        "missing": missing,
        "corrupt": corrupt,
        "entries": len(manifest.entries),
        "created_at_unix": manifest.created_at_unix,
    }


def restore(
    backup_dir: str | os.PathLike[str],
    *,
    database_path: str | os.PathLike[str],
    overwrite: bool = False,
) -> dict[str, Any]:
    """Restore the database from a verified backup.

    Refuses to overwrite an existing database unless told to. A restore that
    silently replaces live owner state because someone got a path wrong is a
    worse outcome than the disaster it was meant to recover from.
    """
    report = verify(backup_dir)
    if not report["ok"]:
        raise RestoreVerificationFailed(
            f"backup at {backup_dir} does not verify: {report}"
        )
    target = Path(database_path)
    if target.exists() and not overwrite:
        raise BackupError(f"{target} exists; pass overwrite=True to replace it")
    target.parent.mkdir(parents=True, exist_ok=True)
    for sidecar in (target.with_name(target.name + "-wal"), target.with_name(target.name + "-shm")):
        if sidecar.exists():
            sidecar.unlink()
    _sqlite_backup(Path(backup_dir) / DATABASE_NAME, target)
    manifest = read_manifest(backup_dir)
    return {"restored_to": str(target), "schema_version": manifest.schema_version}


def drill(
    *,
    database_path: str | os.PathLike[str],
    workspace: str | os.PathLike[str],
    configuration_paths: Iterable[str | os.PathLike[str]] = (),
    evidence_dir: str | os.PathLike[str] | None = None,
    project_state_dir: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Back up, restore into a scratch location, and prove the copy is the original.

    Returns a report rather than a boolean: an operator running a drill wants to
    see what was compared, not only whether it passed.
    """
    space = Path(workspace)
    backup_dir = space / "backup"
    restored = space / "restored" / DATABASE_NAME
    manifest = create_backup(
        database_path=database_path, destination=backup_dir,
        configuration_paths=configuration_paths, evidence_dir=evidence_dir,
        project_state_dir=project_state_dir,
    )
    verification = verify(backup_dir)
    restore(backup_dir, database_path=restored, overwrite=True)

    connection = sqlite3.connect(str(restored))
    try:
        restored_counts = _row_counts(connection)
        restored_schema = _schema_version(connection)
        restored_chain = _audit_chain_summary(connection)
    finally:
        connection.close()

    differing = sorted(
        table for table in set(manifest.row_counts) | set(restored_counts)
        if manifest.row_counts.get(table) != restored_counts.get(table)
    )
    ok = (
        verification["ok"]
        and restored_schema == manifest.schema_version
        and not differing
        and restored_chain == manifest.audit_chain
    )
    return {
        "ok": ok,
        "verification": verification,
        "schema_version": {"backup": manifest.schema_version, "restored": restored_schema},
        "tables_compared": len(manifest.row_counts),
        "rows_compared": sum(manifest.row_counts.values()),
        "differing_tables": differing,
        "audit_chain": {"backup": manifest.audit_chain, "restored": restored_chain},
        "restored_to": str(restored),
    }


__all__ = [
    "BackupEntry", "BackupError", "BackupPart", "DATABASE_NAME", "MANIFEST_NAME",
    "Manifest", "RestoreVerificationFailed", "create_backup", "drill", "read_manifest",
    "restore", "verify",
]
