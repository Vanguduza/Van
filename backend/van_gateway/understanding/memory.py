"""Rev 1 §§65, 72, 76-78, 87 — the rest of the owner-understanding layer.

Five small stores that share one idea: VAN should get better at working with
this particular owner without getting more confident about the world. Each keeps
the evidence that justified it and each can be corrected, because §63.5 requires
inferred understanding to be reversible.

They are deliberately separate from `OwnerCognitiveModel`. Vocabulary is about
words, intent is about goals over time, strategic memory is about a project's
reasoning, fingerprints are about decisions, and the complement map is about
where VAN should compensate. Collapsing them into one "memory" table would make
every read a filter and every write a guess about which kind of thing this is.
"""

from __future__ import annotations

import json
import time
import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from van_gateway.storage.db import Store


# ------------------------------------------------------------- §76 vocabulary


class VocabularyEntry(BaseModel):
    """What the owner means by a word, operationally.

    `anti_examples` is the load-bearing field. §19's requirement is that VAN
    *learn meaning, not mimic vocabulary superficially*, and the difference
    between the two is entirely whether the system knows what the word excludes.
    "Full implementation" means little; "full implementation, and that does not
    mean interface-only" means something a system can check itself against.
    """

    term: str
    owner_meaning: str
    system_operationalization: str
    examples: list[str] = Field(default_factory=list)
    anti_examples: list[str] = Field(default_factory=list)
    project_id: str | None = None
    confidence: float = 0.0
    evidence_refs: list[str] = Field(default_factory=list)

    @property
    def is_operational(self) -> bool:
        """Whether this entry can actually discriminate, or is just a gloss."""
        return bool(self.system_operationalization) and bool(self.anti_examples)


class SharedVocabularyRegistry:
    def __init__(self, store: Store) -> None:
        self.store = store

    async def define(
        self, entry: VocabularyEntry, *, now_ms: int | None = None
    ) -> VocabularyEntry:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        await self.store.execute(
            """
            INSERT INTO shared_vocabulary(
              term, project_id, owner_meaning, system_operationalization, examples_json,
              anti_examples_json, confidence, evidence_refs_json, created_at_ms, updated_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(term, project_id) DO UPDATE SET
              owner_meaning=excluded.owner_meaning,
              system_operationalization=excluded.system_operationalization,
              examples_json=excluded.examples_json,
              anti_examples_json=excluded.anti_examples_json,
              confidence=excluded.confidence,
              evidence_refs_json=excluded.evidence_refs_json,
              updated_at_ms=excluded.updated_at_ms
            """,
            (
                entry.term.strip().lower(), entry.project_id or "", entry.owner_meaning,
                entry.system_operationalization, Store.dumps(entry.examples),
                Store.dumps(entry.anti_examples), entry.confidence,
                Store.dumps(entry.evidence_refs), now, now,
            ),
        )
        return entry

    async def resolve(self, term: str, *, project_id: str | None = None) -> VocabularyEntry | None:
        """Project-scoped meaning wins over the global one when both exist."""
        for scope in ([project_id] if project_id else []) + [""]:
            row = await self.store.fetchone(
                "SELECT * FROM shared_vocabulary WHERE term = ? AND project_id = ?",
                (term.strip().lower(), scope or ""),
            )
            if row is not None:
                return VocabularyEntry(
                    term=str(row["term"]), owner_meaning=str(row["owner_meaning"]),
                    system_operationalization=str(row["system_operationalization"]),
                    examples=json.loads(str(row["examples_json"])),
                    anti_examples=json.loads(str(row["anti_examples_json"])),
                    project_id=row["project_id"] or None, confidence=float(row["confidence"]),
                    evidence_refs=json.loads(str(row["evidence_refs_json"])),
                )
        return None

    async def all_terms(self) -> list[VocabularyEntry]:
        rows = await self.store.fetchall("SELECT * FROM shared_vocabulary ORDER BY term")
        return [
            VocabularyEntry(
                term=str(r["term"]), owner_meaning=str(r["owner_meaning"]),
                system_operationalization=str(r["system_operationalization"]),
                examples=json.loads(str(r["examples_json"])),
                anti_examples=json.loads(str(r["anti_examples_json"])),
                project_id=r["project_id"] or None, confidence=float(r["confidence"]),
                evidence_refs=json.loads(str(r["evidence_refs_json"])),
            )
            for r in rows
        ]


