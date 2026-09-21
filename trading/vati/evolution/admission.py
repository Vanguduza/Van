"""Proposal admission control and gate health (TRD-REV51-125)."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Optional

from vati.core.canonical import canonical_hash
from vati.core.events import EventKind, make_event
from vati.evolution.proposals import SystemImprovementProposal
from vati.evolution.protected_paths import ProtectedPathPolicy

ADMISSION_VERSION = "proposal-admission/5.1.0"


class AdmissionState(str, Enum):
    ADMITTED = "ADMITTED"
    REJECTED = "REJECTED"
    HELD_FOR_AUTHORISED_REVIEW = "HELD_FOR_AUTHORISED_REVIEW"


REQUIRED_GATES = (
    "reproducibility",
    "evidence_quality",
    "replayability",
    "backtest",
    "shadow_evidence",
    "risk_regression",
    "execution_regression",
)


@dataclass(frozen=True)
class ProposalAdmission:
    proposal_id: str
    state: AdmissionState
    gates: tuple[tuple[str, bool], ...]
    protected_paths: tuple[str, ...]
    protected_markers: tuple[str, ...]
    owner_approval_required: bool
    owner_approved: bool
    reasons: tuple[str, ...]
    decided_ms: int
    admission_version: str = ADMISSION_VERSION

    def body(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "state": self.state.value,
            "gates": {k: v for k, v in self.gates},
            "protected_paths": list(self.protected_paths),
            "protected_markers": list(self.protected_markers),
            "owner_approval_required": self.owner_approval_required,
            "owner_approved": self.owner_approved,
            "reasons": list(self.reasons),
            "decided_ms": self.decided_ms,
            "admission_version": self.admission_version,
        }

    @property
    def digest(self) -> str:
        return canonical_hash(self.body())


class ProposalAdmissionControl:
    def __init__(self, *, policy: Optional[ProtectedPathPolicy] = None,
                 ledger=None, producer: str = "vati-proposal-admission") -> None:
        self.policy = policy or ProtectedPathPolicy()
        self._ledger = ledger
        self._producer = producer
        self._records: dict[str, ProposalAdmission] = {}

    def assess(self, proposal: SystemImprovementProposal, *,
               gate_evidence: Mapping[str, bool],
               diff_text: str = "",
               owner_approved: bool = False,
               now_ms: int) -> ProposalAdmission:
        if not proposal.seal_ok():
            raise ValueError("proposal seal invalid")
        scan = self.policy.scan(proposal.affected_paths, diff_text=diff_text)
        missing = [g for g in REQUIRED_GATES if g not in gate_evidence]
        failed = [g for g in REQUIRED_GATES if gate_evidence.get(g) is False]
        reasons: list[str] = []
        if missing:
            reasons.append("MISSING_GATES:" + ",".join(sorted(missing)))
        if failed:
            reasons.append("FAILED_GATES:" + ",".join(sorted(failed)))
        owner_required = bool(proposal.live_affecting and scan.requires_authorised_review)
        if owner_required and not owner_approved:
            reasons.append("OWNER_AUTHORISED_REVIEW_REQUIRED")

        if owner_required and not owner_approved:
            state = AdmissionState.HELD_FOR_AUTHORISED_REVIEW
        elif missing or failed:
            state = AdmissionState.REJECTED
        else:
            state = AdmissionState.ADMITTED

        rec = ProposalAdmission(
            proposal_id=proposal.proposal_id,
            state=state,
            gates=tuple(sorted((str(k), bool(v)) for k, v in gate_evidence.items())),
            protected_paths=scan.touched_paths,
            protected_markers=scan.marker_hits,
            owner_approval_required=owner_required,
            owner_approved=owner_approved,
            reasons=tuple(reasons),
            decided_ms=now_ms,
        )
        self._records[proposal.proposal_id] = rec
        if self._ledger is not None:
            self._ledger.append(make_event(
                EventKind.PROPOSAL_ADMISSION, self._producer,
                rec.body() | {"admission_hash": rec.digest},
                event_time_ms=now_ms, received_time_ms=now_ms,
                correlation_id=proposal.proposal_id,
            ))
        return rec

    def get(self, proposal_id: str) -> Optional[ProposalAdmission]:
        return self._records.get(proposal_id)
