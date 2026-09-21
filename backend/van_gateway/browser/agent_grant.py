"""Rev 1.5 §§22.1, 22.2, 22.3 — what Hermes is given when it drives the owner's browser,
and what happens to it when the owner takes the browser back.

§22.2 is a list of nine things the agent receives and five it does not, and the five are
the interesting half:

    device HMAC          proves a command came from the owner's phone
    owner signing key    signs owner approvals
    VAN internal token   reaches every privileged Gateway route
    raw browser cookies  *is* the owner's logged-in session
    unbounded scope      the absence of all the limits above

An agent that held any of them could do the thing it was delegated to do and then anything
else. So the grant is a value object with exactly the nine fields, and a test asserts the
five are not among them — because the way this fails is not that someone adds `cookies`
deliberately, it is that a convenience field grows into carrying one.

§22.3 is the other half and it is marked mandatory: the owner's first DOWN event
invalidates the control generation, and **queued agent actions are discarded**. A "Take
over" button that only changes what the phone draws is explicitly called insufficient. The
discard is what this module adds to the lease machinery, which already moves the
generation.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class AgentGrantState(str, Enum):
    ACTIVE = "ACTIVE"
    #: The owner touched the viewport. Every queued action went with it.
    PREEMPTED = "PREEMPTED"
    COMPLETED = "COMPLETED"
    EXPIRED = "EXPIRED"
    #: Budget or deadline reached before the goal did.
    EXHAUSTED = "EXHAUSTED"

    @property
    def may_act(self) -> bool:
        return self is AgentGrantState.ACTIVE


#: §22.2's five. Named so the refusal can say which one was asked for, and so the test that
#: keeps them out has something to compare against.
FORBIDDEN_GRANT_FIELDS = frozenset(
    {
        "device_hmac",
        "device_secret",
        "owner_signing_key",
        "owner_approval_key",
        "internal_control_token",
        "van_internal_token",
        "cookies",
        "raw_cookies",
        "browser_cookies",
        "profile_secret",
        "session_storage",
    }
)


class AgentGrantError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class AgentGrant:
    """§22.2 — the nine fields, and nothing else.

    `allowed_domains` is a list rather than a pattern on purpose. A pattern is a thing
    somebody gets subtly wrong once and then an agent is browsing somewhere nobody
    intended; an explicit list is auditable by reading it.
    """

    grant_id: str
    session_id: str
    target_id: str
    goal: str
    allowed_domains: tuple[str, ...]
    action_class: str
    step_budget: int
    deadline_ms: int
    control_lease_id: str
    control_generation: int

    state: AgentGrantState = AgentGrantState.ACTIVE
    steps_used: int = 0
    #: Actions the agent has asked for and not yet performed. Discarded on preemption.
    queued_actions: list[str] = field(default_factory=list)
    preempted_at_ms: int | None = None

    @property
    def steps_remaining(self) -> int:
        return max(0, self.step_budget - self.steps_used)

    def expired(self, now_ms: int) -> bool:
        return now_ms >= self.deadline_ms


def scope_payload(grant: AgentGrant) -> dict:
    """What actually crosses to the agent.

    Built explicitly rather than by serialising the object, so a field added to `AgentGrant`
    for the Gateway's own bookkeeping does not silently become something the agent
    receives. That is the mechanism by which a forbidden field arrives: not a decision, a
    default.
    """
    return {
        "session_id": grant.session_id,
        "target_id": grant.target_id,
        "goal": grant.goal,
        "allowed_domains": list(grant.allowed_domains),
        "action_class": grant.action_class,
        "step_budget": grant.step_budget,
        "steps_remaining": grant.steps_remaining,
        "deadline_ms": grant.deadline_ms,
        "control_lease_id": grant.control_lease_id,
        "control_generation": grant.control_generation,
    }


class AgentGrantService:
    """§§22.1–22.3. Issues grants, spends their budget, and destroys them on preemption."""

    def __init__(self) -> None:
        self._grants: dict[str, AgentGrant] = {}
        self._by_session: dict[str, list[str]] = {}

    def issue(
        self,
        *,
        grant_id: str,
        session_id: str,
        target_id: str,
        goal: str,
        allowed_domains: tuple[str, ...],
        action_class: str,
        step_budget: int,
        deadline_ms: int,
        control_lease_id: str,
        control_generation: int,
        extra: dict | None = None,
    ) -> AgentGrant:
        """Mint a grant, refusing outright if a caller tried to attach anything forbidden.

        `extra` exists so that a caller passing through a dictionary from somewhere else
        is checked rather than trusted. Without it, the forbidden-field rule would only
        apply to code that already knows about it.
        """
        if extra:
            leaked = FORBIDDEN_GRANT_FIELDS & set(extra)
            if leaked:
                raise AgentGrantError(f"agent_grant_carries_credential:{sorted(leaked)[0]}")
        if step_budget <= 0:
            raise AgentGrantError("agent_grant_needs_a_budget")
        if not allowed_domains:
            # An empty list is not "everywhere", and treating it as such is how an
            # unbounded scope arrives without anyone choosing one.
            raise AgentGrantError("agent_grant_needs_allowed_domains")

        grant = AgentGrant(
            grant_id=grant_id,
            session_id=session_id,
            target_id=target_id,
            goal=goal,
            allowed_domains=allowed_domains,
            action_class=action_class,
            step_budget=step_budget,
            deadline_ms=deadline_ms,
            control_lease_id=control_lease_id,
            control_generation=control_generation,
        )
        self._grants[grant_id] = grant
        self._by_session.setdefault(session_id, []).append(grant_id)
        return grant

    def spend(self, grant_id: str, action: str, *, now_ms: int | None = None) -> AgentGrant:
        """Admit one agent action, or refuse with the reason.

        The step is counted here, for the same reason it is counted inside the control
        agent's `authorize`: a budget the caller decrements is a budget the caller controls.
        """
        now = int(time.time() * 1000) if now_ms is None else now_ms
        grant = self._grants.get(grant_id)
        if grant is None:
            raise AgentGrantError("agent_grant_unknown")
        if grant.state is AgentGrantState.PREEMPTED:
            # §22.3 — the distinctive refusal. Not "expired", not "denied": the owner took
            # the browser back, and the agent needs to know that specifically.
            raise AgentGrantError("agent_grant_preempted_by_owner")
        if not grant.state.may_act:
            raise AgentGrantError(f"agent_grant_not_active:{grant.state.value}")
        if grant.expired(now):
            grant.state = AgentGrantState.EXPIRED
            raise AgentGrantError("agent_grant_deadline_passed")
        if grant.steps_remaining == 0:
            grant.state = AgentGrantState.EXHAUSTED
            raise AgentGrantError("agent_grant_step_budget_exhausted")

        grant.steps_used += 1
        return grant

    def queue(self, grant_id: str, action: str) -> None:
        """An action the agent intends to perform. Held so preemption can discard it."""
        grant = self._grants.get(grant_id)
        if grant is None or not grant.state.may_act:
            return
        grant.queued_actions.append(action)

    def owner_preempted(
        self, session_id: str, *, new_generation: int, now_ms: int | None = None
    ) -> list[str]:
        """§22.3 — the owner touched the viewport. Returns what was discarded.

        Every grant on this session whose generation is now stale is preempted and its
        queue emptied. Returning the discarded actions rather than dropping them silently
        is what lets the Mission record say *what* did not happen — an agent that was about
        to submit a form and did not is a fact the owner may need.
        """
        now = int(time.time() * 1000) if now_ms is None else now_ms
        discarded: list[str] = []
        for grant_id in self._by_session.get(session_id, []):
            grant = self._grants[grant_id]
            if grant.control_generation >= new_generation:
                continue
            if grant.state is not AgentGrantState.ACTIVE:
                continue
            grant.state = AgentGrantState.PREEMPTED
            grant.preempted_at_ms = now
            discarded.extend(grant.queued_actions)
            grant.queued_actions.clear()
        return discarded

    def complete(self, grant_id: str) -> None:
        grant = self._grants.get(grant_id)
        if grant is not None and grant.state is AgentGrantState.ACTIVE:
            grant.state = AgentGrantState.COMPLETED
            grant.queued_actions.clear()

    def get(self, grant_id: str) -> AgentGrant | None:
        return self._grants.get(grant_id)

    def active_for(self, session_id: str) -> list[AgentGrant]:
        return [
            self._grants[gid]
            for gid in self._by_session.get(session_id, [])
            if self._grants[gid].state is AgentGrantState.ACTIVE
        ]


def domain_allowed(url: str, allowed_domains: tuple[str, ...]) -> bool:
    """Whether a URL is inside the grant's scope.

    Host-suffix matching with a leading-dot boundary. `example.com` admits
    `www.example.com` and refuses `notexample.com` — the check that a naive
    `endswith` gets wrong, and the way an agent ends up on a domain an attacker
    registered to look like the one it was allowed.
    """
    if not url.startswith(("http://", "https://")):
        return False
    host = url.split("://", 1)[1].split("/", 1)[0].split("@")[-1].split(":")[0].lower()
    if not host:
        return False
    return any(
        host == domain.lower() or host.endswith("." + domain.lower())
        for domain in allowed_domains
    )
