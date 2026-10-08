"""Real canonical admission and bounded byte readers with controlled transports.

These repository tests do not claim a deployed Oracle/VEKL target or job.
"""
import asyncio
import hashlib
import json
import time
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest

from test_browser_producer_api import fabric,ready,NOW,PID,PRINCIPAL
from van_gateway.action.service import ActionRuntime
from van_gateway.auth.provider_transport import ProviderPrincipal
from van_gateway.browser.action_plans import digest
from van_gateway.browser.artifact_admission import (OwnerArtifactAdmissionService,OwnerArtifactAdmissionSigner,
    NativeArtifactSource,CreateProviderRequest,ArtifactAdmissionError,FILE_PROVIDER_ACTION,load_artifact_provider_config)
from van_gateway.browser.artifact_provider import ArtifactProviderBinding,OwnerArtifactProvider
from van_gateway.browser.stream_grants import generate_signing_key
from van_gateway.command.authority import CommandAuthorityRecord,CommandAuthorityService
from van_gateway.mission.models import MissionOrigin,AuthorityEnvelope
from van_gateway.mission.service import MissionService
from van_gateway.models import ActionClass,OriginChannel,PrincipalType


async def prepared(f,monkeypatch,source_parent_state=None):
    monkeypatch.setattr(time,"time",lambda:NOW/1000)
    await ready(f)
    content=b"inert owner artifact"
    sha=hashlib.sha256(content).hexdigest()
    await f.producers.observe(producer_session_id=PID,principal=PRINCIPAL,event="target",target_id="tab",url="https://example.org",now_ms=NOW)
    await f.producers.report_download(producer_session_id=PID,principal=PRINCIPAL,event="started",download_id="artifact",target_id="tab",suggested_name="owner.txt",url_digest="0"*64,now_ms=NOW)
    await f.producers.report_download(producer_session_id=PID,principal=PRINCIPAL,event="finished",download_id="artifact",target_id="tab",byte_size=len(content),content_sha256=sha,observed_mime="text/plain",now_ms=NOW)
    if source_parent_state:
        parent=await MissionService(f.store).create(owner_principal_id="phone",origin=MissionOrigin.OWNER_UI,origin_channel=OriginChannel.UI,
            title="Prepared browser source",goal="Read a page",authority_envelope=AuthorityEnvelope(max_action_class=ActionClass.A3,source_command_id="prepare-source"),now_ms=NOW)
        await f.store.execute("UPDATE missions SET state=? WHERE mission_id=?",(source_parent_state,parent.mission_id))
        await f.store.execute("UPDATE browser_interactive_sessions SET mission_id=? WHERE session_id=?",(parent.mission_id,f.session.session_id))
    signer=OwnerArtifactAdmissionSigner(kid="test-only-artifact",private_pem=generate_signing_key("fixture-only").private_pem.encode())
    principal=ProviderPrincipal(certificate_sha256="d"*64,provider_identity="oracle-fixture",provider="ORACLE_OWNER_ARCHIVE",owner_namespace="owner",project_namespace="van")
    capability={"contract":OwnerArtifactProvider.CONTRACT,"provider":"ORACLE_OWNER_ARCHIVE","provider_identity":"oracle-fixture",
        "current_admission_introspection":True,"namespace_admissions":[{"owner_namespace":"owner","project_namespace":"van"}],
        "admission_issuer":signer.issuer,"admission_signer_public_sha256":signer.public_sha256,
        "provider_transport_principal_sha256":"d"*64,"atomic_one_use_admission_claim":True,
        "claimed_readback_expiry_field":"observation_expires_at_ms"}
    binding=ArtifactProviderBinding("ORACLE_OWNER_ARCHIVE","https://provider.fixture.test","ca","cert","key","oracle-fixture",digest(capability),"owner","van","d"*64)
    provider=OwnerArtifactProvider(binding)
    source=NativeArtifactSource("https://source.fixture.test","ca")
    authority=CommandAuthorityService(f.store)
    state=SimpleNamespace(content=content,persisted=None,receipt=None,put_count=0,content_reads=0,source_reads=0,
        before_claim=None,drop=False,capability=capability,principal=principal,configuration=True,claim_override=None)
    service=OwnerArtifactAdmissionService(store=f.store,sessions=f.sessions,producers=f.producers,command_authority=authority,
        providers={binding.provider:provider},source_clients={"public_research":source},signer=signer,current_configuration=lambda:state.configuration)
    async def source_handler(request):
        state.source_reads+=1
        grant=request.headers["Authorization"].removeprefix("Bearer ")
        await f.producers.consume_transfer_grant(producer_session_id=PID,principal=PRINCIPAL,transfer_grant=grant,operation="download",resource_id="artifact",now_ms=NOW)
        return httpx.Response(200,content=state.content)
    async def target_handler(request):
        if request.url.path.endswith("capabilities"):
            return httpx.Response(200,json=state.capability)
        if request.method=="PUT":
            state.put_count+=1
            if state.before_claim:
                await state.before_claim()
            claim=state.claim_override or await service.introspect(admission_id=request.headers["X-Van-Admission-ID"],
                signed_admission=request.headers["Authorization"].removeprefix("Bearer "),principal=state.principal,claim=True)
            state.persisted=request.content
            state.receipt={"contract":OwnerArtifactProvider.CONTRACT,"provider":binding.provider,"provider_identity":binding.provider_identity,
                "owner_namespace":"owner","project_namespace":"van","content_sha256":sha,"byte_size":len(content),
                "admission_id":claim["admission_id"],"admission_claim_id":claim["admission_claim_id"],"receipt_id":"target-fixture-receipt",
                "status":"ARCHIVED","source_authority":"UNTRUSTED_OWNER_FILE_EVIDENCE","executed_content":False,
                "owner_truth_promoted":False,"project_truth_promoted":False}
            if state.drop:
                raise httpx.ReadTimeout("lost provider reply")
            return httpx.Response(201,json={"written":True})
        await service.introspect(admission_id=request.headers["X-Van-Admission-ID"],
            signed_admission=request.headers["Authorization"].removeprefix("Bearer "),principal=state.principal)
        if request.url.path.endswith("/content"):
            state.content_reads+=1
            return httpx.Response(200,content=state.persisted,headers={"Content-Type":"application/octet-stream"})
        return httpx.Response(200,json=state.receipt)
    monkeypatch.setattr(NativeArtifactSource,"_client",lambda self:httpx.AsyncClient(base_url=self.origin,transport=httpx.MockTransport(source_handler),trust_env=False))
    monkeypatch.setattr(provider,"_client",lambda _:httpx.AsyncClient(base_url=binding.origin,transport=httpx.MockTransport(target_handler),trust_env=False))
    body=CreateProviderRequest(download_id="artifact",provider=binding.provider,owner_namespace="owner",project_namespace="van",
        content_sha256=sha,byte_size=len(content),deadline_ms=NOW+60000,idempotency_key="exact-owner-artifact")
    draft=await service.create(session_id=f.session.session_id,owner_device_id="phone",body=body)
    parameters={name:draft[name] for name in ("session_id","request_id","request_sha256")}
    await authority.seal(CommandAuthorityRecord(command_id="approved-file",device_id="phone",principal_type=PrincipalType.OWNER_DEVICE,
        requested_by="phone",origin_channel=OriginChannel.UI,signed_action_class=ActionClass.A1,effective_action_class=ActionClass.A4,
        typed_action_id=FILE_PROVIDER_ACTION.action_id,typed_parameter_constraints=parameters,snapshot_id="file-snapshot",context_digest="digest",
        issued_at_unix=NOW//1000,expires_at_unix=NOW//1000+30,no_stale_replay=True,owner_approved=True,sealed_at_unix_ms=NOW))
    await f.store.execute("INSERT INTO context_snapshots(snapshot_id,command_id,kernel_revision,fact_ids_json,graph_evidence_refs_json,live_state_refs_json,policy_refs_json,compiled_at_ms,digest) VALUES('file-snapshot','approved-file',1,'[]','[]','[]','[]',?,'digest')",(NOW,))
    runtime=ActionRuntime(f.store)
    await runtime.register(FILE_PROVIDER_ACTION)
    execution=await runtime.begin(execution_id="file-execution",command_id="approved-file",turn_id=None,action_id=FILE_PROVIDER_ACTION.action_id,
        principal_type=PrincipalType.OWNER_DEVICE,requested_by="phone",idempotency_key="file-execute",parameters=parameters,snapshot_id="file-snapshot",owner_approved=True)
    await f.store.execute("UPDATE action_executions SET status='EXECUTING' WHERE execution_id='file-execution'")
    execution=await runtime.get_execution("file-execution")
    mission=await MissionService(f.store).create(owner_principal_id="phone",origin=MissionOrigin.OWNER_UI,origin_channel=OriginChannel.UI,
        title="Archive reviewed artifact",goal="Persist exact inert bytes on the admitted owner target",
        authority_envelope=AuthorityEnvelope(max_action_class=ActionClass.A4,source_command_id="approved-file"),now_ms=NOW)
    await f.store.execute("UPDATE missions SET state='RUNNING' WHERE mission_id=?",(mission.mission_id,))
    return service,draft,parameters,execution,state,body,mission


async def test_real_source_bytes_one_use_target_claim_and_three_separate_readbacks(fabric,monkeypatch):
    service,draft,parameters,execution,state,body,mission=await prepared(fabric,monkeypatch)
    result=await service.submit(execution,parameters)
    assert result["success"] is True and result["effect_observed"] is True
    assert state.persisted==state.content and state.put_count==state.source_reads==state.content_reads==1
    assert (await service.get(session_id=draft["session_id"],owner_device_id="phone",request_id=draft["request_id"]))["status"]=="RUNNING"
    assert (await service.verify(execution,parameters))["success"] is True
    await fabric.store.execute("UPDATE action_executions SET status='VERIFIED_SUCCESS' WHERE execution_id='file-execution'")
    assert (await service.verify(execution,parameters))["success"] is True
    assert state.content_reads==3
    admission=json.loads((await fabric.store.fetchone("SELECT value FROM runtime_meta WHERE key=?",(service.ADMISSION+result["admission_id"],)))["value"])
    with pytest.raises(ArtifactAdmissionError,match="execution_not_live|already_claimed"):
        await service.introspect(admission_id=result["admission_id"],signed_admission=service.signer.sign(admission["claims"]),principal=state.principal,claim=True)
    # Only canonical Action and Mission completion qualify the owner projection.
    await fabric.store.execute("UPDATE missions SET state='VERIFIED_SUCCESS' WHERE mission_id=?",(mission.mission_id,))
    assert (await service.get(session_id=draft["session_id"],owner_device_id="phone",request_id=draft["request_id"]))["status"]=="VERIFIED_SUCCESS"
    assert state.put_count==1


@pytest.mark.parametrize("failure",["revocation","configuration","principal","pause"])
async def test_target_claim_rechecks_current_authority_without_persisting(fabric,monkeypatch,failure):
    service,draft,parameters,execution,state,body,mission=await prepared(fabric,monkeypatch)
    async def before_claim():
        if failure=="revocation":
            await fabric.store.execute("UPDATE devices SET revoked_at_unix=1 WHERE device_id='phone'")
        elif failure=="configuration":
            state.configuration=False
        elif failure=="principal":
            state.principal=replace(state.principal,project_namespace="other-project")
        else:
            from van_gateway.mission.control import MissionExecutionControlService
            await MissionExecutionControlService(fabric.store).request(mission_id=mission.mission_id,request_id="pause-before-provider-claim",
                operation="PAUSE",expected_generation=0,requested_by="device:phone",now_ms=NOW)
    state.before_claim=before_claim
    result=await service.submit(execution,parameters)
    assert result["success"] is False and result["status"]=="UNKNOWN"
    assert state.persisted is None and state.put_count==1
    row=await fabric.store.fetchone("SELECT value FROM runtime_meta WHERE key LIKE ?",(service.ADMISSION+"%",))
    assert json.loads(row["value"])["claimed_at_ms"] is None


async def test_lost_write_reply_never_retries_and_does_not_qualify_from_existing_bytes(fabric,monkeypatch):
    service,draft,parameters,execution,state,body,mission=await prepared(fabric,monkeypatch)
    state.drop=True
    first=await service.submit(execution,parameters)
    assert first["status"]=="UNKNOWN" and state.persisted==state.content and state.put_count==1
    second=await service.submit(execution,parameters)
    assert second["status"]=="UNKNOWN" and state.put_count==1
    assert (await service.verify(execution,parameters))["success"] is False


async def test_source_tamper_refused_before_provider_write(fabric,monkeypatch):
    service,draft,parameters,execution,state,body,mission=await prepared(fabric,monkeypatch)
    state.content=b"tampered source"
    result=await service.submit(execution,parameters)
    assert result["success"] is False and result["status"]=="REFUSED" and result["effect_attempted"] is False
    assert state.put_count==0 and state.persisted is None


async def test_draft_exact_source_namespace_and_recovery_supply_no_action_authority(fabric,monkeypatch):
    service,draft,parameters,execution,state,body,mission=await prepared(fabric,monkeypatch)
    assert await service.create(session_id=draft["session_id"],owner_device_id="phone",body=body)==draft
    assert (await service.list(session_id=draft["session_id"],owner_device_id="phone"))["requests"][0]["idempotency_key"]==body.idempotency_key
    with pytest.raises(ArtifactAdmissionError,match="namespace_not_admitted"):
        await service.create(session_id=draft["session_id"],owner_device_id="phone",body=body.model_copy(update={"project_namespace":"other"}))
    with pytest.raises(ArtifactAdmissionError,match="unknown"):
        await service.get(session_id="other-session",owner_device_id="phone",request_id=draft["request_id"])
    with pytest.raises(ValueError,match="typed_parameter_mismatch"):
        await service.submit(execution,{**parameters,"request_sha256":"0"*64})
    await service.cancel(session_id=draft["session_id"],owner_device_id="phone",request_id=draft["request_id"])
    assert (await service.submit(execution,parameters))["success"] is False and state.put_count==0


def test_operator_config_default_and_strict_schema_withdrawal(tmp_path):
    assert load_artifact_provider_config("")["signer"] is None
    path=tmp_path/"providers.json"
    path.write_text(json.dumps({"schema_version":1,"providers":[],"source_clients":{},"signer":None}))
    value=load_artifact_provider_config(str(path))
    assert value["configuration_sha256"]==hashlib.sha256(path.read_bytes()).hexdigest()
    path.write_text('{"schema_version":1,"schema_version":1,"providers":[],"source_clients":{},"signer":null}')
    with pytest.raises(ArtifactAdmissionError):load_artifact_provider_config(str(path))


async def test_claim_before_write_expiry_allows_bounded_terminal_readback_without_new_write(fabric,monkeypatch):
    service,draft,parameters,execution,state,body,mission=await prepared(fabric,monkeypatch)
    assert (await service.submit(execution,parameters))["success"] is True
    assert (await service.verify(execution,parameters))["success"] is True
    await fabric.store.execute("UPDATE action_executions SET status='VERIFIED_SUCCESS' WHERE execution_id='file-execution'")
    monkeypatch.setattr(time,"time",lambda:(NOW+31000)/1000)
    assert (await service.verify(execution,parameters))["success"] is True
    await fabric.store.execute("UPDATE missions SET state='VERIFIED_SUCCESS' WHERE mission_id=?",(mission.mission_id,))
    assert (await service.verify(execution,parameters))["success"] is True
    assert state.content_reads==4 and state.put_count==1
    row=await fabric.store.fetchone("SELECT value FROM runtime_meta WHERE key LIKE ?",(service.ADMISSION+"%",))
    admission=json.loads(row["value"])
    with pytest.raises(ArtifactAdmissionError,match="signature_or_expiry"):
        await service.introspect(admission_id=draft.get("admission_id") or admission["claims"]["jti"],
            signed_admission=service.signer.sign(admission["claims"]),principal=state.principal,claim=True)
    monkeypatch.setattr(time,"time",lambda:(NOW+300001)/1000)
    with pytest.raises(ArtifactAdmissionError,match="signature_or_expiry"):
        await service.verify(execution,parameters)
    assert state.put_count==1 and state.content_reads==4


async def test_unclaimed_token_cannot_extend_write_past_thirty_seconds(fabric,monkeypatch):
    service,draft,parameters,execution,state,body,mission=await prepared(fabric,monkeypatch)
    async def before_claim():
        monkeypatch.setattr(time,"time",lambda:(NOW+31000)/1000)
    state.before_claim=before_claim
    assert (await service.submit(execution,parameters))["status"]=="UNKNOWN"
    assert state.put_count==1 and state.persisted is None


async def test_unknown_outside_bounded_history_fences_new_content_identical_target(fabric,monkeypatch):
    service,draft,parameters,execution,state,body,mission=await prepared(fabric,monkeypatch)
    state.drop=True
    assert (await service.submit(execution,parameters))["status"]=="UNKNOWN"
    # The old unresolved request remains authoritative even after it falls off
    # the owner's latest100 history rows. Unrelated completed history is inert.
    for i in range(101):
        historic={**draft,"request_id":"historical"+str(i),"status":"CANCELLED","created_at_ms":NOW+i}
        await fabric.store.execute("INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?)",(service.PREFIX+historic["request_id"],json.dumps(historic),NOW+i+1))
    assert draft["request_id"] not in [r["request_id"] for r in (await service.list(session_id=draft["session_id"],owner_device_id="phone"))["requests"]]
    with pytest.raises(ArtifactAdmissionError,match="target_write_unsettled"):
        await service.create(session_id=draft["session_id"],owner_device_id="phone",body=body.model_copy(update={"idempotency_key":"replacement-owner-artifact"}))
    assert state.put_count==1


async def test_cancel_after_dispatch_cannot_erase_uncertainty_or_allow_replacement(fabric,monkeypatch):
    service,draft,parameters,execution,state,body,mission=await prepared(fabric,monkeypatch)
    async def before_claim():
        cancelled=await service.cancel(session_id=draft["session_id"],owner_device_id="phone",request_id=draft["request_id"])
        assert cancelled["status"]=="UNKNOWN" and cancelled["effect_attempted"] is True
    state.before_claim=before_claim
    assert (await service.submit(execution,parameters))["status"]=="UNKNOWN"
    assert state.put_count==1 and state.persisted is None
    with pytest.raises(ArtifactAdmissionError,match="target_write_unsettled"):
        await service.create(session_id=draft["session_id"],owner_device_id="phone",body=body.model_copy(update={"idempotency_key":"replacement-owner-artifact"}))


async def test_source_parent_cancelled_after_draft_blocks_target_claim(fabric,monkeypatch):
    service,draft,parameters,execution,state,body,mission=await prepared(fabric,monkeypatch,source_parent_state="RUNNING")
    async def before_claim():
        await fabric.store.execute("UPDATE missions SET state='CANCELLED' WHERE mission_id=?",(draft["source_mission_id"],))
    state.before_claim=before_claim
    assert (await service.submit(execution,parameters))["status"]=="UNKNOWN"
    assert state.persisted is None and state.put_count==1


async def test_new_exact_artifact_draft_after_parent_completion_is_independent_owner_authority(fabric,monkeypatch):
    service,draft,parameters,execution,state,body,mission=await prepared(fabric,monkeypatch,source_parent_state="UNVERIFIABLE")
    assert draft["source_mission_state_at_creation"]=="UNVERIFIABLE"
    assert (await service.submit(execution,parameters))["success"] is True
    assert state.put_count==1


async def test_concurrent_provider_claims_only_one_nonce_can_admit_target_persistence(fabric,monkeypatch):
    service,draft,parameters,execution,state,body,mission=await prepared(fabric,monkeypatch)
    async def before_claim():
        row=await fabric.store.fetchone("SELECT value FROM runtime_meta WHERE key LIKE ?",(service.ADMISSION+"%",))
        admission=json.loads(row["value"])
        async def claim():
            return await service.introspect(admission_id=admission["claims"]["jti"],
                signed_admission=service.signer.sign(admission["claims"]),principal=state.principal,claim=True)
        results=await asyncio.gather(claim(),claim(),return_exceptions=True)
        assert sum(isinstance(value,dict) for value in results)==1
        assert sum(isinstance(value,ArtifactAdmissionError) for value in results)==1
        state.claim_override=next(value for value in results if isinstance(value,dict))
    state.before_claim=before_claim
    assert (await service.submit(execution,parameters))["success"] is True
    assert state.persisted==state.content and state.put_count==1


async def test_configuration_withdrawal_while_authenticated_claim_waits_on_writer_is_rechecked(fabric,monkeypatch):
    service,draft,parameters,execution,state,body,mission=await prepared(fabric,monkeypatch)
    async def before_claim():
        row=await fabric.store.fetchone("SELECT value FROM runtime_meta WHERE key LIKE ?",(service.ADMISSION+"%",))
        admission=json.loads(row["value"])
        passed_capability=asyncio.Event()
        original=service._qualified
        async def qualified(provider):
            result=await original(provider)
            passed_capability.set()
            return result
        monkeypatch.setattr(service,"_qualified",qualified)
        async with fabric.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            pending=asyncio.create_task(service.introspect(admission_id=admission["claims"]["jti"],
                signed_admission=service.signer.sign(admission["claims"]),principal=state.principal,claim=True))
            await asyncio.wait_for(passed_capability.wait(),1)
            state.configuration=False
            await db.commit()
        with pytest.raises(ArtifactAdmissionError,match="configuration_changed"):
            await pending
    state.before_claim=before_claim
    assert (await service.submit(execution,parameters))["status"]=="UNKNOWN"
    assert state.persisted is None
    row=await fabric.store.fetchone("SELECT value FROM runtime_meta WHERE key LIKE ?",(service.ADMISSION+"%",))
    assert json.loads(row["value"])["claimed_at_ms"] is None


async def test_canonical_terminal_failure_is_unverifiable_read_projection_and_keeps_fence(fabric,monkeypatch):
    service,draft,parameters,execution,state,body,mission=await prepared(fabric,monkeypatch)
    assert (await service.submit(execution,parameters))["success"] is True
    await fabric.store.execute("UPDATE action_executions SET status='UNVERIFIABLE' WHERE execution_id='file-execution'")
    await fabric.store.execute("UPDATE missions SET state='UNVERIFIABLE' WHERE mission_id=?",(mission.mission_id,))
    projection=await service.get(session_id=draft["session_id"],owner_device_id="phone",request_id=draft["request_id"])
    assert projection["status"]=="UNVERIFIABLE" and projection["effect_attempted"] is True
    with pytest.raises(ArtifactAdmissionError,match="target_write_unsettled"):
        await service.create(session_id=draft["session_id"],owner_device_id="phone",body=body.model_copy(update={"idempotency_key":"replacement-artifact"}))


def test_operator_dedicated_signer_cannot_reuse_stream_key_or_loose_private_permissions(tmp_path):
    key=tmp_path/"test-only-dedicated.pem"
    key.write_text(generate_signing_key("fixture-only").private_pem)
    key.chmod(0o600)
    signer=OwnerArtifactAdmissionSigner.from_config(kid="test-only",private_key_file=str(key))
    config=tmp_path/"providers.json"
    config.write_text(json.dumps({"schema_version":1,"providers":[],"source_clients":{},"signer":{
        "kid":"test-only","private_key_file":str(key),"issuer":"van-trading-core"}}))
    assert load_artifact_provider_config(str(config))["signer"].public_sha256==signer.public_sha256
    with pytest.raises(ArtifactAdmissionError,match="separate_from_stream"):
        load_artifact_provider_config(str(config),disallowed_signer_public_sha256=[signer.public_sha256])
    key.chmod(0o644)
    with pytest.raises(ArtifactAdmissionError,match="permissions"):
        load_artifact_provider_config(str(config))


async def test_durable_immutable_request_corruption_cannot_repurpose_valid_owner_approval(fabric,monkeypatch):
    service,draft,parameters,execution,state,body,mission=await prepared(fabric,monkeypatch)
    corrupt={**draft,"project_namespace":"another-project"}
    await fabric.store.execute("UPDATE runtime_meta SET value=? WHERE key=?",(json.dumps(corrupt),service.PREFIX+draft["request_id"]))
    with pytest.raises(ArtifactAdmissionError,match="immutable_request_integrity"):
        await service.submit(execution,parameters)
    assert state.put_count==state.source_reads==0


async def test_source_failure_releases_replacement_only_without_any_target_dispatch(fabric,monkeypatch):
    service,draft,parameters,execution,state,body,mission=await prepared(fabric,monkeypatch)
    original=state.content
    state.content=b"different source"
    result=await service.submit(execution,parameters)
    assert result["status"]=="REFUSED" and result["effect_attempted"] is False and result["failure_reason"]
    state.content=original
    fresh=await service.create(session_id=draft["session_id"],owner_device_id="phone",body=body.model_copy(update={"idempotency_key":"replacement-after-refusal"}))
    assert fresh["status"]=="DRAFT" and fresh["request_id"]!=draft["request_id"] and state.put_count==0


async def test_explicit_uncertain_effect_observation_neither_rewrites_terminal_command_nor_releases_fence(fabric,monkeypatch):
    service,draft,parameters,execution,state,body,mission=await prepared(fabric,monkeypatch)
    state.drop=True
    assert (await service.submit(execution,parameters))["status"]=="UNKNOWN"
    await fabric.store.execute("UPDATE action_executions SET status='UNVERIFIABLE' WHERE execution_id='file-execution'")
    await fabric.store.execute("UPDATE missions SET state='UNVERIFIABLE' WHERE mission_id=?",(mission.mission_id,))
    monkeypatch.setattr(time,"time",lambda:(NOW+31000)/1000)
    result=await service.observe(session_id=draft["session_id"],owner_device_id="phone",request_id=draft["request_id"])
    observed=result["effect_observation"]
    assert result["canonical_status"]=="UNKNOWN" and observed["status"]=="OBSERVED_EXTERNAL_EFFECT"
    assert observed["receipt"]["independent_content_readback"]["content_sha256"]==draft["content_sha256"]
    assert observed["automatic_replacement_authorized"] is False and observed["governed_reconciliation_required"] is True
    assert (await fabric.store.fetchone("SELECT status FROM action_executions WHERE execution_id='file-execution'"))["status"]=="UNVERIFIABLE"
    assert (await fabric.store.fetchone("SELECT state FROM missions WHERE mission_id=?",(mission.mission_id,)))["state"]=="UNVERIFIABLE"
    with pytest.raises(ArtifactAdmissionError,match="target_write_unsettled"):
        await service.create(session_id=draft["session_id"],owner_device_id="phone",body=body.model_copy(update={"deadline_ms":NOW+70000,"idempotency_key":"replacement-uncertain"}))
    assert state.put_count==state.source_reads==state.content_reads==1
    monkeypatch.setattr(time,"time",lambda:(NOW+300001)/1000)
    expired=await service.observe(session_id=draft["session_id"],owner_device_id="phone",request_id=draft["request_id"])
    assert expired["effect_observation"]["status"]=="STILL_UNKNOWN" and "expiry" in expired["effect_observation"]["reason"]
    assert state.put_count==state.content_reads==1


async def test_unclaimed_uncertain_dispatch_has_no_new_observation_token_or_absence_certificate(fabric,monkeypatch):
    service,draft,parameters,execution,state,body,mission=await prepared(fabric,monkeypatch)
    async def before_claim():
        state.configuration=False
    state.before_claim=before_claim
    assert (await service.submit(execution,parameters))["status"]=="UNKNOWN"
    state.configuration=True
    result=await service.observe(session_id=draft["session_id"],owner_device_id="phone",request_id=draft["request_id"])
    assert result["effect_observation"]["status"]=="STILL_UNKNOWN"
    assert result["effect_observation"]["reason"]=="artifact_claimed_observation_scope_required"
    assert state.put_count==1 and state.content_reads==0 and state.persisted is None


async def test_owner_revocation_and_foreign_scope_refuse_external_observation(fabric,monkeypatch):
    service,draft,parameters,execution,state,body,mission=await prepared(fabric,monkeypatch)
    state.drop=True
    assert (await service.submit(execution,parameters))["status"]=="UNKNOWN"
    with pytest.raises(ArtifactAdmissionError,match="request_unknown"):
        await service.observe(session_id="other-session",owner_device_id="phone",request_id=draft["request_id"])
    await fabric.store.execute("UPDATE devices SET revoked_at_unix=1 WHERE device_id='phone'")
    result=await service.observe(session_id=draft["session_id"],owner_device_id="phone",request_id=draft["request_id"])
    assert result["effect_observation"]["status"]=="STILL_UNKNOWN" and "revoked" in result["effect_observation"]["reason"]
    assert state.content_reads==0


async def test_hardware_binding_withdrawal_without_device_row_revocation_blocks_readonly_scope(fabric,monkeypatch):
    service,draft,parameters,execution,state,body,mission=await prepared(fabric,monkeypatch)
    state.drop=True
    assert (await service.submit(execution,parameters))["status"]=="UNKNOWN"
    await fabric.store.execute("INSERT INTO owner_device_bindings(binding_id,owner_principal_id,device_id,device_key_fingerprint,public_key_pem,key_security_level,app_package_name,app_signing_cert_sha256,status,bound_at_ms,revoked_at_ms) VALUES('withdrawn-test-binding','owner','phone','fixture-only-key','fixture-only-public','STRONGBOX','com.van.fixture',?,'REVOKED',?,?)",("a"*64,NOW,NOW+1))
    result=await service.observe(session_id=draft["session_id"],owner_device_id="phone",request_id=draft["request_id"])
    assert result["effect_observation"]["status"]=="STILL_UNKNOWN" and result["effect_observation"]["reason"]=="artifact_owner_device_binding_revoked"
    assert state.content_reads==0 and state.put_count==1


async def test_catalog_qualification_requires_exact_current_profile_native_source_and_capability(fabric,monkeypatch):
    service,draft,parameters,execution,state,body,mission=await prepared(fabric,monkeypatch)
    assert (await service.catalog(session_id=draft["session_id"],owner_device_id="phone"))["contracts"][0]["executable"] is True
    source=service.source_clients.pop("public_research")
    service.source_clients["authenticated_owner"]=source
    assert (await service.catalog(session_id=draft["session_id"],owner_device_id="phone"))["contracts"][0]["executable"] is False
    service.source_clients["public_research"]=source
    await fabric.store.execute("UPDATE browser_interactive_sessions SET acked_viewport_revision=NULL WHERE session_id=?",(draft["session_id"],))
    assert (await service.catalog(session_id=draft["session_id"],owner_device_id="phone"))["contracts"][0]["executable"] is False
    assert (await service.is_ready())[0] is True  # Generic provider, not a session proof.
    state.capability={**state.capability,"atomic_one_use_admission_claim":False}
    assert (await service.is_ready())[0] is False
