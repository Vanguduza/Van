from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from urllib.parse import urlparse

import httpx

from van_gateway.context.models import SourceTrust
from van_gateway.research.models import ResearchEgressClass, ResearchSearchRequest, ResearchSearchResult, ResearchSource
from van_gateway.storage.db import Store


class ResearchPolicyError(ValueError):
    pass


_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password|passwd)\b\s*[:=]\s*\S+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{16,}\b"),
    re.compile(r"\b\d{6}\b.*\b(?:otp|verification|code)\b", re.IGNORECASE),
)


class ExaResearchService:
    """Gateway-mediated Exa adapter; provider credentials never leave the gateway."""

    def __init__(self, store: Store, *, api_key: str, base_url: str = "https://api.exa.ai", egress_enabled: bool = False,
                 timeout_seconds: float = 20.0, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.store = store
        self._api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.egress_enabled = egress_enabled
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @classmethod
    def _reject_secrets(cls, query: str) -> None:
        if any(pattern.search(query) for pattern in _SECRET_PATTERNS):
            raise ResearchPolicyError("query_contains_secret_like_material")

    def _authorize(self, request: ResearchSearchRequest) -> None:
        if not self.egress_enabled:
            raise ResearchPolicyError("research_egress_disabled")
        if not self._api_key:
            raise ResearchPolicyError("exa_api_key_unconfigured")
        if request.egress_class == ResearchEgressClass.PROHIBITED_EGRESS:
            raise ResearchPolicyError("prohibited_research_egress")
        if request.egress_class == ResearchEgressClass.SENSITIVE_CONTEXT and not request.owner_approved_sensitive_egress:
            raise ResearchPolicyError("sensitive_research_egress_requires_owner_approval")
        self._reject_secrets(request.query)

    async def status(self) -> dict[str, object]:
        ready_row = await self.store.fetchone("SELECT value FROM runtime_meta WHERE key='exa_ready_evidence_pointer'")
        state = "UNCONFIGURED"
        if self._api_key and self.egress_enabled:
            state = "READY" if ready_row is not None else "CONFIGURED"
        elif self._api_key:
            state = "CONFIGURED_EGRESS_DISABLED"
        return {"provider": "exa", "state": state, "credential_locus": "gateway", "egress_enabled": self.egress_enabled,
                "evidence_pointer": str(ready_row["value"]) if ready_row is not None else None}

    async def search(self, request: ResearchSearchRequest) -> ResearchSearchResult:
        self._authorize(request)
        research_id = str(uuid.uuid4())
        query_hash = self._hash(request.query)
        body: dict[str, object] = {
            "query": request.query,
            "type": request.mode.exa_type,
            "numResults": request.max_results,
            "moderation": True,
            "contents": {"highlights": True},
        }
        if request.include_domains:
            body["includeDomains"] = request.include_domains
        if request.exclude_domains:
            body["excludeDomains"] = request.exclude_domains
        if request.category:
            body["category"] = request.category

        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout_seconds, transport=self.transport) as client:
            response = await client.post("/search", headers={"x-api-key": self._api_key, "Content-Type": "application/json"}, json=body)
        response.raise_for_status()
        payload = response.json()
        sources: list[ResearchSource] = []
        retrieved_at = int(time.time() * 1000)
        for raw in payload.get("results", []):
            url = str(raw.get("url") or "").strip()
            if not url:
                continue
            highlights = [str(item)[:4000] for item in raw.get("highlights", []) if item]
            evidence_payload = {
                "title": raw.get("title"), "url": url, "publishedDate": raw.get("publishedDate"),
                "author": raw.get("author"), "highlights": highlights, "id": raw.get("id"),
            }
            content_digest = self._hash(json.dumps(evidence_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
            source = ResearchSource(
                title=str(raw.get("title")) if raw.get("title") is not None else None,
                url=url,
                published_at=str(raw.get("publishedDate")) if raw.get("publishedDate") is not None else None,
                author=str(raw.get("author")) if raw.get("author") is not None else None,
                highlights=highlights,
                source_id=str(raw.get("id")) if raw.get("id") is not None else None,
                content_digest=content_digest,
            )
            sources.append(source)
            await self.store.execute(
                """
                INSERT INTO research_evidence(
                  evidence_id, research_id, query_hash, source_url, source_title, source_domain,
                  source_trust, published_at, retrieved_at_unix_ms, content_digest, evidence_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), research_id, query_hash, source.url, source.title, urlparse(source.url).hostname,
                 SourceTrust.UNTRUSTED_EXTERNAL.value, source.published_at, retrieved_at, source.content_digest,
                 Store.dumps(evidence_payload)),
            )

        return ResearchSearchResult(
            research_id=research_id,
            request_id=str(payload.get("requestId")) if payload.get("requestId") is not None else None,
            resolved_search_type=str(payload.get("resolvedSearchType")) if payload.get("resolvedSearchType") is not None else None,
            query_hash=query_hash, sources=sources, cost_dollars=payload.get("costDollars"),
            evidence_pointer=f"gateway://research/{research_id}",
        )

    async def certify_canary(self, request: ResearchSearchRequest) -> dict[str, object]:
        result = await self.search(request)
        if not result.sources:
            raise ResearchPolicyError("exa_canary_returned_no_sources")
        pointer = result.evidence_pointer
        await self.store.execute(
            "INSERT INTO runtime_meta(key, value, updated_at_unix_ms) VALUES ('exa_ready_evidence_pointer', ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at_unix_ms=excluded.updated_at_unix_ms",
            (pointer, int(time.time() * 1000)),
        )
        return {"state": "READY", "evidence_pointer": pointer, "contains_secrets": False}
