from __future__ import annotations

import base64
import hashlib
import time
from datetime import datetime
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from van_gateway.action.models import ExecutionStatus, VerificationObservation
from van_gateway.action.service import ActionPolicyError, ActionRuntime
from van_gateway.models import DegradedCode, GoogleConnectionStatus
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

    Refresh tokens are encrypted at rest and never returned to model prompts.
    Live HTTP transport receives short-lived access tokens obtained through the
    configured OAuth token client; test doubles explicitly bypass that exchange.
    """

    def __init__(self, store: Store, fernet_key: str, transport: Any | None = None, oauth: Any | None = None) -> None:
        self.store = store
        self.transport = transport
        self.oauth = oauth
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
            return GoogleConnectionStatus(connected=False, degraded=[DegradedCode.GOOGLE_TOKEN_EXPIRED.value], services={s: "unavailable" for s in ("gmail", "calendar", "drive", "contacts", "tasks")})
        row = await self.store.fetchone("SELECT encrypted_refresh_token, scopes_json, status FROM google_connections WHERE owner_id = ?", (owner_id,))
        if row is None or row["status"] != "active":
            return GoogleConnectionStatus(connected=False, degraded=[DegradedCode.GOOGLE_TOKEN_EXPIRED.value], services={s: "disconnected" for s in ("gmail", "calendar", "drive", "contacts", "tasks")})
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
        if self.transport is not None and getattr(self.transport, "requires_access_token", True) and self.oauth is None:
            degraded.append(DegradedCode.GOOGLE_OAUTH_CLIENT_UNCONFIGURED.value)
        return GoogleConnectionStatus(connected=True, scopes=scopes, services=services, degraded=degraded)

    async def store_refresh_token(self, owner_id: str, refresh_token: str, scopes: list[str]) -> None:
        if not self._fernet:
            raise GoogleAuthError("encryption_key_missing")
        for scope in scopes:
            if scope not in NARROW_SCOPES:
                raise GoogleAuthError(f"scope_not_allowed:{scope}")
        token = self._fernet.encrypt(refresh_token.encode("utf-8")).decode("ascii")
        now = int(time.time())
        await self.store.execute("""
            INSERT INTO google_connections(owner_id, encrypted_refresh_token, scopes_json, status, updated_at_unix)
            VALUES (?, ?, ?, 'active', ?)
            ON CONFLICT(owner_id) DO UPDATE SET
              encrypted_refresh_token=excluded.encrypted_refresh_token,
              scopes_json=excluded.scopes_json,
              status='active',
              updated_at_unix=excluded.updated_at_unix
            """, (owner_id, token, Store.dumps(scopes), now))

    async def revoke(self, owner_id: str = "owner") -> None:
        now = int(time.time())
        await self.store.execute("UPDATE google_connections SET status = 'revoked', encrypted_refresh_token = '', updated_at_unix = ? WHERE owner_id = ?", (now, owner_id))

    async def _refresh_token(self, owner_id: str) -> str:
        if not self._fernet:
            raise GoogleAuthError("encryption_key_missing")
        row = await self.store.fetchone("SELECT encrypted_refresh_token, status FROM google_connections WHERE owner_id = ?", (owner_id,))
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

    async def _api_token(self, owner_id: str) -> str:
        refresh = await self._refresh_token(owner_id)
        transport = self._require_transport()
        if not getattr(transport, "requires_access_token", True):
            return refresh
        if self.oauth is None:
            raise GoogleAuthError("oauth_refresh_unavailable")
        try:
            return await self.oauth.access_token(refresh)
        except RuntimeError as exc:
            raise GoogleAuthError(str(exc)) from exc

    async def gmail_search(self, query: str, *, owner_id: str = "owner") -> list[dict]:
        token = await self._api_token(owner_id)
        return await self._require_transport().gmail_search(token, query)

    async def gmail_draft(self, thread_id: str, body: str, *, owner_id: str = "owner") -> dict:
        token = await self._api_token(owner_id)
        return await self._require_transport().gmail_draft(token, thread_id, body)

    async def gmail_draft_get(self, draft_id: str, *, owner_id: str = "owner") -> dict:
        token = await self._api_token(owner_id)
        return await self._require_transport().gmail_draft_get(token, draft_id)

    async def gmail_send(self, draft_id: str, *, owner_id: str = "owner") -> dict:
        token = await self._api_token(owner_id)
        return await self._require_transport().gmail_send(token, draft_id)

    async def gmail_message_get(self, message_id: str, *, owner_id: str = "owner") -> dict:
        token = await self._api_token(owner_id)
        return await self._require_transport().gmail_message_get(token, message_id)

    async def calendar_agenda(self, *, owner_id: str = "owner") -> list[dict]:
        token = await self._api_token(owner_id)
        return await self._require_transport().calendar_agenda(token)

    async def calendar_reschedule(self, event_id: str, new_start_unix: int, *, owner_id: str = "owner") -> dict:
        token = await self._api_token(owner_id)
        return await self._require_transport().calendar_reschedule(token, event_id, new_start_unix)

    async def calendar_event_get(self, event_id: str, *, owner_id: str = "owner") -> dict:
        token = await self._api_token(owner_id)
        return await self._require_transport().calendar_event_get(token, event_id)

    async def execute_authorized_action(
        self,
        actions: ActionRuntime,
        *,
        execution_id: str,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a Workspace mutation only after canonical action authorization.

        The internal-control token authenticates the runtime; it is not owner approval.
        Parameter digest equality prevents Hermes or another internal caller from changing
        the object or content after the signed command was authorized. A second provider
        read is required before VERIFIED_SUCCESS can be emitted.
        """
        execution = await actions.get_execution(execution_id)
        if execution is None:
            raise ActionPolicyError("unknown_execution")
        if execution.status is not ExecutionStatus.AUTHORIZED:
            raise ActionPolicyError("execution_not_authorized")
        if execution.parameters_digest != actions.digest_parameters(parameters):
            raise ActionPolicyError("authorized_parameter_mismatch")
        if execution.action_id not in {
            "google.gmail.draft",
            "google.gmail.send",
            "google.calendar.reschedule",
        }:
            raise ActionPolicyError("google_action_not_supported")

        await actions.mark_executing(execution_id)
        try:
            if execution.action_id == "google.gmail.draft":
                thread_id = str(parameters["thread_id"])
                body = str(parameters["body"])
                provider = await self.gmail_draft(thread_id, body)
                object_id = str(provider.get("id") or "")
                if not object_id:
                    raise GoogleAuthError("gmail_draft_id_missing")
                correlation = {"draft_id": object_id}
                pointer = f"google://gmail/drafts/{object_id}"
                await actions.mark_submitted(
                    execution_id, correlation=correlation, evidence_pointer=pointer
                )
                await actions.mark_verifying(execution_id)
                try:
                    observed = await self.gmail_draft_get(object_id)
                    message = dict(observed.get("message") or {})
                    success = (
                        str(observed.get("id") or "") == object_id
                        and str(message.get("threadId") or "") == thread_id
                        and str(message.get("raw") or "") == body
                    )
                except Exception:
                    success, observed = False, {}
                receipt = await actions.verify(
                    VerificationObservation(
                        execution_id=execution_id,
                        success=success,
                        partial=not success,
                        correlation=correlation,
                        observed_postcondition={
                            "draft_id": object_id,
                            "thread_id": str((observed.get("message") or {}).get("threadId") or ""),
                        },
                        evidence_pointer=pointer,
                    )
                )
                return {"provider": provider, "verification": receipt.model_dump(mode="json")}

            if execution.action_id == "google.gmail.send":
                draft_id = str(parameters["draft_id"])
                provider = await self.gmail_send(draft_id)
                message_id = str(provider.get("id") or "")
                if not message_id:
                    raise GoogleAuthError("gmail_sent_message_id_missing")
                correlation = {"message_id": message_id}
                pointer = f"google://gmail/messages/{message_id}"
                await actions.mark_submitted(
                    execution_id, correlation=correlation, evidence_pointer=pointer
                )
                await actions.mark_verifying(execution_id)
                try:
                    observed = await self.gmail_message_get(message_id)
                    labels = {str(item) for item in observed.get("labelIds") or []}
                    success = str(observed.get("id") or "") == message_id and "SENT" in labels
                except Exception:
                    success, observed = False, {}
                receipt = await actions.verify(
                    VerificationObservation(
                        execution_id=execution_id,
                        success=success,
                        partial=not success,
                        correlation=correlation,
                        observed_postcondition={
                            "message_id": str(observed.get("id") or ""),
                            "sent": "SENT" in {str(item) for item in observed.get("labelIds") or []},
                        },
                        evidence_pointer=pointer,
                    )
                )
                return {"provider": provider, "verification": receipt.model_dump(mode="json")}

            event_id = str(parameters["event_id"])
            new_start_unix = int(parameters["new_start_unix"])
            provider = await self.calendar_reschedule(event_id, new_start_unix)
            correlation = {"event_id": str(provider.get("id") or event_id)}
            pointer = f"google://calendar/events/{event_id}"
            await actions.mark_submitted(
                execution_id, correlation=correlation, evidence_pointer=pointer
            )
            await actions.mark_verifying(execution_id)
            try:
                observed = await self.calendar_event_get(event_id)
                raw = str((observed.get("start") or {}).get("dateTime") or "")
                parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                success = (
                    str(observed.get("id") or "") == event_id
                    and int(parsed.timestamp()) == new_start_unix
                )
            except Exception:
                success, observed = False, {}
            receipt = await actions.verify(
                VerificationObservation(
                    execution_id=execution_id,
                    success=success,
                    partial=not success,
                    correlation=correlation,
                    observed_postcondition={
                        "event_id": str(observed.get("id") or ""),
                        "start": (observed.get("start") or {}).get("dateTime"),
                    },
                    evidence_pointer=pointer,
                )
            )
            return {"provider": provider, "verification": receipt.model_dump(mode="json")}
        except (GoogleAuthError, RuntimeError, KeyError, ValueError) as exc:
            await actions.fail_execution(
                execution_id,
                status=ExecutionStatus.EXECUTION_FAILED,
                error_code=str(exc)[:200],
            )
            if isinstance(exc, GoogleAuthError):
                raise
            raise GoogleAuthError(str(exc)) from exc

    async def drive_search(self, query: str, *, owner_id: str = "owner") -> list[dict]:
        token = await self._api_token(owner_id)
        return await self._require_transport().drive_search(token, query)

    async def contacts_resolve(self, query: str, *, owner_id: str = "owner") -> list[dict]:
        token = await self._api_token(owner_id)
        return await self._require_transport().contacts_resolve(token, query)

    async def tasks_list(self, *, owner_id: str = "owner") -> list[dict]:
        token = await self._api_token(owner_id)
        return await self._require_transport().tasks_list(token)

    @staticmethod
    def scrub_for_prompt(payload: dict[str, Any]) -> dict[str, Any]:
        """Ensure tokens and credential material never enter model-visible payloads."""
        blocked = {"access_token", "refresh_token", "authorization", "token", "encrypted_refresh_token", "client_secret", "api_key", "cookie", "session_cookie"}
        return {k: v for k, v in payload.items() if k.lower() not in blocked}
