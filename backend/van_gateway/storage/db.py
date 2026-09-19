from __future__ import annotations

import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

import aiosqlite

SCHEMA_VERSION = 22


MIGRATION_17 = """
-- P1-SEC-005: the command nonce was covered by the v2 signature and then never stored,
-- so a captured command could be replayed inside its validity window. A UNIQUE nonce per
-- device makes the second presentation fail at the database rather than at nobody.
CREATE TABLE IF NOT EXISTS command_nonces (
  device_id TEXT NOT NULL,
  nonce TEXT NOT NULL,
  command_id TEXT NOT NULL,
  consumed_at_unix INTEGER NOT NULL,
  PRIMARY KEY (device_id, nonce)
);
CREATE INDEX IF NOT EXISTS idx_command_nonces_consumed
  ON command_nonces(consumed_at_unix);

-- P1-SEC-006: the owner-authority audit log was a flat table with a random UUID and no
-- ordering, so rows could be inserted, altered or deleted undetectably. The VATI trading
-- ledger already had a verifiable chain; the authority log did not.
ALTER TABLE audit ADD COLUMN chain_seq INTEGER;
ALTER TABLE audit ADD COLUMN prev_hash TEXT;
ALTER TABLE audit ADD COLUMN entry_hash TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_audit_chain_seq ON audit(chain_seq);
"""

MIGRATION_18 = """
-- P0-EXEC-001: an accepted owner command produced no durable work record. The orchestrator
-- now opens exactly one mission per command, and this index is what makes "exactly one"
-- true under concurrency rather than merely intended: a second create for the same
-- source command fails at the database.
CREATE UNIQUE INDEX IF NOT EXISTS idx_missions_source_command
  ON missions(json_extract(authority_envelope_json, '$.source_command_id'))
  WHERE json_extract(authority_envelope_json, '$.source_command_id') IS NOT NULL;
"""

MIGRATION_19 = """
-- P1-LEARN-001: the learning stores had correct invariants and no caller that recorded a
-- real outcome, so VanEval scored a system that had done nothing the same as one that had
-- done everything right. This is the table the production feed writes to.
CREATE TABLE IF NOT EXISTS learning_outcomes (
  outcome_id TEXT PRIMARY KEY,
  mission_id TEXT NOT NULL,
  outcome_kind TEXT NOT NULL,
  goal TEXT NOT NULL,
  verification_status TEXT,
  evidence_refs_json TEXT NOT NULL DEFAULT '[]',
  recorded_at_ms INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_learning_outcomes_kind
  ON learning_outcomes(outcome_kind, recorded_at_ms);
CREATE UNIQUE INDEX IF NOT EXISTS idx_learning_outcomes_mission
  ON learning_outcomes(mission_id);
"""

MIGRATION_20 = """
-- P3-OPS-001: the audit log is hash-chained, so it cannot be pruned the way every other
-- table can. It can be pruned from the *start*, provided the verifier is told where the
-- surviving chain begins and what hash it must link back to. This table is that record.
--
-- The anchor is itself evidence: it says how many rows were removed and what the last
-- removed row hashed to, so a prune is visible rather than being indistinguishable from
-- a deletion someone performed by hand.
CREATE TABLE IF NOT EXISTS audit_chain_anchors (
  anchor_seq INTEGER PRIMARY KEY,
  anchor_hash TEXT NOT NULL,
  pruned_rows INTEGER NOT NULL,
  created_at_unix INTEGER NOT NULL
);

-- P3-OPS-005: reminder and attention dedupe lived in a Python dict, so a restart
-- re-surfaced an item the owner had already dismissed. Suppression is a decision the
-- owner made; it belongs in the database with everything else they decided.
CREATE TABLE IF NOT EXISTS notification_suppressions (
  suppression_key TEXT PRIMARY KEY,
  channel TEXT NOT NULL,
  subject_ref TEXT NOT NULL,
  reason TEXT NOT NULL,
  suppressed_until_unix INTEGER,
  created_at_unix INTEGER NOT NULL,
  updated_at_unix INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notification_suppressions_channel
  ON notification_suppressions(channel, suppressed_until_unix);

-- P3-OPS-004: fire_due had no scheduler, so a reminder that came due was never
-- dispatched by the system itself. A scheduler needs to know what it already ran, or a
-- restart re-fires everything that was ever due.
CREATE TABLE IF NOT EXISTS scheduler_runs (
  job_name TEXT NOT NULL,
  run_at_unix INTEGER NOT NULL,
  finished_at_unix INTEGER,
  outcome TEXT NOT NULL,
  detail_json TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (job_name, run_at_unix)
);
CREATE INDEX IF NOT EXISTS idx_scheduler_runs_job
  ON scheduler_runs(job_name, run_at_unix DESC);
"""


