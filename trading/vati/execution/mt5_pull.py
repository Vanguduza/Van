"""MT5 pull bridge (Rev 5 route 4): a Windows-free MT5 path.

An MQL5 Expert Advisor (deploy/van-trading-core/mql5/VanBridgeEA.mq5) runs inside the
terminal on a MetaQuotes or broker VPS and *pulls* signed commands from van-trading-core
over HTTPS every second, executes them, and reports results plus a fresh account /
position snapshot. Nothing on the trading VM ever holds the MT5 login or password: the
terminal on the VPS does. Trust is a per-alias 32-byte signing key typed into the EA's
inputs and stored behind the account's credential reference here.

Two processes share one SQLite queue (WAL): the session (`Mt5PullAdapter`) enqueues and
waits; the pull server (`create_pull_app`) hands commands to the EA and stores results.

Wire (EA → server): POST /ea/v1/{alias}/poll   JSON {ts, nonce, account, positions, results}
  headers: X-Van-Ts, X-Van-Nonce, X-Van-Signature = HMAC-SHA256(key, "{ts}\\n{nonce}\\n{alias}\\n{sha256(body)}")
Wire (server → EA): text/plain, one command per line:
  id|op|symbol|type|volume|price|sl|tp|position|comment|magic|deviation|order_type|login|server_hex|currency_hex|demo
  ORDER_SEND_EXPIRING adds the exact UTC expires_at_ms as field18; an older
  17-field EA refuses the new frame rather than dropping its deadline.
  (legacy unbound component fixtures retain the original 12-column format)
The EA's operations are ORDER_SEND, ORDER_SEND_EXPIRING, MARGIN_QUOTE, SYMBOL_CONTRACT, QUOTE_SNAPSHOT, MODIFY_SL and CLOSE. The two reads cannot execute an order."""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import threading
import time
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, field, replace
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Optional, ClassVar

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse

from vati.execution.base import AccountState, ExecutionReceipt, Health, OrderCommand, VenuePosition, VenueUnavailable
from vati.execution.mt5_identity import Mt5Identity
from vati.risk.contracts import Direction, LossModel

ZERO = Decimal("0")
ENTRY_OPS = ("ORDER_SEND", "ORDER_SEND_EXPIRING")
OPS = (*ENTRY_OPS, "MARGIN_QUOTE", "SYMBOL_CONTRACT", "QUOTE_SNAPSHOT", "MODIFY_SL", "CLOSE")
SKEW_S = 60
STATE_FRESH_MS = 30_000

# P1-SEC-007. /ea/v1/{alias}/poll is the one internet-reachable route in this deployable
# and it accepted unlimited signature guesses per alias. The counter below is deliberately
# a local twenty lines rather than an import of van_gateway.auth.throttle: the bridge and
# the gateway are separate deployables that share no process and no package, and coupling
# them to share a failure counter would be worse than the duplication.
#
# Same posture as the gateway's live-path surfaces: a correct signature always passes, so
# nobody can take an account's EA offline by hammering its alias. Past the policy, wrong
# signatures are answered 429 and never reach the queue.
POLL_MAX_FAILURES = 10
POLL_WINDOW_S = 300
POLL_LOCKOUT_S = 300