# ------------------------------------------------------------ §77 intent graph


class IntentEdgeType(str, Enum):
    SUPPORTS = "supports"
    CONFLICTS = "conflicts"
    SUPERSEDES = "supersedes"
    DEPENDS_ON = "depends_on"
    REFINES = "refines"


class IntentStatus(str, Enum):
    ACTIVE = "ACTIVE"
    ACHIEVED = "ACHIEVED"
    STALE = "STALE"
    ABANDONED = "ABANDONED"
    SUPERSEDED = "SUPERSEDED"


class IntentHorizon(str, Enum):
    """How long an intent is expected to matter, which is not how long ago it was said.

    P2-MEM-003 — every mission goal used to become a standing objective, so "what is on my
    calendar?" sat in the owner's long-term goal graph until the ninety-day stale sweep.
    §77's whole value is surfacing a newer instruction that contradicts an older standing
    goal; filling the graph with one-off requests gives it transient commands to contradict
    genuine goals with, which is worse than having no graph.

    Everything starts EPHEMERAL. Nothing is promoted by the mere fact of having been said.
    """

    #: Asked for once. Real, recorded, and not a statement about what the owner is doing.
    EPHEMERAL = "EPHEMERAL"
    #: Asked for repeatedly, or scoped to a project the owner keeps returning to.
    PROJECT = "PROJECT"
    #: A long-lived objective: the owner said so, or asked enough times that it is one.
    STANDING = "STANDING"


class IntentNode(BaseModel):
    intent_id: str
    owner_goal: str
    first_observed_ms: int
    latest_observed_ms: int
    projects: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    status: IntentStatus = IntentStatus.ACTIVE
    priority: int = 50
    horizon: IntentHorizon = IntentHorizon.EPHEMERAL
    observation_count: int = 1
    #: What promoted this beyond EPHEMERAL, so a standing intent can be argued with rather
    #: than only observed. Null while EPHEMERAL.
    promoted_reason: str | None = None
    promoted_at_ms: int | None = None


