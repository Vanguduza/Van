from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import time
import uuid
from typing import Any

from van_gateway.artifacts.models import ArtifactKind, ArtifactSensitivity
from van_gateway.artifacts.service import ArtifactService
from van_gateway.storage.db import Store

from .models import DocumentField, DocumentFillProposal, DocumentRecord, DocumentStatus
from .pdf import PdfDocumentError, fill_pdf, inspect_pdf


class DocumentServiceError(ValueError):
    def __init__(self, code: str, detail: str | None = None) -> None:
        super().__init__(code if detail is None else f"{code}: {detail}")
        self.code = code
        self.detail = detail


class DocumentService:
    def __init__(self, store: Store, artifacts: ArtifactService, *, root: str | None = None) -> None:
        self.store = store
        self.artifacts = artifacts
        base = Path(store.path).resolve().parent
        self.root = Path(root).resolve() if root else base / "documents"
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.root, 0o700)
        except OSError:
            pass

    @staticmethod
    def _sha(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def _safe_name(name: str) -> str:
        cleaned = "".join(c for c in Path(name or "document.pdf").name if c.isalnum() or c in "._- ")
        return (cleaned.strip() or "document.pdf")[:180]

    def _path(self, document_id: str, variant: str) -> Path:
        return self.root / f"{document_id}.{variant}.pdf"

    @staticmethod
    def _record(row: Any) -> DocumentRecord:
        return DocumentRecord(
            document_id=row["document_id"], filename=row["filename"],
            mime_type=row["mime_type"], project_id=row["project_id"],
            command_id=row["command_id"], mission_id=row["mission_id"],
            execution_id=row["execution_id"], source_artifact_id=row["source_artifact_id"],
            output_artifact_id=row["output_artifact_id"], source_sha256=row["source_sha256"],
            output_sha256=row["output_sha256"], page_count=int(row["page_count"]),
            form_kind=row["form_kind"],
            fields=[DocumentField(**x) for x in json.loads(row["fields_json"] or "[]")],
            status=DocumentStatus(row["status"]), error_code=row["error_code"],
            created_at_ms=int(row["created_at_ms"]), updated_at_ms=int(row["updated_at_ms"]),
        )

    async def import_pdf(
        self,
        *,
        filename: str,
        data: bytes,
        project_id: str | None = None,
        command_id: str | None = None,
        mission_id: str | None = None,
        execution_id: str | None = None,
        now_ms: int | None = None,
    ) -> DocumentRecord:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        try:
            inspection = inspect_pdf(data)
        except PdfDocumentError as exc:
            raise DocumentServiceError(exc.code, exc.detail) from exc
        document_id = f"doc_{uuid.uuid4().hex}"
        source_sha = self._sha(data)
        source_path = self._path(document_id, "source")
        source_path.write_bytes(data)
        try:
            os.chmod(source_path, 0o600)
        except OSError:
            pass
        artifact = await self.artifacts.create(
            kind=ArtifactKind.PDF, title=self._safe_name(filename),
            summary=f"Imported PDF · {inspection.page_count} page(s)",
            project_id=project_id, command_id=command_id, mission_id=mission_id,
            execution_id=execution_id, mime_type="application/pdf", byte_size=len(data),
            canonical_source_type="document.source", canonical_source_id=document_id,
            canonical_source_digest=source_sha, content_ref=f"document:{document_id}:source",
            sensitivity=ArtifactSensitivity.OWNER_PRIVATE,
        )
        fields = [f.model_dump(mode="json") for f in inspection.fields]
        await self.store.execute(
            """
            INSERT INTO documents(
              document_id, filename, mime_type, project_id, command_id, mission_id, execution_id,
              source_artifact_id, output_artifact_id, source_path, output_path,
              source_sha256, output_sha256, page_count, form_kind, fields_json,
              status, error_code, created_at_ms, updated_at_ms
            ) VALUES (?, ?, 'application/pdf', ?, ?, ?, ?, ?, NULL, ?, NULL, ?, NULL, ?, ?, ?,
                      'IMPORTED', NULL, ?, ?)
            """,
            (
                document_id, self._safe_name(filename), project_id, command_id, mission_id,
                execution_id, artifact.artifact_id, str(source_path), source_sha,
                inspection.page_count, "ACROFORM" if inspection.fields else "STATIC",
                Store.dumps(fields), now, now,
            ),
        )
        record = await self.get(document_id)
        assert record is not None
        return record

    async def get(self, document_id: str) -> DocumentRecord | None:
        row = await self.store.fetchone("SELECT * FROM documents WHERE document_id = ?", (document_id,))
        return None if row is None else self._record(row)

    async def list(self, limit: int = 100) -> list[DocumentRecord]:
        rows = await self.store.fetchall(
            "SELECT * FROM documents ORDER BY created_at_ms DESC LIMIT ?",
            (max(1, min(limit, 500)),),
        )
        return [self._record(row) for row in rows]

    async def propose_fill(
        self, document_id: str, values: dict[str, Any]
    ) -> DocumentFillProposal:
        record = await self.get(document_id)
        if record is None:
            raise DocumentServiceError("DOCUMENT_UNKNOWN")
        known = {field.name: field for field in record.fields}
        unknown = sorted(set(values) - set(known))
        proposed: dict[str, Any] = {}
        missing: list[str] = []
        for name, field in known.items():
            if name in values:
                raw = values[name]
                if field.kind.value == "CHECKBOX":
                    if not isinstance(raw, bool):
                        raise DocumentServiceError("DOCUMENT_FIELD_VALUE_INVALID", name)
                    proposed[name] = raw
                else:
                    if isinstance(raw, (dict, list, tuple)):
                        raise DocumentServiceError("DOCUMENT_FIELD_VALUE_INVALID", name)
                    proposed[name] = "" if raw is None else str(raw)
            else:
                current = field.value
                if current in (None, "", False):
                    missing.append(name)
                proposed[name] = current
        canonical = {
            "document_id": document_id,
            "source_sha256": record.source_sha256,
            "proposed_values": proposed,
            "missing_fields": missing,
            "unknown_fields": unknown,
        }
        proposal_sha = hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return DocumentFillProposal(
            **canonical,
            proposal_sha256=proposal_sha,
            requires_owner_confirmation=True,
        )

    async def fill(self, document_id: str, values: dict[str, Any], *, now_ms: int | None = None) -> DocumentRecord:
        proposal = await self.propose_fill(document_id, values)
        if proposal.unknown_fields:
            raise DocumentServiceError("DOCUMENT_FIELD_UNKNOWN", ",".join(proposal.unknown_fields))
        row = await self.store.fetchone("SELECT * FROM documents WHERE document_id = ?", (document_id,))
        if row is None:
            raise DocumentServiceError("DOCUMENT_UNKNOWN")
        source_path = Path(str(row["source_path"]))
        if not source_path.exists():
            raise DocumentServiceError("DOCUMENT_SOURCE_MISSING")
        source = source_path.read_bytes()
        if self._sha(source) != str(row["source_sha256"]):
            raise DocumentServiceError("DOCUMENT_SOURCE_DIGEST_MISMATCH")
        try:
            output, _inspection = fill_pdf(source, values)
        except PdfDocumentError as exc:
            raise DocumentServiceError(exc.code, exc.detail) from exc
        output_sha = self._sha(output)
        output_path = self._path(document_id, f"filled-{output_sha[:16]}")
        output_path.write_bytes(output)
        try:
            os.chmod(output_path, 0o600)
        except OSError:
            pass
        artifact = await self.artifacts.create(
            kind=ArtifactKind.PDF, title=f"Filled · {row['filename']}",
            summary="Filled PDF copy; source preserved unchanged",
            project_id=row["project_id"], command_id=row["command_id"],
            mission_id=row["mission_id"], execution_id=row["execution_id"],
            mime_type="application/pdf", byte_size=len(output),
            canonical_source_type="document.output", canonical_source_id=document_id,
            canonical_source_digest=output_sha, content_ref=f"document:{document_id}:output",
            evidence_refs=[f"sha256:{row['source_sha256']}", f"sha256:{output_sha}"],
        )
        now = int(time.time() * 1000) if now_ms is None else now_ms
        await self.store.execute(
            """
            UPDATE documents
               SET output_artifact_id = ?, output_path = ?, output_sha256 = ?,
                   status = 'FILLED', error_code = NULL, updated_at_ms = ?
             WHERE document_id = ?
            """,
            (artifact.artifact_id, str(output_path), output_sha, now, document_id),
        )
        record = await self.get(document_id)
        assert record is not None
        return record

    async def bytes_for(self, document_id: str, variant: str) -> tuple[bytes, str]:
        row = await self.store.fetchone("SELECT * FROM documents WHERE document_id = ?", (document_id,))
        if row is None:
            raise DocumentServiceError("DOCUMENT_UNKNOWN")
        if variant == "source":
            path, expected = row["source_path"], row["source_sha256"]
        elif variant == "output":
            path, expected = row["output_path"], row["output_sha256"]
            if not path or not expected:
                raise DocumentServiceError("DOCUMENT_OUTPUT_UNAVAILABLE")
        else:
            raise DocumentServiceError("DOCUMENT_VARIANT_INVALID")
        data = Path(str(path)).read_bytes()
        if self._sha(data) != str(expected):
            raise DocumentServiceError("DOCUMENT_DIGEST_MISMATCH")
        return data, str(row["filename"])
