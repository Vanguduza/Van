# VAN trading intelligence and profitability — enhancement proposal Rev 1.2

**Status:** Proposal. **Not an authority document.** It amends nothing. Every item that changes live risk
requires an owner-signed decision artifact under `PROJECT_CANONICAL_STATE.json → policy.agent_self_authorization_forbidden`.
**Repository state considered:** `main` @ `66e4e42` (`0.5.0-dev`, `SCHEMA_VERSION = 26`).
**Authorities consulted:** `docs/VAN_TRADING_SYSTEM_BLUEPRINT_REV4_CONSOLIDATED.md`,
`docs/VAN_TRADING_PRODUCTION_DEPLOYMENT_BLUEPRINT_REV5.md`, `trading/architecture/stack_lock.json`.
**Authored:** 2026-09-19, from a repository review plus two rounds of owner refinement.
**Rev 1.2 amends:** P7 to the `AccountDecisionCoordinator` architecture (option (c)), adds the sequential
shared-heat procedure and `AllocationEpisode` evidence. The implementation specification derived from this
document is `docs/VAN_DETERMINISTIC_TRADING_SYSTEM_ENHANCEMENT_MODULE_REV_1.md`; this document remains
non-authoritative rationale and evidence.

**Rev 1.1 added:** §4 Market-State and Feature Intelligence Expansion (MS-1…MS-9), the Portfolio Opportunity
Allocator (F10, P7), the Strategy Coverage Map (P8), the Feature Drift Monitor (P9), capital-efficiency
intelligence (P10), and a revised priority sequence with three integrity prerequisites ahead of certification.

The market-state and feature work is **not** a separate initiative. It strengthens the same architecture from
the data end, and keeping it in one document makes the dependency chain explicit:

```text
market data → feature provenance / required_features enforcement → multi-timeframe market state
  → feature expansion + redundancy gate → strategy signals → StrategyValidationCertificate
  → Portfolio Opportunity Allocator → Risk Authority
```

MS-numbering is used inside §4 so the feature items do not collide with the existing P-series.

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


*(F7, F8 and F9 concern market-state and feature representation; they are stated in §4, where the
work that closes them lives.)*

### F10 — There is no runtime in which two candidates coexist, so portfolio heat is allocated by arrival order

This is the structural version of "no portfolio allocator", and it is sharper than a missing module.

```text
trading/vati/app/cycle.py:1   "one pass per bar/tick for one instrument"
SessionConfig.symbol: str      one symbol per session
process_lock.py:1              "One live session per account alias"
deploy README                  vati-session@<alias>.service — DecisionCycle per account
```

One account alias runs one session, which decides one symbol; the advisory `flock` forbids a second session on
the same alias. Meanwhile the *risk model* is written for a multi-instrument book — `TradingMandate.instruments`
is a `frozenset`, and `max_open_stop_risk`, `max_total_positions` and `max_currency_leg_exposure` are
portfolio-wide. `DecisionCycle._open_positions()` reads `adapter.positions()`, i.e. the whole account book, so
heat is *measured* across instruments.

The result is a **portfolio-wide constraint evaluated at a single-instrument decision point**. Whichever
session's bar closes first consumes the shared heat budget. A marginal EURUSD setup firing at 09:00:01 takes
capacity that a materially better GBPUSD setup at 09:00:03 then cannot have. Allocation is arrival-ordered,
not merit-ordered, and nothing in the system ever compares the two.

The gap is between the risk model's ambition and the runtime's shape. An allocator therefore needs a place to
stand that does not yet exist: either a multi-symbol `DecisionCycle`, or a cross-session coordination point.
That is a prerequisite to scope deliberately, not an implementation detail of the allocator itself.

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


### P6 — *(superseded)*

The Indicator Intelligence Layer is specified in §4 as MS-1…MS-9.

### P7 — `OpportunityPortfolioAllocator`

The highest-value addition in Rev 2. VATI answers *"is this trade individually acceptable?"* well. It should
also answer:

> Given the other opportunities and the risk already in the book, is this the best use of the next unit of
> risk capacity?

A deterministic allocator sits **between the Opportunity Engine and the Risk Authority**. It ranks approved
candidates on lower-bound expectancy (the `edge_floor` of §4), incremental Expected Shortfall (from P2's
`PortfolioDependencyEngine`), strategy overlap, execution cost and fill probability (from P5), regime
stability, and capital holding time (P10).

