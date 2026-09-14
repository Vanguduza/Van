from __future__ import annotations

import time
import uuid
from typing import Any

from van_gateway.storage.db import Store


class AuditService:
    def __init__(self, store: Store) -> None:
        self.store = store

    async def record(
        self,
        *,
        result: str,
        command_id: str | None = None,
        device_id: str | None = None,
        project_id: str | None = None,
        capability: str | None = None,
        approval: str | None = None,
        model_delegate: str | None = None,
        tool: str | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        failure_reason: str | None = None,
        evidence_pointer: str | None = None,
    ) -> str:
        audit_id = str(uuid.uuid4())
        await self.store.execute(
            """
            INSERT INTO audit(
              id, command_id, device_id, project_id, capability, approval, model_delegate, tool,
              before_json, after_json, result, failure_reason, evidence_pointer, created_at_unix
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                audit_id,
                command_id,
                device_id,
                project_id,
                capability,
                approval,
                model_delegate,
                tool,
                Store.dumps(before) if before is not None else None,
                Store.dumps(after) if after is not None else None,
                result,
                failure_reason,
                evidence_pointer,
                int(time.time()),
            ),
        )
        return audit_id
