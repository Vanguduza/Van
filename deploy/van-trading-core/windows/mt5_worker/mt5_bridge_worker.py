"""MT5 bridge worker — runs on the Windows host next to the MetaTrader 5 terminal.

Serves the narrow signed protocol `vati.execution.mt5_bridge` speaks:
  POST /bridge/v1/call  {op, nonce, issued_ms, body, signature}
over HTTPS with **mutual TLS** (the worker presents mt5-worker.crt, requires the
vati-core client certificate signed by the same private CA). On top of TLS every
request is HMAC-signed with the shared signing key; nonces are single-use and
issued_ms must be within the skew window. The worker never decides size, never
widens a stop, and refuses an order without SL in the same request.

    python mt5_bridge_worker.py --config C:\\van-mt5\\worker.json

worker.json (0600-equivalent ACL: owner only):
  {"listen": "0.0.0.0", "port": 9443, "cert": "mt5-worker.crt", "key": "mt5-worker.key", "ca": "ca.crt",
   "signing_key_file": "bridge.key", "accounts": {"fx_primary": {"login": 12345678, "server": "Broker-Demo", "currency": "USD", "demo": true, "password_file": "fx_primary.pw"}}}

The MetaTrader5 Python package is imported lazily so this file also runs under
tests on Linux with an injected fake terminal."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import math
import os
import sqlite3
import ssl
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Optional

OPS = ("sync_account", "sync_symbols", "order_check", "order_send", "order_send_expiring", "positions", "orders", "history", "modify_sl_tp", "close")
SKEW_MS = 5000


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class NonceStoreUnavailable(RuntimeError):
    pass


class NonceClockRollback(RuntimeError):
    pass


class NonceStore:
    """Atomic replay cache shared by restarts and workers using the same file.

    Keep the existing ten-skew-window retention; the durable clock high-water
    prevents a backward clock from making purged signed envelopes fresh again.
    This claims a request nonce, not a broker effect or an execution outcome.
    """
    def __init__(self, path: str) -> None:
        if not isinstance(path,str) or not path or path==':memory:':
            raise ValueError('persistent native nonce store required')
        self.path=Path(path).absolute()
        if self.path.is_symlink():raise ValueError('native nonce store cannot be a symbolic link')
        try:
            fd=os.open(self.path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        except FileExistsError:pass
        else:os.close(fd)
        db=self._connect()
        try:
            db.execute('CREATE TABLE IF NOT EXISTS van_native_nonces(nonce TEXT PRIMARY KEY,seen_ms INTEGER NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS van_native_replay_clock(singleton INTEGER PRIMARY KEY CHECK(singleton=1),high_water_ms INTEGER NOT NULL)')
        finally:db.close()

    def _connect(self):
        db=sqlite3.connect(self.path,timeout=5,isolation_level=None)
        try:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('PRAGMA busy_timeout=5000')
        except sqlite3.Error:
            db.close()
            raise
        return db

    def accept(self, nonce: int, now_ms: int) -> bool:
        db=None
        try:
            db=self._connect();db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT high_water_ms FROM van_native_replay_clock WHERE singleton=1').fetchone()
            if row is None and db.execute('SELECT 1 FROM van_native_nonces LIMIT 1').fetchone() is not None:
                raise NonceStoreUnavailable()
            previous=row[0] if row else now_ms
            if type(previous) is not int or not 0<=previous<2**63:raise NonceStoreUnavailable()
            if now_ms+SKEW_MS<previous:raise NonceClockRollback()
            high=max(now_ms,previous)
            db.execute('DELETE FROM van_native_nonces WHERE seen_ms<?',(high-10*SKEW_MS,))
            inserted=db.execute('INSERT OR IGNORE INTO van_native_nonces(nonce,seen_ms) VALUES(?,?)',
                (str(nonce),now_ms)).rowcount==1
            db.execute('INSERT INTO van_native_replay_clock(singleton,high_water_ms) VALUES(1,?) '
                'ON CONFLICT(singleton) DO UPDATE SET high_water_ms=excluded.high_water_ms',(high,))
            db.commit()
            return inserted
        except sqlite3.Error:
            raise NonceStoreUnavailable() from None
        finally:
            if db is not None:
                try:db.rollback()
                finally:db.close()


class Terminal:
    """Thin wrapper over the MetaTrader5 module; every venue effect goes through here."""

    def __init__(self, mt5=None) -> None:
        if mt5 is None:
            import MetaTrader5 as mt5  # type: ignore  # Windows only
        self.mt5 = mt5
        self.logged_in: Optional[tuple[int, str]] = None

    def login(self, login: int, server: str, password: str) -> bool:
        if self.logged_in == (login, server):
            return True
        if not self.mt5.initialize():
            return False
        ok = bool(self.mt5.login(login, password=password, server=server))
        self.logged_in = (login, server) if ok else None
        return ok

    def account(self) -> dict:
        a = self.mt5.account_info()
        if a is None:
            raise RuntimeError("account_info unavailable")
        terminal = self.mt5.terminal_info()
        if terminal is None or getattr(terminal,'connected',None) is not True:
            raise RuntimeError('current terminal broker connection unavailable')
        permissions=(getattr(a,'trade_allowed',None),getattr(a,'trade_expert',None),
                     getattr(terminal,'trade_allowed',None),getattr(terminal,'tradeapi_disabled',None))
        trading_allowed=(permissions[0] and permissions[1] and permissions[2] and not permissions[3]
                         if all(type(value) is bool for value in permissions) else None)
        mode = getattr(a, "trade_mode", None)
        demo = mode == 0 if type(mode) is int and mode in (0, 2) else None
        return {"login": a.login, "server": getattr(a, "server", None), "demo": demo,
                "equity": str(a.equity), "balance": str(a.balance), "currency": a.currency,
                "credit": str(getattr(a, 'credit', None)), "currency_digits": getattr(a, 'currency_digits', None),
                "margin_used": str(getattr(a, "margin", None)),
                "margin_free": str(getattr(a, "margin_free", None)),
                "margin_level": str(getattr(a, "margin_level", None)), "leverage": a.leverage,
                "hedging": getattr(a, "margin_mode", 2) == 2,
                "trade_allowed": trading_allowed}

    def cash_account(self, before: dict, *, query_ms: int, clock) -> dict:
        """Read-only available-history query, bracketed by native account facts.

        Python's period query uses UTC host time, not a broker clock. An SDK
        failure is unavailable evidence and never a successfully empty history.
        This observation does not certify settlement or all lifetime records.
        """
        unavailable = {"schema": "van.mt5.cash-telemetry/1", "complete": False}
        try:
            end_s = query_ms // 1000 + 1
            rows = self._observed_rows(self.mt5.history_deals_get(
                datetime.fromtimestamp(0, timezone.utc),
                datetime.fromtimestamp(end_s, timezone.utc)), 'cash history')
            if len(rows) > 200_000:
                raise ValueError('native history bound')
            names = ('BUY', 'SELL', 'BALANCE', 'CREDIT', 'CHARGE', 'CORRECTION', 'BONUS',
                     'COMMISSION', 'COMMISSION_DAILY', 'COMMISSION_MONTHLY',
                     'COMMISSION_AGENT_DAILY', 'COMMISSION_AGENT_MONTHLY', 'INTEREST',
                     'BUY_CANCELED', 'SELL_CANCELED', 'DIVIDEND', 'DIVIDEND_FRANKED', 'TAX')
            types = {getattr(self.mt5, 'DEAL_TYPE_' + name): 'DEAL_TYPE_' + name
                     for name in names if type(getattr(self.mt5, 'DEAL_TYPE_' + name, None)) is int}
            if types.get(getattr(self.mt5, 'DEAL_TYPE_BUY', None)) != 'DEAL_TYPE_BUY' or types.get(getattr(self.mt5, 'DEAL_TYPE_SELL', None)) != 'DEAL_TYPE_SELL':
                raise ValueError('native deal enum unavailable')
            cash = []
            for row in rows:
                kind = getattr(row, 'type', None)
                if type(kind) is not int or kind < 0:
                    raise ValueError('native deal type unavailable')
                operation = types.get(kind, 'DEAL_TYPE_UNKNOWN_' + str(kind))
                if operation in ('DEAL_TYPE_BUY', 'DEAL_TYPE_SELL'):
                    continue
                ticket = getattr(row, 'ticket', None)
                native_time = getattr(row, 'time_msc', None)
                if (type(ticket) is not int or not 0 < ticket < 2**64
                        or type(native_time) is not int or not 0 <= native_time <= end_s * 1000):
                    raise ValueError('native cash identity unavailable')
                amounts = {}
                for field in ('profit', 'commission', 'swap', 'fee'):
                    value = getattr(row, field, None)
                    if type(value) not in (int, float) or not math.isfinite(value):
                        raise ValueError('native cash amount unavailable')
                    amounts[field] = str(value)
                cash.append({'native_id': ticket, 'operation': operation, 'native_time_ms': native_time, **amounts})
                if len(cash) > 4096:
                    raise ValueError('native cash bound')
            after = self.account()
            keys = ('login', 'server', 'currency', 'demo', 'balance', 'credit')
            if any(before.get(k) != after.get(k) for k in keys) or clock() > end_s * 1000:
                raise ValueError('native cash bracket changed')
            funding = {'schema': 'van.mt5.cash-telemetry/1', 'complete': True,
                       'native_from_ms': 0, 'native_to_ms': end_s * 1000, 'native_clock_ms': query_ms,
                       'binding_before': {k: before[k] for k in keys[:4]},
                       'balance_before': before['balance'], 'credit_before': before['credit'], 'movements': cash}
            return {**after, 'funding': funding}
        except (AttributeError, TypeError, ValueError, RuntimeError, OverflowError, OSError):
            # Existing account/protective routes remain available. Linux holds
            # new risk when this observation cannot be validated.
            return {**before, 'funding': unavailable}

    @staticmethod
    def _observed_rows(rows,kind):
        if not isinstance(rows,(tuple,list)):
            raise RuntimeError(f'native {kind} observation unavailable')
        return rows

    def symbol(self, symbol: str) -> dict:
        s = self.mt5.symbol_info(symbol)
        if s is None:
            raise RuntimeError(f"unknown symbol {symbol}")
        return {"symbol": symbol, "volume_min": str(s.volume_min), "volume_step": str(s.volume_step), "volume_max": str(s.volume_max), "trade_stops_level": s.trade_stops_level, "point": str(s.point), "digits": s.digits,
                "trade_contract_size": str(s.trade_contract_size), "trade_tick_value": str(s.trade_tick_value), "trade_tick_size": str(s.trade_tick_size), "spread": s.spread, "trade_mode": s.trade_mode}

    def _request(self, b: dict) -> dict:
        m = self.mt5
        def number(key,*,positive=False):
            value=b[key]
            if isinstance(value,bool):raise ValueError('invalid native entry parameters')
            value=float(value)
            if not math.isfinite(value) or (value<=0 if positive else value<0):
                raise ValueError('invalid native entry parameters')
            return value
        if (b.get('type') not in {'BUY','SELL'} or b.get('order_type','MARKET') not in {'MARKET','LIMIT','PASSIVE_LIMIT'}
            or not isinstance(b.get('symbol'),str) or not b['symbol'].strip()):
            raise ValueError('invalid native entry parameters')
        number('volume',positive=True);number('sl',positive=True)
        for key in ('price','tp','deviation'):
            if b.get(key) is not None and b[key]!='':number(key,positive=key=='price')
        is_buy = b["type"] == "BUY"
        market = b.get("order_type", "MARKET") in ("MARKET",)
        req = {"action": m.TRADE_ACTION_DEAL if market else m.TRADE_ACTION_PENDING, "symbol": b["symbol"], "volume": float(b["volume"]), "sl": float(b["sl"]), "magic": int(b.get("magic", 0)), "comment": str(b.get("comment", ""))[:31],
               "type_time": m.ORDER_TIME_GTC if not market else m.ORDER_TIME_GTC, "type_filling": m.ORDER_FILLING_IOC}
        if market:
            tick = m.symbol_info_tick(b["symbol"])
            req["type"] = m.ORDER_TYPE_BUY if is_buy else m.ORDER_TYPE_SELL
            req["price"] = tick.ask if is_buy else tick.bid
            req["deviation"] = int(float(b["deviation"]) / float(m.symbol_info(b["symbol"]).point)) if b.get("deviation") else 10
        else:
            req["type"] = m.ORDER_TYPE_BUY_LIMIT if is_buy else m.ORDER_TYPE_SELL_LIMIT
            req["price"] = float(b["price"])
        if b.get("tp"):
            req["tp"] = float(b["tp"])
        return req

    def order_check(self, b: dict) -> dict:
        if not b.get("sl"):
            return {"ok": False, "reason": "protective stop (sl) required in the same request"}
        try:request=self._request(b)
        except (ValueError,TypeError,KeyError,OverflowError):
            return {'ok':False,'reason':'invalid native entry parameters'}
        r = self.mt5.order_check(request)
        return {"ok": r is not None and r.retcode == 0, "retcode": getattr(r, "retcode", None), "reason": getattr(r, "comment", ""), "margin": str(getattr(r, "margin", "")), "margin_free": str(getattr(r, "margin_free", ""))}

    def order_send(self, b: dict, *, before_dispatch: Optional[Callable[[], None]] = None) -> dict:
        if not b.get("sl"):
            return {"status": "REJECTED", "reason": "protective stop (sl) required in the same request"}
        m = self.mt5
        try:request=self._request(b)
        except (ValueError,TypeError,KeyError,OverflowError):
            return {'status':'REJECTED','volume':'0','reason':'invalid native entry parameters'}
        if not self._netting_symbol_clear(b['symbol']):
            return {'status':'REJECTED','volume':'0','reason':'netting symbol has existing or unknown exposure; allocation reconciliation required'}
        # Native symbol/tick/exposure reads can block after signed admission.
        # The worker supplies this private guard; it is not a request field.
        if before_dispatch is not None:
            try:before_dispatch()
            except Exception:
                return {'status':'REJECTED','volume':'0','reason':'native final entry authorization unavailable; not dispatched'}
        r = m.order_send(request)
        if r is None:
            return {"status": "UNKNOWN", "reason": "native order outcome unconfirmed; reconcile the original command"}
        status = "FILLED" if r.retcode == m.TRADE_RETCODE_DONE else ("PARTIAL" if r.retcode == m.TRADE_RETCODE_DONE_PARTIAL else ("ACCEPTED" if r.retcode == m.TRADE_RETCODE_PLACED else "REJECTED" if self._native_refusal(r.retcode) else "UNKNOWN"))
        sl_confirmed = False
        position = None
        if status in {'FILLED','PARTIAL'}:
            pos = self._position_for_result(r,b)
            if pos is not None:
                position = pos.ticket
                sl_confirmed = self._stop_at_least_as_protective(getattr(pos,'sl',None),b['sl'],b['type']=='BUY')
        elif status == 'ACCEPTED':
            try:
                orders=self._observed_rows(m.orders_get(ticket=r.order),'pending orders')
                matches=[o for o in orders if o.ticket==r.order and o.symbol==b['symbol']]
                sl_confirmed=len(matches)==1 and self._stop_at_least_as_protective(matches[0].sl,b['sl'],b['type']=='BUY')
            except Exception:
                # A read fault after a native effect cannot erase that effect.
                sl_confirmed=False
        return {"status": status, "retcode": r.retcode, "reason": getattr(r, "comment", ""), "order": getattr(r, "order", 0), "deal":getattr(r,'deal',None), "position": position, "volume": str(getattr(r, "volume", 0)), "price": str(getattr(r, "price", 0)) if getattr(r, "price", 0) else None,
                "arrival": str(getattr(r, "price", 0)) if getattr(r, "price", 0) else None, "sl_confirmed": sl_confirmed, "server_time_ms": int(time.time() * 1000)}

    @staticmethod
    def _native_refusal(retcode):
        # MetaTrader's explicit refusal codes; TIMEOUT, CONNECTION, LOCKED and
        # generic ERROR remain uncertain, not evidence of no venue effect.
        return type(retcode) is int and retcode in {
            10006,10013,10014,10015,10016,10017,10018,10019,10020,10021,10022,
            10026,10027,10030,10033,10034,10035,10040,10042,10043,10044,10045,10046}

    def _netting_symbol_clear(self,symbol):
        try:
            mode=getattr(self.mt5.account_info(),'margin_mode',None)
            if type(mode) is not int or mode not in (0,1,2):return False
            if mode==2:return True
            positions=self._observed_rows(self.mt5.positions_get(),'positions')
            orders=self._observed_rows(self.mt5.orders_get(),'orders')
            return not any(p.symbol==symbol for p in (*positions,*orders))
        except Exception:return False

    @staticmethod
    def _stop_at_least_as_protective(actual,requested,is_buy):
        try:
            actual=float(actual);requested=float(requested)
            return (math.isfinite(actual) and math.isfinite(requested) and actual>0 and requested>0
                    and (actual>=requested if is_buy else actual<=requested))
        except (TypeError,ValueError,OverflowError):return False

    def _position_for_result(self,result,body):
        try:
            deal=getattr(result,'deal',None);order=getattr(result,'order',None)
            if type(deal) is not int or deal<=0 or type(order) is not int or order<=0:return None
            # Python SDK's ticket filter is the ORDER ticket. Select the exact
            # returned deal before resolving its stable native position ID.
            deals=self._observed_rows(self.mt5.history_deals_get(ticket=order),'deals')
            matches=[d for d in deals if d.ticket==deal and d.order==order and d.symbol==body['symbol']]
            if len(matches)!=1:return None
            identifier=matches[0].position_id
            if type(identifier) is not int or identifier<=0:return None
            positions=self._observed_rows(self.mt5.positions_get(),'positions')
            side=self.mt5.ORDER_TYPE_BUY if body['type']=='BUY' else self.mt5.ORDER_TYPE_SELL
            matches=[p for p in positions if p.identifier==identifier and p.symbol==body['symbol'] and p.type==side]
            if len(matches)!=1 or type(matches[0].ticket) is not int or matches[0].ticket<=0:return None
            return matches[0]
        except Exception:
            # Preserve the accepted fill and unconfirmed protection, never guess
            # an order ticket after a history/position observation failed.
            return None

    def positions(self) -> list[dict]:
        m = self.mt5
        return [{"ticket": p.ticket, "symbol": p.symbol, "type": "BUY" if p.type == m.ORDER_TYPE_BUY else "SELL", "volume": str(p.volume), "price_open": str(p.price_open), "sl": str(p.sl) if p.sl else None, "tp": str(p.tp) if p.tp else None, "comment": p.comment, "magic": p.magic, "profit": str(p.profit)} for p in self._observed_rows(m.positions_get(),'positions')]

    def orders(self) -> list[dict]:
        return [{"ticket": o.ticket, "symbol": o.symbol, "type": o.type, "volume": str(o.volume_current), "price": str(o.price_open), "sl": str(o.sl) if o.sl else None, "comment": o.comment} for o in self._observed_rows(self.mt5.orders_get(),'orders')]

    def history(self, from_s: int, to_s: int) -> list[dict]:
        from datetime import datetime, timezone
        deals = self._observed_rows(self.mt5.history_deals_get(datetime.fromtimestamp(from_s, timezone.utc), datetime.fromtimestamp(to_s, timezone.utc)),'deals')
        return [{"ticket": d.ticket, "order": d.order, "position": d.position_id, "symbol": d.symbol, "type": d.type, "entry": d.entry, "volume": str(d.volume), "price": str(d.price), "profit": str(d.profit), "commission": str(d.commission), "swap": str(d.swap), "time_ms": int(d.time) * 1000, "comment": d.comment} for d in deals]

    def modify_sl_tp(self, position: int, sl: Optional[str], tp: Optional[str]) -> dict:
        m = self.mt5
        pos = [p for p in self._observed_rows(m.positions_get(ticket=int(position)),'positions') if p.ticket == int(position)]
        if not pos:
            return {"ok": False, "reason": "position not found"}
        p = pos[0]
        new_sl = float(sl) if sl else float(p.sl)
        if not math.isfinite(new_sl) or new_sl<=0:
            return {'ok':False,'reason':'positive finite protective stop required'}
        # tighten-only: a stop may only move toward profit
        if p.sl and ((p.type == m.ORDER_TYPE_BUY and new_sl < float(p.sl)) or (p.type == m.ORDER_TYPE_SELL and new_sl > float(p.sl))):
            return {"ok": False, "reason": "refusing to widen protective stop"}
        r = m.order_send({"action": m.TRADE_ACTION_SLTP, "position": int(position), "symbol": p.symbol, "sl": new_sl, "tp": float(tp) if tp else float(p.tp)})
        if r is None:return {'ok':None,'reason':'native stop change outcome unconfirmed; reconcile the original command'}
        confirmed=False
        if r.retcode==m.TRADE_RETCODE_DONE:
            try:
                current=self._observed_rows(m.positions_get(ticket=int(position)),'positions')
                matches=[v for v in current if v.ticket==int(position) and v.symbol==p.symbol and v.type==p.type]
                confirmed=len(matches)==1 and self._stop_at_least_as_protective(matches[0].sl,new_sl,p.type==m.ORDER_TYPE_BUY)
            except Exception:pass
        return {"ok": True if confirmed else False if self._native_refusal(r.retcode) else None, "retcode": getattr(r, "retcode", None), "reason": getattr(r, "comment", "")}

    def close(self, position: int, volume: Optional[str], reason: str) -> dict:
        m = self.mt5
        pos = [p for p in self._observed_rows(m.positions_get(ticket=int(position)),'positions') if p.ticket == int(position)]
        if not pos:
            return {"status": "UNKNOWN", "reason": "position not found"}
        p = pos[0]
        tick = m.symbol_info_tick(p.symbol)
        is_buy = p.type == m.ORDER_TYPE_BUY
        req = {"action": m.TRADE_ACTION_DEAL, "position": int(position), "symbol": p.symbol, "volume": float(volume) if volume else float(p.volume), "type": m.ORDER_TYPE_SELL if is_buy else m.ORDER_TYPE_BUY,
               "price": tick.bid if is_buy else tick.ask, "deviation": 20, "magic": p.magic, "comment": f"vati-close:{reason}"[:31], "type_filling": m.ORDER_FILLING_IOC}
        r = m.order_send(req)
        if r is None:return {'status':'UNKNOWN','reason':'native close outcome unconfirmed; reconcile the original command'}
        ok = r is not None and r.retcode in (m.TRADE_RETCODE_DONE, m.TRADE_RETCODE_DONE_PARTIAL)
        status='PARTIAL' if r.retcode==m.TRADE_RETCODE_DONE_PARTIAL else 'FILLED' if ok else 'REJECTED' if self._native_refusal(r.retcode) else 'UNKNOWN'
        return {"status": status, "retcode": getattr(r, "retcode", None), "reason": getattr(r, "comment", reason), "volume": str(getattr(r, "volume", 0)), "price": str(getattr(r, "price", 0)) if ok else None}


class Worker:
    def __init__(self, config: dict, terminal: Terminal, signing_key: bytes, *, clock=lambda: int(time.time() * 1000)) -> None:
        self.cfg, self.t, self.key, self.clock = config, terminal, signing_key, clock
        nonce_path=config.get('nonce_store')
        if nonce_path is None and config.get('signing_key_file'):
            nonce_path=str(Path(config['signing_key_file']).resolve().with_name(
                Path(config['signing_key_file']).name+'.nonces.sqlite3'))
        self.nonces = NonceStore(nonce_path)
        self.audit: list[dict] = []
        self._terminal_lock = threading.RLock()

    def _account(self, alias: str) -> dict:
        a = self.cfg["accounts"].get(alias)
        if not a:
            raise PermissionError(f"alias {alias} not configured on this worker")
        login = a.get("login")
        if (not ((type(login) is int and login > 0)
                 or (isinstance(login, str) and login.isascii() and login.isdigit() and int(login) > 0))
            or not isinstance(a.get("server"), str) or not a["server"].strip()
            or not isinstance(a.get("currency"), str) or not a["currency"].strip()
            or type(a.get("demo")) is not bool):
            raise PermissionError("configured physical account identity is incomplete")
        pw = Path(a["password_file"]).read_text().strip() if a.get("password_file") else a.get("password", "")
        if not self.t.login(int(a["login"]), a["server"], pw):
            raise RuntimeError(f"MT5 login failed for {alias}")
        return a

    def verify(self, req: dict) -> tuple[bool, str]:
        if not isinstance(req,dict):return False,'invalid signed request'
        for k in ("op", "nonce", "issued_ms", "body", "signature"):
            if k not in req:
                return False, f"missing {k}"
        if (type(req['nonce']) is not int or not 0<=req['nonce']<2**128
            or type(req['issued_ms']) is not int or not 0<=req['issued_ms']<2**63
            or not isinstance(req['op'],str) or not isinstance(req['body'],dict)
            or not isinstance(req['signature'],str)):
            return False,'invalid signed request'
        payload = {"op": req["op"], "nonce": req["nonce"], "issued_ms": req["issued_ms"], "body": req["body"]}
        sig = hmac.new(self.key, canonical_json(payload).encode(), hashlib.sha256).hexdigest()
        if not req['signature'].isascii():return False,'bad signature'
        if not hmac.compare_digest(sig, str(req["signature"])):
            return False, "bad signature"
        now = self.clock()
        if type(now) is not int or not 0<=now<2**63:return False,'native clock unavailable'
        if abs(now - int(req["issued_ms"])) > SKEW_MS:
            return False, "clock skew"
        if req["op"] not in OPS:
            return False, "op not in contract"
        try:
            if not self.nonces.accept(req['nonce'],now):return False,'nonce replayed'
        except NonceStoreUnavailable:return False,'native replay store unavailable'
        except NonceClockRollback:return False,'native replay clock rollback requires recovery'
        return True, "ok"

    def handle(self, req: dict) -> dict:
        ok, why = self.verify(req)
        if not ok:
            return {"error": why, "nonce": req.get("nonce") if isinstance(req,dict) else None, "worker_time_ms": self.clock()}
        op, b = req["op"], req["body"]
        try:
            with self._terminal_lock:
                acc = self._account(str(b.get("alias", "")))
                a = self.t.account()
                if (not isinstance(acc.get("server"), str) or not acc["server"]
                    or not isinstance(acc.get("currency"), str) or not acc["currency"]
                    or type(acc.get("demo")) is not bool):
                    raise PermissionError("configured physical account identity is incomplete")
                if (type(a.get("login")) is not int or a["login"] != int(acc["login"])
                    or a.get("server") != acc["server"] or a.get("currency") != acc["currency"]
                    or type(a.get("demo")) is not bool or a["demo"] is not acc["demo"]):
                    raise PermissionError("terminal physical account identity differs from the configured alias")
                expected = b.get('expected_account')
                physical = {'login': str(a['login']), 'server': a['server'],
                            'currency': a['currency'], 'demo': a['demo']}
                if expected is not None and (
                    not isinstance(expected, dict) or set(expected) != set(physical)
                    or type(expected['demo']) is not bool
                    or any(type(expected[k]) is not str for k in ('login','server','currency'))
                    or expected != physical):
                    raise PermissionError('terminal account identity differs from the signed Linux binding')
                if op == "sync_account":
                    a = self.t.cash_account(a, query_ms=self.clock(), clock=self.clock)
                    out = {"account": {**a, "verified": True, "server_time_ms": self.clock()},
                           "entry_constraints":{"schema":"van.mt5.entry-constraints/1","explicit_deadline":True,"required_op":"order_send_expiring"}}
                elif op == "sync_symbols":
                    out = {"symbols": [self.t.symbol(s) for s in b.get("symbols", [])]}
                elif op == "order_check":
                    out = self.t.order_check(b)
                elif op in ("order_send","order_send_expiring"):
                    if abs(self.clock() - int(req["issued_ms"])) > SKEW_MS:
                        out = {"status": "REJECTED", "reason": "signed entry request expired before terminal dispatch"}
                    elif a.get("trade_allowed") is not True:
                        out = {"status": "REJECTED", "reason": "terminal trade not allowed"}
                    else:
                        def final_entry_guard():
                            current=self.t.account()
                            if (type(current.get('login')) is not int or str(current['login'])!=physical['login']
                                or current.get('server')!=physical['server'] or current.get('currency')!=physical['currency']
                                or type(current.get('demo')) is not bool or current['demo'] is not physical['demo']
                                or current.get('trade_allowed') is not True):
                                raise PermissionError('native entry identity or permissions changed')
                            # Check after the final native read as well as at
                            # HTTP admission. This does not renew signed time.
                            if abs(self.clock()-int(req['issued_ms']))>SKEW_MS:
                                raise PermissionError('signed native entry request expired')
                            if op=='order_send_expiring' and 'expires_at_ms' not in b:
                                raise PermissionError('explicit native entry deadline required')
                            if 'expires_at_ms' in b:
                                expiry=b['expires_at_ms']
                                if type(expiry) is not int or not 0<expiry<2**63 or self.clock()>=expiry:
                                    raise PermissionError('explicit native entry deadline invalid or expired')
                        out = self.t.order_send(b,before_dispatch=final_entry_guard)
                elif op == "positions":
                    out = {"positions": self.t.positions()}
                elif op == "orders":
                    out = {"orders": self.t.orders()}
                elif op == "history":
                    out = {"deals": self.t.history(int(b.get("from_s", 0)), int(b.get("to_s", time.time())))}
                elif op == "modify_sl_tp":
                    out = self.t.modify_sl_tp(int(b["position"]), b.get("sl"), b.get("tp"))
                elif op == "close":
                    out = self.t.close(int(b["position"]), b.get("volume"), str(b.get("reason", "")))
                else:
                    out = {"error": "unreachable"}
                if expected is not None and 'error' not in out:
                    out['identity_binding'] = physical
        except Exception as exc:  # noqa: BLE001 — venue faults become data for the client's fail-closed path
            out = {"error": str(exc)[:200]}
        self.audit.append({"ts": self.clock(), "op": op, "alias": b.get("alias"), "result": "error" if "error" in out else (out.get("status") or "ok")})
        return {**out, "nonce": req["nonce"], "worker_time_ms": self.clock()}


def make_handler(worker: Worker):
    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path != "/bridge/v1/call":
                self.send_response(404); self.end_headers(); return
            n = int(self.headers.get("Content-Length", "0"))
            if n > 65536:
                self.send_response(413); self.end_headers(); return
            try:
                req = json.loads(self.rfile.read(n))
            except ValueError:
                self.send_response(400); self.end_headers(); return
            out = json.dumps(worker.handle(req)).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)

        def log_message(self, fmt, *args):  # never log request bodies
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))
    return H


def serve(config_path: str, terminal: Optional[Terminal] = None) -> None:
    cfg = json.loads(Path(config_path).read_text())
    key = Path(cfg["signing_key_file"]).read_text().strip().encode()
    if len(key) < 32:
        raise SystemExit("signing key must be ≥ 32 bytes")
    worker = Worker(cfg, terminal or Terminal(), key)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(cfg["cert"], cfg["key"])
    ctx.load_verify_locations(cfg["ca"])
    ctx.verify_mode = ssl.CERT_REQUIRED          # mTLS: only vati-core's client certificate is accepted
    srv = ThreadingHTTPServer((cfg.get("listen", "0.0.0.0"), int(cfg.get("port", 9443))), make_handler(worker))
    srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    print(json.dumps({"listening": srv.server_address, "accounts": sorted(cfg["accounts"]), "mtls": True}))
    srv.serve_forever()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--config", required=True)
    serve(ap.parse_args().config)
