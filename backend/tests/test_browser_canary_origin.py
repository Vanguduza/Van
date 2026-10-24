"""Unit G14 — the guard canary's in-zone origin (owner answer 2026-09-30 after unit G13,
"In-zone canary origin (Recommended)"):

    "The canary serves its fixture from a dedicated canary hostname on the zone's private
    overlay, listed in the proxy config as the only allowed non-global upstream. It is checked
    by qualify.sh and never reachable by a task scope. The proxy's local-address rule stays
    strict for everything else."

Three parts:

* the gateway: task creation, owner-approved widening and recorded scopes refuse any
  ``*.internal`` host (the canary origin among them);
* the Harness: a call whose scope or target domain names an overlay host is refused
  (``TASK_SCOPE_RESERVED_HOST``) unless it is the canary's own, MAC-checked call;
* live, production code end to end except the network: ``egress_proxy.py`` as its own process
  with **no** ``VAN_EGRESS_TEST_*`` override (the real resolution and address rule), the canary
  fixture served over TLS on a local non-loopback address, Chromium launched by the Harness's
  own ``ChromeSession.ensure()``. Chromium's wrapper adds ``--host-resolver-rules`` mapping the
  canary name to 127.0.0.1: behind the proxy Chromium never resolves it, so the page still
  comes from the overlay address the proxy pins. The instrument is the fixture's request log.
"""
from __future__ import annotations

import importlib.util
import ipaddress
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

import cdp_harness_kit as kit
import test_browser_api as t
from test_browser_api import _settings  # noqa: F401 - autouse: the API settings the routes need
from van_gateway.browser.task_scope import (
    TaskScope,
    TaskScopeError,
    load_scope,
    parse_scope_entry,
    reserved_host,
    scope_for_new_task,
)

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "deploy/van-browser-core/browser/harness_service.py"
PROXY = ROOT / "deploy/van-browser-core/browser/egress_proxy.py"
CANARY_SCRIPT = ROOT / "deploy/van-browser-core/browser/guard_canary.py"
KEY = b"c" * 64
HOST = "canary.van-browser-core.internal"
OPENSSL = "/usr/bin/openssl"


# ------------------------------------------------------------------------- the gateway side
@pytest.mark.parametrize("host,reserved", [
    (HOST, True), ("internal", True), ("x.internal.", True), ("X.INTERNAL", True),
    ("foo.internals.com", False), ("internal.example.com", False), ("example.com", False), ("", False),
])
def test_overlay_names_are_reserved(host, reserved):
    assert reserved_host(host) is reserved


def test_task_scope_refuses_the_canary_origin_and_every_overlay_host():
    for target, declared in ((HOST, None), ("example.com", [f"https://{HOST}/docs/"]),
                             ("van-browser-core.internal", [f"https://{HOST}"]), ("internal", None),
                             ("example.com", [f"https://{HOST.upper()}./docs/"])):
        with pytest.raises(TaskScopeError) as err:
            scope_for_new_task(target, declared)
        assert err.value.code == "TASK_SCOPE_RESERVED_HOST", (target, declared)
    with pytest.raises(TaskScopeError) as err:
        parse_scope_entry(f"https://{HOST}:8443/", "internal")
    assert err.value.code == "TASK_SCOPE_RESERVED_HOST"
    with pytest.raises(TaskScopeError):
        TaskScope(entries=[]).with_origin(HOST, "OWNER_APPROVED:x")
    # A recorded scope naming the overlay (written before this rule) fails closed.
    assert load_scope(json.dumps({"entries": [{"origin": f"https://{HOST}"}]})) is None
    assert load_scope(json.dumps({"entries": [{"origin": "https://example.com"}, {"origin": f"https://{HOST}"}]})) is None
    # Look-alikes are ordinary names.
    assert scope_for_new_task("foo.internals.com", None).to_wire()["entries"][0]["origin"] == "https://foo.internals.com"


