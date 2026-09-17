"""Request signing shared by the server, the Python client and the MCP shim.

signature = HMAC-SHA256(token, "{ts}\n{nonce}\n{METHOD}\n{path}\n{sha256(body)}")
ts within ±60 s of server time; nonce single-use within the skew window."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Mapping, Optional

SKEW_S = 60
HDR_TS, HDR_NONCE, HDR_SIG = "x-van-ts", "x-van-nonce", "x-van-signature"


def _canonical(ts: str, nonce: str, method: str, path: str, body: bytes) -> bytes:
    return f"{ts}\n{nonce}\n{method.upper()}\n{path}\n{hashlib.sha256(body).hexdigest()}".encode()


def sign(token: str, ts: str, nonce: str, method: str, path: str, body: bytes) -> str:
    return hmac.new(token.encode(), _canonical(ts, nonce, method, path, body), hashlib.sha256).hexdigest()


def sign_headers(token: str, method: str, path: str, body: bytes, *, now: Optional[float] = None) -> dict[str, str]:
    ts = str(int(now if now is not None else time.time()))
    nonce = secrets.token_hex(12)
    return {HDR_TS: ts, HDR_NONCE: nonce, HDR_SIG: sign(token, ts, nonce, method, path, body)}


class NonceCache:
    def __init__(self) -> None:
        self._seen: dict[str, float] = {}

    def check_and_add(self, nonce: str, now: float) -> bool:
        for k, t in list(self._seen.items()):
            if now - t > 2 * SKEW_S:
                del self._seen[k]
        if nonce in self._seen:
            return False
        self._seen[nonce] = now
        return True


def verify_request(token: str, headers: Mapping[str, str], method: str, path: str, body: bytes, *, nonces: NonceCache, now: Optional[float] = None) -> tuple[bool, str]:
    now = now if now is not None else time.time()
    h = {k.lower(): v for k, v in headers.items()}
    ts, nonce, sig = h.get(HDR_TS, ""), h.get(HDR_NONCE, ""), h.get(HDR_SIG, "")
    if not (ts.isdigit() and nonce and sig):
        return False, "missing signature headers"
    if abs(now - int(ts)) > SKEW_S:
        return False, "timestamp outside skew window"
    if not hmac.compare_digest(sign(token, ts, nonce, method, path, body), sig):
        return False, "bad signature"
    if not nonces.check_and_add(nonce, now):
        return False, "nonce replayed"
    return True, "ok"
