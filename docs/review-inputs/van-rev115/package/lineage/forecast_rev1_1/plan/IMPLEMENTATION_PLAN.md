# Implementation plan — Revision 1.1

48 dependency-ordered child packets. Original IDs001–036 are preserved; added IDs037–048 occur before the existing backend closure. Numeric ID is not execution order.

All packets: `NOT_STARTED`. All application tests: `NOT_RUN`. No procurement task or additional live order sender.

### VAN-ML-PKT-001 — Source, branch and parent-programme reconciliation

**Stage:** PREDEVELOPMENT · **Owner:** VAN source owner and independent reviewer
**Depends on:** None
**Parent duties:** PRE-001, PRE-002

**Complete deliverables**

- Freeze main and every relevant feature-bearing candidate branch; compare parent Rev1.10 and current source
- Create function-level retain/adapt/replace/extend mapping, existing conformal and feature ownership, provider/asset scope and licence provenance
- Write proposed additive-to-parent requirement and packet patch without modifying signed parent inputs
- Reconcile prediction-market parent §8.2/§8.4/§8.5, VAN-NX-036 and actual NewsIngress/CalendarRecorder owners; keep source observations dated.

**Exit evidence**

- Independently reviewed no-loss mapping, source hashes and conflict register
- A missing inherited action or PR-only feature must invalidate the proposed merge

**External entry requirements:** Read-only preparation only.
**Requirements:** VAN-ML-REQ-001
**Acceptance contracts:** VAN-ML-AT-001-P, VAN-ML-AT-001-N
**Rollback:** Retain last qualified source/model/configuration and immutable evidence; withdraw only this packet's newly admitted capabilities on failure. Never roll back financial history or weaken existing risk controls.

---

### VAN-ML-PKT-002 — Target, data, consumer and acceptance contracts

**Stage:** PREDEVELOPMENT · **Owner:** Product owner, quant research and risk reviewer
**Depends on:** VAN-ML-PKT-001
**Parent duties:** PRE-002

**Complete deliverables**

- Admit TargetSpecs, cohort/universe definitions, permitted data, validation protocol and research budgets
- Resolve runtime consumers, status/error semantics, numerical boundaries and authority contracts
- Pre-register all required model families, tests, losses, baselines and final holdout access policy
- Apply current no-procurement and Netcup/Oracle owner scope; neither source licence purchases nor direct event-contract eligibility is a prerequisite for adapter/fixture development.

**Exit evidence**

- All affected owner decisions identified by exact scope and gate
- No unresolved START prerequisite hidden by a default; no application PASS claims

**External entry requirements:** Read-only preparation only.
**Requirements:** VAN-ML-REQ-002
**Acceptance contracts:** VAN-ML-AT-002-P, VAN-ML-AT-002-N
**Rollback:** Retain last qualified source/model/configuration and immutable evidence; withdraw only this packet's newly admitted capabilities on failure. Never roll back financial history or weaken existing risk controls.

---

### VAN-ML-PKT-003 — Independent extended F15 entry barrier

**Stage:** PREDEVELOPMENT_GATE · **Owner:** Independent DIAL predevelopment verifier
**Depends on:** VAN-ML-PKT-002
**Parent duties:** PRE-003

**Complete deliverables**

- Integrate amended requirements into the parent predevelopment evidence and obtain genuine independent F15 for the admitted source/scope
- Register all code-bearing child packets and parent dependency changes

**Exit evidence**

- Trusted issuer verifies exact source/scope and owner signature
- A generated JSON PASS, hash or this pack checker cannot issue F15

**External entry requirements:** Owner-admitted amended source/scope and completed preparation evidence; Independent trusted parent PRE-003 verifier available to issue F15; F15 is this gate outcome, not a prerequisite to issue itself
**Requirements:** VAN-ML-REQ-003
**Acceptance contracts:** VAN-ML-AT-003-P, VAN-ML-AT-003-N
**Rollback:** Retain last qualified source/model/configuration and immutable evidence; withdraw only this packet's newly admitted capabilities on failure. Never roll back financial history or weaken existing risk controls.

---

### VAN-ML-PKT-004 — Pinned dependencies and isolated research runtime

**Stage:** BACKEND · **Owner:** VAN forecasting engineering
**Depends on:** VAN-ML-PKT-003
**Parent duties:** BE-001, BE-033, BE-034

**Complete deliverables**

- Lock Qlib, LightGBM, NeuralForecast, XGBoost, Optuna, Feast/MLflow and transitive dependencies by tested version/hash
- Build separate CPU research/inference environments, wheel/architecture matrix, resource and network policy
- Register worker bootstrap, SBOM and safe model-parser compatibility

**Exit evidence**

- Actual train/export/load smoke with locked upstream libraries on an authorized VM
- Import-boundary tests reject heavy model imports and broker credentials in the T0 runtime

**External entry requirements:** Current independent parent PRE-003 F15; Exact source admission through parent BE-001
**Requirements:** VAN-ML-REQ-004
**Acceptance contracts:** VAN-ML-AT-004-P, VAN-ML-AT-004-N
**Rollback:** Retain last qualified source/model/configuration and immutable evidence; withdraw only this packet's newly admitted capabilities on failure. Never roll back financial history or weaken existing risk controls.

---

### VAN-ML-PKT-005 — Point-in-time market dataset and universe snapshots

**Stage:** BACKEND · **Owner:** VAN forecasting engineering
**Depends on:** VAN-ML-PKT-004
**Parent duties:** BE-008, BE-014, BE-015

**Complete deliverables**

- Implement immutable source vintages, availability clocks, calendars, instrument identity and point-in-time universe
- Join licensed market/news/expectation features without revised-future leakage; distinguish observed and reconstructed availability
- Materialize versioned Parquet research snapshots from the existing data owners

**Exit evidence**

- Replay a revision, delisting and late release: past snapshot remains unchanged
- Reject cross-venue collisions, incomplete bars and unknown-use entitlements

**External entry requirements:** Current independent parent PRE-003 F15; Exact source admission through parent BE-001
**Requirements:** VAN-ML-REQ-005, VAN-ML-REQ-006, VAN-ML-REQ-007
**Acceptance contracts:** VAN-ML-AT-005-P, VAN-ML-AT-005-N, VAN-ML-AT-006-P, VAN-ML-AT-006-N, VAN-ML-AT-007-P, VAN-ML-AT-007-N
**Rollback:** Retain last qualified source/model/configuration and immutable evidence; withdraw only this packet's newly admitted capabilities on failure. Never roll back financial history or weaken existing risk controls.

---

### VAN-ML-PKT-006 — Shared feature definitions and Feast parity

**Stage:** BACKEND · **Owner:** VAN forecasting engineering
**Depends on:** VAN-ML-PKT-005
**Parent duties:** BE-008, BE-018

**Complete deliverables**

- Extend existing FeatureRegistry and feature contracts; compile offline/online transformations from one version
- Implement lag/timeframe/peer expansion, fold-fitted preprocessing and aligned row masks
- Integrate scoped Feast feature views/materialization and deterministic local inference snapshots

**Exit evidence**

- Offline/online values and units match within declared tolerances
- Shift peer data, change column order or fit a scaler on validation: qualification fails

**External entry requirements:** Current independent parent PRE-003 F15; Exact source admission through parent BE-001
**Requirements:** VAN-ML-REQ-008, VAN-ML-REQ-009, VAN-ML-REQ-010
**Acceptance contracts:** VAN-ML-AT-008-P, VAN-ML-AT-008-N, VAN-ML-AT-009-P, VAN-ML-AT-009-N, VAN-ML-AT-010-P, VAN-ML-AT-010-N
**Rollback:** Retain last qualified source/model/configuration and immutable evidence; withdraw only this packet's newly admitted capabilities on failure. Never roll back financial history or weaken existing risk controls.

---

### VAN-ML-PKT-037 — Prediction-market scope, VM profiles and source capability contracts

**Stage:** BACKEND · **Owner:** VAN event-data and platform owners
**Depends on:** VAN-ML-PKT-004, VAN-ML-PKT-005
**Parent duties:** BE-003, BE-008, BE-014, BE-015, BE-033

**Complete deliverables**

- Implement reusable source/provider contracts with separate technical reachability, allowed data uses, observed terms reference and acquisition mode; no licence-purchase workflow or external spending.
- Provide Netcup and Oracle worker profiles, actual region/host metadata and Global DIAL placement; distinguish operator/account eligibility from machine location.
- Deliver a no-network fixture/replay path and real read-only adapter path using existing source permissions where established; unavailable access affects that source, never erases other engineering scope.

