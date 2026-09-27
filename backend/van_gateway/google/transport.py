from __future__ import annotations

"""Google Workspace HTTP and OAuth transports.

Refresh tokens are encrypted by GoogleService. Live Workspace requests exchange
the refresh token for a short-lived access token before API calls. Test doubles
explicitly opt out of access-token exchange and never imply live Google state.
"""

import os
import base64
import binascii
from datetime import datetime, timezone
from typing import Any

import httpx


MAX_GMAIL_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_GMAIL_TEXT_BYTES = 1024 * 1024


class GoogleOutcomeUnknown(RuntimeError):
    """A write may have reached Google, so automatic retry is unsafe."""


def _decode_base64url(value: str, *, limit: int) -> bytes:
    if len(value) > ((limit * 4) // 3 + 16):
        raise RuntimeError("google_payload_too_large")
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, binascii.Error) as exc:
        raise RuntimeError("google_base64_invalid") from exc
    if len(raw) > limit:
        raise RuntimeError("google_payload_too_large")
    return raw


def _gmail_headers(payload: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in payload.get("headers") or []:
        if isinstance(item, dict) and item.get("name"):
            out[str(item["name"]).lower()] = str(item.get("value") or "")
    return out


def _normalise_gmail_message(message: dict[str, Any]) -> dict[str, Any]:
    payload = dict(message.get("payload") or {})
    metadata = _gmail_headers(payload)
    plain: list[str] = []
    html: list[str] = []
    attachments: list[dict[str, Any]] = []

    def visit(part: dict[str, Any], depth: int) -> None:
        if depth > 30:
            raise RuntimeError("gmail_mime_nesting_exceeded")
        body = dict(part.get("body") or {})
        filename = str(part.get("filename") or "")
        attachment_id = str(body.get("attachmentId") or "")
        mime = str(part.get("mimeType") or "")
        if filename and attachment_id:
            attachments.append({
                "message_id": str(message.get("id") or ""),
                "attachment_id": attachment_id,
                "filename": filename[:180],
                "mime_type": mime,
                "size": int(body.get("size") or 0),
            })
        data = body.get("data")
        if not filename and data and mime in {"text/plain", "text/html"}:
            decoded = _decode_base64url(str(data), limit=MAX_GMAIL_TEXT_BYTES).decode(
                "utf-8", errors="replace"
            )
            (plain if mime == "text/plain" else html).append(decoded)
        for child in part.get("parts") or []:
            if isinstance(child, dict):
                visit(child, depth + 1)

    visit(payload, 0)
    return {
        "id": str(message.get("id") or ""),
        "threadId": str(message.get("threadId") or ""),
        "labelIds": [str(x) for x in message.get("labelIds") or []],
        "snippet": str(message.get("snippet") or ""),
        "internalDate": str(message.get("internalDate") or ""),
        "from": metadata.get("from", ""),
        "to": metadata.get("to", ""),
        "subject": metadata.get("subject", ""),
        "date": metadata.get("date", ""),
        "body": "\n\n".join(plain) if plain else "\n\n".join(html),
        "body_format": "text/plain" if plain else ("text/html" if html else "snippet"),
        "attachments": attachments,
    }


class GoogleOAuthTokenClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self._client = client

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    async def access_token(self, refresh_token: str) -> str:
        if not self.configured:
            raise RuntimeError("google_oauth_client_unconfigured")
        client = self._client or httpx.AsyncClient(timeout=30.0)
        owns = self._client is None
        try:
            resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
                headers={"Accept": "application/json"},
            )
            if resp.status_code >= 400:
                raise RuntimeError(f"google_oauth_refresh_{resp.status_code}")
            data = resp.json()
            token = data.get("access_token")
            if not token:
                raise RuntimeError("google_oauth_access_token_missing")
            return str(token)
        finally:
            if owns:
                await client.aclose()


