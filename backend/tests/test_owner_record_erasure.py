"""Actual signed A4 command erases precisely reviewed records and proves the effect."""
from __future__ import annotations

import time

import pytest

from test_owner_memory_erasure import client, _settings, _pair, _fact, _approve, _challenge, _command  # noqa: F401
from van_gateway.context.memory_erasure import memory_erasure_readback
from van_gateway.storage.db import Store
from van_gateway.understanding.records import OwnerRecords

pytestmark = pytest.mark.asyncio


async def test_actual_record_a4_erasure_retains_unselected_record_and_retry_receipt(client):
    ac, app, hermes = client
    key = await _pair(ac, app)
    selected = await _fact(app)
    other = await app.state.owner_fact_author.state(device_id="dev-erasure", subject="owner",
        predicate="other-memory", value="keep-this-record")
    records = OwnerRecords(app.state.store)
    page = await records.list("owner_facts")
    target = next(record for record in page["records"] if any(field["name"] == "fact_id" and field["value"] == selected.fact_id for field in record["fields"]))
    plan = await records.erasure_plan("owner_facts", target["record_id"])
    body, result = await _approve(ac, app, key, plan["command_text"], "erase-one-fact")
    assert result["status"] == "accepted", result
    assert result["local_execution"]["verification_state"] == "VERIFIED_SUCCESS"
    assert result["local_execution"]["removed_counts"] == {"owner_facts": 1}
    assert not await app.state.store.fetchone("SELECT fact_id FROM owner_facts WHERE fact_id=?", (selected.fact_id,))
    assert await app.state.store.fetchone("SELECT fact_id FROM owner_facts WHERE fact_id=?", (other.fact_id,))
    observed = await memory_erasure_readback(app.state.store, "owner_facts", body["command_id"],
        record_id=target["record_id"], expected_sha256=target["revision_sha256"])
    assert observed["scope_empty"] and observed["captured_ids_absent"] and observed["owner_approved_command_bound"]
    assert observed["evidence_refs"]
    assert (await ac.post("/v1/commands", json=body)).json() == result
    assert hermes["create_run"] == 0


async def test_changed_record_after_approval_refuses_without_any_erasure(client):
    ac, app, _ = client
    key = await _pair(ac, app)
    fact = await _fact(app)
    target = (await OwnerRecords(app.state.store).list("owner_facts"))["records"][0]
    text = target["erasure"]["command_text"]
    proof = await _challenge(ac, app, key, text, "stale-record-review")
    await app.state.store.execute("UPDATE owner_facts SET value_json='\"new-value\"' WHERE fact_id=?", (fact.fact_id,))
    import time
    body = _command(app, text=text, idem="stale-record-review", expires=int(time.time())+10, proof=proof, no_stale=True)
    response = await ac.post("/v1/commands", json=body)
    result = response.json()
    assert result["status"] == "denied", result
    execution = await app.state.store.fetchone("SELECT error_code FROM action_executions WHERE execution_id=?", (result["execution_id"],))
    assert execution["error_code"] == "memory_record_revision_stale"
    assert await app.state.store.fetchone("SELECT fact_id FROM owner_facts WHERE fact_id=?", (fact.fact_id,))
    assert not await app.state.store.fetchone("SELECT value FROM runtime_meta WHERE key=?", ("memory_erasure_witness:" + body["command_id"],))


async def test_exact_intent_record_closure_preserves_other_node(client):
    ac, app, _ = client
    key = await _pair(ac, app)
    store = app.state.store
    now = int(time.time() * 1000)
    for intent in ("selected", "other"):
        await store.execute("INSERT INTO intent_nodes(intent_id,owner_goal,first_observed_ms,latest_observed_ms) VALUES(?,?,?,?)", (intent, "test direction", now, now))
    await store.execute("INSERT INTO intent_edges(edge_id,from_intent_id,to_intent_id,edge_type,created_at_ms) VALUES('link','selected','other','SUPPORTS',1)")
    await store.execute("INSERT INTO intent_missions VALUES('selected','old-work',1)")
    records = OwnerRecords(store)
    target = next(record for record in (await records.list("intent_nodes"))["records"] if any(field["name"] == "intent_id" and field["value"] == "selected" for field in record["fields"]))
    plan = await records.erasure_plan("intent_nodes", target["record_id"])
    assert {item["store"]: item["count"] for item in plan["affected_records"]} == {"intent_edges": 1, "intent_missions": 1, "intent_nodes": 1}
    _, result = await _approve(ac, app, key, target["erasure"]["command_text"], "erase-one-intent")
    assert result["status"] == "accepted", result
    assert result["local_execution"]["removed_counts"] == {"intent_edges": 1, "intent_missions": 1, "intent_nodes": 1}
    assert not await store.fetchone("SELECT intent_id FROM intent_nodes WHERE intent_id='selected'")
    assert await store.fetchone("SELECT intent_id FROM intent_nodes WHERE intent_id='other'")


