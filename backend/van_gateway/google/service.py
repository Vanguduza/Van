from __future__ import annotations

import base64
import hashlib
import time
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from van_gateway.models import ActionClass, DegradedCode, GoogleConnectionStatus
from van_gateway.storage.db import Store


NARROW_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/contacts.readonly",
    "https://www.googleapis.com/auth/tasks",
]


class GoogleAuthError(Exception):
    pass


class GoogleService:
    """OAuth token vault + capability-mediated Google Workspace operations.

    Tokens are encrypted at rest and never returned to model prompts.
    Without a Fernet key / refresh token, all Google ops fail closed with degraded status.
    Live HTTP calls require credentials; unit tests use the in-memory fake transport.
    """

    def __init__(self, store: Store, fernet_key: str, transport: Any | None = None) -> None:
        self.store = store
        self.transport = transport
        self._fernet: Fernet | None = None
        if fernet_key:
            try:
                self._fernet = Fernet(fernet_key.encode("utf-8"))
            except (ValueError, InvalidToken, Exception):
                self._fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(fernet_key.encode()).digest()))

    def ready(self) -> bool:
        return self._fernet is not None

    async def status(self, owner_id: str = "owner") -> GoogleConnectionStatus:
        if not self.ready():
            return GoogleConnectionStatus(
                connected=False,
                degraded=[DegradedCode.GOOGLE_TOKEN_EXPIRED.value],
                services={s: "unavailable" for s in ("gmail", "calendar", "drive", "contacts", "tasks")},
            )
        row = await self.store.fetchone(
            "SELECT encrypted_refresh_token, scopes_json, status FROM google_connections WHERE owner_id = ?",
            (owner_id,),
        )
        if row is None or row["status"] != "active":
            return GoogleConnectionStatus(
                connected=False,
                degraded=[DegradedCode.GOOGLE_TOKEN_EXPIRED.value],
                services={s: "disconnected" for s in ("gmail", "calendar", "drive", "contacts", "tasks")},
            )
        scopes = __import__("json").loads(row["scopes_json"])
        services = {
            "gmail": "ok" if any("gmail" in s for s in scopes) else "missing_scope",
            "calendar": "ok" if any("calendar" in s for s in scopes) else "missing_scope",
            "drive": "ok" if any("drive" in s for s in scopes) else "missing_scope",
            "contacts": "ok" if any("contacts" in s for s in scopes) else "missing_scope",
            "tasks": "ok" if any("tasks" in s for s in scopes) else "missing_scope",
        }
        degraded = []
        if any(v != "ok" for v in services.values()):
            degraded.append(DegradedCode.GOOGLE_PARTIAL.value)
        return GoogleConnectionStatus(connected=True, scopes=scopes, services=services, degraded=degraded)

    async def store_refresh_token(self, owner_id: str, refresh_token: str, scopes: list[str]) -> None:
        if not self._fernet:
            raise GoogleAuthError("encryption_key_missing")
        for scope in scopes:
            if scope not in NARROW_SCOPES:
                raise GoogleAuthError(f"scope_not_allowed:{scope}")
        token = self._fernet.encrypt(refresh_token.encode("utf-8")).decode("ascii")
        now = int(time.time())
        await self.store.execute(
            """
            INSERT INTO google_connections(owner_id, encrypted_refresh_token, scopes_json, status, updated_at_unix)
            VALUES (?, ?, ?, 'active', ?)
            ON CONFLICT(owner_id) DO UPDATE SET
              encrypted_refresh_token=excluded.encrypted_refresh_token,
              scopes_json=excluded.scopes_json,
              status='active',
              updated_at_unix=excluded.updated_at_unix
            """,
            (owner_id, token, Store.dumps(scopes), now),
        )

    async def revoke(self, owner_id: str = "owner") -> None:
        now = int(time.time())
        await self.store.execute(
            "UPDATE google_connections SET status = 'revoked', encrypted_refresh_token = '', updated_at_unix = ? WHERE owner_id = ?",
            (now, owner_id),
        )

    async def _refresh_token(self, owner_id: str) -> str:
        if not self._fernet:
            raise GoogleAuthError("encryption_key_missing")
        row = await self.store.fetchone(
            "SELECT encrypted_refresh_token, status FROM google_connections WHERE owner_id = ?",
            (owner_id,),
        )
        if row is None or row["status"] != "active" or not row["encrypted_refresh_token"]:
            raise GoogleAuthError("not_connected")
        try:
            return self._fernet.decrypt(row["encrypted_refresh_token"].encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise GoogleAuthError("token_corrupt") from exc

    def _require_transport(self) -> Any:
        if self.transport is None:
            raise GoogleAuthError("transport_unavailable")
        return self.transport

    async def gmail_search(self, query: str, *, owner_id: str = "owner") -> list[dict]:
        token = await self._refresh_token(owner_id)
        return await self._require_transport().gmail_search(token, query)

    async def gmail_draft(self, thread_id: str, body: str, *, owner_id: str = "owner") -> dict:
        token = await self._refresh_token(owner_id)
        return await self._require_transport().gmail_draft(token, thread_id, body)

    async def gmail_send(self, draft_id: str, *, action_class: ActionClass, approved: bool, owner_id: str = "owner") -> dict:
        if action_class == ActionClass.A5:
            raise GoogleAuthError("prohibited")
        if action_class == ActionClass.A4 and not approved:
            raise GoogleAuthError("approval_required")
        token = await self._refresh_token(owner_id)
        return await self._require_transport().gmail_send(token, draft_id)

    async def calendar_agenda(self, *, owner_id: str = "owner") -> list[dict]:
        token = await self._refresh_token(owner_id)
        return await self._require_transport().calendar_agenda(token)

    async def calendar_reschedule(self, event_id: str, new_start_unix: int, *, approved: bool, owner_id: str = "owner") -> dict:
        if not approved:
            raise GoogleAuthError("approval_required")
        token = await self._refresh_token(owner_id)
        return await self._require_transport().calendar_reschedule(token, event_id, new_start_unix)

    async def drive_search(self, query: str, *, owner_id: str = "owner") -> list[dict]:
        token = await self._refresh_token(owner_id)
        return await self._require_transport().drive_search(token, query)

    async def contacts_resolve(self, query: str, *, owner_id: str = "owner") -> list[dict]:
        token = await self._refresh_token(owner_id)
        return await self._require_transport().contacts_resolve(token, query)

    async def tasks_list(self, *, owner_id: str = "owner") -> list[dict]:
        token = await self._refresh_token(owner_id)
        return await self._require_transport().tasks_list(token)

    @staticmethod
    def scrub_for_prompt(payload: dict[str, Any]) -> dict[str, Any]:
        """Ensure tokens never enter model-visible payloads."""
        blocked = {"access_token", "refresh_token", "authorization", "token", "encrypted_refresh_token"}
        return {k: v for k, v in payload.items() if k.lower() not in blocked}
