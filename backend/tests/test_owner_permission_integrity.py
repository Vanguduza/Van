"""Consent source and admission clock are checked inside the actual writer lock."""
from __future__ import annotations

import asyncio
import json
import sqlite3
import time

import pytest

from van_gateway.action.registry import install_builtin_actions
from van_gateway.action.service import ActionRuntime
from van_gateway.capability import owner_permissions as permissions
from van_gateway.command.authority import CommandAuthorityRecord, CommandAuthorityService
from van_gateway.models import ActionClass, OriginChannel, PrincipalType
from van_gateway.storage.db import Store


@pytest.fixture
async def consent(tmp_path):
    store = Store(str(tmp_path / "permission-review.sqlite"))
    await store.migrate()
    runtime = ActionRuntime(store)
    await install_builtin_actions(runtime)
    now = int(time.time())
    params = {"permission":"email.send","action_id":"google.gmail.draft",
              "parameters":{"thread_id":"thread-one","body":"exact text"},
              "expires_at_ms":now*1000+120000,"max_uses":2}
    await store.execute("INSERT INTO devices(device_id,public_key_pem,enrolled_at_unix) VALUES('owner','test',?)", (now,))
    await store.execute(
        "INSERT INTO missions(mission_id,owner_principal_id,origin,origin_channel,title,goal,state,authority_envelope_json,created_at_ms,updated_at_ms) VALUES('mission','device:owner','OWNER_UI','UI','Consent','Grant exact consent','RUNNING',?,1,1)",
        (json.dumps({"source_command_id":"consent-command"}),),
    )
    authority = CommandAuthorityRecord(command_id="consent-command", device_id="owner",
        principal_type=PrincipalType.OWNER_DEVICE,requested_by="device:owner",origin_channel=OriginChannel.UI,
        signed_action_class=ActionClass.A4,effective_action_class=ActionClass.A4,
        typed_action_id=permissions.ACTION_ID,typed_parameter_constraints=params,
        snapshot_id="trusted-snapshot",context_digest="trusted-digest",issued_at_unix=now,
        expires_at_unix=now+120,no_stale_replay=True,owner_approved=True,sealed_at_unix_ms=now*1000)
    await CommandAuthorityService(store).seal(authority)
    return store, params, authority, now


async def grant(consent):
    store, params, authority, _ = consent
    await permissions.grant_owner_permission(store,params,authority.command_id,device_id="owner")
    return await permissions.permission_readback(store,params,authority.command_id)


@pytest.mark.parametrize("elapsed_ms,error", [(31000,"permission_owner_approval_expired"),
                                              (121000,"permission_owner_approval_expired")])
async def test_grant_waiting_on_writer_rechecks_actual_owner_freshness(consent, monkeypatch, elapsed_ms, error):
    store, params, authority, now = consent
    clock = [now]
    monkeypatch.setattr(permissions.time,"time",lambda:clock[0])
    async with store.connection() as db:
        await db.execute("BEGIN IMMEDIATE")
        pending = asyncio.create_task(permissions.grant_owner_permission(store,params,authority.command_id,device_id="owner"))
        done, _ = await asyncio.wait({pending},timeout=0.02)
        assert not done
        clock[0] = now + elapsed_ms/1000
        await db.commit()
    with pytest.raises(permissions.OwnerPermissionDenied,match=error):
        await pending
    assert await store.fetchone("SELECT 1 FROM permission_grants") is None
    assert await store.fetchone("SELECT 1 FROM runtime_meta WHERE key LIKE 'owner_permission_%'") is None


async def test_current_claim_loses_its_marker_and_cannot_bypass_revoked_consent(consent):
    store, params, _, _ = consent
    await grant(consent)
    await permissions.enforce_permission_scope(store,action_id=params["action_id"],parameters=params["parameters"],execution_id="actual-use",claim=True)
    await store.execute("DELETE FROM runtime_meta WHERE key=?",(permissions.scope_key(params["action_id"],params["parameters"]),))
    with pytest.raises(permissions.OwnerPermissionDenied,match="permission_execution_scope_changed"):
        await permissions.recheck_permission_execution(store,"actual-use")


