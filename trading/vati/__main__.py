"""VATI command line.

  python -m vati backtest --bars bars.csv --config session.json [--peek] [--out result.json]
  python -m vati replay-verify --ledger vati.sqlite
  python -m vati ledger-status --ledger vati.sqlite
  python -m vati stack-lock
  python -m vati zse-facts
  python -m vati accounts list|add|remove|verify --registry accounts.json [...]
  python -m vati lake import-csv|list|dukascopy --root lake ...
  python -m vati calendar --file calendar.json
  python -m vati calendar-record --schedule sched.json [--releases obs.json] [--ledger vati.sqlite]
  python -m vati serve --config service.json [--once]

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
                        mandate_dict=cfg_json["mandate"], timeframe=cfg_json.get("timeframe", "UNKNOWN"), warmup_bars=int(cfg_json.get("warmup_bars", 60)), session_id=cfg_json.get("session_id", "cli"), activation_id=cfg_json.get("activation_id", "vtil-act-unresolved"))
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


def cmd_accounts(a: argparse.Namespace) -> int:
    from vati.accounts import Account, AccountRegistry, CredentialRef
    reg = AccountRegistry(a.registry)
    if a.op == "list":
        print(json.dumps(reg.public(), indent=2)); return 0
    if a.op == "remove":
        reg.remove(a.alias); print(f"removed {a.alias}"); return 0
    if a.op == "add":
        acc = Account(alias=a.alias, broker=a.broker, mode=a.mode, currency=a.currency, label=a.label or a.alias, server=a.server or "", login=a.login or "", bridge_url=a.bridge_url or "",
                      credential_ref=CredentialRef(env_var=a.env_var, secrets_file=a.secrets_file), demo=not a.live, mandate_ref=a.mandate_ref or "")
        reg.add(acc); print(json.dumps(acc.public(), indent=2)); return 0
    if a.op == "verify":
        acc = reg.get(a.alias)
        try:
            secrets = reg.credentials(a.alias)
            keys = sorted(secrets)
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"alias": a.alias, "credentials": "MISSING", "reason": str(exc)})); return 1
        print(json.dumps({"alias": a.alias, "safety_identity": acc.safety_identity, "credentials": "PRESENT", "keys": keys}))   # key names only, never values
        return 0
    return 2


def cmd_lake(a: argparse.Namespace) -> int:
    from vati.market_data.feeds import BarLake, bars_from_csv
    lake = BarLake(a.root)
    if a.op == "list":
        print(json.dumps({sym: {tf: [s.__dict__ for s in lake.manifest(sym, tf)] for tf in tfs} for sym, tfs in lake.symbols().items()}, indent=2)); return 0
    if a.op == "import-csv":
        s = lake.write(bars_from_csv(a.file), symbol=a.symbol, timeframe=a.timeframe, source=f"csv:{Path(a.file).name}", provenance=a.provenance)
        print(json.dumps(s.__dict__, indent=2)); return 0
    if a.op == "dukascopy":
        from datetime import datetime, timezone
        from vati.market_data.feeds import DukascopyDownloader
        from vati.market_data.feeds.lake import TIMEFRAMES_MS
        dl = DukascopyDownloader()
        start = datetime.fromisoformat(a.start).replace(tzinfo=timezone.utc); end = datetime.fromisoformat(a.end).replace(tzinfo=timezone.utc)
        bars = dl.bars(a.symbol, start, end, interval_ms=TIMEFRAMES_MS[a.timeframe])
        if not bars:
            print("no bars downloaded"); return 1
        s = lake.write(bars, symbol=a.symbol, timeframe=a.timeframe, source="dukascopy", provenance="HISTORICAL_VENDOR")
        print(json.dumps({**s.__dict__, "hours_fetched": len(dl.fetched)}, indent=2)); return 0
    return 2


def cmd_calendar(a: argparse.Namespace) -> int:
    import time as _t
    from vati.intelligence.calendar_feed import calendar_report, load_calendar
    print(json.dumps(calendar_report(load_calendar(a.file), now_ms=int(_t.time() * 1000)), indent=2)); return 0


def cmd_research(a: argparse.Namespace) -> int:
    """Run one non-authoritative trading research operation from JSON."""
    from vati.core.ledger_pg import open_ledger
    from vati.research.workflow import TradingResearchWorkflow
    spec = json.loads(Path(a.spec).read_text())
    ledger = open_ledger(a.ledger) if a.ledger else None
    result = TradingResearchWorkflow(ledger=ledger).run_spec(spec)
    print(json.dumps(result, indent=2, default=str))
    return 0


def cmd_calendar_record(a: argparse.Namespace) -> int:
    """TRD-REV51-090. Record what was scheduled and what actually printed.

    Exit 1 when any release is DISPUTED: two of our sources disagree, so one
    feed is wrong and the surprise engine must not be handed either value.
    """
    import time as _t
    from vati.calendar import CalendarRecorder, rows_from_file
    from vati.core.ledger import Ledger

    ledger = Ledger(a.ledger) if a.ledger else None
    rec = CalendarRecorder(ledger=ledger)
    rec.ingest_schedule(rows_from_file(a.schedule))
    if a.releases:
        rec.ingest_observations(rows_from_file(a.releases, key="releases"))
    now_ms = int(a.now) if a.now else int(_t.time() * 1000)
    report = rec.report(now_ms=now_ms)
    report["records"] = [r.to_dict() for r in rec.records(now_ms=now_ms)]
    print(json.dumps(report, indent=2))
    if a.out:
        Path(a.out).write_text(json.dumps(report, indent=2))
    return 1 if report["disputed"] else 0


def cmd_serve(a: argparse.Namespace) -> int:
    from vati.app.process_lock import SessionAlreadyRunning, SessionLock
    from vati.app.service import ServiceConfig, SessionService, lake_bar_source
    from vati.market_data.feeds import BarLake
    cfg = ServiceConfig.load(a.config)
    # P0-TRADE-005 — nothing prevented two serve processes for one alias. Each would hold
    # its own idempotency set and both would place orders believing they were alone.
    try:
        lock = SessionLock(cfg.account_alias).acquire()
    except SessionAlreadyRunning as exc:
        print(json.dumps({"error": "session_already_running", "detail": str(exc)}))
        return 2
    try:
        if cfg.instruments:
            from vati.app.account_service import AccountCoordinatorService
            svc = AccountCoordinatorService(cfg).build()
        else:
            svc = SessionService(
                cfg, lake_bar_source(BarLake(cfg.lake_root), cfg.symbol, cfg.timeframe)
            ).build()
        if a.once:
            svc.start()
            result = svc.step_once()
            decision = getattr(result, "outcomes", result)
            print(json.dumps({"decision": str(decision), "cycles": svc.cycles}))
            return 0
        return svc.run_forever()
    finally:
        lock.release()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="vati")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backtest"); b.add_argument("--bars", required=True); b.add_argument("--config", required=True); b.add_argument("--peek", action="store_true"); b.add_argument("--out"); b.add_argument("--ledger"); b.set_defaults(fn=cmd_backtest)
    r = sub.add_parser("replay-verify"); r.add_argument("--ledger", required=True); r.set_defaults(fn=cmd_replay)
    s = sub.add_parser("ledger-status"); s.add_argument("--ledger", required=True); s.set_defaults(fn=cmd_status)
    sub.add_parser("stack-lock").set_defaults(fn=cmd_stack_lock)
    sub.add_parser("zse-facts").set_defaults(fn=cmd_zse_facts)
    ac = sub.add_parser("accounts"); ac.add_argument("op", choices=["list", "add", "remove", "verify"]); ac.add_argument("--registry", default="accounts.json"); ac.add_argument("--alias")
    ac.add_argument("--broker", choices=["MT5", "DERIV", "PAPER", "ZSE_OWNER_TICKET"]); ac.add_argument("--mode", default="DEMO_TRADER"); ac.add_argument("--currency", default="USD"); ac.add_argument("--label")
    ac.add_argument("--server"); ac.add_argument("--login"); ac.add_argument("--bridge-url", dest="bridge_url"); ac.add_argument("--env-var", dest="env_var"); ac.add_argument("--secrets-file", dest="secrets_file")
    ac.add_argument("--live", action="store_true"); ac.add_argument("--mandate-ref", dest="mandate_ref"); ac.set_defaults(fn=cmd_accounts)
    lk = sub.add_parser("lake"); lk.add_argument("op", choices=["list", "import-csv", "dukascopy"]); lk.add_argument("--root", default="lake"); lk.add_argument("--symbol"); lk.add_argument("--timeframe", default="H1")
    lk.add_argument("--file"); lk.add_argument("--provenance", default="HISTORICAL_VENDOR"); lk.add_argument("--start"); lk.add_argument("--end"); lk.set_defaults(fn=cmd_lake)
    cal = sub.add_parser("calendar"); cal.add_argument("--file", required=True); cal.set_defaults(fn=cmd_calendar)
    cr = sub.add_parser("calendar-record"); cr.add_argument("--schedule", required=True); cr.add_argument("--releases"); cr.add_argument("--ledger")
    cr.add_argument("--out"); cr.add_argument("--now"); cr.set_defaults(fn=cmd_calendar_record)
    rs = sub.add_parser("research"); rs.add_argument("--spec", required=True); rs.add_argument("--ledger"); rs.set_defaults(fn=cmd_research)
    sv = sub.add_parser("serve"); sv.add_argument("--config", required=True); sv.add_argument("--once", action="store_true"); sv.set_defaults(fn=cmd_serve)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
