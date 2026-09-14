from __future__ import annotations

"""Google Workspace HTTP transport.

Requires live OAuth access token obtained via refresh. Without credentials, callers
must fail closed — this module never invents mailbox/calendar data.
"""

from datetime import datetime, timezone
from typing import Any

import httpx


class GoogleHttpTransport:
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
        data = await self._request(
            "GET",
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            token,
            params={"q": query, "maxResults": 25},
        )
        return data.get("messages", [])

    async def gmail_draft(self, token: str, thread_id: str, body: str) -> dict:
        return await self._request(
            "POST",
            "https://gmail.googleapis.com/gmail/v1/users/me/drafts",
            token,
            json={"message": {"threadId": thread_id, "raw": body}},
        )

    async def gmail_send(self, token: str, draft_id: str) -> dict:
        return await self._request(
            "POST",
            f"https://gmail.googleapis.com/gmail/v1/users/me/drafts/{draft_id}/send",
            token,
            json={},
        )

    async def calendar_agenda(self, token: str) -> list[dict]:
        data = await self._request(
            "GET",
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            token,
            params={"maxResults": 20, "singleEvents": "true", "orderBy": "startTime"},
        )
        return data.get("items", [])

    async def calendar_reschedule(self, token: str, event_id: str, new_start_unix: int) -> dict:
        start = datetime.fromtimestamp(new_start_unix, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        return await self._request(
            "PATCH",
            f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}",
            token,
            json={"start": {"dateTime": start}},
        )

    async def drive_search(self, token: str, query: str) -> list[dict]:
        data = await self._request(
            "GET",
            "https://www.googleapis.com/drive/v3/files",
            token,
            params={"q": query, "pageSize": 25, "fields": "files(id,name,mimeType,modifiedTime)"},
        )
        return data.get("files", [])

    async def contacts_resolve(self, token: str, query: str) -> list[dict]:
        data = await self._request(
            "GET",
            "https://people.googleapis.com/v1/people:searchContacts",
            token,
            params={"query": query, "readMask": "names,emailAddresses"},
        )
        return data.get("results", [])

    async def tasks_list(self, token: str) -> list[dict]:
        data = await self._request(
            "GET",
            "https://tasks.googleapis.com/tasks/v1/lists/@default/tasks",
            token,
        )
        return data.get("items", [])


class FakeGoogleTransport:
    """Deterministic test double — not presented as live Google state."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []

    async def gmail_search(self, token: str, query: str) -> list[dict]:
        self.calls.append(("gmail_search", (token[:4], query)))
        return [{"id": "m1", "threadId": "t1"}]

    async def gmail_draft(self, token: str, thread_id: str, body: str) -> dict:
        self.calls.append(("gmail_draft", (thread_id,)))
        return {"id": "d1", "message": {"threadId": thread_id}}

    async def gmail_send(self, token: str, draft_id: str) -> dict:
        self.calls.append(("gmail_send", (draft_id,)))
        return {"id": draft_id, "labelIds": ["SENT"]}

    async def calendar_agenda(self, token: str) -> list[dict]:
        self.calls.append(("calendar_agenda", ()))
        return [{"id": "e1", "summary": "Supplier call"}]

    async def calendar_reschedule(self, token: str, event_id: str, new_start_unix: int) -> dict:
        self.calls.append(("calendar_reschedule", (event_id, new_start_unix)))
        return {"id": event_id, "updated": True}

    async def drive_search(self, token: str, query: str) -> list[dict]:
        self.calls.append(("drive_search", (query,)))
        return [{"id": "f1", "name": "spec.pdf"}]

    async def contacts_resolve(self, token: str, query: str) -> list[dict]:
        self.calls.append(("contacts_resolve", (query,)))
        return [{"person": {"names": [{"displayName": query}]}}]

    async def tasks_list(self, token: str) -> list[dict]:
        self.calls.append(("tasks_list", ()))
        return [{"id": "task1", "title": "Follow up"}]
