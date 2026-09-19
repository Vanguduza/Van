"""Rev 1 §§64, 74, 87 — the Owner Cognitive Model and its admission policy.

§64 is careful about what this is: *model collaboration, not psychology*. Every
field describes how the owner works with VAN — how they want to be interrupted,
what evidence they find persuasive, which tradeoffs they habitually take. None of
it describes what kind of person they are, and §11 forbids psychological
diagnoses outright.

The admission policy is the part that decides whether this becomes useful or
becomes a machine for confirming VAN's own guesses. §74 requires that an
inferred trait needs *multiple independent evidence points or owner
confirmation*, and this module makes "independent" mean something checkable
rather than "we saw it twice in one conversation".

DECISION (recorded, made without owner input):

* **Two independent episodes promote OBSERVED to CANDIDATE; three promote
  CANDIDATE to CONFIRMED — and only the owner promotes to CONFIRMED for anything
  that changes VAN's autonomy.** Evidence alone can make VAN *believe* something
  about how the owner works; only the owner can make it *act* on that belief
  where the stakes are their authority.
* **Independence is by episode, not by observation.** Three mentions inside one
  mission are one data point. Without that, a single emphatic conversation would
  mint a confirmed trait.
* **A correction is stronger than any amount of accumulated evidence.** One
  owner rejection moves an assertion to REJECTED and no confidence total
  overrides it, because the alternative is VAN arguing with the owner about the
  owner.
"""

from __future__ import annotations

import json
import time
import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from van_gateway.storage.db import Store


class AssertionState(str, Enum):
    """§64's ladder."""

    OBSERVED = "OBSERVED"
    CANDIDATE = "CANDIDATE"
    #: P1-SYM-001 — VAN's own conclusion from repeated evidence. Distinct from CONFIRMED,
    #: which only the owner produces. The two were the same state, and the calibration
    #: engine read it and told the owner their preference was "owner-confirmed" when they
    #: had never been asked.
    EVIDENCED = "EVIDENCED"
    CONFIRMED = "CONFIRMED"
    CONTESTED = "CONTESTED"
    SUPERSEDED = "SUPERSEDED"
    REJECTED = "REJECTED"

    @property
    def is_actionable(self) -> bool:
        """Whether VAN may act on this rather than merely hold it.

        P1-SYM-001 — EVIDENCED is actionable because refusing to act on a well-evidenced
        preference would make VAN useless until the owner had answered a questionnaire.
        What it is not is *confirmed*, and nothing may describe it that way. The two
        states used to be one, which is how the calibration engine came to tell the owner
        that a preference VAN had inferred was their own stated choice.
        """
        return self in (AssertionState.CONFIRMED, AssertionState.EVIDENCED)

    @property
    def is_owner_stated(self) -> bool:
        """Only the owner's own confirmation. The distinction the finding is about."""
        return self is AssertionState.CONFIRMED


class OwnerModelField(str, Enum):
    """§11's field list. Collaboration, never personality."""

    VALUE = "values"
    STRATEGIC_PRIORITY = "strategic_priorities"
    DECISION_PRINCIPLE = "decision_principles"
    PREFERRED_TRADEOFF = "preferred_tradeoffs"
    COMMUNICATION_PREFERENCE = "communication_preferences"
    REASONING_PREFERENCE = "reasoning_preferences"
    RECURRING_CONSTRAINT = "recurring_constraints"
    ACCEPTED_RISK_PATTERN = "accepted_risk_patterns"
    BLIND_SPOT_CANDIDATE = "blind_spot_candidates"
    DELEGATION_PREFERENCE = "delegation_preferences"
    INTERRUPTION_PREFERENCE = "interruption_preferences"
    EVIDENCE_PREFERENCE = "evidence_preferences"


