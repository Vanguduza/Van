"""Research portfolio yield ledger (TRD-REV51-122).

Descriptive only: it measures the research programme; it cannot alter trading authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from vati.core.canonical import canonical_hash
from vati.core.events import EventKind, make_event


@dataclass(frozen=True)
class ResearchYieldRecord:
    mission_id: str
    cost_micros: int
    admitted_findings: int
    duplicate_findings: int
    rejected_findings: int
    invalidated_findings: int
    improvement_proposals: int
    downstream_value: str
    measured_ms: int

    def body(self) -> dict[str, Any]:
        return self.__dict__.copy()

    @property
    def digest(self) -> str:
        return canonical_hash(self.body())


class ResearchYieldLedger:
    def __init__(self, *, ledger=None, producer: str = "vati-research-yield") -> None:
        self._ledger = ledger
        self._producer = producer
        self._records: dict[str, ResearchYieldRecord] = {}

    def record(self, rec: ResearchYieldRecord) -> ResearchYieldRecord:
        if rec.cost_micros < 0:
            raise ValueError("research cost cannot be negative")
        prior = self._records.get(rec.mission_id)
        if prior is not None and prior.digest != rec.digest:
            raise ValueError("yield record is immutable for a mission")
        self._records[rec.mission_id] = rec
        if self._ledger is not None and prior is None:
            self._ledger.append(make_event(
                EventKind.RESEARCH_YIELD, self._producer,
                rec.body() | {"yield_hash": rec.digest},
                event_time_ms=rec.measured_ms, received_time_ms=rec.measured_ms,
                correlation_id=rec.mission_id,
            ))
        return rec

    def summary(self) -> dict[str, Any]:
        rows = list(self._records.values())
        return {
            "missions": len(rows),
            "cost_micros": sum(r.cost_micros for r in rows),
            "admitted_findings": sum(r.admitted_findings for r in rows),
            "duplicate_findings": sum(r.duplicate_findings for r in rows),
            "rejected_findings": sum(r.rejected_findings for r in rows),
            "invalidated_findings": sum(r.invalidated_findings for r in rows),
            "improvement_proposals": sum(r.improvement_proposals for r in rows),
            "downstream_values": [r.downstream_value for r in rows if r.downstream_value],
            "is_authority": False,
        }

    def records(self) -> list[ResearchYieldRecord]:
        return [self._records[k] for k in sorted(self._records)]
