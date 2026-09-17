"""HTTPS (mTLS) transport for `Mt5BridgeClient` → Windows MT5 worker.

Wire contract (both sides, see deploy/van-trading-core/windows/mt5_worker):
  POST {bridge_url}/bridge/v1/call   body = signed BridgeRequest JSON
  response JSON must echo `nonce` and carry `worker_time_ms`; the client checks both.
Transport security: TLS with the worker's CA pinned, client certificate presented
(mTLS). Without the CA file the transport refuses to construct: never plaintext,
never unverified TLS."""

from __future__ import annotations

import http.client
import json
import ssl
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from vati.execution.base import VenueUnavailable


class Mt5TransportError(VenueUnavailable):
    pass


class Mt5HttpTransport:
    def __init__(self, bridge_url: str, *, ca_file: str, client_cert: Optional[str] = None, client_key: Optional[str] = None, timeout_s: float = 10.0) -> None:
        u = urlparse(bridge_url)
        if u.scheme != "https":
            raise Mt5TransportError("MT5 bridge must be https (mTLS); refusing plaintext")
        if not Path(ca_file).is_file():
            raise Mt5TransportError(f"bridge CA file missing: {ca_file}")
        self.host, self.port, self.path = u.hostname, u.port or 9443, "/bridge/v1/call"
        ctx = ssl.create_default_context(cafile=ca_file)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.check_hostname = True
        if client_cert:
            ctx.load_cert_chain(client_cert, client_key)
        self._ctx, self.timeout_s = ctx, timeout_s
        self.calls = 0

    def __call__(self, req: dict[str, Any]) -> dict[str, Any]:
        conn = http.client.HTTPSConnection(self.host, self.port, context=self._ctx, timeout=self.timeout_s)
        try:
            body = json.dumps(req, separators=(",", ":"), sort_keys=True).encode()
            conn.request("POST", self.path, body=body, headers={"Content-Type": "application/json", "X-Vati-Bridge": "1"})
            resp = conn.getresponse()
            text = resp.read().decode("utf-8", "replace")
            if resp.status != 200:
                raise Mt5TransportError(f"bridge HTTP {resp.status}: {text[:200]}")
            self.calls += 1
            return json.loads(text)
        except (OSError, ssl.SSLError, json.JSONDecodeError) as exc:
            raise Mt5TransportError(f"bridge unreachable: {exc}") from exc
        finally:
            conn.close()
