from __future__ import annotations

import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

import aiosqlite

SCHEMA_VERSION = 6

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
    ALTER TABLE devices ADD COLUMN access_token_hash TEXT;

    CREATE UNIQUE INDEX IF NOT EXISTS idx_devices_access_token_hash
      ON devices(access_token_hash)
      WHERE access_token_hash IS NOT NULL;

    CREATE TABLE IF NOT EXISTS pairing_tickets (
      ticket_hash TEXT PRIMARY KEY,
      label TEXT,
      expires_at_unix INTEGER NOT NULL,
      used_at_unix INTEGER,
      created_at_unix INTEGER NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_pairing_tickets_expiry
      ON pairing_tickets(expires_at_unix, used_at_unix);
    """,
    5: """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_devices_access_token_hash
      ON devices(access_token_hash)
      WHERE access_token_hash IS NOT NULL;

    CREATE TABLE IF NOT EXISTS pairing_tickets (
      ticket_hash TEXT PRIMARY KEY,
      label TEXT,
      expires_at_unix INTEGER NOT NULL,
      used_at_unix INTEGER,
      created_at_unix INTEGER NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_pairing_tickets_expiry
      ON pairing_tickets(expires_at_unix, used_at_unix);

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
    6: """
    -- Rev 1.3 §152/§411 Automation & Browser Fabric.  One semantic migration carrying
    -- automation capability/artifact/run/event/intent state, the standing-automation
    -- authority root, durable run-grant nonces, and browser task/evidence/profile state.

    CREATE TABLE IF NOT EXISTS automation_capabilities (
      capability_id TEXT PRIMARY KEY,
      semantic_name TEXT NOT NULL,
      engine TEXT NOT NULL,
      runtime_workflow_ref TEXT,
      action_class TEXT NOT NULL,
      mutates_state INTEGER NOT NULL,
      input_schema_json TEXT NOT NULL,
      output_schema_json TEXT NOT NULL,
      allowed_principals_json TEXT NOT NULL,
      allowed_origin_channels_json TEXT NOT NULL,
      latency_class TEXT NOT NULL,
      duration_class TEXT NOT NULL,
      required_context_json TEXT NOT NULL,
      required_credentials_json TEXT NOT NULL,
      verifier_type TEXT NOT NULL,
      idempotency_policy TEXT NOT NULL,
      evidence_policy TEXT NOT NULL,
      lifecycle_state TEXT NOT NULL,
      workflow_ir_digest TEXT NOT NULL,
      policy_version TEXT NOT NULL,
      compiler_version TEXT NOT NULL,
      created_at_ms INTEGER NOT NULL,
      updated_at_ms INTEGER NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_automation_capabilities_state
      ON automation_capabilities(lifecycle_state, semantic_name);

    CREATE TABLE IF NOT EXISTS automation_artifacts (
      artifact_id TEXT PRIMARY KEY,
      capability_id TEXT NOT NULL,
      version INTEGER NOT NULL,
      workflow_ir_digest TEXT NOT NULL,
      compiled_semantic_digest TEXT NOT NULL,
      compiled_full_digest TEXT NOT NULL,
      n8n_workflow_id TEXT,
      compiler_version TEXT NOT NULL,
      node_catalog_version TEXT NOT NULL,
      policy_version TEXT NOT NULL,
      source_refs_json TEXT NOT NULL,
      validation_report_digest TEXT,
      lifecycle_state TEXT NOT NULL,
      created_at_ms INTEGER NOT NULL,
      validated_at_ms INTEGER,
      admitted_at_ms INTEGER,
      UNIQUE(capability_id, version),
      FOREIGN KEY(capability_id) REFERENCES automation_capabilities(capability_id)
    );

    CREATE INDEX IF NOT EXISTS idx_automation_artifacts_cap
      ON automation_artifacts(capability_id, version);

    CREATE TABLE IF NOT EXISTS automation_runs (
      run_id TEXT PRIMARY KEY,
      capability_id TEXT NOT NULL,
      artifact_id TEXT NOT NULL,
      command_id TEXT,
      turn_id TEXT,
      execution_id TEXT,
      n8n_execution_id TEXT,
      status TEXT NOT NULL,
      action_class TEXT NOT NULL,
      input_digest TEXT NOT NULL,
      output_digest TEXT,
      evidence_pointer TEXT,
      verifier_status TEXT,
      error_code TEXT,
      started_at_ms INTEGER NOT NULL,
      submitted_at_ms INTEGER,
      verified_at_ms INTEGER,
      completed_at_ms INTEGER,
      updated_at_ms INTEGER NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_automation_runs_cap_time
      ON automation_runs(capability_id, started_at_ms);

    CREATE INDEX IF NOT EXISTS idx_automation_runs_exec
      ON automation_runs(execution_id);

    CREATE TABLE IF NOT EXISTS automation_external_events (
      event_id TEXT PRIMARY KEY,
      source_system TEXT NOT NULL,
      source_account_alias TEXT,
      event_type TEXT NOT NULL,
      observed_at_ms INTEGER,
      received_at_ms INTEGER NOT NULL,
      payload_schema_id TEXT NOT NULL,
      payload_digest TEXT NOT NULL,
      source_trust TEXT NOT NULL,
      sensitivity TEXT NOT NULL,
      dedupe_key TEXT NOT NULL UNIQUE,
      evidence_pointer TEXT,
      payload_json TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_external_events_type_time
      ON automation_external_events(event_type, received_at_ms);

    CREATE TABLE IF NOT EXISTS automation_standing_intents (
      intent_id TEXT PRIMARY KEY,
      owner_goal TEXT NOT NULL,
      trigger_json TEXT NOT NULL,
      scope_json TEXT NOT NULL,
      allowed_effects_json TEXT NOT NULL,
      expires_at_ms INTEGER,
      capability_id TEXT NOT NULL,
      workflow_version INTEGER NOT NULL,
      action_class TEXT NOT NULL,
      owner_approval_ref TEXT,
      enabled INTEGER NOT NULL,
      created_at_ms INTEGER NOT NULL,
      updated_at_ms INTEGER NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_standing_intents_cap
      ON automation_standing_intents(capability_id, enabled);

    -- Rev 1.3 §389.  The owner-authorized root from which a scheduled/event run derives an
    -- ordinary CommandAuthorityRecord.  source_device_id is the revocation root (§392) and is
    -- deliberately NOT NULL: §394 forbids making device binding optional for automation.
    CREATE TABLE IF NOT EXISTS standing_automation_authorities (
      authority_id TEXT PRIMARY KEY,
      standing_intent_id TEXT NOT NULL,
      source_command_id TEXT NOT NULL,
      source_device_id TEXT NOT NULL,
      source_turn_id TEXT,
      source_snapshot_id TEXT NOT NULL,
      source_context_digest TEXT NOT NULL,
      principal_type TEXT NOT NULL,
      requested_by TEXT NOT NULL,
      capability_id TEXT NOT NULL,
      artifact_id TEXT NOT NULL,
      workflow_version INTEGER NOT NULL,
      action_class_ceiling TEXT NOT NULL,
      trigger_digest TEXT NOT NULL,
      parameter_constraints_json TEXT NOT NULL,
      parameter_constraints_digest TEXT NOT NULL,
      allowed_effects_json TEXT NOT NULL,
      allowed_domains_json TEXT NOT NULL,
      issued_at_ms INTEGER NOT NULL,
      expires_at_ms INTEGER,
      revoked_at_ms INTEGER,
      owner_authority_evidence_ref TEXT NOT NULL,
      policy_version TEXT NOT NULL,
      FOREIGN KEY(standing_intent_id) REFERENCES automation_standing_intents(intent_id)
    );

    CREATE INDEX IF NOT EXISTS idx_standing_authorities_intent
      ON standing_automation_authorities(standing_intent_id, revoked_at_ms);

    CREATE INDEX IF NOT EXISTS idx_standing_authorities_device
      ON standing_automation_authorities(source_device_id, revoked_at_ms);

    -- Rev 1.3 §§160-161, 412.  Durable replay protection for run capability grants.
    -- In-memory-only replay protection is explicitly not acceptable.
    CREATE TABLE IF NOT EXISTS automation_run_nonces (
      nonce_hash TEXT PRIMARY KEY,
      grant_id TEXT NOT NULL,
      run_id TEXT NOT NULL,
      command_id TEXT NOT NULL,
      capability_id TEXT NOT NULL,
      artifact_id TEXT NOT NULL,
      artifact_version INTEGER NOT NULL,
      standing_authority_id TEXT,
      context_snapshot_id TEXT NOT NULL,
      input_digest TEXT NOT NULL,
      action_class_ceiling TEXT NOT NULL,
      allowed_operations_json TEXT NOT NULL,
      allowed_domains_json TEXT NOT NULL,
      grant_kind TEXT NOT NULL,
      max_uses INTEGER NOT NULL DEFAULT 1,
      use_count INTEGER NOT NULL DEFAULT 0,
      status TEXT NOT NULL,
      issued_at_ms INTEGER NOT NULL,
      expires_at_ms INTEGER NOT NULL,
      consumed_at_ms INTEGER,
      revoked_at_ms INTEGER
    );

    CREATE INDEX IF NOT EXISTS idx_run_nonces_run
      ON automation_run_nonces(run_id, status);

    CREATE INDEX IF NOT EXISTS idx_run_nonces_grant
      ON automation_run_nonces(grant_id);

    CREATE TABLE IF NOT EXISTS browser_tasks (
      task_id TEXT PRIMARY KEY,
      command_id TEXT,
      execution_id TEXT,
      capability_id TEXT,
      profile_alias TEXT NOT NULL,
      strategy TEXT NOT NULL,
      autonomy_tier TEXT NOT NULL,
      action_class TEXT NOT NULL,
      target_domain TEXT NOT NULL,
      goal TEXT NOT NULL,
      status TEXT NOT NULL,
      evidence_pointer TEXT,
      error_code TEXT,
      started_at_ms INTEGER NOT NULL,
      completed_at_ms INTEGER,
      updated_at_ms INTEGER NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_browser_tasks_status
      ON browser_tasks(status, started_at_ms);

    CREATE TABLE IF NOT EXISTS browser_evidence (
      evidence_id TEXT PRIMARY KEY,
      task_id TEXT NOT NULL,
      kind TEXT NOT NULL,
      url_digest TEXT NOT NULL,
      dom_digest TEXT,
      screenshot_digest TEXT,
      extraction_digest TEXT,
      source_trust TEXT NOT NULL,
      injection_assessment TEXT NOT NULL,
      contains_secrets INTEGER NOT NULL DEFAULT 0,
      created_at_ms INTEGER NOT NULL,
      evidence_json TEXT NOT NULL,
      FOREIGN KEY(task_id) REFERENCES browser_tasks(task_id)
    );

    CREATE INDEX IF NOT EXISTS idx_browser_evidence_task
      ON browser_evidence(task_id, created_at_ms);

    CREATE TABLE IF NOT EXISTS browser_profiles (
      profile_alias TEXT PRIMARY KEY,
      persistence TEXT NOT NULL,
      authentication TEXT NOT NULL,
      mutation_policy TEXT NOT NULL,
      secret_ref TEXT,
      lease_holder TEXT,
      lease_expires_at_ms INTEGER,
      last_verified_at_ms INTEGER,
      created_at_ms INTEGER NOT NULL,
      updated_at_ms INTEGER NOT NULL
    );
    """,
    7: """
    -- Rev 3.1 browser escalation/resume. DecisionService remains the owner
    -- authority; this table only binds a browser checkpoint to that decision.
    CREATE TABLE IF NOT EXISTS browser_escalations (
      escalation_id TEXT PRIMARY KEY,
      task_id TEXT NOT NULL,
      decision_id TEXT NOT NULL UNIQUE,
      boundary_type TEXT NOT NULL,
      reason_code TEXT NOT NULL,
      summary TEXT NOT NULL,
      why_required TEXT NOT NULL,
      risk_summary TEXT NOT NULL,
      current_scope_json TEXT NOT NULL,
      requested_scope_delta_json TEXT NOT NULL,
      current_action_class TEXT NOT NULL,
      required_action_class TEXT,
      pending_step TEXT,
      evidence_refs_json TEXT NOT NULL,
      session_lease_ref TEXT,
      idempotency_key TEXT NOT NULL UNIQUE,
      status TEXT NOT NULL,
      expires_at_ms INTEGER,
      created_at_ms INTEGER NOT NULL,
      updated_at_ms INTEGER NOT NULL,
      FOREIGN KEY(task_id) REFERENCES browser_tasks(task_id),
      FOREIGN KEY(decision_id) REFERENCES decisions(id)
    );

    CREATE INDEX IF NOT EXISTS idx_browser_escalations_task
      ON browser_escalations(task_id, status, created_at_ms);
    """,
    8: """
    -- Owner-approved browser scope deltas become a separate durable authorization.
    CREATE TABLE IF NOT EXISTS browser_scope_authorizations (
      authorization_id TEXT PRIMARY KEY,
      escalation_id TEXT NOT NULL UNIQUE,
      task_id TEXT NOT NULL,
      decision_id TEXT NOT NULL,
      approved_domains_json TEXT NOT NULL,
      approved_action_class_ceiling TEXT,
      status TEXT NOT NULL,
      issued_at_ms INTEGER NOT NULL,
      expires_at_ms INTEGER,
      consumed_at_ms INTEGER,
      FOREIGN KEY(escalation_id) REFERENCES browser_escalations(escalation_id),
      FOREIGN KEY(task_id) REFERENCES browser_tasks(task_id),
      FOREIGN KEY(decision_id) REFERENCES decisions(id)
    );

    CREATE INDEX IF NOT EXISTS idx_browser_scope_auth_task
      ON browser_scope_authorizations(task_id, status, issued_at_ms);
    """

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

    @staticmethod
    async def _ensure_access_token_column(db: aiosqlite.Connection) -> None:
        """Converge databases that already recorded either historical v4 migration.

        VATI v4 introduced ``devices.access_token_hash`` and pairing tickets while
        the parallel Rev 3.1 lineage used v4 for owner-runtime tables.  A database
        may therefore legitimately report schema version 4 with either shape.
        Version 5 heals the missing VATI column before creating indexes/tables.
        """
        cur = await db.execute("PRAGMA table_info(devices)")
        columns = {str(row["name"]) for row in await cur.fetchall()}
        if "access_token_hash" not in columns:
            await db.execute("ALTER TABLE devices ADD COLUMN access_token_hash TEXT")
            await db.commit()

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
                if version == 5:
                    await self._ensure_access_token_column(db)
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