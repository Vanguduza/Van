-- VATI hash-chained ledger on the transactional authority store (Rev 5 Part B).
-- Mirrors vati/core/ledger_pg.py SCHEMA so the service can also create it lazily.
CREATE ROLE vati LOGIN PASSWORD '__VATI_LEDGER_PASSWORD__' NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE SCHEMA IF NOT EXISTS vati AUTHORIZATION vati;
CREATE TABLE IF NOT EXISTS vati.events (
  seq BIGSERIAL PRIMARY KEY,
  kind TEXT NOT NULL, producer TEXT NOT NULL, correlation_id TEXT NOT NULL,
  event_time_ms BIGINT NOT NULL, received_time_ms BIGINT NOT NULL, decision_time_ms BIGINT,
  schema_version INTEGER NOT NULL, payload_json TEXT NOT NULL,
  event_hash TEXT NOT NULL, prev_hash TEXT NOT NULL, chain_hash TEXT NOT NULL UNIQUE,
  inserted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_vati_events_corr ON vati.events(correlation_id);
CREATE INDEX IF NOT EXISTS ix_vati_events_kind ON vati.events(kind);
CREATE TABLE IF NOT EXISTS vati.chain_head (ledger TEXT PRIMARY KEY, chain_hash TEXT NOT NULL, seq BIGINT NOT NULL);
ALTER TABLE vati.events OWNER TO vati;
ALTER TABLE vati.chain_head OWNER TO vati;
-- Append-only: the service user may INSERT/SELECT/UPDATE chain_head, never UPDATE/DELETE events.
REVOKE UPDATE, DELETE, TRUNCATE ON vati.events FROM vati;
GRANT SELECT, INSERT ON vati.events TO vati;
GRANT USAGE, SELECT ON SEQUENCE vati.events_seq_seq TO vati;
GRANT SELECT, INSERT, UPDATE ON vati.chain_head TO vati;
