from __future__ import annotations

import base64
import hashlib
import json
import uuid
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
        workspace_identity: str = "owner_google_account",
    ) -> None:
        self.store = store
        self.transport = transport
        self.oauth = oauth
        self.documents = documents
        self.workspace_identity = workspace_identity
        self.workspace_readiness_aliases = (workspace_identity,)
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
        # Explicit connect/reconnect establishes a new logical connection even when
        # the owner, scopes or token bytes are reused. Access-token refresh never
        # calls this producer and cannot advance this generation.
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            await db.execute("""
                INSERT INTO google_connections(owner_id, encrypted_refresh_token, scopes_json, status, updated_at_unix)
                VALUES (?, ?, ?, 'active', ?)
                ON CONFLICT(owner_id) DO UPDATE SET
                  encrypted_refresh_token=excluded.encrypted_refresh_token,
                  scopes_json=excluded.scopes_json, status='active',
                  updated_at_unix=excluded.updated_at_unix
                """, (owner_id, token, Store.dumps(scopes), now))
            await self._record_connection(db, owner_id, uuid.uuid4().hex)
            # Credential, generation and readiness are one local writer commit.
            # The previous canary remains diagnostic evidence for its own credential.
            await self._invalidate_workspace_readiness(db, owner_id, 'CONFIGURED', now)
            await db.commit()

    @staticmethod
    def _digest(value: Any) -> str:
        return hashlib.sha256(Store.dumps(value).encode()).hexdigest()

    def _seal(self, value: dict) -> str:
        if not self._fernet:
            raise GoogleAuthError("encryption_key_missing")
        return self._fernet.encrypt(Store.dumps(value).encode()).decode()

    def _open(self, value: str) -> dict:
        if not self._fernet:
            raise GoogleAuthError("encryption_key_missing")
        try:
            result = json.loads(self._fernet.decrypt(value.encode()))
            if not isinstance(result, dict):
                raise ValueError("not_object")
            return result
        except (InvalidToken, ValueError, TypeError, UnicodeError) as exc:
            raise GoogleAuthError("workspace_record_integrity_failed") from exc

    @staticmethod
    def _connection_key(owner_id: str) -> str:
        return "google_connection_generation:" + GoogleService._digest(owner_id)

    async def _connection(self, db, owner_id: str) -> dict:
        row = await (await db.execute(
            "SELECT * FROM google_connections WHERE owner_id=?", (owner_id,))).fetchone()
        row = dict(row) if row else None
        meta = await (await db.execute(
            "SELECT value FROM runtime_meta WHERE key=?", (self._connection_key(owner_id),))).fetchone()
        if meta:
            original = self._open(meta['value'])
            if (set(original) != {'schema', 'owner_id', 'generation', 'row_digest'}
                or original['schema'] != 'van.google-connection/1'
                or original['owner_id'] != owner_id
                or not isinstance(original['generation'], str) or not original['generation']
                or original['row_digest'] != self._digest(row)):
                raise GoogleAuthError('workspace_record_integrity_failed')
            generation = original['generation']
        else:
            # Existing installations remain inspectable without a write on GET.
            # The first explicit reconnect gets a fresh generation, including when
            # it supplies the exact same token bytes as this legacy connection.
            generation = 'legacy-' + self._digest({'owner_id': owner_id, 'row': row})
        scopes = json.loads(row['scopes_json']) if row else []
        return dict(owner_id=owner_id, connection_generation=generation,
                    source_revision=self._digest({'owner_id': owner_id, 'generation': generation, 'scopes': scopes}),
                    connected=bool(row and row['status'] == 'active' and row['encrypted_refresh_token']),
                    scopes=scopes, credential_plane='workspace_oauth',
                    effect_scope='gateway_held_workspace_credential_only')

    async def _record_connection(self, db, owner_id: str, generation: str) -> None:
        row = await (await db.execute(
            "SELECT * FROM google_connections WHERE owner_id=?", (owner_id,))).fetchone()
        value = self._seal(dict(schema='van.google-connection/1', owner_id=owner_id,
                                generation=generation, row_digest=self._digest(dict(row) if row else None)))
        await db.execute(
            "INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at_unix_ms=excluded.updated_at_unix_ms",
            (self._connection_key(owner_id), value, int(time.time()*1000)))

    async def connection_detail(self, owner_id: str = 'owner') -> dict:
        async with self.store.connection() as db:
            await db.execute('BEGIN')
            return await self._connection(db, owner_id)

    async def _withdraw_connection(self, db, owner_id: str, generation: str) -> None:
        now = int(time.time())
        await db.execute("UPDATE google_connections SET status='revoked', encrypted_refresh_token='', "
                         "updated_at_unix=? WHERE owner_id=?", (now, owner_id))
        await self._record_connection(db, owner_id, generation)
        await self._invalidate_workspace_readiness(db, owner_id, 'AUTH_REQUIRED', now)

    async def _invalidate_workspace_readiness(self, db, owner_id: str, state: str, now: int) -> None:
        # Aliases are derived from the actual broker registry when it is wired.
        # A non-default credential owner never inherits the canonical owner's rows.
        aliases = self.workspace_readiness_aliases if owner_id == 'owner' else (owner_id,)
        if not aliases:
            return
        placeholders = ','.join('?' for _ in aliases)
        await db.execute(
            "UPDATE google_capability_connections SET state=?,verified_at_unix=NULL,updated_at_unix=? "
            "WHERE credential_plane='workspace_oauth' AND owner_id IN ("+placeholders+")",
            (state, now, *aliases))

    async def revoke(self, owner_id: str = "owner") -> None:
        # Existing internal-control operation is a new explicit current withdrawal.
        # The phone adapter must instead use its selected original operation receipt.
        async with self.store.connection() as db:
            await db.execute('BEGIN IMMEDIATE')
            detail = await self._connection(db, owner_id)
            await self._withdraw_connection(db, owner_id, detail['connection_generation'])
            await db.commit()

    async def _withdrawal_actor(self, db, device_id: str, access_token_hash: str | None,
                                proof_required: bool = False) -> str:
        row = await (await db.execute('SELECT * FROM devices WHERE device_id=?', (device_id,))).fetchone()
        if (not row or row['revoked_at_unix'] is not None
            or access_token_hash is not None and row['access_token_hash'] != access_token_hash):
            raise GoogleAuthError('workspace_caller_not_current')
        binding = await (await db.execute(
            'SELECT binding_id,status,device_key_fingerprint FROM owner_device_bindings WHERE device_id=?',
            (device_id,))).fetchone()
        if binding and binding['status'] != 'ACTIVE':
            raise GoogleAuthError('workspace_caller_not_current')
        return self._digest(dict(device_id=device_id, enrolled_at_unix=row['enrolled_at_unix'],
                                 public_key_pem=row['public_key_pem'], access_token_hash=row['access_token_hash'],
                                 binding=dict(binding) if binding else None))

    async def withdrawal_detail(self, *, device_id: str, access_token_hash: str | None = None,
                                owner_id: str = 'owner') -> dict:
        """An inert, bounded proposal. No connection, grant or operation is written by GET."""
        async with self.store.connection() as db:
            await db.execute('BEGIN')
            actor = await self._withdrawal_actor(db, device_id, access_token_hash)
            detail = await self._connection(db, owner_id)
        return {**detail, 'withdrawal_request': self._new_withdrawal_request(detail, device_id, actor)}

    def _new_withdrawal_request(self, detail: dict, device_id: str, actor: str) -> dict:
        owner_id = detail['owner_id']
        issued = int(time.time()*1000)
        request = dict(operation_id='workspace-withdraw-'+uuid.uuid4().hex,
                       caller_device_id=device_id, owner_id=owner_id,
                       connection_generation=detail['connection_generation'],
                       expected_revision=detail['source_revision'])
        token = dict(schema='van.google-withdrawal-proposal/1', request=request,
                     caller_context=actor, issued_at_ms=issued, deadline_ms=issued+600000)
        return {**request, 'request_token': self._seal(token)}

    def _withdrawal_request(self, request: dict) -> tuple[dict, dict]:
        fields = {'operation_id', 'caller_device_id', 'owner_id', 'connection_generation',
                  'expected_revision', 'request_token'}
        if (not isinstance(request, dict) or set(request) != fields
            or any(not isinstance(v, str) or not v or len(v)>16384 for v in request.values())
            or not re.fullmatch(r'workspace-withdraw-[a-f0-9]{32}', request['operation_id'])):
            raise GoogleAuthError('workspace_withdrawal_request_invalid')
        body = {k:v for k,v in request.items() if k != 'request_token'}
        token = self._open(request['request_token'])
        if (set(token) != {'schema','request','caller_context','issued_at_ms','deadline_ms'}
            or token['schema'] != 'van.google-withdrawal-proposal/1' or token['request'] != body
            or not isinstance(token['caller_context'], str)
            or type(token['issued_at_ms']) is not int or type(token['deadline_ms']) is not int
            or token['deadline_ms']-token['issued_at_ms'] != 600000):
            raise GoogleAuthError('workspace_withdrawal_request_invalid')
        return body, token

    @staticmethod
    def _withdrawal_key(operation_id: str) -> str:
        return 'google_owner_withdrawal:' + operation_id

    async def _original_withdrawal(self, db, operation_id: str) -> dict | None:
        row = await (await db.execute('SELECT value FROM runtime_meta WHERE key=?',
                                     (self._withdrawal_key(operation_id),))).fetchone()
        if not row:
            return None
        record = self._open(row['value'])
        if (set(record) != {'schema','request','request_digest','caller_context','result'}
            or record['schema'] != 'van.google-withdrawal-result/1'
            or not isinstance(record['request'], dict) or not isinstance(record['result'], dict)
            or record['request_digest'] != self._digest(record['request'])
            or record['request'].get('operation_id') != operation_id):
            raise GoogleAuthError('workspace_record_integrity_failed')
        body, token = self._withdrawal_request(record['request'])
        result = record['result']
        if (record['caller_context'] != token['caller_context']
            or any(result.get(k) != body[k] for k in body)
            or result.get('request_deadline_ms') != token['deadline_ms']
            or result.get('state') not in {'APPLIED','REFUSED'}
            or result.get('effect_scope') != 'gateway_held_workspace_credential_only'
            or result.get('provider_token_revoked') is not False):
            raise GoogleAuthError('workspace_record_integrity_failed')
        return record

    async def withdraw_selected(self, request: dict, *, device_id: str,
                                access_token_hash: str | None = None,
                                proof_required: bool = False, owner_id: str = 'owner') -> dict:
        body, token = self._withdrawal_request(request)
        if body['caller_device_id'] != device_id or body['owner_id'] != owner_id:
            raise GoogleAuthError('workspace_withdrawal_wrong_caller')
        async with self.store.connection() as db:
            await db.execute('BEGIN IMMEDIATE')
            result = await self._withdraw_in_writer(db, request, body, token, device_id,
                                                    access_token_hash, proof_required)
            await db.commit()
            return result

    async def _withdraw_in_writer(self, db, request, body, token, device_id,
                                  access_token_hash, proof_required):
        actor = await self._withdrawal_actor(db, device_id, access_token_hash, proof_required)
        original = await self._original_withdrawal(db, body['operation_id'])
        if original:
            # AuthService never re-enrolls an existing device_id, including its
            # revoked tombstone. The already sealed owner/device/target/op are
            # stable history subjects; an old access-token digest is not current
            # read authority. Current lawful authentication was checked above.
            if original['request'] != request:
                raise GoogleAuthError('workspace_withdrawal_operation_conflict')
            return original['result']
        now = int(time.time()*1000)
        reason = ('workspace_withdrawal_request_not_current' if token['caller_context'] != actor else
                  'workspace_withdrawal_request_expired' if now >= token['deadline_ms'] else
                  'workspace_withdrawal_request_not_current' if now+30000 < token['issued_at_ms'] else None)
        if reason is None:
            detail = await self._connection(db, body['owner_id'])
            if (detail['connection_generation'] != body['connection_generation'] or
                detail['source_revision'] != body['expected_revision']):
                reason = 'workspace_withdrawal_stale_connection'
        changed = False
        if reason is None:
            # Recheck the immutable original request lease inside the writer
            # immediately before the local effect, including a delayed read.
            if int(time.time()*1000) >= token['deadline_ms']:
                reason = 'workspace_withdrawal_request_expired'
            else:
                changed = detail['connected']
                await self._withdraw_connection(db, body['owner_id'], body['connection_generation'])
        result = {**body, 'state': 'REFUSED' if reason else 'APPLIED',
                  'withdrawn': reason is None, 'changed': changed, 'reason_code': reason,
                  'completed_at_ms': now, 'request_deadline_ms': token['deadline_ms'],
                  'effect_scope': 'gateway_held_workspace_credential_only',
                  'provider_token_revoked': False}
        record = dict(schema='van.google-withdrawal-result/1', request=request,
                      request_digest=self._digest(request), caller_context=token['caller_context'], result=result)
        await db.execute('INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?)',
                         (self._withdrawal_key(body['operation_id']), self._seal(record), now))
        return result

    async def withdraw_legacy(self, *, device_id: str, access_token_hash: str | None = None,
                              proof_required: bool = False, owner_id: str = 'owner') -> dict:
        """Capture one unambiguous original legacy intent; never select a replacement.

        A new connection or changed caller context requires an explicitly reviewed
        operation. Empty transport retries cannot express that new owner intent.
        """
        key = 'google_legacy_owner_withdrawal:' + self._digest({'owner_id':owner_id, 'device_id':device_id})
        async with self.store.connection() as db:
            await db.execute('BEGIN IMMEDIATE')
            actor = await self._withdrawal_actor(db, device_id, access_token_hash, proof_required)
            detail = await self._connection(db, owner_id)
            saved = await (await db.execute('SELECT value FROM runtime_meta WHERE key=?', (key,))).fetchone()
            if saved:
                pointer = self._open(saved['value'])
                if set(pointer) != {'schema','request','caller_context'} or pointer['schema'] != 'van.google-legacy-withdrawal/1':
                    raise GoogleAuthError('workspace_record_integrity_failed')
                request = pointer['request']
                body, token = self._withdrawal_request(request)
                if (body['owner_id'] != owner_id or body['caller_device_id'] != device_id
                    or body['connection_generation'] != detail['connection_generation']):
                    raise GoogleAuthError('workspace_explicit_operation_required')
                original = await self._original_withdrawal(db, body['operation_id'])
                if (not original or original['request'] != request
                    or pointer['caller_context'] != token['caller_context']):
                    raise GoogleAuthError('workspace_record_integrity_failed')
                result = await self._withdraw_in_writer(db, request, body, token, device_id,
                                                        access_token_hash, proof_required)
            else:
                request = self._new_withdrawal_request(detail, device_id, actor)
                body, token = self._withdrawal_request(request)
                result = await self._withdraw_in_writer(db, request, body, token, device_id,
                                                        access_token_hash, proof_required)
                pointer = dict(schema='van.google-legacy-withdrawal/1', request=request, caller_context=actor)
                await db.execute('INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?)',
                                 (key, self._seal(pointer), int(time.time()*1000)))
            await db.commit()
            return result

    async def original_withdrawal(self, operation_id: str, *, device_id: str,
                                  access_token_hash: str | None = None, owner_id: str = 'owner') -> dict:
        async with self.store.connection() as db:
            await db.execute('BEGIN')
            await self._withdrawal_actor(db, device_id, access_token_hash)
            record = await self._original_withdrawal(db, operation_id)
            if not record:
                raise GoogleAuthError('workspace_withdrawal_not_found')
            if (record['request']['caller_device_id'] != device_id
                or record['request']['owner_id'] != owner_id):
                raise GoogleAuthError('workspace_withdrawal_wrong_caller')
            return record['result']

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
        # Capture the credential and logical connection from one read snapshot.
        # A potentially slow OAuth exchange must never authorize a call using a
        # connection which was withdrawn or replaced while that exchange ran.
        async with self.store.connection() as db:
            await db.execute('BEGIN')
            original = await self._connection(db, owner_id)
            row = await (await db.execute(
                'SELECT encrypted_refresh_token FROM google_connections WHERE owner_id=?',
                (owner_id,))).fetchone()
            if not original['connected'] or not row:
                raise GoogleAuthError('not_connected')
            if not self._fernet:
                raise GoogleAuthError('encryption_key_missing')
            try:
                refresh = self._fernet.decrypt(row['encrypted_refresh_token'].encode()).decode()
            except (InvalidToken, UnicodeError) as exc:
                raise GoogleAuthError('token_decrypt_failed') from exc
        transport = self._require_transport()
        if not getattr(transport, 'requires_access_token', True):
            token = refresh
        else:
            if self.oauth is None:
                raise GoogleAuthError('oauth_refresh_unavailable')
            try:
                token = await self.oauth.access_token(refresh)
            except RuntimeError as exc:
                raise GoogleAuthError(str(exc)) from exc
        # This is local effect admission, serialized with withdrawal/reconnect.
        # Calls already admitted may have external outcomes and must reconcile
        # their existing action receipt; withdrawal blocks the next admission.
        async with self.store.connection() as db:
            await db.execute('BEGIN IMMEDIATE')
            current = await self._connection(db, owner_id)
            if (not current['connected'] or
                current['connection_generation'] != original['connection_generation'] or
                current['source_revision'] != original['source_revision']):
                raise GoogleAuthError('workspace_connection_withdrawn_or_replaced')
            await db.commit()
        return token

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
