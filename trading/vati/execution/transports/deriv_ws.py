"""Deriv WebSocket transport (wss://ws.derivws.com/websockets/v3?app_id=…).

Synchronous request/response over one socket with `req_id` correlation, so the
adapter's `transport(msg) -> dict` contract holds. The API token is read from the
account's secret reference before private calls and reauthorized on rotation or
reconnection. The
adapter's placeholder token is replaced here so no prompt, log or ledger ever
sees it. Subscriptions (ticks / candles) feed the market-data layer through
`DerivMarketFeed`."""

from __future__ import annotations

import json
import hashlib
from contextlib import nullcontext
import threading
import time
from decimal import Decimal
from typing import Any, Callable, Iterator, Optional

from vati.execution.base import VenueUnavailable
from vati.execution.deriv_identity import DerivIdentity, DerivIdentityError
from vati.accounts.registry import AccountRegistryError
from vati.core.file_lock import StateFileLockError
from vati.market_data.bars import Bar, Tick

DEFAULT_ENDPOINT = "wss://ws.derivws.com/websockets/v3"
PLACEHOLDER = "<token-from-vault-never-in-prompt>"


class DerivWsError(VenueUnavailable):
    pass


class DerivWebSocketTransport:
    # Authenticated v3 calls used by this runtime. Public quote/history calls do
    # not acquire a token. Effects are sent exactly once; a lost response closes
    # this socket and propagates uncertainty, never reconnect-and-resend.
    PRIVATE_CALLS = frozenset({"portfolio", "buy", "sell", "contract_update",
                               "proposal_open_contract", "statement", "profit_table",
                               "balance", "transaction"})
    ENTRY_CALLS = frozenset({"proposal", "buy"})

    def __init__(self, *, app_id: str, token_provider: Callable[[], str], endpoint: str = DEFAULT_ENDPOINT, timeout_s: float = 10.0, connector: Optional[Callable[[str], Any]] = None,
                 identity: Optional[DerivIdentity] = None, entry_scope=None) -> None:
        if not app_id:
            raise DerivWsError("Deriv app_id required")
        self.url = f"{endpoint}?app_id={app_id}"
        self._token_provider, self.timeout_s = token_provider, timeout_s
        self._connector, self.identity, self.entry_scope = connector, identity, entry_scope
        self._ws = None
        self._lock = threading.RLock()
        self._req = 0
        self.authorized_loginid: Optional[str] = None
        self.authorized_profile: Optional[dict] = None
        self._token_fingerprint = None
        self.calls = 0

    def connect(self) -> None:
        with self._lock:
            if self._ws is not None:
                return
            try:
                if self._connector is not None:
                    self._ws = self._connector(self.url)
                else:
                    from websockets.sync.client import connect
                    self._ws = connect(self.url, open_timeout=self.timeout_s, close_timeout=self.timeout_s)
            except Exception:
                # Provider/library exceptions can contain URLs or credentials.
                raise DerivWsError("Deriv websocket connect failed") from None

    def close(self) -> None:
        with self._lock:
            try:
                if self._ws is not None:
                    try:
                        self._ws.close()
                    except Exception:
                        pass  # State is discarded even when the remote close fails.
            finally:
                self._ws = None
                self.authorized_loginid = None
                self.authorized_profile = None
                self._token_fingerprint = None

    def _exchange_locked(self, msg: dict[str, Any]) -> dict[str, Any]:
        self._req += 1
        req_id = self._req
        try:
            self._ws.send(json.dumps({**msg, "req_id": req_id}))
            deadline = time.monotonic() + self.timeout_s
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise DerivWsError("Deriv response timeout")
                raw = self._ws.recv(timeout=remaining) if self._connector is None else self._ws.recv()
                resp = json.loads(raw, parse_float=Decimal)
                if not isinstance(resp, dict):
                    raise DerivWsError("Deriv response must be an object")
                if resp.get("req_id") == req_id:
                    break
        except Exception:
            self.close()
            raise DerivWsError("Deriv websocket response unavailable; reconcile effects before retry") from None
        self.calls += 1
        if resp.get("error"):
            return {"error": resp["error"].get("message", "deriv error"),
                    "error_code": resp["error"].get("code"), "req_id": req_id}
        resp.pop("echo_req", None)
        return resp

    def _authorize_locked(self, token: str) -> dict[str, Any]:
        self.authorized_loginid = None
        self.authorized_profile = None
        self._token_fingerprint = None
        response = self._exchange_locked({"authorize": token})
        profile = response.get("authorize")
        if response.get("error") or not isinstance(profile, dict):
            self.close()
            return {"error": "Deriv native authorization refused", "error_code": "NativeIdentityRefused"}
        if self.identity is not None:
            try:
                self.identity.validate(profile)
            except DerivIdentityError as exc:
                self.close()
                return {"error": str(exc), "error_code": "NativeIdentityRefused"}
        self.authorized_loginid = profile.get("loginid")
        self.authorized_profile = dict(profile)
        self._token_fingerprint = hashlib.sha256(token.encode()).digest()
        return response

    def __call__(self, msg: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            # The entry fence is held through the broker send/response, sharing
            # Commander lock order. It does not fence reduce-only protection.
            scope = self.entry_scope() if self.entry_scope and self.ENTRY_CALLS.intersection(msg) else nullcontext()
            try:
                with scope:
                    return self._call_locked(msg)
            except (AccountRegistryError, StateFileLockError):
                return {"error": "Deriv account entry binding or mode changed", "error_code": "EntryBindingRefused"}

    def _call_locked(self, msg: dict[str, Any]) -> dict[str, Any]:
        private = bool(self.PRIVATE_CALLS.intersection(msg))
        # Bound proposals also require current native identity before quoting.
        needs_auth = "authorize" in msg or private or (self.identity is not None and bool(self.ENTRY_CALLS.intersection(msg)))
        token = None
        if needs_auth:
            try:
                token = self._token_provider()
            except Exception:
                raise DerivWsError("Deriv credential reference unavailable; fail closed") from None
            if not isinstance(token, str) or not token or token == PLACEHOLDER:
                raise DerivWsError("Deriv token not available from the secret reference; fail closed")
        self.connect()
        if needs_auth and ("authorize" in msg or self.authorized_profile is None or
                           self._token_fingerprint != hashlib.sha256(token.encode()).digest()):
            authorized = self._authorize_locked(token)
            if "authorize" in msg or authorized.get("error"):
                return authorized
        return self._exchange_locked(msg)


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
