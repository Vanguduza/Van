# VAN Forecasting, Quant Research and Adaptive Model Adoption Blueprint

## Qlib · LightGBM · Freqtrade/FreqAI capabilities · NeuralForecast · Prediction-market intelligence

**Document ID:** `VAN-FORECAST-ADOPTION-REV1.1-20261017`  
**Revision:** 1.1 · **Finalized specification:** 17 October 2026  
**Project:** VAN / VATI · `Vanguduza/Van`  
**Parent:** VAN Next backend-first programme, Rev 1.10  
**Status:** `FINALIZED_SPECIFICATION / INDEPENDENT_PARENT_ADMISSION_PENDING / NOT_IMPLEMENTED`  
**Authority:** Design and implementation specification only. No F15, Backend Complete, deployment, model promotion, trading mandate or financial authorization is issued by this document.

> Build one complete, evidence-qualified forecasting capability inside VAN. Use Qlib for research integration, LightGBM for initial tabular forecasting, NeuralForecast for complementary temporal and distributional models, and selected Freqtrade/FreqAI operating practices for the model lifecycle and diagnostics. Add probability intelligence from prediction markets, causal event-to-asset models, calibrated value proposals and complete execution/arbitrage/market-making research laboratories. Preserve VAN's sole risk authority, order sender, existing services and whole-product backend-first programme.

---

## Reading and delivery map

### Revision 1.1 integration decision

This revision incorporates the owner's instruction to finalize the prediction-market recommendations. **Netcup and Oracle are the intended VAN execution/compute environments. No licence procurement, new subscription, account registration, paid data purchase or live event-contract activation is part of this phase.** The source adapter and all research software remain in the implementation scope; use synthetic fixtures, already-permitted data or admitted existing access according to the actual source-use record. A procurement task is not a prerequisite for authoring or implementing these capabilities. [S26]

Server placement, operator/account eligibility, source-use scope, software completion, economic qualification and live authority are separate facts. A Netcup or Oracle address establishes neither a provider permission nor an operator's eligibility. This distinction is recorded once in the source profile, not converted into a repetitive owner-authentication or general development blocker. Do not falsify a source's state, evade an access restriction or label fixtures as real capture. Where actual external access is unavailable, the affected integration proof remains outstanding while unrelated authorized engineering proceeds. [S39–S40]

**Two tracks are integrated.** The primary track uses event probabilities and uncertainty to improve VAN's existing instrument decisions. The second supplies complete binary-contract valuation, payoff-consistency/arbitrage and inventory-aware market-making research labs. Both tracks are mandatory engineering scope; a live Kalshi/Polymarket order adapter is not added. The labs remain usable with replay and scenario data without becoming a second trading engine.

The original 36 packet IDs, 60 requirement definitions and 120 acceptance contracts are preserved. Twelve backend packets, 30 requirements and 60 acceptance contracts extend the child graph to **48 / 90 / 180**. Ten additional schemas bring the total to **18**. The authoritative revised child plan is in this pack. The actual parent Rev1.10 signed graph is **not** silently rewritten; `plan/PARENT_INTEGRATION_DELTA.json` specifies its required amendment and independent gate integration. The byte-identical original ZIP is retained under `lineage/`.


This master explains the architecture, technical behavior and acceptance policy. `plan/IMPLEMENTATION_PLAN.md` gives the full dependency-ordered packet contracts; its JSON companion is the canonical child-plan representation. `plan/REQUIREMENTS_AND_TESTS.md` and the corresponding JSON files contain **90 mandatory engineering requirements and 180 application acceptance contracts**, all unexecuted. The programme has **48 child packets**, including preparation, backend implementation and verification, parent gate integration, later native surfaces and release.

`contracts/` defines typed interchange and examples. `config/RESEARCH_STARTING_PROFILE.json` contains illustrative research settings, not an optimal strategy or a live mandate. `references/SOURCE_REGISTER.md` records consulted primary sources, parent fingerprints and observed repository identities. `verification/` contains a document-only consistency checker and its actual report. Passing that checker proves selected document properties only; it cannot prove software exists or issue any real gate.

**Order of use:** read §§1–4 for scope and ownership, §§5–15 for implementation, §§16–21 for qualification and rollout, and §22 for the fully integrated prediction-market design, then the packet and acceptance files. Every requirement and parent obligation remains binding even when a section gives a smaller illustrative example.

---

## 1. Product objective, scope and non-claims

### 1.1 What VAN will gain

The completed addition must let VAN construct reproducible point-in-time research datasets; train and compare tabular and neural models; estimate returns, relative opportunity quality, realized volatility, execution costs and uncertainty; record every forecast with its provenance; detect stale or out-of-domain predictions; continuously prepare new model candidates; and admit only independently qualified evidence into the existing trading decision chain.

It must be a usable backend, not a collection of installed packages or notebooks. The owner must eventually be able to inspect current forecast status, understand a model's exact task and limitations, compare studies, request or cancel bounded research, inspect rejected candidates, review promotion proposals, see when inference abstains and recover or roll back model bindings. All these operations require actual services, registered callers, durable outcomes and headless integration proof before frontend implementation.

No part of this blueprint promises profitable trades. A model can be implemented correctly and still have no economic edge. Conversely, an attractive backtest cannot compensate for invalid timestamps, uncharged costs, missing recovery or unauthorized execution.

### 1.2 Mandatory adopted scope

| Component | Complete engineering obligation | Explicit boundary |
|---|---|---|
| Qlib | VAN data loader/handler, fold-scoped datasets and processors, reproducible model tasks, research evaluation hooks and single MLflow recorder integration | No Qlib exchange/execution runtime, default regional trading policy or independent live portfolio controller |
| LightGBM | Return/net-edge regression, binary setup-event models, explicit quantile and grouped-ranking adapters, native artifact handling and comparable evaluation | No pretrained profit assumption; a raw score is not a calibrated win probability |
| Freqtrade/FreqAI practices | Point-in-time bias diagnostics, warmup analysis, feature expansion, rolling retraining, freshness/expiration, novelty checks, cached prediction lineage, bounded studies and complementary trade suppressions | Native VAN implementations of behavior; no second live Freqtrade bot or hidden dependency on its order authority |
| NeuralForecast | Real N-HiTS, N-BEATSx and DeepAR integrations; probabilistic losses, correct exogenous mapping, rolling evaluation, safe persistence, retained temporal scenarios; usable TFT/PatchTST/iTransformer research plugins | Every plugin requires its own supported-input matrix and tests; no requirement that every neural model become a live champion |
| Shared infrastructure | Existing selected Optuna, Feast and MLflow integrations; typed jobs/artifacts/forecasts, calibration, serving, outcomes, supervision and recovery | Logical services may share a process where safe. Do not deploy a separate microservice merely because a contract has a name |
| Baselines and challengers | XGBoost, linear/logistic models, persistence, no-trade/incumbent strategy, simple ranking and HAR/GARCH-style volatility baselines | Baseline selection is task-specific and cannot be weakened to make a complex model win |
| Prediction-market intelligence | Kalshi/Polymarket read-only adapters, semantic contract registry, coherent probabilities, event calibration, frozen expectations, conditional asset-response models and exact existing news-path consumers | No procurement prerequisite; actual data use remains source-scoped; event probability is not trade-win probability |
| Event research laboratories | Full binary value/position-proposal analysis, execution replay, payoff-state arbitrage and inventory-aware market-making labs with fault/recovery scenarios | Mandatory research implementations; no live event-contract order submission, special venue privileges or self-issued risk authority |
| VAN interfaces | Complete backend projections and controls, then full integration into mapped native screens after global backend completion | No new frontend, visual prototype or renderer implementation during backend work |

The core model adapters are mandatory, and the declared challenger plugins must be operational in the research environment. Training tests, failure paths, export/load and evaluation cannot be deferred because a model may ultimately be rejected economically. Other model families, TimeLLM, reinforcement learning, a new crypto exchange executor and every architecture in NeuralForecast's catalogue are outside this addition unless separately admitted. Existing unrelated VAN features are preserved, not removed from parent scope.

### 1.3 Three independent kinds of completion

**Engineering completion** means the full real train→artifact→serve→evaluate→review→admit/reject/revoke→recover capability works with actual upstream packages and permitted data/services. Both positive sandbox admission and refusal paths must be exercised. A permanently unbound evidence producer or refusal-only stub is incomplete.

**Economic model qualification** is per model, strategy, target, instrument cohort, horizon, execution policy and intended use. Its outcomes are `QUALIFIED`, `REJECTED` or `INCONCLUSIVE`. A rejected model remains inspectable and usable for bounded research, with no consequential trading influence. Negative evidence is a valid research outcome, not an excuse to omit the implementation.

**Live authority** is separately granted by the existing owner/risk/governance route. An MLflow alias, model score, completed training job, software release, document approval or Backend Complete certificate does not grant it.

Parent BG-001 may only close after all mandatory engineering, genuine integration and sandbox/technical shadow checks are complete. This does not require fabricating market edge. Any specifically owner-admitted promise of a first economically qualified live strategy remains an explicit separate unmet product outcome until proved; it may not be silently relabelled engineering success.

---

## 2. Current evidence and reconciliation baseline

### 2.1 Source identities

The repository observations below are inherited from Rev1 preparation. This revision re-read the supplied artifact and parent news contracts, not every current repository branch. Implementation packet001 must refresh live source identities before changes.

The live GitHub read on 17 October returned `main` at **`8eb1889822fc8a83f219977c15340172e16acd91`**. The parent Rev1.10 document cites its separate planning-source baseline **`d8a207cb00b3c8e3104041390a861a78a00b7ff7`**. These are not interchangeable. Scope admission must reconcile default-branch code, the parent planning source and every relevant later feature-bearing branch; do not recreate features because they are absent from an old summary. [S01–S03]

The actual Library copies were read and materialized unchanged. Their SHA-256 fingerprints are:

| File | Observed SHA-256 |
|---|---|
| `VAN_NEXT_MASTER_BLUEPRINT_REV1_10_20261017.md` | `dba347b9f02831d1a3a2d9570b4434f6a8b4b98f6f47862c830ff6784cb56f51` |
| `VAN_NEXT_DEVELOPMENT_PLAN_REV1_10.md` | `1b367e7507f2d371230891458ca1efc05c6fbb343b712d97ca170cecebbbc6e2` |

The parent plan declares its generating JSON hash as `391bde124e1015302ebbe6b7db2211303f8e888683782d2db08203fced7ba6bd`. That is a different artifact from the Markdown file. Likewise, the parent's cited historical master hash is not the hash of the newly retrieved Rev1.10 master. Do not collapse these identities.

### 2.2 Preserve and extend actual VAN structures

| Existing source boundary | Observed role / relevance | Required adoption action |
|---|---|---|
| `trading/architecture/stack_lock.json` | Qlib, Optuna, Feast and MLflow are selected but marked not started in inspected main | Complete their stated roles, reconcile exact versions at adoption, update status only from actual evidence |
| `vati/intelligence/feature_registry.py` and feature contracts | Existing feature ownership and evidence boundary identified in earlier source audit | Re-read current implementation, extend definitions rather than make Qlib/NF competing feature authorities |
| `vati/arbiter/meta_labeler.py` | Existing rules-based, uncalibrated, reduce-only scoring in prior audit | Preserve old score semantics; add explicit model evidence and separate probability fields |
| `vati/risk/conformal.py` | Current code already implements symmetric residual-based intervals, calibration age and coverage reporting | Extend this ownership with forecast-specific producers, calibration identity and domain semantics; do not duplicate a risk governor |
| `vati/validation/policy.py` | DSR probability, PBO and walk-forward minimum policy exists | Reuse the canonical policy object and upgrade evidence/statistics rigor, never weaken it silently |
| `vati/backtest/engine.py` | Shared single-symbol DecisionCycle, fixed intrabar ordering and forced terminal closure | Reproduce scoped findings and extend actual portfolio replay and accounting before economic certification |
| `vati/research/workflow.py`, learning hooks/drift/replay | Existing slow research and restricted adaptive feedback identified in prior audit | Add callers/jobs/results to these owners; do not mistake health adaptation for supervised training |
| Account coordinator, RiskAuthority and ExecutionRouter | Existing account-wide decision and execution authority boundaries | Only these owners may reserve risk, size, submit or protect live orders |

The inspected stack explicitly prohibits Qlib's execution layer and says an MLflow alias is not strategy promotion. Qlib's official recorder offers an MLflow-backed experiment manager. Those fit naturally: configure one existing VAN-scoped tracking backend rather than a second registry. [S03, S08]

### 2.3 What was and was not verified for this blueprint

**Revision distinction:** the following source-review history describes Rev1 preparation and is preserved as provenance. Rev1.1 adds primary prediction-market sources, the exact current owner direction, a fresh read-only Global DIAL gateway observation and the source/contract-specific design in §22. No observation here certifies a live prediction-market service. [S26–S42]

This preparation re-read the parent plan and relevant master contracts, current GitHub main identity, stack selection, Qlib's LightGBM wrapper, the backtest engine, existing conformal component and validation thresholds. Other paths above are integration targets established by the preceding audit and require revalidation in packet001. This is not a fresh semantic audit of every VAN function or every branch.

Global DIAL returned a live serving owner route during preparation, but its broad projection also showed stale capacity/Zuul observations and a blocked development-readiness projection. A reachable control gateway is not proof that forecasting workers, dependencies, broker connections or available memory are qualified. Those must be measured at implementation/deployment time. No host configuration or project source was changed during blueprint preparation. [S25]

---

## 3. Authority and architecture

### 3.1 One trading system, several bounded analytical engines

