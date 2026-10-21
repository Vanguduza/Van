"""A cancellation between authorization and admission must remain cancelled."""
import json

import pytest

from tests.test_local_typed_actions import client, _settings
from tests.test_owner_memory_erasure import _pair, _command
from van_gateway.mission.models import MissionState
from van_gateway.models import PrincipalType
from test_device_proof_enforcement import _bind, _proof_headers
from test_owner_device_binding import PACKAGE, SIGNING_CERT


@pytest.fixture(autouse=True)
def configured_owner_proof(_settings,monkeypatch):
    monkeypatch.setenv("VAN_OWNER_DEVICE_PACKAGE",PACKAGE)
    monkeypatch.setenv("VAN_OWNER_DEVICE_SIGNING_CERT_SHA256",SIGNING_CERT)
    monkeypatch.setenv("VAN_REQUIRE_DEVICE_BINDING","false")
    monkeypatch.setenv("VAN_SCHEDULER_ENABLED","false")


async def test_cancel_after_action_authorization_is_a_refusal_with_no_local_effect(client,monkeypatch):
    ac,app,hermes=client
    await _pair(ac,app)
    actions=app.state.owner_runtime.actions
    original=actions.mark_executing
    cancelled=[]
    async def cancel_before_admission(execution_id):
        execution=await actions.get_execution(execution_id)
        row=await app.state.store.fetchone(
            "SELECT mission_id FROM missions WHERE json_extract(authority_envelope_json,'$.source_command_id')=?",
            (execution.command_id,))
        mission=await app.state.missions.get(row["mission_id"])
        await app.state.missions.transition(mission.mission_id,target=MissionState.CANCELLED,
            expected=mission.state,actor=PrincipalType.OWNER_DEVICE,summary="Owner cancellation before dispatch")
        cancelled.append(mission.mission_id)
        return await original(execution_id)
    monkeypatch.setattr(actions,"mark_executing",cancel_before_admission)
    response=await ac.post("/v1/commands",json=_command(app,text="remind me to call Thandi in 2 hours",idem="cancel-before-admission"))
    assert response.status_code==200,response.text
    result=response.json()
    assert result["status"]=="denied" and cancelled==[result["mission_id"]]
    assert (await app.state.missions.get(result["mission_id"])).state is MissionState.CANCELLED
    assert await app.state.store.fetchone("SELECT 1 FROM reminders") is None
    assert hermes["create_run"]==0


async def test_pause_admission_is_temporary_and_resume_never_replays_denied_owner_effect(client,monkeypatch):
    ac,app,hermes=client
    await _pair(ac,app)
    key=await _bind(app,"dev-erasure")
    # Trusted synthetic binding isolates actual middleware signatures here;
    # public attestation-chain verification has separate enrollment regressions.
    await app.state.store.execute("UPDATE owner_device_bindings SET attestation_chain_verified=1 WHERE device_id='dev-erasure'")
    async def signed_post(path,body):
        raw=json.dumps(body,separators=(",",":")).encode()
        headers={"Content-Type":"application/json",**_proof_headers(key,method="POST",path=path,
                    device_id="dev-erasure",body=raw)}
        return await ac.post(path,content=raw,headers=headers)
    actions=app.state.owner_runtime.actions
    original=actions.mark_executing
    paused=[]
    async def pause_before_admission(execution_id):
        execution=await actions.get_execution(execution_id)
        row=await app.state.store.fetchone(
            "SELECT mission_id FROM missions WHERE json_extract(authority_envelope_json,'$.source_command_id')=?",
            (execution.command_id,))
        response=await signed_post(f"/v1/missions/{row['mission_id']}/pause",
            {"request_id":"pause-before-native-effect","expected_generation":0,"reason":"Pause the next effect"})
        assert response.status_code==200,response.text
        paused.append(row["mission_id"])
        return await original(execution_id)
    monkeypatch.setattr(actions,"mark_executing",pause_before_admission)
    command=_command(app,text="remind me to call Thandi in 2 hours",idem="paused-before-admission")
    response=await signed_post("/v1/commands",command)
    assert response.status_code==200,response.text
    result=response.json()
    assert result["status"]=="denied" and paused==[result["mission_id"]]
    assert result["local_execution"]["paused_before_effect"] is True
    assert result["local_execution"]["fresh_owner_command_required"] is True
    assert result["local_execution"]["effects_replay_permitted"] is False
    mission=await app.state.missions.get(result["mission_id"])
    assert not mission.is_terminal
    base=f"/v1/missions/{mission.mission_id}"
    control=(await ac.get(base+"/control")).json()
    assert control["desired_execution"]=="PAUSED" and not control["dispatch_allowed"]
    assert await app.state.store.fetchone("SELECT 1 FROM reminders") is None
    resume={"request_id":"resume-after-paused-admission","expected_generation":1}
    assert (await ac.post(base+"/resume",json=resume)).status_code==401
    resumed=await signed_post(base+"/resume",resume)
    assert resumed.status_code==200 and resumed.json()["desired_execution"]=="RUNNING"
    assert (await signed_post("/v1/commands",command)).json()==result
    assert await app.state.store.fetchone("SELECT 1 FROM reminders") is None
    monkeypatch.setattr(actions,"mark_executing",original)
    fresh=_command(app,text="remind me to call Thandi in 2 hours",idem="fresh-owner-effect-after-resume")
    accepted=await signed_post("/v1/commands",fresh)
    assert accepted.status_code==200 and accepted.json()["status"]=="accepted",accepted.text
    assert len(await app.state.store.fetchall("SELECT * FROM reminders"))==1
    assert hermes["create_run"]==0