MIGRATION_21 = """
-- P1-LEARN-003: `StrategyLearning` keys everything on `mission_class` and no mission
-- carried one, so §25's "which capability sequences work" and §41's "measurable strategy
-- improvement in >= 3 production mission classes" were both unanswerable: the store had
-- the right invariants, a promotion gate that refused without eval evidence, and no way
-- for a row to ever exist. The class is the typed resolver's intent, which the command
-- path already computes and then discarded.
ALTER TABLE missions ADD COLUMN mission_class TEXT NOT NULL DEFAULT 'GENERAL_OWNER_INTENT';
CREATE INDEX IF NOT EXISTS idx_missions_class ON missions(mission_class, state);

-- P1-LEARN-002: nothing prevented learning from widening authority. A strategy is a
-- capability sequence, and a sequence exercised under an A4 envelope offered back to a
-- mission capped at A2 would be exactly that: authority acquired by accumulation rather
-- than by an owner decision. The ceiling a strategy was actually exercised under is
-- recorded here so it can be compared with the asking mission's envelope, and it only
-- ever rises to what has genuinely been run.
ALTER TABLE execution_strategies ADD COLUMN max_action_class TEXT NOT NULL DEFAULT 'A1';
CREATE INDEX IF NOT EXISTS idx_execution_strategies_lookup
  ON execution_strategies(mission_class, promotion_state);
"""

