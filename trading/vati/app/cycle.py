"""The decision cycle (Rev 2 §61): one pass per bar/tick for one instrument.

   VERIFY DATA → MARKET STATE → OPPORTUNITY → RISK AUTHORITY → ROUTER →
   PROTECT → (marks) → RECONCILE → TCA → REVIEW → VTIL PROPOSE

The same class drives backtests (PaperAdapter over historical bars) and live
sessions (real adapter over a feed), which is what makes backtest-to-live parity
a property of the code rather than a hope."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Callable, Optional, Sequence

from vati.arbiter import OpportunityEngine
from vati.core.canonical import canonical_hash
from vati.core.events import EventKind, make_event
from vati.core.ledger import Ledger
from vati.execution.base import StopMode, VenueAdapter
from vati.execution.protection import ProtectionManager
from vati.execution.pretrade import MarketReference, PreTradeControls
from vati.execution.route_registry import RouteRegistry
from vati.execution.style_selector import ExecutionStyleSelector, LiquidityView
from vati.execution.router import ExecutionRouter, RouterError
from vati.execution.review import review_trade
from vati.execution.tca import compute_tca
from vati.execution.reconciliation import LedgerPosition, reconcile
from vati.intelligence.events import EventMatrix, EventWindowState
from vati.intelligence.market_state import MarketState, build_market_state
from vati.intelligence.regimes import RegimeEngine
from vati.learning.hooks import LearningHooks, to_payload
from vati.market_data.bars import Bar
from vati.market_data.calendars import MarketCalendar
from vati.observability import metrics
from vati.risk import Decision, KillSwitch, MarketIntegrityState, OpenPosition, RiskAuthority, RiskSnapshot, SymbolContract, TradingMandate
from vati.risk.contracts import Direction, LossModel, StrategyState
from vati.risk.serde import intent_to_dict, snapshot_to_dict
from vati.strategies.base import StrategyContext
from vati.arbiter.strategy_arbiter import ACTIVE_STATES
from vati.vtil import AdmissionLedger

ZERO = Decimal("0")


@dataclass
class SessionConfig:
    symbol: str
    base: str
    quote: str
    venue: str
    account_alias: str
    contract: SymbolContract
    mandate_dict: dict
    #: Explicit market-state identity. Production services always set this from
    #: ServiceConfig; UNKNOWN is retained only for legacy/research callers.
    timeframe: str = "UNKNOWN"
    warmup_bars: int = 60
    max_quote_age_ms: int = 5000
    targets_from_signal: bool = True
    time_in_force: str = "DAY"
    session_id: str = "session"
    activation_id: str = "vtil-act-unresolved"
    software_stops: bool = False   # ZSE: no venue stop


@dataclass
class CycleResult:
    bar_end_ms: int
    state_hash: str
    decision: str            # NO_TRADE | WAIT | SKIP | REJECTED:<code> | APPROVED | REDUCED | ROUTER_REFUSED
    reason: str
    approved_size: Decimal = ZERO


class DecisionCycle:
    def __init__(self, *, cfg: SessionConfig, adapter: VenueAdapter, ledger: Ledger, engine: OpportunityEngine, cost_fn: Callable[[MarketState], Decimal],
                 calendar: MarketCalendar, events: EventMatrix, regime_engine: Optional[RegimeEngine] = None, kill_switch: Optional[KillSwitch] = None,
                 admission: Optional[AdmissionLedger] = None, ctx_fn: Optional[Callable[[MarketState, Decimal], StrategyContext]] = None,
                 learning: Optional[LearningHooks] = None) -> None:
        self.cfg, self.adapter, self.ledger, self.engine, self.cost_fn, self.calendar, self.events = cfg, adapter, ledger, engine, cost_fn, calendar, events
        self.learning = learning
        self.regime = regime_engine or RegimeEngine()
        self.kill = kill_switch or KillSwitch()
        self.mandate = TradingMandate.from_mapping(cfg.mandate_dict)
        self.authority = RiskAuthority(self.mandate)
        self.protection = ProtectionManager()
        self.routes = RouteRegistry(ledger=ledger)
        self.routes.refresh(
            account_alias=cfg.account_alias,
            adapter_id=cfg.venue,
            contracts={cfg.symbol.upper(): cfg.contract},
            now_ms=0,
            source="decision_cycle_init",
        )
        self.pretrade = PreTradeControls(routes=self.routes, ledger=ledger)
        self.style_selector = ExecutionStyleSelector(ledger=ledger)
        self.router = ExecutionRouter(
            ledger=ledger, adapters={cfg.venue: adapter}, kill_switch=self.kill,
            protection=self.protection, route_registry=self.routes,
            pretrade_controls=self.pretrade, style_selector=self.style_selector,
            enforce_rev51_controls=True)
        self.admission = admission or AdmissionLedger()
        self.ctx_fn = ctx_fn or (lambda st, cost: StrategyContext(round_trip_cost_pct=cost))
        self.peak_equity = ZERO
        self.day_start_equity = ZERO
        self.week_start_equity = ZERO
        self.consecutive_losses = 0
        self.integrity = MarketIntegrityState.NORMAL
        self.reviews: list = []
        self._closed_seen = 0
        self._entries: dict[str, dict] = {}   # trade_intent_id → {entry, stop, direction, strategy_id, cost_pct}

    # --------------------------------------------------------------- helpers
    def _log(self, kind: EventKind, payload: dict, *, now_ms: int, corr: str = "") -> None:
        self.ledger.append(make_event(kind, "vati-cycle", payload, event_time_ms=now_ms, received_time_ms=now_ms, correlation_id=corr or self.cfg.session_id))

    def _open_positions(self) -> tuple[OpenPosition, ...]:
        out = []
        c = self.cfg.contract
        for p in self.adapter.positions():
            stop = p.stop_price if p.stop_price is not None else self.protection.rules.get(p.position_id, None)
            stop_price = stop.stop if hasattr(stop, "stop") else stop
            if p.loss_model is LossModel.ILLIQUID_EQUITY:
                out.append(OpenPosition(p.symbol, p.direction, p.quantity, abs(p.entry_price - (stop_price or p.entry_price)), Decimal(1), c.base_currency, c.quote_currency, "", False, LossModel.ILLIQUID_EQUITY, ZERO, p.entry_price * c.liquidity_haircut))
            else:
                out.append(OpenPosition(p.symbol, p.direction, p.quantity, abs(p.entry_price - stop_price) if stop_price is not None else ZERO, c.value_per_price_unit_per_lot, c.base_currency, c.quote_currency, "", stop_price is not None))
        return tuple(out)

    def _reconciliation_ok(self, *, account_verified: bool) -> bool:
        """P0-TRADE-002 — this was hardcoded True, so RECONCILIATION_FAILED could not fire.

        Reconciled per bar against what the venue reports now, not once at startup. The
        ledger positions come from the entries this cycle actually opened, which is the
        only set the cycle can speak for; a position the venue holds that this cycle never
        opened is an orphan, and `reconcile` already treats it as blocking.
        """
        ledger_positions = [
            LedgerPosition(
                trade_intent_id=iid,
                symbol=self.cfg.symbol,
                quantity=entry.get("quantity", ZERO),
                stop_price=entry.get("stop"),
                software_stop=bool(self.cfg.software_stops),
            )
            for iid, entry in self._entries.items()
            if entry.get("open", True)
        ]
        try:
            report = reconcile(
                ledger_positions, self.adapter.positions(), account_verified=account_verified
            )
        except Exception:  # noqa: BLE001 — a reconciliation that cannot run has not passed
            return False
        return report.permit_new_orders

    def _risk_store_ok(self) -> bool:
        """P0-TRADE-002 — hardcoded True, so RISK_STORE_UNAVAILABLE could not fire.

        The risk store is the ledger: without it the authority cannot know what is open,
        what has been lost today, or whether this decision has already been made. A ledger
        that will not answer is a risk store that is unavailable.
        """
        try:
            return bool(self.ledger.verify_chain()[0])
        except Exception:  # noqa: BLE001 — an unreadable ledger is not a healthy one
            return False

    def _tier1_blackout(self, *, now_ms: int) -> bool:
        """P0-TRADE-002 — hardcoded False, so EVENT_BLACKOUT could not fire.

        The event matrix already computes this and the market state already carries it;
        nothing joined the two to the snapshot the authority reads.
        """
        try:
            window, _event = self.events.state_at(now_ms, self.cfg.base, self.cfg.quote)
        except Exception:  # noqa: BLE001 — an event matrix that cannot answer fails closed
            return True
        return window in (EventWindowState.PRE_BLACKOUT, EventWindowState.POST_BLACKOUT)

    def snapshot(self, *, now_ms: int, quote_age_ms: int) -> RiskSnapshot:
        acct = self.adapter.sync_account()
        if self.peak_equity == ZERO:
            self.peak_equity = self.day_start_equity = self.week_start_equity = acct.equity
        self.peak_equity = max(self.peak_equity, acct.equity)
        hb = self.adapter.heartbeat(now_ms=now_ms)
        return RiskSnapshot(now_unix=now_ms // 1000, account_alias=acct.account_alias, account_verified=acct.verified, equity=acct.equity, balance=acct.balance,
                            peak_equity=self.peak_equity, day_start_equity=self.day_start_equity, week_start_equity=self.week_start_equity, consecutive_losses=self.consecutive_losses,
                            open_positions=self._open_positions(), symbol_contract=self.cfg.contract, quote_age_ms=quote_age_ms, max_quote_age_ms=self.cfg.max_quote_age_ms,
                            broker_connected=hb.connected,
                            reconciliation_ok=self._reconciliation_ok(account_verified=acct.verified),
                            clock_sync_ok=abs(hb.server_offset_ms) < 2000,
                            risk_store_ok=self._risk_store_ok(),
                            market_integrity=self.integrity,
                            tier1_event_blackout_active=self._tier1_blackout(now_ms=now_ms),
                            margin_level_pct=acct.margin_level_pct,
                            free_margin=acct.free_margin,
                            kill_switch_triggers=frozenset(self.kill.active))

    def roll_day(self, equity: Decimal, *, new_week: bool = False) -> None:
        self.day_start_equity = equity
        if new_week:
            self.week_start_equity = equity

    # --------------------------------------------------------------- one step
    def step(self, bars: Sequence[Bar], *, now_ms: int, last_quote_ms: int) -> CycleResult:
        cfg = self.cfg
        if len(bars) < cfg.warmup_bars:
            return CycleResult(bars[-1].end_ms if bars else now_ms, "", "NO_TRADE", "warmup")
        state = build_market_state(symbol=cfg.symbol, base=cfg.base, quote=cfg.quote, bars=bars, regime_engine=self.regime, calendar=self.calendar, events=self.events,
                                   integrity=self.integrity, now_ms=now_ms, last_quote_ms=last_quote_ms, activation_id=cfg.activation_id,
                                   timeframe=cfg.timeframe)
        cost = self.cost_fn(state)
        self._log(EventKind.MARKET_STATE, {"state": state.as_dict(), "cost_pct": str(cost)}, now_ms=now_ms)
        ctx = self.ctx_fn(state, cost)
        regime_label = ctx.zse.currency_regime.value if ctx.zse is not None else state.regime.trend.value
        oa = self.engine.assess(state, ctx, regime_label=state.regime.trend.value, currency_regime_label=(ctx.zse.currency_regime.value if ctx.zse is not None else None),
                                account_alias=cfg.account_alias, venue=cfg.venue,
                                # P0-TRADE-005 — this was f"{cfg.session_id}:{state.as_of_ms}",
                                # and session_id embeds the process start timestamp. A crash
                                # and restart on the same bar produced a different key, so
                                # neither the in-process set nor the ledger-seeded router set
                                # recognised the duplicate and the order could be placed twice.
                                # The seed is now the account, the symbol and the bar, all of
                                # which are the same on both sides of a restart.
                                idempotency_seed=f"{cfg.account_alias}:{cfg.symbol}:{state.as_of_ms}")
        self._log(EventKind.OPPORTUNITY_ASSESSMENT, {"symbol": cfg.symbol, "decision": oa.decision, "reason": oa.abstain_reason, "candidates": list(oa.candidates), "assessment_hash": oa.assessment_hash}, now_ms=now_ms)
        metrics.inc("vati_cycles_total", symbol=cfg.symbol)
        if oa.intent is None:
            return CycleResult(state.as_of_ms, state.state_hash, oa.decision, oa.abstain_reason)
        intent = oa.intent
        snap = self.snapshot(now_ms=now_ms, quote_age_ms=state.quote_age_ms)
        decision = self.authority.evaluate_safe(intent, snap)
        self._log(EventKind.RISK_DECISION, {"inputs": {"intent": intent_to_dict(intent), "snapshot": snapshot_to_dict(snap), "mandate": cfg.mandate_dict}, "decision": decision.to_dict()}, now_ms=now_ms, corr=intent.trade_intent_id)
        metrics.inc("vati_decisions_total", outcome=decision.decision.value)
        if decision.decision is Decision.REJECTED:
            return CycleResult(state.as_of_ms, state.state_hash, f"REJECTED:{decision.reason_code}", decision.reason_detail)
        # P1-TRADE-007 and P4-TRADE-009 — this used to be an empty assignment, a loop
        # with a bare `pass`, and a single target re-derived from expected_gross_move_pct,
        # which discarded whatever exit plan the winning strategy had actually produced.
        # The assessment now carries the signal's own targets.
        targets = tuple(oa.targets)
        if not targets and intent.expected_gross_move_pct is not None:
            # A strategy that declares an expected move and no explicit target still gets
            # one, which is the behaviour the old code always applied. It is a fallback
            # now rather than the rule.
            t = intent.entry * (Decimal(1) + intent.expected_gross_move_pct) if intent.direction is Direction.LONG else intent.entry * (Decimal(1) - intent.expected_gross_move_pct)
            targets = (t,)
        try:
            # Refresh route truth at the decision instant so the registry cannot
            # age out while the session continues to run.
            self.routes.refresh(
                account_alias=cfg.account_alias, adapter_id=cfg.venue,
                contracts={cfg.symbol.upper(): cfg.contract}, now_ms=now_ms,
                source="decision_cycle",
            )
            rec = self.router.execute(
                intent, decision, self.mandate, now_ms=now_ms,
                stop_mode=StopMode.SOFTWARE if cfg.software_stops else StopMode.VENUE,
                targets=targets, time_in_force=cfg.time_in_force, entry_type="LIMIT",
                market_reference=MarketReference(
                    last_price=state.features.close,
                    mark_age_ms=state.quote_age_ms,
                    max_mark_age_ms=cfg.max_quote_age_ms,
                ),
                liquidity=LiquidityView(),
            )
        except RouterError as exc:
            self._log(EventKind.SESSION, {"router_refused": str(exc)}, now_ms=now_ms, corr=intent.trade_intent_id)
            return CycleResult(state.as_of_ms, state.state_hash, "ROUTER_REFUSED", str(exc), decision.approved_size)
        if rec.status in ("FILLED", "PARTIAL", "ACCEPTED", "OWNER_EXECUTED"):
            self._entries[intent.trade_intent_id] = {"entry": rec.average_fill or intent.entry, "stop": intent.stop, "direction": intent.direction, "strategy_id": intent.strategy_id, "cost_pct": cost, "decision_price": intent.entry}
            if rec.average_fill is not None and rec.filled_qty > ZERO:
                tca = compute_tca(rec, direction=intent.direction, qty=rec.filled_qty, value_per_unit=cfg.contract.value_per_price_unit_per_lot if cfg.contract.loss_model is LossModel.STOP_DISTANCE else Decimal(1), modelled_cost_pct=cost)
                tca_payload = tca.as_dict()
                if self.learning is not None:
                    tca_payload |= {
                        "learning_environment": self.learning.environment.value,
                        "broker": self.learning.broker,
                        "symbol": cfg.symbol,
                        "session": state.session.value,
                        "event_window": state.event_window.value,
                        "rejected": False,
                    }
                self._log(EventKind.TCA_RECORD, tca_payload, now_ms=now_ms, corr=intent.trade_intent_id)
                self._entries[intent.trade_intent_id]["cost_ratio"] = tca.cost_ratio
                if self.learning is not None:
                    self.learning.on_tca(symbol=cfg.symbol, session=state.session.value, event_window=state.event_window.value, cost_ratio=tca.cost_ratio, slippage=tca.slippage)
                    self.engine.m.broker_liquidity[cfg.symbol] = self.learning.broker_liquidity(cfg.symbol)
        return CycleResult(state.as_of_ms, state.state_hash, decision.decision.value, "", decision.approved_size)

    # ------------------------------------------------------- marks and exits
    def mark(self, bid: Decimal, ask: Decimal, *, now_ms: int) -> None:
        cfg = self.cfg
        receipts = list(self.router.apply_exits(cfg.venue, cfg.symbol, bid, ask, now_ms=now_ms))
        if hasattr(self.adapter, "mark"):
            receipts += self.adapter.mark(cfg.symbol, bid, ask, now_ms=now_ms)  # type: ignore[attr-defined]
        for r in receipts:
            if r.status == "FILLED" and r.trade_intent_id in self._entries and r.reject_reason not in ("TRAIL", "BREAK_EVEN"):
                self._on_close(r.trade_intent_id, r.average_fill, r.reject_reason, now_ms)
                self.protection.forget(r.broker_position_id)

    def _on_close(self, intent_id: str, exit_price: Optional[Decimal], reason: str, now_ms: int) -> None:
        e = self._entries.pop(intent_id, None)
        if e is None or exit_price is None:
            return
        closed = getattr(self.adapter, "closed", None)
        pnl = ZERO
        if closed:
            for c in reversed(closed):
                if c["intent"] == intent_id:
                    pnl = c["pnl"]; break
        self.consecutive_losses = self.consecutive_losses + 1 if pnl < ZERO else 0
        rv = review_trade(trade_intent_id=intent_id, strategy_id=e["strategy_id"], entry=e["entry"], exit_price=exit_price, stop=e["stop"] or e["entry"], direction_long=e["direction"] is Direction.LONG,
                          pnl=pnl, thesis_correct=pnl > ZERO, process_ok=True, exit_reason=reason)
        self.reviews.append(rv)
        self._log(EventKind.TRADE_REVIEW, {k: (v.value if hasattr(v, "value") else (str(v) if isinstance(v, Decimal) else (list(v) if isinstance(v, tuple) else v))) for k, v in asdict(rv).items()}, now_ms=now_ms, corr=intent_id)
        self.admission.propose(rv.artifact_hash, knowledge_class="TRADE_EXPERIENCE", proposed_by=rv.proposed_by, trust_tier="T0_VAN_TRADING_POLICY")
        metrics.inc("vati_trades_closed_total", outcome=rv.outcome.value)
        if self.learning is not None:
            self._learn(intent_id, rv, e.get("cost_ratio", Decimal(1)), now_ms)

    # ------------------------------------------------------------ learning
    def _learn(self, intent_id: str, rv, cost_ratio: Decimal, now_ms: int) -> None:
        """Observe the closed trade; apply only LearningBoundary-checked, reduce-only effects."""
        assert self.learning is not None
        ep, adj = self.learning.on_review(self.ledger, trade_intent_id=intent_id, strategy_id=rv.strategy_id, r_multiple=rv.r_multiple, process_ok=rv.process_ok, cost_ratio=cost_ratio)
        if ep is not None:
            self._log(EventKind.TRADE_EXPERIENCE_ARTIFACT, to_payload(ep), now_ms=now_ms, corr=intent_id)
            self.admission.propose(ep.artifact_hash, knowledge_class="TRADE_EXPERIENCE", proposed_by="vati-learning", trust_tier="T0_VAN_TRADING_POLICY")
        if adj is None:
            return
        self.engine.m.capsule_health[rv.strategy_id] = adj.multiplier
        if adj.demote_to:
            cap = self.engine.registry.get(rv.strategy_id)
            # Live capsules step down to SHADOW (observe, no orders); pre-live capsules become DEGRADED (inactive).
            target = StrategyState.SHADOW if cap.state in (StrategyState.LIMITED_LIVE, StrategyState.CERTIFIED_LIVE) else StrategyState.DEGRADED
            if cap.state in ACTIVE_STATES and cap.state is not target:
                new = self.engine.registry.demote(rv.strategy_id, target, reason=f"learning health {adj.multiplier}: {'; '.join(self.learning.health.verdict(rv.strategy_id).reasons)}")
                self.learning.demotions.append((rv.strategy_id, target.value))
                self._log(EventKind.CAPSULE_STATE, {"strategy_id": rv.strategy_id, "from": cap.state.value, "to": target.value, "capsule_hash": new.capsule_hash, "supersedes": cap.capsule_hash,
                                                    "capsule": new.data, "by": "vati-learning", "authority": "AUTOMATIC_DEMOTION_ONLY"}, now_ms=now_ms, corr=intent_id)
                metrics.inc("vati_capsule_demotions_total", strategy=rv.strategy_id, to=target.value)
