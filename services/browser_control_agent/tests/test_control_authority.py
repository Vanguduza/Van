"""Rev 1.5 §13.2 — the six checks, driven by the cases where they matter.

The agent is the only cross-host bridge to a Chromium holding the owner's logged-in
sessions, so the interesting tests are all refusals, and specifically refusals of requests
that are *almost* right: the correct caller with a lease that has been preempted, the
correct lease on a task that belongs to another session, a task that has spent its budget,
a read that does not need a lease and must therefore still work when the lease is gone.

What this does not test, and cannot: that the CDP conversation behind each operation does
what its name says. That needs a Chromium and is RB-010/RB-117, a host gate.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from services.browser_control_agent.agent import (
    FORBIDDEN_CDP_METHODS,
    PERMITTED_CDP_METHODS,
    BrowserControlAgent,
    Call,
)
from services.browser_control_agent.authority import (
    ControlAgentRefused,
    ControlAuthority,
    ControlLease,
    Operation,
    Refusal,
    Scope,
    ServiceIdentity,
    TaskGrant,
    SCOPE_ALLOWS,
)

NOW = 1_700_000_000_000
#: The agent's own entry point takes no clock — production has one — so the tests that go
#: through `invoke` need a lease that is live against the real one.
REAL_SOON = int(time.time() * 1000) + 600_000
HARNESS = "browser-harness.trading-core.van.internal"
STAGEHAND = "stagehand.trading-core.van.internal"


class RecordingCdp:
    """Records every CDP method the handlers send, and answers plausibly."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, dict]] = []

    async def send(self, target_id: str, method: str, params: dict) -> dict:
        self.sent.append((target_id, method, params))
        return {
            "sessionId": "cdp-1",
            "frameId": "frame-1",
            "root": {"nodeId": 1},
            "nodeId": 7,
            "outerHTML": "<p>hello</p>",
            "nodes": [{"nodeId": 1, "role": "document"}],
            "entries": [{"url": "https://example.test"}],
            "currentIndex": 0,
            "data": "cHVyZQ==",
        }

    @property
    def methods(self) -> list[str]:
        return [method for _, method, _ in self.sent]


def _authority(
    *,
    scope: Scope = Scope.ACTUATE,
    budget: int = 10,
    generation: int = 3,
    holder: str = HARNESS,
    expires_at_ms: int = REAL_SOON,
    caller_scopes: frozenset[Scope] | None = None,
) -> tuple[ControlAuthority, TaskGrant]:
    task = TaskGrant(task_id="task-1", session_id="ibs_1", scope=scope, step_budget=budget)
    authority = ControlAuthority(
        callers={
            HARNESS: ServiceIdentity(
                HARNESS,
                caller_scopes if caller_scopes is not None else frozenset(Scope),
            ),
            STAGEHAND: ServiceIdentity(STAGEHAND, frozenset({Scope.OBSERVE})),
        },
        leases={
            "bctl_1": ControlLease(
                lease_id="bctl_1", session_id="ibs_1", generation=generation,
                holder=holder, expires_at_ms=expires_at_ms,
            )
        },
        tasks={"task-1": task},
    )
    return authority, task


def _authorize(authority: ControlAuthority, **overrides):
    kwargs = dict(
        caller_common_name=HARNESS,
        operation=Operation.NAVIGATE,
        session_id="ibs_1",
        lease_id="bctl_1",
        lease_generation=3,
        task_id="task-1",
        now_ms=NOW,
    )
    kwargs.update(overrides)
    return authority.authorize(**kwargs)


