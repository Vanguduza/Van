from __future__ import annotations

import asyncio
import base64
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from van_gateway.knowledge.evidence import KnowledgeEvidenceStore
from van_gateway.knowledge.models import (
    KnowledgeOperationStatus,
    KnowledgeProvider,
    NotebookConsumerNoteCreateRequest,
    NotebookEnterpriseAddSourcesRequest,
    NotebookEnterpriseCreateRequest,
    NotebookEnterpriseDeleteRequest,
    NotebookEnterpriseDeleteSourcesRequest,
    NotebookConsumerAskRequest,
    NotebookGroundedAnswer,
    NotebookOperationResult,
    NotebookSourceKind,
    ProviderState,
    ProviderStatus,
)
from van_gateway.storage.db import Store


class NotebookProviderError(RuntimeError):
    pass


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


class CloudAccessTokenProvider:
    """Service-account or short-lived token-file auth; credentials never enter prompts."""

    def __init__(
        self,
        *,
        service_account_file: str = "",
        access_token_file: str = "",
        token_uri: str = "https://oauth2.googleapis.com/token",
        scope: str = "https://www.googleapis.com/auth/cloud-platform",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.service_account_file = service_account_file.strip()
        self.access_token_file = access_token_file.strip()
        self.token_uri = token_uri
        self.scope = scope
        self.transport = transport
        self._cached_token = ""
        self._expires_at = 0

    def configured(self) -> bool:
        return bool(self.service_account_file or self.access_token_file)

    def credential_locus(self) -> str:
        if self.service_account_file:
            return "gateway-service-account-file"
        if self.access_token_file:
            return "gateway-short-lived-token-file"
        return "unconfigured"

    async def token(self) -> str:
        now = int(time.time())
        if self._cached_token and now < self._expires_at - 60:
            return self._cached_token
        if self.access_token_file:
            try:
                token = Path(self.access_token_file).expanduser().read_text(encoding="utf-8").strip()
            except OSError as exc:
                raise NotebookProviderError("notebook_enterprise_token_file_unavailable") from exc
            if not token:
                raise NotebookProviderError("notebook_enterprise_token_file_empty")
            return token
        if not self.service_account_file:
            raise NotebookProviderError("notebook_enterprise_credentials_unconfigured")
        try:
            info = json.loads(Path(self.service_account_file).expanduser().read_text(encoding="utf-8"))
            email = str(info["client_email"])
            private_key = str(info["private_key"])
        except (OSError, KeyError, ValueError, TypeError) as exc:
            raise NotebookProviderError("notebook_enterprise_service_account_invalid") from exc
        issued = int(time.time())
        header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
        claims = _b64url(json.dumps({
            "iss": email, "scope": self.scope, "aud": self.token_uri,
            "iat": issued, "exp": issued + 3600,
        }, separators=(",", ":")).encode())
        signing_input = f"{header}.{claims}".encode("ascii")
        try:
            key = serialization.load_pem_private_key(private_key.encode("utf-8"), password=None)
            signature = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
        except Exception as exc:
            raise NotebookProviderError("notebook_enterprise_service_account_key_invalid") from exc
        assertion = f"{header}.{claims}.{_b64url(signature)}"
        async with httpx.AsyncClient(timeout=15.0, transport=self.transport) as client:
            response = await client.post(self.token_uri, data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            })
        if response.status_code >= 400:
            raise NotebookProviderError(f"notebook_enterprise_token_exchange_failed:{response.status_code}")
        payload = response.json()
        token = str(payload.get("access_token") or "")
        if not token:
            raise NotebookProviderError("notebook_enterprise_token_exchange_malformed")
        self._cached_token = token
        self._expires_at = issued + int(payload.get("expires_in") or 3600)
        return token


