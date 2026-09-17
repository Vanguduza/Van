from __future__ import annotations

import json
import time
from typing import Any

from pydantic import BaseModel

from van_gateway.action.models import ActionDefinition
from van_gateway.models import ActionClass, OriginChannel, PrincipalType
from van_gateway.storage.db import Store


class CommandAuthorityError(ValueError):
    pass


class CommandAuthorityRecord(BaseModel):
    command_id: str
    device_id: str
    principal_type: PrincipalType
    requested_by: str
    origin_channel: OriginChannel
    signed_action_class: ActionClass
    effective_action_class: ActionClass
    typed_action_id: str | None = None
    snapshot_id: str
    context_digest: str
    issued_at_unix: int
    expires_at_unix: int | None = None
    no_stale_replay: bool = False
    owner_approved: bool = False
    turn_id: str | None = None
    sealed_at_unix_ms: int


_RANK = {ActionClass.A1: 1, ActionClass.A2: 2, ActionClass.A3: 3, ActionClass.A4: 4, ActionClass.A5: 5}


class CommandAuthorityService:
    """Pre-dispatch authority record derived only from verified owner ingress.

    The record is intentionally stored in the existing durable ``runtime_meta``
    table so Rev 3.1 can bind Hermes action requests to the signed command and
    immutable context snapshot without inventing a second authentication plane.
    Raw signatures, approval tokens and secrets are never persisted here.
    """

    PREFIX = "command_authority:"

    def __init__(self, store: Store) -> None:
        self.store = store

    async def seal(self, record: CommandAuthorityRecord) -> CommandAuthorityRecord:
        key = self.PREFIX + record.command_id
        existing = await self.get(record.command_id)
        if existing is not None and existing != record:
            raise CommandAuthorityError("command_authority_conflict")
        await self.store.execute(
            """
            INSERT INTO runtime_meta(key, value, updated_at_unix_ms) VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at_unix_ms=excluded.updated_at_unix_ms
            """,
            (key, record.model_dump_json(), int(time.time() * 1000)),
        )
        return record

    async def get(self, command_id: str) -> CommandAuthorityRecord | None:
        row = await self.store.fetchone("SELECT value FROM runtime_meta WHERE key = ?", (self.PREFIX + command_id,))
        if row is None:
            return None
        return CommandAuthorityRecord.model_validate_json(str(row["value"]))

    async def erase(self, command_id: str) -> None:
        await self.store.execute("DELETE FROM runtime_meta WHERE key = ?", (self.PREFIX + command_id,))

    async def authorize_action(
        self,
        *,
        command_id: str,
        action: ActionDefinition,
        principal_type: PrincipalType,
        requested_by: str,
        snapshot_id: str | None,
        turn_id: str | None,
        now_unix: int | None = None,
    ) -> tuple[CommandAuthorityRecord, int]:
        record = await self.get(command_id)
        if record is None:
            raise CommandAuthorityError("command_authority_missing")
        now = int(time.time()) if now_unix is None else now_unix

        if record.principal_type != principal_type:
            raise CommandAuthorityError("principal_mismatch")
        if record.requested_by != requested_by:
            raise CommandAuthorityError("requested_by_mismatch")
        if record.turn_id != turn_id:
            raise CommandAuthorityError("turn_id_mismatch")
        if not snapshot_id or record.snapshot_id != snapshot_id:
            raise CommandAuthorityError("context_snapshot_mismatch")
        if record.expires_at_unix is not None and now >= record.expires_at_unix:
            raise CommandAuthorityError("command_authority_expired")

        device = await self.store.fetchone(
            "SELECT revoked_at_unix FROM devices WHERE device_id = ?",
            (record.device_id,),
        )
        if device is None or device["revoked_at_unix"] is not None:
            raise CommandAuthorityError("device_or_grant_revoked")

        if _RANK[action.action_class] > _RANK[record.effective_action_class]:
            raise CommandAuthorityError("action_class_escalation_denied")
        if record.typed_action_id is not None and action.action_id != record.typed_action_id:
            raise CommandAuthorityError("typed_action_mismatch")

        age = max(0, now - record.issued_at_unix)
        return record, age

    async def export_public(self, command_id: str) -> dict[str, Any] | None:
        record = await self.get(command_id)
        if record is None:
            return None
        data = json.loads(record.model_dump_json())
        data.pop("device_id", None)
        return data
