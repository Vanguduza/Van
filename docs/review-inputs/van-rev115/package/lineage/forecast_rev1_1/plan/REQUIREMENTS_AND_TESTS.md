# Requirements and application acceptance contracts — Revision 1.1

90 mandatory engineering requirements;180 application acceptance contracts, all `NOT_RUN`. The original60 requirements and120 contracts are retained verbatim. Added requirements061–090 cover prediction-market adoption.

### VAN-ML-REQ-001 — Preserve inherited scope and branch improvements

Retain every mapped parent action and source-backed capability; no competing trading stack.

Packet: `VAN-ML-PKT-001` · Parent: PRE-001, PRE-002 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-001-P — POSITIVE — NOT_RUN**

Reconcile parent/source/candidate hashes and all touched functions.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-001-N — ADVERSARIAL — NOT_RUN**

Remove one inherited action or ignore a selected branch: scope admission fails.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-002 — Admit complete targets and market scope

Resolve target units, cohorts, providers, required plugins, consumers and budget before implementation.

Packet: `VAN-ML-PKT-002` · Parent: PRE-002 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-002-P — POSITIVE — NOT_RUN**

Admit an internally coherent research profile and signed scope references.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-002-N — ADVERSARIAL — NOT_RUN**

An unspecified live budget or data entitlement cannot be filled with a guessed value.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-003 — Respect independent F15 and backend-first authority

No code-bearing child may start before current parent F15 and source admission; frontend also requires global BG.

Packet: `VAN-ML-PKT-003` · Parent: PRE-003 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-003-P — POSITIVE — NOT_RUN**

Validate actual external gate receipt with trusted issuer at execution.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-003-N — ADVERSARIAL — NOT_RUN**

A local PASS JSON or document hash alone fails entry.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-004 — Lock tested libraries and isolate computation

Produce reproducible environment manifests and actual VM compatibility evidence without loading training stacks in T0.

Packet: `VAN-ML-PKT-004` · Parent: BE-001, BE-033, BE-034 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-004-P — POSITIVE — NOT_RUN**

Train/export/load a small actual locked model on authorized infrastructure.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-004-N — ADVERSARIAL — NOT_RUN**

Unsupported wheel/architecture or missing quota blocks job admission.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-005 — Point-in-time source availability

Every feature source has event and availability timestamps, revision identity and provenance quality.

Packet: `VAN-ML-PKT-005` · Parent: BE-008, BE-014, BE-015 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-005-P — POSITIVE — NOT_RUN**

Late-arriving release stays absent until its observed availability cutoff.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-005-N — ADVERSARIAL — NOT_RUN**

Replace vintage data with revised future values: dataset validation fails.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-006 — Survivorship and instrument identity

Universe and contract membership are as-of; canonical identity includes venue and contract, not ticker alone.

Packet: `VAN-ML-PKT-005` · Parent: BE-008, BE-014, BE-015 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-006-P — POSITIVE — NOT_RUN**

Reproduce an historical cohort including subsequently delisted instruments.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-006-N — ADVERSARIAL — NOT_RUN**

Present-day universe or cross-venue ticker collision is detected.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-007 — Calendar and bar completeness

Use closed observed bars and per-market session/business-time horizons with gap policy.

Packet: `VAN-ML-PKT-005` · Parent: BE-008, BE-014, BE-015 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-007-P — POSITIVE — NOT_RUN**

DST, holiday and missing-bar fixtures preserve correct cutoff/horizon semantics.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-007-N — ADVERSARIAL — NOT_RUN**

Partial current candle or fabricated forward-filled tradability cannot enter fit.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-008 — Single feature definition and offline-online parity

Reuse the VAN feature owner, version transformations and materialize Feast views without alternate T0 authority.

Packet: `VAN-ML-PKT-006` · Parent: BE-008, BE-018 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-008-P — POSITIVE — NOT_RUN**

Replay identical snapshot through training and serving transforms.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-008-N — ADVERSARIAL — NOT_RUN**

Permute a feature column or change unit while keeping old manifest: reject.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-009 — Train-only transforms and aligned row masks

Fit scalers, PCA, feature selection and outlier transforms only inside training boundaries; preserve X/y/weight alignment.

Packet: `VAN-ML-PKT-006` · Parent: BE-008, BE-018 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-009-P — POSITIVE — NOT_RUN**

Apply a declared row filter and verify row IDs across features, targets and weights.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-009-N — ADVERSARIAL — NOT_RUN**

Validation-fitted scaler or independent target-row filtering fails.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-010 — Controlled feature expansion

Lag, timeframe, peer and calendar features use an admitted DAG and measured feature budget.

Packet: `VAN-ML-PKT-006` · Parent: BE-008, BE-018 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-010-P — POSITIVE — NOT_RUN**

Version added peer/lag features and compare their incremental contribution.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-010-N — ADVERSARIAL — NOT_RUN**

A negative feature shift or asynchronous future peer close fails prefix tests.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-011 — Target maturity and event semantics

Every label records interval, available_at, cost treatment, censoring and target version.

Packet: `VAN-ML-PKT-007` · Parent: BE-013, BE-022 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-011-P — POSITIVE — NOT_RUN**

Build an executable horizon label only after all required observations mature.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-011-N — ADVERSARIAL — NOT_RUN**

Post-entry holding duration presented as a known entry feature is rejected.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-012 — Separate facts, practice and counterfactuals

Do not mix actual fills, paper/practice, inferred outcomes and synthetic fixtures in promotion statistics.

Packet: `VAN-ML-PKT-007` · Parent: BE-013, BE-022 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-012-P — POSITIVE — NOT_RUN**

Build explicitly separated actual and counterfactual cohort reports.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-012-N — ADVERSARIAL — NOT_RUN**

A practice record promoted to live outcome provenance fails.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-013 — Return, ranking, volatility and cost targets

Provide all requested target families with correct domain and units; no binary-option payoff guessed as linear return.

Packet: `VAN-ML-PKT-007` · Parent: BE-013, BE-022 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-013-P — POSITIVE — NOT_RUN**

Compare labels against independent hand calculations for admitted instrument classes.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-013-N — ADVERSARIAL — NOT_RUN**

