#!/usr/bin/env python3
"""PID 1 for the Muse gVisor sandbox.

Runs as sandbox-root so Hermes can control Chromium lifecycle through a narrow authenticated
surface while Chromium itself stays uid 10001 and retains its own browser sandbox.
There is deliberately no shell/exec endpoint.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import signal
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

CONTROL_BIND = os.environ.get("VAN_MUSE_CONTROL_BIND", "172.31.77.2")
CONTROL_PORT = int(os.environ.get("VAN_MUSE_CONTROL_PORT", "9230"))
BROWSER_BIND = os.environ.get("VAN_MUSE_BROWSER_BIND", "172.31.77.2")
TOKEN_FILE = Path(os.environ.get("VAN_MUSE_CONTROL_TOKEN_FILE", "/run/secrets/control-token"))
PROFILE = Path("/home/muse/profile")
DOWNLOADS = Path("/home/muse/downloads")
CHROME_UID = 10001
CHROME_GID = 100
MAX_BODY = 16 * 1024

_lock = threading.RLock()
_proc: subprocess.Popen[bytes] | None = None
_started_at = 0.0


def _token() -> bytes:
    data = TOKEN_FILE.read_bytes().strip()
    if len(data) < 32 or len(data) > 256:
        raise RuntimeError("invalid control token")
    return data


def _auth(value: str | None) -> bool:
    if not value or not value.startswith("Bearer "):
        return False
    supplied = value[7:].encode()
    try:
        expected = _token()
    except Exception:
        return False
    return hmac.compare_digest(supplied, expected)


def _chrome_command() -> list[str]:
    return [
        "/usr/bin/setpriv",
        f"--reuid={CHROME_UID}",
        f"--regid={CHROME_GID}",
        "--clear-groups",
        "--no-new-privs",
        "/usr/bin/chromium",
        "--headless=new",
        "--user-data-dir=/home/muse/profile",
        f"--remote-debugging-address={BROWSER_BIND}",
        "--remote-debugging-port=9222",
        "--proxy-server=socks5://172.31.77.1:17892",
        "--proxy-bypass-list=<-loopback>",
        "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 172.31.77.1",
        "--disable-quic",
        "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-domain-reliability",
        "--disable-sync",
        "--disk-cache-size=536870912",
        "--media-cache-size=268435456",
        "--metrics-recording-only",
        "--no-default-browser-check",
        "--no-first-run",
        "about:blank",
    ]


def start_browser() -> dict:
    global _proc, _started_at
    with _lock:
        if _proc is not None and _proc.poll() is None:
            return status()
        PROFILE.mkdir(parents=True, exist_ok=True)
        DOWNLOADS.mkdir(parents=True, exist_ok=True)
        for path in (PROFILE, DOWNLOADS):
            st = path.stat()
            if st.st_uid != CHROME_UID or st.st_gid != CHROME_GID:
                raise RuntimeError(f"persistent volume ownership mismatch: {path}")
            if st.st_mode & 0o077:
                raise RuntimeError(f"persistent volume permissions too broad: {path}")
        child_env = dict(os.environ)
        child_env.update(
            HOME="/home/muse",
            XDG_CONFIG_HOME="/home/muse/profile/config",
            XDG_CACHE_HOME="/tmp/chromium-cache",
        )
        _proc = subprocess.Popen(
            _chrome_command(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=child_env,
        )
        _started_at = time.monotonic()
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if _proc is None or _proc.poll() is not None:
            raise RuntimeError("chromium exited during start")
        try:
            with urlopen(f"http://{BROWSER_BIND}:9222/json/version", timeout=0.5) as response:
                if response.status == 200:
                    return status()
        except Exception:
            pass
        time.sleep(0.1)
    stop_browser()
    raise RuntimeError("chromium CDP endpoint did not become ready")


def stop_browser() -> dict:
    global _proc
    with _lock:
        proc, _proc = _proc, None
    if proc is not None and proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=3)
    return status()


def restart_browser() -> dict:
    stop_browser()
    return start_browser()


def status() -> dict:
    with _lock:
        proc = _proc
        alive = bool(proc is not None and proc.poll() is None)
        pid = proc.pid if alive else None
        uptime = round(time.monotonic() - _started_at, 3) if alive else 0
    return {
        "ok": alive,
        "service": "van-muse-sandbox-supervisor",
        "browser_pid": pid,
        "browser_uid": CHROME_UID,
        "sandbox_supervisor_uid": os.geteuid(),
        "uptime_seconds": uptime,
        "profile": "/home/muse/profile",
        "downloads": "/home/muse/downloads",
        "cdp_url": f"http://{BROWSER_BIND}:9222" if alive else None,
        "control_bind": CONTROL_BIND,
        "shell_endpoint": False,
        "arbitrary_exec": False,
    }


def profile_manifest() -> dict:
    total = 0
    files = 0
    newest = 0.0
    for root in (PROFILE, DOWNLOADS):
        if not root.exists():
            continue
        for p in root.rglob("*"):
            try:
                st = p.stat()
            except OSError:
                continue
            if p.is_file():
                files += 1
                total += st.st_size
                newest = max(newest, st.st_mtime)
    return {
        "files": files,
        "bytes": total,
        "newest_mtime": newest,
        "manifest_digest": hashlib.sha256(f"{files}:{total}:{newest}".encode()).hexdigest(),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "van-muse-supervisor/1"

    def _write(self, code: int, payload: dict) -> None:
        raw = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.send_header("cache-control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _authorized(self) -> bool:
        if _auth(self.headers.get("authorization")):
            return True
        self._write(401, {"ok": False, "error": "unauthorized"})
        return False

    def do_GET(self) -> None:  # noqa: N802
        if not self._authorized():
            return
        path = urlparse(self.path).path
        if path == "/health":
            self._write(200 if status()["ok"] else 503, status())
        elif path == "/profile":
            self._write(200, {"ok": True, **profile_manifest()})
        else:
            self._write(404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if not self._authorized():
            return
        length = int(self.headers.get("content-length", "0") or "0")
        if length > MAX_BODY:
            self._write(413, {"ok": False, "error": "body_too_large"})
            return
        if length:
            self.rfile.read(length)
        path = urlparse(self.path).path
        try:
            if path == "/browser/start":
                result = start_browser()
            elif path == "/browser/stop":
                result = stop_browser()
            elif path == "/browser/restart":
                result = restart_browser()
            else:
                self._write(404, {"ok": False, "error": "not_found"})
                return
            self._write(200, result)
        except Exception as exc:
            self._write(503, {"ok": False, "error": type(exc).__name__})

    def log_message(self, *_args) -> None:
        return


def shutdown(*_args) -> None:
    stop_browser()
    raise SystemExit(0)


if __name__ == "__main__":
    if os.geteuid() != 0:
        raise SystemExit("sandbox supervisor must be root inside gVisor")
    _token()
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    start_browser()
    ThreadingHTTPServer((CONTROL_BIND, CONTROL_PORT), Handler).serve_forever()
