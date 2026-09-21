#!/usr/bin/env python3
"""Private VAN Browser Harness HTTP worker.

The worker exposes only the fixed operations required by the gateway Browser Harness
adapter and delegates browser mechanics to browser-harness 0.1.13. It never accepts
Python, JavaScript, raw CDP, shell, helper source, cookies, or literal credentials over
HTTP. Authority remains in VAN Gateway.
"""
from __future__ import annotations

import atexit
import json
import os
import re
import signal
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

HARNESS_VERSION = "0.1.13"
SERVICE_VERSION = "van-browser-harness-worker/1"
MAX_BODY_BYTES = 131072
PROFILE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
SECRET_RE = re.compile(r"^secretref://browser/([A-Za-z0-9._-]{1,128})$")
FILE_RE = re.compile(r"^fileref://downloads/([A-Za-z0-9._-]{1,180})$")

BIND = os.getenv("VAN_HARNESS_BIND", "127.0.0.1")
PORT = int(os.getenv("VAN_HARNESS_PORT", "9141"))
HARNESS_BIN = os.getenv(
    "VAN_BROWSER_HARNESS_BIN",
    "/opt/van-browser-runtime/harness-venv/bin/browser-harness",
)
CHROMIUM = os.getenv("VAN_CHROMIUM_EXECUTABLE", "")
PROFILE_ROOT = Path(
    os.getenv("VAN_BROWSER_PROFILE_ROOT", "/var/lib/van-trading/browser/profiles")
)
DOWNLOAD_ROOT = Path(
    os.getenv("VAN_BROWSER_DOWNLOAD_ROOT", "/var/lib/van-trading/browser/downloads")
)
SECRET_ROOT = Path(
    os.getenv("VAN_BROWSER_SECRET_ROOT", "/var/lib/van-trading/browser/secrets")
)
RUNTIME_ROOT = Path(os.getenv("VAN_BROWSER_RUNTIME_ROOT", "/run/van-browser"))
REQUEST_TIMEOUT_SECONDS = float(
    os.getenv("VAN_BROWSER_WORKER_TIMEOUT_SECONDS", "45")
)

if BIND not in {"127.0.0.1", "::1", "localhost"}:
    raise SystemExit("browser harness worker refuses a non-loopback bind")


class WorkerError(RuntimeError):
    def __init__(self, code: str, status: int = 400) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


def safe_alias(value: Any) -> str:
    alias = str(value or "").strip()
    if not PROFILE_RE.fullmatch(alias):
        raise WorkerError("PROFILE_ALIAS_INVALID", 422)
    return alias


def safe_domain(value: Any) -> str:
    domain = str(value or "").strip().lower().rstrip(".")
    if not domain or len(domain) > 253:
        raise WorkerError("TARGET_DOMAIN_REQUIRED", 422)
    if any(not re.fullmatch(r"[a-z0-9-]{1,63}", part) for part in domain.split(".")):
        raise WorkerError("TARGET_DOMAIN_INVALID", 422)
    return domain


