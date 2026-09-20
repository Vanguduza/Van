# VAN Deterministic Trading System Enhancement Module — Rev 1

**Status:** IMPLEMENTATION SPECIFICATION, pending owner adoption. Not yet an engineering authority.
On adoption it **extends** `docs/VAN_TRADING_SYSTEM_BLUEPRINT_REV4_CONSOLIDATED.md` (Rev 4) and
`docs/VAN_TRADING_PRODUCTION_DEPLOYMENT_BLUEPRINT_REV5.md` (Rev 5). It supersedes neither. Where this document
and Rev 4/Rev 5 disagree on an existing contract, Rev 4/Rev 5 win until the owner signs an adoption artifact.
**Rationale and evidence:** `docs/VAN_TRADING_PROFITABILITY_ENHANCEMENT_PROPOSAL_REV_1.md` (Rev 1.2). That
document is non-authoritative reasoning; this one is the specification derived from it. They are deliberately
kept separate and are not to be merged.
**Repository baseline inspected:** `main` @ `66e4e42` (`0.5.0-dev`, `SCHEMA_VERSION = 26`).
**Authorities not amended by this document:** `PROJECT_CANONICAL_STATE.json`, `docs/SECURITY_POLICY.md`,
`docs/PROJECT_TRUTH_PROTOCOL.md`, `trading/architecture/stack_lock.json`, `config/browser/*`.
**Date:** 2026-09-19.

---

## Part A — What this module changes, in one page

VATI today is asymmetric everywhere: `clamp_multiplier` bounds every intelligence multiplier to `[0,1]`,
capsule health demotes but never promotes, five of six counterfactual variants are conservative, and one
`max_risk_per_trade` covers every capsule. That is correct as a **live actuation** invariant and stays. Applied
to the whole system it also means VATI cannot discover that it is under-allocated to a durable edge.

This module separates the two loops that are currently fused, and closes ten verified repository findings.

```text
FAST SAFETY LOOP                         SLOW UPSIDE LOOP
trade evidence                           validated evidence
   ↓                                        ↓
decay · cost · regime · correlation      DSR + PBO + walk-forward + live/shadow
   ↓                                        ↓
AUTO REDUCE / DEMOTE / SUSPEND           capital-budget proposal
   ↓                                        ↓
immediate, no approval                   OWNER APPROVAL (A4)
                                            ↓
                                         new signed mandate version
```

**The invariant this module exists to preserve:** intelligence may discover and propose more upside; only
deterministic authority plus owner-approved ceilings may actuate it.

---

## Part B — Execution contract

A component of this module is complete only when it passes all of these distinct states. No implementation
agent may collapse them into `DONE`.

1. **DESIGNED** — contract and authority boundary explicit.
2. **BUILT** — implementation exists.
3. **WIRED** — a real production path calls it.
4. **REACHABLE** — the intended surface can invoke it.
5. **LIVE** — runs against the real runtime, not a fixture.
6. **VERIFIED** — the requested effect is deterministically confirmed.
7. **OBSERVED** — ledger evidence proves the real execution path.
8. **RECOVERABLE** — restart, stale lease and reconciliation paths work.
9. **CERTIFIED** — live venue and owner-signed gates are green.

Every closure group runs the PR #48 machinery before and after:

```text
python tools/ci/maturity_gate.py
python tools/ci/authority_map.py
python tools/ci/ledger_reconcile.py
python tools/audit/kotlin_reachability.py
python tools/audit/mutation_suite.py        # behaviour-changing groups
```

New components appear in `evidence/van-system-audit/component_ledger.json` with honest maturity.
`INTEGRATED_AND_EVIDENCED` requires producer, consumer, production caller, tests and runtime evidence, all
non-null — the ledger's own rule, unchanged.

---

## Part C — Verified findings this module closes

Each was confirmed against `main` @ `66e4e42`. Full evidence is in the proposal §2 and §4.

