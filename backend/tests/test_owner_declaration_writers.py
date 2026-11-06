"""Real owner ingress: bounded declarations, device proof, session and fresh target.

These tests exercise persisted rows through create_app, including refusals that
would be invisible with a minimal router or a direct store method test.
"""

from __future__ import annotations

import json

import pytest
import pytest_asyncio

from test_device_proof_enforcement import (
    INTERNAL, _base_headers, _bind, _paired, _proof_headers,
    _settings, client as owner_client_fixture,  # noqa: F401
)
from van_gateway.understanding.memory import VocabularyEntry

pytestmark = pytest.mark.asyncio
VOCAB = "/v1/understanding/vocabulary"
COMPLEMENT = "/v1/understanding/complement/preferences"


async def _request(ac, enrolled, key, method, target, body):
    raw = json.dumps(body).encode()
    return await ac.request(method, target, content=raw, headers={
        **_base_headers(enrolled), "Content-Type": "application/json",
        **_proof_headers(key, method=method, path=target,
            device_id=enrolled.device.device_id, body=raw),
    })


@pytest_asyncio.fixture
async def owner(owner_client_fixture):
    ac, app = owner_client_fixture
    enrolled = await _paired(app)
    key = await _bind(app, enrolled.device.device_id)
    opened = await _request(ac, enrolled, key, "POST", "/v1/session/open", {})
    assert opened.status_code == 200, opened.text
    session = {k: opened.json()[k] for k in ("van_session_id", "session_epoch")}
    return ac, app, enrolled, key, session


def _vocabulary(session, **changes):
    return {**session, "term": "  Full   Implementation  ", "owner_meaning": "Every promised function works.",
        "system_operationalization": "Connect each required feature to its verified effect.",
        "examples": ["A provider failure is visible."], "anti_examples": ["Interfaces alone."],
        "project_id": " VAN ", **changes}


def _preference(session, **changes):
    return {**session, "domain": " Trading.Analysis ",
        "preferred_collaboration_pattern": "State uncertainty and ask before changing an assumption.", **changes}


async def test_vocabulary_normalized_exact_project_persisted_and_owner_confirmed(owner):
    ac, app, enrolled, key, session = owner
    grants_before = [dict(row) for row in await app.state.store.fetchall("SELECT * FROM capability_grants ORDER BY grant_id")]
    saved = await _request(ac, enrolled, key, "PUT", VOCAB, _vocabulary(session))
    assert saved.status_code == 200, saved.text
    value = saved.json()
    assert value["status"] == "SAVED" and value["execution_grant"] is False
    assert value["entry"]["term"] == "full implementation" and value["entry"]["project_id"] == "van"
    assert value["entry"]["confidence"] == 1 and value["entry"]["is_operational"] is True
    assert value["provenance"]["state"] == "OWNER_CONFIRMED"
    assert value["provenance"]["device_id"] == enrolled.device.device_id
    assert value["provenance"]["van_session_id"] == session["van_session_id"]
    assert value["entry"]["evidence_refs"] == [value["provenance"]["evidence_ref"]]
    observed = await ac.get(VOCAB, params={"term": "FULL IMPLEMENTATION", "project_id": "van"}, headers=_base_headers(enrolled))
    assert observed.status_code == 200 and observed.json() == value
    assert observed.headers["cache-control"] == "no-store"
    row = await app.state.store.fetchone("SELECT * FROM shared_vocabulary WHERE term='full implementation' AND project_id='van'")
    assert row["owner_meaning"] == value["entry"]["owner_meaning"]
    resolved = await app.state.understanding_api.vocabulary.resolve("Full   Implementation", project_id="van")
    assert resolved.owner_meaning == value["entry"]["owner_meaning"]
    aggregate = (await ac.get("/v1/understanding", headers=_base_headers(enrolled))).json()
    assert any(v["term"] == "full implementation" for v in aggregate["shared_vocabulary"])
    assert not await app.state.store.fetchone("SELECT grant_id FROM permission_grants")
    assert [dict(row) for row in await app.state.store.fetchall("SELECT * FROM capability_grants ORDER BY grant_id")] == grants_before


