"""Rev 1 §§66, 68-71, 88 — the Critical Reasoning Kernel.

§62's target is a counterpart *"independent enough to catch what the owner
misses"*, and §71 names the failure mode that makes personalisation dangerous:
an assistant that has learned the owner well enough to agree with them
fluently. Everything here exists to make agreement cost something.

Three structural choices carry that:

**Solver, critic and verifier are separate passes with separate outputs.** §70
requires the separation and §17 adds that *no critic gains execution authority*.
The critic's findings are recorded beside the recommendation, not blended into
it, so a weak recommendation with three unanswered criticisms looks weak.

**An owner premise is assessed, not accepted.** `assess_premise` records what
the owner asserted, what the evidence says, and whether VAN agreed without
checking. That last flag is what makes §17's `unsupported_agreement_rate`
measurable instead of aspirational — a metric nobody records is a metric nobody
can fail.

**No hidden chain-of-thought is persisted.** §13 and §66 both say so. What
survives is the structure: facts, assumptions, alternatives, failure modes,
confidence. There is deliberately no column to put a reasoning trace in.
"""

from __future__ import annotations

import json
import time
import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from van_gateway.epistemics.models import SemanticClass
from van_gateway.reasoning.critic import critique
from van_gateway.jev.advisor import JevVanAdvisor, noul_probability
from van_gateway.storage.db import Store


class ChallengeMode(str, Enum):
    """§88 — how hard VAN pushes. Never how true it requires things to be."""

    SUPPORTIVE = "SUPPORTIVE"
    BALANCED = "BALANCED"
    CRITICAL = "CRITICAL"
    RED_TEAM = "RED_TEAM"

    @property
    def minimum_alternatives(self) -> int:
        return {
            ChallengeMode.SUPPORTIVE: 1, ChallengeMode.BALANCED: 2,
            ChallengeMode.CRITICAL: 3, ChallengeMode.RED_TEAM: 4,
        }[self]

    @property
    def requires_disconfirming_search(self) -> bool:
        """§28 — RED_TEAM actively seeks evidence against its own recommendation."""
        return self is ChallengeMode.RED_TEAM


#: §28 — "High-consequence missions must be at least CRITICAL." Encoded rather
#: than left to a caller's judgement, because the caller wanting to move fast is
#: exactly when this matters.
def required_mode(*, consequential: bool, irreversible: bool) -> ChallengeMode:
    if irreversible:
        return ChallengeMode.RED_TEAM
    if consequential:
        return ChallengeMode.CRITICAL
    return ChallengeMode.BALANCED


