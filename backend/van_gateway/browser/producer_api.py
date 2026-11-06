"""Private authenticated producer API. No owner credential crosses this surface."""
from __future__ import annotations

from typing import Any, Literal
from urllib.parse import quote, urlsplit

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from van_gateway.auth.control_scopes import ControlScope, require_scoped_internal
from van_gateway.browser.interactive_service import InteractiveSessionError
from van_gateway.browser.downloads import DownloadError
from van_gateway.browser.producer_service import BrowserProducerService, ProducerError, credential_principal
from van_gateway.browser.stream_grants import StreamGrantError
from van_gateway.browser.stream_routes import parse_profile_signal_urls, signal_url_for_profile


STREAM_PRODUCER_PREFIX = "/v1/browser/stream-producer"
CONTROL_PRODUCER_PREFIX = "/v1/browser/control-producer"


def is_browser_producer_consumer_route(path: str) -> bool:
    return (path == STREAM_PRODUCER_PREFIX or path.startswith(STREAM_PRODUCER_PREFIX + "/")
            or path in {CONTROL_PRODUCER_PREFIX + "/authorize-call", CONTROL_PRODUCER_PREFIX + "/validate-call",
                        CONTROL_PRODUCER_PREFIX + "/validate-result"})


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class RedeemBody(StrictBody):
    stream_grant: str = Field(min_length=1, max_length=16384)
    producer_session_id: str = Field(min_length=16, max_length=128)


class InputAuthorityBody(StrictBody):
    session_id: str = Field(min_length=1, max_length=128)
    control_lease_id: str = Field(min_length=1, max_length=128)
    control_generation: int = Field(ge=1)
    viewport_revision: int = Field(ge=1)


class ObservationBody(StrictBody):
    event: Literal["allocated", "signaling", "connecting", "first_frame", "reconnecting", "target", "target_closed", "failed", "closed"]
    viewport_revision: int | None = Field(default=None, ge=1)
    frame_sequence: int | None = Field(default=None, ge=1)
    media_epoch: str | None = Field(default=None, max_length=128)
    width: int | None = Field(default=None, ge=1, le=2400)
    height: int | None = Field(default=None, ge=1, le=2400)
    target_id: str | None = Field(default=None, min_length=1, max_length=128)
    url: str | None = Field(default=None, min_length=1, max_length=8192)
    title: str | None = Field(default=None, max_length=512)
    codec: str | None = Field(default=None, max_length=32)
    transport: str | None = Field(default=None, max_length=32)
    reason: str | None = Field(default=None, max_length=256)


class ControlGrantBody(StrictBody):
    task_id: str = Field(min_length=1, max_length=128)
    session_id: str = Field(min_length=1, max_length=128)
    target_id: str = Field(min_length=1, max_length=128)
    caller_common_name: str = Field(min_length=1, max_length=128)
    proxy_principal_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    scope: Literal["browser.observe", "browser.actuate", "browser.evidence"]
    step_budget: int = Field(ge=1, le=50)
    deadline_ms: int = Field(gt=0)


class ControlCallBody(StrictBody):
    operation: Literal["attach", "navigate", "dispatch_input", "query_dom", "query_accessibility", "observe_navigation", "observe_download", "capture_evidence", "click_element", "fill_element", "observe_effect"]
    session_id: str = Field(min_length=1, max_length=128)
    target_id: str = Field(min_length=1, max_length=128)
    lease_id: str = Field(min_length=1, max_length=128)
    lease_generation: int = Field(ge=1)
    task_id: str = Field(min_length=1, max_length=128)
    caller_common_name: str = Field(min_length=1, max_length=128)


    params: dict[str, Any] = Field(default_factory=dict)


class ChooserBody(StrictBody):
    chooser_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    target_id: str = Field(min_length=1, max_length=128)


class DownloadReportBody(StrictBody):
    event: Literal["started", "finished", "failed", "deleted"]
    download_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    target_id: str = Field(min_length=1, max_length=128)
    suggested_name: str | None = Field(default=None, max_length=180)
    declared_mime: str | None = Field(default=None, max_length=128)
    url_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    byte_size: int | None = Field(default=None, ge=0, le=64 * 1024 * 1024)
    content_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    observed_mime: str | None = Field(default=None, max_length=128)
    reason: str | None = Field(default=None, max_length=256)