```text
Existing broker / market / news / account data owners
       + read-only prediction-market observations / event contracts
                         │
                         ▼
Point-in-time snapshots + canonical feature and target specifications
                         │
               ┌─────────┴──────────┐
               ▼                    ▼
      Qlib / LightGBM /       NeuralForecast model
      tabular challengers    and temporal challengers
               └─────────┬──────────┘
                         ▼
 Shared Optuna studies → MLflow experiments → immutable model artifacts
                         │
                         ▼
 Independent data / forecast / calibration / economic qualification
                         │
                         ▼
 Exact model binding → bounded forecast service → immutable ForecastPacket
                         │
                         ▼
 Existing opportunity arbiter / account coordinator / qualified fusion
                         │
                         ▼
 Existing TradeIntent → RiskSnapshot → RiskAuthority → ExecutionRouter
                         │
                         ▼
 Broker truth / reconciliation / protection / outcome and evidence ledger
```

This is a control and data-flow description, not an instruction to bypass VAN's already selected trading kernel or service contracts. Existing kernel adoption/reconciliation remains a parent duty. Forecasting must integrate at model and evidence interfaces that survive that reconciliation.

### 3.2 Non-negotiable invariants

1. **Single financial authority.** Only the existing RiskAuthority determines permissible risk and size; only the established router submits orders. Forecasts, Qlib, NF, Optuna, research agents and UI carry `authority_effect=NONE`.
2. **No foreground training.** Training, cross-validation, deserialization, registry calls and external model requests never run synchronously inside T0 risk/protection/execution. The trading loop consumes a bounded local snapshot or no model evidence.
3. **No automatic live promotion.** Retraining creates a candidate. Publication to MLflow creates a version. Neither changes an admitted runtime binding. A separately verified scope-bound promotion is required.
4. **Preserve existing protections.** Forecast outages may suppress dependent entries but must not disable authorized exits, reconciliation, kill-switch observation or stop protection. Availability of an exit operation is not a guarantee an offline venue executes it.
5. **No source laundering.** Historical revisions, inferred availability, simulated outcomes, fixture certificates and uncalibrated scores remain labelled as such. Hashes identify bytes; they do not establish truthful evidence or independent approval.
6. **Whole backend before new frontend.** All admitted capabilities, including their actual producers and callers, feed the parent's renewed BG-001. A beautiful chart or installed library cannot close a backend packet.

Owner identity/qualification is distinct from model, data and evidence validity. Expiring or revoking a forecasting artifact must not revoke the owner’s permanent qualification or invent a repeated owner-authentication requirement. Use the current real authority contract for each scoped action.

### 3.3 Logical components and ownership

| Logical component | Owning boundary | Responsibility |
|---|---|---|
| DatasetSnapshotBuilder | Existing market-data/research owners | Immutable data, availability and universe manifests |
| FeatureCompiler | Existing feature registry | One definition/transform catalogue for offline and online |
| TargetBuilder | Research target owner | Executable label semantics, maturity, censoring and provenance |
| FoldPlanner / BiasAnalyzer | Existing validation/research | Leakage controls, chronology, warmup and holdout policies |
| QuantResearchAdapter | Qlib integration | DataHandler/Dataset tasks and tabular model execution |
| TemporalResearchAdapter | NeuralForecast integration | Model-specific panel conversion, training and forecasting |
| StudyController | Existing durable workflow + Optuna | Bounded trials, scheduling, cancellation and retry |
| ModelArtifactRegistry | MLflow + existing VAN evidence authority | Experiments/bytes versus separately admitted use |
| CalibrationService | Existing conformal/validation ownership | Probability and interval quality; no sizing authority |
| ForecastService | Bounded T1 analytical service | Preloaded inference, freshness, novelty and immutable cache |
| ForecastEvidenceAdapter | Existing arbiter/account coordinator | Qualified inputs and explicit failure fallback |
| OutcomeAttribution | Existing learning/TCA/ledger | Observable results, bias-aware counterfactuals and drift |
| PredictionMarketAdapter / ContractMapper | Existing NewsIngress, CalendarRecorder and event registry | Scope-aware observations, exact proposition/rules, clocks, book recovery and versioned equivalence |
| EventProbabilityBuilder / AssetResponse | Existing features, research and calibration services | Coherent market expectations, frozen surprise, conditional asset outputs and no duplicated confirmation |
| EventResearchLabs | Existing isolated research/replay boundary | Binary-value analysis, queue/cash replay, payoff-state comparison and inventory-aware quote proposals; no orders |
| Owner projections | Existing gateway/capability catalogue | Truthful controls, evidence, failures and UI consumption |

Heavy worker code should live outside packages imported by the core trading loop. Proposed new namespaces are `trading/forecast_research/` for heavy workers and `trading/vati/forecasting/` for lightweight contracts, read snapshots and consumers. Exact paths are resolved during source reconciliation; names here do not assert existing modules or endpoints.

### 3.4 Source and change policy

Prefer an adapter around an upstream library to a permanent fork. Pin source/version and artifact hashes; register local patches with upstream provenance and behavioral tests. Modify stack-lock roles only through admitted changes, preserving the prohibition on extra execution authority. Use temporary `DEC-PENDING-*` decision identifiers where repository policy requires them; do not allocate potentially colliding permanent decision numbers from this document.

---

## 4. How this enters the Rev1.10 programme

This is a complete additive specification, not a replacement master and not a claim that the parent has already been updated. Packet001/002 must propose a reconciled parent revision, adding the 90 requirements, model/provider capability contracts and child execution graph. Existing 76 packet IDs remain traceable. The expanded schedule and signed scope must be regenerated and independently checked; an amended graph has a new digest even when legacy packet IDs remain unchanged. [S01–S02]

| Parent duty | Additive work inserted |
|---|---|
| PRE-001 / PRE-002 / PRE-003 | Source reconciliation, data/target/model scope and independent amended F15 |
| BE-008 / BE-014 / BE-015 / BE-018 | Point-in-time data, exogenous vintages, features, model-compatible calendars and prediction-market source/event expectations |
| BE-015 / BE-016 / BE-017 | Exact event semantics, frozen expectations, two-source consistency, conditional asset response and unchanged D1–D7 news consumers |
| BE-006 / BE-009 / BE-010 / BE-012 / BE-019 | Simulation accounting, portfolio replay, cost/latency/protection parity |
| BE-013 | Qlib/LightGBM/neural model providers, forecast use, strategy/mode edge evidence |
| BE-021 / BE-022 | Interpretation, research comparison, diagnostics and manual-pattern research |
| BE-027 / BE-028 | Consent, derived-data erasure, schedules, durable retraining and outcomes |
| BE-030 / BE-031 / BE-032 / BE-033 / BE-034 | Owner projections, settings, complete capability catalogue, operations and qualification tooling |
| BQ-001…BQ-006 / BG-001 | Real cross-domain acceptance, independent additive closure and global backend barrier |
| UX and FE-006…FE-022 as mapped | Later whole-product native consumption, never an early UI exception |
| QA / REL | Actual device acceptance, independent release, compatible rollback and retirement |

**Avoid circular scheduling.** A packet's `parent_units` field says which obligations it contributes to; it is not a demand that every one of those parent units finish before the packet starts. For example, the research dataset and raw model producers contribute to BE-013 before the final BE-022 owner-learning view consumes them. BE-022 must not be made a whole-unit prerequisite of its own upstream BE-013 producer. Integrate at concrete contracts/subreceipts, then validate the expanded parent graph.

The new child backend gate is narrower than BG-001. Even a genuine additive completion receipt cannot unlock the frontend if accounts, funds, news, browser, memory or any other mandatory parent backend service remains incomplete. Existing unrelated scope does not disappear merely because this addition concerns trading.

New probability wording, altered calibration policy, initial instrument scope, resource budgets and any changed strategy evidence threshold must be reconciled with existing owner decisions. Existing no-risk-increase news rules and two-source armed-event conditions are not bypassed by a model that consumed the same news.

---

## 5. Point-in-time data and target engineering

### 5.1 Canonical information record

Every contributing observation must carry canonical instrument/venue/contract identity, market or account scope, event time, provider publication time where available, VAN `available_at`, ingestion time, source revision, collection method, quality and entitlement. Use UTC for transport, with explicit market-calendar and timezone revisions for bar/horizon semantics. Do not invent a historic availability timestamp when only a later archive exists: mark it reconstructed/uncertain and restrict the claimed evidence accordingly.

A decision at time `t` may consume an observation only when its admitted availability is no later than `t`. Training at cutoff `T` additionally requires every supervised label's **end and actual availability** to precede its allowed training boundary. Future calendar variables may be supplied only as the calendar vintage actually known at that forecast origin.

Snapshots are immutable. Corrections create new versions and invalidate descendants as appropriate; they do not retrospectively improve stored forecasts. A point-in-time backtest uses the data view available then, while a separately labelled corrected-data study may examine measurement error. Both must state which view was used.

### 5.2 Market cohorts, not indiscriminate pooling

Define cohorts by instrument class, feed/venue, calendar, target unit, horizon, liquidity and execution convention. An EURUSD CFD, spot currency observation and exchange future are not the same instrument. A ZSE equity with stale end-of-day prints is not a continuously tradable crypto pair. Deriv instruments with non-linear or full-stake settlement need their actual payoff model; do not infer linear mark-to-market returns from a generic ticker.

The research universe is versioned as of each cutoff, including permitted delistings, listings, trading halts and corporate actions. Selection using today's surviving assets must be labelled and cannot certify historical cross-sectional alpha. Equity modeling adjustments must preserve the distinction between adjusted features and executable raw-price/quantity/corporate-action accounting. Point-in-time currency/contract conversions are mandatory.

Use existing provider scope first. This document does not invent a live asset list, buy a data feed or authorize access. A permitted historical research cohort may be admitted separately from live broker scope. New paid feeds, live accounts and compute charges require the existing owner authorization route.

### 5.3 Missing data and irregularity

Validate duplicate timestamps, inverted OHLC, impossible prices, stale quotes, broken sequences, missing bars and volume semantics. Explicitly distinguish no trades, market closed, provider absent and zero volume. Filling a missing observation is a model transformation with an indicator and policy, not evidence a market was tradable. A halted market cannot become continuously liquid because a dataframe was forward-filled.

NeuralForecast and Qlib conversions must preserve these semantics. For regular grids, insert missing masks according to an admitted rule. For business-time grids, retain the mapping to actual session timestamps. Never compress gaps and still label horizons as elapsed hours. Features computed from another timeframe may use only its last completed, available candle.

### 5.4 One feature catalogue

Prediction-market observations enter this same catalogue under §22, not an independent feature store. Event identity, time to release, contract maturity, raw versus calibrated probability, spread/depth, quote age, source relationship and availability must accompany each derived feature. The profile prohibits using the realized future probability trajectory as a known-future covariate.

The existing VAN registry remains the definition owner. Register raw source dependencies, transform code/version, lookback, minimum history, numerical scale, categorical vocabulary, missing policy, time availability, allowed cohort and audit lineage. Produce offline features and online inference snapshots from that definition. Feast provides storage/materialization and retrieval under that ownership; it does not mint definitions or determine risk.

Feature expansion from FreqAI is a pattern, not permission for unbounded dimensionality. Begin with qualified existing trend, momentum, volatility, spread/liquidity, session and event features. Add lags, other horizons and correlated instruments only through the versioned DAG and incremental validation. Preserve row IDs through all filters so features, labels, weights and explanations stay aligned. A feature-selection transform, PCA, scaler, imputer, outlier detector and category vocabulary are learned artifacts fitted inside a training fold, never on the whole dataset. [S12]

### 5.5 Target catalogue and units

| Target family | Definition contract | Recommended first learner |
|---|---|---|
| Future return | Explicit start/end executable reference, horizon and arithmetic/log convention; gross or net costs identified | LightGBM regression; XGBoost baseline/challenger |
| Setup-event probability | Probability of a precisely defined event under a fixed entry/exit policy, e.g. positive net outcome by a given horizon | Binary LightGBM plus independent calibration |
| Relative opportunity | Ordinal ranking within the same cutoff/cohort and compatible target/cost convention | LightGBM grouped ranking or validated regression-score ranking |
| Downside/upside quantiles | Conditional quantiles for a named scalar outcome and horizon | LightGBM quantile adapter; NF multi-quantile models |
| Realized volatility | Forward realized variance/volatility over a named sampling grid, with missing-data rules and optional transformation | HAR/GARCH baselines; N-HiTS/N-BEATSx challengers |
| Execution cost/liquidity | Target under actual side, quantity bucket, venue, order style and opportunity time; identify selection/censoring | Tabular regression/quantiles; temporal challenger only on adequate data |
| Temporal scenarios | Conditional trajectories, with raw samples, generator, seeds, horizon and dependency interpretation | DeepAR tested retained-path adapter |
| Event probabilities and surprise | Named proposition and resolution/vintage, frozen pre-release distribution; real-world calibration separate from market-implied price | Event-calibration provider and Qlib/LightGBM research bridge |
| Conditional asset response | Instrument return, volatility or precisely defined trade event conditional on event scenarios and prior market state | Tabular baseline first; NeuralForecast temporal challenger |
| Excursions and barriers | Maximum favorable/adverse move or stop/target event under specified feasible paths and latency | Separate target-specific models; not inferred from marginal terminal quantiles |

For signed arithmetic gross returns, `target_net = signed_gross_return - explicit_total_cost_fraction` is valid only when both use the same denominator and the gross reference has not already included those costs. If bid/ask fills already embed spread/slippage, do not deduct them a second time. Nonlinear derivative payoffs use the actual payoff function, not this shortcut.

