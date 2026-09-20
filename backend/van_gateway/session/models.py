"""Rev 1.5 §§0B, 20 — the durable VAN⇄Hermes logical session.

The invariant this package exists to make true (§0B):

    No VAN feature may depend directly on one physical Hermes connection.
    Features depend on the durable VAN–Hermes logical session.
    Transports are replaceable carriers underneath it.

So identity is split in two. `van_session_id` and `session_epoch` survive a socket dying,
an ingress switch, a Wi-Fi-to-cellular handoff and a short Gateway restart. `path_id`,
`path_epoch` and the connection id do not, and nothing downstream is allowed to care about
them — except the one place that must: a late envelope from an older path epoch cannot
become a new command (§20.3).

The other half is §0B's warning about claiming continuity that does not exist. Several
protocols over one failed route is protocol diversity, not route diversity, and
`MULTIPATH_HEALTHY` may be claimed only when two independently reachable paths are actually
proven live. Otherwise VAN reports `SINGLE_PATH` — the unflattering status is the honest one.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum

from pydantic import BaseModel, Field

from van_gateway.storage.db import Store

PROTOCOL_VERSION = 1


class SessionState(str, Enum):
    ACTIVE = "ACTIVE"
    #: The client is gone but the session is still resumable with its cursors intact.
    SUSPENDED = "SUSPENDED"
    CLOSED = "CLOSED"


class Direction(str, Enum):
    UPSTREAM = "UPSTREAM"
    DOWNSTREAM = "DOWNSTREAM"


class PathHealth(str, Enum):
    HEALTHY = "HEALTHY"
    SUSPECT = "SUSPECT"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    COOLDOWN = "COOLDOWN"

    @property
    def usable(self) -> bool:
        return self in {PathHealth.HEALTHY, PathHealth.DEGRADED}


class SupervisorState(str, Enum):
    """§20.7. `MULTIPATH_HEALTHY` is a claim about the world, not a preference."""

    STARTING = "STARTING"
    PRIMARY_CONNECTING = "PRIMARY_CONNECTING"
    MULTIPATH_HEALTHY = "MULTIPATH_HEALTHY"
    SINGLE_PATH = "SINGLE_PATH"
    FAILOVER_PREPARING = "FAILOVER_PREPARING"
    FAILOVER_COMMITTING = "FAILOVER_COMMITTING"
    RECOVERING = "RECOVERING"
    STORE_AND_FORWARD = "STORE_AND_FORWARD"
    OFFLINE_LOCAL = "OFFLINE_LOCAL"


class PathClass(str, Enum):
    """§20.5 — the three-level continuity ladder."""

    #: WSS, full duplex. The normal low-latency path.
    A_REALTIME = "A_REALTIME"
    #: HTTP/2 upstream POST + streaming downstream. Deliberately different enough from
    #: WebSocket handling to survive a middlebox that breaks WebSockets while ordinary
    #: HTTPS still works.
    B_STREAMING = "B_STREAMING"
    #: The existing REST command and event APIs. Slower, and always available.
    C_REPLAY_FLOOR = "C_REPLAY_FLOOR"


class CommandStorability(str, Enum):
    """§20.14 — what the local outbox may do with a command while there is no path.

    Classification happens before storage, not at replay time. A command stored first and
    judged later is a command that has already been kept.
    """

    SAFE_TO_RETRY = "SAFE_TO_RETRY"
    STORE_UNTIL_TTL = "STORE_UNTIL_TTL"
    #: Anything whose meaning depends on the moment: "read that back", "cancel it". Asking
    #: again costs the owner a sentence; replaying it silently costs them a surprise.
    REQUIRE_RECONFIRM_ON_RECONNECT = "REQUIRE_RECONFIRM_ON_RECONNECT"
    #: Irreversible or owner-approval-bearing work. §20.14's list exists so that a queue
    #: flushing after an hour offline cannot perform one.
    NEVER_STORE = "NEVER_STORE"


class TransportPathDescriptor(BaseModel):
    """§20.6 — a candidate carrier.

    `route_id` is the field that makes route diversity checkable. Two descriptors with
    different protocols and the same `route_id` are two ways to use one road.
    """

    path_id: str
    path_class: PathClass
    protocol: str
    endpoint: str
    route_id: str
    priority: int = 100
    supports_full_duplex: bool = False
    supports_streaming_downlink: bool = False
    metered_allowed: bool = True
    standby_mode: str = "COLD"


class SessionEnvelope(BaseModel):
    """§20.4 — transport-independent. The same bytes mean the same thing on any carrier.

    High-frequency WebRTC browser input deliberately does not use this: §20.4 keeps the
    pixel-adjacent path out of the semantic envelope, and a pointer MOVE wrapped in this
    would cost more to parse than to deliver.
    """

    protocol_version: int = PROTOCOL_VERSION
    message_id: str
    van_session_id: str
    session_epoch: int
    path_epoch: int
    device_id: str
    direction: Direction
    kind: str
    created_at_ms: int
    expires_at_ms: int | None = None

    turn_id: str | None = None
    command_id: str | None = None
    response_id: str | None = None
    event_id: str | None = None

    idempotency_key: str | None = None
    correlation_id: str | None = None
    payload_digest: str | None = None
    payload: dict = Field(default_factory=dict)

    def digest(self) -> str:
        """The digest the Gateway compares on a resubmission (§20.12).

        Computed from the payload rather than trusted from the envelope, because the whole
        point is to detect a *different* payload arriving under a key that has been seen.
        """
        return hashlib.sha256(
            json.dumps(self.payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()


class VanHermesSession(BaseModel):
    """§20.3 — the identity every feature binds to."""

    van_session_id: str
    session_epoch: int
    device_id: str
    principal_type: str = "OWNER_DEVICE"
    state: SessionState = SessionState.ACTIVE
    created_at_ms: int
    last_resumed_at_ms: int | None = None
    last_client_event_seq: int = 0
    last_server_ack_seq: int = 0
    #: The only path epoch that may produce new upstream work (§20.9).
    authoritative_path_epoch: int = 0
    closed_at_ms: int | None = None


class ResumeRequest(BaseModel):
    """§20.11 — what the client says it already has."""

    van_session_id: str
    session_epoch: int
    device_id: str
    last_event_seq: int = 0
    pending_command_ids: list[str] = Field(default_factory=list)
    active_turn_id: str | None = None
    active_response_id: str | None = None
    last_received_response_segment: int = 0
    last_spoken_speech_segment: int = 0
    path_id: str | None = None
    route_id: str | None = None


class ResumeResult(BaseModel):
    """§20.11 — what the Gateway says is actually true."""

    accepted: bool
    session_epoch: int
    new_path_epoch: int
    authoritative_event_cursor: int
    replay_from_seq: int
    command_states: dict[str, str] = Field(default_factory=dict)
    response_state: dict | None = None
    refusal: str | None = None


class CommandAdmission(str, Enum):
    """§20.12 — the three answers to a resubmitted command."""

    ADMITTED = "ADMITTED"
    #: Same key, same payload: the client lost the acknowledgement, not the command.
    ALREADY_KNOWN = "ALREADY_KNOWN"
    #: Same key, different payload. Never executed: one of the two is not what the owner
    #: asked for, and the Gateway cannot tell which.
    CONFLICT = "CONFLICT"


def store_dumps(value: object) -> str:
    return Store.dumps(value)