async def test_new_dependent_link_after_review_refuses_expanded_record_scope(client):
    ac, app, _ = client
    key = await _pair(ac, app)
    store = app.state.store
    now = int(time.time() * 1000)
    await store.execute("INSERT INTO intent_nodes(intent_id,owner_goal,first_observed_ms,latest_observed_ms) VALUES('selected','test direction',?,?)", (now, now))
    target = (await OwnerRecords(store).list("intent_nodes"))["records"][0]
    text = target["erasure"]["command_text"]
    proof = await _challenge(ac, app, key, text, "changed-intent-links")
    await store.execute("INSERT INTO intent_missions VALUES('selected','new-work',?)", (now,))
    body = _command(app, text=text, idem="changed-intent-links", expires=int(time.time())+10, proof=proof, no_stale=True)
    result = (await ac.post("/v1/commands", json=body)).json()
    assert result["status"] == "denied", result
    execution = await store.fetchone("SELECT error_code FROM action_executions WHERE execution_id=?", (result["execution_id"],))
    assert execution["error_code"] == "memory_record_revision_stale"
    assert await store.fetchone("SELECT intent_id FROM intent_nodes WHERE intent_id='selected'")
    assert await store.fetchone("SELECT mission_id FROM intent_missions WHERE intent_id='selected'")
    assert not await store.fetchone("SELECT value FROM runtime_meta WHERE key=?", ("memory_erasure_witness:" + body["command_id"],))


async def test_exact_cognitive_record_erasure_removes_only_explicitly_linked_growth(client):
    ac, app, _ = client
    key = await _pair(ac, app)
    store = app.state.store
    now = int(time.time() * 1000)
    for assertion in ("selected", "other"):
        await store.execute("INSERT INTO owner_cognitive_model(assertion_id,owner_principal_id,field,value,created_at_ms,updated_at_ms) VALUES(?,'owner','preferred format','test',?,?)", (assertion, now, now))
        await store.execute("INSERT INTO symbiotic_growth(change_id,observed_pattern,previous_behavior,new_behavior,reason,evidence_refs_json,created_at_ms) VALUES(?,'owner correction','before','after','owner correction',?,?)", (assertion, Store.dumps(["assertion:"+assertion]), now))
    records = OwnerRecords(store)
    target = next(record for record in (await records.list("owner_cognitive_model"))["records"] if any(field["name"] == "assertion_id" and field["value"] == "selected" for field in record["fields"]))
    plan = await records.erasure_plan("owner_cognitive_model", target["record_id"])
    assert {item["store"]: item["count"] for item in plan["affected_records"]} == {"symbiotic_growth": 1, "owner_cognitive_model": 1}
    body, result = await _approve(ac, app, key, plan["command_text"], "erase-one-cognitive-record")
    assert result["status"] == "accepted", result
    assert result["local_execution"]["removed_counts"] == {"symbiotic_growth": 1, "owner_cognitive_model": 1}
    assert not await store.fetchone("SELECT assertion_id FROM owner_cognitive_model WHERE assertion_id='selected'")
    assert not await store.fetchone("SELECT change_id FROM symbiotic_growth WHERE change_id='selected'")
    assert await store.fetchone("SELECT assertion_id FROM owner_cognitive_model WHERE assertion_id='other'")
    assert await store.fetchone("SELECT change_id FROM symbiotic_growth WHERE change_id='other'")
    recovered = await memory_erasure_readback(Store(store.path), "owner_cognitive_model", body["command_id"],
        record_id=target["record_id"], expected_sha256=target["revision_sha256"])
    assert recovered["scope_empty"] and recovered["captured_ids_absent"] and recovered["owner_approved_command_bound"]