A setup classifier's event is not universally “the trade wins.” Record entry eligibility, planned horizon, stop/target/order policy, timeout, unresolved fills and ambiguous same-bar touches. Label censoring explicitly. Actual realized holding duration is an outcome, never a prediction-time input unless a planned duration was genuinely declared then.

For volatility, a permitted target is `log(epsilon + sum(r_k**2))` with a fixed return/sampling definition. Preserve target transformation in the manifest. Exponentiating the predicted mean in log-space does not generally recover the arithmetic mean in original space; estimate the desired original-domain statistic using a justified correction or samples. Student-t return models are not automatically valid raw-volatility models because volatility is nonnegative.

### 5.6 Observation selection and proprietary data

Record all eligible opportunities, not just executed profitable trades. Store why a candidate was not traded, which model was available, whether the actual outcome is observable and which simulation was used for counterfactuals. An unexecuted candidate has no actual fill/slippage outcome. A paper execution is not broker evidence. User practice and replay actions remain outside production strategy-promotion statistics under the parent contract.

Consented manual trades may support a separate research cohort, including losing and cancelled decisions. Do not transfer owner-private behavior data into shared multi-user models by default. Every join must retain permission and source lineage so revocation can trace through datasets, features, checkpoints and caches.

---

## 6. Validation chronology and bias defenses

### 6.1 Frozen temporal protocol

Each StudySpec fixes dataset snapshot, candidate universe, target, train/validation/calibration/test intervals, permitted historical context, training/refit cadence, feature version, cost policy, baseline set, trial budget, metrics, rejection criteria and final holdout. The locked protocol is recorded before the result is observed.

Training and preprocessing fit on training only. Validation selects hyperparameters/early stopping. A distinct calibration slice fits probability or uncertainty calibration. Outer test slices score unseen outcomes. The final untouched holdout is used only under a recorded evaluation authorization. Refit on additional data changes model identity and requires compatible renewed calibration; it cannot inherit the old calibrator solely because the architecture name stayed the same.

Use rolling or expanding windows according to the intended runtime policy. Native NeuralForecast cross-validation can simulate repeated prediction or refitting, but it does not replace VAN's information-availability, purge, embargo and grouped-cohort rules. Its cadence must match the production candidate-training plan rather than inadvertently train at every forecast origin in the backtest but once a month live. [S16]

### 6.2 Purging and embargo

Purge supervised rows whose outcome-information intervals overlap a held-out interval or whose label was unavailable at the training cutoff. Align split cutoffs across all related instruments used in a global model or peer features. Apply a declared embargo or gap where the labeling/execution dependence requires it. Respect the maximum label interval, not merely a cosmetic row count.

Historical inputs shared between successive predictions are not automatically leakage: a legitimate live forecaster also sees past data. Preserve lawful warmup/context while preventing future targets, future revisions or preprocessing statistics from crossing the boundary. Intraday observations and overlapping horizons are dependent; confidence intervals and effective sample sizes must reflect this rather than counting every overlapping prediction as independent evidence.

### 6.3 Native Freqtrade-inspired diagnostics

Implement two complementary diagnostics. **Prefix causality** compares values at an identical decision cutoff when given only the permitted prefix versus a larger dataframe with future data present but supposedly inaccessible. **Warmup stability** compares feature values and decisions after several startup history lengths, using tolerances justified for each recursive indicator. Features with a legitimate convergence period report it; they do not silently change live decisions because the backtest received a longer history.

Freqtrade documents lookahead-analysis and recursive-analysis as dedicated diagnostics. Adopt the behavior into VAN's event/feature/strategy APIs, not a wholesale bot runtime. Their existence does not mean all leaks can be found automatically. [S10–S11]

Required poison cases include next-bar features, negative feature shifts, centered rolling windows, full-dataset normalization, post-outcome duration, revised economic releases, incomplete higher-timeframe candles, misaligned peer clocks, whole-period universe selection and a label leaking through a cache key. A detector that passes the clean case but misses deliberate poison cannot qualify the feature path.

### 6.4 Comparable experiments and overfitting

Keep losing, failed and pruned trials. Trial counts include alternative features, horizons, calibrators, model families and execution policies, not just the last Optuna run. Publish the search space and dataset fingerprint with every selected model. Resampling and block-bootstrap choices are frozen or selected without peeking at the final holdout.

VAN's inspected policy requires DSR probability at least 0.95, PBO at most 0.10, at least 30 observations and at least three walk-forward windows. These are existing software policy fields, not a claim that 30 dependent trades are statistically adequate. Preserve the canonical fields; a qualified study must additionally justify sample adequacy, dependence handling and applicability of DSR/PBO. A probability threshold is not a raw Sharpe threshold. [S06]

---

## 7. Simulation correctness before model profitability claims

### 7.1 Reproduce current findings on the admitted source

The re-read main backtester traverses each bar open→low→high→close and uses a single-symbol DecisionCycle. Its terminal flattening occurs after the last equity-curve point is appended, while the summary reads final equity from that curve. These observations justify targeted reproductions; they are not results of executed tests in this blueprint. [S04]

The prior audit additionally found explicit spread/slippage in the paper adapter but no direct commission/financing debits in realized P&L, and closed-trade rather than full MTM reporting. Re-read those functions on the reconciled implementation before applying fixes. A newer branch may have already closed a finding, in which case retain the improvement and its current regression proof rather than patching it twice.

### 7.2 Intrabar and gap semantics

Use actual ticks or lower-timeframe observations where available. If only OHLC is available, define an ambiguity policy that cannot privilege short targets because the path was selected to be conservative for long stops. For a single bracket, report adverse feasible ordering or scenario bounds. For a mixed long/short portfolio, use **common feasible market paths**, not independently contradictory per-position histories falsely presented as one market realization.

Store when a stop/target result is ambiguous. A strategy whose apparent edge depends on ambiguous path selection requires finer data or remains unqualified. A gap across a stop executes according to the admitted available-price and slippage model, not automatically at the stop level. Price-limit and stale-market conditions preserve unfilled/unknown states.

### 7.3 Cost, fill and accounting parity

Charge spread/slippage through executable fills and book commission, financing, borrow, conversion, exchange fees, contract roll and other required costs separately without double counting. Respect fee currencies, tier changes, minimum order sizes, tick/lot rules and partial fills. Cost models used by the risk gate do not themselves debit the accounting ledger.

A signal requiring a bar close cannot fill at an earlier unavailable price. Specify observation delay, feature/inference delay and submission delay; execute at the next actually available event under the order policy. Limit orders require fill logic, cancellation races and volume/participation constraints, not a touch-equals-guaranteed-fill assumption.

Reconcile initial capital + realized trading cash flows + unrealized MTM + external cash movements to account equity. Record equity after terminal liquidation and all final charges. Mark risk at meaningful events, not only closed trades; show pending reservations and simultaneous exposures. Flow-adjusted performance must not fabricate returns from deposits or losses from withdrawals, while reduced collateral may still restrict risk.

### 7.4 Account replay and independent reproduction

Replay the same account coordinator, risk policy, trade lifecycle and reservation logic used by the live architecture through an isolated execution adapter. Do not sum unconstrained single-symbol profits to claim a feasible portfolio. Compare event-level eligibility, proposed intent, risk decision, order state, capital usage and realized outcomes under declared timing tolerances.

Qlib backtest reports may be retained as research diagnostics, but VAN's qualified execution/cost/accounting path is the economic authority. Freqtrade can be an optional isolated behavioral comparator for compatible crypto experiments, not a universal oracle for FX/ZSE/Deriv. Its own documentation states specific fee and execution assumptions; a comparator difference must be explained rather than declaring whichever result looks better correct. Existing LEAN or other independent-reproduction obligations remain parent scope. [S13]

No-trade output is a legitimate strategy outcome, but not complete proof of execution paths. Nonvacuous fixtures must exercise approved, reduced, rejected, cancelled, expired and protective actions. A replay with zero checked decisions cannot certify all of them.

---

## 8. Qlib implementation

### 8.1 Integration shape

Use a VAN-written loader over approved immutable snapshots, producing Qlib's indexed feature/label representation. Configure a fold-specific DataHandlerLP with explicit fit bounds and separate inference/learning processing. Preserve `datetime` and canonical instrument indices through DatasetH and every prediction export. Do not rely on train/test segment names to protect processor fitting: the transform's fitting window is a separate contract.

Qlib documents custom loaders, handlers and distinct data-processing layers. Use those interfaces rather than converting the entire live trading runtime to Qlib's default market assumptions. Benchmark feature sets such as Alpha158 may be reference candidates, not automatic universal feature definitions or China-equity assumptions for every VAN instrument. [S07]

### 8.2 Workflow and experiment tracking

Each Qlib task receives an immutable TrainingJobSpec, DatasetManifest, FoldPlan and adapter type from an allowlisted registry. The task runner resolves code from the pinned package/environment, not arbitrary strings supplied by an LLM or uploaded YAML. It logs parameters, data/target hashes, trial linkage, transforms, selected iteration and predictions through the configured Recorder bound to the shared MLflow run.

Use one experiment identity across Qlib and other providers. Native NeuralForecast workers may write to the same experiment contract without pretending they are stock Qlib LGBModel classes. Prevent duplicate nested runs from fragmenting lineage. Resume only against the same job/input identity and record attempts separately from the logical job.

Publish serialized native model artifacts and safe metadata explicitly. Do not make live inference load an unrestricted Qlib pickled Python model object or deserialize arbitrary Recorder objects from a user-controlled location. Training caches are scoped by snapshot/fold/feature/target/processor version; a cache created using future data cannot be reused in an earlier fold.

### 8.3 Objective compatibility is explicit

The inspected upstream `qlib.contrib.model.gbdt.LGBModel` accepts its `loss` argument only for `mse` and `binary`, and its data preparation expects one label column. Therefore multi-horizon, quantile and ranking support cannot be implemented by passing arbitrary loss names to this stock wrapper. [S09]

Implement `VanLightGBMAdapter` behind the shared model-provider protocol. It may delegate compatible single-label regression/binary tasks to the pinned Qlib wrapper. It must implement its own LightGBM Dataset/objective/validation/export route for quantiles and ranking, preserving Qlib task/recorder integration without modifying the trading runtime. Each target/horizon has its own model or explicitly validated multi-model bundle. Bundle membership and output schema are immutable.

### 8.4 No research defaults become trading policy

Do not import Qlib's strategy/executor, account sizing, exchange price-limit assumptions, region defaults, trading calendar, turnover rule or cash model into the live decision chain. Qlib-generated scores end at ForecastPacket. Portfolio construction is performed by VAN's existing qualified allocation and risk authorities under actual instrument specifications.

---

## 9. LightGBM implementation

### 9.1 Return and setup models

Start with supervised tabular models trained on VAN's own point-in-time features. A return regressor estimates a clearly defined scalar outcome. A setup classifier estimates a named event only for its trained population and execution policy. Their outputs must retain task/cohort/horizon identity; a BTC model is not automatically valid for EURUSD, nor an hour model for a day.

For classifiers, keep raw probability output separate from calibrated probability and from an ordinal opportunity score. Class imbalance handling, sample weights and candidate selection alter probability interpretation; calibrate and evaluate on the intended deployment population using held-out chronological data. Probability calibration cannot turn an information-free model into a profitable one.

### 9.2 Quantiles and ranking

Train quantile models for explicitly configured alpha levels and horizons; record alpha in each artifact. Check quantile crossing. Any correction, monotone rearrangement or joint quantile architecture is a versioned transform with evaluation, not an invisible plotting trick. A 5th-percentile terminal return is not a 5% probability of stop loss, because barrier events depend on the intervening path.

For LambdaRank-style training, form query groups by the same prediction cutoff and comparable eligible universe. Supply the objective's required nonnegative relevance encoding and contiguous group sizes, with encoding rules fitted/defined without final-test leakage. Raw continuous negative return labels must not be passed as relevance values by accident. If ranking the predictions of a regression model is the stronger simpler baseline, retain it. Ordinal rank is never advertised as a win probability.

### 9.3 Reproducibility and resource policy

The initial CPU reference profile uses fixed seeds, fixed row order/feature order, pinned package/compiler/environment, explicit thread caps and `deterministic=true` with one histogram mode such as `force_col_wise=true`. LightGBM documents CPU-specific deterministic behavior and warns that version/compiler/system changes can change results. Test exact-environment reproducibility and declared cross-environment tolerances; do not promise bitwise equality on arbitrary GPU hardware. [S14]

Starting research values are in the supplied profile: modest tree complexity and thread count, bounded boosting/early stopping and explicit sample checks. They are engineering starting points, not optimal trading parameters. Leaf/sample settings must be valid for the admitted dataset; a profile that cannot train meaningfully on a thin cohort should return insufficient-data rather than silently change the study.

Full rolling retraining is the initial adaptation policy. Repeatedly appending trees to a drifting model is not a substitute for measured retraining and can accumulate uncontrolled history/complexity. A warm-start or incremental variant is a separate candidate policy with independent tests.

### 9.4 Deployment artifacts and explanations

Export the native Booster format with a manifest of objective, feature order/types, categorical handling, target transform, normalization/imputation, fitted cutoff and selected iteration. Reload and compare predictions on golden input snapshots. Inference rejects missing/extra/reordered incompatible features, wrong transform hashes and nonfinite results.

Feature importance and local contribution methods are diagnostic evidence, not causal explanations. Preserve raw contributions and their units/expected-value reference; derived summaries must be fact-bound and must not manufacture reasons for an order the risk authority refused. Explanations are generated off the critical path and cannot change model or order decisions.

---

## 10. NeuralForecast implementation

### 10.1 One provider interface, model-specific capabilities

