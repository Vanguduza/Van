"""cTrader Open API venue adapter (Rev 5 route 1: Linux-native FX/CFD execution).

Volumes are in cents of units (lots × lotSize), prices in absolute doubles except
where the API uses 1/100000 units (spots, relative SL). A MARKET order carries its
protective stop as `relativeStopLoss` in the same request (absolute SL is not accepted
on MARKET orders by the API), so the "stop in the same request" doctrine holds. Stops
only tighten. The label carries the intent id so reconciliation can find orphans."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_DOWN, localcontext
from typing import Any, Callable, Optional, ClassVar

from vati.execution.base import AccountState, ExecutionReceipt, Health, OrderCommand, VenuePosition, VenueUnavailable
from vati.execution.ctrader.transport import CtraderApiError, CtraderTransport
from vati.execution.entry_deadline import EntryNotSent, require_entry_deadline
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
    contract_revision: str | None = None

    def lots_to_volume(self, lots: Decimal) -> int:
        vol = int((lots * Decimal(self.lot_size_cents)).to_integral_value(rounding=ROUND_DOWN))
        if self.step_volume:
            vol -= vol % self.step_volume
        return vol

    def volume_to_lots(self, volume: int) -> Decimal:
        # Native steps and partial fills can be smaller than a centilot. The
        # broker's actual quantity must not be rounded to the requested UI step.
        return Decimal(volume) / Decimal(self.lot_size_cents)


@dataclass
class CtraderAdapter:
    #: P1-TRADE-EXEC-004: the entry types this venue really executes (orderType is MARKET or LIMIT; no stop-entry request is built).
    #: The router refuses anything else instead of sending it as a different order.
    supported_entry_types: ClassVar[tuple] = ("MARKET", "LIMIT", "PASSIVE_LIMIT")
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
    _auth_connection: int | None = None
    _symbol_snapshot_valid: bool = True
    _symbol_connection: int | None = None
    _money_digits: int = 2
    _currency: str = "USD"
    _last_spot: dict[int, tuple[Decimal, Decimal]] = field(default_factory=dict)

    # ------------------------------------------------------------ auth
    def _auth_is_current(self) -> bool:
        return (self._authed and self.transport.connected
                and self._auth_connection == getattr(self.transport, "connection_id", None))

    def _authenticate(self) -> None:
        """Authenticate one connection without requiring market metadata reads."""
        if self._auth_is_current():
            return
        from vati.execution.ctrader.feed import native_integer
        self._authed = False
        self._auth_connection = None
        self._symbol_snapshot_valid = False
        self._last_spot.clear()
        try:
            account = native_integer(self.ctid_trader_account_id, minimum=1)
            self.transport.connect()
            connection = getattr(self.transport, "connection_id", None)
            kind, body = self.transport.call("ProtoOAApplicationAuthReq", {"clientId": self.client_id, "clientSecret": self.client_secret_provider()})
            if (kind != "ProtoOAApplicationAuthRes" or not isinstance(body, dict)
                    or not self.transport.connected or getattr(self.transport, "connection_id", None) != connection):
                raise ValueError("application authentication response mismatch")
            kind, body = self.transport.call("ProtoOAAccountAuthReq", {"ctidTraderAccountId": account, "accessToken": self.access_token_provider()})
            if (kind != "ProtoOAAccountAuthRes" or not isinstance(body, dict)
                    or native_integer(body["ctidTraderAccountId"], minimum=1) != account
                    or not self.transport.connected or getattr(self.transport, "connection_id", None) != connection):
                raise ValueError("account authentication response mismatch")
        except (KeyError, TypeError, ValueError) as exc:
            raise VenueUnavailable("cTrader native authentication response or connection scope unavailable") from exc
        self._auth_connection = connection
        self._authed = True

    def _ensure_auth(self) -> None:
        if self._auth_is_current():
            if not self._symbol_snapshot_valid:
                self._load_symbols()
            return
        self._authenticate()
        self._load_symbols()

    def _load_symbols(self) -> None:
        from vati.core.canonical import canonical_hash
        from vati.execution.ctrader.feed import native_integer

        # Publish one complete native registry. A failed refresh retains old bytes
        # for diagnosis but fences their use until a successful native refresh.
        self._symbol_snapshot_valid = False
        try:
            connection = getattr(self.transport, "connection_id", None)
            account = native_integer(self.ctid_trader_account_id,minimum=1)
            kind, response = self.transport.call("ProtoOASymbolsListReq", {"ctidTraderAccountId": account})
            if (kind != "ProtoOASymbolsListRes" or not isinstance(response,dict)
                    or native_integer(response["ctidTraderAccountId"],minimum=1) != account):
                raise ValueError("native symbol list scope mismatch")
            rows=response.get("symbol",[])
            if not isinstance(rows,list): raise ValueError("native symbol list invalid")
            light, aliases = {}, set()
            for row in rows:
                identity=native_integer(row["symbolId"],minimum=1)
                if identity in light: raise ValueError("duplicate native symbol")
                # An omitted optional proto2 bool defaults to false; it must
                # never manufacture permission to use an invisible instrument.
                if type(row.get("enabled",False)) is not bool: raise ValueError("native visibility invalid")
                light[identity]=row
                if not row.get("enabled",False):continue
                name=row["symbolName"]
                if (not isinstance(name,str) or not name.strip() or len(name)>256
                        or any(ord(c)<32 for c in name)):raise ValueError("native symbol name unavailable")
                alias=name.replace("/","").upper()
                if not alias or alias in aliases:raise ValueError("native symbol alias collision")
                aliases.add(alias)
            enabled={k:v for k,v in light.items() if v.get("enabled",False)}
            ids=list(enabled); current={}
            for offset in range(0,len(ids),50):
                requested=ids[offset:offset+50]
                kind, response=self.transport.call("ProtoOASymbolByIdReq", {"ctidTraderAccountId":account,"symbolId":requested})
                if (kind!="ProtoOASymbolByIdRes" or not isinstance(response,dict)
                        or native_integer(response["ctidTraderAccountId"],minimum=1)!=account):
                    raise ValueError("native symbol detail scope mismatch")
                details=response.get("symbol",[])
                if not isinstance(details,list):raise ValueError("native symbol details unavailable")
                seen=set()
                for row in details:
                    identity=native_integer(row["symbolId"],minimum=1)
                    if identity not in requested or identity in seen:raise ValueError("native symbol detail identity mismatch")
                    seen.add(identity)
                    digits=native_integer(row["digits"],maximum=18)
                    lot=native_integer(row["lotSize"],minimum=1)
                    minimum=native_integer(row["minVolume"],minimum=1)
                    step=native_integer(row["stepVolume"],minimum=1)
                    maximum=native_integer(row["maxVolume"],minimum=minimum)
                    if minimum>maximum or step>maximum:raise ValueError("native volume contract incoherent")
                    original=enabled[identity];name=original["symbolName"];alias=name.replace("/","").upper()
                    revision=canonical_hash({"schema":"vati.ctrader-symbol/1","native_account_id":account,
                        "transport_host":getattr(self.transport,"host",None),"light":original,"detail":row})
                    current[alias]=SymbolInfo(identity,name,digits,lot,minimum,step,maximum,revision)
                if seen!=set(requested):raise ValueError("native symbol details incomplete")
            if getattr(self.transport, "connection_id", None) != connection:
                raise ValueError("native symbol connection changed during refresh")
            self.symbols=current
            self._symbol_connection=connection
            self._symbol_snapshot_valid=True
        except (KeyError,TypeError,ValueError,ArithmeticError) as exc:
            raise VenueUnavailable("cTrader native symbol registry unavailable; refresh required") from exc

    def symbol(self, name: str) -> SymbolInfo:
        if (not self._symbol_snapshot_valid
                or self._symbol_connection != getattr(self.transport,"connection_id",None)):
            raise VenueUnavailable("cTrader native symbol registry unavailable; refresh required")
        try:
            return self.symbols[name.replace("/", "").upper()]
        except KeyError:
            raise VenueUnavailable(f"symbol {name} not available on this cTrader account") from None

    # ------------------------------------------------------------ reads
    def funding_reader(self):
        # An independent connection and adapter state keep slow cash history off
        # the protective/order socket. It exposes only the read operation/close.
        transport=CtraderTransport(host=self.transport.host,port=self.transport.port,
            timeout_s=self.transport.timeout_s,connector=self.transport._connector)
        adapter=CtraderAdapter(transport,self.client_id,self.client_secret_provider,self.access_token_provider,
            self.ctid_trader_account_id,self.account_alias,self.venue,clock=self.clock)
        class CashReader:
            def cash_movements(self,**window):
                return adapter.cash_movements(**window)
            def deal_history(self,**window):
                return adapter.deal_history(**window)
            def close(self):transport.close()
        return CashReader()

    def deal_history(self,*,from_ms,to_ms):
        from vati.funding.deals import collect_native_deals
        return collect_native_deals(self,from_ms=from_ms,to_ms=to_ms)

    def _native_trader_identity(self):
        name, r = self.transport.call("ProtoOATraderReq", {"ctidTraderAccountId": self.ctid_trader_account_id})
        try:
            if name != "ProtoOATraderRes":raise ValueError()
            t = dict(r["trader"])
            digits=t['moneyDigits'];deposit=t['depositAssetId'];balance=t['balance']
            if (type(self.ctid_trader_account_id) is not int or self.ctid_trader_account_id<=0
                or type(r['ctidTraderAccountId']) is not int or type(t['ctidTraderAccountId']) is not int
                or r['ctidTraderAccountId']!=self.ctid_trader_account_id or t['ctidTraderAccountId']!=self.ctid_trader_account_id
                or type(digits) is not int or not 0<=digits<=18 or type(deposit) is not int or deposit<=0
                or type(balance) is not int):raise ValueError()
            asset_name,assets=self.transport.call('ProtoOAAssetListReq',{'ctidTraderAccountId':self.ctid_trader_account_id})
            if asset_name!='ProtoOAAssetListRes' or type(assets['ctidTraderAccountId']) is not int or assets['ctidTraderAccountId']!=self.ctid_trader_account_id or not isinstance(assets.get('asset'),list):raise ValueError()
            matches=[a for a in assets['asset'] if isinstance(a,dict) and type(a.get('assetId')) is int and a.get('assetId')==deposit]
            if len(matches)!=1 or not isinstance(matches[0].get('name'),str) or not matches[0]['name'].strip():raise ValueError()
            self._currency=matches[0]['name'];self._money_digits=digits
        except (KeyError,TypeError,ValueError,ArithmeticError):
            raise VenueUnavailable('cTrader native account identity, money precision or deposit currency unavailable') from None
        return t

    def sync_account(self) -> AccountState:
        from vati.funding.native import NativeAccountMark,native_int,native_money
        self._ensure_auth()
        t = self._native_trader_identity()
        bal = native_money(t['balance'],self._money_digits)
        unrealised = self._native_unrealised(margin_mode=t.get("totalMarginCalculationType"))
        # Separate native reads are not an atomic account snapshot. Refuse a
        # visible funds/currency change across the position mark instead of
        # combining old balance with newer PnL and reporting it verified.
        try:
            name,latest=self.transport.call('ProtoOATraderReq',{'ctidTraderAccountId':self.ctid_trader_account_id})
            if (name!='ProtoOATraderRes' or type(latest.get('ctidTraderAccountId')) is not int
                or latest['ctidTraderAccountId']!=self.ctid_trader_account_id):raise ValueError()
            fields=('ctidTraderAccountId','balance','moneyDigits','depositAssetId')
            if any(type(latest['trader'][k]) is not int or latest['trader'][k]!=t[k] for k in fields):raise ValueError()
            for key in ('balanceVersion','registrationTimestamp','managerBonus','ibBonus','nonWithdrawableBonus'):
                minimum=0 if key in {'balanceVersion','registrationTimestamp'} else -(2**63)
                if key in t:native_int(t[key],minimum=minimum)
                if key in latest['trader']:native_int(latest['trader'][key],minimum=minimum)
                if latest['trader'].get(key)!=t.get(key) or (key in latest['trader'])!=(key in t):raise ValueError()
            for key in ('totalMarginCalculationType','accountType','isLimitedRisk','limitedRiskMarginCalculationStrategy'):
                if latest['trader'].get(key)!=t.get(key) or type(latest['trader'].get(key)) is not type(t.get(key)):
                    raise ValueError()
        except (CtraderApiError,KeyError,TypeError,ValueError):
            raise VenueUnavailable('cTrader native funds changed during position PnL observation; refresh required') from None
        with localcontext() as context:
            context.prec=80
            equity=bal+unrealised
        at=native_int(self.clock(),minimum=0)
        from vati.execution.ctrader.transport import DEMO_HOST,LIVE_HOST
        environment={DEMO_HOST:'DEMO',LIVE_HOST:'LIVE'}.get(getattr(self.transport,'host',None))
        mark=None
        if environment:
            bonuses=[native_money(t[k],self._money_digits) if k in t else None for k in ('managerBonus','ibBonus','nonWithdrawableBonus')]
            mark=NativeAccountMark('CTRADER',environment,self.account_alias,self.ctid_trader_account_id,t['depositAssetId'],self._currency,
                at,bal,equity,t.get('balanceVersion'),*bonuses,registered_at_ms=t.get('registrationTimestamp'))
        used = getattr(self, "_native_used_margin", None)
        with localcontext() as context:
            context.prec = 80
            free = equity - used if used is not None else None
            level = equity / used * Decimal("100") if used is not None and used > 0 else None
        # cTrader reports per-position usedMargin, not an account free-margin
        # field. These bounds use that native margin and risk equity excluding
        # separate bonuses; they are not settled money or a broker margin quote.
        return AccountState(self.account_alias, equity, bal, self._currency, True,
            t.get("accountType", "HEDGED") == "HEDGED", at,
            funding_mark=mark,used_margin=used,free_margin=free,margin_level_pct=level)

    def cash_movements(self, *, from_ms: int, to_ms: int):
        """Read one documented native history window, with no payment operation.

        cTrader's vendored protocol limits each request to one week. Every returned
        row is retained or the statement is refused; unknown operation meanings stay
        explicit for the accounting consumer. Provider notes are not copied.
        """
        from vati.funding.native import NativeCashMovement,NativeCashStatement,native_int,native_money
        from vati.execution.ctrader.protoschema import SCHEMA
        try:
            observed=native_int(self.clock(),minimum=0)
            native_int(from_ms,minimum=0);native_int(to_ms,minimum=0,maximum=2147483646000)
            native_int(self.ctid_trader_account_id,minimum=1)
            from vati.execution.ctrader.transport import DEMO_HOST,LIVE_HOST
            environment={DEMO_HOST:'DEMO',LIVE_HOST:'LIVE'}.get(getattr(self.transport,'host',None))
            if environment is None:raise ValueError()
            if from_ms>to_ms or to_ms-from_ms>604800000 or to_ms>observed:raise ValueError()
        except (TypeError,ValueError):
            raise VenueUnavailable('cTrader cash history requires an exact closed past window of at most one week') from None
        self._authenticate()
        try:
            original=self._native_trader_identity();currency=self._currency
            if 'registrationTimestamp' in original and from_ms<native_int(original['registrationTimestamp'],minimum=0):raise ValueError()
            name,response=self.transport.call('ProtoOACashFlowHistoryListReq',{'ctidTraderAccountId':self.ctid_trader_account_id,
                'fromTimestamp':from_ms,'toTimestamp':to_ms})
            if (name!='ProtoOACashFlowHistoryListRes' or type(response['ctidTraderAccountId']) is not int
                or response['ctidTraderAccountId']!=self.ctid_trader_account_id):raise ValueError()
            rows=response.get('depositWithdraw',[])
            if not isinstance(rows,list):raise ValueError()
            movements=[];identities={}
            operations=SCHEMA.enum_reverse['ProtoOAChangeBalanceType']
            for raw in rows:
                identity=native_int(raw['balanceHistoryId'],minimum=1)
                at=native_int(raw['changeBalanceTimestamp'],minimum=0)
                if not from_ms<=at<=to_ms:raise ValueError()
                digits=native_int(raw['moneyDigits'],minimum=0,maximum=18)
                operation=raw['operationType']
                if type(operation) is int:
                    native_int(operation,minimum=0,maximum=2**31-1)
                    operation=operations.get(operation,'NATIVE_UNKNOWN:'+str(operation))
                elif not isinstance(operation,str) or operation not in SCHEMA.enums['ProtoOAChangeBalanceType']:
                    raise ValueError()
                version=raw.get('balanceVersion')
                if version is not None:native_int(version,minimum=0)
                entry=NativeCashMovement(identity,operation,native_money(raw['delta'],digits),native_money(raw['balance'],digits),
                    native_money(raw['equity'],digits) if 'equity' in raw else None,version,at,digits)
                if identity in identities:
                    if identities[identity]!=entry:raise ValueError()
                    continue
                identities[identity]=entry;movements.append(entry)
            latest=self._native_trader_identity()
            if latest['depositAssetId']!=original['depositAssetId'] or self._currency!=currency:raise ValueError()
            received=native_int(self.clock(),minimum=observed)
            return NativeCashStatement('CTRADER',environment,self.account_alias,self.ctid_trader_account_id,original['depositAssetId'],currency,
                from_ms,to_ms,received,tuple(movements))
        except (CtraderApiError,KeyError,TypeError,ValueError,ArithmeticError):
            raise VenueUnavailable('cTrader cash history identity, native precision or complete statement unavailable') from None

    def _native_unrealised(self, *, margin_mode=None) -> Decimal:
        """Broker net mark in deposit currency, never a missing-quote zero.

        The native response defines its own decimal exponent and excludes
        potential closing commission. This is current equity, not settled PnL.
        A changed or incomplete position set needs a fresh read, not a guess.
        """
        self._native_used_margin = None
        try:
            positions = self._positions_raw()
            expected = [p['positionId'] for p in positions]
            if (any(type(i) is not int or not 0<i<2**63 for i in expected)
                or len(set(expected))!=len(expected)):raise ValueError()
            name,r = self.transport.call('ProtoOAGetPositionUnrealizedPnLReq',
                {'ctidTraderAccountId':self.ctid_trader_account_id})
            if (name!='ProtoOAGetPositionUnrealizedPnLRes' or not isinstance(r,dict)
                or type(r.get('ctidTraderAccountId')) is not int
                or r['ctidTraderAccountId']!=self.ctid_trader_account_id):raise ValueError()
            digits=r['moneyDigits'];rows=r.get('positionUnrealizedPnL',[])
            if type(digits) is not int or not 0<=digits<=18 or not isinstance(rows,list):raise ValueError()
            observed=[];total=0
            for row in rows:
                if not isinstance(row,dict):raise ValueError()
                pid=row['positionId'];net=row['netUnrealizedPnL'];gross=row['grossUnrealizedPnL']
                if (type(pid) is not int or not 0<pid<2**63
                    or any(type(v) is not int or not -(2**63)<=v<2**63 for v in (net,gross))):raise ValueError()
                observed.append(pid);total+=net
            if len(set(observed))!=len(observed) or set(observed)!=set(expected):raise ValueError()
            after = self._positions_raw()
            if (len(after) != len(positions) or len({p['positionId'] for p in after}) != len(after)
                or {p['positionId']:p for p in after} != {p['positionId']:p for p in positions}):
                raise ValueError()
            try:
                self._native_used_margin = self._position_margin(positions, margin_mode)
            except (KeyError,TypeError,ValueError,ArithmeticError):
                self._native_used_margin = None
            return Decimal(total)/(Decimal(10)**digits)
        except (CtraderApiError,KeyError,TypeError,ValueError,ArithmeticError):
            raise VenueUnavailable('cTrader native deposit-currency position PnL unavailable or inconsistent') from None

    @staticmethod
    def _position_margin(positions, mode):
        """Documented per-symbol aggregation using the Open API enum values.

        Algo's enum has different integer values: its formulas are referenced
        by name, never by copying those numeric values into this protocol.
        """
        from vati.funding.native import native_int
        if not positions:
            return ZERO
        if type(mode) is int:
            mode = {0:"MAX",1:"SUM",2:"NET"}.get(mode)
        if type(mode) is not str or mode not in {"MAX","SUM","NET"}:
            raise ValueError("native total margin calculation mode unavailable")
        buckets = {}
        with localcontext() as context:
            context.prec = 80
            for position in positions:
                value = native_int(position['usedMargin'],minimum=0,maximum=2**64-1)
                digits = native_int(position['moneyDigits'],minimum=0,maximum=18)
                margin = Decimal((0,tuple(map(int,str(value))),-digits))
                trade = position['tradeData']
                symbol = native_int(trade['symbolId'],minimum=1)
                side = trade['tradeSide']
                if type(side) is int:side = {1:"BUY",2:"SELL"}.get(side)
                if type(side) is not str or side not in {"BUY","SELL"}:raise ValueError()
                bucket = buckets.setdefault(symbol,{"BUY":ZERO,"SELL":ZERO})
                bucket[side] += margin
            if mode == "SUM":return sum((b['BUY']+b['SELL'] for b in buckets.values()),ZERO)
            if mode == "MAX":return sum((max(b['BUY'],b['SELL']) for b in buckets.values()),ZERO)
            return sum((abs(b['BUY']-b['SELL']) for b in buckets.values()),ZERO)

    def _positions_raw(self) -> list[dict]:
        return [p for p in self._reconcile_raw()['position'] if p.get("positionStatus") in ("POSITION_STATUS_OPEN", 1, None)]

    def _reconcile_raw(self):
        _, r = self.transport.call('ProtoOAReconcileReq',{'ctidTraderAccountId':self.ctid_trader_account_id})
        if (not isinstance(r,dict) or r.get('ctidTraderAccountId')!=self.ctid_trader_account_id
            or not isinstance(r.get('position',[]),list) or not isinstance(r.get('order',[]),list)):
            raise VenueUnavailable('cTrader native positions or pending orders unavailable')
        return {'position':r.get('position',[]),'order':r.get('order',[])}

    def orders(self) -> list[dict]:
        self._ensure_auth()
        return self._reconcile_raw()['order']

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
    def _unknown(self, now_ms: int, reason: str, *, cmd: Optional[OrderCommand] = None,
                 position_id: str = "") -> ExecutionReceipt:
        price = cmd.entry_price if cmd is not None else ZERO
        return ExecutionReceipt(cmd.trade_intent_id if cmd else "", cmd.decision_hash if cmd else "",
            self.venue, "UNKNOWN", ZERO, None, price, price, price, False, now_ms, now_ms,
            broker_position_id=position_id, reject_reason=reason).sealed()

    def _wait_execution(self, client_order_id: str, wanted: tuple[str, ...]) -> Optional[dict]:
        def pred(name: str, body: dict) -> bool:
            if (name != "ProtoOAExecutionEvent" or type(body.get('ctidTraderAccountId')) is not int
                or body['ctidTraderAccountId'] != self.ctid_trader_account_id):
                return False
            o = body.get("order") or {}
            return str(o.get("clientOrderId", "")) == client_order_id and body.get("executionType") in wanted
        ev = self.transport.wait_event(pred, timeout_s=self.fill_timeout_s)
        return ev[1] if ev else None

    def submit(self, cmd: OrderCommand, *, now_ms: int) -> ExecutionReceipt:
        rej = lambda why: ExecutionReceipt(cmd.trade_intent_id, cmd.decision_hash, self.venue, "REJECTED", ZERO, None, cmd.entry_price, cmd.entry_price, cmd.entry_price, False, now_ms, now_ms, reject_reason=why).sealed()  # noqa: E731
        if cmd.account_alias != self.account_alias or cmd.venue != self.venue:
            return rej('native command target differs from the configured account or venue; not dispatched')
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
        if volume > sym.max_volume:
            return rej(f"volume {volume} above venue maximum {sym.max_volume}")
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
            if cmd.expires_at_ms is None:
                self.transport.call("ProtoOANewOrderReq", req)
            else:
                require_entry_deadline(cmd.expires_at_ms,self.clock)
                bounded=getattr(self.transport,'call_entry',None)
                if not callable(bounded):
                    raise EntryNotSent('native transport cannot enforce the explicit entry deadline; not sent')
                bounded("ProtoOANewOrderReq",req,expires_at_ms=cmd.expires_at_ms,clock=self.clock)
        except EntryNotSent as exc:
            return rej(str(exc))
        except CtraderApiError as exc:
            return rej(f"{exc.code}: {exc.description}")
        except VenueUnavailable as exc:
            return self._unknown(now_ms,"native entry reply unavailable; reconcile original before retrying",cmd=cmd)
        try:
            ev = self._wait_execution(cmd.trade_intent_id[:50], ("ORDER_FILLED", "ORDER_PARTIAL_FILL", "ORDER_REJECTED", "ORDER_ACCEPTED"))
        except (VenueUnavailable,CtraderApiError):
            return self._unknown(now_ms,"native entry event unavailable; reconcile original before retrying",cmd=cmd)
        if ev is None:
            return ExecutionReceipt(cmd.trade_intent_id, cmd.decision_hash, self.venue, "UNKNOWN", ZERO, None, cmd.entry_price, cmd.entry_price, cmd.entry_price, False, now_ms, now_ms, reject_reason="no execution event within timeout; reconcile before retrying").sealed()
        et = ev["executionType"]
        if et == "ORDER_REJECTED":
            return rej(str(ev.get("errorCode", "ORDER_REJECTED")))
        if et == "ORDER_ACCEPTED":
            try:
                ev2 = self._wait_execution(cmd.trade_intent_id[:50], ("ORDER_FILLED", "ORDER_PARTIAL_FILL", "ORDER_REJECTED"))
            except (VenueUnavailable,CtraderApiError):
                return self._unknown(now_ms,"native fill event unavailable; reconcile original before retrying",cmd=cmd)
            if ev2 is None:
                return ExecutionReceipt(cmd.trade_intent_id, cmd.decision_hash, self.venue, "ACCEPTED", ZERO, None, cmd.entry_price, cmd.entry_price, cmd.entry_price, False, now_ms, now_ms, broker_order_id=str((ev.get("order") or {}).get("orderId", ""))).sealed()
            ev, et = ev2, ev2["executionType"]
            if et == "ORDER_REJECTED":
                return rej(str(ev.get("errorCode", "ORDER_REJECTED")))
        deal, pos = ev.get("deal") or {}, ev.get("position") or {}
        try:
            native_quantity=deal['filledVolume'];px=Decimal(str(deal['executionPrice']))
            order=ev.get('order') or {};pid=deal['positionId'];oid=deal['orderId']
            if (type(native_quantity) is not int or not 0<native_quantity<=volume or not px.is_finite() or px<=0
                or type(pid) is not int or not 0<pid<2**63 or type(oid) is not int or not 0<oid<2**63
                or deal.get('symbolId')!=sym.symbol_id or order.get('orderId')!=oid
                or (pos and pos.get('positionId')!=pid)):raise ValueError()
            filled=sym.volume_to_lots(native_quantity)
        except (KeyError,TypeError,ValueError,ArithmeticError):
            return self._unknown(now_ms,"native entry money/quantity identity incomplete",cmd=cmd)
        try:
            sl = Decimal(str(pos['stopLoss'])) if pos.get('stopLoss') else None
            if sl is not None and (not sl.is_finite() or sl<=0):sl=None
        except (TypeError,ValueError,ArithmeticError):sl=None
        state='FILLED' if et=='ORDER_FILLED' and native_quantity==volume else 'PARTIAL'
        return ExecutionReceipt(cmd.trade_intent_id, cmd.decision_hash, self.venue, state, filled, px, cmd.entry_price, px, cmd.entry_price, sl is not None,
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
        except VenueUnavailable:
            return self._unknown(now_ms,"native stop reply unavailable; reconcile original before retrying",position_id=position_id)
        try:
            confirmed=next((p for p in self._positions_raw() if str(p['positionId'])==str(position_id)),None)
            actual=Decimal(str(confirmed['stopLoss'])) if confirmed and confirmed.get('stopLoss') else None
            if actual is None or not actual.is_finite() or actual!=new_stop:
                return self._unknown(now_ms,"native stop has not been observed at the requested price",position_id=position_id)
        except (VenueUnavailable,CtraderApiError,KeyError,TypeError,ValueError,ArithmeticError):
            return self._unknown(now_ms,"native stop readback unavailable; reconcile original before retrying",position_id=position_id)
        return ExecutionReceipt("", "", self.venue, "ACCEPTED", ZERO, None, ZERO, ZERO, ZERO, True, now_ms, now_ms, broker_position_id=position_id, protective_stop_price=new_stop).sealed()

    def close(self, position_id: str, quantity: Optional[Decimal], *, now_ms: int, reason: str) -> ExecutionReceipt:
        self._ensure_auth()
        cur = next((p for p in self._positions_raw() if str(p["positionId"]) == str(position_id)), None)
        if cur is None:
            return self._unknown(now_ms,"position not found; flat outcome unproven",position_id=position_id)
        sym = next((s for s in self.symbols.values() if s.symbol_id == cur["tradeData"]["symbolId"]), None)
        if sym is None:
            return self._unknown(now_ms,"native close quantity unit unavailable",position_id=position_id)
        vol = sym.lots_to_volume(quantity) if (quantity is not None and sym) else int(cur["tradeData"]["volume"])
        if vol<=0 or vol>int(cur['tradeData']['volume']):
            return ExecutionReceipt("", "", self.venue, "REJECTED", ZERO, None, ZERO, ZERO, ZERO, False,
                now_ms,now_ms,broker_position_id=position_id,reject_reason="invalid native close volume; not dispatched").sealed()
        try:
            name,reply=self.transport.call("ProtoOAClosePositionReq", {"ctidTraderAccountId": self.ctid_trader_account_id, "positionId": int(position_id), "volume": vol})
        except CtraderApiError as exc:
            return ExecutionReceipt("", "", self.venue, "REJECTED", ZERO, None, ZERO, ZERO, ZERO, False, now_ms, now_ms, broker_position_id=position_id, reject_reason=f"{exc.code}: {exc.description}").sealed()
        except VenueUnavailable:
            return self._unknown(now_ms,"native close reply unavailable; reconcile original before retrying",position_id=position_id)
        order_id=(reply.get('order') or {}).get('orderId')
        if (name!='ProtoOAExecutionEvent' or type(reply.get('ctidTraderAccountId')) is not int
            or reply['ctidTraderAccountId']!=self.ctid_trader_account_id or type(order_id) is not int or order_id<=0):
            return self._unknown(now_ms,"native close admission identity unavailable",position_id=position_id)
        def matches(n,b):
            deal=b.get('deal') or {};order=b.get('order') or {}
            return (n=='ProtoOAExecutionEvent' and type(b.get('ctidTraderAccountId')) is int
                and b['ctidTraderAccountId']==self.ctid_trader_account_id and type(deal.get('positionId')) is int
                and str(deal['positionId'])==str(position_id) and type(deal.get('orderId')) is int
                and deal['orderId']==order_id and order.get('closingOrder') is True
                and order.get('orderId')==order_id and b.get('executionType') in ('ORDER_FILLED','ORDER_PARTIAL_FILL'))
        try:
            ev=(name,reply) if matches(name,reply) else self.transport.wait_event(matches,timeout_s=self.fill_timeout_s)
        except (VenueUnavailable,CtraderApiError):
            return self._unknown(now_ms,"native close event unavailable; reconcile original before retrying",position_id=position_id)
        if ev is None:
            return self._unknown(now_ms,f"{reason}; no bound close execution within timeout",position_id=position_id)
        deal = ev[1].get("deal") or {}
        try:
            filled=deal['filledVolume'];price=Decimal(str(deal['executionPrice']))
            if (type(filled) is not int or not 0<filled<=vol or not price.is_finite() or price<=0
                or deal.get('symbolId')!=sym.symbol_id):raise ValueError()
        except (KeyError,TypeError,ValueError,ArithmeticError):
            return self._unknown(now_ms,"native close money/quantity facts incomplete",position_id=position_id)
        state='FILLED' if ev[1]['executionType']=='ORDER_FILLED' and filled==vol else 'PARTIAL'
        remaining=ev[1].get('position') or {};stop=remaining.get('stopLoss')
        protected=filled==int(cur['tradeData']['volume'])
        if not protected and remaining.get('positionId')==int(position_id):
            try:protected=stop is not None and Decimal(str(stop)).is_finite() and Decimal(str(stop))>0
            except (TypeError,ValueError,ArithmeticError):protected=False
        return ExecutionReceipt("", "", self.venue, state, sym.volume_to_lots(filled), price, ZERO, ZERO, ZERO,
            protected,now_ms,now_ms,broker_order_id=str(order_id),broker_position_id=position_id,reject_reason=reason).sealed()

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
