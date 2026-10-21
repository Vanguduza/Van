"""Framed TLS transport for the cTrader Open API (demo.ctraderapi.com:5035 / live:5035).

Wire: 4-byte big-endian length + ProtoMessage. One socket, a reader thread, requests
matched by clientMsgId, unsolicited events (execution, spots, errors) queued for the
adapter, ProtoHeartbeatEvent every 10 s. Credentials (app client id/secret, account
access token) are held by the transport only; nothing here sizes or decides."""

from __future__ import annotations

import queue
import socket
import ssl
import struct
import threading
import time
import uuid
from typing import Any, Callable, Optional

from vati.execution.base import VenueUnavailable
from vati.execution.ctrader.protoschema import SCHEMA

DEMO_HOST, LIVE_HOST, PORT = "demo.ctraderapi.com", "live.ctraderapi.com", 5035


class CtraderError(VenueUnavailable):
    pass


class CtraderApiError(RuntimeError):
    """A ProtoOAErrorRes / ProtoErrorRes: data, not a transport fault."""
    def __init__(self, code: str, description: str) -> None:
        super().__init__(f"{code}: {description}")
        self.code, self.description = code, description


class CtraderTransport:
    def __init__(self, *, host: str = DEMO_HOST, port: int = PORT, timeout_s: float = 10.0, connector: Optional[Callable[[str, int], Any]] = None, heartbeat_s: float = 10.0) -> None:
        self.host, self.port, self.timeout_s, self.heartbeat_s = host, port, timeout_s, heartbeat_s
        self._connector = connector
        self._sock = None
        self._lock = threading.Lock()
        self._pending: dict[str, queue.Queue] = {}
        self.events: queue.Queue = queue.Queue()
        self._reader: Optional[threading.Thread] = None
        self._alive = False
        self.sent = 0

    # ------------------------------------------------------------ lifecycle
    def connect(self) -> None:
        if self._sock is not None:
            return
        try:
            if self._connector is not None:
                self._sock = self._connector(self.host, self.port)
            else:
                raw = socket.create_connection((self.host, self.port), timeout=self.timeout_s)
                ctx = ssl.create_default_context(); ctx.minimum_version = ssl.TLSVersion.TLSv1_2
                self._sock = ctx.wrap_socket(raw, server_hostname=self.host)
        except (OSError, ssl.SSLError) as exc:
            raise CtraderError(f"cTrader connect failed: {exc}") from exc
        self._alive = True
        self._reader = threading.Thread(target=self._read_loop, daemon=True); self._reader.start()
        self._last_hb = time.monotonic()

    def close(self) -> None:
        self._alive = False
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None

    @property
    def connected(self) -> bool:
        return self._sock is not None and self._alive

    # ------------------------------------------------------------ io
    def _send_frame(self, payload: bytes) -> None:
        with self._lock:
            self._sock.sendall(struct.pack(">I", len(payload)) + payload)
            self.sent += 1

    def _recv_exact(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = self._sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("socket closed")
            buf += chunk
        return buf

    def _read_loop(self) -> None:
        try:
            while self._alive:
                (ln,) = struct.unpack(">I", self._recv_exact(4))
                name, body, cid = SCHEMA.unwrap(self._recv_exact(ln))
                if cid and cid in self._pending:
                    self._pending[cid].put((name, body))
                elif name == "ProtoHeartbeatEvent":
                    continue
                else:
                    self.events.put((name, body))
        except Exception as exc:  # noqa: BLE001 — reader death = disconnected; requests then fail closed
            self._alive = False
            for q in list(self._pending.values()):
                q.put(("__disconnect__", {"error": str(exc)}))

    def heartbeat_if_due(self) -> None:
        if self.connected and time.monotonic() - self._last_hb >= self.heartbeat_s:
            self._send_frame(SCHEMA.wrap("ProtoHeartbeatEvent", {}))
            self._last_hb = time.monotonic()

    def call(self, message: str, values: dict[str, Any], *, timeout_s: Optional[float] = None) -> tuple[str, dict[str, Any]]:
        """Send a request, wait for the response carrying the same clientMsgId. Errors come back as CtraderApiError."""
        self.connect()
        cid = uuid.uuid4().hex[:16]
        q: queue.Queue = queue.Queue()
        self._pending[cid] = q
        try:
            self._send_frame(SCHEMA.wrap(message, values, cid))
            try:
                name, body = q.get(timeout=timeout_s or self.timeout_s)
            except queue.Empty:
                raise CtraderError(f"cTrader timeout waiting for {message} response")
        except OSError as exc:
            self.close(); raise CtraderError(f"cTrader socket failure: {exc}") from exc
        finally:
            self._pending.pop(cid, None)
        if name == "__disconnect__":
            self.close(); raise CtraderError(f"cTrader disconnected: {body.get('error')}")
        if name in ("ProtoOAErrorRes", "ProtoErrorRes"):
            raise CtraderApiError(str(body.get("errorCode")), str(body.get("description", "")))
        if name == "ProtoOAExecutionEvent":
            self.events.put((name, body))   # the API answers order requests with an execution event: it is both the reply and an event
        return name, body

    def drain_events(self, max_items: int = 100) -> list[tuple[str, dict[str, Any]]]:
        out = []
        while len(out) < max_items:
            try:
                out.append(self.events.get_nowait())
            except queue.Empty:
                break
        return out

    def wait_event(self, predicate: Callable[[str, dict[str, Any]], bool], *, timeout_s: float) -> Optional[tuple[str, dict[str, Any]]]:
        deadline = time.monotonic() + timeout_s
        stash: list[tuple[str, dict[str, Any]]] = []
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                try:
                    item = self.events.get(timeout=remaining)
                except queue.Empty:
                    return None
                if predicate(*item):
                    return item
                stash.append(item)
        finally:
            for s in stash:
                self.events.put(s)
