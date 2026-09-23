from __future__ import annotations

import time

from starlette.requests import Request

from van_gateway.artemis.console import ArtemisConsoleProxy, session_cookie_name


def _request(path: str, cookie: str | None = None, method: str = "GET") -> Request:
    headers = []
    if cookie:
        headers.append((b"cookie", f"{session_cookie_name()}={cookie}".encode()))
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "scheme": "https",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("van.example", 443),
    }
    return Request(scope)


def test_launch_is_one_use_and_becomes_cookie_session(tmp_path):
    secret = tmp_path / "artemis-console.token"
    secret.write_text("a" * 64)
    proxy = ArtemisConsoleProxy(
        upstream_base_url="http://10.10.0.2:9135",
        upstream_token_file=str(secret),
        public_base_url="https://van.example",
        enabled=True,
        launch_ttl_seconds=60,
        session_ttl_seconds=900,
    )

    launch = proxy.mint("owner-device")
    raw = launch["launch_url"].rsplit("/", 1)[-1]
    redeemed = proxy.redeem(raw)
    assert redeemed is not None
    cookie, session = redeemed
    assert session.device_id == "owner-device"
    assert proxy.redeem(raw) is None
    assert proxy.browser_request_authorized(_request("/v1/artemis/console/", cookie))
    assert proxy.browser_request_authorized(_request("/api/status", cookie))
    assert not proxy.browser_request_authorized(_request("/api/status", "wrong"))


def test_console_rewrites_angular_base_and_never_treats_session_post_as_browser_resource(tmp_path):
    secret = tmp_path / "artemis-console.token"
    secret.write_text("b" * 64)
    proxy = ArtemisConsoleProxy(
        upstream_base_url="http://10.10.0.2:9135",
        upstream_token_file=str(secret),
        public_base_url="https://van.example",
        enabled=True,
    )
    body = b'<html><head><base href="/"></head><body></body></html>'
    assert b'<base href="/v1/artemis/console/">' in proxy.rewrite_html_base(body)
    assert proxy.is_console_resource_path("/v1/artemis/console/")
    assert proxy.is_console_resource_path("/api/stream/device-state")
    assert not proxy.is_console_resource_path("/v1/artemis/console/session")
    assert proxy.is_public_launch_request(_request("/v1/artemis/console/launch/abc"))


def test_console_mutation_requires_same_origin(tmp_path):
    secret = tmp_path / "artemis-console.token"
    secret.write_text("c" * 64)
    proxy = ArtemisConsoleProxy(
        upstream_base_url="http://10.10.0.2:9135",
        upstream_token_file=str(secret),
        public_base_url="https://van.example",
        enabled=True,
    )
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": "/api/run",
        "raw_path": b"/api/run",
        "query_string": b"",
        "headers": [(b"origin", b"https://van.example")],
        "client": ("127.0.0.1", 12345),
        "server": ("van.example", 443),
    }
    assert proxy.mutation_origin_allowed(Request(scope))
    scope["headers"] = [(b"origin", b"https://evil.example")]
    assert not proxy.mutation_origin_allowed(Request(scope))
    scope["headers"] = []
    assert not proxy.mutation_origin_allowed(Request(scope))
