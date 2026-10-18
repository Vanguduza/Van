# VAN / VATI — Consolidated Recommendations and Identified Improvements

## Forecasting, strategy research, execution, adaptive feedback and qualification

**Document ID:** `VAN-VATI-CHAT-CONSOLIDATION-20261018`  
**Revision:** 1.0  
**Compiled:** 18 October 2026  
**Prepared for:** Tapiwa Kevin Guduza  
**Project:** VAN / VAN Adaptive Trading Intelligence (VATI)  
**Repository:** `Vanguduza/Van`  
**Document status:** `CONVERSATION_CONSOLIDATION / NOT_AN_IMPLEMENTATION_RECEIPT / NOT_A_NEW_EXECUTABLE_PLAN`

> **Consolidated direction:** Preserve VATI as one trading system. Complete its evidence-qualified forecasting and research capabilities; correct its simulator and execution accounting; add a durable, governed order-execution lifecycle; and close the feedback-to-decision connections so measured outcomes can improve subsequent strategy selection and execution. Keep financial authority deterministic and separate from models, research and subjective judgments.

This document compiles the recommendations, source findings, corrections and outstanding improvements discussed throughout this chat. It is not a fresh repository audit, market study, code change or deployment. Prior source observations remain tied to their original dates, commits and scope. Proposed improvements are not represented as completed features.

The compilation covers Kronos and the ForgeMesh guide; Qlib and LightGBM; Freqtrade/FreqAI; NeuralForecast and other challengers; Kalshi/Polymarket intelligence; the high-value crypto research additions; comparisons with profitable systematic systems and autonomous bots; the proposed **VATI Symbiotic Execution Fabric**; adaptive feedback; Jev; and the corrections to the unified backend-first programme.

It does **not** replace the detailed machine-readable requirements, acceptance contracts, source-preservation records or independently admitted authority selector of the unified programme. Later execution and feedback recommendations still require explicit reconciliation into that programme. Their presence here does not mean a parent plan has already been amended.

### How to interpret statements in this document

| Label | Meaning |
|---|---|
| **Prior source finding** | Behavior or limitation identified in repository reads already recorded in this chat; not reverified during compilation. |
| **Prior focused reproduction** | A narrowly scoped VM test reported earlier, with its source identity; not a full-suite or live-broker result. |
| **Specified in delivered candidate** | Included in an existing blueprint/plan candidate; not evidence the application functionality is implemented. |
| **Follow-up recommendation** | Proposed later in this chat; must be reconciled with existing owners and admitted contracts before implementation. |
| **Research challenger** | A capability worth evaluating; economic influence remains conditional on evidence. |
| **Not established** | The available chat/source evidence does not establish the asserted integration, deployment, latency, profitability or permission. |

**Citation convention:** `[D1]`–`[D7]` identify source documents in Appendix C. `[CHAT-01]`–`[CHAT-09]` identify the relevant discussion segments in Appendix B. `[CODE-xx]` identifies an immutable repository reference previously inspected in this chat, listed in Appendix D. External reference links in Appendix E are carried forward research pointers, not newly visited sources. Reported financial results are not used as proof of VAN profitability.

## Contents

