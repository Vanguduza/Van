"""One enforced taxonomy, and what the second one contributed to it.

P2-COG-002: two epistemic vocabularies existed. `EpistemicState` with `SourceTrust` was
enforced on admission to `owner_facts` and was what production actually used.
`SemanticClass` with `FORBIDDEN_SELF_PROMOTIONS` had zero production callers and no table
ever stored a `Claim`. Two taxonomies where one is live and one is aspirational is worse
than one, because a reader cannot tell which rules apply.

The reconciliation goes one way, and the direction is the decision:

**`EpistemicState` is the taxonomy.** It is the one enforced at the boundary that matters,
it is stored, and every fact in the system already carries it. Migrating to the other would
mean rewriting the admission gate to enforce something nothing has ever produced.

**`SemanticClass` becomes definitional, not storable.** It keeps the one thing the live
taxonomy lacked — the rule that a model inference may not quietly become a verified fact —
and that rule is now enforced where facts are actually admitted. What it loses is the
pretence of being a parallel store.

The mapping below is the join. It is total over `EpistemicState`, because a state with no
semantic class would be a fact the promotion rule could not reason about.
"""

from __future__ import annotations

from van_gateway.context.models import EpistemicState, SourceTrust
from van_gateway.epistemics.models import FORBIDDEN_SELF_PROMOTIONS, SemanticClass, may_promote

#: Every epistemic state, and what kind of claim it is. Total by construction; the test
#: asserts it, because a state added later without an entry would silently escape the
#: promotion rule.
SEMANTIC_FOR_STATE: dict[EpistemicState, SemanticClass] = {
    EpistemicState.CANONICAL_OWNER: SemanticClass.OWNER_INSTRUCTION,
    EpistemicState.PROJECT_TRUTH: SemanticClass.PROJECT_TRUTH,
    EpistemicState.VERIFIED_LIVE_STATE: SemanticClass.FACT_VERIFIED,
    EpistemicState.VERIFIED_HISTORY: SemanticClass.FACT_VERIFIED,
    EpistemicState.CONFIRMED_LEARNED: SemanticClass.OWNER_PREFERENCE,
    EpistemicState.EXTERNAL_EVIDENCE: SemanticClass.EXTERNAL_CLAIM,
    EpistemicState.INFERRED: SemanticClass.MODEL_INFERENCE,
    EpistemicState.STALE: SemanticClass.FACT_UNVERIFIED,
    EpistemicState.CONFLICTED: SemanticClass.FACT_UNVERIFIED,
    EpistemicState.UNKNOWN: SemanticClass.FACT_UNVERIFIED,
}

#: Source trusts that can legitimately establish something as verified fact. A promotion
#: to a factual authority needs one of these behind it, whatever the target state says.
VERIFYING_TRUSTS = frozenset({
    SourceTrust.OWNER_EXPLICIT,
    SourceTrust.LOCKED_AUTHORITY,
    SourceTrust.VERIFIED_SYSTEM,
    SourceTrust.TRUSTED_OWNER_FILE,
})


class PromotionRefused(ValueError):
    """A supersession that would upgrade what a claim is, without new authority."""


def semantic_class_for(state: EpistemicState) -> SemanticClass:
    return SEMANTIC_FOR_STATE[state]


def check_promotion(
    *,
    prior: EpistemicState,
    proposed: EpistemicState,
    proposed_trust: SourceTrust,
) -> None:
    """Refuse a supersession that promotes a claim past what its source can support.

    The rank check that already existed asks whether the new fact outranks the old one.
    This asks a different question: whether the *kind* of claim changed in a way that
    needs authority the new fact does not have. A model inference superseded by another
    model inference is fine; a model inference becoming a verified fact is the defect
    `FORBIDDEN_SELF_PROMOTIONS` was written to name and nothing ever enforced.
    """
    source = semantic_class_for(prior)
    target = semantic_class_for(proposed)
    if source is target:
        return
    if not may_promote(source, target):
        raise PromotionRefused(
            f"{prior.value} may not become {proposed.value}: "
            f"{source.value} -> {target.value} is a self-promotion"
        )
    if target.is_factual_authority and proposed_trust not in VERIFYING_TRUSTS:
        raise PromotionRefused(
            f"{proposed.value} claims factual authority on {proposed_trust.value}, "
            "which cannot establish one"
        )


__all__ = [
    "FORBIDDEN_SELF_PROMOTIONS",
    "SEMANTIC_FOR_STATE",
    "VERIFYING_TRUSTS",
    "PromotionRefused",
    "check_promotion",
    "semantic_class_for",
]
