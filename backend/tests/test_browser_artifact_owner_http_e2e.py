"""Actual signed owner ingress with controlled native/provider byte transports.

This is repository acceptance, not deployed Oracle/VEKL or handset qualification.
Only the two network transports and their configured identities are fixtures;
the composed owner authority, action ledger, nonce and Mission observers are real.
"""
import base64
import hashlib
import json
import time
from types import SimpleNamespace

import httpx
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from test_browser_owner_command_e2e import client,_settings,browser_config,setup_plan  # noqa:F401
from tests.test_owner_memory_erasure import _command
from test_browser_producer_api import PID,PRINCIPAL
from van_gateway.auth.provider_transport import ProviderPrincipal
from van_gateway.browser.action_plans import digest
from van_gateway.browser.artifact_admission import NativeArtifactSource,OwnerArtifactAdmissionSigner
from van_gateway.browser.artifact_provider import ArtifactProviderBinding,OwnerArtifactProvider
from van_gateway.browser.stream_grants import generate_signing_key

pytestmark=pytest.mark.asyncio


async def setup_artifact(ac,app,monkeypatch):
    key,plan,page,native,parent=await setup_plan(ac,app)
    sid=plan["session_id"]
    response=await ac.post(f"/v1/browser/interactive-sessions/{sid}/take-control")
    assert response.status_code==200,response.text
    content=b"inert signed-owner artifact fixture"
    sha=hashlib.sha256(content).hexdigest()
    producers=app.state.browser_producers
    await producers.report_download(producer_session_id=PID,principal=PRINCIPAL,event="started",download_id="export-artifact",
        target_id="tab",suggested_name="owner.txt",url_digest="0"*64)
    await producers.report_download(producer_session_id=PID,principal=PRINCIPAL,event="finished",download_id="export-artifact",
        target_id="tab",byte_size=len(content),content_sha256=sha,observed_mime="text/plain")
    signer=OwnerArtifactAdmissionSigner(kid="fixture-only-artifact-key",private_pem=generate_signing_key("fixture-only").private_pem.encode())
    principal=ProviderPrincipal(certificate_sha256="d"*64,provider_identity="oracle-fixture",provider="ORACLE_OWNER_ARCHIVE",owner_namespace="owner",project_namespace="van")
    capability={"contract":OwnerArtifactProvider.CONTRACT,"provider":"ORACLE_OWNER_ARCHIVE","provider_identity":"oracle-fixture",
        "current_admission_introspection":True,"namespace_admissions":[{"owner_namespace":"owner","project_namespace":"van"}],
        "admission_issuer":signer.issuer,"admission_signer_public_sha256":signer.public_sha256,
        "provider_transport_principal_sha256":"d"*64,"atomic_one_use_admission_claim":True,
        "claimed_readback_expiry_field":"observation_expires_at_ms"}
    binding=ArtifactProviderBinding("ORACLE_OWNER_ARCHIVE","https://provider.fixture.test","fixture-ca","fixture-cert","fixture-key",
        "oracle-fixture",digest(capability),"owner","van","d"*64)
    provider=OwnerArtifactProvider(binding)
    service=app.state.browser_artifacts
    service.providers={binding.provider:provider}
    service.source_clients={"authenticated_owner":NativeArtifactSource("https://native.fixture.test","fixture-ca")}
    service.signer=signer
    state=SimpleNamespace(content=content,persisted=None,receipt=None,source_reads=0,content_reads=0,put_count=0,
        before_claim=None,drop=False,configuration=True)
    service.current_configuration=lambda:state.configuration
    async def source_handler(request):
        state.source_reads+=1
        await producers.consume_transfer_grant(producer_session_id=PID,principal=PRINCIPAL,
            transfer_grant=request.headers["Authorization"].removeprefix("Bearer "),operation="download",resource_id="export-artifact")
        return httpx.Response(200,content=state.content)
    async def target_handler(request):
        if request.url.path.endswith("capabilities"):
            return httpx.Response(200,json=capability)
        admission_id=request.headers["X-Van-Admission-ID"]
        signed=request.headers["Authorization"].removeprefix("Bearer ")
        if request.method=="PUT":
            state.put_count+=1
            if state.before_claim:
                await state.before_claim()
            claim=await service.introspect(admission_id=admission_id,signed_admission=signed,principal=principal,claim=True)
            state.persisted=request.content
            state.receipt={"contract":OwnerArtifactProvider.CONTRACT,"provider":binding.provider,"provider_identity":binding.provider_identity,
                "owner_namespace":"owner","project_namespace":"van","content_sha256":sha,"byte_size":len(content),
                "admission_id":claim["admission_id"],"admission_claim_id":claim["admission_claim_id"],"receipt_id":"fixture-persisted-receipt",
                "status":"ARCHIVED","source_authority":"UNTRUSTED_OWNER_FILE_EVIDENCE","executed_content":False,
                "owner_truth_promoted":False,"project_truth_promoted":False}
            if state.drop:
                raise httpx.ReadTimeout("fixture lost write reply")
            return httpx.Response(201,json={"written":True})
        await service.introspect(admission_id=admission_id,signed_admission=signed,principal=principal)
        if request.url.path.endswith("/content"):
            state.content_reads+=1
            return httpx.Response(200,content=state.persisted,headers={"Content-Type":"application/octet-stream"})
        return httpx.Response(200,json=state.receipt)
    monkeypatch.setattr(NativeArtifactSource,"_client",lambda self:httpx.AsyncClient(base_url=self.origin,transport=httpx.MockTransport(source_handler),trust_env=False))
    monkeypatch.setattr(provider,"_client",lambda _:httpx.AsyncClient(base_url=binding.origin,transport=httpx.MockTransport(target_handler),trust_env=False))
    catalog=await ac.get(f"/v1/browser/interactive-sessions/{sid}/file-provider-contracts")
    assert catalog.status_code==200,catalog.text
    assert catalog.json()["contracts"][0]["state"]=="QUALIFIED"
    draft_body={"download_id":"export-artifact","provider":"ORACLE_OWNER_ARCHIVE","owner_namespace":"owner","project_namespace":"van",
        "content_sha256":sha,"byte_size":len(content),"deadline_ms":int(time.time()*1000)+60000,"idempotency_key":"exact-export-draft"}
    response=await ac.post(f"/v1/browser/interactive-sessions/{sid}/file-provider-requests",json=draft_body)
    assert response.status_code==200,response.text
    draft=response.json()
    assert draft["status"]=="DRAFT" and state.put_count==0 and state.source_reads==0
    return key,draft,state,parent,native,draft_body