**Exit evidence**

- Positive adapter/replay calls and explicit source-unavailable readback through actual services; source access unresolved must not become a coding prerequisite.
- No country-spoofing, proxy workaround, account creation, trade credential requirement or inferred live permission.

**External entry requirements:** Current independent parent PRE-003 F15; Exact source admission through parent BE-001
**Requirements:** VAN-ML-REQ-061, VAN-ML-REQ-062
**Acceptance contracts:** VAN-ML-AT-061-P, VAN-ML-AT-061-N, VAN-ML-AT-062-P, VAN-ML-AT-062-N
**Rollback:** Withdraw only this component's new evidence/use binding; preserve historical forecasts, broker truth, existing protections and qualified fallback. Restore only compatible still-valid prior artifacts.

---

### VAN-ML-PKT-007 — Targets, executable labels and outcome provenance

**Stage:** BACKEND · **Owner:** VAN forecasting engineering
**Depends on:** VAN-ML-PKT-005, VAN-ML-PKT-006
**Parent duties:** BE-013, BE-022

**Complete deliverables**

- Build returns, setup-event, ranking, realized-volatility, cost and excursion targets with explicit label intervals
- Keep market observations, actual fills, synthetic controls, practice and counterfactual outcomes in separate namespaces
- Preserve candidate sampling, rejection reason and censoring to expose selection bias

**Exit evidence**

- Labels cannot mature before horizon/outcome availability
- Gross/net/cost conventions reconcile; future holding duration cannot become an entry feature

**External entry requirements:** Current independent parent PRE-003 F15; Exact source admission through parent BE-001
**Requirements:** VAN-ML-REQ-011, VAN-ML-REQ-012, VAN-ML-REQ-013
**Acceptance contracts:** VAN-ML-AT-011-P, VAN-ML-AT-011-N, VAN-ML-AT-012-P, VAN-ML-AT-012-N, VAN-ML-AT-013-P, VAN-ML-AT-013-N
**Rollback:** Retain last qualified source/model/configuration and immutable evidence; withdraw only this packet's newly admitted capabilities on failure. Never roll back financial history or weaken existing risk controls.

---

### VAN-ML-PKT-038 — Kalshi and comparison-provider ingestion, depth and history

**Stage:** BACKEND · **Owner:** VAN market-data ingestion owner
**Depends on:** VAN-ML-PKT-037
**Parent duties:** BE-003, BE-008, BE-014, BE-015

**Complete deliverables**

- Implement versioned REST pagination, public metadata/books/trades and historical-boundary reconciliation plus authenticated read-only stream support where available.
- Normalize exact fixed-point YES/NO bids; derive opposite asks, book depth and quote-quality metadata without float cash arithmetic.
- Persist idempotent events with provider time, received time, available_at, source revision and gap/late-message state; stream gaps force resnapshot before usability.

**Exit evidence**

- Contract-compatible positive integration plus pagination, archive handoff, reconnect, duplicate and precision counterexamples.
- Any genuine provider capture has explicit permission/method and timing provenance; fixtures never count as historical/live captures.

**External entry requirements:** Current independent parent PRE-003 F15; Exact source admission through parent BE-001
**Requirements:** VAN-ML-REQ-063, VAN-ML-REQ-064, VAN-ML-REQ-065, VAN-ML-REQ-066
**Acceptance contracts:** VAN-ML-AT-063-P, VAN-ML-AT-063-N, VAN-ML-AT-064-P, VAN-ML-AT-064-N, VAN-ML-AT-065-P, VAN-ML-AT-065-N, VAN-ML-AT-066-P, VAN-ML-AT-066-N
**Rollback:** Withdraw only this component's new evidence/use binding; preserve historical forecasts, broker truth, existing protections and qualified fallback. Restore only compatible still-valid prior artifacts.

---

### VAN-ML-PKT-039 — Event semantics, settlement and cross-venue equivalence

**Stage:** BACKEND · **Owner:** VAN EventRegistry and CalendarRecorder owners
**Depends on:** VAN-ML-PKT-037
**Parent duties:** BE-008, BE-014, BE-015, BE-016

**Complete deliverables**

- Add versioned event-contract definitions: exact proposition, units, comparator, thresholds, time window, timezone, official source/vintage, rounding, resolution, cancellation and dispute rules.
- Implement contract relation graph and reviewed exact/complement/overlap/non-equivalent mappings; semantic proposals from models cannot certify equivalence.
- Keep event occurrence, official publication, trade close and settlement as distinct states/clocks; corrected or cancelled outcomes create new versions and invalidation edges.

**Exit evidence**

- Same-title/different-rule, initial/revised-release, strict/inclusive threshold and settlement-delay cases produce distinct identities.
- Positive exact/complement mapping is usable in research with reviewed evidence; unresolved mapping is explicit, not a permanent empty implementation.

**External entry requirements:** Current independent parent PRE-003 F15; Exact source admission through parent BE-001
**Requirements:** VAN-ML-REQ-067, VAN-ML-REQ-068
**Acceptance contracts:** VAN-ML-AT-067-P, VAN-ML-AT-067-N, VAN-ML-AT-068-P, VAN-ML-AT-068-N
**Rollback:** Withdraw only this component's new evidence/use binding; preserve historical forecasts, broker truth, existing protections and qualified fallback. Restore only compatible still-valid prior artifacts.

---

### VAN-ML-PKT-008 — Chronological folds, lookahead and warmup diagnostics

**Stage:** BACKEND · **Owner:** VAN forecasting engineering
**Depends on:** VAN-ML-PKT-006, VAN-ML-PKT-007
**Parent duties:** BE-013, BE-019, BE-022

**Complete deliverables**

- Implement FoldPlan with interval purging, cohort-coherent cutoffs, calibration slices and embargo policy
- Build full-versus-prefix and positive-poison diagnostics inspired by Freqtrade
- Measure indicator/model feature convergence versus warmup and cache identity

**Exit evidence**

- Leakage, full-data normalization, random splits and future exogenous values are detected
- Overlapping horizons do not inflate independent sample counts

**External entry requirements:** Current independent parent PRE-003 F15; Exact source admission through parent BE-001
**Requirements:** VAN-ML-REQ-014, VAN-ML-REQ-015, VAN-ML-REQ-016
**Acceptance contracts:** VAN-ML-AT-014-P, VAN-ML-AT-014-N, VAN-ML-AT-015-P, VAN-ML-AT-015-N, VAN-ML-AT-016-P, VAN-ML-AT-016-N
**Rollback:** Retain last qualified source/model/configuration and immutable evidence; withdraw only this packet's newly admitted capabilities on failure. Never roll back financial history or weaken existing risk controls.

---

### VAN-ML-PKT-009 — Simulation accounting, intrabar and timing corrections

**Stage:** BACKEND · **Owner:** VAN forecasting engineering
**Depends on:** VAN-ML-PKT-005, VAN-ML-PKT-007
**Parent duties:** BE-006, BE-010, BE-012, BE-019

**Complete deliverables**

- Reproduce and close scoped main-source findings; implement observed intrabar ordering or explicit uncertainty bounds
- Debit commission, financing, borrow/roll and conversion costs exactly once alongside fill spread/slippage
- Produce post-liquidation MTM equity, drawdown and cash-flow-neutral performance with pending risk

**Exit evidence**

- Long/short both-hit, gap-stop, same-close latency, funding boundary and partial-fill cases reconcile
- Closed-trade metrics and pre-flatten final equity cannot certify economic performance

**External entry requirements:** Current independent parent PRE-003 F15; Exact source admission through parent BE-001
**Requirements:** VAN-ML-REQ-017, VAN-ML-REQ-018, VAN-ML-REQ-019
**Acceptance contracts:** VAN-ML-AT-017-P, VAN-ML-AT-017-N, VAN-ML-AT-018-P, VAN-ML-AT-018-N, VAN-ML-AT-019-P, VAN-ML-AT-019-N
**Rollback:** Retain last qualified source/model/configuration and immutable evidence; withdraw only this packet's newly admitted capabilities on failure. Never roll back financial history or weaken existing risk controls.

---

### VAN-ML-PKT-040 — Coherent event distributions, quality and probability features

**Stage:** BACKEND · **Owner:** VAN feature registry and probability intelligence owner
**Depends on:** VAN-ML-PKT-006, VAN-ML-PKT-038, VAN-ML-PKT-039
**Parent duties:** BE-014, BE-015, BE-016, BE-018

