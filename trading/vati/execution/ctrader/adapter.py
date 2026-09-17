"""cTrader Open API venue adapter (Rev 5 route 1: Linux-native FX/CFD execution).

Volumes are in cents of units (lots × lotSize), prices in absolute doubles except
where the API uses 1/100000 units (spots, relative SL). A MARKET order carries its
protective stop as `relativeStopLoss` in the same request (absolute SL is not accepted
on MARKET orders by the API), so the "stop in the same request" doctrine holds. Stops
only tighten. The label carries the intent id so reconciliation can find orphans."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_DOWN
from typing import Any, Callable, Optional

from vati.execution.base import AccountState, ExecutionReceipt, Health, OrderCommand, VenuePosition, VenueUnavailable
from vati.execution.ctrader.transport import CtraderApiError, CtraderTransport
from vati.risk.contracts import Direction, LossModel

ZERO = Decimal("0")
PRICE_SCALE = Decimal("100000")


@dataclass
class SymbolInfo:
    symbol_id: int
    name: str
    digits: int
    lot_size_cents: int      # units × 100
    min_volume: int
    step_volume: int
    max_volume: int

    def lots_to_volume(self, lots: Decimal) -> int:
        vol = int((lots * Decimal(self.lot_size_cents)).to_integral_value(rounding=ROUND_DOWN))
        if self.step_volume:
            vol -= vol % self.step_volume
        return vol

    def volume_to_lots(self, volume: int) -> Decimal:
        return (Decimal(volume) / Decimal(self.lot_size_cents)).quantize(Decimal("0.01"))


@dataclass
class CtraderAdapter:
    transport: CtraderTransport
    client_id: str
    client_secret_provider: Callable[[], str]
    access_token_provider: Callable[[], str]
    ctid_trader_account_id: int
    account_alias: str = "ctrader_primary"
    venue: str = "ctrader"
    clock: Callable[[], int] = field(default=lambda: int(time.time() * 1000))
    fill_timeout_s: float = 10.0
    symbols: dict[str, SymbolInfo] = field(default_factory=dict)
    _authed: bool = False
    _money_digits: int = 2
    _currency: str = "USD"
    _last_spot: dict[int, tuple[Decimal, Decimal]] = field(default_factory=dict)

    # ------------------------------------------------------------ auth
    def _ensure_auth(self) -> None:
        if self._authed and self.transport.connected:
            return
        self.transport.connect()
        self.transport.call("ProtoOAApplicationAuthReq", {"clientId": self.client_id, "clientSecret": self.client_secret_provider()})
        self.transport.call("ProtoOAAccountAuthReq", {"ctidTraderAccountId": self.ctid_trader_account_id, "accessToken": self.access_token_provider()})
        self._authed = True
        if not self.symbols:
            self._load_symbols()

    def _load_symbols(self) -> None:
        _, lst = self.transport.call("ProtoOASymbolsListReq", {"ctidTraderAccountId": self.ctid_trader_account_id})
        light = {s["symbolId"]: s for s in lst.get("symbol", []) if s.get("enabled", True)}
        ids = list(light)
        for i in range(0, len(ids), 50):
            _, full = self.transport.call("ProtoOASymbolByIdReq", {"ctidTraderAccountId": self.ctid_trader_account_id, "symbolId": ids[i:i + 50]})
            for s in full.get("symbol", []):
                name = light[s["symbolId"]].get("symbolName", str(s["symbolId"]))
                self.symbols[name.replace("/", "").upper()] = SymbolInfo(s["symbolId"], name, int(s.get("digits", 5)), int(s.get("lotSize", 10_000_000)), int(s.get("minVolume", 1000)), int(s.get("stepVolume", 1000)), int(s.get("maxVolume", 10**12)))

    def symbol(self, name: str) -> SymbolInfo:
        try:
            return self.symbols[name.replace("/", "").upper()]
        except KeyError:
            raise VenueUnavailable(f"symbol {name} not available on this cTrader account") from None

    # ------------------------------------------------------------ reads
    def sync_account(self) -> AccountState:
        self._ensure_auth()
        _, r = self.transport.call("ProtoOATraderReq", {"ctidTraderAccountId": self.ctid_trader_account_id})
        t = r["trader"]
        self._money_digits = int(t.get("moneyDigits", 2))
        bal = Decimal(t["balance"]) / (Decimal(10) ** self._money_digits)
        unrealised = ZERO
        for p in self._positions_raw():
            sym = next((s for s in self.symbols.values() if s.symbol_id == p["tradeData"]["symbolId"]), None)
            spot = self._last_spot.get(p["tradeData"]["symbolId"])
            if sym and spot and p.get("price"):
                bid, ask = spot
                units = Decimal(p["tradeData"]["volume"]) / 100
                px = Decimal(str(p["price"]))
                unrealised += (bid - px) * units if p["tradeData"]["tradeSide"] == "BUY" else (px - ask) * units
        return AccountState(self.account_alias, bal + unrealised, bal, self._currency, True, t.get("accountType", "HEDGED") == "HEDGED", self.clock())

    def _positions_raw(self) -> list[dict]:
        _, r = self.transport.call("ProtoOAReconcileReq", {"ctidTraderAccountId": self.ctid_trader_account_id})
        return [p for p in r.get("position", []) if p.get("positionStatus") in ("POSITION_STATUS_OPEN", 1, None)]

    def positions(self) -> list[VenuePosition]:
        self._ensure_auth()
        out = []
        for p in self._positions_raw():
            td = p["tradeData"]
            sym = next((s for s in self.symbols.values() if s.symbol_id == td["symbolId"]), None)
            label = str(td.get("label", ""))
            out.append(VenuePosition(str(p["positionId"]), sym.name.replace("/", "").upper() if sym else str(td["symbolId"]), Direction.LONG if td["tradeSide"] == "BUY" else Direction.SHORT,
                                     sym.volume_to_lots(td["volume"]) if sym else Decimal(td["volume"]), Decimal(str(p.get("price", "0"))), Decimal(str(p["stopLoss"])) if p.get("stopLoss") else None,
                                     label[5:] if label.startswith("vati:") else "", LossModel.STOP_DISTANCE))
        return out

    def heartbeat(self, *, now_ms: int) -> Health:
        try:
            self._ensure_auth()
            self.transport.heartbeat_if_due()
            _, r = self.transport.call("ProtoOAGetAccountListByAccessTokenReq", {"accessToken": self.access_token_provider()})
            ok = any(a.get("ctidTraderAccountId") == self.ctid_trader_account_id for a in r.get("ctidTraderAccount", []))
            return Health(ok, 0, now_ms)
        except (VenueUnavailable, CtraderApiError):
            self._authed = False
            return Health(False, 0, now_ms)

    # ------------------------------------------------------------ writes
    def _wait_execution(self, client_order_id: str, wanted: tuple[str, ...]) -> Optional[dict]:
        def pred(name: str, body: dict) -> bool:
            if name != "ProtoOAExecutionEvent":
                return False
            o = body.get("order") or {}
            return str(o.get("clientOrderId", "")) == client_order_id and body.get("executionType") in wanted
        ev = self.transport.wait_event(pred, timeout_s=self.fill_timeout_s)
        return ev[1] if ev else None

    def submit(self, cmd: OrderCommand, *, now_ms: int) -> ExecutionReceipt:
        rej = lambda why: ExecutionReceipt(cmd.trade_intent_id, cmd.decision_hash, self.venue, "REJECTED", ZERO, None, cmd.entry_price, cmd.entry_price, cmd.entry_price, False, now_ms, now_ms, reject_reason=why).sealed()  # noqa: E731
        if cmd.protective_stop is None:
            return rej("cTrader orders require a protective stop in the same request")
        try:
            self._ensure_auth()
            sym = self.symbol(cmd.symbol)
        except VenueUnavailable as exc:
            return rej(str(exc))
        volume = sym.lots_to_volume(cmd.quantity)
        if volume < sym.min_volume:
            return rej(f"volume {volume} below venue minimum {sym.min_volume}")
        rel_sl = int((abs(cmd.entry_price - cmd.protective_stop) * PRICE_SCALE).to_integral_value())
        if rel_sl <= 0:
            return rej("protective stop equals entry")
        req = {"ctidTraderAccountId": self.ctid_trader_account_id, "symbolId": sym.symbol_id, "orderType": "MARKET" if cmd.entry_type == "MARKET" else "LIMIT", "tradeSide": "BUY" if cmd.direction is Direction.LONG else "SELL",
               "volume": volume, "label": f"vati:{cmd.trade_intent_id}"[:100], "clientOrderId": cmd.trade_intent_id[:50], "comment": f"vati {cmd.strategy_id}"[:512]}
        if cmd.entry_type == "MARKET":
            req["relativeStopLoss"] = rel_sl
            if cmd.targets:
                req["relativeTakeProfit"] = int((abs(cmd.targets[0] - cmd.entry_price) * PRICE_SCALE).to_integral_value())
        else:
            req["limitPrice"] = float(cmd.entry_price); req["stopLoss"] = float(cmd.protective_stop)
            if cmd.targets:
                req["takeProfit"] = float(cmd.targets[0])
        try:
            self.transport.call("ProtoOANewOrderReq", req)
        except CtraderApiError as exc:
            return rej(f"{exc.code}: {exc.description}")
        except VenueUnavailable as exc:
            return rej(f"venue unavailable: {exc}")
        ev = self._wait_execution(cmd.trade_intent_id[:50], ("ORDER_FILLED", "ORDER_PARTIAL_FILL", "ORDER_REJECTED", "ORDER_ACCEPTED"))
        if ev is None:
            return ExecutionReceipt(cmd.trade_intent_id, cmd.decision_hash, self.venue, "UNKNOWN", ZERO, None, cmd.entry_price, cmd.entry_price, cmd.entry_price, False, now_ms, now_ms, reject_reason="no execution event within timeout; reconcile before retrying").sealed()
        et = ev["executionType"]
        if et == "ORDER_REJECTED":
            return rej(str(ev.get("errorCode", "ORDER_REJECTED")))
        if et == "ORDER_ACCEPTED":
            ev2 = self._wait_execution(cmd.trade_intent_id[:50], ("ORDER_FILLED", "ORDER_PARTIAL_FILL", "ORDER_REJECTED"))
            if ev2 is None:
                return ExecutionReceipt(cmd.trade_intent_id, cmd.decision_hash, self.venue, "ACCEPTED", ZERO, None, cmd.entry_price, cmd.entry_price, cmd.entry_price, False, now_ms, now_ms, broker_order_id=str((ev.get("order") or {}).get("orderId", ""))).sealed()
            ev, et = ev2, ev2["executionType"]
            if et == "ORDER_REJECTED":
                return rej(str(ev.get("errorCode", "ORDER_REJECTED")))
        deal, pos = ev.get("deal") or {}, ev.get("position") or {}
        filled = sym.volume_to_lots(int(deal.get("filledVolume", 0)))
        px = Decimal(str(deal.get("executionPrice") or pos.get("price") or cmd.entry_price))
        sl = Decimal(str(pos["stopLoss"])) if pos.get("stopLoss") else None
        return ExecutionReceipt(cmd.trade_intent_id, cmd.decision_hash, self.venue, "FILLED" if et == "ORDER_FILLED" else "PARTIAL", filled, px, cmd.entry_price, px, cmd.entry_price, sl is not None,
                                int(deal.get("executionTimestamp", now_ms)), now_ms, broker_order_id=str(deal.get("orderId", "")), broker_position_id=str(pos.get("positionId") or deal.get("positionId", "")),
                                protective_stop_price=sl, fees=abs(Decimal(deal.get("commission", 0))) / (Decimal(10) ** int(deal.get("moneyDigits", self._money_digits)))).sealed()

    def modify_stop(self, position_id: str, new_stop: Decimal, *, now_ms: int) -> ExecutionReceipt:
        self._ensure_auth()
        cur = next((p for p in self._positions_raw() if str(p["positionId"]) == str(position_id)), None)
        if cur is None:
            return ExecutionReceipt("", "", self.venue, "REJECTED", ZERO, None, ZERO, ZERO, ZERO, False, now_ms, now_ms, broker_position_id=position_id, reject_reason="position not found").sealed()
        old = Decimal(str(cur["stopLoss"])) if cur.get("stopLoss") else None
        long = cur["tradeData"]["tradeSide"] == "BUY"
        if old is not None and ((long and new_stop < old) or (not long and new_stop > old)):
            return ExecutionReceipt("", "", self.venue, "REJECTED", ZERO, None, ZERO, ZERO, ZERO, False, now_ms, now_ms, broker_position_id=position_id, reject_reason="refusing to widen protective stop").sealed()
        try:
            self.transport.call("ProtoOAAmendPositionSLTPReq", {"ctidTraderAccountId": self.ctid_trader_account_id, "positionId": int(position_id), "stopLoss": float(new_stop), **({"takeProfit": float(cur["takeProfit"])} if cur.get("takeProfit") else {})})
        except CtraderApiError as exc:
            return ExecutionReceipt("", "", self.venue, "REJECTED", ZERO, None, ZERO, ZERO, ZERO, False, now_ms, now_ms, broker_position_id=position_id, reject_reason=f"{exc.code}: {exc.description}").sealed()
        return ExecutionReceipt("", "", self.venue, "ACCEPTED", ZERO, None, ZERO, ZERO, ZERO, True, now_ms, now_ms, broker_position_id=position_id, protective_stop_price=new_stop).sealed()

    def close(self, position_id: str, quantity: Optional[Decimal], *, now_ms: int, reason: str) -> ExecutionReceipt:
        self._ensure_auth()
        cur = next((p for p in self._positions_raw() if str(p["positionId"]) == str(position_id)), None)
        if cur is None:
            return ExecutionReceipt("", "", self.venue, "UNKNOWN", ZERO, None, ZERO, ZERO, ZERO, True, now_ms, now_ms, broker_position_id=position_id, reject_reason="position not found").sealed()
        sym = next((s for s in self.symbols.values() if s.symbol_id == cur["tradeData"]["symbolId"]), None)
        vol = sym.lots_to_volume(quantity) if (quantity is not None and sym) else int(cur["tradeData"]["volume"])
        try:
            self.transport.call("ProtoOAClosePositionReq", {"ctidTraderAccountId": self.ctid_trader_account_id, "positionId": int(position_id), "volume": vol})
        except CtraderApiError as exc:
            return ExecutionReceipt("", "", self.venue, "REJECTED", ZERO, None, ZERO, ZERO, ZERO, True, now_ms, now_ms, broker_position_id=position_id, reject_reason=f"{exc.code}: {exc.description}").sealed()
        ev = self.transport.wait_event(lambda n, b: n == "ProtoOAExecutionEvent" and str((b.get("deal") or {}).get("positionId", "")) == str(position_id) and b.get("executionType") in ("ORDER_FILLED", "ORDER_PARTIAL_FILL"), timeout_s=self.fill_timeout_s)
        if ev is None:
            return ExecutionReceipt("", "", self.venue, "UNKNOWN", ZERO, None, ZERO, ZERO, ZERO, True, now_ms, now_ms, broker_position_id=position_id, reject_reason=f"{reason}; no close execution within timeout").sealed()
        deal = ev[1].get("deal") or {}
        return ExecutionReceipt("", "", self.venue, "FILLED", sym.volume_to_lots(int(deal.get("filledVolume", vol))) if sym else Decimal(vol), Decimal(str(deal.get("executionPrice", "0"))), ZERO, ZERO, ZERO, True, now_ms, now_ms, broker_position_id=position_id, reject_reason=reason).sealed()

    # ------------------------------------------------------------ market data
    def spot(self, symbol: str) -> Optional[tuple[Decimal, Decimal]]:
        self._ensure_auth()
        sym = self.symbol(symbol)
        for name, body in self.transport.drain_events():
            if name == "ProtoOASpotEvent" and body.get("bid") and body.get("ask"):
                self._last_spot[body["symbolId"]] = (Decimal(body["bid"]) / PRICE_SCALE, Decimal(body["ask"]) / PRICE_SCALE)
        return self._last_spot.get(sym.symbol_id)

    def subscribe_spots(self, symbol: str) -> None:
        self._ensure_auth()
        self.transport.call("ProtoOASubscribeSpotsReq", {"ctidTraderAccountId": self.ctid_trader_account_id, "symbolId": [self.symbol(symbol).symbol_id]})