Double cost deduction or invalid distribution support is detected.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-014 — Purged chronological validation

Purge overlapping label intervals across training/validation/calibration/test; synchronize cohort cutoffs.

Packet: `VAN-ML-PKT-008` · Parent: BE-013, BE-019, BE-022 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-014-P — POSITIVE — NOT_RUN**

Demonstrate disjoint information intervals while retaining lawful historical context.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-014-N — ADVERSARIAL — NOT_RUN**

Random time splits or labels extending through validation boundary fail.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-015 — Bias and warmup diagnostics

Build native lookahead/prefix and indicator-recursion checks; poison tests must demonstrate sensitivity.

Packet: `VAN-ML-PKT-008` · Parent: BE-013, BE-019, BE-022 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-015-P — POSITIVE — NOT_RUN**

A causal strategy is stable at identical cutoff after sufficient warmup.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-015-N — ADVERSARIAL — NOT_RUN**

Leaked future field, centered rolling window or full-data statistic changes prefix result.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-016 — Immutable final holdout and trial census

Pre-register holdout access and count architectures/features/horizons/calibrators tried, including failures.

Packet: `VAN-ML-PKT-008` · Parent: BE-013, BE-019, BE-022 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-016-P — POSITIVE — NOT_RUN**

A single final evaluation references the frozen study census.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-016-N — ADVERSARIAL — NOT_RUN**

Second tuning pass on observed holdout without a new untouched period is blocked.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-017 — Direction-neutral intrabar uncertainty

Use observed subbars/ticks or declared feasible market scenarios; never claim a long-only path is conservative for all sides.

Packet: `VAN-ML-PKT-009` · Parent: BE-006, BE-010, BE-012, BE-019 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-017-P — POSITIVE — NOT_RUN**

Both stop and target touched: long and short and mixed portfolio ambiguity are explicit.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-017-N — ADVERSARIAL — NOT_RUN**

Independent contradictory paths presented as one portfolio market history fail.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-018 — Economic cost and valuation accounting

Debit monetary costs once and use realizable prices, latency, partial fills and post-liquidation equity.

Packet: `VAN-ML-PKT-009` · Parent: BE-006, BE-010, BE-012, BE-019 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-018-P — POSITIVE — NOT_RUN**

Commission, funding, gap and final close reconcile to ledger cash and MTM.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-018-N — ADVERSARIAL — NOT_RUN**

Risk cost estimate substituted for P&L deductions or pre-flatten final equity fails.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-019 — Flow-adjusted and open-position risk metrics

Preserve cash-flow-neutral performance and current collateral/MTM drawdown as separate measurements.

Packet: `VAN-ML-PKT-009` · Parent: BE-006, BE-010, BE-012, BE-019 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-019-P — POSITIVE — NOT_RUN**

Deposit changes collateral but not historical trading return; open loss appears in MTM drawdown.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-019-N — ADVERSARIAL — NOT_RUN**

Deposit erases loss, withdrawal is labelled trading loss or closed-only DD certifies exposure: fail.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-020 — Account-wide research-live parity

Use the real account coordinator and policy interfaces with isolated execution and reservation state.

Packet: `VAN-ML-PKT-010` · Parent: BE-009, BE-010, BE-012, BE-019 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-020-P — POSITIVE — NOT_RUN**

Concurrent candidates contend for the same simulated risk/capital budget.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-020-N — ADVERSARIAL — NOT_RUN**

Independent symbol backtests summed as a feasible portfolio result fail.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-021 — Nonvacuous deterministic evidence

Determinism concerns specified events/decisions, not just final trade count or zero-checked replay.

Packet: `VAN-ML-PKT-010` · Parent: BE-009, BE-010, BE-012, BE-019 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-021-P — POSITIVE — NOT_RUN**

Approval, reduction, rejection, expiry and protection paths are all replayed.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-021-N — ADVERSARIAL — NOT_RUN**

Zero checked decisions reported as full successful decision coverage fail.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-022 — Qlib model boundary and processor configuration

Use custom VAN data handlers; configure processor fitting, DK_L/DK_I and Recorder explicitly; no Qlib execution runtime.

Packet: `VAN-ML-PKT-011` · Parent: BE-013, BE-022 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-022-P — POSITIVE — NOT_RUN**

Compare indexed predictions and train-only preprocessing against the source dataset.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-022-N — ADVERSARIAL — NOT_RUN**

Qlib regional exchange defaults or dynamic unapproved YAML classes fail startup.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-023 — LightGBM regression production adapter

Implement per-target/horizon expected-return/net-edge models and native export with exact transform manifest.

Packet: `VAN-ML-PKT-012` · Parent: BE-013 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-023-P — POSITIVE — NOT_RUN**

Fit/infer/reload under fixed environment and compare predictions.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-023-N — ADVERSARIAL — NOT_RUN**

Feature-order, objective, target or cost-basis mismatch rejects the artifact.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-024 — Calibratable setup classification

Implement binary target models with defined population and raw-probability semantics before separate calibration.

Packet: `VAN-ML-PKT-013` · Parent: BE-013 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-024-P — POSITIVE — NOT_RUN**

Evaluate raw output against base rates on the same candidate population.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-024-N — ADVERSARIAL — NOT_RUN**

Class weighting/resampling output advertised as calibrated probability fails.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-025 — Quantile adapter completeness

Implement separate quantile/horizon objectives outside unsupported stock Qlib loss API.

Packet: `VAN-ML-PKT-014` · Parent: BE-013 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-025-P — POSITIVE — NOT_RUN**

Fit requested alpha models and validate ordered quantiles on evaluation data.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-025-N — ADVERSARIAL — NOT_RUN**

Pass quantile into stock Qlib LGBModel loss, or accept crossed quantiles without handling: fail.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-026 — Grouped ranking correctness

Train ranking with cutoff/universe query groups and appropriate nonnegative relevance coding; report ordinal scores.

Packet: `VAN-ML-PKT-014` · Parent: BE-013 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-026-P — POSITIVE — NOT_RUN**

Verify group sizes/ordering sum to rows and rank metrics use the same cohort.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-026-N — ADVERSARIAL — NOT_RUN**

Continuous negative return labels or cross-time query group leak are rejected.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-027 — Meaningful baseline and challenger comparisons