- [01. Executive decisions and highest-value priorities](#section-01)
- [02. Source lineage, preservation and corrections already agreed](#section-02)
- [03. Unified ownership and integration architecture](#section-03)
- [04. Repository findings, useful existing work and unresolved gaps](#section-04)
- [05. Point-in-time data, feature and target engineering](#section-05)
- [06. Qlib and LightGBM adoption](#section-06)
- [07. Freqtrade and FreqAI capabilities to adopt](#section-07)
- [08. NeuralForecast adoption](#section-08)
- [09. Kronos, Chronos and the ForgeMesh field guide](#section-09)
- [10. Calibration, model fusion and forecast serving](#section-10)
- [11. Kalshi / Polymarket probability intelligence and event research](#section-11)
- [12. Read-only crypto discovery, chain security and temporal wallet intelligence](#section-12)
- [13. Lessons from profitable systems and popular autonomous bots](#section-13)
- [14. VATI Symbiotic Execution Fabric](#section-14)
- [15. Execution economics, transaction-cost analysis and simulator repairs](#section-15)
- [16. Adaptive feedback: existing behavior and the missing positive-improvement loop](#section-16)
- [17. Jev: useful integration, latency limits and quality qualification](#section-17)
- [18. Trading temperaments, strategy lifecycle and owner authority](#section-18)
- [19. Scientific evaluation, profitability evidence and experiment design](#section-19)
- [20. Consolidated acceptance and fault-injection obligations](#section-20)
- [21. Runtime placement, budgets, observability and recovery](#section-21)
- [22. Owner-facing controls and truthful presentation](#section-22)
- [23. Integration order and coding-agent handoff](#section-23)
- [24. Outstanding decisions and explicit non-claims](#section-24)
- [Appendix A. Coverage map: where every discussion workstream is retained](#appendix-a)
- [Appendix B. Conversation provenance](#appendix-b)
- [Appendix C. Document sources and preserved identities](#appendix-c)
- [Appendix D. Immutable code references from prior inspection](#appendix-d)
- [Appendix E. External research and donor pointers carried forward](#appendix-e)
- [Appendix F. Final integration checklist](#appendix-f)

---

<a id="section-01"></a>
## 01. Executive decisions and highest-value priorities

### 01.1 Retain one coherent system

Do not install several autonomous trading engines and allow them to compete over the same accounts. Qlib, NeuralForecast, FreqAI-inspired lifecycle components, Jev, execution algorithms and specialized research laboratories must integrate through VATI's existing boundaries.

The agreed separation is:

**Models and strategies propose → the opportunity allocator ranks → the account coordinator manages account-wide competition and reservations → RiskAuthority authorizes risk and size → ExecutionRouter controls broker submission → confirmed execution evidence drives reconciliation and learning.**

The exact ordering of reservations and authorization must follow the admitted transactional account contract; a scoring component must not invent a separate capital ledger. The essential invariant is that no independent model, agent, executor or interface can create additional financial authority. [D1 §§3,13; D2 §30.3]

### 01.2 Highest-value implementation priorities

| Priority | Consolidated improvement | Why it matters |
|---|---|---|
| P0 | Preserve and reconcile existing branch implementations | Avoid replacing functioning Jev, evidence, mode, account and execution work with duplicates or older versions. |
| P0 | Correct simulated fills, costs, timing and portfolio accounting | Forecasting and strategy evidence cannot be trusted when economic measurement is wrong. |
| P0 | Complete durable order state, unknown-outcome handling, protection confirmation and cancellation reconciliation | A submission or close request is not proof of a fill or flat position. |
| P0 | Connect actual execution outcomes to the existing execution-policy evidence collector | The reviewed code selected policies but did not establish the production feedback path that teaches the selector. |
| P1 | Complete Qlib/LightGBM and the required NeuralForecast integrations | Provide reproducible, task-specific forecasting and challenger evaluation. |
| P1 | Complete model, calibration, study, serving and outcome lifecycle | Installed libraries are insufficient without real producers, consumers, recovery and measured use. |
| P1 | Add governed parent/child execution and portfolio-target reconciliation | Work an approved objective over time without exceeding its financial envelope. |
| P1 | Close the positive-improvement loop | Research and qualify better alternatives, rather than only reduce or suspend existing strategies. |
| P1 | Deliver the already specified prediction-market and read-only crypto research scope | Add context, exitability and defensive evidence without creating another trading desk. |
| P2 | Evaluate Jev as asynchronous diagnostic and research assistance | Test useful interpretation, latency and incremental value; do not assume fast judgments equal better trades. |
| P2 | Reproduce transparent systematic strategy families and specialized execution ideas | Use inspectable methods and appropriate baselines rather than unverifiable retail-bot claims. |

The priorities organize this compilation. They do not supersede prerequisite edges in the canonical development graph or waive any mandatory model/provider implementation. [D1 §§18–21; D2 §30.14; CHAT-06–09]

### 01.3 The most important correction to earlier optimistic descriptions

VATI already has meaningful **defensive adaptation** and rule-based position management. It is not yet established as a fully self-optimizing production system.

The key unresolved connection identified in the final adaptivity review is:

```text
Actual order/fill/non-fill outcomes
    → context- and execution-template-specific evidence
    → persistent execution-quality estimates
    → selection among qualified templates on later trades
```

The reviewed implementation has components on both sides of that connection, but no verified end-to-end production update path was established. Improving the broker-liquidity multiplier is useful; it is not the same as learning which order-working policy is better. [CHAT-09; CODE-05–08]

### 01.4 What success means

The result should be a complete, usable, reproducible and recoverable capability that can honestly determine whether an improvement adds value. A correct system may reject a model or strategy, abstain from a trade, or return `INCONCLUSIVE` when evidence is insufficient.

A favourable backtest, a vendor's profitability claim, a document-checker pass, or a model's confidence must never become a substitute for independent economic and operational qualification. [D1 §§1.3,15,19–21]

---

<a id="section-02"></a>
## 02. Source lineage, preservation and corrections already agreed

### 02.1 Relevant document progression

| Document / discussion stage | Contribution | Treatment in this compilation |
|---|---|---|
| Forecast Adoption Rev1.0 | Qlib, LightGBM, FreqAI-inspired operations and NeuralForecast | Retained through the expanded forecasting specification. |
| Forecast Adoption Rev1.1 | Prediction-market probabilities, asset response and event research laboratories | Preserve the full 90-requirement forecasting scope, not only one probability feed. |
| High-Value Trading Adoptions Rev1.0 | Executable economics, complete cohorts, chain safety, wallet history and typed judgments | Retain as historical input; apply the explicit corrections from the comparative review. |
| Comparative review of all advertised branches | Source ownership, duplicate-service risks, grade conflicts, simulator reproductions | Preserve dated findings and exact evidence scope. |
| High-Value companion Rev1.1 / Unified Rev1.12 | Corrected integrated domain scope and backend-first dependencies | Specification integration, not application completion. |
| Unified Rev1.13 | Subsequent consolidation candidate referenced in the chat; retrieved for lineage confirmation | Its opening scope/status is confirmed from the Library; this compilation does not re-audit its full product specification. |
| Later execution, feedback and adaptivity discussion | Symbiotic execution, missing policy-evidence updates, synchronous cognition risk and positive-improvement lifecycle | Follow-up recommendations to map explicitly into the existing programme. |

The retrieved Rev1.13 opening records **131 packets, 267 active requirements, 82 backend units, 12 backend-verification units, 234 context obligations and 1,377 planned application acceptance contracts**. Its delivery state says those application contracts remain `NOT_RUN`; it identifies BG-001 as packet 098 and the first native UX packet as 099. These are **that candidate's recorded scope and delivery status**, not newly verified implementation totals. No additional packet or requirement total is invented here. [D4 opening]

### 02.2 Preserve the distinction between three kinds of completion

**Engineering completion:** real libraries, services, data contracts, producers, consumers, positive paths, failures, recovery, artifact handling and sandbox admission actually work.

**Economic qualification:** an exact model/strategy/policy adds sufficiently robust value for a defined instrument cohort, horizon, cost model and intended use. A result may be qualified, rejected or inconclusive.

**Financial authority:** the existing owner, strategy, account and risk-governance path authorizes the exact consequential use. Model publication, a research result, a software release or a backend gate does not grant it. [D1 §§1.3,15.3,19]

### 02.3 Do not shrink the agreed engineering scope

Earlier answers described NeuralForecast, prediction-market additions and some model challengers as optional later experiments. The subsequent integrated specifications clarified the intended meaning:

- Their **already specified software integrations** remain mandatory.
- Their **economic influence** remains conditional on evaluation.
- A working implementation that reports no qualified model is valid.
- A permanently empty producer, refusal-only stub or unimplemented adapter is not complete.

Preserve N-HiTS, N-BEATSx, DeepAR, the declared TFT/PatchTST/iTransformer research plugins, calibration, raw scenario handling, lifecycle operations, and the event valuation/arbitrage/market-making research laboratories. Do not reinterpret an earlier smaller starting point as the final scope. Kronos, Chronos and other additional candidates are not silently elevated into mandatory parent requirements by this compilation. [D1 §§1.2,18.2; D2 §§15,30.1]

### 02.4 Preserve one plan and the whole-backend gate

M0–M9, G0–G6, prior child packet suffixes and historical DU references remain traceability aliases, not competing schedules. An old packet number must be interpreted with its plan revision, scope digest and stable unit ID.

New native UI remains downstream of **the single global BG-001**, not merely after an evaluation harness and one healthy feed. Backend API/read-model contracts may be built before that gate; frontend implementation may not use them as a shortcut around incomplete backend obligations. [D2 §§12,30.13–16; D4 opening]

### 02.5 Keep research-source grades separate from implementation grades

The original High-Value document used E1–E5 for publication/source quality, while the parent used E0–E6 for implementation and acceptance evidence. The review identified a dangerous collision: vendor capability and unverified creator claims could be mistaken for software tests or device certification.

Use distinct fields and namespaces:

| Dimension | Examples | Cannot establish |
|---|---|---|
| `research_source_class` | RS1 primary/transactional; RS2 published/reproducible; RS3 vendor capability; RS4 self-reported; RS5 unverified creator | Working VAN code, deployment or permission. |
| `implementation_evidence_level` | Parent E0 owner reference through E6 owner visually accepted; `SPEC_ONLY` where applicable | Trading edge merely because implementation works. |
| `source_integration_state` | Fixture, permitted historical import, actual provider read, unavailable/unconfirmed | Live participation or financial authority. |
| `economic_use_state` | Qualified, rejected, inconclusive, not evaluated | Account or risk permission. |
| `financial_authority_state` | Existing verified strategy/account/mandate status | Universal model validity outside the approved scope. |

Hashes establish identity and integrity, not truth or independent review. A signature must come from the correct existing authority; the model or worker cannot create its own approval. [D2 §30.4]

---

<a id="section-03"></a>
## 03. Unified ownership and integration architecture

### 03.1 Intended end-to-end flow

```text
Broker / market / official news / permitted external-source observations
    + prediction-market records
    + read-only chain and wallet observations
                         |
                         v
Existing identity, event, provenance and point-in-time data owners
                         |
                         v
One feature catalogue + explicit target catalogue + immutable datasets
                         |
             +-----------+------------+
             |                        |
             v                        v
     Qlib / LightGBM          NeuralForecast providers
     and tabular challengers  and admitted temporal challengers
             +-----------+------------+
                         |
                         v
Shared studies, calibration, immutable artifacts and qualified bindings
                         |
                         v
Prepared forecast / context / judgment snapshots with exact scope and TTL
                         |
                         v
Existing strategy capsules and opportunity selection
                         |
                         v
Account-wide target/exposure coordination + existing RiskAuthority
                         |
                         v
Approved execution objective and bounded execution plan
                         |
                         v
Governed parent/child order lifecycle through existing ExecutionRouter
                         |
                         v
Venue updates → confirmed fills/positions/cash → protection/reconciliation
                         |
             +-----------+------------+
             |                        |
             v                        v
 Local deterministic feedback   Asynchronous diagnostics/research
 within existing permissions    including optional qualified Jev assistance
             |                        |
             v                        v
 Later eligible decisions       Challenger evaluation and separate admission
```

This diagram describes proposed functional relationships. It does not assert that all connections currently operate or that each box needs its own process. [D1 §3; D2 §30.3; CHAT-06–09]

### 03.2 Canonical owners

| Mechanism | Owner / integration boundary | Must not become |
|---|---|---|
| Raw data, timestamps, contract identity and source state | Existing market-data, calendar, event and acquisition services | A model-owned source of financial truth. |
| Feature and target definitions | Existing feature registry and research target specifications | Separate incompatible definitions in Qlib, NeuralForecast and serving. |
| Training / experimentation | Shared Qlib and NeuralForecast research adapters, Optuna and durable jobs | A second execution engine or an unbounded notebook-only workflow. |
| Artifact tracking | MLflow and content-addressed artifacts | Authority to promote a model through a mutable alias. |
| Calibration | Existing conformal/validation ownership, extended by target type | A duplicate risk governor or generic confidence score. |
| Opportunity ranking | Existing arbiter and versioned allocator | Position sizing or independent account reservations. |
| Account coordination | Existing coordinator and transactional store | Separate per-bot cash books that ignore each other. |
| Risk sizing and ceilings | Existing RiskAuthority | A responsibility of Jev, an LLM, a neural network or a TWAP worker. |
| Broker commands | Existing ExecutionRouter and admitted adapters | Competing live senders from donor projects. |
| Order working | Proposed bounded lifecycle/executors below existing authority | Self-authorized replacement orders or additional exposure. |
| Judgment | Shared `dial-jev` through existing VAN clients | A second Jev server, ledger, credential plane or trading desk. |
| Financial evidence and feedback | Existing ledger, TCA, lifecycle and trusted evidence resolver | Research prose relabelled as observed execution. |
| Owner experience | Existing gateway and post-BG native contexts | A parallel dashboard with weaker financial controls. |

### 03.3 Determinism does not prohibit adaptation

The desired deterministic property is:

> Given the same admitted policy versions, recorded evidence, account state and ordered external events, VATI reproduces the same decisions and state transitions.

A policy can select different actions when the recorded circumstances change. That is adaptation under a deterministic rule, not a contradiction.

Keep four separate reproducibility claims: exact replay of recorded decisions; fixed-environment inference repeatability; declared cross-device numerical tolerance; and statistical reproducibility of stochastic retraining. Do not promise byte-identical neural training everywhere. External broker fills are not deterministic; the response to their recorded outcomes must be reproducible. [D1 §§9.3,13; D2 §30.12; CHAT-06]

---

<a id="section-04"></a>
## 04. Repository findings, useful existing work and unresolved gaps

### 04.1 Dated source baseline

The repeated source inspections in this chat referenced:

| Source | Identity recorded in the chat | Relevant scope |
|---|---|---|
| Merged main | `8eb1889822fc8a83f219977c15340172e16acd91` | Baseline trading, learning, account and research source. |
| PR #101 / Opus working branch | `a39f241b0135cf92cc5a6b9a28af226aa294603d` | Execution, incremental-ledger and recoverable-lockout corrections; mixed with a design pack; unmerged when inspected. |
| PR93/canon family | `dfc1557ab99ad8d41cf84714e1bb671e89b045e6` | Shared Jev consumers, typed learning evidence, cognitive/mode contributions. |
| PR #92 | `923ecf9bbb81a2b3b485a3730071279851596b06` | Signed opportunity temperaments; draft/unmerged when inspected. |
| PR #77 | `c091d22ce21728de33b5c8318385a147809dc207` | Cognitive-fabric producer/consumer work. |

The all-branch review reported **66 advertised heads at 63 distinct commits and 4,634 union paths**. The first supported-content scan reported 3,680 UTF-8 blobs; the later Rev1.13 review recorded 4,942 under its own broader bounded scan. These are separate scan scopes, not cumulative code-certification totals. Neither proves every line was semantically reviewed, every integration was deployed, or untracked services were absent. [D3 §§1–2; D4 opening]

### 04.2 Existing capabilities to preserve

The chat's source inspections identified real implementations of strategy capsules, RiskAuthority, the execution router, account coordination and leases, route/quantity/stop validation, protective actions, reconciliation, TCA, strategy/broker health, learning-state replay, rule-based meta-labeling, position-lifecycle logic, research workflows, drift analysis, exit research, and cognitive shadow attribution.

On unmerged branches, preserve the Jev gateway/advisor/owner controls, typed ledger-evidence resolution, cognition integrations and signed temperament work. The account service and coordinator had multiple materially distinct versions; choose compatible functions by contract and evidence, not by commit count. [D2 §30.2; D3 §2; CHAT-08–09]

### 04.3 Consolidated gap and correction register

The identifiers below are **editorial compilation IDs**, not new canonical VAN requirements. All statuses refer to the prior evidence, not a new audit.

| ID | Finding / limitation | Required improvement | Evidence state |
|---|---|---|---|
| GAP-01 | `main` does not contain all useful branch work. | Reconcile relevant branch functions, callers, state migrations and tests without blanket merges. | Prior all-branch review. |
| GAP-02 | PR101 combines trading fixes and a design pack. | Preserve intended code corrections without accidentally accepting unrelated unsigned design scope. | Prior PR/source inspection. |
| GAP-03 | Named forecast libraries were declarations/plans, not demonstrated production integrations in the scanned source. | Build real train/export/load/serve/evaluate consumers; do not count package names as completion. | Dated bounded search; external/untracked implementations not ruled out. |
| GAP-04 | `AllocatorV1` already exists and still excludes uncalibrated confidence. | Introduce a reviewed model-informed input/policy version at the same owner; do not treat V1 as a calibrated upgrade automatically. | Prior source finding. |
| GAP-05 | Fixed open→low→high→close backtest path can favour short targets in ambiguous candles. | Use actual finer observations or common feasible scenario paths and explicit ambiguity. | Prior source finding, retained corrective scope. |
| GAP-06 | Paper realized P&L does not show explicit commission/financing debits in the inspected formula. | Charge actual required costs in cash accounting; avoid double-counting embedded spread. | Prior source finding. |
| GAP-07 | Final equity-curve point precedes terminal liquidation. | Record final liquidation and charges before final-equity reporting. | Prior source finding. |
| GAP-08 | Closed-trade statistics do not establish full mark-to-market account drawdown. | Record event-level equity, floating exposure, reservations and cash movements. | Prior evaluation finding. |
| GAP-09 | Single-instrument backtesting does not establish account-coordinator parity. | Replay shared capital, margin, correlated exposure, pending orders and competing opportunities. | Prior source finding. |
| GAP-10 | Immediate buy/sell limit prices can be violated by the PR101 paper fill path. | Enforce side-correct price limits in immediate and resting fills. | Prior focused reproduction. |
| GAP-11 | Missing explicit stop-entry expiry falls back to 24 hours rather than the discussed four-hour policy. | Propagate and persist the actual approved expiry through policy, command, adapter and recovery. | Direct adapter observation; full propagation still needs its own test. |
| GAP-12 | Pending and immediate entries do not yet have fully established unified lifecycle/protection handling. | Apply consistent protection, receipt, cancellation and terminal-state rules to both paths. | Existing corrective obligations. |
| GAP-13 | Multi-slice planning exists but the router refuses more than one slice. | Add an explicitly governed parent/child protocol, not a bypass or one-shot substitution. | Prior source finding. |
| GAP-14 | Common `VenueAdapter` lacks a complete generalized pending-order query/cancel/replace contract. | Add capability-negotiated order management without pretending every venue supports it. | Prior interface review. |
| GAP-15 | A protective-stop failure triggers a close request, but the inspected message says flattened without proving the close succeeded. | Preserve unresolved exposure until confirmed/reconciled flatness; keep protective recovery active. | Prior source finding; targeted failure reproduction still required. |
| GAP-16 | Partial-fill status support is not a complete persistent fill lifecycle. | Deduplicate fill events, track cumulative versus remaining quantities, fees and residual exposure. | Prior execution comparison. |
| GAP-17 | Live order paths pass an empty `LiquidityView()`. | Provide actual qualified depth/liquidity where available; retain honest unknown fallback otherwise. | Prior source finding. |
| GAP-18 | `ExecutionPolicyEngine.select()` is called, but a production `observe()` feedback path was not found in inspected callers. | Join outcomes to execution buckets/templates and persist/replay the statistics used for subsequent selections. | Prior call-site search and source review; not an absolute all-alias absence proof. |
| GAP-19 | Execution-policy evidence is stored in an in-memory map in the inspected implementation. | Establish durable observation and reconstruction semantics before calling it adaptive production learning. | Prior source finding; persistence elsewhere was not established. |
| GAP-20 | Broker-cost feedback mainly reduces opportunity eligibility. | Add qualified execution-method learning rather than describing a liquidity penalty as optimized order working. | Prior feedback review. |
| GAP-21 | Strategy candidate generation exists, but production automatic callers were not established for the reviewed helper. | Connect diagnosis, candidate creation, evaluation and the existing promotion route as a real workflow. | Prior source/search finding. |
| GAP-22 | Exit/drift research is reachable through the research CLI but not established as autonomous live policy replacement. | Add durable triggers, inputs, outcomes and reviewed activation of validated alternatives. | Prior source finding. |
| GAP-23 | Cognition is shadow-only/default-unconfigured in the reviewed account setup. | Expose actual configuration and results; do not claim a working external model when none is configured. | Prior source finding. |
| GAP-24 | `_risk()` calls `cognition.wake()` synchronously after making the risk decision but before returning it. | Move nonessential cognitive/research work off the trade/protection critical path. | Prior source finding; production delay not measured. |
| GAP-25 | Jev gateway attention/critic/browser integration is not a complete VATI trade-feedback consumer. | Reuse the shared service and add explicitly evaluated trading-domain question/result joins. | Prior branch review. |
| GAP-26 | No qualifying Jev feedback-latency or net-trading improvement was demonstrated. | Benchmark event-to-consumer latency, diagnostic correctness, cost and paired policy outcomes. | Not established. |
| GAP-27 | Existing shadow-R comparison is size-only on the same trade. | Add matched-opportunity, changed-path and whole-account policy replay; retain the original limited attribution view. | Prior source finding. |
| GAP-28 | Faster or stricter reactions are not necessarily more profitable. | Compare exposure-matched controls, skipped winners, false vetoes and full net utility. | Agreed evaluation requirement. |
| GAP-29 | Earlier “no edge” wording exceeded what the reported experiments establish. | Record insufficient promotion evidence under that experimental setup, pending evaluator qualification; do not pronounce a strategy universally unprofitable. | Explicit clarification in the unified candidate. |
| GAP-30 | Blueprint completion was repeatedly confused with source or runtime completion. | Keep specification, component, integration, economic and live-authority states separate. | Repeated review correction. |

### 04.4 Preserve already developed corrections, then test their limits

PR101's reported improvements included incremental rather than full-ledger-per-decision verification, price-fraction slippage handling, stop quantization that does not widen the approved distance, propagation of strategy entry types, resting paper orders and recoverable loss/drawdown lockouts.

The conversation did **not** conclude that those changes closed every execution issue. Preserve them and add the missing adversarial and end-to-end tests. The initial stop-entry support also remained unsupported on some real adapters; a paper implementation does not qualify a broker stop order. [CHAT-05–06; D4 opening]

### 04.5 Previously reproduced numerical counterexamples

| Synthetic VM probe at PR101 source | Reported observation | Scope limitation |
|---|---|---|
| Buy limit 1.10000 | Filled at 1.10007 | Paper-adapter behavior, not a claim about a real broker. |
| Sell limit 1.10000 | Filled at 1.09993 | Same limitation. |
| Distant limit | Accepted and retained as pending | Positive control proves resting support exists. |
| Resting stop without explicit expiry | 86,400,000 ms default | Does not independently test every policy-to-router path. |

No such tests were rerun while producing this compilation. [D3 §2.5; D4 opening]

---

<a id="section-05"></a>
## 05. Point-in-time data, feature and target engineering

### 05.1 One historical information contract

Every observation should identify instrument, venue/contract, source, event time, provider publication time where available, VAN receipt/availability time, ingestion time, quality and revision. Preserve the actual market-calendar and timezone versions.

A backtest decision may consume only information available to VAN at that historical decision cutoff. A training row additionally requires its target outcome and actual label availability to precede the permitted fit boundary. Uncertain reconstructed availability must be labelled, not guessed into a clean history. [D1 §5]

### 05.2 Preserve economic identities

Do not pool instruments merely because their tickers look similar. Spot, CFDs, exchange futures, illiquid equities, event contracts and Deriv nonlinear/full-stake products need their own price, payoff, calendar, cost and quantity conventions.

Keep raw executable prices separate from adjusted equity features. Retain listings, delistings, corporate actions, contract rolls, migrations, halts and unavailable intervals in the point-in-time universe. Today's surviving assets cannot silently define yesterday's opportunities. [D1 §§5.2–5.3]

### 05.3 Features have one definition owner

Use the existing feature registry for formulas, versions, lookbacks, missingness, source dependencies and allowed cohorts. Qlib handlers, NeuralForecast datasets and serving must consume the same definitions; Feast supports retrieval/materialization rather than becoming an independent policy owner.

Fit scalers, imputers, categorical vocabularies, PCA, feature selectors and novelty detectors on the relevant training fold only. Preserve row IDs through filtering. Higher-timeframe inputs must come from completed, available candles. Missing data must distinguish market closure, no trading, provider failure and genuine zero observations. [D1 §§5.3–5.4]

### 05.4 Keep targets mathematically distinct

| Target | Meaning that must be recorded | Must not be relabelled as |
|---|---|---|
| Future return | Instrument, sign, arithmetic/log convention, start/end references, gross/net basis and horizon | Probability the trade wins. |
| Setup-event probability | A defined entry/exit/timeout/stop/target outcome for a defined population | Generic confidence. |
| Opportunity rank | Order among comparable eligible candidates at the same cutoff | Calibrated probability. |
| Terminal return quantile | Conditional scalar-outcome quantile at one horizon | Stop-touch or maximum adverse-excursion probability. |
| Realized volatility | Sampling definition, nonnegative domain, aggregation and transform | Directional return or raw Student-t outcome without a valid transform. |
| Execution cost/fill probability | Side, quantity, venue, template, horizon, selection and censoring assumptions | Observed fill on a trade that never executed. |
| Event probability | Exact proposition, outcome vintage and resolution rules | Asset-return or trade-win probability. |
| Temporal scenario | Individual trajectory, horizon ordering and sampling/dependence model | A marginal band or average path. |

Quantiles of cumulative returns cannot be obtained by casually summing one-step quantiles. Exponentiating a predicted log-domain mean does not automatically recover the original-domain arithmetic mean. These distinctions belong in the target/artifact contract, not just explanatory text. [D1 §5.5]

### 05.5 Complete cohorts and permissioned data

Retain accepted, rejected, expired, cancelled, unfilled, unknown and delisted opportunities. An unexecuted order has no actual slippage observation; paper and hypothetical outcomes remain separate evidence classes.

Consented owner-manual trading can feed a distinct research cohort without transferring private behavior into shared models by default. Revocation or source correction must trace through snapshots, features, models, calibration and caches while preserving audit history according to its retention policy. [D1 §§5.6,14,16]


---

<a id="section-06"></a>
## 06. Qlib and LightGBM adoption

### 06.1 Qlib: research framework, not a replacement trader

Implement VAN-specific immutable-data loaders, fold-scoped handlers/processors, research tasks, prediction exports and evaluation hooks. Preserve canonical datetime/instrument identity and all feature/target/fold hashes through Qlib's data representations.

Use the selected shared MLflow tracking backend. One study should retain one coherent experiment identity across Qlib, native LightGBM and NeuralForecast providers. Log logical job and attempt identities separately, and preserve failed or interrupted attempts.

Do not import Qlib's executor, default regional calendar, price-limit conventions, account sizing or portfolio rules into VATI. A familiar Alpha158 benchmark may be studied; it is not automatically the right feature set for FX, gold, Deriv or ZSE. [D1 §8]

### 06.2 Objective compatibility must be implemented explicitly

The earlier upstream source inspection found that the stock Qlib `LGBModel` wrapper accepted `mse` and `binary` and expected a single label column. Therefore the recommendation was not to pass arbitrary objectives through that wrapper and claim quantile/ranking support.

Provide an explicit VAN LightGBM adapter. Delegate compatible tasks to the locked wrapper where useful; implement native LightGBM Dataset/objective/export routes for grouped ranking, quantiles and versioned multi-horizon bundles. Preserve Qlib task/recorder integration without forking the trading engine. Revalidate compatibility against the version actually adopted. [D1 §§8.3–8.4]

### 06.3 Required LightGBM task families

| Task | Required implementation | Important qualification |
|---|---|---|
| Return / net-edge regression | Explicit target and complete execution-cost convention | Compare against zero-return, linear and incumbent baselines. |
| Setup-event classification | Precisely defined profitable-outcome or barrier event | Separate raw probabilities from held-out calibrated probabilities. |
| Downside/upside quantiles | Separate configured alpha levels or a validated bundle | Check crossing, units and horizon; do not turn terminal quantiles into barrier odds. |
| Grouped opportunity ranking | Same-cutoff/cohort query groups and correct relevance encoding | Respect objective label requirements; compare with simply ranking regression forecasts. |
| Execution-quality forecasting | Cost, fill or adverse-risk target for an exact venue/template/size bucket | Account for censoring and the absence of real fills on rejected opportunities. |

Class weighting or imbalance corrections can change probability interpretation. Calibrate on the intended deployment population, not a convenience sample of completed winners. Local feature contributions and importance are diagnostic, not identified causal explanations. [D1 §9]

### 06.4 Reproducible training and safe serving

Start with bounded CPU studies, fixed seeds, explicit row/feature order, thread limits and a tested environment. The earlier reference profile included LightGBM's CPU deterministic setting with one chosen histogram mode; those are engineering choices to verify, not an optimal trading configuration.

Export native Booster artifacts with objective, target transform, feature order/types, vocabulary, fit cutoff and selected iteration. Reload and compare against golden snapshots. Reject incompatible or nonfinite inputs/outputs. Do not deserialize arbitrary Qlib or Python model objects from an untrusted URI in the live path.

Begin with full rolling retraining. Warm-start/incremental variants are separate research candidates; continually appending trees is not automatically a sound response to market drift. Training completion publishes a candidate, not a live binding. [D1 §§9.3–9.4,11.2]

### 06.5 Baselines and challengers

Retain XGBoost, linear/logistic models, persistence/zero-return, incumbent strategy, no-trade where appropriate, simple ranking and HAR/GARCH-style volatility baselines. DoubleEnsemble was suggested as a research challenger in the chat; it is not a proven profit engine or an automatic substitute for the declared baseline suite.

Chronos/Chronos-2 and Kronos remain additional candidates where they supply incremental information. Their names do not extend live authority or remove the required Qlib/LightGBM implementation. [CHAT-02; D1 §1.2]

---

<a id="section-07"></a>
## 07. Freqtrade and FreqAI capabilities to adopt

### 07.1 Adopt behavior, not a second account controller

The chat's audit concluded that Freqtrade should not replace VATI. Its most useful additions are operational patterns for research, forecasting and orders. They must be implemented through existing VAN owners rather than launching another live Freqtrade bot against the same accounts. [CHAT-03; D1 §11]

| Donor capability | Required VAN treatment |
|---|---|
| Separate training and inference | Heavy isolated research workers; preloaded bounded forecast serving. |
| Adaptive retraining | Scheduled and drift-triggered candidate jobs with concurrency, budgets, cancellation and provenance. |
| Model freshness and expiry | Expire exact model/calibration/use bindings; do not extend validity because retraining is late. |
| Prediction persistence/cache | Key by material inputs, model, target, features, transforms, scope and admission epoch. |
| Feature expansion | Versioned lags, higher/lower horizons and peer features fitted/validated within chronology. |
| DI-style novelty, optional PCA/SVM/DBSCAN | Separate domain novelty from feed integrity and calibration; preserve tails and rejected observations. |
| Lookahead analysis | Prefix-causality comparisons on identical decision cutoffs with deliberate future-data poison cases. |
| Recursive-indicator analysis | Warmup-history stability tests with justified per-indicator tolerances. |
| Hyperparameter optimization | Shared Optuna controller; preserve all trials and avoid duplicate search budgets. |
| Cooldown, loss-streak and low-profit protections | Extend existing entry-suppression/risk policy with exact scope and durable state. |
| Dry-run and operational diagnostics | Distinguish real observations, paper fills, shadow results and actual broker outcomes. |
| Order timeout/exit discipline | Integrate into VATI's durable order lifecycle and protection owner. |

### 07.2 Bias diagnostics that must become usable tools

A deliberate `peek` switch that changes a backtest is a useful negative control, but not a complete causal data-access audit.

Implement both prefix-only versus full-frame comparisons and history-length/warmup comparisons. Poison cases from the discussion include negative shifts, centered rolling windows, whole-dataset normalization, future revisions, incomplete higher-timeframe candles, misaligned peer clocks, post-outcome duration, survivor-only universes and cache keys that accidentally admit future labels.

The diagnostic should identify the offending feature or decision path, not merely report that two total returns differ. Passing a clean fixture without detecting the deliberate poison is insufficient. [D1 §§6.1–6.3]

### 07.3 Adaptive model jobs

The delivered forecast candidate specifies:

```text
REQUESTED → VALIDATED → QUEUED → RUNNING → EXPORTING → EVALUATING
          → CANDIDATE_READY

or FAILED / CANCELLED / INSUFFICIENT_DATA / OUTCOME_UNKNOWN
```

Bind dataset/target/model environment, resource allocation, worker lease, attempt and output publication. Coalesce obsolete retraining requests with explicit supersession. Reconcile uncertain publication before retrying. Maintain a previous qualified artifact only while its own scope and expiry remain valid. [D1 §11.2]

### 07.4 Protections and market scope

Loss-streak and cooldown observations must count completed trade/family outcomes, not individual partial-fill messages. Scope suppression by account, environment, strategy, instrument and direction as admitted. Restore it on restart and preserve stricter owner/risk blocks.

The PR101 recoverable-lockout work already exists on a branch and must be reconciled, not rebuilt independently. A protection can suppress new or expanded exposure without blocking mandatory risk reduction.

CCXT-style crypto connectivity or an isolated Freqtrade comparator may be useful for a separately justified crypto study. It is not a universal FX/Deriv/ZSE execution oracle and does not authorize a new venue. [D1 §§7.4,11.4; CHAT-03,05]

---

<a id="section-08"></a>
## 08. NeuralForecast adoption

### 08.1 Role inside VATI

NeuralForecast complements the tabular baseline by supplying temporal, contextual, multi-horizon and probabilistic models. It must share VAN's dataset, target, study, artifact, calibration and serving contracts rather than create a separate model registry or research authority. [D1 §10]

| Model / capability | Role recommended in the chat | Scope treatment |
|---|---|---|
| N-HiTS | Multi-horizon returns and realized-volatility challenger | Mandatory declared integration; economic admission remains empirical. |
| N-BEATSx | Contextual forecasting and supported trend/seasonality/exogenous decomposition | Mandatory integration with actual capability checks. |
| DeepAR | Distributional return/valid transformed-target forecasting and retained temporal scenarios | Mandatory integration and raw-path adapter. |
| TFT | Context-rich, multi-horizon challenger | Usable research plugin, not automatic live preference. |
| PatchTST | Temporal sequence representation challenger | Usable research plugin under its actual supported-input matrix. |
| iTransformer | Aligned multivariate research where appropriate | Usable research plugin; no assumption of universal covariate support. |
| Point, quantile and distributional losses | Match optimization and output to the defined target | Mandatory interface and domain tests. |
| Native cross-validation | Implementation aid for rolling prediction/refit studies | Subordinate to VAN's chronology, purging, labels and final holdout. |
| Auto-model/Optuna mechanisms | Bounded neural search | Share the existing study controller; no second optimization plane. |
| Safe artifacts | Verified local safetensors/JSON path on the adopted supported version | No unrestricted legacy pickle loading in serving. |

Earlier comments that “start with three models” meant the first scientific comparison, not permission to leave the declared challenger plugins unbuilt. Conversely, the chat did not authorize integrating every model in the upstream catalogue. [D1 §§1.2,10,18.2]

### 08.2 Covariates and model-specific capability

Map canonical data to `unique_id`, `ds`, `y` and explicit historical, future-known and static covariates. Historical covariates must be available by the origin. Future-known covariates may contain the calendar vintage known then, but not future returns, volumes, news sentiment, actual releases or later market probabilities.

Inspect and test each model's capability flags on the pinned version. A shared constructor argument does not prove a model actually uses that input type. Static information that changes over time needs vintages or segmentation.

Use decomposition or feature-importance displays only where supported by the fitted configuration. They describe model behavior, not proof that a news event caused a market move. [D1 §§10.1,10.3,10.5]

### 08.3 Uncertainty and trajectories

Keep point forecasts, marginal quantiles, distribution parameters and temporal sample paths separate. Retain actual individual paths before aggregation, with sample count, RNG scheme, artifact identity, units and horizon order.

Autoregressive paths can carry within-series dependence; independent asset paths are not automatically a joint portfolio distribution. A global model trained on many assets does not necessarily produce jointly sampled market scenarios. Separate dependence and joint-risk qualification is required where portfolio scenarios are used.

A Student-t loss is a candidate for appropriate return targets, not a blanket choice for nonnegative volatility. Robust losses may be evaluated, but deleting genuine extreme observations to improve fit is not acceptable. [D1 §§5.5,10.4–10.7]

### 08.4 Evaluation focus

The earlier financial research discussion suggested realized volatility, event-conditioned risk and multi-horizon behavior as promising first uses. Those suggestions remain research hypotheses for VAN's instruments, not inherited performance guarantees.

Compare against strong HAR/GARCH/historical-volatility and tabular baselines at the actual holding horizons. Report proper distribution/quantile scores and their limitations alongside decision-level net utility. A statistically better but expensive or frequently unavailable model can fail practical admission. [CHAT-04; D1 §§15.1–15.2]

---

<a id="section-09"></a>
## 09. Kronos, Chronos and the ForgeMesh field guide

### 09.1 Preserve the actual recommendation about Kronos

The chat treated Kronos as a **research challenger and scenario/representation candidate**, not a demonstrated autonomous profitable trader.

The prior architecture review described a two-stage design: normalized OHLCVA candlesticks are encoded by a Transformer autoencoder and binary spherical quantization; a causal Transformer predicts coarse and fine market tokens; decoded sampled tokens produce future observations. The discussed small/base tokenizer split used coarse/fine subtokens. These are carried-forward descriptions, not a newly inspected version claim. [CHAT-01]

The operational implications identified were more important than the promotional benchmark headline:

- Verify tokenizer/checkpoint compatibility and exact source/weight hashes.
- Use only historical-window normalization and properly aligned market timestamps.
- Retain individual samples; the inspected convenience predictor averaged multi-sample paths.
- Test OHLC consistency, nonnegative activity fields, clipping, extreme outcomes and compounding forecast error.
- Do not equate plausible-looking candles, RankIC improvement or token loss with profitable execution.
- Preserve unresolved checkpoint-provenance questions as unresolved, not proof of contamination or a clean bill of health.
- Test zero-shot and any fine-tuned candidate independently; lower token-prediction loss may fail to improve economic targets.

### 09.2 Preferred research uses and initial comparisons

Investigate cross-sectional opportunity ranking, supplementary setup information, market-state representation and scenario/stress generation. Volatility ranking is a hypothesis to compare against simple historical models, not a validated default.

The prior recommendation was to start with a small model and compare mini/base on identical data and costs rather than assume bigger is better. The paper-style 90-day lookback and 10-day ranking example was a reproduction candidate, not an optimized VAN parameter set.

A Kronos-derived feature must add information beyond existing VAN signals and survive chronological, cost-adjusted, forward comparison. Keep historical crisis replay and conventional stress tests; synthetic scenarios supplement them, not replace them. [CHAT-01]

### 09.3 Chronos / Chronos-2

The earlier discussion identified Chronos as another pretrained time-series challenger. It was not promoted over LightGBM, NeuralForecast or the existing strategy baseline. Compare its output semantics, context/covariates, artifact handling, costs and incremental value through the same provider/evaluation boundary.

This compilation does not authorize a new dependency or assert that a currently available checkpoint has been tested on VAN. [CHAT-02]

### 09.4 ForgeMesh guide

The public field guide was presented as an educational system-building specification and coding-agent kit, not an improved Kronos model or a finished profitable trading application. The discussion identified potentially useful surrounding practices: explained configuration, sanitized/offline tests, hardware planning, paper-trading operations, risk controls and decision audit.

No full purchased kit was established as inspected or adopted in this chat. Do not infer its unseen code, purchase it, import its private licensing terms as permission, or introduce a wallet/order controller merely because the guide mentions broker setup. Reuse only actually available, permitted ideas and retain exact source provenance. The later no-new-procurement direction remains in force for this compilation's scope. [CHAT-01; D1 §§22.2,19.2]

---

<a id="section-10"></a>
## 10. Calibration, model fusion and forecast serving

### 10.1 Extend the existing calibration owner

VATI already has a conformal-risk component in the earlier source observations. Extend that owner rather than installing a second confidence or risk service.

Separate binary event calibration from interval/quantile calibration. Bind model, target, transform, horizon, cohort, estimator and residual window. Refitting or materially changing any component invalidates incompatible calibration even if the model name stays the same.

Measure reliability, Brier/log loss and declared ECE for defined event probabilities; pinball loss, width, coverage and clustered violations for intervals; and appropriate distributional scores for full predictive distributions. Calibration is not itself alpha. Nominal conformal coverage must not be described as an unconditional guarantee for nonstationary, dependent markets. [D1 §12]

### 10.2 Preserve target direction and statistical meaning

A lower expected-return bound and an upper execution-cost bound have different decision meanings. Do not pass both through one lower-bound admission rule without a target-specific adapter.

Keep a market price, a calibrated event probability, an ordinal ranking score, a model's uncertainty, a wallet-attribution confidence and Jev answer quality in different fields. A single undifferentiated “confidence” value hides incompatible meanings and encourages unjustified sizing. [D1 §§5.5,12,14; D2 §30.10]

### 10.3 Fusion must earn complexity

Evaluate each candidate independently before combining models. Use out-of-fold predictions to train a combiner, plus separate calibration and held-out testing. Do not train a stacking model on in-sample component predictions and treat the result as independent evidence.

Compare simple blends and tabular meta-models before elaborate regime switching. Return and volatility forecasts are different quantities, not values to average. Explicitly detect shared inputs and correlated errors so three models using the same signal do not become three independent confirmations.

Every added component needs an ablation result, cost/latency measurement, scope and removal/fallback rule. [D1 §13.2]

### 10.4 Serving and artifact binding

Preload verified local artifacts and prepare bounded forecast snapshots. T0 must not fetch a model registry alias, deserialize weights, train a model or await a remote judge while managing risk/protection.

Bind each decision to one immutable serving epoch containing the model, features, transforms, calibrator and admitted use policy. A mid-cycle update must not mix old and new components. Preserve issued forecasts permanently according to retention policy; do not overwrite them after retraining.

Cache keys must include the material source cutoff/snapshot, target, horizon, model/calibration versions, feature definition, transform, sampling and account/cohort/use scope. Same model name or timestamp alone is insufficient. [D1 §§13.1,14]

### 10.5 Failure states

Represent `DATA_STALE`, `MODEL_EXPIRED`, `CALIBRATION_STALE`, `INSUFFICIENT_CALIBRATION`, `OUT_OF_DOMAIN`, `UNSUPPORTED_COHORT`, `FEATURE_MISMATCH`, `SERVICE_TIMEOUT`, `MODEL_UNAVAILABLE`, `NONFINITE_OUTPUT`, `ARTIFACT_REVOKED` and `EVIDENCE_INSUFFICIENT` explicitly.

A model-dependent entry abstains when required evidence is invalid. An independently qualified model-free strategy may continue only under its admitted fallback. Model unavailability must not disable authorized exits, reconciliation or protective recovery. A failed broker is still an unresolved external state; the model layer cannot claim that it closed a position. [D1 §§12.3,13.4,16.3]

---

<a id="section-11"></a>
## 11. Kalshi / Polymarket probability intelligence and event research

### 11.1 Primary purpose and no-procurement scope

Use prediction-market information first to test whether VAN's existing instrument decisions improve: expectations, uncertainty, changing event risk and surprise interpretation. Do not assume a market price is a ready-made trade signal.

The owner directed that VAN uses the Netcup/Oracle topology and that no new licence is to be obtained in this phase. The integrated blueprint therefore includes no licence procurement, new subscription, paid-feed purchase, account registration, funded event-contract account or live event-contract activation.

Source-independent software, synthetic cases and already-permitted datasets/access can proceed. Record compute placement, operator/account eligibility, source-use scope and financial authority separately. This is the already agreed engineering boundary, not a new legal assessment or instruction to circumvent restrictions. Actual provider proof cannot be replaced by fixture output. [D1 §§22.1–22.2; CHAT-05]

### 11.2 Exact contract semantics

Extend the existing event registry and calendar/news owners with versioned contract mappings. Record proposition, underlying event, units, comparator or range, observation period, timezone, official source, first/revised release convention, rounding, payout, trading close, exceptional/void/refund rules and dispute/finality.

A “cut at a particular meeting” and a “cut by a later deadline” are related, not necessarily equivalent. A model may propose a mapping; reviewed rules and deterministic checks establish the admitted relation.

Keep event occurrence, information availability, trading close, resolution, settlement and reusable cash as different times. Administrative closure is not evidence that an early forecast was useful. [D1 §22.5]

### 11.3 Structured probability information

Build separate fields for raw prices, market-implied estimates, calibrated probabilities, changes, distribution width, tail mass, consensus disagreement, source agreement and quote quality.

For mutually exclusive exhaustive outcomes, nonnegative probabilities should sum to one within an admitted tolerance. Do not normalize an incomplete set of unrelated contracts into a false distribution.

For compatible thresholds:

```text
S(a) = P(X >= a)
P(a <= X < b) = S(a) - S(b), for a < b
```

Check monotonicity, exact boundaries, stale/asynchronous observations and missing bins. Preserve raw data and any constrained adjustment. Open-ended tails require explicit modeling before computing means; missing tail information may still permit some event probabilities or quantiles.

Do not splice successive “next event” contracts into an apparent belief change. Preserve exact event identity and explicit contract-roll markers. [D1 §§22.6–22.7]

### 11.4 Executable order-book observations

The prior research described a normalized complementary binary-book representation. For a $1 payout contract:

```text
YES ask = 1 - best NO bid
NO ask  = 1 - best YES bid
```

Use actual observed depth and the matching opposite-side quantity. An empty book side is missing executable liquidity, not a zero/one price or last-trade substitute. Support the source's actual decimal-price and quantity precision.

Reconstruct books from complete snapshots and sequenced updates, detect gaps/duplicates and resynchronize. Reconcile live/history cutoffs and pagination. Candles and trades do not by themselves establish historical queue priority. Exact upstream endpoints, terms and formats must be pinned at implementation rather than treated as permanently fixed by this chat. [D1 §22.4]

### 11.5 Freeze expectations before the outcome

Seal the exact probability and source snapshot used before an announcement. After the official result arrives, compare it with that frozen expectation, not a refreshed market price that already includes the news.

Calibrate by event family, forecast horizon and relevant liquidity cohort. Keep all quotes/thresholds/venue copies of the same underlying event together in validation. Count independent events or justified blocks, not thousands of correlated quotes.

Two venues reflecting the same news are not independent witnesses. Preserve the parent's required two-source armed-event checks, but do not multiply agreement into exaggerated certainty or claim the rule is met by non-equivalent propositions. [D1 §§22.7–22.8]

### 11.6 Event probability to asset response

A probability of an economic event is not a probability that gold, a currency or a particular strategy trade wins.

The proposed response layer estimates instrument return, volatility, adverse movement or a precise trade event. For an exhaustive compatible event partition, the discussed decomposition is:

```text
Expected asset return = Σ probability(event outcome j | information at t)
                          × expected asset return conditional on outcome j
```

This is a modeling framework, not proof of causal identification. Validate the probability source, conditional response and combined result separately. Qlib/LightGBM provide the first tabular comparison; NeuralForecast can challenge temporal/distributional responses through the same feature and target contracts. Future realized probability trajectories are never known-future inputs. [D1 §22.9]

### 11.7 Preserve the existing news-policy consumers

| Path | Preserved responsibility |
|---|---|
| D1 | Restrict new-trade risk within the existing admitted rules. |
| D2 | Defer entry / extend permitted blackout handling; do not shorten it through the model. |
| D3 | Select an admitted execution template or no execution. |
| D4–D5 | Propose permitted preservation for VAN-managed positions. |
| D6 | Reduce ranking or eligibility. |
| D7 | Separately qualified event-strategy route for creating or enlarging a trade. |

A probability feature does not bypass official-release verification, handover of owner-managed positions, stops, halts, source agreement, mode evidence or the risk mandate. [D1 §22.10]

### 11.8 Binary-contract valuation laboratory

Preserve a complete non-order-sending lab, rather than only a chart or an expected probability:

```text
Hold-to-resolution expected net value
    = quantity × independently estimated success probability × payout
      - executable entry cash - all applicable non-embedded costs
```

Use depth-weighted obtainable prices and actual fee conventions. Early-exit strategies require a model of executable exit prices, costs and fill uncertainty; terminal payout EV is not their return model.

The theoretical isolated binary Kelly expression discussed in the chat, `(p-c)/(1-c)` for the fraction of capital paid into a $1-payout wager, assumes known probability, fixed all-in unit cost and the specified isolated setup. Retain it only as a research comparator. Probability uncertainty, correlated positions, nonlinear costs, settlement delay and capital constraints require the actual optimization problem and existing RiskAuthority. It is not permission for automatic Kelly sizing. [D1 §22.11]

### 11.9 Cross-exchange arbitrage research

Build a contract-relation graph and enumerate payoffs over all relevant admitted settlement states. For completed purchases of exactly complementary $1 contracts, the simple margin is `1 - YES ask A - NO ask B - all costs`.

A proposed hedge must survive differences in rules, exceptional resolution, collateral and cash-release timing. If any relevant state leaves a loss, classify it as risky relative value rather than riskless arbitrage; unresolved rules remain unresolved.

Replay non-atomic legs: first fill, second rejection/reprice/partial fill, failed cancellation, exhausted venue cash and unavailable emergency hedge. Conditional payoff certainty after completed legs does not guarantee execution or counterparty/cash availability. No lab endpoint submits a live leg. [D1 §22.13]

### 11.10 Specialized market-making research

The proposed event-appropriate quote policy uses probability/value, inventory, pending exposure, time to release/resolution, book quality and fill-conditioned adverse selection.

Evaluate:

```text
Expected value of a bid = E[payout | the bid actually fills, available information]
                         - bid price - applicable costs
```

Unconditional fair value can be misleading if informed counterparties fill the quote mainly after news makes it unattractive.

Implement inventory skew, bounded quote counts, stale-book withdrawal, event pauses, cancelled-but-unconfirmed exposure, settlement stress and complete cash/position accounting. Separate spread capture, directional inventory bets and incentives. Do not assume privileged market-maker fees, throughput, queue access or liquidity. No misleading orders, spoofing or wash trading are part of the design. [D1 §22.14]

### 11.11 Required initial study pipelines

| Existing study ID | Hypothesis | Necessary control |
|---|---|---|
| PM-STUDY-01 | Event uncertainty improves pre-event risk filtering. | Existing strategy, calendar-only filter and exposure-matched reduction. |
| PM-STUDY-02 | Frozen distributions improve surprise interpretation after publication. | Conventional consensus and existing event-history features. |
| PM-STUDY-03 | Probability changes/distribution width improve volatility forecasts. | Historical, HAR/GARCH and existing tabular/temporal models. |
| PM-STUDY-04 | Event information improves opportunity ranking. | Same-time eligible universe, capital and risk budget without the source. |

Include delayed-data, shuffled-event, wrong-contract, duplicate-source, contract-roll and future-vintage negative controls. Test full-account economics and false rejection of winners. Event valuation, arbitrage and market-making labs remain mandatory specified software even when their outputs do not qualify economically. [D1 §§22.15–22.18]


---

<a id="section-12"></a>
## 12. Read-only crypto discovery, chain security and temporal wallet intelligence

### 12.1 Scope and ownership

The High-Value review identified chain-aware discovery, sellability, temporal ownership/flow and complete discovery-cohort evaluation as genuinely additive domain capabilities. They should use the shared data, feature, research and evidence infrastructure, not become a meme-token trading desk.

Keep the already specified read-only introduction: no funded wallet, transaction-signing service, new venue authority or independent crypto order sender. Preserve the existing FX, indices, metals, Deriv and ZSE work rather than displacing it with token experiments. [D2 §§30.1–30.3]

### 12.2 Canonical identity and staged screening

Use chain/network-qualified validated token identity; identify pools and routers separately. Tickers and names are display fields. Address normalization must be chain-specific, not a universal lowercase transform. Preserve raw representations, parser versions, migrations and token-to-pool relationships.

Archive discovery before screening, including rejected, expired, migrated, delisted, unreachable and unknown candidates. Retain bounded queues, provider quotas, cursor checkpoints, deduplication and reason-specific negative-result expiry/rechecks.

| Logical stage | Evidence gathered | Required discipline |
|---|---|---|
| D0: identity/discovery | Chain, token, pool, source and first-seen/launch state | Unknown identity remains unresolved. |
| D1: inexpensive numerical screening | Age, liquidity, observed activity and freshness | Do not fabricate ratios for assets younger than the lookback. |
| D2: contract capability | Mint/freeze/upgrade/transfer restrictions and sellability | Fatal restrictions reject; unknown coverage abstains. |
| D3: attribution | Technical pool/vault/burn roles, deployer/holder evidence | Large raw holdings are not automatically insider ownership. |
| D4: temporal flow | Comparable snapshots, transfer/buyer/seller history and liquidity changes | A snapshot alone cannot prove accumulation or holder growth. |
| D5: optional typed context | Supported social/project facts and narrow judgments | Subjective evidence cannot reverse a failed hard check. |
| D6: executable economics | Independent exit-route evidence and qualified value estimates | Eligibility is not authority to trade. |

Exactly one survivor must still receive every remaining gate and a no-trade assessment. Creator example liquidity/holder thresholds must not become VAN defaults without measured false-positive/false-negative evidence. [D2 §§5,30.5]

### 12.3 Chain-specific analyzers

**Solana:** distinguish the admitted SPL Token and Token-2022 behaviors; inspect applicable mint/freeze authority, transfer fees/hooks/delegates and supported extensions; retain slot/finality/parser identity. Unknown extensions or missing state are not benign.

**EVM:** bind chain, contract, proxy and implementation state; inspect applicable admin/upgrade, mint/blacklist, tax/transfer and liquidity-removal controls. A verified proxy shell is not proof that a changed implementation is safe. Unverified source code is uncertainty, not automatic fraud.

Produce factual findings and uncertainty-bearing manipulation features separately. Keep `REJECT`, `INVESTIGATE` and `NO_HARD_BLOCK`; never rename the last state `SAFE_TO_BUY`. [D2 §§6,30.6]

### 12.4 Independent sellability and quantity-aware economics

A buy quote or successful purchase simulation does not prove that selling is allowed or economically viable. Evaluate supported buy and sell routes independently at explicit quantities with chain/router/contract/pool state, caller assumptions, costs and finality.

State-bound simulation success is evidence about that simulation, not a guarantee of a later fill or unchanged taxes/liquidity. A small successful quote cannot be scaled into unlimited free liquidity.

Preserve the three corrected records:

| Record | Contains | Must exclude / clarify |
|---|---|---|
| `ExecutableQuoteFacts` | Observed side, quantity, currency, quoted cash/depth, route/source/state, clocks and embedded-fee conventions | Unobserved future exit proceeds and predicted fill probability. |
| `ExecutionEconomicsForecast` | Predicted costs, exit proceeds, failure/fill outcome with target/model/calibration identity | Claims that modeled quantities are execution facts. |
| `NetEdgeAssessment` | Derived cash-consistent comparison and uncertainty using exact referenced records | Double-counted fees/spread and self-authorized size. |

The discussed economic calculation is expected executable exit proceeds less actual entry cash and non-embedded exit/financing/failure costs. Expected value remains a forecast, not realized P&L. [D2 §§2,30.7]

### 12.5 Temporal wallet evidence and invalidation

Persist anchored holdings, transfers, supply, liquidity and role labels over comparable observation windows. Retain raw concentration plus explained role-adjusted concentration. Common funding is not conclusive common ownership; router hops are not necessarily purchases; airdrops, OTC and internal transfers need negative controls.

Track source/state → facts → features → forecasts → experiments/consumers. Chain reorganizations, corrected observations, changed admin/implementation state and pool migrations invalidate affected descendants before reuse. Revalidation must survive restarts without reactivating stale cached findings. Preserve original issued decisions and add revised analytical versions rather than rewriting history. [D2 §§30.8,30.12]

---

<a id="section-13"></a>
## 13. Lessons from profitable systems and popular autonomous bots

### 13.1 Keep profitability evidence in its proper category

The research distinguished a profitable strategy family, a public implementation and an independently verified live record. A framework does not have an inherent investment return. Aggregate company profits, vault accounting, estimated arbitrage extraction and a trader's screenshot are not interchangeable evidence.

The chat did not establish representative independently audited profitability for default Hummingbot, Freqtrade, pysystemtrade, LEAN, NautilusTrader, 3Commas, Pionex or Cryptohopper configurations. They remain valuable implementation references where their behavior is inspectable. This compilation does not repeat time-sensitive performance figures as current facts. [CHAT-05]

### 13.2 Donor/reference matrix

| System / family | Valuable idea discussed | Appropriate VATI adoption | Limitation to preserve |
|---|---|---|---|
| AQR managed futures | Diversified systematic signals and portfolio risk discipline | Strategy-family reproduction and robust multi-horizon allocation research | Proprietary implementation; fund performance does not prove a specific VAN signal. |
| KMLM / Mount Lucas | Transparent trend methodology, volatility-aware weights, target exposures and rolls | Independent rules-based benchmark | Actual broker order algorithms were not disclosed by the cited methodology. |
| pysystemtrade | Forecast scaling/combination, target positions, instrument→contract→broker order hierarchy, fills/cancel/modify | Account-target coordination and durable order-stack patterns | Public configuration not established as independently audited profitable. |
| Hummingbot V2 | Controllers separated from finite-lifecycle executors; TWAP, grids, DCA, cross-exchange workflows | Bounded execution workers under VATI authority | Platform trading volume is not trader profit; do not import unconstrained grid/DCA risk. |
| QuantConnect LEAN | Risk-adjusted portfolio targets, execution models and independent reproduction | Target-delta execution, spread/volume-aware methods and a validation oracle | A framework or comparator result is not automatically economic truth. |
| NautilusTrader | Event-based order/fill state, unknown outcomes, reconciliation and execution algorithms | Complete the existing selected kernel boundary and recovery mechanics | Do not install it as a competing second order owner. |
| Freqtrade/FreqAI | Operational order discipline and adaptive model lifecycle | Native diagnostics, protection and retraining practices | Default strategies and backtests are not verified live returns. |
| Virtu | Continuous quote/inventory/reprice/cancel/hedge discipline | Adverse-selection, TCA and inventory research | Proprietary algorithms and institutional infrastructure cannot be assumed transferable. |
| Hyperliquid HLP | Inventory from liquidity provision and liquidations, funding and tail risk | Forced-position, illiquidity and concentration stress research | Vault P&L combines activities; privileged/protocol mechanics are not a generic grid bot. |
| CEX–DEX searchers | Executable-spread analysis, capital reservation, atomicity and failed-leg management | Non-atomic multi-leg research and failure models | Estimated extraction is not audited all-in net profit; specialized infrastructure matters. |
| 3Commas | DCA order sequencing and automatic exit management | Study lifecycle/accounting behavior only where compatible | Averaging down can hide increasing exposure and unrealized losses. |
| Pionex | Grid order sequencing and realized-versus-floating P&L separation | Accounting and operational lessons | Positive grid profit may coexist with total portfolio loss. |
| Cryptohopper | Indicator/signal workflows, trailing exits and order timeouts | Bounded order lifetimes and truthful pending-state monitoring | Commercial automation does not establish a profitable default configuration. |

### 13.3 Strategy-family reproduction recommended for VAN

Start with a diversified, volatility-targeted, multi-horizon trend-following reference and add carry only when actual instrument/contract data supports it. Candidate signals discussed include moving-average and breakout families, normalized/capped forecast strength and combined forecasts.

Study risk distribution, correlation/concentration, turnover, financing, contract rolls and trading-cost buffers. Compare portfolio targets with actual holdings and working orders instead of treating every fresh directional signal as another independent entry.

Use pysystemtrade for inspectable mechanics, public KMLM methodology as a transparent benchmark and LEAN for independent reproduction where required. Do not infer AQR/KMLM's private splitting, order types or broker algorithms. [CHAT-05]

### 13.4 Strategy edge and execution quality are separate workstreams

The reported VATI trend-pullback and London-breakout backtests did not establish adequate promotion evidence in their tested configurations. Some earlier messages summarized this as “no edge”; the later unified source narrows the conclusion appropriately because evaluator limitations remain material.

Correcting execution measurement does not guarantee a positive strategy. Adding an attractive signal does not excuse incorrect fills, excessive costs or unmanaged exposure. Qualify both separately and then evaluate their combined account-level economics. [D4 opening; CHAT-05]

---

<a id="section-14"></a>
## 14. VATI Symbiotic Execution Fabric

### 14.1 Purpose

The proposed fabric should work the full lifecycle of an **already approved trading objective**, adapting its permitted execution approach to market/venue evidence while preserving one RiskAuthority, one router-controlled submission boundary and one durable account state.

It combines Nautilus-style recovery, Hummingbot-style finite executors, pysystemtrade/LEAN target-order decomposition and VATI's existing financial governance. This is an extension to VATI, not another autonomous bot. [CHAT-06]

### 14.2 Parent objective and child-order lifecycle

The discussion proposed the following logical progression; exact enums and relationships must be reconciled with the existing event and state contracts:

```text
APPROVED → RESERVED → PLANNED
    → child command durably recorded
    → SUBMITTED / OUTCOME_UNKNOWN
    → WORKING / PARTIALLY_FILLED / FILLED
    → CANCEL_REQUESTED / REPLACEMENT_PENDING / EXPIRED / REJECTED
    → RECONCILED
    → EVALUATED
```

A real state machine has branches and recovery transitions, not just this linear illustration. Parent completion depends on all child, cash, position and protection effects being reconciled; the first submission is not completion.

Every parent needs exact strategy/intent/risk/mandate identity, account/venue/instrument, approved quantity and exposure ceiling, permitted order types, price/slippage constraints, deadline, protection requirements, policy version and reservation identity. Each child remains bound to that parent and the current valid lease/fence. No child receives independent sizing authority. [CHAT-05–06]

### 14.3 Essential invariants

**Aggregate exposure:** cumulative fills plus remaining potentially executable child exposure must stay within the approved parent/account envelope. Cancel-pending orders still count. New relevant account conditions require the appropriate fresh risk validation.

**Durable intent before side effect:** record exact command identity before attempting submission. Use transactional outbox/recovery and durable idempotency. Lost acknowledgements are uncertain outcomes, not permission to retry blindly. Exactly-once economic effects require reconciliation; exactly-once network delivery must not be assumed.

**Receipt semantics:** accepted is not filled; partial is not complete; submitted cancellation is not cancelled; requested flattening is not flat. Preserve the venue's actual status and any unresolved quantities.

**Protection:** fills requiring venue protection cannot be declared protected without the required confirmation. If emergency closing is uncertain, keep unresolved exposure, block new risk and continue recovery until venue evidence establishes the state.

**Policy boundaries:** an executor may work within approved limits; it cannot widen stops, exceed quantity/price limits, clear a kill switch or promote a new policy. Execution optimization must not delay a mandatory protective action. [CHAT-05–06; D1 §§3.2,14.4,16.3]

### 14.4 Capability-negotiated adapter contracts

Extend the common interface without falsely claiming advanced support on every venue. Required behaviors to map include individual order lookup, working-order enumeration, update/fill history, cancellation request and confirmation, replace/amend semantics, time-in-force/expiry, supported stop types and partial-fill reporting.

Capabilities should distinguish broker-native features, validated local behavior and unsupported operations. A venue lacking reliable cancellation must refuse an algorithm that depends on it. A limit, stop or passive order must not silently become a different economic instruction; any separately admitted compatibility behavior needs explicit provenance and tests.

Keep cTrader, MT5 bridge/pull, Deriv, paper and owner-ticket semantics distinct. Deriv nonlinear/full-stake payoffs and owner-confirmed tickets cannot be forced into a fictional exchange-limit lifecycle. [CHAT-05–06; CODE-01–03]

### 14.5 Execution algorithms to introduce under that contract

| Capability | Intended use | Necessary boundary |
|---|---|---|
| Bounded immediate execution | Time-sensitive qualified action / protection | Respect admitted price, venue and risk semantics. |
| Passive limit with expiry | Lower-cost execution where waiting is acceptable | Actual order state, non-fill costs and cancel acknowledgement. |
| Bounded chase / replace | Adapt a working limit within a declared envelope | No unlimited repricing or simultaneous unreserved replacements. |
| TWAP-style scheduling | Work an approved quantity over time | Parent quantity, deadline, reservations and fresh risk checks. |
| Volume/participation-aware scheduling | Avoid excessive impact where trustworthy volume/depth exists | Observed venue data and lot/price constraints; no invented depth. |
| Portfolio target-delta working | Move from actual to approved target exposures | Netting/hedging mode, strategy ownership and pending exposure. |
| Hedge-on-fill / multi-leg research | Study paired positions and failed-leg behavior | Separate venue capital; no presumed atomicity across unrelated venues. |
| Inventory-aware quote research | Study spread capture, adverse selection and inventory | Remains a separately qualified research scope, not default live market-making. |

The current style selector's multi-slice plan must either execute through an admitted child protocol or be refused. Ignoring the slices and sending the full amount is not a valid implementation. [CHAT-05–06; CODE-17]

### 14.6 Portfolio-target execution

Derive trade deltas from approved target exposure minus confirmed holdings and still-working orders. Respect account hedging/netting mode, strategy isolation, manual/automatic ownership and permitted handovers.

Opposing strategy requests may sometimes be netted, reducing turnover, but not by silently changing ownership, mandate or risk meaning. Account-wide reservation and reconciliation remain authoritative. A target of two contracts when five are held implies reducing three, not opening a new independent position because a signal still points long.

This capability is potentially valuable even without a more accurate forecast because it can reduce avoidable costs and conflicting orders. That is a design rationale to test, not a measured VAN saving. [CHAT-05–06]

---

<a id="section-15"></a>
## 15. Execution economics, transaction-cost analysis and simulator repairs

### 15.1 Measure the complete trade, not only direction

Record observed bid/ask, price reference conventions, depth/size where available, fees, slippage, rejection/partial-fill status, financing/borrow, currency conversions and execution timing. Use the actual instrument, venue, side, quantity and policy.

Separate a forecast of costs from debited charges and realized proceeds. If bid/ask fills already include spread, do not charge it again. If a policy uses an estimated cost to reject candidates, that does not mean the paper cash ledger has paid commission or financing. [D1 §7.3; D2 §§2,30.7]

### 15.2 Timing and market-path realism

A signal requiring a completed bar cannot execute at an earlier unavailable price. Model acquisition, feature, forecast, decision, submission, acknowledgement and fill timing separately. Gap and stale-data behavior must retain uncertain/unfilled states.

Use actual ticks or finer bars where available. For OHLC-only ambiguity, evaluate common feasible market paths or conservative scenario bounds without independently choosing contradictory long/short histories. A stop is not guaranteed to fill exactly at its trigger through a gap; a touched limit is not guaranteed to fill regardless of depth/queue.

Qualify queue-sensitive maker research only with appropriate book evidence or explicitly limited conservative scenarios. Candles alone cannot prove queue priority. [D1 §§7.2–7.4,22.12]

### 15.3 Accounting identities and full-account replay

Reconcile initial capital, external cash movements, realized trading cash flows, unrealized mark-to-market, fees and final equity. Record terminal liquidation and all final charges. Report drawdown from the appropriate equity path, not only closed winners and losers.

Each policy arm needs its own account, holdings, reservations, pending orders and opportunity availability. Skipping one trade can make another possible. Summing independently unconstrained single-symbol returns is not a feasible portfolio backtest.

Capital and risk cannot be released solely because a cancellation was requested. A deposit is not trading alpha; a withdrawal is not a trading loss, although less collateral can constrain subsequent trading. [D1 §7; D2 §30.9]

### 15.4 Enrich TCA and attribution

The current TCA module is a useful owner to extend. Capture genuine decision, arrival, submission, acknowledgement and fill observations; placeholder or identical timestamps cannot establish latency performance.

Attribute forecast error, delay, spread, price impact, adverse selection, non-fill opportunity cost, rejects and operational failures separately where the evidence supports it. Label ambiguous causes rather than inventing precision.

A strategy may be sound at signal time but lose edge before execution. Conversely, good fills do not make a bad strategy profitable. The feedback loop must preserve that distinction when evaluating future changes. [CHAT-05,07–09]

### 15.5 What execution learning should optimize

Compare expected and realized cost for comparable **broker/account/instrument/session/volatility/event/direction/template** buckets, with the quantities and other context required by the actual target.

Use fill probability, partial/cancel behavior, slippage, adverse-selection observations, non-fill costs and implementation shortfall as explicitly defined measures. Do not confuse the execution policy's cost estimate with a guaranteed tail-loss bound or with the portfolio risk service's separate expected-shortfall concept.

The best template is the one with defensible lower expected economic cost under the current permitted objective, not necessarily the one with the highest fill rate or most passive orders. Waiting can destroy an otherwise attractive opportunity. [CHAT-09; CODE-05]

---

<a id="section-16"></a>
## 16. Adaptive feedback: existing behavior and the missing positive-improvement loop

### 16.1 Three different forms of adaptation

| Form | Existing evidence from the chat | Desired influence |
|---|---|---|
| Immediate market/risk response | Rule-based protection, position health and permitted adjustments exist in source. | Respond to current observations within existing policies. |
| Outcome-based defensive learning | Broker/strategy health and reduce-only feedback are wired in reviewed source. | Restrict poor conditions, skip/degrade strategies and preserve state on restart. |
| Strategy/model/execution-policy evolution | Research/candidate components exist; full autonomous train/evaluate/admit/consume lifecycle not established. | Produce, test and separately admit genuinely better alternatives. |

VATI is therefore partially adaptive, not already a proven end-to-end self-optimizing trader. Live deployment and effect timings were not established by the prior source reads. [CHAT-07–09]

### 16.2 Source-level feedback that is already connected

The reviewed `DecisionCycle` and account trade lifecycle use:

```text
Filled entry
    → TCA record
    → LearningHooks.on_tca()
    → BrokerLearner
    → broker-liquidity multiplier in the opportunity/meta-label path

Completed trade
    → review / decision-quality evidence
    → LearningHooks.on_review()
    → StrategyHealthTracker
    → capsule-health multiplier / possible demotion
    → later opportunity decisions
```

The single-account service constructs learning hooks and calls learning-state restoration. The account-level runtime passes learning into its lifecycle. `replay.py` rebuilds applicable strategy and broker state from durable records carrying their original environments. These are concrete source connections, not simply planned documentation. [CHAT-08–09; CODE-06–13]

### 16.3 What those connections do not yet prove

A broker-liquidity penalty does not prove that VATI learned to prefer passive rather than aggressive execution. A strategy-health score does not rewrite a breakout rule. A protected position adjustment follows an existing rule, rather than establishing that its parameters were learned from recent trades.

The inspected research workflow exposes drift, exit-policy studies and other bounded operations. The candidate-evolution helper can create a revised RESEARCH capsule, but a continuously running production caller and automatic consequential replacement were not established. Research reports must not be presented as live strategy evolution. [CHAT-09; CODE-14–16]

### 16.4 Complete the execution-policy feedback connection

The final source review found an `ExecutionPolicyEngine` with a real `observe()` method and evidence-based `select()` method. The live callers construct the engine and call `select()`. Searches of the inspected main callers did not establish the production `observe()` route; evidence was an in-memory map in the implementation reviewed.

The required connection is:

1. Bind every applicable order decision to the exact execution bucket, template and policy version used.
2. Record actual fills, partial fills, cancellations, expiry, rejection and non-fill outcomes with correct identity and context.
3. Attach only the measurements supported by the evidence; do not manufacture realized execution statistics for unexecuted hypothetical trades.
4. Update the existing engine's eligible evidence through a deterministic validated consumer.
5. Persist and reconstruct those observations/statistics before subsequent policy selection.
6. Demonstrate that an admissible sequence of outcomes changes a later eligible selection, and that replay produces the same change.
7. Prove that missing/thin/stale/incompatible evidence keeps the declared fallback, while mandatory protection is unaffected.

These are closure obligations derived from the identified missing producer-to-consumer path, not a claim that the missing path has now been implemented. [CHAT-09; CODE-05–08]

### 16.5 Keep observations and sample meaning honest

The inspected LearningBoundary uses a minimum of **30 environment-weighted samples** for restrictive feedback. Historical replay/backtest/counterfactual observations carry zero weight as real broker execution facts in that reviewed weighting scheme. These are existing code settings, not a statistical guarantee that 30 trades are sufficient.

Keep actual live, demo, shadow, backtest and counterfactual provenance distinct. Several fill or evidence records about one trade must not be counted as independent successful trades. Preserve original context during replay; unknown old metadata must not be guessed from today's session.

Faster feedback must not turn unfinished trade paths into mature supervised outcomes. Outcome maturity and processing speed are different constraints. [CHAT-08–09; D1 §§5–6; D2 §30.4]

### 16.6 Diagnose before adapting

| Observed situation | Appropriate learning question | Incorrect shortcut |
|---|---|---|
| Correct directional forecast but high slippage | Was execution timing, venue quality or liquidity the problem? | Penalize the forecasting model automatically. |
| Wrong direction despite good fills | Did the signal fail in this regime? | Attribute every loss to the broker. |
| Profitable result after a policy violation | Was it a lucky bad decision? | Learn that violating controls is useful. |
| Losing result with correct process | Is it normal strategy variance or actual deterioration? | Rewrite policy after one loss. |
| Skipped winner | Was it feasible and eligible with information available then? | Use hindsight to weaken a valid risk rejection. |
| Repeated unfilled passive orders | Did saved spread outweigh missed-opportunity cost? | Treat zero fill costs as superior execution. |
| Jev diagnostic claim | Is the interpretation supported by independent evidence? | Relabel it as a broker fact or calibrated trade probability. |

The chat's recommendation is to learn from both successes and failures, accepted and rejected opportunities, without conflating decision quality with P&L sign. [CHAT-07–09]

### 16.7 Complete the positive-improvement lifecycle

The desired slower loop is:

```text
Matured outcomes / drift / missed-opportunity or execution evidence
    → registered research hypothesis
    → candidate strategy, model or execution-policy version
    → chronological study and independent account replay
    → prospective shadow / permitted demo evidence
    → independent scope-specific qualification
    → existing authorized admission/binding
    → later eligible decisions use the admitted version
    → continued monitoring, revocation and compatible rollback
```

The old strategy/model/policy remains versioned. A candidate is not a mutation of an open trade's original thesis. Test both the valid positive path and rejection/recovery; a permanently unbound producer is not a completed loop.

This does not imply automatic permission to deploy newly learned strategies. The reviewed LearningBoundary explicitly forbids direct changes to mandate, ceilings, leverage, capsule logic/promotion, risk policy, execution policy and production model aliases. Selecting among already qualified alternatives under an admitted policy is different from rewriting those policies. Any broader auto-promotion behavior requires a separately specified and authorized policy; none is inferred here. [D1 §§11–13,19; CHAT-09; CODE-12]

### 16.8 Risk response to positive results

Good evidence may justify prioritizing an already qualified strategy within the approved account budget. It does not automatically increase risk ceilings, remove stops or restore a suspended strategy's authority.

Likewise, a stop moved to break-even is an order/protection condition, not a guarantee of zero real-world gap, liquidity or counterparty loss. The proposed execution/evaluation improvements must not derive unlimited additional exposure from that label. Preserve the actual loss model and current authoritative checks. [CHAT-06–07; D1 §§7.2,22.11]

### 16.9 Two speeds, with explicit observation-triggered updates

Keep the fast operational path local and deterministic. It applies existing controls, records outcomes and updates permitted defensive statistics. Use asynchronous diagnostics and research for slower interpretation, trial creation and model/policy evolution.

The conceptual middle layer—strategy and broker learning after sufficient observations—does not require a third trading authority. It is a constrained consumer of the same durable evidence. [CHAT-07–09]

---

<a id="section-17"></a>
## 17. Jev: useful integration, latency limits and quality qualification

### 17.1 What the chat actually established

An unmerged canon branch contains `JevVanAdvisor`, projection/API clients, attention/critic/browser consumers, fallback behavior and tests. It consumes the shared `dial-jev` service through scoped credentials; it is not another Jev server or VATI order owner.

The code reviewed exposed modules for attention fields, critical reasoning and browser state. That does not establish complete trading-failure diagnosis, matured trade-outcome joins, execution-policy learning or profitable strategy improvements. Existing infrastructure can be reused, but each trading-domain question set needs its own evidence and consumer tests. [CHAT-08; D2 §30.11; CODE-19–20]

### 17.2 The recommended Jev role

Use narrow, falsifiable, typed questions over sanitized, versioned evidence. Appropriate examples from the discussion include inconsistent identifiers, unsupported claims, missing evidence, contradictory context and whether observations are temporally comparable.

Each judgment should retain input/snapshot hash, registered question set and version, provider/model, result fingerprint, unknown/unanswered fields, cost, elapsed time and expiry. Untrusted social/source text cannot contain operative broker commands. Jev may propose an interpretation; the deterministic evidence/consumer boundary decides whether it is usable.

Its answer confidence is not a calibrated probability of a profitable trade. Its explanation cannot overwrite fills, cash, source timestamps or risk decisions. [D2 §§7,30.11]

### 17.3 Do not confuse timeout with measured performance

The inspected gateway adviser used a 1.2-second HTTP client timeout setting. That is configuration, not an observed mean, P95, P99 or guaranteed end-to-end deadline.

No qualifying measurement in this chat established that Jev reduced VATI feedback-injection latency or improved net trading results. Its benefit remains a hypothesis to test against the deterministic baseline and an appropriate alternative. [CHAT-08; CODE-19]

### 17.4 Remove nonessential model waits from the critical path

The source review found that account `_risk()` invoked `cognition.wake()` synchronously after the risk decision but before returning. The judgment may have no authority to change that decision and still delay the caller when an external invoker is configured.

The recommended correction is to commit the evidence/decision, schedule bounded asynchronous interpretation, and let any valid result influence only a later eligible consumer. Keep fills, broker health, protection and immediate risk feedback independent of Jev availability.

The actual current delay and deployed invoker configuration were not measured. The improvement concerns the source-level dependency and requires runtime timing/noninterference tests. [CHAT-08; CODE-07,21]

### 17.5 Measure latency at the right boundaries

| Measurement | What it answers |
|---|---|
| Source event → receipt by VAN | Was information acquisition timely? |
| Receipt → durable evidence | Did persistence or processing delay the fact? |
| Durable evidence → permitted local adjustment | Is the existing deterministic feedback promptly available? |
| Evidence request → Jev answer | How long does optional interpretation take, including queue/service overhead? |
| Jev answer → validated usable annotation | How much does validation/joining add? |
| Usable evidence → next eligible decision | Did the information arrive in time for its actual trading horizon? |
| Research trigger → evaluated/admitted policy | Does Jev improve research throughput or review quality? |

Record P50/P95/P99, timeouts, stale-result rejection, fallback and service/queue costs separately. Do not compare remote interpretation to a local arithmetic operation and call it faster simply because it is faster than a different large-model workflow. [CHAT-08]

### 17.6 Quality and economic experiment

Compare identical sealed cases under deterministic/no-LLM analysis, Jev-assisted analysis and an approved challenger where appropriate. Blindly review diagnostic correctness against independently established labels, not the model's self-assessment.

Measure unsupported conclusions, false vetoes, missed valid opportunities, abstention, cost per useful judgment and source leakage. When decisions change, use full matched-opportunity/account replay. Report whether the improvement is diagnostic, operational, defensive or economically positive; do not promote one category into another.

If Jev only helps explanation or research triage, retain that bounded use. Live selection or policy influence requires its separate evidence and authority. Jev outage or an unqualified judgment must never block a mandatory exit. [D2 §30.11; CHAT-08]


---

<a id="section-18"></a>
## 18. Trading temperaments, strategy lifecycle and owner authority

### 18.1 One execution system for Normal, Risky and Aggressive

The three opportunity temperaments are not three broker engines and are not substitutes for demo/live authorization states.

| Temperament | Intended behavior discussed | Prohibited inference |
|---|---|---|
| Normal | Conservative selection and cost-conscious execution inside the signed budget. | A low-risk label makes stale data or incomplete protection acceptable. |
| Risky | More assertive selection/use of the permitted budget for qualified setups. | The mode can widen the owner mandate or bypass risk checks. |
| Aggressive | Select exceptional opportunities using independently admitted edge and feasible execution. | High confidence alone permits maximum slippage, oversized orders or skipped safety checks. |

Aggressive mode can rationally reject more marginal opportunities than Normal. The same factual inputs and hard constraints apply; the qualified selection policy differs.

The PR92 discussion identified an intentionally unbound independent edge-evidence producer as a live-admission restriction. The integrated forecast plan requires a real producer and both valid sandbox and invalid/missing/wrong-scope cases—not a permanently refusing dataclass presented as a completed feature. [CHAT-03,06–07; D1 §13.3]

### 18.2 Strategy/capsule lifecycle

Retain distinct research, backtest, validation, demo/shadow and controlled live states. A candidate revision must preserve its parent and lineage, data/feature/target/cost identity, test results and admission scope.

Research can cluster failures, propose constraints or compare exits. It cannot directly rewrite an existing live capsule or promote itself. Automatic demotion/restrictive feedback and owner-authorized promotion are separate operations. A successful training or backtest run does not alter the live model alias or strategy by itself. [CHAT-09; CODE-12–16]

### 18.3 Active positions and manual ownership

Protective tightening, exits, reductions and permitted additions continue through the existing lifecycle and risk/router boundaries. New learned policies do not retroactively change the original thesis, widen an open stop or erase an outstanding reservation.

Preserve manual/automatic ownership and handover semantics in the parent programme. Research cannot silently assume control of an owner-managed position. Cost optimization, Jev advice or model outage cannot overrule mandatory risk-reducing actions. [D1 §§13.3–13.4,22.10; D4 §0.2; CHAT-06]

---

<a id="section-19"></a>
## 19. Scientific evaluation, profitability evidence and experiment design

### 19.1 The central admission question

Use a preregistered, task-appropriate utility measure:

```text
ΔU = U(VATI with the candidate improvement)
     - U(the qualified VATI baseline)
```

Compare the same admissible opportunity stream, information timing, risk constraints and capital resources. Include spread, slippage, fees, financing, market impact, non-fill opportunity cost, data/compute overhead and actual operational burden.

A better forecasting score, more frequent winners or lower drawdown from simply trading less is not enough. Determine whether the added information or behavior improves the actual decision at comparable exposure and risk. [D1 §§15,22.15; D2 §§4,30.9]

### 19.2 Chronology and fit boundaries

Freeze training, model-selection validation, calibration and test/holdout periods before examining their outcomes. Purge labels whose outcome-information intervals overlap forbidden periods, and apply the declared embargo/gap where needed.

Preserve legitimate historical warmup while prohibiting future labels, revisions and preprocessing leakage. Align folds across peer assets/global models. Match simulated retraining cadence to the intended deployed candidate workflow.

The final holdout cannot become another tuning set. Keep losing, failed, pruned and alternative feature/horizon/calibration trials in the trial census. [D1 §6]

### 19.3 Sample adequacy and statistical limits

The earlier inspected validation policy included DSR probability, PBO, observation and walk-forward minimums. Preserve applicable canonical fields rather than replacing them with a convenient new threshold. Their numerical presence does not establish independence, sufficient power or suitability for every task.

The High-Value proposal's positive lower-95%-confidence-bound criterion belongs as a candidate setting in the one versioned validation policy, with materiality, dependence-aware resampling and stopping rules specified before results. It must not become another authority service or a guarantee of profitable deployment.

Use justified event/time/asset-cluster handling; overlapping forecasts are not independent trades. A short calendar period or many quote rows may still contain little independent information. Inadequate evidence yields `INCONCLUSIVE`. [D1 §§6.4,15; D2 §30.9]

### 19.4 Metric families

| Evaluation question | Measures to retain |
|---|---|
| Return forecasts | Appropriate loss versus persistence/zero-return/linear/tabular baselines; direction and rank as diagnostics; horizon/regime detail. |
| Event/setup probabilities | Brier/log loss, reliability, declared ECE, base-rate comparison, discrimination, abstention and decision utility. |
| Quantiles/distributions | Pinball/proper score, coverage, interval width, violation clustering, tail/domain behavior and uncertainty. |
| Volatility | Comparable original-domain loss and valid volatility metrics versus historical/HAR/GARCH baselines. |
| Order execution | Implementation shortfall, fill/partial/cancel/reject behavior, price-limit correctness, actual fees, latency and non-fill opportunity cost. |
| Account economics | Net cash/P&L, mark-to-market drawdown, risk-adjusted utility, turnover, capital efficiency, concentration and tail exposure. |
| Defensive screening | Dangerous outcomes avoided minus legitimate opportunities falsely rejected; coverage and unresolved cases. |
| Jev contribution | Valid diagnosis, unsupported claims, false vetoes, latency, cost, stale/unknown responses and incremental policy value. |
| Operational quality | Recovery, duplicated effects, reservation integrity, evidence completeness, service/resource noninterference. |

### 19.5 Same-trade attribution versus changed-policy evaluation

Preserve the existing size-only shadow comparison under its proportional assumptions. `actual_R × multiplier` may be a limited attribution in common baseline risk units; it is not an independent hypothetical trade's own-risk return.

If selection, entry time, route, exit policy or capital usage changes, replay that policy separately with correct fills and account state. Label it simulated counterfactual, not realized. Do not scale nonlinear fees, market impact or available liquidity by one multiplier.

A paired simulation estimates incremental policy performance under its specified assumptions. It does not automatically identify a causal real-world effect. Prospective evidence and independent review remain necessary for consequential use. [D2 §§4,30.9; CHAT-07–09]

### 19.6 Consolidated experiment portfolio

Existing named experiments and later suggested comparisons should be mapped into the same study system, not run as untracked one-off notebooks.

| Experiment family | Comparison | Main question |
|---|---|---|
| EX-01 executable economics | Incumbent versus richer cost/liquidity evidence | Does better executable information improve net results and tail behavior? |
| EX-02 tabular forecasting | Existing strategy versus calibrated LightGBM evidence | Is there incremental value beyond existing rules? |
| EX-03 temporal forecasting | Strong tabular baseline versus NeuralForecast additions | Does temporal/distributional modeling justify its complexity and cost? |
| EX-04 safety funnel | Same discovered crypto cohort with/without deterministic screens | Is defensive benefit greater than false rejection/opportunity cost? |
| EX-05 wallet history | Safety baseline with/without temporal attribution/flow | Does history add information beyond snapshot screening? |
| EX-06 Jev | Same cases/policy with and without qualified typed judgment | Are diagnosis, decisions and net utility actually better? |
| EX-07 event context | Existing forecasting versus prediction-market features | Does the added source outperform existing context? |
| PM-STUDY-01–04 | Risk filter, surprise, volatility and opportunity ranking | Preserve the specific event controls in §11.11. |
| Execution-template learning | Fixed qualified fallback versus evidence-driven selection | Does the wired policy improve actual execution cost under the same authority? |
| Parent/child execution | Feasible single-order baseline versus staged execution | Are impact, delay, non-fill and recovery better at the approved size? |
| Portfolio-target execution | Independent intent working versus authorized target-delta netting | Does reduced turnover improve account economics without changing risk/ownership? |
| Systematic strategy reproduction | Incumbent versus transparent multi-horizon trend/carry candidate | Does an evidence-backed strategy family transfer to VAN's actual instruments? |
| Kronos/Chronos challengers | Strong task-specific baseline versus added model information | Is the contribution positive without depending on an unproven foundation model? |
| Event market-making / arbitrage labs | Full payoff, queue/cash and adverse-selection scenarios | Are theoretical margins robust to the actual rules and execution assumptions? |

The later unnamed experiment families are recommendations for registration, not new issued canonical study IDs. [D1 §22.15; D2 §4; CHAT-01,05–09]

---

<a id="section-20"></a>
## 20. Consolidated acceptance and fault-injection obligations

These are a consolidated checklist, not a replacement for the existing application test registries and not claims that these cases passed. Preserve the original IDs and bind any additional cases through the actual plan/contract generator.

### 20.1 Required positive paths

A complete capability needs more than refusals. Demonstrate a valid data import, correct feature/target conversion, real model fit, artifact reload, qualified-scope inference, outcome attachment, valid sandbox candidate review/admission, revocation and compatible recovery.

For execution, demonstrate approved and reduced commands, a genuine supported resting order, partial and full fills, confirmed cancellation, protective tightening, verified exit and restart reconstruction. For adaptive execution, demonstrate that valid matured evidence changes an eligible later policy selection and that replay reconstructs that change.

No-trade, model rejection and source unavailability are legitimate outcomes, but cannot be the only exercised states of software whose positive operation is mandatory. [D1 §§7.4,19–21; D2 §30.12; CHAT-09]

### 20.2 Data, forecast and research cases

| Case | Required outcome |
|---|---|
| Future feature/negative shift/centered window | Bias analysis detects the prohibited information path. |
| Whole-dataset scaler or vocabulary | Fold-boundary failure, not a better-looking backtest. |
| Revised release or incomplete higher-timeframe candle | Historical availability gate refuses the input. |
| Invalid OHLC, nonfinite forecast or incompatible units | Explicit invalid/abstain state; no financial consumer. |
| Missing previous window / young token | Unknown rather than fabricated growth or denominator. |
| Duplicate ticker or different derivative with similar symbol | Canonical identities remain distinct. |
| Wrong model/feature/calibrator/target/horizon | Binding rejected with a precise reason. |
| Expired model or revoked source | No silent extension or stale result marked current. |
| Quantile crossing / invalid positive-domain output | Detect and apply only an admitted correction or reject. |
| Raw scenarios averaged before retention | Scenario-contract test fails; no claim of individual path availability. |
| Marginal paths presented as joint portfolio samples | Scope/semantic validation fails. |
| Rank or Jev confidence inserted as probability | Output/use contract rejects the semantic mismatch. |
| Data correction or consent revocation | Descendant invalidation/revalidation and retention handling are traceable. |
| Interrupted training/export/publication | Durable attempt state and reconciliation; no duplicate artifact or implied promotion. |
| Mid-decision model update | One decision retains one valid epoch. |
| Holdout reused for tuning | Study cannot qualify under the frozen protocol. |

### 20.3 Execution, protection and adaptive-policy cases

| Case | Required outcome |
|---|---|
| Marketable buy/sell limit | Never fills worse than its actual limit under the admitted order semantics. |
| Both stop and target touched inside coarse bar | Explicit common feasible path/ambiguity; no directional preference hidden in ordering. |
| Gap through protection | Available-price/slippage model, not a guaranteed stop-price fill. |
| Policy deadline shorter than adapter default | Exact approved expiry propagates and persists. |
| Accepted but unfilled entry | Pending reservation, not a phantom open position. |
| Partial fill followed by cancellation | Filled exposure protected and remaining reservation released only on confirmed outcome. |
| Duplicate/out-of-order fill updates | No duplicate quantity, fee or completed-trade sample. |
| Submission acknowledgement lost | Outcome remains unknown; query/reconcile before any safe retry. |
| Cancel request followed by late fill | Exposure remains accounted for; cancellation request is not terminal truth. |
| Replace while prior order may still be live | Total potential exposure respects the parent/account reservation. |
| Multi-slice style on a single-command-only route | Refuse until an admitted child protocol exists; never ignore the selected style. |
| Unsupported venue stop/cancel/replace | Capability refusal, not silent type coercion. |
| Missing or failed protection on immediate/resting fill | Required protective recovery with truthful state. |
| Emergency close rejected/unknown | Do not declare flat; block new risk and continue reconciliation/protection. |
| Crash with pending orders or uncertain publication | Reconstruct durable state before decisions; do not free exposure by restarting. |
| Terminal liquidation | Fees/cash/final equity agree after final effects. |
| Doubled costs / liquidity drought / failed route | Stress results and admission reflect the deterioration. |
| Competing account opportunities | Shared capital, margin and risk constraints hold across instruments. |
| Execution evidence missing/thin | Declared fallback, not imaginary learned policy. |
| Valid template-specific outcomes mature | Existing evidence owner updates; later selection and replay demonstrate the intended effect. |
| Backtest execution treated as real broker evidence | Provenance/weighting boundary refuses the substitution. |
| Good performance attempts to raise a mandate | Existing authority rejects the unauthorized change. |

### 20.4 Jev, event and crypto cases

| Case | Required outcome |
|---|---|
| Jev shadow result | Recorded but no unauthorized effect on deterministic decisions. |
| Jev timeout/failure/stale result | Existing deterministic path continues within its own policy; protection unaffected. |
| Synchronous remote cognition stalls | Timing test reveals the dependency; asynchronous design isolates it. |
| Jev unsupported explanation / source instruction injection | Not converted into execution facts or commands. |
| One surviving token | All remaining gates still run; no-trade remains possible. |
| String `"no"` authority field | Correct typed normalization, not truthiness. |
| Technical pool mistaken for insider | Preserve raw data; require evidence for adjusted ownership interpretation. |
| Buy succeeds, sell fails or tax changes | Exitability remains failed/unknown at the relevant state. |
| Proxy implementation/transfer hook changes or chain reorganization | Invalidate affected findings and downstream caches before reuse. |
| Two event titles look similar but settle differently | Related/ambiguous rather than exact hedge. |
| Threshold probabilities overlap or violate monotonicity | Coherence failure or explicit versioned adjustment, not naive summation. |
| Contract roll presented as changing expectations | Correct event mapping or reject the comparison. |
| Outcome already known before administrative market close | Cannot count it as early forecasting skill. |
| Two venues/model explanations use the same underlying news | No false independent confirmation. |
| Arbitrage first leg fills, second fails | Explicit residual risk, cash reservation and failure scenario. |
| Cancelled quote possibly filled / settlement delayed | Pending exposure and cash remain until confirmed/reconciled. |
| Maker fills occur after adverse information | Fill-conditional economics reveal the cost; spread capture alone does not qualify. |

### 20.5 Evidence required to close work

Each implementation unit must identify source/environment, actual producer, durable state, consumer and production caller; complete operations and errors; authority scope; positive/negative/recovery evidence; resource/cost measurements; and rollback/runbook.

Component tests do not substitute for actual upstream library and permitted provider integration. Fixture/schema/graph mutations test document or synthetic properties, not financial performance. Actual source, VM, broker and handset tests remain separately scoped. [D1 §§18–21; D2 §§12,30.14–16]

---

<a id="section-21"></a>
## 21. Runtime placement, budgets, observability and recovery

### 21.1 Placement and operational constraints

Use the qualified Netcup/Oracle VM topology through Global DIAL's current typed owner/project controls. Do not execute project work on the prohibited physical desktop or silently substitute the chat container for VM/runtime qualification. This compilation's file assembly is document processing, not VAN code execution.

Resolve actual host architecture, resource availability, source binding and transport from live evidence when implementing. A reachable control gateway or old capacity figure does not establish healthy forecasting workers or safe headroom. Existing Zuul admission remains the intended route; do not add a second GitHub Actions deployment authority. [D1 §16; D2 §§30.15–16]

### 21.2 Resource isolation

Keep model training, historical replay, source acquisition and Jev/research calls outside T0. Bound CPU threads, memory, disk, queue depth, concurrent fits, time, output samples and provider requests. One library's hidden thread pool must not starve broker protection.

Start with measured CPU tabular workloads and appropriately bounded neural studies. Additional accelerators, paid services or accounts require their separate existing authorization; none are purchased by compiling this document.

Training workers have no broker/order credentials or ability to issue model-use authority. Forecast serving consumes only verified admitted artifacts and snapshots. Source credentials stay within the permitted read boundary. [D1 §§3,16]

### 21.3 Recovery obligations

| Failure | Required response |
|---|---|
| Training worker or lease dies | Preserve attempt state; resume/retry only against compatible immutable inputs. |
| Artifact corrupt/incomplete | Quarantine; retain only a still-valid prior binding. |
| Registry unavailable | Already admitted local artifact may serve only within its actual validity. |
| Feature/source epoch missing | Abstain or admitted fallback; reconcile before reuse. |
| Disk/queue/memory exhausted | Bounded backpressure and truthful failure; never silently drop financial events. |
| Model or data rollback | Preserve compatibility and do not resurrect revoked evidence. |
| Broker or order outcome unknown | Existing exposure/reservations remain; investigate actual venue truth. |
| Data source corrected/reorganized/revoked | Trace descendants and invalidate/revalidate according to policy. |
| Jev unavailable | No invented diagnosis; deterministic trading/protection behavior does not depend on it. |

### 21.4 Observability and the proprietary evidence advantage

Trace information cutoff → feature/target snapshot → study/model/calibration → issued forecast/judgment → opportunity/risk decision → order/venue update → reconciled outcome → feedback effect → any later admitted policy revision.

Record queue and inference latency, forecast/source age, calibration quality, domain novelty, aborts and stale responses, execution cost, order recovery, strategy health, model contribution, false rejections and actual compute/provider cost. Archive failed as well as successful experiments.

This creates proprietary evaluation and execution evidence over VAN's actual instruments and brokers. The benefit is the ability to learn what genuinely works in that environment—not merely accumulating more raw data or model names. Protect owner-private data and apply explicit retention/consent policies. [D1 §§5.6,15–16; CHAT-01,07–09]

---

<a id="section-22"></a>
## 22. Owner-facing controls and truthful presentation

### 22.1 Backend contracts first

Before frontend work, provide usable APIs/readbacks for forecast status/history, feature and dataset lineage, studies, job request/cancel/status, model comparisons, qualification/rejection, expiry, revocation, rollback, execution state, feedback effects and source health.

Expose exactly which policy/version changed, which evidence supported it, which consumer applies it and which future decisions are eligible. Do not label “adaptive enabled” when the evidence producer or consumer is unbound. [D1 §§14,17; D2 §30.13; CHAT-08–09]

### 22.2 Later native integration

After the actual global BG-001, integrate through existing Trading, Chart/Replay, Positions, Risk/TCA, Strategies/Modes, News/Events, Research/Analyst, Work/Evidence, Memory/Automation and Settings contexts. Preserve the locked dark/light/native direction and existing whole-product obligations.

The six high-value views remain contextual, not six new global tabs: discovery funnel; security finding; wallet/flow evidence; sellability/economics; matched-cohort report; typed judgment trace. Do not crowd Home or turn a compact orb summary into a second dashboard. [D1 §17; D2 §30.13; D4 opening]

### 22.3 Essential visible distinctions

The owner should see research, historical, delayed, fixture, simulated, shadow, demo and actual live evidence as different states. Show unknown/unsupported/stale/rejected/inconclusive/offline conditions with reasons, not green placeholders.

A forecast band must identify horizon, cutoff and calibration; a probability must name its event; a ranking must not look like a win probability; an order must distinguish working, partially filled, cancel-pending and reconciled; P&L must distinguish realized cash from floating inventory.

Show the candidate funnel with complete observed/rejected/eligible/economically assessed/paper/actual-fill counts only where those records exist. A read-only crypto capability can correctly show zero actual fills. No “safe token” badge or new signing/funding/order action is added by this research scope. [D1 §§14,17,22.17; D2 §30.13]

---

<a id="section-23"></a>
## 23. Integration order and coding-agent handoff

### 23.1 One dependency-ordered programme

The following order consolidates the chat's recommendations. The existing generated graph remains authoritative; this is not another executable schedule.

| Stage | Work to complete | Critical exit |
|---|---|---|
| Source and authority reconciliation | Refresh relevant heads, select compatible function-level changes, preserve source lineage and current scope. | PRE-001/PRE-002 and actual required independent predevelopment admission. |
| Execution/evaluator correctness | Limit prices, order semantics, expiry, pending protection, costs, cash and account replay. | Nonvacuous positive and adversarial source/runtime evidence. |
| Order lifecycle and adapter capabilities | Durable commands, receipts, cancellation/replacement, uncertain outcomes, partial fills and recovery. | No duplicate or unaccounted exposure; actual supported capabilities. |
| Data/research/forecast implementation | Point-in-time datasets, Qlib/LightGBM, required NeuralForecast plugins, calibration and artifacts. | Real model round trips, correct targets/folds, safe serialization. |
| Execution and model adaptation | Connect policy observations, durable statistics, valid alternatives, candidate jobs and outcomes. | Demonstrated producer→state→consumer→later-decision effects and replay. |
| Specialized research additions | Complete event labs and read-only crypto/security/wallet scope through shared owners. | Actual software/provider boundaries and domain-specific failure cases. |
| Independent evaluation and backend closure | Full comparative studies, operations, recovery, APIs and all mandatory backend verifiers. | The single actual BG-001, not a subset gate. |
| Native experience and final release | Required post-BG contexts, real device accessibility/state handling and product acceptance. | Separate release and any strategy/model financial authority. |

Dependency-ready units may run in parallel under resource and scope constraints. Preserve all mandatory functions; negative economic findings do not justify deleting model integrations, and blocked external proof does not waive genuine backend integration obligations. [D1 §18; D2 §30.14–16]

### 23.2 Existing adoption crosswalk to preserve

| Original adoption | Existing duty/reference | Compiled treatment |
|---|---|---|
| A01 executable economics | Forecast 007/009/010/044; BE-010/035; high-value economics | Extend, with fact/forecast separation and DEX-specific exitability. |
| A02 quantitative forecasting | Forecast 011–025 | Preserve full mandatory model/lifecycle scope. |
| A03 matched evaluation | Forecast 005/007/008/010/027/030/031/047 | Complete cohorts, changed-trade paths and whole-account comparison. |
| A04 discovery | BE-037/038 and admitted related chain/sellability units | Read-only domain addition with canonical identity and durable funnel. |
| A05 chain/wallet evidence | BE-039–043 within the integrated scope | Chain-specific facts, temporal attribution and invalidation. |
| A06 Jev | Existing shared gateway/cognition/evidence owners; BE-021/044 | New registered trading-domain questions and evaluated effects, not another service. |
| A07 prediction markets | Forecast 037–048 | Retain the full event programme, not only probability-change context. |
| A08 agents and owner views | Existing orchestration and post-BG UX/native units | Clear roles and factual readbacks; no early UI or new order authority. |

These are preserved source crosswalk references. Exact changes to later execution lifecycle, policy-observation wiring and asynchronous cognition must be mapped at the actual contract/operation level, then regenerate the combined graph and its scope digest. This compilation does not invent new packet numbers or assert that those later changes are already covered in full by any named unit. [D2 final crosswalk; D3 §3]

### 23.3 Handoff instruction

> Work from the currently independently admitted unified VAN specification and exact source bindings. Use this document as the complete conversation-derived recommendation and gap register, not as permission to bypass the plan. Preserve all existing forecast, prediction-market, read-only crypto, account, Jev, evidence and product scope. Reconcile branch contributions by function and caller. Close the economic simulator and order/protection correctness issues before claiming strategy/model value. Wire actual outcomes into the existing execution-policy evidence owner and prove their effect on subsequent eligible decisions. Keep cognitive/Jev work asynchronous and maintain deterministic local protection. Implement the complete positive candidate-training, artifact, evaluation, admission/revocation and recovery paths while keeping consequential promotion separate from retraining. Use qualified VM/Zuul/Global DIAL routes and record actual receipts. Report implemented, integrated, tested, deployed and economically qualified states separately. Do not create another trading engine, Jev service, model registry, calibrator or financial ledger. Do not start new frontend work before the sole global backend gate.

This handoff consolidates instructions already discussed. It does not authorize code execution, merges, service mutations, purchases, funded accounts or live trades merely by being included in a Markdown file.

---

<a id="section-24"></a>
## 24. Outstanding decisions and explicit non-claims

### 24.1 Decisions that remain scope-specific

The conversation did not establish final initial instruments/horizons, all actual data-use entitlements, live venue capabilities, provider budgets, statistical materiality thresholds, the eventual best model, or a universally optimal trading setup. Resolve them through the existing relevant admission contracts rather than inventing defaults.

New live event-contract trading, chain custody/signing, additional venues, paid-data/compute procurement and any automatic consequential promotion policy remain separate scope/authority decisions. The owner explicitly excluded new licence procurement in the current phase. That direction is preserved without claiming that hosting changes provider eligibility or that unconfirmed data rights are granted. [D1 §19.2; D2 §30.1]

### 24.2 Claims not supported by this chat

The available record does not establish that:

- VATI is deployed with every discussed feedback and forecasting connection active.
- Jev improves trading-feedback latency, diagnostic accuracy or profitability on VAN's actual workload.
- Kronos, Chronos, LightGBM, NeuralForecast or any open-source bot is inherently profitable.
- The entire source across every branch has passed semantic, runtime or broker qualification.
- A reported profitable organization exposes a copyable configuration with equivalent execution access.
- Fixing an execution defect proves the underlying strategy has positive edge.
- A passing blueprint/schema/graph check is a passing application test, F15, BG-001 or financial mandate.
- A lower risk multiplier, positive closed-trade grid total, or winning streak establishes improved risk-adjusted account value.
- Read-only simulation proves future sellability, fills, protection or settlement.

These limits are part of the consolidated recommendations, not reasons to stop completing the controllable engineering work. [D1–D4; CHAT-01–09]

### 24.3 What was done for this delivery

This pass read the relevant supplied forecasting and corrected high-value documents, the comparative review, and the opening/status lineage of the later unified candidate; organized the full available chat discussion; created one new Markdown compilation; and checked the resulting document's structure and coverage.

No fresh web research, all-branch scan, application test, model training, repository modification, VM deployment, broker transaction, source purchase, tracker status mutation or independent approval was performed. The historical evidence remains historical and source-scoped. The source packs and parent documents remain unchanged.

---

<a id="appendix-a"></a>
## Appendix A. Coverage map: where every discussion workstream is retained

| Chat workstream | Consolidated sections | Principal retained outcome |
|---|---|---|
| Kronos architecture, recent evaluations and best use | 09, 10, 19 | Challenger role, sample retention, normalization/provenance, realistic evaluation. |
| ForgeMesh field guide | 09.4 | Educational kit and surrounding-system ideas; no unseen implementation/profit assumption or purchase. |
| Open-source forecasting and LightGBM explanation | 05–08, 10 | Task-specific tabular baseline, Qlib integration and complementary temporal models. |
| Freqtrade audit | 04, 07, 15, 20 | Bias diagnostics, lifecycle/expiry, protections, execution realism and no second bot. |
| NeuralForecast high-value adoption | 08, 10 | Full required plugins, exogenous semantics, distributions/scenarios and safe artifacts. |
| Original forecast blueprint and prediction-market integration | 02–03, 05–11, 18–23 | Preserve the complete engineering scope and authority boundaries. |
| Kalshi deep research | 11, 19–20 | Exact event contracts, calibrated asset response, full replay and research labs. |
| Hosting / no new licence instruction | 02, 11.1, 21, 24 | Netcup/Oracle, no procurement, precise source/authority separation. |
| High-Value blueprint and all-branch comparison | 02, 04, 12, 23 | Corrected scope, grade namespace, source preservation and genuine domain additions. |
| Rev1.12 integration and later Rev1.13 reference | 02, 04, 22–24 | One candidate lineage and global backend-first gate; no implementation claims. |
| Profitable systems comparable to VATI | 13, 19 | Strategy-family evidence versus inspectable software versus audited live profit. |
| Broader autonomous-bot execution research | 13–15 | Donor roles, parent/child work, cancel/replace, inventory and target execution. |
| Symbiotic deterministic execution question | 03, 14–15, 18 | One risk/router authority and recoverable adaptive order lifecycle. |
| Feedback influence on future trades | 16, 18–20 | Existing defensive adaptation plus separate positive-improvement lifecycle. |
| Current wiring and Jev latency/quality | 04, 16–17 | Source-level status, synchronous cognition concern and measured comparison. |
| Final adaptivity review | 04, 15–17 | Missing execution-policy evidence update and incomplete candidate-to-live loop. |
| Acceptance, scope and operations | 19–24 | Full positive/negative/recovery proof and truthful states. |

---

<a id="appendix-b"></a>
## Appendix B. Conversation provenance

The following labels refer to the actual discussion segments in this chat. They preserve traceability without treating earlier assistant explanations as independent external verification.

| Label | User question / segment | Evidence use |
|---|---|---|
| CHAT-01 | TikTok/Kronos identification, deeper Kronos research and ForgeMesh field-guide discussion | Carries forward architectural descriptions, evaluation limitations and challenger recommendations. The exact video's full audio was not established as retrieved. |
| CHAT-02 | Proven open-source trade forecasting tools; “What is light gbm” | Carries forward Qlib/LightGBM baseline, volatility baselines and other challengers. |
| CHAT-03 | “Audit van against freqtrade” | Prior source comparisons and diagnosis of research/lifecycle/simulation gaps. |
| CHAT-04 | NeuralForecast adoption and the first combined forecast blueprint | Capability and target-specific integration recommendations, later preserved as mandatory scope. |
| CHAT-05 | Kalshi research, high-value review, profitable-system question and broader autonomous-bot execution research | Event/crypto research and donor/strategy/execution comparisons. Financial figures remain research context, not VAN evidence. |
| CHAT-06 | “Can these recommendations and improvements be integrated coherently...” | Proposed VATI Symbiotic Execution Fabric, parent/child authority, portfolio targets and determinism. |
| CHAT-07 | “How does the feedback loop affect or influence future trades?” | Practical feedback attribution, two-speed adaptation and positive-evidence limits. |
| CHAT-08 | “Is all this wired in the current setup? Does jev...” | Prior source wiring review, no proven Jev benefit, synchronous cognition dependency and timing comparison. |
| CHAT-09 | “Is the vati system adaptive...” | Latest source-level adaptivity findings, policy `observe()` gap and incomplete evolution integration. |

When source or timing uncertainty was acknowledged in those segments, this compilation retains it. It does not independently re-establish prior external return statistics, current legal terms, provider uptime or live account status.

---

<a id="appendix-c"></a>
## Appendix C. Document sources and preserved identities

| Source ID | Source | How it was used |
|---|---|---|
| D1 | `VAN_FORECAST_ADOPTION_BLUEPRINT_REV1_1_20261017.md` | Detailed forecasting, model, event, validation and operating specification; read for this compilation. Source ID `file_00000000acfc82089b7d1a7b6ec0779e`. |
| D2 | `VAN_HIGH_VALUE_TRADING_ADOPTIONS_BLUEPRINT_REV1_1_20261017.md` | Corrected integrated high-value/crypto/evidence companion; read for this compilation. Source ID `file_0000000096348208b6cfeb6a09fed449`. |
| D3 | `VAN_HIGH_VALUE_ADOPTIONS_COMPARATIVE_REVIEW_REV1_20261017.html` | All-branch review scope, R01–R12 corrections, function owners and paper probes; read for this compilation. Source ID `file_000000001eb88208806156973fa2e9cc`. |
| D4 | `VAN_NEXT_UNIFIED_REBUILD_BLUEPRINT_REV1_13_20261017.md` | Opening scope/status, source pins and preserved corrective/authority lineage only; retrieved from Library, not a full fresh review. Source ID `file_00000000aac08208a8c9249ceed5d107`. |
| D5 | `VAN_NEXT_UNIFIED_REBUILD_BLUEPRINT_REV1_12_20261017.md` | Delivered parent lineage preserved; no full fresh semantic review claimed. Source ID `file_000000002e148208b95753efc54461ff`. |
| D6 | `VAN_NEXT_DETERMINISTIC_PLAN_REV1_12.md` | Preserved executable-plan lineage referenced by the conversation; not rewritten or rescheduled here. Source ID `file_0000000030e48208bebd63cee1a350d5`. |
| D7 | `VAN_HIGH_VALUE_TRADING_ADOPTIONS_BLUEPRINT_REV1_2026-10-17.md` | Original upload, provided in chat context; historical scope whose conflicts were explicitly corrected by D2/D3. Source ID `file_00000000ccd88208af27e5dc86302ad3`. |

### Source fingerprint manifest

The following hashes were computed from the exact mounted source files during document assembly. A matching hash establishes file identity only, not independent correctness, implementation or authority. D4 was read through the Library interface; no container fingerprint is asserted for it.

| Source | Exact file / byte identity |
|---|---|
| D1 | `VAN_FORECAST_ADOPTION_BLUEPRINT_REV1_1_20261017.md`<br>Bytes: 136,237<br>SHA-256: `544e77a2bc46317ff319c86da646b1c7c937b9c88ee7328b9cafef2f72cff750` |
| D2 | `VAN_HIGH_VALUE_TRADING_ADOPTIONS_BLUEPRINT_REV1_1_20261017.md`<br>Bytes: 78,548<br>SHA-256: `a084c4e744852a82bcadf6ecfbcc065105d647f8393dbf141eafb91d22c5d613` |
| D3 | `VAN_HIGH_VALUE_ADOPTIONS_COMPARATIVE_REVIEW_REV1_20261017.html`<br>Bytes: 32,108<br>SHA-256: `146199b2e44e8b34d52243509cf4a09c283d370439fef9edcfc9108d9ab8c0bd` |
| D5 | `VAN_NEXT_UNIFIED_REBUILD_BLUEPRINT_REV1_12_20261017.md`<br>Bytes: 404,678<br>SHA-256: `2cd2ccaa821cf8d2f561d50d272e62934140fc7dc33273deda97984cd95f4387` |
| D6 | `VAN_NEXT_DETERMINISTIC_PLAN_REV1_12.md`<br>Bytes: 422,276<br>SHA-256: `8fe7fb677860cf8a60cbc368cc37d731b752bea74938f4e9c888cb66f079b3c9` |
| D7 | `VAN_HIGH_VALUE_TRADING_ADOPTIONS_BLUEPRINT_REV1_2026-10-17.md`<br>Bytes: 49,430<br>SHA-256: `50514e34a7fee24c329aa27fffe0e199f2d7d76ec3b6f9ac496f5fbc91c8d12d` |
| Forecast pack Rev1.1 | `VAN_FORECAST_ADOPTION_BLUEPRINT_PACK_REV1_1_20261017.zip`<br>Bytes: 449,989<br>SHA-256: `dbacf6b24f0e2df572a5e1208748921a59bab60780694570bf84aaadb0a8c849` |
| Review pack | `VAN_HIGH_VALUE_ADOPTIONS_REVIEW_PACK_REV1_20261017.zip`<br>Bytes: 31,987<br>SHA-256: `04789cac604de8c0225a04175eb0eba47722a2291e661ce2566f014b74dc4a06` |
| Unified pack Rev1.12 | `VAN_NEXT_UNIFIED_REBUILD_BLUEPRINT_PACK_REV1_12_20261017.zip`<br>Bytes: 13,379,355<br>SHA-256: `d898f2a46904a558fa45658543fc142069739e72498ac0ad58ec851529747a99` |

The existing ZIP packs retain the full original schemas, application-test contracts, generators and crosswalks. This Markdown is a consolidated reading and implementation-reference document, not an edited replacement for those packs.

---

<a id="appendix-d"></a>
## Appendix D. Immutable code references from prior inspection

These links identify code previously read in this conversation. They were **not fetched again for this compilation**. Their hashes are intentionally pinned so a later branch change does not silently change the cited source. Any implementation must reconcile the actual current admitted source before editing.

| Reference | Pinned source | Relevant behavior |
|---|---|---|
| CODE-01 | [`trading/vati/execution/router.py`](https://github.com/Vanguduza/Van/blob/a39f241b0135cf92cc5a6b9a28af226aa294603d/trading/vati/execution/router.py)<br>`a39f241b0135` | Single submission boundary, slices refusal and stop-failure close handling. |
| CODE-02 | [`trading/vati/execution/base.py`](https://github.com/Vanguduza/Van/blob/a39f241b0135cf92cc5a6b9a28af226aa294603d/trading/vati/execution/base.py)<br>`a39f241b0135` | OrderCommand, ExecutionReceipt and common VenueAdapter contract. |
| CODE-03 | [`trading/vati/execution/paper.py`](https://github.com/Vanguduza/Van/blob/a39f241b0135cf92cc5a6b9a28af226aa294603d/trading/vati/execution/paper.py)<br>`a39f241b0135` | Immediate/resting order matching and expiry counterexamples. |
| CODE-04 | [`trading/vati/backtest/engine.py`](https://github.com/Vanguduza/Van/blob/a39f241b0135cf92cc5a6b9a28af226aa294603d/trading/vati/backtest/engine.py)<br>`a39f241b0135` | Single-instrument replay, intrabar path and terminal-equity ordering. |
| CODE-05 | [`trading/vati/execution/policy.py`](https://github.com/Vanguduza/Van/blob/8eb1889822fc8a83f219977c15340172e16acd91/trading/vati/execution/policy.py)<br>`8eb1889822fc` | Execution evidence map, observe() and select() behavior. |
| CODE-06 | [`trading/vati/app/cycle.py`](https://github.com/Vanguduza/Van/blob/8eb1889822fc8a83f219977c15340172e16acd91/trading/vati/app/cycle.py)<br>`8eb1889822fc` | Policy selection, TCA and close-to-learning consumers. |
| CODE-07 | [`trading/vati/app/account_service.py`](https://github.com/Vanguduza/Van/blob/8eb1889822fc8a83f219977c15340172e16acd91/trading/vati/app/account_service.py)<br>`8eb1889822fc` | Account coordinator integration, empty liquidity view and synchronous cognition wake. |
| CODE-08 | [`trading/vati/app/trade_lifecycle.py`](https://github.com/Vanguduza/Van/blob/8eb1889822fc8a83f219977c15340172e16acd91/trading/vati/app/trade_lifecycle.py)<br>`8eb1889822fc` | Entry/close learning, active adjustments and account lifecycle. |
| CODE-09 | [`trading/vati/learning/hooks.py`](https://github.com/Vanguduza/Van/blob/8eb1889822fc8a83f219977c15340172e16acd91/trading/vati/learning/hooks.py)<br>`8eb1889822fc` | on_tca / on_review and permitted feedback outputs. |
| CODE-10 | [`trading/vati/learning/broker.py`](https://github.com/Vanguduza/Van/blob/8eb1889822fc8a83f219977c15340172e16acd91/trading/vati/learning/broker.py)<br>`8eb1889822fc` | Broker evidence and liquidity/eligibility response. |
| CODE-11 | [`trading/vati/learning/health.py`](https://github.com/Vanguduza/Van/blob/8eb1889822fc8a83f219977c15340172e16acd91/trading/vati/learning/health.py)<br>`8eb1889822fc` | Outcome-based strategy health and demotion recommendations. |
| CODE-12 | [`trading/vati/learning/boundary.py`](https://github.com/Vanguduza/Van/blob/8eb1889822fc8a83f219977c15340172e16acd91/trading/vati/learning/boundary.py)<br>`8eb1889822fc` | Allowed feedback targets and prohibited direct policy/authority changes. |
| CODE-13 | [`trading/vati/learning/replay.py`](https://github.com/Vanguduza/Van/blob/8eb1889822fc8a83f219977c15340172e16acd91/trading/vati/learning/replay.py)<br>`8eb1889822fc` | Reconstruction from original environment-bound evidence. |
| CODE-14 | [`trading/vati/learning/evolution.py`](https://github.com/Vanguduza/Van/blob/8eb1889822fc8a83f219977c15340172e16acd91/trading/vati/learning/evolution.py)<br>`8eb1889822fc` | Failure clusters and RESEARCH strategy-candidate helper. |
| CODE-15 | [`trading/vati/learning/exit_research.py`](https://github.com/Vanguduza/Van/blob/8eb1889822fc8a83f219977c15340172e16acd91/trading/vati/learning/exit_research.py)<br>`8eb1889822fc` | Candidate exit-policy comparisons, not live mutation. |
| CODE-16 | [`trading/vati/research/workflow.py`](https://github.com/Vanguduza/Van/blob/8eb1889822fc8a83f219977c15340172e16acd91/trading/vati/research/workflow.py)<br>`8eb1889822fc` | Reachable bounded research operations and CLI-facing run_spec. |
| CODE-17 | [`trading/vati/execution/style_selector.py`](https://github.com/Vanguduza/Van/blob/a39f241b0135cf92cc5a6b9a28af226aa294603d/trading/vati/execution/style_selector.py)<br>`a39f241b0135` | Bounded style and slice selection. |
| CODE-18 | [`trading/vati/arbiter/portfolio_allocator.py`](https://github.com/Vanguduza/Van/blob/8eb1889822fc8a83f219977c15340172e16acd91/trading/vati/arbiter/portfolio_allocator.py)<br>`8eb1889822fc` | Existing V0 and V1 ranking without uncalibrated confidence. |
| CODE-19 | [`backend/van_gateway/jev/advisor.py`](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/backend/van_gateway/jev/advisor.py)<br>`dfc1557ab99a` | Shared Jev consumer, registered modules, request configuration and no trade authority. |
| CODE-20 | [`trading/vati/learning/evidence.py`](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/trading/vati/learning/evidence.py)<br>`dfc1557ab99a` | Typed, source-allowlisted ledger evidence resolution. |
| CODE-21 | [`trading/vati/cognition/runtime.py`](https://github.com/Vanguduza/Van/blob/8eb1889822fc8a83f219977c15340172e16acd91/trading/vati/cognition/runtime.py)<br>`8eb1889822fc` | Shadow cognition and configured invoker behavior. |
| CODE-22 | [`trading/vati/cognition/invokers.py`](https://github.com/Vanguduza/Van/blob/8eb1889822fc8a83f219977c15340172e16acd91/trading/vati/cognition/invokers.py)<br>`8eb1889822fc` | Invoker configuration and bounded provider interface. |
| CODE-23 | [`trading/vati/cognition/shadow_book.py`](https://github.com/Vanguduza/Van/blob/8eb1889822fc8a83f219977c15340172e16acd91/trading/vati/cognition/shadow_book.py)<br>`8eb1889822fc` | Same-trade size-only shadow attribution. |
| CODE-24 | [`trading/vati/cognition/performance_ledger.py`](https://github.com/Vanguduza/Van/blob/8eb1889822fc8a83f219977c15340172e16acd91/trading/vati/cognition/performance_ledger.py)<br>`8eb1889822fc` | Cognitive contribution/calibration records with separate promotion. |
| CODE-25 | [`trading/vati/risk/conformal.py`](https://github.com/Vanguduza/Van/blob/8eb1889822fc8a83f219977c15340172e16acd91/trading/vati/risk/conformal.py)<br>`8eb1889822fc` | Existing calibration owner to extend. |
| CODE-26 | [`trading/vati/validation/policy.py`](https://github.com/Vanguduza/Van/blob/8eb1889822fc8a83f219977c15340172e16acd91/trading/vati/validation/policy.py)<br>`8eb1889822fc` | Canonical validation thresholds and their units. |
| CODE-27 | [`trading/architecture/stack_lock.json`](https://github.com/Vanguduza/Van/blob/8eb1889822fc8a83f219977c15340172e16acd91/trading/architecture/stack_lock.json)<br>`8eb1889822fc` | Selected component ownership and recorded adoption states. |

Prior PR context: [PR #101](https://github.com/Vanguduza/Van/pull/101), [PR #92](https://github.com/Vanguduza/Van/pull/92), [PR #77](https://github.com/Vanguduza/Van/pull/77). Their prior open/unmerged states are historical observations, not newly refreshed metadata.

---

<a id="appendix-e"></a>
## Appendix E. External research and donor pointers carried forward

These are navigational references already discussed in the chat or source documents. They were not newly researched for this compilation. Before selecting dependency versions or using a live provider, verify the exact current interface, source-use scope and compatibility at implementation.

| Topic | Carried-forward reference | Intended use |
|---|---|---|
| Kronos | [Official repository](https://github.com/shiyu-coder/Kronos); [original paper](https://arxiv.org/abs/2508.02739) | Architecture, artifacts and reproducible challenger studies. |
| Kronos independent evaluation | [kronos-market-eval](https://github.com/sumit-ai-ml/kronos-market-eval); [kronos-gauntlet](https://github.com/thotbreakerr/kronos-gauntlet) | Methodological references; do not assume their reported results transfer to VAN. |
| ForgeMesh | [Field guide](https://forgemesh.io/kronos/field-guide) | Publicly available specification concepts, not an inspected purchased implementation. |
| Qlib | [Microsoft Qlib](https://github.com/microsoft/qlib) | Data/model/research interfaces; not live account authority. |
| LightGBM | [Microsoft LightGBM](https://github.com/microsoft/LightGBM); [documentation](https://lightgbm.readthedocs.io/) | Native objectives, deterministic environment choices and artifact formats. |
| Freqtrade/FreqAI | [Repository](https://github.com/freqtrade/freqtrade); [lookahead analysis](https://www.freqtrade.io/en/stable/lookahead-analysis/); [recursive analysis](https://www.freqtrade.io/en/stable/recursive-analysis/) | Native VAN diagnostics and operating patterns. |
| NeuralForecast | [Repository](https://github.com/Nixtla/neuralforecast); [documentation](https://nixtlaverse.nixtla.io/neuralforecast/index.html) | Model-specific inputs, losses, cross-validation and safe persistence. |
| Chronos | [Amazon Chronos forecasting](https://github.com/amazon-science/chronos-forecasting) | Additional pretrained challenger, not assumed alpha. |
| Volatility baselines | [ARCH package](https://github.com/bashtage/arch) | Strong task-specific statistical comparators. |
| Kalshi source interface | [Market-data quick start](https://docs.kalshi.com/getting_started/quick_start_market_data); [order-book responses](https://docs.kalshi.com/getting_started/orderbook_responses); [historical data](https://docs.kalshi.com/getting_started/historical_data) | Exact source adaptation and versioned book/history semantics. |
| Kalshi source/access documents | [Developer agreement](https://assets.kalshi.com/Kalshi-Developer-Agreement.pdf); [member agreement](https://kalshi.com/docs/kalshi-member-agreement.pdf) | Source profiles; no new procurement or legal finding is issued here. |
| Polymarket settlement | [Market resolution](https://docs.polymarket.com/polymarket-learn/markets/how-are-markets-resolved) | Contract equivalence, exceptional rules and settlement-state research. |
| Event-to-asset research | [Cryptocurrency volatility preprint](https://arxiv.org/html/2604.01431v1); [Federal Reserve macro-market paper](https://www.federalreserve.gov/econres/feds/files/2026010pap.pdf) | Motivation for replication, not proof of VAN profitability. |
| Event-market arbitrage | [AFT study](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.AFT.2025.27) | Payoff consistency and execution-sensitive research. |
| Risk-constrained growth | [Risk-constrained Kelly paper](https://arxiv.org/abs/1603.06183) | Assumption-bound research comparator, never a default sizing grant. |
| Systematic trading implementation | [pysystemtrade](https://github.com/pst-group/pysystemtrade) | Forecast combination, target positions and order-stack behavior. |
| Execution workers | [Hummingbot](https://github.com/hummingbot/hummingbot); [Strategy V2](https://hummingbot.org/strategies/v2-strategies/) | Bounded executor lifecycle patterns. |
| Independent execution/reproduction | [QuantConnect LEAN](https://github.com/QuantConnect/Lean) | Portfolio-target execution and separate reproduction. |
| Existing kernel reference | [NautilusTrader](https://github.com/nautechsystems/nautilus_trader) | Order/fill lifecycle, recovery and event-based execution mechanics. |
| Jev | [TypeSafe Jev SDK](https://github.com/jev-ai/typesafe-ai-jev) | Typed judgments; not evidence of profitable decisions. |
| CEX–DEX execution research | [AFT empirical study](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.AFT.2025.26) | Costs, execution competition and failed-leg research. |

External statistics and promotional performance claims were deliberately not reproduced as current financial facts. The relevant recommendation is to adopt testable mechanics and evidence standards, not to copy headline returns.

---

<a id="appendix-f"></a>
## Appendix F. Final integration checklist

Before representing this programme as implemented, the responsible delivery process should be able to demonstrate all of the following within the existing scope:

1. A single current source/plan authority with compatible branch work preserved.
2. Correct economic simulation, costs, timing, limits, account equity and reservations.
3. Durable, capability-aware order lifecycle with truthful unknown/partial/cancel/flat states.
4. Actual policy-observation producers feeding the existing selector and replayable later effects.
5. Complete point-in-time datasets, Qlib/LightGBM and all mandatory NeuralForecast integrations.
6. Separate raw scores, calibrated probabilities, quantiles, paths and financial authority.
7. A usable train→artifact→serve→evaluate→candidate-review→admit/reject/revoke→recover lifecycle.
8. Full prediction-market and read-only crypto research obligations without another trading desk.
9. Jev outside the critical path, with measured latency/quality/value for its exact admitted use.
10. Strong baselines, full cohorts, independent account-policy comparisons and prospective evidence.
11. Existing RiskAuthority, ExecutionRouter, protection, owner controls and mandate boundaries preserved.
12. Actual full backend and independent verification before the sole BG-001 opens new native UI.
13. Product/device/release evidence and separate model/strategy/account live authorization.
14. Honest reporting when no candidate is economically qualified or an external integration remains unverified.

**Final consolidated assessment:** VATI has a real source-level foundation for deterministic trading, defensive feedback and research. The most valuable next work is not another AI trading bot. It is completing the connections between observed economics, governed execution, validated strategy/model evolution and the next eligible decision—while preserving the complete agreed software scope and proving the results rather than assuming them.