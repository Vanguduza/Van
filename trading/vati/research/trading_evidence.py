"""TradingEvidenceCollector (§30, TRD-ENH-074).

The Remote Browser gives VATI a durable primary-source research surface it did
not have. The boundary is the whole design:

    MAY      explain · classify · flag contradiction · reduce confidence
             · trigger research · propose a strategy revision
    MAY NOT  set lot size · widen a stop · create a live strategy
             · promote a capsule · bypass the Risk Authority · send an order

Two facts this module refuses to conflate. Stagehand successfully fetching a
page proves *retrieval*, not truth. And a page saying "buy EURUSD" is untrusted
external content, not a signal — the trust tier travels with the artifact so a
downstream consumer cannot forget which it is holding.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Mapping, Optional

from vati.core.canonical import canonical_hash

#: Trust tiers. `UNTRUSTED_EXTERNAL` is the default and the common case.
UNTRUSTED_EXTERNAL = "UNTRUSTED_EXTERNAL"
PRIMARY_SOURCE = "PRIMARY_SOURCE"
VENUE_OFFICIAL = "VENUE_OFFICIAL"
TRUST_TIERS = (UNTRUSTED_EXTERNAL, PRIMARY_SOURCE, VENUE_OFFICIAL)

SOURCE_TYPES = (
    "CENTRAL_BANK_STATEMENT", "ECONOMIC_RELEASE", "RATE_ANNOUNCEMENT",
    "COMPANY_RESULTS", "ZSE_NOTICE", "VFEX_NOTICE", "CORPORATE_ACTION",
    "BROKER_SPECIFICATION", "MARGIN_CHANGE", "SWAP_CHANGE", "SESSION_CHANGE",
    "OTHER",
)

#: What browser evidence is allowed to do. Enumerated so a new effect has to be
#: added deliberately rather than appearing by accident.
ALLOWED_EFFECTS = frozenset({
    "EXPLAIN", "CLASSIFY", "FLAG_CONTRADICTION", "REDUCE_CONFIDENCE",
    "TRIGGER_RESEARCH", "PROPOSE_REVISION",
})
FORBIDDEN_EFFECTS = frozenset({
    "SET_SIZE", "WIDEN_STOP", "CREATE_STRATEGY", "PROMOTE_CAPSULE",
    "BYPASS_RISK", "SEND_ORDER", "RAISE_ACTION_CLASS", "INCREASE_RISK",
})


class EvidenceAuthorityError(PermissionError):
    """An effect browser evidence may never have."""


@dataclass(frozen=True)
class TradingEvidenceArtifact:
    evidence_id: str
    source_uri: str
    source_type: str
    source_hash: str
    observed_at_ms: int
    extracted_facts: Mapping[str, Any] = field(default_factory=dict)
    extractor_version: str = ""
    trust_tier: str = UNTRUSTED_EXTERNAL
    effective_at_ms: Optional[int] = None
    expires_at_ms: Optional[int] = None
    retrieval_verified: bool = False
    artifact_hash: str = ""

    def __post_init__(self) -> None:
        if self.trust_tier not in TRUST_TIERS:
            raise ValueError(f"unknown trust tier {self.trust_tier}")
        if self.source_type not in SOURCE_TYPES:
            raise ValueError(f"unknown source type {self.source_type}")

    @property
    def fresh_at(self) -> Any:
        def _f(now_ms: int) -> bool:
            if self.expires_at_ms is not None and now_ms >= self.expires_at_ms:
                return False
            if self.effective_at_ms is not None and now_ms < self.effective_at_ms:
                return False
            return True
        return _f

    def as_dict(self) -> dict:
        return {k: (dict(v) if isinstance(v, Mapping) else v)
                for k, v in self.__dict__.items() if k != "artifact_hash"}

    def sealed(self) -> "TradingEvidenceArtifact":
        return TradingEvidenceArtifact(**{**self.__dict__, "artifact_hash": canonical_hash(self.as_dict())})


@dataclass(frozen=True)
class EvidenceEffect:
    """A proposed use of evidence, checked before it is applied anywhere."""

    evidence_id: str
    effect: str
    target: str
    detail: str = ""
    #: Only ever <= 1: evidence may reduce confidence, never raise it.
    confidence_multiplier: Decimal = Decimal("1")

    def __post_init__(self) -> None:
        if self.effect in FORBIDDEN_EFFECTS:
            raise EvidenceAuthorityError(
                f"browser evidence may not {self.effect}; it is research, not authority")
        if self.effect not in ALLOWED_EFFECTS:
            raise EvidenceAuthorityError(f"unknown evidence effect {self.effect}")
        if self.confidence_multiplier > Decimal("1"):
            raise EvidenceAuthorityError(
                f"evidence may only reduce confidence, got {self.confidence_multiplier}")
        if self.confidence_multiplier < Decimal("0"):
            raise EvidenceAuthorityError("confidence multiplier below zero")


class TradingEvidenceCollector:
    """Holds artifacts and gates what may be done with them."""

    def __init__(self) -> None:
        self._artifacts: dict[str, TradingEvidenceArtifact] = {}

    def admit(self, artifact: TradingEvidenceArtifact) -> TradingEvidenceArtifact:
        if not artifact.artifact_hash:
            artifact = artifact.sealed()
        self._artifacts[artifact.evidence_id] = artifact
        return artifact

    def get(self, evidence_id: str) -> Optional[TradingEvidenceArtifact]:
        return self._artifacts.get(evidence_id)

    def active(self, now_ms: int) -> tuple[TradingEvidenceArtifact, ...]:
        return tuple(sorted((a for a in self._artifacts.values() if a.fresh_at(now_ms)),
                            key=lambda a: a.evidence_id))

    def propose(self, effect: EvidenceEffect) -> EvidenceEffect:
        """Effects are validated on construction; this records the linkage."""
        if effect.evidence_id not in self._artifacts:
            raise EvidenceAuthorityError(f"no such evidence {effect.evidence_id}")
        return effect


__all__ = [
    "ALLOWED_EFFECTS", "FORBIDDEN_EFFECTS", "PRIMARY_SOURCE", "SOURCE_TYPES",
    "TRUST_TIERS", "UNTRUSTED_EXTERNAL", "VENUE_OFFICIAL",
    "EvidenceAuthorityError", "EvidenceEffect", "TradingEvidenceArtifact",
    "TradingEvidenceCollector",
]
