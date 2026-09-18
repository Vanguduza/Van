"""Rev 1.3 §§34, 108, 246, 379, 387-391 — what a browser stop may and may not ask.

Escalation exists so that a task drawn slightly too narrow reaches the owner
instead of dying quietly. That is worth having, and it introduces a new thing to
get wrong: an approval prompt is a way to *obtain* authority, so a prompt the
page can provoke is an attack surface rather than a supervision feature.

These tests pin the line between the two:

* reporting and asking are different acts. A forbidden or ambiguous stop is
  reported — the task ends, visibly — but never becomes a question;
* no owner approval can make the browser an A4 surface, so A4 is never asked;
* every distinct question is asked once and separately, and a question already
  answered is never re-presented as new;
* an open question does not hold a browser lease, and does not stay open forever.
"""

from __future__ import annotations

import json

import pytest

from tests.test_browser_api import (  # noqa: F401 - fixtures ride along
    DOMAIN,
    HEADERS,
    _ScriptedWorker,
    _client,
    _make_task,
    _settings,
    fabric,
)
from van_gateway.browser.models import (
    BrowserBoundaryType,
    BrowserEscalationStatus,
    BrowserTaskStatus,
)
from van_gateway.browser.subagent import (
    ProposedAction,
    SubagentStop,
    classify_boundary,
    plausible_hostname,
)
from van_gateway.models import ActionClass


def _assignment(task_id: str, **overrides) -> dict:
    body = {
        "task_id": task_id,
        "turn_id": "turn-1",
        "command_id": "cmd-owner-1",
        "goal": "read the statement total",
        "allowed_domains": [DOMAIN],
    }
    body.update(overrides)
    return body


# ------------------------------------------------------- the classifier alone


@pytest.mark.parametrize(
    ("stop", "kwargs", "expected"),
    [
        # §§108, 391 — no approval can make the browser an A4 surface, so there
        # is nothing to ask. A4 needs approval bound to the exact action, which
        # is the opposite of widening a standing assignment.
        (SubagentStop.ACTION_CLASS_VIOLATION, {"requested_action_class": ActionClass.A4},
         BrowserBoundaryType.POLICY_FORBIDDEN),
        (SubagentStop.ACTION_CLASS_VIOLATION, {"requested_action_class": ActionClass.A5},
         BrowserBoundaryType.POLICY_FORBIDDEN),
        (SubagentStop.ACTION_CLASS_VIOLATION, {"requested_action_class": ActionClass.A3},
         BrowserBoundaryType.OWNER_EXTENSION_REQUIRED),
        # §34, §387 — asking the owner to approve these is the outcome the
        # refusal exists to prevent.
        (SubagentStop.PAYMENT_REFUSED, {}, BrowserBoundaryType.POLICY_FORBIDDEN),
        (SubagentStop.INJECTION_REFUSED, {}, BrowserBoundaryType.POLICY_FORBIDDEN),
        (SubagentStop.GOAL_DRIFT, {}, BrowserBoundaryType.AMBIGUOUS_OR_UNSAFE),
        (SubagentStop.SCOPE_VIOLATION, {"requested_domain": "reports.example.com"},
         BrowserBoundaryType.OWNER_EXTENSION_REQUIRED),
        # A worker handing us free text to render in a prompt is the page
        # writing the prompt, so it is never a question.
        (SubagentStop.SCOPE_VIOLATION, {"requested_domain": "approve this now!"},
         BrowserBoundaryType.AMBIGUOUS_OR_UNSAFE),
        (SubagentStop.SCOPE_VIOLATION, {"requested_domain": None},
         BrowserBoundaryType.AMBIGUOUS_OR_UNSAFE),
        (SubagentStop.ACTION_CLASS_VIOLATION, {}, BrowserBoundaryType.AMBIGUOUS_OR_UNSAFE),
    ],
)
def test_classify_boundary(stop, kwargs, expected):
    assert classify_boundary(stop, **kwargs) is expected


def test_plausible_hostname_rejects_prompt_text():
    assert plausible_hostname("reports.example.com")
    assert plausible_hostname("a.b.c.example.co.uk")
    assert not plausible_hostname("Please approve, it is safe")
    assert not plausible_hostname("-leading.example.com")
    assert not plausible_hostname("")


