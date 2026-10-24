"""Real client/ASGI stream lifecycle with controlled transport faults, never live DIAL."""
import asyncio
import ssl

from fastapi import FastAPI
import httpx
import pytest

from van_gateway.degraded.registry import DegradedRegistry
from van_gateway.dial_dev.api import build_dial_dev_router
from van_gateway.dial_dev.client import DialDevClient, DialDevUnavailable, _finish_stream_close
from van_gateway.dial_dev.config import DialDevConfig
from van_gateway.idempotency.service import IdempotencyService
from van_gateway.storage.db import Store
from test_dial_dev_attention import world, serve_needs_me, _until


FRAME = b'data: {"projection_revision":"fixture","changed":[]}\n\n'
FIXTURE_TOKEN = "fixture-credential-0123456789abcdef0123456789"


class ControlledStream(httpx.AsyncByteStream):
    def __init__(self, *, frames=1, failure=None, held=False):
        self.frames, self.failure, self.held = frames, failure, held
        self.close_count = 0
        self.close_started = asyncio.Event()
        self.close_gate = None
        self.read_gate = asyncio.Event()

    async def __aiter__(self):
        for _ in range(self.frames):
            yield FRAME
        if self.held:
            await self.read_gate.wait()
        if self.failure is not None:
            raise self.failure

    async def aclose(self):
        self.close_started.set()
        if self.close_gate is not None:
            await self.close_gate.wait()
        await asyncio.sleep(0.01)
        self.close_count += 1


class ControlledTransport(httpx.AsyncBaseTransport):
    def __init__(self, stream):
        self.stream, self.requests, self.close_count = stream, [], 0

    async def handle_async_request(self, request):
        self.requests.append(request.url.path)
        return httpx.Response(200, stream=self.stream, headers={"content-type": "text/event-stream"})

    async def aclose(self):
        self.close_count += 1


def setup_stream(tmp_path, stream):
    token = tmp_path / "fixture.token"
    token.write_text(FIXTURE_TOKEN)
    config = DialDevConfig(enabled=True, base_url="https://fixture.invalid", token_file=str(token))
    transport = ControlledTransport(stream)
    client = DialDevClient(config, transport=transport)
    degraded, app = DegradedRegistry(), FastAPI()
    app.include_router(build_dial_dev_router(client=client, config=config,
        idempotency=IdempotencyService(Store(str(tmp_path / "unused.sqlite"))), degraded=degraded))
    return app, client, degraded, transport


@pytest.mark.parametrize("frames", [0, 1])
@pytest.mark.parametrize("failure,reason", [
    pytest.param(ssl.SSLError("private alert text " + FIXTURE_TOKEN), "unreachable", id="tls-alert"),
    pytest.param(httpx.ReadError("private route text " + FIXTURE_TOKEN), "unreachable", id="read-error"),
    pytest.param(httpx.ReadTimeout("private timeout text " + FIXTURE_TOKEN), "timeout", id="read-timeout"),
])
async def test_post_header_failure_is_safe_terminal_sse_and_closes_upstream(tmp_path, frames, failure, reason):
    stream = ControlledStream(frames=frames, failure=failure)
    app, _, degraded, transport = setup_stream(tmp_path, stream)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://van.fixture") as phone:
        response = await phone.get("/v1/dial-dev/events")
    assert response.status_code == 200  # HTTP headers were already committed.
    assert response.content == FRAME * frames + (
        '\nevent: error\ndata: {"error":"dial_dev_unavailable","reason":"' + reason + '"}\n\n').encode()
    assert FIXTURE_TOKEN not in response.text and "private" not in response.text
    assert degraded.codes() == ["DIAL_DEV_UNAVAILABLE"]
    assert stream.close_count == transport.close_count == 1
    assert transport.requests == ["/v1/dev/events"]  # No read or effect retry.


@pytest.mark.parametrize("frames", [0, 2])
async def test_clean_and_empty_eof_preserve_exact_frames_and_close_once(tmp_path, frames):
    stream = ControlledStream(frames=frames)
    app, _, degraded, transport = setup_stream(tmp_path, stream)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://van.fixture") as phone:
        response = await phone.get("/v1/dial-dev/events")
    assert response.status_code == 200 and response.content == FRAME * frames
    assert degraded.codes() == []
    assert stream.close_count == transport.close_count == 1


