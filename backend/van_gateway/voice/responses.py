"""Spoken results use the same durable result and owner check as command readback.

The client chooses an idempotent playback request, never the words or work status.
Reading or repeating an answer cannot re-dispatch the command that produced it.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from van_gateway.coherence.owner_status import FINISHED, NEEDS_OWNER, OwnerWorkStatus, qualified_outcome
from van_gateway.voice.speech_stream import SpeechStream, SpeechStreamService


def with_spoken_result(result: dict) -> dict:
    status = OwnerWorkStatus(result["owner_status"])
    text = qualified_outcome(status, result.get("final_outcome"), finished=result.get("finished", False))
    core = {key: result.get(key) for key in (
        "command_id", "mission_id", "mission_state", "owner_status", "finished",
        "final_outcome", "verification_state", "updated_at_ms",
    )}
    digest = hashlib.sha256(json.dumps(core, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {**result, "result_ref": f"result_{digest}", "spoken_text": text}


class PlaybackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_id: str = Field(min_length=1, max_length=256)
    result_ref: str = Field(pattern=r"^result_[a-f0-9]{64}$")
    playback_request_id: str = Field(min_length=16, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


class CursorReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    last_received_segment: StrictInt = Field(ge=-1)
    last_spoken_segment: StrictInt = Field(ge=-1)


class BoundSpeechResponses:
    def __init__(self, streams: SpeechStreamService,
                 read_result: Callable[[str, str], Awaitable[dict]], authority):
        self.streams, self.read_result, self.authority = streams, read_result, authority

    async def open(self, body: PlaybackRequest, device_id: str) -> dict:
        result = await self.read_result(body.command_id, device_id)
        if result["result_ref"] != body.result_ref:
            raise HTTPException(409, "speech_result_changed")
        status = OwnerWorkStatus(result["owner_status"])
        if status not in FINISHED | NEEDS_OWNER:
            raise HTTPException(409, "speech_result_not_ready")
        authority = await self.authority.get(body.command_id)
        if authority is not None and authority.device_id != device_id:
            raise HTTPException(404, "command_unknown")
        turn_id = authority.turn_id if authority is not None else None
        response_id = "response_" + hashlib.sha256(json.dumps([
            body.command_id, body.result_ref, body.playback_request_id,
        ], separators=(",", ":")).encode()).hexdigest()
        try:
            stream = self.streams.open(
                response_id=response_id, turn_id=turn_id or body.command_id,
                device_id=device_id, text=result["spoken_text"],
                source_command_id=body.command_id, source_result_ref=body.result_ref,
            )
        except ValueError as exc:
            raise HTTPException(429 if str(exc) == "speech_capacity_reached" else 409, str(exc)) from exc
        return self.payload(stream)

    async def require(self, stream_id: str, device_id: str) -> SpeechStream:
        stream = self.streams.get(stream_id)
        if stream is None or stream.device_id != device_id or not stream.source_command_id:
            raise HTTPException(404, "speech_stream_unknown")
        try:
            result = await self.read_result(stream.source_command_id, device_id)
        except HTTPException:
            self.streams.discard(stream_id)
            raise HTTPException(404, "speech_stream_unknown") from None
        if result["result_ref"] != stream.source_result_ref:
            self.streams.discard(stream_id)
            raise HTTPException(409, "speech_result_changed")
        return stream

    def payload(self, stream: SpeechStream) -> dict:
        return {
            "command_id": stream.source_command_id, "result_ref": stream.source_result_ref,
            "response_id": stream.response_id, "speech_stream_id": stream.speech_stream_id,
            "turn_id": stream.turn_id, "last_received_segment": stream.last_received_segment,
            "last_spoken_segment": stream.last_spoken_segment,
            "resume_from_segment": stream.last_spoken_segment + 1,
            "interrupted": stream.interrupted, "complete": stream.complete,
            "total_segments": len(stream.segments),
            "segments": [s.as_json() for s in self.streams.resume_from(stream.speech_stream_id)],
        }

    async def resume_state(self, device_id: str) -> dict | None:
        state = self.streams.response_state(device_id)
        while state is not None:
            try:
                return self.payload(await self.require(state["speech_stream_id"], device_id))
            except HTTPException:
                # An obsolete or unbound cache entry is not resume authority.
                self.streams.discard(state["speech_stream_id"])
                state = self.streams.response_state(device_id)
        return None


def build_voice_router(service: BoundSpeechResponses) -> APIRouter:
    router = APIRouter(prefix="/v1/voice")

    def device(request: Request) -> str:
        value = getattr(request.state, "van_device_id", "")
        if not value:
            raise HTTPException(403, "device_identity_required")
        return value

    @router.post("/responses")
    async def open_response(body: PlaybackRequest, request: Request):
        return await service.open(body, device(request))

    @router.get("/streams/{stream_id}")
    async def read_stream(stream_id: str, request: Request):
        return service.payload(await service.require(stream_id, device(request)))

    @router.post("/streams/{stream_id}/cursors")
    async def report_cursors(stream_id: str, body: CursorReport, request: Request):
        stream = await service.require(stream_id, device(request))
        try:
            service.streams.report_cursors(stream_id, **body.model_dump())
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return service.payload(stream)

    @router.post("/streams/{stream_id}/interrupt")
    async def interrupt(stream_id: str, request: Request):
        stream = await service.require(stream_id, device(request))
        service.streams.interrupt(stream_id)
        return service.payload(stream)

    return router