async def test_the_create_path_refuses_a_scope_naming_the_canary_origin(tmp_path):
    ac, _api, store = await t._client(tmp_path)
    base = {"profile_alias": "public_research", "strategy": "HARNESS", "autonomy_tier": "L1_HARNESS_DETERMINISTIC",
            "action_class": "A2", "goal": "g"}
    async with ac:
        declared = await ac.post("/v1/browser/tasks", headers=t.HEADERS,
                                 json={**base, "target_domain": "van-browser-core.internal", "scope": [f"https://{HOST}/docs/"]})
        implied = await ac.post("/v1/browser/tasks", headers=t.HEADERS, json={**base, "target_domain": HOST})
        fine = await ac.post("/v1/browser/tasks", headers=t.HEADERS, json={**base, "target_domain": t.DOMAIN})
        rows = await store.fetchall("SELECT target_domain FROM browser_tasks")
    for refused in (declared, implied):
        assert refused.status_code == 422 and "TASK_SCOPE_RESERVED_HOST" in refused.text, refused.text
    assert fine.status_code == 200
    assert [r["target_domain"] for r in rows] == [t.DOMAIN]


async def test_an_owner_approval_never_widens_a_task_onto_the_overlay(tmp_path):
    import test_browser_review_i2_lifecycle as lc

    ac, store, _ex, api = await lc._setup(tmp_path, lc.OUT_OF_SCOPE)
    async with ac:
        tid, decision_id = await lc._escalate(ac, store)
        await store.execute("UPDATE decisions SET status = 'APPROVED' WHERE id = ?", (decision_id,))
        await api._sync_waiting_owner_decision(await api._load_task(tid))
        widened = await api._load_task(tid)
        # The same approval, had it named the canary host: nothing is widened.
        await store.execute("UPDATE browser_escalations SET requested_scope_delta_json = ? WHERE task_id = ?",
                            (json.dumps({"allowed_domain": HOST}), tid))
        await store.execute("UPDATE browser_scope_authorizations SET approved_domains_json = ? WHERE task_id = ?",
                            (json.dumps([t.DOMAIN, HOST]), tid))
        overlay = await api._load_task(tid)
    assert [e.origin for e in widened.scope.entries] == [f"https://{t.DOMAIN}"]
    assert await store.fetchall("SELECT * FROM browser_scope_authorizations WHERE task_id=?", (tid,)) == []
    assert [e.origin for e in overlay.scope.entries] == [f"https://{t.DOMAIN}"]


def test_no_gateway_code_can_mint_the_canary_mac():
    """The canary MAC context exists only in the zone (Harness, proxy, canary); the gateway
    holds the fence key but never computes it."""
    offenders = [str(p.relative_to(ROOT)) for p in (ROOT / "backend/van_gateway").rglob("*.py")
                 if "van-egress-canary" in p.read_text(encoding="utf-8")]
    assert offenders == []


# ------------------------------------------------------------------------- the Harness side
def _harness(monkeypatch, tmp_path, *, origin=f"https://{HOST}", address="10.40.0.9", key=True):
    tmp_path.mkdir(parents=True, exist_ok=True)
    key_file = tmp_path / "fence.key"
    key_file.write_bytes(KEY)
    for name, value in {"VAN_HARNESS_STATE_ROOT": str(tmp_path / "state"),
                        "VAN_BROWSER_CANARY_ORIGIN": origin, "VAN_BROWSER_CANARY_ADDRESS": address}.items():
        monkeypatch.setenv(name, value)
    if key:
        monkeypatch.setenv("VAN_HARNESS_FENCE_KEY_FILE", str(key_file))
    else:
        monkeypatch.delenv("VAN_HARNESS_FENCE_KEY_FILE", raising=False)
    monkeypatch.delenv("VAN_TRUST_ZONE", raising=False)
    spec = importlib.util.spec_from_file_location(f"van_harness_canary_{tmp_path.name}", HARNESS)
    hs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hs)
    return hs


def _canary_body(hs, *, alias="guard_canary", task_id="van-guard-canary", generation=7, origin=f"https://{HOST}",
                 address="10.40.0.9", mutating=False, domain=HOST, entries=None, mac=True):
    holder = f"qualify-canary-{generation}"
    body = {"profile_alias": alias, "target_domain": domain, "task_id": task_id, "lease_generation": generation,
            "lease_holder_id": holder, "mutating": mutating,
            "task_scope": {"entries": entries if entries is not None else [{"origin": origin, "path_prefix": "/docs/"}]}}
    if mac:
        body["canary_mac"] = hs.canary_mac(KEY, alias, generation, holder, task_id, origin, address)
    return body


