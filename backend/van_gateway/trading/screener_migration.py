"""Add saved screener rules while preserving every version-58 monitor byte."""
MIGRATION_59 = """
BEGIN IMMEDIATE;
ALTER TABLE market_monitor_objects RENAME TO market_monitor_objects_v58;
CREATE TABLE market_monitor_objects (
 owner_id TEXT NOT NULL, object_id TEXT NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('WATCHLIST','ALERT','SCREEN_RULE')),
 revision INTEGER NOT NULL CHECK(revision>0),
 state_json TEXT NOT NULL, state_sha256 TEXT NOT NULL,
 lifecycle TEXT NOT NULL CHECK(lifecycle IN ('ACTIVE','PAUSED','TRIGGERED')),
 arm_generation INTEGER NOT NULL DEFAULT 1 CHECK(arm_generation>0),
 armed_at_ms INTEGER NOT NULL, updated_at_ms INTEGER NOT NULL,
 evaluation_json TEXT, PRIMARY KEY(owner_id,object_id)
);
INSERT INTO market_monitor_objects
 (owner_id,object_id,kind,revision,state_json,state_sha256,lifecycle,
  arm_generation,armed_at_ms,updated_at_ms,evaluation_json)
 SELECT owner_id,object_id,kind,revision,state_json,state_sha256,lifecycle,
  arm_generation,armed_at_ms,updated_at_ms,evaluation_json
 FROM market_monitor_objects_v58;
DROP TABLE market_monitor_objects_v58;
CREATE INDEX market_monitor_active
 ON market_monitor_objects(kind,lifecycle,owner_id,object_id);
COMMIT;
"""