class TestTheSixChecks:

    def test_a_correct_request_is_admitted_and_costs_a_step(self):
        """The other half of every refusal below: a gate that refused everything passes
        all of them and none of this."""
        authority, task = _authority()
        _authorize(authority)
        assert task.steps_used == 1
        assert task.journal[-1][2] == "admitted"

    def test_an_unknown_caller_learns_nothing_else(self):
        authority, _ = _authority()
        with pytest.raises(ControlAgentRefused) as caught:
            _authorize(authority, caller_common_name="someone-else")
        assert caught.value.reason is Refusal.UNKNOWN_CALLER

    def test_a_task_on_another_session_is_refused_as_unknown(self):
        """Not "wrong session": a caller that can tell those apart can enumerate tasks."""
        authority, _ = _authority()
        with pytest.raises(ControlAgentRefused) as caught:
            _authorize(authority, session_id="ibs_other")
        assert caught.value.reason is Refusal.UNKNOWN_SESSION

    def test_a_caller_without_the_task_s_scope_is_refused(self):
        authority, _ = _authority(scope=Scope.ACTUATE)
        with pytest.raises(ControlAgentRefused) as caught:
            _authorize(authority, caller_common_name=STAGEHAND)
        assert caught.value.reason is Refusal.CALLER_NOT_PERMITTED

    def test_an_observe_task_may_not_actuate(self):
        authority, task = _authority(scope=Scope.OBSERVE)
        with pytest.raises(ControlAgentRefused) as caught:
            _authorize(authority, operation=Operation.DISPATCH_INPUT)
        assert caught.value.reason is Refusal.OUT_OF_SCOPE
        assert task.steps_used == 0, "a refused call must not spend the budget"

    def test_a_preempted_lease_is_refused_although_its_id_is_still_correct(self):
        """ADR-RB-007, and the reason the generation exists at all.

        The owner took control back. The agent is still holding the lease id it was given,
        which has not changed — only the generation has. An agent that checked the id alone
        would keep typing into a page the owner is now using.
        """
        authority, _ = _authority(generation=4)
        with pytest.raises(ControlAgentRefused) as caught:
            _authorize(authority, lease_generation=3)
        assert caught.value.reason is Refusal.LEASE_SUPERSEDED

    def test_an_expired_lease_is_refused(self):
        authority, _ = _authority(expires_at_ms=NOW - 1)
        with pytest.raises(ControlAgentRefused) as caught:
            _authorize(authority)
        assert caught.value.reason is Refusal.LEASE_EXPIRED

    def test_a_lease_held_by_someone_else_is_refused(self):
        authority, _ = _authority(holder="another-service")
        with pytest.raises(ControlAgentRefused) as caught:
            _authorize(authority)
        assert caught.value.reason is Refusal.LEASE_NOT_HELD

    def test_a_lease_for_a_different_session_is_refused(self):
        authority, task = _authority()
        task.session_id = "ibs_1"
        authority._leases["bctl_1"].session_id = "ibs_elsewhere"
        with pytest.raises(ControlAgentRefused) as caught:
            _authorize(authority)
        assert caught.value.reason is Refusal.LEASE_UNKNOWN

    def test_the_step_budget_bounds_a_task_that_has_gone_wrong(self):
        """The bound is per task, not per second: a stuck loop that is rate-limited runs
        slowly forever, which is not a bound."""
        authority, task = _authority(budget=2)
        _authorize(authority)
        _authorize(authority)
        with pytest.raises(ControlAgentRefused) as caught:
            _authorize(authority)
        assert caught.value.reason is Refusal.STEP_BUDGET_EXHAUSTED
        assert task.steps_used == 2

    def test_a_finished_task_cannot_be_resumed(self):
        authority, task = _authority()
        task.finished = True
        with pytest.raises(ControlAgentRefused) as caught:
            _authorize(authority)
        assert caught.value.reason is Refusal.TASK_FINISHED

    def test_the_caller_cannot_spend_its_own_budget(self):
        """The step is counted inside `authorize`, so a caller that never reports back
        still cannot take a second step for free."""
        authority, task = _authority(budget=1)
        _authorize(authority)
        assert task.steps_remaining == 0


class TestReadsDoNotNeedALease:

    def test_evidence_can_still_be_captured_after_the_owner_takes_control(self):
        """The moment the lease is preempted is the moment the evidence matters most.

        A design where every operation needed a live lease would lose the screenshot of
        whatever went wrong, at exactly the point something went wrong.
        """
        authority, _ = _authority(scope=Scope.EVIDENCE, generation=9)
        admitted = _authorize(
            authority, operation=Operation.CAPTURE_EVIDENCE, lease_generation=1,
        )
        assert admitted.steps_used == 1

    def test_a_read_still_respects_the_scope(self):
        authority, _ = _authority(scope=Scope.EVIDENCE)
        with pytest.raises(ControlAgentRefused) as caught:
            _authorize(authority, operation=Operation.OBSERVE_DOWNLOAD)
        assert caught.value.reason is Refusal.OUT_OF_SCOPE

    def test_every_actuating_operation_is_declared_as_one(self):
        """The `actuates` property decides what needs a lease; a mislabelled operation is
        an actuation with no lease check and no test would see it."""
        assert Operation.NAVIGATE.actuates
        assert Operation.DISPATCH_INPUT.actuates
        assert Operation.ATTACH.actuates
        assert not Operation.QUERY_DOM.actuates
        assert not Operation.CAPTURE_EVIDENCE.actuates
        assert not Operation.OBSERVE_DOWNLOAD.actuates


