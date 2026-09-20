# VAN Trading Intelligence & Profitability Improvement Blueprint — Rev 1.1

**Status:** Production implementation blueprint; derived until explicitly admitted as an authority document.  
**Rev 1.1 corrections:** closes B1 (store placement), B2 (lease reachability), B3 (deterministic Allocator V0),
S1 (event-kind discipline), S2 (target precedence), S3 (single threshold source), S4 (per-phase owner adoption)
from `docs/VAN_TRADING_INTELLIGENCE_AND_PROFITABILITY_IMPROVEMENT_BLUEPRINT_REV_1_EXPERT_REVIEW.md`.
Owner-decision points that blocked implementation are resolved with the recommended option and marked
**[OWNER-DEFAULT]**; each may be overridden by an owner decision artifact without re-architecting.  
**Repository:** `Vanguduza/Van`  
**Repository baseline verified:** `main @ 66e4e42a9e8994a0f3129fbda4c794b68b353120`  
**VAN version:** `0.5.0-dev`  
**Database schema baseline:** `26`  
**Trading stack-lock revision observed:** `5.2.0`  
**Source proposal:** `docs/VAN_TRADING_PROFITABILITY_ENHANCEMENT_PROPOSAL_REV_1.md` Rev 1.2  
**Existing active trading authorities:** `VAN_TRADING_SYSTEM_BLUEPRINT_REV4_CONSOLIDATED.md`, `VAN_TRADING_PRODUCTION_DEPLOYMENT_BLUEPRINT_REV5.md`, `SECURITY_POLICY.md`, `PROJECT_TRUTH_PROTOCOL.md`, `trading/architecture/stack_lock.json`.

---

# 0. Executive contract

This blueprint converts the repository-grounded profitability proposal into a closure-grade implementation specification. It is deliberately written to prevent the defect shape exposed during the PR #48 readiness pass: code that exists and tests locally, but has no production producer, no production consumer, no reachable caller, no owner-visible effect, or no independent evidence.

VAN is not being turned into an unconstrained AI trader. The target is:

```text
multi-timeframe market intelligence
+ semantically validated features
+ semantically validated strategies
+ account-scoped multi-symbol opportunity competition
+ portfolio dependency / tail-risk intelligence
+ execution-policy intelligence
+ exit-policy research
+ capital-efficiency intelligence
+ feature/edge drift detection
+ primary-source browser evidence
+ slow owner-approved capital promotion
```

while preserving:

> **Models discover. Rules validate. The allocator selects. The Risk Authority sizes. The Execution Router sends. The owner alone can raise live capital ceilings.**

Profitability is never treated as guaranteed. Every enhancement must prove incremental contribution out of sample, under costs, regime variation and deterministic replay.

---

# 1. Closure doctrine inherited from PR #48

Every work item SHALL identify:

```text
component
authority owner
producer
durable state (if any)
consumer
production caller
owner-facing projection (if any)
tests
runtime evidence
failure/degraded state
falsified_by
```

A work item that cannot fill those fields cannot be called `INTEGRATED_AND_EVIDENCED`.

For every closed finding construct a counterexample in which the implementation appears green while the intended real-world trading outcome is false. If the counterexample still passes, the finding remains open.

Required maturity vocabulary:

```text
ABSENT
STUB
SIMULATED
PARTIAL
IMPLEMENTED_BUT_ISOLATED
INTEGRATED
E2E_VERIFIED
PRODUCTION_CERTIFIED
```

Repository terminal states remain:

```text
INTEGRATED_AND_EVIDENCED
EXTERNALLY_BLOCKED_REPOSITORY_COMPLETE
DELIBERATELY_REMOVED_CANON_CORRECTED
```

Fail-closed is safety, not capability completion.

---

# 2. Source-of-truth and authority rules

## 2.1 This document does not silently acquire authority

At the baseline, `docs/project-state/AUTHORITY_MAP.yaml` permits the deployment blueprint Rev 5 to own trading invariants. This blueprint therefore starts as a **derived implementation blueprint**.

It SHALL NOT be added to `owning_documents` merely because implementation cites it.

## 2.2 Adoption modes

### Mode A — derived implementation blueprint

Preferred initially. Existing Rev 4 / Rev 5 remain authoritative.

### Mode B — admit only genuinely new invariant subjects

If owner-adopted, add the exact repository path to `owning_documents` and add only new subject names, for example:

```text
trading.market_state_timeframe_identity
trading.required_feature_contract
trading.feature_admission
trading.strategy_validation_evidence
trading.account_runtime_single_authority
trading.portfolio_candidate_allocation
trading.allocator_cannot_size
trading.capital_promotion_requires_owner
trading.execution_policy_is_template_bounded
```

Do not duplicate existing ownership such as:

```text
trading.t0_isolation
trading.ledger_authority
authority.owner_approval
authority.learning_cannot_widen
verification.no_success_without_evidence
```

## 2.3 Existing authority survives

```text
Risk Authority = only live sizer
Execution Router = only VATI order sender
Trading Mandate / Platform Ceilings = live capital authority
owner A4 signature = promotion / capital-widening authority
ledger = trade truth / halt truth
browser + Hermes = no order authority
learning = reduce / demote / propose only
```

---

# 3. Verified baseline

The programme is written against actual repository state at `66e4e42`.

1. `DecisionCycle` is one pass per bar/tick for one instrument.
2. `SessionConfig` contains one `symbol`.
3. `SessionLock` enforces one live process per account alias on one host.
4. Risk snapshots read the account book and therefore enforce portfolio-wide constraints.
5. `OpportunityEngine` chooses the best strategy signal within one symbol and directly creates `TradeIntent`.
6. `TradeIntent.correlation_multiplier` reaches Risk Authority but is not populated by the opportunity path.
7. `deflated_sharpe()` returns a probability through a normal CDF.
8. DSR/PBO exist in backtest code but are not semantic promotion evidence.
9. `required_features` is declared in capsule documents but is not enforced.
10. `MarketState` and `FeatureVector` do not identify timeframe.
11. The lake already stores `M1/M5/M15/H1/H4/D1`.
12. TCA already updates `BrokerExecutionProfile` and reduce-only broker liquidity.
13. Strategy targets already survive into the live execution path.
14. Live session learning is wired at the PR #48 baseline.
15. Owner authority tokens, live risk safety flags, broker margin gates, restart-safe idempotency, session locking, ledger staleness and durable owner halt are already closure-evidenced.
16. Browser/automation remain outside the tick-to-order path.
17. Stack lock requires one production kernel, one order sender and one transactional authority store.
18. NautilusTrader remains the canonical future kernel at its adoption gate; this programme must not create a parallel execution kernel.

These existing closures are regression requirements, not implementation suggestions.

---

# 4. Global non-negotiable invariants

## 4.1 Runtime intelligence may not amplify risk

Every live intelligence multiplier remains:

```text
0 <= multiplier <= 1
```

Forbidden examples:

```text
confidence_multiplier > 1
correlation_multiplier > 1
volatility_multiplier > 1
execution_quality_multiplier > 1
```

## 4.2 Learning cannot mint authority

Automatic systems MAY:

```text
WAIT · SKIP · REJECT · REDUCE · DEMOTE · SUSPEND · TIGHTEN · FLAG · PROPOSE
```

They MAY NOT:

```text
raise max_risk_per_trade
raise strategy_risk_budget
promote into more live authority
widen a live ceiling
mutate the owner mandate
clear an owner halt
```

## 4.3 Allocator is not Risk Authority

The allocator may rank, defer, reject or expire candidates. It may not set approved size, approved risk percentage, reserve portfolio heat or bypass `RiskAuthority.evaluate_safe(...)`.

## 4.4 Browser / Stagehand / Hermes are research and explanation surfaces

They never directly reach broker order methods, `ExecutionRouter.execute`, mandate mutation or capsule promotion.

## 4.5 No indicator voting

Features describe state. Strategies decide what that state means. `7 bullish vs 3 bearish = BUY` is forbidden.

## 4.6 Existing hard prohibitions remain

Including:

```text
single_dom_as_total_fx_liquidity
macro_causality_on_synthetics
silent_strategy_mutation
```

---

# 5. P0 integrity repairs — must precede enhancement

## 5.1 P0-A — DSR contract normalization

`deflated_sharpe()` returns a probability. A stale gate `deflated Sharpe > 0` is effectively vacuous for finite values.

Introduce a semantic value object:

```python
@dataclass(frozen=True)
class ValidationStatistics:
    observed_sharpe: float
    dsr_probability: float
    pbo_probability: float
    n_trials: int
    n_observations: int
    validation_policy_version: str
```

Canonical initial policy:

```text
dsr_probability >= 0.95
pbo_probability <= 0.10
```

Put thresholds in `trading/vati/validation/policy.py`, not scattered literals.

`trading/vati/learning/curriculum.py` currently carries the only correct threshold in the repository, as a
human-readable stage string (`"expectancy >= 0.2R, PBO <= 0.10, DSR > 0.95 on backtest"`). Once `policy.py`
exists that string becomes a third copy that can drift. It SHALL be rendered from the policy object rather
than written as a literal, and a test SHALL assert the rendered text matches the active policy.

Required tests:

```text
negative observed Sharpe cannot pass merely because CDF > 0
low DSR fails
high DSR passes
PBO above threshold fails
validation policy version is sealed in the certificate
```

Mutation: change `>= 0.95` to `> 0`. The suite must fail.

Counterexample: certificate tests only a high-Sharpe strategy while a negative-Sharpe strategy also passes. If undetected, P0-A is not closed.

## 5.2 P0-B — required features become executable contract

Add `FeatureContractValidator` at `trading/vati/intelligence/feature_contract.py`.

```python
@dataclass(frozen=True)
class FeatureContractVerdict:
    satisfied: bool
    missing: tuple[str, ...]
    stale: tuple[str, ...]
    unsupported_for_venue: tuple[str, ...]
    insufficient_history: tuple[str, ...]
    bad_provenance: tuple[str, ...]
    invalid_timeframe: tuple[str, ...]
    degraded: tuple[str, ...]
    reasons: tuple[str, ...]
    verdict_hash: str
```

Fail-closed reason:

```text
FEATURE_CONTRACT_UNSATISFIED
```

Production join:

```text
Capsule → required features
MTF state → available features
FeatureContractValidator
    ↓
StrategyArbiter
    ↓ only if satisfied
Strategy.evaluate(...)
```

Validation must run at evaluation time, not only at startup/admission.

Required failure cases:

```text
missing
None
stale
wrong timeframe
wrong venue class
insufficient history
bad provenance
required feed degraded
```