# ------------------------------------------------------------------ shared queue
class BridgeQueue:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self._conn = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False)
        self._lock = threading.Lock()
        if self.path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("""CREATE TABLE IF NOT EXISTS commands (id INTEGER PRIMARY KEY AUTOINCREMENT, alias TEXT NOT NULL, op TEXT NOT NULL, body_json TEXT NOT NULL,
                              status TEXT NOT NULL DEFAULT 'QUEUED', result_json TEXT, created_ms INTEGER NOT NULL, taken_ms INTEGER, done_ms INTEGER)""")
        self._conn.execute("CREATE TABLE IF NOT EXISTS state (alias TEXT PRIMARY KEY, account_json TEXT NOT NULL, positions_json TEXT NOT NULL, updated_ms INTEGER NOT NULL, last_nonce TEXT)")
        if 'orders_json' not in {r[1] for r in self._conn.execute('PRAGMA table_info(state)')}:
            try:self._conn.execute('ALTER TABLE state ADD COLUMN orders_json TEXT')
            except sqlite3.OperationalError:
                if 'orders_json' not in {r[1] for r in self._conn.execute('PRAGMA table_info(state)')}:raise
        self._conn.execute("CREATE TABLE IF NOT EXISTS nonces (alias TEXT NOT NULL, nonce TEXT NOT NULL, seen_ms INTEGER NOT NULL, PRIMARY KEY(alias, nonce))")
        self._conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS native_entry_command
            ON commands(alias,json_extract(body_json,'$.native_command_hash'))
            WHERE op='ORDER_SEND' AND json_type(body_json,'$.native_command_hash')='text'""")
        # Retain the original index for old readers and fence mixed-version
        # senders across both entry operations during a rolling source upgrade.
        self._conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS native_entry_command_v2
            ON commands(alias,json_extract(body_json,'$.native_command_hash'))
            WHERE op IN ('ORDER_SEND','ORDER_SEND_EXPIRING') AND json_type(body_json,'$.native_command_hash')='text'""")

    def enqueue(self, alias: str, op: str, body: dict, *, now_ms: int) -> int:
        if op not in OPS:
            raise ValueError(f"op {op} not in bridge contract")
        if op=='ORDER_SEND' and 'expires_at_ms' in body:
            raise VenueUnavailable('explicit deadline requires the bounded native entry operation')
        with self._lock:
            if op in ENTRY_OPS and body.get('native_command_hash'):
                # SQLite, rather than an instance-local lock, arbitrates the
                # original native claim across independent bridge clients.
                self._conn.execute('BEGIN IMMEDIATE')
                try:
                    encoded=json.dumps(body,sort_keys=True)
                    row=self._conn.execute("SELECT id,body_json FROM commands WHERE alias=? AND op IN ('ORDER_SEND','ORDER_SEND_EXPIRING') AND json_extract(body_json,'$.native_command_hash')=?",
                        (alias,body['native_command_hash'])).fetchone()
                    if row is not None:
                        if row[1]!=encoded:raise VenueUnavailable('original native entry payload conflicts; reconcile without resubmission')
                        cid=int(row[0])
                    else:
                        cid=int(self._conn.execute('INSERT INTO commands(alias,op,body_json,created_ms) VALUES (?,?,?,?)',
                            (alias,op,encoded,now_ms)).lastrowid)
                    self._conn.commit()
                    return cid
                except BaseException:
                    self._conn.rollback();raise
            cur = self._conn.execute("INSERT INTO commands(alias, op, body_json, created_ms) VALUES (?,?,?,?)", (alias, op, json.dumps(body, sort_keys=True), now_ms))
            return int(cur.lastrowid)

    def native_entries(self, alias: str, *, include_clocks: bool = False) -> list[dict]:
        """Original durable claims/results, scoped to this authenticated EA."""
        with self._lock:
            rows=self._conn.execute("SELECT id,body_json,status,result_json,created_ms,taken_ms,done_ms FROM commands WHERE alias=? AND op IN ('ORDER_SEND','ORDER_SEND_EXPIRING') AND json_type(body_json,'$.native_command_hash')='text' ORDER BY id",(alias,)).fetchall()
            return [{'id':int(cid),'body':json.loads(body),'status':status,
                     'result':json.loads(result) if result is not None else None,
                     **({'created_ms':created,'taken_ms':taken,'done_ms':done} if include_clocks else {})}
                    for cid,body,status,result,created,taken,done in rows]

    def take_pending(self, alias: str, *, now_ms: int, limit: int = 10,
                     expected_identity: Mt5Identity | None = None, allow_entry: bool = True) -> list[dict]:
        with self._lock:
            # Independent poll servers share the database, not this lock.
            # Claim the complete batch before any consumer can receive it.
            self._conn.execute('BEGIN IMMEDIATE')
            try:
                rows = self._conn.execute("SELECT id, op, body_json FROM commands WHERE alias = ? AND status = 'QUEUED' ORDER BY id LIMIT ?", (alias, limit)).fetchall()
                out = []
                for cid, op, body in rows:
                    payload = json.loads(body)
                    if ((op in ('ORDER_SEND_EXPIRING','MARGIN_QUOTE','SYMBOL_CONTRACT','QUOTE_SNAPSHOT') and not _deadline_valid(payload.get('expires_at_ms'),now_ms=now_ms))
                        or (op=='ORDER_SEND' and 'expires_at_ms' in payload)):
                        result={'status':'REJECTED','volume':'0','reason':'native entry deadline invalid or expired before dispatch'}
                        self._conn.execute("UPDATE commands SET status='DONE', result_json=?, done_ms=? WHERE id=?",
                            (json.dumps(result,sort_keys=True),now_ms,cid))
                        continue
                    if expected_identity is not None:
                        try:
                            bound = Mt5Identity(**payload['expected_account'])
                            admitted = bound == expected_identity and (op not in ENTRY_OPS or allow_entry is True)
                        except (KeyError, TypeError, ValueError, VenueUnavailable):
                            admitted = False
                        if not admitted:
                            # QUEUED has never been handed to a terminal. Do not
                            # apply this refusal to TAKEN/uncertain operations.
                            result = {'status':'REJECTED','volume':'0','ok':False,
                                'reason':'registered physical account binding or entry permission changed'}
                            self._conn.execute("UPDATE commands SET status='DONE', result_json=?, done_ms=? WHERE id=?",
                                (json.dumps(result,sort_keys=True),now_ms,cid))
                            continue
                    self._conn.execute("UPDATE commands SET status = 'TAKEN', taken_ms = ? WHERE id = ?", (now_ms, cid))
                    out.append({"id": cid, "op": op, **payload})
                self._conn.commit()
                return out
            except BaseException:
                self._conn.rollback()
                raise

    def complete(self, alias: str, cid: int, result: dict, *, now_ms: int) -> bool:
        if type(cid) is not int or not 0<cid<2**63 or not isinstance(result,dict):
            return False
        with self._lock:
            n = self._conn.execute("UPDATE commands SET status = 'DONE', result_json = ?, done_ms = ? WHERE id = ? AND alias = ? AND status = 'TAKEN'", (json.dumps(result, sort_keys=True), now_ms, cid, alias)).rowcount
            return n == 1

    def result(self, cid: int) -> Optional[dict]:
        row = self._conn.execute("SELECT status, result_json FROM commands WHERE id = ?", (cid,)).fetchone()
        if row is None or row[0] != "DONE":
            return None
        return json.loads(row[1])

    def set_state(self, alias: str, account: dict, positions: list[dict], *, now_ms: int, nonce: str, orders=None) -> None:
        with self._lock:
            self._conn.execute("INSERT INTO state(alias, account_json, positions_json, updated_ms, last_nonce,orders_json) VALUES (?,?,?,?,?,?) ON CONFLICT(alias) DO UPDATE SET account_json=excluded.account_json, positions_json=excluded.positions_json, updated_ms=excluded.updated_ms, last_nonce=excluded.last_nonce,orders_json=excluded.orders_json",
                               (alias, json.dumps(account, sort_keys=True), json.dumps(positions, sort_keys=True), now_ms, nonce,json.dumps(orders,sort_keys=True) if orders is not None else None))

    def state(self, alias: str) -> Optional[dict]:
        row = self._conn.execute("SELECT account_json, positions_json, updated_ms,orders_json,last_nonce FROM state WHERE alias = ?", (alias,)).fetchone()
        if row is None:
            return None
        return {"account": json.loads(row[0]), "positions": json.loads(row[1]), "updated_ms": row[2],"orders":json.loads(row[3]) if row[3] is not None else None,"source_nonce":row[4]}

    def nonce_fresh(self, alias: str, nonce: str, *, now_ms: int) -> bool:
        with self._lock:
            self._conn.execute("DELETE FROM nonces WHERE seen_ms < ?", (now_ms - 4 * SKEW_S * 1000,))
            try:
                self._conn.execute("INSERT INTO nonces(alias, nonce, seen_ms) VALUES (?,?,?)", (alias, nonce, now_ms))
                return True
            except sqlite3.IntegrityError:
                return False

    def close(self) -> None:
        self._conn.close()


