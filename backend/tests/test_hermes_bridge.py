from __future__ import annotations

import httpx
import pytest

from van_gateway.hermes.bridge import HermesBridge


@pytest.mark.asyncio
async def test_named_profile_uses_canonical_multiplex_prefix():
    seen: list[tuple[str, str]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        if request.url.path.endswith("/health"):
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path.endswith("/v1/capabilities"):
            return httpx.Response(200, json={"runs": True})
        return httpx.Response(404, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://hermes.test") as client:
        bridge = HermesBridge("http://hermes.test", "secret", profile="van", client=client)
        health = await bridge.health()
        caps = await bridge.capabilities()

    assert health["ok"] is True
    assert caps["runs"] is True
    assert seen == [
        ("GET", "/p/van/health"),
        ("GET", "/p/van/v1/capabilities"),
    ]


@pytest.mark.asyncio
async def test_default_profile_keeps_unprefixed_route():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health"
        return httpx.Response(200, json={"status": "ok"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://hermes.test") as client:
        bridge = HermesBridge("http://hermes.test", "secret", profile="default", client=client)
        assert (await bridge.health())["ok"] is True
