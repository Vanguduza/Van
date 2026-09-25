"""`/v1/dial-dev/*` — the owner surface over DIAL's Development Projection API v1.

Authentication is not decided here. The gateway middleware already requires the ingress
token and a paired device token on every non-control route, and `requires_device_proof`
names `ACTIONS_PATH`, so the one mutation cannot reach this module without a verified
hardware device proof. The handler re-checks that the proof was verified, because a
deployment without a bound device would otherwise let a token alone reach DIAL.

Responses:

* a projection read passes DIAL's envelope through byte for byte, status included, for
  2xx and for DIAL's own 4xx answers (404 unknown id, 409 STALE_VIEW, 422 refusals);
* DIAL unreachable, timing out, refusing VAN's credential or answering 5xx is
  `503 {"error": "dial_dev_unavailable", "reason": <fixed vocabulary>}`;
* the feature switched off is `404 {"error": "dial_dev_disabled"}`;
* a request the gateway refuses before asking DIAL is
  `422 {"error": "dial_dev_request_invalid", "reason": ...}`.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.background import BackgroundTask

from van_gateway.dial_dev.client import (
    DialDevClient,
    DialDevDisabled,
    DialDevUnavailable,
    UpstreamResponse,
)
from van_gateway.dial_dev.config import (
    ACTIONS,
    DECISIONS,
    ENVELOPE_KEYS,
    HUB_CHILDREN,
    PREFIX,
    TASK_SCOPED_ACTIONS,
    TASK_VIEWS,
    TERMINAL_TAIL_MAX_LINES,
    UPSTREAM_PREFIX,
    DialDevConfig,
    valid_identifier,
)
from van_gateway.dial_dev import degraded as dial_degraded
from van_gateway.degraded.registry import DegradedRegistry
from van_gateway.idempotency.service import (
    IdempotencyConflict,
    IdempotencyInFlight,
    IdempotencyService,
)

log = logging.getLogger("van_gateway.dial_dev")

STALE_HEADER = "X-Van-Dial-Dev-Stale-After-Ms"
REPLAY_HEADER = "X-Van-Idempotent-Replay"
_NO_STORE = {"Cache-Control": "no-store"}


def disabled_response() -> JSONResponse:
    return JSONResponse(status_code=404, content={"error": "dial_dev_disabled"}, headers=_NO_STORE)


def unavailable_response(reason: str) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"error": "dial_dev_unavailable", "reason": reason},
        headers=_NO_STORE,
    )


def invalid_response(reason: str, error: str = "dial_dev_request_invalid") -> JSONResponse:
    return JSONResponse(status_code=422, content={"error": error, "reason": reason}, headers=_NO_STORE)


class DialDevActionBody(BaseModel):
    """§3.3, as the device sends it. Closed: an unknown field is a refusal."""

    model_config = ConfigDict(extra="forbid")

    action: str
    target: dict[str, Any]
    params: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=8, max_length=128)
    #: §3.3 — an owner action requires a live projection revision; never queued offline.
    expected_projection_revision: str = Field(min_length=1, max_length=256)
    #: Accepted for shape compatibility and ignored: the gateway, not the device, states
    #: which verified proof authorised the forward.
    owner_device_proof_ref: str | None = None


def _check_action(body: DialDevActionBody) -> str | None:
    """Why the gateway refuses this action before DIAL sees it, or None."""
    if body.action not in ACTIONS:
        return "action_not_allowed"
    project_id = body.target.get("project_id")
    if not isinstance(project_id, str) or not valid_identifier(project_id):
        return "target.project_id"
    for key in ("task_id", "decision_id"):
        value = body.target.get(key)
        if value is not None and (not isinstance(value, str) or not valid_identifier(value)):
            return f"target.{key}"
    if body.action in TASK_SCOPED_ACTIONS and not body.target.get("task_id"):
        return "target.task_id"
    if body.action == "STEER_TASK":
        guidance = body.params.get("guidance")
        if not isinstance(guidance, str) or not guidance.strip() or len(guidance) > 4000:
            return "params.guidance"
    if body.action == "DECIDE":
        if not body.target.get("decision_id"):
            return "target.decision_id"
        if str(body.params.get("decision", "")).upper() not in DECISIONS:
            return "params.decision"
    return None


def owner_device_proof_ref(request: Request, device_id: str) -> str:
    """A reference to the proof the middleware verified, minted by the gateway.

    It identifies the signed request without carrying the signature's secret half (there
    is none to carry) or any VAN credential, so DIAL can record *which* verified owner
    request authorised an action without ever holding VAN authority.
    """
    material = "\n".join((
        device_id,
        request.headers.get("X-Van-Device-Proof-Issued-At", ""),
        request.headers.get("X-Van-Device-Proof", ""),
    ))
    return "van-device-proof:sha256:" + hashlib.sha256(material.encode("utf-8")).hexdigest()


def build_dial_dev_router(
    *,
    client: DialDevClient,
    config: DialDevConfig,
    idempotency: IdempotencyService,
    degraded: DegradedRegistry | None = None,
    audit: Any | None = None,
) -> APIRouter:
    router = APIRouter(prefix=PREFIX, tags=["dial-dev"])

    def _mark_down(exc: DialDevUnavailable) -> JSONResponse:
        dial_degraded.mark_unavailable(degraded, True)
        log.warning("dial_dev upstream unavailable: %s", exc.reason)
        return unavailable_response(exc.reason)

    def _projection(upstream: UpstreamResponse, stale_ms: int) -> Response:
        status = upstream.status_code
        if status in (401, 403):
            # VAN's credential was refused. The device is authenticated; this is VAN's
            # misconfiguration, and saying 401 to the phone would send it to re-pair.
            return _mark_down(DialDevUnavailable("upstream_auth_refused"))
        if 300 <= status < 400:
            return _mark_down(DialDevUnavailable("upstream_redirect"))
        if status >= 500 or status < 200:
            return _mark_down(DialDevUnavailable("upstream_error"))
        try:
            parsed = json.loads(upstream.body)
        except (ValueError, UnicodeDecodeError):
            return _mark_down(DialDevUnavailable("upstream_malformed"))
        if 200 <= status < 300:
            if not isinstance(parsed, dict) or any(key not in parsed for key in ENVELOPE_KEYS):
                return _mark_down(DialDevUnavailable("upstream_malformed"))
            dial_degraded.apply_envelope(degraded, parsed)
        else:
            dial_degraded.mark_unavailable(degraded, False)
        return Response(
            content=upstream.body,
            status_code=status,
            media_type="application/json",
            headers={**_NO_STORE, STALE_HEADER: str(stale_ms)},
        )

    async def _read(upstream_path: str, *, params: dict[str, Any] | None = None,
                    stale_ms: int | None = None) -> Response:
        try:
            upstream = await client.get(upstream_path, params=params)
        except DialDevDisabled:
            return disabled_response()
        except DialDevUnavailable as exc:
            return _mark_down(exc)
        return _projection(upstream, stale_ms or config.stale_ms)

    def _seg(value: str) -> str | None:
        return quote(value, safe="") if valid_identifier(value) else None

    # ------------------------------------------------------------------ reads (§3.2)

    @router.get("/projects")
    async def projects():
        return await _read(f"{UPSTREAM_PREFIX}/projects")

    @router.get("/projects/{project_id}/home")
    async def project_home(project_id: str):
        seg = _seg(project_id)
        if seg is None:
            return invalid_response("project_id")
        return await _read(f"{UPSTREAM_PREFIX}/projects/{seg}/home")

    @router.get("/projects/{project_id}/stage-plan")
    async def project_stage_plan(project_id: str):
        seg = _seg(project_id)
        if seg is None:
            return invalid_response("project_id")
        return await _read(f"{UPSTREAM_PREFIX}/projects/{seg}/stage-plan")

    @router.get("/projects/{project_id}/tasks")
    async def project_tasks(project_id: str, view: str | None = None):
        seg = _seg(project_id)
        if seg is None:
            return invalid_response("project_id")
        if view not in TASK_VIEWS:
            return invalid_response("view")
        return await _read(f"{UPSTREAM_PREFIX}/projects/{seg}/tasks", params={"view": view})

    @router.get("/projects/{project_id}/graph")
    async def project_graph(project_id: str):
        seg = _seg(project_id)
        if seg is None:
            return invalid_response("project_id")
        return await _read(f"{UPSTREAM_PREFIX}/projects/{seg}/graph")

    @router.get("/tasks/{task_id}")
    async def task(task_id: str):
        seg = _seg(task_id)
        if seg is None:
            return invalid_response("task_id")
        return await _read(f"{UPSTREAM_PREFIX}/tasks/{seg}")

    @router.get("/agents")
    async def agents():
        return await _read(f"{UPSTREAM_PREFIX}/agents")

    @router.get("/workspaces")
    async def workspaces():
        return await _read(f"{UPSTREAM_PREFIX}/workspaces", stale_ms=config.workspaces_stale_ms)

    @router.get("/workspaces/{workspace_id}")
    async def workspace(workspace_id: str):
        seg = _seg(workspace_id)
        if seg is None:
            return invalid_response("workspace_id")
        return await _read(
            f"{UPSTREAM_PREFIX}/workspaces/{seg}", stale_ms=config.workspaces_stale_ms
        )

    @router.get("/workspaces/{workspace_id}/diff")
    async def workspace_diff(workspace_id: str):
        seg = _seg(workspace_id)
        if seg is None:
            return invalid_response("workspace_id")
        return await _read(
            f"{UPSTREAM_PREFIX}/workspaces/{seg}/diff", stale_ms=config.workspaces_stale_ms
        )

    @router.get("/workspaces/{workspace_id}/terminal-tail")
    async def workspace_terminal_tail(workspace_id: str, lines: str | None = None):
        seg = _seg(workspace_id)
        if seg is None:
            return invalid_response("workspace_id")
        count = TERMINAL_TAIL_MAX_LINES
        if lines is not None:
            try:
                count = int(lines)
            except ValueError:
                return invalid_response("lines")
            if not 1 <= count <= TERMINAL_TAIL_MAX_LINES:
                return invalid_response("lines")
        return await _read(
            f"{UPSTREAM_PREFIX}/workspaces/{seg}/terminal-tail",
            params={"lines": count},
            stale_ms=config.workspaces_stale_ms,
        )

    def _hub_child(child: str):
        async def handler():
            return await _read(f"{UPSTREAM_PREFIX}/{child}")
        handler.__name__ = f"hub_{child}"
        return handler

    for child in HUB_CHILDREN:
        router.add_api_route(f"/{child}", _hub_child(child), methods=["GET"])

    @router.get("/evidence/{evidence_ref}")
    async def evidence(evidence_ref: str):
        seg = _seg(evidence_ref)
        if seg is None:
            return invalid_response("evidence_ref")
        return await _read(f"{UPSTREAM_PREFIX}/evidence/{seg}")

    @router.get("/infrastructure")
    async def infrastructure():
        return await _read(f"{UPSTREAM_PREFIX}/infrastructure")

    # --------------------------------------------------------------- events (§3.2)

    @router.get("/events")
    async def events():
        """SSE passthrough of `{projection_revision, changed[]}` frames.

        Relayed line by line. A line that would disclose VAN's DIAL credential is dropped,
        so the stream cannot become the one path the credential reaches Android on.
        """
        try:
            stream = await client.open_stream(f"{UPSTREAM_PREFIX}/events")
        except DialDevDisabled:
            return disabled_response()
        except DialDevUnavailable as exc:
            return _mark_down(exc)
        status = stream.response.status_code
        if status != 200:
            await stream.close()
            if status in (401, 403):
                return _mark_down(DialDevUnavailable("upstream_auth_refused"))
            return _mark_down(DialDevUnavailable("upstream_error"))
        dial_degraded.mark_unavailable(degraded, False)

        async def frames():
            async for line in stream.lines():
                if stream.discloses_credential(line):
                    continue
                yield line + "\n"

        return StreamingResponse(
            frames(),
            media_type="text/event-stream",
            headers={**_NO_STORE, "X-Accel-Buffering": "no"},
            background=BackgroundTask(stream.close),
        )

    # -------------------------------------------------------------- actions (§3.3)

    @router.post("/actions")
    async def actions(request: Request):
        device_id = getattr(request.state, "van_device_id", "")
        if not device_id:
            return JSONResponse(status_code=401, content={"error": "owner_device_required"})
        if not getattr(request.state, "van_device_proved", False):
            # The middleware lets an unbound device through on its token alone while a
            # deployment migrates. An action on DIAL is not allowed that downgrade.
            return JSONResponse(status_code=403, content={"error": "device_proof_required"})
        if not config.enabled:
            return disabled_response()
        try:
            raw = await request.json()
        except (ValueError, UnicodeDecodeError):
            return invalid_response("body")
        if not isinstance(raw, dict):
            return invalid_response("body")
        try:
            body = DialDevActionBody.model_validate(raw)
        except ValidationError as exc:
            first = exc.errors()[0] if exc.errors() else {}
            where = ".".join(str(part) for part in first.get("loc", ())) or "body"
            return invalid_response(where)
        refusal = _check_action(body)
        if refusal == "action_not_allowed":
            return invalid_response(refusal, error="dial_dev_action_not_allowed")
        if refusal is not None:
            return invalid_response(refusal)

        request_fields = {
            "action": body.action,
            "target": body.target,
            "params": body.params,
            "idempotency_key": body.idempotency_key,
            "expected_projection_revision": body.expected_projection_revision,
        }
        key = f"dial-dev:{body.idempotency_key}"
        try:
            prior = await idempotency.begin(key, request_fields)
        except IdempotencyConflict:
            return JSONResponse(status_code=409, content={"error": "idempotency_conflict"})
        except IdempotencyInFlight:
            return JSONResponse(status_code=409, content={"error": "idempotency_in_flight"})
        if prior is not None:
            return JSONResponse(
                status_code=int(prior.get("status_code", 202)),
                content=prior.get("body", {}),
                headers={**_NO_STORE, REPLAY_HEADER: "true"},
            )

        forward = {**request_fields, "owner_device_proof_ref": owner_device_proof_ref(request, device_id)}
        try:
            upstream = await client.post(f"{UPSTREAM_PREFIX}/actions", forward)
        except DialDevDisabled:
            await idempotency.fail(key, {"error": "dial_dev_disabled"})
            return disabled_response()
        except DialDevUnavailable as exc:
            # FAILED, not COMPLETED: the same request may be retried under the same key,
            # and DIAL de-duplicates on that key if the first attempt did land.
            await idempotency.fail(key, {"error": "dial_dev_unavailable", "reason": exc.reason})
            return _mark_down(exc)

        status = upstream.status_code
        if status in (401, 403) or status >= 500 or status < 200 or 300 <= status < 400:
            reason = "upstream_auth_refused" if status in (401, 403) else (
                "upstream_redirect" if 300 <= status < 400 else "upstream_error"
            )
            await idempotency.fail(key, {"error": "dial_dev_unavailable", "reason": reason})
            return _mark_down(DialDevUnavailable(reason))
        try:
            parsed = json.loads(upstream.body)
        except (ValueError, UnicodeDecodeError):
            await idempotency.fail(key, {"error": "dial_dev_unavailable", "reason": "upstream_malformed"})
            return _mark_down(DialDevUnavailable("upstream_malformed"))
        dial_degraded.mark_unavailable(degraded, False)

        if 200 <= status < 300:
            await idempotency.complete(key, {"status_code": status, "body": parsed})
        else:
            # DIAL refused (409 STALE_VIEW, 422, 404). Passed through unchanged. The key
            # is released so the identical request can be retried; a changed request —
            # after a STALE_VIEW refetch, a new expected revision — needs a new key.
            await idempotency.fail(key, {"status_code": status, "body": parsed})

        if audit is not None:
            try:
                await audit.record(
                    result="dial_dev_action_forwarded" if 200 <= status < 300 else "dial_dev_action_refused",
                    device_id=device_id,
                    project_id=str(body.target.get("project_id")),
                    capability=f"dial_dev.action.{body.action}",
                    tool="dial_dev_projection_api",
                    after={
                        "status_code": status,
                        "idempotency_key": body.idempotency_key,
                        "target": body.target,
                        "expected_projection_revision": body.expected_projection_revision,
                    },
                    evidence_pointer=forward["owner_device_proof_ref"],
                )
            except Exception:  # noqa: BLE001 - DIAL already answered; do not rewrite it
                # The action happened in DIAL either way. Reporting the audit gap is
                # honest; turning DIAL's 202 into a VAN 500 would invite a retry.
                log.exception("dial_dev audit record failed")
                if degraded is not None:
                    from van_gateway.models import DegradedCode

                    degraded.set(DegradedCode.AUDIT_PROBLEM, True)

        return Response(
            content=upstream.body,
            status_code=status,
            media_type="application/json",
            headers=_NO_STORE,
        )

    return router


def is_dial_dev_route(path: str) -> bool:
    return path == PREFIX or path.startswith(PREFIX + "/")