Counterexample: startup passes, M15 feed later loses a required feature, strategy still trades. Must fail.

## 5.3 P0-C — timeframe enters state identity

Add:

```text
FeatureVector.timeframe
MarketState.timeframe
```

Timeframe participates in:

```text
canonical serialization
feature hash
market-state hash
missed-opportunity ex-ante reference
ledger MARKET_STATE event
trade-detail explanation
```

Same numerical features, same symbol/time, different timeframe:

```text
M5 hash != H1 hash
```

Mutation removing timeframe from the hash must be caught.

---

# 6. Multi-timeframe market intelligence

Reuse the existing lake. Do not create a second market-data store.

## 6.1 Capsule timeframe contract

```yaml
timeframe_contract:
  structural: H4
  regime: H1
  setup: M15
  execution: M5
```

Simple capsule:

```yaml
timeframe_contract:
  primary: D1
```

## 6.2 FeatureValue

```python
@dataclass(frozen=True)
class FeatureValue:
    feature_id: str
    feature_version: str
    timeframe: str
    lookback: int
    value: Decimal | None
    normalized_value: Decimal | None
    percentile: Decimal | None
    as_of_ms: int
    venue_class: str
    source_semantics: str
    data_quality: str
    provenance_hash: str
```

## 6.3 FeatureVectorV2

```python
@dataclass(frozen=True)
class FeatureVectorV2:
    symbol: str
    timeframe: str
    as_of_ms: int
    feature_set_version: str
    features: Mapping[str, FeatureValue]
    complete: bool
    missing_required_features: tuple[str, ...]
    feature_hash: str
```

Keep compatibility accessors until existing strategies migrate.

## 6.4 TimeframeMarketState

```python
@dataclass(frozen=True)
class TimeframeMarketState:
    symbol: str
    timeframe: str
    as_of_ms: int
    session: str
    features: FeatureVectorV2
    regime: RegimeState
    integrity: str
    event_window: str
    quote_age_ms: int
    activation_id: str
    feature_hash: str
    regime_hash: str
    timeframe_state_hash: str
```

## 6.5 MultiTimeframeMarketState

```python
@dataclass(frozen=True)
class MultiTimeframeMarketState:
    symbol: str
    as_of_ms: int
    constituent_states: Mapping[str, TimeframeMarketState]
    required_timeframes: tuple[str, ...]
    fusion_policy_version: str
    mtf_state_hash: str
```

Hash includes ordered `(timeframe, timeframe_state_hash)` pairs.

## 6.6 No fake timeframe fusion

Do not average H4/H1/M15/M5 indicators unless a separately validated feature definition explicitly does so. Timeframes answer different questions.

## 6.7 As-of discipline

For candidate time `T`:

- never consume a bar closing after `T`;
- use latest fully closed required bars unless capsule explicitly validates an intra-bar input;
- carry each constituent `as_of_ms`;
- do not leak unfinished H1/H4 data into lower-timeframe decisions.

Mutation allowing unfinished higher-timeframe bars must change results and be caught by leakage tests.

## 6.8 Capsule schema migration

Every migrated capsule records:

```text
old_capsule_hash
new_capsule_hash
migration_reason = MTF_SCHEMA_ADOPTION
strategy_logic_changed = false
owner_authority_changed = false
migrated_at_unix
```

`strategy_logic_changed=false` must be mechanically verified: entry, invalidation, stop, target, eligibility and risk-limit references remain byte-identical. Otherwise it is a strategy revision.

---

# 7. Venue-aware feature registry

## 7.1 FeatureDefinition

```python
@dataclass(frozen=True)
class FeatureDefinition:
    feature_id: str
    version: str
    family: str
    required_inputs: tuple[str, ...]
    venue_classes: frozenset[str]
    allowed_timeframes: frozenset[str]
    minimum_history: int
    source_semantics: str
    implementation_ref: str
    certificate_required: bool
```

## 7.2 Families

```text
TREND
MOMENTUM
VOLATILITY
STRUCTURE
LIQUIDITY
VOLUME_ACTIVITY
EVENT
EXECUTION
CROSS_ASSET
```

## 7.3 First research tranche

After P0-B/P0-C:

```text
ADX / DMI
Donchian channel
MACD OR PPO
multi-horizon ROC
```

A second member of a redundant pair must prove incremental value over the first admitted member.

## 7.4 FX volume semantics

Spot FX is decentralized OTC. Do not label broker volume as universal traded volume.

Use explicit semantics such as:

```text
BROKER_TICK_ACTIVITY
BROKER_QUOTE_ACTIVITY
BROKER_REPORTED_VOLUME_PROXY
```

## 7.5 ZSE/VFEX volume

Where real traded volume exists, volume features can be admitted with venue-specific provenance.

## 7.6 Microstructure boundary

Depth/order-flow features remain out of scope until suitable source data exists, provenance is proven, any current mandate prohibition is explicitly amended, and the feature passes validation. A single broker DOM is never renamed total FX liquidity.

---

# 8. Feature Validation Certificate

```python
@dataclass(frozen=True)
class FeatureValidationCertificate:
    feature_id: str
    feature_version: str
    baseline_feature_set_hash: str
    candidate_feature_set_hash: str
    instruments: tuple[str, ...]
    regimes: tuple[str, ...]
    timeframes: tuple[str, ...]
    redundancy_correlation: float
    mutual_information_delta: float | None
    incremental_expectancy_delta: float
    incremental_dsr_probability: float
    incremental_pbo_probability: float
    walk_forward_delta: float
    regime_stability: Mapping[str, float]
    instrument_stability: Mapping[str, float]
    leakage_result: str
    status: str
    certificate_hash: str
```

Allowed states:

```text
REJECTED_REDUNDANT
REJECTED_UNSTABLE
SHADOW_APPROVED
PRODUCTION_ADMITTED
```

Standalone correlation is insufficient. Admission requires incremental value over the current baseline feature set.

Certificate lineage includes data manifest, code version, feature-set hash, cost model, validation policy and experiment configuration.

A production capsule may require a feature only when a compatible certificate is `PRODUCTION_ADMITTED`.

---

# 9. Functional confluence

```python
@dataclass(frozen=True)
class ConfluenceAxis:
    state: str
    evidence_refs: tuple[str, ...]
    disagreement_refs: tuple[str, ...]
    as_of_ms: int

@dataclass(frozen=True)
class ConfluenceState:
    trend: ConfluenceAxis
    momentum: ConfluenceAxis
    volatility: ConfluenceAxis
    structure: ConfluenceAxis
    liquidity: ConfluenceAxis
    event: ConfluenceAxis
    execution: ConfluenceAxis
    cross_asset: ConfluenceAxis
    state_hash: str
```

Confluence owns no `buy`, `sell`, `size`, `execute` or `approve` method.

Owner narration is produced from stored evidence, e.g. H1 trend persistent, M15 momentum weakening, H4 resistance overhead, liquidity normal, no Tier-1 blackout.

---

# 10. Strategy Validation Certificate

Current promotion proves an owner signed and evidence references exist; it does not prove semantic evidence content.

```python
@dataclass(frozen=True)
class StrategyValidationCertificate:
    certificate_id: str
    strategy_id: str
    strategy_version: str
    capsule_hash: str
    data_manifest_hash: str
    feature_set_version: str
    feature_certificate_refs: tuple[str, ...]
    cost_model_revision: str
    n_trials: int
    trade_count: int
    walk_forward_windows: int
    cpcv_configuration: Mapping[str, object]
    expectancy_R: float
    expectancy_lower_bound_R: float
    profit_factor: float
    max_drawdown: float
    observed_sharpe: float
    dsr_probability: float
    pbo_probability: float
    cost_stress_2x: str
    latency_slippage_stress: str
    parameter_perturbation_stability: str
    regime_breakdown: Mapping[str, object]
    leakage_switch_result: str
    validation_policy_version: str
    validation_hash: str
```

Owner promotion binds at minimum:

```text
strategy_id
strategy_version
capsule_hash
target_state
validation_hash
mandate_version
```

Initial policy:

```text
VALIDATION → DEMO:
  dsr_probability >= policy threshold
  pbo_probability <= policy threshold
  walk-forward GREEN
  leakage GREEN
  cost stress GREEN

SHADOW → LIMITED_LIVE:
  owner signature + certificate + shadow evidence

LIMITED_LIVE → CERTIFIED_LIVE:
  owner signature + real execution/cost evidence + no unresolved hard blocker
```

When the stack-lock LEAN adoption gate is reached, independent reproduction remains validation-only and never becomes an order sender.

---

# 11. Candidate / Intent separation

## 11.1 Problem

`OpportunityEngine` currently creates `TradeIntent` before account-level cross-symbol competition exists.

## 11.2 CandidateOpportunity

```python
@dataclass(frozen=True)
class CandidateOpportunity:
    candidate_id: str
    account_alias: str
    venue: str
    symbol: str
    strategy_id: str
    strategy_version: str
    capsule_hash: str
    generated_at_ms: int
    valid_from_ms: int
    valid_until_ms: int
    mtf_state_hash: str
    source_state_hashes: tuple[str, ...]
    direction: str
    entry: Decimal
    stop: Decimal | None
    targets: tuple[Decimal, ...]
    horizon: str
    expected_gross_move_pct: Decimal | None
    cost_multiple: Decimal
    confidence_score: Decimal
    edge_floor_R: Decimal | None
    expected_R_per_risk_day: Decimal | None
    regime_stability: Decimal | None
    execution_quality: Decimal | None
    estimated_fill_probability: Decimal | None
    factor_exposures: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    candidate_hash: str
```

Candidate carries no approved size, no approved risk, no RiskDecision hash and no router capability.

### Target precedence — closes the P1-TRADE-007 surface

`CandidateOpportunity` carries both `targets` and `expected_gross_move_pct`. P1-TRADE-007 is precisely the
regression where the decision cycle *"used to throw these away and re-derive a single target from
`expected_gross_move_pct`"*. Carrying both fields reinstates that surface unless the precedence is law:

```text
targets non-empty   →  IntentFactory MUST use targets verbatim
targets empty       →  the existing expected_gross_move_pct fallback applies
```

`IntentFactory` SHALL NOT read `expected_gross_move_pct` when `targets` is non-empty. Required test
`test_intent_factory_prefers_explicit_targets`, with the mutation *swap target precedence* in §48.

Refactor into:

```text
OpportunityEngine.assess_candidates(...)
IntentFactory.from_selected_candidate(...)
```

