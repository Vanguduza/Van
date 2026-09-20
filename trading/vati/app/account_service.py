"""Live account-level VATI runtime for multi-instrument allocation.

This is the production join for AccountDecisionCoordinator. It reuses VATI's
existing authority components rather than creating a second trading stack:
account registry, shared venue adapter, RiskAuthority, ExecutionRouter,
hash-chained VATI ledger, shared KillSwitch/ProtectionManager, and the
PostgreSQL AccountRuntimeLease with a final router epoch fence.

The legacy single-symbol SessionService remains the compatibility runtime.
A ServiceConfig with additional instruments selects this runtime from vati serve.
"""

from __future__ import annotations

import json
import os
import signal
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Optional

from vati.accounts import AccountRegistry, BrokerKind
from vati.app.account_coordinator import AccountDecisionCoordinator, CoordinatorConfig
from vati.app.account_lease import AccountRuntimeLease, PostgresLeaseStore
from vati.app.instrument_evaluator import InstrumentEvaluator, InstrumentEvaluatorConfig
from vati.arbiter import OpportunityEngine
from vati.arbiter.candidate import CandidateOpportunity
from vati.arbiter.portfolio_allocator import OpportunityPortfolioAllocator
from vati.core.canonical import canonical_hash
from vati.core.events import EventKind, make_event
from vati.core.ledger_pg import open_ledger
from vati.execution.base import StopMode, VenueAdapter
from vati.execution.policy import ExecutionBucket, ExecutionPolicyEngine
from vati.execution.protection import ProtectionManager
from vati.execution.reconciliation import LedgerPosition, reconcile
from vati.execution.router import ExecutionRouter, RouterError
from vati.intelligence.calendar_feed import build_matrix
from vati.intelligence.events import EventWindowState
from vati.intelligence.market_state import build_market_state
from vati.intelligence.mtf import TimeframeContract, build_multi_timeframe_state
from vati.intelligence.regimes import RegimeEngine
from vati.market_data.calendars import FX_CALENDAR
from vati.market_data.feeds.lake import BarLake
from vati.observability import metrics
from vati.observability.enhancement_metrics import (
    CORRELATION_MULTIPLIER, EXECUTION_FILL_PROBABILITY, EXECUTION_POLICY_SELECTED,
    PORTFOLIO_INCREMENTAL_ES,
)
from vati.risk import KillSwitch, MarketIntegrityState, OpenPosition, RiskAuthority, RiskSnapshot, TradingMandate
from vati.risk.contracts import Direction, KillSwitchTrigger, LossModel
from vati.risk.dependency import PortfolioDependencyEngine
from vati.risk.expected_shortfall import Position as DependencyPosition
from vati.risk.serde import contract_from_dict, intent_to_dict, snapshot_to_dict
from vati.strategies import STRATEGY_IMPLEMENTATIONS, CapsuleRegistry
from vati.strategies.base import StrategyContext

from vati.app.service import ROOT, build_adapter


@dataclass(frozen=True)
class LiveInstrumentSpec:
    symbol: str
    base: str
    quote: str
    timeframe: str
    contract: dict
    capsules: tuple[str, ...]
    round_trip_cost_pct: Decimal
    time_in_force: str = "DAY"

    @classmethod
    def from_mapping(cls, data: dict, *, defaults) -> "LiveInstrumentSpec":
        return cls(
            symbol=str(data.get("symbol", defaults.symbol)).upper(),
            base=str(data.get("base", defaults.base)),
            quote=str(data.get("quote", defaults.quote)),
            timeframe=str(data.get("timeframe", defaults.timeframe)),
            contract=dict(data.get("contract", defaults.contract)),
            capsules=tuple(data.get("capsules", defaults.capsules)),
            round_trip_cost_pct=Decimal(str(data.get("round_trip_cost_pct", defaults.round_trip_cost_pct))),
            time_in_force=str(data.get("time_in_force", "DAY")),
        )