| ID | Finding | Closed by |
|---|---|---|
| F1 | `TradingMandate` has one `max_risk_per_trade`; no per-strategy allocation | Part H |
| F2 | `TradeIntent.correlation_multiplier` is declared, serialised and consumed, but **never populated** — permanently `1` | Part G |
| F3 | `deflated_sharpe`/`pbo_cscv` referenced only by tests; docs carry a `> 0` gate against a function returning `_norm_cdf(z)`, whose `> 0` gate admits a DSR of 7e-6 (essentially certain selection bias) and even a negative observed Sharpe; see proposal F3 for the measured cases | Part D |
| F4 | `CapsuleRegistry.promote` requires a signature and non-empty `evidence_refs`, but `evidence_refs` is `list[str]` and unvalidated | Part E |
| F5 | Exit policy fixed at `ProtectionManager.register`; `missed.py` computes MFE/MAE and discards them | Part J |
| F6 | TCA *does* drive behaviour via `LearningBroker` → `broker_liquidity` → `MetaLabeler`, reduce-only. Missing dimension is order-type/venue **choice** | Part J |
| F7 | `MarketState` is single-timeframe and records no `timeframe`; `state_hash` cannot separate an M5 from an H1 state | Part D |
| F8 | Every capsule declares `required_features`; nothing under `trading/vati/` reads it | Part D |
| F9 | `Bar.volume` is a broker proxy on FX; microstructure already hard-forbidden by `single_dom_as_total_fx_liquidity` | Part F |
| F10 | `cycle.py` decides one instrument, `process_lock` permits one session per alias, yet heat is portfolio-wide — allocation is **arrival-ordered** | Part I |

---

## Part D — Integrity prerequisites (Phase 0)

Three fixes that change no live risk, add no feature, and must land before anything certifies anything. A
validation certificate must not certify a strategy against an ambiguous market state or a silently missing
dependency.

### D1 — Correct the DSR contract (closes F3, first half)

```text
canonical field:  dsr_probability
gate:             dsr_probability >= 0.95
```

`> 0` rejects only the extremes, where `math.erf` saturates and the CDF underflows to exactly `0.0`. It admits
a +0.10 Sharpe over 60 observations selected from 500 trials (DSR 7e-6) and a negative observed Sharpe.

Amend `docs/VAN_ADAPTIVE_TRADING_INTELLIGENCE_TECHNICAL_BLUEPRINT_REV2.md:551` and
`docs/VAN_ADAPTIVE_TRADING_INTELLIGENCE_TECHNICAL_BLUEPRINT_REV3.md:40` from `deflated Sharpe > 0`.
`trading/vati/learning/curriculum.py:21` already states `DSR > 0.95` and is the correct precedent.

**Test:** a plausible overfit — small positive Sharpe, short sample, many trials — must fail the gate. Under the `> 0` wording it passes.

### D2 — Enforce `required_features` (closes F8)

Capsule admission and per-pass evaluation fail closed when a declared feature is:

```text
missing from the registry          unavailable for this venue class
stale beyond its freshness contract   incompatible with the capsule's timeframe
None when the capsule declares it required
```

The capsule **abstains with a reason code**. It never trades on the remaining features.

### D3 — Add `timeframe` to the market-state record (closes F7)

`timeframe` becomes a field on `FeatureVector` and `MarketState`, included in canonical serialization and in
`state_hash`.

This is an audit defect, not a feature. `missed.py`'s `ex_ante_snapshot_hash` and the ledger's decision record
currently cannot say which timeframe VATI looked at. Retrofitting after two timeframes coexist leaves every
state recorded in between unattributable.

**Phase 0 exit gate:** D1–D3 merged, `maturity_gate` and `ledger_reconcile` green, and a test proving a
negative-Sharpe strategy fails certification.

---

## Part E — Certification plane (Phase 2)

### E1 — `StrategyValidationCertificate` (closes F3 second half, F4)

One sealed artifact, not scattered `deflated_sharpe()` calls:

```text
strategy_id · strategy_version
data_manifest_hash · feature_revision · cost_model_revision
n_trials · trade_count · walk_forward_windows
expectancy_R · profit_factor · max_drawdown · sharpe
dsr_probability · pbo · cpcv_configuration
cost_stress_2x · latency_slippage_stress
parameter_perturbation_stability · regime_breakdown · leakage_switch_result
validation_hash
```

`CapsuleRegistry.promote` requires the certificate in place of an opaque string:

