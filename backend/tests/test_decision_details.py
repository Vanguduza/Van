"""Typed judgments survive lost replies without becoming action authorization."""
from __future__ import annotations

import asyncio
import hashlib
import json
import time

import pytest
from pydantic import ValidationError

from conftest_automation import make_store, enroll_device
from van_gateway.attention.engine import AttentionEngine
from van_gateway.decisions.models import DecisionAnswer, DecisionCreate
from van_gateway.decisions.service import DecisionError, DecisionService
from van_gateway.storage.db import Store


@pytest.fixture
async def judgments(tmp_path):
    store = await make_store(tmp_path)
    await enroll_device(store, "owner")
    await store.execute(
        "INSERT INTO missions(mission_id,owner_principal_id,origin,origin_channel,title,goal,state,"
        "authority_envelope_json,created_at_ms,updated_at_ms) VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("mission", "device:owner", "OWNER_UI", "UI", "Proposal", "Choose", "RUNNING", "{}", 1, 1),
    )
    await store.execute("INSERT INTO hermes_run_bindings(hermes_run_id,mission_id,bound_at_ms) VALUES (?,?,?)", ("run", "mission", 1))
    return DecisionService(store, AttentionEngine(store))


def proposal(**changes):
    body = dict(title="Choose the preferred approach", body="Which option should be proposed next?",
                mission_id="mission", request_id="create-proposal-1",
                choices=[{"id": "brief", "label": "Brief"}, {"id": "detailed", "label": "Detailed"}])
    body.update(changes)
    return DecisionCreate(**body)


def answer(**changes):
    body = dict(choice_id="brief", expected_revision=1, request_id="owner-answer-1", note="Exact owner reason.\n  Keep it.")
    body.update(changes)
    return DecisionAnswer(**body)


async def test_actual_details_answer_and_readback_preserve_owner_choice_without_grants(judgments):
    created = await judgments.escalate(proposal(blocking=False))
    assert created.status.value == "OPEN" and not created.blocking
    assert created.expires_at_unix > int(time.time()) and created.revision == 1
    initial = await judgments.store.fetchone("SELECT state,authority_envelope_json FROM missions WHERE mission_id='mission'")
    resolved = await judgments.answer(created.id, answer(), owner_device_id="owner")
    assert resolved.status.value == "ANSWERED" and resolved.selected_choice_id == "brief"
    assert resolved.answer_note == answer().note and resolved.resolution_request_id == "owner-answer-1"
    assert not resolved.grants_action_authority and (await judgments.get(created.id)) == resolved
    assert tuple(await judgments.store.fetchone("SELECT state,authority_envelope_json FROM missions WHERE mission_id='mission'")) == tuple(initial)
    assert await judgments.store.fetchone("SELECT 1 FROM runtime_meta WHERE key LIKE 'approval:%'") is None
    assert await judgments.store.fetchone("SELECT 1 FROM action_executions") is None
    observed = await judgments.store.fetchone("SELECT * FROM decision_fingerprints")
    assert observed["owner_choice"] == "brief" and observed["owner_stated_reason"] == answer().note
    assert observed["inferred_reason"] is None


async def test_create_and_answer_lost_reply_recover_after_restart_without_growth(judgments):
    first = await judgments.escalate(proposal(), producer_run_id="run")
    accepted = await judgments.answer(first.id, answer(), owner_device_id="owner")
    store = Store(judgments.store.path)
    restarted = DecisionService(store, AttentionEngine(store))
    assert await restarted.escalate(proposal(), producer_run_id="run") == accepted
    assert await restarted.answer(first.id, answer(), owner_device_id="owner") == accepted
    assert len(await store.fetchall("SELECT * FROM decisions")) == 1
    assert len(await store.fetchall("SELECT * FROM decision_fingerprints")) == 1


async def test_changed_create_or_resolution_body_cannot_replace_original(judgments):
    created = await judgments.escalate(proposal())
    with pytest.raises(DecisionError, match="decision_create_request_conflict"):
        await judgments.escalate(proposal(body="Changed"))
    accepted = await judgments.answer(created.id, answer())
    for changed in (dict(choice_id="detailed"), dict(note="Different"), dict(expected_revision=2)):
        with pytest.raises(DecisionError, match="decision_answer_request_conflict"):
            await judgments.answer(created.id, answer(**changed))
    assert await judgments.get(created.id) == accepted


