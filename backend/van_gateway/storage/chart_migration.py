"""Additive chart domain migration; no runtime imports or data reads."""
MIGRATION_56 = '''
CREATE TABLE IF NOT EXISTS chart_workspaces (
 owner_id TEXT NOT NULL, workspace_id TEXT NOT NULL, revision INTEGER NOT NULL,
 name TEXT NOT NULL, updated_at_ms INTEGER NOT NULL,
 PRIMARY KEY(owner_id,workspace_id)
);
CREATE TABLE IF NOT EXISTS chart_workspace_revisions (
 owner_id TEXT NOT NULL, workspace_id TEXT NOT NULL, revision INTEGER NOT NULL,
 state_json TEXT NOT NULL,state_sha256 TEXT NOT NULL,recorded_at_ms INTEGER NOT NULL,
 restored_from_revision INTEGER,
 PRIMARY KEY(owner_id,workspace_id,revision),
 FOREIGN KEY(owner_id,workspace_id) REFERENCES chart_workspaces(owner_id,workspace_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS chart_workspace_operations (
 owner_id TEXT NOT NULL,request_id TEXT NOT NULL,request_sha256 TEXT NOT NULL,
 result_json TEXT NOT NULL,created_at_ms INTEGER NOT NULL,
 PRIMARY KEY(owner_id,request_id)
);
'''
