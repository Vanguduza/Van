from __future__ import annotations

"""Google Workspace HTTP and OAuth transports.

Refresh tokens are encrypted by GoogleService. Live Workspace requests exchange
the refresh token for a short-lived access token before API calls. Test doubles
explicitly opt out of access-token exchange and never imply live Google state.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

import httpx

from van_gateway.google.mail import message_snapshot, prepare_reply


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
                follow_redirects=False,
            )
            if resp.status_code >= 300:
                raise RuntimeError(f"google_oauth_refresh_{resp.status_code}")
            try:
                data = resp.json()
            except ValueError as exc:
                raise RuntimeError("google_oauth_response_malformed") from exc
            if not isinstance(data, dict):
                raise RuntimeError("google_oauth_response_malformed")
            token = data.get("access_token")
            if not isinstance(token, str) or not token:
                raise RuntimeError("google_oauth_access_token_missing")
            return token
        except httpx.TimeoutException as exc:
            raise RuntimeError("google_oauth_timeout") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError("google_oauth_unreachable") from exc
        finally:
            if owns:
                await client.aclose()


class GoogleHttpTransport:
    requires_access_token = True

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    @staticmethod
    def _items(data: dict, field: str) -> list[dict]:
        items = data.get(field, [])
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            raise RuntimeError("google_response_malformed")
        return items

    async def _request(self, method: str, url: str, token: str, **kwargs: Any) -> Any:
        client = self._client or httpx.AsyncClient(timeout=30.0)
        owns = self._client is None
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        headers.update(kwargs.pop("headers", {}))
        try:
            resp = await client.request(method, url, headers=headers, follow_redirects=False, **kwargs)
            if resp.status_code >= 300:
                raise RuntimeError(f"google_http_{resp.status_code}")
            if resp.status_code == 204 or not resp.content:
                return {}
            try:
                payload = resp.json()
            except ValueError as exc:
                raise RuntimeError("google_response_malformed") from exc
            if not isinstance(payload, dict):
                raise RuntimeError("google_response_malformed")
            return payload
        except httpx.TimeoutException as exc:
            raise RuntimeError("google_timeout") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError("google_unreachable") from exc
        finally:
            if owns:
                await client.aclose()

    async def gmail_search(self, token: str, query: str) -> list[dict]:
        data = await self._request("GET", "https://gmail.googleapis.com/gmail/v1/users/me/messages", token, params={"q": query, "maxResults": 25})
        return self._items(data, "messages")

    async def gmail_profile_get(self, token: str) -> dict:
        return await self._request("GET", "https://gmail.googleapis.com/gmail/v1/users/me/profile", token, params={"fields": "emailAddress"})

    async def gmail_thread_get(self, token: str, thread_id: str) -> dict:
        return await self._request(
            "GET", f"https://gmail.googleapis.com/gmail/v1/users/me/threads/{quote(thread_id, safe='')}", token,
            params={
                "format": "metadata", "metadataHeaders": ["From", "Reply-To", "Subject", "Message-ID", "References"],
                "fields": "id,messages(id,threadId,internalDate,labelIds,payload(headers(name,value)))",
            },
        )

    async def gmail_draft(self, token: str, thread_id: str, raw_message: str) -> dict:
        # The owner-facing service accepts plain text and prepares authoritative
        # reply metadata. This lower-level adapter accepts validated MIME only.
        message_snapshot(raw_message)
        return await self._request("POST", "https://gmail.googleapis.com/gmail/v1/users/me/drafts", token, json={"message": {"threadId": thread_id, "raw": raw_message}})

    async def gmail_draft_get(self, token: str, draft_id: str) -> dict:
        return await self._request(
            "GET",
            f"https://gmail.googleapis.com/gmail/v1/users/me/drafts/{quote(draft_id, safe='')}",
            token,
            params={"format": "raw", "fields": "id,message(id,threadId,raw,labelIds)"},
        )

    async def gmail_send(self, token: str, draft_id: str) -> dict:
        # Gmail's drafts.send accepts a Draft resource, not an /{id}/send route.
        return await self._request("POST", "https://gmail.googleapis.com/gmail/v1/users/me/drafts/send", token, json={"id": draft_id})

    async def gmail_message_send(self, token: str, raw_message: str, thread_id: str) -> dict:
        message_snapshot(raw_message)
        return await self._request(
            "POST", "https://gmail.googleapis.com/gmail/v1/users/me/messages/send", token,
            json={"raw": raw_message, "threadId": thread_id},
        )

    async def gmail_message_get(self, token: str, message_id: str) -> dict:
        return await self._request(
            "GET",
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{quote(message_id, safe='')}",
            token,
            params={"format": "raw", "fields": "id,threadId,labelIds,raw"},
        )

    async def calendar_agenda(self, token: str) -> list[dict]:
        data = await self._request("GET", "https://www.googleapis.com/calendar/v3/calendars/primary/events", token, params={"maxResults": 20, "singleEvents": "true", "orderBy": "startTime"})
        return self._items(data, "items")

    async def calendar_reschedule(self, token: str, event_id: str, new_start_unix: int) -> dict:
        # Moving just start leaves end in the past or silently shortens a meeting.
        # Read its duration and use its ETag so a concurrent edit cannot be overwritten.
        event = await self.calendar_event_get(token, event_id)
        if event.get("id") != event_id or event.get("status") == "cancelled":
            raise RuntimeError("google_calendar_event_not_active")
        etag = event.get("etag")
        if not isinstance(etag, str) or not etag:
            raise RuntimeError("google_calendar_event_etag_missing")
        try:
            old_start = datetime.fromisoformat(event["start"]["dateTime"].replace("Z", "+00:00"))
            old_end = datetime.fromisoformat(event["end"]["dateTime"].replace("Z", "+00:00"))
            if old_start.tzinfo is None or old_end.tzinfo is None or old_end <= old_start:
                raise ValueError("invalid timed interval")
            new_start = datetime.fromtimestamp(new_start_unix, tz=timezone.utc)
            new_end = new_start + (old_end - old_start)
        except (KeyError, TypeError, ValueError, OverflowError, OSError) as exc:
            # All-day events need an explicit date contract; seconds must not turn
            # them into timed meetings without the owner's intent.
            raise RuntimeError("google_calendar_timed_interval_required") from exc
        body = {
            "start": {"dateTime": new_start.isoformat().replace("+00:00", "Z")},
            "end": {"dateTime": new_end.isoformat().replace("+00:00", "Z")},
        }
        return await self._request(
            "PATCH", f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{quote(event_id, safe='')}",
            token, json=body, headers={"If-Match": etag},
        )

    async def calendar_event_get(self, token: str, event_id: str) -> dict:
        return await self._request(
            "GET",
            f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{quote(event_id, safe='')}",
            token,
            params={"fields": "id,etag,start,end,updated,status"},
        )

    async def drive_search(self, token: str, query: str) -> list[dict]:
        data = await self._request("GET", "https://www.googleapis.com/drive/v3/files", token, params={"q": query, "pageSize": 25, "fields": "files(id,name,mimeType,modifiedTime)"})
        return self._items(data, "files")

    async def contacts_resolve(self, token: str, query: str) -> list[dict]:
        data = await self._request("GET", "https://people.googleapis.com/v1/people:searchContacts", token, params={"query": query, "readMask": "names,emailAddresses"})
        return self._items(data, "results")

    async def tasks_list(self, token: str) -> list[dict]:
        data = await self._request("GET", "https://tasks.googleapis.com/tasks/v1/lists/@default/tasks", token)
        return self._items(data, "items")


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
        self.profile = {"emailAddress": "owner@example.invalid"}
        self.threads = {"t1": {
            "id": "t1", "messages": [{"id": "incoming-1", "threadId": "t1", "internalDate": "1000", "labelIds": ["INBOX"],
                "payload": {"headers": [{"name": "From", "value": "supplier@example.invalid"},
                    {"name": "Subject", "value": "Supplier update"}, {"name": "Message-ID", "value": "<incoming-1@example.invalid>"}]}}],
        }}
        prepared = prepare_reply(self.profile, self.threads["t1"], "t1", "Owner-approved reply")
        self.drafts["d1"] = {"id": "d1", "message": {"id": "md1", "threadId": "t1", "raw": prepared.raw}}

    async def gmail_search(self, token: str, query: str) -> list[dict]:
        self.calls.append(("gmail_search", (token[:4], query)))
        return [{"id": "m1", "threadId": "t1"}]

    async def gmail_profile_get(self, token: str) -> dict:
        self.calls.append(("gmail_profile_get", ()))
        return dict(self.profile)

    async def gmail_thread_get(self, token: str, thread_id: str) -> dict:
        self.calls.append(("gmail_thread_get", (thread_id,)))
        if thread_id not in self.threads:
            raise RuntimeError("google_http_404")
        return self.threads[thread_id]

    async def gmail_draft(self, token: str, thread_id: str, raw_message: str) -> dict:
        self.calls.append(("gmail_draft", (thread_id,)))
        message_snapshot(raw_message)
        result = {"id": "d1", "message": {"id": "md1", "threadId": thread_id, "raw": raw_message}}
        self.drafts["d1"] = result
        return result

    async def gmail_draft_get(self, token: str, draft_id: str) -> dict:
        self.calls.append(("gmail_draft_get", (draft_id,)))
        if draft_id not in self.drafts:
            raise RuntimeError("google_http_404")
        return dict(self.drafts[draft_id])

    async def gmail_send(self, token: str, draft_id: str) -> dict:
        self.calls.append(("gmail_send", (draft_id,)))
        if draft_id not in self.drafts:
            raise RuntimeError("google_http_404")
        result = {**self.drafts.pop(draft_id)["message"], "id": draft_id, "labelIds": ["SENT"]}
        self.messages[draft_id] = result
        return result

    async def gmail_message_send(self, token: str, raw_message: str, thread_id: str) -> dict:
        self.calls.append(("gmail_message_send", (thread_id,)))
        message_snapshot(raw_message)
        result = {"id": "sent-message-1", "threadId": thread_id, "raw": raw_message, "labelIds": ["SENT"]}
        self.messages[result["id"]] = result
        return result

    async def gmail_message_get(self, token: str, message_id: str) -> dict:
        self.calls.append(("gmail_message_get", (message_id,)))
        return dict(self.messages.get(message_id, {"id": message_id, "labelIds": []}))

    async def calendar_agenda(self, token: str) -> list[dict]:
        self.calls.append(("calendar_agenda", ()))
        return [{"id": "e1", "summary": "Supplier call"}]

    async def calendar_reschedule(self, token: str, event_id: str, new_start_unix: int) -> dict:
        self.calls.append(("calendar_reschedule", (event_id, new_start_unix)))
        start = datetime.fromtimestamp(new_start_unix, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        previous = self.events.get(event_id, {})
        duration = timedelta(hours=1)
        if previous.get("start", {}).get("dateTime") and previous.get("end", {}).get("dateTime"):
            duration = datetime.fromisoformat(previous["end"]["dateTime"].replace("Z", "+00:00")) - datetime.fromisoformat(previous["start"]["dateTime"].replace("Z", "+00:00"))
        end = (datetime.fromtimestamp(new_start_unix, tz=timezone.utc) + duration).isoformat().replace("+00:00", "Z")
        result = {"id": event_id, "updated": True, "start": {"dateTime": start}, "end": {"dateTime": end}}
        self.events[event_id] = result
        return result

    async def calendar_event_get(self, token: str, event_id: str) -> dict:
        self.calls.append(("calendar_event_get", (event_id,)))
        return dict(self.events.get(event_id, {"id": event_id, "start": {}}))

    async def drive_search(self, token: str, query: str) -> list[dict]:
        self.calls.append(("drive_search", (query,)))
        return [{"id": "f1", "name": "spec.pdf"}]

    async def contacts_resolve(self, token: str, query: str) -> list[dict]:
        self.calls.append(("contacts_resolve", (query,)))
        return [{"person": {"names": [{"displayName": query}]}}]

    async def tasks_list(self, token: str) -> list[dict]:
        self.calls.append(("tasks_list", ()))
        return [{"id": "task1", "title": "Follow up"}]