async def approve(ac,app,key,draft,idem="exact-file-provider"):
    challenge=(await ac.post("/v1/commands",json=_command(app,text=draft["approval_command"],idem=idem+"-challenge"))).json()
    assert challenge["status"]=="approval_required",challenge
    assert challenge["resolved_action_id"]=="browser.file.provider.submit"
    assert challenge["resolved_parameters"]=={k:draft[k] for k in ("session_id","request_id","request_sha256")}
    proof={"challenge_id":challenge["approval_challenge_id"],"signature_b64":base64.b64encode(
        key.sign(challenge["approval_challenge"].encode(),ec.ECDSA(hashes.SHA256()))).decode()}
    return _command(app,text=draft["approval_command"],idem=idem,proof=proof,expires=int(time.time())+20,no_stale=True)


async def test_signed_owner_a4_claim_native_source_and_three_real_byte_observers(client,monkeypatch):
    ac,app,hermes=client
    key,draft,state,parent,native,draft_body=await setup_artifact(ac,app,monkeypatch)
    body=await approve(ac,app,key,draft)
    response=await ac.post("/v1/commands",json=body)
    assert response.status_code==200,response.text
    result=response.json()
    assert result["status"]=="accepted",result
    assert result["local_execution"]["verification_state"]=="VERIFIED_SUCCESS",result
    assert (await app.state.missions.get(result["mission_id"])).state.value=="VERIFIED_SUCCESS",result
    final=(await ac.get(f"/v1/browser/interactive-sessions/{draft['session_id']}/file-provider-requests/{draft['request_id']}")).json()
    assert final["status"]=="VERIFIED_SUCCESS" and len(final["verification_receipts"])==2,final
    assert final["effect_attempted"] is True and final["source_readback"]["observer"]=="VAN_NATIVE_PERSISTED_BYTES_READBACK"
    assert state.persisted==state.content and state.source_reads==state.put_count==1 and state.content_reads==3
    assert (await ac.post("/v1/commands",json=body)).json()==result
    assert state.put_count==1 and state.content_reads==3 and hermes["create_run"]==0 and not native.calls


