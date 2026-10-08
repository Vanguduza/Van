# VAN/VATI Opportunity Temperament Modes — Implementation Rev 1

**Branch:** chatgpt/vati-opportunity-modes-20261008
**Implementation scope:** account-level multi-instrument VATI coordination, existing signed mandate and risk authority, already-permitted partial-profit adjustments
**Production deployment:** NOT REQUESTED; NOT DEPLOYED
**Status:** development implementation; high-conviction statistical evidence integration remains an explicit gate.

## Owner intention

Trading temperament controls the *quality threshold, risk-budget utilisation,
and conditional pursuit of qualified winners*. It does not turn AI confidence
into broker orders or make AGGRESSIVE an all-trades, maximum-risk preset.

These are independent of authorization modes (OBSERVE / ADVISOR / DEMO_TRADER /
SHADOW_TRADER / LIMITED_LIVE / AUTONOMOUS_LIVE / HALTED).

- **NORMAL:** prioritises selective, risk-adjusted consistency. It requests
  25–55% of the already-signed per-strategy risk ceiling (specific fractions
  are deterministic functions of observable cost/regime/freshness).
- **RISKY:** permits somewhat broader valid regime setups with 45–85% of the
  signed ceiling. It is not permission to evade the ordinary Risk Authority.
- **AGGRESSIVE:** highly selective. It requires high market-quality thresholds
  **and independently admitted positive-edge statistics**. Verified high
  conviction requests 70% of the existing strategy risk budget; exceptional
  market+edge evidence may request 100% of the signed budget, never above it.
  Absent, stale, manipulated or insufficient evidence means NO_TRADE.

The percentages above are starting **engineering policy values**, not
research-calibrated profit-maximising optimums. They need forward/paper
validation before an owner signs them for live use. Fractional Kelly, confidence
probabilities, or expected win rates are **not** fabricated.

## Implemented path

```text
Owner trading mandate (signature over existing mandate ID/version)
    + separate content-bound trading-temperament-admit signature
               |
      NORMAL/RISKY/AGGRESSIVE (optional, per account or strategy)
               |
       existing OpportunityEngine creates sealed candidates
               |
       TemperedOpportunityAllocator ranks quality/admission
               |
       AccountDecisionCoordinator rechecks profile verdict
       and refreshes RiskSnapshot for every admission
               |
       requested risk = min(capsule ceiling, signed strategy budget)
                        × eligible profile's risk fraction [0,1]
               |
       IntentFactory makes sealed TradeIntent
               |
       unchanged RiskAuthority evaluates; no route bypass
               |
       unchanged execution router / reconciler / kill switch
               |
       trade lifecycle: existing permitted adjustment policy
       → mode can reduce an approved partial-take fraction,
         but may not enable a new ADD/EXIT/re-entry/pyramiding action
```

**Backward compatibility:** omitted profile fields cause the pre-existing
allocator and coordinator behaviour (LEGACY) to remain unchanged. The
explicit NORMAL profile is *not* silently activated for old mandates.

**Explicit owner authority:** a new profile or override is accepted only if the
mandate contains a second valid owner token under action
`trading-temperament-admit`. Its signed subject is computed by
`trading_temperament_subject(mapping)`; this hashes the entire original mandate
document including its owner signature and risk limits, excluding only the new
temperament token itself. Changing strategy budgets, profile, scope, or expiry
after signing invalidates this second signature. Obtain the signature through
the existing owner key ceremony, not an AI agent. Use a new mandate version
when changing policy. No active live mandate was changed in this branch.

Example of the *unsigned inputs* to an owner's new mandate-version request:

```json
{
  "trading_temperament": "NORMAL",
  "strategy_temperaments": {
    "FX-TREND-03": "AGGRESSIVE",
    "FX-LONDON-BREAKOUT-04": "RISKY"
  }
}
```

The complete original mandate fields, its valid ordinary owner signature, and
the **new** content-bound `temperament_owner_signature_ref` must also be present.
The latter is an owner-issued token, not an arbitrary string or model output.
Do not commit private keys, credentials or real signed tokens to Git.

## Entry constraints and evidence provenance

Candidate inputs are checked for seal integrity, freshness, account and
strategy scope, source market hashes, feature contract hash, expected
gross-move/cost multiple, and regime compatibility. Profile ranking excludes
the rule-based/un-calibrated `confidence_score`.