**It selects which candidates proceed. It never enlarges any candidate's risk.** Every runtime multiplier
still `<= 1`; the allocator's only power is to say *not this one, that one*.

Per **F10** this needs a place to stand. Two earlier options — a multi-symbol `DecisionCycle` (a) and a
cross-session coordinator (b) — are **superseded**. `DecisionCycle` carries too much symbol-specific state to
become an N-symbol state machine safely: `RegimeEngine`, symbol contract state, `ProtectionManager`
bookkeeping, TCA learning, `_entries` tracking and symbol-scoped idempotency seeds
(`f"{account_alias}:{symbol}:{as_of_ms}"`). Widening it would multiply every one of those into a collection
and put the shared heat budget inside a loop that also owns per-symbol execution state.

The canonical architecture is **(c) `AccountDecisionCoordinator`** — one authoritative process per account
alias, preserving the existing `process_lock` guarantee:

```text
AccountDecisionCoordinator            one authoritative process per account alias
    ├── InstrumentEvaluator[EURUSD]
    ├── InstrumentEvaluator[GBPUSD]
    ├── InstrumentEvaluator[XAUUSD]
    ├── CandidatePool
    ├── PortfolioDependencyEngine
    ├── OpportunityPortfolioAllocator
    ├── RiskAuthority
    ├── ExecutionRouter
    └── AccountRuntimeLease
```

`InstrumentEvaluator` keeps everything today's `DecisionCycle` owns per symbol — regime, contract, protection,
TCA, idempotency — and stops one step earlier. It emits a `CandidateOpportunity`, not a `TradeIntent`:

```text
N InstrumentEvaluators → CandidatePool → AccountDecisionCoordinator
    → OpportunityPortfolioAllocator → TradeIntent → Risk Authority
```

**`CandidateOpportunity` is deliberately weaker than `TradeIntent`.** It carries no approved size, no control
over protection, and no path to `ExecutionRouter`. Only the coordinator, after allocation, mints a
`TradeIntent` — so the router's input contract is unchanged and nothing upstream of the Risk Authority gains
reach it did not have.

#### Shared-heat procedure

The allocator must not approve several candidates against one stale portfolio snapshot, and it must not become
a shadow Risk Authority by pre-deciding what will fit. Heat is therefore consumed **strictly sequentially**,
with portfolio truth refreshed between candidates:

```text
rank fresh candidates
    ↓
candidate #1
    ↓
fresh portfolio snapshot
    ↓
Risk Authority
    ↓
execute / reject
    ↓
refresh portfolio truth
    ↓
candidate #2
```

The ranking is computed once per pass; the *admission* is re-evaluated per candidate against live state. A
candidate that ranked second may be rejected outright once the first one's risk is in the book — which is the
correct outcome, and is the Risk Authority's decision, not the allocator's.

#### Allocation evidence

Selection policy is itself a hypothesis and must be falsifiable. Every pass records:

```text
AllocationEpisode {
    selected_candidate
    rejected_candidates
    portfolio_snapshot_hash
    ranking_features
    selection_reason
    realised_selected_outcome
    counterfactual_rejected_outcomes
}
```

This lets VAN discover whether its capital-selection policy is actually superior — for example, that it
repeatedly took +0.3R setups while rejecting +1.8R alternatives — **without changing the allocator live**. The
rejected candidates' outcomes are scored on the same bounded, hindsight-guarded basis as `missed.py`, over the
setup's own horizon window, and carry `SIMULATED` weight.

A new allocation policy is a research candidate like any other: offline walk-forward, DSR and PBO before it
replaces the incumbent.

### P8 — Strategy Coverage Map

Six capsules is a good production library, not a strategy universe. Build a `StrategyCoverageMap` across
asset × horizon × regime × style, and let the gaps drive research.

```text
covered:    trend pullback · session breakout · event drift · gold positioning
            ZSE value rotation · ZSE liquidity provision
uncovered:  range / mean-reversion · volatility expansion and contraction
            relative-value / pairs · cross-sectional momentum
            carry / roll · defensive regime strategies
```

Note the regime consequence: `FX-TREND-PULLBACK-01` declares `forbidden_regimes: [TRANSITION, EXTREME]` and
`eligible_regimes: [BULL, BEAR]`. **RANGE is uncovered across the FX book** — when the regime engine reports
RANGE, VATI has no eligible FX capsule at all. That is a measurable idle-capital cost, and the coverage map
makes it visible instead of implicit.

