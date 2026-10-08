"""Irreversible erasure requires exact device-bound approval and real post-state."""

from __future__ import annotations

import base64
import json
import time
import uuid

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from tests.test_local_typed_actions import client, _settings, _pair_a4_device, _public_pem  # noqa: F401
from van_gateway.auth.service import AuthService
from van_gateway.command.resolver import ResolutionMode, TypedCommandResolver
from van_gateway.context.forget import FORGETTABLE
from van_gateway.context.memory_erasure import memory_erasure_readback, selected_stores
from van_gateway.context.models import ContextRequirement
from van_gateway.context.retrieval import HotContextCapsuleRequest

pytestmark = pytest.mark.asyncio


def _command(app, *, text, idem, device="dev-erasure", expires=None, proof=None, no_stale=False, context_trust="CONVERSATION"):
    now, command_id, nonce = int(time.time()), str(uuid.uuid4()), str(uuid.uuid4())
    kwargs = dict(command_id=command_id, idempotency_key=idem, device_id=device,
        issued_at_unix=now, text=text, action_class="A1", project_id=None,
        turn_id="turn-erasure", origin_channel="UI", principal_type="OWNER_DEVICE",
        requested_by=f"device:{device}", expires_at_unix=expires, nonce=nonce,
        context_capsule_revision=None, context_capsule_hash=None, speech_evidence_ref=None,
        no_stale_replay=no_stale, context_trust=context_trust)
    canonical = AuthService.canonical_command_v2(**kwargs)
    body = {k: v for k, v in kwargs.items() if v is not None}
    body.update(signature_version=2, signature=app.state.auth.sign(device, canonical))
    if proof is not None:
        body["approval_proof"] = proof
    return body


async def _pair(ac, app, device="dev-erasure"):
    key = ec.generate_private_key(ec.SECP256R1())
    await _pair_a4_device(ac, app, device_id=device, secret=f"test-secret-{device}", public_key_pem=_public_pem(key))
    return key


async def _fact(app):
    return await app.state.owner_fact_author.state(device_id="dev-erasure", subject="owner",
        predicate="memory_test", value="private-memory-content", scope="global")


async def _challenge(ac, app, key, text, idem):
    first = await ac.post("/v1/commands", json=_command(app, text=text, idem=idem + "-challenge"))
    assert first.status_code == 200, first.text
    challenge = first.json()
    assert challenge["status"] == "approval_required" and challenge["resolved_action_id"] == "memory.erase"
    assert challenge["effective_action_class"] == "A4"
    proof = {"challenge_id": challenge["approval_challenge_id"], "algorithm": "ECDSA_P256_SHA256",
        "signature_b64": base64.b64encode(key.sign(challenge["approval_challenge"].encode(), ec.ECDSA(hashes.SHA256()))).decode()}
    return proof


async def _approve(ac, app, key, text, idem):
    proof = await _challenge(ac, app, key, text, idem)
    body = _command(app, text=text, idem=idem, expires=int(time.time()) + 10, proof=proof, no_stale=True)
    response = await ac.post("/v1/commands", json=body)
    assert response.status_code == 200, response.text
    return body, response.json()


async def test_memory_store_erasure_requires_approval_then_independent_exact_readback(client):
    ac, app, hermes = client
    key = await _pair(ac, app)
    fact = await _fact(app)
    before_revision = await app.state.owner_runtime.context.kernel_revision()
    request = HotContextCapsuleRequest(scopes=["global"],
        requirements=[ContextRequirement(subject="owner", predicate="memory_test", scope="global")],
        seed_nodes=["owner"], lexical_queries=["private-memory-content"], ttl_ms=60_000)
    before_capsule = await app.state.owner_runtime.retrieval.compile_hot_capsule(request)
    assert any(fact.fact_id in ref for ref in before_capsule.fact_refs)
    assert (await app.state.owner_runtime.retrieval.compile_hot_capsule(request)).cache_hit is True
    text = "forget owner-derived memory store owner_facts"
    proof = await _challenge(ac, app, key, text, "erase-facts")
    assert await app.state.store.fetchone("SELECT fact_id FROM owner_facts WHERE fact_id=?", (fact.fact_id,))
    body = _command(app, text=text, idem="erase-facts", expires=int(time.time()) + 10, proof=proof, no_stale=True)
    response = await ac.post("/v1/commands", json=body)
    result = response.json()
    assert result["status"] == "accepted", result
    assert result["local_execution"]["verification_state"] == "VERIFIED_SUCCESS"
    assert result["local_execution"]["removed_counts"] == {"owner_facts": 1}
    assert hermes["create_run"] == 0
    assert not await app.state.store.fetchone("SELECT fact_id FROM owner_facts WHERE fact_id=?", (fact.fact_id,))
    assert await app.state.owner_runtime.context.kernel_revision() > before_revision
    after_capsule = await app.state.owner_runtime.retrieval.compile_hot_capsule(request)
    assert after_capsule.cache_hit is False
    assert not any(fact.fact_id in ref for ref in after_capsule.fact_refs)
    mission = await app.state.store.fetchone("SELECT state,verification_record_json FROM missions WHERE mission_id=?", (result["mission_id"],))
    assert mission["state"] == "VERIFIED_SUCCESS"
    record = json.loads(mission["verification_record_json"])
    assert record["observed_postconditions"]["captured_ids_absent"] is True
    assert record["observed_postconditions"]["context_cache_invalidated"] is True
    assert record["evidence_refs"]
    witness = (await app.state.store.fetchone("SELECT value FROM runtime_meta WHERE key=?", ("memory_erasure_witness:" + body["command_id"],)))["value"]
    assert "private-memory-content" not in witness
    assert fact.fact_id not in witness
    assert (await ac.post("/v1/commands", json=body)).json() == result
    assert "audit" in result["local_execution"]["kept_deliberately"]