Implement XGBoost and simple/statistical incumbents against identical targets and calendars.

Packet: `VAN-ML-PKT-015` · Parent: BE-013, BE-022 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-027-P — POSITIVE — NOT_RUN**

Report matched loss, cost and coverage comparisons with sample counts.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-027-N — ADVERSARIAL — NOT_RUN**

Compare different horizons or omit a stronger simple baseline to claim victory: fail.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-028 — NeuralForecast shared data contract

Map unique_id/ds/y and exogenous inputs with immutable cutoffs and fold-scoped scalers.

Packet: `VAN-ML-PKT-016` · Parent: BE-013, BE-022 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-028-P — POSITIVE — NOT_RUN**

Round-trip aligned panel data and verify output identity and dimensions.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-028-N — ADVERSARIAL — NOT_RUN**

Duplicate timestamps, unseen cohort semantics or predictor-time scaler refit fail.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-029 — N-HiTS complete research integration

Implement real NHITS training, multi-horizon inference, model persistence and shared provenance.

Packet: `VAN-ML-PKT-016` · Parent: BE-013, BE-022 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-029-P — POSITIVE — NOT_RUN**

Execute train/export/reload/infer/evaluate on admitted real historical data.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-029-N — ADVERSARIAL — NOT_RUN**

An import-only plugin or canned forecast cannot close this requirement.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-030 — N-BEATSx contextual and interpretability integration

Implement supported exogenous inputs and optional native decomposition with noncausal explanations.

Packet: `VAN-ML-PKT-017` · Parent: BE-013, BE-021 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-030-P — POSITIVE — NOT_RUN**

Ablate contextual covariates and compare forecast/decomposition before and after reload.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-030-N — ADVERSARIAL — NOT_RUN**

Future actual releases, unavailable decomposition or fabricated causal labels fail.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-031 — DeepAR distribution and path integration

Implement domain-valid distributions and retained individual temporal samples with seeds.

Packet: `VAN-ML-PKT-018` · Parent: BE-013, BE-019 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-031-P — POSITIVE — NOT_RUN**

Compare raw sample tensor, aggregation and original-domain output calculations.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-031-N — ADVERSARIAL — NOT_RUN**

A mean path or independently sampled marginal quantiles labelled joint scenarios fails.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-032 — Complete challenger plugin interfaces

Implement TFT, PatchTST and iTransformer research plugins, gated by verified per-model capability matrix.

Packet: `VAN-ML-PKT-019` · Parent: BE-013, BE-021, BE-022 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-032-P — POSITIVE — NOT_RUN**

Each plugin completes actual train/export/load/infer and reports unsupported inputs before fit.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-032-N — ADVERSARIAL — NOT_RUN**

Constructor field presence alone used as proof of exogenous support fails.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-033 — Reuse existing conformal ownership

Extend existing vati.risk.conformal and source-bound calibration producer; no independent sizing permission.

Packet: `VAN-ML-PKT-020` · Parent: BE-009, BE-013, BE-021 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-033-P — POSITIVE — NOT_RUN**

Old deterministic conformal consumers retain semantics and new buckets enforce identity.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-033-N — ADVERSARIAL — NOT_RUN**

New library calibration silently replaces existing risk policy or raises size: fail.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-034 — Honest probability and interval calibration

Validate disjoint calibration, empirical coverage and adequacy; label marginal/conditional limitations.

Packet: `VAN-ML-PKT-020` · Parent: BE-009, BE-013, BE-021 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-034-P — POSITIVE — NOT_RUN**

Evaluate reliability, Brier/log loss or quantile coverage by horizon/cohort with uncertainty.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-034-N — ADVERSARIAL — NOT_RUN**

Nominal coverage or mathematical minimum residual count used as economic qualification fails.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-035 — Calibration lineage and tail semantics

Bind calibration to exact model/transform/target; avoid unsupported joint-tail, stop-touch and transformed-mean claims.

Packet: `VAN-ML-PKT-020` · Parent: BE-009, BE-013, BE-021 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-035-P — POSITIVE — NOT_RUN**

Refit invalidates the old calibrator; inverse-transform uncertainty is checked.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-035-N — ADVERSARIAL — NOT_RUN**

Sum marginal quantiles or exponentiate log-mean as arithmetic expectation without correction: fail.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-036 — One bounded optimization control

Use one Optuna/trial budget across Qlib/NF; all optimization only creates candidates.

Packet: `VAN-ML-PKT-021` · Parent: BE-013, BE-022, BE-028 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-036-P — POSITIVE — NOT_RUN**

Pause/resume a study and retain failed/pruned trial history and immutable inputs.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-036-N — ADVERSARIAL — NOT_RUN**

Parallel untracked studies or direct writes to live model binding fail.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-037 — Safe artifact and supply-chain boundary

Use native LightGBM and vetted safe neural formats; allowlisted loaders verify immutable bytes.

Packet: `VAN-ML-PKT-022` · Parent: BE-013, BE-031, BE-033 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-037-P — POSITIVE — NOT_RUN**

Corrupted/tampered model is rejected before deserialization and fallback is recorded.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-037-N — ADVERSARIAL — NOT_RUN**

Untrusted pickle, arbitrary import or unchecked remote URI fails.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-038 — Registry is not authority

MLflow aliases and experiment status never grant forecast influence or strategy promotion.

Packet: `VAN-ML-PKT-022` · Parent: BE-013, BE-031, BE-033 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-038-P — POSITIVE — NOT_RUN**

Admit an exact version through independently verified binding and CAS epoch.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-038-N — ADVERSARIAL — NOT_RUN**

Alias swap or attacker-authored certificate leaves active model unchanged.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-039 — Durable adaptive retraining

Implement per-scope jobs, cadence/drift triggers, leases, retries, checkpoints and safe cancellation.

Packet: `VAN-ML-PKT-023` · Parent: BE-013, BE-028, BE-033 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-039-P — POSITIVE — NOT_RUN**

Restart at each job state and recover without duplicate model publication.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-039-N — ADVERSARIAL — NOT_RUN**

Training finished marks model live or expired model used while waiting: fail.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-040 — Prevent schedule and resource starvation

