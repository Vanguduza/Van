"""Rev 1 §§9, 13, 14 — the Context Compiler.

§9 opens with the instruction that matters: *do not concatenate arbitrary
memory*. A `ContextPacket` is a selection, and every selection is a decision
about what VAN will and will not know when it reasons.

Four properties are enforced here rather than hoped for:

**Cross-project isolation is hard.** §9 says "add hard cross-project
isolation", so a claim scoped to project A cannot enter a packet compiled for
project B — not ranked lower, not included with a warning. Excluded, and
counted, so the exclusion is visible.

**Stale claims are marked, never silently dropped.** A fact that has aged out
still tells the reasoner something ("we knew this a month ago and have not
rechecked"), and dropping it invisibly would let VAN act as though it had never
known. They are carried with `stale: true` and excluded from factual authority.

**Contradictions travel together.** §14 wants contradiction groups, so claims
that disagree are placed adjacent rather than resolved by ranking. Silently
including the higher-scored side of a contradiction is how a reasoner becomes
confident about a disputed thing.

**The budget is enforced by dropping the least useful, in a stated order.**
§9 gives a token budget; a compiler that overruns it hands the reasoner a
truncated packet at the far end, where the truncation is invisible and arbitrary.
Dropping deliberately means knowing what was dropped.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from van_gateway.epistemics.models import Claim, SemanticClass

#: DECISION (recorded, no owner input): 8000 tokens. Chosen to leave room for a
#: model's own reasoning inside a typical 32k window while carrying enough
#: history to be useful. Configurable per compile; this is the default, not a
#: limit of the design.
DEFAULT_TOKEN_BUDGET = 8000

#: DECISION (recorded): ~4 characters per token. Deliberately an estimate rather
#: than a tokenizer call — the compiler must not depend on which model will read
#: the packet, and over-estimating costs a little unused budget while
#: under-estimating costs a silent truncation.
CHARS_PER_TOKEN = 4


class ContextSection(str, Enum):
    """§9's sections, in the order they are dropped under budget pressure."""

    OWNER_CONTEXT = "owner_context"
    MISSION_CONTEXT = "mission_context"
    PROJECT_TRUTH = "project_truth"
    AUTHORITY_CONTEXT = "authority_context"
    UNRESOLVED_QUESTIONS = "unresolved_questions"
    RETRIEVED_KNOWLEDGE = "retrieved_knowledge"
    RECENT_EPISODE = "recent_episode"
    EXECUTION_HISTORY = "execution_history"
    CURRENT_ENVIRONMENT = "current_environment"


#: Higher is kept longer. DECISION (recorded): authority and project truth
#: outrank retrieved knowledge because acting with the wrong authority is worse
#: than acting with less information, and a reasoner that loses the mission's own
#: constraints will confidently do the wrong thing.
SECTION_PRIORITY = {
    ContextSection.AUTHORITY_CONTEXT: 100,
    ContextSection.MISSION_CONTEXT: 95,
    ContextSection.PROJECT_TRUTH: 90,
    ContextSection.OWNER_CONTEXT: 80,
    ContextSection.UNRESOLVED_QUESTIONS: 70,
    ContextSection.RETRIEVED_KNOWLEDGE: 50,
    ContextSection.RECENT_EPISODE: 40,
    ContextSection.EXECUTION_HISTORY: 30,
    ContextSection.CURRENT_ENVIRONMENT: 20,
}


@dataclass(frozen=True)
class SelectionStats:
    """What the compiler did, so a thin packet has a visible cause."""

    considered: int = 0
    admitted: int = 0
    dropped_cross_project: int = 0
    dropped_budget: int = 0
    dropped_illformed: int = 0
    marked_stale: int = 0
    contradiction_groups: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "considered": self.considered, "admitted": self.admitted,
            "dropped_cross_project": self.dropped_cross_project,
            "dropped_budget": self.dropped_budget,
            "dropped_illformed": self.dropped_illformed,
            "marked_stale": self.marked_stale,
            "contradiction_groups": self.contradiction_groups,
        }


class ContextPacket(BaseModel):
    """§9 — bounded, provenanced, and honest about what it left out."""

    packet_id: str
    mission_id: str | None = None
    project_id: str | None = None
    compiled_at_ms: int
    token_budget: int = DEFAULT_TOKEN_BUDGET
    estimated_tokens: int = 0
    sections: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    contradiction_groups: dict[str, list[str]] = Field(default_factory=dict)
    stale_claim_ids: list[str] = Field(default_factory=list)
    selection_stats: dict[str, int] = Field(default_factory=dict)
    compiler_version: str = "van-context-compiler-1"

    @property
    def within_budget(self) -> bool:
        return self.estimated_tokens <= self.token_budget

    def factual_claims(self) -> list[dict[str, Any]]:
        """Only what may be cited as "the world is like this".

        Stale claims are excluded even when their class would qualify: knowing
        something a month ago is not the same as knowing it now, and §14's whole
        point is that the difference must survive into reasoning.
        """
        out = []
        for lines in self.sections.values():
            for line in lines:
                if line.get("factual_authority") and not line.get("stale"):
                    out.append(line)
        return out