async def test_all_erasure_matches_allowlist_and_preserves_other_principal_and_audit(client):
    ac, app, _ = client
    key = await _pair(ac, app)
    await _fact(app)
    await app.state.store.execute("INSERT INTO owner_cognitive_model(assertion_id,owner_principal_id,field,value,created_at_ms,updated_at_ms) VALUES('other-assertion','other-owner','values','private-other',1,1)")
    _, result = await _approve(ac, app, key, "forget all owner-derived memory", "erase-all")
    assert result["status"] == "accepted", result
    assert set(result["local_execution"]["removed_counts"]) == {entry.table for entry in FORGETTABLE}
    assert result["local_execution"]["removed_counts"]["owner_facts"] == 1
    assert await app.state.store.fetchone("SELECT assertion_id FROM owner_cognitive_model WHERE assertion_id='other-assertion'")
    inventory = await app.state.owner_memory.inventory()
    assert all(s["rows"] == 0 for s in inventory["stores"].values())
    assert await app.state.store.fetchone("SELECT COUNT(*) AS n FROM audit")


async def test_approval_cannot_move_to_other_store_or_recur_for_new_command(client):
    ac, app, _ = client
    key = await _pair(ac, app)
    fact = await _fact(app)
    proof = await _challenge(ac, app, key, "forget owner-derived memory store owner_facts", "bound-store")
    response = await ac.post("/v1/commands", json=_command(app,
        text="forget all owner-derived memory", idem="changed-store", expires=int(time.time()) + 10, proof=proof, no_stale=True))
    assert response.json()["status"] == "denied"
    assert await app.state.store.fetchone("SELECT fact_id FROM owner_facts WHERE fact_id=?", (fact.fact_id,))
    body = _command(app, text="forget owner-derived memory store owner_facts", idem="bound-store",
                    expires=int(time.time()) + 10, proof=proof, no_stale=True)
    assert (await ac.post("/v1/commands", json=body)).json()["status"] == "accepted"
    second = _command(app, text=body["text"], idem="another-occurrence", expires=int(time.time()) + 10, proof=proof, no_stale=True)
    assert (await ac.post("/v1/commands", json=second)).json()["status"] == "denied"


async def test_intent_node_scope_removes_only_related_links_and_reports_closure(client):
    ac, app, _ = client
    key = await _pair(ac, app)
    store = app.state.store
    for intent in ("old-a", "old-b"):
        await store.execute("INSERT INTO intent_nodes(intent_id,owner_goal,first_observed_ms,latest_observed_ms) VALUES(?,?,1,1)", (intent, "private intent"))
    await store.execute("INSERT INTO intent_edges(edge_id,from_intent_id,to_intent_id,edge_type,created_at_ms) VALUES('linked-edge','old-a','old-b','SUPPORTS',1)")
    await store.execute("INSERT INTO intent_missions VALUES('old-a','mission-old',1)")
    await store.execute("INSERT INTO intent_missions VALUES('unrelated-orphan','mission-kept',1)")
    _, result = await _approve(ac, app, key, "forget owner-derived memory store intent_nodes", "erase-intents")
    assert result["status"] == "accepted", result
    assert set(result["local_execution"]["removed_counts"]) == {"intent_edges", "intent_missions", "intent_nodes"}
    assert result["local_execution"]["removed_counts"]["intent_edges"] == 1
    assert not await store.fetchone("SELECT intent_id FROM intent_nodes")
    assert await store.fetchone("SELECT intent_id FROM intent_missions WHERE intent_id='unrelated-orphan'")


async def test_independent_observer_detects_resurrected_exact_identity_and_direct_delete_is_blocked(client):
    ac, app, _ = client
    key = await _pair(ac, app)
    fact = await _fact(app)
    old = dict(await app.state.store.fetchone("SELECT * FROM owner_facts WHERE fact_id=?", (fact.fact_id,)))
    refused = await ac.delete("/v1/context/memory?store=owner_facts")
    assert refused.status_code == 409, refused.text
    assert await app.state.store.fetchone("SELECT fact_id FROM owner_facts WHERE fact_id=?", (fact.fact_id,))
    body, result = await _approve(ac, app, key, "forget owner-derived memory store owner_facts", "erase-readback")
    assert result["status"] == "accepted"
    columns = list(old)
    await app.state.store.execute(f"INSERT INTO owner_facts({','.join(columns)}) VALUES({','.join('?' for _ in columns)})", tuple(old[c] for c in columns))
    observed = await memory_erasure_readback(app.state.store, "owner_facts", body["command_id"])
    assert observed["captured_ids_absent"] is False and observed["scope_empty"] is False
    assert "evidence_refs" not in observed
    fabricated = await memory_erasure_readback(app.state.store, "owner_facts", "fabricated")
    assert fabricated["owner_approved_command_bound"] is False