Missing coverage produces **research candidates only**. Nothing enters live use except through P3's
certificate and an owner signature.

### P9 — Feature and Edge Drift Monitor

`StrategyHealthTracker` measures realised strategy performance, process correctness, cost ratio and regime
fit — all at capsule level. Underneath it, nothing asks whether the *features* still carry information.

Track each feature's incremental value by strategy × instrument × timeframe × regime. If RSI or a structure
feature contributed historically and has become redundant or unstable, flag it for research **before** the
capsule has lost substantial money. Capsule health is a lagging indicator of feature decay; this is a leading
one.

Lives in VTIL/shadow research. It proposes; it never mutates a live capsule.

### P10 — Capital-efficiency and opportunity-cost intelligence

Expectancy in R is not enough. Two capsules at +0.3R are not equivalent if one occupies risk for two hours and
the other for four days.

Measure and record:

```text
expected_R_per_risk_day · fill probability · financing / rollover cost
capital occupancy · rejected-alternative opportunity cost
```

Used by P7's ranking and by the slow Capital Promotion Plane (P1). **Never as an automatic multiplier above
1** — a capital-efficient strategy earns a larger owner-signed ceiling, not a runtime boost.

This also connects to the funding/rollover item in §4: a swing capsule losing expectancy to triple-rollover
Wednesdays is a capital-efficiency defect that per-trade R will never surface.

---

## 4. Market-State and Feature Intelligence Expansion

This section closes F7, F8 and F9 and specifies the feature work. It is ordered as a dependency chain: nothing
below MS-3 is safe to build before MS-1 and MS-2 are closed, because a validation certificate must not certify
a strategy against an ambiguous market-state representation or a silently missing feature dependency.

### MS-1 (F7) — Timeframe is absent from `FeatureVector` and `MarketState`

`build_market_state(*, symbol, base, quote, bars: Sequence[Bar], ...)`
(`trading/vati/intelligence/market_state.py:49`) takes **one** bar sequence. `MarketState` carries one
`FeatureVector` and one `RegimeState`, and neither has a `timeframe` field.

Two consequences, the second worse than the first:

1. No strategy can express "H4 structural trend, H1 confirmation, M15 setup, M5 timing". Every question is
   answered from one sequence.
2. An M5-built state and an H1-built state for the same symbol at the same instant are **indistinguishable by
   their recorded fields**, and `state_hash` does not separate them. `missed.py`'s `ex_ante_snapshot_hash` and
   the ledger's decision record therefore would not identify what VATI actually looked at, the moment two
   timeframes coexist.

Fix (2) before building (1). It is a field addition to an audit record, not a feature.

The storage tier is already multi-timeframe — `trading/vati/market_data/feeds/lake.py:18`:

```python
TIMEFRAMES_MS = {"M1": 60_000, "M5": 300_000, "M15": 900_000, "H1": 3_600_000, "H4": 14_400_000, "D1": 86_400_000}
```

one directory per symbol/timeframe, with slice manifests. Only the state tier is single-sequence, which makes
multi-timeframe substantially cheaper than it appears.

**Treat this as an audit/provenance defect, not a feature request.** Add `timeframe` to `FeatureVector` and
`MarketState`, and include it in canonical serialization and `state_hash`, **before** multi-timeframe state
exists. Retrofitting it afterwards means every state recorded in between is unattributable.

### MS-2 (F8) — `required_features` is declarative but unenforced

Capsule JSON declares `required_features` — for `FX-TREND-PULLBACK-01`:
`["ema_fast", "ema_slow", "atr", "rsi", "swing_low", "swing_high"]`. **No file under `trading/vati/` reads that
key.**

Harmless today: there are eleven features and all are computed on every pass. It stops being harmless the
moment the registry grows — a capsule could declare `adx` and trade silently without it, or with `None`, and
nothing would notice. A declared-contract check is a **prerequisite** to expanding the feature set, not a
follow-up to it.

**Make it fail closed.** Capsule admission and per-pass evaluation must refuse when a declared feature is:

```text
missing from the registry · unavailable for this venue class
stale beyond its freshness contract · incompatible with the capsule's timeframe
None when the capsule declares it required
```