def assert_url_in_domain(url: str, domain: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise WorkerError("URL_SCHEME_FORBIDDEN", 422)
    host = (parsed.hostname or "").lower().rstrip(".")
    if host != domain and not host.endswith("." + domain):
        raise WorkerError("URL_OUTSIDE_TASK_DOMAIN", 403)
    return url


def safe_child(root: Path, name: str) -> Path:
    root = root.resolve()
    candidate = (root / name).resolve()
    if candidate.parent != root:
        raise WorkerError("REFERENCE_PATH_INVALID", 422)
    return candidate


def resolve_secret(value_ref: Any) -> str:
    match = SECRET_RE.fullmatch(str(value_ref or ""))
    if not match:
        raise WorkerError("SECRET_REFERENCE_REQUIRED", 422)
    path = safe_child(SECRET_ROOT, match.group(1))
    if not path.is_file():
        raise WorkerError("SECRET_REFERENCE_UNAVAILABLE", 409)
    if path.stat().st_size > 16384:
        raise WorkerError("SECRET_REFERENCE_TOO_LARGE", 409)
    return path.read_text(encoding="utf-8").rstrip("\r\n")


def resolve_upload(file_ref: Any) -> Path:
    match = FILE_RE.fullmatch(str(file_ref or ""))
    if not match:
        raise WorkerError("UPLOAD_FILE_REFERENCE_REQUIRED", 422)
    path = safe_child(DOWNLOAD_ROOT, match.group(1))
    if not path.is_file():
        raise WorkerError("UPLOAD_FILE_REFERENCE_UNAVAILABLE", 409)
    return path


class ChromeSession:
    def __init__(self, alias: str) -> None:
        self.alias = alias
        self.profile_dir = safe_child(PROFILE_ROOT, alias)
        self.runtime_dir = safe_child(RUNTIME_ROOT, alias)
        self.process: subprocess.Popen[str] | None = None
        self.cdp_url: str | None = None
        self.lock = threading.RLock()

    def ensure(self) -> str:
        with self.lock:
            if self.process is not None and self.process.poll() is None and self.cdp_url:
                self._publish_cdp()
                return self.cdp_url
            if not CHROMIUM or not Path(CHROMIUM).is_file():
                raise WorkerError("CHROMIUM_EXECUTABLE_UNAVAILABLE", 503)
            self.profile_dir.mkdir(parents=True, exist_ok=True)
            self.runtime_dir.mkdir(parents=True, exist_ok=True)
            active = self.profile_dir / "DevToolsActivePort"
            active.unlink(missing_ok=True)
            self.process = subprocess.Popen(
                [
                    CHROMIUM,
                    "--headless=new",
                    "--remote-debugging-address=127.0.0.1",
                    "--remote-debugging-port=0",
                    f"--user-data-dir={self.profile_dir}",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-dev-shm-usage",
                    "--disable-background-networking",
                    "--disable-component-update",
                    "about:blank",
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise WorkerError("CHROMIUM_START_FAILED", 503)
                if active.is_file():
                    lines = active.read_text(encoding="utf-8").splitlines()
                    if lines and lines[0].isdigit():
                        self.cdp_url = f"http://127.0.0.1:{int(lines[0])}"
                        self._publish_cdp()
                        return self.cdp_url
                time.sleep(0.1)
            self.stop()
            raise WorkerError("CHROMIUM_START_TIMEOUT", 503)

    def _publish_cdp(self) -> None:
        if not self.cdp_url or self.process is None:
            return
        target = self.runtime_dir / "cdp-endpoint.json"
        tmp = self.runtime_dir / ".cdp-endpoint.json.tmp"
        tmp.write_text(
            json.dumps(
                {
                    "profile_alias": self.alias,
                    "cdp_url": self.cdp_url,
                    "pid": self.process.pid,
                },
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        os.chmod(tmp, 0o600)
        os.replace(tmp, target)

    def stop(self) -> None:
        with self.lock:
            proc, self.process = self.process, None
            self.cdp_url = None
            (self.runtime_dir / "cdp-endpoint.json").unlink(missing_ok=True)
            if proc is None or proc.poll() is not None:
                return
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)


class BrowserPool:
    def __init__(self) -> None:
        self.sessions: dict[str, ChromeSession] = {}
        self.lock = threading.RLock()

    def get(self, alias: str) -> ChromeSession:
        with self.lock:
            return self.sessions.setdefault(alias, ChromeSession(alias))

    def close(self) -> None:
        with self.lock:
            sessions = list(self.sessions.values())
        for session in sessions:
            session.stop()


POOL = BrowserPool()
atexit.register(POOL.close)


def harness_env(alias: str, cdp_url: str, extra: dict[str, str] | None = None) -> dict[str, str]:
    runtime = safe_child(RUNTIME_ROOT, alias)
    paths = {
        "BH_HOME": runtime / "harness-home",
        "BH_RUNTIME_DIR": runtime / "harness-runtime",
        "BH_TMP_DIR": runtime / "harness-tmp",
        "BH_AGENT_WORKSPACE": runtime / "fixed-agent-workspace",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        **{key: str(value) for key, value in paths.items()},
        "BU_NAME": f"van_{alias}",
        "BU_CDP_URL": cdp_url,
        "BH_DOMAIN_SKILLS": "0",
        "BH_OPEN_LIVE_URL": "0",
        "BH_TAB_MARKER": "0",
    }
    if extra:
        env.update(extra)
    return env


def run_harness(alias: str, script: str, extra: dict[str, str] | None = None) -> Any:
    if not Path(HARNESS_BIN).is_file():
        raise WorkerError("BROWSER_HARNESS_EXECUTABLE_UNAVAILABLE", 503)
    session = POOL.get(alias)
    cdp_url = session.ensure()
    with session.lock:
        try:
            completed = subprocess.run(
                [HARNESS_BIN],
                input=script,
                text=True,
                capture_output=True,
                env=harness_env(alias, cdp_url, extra),
                timeout=REQUEST_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise WorkerError("BROWSER_HARNESS_TIMEOUT", 504) from exc
    if completed.returncode != 0:
        raise WorkerError("BROWSER_HARNESS_REQUEST_FAILED", 502)
    marker = "__VAN_JSON__"
    for line in reversed(completed.stdout.splitlines()):
        if line.startswith(marker):
            try:
                return json.loads(line[len(marker):])
            except json.JSONDecodeError as exc:
                raise WorkerError("BROWSER_HARNESS_RESPONSE_INVALID", 502) from exc
    raise WorkerError("BROWSER_HARNESS_RESPONSE_MISSING", 502)


PAGE_INFO_SCRIPT = r"""
import json
info = page_info()
visible = js("document.body ? document.body.innerText.slice(0, 32768) : ''") or ""
identity = js("(()=>{const e=document.querySelector('[data-van-account-identity],meta[name=\\\"van-account-identity\\\"]');return e ? (e.content || e.getAttribute('data-van-account-identity') || e.textContent || '') : '';})()") or ""
info["extraction"] = {"visible_text": str(visible)[:32768]}
if identity:
    info["account_identity"] = str(identity)[:256]
info["harness_version"] = "0.1.13"
print("__VAN_JSON__" + json.dumps(info))
"""


def page_info_result(alias: str, domain: str) -> dict[str, Any]:
    result = run_harness(alias, PAGE_INFO_SCRIPT)
    if not isinstance(result, dict):
        raise WorkerError("BROWSER_PAGE_INFO_INVALID", 502)
    current = str(result.get("url") or "")
    if current and current != "about:blank":
        assert_url_in_domain(current, domain)
    return result


def navigate(body: dict[str, Any], alias: str, domain: str) -> dict[str, Any]:
    url = assert_url_in_domain(str(body.get("url") or ""), domain)
    script = r"""
import json, os
url = os.environ["VAN_BH_URL"]
cur = current_tab()
if not cur or str(cur.get("url") or "").startswith("about:blank"):
    new_tab(url)
else:
    goto_url(url)
wait_for_load()
print("__VAN_JSON__" + json.dumps({"navigated": True}))
"""
    run_harness(alias, script, {"VAN_BH_URL": url})
    return page_info_result(alias, domain)


def click(body: dict[str, Any], alias: str, domain: str) -> dict[str, Any]:
    locator = str(body.get("locator") or "")
    if not locator or len(locator) > 2048:
        raise WorkerError("LOCATOR_REQUIRED", 422)
    script = r"""
import json, os
sel = os.environ["VAN_BH_LOCATOR"]
expr = "(()=>{const e=document.querySelector(" + json.dumps(sel) + ");if(!e)return null;const r=e.getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2,w:r.width,h:r.height};})()"
box = js(expr)
if not box or box.get("w", 0) <= 0 or box.get("h", 0) <= 0:
    raise RuntimeError("locator not found or not visible")
click_at_xy(float(box["x"]), float(box["y"]))
print("__VAN_JSON__" + json.dumps({"clicked": True}))
"""
    run_harness(alias, script, {"VAN_BH_LOCATOR": locator})
    return page_info_result(alias, domain)


def fill(body: dict[str, Any], alias: str, domain: str) -> dict[str, Any]:
    locator = str(body.get("locator") or "")
    if not locator or len(locator) > 2048:
        raise WorkerError("LOCATOR_REQUIRED", 422)
    secret = resolve_secret(body.get("value_ref"))
    script = r"""
import json, os
fill_input(os.environ["VAN_BH_LOCATOR"], os.environ["VAN_BH_SECRET"], clear_first=True, timeout=5)
print("__VAN_JSON__" + json.dumps({"filled": True}))
"""
    run_harness(alias, script, {"VAN_BH_LOCATOR": locator, "VAN_BH_SECRET": secret})
    return page_info_result(alias, domain)


def press(body: dict[str, Any], alias: str, domain: str) -> dict[str, Any]:
    key = str(body.get("key") or "")
    if not key or len(key) > 64:
        raise WorkerError("KEY_REQUIRED", 422)
    run_harness(
        alias,
        'import json,os\npress_key(os.environ["VAN_BH_KEY"])\nprint("__VAN_JSON__"+json.dumps({"pressed":True}))\n',
        {"VAN_BH_KEY": key},
    )
    return page_info_result(alias, domain)


def scroll_page(body: dict[str, Any], alias: str, domain: str) -> dict[str, Any]:
    request = body.get("request") if isinstance(body.get("request"), dict) else {}
    dx = int(request.get("x", request.get("delta_x", 0)) or 0)
    dy = int(request.get("y", request.get("delta_y", 0)) or 0)
    if abs(dx) > 20000 or abs(dy) > 20000:
        raise WorkerError("SCROLL_DELTA_OUT_OF_RANGE", 422)
    run_harness(
        alias,
        'import json,os\ninfo=page_info()\nx=max(0,int(info.get("w",0))//2)\ny=max(0,int(info.get("h",0))//2)\nscroll(x,y,dy=int(os.environ["VAN_BH_DY"]),dx=int(os.environ["VAN_BH_DX"]))\nprint("__VAN_JSON__"+json.dumps({"scrolled":True}))\n',
        {"VAN_BH_DX": str(dx), "VAN_BH_DY": str(dy)},
    )
    return page_info_result(alias, domain)


def screenshot(alias: str, domain: str) -> dict[str, Any]:
    script = r"""
import hashlib, json
p = capture_screenshot(max_dim=1800)
with open(p, "rb") as f:
    data = f.read()
print("__VAN_JSON__" + json.dumps({"screenshot_digest": hashlib.sha256(data).hexdigest(), "size_bytes": len(data), "contains_secrets": False}))
"""
    result = run_harness(alias, script)
    info = page_info_result(alias, domain)
    return {**result, "url": info.get("url"), "title": info.get("title")}


def wait(body: dict[str, Any], alias: str, domain: str) -> dict[str, Any]:
    condition = body.get("condition") if isinstance(body.get("condition"), dict) else {}
    kind = str(condition.get("kind") or "load")
    if kind == "load":
        run_harness(alias, 'import json\nwait_for_load(timeout=10)\nprint("__VAN_JSON__"+json.dumps({"waited":"load"}))\n')
    elif kind == "selector":
        selector = str(condition.get("selector") or "")
        if not selector or len(selector) > 2048:
            raise WorkerError("WAIT_SELECTOR_REQUIRED", 422)
        run_harness(
            alias,
            'import json,os\nok=wait_for_element(os.environ["VAN_BH_LOCATOR"],timeout=10)\nprint("__VAN_JSON__"+json.dumps({"waited":"selector","matched":bool(ok)}))\n',
            {"VAN_BH_LOCATOR": selector},
        )
    elif kind == "milliseconds":
        ms = int(condition.get("value", 0) or 0)
        if ms < 0 or ms > 10000:
            raise WorkerError("WAIT_DURATION_OUT_OF_RANGE", 422)
        time.sleep(ms / 1000)
    else:
        raise WorkerError("WAIT_KIND_UNSUPPORTED", 422)
    return page_info_result(alias, domain)


def upload(body: dict[str, Any], alias: str, domain: str) -> dict[str, Any]:
    locator = str(body.get("locator") or "")
    if not locator or len(locator) > 2048:
        raise WorkerError("LOCATOR_REQUIRED", 422)
    path = resolve_upload(body.get("file_ref"))
    script = r"""
import json, os
selector = os.environ["VAN_BH_LOCATOR"]
doc = cdp("DOM.getDocument", depth=1)
node = cdp("DOM.querySelector", nodeId=doc["root"]["nodeId"], selector=selector)
if not node.get("nodeId"):
    raise RuntimeError("upload locator not found")
cdp("DOM.setFileInputFiles", nodeId=node["nodeId"], files=[os.environ["VAN_BH_UPLOAD"]])
print("__VAN_JSON__" + json.dumps({"uploaded": True}))
"""
    run_harness(alias, script, {"VAN_BH_LOCATOR": locator, "VAN_BH_UPLOAD": str(path)})
    return page_info_result(alias, domain)


def tabs(alias: str, domain: str) -> dict[str, Any]:
    script = r"""
import json
items = [{"targetId": str(t.get("targetId") or ""), "title": str(t.get("title") or "")[:512], "url": str(t.get("url") or "")[:4096]} for t in list_tabs()]
print("__VAN_JSON__" + json.dumps({"tabs": items}))
"""
    result = run_harness(alias, script)
    safe = []
    for tab in result.get("tabs", []):
        url = str(tab.get("url") or "")
        if url.startswith(("http://", "https://")):
            try:
                assert_url_in_domain(url, domain)
            except WorkerError:
                continue
        safe.append(tab)
    return {"tabs": safe, "harness_version": HARNESS_VERSION}


OPERATIONS = {
    "/navigate": navigate,
    "/click": click,
    "/fill": fill,
    "/press": press,
    "/scroll": scroll_page,
    "/wait": wait,
    "/upload": upload,
}


class Handler(BaseHTTPRequestHandler):
    server_version = SERVICE_VERSION

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[van-browser-harness] {self.address_string()} {fmt % args}", flush=True)

    def send_json(self, status: int, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(encoded)))
        self.send_header("cache-control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_json(200, {
                "ok": True,
                "service": SERVICE_VERSION,
                "runtime_version": HARNESS_VERSION,
                "helper_authoring": False,
                "raw_cdp_http": False,
                "bind": BIND,
            })
            return
        self.send_json(404, {"error": "NOT_FOUND"})

    def do_POST(self) -> None:
        try:
            raw_length = self.headers.get("content-length")
            if raw_length is None:
                raise WorkerError("CONTENT_LENGTH_REQUIRED", 411)
            length = int(raw_length)
            if length < 0 or length > MAX_BODY_BYTES:
                raise WorkerError("REQUEST_TOO_LARGE", 413)
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                raise WorkerError("REQUEST_BODY_NOT_OBJECT", 422)
            if body.get("mode") != "PRODUCTION_ACTUATOR":
                raise WorkerError("HARNESS_MODE_REQUIRED", 403)
            if body.get("allow_helper_authoring") is not False:
                raise WorkerError("HELPER_AUTHORING_FORBIDDEN", 403)
            alias = safe_alias(body.get("profile_alias"))
            domain = safe_domain(body.get("target_domain"))
            if self.path == "/page_info":
                result = page_info_result(alias, domain)
            elif self.path == "/screenshot":
                result = screenshot(alias, domain)
            elif self.path == "/tabs":
                result = tabs(alias, domain)
            else:
                operation = OPERATIONS.get(self.path)
                if operation is None:
                    raise WorkerError("OPERATION_NOT_ALLOWED", 404)
                result = operation(body, alias, domain)
            self.send_json(200, result)
        except WorkerError as exc:
            self.send_json(exc.status, {"error": exc.code})
        except (ValueError, json.JSONDecodeError):
            self.send_json(422, {"error": "REQUEST_INVALID"})
        except Exception:
            self.send_json(502, {"error": "BROWSER_WORKER_FAILURE"})


def main() -> None:
    for path in (PROFILE_ROOT, DOWNLOAD_ROOT, SECRET_ROOT, RUNTIME_ROOT):
        path.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((BIND, PORT), Handler)

    def stop(_signum: int, _frame: Any) -> None:
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()
        POOL.close()


if __name__ == "__main__":
    main()
