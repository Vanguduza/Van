"""One live session per account alias, enforced by the operating system.

P0-TRADE-005: nothing prevented two `serve` processes for one alias. Each would hold its
own in-process idempotency set, each would reconcile against the same venue, and both
would place orders believing they were the only one. The idempotency key fix stops a
restart duplicating an order; it does not stop two processes running at once, because two
processes deciding the same bar independently is a different failure.

An advisory `flock` is the right tool and its limits are worth stating rather than
implying: it is per-host, so it does not stop a second VM running the same alias, and it
is advisory, so it binds only processes that ask. Both are acceptable here because the
thing being prevented is an operator starting `serve` twice, not an adversary. What it is
not is a substitute for the venue-side check, which is why the reconciliation gate stays.

The lock holds the pid, so a refusal can say who has it rather than only that something
does.
"""

from __future__ import annotations

import errno
import fcntl
import os
from pathlib import Path


class SessionAlreadyRunning(RuntimeError):
    """Another process holds the session lock for this account alias."""

    def __init__(self, alias: str, holder_pid: str, lock_path: Path) -> None:
        self.alias = alias
        self.holder_pid = holder_pid
        super().__init__(
            f"a session for {alias!r} is already running (pid {holder_pid}); "
            f"two sessions on one account both place orders. Lock: {lock_path}"
        )


class SessionLock:
    """An advisory per-alias lock held for the life of the session process."""

    def __init__(self, alias: str, *, directory: str | os.PathLike[str] | None = None) -> None:
        self.alias = alias
        base = Path(directory) if directory else Path(
            os.environ.get("VAN_SESSION_LOCK_DIR", "/tmp/van-sessions")
        )
        base.mkdir(parents=True, exist_ok=True)
        # The alias is validated upstream as [a-z0-9_]; the replace is belt and braces so a
        # future caller cannot produce a path outside the directory.
        self.path = base / f"{alias.replace('/', '_')}.lock"
        self._handle = None

    def acquire(self) -> "SessionLock":
        handle = self.path.open("a+")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno not in (errno.EACCES, errno.EAGAIN):
                handle.close()
                raise
            handle.seek(0)
            holder = handle.read().strip() or "unknown"
            handle.close()
            raise SessionAlreadyRunning(self.alias, holder, self.path) from exc
        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()))
        handle.flush()
        self._handle = handle
        return self

    def release(self) -> None:
        if self._handle is None:
            return
        try:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._handle.close()
            self._handle = None

    def __enter__(self) -> "SessionLock":
        return self.acquire()

    def __exit__(self, *exc_info) -> None:
        self.release()


__all__ = ["SessionAlreadyRunning", "SessionLock"]