def test_the_harness_refuses_overlay_scopes_except_the_canarys_own_call(monkeypatch, tmp_path):
    hs = _harness(monkeypatch, tmp_path)
    own = _canary_body(hs)
    assert hs.reserved_scope_violation(own, "guard_canary") is None
    refused = {
        "ordinary task": _canary_body(hs, task_id="task-1"),
        "other alias": dict(_canary_body(hs), profile_alias="public_research"),
        "no canary mac": _canary_body(hs, mac=False),
        "mac for another lease": dict(_canary_body(hs), lease_generation=8),
        "mac for another address": _canary_body(hs, address="10.40.0.10"),
        "mutating": _canary_body(hs, mutating=True),
        "another overlay host": _canary_body(hs, entries=[{"origin": "https://other.van-browser-core.internal"}]),
        "canary plus a public origin": _canary_body(hs, entries=[{"origin": f"https://{HOST}"}, {"origin": "https://example.com"}]),
        "public target domain": _canary_body(hs, domain="example.com"),
        "unparseable overlay origin": _canary_body(hs, entries=[{"origin": f"https://[{HOST}]"}]),
    }
    for name, body in refused.items():
        alias = body["profile_alias"]
        assert hs.reserved_scope_violation(body, alias) == "TASK_SCOPE_RESERVED_HOST", name
    # Ordinary scopes are not affected.
    plain = {"target_domain": "example.com", "task_scope": {"entries": [{"origin": "https://example.com"}]}}
    assert hs.reserved_scope_violation(plain, "public_research") is None
    # The scope checks of /navigate, /scroll and /upload and the guard/proxy policy refuse too.
    for call in (lambda: hs._assert_scope(_canary_body(hs, task_id="task-1"), f"https://{HOST}/docs/x", "NAVIGATE"),
                 lambda: hs._require_scope(dict(_canary_body(hs, task_id="task-1"), profile_alias="guard_canary"))):
        with pytest.raises(hs.WorkerError) as err:
            call()
        assert (err.value.code, err.value.status) == ("TASK_SCOPE_RESERVED_HOST", 409)
    hs._assert_scope(own, f"https://{HOST}/docs/x", "NAVIGATE")


def test_without_a_key_or_a_canary_config_no_call_is_the_canarys(monkeypatch, tmp_path):
    hs = _harness(monkeypatch, tmp_path / "nokey", key=False)
    assert hs.reserved_scope_violation(_canary_body(hs), "guard_canary") == "TASK_SCOPE_RESERVED_HOST"
    for origin, address in ((f"https://{HOST}", "not-an-ip"), (f"http://{HOST}", "10.40.0.9"), ("https://canary.example.com", "10.40.0.9")):
        hs = _harness(monkeypatch, tmp_path / f"cfg{abs(hash((origin, address)))}", origin=origin, address=address)
        assert hs.reserved_scope_violation(_canary_body(hs, origin=origin, address=address), "guard_canary") \
            == "TASK_SCOPE_RESERVED_HOST", (origin, address)


def test_the_worker_handler_refuses_before_the_fence_is_touched(monkeypatch, tmp_path):
    hs = _harness(monkeypatch, tmp_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), hs.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        body = dict(_canary_body(hs, task_id="task-1"), mode="PRODUCTION_ACTUATOR", allow_helper_authoring=False,
                    url=f"https://{HOST}/docs/x", lease_mac=hs.fence_mac(KEY, "guard_canary", 7, "qualify-canary-7"))
        import urllib.error
        import urllib.request

        request = urllib.request.Request(f"http://127.0.0.1:{server.server_address[1]}/navigate",
                                         data=json.dumps(body).encode(), headers={"content-type": "application/json"})
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=20)
        assert err.value.code == 409 and json.loads(err.value.read()) == {"error": "TASK_SCOPE_RESERVED_HOST"}
        assert not list((tmp_path / "state").glob("*guard_canary*"))  # no lease generation recorded
    finally:
        server.shutdown()
        server.server_close()


