from __future__ import annotations

import pathlib

import httpx
import pytest

from van_gateway.automation.temporal_bridge import (
    DurableSignalBody,
    DurableStartBody,
    TemporalBridgeClient,
    TemporalBridgeError,
)
from van_gateway.config import Settings


def _settings(**overrides):
    values = dict(
        temporal_enabled=True,
        temporal_bridge_url="http://127.0.0.1:9150",
        temporal_bridge_token="t" * 48,
        temporal_timeout_seconds=2.0,
    )
    values.update(overrides)
    return Settings(**values)


async def test_temporal_bridge_fails_closed_when_disabled_or_unconfigured():
    disabled = TemporalBridgeClient(_settings(temporal_enabled=False))
    with pytest.raises(TemporalBridgeError, match="TEMPORAL_DISABLED"):
        await disabled.health()

    unconfigured = TemporalBridgeClient(_settings(temporal_bridge_url=""))
    with pytest.raises(TemporalBridgeError, match="TEMPORAL_UNCONFIGURED"):
        await unconfigured.health()


async def test_temporal_bridge_sends_dedicated_token_and_exact_start_contract(monkeypatch):
    seen = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["url"] = str(request.url)
        seen["token"] = request.headers.get("x-van-temporal-token")
        seen["json"] = __import__("json").loads(request.content)
        return httpx.Response(200, json={"accepted": True, "workflow_id": "wf-1"})

    transport = httpx.MockTransport(handler)

    class ClientFactory:
        def __init__(self, *args, **kwargs):
            self.client = httpx.AsyncClient(transport=transport, timeout=kwargs.get("timeout"))
        async def __aenter__(self):
            return self.client
        async def __aexit__(self, exc_type, exc, tb):
            await self.client.aclose()

    monkeypatch.setattr("van_gateway.automation.temporal_bridge.httpx.AsyncClient", ClientFactory)
    client = TemporalBridgeClient(_settings())
    body = DurableStartBody(
        workflow_id="wf-1",
        process_kind="strategy_promotion",
        idempotency_key="idem-0001",
        payload={"candidate": "c-7"},
        timeout_seconds=900,
    )
    result = await client.start(body)
    assert result["accepted"] is True
    assert seen == {
        "method": "POST",
        "url": "http://127.0.0.1:9150/v1/workflows/start",
        "token": "t" * 48,
        "json": body.model_dump(mode="json"),
    }


async def test_temporal_bridge_translates_runtime_refusal(monkeypatch):
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"detail": "workflow_id_idempotency_conflict"})

    transport = httpx.MockTransport(handler)

    class ClientFactory:
        def __init__(self, *args, **kwargs):
            self.client = httpx.AsyncClient(transport=transport)
        async def __aenter__(self):
            return self.client
        async def __aexit__(self, exc_type, exc, tb):
            await self.client.aclose()

    monkeypatch.setattr("van_gateway.automation.temporal_bridge.httpx.AsyncClient", ClientFactory)
    client = TemporalBridgeClient(_settings())
    with pytest.raises(TemporalBridgeError) as exc:
        await client.signal(
            "wf-1",
            DurableSignalBody(command="CHECKPOINT", detail="sealed", payload={"seq": 2}),
        )
    assert exc.value.code == "TEMPORAL_RUNTIME_REFUSED"
    assert "idempotency_conflict" in exc.value.detail


def test_temporal_runtime_deployment_is_self_hosted_and_loopback_only():
    root = pathlib.Path(__file__).resolve().parents[2]
    compose = (root / "deploy/van-trading-core/temporal/docker-compose.yml").read_text()
    service = (root / "deploy/van-trading-core/systemd/vati-temporal-server.service").read_text()
    runtime = (root / "deploy/van-trading-core/temporal/runtime.py").read_text()
    workflow = (root / "deploy/van-trading-core/temporal/workflows.py").read_text()

    assert "temporalio/auto-setup:1.32.0" in compose
    assert '"127.0.0.1:7233:7233"' in compose
    assert "temporal-postgresql:" in compose
    assert "temporal-ui" not in compose
    assert "docker compose" in service and "127.0.0.1/7233" in service
    assert "Client.connect(TEMPORAL_ADDRESS" in runtime
    assert "@workflow.defn" in workflow
    assert 'executes_live_orders": False' in runtime
