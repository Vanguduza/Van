"""Additive storage: Muse projections and commands use VAN's existing event sequence."""
MIGRATION_31 = """
CREATE TABLE muse_sources (
  producer_id TEXT PRIMARY KEY, sequence INTEGER NOT NULL, digest TEXT NOT NULL,
  observed_at_ms INTEGER NOT NULL, payload_json TEXT NOT NULL
);
CREATE TABLE muse_sessions (
  session_id TEXT PRIMARY KEY, producer_id TEXT NOT NULL, binding_digest TEXT NOT NULL,
  revision INTEGER NOT NULL, observed_at_ms INTEGER NOT NULL, present INTEGER NOT NULL,
  payload_json TEXT NOT NULL
);
CREATE TABLE muse_approvals (
  approval_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, revision INTEGER NOT NULL,
  fingerprint TEXT NOT NULL, state TEXT NOT NULL, command_id TEXT,
  observed_at_ms INTEGER NOT NULL, payload_json TEXT NOT NULL
);
CREATE TABLE muse_commands (
  command_id TEXT PRIMARY KEY, principal TEXT NOT NULL, idempotency_key TEXT NOT NULL,
  request_digest TEXT NOT NULL, payload_json TEXT NOT NULL, state TEXT NOT NULL,
  producer_id TEXT NOT NULL, created_at_ms INTEGER NOT NULL, expires_at_ms INTEGER NOT NULL,
  claimed_at_ms INTEGER, completed_at_ms INTEGER, result_json TEXT, linked_command_id TEXT,
  UNIQUE(principal, idempotency_key)
);
CREATE INDEX idx_muse_command_claim ON muse_commands(producer_id,state,created_at_ms);
CREATE INDEX idx_muse_session_source ON muse_sessions(producer_id,present);
CREATE INDEX idx_muse_approval_session ON muse_approvals(session_id,state);
"""
