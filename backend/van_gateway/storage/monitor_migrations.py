"""Owner monitor state and canonical event projection; additive migration only."""
MIGRATION_58 = """
CREATE TABLE IF NOT EXISTS market_monitor_objects (
 owner_id TEXT NOT NULL, object_id TEXT NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('WATCHLIST','ALERT')),
 revision INTEGER NOT NULL CHECK(revision>0),
 state_json TEXT NOT NULL, state_sha256 TEXT NOT NULL,
 lifecycle TEXT NOT NULL CHECK(lifecycle IN ('ACTIVE','PAUSED','TRIGGERED')),
 arm_generation INTEGER NOT NULL DEFAULT 1 CHECK(arm_generation>0),
 armed_at_ms INTEGER NOT NULL, updated_at_ms INTEGER NOT NULL,
 evaluation_json TEXT, PRIMARY KEY(owner_id,object_id)
);
CREATE INDEX IF NOT EXISTS market_monitor_active
 ON market_monitor_objects(kind,lifecycle,owner_id,object_id);
CREATE TABLE IF NOT EXISTS market_monitor_operations (
 owner_id TEXT NOT NULL, request_id TEXT NOT NULL, request_sha256 TEXT NOT NULL,
 result_json TEXT NOT NULL, created_at_ms INTEGER NOT NULL,
 PRIMARY KEY(owner_id,request_id)
);
CREATE TABLE IF NOT EXISTS market_monitor_scan_budget (
 owner_id TEXT PRIMARY KEY, window_ms INTEGER NOT NULL,
 used INTEGER NOT NULL CHECK(used>=0)
);
CREATE TABLE IF NOT EXISTS market_monitor_publications (
 event_seq INTEGER PRIMARY KEY REFERENCES events(seq) ON DELETE CASCADE,
 projected INTEGER NOT NULL DEFAULT 0 CHECK(projected IN (0,1))
);
"""


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
