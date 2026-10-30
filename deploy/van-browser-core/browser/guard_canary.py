#!/usr/bin/env python3
"""Network-effect guard canary for the INSTALLED van-browser-core (review I7 minor 5, unit G11;
served from the in-zone canary origin through the egress proxy since unit G14).

The guard suite runs in CI against Chromium 1194; bootstrap.sh installs Playwright 1.63.0's
Chromium (build 1243). CDP Fetch interception, related-target auto-attach and the launch flags
the guard depends on are Chromium behaviour, so they are qualified on the Chromium the host
actually runs: this canary drives the running Harness worker (127.0.0.1:9141, its real
browser-harness child and its Chromium) against a fixture server and reads that server's
request log — the only instrument a page cannot lie to.

Unit G14 (owner answer 2026-09-30 after unit G13, "In-zone canary origin (Recommended)"): the
Harness-owned Chromium reaches nothing but through the egress proxy, and the proxy refuses
every non-global upstream, so a fixture on 127.0.0.1 can never load. The fixture is served
over TLS from the canary origin ``VAN_BROWSER_CANARY_ORIGIN`` (a ``*.internal`` name) at the
zone's private overlay address ``VAN_BROWSER_CANARY_ADDRESS``, with the canary certificate the
proxy pins. It is the proxy's only allowed non-global upstream, and only for the canary's own
lease, which this script arms over the proxy's control socket (``op: canary``, MAC
``van-egress-canary/1``) with the dedicated task id ``van-guard-canary``. A task scope can never
name it: the gateway, the Harness and the proxy each refuse ``*.internal`` scope entries.

    python3 guard_canary.py [--worker http://127.0.0.1:9141] [--runtime-env /etc/van-browser-core/runtime.env]

Cases (profile ``guard_canary``, a read-only task scoped to /docs/ on the canary origin):
  immediate     a click whose handler POSTs at once           -> 409 NETWORK_WRITE_BLOCKED:POST
  delayed       a click whose handler POSTs 2.5 s later       -> the click answers 200, nothing
                reaches the server within the wait, the lease then refuses NETWORK_WRITE_BLOCKED:POST
  release       /release ends each lease's guard (page frozen)
  proxy         through the canary lease's own proxy listener: a GET reaches the fixture, a
                WebSocket upgrade to /docs/ws-pay is refused by the proxy (EGRESS_WEBSOCKET_REFUSED)
                and never reaches it
  task_refused  the canary origin in an ordinary task's scope is refused by the Harness
                (TASK_SCOPE_RESERVED_HOST) and by the proxy (POLICY_SCOPE_RESERVED_HOST)
Prints one JSON object; exits 0 only when every case holds. Anything it cannot establish is RED.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import socket
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAY = "fetch('/api/pay',{method:'POST',body:'canary'})"
PAGES = {
    "/docs/immediate": f'<button id="b" onclick="{PAY}">Next</button>',
    "/docs/delayed": f'<button id="b" onclick="setTimeout(()=>{PAY},2500)">Next</button>',
    "/docs/proxy": '<p id="p">proxy</p>',
}
#: An alias the canary's negative probe may give a policy (never a Harness profile).
PROBE_ALIAS = "qualify_canary_task"


def _fixture(address: str, port: int, cert: str, key: str) -> tuple[ThreadingHTTPServer, list[tuple[str, str]]]:
    log: list[tuple[str, str]] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # noqa: D401 - quiet
            pass

        def _any(self):
            length = int(self.headers.get("content-length") or 0)
            if length:
                self.rfile.read(length)
            path = self.path.split("?")[0]
            upgrade = " UPGRADE" if self.headers.get("upgrade") else ""
            log.append((self.command + upgrade, path))
            body = PAGES.get(path, "<p>ok</p>")
            data = f"<!doctype html><html><head><title>{path}</title></head><body>{body}</body></html>".encode()
            self.send_response(200)
            self.send_header("content-type", "text/html")
            self.send_header("content-length", str(len(data)))
            self.send_header("connection", "close")
            self.end_headers()
            self.wfile.write(data)

        do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = _any

    server = ThreadingHTTPServer((address, port), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, log


def _env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                out[key.strip()] = value.strip()
    except OSError:
        pass
    return out


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _control(path: str, message: dict) -> dict:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(10)
        sock.connect(path)
        sock.sendall(json.dumps(message, separators=(",", ":")).encode() + b"\n")
        data = b""
        while not data.endswith(b"\n") and len(data) < 65536:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
    return json.loads(data)


def _through_proxy(port: int, host: str, host_port: int, request: bytes) -> tuple[int | None, str | None]:
    """One request through the proxy listener ``port``: CONNECT, TLS to the proxy's
    interception, then ``request``. (status, X-Van-Egress-Refused code or None). The TLS
    peer is the proxy's own loopback listener, named by its control socket; the probe checks
    the proxy's decision, not the interception certificate (the browser pins that)."""
    with socket.create_connection(("127.0.0.1", port), timeout=15) as raw:
        raw.sendall(f"CONNECT {host}:{host_port} HTTP/1.1\r\nHost: {host}:{host_port}\r\n\r\n".encode())
        head = b""
        while b"\r\n\r\n" not in head and len(head) < 65536:
            chunk = raw.recv(4096)
            if not chunk:
                break
            head += chunk
        first = head.split(b"\r\n", 1)[0].decode("latin-1")
        if " 200 " not in first + " ":
            m = re.search(rb"X-Van-Egress-Refused: ([A-Z_]+)", head)
            return (int(first.split(" ")[1]) if len(first.split(" ")) > 1 else None), (m.group(1).decode() if m else None)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with ctx.wrap_socket(raw, server_hostname=host) as tls:
            tls.sendall(request)
            data = b""
            while b"\r\n\r\n" not in data and len(data) < 65536:
                chunk = tls.recv(4096)
                if not chunk:
                    break
                data += chunk
    line = data.split(b"\r\n", 1)[0].decode("latin-1").split(" ")
    m = re.search(rb"X-Van-Egress-Refused: ([A-Z_]+)", data)
    return (int(line[1]) if len(line) > 1 and line[1].isdigit() else None), (m.group(1).decode() if m else None)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", default="http://127.0.0.1:9141")
    parser.add_argument("--runtime-env", default="/etc/van-browser-core/runtime.env")
    parser.add_argument("--wait", type=float, default=8.0)
    args = parser.parse_args()
    report: dict = {"canary": "network_effect_guard", "cases": {}, "ok": False}
    env = _env_file(Path(args.runtime_env))
    chromium = env.get("VAN_CHROMIUM_EXECUTABLE", "")
    try:
        report["chromium_version"] = subprocess.run([chromium, "--version"], capture_output=True, text=True,
                                                    timeout=20).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        report["chromium_version"] = None

    def red(error: str) -> int:
        report["error"] = error
        print(json.dumps(report))
        return 1

    # The Harness's MAC helpers and the proxy's canary rule (the worker and the proxy
    # themselves are the running services).
    service = _load("van_harness_service_canary", HERE / "harness_service.py")
    egress = _load("van_egress_proxy_canary", HERE / "egress_proxy.py")
    try:
        canary = egress.parse_canary(env.get("VAN_BROWSER_CANARY_ORIGIN", ""), env.get("VAN_BROWSER_CANARY_ADDRESS", ""))
    except ValueError as exc:
        return red(f"canary origin invalid: {exc}")
    if canary is None:
        return red("canary origin unconfigured: VAN_BROWSER_CANARY_ORIGIN / VAN_BROWSER_CANARY_ADDRESS")
    report["origin"] = canary.origin
    control = env.get("VAN_BROWSER_EGRESS_CONTROL_SOCKET", "")
    cert, cert_key = env.get("VAN_BROWSER_CANARY_CERT", ""), env.get("VAN_BROWSER_CANARY_KEY", "")
    if not control:
        return red("egress proxy control socket unconfigured: the canary runs through the proxy")
    try:
        key = service.load_fence_key(env.get("VAN_HARNESS_FENCE_KEY_FILE", ""))
    except (OSError, ValueError) as exc:
        return red(f"fence key unreadable: {type(exc).__name__}")
    if key is None:
        return red("fence key required: the canary arms the proxy's canary exception with it")

    try:
        server, log = _fixture(canary.address, canary.port, cert, cert_key)
    except (OSError, ssl.SSLError) as exc:
        return red(f"canary fixture could not serve {canary.address}:{canary.port}: {type(exc).__name__}")
    scope = {"entries": [{"origin": canary.origin, "path_prefix": "/docs/"}]}
    task = egress.CANARY_TASK_ID

    def mac(generation: int, holder: str) -> str:
        return service.canary_mac(key, egress.CANARY_ALIAS, generation, holder, task, canary.origin, canary.address)

    def arm(generation: int) -> dict:
        holder = f"qualify-canary-{generation}"
        return _control(control, {"op": "canary", "alias": egress.CANARY_ALIAS, "lease_generation": generation,
                                  "lease_holder_id": holder, "task_id": task, "canary_mac": mac(generation, holder)})

    def call(path: str, generation: int, *, task_id: str = task, canary_mac: bool = True, **body):
        alias = egress.CANARY_ALIAS
        holder = f"qualify-canary-{generation}"
        envelope = {"mode": "PRODUCTION_ACTUATOR", "allow_helper_authoring": False, "profile_alias": alias,
                    "target_domain": canary.host, "task_id": task_id, "lease_generation": generation,
                    "lease_holder_id": holder, "task_scope": scope, "mutating": False, **body}
        envelope["lease_mac"] = service.fence_mac(key, alias, generation, holder)
        envelope["effect_mac"] = service.effect_mac(key, alias, generation, holder, task_id, False,
                                                    service.scope_digest(scope))
        if canary_mac:
            envelope["canary_mac"] = mac(generation, holder)
        request = urllib.request.Request(args.worker + path, data=json.dumps(envelope).encode(),
                                         headers={"content-type": "application/json"}, method="POST")
        try:
            # Loopback only: never through a proxy the environment may name.
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=60) as response:
                return response.status, json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read() or b"{}")

    def writes() -> list[tuple[str, str]]:
        return [e for e in log if e[0] not in ("GET", "HEAD", "OPTIONS")]

    try:
        base = int(time.time())  # newer than any generation this profile has seen
        for offset, (case, expect_click) in enumerate((("immediate", 409), ("delayed", 200))):
            generation = base + offset
            result: dict = {"arm": arm(generation)}
            nav = call("/navigate", generation, url=f"{canary.origin}/docs/{case}")
            described = call("/describe", generation, locator="#b")
            binding = (described[1] or {}).get("binding")
            click = call("/click", generation, locator="#b", binding=binding)
            time.sleep(args.wait)
            after = call("/scroll", generation, request={"y": 10})
            released = call("/release", generation)
            result.update({
                "navigate": nav[0], "describe": described[0], "click": [click[0], click[1].get("error")],
                "next_action": [after[0], after[1].get("error")], "release": released[1],
                "writes_reaching_server": writes(),
            })
            result["ok"] = (
                result["arm"].get("ok") is True
                and nav[0] == 200 and described[0] == 200 and binding is not None and click[0] == expect_click
                and (click[1].get("error") == "NETWORK_WRITE_BLOCKED:POST" if expect_click == 409 else True)
                and after == (409, {"error": "NETWORK_WRITE_BLOCKED:POST"})
                and released[0] == 200 and released[1].get("guard") == "ENDED"
                and released[1].get("blocked") == "NETWORK_WRITE_BLOCKED:POST"
                and not writes()
            )
            report["cases"][case] = result

        # The proxy itself, on the canary lease's own listener while its policy is in force.
        generation = base + 2
        result = {"arm": arm(generation)}
        nav = call("/navigate", generation, url=f"{canary.origin}/docs/proxy")
        listener = _control(control, {"op": "listener", "alias": egress.CANARY_ALIAS})
        hostport = f"{canary.host}:{canary.port}" if canary.port != 443 else canary.host
        before = len(log)
        get = _through_proxy(listener.get("port"), canary.host, canary.port,
                             f"GET /docs/probe HTTP/1.1\r\nHost: {hostport}\r\n\r\n".encode())
        ws = _through_proxy(listener.get("port"), canary.host, canary.port, (
            f"GET /docs/ws-pay?amount=500 HTTP/1.1\r\nHost: {hostport}\r\nUpgrade: websocket\r\n"
            "Connection: Upgrade\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: dmFuLWNhbmFyeS1wcm9iZQ==\r\n\r\n").encode())
        time.sleep(0.5)
        seen = log[before:]
        released = call("/release", generation)
        result.update({"navigate": nav[0], "get": list(get), "websocket": list(ws), "fixture_saw": seen,
                       "release": released[1]})
        result["ok"] = (
            result["arm"].get("ok") is True and nav[0] == 200
            and get == (200, None) and ("GET", "/docs/probe") in seen
            and ws == (403, "EGRESS_WEBSOCKET_REFUSED")
            and not [e for e in log if e[1].endswith("/ws-pay")]
            and released[0] == 200 and released[1].get("guard") == "ENDED"
        )
        report["cases"]["proxy"] = result

        # Never reachable by a task scope: an ordinary task naming the canary origin.
        harness = call("/navigate", base + 3, task_id="qualify-task", canary_mac=False,
                       url=f"{canary.origin}/docs/proxy")
        probe_generation, probe_holder = 1 << 40, "qualify"
        policy = _control(control, {
            "op": "policy", "alias": PROBE_ALIAS, "lease_generation": probe_generation,
            "lease_holder_id": probe_holder, "task_id": "qualify-task", "mutating": False, "task_scope": scope,
            "effect_mac": service.effect_mac(key, PROBE_ALIAS, probe_generation, probe_holder, "qualify-task",
                                             False, service.scope_digest(scope))})
        report["cases"]["task_refused"] = {
            "harness": [harness[0], harness[1].get("error")], "proxy": policy.get("error"),
            "ok": harness == (409, {"error": "TASK_SCOPE_RESERVED_HOST"})
            and policy == {"ok": False, "error": "POLICY_SCOPE_RESERVED_HOST"},
        }
    except Exception as exc:  # noqa: BLE001 - reported, never GREEN
        report["error"] = type(exc).__name__
    finally:
        server.shutdown()
        server.server_close()
    report["ok"] = bool(report["cases"]) and all(c.get("ok") for c in report["cases"].values()) and "error" not in report
    print(json.dumps(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
