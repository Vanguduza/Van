"""Durable shared Muse ledger. Browser observations are data; owner actions are authority.

Every mutation and its event are committed together. A command is claimed before the
first possible browser effect and is never automatically re-dispatched after a crash.
The authenticated producer alone reports the resulting provider observation. CONFIRMED
means that the requested interaction was observed, never that the underlying work passed.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any
from van_gateway.approval.service import OwnerApprovalError, OwnerApprovalService
from van_gateway.storage.db import Store
from .models import Action, MuseError, Outcome, Snapshot, canonical, digest

FRESH_MS = 90000
COMMAND_TTL_MS = 60000


class MuseService:
    def __init__(self, store: Store, *, producer_id: str, now=lambda: int(time.time() * 1000), classification_policy=None):
        self.store, self.producer_id, self.now = store, producer_id, now
        # A producer may report a risk label, but only gateway policy may lower step-up.
        self.classification_policy = classification_policy or (lambda prompt: "UNCLASSIFIED")
        self.approval = OwnerApprovalService(store)

    async def _row(self, db, query, args=()):
        return await (await db.execute(query, args)).fetchone()

    async def _event(self, db, kind: str, payload: dict, *, event_id: str | None = None):
        now = self.now()
        payload = {**payload, "observed_at_ms": now}
        await db.execute(
            "INSERT INTO events(event_type,payload_json,created_at_unix,event_id,occurred_at_ms,correlation_id) VALUES(?,?,?,?,?,?)",
            ("muse." + kind, canonical(payload), now // 1000, event_id or "muse-event:" + uuid.uuid4().hex, now, payload.get("command_id")),
        )

    async def ingest(self, value: Snapshot) -> dict:
        if value.producer_id != self.producer_id:
            raise MuseError("producer_mismatch", 403)
        now = self.now()
        payload = value.model_dump()
        hashed = digest(payload)
        async with self.store.connection() as db:
            await db.execute("PRAGMA synchronous=FULL")
            await db.execute("BEGIN IMMEDIATE")
            prior = await self._row(db, "SELECT * FROM muse_sources WHERE producer_id=?", (value.producer_id,))
            if prior and value.sequence <= prior["sequence"]:
                if value.sequence == prior["sequence"] and hashed == prior["digest"]:
                    return {"sequence": value.sequence, "digest": hashed, "replayed": True}
                raise MuseError("source_sequence_conflict")
            if value.observed_at_ms > now + 5000 or now - value.observed_at_ms > FRESH_MS:
                raise MuseError("source_timestamp_invalid")
            if prior and value.observed_at_ms < prior["observed_at_ms"]:
                raise MuseError("source_clock_regressed")
            if prior and value.sequence != prior["sequence"] + 1:
                await self._event(db, "source_gap", {"previous": prior["sequence"], "received": value.sequence})
            await db.execute(
                "INSERT INTO muse_sources VALUES(?,?,?,?,?) ON CONFLICT(producer_id) DO UPDATE SET sequence=excluded.sequence,digest=excluded.digest,observed_at_ms=excluded.observed_at_ms,payload_json=excluded.payload_json",
                (value.producer_id, value.sequence, hashed, value.observed_at_ms, canonical(payload)),
            )
            seen = set()
            for session in value.sessions:
                seen.add(session.session_id)
                if not session.current_job_only and (session.messages or session.approvals):
                    raise MuseError("unqualified_content_refused")
                raw = session.model_dump()
                binding = digest(session.binding())
                old = await self._row(db, "SELECT * FROM muse_sessions WHERE session_id=?", (session.session_id,))
                if old and (old["producer_id"] != value.producer_id or old["binding_digest"] != binding):
                    raise MuseError("immutable_session_binding_changed")
                if old and session.revision < old["revision"]:
                    raise MuseError("session_revision_regressed")
                if old and session.revision == old["revision"] and canonical(raw) != old["payload_json"]:
                    raise MuseError("session_revision_content_conflict")
                await db.execute(
                    "INSERT INTO muse_sessions VALUES(?,?,?,?,?,?,?) ON CONFLICT(session_id) DO UPDATE SET revision=excluded.revision,observed_at_ms=excluded.observed_at_ms,present=1,payload_json=excluded.payload_json",
                    (session.session_id, value.producer_id, binding, session.revision, value.observed_at_ms, 1, canonical(raw)),
                )
                if not old or old["payload_json"] != canonical(raw):
                    await self._event(db, "session_changed", {"session_id": session.session_id, "task_id": session.task_id, "project_id": session.project_id, "revision": session.revision})
                prompt_ids = set()
                for prompt in session.approvals:
                    prompt_ids.add(prompt.id)
                    p = prompt.model_dump()
                    p["action_class"] = "A5" if prompt.action_class == "A5" else self.classification_policy(prompt)
                    if prompt.expires_at_epoch_ms > value.observed_at_ms + 15 * 60000:
                        raise MuseError("approval_expiry_unbounded")
                    oldp = await self._row(db, "SELECT * FROM muse_approvals WHERE approval_id=?", (prompt.id,))
                    if oldp:
                        if oldp["session_id"] != session.session_id or prompt.revision < oldp["revision"]:
                            raise MuseError("approval_identity_conflict")
                        if prompt.revision == oldp["revision"] and oldp["payload_json"] != canonical(p):
                            raise MuseError("approval_revision_content_conflict")
                        # A consumed/unknown control cannot be resurrected by a replay or heartbeat.
                        state = oldp["state"] if prompt.revision == oldp["revision"] else "AWAITING_OWNER"
                        if oldp["state"] == "DISPATCHED" and prompt.revision != oldp["revision"]:
                            state = "CHANGED_DURING_DISPATCH"
                        await db.execute("UPDATE muse_approvals SET revision=?,fingerprint=?,state=?,observed_at_ms=?,payload_json=? WHERE approval_id=?", (prompt.revision, prompt.action_fingerprint, state, value.observed_at_ms, canonical(p), prompt.id))
                    else:
                        await db.execute("INSERT INTO muse_approvals VALUES(?,?,?,?,?,?,?,?)", (prompt.id, session.session_id, prompt.revision, prompt.action_fingerprint, "AWAITING_OWNER", None, value.observed_at_ms, canonical(p)))
                        await self._event(db, "approval_requested", {"approval_id": prompt.id, "session_id": session.session_id, "task_id": session.task_id, "project_id": session.project_id, "expires_at_epoch_ms": prompt.expires_at_epoch_ms})
                rows = await (await db.execute("SELECT approval_id,state FROM muse_approvals WHERE session_id=?", (session.session_id,))).fetchall()
                for row in rows:
                    if row["approval_id"] not in prompt_ids and row["state"] == "AWAITING_OWNER":
                        await db.execute("UPDATE muse_approvals SET state='NO_LONGER_PRESENT' WHERE approval_id=?", (row["approval_id"],))
                        await self._event(db, "approval_changed", {"approval_id": row["approval_id"], "state": "NO_LONGER_PRESENT"})
            if value.complete:
                rows = await (await db.execute("SELECT session_id FROM muse_sessions WHERE producer_id=? AND present=1", (value.producer_id,))).fetchall()
                for row in rows:
                    if row["session_id"] not in seen:
                        await db.execute("UPDATE muse_sessions SET present=0 WHERE session_id=?", (row["session_id"],))
                        await db.execute("UPDATE muse_approvals SET state='NO_LONGER_PRESENT' WHERE session_id=? AND state='AWAITING_OWNER'", (row["session_id"],))
                        await self._event(db, "session_removed", {"session_id": row["session_id"]})
            if not prior or (json.loads(prior["payload_json"])["watchdog"], json.loads(prior["payload_json"])["health"]) != (value.watchdog, value.health):
                await self._event(db, "watchdog_changed", {"watchdog": value.watchdog, "health": value.health})
            await db.commit()
        return {"sequence": value.sequence, "digest": hashed, "replayed": False}

    async def _checked(self, db, action: Action):
        src = await self._row(db, "SELECT * FROM muse_sources WHERE producer_id=?", (self.producer_id,))
        now = self.now()
        if not src or not 0 <= now - src["observed_at_ms"] <= FRESH_MS:
            raise MuseError("source_stale", 503)
        source = json.loads(src["payload_json"])
        if source["health"] != "GREEN" or source["watchdog"] != "GREEN" or not source["complete"]:
            raise MuseError("source_not_qualified", 503)
        row = await self._row(db, "SELECT * FROM muse_sessions WHERE session_id=? AND present=1", (action.session_id,))
        if not row or not 0 <= now - row["observed_at_ms"] <= FRESH_MS:
            raise MuseError("session_unavailable")
        session = json.loads(row["payload_json"])
        for key in ("thread_id", "task_id", "project_id", "scope_binding_sha256", "control_generation"):
            if session[key] != getattr(action, key):
                raise MuseError("session_scope_mismatch")
        if not session["current_job_only"]:
            raise MuseError("capture_unqualified")
        if action.action == "SEND_MESSAGE":
            if not session["can_send"] or session["revision"] != action.expected_revision:
                raise MuseError("conversation_changed")
            return session, None
        approval = await self._row(db, "SELECT * FROM muse_approvals WHERE approval_id=? AND session_id=?", (action.approval_id, action.session_id))
        if not approval or approval["state"] != "AWAITING_OWNER":
            raise MuseError("approval_already_handled_or_unknown")
        prompt = json.loads(approval["payload_json"])
        if approval["revision"] != action.expected_revision or approval["fingerprint"] != action.action_fingerprint:
            raise MuseError("approval_changed")
        if prompt["expires_at_epoch_ms"] <= now or action.choice not in prompt["allowed_actions"]:
            raise MuseError("approval_expired_or_choice_unavailable")
        if action.choice == "ALLOW_ONCE" and prompt["action_class"] == "A5":
            raise MuseError("action_prohibited", 403)
        return session, prompt

    @staticmethod
    def needs_stepup(action, prompt):
        return action.action == "DECIDE_APPROVAL" and action.choice == "ALLOW_ONCE" and prompt["action_class"] not in ("A1", "A2", "A3")

    async def challenge(self, action: Action, device_id: str):
        async with self.store.connection() as db:
            _, prompt = await self._checked(db, action)
        if not self.needs_stepup(action, prompt):
            raise MuseError("step_up_not_required", 422)
        challenge = await self.approval.issue(device_id=device_id, source_command_id=action.idempotency_key, turn_id=action.approval_id, action_id="muse.decide", text=canonical(action.intent()), project_id=action.project_id)
        return {"challenge_id": challenge.challenge_id, "canonical": challenge.canonical, "expires_at_unix": challenge.expires_at_unix}

    async def enqueue(self, action: Action, principal: str, *, device_id: str | None = None):
        intent = action.intent()
        hashed = digest(intent)
        # Read before consuming an A4 proof: an identical retry has already earned its receipt.
        prior = await self.store.fetchone("SELECT * FROM muse_commands WHERE principal=? AND idempotency_key=?", (principal, action.idempotency_key))
        if prior:
            if prior["request_digest"] != hashed:
                raise MuseError("idempotency_conflict")
            return self._receipt(prior)
        async with self.store.connection() as db:
            _, prompt = await self._checked(db, action)
        if self.needs_stepup(action, prompt):
            if device_id is None and principal.startswith("site:"):
                # This is a request for owner verification, not permission to actuate.
                # Only a separately authenticated native command with a valid biometric
                # proof can satisfy it. The producer cannot claim this row.
                return await self.request_native_verification(action, principal)
            if not device_id or not action.challenge_id or not action.signature_b64:
                raise MuseError("bound_owner_step_up_required", 403)
            try:
                await self.approval.verify_and_consume(challenge_id=action.challenge_id, source_command_id=action.idempotency_key, signature_b64=action.signature_b64, device_id=device_id, turn_id=action.approval_id, action_id="muse.decide", text=canonical(intent), project_id=action.project_id)
            except OwnerApprovalError as exc:
                raise MuseError(str(exc), 403) from exc
        async with self.store.connection() as db:
            await db.execute("PRAGMA synchronous=FULL")
            await db.execute("BEGIN IMMEDIATE")
            prior = await self._row(db, "SELECT * FROM muse_commands WHERE principal=? AND idempotency_key=?", (principal, action.idempotency_key))
            if prior:
                if prior["request_digest"] != hashed:
                    raise MuseError("idempotency_conflict")
                return self._receipt(prior)
            session, prompt = await self._checked(db, action)
            command_id = "musecmd_" + uuid.uuid4().hex
            created = self.now()
            expires = min(created + COMMAND_TTL_MS, prompt["expires_at_epoch_ms"] if prompt else created + COMMAND_TTL_MS)
            await db.execute("INSERT INTO muse_commands(command_id,principal,idempotency_key,request_digest,payload_json,state,producer_id,created_at_ms,expires_at_ms) VALUES(?,?,?,?,?,'QUEUED',?,?,?)", (command_id, principal, action.idempotency_key, hashed, canonical(intent), self.producer_id, created, expires))
            if prompt:
                await db.execute("UPDATE muse_approvals SET state='DISPATCHED',command_id=? WHERE approval_id=? AND state='AWAITING_OWNER'", (command_id, action.approval_id))
            if prompt:
                proposals = await (await db.execute("SELECT * FROM muse_commands WHERE state='AWAITING_OWNER_VERIFICATION' AND expires_at_ms>? AND json_extract(payload_json,'$.approval_id')=?", (created, action.approval_id))).fetchall()
                for proposal in proposals:
                    requested = json.loads(proposal["payload_json"])
                    comparison = {k:v for k,v in requested.items() if k not in ("idempotency_key", "choice")}
                    actual = {k:v for k,v in intent.items() if k not in ("idempotency_key", "choice")}
                    if comparison != actual:
                        continue
                    linked_state = "LINKED" if requested.get("choice") == intent.get("choice") else "SUPERSEDED"
                    await db.execute("UPDATE muse_commands SET state=?,linked_command_id=? WHERE command_id=?", (linked_state, command_id, proposal["command_id"]))
                    await self._event(db, "owner_verification_resolved", {"command_id":proposal["command_id"],"linked_command_id":command_id,"approval_id":action.approval_id,"state":linked_state})
            await self._event(db, "command_queued", {"command_id": command_id, "task_id": action.task_id, "approval_id": action.approval_id})
            row = await self._row(db, "SELECT * FROM muse_commands WHERE command_id=?", (command_id,))
            await db.commit()
        return self._receipt(row)

    async def request_native_verification(self, action, principal):
        intent = action.intent()
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            prior = await self._row(db, "SELECT * FROM muse_commands WHERE principal=? AND idempotency_key=?", (principal, action.idempotency_key))
            if prior:
                if prior["request_digest"] != digest(intent):
                    raise MuseError("idempotency_conflict")
                return self._receipt(prior)
            _, prompt = await self._checked(db, action)
            if not self.needs_stepup(action, prompt):
                raise MuseError("owner_verification_not_required",422)
            now = self.now()
            command_id = "musecmd_" + uuid.uuid4().hex
            expires = min(now + 120000, prompt["expires_at_epoch_ms"])
            await db.execute("INSERT INTO muse_commands(command_id,principal,idempotency_key,request_digest,payload_json,state,producer_id,created_at_ms,expires_at_ms) VALUES(?,?,?,?,?,'AWAITING_OWNER_VERIFICATION',?,?,?)", (command_id, principal, action.idempotency_key, digest(intent), canonical(intent), self.producer_id, now, expires))
            await self._event(db, "owner_verification_required", {"command_id":command_id,"approval_id":action.approval_id,"task_id":action.task_id,"project_id":action.project_id,"expires_at_epoch_ms":expires})
            row = await self._row(db, "SELECT * FROM muse_commands WHERE command_id=?", (command_id,))
            await db.commit()
        return self._receipt(row)

    async def _current_receipt(self, row):
        value = self._receipt(row)
        if row["state"] == "LINKED" and row["linked_command_id"]:
            actual = await self.store.fetchone("SELECT * FROM muse_commands WHERE command_id=?", (row["linked_command_id"],))
            if actual:
                value.update(state=actual["state"], result=json.loads(actual["result_json"]) if actual["result_json"] else None, linked_command_id=actual["command_id"], verified_on_owner_device=True)
        if row["state"] == "AWAITING_OWNER_VERIFICATION" and row["expires_at_ms"] <= self.now():
            value["state"] = "EXPIRED"
        return value

    @staticmethod
    def _receipt(row):
        return {"command_id": row["command_id"], "state": row["state"], "created_at_ms": row["created_at_ms"], "expires_at_ms": row["expires_at_ms"], "result": json.loads(row["result_json"]) if row["result_json"] else None, "is_work_outcome": False}

    async def receipt(self, command_id: str, principal: str):
        row = await self.store.fetchone("SELECT * FROM muse_commands WHERE command_id=? AND principal=?", (command_id, principal))
        if not row:
            raise MuseError("command_unknown", 404)
        return await self._current_receipt(row)

    async def receipt_by_key(self, key: str, principal: str):
        row = await self.store.fetchone("SELECT * FROM muse_commands WHERE idempotency_key=? AND principal=?", (key, principal))
        if not row:
            raise MuseError("command_unknown", 404)
        return await self._current_receipt(row)

    async def claim(self):
        async with self.store.connection() as db:
            await db.execute("PRAGMA synchronous=FULL")
            await db.execute("BEGIN IMMEDIATE")
            now = self.now()
            expired = await (await db.execute("SELECT command_id,payload_json FROM muse_commands WHERE producer_id=? AND state='QUEUED' AND expires_at_ms<=?", (self.producer_id, now))).fetchall()
            for row in expired:
                await db.execute("UPDATE muse_commands SET state='EXPIRED',completed_at_ms=? WHERE command_id=?", (now, row["command_id"]))
                await self._event(db, "command_changed", {"command_id": row["command_id"], "state": "EXPIRED"})
            rows = await (await db.execute("SELECT * FROM muse_commands WHERE producer_id=? AND state='QUEUED' AND expires_at_ms>? ORDER BY created_at_ms LIMIT 20", (self.producer_id, now))).fetchall()
            commands = []
            for row in rows:
                await db.execute("UPDATE muse_commands SET state='CLAIMED',claimed_at_ms=? WHERE command_id=? AND state='QUEUED'", (now, row["command_id"]))
                intent = json.loads(row["payload_json"])
                prompt_row = await self._row(db, "SELECT payload_json FROM muse_approvals WHERE approval_id=?", (intent.get("approval_id"),))
                commands.append({"schema_version": 1, "command_id": row["command_id"], "command_digest": row["request_digest"], "principal": row["principal"], "producer_id": self.producer_id, "issued_at_ms": now, "expires_at_ms": row["expires_at_ms"], "intent": intent, "prompt": json.loads(prompt_row["payload_json"]) if prompt_row else None})
                await self._event(db, "command_changed", {"command_id": row["command_id"], "state": "CLAIMED"})
            await db.commit()
        return commands

    async def complete(self, outcome: Outcome):
        async with self.store.connection() as db:
            await db.execute("PRAGMA synchronous=FULL")
            await db.execute("BEGIN IMMEDIATE")
            row = await self._row(db, "SELECT * FROM muse_commands WHERE command_id=? AND producer_id=?", (outcome.command_id, self.producer_id))
            if not row or row["request_digest"] != outcome.command_digest:
                raise MuseError("outcome_command_mismatch")
            data = outcome.model_dump()
            if row["result_json"]:
                if row["result_json"] == canonical(data):
                    return self._receipt(row)
                # UNKNOWN may be resolved with later independent provider evidence, never redispatched.
                if row["state"] != "UNKNOWN":
                    raise MuseError("outcome_conflict")
            if row["state"] not in ("CLAIMED", "UNKNOWN"):
                raise MuseError("command_not_claimed")
            if outcome.observed_at_ms < row["claimed_at_ms"] or outcome.observed_at_ms > self.now() + 5000:
                raise MuseError("outcome_time_invalid")
            await db.execute("UPDATE muse_commands SET state=?,completed_at_ms=?,result_json=? WHERE command_id=?", (outcome.state, self.now(), canonical(data), outcome.command_id))
            intent = json.loads(row["payload_json"])
            if intent.get("approval_id"):
                await db.execute("UPDATE muse_approvals SET state=? WHERE approval_id=? AND command_id=?", (outcome.state, intent["approval_id"], outcome.command_id))
            await self._event(db, "command_changed", {"command_id": outcome.command_id, "state": outcome.state, "approval_id": intent.get("approval_id"), "task_id": intent["task_id"], "evidence_digest": outcome.evidence_digest})
            row = await self._row(db, "SELECT * FROM muse_commands WHERE command_id=?", (outcome.command_id,))
            await db.commit()
        return self._receipt(row)

    async def overview(self):
        source = await self.store.fetchone("SELECT * FROM muse_sources WHERE producer_id=?", (self.producer_id,))
        now = self.now()
        fresh = bool(source and 0 <= now - source["observed_at_ms"] <= FRESH_MS)
        raw = json.loads(source["payload_json"]) if source else {}
        fresh = fresh and raw.get("health") == raw.get("watchdog") == "GREEN" and raw.get("complete") is True
        rows = await self.store.fetchall("SELECT * FROM muse_sessions WHERE producer_id=? AND present=1 ORDER BY session_id", (self.producer_id,))
        sessions = [json.loads(r["payload_json"]) for r in rows]
        prompts = await self.store.fetchall("SELECT a.*,s.payload_json AS session_json FROM muse_approvals a JOIN muse_sessions s ON s.session_id=a.session_id WHERE s.present=1 AND s.producer_id=? AND a.state IN ('AWAITING_OWNER','DISPATCHED','UNKNOWN','CHANGED_DURING_DISPATCH')", (self.producer_id,))
        approvals = []
        for row in prompts:
            session = json.loads(row["session_json"])
            prompt = json.loads(row["payload_json"])
            prompt.update({k:session[k] for k in ("session_id", "thread_id", "task_id", "project_id", "scope_binding_sha256", "control_generation")})
            prompt["state"] = "EXPIRED" if row["state"] == "AWAITING_OWNER" and prompt["expires_at_epoch_ms"] <= now else row["state"]
            approvals.append(prompt)
        cursor = await self.store.fetchone("SELECT COALESCE(MAX(seq),0) AS seq FROM events")
        return {"schema_version": 1, "generated_at_ms": now, "event_cursor": cursor["seq"], "relay":{"state":"live" if fresh else "stale", "last_source_at_ms":source["observed_at_ms"] if source else None}, "health":{"state":raw.get("health","UNOBSERVED")}, "watchdog":{"state":raw.get("watchdog","UNOBSERVED")}, "sessions":sessions, "threads":[{**{k:s[k] for k in ("session_id","thread_id","task_id","project_id","scope_binding_sha256","control_generation","revision","title","can_send")},"id":s["thread_id"]} for s in sessions], "messages":[{**m,"session_id":s["session_id"],"thread_id":s["thread_id"]} for s in sessions for m in s["messages"]], "approvals":approvals, "capabilities":{"conversation":fresh,"approvals":fresh,"task_controls":"existing_dial_task_route", "a4":"bound_device_step_up"}}

    async def replay(self, after: int, limit: int = 100):
        rows = await self.store.fetchall("SELECT seq,event_id,event_type,payload_json,occurred_at_ms FROM events WHERE seq>? AND event_type LIKE 'muse.%' ORDER BY seq LIMIT ?", (after, min(max(limit,1),200)))
        return {"events":[{"seq":r["seq"],"id":r["event_id"],"type":r["event_type"],"payload":json.loads(r["payload_json"]),"observed_at_ms":r["occurred_at_ms"]} for r in rows], "next_cursor":rows[-1]["seq"] if rows else after, "truncated":len(rows)==min(max(limit,1),200)}
