"""LAC-348 original replacement intent and local certificate retirement outbox."""

MIGRATION_60 = """
CREATE TABLE IF NOT EXISTS owner_device_reenrollments (
 operation_id TEXT PRIMARY KEY,
 operator_id TEXT NOT NULL,
 owner_principal_id TEXT NOT NULL,
 request_digest TEXT NOT NULL,
 legacy INTEGER NOT NULL DEFAULT 0,
 original_binding_id TEXT NOT NULL,
 original_bound_at_ms INTEGER NOT NULL,
 original_device_id TEXT NOT NULL,
 native_operation_id TEXT NOT NULL,
 phase TEXT NOT NULL CHECK(phase IN ('RETIRING','READY','EXPIRED')),
 created_at_ms INTEGER NOT NULL,
 expires_at_ms INTEGER NOT NULL,
 encrypted_response TEXT NOT NULL,
 bootstrap_token_sha256 TEXT NOT NULL UNIQUE,
 pairing_ticket_sha256 TEXT,
 challenge TEXT NOT NULL,
 gateway_url TEXT,
 reason TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reenrollments_owner ON owner_device_reenrollments(owner_principal_id, phase);
CREATE UNIQUE INDEX IF NOT EXISTS uq_reenrollment_retiring_owner
 ON owner_device_reenrollments(owner_principal_id) WHERE phase = 'RETIRING';
CREATE TABLE IF NOT EXISTS device_certificate_retirements (
 device_id TEXT PRIMARY KEY,
 native_operation_id TEXT NOT NULL,
 requested_at_ms INTEGER NOT NULL,
 actions_retired INTEGER NOT NULL DEFAULT 0,
 certificates_retired_at_ms INTEGER
);
"""