async def test_exact_scope_never_falls_back_to_global_and_update_has_new_provenance(owner):
    ac, app, enrolled, key, session = owner
    first = await _request(ac, enrolled, key, "PUT", VOCAB, _vocabulary(session, project_id=None))
    assert first.status_code == 200, first.text
    missing = await ac.get(VOCAB, params={"term": "full implementation", "project_id": "van"}, headers=_base_headers(enrolled))
    assert missing.status_code == 404
    updated = await _request(ac, enrolled, key, "PUT", VOCAB, _vocabulary(session, project_id=None, owner_meaning="All declared functions and their error behavior."))
    assert updated.status_code == 200, updated.text
    assert updated.json()["provenance"]["write_id"] != first.json()["provenance"]["write_id"]
    assert (await ac.get(VOCAB, headers=_base_headers(enrolled))).json()["entries"] == [updated.json()]
    assert len(await app.state.understanding_api.vocabulary.all_terms()) == 1


async def test_preference_upsert_returns_actual_id_preserves_hypotheses_without_confirming_them(owner):
    ac, app, enrolled, key, session = owner
    complement = app.state.understanding_api.complement
    existing_id = await complement.upsert(domain="trading.analysis", owner_strength="task hypothesis",
        owner_vulnerability_candidate="task pattern candidate", van_strength="unverified ability",
        confidence=0.2, evidence_refs=["task-observation://fixture"])
    same_id = await complement.upsert(domain="trading.analysis", owner_strength="task hypothesis",
        owner_vulnerability_candidate="task pattern candidate", van_strength="unverified ability",
        confidence=0.2, evidence_refs=["task-observation://fixture"])
    assert same_id == existing_id
    saved = await _request(ac, enrolled, key, "PUT", COMPLEMENT, _preference(session))
    assert saved.status_code == 200, saved.text
    value = saved.json()
    assert value["entry"]["entry_id"] == existing_id and value["entry"]["domain"] == "trading.analysis"
    assert set(value["entry"]) == {"entry_id", "domain", "preferred_collaboration_pattern", "evidence_refs"}
    assert value["provenance"]["state"] == "OWNER_CONFIRMED"
    raw = await app.state.store.fetchone("SELECT * FROM cognitive_complement_map WHERE entry_id=?", (existing_id,))
    assert raw["owner_strength"] == "task hypothesis" and raw["confidence"] == 0.2
    assert json.loads(raw["evidence_refs_json"]) == ["task-observation://fixture"]
    reread = await ac.get(COMPLEMENT, params={"domain": " TRADING.ANALYSIS "}, headers=_base_headers(enrolled))
    assert reread.json() == value
    aggregate = (await ac.get("/v1/understanding", headers=_base_headers(enrolled))).json()
    assert aggregate["cognitive_complement"][0]["preferred_collaboration_pattern"] == value["entry"]["preferred_collaboration_pattern"]


@pytest.mark.parametrize("target,factory,changes", [
    (VOCAB, _vocabulary, {"term": " "}), (VOCAB, _vocabulary, {"term": "x" * 129}),
    (VOCAB, _vocabulary, {"term": "word\x00"}), (VOCAB, _vocabulary, {"owner_meaning": "x" * 4001}),
    (VOCAB, _vocabulary, {"examples": ["x"] * 17}), (VOCAB, _vocabulary, {"anti_examples": [""]}),
    (VOCAB, _vocabulary, {"confidence": 1}), (VOCAB, _vocabulary, {"evidence_refs": ["owner-approved://forged"]}),
    (VOCAB, _vocabulary, {"project_id": "../van"}), (VOCAB, _vocabulary, {"session_epoch": True}),
    (COMPLEMENT, _preference, {"domain": "*"}), (COMPLEMENT, _preference, {"domain": "a..b"}),
    (COMPLEMENT, _preference, {"domain": "a." * 8 + "a"}), (COMPLEMENT, _preference, {"preferred_collaboration_pattern": " "}),
    (COMPLEMENT, _preference, {"owner_strength": "invented"}),
    (COMPLEMENT, _preference, {"owner_vulnerability_candidate": "diagnosis"}),
    (COMPLEMENT, _preference, {"van_strength": "self-awarded"}),
    (COMPLEMENT, _preference, {"execution_grant": True}),
])
async def test_strict_bounds_and_no_inference_or_authority_fields(owner, target, factory, changes):
    ac, app, enrolled, key, session = owner
    denied = await _request(ac, enrolled, key, "PUT", target, factory(session, **changes))
    assert denied.status_code == 422, denied.text
    assert not await app.state.store.fetchone("SELECT term FROM shared_vocabulary")
    assert not await app.state.store.fetchone("SELECT entry_id FROM cognitive_complement_map")


