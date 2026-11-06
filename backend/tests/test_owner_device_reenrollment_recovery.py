"""LAC-348 source evidence with real SQLite/CA files and strict native fixture receipts.

The authenticated native transport is synthetic; these are not deployed/device gates.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet

from conftest_automation import make_store
from test_owner_device_binding import _attestation, _keypair, _policy
from test_mtls_pki import csr_for
from van_gateway.auth.device_binding import DeviceBindingError, OwnerDeviceBindingService
from van_gateway.auth.native_revocation import NativeOwnerRevocations
from van_gateway.auth.reenrollment import OwnerDeviceReenrollment
from van_gateway.auth.service import AuthError, AuthService
from van_gateway.browser.stream_grants import generate_signing_key
from van_gateway.connectivity.config import ConnectivityConfigService
from van_gateway.mtls.pki import DeviceCA, init_ca
from van_gateway.storage.db import Store
from vati.authority_registry import revocation_record

pytestmark = pytest.mark.asyncio


class NativeFixture:
    def __init__(self):
        self.available = False
        self.calls = []

    def run(self, command, target):
        assert command == "owner_authority_revoke"
        self.calls.append(dict(target))
        if not self.available:
            raise TimeoutError("synthetic acknowledgement loss")
        proof = revocation_record(target["device_id"], target["key_id"])
        return {**proof, "phase": "APPLIED", "revoked": True, "key_active": False,
                "revocation_ref": hashlib.sha256(json.dumps(proof,sort_keys=True,separators=(",", ":")).encode()).hexdigest(),
                "registry_ref": "b" * 64}


async def setup(tmp_path):
    store = await make_store(tmp_path)
    fernet = Fernet.generate_key().decode()
    auth = AuthService(store, fernet)
    bindings = OwnerDeviceBindingService(store, _policy())
    token, challenge = await bindings.create_bootstrap_token()
    pem, key = _keypair()
    binding = await bindings.bind(token=token, device_id="original-phone",public_key_pem=pem,
        attestation_extension=_attestation(challenge.encode()),attestation_chain_verified=True)
    ticket = await auth.create_pairing_ticket("original")
    await auth.pair_device(ticket.token,"original-phone","s"*32,pem)
    old_unspent, _ = await bindings.create_bootstrap_token()
    other_token, _ = await bindings.create_bootstrap_token(owner_principal_id="other-owner")
    await store.execute("INSERT INTO van_sessions(van_session_id,session_epoch,device_id,principal_type,state,created_at_ms) "
        "VALUES('original-session',1,'original-phone','OWNER_DEVICE','ACTIVE',?)",(int(time.time()*1000),))
    ca_dir = tmp_path / "ca"
    init_ca(ca_dir)
    ca = DeviceCA(ca_dir)
    ca.issue_client(csr_for("original-phone")[0],"original-phone")
    ca.issue_client(csr_for("unrelated-phone")[0],"unrelated-phone")
    native = NativeFixture()
    native_owner = NativeOwnerRevocations(store=store,promotions=SimpleNamespace(control=native))
    signing = generate_signing_key("reenrollment-fixture")
    connectivity = ConnectivityConfigService(store,private_pem=signing.private_pem,kid=signing.kid)
    service = OwnerDeviceReenrollment(store=store,auth=auth,native_revocations=native_owner,
        device_ca=lambda:ca,connectivity=connectivity)
    request = dict(operator_id="installer-actor",reason="lost handset",operation_id="replacement-original-0001",
        expected_binding_id=binding.binding_id,expected_bound_at_ms=binding.bound_at_ms,gateway_url="https://gateway.example")
    return SimpleNamespace(store=store,auth=auth,bindings=bindings,binding=binding,service=service,native=native,
        native_owner=native_owner,request=request,fernet=fernet,old_unspent=old_unspent,other_token=other_token,ca=ca,
        connectivity=connectivity)


async def test_original_retirement_is_durable_inert_and_recovered_after_restart(tmp_path):
    f = await setup(tmp_path)
    pending = await f.service.start(**f.request)
    assert pending["phase"] == "RETIRING" and pending["bootstrap_token"] is None and pending["envelope"] is None
    assert pending["native_authority_revocation"]["phase"] == "PENDING"
    assert (await f.bindings.for_device("original-phone")).status.value == "REVOKED"
    with pytest.raises(AuthError,match="revoked"):
        await f.auth.require_device("original-phone")
    assert (await f.store.fetchone("SELECT state FROM van_sessions WHERE van_session_id='original-session'"))[0] == "CLOSED"
    with pytest.raises(DeviceBindingError,match="revoked"):
        await f.bindings.challenge_for(f.old_unspent)
    assert await f.bindings.challenge_for(f.other_token)
    with pytest.raises(DeviceBindingError,match="retirement_pending"):
        await f.bindings.create_bootstrap_token()
    inert = await f.store.fetchone("SELECT * FROM owner_device_reenrollments")
    assert await f.store.fetchone("SELECT token_id FROM owner_device_bootstrap_tokens WHERE token_sha256=?",
        (inert["bootstrap_token_sha256"],)) is None
    raw = open(f.store.path,"rb").read()
    secret = json.loads(f.auth._cipher().decrypt(inert["encrypted_response"].encode()))
    assert secret["bootstrap_token"].encode() not in raw
    assert secret["envelope"]["payload"]["pairing_token"].encode() not in raw
    # New service objects and connections, same durable identities and original deadline.
    reopened = Store(f.store.path)
    await reopened.migrate()
    auth = AuthService(reopened,f.fernet)
    native_owner = NativeOwnerRevocations(store=reopened,promotions=SimpleNamespace(control=f.native))
    recovered = OwnerDeviceReenrollment(store=reopened,auth=auth,native_revocations=native_owner,
        device_ca=lambda:f.ca,connectivity=f.connectivity)
    f.native.available = True
    ready = await recovered.start(**f.request)
    assert ready["phase"] == "READY" and ready["expires_at_ms"] == pending["expires_at_ms"]
    assert ready["bootstrap_token"] == secret["bootstrap_token"]
    assert ready["envelope"] == secret["envelope"]
    assert len({x["operation_id"] for x in f.native.calls}) == 1
    assert ready["native_authority_revocation"]["phase"] == "APPLIED"
    assert (await recovered.start(**f.request)) == ready
    replacement = OwnerDeviceBindingService(reopened,_policy())
    pem, _ = _keypair()
    bound = await replacement.bind(token=ready["bootstrap_token"],device_id="replacement-phone",public_key_pem=pem,
        attestation_extension=_attestation(ready["attestation_challenge"].encode()),attestation_chain_verified=True)
    assert bound.device_id == "replacement-phone"
    assert (await recovered.start(**f.request))["bootstrap_token"] == ready["bootstrap_token"]
    assert (await replacement.active()).binding_id == bound.binding_id
    ticket = ready["envelope"]["payload"]["pairing_token"]
    await auth.pair_device(ticket,"replacement-phone","r"*32,pem)
    with pytest.raises(AuthError,match="fresh installation identity"):
        other_ticket = await auth.create_pairing_ticket("old-key")
        await auth.pair_device(other_ticket.token,"resurrected-phone","r"*32,f.binding.public_key_pem)


async def test_request_conflict_wrong_operator_stale_cas_and_legacy_ambiguity_do_not_retire_new_binding(tmp_path):
    f = await setup(tmp_path)
    wrong = {**f.request,"expected_bound_at_ms": f.binding.bound_at_ms+1}
    with pytest.raises(DeviceBindingError,match="precondition_failed"):
        await f.service.start(**wrong)
    assert (await f.bindings.active()).binding_id == f.binding.binding_id
    f.native.available = True
    legacy = dict(operator_id="installer-actor",reason="lost handset")
    ready = await f.service.start(**legacy)
    assert ready["phase"] == "READY"
    assert (await f.service.start(**legacy)) == ready
    pem, _ = _keypair()
    bound = await f.bindings.bind(token=ready["bootstrap_token"],device_id="fresh-phone",public_key_pem=pem,
        attestation_extension=_attestation(ready["attestation_challenge"].encode()))
    with pytest.raises(DeviceBindingError,match="identity_required"):
        await f.service.start(**legacy)
    with pytest.raises(DeviceBindingError,match="operation_unknown"):
        await f.service.recover(operation_id=ready["operation_id"],operator_id="wrong-operator")
    assert (await f.bindings.active()).binding_id == bound.binding_id


async def test_atomic_intent_failure_rolls_back_all_local_retirement(tmp_path):
    f = await setup(tmp_path)
    await f.store.execute("CREATE TRIGGER fail_reenrollment BEFORE INSERT ON owner_device_reenrollments "
        "BEGIN SELECT RAISE(ABORT,'synthetic receipt failure'); END")
    with pytest.raises(Exception,match="synthetic receipt failure"):
        await f.service.start(**f.request)
    assert (await f.bindings.active()).binding_id == f.binding.binding_id
    assert (await f.auth.require_device("original-phone")).revoked_at_unix is None
    assert await f.bindings.challenge_for(f.old_unspent)
    assert not await f.store.fetchall("SELECT * FROM device_certificate_retirements")
    assert not await f.store.fetchall("SELECT * FROM runtime_meta WHERE key GLOB 'native_owner_revocation:*'")


async def test_concurrent_original_retries_and_expiry_never_extend_credential(tmp_path):
    f = await setup(tmp_path)
    pending = await f.service.start(**f.request)
    with pytest.raises(DeviceBindingError,match="operation_conflict"):
        await f.service.start(**{**f.request,"reason":"different intent"})
    # Background reconciliation may finish after the original credential's deadline.
    f.native.available = True
    expired = await f.service.recover(operation_id=f.request["operation_id"],operator_id=f.request["operator_id"],
        now_ms=pending["expires_at_ms"])
    assert expired["phase"] == "EXPIRED" and expired["bootstrap_token"] is None
    assert not await f.store.fetchall("SELECT token_id FROM owner_device_bootstrap_tokens WHERE token_sha256 IN "
        "(SELECT bootstrap_token_sha256 FROM owner_device_reenrollments)")
    assert (await f.service.start(**f.request,now_ms=pending["expires_at_ms"]+1000))["expires_at_ms"] == pending["expires_at_ms"]


async def test_ca_marker_failure_and_native_unknown_replay_original_without_enabling_credentials(tmp_path,monkeypatch):
    f = await setup(tmp_path)
    f.native.available = True
    execute = f.store.execute
    async def fail_marker(sql,params=()):
        if "UPDATE device_certificate_retirements SET certificates_retired_at_ms" in sql:
            raise OSError("synthetic CA marker failure after actual revocation")
        return await execute(sql,params)
    with monkeypatch.context() as scoped:
        scoped.setattr(f.store,"execute",fail_marker)
        pending = await f.service.start(**f.request)
    assert pending["phase"] == "RETIRING" and pending["bootstrap_token"] is None
    assert pending["native_authority_revocation"]["phase"] == "APPLIED"
    assert pending["certificates_retired"] is False
    listing = f.ca.listing()
    assert next(c for c in listing if c["device_id"]=="original-phone")["revoked_at_unix"]
    assert not next(c for c in listing if c["device_id"]=="unrelated-phone").get("revoked_at_unix")
    f.native.available = True
    ready = await f.service.start(**f.request)
    assert ready["phase"] == "READY" and ready["expires_at_ms"] == pending["expires_at_ms"]
    assert len(await f.store.fetchall("SELECT * FROM owner_device_reenrollments")) == 1


async def test_two_competing_intents_have_one_exact_winner_and_normal_revoke_has_same_barrier(tmp_path):
    f = await setup(tmp_path)
    requests = [f.request,{**f.request,"operation_id":"replacement-competing-0002"}]
    results = await asyncio.gather(*(f.service.start(**r) for r in requests),return_exceptions=True)
    assert sum(isinstance(r,dict) for r in results)==1
    assert sum(isinstance(r,DeviceBindingError) for r in results)==1
    assert len(await f.store.fetchall("SELECT * FROM owner_device_reenrollments"))==1
    assert len(await f.store.fetchall("SELECT * FROM device_certificate_retirements"))==1
    with pytest.raises(AuthError,match="retirement is pending"):
        ticket = await f.auth.create_pairing_ticket("bypass")
        await f.auth.pair_device(ticket.token,"bypass-phone","r"*32,_keypair()[0])
    with pytest.raises(AuthError,match="retirement is pending"):
        await f.auth.enroll("bypass-legacy-phone","r"*32,_keypair()[0])
    # The normal revoke writer also retires the hardware binding and fences bootstrap.
    other_path=tmp_path/"normal-revoke"
    other_path.mkdir()
    g = await setup(other_path)
    await g.auth.revoke("original-phone")
    assert (await g.bindings.for_device("original-phone")).status.value=="REVOKED"
    with pytest.raises(DeviceBindingError,match="retirement_pending"):
        await g.bindings.create_bootstrap_token()


async def test_undispatched_actions_retire_but_submitted_effects_and_unrelated_work_remain(tmp_path):
    f = await setup(tmp_path)
    await f.store.execute("INSERT INTO action_definitions(action_id,action_class,mutates_state,allowed_principals_json,"
        "verifier_type,parameter_schema_json,updated_at_unix_ms) VALUES('replacement-test-action','A3',1,'[]','RECEIPT','{}',0)")
    rows=[("ready","AUTHORIZED","device:original-phone"),("effect","SUBMITTED","device:original-phone"),
          ("verifying","VERIFYING","device:original-phone"),("other","AUTHORIZED","device:unrelated-phone")]
    for identity,status,requester in rows:
        await f.store.execute("INSERT INTO action_executions(execution_id,command_id,action_id,action_class,principal_type,"
            "requested_by,status,idempotency_key,parameters_digest,correlation_json,updated_at_unix_ms) "
            "VALUES(?,?,'replacement-test-action','A3','OWNER_DEVICE',?,?,?,'digest','{}',0)",
            (identity,identity,requester,status,identity))
    await f.service.start(**f.request)
    states={r["execution_id"]:r["status"] for r in await f.store.fetchall("SELECT execution_id,status FROM action_executions")}
    assert states=={"ready":"REVOKED","effect":"SUBMITTED","verifying":"VERIFYING","other":"AUTHORIZED"}
    from van_gateway.session.service import VanHermesSessionService,SessionError
    with pytest.raises(SessionError,match="device_revoked"):
        await VanHermesSessionService(f.store).open(device_id="original-phone")


async def test_changed_signing_configuration_replays_original_and_corrupt_secret_fails_closed(tmp_path):
    f=await setup(tmp_path)
    f.native.available=True
    ready=await f.service.start(**f.request)
    f.connectivity.private_pem=None
    assert (await f.service.start(**f.request))["envelope"]==ready["envelope"]
    await f.store.execute("UPDATE owner_device_reenrollments SET encrypted_response='corrupt'")
    with pytest.raises(DeviceBindingError,match="original_response_unavailable"):
        await f.service.start(**f.request)


@pytest.mark.parametrize("column,value",[("request_digest","changed"),("original_bound_at_ms",0),
    ("original_binding_id","unrelated-binding"),("original_device_id","unrelated-phone"),
    ("native_operation_id","0"*64),("challenge","changed"),("bootstrap_token_sha256","0"*64),
    ("reason","changed"),("gateway_url","https://different.example"),("legacy",1)])
async def test_corrupt_original_identity_refuses_before_ca_or_native_recovery(tmp_path,column,value):
    f=await setup(tmp_path)
    # Persist the valid initial intent while both effects are deliberately unavailable.
    f.service.device_ca=lambda:None
    await f.service.start(**f.request)
    f.native.calls.clear()
    f.service.device_ca=lambda:f.ca
    f.native.available=True
    await f.store.execute(f"UPDATE owner_device_reenrollments SET {column}=?",(value,))
    with pytest.raises(DeviceBindingError,match="original_response_unavailable"):
        await f.service.recover(operation_id=f.request["operation_id"],operator_id=f.request["operator_id"])
    assert not f.native.calls
    assert not next(c for c in f.ca.listing() if c["device_id"]=="original-phone").get("revoked_at_unix")


@pytest.mark.parametrize("crash",["before_commit","after_commit"])
async def test_actual_process_death_preserves_original_transaction_or_recovery(tmp_path,crash):
    import os
    import subprocess
    import sys
    from pathlib import Path
    key=Fernet.generate_key().decode()
    program = r"""