Coalesce obsolete retrains with explicit receipts, bound queue/threads and protect serving/T0 capacity.

Packet: `VAN-ML-PKT-023` · Parent: BE-013, BE-028, BE-033 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-040-P — POSITIVE — NOT_RUN**

Burst retraining requests produce bounded pending work and measured noninterference.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-040-N — ADVERSARIAL — NOT_RUN**

Heavy study admitted using stale capacity or no budget is refused.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-041 — Typed forecast service and complete provenance

Emit ForecastPacket or abstention with scope, cutoffs, target, model, transformation and source evidence.

Packet: `VAN-ML-PKT-024` · Parent: BE-008, BE-013, BE-031, BE-033 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-041-P — POSITIVE — NOT_RUN**

Authenticated caller receives correct horizon/scalar/quantile identities.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-041-N — ADVERSARIAL — NOT_RUN**

NaN, Infinity, wrong account/venue, order quantity or executable instruction fails.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-042 — Independent freshness and OOD checks

Validate model age, data age, calibration age and novelty as separate dimensions.

Packet: `VAN-ML-PKT-024` · Parent: BE-008, BE-013, BE-031, BE-033 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-042-P — POSITIVE — NOT_RUN**

Old-but-freshly-served model and new prediction over stale data both fail as appropriate.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-042-N — ADVERSARIAL — NOT_RUN**

Novelty score labelled probability or tail observations silently deleted to improve metrics: fail.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-043 — Nonblocking inference and immutable cache

Preload admitted artifacts and cache by all material identities; T0 never awaits training/registry/network.

Packet: `VAN-ML-PKT-024` · Parent: BE-008, BE-013, BE-031, BE-033 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-043-P — POSITIVE — NOT_RUN**

Service timeout returns bounded abstention and protection continues.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-043-N — ADVERSARIAL — NOT_RUN**

Cache reused after target/model/feature/adjustment revision is rejected.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-044 — OOF-only forecast fusion and redundancy control

Learn combination only from out-of-fold predictions and track shared information across models.

Packet: `VAN-ML-PKT-025` · Parent: BE-009, BE-013, BE-016, BE-021 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-044-P — POSITIVE — NOT_RUN**

Ablate each model and compare against strongest single incumbent on matched outcomes.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-044-N — ADVERSARIAL — NOT_RUN**

Duplicated correlated signals counted as independent confirmation fail.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-045 — Preserve trading and financial authority

Models propose evidence only; only existing RiskAuthority sizes and ExecutionRouter sends orders.

Packet: `VAN-ML-PKT-025` · Parent: BE-009, BE-013, BE-016, BE-021 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-045-P — POSITIVE — NOT_RUN**

Every consequential decision retains exact mandate/risk/intent/route receipt.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-045-N — ADVERSARIAL — NOT_RUN**

Forecast tries to widen stop, raise ceilings, submit order or alter funds: reject.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-046 — Independent edge evidence and mode integration

Supply real economic-evidence producer and signed scope binding for Normal/Risky/Aggressive policy use.

Packet: `VAN-ML-PKT-025` · Parent: BE-009, BE-013, BE-016, BE-021 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-046-P — POSITIVE — NOT_RUN**

Sandbox admission and refusal both execute through genuine consumer paths.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-046-N — ADVERSARIAL — NOT_RUN**

Aggressive solely on model confidence, unbound evidence or wrong environment fails.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-047 — Complementary suppression without duplicate risk governor

Implement per-instrument/strategy cooldown and loss/profit protections through existing risk controls.

Packet: `VAN-ML-PKT-026` · Parent: BE-009, BE-012, BE-013 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-047-P — POSITIVE — NOT_RUN**

Deduplicated losses, persistent locks and defined session expiry reproduce after restart.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-047-N — ADVERSARIAL — NOT_RUN**

Protection suppresses authorized exits, counts fills as separate trades or resets on restart: fail.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-048 — Outcome attribution and scientific data moat

Join all eligible candidates and model outputs to observed decisions/outcomes and label unobserved counterfactuals.

Packet: `VAN-ML-PKT-027` · Parent: BE-012, BE-013, BE-022, BE-027 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-048-P — POSITIVE — NOT_RUN**

A rejected candidate remains in analysis with counterfactual status and missing actual fills.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-048-N — ADVERSARIAL — NOT_RUN**

Only profitable executed candidates retained or paper outcomes relabelled real fails.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-049 — Privacy and correction propagation

Respect entitlements/consent; invalidate downstream datasets/models when affected source is corrected/revoked.

Packet: `VAN-ML-PKT-027` · Parent: BE-012, BE-013, BE-022, BE-027 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-049-P — POSITIVE — NOT_RUN**

Trace a revoked manual-data source to features, models, caches and public projections.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-049-N — ADVERSARIAL — NOT_RUN**

Delete a row and claim model unlearning or keep revoked model active: fail.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-050 — Every capability has a genuine caller and readback

Publish complete catalog/actions/error states and actual gateway operations without new frontend implementation.

Packet: `VAN-ML-PKT-028` · Parent: BE-020, BE-021, BE-022, BE-030, BE-031, BE-032 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-050-P — POSITIVE — NOT_RUN**

Headless owner-scoped caller executes each operation and reads durable outcome.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-050-N — ADVERSARIAL — NOT_RUN**

Only a unit function, fake API or missing cancel/readback cannot close backend capability.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-051 — Truthful confidence and explanation surfaces

Keep raw rank/rule score, calibrated event probability, intervals and economic evidence distinct.

Packet: `VAN-ML-PKT-028` · Parent: BE-020, BE-021, BE-022, BE-030, BE-031, BE-032 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-051-P — POSITIVE — NOT_RUN**

Projection identifies calibration population, sample, horizon, expiry and limitations.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-051-N — ADVERSARIAL — NOT_RUN**

Uncalibrated certainty, neural explanation as causality or stale band as current fails.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-052 — Authorized VM deployment and recovery

Use qualified Global DIAL/Zuul execution routes, exact source, resource admission and tested isolation.

Packet: `VAN-ML-PKT-029` · Parent: BE-033, BE-034 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-052-P — POSITIVE — NOT_RUN**