```text
RESEARCH     → BACKTEST        ordinary research evidence
BACKTEST     → VALIDATION      minimum data/trade gates
VALIDATION   → DEMO            dsr_probability >= 0.95 · pbo <= 0.10
                               walk-forward green · leakage green · cost stress green
SHADOW       → LIMITED_LIVE    owner signature + certificate + shadow evidence
LIMITED_LIVE → CERTIFIED_LIVE  owner signature + real execution and cost evidence
```

The existing per-target-state signature scoping (`capsule.py:112-125`) is unchanged and remains correct.

### E2 — `FeatureValidationCertificate`

A feature proves **incremental** value against a named baseline, not standalone correlation with returns.
Standalone correlation is how a registry acquires five colinear trend measures and manufactures confluence.

```text
feature_id · feature_version · baseline_feature_set
incremental_dsr · incremental_pbo · walk_forward_delta
regime_stability · instrument_stability
redundancy_metrics          correlation, mutual information vs baseline
leakage_result · validation_hash
```

Only a validated feature may enter a production capsule's `required_features`. Same machinery as E1,
deliberately not a second evidence standard.

---

## Part F — Market-state and feature intelligence (Phase 1, 3)

### F1 — `MultiTimeframeMarketState`

Reuse the lake's existing `TIMEFRAMES_MS = {M1, M5, M15, H1, H4, D1}`. **Do not duplicate bar storage.** The
storage tier is already multi-timeframe with slice manifests; only the state tier is single-sequence.

Per-capsule timeframe contract:

```text
structural_timeframe:  H4      regime_timeframe:     H1
setup_timeframe:       M15     execution_timeframe:  M5
```

#### Capsule schema migration

Adding the contract changes `capsule_hash`, which covers the whole document. `silent_strategy_mutation` is a
hard-forbidden behaviour and an unexplained rehash is indistinguishable from one, so each migrated capsule
records:

```text
old_capsule_hash · new_capsule_hash
migration_reason        = MTF_SCHEMA_ADOPTION
strategy_logic_changed  = false
owner_authority_changed = false
migrated_at_unix
```

`strategy_logic_changed = false` must be **mechanically verifiable** — entry, stop, target and eligibility
logic references byte-identical to the parent. If they are not, it is a strategy revision and takes the normal
owner-signed promotion path.

### F2 — Venue-aware Feature Registry

```text
feature_id · feature_version
venue_classes          FX_SPOT · CFD · SYNTHETIC · ZSE_EQUITY · VFEX
required_inputs        ohlc · ticks · volume · spread · depth
timeframe_constraints  minimum bar count, permitted timeframes
source_semantics       e.g. "tick count, not traded volume"
provenance_version
```

`source_semantics` is the load-bearing field. It is what stops `volume` silently meaning centralized traded
volume on an FX pair where no such quantity exists.

Per-value provenance extends the existing `feature_version`:

```text
feature_id · feature_version · timeframe · lookback
value · normalised_value · percentile · regime · as_of · data_quality
```

### F3 — Functional confluence

Evidence aggregates **by function**: `TREND · MOMENTUM · VOLATILITY · STRUCTURE · LIQUIDITY · EVENT ·
EXECUTION · CROSS_ASSET`.

`7 bullish vs 3 bearish = BUY` is forbidden. It discards which *kind* of evidence agrees and double-counts
colinear features by construction. The engine reports state per axis; the strategy decides which axes matter.

### F4 — First feature tranche

```text
ADX / DMI          Donchian OR Keltner
MACD OR PPO        multi-horizon ROC
```

A second member of a redundant pair must show incremental value **over the first**, not over a baseline
containing neither.

### F5 — Venue-gated volume, and the microstructure exclusion (closes F9)

```text
ZSE / VFEX   real traded volume exists → OBV, MFI, money-flow, volume profile permitted
FX spot      no consolidated traded volume → Bar.ticks and broker volume are ACTIVITY PROXIES,
             labelled as such in source_semantics; no feature presents them as traded volume
```

Depth, order-flow imbalance, liquidity sweeps and single-broker fair-value-gap structures are **out of scope**.
`single_dom_as_total_fx_liquidity` and `macro_causality_on_synthetics` remain hard-forbidden. Admission
requires genuine multi-venue data *and* a mandate amendment; neither condition holds.