def open_bridge_queue(path: str) -> BridgeQueue:
    return BridgeQueue(path or ":memory:")


# ------------------------------------------------------------------ signing (shared with the EA)
def sign_poll(key: bytes, ts: str, nonce: str, alias: str, body: bytes) -> str:
    return hmac.new(key, f"{ts}\n{nonce}\n{alias}\n{hashlib.sha256(body).hexdigest()}".encode(), hashlib.sha256).hexdigest()


def _deadline_valid(value, *, now_ms=None):
    return (type(value) is int and 0<value<2**63
        and (now_ms is None or type(now_ms) is int and 0<=now_ms<value))


def format_commands(cmds: list[dict]) -> str:
    """Pipe-delimited lines the EA parses with StringSplit. Fields never contain '|' (comments are sanitised)."""
    lines = []
    for c in cmds:
        if c['op']=='ORDER_SEND' and 'expires_at_ms' in c:
            raise VenueUnavailable('explicit native deadline cannot be dropped from a legacy frame')
        f = [str(c["id"]), c["op"], c.get("symbol", ""), c.get("type", ""), str(c.get("volume", "")), str(c.get("price", "")), str(c.get("sl", "")), str(c.get("tp", "")), str(c.get("position", "")),
             str(c.get("comment", "")).replace("|", "/")[:31], str(c.get("magic", 0)), str(c.get("deviation", 20))]
        if 'expected_account' in c:
            identity = Mt5Identity(**c['expected_account'])
            f += [str(c.get('order_type','')), identity.login, identity.server.encode().hex(),
                  identity.currency.encode().hex(), 'true' if identity.demo else 'false']
        if c['op'] in ('ORDER_SEND_EXPIRING','MARGIN_QUOTE','SYMBOL_CONTRACT','QUOTE_SNAPSHOT'):
            if 'expected_account' not in c or not _deadline_valid(c.get('expires_at_ms')):
                raise VenueUnavailable('bounded native entry frame requires physical identity and an exact deadline')
            f.append(str(c['expires_at_ms']))
        lines.append("|".join(f))
    return "\n".join(lines) + ("\n" if lines else "")


# ------------------------------------------------------------------ adapter (session side)
#: MT5 `deviation` is in points (the symbol's last quoted digit). P1-TRADE-EXEC-002: this
#: was `max_slippage * 10000`, which on a 5-digit EURUSD quote allowed 0.2 pip and on a
#: 3-digit USDJPY quote 0.002 yen. Brokers that quote differently pass `point_sizes`.
DEFAULT_POINT = Decimal("0.00001")
THREE_DIGIT_POINT = Decimal("0.001")
THREE_DIGIT_PREFIXES = ("XAU", "XAG")
DEFAULT_DEVIATION_POINTS = 20