async def test_current_pointer_cannot_admit_another_parameter_set(consent):
    store, params, _, _ = consent
    await grant(consent)
    current = await store.fetchone("SELECT value FROM runtime_meta WHERE key=?",(permissions.scope_key(params["action_id"],params["parameters"]),))
    different={"thread_id":"thread-other","body":"exact text"}
    await store.execute("INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,1)",
        (permissions.scope_key(params["action_id"],different),current["value"]))
    with pytest.raises(permissions.OwnerPermissionDenied,match="permission_scope_integrity_failed"):
        await permissions.enforce_permission_scope(store,action_id=params["action_id"],parameters=different,execution_id="wrong-scope",claim=True)
    assert (await store.fetchone("SELECT use_count FROM permission_grants"))["use_count"] == 0


@pytest.mark.parametrize("change", [{"command_id":"different-source"},{"device_id":"another-owner"},
                                     {"native_action_class":"A1"},{"created_at_ms":1},
                                     {"schema_version":2}])
async def test_current_witness_must_match_immutable_authenticated_source(consent,change):
    store, params, _, _ = consent
    await grant(consent)
    await store.execute("INSERT INTO devices(device_id,public_key_pem,enrolled_at_unix) VALUES('another-owner','test',1)")
    key=permissions.scope_key(params["action_id"],params["parameters"])
    current=json.loads((await store.fetchone("SELECT value FROM runtime_meta WHERE key=?",(key,)))["value"])
    current.update(change)
    await store.execute("UPDATE runtime_meta SET value=? WHERE key=?",(Store.dumps(current),key))
    with pytest.raises(permissions.OwnerPermissionDenied,match="permission_scope_integrity_failed"):
        await permissions.enforce_permission_scope(store,action_id=params["action_id"],parameters=params["parameters"],execution_id="changed-source",claim=True)
    assert (await store.fetchone("SELECT use_count FROM permission_grants"))["use_count"] == 0


async def test_missing_immutable_witness_cannot_admit_current_marker(consent):
    store, params, authority, _ = consent
    await grant(consent)
    await store.execute("DELETE FROM runtime_meta WHERE key=?",(permissions.WITNESS_PREFIX+authority.command_id,))
    with pytest.raises(permissions.OwnerPermissionDenied,match="permission_scope_integrity_failed"):
        await permissions.enforce_permission_scope(store,action_id=params["action_id"],parameters=params["parameters"],execution_id="missing-source",claim=True)


async def test_readback_and_effect_agree_revoked_issuer_is_not_current(consent):
    store, params, authority, _ = consent
    assert (await grant(consent))["current_owner_operation_matches"]
    await store.execute("UPDATE devices SET revoked_at_unix=1 WHERE device_id='owner'")
    observed=await permissions.permission_readback(store,params,authority.command_id)
    assert observed["owner_approved_command_bound"] and observed["grant_exists"]
    assert not observed["grant_current"] and not observed["current_owner_operation_matches"]
    assert "evidence_refs" not in observed
    with pytest.raises(permissions.OwnerPermissionDenied,match="permission_scope_revoked_or_expired"):
        await permissions.enforce_permission_scope(store,action_id=params["action_id"],parameters=params["parameters"],execution_id="revoked-use",claim=True)


async def test_no_exact_marker_still_allows_independent_fresh_native_parameter_set(consent):
    store, params, _, _ = consent
    await grant(consent)
    different={"thread_id":"separately-signed-target","body":"fresh independent owner text"}
    await permissions.enforce_permission_scope(store,action_id=params["action_id"],parameters=different,execution_id="fresh-use",claim=True)
    assert await store.fetchone("SELECT 1 FROM runtime_meta WHERE key=?",(permissions.CLAIM_PREFIX+"fresh-use",)) is None
    assert (await store.fetchone("SELECT use_count FROM permission_grants"))["use_count"] == 0


