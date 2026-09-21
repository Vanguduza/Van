"""Rev 1.5 §27 — the link report, and what VAN does with it.

`BrowserQualityController` has existed and been correct since the checkpoint that wrote
it, and nothing called it. This is the caller.

The shape is forced by who can measure what. RTT, jitter, loss and rendered frame rate are
observable only where the frames arrive, which is the phone; the Gateway is deliberately
not in the media path (§6.4) and the Stream Host can say what it sent, not what landed. So
the phone reports, the Gateway decides, and the decision travels back as a *target* rather
than as an instruction — the host adapts toward it, and the phone shows the owner what
regime they are in.

Two rules this route exists to hold, both from §26.2:

* a metered session is not failed merely because it does not reach the unmetered target.
  The profile it is judged against is chosen from the sample, so `NETWORK_LIMITED` means
  the link cannot meet the budget rather than "this is not wi-fi";
* `high_quality_certified` is a property of the verdict, never a field a caller can set.
  The failure §26.2 names is the telemetry claiming a certification it did not earn, and
  a request body with no field for it cannot make that claim.

The controller is per session and lives for as long as the session does, because §27.4's
hysteresis is state: a controller rebuilt per request would upgrade on every third sample
forever and the owner would watch the badge change more often than the page.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from van_gateway.browser.interactive_api import INTERACTIVE_SESSION_PREFIX
from van_gateway.browser.quality import BrowserQualityController, LinkSample
from van_gateway.observability import instruments


class LinkReportBody(BaseModel):
    """§27's inputs, as the phone can measure them.

    Deliberately absent: `quality_mode`, `status`, `profile` and anything resembling
    `high_quality_certified`. The device reports observations; the verdict is the
    Gateway's, and a body that carried one would let a client certify its own session.

    `extra="forbid"` rather than pydantic's default of ignoring unknown fields, and the
    difference is the whole point of §26.2. An ignored `high_quality_certified` is a field
    a caller believes it set and the next maintainer finds already arriving; a refused one
    is an error the caller reads. The claim is refused where it is made.
    """

    model_config = ConfigDict(extra="forbid")

    rtt_ms: float = Field(ge=0)
    jitter_ms: float = Field(ge=0)
    packet_loss: float = Field(ge=0, le=1)
    available_bitrate_kbps: float = Field(ge=0)
    encode_ms: float = Field(ge=0, default=0.0)
    capture_ms: float = Field(ge=0, default=0.0)
    rendered_fps: float = Field(ge=0)
    metered: bool
    #: §27.2 — per session, not a stored preference. The owner turning this on for one
    #: session must not quietly turn it on for the next one on a different network.
    owner_allows_high_quality_on_metered: bool = False
    #: §27.3 — accounting since the last report, not a running total. A total would be
    #: re-added on every report and the owner's data figure would climb on its own.
    media_bytes_received: int = Field(ge=0, default=0)
    media_bytes_sent: int = Field(ge=0, default=0)
    control_bytes: int = Field(ge=0, default=0)


class QualityControllers:
    """One controller per session, kept for as long as the session is open.

    §27.4's hysteresis is state — an upgrade needs three consecutive agreeing samples —
    so a controller built per request would never hold a streak and would either never
    upgrade or upgrade constantly, depending on which way the arithmetic fell.
    """

    def __init__(self) -> None:
        self._controllers: dict[str, BrowserQualityController] = {}

    def for_session(self, session_id: str) -> BrowserQualityController:
        controller = self._controllers.get(session_id)
        if controller is None:
            controller = BrowserQualityController()
            self._controllers[session_id] = controller
        return controller

    def forget(self, session_id: str) -> None:
        """A closed session's accounting is not the next session's."""
        self._controllers.pop(session_id, None)

    def summary(self, session_id: str) -> dict[str, int] | None:
        controller = self._controllers.get(session_id)
        if controller is None:
            return None
        return {
            "media_bytes_received": controller.media_bytes_received,
            "media_bytes_sent": controller.media_bytes_sent,
            "control_bytes": controller.control_bytes,
            "samples": controller.samples,
        }


def build_quality_router(
    *,
    controllers: QualityControllers,
    sessions: Any,
) -> APIRouter:
    router = APIRouter(prefix=INTERACTIVE_SESSION_PREFIX, tags=["browser-quality"])

    async def _owned(request: Request, session_id: str):
        device_id = getattr(request.state, "van_device_id", None)
        if not device_id:
            raise HTTPException(status_code=403, detail="device_identity_required")
        session = await sessions.get(session_id)
        if session is None or session.owner_device_id != device_id:
            raise HTTPException(status_code=404, detail="interactive_session_unknown")
        return session

    @router.post("/{session_id}/link-report")
    async def link_report(request: Request, session_id: str, body: LinkReportBody):
        """§27 — one observation in, one target out.

        The response is what the owner is shown and what the host is steered toward. It
        names the regime in the owner's words rather than in an enum, because "mobile
        data, bounded profile" is a sentence and `METERED_CONSTRAINED` is not.
        """
        session = await _owned(request, session_id)
        if session.state.is_terminal:
            raise HTTPException(status_code=409, detail="interactive_session_not_live")

        controller = controllers.for_session(session.session_id)
        sample = LinkSample(
            rtt_ms=body.rtt_ms,
            jitter_ms=body.jitter_ms,
            packet_loss=body.packet_loss,
            available_bitrate_kbps=body.available_bitrate_kbps,
            encode_ms=body.encode_ms,
            capture_ms=body.capture_ms,
            rendered_fps=body.rendered_fps,
            metered=body.metered,
            owner_allows_high_quality_on_metered=body.owner_allows_high_quality_on_metered,
        )
        # §27.3 — accounted before the verdict, so the summary the owner reads includes
        # the bytes this very report is telling us about.
        controller.account(
            media_received=body.media_bytes_received,
            media_sent=body.media_bytes_sent,
            control=body.control_bytes,
        )
        verdict = controller.observe(sample)
        instruments.record_quality_mode(verdict.mode, metered=body.metered)

        return {
            "session_id": session.session_id,
            "quality_mode": verdict.mode.value,
            "status": verdict.status.value,
            "profile": verdict.profile.name,
            "reason": verdict.reason,
            # The target the host is steered toward. Not an instruction: the host adapts,
            # and a phone that could command an encoder directly would be a second
            # actuation path with no control lease behind it.
            "target": {
                "max_height": verdict.target.max_height,
                "fps": verdict.target.fps,
                "bitrate_kbps": verdict.target.bitrate_kbps,
            },
            "high_quality_certified": verdict.certified_high_quality,
            "accounting": controllers.summary(session.session_id),
        }

    @router.get("/{session_id}/quality")
    async def quality(request: Request, session_id: str):
        """What the owner is shown, without sending a new observation.

        Reads the last verdict rather than recomputing one from nothing: a GET that
        invented a sample would move the hysteresis streak, and polling a status page
        would change the thing it reports.
        """
        session = await _owned(request, session_id)
        controller = controllers.for_session(session.session_id)
        return {
            "session_id": session.session_id,
            "quality_mode": controller.mode.value,
            "accounting": controllers.summary(session.session_id),
            # Absent until the device has reported: VAN does not know what the link is
            # doing before anything has measured it, and a default would be a guess the
            # owner reads as a measurement.
            "observed": controller.samples > 0,
        }

    return router
