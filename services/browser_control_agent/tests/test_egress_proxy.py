from __future__ import annotations

import asyncio
import ipaddress
import socket

import pytest

from services.browser_control_agent.egress_proxy import (
    EgressRefused, ExactIpEgressProxy, PublicResolver,
    _http_request_for_origin, validate_public_url_syntax,
)


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "chrome://settings",
        "http://127.0.0.1/",
        "http://10.0.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "https://[::1]/",
        "http://224.0.0.1/",
        "http://239.255.255.250/",
        "https://[ff02::1]/",
        "https://[fec0::1]/",
        "https://[::ffff:224.0.0.1]/",
        "https://user:pass@example.com/",
        "https://example.com:8443/",
    ],
)
def test_public_url_syntax_refuses_local_secret_and_nonstandard_destinations(url):
    with pytest.raises(EgressRefused):
        validate_public_url_syntax(url)


def test_http_proxy_rewrites_absolute_form_and_removes_proxy_headers():
    host, port, request = _http_request_for_origin(
        b"GET http://example.com/a?q=1 HTTP/1.1\r\n"
        b"Host: example.com\r\nProxy-Connection: keep-alive\r\n"
        b"Proxy-Authorization: secret\r\nX-Test: yes\r\n\r\n"
    )
    assert (host, port) == ("example.com", 80)
    assert request.startswith(b"GET /a?q=1 HTTP/1.1\r\n")
    assert b"Proxy-Authorization" not in request
    assert b"Proxy-Connection" not in request
    assert b"X-Test: yes" in request


@pytest.mark.asyncio
@pytest.mark.parametrize("denied", ["10.0.0.9", "224.0.0.1", "ff02::1", "fec0::1", "::ffff:224.0.0.1"])
async def test_resolver_rejects_hostname_if_any_dns_answer_is_non_public(monkeypatch, denied):
    loop = asyncio.get_running_loop()

    async def fake_getaddrinfo(host, port, **kwargs):
        blocked_family = socket.AF_INET6 if ":" in denied else socket.AF_INET
        blocked_sockaddr = (denied, port, 0, 0) if blocked_family == socket.AF_INET6 else (denied, port)
        return [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", port)),
            (blocked_family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", blocked_sockaddr),
        ]

    monkeypatch.setattr(loop, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(EgressRefused, match="EGRESS_NON_PUBLIC_ADDRESS"):
        await PublicResolver().resolve("example.com", 443)


@pytest.mark.asyncio
async def test_resolver_preserves_public_ipv4_ipv6_and_mapped_ipv4_addresses(monkeypatch):
    loop = asyncio.get_running_loop()

    async def public_answers(host, port, **kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("8.8.8.8", port)),
            (socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("2606:4700:4700::1111", port, 0, 0)),
            (socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("::ffff:8.8.8.8", port, 0, 0)),
        ]

    monkeypatch.setattr(loop, "getaddrinfo", public_answers)
    destination = await PublicResolver().resolve("PUBLIC.EXAMPLE.", 443)
    assert destination.hostname == "public.example" and destination.port == 443
    assert len(destination.addresses) == 3
    assert destination.addresses[:2] == ("8.8.8.8", "2606:4700:4700::1111")
    assert ipaddress.IPv6Address(destination.addresses[2]).ipv4_mapped == ipaddress.IPv4Address("8.8.8.8")


def test_proxy_refuses_non_loopback_bind():
    with pytest.raises(EgressRefused, match="EGRESS_PROXY_BIND_NOT_LOOPBACK"):
        ExactIpEgressProxy(host="0.0.0.0", port=8899)