**Important active limitation:** the production account runtime does not yet
supply an independently verified `AdmittedEdge` provider to
`TemperamentPolicy`. Therefore, selecting AGGRESSIVE in the current branch
will **refuse** candidates rather than trade on unsupported optimism. Tests
exercise the provider interface with fixture evidence. This is deliberately
not portrayed as live high-conviction certification.

A future producer must independently verify strategy evidence (sample
sufficiency, reliable positive edge-floor, cost, execution quality, regime
stability, validation certificate, expiry and candidate identity), bind it to
the full candidate context, then expose it via the read-only
`admitted_edge_fn` callback. A dataclass hash by itself is **not** proof
of an independent validation authority. Production wiring must be a reviewed
change and pass replay and independent broker-disabled shadow tests.

An exceptional grade prioritises scarce account admission slots over
ordinary candidates. This is not a capital reservation or broker heat
preapproval. The account Risk Authority still makes the actual portfolio-heat,
drawdown, account reconciliation, margin, leverage and risk decisions.

## Profit pursuit

Only positions whose **existing adjustment policies permit** partial profit
taking can be affected:

- NORMAL/LEGACY: preserve the capsule's original partial-take fraction.
- RISKY: cap early partial take at 25% of the remaining position.
- AGGRESSIVE: cap early partial take at 15% of the remaining position.

These modes do **not** widen stops or delay invalidated-thesis/urgent-health
exits. Explicit capsule targets, time stops, the regular preservation system,
Risk Authority and reconciler stay authoritative. The lifecycle retains its
existing separately admitted ADD / scale policy mechanism; choosing AGGRESSIVE
does NOT enable pyramiding or mark-to-market-only additions. This branch does
not silently invent new strategy signals for re-entry.

## Fail-closed boundaries

- All `HARD_FORBIDDEN_BEHAVIOURS` remain unmodified.
- Every proposed entry continues through an entirely new sealed
  `TradeIntent` and `RiskAuthority` evaluation, then the existing router.
- Profile fractions never exceed one and never alter PlatformCeilings or
  `strategy_risk_budgets`.
- Profile/candidate/evidence admission decisions are deterministic and sealed.
- Allocation decisions carry profile verdict/evidence hashes. Coordinator pass
  outcomes and the hash-chained ledger retain profile provenance.
- Model confidence, synthetic certainty and unsupported probabilities cannot
  increase the base risk budget.
- Standalone single-symbol SessionService/DecisionCycle **refuse to start**
  when a temperament is explicitly selected; their incompatible path must not
  ignore the signed intent.
- No hot changes to running account profile; changing it requires a new signed
  mandate and restart, with reconciliation before new entry permission.
- No live positions/orders/account configuration were mutated by this branch.

## Test invocation

On an isolated development checkout:

```bash
PYTHONPATH=trading uv run --no-project --with pytest --with pytest-asyncio \
  --with cryptography python -m pytest -q \
  trading/tests/test_trading_temperament.py \
  trading/tests/test_account_coordinator.py \
  trading/tests/test_capital_promotion.py \
  trading/tests/test_account_trade_lifecycle.py \
  trading/tests/test_mandate.py \
  trading/tests/test_live_risk_is_real.py \
  trading/tests/test_execution_and_exits.py
```

### Before production adoption

1. Build and independently qualify an evidence producer against authenticated
   historical/live trade and execution records. The current AGGRESSIVE
   provider is intentionally **UNBOUND**.
2. Backtest and walk-forward each profile, including costs, slippage,
   symbol correlations, missed opportunities, severe volatility and regime
   shifts. No live deployment solely on passing unit tests.
3. Verify an actual owner-issued content-bound profile signature and revision
   policy; no model may sign it.
4. Demonstrate passive monitoring of per-account mode, profile, refused
   candidates and fractional risk requests before trial/demo activation.
5. Independently validate any future continuation/pyramiding or risk-capacity
   reservation logic rather than bypass existing capsule promotion controls.

## Parallel implementation comparison

A separately scoped VAN Muse task was requested on branch
`muse/vati-opportunity-modes-20261008`. Review both implementations' tests,
authority boundaries, evidence calibration, market-data interfaces and
post-entry correctness independently. Merge neither branch automatically.