Actual staged services survive restart, backup/restore and compatible rollback.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-052-N — ADVERSARIAL — NOT_RUN**

Forbidden desktop/local substitution, broker keys in trainer or stale-source receipt fails.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-053 — Bounded capacity and observability

Measure real CPU/memory/latency/disk and keep risk/protection independent of research load.

Packet: `VAN-ML-PKT-029` · Parent: BE-033, BE-034 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-053-P — POSITIVE — NOT_RUN**

Overload, disk full and unavailable registry produce recorded safe backpressure.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-053-N — ADVERSARIAL — NOT_RUN**

Unbounded threads/logs/cache, exposed secrets or unmeasured T0 starvation fails.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-054 — Actual statistical and economic evaluation

Use matched OOS forecasts, costs, intervals, DSR/PBO where applicable and pre-registered uncertainty analysis.

Packet: `VAN-ML-PKT-030` · Parent: BQ-001, BQ-002, BQ-003 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-054-P — POSITIVE — NOT_RUN**

Recompute metrics from immutable prediction/outcome files independently.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-054-N — ADVERSARIAL — NOT_RUN**

Literature returns, arbitrary accuracy threshold or in-sample results used as VAN proof fail.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-055 — Real shadow pipeline and full rejection path

Exercise the real pipeline in shadow/sandbox and preserve prospective timestamped outcomes.

Packet: `VAN-ML-PKT-031` · Parent: BQ-001, BQ-002, BQ-003, BQ-005 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-055-P — POSITIVE — NOT_RUN**

Fit, serve, evaluate, sandbox-admit, revoke and reject through genuine services.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-055-N — ADVERSARIAL — NOT_RUN**

Only refusal stubs or a synthetic approval promoted to live cannot pass.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-056 — Independent complete additive backend closure

All mandatory backend engineering must have real source/service/caller/failure evidence.

Packet: `VAN-ML-PKT-032` · Parent: BQ-006 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-056-P — POSITIVE — NOT_RUN**

Independent audit enumerates every backend requirement and verifies authoritative receipts.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-056-N — ADVERSARIAL — NOT_RUN**

Machine-readable nonempty evidence arrays or this checker substituted for semantic qualification fail.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-057 — Global backend barrier and contract renewal

Integrate with all parent backend/BQ obligations; renew BG before any new UX/frontend.

Packet: `VAN-ML-PKT-033` · Parent: BE-032, BQ-006, BG-001 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-057-P — POSITIVE — NOT_RUN**

Parent verifies additive and original whole-product scope in one contract baseline.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-057-N — ADVERSARIAL — NOT_RUN**

Additive-only pass used to bypass incomplete original backend fails.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-058 — Complete post-backend UI integration

Apply every forecast capability/state/action in appropriate existing native screen families after BG.

Packet: `VAN-ML-PKT-034` · Parent: UX-001, UX-002, UX-003, FE-006, FE-007, FE-008, FE-009, FE-011, FE-012, FE-014, FE-015, FE-018, FE-019, FE-020, FE-022 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-058-P — POSITIVE — NOT_RUN**

Both themes, offline/restoration, cancellation and accessibility retain all mapped actions.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-058-N — ADVERSARIAL — NOT_RUN**

Crowded Home, hidden required capability or UI-coded domain rule fails.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-059 — Physical and whole-product final acceptance

Actual S24 and signed app use the qualified backend and preserve all inherited actions.

Packet: `VAN-ML-PKT-035` · Parent: QA-001, QA-002, QA-003, QA-004, QA-005 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-059-P — POSITIVE — NOT_RUN**

Physical lifecycle/performance/privacy and independent whole-product acceptance are recorded.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-059-N — ADVERSARIAL — NOT_RUN**

Emulator screenshot or backend contract proof offered as S24 acceptance fails.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-060 — Separate software release from live-model promotion

Release software by parent policy; live influence requires independent model/strategy/account admission and owner authority.

Packet: `VAN-ML-PKT-036` · Parent: REL-001, REL-002 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-060-P — POSITIVE — NOT_RUN**

A released app can honestly show a rejected model with zero live influence.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

**VAN-ML-AT-060-N — ADVERSARIAL — NOT_RUN**

Install success enables trading, retrospective gate weakens, or rollback deletes ledger history: fail.

Evidence: Exact source and environment identity; Input/fixture/data snapshot identity; Invoked actual component or service and assertion output; Independent review where required by the parent gate

### VAN-ML-REQ-061 — Separate deployment, source access and procurement

Record Netcup/Oracle execution profiles; no licence procurement or external spending in this phase; no inference that VM location establishes operator eligibility.

Packet: `VAN-ML-PKT-037` · Parent: BE-003, BE-008, BE-014, BE-015, BE-033 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-061-P — POSITIVE — NOT_RUN**

Build and select both VM deployment profiles with explicit source/capability states and no payment workflow.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

**VAN-ML-AT-061-N — ADVERSARIAL — NOT_RUN**

Changing execution_host to a permitted region must not set operator eligibility, purchase approval or source-use permission.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

### VAN-ML-REQ-062 — Non-blocking no-procurement development path

Provide implemented fixture/replay and provider-adapter paths; source-use status is scoped; absent purchased licence cannot block ordinary specification, coding or fixture validation.

Packet: `VAN-ML-PKT-037` · Parent: BE-003, BE-008, BE-014, BE-015, BE-033 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-062-P — POSITIVE — NOT_RUN**

Exercise full positive synthetic ingest-to-evidence flow with purchases disabled and explicit NOT_LIVE data labels.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

**VAN-ML-AT-062-N — ADVERSARIAL — NOT_RUN**

Do not require a purchased licence to run synthetic tests; do not relabel unknown source-use rights as an admitted real-data capture.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

### VAN-ML-REQ-063 — Versioned bounded read-only adapters

Implement allowlisted market-data REST and optional read-only streaming with pinned contract revisions, timeouts, rate budgets and cursor handling; no order/account mutations.

Packet: `VAN-ML-PKT-038` · Parent: BE-003, BE-008, BE-014, BE-015 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-063-P — POSITIVE — NOT_RUN**

Read complete paged synthetic and authorized-provider datasets with method/endpoint and schema version receipts.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

**VAN-ML-AT-063-N — ADVERSARIAL — NOT_RUN**

