"""Rev 1 §§14, 67 — fact / inference / preference separation.

§14's rule is that every material decision-support claim carries a semantic
class, and that the class survives context compilation, reasoning, evidence, UI
explanation and knowledge admission. The reason is stated bluntly in §67:

    Owner belief is NOT factual authority.
    Owner instruction is authority over desired action within policy,
    not over external reality.

That distinction is what stops a personalised assistant becoming an echo
chamber. If "the owner said so" and "the world is measurably like this" are the
same kind of thing internally, then the more VAN learns about the owner the
more confidently it repeats the owner's errors back to them.

So a `Claim` is never bare text. It carries its class, its provenance, and what
would change it — and `SemanticClass.factual_weight` is deliberately not a
function of how confident anyone is.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SemanticClass(str, Enum):
    """§14 — the nine classes, and they are not interchangeable."""

    FACT_VERIFIED = "FACT_VERIFIED"
    FACT_UNVERIFIED = "FACT_UNVERIFIED"
    OWNER_PREFERENCE = "OWNER_PREFERENCE"
    OWNER_INSTRUCTION = "OWNER_INSTRUCTION"
    MODEL_INFERENCE = "MODEL_INFERENCE"
    HYPOTHESIS = "HYPOTHESIS"
    FORECAST = "FORECAST"
    EXTERNAL_CLAIM = "EXTERNAL_CLAIM"
    PROJECT_TRUTH = "PROJECT_TRUTH"

    @property
    def is_factual_authority(self) -> bool:
        """Whether this class may be cited as "the world is like this".

        Owner preference and instruction are excluded on purpose. They are
        authority over what VAN should *do*, never over what is *true*.
        """
        return self in (SemanticClass.FACT_VERIFIED, SemanticClass.PROJECT_TRUTH)

    @property
    def is_owner_authority(self) -> bool:
        """Whether this class may direct action within policy."""
        return self in (SemanticClass.OWNER_INSTRUCTION, SemanticClass.OWNER_PREFERENCE)

    @property
    def requires_provenance(self) -> bool:
        """§41 — provenance on 100% of non-owner facts."""
        return self not in (
            SemanticClass.OWNER_PREFERENCE,
            SemanticClass.OWNER_INSTRUCTION,
        )

    @property
    def is_speculative(self) -> bool:
        return self in (
            SemanticClass.HYPOTHESIS,
            SemanticClass.FORECAST,
            SemanticClass.MODEL_INFERENCE,
        )


#: §14 — how long a claim of each class stays fresh before it must be
#: re-established. DECISION (recorded): these are conservative defaults chosen
#: without owner input. Verified facts about the external world go stale fastest
#: because the world moves; project truth is re-derived from the repository so it
#: is cheap to refresh; owner preferences persist until contradicted rather than
#: expiring on a clock, because a preference that "expires" would make VAN
#: forget the owner for no reason.
DEFAULT_TTL_MS: dict[SemanticClass, int | None] = {
    SemanticClass.FACT_VERIFIED: 7 * 24 * 60 * 60 * 1000,
    SemanticClass.FACT_UNVERIFIED: 24 * 60 * 60 * 1000,
    SemanticClass.EXTERNAL_CLAIM: 24 * 60 * 60 * 1000,
    SemanticClass.FORECAST: 24 * 60 * 60 * 1000,
    SemanticClass.MODEL_INFERENCE: 3 * 24 * 60 * 60 * 1000,
    SemanticClass.HYPOTHESIS: 7 * 24 * 60 * 60 * 1000,
    SemanticClass.PROJECT_TRUTH: 14 * 24 * 60 * 60 * 1000,
    SemanticClass.OWNER_PREFERENCE: None,
    SemanticClass.OWNER_INSTRUCTION: None,
}


class Provenance(BaseModel):
    """Where a claim came from, precisely enough to go back and check."""

    source_kind: str
    source_ref: str
    observed_at_ms: int
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: float = 0.5

    @property
    def is_citable(self) -> bool:
        return bool(self.source_ref) and bool(self.source_kind)


class Claim(BaseModel):
    """One decision-support statement, with its class attached for life."""

    claim_id: str
    statement: str
    semantic_class: SemanticClass
    provenance: Provenance | None = None
    project_id: str | None = None
    sensitivity: str = "ROUTINE"
    superseded_by: str | None = None
    contradiction_group: str | None = None
    falsifier: str | None = None
    created_at_ms: int = 0

    @property
    def is_stale(self) -> bool:
        return self.staleness_at_ms(int(time.time() * 1000))

    def staleness_at_ms(self, now_ms: int) -> bool:
        ttl = DEFAULT_TTL_MS.get(self.semantic_class)
        if ttl is None:
            return False
        observed = self.provenance.observed_at_ms if self.provenance else self.created_at_ms
        return now_ms - observed > ttl

    @property
    def is_wellformed(self) -> bool:
        """§41 — provenance on every non-owner claim, without exception.

        Checked as a property rather than a validator so an ill-formed claim can
        be *represented* (and rejected with a reason) rather than being
        impossible to construct — a claim that cannot exist cannot be explained
        to the owner.
        """
        if self.superseded_by is not None:
            return True
        if self.semantic_class.requires_provenance:
            return self.provenance is not None and self.provenance.is_citable
        return True

    def as_context_line(self) -> dict[str, Any]:
        """What reaches a reasoner: the class travels with the statement.

        §14 — the class must survive into reasoning and UI explanation. Handing a
        model a bare string would strip exactly the distinction this exists for.
        """
        return {
            "claim_id": self.claim_id,
            "statement": self.statement,
            "class": self.semantic_class.value,
            "factual_authority": self.semantic_class.is_factual_authority,
            "source": self.provenance.source_ref if self.provenance else None,
            "confidence": self.provenance.confidence if self.provenance else None,
            "contradiction_group": self.contradiction_group,
        }


class AdmissionOutcome(str, Enum):
    ADMITTED = "ADMITTED"
    QUARANTINED = "QUARANTINED"
    REJECTED = "REJECTED"
    DUPLICATE = "DUPLICATE"
    SUPERSEDES = "SUPERSEDES"


class AdmissionVerdict(BaseModel):
    outcome: AdmissionOutcome
    reason: str
    claim_id: str | None = None
    supersedes_claim_id: str | None = None


#: §10 — class transitions a candidate may NOT make on its own.
#: DECISION (recorded): promotion into factual authority always requires either
#: a verifier receipt or the owner, never accumulated model confidence. Without
#: this, enough repetitions of a MODEL_INFERENCE would eventually become a fact.
FORBIDDEN_SELF_PROMOTIONS = frozenset({
    (SemanticClass.MODEL_INFERENCE, SemanticClass.FACT_VERIFIED),
    (SemanticClass.HYPOTHESIS, SemanticClass.FACT_VERIFIED),
    (SemanticClass.FORECAST, SemanticClass.FACT_VERIFIED),
    (SemanticClass.EXTERNAL_CLAIM, SemanticClass.FACT_VERIFIED),
    (SemanticClass.EXTERNAL_CLAIM, SemanticClass.PROJECT_TRUTH),
    (SemanticClass.MODEL_INFERENCE, SemanticClass.PROJECT_TRUTH),
    (SemanticClass.OWNER_PREFERENCE, SemanticClass.FACT_VERIFIED),
    (SemanticClass.OWNER_INSTRUCTION, SemanticClass.FACT_VERIFIED),
    (SemanticClass.MODEL_INFERENCE, SemanticClass.OWNER_PREFERENCE),
})


def may_promote(source: SemanticClass, target: SemanticClass) -> bool:
    """§§10, 14 — whether a reclassification is allowed without new authority."""
    if source is target:
        return True
    return (source, target) not in FORBIDDEN_SELF_PROMOTIONS


__all__ = [
    "DEFAULT_TTL_MS",
    "FORBIDDEN_SELF_PROMOTIONS",
    "AdmissionOutcome",
    "AdmissionVerdict",
    "Claim",
    "Provenance",
    "SemanticClass",
    "may_promote",
]
