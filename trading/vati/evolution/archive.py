"""Immutable strategy/system evolution archive (TRD-REV51-123)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from vati.core.canonical import canonical_hash
from vati.core.events import EventKind, make_event

ARCHIVE_VERSION = "evolution-archive/5.1.0"


@dataclass(frozen=True)
class EvolutionRecord:
    candidate_id: str
    incumbent_version: str
    candidate_version: str
    research_provenance: tuple[str, ...]
    training_evaluation_provenance: tuple[str, ...]
    test_corpus_version: str
    backtest_evidence: tuple[str, ...]
    shadow_evidence: tuple[str, ...]
    outcome: str
    rejection_reason: str
    supersedes: str
    created_ms: int
    archive_version: str = ARCHIVE_VERSION

    def body(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "incumbent_version": self.incumbent_version,
            "candidate_version": self.candidate_version,
            "research_provenance": list(self.research_provenance),
            "training_evaluation_provenance": list(self.training_evaluation_provenance),
            "test_corpus_version": self.test_corpus_version,
            "backtest_evidence": list(self.backtest_evidence),
            "shadow_evidence": list(self.shadow_evidence),
            "outcome": self.outcome,
            "rejection_reason": self.rejection_reason,
            "supersedes": self.supersedes,
            "created_ms": self.created_ms,
            "archive_version": self.archive_version,
        }

    @property
    def digest(self) -> str:
        return canonical_hash(self.body())


class EvolutionArchive:
    """Append-only content-addressed history. Existing records are never rewritten."""

    def __init__(self, *, ledger=None, producer: str = "vati-evolution-archive") -> None:
        self._ledger = ledger
        self._producer = producer
        self._records: dict[str, EvolutionRecord] = {}

    def append(self, record: EvolutionRecord) -> EvolutionRecord:
        if not record.candidate_id or not record.candidate_version:
            raise ValueError("candidate id and candidate version are required")
        prior = self._records.get(record.candidate_id)
        if prior is not None:
            if prior.digest != record.digest:
                raise ValueError(f"candidate {record.candidate_id} is immutable")
            return prior
        if record.supersedes and record.supersedes not in self._records:
            raise ValueError(f"superseded candidate {record.supersedes} is unknown")
        self._records[record.candidate_id] = record
        if self._ledger is not None:
            self._ledger.append(make_event(
                EventKind.EVOLUTION_CANDIDATE, self._producer,
                record.body() | {"record_hash": record.digest},
                event_time_ms=record.created_ms, received_time_ms=record.created_ms,
                correlation_id=record.candidate_id,
            ))
        return record

    def get(self, candidate_id: str) -> Optional[EvolutionRecord]:
        return self._records.get(candidate_id)

    def chain(self, candidate_id: str) -> list[EvolutionRecord]:
        out: list[EvolutionRecord] = []
        seen: set[str] = set()
        current = self._records.get(candidate_id)
        while current is not None:
            if current.candidate_id in seen:
                raise ValueError("evolution supersession cycle")
            seen.add(current.candidate_id)
            out.append(current)
            current = self._records.get(current.supersedes) if current.supersedes else None
        return out

    def records(self) -> list[EvolutionRecord]:
        return [self._records[k] for k in sorted(self._records)]