A capsule that cannot obtain a feature it declared does not trade on the remainder. It abstains, with a reason
code, exactly as it does for any other eligibility failure.

### MS-3 — `MultiTimeframeMarketState`

Reuse the lake's existing `M1/M5/M15/H1/H4/D1`. **Do not duplicate bar storage.** The storage tier is already
multi-timeframe with slice manifests; only the state tier is single-sequence.

Give capsules an explicit timeframe contract:

```text
structural_timeframe:  H4
regime_timeframe:      H1
setup_timeframe:       M15
execution_timeframe:   M5
```

so a strategy stops asking one sequence every question. `FX-TREND-PULLBACK-01` reads structure from H4,
confirms regime on H1, forms the pullback on M15 and times entry on M5.

#### Capsule schema migration

Adding a timeframe contract changes `capsule_hash`, which covers the whole capsule document. That must be an
explicit, provenanced migration — not a silent rehash — so VAN can distinguish schema evolution from strategy
mutation. `silent_strategy_mutation` is a hard-forbidden behaviour, and an unexplained hash change is
indistinguishable from one.

Each migrated capsule records:

```text
old_capsule_hash
new_capsule_hash
migration_reason        = MTF_SCHEMA_ADOPTION
strategy_logic_changed  = false
owner_authority_changed = false
migrated_at_unix
```

A migration asserting `strategy_logic_changed = false` must be mechanically verifiable — the entry, stop,
target and eligibility logic references are byte-identical to the parent. If they are not, it is a strategy
revision and takes the normal owner-signed promotion path instead.

### MS-4 — Venue-aware Feature Registry

Every feature declares its own applicability, so a feature cannot be silently computed where its inputs do not
mean what the name implies:

```text
feature_id · feature_version
venue_classes            FX_SPOT · CFD · SYNTHETIC · ZSE_EQUITY · VFEX
required_inputs          ohlc · ticks · volume · spread · depth
timeframe_constraints    minimum bar count, permitted timeframes
source_semantics         e.g. "tick count, not traded volume"
provenance_version
```

`source_semantics` is the field that matters. It is what stops `volume` silently meaning centralized traded
volume on an FX pair where no such quantity exists.

Per-value provenance travels with the computed feature, extending the existing `feature_version`:

```text
feature_id · feature_version · timeframe · lookback
value · normalised_value · percentile · regime · as_of · data_quality
```

### MS-5 — `FeatureValidationCertificate`

A feature must prove **incremental** value against the existing feature set — not merely standalone
correlation with returns. Standalone correlation is how a registry acquires five colinear trend measures and
manufactures confluence.

```text
feature_id · feature_version
baseline_feature_set          what it is being added to
incremental_dsr               DSR of baseline+feature vs baseline alone
incremental_pbo
walk_forward_delta
regime_stability              contribution by regime
instrument_stability          contribution by instrument
redundancy_metrics            correlation, mutual information vs baseline
leakage_result                the same one-switch decision-time test
validation_hash
```

Only a validated feature may enter a production capsule's `required_features`. This is the same evidence
standard as P3's `StrategyValidationCertificate`, deliberately reusing that machinery rather than inventing a
second one — and it inherits F3's corrected `dsr_probability >= 0.95` contract.

### MS-6 — Functional Confluence Engine

Aggregate evidence **by function**, never by tally:

```text
TREND        MOMENTUM      VOLATILITY    STRUCTURE
LIQUIDITY    EVENT         EXECUTION     CROSS_ASSET
```

`7 bullish indicators vs 3 bearish = BUY` is forbidden. It destroys the information that makes confluence
useful — *which kind* of evidence agrees — and it double-counts colinear features by construction.

The strategy decides which functional axes matter to it. The engine only reports state per axis. This is also
what lets VAN speak usefully: *"H1 trend remains bullish and ADX shows persistence, but M15 momentum has
weakened and price is approaching H4 resistance. The setup is still eligible; confirmation quality is lower."*

### MS-7 — Controlled feature expansion, first tranche

```text
ADX / DMI
Donchian  OR  Keltner
MACD      OR  PPO
multi-horizon ROC
```

**Do not add both members of a highly redundant pair without evidence.** MACD and PPO are the same construction
under different normalisation; Donchian and Keltner both answer "where is price within its recent envelope".
Each candidate passes MS-5 before admission, and a second member of a pair must show incremental value *over
the first*, not over the baseline without either.