import asyncio,os,sys
from pathlib import Path
from cryptography.fernet import Fernet
from test_owner_device_reenrollment_recovery import setup
async def main():
    fixture=await setup(Path(sys.argv[1]))
    fixture.auth._fernet=Fernet(os.environ['VAN_REENROLLMENT_CRASH_TEST_KEY'].encode())
    if sys.argv[2]=='before_commit':
        import aiosqlite
        original=aiosqlite.Connection.execute
        async def execute(self,sql,*args,**kwargs):
            if sql.startswith('INSERT INTO owner_device_reenrollments'):
                os._exit(27)
            return await original(self,sql,*args,**kwargs)
        aiosqlite.Connection.execute=execute
    else:
        async def die(**kwargs):os._exit(28)
        fixture.service.recover=die
    await fixture.service.start(**fixture.request)
asyncio.run(main())
"""
    result=subprocess.run([sys.executable,"-c",program,str(tmp_path),crash],
        env={**os.environ,"VAN_REENROLLMENT_CRASH_TEST_KEY":key},capture_output=True,timeout=30)
    (tmp_path/"child.stdout").write_bytes(result.stdout)
    (tmp_path/"child.stderr").write_bytes(result.stderr)
    assert result.returncode==(27 if crash=="before_commit" else 28),result.stderr.decode()
    store=Store(str(tmp_path/"van.sqlite3"))
    await store.migrate()
    device=await store.fetchone("SELECT revoked_at_unix FROM devices WHERE device_id='original-phone'")
    rows=await store.fetchall("SELECT * FROM owner_device_reenrollments")
    if crash=="before_commit":
        assert not rows and device[0] is None
        assert not await store.fetchall("SELECT * FROM device_certificate_retirements")
        assert (await OwnerDeviceBindingService(store,_policy()).active()).device_id=="original-phone"
        return
    assert device[0] is not None and len(rows)==1
    row=rows[0]
    native=NativeFixture()
    native.available=True
    service=OwnerDeviceReenrollment(store=store,auth=AuthService(store,key),
        native_revocations=NativeOwnerRevocations(store=store,promotions=SimpleNamespace(control=native)),
        device_ca=lambda:DeviceCA(tmp_path/"ca"),connectivity=None)
    ready=await service.recover(operation_id=row["operation_id"],operator_id=row["operator_id"])
    assert ready["phase"]=="READY" and ready["expires_at_ms"]==row["expires_at_ms"]
    assert len({call["operation_id"] for call in native.calls})==1
    assert len(await store.fetchall("SELECT * FROM owner_device_reenrollments"))==1


async def test_interrupted_migration_ddl_restarts_without_losing_original_replacement(tmp_path):
    f=await setup(tmp_path)
    pending=await f.service.start(**f.request)
    original=dict(await f.store.fetchone("SELECT * FROM owner_device_reenrollments"))
    # Store.migrate executes DDL before its version marker. Simulate death between
    # those boundaries, retaining the actual installed schema and original data.
    await f.store.execute("DELETE FROM schema_migrations WHERE version=60")
    reopened=Store(f.store.path)
    await reopened.migrate()
    assert dict(await reopened.fetchone("SELECT * FROM owner_device_reenrollments"))==original
    assert (await reopened.fetchone("SELECT COUNT(*) FROM schema_migrations WHERE version=60"))[0]==1
    assert pending["operation_id"]==original["operation_id"]
    await reopened.migrate()
    assert dict(await reopened.fetchone("SELECT * FROM owner_device_reenrollments"))==original
