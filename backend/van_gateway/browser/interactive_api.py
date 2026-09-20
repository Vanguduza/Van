"""Rev 1.5 §§6, 34 — the owner-device control surface for an interactive browser.

Every other `/v1/browser/` mutation is Hermes-only (§2.2: Android is not a second agent).
These routes are the deliberate exception and the reason is not convenience: **the owner's
phone is the thing holding the browser**. A session it cannot create, heartbeat or close is
a session nobody owns.

So they authenticate as the owner's device — ingress token plus device token, exactly like
every other owner route — and every one of them then checks that the session belongs to the
calling device. Pairing gives a device an identity, not the right to drive another device's
browser.

What these routes do **not** do:

* they never carry pixels, SDP or ICE. §6.4 keeps the Gateway out of the media path, and
  signalling goes straight to the stream runtime against a minted grant;
* they never accept a URL to navigate to. Navigation is an actuation, and actuation is
  fenced by the control lease on the stream host, not by an authenticated REST call;
* they never mint authority for another device.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from van_gateway.browser.agent_grant import AgentGrantService
from van_gateway.browser.control_lease import ControlLeaseError, ControlLeaseService
from van_gateway.browser.downloads import (
    DownloadBroker,
    DownloadError,
    DownloadState,
    owner_actions,
)
from van_gateway.browser.interactive_models import (
    BrowserControlHolder,
    InteractiveBrowserSession,
    InteractiveSessionState,
    Viewport,
)
from van_gateway.browser.interactive_service import (
    InteractiveSessionError,
    InteractiveSessionService,
)
from van_gateway.browser.policy import BrowserPolicyError
from van_gateway.browser.stream_grants import StreamGrantError, StreamGrantService
from van_gateway.observability import instruments

#: §34 / §6.1. One prefix, read by the router and by the two route classifiers in app.py,
#: because the alternative is three lists that agree until someone adds a route to two of
#: them. An unclassified route falls through to owner-device authentication, which for a
#: Hermes-only surface would be a hole rather than an inconsistency (P2-GOOG-004).
INTERACTIVE_SESSION_PREFIX = "/v1/browser/interactive-sessions"


def is_interactive_browser_owner_route(path: str) -> bool:
    """Whether this path is an owner-device route rather than a Hermes control route."""
    return path == INTERACTIVE_SESSION_PREFIX or path.startswith(INTERACTIVE_SESSION_PREFIX + "/")


class ViewportBody(BaseModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    device_scale_factor: float = Field(gt=0, default=1.0)


class MediaPreferenceBody(BaseModel):
    preferred_video: list[str] = Field(default_factory=lambda: ["H264"])
    preferred_audio: list[str] = Field(default_factory=lambda: ["OPUS"])
    max_fps: int = 60


class CreateSessionBody(BaseModel):
    profile_alias: str
    viewport: ViewportBody
    media: MediaPreferenceBody = Field(default_factory=MediaPreferenceBody)
    mission_id: str | None = None
    idempotency_key: str | None = None


class DelegateControlBody(BaseModel):
    #: Only the two Hermes holders are accepted; the service refuses anything else.
    holder: str
    issued_for: str


class ViewportAckBody(BaseModel):
    revision: int


def _session_json(session: InteractiveBrowserSession) -> dict[str, Any]:
    """What the device is told. Never the profile secret, never the URL in plaintext."""
    return {
        "session_id": session.session_id,
        "state": session.state.value,
        "owner_readable_state": session.owner_readable_state,
        "profile_alias": session.profile_alias,
        "viewport": {
            "width": session.viewport.width,
            "height": session.viewport.height,
            "device_scale_factor": session.viewport.device_scale_factor,
            "revision": session.viewport.revision,
        },
        "acked_viewport_revision": session.acked_viewport_revision,
        "control_holder": session.control_holder.value,
        "control_lease_id": session.control_lease_id,
        "control_generation": session.control_generation,
        "active_target_id": session.active_target_id,
        "requested_fps": session.requested_fps,
        "mission_id": session.mission_id,
        "created_at_ms": session.created_at_ms,
        "expires_at_ms": session.expires_at_ms,
        # §5.2 — stated rather than implied. A device that has to infer "did the work
        # succeed" from a session state will infer it wrongly.
        "is_work_outcome": False,
    }


def build_interactive_router(
    *,
    sessions: InteractiveSessionService,
    control: ControlLeaseService,
    grants: StreamGrantService,
    agent_grants: AgentGrantService | None = None,
    downloads_broker: DownloadBroker | None = None,
    signal_url: str,
    ice_servers: list[dict[str, Any]],
    mission_binder: Any | None = None,
    audit: Any | None = None,
) -> APIRouter:
    router = APIRouter(prefix=INTERACTIVE_SESSION_PREFIX, tags=["browser-interactive"])

    async def _owned(request: Request, session_id: str) -> InteractiveBrowserSession:
        """The device check every route shares.

        A paired device is not automatically entitled to another device's session. Without
        this, a second phone in the house could take control of the browser the owner is
        looking at, and every route below would still look correctly authenticated.
        """
        device_id = getattr(request.state, "van_device_id", None)
        if not device_id:
            raise HTTPException(status_code=403, detail="device_identity_required")
        session = await sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="interactive_session_unknown")
        if session.owner_device_id != device_id:
            # 404 rather than 403: a device that does not own this session should not learn
            # that it exists.
            raise HTTPException(status_code=404, detail="interactive_session_unknown")
        return session

    async def _abandon(session: InteractiveBrowserSession) -> None:
        """Unwind a session that was created and must not survive.

        The profile lease is the reason this is not simply "ignore it": a session left in
        INTERACTIVE holds the owner's authenticated profile, and the next attempt would be
        refused as leased by a session nobody is using.
        """
        await grants.revoke_for_session(session.session_id)
        await sessions.transition(
            session_id=session.session_id,
            target=InteractiveSessionState.TERMINATING, reason="mission_binding_refused",
        )
        await sessions.transition(
            session_id=session.session_id,
            target=InteractiveSessionState.TERMINATED, reason="mission_binding_refused",
        )

    @router.post("")
    async def create_session(request: Request, body: CreateSessionBody):
        device_id = getattr(request.state, "van_device_id", None)
        if not device_id:
            raise HTTPException(status_code=403, detail="device_identity_required")
        try:
            session = await sessions.create(
                owner_device_id=device_id,
                profile_alias=body.profile_alias,
                viewport=Viewport(
                    width=body.viewport.width,
                    height=body.viewport.height,
                    device_scale_factor=body.viewport.device_scale_factor,
                ),
                requested_fps=body.media.max_fps,
                mission_id=body.mission_id,
                idempotency_key=body.idempotency_key,
            )
        except BrowserPolicyError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except InteractiveSessionError as exc:
            # A leased profile is a conflict, not a bad request: the caller did nothing
            # wrong and retrying later is the correct response.
            status = 409 if "leased" in str(exc) else 400
            raise HTTPException(status_code=status, detail=str(exc)) from exc

        if body.mission_id and mission_binder is not None:
            # ADR-RB-018 / §23.1 — attach to the Mission the command already created. The
            # session never creates one.
            #
            # A refused binding ends the session rather than leaving it. Until RB-044 this
            # call was unguarded and `browser.interactive.session` was named by the binder
            # and declared by nobody, so every mission-bound session raised
            # MISSION_CAPABILITY_NOT_PERMITTED out of the route as a 500 — §23.1 had never
            # once worked. Returning 201 with the session unbound would be the worse fix:
            # the phone would hold a session it believes is part of a Mission that has no
            # record of it, and the owner's Missions page would be missing the work.
            try:
                await mission_binder.bind_browser_session(
                    mission_id=body.mission_id, session_id=session.session_id
                )
            except Exception as exc:  # MissionError and anything else the binder raises
                await _abandon(session)
                raise HTTPException(
                    status_code=409, detail=f"mission_binding_refused:{exc}"
                ) from exc
        if audit is not None:
            await audit.record(
                result="ok", device_id=device_id, capability="browser.interactive.create",
                after={"session_id": session.session_id, "profile_alias": body.profile_alias},
            )
        return _session_json(session)

    @router.get("/{session_id}")
    async def read_session(request: Request, session_id: str):
        return _session_json(await _owned(request, session_id))

    @router.post("/{session_id}/stream-grant")
    async def mint_stream_grant(request: Request, session_id: str):
        """§6.3 — the one-time credential the stream runtime verifies.

        Minting is separate from session creation because a reconnect needs a new grant and
        must not need a new session: §29's recovery path is the owner coming back to their
        tabs, not starting again.
        """
        session = await _owned(request, session_id)
        if session.state.is_terminal:
            raise HTTPException(status_code=409, detail="interactive_session_ended")
        try:
            token, claims = await grants.mint(
                session_id=session.session_id,
                device_id=session.owner_device_id,
                profile_alias=session.profile_alias,
                scope=["webrtc.signal", "browser.view", "browser.owner_input"],
                max_width=session.viewport.width,
                max_height=session.viewport.height,
                max_fps=session.requested_fps,
            )
        except StreamGrantError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "session_id": session.session_id,
            "state": session.state.value,
            "stream_grant": token,
            "signal_url": signal_url,
            "ice_servers": ice_servers,
            "expires_at_ms": claims["expires_at_ms"],
        }

    @router.post("/{session_id}/take-control")
    async def take_control(request: Request, session_id: str):
        """ADR-RB-007 — the owner takes control back. Not a request; a fact."""
        session = await _owned(request, session_id)
        started = time.monotonic()
        lease = await control.owner_preempt(
            session_id=session.session_id, device_id=session.owner_device_id
        )
        # §22.3, the half that is marked mandatory and that a "Take over" button does not
        # provide: the agent's *queued* actions are discarded, not merely refused when they
        # next arrive. An action already accepted and waiting is one the owner has taken
        # the browser back from, and letting it run because it was queued before the
        # preemption is the failure the section exists to forbid.
        discarded: list[str] = []
        if agent_grants is not None:
            discarded = agent_grants.owner_preempted(
                session.session_id, new_generation=lease.generation
            )
        instruments.record_control_preempt((time.monotonic() - started) * 1000.0)

        if session.state is InteractiveSessionState.AGENT_CONTROLLED:
            await sessions.transition(
                session_id=session.session_id, target=InteractiveSessionState.INTERACTIVE,
                reason="owner_preempt",
            )
            await sessions.record_event(
                session_id=session.session_id,
                event_type="session.agent_takeover_stopped", severity="INFO",
                summary="Owner took control", device_id=session.owner_device_id,
            )
        return {
            "control_lease_id": lease.control_lease_id,
            "control_generation": lease.generation,
            "holder": lease.holder.value,
            "expires_at_ms": lease.expires_at_ms,
            # Named rather than counted. An agent that was about to submit a form and did
            # not is a fact the owner may need, and "3 actions discarded" is not that fact.
            "discarded_agent_actions": discarded,
        }

    @router.post("/{session_id}/delegate-control")
    async def delegate_control(request: Request, session_id: str, body: DelegateControlBody):
        """The owner hands actuation to Hermes. Only the owner may do this."""
        session = await _owned(request, session_id)
        try:
            holder = BrowserControlHolder(body.holder)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="control_holder_unknown") from exc
        try:
            lease = await control.delegate(
                session_id=session.session_id, holder=holder, issued_for=body.issued_for
            )
        except ControlLeaseError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if session.state is InteractiveSessionState.INTERACTIVE:
            await sessions.transition(
                session_id=session.session_id,
                target=InteractiveSessionState.AGENT_CONTROLLED, reason="delegated",
            )
            await sessions.record_event(
                session_id=session.session_id,
                event_type="session.agent_takeover_started", severity="INFO",
                summary=f"{holder.value} is driving", device_id=session.owner_device_id,
            )
        return {
            "control_lease_id": lease.control_lease_id,
            "control_generation": lease.generation,
            "holder": lease.holder.value,
            "expires_at_ms": lease.expires_at_ms,
        }

    @router.post("/{session_id}/heartbeat")
    async def heartbeat(request: Request, session_id: str):
        """§5.3 — the device is still here, and the lease is renewed if it is due.

        The failure is reported rather than smoothed over: a session whose lease could not
        be renewed has stopped being able to act, and a phone that is told "fine" will keep
        sending input that the stream host now refuses.
        """
        session = await _owned(request, session_id)
        try:
            updated = await sessions.heartbeat(session_id=session.session_id)
        except InteractiveSessionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _session_json(updated)

    @router.post("/{session_id}/viewport")
    async def propose_viewport(request: Request, session_id: str, body: ViewportBody):
        """A resize. Actuation is withheld until the device acknowledges the new revision."""
        session = await _owned(request, session_id)
        try:
            revision = await sessions.propose_viewport(
                session_id=session.session_id,
                viewport=Viewport(
                    width=body.width, height=body.height,
                    device_scale_factor=body.device_scale_factor,
                ),
            )
        except InteractiveSessionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"session_id": session.session_id, "viewport_revision": revision}

    @router.post("/{session_id}/viewport/ack")
    async def acknowledge_viewport(request: Request, session_id: str, body: ViewportAckBody):
        session = await _owned(request, session_id)
        try:
            await sessions.acknowledge_viewport(
                session_id=session.session_id, revision=body.revision
            )
        except InteractiveSessionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"session_id": session.session_id, "acked_viewport_revision": body.revision}

    @router.post("/{session_id}/suspend")
    async def suspend(request: Request, session_id: str):
        session = await _owned(request, session_id)
        try:
            updated = await sessions.transition(
                session_id=session.session_id,
                target=InteractiveSessionState.SUSPENDED, reason="owner_suspended",
            )
        except InteractiveSessionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _session_json(updated)

    @router.delete("/{session_id}")
    async def end_session(request: Request, session_id: str):
        session = await _owned(request, session_id)
        if session.state.is_terminal:
            return _session_json(session)
        await grants.revoke_for_session(session.session_id)
        if session.state is not InteractiveSessionState.TERMINATING:
            await sessions.transition(
                session_id=session.session_id,
                target=InteractiveSessionState.TERMINATING, reason="owner_closed",
            )
        updated = await sessions.transition(
            session_id=session.session_id,
            target=InteractiveSessionState.TERMINATED, reason="owner_closed",
        )
        if audit is not None:
            await audit.record(
                result="ok", device_id=session.owner_device_id,
                capability="browser.interactive.end",
                after={"session_id": session.session_id},
            )
        return _session_json(updated)

    @router.get("/{session_id}/tabs")
    async def tabs(request: Request, session_id: str):
        session = await _owned(request, session_id)
        return {"session_id": session.session_id, "tabs": await sessions.targets(session.session_id)}

    @router.get("/{session_id}/downloads")
    async def downloads(request: Request, session_id: str):
        """§18.3 — what was downloaded and what the owner may do with each one.

        `actions` is computed here rather than on the phone. A client that derived the
        offered actions from the state string would have to re-implement §18.2's rule that
        a quarantined file loses exactly `OPEN_IN_VAN` and `SEND_TO_PHONE` — and a client
        that got it wrong would put a dangerous file one tap from opening.
        """
        session = await _owned(request, session_id)
        rows = await sessions.store.fetchall(
            "SELECT download_id, suggested_name, mime_type, byte_size, state, "
            "failure_reason, created_at_ms, completed_at_ms "
            "FROM browser_downloads WHERE session_id = ? ORDER BY created_at_ms DESC",
            (session.session_id,),
        )
        return {
            "session_id": session.session_id,
            "downloads": [
                {
                    "download_id": r["download_id"],
                    "suggested_name": r["suggested_name"],
                    "mime_type": r["mime_type"],
                    "byte_size": r["byte_size"],
                    "state": r["state"],
                    "failure_reason": r["failure_reason"],
                    # Stated, not inferred from `failure_reason` being non-empty by a
                    # client that does not know what that column means.
                    "dangerous": bool(r["failure_reason"]),
                    "actions": [
                        action.value
                        for action in owner_actions(
                            DownloadState(r["state"]), dangerous=bool(r["failure_reason"])
                        )
                    ],
                    "created_at_ms": int(r["created_at_ms"]),
                    "completed_at_ms": (
                        int(r["completed_at_ms"]) if r["completed_at_ms"] is not None else None
                    ),
                }
                for r in rows
            ],
        }

    @router.delete("/{session_id}/downloads/{download_id}")
    async def delete_download(request: Request, session_id: str, download_id: str):
        """The one owner action the Gateway can carry out on its own.

        Every other action in §18.3 moves the *file*, which is on the Stream Host's
        quarantine volume and not reachable from here (§6.4 keeps the Gateway out of that
        path for the same reason it keeps it out of the media one). Deleting is a decision
        about the record, and the host reaps what the record no longer claims.

        The download is checked against *this* session before anything happens. Without
        that, a device that owns one session could name a download id belonging to
        another and delete a file it has no authority over — the session check above
        would still have passed.
        """
        session = await _owned(request, session_id)
        if downloads_broker is None:
            raise HTTPException(status_code=503, detail="browser_downloads_unconfigured")
        row = await sessions.store.fetchone(
            "SELECT session_id FROM browser_downloads WHERE download_id = ?", (download_id,)
        )
        if row is None or row["session_id"] != session.session_id:
            raise HTTPException(status_code=404, detail="download_unknown")
        try:
            await downloads_broker.delete(download_id)
        except DownloadError as exc:
            raise HTTPException(status_code=409, detail=exc.reason) from exc
        if audit is not None:
            await audit.record(
                result="ok", device_id=session.owner_device_id,
                capability="browser.download.delete",
                after={"download_id": download_id, "session_id": session.session_id},
            )
        return {"download_id": download_id, "state": DownloadState.DELETED.value}

    @router.get("/{session_id}/events")
    async def session_events(request: Request, session_id: str):
        session = await _owned(request, session_id)
        return {
            "session_id": session.session_id,
            "events": await sessions.session_events(session.session_id),
        }

    return router