class TestTheAgentIsNarrow:

    def test_every_operation_has_a_handler(self):
        from services.browser_control_agent.agent import _HANDLERS

        assert set(_HANDLERS) == set(Operation)

    def test_every_operation_is_reachable_from_some_scope(self):
        """An operation no scope admits is either dead or a hole waiting for a scope."""
        reachable = set().union(*SCOPE_ALLOWS.values())
        assert reachable == set(Operation)

    def test_no_handler_can_send_a_forbidden_cdp_method(self):
        """§13.2's list, made checkable rather than asserted in prose."""
        assert not (PERMITTED_CDP_METHODS & FORBIDDEN_CDP_METHODS)

    def test_what_the_handlers_actually_send_is_within_the_allowlist(self):
        """Drives every operation and compares the CDP traffic to the declared set.

        This is the test that fails if someone adds a `Runtime.evaluate` to a handler: the
        allowlist is only a claim until something compares it with the code.
        """
        cdp = RecordingCdp()
        for operation in Operation:
            # Each operation is driven under a scope that admits it; which scope that is
            # is read from the table rather than repeated here.
            scope = next(s for s, allowed in SCOPE_ALLOWS.items() if operation in allowed)
            authority, _ = _authority(scope=scope)
            agent = BrowserControlAgent(authority=authority, cdp=cdp)
            asyncio.run(
                agent.invoke(
                    caller_common_name=HARNESS,
                    call=Call(
                        operation=operation,
                        session_id="ibs_1",
                        target_id="target-1",
                        lease_id="bctl_1",
                        lease_generation=3,
                        task_id="task-1",
                        params={"url": "https://example.test", "selector": "h1"},
                    ),
                )
            )
        assert set(cdp.methods) <= PERMITTED_CDP_METHODS, (
            f"a handler sends {sorted(set(cdp.methods) - PERMITTED_CDP_METHODS)}"
        )

    def test_navigate_refuses_a_scheme_that_is_not_the_web(self):
        """`file:///` reads the host's disk into a page the owner is watching."""
        cdp = RecordingCdp()
        authority, _ = _authority()
        agent = BrowserControlAgent(authority=authority, cdp=cdp)
        for url in ("file:///etc/passwd", "chrome://settings", "javascript:alert(1)", ""):
            with pytest.raises(ValueError):
                asyncio.run(
                    agent.invoke(
                        caller_common_name=HARNESS,
                        call=Call(
                            operation=Operation.NAVIGATE,
                            session_id="ibs_1",
                            target_id="target-1",
                            lease_id="bctl_1",
                            lease_generation=3,
                            task_id="task-1",
                            params={"url": url},
                        ),
                    )
                )
        assert "Page.navigate" not in cdp.methods

    def test_a_download_is_reported_and_never_carried(self):
        """A file the agent could return is a file the private VCN carries out of the
        owner's browser profile."""
        cdp = RecordingCdp()
        authority, _ = _authority(scope=Scope.OBSERVE)
        agent = BrowserControlAgent(authority=authority, cdp=cdp)
        result = asyncio.run(
            agent.invoke(
                caller_common_name=HARNESS,
                call=Call(
                    operation=Operation.OBSERVE_DOWNLOAD,
                    session_id="ibs_1",
                    target_id="target-1",
                    lease_id="bctl_1",
                    lease_generation=3,
                    task_id="task-1",
                    params={"known": ["invoice.pdf"]},
                ),
            )
        )
        assert result["transfer"] == "not_through_this_agent"
        assert "IO.read" not in cdp.methods

    def test_nothing_reaches_the_browser_without_being_authorized(self):
        """The ordering guarantee, stated as a test rather than as a comment."""
        cdp = RecordingCdp()
        authority, _ = _authority(scope=Scope.OBSERVE)
        agent = BrowserControlAgent(authority=authority, cdp=cdp)
        with pytest.raises(ControlAgentRefused):
            asyncio.run(
                agent.invoke(
                    caller_common_name=HARNESS,
                    call=Call(
                        operation=Operation.DISPATCH_INPUT,
                        session_id="ibs_1",
                        target_id="target-1",
                        lease_id="bctl_1",
                        lease_generation=3,
                        task_id="task-1",
                        params={},
                    ),
                )
            )
        assert cdp.sent == [], "the browser was touched by a call that was refused"


class TestTheJournal:

    def test_a_refusal_is_recorded_with_its_reason(self):
        """A Mission whose automation was refused needs to say why, not that it stopped."""
        authority, task = _authority(scope=Scope.OBSERVE)
        with pytest.raises(ControlAgentRefused):
            _authorize(authority, operation=Operation.NAVIGATE)
        assert task.journal[-1][2] == Refusal.OUT_OF_SCOPE.value
        assert task.journal[-1][1] == Operation.NAVIGATE.value