**Complete deliverables**

- Implement binary, mutually exclusive outcome and threshold distribution builders; explicit raw versus adjusted estimates, monotonicity, missing bins and open-tail policies.
- Register probability levels/changes, entropy, tail mass, dispersion, consensus differences, spread/depth and freshness as distinct features; fit all transforms on permitted history.
- Prevent artificial jumps at contract roll; compare aligned maturity/proposition only; preserve Kalshi/Polymarket agreement as consistency, not independent-probability multiplication.

**Exit evidence**

- Finite coherent full distributions, correctly differenced threshold masses, explicit unavailable/partial distributions and deterministic same-input outputs.
- Low-depth/outdated/crossed or mismatched books cannot become confident features through averaging or silent normalization.

**External entry requirements:** Current independent parent PRE-003 F15; Exact source admission through parent BE-001
**Requirements:** VAN-ML-REQ-069, VAN-ML-REQ-070, VAN-ML-REQ-071, VAN-ML-REQ-073
**Acceptance contracts:** VAN-ML-AT-069-P, VAN-ML-AT-069-N, VAN-ML-AT-070-P, VAN-ML-AT-070-N, VAN-ML-AT-071-P, VAN-ML-AT-071-N, VAN-ML-AT-073-P, VAN-ML-AT-073-N
**Rollback:** Withdraw only this component's new evidence/use binding; preserve historical forecasts, broker truth, existing protections and qualified fallback. Restore only compatible still-valid prior artifacts.

---

### VAN-ML-PKT-010 — Account-wide replay and execution-policy parity

**Stage:** BACKEND · **Owner:** VAN forecasting engineering
**Depends on:** VAN-ML-PKT-008, VAN-ML-PKT-009
**Parent duties:** BE-009, BE-010, BE-012, BE-019

**Complete deliverables**

- Replay through the shared account coordinator/risk/reservation/route policy, not only independent single-symbol cycles
- Build comparable event streams, symbol calendars, margin and instrument specifications
- Provide independent oracle export and documented comparator differences; no second live sender

**Exit evidence**

- Concurrent orders/cancel-fill races and capital contention have equivalent risk decisions
- Zero-trade replay does not stand in for exercised approval, rejection and protection paths

**External entry requirements:** Current independent parent PRE-003 F15; Exact source admission through parent BE-001
**Requirements:** VAN-ML-REQ-020, VAN-ML-REQ-021
**Acceptance contracts:** VAN-ML-AT-020-P, VAN-ML-AT-020-N, VAN-ML-AT-021-P, VAN-ML-AT-021-N
**Rollback:** Retain last qualified source/model/configuration and immutable evidence; withdraw only this packet's newly admitted capabilities on failure. Never roll back financial history or weaken existing risk controls.

---

### VAN-ML-PKT-011 — Qlib data, processor and recorder integration

**Stage:** BACKEND · **Owner:** VAN forecasting engineering
**Depends on:** VAN-ML-PKT-004, VAN-ML-PKT-006, VAN-ML-PKT-007, VAN-ML-PKT-008
**Parent duties:** BE-013, BE-022

**Complete deliverables**

- Implement VanQlibDataLoader and fold-scoped DataHandlerLP/DatasetH adapter over VAN-owned snapshots
- Register T3 training tasks and explicit Qlib Recorder/MLflow run binding
- Use model APIs only; disable Qlib execution/exchange and default equity-region semantics in VAN runtime

**Exit evidence**

- DK_L/DK_I separation, train-only processor fitting and prediction index identity verified
- Qlib default execution path and unrestricted YAML imports are rejected

**External entry requirements:** Current independent parent PRE-003 F15; Exact source admission through parent BE-001
**Requirements:** VAN-ML-REQ-022
**Acceptance contracts:** VAN-ML-AT-022-P, VAN-ML-AT-022-N
**Rollback:** Retain last qualified source/model/configuration and immutable evidence; withdraw only this packet's newly admitted capabilities on failure. Never roll back financial history or weaken existing risk controls.

---

### VAN-ML-PKT-012 — LightGBM expected-return and net-edge regressors

**Stage:** BACKEND · **Owner:** VAN forecasting engineering
**Depends on:** VAN-ML-PKT-011, VAN-ML-PKT-010
**Parent duties:** BE-013

**Complete deliverables**

- Train horizon/cohort-specific regression baselines with explicit cost conventions and objective semantics
- Export native Booster plus feature/target/preprocessor manifests
- Implement out-of-fold predictions, stopping, uncertainty comparison and diagnostic explanations

**Exit evidence**

- Reproducible fixed-environment fits; native export/import numerical equivalence
- Data/feature order mismatch and net-cost double subtraction fail tests

**External entry requirements:** Current independent parent PRE-003 F15; Exact source admission through parent BE-001
**Requirements:** VAN-ML-REQ-023
**Acceptance contracts:** VAN-ML-AT-023-P, VAN-ML-AT-023-N
**Rollback:** Retain last qualified source/model/configuration and immutable evidence; withdraw only this packet's newly admitted capabilities on failure. Never roll back financial history or weaken existing risk controls.

---

### VAN-ML-PKT-013 — LightGBM setup-event classification

**Stage:** BACKEND · **Owner:** VAN forecasting engineering
**Depends on:** VAN-ML-PKT-011, VAN-ML-PKT-010
**Parent duties:** BE-013

**Complete deliverables**

- Implement binary event targets and raw-probability output with defined censor/tie behavior
- Create disjoint calibration handoff, imbalance controls and reliability metadata
- Compare against event base rate and existing rules on the same candidate population

**Exit evidence**

- Class score is not called win probability until packet020 calibration passes
- Unmatured labels, resampling bias and leaked outcome fields fail

**External entry requirements:** Current independent parent PRE-003 F15; Exact source admission through parent BE-001
**Requirements:** VAN-ML-REQ-024
**Acceptance contracts:** VAN-ML-AT-024-P, VAN-ML-AT-024-N
**Rollback:** Retain last qualified source/model/configuration and immutable evidence; withdraw only this packet's newly admitted capabilities on failure. Never roll back financial history or weaken existing risk controls.

---

### VAN-ML-PKT-014 — LightGBM quantile and grouped ranking adapters

**Stage:** BACKEND · **Owner:** VAN forecasting engineering
**Depends on:** VAN-ML-PKT-011, VAN-ML-PKT-010
**Parent duties:** BE-013

**Complete deliverables**

- Implement VAN-owned Qlib-compatible/direct-LightGBM adapters for quantile and ranking objectives
- Train explicit alpha/horizon quantiles and grouped cutoff/universe ranking with integer relevance rules
- Validate quantile order, group contiguity and units; rank score remains ordinal

**Exit evidence**

- Stock LGBModel wrapper is not used with unsupported loss values
- Negative regression labels passed as rank relevance and cross-date groups are rejected

**External entry requirements:** Current independent parent PRE-003 F15; Exact source admission through parent BE-001
**Requirements:** VAN-ML-REQ-025, VAN-ML-REQ-026
**Acceptance contracts:** VAN-ML-AT-025-P, VAN-ML-AT-025-N, VAN-ML-AT-026-P, VAN-ML-AT-026-N
**Rollback:** Retain last qualified source/model/configuration and immutable evidence; withdraw only this packet's newly admitted capabilities on failure. Never roll back financial history or weaken existing risk controls.

---

### VAN-ML-PKT-015 — Challenger and simple baseline suite

**Stage:** BACKEND · **Owner:** VAN forecasting engineering
**Depends on:** VAN-ML-PKT-011, VAN-ML-PKT-010
**Parent duties:** BE-013, BE-022

**Complete deliverables**

- Integrate XGBoost as a comparable tabular challenger and linear/logistic/persistence/ranking baselines
- Include HAR-style realized-volatility and authorized GARCH implementations with identical data cutoffs
- Version each baseline and preserve failed/no-skill results

**Exit evidence**

- Every mandatory task has a meaningful naive and incumbent comparison
- Different horizons, price units, sample windows or costs cannot be compared as like-for-like

**External entry requirements:** Current independent parent PRE-003 F15; Exact source admission through parent BE-001
**Requirements:** VAN-ML-REQ-027
**Acceptance contracts:** VAN-ML-AT-027-P, VAN-ML-AT-027-N
**Rollback:** Retain last qualified source/model/configuration and immutable evidence; withdraw only this packet's newly admitted capabilities on failure. Never roll back financial history or weaken existing risk controls.

---

### VAN-ML-PKT-016 — NeuralForecast bridge and N-HiTS

