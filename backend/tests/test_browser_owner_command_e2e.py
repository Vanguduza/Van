"""Signed owner HTTP ingress through broker, narrow native wire and separate readbacks.

The page transport is a controlled fixture. These checks qualify repository wiring,
not a deployed Chromium service, production TLS route, or a physical handset.
"""
import base64
import json
import time
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from tests.test_local_typed_actions import client, _settings  # noqa: F401
from tests.test_owner_memory_erasure import _command, _pair
from test_browser_action_plans import Page, Client
import test_browser_action_plans as native_fixture
from test_browser_producer_api import PRINCIPAL, PID
from van_gateway.browser.stream_grants import generate_signing_key
from van_gateway.mission.control import MissionExecutionControlService


@pytest.fixture(autouse=True)
def browser_config(_settings,tmp_path,monkeypatch):
    now=int(time.time()*1000)
    monkeypatch.setattr(time,"time",lambda:now/1000)
    monkeypatch.setattr(native_fixture,"NOW",now)
    keyfile=tmp_path/"test-browser-stream-key.pem"
    keyfile.write_text(generate_signing_key("test-only-stream").private_pem)
    keyfile.chmod(0o600)
    monkeypatch.setenv("VAN_BROWSER_ENABLED","true")
    monkeypatch.setenv("VAN_BROWSER_STREAM_SIGNING_KEY_FILE",str(keyfile))
    monkeypatch.setenv("VAN_BROWSER_STREAM_SIGNAL_URL","https://media.fixture.test")
    monkeypatch.setenv("VAN_BROWSER_CONTROL_PROXY_BINDINGS",json.dumps({PRINCIPAL:["van-trading-core"]}))
    monkeypatch.setenv("VAN_BROWSER_CONTROL_PROFILE_CLIENTS",json.dumps({"authenticated_owner":{
        "address":"127.0.0.1","port":9443,"server_name":"native.fixture.test",
        "ca_file":"test-transport-injected","cert_file":"test-transport-injected","key_file":"test-transport-injected",
        "caller_common_name":"van-trading-core","proxy_principal_sha256":PRINCIPAL,"stream_principal_sha256":"c"*64}}))
    # Inject only the private page transport; real app composition, identity,
    # broker admission, signatures, immutable authority and wire remain exercised.
    import services.browser_control_agent.client as control_client
    monkeypatch.setattr(control_client,"BrowserControlClient",lambda config:SimpleNamespace(config=config))


async def setup_plan(ac,app,operation="fill_element"):
    key=await _pair(ac,app)
    await app.state.browser.broker.register_profile(profile_alias="authenticated_owner")
    response=await ac.post("/v1/browser/interactive-sessions",json={"profile_alias":"authenticated_owner",
        "viewport":{"width":1080,"height":1920,"device_scale_factor":1.0},"idempotency_key":"open-owned-browser"})
    assert response.status_code==200,response.text
    sid=response.json()["session_id"]
    session=await app.state.interactive_sessions.get(sid)
    token,_=await app.state.browser_stream_grants.mint(session_id=sid,device_id="dev-erasure",profile_alias="authenticated_owner",
        scope=["browser.view","webrtc.signal","browser.owner_input"],max_width=1080,max_height=1920,max_fps=60)
    producers=app.state.browser_producers
    await producers.redeem(stream_grant=token,producer_session_id=PID,principal=PRINCIPAL)
    for event in ["allocated","signaling","connecting"]:
        await producers.observe(producer_session_id=PID,principal=PRINCIPAL,event=event)
    await producers.observe(producer_session_id=PID,principal=PRINCIPAL,event="first_frame",
        frame_sequence=1,viewport_revision=1,width=1080,height=1920,media_epoch=PID,codec="H264",transport="WEBRTC")
    response=await ac.post(f"/v1/browser/interactive-sessions/{sid}/viewport/ack",
        json={"revision":1,"frame_sequence":1,"media_epoch":PID})
    assert response.status_code==200,response.text
    await producers.observe(producer_session_id=PID,principal=PRINCIPAL,event="target",target_id="tab",
        url="https://example.org/?private=not-stored",title="Controlled owner page")
    params={"session_id":sid,"target_domain":"example.org","goal":"Fill the exact reviewed field"}
    prepared=(await ac.post("/v1/commands",json=_command(app,text="prepare browser task "+json.dumps(params),idem="prepare-actual",expires=int(time.time())+20,no_stale=True))).json()
    assert prepared["status"]=="accepted",prepared
    assert prepared["local_execution"]["mission_pending"] is True
    mission=await app.state.missions.get(prepared["mission_id"])
    assert mission.state.value=="RUNNING"
    candidates=(await ac.get(f"/v1/browser/interactive-sessions/{sid}/action-plans")).json()["task_candidates"]
    assert len(candidates)==1 and candidates[0]["action_class"]=="A1"
    step={"step_id":"one","operation":operation,"selector":"#owner-field","text":"after",
        "postcondition":{"kind":"input_value_equals","selector":"#owner-field","value":"after"}}
    if operation=="click_element":
        step.pop("text")
        step["postcondition"]={"kind":"element_text_equals","selector":"#result","text":"after"}
    response=await ac.post(f"/v1/browser/interactive-sessions/{sid}/action-plans",json={"task_id":candidates[0]["task_id"],
        "target_id":"tab","idempotency_key":"exact-plan","deadline_ms":int(time.time()*1000)+50000,"steps":[step]})
    assert response.status_code==200,response.text
    plan=response.json()
    assert plan["status"]=="DRAFT"
    response=await ac.post(f"/v1/browser/interactive-sessions/{sid}/delegate-control",json={"holder":"HERMES_DETERMINISTIC"})
    assert response.status_code==200,response.text
    page=Page()
    f=SimpleNamespace(producers=producers)
    native=Client(f,page)
    app.state.browser_action_plans.profile_clients["authenticated_owner"]=(native,"van-trading-core",PRINCIPAL)
    return key,plan,page,native,mission


