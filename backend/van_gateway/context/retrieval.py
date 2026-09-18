from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from van_gateway.context.models import ContextGraphQuery, ContextRequirement, ReadinessState
from van_gateway.context.service import OwnerContextService
from van_gateway.storage.db import Store


_AUTHORITY_RANK = {
    "CANONICAL_OWNER": 800,
    "PROJECT_TRUTH": 700,
    "VERIFIED_LIVE_STATE": 600,
    "VERIFIED_HISTORY": 500,
    "CONFIRMED_LEARNED": 400,
    "EXTERNAL_EVIDENCE": 300,
    "INFERRED": 200,
    "STALE": 100,
    "CONFLICTED": 0,
    "UNKNOWN": -1,
}

_AUTHORITY_CASE = "CASE authority " + " ".join(
    f"WHEN '{name}' THEN {rank}" for name, rank in _AUTHORITY_RANK.items()
) + " ELSE -2 END"


class ContextRetrievalError(RuntimeError):
    pass


class ContextLexicalQuery(BaseModel):
    query: str = Field(min_length=1, max_length=256)
    scope: str = Field(default="global", min_length=1, max_length=128)
    max_results: int = Field(default=32, ge=1, le=64)
    allow_inferred: bool = False
    include_facts: bool = True
    include_edges: bool = True

    @field_validator("query")
    @classmethod
    def _query_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must not be blank")
        return value


class ContextLexicalHit(BaseModel):
    kind: Literal["fact", "edge"]
    object_id: str
    evidence_ref: str
    subject: str
    predicate: str
    value: str
    authority: str
    source_trust: str
    confidence_permille: int
    revision: int
    score: int
    matched_fields: list[str] = Field(default_factory=list)


class ContextLexicalResult(BaseModel):
    query: str
    normalized_query: str
    scope: str
    kernel_revision: int
    hits: list[ContextLexicalHit]
    truncated: bool
    scanned_facts: int
    scanned_edges: int
    compiled_at_ms: int