Injected order endpoint, redirect to credential host, unbounded paging or HTTP429 hot retry must be refused.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

### VAN-ML-REQ-064 — Point-in-time archive and live completeness

Store publication/receive/availability clocks and per-record historical cutoffs; dedupe and reconcile archive handoffs without inventing past receipt times.

Packet: `VAN-ML-PKT-038` · Parent: BE-003, BE-008, BE-014, BE-015 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-064-P — POSITIVE — NOT_RUN**

Union live/historical responses under overlap and moving boundaries with stable IDs and complete provenance.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

**VAN-ML-AT-064-N — ADVERSARIAL — NOT_RUN**

Dropped page or single shared archive cutoff cannot be silently accepted; reconstructed time cannot masquerade as actual availability.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

### VAN-ML-REQ-065 — Exact bid and ask conversion

Parse fixed-point price/quantity strings and derive YES asks from NO bids and vice versa; retain source book and executable depth.

Packet: `VAN-ML-PKT-038` · Parent: BE-003, BE-008, BE-014, BE-015 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-065-P — POSITIVE — NOT_RUN**

For YES bid0.42 and NO bid0.56 obtain YES ask0.44 and NO ask0.58 with correct quantities.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

**VAN-ML-AT-065-N — ADVERSARIAL — NOT_RUN**

Treating YES last trade as executable ask or performing currency calculations through rounded binary floats fails the contract.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

### VAN-ML-REQ-066 — Stream gap and sequence recovery

Apply sequence-aware deltas idempotently; gaps, negative resulting depth or duplicate mismatches force INVALID until full resynchronization.

Packet: `VAN-ML-PKT-038` · Parent: BE-003, BE-008, BE-014, BE-015 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-066-P — POSITIVE — NOT_RUN**

Replay snapshot/deltas, duplicate and restart; regain READY only after a consistent new snapshot.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

**VAN-ML-AT-066-N — ADVERSARIAL — NOT_RUN**

Out-of-order delta, missing sequence or stale cached depth must not continue providing usable liquidity.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

### VAN-ML-REQ-067 — Canonical event and proposition identity

Bind thresholds/comparators, units, timezones, official source/vintage and rules digest; distinguish exact, complement, overlapping and non-equivalent contracts.

Packet: `VAN-ML-PKT-039` · Parent: BE-008, BE-014, BE-015, BE-016 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-067-P — POSITIVE — NOT_RUN**

Resolve two reviewed identical propositions and explicit complement relation into a shared event mapping.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

**VAN-ML-AT-067-N — ADVERSARIAL — NOT_RUN**

Same headline with different rounding, observation date or revised-value rules cannot be treated as identical.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

### VAN-ML-REQ-068 — Resolution and cash settlement are separate

Track occurrence, release, close, provisional outcome, dispute/cancel and final settlement separately; corrections create versions.

Packet: `VAN-ML-PKT-039` · Parent: BE-008, BE-014, BE-015, BE-016 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-068-P — POSITIVE — NOT_RUN**

Process an official release, later correction and delayed settlement without rewriting issued forecasts or prematurely crediting cash.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

**VAN-ML-AT-068-N — ADVERSARIAL — NOT_RUN**

Event happened or market closed cannot be used as proof that a payout is final or funds are available.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

### VAN-ML-REQ-069 — Maturity-aware contract continuity

Key probability changes by event/proposition/horizon and explicit roll rule; missing successor contracts produce missing features.

Packet: `VAN-ML-PKT-040` · Parent: BE-014, BE-015, BE-016, BE-018 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-069-P — POSITIVE — NOT_RUN**

Forecast features remain stable when a next-meeting display rolls to a different underlying event.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

**VAN-ML-AT-069-N — ADVERSARIAL — NOT_RUN**

Subtracting different event contracts and reporting the difference as same-event repricing fails validation.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

### VAN-ML-REQ-070 — Coherent distributions without fabricated tails

Differentiate mutually exclusive bins from overlapping thresholds; monotonicity, mass, open-tail and adjustment policies are explicit.

Packet: `VAN-ML-PKT-040` · Parent: BE-014, BE-015, BE-016, BE-018 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-070-P — POSITIVE — NOT_RUN**

Convert decreasing threshold probabilities into disjoint masses; retain raw and adjusted distributions and tail assumptions.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

**VAN-ML-AT-070-N — ADVERSARIAL — NOT_RUN**

Summing overlapping threshold probabilities, silently normalizing missing bins or inventing a tail midpoint is rejected.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

### VAN-ML-REQ-071 — Quality-aware market-implied estimates

Track estimator type, depth, spread, age, activity and rule coherence separately from calibration; empty books produce missing observations.

Packet: `VAN-ML-PKT-040` · Parent: BE-014, BE-015, BE-016, BE-018 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-071-P — POSITIVE — NOT_RUN**

Produce mid/interval estimates only from valid two-sided books and admit eligible liquidity cohorts.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

**VAN-ML-AT-071-N — ADVERSARIAL — NOT_RUN**

Volume-only confidence, stale last trades, crossed books or empty levels cannot become high-confidence event probabilities.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

### VAN-ML-REQ-072 — Freeze expectations before official information

Link each surprise to the last genuinely available pre-release snapshot and official release vintage; no future availability.

Packet: `VAN-ML-PKT-041` · Parent: BE-015, BE-016, BE-021, BE-022 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-072-P — POSITIVE — NOT_RUN**

Issue immutable expectation snapshot then calculate a versioned surprise when official information arrives.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

**VAN-ML-AT-072-N — ADVERSARIAL — NOT_RUN**

Replacing the pre-release distribution with a post-release price or corrected value fails the lookahead sentinel.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

### VAN-ML-REQ-073 — Two-source agreement is not independence

Preserve parent Kalshi/Polymarket liquidity/agreement rules for armed expectations; matching horizons and semantic relation required; no independent-evidence multiplication.

Packet: `VAN-ML-PKT-040` · Parent: BE-014, BE-015, BE-016, BE-018 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-073-P — POSITIVE — NOT_RUN**

Two fresh comparable sources pass consistency; single-source research remains explicitly SINGLE_SOURCE and cannot arm the inherited dual-source path.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

