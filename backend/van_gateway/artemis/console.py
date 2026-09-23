from __future__ import annotations

from dataclasses import dataclass
import hashlib
import secrets
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.background import BackgroundTask


_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}
_FORWARD_ALLOWLIST = {
    "accept",
    "accept-encoding",
    "accept-language",
    "if-modified-since",
    "if-none-match",
    "range",
    "user-agent",
}
_SESSION_COOKIE = "__Host-van_artemis_console"


@dataclass(frozen=True)
class ConsoleSession:
    device_id: str
    expires_at: float


class ArtemisConsoleProxy:
    """Owner-device web-session boundary for the private Hermes ARTEMIS console.

    Android never receives the Netcup bearer token. The phone first performs one normal
    VAN privileged POST (ingress token + device access token + hardware device proof),
    receives a one-use launch URL, and exchanges that URL for a short HttpOnly cookie.
    Browser asset/API requests are then same-origin to the VAN Gateway and are proxied
    server-side to the Netcup Hermes console proxy.

    The Netcup side is observe-only; this class intentionally does not create another
    Android-execution authority.
    """

    SESSION_PATH = "/v1/artemis/console/session"
    LAUNCH_PREFIX = "/v1/artemis/console/launch/"
    CONSOLE_PREFIX = "/v1/artemis/console/"

    def __init__(
        self,
        *,
        upstream_base_url: str,
        upstream_token_file: str,
        public_base_url: str,
        session_ttl_seconds: int = 900,
        launch_ttl_seconds: int = 60,
        enabled: bool = False,
    ) -> None:
        self.upstream_base_url = upstream_base_url.rstrip("/")
        self.upstream_token_file = upstream_token_file
        self.public_base_url = public_base_url.rstrip("/")
        self.session_ttl_seconds = max(60, min(int(session_ttl_seconds), 3600))
        self.launch_ttl_seconds = max(15, min(int(launch_ttl_seconds), 300))
        self.enabled = bool(enabled)
        self._launches: dict[str, ConsoleSession] = {}
        self._sessions: dict[str, ConsoleSession] = {}

    @property
    def ready(self) -> bool:
        return (
            self.enabled
            and self.upstream_base_url.startswith(("http://", "https://"))
            and bool(self.upstream_token_file)
            and Path(self.upstream_token_file).is_file()
        )

    def _now(self) -> float:
        return time.time()

    def _prune(self) -> None:
        now = self._now()
        self._launches = {key: value for key, value in self._launches.items() if value.expires_at > now}
        self._sessions = {key: value for key, value in self._sessions.items() if value.expires_at > now}

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def mint(self, device_id: str) -> dict:
        if not self.ready:
            raise RuntimeError("artemis_console_unavailable")
        self._prune()
        raw = secrets.token_urlsafe(32)
        expires = self._now() + self.launch_ttl_seconds
        self._launches[self._digest(raw)] = ConsoleSession(device_id=device_id, expires_at=expires)
        path = f"{self.LAUNCH_PREFIX}{raw}"
        return {
            "launch_url": f"{self.public_base_url}{path}",
            "expires_at_unix": int(expires),
            "mode": "OBSERVE_ONLY",
            "authority": "HERMES_CONTROL_AUTHORITY",
            "subordinate": "ARTEMIS",
        }

    def redeem(self, raw_launch_token: str) -> tuple[str, ConsoleSession] | None:
        self._prune()
        record = self._launches.pop(self._digest(raw_launch_token), None)
        if record is None or record.expires_at <= self._now():
            return None
        cookie = secrets.token_urlsafe(32)
        session = ConsoleSession(
            device_id=record.device_id,
            expires_at=self._now() + self.session_ttl_seconds,
        )
        self._sessions[self._digest(cookie)] = session
        return cookie, session

    def cookie_session(self, request: Request) -> ConsoleSession | None:
        self._prune()
        raw = request.cookies.get(_SESSION_COOKIE, "")
        if not raw:
            return None
        record = self._sessions.get(self._digest(raw))
        if record is None or record.expires_at <= self._now():
            return None
        return record

    def is_public_launch_request(self, request: Request) -> bool:
        return request.method == "GET" and request.url.path.startswith(self.LAUNCH_PREFIX)

    def is_console_resource_path(self, path: str) -> bool:
        if path == self.SESSION_PATH or path.startswith(self.LAUNCH_PREFIX):
            return False
        return (
            path == self.CONSOLE_PREFIX.rstrip("/")
            or path.startswith(self.CONSOLE_PREFIX)
            or path == "/api"
            or path.startswith("/api/")
            or path == "/images"
            or path.startswith("/images/")
            or path == "/videos"
            or path.startswith("/videos/")
            or path == "/local_file"
            or path.startswith("/local_file/")
        )

    def browser_request_authorized(self, request: Request) -> bool:
        return self.is_console_resource_path(request.url.path) and self.cookie_session(request) is not None

    def launch_cookie_kwargs(self) -> dict:
        return {
            "key": _SESSION_COOKIE,
            "httponly": True,
            "secure": urlsplit(self.public_base_url).scheme.lower() == "https",
            "samesite": "strict",
            "path": "/",
            "max_age": self.session_ttl_seconds,
        }

    def _upstream_token(self) -> str:
        if not self.ready:
            raise RuntimeError("artemis_console_unavailable")
        token = Path(self.upstream_token_file).read_text(encoding="utf-8").strip()
        if len(token) < 32:
            raise RuntimeError("artemis_console_token_invalid")
        return token

    @staticmethod
    def rewrite_html_base(body: bytes) -> bytes:
        text = body.decode("utf-8")
        if '<base href="/">' in text:
            text = text.replace('<base href="/">', '<base href="/v1/artemis/console/">', 1)
        return text.encode("utf-8")

    @staticmethod
    def upstream_path_for(request_path: str) -> str:
        if request_path == ArtemisConsoleProxy.CONSOLE_PREFIX.rstrip("/"):
            return "/"
        if request_path.startswith(ArtemisConsoleProxy.CONSOLE_PREFIX):
            suffix = request_path[len(ArtemisConsoleProxy.CONSOLE_PREFIX):]
            return "/" + suffix
        return request_path

    async def proxy(self, request: Request) -> Response:
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            return JSONResponse(
                status_code=405,
                content={
                    "detail": "hermes_governed_control_required",
                    "mode": "OBSERVE_ONLY",
                },
            )
        session = self.cookie_session(request)
        if session is None:
            return JSONResponse(status_code=401, content={"detail": "artemis_console_session_required"})
        try:
            token = self._upstream_token()
        except RuntimeError as exc:
            return JSONResponse(status_code=503, content={"detail": str(exc)})

        upstream_path = self.upstream_path_for(request.url.path)
        target = f"{self.upstream_base_url}{upstream_path}"
        if request.url.query:
            target += f"?{request.url.query}"

        headers = {
            key: value
            for key, value in request.headers.items()
            if key.lower() in _FORWARD_ALLOWLIST
        }
        headers["Authorization"] = f"Bearer {token}"

        client = httpx.AsyncClient(timeout=None, follow_redirects=False)
        try:
            upstream_request = client.build_request(request.method, target, headers=headers)
            upstream_response = await client.send(upstream_request, stream=True)
        except httpx.HTTPError as exc:
            await client.aclose()
            return JSONResponse(
                status_code=502,
                content={"detail": "artemis_console_upstream_unavailable", "error": str(exc)},
            )

        response_headers = {
            key: value
            for key, value in upstream_response.headers.items()
            if key.lower() not in _HOP_BY_HOP
            and key.lower() not in {"content-length", "set-cookie"}
        }
        response_headers["Cache-Control"] = "no-store"
        response_headers["X-Van-Artemis-Mode"] = "OBSERVE_ONLY"
        response_headers["X-Van-Artemis-Authority"] = "HERMES_SUBORDINATE"

        content_type = upstream_response.headers.get("content-type", "")
        if content_type.lower().startswith("text/html"):
            try:
                body = await upstream_response.aread()
                body = self.rewrite_html_base(body)
            finally:
                await upstream_response.aclose()
                await client.aclose()
            # httpx decodes Content-Encoding when reading the body. Do not forward the
            # upstream encoding/length after rewriting the Angular base path.
            response_headers.pop("content-encoding", None)
            response_headers.pop("content-type", None)
            return Response(
                content=body,
                status_code=upstream_response.status_code,
                media_type="text/html",
                headers=response_headers,
            )

        async def close_all() -> None:
            await upstream_response.aclose()
            await client.aclose()

        return StreamingResponse(
            upstream_response.aiter_raw(),
            status_code=upstream_response.status_code,
            headers=response_headers,
            background=BackgroundTask(close_all),
        )


def session_cookie_name() -> str:
    return _SESSION_COOKIE