**Stage:** BACKEND · **Owner:** VAN forecasting engineering
**Depends on:** VAN-ML-PKT-004, VAN-ML-PKT-006, VAN-ML-PKT-007, VAN-ML-PKT-008, VAN-ML-PKT-010
**Parent duties:** BE-013, BE-022

**Complete deliverables**

- Implement canonical unique_id/ds/y and historical/future/static exogenous mapping
- Integrate NHITS multi-horizon training, native validation and fold-scoped scaling
- Capture native outputs and learned preprocessing in the shared experiment/artifact contract

**Exit evidence**

- Actual locked-library training/inference on admitted data
- Calendar gaps, unavailable future values and scaler refits at prediction fail

**External entry requirements:** Current independent parent PRE-003 F15; Exact source admission through parent BE-001
**Requirements:** VAN-ML-REQ-028, VAN-ML-REQ-029
**Acceptance contracts:** VAN-ML-AT-028-P, VAN-ML-AT-028-N, VAN-ML-AT-029-P, VAN-ML-AT-029-N
**Rollback:** Retain last qualified source/model/configuration and immutable evidence; withdraw only this packet's newly admitted capabilities on failure. Never roll back financial history or weaken existing risk controls.

---

### VAN-ML-PKT-044 — Execution-realistic prediction-contract replay

**Stage:** BACKEND · **Owner:** VAN simulator and accounting owners
**Depends on:** VAN-ML-PKT-009, VAN-ML-PKT-010, VAN-ML-PKT-038, VAN-ML-PKT-039
**Parent duties:** BE-006, BE-009, BE-010, BE-011, BE-012, BE-019

**Complete deliverables**

- Extend the existing replay adapter family with decimal cash, depth/partial-fill logic, order activation/cancel timing, queue uncertainty and trade/bid/ask distinction.
- Bind versioned per-series/per-account fee precision and accumulator semantics; include settlement/dispute/cancel outcomes, venue cash reservations, financing and conversion costs where applicable.
- Keep all positions on one coherent event/book path and reconcile final liquidation/settlement equity; sparse history returns evidence limitations rather than guaranteed maker fills.

**Exit evidence**

- Deterministic accounting identities and counterexamples for touch-not-fill, queue loss, partial fill/cancel races, settlement delay and fee fragmentation.
- External-asset evaluation uses the actual destination broker model instead of charging hypothetical Kalshi trades.

**External entry requirements:** Current independent parent PRE-003 F15; Exact source admission through parent BE-001
**Requirements:** VAN-ML-REQ-081, VAN-ML-REQ-082
**Acceptance contracts:** VAN-ML-AT-081-P, VAN-ML-AT-081-N, VAN-ML-AT-082-P, VAN-ML-AT-082-N
**Rollback:** Withdraw only this component's new evidence/use binding; preserve historical forecasts, broker truth, existing protections and qualified fallback. Restore only compatible still-valid prior artifacts.

---

### VAN-ML-PKT-017 — N-BEATSx contextual forecasts and decomposition

**Stage:** BACKEND · **Owner:** VAN forecasting engineering
**Depends on:** VAN-ML-PKT-016
**Parent duties:** BE-013, BE-021

**Complete deliverables**

- Implement NBEATSx model plugin and valid exogenous capabilities
- Expose trend/seasonality/exogenous decomposition only when the chosen architecture supports it
- Measure contextual ablation and explanatory output stability

**Exit evidence**

- Actual contextual prediction and decomposition round trip
- Explanations cannot claim causal drivers or invent contributions for an unsupported configuration

**External entry requirements:** Current independent parent PRE-003 F15; Exact source admission through parent BE-001
**Requirements:** VAN-ML-REQ-030
**Acceptance contracts:** VAN-ML-AT-030-P, VAN-ML-AT-030-N
**Rollback:** Retain last qualified source/model/configuration and immutable evidence; withdraw only this packet's newly admitted capabilities on failure. Never roll back financial history or weaken existing risk controls.

---

### VAN-ML-PKT-018 — DeepAR distributional forecasts and retained scenarios

**Stage:** BACKEND · **Owner:** VAN forecasting engineering
**Depends on:** VAN-ML-PKT-016
**Parent duties:** BE-013, BE-019

**Complete deliverables**

- Integrate DeepAR distribution loss, target-domain checks and pinned RNG/sample manifests
- Retain individual trajectories through a tested adapter, or expose UNSUPPORTED_RAW_PATHS for a pinned API while implementing the documented retained-path adapter before closure
- Keep marginal intervals separate from temporal and cross-asset joint-scenario claims

**Exit evidence**

- Distribution support and raw-path dimensions verified with a real model
- Averaged trajectories cannot masquerade as samples; independent assets cannot claim joint portfolio coverage

**External entry requirements:** Current independent parent PRE-003 F15; Exact source admission through parent BE-001
**Requirements:** VAN-ML-REQ-031
**Acceptance contracts:** VAN-ML-AT-031-P, VAN-ML-AT-031-N
**Rollback:** Retain last qualified source/model/configuration and immutable evidence; withdraw only this packet's newly admitted capabilities on failure. Never roll back financial history or weaken existing risk controls.

---

### VAN-ML-PKT-045 — Contract-consistency and non-atomic arbitrage research laboratory

**Stage:** BACKEND · **Owner:** VAN research workflow and risk reviewer
**Depends on:** VAN-ML-PKT-039, VAN-ML-PKT-040, VAN-ML-PKT-044
**Parent duties:** BE-009, BE-012, BE-019, BE-021, BE-022

**Complete deliverables**

- Implement candidate discovery and exact payoff-state matrices for complementary and related contracts; title embeddings only shortlist candidates.
- Compute worst-case payout/net margin at executable quantities across success/void/cancel/dispute states; separate conditional payoff hedge from guaranteed real execution.
- Simulate venue-specific cash, collateral/currency haircut, settlement delay, partial first-leg fill, failed hedge and feasible unwind; do not assume cross-exchange atomicity or transferable immediate collateral.

**Exit evidence**

- Positive synthetic hedged-payoff case and near-match false-arbitrage/one-leg-failure cases with source-bound research reports.
- No new arbitrage order sender; cashflows and margin do not assume default-free settlement or fabricate a USD-stablecoin equivalence.

**External entry requirements:** Current independent parent PRE-003 F15; Exact source admission through parent BE-001
**Requirements:** VAN-ML-REQ-083, VAN-ML-REQ-084
**Acceptance contracts:** VAN-ML-AT-083-P, VAN-ML-AT-083-N, VAN-ML-AT-084-P, VAN-ML-AT-084-N
**Rollback:** Withdraw only this component's new evidence/use binding; preserve historical forecasts, broker truth, existing protections and qualified fallback. Restore only compatible still-valid prior artifacts.

---

### VAN-ML-PKT-019 — Contextual and multivariate neural challengers

**Stage:** BACKEND · **Owner:** VAN forecasting engineering
**Depends on:** VAN-ML-PKT-016, VAN-ML-PKT-017, VAN-ML-PKT-018
**Parent duties:** BE-013, BE-021, BE-022

**Complete deliverables**

- Provide usable research plugins for TFT, PatchTST and iTransformer with capability introspection and target compatibility
- Bound cross-market cohorts, missing histories, architecture-specific exogenous support and compute budgets
- Test each admitted plugin in training/export/load/inference; economic admission remains conditional

**Exit evidence**

- Do not infer support from constructor argument names alone
- Global shared weights are not labelled joint dependence, and invalid capabilities fail before training

**External entry requirements:** Current independent parent PRE-003 F15; Exact source admission through parent BE-001
**Requirements:** VAN-ML-REQ-032
**Acceptance contracts:** VAN-ML-AT-032-P, VAN-ML-AT-032-N
**Rollback:** Retain last qualified source/model/configuration and immutable evidence; withdraw only this packet's newly admitted capabilities on failure. Never roll back financial history or weaken existing risk controls.

---

### VAN-ML-PKT-020 — One calibration and uncertainty-validation boundary

**Stage:** BACKEND · **Owner:** VAN forecasting engineering
**Depends on:** VAN-ML-PKT-012, VAN-ML-PKT-013, VAN-ML-PKT-014, VAN-ML-PKT-015, VAN-ML-PKT-016, VAN-ML-PKT-017, VAN-ML-PKT-018, VAN-ML-PKT-019
**Parent duties:** BE-009, BE-013, BE-021

**Complete deliverables**

