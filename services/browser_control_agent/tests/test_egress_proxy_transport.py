"""Actual loopback proxy transport; controlled upstreams are not live web qualification."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import socket

import pytest

from services.browser_control_agent.egress_proxy import (
    ExactIpEgressProxy, PublicDestination,
)


@asynccontextmanager
async def local_upstream(handler):
    tasks = set()

    async def accepted(reader, writer):
        task = asyncio.current_task()
        tasks.add(task)
        try:
            await asyncio.wait_for(handler(reader, writer), 3)
        finally:
            writer.close()
            await writer.wait_closed()
            tasks.discard(task)

    server = await asyncio.start_server(accepted, "127.0.0.1", 0)
    try:
        yield server.sockets[0].getsockname()[1]
    finally:
        server.close()
        await server.wait_closed()
        pending = list(tasks)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)


@asynccontextmanager
async def local_proxy(resolver=None):
    # The production CLI refuses port zero. Pick a measured temporary loopback port;
    # these tests do not relax its constructor or its real socket/connect methods.
    with socket.socket() as selected:
        selected.bind(("127.0.0.1", 0))
        port = selected.getsockname()[1]
    proxy = ExactIpEgressProxy(port=port, resolver=resolver)
    address, observed_port = await proxy.start()
    assert (address, observed_port) == ("127.0.0.1", port)
    try:
        yield proxy, port
    finally:
        await proxy.close()


class ControlledUpstreamResolver:
    """A named local fixture mapping; production PublicResolver remains unchanged."""

    def __init__(self, port):
        self.port = port
        self.calls = []

    async def resolve(self, hostname, port):
        self.calls.append((hostname, port))
        return PublicDestination(hostname, self.port, ("127.0.0.1",))


@pytest.mark.asyncio
async def test_actual_proxy_http_socket_reaches_only_selected_upstream_and_strips_proxy_secrets():
    observed = []

    async def upstream(reader, writer):
        observed.append(await reader.readuntil(b"\r\n\r\n"))
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 7\r\nConnection: close\r\n\r\nfixture")
        await writer.drain()

    async with local_upstream(upstream) as destination:
        resolver = ControlledUpstreamResolver(destination)
        async with local_proxy(resolver) as (_, port):
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            try:
                writer.write(b"GET http://public.example/a?q=1 HTTP/1.1\r\nHost: public.example\r\n"
                             b"Proxy-Authorization: private-fixture-token\r\nProxy-Connection: keep-alive\r\n\r\n")
                await writer.drain()
                writer.write_eof()
                reply = await asyncio.wait_for(reader.read(), 3)
                assert reply.endswith(b"\r\n\r\nfixture")
            finally:
                writer.close()
                await writer.wait_closed()
    assert resolver.calls == [("public.example", 80)]
    assert len(observed) == 1
    assert observed[0].startswith(b"GET /a?q=1 HTTP/1.1\r\n")
    assert b"Host: public.example\r\n" in observed[0]
    assert b"private-fixture-token" not in observed[0]
    assert b"Proxy-Authorization" not in observed[0] and b"Proxy-Connection" not in observed[0]


@pytest.mark.asyncio
async def test_actual_proxy_connect_socket_relays_opaque_bytes_to_the_selected_upstream():
    payload = b"\x16\x03\x03\x00\x13opaque-fixture-only"
    observed = []

    async def upstream(reader, writer):
        observed.append(await reader.readexactly(len(payload)))
        writer.write(observed[-1])
        await writer.drain()

    async with local_upstream(upstream) as destination:
        resolver = ControlledUpstreamResolver(destination)
        async with local_proxy(resolver) as (_, port):
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            try:
                writer.write(b"CONNECT public.example:443 HTTP/1.1\r\nHost: public.example:443\r\n\r\n")
                await writer.drain()
                handshake = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 3)
                assert handshake == b"HTTP/1.1 200 Connection Established\r\n\r\n"
                writer.write(payload)
                await writer.drain()
                writer.write_eof()
                assert await asyncio.wait_for(reader.readexactly(len(payload)), 3) == payload
            finally:
                writer.close()
                await writer.wait_closed()
    assert resolver.calls == [("public.example", 443)]
    assert observed == [payload]


@pytest.mark.asyncio
@pytest.mark.parametrize("wire_request", [
    b"GET http://127.0.0.1/private HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n",
    b"CONNECT 10.0.0.9:443 HTTP/1.1\r\nHost: 10.0.0.9\r\n\r\n",
    b"CONNECT [::1]:443 HTTP/1.1\r\nHost: [::1]\r\n\r\n",
    b"CONNECT 224.0.0.1:443 HTTP/1.1\r\nHost: 224.0.0.1\r\n\r\n",
    b"CONNECT 239.255.255.250:443 HTTP/1.1\r\nHost: 239.255.255.250\r\n\r\n",
    b"CONNECT [ff02::1]:443 HTTP/1.1\r\nHost: [ff02::1]\r\n\r\n",
    b"CONNECT [fec0::1]:443 HTTP/1.1\r\nHost: [fec0::1]\r\n\r\n",
    b"CONNECT [::ffff:224.0.0.1]:443 HTTP/1.1\r\nHost: [::ffff:224.0.0.1]\r\n\r\n",
])
async def test_actual_proxy_refuses_non_public_literals_before_any_upstream_connection(wire_request, monkeypatch):
    # No resolver override: exercise production literal-address policy through a
    # real proxy client socket. A forbidden connect attempt fails the test.
    async with local_proxy() as (proxy, port):
        attempted = []

        async def forbidden_connect(destination):
            attempted.append(destination)
            raise AssertionError("private upstream connection was attempted")

        monkeypatch.setattr(proxy, "_connect_exact", forbidden_connect)
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        try:
            writer.write(wire_request)
            await writer.drain()
            writer.write_eof()
            reply = await asyncio.wait_for(reader.read(), 3)
            assert reply.startswith(b"HTTP/1.1 403 Forbidden\r\n")
            assert reply.endswith(b"EGRESS_NON_PUBLIC_ADDRESS")
            assert attempted == []
        finally:
            writer.close()
            await writer.wait_closed()


@pytest.mark.asyncio
@pytest.mark.parametrize("denied", ["10.0.0.9", "224.0.0.1", "ff02::1", "fec0::1", "::ffff:224.0.0.1"])
async def test_actual_proxy_refuses_mixed_public_and_non_public_dns_before_connect(denied, monkeypatch):
    loop = asyncio.get_running_loop()

    async def mixed_answers(host, port, **kwargs):
        assert host == "public.example" and port == 443
        family = socket.AF_INET6 if ":" in denied else socket.AF_INET
        blocked = (denied, port, 0, 0) if family == socket.AF_INET6 else (denied, port)
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("8.8.8.8", port)),
                (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", blocked)]

    async with local_proxy() as (proxy, port):
        attempted = []

        async def forbidden_connect(destination):
            attempted.append(destination)
            raise AssertionError("mixed DNS destination must be rejected before connect")

        monkeypatch.setattr(loop, "getaddrinfo", mixed_answers)
        monkeypatch.setattr(proxy, "_connect_exact", forbidden_connect)
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        try:
            writer.write(b"CONNECT public.example:443 HTTP/1.1\r\nHost: public.example\r\n\r\n")
            await writer.drain()
            writer.write_eof()
            reply = await asyncio.wait_for(reader.read(), 3)
            assert reply.startswith(b"HTTP/1.1 403 Forbidden\r\n")
            assert reply.endswith(b"EGRESS_NON_PUBLIC_ADDRESS")
            assert attempted == []
        finally:
            writer.close()
            await writer.wait_closed()