class IntentContinuityGraph:
    """§77 — long-lived goals and how they relate.

    The value is in `conflicts` and `supersedes`: a newer instruction that
    contradicts an older standing goal should be *visible* rather than silently
    winning because it arrived more recently.
    """

    #: DECISION (recorded): an intent unmentioned for 90 days is STALE, not
    #: abandoned. Stale means "ask before assuming this still matters"; only the
    #: owner abandons a goal.
    STALE_AFTER_MS = 90 * 24 * 60 * 60 * 1000

    #: DECISION (recorded): how many separate observations make a request an objective.
    #:
    #: P2-MEM-003 — three, chosen because two is a coincidence and a number much higher
    #: would mean VAN never notices what the owner keeps coming back to. It is deliberately
    #: not time-weighted: asking three times in a morning and three times over a month are
    #: both evidence, and guessing which one means more would be inference dressed as a
    #: rule.
    STANDING_AFTER_OBSERVATIONS = 3

    def __init__(self, store: Store) -> None:
        self.store = store

    async def observe(
        self,
        *,
        owner_goal: str,
        project_id: str | None = None,
        constraints: list[str] | None = None,
        owner_declared_standing: bool = False,
        now_ms: int | None = None,
    ) -> IntentNode:
        """Record that the owner asked for this, and promote it only on evidence.

        P2-MEM-003 — an observation is not a promotion. A new goal is EPHEMERAL, whatever
        it says: VAN cannot tell an objective from an errand by reading one sentence, and
        deciding it can is how a calendar lookup becomes a long-term commitment.

        Two things promote. `owner_declared_standing` is the owner saying so, which needs
        no corroboration and is not VAN's inference. Otherwise it takes
        `STANDING_AFTER_OBSERVATIONS` separate observations, and a goal that arrives with a
        project reaches PROJECT on the second. Each promotion records what caused it.
        """
        now = int(time.time() * 1000) if now_ms is None else now_ms
        normalized = owner_goal.strip()
        row = await self.store.fetchone(
            "SELECT * FROM intent_nodes WHERE owner_goal = ?", (normalized,)
        )
        if row is not None:
            projects = sorted(set(json.loads(str(row["projects_json"]))) | (
                {project_id} if project_id else set()
            ))
            seen = int(row["observation_count"]) + 1
            horizon, reason = self._horizon_for(
                current=IntentHorizon(str(row["horizon"])),
                observations=seen,
                projects=projects,
                owner_declared_standing=owner_declared_standing,
            )
            promoted = horizon is not IntentHorizon(str(row["horizon"]))
            await self.store.execute(
                "UPDATE intent_nodes SET latest_observed_ms = ?, projects_json = ?, "
                "observation_count = ?, horizon = ?, "
                "promoted_reason = COALESCE(?, promoted_reason), "
                "promoted_at_ms = COALESCE(?, promoted_at_ms), "
                "status = CASE WHEN status = 'STALE' THEN 'ACTIVE' ELSE status END "
                "WHERE intent_id = ?",
                (
                    now, Store.dumps(projects), seen, horizon.value,
                    reason if promoted else None, now if promoted else None,
                    row["intent_id"],
                ),
            )
            return await self.get(str(row["intent_id"]))  # type: ignore[return-value]

        # A goal seen for the first time is EPHEMERAL unless the owner said otherwise.
        # Not "unless it looks important": VAN cannot tell an objective from an errand by
        # reading one sentence, and a rule that tried would promote whichever phrasing it
        # happened to like.
        horizon, reason = self._horizon_for(
            current=IntentHorizon.EPHEMERAL,
            observations=1,
            projects=[project_id] if project_id else [],
            owner_declared_standing=owner_declared_standing,
        )
        node = IntentNode(
            intent_id=f"intent_{uuid.uuid4().hex}", owner_goal=normalized,
            first_observed_ms=now, latest_observed_ms=now,
            projects=[project_id] if project_id else [],
            constraints=list(constraints or []),
            horizon=horizon,
            observation_count=1,
            promoted_reason=reason if horizon is not IntentHorizon.EPHEMERAL else None,
            promoted_at_ms=now if horizon is not IntentHorizon.EPHEMERAL else None,
        )
        await self.store.execute(
            "INSERT INTO intent_nodes(intent_id, owner_goal, first_observed_ms, "
            "latest_observed_ms, projects_json, constraints_json, status, priority, "
            "horizon, observation_count, promoted_reason, promoted_at_ms) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                node.intent_id, node.owner_goal, now, now, Store.dumps(node.projects),
                Store.dumps(node.constraints), node.status.value, node.priority,
                node.horizon.value, node.observation_count, node.promoted_reason,
                node.promoted_at_ms,
            ),
        )
        return node

    def _horizon_for(
        self,
        *,
        current: IntentHorizon,
        observations: int,
        projects: list[str],
        owner_declared_standing: bool,
    ) -> tuple[IntentHorizon, str | None]:
        """The horizon and what earned it. Never demotes.

        A goal that was standing does not stop being one because the next mention was
        casual; only the owner retires an objective, which is the same rule STALE follows.
        """
        if owner_declared_standing:
            return IntentHorizon.STANDING, "the owner stated this is a standing goal"
        if current is IntentHorizon.STANDING:
            return current, None
        if observations >= self.STANDING_AFTER_OBSERVATIONS:
            return (
                IntentHorizon.STANDING,
                f"asked for {observations} times, which is repetition rather than a "
                f"one-off request",
            )
        if projects and observations >= 2 and current is IntentHorizon.EPHEMERAL:
            return (
                IntentHorizon.PROJECT,
                f"asked for {observations} times within {', '.join(sorted(projects))}",
            )
        return current, None

    async def relate(
        self,
        *,
        from_intent_id: str,
        to_intent_id: str,
        edge_type: IntentEdgeType,
        evidence_ref: str | None = None,
        now_ms: int | None = None,
    ) -> str:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        edge_id = f"iedge_{uuid.uuid4().hex}"
        await self.store.execute(
            "INSERT INTO intent_edges(edge_id, from_intent_id, to_intent_id, edge_type, "
            "evidence_ref, created_at_ms) VALUES (?, ?, ?, ?, ?, ?)",
            (edge_id, from_intent_id, to_intent_id, edge_type.value, evidence_ref, now),
        )
        if edge_type is IntentEdgeType.SUPERSEDES:
            await self.store.execute(
                "UPDATE intent_nodes SET status = 'SUPERSEDED' WHERE intent_id = ?",
                (to_intent_id,),
            )
        return edge_id

    async def get(self, intent_id: str) -> IntentNode | None:
        row = await self.store.fetchone(
            "SELECT * FROM intent_nodes WHERE intent_id = ?", (intent_id,)
        )
        if row is None:
            return None
        return IntentNode(
            intent_id=str(row["intent_id"]), owner_goal=str(row["owner_goal"]),
            first_observed_ms=int(row["first_observed_ms"]),
            latest_observed_ms=int(row["latest_observed_ms"]),
            projects=json.loads(str(row["projects_json"])),
            constraints=json.loads(str(row["constraints_json"])),
            status=IntentStatus(str(row["status"])), priority=int(row["priority"]),
            horizon=IntentHorizon(str(row["horizon"])),
            observation_count=int(row["observation_count"]),
            promoted_reason=row["promoted_reason"],
            promoted_at_ms=row["promoted_at_ms"],
        )

    async def conflicts_for(self, intent_id: str) -> list[IntentNode]:
        """What this goal is in tension with — the thing worth surfacing."""
        rows = await self.store.fetchall(
            "SELECT to_intent_id AS other FROM intent_edges "
            "WHERE from_intent_id = ? AND edge_type = 'conflicts' "
            "UNION SELECT from_intent_id AS other FROM intent_edges "
            "WHERE to_intent_id = ? AND edge_type = 'conflicts'",
            (intent_id, intent_id),
        )
        out = []
        for row in rows:
            node = await self.get(str(row["other"]))
            if node is not None:
                out.append(node)
        return out

    async def link_mission(self, intent_id: str, mission_id: str, *, now_ms: int | None = None):
        now = int(time.time() * 1000) if now_ms is None else now_ms
        await self.store.execute(
            "INSERT INTO intent_missions(intent_id, mission_id, linked_at_ms) VALUES (?, ?, ?) "
            "ON CONFLICT(intent_id, mission_id) DO NOTHING",
            (intent_id, mission_id, now),
        )

    async def mark_stale(self, *, now_ms: int | None = None) -> int:
        """§20 — surface stale objectives rather than acting on them silently."""
        now = int(time.time() * 1000) if now_ms is None else now_ms
        async with self.store.connection() as db:
            cur = await db.execute(
                "UPDATE intent_nodes SET status = 'STALE' "
                "WHERE status = 'ACTIVE' AND latest_observed_ms < ?",
                (now - self.STALE_AFTER_MS,),
            )
            await db.commit()
            return cur.rowcount


