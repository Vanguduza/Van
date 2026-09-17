from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any

from van_gateway.context.models import (
    ContextEdgeCandidate,
    ContextReadiness,
    ContextRequirement,
    ContextSnapshot,
    EpistemicState,
    OwnerFactCandidate,
    OwnerFactRecord,
    ReadinessState,
    RequirementResolution,
    SensitivityClass,
    SourceTrust,
)
from van_gateway.storage.db import Store


class ContextAdmissionError(ValueError):
    pass


_AUTHORITY_RANK: dict[EpistemicState, int] = {
    EpistemicState.CANONICAL_OWNER: 800,
    EpistemicState.PROJECT_TRUTH: 700,
    EpistemicState.VERIFIED_LIVE_STATE: 600,
    EpistemicState.VERIFIED_HISTORY: 500,
    EpistemicState.CONFIRMED_LEARNED: 400,
    EpistemicState.EXTERNAL_EVIDENCE: 300,
    EpistemicState.INFERRED: 200,
    EpistemicState.STALE: 100,
    EpistemicState.CONFLICTED: 0,
    EpistemicState.UNKNOWN: -1,
}

_HIGH_AUTHORITY = {
    EpistemicState.CANONICAL_OWNER,
    EpistemicState.PROJECT_TRUTH,
    EpistemicState.VERIFIED_LIVE_STATE,
    EpistemicState.VERIFIED_HISTORY,
    EpistemicState.CONFIRMED_LEARNED,
}


