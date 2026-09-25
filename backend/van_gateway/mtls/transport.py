"""TLS context, client-certificate plumbing and the per-route gate for the public listener.

uvicorn verifies the client certificate during the handshake (chain to the VAN device CA,
validity) but does not tell the ASGI app which certificate it saw. The two protocol shims
below record the verified peer certificate on the connection and hand it to the app as the
scope extension ``van.mtls``. The gate then decides per route:

* no client certificate: only the routes a phone must reach *before* it holds one (pairing,
  hardware-bound bootstrap, TLS certificate enrolment) and the two browser surfaces that carry
  their own credential (the ARTEMIS console launch/cookie paths, the broker OAuth callback);
* a client certificate: admitted only if this CA issued it to that device and has not revoked
  it. The device id it names is put on the scope so the gateway can require the device token
  to belong to the same device.

The gate wraps the public listener only; the loopback listener used by Hermes and local tools
is unchanged.
"""

from __future__ import annotations

import json
import re
import ssl
from pathlib import Path
from typing import Any, Awaitable, Callable

from uvicorn.protocols.http.h11_impl import H11Protocol
from uvicorn.protocols.websockets.websockets_sansio_impl import WebSocketsSansIOProtocol

from van_gateway.mtls.pki import CA_CERT, SERVER_CERT, SERVER_KEY, DeviceCA, peer_identity

EXTENSION = "van.mtls"
STATE_DEVICE_ID = "van_mtls_device_id"
WS_CLOSE_CERT_REQUIRED = 4403

ASGIApp = Callable[[dict, Callable[[], Awaitable[dict]], Callable[[dict], Awaitable[None]]], Awaitable[None]]


def build_ssl_context(directory: str | Path) -> ssl.SSLContext:
    """TLS 1.3 only. The client certificate is requested and, when presented, verified
    against the device CA in the handshake; whether one is *required* is the gate's call,
    because pairing has to work before the phone holds one."""
    d = Path(directory)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.load_cert_chain(str(d / SERVER_CERT), str(d / SERVER_KEY))
    ctx.load_verify_locations(cafile=str(d / CA_CERT))
    ctx.verify_mode = ssl.CERT_OPTIONAL
    ctx.set_alpn_protocols(["http/1.1"])
    return ctx


def _peer_der(transport: Any) -> bytes | None:
    ssl_object = transport.get_extra_info("ssl_object") if transport is not None else None
    if ssl_object is None:
        return None
    try:
        return ssl_object.getpeercert(binary_form=True) or None
    except ValueError:  # handshake not complete; cannot happen once a request is parsed
        return None


class _PeerCertificateMixin:
    """Wrap the app per connection so every scope on it carries the verified peer certificate."""

    app: ASGIApp

    def connection_made(self, transport: Any) -> None:  # type: ignore[override]
        super().connection_made(transport)  # type: ignore[misc]
        info = {"client_cert_der": _peer_der(transport)}
        inner = self.app

        async def app(scope: dict, receive: Any, send: Any) -> None:
            extensions = scope.get("extensions")
            if not isinstance(extensions, dict):
                extensions = {}
                scope["extensions"] = extensions
            extensions[EXTENSION] = info
            await inner(scope, receive, send)

        self.app = app


class PeerCertificateH11Protocol(_PeerCertificateMixin, H11Protocol):
    pass


class PeerCertificateWebSocketProtocol(_PeerCertificateMixin, WebSocketsSansIOProtocol):
    pass


_OAUTH_CALLBACK = re.compile(r"^/v1/trading/oauth/[^/]+/callback$")
_ARTEMIS_PREFIXES = ("/v1/artemis/console/", "/api/", "/images/", "/videos/", "/local_file/")
_ARTEMIS_EXACT = {"/v1/artemis/console", "/api", "/images", "/videos", "/local_file"}
_ARTEMIS_SESSION = "/v1/artemis/console/session"
_NO_CERT_POSTS = {
    "/v1/devices/pair",
    "/v1/devices/bootstrap/challenge",
    "/v1/devices/bootstrap/attest",
    "/v1/devices/tls-certificate",
}


def allowed_without_certificate(scope_type: str, method: str, path: str) -> bool:
    if scope_type != "http":
        return False  # the session WebSocket always needs a device certificate
    if method == "POST" and path in _NO_CERT_POSTS:
        return True
    if method == "GET" and _OAUTH_CALLBACK.fullmatch(path):
        return True
    if path == _ARTEMIS_SESSION:
        return False  # minting a console session is an owner action: certificate required
    return path in _ARTEMIS_EXACT or path.startswith(_ARTEMIS_PREFIXES)


class MutualTLSGate:
    """Pure ASGI. Enforces the client-certificate policy on scopes from the public listener."""

    def __init__(self, app: ASGIApp, ca_provider: Callable[[], DeviceCA | None]):
        self.app = app
        self.ca_provider = ca_provider

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] not in {"http", "websocket"}:
            return await self.app(scope, receive, send)
        info = (scope.get("extensions") or {}).get(EXTENSION)
        if info is None:
            # Not from the public listener (loopback). Unchanged behaviour.
            return await self.app(scope, receive, send)

        identity = peer_identity(info.get("client_cert_der"))
        if identity is None:
            if allowed_without_certificate(scope["type"], scope.get("method", "GET"), scope["path"]):
                return await self.app(scope, receive, send)
            return await self._refuse(scope, send, "client_certificate_required")

        ca = self.ca_provider()
        serial_hex, device_id = identity
        if ca is None or not ca.admitted(serial_hex, device_id):
            return await self._refuse(scope, send, "client_certificate_not_admitted")
        state = scope.setdefault("state", {})
        state[STATE_DEVICE_ID] = device_id
        return await self.app(scope, receive, send)

    @staticmethod
    async def _refuse(scope: dict, send: Any, detail: str) -> None:
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": WS_CLOSE_CERT_REQUIRED, "reason": detail})
            return
        body = json.dumps({"detail": detail}).encode()
        await send({"type": "http.response.start", "status": 403,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})


def mtls_device_id(scope: dict) -> str | None:
    """The device named by the verified client certificate, when the request came over mutual TLS."""
    state = scope.get("state")
    if isinstance(state, dict):
        value = state.get(STATE_DEVICE_ID)
        return value if isinstance(value, str) else None
    return None
