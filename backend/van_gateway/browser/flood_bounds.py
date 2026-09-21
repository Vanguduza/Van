"""Rev 1.5 §38 items 12, 17 and 18 — the three floods, and the bounds that answer them.

A flood is not an attack that steals anything. It is an attack that makes VAN unusable
while every individual request is perfectly legitimate, which is why none of these three
had a bound: each single tab, download or input packet is exactly what the system is for.

The three are bounded in different places because they arrive from different components,
and that is the part worth stating. A page can open tabs on its own; the Stream Host
reports each one to the Gateway. A page can start downloads; Hermes reports each one. The
phone sends input packets; the Stream Host's router translates each one. So there is no
single door to hold — the bound goes where the thing is *recorded*, which is the one place
that sees all of them.

**What a bound must not do, and why these are shaped the way they are.** An input bound
that dropped the owner's taps would make VAN feel broken in the exact moment they are
trying to stop whatever is happening. So the input bound is a rate, measured over a window,
and it refuses by name rather than silently; the owner's own gestures do not approach it
(a finger produces one MOVE per frame, §8.7) and a page driving synthetic input does.
A tab bound that closed tabs would lose the owner's work; it refuses the *new* one.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

#: §38 item 17. More tabs than this in one session is a page opening them, not a person.
#:
#: Sixty-four is deliberately generous: an owner researching something across a morning
#: can genuinely have dozens open, and a bound that fired on ordinary use would be removed
#: by the first person it inconvenienced. What it stops is the unbounded case.
MAX_OPEN_TABS_PER_SESSION = 64

#: §38 item 18. Downloads in flight at once for one session.
#:
#: Lower than the tab bound because a download is a file on a disk somewhere, and because
#: a page that starts sixteen at once is not serving a person.
MAX_CONCURRENT_DOWNLOADS_PER_SESSION = 16

#: §38 item 12. Input packets per second, per session, as measured at the router.
#:
#: §8.7 coalesces motion to one MOVE per frame, so a 120 Hz phone with a finger down
#: produces about 120 packets a second at its very busiest, plus edges. The bound is set
#: well above that on purpose: it exists to stop a synthetic flood, and an owner dragging
#: on a high-refresh display must never reach it.
MAX_INPUT_PACKETS_PER_SECOND = 400

#: The window the rate is measured over. A second, because a shorter window turns an
#: ordinary burst — the first frames of a fling — into a refusal.
INPUT_WINDOW_MS = 1_000

REJECT_TAB_FLOOD = "browser_tab_limit_reached"
REJECT_DOWNLOAD_FLOOD = "browser_download_limit_reached"
REJECT_INPUT_FLOOD = "input_rate_limit_exceeded"

#: Not a flood, and it lives here because it was found by one.
#:
#: `browser_downloads` has a foreign key to `browser_interactive_sessions`, and SQLite
#: raises `IntegrityError` for a foreign-key violation and for a duplicate primary key
#: alike. `create` caught both and called them a duplicate report, so a download for a
#: session that does not exist told the host its report had already been recorded — and
#: sent whoever read the log looking for a record that was never created.
REJECT_DOWNLOAD_SESSION_UNKNOWN = "download_session_unknown"


@dataclass
class InputRateLimiter:
    """§38 item 12 — a sliding window per session.

    A sliding window rather than a token bucket, because the question being asked is "has
    this session sent more than N packets in the last second", and a bucket answers a
    subtly different one: it permits a long-run rate above the bound as long as the burst
    shape is right, which is exactly what a patient flood would do.

    Per session, not global: one session under attack must not throttle another, and the
    owner's own session is the one that must keep working.
    """

    limit: int = MAX_INPUT_PACKETS_PER_SECOND
    window_ms: int = INPUT_WINDOW_MS
    _seen: dict[str, deque[int]] = field(default_factory=dict)

    def admit(self, session_id: str, now_ms: int) -> bool:
        """True if this packet may be translated. False means refuse it, by name."""
        window = self._seen.setdefault(session_id, deque())
        cutoff = now_ms - self.window_ms
        while window and window[0] <= cutoff:
            window.popleft()
        if len(window) >= self.limit:
            # Not appended: a refused packet must not push the window forward, or a
            # sustained flood would keep the session refused long after it stopped.
            return False
        window.append(now_ms)
        return True

    def depth(self, session_id: str) -> int:
        """How full the window is. For the refusal message and for a test to read."""
        return len(self._seen.get(session_id, ()))

    def forget(self, session_id: str) -> None:
        """A closed session's window is not the next session's."""
        self._seen.pop(session_id, None)
