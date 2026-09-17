from __future__ import annotations

import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

import aiosqlite

SCHEMA_VERSION = 4

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
    4: """
    CREATE TABLE IF NOT EXISTS runtime_meta (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL,
      updated_at_unix_ms INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS owner_facts (
      fact_id TEXT PRIMARY KEY,
      subject TEXT NOT NULL,
      predicate TEXT NOT NULL,
      value_json TEXT NOT NULL,
      authority TEXT NOT NULL,
      source_trust TEXT NOT NULL,
      source_ref TEXT NOT NULL,
      confidence_permille INTEGER NOT NULL CHECK(confidence_permille BETWEEN 0 AND 1000),
      confidence_profile_version INTEGER NOT NULL,
      scope TEXT NOT NULL,
      valid_from_ms INTEGER NOT NULL,
      valid_until_ms INTEGER,
      observed_at_ms INTEGER NOT NULL,
      last_verified_at_ms INTEGER,
      sensitivity TEXT NOT NULL,
      revision INTEGER NOT NULL,
      content_digest TEXT NOT NULL,
      created_at_unix_ms INTEGER NOT NULL,
      updated_at_unix_ms INTEGER NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_owner_facts_lookup
      ON owner_facts(subject, predicate, scope, valid_from_ms, valid_until_ms);
    CREATE INDEX IF NOT EXISTS idx_owner_facts_revision
      ON owner_facts(revision);

    CREATE TABLE IF NOT EXISTS owner_context_edges (
      edge_id TEXT PRIMARY KEY,
      from_node TEXT NOT NULL,
      predicate TEXT NOT NULL,
      to_node TEXT NOT NULL,
      scope TEXT NOT NULL,
      authority TEXT NOT NULL,
      source_trust TEXT NOT NULL,
      source_ref TEXT NOT NULL,
      confidence_permille INTEGER NOT NULL CHECK(confidence_permille BETWEEN 0 AND 1000),
      confidence_profile_version INTEGER NOT NULL,
      valid_from_ms INTEGER NOT NULL,
      valid_until_ms INTEGER,
      observed_at_ms INTEGER NOT NULL,
      sensitivity TEXT NOT NULL,
      revision INTEGER NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_owner_edges_from
      ON owner_context_edges(from_node, predicate, scope, valid_from_ms, valid_until_ms);
    CREATE INDEX IF NOT EXISTS idx_owner_edges_to
      ON owner_context_edges(to_node, predicate, scope, valid_from_ms, valid_until_ms);

    CREATE TABLE IF NOT EXISTS context_snapshots (
      snapshot_id TEXT PRIMARY KEY,
      command_id TEXT NOT NULL,
      kernel_revision INTEGER NOT NULL,
      fact_ids_json TEXT NOT NULL,
      graph_evidence_refs_json TEXT NOT NULL,
      live_state_refs_json TEXT NOT NULL,
      policy_refs_json TEXT NOT NULL,
      compiled_at_ms INTEGER NOT NULL,
      digest TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_context_snapshots_command
      ON context_snapshots(command_id, compiled_at_ms);

    CREATE TABLE IF NOT EXISTS action_definitions (
      action_id TEXT PRIMARY KEY,
      action_class TEXT NOT NULL,
      mutates_state INTEGER NOT NULL,
      allowed_principals_json TEXT NOT NULL,
      verifier_type TEXT NOT NULL,
      no_stale_replay INTEGER NOT NULL DEFAULT 0,
      max_age_seconds INTEGER,
      parameter_schema_json TEXT NOT NULL,
      enabled INTEGER NOT NULL DEFAULT 1,
      updated_at_unix_ms INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS action_executions (
      execution_id TEXT PRIMARY KEY,
      command_id TEXT NOT NULL,
      turn_id TEXT,
      action_id TEXT NOT NULL,
      action_class TEXT NOT NULL,
      principal_type TEXT NOT NULL,
      requested_by TEXT NOT NULL,
      status TEXT NOT NULL,
      idempotency_key TEXT NOT NULL UNIQUE,
      snapshot_id TEXT,
      parameters_digest TEXT NOT NULL,
      submitted_at_ms INTEGER,
      verified_at_ms INTEGER,
      correlation_json TEXT NOT NULL,
      evidence_pointer TEXT,
      error_code TEXT,
      updated_at_unix_ms INTEGER NOT NULL,
      FOREIGN KEY(action_id) REFERENCES action_definitions(action_id),
      FOREIGN KEY(snapshot_id) REFERENCES context_snapshots(snapshot_id)
    );

    CREATE INDEX IF NOT EXISTS idx_action_exec_command
      ON action_executions(command_id, updated_at_unix_ms);

    CREATE TABLE IF NOT EXISTS action_receipts (
      receipt_id TEXT PRIMARY KEY,
      execution_id TEXT NOT NULL,
      status TEXT NOT NULL,
      verifier_type TEXT NOT NULL,
      correlation_json TEXT NOT NULL,
      observed_postcondition_json TEXT NOT NULL,
      evidence_pointer TEXT,
      created_at_unix_ms INTEGER NOT NULL,
      FOREIGN KEY(execution_id) REFERENCES action_executions(execution_id)
    );

    CREATE INDEX IF NOT EXISTS idx_action_receipts_execution
      ON action_receipts(execution_id, created_at_unix_ms);

    CREATE TABLE IF NOT EXISTS research_evidence (
      evidence_id TEXT PRIMARY KEY,
      research_id TEXT NOT NULL,
      query_hash TEXT NOT NULL,
      source_url TEXT NOT NULL,
      source_title TEXT,
      source_domain TEXT,
      source_trust TEXT NOT NULL,
      published_at TEXT,
      retrieved_at_unix_ms INTEGER NOT NULL,
      content_digest TEXT NOT NULL,
      evidence_json TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_research_evidence_research
      ON research_evidence(research_id, retrieved_at_unix_ms);
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