`IntentFactory` is called only by the account coordinator after allocation.

Backward-compatibility gate: with one symbol/one candidate, strategy, entry, stop, targets, multipliers and Risk Authority result remain equivalent to the prior path except intended schema/hash changes.

---

# 12. AccountDecisionCoordinator

One live account alias owns one authoritative coordinator process.

```text
AccountDecisionCoordinator
│
├── AccountRuntime
│   ├── VenueAdapter
│   ├── TradingMandate
│   ├── RiskAuthority
│   ├── ExecutionRouter
│   ├── KillSwitch
│   ├── ledger
│   └── AccountRuntimeLease
│
├── InstrumentEvaluator[EURUSD]
├── InstrumentEvaluator[GBPUSD]
├── InstrumentEvaluator[XAUUSD]
├── ...
├── CandidatePool
├── PortfolioDependencyEngine
└── OpportunityPortfolioAllocator
```

`InstrumentEvaluator` owns symbol-local market state, regime, feature contract, strategy evaluation and candidate production. It does not own live sizing or execution.

Do not turn `DecisionCycle` into a monolithic N-symbol object. Its current symbol-specific regime, contract, protection, TCA, `_entries` and idempotency concerns would become hidden collections mixed with account authority.

Live service evolves from:

```text
vati-session@<alias> → one DecisionCycle
```

to:

```text
vati-session@<alias> → AccountDecisionCoordinator → InstrumentEvaluator[N]
```

---

# 13. Distributed AccountRuntimeLease

Keep host-local `flock`. `trading/vati/app/process_lock.py` already states its own limit precisely, and §13
inherits that statement rather than restating it:

> it is per-host, so it does not stop a second VM running the same alias, and it is advisory, so it binds only
> processes that ask. Both are acceptable here because the thing being prevented is an operator starting
> `serve` twice, not an adversary.

Add a transactional cross-host lease on the VATI authority store (§33.1).

```text
account_runtime_leases
  account_alias PRIMARY KEY
  holder_instance_id
  lease_epoch
  acquired_at_ms
  heartbeat_at_ms
  expires_at_ms
  software_version
  git_sha
```

Acquire atomically if absent or expired. Renewal requires matching holder and epoch. Every order-producing
path carries the current `lease_epoch`; the Router refuses stale epochs.

## 13.1 Reachability is a precondition, not an assumption — [OWNER-DEFAULT]

At the baseline `vati-supabase` is **loopback only** (`deploy/van-trading-core/README.md`). A second host
therefore cannot reach the lease store at all.

Two refusals must never be conflated:

```text
LEASE_REFUSED_HELD_BY_OTHER      arbitration worked
LEASE_STORE_UNREACHABLE          fail-closed, arbitration did NOT run
```

Both block new orders. Only the first proves the control. A test that asserts "second VM cannot trade" while
the store is unreachable proves unreachability, and would let the `remove lease_epoch fence` mutation survive.

Therefore:

- the lease API SHALL return the two outcomes as distinct typed results;
- the fencing test SHALL assert `LEASE_REFUSED_HELD_BY_OTHER` against a **reachable shared store**;
- until the VATI authority store is reachable from more than one host, the cross-host property is classified
  `EXTERNALLY_BLOCKED_REPOSITORY_COMPLETE` with the missing artefact named as
  *"authority store reachable from a second host"* — not as a working control.

Single-host correctness (lock + lease + epoch fence within one host) is fully closable now and is not
externally blocked.

---

# 14. CandidatePool

CandidatePool creates the bounded time window where multiple symbols can compete.

States:

```text
ACTIVE
SELECTED
DEFERRED
REJECTED
EXPIRED
SUPERSEDED
```

Every candidate has deterministic TTL/freshness based on strategy/horizon. A candidate cannot become `TradeIntent` when expired, source state is no longer latest-compatible, integrity degraded beyond policy, or event state changed into a prohibited state.

Suggested supersession key:

```text
account_alias + symbol + strategy_id + direction + setup_identity
```

Potential Trades UI must distinguish active, deferred, risk-rejected, router-refused and expired states.

---

# 15. Portfolio Opportunity Allocator

Allocator performs selection, not sizing.

```python
@dataclass(frozen=True)
class AllocationEpoch:
    allocation_epoch_id: str
    account_alias: str
    started_at_ms: int
    portfolio_snapshot_hash: str
    candidate_hashes: tuple[str, ...]
    policy_version: str
```

```python
@dataclass(frozen=True)
class AllocationDecision:
    allocation_epoch_id: str
    candidate_id: str
    rank: int
    decision: str
    allocation_utility: Decimal
    score_components: Mapping[str, Decimal]
    incremental_expected_shortfall: Decimal | None
    overlap_penalty: Decimal | None
    capital_efficiency: Decimal | None
    execution_quality: Decimal | None
    explanation: tuple[str, ...]
    decision_hash: str
```

### Allocator V0 inputs — [OWNER-DEFAULT]

`trading/vati/arbiter/confidence.py` states its score *"never sizes a trade, and it never feeds the Risk
Authority"*, and calls itself `RULES_V0_UNCALIBRATED`. Under §15's sequential procedure, ranking decides which
candidate **reaches** the Risk Authority and therefore which consumes scarce capacity — so ranking on an
uncalibrated score would let it decide which trade happens. That is the indirect authority path §65 rule 9
exists to catch.

Allocator V0 therefore ranks on deterministic, non-model evidence only:

```text
cost_multiple              lower is better, already deterministic
freshness                  remaining TTL fraction
regime_multiplier          rule-derived, reduce-only, already bounded
dependency_penalty         when the dependency engine is live (Phase 7)
```

`confidence_score` is **carried on the candidate for owner display and is excluded from V0 ranking.**
Confidence-weighted ranking is deferred to Allocator V1 (§12 of the phase order) and only after §28's
calibration gate passes. A contract test asserts V0's utility is invariant to `confidence_score`.

Allocator V1 later adds edge floor, risk-day efficiency, incremental ES, overlap, execution quality, fill probability, regime stability and financing/rollover cost.

Deterministic tie-break:

```text
allocation utility DESC
valid_until ASC
symbol ASC
strategy_id ASC
candidate_id ASC
```

`allocation_utility` is a ranking utility, not a probability of profit.

Shared-heat procedure:

```text
rank fresh candidates
    ↓
candidate #1
    ↓
fresh account/position snapshot
    ↓
RiskAuthority.evaluate_safe
    ↓
execute / reject
    ↓
reconcile / refresh truth
    ↓
candidate #2
```

Allocator has no `reserve_heat`, `allocate_size` or `preapprove` API.

---

# 16. AllocationEpisode learning

```python
@dataclass(frozen=True)
class AllocationEpisode:
    allocation_epoch_id: str
    selected_candidate_ids: tuple[str, ...]
    rejected_candidate_ids: tuple[str, ...]
    portfolio_snapshot_hash: str
    ranking_policy_version: str
    ranking_features: Mapping[str, object]
    realised_selected_outcomes: Mapping[str, object]
    counterfactual_rejected_outcomes: Mapping[str, object]
    environment: str
    evidence_weight: Decimal
    episode_hash: str
```

Rejected candidates use the same hindsight guard principle as `missed.py`: ex-ante validity is frozen; later path only scores outcome. A Risk Authority rejection is not allocator regret, even if price later moved favorably.

New allocator policies progress through research/replay/backtest/shadow before production admission. No live self-training.

---

# 17. PortfolioDependencyEngine

Two separate correlation questions exist.

### A — live market-exposure dependency

Uses instrument returns, explicit factor metadata, current positions, candidate direction and stressed covariance. Live effect is reduce/reject only.

### B — strategy-return dependency

Uses realised/shadow R-multiples to support slow capital proposals and diversification research; never live risk amplification.

Initial factor metadata may include:

```text
USD · EUR · GBP · JPY · GOLD · RATES · RISK_ON_OFF · ZIG · ZSE_SECTOR · VFEX_USD
```

Factor tags are versioned configuration, not LLM guesses.

Add Expected Shortfall alongside stop-risk heat and currency-leg exposure.

```python
@dataclass(frozen=True)
class PortfolioDependencySnapshot:
    as_of_ms: int
    portfolio_snapshot_hash: str
    candidate_id: str
    normal_model_hash: str
    stressed_model_hash: str
    es_before: Decimal
    es_after: Decimal
    incremental_es: Decimal
    factor_exposures: Mapping[str, Decimal]
    correlation_multiplier: Decimal
    dependency_hash: str
```

Populate the existing `TradeIntent.correlation_multiplier` with a real reduce-only value:

```text
0 <= correlation_multiplier <= 1
```

No covariance estimate must never be interpreted as zero dependency. Use an explicit conservative factor-overlap fallback or reject/wait according to policy.

---

# 18. StrategyOverlapDetector

Correlation alone is insufficient when historical sample is small. Track:

```text
instrument overlap
factor overlap
direction overlap
regime overlap
entry-time overlap
return correlation
drawdown co-occurrence
```

Output `LOW/MEDIUM/HIGH/UNKNOWN`. Live effect reduce-only; slow effect informs capital proposals.

---

# 19. Continuous volatility targeting

Optional and certificate-gated:

```text
vol_multiplier = min(1, certified_target_vol / max(current_realised_vol, epsilon))
```

It cannot exceed 1, cannot replace hard volatility/regime gates, and the target cannot self-update live.

---

# 20. Capital Promotion Plane

Fast safety loop may shrink immediately. Slow upside loop validates, proposes and requires owner signature.

Extend `TradingMandate`:

```yaml
strategy_risk_budgets:
  FX-TREND-PULLBACK-01: "0.0075"
  FX-LONDON-BREAKOUT-01: "0.0030"
```

Absolute constraints:

```text
0 < strategy budget
strategy budget <= mandate.max_risk_per_trade
strategy budget <= PlatformCeilings.max_risk_per_trade
```

Backward-compatible fallback retains current base risk when no per-strategy budget exists.

Runtime approved risk remains base risk multiplied only by reduce-only factors.

```python
@dataclass(frozen=True)
class CapitalBudgetProposal:
    proposal_id: str
    strategy_id: str
    strategy_version: str
    current_budget: Decimal
    proposed_budget: Decimal
    validation_hash: str
    live_sample: int
    shadow_sample: int
    expectancy_R: Decimal
    edge_floor_R: Decimal
    max_drawdown: Decimal
    tail_risk: Decimal
    strategy_return_correlation: Mapping[str, Decimal]
    regime_stability: Mapping[str, Decimal]
    capital_efficiency: Decimal
    execution_quality: Decimal
    evidence_refs: tuple[str, ...]
    created_at_ms: int
    expires_at_ms: int
    proposal_hash: str
```