def point_size(symbol: str, overrides: Optional[dict] = None) -> Decimal:
    sym = symbol.upper()
    if overrides and sym in overrides:
        return Decimal(str(overrides[sym]))
    if sym.endswith("JPY") or sym.startswith(THREE_DIGIT_PREFIXES):
        return THREE_DIGIT_POINT
    return DEFAULT_POINT


def deviation_points(symbol: str, max_slippage: Optional[Decimal], overrides: Optional[dict] = None) -> int:
    """Price-unit slippage bound → whole MT5 points, rounded down so it never widens."""
    if max_slippage is None:
        return DEFAULT_DEVIATION_POINTS
    return max(0, int(max_slippage / point_size(symbol, overrides)))


@dataclass
class Mt5PullAdapter:
    #: P1-TRADE-EXEC-004: the entry types this venue really executes (the EA picks LIMIT only if the comment contains "LIMIT", and the comment is "vati:<intent>", so every order is sent at market today).
    #: The router refuses anything else instead of sending it as a different order.
    supported_entry_types: ClassVar[tuple] = ("MARKET",)
    queue: BridgeQueue
    account_alias: str = "mt5_ea"
    venue: str = "mt5"
    timeout_s: float = 15.0
    clock: Callable[[], int] = field(default=lambda: int(time.time() * 1000))
    poll_s: float = 0.2
    point_sizes: dict = field(default_factory=dict)
    identity: Mt5Identity | None = None

    def _state(self) -> dict:
        st = self.queue.state(self.account_alias)
        if st is None:
            raise VenueUnavailable("MT5 EA has never reported; fail closed")
        if not 0 <= self.clock() - st["updated_ms"] <= STATE_FRESH_MS:
            raise VenueUnavailable(f"MT5 EA snapshot stale ({(self.clock() - st['updated_ms']) // 1000}s); fail closed")
        if self.identity is not None:
            self.identity.validate(st.get('account'))
        return st

    def _await(self, cid: int) -> Optional[dict]:
        deadline = time.monotonic() + self.timeout_s
        while time.monotonic() < deadline:
            r = self.queue.result(cid)
            if r is not None:
                return r
            time.sleep(self.poll_s)
        return None

    def symbol_contract(self,symbol,*,context,deadline_ms):
        from vati.execution.mt5_symbol_contract import read_symbol_contract
        return read_symbol_contract(self,symbol,context=context,deadline_ms=deadline_ms,pull=True)

    def quote_snapshot(self,symbol,*,context,deadline_ms):
        from vati.execution.mt5_quotes import read_quote_snapshot
        return read_quote_snapshot(self,symbol,context=context,deadline_ms=deadline_ms,pull=True)

    def expected_margin(self,symbol,lots,*,price,direction,context,deadline_ms):
        from vati.execution.mt5_expected_margin import read_pull_expected_margin
        return read_pull_expected_margin(self,symbol,lots,price=price,direction=direction,
            context=context,deadline_ms=deadline_ms)

    def sync_account(self) -> AccountState:
        st = self._state();a = st["account"]
        allowed=a.get('trade_allowed',False);hedging=a.get('hedging',True)
        if type(allowed) is not bool or type(hedging) is not bool:
            raise VenueUnavailable('MT5 EA account permissions and topology require explicit boolean facts')
        from vati.funding.mt5 import frame_from_poll,amount,text
        mark=None;self._funding_issue='MT5_NATIVE_CASH_HISTORY_UNAVAILABLE'
        try:
            mark=frame_from_poll(self.account_alias,a,received_ms=st['updated_ms'],nonce=st['source_nonce'])
            self._funding_issue=''
        except (KeyError,TypeError,ValueError,ArithmeticError):pass
        # This is a broker observation, never a fabricated missing-credit zero.
        # Unknown cash history still permits independent protection/reconciliation.
        from vati.execution.native_margin import mt5_margin, mt5_risk_equity
        used,free,level=mt5_margin(a)
        try:
            from vati.execution.mt5_observation import observe_mt5_account
            observation=observe_mt5_account(self.account_alias,self.identity,a,
                source_kind='MT5_SIGNED_EA_POLL',source_nonce=st['source_nonce'],
                source_received_at_ms=st['updated_ms'],observed_at_ms=self.clock())
            equity=mark.net_equity if mark is not None else mt5_risk_equity(a)
            return AccountState(self.account_alias,equity,amount(str(a['balance'])),text(a['currency']),allowed and bool(a.get('login')),
                hedging,int(a.get('server_time_ms',0)),funding_mark=mark,used_margin=used,free_margin=free,margin_level_pct=level,native_observation=observation)
        except (KeyError,TypeError,ValueError,ArithmeticError):
            raise VenueUnavailable('MT5 native account amounts unavailable') from None

    def positions(self) -> list[VenuePosition]:
        out = []
        entries=self.queue.native_entries(self.account_alias)
        for p in self._state()["positions"]:
            comment=str(p.get('comment',''))
            iid=comment[5:] if comment.startswith('vati:') else ''
            bound=[e for e in entries if isinstance(e['result'],dict)
                   and str(e['result'].get('position',''))==str(p['ticket'])
                   and e['result'].get('status') in {'FILLED','PARTIAL'}]
            if bound:
                iid=''
                if len(bound)==1:
                    body=bound[0]['body'];result=bound[0]['result']
                    try:
                        qty=Decimal(str(p['volume']));filled=Decimal(str(result['volume']))
                        if (body['symbol']==p['symbol'] and body['type']==p['type']
                            and comment==body['comment'][:31] and int(p['magic'])==int(body['magic'])
                            and qty.is_finite() and filled.is_finite() and ZERO<qty<=filled<=Decimal(body['volume'])):
                            iid=body['trade_intent_id']
                    except (KeyError,ValueError,ArithmeticError):pass
            elif any(e['body'].get('comment','')[:31]==comment for e in entries):
                iid=''  # a truncated comment alone cannot bind an unsettled claim
            out.append(VenuePosition(str(p["ticket"]), p["symbol"], Direction.LONG if p["type"] == "BUY" else Direction.SHORT, Decimal(str(p["volume"])), Decimal(str(p["price_open"])), Decimal(str(p["sl"])) if p.get("sl") else None,
                                     iid, LossModel.STOP_DISTANCE))
        return out

    def heartbeat(self, *, now_ms: int) -> Health:
        try:
            st = self._state()
        except VenueUnavailable:
            return Health(False, 0, now_ms)
        fresh = st is not None and now_ms - st["updated_ms"] <= STATE_FRESH_MS
        return Health(fresh, int(st["account"].get("server_time_ms", now_ms)) - now_ms if fresh else 0, now_ms)

    def orders(self) -> list[dict]:
        orders=self._state().get('orders')
        if not isinstance(orders,list):
            raise VenueUnavailable('MT5 EA native pending orders unavailable; update and reconcile the terminal observation')
        return orders

    def _entry_body(self, cmd: OrderCommand) -> dict:
        if cmd.account_alias!=self.account_alias or cmd.venue!=self.venue:
            raise VenueUnavailable('native entry account/venue differs from the authenticated adapter')
        if not cmd.command_hash or cmd.sealed().command_hash!=cmd.command_hash:
            raise VenueUnavailable('native entry command seal is invalid')
        return {"symbol": cmd.symbol, "type": "BUY" if cmd.direction is Direction.LONG else "SELL", "volume": str(cmd.quantity), "price": str(cmd.entry_price), "sl": str(cmd.protective_stop), "tp": str(cmd.targets[0]) if cmd.targets else "",
                "comment": f"vati:{cmd.trade_intent_id}"[:31], "magic": int(cmd.decision_hash[:8], 16) % 2_147_483_647, "deviation": str(deviation_points(cmd.symbol, cmd.max_slippage, self.point_sizes)), "order_type": cmd.entry_type,
                'native_command_hash':cmd.command_hash,'trade_intent_id':cmd.trade_intent_id,
                **({'expires_at_ms':cmd.expires_at_ms} if cmd.expires_at_ms is not None else {}),
                **({'expected_account':self.identity.as_dict()} if self.identity is not None else {})}

    def _entry_receipt(self, cmd: OrderCommand, r, *, now_ms: int) -> ExecutionReceipt:
        # Local receipt time is never a substitute for an absent native clock.
        native_clock = r.get('server_time_ms') if isinstance(r,dict) else None
        native_clock = native_clock if type(native_clock) is int and 0<native_clock<=now_ms else 0
        rej = lambda why, status="REJECTED": ExecutionReceipt(cmd.trade_intent_id, cmd.decision_hash, self.venue, status, ZERO, None, cmd.entry_price, cmd.entry_price, cmd.entry_price, False, native_clock, now_ms, reject_reason=why).sealed()  # noqa: E731
        if r is None:
            return rej("EA did not report within timeout; reconcile before retrying", "UNKNOWN")
        if not isinstance(r,dict):return rej('native entry result malformed; reconcile original claim','UNKNOWN')
        status=r.get('status')
        if not isinstance(status,str):return rej('native entry status malformed; reconcile original claim','UNKNOWN')
        if status in {'REJECTED','CANCELLED','EXPIRED'}:
            try:
                qty=Decimal(str(r.get('volume','0')))
                if not qty.is_finite() or qty!=ZERO:return rej('native refusal contradicts reported fill','UNKNOWN')
            except (ValueError,ArithmeticError):return rej('native refusal volume malformed','UNKNOWN')
            return rej(str(r.get('reason') or status),status)
        if status=='ACCEPTED':
            try:
                # The actual EA PLACED response confirms an order, not a fill
                # or a position. Preserve the full native unsigned ticket.
                order=r['order']
                if type(order) is int:
                    valid=0<order<2**64
                else:
                    valid=(type(order) is str and order.isascii() and order.isdecimal()
                           and not order.startswith('0') and len(order)<=20 and int(order)<2**64)
                qty=Decimal(str(r.get('volume','0')))
                if (not valid or not qty.is_finite() or qty!=ZERO
                    or not (r.get('position') is None or r.get('position')==''
                            or (type(r.get('position')) is int and r['position']==0))
                    or ('retcode' in r and (type(r['retcode']) is not int or r['retcode']!=10008))):
                    raise ValueError('contradictory pending acknowledgment')
                stop_confirmed=r.get('sl_confirmed') is True
                return ExecutionReceipt(cmd.trade_intent_id,cmd.decision_hash,self.venue,'ACCEPTED',
                    ZERO,None,cmd.entry_price,cmd.entry_price,cmd.entry_price,stop_confirmed,
                    native_clock,now_ms,broker_order_id=str(order),
                    protective_stop_price=cmd.protective_stop if stop_confirmed else None).sealed()
            except (KeyError,TypeError,ValueError,ArithmeticError):
                return rej('native pending acknowledgment malformed; reconcile original claim','UNKNOWN')
        if status not in {'FILLED','PARTIAL'}:return rej('original native entry result unconfirmed','UNKNOWN')
        try:
            qty=Decimal(str(r['volume']));price=Decimal(str(r['price']))
            if not qty.is_finite() or not ZERO<qty<=cmd.quantity or not price.is_finite() or price<=ZERO:raise ValueError('invalid fill')
            if qty<cmd.quantity:status='PARTIAL'
            stop_confirmed=r.get('sl_confirmed') is True
            return ExecutionReceipt(cmd.trade_intent_id, cmd.decision_hash, self.venue, status, qty, price, cmd.entry_price, Decimal(str(r.get('arrival',r['price']))), cmd.entry_price,
                stop_confirmed,native_clock,now_ms,broker_order_id=str(r.get('order') or ''),broker_position_id=str(r.get('position') or ''),
                protective_stop_price=cmd.protective_stop if stop_confirmed else None).sealed()
        except (KeyError,ValueError,ArithmeticError):return rej('native fill malformed; reconcile original claim','UNKNOWN')

    def _recorded_entry_receipt(self, cmd: OrderCommand, entry: dict, *, now_ms: int) -> ExecutionReceipt:
        """Decode the first durable result, retaining its original local completion."""
        done=entry.get('done_ms');created=entry.get('created_ms');taken=entry.get('taken_ms')
        completed=entry.get('status')=='DONE'
        preflight=(isinstance(entry.get('result'),dict)
                   and entry['result'].get('status') in ('REJECTED','CANCELLED','EXPIRED'))
        valid=(completed and type(created) is int and type(done) is int
               and 0<=created<=done<=now_ms
               and ((taken is None and preflight) or (type(taken) is int and created<=taken<=done)))
        receipt=self._entry_receipt(cmd,entry.get('result') if completed else None,
            now_ms=done if valid else now_ms)
        # A missing/corrupt completion clock must not erase a known native
        # effect, or invent a new completion each time recovery observes it.
        return replace(receipt,received_time_unix_ms=done if valid else None,receipt_hash='').sealed()

    def recover_entry(self, cmd: OrderCommand, *, now_ms: int) -> Optional[ExecutionReceipt]:
        """Read the original claim/result. Never enqueue, emit or retry."""
        body=self._entry_body(cmd)
        rows=[e for e in self.queue.native_entries(self.account_alias,include_clocks=True) if e['body'].get('native_command_hash')==cmd.command_hash]
        if len(rows)!=1 or rows[0]['body']!=body:return None
        # Original result readback is historical, not a current account view.
        # Consumers still need positions()/sync_account() before applying it.
        return self._recorded_entry_receipt(cmd,rows[0],now_ms=now_ms)

    def submit(self, cmd: OrderCommand, *, now_ms: int) -> ExecutionReceipt:
        rej = lambda why: self._entry_receipt(cmd,{'status':'REJECTED','volume':'0','reason':why},now_ms=now_ms)
        if cmd.protective_stop is None:
            return rej("MT5 orders require SL in the same request")
        body=self._entry_body(cmd)
        previous=[e for e in self.queue.native_entries(self.account_alias,include_clocks=True) if e['body'].get('native_command_hash')==cmd.command_hash]
        if previous:
            if len(previous)!=1 or previous[0]['body']!=body:
                return self._entry_receipt(cmd,None,now_ms=now_ms)
            # Current availability cannot rewrite an existing UNKNOWN claim as
            # a new preflight refusal. Return its original result without send.
            return self._recorded_entry_receipt(cmd,previous[0],now_ms=now_ms)
        try:
            state=self._state()
        except VenueUnavailable as exc:
            return rej(str(exc))
        if cmd.expires_at_ms is not None:
            if not _deadline_valid(cmd.expires_at_ms,now_ms=now_ms) or not _deadline_valid(cmd.expires_at_ms,now_ms=self.clock()):
                return rej('explicit native entry deadline invalid or expired; not queued')
            support=state['account'].get('entry_constraints')
            expected={'schema':'van.mt5.ea-entry-constraints/1','explicit_deadline':True,
                      'required_op':'ORDER_SEND_EXPIRING','framed_fields':18}
            if self.identity is None or support!=expected or support.get('explicit_deadline') is not True:
                return rej('native EA cannot enforce the explicit entry deadline; not queued')
        body = self._entry_body(cmd)
        cid = self.queue.enqueue(self.account_alias, "ORDER_SEND_EXPIRING" if cmd.expires_at_ms is not None else "ORDER_SEND", body, now_ms=now_ms)
        self._await(cid)
        # Read back the original SQL claim, rather than trusting a transient
        # waiter return or renewing the caller's pre-dispatch timestamp.
        rows=[e for e in self.queue.native_entries(self.account_alias,include_clocks=True) if e['id']==cid]
        if len(rows)!=1 or rows[0]['body']!=body:
            return self._entry_receipt(cmd,None,now_ms=self.clock())
        return self._recorded_entry_receipt(cmd,rows[0],now_ms=self.clock())

    def modify_stop(self, position_id: str, new_stop: Decimal, *, now_ms: int) -> ExecutionReceipt:
        try:
            pos = next((p for p in self._state()["positions"] if str(p["ticket"]) == str(position_id)), None)
        except VenueUnavailable as exc:
            return ExecutionReceipt("", "", self.venue, "REJECTED", ZERO, None, ZERO, ZERO, ZERO, False, now_ms, now_ms, broker_position_id=position_id, reject_reason=str(exc)).sealed()
        if pos is None:
            return ExecutionReceipt("", "", self.venue, "REJECTED", ZERO, None, ZERO, ZERO, ZERO, False, now_ms, now_ms, broker_position_id=position_id, reject_reason="position not found").sealed()
        old = Decimal(str(pos["sl"])) if pos.get("sl") else None
        if old is not None and ((pos["type"] == "BUY" and new_stop < old) or (pos["type"] == "SELL" and new_stop > old)):
            return ExecutionReceipt("", "", self.venue, "REJECTED", ZERO, None, ZERO, ZERO, ZERO, False, now_ms, now_ms, broker_position_id=position_id, reject_reason="refusing to widen protective stop").sealed()
        cid = self.queue.enqueue(self.account_alias, "MODIFY_SL", {"position": str(position_id), "symbol": pos["symbol"], "sl": str(new_stop), "tp": str(pos.get("tp") or ""),
            **({'expected_account':self.identity.as_dict()} if self.identity is not None else {})}, now_ms=now_ms)
        r = self._await(cid)
        ok=r.get('ok') if r is not None else None
        status='ACCEPTED' if ok is True else 'REJECTED' if ok is False else 'UNKNOWN'
        return ExecutionReceipt("", "", self.venue, status, ZERO, None, ZERO, ZERO, ZERO, ok is True, now_ms, now_ms, broker_position_id=position_id, protective_stop_price=new_stop if ok is True else None, reject_reason="" if ok is True else str((r or {}).get("reason", "EA result unconfirmed; reconcile original request"))).sealed()

    def close(self, position_id: str, quantity: Optional[Decimal], *, now_ms: int, reason: str) -> ExecutionReceipt:
        if self.identity is not None:
            self._state()
        cid = self.queue.enqueue(self.account_alias, "CLOSE", {"position": str(position_id), "volume": str(quantity) if quantity else "", "comment": f"vati-close:{reason}"[:31],
            **({'expected_account':self.identity.as_dict()} if self.identity is not None else {})}, now_ms=now_ms)
        r = self._await(cid)
        if r is None:
            return ExecutionReceipt("", "", self.venue, "UNKNOWN", ZERO, None, ZERO, ZERO, ZERO, False, now_ms, now_ms, broker_position_id=position_id, reject_reason=f"{reason}; EA timeout").sealed()
        return ExecutionReceipt("", "", self.venue, r.get("status", "UNKNOWN"), Decimal(str(r.get("volume", "0"))), Decimal(str(r["price"])) if r.get("price") else None, ZERO, ZERO, ZERO, r.get('sl_confirmed') is True, now_ms, now_ms, broker_position_id=position_id, reject_reason=reason).sealed()


