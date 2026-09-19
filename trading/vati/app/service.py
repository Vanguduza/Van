"""Long-running session service (Rev 5 Part F): `python -m vati serve --account <alias>`.

One process per account alias. It resolves the venue adapter and market feed
from the account registry, builds the same DecisionCycle the backtest uses,
runs startup reconciliation, then steps once per closed bar. Every bar also
writes an ACCOUNT_SNAPSHOT and MARKET_DATA_HEALTH event so the owner surface
reads portfolio truth from the ledger, never from memory. A heartbeat file is
refreshed each loop for the commander's status command. Stopping is graceful
on SIGTERM: open positions keep their venue stops; no new orders are placed."""

from __future__ import annotations

import json
import os
import signal
import time
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Callable, Optional

from vati.accounts import Account, AccountRegistry, BrokerKind
from vati.app.cycle import DecisionCycle, SessionConfig
from vati.app.runner import SessionRunner
from vati.arbiter import OpportunityEngine
from vati.core.events import EventKind, make_event
from vati.core.ledger_pg import open_ledger
from vati.execution.base import VenueAdapter
from vati.execution.paper import PaperAdapter
from vati.intelligence.calendar_feed import build_matrix
from vati.market_data.bars import Bar
from vati.market_data.calendars import FX_CALENDAR
from vati.market_data.feeds.lake import TIMEFRAMES_MS, BarLake
from vati.learning.episodes import Environment
from vati.learning.hooks import LearningHooks
from vati.risk import AuthorizationMode, TradingMandate
from vati.risk.serde import contract_from_dict
from vati.strategies import STRATEGY_IMPLEMENTATIONS, CapsuleRegistry

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class ServiceConfig:
    account_alias: str
    symbol: str
    base: str
    quote: str
    timeframe: str
    contract: dict
    mandate: dict
    capsules: list[str]
    round_trip_cost_pct: str = "0.0003"
    registry_path: str = "accounts.json"
    ledger: str = "vati.sqlite"
    lake_root: str = "lake"
    calendar_path: Optional[str] = None
    heartbeat_path: str = "heartbeat.json"
    capsule_dir: Optional[str] = None
    warmup_bars: int = 60
    max_quote_age_ms: int = 5000
    poll_seconds: float = 5.0
    activation_id: str = "vtil-act-unresolved"

    @classmethod
    def load(cls, path: str | Path) -> "ServiceConfig":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(**d)


#: P1-TRADE-008 — which learning environment a session's experience belongs to. Taken from
#: the mandate's authorization mode rather than assumed, so a demo session's episodes are
#: never pooled with a live one's; the two are not comparable evidence.
ENVIRONMENT_FOR_MODE: dict[AuthorizationMode, Environment] = {
    AuthorizationMode.OBSERVE: Environment.SHADOW,
    AuthorizationMode.ADVISOR: Environment.SHADOW,
    AuthorizationMode.DEMO_TRADER: Environment.DEMO,
    AuthorizationMode.SHADOW_TRADER: Environment.SHADOW,
    AuthorizationMode.LIMITED_LIVE: Environment.LIMITED_LIVE,
    AuthorizationMode.AUTONOMOUS_LIVE: Environment.LIVE,
    AuthorizationMode.HALTED: Environment.SHADOW,
}