Proposal has zero mutation authority. Only an owner-signed new mandate version changes a ceiling. Signature binds account, mandate id/version, old/new budget, strategy id, validation hash and proposal hash.


---

# 21. Uncertainty-aware edge

Do not allocate capital from mean expectancy alone.

Store:

```text
mean_expectancy_R
edge_floor_R
interval_method
sample_size
regime_coverage
```

Use `edge_floor_R` for Allocator V1 and capital promotion. Advanced conformal or adaptive uncertainty models remain research/shadow until out-of-sample calibration is demonstrated.

---

# 22. ExecutionPolicyEngine

Preserve the existing TCA feedback path:

```text
ExecutionReceipt → TCA → LearningBroker → BrokerExecutionProfile → broker_liquidity → MetaLabeler
```

Add execution-choice intelligence across:

```text
broker
account alias
symbol
session
volatility bucket
event proximity
direction
order template
```

Metrics:

```text
fill probability
time to fill
partial-fill probability
slippage
spread captured
post-fill adverse movement
cancel/requote rate
non-fill opportunity cost
implementation shortfall
```

Sealed templates only:

```text
PASSIVE
PASSIVE_THEN_CROSS
LIMIT_AT_TOUCH
LIMIT_WITH_BOUNDED_CHASE
MARKET_WITH_SLIPPAGE_CAP
DO_NOT_EXECUTE
```

```python
@dataclass(frozen=True)
class ExecutionTemplate:
    template_id: str
    version: str
    allowed_entry_types: tuple[str, ...]
    max_chase_ticks: int
    max_wait_ms: int
    max_replace_count: int
    max_slippage: Decimal
    cancel_on_event_state: tuple[str, ...]
    fallback_template_id: str | None
```

```python
@dataclass(frozen=True)
class ExecutionPolicyDecision:
    candidate_id: str
    template_id: str
    template_version: str
    estimated_fill_probability: Decimal | None
    expected_slippage: Decimal | None
    expected_adverse_selection: Decimal | None
    expected_non_fill_cost: Decimal | None
    expected_shortfall: Decimal | None
    evidence_sample_size: Decimal
    evidence_state: str
    decision_hash: str
```

If sample quality is insufficient, use the current certified default execution behavior. No learned system invents an arbitrary order shape.

The execution-policy component decides **how** to execute an already-approved trade; it cannot cause an unapproved trade to exist.

---

# 23. Cross-broker execution selection — future gate

Only after multiple owner-authorized venues genuinely exist for the same instrument may VAN compare venue execution quality.

It may not create accounts, transfer funds, use unauthorized venues, or broaden mandate scope.

Until real multi-venue conditions exist, classify this capability honestly as future / external rather than built.

---

# 24. ExitPolicyResearchEngine

Protection stays deterministic live. Exit optimization is offline/shadow research.

Preserve:

```text
MFE
MAE
time_to_MFE
time_to_MAE
time_to_target
post_exit_continuation
give_back_from_MFE
```

Do not learn directly from winners-only MAE/MFE.

Registered research family:

```text
CURRENT_POLICY
TIME_EXIT
EXIT_ONE_BAR_LATER
EXIT_N_BARS_LATER
SCALE_HALF_AT_1R_THEN_TRAIL
SCALE_33_33_34
ATR_TRAIL
STRUCTURE_TRAIL
VOL_ADJUSTED_TRAIL
BREAK_EVEN_0_75R
BREAK_EVEN_1R
BREAK_EVEN_1_5R
NO_BREAK_EVEN
FIXED_2R
FIXED_3R
FIXED_4R
REGIME_CONDITIONED_TARGET
LET_RUN_UNTIL_INVALIDATION
```

Research produces `ExitPolicyCandidate`, never a live mutation.

Admission requires the same validation discipline as a strategy revision:

```text
walk-forward
DSR
PBO
cost stress
regime breakdown
execution realism
leakage switch
```

Then a new capsule revision enters the normal promotion lifecycle.

---

# 25. StrategyCoverageMap

Map:

```text
market × instrument × horizon × regime × style × session × event-state × currency-regime
```

Coverage states:

```text
COVERED_CERTIFIED
COVERED_LIMITED
COVERED_RESEARCH
INTENTIONALLY_ABSTAIN
UNRESEARCHED
RESEARCH_NEGATIVE
BLOCKED_DATA
```

Current FX `RANGE` is an uncovered research space, not automatically lost profit.

Measure first:

```text
share of tradable time
spread/cost conditions
false-breakout frequency
historical opportunity count
validated hypothetical expectancy
edge after cost
capital opportunity cost
```

Possible research families:

```text
range mean reversion
failed breakout / rejection
compression-to-expansion transition
```

No matrix gap creates a live strategy by itself.

---

# 26. Feature and edge drift

Feature drift is tracked by:

```text
feature × strategy × instrument × timeframe × regime
```

Metrics:

```text
distribution shift
incremental contribution
redundancy change
missingness
staleness
regime-specific performance
```

Edge drift:

```text
expectancy_R
edge_floor_R
profit factor
payoff ratio
hit rate
holding time
cost-adjusted expectancy
drawdown
regime-conditioned expectancy
```

Drift may trigger research, lower confidence through already-authorized reduce-only paths, feed StrategyHealth, or recommend feature/capsule review. It does not rewrite a live capsule.

---

# 27. Capital-efficiency intelligence

Record:

```text
expected_R
edge_floor_R
expected_R_per_risk_day
risk-capital occupancy time
fill probability
financing cost
rollover cost
opportunity cost of rejected alternatives
```

Use for Allocator V1, CapitalBudgetProposal, research and owner explanation.

Never convert capital efficiency into a runtime multiplier above 1.

Extend slow-horizon cost models for swap, triple rollover, broker financing schedules and holding period where applicable.

---

# 28. MetaLabeler calibration

Keep:

```text
RULES_V0_UNCALIBRATED
```

until a statistical candidate proves:

```text
Brier score
Expected Calibration Error
reliability artifact
out-of-sample calibration
regime stability
```

Rollout:

```text
RESEARCH → SHADOW → DISPLAY_ONLY → REDUCE_ONLY
```

No statistical model may directly raise live risk.

---

# 29. Champion / Challenger research fabric

Use for:

```text
feature sets
exit policies
allocator policies
execution templates
meta-label models
```

`CHALLENGER` is research/shadow only and has no order authority. Champion replacement requires normal validation/admission.

---

# 30. Primary-source browser trading evidence

Create `TradingEvidenceCollector` above Stagehand / Browser Harness:

```text
primary source
    ↓
Stagehand retrieval
    ↓
Browser Harness provenance
    ↓
structured extractor
    ↓
TradingEvidenceArtifact
    ↓
VTIL admission
    ↓
Hermes/T2 assessment
    ↓
MetaLabeler / research
```

Scope may include:

```text
central-bank statements
economic releases
rate announcements
company results
ZSE/VFEX notices
corporate actions
broker specification changes
margin changes
swap/financing changes
session changes
```

```python
@dataclass(frozen=True)
class TradingEvidenceArtifact:
    evidence_id: str
    source_uri: str
    source_type: str
    source_hash: str
    observed_at_ms: int
    effective_at_ms: int | None
    expires_at_ms: int | None
    extracted_facts: Mapping[str, object]
    extractor_version: str
    trust_tier: str
    artifact_hash: str
```

A web page saying `buy EURUSD` is untrusted content, not a signal.

Stagehand successfully fetching a page proves retrieval, not truth. Browser evidence may reduce, explain or trigger research; it may not increase risk, create a live strategy, promote a capsule or send an order.

---

# 31. MarketDataDisagreementDetector

Where a trusted independent reference exists, compare execution feed against reference feed for:

```text
staleness
timestamp divergence
large price divergence
spread anomaly
feed freeze
```

Response is fail-safe (`WAIT`, `REDUCE`, `HALT`) according to policy. Never assume the reference feed is correct merely because it is independent.

Persist disagreement state and provenance.

---

# 32. Event and ledger model

Add typed event kinds or equivalent payloads:

```text
TIMEFRAME_MARKET_STATE
MULTITIMEFRAME_MARKET_STATE
FEATURE_CONTRACT_VERDICT
CONFLUENCE_STATE
FEATURE_VALIDATION_CERTIFICATE
STRATEGY_VALIDATION_CERTIFICATE
CANDIDATE_OPPORTUNITY
CANDIDATE_EXPIRED
ALLOCATION_EPOCH
ALLOCATION_DECISION
ALLOCATION_EPISODE
PORTFOLIO_DEPENDENCY
EXECUTION_POLICY_DECISION
CAPITAL_BUDGET_PROPOSAL
FEATURE_DRIFT
EDGE_DRIFT
STRATEGY_COVERAGE
TRADING_EVIDENCE
MARKET_DATA_DISAGREEMENT
```

Every applicable event includes account alias, symbol, strategy/candidate/trade identifiers, policy/model
version, source hashes, event/received times and canonical payload hash.

## 32.1 Durable state changes, not recomputable per-bar state — [OWNER-DEFAULT]

`EventKind` is a closed enum and the ledger is hash-chained and append-only (role `vati` has no UPDATE or
DELETE on `vati.events`), so an admitted kind is permanent. These are **typed kinds**, not "equivalent
payloads" — the ambiguity is resolved in favour of typed kinds so the enum stays the index of what the system
can say.

Per-bar recomputable state is *not* persisted as an event. It is referenced by hash:

```text
PERSIST (durable state change)     REFERENCE BY HASH (recomputable)
CANDIDATE_OPPORTUNITY              TIMEFRAME_MARKET_STATE
CANDIDATE_EXPIRED                  MULTITIMEFRAME_MARKET_STATE
ALLOCATION_EPOCH                   CONFLUENCE_STATE
ALLOCATION_DECISION                FEATURE_CONTRACT_VERDICT  (when satisfied)
ALLOCATION_EPISODE
PORTFOLIO_DEPENDENCY
EXECUTION_POLICY_DECISION
FEATURE_VALIDATION_CERTIFICATE
STRATEGY_VALIDATION_CERTIFICATE
CAPITAL_BUDGET_PROPOSAL
FEATURE_DRIFT / EDGE_DRIFT
STRATEGY_COVERAGE
TRADING_EVIDENCE
MARKET_DATA_DISAGREEMENT
```