- Extend existing vati.risk.conformal through separate forecast calibration producers and source-bound buckets
- Implement probability calibration, quantile evaluation, optional conformalized intervals and realized coverage monitoring
- Bind residuals to model/target/cohort/horizon and invalidate on refit; correct guarantee language

**Exit evidence**

- Calibration/test separation and stale/mismatched residual refusal verified
- Nine residuals or nominal coverage alone cannot establish reliable trading confidence

**External entry requirements:** Current independent parent PRE-003 F15; Exact source admission through parent BE-001
**Requirements:** VAN-ML-REQ-033, VAN-ML-REQ-034, VAN-ML-REQ-035
**Acceptance contracts:** VAN-ML-AT-033-P, VAN-ML-AT-033-N, VAN-ML-AT-034-P, VAN-ML-AT-034-N, VAN-ML-AT-035-P, VAN-ML-AT-035-N
**Rollback:** Retain last qualified source/model/configuration and immutable evidence; withdraw only this packet's newly admitted capabilities on failure. Never roll back financial history or weaken existing risk controls.

---

### VAN-ML-PKT-021 — Unified Optuna and rolling research studies

**Stage:** BACKEND · **Owner:** VAN forecasting engineering
**Depends on:** VAN-ML-PKT-008, VAN-ML-PKT-011, VAN-ML-PKT-015, VAN-ML-PKT-019, VAN-ML-PKT-020
**Parent duties:** BE-013, BE-022, BE-028

**Complete deliverables**

- Use one study/budget/trial ledger for Qlib, native LightGBM and NeuralForecast candidates
- Implement bounded neural Auto/Optuna adapter, nested temporal selection and independent final holdout
- Preserve all tried configurations, early/pruned failures and comparison lineage

**Exit evidence**

- Search cannot observe final holdout or mutate live aliases
- Repeat study from snapshot and detect data, target, trial-count and environment changes

**External entry requirements:** Current independent parent PRE-003 F15; Exact source admission through parent BE-001
**Requirements:** VAN-ML-REQ-036
**Acceptance contracts:** VAN-ML-AT-036-P, VAN-ML-AT-036-N
**Rollback:** Retain last qualified source/model/configuration and immutable evidence; withdraw only this packet's newly admitted capabilities on failure. Never roll back financial history or weaken existing risk controls.

---

### VAN-ML-PKT-041 — Event calibration, grouped chronology and frozen surprise

**Stage:** BACKEND · **Owner:** Existing calibration and independent quant validation owners
**Depends on:** VAN-ML-PKT-008, VAN-ML-PKT-020, VAN-ML-PKT-040
**Parent duties:** BE-015, BE-016, BE-021, BE-022

**Complete deliverables**

- Extend existing calibration by event family, horizon and liquidity cohort; retain market-implied values separately from calibrated physical-event probabilities.
- Freeze admissible pre-release expectations and calculate surprise only once the correct official release becomes available; preserve every later revision separately.
- Group training/calibration/testing by underlying event and aligned cross-market folds; report event-effective sample size, proper scores and concentration, not inflated quote counts.

**Exit evidence**

- Positive matured-label/calibration workflow and real producer binding through existing service.
- Post-release input, correlated snapshots split randomly, unsupported probability claims and stale calibration fail qualification.

**External entry requirements:** Current independent parent PRE-003 F15; Exact source admission through parent BE-001
**Requirements:** VAN-ML-REQ-072, VAN-ML-REQ-074, VAN-ML-REQ-075
**Acceptance contracts:** VAN-ML-AT-072-P, VAN-ML-AT-072-N, VAN-ML-AT-074-P, VAN-ML-AT-074-N, VAN-ML-AT-075-P, VAN-ML-AT-075-N
**Rollback:** Withdraw only this component's new evidence/use binding; preserve historical forecasts, broker truth, existing protections and qualified fallback. Restore only compatible still-valid prior artifacts.

---

### VAN-ML-PKT-022 — Safe model artifacts and candidate registry

**Stage:** BACKEND · **Owner:** VAN forecasting engineering
**Depends on:** VAN-ML-PKT-004, VAN-ML-PKT-011, VAN-ML-PKT-020, VAN-ML-PKT-021
**Parent duties:** BE-013, BE-031, BE-033

**Complete deliverables**

- Implement native Booster and safe neural artifact formats with verified source/configuration/manifests
- Connect MLflow versions/runs and immutable VAN admission records; aliases remain advisory
- Implement atomic stage transitions, CAS deployment binding and rollback compatibility

**Exit evidence**

- No untrusted pickle, unapproved dynamic imports or unchecked remote model URI
- Changing registry alias cannot change admitted runtime model without a valid binding

**External entry requirements:** Current independent parent PRE-003 F15; Exact source admission through parent BE-001
**Requirements:** VAN-ML-REQ-037, VAN-ML-REQ-038
**Acceptance contracts:** VAN-ML-AT-037-P, VAN-ML-AT-037-N, VAN-ML-AT-038-P, VAN-ML-AT-038-N
**Rollback:** Retain last qualified source/model/configuration and immutable evidence; withdraw only this packet's newly admitted capabilities on failure. Never roll back financial history or weaken existing risk controls.

---

### VAN-ML-PKT-023 — Adaptive retraining scheduler and lifecycle

**Stage:** BACKEND · **Owner:** VAN forecasting engineering
**Depends on:** VAN-ML-PKT-021, VAN-ML-PKT-022
**Parent duties:** BE-013, BE-028, BE-033

**Complete deliverables**

- Implement FreqAI-inspired retraining cadence, drift-triggered jobs, expiry and per-scope queues
- Use existing durable workflow/scheduler owner, bounded retries, resumable checkpoints and worker leases
- Finish candidate fits without automatic promotion; prioritize inference/protection over training

**Exit evidence**

- Kill/restart trainer and duplicate trigger produce no duplicate publication
- Old model remains only while valid; training completion never means approved deployment

**External entry requirements:** Current independent parent PRE-003 F15; Exact source admission through parent BE-001
**Requirements:** VAN-ML-REQ-039, VAN-ML-REQ-040
**Acceptance contracts:** VAN-ML-AT-039-P, VAN-ML-AT-039-N, VAN-ML-AT-040-P, VAN-ML-AT-040-N
**Rollback:** Retain last qualified source/model/configuration and immutable evidence; withdraw only this packet's newly admitted capabilities on failure. Never roll back financial history or weaken existing risk controls.

---

### VAN-ML-PKT-024 — Forecast serving, cache, freshness and novelty gates

**Stage:** BACKEND · **Owner:** VAN forecasting engineering
**Depends on:** VAN-ML-PKT-006, VAN-ML-PKT-020, VAN-ML-PKT-022, VAN-ML-PKT-023
**Parent duties:** BE-008, BE-013, BE-031, BE-033

**Complete deliverables**

- Implement typed bounded ForecastService and immutable cache keys tied to actual material inputs
- Add model/data/calibration freshness, schema validation, DI-style novelty and optional SVM/DBSCAN/PCA ablations
- Persist accepted and abstained outputs with explicit reason and identity; no order fields

**Exit evidence**

- Timeout, corrupt model, OOD, stale feed, changed feature order and queue saturation return truthful abstention
- No synchronous network/model load can enter T0 risk or protection

**External entry requirements:** Current independent parent PRE-003 F15; Exact source admission through parent BE-001
**Requirements:** VAN-ML-REQ-041, VAN-ML-REQ-042, VAN-ML-REQ-043
**Acceptance contracts:** VAN-ML-AT-041-P, VAN-ML-AT-041-N, VAN-ML-AT-042-P, VAN-ML-AT-042-N, VAN-ML-AT-043-P, VAN-ML-AT-043-N
**Rollback:** Retain last qualified source/model/configuration and immutable evidence; withdraw only this packet's newly admitted capabilities on failure. Never roll back financial history or weaken existing risk controls.

---

### VAN-ML-PKT-025 — Forecast fusion, arbiter and mode evidence integration

**Stage:** BACKEND · **Owner:** VAN forecasting engineering
**Depends on:** VAN-ML-PKT-010, VAN-ML-PKT-012, VAN-ML-PKT-013, VAN-ML-PKT-014, VAN-ML-PKT-019, VAN-ML-PKT-020, VAN-ML-PKT-024
**Parent duties:** BE-009, BE-013, BE-016, BE-021

**Complete deliverables**

- Join forecasts into existing OpportunityEngine/MetaLabeler and account coordinator through versioned evidence inputs
- Train fusion only on OOF predictions, measure redundancy, preserve baseline fallback policies
- Bind independent economic admission producer to Normal/Risky/Aggressive use; never modify signed ceilings

