# VAN Adaptive Trading Intelligence (VATI) — `trading/`

Canonical authority: `docs/VAN_ADAPTIVE_TRADING_INTELLIGENCE_TECHNICAL_BLUEPRINT_REV2.md`.

This tree holds VATI code. Phase 0 (Canon & Risk Boundary) is delivered here;
later phases add packages under the layout in Rev 2 §49.

| Path | Phase | Role |
|---|---|---|
| `vati/risk/` | 0 | Deterministic Risk Authority: mandate, sizing, portfolio heat, currency legs, drawdown governor, kill switch, sealed `RiskDecision`. Pure Python, stdlib only. |
| `vati/contracts/schemas/` | 0 | JSON Schema for `TradingMandate`, `SymbolContract`, `RiskSnapshot`, `TradeIntent`, `RiskDecision`, `ExecutionReceipt`, `StrategyCapsule`. |
| `examples/` | 0 | Example mandate (unsigned placeholder signature; not a live mandate). |
| `tests/` | 0 | Unit tests, fail-closed path tests and seeded property fuzz (P1–P8). |
| `architecture/stack_lock.json` | 0 (Rev 2.1) | Machine-checked tool-per-layer lock with adoption phase, latency tier, licence class and observed version. |
| `vtil/` | 2 (seed now) | VTIL registry in DIAL VEKL schema plus the probe that runs DIAL's unmodified resolver against it. |

## Invariants the code enforces

- Nothing in `vati/risk` imports a model, a broker SDK or the network.
- Multipliers can only reduce risk: every multiplier is clamped into `[0, 1]`.
- Lot sizes round **down** to the venue step; below venue minimum is `NO_TRADE`.
- Approved risk ≤ min(requested, mandate) and a mandate cannot exceed platform ceilings.
- Any unprovable health flag (stale quote, disconnected venue, failed
  reconciliation, clock, risk store, unverified account, kill switch) rejects.
- A replayed idempotency key is rejected as `DUPLICATE_INTENT`.
- A Deriv fixed-payout contract is sized by stake (stake = maximum loss).

## Run

```bash
python3 -m pytest trading -q
```

The property fuzz (`tests/test_authority_properties.py`) must exercise both
approval and rejection branches; it asserts that it did. The gate was broken
deliberately five ways (multiplier clamp, mandate clamp, heat check,
duplicate latch, kill switch) and the fuzz failed each time — see Rev 2 Part D.

## Not in this tree yet

Market data, strategies, execution adapters (MT5/Deriv), reconciliation, TCA,
VTIL admission and GraphRAG are Phases 1–12. No adapter may be added before the
Phase 0 gate evidence in Rev 2 Part D is accepted by the owner.