Use a common model-provider contract for `validate_spec`, `fit`, `predict`, `export`, `load`, `explain` and `describe_capabilities`. The actual supported input/output set remains model-specific. Enforce the pinned implementation's capability flags and a real behavioral test rather than assuming a constructor accepts meaningful historical/static/future inputs because parameters exist in a shared base class.

Map canonical snapshot data to `unique_id`, `ds`, `y` and documented exogenous columns. `unique_id` represents an admitted instrument/target/cohort identity, not a display ticker. Historical exogenous values must be observed by the origin. Future exogenous values are only genuinely known future information, such as a versioned market-session calendar; future returns, volume, actual economic releases and later consensus revisions are prohibited. Static features must really be static for the modeled segment or become time-varying vintages. [S17]

### 10.2 N-HiTS

Implement NHITS as the initial temporal challenger for multi-horizon return and realized-volatility tasks. Its hierarchical/multirate structure is a capability to test, not evidence it will beat tabular or HAR models on VAN data. Preserve model-specific input length, forecast horizon, loss, scaler, batch/window selection and training budget in the artifact. [S18]

Evaluate every horizon separately and as an explicitly weighted business objective. A strong one-step result must not mask a poor trading holding-period forecast. A cumulative-return target at horizon16 is not necessarily the sum of sixteen independently predicted one-step quantiles; compute the intended statistic consistently or use a validated path model.

### 10.3 N-BEATSx

Implement NBEATSx for historical and known-future context experiments. Compare the same target with and without permitted market/news/calendar covariates to establish incremental value. Decomposition outputs are exposed only for configurations that actually implement the relevant interpretable blocks. Trend/seasonality/exogenous contributions are a model decomposition, not proof that a news event caused a price move.

Maintain diagnostic readbacks for unavailable inputs and missing decomposition. Missing interpretability in a generic configuration is not grounds to fake a chart; the capability catalogue declares what the fitted artifact supports. The required contextual plugin itself must still train, forecast and round-trip through the common interfaces.

The N-BEATSx provider behavior and the capability-driven separation are grounded in current upstream model references. [S18]

### 10.4 DeepAR and probabilistic paths

Use domain-valid distributional objectives for return or transformed positive targets. Record distribution family/parameterization, loss, sample count and RNG scheme. Retain individual temporal trajectories through a tested provider adapter before any averaging; verify shape, units and horizon ordering against actual native outputs. If the locked convenience API only returns aggregated predictions, implement the raw-path adapter rather than claiming the aggregated result is a scenario ensemble.

Autoregressive trajectories can encode within-series temporal dependence. They are not automatically calibrated, and global training across assets does not create a jointly sampled portfolio. Cross-asset scenarios require an explicit dependence model or common multivariate generator and its own evaluation. A marginal interval at each horizon is not a simultaneous path-coverage guarantee.

These capability assumptions must be checked against the exact implementation because current DeepAR documentation contains prose/signature discrepancies; the source register records that limitation. [S18]

### 10.5 TFT, PatchTST and iTransformer challengers

Deliver working research plugins with the same dataset/fold/serialization/inference contracts. Their configured scientific role is conditional: TFT for contextual multi-horizon experiments, PatchTST for temporal sequence representation, and iTransformer where aligned multivariate cohorts and its verified capabilities are suitable. No plugin receives live preference because it is larger or uses attention.

The programme does not require unrestricted brute-force search across every architecture. Build the admitted plugin set in full, then let preregistered empirical comparisons decide whether a model is used, rejected or insufficiently supported. A cohort without enough aligned data may produce a complete `INSUFFICIENT_DATA` evaluation, while the plugin remains verified on an admitted adequate research dataset.

### 10.6 Losses and uncertainty outputs

Integrate point losses, multi-quantile losses and distributional losses according to target semantics. Score quantiles with pinball loss and coverage/width; score full distributions with proper scoring rules where supported; score return decisions after actual costs separately. A robust Huber loss can be a candidate, but never delete genuine extreme market observations simply to improve fit. [S19]

For quantiles, carry alpha, target, calibration status and empirical coverage. For distribution parameters, carry the native family/version and units. For raw scenarios, carry samples and dependency interpretation. Do not collapse all three into a single ambiguous `confidence` field.

### 10.7 Safe persistence and native cross-validation

Current NeuralForecast documentation describes safetensors plus JSON for newer saves, explicit legacy pickle consent and restrictions on remote loading. Pin a tested release with the required format and use closed, reviewed class registries. Stage artifacts through the verified model admission store and load verified local bytes, not user-controlled URIs or arbitrary serialized classes. Any legacy conversion happens in an isolated trusted migration environment; never enable general `allow_pickle=True` in serving. [S20]

Use native cross-validation as an implementation aid while enforcing VAN's FoldPlan, label maturity and retraining schedule externally. Do not silently switch between one-fit evaluation and refit-every-window behavior. All scalers, categorical vocabularies and calibration artifacts are bound to the appropriate fold/model identity.

---

## 11. Freqtrade and FreqAI capability adoption

### 11.1 What to adopt and how

| Donor capability | VAN-native implementation | Why not copy the surrounding bot |
|---|---|---|
| Training separated from inference | Dedicated research workers, model preloading and bounded ForecastService | VAN retains its own risk, broker and lifecycle authority |
| Repeated training and expiry | Per-scope candidate jobs, cadence/drift policy, TTLs and last-qualified fallback | Retraining must not silently promote a model |
| Feature expansion | Registered lag/timeframe/peer DAG and incremental validation | Existing feature definitions remain canonical |
| Prediction reuse | Immutable cache keyed by data/model/target/transform/scope | A convenience identifier alone is insufficient provenance |
| Novelty/outlier filters | Versioned DI-style distance, optionally PCA/SVM/DBSCAN with train-only fit | Novelty is not calibration or confidence; genuine tails stay in evaluation |
| Lookahead and recursive analysis | Prefix-causality and warmup diagnostics over VAN paths | No need for Freqtrade's account/execution runtime |
| Hyperparameter optimization | Shared Optuna study controller and immutable trial census | One optimizer budget, not competing tuning systems |
| Cooldown/stop-loss/low-profit guards | Entry-suppression proposals consumed by existing RiskAuthority | No duplicate global drawdown or kill-switch governor |
| Dry-run discipline | Real-data shadow and isolated paper accounting through VAN | Paper P&L is never represented as actual live fills |

FreqAI documentation provides rolling training, expiration and persisted prediction/model concepts; Freqtrade documents optimization and plugin-based protections. This blueprint specifies native contracts compatible with VAN's existing ownership rather than assuming those components can be transplanted unchanged. [S12–S15]

### 11.2 Retraining policy and job states

A candidate job has `REQUESTED → VALIDATED → QUEUED → RUNNING → EXPORTING → EVALUATING → CANDIDATE_READY` or explicit `FAILED`, `CANCELLED`, `INSUFFICIENT_DATA` and `OUTCOME_UNKNOWN` states. These are separate from model approval and runtime binding. Persist logical job ID, attempt ID, immutable input digests, scope, lease epoch, resource admission and publication identity.

Scheduled and drift-driven triggers use the existing durable workflow/scheduler. Coalesce obsolete repeated requests only with recorded supersession; never discard work invisibly. Limit per-scope concurrency, threads, memory, runtime, disk and total study budget. A failure retries the same immutable job only when safe; a changed data snapshot creates a new job. Cancellation during export or publication reconciles the result instead of declaring it never existed.

Model training completion cannot change a live binding. The scheduler submits the candidate for independent evaluation and records the outcome. An old model can continue only if its own freshness/admission policy remains valid. Waiting for a retrain does not extend expiry automatically.

### 11.3 Novelty and sample handling

Keep data integrity, feature-domain novelty, calibration quality, model age and market-regime mismatch as separate flags. A feed may be valid while its feature vector is far from training experience. Conversely, a familiar feature vector can be based on stale quotes. Unknown values must not default to healthy.

Fit novelty transforms on training data only. Evaluate abstention coverage: how many real opportunities are rejected, in which regimes, and with what outcome distribution? A filter that excludes every difficult period may produce attractive reported skill but a weak or unusable strategy. Preserve extreme outcomes in the study and show conditional results for accepted and rejected regions.

### 11.4 Suppression policy

Implement per-account/environment/strategy/instrument/direction cooldowns and loss/profit windows where admitted. Define event counting at completed trade/family outcome level, not per partial fill. Deduplicate observations, persist lock start/end/reason, and use market-calendar or elapsed-time semantics explicitly. Apply suppression to new or expanded risk only.

Reuse existing drawdown, kill, strategy-health and scale-in cooldown behavior. A new suppression may tighten eligibility, never clear an owner halt or loosen a signed mandate. Conflict resolution is deterministic: the strictest applicable block remains, with all contributing reasons inspectable. Restart or mode change cannot silently erase the lock.

### 11.5 Source-use boundary

Freqtrade's repository is GPLv3; NeuralForecast is Apache-2.0; the inspected Qlib wrapper and LightGBM licence are MIT. Keep dependency and donor provenance with the exact adopted artifacts. The default Freqtrade route here is independent VAN code implementing documented behavior. Direct reuse or distribution of GPL code requires the corresponding licence obligations; merely placing copied code behind an API is not asserted to remove them. This is an engineering source-use choice, not a substitute for review of the actual distribution arrangement. [S09, S21–S23]

---

## 12. Calibration and forecast trust: extend VAN, do not duplicate it

### 12.1 Existing conformal implementation is the starting boundary

VAN already has a residual-based conformal component. Preserve its deterministic and reduce-only consumer semantics, but add explicit calibration provenance, target type/direction, model/transform identity, horizon/cohort, residual observation cutoff and empirical evidence. Separate probability calibration from interval calibration: they are not interchangeable. [S05]

A lower return bound may be relevant to an opportunity threshold; an upper cost or volatility bound may be relevant to adverse risk. Do not feed every target into a lower-bound-only `admits` check and assume the sign is correct. Add typed target-specific evidence adapters, while RiskAuthority remains the only owner of any decision that follows.

### 12.2 Calibration procedures

For binary event probabilities, compare raw output with calibrated candidates such as logistic or isotonic mappings trained on a separate chronological calibration set. Freeze calibrator selection without using the final test. Store event prevalence, binning/reliability method, Brier/log loss, ECE definition where used, sample counts and uncertainty. Small samples can make flexible calibration worse; report insufficient evidence rather than manufacture precision.

For quantiles and intervals, measure pinball loss, width, coverage and violation clustering by horizon/cohort/regime. If conformalizing, define residual score, quantile calculation, calibration window and validity assumptions. A nine-residual mathematical minimum in existing code is not adequate empirical confidence in a trading model. Standard conformal guarantees require assumptions such as exchangeability; changing dependent financial series do not automatically satisfy them. Report measured coverage and limitations instead of unconditional distribution-free trading guarantees. [S05, S24]

Refit or materially changed model/scaler/target invalidates the old calibration binding. Calibration residuals require matured outcomes. Known source corrections and data-domain shifts can revoke a calibrator even before its time-based expiry.

### 12.3 Trust state is structured

For event markets, calibration is grouped by underlying event, forecast horizon and admitted category. Quotes near or after the true outcome becoming known cannot be pooled with early tradable forecasts to claim useful calibration. Administrative close, resolution and available-cash times are distinct from the outcome-information time. Source agreement is a consistency test, not independence; see §22.7–22.9.

Forecasts expose separate dimensions: `data_quality`, `model_freshness`, `calibration_state`, `novelty_state`, `scope_match` and `admission_state`. Their aggregate status is a deterministic policy result, not an LLM judgment. `READY` means a structurally usable forecast for the declared use scope; it does not mean a trade is allowed.

Use explicit `ABSTAINED` reason codes including `DATA_STALE`, `MODEL_EXPIRED`, `CALIBRATION_STALE`, `INSUFFICIENT_CALIBRATION`, `OUT_OF_DOMAIN`, `UNSUPPORTED_COHORT`, `FEATURE_MISMATCH`, `SERVICE_TIMEOUT`, `MODEL_UNAVAILABLE`, `NONFINITE_OUTPUT`, `ARTIFACT_REVOKED` and `EVIDENCE_INSUFFICIENT`. Keep a missing prediction missing; never replace it with a fabricated neutral zero while calling the model healthy.

---

## 13. Serving, fusion and integration with VAN modes

### 13.1 Bounded serving

Load verified artifacts before activating a serving binding. Keep the last qualified version available for rollback, but only within its actual allowed scope and age. A change is an atomic compare-and-swap of immutable model/feature/calibrator/use-policy identities, with a new epoch. Each account decision snapshots the binding once so a mid-cycle update cannot mix model versions.

Cache keys cover project/cohort/instrument/venue, target, horizon, feature-definition digest, input snapshot/cutoff, model artifact, calibration artifact, transform, sampling policy and admitted-use epoch. Same key means the same material prediction contract; timestamp-only or model-name-only keys are insufficient. Persist the originally issued forecast and outcome linkage; never overwrite history after a new fit.

The core loop consumes a precomputed local forecast snapshot with a bounded read deadline. It must not resolve MLflow aliases, deserialize weights, fetch remote features or call a neural service synchronously while protecting orders. Worker and service failures produce explicit abstention and telemetry.

### 13.2 Fusion must earn its complexity

Begin with each model evaluated independently. Combine models only when their out-of-fold forecasts add useful information beyond the strongest simple/incumbent model. Fusion training uses OOF inputs and its own held-out calibration/test protocol; in-sample model predictions are not valid training evidence for the combiner.

