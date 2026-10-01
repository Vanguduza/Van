"""Review I9 (independent review of 28be6c42) — egress proxy, against the real proxy process
and a raw upstream whose request log is the instrument (outside the proxy).

* MAJOR-1: for an ``Upgrade`` request the proxy piped every later client byte upstream without
  waiting for the upstream's answer. An upstream that ignored the upgrade answered ``200`` and
  kept the connection open, so a second, pipelined request (a ``DELETE`` outside the task's
  path scope) reached it unjudged. ``Upgrade: websocket, h2c`` was also admitted, so an
  upstream could switch to a protocol the proxy never reads. Now: only the single token
  ``websocket`` is admitted, and client bytes are relayed only after the upstream answers
  ``101`` naming ``websocket``; otherwise exactly one response comes back and nothing more of
  the client's reaches upstream.
"""
from __future__ import annotations

import json
import socket
import ssl
import threading
import time
from pathlib import Path

import pytest

import cdp_harness_kit as kit
from test_browser_egress_proxy_i8 import Rig, _recv, _refused, _tls

pytestmark = pytest.mark.skipif(not Path("/usr/bin/openssl").is_file(), reason="needs openssl")


class RawUpstream:
    """An HTTP/1.1 upstream that keeps the connection alive and logs every request line.

    ``answer`` decides the reply to an ``Upgrade`` request: ``"ignore"`` (a plain 200, as a
    server that does not speak WebSocket does), ``"websocket"`` or ``"h2c"`` (a 101 naming that
    protocol, after which every byte received is logged as ``("RAW", bytes)``)."""

    def __init__(self, directory: Path, answer: str, tls: bool) -> None:
        self.answer = answer
        self.log: list = []
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
        self.port = self.sock.getsockname()[1]
        self.ctx = None
        if tls:
            self.ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            self.ctx.load_cert_chain(*kit._certificate(directory))
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self) -> None:
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn: socket.socket) -> None:
        try:
            if self.ctx is not None:
                conn = self.ctx.wrap_socket(conn, server_side=True)
            conn.settimeout(5)
            buf = b""
            while True:
                while b"\r\n\r\n" not in buf:
                    chunk = conn.recv(65536)
                    if not chunk:
                        return
                    buf += chunk
                head, _, buf = buf.partition(b"\r\n\r\n")
                lines = head.decode("latin-1").split("\r\n")
                method, path, _ = lines[0].split(" ")
                headers = {k.strip().lower(): v.strip() for k, v in (l.split(":", 1) for l in lines[1:])}
                self.log.append((method, headers.get("host", "").split(":")[0], path))
                if "upgrade" in headers and self.answer != "ignore":
                    conn.sendall(f"HTTP/1.1 101 Switching Protocols\r\nUpgrade: {self.answer}\r\n"
                                 "Connection: Upgrade\r\n\r\n".encode())
                    if buf:
                        self.log.append(("RAW", buf))
                    while True:
                        chunk = conn.recv(65536)
                        if not chunk:
                            return
                        self.log.append(("RAW", chunk))
                        conn.sendall(b"echo:" + chunk)
                conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
        except (OSError, ValueError, ssl.SSLError):
            pass
        finally:
            conn.close()

    def requests(self) -> list:
        return [e for e in self.log if e[0] != "RAW"]

    def raw(self) -> bytes:
        return b"".join(e[1] for e in self.log if e[0] == "RAW")

    def close(self) -> None:
        self.sock.close()


@pytest.fixture
def make_rig(tmp_path):
    made: list = []

    def make(answer: str):
        certs = tmp_path / f"up-{answer}"
        certs.mkdir()
        https, http = RawUpstream(certs, answer, tls=True), RawUpstream(certs, answer, tls=False)
        home = tmp_path / f"rig-{answer}"
        home.mkdir()
        rig = Rig(home, VAN_EGRESS_TEST_RESOLVE=json.dumps({"*:443": f"127.0.0.1:{https.port}",
                                                      "*:80": f"127.0.0.1:{http.port}"}),
                  VAN_EGRESS_TEST_UPSTREAM_CAFILE=str(certs / "cert.pem"))
        made.extend([rig, https, http])
        return rig, https, http

    yield make
    for thing in made:
        thing.close()


UPGRADE_THEN_DELETE = (b"GET /docs/ws HTTP/1.1\r\nHost: docs.example.com\r\nUpgrade: websocket\r\n"
                       b"Connection: Upgrade\r\n\r\n"
                       b"DELETE /admin/all HTTP/1.1\r\nHost: docs.example.com\r\nContent-Length: 0\r\n\r\n")


def test_a_request_pipelined_behind_an_ignored_upgrade_never_reaches_upstream(make_rig):
    rig, https, http = make_rig("ignore")
    assert rig.policy(1, True)["ok"] is True
    port = rig.port()
    t = _tls(port)
    t.sendall(UPGRADE_THEN_DELETE)
    answer = _recv(t)
    assert answer.startswith(b"HTTP/1.1 200") and answer.count(b"HTTP/1.1 ") == 1, answer
    s = socket.create_connection(("127.0.0.1", port))
    s.sendall(UPGRADE_THEN_DELETE.replace(b"GET /docs/ws", b"GET http://docs.example.com/docs/ws", 1))
    answer = _recv(s)
    assert answer.startswith(b"HTTP/1.1 200") and answer.count(b"HTTP/1.1 ") == 1, answer
    time.sleep(0.5)
    assert https.requests() == [("GET", "docs.example.com", "/docs/ws")]
    assert http.requests() == [("GET", "docs.example.com", "/docs/ws")]


def test_a_websocket_the_upstream_accepts_still_carries_frames_both_ways(make_rig):
    """Control: the fix gates the relay on the upstream's 101, it does not break WebSockets."""
    rig, https, _ = make_rig("websocket")
    assert rig.policy(1, True)["ok"] is True
    t = _tls(rig.port())
    t.sendall(b"GET /docs/ws HTTP/1.1\r\nHost: docs.example.com\r\nUpgrade: websocket\r\n"
              b"Connection: Upgrade\r\n\r\n")
    t.settimeout(5)
    head = b""
    while b"\r\n\r\n" not in head:
        head += t.recv(1)
    assert head.startswith(b"HTTP/1.1 101"), head
    t.sendall(b"frame-1")
    assert t.recv(64) == b"echo:frame-1"
    assert https.raw() == b"frame-1"


def test_an_upgrade_to_a_protocol_the_proxy_does_not_read_never_opens_a_tunnel(make_rig):
    rig, https, _ = make_rig("h2c")
    assert rig.policy(1, True)["ok"] is True
    port = rig.port()
    t = _tls(port)
    t.sendall(UPGRADE_THEN_DELETE.replace(b"Upgrade: websocket", b"Upgrade: websocket, h2c", 1))
    assert _refused(_recv(t)) == "EGRESS_UPGRADE_REFUSED"
    assert https.requests() == []
    # Asked for websocket, the upstream switches to h2c: the client's next bytes stay put.
    t = _tls(port)
    t.sendall(UPGRADE_THEN_DELETE)
    answer = _recv(t)
    assert _refused(answer) == "EGRESS_UPGRADE_REFUSED", answer
    time.sleep(0.5)
    assert https.requests() == [("GET", "docs.example.com", "/docs/ws")]
    assert https.raw() == b""
