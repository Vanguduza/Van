from __future__ import annotations

import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

import aiosqlite

SCHEMA_VERSION = 3

MIGRATIONS: dict[int, str] = {
    1: """
    CREATE TABLE IF NOT EXISTS schema_migrations (
      version INTEGER PRIMARY KEY,
      applied_at_unix INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS devices (
      device_id TEXT PRIMARY KEY,
      public_key_pem TEXT NOT NULL,
      enrolled_at_unix INTEGER NOT NULL,
      revoked_at_unix INTEGER,
      label TEXT
    );

    CREATE TABLE IF NOT EXISTS idempotency (
      idempotency_key TEXT PRIMARY KEY,
      request_hash TEXT NOT NULL,
      status TEXT NOT NULL,
      response_json TEXT,
      created_at_unix INTEGER NOT NULL,
      updated_at_unix INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS attention (
      id TEXT PRIMARY KEY,
      title TEXT NOT NULL,
      severity TEXT NOT NULL,
      state TEXT NOT NULL,
      source TEXT NOT NULL,
      project_id TEXT,
      created_at_unix INTEGER NOT NULL,
      updated_at_unix INTEGER NOT NULL,
      dedupe_key TEXT NOT NULL UNIQUE,
      snooze_until_unix INTEGER,
      payload_json TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS reminders (
      id TEXT PRIMARY KEY,
      text TEXT NOT NULL,
      due_at_unix INTEGER NOT NULL,
      status TEXT NOT NULL,
      project_id TEXT,
      idempotency_key TEXT NOT NULL UNIQUE,
      chain_follow_up_text TEXT,
      chain_follow_up_offset_seconds INTEGER,
      created_at_unix INTEGER NOT NULL,
      updated_at_unix INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS decisions (
      id TEXT PRIMARY KEY,
      title TEXT NOT NULL,
      body TEXT NOT NULL,
      status TEXT NOT NULL,
      source TEXT NOT NULL,
      hermes_ref TEXT,
      created_at_unix INTEGER NOT NULL,
      updated_at_unix INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS audit (
      id TEXT PRIMARY KEY,
      command_id TEXT,
      device_id TEXT,
      project_id TEXT,
      capability TEXT,
      approval TEXT,
      model_delegate TEXT,
      tool TEXT,
      before_json TEXT,
      after_json TEXT,
      result TEXT NOT NULL,
      failure_reason TEXT,
      evidence_pointer TEXT,
      created_at_unix INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS events (
      seq INTEGER PRIMARY KEY AUTOINCREMENT,
      event_type TEXT NOT NULL,
      payload_json TEXT NOT NULL,
      created_at_unix INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS event_cursors (
      device_id TEXT PRIMARY KEY,
      last_seq INTEGER NOT NULL,
      updated_at_unix INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS google_connections (
      owner_id TEXT PRIMARY KEY,
      encrypted_refresh_token TEXT NOT NULL,
      scopes_json TEXT NOT NULL,
      status TEXT NOT NULL,
      updated_at_unix INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS project_truth_cache (
      project_id TEXT PRIMARY KEY,
      truth_sha TEXT,
      repo_sha TEXT,
      truth_json TEXT,
      updated_at_unix INTEGER NOT NULL,
      stale INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS capability_grants (
      grant_id TEXT PRIMARY KEY,
      device_id TEXT NOT NULL,
      capabilities_json TEXT NOT NULL,
      expires_at_unix INTEGER NOT NULL,
      task_id TEXT,
      revoked_at_unix INTEGER,
      created_at_unix INTEGER NOT NULL
    );
    """,
    2: """
    CREATE TABLE IF NOT EXISTS google_principal (
      owner_id TEXT PRIMARY KEY,
      subject_hash TEXT NOT NULL,
      account_kind TEXT NOT NULL,
      ai_plan TEXT NOT NULL,
      status TEXT NOT NULL,
      updated_at_unix INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS google_capability_connections (
      capability_id TEXT PRIMARY KEY,
      owner_id TEXT NOT NULL,
      state TEXT NOT NULL,
      credential_plane TEXT NOT NULL,
      evidence_pointer TEXT,
      verified_at_unix INTEGER,
      metadata_json TEXT NOT NULL,
      updated_at_unix INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS google_jobs (
      job_id TEXT PRIMARY KEY,
      owner_intent_id TEXT NOT NULL,
      project_id TEXT,
      capability_id TEXT NOT NULL,
      action_class TEXT NOT NULL,
      truth_sha TEXT,
      grant_id TEXT,
      input_hash TEXT NOT NULL,
      status TEXT NOT NULL,
      output_hash TEXT,
      evidence_pointer TEXT,
      created_at_unix INTEGER NOT NULL,
      updated_at_unix INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS google_artifacts (
      artifact_id TEXT PRIMARY KEY,
      job_id TEXT NOT NULL,
      project_id TEXT,
      source_provider TEXT NOT NULL,
      source_tool TEXT NOT NULL,
      tool_version TEXT,
      input_hashes_json TEXT NOT NULL,
      output_hash TEXT NOT NULL,
      trust TEXT NOT NULL,
      validation_state TEXT NOT NULL,
      parent_artifact_ids_json TEXT NOT NULL,
      created_at_unix INTEGER NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_google_jobs_project
      ON google_jobs(project_id, created_at_unix);

    CREATE INDEX IF NOT EXISTS idx_google_artifacts_job
      ON google_artifacts(job_id, created_at_unix);
    """,
    3: """
    ALTER TABLE devices ADD COLUMN encrypted_secret TEXT;
    """,
}


class Store:
    def __init__(self, path: str) -> None:
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[aiosqlite.Connection]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA foreign_keys = ON")
            yield db

    async def migrate(self) -> None:
        async with self.connection() as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                  version INTEGER PRIMARY KEY,
                  applied_at_unix INTEGER NOT NULL
                )
                """
            )
            await db.commit()
            cur = await db.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations")
            row = await cur.fetchone()
            current = int(row[0])
            for version in sorted(MIGRATIONS):
                if version <= current:
                    continue
                await db.executescript(MIGRATIONS[version])
                await db.execute(
                    "INSERT INTO schema_migrations(version, applied_at_unix) VALUES (?, ?)",
                    (version, int(time.time())),
                )
                await db.commit()

    async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        async with self.connection() as db:
            await db.execute(sql, params)
            await db.commit()

    async def fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> aiosqlite.Row | None:
        async with self.connection() as db:
            cur = await db.execute(sql, params)
            return await cur.fetchone()

    async def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[aiosqlite.Row]:
        async with self.connection() as db:
            cur = await db.execute(sql, params)
            return await cur.fetchall()

    @staticmethod
    def dumps(obj: Any) -> str:
        return json.dumps(obj, sort_keys=True, separators=(",", ":"))
