"""Rev 1.5 §§5.1, 5.2, 5.4 — the interactive browser session.

An interactive session is a person looking at a remote Chromium through their phone. A
`BrowserTask` is a unit of automated work. They are different lifetimes with different
owners, which is why §5 says not to overload `BrowserTask` with session state: a task ends
when its goal is verified, and a session ends when the owner closes it or the profile lease
cannot be renewed.

Two exclusivity questions are represented separately, because they genuinely are two
questions (ADR-RB-006):

* the **profile lease** decides which session may use a browser profile at all;
* the **control lease** decides who, inside an already-open session, may generate actions.

Conflating them would mean an agent taking control of a page implicitly evicting the owner
from the profile, or an owner holding a profile being unable to hand the keyboard to Hermes
without giving up their tabs.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from van_gateway.browser.models import ProfileLeaseHolderKind

__all__ = [
    "ALLOWED_TRANSITIONS",
    "BrowserControlHolder",
    "BrowserControlLease",
    "BrowserDownload",
    "BrowserDownloadState",
    "BrowserSessionTarget",
    "DURABLE_SESSION_EVENTS",
    "InteractiveBrowserSession",
    "InteractiveSessionState",
    "ProfileLeaseHolderKind",
    "Viewport",
    "may_transition",
]


class InteractiveSessionState(str, Enum):
    """§5.2 — the session ladder.

    `INTERACTIVE` means pixels are flowing and the owner can touch the page. It does **not**
    mean any browser task succeeded: §5.2 is explicit that no UI may infer a completed task
    from this state or from `TERMINATED`, which is the same collapse `P0-EXEC-003` found on
    the mission screen.
    """

    REQUESTED = "REQUESTED"
    AUTHORIZED = "AUTHORIZED"
    ALLOCATING = "ALLOCATING"
    SIGNALING = "SIGNALING"
    CONNECTING = "CONNECTING"
    INTERACTIVE = "INTERACTIVE"
    AGENT_CONTROLLED = "AGENT_CONTROLLED"
    RECONNECTING = "RECONNECTING"
    SUSPENDED = "SUSPENDED"
    TERMINATING = "TERMINATING"
    TERMINATED = "TERMINATED"
    FAILED = "FAILED"

    @property
    def is_terminal(self) -> bool:
        return self in _TERMINAL_STATES

    @property
    def can_actuate(self) -> bool:
        """Whether input may reach the browser at all in this state."""
        return self in {InteractiveSessionState.INTERACTIVE, InteractiveSessionState.AGENT_CONTROLLED}


_TERMINAL_STATES = {InteractiveSessionState.TERMINATED, InteractiveSessionState.FAILED}

#: §5.2 — the permitted transitions, as a table rather than as scattered `if` statements.
#:
#: FAILED is reachable from every non-terminal state, and is deliberately *not* reachable
#: from TERMINATED: a session that ended cleanly cannot be retroactively described as having
#: failed, and one that failed cannot be quietly promoted to a clean end.
ALLOWED_TRANSITIONS: dict[InteractiveSessionState, frozenset[InteractiveSessionState]] = {
    InteractiveSessionState.REQUESTED: frozenset({InteractiveSessionState.AUTHORIZED}),
    InteractiveSessionState.AUTHORIZED: frozenset({InteractiveSessionState.ALLOCATING}),
    InteractiveSessionState.ALLOCATING: frozenset({InteractiveSessionState.SIGNALING}),
    InteractiveSessionState.SIGNALING: frozenset({InteractiveSessionState.CONNECTING}),
    InteractiveSessionState.CONNECTING: frozenset({
        InteractiveSessionState.INTERACTIVE,
        InteractiveSessionState.RECONNECTING,
    }),
    InteractiveSessionState.INTERACTIVE: frozenset({
        InteractiveSessionState.AGENT_CONTROLLED,
        InteractiveSessionState.RECONNECTING,
        InteractiveSessionState.SUSPENDED,
        InteractiveSessionState.TERMINATING,
    }),
    InteractiveSessionState.AGENT_CONTROLLED: frozenset({
        InteractiveSessionState.INTERACTIVE,
        InteractiveSessionState.RECONNECTING,
        InteractiveSessionState.SUSPENDED,
        InteractiveSessionState.TERMINATING,
    }),
    InteractiveSessionState.RECONNECTING: frozenset({
        InteractiveSessionState.INTERACTIVE,
        InteractiveSessionState.SUSPENDED,
        InteractiveSessionState.TERMINATING,
    }),
    InteractiveSessionState.SUSPENDED: frozenset({
        InteractiveSessionState.CONNECTING,
        InteractiveSessionState.TERMINATING,
    }),
    InteractiveSessionState.TERMINATING: frozenset({InteractiveSessionState.TERMINATED}),
    InteractiveSessionState.TERMINATED: frozenset(),
    InteractiveSessionState.FAILED: frozenset(),
}


def may_transition(current: InteractiveSessionState, target: InteractiveSessionState) -> bool:
    """§5.2. FAILED is reachable from any non-terminal state; nothing is reachable from a terminal one."""
    if current.is_terminal:
        return False
    if target is InteractiveSessionState.FAILED:
        return True
    return target in ALLOWED_TRANSITIONS[current]


class BrowserControlHolder(str, Enum):
    """§5.4 — exactly one of these may actuate at a time. Observers are unlimited."""

    OWNER = "OWNER"
    HERMES_DETERMINISTIC = "HERMES_DETERMINISTIC"
    HERMES_STAGEHAND = "HERMES_STAGEHAND"
    SYSTEM_RECOVERY = "SYSTEM_RECOVERY"
    NONE = "NONE"

    @property
    def is_agent(self) -> bool:
        return self in {
            BrowserControlHolder.HERMES_DETERMINISTIC,
            BrowserControlHolder.HERMES_STAGEHAND,
        }


class Viewport(BaseModel):
    """What the device is actually displaying.

    `revision` is the fence for coordinates. §8.1 refuses actuation carrying an old revision
    rather than transforming it: after a Chromium reflow the old coordinates do not describe
    a scaled version of the new page, they describe a different page, and a transform would
    turn a stale tap into a confident wrong tap.
    """

    width: int = Field(gt=0)
    height: int = Field(gt=0)
    device_scale_factor: float = Field(gt=0)
    revision: int = Field(ge=1, default=1)


class InteractiveBrowserSession(BaseModel):
    session_id: str
    owner_device_id: str

    #: One of the aliases in config/browser/profiles.yaml. §0A/B3: an implementation agent
    #: may not invent aliases; a new one is an owner-approved policy amendment.
    profile_alias: str
    profile_lease_id: str | None = None

    state: InteractiveSessionState = InteractiveSessionState.REQUESTED
    active_target_id: str | None = None
    active_url_digest: str | None = None

    viewport: Viewport
    acked_viewport_revision: int | None = None

    requested_fps: int = 60
    negotiated_codec: str | None = None
    negotiated_transport: str | None = None

    control_holder: BrowserControlHolder = BrowserControlHolder.OWNER
    control_lease_id: str | None = None
    control_generation: int = 0

    created_at_ms: int
    connected_at_ms: int | None = None
    last_client_seen_at_ms: int | None = None
    last_profile_lease_renewed_at_ms: int | None = None
    suspended_at_ms: int | None = None
    expires_at_ms: int
    terminated_at_ms: int | None = None
    final_reason: str | None = None

    #: ADR-RB-018 — the Mission its originating command already created, by reference. A
    #: purely manual browsing session legitimately has neither until the owner asks for work.
    mission_id: str | None = None
    originating_command_id: str | None = None
    idempotency_key: str | None = None

    @property
    def owner_readable_state(self) -> str:
        """§48's rule, carried to this surface: no enum reaches the owner."""
        return {
            InteractiveSessionState.REQUESTED: "Asking for a browser",
            InteractiveSessionState.AUTHORIZED: "Allowed, not started",
            InteractiveSessionState.ALLOCATING: "Getting a browser ready",
            InteractiveSessionState.SIGNALING: "Connecting",
            InteractiveSessionState.CONNECTING: "Connecting",
            InteractiveSessionState.INTERACTIVE: "Ready",
            InteractiveSessionState.AGENT_CONTROLLED: "Van is driving",
            InteractiveSessionState.RECONNECTING: "Reconnecting",
            InteractiveSessionState.SUSPENDED: "Paused",
            InteractiveSessionState.TERMINATING: "Closing",
            InteractiveSessionState.TERMINATED: "Closed",
            InteractiveSessionState.FAILED: self.final_reason or "Stopped",
        }[self.state]


