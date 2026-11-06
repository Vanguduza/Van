"""Durable future-dispatch controls and bounded worker checkpoint reports.

The desired RUNNING/PAUSED fence is independent of mission lifecycle and action
authority. A worker receipt records a checkpoint or direction adoption; it does
not verify that an OS process stopped. Only an actual create-run receipt in
hermes_run_bindings can associate a worker with these controls.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import aiosqlite

from van_gateway.mission.models import TERMINAL_STATES
from van_gateway.storage.db import Store

_TERMINAL = frozenset(state.value for state in TERMINAL_STATES)
_OPERATIONS = frozenset({"PAUSE", "RESUME", "DIRECTION"})


class MissionControlError(ValueError):
    def __init__(self, code: str, detail: str | None = None) -> None:
        self.code = self.reason = code
        self.detail = detail or code
        super().__init__(code if detail is None else f"{code}: {detail}")


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False)


def _digest(payload: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _text(value: Any, name: str, maximum: int = 256) -> str:
    if (not isinstance(value, str) or not value or len(value) > maximum
            or value != value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise MissionControlError("MISSION_CONTROL_INVALID", f"Invalid {name}")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise MissionControlError("MISSION_CONTROL_INVALID", f"Invalid {name}") from exc
    return value


def _generation(value: Any) -> int:
    if type(value) is not int or value < 0 or value > 2**63 - 2:
        raise MissionControlError("MISSION_CONTROL_INVALID", "Invalid generation")
    return value


def _now(value: int | None) -> int:
    result = int(time.time() * 1000) if value is None else value
    if type(result) is not int or result < 0:
        raise MissionControlError("MISSION_CONTROL_INVALID", "Invalid timestamp")
    return result


async def _one(db: aiosqlite.Connection, sql: str, params: tuple = ()) -> aiosqlite.Row | None:
    async with db.execute(sql, params) as cursor:
        return await cursor.fetchone()


async def _all(db: aiosqlite.Connection, sql: str, params: tuple = ()) -> list[aiosqlite.Row]:
    async with db.execute(sql, params) as cursor:
        return await cursor.fetchall()


@asynccontextmanager
async def _transaction(store: Store, *, write: bool = True) -> AsyncIterator[aiosqlite.Connection]:
    async with store.connection() as db:
        await db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        try:
            yield db
            await db.commit()
        except BaseException:
            await db.rollback()
            raise


async def require_mission_dispatch(
    store: Store, mission_id: str, *, db: aiosqlite.Connection | None = None,
) -> None:
    """Check future admission; already executing work reaches its natural boundary.

    This helper grants no authority. Pass the existing writer connection for an
    atomic check at effect admission; it does not begin or commit that transaction.
    An already admitted operation may finish. Every later effect needs a fresh
    admission check.
    """
    _text(mission_id, "mission_id")
    sql = ("SELECT m.state,c.desired_execution FROM missions m "
           "LEFT JOIN mission_execution_controls c ON c.mission_id=m.mission_id WHERE m.mission_id=?")
    row = await _one(db, sql, (mission_id,)) if db is not None else await store.fetchone(sql, (mission_id,))
    if row is None:
        raise MissionControlError("MISSION_UNKNOWN")
    if row["state"] in _TERMINAL:
        raise MissionControlError("MISSION_CONTROL_TERMINAL")
    if row["desired_execution"] == "PAUSED":
        raise MissionControlError("MISSION_DISPATCH_PAUSED")


class MissionExecutionControlService:
    def __init__(self, store: Store) -> None:
        self.store = store

    @staticmethod
    async def _mission(db: aiosqlite.Connection, mission_id: str) -> aiosqlite.Row:
        row = await _one(db, "SELECT mission_id,state FROM missions WHERE mission_id=?", (mission_id,))
        if row is None:
            raise MissionControlError("MISSION_UNKNOWN")
        return row

    @staticmethod
    async def _active_owner(db: aiosqlite.Connection, requested_by: str) -> None:
        # This identity is constructed by the authenticated owner route, never a
        # public body claim. Recheck revocation under the same writer lock.
        if not requested_by.startswith("device:") or not requested_by[7:]:
            raise MissionControlError("MISSION_CONTROL_INVALID", "Owner device identity required")
        device = await _one(db, "SELECT revoked_at_unix FROM devices WHERE device_id=?",
                            (requested_by[7:],))
        if device is None or device["revoked_at_unix"] is not None:
            raise MissionControlError("MISSION_CONTROL_DEVICE_REVOKED")

    @staticmethod
    async def _execution(db: aiosqlite.Connection, mission_id: str, now: int) -> aiosqlite.Row:
        await db.execute(
            "INSERT OR IGNORE INTO mission_execution_controls(mission_id,updated_at_ms) VALUES (?,?)",
            (mission_id, now),
        )
        return await _one(db, "SELECT * FROM mission_execution_controls WHERE mission_id=?", (mission_id,))

    @staticmethod
    async def _binding(db: aiosqlite.Connection, mission_id: str) -> str | None:
        actual = await _one(db, "SELECT hermes_run_id FROM hermes_run_bindings WHERE mission_id=?",
                            (mission_id,))
        run_id = actual["hermes_run_id"] if actual else None
        pinned = await _one(db, "SELECT hermes_run_id FROM mission_execution_controls WHERE mission_id=?",
                            (mission_id,))
        if pinned and pinned["hermes_run_id"] is not None and pinned["hermes_run_id"] != run_id:
            raise MissionControlError("MISSION_CONTROL_BINDING_CONFLICT")
        inconsistent = await _one(
            db, "SELECT control_id FROM mission_control_requests WHERE mission_id=? "
            "AND hermes_run_id IS NOT NULL AND (hermes_run_id != ? OR ? IS NULL) LIMIT 1",
            (mission_id, run_id, run_id),
        )
        if inconsistent:
            raise MissionControlError("MISSION_CONTROL_BINDING_CONFLICT")
        return run_id

    @classmethod
    async def _bind(cls, db: aiosqlite.Connection, mission_id: str) -> str | None:
        run_id = await cls._binding(db, mission_id)
        if run_id is not None:
            await db.execute(
                "UPDATE mission_execution_controls SET hermes_run_id=? "
                "WHERE mission_id=? AND hermes_run_id IS NULL", (run_id, mission_id),
            )
            await db.execute(
                "UPDATE mission_control_requests SET hermes_run_id=? "
                "WHERE mission_id=? AND hermes_run_id IS NULL", (run_id, mission_id),
            )
        return run_id

    @staticmethod
    def _control(row: aiosqlite.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        result = json.loads(row["owner_receipt_json"])
        # The owner receipt stays immutable. This worker projection adds the
        # actual associated run and the original direction payload.
        result["hermes_run_id"] = row["hermes_run_id"]
        if row["operation"] == "DIRECTION":
            result["direction"] = row["direction"]
        return result

    async def request(
        self, *, mission_id: str, request_id: str, operation: str,
        expected_generation: int, requested_by: str, direction: str | None = None,
        reason: str = "", now_ms: int | None = None,
    ) -> dict[str, Any]:
        _text(mission_id, "mission_id")
        _text(request_id, "request_id", 128)
        _text(requested_by, "requested_by")
        if not isinstance(operation, str) or operation not in _OPERATIONS:
            raise MissionControlError("MISSION_CONTROL_INVALID", "Invalid operation")
        expected_generation = _generation(expected_generation)
        if not isinstance(reason, str) or len(reason) > 2000 or "\x00" in reason:
            raise MissionControlError("MISSION_CONTROL_INVALID", "Invalid reason")
        try:
            reason.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise MissionControlError("MISSION_CONTROL_INVALID", "Invalid reason") from exc
        if operation == "DIRECTION":
            if (not isinstance(direction, str) or not direction.strip() or len(direction) > 16000
                    or "\x00" in direction):
                raise MissionControlError("MISSION_CONTROL_INVALID", "Direction required")
            try:
                direction.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise MissionControlError("MISSION_CONTROL_INVALID", "Invalid direction") from exc
        elif direction is not None:
            raise MissionControlError("MISSION_CONTROL_INVALID", "Unexpected direction")
        payload = dict(mission_id=mission_id, request_id=request_id, operation=operation,
                       expected_generation=expected_generation, requested_by=requested_by,
                       direction=direction, reason=reason)
        payload_digest = _digest(payload)
        now = _now(now_ms)
        async with _transaction(self.store) as db:
            mission = await self._mission(db, mission_id)
            await self._active_owner(db, requested_by)
            existing = await _one(db, "SELECT * FROM mission_control_requests WHERE mission_id=? AND request_id=?",
                                  (mission_id, request_id))
            if existing:
                if existing["payload_digest"] != payload_digest:
                    raise MissionControlError("MISSION_CONTROL_REQUEST_CONFLICT")
                return json.loads(existing["owner_receipt_json"])
            if mission["state"] in _TERMINAL:
                raise MissionControlError("MISSION_CONTROL_TERMINAL")
            state = await self._execution(db, mission_id, now)
            if state["generation"] != expected_generation:
                raise MissionControlError("MISSION_CONTROL_GENERATION_CONFLICT")
            run_id = await self._bind(db, mission_id)
            generation = expected_generation + 1
            desired = {"PAUSE": "PAUSED", "RESUME": "RUNNING"}.get(operation, state["desired_execution"])
            control_id = "mctl_" + uuid.uuid4().hex
            receipt = dict(status="CONTROL_RECORDED", control_id=control_id, mission_id=mission_id,
                           request_id=request_id, operation=operation, expected_generation=expected_generation,
                           generation=generation, payload_digest=payload_digest, desired_execution=desired,
                           hermes_run_id=run_id, requested_by=requested_by, reason=reason, created_at_ms=now)
            if operation == "DIRECTION":
                receipt["direction"] = direction
            await db.execute(
                "INSERT INTO mission_control_requests(control_id,mission_id,request_id,operation,"
                "expected_generation,generation,payload_digest,canonical_payload_json,requested_by,direction,"
                "desired_execution,hermes_run_id,owner_receipt_json,created_at_ms) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (control_id, mission_id, request_id, operation, expected_generation, generation, payload_digest,
                 _canonical(payload), requested_by, direction, desired, run_id, _canonical(receipt), now),
            )
            await db.execute(
                "UPDATE mission_execution_controls SET generation=?,desired_execution=?,updated_at_ms=? "
                "WHERE mission_id=?", (generation, desired, now, mission_id),
            )
            return receipt

    async def get_request(self, mission_id: str, request_id: str) -> dict[str, Any]:
        _text(mission_id, "mission_id")
        _text(request_id, "request_id", 128)
        async with _transaction(self.store, write=False) as db:
            await self._mission(db, mission_id)
            row = await _one(db, "SELECT owner_receipt_json FROM mission_control_requests "
                             "WHERE mission_id=? AND request_id=?", (mission_id, request_id))
            if row is None:
                raise MissionControlError("MISSION_CONTROL_UNKNOWN")
            return json.loads(row["owner_receipt_json"])

    async def _read(self, db: aiosqlite.Connection, mission_id: str) -> dict[str, Any]:
        mission = await self._mission(db, mission_id)
        run_id = await self._binding(db, mission_id)
        state = await _one(db, "SELECT * FROM mission_execution_controls WHERE mission_id=?", (mission_id,))
        generation = state["generation"] if state else 0
        desired = state["desired_execution"] if state else "RUNNING"
        latest = await _one(db, "SELECT * FROM mission_control_requests WHERE mission_id=? "
                            "ORDER BY generation DESC LIMIT 1", (mission_id,))
        fence = await _one(db, "SELECT * FROM mission_control_requests WHERE mission_id=? "
                           "AND operation IN ('PAUSE','RESUME') ORDER BY generation DESC LIMIT 1", (mission_id,))
        report = await _one(db, "SELECT worker_ack_json FROM mission_control_requests WHERE mission_id=? "
                            "AND worker_ack_json IS NOT NULL ORDER BY acknowledged_at_ms DESC,generation DESC LIMIT 1",
                            (mission_id,))
        pending = await _all(db, "SELECT * FROM mission_control_requests WHERE mission_id=? "
                             "AND operation='DIRECTION' AND worker_ack_json IS NULL ORDER BY generation", (mission_id,))
        return dict(mission_id=mission_id, mission_state=mission["state"], generation=generation,
                    desired_execution=desired, dispatch_allowed=desired == "RUNNING" and mission["state"] not in _TERMINAL,
                    hermes_run_id=run_id, latest_control=self._control(latest), latest_fence_control=self._control(fence),
                    latest_worker_report=json.loads(report["worker_ack_json"]) if report else None,
                    pending_directions=[self._control(row) for row in pending])

    async def read(self, mission_id: str) -> dict[str, Any]:
        _text(mission_id, "mission_id")
        async with _transaction(self.store, write=False) as db:
            return await self._read(db, mission_id)

    async def poll(self, *, mission_id: str, hermes_run_id: str) -> dict[str, Any]:
        _text(mission_id, "mission_id")
        _text(hermes_run_id, "hermes_run_id")
        async with _transaction(self.store) as db:
            await self._mission(db, mission_id)
            actual = await self._binding(db, mission_id)
            if actual is None:
                raise MissionControlError("MISSION_CONTROL_RUN_UNBOUND")
            if actual != hermes_run_id:
                raise MissionControlError("MISSION_CONTROL_RUN_MISMATCH")
            await self._execution(db, mission_id, _now(None))
            await self._bind(db, mission_id)
            return await self._read(db, mission_id)

    async def acknowledge(
        self, *, mission_id: str, hermes_run_id: str, control_id: str, generation: int,
        payload_digest: str, checkpoint_ref: str, now_ms: int | None = None,
    ) -> dict[str, Any]:
        for name, value in (("mission_id", mission_id), ("hermes_run_id", hermes_run_id),
                            ("control_id", control_id), ("payload_digest", payload_digest)):
            _text(value, name)
        _text(checkpoint_ref, "checkpoint_ref", 2048)
        generation = _generation(generation)
        ack_body = dict(mission_id=mission_id, hermes_run_id=hermes_run_id, control_id=control_id,
                        generation=generation, payload_digest=payload_digest, checkpoint_ref=checkpoint_ref)
        ack_digest = _digest(ack_body)
        now = _now(now_ms)
        async with _transaction(self.store) as db:
            mission = await self._mission(db, mission_id)
            actual = await self._binding(db, mission_id)
            if actual is None:
                raise MissionControlError("MISSION_CONTROL_RUN_UNBOUND")
            if actual != hermes_run_id:
                raise MissionControlError("MISSION_CONTROL_RUN_MISMATCH")
            control = await _one(db, "SELECT * FROM mission_control_requests WHERE control_id=? AND mission_id=?",
                                 (control_id, mission_id))
            if control is None:
                raise MissionControlError("MISSION_CONTROL_UNKNOWN")
            if control["payload_digest"] != payload_digest:
                raise MissionControlError("MISSION_CONTROL_DIGEST_MISMATCH")
            if control["worker_ack_json"] is not None:
                if control["worker_ack_digest"] != ack_digest:
                    raise MissionControlError("MISSION_CONTROL_ACK_CONFLICT")
                return json.loads(control["worker_ack_json"])
            if mission["state"] in _TERMINAL:
                raise MissionControlError("MISSION_CONTROL_TERMINAL")
            state = await self._execution(db, mission_id, now)
            if generation != state["generation"]:
                raise MissionControlError("MISSION_CONTROL_GENERATION_CONFLICT")
            await self._bind(db, mission_id)
            if control["operation"] == "DIRECTION":
                oldest = await _one(db, "SELECT control_id FROM mission_control_requests WHERE mission_id=? "
                                    "AND operation='DIRECTION' AND worker_ack_json IS NULL ORDER BY generation LIMIT 1",
                                    (mission_id,))
                if oldest["control_id"] != control_id:
                    raise MissionControlError("MISSION_CONTROL_DIRECTION_ORDER")
                status = "DIRECTION_ADOPTION_RECORDED"
            else:
                latest = await _one(db, "SELECT control_id FROM mission_control_requests WHERE mission_id=? "
                                    "AND operation IN ('PAUSE','RESUME') ORDER BY generation DESC LIMIT 1", (mission_id,))
                if latest["control_id"] != control_id:
                    raise MissionControlError("MISSION_CONTROL_SUPERSEDED")
                status = "CHECKPOINT_RECORDED"
            receipt = dict(status=status, control_id=control_id, mission_id=mission_id,
                           hermes_run_id=hermes_run_id, generation=generation,
                           original_control_generation=control["generation"], payload_digest=payload_digest,
                           checkpoint_ref=checkpoint_ref, acknowledged_at_ms=now,
                           process_stopped_verified=False, authority_granted=False)
            await db.execute(
                "UPDATE mission_control_requests SET worker_ack_json=?,worker_ack_digest=?,checkpoint_ref=?,"
                "acknowledged_at_ms=? WHERE control_id=? AND worker_ack_json IS NULL",
                (_canonical(receipt), ack_digest, checkpoint_ref, now, control_id),
            )
            return receipt
