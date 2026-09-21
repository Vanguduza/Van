"""A durable write that blocks is a durable write that must not run on the UI thread.

`EncryptedCommandQueue.persist` and `remove` use `SharedPreferences.Editor.commit()`
rather than `apply()`, so the owner's command is on disk before anything tells them it is
saved. That is the right trade for the outbox. It also means every mutating call is an
AES-GCM encryption plus a synchronous file write on the calling thread.

When that change was made, two callers that had always been harmless became main-thread
disk writers: `ShareIntakeActivity.onCreate` and
`VanNotificationListenerService.onNotificationPosted` are both Android main-thread entry
points, and a burst of notifications would do one encrypted write per notification on the
thread that draws. Raised by external review, which was right to ask where the
synchronous write actually runs rather than accept that the durability was improved.

So this asks it of every call site, statically: does the file that writes to the queue
dispatch that write off the caller's thread? It cannot see a real thread, and says so —
what it can see is whether the write is inside an IO-dispatched block, which is the thing
that was wrong.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "android/app/src/main/java/com/dial/van"
QUEUE = APP / "queue/EncryptedCommandQueue.kt"

#: The calls that block until the bytes are down.
WRITES = ("enqueue", "upsert", "remove", "clear", "markAttempt", "purgeExpired")

#: Files whose own dispatcher is not visible here, and why that is acceptable.
#:  - the queue itself, which is the thing being called
#:  - the replayer, which already launches on `Dispatchers.IO` and is checked below
EXEMPT = {"EncryptedCommandQueue.kt"}


def _call_sites() -> dict[Path, list[str]]:
    found: dict[Path, list[str]] = {}
    # `commandQueue` specifically. A first version matched any `*queue.` receiver and
    # reported `VoiceAudioArbiter`'s audio buffer, which is a ring of PCM frames and has
    # nothing to do with a disk — a check that cries wolf is one somebody switches off.
    pattern = re.compile(rf"\bcommandQueue\.({'|'.join(WRITES)})\s*\(")
    for path in APP.rglob("*.kt"):
        if path.name in EXEMPT:
            continue
        hits = pattern.findall(path.read_text(encoding="utf-8"))
        if hits:
            found[path] = hits
    return found


def test_the_queue_still_commits_synchronously():
    """Guards the guard: without `commit()` there is nothing here to protect against."""
    source = QUEUE.read_text(encoding="utf-8")
    assert ".commit()" in source, "the queue no longer writes synchronously"
    assert ".apply()" not in source, (
        "a write went back to apply(); the outbox's 'saved' claim is no longer true when made"
    )


def test_every_file_that_writes_to_the_queue_dispatches_it_off_the_caller():
    sites = _call_sites()
    assert sites, "no call sites found — this test would pass by finding nothing"
    offenders = []
    for path, hits in sites.items():
        source = path.read_text(encoding="utf-8")
        if "Dispatchers.IO" not in source:
            offenders.append(f"{path.relative_to(ROOT)} calls {sorted(set(hits))}")
    assert not offenders, (
        "these write to the encrypted queue with no IO dispatch in the file, so the "
        "synchronous encrypted write runs on whatever thread called them:\n  "
        + "\n  ".join(offenders)
    )


def test_the_two_android_entry_points_that_were_wrong_are_named():
    """The specific regression, pinned.

    A file-level check would pass if these dispatched *something else* to IO while still
    writing to the queue inline, so the two that actually broke are checked by shape: the
    queue call must come after an IO launch in the same file.
    """
    for relative in (
        "share/ShareIntakeActivity.kt",
        "notification/VanNotificationListenerService.kt",
    ):
        source = (APP / relative).read_text(encoding="utf-8")
        launch = source.find("appScope.launch(Dispatchers.IO)")
        write = source.find("commandQueue.enqueue(")
        assert launch != -1, f"{relative} no longer dispatches its write"
        assert write > launch, (
            f"{relative} writes to the encrypted queue before its IO launch, so the "
            f"write is back on the main thread"
        )


def test_discarding_the_queue_is_one_write_rather_than_one_per_command():
    """`clear()` looped `remove`, and every `remove` commits.

    So the owner's "discard everything" tap was one encrypted disk write per queued
    command, in a row — the deeper the queue the longer they wait, which is backwards —
    and N chances to be killed half way through, leaving a queue that is neither what it
    was nor empty.

    Checked by shape rather than executed: `EncryptedCommandQueue` needs a Keystore and a
    disk, so nothing in this repository can run it. What is visible is whether the body of
    `clear` calls the committing `remove` at all.
    """
    source = QUEUE.read_text(encoding="utf-8")
    start = source.index("    fun clear() {")
    body = source[start : source.index("\n    }", start)]
    assert "remove(id)" not in body, (
        "clear() calls remove() per command, so discarding a deep queue is N synchronous "
        "encrypted writes on the caller's thread"
    )
    assert body.count(".commit()") == 1, (
        "clear() should be exactly one committed editor"
    )