### MS-8 — Venue-gated volume intelligence

```text
ZSE / VFEX   real traded volume exists and is meaningful
             → OBV, MFI, money-flow and volume-profile features permitted
               where provenance is sound

FX spot      no consolidated traded volume exists
             → Bar.ticks and broker volume are ACTIVITY PROXIES,
               labelled as such in source_semantics
             → no feature may present them as traded volume
```

The polarity is the reverse of the usual assumption: the volume family is more defensible on the illiquid
end-of-day equity book than on liquid FX.

### MS-9 (F9) — Hard exclusion: microstructure pseudo-intelligence

`FeatureVector` (`trading/vati/intelligence/features.py`) supplies `close`, `ema_fast`, `ema_slow`, `atr`,
`rsi`, `realised_vol`, `vol_percentile`, `spread_percentile`, `trend_slope`, `range_compression`, `swing_high`,
`swing_low`, `complete`, and already carries `feature_version: "features/1.0.0"` — partial provenance exists.

Around it sits intelligence that is worth more than most chart indicators: CUSUM change-point detection, trend
and volatility regimes, transition phase, session classification, event windows, market integrity, ZiG currency
regime, execution-cost state and broker-liquidity state. Indicators are treated as evidence, never as
buy/sell commands. That framing should survive any expansion unchanged.

Two families from a conventional technical-analysis vocabulary do **not** transfer to VAN's venues:

**Volume.** `Bar.volume` is populated from Dukascopy ask/bid volume and from tick aggregation
(`trading/vati/market_data/bars.py:63`). FX spot has no consolidated traded volume — there is no central
exchange. OBV, MFI, Chaikin money flow and volume profile would run on a broker-specific liquidity proxy that
differs between Dukascopy, MT5 and cTrader for the same instrument at the same instant. `Bar.ticks` is honest
about what it measures; `Bar.volume` invites a false reading.

The polarity is the reverse of the usual assumption: **ZSE has real traded volume and FX does not**, so the
volume family is more defensible on the illiquid end-of-day equity book than on liquid FX.

**Microstructure.** There is no depth or order-book data anywhere in `trading/vati/`, and
`trading/vati/risk/mandate.py:60` already lists in `HARD_FORBIDDEN_BEHAVIOURS`:

```python
"single_dom_as_total_fx_liquidity",
"macro_causality_on_synthetics",
```

Order-flow imbalance, market depth, liquidity sweeps and single-broker fair-value-gap structures are therefore
not a gap to fill — the mandate has already named the exact fallacy they would invite. Admitting them requires
a mandate amendment plus a genuine multi-venue data source. `macro_causality_on_synthetics` similarly
constrains cross-asset confirmation and relative strength across the Deriv synthetic universe.

Depth and order-flow features remain **outside scope** until there is genuine multi-venue data *and* an
explicit mandate amendment. Neither condition holds today, and the prohibition is deliberate rather than an
oversight.

---

## 5. Further enhancements

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

## 6. Target architecture

```text
      MARKET DATA  +  EVENTS  +  PRIMARY-SOURCE BROWSER RESEARCH
                            ▼
                  FEATURE INTELLIGENCE                       (§4 MS)
     multi-timeframe · structure · trend · momentum · volatility
        volume (venue-gated MS-8) · liquidity · cross-asset
                            ▼
                      REGIME ENGINE
                            ▼
                  STRATEGY COVERAGE MAP                       (P8)
                            ▼
                    STRATEGY CAPSULES
                            ▼
                   META / COST FILTERS
                            ▼
                  CANDIDATE OPPORTUNITIES
                            ▼
            PORTFOLIO OPPORTUNITY ALLOCATOR                   (P7)
     edge-floor · tail-risk · overlap · execution · capital-efficiency
                            ▼
                       TradeIntent
                            ▼
           ═══ DETERMINISTIC RISK AUTHORITY ═══
                            ▼
                 EXECUTION POLICY ENGINE                      (P5)
                            ▼
                         BROKER
                            ▼
          TCA  +  OUTCOME  +  MFE/MAE  +  PATH DATA
                            ▼
        EXPERIENCE  /  FEATURE-DRIFT LEARNING                 (P9)
              ↙                            ↘
     FAST SAFETY LOOP                SLOW UPSIDE LOOP
     reduce · demote                 validation certificate   (P3)
     suspend · reject                capital proposal         (P1, P10)
                                              ▼
                                         OWNER A4
                                              ▼
                                   new signed mandate
```