**Exit evidence**

- Model disagreement, duplicate-signal confidence, missing edge and mid-cycle model change are handled
- Arbiter output still requires new TradeIntent, RiskSnapshot, RiskAuthority and sole router

**External entry requirements:** Current independent parent PRE-003 F15; Exact source admission through parent BE-001
**Requirements:** VAN-ML-REQ-044, VAN-ML-REQ-045, VAN-ML-REQ-046
**Acceptance contracts:** VAN-ML-AT-044-P, VAN-ML-AT-044-N, VAN-ML-AT-045-P, VAN-ML-AT-045-N, VAN-ML-AT-046-P, VAN-ML-AT-046-N
**Rollback:** Retain last qualified source/model/configuration and immutable evidence; withdraw only this packet's newly admitted capabilities on failure. Never roll back financial history or weaken existing risk controls.

---

### VAN-ML-PKT-026 — Instrument and strategy protection policies

**Stage:** BACKEND · **Owner:** VAN forecasting engineering
**Depends on:** VAN-ML-PKT-010, VAN-ML-PKT-025
**Parent duties:** BE-009, BE-012, BE-013

**Complete deliverables**

- Add native cooldown, stop-loss streak and low-profit suppression proposals inspired by Freqtrade
- Reuse existing drawdown/kill/health controls and resolve overlapping suppression deterministically
- Persist per-account/environment/strategy/instrument/direction state and reasons

**Exit evidence**

- Partial fills do not multiply loss counts; restarts cannot erase locks
- All entry blocks preserve authorized reductions, stop protection and manual control ownership

**External entry requirements:** Current independent parent PRE-003 F15; Exact source admission through parent BE-001
**Requirements:** VAN-ML-REQ-047
**Acceptance contracts:** VAN-ML-AT-047-P, VAN-ML-AT-047-N
**Rollback:** Retain last qualified source/model/configuration and immutable evidence; withdraw only this packet's newly admitted capabilities on failure. Never roll back financial history or weaken existing risk controls.

---

### VAN-ML-PKT-042 — Conditional asset-response models and forecast-stack integration

**Stage:** BACKEND · **Owner:** Qlib/LightGBM and NeuralForecast adapter owners
**Depends on:** VAN-ML-PKT-012, VAN-ML-PKT-013, VAN-ML-PKT-014, VAN-ML-PKT-017, VAN-ML-PKT-018, VAN-ML-PKT-024, VAN-ML-PKT-025, VAN-ML-PKT-041
**Parent duties:** BE-013, BE-015, BE-016, BE-021, BE-022

**Complete deliverables**

- Join point-in-time event features into existing Qlib tabular tasks and model-supported NeuralForecast historical exogenous inputs; future probability trajectories are never known covariates.
- Implement conditional asset-response targets for returns, volatility, adverse excursion and trade quality by instrument/horizon/session, with simple market/calendar baselines.
- Use out-of-fold predictions in fusion, measure incremental information beyond price/news/consensus inputs and preserve shared-source dependencies across model families.

**Exit evidence**

- Actual fitted-model export/load/inference on adequate permitted research data with predictions joined to exact available event snapshots.
- Event probability cannot be copied into asset-direction or trade-win probability; incapable NF configurations reject unsupported exogenous fields.

**External entry requirements:** Current independent parent PRE-003 F15; Exact source admission through parent BE-001
**Requirements:** VAN-ML-REQ-076, VAN-ML-REQ-077
**Acceptance contracts:** VAN-ML-AT-076-P, VAN-ML-AT-076-N, VAN-ML-AT-077-P, VAN-ML-AT-077-N
**Rollback:** Withdraw only this component's new evidence/use binding; preserve historical forecasts, broker truth, existing protections and qualified fallback. Restore only compatible still-valid prior artifacts.

---

### VAN-ML-PKT-027 — Outcome ledger, drift and proprietary learning data

**Stage:** BACKEND · **Owner:** VAN forecasting engineering
**Depends on:** VAN-ML-PKT-007, VAN-ML-PKT-023, VAN-ML-PKT-024, VAN-ML-PKT-025, VAN-ML-PKT-026
**Parent duties:** BE-012, BE-013, BE-022, BE-027

**Complete deliverables**

- Persist input-to-forecast-to-decision-to-outcome attribution and counterfactual separation
- Connect existing drift/health/replay and observed broker costs to candidate retraining requests
- Implement privacy/retention/correction invalidation, consented manual-trade datasets and no-survivor bias

**Exit evidence**

- Deletion/correction invalidates affected derived models without pretending unlearning
- Feature drift triggers candidate work or abstention, never unilateral risk expansion

**External entry requirements:** Current independent parent PRE-003 F15; Exact source admission through parent BE-001
**Requirements:** VAN-ML-REQ-048, VAN-ML-REQ-049
**Acceptance contracts:** VAN-ML-AT-048-P, VAN-ML-AT-048-N, VAN-ML-AT-049-P, VAN-ML-AT-049-N
**Rollback:** Retain last qualified source/model/configuration and immutable evidence; withdraw only this packet's newly admitted capabilities on failure. Never roll back financial history or weaken existing risk controls.

---

### VAN-ML-PKT-043 — Calibrated event value and bounded position evidence

**Stage:** BACKEND · **Owner:** VAN arbiter, risk and lifecycle owners
**Depends on:** VAN-ML-PKT-010, VAN-ML-PKT-025, VAN-ML-PKT-041, VAN-ML-PKT-042
**Parent duties:** BE-009, BE-011, BE-013, BE-015, BE-016, BE-017

**Complete deliverables**

- Implement external-asset evidence integration through inherited D1–D7 policies and preserve manual-position ownership, no stop widening, calendar blackouts and two-source armed expectations.
- Implement sandbox binary-contract value calculations for held-to-settlement and exit-before-settlement strategies with explicit depth/fees/currency/capital lockup; probabilities must be independently calibrated.
- Implement maximum-loss/event-family portfolio stress and constrained Kelly-style research comparisons; output only bounded proposals, never final authority, actual order instructions or self-promotion.

**Exit evidence**

- Positive admitted sandbox evidence consumed by risk evaluation and negative stale/unknown/wrong-use cases, with exact source and independent receipt bindings.
- No live event-contract adapter is registered; event-risk proposals cannot raise existing news multipliers or treat stop distance as maximum binary loss.

**External entry requirements:** Current independent parent PRE-003 F15; Exact source admission through parent BE-001
**Requirements:** VAN-ML-REQ-078, VAN-ML-REQ-079, VAN-ML-REQ-080
**Acceptance contracts:** VAN-ML-AT-078-P, VAN-ML-AT-078-N, VAN-ML-AT-079-P, VAN-ML-AT-079-N, VAN-ML-AT-080-P, VAN-ML-AT-080-N
**Rollback:** Withdraw only this component's new evidence/use binding; preserve historical forecasts, broker truth, existing protections and qualified fallback. Restore only compatible still-valid prior artifacts.

---

### VAN-ML-PKT-046 — Inventory-aware event market-making research laboratory

**Stage:** BACKEND · **Owner:** VAN microstructure research and risk reviewer
**Depends on:** VAN-ML-PKT-026, VAN-ML-PKT-041, VAN-ML-PKT-044
**Parent duties:** BE-009, BE-010, BE-012, BE-019, BE-021, BE-022

**Complete deliverables**

- Implement bounded inventory-aware two-sided quoting simulations with jump risk, time-to-event, event-family exposure, toxicity and fill-conditional expected value.
- Compare no-quote, fixed-spread and inventory-aware policies; measure queue dependence, inventory age, markout at several horizons, fee/rebate assumptions and cancel effectiveness.
- Implement research stop/quote-reduction on stale/gapped books and official-release risk; simulate pending cancels and retain exposure until confirmed. No spoofing/wash-trade logic or assumed special market-maker privileges.

**Exit evidence**

- Positive simulated quoting/fill/inventory roundtrip and adverse-selection/cancel-race/queue-loss stress evidence.
- Conditional value uses outcomes after actual modeled fills; unconditional spread capture or touched quotes do not qualify profitability.

**External entry requirements:** Current independent parent PRE-003 F15; Exact source admission through parent BE-001
**Requirements:** VAN-ML-REQ-085, VAN-ML-REQ-086
**Acceptance contracts:** VAN-ML-AT-085-P, VAN-ML-AT-085-N, VAN-ML-AT-086-P, VAN-ML-AT-086-N
**Rollback:** Withdraw only this component's new evidence/use binding; preserve historical forecasts, broker truth, existing protections and qualified fallback. Restore only compatible still-valid prior artifacts.

