from __future__ import annotations

import time
import uuid
from typing import Any

from van_gateway.storage.db import Store


class AuditService:
    def __init__(self, store: Store) -> None:
        self.store = store

    @staticmethod
    def _normalize_evidence(value: dict[str, Any] | None) -> dict[str, Any] | None:
        """Preserve established audit keys while retaining richer Rev 3.1 evidence.

        Rev 3.1 records Project Truth as a nested object so provenance stays
        explicit. Older acceptance/evidence consumers already depend on the
        top-level ``truth_sha``/``repo_sha`` fields, so the audit boundary keeps
        both representations rather than forcing callers to fork the schema.
        """
        if value is None:
            return None
        normalized = dict(value)
        project_truth = normalized.get("project_truth")
        if isinstance(project_truth, dict):
            if "truth_sha" in project_truth:
                normalized.setdefault("truth_sha", project_truth.get("truth_sha"))
            if "repo_sha" in project_truth:
                normalized.setdefault("repo_sha", project_truth.get("repo_sha"))
        return normalized

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
        normalized_before = self._normalize_evidence(before)
        normalized_after = self._normalize_evidence(after)
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
                Store.dumps(normalized_before) if normalized_before is not None else None,
                Store.dumps(normalized_after) if normalized_after is not None else None,
                result,
                failure_reason,
                evidence_pointer,
                int(time.time()),
            ),
        )
        return audit_id
