"""Rev 1 §§75, 27 — the Relationship Calibration Engine.

§27 states the constraint that makes this safe, and it is worth quoting because
it is the whole design:

    Do NOT tune truth standards.
    Truth and evidence rules are invariant.
    Interaction style may adapt.

So this engine chooses *how* VAN says something and *how hard it pushes* — never
what it is willing to call true. The separation is enforced structurally: the
engine returns a `Calibration` carrying a challenge mode and presentation
preferences, and it has no field that could relax a verification requirement,
lower an evidence bar, or change a semantic class. There is nothing to tune
because nothing tunable exists.

The one asymmetry worth naming: calibration can raise the challenge mode above
what the owner's style would suggest, and can never lower it below what the
mission's consequences demand. An owner who prefers brisk agreement still gets
RED_TEAM on an irreversible decision, because §28 makes that a property of the
work rather than of the relationship.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from van_gateway.reasoning.kernel import ChallengeMode, required_mode
from van_gateway.storage.db import Store
from van_gateway.understanding.owner_model import (
    OwnerCognitiveModel,
    OwnerModelField,
)


class Verbosity(str, Enum):
    TERSE = "TERSE"
    BALANCED = "BALANCED"
    THOROUGH = "THOROUGH"


class EvidencePresentation(str, Enum):
    """How much of the evidence to lead with — never how much is required."""

    SUMMARY_FIRST = "SUMMARY_FIRST"
    EVIDENCE_FIRST = "EVIDENCE_FIRST"
    EVIDENCE_ON_REQUEST = "EVIDENCE_ON_REQUEST"


@dataclass(frozen=True)
class Calibration:
    """Style, and only style."""

    challenge_mode: ChallengeMode
    verbosity: Verbosity
    evidence_presentation: EvidencePresentation
    interrupt_threshold: float
    reasons: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "challenge_mode": self.challenge_mode.value,
            "verbosity": self.verbosity.value,
            "evidence_presentation": self.evidence_presentation.value,
            "interrupt_threshold": self.interrupt_threshold,
            "reasons": list(self.reasons),
            # Stated in the payload so any consumer can see the invariant rather
            # than having to trust that it held.
            "truth_standards_tuned": False,
        }


#: DECISION (recorded, no owner input): the fields calibration may read. Every
#: one is about interaction. `accepted_risk_patterns` is deliberately absent —
#: what risk the owner tolerates is an authority question answered by
#: DomainTrust, not a presentation question answered here.
CALIBRATION_INPUTS = frozenset({
    OwnerModelField.COMMUNICATION_PREFERENCE,
    OwnerModelField.REASONING_PREFERENCE,
    OwnerModelField.EVIDENCE_PREFERENCE,
    OwnerModelField.INTERRUPTION_PREFERENCE,
})


class RelationshipCalibrationEngine:
    """Adapts how VAN talks, using only what the owner has actually confirmed."""

    def __init__(self, store: Store) -> None:
        self.store = store
        self.owner_model = OwnerCognitiveModel(store)

    async def calibrate(
        self,
        *,
        owner_principal_id: str,
        consequential: bool = False,
        irreversible: bool = False,
        urgency: float = 0.5,
        van_confidence: float = 0.5,
        prior_corrections: int = 0,
    ) -> Calibration:
        """§75's inputs, resolved into a style — and a floor that cannot be lowered."""
        reasons: list[str] = []

        # §28 — the work sets the floor, not the relationship.
        floor = required_mode(consequential=consequential, irreversible=irreversible)
        mode = floor
        if floor is not ChallengeMode.BALANCED:
            reasons.append(f"consequence floor: {floor.value}")

        # Being corrected is evidence VAN is agreeing too easily, so it pushes
        # harder rather than softer. §71's failure mode is fluent agreement.
        if prior_corrections >= 2 and mode.minimum_alternatives < (
            ChallengeMode.CRITICAL.minimum_alternatives
        ):
            mode = ChallengeMode.CRITICAL
            reasons.append(f"{prior_corrections} prior corrections in this domain")

        # Low confidence is a reason to consider more alternatives, not to hedge
        # the wording and move on.
        if van_confidence < 0.4 and mode is ChallengeMode.BALANCED:
            mode = ChallengeMode.CRITICAL
            reasons.append("low confidence")

        confirmed = await self._confirmed_preferences(owner_principal_id)

        verbosity = Verbosity.BALANCED
        if self._prefers(confirmed, OwnerModelField.COMMUNICATION_PREFERENCE, "terse", "brief",
                         "short", "concise"):
            verbosity = Verbosity.TERSE
            reasons.append("owner-confirmed preference for terse updates")
        elif self._prefers(confirmed, OwnerModelField.REASONING_PREFERENCE, "thorough", "full",
                           "detail", "exhaustive"):
            verbosity = Verbosity.THOROUGH
            reasons.append("owner-confirmed preference for full reasoning")

        presentation = EvidencePresentation.SUMMARY_FIRST
        if self._prefers(confirmed, OwnerModelField.EVIDENCE_PREFERENCE, "evidence", "proof",
                         "receipts", "sources"):
            presentation = EvidencePresentation.EVIDENCE_FIRST
            reasons.append("owner-confirmed preference for evidence up front")

        # §29's thresholds shift with stated interruption tolerance and urgency,
        # within a band — never to zero, which would make VAN silent, and never
        # to one, which would make it constant.
        threshold = 0.55
        if self._prefers(confirmed, OwnerModelField.INTERRUPTION_PREFERENCE, "minimal",
                         "rarely", "quiet", "few"):
            threshold = 0.70
            reasons.append("owner-confirmed preference for fewer interruptions")
        threshold = max(0.25, min(0.85, threshold - (urgency - 0.5) * 0.2))

        # A thorough presentation on an urgent item is a worse answer than a
        # terse one, whatever the standing preference says.
        if urgency >= 0.8 and verbosity is Verbosity.THOROUGH:
            verbosity = Verbosity.BALANCED
            reasons.append("urgency overrides standing verbosity preference")

        return Calibration(
            challenge_mode=mode, verbosity=verbosity, evidence_presentation=presentation,
            interrupt_threshold=round(threshold, 3), reasons=tuple(reasons),
        )

    async def _confirmed_preferences(
        self, owner_principal_id: str
    ) -> dict[OwnerModelField, list[str]]:
        """Only CONFIRMED assertions, and only interaction fields.

        §64 — a CANDIDATE is something VAN noticed, not something it may act on.
        Calibrating off unconfirmed guesses is how an assistant starts behaving
        oddly for reasons the owner never agreed to.
        """
        out: dict[OwnerModelField, list[str]] = {}
        for field_name in CALIBRATION_INPUTS:
            assertions = await self.owner_model.actionable(
                owner_principal_id, field=field_name
            )
            if assertions:
                out[field_name] = [a.value.lower() for a in assertions]
        return out

    @staticmethod
    def _prefers(
        confirmed: dict[OwnerModelField, list[str]],
        field_name: OwnerModelField,
        *needles: str,
    ) -> bool:
        values = confirmed.get(field_name, [])
        return any(needle in value for value in values for needle in needles)


__all__ = [
    "CALIBRATION_INPUTS",
    "Calibration",
    "EvidencePresentation",
    "RelationshipCalibrationEngine",
    "Verbosity",
]