The allocator is the structural addition. Everything left of `TradeIntent` may now compare opportunities;
everything right of it remains exactly as deterministic as it is today.

---

## 7. Priority order

Three cheap integrity fixes come before anything certifies anything. A validation certificate must not certify
a strategy against an ambiguous market-state representation or a silently missing feature dependency — so the
prerequisites are numbered 0A–0C rather than folded into the main sequence.

| # | Work | Changes live risk? | New owner authority? |
|---|---|---|---|
| **0A** | **F3** — correct the DSR gate to `dsr_probability >= 0.95` in Rev 2 §551 and Rev 3 D7 | no | no |
| **0B** | **MS-2** — enforce `required_features`, fail closed | no | no |
| **0C** | **MS-1** — `timeframe` on `FeatureVector`/`MarketState`, in canonical serialization and `state_hash` | no | no |
| 1 | **MS-3** `MultiTimeframeMarketState` over the existing lake, with the provenanced capsule migration | no | capsule rehash, provenanced |
| 2 | **P3** `StrategyValidationCertificate` wired into `CapsuleRegistry.promote` (closes F3's discard, F4's opaque evidence) | no | no |
| 3 | **MS-4/MS-5** venue-aware registry + `FeatureValidationCertificate`, then **MS-7** first tranche | no | no |
| 4 | **MS-6** functional confluence engine | no | no |
| 5 | **P7** `OpportunityPortfolioAllocator` (+ the F10 runtime decision) | selection only, never size | no |
| 6 | **P1** per-strategy capital budgets + `CapitalBudgetProposal` | **yes — raises ceilings** | **yes, A4** |
| 7 | **P2** `PortfolioDependencyEngine`, populating the dead `correlation_multiplier` | reduce-only | no |
| 8 | **P5** `ExecutionPolicyEngine` and **P4** exit-policy research | reduce-only / research | template approval |
| 9 | **MS-8** venue-gated volume (ZSE first); **P9** feature drift; **P8** strategy coverage | no | no |
| 10 | Continuous volatility targeting; portfolio Expected Shortfall | reduce-only | no |
| 11 | **P10** / §5 uncertainty-aware capital promotion; browser-powered evidence | proposal / T2 only | per-capability |
| — | **MS-9** microstructure | out of scope | mandate amendment + multi-venue data |

0A is first because the `> 0` wording can currently make an invalid strategy look validated — it is a live
gate that certifies noise, and every certificate built on it inherits the defect.

0B and 0C are each a few hours of work and neither adds a feature. Both become materially harder after the
thing they protect exists: retrofitting `timeframe` once two timeframes coexist leaves every state recorded in
between unattributable.

Everything except item 6 changes no ceiling. **Item 6 is the only one requiring a new owner decision artifact,**
because it is the only one that can raise one.

---

## 8. What must not change

- `clamp_multiplier` stays `[0,1]`. No runtime multiplier may exceed 1, ever.
- Automatic learning reduces, demotes, suspends, tightens or proposes. It never raises a ceiling.
- The Risk Authority stays deterministic. No model output sizes a trade directly.
- `MetaLabeler` stays `RULES_V0_UNCALIBRATED` until a Brier/ECE gate exists and passes.
- Browser and LLM evidence never generate orders, never promote a capsule, never bypass the Risk Authority.
- VATI remains the single execution route. Nothing here creates a second sender.
- Indicators describe market state. They are evidence, never order authority. No feature, confluence score or
  timeframe agreement may size, promote or execute anything.
- A capsule that cannot obtain a feature it declared abstains with a reason code. It never trades on the
  remainder.
- Confluence is reported by function. A bullish-versus-bearish tally is forbidden.
- A capsule hash change carries a migration record. An unexplained rehash is indistinguishable from
  `silent_strategy_mutation`, which is hard-forbidden.
- The Portfolio Opportunity Allocator selects among candidates. It may reject or defer; it may never increase
  a candidate's risk, and it sits before the Risk Authority, never in place of it.
- Volume and microstructure features stay venue-gated. `single_dom_as_total_fx_liquidity` and
  `macro_causality_on_synthetics` remain hard-forbidden behaviours.
- Feature-drift and coverage-map findings produce research candidates only. Neither mutates a live capsule.