@pytest.mark.parametrize("failure",["pause","revocation","configuration"])
async def test_signed_owner_claim_current_fence_refuses_without_provider_persistence(client,monkeypatch,failure):
    ac,app,hermes=client
    key,draft,state,parent,native,draft_body=await setup_artifact(ac,app,monkeypatch)
    body=await approve(ac,app,key,draft)
    async def before_claim():
        if failure=="pause":
            response=await ac.post(f"/v1/missions/{parent.mission_id}/pause",json={"request_id":"pause-export-target","expected_generation":0})
            assert response.status_code==200,response.text
        elif failure=="revocation":
            await app.state.store.execute("UPDATE devices SET revoked_at_unix=1 WHERE device_id='dev-erasure'")
        else:
            state.configuration=False
    state.before_claim=before_claim
    result=(await ac.post("/v1/commands",json=body)).json()
    assert result["status"] in {"denied","degraded"},result
    assert state.persisted is None and state.put_count==1 and state.content_reads==0 and hermes["create_run"]==0
    stored=await app.state.store.fetchone("SELECT value FROM runtime_meta WHERE key=?",(app.state.browser_artifacts.PREFIX+draft["request_id"],))
    assert json.loads(stored["value"])["status"]=="UNKNOWN"


async def test_signed_owner_lost_write_reply_exact_replay_never_retries_external_effect(client,monkeypatch):
    ac,app,hermes=client
    key,draft,state,parent,native,draft_body=await setup_artifact(ac,app,monkeypatch)
    body=await approve(ac,app,key,draft)
    state.drop=True
    result=(await ac.post("/v1/commands",json=body)).json()
    assert result["status"]=="degraded",result
    assert state.persisted==state.content and state.put_count==1
    final=(await ac.get(f"/v1/browser/interactive-sessions/{draft['session_id']}/file-provider-requests/{draft['request_id']}")).json()
    assert final["status"]=="UNKNOWN" and final["effect_receipt"] is None
    assert (await ac.post("/v1/commands",json=body)).json()==result
    assert state.put_count==1 and state.content_reads==0 and hermes["create_run"]==0
    mission_before=(await app.state.missions.get(result["mission_id"])).state.value
    observed=await ac.get(f"/v1/browser/interactive-sessions/{draft['session_id']}/file-provider-requests/{draft['request_id']}/observation")
    assert observed.status_code==200,observed.text
    assert observed.json()["canonical_status"]=="UNKNOWN"
    assert observed.json()["effect_observation"]["status"]=="OBSERVED_EXTERNAL_EFFECT"
    assert observed.json()["effect_observation"]["automatic_replacement_authorized"] is False
    assert (await app.state.missions.get(result["mission_id"])).state.value==mission_before
    assert state.put_count==1 and state.content_reads==1 and hermes["create_run"]==0
    refused=await ac.post(f"/v1/browser/interactive-sessions/{draft['session_id']}/file-provider-requests",json={**draft_body,"idempotency_key":"replacement-draft"})
    assert refused.status_code==409 and "target_write_unsettled" in refused.text


async def test_exact_owner_approval_cannot_substitute_request_digest_or_session(client,monkeypatch):
    ac,app,hermes=client
    key,draft,state,parent,native,draft_body=await setup_artifact(ac,app,monkeypatch)
    body=await approve(ac,app,key,draft)
    # A separately valid owner command signature cannot repurpose the original
    # biometric challenge for a different immutable effect.
    text="submit browser file "+json.dumps({"session_id":draft["session_id"],"request_id":draft["request_id"],"request_sha256":"0"*64})
    forged=_command(app,text=text,idem="substituted-file",proof=body["approval_proof"],expires=int(time.time())+20,no_stale=True)
    result=(await ac.post("/v1/commands",json=forged)).json()
    assert result["status"] in {"denied","approval_required"},result
    assert state.put_count==0 and state.source_reads==0 and hermes["create_run"]==0
    wrong_session=await ac.get(f"/v1/browser/interactive-sessions/other-session/file-provider-requests/{draft['request_id']}")
    assert wrong_session.status_code==409