A `FEATURE_CONTRACT_VERDICT` is persisted **only when unsatisfied** — a refusal is a durable state change; a
pass is the normal case and is carried as the verdict hash on the candidate. The MTF state hash already
appears on `CandidateOpportunity.mtf_state_hash`, so the state is reconstructible from the lake slice plus the
capsule and feature-set versions without storing it per bar.

This is the same discipline the ledger already applies to `MARKET_TICK`/`MARKET_BAR` volume.

Causality chain:

```text
MTF state hash
  ↓
feature contract verdict
  ↓
candidate hash
  ↓
allocation decision hash
  ↓
TradeIntent decision hash
  ↓
RiskDecision hash
  ↓
OrderCommand
  ↓
ExecutionReceipt
  ↓
TCA
  ↓
TradeReview
```

Owner surfaces must be able to traverse this chain.

---

# 33. Database migrations and store placement

## 33.1 Two stores, one authority each — [OWNER-DEFAULT]

`stack_lock.json` declares `single_transactional_authority: "PostgreSQL (SQLite in Phases 0-3)"`, and
`trading/vati/core/ledger_pg.py` already implements the hash-chained trading ledger on it. The VAN Gateway's
own store (`backend/van_gateway/storage/db.py`, `SCHEMA_VERSION = 26`) is a **different** store with a
different owner.

Trading decision truth therefore does **not** go into the gateway schema. Placement is fixed per table:

| Table | Store | Reason |
|---|---|---|
| `strategy_validation_certificates` | VATI authority store | promotion evidence, trading truth |
| `feature_validation_certificates` | VATI authority store | admission evidence, trading truth |
| `capsule_schema_migrations` | VATI authority store | capsule provenance |
| `account_runtime_leases` | VATI authority store | order authority fencing |
| `candidate_opportunities` | VATI authority store | decision chain |
| `allocation_epochs` | VATI authority store | decision chain |
| `allocation_decisions` | VATI authority store | decision chain |
| `allocation_episodes` | VATI authority store | decision chain / research |
| `portfolio_dependency_snapshots` | VATI authority store | risk input provenance |
| `execution_policy_decisions` | VATI authority store | execution provenance |
| `capital_budget_proposals` | VATI authority store | capital evidence |
| `strategy_coverage` | VATI authority store | research state |
| `feature_drift_observations` | VATI authority store | research state |
| `edge_drift_observations` | VATI authority store | research state |
| `trading_evidence_artifacts` | VATI authority store | T2 research provenance |
| `market_data_disagreements` | VATI authority store | data-integrity provenance |

**Nothing in this programme adds a trading table to the gateway SQLite schema.** The gateway continues to
serve owner read models by querying VATI read APIs / the ledger, exactly as it does today. If the gateway
later needs a projection table, it is a cache with a stated rebuild source, never trading truth.

Phases 0–3 run SQLite as the VATI store per the stack lock's own transitional clause; the table set and the
DDL are identical, and `ledger_pg` demonstrates the dual-backend pattern to follow.

## 33.2 Migration numbering

At implementation time inspect current main and choose the next unused migration for the store being changed.
Do not hard-code a number.

## 33.3 Immutability

Certificates, proposals, allocation records and evidence artifacts are immutable; corrections create
superseding artifacts. Owner-signed mandate changes are atomic and both versions remain auditable.

Do not insert a network event broker into the T0 route merely because an event table exists.

---

# 34. Backtest / replay / live parity

Supported environments:

```text
BACKTEST · REPLAY · PAPER · DEMO · SHADOW · LIVE
```

Use the same deterministic code for:

```text
feature contracts
MTF assembly
candidate generation
allocation policy
portfolio dependency
Risk Authority
execution-policy selection
```

where adapter semantics permit.

Backtest/replay execution facts must retain their lower evidence weight and cannot masquerade as real broker execution evidence.

Same data, capsules, manifests, policy versions and configuration must reproduce MTF hashes, candidate hashes, allocation order and RiskDecision hashes except genuinely external live fill outcomes.

---

# 35. T0 / T1 / T2 / T3 placement

Respect stack lock.

## T0 — decision path

In-process only:

```text
MTF state
FeatureContract
strategy evaluation
CandidatePool
Allocator
PortfolioDependency fast path
RiskAuthority
ExecutionPolicy selection
ExecutionRouter
```

No LLM, browser, n8n or remote workflow engine inside T0.

## T1 — fast data/state

Transactional authority store, future feature/time-series stores, reference feeds. These must not become unavoidable remote dependencies for every T0 actuation unless explicitly certified.

## T2 — research/knowledge

VTIL, Hermes assessments, browser evidence.

## T3 — research certification

Walk-forward, CPCV/PBO, DSR, Optuna/Qlib research, independent LEAN reproduction and future durable research workflows.

---

# 36. Deployment topology

Keep the enhancement inside the current trading estate:

```text
dial-hermes-control
    │ control/research only
    ▼
van-trading-core
    ├── AccountDecisionCoordinator per account alias
    ├── InstrumentEvaluator[N]
    ├── VATI Risk Authority
    ├── Execution Router
    ├── bar lake
    ├── transactional authority store
    ├── VTIL
    └── commander
```

Windows MT5 worker remains a venue worker where used. Browser Stream Host / Stagehand remains research-side and cannot enter T0.

---

# 37. Existing external/deployment truth

Do not erase current residual truth while improving the architecture.

Repository completion and external readiness are different axes:

```text
feature code complete ≠ live data source available
Postgres code complete ≠ production Postgres qualified
Deriv adapter tested ≠ owner live account connected
Stagehand adapter ready ≠ live external worker qualified
```

Every externally blocked closure must name the missing external artifact precisely.

---

# 38. Owner surface / Trading Command Center

## 38.1 Market Intelligence

Show symbol, constituent timeframes, regime per timeframe, functional confluence, feature health, event state, data integrity and state age.

## 38.2 Potential Trades

Show:

```text
candidate state
age/expiry
strategy/direction
entry/stop/targets
allocator rank
allocation utility
incremental ES
capital efficiency
selection/defer/reject reason
```

Do not display size until Risk Authority produces one.

## 38.3 Strategy Intelligence

Show capsule state, validation certificate, DSR probability, PBO probability, walk-forward state, cost stress, feature-set hash, feature certificates, coverage role and drift state.

## 38.4 Execution Intelligence

Show selected execution template, fill estimate, actual fill, slippage, implementation shortfall, broker profile and sample sufficiency.

## 38.5 Capital Promotion

Show current budget, proposed budget, edge floor, live/shadow sample size, drawdown, tail risk, strategy-return correlation, capital efficiency, expiry and owner approval state.

## 38.6 Explainability

Owner questions resolve from ledger evidence:

```text
Why GBPUSD over EURUSD?
Why was XAUUSD deferred?
Why was risk reduced?
Which timeframes supported this?
Which feature contract failed?
Which certificate admitted the strategy?
Which execution template ran?
What happened to rejected alternatives?
```

No ungrounded reconstruction from model intuition.

---

# 39. Repository file plan

Integrate by current domain ownership; do not create a parallel `smart_trading/` stack.

## Intelligence

Modify:

```text
trading/vati/intelligence/features.py
trading/vati/intelligence/market_state.py
trading/vati/intelligence/regimes.py
```

Add:

```text
trading/vati/intelligence/feature_registry.py
trading/vati/intelligence/feature_contract.py
trading/vati/intelligence/mtf.py
trading/vati/intelligence/confluence.py
trading/vati/intelligence/feature_validation.py
```

## Validation

```text
trading/vati/validation/__init__.py
trading/vati/validation/policy.py
trading/vati/validation/strategy_certificate.py
trading/vati/validation/feature_certificate.py
```

Reuse `trading/vati/backtest/metrics.py`.

## Strategies

Modify:

```text
trading/vati/strategies/capsule.py
trading/vati/strategies/base.py
trading/strategies/registry/*.json
```

Add `trading/tools/migrate_capsule_timeframes.py`.

## Arbitration

Modify `trading/vati/arbiter/opportunity.py`.

Add:

```text
trading/vati/arbiter/candidate.py
trading/vati/arbiter/intent_factory.py
trading/vati/arbiter/portfolio_allocator.py
trading/vati/arbiter/allocation_policy.py
```

## Account runtime

```text
trading/vati/app/account_coordinator.py
trading/vati/app/instrument_evaluator.py
trading/vati/app/candidate_pool.py
trading/vati/app/account_lease.py
```

Refactor shared logic from `cycle.py`, `service.py`, `runner.py`, `__main__.py` without breaking parity.

## Risk

Modify:

```text
trading/vati/risk/mandate.py
trading/vati/risk/contracts.py
trading/vati/risk/authority.py
trading/vati/risk/serde.py
```

Add:

```text
trading/vati/risk/factors.py
trading/vati/risk/dependency.py
trading/vati/risk/expected_shortfall.py
```

## Execution

Modify `tca.py`, `router.py`, `learning/broker.py`.

Add:

```text
trading/vati/execution/policy.py
trading/vati/execution/policy_templates.py
```

## Learning / research

```text
trading/vati/learning/allocation.py
trading/vati/learning/exit_research.py
trading/vati/learning/feature_drift.py
trading/vati/learning/coverage.py
trading/vati/learning/capital_efficiency.py
trading/vati/research/trading_evidence.py
trading/vati/research/market_data_disagreement.py
```

## Owner read models

Extend `trading/vati/app/tradebook.py`, `portfolio.py`, `backend/van_gateway/trading/*`, and Android trading surfaces. These remain read/approval surfaces, not order senders.

---

# 40. API contracts

Potential read routes:

```text
GET /v1/trading/market-state?symbol=
GET /v1/trading/candidates?account_alias=
GET /v1/trading/allocation/latest?account_alias=
GET /v1/trading/strategies/{id}/validation
GET /v1/trading/strategies/{id}/coverage
GET /v1/trading/strategies/{id}/drift
GET /v1/trading/execution/intelligence?symbol=
GET /v1/trading/capital-proposals
```

Capital mutation must use the existing owner authority model. Do not create a hidden auto-apply proposal route.

---

# 41. Observability

Bounded-cardinality metrics:

```text
vati_feature_contract_failures_total
vati_mtf_state_build_seconds
vati_mtf_missing_timeframe_total
vati_candidates_active
vati_candidate_expirations_total
vati_candidate_supersessions_total
vati_allocation_epochs_total
vati_allocator_selected_total
vati_allocator_deferred_total
vati_allocator_rejected_total
vati_portfolio_incremental_es
vati_correlation_multiplier
vati_strategy_certificate_state
vati_feature_certificate_state
vati_execution_policy_selected_total
vati_execution_fill_probability_estimate
vati_execution_shortfall
vati_capital_proposals_total
vati_capital_proposal_expired_total
vati_allocation_regret_R
vati_feature_drift_alerts_total
vati_edge_drift_alerts_total
vati_strategy_coverage_gaps
vati_data_disagreements_total
```

