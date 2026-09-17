"""VTIL admission (Rev 2 §6.3, §9): PROPOSED → QUARANTINED → VALIDATED →
ADMITTED | REJECTED. The proposer can never admit its own artifact; T4
community content cannot skip validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AdmissionError(RuntimeError):
    pass


class AdmissionState(str, Enum):
    PROPOSED = "PROPOSED"
    QUARANTINED = "QUARANTINED"
    VALIDATED = "VALIDATED"
    ADMITTED = "ADMITTED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


@dataclass
class _Record:
    artifact_hash: str
    knowledge_class: str
    proposed_by: str
    trust_tier: str
    state: AdmissionState = AdmissionState.PROPOSED
    validation_evidence: list[str] = field(default_factory=list)
    admitted_by: Optional[str] = None
    history: list[str] = field(default_factory=list)


class AdmissionLedger:
    def __init__(self) -> None:
        self._r: dict[str, _Record] = {}

    def propose(self, artifact_hash: str, *, knowledge_class: str, proposed_by: str, trust_tier: str) -> AdmissionState:
        if artifact_hash in self._r:
            raise AdmissionError("artifact already proposed")
        self._r[artifact_hash] = _Record(artifact_hash, knowledge_class, proposed_by, trust_tier, history=["PROPOSED"])
        return AdmissionState.PROPOSED

    def quarantine(self, artifact_hash: str) -> AdmissionState:
        return self._move(artifact_hash, AdmissionState.PROPOSED, AdmissionState.QUARANTINED)

    def validate(self, artifact_hash: str, *, evidence_ref: str) -> AdmissionState:
        r = self._r[artifact_hash]
        if not evidence_ref.strip():
            raise AdmissionError("validation requires an evidence reference")
        r.validation_evidence.append(evidence_ref)
        return self._move(artifact_hash, AdmissionState.QUARANTINED, AdmissionState.VALIDATED)

    def admit(self, artifact_hash: str, *, admitted_by: str) -> AdmissionState:
        r = self._r[artifact_hash]
        if admitted_by == r.proposed_by:
            raise AdmissionError("self-admission forbidden: proposer cannot admit its own artifact")
        if r.trust_tier.startswith("T4") and not r.validation_evidence:
            raise AdmissionError("T4 community content cannot be admitted without validation evidence")
        r.admitted_by = admitted_by
        return self._move(artifact_hash, AdmissionState.VALIDATED, AdmissionState.ADMITTED)

    def reject(self, artifact_hash: str, *, reason: str) -> AdmissionState:
        r = self._r[artifact_hash]
        if r.state is AdmissionState.ADMITTED:
            raise AdmissionError("admitted knowledge is superseded, never rejected in place")
        r.state = AdmissionState.REJECTED; r.history.append(f"REJECTED:{reason}")
        return r.state

    def supersede(self, artifact_hash: str, *, by_hash: str) -> AdmissionState:
        r = self._r[artifact_hash]
        if r.state is not AdmissionState.ADMITTED:
            raise AdmissionError("only admitted knowledge can be superseded")
        r.state = AdmissionState.SUPERSEDED; r.history.append(f"SUPERSEDED_BY:{by_hash}")
        return r.state

    def state(self, artifact_hash: str) -> AdmissionState:
        return self._r[artifact_hash].state

    def _move(self, h: str, frm: AdmissionState, to: AdmissionState) -> AdmissionState:
        r = self._r[h]
        if r.state is not frm:
            raise AdmissionError(f"{h[:8]}: cannot move {r.state.value} → {to.value}")
        r.state = to; r.history.append(to.value)
        return to