async def test_concurrent_choices_have_one_durable_winner(judgments):
    created = await judgments.escalate(proposal())
    results = await asyncio.gather(
        judgments.answer(created.id, answer(), owner_device_id="owner"),
        judgments.answer(created.id, answer(choice_id="detailed", request_id="owner-answer-2"), owner_device_id="owner"),
        return_exceptions=True,
    )
    accepted = [r for r in results if not isinstance(r, Exception)]
    refused = [r for r in results if isinstance(r, DecisionError)]
    assert len(accepted) == len(refused) == 1 and refused[0].reason == "decision_already_resolved"
    assert await judgments.get(created.id) == accepted[0]
    assert len(await judgments.store.fetchall("SELECT * FROM decision_fingerprints")) == 1


@pytest.mark.parametrize("changes,error", [({"expected_revision": 2}, "decision_revision_stale"),
                                           ({"choice_id": "unlisted"}, "decision_choice_unknown")])
async def test_unlisted_or_stale_choices_leave_question_open(judgments, changes, error):
    created = await judgments.escalate(proposal())
    with pytest.raises(DecisionError, match=error):
        await judgments.answer(created.id, answer(**changes))
    assert (await judgments.get(created.id)).status.value == "OPEN"


async def test_deadline_fences_answer_and_handles_attention(judgments, monkeypatch):
    now = int(time.time())
    created = await judgments.escalate(proposal(expires_at_unix=now + 5))
    monkeypatch.setattr("van_gateway.decisions.service.time.time", lambda: now + 5)
    with pytest.raises(DecisionError, match="decision_expired"):
        await judgments.answer(created.id, answer(), owner_device_id="owner")
    expired = await judgments.get(created.id)
    assert expired.status.value == "EXPIRED" and expired.selected_choice_id is None
    assert await judgments.list_open() == []
    assert (await judgments.store.fetchone("SELECT state FROM attention WHERE dedupe_key=?", (f"decision:{created.id}",)))["state"] == "HANDLED"
    assert await judgments.store.fetchone("SELECT 1 FROM decision_fingerprints") is None


async def test_original_accepted_answer_recovers_even_after_deadline(judgments, monkeypatch):
    now = int(time.time())
    created = await judgments.escalate(proposal(expires_at_unix=now + 5))
    accepted = await judgments.answer(created.id, answer())
    monkeypatch.setattr("van_gateway.decisions.service.time.time", lambda: now + 50)
    assert await judgments.answer(created.id, answer()) == accepted


async def test_waiting_answer_rechecks_deadline_after_writer_lock(judgments, monkeypatch):
    now = int(time.time())
    created = await judgments.escalate(proposal(expires_at_unix=now + 5))
    clock = [now]
    monkeypatch.setattr("van_gateway.decisions.service.time.time", lambda: clock[0])
    async with judgments.store.connection() as db:
        await db.execute("BEGIN IMMEDIATE")
        pending = asyncio.create_task(judgments.answer(created.id, answer(), owner_device_id="owner"))
        done, _ = await asyncio.wait({pending}, timeout=0.02)
        assert not done
        clock[0] = now + 5
        await db.commit()
    with pytest.raises(DecisionError, match="decision_expired"):
        await pending
    assert (await judgments.get(created.id)).status.value == "EXPIRED"
    assert await judgments.store.fetchone("SELECT 1 FROM decision_fingerprints") is None


async def test_expiry_attention_publish_failure_recovers_on_later_open_list(judgments, monkeypatch):
    now = int(time.time())
    created = await judgments.escalate(proposal(expires_at_unix=now + 5))
    monkeypatch.setattr("van_gateway.decisions.service.time.time", lambda: now + 5)
    original = judgments.attention.mark_handled
    async def unavailable(item_id):
        raise RuntimeError("attention publish failed")
    monkeypatch.setattr(judgments.attention, "mark_handled", unavailable)
    with pytest.raises(RuntimeError, match="attention publish failed"):
        await judgments.list_open()
    monkeypatch.setattr(judgments.attention, "mark_handled", original)
    assert await judgments.list_open() == []
    assert (await judgments.store.fetchone("SELECT state FROM attention WHERE dedupe_key=?", (f"decision:{created.id}",)))["state"] == "HANDLED"


@pytest.mark.parametrize("value", [True, "1", 1.0])
def test_revision_requires_an_actual_integer(value):
    with pytest.raises(ValidationError):
        answer(expected_revision=value)


@pytest.mark.parametrize("value", ["false", 0, 1, None])
def test_blocking_requires_actual_boolean(value):
    with pytest.raises(ValidationError):
        proposal(blocking=value)


@pytest.mark.parametrize("changes", [dict(choices=[{"id":"same","label":"A"},{"id":"same","label":"B"}]),
                                     dict(choices=[{"id":"only","label":"A"}]),
                                     dict(evidence=[{"ref":"same"},{"ref":"same"}]),
                                     dict(grants_action_authority=True)])
