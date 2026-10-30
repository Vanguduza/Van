"""Deriv WebSocket transport (wss://ws.derivws.com/websockets/v3?app_id=…).

Synchronous request/response over one socket with `req_id` correlation, so the
adapter's `transport(msg) -> dict` contract holds. The API token is read from the
account's secret reference at connect time, sent once in `authorize`, and the
adapter's placeholder token is replaced here so no prompt, log or ledger ever
sees it. Subscriptions (ticks / candles) feed the market-data layer through
`DerivMarketFeed`."""

from __future__ import annotations

import json
import threading
import time
from decimal import Decimal
from typing import Any, Callable, Iterator, Optional

from vati.execution.base import VenueUnavailable
from vati.market_data.bars import Bar, Tick

DEFAULT_ENDPOINT = "wss://ws.derivws.com/websockets/v3"
PLACEHOLDER = "<token-from-vault-never-in-prompt>"


class DerivWsError(VenueUnavailable):
    pass


class DerivWebSocketTransport:
    def __init__(self, *, app_id: str, token_provider: Callable[[], str], endpoint: str = DEFAULT_ENDPOINT, timeout_s: float = 10.0, connector: Optional[Callable[[str], Any]] = None) -> None:
        if not app_id:
            raise DerivWsError("Deriv app_id required")
        self.url = f"{endpoint}?app_id={app_id}"
        self._token_provider, self.timeout_s = token_provider, timeout_s
        self._connector = connector
        self._ws = None
        self._lock = threading.Lock()
        self._req = 0
        self.authorized_loginid: Optional[str] = None
        self.calls = 0

    # ------------------------------------------------------------- lifecycle
    def connect(self) -> None:
        if self._ws is not None:
            return
        try:
            if self._connector is not None:
                self._ws = self._connector(self.url)
            else:
                from websockets.sync.client import connect
                self._ws = connect(self.url, open_timeout=self.timeout_s, close_timeout=self.timeout_s)
        except Exception as exc:  # noqa: BLE001 — every failure here is "venue unavailable"
            raise DerivWsError(f"Deriv websocket connect failed: {exc}") from exc

    def close(self) -> None:
        if self._ws is not None:
            try:
                self._ws.close()
            finally:
                self._ws = None
                self.authorized_loginid = None

    # ----------------------------------------------------------------- calls
    def __call__(self, msg: dict[str, Any]) -> dict[str, Any]:
        if "authorize" in msg:
            token = self._token_provider()
            if not token or token == PLACEHOLDER:
                raise DerivWsError("Deriv token not available from the secret reference; fail closed")
            msg = {**msg, "authorize": token}
        self.connect()
        with self._lock:
            self._req += 1
            req_id = self._req
            payload = {**msg, "req_id": req_id}
            try:
                self._ws.send(json.dumps(payload))
                deadline = time.monotonic() + self.timeout_s
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise DerivWsError("Deriv response timeout")
                    raw = self._ws.recv(timeout=remaining) if self._connector is None else self._ws.recv()
                    resp = json.loads(raw)
                    if resp.get("req_id") == req_id:
                        break
            except DerivWsError:
                raise
            except Exception as exc:  # noqa: BLE001
                self.close()
                raise DerivWsError(f"Deriv websocket failure: {exc}") from exc
        self.calls += 1
        if "authorize" in resp and isinstance(resp.get("authorize"), dict):
            self.authorized_loginid = resp["authorize"].get("loginid")
        if resp.get("error"):
            # surfaced as data, not exception: the adapter turns it into a REJECTED receipt
            return {"error": resp["error"].get("message", "deriv error"), "error_code": resp["error"].get("code"), "req_id": req_id}
        resp.pop("echo_req", None)
        return resp


class DerivMarketFeed:
    """Historical + streaming market data from the same socket. Unauthenticated: only an app_id is needed."""

    def __init__(self, transport: DerivWebSocketTransport) -> None:
        self.t = transport

    def history_bars(self, symbol: str, *, granularity_s: int, count: int = 500, end: str = "latest") -> list[Bar]:
        r = self.t({"ticks_history": symbol, "style": "candles", "granularity": granularity_s, "count": count, "end": end})
        if r.get("error"):
            raise DerivWsError(f"ticks_history: {r['error']}")
        out = []
        for c in r.get("candles", []):
            start = int(c["epoch"]) * 1000
            out.append(Bar(symbol, start, start + granularity_s * 1000, Decimal(str(c["open"])), Decimal(str(c["high"])), Decimal(str(c["low"])), Decimal(str(c["close"])), Decimal("0"), 1, Decimal("0")))
        return out

    def history_ticks(self, symbol: str, *, count: int = 1000, end: str = "latest") -> list[Tick]:
        r = self.t({"ticks_history": symbol, "style": "ticks", "count": count, "end": end})
        if r.get("error"):
            raise DerivWsError(f"ticks_history: {r['error']}")
        h = r.get("history", {})
        return [Tick(int(t) * 1000, Decimal(str(p)), Decimal(str(p))) for t, p in zip(h.get("times", []), h.get("prices", []))]

    def active_symbols(self) -> list[dict]:
        r = self.t({"active_symbols": "brief", "product_type": "basic"})
        return r.get("active_symbols", [])