Do not use unbounded IDs or URLs as Prometheus labels.

---

# 42. Degraded states

Owner-visible states distinguish:

```text
FEATURE_DEGRADED
MTF_INCOMPLETE
ALLOCATION_DEGRADED
DEPENDENCY_MODEL_DEGRADED
EXECUTION_INTELLIGENCE_INSUFFICIENT
TRADING_EVIDENCE_STALE
REFERENCE_FEED_DISAGREEMENT
CAPITAL_PROPOSAL_EXPIRED
```

Example: insufficient execution-learning evidence may safely fall back to the certified default template; transactional risk truth unavailable must block new risk.

---

# 43. Security / threat model

| Threat | Required control |
|---|---|
| AI gives itself more risk | proposal != mandate; A4 signature; multipliers <=1 |
| Allocator becomes shadow Risk Authority | no candidate size; fresh RiskAuthority call |
| Stale candidate executes | TTL + state hash + freshness recheck |
| Duplicate account coordinators | flock + distributed lease + lease_epoch fence + broker reconciliation |
| Redundant indicators manufacture confidence | FeatureValidationCertificate + incremental gate + functional confluence |
| Browser prompt injection influences order | untrusted external data + T2 boundary + no execution capability |
| Research look-ahead | as-of discipline + leakage switch + immutable data manifests |
| Favorable hindsight teaches bypass of risk gate | Risk Authority rejection remains correct no-trade attribution |
| Schema migration hides logic change | mechanical logic-reference comparison + migration artifact |


---

# 44. Closure classification for new components

Every new component is classified precisely during implementation.

`INTEGRATED_AND_EVIDENCED` requires all of:

```text
producer
consumer
production caller
tests
runtime evidence
```

External blocks must name the exact missing artefact. `deployment` is not an acceptable residual description.

Fail-closed absence is not capability-complete. A feature that safely refuses because a source is absent is **safe**, not **available**.

---

# 45. Proposed component-ledger additions

Add/update rows as implementation lands for:

```text
Trading timeframe identity
Required-feature contract
MultiTimeframeMarketState
Venue-aware Feature Registry
FeatureValidationCertificate
Functional Confluence Engine
StrategyValidationCertificate
CandidateOpportunity
AccountDecisionCoordinator
AccountRuntimeLease
CandidatePool
OpportunityPortfolioAllocator
PortfolioDependencyEngine
ExpectedShortfallEngine
StrategyOverlapDetector
ExecutionPolicyEngine
ExitPolicyResearchEngine
CapitalBudgetProposal
Per-strategy mandate budgets
AllocationEpisode learning
CapitalEfficiency intelligence
StrategyCoverageMap
FeatureDriftMonitor
EdgeDriftMonitor
TradingEvidenceCollector
MarketDataDisagreementDetector
```

Do not create terminal ledger rows before the real producer/consumer/caller exists.

---

# 46. Producer / consumer / production-caller matrix

| Component | Producer | Consumer | Production caller |
|---|---|---|---|
| Timeframe identity | state/MTF builder | ledger, arbiter, trade detail | `InstrumentEvaluator` |
| FeatureContractVerdict | `FeatureContractValidator` | `StrategyArbiter` | `InstrumentEvaluator.evaluate` |
| MTF state | MTF assembler | strategy/context layer | `InstrumentEvaluator` |
| Feature certificate | validation pipeline | feature/capsule admission | research certification workflow |
| Strategy certificate | validation pipeline | `CapsuleRegistry.promote` | owner promotion workflow |
| CandidateOpportunity | `InstrumentEvaluator` | `CandidatePool` | coordinator evaluation cycle |
| CandidatePool | instrument evaluators | allocator | `AccountDecisionCoordinator` |
| AllocationDecision | allocator | `IntentFactory`, ledger, read model | coordinator candidate loop |
| Dependency snapshot | dependency engine | allocator / intent factory | coordinator candidate loop |
| `correlation_multiplier` | dependency snapshot | Risk Authority sizing | `IntentFactory` |
| ExecutionPolicyDecision | execution-policy engine | Router | coordinator after RiskDecision |
| AllocationEpisode | coordinator/outcome join | allocator research | learning/research cycle |
| CapitalBudgetProposal | capital-promotion analysis | owner UI / approval path | research/scheduled workflow |
| TradingEvidenceArtifact | browser evidence collector | VTIL/T2 research | research workflow only |

This matrix is not evidence. The final component ledger records actual paths and callers.

---

# 47. Counterexample closure matrix

## Timeframe identity

**False green:** `timeframe` field exists but canonical hash omits it.  
**Must fail:** identical M5/H1 values cannot share state hash.

## Required features

**False green:** startup validates requirements, later live data loses one, strategy still trades.  
**Must fail:** per-pass missing feature causes abstention.

## MTF

**False green:** H4 role declared but implementation quietly reuses H1 bars.  
**Must fail:** constituent slice/timeframe provenance checked and hashed.

## Feature validation

**False green:** MACD and PPO independently pass against a baseline containing neither and both are admitted.  
**Must fail:** second redundant member compared incrementally over the first admitted member.

## Strategy certificate

**False green:** owner signed promotion, evidence refs are arbitrary strings.  
**Must fail:** certificate semantic fields/hash mismatch refuses promotion.

## Account coordinator

**False green:** multiple evaluator classes exist, live service only calls one.  
**Must fail:** real service pass invokes all configured symbols and emits candidates.

## Candidate pool

**False green:** candidates stored, allocator receives only latest symbol.  
**Must fail:** two symbols coexist in one allocation epoch.

## Allocator

**False green:** ranking logged, first-arriving candidate still bypasses allocator into Risk Authority.  
**Must fail:** bypass mutation caught.

## Shared heat

**False green:** all candidates sized from one pre-allocation snapshot.  
**Must fail:** first execution changes second candidate's RiskDecision.

## Dependency engine

**False green:** dependency snapshot exists but `correlation_multiplier` remains `1`.  
**Must fail:** high-dependency scenario carries reduced multiplier into Risk Authority.

## Execution policy

**False green:** execution-policy decision logged but Router always sends `LIMIT`.  
**Must fail:** order command reflects selected certified template.

## Exit research

**False green:** research variant updates live `ProtectionManager`.  
**Must fail:** no production call path from exit research into live protection mutation.

## Capital proposal

**False green:** proposal object can invoke internal mandate update.  
**Must fail:** only owner-signed mandate path can change budget.

## Browser evidence

**False green:** browser fact appears in explanation and directly changes requested risk.  
**Must fail:** browser evidence can never increase risk or mint an intent.

---

# 48. Mutation-suite extensions

Add deliberate mutations that must be killed:

```text
DSR threshold 0.95 → 0
remove timeframe from state hash
skip required-feature validator
ignore stale required feature
allow unsupported venue feature
admit redundant feature pair without incremental comparison
remove certificate check from capsule promotion
allow arbitrary evidence refs without semantic certificate
let InstrumentEvaluator create TradeIntent directly
bypass CandidatePool
bypass allocator
allow allocator to set requested_risk_pct
reuse one RiskSnapshot for all candidates
remove candidate TTL
remove lease_epoch fence
set correlation_multiplier > 1
treat missing covariance as zero dependency
hard-code Router entry_type after policy decision
allow exit research to call ProtectionManager
allow CapitalBudgetProposal to mutate mandate
remove owner-signature binding to validation_hash
allow browser evidence to call execution path
remove evidence TTL
remove AllocationEpisode hindsight guard
treat favorable risk-rejected candidate as allocator regret
swap target precedence: read expected_gross_move_pct when targets non-empty
rank Allocator V0 on confidence_score
persist per-bar MTF state as ledger events
conflate LEASE_STORE_UNREACHABLE with LEASE_REFUSED_HELD_BY_OTHER
write a trading table into the gateway schema
hard-code the DSR threshold outside validation policy
```

A surviving mutation is a real defect, not a nuisance to waive.

---

# 49. Test layers

## 49.1 Pure unit

```text
hashing
feature formulas
validators
ranking
Expected Shortfall math
execution template policy
certificate validation
```

## 49.2 Property / fuzz

```text
multiplier bounds
risk never above ceiling
candidate order determinism
hash determinism
no look-ahead
lease epoch monotonicity
```

## 49.3 Integration

```text
lake → MTF → feature contract → strategy → candidate
candidate pool → allocator → intent → RiskAuthority
RiskDecision → ExecutionPolicy → Router
```

## 49.4 Replay / backtest

```text
same data → same decisions
multi-symbol candidate competition
allocator walk-forward
portfolio dependency stress
```

## 49.5 Live-adapter simulation

Use Paper/fake broker for:

```text
fill
partial fill
reject
spread expansion
disconnect
stop reject
reconnect
```

## 49.6 Runtime qualification on `van-trading-core`

```text
systemd service
transactional store
real process lock + distributed lease
configured feeds
network failure
restart
resource pressure
```

## 49.7 Owner E2E

On Android Command Center:

```text
candidate appears
allocation reason appears
RiskDecision appears
certificate drill-down works
degraded truth is accurate
capital proposal cannot auto-apply
```

Backend tests alone cannot certify owner E2E.

---

# 50. CI gates

Extend current CI; do not create a disconnected enhancement workflow.

Required existing gates:

```text
python tools/ci/maturity_gate.py
python tools/ci/authority_map.py
python tools/ci/ledger_reconcile.py
python tools/audit/mutation_suite.py
```

Also run the full `trading/tests/` and contract suites.

Add contract/static guardrails for:

```text
new blueprint does not duplicate authority subjects
CandidateOpportunity has no approved-size field
InstrumentEvaluator has no broker-send method
PortfolioAllocator cannot import ExecutionRouter
CapitalBudgetProposal cannot mutate TradingMandate
browser research package cannot import trading execution adapters
```

Static source assertions are guardrails, not substitutes for production-path execution.

---

# 51. Authority-map plan

If the owner explicitly admits this blueprint, add only new subjects with implementation/tests already present where required by the gate.

Possible subjects:

```text
trading.market_state_timeframe_identity
trading.required_feature_contract
trading.feature_admission
trading.strategy_validation_evidence
trading.account_runtime_single_authority
trading.portfolio_candidate_allocation
trading.allocator_cannot_size
trading.capital_promotion_requires_owner
trading.execution_policy_is_template_bounded
```