# -------------------------------------------------------- §78 strategic memory


class StrategicEntryType(str, Enum):
    WHY_EXISTS = "WHY_EXISTS"
    INTENDED_END_STATE = "INTENDED_END_STATE"
    PRINCIPLE = "PRINCIPLE"
    HISTORICAL_PIVOT = "HISTORICAL_PIVOT"
    REJECTED_STRATEGY = "REJECTED_STRATEGY"
    CURRENT_BOTTLENECK = "CURRENT_BOTTLENECK"
    OPEN_QUESTION = "OPEN_QUESTION"


class StrategicMemory:
    """§78 — why a project exists and what was already tried and rejected.

    §21 is explicit that this does not replace Project Truth. Project Truth is
    what the repository *is*; strategic memory is why it became that. Keeping
    them apart stops a rationale being cited as a fact about the code.
    """

    def __init__(self, store: Store) -> None:
        self.store = store

    async def record(
        self,
        *,
        project_id: str,
        entry_type: StrategicEntryType,
        statement: str,
        rationale: str | None = None,
        evidence_refs: list[str] | None = None,
        now_ms: int | None = None,
    ) -> str:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        entry_id = f"strat_{uuid.uuid4().hex}"
        await self.store.execute(
            "INSERT INTO strategic_memory(entry_id, project_id, entry_type, statement, "
            "rationale, evidence_refs_json, superseded_by, created_at_ms, updated_at_ms) "
            "VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?)",
            (
                entry_id, project_id, entry_type.value, statement, rationale,
                Store.dumps(sorted(set(evidence_refs or []))), now, now,
            ),
        )
        return entry_id

    async def for_project(
        self, project_id: str, *, entry_type: StrategicEntryType | None = None
    ) -> list[dict[str, Any]]:
        sql = ("SELECT * FROM strategic_memory WHERE project_id = ? AND superseded_by IS NULL")
        params: list[Any] = [project_id]
        if entry_type is not None:
            sql += " AND entry_type = ?"
            params.append(entry_type.value)
        rows = await self.store.fetchall(sql + " ORDER BY created_at_ms", tuple(params))
        return [dict(r) for r in rows]

    async def already_rejected(self, project_id: str, statement: str) -> bool:
        """The question worth asking before proposing something: did we try this?"""
        rows = await self.for_project(project_id, entry_type=StrategicEntryType.REJECTED_STRATEGY)
        needle = statement.strip().lower()
        return any(needle in str(r["statement"]).strip().lower() for r in rows)


