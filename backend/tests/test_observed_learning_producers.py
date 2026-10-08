"""Actual owner mission and provider evidence producers, with bounded falsifiability."""
from __future__ import annotations

import json
import time
import uuid

import pytest
import pytest_asyncio

from van_gateway.context.authoring import OwnerFactAuthor
from van_gateway.context.models import SourceTrust
from van_gateway.context.service import OwnerContextService
from van_gateway.knowledge.evidence import KnowledgeEvidenceStore
from van_gateway.knowledge.models import KnowledgeProvider
from van_gateway.knowledge.schema import KnowledgeSchema
from van_gateway.learning.feed import LearningFeed
from van_gateway.learning.observations import ObservedLearning, MAX_AGE_MS, MAX_ROWS, record_external_claim, record_owner_decision_fingerprint
from van_gateway.mission.models import AuthorityEnvelope, MissionOrigin
from van_gateway.mission.service import MissionService
from van_gateway.models import ActionClass, OriginChannel
from van_gateway.storage.db import Store

def _now(store):
    return store._test_observed_at_ms
pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def store(tmp_path):
    store = Store(str(tmp_path / "observed-learning.sqlite3"))
    await store.migrate()
    await KnowledgeSchema(store).ensure()
    store._test_observed_at_ms = int(time.time() * 1000)
    return store


