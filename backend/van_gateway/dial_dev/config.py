"""Static contract for the DIAL development proxy: paths, closed sets, configuration."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: What Android calls. Nothing under this prefix is reachable without owner-device auth.
PREFIX = "/v1/dial-dev"
#: What DIAL serves on `dial-control`. Only the gateway ever builds this path.
UPSTREAM_PREFIX = "/v1/dev"

ACTIONS_PATH = f"{PREFIX}/actions"
EVENTS_PATH = f"{PREFIX}/events"

#: §3.3 — the owner's entire vocabulary for DIAL development. Anything else is refused
#: before it leaves the gateway; there is no pass-through for an unknown action.
ACTIONS: frozenset[str] = frozenset({
    "STEER_TASK",
    "PAUSE_TASK_SAFE",
    "RESUME_TASK",
    "REQUEST_CHECKPOINT",
    "REQUEST_REVIEW",
    "REVOKE_TASK",
    "DECIDE",
    "PAUSE_MISSION",
    "RESUME_MISSION",
    "REPRIORITISE",
})

#: Actions that address one task and therefore must name it.
TASK_SCOPED_ACTIONS: frozenset[str] = frozenset({
    "STEER_TASK",
    "PAUSE_TASK_SAFE",
    "RESUME_TASK",
    "REQUEST_CHECKPOINT",
    "REQUEST_REVIEW",
    "REVOKE_TASK",
})

#: `DECIDE` carries one of these in `params.decision`.
DECISIONS: frozenset[str] = frozenset({"APPROVE", "REJECT"})

#: §3.2 / Rev 1 §16.3 — the task views DIAL projects.
TASK_VIEWS: tuple[str, ...] = (
    "now", "next", "in_progress", "needs_me", "blocked",
    "review", "failed", "completed", "all",
)

#: §3.2 — hub children that are a single un-parameterised read each.
HUB_CHILDREN: tuple[str, ...] = ("reviews", "memory", "research", "design", "ci", "security")

#: §3.2 — the terminal tail is bounded at 200 lines by contract.
TERMINAL_TAIL_MAX_LINES = 200

#: §3.1 — every projection read carries exactly this envelope.
ENVELOPE_KEYS: tuple[str, ...] = (
    "projection_revision", "observed_at", "sources", "freshness_ms", "degraded", "data",
)

#: One path segment of an identifier DIAL issues (project, task, workspace, evidence ref).
#: No slash, no dot-dot, no whitespace: a segment that could re-route the upstream request
#: to a different DIAL endpoint is refused rather than escaped into one.
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:\-]{0,159}$")


def valid_identifier(value: str) -> bool:
    return bool(_IDENTIFIER.match(value or "")) and ".." not in value


#: The shortest DIAL-scoped credential the gateway will present. Same floor as the ARTEMIS
#: console proxy: a short token file is a misconfiguration, not a secret.
MIN_TOKEN_LENGTH = 32


@dataclass(frozen=True)
class DialDevConfig:
    enabled: bool = False
    base_url: str = ""
    token_file: str = ""
    timeout_s: float = 10.0
    stale_ms: int = 30_000
    workspaces_stale_ms: int = 10_000
    attention_enabled: bool = True

    @classmethod
    def from_settings(cls, settings: Any) -> "DialDevConfig":
        return cls(
            enabled=bool(settings.dial_dev_enabled),
            base_url=str(settings.dial_dev_base_url or "").rstrip("/"),
            token_file=str(settings.dial_dev_token_file or ""),
            timeout_s=max(0.5, float(settings.dial_dev_timeout_s)),
            stale_ms=max(1, int(settings.dial_dev_stale_ms)),
            workspaces_stale_ms=max(1, int(settings.dial_dev_workspaces_stale_ms)),
            attention_enabled=bool(settings.dial_dev_attention_enabled),
        )

    @property
    def configured(self) -> bool:
        return (
            self.enabled
            and self.base_url.startswith(("http://", "https://"))
            and bool(self.token_file)
            and Path(self.token_file).is_file()
        )