# ------------------------------------------------------- §65 decision fingerprints


class DecisionFingerprints:
    """§65 — how the owner decides, kept falsifiable.

    §12's warning is the important part: *never use them as unquestionable
    rules*, and *outcomes must be able to falsify earlier inferred patterns*. So
    `record_outcome` exists and is expected to be used; a fingerprint store that
    only ever accumulates choices would become a machine for justifying whatever
    the owner did last.
    """

    def __init__(self, store: Store) -> None:
        self.store = store

    async def record(
        self,
        *,
        owner_choice: str,
        mission_id: str | None = None,
        context: dict[str, Any] | None = None,
        options_considered: list[str] | None = None,
        owner_stated_reason: str | None = None,
        inferred_reason: str | None = None,
        tradeoffs: list[str] | None = None,
        evidence_used: list[str] | None = None,
        rejected_alternatives: list[str] | None = None,
        now_ms: int | None = None,
    ) -> str:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        decision_id = f"dfp_{uuid.uuid4().hex}"
        await self.store.execute(
            """
            INSERT INTO decision_fingerprints(
              decision_id, mission_id, context_json, options_considered_json, owner_choice,
              owner_stated_reason, inferred_reason, tradeoffs_json, evidence_used_json,
              rejected_alternatives_json, outcome, reassessment, created_at_ms, updated_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)
            """,
            (
                decision_id, mission_id, Store.dumps(context or {}),
                Store.dumps(options_considered or []), owner_choice, owner_stated_reason,
                inferred_reason, Store.dumps(tradeoffs or []),
                Store.dumps(evidence_used or []), Store.dumps(rejected_alternatives or []),
                now, now,
            ),
        )
        return decision_id

    async def record_outcome(
        self, decision_id: str, *, outcome: str, reassessment: str | None = None,
        now_ms: int | None = None,
    ) -> None:
        """§12 — the outcome is what lets an inferred reason be wrong."""
        now = int(time.time() * 1000) if now_ms is None else now_ms
        await self.store.execute(
            "UPDATE decision_fingerprints SET outcome = ?, reassessment = ?, updated_at_ms = ? "
            "WHERE decision_id = ?",
            (outcome, reassessment, now, decision_id),
        )

    async def falsified(self) -> list[dict[str, Any]]:
        """Fingerprints whose outcome contradicts the reason inferred at the time.

        These are the interesting ones: each is a place where VAN's model of how
        the owner decides was measurably wrong.
        """
        rows = await self.store.fetchall(
            "SELECT * FROM decision_fingerprints WHERE outcome IS NOT NULL "
            "AND inferred_reason IS NOT NULL AND reassessment IS NOT NULL"
        )
        return [dict(r) for r in rows]


# ----------------------------------------------------- §72 complement map, §87 growth


class CognitiveComplementMap:
    """§72 — where VAN compensates rather than imitates.

    §18 forbids psychological diagnoses, so every entry must cite task
    observations. `owner_vulnerability_candidate` is deliberately named as a
    *candidate*: it is a hypothesis about a working pattern, not a finding about
    a person.
    """

    def __init__(self, store: Store) -> None:
        self.store = store

    async def upsert(
        self,
        *,
        domain: str,
        owner_strength: str | None = None,
        owner_vulnerability_candidate: str | None = None,
        van_strength: str | None = None,
        preferred_collaboration_pattern: str | None = None,
        confidence: float = 0.0,
        evidence_refs: list[str] | None = None,
        now_ms: int | None = None,
    ) -> str:
        if owner_vulnerability_candidate and not evidence_refs:
            # §18 — no diagnosis without task observations behind it.
            raise ValueError("complement_vulnerability_requires_evidence")
        now = int(time.time() * 1000) if now_ms is None else now_ms
        entry_id = f"ccm_{uuid.uuid4().hex}"
        await self.store.execute(
            """
            INSERT INTO cognitive_complement_map(
              entry_id, domain, owner_strength, owner_vulnerability_candidate, van_strength,
              preferred_collaboration_pattern, confidence, evidence_refs_json,
              created_at_ms, updated_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(domain) DO UPDATE SET
              owner_strength=excluded.owner_strength,
              owner_vulnerability_candidate=excluded.owner_vulnerability_candidate,
              van_strength=excluded.van_strength,
              preferred_collaboration_pattern=excluded.preferred_collaboration_pattern,
              confidence=excluded.confidence,
              evidence_refs_json=excluded.evidence_refs_json,
              updated_at_ms=excluded.updated_at_ms
            """,
            (
                entry_id, domain, owner_strength, owner_vulnerability_candidate, van_strength,
                preferred_collaboration_pattern, confidence,
                Store.dumps(sorted(set(evidence_refs or []))), now, now,
            ),
        )
        return entry_id

    async def all(self) -> list[dict[str, Any]]:
        rows = await self.store.fetchall(
            "SELECT * FROM cognitive_complement_map ORDER BY domain"
        )
        return [dict(r) for r in rows]


