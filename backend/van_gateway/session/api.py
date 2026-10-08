"""Rev 1.5 §§20.5, 34 — the session's three carriers, one authority.

`/v1/session/ws` is the only full-duplex semantic endpoint (§34.1). The HTTP/2 pair and the
existing REST APIs are fallbacks, not alternative authorities: every one of them routes
through the same `SessionRouter`, which routes into the same command path the phone has
always used.

§20.5's reason for the HTTP/2 path is worth keeping in view while reading it: it exists to
be *different enough* from WebSocket handling to survive a middlebox that breaks WebSockets
while ordinary HTTPS still works. Sharing a code path with the socket would defeat the
purpose; sharing the envelope and the router is the point.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import time
from typing import Any

import anyio
from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from van_gateway.auth.device_binding import DeviceBindingError
from van_gateway.command.nonce import CommandNonceService, NonceReplay

from van_gateway.mtls.transport import mtls_certificate_serial, mtls_device_id
from van_gateway.observability import instruments
from van_gateway.session.models import (
    Direction,
    PROTOCOL_VERSION,
    PathClass,
    SessionEnvelope,
    SessionState,
    TransportPathDescriptor,
)
from van_gateway.session.router import REJECT_RESULT_PENDING, SessionRouter
from van_gateway.session.service import SessionError, VanHermesSessionService

SESSION_PREFIX = "/v1/session"

#: §20.8 — the idle cadence. The active-interaction cadence is the client's business; the
#: server's job is to not hold a socket open forever with nothing on it.
DOWNSTREAM_POLL_MS = 500
STREAM_KEEPALIVE_MS = 15_000


def is_session_owner_route(path: str) -> bool:
    """Owner-device authenticated, like the interactive browser routes.

    One predicate, read by the scope classifier in app.py. The session carries the owner's
    commands, so it authenticates as the owner's device — and an unclassified route would
    fall through to exactly that, which is why this is written down rather than assumed.
    """
    return path == SESSION_PREFIX or path.startswith(SESSION_PREFIX + "/")


class OpenSessionBody(BaseModel):
    open_request_id: str | None = Field(default=None, min_length=16, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    path_id: str = "primary"
    route_id: str = "default"
    protocol: str = "WSS"
    path_class: PathClass = PathClass.A_REALTIME


class ResumeBody(BaseModel):
    van_session_id: str
    session_epoch: int
    last_event_seq: int = 0
    pending_command_ids: list[str] = Field(default_factory=list)
    active_turn_id: str | None = None
    active_response_id: str | None = None
    last_received_response_segment: int = 0
    last_spoken_speech_segment: int = 0
    path_id: str = "fallback"
    route_id: str = "default"
    path_class: PathClass = PathClass.B_STREAMING


class EnvelopeBody(BaseModel):
    """§20.4's envelope, as a request body. Identical fields on every carrier."""

    protocol_version: int = PROTOCOL_VERSION
    message_id: str
    van_session_id: str
    session_epoch: int
    path_epoch: int
    kind: str
    created_at_ms: int | None = None
    expires_at_ms: int | None = None
    turn_id: str | None = None
    command_id: str | None = None
    idempotency_key: str | None = None
    correlation_id: str | None = None
    payload_digest: str | None = None
    payload: dict = Field(default_factory=dict)


