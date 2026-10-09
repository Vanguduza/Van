"""OMV-008 — exact-IP public-web egress proxy for the Browser Stream Host.

Design adapted from CopilotKit/openmuse
@34b15bc80340e582fb8c25573646cfb0bbc5184d, apps/worker/* (MIT).

Why a proxy, rather than only validating Page.navigate:
Chromium performs its own subresource requests and DNS lookups. Validating the top-level
URL alone leaves redirects, images, scripts and DNS rebinding outside the policy boundary.
This loopback proxy resolves a destination once, rejects the whole hostname if *any*
answer is non-public, then opens the socket to the exact admitted IP. Chromium therefore
never performs the second destination DNS lookup for proxied HTTP(S).

This is application-level egress mediation, not a kernel firewall or browser sandbox. The
deployment must still run Chromium unprivileged, configure this proxy with no implicit
loopback bypass, block QUIC/non-proxied WebRTC egress and apply host/container firewall
policy. Those host facts remain live qualification evidence.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import ipaddress
import socket
from typing import Iterable
from urllib.parse import urlsplit

MAX_HEADER_BYTES = 64 * 1024
HEADER_TIMEOUT_SECONDS = 10.0
CONNECT_TIMEOUT_SECONDS = 10.0
IDLE_TIMEOUT_SECONDS = 300.0


class EgressRefused(ValueError):
    def __init__(self, code: str, detail: str | None = None) -> None:
        super().__init__(code if detail is None else f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class PublicDestination:
    hostname: str
    port: int
    addresses: tuple[str, ...]


def _public_address(raw: str) -> str:
    try:
        address = ipaddress.ip_address(raw)
    except ValueError as exc:
        raise EgressRefused("EGRESS_IP_INVALID", raw) from exc
    # is_global alone admits multicast and deprecated IPv6 site-local addresses.
    # Classify an IPv4-mapped IPv6 destination by its actual IPv4 destination;
    # the outer IPv6 object's is_multicast flag does not describe the mapped IP.
    mapped = address.ipv4_mapped if isinstance(address, ipaddress.IPv6Address) else None
    policy_address = mapped if mapped is not None else address
    if (not policy_address.is_global or policy_address.is_multicast
            or (isinstance(policy_address, ipaddress.IPv6Address) and policy_address.is_site_local)):
        raise EgressRefused("EGRESS_NON_PUBLIC_ADDRESS", str(address))
    return str(address)


def _host_ascii(hostname: str) -> str:
    value = hostname.rstrip(".").strip()
    if not value:
        raise EgressRefused("EGRESS_HOST_REQUIRED")
    try:
        encoded = value.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise EgressRefused("EGRESS_HOST_INVALID") from exc
    if encoded == "localhost" or encoded.endswith(".localhost"):
        raise EgressRefused("EGRESS_LOCALHOST_REFUSED")
    return encoded


def validate_public_url_syntax(url: str) -> tuple[str, str, int]:
    """Validate what can be known before DNS.

    DNS-address admission occurs in :class:`PublicResolver`. Literal IPs can be rejected
    immediately and therefore never reach Chromium even if the deployment proxy is absent.
    """
    if len(url) > 8192:
        raise EgressRefused("EGRESS_URL_TOO_LONG")
    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise EgressRefused("EGRESS_URL_INVALID") from exc
    if parsed.scheme not in {"http", "https"}:
        raise EgressRefused("EGRESS_SCHEME_REFUSED")
    if parsed.username is not None or parsed.password is not None:
        raise EgressRefused("EGRESS_URL_CREDENTIALS_REFUSED")
    if not parsed.hostname:
        raise EgressRefused("EGRESS_HOST_REQUIRED")
    hostname = _host_ascii(parsed.hostname)
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise EgressRefused("EGRESS_PORT_INVALID") from exc
    expected = 443 if parsed.scheme == "https" else 80
    if port != expected:
        raise EgressRefused("EGRESS_PORT_REFUSED", str(port))
    try:
        _public_address(hostname)
    except EgressRefused as exc:
        # A DNS name is not an IP and proceeds to the resolver. A literal IP must already
        # satisfy the public-address rule.
        try:
            ipaddress.ip_address(hostname)
        except ValueError:
            pass
        else:
            raise exc
    return parsed.scheme, hostname, port


class PublicResolver:
    """Resolve once and bind admission to the exact returned addresses."""

    async def resolve(self, hostname: str, port: int) -> PublicDestination:
        host = _host_ascii(hostname)
        try:
            literal = ipaddress.ip_address(host)
        except ValueError:
            literal = None
        if literal is not None:
            return PublicDestination(host, port, (_public_address(str(literal)),))

        loop = asyncio.get_running_loop()
        try:
            records = await loop.getaddrinfo(
                host,
                port,
                family=socket.AF_UNSPEC,
                type=socket.SOCK_STREAM,
                proto=socket.IPPROTO_TCP,
            )
        except socket.gaierror as exc:
            raise EgressRefused("EGRESS_DNS_UNAVAILABLE", host) from exc
        addresses: list[str] = []
        for _family, _type, _proto, _canonname, sockaddr in records:
            raw = str(sockaddr[0])
            admitted = _public_address(raw)
            if admitted not in addresses:
                addresses.append(admitted)
        if not addresses:
            raise EgressRefused("EGRESS_DNS_EMPTY", host)
        # Crucially, _public_address is evaluated for every answer before this tuple is
        # returned. A hostname with one public and one private answer is rejected, not
        # "rescued" by choosing the public address.
        return PublicDestination(host, port, tuple(addresses))


async def _read_headers(reader: asyncio.StreamReader) -> bytes:
    try:
        data = await asyncio.wait_for(
            reader.readuntil(b"\r\n\r\n"), timeout=HEADER_TIMEOUT_SECONDS
        )
    except asyncio.LimitOverrunError as exc:
        raise EgressRefused("EGRESS_HEADER_TOO_LARGE") from exc
    except asyncio.IncompleteReadError as exc:
        raise EgressRefused("EGRESS_HEADER_INCOMPLETE") from exc
    except asyncio.TimeoutError as exc:
        raise EgressRefused("EGRESS_HEADER_TIMEOUT") from exc
    if len(data) > MAX_HEADER_BYTES:
        raise EgressRefused("EGRESS_HEADER_TOO_LARGE")
    return data


def _parse_connect_target(raw: str) -> tuple[str, int]:
    value = raw.strip()
    if value.startswith("["):
        end = value.find("]")
        if end < 0 or end + 1 >= len(value) or value[end + 1] != ":":
            raise EgressRefused("EGRESS_CONNECT_TARGET_INVALID")
        host, port_raw = value[1:end], value[end + 2 :]
    else:
        if ":" not in value:
            raise EgressRefused("EGRESS_CONNECT_TARGET_INVALID")
        host, port_raw = value.rsplit(":", 1)
    try:
        port = int(port_raw)
    except ValueError as exc:
        raise EgressRefused("EGRESS_PORT_INVALID") from exc
    if port != 443:
        raise EgressRefused("EGRESS_PORT_REFUSED", str(port))
    return _host_ascii(host), port


def _http_request_for_origin(header: bytes) -> tuple[str, int, bytes]:
    try:
        text = header.decode("iso-8859-1")
    except UnicodeDecodeError as exc:
        raise EgressRefused("EGRESS_HEADER_INVALID") from exc
    lines = text.split("\r\n")
    parts = lines[0].split(" ")
    if len(parts) != 3:
        raise EgressRefused("EGRESS_REQUEST_LINE_INVALID")
    method, target, version = parts
    if method.upper() == "CONNECT":
        raise EgressRefused("EGRESS_INTERNAL_PARSE_ERROR")
    scheme, host, port = validate_public_url_syntax(target)
    if scheme != "http":
        # HTTPS proxying must use CONNECT. Accepting an absolute https URI here would make
        # this process a TLS terminator, which it deliberately is not.
        raise EgressRefused("EGRESS_HTTPS_REQUIRES_CONNECT")
    parsed = urlsplit(target)
    origin_target = parsed.path or "/"
    if parsed.query:
        origin_target += "?" + parsed.query

    forwarded = [f"{method} {origin_target} {version}"]
    saw_host = False
    for line in lines[1:]:
        if not line:
            continue
        if ":" not in line:
            raise EgressRefused("EGRESS_HEADER_INVALID")
        name, value = line.split(":", 1)
        lower = name.strip().lower()
        if lower in {"proxy-connection", "proxy-authorization"}:
            continue
        if lower == "host":
            saw_host = True
        forwarded.append(f"{name}:{value}")
    if not saw_host:
        forwarded.append(f"Host: {host}")
    return host, port, ("\r\n".join(forwarded) + "\r\n\r\n").encode("iso-8859-1")


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while True:
            chunk = await asyncio.wait_for(reader.read(64 * 1024), timeout=IDLE_TIMEOUT_SECONDS)
            if not chunk:
                return
            writer.write(chunk)
            await writer.drain()
    except (asyncio.TimeoutError, ConnectionError, OSError):
        return
    finally:
        try:
            writer.write_eof()
        except (AttributeError, OSError, RuntimeError):
            pass


class ExactIpEgressProxy:
    """Loopback HTTP(S) forward proxy with exact-IP destination binding."""

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 8899,
        resolver: PublicResolver | None = None,
    ) -> None:
        try:
            bind = ipaddress.ip_address(host)
        except ValueError as exc:
            raise EgressRefused("EGRESS_PROXY_BIND_MUST_BE_LOOPBACK_LITERAL") from exc
        if not bind.is_loopback:
            raise EgressRefused("EGRESS_PROXY_BIND_NOT_LOOPBACK")
        if port < 1 or port > 65535:
            raise EgressRefused("EGRESS_PROXY_PORT_INVALID")
        self.host = str(bind)
        self.port = port
        self.resolver = resolver or PublicResolver()
        self._server: asyncio.AbstractServer | None = None

    async def start(self) -> tuple[str, int]:
        self._server = await asyncio.start_server(
            self._handle, self.host, self.port, limit=MAX_HEADER_BYTES + 1
        )
        sock = self._server.sockets[0]
        bound = sock.getsockname()
        return str(bound[0]), int(bound[1])

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def serve_forever(self) -> None:
        if self._server is None:
            await self.start()
        assert self._server is not None
        async with self._server:
            await self._server.serve_forever()

    async def _connect_exact(
        self, destination: PublicDestination
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        last: BaseException | None = None
        for address in destination.addresses:
            try:
                return await asyncio.wait_for(
                    asyncio.open_connection(address, destination.port),
                    timeout=CONNECT_TIMEOUT_SECONDS,
                )
            except (OSError, asyncio.TimeoutError) as exc:
                last = exc
        raise EgressRefused(
            "EGRESS_CONNECT_FAILED",
            destination.hostname,
        ) from last

    async def _handle(
        self, client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter
    ) -> None:
        upstream_writer: asyncio.StreamWriter | None = None
        try:
            header = await _read_headers(client_reader)
            line = header.split(b"\r\n", 1)[0].decode("iso-8859-1")
            parts = line.split(" ")
            if len(parts) != 3:
                raise EgressRefused("EGRESS_REQUEST_LINE_INVALID")
            method = parts[0].upper()
            if method == "CONNECT":
                host, port = _parse_connect_target(parts[1])
                destination = await self.resolver.resolve(host, port)
                upstream_reader, upstream_writer = await self._connect_exact(destination)
                client_writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                await client_writer.drain()
            else:
                host, port, forwarded = _http_request_for_origin(header)
                destination = await self.resolver.resolve(host, port)
                upstream_reader, upstream_writer = await self._connect_exact(destination)
                upstream_writer.write(forwarded)
                await upstream_writer.drain()

            await asyncio.gather(
                _pipe(client_reader, upstream_writer),
                _pipe(upstream_reader, client_writer),
            )
        except EgressRefused as exc:
            body = exc.code.encode("ascii", errors="ignore")
            try:
                client_writer.write(
                    b"HTTP/1.1 403 Forbidden\r\n"
                    + f"Content-Length: {len(body)}\r\n".encode()
                    + b"Connection: close\r\nContent-Type: text/plain\r\n\r\n"
                    + body
                )
                await client_writer.drain()
            except (ConnectionError, OSError):
                pass
        finally:
            if upstream_writer is not None:
                upstream_writer.close()
                try:
                    await upstream_writer.wait_closed()
                except (ConnectionError, OSError):
                    pass
            client_writer.close()
            try:
                await client_writer.wait_closed()
            except (ConnectionError, OSError):
                pass


async def _main(host: str, port: int) -> None:
    proxy = ExactIpEgressProxy(host=host, port=port)
    bound = await proxy.start()
    print(f"VAN browser exact-IP egress proxy listening on {bound[0]}:{bound[1]}", flush=True)
    await proxy.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8899)
    args = parser.parse_args()
    asyncio.run(_main(args.host, args.port))