async def approve(ac,app,key,plan,idem="actual-plan"):
    challenge=(await ac.post("/v1/commands",json=_command(app,text=plan["approval_command"],idem=idem+"-challenge"))).json()
    assert challenge["status"]=="approval_required",challenge
    assert challenge["resolved_action_id"]=="browser.plan.execute"
    assert challenge["resolved_parameters"]=={k:plan[k] for k in ["session_id","plan_id","plan_sha256"]}
    proof={"challenge_id":challenge["approval_challenge_id"],"signature_b64":base64.b64encode(
        key.sign(challenge["approval_challenge"].encode(),ec.ECDSA(hashes.SHA256()))).decode()}
    return _command(app,text=plan["approval_command"],idem=idem,proof=proof,expires=int(time.time())+20,no_stale=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation",["fill_element","click_element"])
async def test_actual_signed_http_prepare_review_native_a4_effect_and_two_fresh_verifiers(client,operation):
    ac,app,calls=client
    key,plan,page,native,mission=await setup_plan(ac,app,operation)
    assert not native.calls
    body=await approve(ac,app,key,plan)
    result=(await ac.post("/v1/commands",json=body)).json()
    assert result["status"]=="accepted",result
    assert result["local_execution"]["verification_state"]=="VERIFIED_SUCCESS"
    final_mission=await app.state.missions.get(result["mission_id"])
    assert final_mission.state.value=="VERIFIED_SUCCESS",final_mission.model_dump()
    assert [call.operation.value for call in native.calls]==[operation,"observe_effect","observe_effect","observe_effect"]
    assert (await ac.post("/v1/commands",json=body)).json()==result
    assert len(native.calls)==4 and calls["create_run"]==0
    providers=(await ac.get(f"/v1/browser/interactive-sessions/{plan['session_id']}/file-provider-contracts")).json()
    assert providers["contracts"]
    assert all(row["adapter_implemented"] is True and row["executable"] is False for row in providers["contracts"])
    assert result["local_execution"]["parent_reconciliation"]["reconciliation_complete"] is True
    assert (await app.state.missions.get(mission.mission_id)).state.value=="UNVERIFIABLE"


@pytest.mark.asyncio
async def test_owner_pause_after_plan_approval_blocks_native_effect(client):
    ac,app,_=client
    key,plan,page,native,mission=await setup_plan(ac,app)
    body=await approve(ac,app,key,plan)
    response=await ac.post(f"/v1/missions/{mission.mission_id}/pause",json={"request_id":"pause-before-effect","expected_generation":0})
    assert response.status_code==200,response.text
    result=(await ac.post("/v1/commands",json=body)).json()
    assert result["status"] in {"denied","degraded"},result
    assert not native.calls and page.value=="before"


@pytest.mark.asyncio
async def test_lost_native_reply_remains_unknown_and_identical_delivery_cannot_reactuate(client):
    ac,app,_=client
    key,plan,page,native,mission=await setup_plan(ac,app)
    body=await approve(ac,app,key,plan)
    native.drop=True
    result=(await ac.post("/v1/commands",json=body)).json()
    assert result["status"]=="degraded",result
    assert page.value=="after" and len(native.calls)==1
    stored=(await ac.get(f"/v1/browser/interactive-sessions/{plan['session_id']}/action-plans/{plan['plan_id']}")).json()
    assert stored["status"]=="UNKNOWN" and stored["step_states"]["one"]["status"]=="IN_FLIGHT"
    assert (await ac.post("/v1/commands",json=body)).json()==result
    assert len(native.calls)==1
