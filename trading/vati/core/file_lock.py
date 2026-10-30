"""Cross-process lock for replace-based state files; sidecar inode is retained."""
from contextlib import contextmanager
import os
from pathlib import Path
import stat
import threading
import weakref


class StateFileLockError(ValueError):
    pass


_process_id = os.getpid()
_thread_state = threading.local()
_mutex_guard = threading.Lock()
_mutexes = weakref.WeakValueDictionary()


def _reset_after_fork():
    global _process_id, _thread_state, _mutex_guard, _mutexes
    _process_id = os.getpid()
    _thread_state = threading.local()
    _mutex_guard = threading.Lock()
    _mutexes = weakref.WeakValueDictionary()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_reset_after_fork)


@contextmanager
def exclusive_state_lock(path):
    """Reentrant within one thread; exclusive across threads and processes."""
    if _process_id != os.getpid():
        _reset_after_fork()
    path = Path(path).resolve()
    key = str(path)
    with _mutex_guard:
        mutex = _mutexes.get(key)
        if mutex is None:
            mutex = threading.RLock()
            _mutexes[key] = mutex
    with mutex:
        held = getattr(_thread_state, "held", None)
        if held is None:
            held = _thread_state.held = set()
        if key in held:
            yield
            return
        with _kernel_state_lock(path):
            held.add(key)
            try:
                yield
            finally:
                held.remove(key)


@contextmanager
def _kernel_state_lock(path):
    """A persistent sidecar inode serializes replace-based writers across processes."""
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(lock_path, flags, 0o600)
    locked = False
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or (os.name != "nt" and (info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077)):
            raise StateFileLockError("state mutation lock must be an owner-only regular file")
        if os.name == "nt":
            import msvcrt
            if info.st_size == 0:
                os.write(fd, b"0")
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX)
        locked = True
        yield
    finally:
        if locked:
            if os.name == "nt":
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)

