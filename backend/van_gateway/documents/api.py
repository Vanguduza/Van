from __future__ import annotations

from urllib.parse import quote
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile

from .models import FillDocumentRequest, DocumentRecord, DocumentFieldsView, DocumentFillProposal
from .service import DocumentService, DocumentServiceError


def build_document_router(service: DocumentService) -> APIRouter:
    router = APIRouter(prefix="/v1/documents", tags=["documents"])

    def fail(exc: DocumentServiceError) -> None:
        status = 404 if exc.code == "DOCUMENT_UNKNOWN" else 409
        if exc.code in {"PDF_TOO_LARGE"}:
            status = 413
        if exc.code in {"PDF_INVALID", "PDF_SIGNATURE_INVALID", "PDF_FIELD_FLAGS_INVALID"}:
            status = 422
        raise HTTPException(status_code=status, detail=exc.code) from exc

    @router.post("/import", response_model=DocumentRecord)
    async def import_document(
        file: UploadFile = File(...),
        project_id: str | None = Form(default=None),
        command_id: str | None = Form(default=None),
        mission_id: str | None = Form(default=None),
        execution_id: str | None = Form(default=None),
    ):
        if file.content_type not in {None, "", "application/pdf", "application/octet-stream"}:
            raise HTTPException(status_code=415, detail="document_mime_unsupported")
        data = await file.read(10 * 1024 * 1024 + 1)
        try:
            record = await service.import_pdf(
                filename=file.filename or "document.pdf", data=data, project_id=project_id,
                command_id=command_id, mission_id=mission_id, execution_id=execution_id,
            )
        except DocumentServiceError as exc:
            fail(exc)
        return record.model_dump(mode="json")

    @router.get("", response_model=list[DocumentRecord])
    async def list_documents(limit: int = Query(default=100, ge=1, le=500)):
        return [d.model_dump(mode="json") for d in await service.list(limit)]

    @router.get("/{document_id}", response_model=DocumentRecord)
    async def get_document(document_id: str):
        record = await service.get(document_id)
        if record is None:
            raise HTTPException(status_code=404, detail="document_unknown")
        return record.model_dump(mode="json")

    @router.get("/{document_id}/fields", response_model=DocumentFieldsView)
    async def document_fields(document_id: str):
        record = await service.get(document_id)
        if record is None:
            raise HTTPException(status_code=404, detail="document_unknown")
        return {"document_id": document_id, "fields": [f.model_dump(mode="json") for f in record.fields]}

    @router.post("/{document_id}/proposal", response_model=DocumentFillProposal)
    async def propose_document_fill(document_id: str, body: FillDocumentRequest):
        try:
            proposal = await service.propose_fill(document_id, body.values)
        except DocumentServiceError as exc:
            fail(exc)
        return proposal.model_dump(mode="json")

    @router.post("/{document_id}/fill", response_model=DocumentRecord)
    async def fill_document(document_id: str, body: FillDocumentRequest):
        try:
            record = await service.fill(document_id, body.values)
        except DocumentServiceError as exc:
            fail(exc)
        return record.model_dump(mode="json")

    @router.get("/{document_id}/content/{variant}", response_class=Response,
                responses={200: {"content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}}}})
    async def document_content(document_id: str, variant: Literal["source", "output"]):
        try:
            data, filename = await service.bytes_for(document_id, variant)
        except DocumentServiceError as exc:
            fail(exc)
        suffix = "filled.pdf" if variant == "output" else "source.pdf"
        safe = filename.rsplit(".", 1)[0][:120]
        fallback = "".join(char if char.isascii() and (char.isalnum() or char in "._- ") else "_" for char in safe) or "document"
        download_name = f"{safe}-{suffix}"
        disposition = f'attachment; filename="{fallback}-{suffix}"; filename*=UTF-8\'\'{quote(download_name, safe="")}'
        return Response(
            content=data, media_type="application/pdf",
            headers={
                "Content-Disposition": disposition,
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    return router
