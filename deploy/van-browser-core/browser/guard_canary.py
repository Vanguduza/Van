#!/usr/bin/env python3
"""Network-effect guard canary for the INSTALLED van-browser-core (review I7 minor 5, unit G11).

The guard suite runs in CI against Chromium 1194; bootstrap.sh installs Playwright 1.63.0's
Chromium (build 1243). CDP Fetch interception, related-target auto-attach and the launch flags
the guard depends on are Chromium behaviour, so they are qualified on the Chromium the host
actually runs: this canary drives the running Harness worker (127.0.0.1:9141, its real
browser-harness child and its Chromium) against a local fixture server and reads that server's
request log — the only instrument a page cannot lie to.

    python3 guard_canary.py [--worker http://127.0.0.1:9141] [--runtime-env /etc/van-browser-core/runtime.env]

Cases (a canary profile ``guard_canary``, a read-only task scoped to /docs/ on the fixture):
  immediate   a click whose handler POSTs at once           -> 409 NETWORK_WRITE_BLOCKED:POST
  delayed     a click whose handler POSTs 2.5 s later       -> the click answers 200, nothing
              reaches the server within 8 s, the lease then refuses NETWORK_WRITE_BLOCKED:POST
  release     /release ends each lease's guard (page frozen)
Prints one JSON object; exits 0 only when every case holds. Anything it cannot establish is RED.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
ALIAS = "guard_canary"
PAY = "fetch('/api/pay',{method:'POST',body:'canary'})"
PAGES = {
    "/docs/immediate": f'<button id="b" onclick="{PAY}">Next</button>',
    "/docs/delayed": f'<button id="b" onclick="setTimeout(()=>{PAY},2500)">Next</button>',
}


def _fixture() -> tuple[ThreadingHTTPServer, list[tuple[str, str]]]:
    log: list[tuple[str, str]] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # noqa: D401 - quiet
            pass

        def _any(self):
            length = int(self.headers.get("content-length") or 0)
            if length:
                self.rfile.read(length)
            path = self.path.split("?")[0]
            log.append((self.command, path))
            body = PAGES.get(path, "<p>ok</p>")
            data = f"<!doctype html><html><head><title>{path}</title></head><body>{body}</body></html>".encode()
            self.send_response(200)
            self.send_header("content-type", "text/html")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = _any

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
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
    spec = importlib.util.spec_from_file_location("van_harness_service_canary", HERE / "harness_service.py")
    service = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(service)  # its MAC helpers; the worker itself is the running service
    key = None
    key_file = env.get("VAN_HARNESS_FENCE_KEY_FILE", "")
    if key_file:
        try:
            key = service.load_fence_key(key_file)
        except (OSError, ValueError) as exc:
            report["error"] = f"fence key unreadable: {type(exc).__name__}"
            print(json.dumps(report))
            return 1

    server, log = _fixture()
    origin = f"http://127.0.0.1:{server.server_address[1]}"
    scope = {"entries": [{"origin": origin, "path_prefix": "/docs/"}]}

    def call(path: str, generation: int, **body):
        holder = f"qualify-canary-{generation}"
        envelope = {"mode": "PRODUCTION_ACTUATOR", "allow_helper_authoring": False, "profile_alias": ALIAS,
                    "target_domain": "127.0.0.1", "task_id": holder, "lease_generation": generation,
                    "lease_holder_id": holder, "task_scope": scope, "mutating": False, **body}
        if key is not None:
            envelope["lease_mac"] = service.fence_mac(key, ALIAS, generation, holder)
            envelope["effect_mac"] = service.effect_mac(key, ALIAS, generation, holder, holder, False,
                                                        service.scope_digest(scope))
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
            result: dict = {}
            nav = call("/navigate", generation, url=f"{origin}/docs/{case}")
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
                nav[0] == 200 and described[0] == 200 and binding is not None and click[0] == expect_click
                and (click[1].get("error") == "NETWORK_WRITE_BLOCKED:POST" if expect_click == 409 else True)
                and after == (409, {"error": "NETWORK_WRITE_BLOCKED:POST"})
                and released[0] == 200 and released[1].get("guard") == "ENDED"
                and released[1].get("blocked") == "NETWORK_WRITE_BLOCKED:POST"
                and not writes()
            )
            report["cases"][case] = result
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
