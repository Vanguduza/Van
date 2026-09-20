"""Two clocks decide whether a stored command may still run, and they must not disagree.

The phone's outbox expires a queued command after `DurableOutbox.DEFAULT_TTL_MS`. The
Gateway refuses any owner command whose `issued_at_unix` is older than
`owner_intent_max_age_seconds` — a rule written for exactly this case, whose failure
message says "refusing stale offline replay".

Which is stricter decides what the owner sees. If the phone's window is the shorter one,
a command that waited too long is dropped on the device with an owner-readable reason,
and `DurableOutbox.ownerReadableState` says "Not done". If the Gateway's is shorter, the
phone flushes a command it believes is live, and the answer comes back `expired` from a
system the owner cannot see, after they were told it was queued.

Nothing tied the two together. They agree today at four hours against twenty-four, and
they agree by coincidence: the two numbers were chosen in different languages, in
different checkpoints, for different reasons.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTBOX = ROOT / "android/app/src/main/java/com/dial/van/session/DurableOutbox.kt"
QUEUE = ROOT / "android/app/src/main/java/com/dial/van/queue/CommandQueueModels.kt"
CONFIG = ROOT / "backend/van_gateway/config.py"


def _kotlin_millis(path: Path, name: str) -> int:
    """`const val NAME = 4 * 60 * 60 * 1000L` -> 14400000.

    Evaluated rather than matched, because the value is written as an arithmetic
    expression on purpose — `4 * 60 * 60 * 1000` says "four hours" and `14400000` does
    not — and a test that only matched a literal would stop seeing it.
    """
    source = path.read_text(encoding="utf-8")
    match = re.search(rf"\b{name}\b\s*(?::\s*Long\s*)?=\s*([0-9*\sL]+)", source)
    assert match, f"{name} not found in {path.name}"
    return int(eval(match.group(1).replace("L", "").strip()))  # noqa: S307 - digits only


def _gateway_seconds() -> int:
    source = CONFIG.read_text(encoding="utf-8")
    match = re.search(r"owner_intent_max_age_seconds:\s*int\s*=\s*([0-9*\s]+)", source)
    assert match, "owner_intent_max_age_seconds not found"
    return int(eval(match.group(1).strip()))  # noqa: S307 - digits only


def test_the_phone_gives_up_before_the_gateway_would_refuse():
    """The direction that keeps the reason visible to the owner."""
    phone_ms = _kotlin_millis(OUTBOX, "DEFAULT_TTL_MS")
    gateway_ms = _gateway_seconds() * 1000
    assert phone_ms > 0 and gateway_ms > 0
    assert phone_ms <= gateway_ms, (
        f"the outbox holds a command for {phone_ms / 3_600_000:g}h and the Gateway refuses "
        f"owner intent older than {gateway_ms / 3_600_000:g}h, so a flush in between is "
        f"answered 'expired' by something the owner cannot see"
    )


def test_the_queues_own_default_does_not_exceed_it_either():
    """§20.14's record rides on the canonical queue, which has its own default.

    `OutboxPersistence.toCommand` writes the entry's own expiry rather than the queue's —
    a mutation asserts that — but the queue's default is what a record written by any
    other path gets, and `QueueReplayer` posts those to the same command endpoint.
    """
    queue_ms = _kotlin_millis(QUEUE, "COMMAND_QUEUE_DEFAULT_TTL_MS")
    assert queue_ms <= _gateway_seconds() * 1000, (
        "a queued command can outlive the Gateway's owner-intent window"
    )


def test_the_gateway_still_has_the_rule_this_depends_on():
    """Guards the guard: the comparison is meaningless if the refusal is gone."""
    orchestrator = (ROOT / "backend/van_gateway/orchestrator.py").read_text(encoding="utf-8")
    assert "command_age > self.owner_intent_max_age_seconds" in orchestrator
    assert "stale offline replay" in orchestrator
