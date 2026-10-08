"""Proposed provider consumer refuses unbound/mismatched/unobserved targets."""
import hashlib
import httpx
import pytest
from van_gateway.browser.artifact_provider import ArtifactProviderBinding, OwnerArtifactProvider, ArtifactProviderError, build_artifact_provider_router
from van_gateway.browser.action_plans import digest


async def test_unbound_external_provider_cannot_claim_local_copy_success():
    with pytest.raises(ArtifactProviderError, match="contract_unbound"):
        await OwnerArtifactProvider().submit(content=b"a", content_sha256=hashlib.sha256(b"a").hexdigest(),
            admission_id="admission", signed_admission="a"*32, idempotency_key="request")


@pytest.mark.parametrize("failure", ["provider", "namespace", "truth", "bytes", "lost_reply", "capability"])
async def test_provider_write_needs_exact_capability_and_independent_target_readback(failure, monkeypatch):
    capability = {"contract":OwnerArtifactProvider.CONTRACT,"provider":"ORACLE_OWNER_ARCHIVE",
        "provider_identity":"qualified-oracle-store", "current_admission_introspection":True,
        "namespace_admissions":[{"owner_namespace":"owner","project_namespace":"van"}]}
    binding = ArtifactProviderBinding("ORACLE_OWNER_ARCHIVE","https://oracle.test","ca","cert","key",
        "qualified-oracle-store",digest(capability),"owner","van")
    content = b"inert owner file"
    sha = hashlib.sha256(content).hexdigest()
    receipt = {**{key:capability[key] for key in ("contract","provider","provider_identity")},
        "owner_namespace":"owner","project_namespace":"van","content_sha256":sha,"byte_size":len(content),
        "admission_id":"admission","receipt_id":"actual-target-receipt","executed_content":False,
        "project_truth_promoted":False,"owner_truth_promoted":False,"status":"ARCHIVED",
        "source_authority":"UNTRUSTED_OWNER_FILE_EVIDENCE"}
    seen = []
    def handler(request):
        seen.append(request.method)
        if request.url.path.endswith("capabilities"):
            return httpx.Response(200,json={**capability,"current_admission_introspection": failure != "capability"})
        if request.method == "PUT":
            assert request.content == content
            if failure == "lost_reply": raise httpx.ReadTimeout("uncertain write")
            return httpx.Response(201,json={"success":True})
        bad = {"provider":"LOCAL_COPY", "namespace":"other", "truth":True, "bytes":"0"*64}
        key = {"provider":"provider", "namespace":"project_namespace", "truth":"owner_truth_promoted", "bytes":"content_sha256"}.get(failure)
        return httpx.Response(200,json={**receipt, **({key:bad[failure]} if key else {})})
    provider = OwnerArtifactProvider(binding)
    monkeypatch.setattr(provider,"_client",lambda binding: httpx.AsyncClient(base_url=binding.origin,
        transport=httpx.MockTransport(handler),trust_env=False,follow_redirects=False))
    with pytest.raises(ArtifactProviderError):
        await provider.submit(content=content,content_sha256=sha,admission_id="admission",
            signed_admission="a"*32,idempotency_key="request")
    assert seen.count("PUT") <= 1


