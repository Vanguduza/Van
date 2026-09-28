from __future__ import annotations

import base64
import io
from email import policy
from email.parser import BytesParser

import httpx
import pytest
from cryptography.fernet import Fernet
from pypdf import PdfWriter

from van_gateway.artifacts.service import ArtifactService
from van_gateway.documents.service import DocumentService
from van_gateway.google.service import GoogleService
from van_gateway.google.transport import (
    FakeGoogleTransport, GoogleHttpTransport, GoogleOutcomeUnknown, _normalise_gmail_message,
)
from van_gateway.storage.db import Store


def b64url(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def test_gmail_full_message_normalizes_text_and_attachment_metadata():
    message = {
        "id": "m1", "threadId": "t1", "labelIds": ["INBOX"],
        "payload": {
            "headers": [
                {"name": "From", "value": "supplier@example.com"},
                {"name": "Subject", "value": "Form"},
            ],
            "parts": [
                {
                    "mimeType": "text/plain", "filename": "",
                    "body": {"data": b64url("Please complete the attached form")},
                },
                {
                    "mimeType": "application/pdf", "filename": "form.pdf",
                    "body": {"attachmentId": "att1", "size": 123},
                },
            ],
        },
    }
    result = _normalise_gmail_message(message)
    assert result["subject"] == "Form"
    assert result["body"] == "Please complete the attached form"
    assert result["attachments"] == [{
        "message_id": "m1", "attachment_id": "att1", "filename": "form.pdf",
        "mime_type": "application/pdf", "size": 123,
    }]


@pytest.mark.asyncio
async def test_calendar_update_binds_if_match_to_reviewed_version():
    seen = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["if_match"] = request.headers.get("if-match")
        return httpx.Response(200, json={
            "id": "e1", "etag": '"v2"', "summary": "New",
            "start": {"dateTime": "2026-09-27T10:00:00+02:00"},
            "end": {"dateTime": "2026-09-27T11:00:00+02:00"},
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        transport = GoogleHttpTransport(client)
        result = await transport.calendar_update(
            "token", "e1",
            {
                "summary": "New",
                "start": {"dateTime": "2026-09-27T10:00:00+02:00"},
                "end": {"dateTime": "2026-09-27T11:00:00+02:00"},
            },
            '"v1"',
        )
    assert seen["if_match"] == '"v1"'
    assert result["etag"] == '"v2"'


@pytest.mark.asyncio
async def test_ambiguous_calendar_server_failure_is_outcome_unknown():
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "unavailable"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        transport = GoogleHttpTransport(client)
        with pytest.raises(GoogleOutcomeUnknown):
            await transport.calendar_create(
                "token",
                {
                    "summary": "Supplier call",
                    "start": {"dateTime": "2026-09-27T10:00:00+02:00"},
                    "end": {"dateTime": "2026-09-27T11:00:00+02:00"},
                },
            )


@pytest.mark.asyncio
async def test_stale_calendar_version_is_definite_rejection_not_unknown():
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(412, json={"error": "precondition"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        transport = GoogleHttpTransport(client)
        with pytest.raises(RuntimeError, match="google_http_412"):
            await transport.calendar_update(
                "token", "e1",
                {
                    "summary": "Supplier call",
                    "start": {"dateTime": "2026-09-27T10:00:00+02:00"},
                    "end": {"dateTime": "2026-09-27T11:00:00+02:00"},
                },
                '"stale"',
            )


@pytest.mark.asyncio
async def test_gmail_reply_draft_binds_threading_headers():
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/threads/t1"):
            return httpx.Response(200, json={
                "id":"t1",
                "messages":[{
                    "id":"m1","threadId":"t1",
                    "payload":{"headers":[
                        {"name":"Message-ID","value":"<source@example.com>"},
                        {"name":"References","value":"<older@example.com>"},
                        {"name":"Subject","value":"Question"},
                        {"name":"From","value":"Supplier <supplier@example.com>"},
                    ]},
                }],
            })
        if request.url.path.endswith("/profile"):
            return httpx.Response(200, json={"emailAddress":"owner@example.com"})
        if request.url.path.endswith("/drafts"):
            body=__import__("json").loads(request.content)
            return httpx.Response(200, json={
                "id":"d1",
                "message":{"id":"md1","threadId":body["message"]["threadId"],"raw":body["message"]["raw"]},
            })
        raise AssertionError(str(request.url))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        transport=GoogleHttpTransport(client)
        result=await transport.gmail_draft("token","t1","Thanks")
    assert result["id"]=="d1"
    raw=result["message"]["raw"]
    decoded=base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8")
    assert "In-Reply-To: <source@example.com>" in decoded
    assert "References: <older@example.com> <source@example.com>" in decoded
    assert "To: supplier@example.com" in decoded
    assert "Subject: Re: Question" in decoded
    assert len(result["_van_raw_sha256"])==64



@pytest.mark.asyncio
async def test_filled_document_output_is_attached_to_reviewed_reply(tmp_path):
    """Acceptance #3: Document Fabric output, not the source, enters the reviewed MIME."""
    writer=PdfWriter()
    writer.add_blank_page(width=100,height=100)
    source_buf=io.BytesIO()
    writer.write(source_buf)

    store=Store(str(tmp_path/"google-document.sqlite3"))
    await store.migrate()
    documents=DocumentService(store,ArtifactService(store),root=str(tmp_path/"documents"))
    source=await documents.import_pdf(filename="permission.pdf",data=source_buf.getvalue())

    # A static PDF has no form fields, but filling an empty value map still produces a
    # distinct governed output copy. The Gmail adapter may attach only that output variant.
    filled=await documents.fill(source.document_id,{})
    output_bytes,_=await documents.bytes_for(source.document_id,"output")
    source_bytes,_=await documents.bytes_for(source.document_id,"source")
    assert filled.output_sha256 is not None
    assert output_bytes != b""
    assert source_bytes != b""

    service=GoogleService(
        store,Fernet.generate_key().decode(),
        transport=FakeGoogleTransport(),documents=documents,
    )
    await service.store_refresh_token(
        "owner","refresh-test",
        [
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.compose",
        ],
    )
    result=await service.gmail_draft(
        "thread-1","Attached is the completed form.",
        attachment_document_id=source.document_id,
    )
    raw=result["message"]["raw"]
    mime=BytesParser(policy=policy.default).parsebytes(
        base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    )
    attachments=list(mime.iter_attachments())
    assert len(attachments)==1
    assert attachments[0].get_filename()=="permission.pdf"
    assert attachments[0].get_content_type()=="application/pdf"
    assert attachments[0].get_payload(decode=True)==output_bytes
    assert len(result["_van_raw_sha256"])==64