class OwnerContextService:
    """Deterministic canonical owner-context service.

    The gateway owns canonical state. This class performs no model inference. It
    stores provenance, preserves contradictions, provides deterministic temporal
    selection, and compiles immutable context snapshots for downstream planning.
    """

    def __init__(self, store: Store) -> None:
        self.store = store

    @staticmethod
    def _canonical_json(value: Any) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def _digest(cls, value: Any) -> str:
        return hashlib.sha256(cls._canonical_json(value).encode("utf-8")).hexdigest()

    @staticmethod
    def _validate_admission(candidate: OwnerFactCandidate) -> None:
        if candidate.sensitivity == SensitivityClass.SECRET:
            raise ContextAdmissionError("SECRET content is forbidden from canonical owner-context storage")
        if candidate.source_trust in {SourceTrust.UNTRUSTED_EXTERNAL, SourceTrust.MODEL_DERIVED}:
            if candidate.authority in _HIGH_AUTHORITY:
                raise ContextAdmissionError(
                    f"{candidate.source_trust.value} cannot be promoted directly to {candidate.authority.value}"
                )
        if candidate.authority == EpistemicState.CONFIRMED_LEARNED and candidate.source_trust not in {
            SourceTrust.OWNER_EXPLICIT,
            SourceTrust.VERIFIED_SYSTEM,
            SourceTrust.TRUSTED_OWNER_FILE,
        }:
            raise ContextAdmissionError("CONFIRMED_LEARNED requires owner/trusted-system provenance")
        if candidate.valid_until_ms is not None and candidate.valid_until_ms <= candidate.valid_from_ms:
            raise ContextAdmissionError("valid_until_ms must be after valid_from_ms")

    async def kernel_revision(self) -> int:
        row = await self.store.fetchone("SELECT value FROM runtime_meta WHERE key = 'owner_context_revision'")
        return int(row["value"]) if row is not None else 0

    async def _bump_revision(self) -> int:
        async with self.store.connection() as db:
            row = await (await db.execute("SELECT value FROM runtime_meta WHERE key = 'owner_context_revision'")).fetchone()
            revision = (int(row["value"]) if row is not None else 0) + 1
            await db.execute(
                "INSERT INTO runtime_meta(key, value, updated_at_unix_ms) VALUES ('owner_context_revision', ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at_unix_ms=excluded.updated_at_unix_ms",
                (str(revision), int(time.time() * 1000)),
            )
            await db.commit()
        return revision

    async def admit_fact(self, candidate: OwnerFactCandidate) -> OwnerFactRecord:
        self._validate_admission(candidate)
        content_digest = self._digest(candidate.value)
        revision = await self._bump_revision()

        async with self.store.connection() as db:
            if candidate.supersedes_fact_id:
                prior = await (await db.execute(
                    "SELECT authority, valid_from_ms, valid_until_ms FROM owner_facts WHERE fact_id = ?",
                    (candidate.supersedes_fact_id,),
                )).fetchone()
                if prior is None:
                    raise ContextAdmissionError("supersedes_fact_id does not exist")
                prior_authority = EpistemicState(str(prior["authority"]))
                if _AUTHORITY_RANK[candidate.authority] < _AUTHORITY_RANK[prior_authority]:
                    raise ContextAdmissionError("lower-authority fact cannot supersede higher-authority fact")
                if prior["valid_until_ms"] is None:
                    await db.execute(
                        "UPDATE owner_facts SET valid_until_ms = ?, updated_at_unix_ms = ? WHERE fact_id = ?",
                        (candidate.valid_from_ms, int(time.time() * 1000), candidate.supersedes_fact_id),
                    )

            await db.execute(
                """
                INSERT INTO owner_facts(
                  fact_id, subject, predicate, value_json, authority, source_trust, source_ref,
                  confidence_permille, confidence_profile_version, scope, valid_from_ms, valid_until_ms,
                  observed_at_ms, last_verified_at_ms, sensitivity, revision, content_digest,
                  created_at_unix_ms, updated_at_unix_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate.fact_id,
                    candidate.subject,
                    candidate.predicate,
                    self._canonical_json(candidate.value),
                    candidate.authority.value,
                    candidate.source_trust.value,
                    candidate.source_ref,
                    candidate.confidence_permille,
                    candidate.confidence_profile_version,
                    candidate.scope,
                    candidate.valid_from_ms,
                    candidate.valid_until_ms,
                    candidate.observed_at_ms,
                    candidate.last_verified_at_ms,
                    candidate.sensitivity.value,
                    revision,
                    content_digest,
                    int(time.time() * 1000),
                    int(time.time() * 1000),
                ),
            )
            await db.commit()
        return OwnerFactRecord(**candidate.model_dump(exclude={"supersedes_fact_id"}), revision=revision, content_digest=content_digest)

    @staticmethod
    def _row_to_fact(row: Any) -> OwnerFactRecord:
        return OwnerFactRecord(
            fact_id=str(row["fact_id"]),
            subject=str(row["subject"]),
            predicate=str(row["predicate"]),
            value=json.loads(row["value_json"]),
            authority=EpistemicState(str(row["authority"])),
            source_trust=SourceTrust(str(row["source_trust"])),
            source_ref=str(row["source_ref"]),
            confidence_permille=int(row["confidence_permille"]),
            confidence_profile_version=int(row["confidence_profile_version"]),
            scope=str(row["scope"]),
            valid_from_ms=int(row["valid_from_ms"]),
            valid_until_ms=int(row["valid_until_ms"]) if row["valid_until_ms"] is not None else None,
            observed_at_ms=int(row["observed_at_ms"]),
            last_verified_at_ms=int(row["last_verified_at_ms"]) if row["last_verified_at_ms"] is not None else None,
            sensitivity=SensitivityClass(str(row["sensitivity"])),
            revision=int(row["revision"]),
            content_digest=str(row["content_digest"]),
        )

    async def current_candidates(self, requirement: ContextRequirement, now_ms: int | None = None) -> list[OwnerFactRecord]:
        now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
        rows = await self.store.fetchall(
            """
            SELECT * FROM owner_facts
            WHERE subject = ? AND predicate = ? AND scope = ?
              AND valid_from_ms <= ?
              AND (valid_until_ms IS NULL OR valid_until_ms > ?)
            """,
            (requirement.subject, requirement.predicate, requirement.scope, now_ms, now_ms),
        )
        facts = [self._row_to_fact(row) for row in rows]
        if not requirement.allow_inferred:
            facts = [f for f in facts if f.authority != EpistemicState.INFERRED]
        return sorted(
            facts,
            key=lambda f: (_AUTHORITY_RANK[f.authority], f.valid_from_ms, f.revision, f.confidence_permille),
            reverse=True,
        )

    async def resolve_requirement(self, requirement: ContextRequirement, now_ms: int | None = None) -> RequirementResolution:
        now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
        facts = await self.current_candidates(requirement, now_ms=now_ms)
        if not facts:
            return RequirementResolution(requirement=requirement, state=ReadinessState.MISSING, reason="no_current_fact")

        top_rank = _AUTHORITY_RANK[facts[0].authority]
        top = [fact for fact in facts if _AUTHORITY_RANK[fact.authority] == top_rank]
        digests = {fact.content_digest for fact in top}
        if len(digests) > 1:
            return RequirementResolution(
                requirement=requirement,
                state=ReadinessState.CONFLICTED,
                conflicting_fact_ids=[fact.fact_id for fact in top],
                reason="same_authority_conflict",
            )

        selected = top[0]
        verified_at = selected.last_verified_at_ms or selected.observed_at_ms
        if requirement.max_age_ms is not None and now_ms - verified_at > requirement.max_age_ms:
            return RequirementResolution(requirement=requirement, state=ReadinessState.STALE, fact=selected, reason="fact_exceeds_max_age")
        return RequirementResolution(requirement=requirement, state=ReadinessState.CURRENT, fact=selected)

    async def readiness(self, command_id: str, requirements: list[ContextRequirement], now_ms: int | None = None) -> ContextReadiness:
        resolutions = [await self.resolve_requirement(req, now_ms=now_ms) for req in requirements]
        states = {item.state for item in resolutions}
        if ReadinessState.CONFLICTED in states:
            overall = ReadinessState.CONFLICTED
        elif ReadinessState.MISSING in states:
            overall = ReadinessState.MISSING
        elif ReadinessState.STALE in states:
            overall = ReadinessState.STALE
        elif all(state == ReadinessState.CURRENT for state in states):
            overall = ReadinessState.CURRENT
        else:
            overall = ReadinessState.UNKNOWN
        return ContextReadiness(command_id=command_id, state=overall, requirements=resolutions)

    async def compile_snapshot(
        self,
        command_id: str,
        requirements: list[ContextRequirement],
        *,
        graph_evidence_refs: list[str] | None = None,
        live_state_refs: list[str] | None = None,
        policy_refs: list[str] | None = None,
        now_ms: int | None = None,
    ) -> ContextSnapshot:
        now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
        ready = await self.readiness(command_id, requirements, now_ms=now_ms)
        if ready.state != ReadinessState.CURRENT:
            raise ContextAdmissionError(f"context_not_ready:{ready.state.value}")
        fact_ids = [item.fact.fact_id for item in ready.requirements if item.fact is not None]
        kernel_revision = await self.kernel_revision()
        payload = {
            "command_id": command_id,
            "kernel_revision": kernel_revision,
            "fact_ids": fact_ids,
            "graph_evidence_refs": graph_evidence_refs or [],
            "live_state_refs": live_state_refs or [],
            "policy_refs": policy_refs or [],
            "compiled_at_ms": now_ms,
        }
        digest = self._digest(payload)
        snapshot = ContextSnapshot(snapshot_id=str(uuid.uuid4()), digest=digest, **payload)
        await self.store.execute(
            """
            INSERT INTO context_snapshots(
              snapshot_id, command_id, kernel_revision, fact_ids_json, graph_evidence_refs_json,
              live_state_refs_json, policy_refs_json, compiled_at_ms, digest
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot.snapshot_id, snapshot.command_id, snapshot.kernel_revision,
                Store.dumps(snapshot.fact_ids), Store.dumps(snapshot.graph_evidence_refs),
                Store.dumps(snapshot.live_state_refs), Store.dumps(snapshot.policy_refs),
                snapshot.compiled_at_ms, snapshot.digest,
            ),
        )
        return snapshot

    async def admit_edge(self, candidate: ContextEdgeCandidate) -> int:
        if candidate.sensitivity == SensitivityClass.SECRET:
            raise ContextAdmissionError("SECRET content is forbidden from owner-context graph")
        if candidate.source_trust in {SourceTrust.UNTRUSTED_EXTERNAL, SourceTrust.MODEL_DERIVED} and candidate.authority in _HIGH_AUTHORITY:
            raise ContextAdmissionError("untrusted/model-derived edge cannot enter authoritative graph")
        revision = await self._bump_revision()
        async with self.store.connection() as db:
            if candidate.supersedes_edge_id:
                prior = await (await db.execute(
                    "SELECT authority, valid_until_ms FROM owner_context_edges WHERE edge_id = ?",
                    (candidate.supersedes_edge_id,),
                )).fetchone()
                if prior is None:
                    raise ContextAdmissionError("supersedes_edge_id does not exist")
                if _AUTHORITY_RANK[candidate.authority] < _AUTHORITY_RANK[EpistemicState(str(prior["authority"]))]:
                    raise ContextAdmissionError("lower-authority edge cannot supersede higher-authority edge")
                if prior["valid_until_ms"] is None:
                    await db.execute(
                        "UPDATE owner_context_edges SET valid_until_ms = ? WHERE edge_id = ?",
                        (candidate.valid_from_ms, candidate.supersedes_edge_id),
                    )
            await db.execute(
                """
                INSERT INTO owner_context_edges(
                  edge_id, from_node, predicate, to_node, authority, source_trust, source_ref,
                  confidence_permille, confidence_profile_version, scope, valid_from_ms, valid_until_ms,
                  observed_at_ms, sensitivity, revision
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate.edge_id, candidate.from_node, candidate.predicate, candidate.to_node,
                    candidate.authority.value, candidate.source_trust.value, candidate.source_ref,
                    candidate.confidence_permille, candidate.confidence_profile_version, candidate.scope,
                    candidate.valid_from_ms, candidate.valid_until_ms, candidate.observed_at_ms,
                    candidate.sensitivity.value, revision,
                ),
            )
            await db.commit()
        return revision

    async def export_scope(self, scope: str) -> dict[str, Any]:
        facts = await self.store.fetchall(
            "SELECT * FROM owner_facts WHERE scope = ? AND sensitivity != 'SECRET' ORDER BY revision",
            (scope,),
        )
        return {"scope": scope, "facts": [self._row_to_fact(row).model_dump(mode="json") for row in facts]}

    async def erase_scope(self, scope: str) -> int:
        async with self.store.connection() as db:
            cur = await db.execute("DELETE FROM owner_facts WHERE scope = ?", (scope,))
            await db.execute("DELETE FROM owner_context_edges WHERE scope = ?", (scope,))
            await db.commit()
            count = int(cur.rowcount if cur.rowcount is not None and cur.rowcount >= 0 else 0)
        if count:
            await self._bump_revision()
        return count