---

## Part G — Portfolio dependency (Phase 6)

Two correlation systems, for two different jobs. They are not interchangeable.

```text
MARKET EXPOSURE CORRELATION          STRATEGY RETURN CORRELATION
instrument returns / risk factors    realised + shadow R-multiples
→ controls open-book concentration   → controls slow capital allocation (Part H)
→ live, reduce-only                  → proposal-time only
```

`PortfolioDependencyEngine` computes a shrinkage/stability-aware covariance over instrument returns with
explicit factor tags — `USD · EUR · GBP · JPY · gold · rates · risk-on/off · ZiG · ZSE sector · VFEX/USD` —
and sizes the **increment**:

```text
risk_before      = portfolio_tail_risk(existing_book)
risk_after       = portfolio_tail_risk(existing_book + candidate)
incremental_risk = risk_after - risk_before   →   correlation_multiplier ∈ [0,1]
```

This finally populates the dead field (closes F2). A stressed correlation matrix runs alongside the normal one:
correlations converge precisely when a portfolio is under stress, so the joint tail is the measurement, not the
sum of independent position risks.

Three complementary views result — stop-risk heat, currency-leg exposure, portfolio dependency — and none
replaces another.

---

## Part H — Capital promotion plane (Phase 5)

### H1 — Per-strategy budgets

```text
strategy_risk_budgets:
    FX-TREND-PULLBACK-01:   0.0075
    FX-LONDON-BREAKOUT-01:  0.0030
    GOLD-TREND-POSITION-01: 0.0060

0 < strategy_risk_budget <= mandate.max_risk_per_trade <= PlatformCeilings.max_risk_per_trade
```

```text
base_risk     = min(owner_strategy_budget, capsule_ceiling, mandate_ceiling, platform_ceiling)
approved_risk = base_risk × regime × volatility × liquidity × event × confidence
                          × correlation × drawdown
```

Every runtime multiplier stays `<= 1`. `clamp_multiplier` is **unchanged**.

### H2 — `CapitalBudgetProposal`

The only mechanism that raises a ceiling, and it is not automatic:

```text
strategy_id · current_budget · proposed_budget
certified_expectancy · lower_confidence_expectancy   ← edge_floor, not mean R
live_sample · shadow_sample
dsr_probability · pbo · cost_stress_result
regime_stability · tail_risk · max_drawdown
capital_efficiency          expected_R_per_risk_day, occupancy, financing
evidence_refs
```

Only an owner-signed new mandate version changes the number. **This is the sole item in this module requiring
a new owner decision artifact.**

`edge_floor` is a lower confidence bound, not a mean. `+0.34R [-0.02, +0.70]` and `+0.34R [+0.22, +0.46]` are
not the same proposition.

---

## Part I — `AccountDecisionCoordinator` (Phase 4) — closes F10

### I1 — Why not a wider `DecisionCycle`

`DecisionCycle` carries too much symbol-specific state to become an N-symbol state machine: `RegimeEngine`,
symbol contract, `ProtectionManager` bookkeeping, TCA learning, `_entries` tracking and symbol-scoped
idempotency seeds (`f"{account_alias}:{symbol}:{as_of_ms}"`). Widening it multiplies each into a collection and
puts the shared heat budget inside a loop that also owns per-symbol execution state.

### I2 — Canonical architecture

One authoritative process per account alias, preserving the existing `process_lock` guarantee:

```text
AccountDecisionCoordinator
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

`InstrumentEvaluator` keeps everything `DecisionCycle` owns per symbol and stops one step earlier:

```text
N InstrumentEvaluators → CandidatePool → AccountDecisionCoordinator
    → OpportunityPortfolioAllocator → TradeIntent → Risk Authority
