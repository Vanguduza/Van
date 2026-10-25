"""Framed TLS transport for the cTrader Open API (demo.ctraderapi.com:5035 / live:5035).

Wire: 4-byte big-endian length + ProtoMessage. One socket, a reader thread, requests
matched by clientMsgId, unsolicited events (execution, spots, errors) queued for the
adapter, ProtoHeartbeatEvent every 10 s. Credentials (app client id/secret, account
access token) are held by the transport only; nothing here sizes or decides."""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import queue
import math
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
    def __init__(self, *, host: str = DEMO_HOST, port: int = PORT, timeout_s: float = 10.0, connector: Optional[Callable[[str, int], Any]] = None, heartbeat_s: float = 10.0, max_frame_bytes: int = 8*1024*1024) -> None:
        if type(max_frame_bytes) is not int or not 1 <= max_frame_bytes <= 64*1024*1024:
            raise ValueError("cTrader frame capacity must be an integer from1byte through64MiB")
        self.host, self.port, self.timeout_s, self.heartbeat_s = host, port, timeout_s, heartbeat_s
        self.max_frame_bytes = max_frame_bytes
        self._connector = connector
        self._sock = None
        self._lock = threading.Lock()
        self._state_lock = threading.RLock()
        self._pending: dict[str, queue.Queue] = {}
        self._pending_sockets: dict[str, Any] = {}
        self.events: queue.Queue = queue.Queue()
        self._reader: Optional[threading.Thread] = None
        self._readers: set[threading.Thread] = set()
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
            self._readers = {reader for reader in self._readers if reader.is_alive()}
            raw = sock = None
            try:
                if self._connector is not None:
                    sock = self._connector(self.host, self.port)
                else:
                    raw = socket.create_connection((self.host, self.port), timeout=self._io_timeout())
                    ctx = ssl.create_default_context(); ctx.minimum_version = ssl.TLSVersion.TLSv1_2
                    self._prepare_io(raw)
                    sock = ctx.wrap_socket(raw, server_hostname=self.host)
                if sock is None:
                    raise CtraderError("cTrader connector returned no socket")
                self._prepare_io(sock)
                self._sock, self._alive = sock, True
                self._connection_counter += 1
                self._last_hb = time.monotonic()
                self._reader = threading.Thread(target=self._read_loop, args=(sock,), daemon=True)
                self._readers.add(self._reader)
                self._reader.start()
            except Exception as exc:
                self._readers.discard(self._reader)
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
            readers = list(self._readers)
        if sock is not None:
            self._retire(sock, "connection closed")
        # A failed reader may already have detached itself while still releasing
        # its socket. Retain/join that exact owner; never join a later replacement.
        for reader in readers:
            self._join_reader(reader)

    def _join_reader(self, reader):
        if reader is threading.current_thread():
            return
        reader.join(self.timeout_s)
        if reader.is_alive():
            raise CtraderError("cTrader reader did not terminate after socket shutdown")
        with self._state_lock:
            self._readers.discard(reader)

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
        with self.events.not_empty:
            self.events.not_empty.notify_all()
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
                    self._join_reader(reader)

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
    def _io_timeout(self):
        return self.timeout_s

    def _prepare_io(self, sock):
        pass  # Financial transport retains its existing peer-timeout semantics.

    def _response_timeout(self, timeout_s):
        return timeout_s or self.timeout_s

    def _send_guard(self):
        return self._lock

    def _send_frame(self, payload: bytes, *, expires_at_ms=None, clock=None, expected_socket=None) -> None:
        frame=struct.pack(">I", len(payload)) + payload
        with self._send_guard():
            if expires_at_ms is not None:
                require_entry_deadline(expires_at_ms, clock)
            with self._state_lock:
                sock = self._sock
                if sock is None or not self._alive or (expected_socket is not None and sock is not expected_socket):
                    raise CtraderError("cTrader connection changed before send")
            self._prepare_io(sock)
            sock.sendall(frame)
            self.sent += 1

    def _recv_exact(self, sock, n: int) -> bytes:
        buf = bytearray()
        while len(buf) < n:
            self._prepare_io(sock)
            chunk = sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("socket closed")
            buf.extend(chunk)
        return bytes(buf)

    def _admit_frame_header(self, length: int) -> None:
        """Ordinary financial transport retains its existing per-frame policy."""

    def _read_loop(self, sock) -> None:
        try:
            while True:
                with self._state_lock:
                    if self._sock is not sock:
                        return
                (ln,) = struct.unpack(">I", self._recv_exact(sock, 4))
                if not 1 <= ln <= self.max_frame_bytes:
                    raise CtraderError("cTrader native frame length exceeds configured capacity")
                self._admit_frame_header(ln)
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
                name, body = q.get(timeout=self._response_timeout(timeout_s))
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

    def drain_events_kind(self, kind: str, max_items: int = 100) -> list[tuple[str, dict[str, Any]]]:
        """Consume this native event kind while preserving all other deliveries.

        No caller predicate or transport-state lock runs under the queue mutex;
        the reader publishes in the opposite state/queue order. Existing queue
        capacity and full tick-history qualification remain separate obligations.
        """
        if not isinstance(kind,str) or type(max_items) is not int or max_items<1:
            raise ValueError('native event kind and positive bound required')
        with self._state_lock:
            sock=self._sock
        output=[];remove=[]
        with self.events.mutex:
            for index,original in enumerate(self.events.queue):
                source,name,body=original
                if name!=kind:continue
                remove.append(index)
                if name not in {'ProtoOASpotEvent','ProtoOADepthEvent'} or source is sock:
                    output.append((name,body))
                if len(remove)>=max_items:break
            for index in reversed(remove):del self.events.queue[index]
            if remove:self.events.not_full.notify_all()
        return output

    def has_events_kind(self,kind: str) -> bool:
        with self.events.mutex:
            return any(original[1]==kind for original in self.events.queue)

    def wait_event(self, predicate: Callable[[str, dict[str, Any]], bool], *, timeout_s: float) -> Optional[tuple[str, dict[str, Any]]]:
        """Claim one match without hiding, reordering or mutating other evidence.

        Predicates receive a copy outside queue/state locks. An exception or
        elapsed timeout leaves the original delivery queued. Competing selectors
        must claim the same original by identity; only one can receive it.
        Arbitrary callback execution is not an interruptible host sandbox.
        """
        if (not callable(predicate) or type(timeout_s) not in (int,float)
                or not math.isfinite(timeout_s) or timeout_s<0):
            raise ValueError('native event selector and finite nonnegative timeout required')
        deadline = time.monotonic() + timeout_s
        examined = {}

        def claim(original):
            with self.events.mutex:
                for index,candidate in enumerate(self.events.queue):
                    if candidate is original:
                        del self.events.queue[index]
                        self.events.not_full.notify_all()
                        return True
            return False

        while time.monotonic()<deadline:
            with self.events.mutex:
                snapshot=list(self.events.queue)
            # Retain references only to entries still in this snapshot, avoiding
            # object-ID reuse and accumulation of already-consumed deliveries.
            examined={id(original):original for original in snapshot if id(original) in examined}
            for original in snapshot:
                if time.monotonic()>=deadline:return None
                if id(original) in examined:continue
                examined[id(original)]=original
                item=self._event_value(original)
                if item is None:
                    claim(original)  # Only retired market data, never financial evidence.
                    continue
                name,body=item
                matches=predicate(name,deepcopy(body))
                if time.monotonic()>=deadline:return None
                if matches and claim(original):
                    # The connection can retire while a callback runs. Such a
                    # quote cannot seed its replacement; financial evidence stays valid.
                    current=self._event_value(original)
                    if current is not None:return current[0],deepcopy(current[1])
            with self.events.not_empty:
                if any(id(original) not in examined for original in self.events.queue):
                    continue  # A delivery arrived after the unlocked snapshot.
                remaining=deadline-time.monotonic()
                if remaining<=0:return None
                self.events.not_empty.wait(remaining)
        return None


