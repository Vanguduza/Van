"""cTrader Open API venue adapter (Rev 5 route 1: Linux-native FX/CFD execution).

Volumes are in cents of units (lots × lotSize), prices in absolute doubles except
where the API uses 1/100000 units (spots, relative SL). A MARKET order carries its
protective stop as `relativeStopLoss` in the same request (absolute SL is not accepted
on MARKET orders by the API), so the "stop in the same request" doctrine holds. Stops
only tighten. The label carries the intent id so reconciliation can find orphans."""

from __future__ import annotations

import time
import threading
import json
from collections import OrderedDict
from dataclasses import dataclass, field, replace
from decimal import Decimal, ROUND_DOWN, localcontext
from vati.core.decimal_context import native_decimal_context
from typing import Any, Callable, Optional, ClassVar

from vati.execution.base import AccountState, ExecutionReceipt, Health, OrderCommand, VenuePosition, VenueUnavailable
from vati.execution.ctrader.transport import CtraderApiError, CtraderTransport, CtraderReadTransport
from vati.execution.ctrader.contracts import NativeSymbolContract
from vati.execution.ctrader.spots import SpotBook
from vati.execution.ctrader.depth import DepthBook
from vati.execution.entry_deadline import EntryNotSent, require_entry_deadline
from vati.risk.contracts import Direction, LossModel

ZERO = Decimal("0")
PRICE_SCALE = Decimal("100000")


