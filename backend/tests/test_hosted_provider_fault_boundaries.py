from __future__ import annotations

import httpx
import pytest

from test_extra_apis import _env, client
from van_gateway.google.transport import FakeGoogleTransport
from van_gateway.research.exa import ExaResearchService


@pytest.mark.parametrize("route", ["search", "certify-canary"])
@pytest.mark.parametrize("failure,reason", [
    (httpx.ReadTimeout("transport URL and secret details"), "exa_timeout"),
    (httpx.ReadError("transport URL and secret details"), "exa_unreachable"),
    (httpx.Response(503, text="private upstream error"), "exa_http_503"),
    (httpx.Response(302, headers={"Location": "https://other.invalid"}), "exa_http_302"),
    (httpx.Response(200, text="not JSON"), "exa_response_malformed"),
    (httpx.Response(200, json=[]), "exa_response_malformed"),
    (httpx.Response(200, json={"results": [{"url": "https://docs.example", "title": "Good source"}, {"url": "https://bad.example", "highlights": {}}]}), "exa_response_malformed"),
    (httpx.Response(200, json={"results": [{"url": "file:///private/document"}]}), "exa_response_malformed"),
    (httpx.Response(200, json={"results": [], "costDollars": "invalid-shape"}), "exa_response_malformed"),
])
async def test_research_provider_faults_are_safe_unavailable_without_partial_evidence(client, route, failure, reason):
    ac, app = client
    calls = []

    def handler(request):
        calls.append(request)
        if isinstance(failure, Exception):
            raise failure
        return failure

    app.state.owner_runtime.research = ExaResearchService(
        app.state.store, api_key="synthetic-exa-secret", egress_enabled=True, transport=httpx.MockTransport(handler),
    )
    await app.state.store.execute("INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES ('exa_ready_evidence_pointer','historical-canary',1)")
    response = await ac.post(f"/v1/runtime/research/{route}", headers={"X-Van-Internal-Token": "test-internal-token"}, json={"query": "Android API docs"})
    assert response.status_code == 503 and response.json() == {"detail": reason}
    assert len(calls) == 1
    assert (await app.state.owner_runtime.research.status())["state"] == "CONFIGURED"
    assert await app.state.store.fetchone("SELECT evidence_id FROM research_evidence") is None
    assert "synthetic-exa-secret" not in response.text and "private" not in response.text


@pytest.mark.parametrize("path,method,body,provider_method", [
    ("vekl/query", "POST", {"mission_id": "00000000-0000-0000-0000-000000000001"}, "query_vekl"),
    ("vekl/certify-canary", "POST", {"mission_id": "00000000-0000-0000-0000-000000000001"}, "certify_vekl"),
    ("obsidian/query", "POST", {"query": "API contract"}, "query_obsidian"),
    ("obsidian/index", "POST", {}, "index_obsidian"),
    ("obsidian/certify", "POST", None, "certify_obsidian"),
    ("notebook/enterprise/recent", "GET", None, "notebook_enterprise_recent"),
    ("notebook/enterprise/notebook-1", "GET", None, "notebook_enterprise_get"),
    ("notebook/enterprise/certify", "POST", None, "certify_notebook_enterprise"),
    ("notebook/consumer/ask", "POST", {"notebook_id": "notebook-1", "question": "What is the contract?"}, "ask_consumer_notebook"),
    ("notebook/consumer/certify", "POST", {"notebook_id": "notebook-1", "question": "What is the contract?"}, "certify_consumer_notebook"),
])
@pytest.mark.parametrize("failure,reason", [
    (httpx.ReadTimeout("private auth exchange endpoint"), "knowledge_provider_timeout"),
    (httpx.ReadError("private harness endpoint"), "knowledge_provider_unavailable"),
])
async def test_direct_knowledge_reads_and_canaries_map_http_faults(client, monkeypatch, path, method, body, provider_method, failure, reason):
    ac, app = client

    async def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(app.state.owner_runtime.knowledge, provider_method, fail)
    response = await ac.request(method, f"/v1/runtime/knowledge/{path}", headers={"X-Van-Internal-Token": "test-internal-token"}, json=body)
    assert response.status_code == 503 and response.json() == {"detail": reason}


async def test_google_preview_body_is_owner_private_and_no_unapproved_effect(client):
    ac, app = client
    app.state.google.transport = FakeGoogleTransport()
    app.state.google.oauth = None
    await app.state.google.store_refresh_token("owner", "synthetic-google-secret", [])
    internal = await ac.get("/v1/google/gmail/drafts/d1/preview", headers={"X-Van-Internal-Token": "test-internal-token"})
    assert internal.status_code == 200 and "preview" not in internal.json()
    assert "Owner-approved reply" not in internal.text
    owner = await ac.get("/v1/owner/google/gmail/drafts/d1/preview")
    assert owner.status_code == 200 and owner.json()["preview"]["body"] == "Owner-approved reply\n"
    assert internal.json()["draft_content_sha256"] == owner.json()["draft_content_sha256"]
    assert owner.json()["source_draft_cleanup"] == "NOT_ATTEMPTED"
    token = ac.headers.pop("X-Van-Device-Token")
    try:
        worker_attempt = await ac.get("/v1/owner/google/gmail/drafts/d1/preview", headers={"X-Van-Internal-Token": "test-internal-token"})
    finally:
        ac.headers["X-Van-Device-Token"] = token
    assert worker_attempt.status_code in {401, 403}
    assert all(name == "gmail_draft_get" for name, _ in app.state.google.transport.calls)
