from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid

from van_gateway.attention.engine import AttentionEngine
from van_gateway.decisions.models import (
    DecisionAnswer, DecisionCreate, DecisionEvidence, DecisionRecord,
    DecisionStatus, binary_choices,
)
from van_gateway.models import AttentionSeverity, AttentionState
from van_gateway.storage.db import Store

DEFAULT_DECISION_TTL_SECONDS = 86400
MAX_DECISION_TTL_SECONDS = 30 * 86400

_COLUMNS = """d.id, d.title, d.body, d.status, d.source, d.hermes_ref,
d.created_at_unix, d.updated_at_unix, x.choices_json, x.evidence_json,
x.mission_id, x.blocking, x.expires_at_unix, x.revision, x.selected_choice_id,
x.answer_note, x.answered_at_unix, x.resolution_request_id,
x.resolution_request_hash, x.create_request_id, x.create_request_hash"""
_FROM = " FROM decisions d LEFT JOIN decision_details x ON x.decision_id=d.id"


class DecisionError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _digest(value: dict) -> str:
    return hashlib.sha256(Store.dumps(value).encode()).hexdigest()


def _record(row) -> DecisionRecord:
    return DecisionRecord(
        id=row["id"], title=row["title"], body=row["body"],
        status=DecisionStatus(row["status"]), source=row["source"],
        hermes_ref=row["hermes_ref"],
        created_at_unix=int(row["created_at_unix"]),
        updated_at_unix=int(row["updated_at_unix"]),
        choices=json.loads(row["choices_json"]) if row["choices_json"] else binary_choices(),
        evidence=json.loads(row["evidence_json"]) if row["evidence_json"] else [],
        mission_id=row["mission_id"],
        blocking=bool(row["blocking"]) if row["blocking"] is not None else True,
        expires_at_unix=row["expires_at_unix"],
        revision=int(row["revision"]) if row["revision"] is not None else 1,
        selected_choice_id=row["selected_choice_id"],
        answer_note=row["answer_note"],
        answered_at_unix=row["answered_at_unix"],
        resolution_request_id=row["resolution_request_id"],
    )