class FileResultBody(StrictBody):
    transfer_id: str = Field(min_length=1, max_length=128)
    operation: Literal["analyse"]
    resource_id: str = Field(min_length=1, max_length=128)
    receipt: dict[str, Any]


class TransferBody(StrictBody):
    operation: Literal["download", "upload", "paste", "copy", "analyse", "file_import"]
    target_id: str = Field(min_length=1, max_length=128)
    download_id: str | None = Field(default=None, max_length=128)
    chooser_id: str | None = Field(default=None, max_length=128)
    byte_size: int | None = Field(default=None, ge=0, le=64 * 1024 * 1024)
    content_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    suggested_name: str | None = Field(default=None, max_length=180)
    mime_type: str | None = Field(default=None, max_length=128)


class ConsumeTransferBody(StrictBody):
    transfer_grant: str = Field(min_length=32, max_length=128)
    operation: Literal["download", "upload", "paste", "copy", "analyse", "file_import"]
    resource_id: str = Field(min_length=1, max_length=128)
    content_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    byte_size: int | None = Field(default=None, ge=0, le=64 * 1024 * 1024)


def build_browser_producer_router(*, service: BrowserProducerService, settings: Any,
                                 audit: Any | None = None) -> APIRouter:
    router = APIRouter(prefix="/v1/browser", tags=["browser-producer"])
    base_signal_url = getattr(settings, "browser_stream_signal_url", "")
    profile_urls = parse_profile_signal_urls(getattr(settings, "browser_stream_profile_signal_urls", "{}"), manifest_base_url=base_signal_url)
    for alias in profile_urls:
        service.sessions.broker.policy.check_profile(alias)

    def principal(token: str | None, *, issuer: bool = False) -> str:
        require_scoped_internal(settings, token, ControlScope.BROWSER if issuer else ControlScope.BROWSER_STREAM_PRODUCER)
        return credential_principal(token or "")

    async def guarded(operation):
        try:
            return await operation
        except (ProducerError, StreamGrantError, InteractiveSessionError, DownloadError) as exc:
            code = str(exc)
            status = 404 if code.endswith("_unknown") else 409
            if code in {"stream_grant_malformed", "stream_grant_signature_invalid", "stream_grant_algorithm_not_accepted"}:
                status = 403
            raise HTTPException(status_code=status, detail=code) from exc
        except (ValueError, TypeError, KeyError, UnicodeDecodeError) as exc:
            # Malformed untrusted grants must not turn into internal-server failures.
            raise HTTPException(status_code=403, detail="stream_grant_malformed") from exc

    @router.post("/stream-producer/redeem")
    async def redeem(body: RedeemBody, x_van_internal_token: str | None = Header(default=None)):
        p = principal(x_van_internal_token)
        return await guarded(service.redeem(principal=p, **body.model_dump()))

    @router.post("/stream-producer/{producer_session_id}/authority")
    async def authority(producer_session_id: str, body: StrictBody, x_van_internal_token: str | None = Header(default=None)):
        p = principal(x_van_internal_token)
        return await guarded(service.authority(producer_session_id=producer_session_id, principal=p))

    @router.post("/stream-producer/{producer_session_id}/authorize-input")
    async def authorize_input(producer_session_id: str, body: InputAuthorityBody, x_van_internal_token: str | None = Header(default=None)):
        p = principal(x_van_internal_token)
        return await guarded(service.authorize_input(producer_session_id=producer_session_id, principal=p, **body.model_dump()))

    @router.post("/stream-producer/{producer_session_id}/observe")
    async def observe(producer_session_id: str, body: ObservationBody, x_van_internal_token: str | None = Header(default=None)):
        p = principal(x_van_internal_token)
        return await guarded(service.observe(producer_session_id=producer_session_id, principal=p, **body.model_dump(exclude_none=True)))

    @router.post("/control-producer/grants")
    async def issue_control_grant(body: ControlGrantBody, x_van_internal_token: str | None = Header(default=None)):
        principal(x_van_internal_token, issuer=True)
        return await guarded(service.issue_control_grant(**body.model_dump()))

    @router.post("/stream-producer/{producer_session_id}/file-results")
    async def file_result(producer_session_id: str, body: FileResultBody, x_van_internal_token: str | None = Header(default=None)):
        p = principal(x_van_internal_token)
        return await guarded(service.report_file_result(producer_session_id=producer_session_id, principal=p, **body.model_dump()))

    @router.post("/control-producer/authorize-call")
    async def authorize_call(body: ControlCallBody, x_van_internal_token: str | None = Header(default=None)):
        p = principal(x_van_internal_token)
        return await guarded(service.authorize_call(principal=p, **body.model_dump()))

    @router.post("/control-producer/validate-call")
    async def validate_call(body: ControlCallBody, x_van_internal_token: str | None = Header(default=None)):
        p = principal(x_van_internal_token)
        return await guarded(service.validate_call(principal=p, **body.model_dump()))

    @router.post("/control-producer/validate-result")
    async def validate_result(body: ControlCallBody, x_van_internal_token: str | None = Header(default=None)):
        p = principal(x_van_internal_token)
        return await guarded(service.validate_result(principal=p, **body.model_dump()))

    @router.post("/stream-producer/{producer_session_id}/chooser")
    async def chooser(producer_session_id: str, body: ChooserBody, x_van_internal_token: str | None = Header(default=None)):
        p = principal(x_van_internal_token)
        return await guarded(service.register_chooser(producer_session_id=producer_session_id, principal=p, **body.model_dump()))

    @router.post("/stream-producer/{producer_session_id}/downloads")
    async def downloads(producer_session_id: str, body: DownloadReportBody, x_van_internal_token: str | None = Header(default=None)):
        p = principal(x_van_internal_token)
        return await guarded(service.report_download(producer_session_id=producer_session_id, principal=p, **body.model_dump(exclude_none=True)))

    @router.post("/stream-producer/{producer_session_id}/consume-transfer-grant")
    async def consume_transfer(producer_session_id: str, body: ConsumeTransferBody, x_van_internal_token: str | None = Header(default=None)):
        p = principal(x_van_internal_token)
        return await guarded(service.consume_transfer_grant(producer_session_id=producer_session_id, principal=p, **body.model_dump()))

    @router.post("/interactive-sessions/{session_id}/transfer-grants")
    async def transfer_grant(request: Request, session_id: str, body: TransferBody):
        device_id = getattr(request.state, "van_device_id", None)
        session = await service.sessions.get(session_id)
        if not device_id:
            raise HTTPException(status_code=403, detail="device_identity_required")
        if session is None or session.owner_device_id != device_id:
            raise HTTPException(status_code=404, detail="interactive_session_unknown")
        # Owner proof is enforced by the gateway middleware for every mutation under
        # the interactive session prefix, before this handler is allowed to mint.
        selected_signal_url = signal_url_for_profile(session.profile_alias, profile_urls=profile_urls, fallback_url=base_signal_url)
        signal = urlsplit(selected_signal_url)
        if signal.scheme != "https" or not signal.hostname or signal.username or signal.password or signal.query or signal.fragment:
            raise HTTPException(status_code=503, detail="BROWSER_STREAM_UNCONFIGURED")
        result = await guarded(service.issue_transfer_grant(session_id=session_id, owner_device_id=device_id, **body.model_dump()))
        if audit is not None:
            await audit.record(result="ok", device_id=device_id, capability="browser.owner.transfer.authorize",
                after={"session_id": session_id, "producer_session_id": result["producer_session_id"],
                       "operation": result["operation"], "resource_id": result["resource_id"],
                       "content_sha256": result.get("content_sha256"), "byte_size": result.get("byte_size")})
        base = selected_signal_url.rstrip("/")
        path = {"download": "/files/download/", "upload": "/files/upload/", "paste": "/clipboard/paste", "copy": "/clipboard/copy", "analyse": "/files/analyse/", "file_import": "/files/import/"}[body.operation]
        resource = quote(result["resource_id"], safe="") if body.operation in {"download", "upload", "analyse", "file_import"} else ""
        result["host_url"] = base + path + resource
        return result

    return router