def test_bounded_choices_and_evidence_reject_duplicates_and_caller_authority(changes):
    with pytest.raises(ValidationError):
        proposal(**changes)


async def test_referenced_content_cannot_claim_verified_evidence(judgments):
    created = await judgments.escalate(proposal(evidence=[{"ref":"evidence://claim", "label":"Claimed verified"}]))
    assert created.evidence[0].verification == "REFERENCE_ONLY"
    with pytest.raises(ValidationError):
        proposal(evidence=[{"ref":"evidence://claim","verification":"RECORDED_EVENT"}])


async def test_mission_event_evidence_is_exact_correlated_timeline_not_effect_proof(judgments):
    await judgments.store.execute(
        "INSERT INTO mission_events(event_id,mission_id,event_type,actor,summary,evidence_ref,occurred_at_ms) VALUES (?,?,?,?,?,?,?)",
        ("event-1", "mission", "mission.note", "HERMES_AGENT", "Actual gateway timeline", "actual://event", 123000),
    )
    created = await judgments.escalate(proposal(evidence=[{"ref":"event-1", "kind":"MISSION_EVENT", "label":"Caller label", "observed_at_unix":999}]))
    assert created.evidence[0].verification == "RECORDED_EVENT"
    assert created.evidence[0].label == "Actual gateway timeline" and created.evidence[0].observed_at_unix == 123
    with pytest.raises(DecisionError, match="decision_evidence_uncorrelated"):
        await judgments.escalate(proposal(request_id="create-proposal-2", evidence=[{"ref":"not-recorded", "kind":"MISSION_EVENT"}]))


async def test_bound_runtime_producer_refuses_unknown_run_and_terminal_new_proposal(judgments):
    with pytest.raises(DecisionError, match="decision_run_binding_mismatch"):
        await judgments.escalate(proposal(), producer_run_id="not-real")
    first = await judgments.escalate(proposal(), producer_run_id="run")
    await judgments.store.execute("UPDATE missions SET state='CANCELLED' WHERE mission_id='mission'")
    assert await judgments.escalate(proposal(), producer_run_id="run") == first
    with pytest.raises(DecisionError, match="decision_mission_terminal"):
        await judgments.escalate(proposal(request_id="create-proposal-2"), producer_run_id="run")


async def test_revoked_owner_cannot_answer_or_read_an_exact_retry_through_service(judgments):
    created = await judgments.escalate(proposal())
    await judgments.store.execute("UPDATE devices SET revoked_at_unix=1 WHERE device_id='owner'")
    with pytest.raises(DecisionError, match="decision_owner_device_revoked"):
        await judgments.answer(created.id, answer(), owner_device_id="owner")
    assert (await judgments.get(created.id)).status.value == "OPEN"


async def test_observer_failure_rolls_back_actual_answer_and_derived_observation(judgments, monkeypatch):
    created = await judgments.escalate(proposal())
    async def fail(db, **kwargs):
        await db.execute("INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES('unfinished-owner-observation','{}',1)")
        raise RuntimeError("observer write failed")
    monkeypatch.setattr("van_gateway.learning.observations.record_owner_decision_fingerprint", fail)
    with pytest.raises(RuntimeError, match="observer write failed"):
        await judgments.answer(created.id, answer(), owner_device_id="owner")
    assert (await judgments.get(created.id)).status.value == "OPEN"
    assert await judgments.store.fetchone("SELECT 1 FROM runtime_meta WHERE key='unfinished-owner-observation'") is None


async def test_answer_retry_and_reads_do_not_resurrect_erased_fingerprint(judgments):
    created = await judgments.escalate(proposal())
    accepted = await judgments.answer(created.id, answer(), owner_device_id="owner")
    fingerprint = await judgments.store.fetchone("SELECT decision_id FROM decision_fingerprints")
    identity = hashlib.sha256(Store.dumps({"table":"decision_fingerprints", "key":{"decision_id":fingerprint["decision_id"]}}).encode()).hexdigest()
    await judgments.store.execute("INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,1)", ("memory_erasure_witness:test", json.dumps({"tables":{"decision_fingerprints":{"before_ids":[identity]}}})))
    await judgments.store.execute("DELETE FROM decision_fingerprints")
    assert await judgments.answer(created.id, answer(), owner_device_id="owner") == accepted
    assert await judgments.get(created.id) == accepted
    assert await judgments.store.fetchone("SELECT 1 FROM decision_fingerprints") is None
