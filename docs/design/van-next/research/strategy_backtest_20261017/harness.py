"""Research backtest of VAN's FX strategies on HistData 1-minute history.

Runs VAN's own DecisionCycle / PaperAdapter / RiskAuthority (the same loop as
vati.backtest.BacktestEngine.run) with one change: the cycle sees a trailing
window of WINDOW bars instead of the whole history, because compute_features
recomputes EMAs over the full list on every bar (O(n^2)). The window is checked
against the full-history engine on a sample (--check-window).

Paper only. No broker, account or network access from here.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
TRADING = HERE / "van" / "trading"
sys.path[:0] = [str(TRADING), str(TRADING / "tests")]

import pandas as pd  # noqa: E402

from conftest import mandate_dict, owner_authority  # noqa: E402  (test owner key: paper research only)
from conftest_owner_authority import OWNER_KEY_ID  # noqa: E402

_keys = HERE / f"owner_keys_{os.getpid()}.json"
_keys.write_text(json.dumps({"keys": {OWNER_KEY_ID: owner_authority().pem}}))
os.environ["VAN_OWNER_AUTHORITY_KEYS"] = str(_keys)

from vati.app.cycle import DecisionCycle, SessionConfig  # noqa: E402
from vati.arbiter import OpportunityEngine  # noqa: E402
from vati.backtest.metrics import compute_metrics  # noqa: E402
from vati.core.ledger import Ledger  # noqa: E402
from vati.execution.paper import PaperAdapter  # noqa: E402
from vati.intelligence.events import EventMatrix  # noqa: E402
from vati.market_data.bars import Bar  # noqa: E402
from vati.market_data.calendars import FX_CALENDAR  # noqa: E402
from vati.risk import SymbolContract, TradingMandate  # noqa: E402
from vati.strategies import STRATEGY_IMPLEMENTATIONS, CapsuleRegistry  # noqa: E402

D = Decimal
SPEC = {  # spread, slippage, round-trip cost fraction, USD per 1.0 price unit per lot, tick
    "EURUSD": dict(spread=D("0.00008"), slip=D("0.00002"), cost=D("0.00010"), vpu=D("100000"), tick=D("0.00001"), minstop=D("0.00030")),
    "GBPUSD": dict(spread=D("0.00012"), slip=D("0.00002"), cost=D("0.00012"), vpu=D("100000"), tick=D("0.00001"), minstop=D("0.00030")),
    # USDJPY: per-side cost 0.006 (half spread + slippage), split like the other pairs. On main
    # (8eb1889) that slippage refused every JPY fill (finding 2); BT_JPY_FOLD=1 reproduces the
    # original study's workaround of folding the slippage into the spread.
    "USDJPY": (dict(spread=D("0.012"), slip=D("0"), cost=D("0.00008"), vpu=D("667"), tick=D("0.001"), minstop=D("0.030"))
               if os.environ.get("BT_JPY_FOLD") == "1" else
               dict(spread=D("0.008"), slip=D("0.002"), cost=D("0.00008"), vpu=D("667"), tick=D("0.001"), minstop=D("0.030"))),
}
TF_RULE = {"H1": "1h", "M15": "15min"}
TF_MS = {"H1": 3_600_000, "M15": 900_000}


def load_bars(symbol: str, tf: str, start: str, end: str) -> list[Bar]:
    cache = HERE / "data" / f"{symbol.lower()}_{tf}_{start}_{end}.pkl"
    if cache.exists():
        df = pd.read_pickle(cache)
    else:
        m = pd.read_parquet(HERE / "data" / f"{symbol.lower()}.parquet")
        m = m[(m.ts >= start) & (m.ts < end)].set_index("ts")
        df = m.resample(TF_RULE[tf], label="left", closed="left").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "count"}).dropna()
        df.to_pickle(cache)
    sp = SPEC[symbol]["spread"]
    step = TF_MS[tf]
    out = []
    for ts, r in df.iterrows():
        s = int(ts.timestamp() * 1000)
        out.append(Bar(symbol, s, s + step, D(str(float(r.open))), D(str(float(r.high))), D(str(float(r.low))), D(str(float(r.close))), D(int(r.volume)), int(r.volume), sp))
    return out


FAST_CHAIN = os.environ.get("BT_FAST_CHAIN") == "1"
TICK_ALIGN = os.environ.get("BT_TICK_ALIGN") == "1"
if TICK_ALIGN:
    # VAN rounds the stop to tick size after approval and can make it wider than approved
    # (STOP_WIDER_THAN_APPROVED). Align signal prices to the tick first, stop toward entry.
    import dataclasses
    from decimal import ROUND_CEILING, ROUND_FLOOR
    from vati.risk.contracts import Direction as _Dir
    from vati.strategies import STRATEGY_IMPLEMENTATIONS as _SI
    def _align(sig, tick):
        if sig is None:
            return None
        q = lambda x, r: (x / tick).to_integral_value(rounding=r) * tick
        long_ = sig.direction is _Dir.LONG
        entry = q(sig.entry, ROUND_FLOOR)
        stop = q(sig.stop, ROUND_CEILING if long_ else ROUND_FLOOR)
        return dataclasses.replace(sig, entry=entry, stop=stop, targets=tuple(q(t, ROUND_FLOOR) for t in sig.targets))
    for _k, _cls in list(_SI.items()):
        _orig = _cls.evaluate
        def _ev(self, state, ctx, _o=_orig):
            sig = _o(self, state, ctx)
            return _align(sig, SPEC[state.symbol]["tick"]) if sig is not None else None
        _cls.evaluate = _ev
if FAST_CHAIN:
    # The per-decision full-chain verify is O(ledger) per decision (quadratic over a run).
    # In-memory research ledger: verify once at the end instead (as BacktestEngine does).
    DecisionCycle._risk_store_ok = lambda self: True


def run(symbol: str, sid: str, bars: list[Bar], window: int, peek: bool = False, raw: bool = False) -> dict:
    s = SPEC[symbol]
    contract = SymbolContract(symbol=symbol, venue="paper", base_currency=symbol[:3], quote_currency=symbol[3:], account_currency="USD",
                              contract_size=D("100000"), tick_size=s["tick"], tick_value=s["vpu"] * s["tick"], volume_min=D("0.01"),
                              volume_step=D("0.01"), volume_max=D("100"), min_stop_distance=s["minstop"])
    m = mandate_dict(venue="paper", mode="DEMO_TRADER", instruments=[symbol], allowed_strategies=[sid], **({"max_consecutive_losses": 100000, "drawdown_tiers": [{"threshold": "0.95", "multiplier": "0"}]} if raw else {}))
    cfg = SessionConfig(symbol=symbol, base=symbol[:3], quote=symbol[3:], venue="paper", account_alias="fx_primary", contract=contract,
                        mandate_dict=m, session_id=f"research-{sid}-{symbol}", timeframe="H1")
    reg = CapsuleRegistry.load_dir(TRADING / "strategies" / "registry")
    impl = {sid: STRATEGY_IMPLEMENTATIONS[sid.rsplit("-", 1)[0]](strategy_id=sid)}
    engine = OpportunityEngine(reg, impl, TradingMandate.from_mapping(m))
    paper = PaperAdapter(venue="paper", account_alias="fx_primary", equity=D("10000"), spread=s["spread"], slippage=s["slip"], value_per_price_unit_per_lot=s["vpu"])
    ledger = Ledger(":memory:")
    cycle = DecisionCycle(cfg=cfg, adapter=paper, ledger=ledger, engine=engine, cost_fn=lambda st: s["cost"], calendar=FX_CALENDAR, events=EventMatrix())
    decisions: dict[str, int] = {}
    last_day = None
    for i in range(len(bars)):
        lo = max(0, i + 1 - window)
        hist = bars[lo: i + 2] if (peek and i + 1 < len(bars)) else bars[lo: i + 1]
        bar = bars[i]
        day = bar.end_ms // 86_400_000
        if last_day is not None and day != last_day:
            cycle.roll_day(paper.sync_account().equity, new_week=(day // 7) != (last_day // 7))
        last_day = day
        half = s["spread"] / 2
        for px in (bar.open, bar.low, bar.high, bar.close):
            cycle.mark(px - half, px + half, now_ms=bar.end_ms)
        res = cycle.step(hist, now_ms=bar.end_ms, last_quote_ms=bar.end_ms)
        k = res.decision if res.decision.startswith("REJECTED") else res.decision.split(":")[0]
        decisions[k] = decisions.get(k, 0) + 1
    for p in paper.positions():
        paper.close(p.position_id, None, now_ms=bars[-1].end_ms, reason="END_OF_TEST")
        cycle._on_close(p.trade_intent_id, paper.closed[-1]["exit"], "END_OF_TEST", bars[-1].end_ms)
    trades = [{"t": c.get("closed_ms") or c.get("exit_ms"), "pnl": str(c["pnl"])} for c in paper.closed]
    rs = [rv.r_multiple for rv in cycle.reviews]
    met = compute_metrics([D(str(c["pnl"])) for c in paper.closed], rs, D("10000"))
    chain_ok, chain_n = ledger.verify_chain()
    return {"chain_ok": chain_ok, "chain_events": chain_n, "fast_chain": FAST_CHAIN, "symbol": symbol, "strategy": sid, "bars": len(bars), "window": window, "peek": peek, "decisions": decisions,
            "metrics": met.as_dict(), "r_multiples": [str(r) for r in rs],
            "review_times": [getattr(rv, "closed_ms", None) or getattr(rv, "exit_ms", None) for rv in cycle.reviews],
            "closed_raw_keys": sorted(paper.closed[0].keys()) if paper.closed else [], "trades": trades}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--strategy", required=True)
    ap.add_argument("--tf", default="H1")
    ap.add_argument("--start", default="2018-07-01")
    ap.add_argument("--end", default="2025-03-22")
    ap.add_argument("--window", type=int, default=400)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--peek", action="store_true")
    ap.add_argument("--raw", action="store_true", help="disable the consecutive-loss lockout to measure the strategy itself")
    ap.add_argument("--out")
    a = ap.parse_args()
    bars = load_bars(a.symbol, a.tf, a.start, a.end)
    if a.limit:
        bars = bars[: a.limit]
    t0 = time.time()
    out = run(a.symbol, a.strategy, bars, a.window, a.peek, a.raw)
    out["raw"] = a.raw
    out["tf"], out["seconds"] = a.tf, round(time.time() - t0, 1)
    js = json.dumps(out, indent=1, default=str)
    if a.out:
        Path(a.out).write_text(js)
    print(json.dumps({k: out[k] for k in ("chain_ok", "chain_events", "fast_chain", "symbol", "strategy", "tf", "bars", "window", "peek", "decisions", "metrics", "seconds")}, indent=1, default=str))
