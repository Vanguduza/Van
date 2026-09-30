"""Unit G12 — the van-browser-core egress proxy, through real Chromium.

Owner answer 2026-09-30 after review I7 ("Egress proxy (Recommended)"): the browser goes out
through a local egress proxy that refuses WebSocket upgrades and non-GET requests unless the
task is admitted as mutating.

What runs here is production code end to end except the network itself:

* the proxy is ``deploy/van-browser-core/browser/egress_proxy.py`` run as its own process
  (its ``VAN_EGRESS_TEST_*`` overrides point every host at the local fixture servers and trust
  the fixture's certificate upstream; the proxy refuses those overrides in a trust zone);
* Chromium is launched by the Harness worker's own ``ChromeSession.ensure()`` (the argv the
  worker uses in production, plus ``--no-sandbox`` through a wrapper because this sandbox runs
  as root) — so the proxy flags, the SPKI pin and ``--disable-quic`` are the real ones;
* the policy reaches the proxy through the worker's ``network_guard_env`` (effect MAC verified
  by the worker, then again by the proxy).

The instrument is the fixture servers' request log (outside the browser and the proxy): a
refused handshake or write never appears there. There is no ``--host-resolver-rules`` and no
``--ignore-certificate-errors``: Chromium resolves nothing itself and trusts the interception
certificate only through the pinned leaf key.
"""
from __future__ import annotations

import importlib.util
import json
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

import cdp_harness_kit as kit

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "deploy/van-browser-core/browser/harness_service.py"
PROXY = ROOT / "deploy/van-browser-core/browser/egress_proxy.py"
KEY = b"e" * 64
DOCS = "docs.example.com"

pytestmark = pytest.mark.skipif(
    not kit.chromium_available() or not Path("/usr/bin/openssl").is_file(),
    reason="needs the pinned Chromium and openssl",
)

PAGES = {
    "/docs/page": "<p id='p'>docs</p>",
    "/docs/ws": "<button id='b' onclick=\"window.__ws=new WebSocket('ws://docs.example.com:8080/api/ws-pay?amount=500')\">Next</button>",
    "/docs/wss": "<button id='b' onclick=\"window.__ws=new WebSocket('wss://docs.example.com/api/ws-pay?amount=500')\">Next</button>",
    "/docs/wss_oos": "<button id='b' onclick=\"window.__ws=new WebSocket('wss://evil.example.net/api/ws-pay?amount=500')\">Next</button>",
    "/docs/get_oos": "<button id='b' onclick=\"new Image().src='https://evil.example.net/api/transfer-get?amount=500'\">Next</button>",
    "/docs/delay_post": "<button id='b' onclick=\"setTimeout(()=>fetch('/docs/api/pay',{method:'POST',body:'amount=500'}),1500)\">Next</button>",
    "/docs/get_body": "<button id='b' onclick=\"fetch('/docs/api/pay',{method:'PUT',body:'amount=500'})\">Next</button>",
    "/docs/loopback": "<button id='b' onclick=\"new Image().src='http://127.0.0.1:__LOOP__/health'\">Next</button>",
}
LOOP = {"port": None}


def _pages(host, path):
    if host.startswith("evil"):
        return None
    page = PAGES.get(path)
    if page is None:
        return None
    return f"<!doctype html><html><head><title>{path}</title></head><body>{page.replace('__LOOP__', str(LOOP['port']))}</body></html>"


class LoopbackService:
    """Stands in for a zone-local loopback service (the Harness API, a CDP port)."""

    def __init__(self) -> None:
        self.log: list[str] = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                outer.log.append(self.path)
                self.send_response(200)
                self.send_header("content-length", "2")
                self.end_headers()
                self.wfile.write(b"ok")

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


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