---

### VAN-ML-PKT-028 — Complete backend APIs and future-screen consumption

**Stage:** BACKEND · **Owner:** VAN forecasting engineering
**Depends on:** VAN-ML-PKT-024, VAN-ML-PKT-025, VAN-ML-PKT-026, VAN-ML-PKT-027
**Parent duties:** BE-020, BE-021, BE-022, BE-030, BE-031, BE-032

**Complete deliverables**

- Extend genuine gateway operations for forecasts, experiments, diagnostics, proposals, retraining and receipts
- Publish complete typed states/actions/eligibility/readback, cancellation and source-age contract
- Map all forecast features to existing Trading/Analyst/Strategy/Risk/Settings/Work surfaces without new frontend code

**Exit evidence**

- Real authenticated headless caller exercises every registered operation
- Uncalibrated scores never exposed as win probabilities; hidden unsupported flags cannot omit required functions

**External entry requirements:** Current independent parent PRE-003 F15; Exact source admission through parent BE-001
**Requirements:** VAN-ML-REQ-050, VAN-ML-REQ-051
**Acceptance contracts:** VAN-ML-AT-050-P, VAN-ML-AT-050-N, VAN-ML-AT-051-P, VAN-ML-AT-051-N
**Rollback:** Retain last qualified source/model/configuration and immutable evidence; withdraw only this packet's newly admitted capabilities on failure. Never roll back financial history or weaken existing risk controls.

---

### VAN-ML-PKT-047 — Prediction-market incremental-value and prospective study programme

**Stage:** BACKEND · **Owner:** Independent scientific/economic validation owner
**Depends on:** VAN-ML-PKT-021, VAN-ML-PKT-027, VAN-ML-PKT-042, VAN-ML-PKT-043, VAN-ML-PKT-044, VAN-ML-PKT-045, VAN-ML-PKT-046
**Parent duties:** BE-016, BE-021, BE-022, BQ-001, BQ-002, BQ-003

**Complete deliverables**

- Implement four frozen studies: pre-event risk, surprise interpretation, volatility and opportunity ranking, all paired against the same incumbent and exposure-matched/simple controls.
- Include dependency-aware uncertainty, trial census, event counts, publication/acquisition/execution lag tests, shuffled/lagged controls, full-account accounting and operating costs.
- Deliver prospective forecast sealing, outcome maturation and per-use decisions QUALIFIED/REJECTED/INCONCLUSIVE/UNAVAILABLE; useful context is not automatically trading edge.

**Exit evidence**

- Actual comparison/report pipelines with positive and deliberately no-edge fixtures; actual market claims require permitted untouched and prospective observations.
- Fewer trades or reduced capital alone cannot be advertised as superior intelligence; insufficient independent events remains inconclusive.

**External entry requirements:** Current independent parent PRE-003 F15; Exact source admission through parent BE-001
**Requirements:** VAN-ML-REQ-087, VAN-ML-REQ-088
**Acceptance contracts:** VAN-ML-AT-087-P, VAN-ML-AT-087-N, VAN-ML-AT-088-P, VAN-ML-AT-088-N
**Rollback:** Withdraw only this component's new evidence/use binding; preserve historical forecasts, broker truth, existing protections and qualified fallback. Restore only compatible still-valid prior artifacts.

---

### VAN-ML-PKT-029 — VM deployment, isolation, recovery and service operations

**Stage:** BACKEND · **Owner:** VAN forecasting engineering
**Depends on:** VAN-ML-PKT-022, VAN-ML-PKT-023, VAN-ML-PKT-024, VAN-ML-PKT-028
**Parent duties:** BE-033, BE-034

**Complete deliverables**

- Build approved VM service manifests with isolated users/quotas/secrets/network and capacity admission
- Exercise install, migration, backup/restore, rollback, model hot-swap and telemetry retention
- Use Global DIAL and Zuul routes; do not run on forbidden desktop or silently substitute local compute

**Exit evidence**

- Kill/pressure/full-disk/mismatched build and lost-receipt drills with actual services
- T0 deadline/protection noninterference and immutable ledger survival independently measured

**External entry requirements:** Current independent parent PRE-003 F15; Exact source admission through parent BE-001
**Requirements:** VAN-ML-REQ-052, VAN-ML-REQ-053
**Acceptance contracts:** VAN-ML-AT-052-P, VAN-ML-AT-052-N, VAN-ML-AT-053-P, VAN-ML-AT-053-N
**Rollback:** Retain last qualified source/model/configuration and immutable evidence; withdraw only this packet's newly admitted capabilities on failure. Never roll back financial history or weaken existing risk controls.

---

### VAN-ML-PKT-048 — Prediction-market consumers, operations and complete backend integration

**Stage:** BACKEND · **Owner:** VAN gateway, platform and independent integration reviewers
**Depends on:** VAN-ML-PKT-028, VAN-ML-PKT-029, VAN-ML-PKT-037, VAN-ML-PKT-038, VAN-ML-PKT-039, VAN-ML-PKT-040, VAN-ML-PKT-041, VAN-ML-PKT-042, VAN-ML-PKT-043, VAN-ML-PKT-044, VAN-ML-PKT-045, VAN-ML-PKT-046, VAN-ML-PKT-047
**Parent duties:** BE-003, BE-015, BE-016, BE-017, BE-030, BE-031, BE-032, BE-033, BE-034, BQ-001, BQ-005, BQ-006

**Complete deliverables**

- Wire all data, probability, comparison, research-lab and evidence states into existing APIs, capability catalogue, alerts, logs and later-screen contracts; no early frontend.
- Exercise Netcup/Oracle host profiles, endpoint changes, stream gaps, source revocation, disk/backlog pressure, restart, duplicate/unknown publication and schema rollback with no T0/provider network coupling.
- Provide honest per-source integration state and no-procurement development path; all mandatory backend/parent obligations remain visible and source-specific real-data gates cannot be replaced by fixtures.

**Exit evidence**

- Headless real-service positive/recovery/error readbacks; all new requirements join independent packet032 closure and parent033/BG-001.
- No background order enablement, licence purchase, new account, cloud bill, fixture-to-live promotion or false full-provider-ready claim.

**External entry requirements:** Current independent parent PRE-003 F15; Exact source admission through parent BE-001
**Requirements:** VAN-ML-REQ-089, VAN-ML-REQ-090
**Acceptance contracts:** VAN-ML-AT-089-P, VAN-ML-AT-089-N, VAN-ML-AT-090-P, VAN-ML-AT-090-N
**Rollback:** Withdraw only this component's new evidence/use binding; preserve historical forecasts, broker truth, existing protections and qualified fallback. Restore only compatible still-valid prior artifacts.

---

### VAN-ML-PKT-030 — Reproducible forecast and economic qualification reports

**Stage:** BACKEND_VERIFICATION · **Owner:** Independent quant validation
**Depends on:** VAN-ML-PKT-009, VAN-ML-PKT-010, VAN-ML-PKT-020, VAN-ML-PKT-021, VAN-ML-PKT-025, VAN-ML-PKT-026, VAN-ML-PKT-027, VAN-ML-PKT-047, VAN-ML-PKT-048
**Parent duties:** BQ-001, BQ-002, BQ-003

**Complete deliverables**

- Execute matched baseline/ablation/cost-stress/rank/return/volatility/calibration studies
- Build source-bound certificates from actual outputs, effective sample sizes and uncertainty; report rejected/inconclusive cases honestly
- Independently reproduce selected results and attach immutable artifact/dataset/config evidence

**Exit evidence**

- Positive, negative and no-edge reporting pathways all exercised
- No raw accuracy, favorable chart, in-sample fit or historic literature metric certifies VAN alpha

**External entry requirements:** Current independent parent PRE-003 F15; Exact source admission through parent BE-001
**Requirements:** VAN-ML-REQ-054
**Acceptance contracts:** VAN-ML-AT-054-P, VAN-ML-AT-054-N
**Rollback:** Retain last qualified source/model/configuration and immutable evidence; withdraw only this packet's newly admitted capabilities on failure. Never roll back financial history or weaken existing risk controls.

---

### VAN-ML-PKT-031 — Prospective shadow and controlled sandbox admission