class HotContextCapsuleRequest(BaseModel):
    scopes: list[str] = Field(default_factory=lambda: ["global"])
    requirements: list[ContextRequirement] = Field(default_factory=list)
    seed_nodes: list[str] = Field(default_factory=list)
    lexical_queries: list[str] = Field(default_factory=list)
    allow_inferred: bool = False
    graph_depth: int = Field(default=1, ge=1, le=2)
    max_graph_edges: int = Field(default=48, ge=1, le=96)
    max_lexical_hits_per_query: int = Field(default=12, ge=1, le=24)
    ttl_ms: int = Field(default=30_000, ge=1_000, le=300_000)

    @field_validator("scopes")
    @classmethod
    def _normalize_scopes(cls, value: list[str]) -> list[str]:
        normalized = sorted({item.strip() for item in value if item.strip()})
        if not normalized:
            raise ValueError("scopes must contain at least one scope")
        if len(normalized) > 8:
            raise ValueError("scopes may contain at most 8 scopes")
        return normalized

    @field_validator("seed_nodes")
    @classmethod
    def _normalize_seeds(cls, value: list[str]) -> list[str]:
        normalized = sorted({item.strip() for item in value if item.strip()})
        if len(normalized) > 16:
            raise ValueError("seed_nodes may contain at most 16 nodes")
        return normalized

    @field_validator("lexical_queries")
    @classmethod
    def _normalize_lexical_queries(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            item = item.strip()
            if not item or item in seen:
                continue
            if len(item) > 256:
                raise ValueError("lexical query may contain at most 256 characters")
            seen.add(item)
            normalized.append(item)
        if len(normalized) > 8:
            raise ValueError("lexical_queries may contain at most 8 queries")
        return normalized

    @field_validator("requirements")
    @classmethod
    def _requirements_bound(cls, value: list[ContextRequirement]) -> list[ContextRequirement]:
        if len(value) > 32:
            raise ValueError("requirements may contain at most 32 entries")
        return value


class HotContextCapsule(BaseModel):
    capsule_id: str
    digest: str
    request_hash: str
    kernel_revision: int
    scopes: list[str]
    readiness_state: ReadinessState
    fact_refs: list[str] = Field(default_factory=list)
    graph_evidence_refs: list[str] = Field(default_factory=list)
    lexical_evidence_refs: list[str] = Field(default_factory=list)
    compiled_at_ms: int
    expires_at_ms: int
    cache_hit: bool = False


@dataclass
class _CachedCapsule:
    revision: int
    expires_at_ms: int
    capsule: HotContextCapsule


class ContextRetrievalService:
    """Bounded local retrieval for VAN owner context.

    This service deliberately performs no embedding lookup, model inference or
    remote call. Lexical results and hot capsules are evidence bundles only;
    authority remains in OwnerContextService.
    """

    def __init__(self, store: Store, context: OwnerContextService) -> None:
        self.store = store
        self.context = context
        self._hot_cache: dict[str, _CachedCapsule] = {}

    @staticmethod
    def _canonical_json(value: Any) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def _digest(cls, value: Any) -> str:
        return hashlib.sha256(cls._canonical_json(value).encode("utf-8")).hexdigest()

    @staticmethod
    def _normalize(value: str) -> str:
        folded = unicodedata.normalize("NFKC", value).casefold()
        return " ".join(re.findall(r"[^\W_]+", folded, flags=re.UNICODE))

    @classmethod
    def _tokens(cls, value: str) -> tuple[str, ...]:
        return tuple(cls._normalize(value).split())

    @classmethod
    def _score_fields(cls, query: str, fields: list[tuple[str, str, int, int]]) -> tuple[int, list[str]]:
        qn = cls._normalize(query)
        qtokens = set(qn.split())
        score = 0
        matched: list[str] = []
        for field_name, raw_value, token_weight, exact_bonus in fields:
            normalized = cls._normalize(raw_value)
            if not normalized:
                continue
            field_tokens = set(normalized.split())
            overlap = qtokens.intersection(field_tokens)
            field_score = len(overlap) * token_weight
            if normalized == qn:
                field_score += exact_bonus
            elif qn in normalized:
                field_score += max(1, exact_bonus // 8)
            elif normalized in qn:
                field_score += max(1, exact_bonus // 12)
            if field_score:
                score += field_score
                matched.append(field_name)
        return score, matched

    async def _fact_rows(self, query: ContextLexicalQuery, *, now_ms: int, candidate_limit: int) -> list[Any]:
        clauses = [
            "scope = ?",
            "valid_from_ms <= ?",
            "(valid_until_ms IS NULL OR valid_until_ms > ?)",
            "sensitivity != 'SECRET'",
        ]
        params: list[Any] = [query.scope, now_ms, now_ms]
        if not query.allow_inferred:
            clauses.append("authority != 'INFERRED'")
        sql = (
            "SELECT fact_id, subject, predicate, value_json, authority, source_trust, "
            "confidence_permille, revision, valid_from_ms FROM owner_facts WHERE "
            + " AND ".join(clauses)
            + f" ORDER BY {_AUTHORITY_CASE} DESC, confidence_permille DESC, valid_from_ms DESC, revision DESC, fact_id ASC LIMIT ?"
        )
        params.append(candidate_limit + 1)
        return await self.store.fetchall(sql, tuple(params))

    async def _edge_rows(self, query: ContextLexicalQuery, *, now_ms: int, candidate_limit: int) -> list[Any]:
        clauses = [
            "scope = ?",
            "valid_from_ms <= ?",
            "(valid_until_ms IS NULL OR valid_until_ms > ?)",
            "sensitivity != 'SECRET'",
        ]
        params: list[Any] = [query.scope, now_ms, now_ms]
        if not query.allow_inferred:
            clauses.append("authority != 'INFERRED'")
        sql = (
            "SELECT edge_id, from_node, predicate, to_node, authority, source_trust, "
            "confidence_permille, revision, valid_from_ms FROM owner_context_edges WHERE "
            + " AND ".join(clauses)
            + f" ORDER BY {_AUTHORITY_CASE} DESC, confidence_permille DESC, valid_from_ms DESC, revision DESC, edge_id ASC LIMIT ?"
        )
        params.append(candidate_limit + 1)
        return await self.store.fetchall(sql, tuple(params))

    async def lexical_query(
        self,
        query: ContextLexicalQuery,
        *,
        now_ms: int | None = None,
    ) -> ContextLexicalResult:
        now_ms = int(time.time() * 1000) if now_ms is None else now_ms
        candidate_limit = min(2048, max(256, query.max_results * 32))
        fact_rows = await self._fact_rows(query, now_ms=now_ms, candidate_limit=candidate_limit) if query.include_facts else []
        edge_rows = await self._edge_rows(query, now_ms=now_ms, candidate_limit=candidate_limit) if query.include_edges else []
        truncated = len(fact_rows) > candidate_limit or len(edge_rows) > candidate_limit
        fact_rows = fact_rows[:candidate_limit]
        edge_rows = edge_rows[:candidate_limit]

        ranked: list[tuple[tuple[Any, ...], ContextLexicalHit]] = []
        for row in fact_rows:
            try:
                rendered_value = self._canonical_json(json.loads(str(row["value_json"])))
            except (json.JSONDecodeError, TypeError, ValueError):
                rendered_value = str(row["value_json"])
            score, matched = self._score_fields(
                query.query,
                [
                    ("subject", str(row["subject"]), 1600, 12_000),
                    ("predicate", str(row["predicate"]), 1300, 10_000),
                    ("value", rendered_value, 700, 7_000),
                ],
            )
            if score <= 0:
                continue
            hit = ContextLexicalHit(
                kind="fact",
                object_id=str(row["fact_id"]),
                evidence_ref=f"context-fact:{row['fact_id']}:r{int(row['revision'])}",
                subject=str(row["subject"]),
                predicate=str(row["predicate"]),
                value=rendered_value,
                authority=str(row["authority"]),
                source_trust=str(row["source_trust"]),
                confidence_permille=int(row["confidence_permille"]),
                revision=int(row["revision"]),
                score=score,
                matched_fields=matched,
            )
            key = (
                -score,
                -_AUTHORITY_RANK.get(hit.authority, -2),
                -hit.confidence_permille,
                -hit.revision,
                0,
                hit.object_id,
            )
            ranked.append((key, hit))

        for row in edge_rows:
            score, matched = self._score_fields(
                query.query,
                [
                    ("from_node", str(row["from_node"]), 1600, 12_000),
                    ("predicate", str(row["predicate"]), 1300, 10_000),
                    ("to_node", str(row["to_node"]), 900, 8_000),
                ],
            )
            if score <= 0:
                continue
            hit = ContextLexicalHit(
                kind="edge",
                object_id=str(row["edge_id"]),
                evidence_ref=f"context-edge:{row['edge_id']}:r{int(row['revision'])}",
                subject=str(row["from_node"]),
                predicate=str(row["predicate"]),
                value=str(row["to_node"]),
                authority=str(row["authority"]),
                source_trust=str(row["source_trust"]),
                confidence_permille=int(row["confidence_permille"]),
                revision=int(row["revision"]),
                score=score,
                matched_fields=matched,
            )
            key = (
                -score,
                -_AUTHORITY_RANK.get(hit.authority, -2),
                -hit.confidence_permille,
                -hit.revision,
                1,
                hit.object_id,
            )
            ranked.append((key, hit))

        ranked.sort(key=lambda item: item[0])
        if len(ranked) > query.max_results:
            truncated = True
        hits = [hit for _, hit in ranked[: query.max_results]]
        return ContextLexicalResult(
            query=query.query,
            normalized_query=self._normalize(query.query),
            scope=query.scope,
            kernel_revision=await self.context.kernel_revision(),
            hits=hits,
            truncated=truncated,
            scanned_facts=len(fact_rows),
            scanned_edges=len(edge_rows),
            compiled_at_ms=now_ms,
        )

    @staticmethod
    def _stable_unique(values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result

    async def compile_hot_capsule(
        self,
        request: HotContextCapsuleRequest,
        *,
        now_ms: int | None = None,
    ) -> HotContextCapsule:
        now_ms = int(time.time() * 1000) if now_ms is None else now_ms
        request_payload = request.model_dump(mode="json")
        request_hash = self._digest(request_payload)
        initial_revision = await self.context.kernel_revision()
        cached = self._hot_cache.get(request_hash)
        if cached and cached.revision == initial_revision and cached.expires_at_ms > now_ms:
            return cached.capsule.model_copy(update={"cache_hit": True})

        for attempt in range(2):
            revision = await self.context.kernel_revision()
            readiness = await self.context.readiness(
                f"hot-context:{request_hash[:16]}",
                request.requirements,
                now_ms=now_ms,
            )
            fact_refs = [
                f"context-fact:{item.fact.fact_id}:r{item.fact.revision}"
                for item in readiness.requirements
                if item.state == ReadinessState.CURRENT and item.fact is not None
            ]

            graph_refs: list[str] = []
            if request.seed_nodes:
                for scope in request.scopes:
                    graph = await self.context.traverse_graph(
                        ContextGraphQuery(
                            seed_nodes=request.seed_nodes,
                            scope=scope,
                            max_depth=request.graph_depth,
                            max_edges=request.max_graph_edges,
                            allow_inferred=request.allow_inferred,
                        ),
                        now_ms=now_ms,
                    )
                    graph_refs.extend(graph.evidence_refs)

            lexical_refs: list[str] = []
            for scope in request.scopes:
                for lexical_text in request.lexical_queries:
                    result = await self.lexical_query(
                        ContextLexicalQuery(
                            query=lexical_text,
                            scope=scope,
                            max_results=request.max_lexical_hits_per_query,
                            allow_inferred=request.allow_inferred,
                        ),
                        now_ms=now_ms,
                    )
                    lexical_refs.extend(hit.evidence_ref for hit in result.hits)

            final_revision = await self.context.kernel_revision()
            if final_revision != revision:
                if attempt == 0:
                    continue
                raise ContextRetrievalError("context_revision_changed_during_hot_capsule_compile")

            fact_refs = self._stable_unique(fact_refs)
            graph_refs = self._stable_unique(graph_refs)
            lexical_refs = self._stable_unique(lexical_refs)
            digest_payload = {
                "request_hash": request_hash,
                "kernel_revision": revision,
                "readiness_state": readiness.state.value,
                "fact_refs": fact_refs,
                "graph_evidence_refs": graph_refs,
                "lexical_evidence_refs": lexical_refs,
            }
            digest = self._digest(digest_payload)
            capsule = HotContextCapsule(
                capsule_id=f"hotctx:{digest[:24]}",
                digest=digest,
                request_hash=request_hash,
                kernel_revision=revision,
                scopes=request.scopes,
                readiness_state=readiness.state,
                fact_refs=fact_refs,
                graph_evidence_refs=graph_refs,
                lexical_evidence_refs=lexical_refs,
                compiled_at_ms=now_ms,
                expires_at_ms=now_ms + request.ttl_ms,
                cache_hit=False,
            )
            self._hot_cache[request_hash] = _CachedCapsule(
                revision=revision,
                expires_at_ms=capsule.expires_at_ms,
                capsule=capsule,
            )
            return capsule

        raise ContextRetrievalError("hot_capsule_compile_failed")
