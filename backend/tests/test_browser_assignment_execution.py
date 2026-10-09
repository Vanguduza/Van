"""Assignments own their profile lease and require real, sealed completion evidence."""

from __future__ import annotations

import asyncio
import time

import pytest

from tests.test_browser_api import (
    DOMAIN,
    HEADERS,
    _client,
    _make_task,
    _settings,  # noqa: F401 - shared autouse settings fixture
)
from van_gateway.automation.canonical import digest
from van_gateway.browser.adapters import BrowserAdapterError
from van_gateway.browser.subagent import ProposedAction
from van_gateway.browser.worker import AdapterBackedWorker
from van_gateway.browser.interaction_router import IndependentPostconditionVerifier

GOAL = "Read the public statement page and report its URL and title."


class _Harness:
    def __init__(self, *, fail=False, entered=None, proceed=None, after_read=None, observed_url=None):
        self.fail = fail
        self.entered = entered
        self.proceed = proceed
        self.after_read = after_read
        self.observed_url = observed_url or f"https://{DOMAIN}/actual-statement"
        self.calls = []

    async def navigate(self, task, url):
        self.calls.append(("navigate", task.task_id))
        if self.fail:
            raise BrowserAdapterError("BROWSER_WORKER_UNREACHABLE", "test failure")
        if self.entered is not None:
            self.entered.set()
        if self.proceed is not None:
            await self.proceed.wait()

    async def page_info(self, task):
        self.calls.append(("page_info", task.task_id))
        if self.after_read is not None:
            await self.after_read()
        return {
            "url": self.observed_url,
            "title": "Actual statement",
            "extraction": {"visible_text": "Statement total 42"},
        }


def _assignment(task):
    return {
        "task_id": task["task_id"],
        "turn_id": "assignment-proof-turn",
        "command_id": "cmd-owner-1",
        "goal": GOAL,
        "allowed_domains": [DOMAIN],
        "action_class_ceiling": "A2",
        "autonomy_tier": "L1_HARNESS_DETERMINISTIC",
        "max_steps": 4,
        "postcondition": {"kind": "READ_BACK", "field": "title", "expected": "Actual statement"},
        "plan": {"steps": [
            {"kind": "navigate", "domain": DOMAIN, "url": f"https://{DOMAIN}/statement"},
            {"kind": "read", "domain": DOMAIN},
        ]},
    }


async def _task(ac, **overrides):
    return await _make_task(
        ac, strategy="HARNESS", autonomy_tier="L1_HARNESS_DETERMINISTIC",
        goal=GOAL, **overrides,
    )


async def _profile(store, alias="public_research"):
    return await store.fetchone(
        "SELECT lease_holder, lease_holder_id, lease_holder_kind, secret_ref "
        "FROM browser_profiles WHERE profile_alias = ?", (alias,),
    )


async def test_five_tool_route_registers_a_fresh_public_profile(tmp_path):
    harness = _Harness()
    ac, _api, store = await _client(tmp_path, worker=AdapterBackedWorker(harness), verifier=IndependentPostconditionVerifier(harness))
    async with ac:
        assert await _profile(store) is None
        created = await ac.post("/v1/browser/tasks", headers=HEADERS, json={
            "profile_alias": "public_research", "strategy": "HARNESS",
            "autonomy_tier": "L1_HARNESS_DETERMINISTIC", "action_class": "A2",
            "target_domain": DOMAIN, "goal": GOAL, "command_id": "cmd-owner-1",
        })
        assert created.status_code == 200, created.text
        assert await _profile(store) is None
        result = await ac.post(
            "/v1/browser/assignments", headers=HEADERS, json=_assignment(created.json())
        )
        assert result.status_code == 200, result.text
        assert result.json()["succeeded"] is True
        profile = await store.fetchone(
            "SELECT authentication, mutation_policy, secret_ref, lease_holder "
            "FROM browser_profiles WHERE profile_alias = 'public_research'"
        )
        assert profile["authentication"] == "none"
        assert profile["mutation_policy"] == "forbidden"
        assert profile["secret_ref"] is None
        assert profile["lease_holder"] is None