def build_session_router(
    *,
    sessions: VanHermesSessionService,
    router: SessionRouter,
    events: Any,
    resume_snapshot: Any | None = None,
    require_device_binding: bool = False,
    audit: Any | None = None,
) -> APIRouter:
    api = APIRouter(prefix=SESSION_PREFIX, tags=["session"])

    def _device(request: Request) -> str:
        device_id = getattr(request.state, "van_device_id", None)
        if not device_id:
            raise HTTPException(status_code=403, detail="device_identity_required")
        return device_id

    def _envelope(body: EnvelopeBody, device_id: str) -> SessionEnvelope:
        return SessionEnvelope(
            protocol_version=body.protocol_version,
            message_id=body.message_id,
            van_session_id=body.van_session_id,
            session_epoch=body.session_epoch,
            path_epoch=body.path_epoch,
            device_id=device_id,
            direction=Direction.UPSTREAM,
            kind=body.kind,
            created_at_ms=body.created_at_ms or int(time.time() * 1000),
            expires_at_ms=body.expires_at_ms,
            turn_id=body.turn_id,
            command_id=body.command_id,
            idempotency_key=body.idempotency_key,
            correlation_id=body.correlation_id,
            payload_digest=body.payload_digest,
            payload=body.payload,
        )

    @api.post("/open")
    async def open_session(request: Request, body: OpenSessionBody):
        device_id = _device(request)
        try:
            session, path_epoch = await sessions.open(
                device_id=device_id, open_request_id=body.open_request_id,
                path=TransportPathDescriptor(
                    path_id=body.path_id, path_class=body.path_class, protocol=body.protocol,
                    endpoint=f"{SESSION_PREFIX}/ws", route_id=body.route_id,
                    supports_full_duplex=body.path_class is PathClass.A_REALTIME,
                ),
            )
        except SessionError as exc:
            raise HTTPException(status_code=409, detail=exc.reason) from exc
        state, reason = await sessions.continuity(session.van_session_id)
        return {
            "open_request_id": body.open_request_id,
            "van_session_id": session.van_session_id,
            "session_epoch": session.session_epoch,
            "path_epoch": path_epoch,
            "continuity": state.value,
            "continuity_reason": reason,
        }

    @api.post("/resume")
    async def resume_session(request: Request, body: ResumeBody):
        """§20.10 step 4 — the authoritative snapshot a failover reconciles against."""
        device_id = _device(request)
        from van_gateway.session.models import ResumeRequest

        # §20.10 — what the Gateway can honestly say about a path switch, taken *before*
        # the resume grants a new epoch. Afterwards the old path's row has been
        # superseded and the route it was on is no longer recoverable from the session.
        #
        # This is the Gateway's half of the failover picture and it is deliberately only
        # the half it can see: whether the session moved, and whether it moved to another
        # road. How long the owner sat looking at a frozen page is the device's
        # measurement (`session_failover_ms`), because the Gateway does not learn a path
        # died until the resume arrives — by which time the gap is already over.
        previous = await sessions.get(body.van_session_id)
        previous_route, previous_path = None, None
        if previous is not None:
            for live in await sessions.live_paths(body.van_session_id):
                if live["path_epoch"] == previous.authoritative_path_epoch:
                    previous_route = live["route_id"]
                    previous_path = live["path_id"]
                    break
        route_changed = previous_route is not None and previous_route != body.route_id

        snapshot = {}
        if resume_snapshot is not None:
            snapshot = await resume_snapshot(
                device_id=device_id,
                # §20.12 — the admission table is per session, so the answer has to be
                # too. Without this the Gateway could only answer from the mission table.
                van_session_id=body.van_session_id,
                pending_command_ids=body.pending_command_ids,
            )
        result = await sessions.resume(
            ResumeRequest(
                van_session_id=body.van_session_id,
                session_epoch=body.session_epoch,
                device_id=device_id,
                last_event_seq=body.last_event_seq,
                pending_command_ids=body.pending_command_ids,
                active_turn_id=body.active_turn_id,
                active_response_id=body.active_response_id,
                last_received_response_segment=body.last_received_response_segment,
                last_spoken_speech_segment=body.last_spoken_speech_segment,
            ),
            path=TransportPathDescriptor(
                path_id=body.path_id, path_class=body.path_class,
                protocol="HTTP2" if body.path_class is PathClass.B_STREAMING else "WSS",
                endpoint=f"{SESSION_PREFIX}/events-stream", route_id=body.route_id,
            ),
            command_states=snapshot.get("command_states"),
            authoritative_event_cursor=snapshot.get("authoritative_event_cursor"),
            # §21.16 — the spoken cursor. Without this the resume tells the client where
            # its *commands* got to and says nothing about where its answer got to, so a
            # reconnect mid-sentence has nothing to resume speech from.
            response_state=snapshot.get("response_state"),
        )
        if not result.accepted:
            # Counted, not just raised. A resume that is refused is the failover that did
            # not happen, and a counter that only saw the successful ones would report a
            # perfect record for a session that never came back.
            instruments.record_session_failover(
                result.refusal, route_changed=route_changed,
            )
            # A refused resume is a 409 rather than a 401: the credential was fine, the
            # session's state was not, and the client needs to open a new one rather than
            # re-authenticate.
            raise HTTPException(status_code=409, detail=result.refusal)
        instruments.record_session_failover(
            # A client that came back on the same path did not fail over; it reconnected.
            # Counting the two as one outcome would make an ordinary tunnel look like a
            # route failure, and the label exists precisely so they can be told apart.
            "reconnected" if previous_path == body.path_id else "failed_over",
            route_changed=route_changed,
        )
        return result.model_dump(mode="json")

    @api.get("/status")
    async def session_status(request: Request, van_session_id: str):
        device_id = _device(request)
        session = await sessions.get(van_session_id)
        if session is None or session.device_id != device_id:
            raise HTTPException(status_code=404, detail="session_unknown")
        state, reason = await sessions.continuity(van_session_id)
        return {
            "van_session_id": session.van_session_id,
            "session_epoch": session.session_epoch,
            "state": session.state.value,
            "authoritative_path_epoch": session.authoritative_path_epoch,
            "continuity": state.value,
            "continuity_reason": reason,
            "paths": await sessions.live_paths(van_session_id),
        }

    @api.post("/messages")
    async def upstream_message(request: Request, body: EnvelopeBody):
        """§20.5 path class B, upstream half."""
        device_id = _device(request)
        routed = await router.route(_envelope(body, device_id))
        if not routed.accepted:
            status = (503 if routed.refusal == REJECT_RESULT_PENDING else
                      409 if routed.refusal == "session_idempotency_conflict" else 400)
            raise HTTPException(status_code=status, detail=routed.refusal)
        return {
            "accepted": True,
            "kind": routed.kind,
            "admission": routed.admission.value if routed.admission else None,
            "result": routed.result,
        }

    @api.get("/events-stream")
    async def events_stream(request: Request, van_session_id: str, after_seq: int = 0):
        """§20.5 path class B, downstream half.

        The frames carry the same durable events the REST replay serves, from the same
        cursor. §20.13: realtime push and REST replay are two carriers for one authority,
        so a client that switches between them mid-session sees no gap and no duplicate it
        cannot identify.
        """
        device_id = _device(request)
        session = await sessions.get(van_session_id)
        if session is None or session.device_id != device_id:
            raise HTTPException(status_code=404, detail="session_unknown")

        async def frames():
            cursor = after_seq
            last_sent = time.monotonic()
            while True:
                if await request.is_disconnected():
                    return
                page = await events.replay(device_id, cursor)
                for event in page["events"]:
                    yield f"data: {json.dumps(event)}\n\n"
                    last_sent = time.monotonic()
                cursor = page["next_cursor"]
                if time.monotonic() - last_sent > STREAM_KEEPALIVE_MS / 1000:
                    # A comment frame, not an event. A middlebox that closes idle
                    # connections is one of the reasons this path exists at all.
                    yield ": keepalive\n\n"
                    last_sent = time.monotonic()
                await asyncio.sleep(DOWNSTREAM_POLL_MS / 1000)

        return StreamingResponse(frames(), media_type="text/event-stream")

    @api.websocket("/ws")
    async def session_socket(websocket: WebSocket, van_session_id: str, device_token: str = ""):
        """§34.1 — the only full-duplex semantic session endpoint.

        Authentication is explicit here rather than inherited: the HTTP middleware does not
        run for a WebSocket handshake, so a socket that assumed the device had already been
        checked would be an unauthenticated ingress into the command path.
        """
        app = websocket.app
        auth = getattr(app.state, "auth", None)
        if auth is None:
            await websocket.close(code=1011)
            return
        try:
            device = await auth.require_access_token(device_token)
        except Exception:  # AuthError and anything else it raises
            await websocket.close(code=4401)
            return

        certified = mtls_device_id(websocket.scope)
        if certified is not None and certified != device.device_id:
            # Direct mutual-TLS link: the token must belong to the certified device.
            await websocket.close(code=4403)
            return

        session = await sessions.get(van_session_id)
        if session is None or session.device_id != device.device_id:
            await websocket.close(code=4404)
            return
        if session.state is SessionState.CLOSED:
            await websocket.close(code=4404, reason="session_closed")
            return

        async def binding_identity(*, verify_proof: bool) -> str | None:
            service = getattr(app.state, "owner_device_bindings", None)
            if service is None:
                if require_device_binding:
                    raise DeviceBindingError("owner_device_binding_unconfigured")
                return None
            binding = await service.active()
            if binding is None:
                if await service.for_device(device.device_id) is not None:
                    raise DeviceBindingError("device_binding_revoked")
                if require_device_binding:
                    raise DeviceBindingError("device_not_bound")
                return None
            if binding.device_id != device.device_id:
                raise DeviceBindingError("device_not_owner_device")
            if require_device_binding and not binding.attestation_chain_verified:
                raise DeviceBindingError("device_attestation_recertification_required")
            # Only the server's verified certificate scope may substitute for a request
            # proof. A caller header cannot create it, and strict binding still applies.
            if not verify_proof or certified == device.device_id:
                return binding.binding_id
            signature_b64 = websocket.headers.get("X-Van-Device-Proof", "")
            issued_at_raw = websocket.headers.get("X-Van-Device-Proof-Issued-At", "")
            if not signature_b64 or not issued_at_raw:
                raise DeviceBindingError("device_proof_required")
            try:
                signature = base64.b64decode(signature_b64, validate=True)
                issued_at_ms = int(issued_at_raw)
            except (ValueError, binascii.Error) as exc:
                raise DeviceBindingError("device_proof_malformed") from exc
            await service.require_proof(
                device_id=device.device_id, signature=signature, method="GET",
                path=SESSION_PREFIX + "/ws", issued_at_ms=issued_at_ms, body=b"",
            )
            try:
                # The signed timestamp identifies one handshake, regardless of ECDSA
                # signature encoding. An intercepted proof cannot open a second socket.
                await CommandNonceService(service.store).consume(
                    device_id=device.device_id, nonce=f"ws-proof:{issued_at_ms}",
                    command_id=van_session_id,
                )
            except NonceReplay as exc:
                raise DeviceBindingError("device_proof_replayed") from exc
            return binding.binding_id

        authority_closed = False
        authority_close: asyncio.Task | None = None

        async def close_authority(code: int, reason: str) -> None:
            nonlocal authority_closed, authority_close
            if authority_close is None:
                authority_closed = True
                authority_close = asyncio.create_task(websocket.close(code=code, reason=reason))
            # Revocation can be observed by both loops. Canceling the event pump during
            # receiver shutdown must not cancel the close frame before it is delivered.
            await asyncio.shield(authority_close)

        async def refuse_binding(exc: DeviceBindingError) -> None:
            code = 1011 if exc.reason == "owner_device_binding_unconfigured" else (
                4401 if exc.reason.startswith("device_proof_") else 4403
            )
            await close_authority(code, exc.reason)

        try:
            admitted_binding_id = await binding_identity(verify_proof=True)
        except DeviceBindingError as exc:
            await refuse_binding(exc)
            return

        async def continuing_authority() -> bool:
            if authority_closed:
                return False
            try:
                await auth.require_access_token(device_token)
            except Exception:
                await close_authority(4401, "device_access_revoked")
                return False
            try:
                if await binding_identity(verify_proof=False) != admitted_binding_id:
                    raise DeviceBindingError("device_binding_changed")
            except DeviceBindingError as exc:
                await refuse_binding(exc)
                return False
            return not authority_closed

        await websocket.accept()
        if audit is not None:
            await audit.record(
                result="accepted", device_id=device.device_id, capability="session.transport.admitted",
                after={
                    "van_session_id": van_session_id,
                    "binding_id": admitted_binding_id,
                    "transport": "WEBSOCKET",
                    "certified_matching": certified == device.device_id,
                    "certificate_serial": mtls_certificate_serial(websocket.scope),
                    "proof_verified": admitted_binding_id is not None and certified != device.device_id,
                },
            )
        cursor = session.last_client_event_seq

        async def pump_downstream():
            nonlocal cursor
            while True:
                if not await continuing_authority():
                    return
                page = await events.replay(device.device_id, cursor)
                for event in page["events"]:
                    if authority_closed:
                        return
                    await websocket.send_json({"direction": "DOWNSTREAM", "event": event})
                cursor = page["next_cursor"]
                await asyncio.sleep(DOWNSTREAM_POLL_MS / 1000)

        pump = asyncio.create_task(pump_downstream())
        try:
            while not authority_closed:
                raw = await websocket.receive_json()
                if not await continuing_authority():
                    return
                try:
                    body = EnvelopeBody(**raw)
                except Exception:
                    await websocket.send_json({"accepted": False, "refusal": "session_envelope_invalid"})
                    continue
                routed = await router.route(_envelope(body, device.device_id))
                await websocket.send_json({
                    "accepted": routed.accepted,
                    "message_id": body.message_id,
                    "kind": routed.kind,
                    "refusal": routed.refusal,
                    "admission": routed.admission.value if routed.admission else None,
                    "result": routed.result,
                })
        except WebSocketDisconnect:
            pass
        finally:
            # A peer can disconnect immediately after receiving the revocation
            # close. ASGI cancellation must not cancel the task join itself and
            # recancel a pump that is already releasing its database resources.
            # asyncio.shield above protects the close sender from sibling task
            # cancellation; this scope also protects their final joins from the
            # enclosing ASGI/AnyIO connection cancellation.
            with anyio.CancelScope(shield=True):
                pump.cancel()
                await asyncio.gather(pump, return_exceptions=True)
                if authority_close is not None:
                    await asyncio.gather(authority_close, return_exceptions=True)

    return api
