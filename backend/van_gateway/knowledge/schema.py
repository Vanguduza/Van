from __future__ import annotations

import time

import aiosqlite

from van_gateway.storage.db import Store

KNOWLEDGE_SCHEMA_VERSION = 1


class KnowledgeSchema:
    def __init__(self, store: Store) -> None:
        self.store = store
        self.fts_enabled = False

    async def ensure(self) -> None:
        async with self.store.connection() as db:
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS knowledge_schema_migrations (
                  version INTEGER PRIMARY KEY,
                  applied_at_unix INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS knowledge_evidence (
                  evidence_id TEXT PRIMARY KEY,
                  provider TEXT NOT NULL,
                  query_id TEXT NOT NULL,
                  source_ref TEXT NOT NULL,
                  title TEXT,
                  source_trust TEXT NOT NULL,
                  epistemic_state TEXT NOT NULL,
                  scope TEXT NOT NULL,
                  retrieved_at_unix_ms INTEGER NOT NULL,
                  content_digest TEXT NOT NULL,
                  snippet TEXT NOT NULL,
                  metadata_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_knowledge_evidence_query
                  ON knowledge_evidence(provider, query_id, retrieved_at_unix_ms);
                CREATE INDEX IF NOT EXISTS idx_knowledge_evidence_source
                  ON knowledge_evidence(provider, source_ref, content_digest);
                CREATE TABLE IF NOT EXISTS knowledge_provider_certifications (
                  provider TEXT PRIMARY KEY,
                  state TEXT NOT NULL,
                  evidence_pointer TEXT,
                  verified_at_unix_ms INTEGER,
                  details_json TEXT NOT NULL,
                  updated_at_unix_ms INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS obsidian_documents (
                  document_id TEXT PRIMARY KEY,
                  relative_path TEXT NOT NULL UNIQUE,
                  title TEXT,
                  mtime_ns INTEGER NOT NULL,
                  size_bytes INTEGER NOT NULL,
                  content_digest TEXT NOT NULL,
                  body_text TEXT NOT NULL,
                  tags_json TEXT NOT NULL,
                  links_json TEXT NOT NULL,
                  frontmatter_json TEXT NOT NULL,
                  indexed_at_unix_ms INTEGER NOT NULL,
                  deleted_at_unix_ms INTEGER,
                  blocked_reason TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_obsidian_documents_active
                  ON obsidian_documents(deleted_at_unix_ms, relative_path);
                CREATE TABLE IF NOT EXISTS notebook_operations (
                  operation_id TEXT PRIMARY KEY,
                  provider TEXT NOT NULL,
                  operation TEXT NOT NULL,
                  idempotency_key TEXT NOT NULL UNIQUE,
                  request_digest TEXT NOT NULL,
                  status TEXT NOT NULL,
                  resource_id TEXT,
                  correlation_json TEXT NOT NULL,
                  observed_postcondition_json TEXT NOT NULL,
                  evidence_pointer TEXT,
                  error_code TEXT,
                  created_at_unix_ms INTEGER NOT NULL,
                  updated_at_unix_ms INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_notebook_operations_provider
                  ON notebook_operations(provider, updated_at_unix_ms);
                """
            )
            row = await (await db.execute(
                "SELECT COALESCE(MAX(version), 0) AS v FROM knowledge_schema_migrations"
            )).fetchone()
            current = int(row["v"]) if row is not None else 0
            if current < KNOWLEDGE_SCHEMA_VERSION:
                await db.execute(
                    "INSERT INTO knowledge_schema_migrations(version, applied_at_unix) VALUES (?, ?)",
                    (KNOWLEDGE_SCHEMA_VERSION, int(time.time())),
                )
            try:
                await db.execute(
                    """CREATE VIRTUAL TABLE IF NOT EXISTS obsidian_fts USING fts5(
                    document_id UNINDEXED, title, body_text, tags, links,
                    tokenize='unicode61 remove_diacritics 2'
                    )"""
                )
                self.fts_enabled = True
            except aiosqlite.OperationalError:
                self.fts_enabled = False
            await db.commit()