async def test_unknown_or_untrusted_memory_erasure_never_bypasses_exact_authority(client):
    resolver = TypedCommandResolver()
    for phrase in ("forget owner-derived memory store audit", "forget owner-derived memory store devices", "forget everything"):
        assert resolver.resolve(phrase).mode is ResolutionMode.HERMES_INTERPRETATION_REQUIRED
    resolution = resolver.resolve("forget owner-derived memory store intent_nodes")
    assert resolution.parameters == {"store": "intent_nodes", "stores": [entry.table for entry in selected_stores("intent_nodes")]}
    ac, app, _ = client
    key = await _pair(ac, app)
    fact = await _fact(app)
    proof = await _challenge(ac, app, key, "forget owner-derived memory store owner_facts", "untrusted-erase")
    body = _command(app, text="forget owner-derived memory store owner_facts", idem="untrusted-erase",
                    expires=int(time.time()) + 10, proof=proof, no_stale=True, context_trust="UNTRUSTED")
    result = await ac.post("/v1/commands", json=body)
    assert result.json()["status"] in {"denied", "rejected_untrusted"}
    assert await app.state.store.fetchone("SELECT fact_id FROM owner_facts WHERE fact_id=?", (fact.fact_id,))


async def test_erasure_rechecks_device_revocation_after_executor_precheck(client, monkeypatch):
    from van_gateway.command import local_executors

    ac, app, _ = client
    key = await _pair(ac, app)
    fact = await _fact(app)
    original = local_executors.erase_memory

    async def revoke_between_precheck_and_lock(store, store_id, command_id, **kwargs):
        await store.execute("UPDATE devices SET revoked_at_unix=? WHERE device_id=?", (int(time.time()), "dev-erasure"))
        return await original(store, store_id, command_id, **kwargs)

    monkeypatch.setattr(local_executors, "erase_memory", revoke_between_precheck_and_lock)
    body, result = await _approve(ac, app, key, "forget owner-derived memory store owner_facts", "erase-racing-revoke")
    assert result["status"] == "denied", result
    execution = await app.state.store.fetchone("SELECT error_code FROM action_executions WHERE execution_id=?", (result["execution_id"],))
    assert execution["error_code"] == "memory_erasure_device_revoked"
    assert await app.state.store.fetchone("SELECT fact_id FROM owner_facts WHERE fact_id=?", (fact.fact_id,))
    assert not await app.state.store.fetchone("SELECT value FROM runtime_meta WHERE key=?", ("memory_erasure_witness:" + body["command_id"],))


async def test_erasure_rechecks_actual_clock_after_waiting_for_write_lock(client, monkeypatch):
    from van_gateway.context import memory_erasure

    ac, app, _ = client
    key = await _pair(ac, app)
    fact = await _fact(app)
    monkeypatch.setattr(memory_erasure, "_now_ms", lambda: int(time.time() * 1000) + 60_000)
    body, result = await _approve(ac, app, key, "forget owner-derived memory store owner_facts", "erase-racing-expiry")
    assert result["status"] == "denied", result
    execution = await app.state.store.fetchone("SELECT error_code FROM action_executions WHERE execution_id=?", (result["execution_id"],))
    assert execution["error_code"] == "memory_erasure_authority_expired"
    assert await app.state.store.fetchone("SELECT fact_id FROM owner_facts WHERE fact_id=?", (fact.fact_id,))
    assert not await app.state.store.fetchone("SELECT value FROM runtime_meta WHERE key=?", ("memory_erasure_witness:" + body["command_id"],))


async def test_expiry_during_erasure_rolls_back_the_delete_and_cache_revision(client, monkeypatch):
    from van_gateway.context import memory_erasure

    ac, app, _ = client
    key = await _pair(ac, app)
    fact = await _fact(app)
    revision = await app.state.owner_runtime.context.kernel_revision()
    calls = 0

    def advancing_clock():
        nonlocal calls
        calls += 1
        return int(time.time() * 1000) + (60_000 if calls >= 4 else 0)

    monkeypatch.setattr(memory_erasure, "_now_ms", advancing_clock)
    body, result = await _approve(ac, app, key, "forget owner-derived memory store owner_facts", "erase-expiry-mid-write")
    assert result["status"] == "denied", result
    assert calls >= 4
    assert await app.state.store.fetchone("SELECT fact_id FROM owner_facts WHERE fact_id=?", (fact.fact_id,))
    assert await app.state.owner_runtime.context.kernel_revision() == revision
    assert not await app.state.store.fetchone("SELECT value FROM runtime_meta WHERE key=?", ("memory_erasure_witness:" + body["command_id"],))
