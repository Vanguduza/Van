"""Public web-acquisition runtime boundary tests."""

from __future__ import annotations

import httpx
import pytest

from tests.conftest_automation import make_store
from van_gateway.automation.external_runtime import ExternalRuntimeRegistry
from van_gateway.browser.acquisition import AcquisitionFrontier
from van_gateway.browser.acquisition_adapters import (
    AcquisitionRuntimeError,
    HttpAcquisitionRuntimeAdapter,
)


async def _item(tmp_path, *, profile_alias="public_research"):
    store = await make_store(tmp_path)
    frontier = AcquisitionFrontier(store)
    item = await frontier.enqueue(
        "https://example.com/catalog",
        profile_alias=profile_alias,
        now_ms=1000,
    )
    return store, item


async def test_public_runtime_envelope_has_no_credentials(tmp_path):
    store, item = await _item(tmp_path)
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json
        seen.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "ok": True,
                "status": 200,
                "content": "catalog",
                "content_digest": "sha256:" + "a" * 64,
                "byte_size": 7,
                "contains_secrets": False,
            },
        )

    adapter = HttpAcquisitionRuntimeAdapter(
        ExternalRuntimeRegistry(store),
        base_url="http://127.0.0.1:9143",
        enabled=True,
        transport=httpx.MockTransport(handler),
    )
    result = await adapter.fetch_http(item)
    assert result["ok"] is True
    assert seen["mode"] == "READ_ONLY_ACQUISITION"
    assert seen["target_domain"] == "example.com"
    assert "cookie" not in seen
    assert "headers" not in seen
    assert "secret_ref" not in seen
    assert "profile_alias" not in seen


async def test_public_runtime_refuses_authenticated_profile(tmp_path):
    store, item = await _item(tmp_path, profile_alias="authenticated_owner")
    adapter = HttpAcquisitionRuntimeAdapter(
        ExternalRuntimeRegistry(store),
        base_url="http://127.0.0.1:9143",
        enabled=True,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(500, json={"error": "SHOULD_NOT_BE_CALLED"})
        ),
    )
    with pytest.raises(AcquisitionRuntimeError, match="PUBLIC_PROFILE_REQUIRED"):
        await adapter.fetch_http(item)


async def test_runtime_refuses_secret_bearing_response(tmp_path):
    store, item = await _item(tmp_path)
    adapter = HttpAcquisitionRuntimeAdapter(
        ExternalRuntimeRegistry(store),
        base_url="http://127.0.0.1:9143",
        enabled=True,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"ok": True, "contains_secrets": True}
            )
        ),
    )
    with pytest.raises(AcquisitionRuntimeError, match="SECRET_BOUNDARY"):
        await adapter.fetch_http(item)