Compare simple blends, tabular meta-models and regime-conditioned weights only as controlled candidates. Preserve each component's task and units. A return forecast and volatility forecast are different quantities, not numbers to average. Detect shared features, correlated errors and duplicated signals so three variants of the same model do not count as three independent confirmations. Every added model has an ablation result and an explicit removal/fallback rule.

### 13.3 Modes are opportunity policies, not model authority

Normal, Risky and Aggressive remain orthogonal to the underlying live/demo authorization states and signed risk ceilings. A model may change ranking or supply qualified evidence within an admitted strategy policy; it cannot enlarge authority merely because confidence rises.

For Aggressive, implement the real independent edge-evidence producer and binding required by the parent BE-013 contract. Do not stop at an empty typed dataclass or a permanent refusal path. Qualify the sandbox positive path and the missing/expired/wrong-scope evidence refusal path. Live use still requires real economic evidence and an owner-authorized mandate; no model-origin approval is accepted.

Keep news-policy controls intact. A learned model using news must not indirectly bypass reduce-only D1–D6 policies or the separately qualified D7 event-strategy/ticket conditions. Forecasting is not a shortcut around source agreement, event timing, account state or nonce consumption.

### 13.4 Failure fallback

A strategy explicitly dependent on a forecast refuses new entries if required evidence is missing or invalid. A baseline strategy that was qualified without that model may continue under its existing policy only when the admitted fallback says so. Model failure does not create a blanket license to trade without required checks, nor does it unnecessarily shut down unrelated qualified capabilities.

During uncertainty, preserve risk reduction, truthful broker status and operator visibility. A unavailable broker still creates an unknown effect requiring reconciliation; the forecast system must not claim it closed a position merely because it asked for risk reduction.

---

## 14. Contracts, API and storage obligations

### 14.1 Shared typed records

The eight inherited contract schemas cover `DatasetManifest`, `TargetSpec`, `FeatureManifest`, `TrainingJobSpec`, `ModelArtifactManifest`, `ForecastPacket`, `QualificationRecord` and `DeploymentBinding`. Ten additional prediction-market schemas cover source scope, exact contract semantics, book observations, event distributions, conditional asset responses, bounded proposals, study protocols, execution scenarios, arbitrage and market-making policies; see §22.18 and `contracts/CONTRACTS_AND_SEMANTICS.md`. They are proposed interchange contracts, not claims that current endpoints accept them. JSON Schema checks shape; separate semantic validators must check clocks, identity references, permissions, numerical domains, receipt trust and cross-record compatibility.

Every record includes schema version, canonical ID and explicit environment/use scope. Hashes bind content-addressed material identities; signatures and trusted verifier references remain separate. A record with an arbitrary valid-looking hash does not prove the referenced artifact exists.

### 14.2 ForecastPacket minimum semantics

A packet identifies the precise instrument/cohort/target/horizon, source snapshot and cutoff, model and feature/transform revisions, calibration identity where applicable, train-label cutoff, generated time and expiry. It carries typed scalar means, quantiles, event probabilities or raw scenario references only where supported. Field-level labels describe gross/net basis, original/transformed units and marginal/path/joint scope.

Probability fields require a named event and admitted calibration evidence for the intended population. A rank score and legacy confidence score remain separate. An abstained packet has no usable forecast payload, but retains reasons/provenance so diagnostics can explain the missing evidence.

Predictive values may be floating-point with declared precision; reject nonfinite values and incompatible domains. Monetary balances, fees, orders and authoritative sizing remain exact existing decimal/minor-unit contracts. A conversion to a risk feature is bounded and tested; displayed rounding never re-enters financial arithmetic.

### 14.3 Operations and readbacks

| Proposed operation family | Permitted effect | Required durable outcome |
|---|---|---|
| Forecast read / forecast history / uncertainty detail | Read-only | Snapshot, freshness, model/task identity and abstention/evidence |
| Dataset preview / quality report / feature lineage | Read-only or bounded research snapshot creation under entitlement | Dataset ID, availability/provenance and completion/error report |
| Research request / cancel / status | Bounded scoped compute job | Logical job/attempt IDs, resource admission, state and artifact or unknown outcome |
| Model comparison / explanations / outcome attribution | Read-only | Matched cohorts/targets and source-backed results, not raw unverified model claims |
| Retraining schedule proposal / change | Existing owner/scheduler permission | Versioned schedule, scope, budget and next/last run readback |
| Model use proposal / revoke / rollback | Existing independent model/strategy admission route | Verified exact binding, decision epoch and revocation/readback; not an MLflow alias |
| Protection-policy review | Existing risk-policy owner | Preview of changed scope and policy, independently applied outcome |
| Export evidence / erase consented research data | Scoped owner policy | Artifact manifest or traced erasure/retention-exception receipt |

Resolve actual routes against the gateway during PRE-002. Extend existing endpoints where contracts align. No arbitrary code, unbounded query, model download URL, broker credential or root command is accepted as a general research request. Each effect has idempotency, authorization, argument digest, lease/epoch, cancellation semantics and receipt lookup.

### 14.4 Storage and event behavior

Use append-only or versioned research/evidence records in the existing store with scoped object artifacts. Large forecast samples and model binaries live in content-addressed storage; the financial ledger keeps exact references and decision inputs, not unbounded tensors. Keep operational logs, immutable qualification evidence, datasets and financial records under distinct retention policies.

Transactional outbox and reconciliation provide effectively-once business effects; do not assume networks deliver exactly once. A timeout while publishing or changing a model binding must be reconciled before retrying. Foreign key/identity checks prevent forecasts from another account/cohort/environment being used. A cache or MLflow outage cannot mutate financial truth.

---

## 15. Scientific evaluation and economic admission

### 15.1 Task-specific metrics

| Question | Mandatory comparison/evidence |
|---|---|
| Does return forecasting add information? | Matched loss against zero-return/persistence/linear/tabular baseline; directional and rank metrics as diagnostics; error by horizon/cohort |
| Is a binary probability useful? | Brier/log loss, calibration/reliability and event prevalence, discrimination, coverage of eligible candidates, utility after costs |
| Are quantiles or distributions honest? | Pinball/proper scores, realized coverage/width/violation clustering, tail and domain tests, calibration sample/dependence limitations |
| Is volatility useful? | HAR/GARCH/simple historical baseline, original-domain loss and QLIKE where appropriate and domain-valid, performance by horizon/regime |
| Is ranking actionable? | Cross-sectional rank quality with enough comparable instruments, turnover/cost/capacity, feasible account allocation |
| Does VAN improve? | Same-time counterfactual comparison of VAN alone versus VAN plus the candidate, matched fills/costs/risk constraints and uncertainty |
| Does the system remain safe? | Reproducible risk decisions, no authority bypass, failure/recovery, capacity and protection noninterference |

Raw accuracy is not the admission metric. A classifier can be accurate by choosing a frequent event while adding no economic value. A lower price MSE may reflect persistence rather than return predictability. Coverage alone is also inadequate when intervals become so wide that no useful decision remains.

### 15.2 Incremental-value protocol

Predefine utility `U` for the actual use: for example cost-adjusted return with explicit drawdown/turnover/risk penalties or a volatility sizing objective under fixed limits. Evaluate `ΔU = U(VAN + candidate) − U(VAN baseline)` on identical admissible opportunity streams. Report uncertainty under serial/cross-sectional dependence, economic materiality and performance concentration. The owner/reviewer sets the materiality and risk limits before the final result, not afterward.

Run cost stress (including at least the existing required doubled-cost case), delay/slippage/gap stress, spread/liquidity drought, model outage, regime change and ablations. Not every hypothetical stress must produce profit, but loss/coverage/failure outcomes must satisfy the admitted risk policy. Do not revise failed thresholds after observing the holdout.

Model selection considers compute cost, latency, abstention rate, data coverage and maintenance burden alongside statistical skill. A neural model that adds negligible value at much higher cost is rejected for that use even when its framework is correctly integrated. The simpler strongest qualified candidate remains eligible.

### 15.3 Certificates and evidence chain

Qualification must bind exact dataset/feature/target/fold/cost/model/calibration/fusion/use-policy versions, all trial references, realized results and reviewer identity. The existing trusted verifier checks the actual evidence and issues any authority-bearing certificate. The training worker cannot write its own success certificate, register its own verifier key or turn a fixture into live evidence.

Separate forecast quality, economic suitability, software/runtime qualification and live strategy/account authority. A forecast useful for a displayed research panel need not be admitted to capital allocation. A model admitted for volatility research cannot later be used as a return signal without a new scope-specific decision.

### 15.4 Prospective shadow and canary

Before consequential live use, persist forecasts before outcomes exist and compare the exact admitted pipeline to its baseline prospectively. Choose sufficient independent event/trade opportunities and regimes based on uncertainty/power, not only “seven days passed.” Thin daily markets may require much longer than liquid intraday series. Counts of overlapping predictions do not substitute for independent evidence.

The full real incoming-data shadow pipeline and controlled sandbox admission/revocation must work before backend closure. Continued economic observation can remain an honest model state after software completion. Live canary exposure is separately owner-authorized, bounded by existing risk policy and reversible. A software canary is not a financial mandate.

---

## 16. Operations, resource placement and recovery

### 16.1 Deployment topology

**Intended hosting:** Netcup / Oracle VM topology, as directed by the owner. Resolve the actual instance, architecture, region, capacity and existing transport from live evidence at deployment. Do not infer location from a cloud brand or confuse the phone used for control with the machine executing trades. This document makes no new server purchase, provider application or deployment change. No licence procurement is scheduled; source-specific use status is tracked separately under §22.2.

Use Global DIAL as the default owner ingress for authorized project operations, Zuul for admission and the existing estate execution/deployment boundary for VM changes. Do not run VAN work on the forbidden owner desktop, silently move project testing into the chat container, bypass signed gates or treat stale placement figures as current headroom. Artifact formatting/checks performed in this conversation container are document work only, not runtime qualification.

Training workers have no broker/order credentials, no authority-store write access and no ability to grant model use. Inference has read-only access to admitted artifacts and feature snapshots. The arbiter consumes evidence; risk and execution remain separate. Administrative installation, service changes, external charges and new providers require the applicable owner authorization.

Prefer CPU LightGBM as the initial reference workload and measure actual neural costs before committing accelerators. A qualifying environment must prove supported wheels/builds, available RAM/disk, bounded CPU/threads and noninterference with existing services. Avoid one hidden thread pool per library saturating the host. GPU workers may be separately placed when justified; no GPU purchase is authorized here.

### 16.2 Proposed service objectives

Initial engineering targets, subject to measured admission, are a bounded local forecast read of no more than 100 ms p95 for precomputed/cache-backed access, no model/network wait inside T0, explicit per-model inference budgets appropriate to the bar cadence, and bounded cancellation/lease recovery. These are **targets**, not observed performance. The critical risk/protection deadline is inherited from VAN and must not regress.

Fix memory, CPU, concurrent fits, artifact/sample retention, thread counts, max input size and total job time in each admitted profile. A model that cannot fit within the budget queues, fails admission or moves through an authorized placement route; it must not borrow unbounded live trading capacity. Configure output-size limits for scenario samples and explanations.

### 16.3 Recovery matrix

| Failure | Required behavior |
|---|---|
| Trainer killed or worker lease lost | Record interrupted attempt; resume/retry under same immutable input identity; no duplicate artifact publication |
| Partial artifact upload / corrupt checkpoint | Quarantine; keep previous valid binding if still qualified; no partial load |
| Registry unavailable | Already admitted local artifact can serve only within its validity; no mutable alias lookup in T0 |
| Feature store unavailable or epoch gap | Use only a still-valid exact snapshot; otherwise abstain and reconcile |
| Model expired / calibration revoked | Dependent entries refuse or use separately admitted fallback; protection continues |
| Model update during a decision | Decision retains one binding epoch; later decisions see the new valid epoch |
| Disk full / queue saturation / memory pressure | Bounded backpressure, safe job refusal and retention policy; no dropped financial events |
| Rollback after schema evolution | Restore compatible software/model, preserve newer financial records; explicit migration/read compatibility |
| Broker outcome unknown | Existing reconciliation controls apply; the ML service never reports invented execution success |
| Source consent revoked or data corrected | Trace and invalidate affected descendants, bindings and cached projections; retain permitted audit evidence |

### 16.4 Observability

Trace source cutoff→feature snapshot→training job/model→forecast→arbiter outcome→risk decision→order/fill→realized outcome. Record forecast age, model/calibrator age, inference latency, queue wait, active memory, cache hit/mismatch, OOD/abstention rate, drift, calibration coverage, forecast skill and incremental utility by scope.

Alert on genuine degradation with distinct unknown/stale states. An empty queue is not proof of a healthy model. Redact secrets and owner-private feature values from routine logs; detailed evidence uses permissioned artifact access. Backups and restoration must preserve artifact references and model/decision epochs, not only MLflow table rows.

---

## 17. Full backend-to-frontend consumption contract

No new screens are implemented before the parent's current BG-001. Backend work produces all necessary versioned fields, actions, error states and real receipts. After that, the full-product design stage places them in the locked dark/light native design; the backend catalogue is not a schema dump masquerading as a UI.

