"""An owner answer is a typed, durable decision, including lost replies and races."""
import asyncio

import pytest

from conftest_automation import make_store
from test_session_transport_api import _device, _headers, _open, _settings, client
from van_gateway.attention.engine import AttentionEngine
from van_gateway.decisions.service import DecisionCreate, DecisionError, DecisionService
from van_gateway.storage.db import Store


@pytest.fixture(autouse=True)
def _no_scheduler(monkeypatch):
    monkeypatch.setenv("VAN_SCHEDULER_ENABLED", "false")


async def _service(tmp_path):
    store = await make_store(tmp_path)
    service = DecisionService(store, AttentionEngine(store))
    decision = await service.escalate(DecisionCreate(title="Owner judgment", body="Approve proposal?"))
    return service, decision


@pytest.mark.asyncio
async def test_lost_response_recovers_same_decision_and_resolution_timestamp_after_restart(tmp_path):
    service, decision = await _service(tmp_path)
    first = await service.resolve(decision.id, approved=False)
    restarted = DecisionService(Store(service.store.path), AttentionEngine(Store(service.store.path)))
    assert await restarted.resolve(decision.id, approved=False) == first
    assert (await service.store.fetchone("SELECT state FROM attention WHERE dedupe_key=?", (f"decision:{decision.id}",)))["state"] == "HANDLED"


@pytest.mark.asyncio
async def test_concurrent_opposite_answers_cannot_overwrite_first_resolution(tmp_path):
    service, decision = await _service(tmp_path)
    results = await asyncio.gather(service.resolve(decision.id, approved=True),
                                   service.resolve(decision.id, approved=False), return_exceptions=True)
    accepted = [result for result in results if not isinstance(result, BaseException)]
    refused = [result for result in results if isinstance(result, DecisionError)]
    assert len(accepted) == len(refused) == 1
    assert refused[0].reason == "decision_already_resolved"
    row = await service.store.fetchone("SELECT status FROM decisions WHERE id=?", (decision.id,))
    assert row["status"] == accepted[0].status.value


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["false", "true", 0, 1, None, [], {}])
async def test_service_does_not_coerce_untyped_owner_answer(tmp_path, value):
    service, decision = await _service(tmp_path)
    with pytest.raises(DecisionError) as refused:
        await service.resolve(decision.id, approved=value)
    assert refused.value.reason == "decision_answer_invalid"
    assert (await service.store.fetchone("SELECT status FROM decisions WHERE id=?", (decision.id,)))["status"] == "OPEN"


@pytest.mark.asyncio
async def test_expired_decision_cannot_be_approved_or_rejected(tmp_path):
    service, decision = await _service(tmp_path)
    await service.store.execute("UPDATE decisions SET status='EXPIRED' WHERE id=?", (decision.id,))
    for approved in (True, False):
        with pytest.raises(DecisionError, match="decision_already_resolved"):
            await service.resolve(decision.id, approved=approved)


@pytest.mark.asyncio
async def test_attention_failure_after_resolution_recovers_without_reversing_answer(tmp_path, monkeypatch):
    service, decision = await _service(tmp_path)
    original = service.attention.mark_handled
    async def unavailable(item_id):
        raise RuntimeError("attention unavailable after resolution")
    monkeypatch.setattr(service.attention, "mark_handled", unavailable)
    with pytest.raises(RuntimeError):
        await service.resolve(decision.id, approved=True)
    monkeypatch.setattr(service.attention, "mark_handled", original)
    assert (await service.resolve(decision.id, approved=True)).status.value == "APPROVED"
    with pytest.raises(DecisionError, match="decision_already_resolved"):
        await service.resolve(decision.id, approved=False)


@pytest.mark.asyncio
async def test_both_carriers_refuse_string_false_and_keep_decision_open(client):
    ac, app = client
    device = await _device(app)
    decision = await app.state.decisions.escalate(DecisionCreate(title="Owner judgment", body="Approve proposal?"))
    rejected = await ac.post(f"/v1/decisions/{decision.id}/resolve", headers=_headers(device), json={"approved": "false"})
    assert rejected.status_code == 422
    opened = await _open(ac, device)
    body = {"message_id": "invalid-answer", "van_session_id": opened["van_session_id"],
            "session_epoch": opened["session_epoch"], "path_epoch": opened["path_epoch"],
            "kind": "decision.answer", "idempotency_key": "invalid-answer-key",
            "payload": {"decision_id": decision.id, "approved": "false"}}
    rejected = await ac.post("/v1/session/messages", headers=_headers(device), json=body)
    assert rejected.status_code == 400 and rejected.json()["detail"] == "approved_invalid"
    assert (await app.state.store.fetchone("SELECT status FROM decisions WHERE id=?", (decision.id,)))["status"] == "OPEN"
    body["payload"]["approved"] = False
    accepted = await ac.post("/v1/session/messages", headers=_headers(device), json=body)
    assert accepted.status_code == 200 and accepted.json()["result"]["status"] == "REJECTED"
    contradiction = await ac.post(f"/v1/decisions/{decision.id}/resolve", headers=_headers(device), json={"approved": True})
    assert contradiction.status_code == 409 and contradiction.json()["detail"] == "decision_already_resolved"