async def _mission(store, *, origin=MissionOrigin.OWNER_UI, mission_class="TRADING_HALT", approved=True):
    from van_gateway.command.authority import CommandAuthorityRecord, CommandAuthorityService
    from van_gateway.models import PrincipalType
    command_id = "observed-test-" + uuid.uuid4().hex
    await CommandAuthorityService(store).seal(CommandAuthorityRecord(command_id=command_id,
        device_id="owner-phone", principal_type=PrincipalType.OWNER_DEVICE, requested_by="owner",
        origin_channel=OriginChannel.UI, signed_action_class=ActionClass.A4, effective_action_class=ActionClass.A4,
        snapshot_id="test-snapshot", context_digest="a"*64, issued_at_unix=_now(store)//1000,
        expires_at_unix=_now(store)//1000+30, no_stale_replay=True, owner_approved=approved, sealed_at_unix_ms=_now(store)))
    return await MissionService(store, learning=LearningFeed(store)).create(
        owner_principal_id="owner", origin=origin, origin_channel=OriginChannel.UI,
        title="test", goal="test observed approval", mission_class=mission_class,
        authority_envelope=AuthorityEnvelope(max_action_class=ActionClass.A4, requires_owner_presence=True, source_command_id=command_id),
        now_ms=_now(store))


async def _evidence(store, content):
    return await KnowledgeEvidenceStore(store).persist(provider=KnowledgeProvider.VEKL,
        query_id="query-1", source_ref="https://source.example/observed?utm=test",
        title="source result", source_trust=SourceTrust.UNTRUSTED_EXTERNAL, scope="global",
        content=content, snippet="bounded source excerpt", retrieved_at_ms=_now(store))


async def test_real_owner_missions_form_bounded_advisory_candidate_without_guessing_reason(store):
    for _ in range(3):
        await _mission(store)
    first = await ObservedLearning(store).decisions(now_ms=_now(store)+10000)
    assert first["active"] and first["status"] == "READY"
    pattern = first["patterns"][0]
    assert pattern["distinct_owner_observations"] == 3 and pattern["support_count"] == 3
    assert pattern["inferred_reason"] is None and pattern["execution_grant"] is False
    assert pattern["observed_outcomes"]["unknown_or_inconclusive"] == 3
    assert pattern["confidence_ceiling"] <= .75
    recovered = await ObservedLearning(Store(store.path)).decisions(now_ms=_now(store)+10000)
    assert recovered == first
    assert not await store.fetchone("SELECT grant_id FROM permission_grants")


async def test_duplicate_system_and_generic_observations_cannot_promote_pattern(store):
    mission = await _mission(store)
    for _ in range(4):
        await LearningFeed(store).record_mission_opened(mission)
    for _ in range(3):
        await _mission(store, origin=MissionOrigin.PROACTIVE)
        await _mission(store, mission_class="GENERAL_OWNER_INTENT")
    result = await ObservedLearning(store).decisions(now_ms=_now(store)+10000)
    assert result["patterns"] == [] and result["status"] == "PARTIAL"
    assert result["unmeasured"] > 0


async def test_counterexample_revises_candidate_and_erasure_removes_derived_pattern(store):
    for _ in range(3):
        await _mission(store)
    before = await ObservedLearning(store).decisions(now_ms=_now(store)+10000)
    mission = await _mission(store)
    from van_gateway.decisions.models import DecisionAnswer, DecisionChoice, DecisionCreate
    from van_gateway.decisions.service import DecisionService
    from van_gateway.attention.engine import AttentionEngine
    await store.execute("INSERT INTO devices(device_id,public_key_pem,enrolled_at_unix) VALUES('owner-phone','test',?)", (_now(store)//1000,))
    service = DecisionService(store, AttentionEngine(store))
    decision = await service.escalate(DecisionCreate(title="Choose", body="Choose for this task", source="test",
        mission_id=mission.mission_id, choices=[DecisionChoice(id="decline", label="Decline"), DecisionChoice(id="approve", label="Approve")]))
    await service.answer(decision.id, DecisionAnswer(choice_id="decline", expected_revision=decision.revision,
        request_id="observed-owner-decline"), owner_device_id="owner-phone")
    after = await ObservedLearning(store).decisions(now_ms=_now(store)+10000)
    assert after["patterns"][0]["state"] == "COUNTEREXAMPLES_PRESENT"
    assert after["patterns"][0]["counterexample_count"] == 1
    assert after["snapshot_sha256"] != before["snapshot_sha256"]
    await store.execute("DELETE FROM decision_fingerprints")
    assert (await ObservedLearning(store).decisions(now_ms=_now(store)+10000))["status"] == "NO_DATA"


async def test_stale_sources_do_not_claim_current_owner_preference(store):
    for _ in range(3):
        await _mission(store)
    result = await ObservedLearning(store).decisions(now_ms=_now(store)+MAX_AGE_MS+10000)
    assert result["patterns"] == [] and result["unmeasured"] == 3


async def test_provider_persistence_is_real_external_producer_and_preserves_disagreement(store):
    fact = await OwnerFactAuthor(OwnerContextService(store)).state(device_id="owner-phone",
        subject="market", predicate="open", value=True, now_ms=_now(store))
    evidence = await _evidence(store, {"subject": "market", "predicate": "open", "value": False})
    observations = await store.fetchall("SELECT * FROM external_reality")
    assert len(observations) == 1 and observations[0]["source_kind"] == "structured_provider_claim"
    result = await ObservedLearning(store).external(now_ms=_now(store)+10)
    assert result["status"] == "READY" and result["contradiction_count"] == 1
    comparison = result["contradictions"][0]
    assert comparison["owner_value"] == "true" and comparison["external_value"] == "false"
    assert comparison["source_trust"] == "UNTRUSTED_EXTERNAL" and comparison["external_confidence"] == 0
    assert "knowledge:" + evidence.evidence_id in comparison["evidence_refs"]
    assert "access_token" not in comparison["source_ref"]
    assert (await store.fetchone("SELECT value_json FROM owner_facts WHERE fact_id=?", (fact.fact_id,)))["value_json"] == "true"
    assert await ObservedLearning(Store(store.path)).external(now_ms=_now(store)+10) == result


async def test_prose_wrong_scope_stale_and_tampered_content_remain_unmeasured(store):
    author = OwnerFactAuthor(OwnerContextService(store))
    await author.state(device_id="owner-phone", subject="market", predicate="open", value=True, now_ms=_now(store))
    assert await record_external_claim(store, evidence_id="missing", content={"subject":"market","predicate":"open","value":False}) is None
    await _evidence(store, "A headline that appears to disagree")
    assert not await store.fetchone("SELECT observation_id FROM external_reality")
    source = await _evidence(store, {"subject": "market", "predicate": "open", "scope": "other", "value": False})
    result = await ObservedLearning(store).external(now_ms=_now(store)+10)
    assert result["comparisons"] == [] and result["unmeasured"] == 1
    with pytest.raises(ValueError, match="content_mismatch"):
        await record_external_claim(store, evidence_id=source.evidence_id, content={"subject":"market","predicate":"open","value":"changed"})
    current = await _evidence(store, {"subject": "market", "predicate": "open", "value": True})
    assert (await ObservedLearning(store).external(now_ms=_now(store)+10))["comparisons"][0]["state"] == "MATCHED_CLAIM"
    row = await store.fetchone("SELECT * FROM external_reality WHERE claim LIKE ?", ("%" + current.evidence_id + "%",))
    wrapped = json.loads(row["claim"])
    wrapped["claim"]["value"] = False
    await store.execute("UPDATE external_reality SET claim=? WHERE observation_id=?", (Store.dumps(wrapped), row["observation_id"]))
    result = await ObservedLearning(store).external(now_ms=_now(store)+10)
    assert result["contradictions"] == [] and result["unmeasured"] == 2
    assert (await ObservedLearning(store).external(now_ms=_now(store)+MAX_AGE_MS+1))["comparisons"] == []


async def test_matching_new_owner_correction_resolves_disagreement_without_choosing_for_owner(store):
    author = OwnerFactAuthor(OwnerContextService(store))
    await author.state(device_id="owner-phone", subject="market", predicate="open", value=True, now_ms=_now(store))
    await _evidence(store, {"subject": "market", "predicate": "open", "value": False})
    assert (await ObservedLearning(store).external(now_ms=_now(store)+1))["contradiction_count"] == 1
    await author.state(device_id="owner-phone", subject="market", predicate="open", value=False, now_ms=_now(store)+2)
    result = await ObservedLearning(store).external(now_ms=_now(store)+3)
    assert result["contradictions"] == [] and result["comparison_count"] == 1
    await store.execute("DELETE FROM owner_facts")
    assert (await ObservedLearning(store).external(now_ms=_now(store)+3))["unmeasured"] == 1


async def test_owner_presence_requirement_without_actual_approval_stays_unmeasured(store):
    for _ in range(3):
        await _mission(store, approved=False)
    result = await ObservedLearning(store).decisions(now_ms=_now(store)+10000)
    assert result["patterns"] == [] and result["unmeasured"] == 3


async def test_distinct_case_sensitive_owner_choice_ids_cannot_merge_into_candidate(store):
    from van_gateway.attention.engine import AttentionEngine
    from van_gateway.decisions.models import DecisionAnswer, DecisionChoice, DecisionCreate
    from van_gateway.decisions.service import DecisionService
    await store.execute("INSERT INTO devices(device_id,public_key_pem,enrolled_at_unix) VALUES('owner-phone','test',?)", (_now(store)//1000,))
    service = DecisionService(store, AttentionEngine(store))
    for index, choice in enumerate(("BUY", "BUY", "buy")):
        mission = await _mission(store, approved=False)
        decision = await service.escalate(DecisionCreate(title="Choose", body="Distinct listed choices",
            mission_id=mission.mission_id, choices=[DecisionChoice(id="BUY", label="Upper choice"), DecisionChoice(id="buy", label="Lower choice")]))
        await service.answer(decision.id, DecisionAnswer(choice_id=choice, expected_revision=decision.revision,
            request_id="case-sensitive-answer-"+str(index)), owner_device_id="owner-phone")
    result = await ObservedLearning(store).decisions(now_ms=_now(store)+10000)
    assert result["patterns"] == [] and result["unmeasured"] == 6


async def test_malformed_decision_context_remains_unmeasured_and_does_not_break_other_evidence(store):
    for _ in range(4):
        await _mission(store)
    row = await store.fetchone("SELECT decision_id FROM decision_fingerprints ORDER BY decision_id LIMIT 1")
    await store.execute("UPDATE decision_fingerprints SET context_json='[]' WHERE decision_id=?", (row["decision_id"],))
    result = await ObservedLearning(store).decisions(now_ms=_now(store)+10000)
    assert result["status"] == "PARTIAL" and result["unmeasured"] == 1
    assert result["patterns"][0]["support_count"] == 3


async def test_external_comparisons_are_bounded_and_explicitly_partial(store):
    author = OwnerFactAuthor(OwnerContextService(store))
    await author.state(device_id="owner-phone", subject="market", predicate="open", value=True, now_ms=_now(store))
    for index in range(MAX_ROWS+1):
        await _evidence(store, {"subject": "market", "predicate": "open", "value": str(index)})
    result = await ObservedLearning(store).external(now_ms=_now(store)+10)
    assert result["truncated"] and result["status"] == "PARTIAL"
    assert result["comparison_count"] == MAX_ROWS and len(result["contradictions"]) == MAX_ROWS
    assert len(result["evidence_refs"]) <= MAX_ROWS


async def test_sensitive_source_claim_and_credential_reference_do_not_produce_advisory_claim(store):
    evidence_store = KnowledgeEvidenceStore(store)
    for content, source in (({"subject":"owner","predicate":"password","value":"sensitive-value"}, "https://source.example/observed"),
                            ({"subject":"market","predicate":"open","value":False}, "https://source.example/observed?access_token=sensitive-value")):
        await evidence_store.persist(provider=KnowledgeProvider.VEKL, query_id="private", source_ref=source,
            title="source", source_trust=SourceTrust.UNTRUSTED_EXTERNAL, scope="global", content=content,
            snippet="provider payload", retrieved_at_ms=_now(store))
    assert not await store.fetchone("SELECT observation_id FROM external_reality")


async def test_owner_decision_producer_is_idempotent_transactional_and_honors_erasure_witness(store):
    kwargs = dict(decision_id="actual-owner-answer", mission_id=None, choice_id="decline", owner_note="owner stated why",
                  evidence_refs=["recorded-event:original"], now_ms=_now(store))
    async with store.connection() as db:
        await db.execute("BEGIN IMMEDIATE")
        fingerprint_id = await record_owner_decision_fingerprint(db, **kwargs)
        assert await record_owner_decision_fingerprint(db, **kwargs) == fingerprint_id
        with pytest.raises(ValueError, match="source_conflict"):
            await record_owner_decision_fingerprint(db, **{**kwargs, "choice_id": "approve"})
        await db.commit()
    row = await store.fetchone("SELECT * FROM decision_fingerprints WHERE decision_id=?", (fingerprint_id,))
    assert row["owner_choice"] == "decline" and row["owner_stated_reason"] == "owner stated why"
    assert row["inferred_reason"] is None
    # A failed answer transaction leaves neither a decision nor a learning projection.
    async with store.connection() as db:
        await db.execute("BEGIN IMMEDIATE")
        await record_owner_decision_fingerprint(db, **{**kwargs, "decision_id": "rolled-back-answer"})
        await db.rollback()
    assert len(await store.fetchall("SELECT * FROM decision_fingerprints")) == 1
    from van_gateway.context.memory_erasure import _identity
    witness = {"tables": {"decision_fingerprints": {"before_ids": [_identity("decision_fingerprints", ["decision_id"], row)]}}}
    await store.execute("INSERT INTO runtime_meta VALUES('memory_erasure_witness:prior',?,?)", (Store.dumps(witness), _now(store)))
    await store.execute("DELETE FROM decision_fingerprints WHERE decision_id=?", (fingerprint_id,))
    async with store.connection() as db:
        assert await record_owner_decision_fingerprint(db, **kwargs) is None
    assert not await store.fetchone("SELECT decision_id FROM decision_fingerprints")


async def test_provider_evidence_and_learning_projection_roll_back_and_recover_together(store, monkeypatch):
    import van_gateway.learning.observations as observations
    original = observations.record_external_claim
    async def project_then_fail(*args, **kwargs):
        await original(*args, **kwargs)
        raise OSError("simulated projection persistence failure")
    monkeypatch.setattr(observations, "record_external_claim", project_then_fail)
    claim = {"subject": "market", "predicate": "open", "value": False}
    with pytest.raises(OSError, match="projection persistence failure"):
        await _evidence(store, claim)
    assert not await store.fetchone("SELECT evidence_id FROM knowledge_evidence")
    assert not await store.fetchone("SELECT observation_id FROM external_reality")
    monkeypatch.setattr(observations, "record_external_claim", original)
    evidence = await _evidence(store, claim)
    assert await store.fetchone("SELECT evidence_id FROM knowledge_evidence WHERE evidence_id=?", (evidence.evidence_id,))
    assert await store.fetchone("SELECT observation_id FROM external_reality")