class EgressRig:
    def __init__(self, monkeypatch, tmp_path: Path) -> None:
        self.tmp = tmp_path
        self.https = kit.FixtureServer(_pages, tmp_path)
        self.http = kit.FixtureServer(_pages, tmp_path, tls=False)
        self.loop = LoopbackService()
        LOOP["port"] = self.loop.port
        key_file = tmp_path / "fence.key"
        key_file.write_bytes(KEY)
        self.control = str(tmp_path / "egress.sock")
        self.decisions = tmp_path / "decisions.jsonl"
        env = {k: v for k, v in os.environ.items() if not k.startswith(("VAN_", "HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"))}
        env.update({
            "VAN_EGRESS_CONTROL_SOCKET": self.control,
            "VAN_EGRESS_STATE_DIR": str(tmp_path / "egress-state"),
            "VAN_EGRESS_FENCE_KEY_FILE": str(key_file),
            "VAN_EGRESS_DECISION_LOG": str(self.decisions),
            "VAN_EGRESS_PORT_RANGE": "20000-60000",
            "VAN_EGRESS_TEST_RESOLVE": json.dumps({"*:443": f"127.0.0.1:{self.https.port}",
                                                   "*:80": f"127.0.0.1:{self.http.port}",
                                                   "*:8080": f"127.0.0.1:{self.http.port}",
                                                   f"127.0.0.1:{self.loop.port}": f"127.0.0.1:{self.loop.port}"}),
            "VAN_EGRESS_TEST_UPSTREAM_CAFILE": str(tmp_path / "cert.pem"),
        })
        self.proxy = subprocess.Popen([sys.executable, str(PROXY)], env=env,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        deadline = time.monotonic() + 20
        while not Path(self.control).exists():
            if self.proxy.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError(f"egress proxy did not start: {self.proxy.stderr.read()!r}")
            time.sleep(0.05)
        wrapper = tmp_path / "chrome-wrapper.sh"
        wrapper.write_text(f"#!/bin/sh\nexec {kit.CHROMIUM} --no-sandbox \"$@\"\n", encoding="utf-8")
        wrapper.chmod(0o755)
        for name, value in {
            "VAN_CHROMIUM_EXECUTABLE": str(wrapper),
            "VAN_BROWSER_PROFILE_ROOT": str(tmp_path / "profiles"),
            "VAN_BROWSER_RUNTIME_ROOT": str(tmp_path / "run"),
            "VAN_HARNESS_STATE_ROOT": str(tmp_path / "harness-state"),
            "VAN_HARNESS_FENCE_KEY_FILE": str(key_file),
            "VAN_BROWSER_EGRESS_CONTROL_SOCKET": self.control,
        }.items():
            monkeypatch.setenv(name, value)
        monkeypatch.delenv("VAN_TRUST_ZONE", raising=False)
        spec = importlib.util.spec_from_file_location("van_harness_egress", HARNESS)
        self.hs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.hs)
        self.sessions: list[kit.HarnessSession] = []
        self.generation = 0

    # -- the worker's own paths
    def policy(self, alias: str, *, mutating: bool, scope: dict) -> None:
        self.generation += 1
        body = {"lease_generation": self.generation, "lease_holder_id": "holder", "task_id": "task-1",
                "mutating": mutating, "task_scope": scope}
        body["effect_mac"] = self.hs.effect_mac(KEY, alias, self.generation, "holder", "task-1", mutating,
                                                self.hs.scope_digest(scope))
        self.hs.network_guard_env(body, alias)

    def launch(self, alias: str) -> kit.HarnessSession:
        chrome = self.hs.POOL.get(alias)
        chrome.ensure()
        lines = (chrome.profile_dir / "DevToolsActivePort").read_text().splitlines()
        session = kit.HarnessSession(f"ws://127.0.0.1:{lines[0]}{lines[1]}")
        self.sessions.append(session)
        return session

    def argv(self, alias: str) -> list[str]:
        pid = self.hs.POOL.get(alias).process.pid
        return Path(f"/proc/{pid}/cmdline").read_bytes().decode().split("\0")

    def visit(self, session: kit.HarnessSession, url: str, wait: float = 2.0) -> None:
        session.goto_url(url)
        time.sleep(wait)
        self.clear()

    def click(self, session: kit.HarnessSession, wait: float = 3.0) -> None:
        session.js("document.getElementById('b').click()")
        time.sleep(wait)

    def clear(self) -> None:
        self.https.log.clear()
        self.http.log.clear()
        self.loop.log.clear()
        self.decisions.write_text("", encoding="utf-8")

    def server_log(self) -> list[tuple[str, str, str]]:
        return list(self.https.log) + list(self.http.log)

    def decision_log(self) -> list[dict]:
        if not self.decisions.exists():
            return []
        return [json.loads(line) for line in self.decisions.read_text(encoding="utf-8").splitlines() if line]

    def close(self) -> None:
        for session in self.sessions:
            session.close()
        self.hs.POOL.close()
        self.proxy.terminate()
        try:
            self.proxy.wait(5)
        except subprocess.TimeoutExpired:
            self.proxy.kill()
        self.https.close()
        self.http.close()
        self.loop.close()


@pytest.fixture
def rig(monkeypatch, tmp_path):
    r = EgressRig(monkeypatch, tmp_path)
    try:
        yield r
    finally:
        r.close()


def _scope(*entries: tuple[str, str | None]) -> dict:
    return {"entries": [{"origin": origin, "path_prefix": prefix} for origin, prefix in entries]}


DOCS_SCOPE = _scope((f"https://{DOCS}", "/docs/"), (f"http://{DOCS}:8080", "/docs/"))


def _codes(rig: EgressRig) -> list[str]:
    return [d["code"] for d in rig.decision_log() if d["code"]]