class GoogleHttpTransport:
    requires_access_token = True

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def _request(
        self,
        method: str,
        url: str,
        token: str,
        *,
        headers_extra: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> Any:
        client = self._client or httpx.AsyncClient(timeout=30.0)
        owns = self._client is None
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        if headers_extra:
            headers.update(headers_extra)
        try:
            resp = await client.request(method, url, headers=headers, **kwargs)
            if resp.status_code >= 400:
                raise RuntimeError(f"google_http_{resp.status_code}")
            if resp.status_code == 204 or not resp.content:
                return {}
            return resp.json()
        finally:
            if owns:
                await client.aclose()

    async def gmail_search(self, token: str, query: str) -> list[dict]:
        data = await self._request("GET", "https://gmail.googleapis.com/gmail/v1/users/me/messages", token, params={"q": query, "maxResults": 25})
        return data.get("messages", [])

    async def gmail_draft(self, token: str, thread_id: str, body: str) -> dict:
        return await self._request("POST", "https://gmail.googleapis.com/gmail/v1/users/me/drafts", token, json={"message": {"threadId": thread_id, "raw": body}})

    async def gmail_draft_get(self, token: str, draft_id: str) -> dict:
        return await self._request(
            "GET",
            f"https://gmail.googleapis.com/gmail/v1/users/me/drafts/{draft_id}",
            token,
            params={"format": "raw", "fields": "id,message(id,threadId,raw,labelIds)"},
        )

    async def gmail_send(self, token: str, draft_id: str) -> dict:
        return await self._request("POST", f"https://gmail.googleapis.com/gmail/v1/users/me/drafts/{draft_id}/send", token, json={})

    async def gmail_message_get(self, token: str, message_id: str) -> dict:
        return await self._request(
            "GET",
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}",
            token,
            params={"format": "minimal", "fields": "id,threadId,labelIds"},
        )

    async def gmail_thread_get(self, token: str, thread_id: str) -> dict:
        data = await self._request(
            "GET",
            f"https://gmail.googleapis.com/gmail/v1/users/me/threads/{thread_id}",
            token,
            params={"format": "full"},
        )
        return {
            "id": str(data.get("id") or thread_id),
            "historyId": str(data.get("historyId") or ""),
            "messages": [
                _normalise_gmail_message(dict(item))
                for item in data.get("messages") or []
                if isinstance(item, dict)
            ][:100],
        }

    async def gmail_attachment_get(
        self, token: str, message_id: str, attachment_id: str
    ) -> bytes:
        data = await self._request(
            "GET",
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}/attachments/{attachment_id}",
            token,
        )
        declared = int(data.get("size") or 0)
        if declared > MAX_GMAIL_ATTACHMENT_BYTES:
            raise RuntimeError("gmail_attachment_too_large")
        payload = _decode_base64url(
            str(data.get("data") or ""), limit=MAX_GMAIL_ATTACHMENT_BYTES
        )
        if declared and declared != len(payload):
            raise RuntimeError("gmail_attachment_size_mismatch")
        return payload

    async def calendar_agenda(self, token: str) -> list[dict]:
        data = await self._request("GET", "https://www.googleapis.com/calendar/v3/calendars/primary/events", token, params={"maxResults": 20, "singleEvents": "true", "orderBy": "startTime"})
        return data.get("items", [])

    async def calendar_reschedule(self, token: str, event_id: str, new_start_unix: int) -> dict:
        start = datetime.fromtimestamp(new_start_unix, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        return await self._request("PATCH", f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}", token, json={"start": {"dateTime": start}})

    async def calendar_event_get(self, token: str, event_id: str) -> dict:
        return await self._request(
            "GET",
            f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}",
            token,
            params={"fields": "id,summary,start,end,updated,status,etag,recurrence,attendees,description,location"},
        )

    async def calendar_event_review(self, token: str, event_id: str) -> dict:
        event = await self.calendar_event_get(token, event_id)
        version = str(event.get("etag") or "").strip()
        if not version:
            raise RuntimeError("google_calendar_event_version_missing")
        return {"event": event, "version": version}

    async def _calendar_write(
        self,
        method: str,
        url: str,
        token: str,
        *,
        body: dict[str, Any] | None = None,
        expected_version: str | None = None,
    ) -> dict:
        try:
            kwargs: dict[str, Any] = {}
            if body is not None:
                kwargs["json"] = body
            return await self._request(
                method, url, token,
                headers_extra=({"If-Match": expected_version} if expected_version else None),
                **kwargs,
            )
        except httpx.RequestError as exc:
            raise GoogleOutcomeUnknown("google_outcome_unknown") from exc
        except RuntimeError as exc:
            message = str(exc)
            if message in {"google_http_408"} or any(
                message == f"google_http_{code}" for code in range(500, 600)
            ):
                raise GoogleOutcomeUnknown("google_outcome_unknown") from exc
            raise

    @staticmethod
    def _calendar_body(raw: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "summary", "start", "end", "location", "description", "attendees", "recurrence"
        }
        body = {k: raw[k] for k in allowed if k in raw}
        if not str(body.get("summary") or "").strip():
            raise RuntimeError("google_calendar_summary_required")
        if not isinstance(body.get("start"), dict) or not isinstance(body.get("end"), dict):
            raise RuntimeError("google_calendar_time_range_required")
        attendees = body.get("attendees")
        if attendees is not None:
            if not isinstance(attendees, list) or len(attendees) > 100:
                raise RuntimeError("google_calendar_attendees_invalid")
        return body

    async def calendar_create(self, token: str, event: dict[str, Any]) -> dict:
        return await self._calendar_write(
            "POST",
            "https://www.googleapis.com/calendar/v3/calendars/primary/events?sendUpdates=all",
            token,
            body=self._calendar_body(event),
        )

    async def calendar_update(
        self, token: str, event_id: str, event: dict[str, Any], expected_version: str
    ) -> dict:
        if not expected_version.strip():
            raise RuntimeError("google_calendar_expected_version_required")
        return await self._calendar_write(
            "PATCH",
            f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}?sendUpdates=all",
            token,
            body=self._calendar_body(event),
            expected_version=expected_version,
        )

    async def calendar_delete(
        self, token: str, event_id: str, expected_version: str
    ) -> dict:
        if not expected_version.strip():
            raise RuntimeError("google_calendar_expected_version_required")
        return await self._calendar_write(
            "DELETE",
            f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}?sendUpdates=all",
            token,
            expected_version=expected_version,
        )

    async def drive_search(self, token: str, query: str) -> list[dict]:
        data = await self._request("GET", "https://www.googleapis.com/drive/v3/files", token, params={"q": query, "pageSize": 25, "fields": "files(id,name,mimeType,modifiedTime)"})
        return data.get("files", [])

    async def contacts_resolve(self, token: str, query: str) -> list[dict]:
        data = await self._request("GET", "https://people.googleapis.com/v1/people:searchContacts", token, params={"query": query, "readMask": "names,emailAddresses"})
        return data.get("results", [])

    async def tasks_list(self, token: str) -> list[dict]:
        data = await self._request("GET", "https://tasks.googleapis.com/tasks/v1/lists/@default/tasks", token)
        return data.get("items", [])


