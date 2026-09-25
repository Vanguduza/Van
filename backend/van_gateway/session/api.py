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
import json
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from van_gateway.mtls.transport import mtls_device_id
from van_gateway.observability import instruments
from van_gateway.session.models import (
    Direction,
    PROTOCOL_VERSION,
    PathClass,
    SessionEnvelope,
    TransportPathDescriptor,
)
from van_gateway.session.router import SessionRouter
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
        session, path_epoch = await sessions.open(
            device_id=device_id,
            path=TransportPathDescriptor(
                path_id=body.path_id, path_class=body.path_class, protocol=body.protocol,
                endpoint=f"{SESSION_PREFIX}/ws", route_id=body.route_id,
                supports_full_duplex=body.path_class is PathClass.A_REALTIME,
            ),
        )
        state, reason = await sessions.continuity(session.van_session_id)
        return {
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
            status = 409 if routed.refusal in {"session_idempotency_conflict"} else 400
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

        await websocket.accept()
        cursor = session.last_client_event_seq

        async def pump_downstream():
            nonlocal cursor
            while True:
                page = await events.replay(device.device_id, cursor)
                for event in page["events"]:
                    await websocket.send_json({"direction": "DOWNSTREAM", "event": event})
                cursor = page["next_cursor"]
                await asyncio.sleep(DOWNSTREAM_POLL_MS / 1000)

        pump = asyncio.create_task(pump_downstream())
        try:
            while True:
                raw = await websocket.receive_json()
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
            pump.cancel()

    return api