| Surface family | Required later experience | Parent duties |
|---|---|---|
| Trading / Markets / Watchlists | Qualified opportunity ordering, model availability, horizon selector, stale/abstain explanations, filters and alerts without trade authority | FE-006 |
| Chart / Replay | Properly labelled forecast bands and horizon/cutoff, historical issued forecasts, actual-vs-predicted comparison; no fabricated future candles | FE-007/008 |
| Order review / Positions | Which qualified evidence contributed, current risk decision, model-dependence/fallback status; no raw forecast sizes | FE-009 |
| Portfolio / Risk / TCA | Realized volatility/cost diagnostics, calibration limitations, marginal-versus-joint risk distinction and protection reasons | FE-011 |
| Strategies / Modes / Promotion | Model/capsule versions, comparison evidence, scoped admission, rejected/inconclusive candidates, owner review and rollback | FE-012 |
| Analyst / Research / Diagnostics | Studies, baseline comparisons, feature/target lineage, noncausal explanations, scenario semantics and consented manual-pattern research | FE-014 |
| News / Events / Armed-plan review | Frozen expectations, source quality/disagreement, event-vs-asset meaning, D1–D7 effects and read-only event-lab evidence; no new event-contract buy/sell route | FE-013 |
| Work / Evidence | Genuine training progress, attempts, lease, cancellation, source/artifact identity and independent review | FE-015/018 |
| Memory / Automation / Settings | Data use/erasure, retraining schedules, budgets, model expiration, provider health and notifications | FE-019/020/022 |

Every surface implements empty, loading, ready, stale, expired, rejected, inconclusive, unsupported, unauthorized, offline and unknown states where applicable. An uncalibrated legacy confidence score retains its existing label. A new calibrated event probability must identify event, horizon, population, calibration vintage and limitations, and its wording must be admitted into the parent's probability-label rules rather than silently replacing them.

Do not add dense research dashboards to Home, expose dozens of model switches as mandatory choices or implement scientific domain logic in Compose to avoid backend work. Keep detailed evidence reachable through context-specific navigation. Both themes, screen-reader semantics, reduced motion, landscape/large text, lifecycle restoration, version changes and physical S24 behavior are mandatory later acceptance work. [S01–S02]

---

## 18. Packet roadmap and delivery policy

The canonical child plan has **48 packets**, detailed in `plan/IMPLEMENTATION_PLAN.md`. It is dependency ordered, not a set of optional suggestions. The JSON packet array and rendered plan are topologically sorted: new037–048 execute before existing030–036 according to their prerequisites, despite their higher identifiers.

| Range | Full deliverable | Principal closure |
|---|---|---|
| 001–003 | Source/parent reconciliation, complete scope/contracts and independent F15 entry | No-loss source mapping and real predevelopment authority |
| 004–011 | Environments, data/features/targets, temporal diagnostics, simulator/account replay and Qlib bridge | Actual usable research foundation; corrected economic measurement |
| 012–019 | LightGBM objectives, baselines/XGBoost, NHITS/NBEATSx/DeepAR and declared neural challengers | Real training/export/load/inference per admitted plugin |
| 020–024 | Calibration, Optuna studies, artifacts/registry, adaptive retraining and forecast serving | Full stable model lifecycle with freshness and abstention |
| 025–029 | Arbiter/modes, protections, outcomes/data moat, complete APIs and VM operations | Actual consumers, independent financial boundaries and recovery |
| 037–048 | Source/event semantics, probabilities, conditional response, value/cash/queue/arbitrage/market-making research, four studies and full integrations | Mandatory backend work upstream of030–033; numeric IDs preserve lineage, not execution order |
| 030–033 | Scientific reports, real shadow/sandbox, independent additive closure and parent BG integration | Every mandatory backend engineering obligation and parent barrier |
| 034–036 | Later locked-design screens, actual device/whole-product acceptance and release | Software acceptance and separate model/strategy live authorization |

### 18.1 Packet exit rule

Each packet completes its specified operations, not just its happy path. It must provide source/artifact/environment identity; real producer and consumer; persistence/idempotency; authority check; positive, negative and recovery evidence; and a documented rollback. Code reviews and passing unit suites do not replace real package/service integration. Synthetic cases remain necessary for edge/fault tests but cannot be reported as profitable trading evidence.

Model research and economic evaluation may parallelize only when dependencies and compute budgets permit. A common parent contract may be implemented once and referenced by many packets; duplicating the same service across adapters is forbidden. No independent agent receives unscoped repository or live trading rights just because it owns a packet.

### 18.2 Adoption milestones are not artificial feature cuts

The early LightGBM baseline is an integration milestone, not the final scope. N-BEATSx, DeepAR, scenario retention, challenger plugins, calibration, OOD, protections, projections and recovery remain mandatory engineering duties. A feature cannot be silently moved to “future work” to make backend completion easier. Genuine scientific rejection is recorded with implemented capability and actual evidence; missing functionality stays blocked.

### 18.3 Parent artifacts to amend at implementation admission

Update the actual parent `DEVELOPMENT_PLAN.json` and renderer output, requirements/traceability maps, affected BE contracts, BQ evidence definitions, BG scope/consumer bundle, screen action contracts and relevant stack-lock/resource records. Preserve original parent source fingerprints as lineage. Re-run the true parent graph and authority validators on the combined graph; the supplied additive checker does not understand or certify every original parent action.

---

## 19. Acceptance, unresolved decisions and release gates

### 19.1 Mandatory evidence levels

**L0 Document structure:** IDs, links, schemas, dependencies and coverage shape. This pack can check selected L0 properties only.

**L1 Source and component:** actual implementations, unit/property/mutation tests, serializer and adapter behavior on exact source.

**L2 Integration and environment:** real locked upstream libraries, real permitted datasets, actual gateway/auth/worker/registry/feature services and VM resource/recovery tests.

**L3 Scientific/economic:** reproducible out-of-sample and prospective evidence, matched baselines/costs, calibration and uncertainty, independently reviewed scope-specific use.

**L4 Product and live authority:** current parent whole-backend certificate, actual app/device acceptance, software release, and separately authorized per-model/strategy/account live use.

No lower level substitutes for a higher one. A model may have L2 engineering proof and an L3 negative result without being a broken integration; it still has no L4 permission to influence live trading.

### 19.2 Owner/reviewer decisions with exact blocking scope

The current owner has resolved the procurement choice for this phase: **do not obtain a new licence now**. This is not an unresolved purchase gate on software implementation. Existing/public source-use terms and actual account eligibility remain factual scoped checks before affected external operations, not evidence inferred from VM placement. Contract design, synthetic tests and other authorized work continue. The parent still requires genuine source/service proof where applicable; no fixture can close an unavailable real-provider gate.

| Decision | Must be resolved before | Safe preparation meanwhile |
|---|---|---|
| Initial research cohorts, instruments, horizons and data entitlements | Dataset admission and real evaluation | Contract design and synthetic causal fixtures |
| Owner scope and formal parent F15 signature | Code-bearing execution | Read-only reconciliation and blueprint review |
| Research compute/paid provider budget and placement | Charged work or actual deployment changes | Static packaging specification and measured no-charge discovery |
| Economic materiality, risk noninferiority and model-use policy | Final holdout evaluation/admission | Implement metric computation and negative controls |
| Probability/interval display semantics and calibration adequacy | Consequential probability use and later UI acceptance | Keep raw score labelled uncalibrated |
| Existing stop recovery, currency, news and temperament decisions | Their affected parent backend/live gates | Preserve current qualified policy and mark conflicts explicitly |
| Model auto-promotion policy | Any proposal to automate consequential promotion | Default: candidate training only; no automatic live promotion |
| New exchange/provider expansion | Its integration/financial actions | No implied crypto execution or new accounts |

Do not invent percentages, authority signatures, account identities or budgets to close these decisions. Dependency delays do not justify thinning another feature, but unrelated safe preparation can proceed within current authorization.

### 19.3 Release and negative-result behavior

The software can present a complete research capability that correctly reports `NO_QUALIFIED_MODEL` and lists why candidates failed. That is superior to shipping an unsafe model to satisfy a superficial “AI enabled” requirement. The complete positive sandbox path, actual model providers and callable services must nevertheless be proven; “no model qualified” cannot hide an unbuilt training pipeline.

For each live admission, bind model+calibrator+feature+fusion+strategy+account/cohort+horizon+execution/cost policy+expiry. Revocation removes future influence without rewriting issued forecasts, financial outcomes or audit history. Rollback selects a previously qualified compatible binding only if it remains admissible. Otherwise the dependent strategy abstains while existing protection continues.

---

## 20. Execution handoff to coding agents

The authoritative handoff is `CODING_AGENT_HANDOFF.md`. An agent must first resolve the current VAN context, compare the parent and source identities, acknowledge required project context and inspect all relevant unfinished branches. It must treat this document as proposed scope until properly admitted into the parent programme.

For every packet, the agent records what it actually changed, what commands/tests ran, which exact environment/source was tested, which evidence is independent, what remains blocked and what safe work can continue. It never marks source count or schema presence as functional completion. It preserves the original service owner, does not run on the forbidden desktop, uses Global DIAL's current typed/authorized route and does not start an unapproved parallel live executor.

An agent producing more installation files but no real fitted-model round trip has not completed a model packet. An agent producing an excellent forecast plot but no cost-corrected account comparison has not qualified economic use. An agent writing its own `APPROVED` receipt has not obtained independent authority.

---

## 21. Definition of done

The adoption is complete only when the admitted scope has all of the following: preserved parent and branch capabilities; exact safe dependency/environment locks; point-in-time data/features/targets; bias-tested chronological studies; corrected cost/account simulation; usable Qlib/LightGBM and every specified NeuralForecast plugin; calibrated uncertainty with honest limitations; bounded retraining and serving; actual arbiter/mode/edge producer and protection integration; complete owner APIs and evidence readbacks; source-bound independent backend and recovery proof; renewed whole-product BG-001; later full native action/state coverage; actual device/owner acceptance and controlled software release. The integrated prediction-market scope additionally requires the full source/event/distribution/calibration/asset-response chain, exact D1–D7 consumers, all three event research labs, four frozen comparative studies, truthful source states and corresponding recovery/projection contracts. Scientific rejection of a feature is valid; omitting its mandatory research implementation is not.

Live forecast influence is additionally restricted to models and strategies whose own economic evidence and owner authority are valid. Rejected and inconclusive candidates remain visible, their complete research capabilities remain usable, and their live influence remains disabled.

**Current delivery truth:** this document and its supporting plan/contracts are created. Application implementation, model fits, upstream integration tests, VM deployments, economic studies, broker actions, independent semantic review, F15, BG-001 and live promotion have not been performed by producing this pack. Only the separately reported document checks were run.

## 22. Integrated prediction-market intelligence and event research

### 22.1 Objective and adopted scope

The objective is to discover whether event-market information improves VAN's decisions **at comparable risk, with feasible information timing and after costs**. The source is not admitted as an oracle. An economically rejected feature may remain useful labelled context; lack of demonstrated edge must never be concealed by a forecast plot or a backtest selected after its result was seen.

The macroeconomic and cryptocurrency-volatility studies motivate testing market-implied distributions and risk information, not a blanket claim of profitable directional trading. Exchange-authored calibration research and independent author research describe different samples and biases. These findings justify category/horizon-specific replication rather than assuming either perfect calibration or useless prices. [S33–S34, S37–S38]

The adoption has five complete capabilities: probability/uncertainty intelligence; calibrated event-to-asset and forecast-to-position evidence; execution-realistic evaluation; payoff-consistency and cross-venue arbitrage research; and specialized inventory-aware market-making research. The first three are the initial economic priorities. The last two are **mandatory usable research labs in this addition**, not placeholders for unspecified future implementation. Neither includes a live event-contract order sender.

Prediction-market signals join the existing Qlib/LightGBM/NeuralForecast programme and parent news services. Do not add a second feature store, calibrator, portfolio controller, model registry, account book or broker authority. Native VAN implementations remain the integration default; descriptive source findings do not qualify a provider or copied dependency.

### 22.2 Hosted deployment and no-procurement development policy

VAN's intended runtime is the Netcup/Oracle topology, not the owner's mobile phone. The adapter profile records the actual host and region when observed, without substituting a cloud brand for an instance location. The owner has explicitly excluded obtaining a new licence now. **No procurement, subscription, commercial licence application, funded account or paid service is a dependency for finalizing this design or developing its software.** [S26]

Keep four distinct records: compute placement; operator/account eligibility; data-use scope; and model/strategy live authority. Public API reachability is a technical property. It does not itself establish unrestricted storage, training or redistribution rights, and a server address does not establish operator eligibility. The official developer and member agreements are reference inputs to the source profile, not a procurement instruction. This pack does not grant or assert either permission. [S39–S40]

Use the following stage-correct progression:

| Work mode | Work that proceeds now in the implementation plan | Meaning of completion |
|---|---|---|
| Synthetic fixture replay | Implement full adapters against fixtures, semantic transforms, model-provider tests, valuation, queue/cash simulation, labs and owner API contracts | Actual software behavior on synthetic data; no provider connectivity or economic claim |
| Already-permitted historical import | Admit existing data with its actual provenance, permitted use and availability limitations; run reproducible historical studies | Evidence scoped to that dataset and its limitations; not a new licence purchase |
| Existing-access read-only capture | Exercise actual provider reads/streams only for a documented applicable use, with existing credentials where needed | Real source-specific integration evidence; no trading or model promotion authority |
| Consequential use of external-asset evidence | Apply an independently qualified signal through VAN's existing policies and owner mandates | Separate economic, data and financial authority requirements satisfied for the named use |
| Live event-contract execution | Not included in this addition; needs its own explicit scope, eligibility and existing-authority integration | Cannot be inferred from any preceding research, cloud placement or code test |

The default supplied profile is `FIXTURE_REPLAY`, with a zero new-purchase budget and live order submission disabled. It is not an instruction to stop building. If a source is unavailable for the proposed use, record `UNAVAILABLE` or `USE_SCOPE_UNCONFIRMED`, finish the source-independent code and continue other authorized packets. Do not relabel fixture success as real-source qualification, silently waive a parent mandatory external test or mark the whole backend complete while its admitted genuine integration duties are outstanding. Scope changes require a visible parent amendment, not an invented pass.

