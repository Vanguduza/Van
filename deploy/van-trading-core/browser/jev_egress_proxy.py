#!/usr/bin/env python3
"""Loopback-only CONNECT proxy for the Jev TypeSafe decision service.

This service deliberately supports one authority only: api.typesafe.ai:443.
It does not forward HTTP, accept arbitrary CONNECT targets, or read VAN secrets.
TLS remains end-to-end between Jev/httpx and TypeSafe, so certificate validation
still happens in the Jev client.
"""
from __future__ import annotations

import ipaddress
import os
import selectors
import socket
import socketserver

BIND = os.getenv("VAN_JEV_PROXY_BIND", "127.0.0.1")
PORT = int(os.getenv("VAN_JEV_PROXY_PORT", "9143"))
UPSTREAM_HOST = "api.typesafe.ai"
UPSTREAM_PORT = 443
MAX_HEADER = 16 * 1024

if BIND not in {"127.0.0.1", "::1", "localhost"}:
    raise SystemExit("Jev egress proxy refuses a non-loopback bind")


def _connect_upstream() -> socket.socket:
    last: OSError | None = None
    for family, socktype, proto, _canon, sockaddr in socket.getaddrinfo(
        UPSTREAM_HOST, UPSTREAM_PORT, type=socket.SOCK_STREAM
    ):
        try:
            addr = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            continue
        if not addr.is_global:
            continue
        s = socket.socket(family, socktype, proto)
        s.settimeout(10)
        try:
            s.connect(sockaddr)
            s.settimeout(None)
            return s
        except OSError as exc:
            last = exc
            s.close()
    raise OSError(f"no valid global address for {UPSTREAM_HOST}") from last


def _relay(left: socket.socket, right: socket.socket) -> None:
    selector = selectors.DefaultSelector()
    selector.register(left, selectors.EVENT_READ, right)
    selector.register(right, selectors.EVENT_READ, left)
    try:
        while True:
            events = selector.select(timeout=120)
            if not events:
                return
            for key, _mask in events:
                src: socket.socket = key.fileobj
                dst: socket.socket = key.data
                data = src.recv(64 * 1024)
                if not data:
                    return
                dst.sendall(data)
    finally:
        selector.close()


class Handler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        client: socket.socket = self.request
        client.settimeout(5)
        buf = bytearray()
        while b"\r\n\r\n" not in buf:
            chunk = client.recv(4096)
            if not chunk:
                return
            buf.extend(chunk)
            if len(buf) > MAX_HEADER:
                client.sendall(b"HTTP/1.1 431 Request Header Fields Too Large\r\n\r\n")
                return

        header, remainder = bytes(buf).split(b"\r\n\r\n", 1)
        try:
            first = header.split(b"\r\n", 1)[0].decode("ascii")
            method, authority, version = first.split(" ", 2)
        except (UnicodeDecodeError, ValueError):
            client.sendall(b"HTTP/1.1 400 Bad Request\r\n\r\n")
            return

        if (
            method != "CONNECT"
            or authority.lower() != f"{UPSTREAM_HOST}:{UPSTREAM_PORT}"
            or version not in {"HTTP/1.0", "HTTP/1.1"}
        ):
            client.sendall(b"HTTP/1.1 403 Forbidden\r\n\r\n")
            return

        try:
            upstream = _connect_upstream()
        except OSError:
            client.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            return

        try:
            client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            if remainder:
                upstream.sendall(remainder)
            client.settimeout(None)
            _relay(client, upstream)
        finally:
            upstream.close()


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 16


if __name__ == "__main__":
    with Server((BIND, PORT), Handler) as server:
        server.serve_forever(poll_interval=0.25)
