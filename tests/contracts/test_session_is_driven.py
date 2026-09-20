"""A constructed subsystem is not a running one.

`tools/audit/kotlin_reachability.py` asks whether anything *references* a file, and by
that measure the §20 session was reachable for five checkpoints: `VanApplication`
constructs `VanHermesSessionManager`, so the file is referenced. It called
`setInteractionActive` and `setStandbyConditions` and nothing else. `start()` had no
caller, so no socket opened, no outbox was restored, no resume ran, and `submit` — the
only way a command enters the durable outbox — was never reached.

Two checkpoints made that outbox durable and then atomic without noticing that nothing
puts anything in it. Every test passed, because every one of them called the outbox
directly.

So this asks the question the file-level check cannot: **for each entry point, does
anything in the app call it?** And it holds the matrix to the answer, rather than to a
sentence somebody wrote next to it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "android/app/src/main/java/com/dial/van"
MANAGER = APP / "session/VanHermesSessionManager.kt"
MATRIX = ROOT / "docs/project-state/REMOTE_BROWSER_IMPLEMENTATION_MATRIX.json"

#: The field the app holds the session in. Named once here so that renaming it in the
#: app breaks this test loudly rather than making every entry point look uncalled.
HANDLE = "vanSession"

#: Rows whose named consumer is a device-side §20 entry point. If the session is not
#: driven, none of these may claim to be wired.
DEVICE_SIDE_ROWS = ("RB-035", "RB-061", "RB-062", "RB-064", "RB-068", "RB-069", "RB-071")


def _public_entry_points() -> set[str]:
    """Every public `fun` on the manager. Its API, as the app can see it."""
    source = MANAGER.read_text(encoding="utf-8")
    found = set(re.findall(r"^    (?:suspend )?fun (\w+)\s*\(", source, re.M))
    assert found, "no entry points parsed — this test would pass by finding nothing"
    return found


def _app_sources() -> list[Path]:
    return [p for p in APP.rglob("*.kt") if p != MANAGER]


def _called_entry_points() -> set[str]:
    """Which of them anything in the app actually calls."""
    blob = "\n".join(p.read_text(encoding="utf-8") for p in _app_sources())
    return set(re.findall(rf"\b{HANDLE}\.(\w+)\s*\(", blob))


def _rows() -> dict:
    return {r["id"]: r for r in json.loads(MATRIX.read_text(encoding="utf-8"))["rows"]}


def test_the_session_handle_still_exists():
    """Guards the guard. A renamed field would make every call site invisible."""
    app = (APP / "VanApplication.kt").read_text(encoding="utf-8")
    assert re.search(rf"\b{HANDLE}\s*=\s*VanHermesSessionManager\(", app), (
        f"nothing assigns {HANDLE}; this test can no longer see who calls the session"
    )


def test_the_matrix_agrees_with_whether_the_session_is_driven():
    """The rule, stated once and applied in both directions.

    Not "assert the session is unwired" — that would have to be deleted the moment it is
    wired, which is how a correction becomes a fossil. The invariant is the agreement: if
    nothing starts the session, the rows that depend on it say `BUILT_UNWIRED`; once
    something does, they are free to claim more and this test stops objecting.
    """
    started = "start" in _called_entry_points()
    rows = _rows()
    for rid in DEVICE_SIDE_ROWS:
        row = rows[rid]
        if not started:
            assert row["status"] == "BUILT_UNWIRED", (
                f"{rid} claims {row['status']} while VanHermesSessionManager.start() has "
                f"no caller, so nothing it describes can run"
            )
            assert row["wired"] is False, f"{rid} claims wired with no session running"


def test_every_uncalled_entry_point_is_accounted_for():
    """An entry point nobody calls is either wired or written down as unwired.

    The list is explicit so that adding a public method to the session, and no caller
    for it, fails here — rather than joining the seven that already had none.
    """
    uncalled = _public_entry_points() - _called_entry_points()
    # What C16 found, exactly. Each is unreachable because `start()` is: the socket is
    # never opened, so nothing resumes, flushes, expires or asks the owner anything.
    known = {
        "start", "close", "submit", "reconfirm",
        "queuedForOwner", "awaitingReconfirmation",
        "expiredSinceLastRead", "undeliveredSinceLastRead",
    }
    surprising = uncalled - known
    assert not surprising, (
        f"new session entry points with no caller in the app: {sorted(surprising)}. "
        f"Either call them or record the row as BUILT_UNWIRED."
    )
    # And the other direction: something in `known` that has since gained a caller must
    # be removed from the list, or this test quietly stops checking it.
    stale = known - _public_entry_points()
    assert not stale, f"these no longer exist on the session: {sorted(stale)}"


def test_a_stored_command_the_owner_must_confirm_can_be_released():
    """§20.15 — storing a command that needs the owner's yes is half of the rule.

    `DurableOutbox` classifies "read that back to me" and "cancel it" as
    `REQUIRE_RECONFIRM_ON_RECONNECT`, `flushOutbox` correctly holds one rather than
    sending it, and `reconfirm(messageId)` is the only thing that releases it. Nothing
    calls `reconfirm`, so such a command is stored, held, and stuck.

    Written as the rule rather than as the gap, so the day something calls it the test
    keeps holding the row to the truth instead of needing to be deleted. Until then
    RB-069 must name it, because a row that claims otherwise is claiming the owner can
    answer a question nothing asks.
    """
    releasable = "reconfirm" in _called_entry_points()
    row = _rows()["RB-069"]
    if not releasable:
        gates = " ".join(row.get("external_gates", []))
        assert "reconfirm" in gates, (
            "a command needing the owner's confirmation is stored and cannot be released, "
            "and RB-069 does not say so"
        )