# ------------------------------------------------------------------------------ live rig
def _overlay_address() -> str | None:
    """A local IPv4 address that is not loopback and not global (the sandbox's stand-in for the
    zone's private overlay address)."""
    try:
        text = Path("/proc/net/fib_trie").read_text()
    except OSError:
        return None
    for match in re.finditer(r"\|-- (\d+\.\d+\.\d+\.\d+)\n\s+/32 host LOCAL", text):
        ip = ipaddress.ip_address(match.group(1))
        if not ip.is_loopback and not ip.is_global and not ip.is_link_local:
            return str(ip)
    return None


ADDRESS = _overlay_address()
live = pytest.mark.skipif(
    not kit.chromium_available() or not Path(OPENSSL).is_file() or ADDRESS is None,
    reason="needs the pinned Chromium, openssl and a local non-loopback address",
)


def _control(path: str, message: dict) -> dict:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(10)
        sock.connect(path)
        sock.sendall(json.dumps(message).encode() + b"\n")
        data = b""
        while not data.endswith(b"\n"):
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
    return json.loads(data)


class Fixture:
    """An HTTP(S) server on ``address``; ``log`` holds (method, path)."""

    def __init__(self, address: str, cert: tuple[str, str] | None) -> None:
        self.log: list[tuple[str, str]] = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                path = self.path.split("?")[0]
                outer.log.append(("GET UPGRADE" if self.headers.get("upgrade") else "GET", path))
                data = f"<!doctype html><title>{path}</title><p id='p'>canary {path}</p>".encode()
                self.send_response(200)
                self.send_header("content-type", "text/html")
                self.send_header("content-length", str(len(data)))
                self.send_header("connection", "close")
                self.end_headers()
                self.wfile.write(data)

            do_POST = do_HEAD = do_GET

        self.httpd = ThreadingHTTPServer((address, 0), H)
        if cert:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(*cert)
            self.httpd.socket = ctx.wrap_socket(self.httpd.socket, server_side=True)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def _canary_cert(directory: Path, host: str) -> tuple[str, str]:
    """The canary certificate the way bootstrap.sh issues it (openssl, self-signed, SAN = the
    canary name); the proxy pins it."""
    directory.mkdir(parents=True, exist_ok=True)
    crt, key = directory / "canary.crt", directory / "canary.key"
    subprocess.run([OPENSSL, "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256", "-nodes",
                    "-keyout", str(key), "-out", str(crt), "-days", "397", "-subj", f"/CN={host}",
                    "-addext", f"subjectAltName=DNS:{host}", "-addext", "extendedKeyUsage=serverAuth",
                    "-addext", "basicConstraints=critical,CA:FALSE", "-addext", "keyUsage=critical,digitalSignature"],
                   check=True, capture_output=True, timeout=30)
    return str(crt), str(key)


