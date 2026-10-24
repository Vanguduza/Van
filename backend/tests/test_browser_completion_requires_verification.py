"""Review I M-2 — no path sets a browser task COMPLETED without a VERIFIED verdict.

Owner decision 2026-09-29 §7: "No browser lane may self-certify success." Before the fix
``POST /v1/browser/tasks/{id}/complete`` wrote COMPLETED unconditionally: an assignment
whose independent verifier returned FAILED left the task FAILED, and one internal call then
turned it COMPLETED (review-i/probes/complete.py: ``POST /complete: 200 ... status now:
COMPLETED``). ``BrowserTaskService.complete`` is now the single choke point and requires the
task's latest recorded verdict to be VERIFIED.
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

import test_browser_api as t
from conftest_automation import make_store
from van_gateway.browser.models import AutonomyTier, BrowserStrategy, BrowserTaskStatus
from van_gateway.browser.policy import BrowserPolicyError
from van_gateway.browser.service import (
    VERIFICATION_EVIDENCE_KIND,
    BrowserTaskNotVerified,
    BrowserTaskService,
)
from van_gateway.browser.subagent import ProposedAction
from van_gateway.config import get_settings
from van_gateway.models import ActionClass

POSTCONDITION = {"kind": "READ_BACK", "field": "title", "expected": "Statement"}


@pytest.fixture(autouse=True)
def _browser_env(monkeypatch, tmp_path):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "browser.sqlite3"))
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", t.INGRESS)
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", t.INTERNAL)
    monkeypatch.setenv("VAN_DEVICE_ENROLMENT_TOKEN", t.INTERNAL)
    monkeypatch.setenv("VAN_BROWSER_ENABLED", "1")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _assign(ac, task, **extra):
    body = {
        "task_id": task["task_id"], "turn_id": "turn-v", "command_id": "cmd-owner-1",
        "goal": "read the statement total", "allowed_domains": [t.DOMAIN],
        "postcondition": POSTCONDITION,
    }
    body.update(extra)
    return await ac.post("/v1/browser/assignments", headers=t.HEADERS, json=body)


async def _status(ac, task):
    return (await ac.get(f"/v1/browser/tasks/{task['task_id']}", headers=t.HEADERS)).json()["task"]["status"]


async def _complete(ac, task, status="COMPLETED"):
    return await ac.post(
        f"/v1/browser/tasks/{task['task_id']}/complete", headers=t.HEADERS, json={"status": status}
    )


async def test_complete_cannot_overrule_a_failed_verifier(tmp_path):
    """The reviewer's probe, as a regression test."""
    worker = t._ScriptedWorker([ProposedAction(kind="done", domain=t.DOMAIN, done=True)])
    ac, _api, _store = await t._client(tmp_path, worker=worker, verifier=t._Verdict("FAILED"))
    async with ac:
        task = await t._make_task(ac)
        r = await _assign(ac, task)
        assert (r.json()["stop_reason"], r.json()["succeeded"]) == ("NOT_SATISFIED", False)
        assert await _status(ac, task) == "FAILED"

        c = await _complete(ac, task)
        assert c.status_code == 409
        assert c.json()["detail"] == "BROWSER_TASK_NOT_VERIFIED:FAILED"
        assert await _status(ac, task) == "FAILED"


async def test_complete_without_any_verdict_is_refused(tmp_path):
    ac, _api, _store = await t._client(tmp_path)
    async with ac:
        task = await t._make_task(ac)
        c = await _complete(ac, task)
        assert (c.status_code, c.json()["detail"]) == (409, "BROWSER_TASK_NOT_VERIFIED:NO_VERIFICATION")
        assert await _status(ac, task) == "PENDING"
        # Non-success end states are not a success claim and stay available.
        assert (await _complete(ac, task, "CANCELLED")).status_code == 200
        assert await _status(ac, task) == "CANCELLED"


async def test_unverifiable_done_claim_cannot_be_completed_by_hand(tmp_path):
    worker = t._ScriptedWorker([ProposedAction(kind="done", domain=t.DOMAIN, done=True)])
    ac, _api, _store = await t._client(tmp_path, worker=worker, verifier=None)
    async with ac:
        task = await t._make_task(ac)
        r = await _assign(ac, task)
        assert r.json()["stop_reason"] == "UNVERIFIABLE"
        assert await _status(ac, task) == "VERIFYING"
        c = await _complete(ac, task)
        assert (c.status_code, c.json()["detail"]) == (409, "BROWSER_TASK_NOT_VERIFIED:UNVERIFIABLE")