def build_adapter(account: Account, registry: AccountRegistry, *, equity_hint: Decimal = Decimal("10000")) -> VenueAdapter:
    """Adapter from the account record. Credentials are resolved inside the transport and never returned."""
    if account.broker == BrokerKind.PAPER:
        return PaperAdapter(venue=account.router_venue, account_alias=account.alias, equity=equity_hint)
    if account.broker == BrokerKind.MT5:
        from vati.execution.mt5_bridge import Mt5BridgeAdapter, Mt5BridgeClient
        from vati.execution.transports.mt5_http import Mt5HttpTransport
        secrets = registry.credentials(account.alias)
        key = secrets.get("BRIDGE_SIGNING_KEY", "")
        if not key:
            raise RuntimeError(f"{account.alias}: BRIDGE_SIGNING_KEY missing from secrets")
        transport = Mt5HttpTransport(account.bridge_url, ca_file=secrets["BRIDGE_CA_FILE"], client_cert=secrets.get("BRIDGE_CLIENT_CERT"), client_key=secrets.get("BRIDGE_CLIENT_KEY"))
        return Mt5BridgeAdapter(Mt5BridgeClient(signing_key=key.encode(), transport=transport), account_alias=account.alias, venue=account.router_venue)
    if account.broker == BrokerKind.DERIV:
        from vati.execution.deriv import DerivAdapter
        from vati.execution.transports.deriv_ws import DerivWebSocketTransport
        transport = DerivWebSocketTransport(app_id=account.server or "1089", token_provider=lambda: registry.credentials(account.alias).get("DERIV_API_TOKEN") or registry.credentials(account.alias).get("TOKEN", ""),
                                            endpoint=account.bridge_url or "wss://ws.derivws.com/websockets/v3")
        return DerivAdapter(venue=account.router_venue, account_alias=account.alias, transport=transport)
    if account.broker == BrokerKind.CTRADER:
        from vati.execution.ctrader import DEMO_HOST, LIVE_HOST, CtraderAdapter, CtraderTransport
        secrets = registry.credentials(account.alias)
        for k in ("CTRADER_CLIENT_ID", "CTRADER_CLIENT_SECRET", "CTRADER_ACCESS_TOKEN"):
            if not secrets.get(k):
                raise RuntimeError(f"{account.alias}: {k} missing from secrets")
        host = LIVE_HOST if (account.server or "demo").lower() == "live" or not account.demo else DEMO_HOST
        return CtraderAdapter(CtraderTransport(host=host), client_id=secrets["CTRADER_CLIENT_ID"], client_secret_provider=lambda: registry.credentials(account.alias)["CTRADER_CLIENT_SECRET"],
                              access_token_provider=lambda: registry.credentials(account.alias)["CTRADER_ACCESS_TOKEN"], ctid_trader_account_id=int(account.login), account_alias=account.alias, venue=account.router_venue)
    if account.broker == BrokerKind.MT5_EA:
        from vati.execution.mt5_pull import Mt5PullAdapter, open_bridge_queue
        secrets = registry.credentials(account.alias)
        if not secrets.get("BRIDGE_SIGNING_KEY"):
            raise RuntimeError(f"{account.alias}: BRIDGE_SIGNING_KEY missing from secrets")
        return Mt5PullAdapter(open_bridge_queue(secrets.get("BRIDGE_QUEUE", "")), account_alias=account.alias, venue=account.router_venue)
    if account.broker == BrokerKind.ZSE_OWNER_TICKET:
        from vati.execution.zse_ticket import OwnerTicketAdapter
        return OwnerTicketAdapter(equity=equity_hint, csd_verified=False)
    raise RuntimeError(f"no adapter for broker {account.broker}")


