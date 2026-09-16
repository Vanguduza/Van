"""Deterministic event-driven backtest (Rev 2 §26, Rev 2.1 §E.3). Runs the very
same DecisionCycle used live against a PaperAdapter, bar by bar. Bars are
walked open → low → high → close for longs' worst case first (stop before
target), which is the conservative intrabar assumption. The `peek` switch
feeds the next bar into the state on purpose: a leakage test must show it
changes the result."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable, Optional, Sequence

from vati.app.cycle import CycleResult, DecisionCycle, SessionConfig
from vati.arbiter import OpportunityEngine
from vati.backtest.metrics import Metrics, compute_metrics
from vati.core.ledger import Ledger
from vati.execution.paper import PaperAdapter
from vati.intelligence.events import EventMatrix
from vati.intelligence.market_state import MarketState
from vati.market_data.bars import Bar
from vati.market_data.calendars import MarketCalendar
from vati.strategies.base import StrategyContext

ZERO = Decimal("0")


@dataclass
class BacktestResult:
    trades: int
    metrics: Metrics
    equity_curve: list[tuple[int, Decimal]]
    cycles: list[CycleResult]
    reviews: list
    ledger_head: str
    ledger_ok: bool
    decision_replay_identical: bool
    rejections: dict[str, int] = field(default_factory=dict)

    def summary(self) -> dict:
        return {"trades": self.trades, "metrics": self.metrics.as_dict(), "final_equity": str(self.equity_curve[-1][1]) if self.equity_curve else None,
                "ledger_head": self.ledger_head, "ledger_ok": self.ledger_ok, "decision_replay_identical": self.decision_replay_identical, "rejections": self.rejections}


class BacktestEngine:
    def __init__(self, *, cfg: SessionConfig, engine: OpportunityEngine, cost_fn: Callable[[MarketState], Decimal], calendar: MarketCalendar, events: EventMatrix,
                 start_equity: Decimal = Decimal("10000"), spread: Decimal = Decimal("0.00010"), slippage: Decimal = Decimal("0.00002"),
                 ctx_fn: Optional[Callable[[MarketState, Decimal], StrategyContext]] = None, ledger_path: str = ":memory:") -> None:
        self.cfg, self.engine, self.cost_fn, self.calendar, self.events, self.ctx_fn = cfg, engine, cost_fn, calendar, events, ctx_fn
        self.start_equity, self.spread, self.slippage, self.ledger_path = start_equity, spread, slippage, ledger_path

    def run(self, bars: Sequence[Bar], *, peek: bool = False) -> BacktestResult:
        cfg = self.cfg
        paper = PaperAdapter(venue=cfg.venue, account_alias=cfg.account_alias, equity=self.start_equity, spread=self.spread, slippage=self.slippage,
                             value_per_price_unit_per_lot=cfg.contract.value_per_price_unit_per_lot)
        ledger = Ledger(self.ledger_path)
        cycle = DecisionCycle(cfg=cfg, adapter=paper, ledger=ledger, engine=self.engine, cost_fn=self.cost_fn, calendar=self.calendar, events=self.events, ctx_fn=self.ctx_fn)
        curve: list[tuple[int, Decimal]] = []
        cycles: list[CycleResult] = []
        rejections: dict[str, int] = {}
        last_day = None
        for i in range(len(bars)):
            hist = bars[: i + 2] if (peek and i + 1 < len(bars)) else bars[: i + 1]
            bar = bars[i]
            day = bar.end_ms // 86_400_000
            if last_day is not None and day != last_day:
                cycle.roll_day(paper.sync_account().equity, new_week=(day // 7) != (last_day // 7))
            last_day = day
            # marks: walk the bar path against open positions before deciding on the close
            half = self.spread / 2
            for px in (bar.open, bar.low, bar.high, bar.close):
                cycle.mark(px - half, px + half, now_ms=bar.end_ms)
            res = cycle.step(hist, now_ms=bar.end_ms, last_quote_ms=bar.end_ms)
            cycles.append(res)
            if res.decision.startswith("REJECTED:"):
                rejections[res.decision] = rejections.get(res.decision, 0) + 1
            curve.append((bar.end_ms, paper.sync_account().equity))
        # flatten at end for accounting
        for p in paper.positions():
            paper.close(p.position_id, None, now_ms=bars[-1].end_ms, reason="END_OF_TEST")
            cycle._on_close(p.trade_intent_id, paper.closed[-1]["exit"], "END_OF_TEST", bars[-1].end_ms)
        pnls = [Decimal(str(c["pnl"])) for c in paper.closed]
        rs = [rv.r_multiple for rv in cycle.reviews]
        ok, _ = ledger.verify_chain()
        from vati.risk import RiskAuthority, TradingMandate
        from vati.risk.serde import intent_from_dict, snapshot_from_dict
        rep = ledger.replay_decisions(lambda inp: RiskAuthority(TradingMandate.from_mapping(inp["mandate"])).evaluate(intent_from_dict(inp["intent"]), snapshot_from_dict(inp["snapshot"])).to_dict())
        return BacktestResult(len(paper.closed), compute_metrics(pnls, rs, self.start_equity), curve, cycles, cycle.reviews, ledger.head(), ok, rep.ok and rep.checked >= 0, rejections)