def test_chromium_is_launched_through_the_proxy_with_quic_disabled(rig):
    rig.policy("egress_a", mutating=False, scope=DOCS_SCOPE)
    rig.launch("egress_a")
    argv = rig.argv("egress_a")
    proxy = [a for a in argv if a.startswith("--proxy-server=")]
    assert len(proxy) == 1 and proxy[0].startswith("--proxy-server=http://127.0.0.1:")
    assert "--proxy-bypass-list=<-loopback>" in argv
    assert "--disable-quic" in argv
    spki = [a for a in argv if a.startswith("--ignore-certificate-errors-spki-list=")]
    assert spki == [f"--ignore-certificate-errors-spki-list={_control(rig.control, {'op': 'health'})['leaf_spki_sha256']}"]
    assert "--ignore-certificate-errors" not in argv


def test_in_scope_get_passes_through_the_interception(rig):
    rig.policy("egress_a", mutating=False, scope=DOCS_SCOPE)
    session = rig.launch("egress_a")
    session.goto_url(f"https://{DOCS}/docs/page")
    time.sleep(2)
    assert ("GET", DOCS, "/docs/page") in rig.https.log
    assert session.js("document.getElementById('p') && document.getElementById('p').textContent") == "docs"
    assert session.js("location.protocol") == "https:"


def test_ws_handshake_to_ws_pay_is_refused_and_never_reaches_the_server(rig):
    # A non-default port: Chromium does not HTTPS-upgrade the navigation, so the page and its
    # ws:// stay plain text and the proxy reads the Upgrade request itself.
    rig.policy("egress_a", mutating=False, scope=_scope((f"http://{DOCS}:8080", "/docs/")))
    session = rig.launch("egress_a")
    rig.visit(session, f"http://{DOCS}:8080/docs/ws")
    assert session.js("location.href") == f"http://{DOCS}:8080/docs/ws"
    rig.click(session)
    assert [e for e in rig.server_log() if "ws-pay" in e[2]] == []
    assert "EGRESS_WEBSOCKET_REFUSED" in _codes(rig)


def test_wss_handshake_to_ws_pay_is_refused_inside_tls_and_never_reaches_the_server(rig):
    """The case a CONNECT allowlist cannot refuse: the host is in scope, the path is not a read."""
    rig.policy("egress_a", mutating=False, scope=DOCS_SCOPE)
    session = rig.launch("egress_a")
    rig.visit(session, f"https://{DOCS}/docs/wss")
    rig.click(session)
    assert [e for e in rig.server_log() if "ws-pay" in e[2]] == []
    assert "EGRESS_WEBSOCKET_REFUSED" in _codes(rig)


def test_a_mutating_task_may_open_a_websocket_inside_its_scope(rig):
    """Control: the refusal above is the policy, not a broken proxy."""
    rig.policy("egress_a", mutating=True, scope=_scope((f"https://{DOCS}", None)))
    session = rig.launch("egress_a")
    rig.visit(session, f"https://{DOCS}/docs/wss")
    rig.click(session)
    assert ("GET", DOCS, "/api/ws-pay") in rig.https.log


def test_out_of_scope_wss_host_and_out_of_scope_get_are_refused_at_connect(rig):
    rig.policy("egress_a", mutating=True, scope=_scope((f"https://{DOCS}", None)))
    session = rig.launch("egress_a")
    for page in ("/docs/wss_oos", "/docs/get_oos"):
        rig.visit(session, f"https://{DOCS}{page}")
        rig.click(session)
        assert [e for e in rig.server_log() if e[1].startswith("evil")] == []
        refused = [d for d in rig.decision_log() if d["method"] == "CONNECT" and d["origin"] == "evil.example.net:443"]
        assert refused and all(d["code"] == "EGRESS_CONNECT_OUT_OF_SCOPE" for d in refused)


def test_writes_after_the_guard_window_are_refused_for_a_read_only_task(rig):
    """Review I7: a POST 1.5 s (or 6 s, or on an interval) after the action outlived the
    in-browser guard's settle window and reached the server. The proxy's policy outlives it."""
    rig.policy("egress_a", mutating=False, scope=DOCS_SCOPE)
    session = rig.launch("egress_a")
    for page in ("/docs/delay_post", "/docs/get_body"):
        rig.visit(session, f"https://{DOCS}{page}")
        rig.click(session)
        assert kit.FixtureServer.writes(rig.https) == []
        assert "EGRESS_WRITE_REFUSED" in _codes(rig)