No region spoofing, proxy rotation to defeat a restriction, borrowed account, credential fabrication, automatic terms acceptance or hidden export of owner research is part of the implementation. Source metadata review is bounded to the operations being attempted; it is not a repeated general licence-review programme.

### 22.3 Logical producers and consumers

Extend `NewsIngress`, `CalendarRecorder` and the event registry, as specified by the parent. A `PredictionMarketAdapter` acquires structured records; a `ContractMapper` binds each proposition to the canonical event and settlement rules; an `EventProbabilityBuilder` derives quality-labelled expectations; a calibration producer supplies separately evaluated probability mappings; the existing research service produces conditional asset forecasts. [S42]

The resulting evidence has explicit consumers: the news-history profile, candidate-ranking/risk-suppression paths, event-driven strategy research, existing forecast serving, scenario replay, research comparison and owner projections. An ingestion adapter with no reachable consumer is incomplete. A consumer with no real source/fixture producer or durable outcome is likewise incomplete.

Training workers receive no broker credentials. The read-only adapter receives only credentials needed for its source read/stream, never an order-signing privilege where the provider allows that separation. Where credential privileges cannot be technically separated, keep them in an isolated gateway, deny order routes and qualify the exact outbound allowlist. Do not expose unrestricted provider calls through the research API.

### 22.4 Source adapter and acquisition contract

Implement provider-specific discovery, market metadata, rule/version retrieval, order-book snapshots, historical observations and permitted stream capture. Include paging, bounded retry/backoff, schema-version checks, response byte limits, request budgets and durable checkpoints. Capture raw source identity and exact received/available times before normalization.

Kalshi documents unauthenticated public REST market-data access and separate authenticated streaming. The current documentation describes `orderbook_fp` with YES/NO bid ladders using decimal-string prices and quantities. Treat these as versioned contracts rather than permanently hardcoded expectations about integers, whole cents or whole contracts. [S27–S28, S31]

For normalized binary books:

```text
best_yes_bid = highest valid YES bid
best_no_bid  = highest valid NO bid
best_yes_ask = payout_per_contract - best_no_bid
best_no_ask  = payout_per_contract - best_yes_bid
```

The $1 complementary-price identity applies to the normalized $1 binary contract. Other payout units require the corresponding scale. Preserve the quantity attached to the opposite bid. An empty opposite side means no observed executable ask; it must not become zero, one, midpoint or last price. Validate all prices and quantities using exact decimal arithmetic, instrument precision and payout bounds. Crossed or internally inconsistent observations are flagged, not exploited as guaranteed profit before validating synchronization and fillability.

The book starts from a complete snapshot. Apply only updates consistent with the channel's sequence protocol and current market identity; deduplicate, detect gaps and invalidate the book until a permitted resnapshot repairs it. Do not keep advertising an old synthetic best price while a sequence is broken. Received-time order, provider sequence and economic event time are recorded separately. A reconnect after downtime must reconcile whether historical catch-up is possible rather than interpolate unobserved depth.

Kalshi's current history interfaces partition live and historical data using documented cutoffs. Discover and persist the relevant cutoff for each data type, page both sides where required, merge by stable identity and reject contradictory duplicates. The dataset manifest must state whether it contains candles, trades, snapshots or an ordered depth stream. A candles-only archive cannot claim historical queue evidence. [S29]

Polymarket implements the same normalized read contract through its own separately verified provider API; its identifiers, complementary outcome mappings, clocks and settlement rules are not assumed identical to Kalshi. Re-read the exact current API schema when implementing packet038. This revision establishes the required behavior and interfaces, not an assertion that every Polymarket endpoint was newly audited here.

### 22.5 Canonical proposition, settlement and event identity

Each `PredictionMarketContract` records provider/market ID, underlying event ID/family, proposition, units, comparator or disjoint range, observation interval, timezone, official reference source, release vintage, rounding, payout currency and amount, close rule, resolution policy, void/refund policy, dispute policy and exact rules digest. A provider change creates a new version with lineage.

Distinguish an economic event from the contracts referring to it. Multiple CPI thresholds, category bins, venues and intraday quotes can all share one underlying event. That event identity is the grouping key for dependence-aware validation and portfolio concentration, not the number of tickers.

A model may propose a contract match, but reviewed semantics and deterministic checks establish the admitted relation. “A cut at the December meeting” and “a cut by year-end” are not identical. Nor are first-published and revised economic releases, inclusive and exclusive thresholds, local-midnight and UTC cutoffs, or last-price and average-price resolutions.

The relation state is `EXACT`, `COMPLEMENT`, `RELATED_NOT_EQUIVALENT`, `AMBIGUOUS` or `INCOMPATIBLE`, with reviewed evidence and a version. An arbitrage lab may use only the required reviewed relation and its enumerated settlement assumptions. Related contracts can be informative explanatory features without forming a guaranteed hedge. Both providers' actual resolution rules remain authoritative for their contracts. [S32]

Record separately: scheduled announcement time; actual first usable official publication; information becoming known; trading close; outcome determination; dispute finality; settlement; and cash becoming reusable. A final known outcome before administrative close must not be counted as an early forecast. A resolved contract may still tie up cash.

### 22.6 Coherent probability distributions and liquidity quality

Preserve at least three interpretations: raw market observation, derived market-implied estimate, and independently calibrated real-world probability. Bid/ask bounds, midpoint and last trade are not interchangeable estimators. The estimator policy is versioned and records quote age, spread, depth, last-trade age, relevant turnover horizon and source concentration. A price is evidence about an event, not a certified probability by definition.

For mutually exclusive exhaustive outcomes, require nonnegative probabilities summing to one within a declared tolerance. Do not normalize unrelated or incomplete markets merely to make a neat chart. A constrained adjustment can be a research policy only if it preserves raw values, discloses missing mass and assumptions, and is evaluated for downstream usefulness.

Threshold contracts form a survival function. For compatible thresholds `a < b`:

```text
S(a) = probability(X >= a)
probability(a <= X < b) = S(a) - S(b)
```

Check threshold order, monotonic survival probabilities and exact boundary/rounding semantics. Do not sum overlapping threshold prices. Do not create a negative interval mass by ignoring asynchronous quotes. When measurements conflict, report a coherence failure or a versioned constrained projection; retain the raw book evidence and adjustment amount.

Open-ended bins do not supply their own finite representative values. Quantiles, bounded event probabilities and interval masses can remain usable without a mean. A mean/variance estimate involving open tails must cite an admitted tail model and sensitivity analysis. Shannon entropy is a useful research feature only for comparable event definitions/binning; a different number of bins can change entropy without any change in economic uncertainty.

The liquidity floor should be tied to the actual information/execution use, source freshness and relevant depth, with exact thresholds decided from a frozen profile. There is no invented universal dollar floor in this pack. Total lifetime volume is not proof of a current tight book. A low-liquidity observation can remain visible as labelled context while being excluded from consequential forecasts.

### 22.7 Frozen expectations, surprise and contract rolls

Before each release, seal the expectation snapshot used by an armed plan or research observation. Bind its underlying event, source versions, rule digest, quote cutoffs, estimator/calibrator versions and exact maximum input availability. After the official release, compute surprise against this frozen snapshot—not a refreshed probability that already incorporated the result.

A continuous standardized surprise needs a supported mean, scale and outcome measurement. With only categorical probabilities, use a declared categorical surprise or probability-of-realized-bin score, not a fabricated continuous z-score. The scoring rule, handling of zero probabilities and clipping/smoothing belong to the preregistered study. A surprising macro result need not imply a specific directional asset response.

Do not splice “next meeting” contracts across events and describe the resulting jump as changing belief. An event-specific change requires the same underlying event/rules and an admitted horizon comparison. A maturity-normalized research series must preserve the mapping to actual events and a roll flag. Missing prior snapshots produce `CHANGE_UNAVAILABLE`, not zero.

For armed expectations, preserve the parent's two-source rule and exact tolerance, liquidity and freshness checks. If the two providers do not offer an equivalent proposition, the rule is not satisfied by two vaguely related markets. In ordinary research, a one-source observation can still be studied with its quality state; it cannot quietly unlock an armed consumer that requires two. Agreement is not independence: common news and shared price discovery remain one potential information channel, and duplicate derived signals must not multiply conviction. [S42]

### 22.8 Category- and horizon-specific calibration

Fit probability calibration separately from price estimation and asset-response modeling. Compare raw probabilities with simple parametric and monotone alternatives using earlier data only. Calibrator identity binds event category, horizon, liquidity cohort, estimator policy, target settlement/vintage and training/calibration cutoff.

Evaluate Brier score, log loss with a documented probability-bound policy, reliability and resolution/discrimination. Report calibration uncertainty, binning choices, source coverage, abstentions, event counts and effective sample assumptions. Include a prevalence/base-rate baseline and the raw market-implied estimate. Recalibration that worsens proper scores or downstream utility is rejected; recalibration does not create new information automatically.

Split by underlying event and time. All quotes, thresholds and venue copies of a held-out event remain together. For ongoing multi-event/global models, exclude labels whose resolution or actual availability occurs after the training cutoff. Report different decision horizons separately; do not pool minutes-before-announcement predictions with weeks-ahead predictions and present the combined score as early tradable accuracy.

Calibration evidence reported by the exchange and independent research provides motivation, not a default certificate. Inspect near-resolution observations for already-known outcomes, category imbalance, participant concentration and favourite–longshot effects in VAN's intended use population. Refit, estimator changes and material rule changes invalidate incompatible calibration bindings. [S37–S38]

### 22.9 Event probability to conditional asset response

A 70% probability of a policy decision is **not** a 70% probability that an FX, gold or crypto trade wins. The response layer estimates a different object: instrument return, volatility, adverse excursion or a precisely defined trade event, under its own horizon and execution policy.

For a reviewed exhaustive event partition, a candidate conditional model may use:

```text
expected_asset_return(t,h)
    = sum over event outcomes j:
        calibrated_event_probability(j | information_at_t)
        * expected_asset_return(t,h | outcome_j, information_at_t)
```

This is a law-of-total-expectation decomposition, not proof of causal identification or model accuracy. A mixture distribution similarly requires valid conditional distributions and compatible event weights. Evaluate the event probabilities and conditional response model separately and together. Do not substitute “rate cuts imply currency weakness” for an estimated response; positioning, prior expectations and broader conditions are part of the model's information set.

Initial research consumers should include pre-event adverse-risk filtering, multi-horizon volatility, frozen-surprise interpretation after official publication, and ranking among already eligible opportunities. Retain the no-prediction-market baseline, calendar-only baseline and strongest existing market-data features. Control for the possibility that event prices merely echo asset moves already captured elsewhere.

Qlib receives the same canonical point-in-time features and FoldPlan as the other models. LightGBM is the first tabular challenger. N-HiTS and N-BEATSx can investigate temporal/volatility responses; DeepAR or other admitted models may provide domain-valid conditional distributions. All model adapters remain those specified in §§8–10. Event-derived features are not a separate training/serving definition catalogue.

Future probability trajectories, later liquidity, realized policy outcomes and revised consensus are not future-known covariates. Only genuinely known event-calendar vintages may enter a future-exogenous channel. Stacking or blending uses out-of-fold component predictions; a model and an analyst explanation using the same market probabilities do not constitute independent confirmations.

### 22.10 Integration with news policy and VAN trading modes

Keep the existing D1–D7 responsibilities. D1 can reduce a new trade's risk multiplier within its existing floor/exception rules; D2 can defer entries and extend but not shorten the calendar blackout; D3 can select admitted execution templates or no-execution; D4/D5 can propose permitted preservation for VAN-managed positions; D6 can reduce ranking/eligibility. D7 remains the only route for a validated news/event strategy to create or enlarge a trade. Each path requires its existing shadow, evidence and owner-live admission. [S42]

Prediction-market information alone cannot widen a stop, manage an owner-controlled position without handover, clear a halt, enlarge a mandate or replace official-release verification. Uncorroborated observations retain the parent's limited influence. An expired probability snapshot invalidates dependent new-entry evidence but does not disable existing protective controls.

Normal, Risky and Aggressive consume the same fact-bound evidence at their admitted use scopes. More aggressive opportunity selection is not permission to increase an unverified probability or count repeated signals twice. Required independent edge evidence must be genuinely produced and bound, including positive sandbox tests. Raw market price cannot satisfy that evidence requirement by itself.

### 22.11 Binary-contract valuation and constrained position proposals

The research lab distinguishes hold-to-resolution valuation from early-exit strategies. For a purchased $1 YES contract bundle held to settlement:

```text
expected_net_value
    = contract_count * independently_estimated_success_probability
      - executable_entry_cost_total - fees_total - other_costs_total
```

Use the quantity-weighted executable ask through available depth, not midpoint or a conveniently selected last trade. NO uses the matching complementary probability and its own obtainable price. Probability calibration uncertainty, settlement ambiguity and capital lock-up remain explicit. Expected net value is not a realized receipt.

For early exits, model executable exit price, exit fees, unfilled/partial exit states and elapsed capital use. Do not use final payout EV to qualify a strategy whose rule is to sell after a price move. Cost denominators and spread already embedded in fills must match the existing accounting rules.

A synthetic fixture illustrates the arithmetic: 100 contracts at an aggregate entry cost of $60, a synthetic fee of $1.68 and a hypothetical independently estimated success probability of 65% produce $65 expected payout and $3.32 expected net value. Maximum paid-outlay loss in that particular no-extra-liability fixture is $61.68. **These are synthetic parameters, not a current fee quotation, forecast or trading recommendation.** Real series fees and settlement rules are separately versioned.

