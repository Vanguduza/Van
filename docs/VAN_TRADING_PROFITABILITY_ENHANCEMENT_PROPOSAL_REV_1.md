# VAN trading intelligence and profitability — enhancement proposal Rev 1

**Status:** Proposal. **Not an authority document.** It amends nothing. Every item that changes live risk
requires an owner-signed decision artifact under `PROJECT_CANONICAL_STATE.json → policy.agent_self_authorization_forbidden`.
**Repository state considered:** `main` @ `66e4e42` (`0.5.0-dev`, `SCHEMA_VERSION = 26`).
**Authorities consulted:** `docs/VAN_TRADING_SYSTEM_BLUEPRINT_REV4_CONSOLIDATED.md`,
`docs/VAN_TRADING_PRODUCTION_DEPLOYMENT_BLUEPRINT_REV5.md`, `trading/architecture/stack_lock.json`.
**Authored:** 2026-09-19, from a repository review plus owner refinement.

---

## 1. The governing observation

Every intelligence path in VATI can only reduce risk.

| Mechanism | File | Behaviour |
|---|---|---|
| Sizing multipliers | `trading/vati/risk/sizing.py` | `clamp_multiplier` bounds every input to `[0,1]` — *"intelligence may only reduce risk below the mandate, never amplify it"* |
| Capsule health | `trading/vati/learning/health.py:2` | *"Demotion is automatic; recovery/promotion never is"* |
| Counterfactuals | `trading/vati/learning/counterfactual.py` | five of six variants are more conservative (`HALF_SIZE`, `SKIP_TRADE`, later entry, structure stop, HTF confirmation). No expansive variant exists |
| Mandate | `trading/vati/risk/mandate.py:123` | one `max_risk_per_trade` for every capsule in the mandate |

As a **live actuation** invariant this is correct and should be permanent. Applied to the *whole* system it
means VATI is structurally incapable of discovering that it is under-allocated to a durable edge. A system that
can only shrink converges toward trading nothing.

The resolution is not to weaken the clamp. It is to separate the two loops that are currently fused:

```text
FAST SAFETY LOOP                         SLOW UPSIDE LOOP
trade evidence                           validated evidence
   ↓                                        ↓
decay / cost / regime / correlation      DSR + PBO + walk-forward + live/shadow
   ↓                                        ↓
AUTO REDUCE / DEMOTE / SUSPEND           capital-budget proposal
   ↓                                        ↓
immediate, no approval                   OWNER APPROVAL (A4)
                                            ↓
                                         new signed mandate version
                                            ↓
                                         larger strategy ceiling
```

Automatic learning still only reduces, demotes, suspends, tightens or **proposes**. Nothing learns itself into
more live risk. What is added is a deliberately slower Capital Promotion Plane that turns validated evidence
into an owner-signed mandate amendment.

This preserves the strongest property VATI currently has — *models may discover opportunity; they may not
authorize themselves to take more risk* — while removing the ceiling on what discovery is worth.

---

## 2. Repository findings

Each was verified against `main` @ `66e4e42`.

### F1 — One mandate-wide risk fraction, no per-strategy allocation

`TradingMandate` (`trading/vati/risk/mandate.py:115-137`) carries a single `max_risk_per_trade`. There is no
owner-level strategy allocation map. `FX-TREND-PULLBACK-01` in `DEMO` draws the same base risk as a capsule
with a long `CERTIFIED_LIVE` record. Equal-weighting a 0.35R capsule against a 0.05R capsule discards most of
the first one's edge.

### F2 — `correlation_multiplier` is dead code

`TradeIntent.correlation_multiplier` is declared (`trading/vati/risk/contracts.py:156`, default `Decimal("1")`),
carried by serde (`trading/vati/risk/serde.py:12`) and consumed by the Risk Authority
(`trading/vati/risk/authority.py:283`). **Nothing populates it.** `OpportunityEngine` builds the intent with
exactly five multipliers — regime, confidence, volatility, liquidity, event risk
(`trading/vati/arbiter/opportunity.py:65-66, 92-93`). The field is permanently `1`.