def test_a_mutating_task_may_write_inside_its_scope_only(rig):
    rig.policy("egress_a", mutating=True, scope=DOCS_SCOPE)
    session = rig.launch("egress_a")
    rig.visit(session, f"https://{DOCS}/docs/delay_post")
    rig.click(session)
    assert ("POST", DOCS, "/docs/api/pay") in rig.https.log
    # A mutating task whose scope is the page alone: its write to /docs/api/pay is outside it.
    rig.policy("egress_a", mutating=True, scope=_scope((f"https://{DOCS}", "/docs/delay_post")))
    rig.visit(session, f"https://{DOCS}/docs/delay_post")
    rig.click(session)
    assert kit.FixtureServer.writes(rig.https) == []
    assert "EGRESS_WRITE_OUT_OF_SCOPE" in _codes(rig)


def test_no_policy_means_every_request_is_refused(rig):
    session = rig.launch("egress_nopolicy")
    session.goto_url(f"https://{DOCS}/docs/page")
    time.sleep(2)
    session.goto_url(f"http://{DOCS}:8080/docs/page")
    time.sleep(2)
    assert rig.server_log() == []
    codes = _codes(rig)
    assert codes and set(codes) == {"EGRESS_POLICY_UNKNOWN"}


def test_loopback_goes_through_the_proxy_and_is_refused(rig):
    rig.policy("egress_a", mutating=False, scope=DOCS_SCOPE)
    session = rig.launch("egress_a")
    rig.visit(session, f"https://{DOCS}/docs/loopback")
    rig.click(session)
    assert rig.loop.log == []
    assert "EGRESS_ORIGIN_OUT_OF_SCOPE" in _codes(rig)


def test_a_policy_without_a_valid_effect_mac_is_refused_and_leaves_the_old_one(rig):
    rig.policy("egress_a", mutating=False, scope=DOCS_SCOPE)
    rig.generation += 1
    forged = {"op": "policy", "alias": "egress_a", "lease_generation": rig.generation, "lease_holder_id": "holder",
              "task_id": "task-1", "mutating": True, "task_scope": DOCS_SCOPE,
              "effect_mac": rig.hs.effect_mac(KEY, "egress_a", rig.generation, "holder", "task-1", False,
                                              rig.hs.scope_digest(DOCS_SCOPE))}
    assert _control(rig.control, forged) == {"ok": False, "error": "POLICY_MAC_INVALID"}
    stale = dict(forged, lease_generation=rig.generation - 2 if rig.generation > 2 else 0)
    assert _control(rig.control, stale)["ok"] is False
    # The worker refuses an action whose policy the proxy refused (flag flipped after MACing).
    body = {"lease_generation": rig.generation + 1, "lease_holder_id": "holder", "task_id": "task-1",
            "mutating": True, "task_scope": DOCS_SCOPE,
            "effect_mac": rig.hs.effect_mac(KEY, "egress_a", rig.generation + 1, "holder", "task-1", False,
                                            rig.hs.scope_digest(DOCS_SCOPE))}
    with pytest.raises(rig.hs.WorkerError) as err:
        rig.hs.network_guard_env(body, "egress_a")
    assert err.value.code == "NETWORK_EFFECT_MAC_INVALID"
    session = rig.launch("egress_a")
    rig.visit(session, f"https://{DOCS}/docs/delay_post")
    rig.click(session)
    assert kit.FixtureServer.writes(rig.https) == []


def test_interception_is_trusted_only_through_the_pinned_leaf_key(rig, monkeypatch):
    """Without the SPKI pin Chromium refuses the interception certificate: the trust is the
    flag on this Chromium, not a trust store."""
    rig.policy("egress_a", mutating=False, scope=DOCS_SCOPE)
    real = rig.hs.egress_proxy_flags
    monkeypatch.setattr(rig.hs, "egress_proxy_flags",
                        lambda alias: tuple(f for f in real(alias) if not f.startswith("--ignore-certificate-errors-spki-list")))
    session = rig.launch("egress_a")
    session.goto_url(f"https://{DOCS}/docs/page")
    time.sleep(2)
    assert ("GET", DOCS, "/docs/page") not in rig.https.log
    assert session.js("document.getElementById('p') === null") is True


def test_a_trust_zone_worker_refuses_to_start_chromium_without_the_proxy(rig, monkeypatch):
    monkeypatch.setattr(rig.hs, "EGRESS_CONTROL_SOCKET", "")
    monkeypatch.setattr(rig.hs, "TRUST_ZONE", "van-browser-core")
    with pytest.raises(rig.hs.WorkerError) as err:
        rig.hs.egress_proxy_flags("egress_a")
    assert err.value.code == "EGRESS_PROXY_UNCONFIGURED"
    with pytest.raises(rig.hs.WorkerError):
        rig.hs.push_egress_policy({}, "egress_a", DOCS_SCOPE, False)
    monkeypatch.setattr(rig.hs, "TRUST_ZONE", "")
    assert rig.hs.egress_proxy_flags("egress_a") == ("--disable-quic",)
