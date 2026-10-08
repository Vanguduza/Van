from __future__ import annotations

import base64
import hashlib
import re
import time
from datetime import datetime
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from van_gateway.action.models import ExecutionStatus, VerificationObservation
from van_gateway.action.service import ActionPolicyError, ActionRuntime
from van_gateway.google.mail import content_digest, encode_snapshot, message_snapshot, prepare_reply
from van_gateway.documents.service import DocumentService, DocumentServiceError
from van_gateway.models import DegradedCode, GoogleConnectionStatus
from van_gateway.google.transport import GoogleOutcomeUnknown
from van_gateway.google.calendar_readback import event_content_matches
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

    def __init__(
        self,
        store: Store,
        fernet_key: str,
        transport: Any | None = None,
        oauth: Any | None = None,
        documents: DocumentService | None = None,
    ) -> None:
        self.store = store
        self.transport = transport
        self.oauth = oauth
        self.documents = documents
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
        # A new refresh credential needs its own canary. Retain the previous receipt
        # for diagnosis, but do not let it certify a replacement credential.
        await self.store.execute(
            "UPDATE google_capability_connections SET state = 'CONFIGURED', "
            "verified_at_unix = NULL, updated_at_unix = ? "
            "WHERE credential_plane = 'workspace_oauth'",
            (now,),
        )

    async def revoke(self, owner_id: str = "owner") -> None:
        now = int(time.time())
        await self.store.execute("UPDATE google_connections SET status = 'revoked', encrypted_refresh_token = '', updated_at_unix = ? WHERE owner_id = ?", (now, owner_id))
        # Readiness consumers do not all receive GoogleService.status(). Invalidate
        # this plane's live verdict at the revocation boundary as well.
        await self.store.execute(
            "UPDATE google_capability_connections SET state = 'AUTH_REQUIRED', "
            "verified_at_unix = NULL, updated_at_unix = ? "
            "WHERE credential_plane = 'workspace_oauth'",
            (now,),
        )

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

    async def _provider_call(self, method: str, *args: Any, owner_id: str = "owner") -> Any:
        token = await self._api_token(owner_id)
        try:
            return await getattr(self._require_transport(), method)(token, *args)
        except RuntimeError as exc:
            # Owner read routes already translate GoogleAuthError into a usable
            # service-unavailable state. Transport failures need the same boundary.
            raise GoogleAuthError(str(exc)) from exc

    async def gmail_search(self, query: str, *, owner_id: str = "owner") -> list[dict]:
        return await self._provider_call("gmail_search", query, owner_id=owner_id)

    async def gmail_draft(self, thread_id: str, body: str, *, attachment_document_id: str | None = None, owner_id: str = "owner") -> dict:
        provider, _prepared = await self._create_gmail_reply(thread_id, body, attachment_document_id=attachment_document_id, owner_id=owner_id)
        return provider

    async def _create_gmail_reply(self, thread_id: str, body: str, *, attachment_document_id: str | None = None, owner_id: str = "owner"):
        attachments = []
        if attachment_document_id:
            if self.documents is None:
                raise GoogleAuthError("document_fabric_unbound")
            try:
                data, filename = await self.documents.bytes_for(attachment_document_id, "output")
            except DocumentServiceError as exc:
                raise GoogleAuthError(exc.code) from exc
            attachments.append({"filename": filename, "mime_type": "application/pdf", "data": data})
        profile = await self._provider_call("gmail_profile_get", owner_id=owner_id)
        thread = await self._provider_call("gmail_thread_get", thread_id, owner_id=owner_id)
        try:
            prepared = prepare_reply(profile, thread, thread_id, body, attachments=attachments)
        except RuntimeError as exc:
            raise GoogleAuthError(str(exc)) from exc
        provider = await self._provider_call("gmail_draft", thread_id, prepared.raw, owner_id=owner_id)
        return provider, prepared

    async def gmail_draft_preview(self, draft_id: str, *, owner_id: str = "owner") -> dict:
        draft = await self.gmail_draft_get(draft_id, owner_id=owner_id)
        message = draft.get("message") or {}
        if draft.get("id") != draft_id or not isinstance(message, dict) or not isinstance(message.get("threadId"), str) or not message["threadId"]:
            raise GoogleAuthError("gmail_draft_identity_invalid")
        try:
            snapshot = message_snapshot(message.get("raw"))
        except RuntimeError as exc:
            raise GoogleAuthError(str(exc)) from exc
        return {
            "draft_id": draft_id, "thread_id": message["threadId"],
            "draft_content_sha256": content_digest(snapshot, message["threadId"]),
            "recipient": snapshot["to"], "cc": snapshot["cc"], "bcc": snapshot["bcc"],
            "sender": snapshot["from"], "subject": snapshot["subject"],
            "body_sha256": hashlib.sha256(snapshot["body"].encode()).hexdigest(),
            "preview": snapshot, "content_trust": "UNTRUSTED_EXTERNAL",
            "atomic_conditional_send_supported": False,
            "immutable_payload_send_supported": True,
            "source_draft_cleanup": "NOT_ATTEMPTED",
            "source_draft_state": "UNOBSERVED",
        }

    async def gmail_draft_get(self, draft_id: str, *, owner_id: str = "owner") -> dict:
        return await self._provider_call("gmail_draft_get", draft_id, owner_id=owner_id)

    async def gmail_send(self, draft_id: str, *, owner_id: str = "owner") -> dict:
        return await self._provider_call("gmail_send", draft_id, owner_id=owner_id)

    async def gmail_message_get(self, message_id: str, *, owner_id: str = "owner") -> dict:
        return await self._provider_call("gmail_message_get", message_id, owner_id=owner_id)

    async def gmail_thread_get(self, thread_id: str, *, owner_id: str = "owner") -> dict:
        token = await self._api_token(owner_id)
        return await self._require_transport().gmail_thread_get(token, thread_id)

    async def gmail_attachment_get(
        self, message_id: str, attachment_id: str, *, owner_id: str = "owner"
    ) -> bytes:
        token = await self._api_token(owner_id)
        return await self._require_transport().gmail_attachment_get(token, message_id, attachment_id)

    async def calendar_agenda(self, *, owner_id: str = "owner") -> list[dict]:
        return await self._provider_call("calendar_agenda", owner_id=owner_id)

    async def calendar_reschedule(self, event_id: str, new_start_unix: int, *, owner_id: str = "owner") -> dict:
        return await self._provider_call("calendar_reschedule", event_id, new_start_unix, owner_id=owner_id)

    async def calendar_event_get(self, event_id: str, *, owner_id: str = "owner") -> dict:
        return await self._provider_call("calendar_event_get", event_id, owner_id=owner_id)

    async def calendar_event_review(
        self, event_id: str, *, owner_id: str = "owner"
    ) -> dict:
        token = await self._api_token(owner_id)
        return await self._require_transport().calendar_event_review(token, event_id)

    async def calendar_create(
        self, event: dict[str, Any], *, owner_id: str = "owner"
    ) -> dict:
        token = await self._api_token(owner_id)
        return await self._require_transport().calendar_create(token, event)

    async def calendar_update(
        self, event_id: str, event: dict[str, Any], expected_version: str,
        *, owner_id: str = "owner",
    ) -> dict:
        token = await self._api_token(owner_id)
        return await self._require_transport().calendar_update(
            token, event_id, event, expected_version
        )

    async def calendar_delete(
        self, event_id: str, expected_version: str, *, owner_id: str = "owner"
    ) -> dict:
        token = await self._api_token(owner_id)
        return await self._require_transport().calendar_delete(
            token, event_id, expected_version
        )

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
            "google.calendar.create",
            "google.calendar.update",
            "google.calendar.delete",
        }:
            raise ActionPolicyError("google_action_not_supported")

        await actions.mark_executing(execution_id)
        try:
            if execution.action_id == "google.gmail.draft":
                thread_id = str(parameters["thread_id"])
                body = str(parameters["body"])
                provider, prepared = await self._create_gmail_reply(thread_id, body,
                    attachment_document_id=str(parameters.get("attachment_document_id") or "").strip() or None)
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
                        and message_snapshot(message.get("raw")) == prepared.snapshot
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
                            "source_message_id": prepared.source_message_id,
                            "draft_content_sha256": content_digest(prepared.snapshot, thread_id) if success else None,
                            "decoded_content_matches": success,
                        },
                        evidence_pointer=pointer,
                    ),
                    independent_observer=True,
                )
                # This review object is what a later A4 send approval binds to. Raw MIME bytes
                # remain provider data; the owner/runtime receives only the exact digest.
                if isinstance(provider.get("message"), dict):
                    provider["message"].pop("raw", None)
                return {
                    "provider": provider,
                    "review": {
                        "draft_id": object_id,
                        "thread_id": thread_id,
                        "draft_content_sha256": content_digest(prepared.snapshot, thread_id),
                        "source_message_id": prepared.source_message_id,
                        "attachment_document_id": str(parameters.get("attachment_document_id") or "").strip() or None,
                    },
                    "verification": receipt.model_dump(mode="json"),
                }

            if execution.action_id == "google.gmail.send":
                draft_id = str(parameters["draft_id"])
                expected_digest = parameters.get("draft_content_sha256")
                if not isinstance(expected_digest, str) or re.fullmatch(r"[0-9a-f]{64}", expected_digest) is None:
                    raise GoogleAuthError("gmail_send_content_binding_required")
                preview = await self.gmail_draft_preview(draft_id)
                if preview["draft_content_sha256"] != expected_digest:
                    raise GoogleAuthError("gmail_send_draft_changed_since_approval")
                # Gmail cannot conditionally send a mutable draft revision.
                # messages.send takes the frozen approved MIME as request data,
                # so an edit to the original draft after this read cannot change
                # the recipients/content of the effect request.
                frozen_raw = encode_snapshot(preview["preview"])
                provider = await self._provider_call("gmail_message_send", frozen_raw, preview["thread_id"])
                message_id = str(provider.get("id") or "")
                if not message_id:
                    raise GoogleAuthError("gmail_sent_message_id_missing")
                correlation = {"message_id": message_id, "source_draft_id": draft_id}
                pointer = f"google://gmail/messages/{message_id}"
                await actions.mark_submitted(
                    execution_id, correlation=correlation, evidence_pointer=pointer
                )
                await actions.mark_verifying(execution_id)
                try:
                    observed = await self.gmail_message_get(message_id)
                    labels = {str(item) for item in observed.get("labelIds") or []}
                    success = (
                        str(observed.get("id") or "") == message_id and "SENT" in labels
                        and str(observed.get("threadId") or "") == preview["thread_id"]
                        and content_digest(message_snapshot(observed.get("raw")), preview["thread_id"]) == expected_digest
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
                            "message_id": str(observed.get("id") or ""),
                            "sent": "SENT" in {str(item) for item in observed.get("labelIds") or []},
                            "approved_content_matches": success,
                            "draft_content_sha256": expected_digest,
                            "atomic_conditional_send_supported": False,
                            "immutable_payload_send_supported": True,
                            "source_draft_cleanup": "NOT_ATTEMPTED",
                            "source_draft_state": "UNOBSERVED",
                        },
                        evidence_pointer=pointer,
                    ),
                    independent_observer=True,
                )
                return {"provider": provider, "verification": receipt.model_dump(mode="json")}

            if execution.action_id == "google.calendar.create":
                event = dict(parameters["event"])
                provider = await self.calendar_create(event)
                event_id = str(provider.get("id") or "")
                if not event_id:
                    raise GoogleAuthError("calendar_event_id_missing")
                correlation = {"event_id": event_id}
                pointer = f"google://calendar/events/{event_id}"
                await actions.mark_submitted(
                    execution_id, correlation=correlation, evidence_pointer=pointer
                )
                await actions.mark_verifying(execution_id)
                try:
                    observed = await self.calendar_event_get(event_id)
                    success = (
                        str(observed.get("id") or "") == event_id
                        and event_content_matches(event, observed)
                    )
                except Exception:
                    success, observed = False, {}
                receipt = await actions.verify(
                    VerificationObservation(
                        execution_id=execution_id, success=success, partial=not success,
                        correlation=correlation,
                        observed_postcondition={
                            "event_id": str(observed.get("id") or ""),
                            "etag": str(observed.get("etag") or ""),
                        },
                        evidence_pointer=pointer,
                    ),
                    independent_observer=True,
                )
                return {"provider": provider, "verification": receipt.model_dump(mode="json")}

            if execution.action_id == "google.calendar.update":
                event_id = str(parameters["event_id"])
                event = dict(parameters["event"])
                expected_version = str(parameters["expected_version"])
                provider = await self.calendar_update(event_id, event, expected_version)
                correlation = {"event_id": str(provider.get("id") or event_id)}
                pointer = f"google://calendar/events/{event_id}"
                await actions.mark_submitted(
                    execution_id, correlation=correlation, evidence_pointer=pointer
                )
                await actions.mark_verifying(execution_id)
                try:
                    observed = await self.calendar_event_get(event_id)
                    success = (
                        str(observed.get("id") or "") == event_id
                        and bool(str(observed.get("etag") or ""))
                        and str(observed.get("etag") or "") != expected_version
                        and event_content_matches(event, observed)
                    )
                except Exception:
                    success, observed = False, {}
                receipt = await actions.verify(
                    VerificationObservation(
                        execution_id=execution_id, success=success, partial=not success,
                        correlation=correlation,
                        observed_postcondition={
                            "event_id": str(observed.get("id") or ""),
                            "etag": str(observed.get("etag") or ""),
                        },
                        evidence_pointer=pointer,
                    ),
                    independent_observer=True,
                )
                return {"provider": provider, "verification": receipt.model_dump(mode="json")}

            if execution.action_id == "google.calendar.delete":
                event_id = str(parameters["event_id"])
                expected_version = str(parameters["expected_version"])
                provider = await self.calendar_delete(event_id, expected_version)
                correlation = {"event_id": event_id}
                pointer = f"google://calendar/events/{event_id}"
                await actions.mark_submitted(
                    execution_id, correlation=correlation, evidence_pointer=pointer
                )
                await actions.mark_verifying(execution_id)
                observed: dict[str, Any] = {}
                success = False
                try:
                    observed = await self.calendar_event_get(event_id)
                    success = (
                        str(observed.get("id") or "") == event_id
                        and str(observed.get("status") or "") == "cancelled"
                    )
                except Exception as exc:
                    success = str(exc) == "google_http_404"
                receipt = await actions.verify(
                    VerificationObservation(
                        execution_id=execution_id, success=success, partial=not success,
                        correlation=correlation,
                        observed_postcondition={
                            "event_id": event_id,
                            "deleted": success,
                        },
                        evidence_pointer=pointer,
                    ),
                    independent_observer=True,
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
                observed_end = datetime.fromisoformat(
                    str((observed.get("end") or {}).get("dateTime") or "").replace("Z", "+00:00")
                )
                expected_end = datetime.fromisoformat(
                    str((provider.get("end") or {}).get("dateTime") or "").replace("Z", "+00:00")
                )
                success = (
                    str(observed.get("id") or "") == event_id
                    and str(provider.get("id") or "") == event_id
                    and observed.get("status") != "cancelled"
                    and parsed.tzinfo is not None
                    and observed_end.tzinfo is not None
                    and expected_end.tzinfo is not None
                    and int(parsed.timestamp()) == new_start_unix
                    and observed_end == expected_end
                    and observed_end > parsed
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
                        "end": (observed.get("end") or {}).get("dateTime"),
                    },
                    evidence_pointer=pointer,
                ),
                independent_observer=True,
            )
            return {"provider": provider, "verification": receipt.model_dump(mode="json")}
        except GoogleOutcomeUnknown as exc:
            await actions.fail_execution(
                execution_id,
                status=ExecutionStatus.CONFLICTED_STATE,
                error_code="GOOGLE_OUTCOME_UNKNOWN",
            )
            raise GoogleAuthError("google_outcome_unknown") from exc
        except (GoogleAuthError, RuntimeError, KeyError, ValueError) as exc:
            code = str(exc)
            status = ExecutionStatus.EXECUTION_FAILED
            if code == "gmail_send_draft_changed_since_approval":
                status = ExecutionStatus.CONFLICTED_STATE
            elif code.startswith(("gmail_reply_", "gmail_raw_", "gmail_frozen_")) or code in {
                "gmail_send_content_binding_required", "gmail_draft_identity_invalid",
            }:
                status = ExecutionStatus.PRECONDITION_FAILED
            await actions.fail_execution(
                execution_id,
                status=status,
                error_code=code[:200],
            )
            if isinstance(exc, GoogleAuthError):
                raise
            raise GoogleAuthError(str(exc)) from exc

    async def drive_search(self, query: str, *, owner_id: str = "owner") -> list[dict]:
        return await self._provider_call("drive_search", query, owner_id=owner_id)

    async def contacts_resolve(self, query: str, *, owner_id: str = "owner") -> list[dict]:
        return await self._provider_call("contacts_resolve", query, owner_id=owner_id)

    async def tasks_list(self, *, owner_id: str = "owner") -> list[dict]:
        return await self._provider_call("tasks_list", owner_id=owner_id)

    @staticmethod
    def scrub_for_prompt(payload: dict[str, Any]) -> dict[str, Any]:
        """Ensure tokens and credential material never enter model-visible payloads."""
        blocked = {"access_token", "refresh_token", "authorization", "token", "encrypted_refresh_token", "client_secret", "api_key", "cookie", "session_cookie"}
        return {k: v for k, v in payload.items() if k.lower() not in blocked}
