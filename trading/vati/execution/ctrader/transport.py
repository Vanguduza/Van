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
from vati.execution.entry_deadline import EntryNotSent, require_entry_deadline
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
        self._state_lock = threading.RLock()
        self._pending: dict[str, queue.Queue] = {}
        self._pending_sockets: dict[str, Any] = {}
        self.events: queue.Queue = queue.Queue()
        self._reader: Optional[threading.Thread] = None
        self._alive = False
        self._connection_counter = 0
        self.sent = 0

    # ------------------------------------------------------------ lifecycle
    def connect(self) -> None:
        # One connection construction at a time. Reader I/O never holds this
        # lock, so shutdown can interrupt a blocked receive/send.
        with self._state_lock:
            if self._sock is not None:
                return
            raw = sock = None
            try:
                if self._connector is not None:
                    sock = self._connector(self.host, self.port)
                else:
                    raw = socket.create_connection((self.host, self.port), timeout=self.timeout_s)
                    ctx = ssl.create_default_context(); ctx.minimum_version = ssl.TLSVersion.TLSv1_2
                    sock = ctx.wrap_socket(raw, server_hostname=self.host)
                self._sock, self._alive = sock, True
                self._connection_counter += 1
                self._last_hb = time.monotonic()
                self._reader = threading.Thread(target=self._read_loop, args=(sock,), daemon=True)
                self._reader.start()
            except Exception as exc:
                self._sock, self._alive, self._reader = None, False, None
                if sock is not None:
                    sock.close()
                elif raw is not None:
                    raw.close()
                if isinstance(exc, (OSError, RuntimeError)):
                    raise CtraderError(f"cTrader connect failed: {exc}") from exc
                raise

    def close(self) -> None:
        with self._state_lock:
            sock = self._sock
        if sock is not None:
            self._retire(sock, "connection closed")

    def _retire(self, sock, error: str) -> None:
        """Retire only this socket; old failures cannot close a replacement.

        Disconnect is an unknown response/effect, never evidence that an order
        was refused or safe to replay. Callers retain the existing reconciliation
        contract. Wake pending calls before joining the original reader.
        """
        with self._state_lock:
            if self._sock is not sock:
                return
            self._sock, self._alive = None, False
            reader, self._reader = self._reader, None
            for cid, pending in self._pending.items():
                if self._pending_sockets.get(cid) is sock:
                    pending.put(("__disconnect__", {"error": error}))
        try:
            shutdown = getattr(sock, "shutdown", None)
            if shutdown is not None:
                shutdown(socket.SHUT_RDWR)
        except OSError:
            pass  # Already disconnected; close and reader reconciliation remain.
        finally:
            try:
                sock.close()
            except OSError:
                pass
            finally:
                if reader is not None and reader is not threading.current_thread():
                    reader.join(self.timeout_s)
                    if reader.is_alive():
                        raise CtraderError("cTrader reader did not terminate after socket shutdown")

    @property
    def connected(self) -> bool:
        with self._state_lock:
            return self._sock is not None and self._alive

    @property
    def connection_id(self) -> int | None:
        """Process-local lifetime identity, not account authority or provenance."""
        with self._state_lock:
            return self._connection_counter if self._sock is not None and self._alive else None

    # ------------------------------------------------------------ io
    def _send_frame(self, payload: bytes, *, expires_at_ms=None, clock=None, expected_socket=None) -> None:
        frame=struct.pack(">I", len(payload)) + payload
        with self._lock:
            if expires_at_ms is not None:
                require_entry_deadline(expires_at_ms, clock)
            with self._state_lock:
                sock = self._sock
                if sock is None or not self._alive or (expected_socket is not None and sock is not expected_socket):
                    raise CtraderError("cTrader connection changed before send")
            sock.sendall(frame)
            self.sent += 1

    def _recv_exact(self, sock, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("socket closed")
            buf += chunk
        return buf

    def _read_loop(self, sock) -> None:
        try:
            while True:
                with self._state_lock:
                    if self._sock is not sock:
                        return
                (ln,) = struct.unpack(">I", self._recv_exact(sock, 4))
                name, body, cid = SCHEMA.unwrap(self._recv_exact(sock, ln))
                with self._state_lock:
                    if self._sock is not sock:
                        return
                    if cid and self._pending_sockets.get(cid) is sock:
                        self._pending[cid].put((name, body))
                    elif name != "ProtoHeartbeatEvent":
                        self.events.put((sock, name, body))
        except Exception as exc:  # noqa: BLE001 — reader death = disconnected; requests then fail closed
            self._retire(sock, str(exc))

    def heartbeat_if_due(self) -> None:
        with self._state_lock:
            sock = self._sock
            due = self._alive and sock is not None and time.monotonic() - self._last_hb >= self.heartbeat_s
        if due:
            self._send_frame(SCHEMA.wrap("ProtoHeartbeatEvent", {}), expected_socket=sock)
            with self._state_lock:
                if self._sock is sock:
                    self._last_hb = time.monotonic()

    def call(self, message: str, values: dict[str, Any], *, timeout_s: Optional[float] = None) -> tuple[str, dict[str, Any]]:
        """Send a request, wait for the response carrying the same clientMsgId. Errors come back as CtraderApiError."""
        return self._request(message,values,timeout_s=timeout_s)

    def call_entry(self, message: str, values: dict[str, Any], *, expires_at_ms, clock, timeout_s=None):
        """A bounded new order. Auth/read/close requests use the ordinary path."""
        if message != 'ProtoOANewOrderReq':
            raise EntryNotSent('bounded entry operation differs; not sent')
        require_entry_deadline(expires_at_ms,clock)
        return self._request(message,values,timeout_s=timeout_s,expires_at_ms=expires_at_ms,clock=clock)

    def _request(self, message, values, *, timeout_s=None, expires_at_ms=None, clock=None):
        self.connect()
        cid = uuid.uuid4().hex[:16]
        q: queue.Queue = queue.Queue()
        with self._state_lock:
            sock = self._sock
            if sock is None or not self._alive:
                raise CtraderError("cTrader disconnected before request registration")
            self._pending[cid] = q
            self._pending_sockets[cid] = sock
        try:
            payload=SCHEMA.wrap(message, values, cid)
            if expires_at_ms is None:
                self._send_frame(payload, expected_socket=sock)
            else:
                self._send_frame(payload,expires_at_ms=expires_at_ms,clock=clock,expected_socket=sock)
            try:
                name, body = q.get(timeout=timeout_s or self.timeout_s)
            except queue.Empty:
                raise CtraderError(f"cTrader timeout waiting for {message} response")
        except OSError as exc:
            self._retire(sock, str(exc))
            raise CtraderError(f"cTrader socket failure: {exc}") from exc
        finally:
            with self._state_lock:
                if self._pending.get(cid) is q:
                    self._pending.pop(cid, None)
                    self._pending_sockets.pop(cid, None)
        if name == "__disconnect__":
            raise CtraderError(f"cTrader disconnected: {body.get('error')}")
        if name in ("ProtoOAErrorRes", "ProtoErrorRes"):
            raise CtraderApiError(str(body.get("errorCode")), str(body.get("description", "")))
        if name == "ProtoOAExecutionEvent":
            self.events.put((sock, name, body))   # A real original effect remains evidence even after disconnect.
        return name, body

    def _event_value(self, item):
        sock, name, body = item
        # Quotes/depth from a retired subscription cannot seed the replacement
        # connection's cache. Execution/error evidence remains for reconciliation.
        if name in {"ProtoOASpotEvent", "ProtoOADepthEvent"}:
            with self._state_lock:
                if self._sock is not sock:
                    return None
        return name, body

    def drain_events(self, max_items: int = 100) -> list[tuple[str, dict[str, Any]]]:
        out = []
        while len(out) < max_items:
            try:
                item = self._event_value(self.events.get_nowait())
                if item is not None:
                    out.append(item)
            except queue.Empty:
                break
        return out

    def wait_event(self, predicate: Callable[[str, dict[str, Any]], bool], *, timeout_s: float) -> Optional[tuple[str, dict[str, Any]]]:
        deadline = time.monotonic() + timeout_s
        stash = []
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                try:
                    original = self.events.get(timeout=remaining)
                except queue.Empty:
                    return None
                item = self._event_value(original)
                if item is None:
                    continue
                if predicate(*item):
                    return item
                stash.append(original)
        finally:
            for s in stash:
                self.events.put(s)
