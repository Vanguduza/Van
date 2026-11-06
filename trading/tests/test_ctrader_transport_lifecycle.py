"""Connection lifetime boundaries using owned sockets and joined test workers."""
from __future__ import annotations

import queue
import socket
import ssl
import struct
import threading

import pytest

from vati.execution.ctrader import CtraderError, CtraderTransport, SCHEMA
from vati.execution.ctrader import transport as transport_module


class Harness:
    def __init__(self):
        self.sockets = []
        self.transports = []
        self.threads = []
        self.release = []

    def pair(self):
        pair = socket.socketpair()
        self.sockets.extend(pair)
        return pair

    def transport(self, connector):
        transport = CtraderTransport(connector=connector, timeout_s=2)
        self.transports.append(transport)
        return transport

    def worker(self, operation):
        result = queue.Queue()
        def run():
            try:
                result.put(operation())
            except Exception as exc:
                result.put(exc)
        thread = threading.Thread(target=run)
        self.threads.append(thread)
        thread.start()
        return thread, result

    def cleanup(self):
        for event in self.release:
            event.set()
        for sock in self.sockets:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()
        readers = [thread for thread in threading.enumerate()
                   if getattr(getattr(thread, "_target", None), "__self__", None) in self.transports]
        for transport in self.transports:
            transport.close()
        for thread in self.threads + readers:
            thread.join(3)
            assert not thread.is_alive(), "owned native fixture worker did not terminate"


@pytest.fixture
def harness():
    owned = Harness()
    try:
        yield owned
    finally:
        owned.cleanup()


def receive_frame(sock):
    def exact(size):
        value = b""
        while len(value) < size:
            chunk = sock.recv(size - len(value))
            assert chunk, "fixture peer closed before request"
            value += chunk
        return value
    sock.settimeout(2)
    length, = struct.unpack(">I", exact(4))
    return SCHEMA.unwrap(exact(length))


def test_close_shuts_down_and_joins_a_blocked_reader(harness):
    client, _ = harness.pair()
    transport = harness.transport(lambda *_: client)
    transport.connect()
    reader = transport._reader
    transport.close()
    assert not reader.is_alive(), "close returned with its socket reader still blocked"
    assert client.fileno() == -1 and not transport.connected
    transport.close()  # repeated owner cleanup remains safe


def test_close_wakes_an_original_pending_request_without_waiting_for_timeout(harness):
    client, server = harness.pair()
    transport = harness.transport(lambda *_: client)
    worker, result = harness.worker(lambda: transport.call("ProtoOATraderReq", {"ctidTraderAccountId": 12345}))
    assert receive_frame(server)[0] == "ProtoOATraderReq"
    transport.close()
    worker.join(.5)
    assert not worker.is_alive(), "closed native request waited for its original response timeout"
    assert isinstance(result.get_nowait(), CtraderError)
    assert transport._pending == {}


def test_peer_disconnect_retires_and_closes_the_original_socket(harness):
    client, server = harness.pair()
    transport = harness.transport(lambda *_: client)
    transport.connect()
    reader = transport._reader
    server.shutdown(socket.SHUT_RDWR)
    server.close()
    reader.join(1)
    assert not reader.is_alive() and not transport.connected
    assert client.fileno() == -1, "reader failure retained an open disconnected socket"
    assert transport._sock is None


def test_concurrent_connects_create_one_socket_and_one_reader(harness):
    entered, release, duplicate = threading.Event(), threading.Event(), threading.Event()
    harness.release.append(release)
    calls = []
    def connector(*_):
        calls.append(None)
        if len(calls) > 1:
            duplicate.set()
        entered.set()
        assert release.wait(2)
        return harness.pair()[0]
    transport = harness.transport(connector)
    first, first_result = harness.worker(transport.connect)
    assert entered.wait(1)
    second, second_result = harness.worker(transport.connect)
    duplicated = duplicate.wait(.15)
    release.set()
    first.join(1); second.join(1)
    assert first_result.get_nowait() is None and second_result.get_nowait() is None
    assert not duplicated, "concurrent connect opened another native connection"
    assert len(calls) == 1 and transport.connected


class DelayedSocket:
    def __init__(self, sock, *, read=False, write=False):
        self.sock, self.read, self.write = sock, read, write
        self.entered, self.release, self.closed = threading.Event(), threading.Event(), threading.Event()

    def recv(self, size):
        if self.read:
            self.entered.set()
            assert self.release.wait(3)
            raise OSError("original reader failed after replacement connected")
        return self.sock.recv(size)

    def sendall(self, value):
        if self.write:
            self.entered.set()
            assert self.release.wait(3)
            raise OSError("original send failed after replacement connected")
        return self.sock.sendall(value)

    def shutdown(self, how):
        self.sock.shutdown(how)

    def close(self):
        self.sock.close()
        self.closed.set()


def test_old_reader_failure_cannot_disconnect_a_replacement_connection(harness):
    original = DelayedSocket(harness.pair()[0], read=True)
    replacement = harness.pair()[0]
    harness.release.append(original.release)
    sockets = iter([original, replacement])
    transport = harness.transport(lambda *_: next(sockets))
    transport.connect()
    reader = transport._reader
    assert original.entered.wait(1)
    closer, close_result = harness.worker(transport.close)
    assert original.closed.wait(1)
    closer.join(.1)
    assert closer.is_alive(), "close returned before its original reader terminated"
    transport.connect()
    original.release.set()
    reader.join(1); closer.join(1)
    assert close_result.get_nowait() is None
    assert transport.connected and transport._sock is replacement, "retired reader poisoned the new connection"


