"""P3-OPS-002 — a backup, a restore, and a drill that actually restores.

The drill is the test. A backup procedure that has never been restored is a
hypothesis; `test_the_drill_restores_a_populated_database` is what makes it a
fact, and it is written so that it fails if the restored database differs from
the original in schema, in any table's row count, or in its audit chain tip.
"""

from __future__ import annotations

import sqlite3

import pytest

from conftest_automation import make_store
from van_gateway.audit.service import AuditService
from van_gateway.ops.backup import (
    BackupError,
    RestoreVerificationFailed,
    create_backup,
    drill,
    read_manifest,
    restore,
    verify,
)


async def _populated(tmp_path):
    """A database with real content, including a hash chain to compare after."""
    store = await make_store(tmp_path)
    audit = AuditService(store)
    for index in range(5):
        await audit.record(result="accepted", command_id=f"c{index}", device_id="dev-1")
    now = 1_700_000_000_000
    for index in range(3):
        await store.execute(
            "INSERT INTO missions(mission_id, owner_principal_id, origin, origin_channel, "
            "title, goal, created_at_ms, updated_at_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (f"m{index}", "owner", "OWNER_VOICE", "VOICE", f"t{index}", "g", now, now),
        )
    return store


@pytest.mark.asyncio
async def test_the_drill_restores_a_populated_database(tmp_path):
    store = await _populated(tmp_path)
    report = drill(database_path=store.path, workspace=str(tmp_path / "drill"))
    assert report["ok"] is True, report
    assert report["verification"]["ok"] is True
    assert report["differing_tables"] == []
    assert report["rows_compared"] >= 8
    assert report["tables_compared"] > 50
    assert report["schema_version"]["backup"] == report["schema_version"]["restored"]
    # The chain tip, not just the row count: a restore that lands on a different
    # history has the same number of rows.
    assert report["audit_chain"]["backup"] == report["audit_chain"]["restored"]
    assert report["audit_chain"]["restored"]["rows"] == 5


@pytest.mark.asyncio
async def test_the_restored_database_verifies_its_own_audit_chain(tmp_path):
    """Round-tripping through the backup must not break tamper-evidence."""
    store = await _populated(tmp_path)
    backup_dir = tmp_path / "b"
    create_backup(database_path=store.path, destination=backup_dir)
    target = tmp_path / "restored" / "van.sqlite3"
    restore(backup_dir, database_path=target)

    from van_gateway.storage.db import Store
    restored = AuditService(Store(str(target)))
    assert (await restored.verify_chain())["ok"] is True


@pytest.mark.asyncio
async def test_a_backup_taken_while_the_database_is_being_written_is_consistent(tmp_path):
    """The gateway runs in WAL mode and serves requests while a backup runs.
    Copying the file without its -wal sidecar restores to a plausible past."""
    store = await _populated(tmp_path)
    audit = AuditService(store)
    # Write more rows and do not checkpoint; they live in the WAL.
    for index in range(5, 20):
        await audit.record(result="accepted", command_id=f"c{index}")
    manifest = create_backup(database_path=store.path, destination=tmp_path / "wal-backup")
    assert manifest.audit_chain["rows"] == 20
    assert manifest.row_counts["audit"] == 20


@pytest.mark.asyncio
async def test_a_corrupted_backup_is_refused_before_it_overwrites_anything(tmp_path):
    store = await _populated(tmp_path)
    backup_dir = tmp_path / "b"
    create_backup(database_path=store.path, destination=backup_dir)
    assert verify(backup_dir)["ok"] is True

    with (backup_dir / "gateway.sqlite3").open("r+b") as handle:
        handle.seek(4096)
        handle.write(b"\x00" * 64)

    report = verify(backup_dir)
    assert report["ok"] is False
    assert report["corrupt"] == ["gateway.sqlite3"]
    with pytest.raises(RestoreVerificationFailed):
        restore(backup_dir, database_path=tmp_path / "out.sqlite3")


@pytest.mark.asyncio
async def test_a_truncated_backup_is_caught_too(tmp_path):
    store = await _populated(tmp_path)
    backup_dir = tmp_path / "b"
    create_backup(database_path=store.path, destination=backup_dir)
    (backup_dir / "gateway.sqlite3").unlink()
    report = verify(backup_dir)
    assert report["missing"] == ["gateway.sqlite3"]


@pytest.mark.asyncio
async def test_a_restore_will_not_silently_replace_live_owner_state(tmp_path):
    """Worse than the disaster it was meant to recover from."""
    store = await _populated(tmp_path)
    backup_dir = tmp_path / "b"
    create_backup(database_path=store.path, destination=backup_dir)
    with pytest.raises(BackupError):
        restore(backup_dir, database_path=store.path)
    restore(backup_dir, database_path=store.path, overwrite=True)