MIGRATION_22 = """
-- P0-OPS-011: an IN_FLIGHT idempotency claim had no lease. A gateway that died between
-- claiming a key and completing it left the row IN_FLIGHT forever, and every later retry
-- of that command raised "still in flight". The idempotency key is part of the signed
-- request, so the owner could not work around it by changing it: that command became
-- permanently unrepeatable, and the only cure was editing the database.
--
-- claim_count records how many times a claim has been taken, so a recovered claim is
-- visible rather than looking like the first attempt.
ALTER TABLE idempotency ADD COLUMN claim_count INTEGER NOT NULL DEFAULT 1;
"""

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
    """,
    9: """
    -- Rev 1.3 §§76-78, 101-102, 243-246 — operating a fabric, not just building it.

    -- §76. One row per admitted workflow version. Health is per version because a
    -- repair produces a new version, and the old version's failures are not the
    -- new one's record.
    CREATE TABLE IF NOT EXISTS automation_workflow_health (
      capability_id TEXT NOT NULL,
      workflow_version INTEGER NOT NULL,
      runs INTEGER NOT NULL DEFAULT 0,
      verified_successes INTEGER NOT NULL DEFAULT 0,
      failures INTEGER NOT NULL DEFAULT 0,
      consecutive_failures INTEGER NOT NULL DEFAULT 0,
      total_duration_ms INTEGER NOT NULL DEFAULT 0,
      duration_samples_json TEXT NOT NULL DEFAULT '[]',
      p95_duration_ms INTEGER,
      repair_count INTEGER NOT NULL DEFAULT 0,
      last_verified_at_ms INTEGER,
      last_failure_class TEXT,
      status TEXT NOT NULL DEFAULT 'GREEN',
      updated_at_ms INTEGER NOT NULL,
      PRIMARY KEY (capability_id, workflow_version)
    );

    CREATE INDEX IF NOT EXISTS idx_automation_health_status
      ON automation_workflow_health(status, updated_at_ms);

    -- §§78, 243-245. Repair lineage. The admitted workflow is never mutated in
    -- place, so every repair is a row pointing at the artifact it replaced.
    CREATE TABLE IF NOT EXISTS automation_repairs (
      repair_id TEXT PRIMARY KEY,
      capability_id TEXT NOT NULL,
      failing_artifact_id TEXT NOT NULL,
      failing_run_id TEXT,
      failure_class TEXT NOT NULL,
      error_code TEXT,
      decision TEXT NOT NULL,
      candidate_artifact_id TEXT,
      superseded_artifact_id TEXT,
      promoted_at_ms INTEGER,
      detail_json TEXT NOT NULL DEFAULT '{}',
      created_at_ms INTEGER NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_automation_repairs_cap
      ON automation_repairs(capability_id, created_at_ms);

    -- §246. Bounded retry ends somewhere, and that somewhere is a row an owner
    -- or operator can act on — never an infinite retry.
    CREATE TABLE IF NOT EXISTS automation_dead_letter (
      dead_letter_id TEXT PRIMARY KEY,
      run_id TEXT,
      event_id TEXT,
      capability_id TEXT,
      failure_class TEXT NOT NULL,
      last_error_code TEXT,
      attempt_count INTEGER NOT NULL DEFAULT 1,
      evidence_refs_json TEXT NOT NULL DEFAULT '[]',
      next_action TEXT NOT NULL,
      detail_json TEXT NOT NULL DEFAULT '{}',
      created_at_ms INTEGER NOT NULL,
      updated_at_ms INTEGER NOT NULL,
      resolved_at_ms INTEGER,
      resolution TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_automation_dead_letter_open
      ON automation_dead_letter(resolved_at_ms, created_at_ms);

    CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_dead_letter_run
      ON automation_dead_letter(run_id) WHERE run_id IS NOT NULL;

    -- §101. Per-run timing, so the ladder's claims are measured rather than
    -- asserted. `cache_state` is what makes the HOT hit rate observable.
    CREATE TABLE IF NOT EXISTS automation_run_telemetry (
      run_id TEXT PRIMARY KEY,
      capability_id TEXT,
      workflow_version INTEGER,
      cache_state TEXT NOT NULL,
      compile_time_ms INTEGER NOT NULL DEFAULT 0,
      dispatch_time_ms INTEGER NOT NULL DEFAULT 0,
      execution_time_ms INTEGER NOT NULL DEFAULT 0,
      external_wait_ms INTEGER NOT NULL DEFAULT 0,
      verification_time_ms INTEGER NOT NULL DEFAULT 0,
      retry_count INTEGER NOT NULL DEFAULT 0,
      failure_count INTEGER NOT NULL DEFAULT 0,
      recorded_at_ms INTEGER NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_automation_run_telemetry_time
      ON automation_run_telemetry(recorded_at_ms);

    -- §102. One row per capability-acquisition attempt. The core success metric
    -- is that the HOT share of these rises over time.
    CREATE TABLE IF NOT EXISTS automation_generation_telemetry (
      generation_id TEXT PRIMARY KEY,
      goal_class TEXT NOT NULL,
      medium TEXT NOT NULL,
      outcome TEXT NOT NULL,
      pattern_reused INTEGER NOT NULL DEFAULT 0,
      ir_cache_hit INTEGER NOT NULL DEFAULT 0,
      first_use_latency_ms INTEGER NOT NULL DEFAULT 0,
      recorded_at_ms INTEGER NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_automation_generation_time
      ON automation_generation_telemetry(recorded_at_ms);
    """,
    10: """
    -- Rev 1 §§3, 5, 34, 46 — Mission Core. The single owner-visible unit of work.

    -- §3.1. Additive only: no existing subsystem table is altered or dropped, so
    -- browser tasks, automation runs and Google jobs keep their own state and are
    -- referenced from mission_activities rather than absorbed into it.
    CREATE TABLE IF NOT EXISTS missions (
      mission_id TEXT PRIMARY KEY,
      owner_principal_id TEXT NOT NULL,
      project_id TEXT,
      origin TEXT NOT NULL,
      origin_channel TEXT NOT NULL,
      title TEXT NOT NULL,
      goal TEXT NOT NULL,
      success_contract_json TEXT NOT NULL DEFAULT '{}',
      constraints_json TEXT NOT NULL DEFAULT '[]',
      authority_envelope_json TEXT NOT NULL DEFAULT '{}',
      sensitivity TEXT NOT NULL DEFAULT 'ROUTINE',
      context_snapshot_id TEXT,
      state TEXT NOT NULL DEFAULT 'CAPTURED',
      priority INTEGER NOT NULL DEFAULT 50,
      created_at_ms INTEGER NOT NULL,
      updated_at_ms INTEGER NOT NULL,
      deadline_ms INTEGER,
      attention_policy TEXT NOT NULL DEFAULT 'NORMAL',
      plan_revision INTEGER NOT NULL DEFAULT 0,
      current_phase TEXT,
      parent_mission_id TEXT,
      final_outcome TEXT,
      verification_state TEXT NOT NULL DEFAULT 'PENDING',
      verification_record_json TEXT,
      learning_record_id TEXT,
      FOREIGN KEY(parent_mission_id) REFERENCES missions(mission_id)
    );

    CREATE INDEX IF NOT EXISTS idx_missions_state
      ON missions(state, updated_at_ms);
    CREATE INDEX IF NOT EXISTS idx_missions_owner_project
      ON missions(owner_principal_id, project_id, updated_at_ms);

    -- §5. Modular execution under one mission. `executor_ref` points at the
    -- specialist row (browser_tasks.task_id, automation_runs.run_id, ...) so the
    -- subsystem stays authoritative for its own execution detail.
    CREATE TABLE IF NOT EXISTS mission_activities (
      activity_id TEXT PRIMARY KEY,
      mission_id TEXT NOT NULL,
      activity_type TEXT NOT NULL,
      capability_id TEXT NOT NULL,
      executor TEXT NOT NULL,
      executor_ref TEXT,
      input_contract_json TEXT NOT NULL DEFAULT '{}',
      authority_ref TEXT,
      state TEXT NOT NULL DEFAULT 'PENDING',
      attempt INTEGER NOT NULL DEFAULT 1,
      started_at_ms INTEGER NOT NULL,
      ended_at_ms INTEGER,
      dependency_activity_ids_json TEXT NOT NULL DEFAULT '[]',
      checkpoint_ref TEXT,
      error_class TEXT,
      retry_policy TEXT NOT NULL DEFAULT 'NONE',
      verification_contract_json TEXT NOT NULL DEFAULT '{}',
      FOREIGN KEY(mission_id) REFERENCES missions(mission_id)
    );

    CREATE INDEX IF NOT EXISTS idx_mission_activities_mission
      ON mission_activities(mission_id, started_at_ms);
    CREATE INDEX IF NOT EXISTS idx_mission_activities_executor_ref
      ON mission_activities(executor, executor_ref);

    -- §34. The owner-visible timeline. Raw provider logs stay in their own
    -- tables and are technical drill-down; this is what the Activity page reads.
    CREATE TABLE IF NOT EXISTS mission_events (
      event_id TEXT PRIMARY KEY,
      mission_id TEXT NOT NULL,
      activity_id TEXT,
      event_type TEXT NOT NULL,
      actor TEXT NOT NULL,
      occurred_at_ms INTEGER NOT NULL,
      severity TEXT NOT NULL DEFAULT 'INFO',
      owner_visibility INTEGER NOT NULL DEFAULT 1,
      summary TEXT NOT NULL DEFAULT '',
      evidence_ref TEXT,
      FOREIGN KEY(mission_id) REFERENCES missions(mission_id)
    );

    CREATE INDEX IF NOT EXISTS idx_mission_events_mission
      ON mission_events(mission_id, occurred_at_ms);
    CREATE INDEX IF NOT EXISTS idx_mission_events_owner_feed
      ON mission_events(owner_visibility, occurred_at_ms);
    """,
    11: """
    -- Rev 1 §7 — the canonical capability declaration set, materialized.

    -- This table holds DECLARATIONS, never readiness. Readiness stays with the
    -- subsystem that already owns it (automation_artifacts lifecycle, the Google
    -- mesh, ExternalRuntimeRegistry evidence) and is reached through
    -- `readiness_source`. That is what lets this registry be canonical without
    -- becoming a third copy of state those subsystems already maintain.
    CREATE TABLE IF NOT EXISTS capability_registry (
      capability_id TEXT PRIMARY KEY,
      manifest_version TEXT NOT NULL,
      manifest_digest TEXT NOT NULL,
      declaration_json TEXT NOT NULL,
      capability_class TEXT NOT NULL,
      authority_class TEXT NOT NULL,
      readiness_source TEXT NOT NULL,
      provider TEXT NOT NULL,
      executor TEXT NOT NULL,
      created_at_ms INTEGER NOT NULL,
      updated_at_ms INTEGER NOT NULL,
      withdrawn_at_ms INTEGER
    );

    CREATE INDEX IF NOT EXISTS idx_capability_registry_class
      ON capability_registry(capability_class, withdrawn_at_ms);
    CREATE INDEX IF NOT EXISTS idx_capability_registry_digest
      ON capability_registry(manifest_digest);

    -- §8 — the route decision is persisted as evidence: what was considered,
    -- what was rejected and why. A routing choice nobody can reconstruct is a
    -- routing choice nobody can audit.
    CREATE TABLE IF NOT EXISTS capability_route_decisions (
      decision_id TEXT PRIMARY KEY,
      mission_id TEXT,
      goal_class TEXT NOT NULL,
      selected_capability_id TEXT,
      candidates_json TEXT NOT NULL DEFAULT '[]',
      rejected_json TEXT NOT NULL DEFAULT '[]',
      fallback_chain_json TEXT NOT NULL DEFAULT '[]',
      routing_policy_version TEXT NOT NULL,
      manifest_digest TEXT NOT NULL,
      decided_at_ms INTEGER NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_capability_route_decisions_mission
      ON capability_route_decisions(mission_id, decided_at_ms);
    """,
    12: """
    -- Rev 1 §§64-65, 68, 72, 76-78, 87 — the owner-understanding layer.

    -- §64. How the owner works, not who they are. Every field is an assertion
    -- with a state and evidence, never a settled truth, so it can be corrected.
    CREATE TABLE IF NOT EXISTS owner_cognitive_model (
      assertion_id TEXT PRIMARY KEY,
      owner_principal_id TEXT NOT NULL,
      field TEXT NOT NULL,
      value TEXT NOT NULL,
      state TEXT NOT NULL DEFAULT 'OBSERVED',
      confidence REAL NOT NULL DEFAULT 0.0,
      evidence_refs_json TEXT NOT NULL DEFAULT '[]',
      supporting_episode_refs_json TEXT NOT NULL DEFAULT '[]',
      project_id TEXT,
      temporary INTEGER NOT NULL DEFAULT 0,
      superseded_by TEXT,
      owner_confirmed_at_ms INTEGER,
      last_revalidated_at_ms INTEGER,
      created_at_ms INTEGER NOT NULL,
      updated_at_ms INTEGER NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_owner_model_field
      ON owner_cognitive_model(owner_principal_id, field, state);

    -- §65. Why a decision went the way it did, so patterns can be learned and,
    -- crucially, falsified by later outcomes.
    CREATE TABLE IF NOT EXISTS decision_fingerprints (
      decision_id TEXT PRIMARY KEY,
      mission_id TEXT,
      context_json TEXT NOT NULL DEFAULT '{}',
      options_considered_json TEXT NOT NULL DEFAULT '[]',
      owner_choice TEXT NOT NULL,
      owner_stated_reason TEXT,
      inferred_reason TEXT,
      tradeoffs_json TEXT NOT NULL DEFAULT '[]',
      evidence_used_json TEXT NOT NULL DEFAULT '[]',
      rejected_alternatives_json TEXT NOT NULL DEFAULT '[]',
      outcome TEXT,
      reassessment TEXT,
      created_at_ms INTEGER NOT NULL,
      updated_at_ms INTEGER NOT NULL
    );

    -- §76. Owner words mapped to operational meaning, with anti-examples so the
    -- mapping is falsifiable rather than merely plausible.
    CREATE TABLE IF NOT EXISTS shared_vocabulary (
      term TEXT NOT NULL,
      project_id TEXT NOT NULL DEFAULT '',
      owner_meaning TEXT NOT NULL,
      system_operationalization TEXT NOT NULL,
      examples_json TEXT NOT NULL DEFAULT '[]',
      anti_examples_json TEXT NOT NULL DEFAULT '[]',
      confidence REAL NOT NULL DEFAULT 0.0,
      evidence_refs_json TEXT NOT NULL DEFAULT '[]',
      created_at_ms INTEGER NOT NULL,
      updated_at_ms INTEGER NOT NULL,
      PRIMARY KEY (term, project_id)
    );

    -- §77. Long-lived goals and how they relate, so a newer instruction that
    -- contradicts an older one is visible rather than silently winning.
    CREATE TABLE IF NOT EXISTS intent_nodes (
      intent_id TEXT PRIMARY KEY,
      owner_goal TEXT NOT NULL,
      first_observed_ms INTEGER NOT NULL,
      latest_observed_ms INTEGER NOT NULL,
      projects_json TEXT NOT NULL DEFAULT '[]',
      constraints_json TEXT NOT NULL DEFAULT '[]',
      status TEXT NOT NULL DEFAULT 'ACTIVE',
      priority INTEGER NOT NULL DEFAULT 50
    );

    CREATE TABLE IF NOT EXISTS intent_edges (
      edge_id TEXT PRIMARY KEY,
      from_intent_id TEXT NOT NULL,
      to_intent_id TEXT NOT NULL,
      edge_type TEXT NOT NULL,
      evidence_ref TEXT,
      created_at_ms INTEGER NOT NULL,
      FOREIGN KEY(from_intent_id) REFERENCES intent_nodes(intent_id),
      FOREIGN KEY(to_intent_id) REFERENCES intent_nodes(intent_id)
    );

    CREATE INDEX IF NOT EXISTS idx_intent_edges_from
      ON intent_edges(from_intent_id, edge_type);

    CREATE TABLE IF NOT EXISTS intent_missions (
      intent_id TEXT NOT NULL,
      mission_id TEXT NOT NULL,
      linked_at_ms INTEGER NOT NULL,
      PRIMARY KEY (intent_id, mission_id)
    );

    -- §78. Why a project exists and what was already rejected. Scoped, and
    -- explicitly not a replacement for Project Truth.
    CREATE TABLE IF NOT EXISTS strategic_memory (
      entry_id TEXT PRIMARY KEY,
      project_id TEXT NOT NULL,
      entry_type TEXT NOT NULL,
      statement TEXT NOT NULL,
      rationale TEXT,
      evidence_refs_json TEXT NOT NULL DEFAULT '[]',
      superseded_by TEXT,
      created_at_ms INTEGER NOT NULL,
      updated_at_ms INTEGER NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_strategic_memory_project
      ON strategic_memory(project_id, entry_type);

    -- §72. Where VAN compensates rather than imitates. Task observations only.
    CREATE TABLE IF NOT EXISTS cognitive_complement_map (
      entry_id TEXT PRIMARY KEY,
      domain TEXT NOT NULL UNIQUE,
      owner_strength TEXT,
      owner_vulnerability_candidate TEXT,
      van_strength TEXT,
      preferred_collaboration_pattern TEXT,
      confidence REAL NOT NULL DEFAULT 0.0,
      evidence_refs_json TEXT NOT NULL DEFAULT '[]',
      created_at_ms INTEGER NOT NULL,
      updated_at_ms INTEGER NOT NULL
    );

    -- §87. What changed about how VAN works with the owner, and whether the
    -- owner may reverse it.
    CREATE TABLE IF NOT EXISTS symbiotic_growth (
      change_id TEXT PRIMARY KEY,
      observed_pattern TEXT NOT NULL,
      previous_behavior TEXT NOT NULL,
      new_behavior TEXT NOT NULL,
      reason TEXT NOT NULL,
      evidence_refs_json TEXT NOT NULL DEFAULT '[]',
      owner_confirmation_required INTEGER NOT NULL DEFAULT 1,
      owner_confirmed_at_ms INTEGER,
      reverted_at_ms INTEGER,
      reversible INTEGER NOT NULL DEFAULT 1,
      effective_from_ms INTEGER,
      created_at_ms INTEGER NOT NULL
    );
    """,
    13: """
    -- Rev 1 §§66, 68-71, 75, 88 — the critical reasoning layer.

    -- §66. Structured conclusions only. §13 forbids persisting hidden
    -- chain-of-thought, so there is no column for it: what survives an
    -- assessment is the facts, assumptions, alternatives and the confidence.
    CREATE TABLE IF NOT EXISTS reasoning_assessments (
      assessment_id TEXT PRIMARY KEY,
      mission_id TEXT,
      problem_statement TEXT NOT NULL,
      known_facts_json TEXT NOT NULL DEFAULT '[]',
      assumptions_json TEXT NOT NULL DEFAULT '[]',
      uncertainties_json TEXT NOT NULL DEFAULT '[]',
      contradictions_json TEXT NOT NULL DEFAULT '[]',
      hypotheses_json TEXT NOT NULL DEFAULT '[]',
      alternatives_json TEXT NOT NULL DEFAULT '[]',
      failure_modes_json TEXT NOT NULL DEFAULT '[]',
      counterfactuals_json TEXT NOT NULL DEFAULT '[]',
      recommended_next_action TEXT,
      confidence REAL NOT NULL DEFAULT 0.0,
      evidence_refs_json TEXT NOT NULL DEFAULT '[]',
      challenge_mode TEXT NOT NULL DEFAULT 'BALANCED',
      critic_findings_json TEXT NOT NULL DEFAULT '[]',
      verifier_findings_json TEXT NOT NULL DEFAULT '[]',
      created_at_ms INTEGER NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_reasoning_mission
      ON reasoning_assessments(mission_id, created_at_ms);

    -- §68. Mission-scoped assumptions, and whether anyone checked them.
    CREATE TABLE IF NOT EXISTS assumption_ledger (
      assumption_id TEXT PRIMARY KEY,
      mission_id TEXT NOT NULL,
      claim TEXT NOT NULL,
      source TEXT NOT NULL,
      importance TEXT NOT NULL DEFAULT 'MEDIUM',
      confidence REAL NOT NULL DEFAULT 0.5,
      testability TEXT NOT NULL DEFAULT 'UNKNOWN',
      verification_plan TEXT,
      status TEXT NOT NULL DEFAULT 'ACTIVE',
      resolved_evidence_refs_json TEXT NOT NULL DEFAULT '[]',
      created_at_ms INTEGER NOT NULL,
      updated_at_ms INTEGER NOT NULL,
      FOREIGN KEY(mission_id) REFERENCES missions(mission_id)
    );

    CREATE INDEX IF NOT EXISTS idx_assumption_mission
      ON assumption_ledger(mission_id, status, importance);

    -- §71. Every time VAN agreed or disagreed with the owner on a factual
    -- premise, so the anti-sycophancy metrics are measured rather than claimed.
    CREATE TABLE IF NOT EXISTS premise_assessments (
      premise_id TEXT PRIMARY KEY,
      mission_id TEXT,
      owner_premise TEXT NOT NULL,
      van_position TEXT NOT NULL,
      evidence_refs_json TEXT NOT NULL DEFAULT '[]',
      semantic_class TEXT NOT NULL,
      corrected INTEGER NOT NULL DEFAULT 0,
      agreed_without_evidence INTEGER NOT NULL DEFAULT 0,
      created_at_ms INTEGER NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_premise_created
      ON premise_assessments(created_at_ms);
    """,
    14: """
    -- Rev 1 §§10, 11, 27, 31 — attention scoring, proactive autonomy, trust.

    -- §10. Candidates are scored and may be suppressed; the existing `attention`
    -- table stays the owner-visible queue, and this records why something did or
    -- did not reach it.
    CREATE TABLE IF NOT EXISTS attention_candidates (
      candidate_id TEXT PRIMARY KEY,
      source TEXT NOT NULL,
      dedupe_key TEXT NOT NULL,
      importance REAL NOT NULL DEFAULT 0.0,
      urgency REAL NOT NULL DEFAULT 0.0,
      actionability REAL NOT NULL DEFAULT 0.0,
      novelty REAL NOT NULL DEFAULT 0.0,
      owner_relevance REAL NOT NULL DEFAULT 0.0,
      confidence REAL NOT NULL DEFAULT 0.0,
      interruption_cost REAL NOT NULL DEFAULT 0.0,
      score REAL NOT NULL DEFAULT 0.0,
      disposition TEXT NOT NULL,
      reason TEXT,
      related_mission_id TEXT,
      summary TEXT NOT NULL DEFAULT '',
      expiry_ms INTEGER,
      created_at_ms INTEGER NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_attention_candidates_dedupe
      ON attention_candidates(dedupe_key, created_at_ms);

    -- §31. Trust is earned from verified outcomes and lost hard on false success.
    CREATE TABLE IF NOT EXISTS domain_trust (
      domain TEXT PRIMARY KEY,
      verified_successes INTEGER NOT NULL DEFAULT 0,
      meaningful_failures INTEGER NOT NULL DEFAULT 0,
      false_successes INTEGER NOT NULL DEFAULT 0,
      owner_overrides INTEGER NOT NULL DEFAULT 0,
      recovery_successes INTEGER NOT NULL DEFAULT 0,
      current_autonomy_ceiling TEXT NOT NULL DEFAULT 'S1',
      owner_granted_ceiling TEXT,
      updated_at_ms INTEGER NOT NULL
    );

    -- §11. Proactive missions and the standing policy that allowed them.
    CREATE TABLE IF NOT EXISTS proactive_policies (
      policy_id TEXT PRIMARY KEY,
      domain TEXT NOT NULL,
      autonomy_level TEXT NOT NULL,
      mission_class TEXT NOT NULL,
      owner_granted_at_ms INTEGER,
      owner_evidence_ref TEXT,
      enabled INTEGER NOT NULL DEFAULT 1,
      created_at_ms INTEGER NOT NULL,
      updated_at_ms INTEGER NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_proactive_policies_domain
      ON proactive_policies(domain, enabled);
    """,
    15: """
    -- Rev 1 §§79-84, 24-25, 40 — external reality, evolution, benchmarks, eval.

    -- §79. What the evidence says now, kept strictly apart from what the owner
    -- thinks. §22 makes the separation mandatory to stop personalisation
    -- becoming an echo chamber.
    CREATE TABLE IF NOT EXISTS external_reality (
      observation_id TEXT PRIMARY KEY,
      subject TEXT NOT NULL,
      claim TEXT NOT NULL,
      source_kind TEXT NOT NULL,
      source_ref TEXT NOT NULL,
      observed_at_ms INTEGER NOT NULL,
      confidence REAL NOT NULL DEFAULT 0.5,
      superseded_by TEXT,
      contradicts_owner_belief INTEGER NOT NULL DEFAULT 0
    );

    CREATE INDEX IF NOT EXISTS idx_external_reality_subject
      ON external_reality(subject, observed_at_ms);

    -- §82. One row per technology VAN knows about, with its pipeline state.
    CREATE TABLE IF NOT EXISTS technology_capabilities (
      technology_id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      category TEXT NOT NULL,
      version TEXT,
      source TEXT,
      licence TEXT,
      security_profile TEXT,
      strengths_json TEXT NOT NULL DEFAULT '[]',
      weaknesses_json TEXT NOT NULL DEFAULT '[]',
      integration_cost TEXT,
      migration_risk TEXT,
      owner_value TEXT,
      pipeline_state TEXT NOT NULL DEFAULT 'DISCOVERED',
      benchmark_digest TEXT,
      owner_decision_ref TEXT,
      last_evaluated_at_ms INTEGER,
      created_at_ms INTEGER NOT NULL,
      updated_at_ms INTEGER NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_technology_state
      ON technology_capabilities(pipeline_state, category);

    -- §83. VAN-specific benchmark results. §24 forbids relying on public
    -- leaderboards, so a technology's standing here is measured on VAN tasks.
    CREATE TABLE IF NOT EXISTS benchmark_runs (
      run_id TEXT PRIMARY KEY,
      suite TEXT NOT NULL,
      technology_id TEXT,
      task_count INTEGER NOT NULL DEFAULT 0,
      passed INTEGER NOT NULL DEFAULT 0,
      failed INTEGER NOT NULL DEFAULT 0,
      median_latency_ms INTEGER,
      total_cost_micros INTEGER,
      results_json TEXT NOT NULL DEFAULT '[]',
      harness_version TEXT NOT NULL,
      created_at_ms INTEGER NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_benchmark_suite
      ON benchmark_runs(suite, technology_id, created_at_ms);

    -- §25. Which capability sequences actually work for which mission class.
    CREATE TABLE IF NOT EXISTS execution_strategies (
      strategy_id TEXT PRIMARY KEY,
      mission_class TEXT NOT NULL,
      capability_sequence_json TEXT NOT NULL DEFAULT '[]',
      conditions_json TEXT NOT NULL DEFAULT '{}',
      success_count INTEGER NOT NULL DEFAULT 0,
      failure_count INTEGER NOT NULL DEFAULT 0,
      median_latency_ms INTEGER,
      median_cost_micros INTEGER,
      verification_quality REAL NOT NULL DEFAULT 0.0,
      promotion_state TEXT NOT NULL DEFAULT 'EXPERIMENTAL',
      eval_run_id TEXT,
      last_evaluated_at_ms INTEGER,
      created_at_ms INTEGER NOT NULL,
      updated_at_ms INTEGER NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_strategy_class
      ON execution_strategies(mission_class, promotion_state);

    -- §40. Versioned eval runs across the >9 dimensions.
    CREATE TABLE IF NOT EXISTS eval_runs (
      eval_run_id TEXT PRIMARY KEY,
      suite TEXT NOT NULL,
      dimension TEXT NOT NULL,
      measured INTEGER NOT NULL DEFAULT 0,
      sample_size INTEGER NOT NULL DEFAULT 0,
      score REAL,
      target REAL,
      meets_target INTEGER,
      unmeasurable_reason TEXT,
      details_json TEXT NOT NULL DEFAULT '{}',
      harness_version TEXT NOT NULL,
      created_at_ms INTEGER NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_eval_dimension
      ON eval_runs(dimension, created_at_ms);
    """,
    16: """
    -- Rev 1 §§34, 36, 38 — permissions the owner can read, and computer use.

    -- §34/§36. One owner-readable place for every standing grant, with where it
    -- came from and when it was last used. A grant nobody can see is a grant
    -- nobody can revoke.
    CREATE TABLE IF NOT EXISTS permission_grants (
      grant_id TEXT PRIMARY KEY,
      permission TEXT NOT NULL,
      display_name TEXT NOT NULL,
      scope TEXT NOT NULL DEFAULT '',
      origin TEXT NOT NULL,
      origin_evidence_ref TEXT,
      granted_at_ms INTEGER NOT NULL,
      expires_at_ms INTEGER,
      last_used_at_ms INTEGER,
      use_count INTEGER NOT NULL DEFAULT 0,
      revoked_at_ms INTEGER,
      revocation_reason TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_permission_grants_live
      ON permission_grants(revoked_at_ms, permission);

    -- §38. The Browser Fabric generalised: a typed operation against any target
    -- surface, bound to a mission, with its own evidence and verifier.
    CREATE TABLE IF NOT EXISTS computer_operations (
      operation_id TEXT PRIMARY KEY,
      mission_id TEXT,
      activity_id TEXT,
      surface TEXT NOT NULL,
      target_application TEXT NOT NULL,
      operation_type TEXT NOT NULL,
      action_class TEXT NOT NULL,
      scope_json TEXT NOT NULL DEFAULT '{}',
      checkpoint_ref TEXT,
      evidence_ref TEXT,
      verifier_type TEXT NOT NULL DEFAULT 'NONE',
      state TEXT NOT NULL DEFAULT 'PENDING',
      error_code TEXT,
      started_at_ms INTEGER NOT NULL,
      completed_at_ms INTEGER
    );

    CREATE INDEX IF NOT EXISTS idx_computer_operations_mission
      ON computer_operations(mission_id, started_at_ms);
    """,
    17: MIGRATION_17,
    18: MIGRATION_18,
    19: MIGRATION_19,
    20: MIGRATION_20,
    21: MIGRATION_21,
    22: MIGRATION_22,
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
            # A fresh connection per query with journal_mode=delete and no busy timeout is
            # why two concurrent identical signed commands could both pass the idempotency
            # SELECT (finding P1-SEC-005). WAL lets readers and one writer coexist; the
            # busy timeout makes a contended write wait rather than raise immediately.
            await db.execute("PRAGMA journal_mode = WAL")
            await db.execute("PRAGMA busy_timeout = 5000")
            await db.execute("PRAGMA synchronous = NORMAL")
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