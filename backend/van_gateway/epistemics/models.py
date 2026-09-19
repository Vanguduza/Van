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

What survives here is the class itself and the rule about promoting between
classes. An earlier design had a storable `Claim` carrying provenance, staleness
and an admission verdict; component ledger entries 2 and 4 recorded it as
`IMPLEMENTED_BUT_ISOLATED` with disposition DELETE, and reconciliation.py states
the reason plainly — no table ever stored one, and two taxonomies where one is
live and one is aspirational is worse than either alone. The live taxonomy is
`owner_facts`, whose `EpistemicState` does the storing. This module keeps the
part that is enforced: `SemanticClass` as a definitional vocabulary, and
`FORBIDDEN_SELF_PROMOTIONS`, which `check_promotion` applies on every fact
admission.
"""

from __future__ import annotations

from enum import Enum


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


__all__ = ["FORBIDDEN_SELF_PROMOTIONS", "SemanticClass", "may_promote"]