async def test_programming_failure_propagates_after_actual_cleanup(tmp_path):
    stream = ControlledStream(failure=ValueError("fixture programming defect"))
    app, _, degraded, transport = setup_stream(tmp_path, stream)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://van.fixture") as phone:
        with pytest.raises(ValueError, match="fixture programming defect"):
            await phone.get("/v1/dial-dev/events")
    assert stream.close_count == transport.close_count == 1
    assert degraded.codes() == []


async def test_fault_after_partial_event_keeps_typed_error_in_its_own_sse_event(tmp_path):
    from van_gateway.dial_dev.attention import parse_sse

    class PartialEvent(ControlledStream):
        async def __aiter__(self):
            yield b'data: {"partial":"unfinished"\n'
            raise ssl.SSLError("fixture late alert")

    stream = PartialEvent()
    app, _, degraded, transport = setup_stream(tmp_path, stream)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://van.fixture") as phone:
        response = await phone.get("/v1/dial-dev/events")

    async def lines():
        for line in response.text.splitlines():
            yield line

    assert [event async for event in parse_sse(lines())] == [None, {
        "error": "dial_dev_unavailable", "reason": "unreachable"}]
    assert stream.close_count == transport.close_count == 1
    assert degraded.codes() == ["DIAL_DEV_UNAVAILABLE"]


async def test_downstream_asgi_disconnect_finishes_private_close_without_marking_dial_down(tmp_path):
    stream = ControlledStream(held=True)
    app, _, degraded, transport = setup_stream(tmp_path, stream)
    disconnected, sent = asyncio.Event(), []
    initial = True

    async def receive():
        nonlocal initial
        if initial:
            initial = False
            return {"type": "http.request", "body": b"", "more_body": False}
        await disconnected.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)
        if message["type"] == "http.response.body" and message.get("body"):
            disconnected.set()

    scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1", "scheme": "http", "method": "GET", "path": "/v1/dial-dev/events",
        "raw_path": b"/v1/dial-dev/events", "query_string": b"", "root_path": "", "headers": [],
        "client": ("127.0.0.1", 1000), "server": ("van.fixture", 80)}
    await asyncio.wait_for(app(scope, receive, send), 1)
    assert any(item.get("body") for item in sent)
    assert stream.close_count == transport.close_count == 1
    assert degraded.codes() == []


async def test_repeated_caller_cancel_does_not_abandon_one_private_close(tmp_path):
    stream = ControlledStream(held=True)
    stream.close_gate = asyncio.Event()
    _, client, _, transport = setup_stream(tmp_path, stream)
    upstream = await client.open_stream("/v1/dev/events")
    closing = asyncio.create_task(upstream.close())
    await stream.close_started.wait()
    closing.cancel()
    await asyncio.sleep(0)
    closing.cancel()
    stream.close_gate.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(closing, 1)
    await upstream.close()
    assert stream.close_count == transport.close_count == 1


async def test_private_close_deadline_is_bounded_and_cancels_stuck_task():
    gate = asyncio.Event()
    task = asyncio.create_task(gate.wait())
    with pytest.raises(DialDevUnavailable, match="timeout"):
        await asyncio.wait_for(_finish_stream_close(task, timeout_s=0.01), 0.5)
    await asyncio.sleep(0)
    assert task.cancelled()


@pytest.mark.parametrize("fault", ["read_tls_alert", "transport_close"])
async def test_attention_reconnects_after_actual_stream_fault_and_cleanup(world, fault):
    ingest, dial, _, degraded = world
    serve_needs_me(dial, [], "fixture-current")

    class CloseFailure(ControlledStream):
        async def aclose(self):
            self.close_count += 1
            raise httpx.ReadError("fixture close transport failure")

    first = (ControlledStream(failure=ssl.SSLError("fixture read alert"))
             if fault == "read_tls_alert" else CloseFailure())
    restored = ControlledStream(held=True)
    attempts, observed_down = [], []

    def serve(request):
        attempts.append(request.url.path)
        if len(attempts) > 1:
            observed_down.append("DIAL_DEV_EVENT_STREAM_DOWN" in degraded.codes())
        return httpx.Response(200, stream=first if len(attempts) == 1 else restored,
            headers={"content-type": "text/event-stream"})

    dial.raw("GET", "/v1/dev/events", serve)
    ingest.start()
    await _until(lambda: ingest.connects >= 2)
    assert ingest.running and observed_down == [True]
    assert "DIAL_DEV_EVENT_STREAM_DOWN" not in degraded.codes()
    assert first.close_count == 1
    assert attempts == ["/v1/dev/events", "/v1/dev/events"]
    await ingest.stop(grace_s=0.01)
    assert restored.close_count == 1
