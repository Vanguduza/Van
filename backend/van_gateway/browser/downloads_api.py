"""Rev 1.5 §18 — the two surfaces a download record is reachable through.

The bytes never pass through here. They are written on the Stream Host's quarantine
volume, and what travels is a *report* about them and, later, an owner decision.

Two surfaces because there are two different authorities:

* the **report** surface, Hermes-scoped. Downloads start because something navigated or
  clicked on the Stream Host, and the only component that learns about them is the Browser
  Control Agent, which Hermes drives over mTLS. The host itself holds no Gateway
  credential — it verifies stream grants and issues nothing — so a host-authenticated
  route would need one invented for it. Hermes already has `ControlScope.BROWSER`;
* the **owner** surface, on the interactive-session prefix, which is where the owner
  deletes a file or asks what they are allowed to do with it. That lives in
  `interactive_api` next to the session it belongs to.

The report surface accepts a state *report*, never a state *assignment*: there is no route
that says "this download is now COMPLETED". The host says what happened — it started, it
finished with this hash and this sniffed type, it failed — and §18.2's pipeline decides
where the record stops. Otherwise a compromised or merely buggy agent could report an
executable straight into `COMPLETED` and the classification would never run.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from van_gateway.browser.downloads import DownloadBroker, DownloadError, DownloadState
from van_gateway.browser.interactive_models import InteractiveSessionState
from van_gateway.observability import instruments

#: POSTs under `/v1/browser/` are `ControlScope.BROWSER` in the ingress classifier, so this
#: prefix is Hermes-scoped without a new branch there. It deliberately does **not** start
#: with the interactive-session prefix, which is the owner-device surface: a report route
#: under that prefix would be authenticated as the owner's phone, and the phone is not the
#: thing that saw the download.
DOWNLOAD_REPORT_PREFIX = "/v1/browser/download-reports"


class DownloadStartedBody(BaseModel):
    download_id: str
    session_id: str
    suggested_name: str
    url_digest: str
    target_id: str | None = None
    declared_mime: str | None = None


class DownloadFinishedBody(BaseModel):
    byte_size: int = Field(ge=0)
    content_sha256: str = Field(min_length=64, max_length=64)
    #: What the host sniffed from the bytes, as opposed to what the server claimed.
    observed_mime: str | None = None


class DownloadFailedBody(BaseModel):
    reason: str = Field(min_length=1, max_length=200)


def _status_for(error: DownloadError) -> int:
    """404 for a download that does not exist, 409 for one that does and refuses.

    Collapsing both into 409 would tell a host retrying a report for an id the Gateway
    never recorded that the state machine refused it, and the host would keep retrying a
    transition against a row that is not there.
    """
    return 404 if error.reason == "download_unknown" else 409


def build_download_report_router(
    *,
    broker: DownloadBroker,
    sessions: Any,
    audit: Any | None = None,
) -> APIRouter:
    router = APIRouter(prefix=DOWNLOAD_REPORT_PREFIX, tags=["browser-downloads"])

    @router.post("")
    async def report_started(body: DownloadStartedBody):
        """A download exists. Classification runs now, before anything can read the row.

        The session is checked first and a terminal one is refused: a report arriving for a
        session the owner has already closed would otherwise create a record attached to
        nothing, and the owner would see a file appear in a browser that is not open.
        """
        session = await sessions.get(body.session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="interactive_session_unknown")
        if session.state.is_terminal or session.state is InteractiveSessionState.TERMINATING:
            raise HTTPException(status_code=409, detail="interactive_session_not_live")
        try:
            verdict = await broker.create(
                download_id=body.download_id,
                session_id=body.session_id,
                target_id=body.target_id,
                suggested_name=body.suggested_name,
                declared_mime=body.declared_mime,
                url_digest=body.url_digest,
            )
            await broker.start(body.download_id)
        except DownloadError as exc:
            if exc.reason == "download_already_reported":
                # A retry of a report that was already accepted. 409 with the record's
                # *current* state, because the retry may be arriving long after the
                # download finished, and answering "IN_PROGRESS" would tell the caller
                # something that stopped being true before it asked.
                raise HTTPException(
                    status_code=409,
                    detail=f"{exc.reason}:{(await broker.state_of(body.download_id)).value}",
                ) from exc
            # An unsafe name is the caller's fault and never becomes a row: `create`
            # refuses before the INSERT, so there is nothing to clean up here.
            raise HTTPException(status_code=400, detail=exc.reason) from exc
        instruments.record_download(state=DownloadState.IN_PROGRESS.value)
        return {
            "download_id": body.download_id,
            "state": DownloadState.IN_PROGRESS.value,
            "safe_name": verdict.safe_name,
            "dangerous": verdict.dangerous,
            "reason": verdict.reason or None,
        }

    @router.post("/{download_id}/finish")
    async def report_finished(download_id: str, body: DownloadFinishedBody):
        """The host wrote the last byte. Where the record stops is not the host's call."""
        try:
            state = await broker.finish(
                download_id=download_id,
                byte_size=body.byte_size,
                content_sha256=body.content_sha256,
                observed_mime=body.observed_mime,
            )
        except DownloadError as exc:
            raise HTTPException(status_code=_status_for(exc), detail=exc.reason) from exc
        instruments.record_download(state=state.value)
        if audit is not None and state is DownloadState.QUARANTINED:
            # Quarantine is a decision VAN made about the owner's file. It is in the audit
            # chain for the same reason a refusal is: the owner can ask why later.
            await audit.record(
                result="quarantined", device_id=None,
                capability="browser.download.quarantine",
                after={"download_id": download_id},
            )
        return {"download_id": download_id, "state": state.value}

    @router.post("/{download_id}/fail")
    async def report_failed(download_id: str, body: DownloadFailedBody):
        try:
            await broker.fail(download_id, body.reason)
        except DownloadError as exc:
            raise HTTPException(status_code=_status_for(exc), detail=exc.reason) from exc
        instruments.record_download(state=DownloadState.FAILED.value)
        return {"download_id": download_id, "state": DownloadState.FAILED.value}

    return router
