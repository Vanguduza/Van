"""Research qualification and synthesis join (TRD-REV51-121)."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Sequence

from vati.core.canonical import canonical_hash
from vati.core.events import EventKind, make_event
from vati.research.missions import PacketState, ResearchMission, ResearchPacket

SYNTHESIS_VERSION = "research-synthesis/5.1.0"


class ClaimStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    CONTESTED = "CONTESTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    CONTRADICTED = "CONTRADICTED"
    STALE_EVIDENCE = "STALE_EVIDENCE"
    UNREPRODUCIBLE = "UNREPRODUCIBLE"


@dataclass(frozen=True)
class SynthesisedClaim:
    claim: str
    status: ClaimStatus
    packet_seals: tuple[str, ...]
    source_ids: tuple[str, ...]
    counterevidence: tuple[str, ...]

    def body(self) -> dict[str, Any]:
        return {
            "claim": self.claim, "status": self.status.value,
            "packet_seals": list(self.packet_seals),
            "source_ids": list(self.source_ids),
            "counterevidence": list(self.counterevidence),
        }


@dataclass(frozen=True)
class ResearchSynthesis:
    mission_id: str
    claims: tuple[SynthesisedClaim, ...]
    packet_seals: tuple[str, ...]
    created_ms: int
    synthesis_version: str = SYNTHESIS_VERSION

    @property
    def digest(self) -> str:
        return canonical_hash(self.body())

    @property
    def admitted_claims(self) -> tuple[SynthesisedClaim, ...]:
        return tuple(c for c in self.claims if c.status is ClaimStatus.SUPPORTED)

    def body(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "claims": [c.body() for c in self.claims],
            "packet_seals": list(self.packet_seals),
            "created_ms": self.created_ms,
            "synthesis_version": self.synthesis_version,
        }


class ResearchSynthesiser:
    def __init__(self, *, minimum_source_diversity: int = 2,
                 max_evidence_age_ms: int = 30 * 24 * 3_600_000,
                 ledger=None, producer: str = "vati-research-synthesis") -> None:
        self.minimum_source_diversity = minimum_source_diversity
        self.max_evidence_age_ms = max_evidence_age_ms
        self._ledger = ledger
        self._producer = producer

    def synthesise(self, mission: ResearchMission, packets: Sequence[ResearchPacket],
                   *, now_ms: int) -> ResearchSynthesis:
        if not mission.seal_ok():
            raise ValueError("mission seal invalid")
        complete = [p for p in packets if p.state is PacketState.COMPLETE and p.seal_ok()]
        statements = sorted({c.statement for p in complete for c in p.claims})
        out: list[SynthesisedClaim] = []
        for statement in statements:
            supporting = [p for p in complete if any(c.statement == statement for c in p.claims)]
            counters = [p for p in complete if statement in p.counterevidence]
            sources = tuple(sorted({s for p in supporting for s in p.source_ids}))
            counter = tuple(sorted({s for p in counters for s in p.source_ids}))
            seals = tuple(sorted(p.seal for p in supporting + counters))
            timestamps = [t for p in supporting for t in p.retrieved_ms]
            reproducible = bool(supporting) and all(bool(p.reproducibility) for p in supporting)

            if counters and not supporting:
                status = ClaimStatus.CONTRADICTED
            elif counters:
                status = ClaimStatus.CONTESTED
            elif timestamps and max(timestamps) < now_ms - self.max_evidence_age_ms:
                status = ClaimStatus.STALE_EVIDENCE
            elif not reproducible:
                status = ClaimStatus.UNREPRODUCIBLE
            elif len(sources) < self.minimum_source_diversity:
                status = ClaimStatus.INSUFFICIENT_EVIDENCE
            else:
                status = ClaimStatus.SUPPORTED
            out.append(SynthesisedClaim(statement, status, seals, sources, counter))

        result = ResearchSynthesis(
            mission_id=mission.mission_id,
            claims=tuple(out),
            packet_seals=tuple(sorted(p.seal for p in complete)),
            created_ms=now_ms,
        )
        if self._ledger is not None:
            self._ledger.append(make_event(
                EventKind.RESEARCH_SYNTHESIS, self._producer,
                result.body() | {"synthesis_hash": result.digest},
                event_time_ms=now_ms, received_time_ms=now_ms,
                correlation_id=mission.mission_id,
            ))
        return result
