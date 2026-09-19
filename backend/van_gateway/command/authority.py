from __future__ import annotations

import json
import time
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from van_gateway.action.models import ActionDefinition
from van_gateway.models import ActionClass, OriginChannel, PrincipalType
from van_gateway.storage.db import Store


class CommandAuthorityError(ValueError):
    pass


class AuthoritySource(str, Enum):
    OWNER_COMMAND = "OWNER_COMMAND"
    STANDING_AUTOMATION = "STANDING_AUTOMATION"


class CommandAuthorityRecord(BaseModel):
    command_id: str
    device_id: str
    principal_type: PrincipalType
    requested_by: str
    origin_channel: OriginChannel
    signed_action_class: ActionClass
    effective_action_class: ActionClass
    typed_action_id: str | None = None
    typed_parameter_constraints: dict[str, Any] = Field(default_factory=dict)
    snapshot_id: str
    context_digest: str
    issued_at_unix: int
    expires_at_unix: int | None = None
    no_stale_replay: bool = False
    owner_approved: bool = False
    turn_id: str | None = None
    sealed_at_unix_ms: int
    authority_source: AuthoritySource = AuthoritySource.OWNER_COMMAND
    source_authority_id: str | None = None
    source_command_id: str | None = None


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
        parameters: dict[str, Any] | None = None,
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
        submitted_parameters = parameters or {}
        for key, expected in record.typed_parameter_constraints.items():
            if key not in submitted_parameters or submitted_parameters[key] != expected:
                raise CommandAuthorityError(f"typed_parameter_mismatch:{key}")
        if record.typed_action_id is not None:
            self._assert_parameters_fully_sealed(action, record, submitted_parameters)

        age = max(0, now - record.issued_at_unix)
        return record, age

    @staticmethod
    def _assert_parameters_fully_sealed(
        action: ActionDefinition,
        record: CommandAuthorityRecord,
        submitted: dict[str, Any],
    ) -> None:
        """For a state-changing action, the owner sealed *which* thing, not just what to do.

        P1-GOOG-002 — the check above only required the sealed parameters to be a subset of
        the submitted ones. `google.notebook.note.create` is A3, requires `notebook_id`, and
        the resolver sealed only `title`, so `notebook_id` was unconstrained: Hermes chose
        which of the owner's notebooks the note landed in, and the sealed authority record
        said nothing about it. The owner approved "make a note called X"; what happened was
        "make a note called X in a notebook the model picked".

        Two rules, both only for A3 and above — an A1 read may legitimately carry paging or
        filter arguments nobody sealed, and refusing those would break every read path:

        * every parameter the action *requires* must be sealed;
        * no parameter outside the sealed set may be submitted.

        The second is the one that matters. Without it, sealing `notebook_id` would stop
        Hermes overriding the notebook but not stop it adding a `parent_folder` or a
        `share_with` the owner never saw.
        """
        if _RANK[action.action_class] < _RANK[ActionClass.A3]:
            return
        required = [str(name) for name in (action.parameter_schema or {}).get("required", [])]
        unsealed_required = [
            name for name in required if name not in record.typed_parameter_constraints
        ]
        if unsealed_required:
            raise CommandAuthorityError(
                f"unsealed_required_parameter:{unsealed_required[0]}"
            )
        extra = sorted(set(submitted) - set(record.typed_parameter_constraints))
        if extra:
            raise CommandAuthorityError(f"unsealed_parameter:{extra[0]}")

    async def export_public(self, command_id: str) -> dict[str, Any] | None:
        record = await self.get(command_id)
        if record is None:
            return None
        data = json.loads(record.model_dump_json())
        data.pop("device_id", None)
        return data