async def test_success_seals_actual_observation_and_releases_profile(tmp_path):
    harness = _Harness()
    ac, _api, store = await _client(tmp_path, worker=AdapterBackedWorker(harness), verifier=IndependentPostconditionVerifier(harness))
    async with ac:
        task = await _task(ac)
        response = await ac.post("/v1/browser/assignments", headers=HEADERS, json=_assignment(task))
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["succeeded"] is True
        assert result["stop_reason"] == "GOAL_ACHIEVED"
        assert result["step_count"] == 2
        assert result["session_lease_generation"] > 0
        assert result["session_lease_released"] is True

        evidence = result["evidence"]
        assert evidence["task_id"] == task["task_id"]
        assert evidence["kind"] == "ASSIGNMENT_COMPLETION"
        assert evidence["contains_secrets"] is False
        assert evidence["url_digest"] == digest({"url": f"https://{DOMAIN}/actual-statement"})
        assert evidence["extraction_digest"] == digest({
            "assignment_id": result["assignment_id"],
            "turn_id": result["turn_id"],
            "command_id": "cmd-owner-1",
            "goal_digest": digest({"goal": GOAL}),
            "steps": result["steps"],
            "observation": result["extraction"],
        })
        pointer = f"browser-evidence://{evidence['evidence_id']}"
        assert result["evidence_pointer"] == pointer
        task_result = (await ac.get(f"/v1/browser/tasks/{task['task_id']}")).json()
        assert task_result["task"]["status"] == "COMPLETED"
        assert task_result["task"]["evidence_pointer"] == pointer
        rows = (await ac.get(f"/v1/browser/tasks/{task['task_id']}/evidence")).json()
        assert any(row["kind"] == "postcondition_verification" for row in rows)
        rows = [row for row in rows if row["kind"] == "ASSIGNMENT_COMPLETION"]
        assert len(rows) == 1
        assert rows[0]["evidence_id"] == evidence["evidence_id"]
        assert rows[0]["extraction_digest"] == evidence["extraction_digest"]
        profile = await _profile(store)
        assert profile["lease_holder"] is None
        assert profile["lease_holder_id"] is None
        assert profile["lease_holder_kind"] is None


async def test_adapter_failure_cannot_complete_or_seal_evidence(tmp_path):
    harness = _Harness(fail=True)
    ac, _api, store = await _client(tmp_path, worker=AdapterBackedWorker(harness), verifier=IndependentPostconditionVerifier(harness))
    async with ac:
        task = await _task(ac)
        response = await ac.post("/v1/browser/assignments", headers=HEADERS, json=_assignment(task))
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["succeeded"] is False
        assert result["stop_reason"] == "WORKER_ERROR"
        assert result["step_count"] == 0
        assert result["evidence"] is None
        assert result["evidence_pointer"] is None
        assert result["session_lease_released"] is True
        fetched = (await ac.get(f"/v1/browser/tasks/{task['task_id']}")).json()
        assert fetched["task"]["status"] == "FAILED"
        assert fetched["task"]["error_code"] == "WORKER_ERROR"
        assert fetched["evidence"] == []
        assert (await _profile(store))["lease_holder"] is None


async def test_concurrent_assignments_cannot_share_a_profile(tmp_path):
    entered = asyncio.Event()
    proceed = asyncio.Event()
    harness = _Harness(entered=entered, proceed=proceed)
    ac, _api, store = await _client(tmp_path, worker=AdapterBackedWorker(harness), verifier=IndependentPostconditionVerifier(harness))
    async with ac:
        first_task = await _task(ac)
        second_task = await _task(ac)
        first = asyncio.create_task(
            ac.post("/v1/browser/assignments", headers=HEADERS, json=_assignment(first_task))
        )
        try:
            await asyncio.wait_for(entered.wait(), timeout=2)
            held = await _profile(store)
            assert held["lease_holder_id"] == first_task["task_id"]
            assert held["lease_holder_kind"] == "TASK"
            second = await ac.post(
                "/v1/browser/assignments", headers=HEADERS, json=_assignment(second_task)
            )
            assert second.status_code == 409
            assert "browser_profile_leased" in second.json()["detail"]
            assert (await _profile(store))["lease_holder"] == held["lease_holder"]
            assert not any(task_id == second_task["task_id"] for _, task_id in harness.calls)
        finally:
            proceed.set()
            first_result = await asyncio.wait_for(first, timeout=2)
        assert first_result.json()["succeeded"] is True
        retry = await ac.post(
            "/v1/browser/assignments", headers=HEADERS, json=_assignment(second_task)
        )
        assert retry.json()["succeeded"] is True
        assert (await _profile(store))["lease_holder"] is None


