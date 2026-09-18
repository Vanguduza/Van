from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any

from van_gateway.context.models import EpistemicState, SourceTrust
from van_gateway.knowledge.models import KnowledgeEvidence, KnowledgeProvider, ProviderState
from van_gateway.storage.db import Store


class KnowledgeEvidenceStore:
    def __init__(self, store: Store) -> None:
        self.store = store

    @staticmethod
    def canonical_json(value: Any) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def digest(cls, value: Any) -> str:
        raw = value if isinstance(value, str) else cls.canonical_json(value)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    async def persist(
        self,
        *,
        provider: KnowledgeProvider,
        query_id: str,
        source_ref: str,
        title: str | None,
        source_trust: SourceTrust,
        scope: str,
        content: Any,
        snippet: str,
        metadata: dict[str, Any] | None = None,
        epistemic_state: EpistemicState = EpistemicState.EXTERNAL_EVIDENCE,
        retrieved_at_ms: int | None = None,
    ) -> KnowledgeEvidence:
        retrieved_at_ms = retrieved_at_ms or int(time.time() * 1000)
        content_digest = self.digest(content)
        evidence = KnowledgeEvidence(
            evidence_id=str(uuid.uuid4()), provider=provider, query_id=query_id,
            source_ref=source_ref, title=title, source_trust=source_trust,
            epistemic_state=epistemic_state, scope=scope,
            retrieved_at_ms=retrieved_at_ms, content_digest=content_digest,
            snippet=snippet[:8000], metadata=metadata or {},
        )
        await self.store.execute(
            """INSERT INTO knowledge_evidence(
              evidence_id, provider, query_id, source_ref, title, source_trust,
              epistemic_state, scope, retrieved_at_unix_ms, content_digest,
              snippet, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                evidence.evidence_id, evidence.provider.value, evidence.query_id,
                evidence.source_ref, evidence.title, evidence.source_trust.value,
                evidence.epistemic_state.value, evidence.scope,
                evidence.retrieved_at_ms, evidence.content_digest, evidence.snippet,
                Store.dumps(evidence.metadata),
            ),
        )
        return evidence

    async def certify(
        self,
        provider: KnowledgeProvider,
        state: ProviderState,
        *,
        evidence_pointer: str | None,
        details: dict[str, Any],
    ) -> None:
        now = int(time.time() * 1000)
        verified = now if state == ProviderState.READY else None
        await self.store.execute(
            """INSERT INTO knowledge_provider_certifications(
              provider, state, evidence_pointer, verified_at_unix_ms, details_json, updated_at_unix_ms
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(provider) DO UPDATE SET state=excluded.state,
              evidence_pointer=excluded.evidence_pointer,
              verified_at_unix_ms=excluded.verified_at_unix_ms,
              details_json=excluded.details_json,
              updated_at_unix_ms=excluded.updated_at_unix_ms""",
            (provider.value, state.value, evidence_pointer, verified, Store.dumps(details), now),
        )

    async def certification(self, provider: KnowledgeProvider) -> dict[str, Any] | None:
        row = await self.store.fetchone(
            "SELECT * FROM knowledge_provider_certifications WHERE provider=?", (provider.value,)
        )
        if row is None:
            return None
        return {
            "state": str(row["state"]),
            "evidence_pointer": str(row["evidence_pointer"]) if row["evidence_pointer"] else None,
            "verified_at_ms": int(row["verified_at_unix_ms"]) if row["verified_at_unix_ms"] else None,
            "details": json.loads(row["details_json"] or "{}"),
        }