class Importance(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AssumptionStatus(str, Enum):
    ACTIVE = "ACTIVE"
    VERIFIED = "VERIFIED"
    FALSIFIED = "FALSIFIED"
    EXPIRED = "EXPIRED"
    SUPERSEDED = "SUPERSEDED"


class Assumption(BaseModel):
    assumption_id: str
    mission_id: str
    claim: str
    source: str
    importance: Importance = Importance.MEDIUM
    confidence: float = 0.5
    testability: str = "UNKNOWN"
    verification_plan: str | None = None
    status: AssumptionStatus = AssumptionStatus.ACTIVE
    resolved_evidence_refs: list[str] = Field(default_factory=list)
    #: What replaced this, when it was superseded. Carried so a cleared assumption can be
    #: read as a correction pointing somewhere rather than as a row that simply stopped
    #: blocking.
    superseded_by: str | None = None

    @property
    def blocks_irreversible_work(self) -> bool:
        """§15 — a high-impact assumption must be settled before irreversible work."""
        return (
            self.status is AssumptionStatus.ACTIVE
            and self.importance in (Importance.HIGH, Importance.CRITICAL)
        )


class CriticFinding(BaseModel):
    """§17's checklist, as a typed finding rather than prose."""

    kind: str
    detail: str
    severity: str = "MEDIUM"
    evidence_ref: str | None = None


CRITIC_KINDS = (
    "missing_constraint", "contradictory_evidence", "owner_confirmation_bias",
    "motivated_reasoning", "causal_overclaim", "ignored_alternative", "evidence_quality",
)


class ReasoningAssessment(BaseModel):
    """§66.1 — the structured output. Conclusions and evidence, never the trace."""

    assessment_id: str
    problem_statement: str
    mission_id: str | None = None
    known_facts: list[dict[str, Any]] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    hypotheses: list[str] = Field(default_factory=list)
    alternatives: list[str] = Field(default_factory=list)
    failure_modes: list[str] = Field(default_factory=list)
    counterfactuals: list[dict[str, Any]] = Field(default_factory=list)
    recommended_next_action: str | None = None
    confidence: float = 0.0
    evidence_refs: list[str] = Field(default_factory=list)
    challenge_mode: ChallengeMode = ChallengeMode.BALANCED
    critic_findings: list[CriticFinding] = Field(default_factory=list)
    verifier_findings: list[str] = Field(default_factory=list)
    created_at_ms: int = 0

    @property
    def meets_mode_requirements(self) -> bool:
        """§88 — the mode sets how many alternatives had to be considered."""
        return len(self.alternatives) >= self.challenge_mode.minimum_alternatives

    @property
    def has_unaddressed_criticism(self) -> bool:
        return any(f.severity in ("HIGH", "CRITICAL") for f in self.critic_findings)

    @property
    def is_actionable(self) -> bool:
        """A recommendation with unanswered high-severity criticism is not advice."""
        return (
            self.recommended_next_action is not None
            and self.meets_mode_requirements
            and not self.has_unaddressed_criticism
        )


#: §16's required counterfactual questions. Asked every time for a consequential
#: decision, because the ones that get skipped are the ones that were
#: uncomfortable.
REQUIRED_COUNTERFACTUALS = (
    "What if the primary assumption is wrong?",
    "What if no action is taken?",
    "What if the opposite strategy is used?",
    "What reversible experiment would reduce uncertainty?",
    "What evidence would change this recommendation?",
    "What is the worst credible failure mode?",
)


def _optional_column(row: Any, column: str) -> str | None:
    """A nullable column a row may not carry, for queries with explicit column lists."""
    try:
        value = row[column]
    except (IndexError, KeyError):
        return None
    return str(value) if value is not None else None


class ReasoningError(ValueError):
    def __init__(self, code: str, detail: str | None = None) -> None:
        super().__init__(code if detail is None else f"{code}: {detail}")
        self.code = code
        self.detail = detail


class CriticalReasoningKernel:
    """Structures a consequential decision, and records what it could not settle."""

    def __init__(self, store: Store, *, jev_advisor: JevVanAdvisor | None = None) -> None:
        self.store = store
        self.jev_advisor = jev_advisor

    # ------------------------------------------------------------ assessment

    async def assess(
        self,
        *,
        problem_statement: str,
        challenge_mode: ChallengeMode,
        known_facts: list[dict[str, Any]] | None = None,
        assumptions: list[str] | None = None,
        uncertainties: list[str] | None = None,
        contradictions: list[str] | None = None,
        hypotheses: list[str] | None = None,
        alternatives: list[str] | None = None,
        failure_modes: list[str] | None = None,
        counterfactuals: list[dict[str, Any]] | None = None,
        recommended_next_action: str | None = None,
        confidence: float = 0.0,
        evidence_refs: list[str] | None = None,
        #: P0-COG-001 — these are now *additional* findings a caller may contribute, not
        #: the whole critique. The kernel derives its own and they cannot be suppressed.
        critic_findings: list[CriticFinding] | None = None,
        verifier_findings: list[str] | None = None,
        mission_id: str | None = None,
        now_ms: int | None = None,
    ) -> ReasoningAssessment:
        """Assess, criticise, and refuse the assessments that do not meet their mode.

        The refusal matters: an assessment claiming RED_TEAM rigour with one
        alternative considered is worse than no assessment, because it carries
        the authority of a process that did not actually happen.

        P0-COG-001 — this used to take `critic_findings` from the caller and store them,
        so an assessment with zero findings and 0.99 confidence was recorded as actionable
        and the matrix described the result as a solver/critic/verifier separation. The
        critic now runs over what the assessment actually contains. Caller-supplied
        findings are merged in rather than replaced by, because a caller that noticed
        something real should be able to say so — but it cannot make the kernel's own
        findings go away, which is the property that was missing.
        """
        now = int(time.time() * 1000) if now_ms is None else now_ms
        derived = [
            CriticFinding(**finding)
            for finding in critique(
                problem_statement=problem_statement,
                known_facts=list(known_facts or []),
                assumptions=list(assumptions or []),
                alternatives=list(alternatives or []),
                contradictions=list(contradictions or []),
                failure_modes=list(failure_modes or []),
                evidence_refs=list(evidence_refs or []),
                recommended_next_action=recommended_next_action,
                confidence=confidence,
            )
        ]
        # Jev is an optional raise-only critic extension. In SHADOW/ADVISORY it is
        # still evaluated by the shared service but cannot change this assessment.
        jev_findings: list[CriticFinding] = []
        if self.jev_advisor is not None and self.jev_advisor.configured:
            try:
                annotation = await self.jev_advisor.critic(
                    {
                        "problem_statement": problem_statement,
                        "known_facts": list(known_facts or []),
                        "assumptions": list(assumptions or []),
                        "uncertainties": list(uncertainties or []),
                        "contradictions": list(contradictions or []),
                        "alternatives": list(alternatives or []),
                        "failure_modes": list(failure_modes or []),
                        "recommended_next_action": recommended_next_action,
                        "evidence_refs": list(evidence_refs or []),
                    }
                )
                if annotation is not None and annotation.apply_effect:
                    unsupported = noul_probability(annotation.answers.get("unsupported_claim"))
                    missing = noul_probability(annotation.answers.get("missing_prerequisite"))
                    if unsupported is not None and unsupported >= 0.80:
                        jev_findings.append(
                            CriticFinding(
                                kind="evidence_quality",
                                detail=f"Jev critic flags an important unsupported claim (p={unsupported:.2f})",
                                severity="HIGH",
                                evidence_ref=annotation.result_fingerprint,
                            )
                        )
                    if missing is not None and missing >= 0.80:
                        jev_findings.append(
                            CriticFinding(
                                kind="missing_constraint",
                                detail=f"Jev critic flags a missing prerequisite or contradictory condition (p={missing:.2f})",
                                severity="HIGH",
                                evidence_ref=annotation.result_fingerprint,
                            )
                        )
            except Exception:
                # An optional critic provider cannot suppress or weaken the deterministic critic.
                pass

        # The caller's findings first and Jev findings only add. The deterministic
        # critic is always retained, so no model can erase an existing finding.
        merged = list(critic_findings or []) + jev_findings + derived
        assessment = ReasoningAssessment(
            assessment_id=f"ras_{uuid.uuid4().hex}", problem_statement=problem_statement,
            mission_id=mission_id, known_facts=list(known_facts or []),
            assumptions=list(assumptions or []), uncertainties=list(uncertainties or []),
            contradictions=list(contradictions or []), hypotheses=list(hypotheses or []),
            alternatives=list(alternatives or []), failure_modes=list(failure_modes or []),
            counterfactuals=list(counterfactuals or []),
            recommended_next_action=recommended_next_action, confidence=confidence,
            evidence_refs=sorted(set(evidence_refs or [])), challenge_mode=challenge_mode,
            critic_findings=merged,
            verifier_findings=list(verifier_findings or []), created_at_ms=now,
        )
        if recommended_next_action and not assessment.meets_mode_requirements:
            raise ReasoningError(
                "REASONING_MODE_REQUIREMENTS_UNMET",
                f"{challenge_mode.value} needs >= "
                f"{challenge_mode.minimum_alternatives} alternatives, "
                f"got {len(assessment.alternatives)}",
            )
        # §41 — hallucinated evidence = 0. A cited fact with no reference is
        # refused here rather than believed downstream.
        for fact in assessment.known_facts:
            if fact.get("factual_authority") and not fact.get("source"):
                raise ReasoningError(
                    "REASONING_UNSOURCED_FACT", str(fact.get("statement", ""))[:120]
                )
        await self._persist(assessment)
        return assessment

    async def _persist(self, a: ReasoningAssessment) -> None:
        await self.store.execute(
            """
            INSERT INTO reasoning_assessments(
              assessment_id, mission_id, problem_statement, known_facts_json,
              assumptions_json, uncertainties_json, contradictions_json, hypotheses_json,
              alternatives_json, failure_modes_json, counterfactuals_json,
              recommended_next_action, confidence, evidence_refs_json, challenge_mode,
              critic_findings_json, verifier_findings_json, created_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                a.assessment_id, a.mission_id, a.problem_statement,
                Store.dumps(a.known_facts), Store.dumps(a.assumptions),
                Store.dumps(a.uncertainties), Store.dumps(a.contradictions),
                Store.dumps(a.hypotheses), Store.dumps(a.alternatives),
                Store.dumps(a.failure_modes), Store.dumps(a.counterfactuals),
                a.recommended_next_action, a.confidence, Store.dumps(a.evidence_refs),
                a.challenge_mode.value,
                Store.dumps([f.model_dump(mode="json") for f in a.critic_findings]),
                Store.dumps(a.verifier_findings), a.created_at_ms,
            ),
        )

    @staticmethod
    def missing_counterfactuals(assessment: ReasoningAssessment) -> list[str]:
        """§16 — which required questions were not asked."""
        asked = {str(c.get("question", "")).strip() for c in assessment.counterfactuals}
        return [q for q in REQUIRED_COUNTERFACTUALS if q not in asked]

    # ----------------------------------------------------------- assumptions

    async def record_assumption(
        self,
        *,
        mission_id: str,
        claim: str,
        source: str,
        importance: Importance = Importance.MEDIUM,
        confidence: float = 0.5,
        testability: str = "UNKNOWN",
        verification_plan: str | None = None,
        now_ms: int | None = None,
    ) -> Assumption:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        assumption = Assumption(
            assumption_id=f"asm_{uuid.uuid4().hex}", mission_id=mission_id, claim=claim,
            source=source, importance=importance, confidence=confidence,
            testability=testability, verification_plan=verification_plan,
        )
        await self.store.execute(
            """
            INSERT INTO assumption_ledger(
              assumption_id, mission_id, claim, source, importance, confidence, testability,
              verification_plan, status, resolved_evidence_refs_json, created_at_ms,
              updated_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', ?, ?)
            """,
            (
                assumption.assumption_id, mission_id, claim, source, importance.value,
                confidence, testability, verification_plan, assumption.status.value, now, now,
            ),
        )
        return assumption

    #: Resolutions a caller may assert, and what each one costs to assert.
    #:
    #: Every value here clears ACTIVE, and clearing ACTIVE unblocks irreversible work. So
    #: the question for each is not "is this a legitimate outcome" — they all are — but
    #: "can the actor the gate restrains reach it by saying so". VERIFIED and FALSIFIED are
    #: both claims about having checked, and both need evidence. SUPERSEDED needs to name
    #: the assumption that replaced it, which is the difference between a correction and a
    #: deletion. EXPIRED is not a claim at all, it is the passage of time, and is the
    #: kernel's to decide rather than a caller's to assert.
    CALLER_RESOLVABLE: frozenset[AssumptionStatus] = frozenset(
        {AssumptionStatus.VERIFIED, AssumptionStatus.FALSIFIED, AssumptionStatus.SUPERSEDED}
    )

    async def resolve_assumption(
        self,
        assumption_id: str,
        *,
        status: AssumptionStatus,
        evidence_refs: list[str] | None = None,
        superseded_by: str | None = None,
        now_ms: int | None = None,
    ) -> None:
        """Clear an assumption, at a price that depends on what is being claimed.

        §15's gate blocks irreversible work while a HIGH or CRITICAL assumption is ACTIVE.
        Before this, only VERIFIED cost anything: the same caller could record a CRITICAL
        assumption and mark it SUPERSEDED a moment later with nothing to show, and the gate
        opened. A check the restrained party can mark passed is not a check — it is
        P0-VERIFY-001's defect in a different ledger.
        """
        if status is AssumptionStatus.ACTIVE:
            raise ReasoningError("ASSUMPTION_CANNOT_BE_REOPENED", assumption_id)
        if status not in self.CALLER_RESOLVABLE:
            # EXPIRED specifically. A caller asserting that time has passed is a caller
            # deciding when its own deadline was.
            raise ReasoningError("ASSUMPTION_STATUS_NOT_CALLER_SETTABLE", status.value)
        if status in (AssumptionStatus.VERIFIED, AssumptionStatus.FALSIFIED) and not evidence_refs:
            # Verifying an assumption without evidence is asserting it again; falsifying one
            # without evidence is the same assertion wearing the opposite sign, and it is
            # the one that unblocks the work.
            raise ReasoningError("ASSUMPTION_RESOLUTION_REQUIRES_EVIDENCE", assumption_id)

        if status is AssumptionStatus.SUPERSEDED:
            if not superseded_by:
                raise ReasoningError("SUPERSEDED_REQUIRES_A_REPLACEMENT", assumption_id)
            original = await self.store.fetchone(
                "SELECT mission_id FROM assumption_ledger WHERE assumption_id = ?",
                (assumption_id,),
            )
            if original is None:
                raise ReasoningError("ASSUMPTION_NOT_FOUND", assumption_id)
            replacement = await self.store.fetchone(
                "SELECT mission_id, status FROM assumption_ledger WHERE assumption_id = ?",
                (superseded_by,),
            )
            if replacement is None:
                raise ReasoningError("REPLACEMENT_ASSUMPTION_NOT_FOUND", superseded_by)
            # Same mission, or the replacement is an assumption about other work and this is
            # a deletion with a citation attached.
            if str(replacement["mission_id"]) != str(original["mission_id"]):
                raise ReasoningError("REPLACEMENT_BELONGS_TO_ANOTHER_MISSION", superseded_by)
            if superseded_by == assumption_id:
                raise ReasoningError("ASSUMPTION_CANNOT_SUPERSEDE_ITSELF", assumption_id)

        now = int(time.time() * 1000) if now_ms is None else now_ms
        await self.store.execute(
            "UPDATE assumption_ledger SET status = ?, resolved_evidence_refs_json = ?, "
            "superseded_by = ?, updated_at_ms = ? WHERE assumption_id = ?",
            (
                status.value,
                Store.dumps(sorted(set(evidence_refs or []))),
                superseded_by,
                now,
                assumption_id,
            ),
        )

    async def expire_assumptions(self, *, older_than_ms: int, now_ms: int | None = None) -> int:
        """The one resolution a caller cannot assert, performed by the kernel on the clock.

        Kept deliberately separate from `resolve_assumption` so that expiry is something
        that happens to an assumption rather than something a caller does to one.
        """
        now = int(time.time() * 1000) if now_ms is None else now_ms
        # Through a connection rather than Store.execute, which returns None: a count taken
        # from that is always zero, which is a number that reads like a measurement and is
        # not one. The test that asserts a row was expired is what caught it.
        async with self.store.connection() as db:
            cursor = await db.execute(
                "UPDATE assumption_ledger SET status = ?, updated_at_ms = ? "
                "WHERE status = 'ACTIVE' AND created_at_ms <= ?",
                (AssumptionStatus.EXPIRED.value, now, now - older_than_ms),
            )
            await db.commit()
            return int(cursor.rowcount or 0)

    async def blocking_assumptions(self, mission_id: str) -> list[Assumption]:
        """§15 — what must be settled before irreversible work proceeds."""
        rows = await self.store.fetchall(
            "SELECT * FROM assumption_ledger WHERE mission_id = ? AND status = 'ACTIVE' "
            "AND importance IN ('HIGH','CRITICAL') ORDER BY created_at_ms",
            (mission_id,),
        )
        return [self._row_to_assumption(r) for r in rows]

    async def assert_safe_for_irreversible_work(self, mission_id: str) -> None:
        """§15's gate, as something a caller can actually invoke."""
        blocking = await self.blocking_assumptions(mission_id)
        if blocking:
            raise ReasoningError(
                "MISSION_HAS_UNVERIFIED_HIGH_IMPACT_ASSUMPTIONS",
                "; ".join(a.claim[:60] for a in blocking[:3]),
            )

    @staticmethod
    def _row_to_assumption(row: Any) -> Assumption:
        return Assumption(
            assumption_id=str(row["assumption_id"]), mission_id=str(row["mission_id"]),
            claim=str(row["claim"]), source=str(row["source"]),
            importance=Importance(str(row["importance"])), confidence=float(row["confidence"]),
            testability=str(row["testability"]), verification_plan=row["verification_plan"],
            status=AssumptionStatus(str(row["status"])),
            resolved_evidence_refs=json.loads(str(row["resolved_evidence_refs_json"])),
            superseded_by=_optional_column(row, "superseded_by"),
        )

    # ------------------------------------------------------- anti-sycophancy

    async def assess_premise(
        self,
        *,
        owner_premise: str,
        van_position: str,
        semantic_class: SemanticClass,
        evidence_refs: list[str] | None = None,
        corrected: bool = False,
        mission_id: str | None = None,
        now_ms: int | None = None,
    ) -> str:
        """§71 — record every time VAN agreed or disagreed with a factual premise.

        `agreed_without_evidence` is derived rather than supplied, so a caller
        cannot mark its own agreement as well-founded. Agreeing with a factual
        claim while citing nothing is the behaviour §17 measures, and deriving it
        here is what makes the rate real.
        """
        now = int(time.time() * 1000) if now_ms is None else now_ms
        refs = sorted(set(evidence_refs or []))
        agreed_without_evidence = (
            not corrected
            and not refs
            and semantic_class in (SemanticClass.FACT_VERIFIED, SemanticClass.FACT_UNVERIFIED)
        )
        premise_id = f"prem_{uuid.uuid4().hex}"
        await self.store.execute(
            """
            INSERT INTO premise_assessments(
              premise_id, mission_id, owner_premise, van_position, evidence_refs_json,
              semantic_class, corrected, agreed_without_evidence, created_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                premise_id, mission_id, owner_premise, van_position, Store.dumps(refs),
                semantic_class.value, 1 if corrected else 0,
                1 if agreed_without_evidence else 0, now,
            ),
        )
        return premise_id

    async def sycophancy_metrics(self, *, window_ms: int | None = None,
                                 now_ms: int | None = None) -> dict[str, Any]:
        """§17's metrics, computed from what actually happened.

        Returns `measured: False` with a zero denominator rather than a
        flattering 0% when nothing has been recorded — §55 forbids reporting a
        target as met when it has simply never been tested.
        """
        now = int(time.time() * 1000) if now_ms is None else now_ms
        since = now - (window_ms or 30 * 24 * 60 * 60 * 1000)
        rows = await self.store.fetchall(
            "SELECT corrected, agreed_without_evidence FROM premise_assessments "
            "WHERE created_at_ms >= ?",
            (since,),
        )
        total = len(rows)
        unsupported = sum(int(r["agreed_without_evidence"]) for r in rows)
        corrections = sum(int(r["corrected"]) for r in rows)
        return {
            "measured": total > 0,
            "premises_assessed": total,
            "unsupported_agreement_rate": (unsupported / total) if total else None,
            "correction_rate": (corrections / total) if total else None,
            "target_unsupported_agreement_rate": 0.01,
            "meets_target": (unsupported / total) < 0.01 if total else None,
        }


__all__ = [
    "CRITIC_KINDS",
    "REQUIRED_COUNTERFACTUALS",
    "Assumption",
    "AssumptionStatus",
    "ChallengeMode",
    "CriticFinding",
    "CriticalReasoningKernel",
    "Importance",
    "ReasoningAssessment",
    "ReasoningError",
    "required_mode",
]