class NotebookOperationStore:
    def __init__(self, store: Store) -> None:
        self.store = store

    async def get_by_key(self, key: str) -> NotebookOperationResult | None:
        row = await self.store.fetchone("SELECT * FROM notebook_operations WHERE idempotency_key=?", (key,))
        return self._row(row) if row else None

    async def begin(self, provider: KnowledgeProvider, operation: str, key: str, request_digest: str) -> NotebookOperationResult:
        existing = await self.get_by_key(key)
        if existing:
            row = await self.store.fetchone("SELECT request_digest FROM notebook_operations WHERE idempotency_key=?", (key,))
            if row is None or str(row["request_digest"]) != request_digest:
                raise NotebookProviderError("notebook_idempotency_conflict")
            return existing
        now = int(time.time() * 1000)
        op = NotebookOperationResult(
            operation_id=str(uuid.uuid4()), provider=provider, operation=operation,
            status=KnowledgeOperationStatus.PREFLIGHT, idempotency_key=key,
        )
        await self.store.execute(
            """INSERT INTO notebook_operations(operation_id,provider,operation,idempotency_key,request_digest,status,
            resource_id,correlation_json,observed_postcondition_json,evidence_pointer,error_code,created_at_unix_ms,updated_at_unix_ms)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (op.operation_id, provider.value, operation, key, request_digest, op.status.value,
             None, "{}", "{}", None, None, now, now),
        )
        return op

    async def update(self, operation_id: str, *, status: KnowledgeOperationStatus, resource_id: str | None = None,
                     correlation: dict[str, Any] | None = None, observed: dict[str, Any] | None = None,
                     evidence_pointer: str | None = None, error_code: str | None = None) -> NotebookOperationResult:
        current = await self.store.fetchone("SELECT * FROM notebook_operations WHERE operation_id=?", (operation_id,))
        if current is None:
            raise NotebookProviderError("notebook_operation_missing")
        correlation_json = Store.dumps(correlation) if correlation is not None else str(current["correlation_json"] or "{}")
        observed_json = Store.dumps(observed) if observed is not None else str(current["observed_postcondition_json"] or "{}")
        now = int(time.time() * 1000)
        await self.store.execute(
            """UPDATE notebook_operations SET status=?,resource_id=COALESCE(?,resource_id),correlation_json=?,
            observed_postcondition_json=?,evidence_pointer=COALESCE(?,evidence_pointer),error_code=?,updated_at_unix_ms=?
            WHERE operation_id=?""",
            (status.value, resource_id, correlation_json, observed_json,
             evidence_pointer, error_code, now, operation_id),
        )
        row = await self.store.fetchone("SELECT * FROM notebook_operations WHERE operation_id=?", (operation_id,))
        assert row is not None
        return self._row(row)

    @staticmethod
    def _row(row: Any) -> NotebookOperationResult:
        return NotebookOperationResult(
            operation_id=str(row["operation_id"]), provider=KnowledgeProvider(str(row["provider"])),
            operation=str(row["operation"]), status=KnowledgeOperationStatus(str(row["status"])),
            idempotency_key=str(row["idempotency_key"]),
            resource_id=str(row["resource_id"]) if row["resource_id"] else None,
            correlation=json.loads(row["correlation_json"] or "{}"),
            observed_postcondition=json.loads(row["observed_postcondition_json"] or "{}"),
            evidence_pointer=str(row["evidence_pointer"]) if row["evidence_pointer"] else None,
            error_code=str(row["error_code"]) if row["error_code"] else None,
        )


class NotebookEnterpriseProvider:
    def __init__(self, store: Store, evidence: KnowledgeEvidenceStore, *, enabled: bool,
                 project_number: str, location: str, auth: CloudAccessTokenProvider,
                 timeout_seconds: float = 20.0, transport: httpx.AsyncBaseTransport | None = None,
                 upload_root: str = "", max_upload_bytes: int = 100_000_000) -> None:
        self.store = store
        self.evidence = evidence
        self.enabled = enabled
        self.project_number = project_number.strip()
        self.location = location.strip() or "global"
        self.auth = auth
        self.timeout_seconds = timeout_seconds
        self.transport = transport
        self.upload_root = upload_root.strip()
        self.max_upload_bytes = max(1_000_000, min(max_upload_bytes, 1_000_000_000))
        self.operations = NotebookOperationStore(store)

    def configured(self) -> bool:
        return bool(self.enabled and self.project_number and self.location and self.auth.configured())

    def _base(self) -> str:
        return f"https://{self.location}-discoveryengine.googleapis.com/v1alpha/projects/{quote(self.project_number)}/locations/{quote(self.location)}"

    async def _request(self, method: str, path: str, *, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.enabled:
            raise NotebookProviderError("notebook_enterprise_disabled")
        if not self.configured():
            raise NotebookProviderError("notebook_enterprise_unconfigured")
        token = await self.auth.token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=self.timeout_seconds, transport=self.transport) as client:
            response = await client.request(method, self._base() + path, headers=headers, json=payload)
        if response.status_code == 404:
            raise NotebookProviderError("notebook_enterprise_not_found")
        if response.status_code in {401, 403}:
            raise NotebookProviderError(f"notebook_enterprise_authorization_failed:{response.status_code}")
        if response.status_code >= 400:
            raise NotebookProviderError(f"notebook_enterprise_http_{response.status_code}")
        if not response.content:
            return {}
        try:
            body = response.json()
        except ValueError as exc:
            raise NotebookProviderError("notebook_enterprise_malformed_response") from exc
        if not isinstance(body, dict):
            raise NotebookProviderError("notebook_enterprise_malformed_response")
        return body

    async def status(self) -> ProviderStatus:
        certification = await self.evidence.certification(KnowledgeProvider.NOTEBOOK_ENTERPRISE)
        if not self.enabled:
            state = ProviderState.DISABLED
        elif not self.configured():
            state = ProviderState.UNCONFIGURED
        elif certification and certification["state"] == ProviderState.READY.value:
            state = ProviderState.READY
        else:
            state = ProviderState.CONFIGURED
        return ProviderStatus(
            provider=KnowledgeProvider.NOTEBOOK_ENTERPRISE, state=state,
            credential_locus=self.auth.credential_locus(),
            evidence_pointer=certification["evidence_pointer"] if certification else None,
            details={"project_number_configured": bool(self.project_number), "location": self.location,
                     "api": "discoveryengine/v1alpha", "readback_required": True,
                     "automatic_owner_truth_promotion": False},
        )

    async def get_notebook(self, notebook_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/notebooks/{quote(notebook_id)}")

    async def list_recent(self, page_size: int = 100) -> list[dict[str, Any]]:
        size = max(1, min(page_size, 500))
        body = await self._request("GET", f"/notebooks:listRecentlyViewed?pageSize={size}")
        return list(body.get("notebooks") or [])

    async def certify(self) -> ProviderStatus:
        notebooks = await self.list_recent(1)
        pointer = f"google://notebook-enterprise/certification/{int(time.time() * 1000)}"
        await self.evidence.certify(
            KnowledgeProvider.NOTEBOOK_ENTERPRISE,
            ProviderState.READY,
            evidence_pointer=pointer,
            details={"list_recent": True, "visible_notebook_count": len(notebooks), "contains_secrets": False},
        )
        return await self.status()

    async def create_notebook(self, request: NotebookEnterpriseCreateRequest) -> NotebookOperationResult:
        digest = self.evidence.digest(request.model_dump())
        op = await self.operations.begin(KnowledgeProvider.NOTEBOOK_ENTERPRISE, "CREATE_NOTEBOOK", request.idempotency_key, digest)
        if op.status == KnowledgeOperationStatus.VERIFIED_SUCCESS:
            return op
        if op.status not in {KnowledgeOperationStatus.PREFLIGHT, KnowledgeOperationStatus.RETRYABLE_FAILURE}:
            return op
        if op.status == KnowledgeOperationStatus.RETRYABLE_FAILURE:
            before_ids = set(op.correlation.get("preexisting_notebook_ids") or [])
            matches = [
                n for n in await self.list_recent(500)
                if str(n.get("title") or "") == request.title
                and str(n.get("notebookId") or "") not in before_ids
            ]
            if len(matches) == 1 and matches[0].get("notebookId"):
                created = matches[0]
            else:
                return op
        else:
            preexisting = await self.list_recent(500)
            preexisting_ids = sorted(
                str(n.get("notebookId")) for n in preexisting
                if n.get("notebookId") and str(n.get("title") or "") == request.title
            )
            await self.operations.update(
                op.operation_id, status=KnowledgeOperationStatus.PREFLIGHT,
                correlation={"preexisting_notebook_ids": preexisting_ids, "title": request.title},
            )
            try:
                created = await self._request("POST", "/notebooks", payload={"title": request.title})
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                return await self.operations.update(
                    op.operation_id, status=KnowledgeOperationStatus.RETRYABLE_FAILURE,
                    correlation={"preexisting_notebook_ids": preexisting_ids, "title": request.title},
                    error_code=type(exc).__name__,
                )
            notebook_id = str(created.get("notebookId") or "")
            if not notebook_id:
                return await self.operations.update(op.operation_id, status=KnowledgeOperationStatus.EXECUTION_FAILED, error_code="CREATE_RESPONSE_MISSING_ID")
            await self.operations.update(op.operation_id, status=KnowledgeOperationStatus.SUBMITTED, resource_id=notebook_id,
                                         correlation={"notebook_id": notebook_id, "title": request.title})
        notebook_id = str(created.get("notebookId") or "")
        observed = await self.get_notebook(notebook_id)
        if str(observed.get("title") or "") != request.title or str(observed.get("notebookId") or "") != notebook_id:
            return await self.operations.update(op.operation_id, status=KnowledgeOperationStatus.VERIFICATION_FAILED,
                                                resource_id=notebook_id, observed=observed, error_code="READBACK_MISMATCH")
        pointer = f"google://notebook-enterprise/{notebook_id}"
        await self.evidence.persist(
            provider=KnowledgeProvider.NOTEBOOK_ENTERPRISE, query_id=op.operation_id, source_ref=pointer,
            title=request.title, source_trust=__import__('van_gateway.context.models', fromlist=['SourceTrust']).SourceTrust.VERIFIED_SYSTEM,
            scope="google-notebook", content=observed, snippet=request.title,
            metadata={"operation": "CREATE_NOTEBOOK", "notebook_id": notebook_id},
        )
        return await self.operations.update(op.operation_id, status=KnowledgeOperationStatus.VERIFIED_SUCCESS,
                                            resource_id=notebook_id, correlation={"notebook_id": notebook_id, "title": request.title},
                                            observed={"notebook_id": notebook_id, "title": request.title}, evidence_pointer=pointer)

    @staticmethod
    def _source_payload(item: Any) -> dict[str, Any]:
        if item.kind == NotebookSourceKind.TEXT:
            return {"textContent": {"sourceName": item.source_name, "content": item.content}}
        if item.kind == NotebookSourceKind.WEB:
            return {"webContent": {"url": item.url, "sourceName": item.source_name}}
        if item.kind == NotebookSourceKind.GOOGLE_DRIVE:
            return {"googleDriveContent": {"documentId": item.document_id, "mimeType": item.mime_type, "sourceName": item.source_name}}
        if item.kind == NotebookSourceKind.YOUTUBE:
            return {"videoContent": {"youtubeUrl": item.url}}
        raise NotebookProviderError("unsupported_notebook_source_kind")

    def _resolve_upload_path(self, raw_path: str) -> Path:
        if not self.upload_root:
            raise NotebookProviderError("notebook_enterprise_upload_root_unconfigured")
        try:
            root = Path(self.upload_root).expanduser().resolve(strict=True)
            candidate = (root / raw_path).resolve(strict=True) if not Path(raw_path).is_absolute() else Path(raw_path).expanduser().resolve(strict=True)
            candidate.relative_to(root)
        except (OSError, ValueError) as exc:
            raise NotebookProviderError("notebook_enterprise_upload_path_denied") from exc
        if not candidate.is_file() or candidate.is_symlink():
            raise NotebookProviderError("notebook_enterprise_upload_file_invalid")
        if candidate.stat().st_size > self.max_upload_bytes:
            raise NotebookProviderError("notebook_enterprise_upload_too_large")
        return candidate

    async def _upload_file(self, notebook_id: str, item: Any) -> dict[str, Any]:
        candidate = self._resolve_upload_path(str(item.file_path or ""))
        token = await self.auth.token()
        url = (
            f"https://{self.location}-discoveryengine.googleapis.com/upload/v1alpha/projects/"
            f"{quote(self.project_number)}/locations/{quote(self.location)}/notebooks/"
            f"{quote(notebook_id)}/sources:uploadFile"
        )
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Goog-Upload-File-Name": item.source_name,
            "X-Goog-Upload-Protocol": "raw",
            "Content-Type": str(item.mime_type),
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds, transport=self.transport) as client:
            with candidate.open("rb") as handle:
                response = await client.post(url, headers=headers, content=handle.read())
        if response.status_code in {401, 403}:
            raise NotebookProviderError(f"notebook_enterprise_authorization_failed:{response.status_code}")
        if response.status_code >= 400:
            raise NotebookProviderError(f"notebook_enterprise_upload_http_{response.status_code}")
        try:
            body = response.json()
        except ValueError as exc:
            raise NotebookProviderError("notebook_enterprise_upload_malformed_response") from exc
        if not isinstance(body, dict):
            raise NotebookProviderError("notebook_enterprise_upload_malformed_response")
        return body

    async def _wait_source_complete(self, notebook_id: str, source_id: str) -> dict[str, Any]:
        current: dict[str, Any] = {}
        for delay in (0.0, 0.5, 1.0, 2.0, 4.0):
            if delay:
                await asyncio.sleep(delay)
            current = await self._request("GET", f"/notebooks/{quote(notebook_id)}/sources/{quote(source_id)}")
            source_obj = (current.get("sources") or [current])[0]
            status = str((source_obj.get("settings") or {}).get("status") or "")
            if status in {"SOURCE_STATUS_COMPLETE", "COMPLETE"}:
                return current
            if "FAILED" in status:
                raise NotebookProviderError("notebook_enterprise_source_processing_failed")
        raise NotebookProviderError("notebook_enterprise_source_still_processing")

    async def add_sources(self, request: NotebookEnterpriseAddSourcesRequest) -> NotebookOperationResult:
        digest = self.evidence.digest(request.model_dump())
        op = await self.operations.begin(KnowledgeProvider.NOTEBOOK_ENTERPRISE, "ADD_SOURCES", request.idempotency_key, digest)
        if op.status == KnowledgeOperationStatus.VERIFIED_SUCCESS:
            return op
        if op.status not in {KnowledgeOperationStatus.PREFLIGHT, KnowledgeOperationStatus.RETRYABLE_FAILURE}:
            return op
        if any(item.kind == NotebookSourceKind.GOOGLE_DRIVE for item in request.sources) and not self.auth.access_token_file:
            return await self.operations.update(
                op.operation_id, status=KnowledgeOperationStatus.CONFIGURATION_REQUIRED,
                error_code="GOOGLE_DRIVE_USER_CREDENTIAL_REQUIRED",
            )
        # A retry resumes only source IDs already submitted by this operation. We do
        # not issue the mutation twice because provider-side request IDs are not
        # documented for this preview API.
        prior_ids = list(op.correlation.get("source_ids") or [])
        if op.status == KnowledgeOperationStatus.RETRYABLE_FAILURE and prior_ids:
            observed: list[dict[str, Any]] = []
            try:
                for source_id in prior_ids:
                    observed.append(await self._wait_source_complete(request.notebook_id, source_id))
            except NotebookProviderError as exc:
                return await self.operations.update(
                    op.operation_id, status=KnowledgeOperationStatus.RETRYABLE_FAILURE,
                    correlation=op.correlation, error_code=str(exc),
                )
            pointer = f"google://notebook-enterprise/{request.notebook_id}/sources/{','.join(prior_ids)}"
            return await self.operations.update(
                op.operation_id, status=KnowledgeOperationStatus.VERIFIED_SUCCESS,
                resource_id=request.notebook_id, correlation=op.correlation,
                observed={"source_ids": prior_ids, "readbacks": observed}, evidence_pointer=pointer,
            )

        batch_items = [item for item in request.sources if item.kind != NotebookSourceKind.FILE]
        file_items = [item for item in request.sources if item.kind == NotebookSourceKind.FILE]
        created_sources: list[dict[str, Any]] = []
        try:
            if batch_items:
                payload = {"userContents": [self._source_payload(item) for item in batch_items]}
                body = await self._request("POST", f"/notebooks/{quote(request.notebook_id)}/sources:batchCreate", payload=payload)
                created_sources.extend(list(body.get("sources") or []))
            for item in file_items:
                created_sources.append(await self._upload_file(request.notebook_id, item))
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            return await self.operations.update(
                op.operation_id, status=KnowledgeOperationStatus.CONFLICTED_STATE,
                error_code=f"AMBIGUOUS_SUBMISSION:{type(exc).__name__}",
            )
        except NotebookProviderError as exc:
            code = str(exc)
            state = KnowledgeOperationStatus.CONFIGURATION_REQUIRED if "unconfigured" in code or "credential" in code else KnowledgeOperationStatus.EXECUTION_FAILED
            return await self.operations.update(op.operation_id, status=state, error_code=code)

        if len(created_sources) != len(request.sources):
            return await self.operations.update(
                op.operation_id, status=KnowledgeOperationStatus.VERIFICATION_FAILED,
                error_code="SOURCE_COUNT_MISMATCH",
                observed={"returned": len(created_sources), "expected": len(request.sources)},
            )
        ids: list[str] = []
        for source in created_sources:
            source_id = str((source.get("sourceId") or {}).get("id") or source.get("sourceId") or "")
            if not source_id:
                return await self.operations.update(op.operation_id, status=KnowledgeOperationStatus.VERIFICATION_FAILED, error_code="SOURCE_ID_MISSING")
            ids.append(source_id)
        await self.operations.update(
            op.operation_id, status=KnowledgeOperationStatus.SUBMITTED,
            resource_id=request.notebook_id,
            correlation={"notebook_id": request.notebook_id, "source_ids": ids, "submitted_by_operation": True},
        )
        observed: list[dict[str, Any]] = []
        try:
            for source_id in ids:
                observed.append(await self._wait_source_complete(request.notebook_id, source_id))
        except NotebookProviderError as exc:
            return await self.operations.update(
                op.operation_id, status=KnowledgeOperationStatus.RETRYABLE_FAILURE,
                resource_id=request.notebook_id,
                correlation={"notebook_id": request.notebook_id, "source_ids": ids, "submitted_by_operation": True},
                observed={"readbacks": observed}, error_code=str(exc),
            )
        pointer = f"google://notebook-enterprise/{request.notebook_id}/sources/{','.join(ids)}"
        return await self.operations.update(
            op.operation_id, status=KnowledgeOperationStatus.VERIFIED_SUCCESS,
            resource_id=request.notebook_id,
            correlation={"notebook_id": request.notebook_id, "source_ids": ids, "submitted_by_operation": True},
            observed={"source_ids": ids, "readbacks": observed}, evidence_pointer=pointer,
        )

    async def delete_notebook(self, request: NotebookEnterpriseDeleteRequest) -> NotebookOperationResult:
        digest = self.evidence.digest(request.model_dump())
        op = await self.operations.begin(KnowledgeProvider.NOTEBOOK_ENTERPRISE, "DELETE_NOTEBOOK", request.idempotency_key, digest)
        if op.status == KnowledgeOperationStatus.VERIFIED_SUCCESS:
            return op
        if op.status != KnowledgeOperationStatus.PREFLIGHT:
            return op
        name = f"projects/{self.project_number}/locations/{self.location}/notebooks/{request.notebook_id}"
        try:
            await self._request("POST", "/notebooks:batchDelete", payload={"names": [name]})
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            return await self.operations.update(
                op.operation_id, status=KnowledgeOperationStatus.CONFLICTED_STATE,
                resource_id=request.notebook_id, error_code=f"AMBIGUOUS_DELETE:{type(exc).__name__}",
            )
        await self.operations.update(
            op.operation_id, status=KnowledgeOperationStatus.SUBMITTED,
            resource_id=request.notebook_id,
            correlation={"notebook_id": request.notebook_id, "submitted_by_operation": True},
        )
        try:
            await self.get_notebook(request.notebook_id)
        except NotebookProviderError as exc:
            if str(exc) == "notebook_enterprise_not_found":
                pointer = f"google://notebook-enterprise/{request.notebook_id}/deleted"
                return await self.operations.update(
                    op.operation_id, status=KnowledgeOperationStatus.VERIFIED_SUCCESS,
                    resource_id=request.notebook_id, correlation={"notebook_id": request.notebook_id},
                    observed={"notebook_absent": True}, evidence_pointer=pointer,
                )
            raise
        return await self.operations.update(
            op.operation_id, status=KnowledgeOperationStatus.VERIFICATION_FAILED,
            resource_id=request.notebook_id, observed={"notebook_absent": False}, error_code="DELETE_READBACK_PRESENT",
        )

    async def delete_sources(self, request: NotebookEnterpriseDeleteSourcesRequest) -> NotebookOperationResult:
        digest = self.evidence.digest(request.model_dump())
        op = await self.operations.begin(KnowledgeProvider.NOTEBOOK_ENTERPRISE, "DELETE_SOURCES", request.idempotency_key, digest)
        if op.status == KnowledgeOperationStatus.VERIFIED_SUCCESS:
            return op
        if op.status != KnowledgeOperationStatus.PREFLIGHT:
            return op
        try:
            await self._request(
                "POST", f"/notebooks/{quote(request.notebook_id)}/sources:batchDelete",
                payload={"names": request.source_names},
            )
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            return await self.operations.update(
                op.operation_id, status=KnowledgeOperationStatus.CONFLICTED_STATE,
                resource_id=request.notebook_id, error_code=f"AMBIGUOUS_DELETE:{type(exc).__name__}",
            )
        await self.operations.update(
            op.operation_id, status=KnowledgeOperationStatus.SUBMITTED,
            resource_id=request.notebook_id,
            correlation={"notebook_id": request.notebook_id, "source_names": sorted(request.source_names), "submitted_by_operation": True},
        )
        still_present: list[str] = []
        for name in request.source_names:
            source_id = name.rsplit("/", 1)[-1]
            try:
                await self._request("GET", f"/notebooks/{quote(request.notebook_id)}/sources/{quote(source_id)}")
                still_present.append(name)
            except NotebookProviderError as exc:
                if str(exc) != "notebook_enterprise_not_found":
                    raise
        if still_present:
            return await self.operations.update(
                op.operation_id, status=KnowledgeOperationStatus.VERIFICATION_FAILED,
                resource_id=request.notebook_id, observed={"still_present": still_present}, error_code="DELETE_READBACK_PRESENT",
            )
        pointer = f"google://notebook-enterprise/{request.notebook_id}/sources/deleted"
        return await self.operations.update(
            op.operation_id, status=KnowledgeOperationStatus.VERIFIED_SUCCESS,
            resource_id=request.notebook_id,
            correlation={"notebook_id": request.notebook_id, "source_names": sorted(request.source_names)},
            observed={"sources_absent": sorted(request.source_names)}, evidence_pointer=pointer,
        )


class NotebookConsumerProvider:
    """Deterministic browser bridge for the owner's personal NotebookLM session.

    No cookies are exported. A persistent Chromium profile is used in place and
    every mutation is followed by UI readback. DOM changes fail closed.
    """

    def __init__(self, store: Store, evidence: KnowledgeEvidenceStore, *, enabled: bool,
                 profile_dir: str, base_url: str = "https://notebooklm.google.com",
                 headless: bool = True, timeout_seconds: float = 20.0) -> None:
        self.store = store
        self.evidence = evidence
        self.enabled = enabled
        self.profile_dir = profile_dir.strip()
        self.base_url = base_url.rstrip("/")
        self.headless = headless
        self.timeout_ms = int(timeout_seconds * 1000)
        self.operations = NotebookOperationStore(store)

    async def status(self) -> ProviderStatus:
        certification = await self.evidence.certification(KnowledgeProvider.NOTEBOOK_CONSUMER)
        if not self.enabled:
            state = ProviderState.DISABLED
        elif not self.profile_dir:
            state = ProviderState.UNCONFIGURED
        elif certification and certification["state"] == ProviderState.READY.value:
            state = ProviderState.READY
        else:
            state = ProviderState.CONFIGURED
        return ProviderStatus(
            provider=KnowledgeProvider.NOTEBOOK_CONSUMER, state=state,
            credential_locus="owner-consumer-session-profile",
            evidence_pointer=certification["evidence_pointer"] if certification else None,
            details={"cookie_export_allowed": False, "persistent_profile": bool(self.profile_dir),
                     "readback_required": True, "automatic_owner_truth_promotion": False},
        )

    async def _browser(self):
        if not self.enabled:
            raise NotebookProviderError("notebook_consumer_disabled")
        if not self.profile_dir:
            raise NotebookProviderError("notebook_consumer_profile_unconfigured")
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise NotebookProviderError("playwright_unavailable") from exc
        p = await async_playwright().start()
        try:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=str(Path(self.profile_dir).expanduser()), headless=self.headless,
            )
        except Exception as exc:
            await p.stop()
            raise NotebookProviderError("notebook_consumer_browser_unavailable") from exc
        return p, context

    async def ask(self, request: NotebookConsumerAskRequest) -> NotebookGroundedAnswer:
        p, context = await self._browser()
        page = context.pages[0] if context.pages else await context.new_page()
        query_id = str(uuid.uuid4())
        try:
            await page.goto(f"{self.base_url}/notebook/{quote(request.notebook_id)}", wait_until="domcontentloaded", timeout=self.timeout_ms)
            await page.wait_for_timeout(800)
            if "accounts.google." in page.url or await page.get_by_text(re.compile(r"^sign in$", re.I)).count():
                raise NotebookProviderError("notebook_consumer_session_auth_required")
            prompt = page.get_by_role("textbox", name=re.compile(r"ask|question|chat|prompt", re.I))
            if await prompt.count() == 0:
                prompt = page.locator('textarea[placeholder*="ask" i], input[placeholder*="ask" i], textarea[placeholder*="question" i]')
            if await prompt.count() == 0:
                raise NotebookProviderError("notebook_consumer_prompt_control_not_found")
            selectors = (
                '[data-message-author="assistant"]',
                '[data-testid*="response" i]',
                '[class*="response-content" i]',
                '[class*="chat-response" i]',
            )
            before: dict[str, int] = {}
            for selector in selectors:
                before[selector] = await page.locator(selector).count()
            await prompt.last.fill(request.question)
            await prompt.last.press("Enter")
            deadline = time.monotonic() + (self.timeout_ms / 1000.0)
            answer = ""
            while time.monotonic() < deadline:
                await page.wait_for_timeout(400)
                for selector in selectors:
                    nodes = page.locator(selector)
                    count = await nodes.count()
                    if count <= before[selector]:
                        continue
                    candidate = (await nodes.last.inner_text()).strip()
                    if candidate and candidate.casefold() != request.question.casefold() and len(candidate) >= 2:
                        answer = candidate
                        break
                if answer:
                    break
            if not answer:
                raise NotebookProviderError("notebook_consumer_answer_readback_failed")
            pointer = f"google://notebook-consumer/{request.notebook_id}/query/{query_id}"
            await self.evidence.persist(
                provider=KnowledgeProvider.NOTEBOOK_CONSUMER,
                query_id=query_id,
                source_ref=pointer,
                title=f"Notebook answer: {request.question[:120]}",
                source_trust=__import__('van_gateway.context.models', fromlist=['SourceTrust']).SourceTrust.VERIFIED_SYSTEM,
                scope=request.scope,
                content={"notebook_id": request.notebook_id, "question": request.question, "answer": answer},
                snippet=answer,
                metadata={"operation": "GROUNDED_ASK", "browser_readback": True},
            )
            return NotebookGroundedAnswer(
                query_id=query_id,
                notebook_id=request.notebook_id,
                question=request.question,
                answer=answer,
                evidence_pointer=pointer,
            )
        finally:
            await context.close()
            await p.stop()

    async def certify(self, request: NotebookConsumerAskRequest) -> ProviderStatus:
        result = await self.ask(request)
        await self.evidence.certify(
            KnowledgeProvider.NOTEBOOK_CONSUMER,
            ProviderState.READY,
            evidence_pointer=result.evidence_pointer,
            details={"notebook_id": request.notebook_id, "grounded_ask": True, "contains_secrets": False},
        )
        return await self.status()

    async def create_note(self, request: NotebookConsumerNoteCreateRequest) -> NotebookOperationResult:
        digest = self.evidence.digest(request.model_dump())
        op = await self.operations.begin(KnowledgeProvider.NOTEBOOK_CONSUMER, "CREATE_NOTE", request.idempotency_key, digest)
        if op.status == KnowledgeOperationStatus.VERIFIED_SUCCESS:
            return op
        if op.status not in {KnowledgeOperationStatus.PREFLIGHT, KnowledgeOperationStatus.RETRYABLE_FAILURE}:
            return op
        p, context = await self._browser()
        page = context.pages[0] if context.pages else await context.new_page()
        try:
            await page.goto(f"{self.base_url}/notebook/{quote(request.notebook_id)}", wait_until="domcontentloaded", timeout=self.timeout_ms)
            await page.wait_for_timeout(800)
            if "accounts.google." in page.url or await page.get_by_text(re.compile(r"^sign in$", re.I)).count():
                return await self.operations.update(op.operation_id, status=KnowledgeOperationStatus.CONFIGURATION_REQUIRED,
                                                    error_code="CONSUMER_SESSION_AUTH_REQUIRED")
            exact = page.get_by_text(request.title, exact=True)
            if await exact.count() > 0:
                prior_submission = bool(op.correlation.get("submitted_by_operation"))
                if not prior_submission:
                    return await self.operations.update(
                        op.operation_id, status=KnowledgeOperationStatus.VERIFICATION_FAILED,
                        observed={"title": request.title, "preexisting": True},
                        error_code="PREEXISTING_NOTE_AMBIGUOUS",
                    )
                pointer = f"google://notebook-consumer/{request.notebook_id}/note/{quote(request.title)}"
                return await self.operations.update(op.operation_id, status=KnowledgeOperationStatus.VERIFIED_SUCCESS,
                                                    resource_id=request.title, correlation=op.correlation,
                                                    observed={"title": request.title, "readback_after_prior_submission": True}, evidence_pointer=pointer)
            add = page.get_by_role("button", name=re.compile(r"add note|new note|create note", re.I))
            if await add.count() == 0:
                add = page.get_by_text(re.compile(r"^add note$|^new note$", re.I))
            if await add.count() == 0:
                return await self.operations.update(op.operation_id, status=KnowledgeOperationStatus.EXECUTION_FAILED,
                                                    error_code="NOTE_CREATE_CONTROL_NOT_FOUND")
            await add.first.click()
            await page.wait_for_timeout(300)
            title_input = page.get_by_role("textbox", name=re.compile(r"title|note title", re.I))
            if await title_input.count() == 0:
                title_input = page.locator('input[placeholder*="title" i], textarea[placeholder*="title" i]')
            if await title_input.count() == 0:
                return await self.operations.update(op.operation_id, status=KnowledgeOperationStatus.EXECUTION_FAILED,
                                                    error_code="NOTE_TITLE_EDITOR_NOT_FOUND")
            await title_input.last.fill(request.title)
            if request.body:
                body_input = page.get_by_role("textbox", name=re.compile(r"note|body|content", re.I))
                if await body_input.count() > 1:
                    await body_input.last.fill(request.body)
                else:
                    editable = page.locator('[contenteditable="true"]')
                    if await editable.count():
                        await editable.last.fill(request.body)
            save = page.get_by_role("button", name=re.compile(r"save|done|create", re.I))
            if await save.count():
                await save.last.click()
            else:
                await title_input.last.press("Tab")
            await self.operations.update(op.operation_id, status=KnowledgeOperationStatus.SUBMITTED,
                                         correlation={"notebook_id": request.notebook_id, "title": request.title,
                                                      "submitted_by_operation": True})
            try:
                await page.get_by_text(request.title, exact=True).first.wait_for(state="visible", timeout=self.timeout_ms)
            except Exception:
                return await self.operations.update(op.operation_id, status=KnowledgeOperationStatus.VERIFICATION_FAILED,
                                                    error_code="NOTE_READBACK_FAILED")
            pointer = f"google://notebook-consumer/{request.notebook_id}/note/{quote(request.title)}"
            evidence_payload = {"notebook_id": request.notebook_id, "title": request.title, "url_host": "notebooklm.google.com"}
            await self.evidence.persist(
                provider=KnowledgeProvider.NOTEBOOK_CONSUMER, query_id=op.operation_id, source_ref=pointer,
                title=request.title, source_trust=__import__('van_gateway.context.models', fromlist=['SourceTrust']).SourceTrust.VERIFIED_SYSTEM,
                scope="google-notebook", content=evidence_payload, snippet=request.title,
                metadata={"operation": "CREATE_NOTE", "browser_readback": True},
            )
            return await self.operations.update(op.operation_id, status=KnowledgeOperationStatus.VERIFIED_SUCCESS,
                                                resource_id=request.title, correlation={"notebook_id": request.notebook_id, "title": request.title},
                                                observed={"title": request.title, "visible": True}, evidence_pointer=pointer)
        except NotebookProviderError:
            raise
        except Exception as exc:
            return await self.operations.update(op.operation_id, status=KnowledgeOperationStatus.RETRYABLE_FAILURE,
                                                error_code=type(exc).__name__)
        finally:
            await context.close()
            await p.stop()