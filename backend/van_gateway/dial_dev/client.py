"""Typed server-to-server client for DIAL's Development Projection API v1.

Only the VAN gateway holds the DIAL-scoped credential. It is read from a token file on
every call — so a rotated file takes effect without a restart — and is screened out of
everything that comes back, so the one way it could reach Android (DIAL echoing a request
header into a body) is a refusal rather than a leak.

No Android header is ever forwarded upstream: requests are built from scratch here, with
the bearer and an Accept header only.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable

import httpx

from van_gateway.dial_dev.config import MIN_TOKEN_LENGTH, DialDevConfig


class DialDevDisabled(Exception):
    """The feature switch is off. Answered as 404 on the owner surface."""


class DialDevUnavailable(Exception):
    """DIAL cannot be asked right now. Answered as 503 `dial_dev_unavailable`.

    `reason` is a fixed vocabulary safe to show the device; it never carries an exception
    message, a URL or anything read from the token file.
    """

    REASONS = frozenset({
        "unconfigured",
        "credential_invalid",
        "unreachable",
        "timeout",
        "upstream_error",
        "upstream_auth_refused",
        "upstream_redirect",
        "upstream_malformed",
        "upstream_echoed_credential",
    })

    def __init__(self, reason: str) -> None:
        if reason not in self.REASONS:
            reason = "upstream_error"
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class UpstreamResponse:
    status_code: int
    body: bytes


@dataclass
class UpstreamStream:
    """An open SSE response and how to release it."""

    response: httpx.Response
    close: Callable[[], Awaitable[None]]
    #: True when a line would disclose the DIAL-scoped credential.
    discloses_credential: Callable[[str], bool]

    async def lines(self) -> AsyncIterator[str]:
        async for line in self.response.aiter_lines():
            yield line


class DialDevClient:
    USER_AGENT = "van-gateway/dial-dev"

    def __init__(
        self,
        config: DialDevConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config
        #: Replaceable so tests can put DIAL behind an in-process fake. Production leaves
        #: it None and httpx opens a real connection over the private overlay.
        self.transport = transport

    # ------------------------------------------------------------------ credential

    def _token(self) -> str:
        if not self.config.enabled:
            raise DialDevDisabled()
        if not self.config.configured:
            raise DialDevUnavailable("unconfigured")
        try:
            token = Path(self.config.token_file).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise DialDevUnavailable("unconfigured") from exc
        if len(token) < MIN_TOKEN_LENGTH or any(ch.isspace() for ch in token):
            raise DialDevUnavailable("credential_invalid")
        return token

    def _headers(self, token: str, accept: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "Accept": accept,
            "User-Agent": self.USER_AGENT,
        }

    def _client(self, timeout: httpx.Timeout) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.config.base_url,
            timeout=timeout,
            transport=self.transport,
            follow_redirects=False,
            # A proxy environment variable must not route DIAL traffic somewhere else.
            trust_env=False,
        )

    # --------------------------------------------------------------------- requests

    async def get(self, path: str, params: dict[str, Any] | None = None) -> UpstreamResponse:
        return await self._send("GET", path, params=params)

    async def post(self, path: str, payload: dict[str, Any]) -> UpstreamResponse:
        return await self._send("POST", path, json_body=payload)

    async def _send(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> UpstreamResponse:
        token = self._token()
        async with self._client(httpx.Timeout(self.config.timeout_s)) as client:
            try:
                response = await client.request(
                    method,
                    path,
                    params=params,
                    json=json_body,
                    headers=self._headers(token, "application/json"),
                )
            except httpx.TimeoutException as exc:
                raise DialDevUnavailable("timeout") from exc
            except httpx.HTTPError as exc:
                raise DialDevUnavailable("unreachable") from exc
        body = response.content
        if token.encode("utf-8") in body:
            raise DialDevUnavailable("upstream_echoed_credential")
        return UpstreamResponse(status_code=response.status_code, body=body)

    async def open_stream(self, path: str) -> UpstreamStream:
        """Open DIAL's SSE stream. The caller must `await stream.close()`."""
        token = self._token()
        # Connect is bounded; reading is not, because an idle event stream is healthy.
        client = self._client(httpx.Timeout(self.config.timeout_s, read=None))
        request = client.build_request(
            "GET", path, headers=self._headers(token, "text/event-stream")
        )
        try:
            response = await client.send(request, stream=True)
        except httpx.TimeoutException as exc:
            await client.aclose()
            raise DialDevUnavailable("timeout") from exc
        except httpx.HTTPError as exc:
            await client.aclose()
            raise DialDevUnavailable("unreachable") from exc

        async def close() -> None:
            await response.aclose()
            await client.aclose()

        return UpstreamStream(
            response=response,
            close=close,
            discloses_credential=lambda line: token in line,
        )