#: §74 — fields whose CONFIRMED state would change what VAN does on its own.
#: These never reach CONFIRMED from evidence alone, however much accumulates.
AUTONOMY_BEARING_FIELDS = frozenset({
    OwnerModelField.DELEGATION_PREFERENCE,
    OwnerModelField.ACCEPTED_RISK_PATTERN,
    OwnerModelField.INTERRUPTION_PREFERENCE,
})

EPISODES_FOR_CANDIDATE = 2
#: How many distinct, resolvable episodes make VAN's own conclusion. Not the owner's.
EPISODES_FOR_EVIDENCED = 3
#: Retained under the old name because it is exported; it is the same threshold, and what
#: changed is what the threshold produces (P1-SYM-001).
EPISODES_FOR_CONFIRMED = EPISODES_FOR_EVIDENCED


class OwnerAssertion(BaseModel):
    assertion_id: str
    owner_principal_id: str
    field: OwnerModelField
    value: str
    state: AssertionState = AssertionState.OBSERVED
    confidence: float = 0.0
    evidence_refs: list[str] = Field(default_factory=list)
    supporting_episode_refs: list[str] = Field(default_factory=list)
    project_id: str | None = None
    temporary: bool = False
    superseded_by: str | None = None
    owner_confirmed_at_ms: int | None = None
    last_revalidated_at_ms: int | None = None
    created_at_ms: int = 0
    updated_at_ms: int = 0

    @property
    def independent_episodes(self) -> int:
        """§74 — independence is by episode. Three mentions in one mission is one."""
        return len(set(self.supporting_episode_refs))

    @property
    def is_autonomy_bearing(self) -> bool:
        return self.field in AUTONOMY_BEARING_FIELDS

    @property
    def may_act_on(self) -> bool:
        return self.state.is_actionable and self.superseded_by is None


class OwnerModelError(ValueError):
    def __init__(self, code: str, detail: str | None = None) -> None:
        super().__init__(code if detail is None else f"{code}: {detail}")
        self.code = code
        self.detail = detail


#: What an episode reference may name, and the table that has to contain it.
#:
#: P1-SYM-001 — `episode_ref` was a free string, and three distinct strings promoted an
#: assertion. Nothing ever checked that an episode existed, so three typos were evidence.
EPISODE_SOURCES: dict[str, tuple[str, str]] = {
    "mission": ("missions", "mission_id"),
    "command": ("audit", "command_id"),
}