The only live correlation control is `currency_leg_exposure` (`trading/vati/risk/heat.py:46`), a structural
per-currency cap. It does not see EUR/GBP co-movement beyond the shared USD leg, XAUUSD against the dollar, or
ZSE names moving together on a ZiG regime shift — even though `CurrencyRegime` is already computed.

### F3 — DSR and PBO are computed and discarded, and the documented gate is vacuous

`deflated_sharpe` and `pbo_cscv` exist in `trading/vati/backtest/metrics.py` and are referenced **only** by
`trading/tests/test_backtest_runner_cli.py` and the `__init__` re-export. No promotion or admission path
consumes them.

Worse, the repository carries two incompatible DSR gates:

| Source | Gate |
|---|---|
| `trading/vati/backtest/metrics.py` docstring | `> 0.95 ⇒ DSR passes` — the function returns a **probability** via `_norm_cdf` |
| `docs/VAN_ADAPTIVE_TRADING_INTELLIGENCE_TECHNICAL_BLUEPRINT_REV3.md:40` (D7) | `deflated Sharpe > 0` |
| `docs/VAN_ADAPTIVE_TRADING_INTELLIGENCE_TECHNICAL_BLUEPRINT_REV2.md:551` | `deflated Sharpe > 0` |
| `trading/vati/learning/curriculum.py:21` | `DSR > 0.95` — correct |

`deflated_sharpe` returns `_norm_cdf(z)`, which is strictly positive for every finite `z`. A `> 0` gate is
therefore **not merely ambiguous — it passes every strategy that reaches the function at all**, including one
with a negative observed Sharpe. The only input that returns exactly `0.0` is the `n_obs < 3 or n_trials < 1`
guard. An implementation agent could correctly call the function and implement a gate that certifies noise.

**Normalize the contract to an explicit named field — `dsr_probability >= 0.95` — and correct Rev 2 §551 and
Rev 3 D7.** This is the highest-severity item in this document and it is a documentation fix.

### F4 — Promotion carries authority but no validation content

`CapsuleRegistry.promote` (`trading/vati/strategies/capsule.py:106-128`) correctly requires an owner approval
signature scoped to the target state, and requires `evidence_refs` to be non-empty for `LIMITED_LIVE` and
`CERTIFIED_LIVE`. But `evidence_refs` is `list[str]` — opaque. Nothing verifies that the evidence contains a
DSR result, a PBO result, a walk-forward window count or a cost-stress outcome. The gate proves *someone
signed*, not *what was proven*.

### F5 — Exit policy is fixed after registration

`ProtectionManager.register` (`trading/vati/execution/protection.py:49-53`) takes `break_even_trigger` and
`trail_distance` once; `on_mark` only tightens. `target_model` is a fixed string in the capsule JSON
(`"3 ATR"` for `FX-TREND-PULLBACK-01`). Meanwhile `trading/vati/learning/missed.py` already computes `mfe` and
`mae` per episode and discards them after scoring a verdict.

### F6 — TCA already drives behaviour; the gap is narrower than first stated

**Correction to the initial review.** The claim that "nothing acts on TCA" was wrong. The path exists and is
production-shaped:

```text
ExecutionReceipt → compute_tca() → LearningBroker.observe()
   → BrokerExecutionProfile (median/p95 cost ratio, slippage, rejection rate, event cost ratio)
   → broker_liquidity → MetaLabeler (meta_labeler.py:78, reduce-only, 0 = SUSPENDED)
   → reduce / skip / suspend
```

`trading/vati/learning/broker.py` correctly weights `BACKTEST/REPLAY/COUNTERFACTUAL` execution facts at zero.
So TCA already changes future behaviour **defensively**. What is missing is the *choice* dimension: nothing
selects between order types, sessions or venues on measured execution quality. `FxCostModel.estimate` models
`order_passive` as saving half a spread, and `ExecutionRouter.execute` takes `entry_type` as a caller argument
defaulting to `"LIMIT"` — so the decision exists but is never learned.

---

## 3. Proposals

### P1 — Per-strategy capital budgets as a slow authority layer

Add to `TradingMandate`:

```text
strategy_risk_budgets:
    FX-TREND-PULLBACK-01:   0.0075
    FX-LONDON-BREAKOUT-01:  0.0030
    GOLD-TREND-POSITION-01: 0.0060
```

bounded by:

```text
0 < strategy_risk_budget
      <= mandate.max_risk_per_trade
      <= PlatformCeilings.max_risk_per_trade
```

Live sizing becomes:

```text
base_risk = min(owner_strategy_budget, capsule_ceiling, mandate_ceiling, platform_ceiling)

approved_risk = base_risk
    × regime × volatility × liquidity × event × confidence × correlation × drawdown
```

Every runtime multiplier stays `<= 1`; `clamp_multiplier` is unchanged.

The increase mechanism is a **`CapitalBudgetProposal`**, never an automatic raise:

```text
strategy_id, current_budget, proposed_budget
certified_expectancy, lower_confidence_expectancy
live_sample, shadow_sample
dsr_probability, pbo
cost_stress_result, regime_stability
tail_risk, max_drawdown
evidence_refs
```

Only an owner-signed new mandate version changes the number.

### P2 — Correlation is two systems, not one

**Refinement of the initial review.** Rolling R-multiple correlation was proposed for the open book; that is
the wrong instrument. R-multiples measure realised per-trade *outcome* correlation between strategies. They do
not represent the instantaneous market covariance of currently open EURUSD, GBPUSD and XAUUSD positions. Both
are needed, for different jobs:

```text
MARKET EXPOSURE CORRELATION          STRATEGY RETURN CORRELATION
instrument returns / risk factors    realised + shadow R-multiples
→ controls open-book concentration   → controls slow capital allocation (P1)
→ live, reduce-only                  → proposal-time only
```

For the live book, add a `PortfolioDependencyEngine` with a shrinkage/stability-aware covariance over
instrument returns and explicit factor tags — `USD`, `EUR`, `GBP`, `JPY`, `gold`, `rates`, `risk-on/off`,
`ZiG`, ZSE sector, `VFEX/USD` — and size the *increment*:

```text
risk_before      = portfolio_tail_risk(existing_book)
risk_after       = portfolio_tail_risk(existing_book + candidate)
incremental_risk = risk_after - risk_before      →  correlation_multiplier ∈ [0,1]
```

Add a stressed correlation matrix alongside the normal one: correlations tend to converge precisely when a
portfolio is under stress, so the joint tail is the thing to measure, not the sum of independent position risks.

This gives three complementary and non-overlapping risk views — stop-risk heat, currency-leg exposure,
portfolio dependency/tail risk — and replaces none of them.

### P3 — A sealed `StrategyValidationCertificate` as a non-bypassable promotion gate

Do not scatter `deflated_sharpe()` calls. Produce one sealed artifact:

```text
strategy_id, strategy_version
data_manifest_hash, feature_revision, cost_model_revision
n_trials, trade_count, walk_forward_windows
expectancy_R, profit_factor, max_drawdown, sharpe
dsr_probability, pbo, cpcv_configuration
cost_stress_2x, latency_slippage_stress
parameter_perturbation_stability, regime_breakdown, leakage_switch_result
validation_hash
```

and make `CapsuleRegistry.promote` require it rather than an opaque string (closing **F4**):

```text
RESEARCH    → BACKTEST     ordinary research evidence
BACKTEST    → VALIDATION   minimum data/trade gates
VALIDATION  → DEMO         dsr_probability >= 0.95, pbo <= 0.10,
                           walk-forward green, leakage green, cost stress green
SHADOW      → LIMITED_LIVE owner signature + certificate + shadow evidence
LIMITED_LIVE→ CERTIFIED_LIVE owner signature + real execution and cost evidence
```

### P4 — Exit research, with no learning directly from winners

**Refinement of the initial review.** Deriving trailing and break-even parameters from "MAE of winners"
introduces selection bias: conditioning on the outcome selects paths that happened not to stop out. Instead
preserve the full post-entry path for every completed historical/shadow trade and evaluate a *fixed registered
family* offline:

