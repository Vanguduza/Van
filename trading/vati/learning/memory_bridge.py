"""Hermes ↔ VTIL memory bridge (integration doc §3, §50; Rev 4 improvement).

Hermes persistent memory is continuity, never evidence. The bridge exports
structured ContinuityRecords (what VAN was working on) with TTLs into the
`trading` namespace only, refuses anything that looks like a credential, and
lets a record cite evidence only by VTIL artifact hash. Nothing here can be
promoted to knowledge without admission."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

from vati.core.canonical import canonical_hash

SECRET_PATTERNS = re.compile(r"(?i)(password|passwd|api[_-]?key|secret|token|bearer|private[_-]?key|login[_ ]?id|account[_ ]?number|otp)")
NAMESPACE = "trading"
DEFAULT_TTL_MS = {"OPEN_INVESTIGATION": 14 * 86_400_000, "PENDING_CANDIDATE": 30 * 86_400_000, "BROKER_ANOMALY": 7 * 86_400_000, "REGIME_NOTE": 3 * 86_400_000, "RESEARCH_PRIORITY": 7 * 86_400_000, "OWNER_PREFERENCE": 365 * 86_400_000}


class MemoryBridgeError(ValueError):
    pass


@dataclass(frozen=True)
class ContinuityRecord:
    kind: str                 # keys of DEFAULT_TTL_MS
    subject: str
    summary: str              # plain text, no secrets
    created_ms: int
    expires_ms: int
    evidence_hashes: tuple[str, ...] = ()   # VTIL artifact hashes only; free-text claims carry no authority
    namespace: str = NAMESPACE
    authority: str = "CONTINUITY_ONLY_NOT_EVIDENCE"
    record_hash: str = ""

    def sealed(self) -> "ContinuityRecord":
        return ContinuityRecord(**{**self.__dict__, "record_hash": canonical_hash({k: v for k, v in self.__dict__.items() if k != "record_hash"})})

    def expired(self, now_ms: int) -> bool:
        return now_ms >= self.expires_ms


@dataclass
class HermesMemoryBridge:
    records: dict[str, ContinuityRecord] = field(default_factory=dict)

    def remember(self, *, kind: str, subject: str, summary: str, now_ms: int, evidence_hashes: Iterable[str] = (), ttl_ms: Optional[int] = None) -> ContinuityRecord:
        if kind not in DEFAULT_TTL_MS:
            raise MemoryBridgeError(f"unknown continuity kind {kind}")
        if SECRET_PATTERNS.search(summary) or SECRET_PATTERNS.search(subject):
            raise MemoryBridgeError("credential-shaped content may not enter Hermes memory")
        hashes = tuple(evidence_hashes)
        if any(not re.fullmatch(r"[a-f0-9]{64}", h) for h in hashes):
            raise MemoryBridgeError("evidence must be cited by 64-hex VTIL artifact hash")
        rec = ContinuityRecord(kind, subject, summary, now_ms, now_ms + (ttl_ms or DEFAULT_TTL_MS[kind]), hashes).sealed()
        self.records[rec.record_hash] = rec
        return rec

    def recall(self, *, now_ms: int, kind: Optional[str] = None, subject: Optional[str] = None) -> list[ContinuityRecord]:
        return sorted((r for r in self.records.values() if not r.expired(now_ms) and (kind is None or r.kind == kind) and (subject is None or r.subject == subject)), key=lambda r: -r.created_ms)

    def expire(self, *, now_ms: int) -> int:
        dead = [h for h, r in self.records.items() if r.expired(now_ms)]
        for h in dead:
            del self.records[h]
        return len(dead)

    def export_prompt_context(self, *, now_ms: int, limit: int = 12) -> str:
        lines = [f"[{r.kind}] {r.subject}: {r.summary} (evidence: {', '.join(h[:8] for h in r.evidence_hashes) or 'none — continuity only'})" for r in self.recall(now_ms=now_ms)[:limit]]
        return "\n".join(lines)
