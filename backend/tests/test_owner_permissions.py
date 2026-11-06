"""Exact native owner consent, actual signed admission and current effect fences."""
import base64
import json
import time

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from tests.test_local_typed_actions import client, _settings  # noqa: F401
from tests.test_owner_memory_erasure import _pair, _command
from van_gateway.action.models import ExecutionStatus
from van_gateway.action.service import ActionPolicyError
from van_gateway.capability import owner_permissions as permissions
from van_gateway.command.resolver import ResolutionMode, TypedCommandResolver
from van_gateway.models import PrincipalType


def _parameters(**changes):
    result = {"permission":"email.send", "action_id":"google.gmail.draft",
        "parameters":{"thread_id":"thread-exact","body":"exact owner draft"},
        "expires_at_ms":int(time.time()*1000)+120000,"max_uses":1}
    result.update(changes)
    return result


def _text(parameters):
    return permissions.COMMAND_PREFIX + json.dumps(parameters, separators=(",",":"))


async def _approved(ac, app, key, parameters, idem):
    text = _text(parameters)
    challenge = (await ac.post("/v1/commands", json=_command(app,text=text,idem=idem+"-challenge"))).json()
    assert challenge["status"] == "approval_required", challenge
    assert challenge["resolved_action_id"] == permissions.ACTION_ID
    assert challenge["resolved_parameters"] == parameters
    proof = {"challenge_id":challenge["approval_challenge_id"],
        "signature_b64":base64.b64encode(key.sign(challenge["approval_challenge"].encode(),ec.ECDSA(hashes.SHA256()))).decode()}
    return _command(app,text=text,idem=idem,proof=proof,expires=int(time.time())+20,no_stale=True)


@pytest.mark.parametrize("change", [{"permission":"email.*"},{"max_uses":True},{"max_uses":0},
    {"max_uses":1001},{"expires_at_ms":False},{"parameters":{"thread_id":"*","body":"x"}},
    {"parameters":{"password":"private"}},{"action_id":"google.gmail.send-unregistered"}])
def test_unbounded_or_undeclared_permissions_cannot_resolve(change):
    assert TypedCommandResolver().resolve(_text(_parameters(**change))).mode is not ResolutionMode.EXACT_ACTION


@pytest.mark.asyncio
async def test_native_owner_grant_has_independent_mission_readback_and_exact_replay(client):
    ac, app, calls = client
    key = await _pair(ac,app)
    p = _parameters()
    body = await _approved(ac,app,key,p,"permission-good")
    result = (await ac.post("/v1/commands",json=body)).json()
    assert result["status"] == "accepted", result
    assert result["local_execution"]["verification_state"] == "VERIFIED_SUCCESS"
    assert (await app.state.missions.get(result["mission_id"])).state.value == "VERIFIED_SUCCESS"
    assert calls["create_run"] == 0
    assert (await ac.post("/v1/commands",json=body)).json() == result
    witness = await app.state.store.fetchone("SELECT value FROM runtime_meta WHERE key=?",(permissions.WITNESS_PREFIX+body["command_id"],))
    grant_id = json.loads(witness["value"])["grant_id"]
    detail = (await ac.get("/v1/permissions/grants/"+grant_id)).json()
    assert detail["exact_scope"] == p and detail["native_authority_required"] is True
    assert detail["use_count"] == 0
    assert app.state.capability_registry.get(permissions.ACTION_ID).requires_owner_presence
    catalog = (await ac.get("/v1/permissions/contracts")).json()
    assert catalog["native_authority_required"] and catalog["max_uses"] == 1000
    assert "computer.remote" in catalog["unavailable_permissions"]


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [{"parameters":{"thread_id":"thread-exact","body":"text","folder":"other"}},
    {"parameters":{"thread_id":42,"body":"text"}},
    {"outside_expiry_limit":True}])
async def test_invalid_native_shape_and_expiry_never_write_grant(client,changes):
    ac, app, _ = client
    key = await _pair(ac,app)
    # Evaluate the boundary when this case runs, not at collection: the full
    # suite may take longer than the excess-expiry interval.
    p = _parameters(**changes) if "outside_expiry_limit" not in changes else _parameters(
        expires_at_ms=int(time.time()*1000)+permissions.MAX_DURATION_MS+60000)
    body = await _approved(ac,app,key,p,"invalid-grant")
    result = (await ac.post("/v1/commands",json=body)).json()
    assert result["status"] == "denied", result
    assert not await app.state.store.fetchone("SELECT grant_id FROM permission_grants")


async def _begin(app,p,execution_id):
    return await app.state.owner_runtime.actions.begin(execution_id=execution_id,command_id="native-owner-use",
        turn_id=None,action_id=p["action_id"],principal_type=PrincipalType.OWNER_DEVICE,
        requested_by="device:dev-erasure",idempotency_key="use:"+execution_id,parameters=p["parameters"],
        snapshot_id=None,owner_approved=False)