Each entry names:

```text
owner
falsifiable statement
implemented_by
tested_by
finding/work-item linkage
```

---

# 52. Workstream register

Use deterministic IDs.

## Integrity

```text
TRD-ENH-001 DSR probability contract
TRD-ENH-002 PBO semantic promotion gate
TRD-ENH-003 required_features live contract
TRD-ENH-004 timeframe state identity
TRD-ENH-005 capsule schema migration verifier
```

## MTF / features

```text
TRD-ENH-010 TimeframeMarketState
TRD-ENH-011 MultiTimeframeMarketState
TRD-ENH-012 Feature Registry
TRD-ENH-013 FeatureValidationCertificate
TRD-ENH-014 Functional Confluence
TRD-ENH-015 ADX/DMI research
TRD-ENH-016 Donchian/Keltner research gate
TRD-ENH-017 MACD/PPO research gate
TRD-ENH-018 multi-horizon ROC
TRD-ENH-019 venue-gated volume
```

## Strategy validation

```text
TRD-ENH-020 StrategyValidationCertificate
TRD-ENH-021 capsule promotion integration
TRD-ENH-022 owner signature validation-hash binding
```

## Runtime / allocation

```text
TRD-ENH-030 CandidateOpportunity
TRD-ENH-031 OpportunityEngine candidate split
TRD-ENH-032 InstrumentEvaluator
TRD-ENH-033 CandidatePool
TRD-ENH-034 AccountDecisionCoordinator
TRD-ENH-035 distributed AccountRuntimeLease
TRD-ENH-036 Allocator V0
TRD-ENH-037 sequential fresh-snapshot heat procedure
TRD-ENH-038 AllocationEpisode
```

## Portfolio intelligence

```text
TRD-ENH-040 Factor Registry
TRD-ENH-041 PortfolioDependencyEngine
TRD-ENH-042 ExpectedShortfallEngine
TRD-ENH-043 correlation_multiplier integration
TRD-ENH-044 StrategyOverlapDetector
TRD-ENH-045 continuous volatility targeting research
```

## Execution / exits

```text
TRD-ENH-050 ExecutionPolicy templates
TRD-ENH-051 execution evidence aggregation
TRD-ENH-052 ExecutionPolicyDecision
TRD-ENH-053 Router integration
TRD-ENH-054 exit-path evidence
TRD-ENH-055 ExitPolicyResearchEngine
TRD-ENH-056 expanded counterfactual variants
```

## Capital

```text
TRD-ENH-060 per-strategy mandate budgets
TRD-ENH-061 CapitalBudgetProposal
TRD-ENH-062 owner mandate amendment binding
TRD-ENH-063 uncertainty edge floor
TRD-ENH-064 capital efficiency / risk-day
TRD-ENH-065 financing / rollover costs
TRD-ENH-066 Allocator V1
```

## Research / drift

```text
TRD-ENH-070 StrategyCoverageMap
TRD-ENH-071 RANGE research mission
TRD-ENH-072 FeatureDriftMonitor
TRD-ENH-073 EdgeDriftMonitor
TRD-ENH-074 TradingEvidenceCollector
TRD-ENH-075 MarketDataDisagreementDetector
TRD-ENH-076 MetaLabel calibration research
TRD-ENH-077 Champion/Challenger framework
```

## Owner / operations

```text
TRD-ENH-080 trading read-model extensions
TRD-ENH-081 Android market-intelligence UI
TRD-ENH-082 candidate/allocation UI
TRD-ENH-083 strategy validation UI
TRD-ENH-084 execution intelligence UI
TRD-ENH-085 capital proposal UI
TRD-ENH-086 degraded-state projection
TRD-ENH-087 observability
TRD-ENH-088 runtime qualification
TRD-ENH-089 soak / chaos certification
```

---

# 53. Phase order and hard gates

## 53.0 Which phases need owner adoption — [OWNER-DEFAULT]

```text
Phases 1-10, 12-15   NO new owner authority.
                     They strengthen existing owner-signed gates, add evidence, or
                     add reduce-only controls. Phase 3's certificates make an existing
                     owner signature harder to satisfy; they do not relocate authority.

Phase 11             OWNER ADOPTION REQUIRED (A4).
                     Per-strategy budgets introduce differentiated live ceilings.
                     This is the only phase that can raise what the system may risk.
```

Implementers SHALL NOT raise an approval request for phases other than 11 on authority grounds. Phase 2's
capsule rehash is a provenanced schema migration, not an authority change (§6.8).


## Phase 0 — baseline

Before changing code:

```text
fetch exact main
record SHA
run maturity gate
run authority map
run ledger reconcile
run full trading suite
run mutation suite baseline
inventory trading component ledger
```

No work starts from red baseline.

## Phase 1 — integrity prerequisites

`TRD-ENH-001..005`

Exit gate:

```text
DSR semantics correct
required_features fail closed
timeframe auditable
capsule migration proof exists
single-timeframe behavior preserved
```

## Phase 2 — MTF foundation

`TRD-ENH-010..011`

Exit gate:

```text
existing lake → multiple timeframe states → exact hashes
one existing strategy consumes compatibility layer
no new indicator required yet
```

## Phase 3 — validation evidence

`TRD-ENH-012..014`, `020..022`

Exit gate:

```text
feature certificate works
strategy certificate works
opaque promotion evidence refused
owner signature binds validation hash
```

## Phase 4 — candidate separation

`TRD-ENH-030..031`

Exit gate:

```text
single-symbol new path reproduces old behavior
CandidateOpportunity cannot reach Router
```

## Phase 5 — account coordinator

`TRD-ENH-032..035`

Exit gate:

```text
one authoritative coordinator per alias
multiple evaluators
cross-host lease fence
single order authority preserved
```

## Phase 6 — Allocator V0

`TRD-ENH-036..038`

Exit gate:

```text
two symbols coexist in candidate pool
merit order can beat arrival order
fresh RiskSnapshot per candidate
allocation evidence persisted
```

## Phase 7 — dependency / tail risk

`TRD-ENH-040..044`

Exit gate:

```text
correlation_multiplier no longer permanently 1
high-dependency candidate reduced/rejected
unknown dependency cannot fake independence
```

## Phase 8 — controlled feature expansion

`TRD-ENH-015..019`

Exit gate:

```text
at least one new feature passes incremental certificate
redundant-pair rule proven
venue semantics proven
```

## Phase 9 — execution intelligence

`TRD-ENH-050..053`

Exit gate:

```text
ExecutionPolicyDecision changes actual Router command within sealed template bounds
insufficient evidence falls back safely
```

## Phase 10 — exit research

`TRD-ENH-054..056`

Exit gate:

```text
research variants cannot mutate live protection
validated result produces capsule candidate only
```

## Phase 11 — capital promotion

`TRD-ENH-060..065`

Exit gate:

```text
per-strategy budgets exist
automation cannot raise them
proposal evidence bound
owner-signed mandate is only widening path
```

This phase requires explicit owner adoption because it introduces differentiated strategy ceilings.

## Phase 12 — Allocator V1

`TRD-ENH-066`

Exit gate: edge-floor, capital-efficiency, execution and dependency evidence enter ranking only after their own validation.

## Phase 13 — strategy research intelligence

`TRD-ENH-070..077`

Exit gate:

```text
coverage visible
RANGE researched, not assumed profitable
drift visible
browser evidence provenance complete
calibration remains shadow until certified
```

## Phase 14 — owner surface

`TRD-ENH-080..086`

Exit gate: owner can inspect selection, rejection, risk, execution and validation evidence from real ledger/read models.

## Phase 15 — production qualification

`TRD-ENH-087..089`

Exit gate:

```text
exact SHA
CI green
runtime qualification green
chaos/soak green
component ledger reconciled
authority map green
external residuals named
```

---

# 54. Dependency DAG

```text
DSR FIX ───────────────────────────────┐
                                      ├─ Strategy Certificate
TIMEFRAME ID ── MTF ──────────────────┤
                                      │
REQUIRED FEATURES ─ Feature Registry ─┼─ Feature Certificate ─ Feature Expansion
                                      │
MTF + Existing Strategy ─ Candidate Split
                                      │
                                      └─ InstrumentEvaluator
                                             │
Account Lease ───────────────────────────────┤
                                             └─ AccountCoordinator
                                                    │
CandidatePool ──────────────────────────────────────┤
                                                    └─ Allocator V0
                                                           │
Factor Registry ─ Dependency/ES ───────────────────────────┤
                                                           │
Execution Evidence ─ ExecutionPolicy ──────────────────────┤
                                                           │
Edge Floor + Capital Efficiency ───────────────────────────┤
                                                           └─ Allocator V1

Strategy Certificate + Owner A4 ─ Capital Promotion
```

No downstream task substitutes a stub for an unmet dependency.

---

# 55. Release / rollback strategy

Use explicit staged flags such as:

```text
mtf_state_enabled
feature_contract_enforced
candidate_pool_enabled
portfolio_allocator_enabled
dependency_engine_enabled
execution_policy_enabled
per_strategy_budget_enabled
```

A disabled enhancement falls back to previously certified behavior. No flag may disable Risk Authority, mandate, kill switch, reconciliation or protection.

Rollback must preserve readability of newly written ledger events and schema rows.

---

# 56. Performance budget

Measure:

```text
MTF assembly
feature contract
strategy evaluation
candidate update
allocation
dependency calculation
RiskAuthority
execution-policy selection
Router
```

Do not declare unsupported latency numbers. Establish hardware baselines on `van-trading-core`, then enforce regression bounds.

Heavy CPCV/DSR research, browser work and drift analytics remain outside T0.

---

# 57. Data retention and reproducibility

Retain enough evidence to reconstruct:

```text
why candidate existed
why it ranked where it did
why risk accepted/reduced/rejected
what execution policy ran
what later outcome occurred
```

Do not duplicate full market datasets into the ledger. Store hashes/references to immutable lake slices and manifests.

---

# 58. Credential / privacy boundary

No new artifact contains:

```text
broker passwords
API secrets
private signing keys
raw account credentials
```

Use account aliases. Browser research never receives broker execution credentials.

---

# 59. External research guardrails

The statistical direction is consistent with established work on Deflated Sharpe Ratio, PBO/CSCV, volatility scaling and Expected Shortfall/joint-tail risk. Those papers motivate research; they do not become live authority.

The 2025 BIS survey continues to characterize spot FX as an OTC, decentralized and fragmented market, supporting the blueprint's prohibition on presenting single-broker volume/DOM as universal FX market truth.