class AccountCoordinatorService:
    """One live decision authority for every configured symbol in an account."""

    def __init__(self, cfg, *, clock=None, adapter: Optional[VenueAdapter] = None) -> None:
        self.cfg = cfg
        self.clock = clock or (lambda: int(time.time() * 1000))
        self.adapter = adapter
        self.stop_requested = False
        self.cycles = 0
        self.last_bar_end_ms: dict[str, int] = {}
        self._ledger = None
        self._lease_store: Optional[PostgresLeaseStore] = None
        self.lease: Optional[AccountRuntimeLease] = None
        self.coordinator: Optional[AccountDecisionCoordinator] = None
        self.kill = KillSwitch()
        self.protection = ProtectionManager()
        self.policy = ExecutionPolicyEngine()
        self.dependency = PortfolioDependencyEngine()
        self.mandate: Optional[TradingMandate] = None
        self.authority: Optional[RiskAuthority] = None
        self.router: Optional[ExecutionRouter] = None
        self.account = None
        self.specs: dict[str, LiveInstrumentSpec] = {}
        self.contracts = {}
        self.evaluators: dict[str, InstrumentEvaluator] = {}
        self.bar_sources = {}
        self.mtf_bar_sources = {}
        self.mtf_required: dict[str, tuple[str, ...]] = {}
        self.mtf_shadow = {}
        self._events = None
        self._entries: dict[str, dict] = {}
        self.peak_equity = Decimal("0")
        self.day_start_equity = Decimal("0")
        self.week_start_equity = Decimal("0")
        self.consecutive_losses = 0

    def _load_specs(self) -> None:
        primary = LiveInstrumentSpec.from_mapping({}, defaults=self.cfg)
        specs = [primary]
        for raw in getattr(self.cfg, "instruments", ()) or ():
            specs.append(LiveInstrumentSpec.from_mapping(dict(raw), defaults=self.cfg))
        by_symbol = {spec.symbol: spec for spec in specs}
        if len(by_symbol) != len(specs):
            raise RuntimeError("duplicate symbol in account coordinator configuration")
        if len(by_symbol) < 2:
            raise RuntimeError("AccountCoordinatorService requires at least two configured instruments")
        self.specs = by_symbol

    def build(self) -> "AccountCoordinatorService":
        self._load_specs()
        c = self.cfg
        registry = AccountRegistry(c.registry_path)
        account = registry.get(c.account_alias)
        if not account.enabled:
            raise RuntimeError(f"account {account.alias} is disabled")
        mandate = TradingMandate.from_mapping(c.mandate)
        if mandate.account_alias != account.alias:
            raise RuntimeError(f"mandate is for {mandate.account_alias!r}, account is {account.alias!r}")
        if mandate.mode.value in ("LIMITED_LIVE", "AUTONOMOUS_LIVE") and account.demo:
            raise RuntimeError("live mandate cannot run against a demo account identity")
        if not str(c.ledger).startswith(("postgres://", "postgresql://")):
            raise RuntimeError(
                "multi-instrument account coordination requires the shared PostgreSQL "
                "VATI authority store; a process-local lease is not a cross-host fence")

        self.account = account
        self.mandate = mandate
        self.authority = RiskAuthority(mandate)
        self.adapter = self.adapter or build_adapter(account, registry)
        self._ledger = open_ledger(c.ledger)
        self._lease_store = PostgresLeaseStore(c.ledger)
        self.lease = AccountRuntimeLease(
            self._lease_store,
            account_alias=account.alias,
            instance_id=f"{os.uname().nodename}:{os.getpid()}",
            software_version="vati-account-coordinator/1",
            git_sha=os.environ.get("VAN_GIT_SHA", ""),
        )
        self.router = ExecutionRouter(
            ledger=self._ledger,
            adapters={account.router_venue: self.adapter},
            kill_switch=self.kill,
            protection=self.protection,
            lease_fence=self.lease.fence,
        )

        capsule_root = c.capsule_dir or ROOT / "strategies" / "registry"
        all_capsules = CapsuleRegistry.load_dir(capsule_root)
        events = build_matrix(c.calendar_path)
        self._events = events
        lake = BarLake(c.lake_root)

        evaluators: list[InstrumentEvaluator] = []
        for spec in self.specs.values():
            self.contracts[spec.symbol] = contract_from_dict({**spec.contract, "venue": account.router_venue})
            chosen_capsules = [all_capsules.get(sid) for sid in spec.capsules]
            required = set()
            for capsule in chosen_capsules:
                contract = TimeframeContract.from_capsule(capsule.data)
                if contract is not None:
                    required.update(contract.required_timeframes)
            self.mtf_required[spec.symbol] = tuple(
                tf for tf in ("D1", "H4", "H1", "M15", "M5", "M1") if tf in required)
            capsule_registry = CapsuleRegistry(chosen_capsules)
            implementations = {
                sid: STRATEGY_IMPLEMENTATIONS[sid.rsplit("-", 1)[0]](strategy_id=sid)
                for sid in spec.capsules
            }
            engine = OpportunityEngine(capsule_registry, implementations, mandate)
            primary_regime = RegimeEngine()
            required_timeframes = {spec.timeframe}
            for capsule in chosen_capsules:
                contract = TimeframeContract.from_capsule(capsule.data)
                if contract is not None:
                    required_timeframes.update(contract.required_timeframes)
            required_timeframes = tuple(sorted(
                required_timeframes,
                key=lambda tf: ("D1", "H4", "H1", "M15", "M5", "M1").index(tf),
            ))
            mtf_regimes = {tf: RegimeEngine() for tf in required_timeframes}

            def state_fn(bars, now_ms, *, _spec=spec, _regime=primary_regime):
                if not bars:
                    raise RuntimeError(f"{_spec.symbol}: no bars")
                return build_market_state(
                    symbol=_spec.symbol, base=_spec.base, quote=_spec.quote, bars=bars,
                    regime_engine=_regime, calendar=FX_CALENDAR, events=events,
                    integrity=MarketIntegrityState.NORMAL, now_ms=now_ms,
                    last_quote_ms=bars[-1].end_ms, activation_id=c.activation_id,
                    timeframe=_spec.timeframe,
                )

            def mtf_state_fn(now_ms, *, _spec=spec, _required=required_timeframes, _regimes=mtf_regimes):
                def bars_for(tf):
                    bars, _manifest = lake.read(_spec.symbol, tf, end_ms=now_ms + 1)
                    return bars[-400:]

                def state_builder(*, bars, timeframe, now_ms):
                    return build_market_state(
                        symbol=_spec.symbol, base=_spec.base, quote=_spec.quote, bars=bars,
                        regime_engine=_regimes[timeframe], calendar=FX_CALENDAR, events=events,
                        integrity=MarketIntegrityState.NORMAL, now_ms=now_ms,
                        last_quote_ms=bars[-1].end_ms, activation_id=c.activation_id,
                        timeframe=timeframe,
                    )

                return build_multi_timeframe_state(
                    symbol=_spec.symbol, as_of_ms=now_ms,
                    required_timeframes=_required,
                    bars_for=bars_for, state_builder=state_builder,
                    minimum_bars=2,
                )

            evaluator = InstrumentEvaluator(
                InstrumentEvaluatorConfig(
                    symbol=spec.symbol, base=spec.base, quote=spec.quote,
                    venue=account.router_venue, account_alias=account.alias,
                    timeframe=spec.timeframe,
                ),
                engine=engine,
                state_fn=state_fn,
                ctx_fn=lambda _state, _cost=spec.round_trip_cost_pct: StrategyContext(round_trip_cost_pct=_cost),
                mtf_state_fn=mtf_state_fn,
            )
            evaluators.append(evaluator)
            self.evaluators[spec.symbol] = evaluator

            def source(now_ms, *, _spec=spec):
                bars, _manifest = lake.read(_spec.symbol, _spec.timeframe, end_ms=now_ms + 1)
                return [bar for bar in bars if bar.end_ms <= now_ms][-400:]
            self.bar_sources[spec.symbol] = source
            for tf in self.mtf_required[spec.symbol]:
                def mtf_source(now_ms, *, _spec=spec, _tf=tf):
                    bars, _manifest = lake.read(_spec.symbol, _tf, end_ms=now_ms + 1)
                    return [bar for bar in bars if bar.end_ms <= now_ms][-400:]
                self.mtf_bar_sources[(spec.symbol, tf)] = mtf_source

        self.coordinator = AccountDecisionCoordinator(
            CoordinatorConfig(account_alias=account.alias, max_new_intents_per_pass=1),
            evaluators=evaluators,
            allocator=OpportunityPortfolioAllocator(),
            lease=self.lease,
            snapshot_fn=self._snapshot_for,
            risk_fn=self._risk,
            execute_fn=self._execute,
            dependency_fn=self._dependency_for,
            mandate=mandate,
        )
        return self

    def _update_mtf_shadow(self, now_ms: int) -> None:
        """Build MTF evidence without changing the certified live decision path.

        The added timeframe_contract changed capsule schema, not owner-authorized
        strategy logic. This shadow path proves data availability, as-of discipline
        and deterministic identity. Actuation stays on the capsule's existing
        certified implementation until a signed strategy revision adopts MTF roles.
        """
        assert self._events is not None
        for symbol, required in self.mtf_required.items():
            if not required:
                continue
            spec = self.specs[symbol]

            def bars_for(tf, *, _symbol=symbol):
                return self.mtf_bar_sources[(_symbol, tf)](now_ms)

            def state_builder(*, bars, timeframe, now_ms, _spec=spec):
                return build_market_state(
                    symbol=_spec.symbol, base=_spec.base, quote=_spec.quote, bars=bars,
                    regime_engine=RegimeEngine(), calendar=FX_CALENDAR, events=self._events,
                    integrity=MarketIntegrityState.NORMAL, now_ms=now_ms,
                    last_quote_ms=bars[-1].end_ms, activation_id=self.cfg.activation_id,
                    timeframe=timeframe,
                )

            self.mtf_shadow[symbol] = build_multi_timeframe_state(
                symbol=symbol, as_of_ms=now_ms, required_timeframes=required,
                bars_for=bars_for, state_builder=state_builder,
                minimum_bars=max(2, self.cfg.warmup_bars),
            )

    def _open_positions(self) -> tuple[OpenPosition, ...]:
        assert self.adapter is not None
        out: list[OpenPosition] = []
        for position in self.adapter.positions():
            contract = self.contracts.get(position.symbol.upper())
            rule = self.protection.rules.get(position.position_id)
            stop = position.stop_price if position.stop_price is not None else (rule.stop if rule is not None else None)
            if contract is None:
                out.append(OpenPosition(
                    position.symbol, position.direction, position.quantity, Decimal("0"),
                    Decimal("0"), "", "", has_broker_side_stop=False))
                continue
            if position.loss_model is LossModel.ILLIQUID_EQUITY:
                out.append(OpenPosition(
                    position.symbol, position.direction, position.quantity,
                    abs(position.entry_price - (stop or position.entry_price)),
                    Decimal("1"), contract.base_currency, contract.quote_currency,
                    "", False, LossModel.ILLIQUID_EQUITY, Decimal("0"),
                    position.entry_price * contract.liquidity_haircut))
            else:
                out.append(OpenPosition(
                    position.symbol, position.direction, position.quantity,
                    abs(position.entry_price - stop) if stop is not None else Decimal("0"),
                    contract.value_per_price_unit_per_lot,
                    contract.base_currency, contract.quote_currency, "", stop is not None))
        return tuple(out)

    def _ledger_positions(self) -> list[LedgerPosition]:
        return [
            LedgerPosition(
                trade_intent_id=iid, symbol=row["symbol"], quantity=row["quantity"],
                stop_price=row.get("stop"), software_stop=row.get("software_stop", False))
            for iid, row in self._entries.items() if row.get("open", True)
        ]

    def _risk_store_ok(self) -> bool:
        try:
            return bool(self._ledger.verify_chain()[0])
        except Exception:
            return False

    def _snapshot_for(self, candidate: CandidateOpportunity) -> RiskSnapshot:
        assert self.adapter is not None and self.account is not None
        contract = self.contracts[candidate.symbol.upper()]
        acct = self.adapter.sync_account()
        now_ms = self.clock()
        if self.peak_equity == 0:
            self.peak_equity = self.day_start_equity = self.week_start_equity = acct.equity
        self.peak_equity = max(self.peak_equity, acct.equity)
        hb = self.adapter.heartbeat(now_ms=now_ms)
        report = reconcile(self._ledger_positions(), self.adapter.positions(), account_verified=acct.verified)
        state = self.evaluators[candidate.symbol.upper()].last_state
        quote_age = state.quote_age_ms if state is not None else self.cfg.max_quote_age_ms + 1
        blackout = bool(
            state is not None and
            state.event_window in (EventWindowState.PRE_BLACKOUT, EventWindowState.POST_BLACKOUT))
        integrity = state.integrity if state is not None else MarketIntegrityState.HALTED
        return RiskSnapshot(
            now_unix=now_ms // 1000, account_alias=acct.account_alias,
            account_verified=acct.verified, equity=acct.equity, balance=acct.balance,
            peak_equity=self.peak_equity, day_start_equity=self.day_start_equity,
            week_start_equity=self.week_start_equity,
            consecutive_losses=self.consecutive_losses,
            open_positions=self._open_positions(), symbol_contract=contract,
            quote_age_ms=quote_age, max_quote_age_ms=self.cfg.max_quote_age_ms,
            broker_connected=hb.connected, reconciliation_ok=report.permit_new_orders,
            clock_sync_ok=abs(hb.server_offset_ms) < 2000,
            risk_store_ok=self._risk_store_ok(), market_integrity=integrity,
            tier1_event_blackout_active=blackout,
            margin_level_pct=acct.margin_level_pct, free_margin=acct.free_margin,
            kill_switch_triggers=frozenset(self.kill.active),
        )

    def _risk(self, intent, snapshot: RiskSnapshot):
        assert self.authority is not None
        decision = self.authority.evaluate_safe(intent, snapshot)
        now = self.clock()
        self._ledger.append(make_event(
            EventKind.RISK_DECISION, "vati-account-coordinator",
            {"inputs": {"intent": intent_to_dict(intent), "snapshot": snapshot_to_dict(snapshot),
                        "mandate": self.cfg.mandate},
             "decision": decision.to_dict()},
            event_time_ms=now, received_time_ms=now, decision_time_ms=now,
            correlation_id=intent.trade_intent_id))
        metrics.inc("vati_decisions_total", outcome=decision.decision.value)
        return decision

    @staticmethod
    def _dependency_positions(snapshot: RiskSnapshot) -> list[DependencyPosition]:
        out = []
        for p in snapshot.open_positions:
            if p.loss_model is LossModel.FULL_STAKE:
                risk = p.stake
            elif p.loss_model is LossModel.ILLIQUID_EQUITY:
                risk = p.lots * p.liquidity_haircut_per_unit
            else:
                risk = p.lots * p.stop_distance * p.value_per_price_unit_per_lot
            out.append(DependencyPosition(p.symbol, risk, 1 if p.direction is Direction.LONG else -1))
        return out

    def _dependency_for(self, candidate: CandidateOpportunity, snapshot: RiskSnapshot):
        risk_pct = self.coordinator.risk_pct_fn(candidate) if self.coordinator else Decimal("0")
        dep = self.dependency.assess(
            candidate_id=candidate.candidate_id, symbol=candidate.symbol,
            candidate_risk=snapshot.equity * risk_pct,
            direction=1 if candidate.direction is Direction.LONG else -1,
            open_positions=self._dependency_positions(snapshot), now_ms=self.clock(),
            portfolio_snapshot_hash=canonical_hash(snapshot_to_dict(snapshot)))
        metrics.set(
            PORTFOLIO_INCREMENTAL_ES, float(dep.incremental_es),
            account_alias=self.account.alias, symbol=candidate.symbol)
        metrics.set(
            CORRELATION_MULTIPLIER, float(dep.correlation_multiplier),
            account_alias=self.account.alias, symbol=candidate.symbol)
        now = self.clock()
        self._ledger.append(make_event(
            EventKind.PORTFOLIO_DEPENDENCY, "vati-account-coordinator",
            dep.as_dict() | {"dependency_hash": dep.dependency_hash},
            event_time_ms=now, received_time_ms=now, decision_time_ms=now,
            correlation_id=candidate.candidate_id))
        return dep

    def _execute(self, candidate, intent, decision, targets, lease_epoch):
        assert self.router is not None and self.account is not None and self.mandate is not None
        state = self.evaluators[candidate.symbol.upper()].last_state
        if state is None:
            raise RouterError("candidate has no current market state")
        bucket = ExecutionBucket(
            broker=str(getattr(self.account.broker, "value", self.account.broker)).lower(),
            account_alias=self.account.alias, symbol=candidate.symbol,
            session=state.session.value, volatility_bucket=state.regime.vol.value,
            event_proximity=state.event_window.value, direction=candidate.direction.value)
        policy_decision = self.policy.select(
            candidate_id=candidate.candidate_id, bucket=bucket,
            event_state=state.event_window.value)
        metrics.inc(
            EXECUTION_POLICY_SELECTED,
            account_alias=self.account.alias, symbol=candidate.symbol,
            template_id=policy_decision.template_id)
        if policy_decision.estimated_fill_probability is not None:
            metrics.set(
                EXECUTION_FILL_PROBABILITY, float(policy_decision.estimated_fill_probability),
                account_alias=self.account.alias, symbol=candidate.symbol,
                template_id=policy_decision.template_id)
        software = self.account.broker == BrokerKind.ZSE_OWNER_TICKET
        receipt = self.router.execute(
            intent, decision, self.mandate, now_ms=self.clock(),
            stop_mode=StopMode.SOFTWARE if software else StopMode.VENUE,
            targets=targets, time_in_force=self.specs[candidate.symbol.upper()].time_in_force,
            lease_epoch=lease_epoch, execution_policy_decision=policy_decision)
        if receipt.status in ("FILLED", "PARTIAL", "ACCEPTED", "OWNER_EXECUTED"):
            self._entries[intent.trade_intent_id] = {
                "symbol": candidate.symbol, "quantity": receipt.filled_qty,
                "stop": intent.stop, "software_stop": software, "open": True}
        return receipt

    def _observe_owner_halt(self, now_ms: int) -> None:
        latest = None
        for event in self._ledger.iter(EventKind.KILL_SWITCH):
            if event.payload.get("trigger") != "OWNER_HALT":
                continue
            latest = None if event.payload.get("cleared") else event
        if latest is not None:
            self.kill.trip(KillSwitchTrigger.OWNER_HALT, now_ms)

    def _heartbeat(self, status: str, extra: Optional[dict] = None) -> None:
        payload = {
            "account_alias": self.cfg.account_alias, "symbols": sorted(self.specs),
            "status": status, "cycles": self.cycles,
            "lease_epoch": self.lease.epoch if self.lease else None,
            "kill_switch": sorted(t.value for t in self.kill.active),
            "mtf_shadow": {
                symbol: {
                    "complete": mtf.complete,
                    "missing": list(mtf.missing_timeframes),
                    "mtf_state_hash": mtf.mtf_state_hash,
                }
                for symbol, mtf in sorted(self.mtf_shadow.items())
            },
            "updated_ms": self.clock(), "pid": os.getpid(), **(extra or {})}
        Path(self.cfg.heartbeat_path).write_text(json.dumps(payload))

    def start(self) -> None:
        assert self.lease is not None and self.adapter is not None
        result = self.lease.acquire(now_ms=self.clock())
        if not result.permits_orders:
            raise RuntimeError(f"account runtime lease refused: {result.outcome.value}")
        acct = self.adapter.sync_account()
        report = reconcile([], self.adapter.positions(), account_verified=acct.verified)
        if not report.permit_new_orders:
            self.kill.trip(KillSwitchTrigger.RECONCILIATION_FAILURE, self.clock())
        self.peak_equity = self.day_start_equity = self.week_start_equity = acct.equity
        self._observe_owner_halt(self.clock())
        self._heartbeat("STARTED", {"lease_outcome": result.outcome.value})

    def step_once(self):
        assert self.coordinator is not None
        now = self.clock()
        self._observe_owner_halt(now)
        bars_by_symbol = {}
        advanced = False
        for symbol, source in self.bar_sources.items():
            bars = source(now)
            if not bars:
                continue
            bars_by_symbol[symbol] = bars
            if bars[-1].end_ms > self.last_bar_end_ms.get(symbol, 0):
                advanced = True
        if not bars_by_symbol:
            self._heartbeat("NO_DATA")
            return None
        if not advanced:
            self._heartbeat("WAITING_FOR_BAR")
            return None
        self._update_mtf_shadow(now)
        result = self.coordinator.step(now_ms=now, bars_by_symbol=bars_by_symbol)
        for symbol, bars in bars_by_symbol.items():
            self.last_bar_end_ms[symbol] = max(self.last_bar_end_ms.get(symbol, 0), bars[-1].end_ms)
        self.cycles += 1
        self._heartbeat("RUNNING", {
            "allocation_epoch_id": result.allocation_epoch_id,
            "ranking": list(result.ranking),
            "outcomes": [o.as_dict() for o in result.outcomes]})
        return result

    def run_forever(self) -> int:
        def stop(*_args):
            self.stop_requested = True
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        self.start()
        try:
            while not self.stop_requested:
                try:
                    self.step_once()
                except Exception as exc:
                    self.kill.trip(KillSwitchTrigger.RECONCILIATION_FAILURE, self.clock())
                    self._heartbeat("FAULT", {"error": str(exc)[:200]})
                time.sleep(self.cfg.poll_seconds)
        finally:
            if self.lease is not None:
                self.lease.release(now_ms=self.clock())
            if self._lease_store is not None:
                self._lease_store.close()
        self._heartbeat("STOPPED")
        return 0


__all__ = ["AccountCoordinatorService", "LiveInstrumentSpec"]