```

**`CandidateOpportunity` is deliberately weaker than `TradeIntent`** — no approved size, no protection control,
no path to `ExecutionRouter`. Only the coordinator, post-allocation, mints a `TradeIntent`. The router's input
contract is unchanged.

### I3 — Allocator ranking

Ranks on `edge_floor`, incremental Expected Shortfall (Part G), strategy overlap, execution cost and fill
probability (Part J), regime stability, and capital efficiency. **It selects which candidates proceed. It never
enlarges any candidate's risk.**

### I4 — Shared-heat procedure

The allocator must not approve several candidates against one stale snapshot, and must not become a shadow
Risk Authority by pre-deciding what will fit:

```text
rank fresh candidates → candidate #1 → fresh portfolio snapshot → Risk Authority
    → execute / reject → refresh portfolio truth → candidate #2
```

Ranking is computed once per pass; **admission is re-evaluated per candidate against live state.** A candidate
that ranked second may be rejected outright once the first one's risk is in the book — the correct outcome, and
the Risk Authority's decision, not the allocator's.

### I5 — `AllocationEpisode`

Selection policy is a hypothesis and must be falsifiable:

```text
AllocationEpisode {
    selected_candidate · rejected_candidates
    portfolio_snapshot_hash · ranking_features · selection_reason
    realised_selected_outcome
    counterfactual_rejected_outcomes
}
```

Rejected candidates are scored on the same bounded, hindsight-guarded basis as `missed.py` — over the setup's
own horizon window, from the frozen ex-ante snapshot — and carry `SIMULATED` weight. This lets VAN discover
that it repeatedly took +0.3R setups while rejecting +1.8R alternatives **without changing the allocator live**.
A new allocation policy is a research candidate: offline walk-forward, DSR and PBO before it replaces the
incumbent.

---

## Part J — Execution and exit intelligence (Phase 7)

### J1 — `ExecutionPolicyEngine` (extends F6, does not rebuild it)

The existing path stays: `ExecutionReceipt → compute_tca() → LearningBroker.observe() →
BrokerExecutionProfile → broker_liquidity → MetaLabeler`, reduce-only, with `BACKTEST/REPLAY/COUNTERFACTUAL`
facts at zero weight.

Added dimension — learn per broker × symbol × session × volatility bucket × event proximity × direction ×
order type:

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

No model emits an arbitrary order. It selects a template under deterministic hard limits.

### J2 — Exit-policy research (closes F5)

Deriving parameters from "MAE of winners" introduces selection bias — conditioning on outcome selects paths
that happened not to stop out. Instead preserve the full post-entry path and evaluate a **fixed registered
family** offline:

```text
original fixed target · time exit · exit 1/N bars later
scale 50% at 1R + trail · scale 33/33/34
ATR trail · structure trail · volatility-adjusted trail
break-even at 0.75R / 1R / 1.5R · no break-even
fixed 2R / 3R / 4R · regime-conditioned target · LET_RUN until invalidation
```

Research variants, never live mutations. Each passes the same walk-forward, CPCV/PBO, DSR, cost-stress and
regime splits as any capsule revision.

Store by strategy × regime × session × volatility regime × event state: MFE and MAE distributions,
time-to-MFE, time-to-MAE, time-to-target, post-exit continuation, give-back from MFE.

Extend `CounterfactualVariant` with expansive members — `EXIT_ONE_BAR_LATER`, `SCALE_OUT_HALF_AT_1R`,
`TRAIL_INSTEAD_OF_FIXED_TARGET`. Output is already `SIMULATED`, weight 0.2, capsule-level only, so widening the
hypothesis space carries no actuation risk.

---

## Part K — Research and drift (Phase 8)

### K1 — Feature and edge drift monitor

`StrategyHealthTracker` measures realised performance, process, cost ratio and regime fit — all at capsule
level. Underneath it, track each feature's incremental value by strategy × instrument × timeframe × regime.
Capsule health is a *lagging* indicator of feature decay; this is a leading one. Lives in VTIL/shadow research;
proposes, never mutates.

### K2 — Strategy coverage map

`StrategyCoverageMap` across asset × horizon × regime × style.

```text
covered:    trend pullback · session breakout · event drift · gold positioning
            ZSE value rotation · ZSE liquidity provision
uncovered:  range / mean-reversion · volatility expansion and contraction
            relative-value / pairs · cross-sectional momentum
            carry / roll · defensive regime
