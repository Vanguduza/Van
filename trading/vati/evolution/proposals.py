"""Typed system-improvement proposals (TRD-REV51-124)."""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Optional

from vati.core.canonical import canonical_hash
from vati.core.events import EventKind, make_event

PROPOSAL_VERSION = "improvement-proposal/5.1.0"


class ProposalType(str, Enum):
    STRATEGY_LOGIC = "STRATEGY_LOGIC"
    FEATURE = "FEATURE"
    THRESHOLD_TUNABLE = "THRESHOLD_TUNABLE"
    EXECUTION_POLICY = "EXECUTION_POLICY"
    CONTEXT_RETRIEVAL = "CONTEXT_RETRIEVAL"
    MODEL_PROMPT_SCHEMA = "MODEL_PROMPT_SCHEMA"
    OBSERVABILITY = "OBSERVABILITY"
    INFRASTRUCTURE = "INFRASTRUCTURE"


@dataclass(frozen=True)
class SystemImprovementProposal:
    proposal_id: str
    proposal_type: ProposalType
    title: str
    description: str
    evidence_refs: tuple[str, ...]
    affected_paths: tuple[str, ...]
    live_affecting: Optional[bool]
    proposed_by: str
    created_ms: int
    proposal_version: str = PROPOSAL_VERSION
    seal: str = ""

    def body(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "proposal_type": self.proposal_type.value,
            "title": self.title,
            "description": self.description,
            "evidence_refs": list(self.evidence_refs),
            "affected_paths": list(self.affected_paths),
            "live_affecting": self.live_affecting,
            "proposed_by": self.proposed_by,
            "created_ms": self.created_ms,
            "proposal_version": self.proposal_version,
        }

    def validate(self) -> None:
        if not self.proposal_id or not self.title or not self.description:
            raise ValueError("proposal id, title and description are required")
        if self.live_affecting is None:
            raise ValueError("proposal live impact is unclassified; INV-LEARN-001 forbids admission")
        if not self.evidence_refs:
            raise ValueError("proposal has no evidence provenance")

    def sealed(self) -> "SystemImprovementProposal":
        self.validate()
        return replace(self, seal=canonical_hash(self.body()))

    def seal_ok(self) -> bool:
        return bool(self.seal) and self.seal == canonical_hash(self.body())


class SystemImprovementProposalEngine:
    def __init__(self, *, ledger=None, producer: str = "vati-improvement-proposals") -> None:
        self._ledger = ledger
        self._producer = producer
        self._proposals: dict[str, SystemImprovementProposal] = {}

    def propose(self, proposal: SystemImprovementProposal) -> SystemImprovementProposal:
        sealed = proposal.sealed()
        prior = self._proposals.get(sealed.proposal_id)
        if prior is not None and prior.seal != sealed.seal:
            raise ValueError("proposal id already exists with different terms")
        self._proposals[sealed.proposal_id] = sealed
        if self._ledger is not None and prior is None:
            self._ledger.append(make_event(
                EventKind.IMPROVEMENT_PROPOSAL, self._producer,
                sealed.body() | {"seal": sealed.seal},
                event_time_ms=sealed.created_ms, received_time_ms=sealed.created_ms,
                correlation_id=sealed.proposal_id,
            ))
        return sealed

    def get(self, proposal_id: str) -> Optional[SystemImprovementProposal]:
        return self._proposals.get(proposal_id)