class DecisionService:
    """Bounded owner judgments, separate from command/approval authority.

    Detail and selection commit atomically. Attention is a recoverable projection;
    no answer transitions a mission or issues an action/capability/approval grant.
    """

    def __init__(self, store: Store, attention: AttentionEngine) -> None:
        self.store = store
        self.attention = attention

    async def _reconcile_attention(self, record: DecisionRecord) -> None:
        if record.status is not DecisionStatus.OPEN:
            row = await self.store.fetchone(
                "SELECT id FROM attention WHERE dedupe_key=?", (f"decision:{record.id}",),
            )
            if row:
                await self.attention.mark_handled(row["id"])
            return
        args = {
            "title": record.title,
            "severity": AttentionSeverity.BLOCKER if record.blocking else AttentionSeverity.FOLLOW_UP,
            "source": f"escalation:{record.source}",
            "dedupe_key": f"decision:{record.id}",
            "payload": {"decision_id": record.id, "hermes_ref": record.hermes_ref,
                        "body": record.body, "mission_id": record.mission_id,
                        "expires_at_unix": record.expires_at_unix},
            "state": AttentionState.OPEN,
        }
        try:
            await self.attention.upsert(**args)
        except sqlite3.IntegrityError:
            # Concurrent exact create retries can race only on the attention dedupe
            # projection. The accepted judgment itself was serialized before this.
            if await self.store.fetchone(
                "SELECT id FROM attention WHERE dedupe_key=?", (f"decision:{record.id}",),
            ) is None:
                raise
            await self.attention.upsert(**args)

    async def escalate(self, body: DecisionCreate, *, producer_run_id: str | None = None) -> DecisionRecord:
        request_hash = _digest(body.model_dump(mode="json"))
        decision_id = str(uuid.uuid4())
        choices = body.choices or binary_choices()
        evidence = []
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            now = int(time.time())
            try:
                if producer_run_id is not None:
                    cur = await db.execute(
                        "SELECT m.state FROM hermes_run_bindings b JOIN missions m USING(mission_id) "
                        "WHERE b.hermes_run_id=? AND b.mission_id=?",
                        (producer_run_id, body.mission_id),
                    )
                    bound_mission = await cur.fetchone()
                    if bound_mission is None:
                        raise DecisionError("decision_run_binding_mismatch")
                if body.request_id:
                    cur = await db.execute(
                        "SELECT " + _COLUMNS + _FROM + " WHERE x.create_request_id=?",
                        (body.request_id,),
                    )
                    previous = await cur.fetchone()
                    if previous:
                        if previous["create_request_hash"] != request_hash:
                            raise DecisionError("decision_create_request_conflict")
                        await db.commit()
                        record = _record(previous)
                    else:
                        record = None
                else:
                    record = None
                if record is None:
                    if producer_run_id is not None:
                        from van_gateway.mission.models import TERMINAL_STATES
                        if bound_mission["state"] in {state.value for state in TERMINAL_STATES}:
                            raise DecisionError("decision_mission_terminal")
                    expires = body.expires_at_unix or now + DEFAULT_DECISION_TTL_SECONDS
                    if expires <= now or expires > now + MAX_DECISION_TTL_SECONDS:
                        raise DecisionError("decision_expiry_invalid")
                    if body.mission_id:
                        cur = await db.execute(
                            "SELECT mission_id FROM missions WHERE mission_id=?", (body.mission_id,),
                        )
                        if await cur.fetchone() is None:
                            raise DecisionError("decision_mission_unknown")
                    for item in body.evidence:
                        observed = DecisionEvidence(**item.model_dump())
                        if item.kind == "MISSION_EVENT":
                            if not body.mission_id:
                                raise DecisionError("decision_evidence_uncorrelated")
                            cur = await db.execute(
                                "SELECT event_id, summary, occurred_at_ms FROM mission_events "
                                "WHERE mission_id=? AND (event_id=? OR evidence_ref=?) "
                                "ORDER BY occurred_at_ms DESC LIMIT 1",
                                (body.mission_id, item.ref, item.ref),
                            )
                            event = await cur.fetchone()
                            if event is None:
                                raise DecisionError("decision_evidence_uncorrelated")
                            observed.label = str(event["summary"])[:200]
                            observed.observed_at_unix = int(event["occurred_at_ms"]) // 1000
                            observed.verification = "RECORDED_EVENT"
                        evidence.append(observed)
                    await db.execute(
                        "INSERT INTO decisions(id,title,body,status,source,hermes_ref,"
                        "created_at_unix,updated_at_unix) VALUES (?,?,?,?,?,?,?,?)",
                        (decision_id, body.title, body.body, DecisionStatus.OPEN.value,
                         body.source, body.hermes_ref, now, now),
                    )
                    await db.execute(
                        "INSERT INTO decision_details(decision_id,choices_json,evidence_json,"
                        "mission_id,blocking,expires_at_unix,revision,create_request_id,create_request_hash) "
                        "VALUES (?,?,?,?,?,?,1,?,?)",
                        (decision_id, Store.dumps([c.model_dump(mode="json") for c in choices]),
                         Store.dumps([e.model_dump(mode="json") for e in evidence]),
                         body.mission_id, int(body.blocking), expires,
                         body.request_id, request_hash if body.request_id else None),
                    )
                    cur = await db.execute("SELECT " + _COLUMNS + _FROM + " WHERE d.id=?", (decision_id,))
                    record = _record(await cur.fetchone())
                    await db.commit()
            except BaseException:
                await db.rollback()
                raise
        # A spent create request recovers the existing record even if its original
        # response/attention publish was lost. It cannot reopen a answered decision.
        await self.expire_due(decision_id=record.id)
        current = await self._read(record.id)
        await self._reconcile_attention(current)
        return current

    async def _read(self, decision_id: str) -> DecisionRecord | None:
        row = await self.store.fetchone(
            "SELECT " + _COLUMNS + _FROM + " WHERE d.id=?", (decision_id,),
        )
        return _record(row) if row else None

    async def get(self, decision_id: str) -> DecisionRecord | None:
        await self.expire_due(decision_id=decision_id)
        record = await self._read(decision_id)
        if record and record.status is not DecisionStatus.OPEN:
            await self._reconcile_attention(record)
        return record

    async def expire_due(self, *, decision_id: str | None = None, now_unix: int | None = None) -> int:
        restriction = " AND d.id=?" if decision_id else ""
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            now = int(time.time()) if now_unix is None else now_unix
            params = (now, decision_id) if decision_id else (now,)
            cur = await db.execute(
                "SELECT d.id FROM decisions d JOIN decision_details x ON x.decision_id=d.id "
                "WHERE d.status='OPEN' AND x.expires_at_unix<=?" + restriction, params,
            )
            ids = [row["id"] for row in await cur.fetchall()]
            for ident in ids:
                await db.execute(
                    "UPDATE decisions SET status='EXPIRED',updated_at_unix=? WHERE id=? AND status='OPEN'",
                    (now, ident),
                )
            await db.commit()
        # Expiry is durable before the attention projection. Also recover any
        # terminal projection whose previous publish failed after that commit.
        pending = await self.store.fetchall(
            "SELECT d.id FROM decisions d JOIN attention a ON a.dedupe_key='decision:' || d.id "
            "WHERE d.status!='OPEN' AND a.state!='HANDLED'" + (" AND d.id=?" if decision_id else ""),
            (decision_id,) if decision_id else (),
        )
        for ident in sorted(set(ids) | {row["id"] for row in pending}):
            await self._reconcile_attention(await self._read(ident))
        return len(ids)

    async def list_open(self) -> list[DecisionRecord]:
        await self.expire_due()
        rows = await self.store.fetchall(
            "SELECT " + _COLUMNS + _FROM + " WHERE d.status='OPEN' ORDER BY d.created_at_unix DESC",
        )
        return [_record(row) for row in rows]

    async def answer(self, decision_id: str, body: DecisionAnswer, *, owner_device_id: str | None = None) -> DecisionRecord:
        if not isinstance(body, DecisionAnswer):
            raise DecisionError("decision_answer_invalid")
        request_hash = _digest({"decision_id": decision_id, **body.model_dump(mode="json")})
        expired = False
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            now = int(time.time())
            try:
                if owner_device_id is not None:
                    cur = await db.execute("SELECT revoked_at_unix FROM devices WHERE device_id=?", (owner_device_id,))
                    owner = await cur.fetchone()
                    if owner is None or owner["revoked_at_unix"] is not None:
                        raise DecisionError("decision_owner_device_revoked")
                cur = await db.execute("SELECT " + _COLUMNS + _FROM + " WHERE d.id=?", (decision_id,))
                row = await cur.fetchone()
                if row is None:
                    raise KeyError("decision_not_found")
                record = _record(row)
                if row["resolution_request_id"] == body.request_id:
                    if row["resolution_request_hash"] != request_hash:
                        raise DecisionError("decision_answer_request_conflict")
                    await db.commit()
                elif record.status is DecisionStatus.EXPIRED:
                    raise DecisionError("decision_expired")
                elif record.status is not DecisionStatus.OPEN:
                    raise DecisionError("decision_already_resolved")
                elif record.expires_at_unix is not None and record.expires_at_unix <= now:
                    await db.execute(
                        "UPDATE decisions SET status='EXPIRED',updated_at_unix=? WHERE id=? AND status='OPEN'",
                        (now, decision_id),
                    )
                    await db.commit()
                    expired = True
                else:
                    if body.expected_revision != record.revision:
                        raise DecisionError("decision_revision_stale")
                    if body.choice_id not in {c.id for c in record.choices}:
                        raise DecisionError("decision_choice_unknown")
                    if row["choices_json"] is None:
                        # The first typed answer upgrades legacy binary metadata without
                        # altering the owner's original question or its creation time.
                        await db.execute(
                            "INSERT INTO decision_details(decision_id,choices_json,evidence_json,revision) "
                            "VALUES (?,?,?,?)",
                            (decision_id, Store.dumps([c.model_dump() for c in record.choices]), "[]", record.revision),
                        )
                    status = (DecisionStatus.APPROVED if body.choice_id == "approve"
                              else DecisionStatus.REJECTED if body.choice_id == "reject"
                              else DecisionStatus.ANSWERED)
                    await db.execute(
                        "UPDATE decisions SET status=?,updated_at_unix=? WHERE id=? AND status='OPEN'",
                        (status.value, now, decision_id),
                    )
                    await db.execute(
                        "UPDATE decision_details SET selected_choice_id=?,answer_note=?,answered_at_unix=?,"
                        "resolution_request_id=?,resolution_request_hash=? WHERE decision_id=?",
                        (body.choice_id, body.note, now, body.request_id, request_hash, decision_id),
                    )
                    if owner_device_id is not None:
                        # Record the actual owner observation in the same commit. Reads
                        # and exact answer retries never recreate deliberately forgotten
                        # derived memory from the retained judgment record.
                        from van_gateway.learning.observations import record_owner_decision_fingerprint
                        await record_owner_decision_fingerprint(
                            db, decision_id=decision_id, mission_id=record.mission_id,
                            choice_id=body.choice_id, owner_note=body.note,
                            evidence_refs=[item.ref for item in record.evidence],
                            now_ms=now * 1000,
                            options_considered=[choice.id for choice in record.choices],
                        )
                    await db.commit()
            except BaseException:
                await db.rollback()
                raise
        current = await self._read(decision_id)
        await self._reconcile_attention(current)
        if expired:
            raise DecisionError("decision_expired")
        return current

    async def resolve(self, decision_id: str, *, approved: bool, owner_device_id: str | None = None) -> DecisionRecord:
        """Compatibility binary judgment; this never issues execution permission."""
        if type(approved) is not bool:
            raise DecisionError("decision_answer_invalid")
        record = await self.get(decision_id)
        if record is None:
            raise KeyError("decision_not_found")
        if {choice.id for choice in record.choices} != {"approve", "reject"}:
            raise DecisionError("decision_requires_typed_choice")
        choice_id = "approve" if approved else "reject"
        status = DecisionStatus.APPROVED if approved else DecisionStatus.REJECTED
        if record.status is DecisionStatus.EXPIRED:
            raise DecisionError("decision_already_resolved")
        if record.status is status and record.selected_choice_id is None:
            # Recover terminal historical binary rows that predate detail metadata.
            await self._reconcile_attention(record)
            return record
        return await self.answer(
            decision_id, DecisionAnswer(choice_id=choice_id, expected_revision=record.revision,
                                        request_id=f"legacy:{decision_id}:{choice_id}"),
            owner_device_id=owner_device_id,
        )