```

`FX-TREND-PULLBACK-01` declares `eligible_regimes: [BULL, BEAR]`, `forbidden_regimes: [TRANSITION, EXTREME]`.
**RANGE is uncovered across the FX book** — when the regime engine reports RANGE, no FX capsule is eligible.
That is measurable idle capital and likely the highest-value entry on the uncovered list.

Missing coverage produces research candidates only.

### K3 — Browser-sourced trading evidence

```text
primary source → Stagehand retrieval → Browser Harness provenance
  → structured extractor → TradingEvidenceArtifact → VTIL admission
  → Hermes assessment → T2Assessment (TTL + evidence refs) → MetaLabeler
```

Boundary preserved exactly: such evidence **may** explain, classify, flag contradiction, reduce confidence,
trigger research or propose a strategy revision; it **may not** set lot size, widen a stop, create a live
strategy, promote a capsule, bypass the Risk Authority or send an order.

Depends on the Remote Browser programme and on `VAN-ADOPT-STAGEHAND-001.yaml` reaching owner approval.

---

## Part L — Target architecture

```text
      MARKET DATA  +  EVENTS  +  PRIMARY-SOURCE BROWSER RESEARCH
                            ▼
                  FEATURE INTELLIGENCE                    (Part F)
     multi-timeframe · structure · trend · momentum · volatility
        volume (venue-gated) · liquidity · cross-asset
                            ▼
                      REGIME ENGINE
                            ▼
                  STRATEGY COVERAGE MAP                   (Part K)
                            ▼
                    STRATEGY CAPSULES
                            ▼
                   META / COST FILTERS
                            ▼
              N × InstrumentEvaluator                     (Part I)
                            ▼
                     CandidatePool
                            ▼
              AccountDecisionCoordinator
                            ▼
            PORTFOLIO OPPORTUNITY ALLOCATOR
     edge-floor · tail-risk · overlap · execution · capital-efficiency
                            ▼
                       TradeIntent
                            ▼
           ═══ DETERMINISTIC RISK AUTHORITY ═══      (sequential, Part I4)
                            ▼
                 EXECUTION POLICY ENGINE                  (Part J)
                            ▼
                         BROKER
                            ▼
     TCA + OUTCOME + MFE/MAE + PATH + AllocationEpisode
                            ▼
        EXPERIENCE  /  FEATURE-DRIFT LEARNING             (Part K)
              ↙                            ↘
     FAST SAFETY LOOP                SLOW UPSIDE LOOP
     reduce · demote                 validation certificate  (Part E)
     suspend · reject                capital proposal        (Part H)
                                              ▼
                                         OWNER A4
                                              ▼
                                   new signed mandate
