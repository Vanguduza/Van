from __future__ import annotations

import base64

import httpx
import pytest

from van_gateway.google.transport import (
    GoogleHttpTransport, GoogleOutcomeUnknown, _normalise_gmail_message,
)


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