@pytest.mark.asyncio
async def test_budget_and_revocation_fence_actual_effect_and_never_mint_native_a4(client):
    ac, app, _ = client
    key = await _pair(ac,app)
    p = _parameters()
    body = await _approved(ac,app,key,p,"one-use")
    assert (await ac.post("/v1/commands",json=body)).json()["status"] == "accepted"
    execution = await _begin(app,p,"first")
    assert execution.status is ExecutionStatus.AUTHORIZED
    assert (await _begin(app,p,"first")).execution_id == "first"
    with pytest.raises(ActionPolicyError,match="budget_exhausted"):
        await _begin(app,p,"second")
    await app.state.store.execute("UPDATE permission_grants SET revoked_at_ms=?",(int(time.time()*1000),))
    with pytest.raises(ActionPolicyError,match="revoked_or_expired"):
        await app.state.owner_runtime.actions.mark_executing("first")
    assert (await app.state.owner_runtime.actions.get_execution("first")).status is ExecutionStatus.AUTHORIZED
    # Exact consent for a send does not grant the independent per-use A4 approval.
    p2 = _parameters(action_id="google.gmail.send",parameters={"draft_id":"d-exact","draft_content_sha256":"a"*64})
    body = await _approved(ac,app,key,p2,"send-consent")
    assert (await ac.post("/v1/commands",json=body)).json()["status"] == "accepted"
    assert (await _begin(app,p2,"send-unapproved")).status is ExecutionStatus.AUTHORIZATION_REQUIRED


@pytest.mark.asyncio
async def test_grant_swap_refuses_old_execution_and_readback_does_not_certify_superseded_consent(client):
    ac, app, _ = client
    key = await _pair(ac,app)
    p = _parameters()
    first = await _approved(ac,app,key,p,"first-consent")
    assert (await ac.post("/v1/commands",json=first)).json()["status"] == "accepted"
    await _begin(app,p,"old-use")
    second = await _approved(ac,app,key,p,"replacement-consent")
    assert (await ac.post("/v1/commands",json=second)).json()["status"] == "accepted"
    with pytest.raises(ActionPolicyError,match="scope_changed"):
        await app.state.owner_runtime.actions.mark_executing("old-use")
    observed = await permissions.permission_readback(app.state.store,p,first["command_id"])
    assert observed["current_owner_operation_matches"] is False and "evidence_refs" not in observed


@pytest.mark.asyncio
async def test_committed_permission_reply_loss_recovers_by_readback_without_effect_replay(client,monkeypatch):
    ac, app, _ = client
    key = await _pair(ac,app)
    p = _parameters()
    body = await _approved(ac,app,key,p,"permission-commit-crash")
    actions = app.state.owner_runtime.actions
    original = actions.mark_submitted
    async def interrupt(*args,**kwargs):
        raise RuntimeError("interrupted-after-grant-commit")
    monkeypatch.setattr(actions,"mark_submitted",interrupt)
    with pytest.raises(RuntimeError,match="interrupted-after-grant-commit"):
        await ac.post("/v1/commands",json=body)
    witness = (await app.state.store.fetchone("SELECT value FROM runtime_meta WHERE key=?",(permissions.WITNESS_PREFIX+body["command_id"],)))["value"]
    monkeypatch.setattr(actions,"mark_submitted",original)
    await app.state.store.execute("UPDATE idempotency SET status='FAILED',response_json=NULL WHERE idempotency_key=?",(body["idempotency_key"],))
    async def forbid_reexecution(*args,**kwargs):
        raise AssertionError("committed permission must only be read back")
    monkeypatch.setattr(permissions,"grant_owner_permission",forbid_reexecution)
    result = (await ac.post("/v1/commands",json=body)).json()
    assert result["status"] == "accepted", result
    assert result["local_execution"]["verification_state"] == "VERIFIED_SUCCESS"
    assert (await app.state.store.fetchone("SELECT value FROM runtime_meta WHERE key=?",(permissions.WITNESS_PREFIX+body["command_id"],)))["value"] == witness
    assert (await app.state.store.fetchone("SELECT COUNT(*) AS n FROM permission_grants"))["n"] == 1


@pytest.mark.asyncio
async def test_malformed_exact_owner_control_is_refused_without_hermes_fallback(client):
    ac, app, calls = client
    await _pair(ac,app)
    response = (await ac.post("/v1/commands",json=_command(app,text=_text(_parameters(max_uses=0)),idem="malformed-exact"))).json()
    assert response["status"] == "denied" and response["message"] == "exact_owner_control_parameters_invalid"
    assert calls["create_run"] == 0
    assert not await app.state.store.fetchone("SELECT grant_id FROM permission_grants")