**Stage:** BACKEND_VERIFICATION · **Owner:** Backend qualification team
**Depends on:** VAN-ML-PKT-028, VAN-ML-PKT-029, VAN-ML-PKT-030
**Parent duties:** BQ-001, BQ-002, BQ-003, BQ-005

**Complete deliverables**

- Exercise real incoming-data shadow recording and full sandbox train-to-inference-to-arbiter-to-paper lifecycle
- Test trusted sandbox admission, revocation, fallback and rollbacks without live financial authority
- Implement continuing prospective economic review windows and no-edge terminal decisions
- Include prediction-market per-source integration and frozen prospective expectations; source-unavailable cannot be reported as an actual Kalshi data qualification.

**Exit evidence**

- Same gateway/service path supplies genuine scoped receipts before BG
- A fixture-approved model cannot enter a live binding; real-paper evidence is not booked as live profit

**External entry requirements:** Current independent parent PRE-003 F15; Exact source admission through parent BE-001
**Requirements:** VAN-ML-REQ-055
**Acceptance contracts:** VAN-ML-AT-055-P, VAN-ML-AT-055-N
**Rollback:** Retain last qualified source/model/configuration and immutable evidence; withdraw only this packet's newly admitted capabilities on failure. Never roll back financial history or weaken existing risk controls.

---

### VAN-ML-PKT-032 — Independent additive backend closure

**Stage:** BACKEND_GATE · **Owner:** Independent Zuul and backend verifier
**Depends on:** VAN-ML-PKT-004, VAN-ML-PKT-005, VAN-ML-PKT-006, VAN-ML-PKT-007, VAN-ML-PKT-008, VAN-ML-PKT-009, VAN-ML-PKT-010, VAN-ML-PKT-011, VAN-ML-PKT-012, VAN-ML-PKT-013, VAN-ML-PKT-014, VAN-ML-PKT-015, VAN-ML-PKT-016, VAN-ML-PKT-017, VAN-ML-PKT-018, VAN-ML-PKT-019, VAN-ML-PKT-020, VAN-ML-PKT-021, VAN-ML-PKT-022, VAN-ML-PKT-023, VAN-ML-PKT-024, VAN-ML-PKT-025, VAN-ML-PKT-026, VAN-ML-PKT-027, VAN-ML-PKT-028, VAN-ML-PKT-029, VAN-ML-PKT-030, VAN-ML-PKT-031, VAN-ML-PKT-037, VAN-ML-PKT-038, VAN-ML-PKT-039, VAN-ML-PKT-040, VAN-ML-PKT-041, VAN-ML-PKT-042, VAN-ML-PKT-043, VAN-ML-PKT-044, VAN-ML-PKT-045, VAN-ML-PKT-046, VAN-ML-PKT-047, VAN-ML-PKT-048
**Parent duties:** BQ-006

**Complete deliverables**

- Audit every requirement, real provider/model integration, registered consumer and failure/recovery record
- Verify source/runtime identity, no unclosed mandatory implementation gaps and all selected model plugins operational
- Issue independent additive technical closure only through the genuine trusted authority
- Include all12 prediction-market backend packets, all30 added requirements, research labs, real consumer paths and truthful source-specific limitations.

**Exit evidence**

- All backend requirements/tests trace to source-bound results, not this document checker
- Economic rejection is distinct from missing software; false-complete mutation must fail

**External entry requirements:** Current independent parent PRE-003 F15; Exact source admission through parent BE-001
**Requirements:** VAN-ML-REQ-056
**Acceptance contracts:** VAN-ML-AT-056-P, VAN-ML-AT-056-N
**Rollback:** Retain last qualified source/model/configuration and immutable evidence; withdraw only this packet's newly admitted capabilities on failure. Never roll back financial history or weaken existing risk controls.

---

### VAN-ML-PKT-033 — Parent BG-001 integration and renewed contract baseline

**Stage:** BACKEND_GATE · **Owner:** Parent programme admission owner
**Depends on:** VAN-ML-PKT-032
**Parent duties:** BE-032, BQ-006, BG-001

**Complete deliverables**

- Merge additive evidence and catalogue into parent units and regenerate exact whole-product scope/contract hashes
- Require every original parent backend obligation plus this additive before parent BG-001
- Produce frontend consumption handoff; do not self-issue the global certificate
- Apply the supplied prediction-market parent delta under actual independent admission; preserve VAN-NX-036, OD-14, D1–D7 and original parent IDs.

**Exit evidence**

- No additive-only receipt can unlock parent UX
- Existing backend/parent requirement removal, signature substitution or affected stale receipt blocks entry

**External entry requirements:** Current independent parent PRE-003 F15; Exact source admission through parent BE-001
**Requirements:** VAN-ML-REQ-057
**Acceptance contracts:** VAN-ML-AT-057-P, VAN-ML-AT-057-N
**Rollback:** Retain last qualified source/model/configuration and immutable evidence; withdraw only this packet's newly admitted capabilities on failure. Never roll back financial history or weaken existing risk controls.

---

### VAN-ML-PKT-034 — Post-BG complete native forecast surfaces

**Stage:** FRONTEND · **Owner:** VAN Android and design owner
**Depends on:** VAN-ML-PKT-033
**Parent duties:** UX-001, UX-002, UX-003, FE-006, FE-007, FE-008, FE-009, FE-011, FE-012, FE-014, FE-015, FE-018, FE-019, FE-020, FE-022, FE-013

**Complete deliverables**

- After current BG and parent UX acceptance, implement every mapped projection/control in the locked two-theme design
- Deliver context-specific uncertainty, source age, model/strategy distinction, experiment and review flows
- No dashboards on Home by default, no mobile training or broker authority in charts
- Complete News/Event context, probability/source-age, frozen expectation, research payoff/quote diagnostics and per-use evidence readbacks without enabling live event-contract trading.

**Exit evidence**

- Both-theme/state/action parity, accessibility, lifecycle and offline restoration
- Model version changes and stale bands never leave an enabled misleading action

**External entry requirements:** Current parent BG-001 covering this additive; Parent UX and frontend predecessor receipts applicable to the mapped surface
**Requirements:** VAN-ML-REQ-058
**Acceptance contracts:** VAN-ML-AT-058-P, VAN-ML-AT-058-N
**Rollback:** Retain last qualified source/model/configuration and immutable evidence; withdraw only this packet's newly admitted capabilities on failure. Never roll back financial history or weaken existing risk controls.

---

### VAN-ML-PKT-035 — Whole-product physical and independent final qualification

**Stage:** FINAL_QUALIFICATION · **Owner:** Independent app/device reviewer
**Depends on:** VAN-ML-PKT-034
**Parent duties:** QA-001, QA-002, QA-003, QA-004, QA-005

**Complete deliverables**

- Run actual signed-app/gateway/provider round trips, physical S24 performance and accessibility acceptance
- Verify original and additive action coverage, telemetry privacy and all recovery cases
- Obtain independent owner acceptance without replacing parent evidence

**Exit evidence**

- Physical device evidence cannot be substituted by emulator or headless tests
- Removing any inherited or additive action fails coverage

**External entry requirements:** Current parent BG-001 covering this additive; Parent UX and frontend predecessor receipts applicable to the mapped surface
**Requirements:** VAN-ML-REQ-059
**Acceptance contracts:** VAN-ML-AT-059-P, VAN-ML-AT-059-N
**Rollback:** Retain last qualified source/model/configuration and immutable evidence; withdraw only this packet's newly admitted capabilities on failure. Never roll back financial history or weaken existing risk controls.

---

### VAN-ML-PKT-036 — Controlled software release and separate economic promotion

**Stage:** RELEASE · **Owner:** Owner release and risk authority
**Depends on:** VAN-ML-PKT-035
**Parent duties:** REL-001, REL-002

**Complete deliverables**

- Release only exact accepted software under owner-approved rollout and proven rollback
- Promote each economically qualified model/strategy/account/horizon separately using live mandate and prospective evidence
- Retire old presentation only after whole-product parity; retain evidence and qualified baseline fallback

**Exit evidence**

- Software release does not auto-enable new trading risk
- Rejected/inconclusive models remain available for research, disabled for consequential influence

**External entry requirements:** Current parent BG-001 covering this additive; Parent UX and frontend predecessor receipts applicable to the mapped surface
**Requirements:** VAN-ML-REQ-060
**Acceptance contracts:** VAN-ML-AT-060-P, VAN-ML-AT-060-N
**Rollback:** Retain last qualified source/model/configuration and immutable evidence; withdraw only this packet's newly admitted capabilities on failure. Never roll back financial history or weaken existing risk controls.

---
