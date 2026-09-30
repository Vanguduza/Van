"""Real-Chromium kit for the Harness worker's fixed scripts (unit G9c, network-effect guard).

The production worker runs each fixed script in browser-harness 0.1.13, whose helpers talk
to a daemon holding one CDP connection. This kit gives a script the same helper surface over
a direct CDP connection with the daemon's semantics — ``cdp(method, session_id=None,
**params)`` goes to the attached page session unless a session is named, ``Target.*`` always
goes unsessioned (browser level), and ``drain_events()`` returns and clears a bounded buffer
of every event on the connection (the daemon keeps 500) — and runs the script on the calling
thread, as the worker's subprocess does.

Pages are served by a local HTTPS server (every host resolves to it through
``--host-resolver-rules``), which records each request it receives. That log is the
instrument for "did a write reach the server": it sits outside the browser, so nothing in
the page or in the guard can make it lie.
"""
from __future__ import annotations

import collections
import contextlib
import datetime
import io
import json
import os
import shutil
import ssl
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

CHROMIUM = os.environ.get("VAN_TEST_CHROMIUM", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
READ_METHODS = ("GET", "HEAD", "OPTIONS")


def chromium_available() -> bool:
    return Path(CHROMIUM).is_file()


def _certificate(directory: Path) -> tuple[str, str]:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "van-test")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=2))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("*.example.com"), x509.DNSName("*.example.net"),
                                                    x509.DNSName("docs.example.com")]), critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_path, key_path = directory / "cert.pem", directory / "key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
    return str(cert_path), str(key_path)


class FixtureServer:
    """HTTPS server for every host. ``pages(host, path)`` returns html, (content_type, body)
    or None (a plain landing page). ``log`` holds (method, host, path) per request."""

    def __init__(self, pages: Callable[[str, str], Any], directory: Path, tls: bool = True) -> None:
        self.pages = pages
        self.log: list[tuple[str, str, str]] = []
        server = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args: Any) -> None:
                pass

            def _any(self) -> None:
                length = int(self.headers.get("content-length") or 0)
                if length:
                    self.rfile.read(length)
                host = (self.headers.get("host") or "").split(":")[0]
                path = self.path.split("?")[0]
                server.log.append((self.command, host, path))
                page = server.pages(host, path)
                ctype = "text/html"
                if isinstance(page, tuple):
                    ctype, page = page
                if page is None:
                    page = f"<!doctype html><title>{path}</title><p>landed {path}</p>"
                data = page.encode()
                self.send_response(200)
                self.send_header("content-type", ctype)
                self.send_header("content-length", str(len(data)))
                self.send_header("cache-control", "no-store")
                self.end_headers()
                self.wfile.write(data)

            do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_HEAD = _any

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        if tls:  # unit G12: plain HTTP too (ws:// through the egress proxy)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(*_certificate(directory))
            self.httpd.socket = context.wrap_socket(self.httpd.socket, server_side=True)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def writes(self, hosts: tuple[str, ...] = ("example.com", "example.net")) -> list[tuple[str, str, str]]:
        """Non-GET/HEAD/OPTIONS requests to the fixture hosts (browser background traffic to
        other hosts is not the page's)."""
        return [e for e in self.log if e[0] not in READ_METHODS and e[1].endswith(hosts)]

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


def _merge_disable_features(flags: list[str]) -> list[str]:
    """Chromium honours only the last ``--disable-features`` (review I7 minor 4): the kit's own
    and the worker's are merged into one, as the worker's ``chromium_argv`` does."""
    names: list[str] = []
    out: list[str] = []
    for flag in flags:
        if flag.startswith("--disable-features="):
            names += [n for n in flag.split("=", 1)[1].split(",") if n and n not in names]
        else:
            out.append(flag)
    return out + (["--disable-features=" + ",".join(names)] if names else [])