class OwnerCognitiveModel:
    """Holds assertions about how the owner works, and the rules for trusting them."""

    def __init__(self, store: Store, *, learning: Any | None = None) -> None:
        self.store = store
        # P1-LEARN-001 — an owner correction is the strongest learning signal there is and
        # nothing recorded it. Optional so the model stays constructible on its own.
        self.learning = learning

    async def _require_episode(self, episode_ref: str) -> str:
        """Refuse an episode reference that does not name something that happened.

        The ladder counts distinct references, so an unresolvable one is not merely
        untidy: it is a vote. Requiring the prefix as well as the row means a caller
        cannot satisfy the check by passing a bare id that happens to collide.
        """
        ref = (episode_ref or "").strip()
        kind, separator, identifier = ref.partition(":")
        if not separator or kind not in EPISODE_SOURCES or not identifier.strip():
            raise OwnerModelError(
                "OWNER_MODEL_EPISODE_UNRESOLVABLE",
                f"{ref!r} does not name an episode; expected one of "
                f"{sorted(f'{k}:<id>' for k in EPISODE_SOURCES)}",
            )
        table, column = EPISODE_SOURCES[kind]
        row = await self.store.fetchone(
            f"SELECT 1 AS present FROM {table} WHERE {column} = ? LIMIT 1",  # noqa: S608
            (identifier.strip(),),
        )
        if row is None:
            raise OwnerModelError(
                "OWNER_MODEL_EPISODE_UNKNOWN",
                f"no {kind} {identifier.strip()!r} exists; an assertion cannot be "
                "evidenced by something that did not happen",
            )
        return ref

    async def observe(
        self,
        *,
        owner_principal_id: str,
        field: OwnerModelField,
        value: str,
        episode_ref: str,
        evidence_refs: list[str] | None = None,
        project_id: str | None = None,
        now_ms: int | None = None,
    ) -> OwnerAssertion:
        """Record one observation and let the ladder decide what it becomes.

        Observing the same value again from a *new* episode is what advances it.
        Re-observing from an episode already counted changes nothing, which is
        what stops one emphatic conversation minting a confirmed trait.
        """
        now = int(time.time() * 1000) if now_ms is None else now_ms
        episode_ref = await self._require_episode(episode_ref)
        existing = await self._find(owner_principal_id, field, value, project_id)

        if existing is None:
            assertion = OwnerAssertion(
                assertion_id=f"oca_{uuid.uuid4().hex}",
                owner_principal_id=owner_principal_id, field=field, value=value,
                state=AssertionState.OBSERVED,
                evidence_refs=sorted(set(evidence_refs or [])),
                supporting_episode_refs=[episode_ref], project_id=project_id,
                confidence=0.2, created_at_ms=now, updated_at_ms=now,
            )
            await self._insert(assertion)
            return assertion

        if existing.state is AssertionState.REJECTED:
            # §74 — a correction outranks accumulation. Re-observing something
            # the owner rejected does not revive it; only the owner does.
            return existing

        episodes = sorted(set(existing.supporting_episode_refs) | {episode_ref})
        evidence = sorted(set(existing.evidence_refs) | set(evidence_refs or []))
        state = existing.state
        if existing.state in (AssertionState.OBSERVED, AssertionState.CANDIDATE):
            state = self._ladder(field, len(episodes), existing.state)
        confidence = min(0.95, 0.2 + 0.25 * (len(episodes) - 1))

        updated = existing.model_copy(update={
            "supporting_episode_refs": episodes, "evidence_refs": evidence,
            "state": state, "confidence": confidence, "updated_at_ms": now,
        })
        await self._update(updated)
        return updated

    @staticmethod
    def _ladder(
        field: OwnerModelField, episodes: int, current: AssertionState
    ) -> AssertionState:
        """Evidence promotes to CANDIDATE, then to EVIDENCED. Never to CONFIRMED.

        P1-SYM-001 — three distinct episode references used to produce CONFIRMED for any
        non-autonomy field, and the calibration engine then described the result to the
        owner as "owner-confirmed". Nobody had asked them. The top of the evidence ladder
        is now EVIDENCED, which means exactly what it says, and CONFIRMED is reachable
        only through `confirm()`.
        """
        if episodes >= EPISODES_FOR_EVIDENCED and field not in AUTONOMY_BEARING_FIELDS:
            return AssertionState.EVIDENCED
        if episodes >= EPISODES_FOR_CANDIDATE:
            return AssertionState.CANDIDATE
        return current

    # ------------------------------------------------------ owner control

    async def confirm(self, assertion_id: str, *, now_ms: int | None = None) -> OwnerAssertion:
        """§33 — the owner's confirm. The only route to CONFIRMED for autonomy
        fields, and available for every other field too."""
        now = int(time.time() * 1000) if now_ms is None else now_ms
        assertion = await self.get(assertion_id)
        if assertion is None:
            raise OwnerModelError("OWNER_ASSERTION_UNKNOWN", assertion_id)
        updated = assertion.model_copy(update={
            "state": AssertionState.CONFIRMED, "confidence": 1.0,
            "owner_confirmed_at_ms": now, "last_revalidated_at_ms": now, "updated_at_ms": now,
        })
        await self._update(updated)
        return updated

    async def correct(
        self, assertion_id: str, *, new_value: str, now_ms: int | None = None
    ) -> OwnerAssertion:
        """A correction supersedes rather than edits, so the history survives."""
        now = int(time.time() * 1000) if now_ms is None else now_ms
        assertion = await self.get(assertion_id)
        if assertion is None:
            raise OwnerModelError("OWNER_ASSERTION_UNKNOWN", assertion_id)
        replacement = OwnerAssertion(
            assertion_id=f"oca_{uuid.uuid4().hex}",
            owner_principal_id=assertion.owner_principal_id, field=assertion.field,
            value=new_value, state=AssertionState.CONFIRMED, confidence=1.0,
            evidence_refs=list(assertion.evidence_refs),
            supporting_episode_refs=list(assertion.supporting_episode_refs),
            project_id=assertion.project_id, owner_confirmed_at_ms=now,
            last_revalidated_at_ms=now, created_at_ms=now, updated_at_ms=now,
        )
        await self._insert(replacement)
        await self._update(assertion.model_copy(update={
            "state": AssertionState.SUPERSEDED,
            "superseded_by": replacement.assertion_id, "updated_at_ms": now,
        }))
        if self.learning is not None:
            # The one adaptation that is honest to record: the owner said something
            # different, VAN superseded what it believed, and that changes what VAN does.
            await self.learning.record_owner_correction(
                assertion_id=replacement.assertion_id,
                field=assertion.field.value,
                previous_value=assertion.value,
                new_value=new_value,
                now_ms=now,
            )
        return replacement

    async def reject(self, assertion_id: str, *, now_ms: int | None = None) -> OwnerAssertion:
        """One rejection ends it. No confidence total overrides the owner."""
        now = int(time.time() * 1000) if now_ms is None else now_ms
        assertion = await self.get(assertion_id)
        if assertion is None:
            raise OwnerModelError("OWNER_ASSERTION_UNKNOWN", assertion_id)
        updated = assertion.model_copy(update={
            "state": AssertionState.REJECTED, "confidence": 0.0, "updated_at_ms": now,
        })
        await self._update(updated)
        return updated

    async def contest(self, assertion_id: str, *, now_ms: int | None = None) -> OwnerAssertion:
        """Evidence disagrees with itself; the owner should look."""
        now = int(time.time() * 1000) if now_ms is None else now_ms
        assertion = await self.get(assertion_id)
        if assertion is None:
            raise OwnerModelError("OWNER_ASSERTION_UNKNOWN", assertion_id)
        updated = assertion.model_copy(update={
            "state": AssertionState.CONTESTED, "updated_at_ms": now,
        })
        await self._update(updated)
        return updated

    # --------------------------------------------------------------- reads

    async def get(self, assertion_id: str) -> OwnerAssertion | None:
        row = await self.store.fetchone(
            "SELECT * FROM owner_cognitive_model WHERE assertion_id = ?", (assertion_id,)
        )
        return None if row is None else self._row(row)

    async def actionable(
        self, owner_principal_id: str, *, field: OwnerModelField | None = None
    ) -> list[OwnerAssertion]:
        """What VAN may actually act on — CONFIRMED or EVIDENCED, and not superseded.

        EVIDENCED is included because refusing to act on a well-evidenced preference would
        make VAN useless until the owner had answered a questionnaire. What changed is
        that the two are distinguishable, so nothing describes one as the other.
        """
        sql = ("SELECT * FROM owner_cognitive_model WHERE owner_principal_id = ? "
               "AND state IN ('CONFIRMED', 'EVIDENCED') AND superseded_by IS NULL")
        params: list[Any] = [owner_principal_id]
        if field is not None:
            sql += " AND field = ?"
            params.append(field.value)
        return [self._row(r) for r in await self.store.fetchall(sql, tuple(params))]

    async def understanding(self, owner_principal_id: str) -> dict[str, Any]:
        """§33's Understanding surface: what VAN believes, and how firmly."""
        rows = await self.store.fetchall(
            "SELECT * FROM owner_cognitive_model WHERE owner_principal_id = ? "
            "AND state != 'SUPERSEDED' ORDER BY field, updated_at_ms DESC",
            (owner_principal_id,),
        )
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            assertion = self._row(row)
            grouped.setdefault(assertion.field.value, []).append({
                "assertion_id": assertion.assertion_id,
                "value": assertion.value,
                "state": assertion.state.value,
                "confidence": round(assertion.confidence, 2),
                "independent_episodes": assertion.independent_episodes,
                "autonomy_bearing": assertion.is_autonomy_bearing,
                "owner_confirmed": assertion.owner_confirmed_at_ms is not None,
                "temporary": assertion.temporary,
                "project_id": assertion.project_id,
            })
        return {"owner_principal_id": owner_principal_id, "fields": grouped}

    # -------------------------------------------------------------- storage

    async def _find(
        self, owner: str, field: OwnerModelField, value: str, project_id: str | None
    ) -> OwnerAssertion | None:
        row = await self.store.fetchone(
            "SELECT * FROM owner_cognitive_model WHERE owner_principal_id = ? AND field = ? "
            "AND value = ? AND IFNULL(project_id,'') = ? AND superseded_by IS NULL",
            (owner, field.value, value, project_id or ""),
        )
        return None if row is None else self._row(row)

    async def _insert(self, a: OwnerAssertion) -> None:
        await self.store.execute(
            """
            INSERT INTO owner_cognitive_model(
              assertion_id, owner_principal_id, field, value, state, confidence,
              evidence_refs_json, supporting_episode_refs_json, project_id, temporary,
              superseded_by, owner_confirmed_at_ms, last_revalidated_at_ms,
              created_at_ms, updated_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                a.assertion_id, a.owner_principal_id, a.field.value, a.value, a.state.value,
                a.confidence, Store.dumps(a.evidence_refs),
                Store.dumps(a.supporting_episode_refs), a.project_id, 1 if a.temporary else 0,
                a.superseded_by, a.owner_confirmed_at_ms, a.last_revalidated_at_ms,
                a.created_at_ms, a.updated_at_ms,
            ),
        )

    async def _update(self, a: OwnerAssertion) -> None:
        await self.store.execute(
            "UPDATE owner_cognitive_model SET state = ?, confidence = ?, "
            "evidence_refs_json = ?, supporting_episode_refs_json = ?, temporary = ?, "
            "superseded_by = ?, owner_confirmed_at_ms = ?, last_revalidated_at_ms = ?, "
            "updated_at_ms = ? WHERE assertion_id = ?",
            (
                a.state.value, a.confidence, Store.dumps(a.evidence_refs),
                Store.dumps(a.supporting_episode_refs), 1 if a.temporary else 0,
                a.superseded_by, a.owner_confirmed_at_ms, a.last_revalidated_at_ms,
                a.updated_at_ms, a.assertion_id,
            ),
        )

    @staticmethod
    def _row(row: Any) -> OwnerAssertion:
        return OwnerAssertion(
            assertion_id=str(row["assertion_id"]),
            owner_principal_id=str(row["owner_principal_id"]),
            field=OwnerModelField(str(row["field"])), value=str(row["value"]),
            state=AssertionState(str(row["state"])), confidence=float(row["confidence"]),
            evidence_refs=json.loads(str(row["evidence_refs_json"])),
            supporting_episode_refs=json.loads(str(row["supporting_episode_refs_json"])),
            project_id=row["project_id"], temporary=bool(row["temporary"]),
            superseded_by=row["superseded_by"],
            owner_confirmed_at_ms=row["owner_confirmed_at_ms"],
            last_revalidated_at_ms=row["last_revalidated_at_ms"],
            created_at_ms=int(row["created_at_ms"]), updated_at_ms=int(row["updated_at_ms"]),
        )


__all__ = [
    "AUTONOMY_BEARING_FIELDS",
    "EPISODE_SOURCES",
    "EPISODES_FOR_CANDIDATE",
    "EPISODES_FOR_CONFIRMED",
    "EPISODES_FOR_EVIDENCED",
    "AssertionState",
    "OwnerAssertion",
    "OwnerCognitiveModel",
    "OwnerModelError",
    "OwnerModelField",
]