class CtraderReadTransport(CtraderTransport):
    """One native market-read operation; its budget cannot authorize an order.

    Socket and response waits share a monotonic deadline. External DNS resolver
    or custom connector code is not an interruptible OS sandbox: expiry is also
    rechecked on return. A separately governed worker must bound that host work.
    """
    READ_MESSAGES = frozenset({"ProtoOAApplicationAuthReq", "ProtoOAAccountAuthReq",
                              "ProtoOASymbolsListReq", "ProtoOASymbolByIdReq",
                              "ProtoOAGetTrendbarsReq", "ProtoOASubscribeSpotsReq",
                              "ProtoOAUnsubscribeSpotsReq", "ProtoHeartbeatEvent"})

    def __init__(self, *, operation_timeout_s=30.0, monotonic=None,
                 max_read_frames=4096, max_read_bytes=16*1024*1024, **kwargs):
        if (type(operation_timeout_s) not in (int, float) or not math.isfinite(operation_timeout_s)
                or not 0 < operation_timeout_s <= 300):
            raise ValueError("native read budget must be finite and positive, at most300seconds")
        if type(max_read_frames) is not int or not 1<=max_read_frames<=65536:
            raise ValueError('native read frame capacity must be an integer from1through65536')
        if type(max_read_bytes) is not int or not 1<=max_read_bytes<=256*1024*1024:
            raise ValueError('native read encoded capacity must be an integer from1byte through256MiB')
        super().__init__(**kwargs)
        if (type(self.timeout_s) not in (int, float) or not math.isfinite(self.timeout_s) or self.timeout_s <= 0):
            raise ValueError("native read peer timeout must be finite and positive")
        self.operation_timeout_s = operation_timeout_s
        self._budget_clock = monotonic if monotonic is not None else time.monotonic
        if not callable(self._budget_clock):
            raise ValueError("native read monotonic clock required")
        self._operation_deadline = None
        self._last_budget_clock = None
        self.max_read_frames,self.max_read_bytes=max_read_frames,max_read_bytes
        self._admitted_frame_headers=self._reserved_encoded_bytes=0
        self._refused_frame_length=None

    def _admit_frame_header(self,length):
        # Charge before reading/decoding the body, including heartbeats and RPC
        # replies. Drain, close and reconnect cannot refund this operation.
        with self._state_lock:
            if (self._refused_frame_length is not None
                    or self._admitted_frame_headers>=self.max_read_frames
                    or length>self.max_read_bytes-self._reserved_encoded_bytes):
                if self._refused_frame_length is None:self._refused_frame_length=length
                raise CtraderError('native read cumulative frame/encoded-byte capacity exhausted')
            self._admitted_frame_headers+=1
            self._reserved_encoded_bytes+=length

    def read_capacity_snapshot(self):
        with self._state_lock:
            return {'schema':'vati.ctrader-read-capacity/1',
                    'state':'EXHAUSTED' if self._refused_frame_length is not None else 'WITHIN_LIMIT',
                    'max_read_frames':self.max_read_frames,'max_read_bytes':self.max_read_bytes,
                    'admitted_frame_headers':self._admitted_frame_headers,
                    'reserved_encoded_bytes':self._reserved_encoded_bytes,
                    'refused_frame_length':self._refused_frame_length,
                    'accounting_basis':'ADMITTED_PROTOBUF_LENGTH_EXCLUDING_PREFIX_NOT_DECODED_DELIVERY_OR_PROCESS_MEMORY',
                    'provider_qualified':False,'authority_effect':'NONE'}

    def _io_timeout(self):
        with self._state_lock:
            if self._refused_frame_length is not None:
                raise CtraderError('native read cumulative frame/encoded-byte capacity exhausted')
            try:
                now = self._budget_clock()
            except Exception as exc:
                raise CtraderError("native read monotonic clock unavailable") from exc
            if type(now) not in (int, float) or not math.isfinite(now):
                raise CtraderError("native read monotonic clock unavailable")
            if self._last_budget_clock is not None and now < self._last_budget_clock:
                raise CtraderError("native read budget clock moved backwards")
            self._last_budget_clock = now
            if self._operation_deadline is None:
                self._operation_deadline = now+self.operation_timeout_s
            remaining = self._operation_deadline-now
            if remaining <= 0:
                raise CtraderError("native read operation budget exhausted")
            return min(self.timeout_s, remaining)

    def _prepare_io(self, sock):
        remaining = self._io_timeout()
        setter = getattr(sock, "settimeout", None)
        if not callable(setter):
            raise CtraderError("native read budget requires socket timeout support")
        setter(remaining)

    def _response_timeout(self, timeout_s):
        return min(super()._response_timeout(timeout_s), self._io_timeout())

    @contextmanager
    def _send_guard(self):
        if not self._lock.acquire(timeout=self._io_timeout()):
            raise CtraderError("native read send lock unavailable within budget")
        try:
            yield
        finally:
            self._lock.release()

    def check_budget(self):
        self._io_timeout()

    def connect(self):
        try:
            self.check_budget()  # Includes elapsed connector work, even before auth.
            return super().connect()
        except CtraderError:
            self.close()
            raise

    def call(self, message, values, *, timeout_s=None):
        if not isinstance(message, str) or message not in self.READ_MESSAGES:
            raise CtraderError("read-only native source transport refuses this operation")
        if timeout_s is not None and (type(timeout_s) not in (int, float)
                or not math.isfinite(timeout_s) or timeout_s <= 0):
            raise ValueError("native read response timeout must be finite and positive")
        try:
            self._io_timeout()  # Starts once; reconnect/later calls cannot reset it.
            result = super().call(message, values, timeout_s=timeout_s)
            self.check_budget()
            return result
        except CtraderError:
            self.close()
            raise

    def call_entry(self, *args, **kwargs):
        raise EntryNotSent("read-only native source cannot submit an order; not sent")

    def wait_event(self,predicate,*,timeout_s):
        if type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or timeout_s<=0:
            raise ValueError('native read event timeout must be finite and positive')
        try:
            result=super().wait_event(predicate,timeout_s=min(timeout_s,self._io_timeout()))
            self.check_budget()
            return result
        except CtraderError:
            self.close()
            raise

    def wait_for_event_kind(self,kind: str,*,timeout_s=None):
        """Wait for source data without consuming a financial/other delivery."""
        if not isinstance(kind,str) or (timeout_s is not None and
                (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or timeout_s<=0)):
            raise ValueError('native read event kind/timeout invalid')
        try:
            wait=min(timeout_s,self._io_timeout()) if timeout_s is not None else self._io_timeout()
            deadline=time.monotonic()+wait
            while True:
                self.check_budget()
                with self._state_lock:
                    sock=self._sock
                if sock is None:return False
                with self.events.not_empty:
                    if any(item[0] is sock and item[1]==kind for item in self.events.queue):return True
                    remaining=deadline-time.monotonic()
                    if remaining<=0:
                        break
                    self.events.not_empty.wait(remaining)
            self.check_budget()
            return False
        except CtraderError:
            self.close()
            raise