**VAN-ML-AT-073-N — ADVERSARIAL — NOT_RUN**

Duplicate syndication, mismatched contract horizons or two models reading one feed cannot count as independent confirmations.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

### VAN-ML-REQ-074 — Event-grouped calibration and adequate evidence

Calibrate by declared event family/horizon/cohort with matured labels; group dependent snapshots/contracts and report effective event counts and uncertainty.

Packet: `VAN-ML-PKT-041` · Parent: BE-015, BE-016, BE-021, BE-022 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-074-P — POSITIVE — NOT_RUN**

Evaluate raw and calibrated proper scores on later whole-event holdouts with recorded sample adequacy.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

**VAN-ML-AT-074-N — ADVERSARIAL — NOT_RUN**

Randomly splitting snapshots of the same event or pooling unrelated categories to conceal macro miscalibration fails admission.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

### VAN-ML-REQ-075 — Preserve probability meaning

Market-implied estimate, calibrated physical-event probability, asset outcome probability and rank score are distinct types and fields.

Packet: `VAN-ML-PKT-041` · Parent: BE-015, BE-016, BE-021, BE-022 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-075-P — POSITIVE — NOT_RUN**

Expose raw and calibrated event probabilities with compatible calibrator lineage and explicit event definition.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

**VAN-ML-AT-075-N — ADVERSARIAL — NOT_RUN**

Copy event probability to trade win probability or label an uncalibrated market price CALIBRATED without evidence is refused.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

### VAN-ML-REQ-076 — Correct Qlib and neural event-feature adapters

Feed as-of event features to existing Qlib/LightGBM tasks and supported NeuralForecast historical covariates; future calendar use is versioned and not future probabilities.

Packet: `VAN-ML-PKT-042` · Parent: BE-013, BE-015, BE-016, BE-021, BE-022 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-076-P — POSITIVE — NOT_RUN**

Fit/export/reload each selected provider on an adequate causal synthetic/allowed cohort and reproduce held-out predictions.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

**VAN-ML-AT-076-N — ADVERSARIAL — NOT_RUN**

Future event prices, unsupported exogenous flags or cross-fold scaler/calibrator fits fail before model publication.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

### VAN-ML-REQ-077 — Conditional asset response and incremental information

Estimate event-to-instrument outcomes under context, timing and horizon; compare against conventional market/news/calendar features and use OOF fusion.

Packet: `VAN-ML-PKT-042` · Parent: BE-013, BE-015, BE-016, BE-021, BE-022 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-077-P — POSITIVE — NOT_RUN**

Demonstrate a conditional response bundle with matched labels/units and a complete with/without-event ablation report.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

**VAN-ML-AT-077-N — ADVERSARIAL — NOT_RUN**

Treat a rate-cut probability as gold-up probability or use in-sample learner predictions to qualify fusion is rejected.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

### VAN-ML-REQ-078 — Preserve D1–D7 and manual ownership

External information affects entries/ranking/lifecycle only through inherited rules; D7 is required for news-generated added risk; existing risk authority sizes.

Packet: `VAN-ML-PKT-043` · Parent: BE-009, BE-011, BE-013, BE-015, BE-016, BE-017 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-078-P — POSITIVE — NOT_RUN**

Exercise permitted reduce/defer/template/rank actions plus separately admitted sandbox D7 with correct source and owner bindings.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

**VAN-ML-AT-078-N — ADVERSARIAL — NOT_RUN**

Raise news multiplier above1, shorten blackout, widen stop, touch owner-managed position or bypass two-source arming: refuse.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

### VAN-ML-REQ-079 — Net executable binary-contract value

For held-to-settlement use expected payout minus actual entry costs/fees/lockup; for early exit use executable exit distribution; market price is not independent edge.

Packet: `VAN-ML-PKT-043` · Parent: BE-009, BE-011, BE-013, BE-015, BE-016, BE-017 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-079-P — POSITIVE — NOT_RUN**

Reference fixtures reconcile depth-aware entry cost and final/early-exit value in exact currency units.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

**VAN-ML-AT-079-N — ADVERSARIAL — NOT_RUN**

Use midpoint instead of ask, omit fees, double-charge embedded spread or reuse purchase price as independent success probability: fail.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

### VAN-ML-REQ-080 — Full event-loss and portfolio stress

Model maximum binary outlay, related event exposures and uncertain probabilities; Kelly-style analysis remains a bounded sandbox proposal, never sizing authority.

Packet: `VAN-ML-PKT-043` · Parent: BE-009, BE-011, BE-013, BE-015, BE-016, BE-017 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-080-P — POSITIVE — NOT_RUN**

Compare risk-constrained proposals against existing account/event limits and explicit worst-case payoff scenarios.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

**VAN-ML-AT-080-N — ADVERSARIAL — NOT_RUN**

Assume a protective stop caps binary loss, net incompatible contracts, infer joint independence or emit a live order quantity from the forecaster: refuse.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

### VAN-ML-REQ-081 — Exact fees and complete settlement accounting

Use revision/series/account-specific fee rules, per-fill precision/accumulator, cash reservations and all relevant settlement/conversion costs.

Packet: `VAN-ML-PKT-044` · Parent: BE-006, BE-009, BE-010, BE-011, BE-012, BE-019 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-081-P — POSITIVE — NOT_RUN**

Fragmented fill and single-fill fixtures reconcile cash, fees, inventory and final settlement under the configured policy.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

**VAN-ML-AT-081-N — ADVERSARIAL — NOT_RUN**

Applying one timeless fee constant, cancelling debit on unknown state or crediting unsettled cash fails accounting.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

### VAN-ML-REQ-082 — Queue-aware feasible event execution

Model real observation/decision/order latency, depth, partial fills, queue uncertainty and cancel races; sparse data cannot prove maker profitability.

Packet: `VAN-ML-PKT-044` · Parent: BE-006, BE-009, BE-010, BE-011, BE-012, BE-019 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-082-P — POSITIVE — NOT_RUN**

Replay a partial fill followed by cancellation and delayed acknowledgement on one consistent book path.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

**VAN-ML-AT-082-N — ADVERSARIAL — NOT_RUN**

