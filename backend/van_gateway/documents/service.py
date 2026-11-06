from __future__ import annotations

import hashlib
import asyncio
import re
import tempfile
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
    def __init__(self, code: str, detail: str | None = None, *, document_id: str | None = None, publication_id: str | None = None) -> None:
        super().__init__(code if detail is None else f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.document_id = document_id
        self.publication_id = publication_id


class DocumentService:
    def __init__(self, store: Store, artifacts: ArtifactService, *, root: str | None = None) -> None:
        self.store = store
        self.artifacts = artifacts
        base = Path(store.path).resolve().parent
        self.root = Path(root).resolve() if root else base / "documents"

    def _ensure_root(self) -> None:
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

    def _verified_bytes(self, path: str | Path, expected: str) -> bytes:
        path = Path(path)
        if path.is_symlink() or not path.resolve().is_relative_to(self.root.resolve()):
            raise DocumentServiceError("DOCUMENT_PATH_INVALID")
        if not path.is_file():
            raise DocumentServiceError("DOCUMENT_BYTES_MISSING")
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise DocumentServiceError("DOCUMENT_BYTES_UNREADABLE") from exc
        if self._sha(data) != expected:
            raise DocumentServiceError("DOCUMENT_DIGEST_MISMATCH")
        return data

    def _publish_bytes(self, path: Path, data: bytes) -> bool:
        """Publish private immutable bytes before the referencing SQL commit."""
        temporary = None
        linked = False
        try:
            with tempfile.NamedTemporaryFile(dir=self.root, prefix=".document-", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, path)
                linked = True
            except FileExistsError:
                if self._verified_bytes(path, self._sha(data)) != data:
                    raise DocumentServiceError("DOCUMENT_IMMUTABLE_BYTES_CONFLICT")
            if os.name != "nt":
                fd = os.open(self.root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
            return linked
        except BaseException:
            if linked:
                path.unlink(missing_ok=True)
            raise
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    async def _publication_recovery(self, *, publication_id: str, document_id: str,
                                    witness: str, commit_attempted: bool,
                                    path: Path | None, created: bool) -> bool:
        # The witness shares the metadata transaction. Its presence proves this
        # publication, rather than whichever document version is latest now.
        if commit_attempted:
            try:
                row = await self.store.fetchone("SELECT value FROM runtime_meta WHERE key=?", (publication_id,))
            except Exception as exc:
                raise DocumentServiceError("DOCUMENT_PUBLICATION_UNKNOWN", document_id=document_id,
                                           publication_id=publication_id) from exc
            if row is not None:
                if row["value"] != witness:
                    raise DocumentServiceError("DOCUMENT_PUBLICATION_UNKNOWN", document_id=document_id,
                                               publication_id=publication_id)
                return True
        if created and path is not None:
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                raise DocumentServiceError("DOCUMENT_PUBLICATION_UNKNOWN", document_id=document_id,
                                           publication_id=publication_id) from exc
        return False

    async def import_pdf(
        self, *, filename: str, data: bytes, project_id: str | None = None,
        command_id: str | None = None, mission_id: str | None = None,
        execution_id: str | None = None, now_ms: int | None = None,
    ) -> DocumentRecord:
        now = int(time.time()*1000) if now_ms is None else now_ms
        try:
            inspection = inspect_pdf(data)
        except PdfDocumentError as exc:
            raise DocumentServiceError(exc.code, exc.detail) from exc
        document_id = f"doc_{uuid.uuid4().hex}"
        publication_id = "document_publication:"+uuid.uuid4().hex
        source_sha = self._sha(data)
        self._ensure_root()
        source_path = self._path(document_id, "source")
        created = commit_attempted = False
        witness = ""
        result = None
        try:
            async with self.store.connection() as db:
                await db.execute("PRAGMA synchronous = FULL")
                await db.execute("BEGIN IMMEDIATE")
                created = self._publish_bytes(source_path, data)
                artifact = await self.artifacts.create(
                    kind=ArtifactKind.PDF, title=self._safe_name(filename),
                    summary=f"Imported PDF · {inspection.page_count} page(s)",
                    project_id=project_id, command_id=command_id, mission_id=mission_id,
                    execution_id=execution_id, mime_type="application/pdf", byte_size=len(data),
                    canonical_source_type="document.source", canonical_source_id=document_id,
                    canonical_source_digest=source_sha, content_ref=f"document:{document_id}:source",
                    sensitivity=ArtifactSensitivity.OWNER_PRIVATE, _db=db,
                )
                await db.execute(
                    """INSERT INTO documents(
                      document_id, filename, mime_type, project_id, command_id, mission_id, execution_id,
                      source_artifact_id, output_artifact_id, source_path, output_path,
                      source_sha256, output_sha256, page_count, form_kind, fields_json,
                      status, error_code, created_at_ms, updated_at_ms
                    ) VALUES (?, ?, 'application/pdf', ?, ?, ?, ?, ?, NULL, ?, NULL, ?, NULL, ?, ?, ?, 'IMPORTED', NULL, ?, ?)""",
                    (document_id, self._safe_name(filename), project_id, command_id, mission_id,
                     execution_id, artifact.artifact_id, str(source_path), source_sha,
                     inspection.page_count, "ACROFORM" if inspection.fields else "STATIC",
                     Store.dumps([field.model_dump(mode="json") for field in inspection.fields]), now, now),
                )
                row = await (await db.execute("SELECT * FROM documents WHERE document_id=?", (document_id,))).fetchone()
                result = self._record(row)
                witness = Store.dumps({"kind": "IMPORT", "document_id": document_id, "sha256": source_sha, "artifact_id": artifact.artifact_id})
                await db.execute("INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?)", (publication_id,witness,now))
                commit_attempted = True
                await db.commit()
            return result
        except BaseException as exc:
            committed = await self._publication_recovery(publication_id=publication_id, document_id=document_id,
                witness=witness, commit_attempted=commit_attempted, path=source_path, created=created)
            if committed and not isinstance(exc, asyncio.CancelledError):
                assert result is not None
                return result
            raise

    async def get(self, document_id: str) -> DocumentRecord | None:
        row = await self.store.fetchone("SELECT * FROM documents WHERE document_id = ?", (document_id,))
        return None if row is None else self._record(row)

    async def list(self, limit: int = 100) -> list[DocumentRecord]:
        rows = await self.store.fetchall(
            "SELECT * FROM documents ORDER BY created_at_ms DESC LIMIT ?",
            (max(1, min(limit, 500)),),
        )
        return [self._record(row) for row in rows]

    async def _published_output(self, document_id: str, digest: str, *, _db: Any | None = None) -> Any:
        sql = "SELECT expires_at_ms,sensitivity FROM owner_artifacts WHERE owner_id='owner' AND canonical_source_type='document.output' AND canonical_source_id=? AND canonical_source_digest=? LIMIT 1"
        if _db is None:
            artifact = await self.store.fetchone(sql,(document_id,digest))
        else:
            artifact = await (await _db.execute(sql,(document_id,digest))).fetchone()
        if artifact is None:
            raise DocumentServiceError("DOCUMENT_VERSION_UNKNOWN")
        if artifact["sensitivity"] == ArtifactSensitivity.SECRET_REF_ONLY.value:
            raise DocumentServiceError("DOCUMENT_VERSION_RESTRICTED")
        if artifact["expires_at_ms"] is not None and artifact["expires_at_ms"] <= int(time.time()*1000):
            raise DocumentServiceError("DOCUMENT_VERSION_EXPIRED")
        return artifact

    def _proposal(self, row: Any, values: dict[str, Any]) -> tuple[DocumentFillProposal, bytes]:
        source = self._verified_bytes(row["source_path"], row["source_sha256"])
        baseline = source
        baseline_sha = row["source_sha256"]
        if row["output_sha256"] is not None:
            baseline = self._verified_bytes(row["output_path"], row["output_sha256"])
            baseline_sha = row["output_sha256"]
        try:
            source_fields = {field.name: field for field in inspect_pdf(source).fields}
            known = {field.name: field for field in inspect_pdf(baseline).fields}
        except PdfDocumentError as exc:
            raise DocumentServiceError(exc.code, exc.detail) from exc
        if set(known) != set(source_fields) or any(known[name].kind != source_fields[name].kind for name in known):
            raise DocumentServiceError("DOCUMENT_FIELD_SCHEMA_MISMATCH")
        unknown = sorted(set(values)-set(known))
        proposed = {}
        missing = []
        for name, field in known.items():
            if name in values:
                raw = values[name]
                if field.kind.value == "CHECKBOX":
                    if not isinstance(raw, bool):
                        raise DocumentServiceError("DOCUMENT_FIELD_VALUE_INVALID", name)
                    proposed[name] = raw
                else:
                    if isinstance(raw, (dict,list,tuple)):
                        raise DocumentServiceError("DOCUMENT_FIELD_VALUE_INVALID", name)
                    proposed[name] = "" if raw is None else str(raw)
            else:
                proposed[name] = field.value
                if field.value in (None, "", False):
                    missing.append(name)
        missing = [name for name,value in proposed.items() if value in (None,"",False)]
        missing_required = [name for name in missing if known[name].required]
        canonical = {"document_id": row["document_id"], "source_sha256": row["source_sha256"],
                     "baseline_sha256": baseline_sha, "proposed_values": proposed,
                     "missing_fields": missing, "missing_required_fields": missing_required, "unknown_fields": unknown}
        proposal_sha = self._sha(json.dumps(canonical,sort_keys=True,separators=(",",":")).encode())
        return DocumentFillProposal(**canonical, proposal_sha256=proposal_sha, requires_owner_confirmation=True), source

    async def validate_context(self, document_id: str, **requested: str | None) -> None:
        row = await self.store.fetchone("SELECT * FROM documents WHERE document_id=?",(document_id,))
        if row is None:
            raise DocumentServiceError("DOCUMENT_UNKNOWN")
        for name in ("project_id","command_id","mission_id","execution_id"):
            if requested.get(name) is not None and requested[name] != row[name]:
                raise DocumentServiceError("DOCUMENT_CONTEXT_MISMATCH", name)

    async def propose_fill(self, document_id: str, values: dict[str, Any]) -> DocumentFillProposal:
        row = await self.store.fetchone("SELECT * FROM documents WHERE document_id=?", (document_id,))
        if row is None:
            raise DocumentServiceError("DOCUMENT_UNKNOWN")
        if row["output_sha256"] is not None:
            await self._published_output(document_id,row["output_sha256"])
        return self._proposal(row, values)[0]

    async def current_fields(self, document_id: str) -> list[DocumentField]:
        row = await self.store.fetchone("SELECT * FROM documents WHERE document_id=?", (document_id,))
        if row is None:
            raise DocumentServiceError("DOCUMENT_UNKNOWN")
        variant = "output" if row["output_sha256"] is not None else "source"
        data, _ = await self.bytes_for(document_id, variant)
        try:
            return list(inspect_pdf(data).fields)
        except PdfDocumentError as exc:
            raise DocumentServiceError(exc.code, exc.detail) from exc

    async def fill(self, document_id: str, values: dict[str, Any], *, now_ms: int | None = None,
                   expected_proposal_sha256: str | None = None) -> DocumentRecord:
        now = int(time.time()*1000) if now_ms is None else now_ms
        publication_id = "document_publication:"+uuid.uuid4().hex
        self._ensure_root()
        created = commit_attempted = False
        output_path = None
        witness = ""
        result = None
        try:
            async with self.store.connection() as db:
                await db.execute("PRAGMA synchronous = FULL")
                await db.execute("BEGIN IMMEDIATE")
                row = await (await db.execute("SELECT * FROM documents WHERE document_id=?", (document_id,))).fetchone()
                if row is None:
                    raise DocumentServiceError("DOCUMENT_UNKNOWN")
                if row["output_sha256"] is not None:
                    await self._published_output(document_id,row["output_sha256"],_db=db)
                proposal, source = self._proposal(row, values)
                if expected_proposal_sha256 is not None and proposal.proposal_sha256 != expected_proposal_sha256:
                    raise DocumentServiceError("DOCUMENT_PROPOSAL_STALE")
                if proposal.unknown_fields:
                    raise DocumentServiceError("DOCUMENT_FIELD_UNKNOWN", ",".join(proposal.unknown_fields))
                try:
                    output, _ = fill_pdf(source, proposal.proposed_values)
                    actual_fields = list(inspect_pdf(output).fields)
                except PdfDocumentError as exc:
                    raise DocumentServiceError(exc.code, exc.detail) from exc
                output_sha = self._sha(output)
                output_path = self._path(document_id, "filled-"+output_sha)
                created = self._publish_bytes(output_path, output)
                artifact = await self.artifacts.ensure_projection(
                    kind=ArtifactKind.PDF, title=f"Filled · {row['filename']}",
                    summary="Filled PDF copy; source preserved unchanged",
                    project_id=row["project_id"], command_id=row["command_id"],
                    mission_id=row["mission_id"], execution_id=row["execution_id"],
                    mime_type="application/pdf", byte_size=len(output),
                    canonical_source_type="document.output", canonical_source_id=document_id,
                    canonical_source_digest=output_sha, content_ref=f"document:{document_id}:output:{output_sha}",
                    evidence_refs=["sha256:"+row["source_sha256"],"sha256:"+output_sha], _db=db,
                )
                await db.execute(
                    "UPDATE documents SET output_artifact_id=?,output_path=?,output_sha256=?,fields_json=?,status='FILLED',error_code=NULL,updated_at_ms=? WHERE document_id=?",
                    (artifact.artifact_id,str(output_path),output_sha,
                     Store.dumps([field.model_dump(mode="json") for field in actual_fields]),now,document_id),
                )
                current = await (await db.execute("SELECT * FROM documents WHERE document_id=?", (document_id,))).fetchone()
                result = self._record(current)
                witness = Store.dumps({"kind":"FILL","document_id":document_id,"sha256":output_sha,"artifact_id":artifact.artifact_id})
                await db.execute("INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?)",(publication_id,witness,now))
                commit_attempted = True
                await db.commit()
            return result
        except BaseException as exc:
            committed = await self._publication_recovery(publication_id=publication_id, document_id=document_id,
                witness=witness, commit_attempted=commit_attempted, path=output_path, created=created)
            if committed and not isinstance(exc, asyncio.CancelledError):
                assert result is not None
                return result
            raise

    async def bytes_for(self, document_id: str, variant: str, *, sha256: str | None = None) -> tuple[bytes,str]:
        if sha256 is not None and (not isinstance(sha256,str) or re.fullmatch(r"[0-9a-f]{64}",sha256) is None):
            raise DocumentServiceError("DOCUMENT_VERSION_INVALID")
        row = await self.store.fetchone("SELECT * FROM documents WHERE document_id=?",(document_id,))
        if row is None:
            raise DocumentServiceError("DOCUMENT_UNKNOWN")
        if variant == "source":
            if sha256 is not None and sha256 != row["source_sha256"]:
                raise DocumentServiceError("DOCUMENT_VERSION_UNKNOWN")
            path, expected = row["source_path"],row["source_sha256"]
        elif variant == "output":
            expected = sha256 or row["output_sha256"]
            if expected is None:
                raise DocumentServiceError("DOCUMENT_OUTPUT_UNAVAILABLE")
            await self._published_output(document_id,expected)
            if expected == row["output_sha256"]:
                path = row["output_path"]
            else:
                path = self._path(document_id,"filled-"+expected)
                if not path.exists():
                    path = self._path(document_id,"filled-"+expected[:16])
        else:
            raise DocumentServiceError("DOCUMENT_VARIANT_INVALID")
        return self._verified_bytes(path,expected),str(row["filename"])