Every technique still requires VATI's own out-of-sample validation for the specific capsule/venue.

---

# 60. Production-complete definition

## Integrity

```text
DSR probability gate correct
PBO consumed
timeframe in hashes
required features fail closed
```

## MTF

```text
existing lake reused
no look-ahead
capsule migration proven
constituent states auditable
```

## Validation

```text
FeatureValidationCertificate production-gated
StrategyValidationCertificate promotion-gated
owner promotion binds evidence
```

## Runtime

```text
CandidateOpportunity weaker than TradeIntent
AccountDecisionCoordinator is live account entry point
multiple symbols evaluated
CandidatePool real
allocator real
fresh RiskSnapshot per candidate
distributed lease fences duplicate authority
```

## Portfolio risk

```text
correlation_multiplier populated by real dependency logic
Expected Shortfall evidence exists
unknown dependency not treated as independence
```

## Execution

```text
TCA evidence selects sealed execution template
Router uses actual selected template
fallback safe
```

## Exits

```text
research variants cannot mutate live protection
validated capsule revision required
```

## Capital

```text
per-strategy budgets bounded
automation cannot raise them
owner-signed mandate change is only widening path
```

## Research

```text
RANGE measured, not assumed profitable
feature/edge drift observable
browser evidence provenance-rich and non-actuating
```

## Owner surface

```text
selection/rejection/risk/execution explanations derive from stored evidence
degraded states truthful
```

## Closure machinery

```text
maturity gate green
authority map green
ledger reconcile green
mutation suite green
full trading tests green
exact-SHA CI green
runtime qualification green
component ledger honest
external residuals named
```

---

# 61. Final anti-gap checklist

Before any workstream is called complete:

```text
[ ] What requirement does this satisfy?
[ ] Which authority owns the invariant?
[ ] What code implements it?
[ ] What produces its input?
[ ] What consumes its output?
[ ] What real production caller reaches it?
[ ] What durable evidence proves it ran?
[ ] What does the owner observe?
[ ] What happens when its dependency is absent?
[ ] What happens when input is stale?
[ ] What happens after restart?
[ ] What happens with duplicate processes?
[ ] What happens under partial failure?
[ ] What happens when model/research is wrong?
[ ] Can learning widen authority indirectly?
[ ] Can browser/external content reach execution indirectly?
[ ] Can missing data look like zero risk?
[ ] Can an opaque evidence ref satisfy a semantic gate?
[ ] Can a stale candidate execute?
[ ] Can two candidates consume one stale heat snapshot?
[ ] Can a research variant mutate production?
[ ] Can a proposal mutate a mandate?
[ ] Can a second document claim the same invariant?
[ ] Does a mutation prove the test is load-bearing?
[ ] What exact counterexample falsifies closure?
[ ] Is each external blocker named precisely?
```

Unknown answer means not production-complete.

---

# 62. Final engineering directive

Implement these improvements as an evolution of existing VATI, not as a parallel AI trading system.

The finished architecture combines:

```text
better market-state fidelity
+ better feature discipline
+ better statistical validation
+ better cross-symbol capital selection
+ better portfolio dependency / tail-risk awareness
+ better execution policy
+ better exit research
+ better capital-efficiency measurement
+ better research provenance
+ better owner explanations
+ controlled owner-approved upside
```

while preserving:

```text
one Risk Authority
one order sender
one transactional authority truth
one owner-widening boundary
hash-chained evidence
fail-closed safety
backtest/live parity
```

> **VAN may become progressively more intelligent about where edge exists, how strong the evidence is, which opportunity deserves scarce portfolio capacity, how execution should be optimized, and where the system is leaving value on the table. It may not turn that intelligence into additional live authority by itself.**


---

# 63. Baseline preservation gates — PR #48 work that must not regress

Enhancement implementation must preserve the following already-closure-evidenced trading capabilities at the baseline.

## 63.1 Owner authority verification

Existing owner-signature verification is real cryptographic authority, not `non_empty_string == approved`.

Regression gate:

```text
old fake signature strings remain refused
act/subject scoping remains enforced
single-use owner act semantics remain enforced
```

Per-strategy capital-budget changes must reuse this authority, not invent a second signature format.

## 63.2 Live risk snapshot safety flags

Existing live snapshot fields such as reconciliation, risk-store health and Tier-1 blackout must remain produced from real state, not literals.

The AccountDecisionCoordinator refactor must not regress them while moving snapshot ownership to account scope.

## 63.3 Broker margin gates

Margin call, margin floor and free-margin gates remain real inputs to Risk Authority.

Portfolio allocation must never rank a candidate and then bypass the margin snapshot used by Risk Authority.

## 63.4 Owner halt durability

A restart must not forget an uncleared owner halt.

Coordinator restart tests must replay/observe the durable halt before admitting candidates.

## 63.5 Restart-safe idempotency

The current account/symbol/bar idempotency principle survives the candidate split.

New hierarchy:

```text
candidate identity
allocation identity
trade-intent identity
order-command identity
```

must remain deterministic across process restart where the economic decision is unchanged.

## 63.6 One process per account alias

The existing `SessionLock` protection remains; distributed lease strengthens rather than replaces it.

## 63.7 Live learning

The PR #48 closure wired learning into the live session. AccountCoordinator refactoring must preserve environment-appropriate learning and must not accidentally return learning to backtest-only reachability.

## 63.8 Strategy targets survive

The winning strategy's actual targets must continue into execution. The candidate/allocator split must carry the exact target tuple and may not reconstruct it from expected move except through the already-defined fallback semantics.

## 63.9 Trading ledger truth

Gateway/Android read models continue deriving trading truth from the hash-chained ledger. New candidate/allocation stores do not become alternative truth about whether an order happened.

## 63.10 T0 isolation

Neither browser nor automation fabric enters the tick-to-order route during this enhancement.

Any test that requires Stagehand/Hermes/n8n availability for a Risk Authority decision indicates an architecture regression.

---

# 64. Workstream evidence manifest template

Every `TRD-ENH-*` work item SHALL close with a machine-readable evidence record equivalent to:

```yaml
work_item: TRD-ENH-034
component: AccountDecisionCoordinator
repository_sha: <exact-sha>

requirement:
  source: VAN_TRADING_INTELLIGENCE_AND_PROFITABILITY_IMPROVEMENT_BLUEPRINT_REV_1
  section: 12

maturity:
  before: ABSENT
  after: INTEGRATED
  terminal_state: null

producer:
  path: trading/vati/app/service.py
  symbol: SessionService.build
  claim: constructs the coordinator for the configured account alias

consumer:
  path: trading/vati/app/account_coordinator.py
  symbol: AccountDecisionCoordinator.step
  claim: consumes per-symbol evaluator outputs and invokes allocation

production_caller:
  path: trading/vati/__main__.py
  symbol: cmd_serve
  ingress: systemd vati-session@<alias>

runtime_join:
  input: configured account with EURUSD and GBPUSD
  observed:
    - both evaluators ran
    - two candidate records shared one allocation epoch
    - exactly one RiskAuthority object owned account sizing

owner_projection:
  surface: Trading Command Center / Potential Trades
  state: allocation explanation visible

fail_closed:
  dependency_absent: no new orders
  stale_candidate: expires
  duplicate_coordinator: lease refusal

tests:
  - trading/tests/test_account_coordinator.py::test_two_symbols_compete_in_one_epoch
  - trading/tests/test_account_coordinator.py::test_fresh_snapshot_after_first_fill
  - trading/tests/test_account_coordinator.py::test_instrument_evaluator_cannot_execute

mutation:
  description: bypass allocator and send first candidate directly to IntentFactory
  expected: test suite fails
  result: KILLED

runtime_evidence:
  environment: van-trading-core
  artifact: evidence/trading-enhancement/TRD-ENH-034/runtime.json
  observed_sha: <exact-sha>

falsified_by:
  - only one configured evaluator is reached in the production service
  - two candidates never coexist
  - a candidate can reach Router without allocator/RiskAuthority

residual:
  class: null
  artifact_missing: null
```

A generated document or test name without an actual file/runtime observation is not evidence.

---

# 65. Implementation handoff rules for Opus / ChatGPT / Codex / human engineers

1. **Repository first.** Re-read current main before each phase. Do not implement against this document's old line numbers if source moved.
2. **No append-only correction documents.** Fix this blueprint in place or issue an explicit superseding revision; do not leave contradictory normative sections active.
3. **No orphan classes.** Every new class must have a production caller or be explicitly research/test-only.
4. **No hidden registries.** A registry with entries but no consuming path is `IMPLEMENTED_BUT_ISOLATED`.
5. **No fake live evidence.** Paper/backtest evidence is labelled as such and cannot certify broker/live behavior.
6. **No fake independent verification.** The component that acted cannot be its own independent verifier.
7. **No silent default semantics.** Unknown timeframe, unknown volume semantics, missing covariance, missing certificate and missing source provenance must not become optimistic defaults.
8. **No second order sender.** Any new package importing broker-send primitives requires explicit architecture review.
9. **No learned authority.** Review indirect paths, especially allocator learning, drift, execution learning and capital proposals.
10. **Run joins, not only units.** Test lake→MTF→candidate→allocation→RiskAuthority→Router and the owner readback.
11. **Run negative paths.** Missing data, stale data, duplicated runtime, wrong certificate, expired candidate, bad browser evidence, failed broker, partial fill.
12. **Update both truth registers.** Findings/work items and component ledger must reconcile before closure.
13. **Use exact SHA.** Runtime evidence that does not name the tested commit does not certify a later commit.
14. **Re-run the whole regression suite after every closure group.**
15. **Do not erase residuals to make the completion count green.**

---

# Appendix A — statistical / market-structure research basis

The implementation remains repository-authoritative, but these external research families motivate specific research gates:

- Bailey & López de Prado, *The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting, and Non-Normality* — motivation for DSR as probability-aware strategy validation rather than raw Sharpe thresholding.
- Bailey, Borwein, López de Prado & Zhu, *The Probability of Backtest Overfitting* — CSCV/PBO framework used to estimate selection-overfitting risk.
- Moreira & Muir, *Volatility-Managed Portfolios* — research motivation for testing reduce-only continuous volatility targeting; not evidence that a specific VATI capsule benefits.
- Bank for International Settlements, 2025 Triennial FX Survey / FX market analysis — current evidence that spot FX remains OTC, decentralized and fragmented, reinforcing source-semantics discipline for FX volume and depth features.

These sources motivate hypotheses. They do not override VATI validation or owner authority.

