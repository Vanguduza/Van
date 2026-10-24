"""Review I8 (independent review of 17fec5d8) — egress proxy findings, against the real proxy
process and fixture servers whose request logs are the instrument (outside the proxy).

* MAJOR-3: a bare LF in a header value was forwarded verbatim and became a second request
  upstream (a POST under a read-only policy; a DELETE outside the path scope under a mutating
  one). Now refused; the forwarded target is the parsed one; only the configured client uid
  may use a listener (the kernel's socket table names the owner of the client socket).
* MINOR-2: after a proxy restart a captured policy of an ended lease was accepted again.
* MINOR-7: OPTIONS was refused although the guard treats it as a read.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import ssl
import subprocess
import sys
import time
from pathlib import Path

import pytest

import cdp_harness_kit as kit

ROOT = Path(__file__).resolve().parents[2]
PROXY = ROOT / "deploy/van-browser-core/browser/egress_proxy.py"
KEY = b"i" * 48
SCOPE = {"entries": [{"origin": "https://docs.example.com", "path_prefix": "/docs/"},
                     {"origin": "http://docs.example.com", "path_prefix": "/docs/"}]}

pytestmark = pytest.mark.skipif(not Path("/usr/bin/openssl").is_file(), reason="needs openssl")


def _load_proxy_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("van_egress_i8", PROXY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ep = _load_proxy_module()


class Rig:
    def __init__(self, tmp: Path, **extra: str) -> None:
        self.tmp = tmp
        self.https = kit.FixtureServer(lambda h, p: None, tmp)
        self.http = kit.FixtureServer(lambda h, p: None, tmp, tls=False)
        (tmp / "k").write_bytes(KEY)
        self.ctl = str(tmp / "c.sock")
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("VAN_", "HTTP", "http"))}
        self.env.update({
            "VAN_EGRESS_CONTROL_SOCKET": self.ctl, "VAN_EGRESS_STATE_DIR": str(tmp / "st"),
            "VAN_EGRESS_FENCE_KEY_FILE": str(tmp / "k"), "VAN_EGRESS_DECISION_LOG": str(tmp / "d.jsonl"),
            "VAN_EGRESS_PORT_RANGE": "22000-22999",
            "VAN_EGRESS_TEST_RESOLVE": json.dumps({"*:443": f"127.0.0.1:{self.https.port}", "*:80": f"127.0.0.1:{self.http.port}"}),
            "VAN_EGRESS_TEST_UPSTREAM_CAFILE": str(tmp / "cert.pem"), **extra,
        })
        self.proc = None
        self.start()

    def start(self) -> None:
        Path(self.ctl).unlink(missing_ok=True)
        self.proc = subprocess.Popen([sys.executable, str(PROXY)], env=self.env, stderr=subprocess.PIPE)
        deadline = time.monotonic() + 20
        while not Path(self.ctl).exists():
            assert self.proc.poll() is None and time.monotonic() < deadline, self.proc.stderr.read()
            time.sleep(0.05)

    def stop(self) -> None:
        self.proc.terminate()
        self.proc.wait(5)

    def call(self, msg: dict) -> dict:
        with socket.socket(socket.AF_UNIX) as s:
            s.settimeout(5)
            s.connect(self.ctl)
            s.sendall(json.dumps(msg).encode() + b"\n")
            return json.loads(s.makefile().readline())

    def policy(self, generation: int, mutating: bool, alias: str = "a") -> dict:
        return self.call({"op": "policy", "alias": alias, "lease_generation": generation, "lease_holder_id": "h",
                          "task_id": "t", "mutating": mutating, "task_scope": SCOPE,
                          "effect_mac": ep.effect_mac(KEY, alias, generation, "h", "t", mutating, ep.scope_digest(SCOPE))})

    def port(self, alias: str = "a") -> int:
        return self.call({"op": "listener", "alias": alias})["port"]

    def upstream(self) -> list:
        return list(self.https.log) + list(self.http.log)

    def clear(self) -> None:
        self.https.log.clear()
        self.http.log.clear()

    def close(self) -> None:
        self.stop()
        self.https.close()
        self.http.close()


def _recv(sock, timeout=3.0) -> bytes:
    sock.settimeout(timeout)
    out = b""
    try:
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            out += chunk
    except (socket.timeout, ssl.SSLError, OSError):
        pass
    return out


def _tls(port: int, host: str = "docs.example.com"):
    s = socket.create_connection(("127.0.0.1", port), timeout=5)
    s.sendall(f"CONNECT {host}:443 HTTP/1.1\r\nHost: {host}:443\r\n\r\n".encode())
    head = b""
    while b"\r\n\r\n" not in head:
        chunk = s.recv(1)
        if not chunk:
            break
        head += chunk
    assert b" 200 " in head.split(b"\r\n")[0], head
    ctx = ssl.create_default_context()
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    return ctx.wrap_socket(s, server_hostname=host)


def _refused(answer: bytes) -> str | None:
    if b"X-Van-Egress-Refused: " not in answer:
        return None
    return answer.split(b"X-Van-Egress-Refused: ")[1].split(b"\r\n")[0].decode()


@pytest.fixture
def rig(tmp_path):
    r = Rig(tmp_path)
    try:
        yield r
    finally:
        r.close()


SMUGGLE_POST = (b"GET /docs/x HTTP/1.1\r\nHost: docs.example.com\r\nX-A: 1\n\nPOST /api/pay HTTP/1.1\n"
                b"Host: docs.example.com\nX-Pad: z\r\n\r\n")
SMUGGLE_DELETE = (b"GET /docs/x HTTP/1.1\r\nHost: docs.example.com\r\nX-A: 1\n\nDELETE /admin/all HTTP/1.1\n"
                  b"Host: docs.example.com\nX-Pad: z\r\n\r\n")


def test_a_bare_lf_smuggled_request_never_reaches_upstream(rig):
    assert rig.policy(1, False)["ok"] is True
    port = rig.port()
    t = _tls(port)
    t.sendall(SMUGGLE_POST)
    assert _refused(_recv(t)) == "EGRESS_REQUEST_INVALID"
    s = socket.create_connection(("127.0.0.1", port))
    s.sendall(SMUGGLE_POST.replace(b"GET /docs/x", b"GET http://docs.example.com/docs/x"))
    assert _refused(_recv(s)) == "EGRESS_REQUEST_INVALID"
    # Under a mutating policy a smuggled DELETE outside the path scope reached upstream too.
    assert rig.policy(2, True)["ok"] is True
    t = _tls(port)
    t.sendall(SMUGGLE_DELETE)
    assert _refused(_recv(t)) == "EGRESS_REQUEST_INVALID"
    time.sleep(0.5)
    assert rig.upstream() == []
    # The instrument works: the same GET without the injection reaches the server.
    t = _tls(port)
    t.sendall(b"GET /docs/x HTTP/1.1\r\nHost: docs.example.com\r\n\r\n")
    assert _recv(t).startswith(b"HTTP/1.1 200")
    assert rig.upstream() == [("GET", "docs.example.com", "/docs/x")]


def test_the_server_sees_the_normalised_target_the_proxy_judged(rig):
    assert rig.policy(1, False)["ok"] is True
    t = _tls(rig.port())
    t.sendall(b"GET /docs/%2e%2e/docs/y?a=1 HTTP/1.1\r\nHost: docs.example.com\r\n\r\n")
    assert _recv(t).startswith(b"HTTP/1.1 200")
    assert rig.upstream() == [("GET", "docs.example.com", "/docs/y")]


def test_options_is_a_read_in_scope_and_refused_out_of_scope(rig):
    assert rig.policy(1, False)["ok"] is True
    port = rig.port()
    t = _tls(port)
    t.sendall(b"OPTIONS /docs/x HTTP/1.1\r\nHost: docs.example.com\r\nOrigin: https://docs.example.com\r\n\r\n")
    assert _recv(t).startswith(b"HTTP/1.1 200")
    t = _tls(port)
    t.sendall(b"OPTIONS /docs/x HTTP/1.1\r\nHost: docs.example.com\r\nContent-Length: 2\r\n\r\nab")
    assert _refused(_recv(t)) == "EGRESS_WRITE_REFUSED"
    s = socket.create_connection(("127.0.0.1", port))
    s.sendall(b"OPTIONS http://evil.example.net/x HTTP/1.1\r\nHost: evil.example.net\r\n\r\n")
    assert _refused(_recv(s)) == "EGRESS_ORIGIN_OUT_OF_SCOPE"
    assert rig.upstream() == [("OPTIONS", "docs.example.com", "/docs/x")]


def test_a_restart_does_not_readmit_an_ended_or_older_lease(rig):
    assert rig.policy(1, False)["ok"] is True
    assert rig.policy(2, False)["ok"] is True
    assert rig.call({"op": "revoke", "alias": "a", "lease_generation": 2, "lease_holder_id": "h", "final": True,
                     "revoke_mac": ep.revoke_mac(KEY, "a", 2, "h", True)})["ok"] is True
    rig.stop()
    rig.start()
    assert rig.policy(1, True) == {"ok": False, "error": "POLICY_GENERATION_STALE"}
    assert rig.policy(2, True) == {"ok": False, "error": "POLICY_LEASE_ENDED"}
    port = rig.port()
    s = socket.create_connection(("127.0.0.1", port))
    s.sendall(b"CONNECT docs.example.com:443 HTTP/1.1\r\nHost: docs.example.com:443\r\n\r\n")
    assert _refused(_recv(s)) == "EGRESS_POLICY_UNKNOWN"
    assert rig.policy(3, False)["ok"] is True  # the next lease works
    assert rig.upstream() == []


def _as_uid(uid: int, port: int, data: bytes) -> str:
    code = ("import socket,sys;s=socket.create_connection(('127.0.0.1',int(sys.argv[1])),timeout=5);"
            "s.sendall(bytes.fromhex(sys.argv[2]));print(s.recv(4096).decode('latin-1').split('\\r\\n')[0])")
    proc = subprocess.run(["setpriv", f"--reuid={uid}", f"--regid={uid}", "--clear-groups", sys.executable, "-c",
                           code, str(port), data.hex()], capture_output=True, text=True, timeout=30)
    return proc.stdout.strip() or proc.stderr[-300:]


@pytest.mark.skipif(os.geteuid() != 0 or not shutil.which("setpriv"), reason="needs root and setpriv")
def test_only_the_configured_client_uid_may_use_a_listener(tmp_path):
    r = Rig(tmp_path, VAN_EGRESS_CLIENT_UID="65534")
    try:
        assert r.policy(1, False)["ok"] is True
        port = r.port()
        request = b"GET http://docs.example.com/docs/x HTTP/1.1\r\nHost: docs.example.com\r\n\r\n"
        s = socket.create_connection(("127.0.0.1", port))  # root: not the browser user
        s.sendall(request)
        assert _refused(_recv(s)) == "EGRESS_CLIENT_REFUSED"
        assert r.upstream() == []
        assert _as_uid(65534, port, request) == "HTTP/1.1 200 OK"   # the browser user
        assert _as_uid(65533, port, request) == "HTTP/1.1 403 Forbidden"
        assert r.upstream() == [("GET", "docs.example.com", "/docs/x")]
        codes = [json.loads(x)["code"] for x in (tmp_path / "d.jsonl").read_text().splitlines()]
        assert codes.count("EGRESS_CLIENT_REFUSED") == 2
    finally:
        r.close()
