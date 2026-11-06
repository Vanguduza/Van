"""Durable projections of original mission facts; no execution authority."""

# Store.migrate adds the schema-version marker and commits this same transaction.
MIGRATION_57 = """
BEGIN IMMEDIATE;
CREATE TABLE mission_learning_outbox (
 mission_id TEXT NOT NULL REFERENCES missions(mission_id) ON DELETE CASCADE,
 stage TEXT NOT NULL CHECK(stage IN ('OPENED','MISSION_OUTCOME','STRATEGY_OUTCOME','DECISION_OUTCOME')),
 created_at_ms INTEGER NOT NULL, attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts >= 0),
 queue_order INTEGER NOT NULL CHECK(queue_order >= 0),
 generation INTEGER NOT NULL DEFAULT 1 CHECK(generation > 0),
 last_failure TEXT, PRIMARY KEY(mission_id,stage)
);
CREATE INDEX idx_mission_learning_pending ON mission_learning_outbox(queue_order,mission_id,stage);
CREATE TABLE mission_strategy_observations (
 mission_id TEXT PRIMARY KEY REFERENCES missions(mission_id) ON DELETE CASCADE,
 state TEXT NOT NULL CHECK(state IN ('OBSERVED','LEGACY_UNRECONCILED')),
 strategy_id TEXT, scope_sha256 TEXT, outcome TEXT, recorded_at_ms INTEGER NOT NULL,
 CHECK ((state='LEGACY_UNRECONCILED' AND strategy_id IS NULL AND scope_sha256 IS NULL AND outcome IS NULL)
     OR (state='OBSERVED' AND strategy_id IS NOT NULL AND scope_sha256 IS NOT NULL AND outcome IS NOT NULL))
);
INSERT INTO mission_strategy_observations(mission_id,state,recorded_at_ms)
 SELECT mission_id,'LEGACY_UNRECONCILED',updated_at_ms FROM missions WHERE state IN
 ('VERIFIED_SUCCESS','PARTIAL_SUCCESS','UNVERIFIABLE','FAILED','BLOCKED_POLICY','BLOCKED_UNSAFE','CANCELLED','EXPIRED');
"""
