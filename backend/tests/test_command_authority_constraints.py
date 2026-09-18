from __future__ import annotations

import time

import pytest

from van_gateway.action.registry import BUILTIN_ACTIONS
from van_gateway.command.authority import (
    CommandAuthorityError,
    CommandAuthorityRecord,
    CommandAuthorityService,
)
from van_gateway.models import ActionClass, OriginChannel, PrincipalType
from van_gateway.storage.db import Store


@pytest.mark.asyncio
async def test_exact_action_parameter_constraints_cannot_be_swapped(tmp_path):
    store = Store(str(tmp_path / "authority.sqlite3"))
    await store.migrate()
    await store.execute(
        "INSERT INTO devices(device_id, public_key_pem, enrolled_at_unix, label) VALUES(?,?,?,?)",
        ("dev-1", "PEM", int(time.time()), "test"),
    )
    service = CommandAuthorityService(store)
    now = int(time.time())
    record = CommandAuthorityRecord(
        command_id="cmd-delete",
        device_id="dev-1",
        principal_type=PrincipalType.OWNER_DEVICE,
        requested_by="device:dev-1",
        origin_channel=OriginChannel.VOICE,
        signed_action_class=ActionClass.A1,
        effective_action_class=ActionClass.A4,
        typed_action_id="google.notebook.enterprise.delete",
        typed_parameter_constraints={"notebook_id": "Nb-1"},
        snapshot_id="snap-1",
        context_digest="digest",
        issued_at_unix=now,
        expires_at_unix=now + 60,
        no_stale_replay=True,
        owner_approved=True,
        turn_id="turn-1",
        sealed_at_unix_ms=now * 1000,
    )
    await service.seal(record)
    definition = next(
        item for item in BUILTIN_ACTIONS
        if item.action_id == "google.notebook.enterprise.delete"
    )

    authorized, _age = await service.authorize_action(
        command_id="cmd-delete",
        action=definition,
        principal_type=PrincipalType.OWNER_DEVICE,
        requested_by="device:dev-1",
        snapshot_id="snap-1",
        turn_id="turn-1",
        parameters={"notebook_id": "Nb-1"},
        now_unix=now + 1,
    )
    assert authorized.typed_parameter_constraints == {"notebook_id": "Nb-1"}

    with pytest.raises(CommandAuthorityError, match="typed_parameter_mismatch:notebook_id"):
        await service.authorize_action(
            command_id="cmd-delete",
            action=definition,
            principal_type=PrincipalType.OWNER_DEVICE,
            requested_by="device:dev-1",
            snapshot_id="snap-1",
            turn_id="turn-1",
            parameters={"notebook_id": "Nb-OTHER"},
            now_unix=now + 1,
        )