Touch-equals-fill, cancel-request-equals-cancelled, candles-prove-queue or zero-latency post-announcement entry cannot qualify.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

### VAN-ML-REQ-083 — Payoff-proven contract consistency

Enumerate permissible resolution/void/dispute states and quantities; exact/complement matching precedes worst-case net-payoff assessment.

Packet: `VAN-ML-PKT-045` · Parent: BE-009, BE-012, BE-019, BE-021, BE-022 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-083-P — POSITIVE — NOT_RUN**

Produce a positive synthetic complementary payout matrix and a separately named executable-margin estimate.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

**VAN-ML-AT-083-N — ADVERSARIAL — NOT_RUN**

Different source/vintage, omitted void state, unequal hedge quantity or negative state payout must defeat an arbitrage assertion.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

### VAN-ML-REQ-084 — Non-atomic multi-venue risk and capital

Keep venue-specific balances, collateral/currency conversion and hedge-failure unwind costs; no instant cross-venue capital or fill assumption.

Packet: `VAN-ML-PKT-045` · Parent: BE-009, BE-012, BE-019, BE-021, BE-022 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-084-P — POSITIVE — NOT_RUN**

Simulate both-filled and first-leg-only outcomes with bounded loss and explicit cash reservation/readback.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

**VAN-ML-AT-084-N — ADVERSARIAL — NOT_RUN**

Unfilled hedge assumed complete, stablecoin treated as guaranteed USD or delayed settlement capital instantly reused fails.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

### VAN-ML-REQ-085 — Inventory-aware event quoting laboratory

Implement bounded quoting policies with event-family inventory, jump risk, adverse selection and value conditional on fills; no direct live execution.

Packet: `VAN-ML-PKT-046` · Parent: BE-009, BE-010, BE-012, BE-019, BE-021, BE-022 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-085-P — POSITIVE — NOT_RUN**

Exercise fixed and inventory-skew policies on the same synthetic stream with exact inventory and fill-conditional markout.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

**VAN-ML-AT-085-N — ADVERSARIAL — NOT_RUN**

A profitable unconditional midpoint forecast or assumed privileged queue/rate treatment cannot prove maker profitability.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

### VAN-ML-REQ-086 — Maker quote lifecycle and protective withdrawal

Simulate pending/new/partial/cancel/unknown quote states, stale-feed reduction and scheduled-event withdrawal without manipulating markets.

Packet: `VAN-ML-PKT-046` · Parent: BE-009, BE-010, BE-012, BE-019, BE-021, BE-022 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-086-P — POSITIVE — NOT_RUN**

Bad book/official-release state prevents new quotes; pending cancels remain reserved until confirmed and restart restores exposure.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

**VAN-ML-AT-086-N — ADVERSARIAL — NOT_RUN**

Spoofing/wash-trade policy, removed reservation before cancellation, unbounded quote loops or continued healthy status after a gap: refuse.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

### VAN-ML-REQ-087 — Four preregistered incremental-value studies

Implement risk-filter, surprise, volatility and ranking studies with identical opportunity sets, incumbent/calendar/exposure-matched controls and frozen utility.

Packet: `VAN-ML-PKT-047` · Parent: BE-016, BE-021, BE-022, BQ-001, BQ-002, BQ-003 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-087-P — POSITIVE — NOT_RUN**

Produce all four complete study contracts, reports and explicit no-edge/inconclusive paths with full-account outcomes.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

**VAN-ML-AT-087-N — ADVERSARIAL — NOT_RUN**

Claim improvement solely from fewer trades, dropped missed winners, favourable period selection or ignored source/compute cost: fail.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

### VAN-ML-REQ-088 — Prospective sealing and dependent uncertainty

Seal issued forecasts before outcomes, use event/time-block inference and full trial census; compare realistic lags and negative controls.

Packet: `VAN-ML-PKT-047` · Parent: BE-016, BE-021, BE-022, BQ-001, BQ-002, BQ-003 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-088-P — POSITIVE — NOT_RUN**

Mature future outcomes against sealed forecasts and report effective events, uncertainty, concentration and cost-adjusted utility.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

**VAN-ML-AT-088-N — ADVERSARIAL — NOT_RUN**

Repeated quotes as independent trials, post-release resealing, future correction leakage or fixed-days-as-sufficient rule fails qualification.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

### VAN-ML-REQ-089 — Complete owner projections and operator controls

Extend existing event/research/work/evidence/settings and later native surfaces with source state, expectation lineage, study/lab controls, calibration and per-use outcomes.

Packet: `VAN-ML-PKT-048` · Parent: BE-003, BE-015, BE-016, BE-017, BE-030, BE-031, BE-032, BE-033, BE-034, BQ-001, BQ-005, BQ-006 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-089-P — POSITIVE — NOT_RUN**

Headless actual gateway and worker readback handles ready, absent, stale, disputed, rejected, inconclusive and unknown without fake controls.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

**VAN-ML-AT-089-N — ADVERSARIAL — NOT_RUN**

Dense new Home dashboard, backend-only schema with no real caller, or active trade control on research-only evidence cannot pass closure.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

### VAN-ML-REQ-090 — Failure isolation and truthful full-backend closure

Isolate event workers from T0 and finance; complete recovery, revocation and rollback; all new backend obligations feed existing gates without purchasing licences or fabricating access.

Packet: `VAN-ML-PKT-048` · Parent: BE-003, BE-015, BE-016, BE-017, BE-030, BE-031, BE-032, BE-033, BE-034, BQ-001, BQ-005, BQ-006 · State: `SPECIFIED_NOT_IMPLEMENTED`

**VAN-ML-AT-090-P — POSITIVE — NOT_RUN**

Kill/restart adapter, lose registry/source, fill disk, change schema and revoke inputs; valid unrelated strategies/protection continue within their policy.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions

**VAN-ML-AT-090-N — ADVERSARIAL — NOT_RUN**

Fixture success relabelled provider-ready, additive-only gate unlocking frontend, source failure disabling exits or unexpected external payment: fail.

Evidence: Exact source and VM/runtime identity; Input, event/rule/data/fee revision and availability cutoffs; Invoked real component/service, assertion outputs and durable readbacks; Scope-correct independent review and honest fixture/provider/economic distinctions