@pytest.mark.parametrize("provider", ["ORACLE_OWNER_ARCHIVE", "VEKL_OWNER_CANDIDATE_INGRESS"])
@pytest.mark.parametrize("persisted", [b"inert owner file", b"different bytes", b"inert owner file with excess"])
async def test_provider_receipt_requires_distinct_bounded_persisted_content_readback(provider, persisted, monkeypatch):
    content = b"inert owner file"
    sha = hashlib.sha256(content).hexdigest()
    capability = {"contract":OwnerArtifactProvider.CONTRACT,"provider":provider,
        "provider_identity":"qualified-owner-provider", "current_admission_introspection":True,
        "namespace_admissions":[{"owner_namespace":"owner","project_namespace":"van"}]}
    if provider == "VEKL_OWNER_CANDIDATE_INGRESS":
        capability["oracle_instruction_job_id"] = "actual-admitted-job"
    binding = ArtifactProviderBinding(provider,"https://provider.test","ca","cert","key",
        "qualified-owner-provider",digest(capability),"owner","van")
    receipt = {"contract":OwnerArtifactProvider.CONTRACT,"provider":provider,"provider_identity":"qualified-owner-provider",
        "owner_namespace":"owner","project_namespace":"van","content_sha256":sha,"byte_size":len(content),
        "admission_id":"admission","receipt_id":"target-receipt","executed_content":False,
        "project_truth_promoted":False,"owner_truth_promoted":False,"source_authority":"UNTRUSTED_OWNER_FILE_EVIDENCE",
        "status":"ARCHIVED" if provider == "ORACLE_OWNER_ARCHIVE" else "CANDIDATE_RECORDED"}
    if provider == "VEKL_OWNER_CANDIDATE_INGRESS":
        receipt.update(source_authority="UNTRUSTED_OWNER_FILE_EVIDENCE",canonical_candidate_id="canonical-candidate")
    seen = []
    def handler(request):
        seen.append((request.method, request.url.path))
        if request.url.path.endswith("capabilities"):
            return httpx.Response(200,json=capability)
        if request.method == "PUT":
            assert request.content == content
            return httpx.Response(201,json={"success":True})
        if request.url.path.endswith("/content"):
            return httpx.Response(200,content=persisted,headers={"Content-Type":"application/octet-stream"})
        return httpx.Response(200,json=receipt)
    adapter = OwnerArtifactProvider(binding)
    monkeypatch.setattr(adapter,"_client",lambda _:httpx.AsyncClient(base_url=binding.origin,
        transport=httpx.MockTransport(handler),trust_env=False,follow_redirects=False))
    if persisted == content:
        observed = await adapter.submit(content=content,content_sha256=sha,admission_id="admission",signed_admission="a"*32,idempotency_key="request")
        assert observed["independent_content_readback"] == {"content_sha256":sha,"byte_size":len(content),"observer":"VAN_BOUNDED_PERSISTED_BYTES_READBACK"}
    else:
        with pytest.raises(ArtifactProviderError,match="content_mismatch"):
            await adapter.submit(content=content,content_sha256=sha,admission_id="admission",signed_admission="a"*32,idempotency_key="request")
    assert [method for method,_ in seen] == ["GET","PUT","GET","GET"]


async def test_empty_provider_config_exposes_unavailable_and_valid_openapi():
    from types import SimpleNamespace
    from fastapi import FastAPI
    class Sessions:
        async def get(self, sid):
            return SimpleNamespace(owner_device_id="phone") if sid == "sid" else None
    app = FastAPI()
    @app.middleware("http")
    async def proof(request, call_next):
        request.state.van_device_id = "phone"
        return await call_next(request)
    app.include_router(build_artifact_provider_router(sessions=Sessions(),providers={}))
    assert "/v1/browser/interactive-sessions/{session_id}/file-provider-contracts" in app.openapi()["paths"]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://test") as client:
        body = (await client.get("/v1/browser/interactive-sessions/sid/file-provider-contracts")).json()
        assert body["live_effects_verified"] == 0 and len(body["contracts"]) == 2
        assert all(row["adapter_implemented"] is True and row["executable"] is False
                   and row["target_contract_qualified"] is False and row["reason"] == "TARGET_CONTRACT_UNBOUND" for row in body["contracts"])


async def test_capability_response_is_stream_bounded_before_json_parsing(monkeypatch):
    seen=[]
    class Oversized(httpx.AsyncByteStream):
        async def __aiter__(self):
            for i in range(1000):
                seen.append(i)
                yield b"x"*4096
    binding=ArtifactProviderBinding("ORACLE_OWNER_ARCHIVE","https://provider.test","ca","cert","key",
        "provider-fixture","0"*64,"owner","van")
    adapter=OwnerArtifactProvider(binding)
    monkeypatch.setattr(adapter,"_client",lambda _:httpx.AsyncClient(base_url=binding.origin,
        transport=httpx.MockTransport(lambda request:httpx.Response(200,stream=Oversized())),trust_env=False))
    with pytest.raises(ArtifactProviderError,match="response_too_large"):
        await adapter.probe()
    assert len(seen)<=16  # At most one fixed64KiB reader chunk, not the response.


async def test_duplicate_capability_fields_are_not_interpreted_as_a_qualified_contract(monkeypatch):
    binding=ArtifactProviderBinding("ORACLE_OWNER_ARCHIVE","https://provider.test","ca","cert","key",
        "provider-fixture","0"*64,"owner","van")
    adapter=OwnerArtifactProvider(binding)
    monkeypatch.setattr(adapter,"_client",lambda _:httpx.AsyncClient(base_url=binding.origin,
        transport=httpx.MockTransport(lambda request:httpx.Response(200,content=b'{"provider":"ORACLE_OWNER_ARCHIVE","provider":"ORACLE_OWNER_ARCHIVE"}')),trust_env=False))
    with pytest.raises(ArtifactProviderError,match="response_invalid"):
        await adapter.probe()