def test_old_request_failure_cannot_close_a_replacement_socket(harness):
    original = DelayedSocket(harness.pair()[0], write=True)
    replacement = harness.pair()[0]
    harness.release.append(original.release)
    sockets = iter([original, replacement])
    transport = harness.transport(lambda *_: next(sockets))
    caller, result = harness.worker(lambda: transport.call("ProtoOATraderReq", {"ctidTraderAccountId": 12345}))
    assert original.entered.wait(1)
    transport.close()
    transport.connect()
    original.release.set()
    caller.join(1)
    assert isinstance(result.get_nowait(), CtraderError)
    assert transport.connected and replacement.fileno() >= 0, "old request closed the new native connection"


def test_tls_failure_closes_the_raw_socket_before_reporting_unavailable(harness, monkeypatch):
    raw, _ = harness.pair()
    class FailedTLS:
        def wrap_socket(self, *_args, **_kwargs):
            raise ssl.SSLError("fixture TLS refusal")
    monkeypatch.setattr(transport_module.socket, "create_connection", lambda *_args, **_kwargs: raw)
    monkeypatch.setattr(transport_module.ssl, "create_default_context", FailedTLS)
    transport = CtraderTransport()
    harness.transports.append(transport)
    with pytest.raises(CtraderError, match="connect failed"):
        transport.connect()
    assert raw.fileno() == -1, "TLS failure leaked the original TCP socket"
    assert not transport.connected and transport._reader is None


def test_response_correlation_and_unsolicited_events_survive_cleanup(harness):
    client, server = harness.pair()
    transport = harness.transport(lambda *_: client)
    caller, result = harness.worker(lambda: transport.call("ProtoOATraderReq", {"ctidTraderAccountId": 12345}))
    _, _, cid = receive_frame(server)
    for name, values, request_id in [
        ("ProtoHeartbeatEvent", {}, None),
        ("ProtoOASpotEvent", {"ctidTraderAccountId": 12345, "symbolId": 1, "bid": 110000}, None),
        ("ProtoOATraderRes", {"ctidTraderAccountId": 12345, "trader": {"ctidTraderAccountId": 12345, "balance": 100, "depositAssetId": 1}}, cid),
    ]:
        payload = SCHEMA.wrap(name, values, request_id)
        server.sendall(struct.pack(">I", len(payload)) + payload)
    caller.join(1)
    response = result.get_nowait()
    assert response[0] == "ProtoOATraderRes" and response[1]["ctidTraderAccountId"] == 12345
    assert [name for name, _ in transport.drain_events()] == ["ProtoOASpotEvent"]
    transport.close()
    assert transport._pending == {}


def test_failed_reader_thread_start_closes_the_socket_and_leaves_no_active_connection(harness, monkeypatch):
    client, _ = harness.pair()
    transport = harness.transport(lambda *_: client)
    def cannot_start(_thread):
        raise RuntimeError("fixture process/thread quota unavailable")
    monkeypatch.setattr(threading.Thread, 'start', cannot_start)
    with pytest.raises(CtraderError, match="connect failed"):
        transport.connect()
    assert client.fileno() == -1 and not transport.connected
    assert transport._reader is None and transport.connection_id is None


def test_reconnect_discards_old_quotes_and_keeps_original_execution_evidence(harness):
    client, server = harness.pair()
    replacement, _ = harness.pair()
    sockets = iter([client, replacement])
    transport = harness.transport(lambda *_: next(sockets))
    transport.connect()
    first_id = transport.connection_id
    for name, values in [
        ('ProtoOASpotEvent', {'ctidTraderAccountId': 12345, 'symbolId': 1, 'bid': 110000}),
        ('ProtoOAExecutionEvent', {'ctidTraderAccountId': 12345, 'executionType': 'ORDER_ACCEPTED'}),
    ]:
        payload = SCHEMA.wrap(name, values)
        server.sendall(struct.pack('>I', len(payload)) + payload)
    # Consume the original execution through the public matcher, which stashes
    # the preceding quote. Its original connection identity must survive stashing.
    result = transport.wait_event(lambda name, _: name == 'ProtoOAExecutionEvent', timeout_s=1)
    assert result[1]['executionType'] == 'ORDER_ACCEPTED'
    # A second execution remains queued across reconnect for reconciliation.
    payload = SCHEMA.wrap('ProtoOAExecutionEvent', {'ctidTraderAccountId': 12345, 'executionType': 'ORDER_FILLED'})
    server.sendall(struct.pack('>I', len(payload)) + payload)
    # A correlated response is the barrier proving the preceding event arrived.
    caller, response = harness.worker(lambda: transport.call('ProtoHeartbeatEvent', {}))
    _, _, cid = receive_frame(server)
    payload = SCHEMA.wrap('ProtoHeartbeatEvent', {}, cid)
    server.sendall(struct.pack('>I', len(payload)) + payload)
    caller.join(1)
    assert response.get_nowait()[0] == 'ProtoHeartbeatEvent'
    transport.close()
    transport.connect()
    assert transport.connection_id > first_id
    assert transport.drain_events() == [('ProtoOAExecutionEvent', {'payloadType': 'PROTO_OA_EXECUTION_EVENT', 'ctidTraderAccountId': 12345, 'executionType': 'ORDER_FILLED'})]
