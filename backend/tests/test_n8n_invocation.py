"""P3-OPS-007 / P3-OPS-006 — a real n8n call, and a backoff that does not stop the world.

`POST /workflows/{id}/run` has no counterpart in the n8n API or anywhere else in
the repository. The only thing that ever exercised it was a test fake that
answered it, which is how an invented endpoint survived: the call and its test
agreed with each other and neither agreed with n8n.
"""

from __future__ import annotations

import asyncio
import json
import time

import httpx
import pytest

from van_gateway.automation.external_runtime import ExternalRuntimeRegistry
from van_gateway.automation.n8n_client import N8nClientError, N8nManagementClient

WEBHOOK_PATH = "van/statements"


def _client(transport, *, store=None, base_url="http://127.0.0.1:5678/api/v1"):
    return N8nManagementClient(
        ExternalRuntimeRegistry(store) if store is not None else None,
        base_url=base_url, api_key="k", enabled=True, transport=transport,
    )


def _n8n(*, active=True, has_webhook=True, run_status=200):
    """A fake shaped like the real n8n: management API under /api/v1, webhooks not."""
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.startswith("/api/v1/workflows/") and request.method == "GET":
            nodes = []
            if has_webhook:
                nodes.append({"type": "n8n-nodes-base.webhook",
                              "parameters": {"path": WEBHOOK_PATH}})
            nodes.append({"type": "n8n-nodes-base.httpRequest", "parameters": {}})
            return httpx.Response(200, json={"id": "wf-1", "active": active, "nodes": nodes})
        if path == f"/webhook/{WEBHOOK_PATH}" and request.method == "POST":
            if not active:
                return httpx.Response(404, json={"message": "webhook not registered"})
            seen["url"] = str(request.url)
            seen["body"] = json.loads(request.content)
            return httpx.Response(run_status, json={"executionId": "exec-1"})
        return httpx.Response(404)

    return httpx.MockTransport(handler), seen


@pytest.mark.asyncio
async def test_invoking_a_workflow_never_touches_a_management_run_endpoint():
    """The finding itself, asserted against what the client does rather than
    against what its source says. Every URL it opens is recorded, and none of
    them may be the endpoint n8n does not have."""
    touched: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        touched.append(f"{request.method} {request.url.path}")
        if request.url.path.startswith("/api/v1/workflows/") and request.method == "GET":
            return httpx.Response(200, json={"nodes": [
                {"type": "n8n-nodes-base.webhook", "parameters": {"path": WEBHOOK_PATH}}
            ]})
        return httpx.Response(200, json={"executionId": "exec-1"})

    await _client(httpx.MockTransport(handler)).run_workflow("wf-1", {})
    assert touched
    assert not any(call.endswith("/run") for call in touched), touched
    assert f"POST /webhook/{WEBHOOK_PATH}" in touched


@pytest.mark.asyncio
async def test_a_workflow_is_invoked_through_its_own_webhook():
    transport, seen = _n8n()
    client = _client(transport)
    result = await client.run_workflow("wf-1", {"run_id": "r1", "capability_grant": "g"})
    assert result["executionId"] == "exec-1"
    assert seen["url"] == f"http://127.0.0.1:5678/webhook/{WEBHOOK_PATH}"
    # The run envelope and the run-scoped grant still travel in the body.
    assert seen["body"]["capability_grant"] == "g"


def test_the_webhook_root_is_derived_from_the_management_root():
    """Webhooks are not under /api/v1. A second setting would drift on a host
    where only one was updated."""
    client = _client(None)
    assert client.webhook_url("a/b") == "http://127.0.0.1:5678/webhook/a/b"
    explicit = N8nManagementClient(
        None, base_url="http://127.0.0.1:5678/api/v1", api_key="k",
        webhook_base_url="http://n8n.internal:5678",
    )
    assert explicit.webhook_url("/a") == "http://n8n.internal:5678/webhook/a"


@pytest.mark.asyncio
async def test_the_path_comes_from_the_deployed_workflow_not_from_vans_copy():
    """A workflow edited in the n8n UI is exactly the case where they differ, and
    posting to the compiled path would silently do nothing."""
    transport, _seen = _n8n()
    client = _client(transport)
    assert await client.trigger_path("wf-1") == WEBHOOK_PATH


@pytest.mark.asyncio
async def test_a_workflow_with_no_trigger_is_refused_rather_than_invoked():
    transport, _ = _n8n(has_webhook=False)
    client = _client(transport)
    with pytest.raises(N8nClientError) as raised:
        await client.run_workflow("wf-1", {})
    assert raised.value.code == "AUTOMATION_WORKFLOW_NOT_INVOCABLE"


@pytest.mark.asyncio
async def test_an_inactive_workflow_gets_its_own_error_code():
    """n8n answers 404 on a webhook whose workflow is not active. That is a
    deployment fault with a specific remedy, not a generic request failure."""
    transport, _ = _n8n(active=False)
    client = _client(transport)
    with pytest.raises(N8nClientError) as raised:
        await client.run_workflow("wf-1", {})
    assert raised.value.code == "AUTOMATION_WORKFLOW_NOT_ACTIVE"


@pytest.mark.asyncio
async def test_a_plain_text_webhook_response_is_still_a_run():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/api/v1/workflows/"):
            return httpx.Response(200, json={"nodes": [
                {"type": "n8n-nodes-base.webhook", "parameters": {"path": WEBHOOK_PATH}}
            ]})
        return httpx.Response(200, text="OK")

    client = _client(httpx.MockTransport(handler))
    assert await client.run_workflow("wf-1", {}) == {"body": "OK"}


# ---------------------------------------------------------------- P3-OPS-006

@pytest.mark.asyncio
async def test_a_retry_backoff_does_not_block_the_event_loop():
    """This was `time.sleep` inside an `async def` inside the gateway's single
    event loop: one n8n 503 stopped every other request the gateway was serving,
    including the owner's."""
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(503)

    client = _client(httpx.MockTransport(handler))
    client.BACKOFF_SECONDS = (0.05, 0.05)

    ticks = {"n": 0}

    async def other_work() -> None:
        # If the loop is blocked, this task cannot run while the retry sleeps.
        for _ in range(40):
            ticks["n"] += 1
            await asyncio.sleep(0.005)

    started = time.monotonic()
    companion = asyncio.create_task(other_work())
    with pytest.raises(N8nClientError):
        await client.get_workflow("wf-1")
    elapsed = time.monotonic() - started
    companion.cancel()

    assert attempts["n"] == client.MAX_ATTEMPTS
    assert elapsed >= 0.09, "the backoff did not actually wait"
    assert ticks["n"] > 5, "the event loop was blocked while the retry slept"