@pytest.mark.asyncio
async def test_configuration_evidence_and_project_state_are_all_covered(tmp_path):
    """Gate 11 names four parts. A database-only backup restores a VAN that no
    longer knows which repository revision its facts were true of."""
    store = await _populated(tmp_path)
    config = tmp_path / "gateway.env"
    config.write_text("VAN_LOG_LEVEL=INFO\n", encoding="utf-8")
    evidence = tmp_path / "evidence"
    (evidence / "runs").mkdir(parents=True)
    (evidence / "runs" / "probe.json").write_text("{}", encoding="utf-8")
    project = tmp_path / "project-state"
    project.mkdir()
    (project / "truth.json").write_text('{"repo_sha": "abc"}', encoding="utf-8")

    manifest = create_backup(
        database_path=store.path, destination=tmp_path / "full",
        configuration_paths=[config, tmp_path / "does-not-exist.env"],
        evidence_dir=evidence, project_state_dir=project,
    )
    parts = {entry.part for entry in manifest.entries}
    assert parts == {"DATABASE", "CONFIGURATION", "EVIDENCE", "PROJECT_STATE"}
    # A configuration file that is absent is absent from the manifest, not present
    # and empty: restoring an empty config is worse than restoring none.
    assert not any("does-not-exist" in e.relative_path for e in manifest.entries)
    assert verify(tmp_path / "full")["ok"] is True


@pytest.mark.asyncio
async def test_the_manifest_records_what_was_there_so_a_restore_can_be_compared(tmp_path):
    store = await _populated(tmp_path)
    create_backup(database_path=store.path, destination=tmp_path / "b")
    manifest = read_manifest(tmp_path / "b")
    assert manifest.row_counts["missions"] == 3
    assert manifest.row_counts["audit"] == 5
    assert manifest.schema_version >= 20


def test_backing_up_a_database_that_is_not_there_fails_loudly(tmp_path):
    with pytest.raises(BackupError):
        create_backup(database_path=tmp_path / "nope.sqlite3", destination=tmp_path / "b")


@pytest.mark.asyncio
async def test_the_drill_fails_when_the_restore_does_not_match(tmp_path, monkeypatch):
    """The drill has to be able to fail, or it proves nothing. Here the backup
    silently loses a table's rows and the drill catches it."""
    store = await _populated(tmp_path)
    from van_gateway.ops import backup as backup_module

    real = backup_module._sqlite_backup
    calls = {"n": 0}

    def lossy(source, destination):
        real(source, destination)
        calls["n"] += 1
        if calls["n"] == 2:  # the restore copy, not the backup
            connection = sqlite3.connect(str(destination))
            connection.execute("DELETE FROM missions")
            connection.commit()
            connection.close()

    monkeypatch.setattr(backup_module, "_sqlite_backup", lossy)
    report = drill(database_path=store.path, workspace=str(tmp_path / "drill"))
    assert report["ok"] is False
    assert "missions" in report["differing_tables"]


@pytest.mark.asyncio
async def test_the_scheduler_runs_the_drill(monkeypatch, tmp_path):
    """P3-OPS-009 — the drill was complete and nothing called it.

    Owner decision 10 in the closure blueprint took "local only, with the drill enabled"
    as the default, and only the backup half had a scheduled job. A backup nobody has
    restored is a hypothesis; the night it matters is the wrong time to test it.
    """
    from cryptography.fernet import Fernet

    from van_gateway.config import get_settings

    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "drill.sqlite3"))
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", "drill-ingress-token-0123456789")
    monkeypatch.setenv("VAN_BACKUP_DIR", str(tmp_path / "backups"))
    get_settings.cache_clear()
    try:
        from van_gateway.app import create_app

        app = create_app()
        assert "ops.backup_drill" in app.state.scheduler.jobs
        # Taking a backup is off by default and proving one restores is not: they are
        # different decisions, and conflating them is how "backups are configured" came
        # to mean "backups were written".
        assert "ops.backup" not in app.state.scheduler.jobs
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_the_drill_job_cleans_up_after_itself(monkeypatch, tmp_path):
    """The scratch restore is a second full database.

    Leaving it behind doubles the disk the deployment needs, and anyone who found it
    would reasonably read it as a backup.
    """
    from cryptography.fernet import Fernet

    from van_gateway.config import get_settings

    backups = tmp_path / "backups"
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "drill2.sqlite3"))
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", "drill-ingress-token-0123456789")
    monkeypatch.setenv("VAN_BACKUP_DIR", str(backups))
    get_settings.cache_clear()
    try:
        from van_gateway.app import create_app

        app = create_app()
        await app.state.store.migrate()
        result = await app.state.scheduler.jobs["ops.backup_drill"].run()
        assert result["ok"] is True
        assert result["tables_compared"] > 0
        assert not (backups / "drill").exists()
    finally:
        get_settings.cache_clear()