async def test_unknown_project_refused_and_no_declaration_written(owner):
    ac, app, enrolled, key, session = owner
    denied = await _request(ac, enrolled, key, "PUT", VOCAB, _vocabulary(session, project_id="not_registered"))
    assert denied.status_code == 404 and denied.json()["detail"] == "owner_memory_project_not_known"
    assert not await app.state.store.fetchone("SELECT term FROM shared_vocabulary")


@pytest.mark.parametrize("target,factory", [(VOCAB, _vocabulary), (COMPLEMENT, _preference)])
async def test_owner_proof_required_internal_token_cannot_substitute_or_read(owner, target, factory):
    ac, app, enrolled, key, session = owner
    body = factory(session)
    denied = await ac.put(target, json=body, headers={**_base_headers(enrolled), "X-Van-Internal-Token": INTERNAL})
    assert denied.status_code == 401 and denied.json()["detail"] == "device_proof_required"
    internal = await ac.put(target, json=body, headers={"X-Van-Internal-Token": INTERNAL})
    assert internal.status_code == 401
    read = await ac.get(target, headers={"X-Van-Internal-Token": INTERNAL})
    assert read.status_code == 401


async def test_unbound_legacy_device_cannot_claim_owner_authored_preference(owner_client_fixture):
    ac, app = owner_client_fixture
    enrolled = await _paired(app)
    session, _ = await app.state.van_sessions.open(device_id=enrolled.device.device_id)
    denied = await ac.put(COMPLEMENT, json=_preference({"van_session_id": session.van_session_id, "session_epoch": 1}), headers=_base_headers(enrolled))
    assert denied.status_code == 403 and denied.json()["detail"] == "owner_bound_device_proof_required"
    read = await ac.get(COMPLEMENT, headers=_base_headers(enrolled))
    assert read.status_code == 403 and read.json()["detail"] == "owner_bound_device_required"


@pytest.mark.parametrize("change,expected", [
    ({"session_epoch": 2}, "owner_memory_session_epoch_stale"),
    ({"van_session_id": "vhs_unknown"}, "owner_memory_session_device_mismatch"),
])
async def test_current_exact_session_binding_required(owner, change, expected):
    ac, app, enrolled, key, session = owner
    denied = await _request(ac, enrolled, key, "PUT", COMPLEMENT, _preference(session, **change))
    assert denied.status_code in {403, 409} and denied.json()["detail"] == expected
    assert not await app.state.store.fetchone("SELECT entry_id FROM cognitive_complement_map")


async def test_foreign_session_and_closed_session_cannot_write(owner):
    ac, app, enrolled, key, session = owner
    other = await _paired(app, "other-phone")
    foreign, _ = await app.state.van_sessions.open(device_id=other.device.device_id)
    denied = await _request(ac, enrolled, key, "PUT", COMPLEMENT, _preference(session, van_session_id=foreign.van_session_id))
    assert denied.status_code == 403
    await app.state.van_sessions.close(session["van_session_id"])
    denied = await _request(ac, enrolled, key, "PUT", COMPLEMENT, _preference(session))
    assert denied.status_code == 409 and denied.json()["detail"] == "owner_memory_session_not_active"