```text
original fixed target · time exit
exit 1 bar later · exit N bars later
scale 50% at 1R + trail · scale 33/33/34
ATR trail · structure trail · volatility-adjusted trail
break-even at 0.75R / 1R / 1.5R · no break-even
fixed 2R / 3R / 4R · regime-conditioned target
LET_RUN until invalidation
```

These are research variants, never live mutations. Each candidate passes the same walk-forward, CPCV/PBO, DSR,
cost-stress and regime splits as any other capsule revision before becoming a proposal.

Store, by strategy × regime × session × volatility regime × event state: MFE and MAE distributions,
time-to-MFE, time-to-MAE, time-to-target, post-exit continuation, and give-back from MFE. That lets VAN state
something actionable — *"Trend Pullback winners typically tolerate 0.42R adverse excursion before reaching
2.8R MFE, while the current break-even rule exits 31% of eventual winners"* — rather than moving stops blindly.

Also extend `CounterfactualVariant` with expansive members (`EXIT_ONE_BAR_LATER`, `SCALE_OUT_HALF_AT_1R`,
`TRAIL_INSTEAD_OF_FIXED_TARGET`). Counterfactual output is already `SIMULATED`, weight 0.2, aggregated only at
capsule level, so widening the hypothesis space carries no actuation risk — it only widens what the owner is
told.

### P5 — Extend TCA into an `ExecutionPolicyEngine`

Building on the existing `LearningBroker` path (**F6**), learn per broker × symbol × session × volatility
bucket × event proximity × direction × order type:

```text
fill probability · time to fill · partial-fill probability
slippage · spread captured · post-fill adverse movement
cancel/requote rate · opportunity cost of non-fill · realised implementation shortfall
```

and choose deterministically among **owner-approved sealed templates**:

```text
PASSIVE · PASSIVE_THEN_CROSS · LIMIT_AT_TOUCH
LIMIT_WITH_BOUNDED_CHASE · MARKET_WITH_SLIPPAGE_CAP · DO_NOT_EXECUTE
```

No model emits an arbitrary order. It selects a template, under deterministic hard limits. This replaces the
current "passive saves half a spread" approximation with the real trade-off — fill probability against adverse
selection against non-execution opportunity cost.

---

## 4. Further enhancements

| Enhancement | Why | Authority behaviour |
|---|---|---|
| Continuous volatility targeting | Vol handling is bucketed `LOW/NORMAL/HIGH/EXTREME`; a continuous realised-vol target avoids oversizing into rising vol and uses calm regimes more efficiently | Reduce-only live multiplier |
| Portfolio Expected Shortfall / scenario engine | Stop-risk alone misses gaps, correlated shocks and simultaneous stop slippage | Reduce/reject only |
| Strategy overlap detector | Two capsules can express the same latent bet and consume risk twice | Reduce-only |
| Uncertainty-adjusted expectancy | Prefer a lower-confidence bound over mean R, so small-sample winners do not attract capital | Capital proposal only |
| Calibrated meta-labeler v1 | `confidence.py` is explicitly `RULES_V0_UNCALIBRATED`; build the promised Brier/ECE gate before any probability sizes anything | Shadow/display first, then reduce-only |
| Champion/challenger shadow fabric | Explore aggressive exits, features and execution policies without capital at risk | Challenger cannot execute |
| Cross-broker execution selection | Where an approved instrument exists on several linked venues, execution quality — not strategy logic — should pick the venue | Only among owner-authorized accounts/venues |
| Funding/rollover intelligence | Swing strategies lose real expectancy to swap, triple-rollover and broker financing schedules | Cost gate / scheduling |
| Browser-powered evidence intelligence | The Oracle browser can inspect central-bank releases and primary sources continuously, with provenance | T2/research only; never order generation |
| Market-data disagreement detector | Compare execution feed against an independent reference to catch stale or bad broker quotes | Halt/reduce only |

Continuous volatility targeting has reasonable empirical support — reducing exposure as realised volatility
rises has improved Sharpe across several historical factor portfolios, currency carry among them. That is not
evidence it will improve any *particular* VATI capsule, so it is admitted only through VATI's own
walk-forward/DSR/PBO evidence, like anything else.