class FakeGoogleTransport:
    """Deterministic test double — never available accidentally in production.

    Pytest sets ``PYTEST_CURRENT_TEST`` while a test is executing. Outside tests,
    operators must explicitly set ``VAN_ALLOW_FAKE_GOOGLE_TRANSPORT=1`` before
    this transport can be constructed. This prevents the public test helper from
    silently replacing a live Google transport in normal runtime.
    """

    requires_access_token = False

    def __init__(self) -> None:
        if not os.getenv("PYTEST_CURRENT_TEST") and os.getenv("VAN_ALLOW_FAKE_GOOGLE_TRANSPORT") != "1":
            raise RuntimeError("fake_google_transport_disabled")
        self.calls: list[tuple[str, tuple]] = []
        self.drafts: dict[str, dict] = {}
        self.messages: dict[str, dict] = {}
        self.events: dict[str, dict] = {}

    async def gmail_search(self, token: str, query: str) -> list[dict]:
        self.calls.append(("gmail_search", (token[:4], query)))
        return [{"id": "m1", "threadId": "t1"}]

    async def gmail_draft(self, token: str, thread_id: str, body: str) -> dict:
        self.calls.append(("gmail_draft", (thread_id,)))
        result = {"id": "d1", "message": {"id": "md1", "threadId": thread_id, "raw": body}}
        self.drafts["d1"] = result
        return result

    async def gmail_draft_get(self, token: str, draft_id: str) -> dict:
        self.calls.append(("gmail_draft_get", (draft_id,)))
        return dict(self.drafts.get(draft_id, {"id": draft_id, "message": {}}))

    async def gmail_send(self, token: str, draft_id: str) -> dict:
        self.calls.append(("gmail_send", (draft_id,)))
        result = {"id": draft_id, "labelIds": ["SENT"]}
        self.messages[draft_id] = result
        return result

    async def gmail_message_get(self, token: str, message_id: str) -> dict:
        self.calls.append(("gmail_message_get", (message_id,)))
        return dict(self.messages.get(message_id, {"id": message_id, "labelIds": []}))

    async def gmail_thread_get(self, token: str, thread_id: str) -> dict:
        self.calls.append(("gmail_thread_get", (thread_id,)))
        return {"id": thread_id, "messages": [
            {"id": "m1", "threadId": thread_id, "subject": "Subject", "body": "Body", "attachments": []}
        ]}

    async def gmail_attachment_get(self, token: str, message_id: str, attachment_id: str) -> bytes:
        self.calls.append(("gmail_attachment_get", (message_id, attachment_id)))
        return b"%PDF-1.4\n% fake attachment"

    async def calendar_agenda(self, token: str) -> list[dict]:
        self.calls.append(("calendar_agenda", ()))
        return [{"id": "e1", "summary": "Supplier call"}]

    async def calendar_reschedule(self, token: str, event_id: str, new_start_unix: int) -> dict:
        self.calls.append(("calendar_reschedule", (event_id, new_start_unix)))
        start = datetime.fromtimestamp(new_start_unix, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        result = {"id": event_id, "updated": True, "start": {"dateTime": start}}
        self.events[event_id] = result
        return result

    async def calendar_event_get(self, token: str, event_id: str) -> dict:
        self.calls.append(("calendar_event_get", (event_id,)))
        return dict(self.events.get(event_id, {"id": event_id, "start": {}}))

    async def calendar_event_review(self, token: str, event_id: str) -> dict:
        event = await self.calendar_event_get(token, event_id)
        event.setdefault("etag", '"v1"')
        return {"event": event, "version": event["etag"]}

    async def calendar_create(self, token: str, event: dict[str, Any]) -> dict:
        self.calls.append(("calendar_create", (event,)))
        event_id = f"e{len(self.events) + 1}"
        result = {"id": event_id, "etag": '"v1"', **event}
        self.events[event_id] = result
        return result

    async def calendar_update(
        self, token: str, event_id: str, event: dict[str, Any], expected_version: str
    ) -> dict:
        self.calls.append(("calendar_update", (event_id, expected_version)))
        current = dict(self.events.get(event_id, {"id": event_id, "etag": '"v1"'}))
        if current.get("etag") != expected_version:
            raise RuntimeError("google_http_412")
        result = {**current, **event, "id": event_id, "etag": '"v2"'}
        self.events[event_id] = result
        return result

    async def calendar_delete(
        self, token: str, event_id: str, expected_version: str
    ) -> dict:
        self.calls.append(("calendar_delete", (event_id, expected_version)))
        current = dict(self.events.get(event_id, {"id": event_id, "etag": '"v1"'}))
        if current.get("etag") != expected_version:
            raise RuntimeError("google_http_412")
        self.events[event_id] = {"id": event_id, "status": "cancelled", "etag": expected_version}
        return {}

    async def drive_search(self, token: str, query: str) -> list[dict]:
        self.calls.append(("drive_search", (query,)))
        return [{"id": "f1", "name": "spec.pdf"}]

    async def contacts_resolve(self, token: str, query: str) -> list[dict]:
        self.calls.append(("contacts_resolve", (query,)))
        return [{"person": {"names": [{"displayName": query}]}}]

    async def tasks_list(self, token: str) -> list[dict]:
        self.calls.append(("tasks_list", ()))
        return [{"id": "task1", "title": "Follow up"}]