async def test_signed_body_cannot_be_changed_or_replayed(owner):
    ac, app, enrolled, key, session = owner
    body = json.dumps(_preference(session)).encode()
    headers = {**_base_headers(enrolled), "Content-Type": "application/json", **_proof_headers(key,
        method="PUT", path=COMPLEMENT, device_id=enrolled.device.device_id, body=body)}
    altered = await ac.put(COMPLEMENT, content=body.replace(b"State uncertainty", b"Never show uncertainty"), headers=headers)
    assert altered.status_code == 401 and altered.json()["detail"] == "device_proof_invalid"
    saved = await ac.put(COMPLEMENT, content=body, headers=headers)
    assert saved.status_code == 200, saved.text
    replayed = await ac.put(COMPLEMENT, content=body, headers=headers)
    assert replayed.status_code == 401 and replayed.json()["detail"] == "device_proof_replayed"


async def test_revocation_between_ingress_and_write_is_rechecked_under_transaction(owner, monkeypatch):
    ac, app, enrolled, key, session = owner
    declarations = app.state.understanding_api.owner_declarations
    save = declarations.save
    async def revoke_then_save(kind, body, request):
        await app.state.store.execute("UPDATE owner_device_bindings SET status='REVOKED' WHERE device_id=?", (enrolled.device.device_id,))
        return await save(kind, body, request)
    monkeypatch.setattr(declarations, "save", revoke_then_save)
    denied = await _request(ac, enrolled, key, "PUT", COMPLEMENT, _preference(session))
    assert denied.status_code == 403 and denied.json()["detail"] == "owner_bound_device_required"
    assert not await app.state.store.fetchone("SELECT entry_id FROM cognitive_complement_map")


async def test_existing_inferred_or_changed_content_never_read_back_as_owner_confirmed(owner):
    ac, app, enrolled, key, session = owner
    await app.state.understanding_api.vocabulary.define(VocabularyEntry(term="inferred", owner_meaning="guess", system_operationalization="guess"))
    observed = await ac.get(VOCAB, params={"term": "inferred"}, headers=_base_headers(enrolled))
    assert observed.json()["provenance"]["state"] == "UNCONFIRMED" and observed.json()["status"] == "OBSERVED"
    saved = await _request(ac, enrolled, key, "PUT", COMPLEMENT, _preference(session))
    assert saved.status_code == 200
    await app.state.store.execute("UPDATE cognitive_complement_map SET preferred_collaboration_pattern='an inference' WHERE domain='trading.analysis'")
    observed = await ac.get(COMPLEMENT, params={"domain": "trading.analysis"}, headers=_base_headers(enrolled))
    assert observed.json()["provenance"]["state"] == "UNCONFIRMED" and observed.json()["entry"]["evidence_refs"] == []


async def test_forgetting_complement_or_vocabulary_removes_values_and_declaration_witnesses(owner):
    ac, app, enrolled, key, session = owner
    assert (await _request(ac, enrolled, key, "PUT", VOCAB, _vocabulary(session))).status_code == 200
    assert (await _request(ac, enrolled, key, "PUT", COMPLEMENT, _preference(session))).status_code == 200
    assert (await app.state.owner_memory.inventory())["stores"]["cognitive_complement_map"]["rows"] == 1
    assert await app.state.owner_memory.forget_store("cognitive_complement_map") == 1
    assert not await app.state.store.fetchone("SELECT key FROM runtime_meta WHERE key LIKE 'owner_memory_declaration:complement:%'")
    assert await app.state.store.fetchone("SELECT key FROM runtime_meta WHERE key LIKE 'owner_memory_declaration:vocabulary:%'")
    assert (await ac.get(COMPLEMENT, params={"domain": "trading.analysis"}, headers=_base_headers(enrolled))).status_code == 404
    await app.state.owner_memory.forget_all()
    assert not await app.state.store.fetchone("SELECT key FROM runtime_meta WHERE key LIKE 'owner_memory_declaration:%'")