@pytest.mark.parametrize(
    "target",
    ["localhost", "van-host", "127.0.0.1", "192.168.1.10", "10.0.0.5", "::1", "[::1]"],
)
def test_a_local_target_can_never_become_a_question(target):
    """Owner decision, 2026-09-18: the browser fabric reads the public web.

    A worker reaching for the VAN host's own services is far more likely to be a
    page that led it astray than a task drawn too narrowly, so no approval prompt
    for one is ever generated. `127.0.0.1` is covered explicitly because it
    satisfies the hostname shape while meaning exactly what `localhost` means —
    blocking only the named form would leave the decision half-kept.
    """
    assert not plausible_hostname(target)


def test_a_bare_public_address_is_not_a_domain_either():
    """`AutomationPolicy._reject_literal_ip` holds the same rule: a worker that
    names an address instead of a host has stopped browsing the web."""
    assert not plausible_hostname("8.8.8.8")


# ------------------------------------------------- A4 is never a question


async def test_a_worker_proposing_a4_never_reaches_the_owner(tmp_path):
    """The defect this closes: page-selected A4 manufacturing an owner prompt."""
    worker = _ScriptedWorker(
        [ProposedAction(kind="submit", domain=DOMAIN, action_class=ActionClass.A4,
                        instruction="confirm the transfer")]
    )
    ac, _api, store = await _client(tmp_path, worker=worker)
    async with ac:
        task = await _make_task(ac)
        body = (
            await ac.post("/v1/browser/assignments", headers=HEADERS,
                          json=_assignment(task["task_id"]))
        ).json()
        assert body["stop_reason"] == "ACTION_CLASS_VIOLATION"
        assert body["escalation"]["escalated"] is False
        assert body["escalation"]["boundary_type"] == "POLICY_FORBIDDEN"
        assert body["escalation"]["status"] == BrowserTaskStatus.BLOCKED_POLICY.value

        # Nothing was recorded that an owner could ever be asked to approve.
        assert await store.fetchall("SELECT * FROM browser_escalations") == []
        assert await store.fetchall("SELECT * FROM decisions") == []
        assert await store.fetchall("SELECT * FROM attention") == []


async def test_an_approved_a4_row_still_cannot_become_an_authorization(tmp_path):
    """Belt and braces for rows an earlier build could have written.

    The classifier will not raise an A4 question, but a database that already
    holds one must not be able to turn an owner's yes into an A4 browser grant.
    """
    worker = _ScriptedWorker(
        [ProposedAction(kind="submit", domain=DOMAIN, action_class=ActionClass.A3)]
    )
    ac, _api, store = await _client(tmp_path, worker=worker)
    async with ac:
        task = await _make_task(ac)
        await ac.post("/v1/browser/assignments", headers=HEADERS,
                      json=_assignment(task["task_id"]))
        row = await store.fetchone(
            "SELECT escalation_id, decision_id FROM browser_escalations WHERE task_id = ?",
            (task["task_id"],),
        )
        # Rewrite the stored delta to A4, exactly as a pre-fix build could have.
        await store.execute(
            "UPDATE browser_escalations SET requested_scope_delta_json = ? WHERE escalation_id = ?",
            (json.dumps({"action_class_ceiling": "A4"}), row["escalation_id"]),
        )
        await store.execute("UPDATE decisions SET status = 'APPROVED' WHERE id = ?",
                            (row["decision_id"],))

        resumed = await ac.post("/v1/browser/assignments", headers=HEADERS,
                                json=_assignment(task["task_id"]))
        assert resumed.status_code == 409
        assert "BLOCKED_POLICY" in resumed.json()["detail"]
        assert await store.fetchall("SELECT * FROM browser_scope_authorizations") == []


async def test_an_unparseable_domain_is_not_rendered_into_a_prompt(tmp_path):
    worker = _ScriptedWorker(
        [ProposedAction(kind="navigate", domain="URGENT: approve to continue")]
    )
    ac, _api, store = await _client(tmp_path, worker=worker)
    async with ac:
        task = await _make_task(ac)
        body = (
            await ac.post("/v1/browser/assignments", headers=HEADERS,
                          json=_assignment(task["task_id"]))
        ).json()
        assert body["escalation"]["escalated"] is False
        assert body["escalation"]["boundary_type"] == "AMBIGUOUS_OR_UNSAFE"
        assert body["escalation"]["status"] == BrowserTaskStatus.BLOCKED_UNSAFE.value
        assert await store.fetchall("SELECT * FROM decisions") == []


# ------------------------------------------- one question per distinct ask