async def test_lease_expiry_during_observation_stops_before_completion(tmp_path):
    harness = _Harness()
    ac, _api, store = await _client(tmp_path, worker=AdapterBackedWorker(harness), verifier=IndependentPostconditionVerifier(harness))

    async def expire_lease():
        await store.execute(
            "UPDATE browser_profiles SET lease_expires_at_ms = 1 "
            "WHERE profile_alias = 'public_research'"
        )

    harness.after_read = expire_lease
    async with ac:
        task = await _task(ac)
        response = await ac.post("/v1/browser/assignments", headers=HEADERS, json=_assignment(task))
        result = response.json()
        assert result["succeeded"] is False
        assert result["stop_reason"] == "WORKER_ERROR"
        assert result["step_count"] == 0
        assert result["evidence"] is None
        assert len(harness.calls) == 2
        assert (await _profile(store))["lease_holder"] is None


async def test_blocked_proposal_cannot_run_past_the_assignment_deadline(tmp_path):
    class BlockedWorker:
        def __init__(self):
            self.entered = asyncio.Event()
            self.executed = False

        async def propose(self, assignment, history):
            self.entered.set()
            await asyncio.Event().wait()
            return ProposedAction(kind="read", domain=DOMAIN)

        async def execute(self, assignment, action):
            self.executed = True
            raise AssertionError("an expired proposal must never execute")

    worker = BlockedWorker()
    ac, _api, store = await _client(tmp_path, worker=worker)
    async with ac:
        task = await _task(ac)
        body = _assignment(task)
        body["deadline_ms"] = int(time.time() * 1000) + 500
        response = await asyncio.wait_for(
            ac.post("/v1/browser/assignments", headers=HEADERS, json=body), timeout=2
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert worker.entered.is_set()
        assert worker.executed is False
        assert result["succeeded"] is False
        assert result["stop_reason"] == "DEADLINE_REACHED"
        assert result["evidence"] is None
        fetched = (await ac.get(f"/v1/browser/tasks/{task['task_id']}")).json()
        assert fetched["task"]["status"] == "FAILED"
        assert fetched["task"]["error_code"] == "DEADLINE_REACHED"
        assert (await _profile(store))["lease_holder"] is None


@pytest.mark.parametrize("observed_url, succeeds", [
    (f"https://Sub.{DOMAIN.upper()}./statement", True),
    (f"https://{DOMAIN}.outside.example/statement", False),
])
async def test_completion_observation_uses_the_bounded_domain_rule(tmp_path, observed_url, succeeds):
    harness = _Harness(observed_url=observed_url)
    ac, _api, store = await _client(tmp_path, worker=AdapterBackedWorker(harness), verifier=IndependentPostconditionVerifier(harness))
    async with ac:
        task = await _task(ac, scope=[f"https://{DOMAIN}", f"https://sub.{DOMAIN}"])
        body = _assignment(task)
        body["allowed_domains"] = [DOMAIN, f"sub.{DOMAIN}"]
        response = await ac.post("/v1/browser/assignments", headers=HEADERS, json=body)
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["succeeded"] is succeeds, result
        assert (result["evidence"] is not None) is succeeds
        assert (await _profile(store))["lease_holder"] is None


async def test_assignment_does_not_replace_authenticated_profile_reference(tmp_path):
    harness = _Harness()
    ac, _api, store = await _client(tmp_path, worker=AdapterBackedWorker(harness), verifier=IndependentPostconditionVerifier(harness))
    async with ac:
        registered = await ac.post("/v1/browser/profiles", headers=HEADERS, json={
            "profile_alias": "authenticated_owner",
            "secret_ref": "secretref://browser/existing-owner",
        })
        assert registered.status_code == 200
        task = await _task(ac, profile_alias="authenticated_owner")
        response = await ac.post("/v1/browser/assignments", headers=HEADERS, json=_assignment(task))
        assert response.json()["succeeded"] is True
        profile = await _profile(store, "authenticated_owner")
        assert profile["secret_ref"] == "secretref://browser/existing-owner"
        assert profile["lease_holder"] is None


async def test_assignment_does_not_provision_an_absent_authenticated_profile(tmp_path):
    harness = _Harness()
    ac, _api, store = await _client(tmp_path, worker=AdapterBackedWorker(harness), verifier=IndependentPostconditionVerifier(harness))
    async with ac:
        task = await _task(ac, profile_alias="authenticated_owner")
        response = await ac.post("/v1/browser/assignments", headers=HEADERS, json=_assignment(task))
        assert response.status_code == 409
        assert response.json()["detail"] == "browser_profile_registration_required:authenticated_owner"
        assert await _profile(store, "authenticated_owner") is None
        assert harness.calls == []


async def test_cancelled_assignment_fails_and_releases_its_profile(tmp_path):
    entered = asyncio.Event()
    harness = _Harness(entered=entered, proceed=asyncio.Event())
    ac, _api, store = await _client(tmp_path, worker=AdapterBackedWorker(harness), verifier=IndependentPostconditionVerifier(harness))
    async with ac:
        task = await _task(ac)
        pending = asyncio.create_task(
            ac.post("/v1/browser/assignments", headers=HEADERS, json=_assignment(task))
        )
        await asyncio.wait_for(entered.wait(), timeout=2)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        fetched = (await ac.get(f"/v1/browser/tasks/{task['task_id']}")).json()
        assert fetched["task"]["status"] == "FAILED"
        assert fetched["task"]["error_code"] == "BROWSER_ASSIGNMENT_INTERRUPTED"
        assert fetched["evidence"] == []
        assert (await _profile(store))["lease_holder"] is None


async def test_cancellation_during_acquisition_releases_the_committed_lease(tmp_path, monkeypatch):
    harness = _Harness()
    ac, api, store = await _client(tmp_path, worker=AdapterBackedWorker(harness), verifier=IndependentPostconditionVerifier(harness))
    acquired = asyncio.Event()
    proceed = asyncio.Event()
    acquire = api.broker.acquire_lease

    async def held_acquisition(**kwargs):
        lease = await acquire(**kwargs)
        acquired.set()
        await proceed.wait()
        return lease

    monkeypatch.setattr(api.broker, "acquire_lease", held_acquisition)
    async with ac:
        task = await _task(ac)
        pending = asyncio.create_task(
            ac.post("/v1/browser/assignments", headers=HEADERS, json=_assignment(task))
        )
        await asyncio.wait_for(acquired.wait(), timeout=2)
        assert (await _profile(store))["lease_holder"] is not None
        pending.cancel()
        proceed.set()
        with pytest.raises(asyncio.CancelledError):
            await pending
        fetched = (await ac.get(f"/v1/browser/tasks/{task['task_id']}")).json()
        assert fetched["task"]["status"] == "PENDING"
        assert fetched["evidence"] == []
        assert (await _profile(store))["lease_holder"] is None


async def test_failed_evidence_sealing_cannot_complete_and_releases_profile(tmp_path, monkeypatch):
    harness = _Harness()
    ac, api, store = await _client(tmp_path, worker=AdapterBackedWorker(harness), verifier=IndependentPostconditionVerifier(harness))

    async def failed_seal(**kwargs):
        raise RuntimeError("evidence store unavailable")

    monkeypatch.setattr(api.tasks, "seal_evidence", failed_seal)
    async with ac:
        task = await _task(ac)
        with pytest.raises(RuntimeError, match="evidence store unavailable"):
            await ac.post("/v1/browser/assignments", headers=HEADERS, json=_assignment(task))
        fetched = (await ac.get(f"/v1/browser/tasks/{task['task_id']}")).json()
        assert fetched["task"]["status"] == "FAILED"
        assert fetched["task"]["evidence_pointer"] is None
        assert fetched["evidence"] == []
        assert (await _profile(store))["lease_holder"] is None


async def test_done_without_observation_is_not_success(tmp_path):
    class EmptyWorker:
        async def propose(self, assignment, history):
            return ProposedAction(kind="done", domain=DOMAIN, done=True)

        async def execute(self, assignment, action):
            raise AssertionError("no action was proposed")

    ac, _api, store = await _client(tmp_path, worker=EmptyWorker())
    async with ac:
        task = await _task(ac)
        result = (await ac.post(
            "/v1/browser/assignments", headers=HEADERS, json=_assignment(task)
        )).json()
        assert result["succeeded"] is False
        assert result["stop_reason"] == "UNVERIFIABLE"
        assert result["detail"] == "verifier_unavailable"
        assert result["evidence"] is None
        assert (await _profile(store))["lease_holder"] is None
