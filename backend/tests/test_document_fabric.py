from __future__ import annotations

import io
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject, BooleanObject, DictionaryObject, FloatObject, NameObject,
    NumberObject, TextStringObject,
)

from van_gateway.artifacts.service import ArtifactService
from van_gateway.documents.pdf import PdfDocumentError, fill_pdf, inspect_pdf
from van_gateway.documents.service import DocumentService, DocumentServiceError
from van_gateway.storage.db import Store


def form_pdf() -> bytes:
    writer=PdfWriter()
    page=writer.add_blank_page(width=300,height=200)
    font=DictionaryObject({
        NameObject("/Type"):NameObject("/Font"),
        NameObject("/Subtype"):NameObject("/Type1"),
        NameObject("/BaseFont"):NameObject("/Helvetica"),
    })
    font_ref=writer._add_object(font)
    field=DictionaryObject({
        NameObject("/FT"):NameObject("/Tx"),
        NameObject("/T"):TextStringObject("owner_name"),
        NameObject("/V"):TextStringObject(""),
        NameObject("/Type"):NameObject("/Annot"),
        NameObject("/Subtype"):NameObject("/Widget"),
        NameObject("/Rect"):ArrayObject([FloatObject(20),FloatObject(100),FloatObject(220),FloatObject(130)]),
        NameObject("/F"):NumberObject(4),
        NameObject("/DA"):TextStringObject("/Helv 10 Tf 0 g"),
    })
    field_ref=writer._add_object(field)
    page[NameObject("/Annots")]=ArrayObject([field_ref])
    acro=DictionaryObject({
        NameObject("/Fields"):ArrayObject([field_ref]),
        NameObject("/NeedAppearances"):BooleanObject(True),
        NameObject("/DA"):TextStringObject("/Helv 10 Tf 0 g"),
        NameObject("/DR"):DictionaryObject({
            NameObject("/Font"):DictionaryObject({NameObject("/Helv"):font_ref})
        }),
    })
    writer._root_object[NameObject("/AcroForm")]=writer._add_object(acro)
    out=io.BytesIO(); writer.write(out); return out.getvalue()


def static_pdf() -> bytes:
    writer=PdfWriter(); writer.add_blank_page(width=100,height=100)
    out=io.BytesIO(); writer.write(out); return out.getvalue()


def test_pdf_adapter_inspects_and_fills_text_field_without_mutating_source():
    source=form_pdf()
    before=bytes(source)
    inspection=inspect_pdf(source)
    assert [f.name for f in inspection.fields]==["owner_name"]
    output,_=fill_pdf(source,{"owner_name":"Tapiwa"})
    assert source==before
    fields=PdfReader(io.BytesIO(output)).get_fields()
    assert str(fields["owner_name"]["/V"])=="Tapiwa"


def test_pdf_adapter_rejects_unknown_field():
    with pytest.raises(PdfDocumentError,match="PDF_FIELD_UNKNOWN"):
        fill_pdf(form_pdf(),{"not_a_field":"x"})


@pytest.mark.asyncio
async def test_document_service_creates_new_output_artifact_and_preserves_source(tmp_path):
    store=Store(str(tmp_path/"van.sqlite3")); await store.migrate()
    artifacts=ArtifactService(store)
    service=DocumentService(store,artifacts,root=str(tmp_path/"docs"))
    source=form_pdf()
    record=await service.import_pdf(filename="form.pdf",data=source,mission_id="m1")
    source_on_disk=(tmp_path/"docs"/f"{record.document_id}.source.pdf").read_bytes()
    filled=await service.fill(record.document_id,{"owner_name":"Tapiwa"})
    assert filled.status.value=="FILLED"
    assert filled.output_artifact_id
    assert filled.source_sha256!=filled.output_sha256
    assert source_on_disk==source
    output,_=await service.bytes_for(record.document_id,"output")
    assert str(PdfReader(io.BytesIO(output)).get_fields()["owner_name"]["/V"])=="Tapiwa"


@pytest.mark.asyncio
async def test_document_service_rejects_non_pdf(tmp_path):
    store=Store(str(tmp_path/"van.sqlite3")); await store.migrate()
    service=DocumentService(store,ArtifactService(store),root=str(tmp_path/"docs"))
    with pytest.raises(DocumentServiceError,match="PDF_SIGNATURE_INVALID"):
        await service.import_pdf(filename="bad.pdf",data=b"not pdf")


@pytest.mark.asyncio
async def test_document_fill_proposal_is_source_digest_bound(tmp_path):
    store=Store(str(tmp_path/"van.sqlite3")); await store.migrate()
    service=DocumentService(store,ArtifactService(store),root=str(tmp_path/"docs"))
    record=await service.import_pdf(filename="form.pdf",data=form_pdf())
    proposal=await service.propose_fill(record.document_id,{"owner_name":"Tapiwa"})
    assert proposal.document_id==record.document_id
    assert proposal.source_sha256==record.source_sha256
    assert proposal.proposed_values["owner_name"]=="Tapiwa"
    assert proposal.missing_fields==[]
    assert len(proposal.proposal_sha256)==64
    assert proposal.requires_owner_confirmation is True
