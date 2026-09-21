from __future__ import annotations

"""Google Workspace HTTP and OAuth transports.

Refresh tokens are encrypted by GoogleService. Live Workspace requests exchange
the refresh token for a short-lived access token before API calls. Test doubles
explicitly opt out of access-token exchange and never imply live Google state.
"""

import os
from datetime import datetime, timezone
from typing import Any

import httpx


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

    async def _request(self, method: str, url: str, token: str, **kwargs: Any) -> Any:
        client = self._client or httpx.AsyncClient(timeout=30.0)
        owns = self._client is None
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
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
            params={"fields": "id,start,end,updated,status"},
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

    async def drive_search(self, token: str, query: str) -> list[dict]:
        self.calls.append(("drive_search", (query,)))
        return [{"id": "f1", "name": "spec.pdf"}]

    async def contacts_resolve(self, token: str, query: str) -> list[dict]:
        self.calls.append(("contacts_resolve", (query,)))
        return [{"person": {"names": [{"displayName": query}]}}]

    async def tasks_list(self, token: str) -> list[dict]:
        self.calls.append(("tasks_list", ()))
        return [{"id": "task1", "title": "Follow up"}]