class BrowserControlLease(BaseModel):
    """§5.4 — the right to actuate, fenced by a generation.

    Every actuation packet carries `(session_id, control_lease_id, control_generation)`. A
    stale generation is refused server-side, which is what makes "owner touch wins" real:
    the agent's in-flight input is not merely ignored by convention, it names an authority
    that no longer exists.
    """

    control_lease_id: str
    session_id: str
    holder: BrowserControlHolder
    issued_for: str
    issued_at_ms: int
    expires_at_ms: int
    generation: int
    revoked_at_ms: int | None = None
    revoke_reason: str | None = None

    def active(self, now_ms: int) -> bool:
        return self.revoked_at_ms is None and now_ms < self.expires_at_ms


class BrowserSessionTarget(BaseModel):
    """A tab, as the Gateway knows it. The URL is a digest for the same reason evidence is."""

    session_id: str
    target_id: str
    title: str | None = None
    url_digest: str | None = None
    opener_target_id: str | None = None
    is_active: bool = False
    created_at_ms: int
    closed_at_ms: int | None = None


class BrowserDownloadState(str, Enum):
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REFUSED = "REFUSED"


class BrowserDownload(BaseModel):
    download_id: str
    session_id: str
    target_id: str | None = None
    suggested_name: str
    mime_type: str | None = None
    byte_size: int | None = None
    content_sha256: str | None = None
    url_digest: str | None = None
    state: BrowserDownloadState = BrowserDownloadState.STARTED
    failure_reason: str | None = None
    evidence_ref: str | None = None
    created_at_ms: int
    completed_at_ms: int | None = None


#: ADR-RB-008 — what is durable. High-frequency media, pointer motion and telemetry are not
#: in this list and must never be written to the event ledger: an event store that carries
#: every MOVE stops being readable exactly when someone needs to read it.
DURABLE_SESSION_EVENTS = frozenset({
    "session.created",
    "session.profile_attached",
    "session.state_changed",
    "session.url_changed",
    "session.target_opened",
    "session.target_closed",
    "session.control_changed",
    "session.agent_takeover_started",
    "session.agent_takeover_stopped",
    "session.download_created",
    "session.download_completed",
    "session.escalation_raised",
    "session.stream_degraded",
    "session.stream_recovered",
    "session.lease_expired",
    "session.ended",
})
