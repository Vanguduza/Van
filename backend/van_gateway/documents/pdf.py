"""PDF v1 adapter for VAN Document Fabric.

Upstream provenance/reference:
- CopilotKit/openmuse
- commit 34b15bc80340e582fb8c25573646cfb0bbc5184d
- packages/integrations/src/pdf.ts
- MIT

This is a VAN-native implementation using pypdf. It preserves OpenMuse's useful
fail-closed behavior (encrypted/XFA/unsupported fields rejected, no embedded action
execution, immutable source) while keeping VAN evidence/authority outside this adapter.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError
from pypdf.generic import DictionaryObject, NameObject

from .models import DocumentField, DocumentFieldKind

MAX_PDF_BYTES = 10 * 1024 * 1024
MAX_PAGES = 500


class PdfDocumentError(ValueError):
    def __init__(self, code: str, detail: str | None = None) -> None:
        super().__init__(code if detail is None else f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class PdfInspection:
    page_count: int
    fields: tuple[DocumentField, ...]


def _object(value: Any) -> Any:
    return value.get_object() if hasattr(value, "get_object") else value


def _acroform(reader: PdfReader) -> DictionaryObject | None:
    root = _object(reader.trailer.get("/Root"))
    if not isinstance(root, DictionaryObject):
        return None
    acro = _object(root.get("/AcroForm"))
    return acro if isinstance(acro, DictionaryObject) else None


def _checkbox_on_value(field: Any) -> str:
    states = field.get("/_States_") if hasattr(field, "get") else None
    if states:
        for state in states:
            value = str(state)
            if value != "/Off":
                return value
    return "/Yes"


def _field_flags(field: Any) -> int:
    try:
        return int(field.get("/Ff", 0))
    except (TypeError, ValueError):
        return 0


def inspect_pdf(data: bytes) -> PdfInspection:
    if len(data) > MAX_PDF_BYTES:
        raise PdfDocumentError("PDF_TOO_LARGE")
    if not data.startswith(b"%PDF-"):
        raise PdfDocumentError("PDF_SIGNATURE_INVALID")
    try:
        reader = PdfReader(io.BytesIO(data), strict=True)
    except (PdfReadError, ValueError, TypeError) as exc:
        raise PdfDocumentError("PDF_INVALID") from exc
    if reader.is_encrypted:
        raise PdfDocumentError("PDF_ENCRYPTED_UNSUPPORTED")
    if len(reader.pages) > MAX_PAGES:
        raise PdfDocumentError("PDF_PAGE_LIMIT_EXCEEDED")
    acro = _acroform(reader)
    if acro is None:
        return PdfInspection(page_count=len(reader.pages), fields=())
    if "/XFA" in acro:
        raise PdfDocumentError("PDF_XFA_UNSUPPORTED")

    raw_fields = reader.get_fields() or {}
    fields: list[DocumentField] = []
    for name, field in raw_fields.items():
        field_type = str(field.get("/FT", ""))
        flags = _field_flags(field)
        if field_type == "/Tx":
            value = field.get("/V")
            fields.append(DocumentField(
                name=str(name), kind=DocumentFieldKind.TEXT,
                value=None if value is None else str(value),
            ))
            continue
        if field_type == "/Btn":
            # PDF button flags: bit 16 (1<<15) radio, bit 17 (1<<16) pushbutton.
            if flags & (1 << 15) or flags & (1 << 16):
                raise PdfDocumentError("PDF_FIELD_TYPE_UNSUPPORTED", str(name))
            on_value = _checkbox_on_value(field)
            value = str(field.get("/V", "/Off")) != "/Off"
            fields.append(DocumentField(
                name=str(name), kind=DocumentFieldKind.CHECKBOX,
                value=value, on_value=on_value,
            ))
            continue
        raise PdfDocumentError("PDF_FIELD_TYPE_UNSUPPORTED", f"{name}:{field_type or 'unknown'}")
    return PdfInspection(page_count=len(reader.pages), fields=tuple(fields))


def _strip_actions(writer: PdfWriter) -> None:
    root = writer.root_object
    root.pop(NameObject("/OpenAction"), None)
    root.pop(NameObject("/AA"), None)
    names = _object(root.get("/Names"))
    if isinstance(names, DictionaryObject):
        names.pop(NameObject("/JavaScript"), None)

    for page in writer.pages:
        page.pop(NameObject("/AA"), None)
        annotations = _object(page.get("/Annots"))
        if not annotations:
            continue
        for ref in annotations:
            annotation = _object(ref)
            if isinstance(annotation, DictionaryObject):
                annotation.pop(NameObject("/A"), None)
                annotation.pop(NameObject("/AA"), None)


def fill_pdf(data: bytes, values: dict[str, Any]) -> tuple[bytes, PdfInspection]:
    inspection = inspect_pdf(data)
    known = {field.name: field for field in inspection.fields}
    unknown = sorted(set(values) - set(known))
    if unknown:
        raise PdfDocumentError("PDF_FIELD_UNKNOWN", ",".join(unknown))

    mapped: dict[str, str] = {}
    for name, raw in values.items():
        field = known[name]
        if field.kind is DocumentFieldKind.TEXT:
            if isinstance(raw, (dict, list, tuple)):
                raise PdfDocumentError("PDF_FIELD_VALUE_INVALID", name)
            mapped[name] = "" if raw is None else str(raw)
        elif field.kind is DocumentFieldKind.CHECKBOX:
            if not isinstance(raw, bool):
                raise PdfDocumentError("PDF_FIELD_VALUE_INVALID", name)
            mapped[name] = field.on_value or "/Yes" if raw else "/Off"

    reader = PdfReader(io.BytesIO(data), strict=True)
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    _strip_actions(writer)
    if mapped:
        writer.update_page_form_field_values(
            None, mapped, auto_regenerate=False, flatten=False
        )
    out = io.BytesIO()
    writer.write(out)
    output = out.getvalue()
    # Re-parse output before publication; a writer success is not enough evidence.
    inspect_pdf(output)
    return output, inspection
