"""VATI command line.

  python -m vati backtest --bars bars.csv --config session.json [--peek] [--out result.json]
  python -m vati replay-verify --ledger vati.sqlite
  python -m vati ledger-status --ledger vati.sqlite
  python -m vati stack-lock
  python -m vati zse-facts

CSV bars: symbol,start_ms,end_ms,open,high,low,close,volume,ticks,avg_spread
session.json: SessionConfig fields + contract dict + mandate dict + capsule ids."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from decimal import Decimal
from pathlib import Path

from vati.app.cycle import SessionConfig
from vati.arbiter import OpportunityEngine
from vati.backtest import BacktestEngine
from vati.core.ledger import Ledger
from vati.intelligence.events import EventMatrix
from vati.market_data.bars import Bar
from vati.market_data.calendars import FX_CALENDAR
from vati.risk import RiskAuthority, TradingMandate
from vati.risk.serde import contract_from_dict, intent_from_dict, snapshot_from_dict
from vati.strategies import STRATEGY_IMPLEMENTATIONS, CapsuleRegistry

ROOT = Path(__file__).resolve().parents[1]


def load_bars(path: str) -> list[Bar]:
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out.append(Bar(r["symbol"], int(r["start_ms"]), int(r["end_ms"]), Decimal(r["open"]), Decimal(r["high"]), Decimal(r["low"]), Decimal(r["close"]), Decimal(r.get("volume", "0")), int(r.get("ticks", "1")), Decimal(r.get("avg_spread", "0"))))
    return out


def build_engine(cfg_json: dict) -> tuple[SessionConfig, OpportunityEngine]:
    contract = contract_from_dict(cfg_json["contract"])
    cfg = SessionConfig(symbol=cfg_json["symbol"], base=cfg_json["base"], quote=cfg_json["quote"], venue=cfg_json["venue"], account_alias=cfg_json["account_alias"], contract=contract,
                        mandate_dict=cfg_json["mandate"], warmup_bars=int(cfg_json.get("warmup_bars", 60)), session_id=cfg_json.get("session_id", "cli"), activation_id=cfg_json.get("activation_id", "vtil-act-unresolved"))
    reg = CapsuleRegistry.load_dir(cfg_json.get("capsule_dir", ROOT / "strategies" / "registry"))
    impl = {sid: STRATEGY_IMPLEMENTATIONS[sid.rsplit("-", 1)[0]](strategy_id=sid) for sid in cfg_json["capsules"]}
    return cfg, OpportunityEngine(reg, impl, TradingMandate.from_mapping(cfg_json["mandate"]))


def cmd_backtest(a: argparse.Namespace) -> int:
    cfg_json = json.loads(Path(a.config).read_text())
    cfg, engine = build_engine(cfg_json)
    cost = Decimal(str(cfg_json.get("round_trip_cost_pct", "0.0003")))
    bt = BacktestEngine(cfg=cfg, engine=engine, cost_fn=lambda st: cost, calendar=FX_CALENDAR, events=EventMatrix(), start_equity=Decimal(str(cfg_json.get("start_equity", "10000"))),
                        ledger_path=a.ledger or ":memory:")
    res = bt.run(load_bars(a.bars), peek=a.peek)
    out = res.summary()
    print(json.dumps(out, indent=2, default=str))
    if a.out:
        Path(a.out).write_text(json.dumps(out, indent=2, default=str))
    return 0 if res.ledger_ok and res.decision_replay_identical else 1


def cmd_replay(a: argparse.Namespace) -> int:
    led = Ledger(a.ledger)
    ok, n = led.verify_chain()
    rep = led.replay_decisions(lambda inp: RiskAuthority(TradingMandate.from_mapping(inp["mandate"])).evaluate(intent_from_dict(inp["intent"]), snapshot_from_dict(inp["snapshot"])).to_dict())
    print(json.dumps({"chain_ok": ok, "events": n, "decisions_checked": rep.checked, "identical": rep.identical, "divergent": rep.divergent}, indent=2))
    return 0 if ok and rep.ok else 1


def cmd_status(a: argparse.Namespace) -> int:
    from vati.core.events import EventKind
    led = Ledger(a.ledger)
    print(json.dumps({k.value: led.count(k) for k in EventKind if led.count(k)}, indent=2))
    return 0


def cmd_stack_lock(a: argparse.Namespace) -> int:
    d = json.loads((ROOT / "architecture" / "stack_lock.json").read_text())
    for l in d["layers"]:
        print(f"{l['layer']:<36} {l['canonical'][:60]:<60} phase {l['adoption_phase']:<2} {l['latency_tier']} {l['licence_class']}")
    return 0


def cmd_zse_facts(a: argparse.Namespace) -> int:
    from vati.zse import ZSE_SPEC, VFEX_SPEC
    for spec in (ZSE_SPEC, VFEX_SPEC):
        print(f"== {spec.exchange.value}: live blockers = {spec.live_blockers()}")
        for name in ("session_open", "session_close", "settlement_days", "board_lot", "foreign_ownership_limits", "stop_orders_supported"):
            f = getattr(spec, name)
            print(f"  {name:<26} {str(f.value):<20} {f.state.value:<12} {f.note[:70]}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="vati")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backtest"); b.add_argument("--bars", required=True); b.add_argument("--config", required=True); b.add_argument("--peek", action="store_true"); b.add_argument("--out"); b.add_argument("--ledger"); b.set_defaults(fn=cmd_backtest)
    r = sub.add_parser("replay-verify"); r.add_argument("--ledger", required=True); r.set_defaults(fn=cmd_replay)
    s = sub.add_parser("ledger-status"); s.add_argument("--ledger", required=True); s.set_defaults(fn=cmd_status)
    sub.add_parser("stack-lock").set_defaults(fn=cmd_stack_lock)
    sub.add_parser("zse-facts").set_defaults(fn=cmd_zse_facts)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