class Chromium:
    """Headless Chromium launched with the Harness worker's guard flags."""

    def __init__(self, port: int, flags: tuple[str, ...], directory: Path) -> None:
        self.dir = tempfile.mkdtemp(prefix="chromium-", dir=str(directory))
        self.proc = subprocess.Popen(
            [CHROMIUM, "--headless=new", "--remote-debugging-port=0", f"--user-data-dir={self.dir}",
             "--no-first-run", "--no-default-browser-check", "--disable-dev-shm-usage",
             "--disable-background-networking", "--disable-component-update", "--no-sandbox",
             *_merge_disable_features(["--no-proxy-server", "--ignore-certificate-errors", "--disable-features=DnsOverHttps",
                                       f"--host-resolver-rules=MAP * 127.0.0.1:{port}", *flags]), "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        active = Path(self.dir) / "DevToolsActivePort"
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and not (active.is_file() and active.read_text().count("\n") >= 1):
            time.sleep(0.05)
        lines = active.read_text().splitlines()
        self.ws_url = f"ws://127.0.0.1:{lines[0]}{lines[1]}"

    def close(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        shutil.rmtree(self.dir, ignore_errors=True)


_KEYS = {"Enter": (13, "Enter", "\r"), " ": (32, "Space", " "), "Tab": (9, "Tab", ""), "Escape": (27, "Escape", "")}


class HarnessSession:
    """browser-harness helper surface over one CDP connection (daemon semantics)."""

    BUFFER = 500

    def __init__(self, ws_url: str) -> None:
        from websockets.sync.client import connect

        self.ws = connect(ws_url, max_size=None)
        self.counter = 0
        self.pending: dict[int, tuple[threading.Event, dict]] = {}
        self.events: collections.deque = collections.deque(maxlen=self.BUFFER)
        self.lock = threading.Lock()
        threading.Thread(target=self._reader, daemon=True).start()
        page = next(t for t in self.send("Target.getTargets")["targetInfos"] if t["type"] == "page")
        self.session = self.send("Target.attachToTarget", {"targetId": page["targetId"], "flatten": True})["sessionId"]
        for domain in ("Page", "DOM", "Runtime", "Network"):
            self.send(f"{domain}.enable", session_id=self.session)
        #: test hook: method -> callable(params) raising to simulate a CDP failure
        self.fail: dict[str, Callable[[dict], None]] = {}

    def _reader(self) -> None:
        try:
            for raw in self.ws:
                message = json.loads(raw)
                if "id" in message:
                    waiter = self.pending.pop(message["id"], None)
                    if waiter:
                        waiter[1].update(message)
                        waiter[0].set()
                else:
                    self.events.append({"method": message["method"], "params": message.get("params", {}),
                                        "session_id": message.get("sessionId")})
        except Exception:  # noqa: BLE001 - connection closed
            pass

    def send(self, method: str, params: dict | None = None, session_id: str | None = None, timeout: float = 15) -> dict:
        with self.lock:
            self.counter += 1
            ident = self.counter
        waiter = (threading.Event(), {})
        self.pending[ident] = waiter
        message = {"id": ident, "method": method, "params": params or {}}
        if session_id:
            message["sessionId"] = session_id
        self.ws.send(json.dumps(message))
        if not waiter[0].wait(timeout):
            raise TimeoutError(method)
        if "error" in waiter[1]:
            raise RuntimeError(waiter[1]["error"].get("message"))
        return waiter[1].get("result", {})

    # -- helpers, as browser_harness.helpers defines them
    def cdp(self, method: str, session_id: str | None = None, **params: Any) -> dict:
        if method in self.fail:
            self.fail[method](params)
        sid = None if method.startswith("Target.") else (session_id or self.session)
        return self.send(method, params, session_id=sid)

    def _drain_all(self) -> list[dict]:
        out = []
        while self.events:
            out.append(self.events.popleft())
        return out

    #: What the Harness guard needs to see (unit G11). A test's own drain (to start from a quiet
    #: buffer) must not swallow them: in production only the Harness scripts drain the daemon.
    GUARD_EVENTS = ("Fetch.", "Target.", "Page.frameNavigated", "Page.navigatedWithinDocument",
                    "Page.frameRequestedNavigation", "ServiceWorker.", "Network.webSocketCreated")

    def drain_events(self) -> list[dict]:
        """Test-side drain: discards noise, keeps what a Harness guard must still see."""
        out = self._drain_all()
        keep = [e for e in out if str(e.get("method") or "").startswith(self.GUARD_EVENTS)]
        for event in reversed(keep):
            self.events.appendleft(event)
        return [e for e in out if e not in keep]

    def js(self, expression: str) -> Any:
        r = self.cdp("Runtime.evaluate", expression=expression, returnByValue=True, awaitPromise=True)
        return (r.get("result") or {}).get("value")

    def page_info(self) -> dict:
        return json.loads(self.js("JSON.stringify({url:location.href,title:document.title,w:innerWidth,h:innerHeight,sx:scrollX,sy:scrollY})"))

    #: browser-harness's click_at_xy sends press + release only. Playwright's mouse.click
    #: moves the pointer there first; fixtures written against it (a page reacting to the
    #: pointer arriving) set this to keep their instrument.
    move_before_click = False

    def click_at_xy(self, x: float, y: float) -> None:
        if self.move_before_click:
            self.cdp("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)
        for kind in ("mousePressed", "mouseReleased"):
            self.cdp("Input.dispatchMouseEvent", type=kind, x=x, y=y, button="left", clickCount=1)

    def press_key(self, key: str) -> None:
        vk, code, text = _KEYS.get(key, (0, key, key if len(key) == 1 else ""))
        base = {"key": key, "code": code, "windowsVirtualKeyCode": vk, "nativeVirtualKeyCode": vk}
        self.cdp("Input.dispatchKeyEvent", type="keyDown", **base, **({"text": text} if text else {}))
        self.cdp("Input.dispatchKeyEvent", type="keyUp", **base)

    def scroll(self, x: float, y: float, dy: int = -300, dx: int = 0) -> None:
        self.cdp("Input.dispatchMouseEvent", type="mouseWheel", x=x, y=y, deltaX=dx, deltaY=dy)

    def goto_url(self, url: str) -> dict:
        return self.cdp("Page.navigate", url=url)

    def wait_for_load(self, timeout: float = 10.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if self.js("document.readyState") == "complete":
                    return True
            except Exception:  # noqa: BLE001 - mid-navigation
                pass
            time.sleep(0.05)
        return False

    def current_tab(self) -> dict:
        return {"url": self.page_info().get("url")}

    def namespace(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in (
            "cdp", "js", "page_info", "click_at_xy", "press_key", "scroll", "goto_url",
            "wait_for_load", "current_tab")} | {"new_tab": self.goto_url, "drain_events": self._drain_all}

    # -- test-side conveniences
    def goto(self, url: str) -> None:
        self.goto_url(url)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                if self.js("location.href") == url and self.js("document.readyState") == "complete":
                    break
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.05)
        time.sleep(0.15)
        self.drain_events()

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self.ws.close()


def exec_script(session: HarnessSession, script: str, extra: dict[str, str] | None = None) -> Any:
    """Run a fixed Harness script the way browser-harness does (helpers as globals, JSON on
    stdout), on the calling thread."""
    saved = {k: os.environ.get(k) for k in (extra or {})}
    os.environ.update(extra or {})
    out = io.StringIO()

    def _print(*args: Any, **kwargs: Any) -> None:
        # The script's own stdout, captured through its ``print`` rather than by redirecting
        # sys.stdout: other threads (a test printing its result, the worker's guard thread)
        # keep theirs while a script runs.
        if kwargs.get("file") is None:
            out.write(kwargs.get("sep", " ").join(str(a) for a in args) + kwargs.get("end", "\n"))
        else:
            print(*args, **kwargs)

    try:
        exec(compile(script, "<harness-script>", "exec"), {**session.namespace(), "print": _print})  # noqa: S102
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    for line in reversed(out.getvalue().splitlines()):
        if line.startswith("__VAN_JSON__"):
            return json.loads(line[len("__VAN_JSON__"):])
    raise RuntimeError("BROWSER_HARNESS_RESPONSE_MISSING")


class Rig:
    """Chromium + fixture server + helper session for one test."""

    def __init__(self, pages: Callable[[str, str], Any], flags: tuple[str, ...], directory: Path) -> None:
        self.server = FixtureServer(pages, directory)
        self.chromium = Chromium(self.server.port, flags, directory)
        self.session = HarnessSession(self.chromium.ws_url)
        self.lock = threading.Lock()

    def run_harness(self, alias: str, script: str, extra: dict[str, str] | None = None) -> Any:
        with self.lock:
            return exec_script(self.session, script, extra)

    def close(self) -> None:
        self.session.close()
        self.chromium.close()
        self.server.close()