# ------------------------------------------------------------------ pull server (EA side)
class PollThrottle:
    """Per-alias failed-signature counter for the EA poll route."""

    def __init__(self) -> None:
        self._failures: dict[str, list[float]] = {}
        self._locked_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def retry_after(self, alias: str, *, now_s: float) -> int:
        """Seconds the alias must wait, or 0 if it may attempt now."""
        with self._lock:
            until = self._locked_until.get(alias, 0.0)
        return int(until - now_s) + 1 if until > now_s else 0

    def record_failure(self, alias: str, *, now_s: float) -> None:
        with self._lock:
            recent = [f for f in self._failures.get(alias, []) if f > now_s - POLL_WINDOW_S]
            recent.append(now_s)
            if len(recent) >= POLL_MAX_FAILURES:
                self._locked_until[alias] = now_s + POLL_LOCKOUT_S
                recent = []
            self._failures[alias] = recent

    def record_success(self, alias: str) -> None:
        with self._lock:
            self._failures.pop(alias, None)
            self._locked_until.pop(alias, None)


def create_pull_app(queue: BridgeQueue, key_provider: Callable[[str], Optional[bytes]], *, clock: Callable[[], int] = lambda: int(time.time() * 1000)) -> FastAPI:
    app = FastAPI(title="Van MT5 pull bridge", version="1.0.0")
    throttle = PollThrottle()
    app.state.poll_throttle = throttle

    @app.get("/health")
    async def health():
        return {"ok": True, "service": "van-mt5-pull-bridge", "ops": list(OPS)}

    @app.post("/ea/v1/{alias}/poll", response_class=PlainTextResponse)
    async def poll(alias: str, request: Request):
        if not alias.replace("_", "").isalnum():
            raise HTTPException(400, "bad alias")
        identity = None
        allow_entry = True
        if isinstance(key_provider, RegistryKeyProvider):
            key, identity, allow_entry = key_provider.binding(alias)
        else:
            key = key_provider(alias)
        if not key:
            raise HTTPException(404, "unknown alias")
        body = await request.body()
        h = {k.lower(): v for k, v in request.headers.items()}
        ts, nonce, sig = h.get("x-van-ts", ""), h.get("x-van-nonce", ""), h.get("x-van-signature", "")
        now = clock()
        now_s = now / 1000

        def refuse(status: int, detail: str) -> HTTPException:
            """Count the failure; once the alias is locked, say so instead."""
            throttle.record_failure(alias, now_s=now_s)
            wait = throttle.retry_after(alias, now_s=now_s)
            if wait:
                return HTTPException(429, "too many failed attempts", headers={"Retry-After": str(wait)})
            return HTTPException(status, detail)

        if not (ts.isdigit() and nonce and sig) or abs(now // 1000 - int(ts)) > SKEW_S:
            raise refuse(401, "bad or stale signature headers")
        if not hmac.compare_digest(sign_poll(key, ts, nonce, alias, body), sig):
            raise refuse(401, "bad signature")
        throttle.record_success(alias)
        if not queue.nonce_fresh(alias, nonce, now_ms=now):
            raise HTTPException(401, "nonce replayed")
        try:
            data = json.loads(body or b"{}")
        except ValueError:
            raise HTTPException(400, "body must be JSON")
        if (not isinstance(data,dict) or not isinstance(data.get('results',[]),list)
            or not isinstance(data.get('positions',[]),list)
            or ('account' in data and not isinstance(data.get('positions'),list))
            or ('orders' in data and not isinstance(data['orders'],list))
            or ('account' in data and not isinstance(data['account'],dict))):
            raise HTTPException(400, 'native poll body shape is invalid')
        scope = key_provider.poll_binding(alias) if isinstance(key_provider, RegistryKeyProvider) else nullcontext((key,identity,allow_entry))
        with scope as (current_key,identity,allow_entry):
            if current_key is None or not hmac.compare_digest(key,current_key):
                raise HTTPException(409, 'native poll credential binding changed')
            if identity is not None:
                try:
                    identity.validate(data.get('account'))
                except VenueUnavailable:
                    raise HTTPException(409, 'native account identity differs from its registered binding')
            if "account" in data:
                queue.set_state(alias, data.get("account", {}), data.get("positions", []), now_ms=now, nonce=nonce,orders=data.get('orders'))
            for r in data.get("results", []):
                try:
                    queue.complete(alias, r["id"], {k: v for k, v in r.items() if k != "id"}, now_ms=now)
                except (KeyError, ValueError, TypeError):
                    continue
            return format_commands(queue.take_pending(alias, now_ms=now,
                expected_identity=identity, allow_entry=allow_entry))

    return app


class RegistryKeyProvider:
    """Read the key and expected identity from the same registered account."""
    def __init__(self, registry_path):
        self.registry_path = registry_path

    def binding(self, alias):
        try:
            from vati.accounts import AccountRegistry
            from vati.accounts.access import SENDING_MODES
            reg = AccountRegistry(self.registry_path)
            a = reg.get(alias)
            if a.broker != "MT5_EA":
                return None, None, False
            identity = Mt5Identity.from_account(a)
            k = reg.credentials(alias).get("BRIDGE_SIGNING_KEY", "")
            return (k.encode(),identity,a.enabled and a.mode in SENDING_MODES) if len(k)>=32 else (None,None,False)
        except Exception:  # noqa: BLE001 — unknown alias / missing secret = 404, never a stack trace to the EA
            return None, None, False

    def __call__(self, alias):
        return self.binding(alias)[0]

    @contextmanager
    def poll_binding(self, alias):
        from vati.accounts import AccountRegistry
        registry = AccountRegistry(self.registry_path)
        # Same lock order as profile/key writers. Re-read after receiving and
        # verifying the body; a slow poll cannot extend the old permission.
        with registry.operation_lock(alias):
            with registry._mutation_lock():
                yield self.binding(alias)


def key_provider_from_registry(registry_path: str) -> Callable[[str], Optional[bytes]]:
    """Production poll provider includes the current native binding and entry ceiling."""
    return RegistryKeyProvider(registry_path)
