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
* **Only what VAN itself saw happen is evidence** (Memory Fabric contract C1). Every
  supporting episode carries an `ObservationOrigin`, recorded per episode. The ladder
  counts distinct `SYSTEM_OBSERVED` episodes only (`evidencing_episode_count`). An
  episode that reached VAN through Hindsight, an OpenViking retrieval or a model's
  inference is kept for provenance and explanation, but it never advances the ladder and
  never makes anything actionable — however real the mission id it cites. Without this a
  derived memory that merely *mentions* a mission becomes the third vote that makes VAN
  act on its own guess about the owner.
* **Every authoritative mutation advances `owner_model_revision`** (contract C2) in the
  same transaction as the mutation, so a personal context capsule can be fenced against
  the live Owner Model. The revision advances iff a persisted Owner Model row changes: a
  re-observation of an (episode, origin) already recorded, with no new evidence refs, is a
  no-op and does not advance it. A *derived* episode does advance it (the provenance
  record changed), which can only make a capsule stale — the fail-closed direction.
"""

from __future__ import annotations

import json
import time
import uuid
from contextlib import asynccontextmanager
from enum import Enum
from typing import Any, AsyncIterator

import aiosqlite
from pydantic import BaseModel, Field

from van_gateway.storage.db import Store
from van_gateway.understanding.owner_model_outbox import OutboxEventKind, write_outbox


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


class ObservationOrigin(str, Enum):
    """Contract C1 — where one supporting episode came from. Persisted per episode."""

    #: The owner, through confirm/correct. Never accepted by `observe()`.
    OWNER_EXPLICIT = "OWNER_EXPLICIT"
    #: VAN observed it on its own mission/command path. The only admissible evidence.
    SYSTEM_OBSERVED = "SYSTEM_OBSERVED"
    HINDSIGHT_DERIVED = "HINDSIGHT_DERIVED"
    OPENVIKING_RETRIEVED = "OPENVIKING_RETRIEVED"
    MODEL_INFERRED = "MODEL_INFERRED"

    @property
    def is_evidencing(self) -> bool:
        """Whether an episode of this origin counts toward CANDIDATE/EVIDENCED."""
        return self is ObservationOrigin.SYSTEM_OBSERVED


#: Origins `observe()` accepts. OWNER_EXPLICIT is the owner path only.
OBSERVABLE_ORIGINS = frozenset(o for o in ObservationOrigin if o is not ObservationOrigin.OWNER_EXPLICIT)


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


class EpisodeProvenance(BaseModel):
    """One supporting episode and where it came from (C1)."""

    episode_ref: str
    origin: ObservationOrigin
    evidence_refs: list[str] = Field(default_factory=list)
    recorded_at_ms: int = 0
    #: What the ladder counts: the episode's identity, not its spelling. A mission opened
    #: by a command and that command are one thing the owner did, so both carry the key
    #: `command:<source_command_id>`. Empty means "same as `episode_ref`".
    episode_key: str = ""

    @property
    def key(self) -> str:
        return self.episode_key or self.episode_ref


class OwnerAssertion(BaseModel):
    assertion_id: str
    owner_principal_id: str
    field: OwnerModelField
    value: str
    state: AssertionState = AssertionState.OBSERVED
    confidence: float = 0.0
    #: Evidence refs carried by SYSTEM_OBSERVED episodes only. Derived-origin evidence refs
    #: stay on their episode row so nothing reads them as evidence.
    evidence_refs: list[str] = Field(default_factory=list)
    #: SYSTEM_OBSERVED episode refs only — the refs the ladder counts. Every episode of
    #: every origin is in `episodes`.
    supporting_episode_refs: list[str] = Field(default_factory=list)
    episodes: list[EpisodeProvenance] = Field(default_factory=list)
    project_id: str | None = None
    temporary: bool = False
    superseded_by: str | None = None
    owner_confirmed_at_ms: int | None = None
    last_revalidated_at_ms: int | None = None
    created_at_ms: int = 0
    updated_at_ms: int = 0

    @property
    def evidencing_episode_count(self) -> int:
        """C1 — distinct SYSTEM_OBSERVED episodes. The only number the ladder reads.

        Distinct by episode *key*, so a mission and the command that opened it are one
        vote (M4), not two.
        """
        return len({e.key for e in self.episodes if e.origin.is_evidencing})

    @property
    def derived_episode_refs(self) -> list[str]:
        """Episodes recorded for provenance only; they never advanced this assertion."""
        return sorted({e.episode_ref for e in self.episodes if not e.origin.is_evidencing})

    @property
    def independent_episodes(self) -> int:
        """§74 — independence is by episode, and only admissible episodes are evidence."""
        return self.evidencing_episode_count

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

REVISION_SCHEMA = "van.owner_model.revision.v1"

#: SQL for an episode row's identity (alias `e`). M4 — `mission:M` and `command:C` used to
#: be two votes when M was opened by C: one owner command, two episode refs. A mission
#: whose authority envelope names a source command is keyed by that command, so the pair
#: is one vote whichever was observed first (keying the command by its mission instead
#: would miss the case where the command was observed before the mission existed). Keys
#: are computed at read time, not stored, so the recorded ref keeps its provenance.
#: Migration 32 inlines the same expression; the two must stay equivalent.
EPISODE_KEY_SQL = (
    "COALESCE(CASE WHEN substr(e.episode_ref, 1, 8) = 'mission:' THEN ("
    "SELECT 'command:' || NULLIF(trim(json_extract(m.authority_envelope_json, "
    "'$.source_command_id')), '') FROM missions m "
    "WHERE m.mission_id = substr(e.episode_ref, 9) "
    "AND json_valid(m.authority_envelope_json)) END, e.episode_ref)"
)

#: The principal a stored mission principal resolves to. Missions opened by a command
#: are owned by `device:<device_id>` (command/mission_link.py); that device is the owner's
#: only if `owner_device_bindings` binds it to them. `?` is the mission's
#: owner_principal_id.
_RESOLVE_PRINCIPAL_SQL = (
    "SELECT CASE WHEN substr(?1, 1, 7) = 'device:' THEN COALESCE(("
    "SELECT b.owner_principal_id FROM owner_device_bindings b "
    "WHERE b.device_id = substr(?1, 8) LIMIT 1), ?1) ELSE ?1 END AS principal"
)


def _confidence(evidencing: int) -> float:
    """Confidence is a function of admissible evidence only. No admissible episode, none."""
    if evidencing <= 0:
        return 0.0
    return min(0.95, 0.2 + 0.25 * (evidencing - 1))


class OwnerCognitiveModel:
    """Holds assertions about how the owner works, and the rules for trusting them."""

    def __init__(self, store: Store, *, learning: Any | None = None) -> None:
        self.store = store
        # P1-LEARN-001 — an owner correction is the strongest learning signal there is and
        # nothing recorded it. Optional so the model stays constructible on its own.
        self.learning = learning

    @asynccontextmanager
    async def _tx(self) -> AsyncIterator[aiosqlite.Connection]:
        """One connection, one IMMEDIATE transaction: the mutation, its episode rows, the
        revision bump and any outbox row commit together or not at all."""
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            try:
                yield db
            except BaseException:
                await db.rollback()
                raise
            await db.commit()

    async def _require_episode(self, episode_ref: str, owner_principal_id: str) -> str:
        """Refuse an episode reference that does not name something that happened.

        The ladder counts distinct references, so an unresolvable one is not merely
        untidy: it is a vote. Requiring the prefix as well as the row means a caller
        cannot satisfy the check by passing a bare id that happens to collide.

        Returns the normalised ref (`<lowercase kind>:<stripped id>`), so one episode is
        one vote however it was spelled.

        O2 — the episode must also be the owner's. A mission owned by another principal
        (directly, or through a `device:` principal bound to someone else) is refused. A
        command is refused when anything attributes it to another principal: a mission it
        opened, or an audit row whose device is bound to someone else. The audit table
        records no principal of its own, so a command nothing attributes is accepted, as
        it was before; that is the one case this check cannot decide.
        """
        raw = episode_ref or ""
        kind, separator, identifier = raw.partition(":")
        kind, identifier = kind.strip().lower(), identifier.strip()
        if not separator or kind not in EPISODE_SOURCES or not identifier:
            raise OwnerModelError(
                "OWNER_MODEL_EPISODE_UNRESOLVABLE",
                f"{raw.strip()!r} does not name an episode; expected one of "
                f"{sorted(f'{k}:<id>' for k in EPISODE_SOURCES)}",
            )
        table, column = EPISODE_SOURCES[kind]
        row = await self.store.fetchone(
            f"SELECT 1 AS present FROM {table} WHERE {column} = ? LIMIT 1",  # noqa: S608
            (identifier,),
        )
        if row is None:
            raise OwnerModelError(
                "OWNER_MODEL_EPISODE_UNKNOWN",
                f"no {kind} {identifier!r} exists; an assertion cannot be "
                "evidenced by something that did not happen",
            )
        foreign = await self._foreign_principal(kind, identifier, owner_principal_id)
        if foreign is not None:
            raise OwnerModelError(
                "OWNER_MODEL_EPISODE_FOREIGN_PRINCIPAL",
                f"{kind} {identifier!r} belongs to {foreign!r}, not {owner_principal_id!r}; "
                "another principal's episode is not evidence about this owner",
            )
        # The canonical spelling of the episode that was looked up — not the caller's.
        # Returning the caller's spelling made `mission:X`, `mission: X` and `MISSION:\tX`
        # one mission for the lookup and three distinct votes for the ladder.
        return f"{kind}:{identifier}"

    async def _resolve_principal(self, principal: str) -> str:
        row = await self.store.fetchone(_RESOLVE_PRINCIPAL_SQL, (principal,))
        return str(row["principal"])

    async def _foreign_principal(self, kind: str, identifier: str, owner: str) -> str | None:
        """The other principal this episode belongs to, or None if nothing says so."""
        if kind == "mission":
            missions = await self.store.fetchall(
                "SELECT owner_principal_id FROM missions WHERE mission_id = ?", (identifier,))
        else:
            missions = await self.store.fetchall(
                "SELECT owner_principal_id FROM missions WHERE json_valid(authority_envelope_json) "
                "AND json_extract(authority_envelope_json, '$.source_command_id') = ?",
                (identifier,))
            devices = await self.store.fetchall(
                "SELECT DISTINCT b.owner_principal_id FROM audit c "
                "JOIN owner_device_bindings b ON b.device_id = c.device_id "
                "WHERE c.command_id = ?", (identifier,))
            for d in devices:
                if str(d["owner_principal_id"]) != owner:
                    return str(d["owner_principal_id"])
        for m in missions:
            principal = await self._resolve_principal(str(m["owner_principal_id"]))
            if principal != owner:
                return principal
        return None

    @staticmethod
    def _require_origin(origin: Any) -> ObservationOrigin:
        """C1 — no silent default. A caller must say where the observation came from."""
        try:
            parsed = ObservationOrigin(origin)
        except ValueError as exc:
            raise OwnerModelError("OWNER_MODEL_ORIGIN_REQUIRED", repr(origin)) from exc
        if parsed not in OBSERVABLE_ORIGINS:
            raise OwnerModelError(
                "OWNER_MODEL_ORIGIN_OWNER_PATH_ONLY",
                "OWNER_EXPLICIT is produced only by confirm()/correct()",
            )
        return parsed

    async def observe(
        self,
        *,
        owner_principal_id: str,
        field: OwnerModelField,
        value: str,
        episode_ref: str,
        origin: ObservationOrigin,
        evidence_refs: list[str] | None = None,
        project_id: str | None = None,
        now_ms: int | None = None,
    ) -> OwnerAssertion:
        """Record one observation and let the ladder decide what it becomes.

        Observing the same value again from a *new* SYSTEM_OBSERVED episode is what
        advances it. Re-observing from an episode already counted changes nothing, which is
        what stops one emphatic conversation minting a confirmed trait. A derived-origin
        episode is recorded and changes nothing about state or confidence, in any order.
        """
        origin = self._require_origin(origin)
        now = int(time.time() * 1000) if now_ms is None else now_ms
        episode_ref = await self._require_episode(episode_ref, owner_principal_id)
        new_evidence = sorted(set(evidence_refs or []))

        async with self._tx() as db:
            existing = await self._find(db, owner_principal_id, field, value, project_id)

            if existing is None:
                assertion_id = f"oca_{uuid.uuid4().hex}"
                evidencing = origin.is_evidencing
                assertion = OwnerAssertion(
                    assertion_id=assertion_id,
                    owner_principal_id=owner_principal_id, field=field, value=value,
                    state=AssertionState.OBSERVED,
                    evidence_refs=new_evidence if evidencing else [],
                    supporting_episode_refs=[episode_ref] if evidencing else [],
                    project_id=project_id, confidence=_confidence(1 if evidencing else 0),
                    created_at_ms=now, updated_at_ms=now,
                )
                await self._insert(db, assertion)
                await self._record_episode(db, assertion_id, episode_ref, origin, new_evidence, now)
                await self._bump_revision(db, owner_principal_id, now)
                return await self._load_one(db, assertion_id)

            if existing.state is AssertionState.REJECTED:
                # §74 — a correction outranks accumulation. Re-observing something
                # the owner rejected does not revive it; only the owner does.
                return existing

            recorded = await self._record_episode(
                db, existing.assertion_id, episode_ref, origin, new_evidence, now
            )
            if origin.is_evidencing:
                evidence = sorted(set(existing.evidence_refs) | set(new_evidence))
            else:
                evidence = list(existing.evidence_refs)
            if not recorded and evidence == existing.evidence_refs:
                # Already-counted (episode, origin) and nothing new: a true no-op. No
                # write, so no revision bump.
                return existing

            system_refs = await self._evidencing_refs(db, existing.assertion_id)
            # M4 — the ladder counts episodes, not refs: a mission and its source command
            # are two refs and one vote.
            votes = await self._evidencing_count(db, existing.assertion_id)
            state = existing.state
            if existing.state in (AssertionState.OBSERVED, AssertionState.CANDIDATE):
                state = self._ladder(field, votes, existing.state)

            updated = existing.model_copy(update={
                "supporting_episode_refs": system_refs, "evidence_refs": evidence,
                "state": state, "confidence": _confidence(votes),
                "updated_at_ms": now,
            })
            await self._update(db, updated)
            await self._bump_revision(db, owner_principal_id, now)
            return await self._load_one(db, existing.assertion_id)

    @staticmethod
    def _ladder(
        field: OwnerModelField, episodes: int, current: AssertionState
    ) -> AssertionState:
        """Evidence promotes to CANDIDATE, then to EVIDENCED. Never to CONFIRMED.

        `episodes` is the count of distinct SYSTEM_OBSERVED episodes (C1) — callers must
        not pass a count that includes derived-origin episodes.

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

    async def _require(self, db: aiosqlite.Connection, assertion_id: str) -> OwnerAssertion:
        assertion = await self._load_one(db, assertion_id)
        if assertion is None:
            raise OwnerModelError("OWNER_ASSERTION_UNKNOWN", assertion_id)
        return assertion

    async def confirm(self, assertion_id: str, *, now_ms: int | None = None) -> OwnerAssertion:
        """§33 — the owner's confirm. The only route to CONFIRMED for autonomy
        fields, and available for every other field too."""
        now = int(time.time() * 1000) if now_ms is None else now_ms
        async with self._tx() as db:
            assertion = await self._require(db, assertion_id)
            updated = assertion.model_copy(update={
                "state": AssertionState.CONFIRMED, "confidence": 1.0,
                "owner_confirmed_at_ms": now, "last_revalidated_at_ms": now,
                "updated_at_ms": now,
            })
            await self._update(db, updated)
            await self._bump_revision(db, assertion.owner_principal_id, now)
        return updated

    async def correct(
        self, assertion_id: str, *, new_value: str, now_ms: int | None = None
    ) -> OwnerAssertion:
        """A correction supersedes rather than edits, so the history survives.

        The replacement insert, the supersede, the revision bump and the invalidation
        outbox row are one transaction.
        """
        now = int(time.time() * 1000) if now_ms is None else now_ms
        async with self._tx() as db:
            assertion = await self._require(db, assertion_id)
            replacement = OwnerAssertion(
                assertion_id=f"oca_{uuid.uuid4().hex}",
                owner_principal_id=assertion.owner_principal_id, field=assertion.field,
                value=new_value, state=AssertionState.CONFIRMED, confidence=1.0,
                evidence_refs=list(assertion.evidence_refs),
                supporting_episode_refs=list(assertion.supporting_episode_refs),
                project_id=assertion.project_id, owner_confirmed_at_ms=now,
                last_revalidated_at_ms=now, created_at_ms=now, updated_at_ms=now,
            )
            await self._insert(db, replacement)
            # History travels with its origin intact: a derived episode stays derived.
            await db.execute(
                "INSERT OR IGNORE INTO owner_model_episodes(assertion_id, episode_ref, origin, "
                "evidence_refs_json, recorded_at_ms) SELECT ?, episode_ref, origin, "
                "evidence_refs_json, recorded_at_ms FROM owner_model_episodes "
                "WHERE assertion_id = ?",
                (replacement.assertion_id, assertion.assertion_id),
            )
            await self._update(db, assertion.model_copy(update={
                "state": AssertionState.SUPERSEDED,
                "superseded_by": replacement.assertion_id, "updated_at_ms": now,
            }))
            revision = await self._bump_revision(db, assertion.owner_principal_id, now)
            await self._write_outbox(
                db, owner_principal_id=assertion.owner_principal_id,
                owner_model_revision=revision, event_kind=OutboxEventKind.CORRECTED,
                payload={
                    "assertion_ids": [assertion.assertion_id],
                    "superseded_by": replacement.assertion_id,
                    "field": assertion.field.value,
                    "new_state": AssertionState.SUPERSEDED.value,
                },
                now_ms=now,
            )
            replacement = await self._load_one(db, replacement.assertion_id)
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
        return await self._owner_state_change(
            assertion_id, AssertionState.REJECTED, OutboxEventKind.REJECTED,
            {"confidence": 0.0}, now_ms,
        )

    async def contest(self, assertion_id: str, *, now_ms: int | None = None) -> OwnerAssertion:
        """Evidence disagrees with itself; the owner should look."""
        return await self._owner_state_change(
            assertion_id, AssertionState.CONTESTED, OutboxEventKind.CONTESTED, {}, now_ms,
        )

    async def _owner_state_change(
        self, assertion_id: str, state: AssertionState, kind: OutboxEventKind,
        extra: dict[str, Any], now_ms: int | None,
    ) -> OwnerAssertion:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        async with self._tx() as db:
            assertion = await self._require(db, assertion_id)
            updated = assertion.model_copy(update={"state": state, "updated_at_ms": now, **extra})
            await self._update(db, updated)
            revision = await self._bump_revision(db, assertion.owner_principal_id, now)
            await self._write_outbox(
                db, owner_principal_id=assertion.owner_principal_id,
                owner_model_revision=revision, event_kind=kind,
                payload={
                    "assertion_ids": [assertion.assertion_id],
                    "field": assertion.field.value, "new_state": state.value,
                },
                now_ms=now,
            )
        return updated

    async def _write_outbox(self, db: aiosqlite.Connection, **kwargs: Any) -> str:
        """Seam for the outbox write, kept on the instance so a test can inject a failure
        *after* the row is written and before the transaction commits."""
        return await write_outbox(db, **kwargs)

    # ------------------------------------------------------------ revision

    @staticmethod
    async def _bump_revision(db: aiosqlite.Connection, owner: str, now: int) -> int:
        """C2 — advance the owner's revision on the caller's open transaction."""
        cursor = await db.execute(
            "INSERT INTO owner_model_revisions(owner_principal_id, owner_model_revision, "
            "updated_at_ms) VALUES (?, 1, ?) ON CONFLICT(owner_principal_id) DO UPDATE SET "
            "owner_model_revision = owner_model_revision + 1, "
            "updated_at_ms = MAX(updated_at_ms, excluded.updated_at_ms) "
            "RETURNING owner_model_revision",
            (owner, now),
        )
        row = await cursor.fetchone()
        await cursor.close()
        return int(row[0])

    async def current_revision(self, owner_principal_id: str) -> int:
        row = await self.store.fetchone(
            "SELECT owner_model_revision FROM owner_model_revisions WHERE owner_principal_id = ?",
            (owner_principal_id,),
        )
        return 0 if row is None else int(row["owner_model_revision"])

    async def revision(self, owner_principal_id: str, *, now_ms: int | None = None) -> dict[str, Any]:
        """C2 read surface. 0 means no authoritative mutation has ever happened."""
        now = int(time.time() * 1000) if now_ms is None else now_ms
        return {
            "schema": REVISION_SCHEMA,
            "owner_principal_id": owner_principal_id,
            "owner_model_revision": await self.current_revision(owner_principal_id),
            "as_of_ms": now,
        }

    # --------------------------------------------------------------- reads

    async def get(self, assertion_id: str) -> OwnerAssertion | None:
        async with self.store.connection() as db:
            return await self._load_one(db, assertion_id)

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
        async with self.store.connection() as db:
            cursor = await db.execute(sql, tuple(params))
            return await self._hydrate(db, await cursor.fetchall())

    async def understanding(self, owner_principal_id: str) -> dict[str, Any]:
        """§33's Understanding surface: what VAN believes, and how firmly."""
        async with self.store.connection() as db:
            cursor = await db.execute(
                "SELECT * FROM owner_cognitive_model WHERE owner_principal_id = ? "
                "AND state != 'SUPERSEDED' ORDER BY field, updated_at_ms DESC",
                (owner_principal_id,),
            )
            assertions = await self._hydrate(db, await cursor.fetchall())
        grouped: dict[str, list[dict[str, Any]]] = {}
        for assertion in assertions:
            grouped.setdefault(assertion.field.value, []).append({
                "assertion_id": assertion.assertion_id,
                "value": assertion.value,
                "state": assertion.state.value,
                "confidence": round(assertion.confidence, 2),
                "independent_episodes": assertion.independent_episodes,
                "evidencing_episode_count": assertion.evidencing_episode_count,
                # Shown so the owner can see what VAN heard second-hand, and that it was
                # not counted.
                "derived_episode_count": len(assertion.derived_episode_refs),
                "autonomy_bearing": assertion.is_autonomy_bearing,
                "owner_confirmed": assertion.owner_confirmed_at_ms is not None,
                "temporary": assertion.temporary,
                "project_id": assertion.project_id,
            })
        return {
            "owner_principal_id": owner_principal_id,
            "owner_model_revision": await self.current_revision(owner_principal_id),
            "fields": grouped,
        }

    # -------------------------------------------------------------- storage

    async def _find(
        self, db: aiosqlite.Connection, owner: str, field: OwnerModelField, value: str,
        project_id: str | None,
    ) -> OwnerAssertion | None:
        cursor = await db.execute(
            "SELECT * FROM owner_cognitive_model WHERE owner_principal_id = ? AND field = ? "
            "AND value = ? AND IFNULL(project_id,'') = ? AND superseded_by IS NULL",
            (owner, field.value, value, project_id or ""),
        )
        row = await cursor.fetchone()
        return None if row is None else (await self._hydrate(db, [row]))[0]

    async def _load_one(self, db: aiosqlite.Connection, assertion_id: str) -> OwnerAssertion | None:
        cursor = await db.execute(
            "SELECT * FROM owner_cognitive_model WHERE assertion_id = ?", (assertion_id,)
        )
        row = await cursor.fetchone()
        return None if row is None else (await self._hydrate(db, [row]))[0]

    @staticmethod
    async def _record_episode(
        db: aiosqlite.Connection, assertion_id: str, episode_ref: str,
        origin: ObservationOrigin, evidence_refs: list[str], now: int,
    ) -> bool:
        """Insert the (assertion, episode, origin) row. False if it was already there."""
        cursor = await db.execute(
            "INSERT OR IGNORE INTO owner_model_episodes(assertion_id, episode_ref, origin, "
            "evidence_refs_json, recorded_at_ms) VALUES (?, ?, ?, ?, ?)",
            (assertion_id, episode_ref, origin.value, Store.dumps(evidence_refs), now),
        )
        return bool(cursor.rowcount)

    @staticmethod
    async def _evidencing_refs(db: aiosqlite.Connection, assertion_id: str) -> list[str]:
        """Distinct SYSTEM_OBSERVED refs, read from the per-episode table (C1)."""
        cursor = await db.execute(
            "SELECT DISTINCT episode_ref FROM owner_model_episodes "
            "WHERE assertion_id = ? AND origin = ? ORDER BY episode_ref",
            (assertion_id, ObservationOrigin.SYSTEM_OBSERVED.value),
        )
        return [str(r[0]) for r in await cursor.fetchall()]

    @staticmethod
    async def _evidencing_count(db: aiosqlite.Connection, assertion_id: str) -> int:
        """Distinct SYSTEM_OBSERVED episode *keys* — the number the ladder reads (M4)."""
        cursor = await db.execute(
            f"SELECT COUNT(DISTINCT {EPISODE_KEY_SQL}) FROM owner_model_episodes e "  # noqa: S608
            "WHERE e.assertion_id = ? AND e.origin = ?",
            (assertion_id, ObservationOrigin.SYSTEM_OBSERVED.value),
        )
        row = await cursor.fetchone()
        await cursor.close()
        return int(row[0])

    @staticmethod
    async def _insert(db: aiosqlite.Connection, a: OwnerAssertion) -> None:
        await db.execute(
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

    @staticmethod
    async def _update(db: aiosqlite.Connection, a: OwnerAssertion) -> None:
        await db.execute(
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

    async def _hydrate(self, db: aiosqlite.Connection, rows: list[Any]) -> list[OwnerAssertion]:
        if not rows:
            return []
        ids = [str(r["assertion_id"]) for r in rows]
        placeholders = ",".join("?" for _ in ids)
        cursor = await db.execute(
            f"SELECT e.*, {EPISODE_KEY_SQL} AS episode_key FROM owner_model_episodes e "  # noqa: S608
            f"WHERE e.assertion_id IN ({placeholders}) "
            "ORDER BY e.recorded_at_ms, e.episode_ref, e.origin",
            tuple(ids),
        )
        by_assertion: dict[str, list[EpisodeProvenance]] = {}
        for e in await cursor.fetchall():
            by_assertion.setdefault(str(e["assertion_id"]), []).append(EpisodeProvenance(
                episode_ref=str(e["episode_ref"]), origin=ObservationOrigin(str(e["origin"])),
                evidence_refs=json.loads(str(e["evidence_refs_json"])),
                recorded_at_ms=int(e["recorded_at_ms"]),
                episode_key=str(e["episode_key"]),
            ))
        return [self._row(r, by_assertion.get(str(r["assertion_id"]), [])) for r in rows]

    @staticmethod
    def _row(row: Any, episodes: list[EpisodeProvenance]) -> OwnerAssertion:
        return OwnerAssertion(
            assertion_id=str(row["assertion_id"]),
            owner_principal_id=str(row["owner_principal_id"]),
            field=OwnerModelField(str(row["field"])), value=str(row["value"]),
            state=AssertionState(str(row["state"])), confidence=float(row["confidence"]),
            evidence_refs=json.loads(str(row["evidence_refs_json"])),
            supporting_episode_refs=json.loads(str(row["supporting_episode_refs_json"])),
            episodes=episodes,
            project_id=row["project_id"], temporary=bool(row["temporary"]),
            superseded_by=row["superseded_by"],
            owner_confirmed_at_ms=row["owner_confirmed_at_ms"],
            last_revalidated_at_ms=row["last_revalidated_at_ms"],
            created_at_ms=int(row["created_at_ms"]), updated_at_ms=int(row["updated_at_ms"]),
        )


__all__ = [
    "AUTONOMY_BEARING_FIELDS",
    "EPISODE_KEY_SQL",
    "EPISODE_SOURCES",
    "EPISODES_FOR_CANDIDATE",
    "EPISODES_FOR_CONFIRMED",
    "EPISODES_FOR_EVIDENCED",
    "OBSERVABLE_ORIGINS",
    "REVISION_SCHEMA",
    "AssertionState",
    "EpisodeProvenance",
    "ObservationOrigin",
    "OwnerAssertion",
    "OwnerCognitiveModel",
    "OwnerModelError",
    "OwnerModelField",
]
