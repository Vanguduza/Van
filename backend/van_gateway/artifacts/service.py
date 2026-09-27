from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any

from van_gateway.storage.db import Store

from .models import ArtifactKind, ArtifactSensitivity, OwnerArtifact

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ArtifactServiceError(ValueError):
    pass


class ArtifactService:
    """Durable owner-facing projection over canonical evidence.

    The canonical source digest is immutable identity. Artifact rows may point at bytes or a
    preview, but secrets remain opaque references and are never copied into this table.
    """

    def __init__(self, store: Store) -> None:
        self.store = store

    @staticmethod
    def _row(row: Any) -> OwnerArtifact:
        return OwnerArtifact(
            artifact_id=row["artifact_id"], owner_id=row["owner_id"],
            project_id=row["project_id"], command_id=row["command_id"],
            mission_id=row["mission_id"], execution_id=row["execution_id"],
            kind=ArtifactKind(row["kind"]), title=row["title"], summary=row["summary"],
            mime_type=row["mime_type"], byte_size=row["byte_size"],
            canonical_source_type=row["canonical_source_type"],
            canonical_source_id=row["canonical_source_id"],
            canonical_source_digest=row["canonical_source_digest"],
            content_ref=row["content_ref"], preview_ref=row["preview_ref"],
            evidence_refs=json.loads(row["evidence_refs_json"] or "[]"),
            created_at_ms=int(row["created_at_ms"]),
            expires_at_ms=row["expires_at_ms"],
            sensitivity=ArtifactSensitivity(row["sensitivity"]),
        )

    async def create(
        self,
        *,
        kind: ArtifactKind,
        title: str,
        canonical_source_type: str,
        canonical_source_id: str,
        canonical_source_digest: str,
        summary: str = "",
        owner_id: str = "owner",
        project_id: str | None = None,
        command_id: str | None = None,
        mission_id: str | None = None,
        execution_id: str | None = None,
        mime_type: str | None = None,
        byte_size: int | None = None,
        content_ref: str | None = None,
        preview_ref: str | None = None,
        evidence_refs: list[str] | None = None,
        sensitivity: ArtifactSensitivity = ArtifactSensitivity.OWNER_PRIVATE,
        expires_at_ms: int | None = None,
        artifact_id: str | None = None,
        now_ms: int | None = None,
    ) -> OwnerArtifact:
        digest = canonical_source_digest.strip().lower()
        if not _SHA256.fullmatch(digest):
            raise ArtifactServiceError("artifact_source_digest_invalid")
        if not title.strip():
            raise ArtifactServiceError("artifact_title_required")
        if sensitivity is ArtifactSensitivity.SECRET_REF_ONLY and (content_ref or preview_ref):
            raise ArtifactServiceError("secret_ref_only_cannot_expose_content")
        now = int(time.time() * 1000) if now_ms is None else now_ms
        artifact = OwnerArtifact(
            artifact_id=artifact_id or f"art_{uuid.uuid4().hex}",
            owner_id=owner_id, project_id=project_id, command_id=command_id,
            mission_id=mission_id, execution_id=execution_id, kind=kind,
            title=title.strip(), summary=summary.strip(), mime_type=mime_type,
            byte_size=byte_size, canonical_source_type=canonical_source_type.strip(),
            canonical_source_id=canonical_source_id.strip(),
            canonical_source_digest=digest, content_ref=content_ref, preview_ref=preview_ref,
            evidence_refs=list(evidence_refs or []), created_at_ms=now,
            expires_at_ms=expires_at_ms, sensitivity=sensitivity,
        )
        await self.store.execute(
            """
            INSERT INTO owner_artifacts(
              artifact_id, owner_id, project_id, command_id, mission_id, execution_id,
              kind, title, summary, mime_type, byte_size, canonical_source_type,
              canonical_source_id, canonical_source_digest, content_ref, preview_ref,
              evidence_refs_json, sensitivity, created_at_ms, expires_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                artifact.artifact_id, artifact.owner_id, artifact.project_id,
                artifact.command_id, artifact.mission_id, artifact.execution_id,
                artifact.kind.value, artifact.title, artifact.summary, artifact.mime_type,
                artifact.byte_size, artifact.canonical_source_type,
                artifact.canonical_source_id, artifact.canonical_source_digest,
                artifact.content_ref, artifact.preview_ref, Store.dumps(artifact.evidence_refs),
                artifact.sensitivity.value, artifact.created_at_ms, artifact.expires_at_ms,
            ),
        )
        return artifact

    async def get(self, artifact_id: str) -> OwnerArtifact | None:
        row = await self.store.fetchone(
            "SELECT * FROM owner_artifacts WHERE artifact_id = ?", (artifact_id,)
        )
        return None if row is None else self._row(row)

    async def list(
        self,
        *,
        project_id: str | None = None,
        mission_id: str | None = None,
        kind: ArtifactKind | None = None,
        limit: int = 100,
    ) -> list[OwnerArtifact]:
        clauses, params = [], []
        if project_id is not None:
            clauses.append("project_id = ?"); params.append(project_id)
        if mission_id is not None:
            clauses.append("mission_id = ?"); params.append(mission_id)
        if kind is not None:
            clauses.append("kind = ?"); params.append(kind.value)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = await self.store.fetchall(
            f"SELECT * FROM owner_artifacts{where} ORDER BY created_at_ms DESC LIMIT ?",
            tuple(params + [max(1, min(limit, 500))]),
        )
        return [self._row(r) for r in rows]