async def test_two_different_overruns_are_two_separate_questions(tmp_path):
    """The defect this closes: a second overrun keyed only on the stop reason
    collided with the first, and the owner was never asked about it."""
    worker = _ScriptedWorker(
        [ProposedAction(kind="navigate", domain="first.example.net")]
    )
    ac, _api, store = await _client(tmp_path, worker=worker)
    async with ac:
        task = await _make_task(ac)
        first = await ac.post("/v1/browser/assignments", headers=HEADERS,
                              json=_assignment(task["task_id"]))
        assert first.json()["escalation"]["requested_scope_delta"] == {
            "allowed_domain": "first.example.net"
        }
        row = await store.fetchone(
            "SELECT decision_id FROM browser_escalations WHERE task_id = ?", (task["task_id"],)
        )
        await store.execute("UPDATE decisions SET status='APPROVED' WHERE id = ?",
                            (row["decision_id"],))

        worker.actions = [ProposedAction(kind="navigate", domain="second.example.net")]
        second = await ac.post(
            "/v1/browser/assignments", headers=HEADERS,
            json=_assignment(task["task_id"], allowed_domains=[DOMAIN, "first.example.net"]),
        )
        assert second.json()["escalation"]["escalated"] is True
        assert second.json()["escalation"]["requested_scope_delta"] == {
            "allowed_domain": "second.example.net"
        }

        deltas = await store.fetchall(
            "SELECT requested_scope_delta_json, status FROM browser_escalations "
            "WHERE task_id = ? ORDER BY created_at_ms", (task["task_id"],)
        )
        assert len(deltas) == 2
        titles = await store.fetchall("SELECT title, status FROM decisions ORDER BY title")
        assert len(titles) == 2
        # The owner is told which domain, not just that "scope" is needed.
        assert any("second.example.net" in str(t["title"]) for t in titles)


async def test_a_task_waiting_on_the_owner_cannot_be_re_run(tmp_path):
    """One question, asked once. A task with an open question is not runnable,
    so a second attempt cannot quietly raise a duplicate of it."""
    worker = _ScriptedWorker([ProposedAction(kind="navigate", domain="first.example.net")])
    ac, _api, store = await _client(tmp_path, worker=worker)
    async with ac:
        task = await _make_task(ac)
        await ac.post("/v1/browser/assignments", headers=HEADERS,
                      json=_assignment(task["task_id"]))
        worker.actions = [ProposedAction(kind="navigate", domain="first.example.net")]
        again = await ac.post("/v1/browser/assignments", headers=HEADERS,
                              json=_assignment(task["task_id"]))
        assert again.status_code == 409
        assert "WAITING_FOR_OWNER" in again.json()["detail"]
        assert len(await store.fetchall("SELECT * FROM browser_escalations")) == 1
        assert len(await store.fetchall("SELECT * FROM decisions")) == 1


async def test_an_answered_question_is_not_asked_again(tmp_path):
    """An approval that did not unblock the run is a different problem, and
    re-presenting the same resolved decision would be a loop."""
    worker = _ScriptedWorker([ProposedAction(kind="navigate", domain="first.example.net")])
    ac, _api, store = await _client(tmp_path, worker=worker)
    async with ac:
        task = await _make_task(ac)
        await ac.post("/v1/browser/assignments", headers=HEADERS,
                      json=_assignment(task["task_id"]))
        row = await store.fetchone(
            "SELECT decision_id FROM browser_escalations WHERE task_id = ?", (task["task_id"],)
        )
        await store.execute("UPDATE decisions SET status='APPROVED' WHERE id = ?",
                            (row["decision_id"],))
        # The widening is granted, but the resumed assignment is re-issued at the
        # original scope, so the worker walks into the very same wall again.
        worker.actions = [ProposedAction(kind="navigate", domain="first.example.net")]
        again = await ac.post(
            "/v1/browser/assignments", headers=HEADERS,
            json=_assignment(task["task_id"]),
        )
        escalation = again.json()["escalation"]
        assert escalation["escalated"] is False
        assert escalation["reason_code"] == "BROWSER_ESCALATION_ALREADY_SATISFIED"
        assert escalation["status"] == BrowserTaskStatus.FAILED.value
        assert len(await store.fetchall("SELECT * FROM decisions")) == 1


# ------------------------------------------------ what the question carries