### Uncertainty-aware capital proposals

VATI currently asks *what is the estimated expectancy?* It should ask *what is the worst plausible expectancy
consistent with our evidence?*

```text
mean +0.34R, interval [-0.02R, +0.70R]     ← do not allocate
mean +0.34R, interval [+0.22R, +0.46R]     ← allocate
```

Capital proposals should key on an `edge_floor` — a lower confidence or calibrated bound — rather than mean R.
Conformal methods are interesting here because they target calibration under non-stationarity, but the
generalisation record is mixed and development-period gains often fall sharply out of sample. Use them in
shadow research first; do not place a recent paper inside the Risk Authority.

That is the same principle as the rest of this document: **sophisticated models to quantify uncertainty and
propose; simple deterministic authority to actuate.**

### Browser-sourced trading evidence

The Remote Browser programme gives VATI something Rev 4/5 did not assume: a durable Oracle-side research
surface. Add a `TradingEvidenceCollector` above Stagehand:

```text
primary source → Stagehand retrieval → Browser Harness provenance
  → structured extractor → TradingEvidenceArtifact → VTIL admission
  → Hermes assessment → T2Assessment (TTL + evidence refs) → MetaLabeler
```

Scope: central-bank statements, economic releases, rate announcements, company results, ZSE/VFEX notices,
corporate actions, broker specification changes, margin/swap changes, session changes.

The existing boundary is preserved exactly:

```text
browser/LLM evidence MAY:  explain · classify · flag contradiction · reduce confidence
                           · trigger research · propose strategy revision
                    MAY NOT: set lot size · widen stop · create a live strategy
                           · promote a capsule · bypass the Risk Authority · send an order
```

---

## 5. Target architecture

```text
MARKET / RESEARCH INTELLIGENCE
   market data ─── events/macro ─── browser evidence ─── VTIL
                            ▼
                      MARKET STATE
                ┌───────────┴───────────┐
        strategy candidates      uncertainty state
                └───────────┬───────────┘
                            ▼
                   OPPORTUNITY ENGINE
          regime / cost / execution / correlation
                            ▼
                       TradeIntent
              ═ DETERMINISTIC RISK AUTHORITY ═
                            ▼
                    Execution Policy  →  Broker
                            ▼
              TCA ───────────────────── trade outcome
                            ▼
                  EXPERIENCE / LEARNING
                ┌───────────┴───────────┐
        FAST SAFETY LOOP          SLOW UPSIDE LOOP
        auto reduce/demote        validation certificate
                                  capital proposal
                                        ▼
                                    OWNER A4
                                        ▼
                                new signed mandate
```

---

## 6. Priority order

1. **F3 DSR contract normalization** — a documentation fix that today permits a vacuous gate. Do this first;
   it costs nothing and everything downstream depends on it.
2. **P3 StrategyValidationCertificate** wired into `CapsuleRegistry.promote` (closes F3's discard and F4's
   opaque evidence).
3. **P1 per-capsule owner risk budgets** plus the `CapitalBudgetProposal` plane.
4. **P2 PortfolioDependencyEngine**, populating the dead `correlation_multiplier`.
5. **P5 ExecutionPolicyEngine** and **P4 exit-policy research**.
6. Continuous volatility targeting and portfolio Expected Shortfall.
7. Calibrated uncertainty (`edge_floor`) and browser-powered evidence intelligence.

Items 1, 2 and 4 change no live risk and need no new owner authority beyond the existing promotion signature.
Item 3 is the one that requires a new owner decision artifact, because it is the only one that can raise a
ceiling.

---

## 7. What must not change

- `clamp_multiplier` stays `[0,1]`. No runtime multiplier may exceed 1, ever.
- Automatic learning reduces, demotes, suspends, tightens or proposes. It never raises a ceiling.
- The Risk Authority stays deterministic. No model output sizes a trade directly.
- `MetaLabeler` stays `RULES_V0_UNCALIBRATED` until a Brier/ECE gate exists and passes.
- Browser and LLM evidence never generate orders, never promote a capsule, never bypass the Risk Authority.
- VATI remains the single execution route. Nothing here creates a second sender.
