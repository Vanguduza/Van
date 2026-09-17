# VAN Trading System (VATI) — `trading/`

Canonical authority: `docs/VAN_TRADING_SYSTEM_BLUEPRINT_REV4_CONSOLIDATED.md` (Rev 4 consolidates Rev 2, 2.1 and 3; earlier revisions remain provenance).

```
python3 -m pytest trading -q                       # all trading tests
python3 -m vati backtest --bars bars.csv --config session.json --ledger run.sqlite
python3 -m vati replay-verify --ledger run.sqlite  # recompute every RiskDecision from its stored inputs
python3 -m vati zse-facts                          # ZSE/VFEX facts with verification state and live blockers
python3 trading/tools/induce_gate_failures.py      # break the risk gate deliberately; fuzz must catch it
DIAL_REPO=../dial-new node trading/vtil/tools/resolve_probe.mjs   # DIAL VEKL resolver over the Van registry
```

| Package | Role |
|---|---|
| `vati/core` | canonical JSON/hash, event envelope (3 clocks), hash-chained SQLite ledger with decision replay |
| `vati/market_data` | session calendars (FX 24×5, ZSE fail-closed until verified), integrity state machine, bar aggregation, FX cost model |
| `vati/intelligence` | features, regime engine (CUSUM change-point + hysteresis), Tier-1 event matrix, MarketState |
| `vati/strategies` | signed StrategyCapsule registry (`strategies/registry/*.json`) and five deterministic strategies |
| `vati/arbiter` | horizon arbiter (k × cost), strategy arbiter, rule meta-labeller (uncalibrated, reduce-only), opportunity engine → sealed TradeIntent |
| `vati/risk` | Deterministic Risk Authority: mandate + ceilings, sizing for STOP_DISTANCE / FULL_STAKE / ILLIQUID_EQUITY, heat, currency legs, drawdown governor, kill switch, EDGE_BELOW_COST |
| `vati/execution` | router (sealed-decision verification, idempotency, flatten-on-stop-reject), adapters: paper, owner ticket (ZSE), MT5 bridge client, Deriv; protection (stops only tighten), reconciliation, TCA, review |
| `vati/zse` | Zimbabwe Stock Exchange / VFEX: sourced market facts with verification state, cost schedule, ZiG regime, liquidity haircut |
| `vati/vtil` | admission ledger (no self-admission; T4 needs validation); registry + DIAL resolver probe under `vtil/` |
| `vati/backtest` | deterministic backtest over the live DecisionCycle; expectancy, drawdown, deflated Sharpe, PBO (CSCV), walk-forward; leakage switch |
| `vati/app` | DecisionCycle (shared by backtest and live), SessionRunner (startup reconciliation, owner halt) |
| `architecture/stack_lock.json` | one tool per layer, licence class, adoption phase, build status; tested |

Not built yet (by design, gated): NautilusTrader kernel adoption, real MT5 Windows worker and Deriv transports, ZSE data ingestion adapters, PostgreSQL/Parquet migration, calibrated meta-labeller, LEAN reproduction. Nothing here has traded on demo or live.