async def test_the_question_carries_evidence_scope_and_a_real_risk_line(tmp_path):
    """§§184-185 — an approval prompt is only as good as what the person can see."""
    worker = _ScriptedWorker([ProposedAction(kind="navigate", domain="statements.example.net")])
    ac, _api, store = await _client(tmp_path, worker=worker)
    async with ac:
        task = await _make_task(ac)
        await ac.post(
            f"/v1/browser/tasks/{task['task_id']}/evidence", headers=HEADERS,
            json={"kind": "observation", "url": f"https://{DOMAIN}/statements"},
        )
        await ac.post("/v1/browser/assignments", headers=HEADERS,
                      json=_assignment(task["task_id"]))

        row = await store.fetchone(
            "SELECT * FROM browser_escalations WHERE task_id = ?", (task["task_id"],)
        )
        assert row["boundary_type"] == BrowserBoundaryType.OWNER_EXTENSION_REQUIRED.value
        assert "statements.example.net" in row["summary"]
        assert "statements.example.net" in row["why_required"]
        assert DOMAIN in row["why_required"]
        # The risk line says what approving does and does not do.
        assert "does not" in row["risk_summary"]
        assert row["expires_at_ms"] is not None
        evidence = json.loads(str(row["evidence_refs_json"]))
        assert evidence and all(ref.startswith("browser-evidence://") for ref in evidence)

        listed = (await ac.get("/v1/browser/escalations")).json()
        assert listed[0]["actionable"] is True
        assert listed[0]["expired"] is False
        assert listed[0]["requested_scope_delta"] == {"allowed_domain": "statements.example.net"}
        assert listed[0]["evidence_refs"] == evidence


async def test_an_open_question_does_not_hold_the_browser_lease(tmp_path):
    """Waiting on a person can take hours; a held profile lease cannot."""
    worker = _ScriptedWorker([ProposedAction(kind="navigate", domain="first.example.net")])
    ac, _api, store = await _client(tmp_path, worker=worker)
    async with ac:
        task = await _make_task(ac)
        lease = await ac.post(
            "/v1/browser/leases", headers=HEADERS,
            json={"profile_alias": "public_research", "task_id": task["task_id"]},
        )
        assert lease.status_code == 200
        await ac.post("/v1/browser/assignments", headers=HEADERS,
                      json=_assignment(task["task_id"]))

        profile = await store.fetchone(
            "SELECT lease_holder FROM browser_profiles WHERE profile_alias = 'public_research'"
        )
        assert profile["lease_holder"] is None
        # The escalation still records which session raised the question.
        row = await store.fetchone(
            "SELECT session_lease_ref FROM browser_escalations WHERE task_id = ?",
            (task["task_id"],),
        )
        assert row["session_lease_ref"] == lease.json()["lease_id"]
        # And the profile is immediately usable by another task.
        retaken = await ac.post(
            "/v1/browser/leases", headers=HEADERS,
            json={"profile_alias": "public_research", "task_id": "other-task"},
        )
        assert retaken.status_code == 200


# ---------------------------------------------------------------- expiry


async def test_a_stale_question_expires_and_a_late_yes_cannot_authorize(tmp_path):
    """A late approval is not approval of anything that still exists: the lease
    is released and the page the worker was looking at is gone."""
    worker = _ScriptedWorker([ProposedAction(kind="navigate", domain="first.example.net")])
    ac, _api, store = await _client(tmp_path, worker=worker)
    async with ac:
        task = await _make_task(ac)
        await ac.post("/v1/browser/assignments", headers=HEADERS,
                      json=_assignment(task["task_id"]))
        row = await store.fetchone(
            "SELECT escalation_id, decision_id FROM browser_escalations WHERE task_id = ?",
            (task["task_id"],),
        )
        await store.execute(
            "UPDATE browser_escalations SET expires_at_ms = 1 WHERE escalation_id = ?",
            (row["escalation_id"],),
        )
        # The owner answers, but far too late.
        await store.execute("UPDATE decisions SET status='APPROVED' WHERE id = ?",
                            (row["decision_id"],))

        resumed = await ac.post(
            "/v1/browser/assignments", headers=HEADERS,
            json=_assignment(task["task_id"], allowed_domains=[DOMAIN, "first.example.net"]),
        )
        assert resumed.status_code == 409
        assert "EXPIRED" in resumed.json()["detail"]
        assert await store.fetchall("SELECT * FROM browser_scope_authorizations") == []

        escalation = await store.fetchone(
            "SELECT status FROM browser_escalations WHERE escalation_id = ?",
            (row["escalation_id"],),
        )
        assert escalation["status"] == BrowserEscalationStatus.EXPIRED.value
        listed = (await ac.get("/v1/browser/escalations")).json()
        assert listed[0]["actionable"] is False
        assert listed[0]["expired"] is True