For an isolated binary wager with known `p`, a constant all-in unit cost `c < 1`, and a $1 success payout, the theoretical log-growth allocation of capital committed is `(p-c)/(1-c)` when positive. This formula assumes the specified distribution, isolated position and fixed costs; it is only a research comparator. Fees depending on size, uncertain probabilities, correlated outcomes and nonlinear payoffs require the proper optimization problem. Risk-constrained growth research is relevant, but its assumptions are not automatic market facts. [S36]

The lab must produce robust sensitivity analyses, fractional/constrained alternatives, full-outlay/settlement loss bounds, event-family concentration and cash-reservation proposals. It cannot send an order or compute an authoritative size. All external-asset proposals follow the existing loss model; binary-contract analysis must never pretend a narrow technical stop guarantees a small loss during a discontinuous event. The current pack introduces no naked short or leveraged event-contract authority.

### 22.12 Execution-realistic book, queue, fees and settlement replay

Use two evaluation modes. **External-information mode** replays the actual destination FX/CFD/other instrument's broker, spread, delay and risk semantics. **Event-contract research mode** models its own depth, contract settlement and cash ledger. Their P&L and evidence cannot be mixed.

External-information mode uses the first instant the data was available to VAN, then acquisition/feature/model/decision/submission delay and the next feasible execution event. A historical provider timestamp is not proof VAN could trade then. Preserve post-release acquisition lag and verify that apparent performance survives plausible additional delays.

Event mode handles partial fills, resting queue uncertainty, cancel/replace races, self-trade prevention where applicable, tick/quantity minimums, stale books, trading pauses, fee tiers and effective dates. A price touch is not a guaranteed fill. A cancellation request does not release risk or cash until confirmed or reconciled. Outstanding orders remain potential exposure during a gap or disconnect.

Use versioned exact-money fee accounting, including the applicable rounding/accumulator and balance precision. A generic percentage applied to each aggregate trade is insufficient where the venue's per-fill rules differ. Separate debited fees from any rebate or incentive; do not assume special maker benefits. If precise queue position is unobservable, report conservative fill scenarios and sensitivity rather than a single fictitiously exact maker backtest. [S30]

Settlement replay includes ordinary win/loss, cancellation/void/refund where allowed, delayed resolution, dispute outcomes and cash release. It also tests exhausted per-venue capital, conversion costs, currency/depeg stress for unlike collateral and stranded hedges. Use realized cash and marks consistently: a known winner is not immediately available cash unless the venue confirms it.

The implementation must reconcile cash plus positions and reservations across every event; show initial capital, debits, fees, payouts and final cash. Candles/trades-only data are insufficient to qualify historical queue priority. Such data can support restricted valuation research while book-based claims remain unsupported. [S28–S31]

### 22.13 Cross-venue arbitrage and payoff-consistency laboratory

Implement a reviewed contract-relation graph and payoff-state enumerator. The lab checks within-event coherence and cross-venue exact/complement relationships without assuming that related headlines settle together. Research on Polymarket demonstrates that such inconsistencies are a genuine study area, but does not prove a current accessible opportunity for VAN. [S35]

For two exactly complementary $1 contracts, the illustrative combined payoff is $1 and the conditional net margin is `1 - YES_ask_A - NO_ask_B - all_costs`. The real test is the minimum portfolio payoff over **all admitted relevant resolution states**, after executable acquisition costs and charges. Include voids, disputes, timing differences and currency/collateral effects where the actual rules allow them.

If a state exists with unhedged loss, classify the opportunity as a risky relative-value candidate rather than riskless arbitrage. If rules or outcomes are unenumerated, return `UNRESOLVED_PAYOFF_SCOPE`. A positive theoretical minimum under assumed completed fills is still not a guarantee of execution, solvency or timely cash release.

Model non-atomic legs: the first order fills, the second reprices/rejects/partially fills, cancellation races, emergency hedge unavailable and separate venue cash exhausted. Report worst legging loss, executable capacity, maximum reserved cash and time to redeploy. Same underlying event exposure must be consolidated at the portfolio level even when held at different venues.

Output is an immutable `ArbitrageCandidate`, with exact relation/rules, acquisition assumptions, payoff states, depth/cost evidence and hedge-failure scenarios. No lab endpoint submits a leg or treats a positive spread as owner authority.

### 22.14 Inventory-aware market-making laboratory

Implement an event-appropriate quote-policy plugin, not a direct transfer of stock-market continuous-price assumptions. A binary contract has bounded payouts and can jump abruptly when information arrives. Quote proposals should depend on conditional event value, existing inventory, pending orders, time to release/resolution, book quality and a measured fill-arrival/adverse-selection model.

The relevant expected value of a bid is `E[payout | this bid fills, available information] - bid - fees`, not only unconditional expected payout minus bid. Test whether fills concentrate after new information has made a resting quote unattractive. This is a predictive/execution question; a tight spread alone is not an edge.

Mandatory behavior includes inventory-skew proposals, both-side consistency, gross-outlay and event-family limits, bounded quote counts, pause/withdrawal around admitted high-impact events, stale-book withdrawal and explicit cancel-pending exposure. A later quote does not erase an earlier possibly filled order. Queue/fill assumptions and source limitations remain visible in every report.

Evaluate cash- and inventory-adjusted net P&L, adverse-selection markouts, fill probability, inventory age, worst settlement state, stress losses and quote/cancel latency. Separate spread capture from inventory bets and any rebate/incentive. Do not assume designated market-maker privileges, preferential queue placement, faster throughput or fee subsidies. [S40]

The lab must have negative tests for crossed quotes, unlimited replenishment, book gaps, duplicate order identities and cancellation storms. It must not propose spoofing, wash trading or misleading orders. This implementation is a research simulator and quote-proposal generator; live order submission remains absent.

### 22.15 Four registered studies and meaningful incremental value

Deliver the four named studies in `research/PREDICTION_MARKET_STUDIES.json`. Each is a real callable experiment pipeline with independently frozen configuration; its final thresholds and instrument cohort are selected before holdout access, not invented by this specification.

| Study | Hypothesis and output | Mandatory comparators |
|---|---|---|
| PM-STUDY-01 — Pre-event risk filter | Event uncertainty helps identify adverse trading conditions for otherwise eligible setups | VAN incumbent, calendar-only blackout and uniformly reduced/exposure-matched policies |
| PM-STUDY-02 — Surprise interpretation | Frozen market distributions improve interpretation after the official result is available | Conventional consensus alone, existing event-history features, and consensus plus prediction distributions |
| PM-STUDY-03 — Volatility | Probability changes/distribution width add forecast information at actual holding horizons | Historical volatility, HAR/GARCH where appropriate, existing tabular/temporal model, with/without event features |
| PM-STUDY-04 — Opportunity ranking | Event information improves selection among eligible candidates | Same timestamp/universe, capital and mandate, incumbent ranking and strongest existing model without the source |

Record all attempted features, event categories, horizons, calibrators and models. Compare at common information cutoffs and opportunity streams. Smaller drawdown caused solely by less exposure is not proof of more intelligent selection; include exposure-matched policies and show opportunity costs of skipped winners.

Replay the full account, including simultaneous opportunities, reserved risk and cash. Skipping one opportunity can allow another; isolated “losses avoided” must not be added into an impossible portfolio. Utility includes risk, turnover, slippage, operating costs and any actually incurred data costs. Zero procurement in this phase does not authorize inventing a negative or free future operating cost in a commercialization claim.

Use event-cluster or justified time-block confidence intervals, power/sample adequacy and dependence-aware statistics. Predefine economically material improvement and risk noninferiority; preserve the parent DSR/PBO requirements where applicable rather than applying them nonsensically to every probability-score dataset. A calibrated source can still fail net economic admission.

### 22.16 Prospective evidence and nonvacuous qualification

Seal forecasts and candidate decisions before outcomes are available. Retain a control policy and record real receipt times, source state, proposed decisions and actual later outcomes. Prospective shadow fills remain simulated and cannot be reported as broker executions. Approved source use, actual source integration, scientific value and live authority are independently recorded.

The protocol includes shuffled event assignments, extra information lags, wrong-event mapping, future-vintage poisoning, contract-roll artefacts, duplicated sources, thin-liquidity exclusions and outages. A test that detects an obvious negative shift but misses a future-revised release does not qualify point-in-time behavior. Reject p-value selection across many studies without the trial census.

Count independent events or justified blocks, not thousands of correlated quotes on one announcement. No fixed short observation period guarantees sufficient evidence. Report `INCONCLUSIVE` when power or coverage is inadequate, retain the complete software and avoid forced promotion. Prospective rejection is a valuable outcome when it prevents unsupported live influence.

Both positive and failure paths must work: genuine adapter readback where available and permitted; synthetic malformed feeds; complete model round trips; retained probability provenance; actual scoped gateway consumers; sandbox promotion/refusal/revocation; and recovery. The model worker cannot issue its own independent evidence certificate. A fixture reference with a valid hash remains a fixture.

### 22.17 Owner operations, runtime isolation and recovery

The owner-facing backend must support source health/scope inspection, contract-resolution explanation, probability-history read, event snapshot freeze/readback, bounded study request/cancel/status, model/ablation comparison, lab scenario selection, outcome inspection and export of entitled evidence. Reuse existing jobs, capability catalogue and durable receipt lookup rather than adding opaque notebook-only functionality.

Backend projections distinguish market-implied probability, calibrated event probability, conditional asset forecast, quote availability, fixture/historical/live-read evidence and consequential use status. They show source disagreement, stale snapshots, unavailable mappings, rejected features and blocked integrations. A missing source never appears as 50% probability or “no risk.”

After renewed global BG-001, integrate these fields/actions into News/Events, Research/Analyst, Replay/Chart, Strategies/Modes, Portfolio/Risk, Work/Evidence and Settings. Home keeps its existing information budget. Show detailed rule/settlement evidence through contextual navigation. There is no new event-contract “buy” button or ungoverned market-making switch in this addition.

Read-only source workers and heavy studies run on qualified Netcup/Oracle placements through Global DIAL's existing boundaries. Keep source credential access, retained books, training files and output quotas isolated from financial authority. Measure actual headroom, acquisition delay, sequence resync, source time skew and stale-consumer behavior. Do not change VPN or network routing as part of this blueprint task.

On data outage, dependent new-entry evidence abstains or follows its separately admitted fallback. Existing risk reduction, broker reconciliation and owner visibility continue. On restart, replay source checkpoint and sequence state, revalidate exact contract rules and model/calibration bindings, and do not release pending quote/settlement cash without confirmation. Erasure or source-scope revocation traces through derived datasets/models/caches under the existing retention contract.

### 22.18 Concrete delivery, contracts and gate mapping

New backend packets037–048 are integrated into the same child graph and contribute to parent BE-008, BE-013 through017, BE-019, BE-021/022 and the existing operations/projection/verification duties. Packet032 explicitly depends on every new backend packet; packet033 proposes the complete amended parent BG bundle. No later frontend packet can bypass that chain. Parent scope is preserved in `plan/PARENT_INTEGRATION_DELTA.json` and the original byte-identical pack in `lineage/`.

| Contract | Producer → consumer | Required semantic check beyond schema |
|---|---|---|
| PredictionMarketSourceProfile | Source configuration → adapter/job admission | Hosting never proves eligibility; no procurement; actual use scope distinct from fixture support |
| PredictionMarketContract | Rules mapper → event/distribution/payoff services | Exact boundaries, vintage, exceptional resolution and reviewed equivalence |
| PredictionMarketObservation | Source adapter → coherent book/feature builder | Clocks, sequence continuity, decimal domains and complementary executable sides |
| EventProbabilitySnapshot | Probability builder/calibration → news/model consumers | Probability meaning, coherent bins/thresholds, frozen event, source dependence and arming constraints |
| EventAssetResponse | Qlib/NF response provider → existing forecast/evidence adapter | Actual instrument/target/horizon identity, point-in-time inputs and no copied event-win probability |
| EventPositionProposal | Value lab/response consumer → research and existing risk review | Correct EV/cost/full-loss interpretation, D1–D7 scope and no direct order authority |
| PredictionMarketStudySpec | Study controller → workers/independent evaluator | Event-grouped chronology, matched controls, full account, frozen holdout and retained trials |
| EventExecutionScenario | Replay lab → economic report | Book granularity, uncertain fills, fee/cash arithmetic and settlement availability |
| ArbitrageCandidate | Payoff lab → research review | Full relation/state assumptions, worst net payoff, non-atomic legs and venue cash |
| MarketMakingPolicy | Quote lab → replay/research | Conditional-on-fill valuation, pending exposure, inventory limits and no special privileges |

The ten added JSON fixtures are **synthetic document-contract examples**. Their hashes/references do not establish real data, real calibration, semantic review or market execution. The bundled local checker exercises selected shapes, arithmetic and counterexamples only. Production implementations must bind real typed records to trusted source/authority stores and run all 180 application acceptance contracts at their proper stages.

**Revision completion truth:** the integrated specification, child schedule, requirements, test contracts, source references and interchange schemas are delivered. No licence was obtained, no trading account opened, no provider collection job started, no model fitted, no event order sent, no host deployment changed and no parent independent gate issued by making this revision. The software scope is complete and explicit; engineering and economic execution remain the next programme stages, not facts claimed by this document.

## References

Source IDs `[S01]` through `[S42]` resolve in `references/SOURCE_REGISTER.md` and its JSON companion. Primary documentation establishes upstream capabilities, not VAN performance. VAN source observations establish inspected behavior and intended boundaries, not deployed qualification. Parent Library materials establish the programme contract, not a completed implementation.