class SymbioticGrowthLedger:
    """§87 — "How Van has adapted", and the owner's ability to undo it.

    §26 requires the owner be able to correct or reject a material cognitive-model
    change, so every entry carries whether it is reversible and whether the owner
    has confirmed it. An adaptation that took effect without confirmation and
    cannot be reverted would be VAN changing itself behind the owner's back.
    """

    def __init__(self, store: Store) -> None:
        self.store = store

    async def record(
        self,
        *,
        observed_pattern: str,
        previous_behavior: str,
        new_behavior: str,
        reason: str,
        evidence_refs: list[str] | None = None,
        owner_confirmation_required: bool = True,
        reversible: bool = True,
        now_ms: int | None = None,
    ) -> str:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        change_id = f"grow_{uuid.uuid4().hex}"
        await self.store.execute(
            """
            INSERT INTO symbiotic_growth(
              change_id, observed_pattern, previous_behavior, new_behavior, reason,
              evidence_refs_json, owner_confirmation_required, owner_confirmed_at_ms,
              reverted_at_ms, reversible, effective_from_ms, created_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?)
            """,
            (
                change_id, observed_pattern, previous_behavior, new_behavior, reason,
                Store.dumps(sorted(set(evidence_refs or []))),
                1 if owner_confirmation_required else 0, 1 if reversible else 0,
                None if owner_confirmation_required else now, now,
            ),
        )
        return change_id

    async def confirm(self, change_id: str, *, now_ms: int | None = None) -> None:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        await self.store.execute(
            "UPDATE symbiotic_growth SET owner_confirmed_at_ms = ?, effective_from_ms = ? "
            "WHERE change_id = ? AND reverted_at_ms IS NULL",
            (now, now, change_id),
        )

    async def revert(self, change_id: str, *, now_ms: int | None = None) -> bool:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        async with self.store.connection() as db:
            cur = await db.execute(
                "UPDATE symbiotic_growth SET reverted_at_ms = ?, effective_from_ms = NULL "
                "WHERE change_id = ? AND reversible = 1 AND reverted_at_ms IS NULL",
                (now, change_id),
            )
            await db.commit()
            return cur.rowcount == 1

    async def effective(self) -> list[dict[str, Any]]:
        """Adaptations actually in force — confirmed where confirmation was needed."""
        rows = await self.store.fetchall(
            "SELECT * FROM symbiotic_growth WHERE reverted_at_ms IS NULL "
            "AND effective_from_ms IS NOT NULL ORDER BY created_at_ms DESC"
        )
        return [dict(r) for r in rows]

    async def awaiting_owner(self) -> list[dict[str, Any]]:
        rows = await self.store.fetchall(
            "SELECT * FROM symbiotic_growth WHERE owner_confirmation_required = 1 "
            "AND owner_confirmed_at_ms IS NULL AND reverted_at_ms IS NULL "
            "ORDER BY created_at_ms DESC"
        )
        return [dict(r) for r in rows]


__all__ = [
    "CognitiveComplementMap",
    "DecisionFingerprints",
    "IntentContinuityGraph",
    "IntentEdgeType",
    "IntentNode",
    "IntentStatus",
    "SharedVocabularyRegistry",
    "StrategicEntryType",
    "StrategicMemory",
    "SymbioticGrowthLedger",
    "VocabularyEntry",
]