def _recorded_commission(deal: dict) -> Decimal | None:
    """Decode only a charge with its own native precision, never account fallback.

    This retains the adapter's existing magnitude convention. It is a recorded
    charge, not a claim of complete fees, sign qualification or settlement.
    Invalid optional metadata must not erase an independently observed fill.
    """
    from vati.funding.native import native_int, native_money
    try:
        raw = native_int(deal['commission'])
        digits = native_int(deal['moneyDigits'], minimum=0, maximum=18)
        # copy_abs is exact even for the minimum int64 and under caller traps.
        return native_money(raw, digits).copy_abs()
    except (KeyError, TypeError, ValueError):
        return None


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
    native_contract: NativeSymbolContract | None = None

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
    _selected_native_symbols: tuple[int, ...] | None = None
    _money_digits: int = 2
    _currency: str = "USD"
    _last_spot: dict[int, tuple[Decimal, Decimal]] = field(default_factory=dict)
    _spot_book: SpotBook = field(default_factory=SpotBook)
    _spot_subscriptions: set = field(default_factory=set)
    _spot_control_states: dict = field(default_factory=dict)
    _spot_lock: Any = field(default_factory=threading.RLock,repr=False)
    _depth_book: DepthBook = field(default_factory=DepthBook)
    _depth_subscriptions: dict = field(default_factory=dict)
    _depth_control_states: dict = field(default_factory=dict)
    _depth_retired: set = field(default_factory=set)
    _recorded_charges: Any = field(default_factory=OrderedDict,repr=False)

    def _remember_native_charge(self,receipt,deal,symbol,*,closing):
        from vati.core.canonical import canonical_json
        from vati.execution.ctrader.charge_source import capture_charge_source,execution_ref
        try:
            source=capture_charge_source(receipt,deal,symbol,account_alias=self.account_alias,
                native_account_id=self.ctid_trader_account_id,closing=closing)
            key=execution_ref(receipt);encoded=canonical_json(source).encode()
            # Conflicting native identities never overwrite an earlier source.
            if key in self._recorded_charges and self._recorded_charges[key]!=encoded:
                self._recorded_charges[key]=None
            else:self._recorded_charges[key]=encoded
            while len(self._recorded_charges)>128:self._recorded_charges.popitem(last=False)
        except (KeyError,TypeError,ValueError,ArithmeticError):
            pass  # Optional metadata cannot invalidate the independently known fill.
        return receipt

    def recorded_native_charge(self,receipt):
        from vati.execution.ctrader.charge_source import execution_ref,validate_charge_source
        encoded=self._recorded_charges.get(execution_ref(receipt))
        if encoded is None:return None
        body=json.loads(encoded)
        return validate_charge_source(body,receipt,account_alias=self.account_alias,closing=body['closing'])

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
        self._spot_book=SpotBook()
        self._spot_subscriptions=set()
        self._spot_control_states={}
        self._depth_book=DepthBook()
        self._depth_subscriptions={}
        self._depth_control_states={}
        self._depth_retired=set()
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
            if self._selected_native_symbols is not None:
                selected={native_integer(value,minimum=1) for value in self._selected_native_symbols}
                if not selected or not selected <= enabled.keys():
                    raise ValueError("selected native product unavailable")
                enabled={key:enabled[key] for key in selected}
            ids=list(enabled); current={}; originals={}
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
                    originals[alias]=(original,row)
                if seen!=set(requested):raise ValueError("native symbol details incomplete")
            if getattr(self.transport, "connection_id", None) != connection:
                raise ValueError("native symbol connection changed during refresh")
            received=native_integer(self.clock(),maximum=253402300799000)
            for alias, symbol in current.items():
                light, detail = originals[alias]
                contract=NativeSymbolContract.capture(account_id=account,
                    transport_host=getattr(self.transport,"host",None),light=light,detail=detail,
                    received_at_ms=received)
                if contract.revision != symbol.contract_revision:
                    raise ValueError("native symbol capture revision mismatch")
                symbol.native_contract=contract
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
    def market_reader(self, *, collection_timeout_s=30.0,
                      max_read_frames=4096,max_read_bytes=16*1024*1024):
        """Independent read-only connection; never shares the protective socket."""
        transport=CtraderReadTransport(host=self.transport.host,port=self.transport.port,
            timeout_s=self.transport.timeout_s,connector=self.transport._connector,
            max_frame_bytes=self.transport.max_frame_bytes,operation_timeout_s=collection_timeout_s,
            max_read_frames=max_read_frames,max_read_bytes=max_read_bytes)
        adapter=CtraderAdapter(transport,self.client_id,self.client_secret_provider,self.access_token_provider,
            self.ctid_trader_account_id,self.account_alias,self.venue,clock=self.clock)
        class MarketReader:
            def read_catalog(self,expected_scope):
                from vati.execution.ctrader.catalog import NativeSymbolCatalog,catalog_scope
                scope=catalog_scope(expected_scope)
                if (scope['native_account_id']!=adapter.ctid_trader_account_id
                        or scope['transport_host']!=transport.host):
                    raise VenueUnavailable('cTrader catalog reader account/environment differs')
                adapter._authenticate()
                connection=getattr(transport,'connection_id',None)
                kind,body=transport.call('ProtoOASymbolsListReq',
                    {'ctidTraderAccountId':adapter.ctid_trader_account_id,'includeArchivedSymbols':True})
                if (kind!='ProtoOASymbolsListRes' or connection!=getattr(transport,'connection_id',None)
                        or not adapter._auth_is_current()):
                    raise VenueUnavailable('cTrader catalog response or connection scope differs')
                try:
                    captured=NativeSymbolCatalog.capture(scope=scope,response=body,
                        received_at_ms=adapter.clock(),include_archived_symbols=True)
                except (KeyError,TypeError,ValueError,ArithmeticError) as error:
                    raise VenueUnavailable('cTrader native catalog response invalid') from error
                transport.check_budget()
                return captured
            def _select(self,expected_contract):
                if not isinstance(expected_contract,NativeSymbolContract):
                    raise VenueUnavailable('cTrader captured native contract required')
                scope=expected_contract.native_scope
                if (scope['native_account_id']!=adapter.ctid_trader_account_id
                        or scope['transport_host']!=transport.host):
                    raise VenueUnavailable('cTrader market reader account/environment differs')
                adapter._selected_native_symbols=(scope['native_symbol_id'],)
                adapter._symbol_snapshot_valid=False
                name=expected_contract.metadata['light']['symbolName']
                adapter._ensure_auth()
                original=adapter.symbol(name).native_contract
                if original is None or original.revision!=expected_contract.revision:
                    raise VenueUnavailable('cTrader native contract changed; refresh required')
                return name,original
            def read_window(self,expected_contract,*,timeframe,from_ms,to_ms):
                from vati.execution.ctrader.read_identity import NativeReadIdentity
                if isinstance(expected_contract,NativeReadIdentity):
                    return self.read_identity_window(expected_contract,timeframe=timeframe,from_ms=from_ms,to_ms=to_ms)
                from vati.execution.ctrader.feed import read_trendbars,native_integer,PERIOD,MAX_TIMESTAMP
                if not isinstance(timeframe,str) or timeframe not in PERIOD:
                    raise VenueUnavailable('cTrader market reader timeframe invalid')
                native_integer(from_ms,maximum=MAX_TIMESTAMP)
                native_integer(to_ms,minimum=from_ms,maximum=MAX_TIMESTAMP)
                name,original=self._select(expected_contract)
                observed=read_trendbars(adapter,name,timeframe,from_ms=from_ms,to_ms=to_ms,count=2001)
                transport.check_budget()  # Includes native observation parsing.
                return original,observed
            def read_identity_window(self,expected_identity,*,timeframe,from_ms,to_ms):
                from types import SimpleNamespace
                from vati.execution.ctrader.read_identity import NativeReadIdentity
                from vati.execution.ctrader.feed import read_trendbars,native_integer,PERIOD,MAX_TIMESTAMP
                if not isinstance(expected_identity,NativeReadIdentity):
                    raise VenueUnavailable('cTrader readonly source identity required')
                if not isinstance(timeframe,str) or timeframe not in PERIOD:
                    raise VenueUnavailable('cTrader readonly source timeframe invalid')
                native_integer(from_ms,maximum=MAX_TIMESTAMP)
                native_integer(to_ms,minimum=from_ms,maximum=MAX_TIMESTAMP)
                scope=expected_identity.native_scope
                catalog_scope={key:value for key,value in scope.items() if key!='native_symbol_id'}
                catalog=self.read_catalog(catalog_scope)
                try:
                    original=NativeReadIdentity.capture(catalog,scope['native_symbol_id'])
                    if original.revision!=expected_identity.revision:
                        raise ValueError('native source catalog identity changed')
                except (KeyError,TypeError,ValueError) as error:
                    raise VenueUnavailable('cTrader readonly source identity changed or unavailable') from error
                connection=getattr(transport,'connection_id',None)
                def current():
                    if connection!=getattr(transport,'connection_id',None) or not adapter._auth_is_current():
                        raise VenueUnavailable('cTrader readonly source session changed')
                def symbol(name):
                    if name!=original.series_label:
                        raise VenueUnavailable('cTrader readonly source label differs')
                    # Only the two fields consumed by the native history codec.
                    # No invented order-volume or execution metadata is supplied.
                    return SimpleNamespace(symbol_id=scope['native_symbol_id'],contract_revision=original.revision)
                source=SimpleNamespace(_ensure_auth=current,ctid_trader_account_id=scope['native_account_id'],
                    symbol=symbol,transport=transport,clock=adapter.clock)
                observed=read_trendbars(source,original.series_label,timeframe,from_ms=from_ms,to_ms=to_ms,count=2001)
                current();transport.check_budget()
                return original,observed
            def read_quote(self,expected_contract,*,max_age_ms=5000):
                from vati.execution.ctrader.feed import native_integer
                native_integer(max_age_ms,minimum=1)
                name,original=self._select(expected_contract)
                adapter.subscribe_spots(name)
                while True:
                    observed=adapter.spot_observation(name,max_age_ms=max_age_ms)
                    transport.check_budget()
                    if observed.prices is not None:return original,observed
                    if observed.state not in {'WAITING_NATIVE_BID','WAITING_NATIVE_ASK','NATIVE_QUOTE_BACKLOG_UNPROCESSED'}:
                        raise VenueUnavailable('cTrader native quote unavailable: '+observed.state)
                    if not transport.wait_for_event_kind('ProtoOASpotEvent'):
                        raise VenueUnavailable('cTrader native spot subscription queued but no complete fresh quote delivered')
            def close(self):transport.close()
            def read_capacity_snapshot(self):return transport.read_capacity_snapshot()
            def read_depth(self,expected_contract,*,max_age_ms=5000,limit=100):
                from vati.execution.ctrader.feed import native_integer
                native_integer(max_age_ms,minimum=1);native_integer(limit,minimum=1,maximum=4096)
                name,original=self._select(expected_contract)
                adapter.subscribe_depth(name)
                while True:
                    observed=adapter.depth_observation(name,max_age_ms=max_age_ms,limit=limit)
                    transport.check_budget()
                    if observed.state=='OBSERVED_PARTIAL_NATIVE_DEPTH':return original,observed
                    if observed.state not in {'WAITING_NATIVE_DEPTH','NATIVE_DEPTH_BACKLOG_UNPROCESSED'}:
                        raise VenueUnavailable('cTrader native depth unavailable: '+observed.state)
                    if not transport.wait_for_event_kind('ProtoOADepthEvent'):
                        raise VenueUnavailable('cTrader native depth subscription queued but no native changes delivered')
        return MarketReader()

    def funding_reader(self):
        # An independent connection and adapter state keep slow cash history off
        # the protective/order socket. It exposes only the read operation/close.
        transport=CtraderTransport(host=self.transport.host,port=self.transport.port,
            timeout_s=self.transport.timeout_s,connector=self.transport._connector,
            max_frame_bytes=self.transport.max_frame_bytes)
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

    def expected_margin(self, symbol: str, lots: Decimal, *, context, deadline_ms: int):
        """Read native current-price margin; grants no order or reservation."""
        from vati.execution.ctrader.margin_quote import read_expected_margin
        return read_expected_margin(self, symbol, lots, context=context, deadline_ms=deadline_ms)

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
        with localcontext(native_decimal_context()):
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
        with localcontext(native_decimal_context()):
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
            # Preserve the existing exact division's decimal text without doing
            # arithmetic in the caller's context or rounding a native amount.
            while digits and total%10==0:
                total//=10;digits-=1
            return Decimal((int(total<0),tuple(map(int,str(abs(total)))),-digits))
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
        with localcontext(native_decimal_context()):
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

    def order_details(self, order_id: int, *, context, deadline_ms: int):
        from vati.execution.ctrader.orders import read_order_details
        return read_order_details(self, order_id, context=context, deadline_ms=deadline_ms)

    def cancel_order(self, observation, *, deadline_ms: int, recheck):
        from vati.execution.ctrader.cancel import cancel_original_order
        return cancel_original_order(self, observation, deadline_ms=deadline_ms, recheck=recheck)

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
        receipt=ExecutionReceipt(cmd.trade_intent_id, cmd.decision_hash, self.venue, state, filled, px, cmd.entry_price, px, cmd.entry_price, sl is not None,
                                int(deal.get("executionTimestamp", now_ms)), now_ms, broker_order_id=str(deal.get("orderId", "")), broker_position_id=str(pos.get("positionId") or deal.get("positionId", "")),
                                protective_stop_price=sl, fees=_recorded_commission(deal)).sealed()
        return self._remember_native_charge(receipt,deal,sym,closing=False)

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
        receipt=ExecutionReceipt("", "", self.venue, state, sym.volume_to_lots(filled), price, ZERO, ZERO, ZERO,
            protected,now_ms,now_ms,broker_order_id=str(order_id),broker_position_id=position_id,
            reject_reason=reason,fees=_recorded_commission(deal)).sealed()
        return self._remember_native_charge(receipt,deal,sym,closing=True)

    # ------------------------------------------------------------ market data
    def subscribe_depth(self,symbol: str) -> None:
        from vati.execution.ctrader.feed import native_integer
        with self._spot_lock:
            self._ensure_auth();sym=self.symbol(symbol)
            if sym.native_contract is None:raise VenueUnavailable('cTrader native depth contract unavailable')
            connection=getattr(self.transport,'connection_id',None);key=(connection,sym.symbol_id)
            if key in self._depth_subscriptions:
                if self._depth_subscriptions[key]==sym.contract_revision:return
                self._depth_subscriptions.pop(key,None);self._depth_retired.add(key)
            if key in self._depth_retired:
                raise VenueUnavailable('cTrader native depth recovery requires a fresh connection')
            if len(self._depth_subscriptions)>=64:raise VenueUnavailable('cTrader native depth product capacity')
            self._depth_retired.add(key)  # An unknown control reply cannot reopen this session.
            self._depth_control_states[key]='SUBSCRIBE_REQUESTED_UNCONFIRMED'
            name,body=self.transport.call('ProtoOASubscribeDepthQuotesReq',{
                'ctidTraderAccountId':self.ctid_trader_account_id,'symbolId':[sym.symbol_id]})
            try:
                if (name!='ProtoOASubscribeDepthQuotesRes' or not isinstance(body,dict)
                        or native_integer(body['ctidTraderAccountId'],minimum=1)!=self.ctid_trader_account_id
                        or connection!=getattr(self.transport,'connection_id',None) or not self._auth_is_current()):raise ValueError()
            except (KeyError,TypeError,ValueError) as exc:
                self._depth_control_states[key]='SUBSCRIBE_ACKNOWLEDGEMENT_INVALID'
                raise VenueUnavailable('cTrader native depth subscription acknowledgement mismatch') from exc
            self._depth_subscriptions[key]=sym.contract_revision;self._depth_retired.discard(key)
            self._depth_control_states[key]='SUBSCRIBE_ACKNOWLEDGED_QUEUED'

    def unsubscribe_depth(self,symbol: str) -> None:
        from vati.execution.ctrader.feed import native_integer
        with self._spot_lock:
            self._ensure_auth();sym=self.symbol(symbol)
            connection=getattr(self.transport,'connection_id',None);key=(connection,sym.symbol_id)
            self._depth_subscriptions.pop(key,None);self._depth_retired.add(key)
            self._depth_book.forget(sym.symbol_id)
            self._depth_control_states[key]='UNSUBSCRIBE_REQUESTED_UNCONFIRMED'
            name,body=self.transport.call('ProtoOAUnsubscribeDepthQuotesReq',{
                'ctidTraderAccountId':self.ctid_trader_account_id,'symbolId':[sym.symbol_id]})
            try:
                if (name!='ProtoOAUnsubscribeDepthQuotesRes' or not isinstance(body,dict)
                        or native_integer(body['ctidTraderAccountId'],minimum=1)!=self.ctid_trader_account_id
                        or connection!=getattr(self.transport,'connection_id',None) or not self._auth_is_current()):raise ValueError()
            except (KeyError,TypeError,ValueError) as exc:
                self._depth_control_states[key]='UNSUBSCRIBE_ACKNOWLEDGEMENT_INVALID'
                raise VenueUnavailable('cTrader native depth unsubscription acknowledgement mismatch') from exc
            self._depth_control_states[key]='UNSUBSCRIBE_ACKNOWLEDGED_QUEUED'

    def depth_observation(self,symbol: str,*,max_age_ms=5000,limit=100):
        from vati.execution.ctrader.feed import native_integer
        native_integer(max_age_ms,minimum=1);native_integer(limit,minimum=1,maximum=4096)
        with self._spot_lock:
            self._ensure_auth();sym=self.symbol(symbol)
            if sym.native_contract is None:raise VenueUnavailable('cTrader native depth contract unavailable')
            connection=getattr(self.transport,'connection_id',None);book=self._depth_book
            pending=self.transport.drain_events_kind('ProtoOADepthEvent')
            try:now=self.clock()
            except Exception:now=None
            known={item.symbol_id:item for item in self.symbols.values()}
            for _,body in pending:
                product=body.get('symbolId') if isinstance(body,dict) else None
                if type(product) is not int or product not in known:continue
                item=known[product]
                if (self._depth_subscriptions.get((connection,product))!=item.contract_revision
                        or item.native_contract is None):continue
                book.observe(item.native_contract,connection,body,now)
            if (not self._auth_is_current() or connection!=getattr(self.transport,'connection_id',None)
                    or book is not self._depth_book or self.symbol(symbol).contract_revision!=sym.contract_revision):
                raise VenueUnavailable('cTrader native depth context changed')
            try:evaluated=self.clock()
            except Exception:evaluated=None
            key=(connection,sym.symbol_id)
            return book.snapshot(sym.native_contract,connection,now_ms=evaluated,max_age_ms=max_age_ms,limit=limit,
                subscribed=self._depth_subscriptions.get(key)==sym.contract_revision,
                control_state=self._depth_control_states.get(key,'NOT_REQUESTED'),
                backlog=self.transport.has_events_kind('ProtoOADepthEvent'))

    def spot_observation(self,symbol: str,*,max_age_ms=5000):
        """Scoped raw native sides and freshness; never a tradability claim."""
        from vati.execution.ctrader.feed import native_integer
        native_integer(max_age_ms,minimum=1)
        with self._spot_lock:
            self._ensure_auth();sym=self.symbol(symbol)
            if sym.native_contract is None:
                raise VenueUnavailable('cTrader native quote contract unavailable')
            connection=getattr(self.transport,'connection_id',None)
            book=self._spot_book
            pending=self.transport.drain_events_kind('ProtoOASpotEvent')
            try:now=self.clock()
            except Exception:now=None
            known={item.symbol_id:item for item in self.symbols.values()}
            for _,body in pending:
                product=body.get('symbolId') if isinstance(body,dict) else None
                if type(product) is not int or product not in known:continue
                if (connection,product) not in self._spot_subscriptions:continue
                item=known[product]
                if item.native_contract is not None:book.observe(item.native_contract,connection,body,now)
            if (not self._auth_is_current() or connection!=getattr(self.transport,'connection_id',None)
                    or book is not self._spot_book or self.symbol(symbol).contract_revision!=sym.contract_revision):
                raise VenueUnavailable('cTrader native quote context changed')
            try:evaluated=self.clock()
            except Exception:evaluated=None
            result=book.snapshot(sym.native_contract,connection,now_ms=evaluated,max_age_ms=max_age_ms,
                subscribed=(connection,sym.symbol_id) in self._spot_subscriptions)
            result=replace(result,control_state=self._spot_control_states.get((connection,sym.symbol_id),'NOT_REQUESTED'))
            if self.transport.has_events_kind('ProtoOASpotEvent'):
                result=replace(result,state='NATIVE_QUOTE_BACKLOG_UNPROCESSED')
            if result.prices is None:self._last_spot.pop(sym.symbol_id,None)
            else:self._last_spot[sym.symbol_id]=result.prices
            return result

    def spot(self,symbol: str,*,max_age_ms=5000) -> Optional[tuple[Decimal,Decimal]]:
        """Legacy price-pair adapter. A raw pair is not a live/trading certificate."""
        return self.spot_observation(symbol,max_age_ms=max_age_ms).prices

    def subscribe_spots(self, symbol: str) -> None:
        from vati.execution.ctrader.feed import native_integer
        with self._spot_lock:
            self._ensure_auth();sym=self.symbol(symbol)
            connection=getattr(self.transport,'connection_id',None);key=(connection,sym.symbol_id)
            if key in self._spot_subscriptions:return
            self._spot_control_states[key]='SUBSCRIBE_REQUESTED_UNCONFIRMED'
            name,body=self.transport.call('ProtoOASubscribeSpotsReq',{'ctidTraderAccountId':self.ctid_trader_account_id,
                'symbolId':[sym.symbol_id],'subscribeToSpotTimestamp':True})
            try:
                if (name!='ProtoOASubscribeSpotsRes' or not isinstance(body,dict)
                        or native_integer(body['ctidTraderAccountId'],minimum=1)!=self.ctid_trader_account_id
                        or connection!=getattr(self.transport,'connection_id',None) or not self._auth_is_current()):
                    raise ValueError()
            except (KeyError,TypeError,ValueError) as exc:
                self._spot_control_states[key]='SUBSCRIBE_ACKNOWLEDGEMENT_INVALID'
                raise VenueUnavailable('cTrader native spot subscription acknowledgement mismatch') from exc
            self._spot_subscriptions.add(key)  # ACK is queued subscription, not a delivered quote.
            self._spot_control_states[key]='SUBSCRIBE_ACKNOWLEDGED_QUEUED'

    def unsubscribe_spots(self,symbol: str) -> None:
        from vati.execution.ctrader.feed import native_integer
        with self._spot_lock:
            self._ensure_auth();sym=self.symbol(symbol)
            connection=getattr(self.transport,'connection_id',None);key=(connection,sym.symbol_id)
            # Local stop takes effect before native I/O. A queued/unknown ACK
            # cannot keep old prices usable or admit residual provider updates.
            self._spot_subscriptions.discard(key);self._last_spot.pop(sym.symbol_id,None)
            self._spot_book.forget(sym.symbol_id)
            self._spot_control_states[key]='UNSUBSCRIBE_REQUESTED_UNCONFIRMED'
            name,body=self.transport.call('ProtoOAUnsubscribeSpotsReq',{'ctidTraderAccountId':self.ctid_trader_account_id,
                'symbolId':[sym.symbol_id]})
            try:
                if (name!='ProtoOAUnsubscribeSpotsRes' or not isinstance(body,dict)
                        or native_integer(body['ctidTraderAccountId'],minimum=1)!=self.ctid_trader_account_id
                        or connection!=getattr(self.transport,'connection_id',None) or not self._auth_is_current()):
                    raise ValueError()
            except (KeyError,TypeError,ValueError) as exc:
                self._spot_control_states[key]='UNSUBSCRIBE_ACKNOWLEDGEMENT_INVALID'
                raise VenueUnavailable('cTrader native spot unsubscription acknowledgement mismatch') from exc
            self._spot_control_states[key]='UNSUBSCRIBE_ACKNOWLEDGED_QUEUED'