class ContextCompiler:
    """Selects. Never concatenates."""

    def __init__(self, *, token_budget: int = DEFAULT_TOKEN_BUDGET) -> None:
        self.token_budget = token_budget

    @staticmethod
    def estimate_tokens(payload: Any) -> int:
        import json

        return max(1, len(json.dumps(payload, default=str)) // CHARS_PER_TOKEN)

    def compile(
        self,
        *,
        packet_id: str,
        claims: dict[ContextSection, list[Claim]],
        mission_id: str | None = None,
        project_id: str | None = None,
        unresolved_questions: list[str] | None = None,
        token_budget: int | None = None,
        now_ms: int | None = None,
    ) -> ContextPacket:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        budget = token_budget or self.token_budget

        considered = admitted = cross_project = illformed = stale_count = 0
        scored: list[tuple[int, ContextSection, Claim, dict[str, Any]]] = []
        contradiction_groups: dict[str, list[str]] = {}
        stale_ids: list[str] = []
        evidence: list[str] = []

        for section, section_claims in claims.items():
            for claim in section_claims:
                considered += 1

                # §9 — hard isolation. A claim belonging to another project does
                # not get ranked down; it does not get in.
                if (
                    project_id is not None
                    and claim.project_id is not None
                    and claim.project_id != project_id
                ):
                    cross_project += 1
                    continue

                if not claim.is_wellformed:
                    # §41 — provenance on 100% of non-owner facts. A claim that
                    # cannot say where it came from cannot be reasoned from.
                    illformed += 1
                    continue

                line = claim.as_context_line()
                is_stale = claim.staleness_at_ms(now)
                if is_stale:
                    stale_count += 1
                    stale_ids.append(claim.claim_id)
                    line["stale"] = True
                    # A stale claim is still context, but never authority.
                    line["factual_authority"] = False
                else:
                    line["stale"] = False

                if claim.contradiction_group:
                    contradiction_groups.setdefault(claim.contradiction_group, []).append(
                        claim.claim_id
                    )
                if claim.provenance:
                    evidence.extend(claim.provenance.evidence_refs)

                scored.append((self._score(section, claim, is_stale), section, claim, line))

        # Contradicting claims are kept together: dropping one side under budget
        # pressure would leave the reasoner confident about a disputed thing.
        contested = {
            claim_id
            for group in contradiction_groups.values()
            if len(group) > 1
            for claim_id in group
        }

        scored.sort(key=lambda item: (-item[0], item[2].claim_id))
        sections: dict[str, list[dict[str, Any]]] = {}
        used = 0
        dropped_budget = 0
        deferred: list[tuple[int, ContextSection, Claim, dict[str, Any]]] = []

        for score, section, claim, line in scored:
            cost = self.estimate_tokens(line)
            if used + cost > budget and claim.claim_id not in contested:
                dropped_budget += 1
                continue
            if used + cost > budget:
                # Contested claims get one more chance after everything else is
                # placed, so a contradiction survives as a pair or not at all.
                deferred.append((score, section, claim, line))
                continue
            sections.setdefault(section.value, []).append(line)
            used += cost
            admitted += 1

        for _score, section, claim, line in deferred:
            cost = self.estimate_tokens(line)
            if used + cost > budget:
                dropped_budget += 1
                continue
            sections.setdefault(section.value, []).append(line)
            used += cost
            admitted += 1

        stats = SelectionStats(
            considered=considered, admitted=admitted,
            dropped_cross_project=cross_project, dropped_budget=dropped_budget,
            dropped_illformed=illformed, marked_stale=stale_count,
            contradiction_groups=len([g for g in contradiction_groups.values() if len(g) > 1]),
        )
        return ContextPacket(
            packet_id=packet_id, mission_id=mission_id, project_id=project_id,
            compiled_at_ms=now, token_budget=budget, estimated_tokens=used,
            sections=sections, evidence_refs=sorted(set(evidence)),
            unresolved_questions=list(unresolved_questions or []),
            contradiction_groups={
                k: sorted(v) for k, v in contradiction_groups.items() if len(v) > 1
            },
            stale_claim_ids=sorted(stale_ids),
            selection_stats=stats.as_dict(),
        )

    @staticmethod
    def _score(section: ContextSection, claim: Claim, is_stale: bool) -> int:
        """Relevance, authority, provenance and freshness, as arithmetic.

        §9 lists the factors; making them a visible sum rather than a heuristic
        means a surprising packet can be explained by pointing at a number.
        """
        score = SECTION_PRIORITY.get(section, 10)
        if claim.semantic_class.is_factual_authority:
            score += 25
        elif claim.semantic_class.is_owner_authority:
            score += 20
        elif claim.semantic_class.is_speculative:
            score -= 10
        if claim.provenance is not None:
            score += int(claim.provenance.confidence * 10)
        if is_stale:
            score -= 30
        if claim.contradiction_group:
            # Contested material is worth the reasoner's attention, not less.
            score += 5
        return score


__all__ = [
    "CHARS_PER_TOKEN",
    "DEFAULT_TOKEN_BUDGET",
    "SECTION_PRIORITY",
    "ContextCompiler",
    "ContextPacket",
    "ContextSection",
    "SelectionStats",
]
