"""Review I5 D1 — a terminal browser task cannot be resurrected at the database (migration 35).

Probe review-i5/probes/triggers.py (fbe5502e, schema 34): DELETE then INSERT the same task_id
as PENDING, and renaming a terminal row's task_id then INSERTing the old id, both succeeded;
every non-status column of a terminal row stayed writable.
"""

from __future__ import annotations

import sqlite3

import pytest

from conftest_automation import make_store
from van_gateway.browser.service import TERMINAL_TASK_STATUSES
from van_gateway.ops.retention import RetentionService
from van_gateway.storage.db import SCHEMA_VERSION

TERMINAL = sorted(s.value for s in TERMINAL_TASK_STATUSES)
IDENTITY = ("task_id", "command_id", "execution_id", "capability_id", "profile_alias", "strategy",
            "autonomy_tier", "action_class", "target_domain", "goal", "started_at_ms")


def _ins(db, tid, status, *, updated=1, verb="INSERT"):
    db.execute(
        f"{verb} INTO browser_tasks(task_id, command_id, profile_alias, strategy, autonomy_tier, action_class, "
        "target_domain, goal, status, started_at_ms, updated_at_ms) VALUES (?, 'cmd', 'public_research', "
        "'HARNESS', 'T1', 'A1', 'docs.example.com', 'g', ?, 1, ?)", (tid, status, updated))
    db.commit()


def _status(db, tid):
    row = db.execute("SELECT status FROM browser_tasks WHERE task_id = ?", (tid,)).fetchone()
    return row[0] if row else None


@pytest.fixture
async def db(tmp_path):
    store = await make_store(tmp_path)
    conn = sqlite3.connect(store.path)
    yield conn, store
    conn.close()


def _refused(db, fn, match="browser_task_terminal_status"):
    with pytest.raises(sqlite3.IntegrityError, match=match):
        fn()
    db.rollback()


async def test_schema_is_35():
    assert SCHEMA_VERSION == 35


@pytest.mark.parametrize("terminal", TERMINAL)
async def test_delete_then_insert_is_refused(db, terminal):
    conn, _ = db
    _ins(conn, "t1", terminal)
    conn.execute("DELETE FROM browser_tasks WHERE task_id = 't1'")
    conn.commit()
    _refused(conn, lambda: _ins(conn, "t1", "PENDING"))
    assert _status(conn, "t1") is None


async def test_a_task_that_became_terminal_by_update_is_tombstoned(db):
    conn, _ = db
    _ins(conn, "t2", "PENDING")
    conn.execute("UPDATE browser_tasks SET status = 'RUNNING' WHERE task_id = 't2'")
    conn.execute("UPDATE browser_tasks SET status = 'CANCELLED' WHERE task_id = 't2'")
    conn.commit()
    conn.execute("DELETE FROM browser_tasks WHERE task_id = 't2'")
    conn.commit()
    _refused(conn, lambda: _ins(conn, "t2", "PENDING"))
    _refused(conn, lambda: _ins(conn, "t2", "PENDING", verb="INSERT OR REPLACE"))


async def test_rename_then_reinsert_is_refused(db):
    conn, _ = db
    _ins(conn, "t3", "CANCELLED")
    _refused(conn, lambda: conn.execute("UPDATE browser_tasks SET task_id = 't3-old' WHERE task_id = 't3'"),
             match="browser_task_identity_immutable")
    _refused(conn, lambda: _ins(conn, "t3", "PENDING"))
    assert _status(conn, "t3") == "CANCELLED"


@pytest.mark.parametrize("column", IDENTITY)
async def test_identity_columns_never_change_even_on_a_live_task(db, column):
    conn, _ = db
    _ins(conn, "t4", "RUNNING")
    value = 999 if column == "started_at_ms" else "rewritten"
    _refused(conn, lambda: conn.execute(f"UPDATE browser_tasks SET {column} = ? WHERE task_id = 't4'", (value,)),
             match="browser_task_identity_immutable")


@pytest.mark.parametrize("column,value", [("evidence_pointer", "bevd://forged"), ("completed_at_ms", 5)])
async def test_a_terminal_rows_evidence_is_frozen(db, column, value):
    conn, _ = db
    _ins(conn, "t5", "COMPLETED")
    _refused(conn, lambda: conn.execute(f"UPDATE browser_tasks SET {column} = ? WHERE task_id = 't5'", (value,)))
    # The live service write path still works on a live row.
    _ins(conn, "t6", "RUNNING")
    conn.execute(f"UPDATE browser_tasks SET {column} = ? WHERE task_id = 't6'", (value,))
    conn.commit()


async def test_tombstones_cannot_be_removed_or_changed(db):
    conn, _ = db
    _ins(conn, "t7", "DENIED")
    _refused(conn, lambda: conn.execute("DELETE FROM browser_task_tombstones WHERE task_id = 't7'"),
             match="browser_task_tombstone_immutable")
    _refused(conn, lambda: conn.execute("UPDATE browser_task_tombstones SET task_id = 'x' WHERE task_id = 't7'"),
             match="browser_task_tombstone_immutable")


async def test_retention_still_deletes_old_terminal_rows_and_the_tombstone_stays(db):
    conn, store = db
    _ins(conn, "old", "COMPLETED", updated=1)
    _ins(conn, "live", "PENDING", updated=10**13)
    results = await RetentionService(store).prune(now_ms=10**13)
    by_table = {r.table: r.deleted for r in results}
    assert by_table["browser_tasks"] == 1
    assert _status(conn, "old") is None and _status(conn, "live") == "PENDING"
    assert conn.execute("SELECT terminal_status FROM browser_task_tombstones WHERE task_id = 'old'").fetchone()[0] == "COMPLETED"
    _refused(conn, lambda: _ins(conn, "old", "PENDING"))


async def test_a_new_task_id_is_unaffected(db):
    conn, _ = db
    _ins(conn, "fresh", "PENDING")
    conn.execute("UPDATE browser_tasks SET status = 'RUNNING', updated_at_ms = 2 WHERE task_id = 'fresh'")
    conn.commit()
    assert _status(conn, "fresh") == "RUNNING"


async def test_upgrading_a_v34_database_tombstones_tasks_already_terminal(db):
    """Migration 35 over an existing store: terminal rows written before it are tombstoned."""
    conn, store = db
    for name in ("browser_tasks_tombstone_on_terminal_insert", "browser_tasks_tombstone_on_terminal_update",
                 "browser_tasks_tombstoned_id_not_reinserted", "browser_tasks_identity_immutable",
                 "browser_tasks_terminal_evidence_frozen", "browser_task_tombstones_no_delete",
                 "browser_task_tombstones_no_update"):
        conn.execute(f"DROP TRIGGER {name}")
    conn.execute("DROP TABLE browser_task_tombstones")
    conn.execute("DELETE FROM schema_migrations WHERE version = 35")
    conn.commit()
    _ins(conn, "legacy", "EXPIRED")
    await store.migrate()
    conn.execute("DELETE FROM browser_tasks WHERE task_id = 'legacy'")
    conn.commit()
    _refused(conn, lambda: _ins(conn, "legacy", "PENDING"))