async def test_concurrent_idempotency_recovery_reserves_only_one_canonical_admission(consent,monkeypatch):
    store,params,_,_=consent
    await grant(consent)
    actions=ActionRuntime(store)
    original=actions._persist_execution
    reached=0
    ready=asyncio.Event()
    async def both_requests_before_persist(*args,**kwargs):
        nonlocal reached
        reached+=1
        if reached==2:
            ready.set()
        await ready.wait()
        return await original(*args,**kwargs)
    monkeypatch.setattr(actions,"_persist_execution",both_requests_before_persist)
    async def begin(execution_id):
        return await actions.begin(execution_id=execution_id,command_id="same-native-command",turn_id=None,
            action_id=params["action_id"],principal_type=PrincipalType.OWNER_DEVICE,requested_by="device:owner",
            idempotency_key="same-canonical-idempotency",parameters=params["parameters"],snapshot_id=None,owner_approved=False)
    first,second=await asyncio.wait_for(asyncio.gather(begin("candidate-first"),begin("candidate-second")),timeout=3)
    assert first==second
    assert len(await store.fetchall("SELECT * FROM action_executions"))==1
    assert (await store.fetchone("SELECT use_count FROM permission_grants"))["use_count"]==1
    assert len(await store.fetchall("SELECT * FROM runtime_meta WHERE key LIKE 'owner_permission_claim:%'"))==1


async def test_ledger_insert_failure_rolls_back_permission_reservation_and_exact_retry_recovers(consent):
    store,params,_,_=consent
    await grant(consent)
    actions=ActionRuntime(store)
    await store.execute("CREATE TRIGGER fail_new_execution BEFORE INSERT ON action_executions BEGIN SELECT RAISE(ABORT,'admission transaction interrupted'); END")
    kwargs=dict(execution_id="stable-admission",command_id="native-command",turn_id=None,
        action_id=params["action_id"],principal_type=PrincipalType.OWNER_DEVICE,requested_by="device:owner",
        idempotency_key="stable-native-admission",parameters=params["parameters"],snapshot_id=None,owner_approved=False)
    with pytest.raises(sqlite3.IntegrityError,match="admission transaction interrupted"):
        await actions.begin(**kwargs)
    assert await store.fetchone("SELECT 1 FROM action_executions") is None
    assert (await store.fetchone("SELECT use_count FROM permission_grants"))["use_count"]==0
    assert await store.fetchone("SELECT 1 FROM runtime_meta WHERE key LIKE 'owner_permission_claim:%'") is None
    await store.execute("DROP TRIGGER fail_new_execution")
    accepted=await actions.begin(**kwargs)
    assert await actions.begin(**kwargs)==accepted
    assert (await store.fetchone("SELECT use_count FROM permission_grants"))["use_count"]==1


@pytest.mark.parametrize("depth,error", [(17,"permission_scope_too_deep"),
    (1100,r"permission_(parameters_invalid|scope_private_credentials_refused|scope_too_deep)")])
def test_nested_scope_is_bounded_and_does_not_raise_recursion_errors(depth,error):
    nested="value"
    for _ in range(depth):
        nested={"nested":nested}
    body={"permission":"email.send","action_id":"google.gmail.draft","parameters":nested,
          "expires_at_ms":1800000000000,"max_uses":1}
    with pytest.raises(permissions.OwnerPermissionDenied,match=error):
        permissions.permission_parameters(body)


def test_serializer_recursion_failure_is_an_explicit_refusal(monkeypatch):
    def too_deep(*args,**kwargs):
        raise RecursionError("nested JSON")
    monkeypatch.setattr(permissions.json,"dumps",too_deep)
    body={"permission":"email.send","action_id":"google.gmail.draft","parameters":{},
          "expires_at_ms":1800000000000,"max_uses":1}
    with pytest.raises(permissions.OwnerPermissionDenied,match="permission_parameters_invalid"):
        permissions.permission_parameters(body)


def test_invalid_unicode_is_a_bounded_parameter_refusal():
    body={"permission":"email.send","action_id":"google.gmail.draft",
          "parameters":{"thread_id":"thread","body":"\ud800"},"expires_at_ms":1800000000000,"max_uses":1}
    with pytest.raises(permissions.OwnerPermissionDenied,match="permission_parameters_invalid"):
        permissions.permission_parameters(body)
