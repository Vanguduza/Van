"""Exact owner record readback, privacy screening and stale destructive selection."""
from __future__ import annotations

import json

import pytest

from test_owner_declaration_writers import owner, owner_client_fixture, _base_headers  # noqa: F401
from test_device_proof_enforcement import _settings  # noqa: F401
from van_gateway.context.forget import FORGETTABLE
from van_gateway.understanding.records import OwnerRecords, PRIMARY_KEYS, record_identity

pytestmark = pytest.mark.asyncio


async def test_actual_record_routes_inspect_export_and_exact_plan(owner):
    ac, app, enrolled, _, _ = owner
    fact = await app.state.owner_fact_author.state(device_id=enrolled.device.device_id,
        subject="owner", predicate="timezone", value={"zone": "Africa/Harare", "access_token": "secret-value"})
    listed = await ac.get("/v1/context/records?store=owner_facts&limit=1", headers=_base_headers(enrolled))
    assert listed.status_code == 200, listed.text
    record = listed.json()["records"][0]
    assert record["source_class"] == "OWNER_DECLARED"
    assert record["record_id"].startswith("mr_") and len(record["record_id"]) == 67
    assert "secret-value" not in json.dumps(record)
    assert fact.fact_id not in record["record_id"]
    target = f"/v1/context/records/owner_facts/{record['record_id']}"
    detail = await ac.get(target, headers=_base_headers(enrolled))
    assert detail.status_code == 200 and detail.json() == record
    export = await ac.get(target + "/export", headers=_base_headers(enrolled))
    assert export.json() == record and export.headers["cache-control"] == "no-store"
    plan = (await ac.get(target + "/erasure-plan", headers=_base_headers(enrolled))).json()
    assert plan["action_class"] == "A4" and plan["revision_sha256"] == record["revision_sha256"]
    assert plan["command_text"].endswith(record["revision_sha256"])
    assert "audit" in plan["kept_deliberately"]
    assert await app.state.store.fetchone("SELECT fact_id FROM owner_facts WHERE fact_id=?", (fact.fact_id,))


async def test_record_routes_refuse_bad_scope_and_other_owner(owner):
    ac, app, enrolled, _, _ = owner
    for query in ("store=audit", "store=devices", "store=owner_facts&limit=101", "store=owner_facts&cursor=-1"):
        response = await ac.get("/v1/context/records?" + query, headers=_base_headers(enrolled))
        assert response.status_code == 422
    await app.state.store.execute("INSERT INTO owner_cognitive_model(assertion_id,owner_principal_id,field,value,created_at_ms,updated_at_ms) VALUES('elsewhere','other','values','private-other',1,1)")
    other = await app.state.store.fetchone("SELECT * FROM owner_cognitive_model WHERE assertion_id='elsewhere'")
    other_id = record_identity("owner_cognitive_model", other)
    response = await ac.get(f"/v1/context/records/owner_cognitive_model/{other_id}", headers=_base_headers(enrolled))
    assert response.status_code == 404
    assert (await ac.get("/v1/context/records?store=owner_facts")).status_code == 401


async def test_pagination_and_composite_key_records_survive_restart(owner):
    _, app, _, _, _ = owner
    store = app.state.store
    for scope in ("", "van", "dial"):
        await store.execute("INSERT INTO shared_vocabulary(term,project_id,owner_meaning,system_operationalization,created_at_ms,updated_at_ms) VALUES('complete',?,'working functions','verify effects',1,1)", (scope,))
    records = OwnerRecords(store)
    first = await records.list("shared_vocabulary", limit=2)
    second = await OwnerRecords(store).list("shared_vocabulary", limit=2, cursor=first["next_cursor"])
    assert first["total"] == 3 and first["truncated"]
    ids = {record["record_id"] for record in first["records"] + second["records"]}
    assert len(ids) == 3 and second["next_cursor"] is None
    assert await OwnerRecords(store).exact("shared_vocabulary", first["records"][0]["record_id"]) == first["records"][0]
    for entry in FORGETTABLE:
        info = await store.fetchall(f"PRAGMA table_info({entry.table})")
        actual = tuple(row["name"] for row in sorted(info, key=lambda item: item["pk"]) if row["pk"])
        assert actual == PRIMARY_KEYS[entry.table]


async def test_record_revision_changes_for_dependent_links(owner):
    _, app, _, _, _ = owner
    store = app.state.store
    for intent in ("a", "b"):
        await store.execute("INSERT INTO intent_nodes(intent_id,owner_goal,first_observed_ms,latest_observed_ms) VALUES(?,?,1,1)", (intent, "test-goal"))
    records = OwnerRecords(store)
    first = (await records.list("intent_nodes"))["records"][0]
    await store.execute("INSERT INTO intent_edges(edge_id,from_intent_id,to_intent_id,edge_type,created_at_ms) VALUES('new-link','a','b','SUPPORTS',1)")
    later = await records.exact("intent_nodes", first["record_id"])
    assert first["record_id"] == later["record_id"]
    assert first["revision_sha256"] != later["revision_sha256"]


async def test_actual_learning_producers_no_data_and_independent_degraded_state(owner, monkeypatch):
    ac, app, enrolled, _, _ = owner
    endpoint = "/v1/understanding/learning/producers"
    initial = await ac.get(endpoint, headers=_base_headers(enrolled))
    assert initial.status_code == 200, initial.text
    assert all(producer["status"] == "NO_DATA" for producer in initial.json()["producers"])
    assert all(isinstance(producer["comparisons"], int) for producer in initial.json()["producers"])
    assert initial.json()["execution_grant"] is False
    async def unavailable(**_kwargs):
        raise RuntimeError("private database diagnostic")
    monkeypatch.setattr(app.state.understanding_api.observed_learning, "decisions", unavailable)
    observed = await ac.get(endpoint, headers=_base_headers(enrolled))
    by_id = {producer["id"]: producer for producer in observed.json()["producers"]}
    assert by_id["decision-patterns"]["status"] == "DEGRADED"
    assert by_id["decision-patterns"]["comparisons"] is None
    assert by_id["external-contradictions"]["status"] == "NO_DATA"
    assert "private database diagnostic" not in observed.text
    paths = app.openapi()["paths"]
    assert paths[endpoint]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("LearningProducersView")