class CanaryRig:
    def __init__(self, monkeypatch, tmp_path: Path, *, pin_cert: bool = True) -> None:
        self.tmp = tmp_path
        self.cert = _canary_cert(tmp_path / "canary", HOST)
        self.canary = Fixture(ADDRESS, self.cert)
        self.origin = f"https://{HOST}:{self.canary.port}"
        self.loop = Fixture("127.0.0.1", None)            # a zone loopback service
        self.plain = Fixture(ADDRESS, None)               # another service on the overlay address
        key_file = tmp_path / "fence.key"
        key_file.write_bytes(KEY)
        self.control = str(tmp_path / "egress.sock")
        self.decisions = tmp_path / "decisions.jsonl"
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("VAN_", "HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"))}
        env.update({
            "VAN_EGRESS_CONTROL_SOCKET": self.control, "VAN_EGRESS_STATE_DIR": str(tmp_path / "egress-state"),
            "VAN_EGRESS_FENCE_KEY_FILE": str(key_file), "VAN_EGRESS_DECISION_LOG": str(self.decisions),
            "VAN_EGRESS_PORT_RANGE": "20000-60000",
            "VAN_BROWSER_CANARY_ORIGIN": self.origin, "VAN_BROWSER_CANARY_ADDRESS": ADDRESS,
            # Pinned: the canary's own certificate is the only trust anchor for that upstream.
            "VAN_BROWSER_CANARY_CERT": self.cert[0] if pin_cert else _canary_cert(tmp_path / "other", HOST)[0],
        })
        self.proxy = subprocess.Popen([sys.executable, str(PROXY)], env=env,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        deadline = time.monotonic() + 20
        while not Path(self.control).exists():
            if self.proxy.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError(f"egress proxy did not start: {self.proxy.stderr.read()!r}")
            time.sleep(0.05)
        wrapper = tmp_path / "chrome-wrapper.sh"
        wrapper.write_text(f"#!/bin/sh\nexec {kit.CHROMIUM} --no-sandbox '--host-resolver-rules=MAP {HOST} 127.0.0.1'"
                           f" \"$@\"\n", encoding="utf-8")
        wrapper.chmod(0o755)
        for name, value in {
            "VAN_CHROMIUM_EXECUTABLE": str(wrapper), "VAN_BROWSER_PROFILE_ROOT": str(tmp_path / "profiles"),
            "VAN_BROWSER_RUNTIME_ROOT": str(tmp_path / "run"), "VAN_HARNESS_STATE_ROOT": str(tmp_path / "harness-state"),
            "VAN_HARNESS_FENCE_KEY_FILE": str(key_file), "VAN_BROWSER_EGRESS_CONTROL_SOCKET": self.control,
            "VAN_BROWSER_CANARY_ORIGIN": self.origin, "VAN_BROWSER_CANARY_ADDRESS": ADDRESS,
        }.items():
            monkeypatch.setenv(name, value)
        monkeypatch.delenv("VAN_TRUST_ZONE", raising=False)
        spec = importlib.util.spec_from_file_location("van_harness_canary_live", HARNESS)
        self.hs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.hs)
        self.sessions: list[kit.HarnessSession] = []
        self.generation = int(time.time())

    # -- the canary's own lease, the way guard_canary.py and the Harness handler do it
    def arm(self, generation: int, holder: str) -> dict:
        return _control(self.control, {"op": "canary", "alias": "guard_canary", "lease_generation": generation,
                                       "lease_holder_id": holder, "task_id": "van-guard-canary",
                                       "canary_mac": self.hs.canary_mac(KEY, "guard_canary", generation, holder,
                                                                        "van-guard-canary", self.origin, ADDRESS)})

    def body(self, alias: str, scope: dict, *, task_id: str, generation: int, holder: str, domain: str) -> dict:
        body = {"profile_alias": alias, "target_domain": domain, "lease_generation": generation,
                "lease_holder_id": holder, "task_id": task_id, "mutating": False, "task_scope": scope,
                "effect_mac": self.hs.effect_mac(KEY, alias, generation, holder, task_id, False, self.hs.scope_digest(scope))}
        body["canary_mac"] = self.hs.canary_mac(KEY, alias, generation, holder, task_id, self.origin, ADDRESS)
        return body

    def lease(self, alias: str, scope: dict, *, task_id: str, domain: str, arm: bool):
        """A new lease on ``alias`` whose first action carries ``scope`` (the handler's path)."""
        self.generation += 1
        holder = f"holder-{self.generation}"
        if arm:
            assert self.arm(self.generation, holder) == {"ok": True, "error": None}
        lease = self.hs.GuardLease(alias, self.generation, holder, task_id)
        self.hs.revoke_egress_policy(alias, self.generation, holder, final=False)
        self.hs.apply_lease_policy(lease, self.body(alias, scope, task_id=task_id, generation=self.generation,
                                                    holder=holder, domain=domain), alias)
        return lease

    def launch(self, alias: str) -> kit.HarnessSession:
        chrome = self.hs.POOL.get(alias)
        chrome.ensure()
        lines = (chrome.profile_dir / "DevToolsActivePort").read_text().splitlines()
        session = kit.HarnessSession(f"ws://127.0.0.1:{lines[0]}{lines[1]}")
        self.sessions.append(session)
        return session

    def raw(self, alias: str, request: bytes, host: str, port: int, *, tls: bool = True) -> tuple[str, str | None]:
        """One request through ``alias``'s proxy listener: (status line, refusal code)."""
        listener = _control(self.control, {"op": "listener", "alias": alias})["port"]
        with socket.create_connection(("127.0.0.1", listener), timeout=15) as sock:
            if tls:
                sock.sendall(f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n".encode())
                head = sock.recv(65536)
                if b" 200 " not in head.split(b"\r\n")[0] + b" ":
                    m = re.search(rb"X-Van-Egress-Refused: ([A-Z_]+)", head)
                    return head.split(b"\r\n")[0].decode(), m.group(1).decode() if m else None
                ctx = ssl.create_default_context()
                ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
                sock = ctx.wrap_socket(sock, server_hostname=host)
            sock.sendall(request)
            data = b""
            while b"\r\n\r\n" not in data:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                data += chunk
        m = re.search(rb"X-Van-Egress-Refused: ([A-Z_]+)", data)
        return data.split(b"\r\n")[0].decode(), m.group(1).decode() if m else None

    def codes(self) -> list[str]:
        if not self.decisions.exists():
            return []
        return [json.loads(x)["code"] for x in self.decisions.read_text().splitlines() if x and json.loads(x)["code"]]

    def clear(self):
        for f in (self.canary, self.loop, self.plain):
            f.log.clear()
        self.decisions.write_text("", encoding="utf-8")

    def close(self) -> None:
        for session in self.sessions:
            session.close()
        self.hs.POOL.close()
        with __import__("contextlib").suppress(Exception):
            self.hs.NET_GUARDS.close()
        self.proxy.terminate()
        try:
            self.proxy.wait(5)
        except subprocess.TimeoutExpired:
            self.proxy.kill()
        for f in (self.canary, self.loop, self.plain):
            f.close()


@pytest.fixture
def rig(monkeypatch, tmp_path):
    r = CanaryRig(monkeypatch, tmp_path)
    try:
        yield r
    finally:
        r.close()


def _scope(origin: str, prefix: str | None = "/docs/") -> dict:
    return {"entries": [{"origin": origin, "path_prefix": prefix}]}


@live
def test_the_armed_canary_lease_loads_its_page_from_the_overlay_address_through_the_proxy(rig):
    rig.lease("guard_canary", _scope(rig.origin), task_id="van-guard-canary", domain=HOST, arm=True)
    session = rig.launch("guard_canary")
    session.goto_url(f"{rig.origin}/docs/page")
    time.sleep(2)
    assert ("GET", "/docs/page") in rig.canary.log
    assert session.js("document.getElementById('p') && document.getElementById('p').textContent") == "canary /docs/page"
    assert rig.loop.log == []  # the resolver rule pointed the name at loopback: never used
    argv = Path(f"/proc/{rig.hs.POOL.get('guard_canary').process.pid}/cmdline").read_bytes().decode().split("\0")
    assert any(a.startswith("--proxy-server=http://127.0.0.1:") for a in argv)
    health = _control(rig.control, {"op": "health"})
    assert health["canary"] == {"origin": rig.origin, "address": ADDRESS, "port": rig.canary.port, "certificate_pinned": True}


@live
def test_the_canary_exception_refuses_a_websocket_upgrade_and_ends_with_the_lease(rig):
    lease = rig.lease("guard_canary", _scope(rig.origin), task_id="van-guard-canary", domain=HOST, arm=True)
    host = f"{HOST}:{rig.canary.port}"
    ok = rig.raw("guard_canary", f"GET /docs/probe HTTP/1.1\r\nHost: {host}\r\n\r\n".encode(), HOST, rig.canary.port)
    ws = rig.raw("guard_canary", (f"GET /docs/ws-pay?amount=500 HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\n"
                                  "Connection: Upgrade\r\n\r\n").encode(), HOST, rig.canary.port)
    assert ok[0].startswith("HTTP/1.0 200") or ok[0].startswith("HTTP/1.1 200"), ok
    assert ws == ("HTTP/1.1 403 Forbidden", "EGRESS_WEBSOCKET_REFUSED")
    assert rig.canary.log == [("GET", "/docs/probe")]
    # The lease ends: the grant goes with it, and its policy cannot come back.
    rig.hs.revoke_egress_policy("guard_canary", lease.generation, lease.holder, final=True)
    assert rig.arm(lease.generation, lease.holder) == {"ok": False, "error": "POLICY_LEASE_ENDED"}
    # A new canary lease that was never armed gets the address rule: refused, nothing sent.
    rig.clear()
    rig.lease("guard_canary", _scope(rig.origin), task_id="van-guard-canary", domain=HOST, arm=False)
    assert rig.raw("guard_canary", f"GET /docs/probe HTTP/1.1\r\nHost: {host}\r\n\r\n".encode(), HOST,
                   rig.canary.port) == ("HTTP/1.1 403 Forbidden", "EGRESS_UPSTREAM_ADDRESS_REFUSED")
    assert rig.canary.log == [] and "EGRESS_UPSTREAM_ADDRESS_REFUSED" in rig.codes()


@live
def test_a_normal_task_cannot_reach_the_canary_origin(rig):
    """Scope creation refuses it (gateway), the Harness refuses it, the proxy refuses a policy
    naming it, and the proxy refuses the canary host itself to any lease qualify.sh did not arm."""
    with pytest.raises(TaskScopeError):
        scope_for_new_task("van-browser-core.internal", [f"{rig.origin}/docs/"])
    # The Harness: a normal task's action carrying the canary origin is refused before any push.
    rig.generation += 1
    lease = rig.hs.GuardLease("public_research", rig.generation, "h", "task-1")
    with pytest.raises(rig.hs.WorkerError) as err:
        rig.hs.apply_lease_policy(lease, rig.body("public_research", _scope(rig.origin), task_id="task-1",
                                                  generation=rig.generation, holder="h", domain=HOST), "public_research")
    assert err.value.code == "TASK_SCOPE_RESERVED_HOST"
    # The proxy: the same policy sent straight to it (a caller holding the key) is refused.
    scope = _scope(rig.origin)
    for alias, task_id in (("public_research", "task-1"), ("guard_canary", "task-1")):
        mac = rig.hs.effect_mac(KEY, alias, 1 << 40, "h", task_id, False, rig.hs.scope_digest(scope))
        reply = _control(rig.control, {"op": "policy", "alias": alias, "lease_generation": 1 << 40, "lease_holder_id": "h",
                                       "task_id": task_id, "mutating": False, "task_scope": scope, "effect_mac": mac})
        assert reply == {"ok": False, "error": "POLICY_SCOPE_RESERVED_HOST"}, (alias, task_id)
    # Arming refuses anything but the canary's alias and task id.
    for alias, task_id in (("public_research", "van-guard-canary"), ("guard_canary", "task-1")):
        reply = _control(rig.control, {"op": "canary", "alias": alias, "lease_generation": 5, "lease_holder_id": "h",
                                       "task_id": task_id, "canary_mac": rig.hs.canary_mac(
                                           KEY, alias, 5, "h", task_id, rig.origin, ADDRESS)})
        assert reply == {"ok": False, "error": "CANARY_TASK_INVALID"}
    forged = _control(rig.control, {"op": "canary", "alias": "guard_canary", "lease_generation": 5, "lease_holder_id": "h",
                                    "task_id": "van-guard-canary", "canary_mac": "0" * 64})
    assert forged == {"ok": False, "error": "CANARY_MAC_INVALID"}
    # Even while the canary is armed for its own lease, another alias's browser gets nothing
    # from the canary host (it is not in its scope, and its policy cannot name it).
    rig.lease("guard_canary", _scope(rig.origin), task_id="van-guard-canary", domain=HOST, arm=True)
    rig.lease("public_research", _scope(f"https://{t.DOMAIN}"), task_id="task-1", domain=t.DOMAIN, arm=False)
    session = rig.launch("public_research")
    rig.clear()
    session.goto_url(f"{rig.origin}/docs/page")
    time.sleep(2)
    assert rig.canary.log == [] and "EGRESS_CONNECT_OUT_OF_SCOPE" in rig.codes()


@live
def test_loopback_and_every_other_non_global_upstream_stay_refused_while_the_canary_is_armed(rig):
    rig.lease("guard_canary", _scope(rig.origin), task_id="van-guard-canary", domain=HOST, arm=True)
    rig.clear()
    cases = {
        # (alias scope origin, request host, port, tls)
        "loopback literal": (f"http://127.0.0.1:{rig.loop.port}", "127.0.0.1", rig.loop.port, False),
        "localhost name": (f"http://localhost:{rig.loop.port}", "localhost", rig.loop.port, False),
        "the overlay address itself, another port": (f"http://{ADDRESS}:{rig.plain.port}", ADDRESS, rig.plain.port, False),
        "the overlay address itself, the canary port": (f"https://{ADDRESS}:{rig.canary.port}", ADDRESS, rig.canary.port, True),
        "private literal": ("http://10.255.255.1:80", "10.255.255.1", 80, False),
    }
    for name, (origin, host, port, tls) in cases.items():
        rig.lease("public_research", _scope(origin, None), task_id="task-1", domain=host, arm=False)
        authority = host if port in (80, 443) else f"{host}:{port}"
        target = "/docs/x" if tls else f"http://{authority}/docs/x"
        got = rig.raw("public_research", f"GET {target} HTTP/1.1\r\nHost: {authority}\r\n\r\n".encode(), host, port, tls=tls)
        assert got == ("HTTP/1.1 403 Forbidden", "EGRESS_UPSTREAM_ADDRESS_REFUSED"), (name, got)
    # The canary lease itself cannot use the exception for anything but the canary host:port.
    same_alias = rig.raw("guard_canary", f"GET http://127.0.0.1:{rig.loop.port}/ HTTP/1.1\r\nHost: 127.0.0.1:{rig.loop.port}\r\n\r\n".encode(),
                         "127.0.0.1", rig.loop.port, tls=False)
    assert same_alias == ("HTTP/1.1 403 Forbidden", "EGRESS_ORIGIN_OUT_OF_SCOPE")
    assert rig.loop.log == [] and rig.plain.log == [] and rig.canary.log == []


@live
def test_the_canary_upstream_is_verified_against_its_pinned_certificate_only(monkeypatch, tmp_path):
    r = CanaryRig(monkeypatch, tmp_path, pin_cert=False)
    try:
        r.lease("guard_canary", _scope(r.origin), task_id="van-guard-canary", domain=HOST, arm=True)
        got = r.raw("guard_canary", f"GET /docs/probe HTTP/1.1\r\nHost: {HOST}:{r.canary.port}\r\n\r\n".encode(),
                    HOST, r.canary.port)
        assert got == ("HTTP/1.1 403 Forbidden", "EGRESS_UPSTREAM_UNAVAILABLE")
        assert r.canary.log == []
    finally:
        r.close()


@live
def test_guard_canary_passes_end_to_end_through_the_proxy_and_the_harness_handler(rig, monkeypatch):
    """guard_canary.py, unchanged, against the real Harness handler (the worker's HTTP surface,
    its fence, lease guard and proxy policy) in front of the real proxy. Scripts run in the
    worker's Chromium over CDP (the kit) instead of the browser-harness binary; the binary path
    is the live qualify run recorded with this unit."""
    alias = "guard_canary"
    session = rig.launch(alias)
    lock = threading.Lock()

    def run_harness(_alias, script, extra=None):
        with lock:
            return kit.exec_script(session, script, extra)

    monkeypatch.setattr(rig.hs, "run_harness", run_harness)
    server = ThreadingHTTPServer(("127.0.0.1", 0), rig.hs.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    # guard_canary.py serves its own fixture on the canary address/port: free the rig's.
    port = rig.canary.port
    rig.canary.close()
    env_file = rig.tmp / "runtime.env"
    env_file.write_text("\n".join([
        f"VAN_CHROMIUM_EXECUTABLE={kit.CHROMIUM}", f"VAN_HARNESS_FENCE_KEY_FILE={rig.tmp / 'fence.key'}",
        f"VAN_BROWSER_EGRESS_CONTROL_SOCKET={rig.control}", f"VAN_BROWSER_CANARY_ORIGIN={rig.origin}",
        f"VAN_BROWSER_CANARY_ADDRESS={ADDRESS}", f"VAN_BROWSER_CANARY_CERT={rig.cert[0]}",
        f"VAN_BROWSER_CANARY_KEY={rig.cert[1]}"]) + "\n", encoding="utf-8")
    try:
        proc = subprocess.run([sys.executable, str(CANARY_SCRIPT), "--worker", f"http://127.0.0.1:{server.server_address[1]}",
                               "--runtime-env", str(env_file), "--wait", "4"],
                              capture_output=True, text=True, timeout=240)
        report = json.loads(proc.stdout)
        assert proc.returncode == 0 and report["ok"] is True, json.dumps(report, indent=1)
        assert set(report["cases"]) == {"immediate", "delayed", "proxy", "task_refused"}
        assert report["cases"]["proxy"]["websocket"] == [403, "EGRESS_WEBSOCKET_REFUSED"]
        assert report["origin"] == f"https://{HOST}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        rig.canary = Fixture(ADDRESS, rig.cert)  # for close()