```

Everything left of `TradeIntent` may now compare opportunities. Everything right of it remains exactly as
deterministic as it is today.

---

## Part M — Phase order and exit gates

| Phase | Work | Exit gate |
|---|---|---|
| **0** | D1 DSR contract · D2 `required_features` · D3 `timeframe` | negative-Sharpe strategy fails certification; a capsule missing a declared feature abstains; `state_hash` separates M5 from H1 |
| **1** | F1 `MultiTimeframeMarketState` + provenanced capsule migration | a capsule reads four timeframes; every migrated capsule carries a verifiable `strategy_logic_changed = false` |
| **2** | E1 `StrategyValidationCertificate` into `promote` | no promotion to `DEMO`+ without a certificate; F3/F4 closed |
| **3** | F2 registry · E2 `FeatureValidationCertificate` · F4 tranche · F3 confluence | a redundant second-of-pair is rejected on incremental evidence |
| **4** | I `AccountDecisionCoordinator` + allocator + `AllocationEpisode` | two simultaneous candidates on one alias are ranked, admitted sequentially against refreshed state, and both outcomes recorded |
| **5** | H per-strategy budgets + `CapitalBudgetProposal` | a budget rises only via a new signed mandate; **owner A4 required** |
| **6** | G `PortfolioDependencyEngine` | `correlation_multiplier` is populated and reduce-only; stressed matrix exercised |
| **7** | J1 execution policy · J2 exit research | template selection is deterministic and bounded; expansive counterfactuals produce candidates |
| **8** | K1 drift · K2 coverage · F5 ZSE volume | a decayed feature is flagged before capsule health degrades |
| **9** | K3 browser evidence · uncertainty-aware promotion | T2 evidence reaches `MetaLabeler` and provably cannot size or promote |
| **10** | Closure | matrix, external gates and acceptance ledger updated; no hidden `BUILT_UNWIRED` |

Phases 0–4 and 6–9 change no ceiling. **Phase 5 is the only one requiring a new owner decision artifact.**

---

## Part N — Test and red-team requirements

### N1 — Contract tests

```text
negative-Sharpe strategy fails dsr_probability >= 0.95
promotion without a certificate is refused
certificate with a stale data_manifest_hash is refused
capsule declaring an absent feature abstains with a reason code
capsule declaring a venue-incompatible feature abstains
state_hash differs for M5 and H1 states of the same symbol/instant
capsule migration with changed logic references is refused as MTF_SCHEMA_ADOPTION
second-of-redundant-pair rejected on incremental evidence
CandidateOpportunity cannot reach ExecutionRouter
allocator cannot raise a candidate's requested risk
two candidates cannot both be approved against one portfolio snapshot
correlation_multiplier > 1 is clamped to 1
strategy_risk_budget > mandate.max_risk_per_trade is refused
budget increase without an owner signature is refused
```

### N2 — Red-team matrix

```text
1  stale portfolio snapshot reused across candidates
2  allocator ranks on a rejected candidate's post-hoc outcome (hindsight leak)
3  AllocationEpisode counterfactual scored beyond its horizon window
4  feature certificate reused against a different baseline_feature_set
5  capsule migration used to smuggle a logic change
6  required_features satisfied by a None value
7  timeframe omitted from state_hash
8  FX volume feature admitted without source_semantics
9  depth-derived feature admitted without a mandate amendment
10 execution template chosen outside the approved set
11 exit-policy variant promoted without walk-forward
12 budget proposal built on mean R rather than edge_floor
13 drift monitor mutating a live capsule
14 browser evidence raising an action class
15 two coordinator processes on one account alias
16 coordinator crash mid-sequence leaves heat double-counted
17 InstrumentEvaluator emitting a TradeIntent directly
```

Every finding is `PASS · FAIL · BLOCKED_EXTERNAL · NOT_APPLICABLE_WITH_REASON`. Never `assumed`.

---

## Part O — Definition of complete

```text
AUTHORITY
  one Risk Authority · one sizer · one execution route
  allocator selects only · owner signature for every ceiling change

INTEGRITY
  dsr_probability gate correct and enforced
  required_features enforced fail-closed
  timeframe in canonical state and hash
  every capsule migration provenanced and verifiable

INTELLIGENCE
  multi-timeframe state live · feature registry venue-aware
  every production feature certified · confluence by function
  correlation_multiplier populated and reduce-only

ALLOCATION
  candidates ranked · heat consumed sequentially against refreshed truth
  AllocationEpisode recorded for selected and rejected

EVIDENCE
  certificates sealed · counterfactuals hindsight-guarded
  component ledger claims no stronger than its evidence
  maturity_gate · authority_map · ledger_reconcile · mutation_suite green
```

---

## Part P — What must not change

- `clamp_multiplier` stays `[0,1]`. No runtime multiplier may exceed 1, ever.
- Automatic learning reduces, demotes, suspends, tightens or **proposes**. It never raises a ceiling.
- The Risk Authority stays deterministic and is the only sizer.
- `CandidateOpportunity` never carries an approved size and never reaches the router.
- The allocator sits **before** the Risk Authority, never in place of it.
- `MetaLabeler` stays `RULES_V0_UNCALIBRATED` until a Brier/ECE gate exists and passes.
- Indicators are evidence, never order authority. No feature, confluence state or timeframe agreement sizes,
  promotes or executes anything.
- A capsule that cannot obtain a declared feature abstains. It never trades on the remainder.
- Confluence is reported by function. A bullish-versus-bearish tally is forbidden.
- An unexplained `capsule_hash` change is indistinguishable from `silent_strategy_mutation` and is refused.
- `single_dom_as_total_fx_liquidity` and `macro_causality_on_synthetics` remain hard-forbidden.
- Browser and LLM evidence never generate orders, promote capsules or bypass the Risk Authority.
- VATI remains the single execution route. Nothing here creates a second sender.
