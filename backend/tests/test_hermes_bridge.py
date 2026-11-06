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

@pytest.mark.asyncio
@pytest.mark.parametrize('body',[b'not json',b'[]',b'null'])
async def test_malformed_health_is_degraded(body):
    async def handler(request):
        return httpx.Response(200,content=body)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert (await HermesBridge('http://hermes.test','test',client=client).health())['ok'] is False

@pytest.mark.asyncio
async def test_explicit_unhealthy_body_is_not_promoted_to_ready():
    async def handler(request):
        return httpx.Response(200,json={'ok':False,'status':'unhealthy'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert (await HermesBridge('http://hermes.test','test',client=client).health())['ok'] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["true", "false", 1, 0, None])
async def test_untyped_provider_health_cannot_mint_readiness(value):
    async def handler(request):
        return httpx.Response(200, json={"ok": value})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert (await HermesBridge("http://hermes.test", "test", client=client).health())["ok"] is False

@pytest.mark.asyncio
@pytest.mark.parametrize('body',[b'not json',b'[]',b'{}',b'{"id":""}',b'{"id":123}',b'{"id":" run-1 "}',b'{"id":"run\\n1"}'])
async def test_malformed_post_receipt_is_outcome_unknown(body):
    from van_gateway.hermes.bridge import HermesBridgeError
    async def handler(request):
        return httpx.Response(200,content=body)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(HermesBridgeError) as raised:
            await HermesBridge('http://hermes.test','test',client=client).create_run('test')
        assert raised.value.code=='hermes_outcome_unknown' and raised.value.retry_safe is False

@pytest.mark.asyncio
@pytest.mark.parametrize('status,retry_safe',[(401,True),(403,True),(422,True),(408,False),(409,False),(500,False),(503,False)])
async def test_only_definitive_http_rejections_allow_retry(status,retry_safe):
    from van_gateway.hermes.bridge import HermesBridgeError
    async def handler(request):
        return httpx.Response(status,json={'error':'test failure'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(HermesBridgeError) as raised:
            await HermesBridge('http://hermes.test','test',client=client).create_run('test')
        assert raised.value.retry_safe is retry_safe

@pytest.mark.asyncio
@pytest.mark.parametrize('error,retry_safe',[(httpx.ConnectError,True),(httpx.ConnectTimeout,True),(httpx.ReadTimeout,False),(httpx.WriteError,False)])
async def test_only_no_send_transport_failures_allow_retry(error,retry_safe):
    from van_gateway.hermes.bridge import HermesBridgeError
    async def handler(request):
        raise error('test-only transport failure',request=request)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(HermesBridgeError) as raised:
            await HermesBridge('http://hermes.test','test',client=client).create_run('test')
        assert raised.value.retry_safe is retry_safe


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [b"not json", b"[]", b"null"])
async def test_invalid_capability_payload_is_explicitly_unavailable(body):
    from van_gateway.hermes.bridge import HermesBridgeError
    async def handler(request):
        return httpx.Response(200, content=body)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(HermesBridgeError) as raised:
            await HermesBridge("http://hermes.test", "test", client=client).capabilities()
        assert raised.value.code == "capabilities_unavailable"


@pytest.mark.asyncio
async def test_redirect_responses_cannot_mint_health_run_or_capability_receipts():
    from van_gateway.hermes.bridge import HermesBridgeError
    requests = []
    async def handler(request):
        requests.append(request.url.path)
        return httpx.Response(302, json={"ok": True, "id": "unqualified-run"},
                              headers={"Location": "https://unqualified.test/run"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        bridge = HermesBridge("http://hermes.test", "test", client=client)
        assert (await bridge.health())["ok"] is False
        with pytest.raises(HermesBridgeError) as run:
            await bridge.create_run("owner task")
        assert run.value.retry_safe is False
        with pytest.raises(HermesBridgeError) as capabilities:
            await bridge.capabilities()
        assert capabilities.value.code == "capabilities_unavailable"
    assert requests == ["/p/van/health", "/p/van/v1/runs", "/p/van/v1/capabilities"]