@dataclass
class SessionService:
    cfg: ServiceConfig
    bar_source: Callable[[int], list[Bar]]          # now_ms → closed bars history (lake / feed)
    clock: Callable[[], int] = lambda: int(time.time() * 1000)
    adapter: Optional[VenueAdapter] = None
    stop_requested: bool = False
    cycles: int = 0
    last_bar_end_ms: int = 0
    runner: Optional[SessionRunner] = None
    _ledger: object = None
    _started_ms: int = 0

    def build(self) -> "SessionService":
        c = self.cfg
        registry = AccountRegistry(c.registry_path)
        account = registry.get(c.account_alias)
        if not account.enabled:
            raise RuntimeError(f"account {account.alias} is disabled")
        mandate = TradingMandate.from_mapping(c.mandate)
        if mandate.mode.value in ("LIMITED_LIVE", "AUTONOMOUS_LIVE") and account.demo:
            raise RuntimeError("mandate is live but the account record is demo: refuse to start with mismatched safety identity")
        if mandate.account_alias != account.alias:
            raise RuntimeError(f"mandate is signed for account {mandate.account_alias!r} but the session is for {account.alias!r}: refuse to start (every intent would be ACCOUNT_MISMATCH)")
        self.adapter = self.adapter or build_adapter(account, registry)
        self._ledger = open_ledger(c.ledger)
        contract = contract_from_dict({**c.contract, "venue": account.router_venue})   # the account decides the venue; a contract copied from another venue must not silently mismatch
        scfg = SessionConfig(symbol=c.symbol, base=c.base, quote=c.quote, venue=account.router_venue, account_alias=account.alias, contract=contract, mandate_dict=c.mandate,
                             warmup_bars=c.warmup_bars, max_quote_age_ms=c.max_quote_age_ms, session_id=f"{account.alias}:{c.symbol}:{int(self.clock())}", activation_id=c.activation_id,
                             software_stops=account.broker == BrokerKind.ZSE_OWNER_TICKET)
        reg = CapsuleRegistry.load_dir(c.capsule_dir or ROOT / "strategies" / "registry")
        impl = {sid: STRATEGY_IMPLEMENTATIONS[sid.rsplit("-", 1)[0]](strategy_id=sid) for sid in c.capsules}
        engine = OpportunityEngine(reg, impl, mandate)
        cost = Decimal(c.round_trip_cost_pct)
        # P1-TRADE-008 — `learning` was never passed here, so capsule-health demotion,
        # broker-liquidity learning and experience artefacts existed only in backtests.
        # The environment is taken from the mandate's mode rather than assumed, because a
        # DEMO session's experience must not be pooled with a LIVE one's.
        #
        # This is safe to wire because the effects it can have are already bounded: the
        # LearningBoundary permits reduce-only adjustments, and a demotion moves a capsule
        # towards SHADOW or DEGRADED, never towards more authority. That boundary is what
        # made this a wiring job rather than a design one.
        learning = LearningHooks(
            environment=ENVIRONMENT_FOR_MODE[mandate.mode],
            broker=str(getattr(account.broker, "value", account.broker)).lower(),
        )
        cycle = DecisionCycle(cfg=scfg, adapter=self.adapter, ledger=self._ledger, engine=engine, cost_fn=lambda st: cost, calendar=FX_CALENDAR, events=build_matrix(c.calendar_path), learning=learning)
        self.learning = learning
        self.runner = SessionRunner(cycle)
        return self

    # ------------------------------------------------------------------ loop
    def _heartbeat(self, status: str, extra: Optional[dict] = None) -> None:
        hb = {"account_alias": self.cfg.account_alias, "symbol": self.cfg.symbol, "status": status, "cycles": self.cycles, "last_bar_end_ms": self.last_bar_end_ms,
              "permit_new_orders": bool(self.runner and self.runner.permit_new_orders), "kill_switch": sorted(t.value for t in self.runner.cycle.kill.active) if self.runner else [],
              "updated_ms": self.clock(), "pid": os.getpid(), **(extra or {})}
        Path(self.cfg.heartbeat_path).write_text(json.dumps(hb))

    def _account_snapshot(self, now_ms: int) -> None:
        r = self.runner
        assert r is not None
        acct = r.cycle.adapter.sync_account()
        hb = r.cycle.adapter.heartbeat(now_ms=now_ms)
        positions = r.cycle.adapter.positions()
        r.cycle.ledger.append(make_event(EventKind.ACCOUNT_SNAPSHOT, "vati-service", {
            "account_alias": acct.account_alias, "equity": str(acct.equity), "balance": str(acct.balance), "currency": acct.currency, "verified": acct.verified,
            "connected": hb.connected, "server_offset_ms": hb.server_offset_ms, "open_positions": len(positions), "peak_equity": str(r.cycle.peak_equity), "day_start_equity": str(r.cycle.day_start_equity),
            "week_start_equity": str(r.cycle.week_start_equity), "kill_switch": sorted(t.value for t in r.cycle.kill.active), "mode": r.cycle.mandate.mode.value,
        }, event_time_ms=now_ms, received_time_ms=now_ms, correlation_id=r.cycle.cfg.session_id))

    def start(self) -> None:
        assert self.runner is not None, "build() first"
        now = self.clock()
        self._started_ms = now
        rep = self.runner.startup(now_ms=now)
        # P0-TRADE-003 — an owner halt written before this process started used to be
        # discarded, so a restart undid it. Checked here, before the first bar, so the
        # session never runs a cycle believing it is permitted when it is not.
        self._observe_owner_halt(now)
        self._account_snapshot(now)
        self._heartbeat("STARTED", {"reconciliation": rep.counts()})

    def _observe_owner_halt(self, now_ms: int) -> None:
        """An OWNER_HALT written by the gateway or the commander (A4) stops new orders.

        P0-TRADE-003 — this filtered events at or after `self._started_ms`, so restarting
        the session discarded an active owner halt. `restart_service` is an exposed
        commander command, which made "halt trading" undoable by the same interface that
        was meant to enforce it.

        The filter is now the *latest* OWNER_HALT and whether anything cleared it since,
        which is a property of the ledger rather than of this process. A halt therefore
        survives a restart, and a clear is what ends it — as it always was for a session
        that happened to stay up.
        """
        assert self.runner is not None
        from vati.risk.contracts import KillSwitchTrigger
        if KillSwitchTrigger.OWNER_HALT in self.runner.cycle.kill.active:
            return
        latest_halt = None
        for ev in self.runner.cycle.ledger.iter(EventKind.KILL_SWITCH):
            if ev.producer == "vati-runner":
                continue
            if ev.payload.get("trigger") != "OWNER_HALT":
                continue
            if ev.payload.get("cleared"):
                latest_halt = None
                continue
            latest_halt = ev
        if latest_halt is None:
            return
        self.runner.cycle.kill.trip(KillSwitchTrigger.OWNER_HALT, now_ms)
        self.runner.permit_new_orders = False
        self.runner.cycle.ledger.append(make_event(
            EventKind.SESSION, "vati-service",
            {"event": "OWNER_HALT_OBSERVED", "source_event": latest_halt.hash,
             "halt_event_time_ms": latest_halt.event_time_ms,
             "observed_after_restart": latest_halt.event_time_ms < self._started_ms},
            event_time_ms=now_ms, received_time_ms=now_ms,
            correlation_id=self.runner.cycle.cfg.session_id,
        ))

    def step_once(self) -> Optional[str]:
        """One loop iteration; returns the cycle decision when a new bar closed, else None."""
        assert self.runner is not None
        now = self.clock()
        self._observe_owner_halt(now)
        bars = self.bar_source(now)
        if not bars:
            self.runner.cycle.ledger.append(make_event(EventKind.MARKET_DATA_HEALTH, "vati-service", {"symbol": self.cfg.symbol, "state": "NO_DATA"}, event_time_ms=now, received_time_ms=now, correlation_id=self.cfg.symbol))
            self._heartbeat("NO_DATA")
            return None
        last = bars[-1]
        if last.end_ms <= self.last_bar_end_ms:
            self._heartbeat("WAITING_FOR_BAR")
            return None
        age = now - last.end_ms
        state = "LIVE" if age <= 2 * TIMEFRAMES_MS[self.cfg.timeframe] else ("DELAYED" if age <= 6 * TIMEFRAMES_MS[self.cfg.timeframe] else "STALE")
        self.runner.cycle.ledger.append(make_event(EventKind.MARKET_DATA_HEALTH, "vati-service", {"symbol": self.cfg.symbol, "state": state, "bar_age_ms": age, "bars": len(bars)}, event_time_ms=now, received_time_ms=now, correlation_id=self.cfg.symbol))
        res = self.runner.on_bar(bars, now_ms=now, last_quote_ms=last.end_ms if state == "LIVE" else last.end_ms - age)
        self.last_bar_end_ms = last.end_ms
        self.cycles += 1
        self._account_snapshot(now)
        self._heartbeat("RUNNING", {"last_decision": res.decision, "data_state": state})
        return res.decision

    def run_forever(self) -> int:
        def _stop(*_):
            self.stop_requested = True
        signal.signal(signal.SIGTERM, _stop)
        signal.signal(signal.SIGINT, _stop)
        self.start()
        while not self.stop_requested:
            try:
                self.step_once()
            except Exception as exc:  # noqa: BLE001 — a loop fault must not drop protection; it is logged and the loop continues fail-closed
                now = self.clock()
                self.runner.cycle.ledger.append(make_event(EventKind.SESSION, "vati-service", {"event": "LOOP_FAULT", "error": str(exc)[:300]}, event_time_ms=now, received_time_ms=now, correlation_id=self.runner.cycle.cfg.session_id))
                self._heartbeat("FAULT", {"error": str(exc)[:200]})
            time.sleep(self.cfg.poll_seconds)
        now = self.clock()
        self.runner.cycle.ledger.append(make_event(EventKind.SESSION, "vati-service", {"event": "STOPPED", "open_positions": len(self.runner.cycle.adapter.positions())}, event_time_ms=now, received_time_ms=now, correlation_id=self.runner.cycle.cfg.session_id))
        self._heartbeat("STOPPED")
        return 0


def lake_bar_source(lake: BarLake, symbol: str, timeframe: str, *, lookback_bars: int = 400) -> Callable[[int], list[Bar]]:
    def src(now_ms: int) -> list[Bar]:
        bars, _ = lake.read(symbol, timeframe, end_ms=now_ms + 1)
        return [b for b in bars if b.end_ms <= now_ms][-lookback_bars:]
    return src