async def test_verified_assignment_completes_and_records_its_verdict(tmp_path):
    worker = t._ScriptedWorker([
        ProposedAction(kind="extract", domain=t.DOMAIN, instruction="read the statement"),
        ProposedAction(kind="done", domain=t.DOMAIN, done=True),
    ])
    ac, _api, store = await t._client(tmp_path, worker=worker, verifier=t._Verdict("VERIFIED"))
    async with ac:
        task = await t._make_task(ac)
        r = await _assign(ac, task)
        assert r.json()["succeeded"] is True
        assert await _status(ac, task) == "COMPLETED"
        rows = await store.fetchall(
            "SELECT evidence_json FROM browser_evidence WHERE task_id = ? AND kind = ?",
            (task["task_id"], VERIFICATION_EVIDENCE_KIND),
        )
        assert len(rows) == 1 and '"VERIFIED"' in str(rows[0]["evidence_json"])


async def test_verdict_kind_cannot_be_forged_through_the_evidence_route(tmp_path):
    ac, _api, _store = await t._client(tmp_path)
    async with ac:
        task = await t._make_task(ac)
        r = await ac.post(
            f"/v1/browser/tasks/{task['task_id']}/evidence", headers=t.HEADERS,
            json={"kind": VERIFICATION_EVIDENCE_KIND, "url": f"https://{t.DOMAIN}/",
                  "extraction": {"outcome": "VERIFIED"}},
        )
        assert r.status_code == 422
        assert (await _complete(ac, task)).status_code == 409


async def _service_task(tmp_path, action_class=ActionClass.A1):
    store = await make_store(tmp_path)
    service = BrowserTaskService(store)
    await service.broker.register_profile(profile_alias="public_research")
    task = await service.create_task(
        profile_alias="public_research", strategy=BrowserStrategy.HARNESS,
        autonomy_tier=AutonomyTier.L1_HARNESS_DETERMINISTIC, action_class=action_class,
        target_domain="research.example.com", goal="read",
    )
    return store, service, task


async def test_latest_verdict_decides(tmp_path):
    _store, service, task = await _service_task(tmp_path)
    await service.record_verification(task=task, outcome="VERIFIED", verifier="v", now_ms=1)
    await service.record_verification(task=task, outcome="FAILED", verifier="v", now_ms=2)
    with pytest.raises(BrowserTaskNotVerified, match="FAILED"):
        await service.complete(task_id=task.task_id, status=BrowserTaskStatus.COMPLETED)
    await service.record_verification(task=task, outcome="VERIFIED", verifier="v", now_ms=3)
    await service.complete(task_id=task.task_id, status=BrowserTaskStatus.COMPLETED)


async def test_seal_evidence_refuses_the_verdict_kind(tmp_path):
    _store, service, task = await _service_task(tmp_path)
    with pytest.raises(BrowserPolicyError, match="reserved_for_verifier"):
        await service.seal_evidence(task=task, kind=VERIFICATION_EVIDENCE_KIND, url="https://x.example/")


async def test_read_only_evidence_verification_reads_the_row_back(tmp_path):
    _store, service, task = await _service_task(tmp_path)
    assert await service.verify_read_only_evidence(task=task, evidence_id="browser_evidence_nope") == "UNVERIFIABLE"
    with pytest.raises(BrowserTaskNotVerified):
        await service.complete(task_id=task.task_id, status=BrowserTaskStatus.COMPLETED)
    evidence = await service.seal_evidence(task=task, kind="watch_observation", url="https://x.example/",
                                           extraction={"sha": "0" * 64})
    assert await service.verify_read_only_evidence(task=task, evidence_id=evidence.evidence_id) == "VERIFIED"
    await service.complete(task_id=task.task_id, status=BrowserTaskStatus.COMPLETED)


async def test_read_only_evidence_verification_refuses_tasks_above_a1(tmp_path):
    _store, service, task = await _service_task(tmp_path, action_class=ActionClass.A2)
    evidence = await service.seal_evidence(task=task, kind="observation", url="https://x.example/",
                                           extraction={"a": 1})
    assert await service.verify_read_only_evidence(task=task, evidence_id=evidence.evidence_id) == "UNVERIFIABLE"
    with pytest.raises(BrowserTaskNotVerified, match="UNVERIFIABLE"):
        await service.complete(task_id=task.task_id, status=BrowserTaskStatus.COMPLETED)
