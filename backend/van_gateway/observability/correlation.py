"""One identifier that follows a piece of work from command to verification.

P2-OBS-001: identifiers existed per subsystem — command_id, mission_id, execution_id,
hermes_run_id, snapshot_id, evidence_id — and nothing joined them. A hermes_run_id could
not be traced to the verification that later judged it, and mission changes never reached
the event bus at all. An operator asking "what happened to the thing I asked for" had to
read SQLite and do the join by hand.

The correlation id is deliberately derived from the command id rather than being a new
random value. A new random value means something has to carry it from the very first hop,
and the very first hop is a signed command whose id is already unique, already covered by
the signature, and already present in every downstream record that matters. Deriving it
means a subsystem that forgot to propagate can still be joined after the fact, which is
the failure mode worth designing for: propagation is the thing that gets forgotten.
"""

from __future__ import annotations

import hashlib
import re

PREFIX = "corr_"

#: A correlation id is 12 hex characters after the prefix. Short enough to read aloud from
#: a log line, long enough that two commands do not collide in a system this size.
_VALID = re.compile(rf"^{PREFIX}[0-9a-f]{{12}}$")


def for_command(command_id: str) -> str:
    """The correlation id for a command, and therefore for everything it causes."""
    digest = hashlib.sha256(f"van-correlation-v1|{command_id}".encode("utf-8")).hexdigest()
    return f"{PREFIX}{digest[:12]}"


def is_correlation_id(value: str | None) -> bool:
    return bool(value) and bool(_VALID.match(str(value)))


__all__ = ["PREFIX", "for_command", "is_correlation_id"]
