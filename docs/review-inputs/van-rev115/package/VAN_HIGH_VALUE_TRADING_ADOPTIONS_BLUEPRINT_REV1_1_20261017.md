# VAN — High-Value Trading Intelligence Adoptions
## Additive, Repository-Aligned Engineering Blueprint — Revision 1.1 — corrected integrated companion

**Date:** 2026-10-17  
**Status:** **OWNER-DIRECTED SCOPE INTEGRATION / INDEPENDENT SEMANTIC ADMISSION PENDING / NOT IMPLEMENTED, NOT DEPLOYED**  
**Product:** VAN Adaptive Trading Intelligence (VATI)  
**Primary purpose:** Adopt objectively useful capabilities from the @savipww Grok Bot + Jev design and from systematic/profitable trading practice **without importing its unverified results, replacing existing VAN architecture, or weakening established safety invariants**.  
**Change type:** Additive. This revision integrates the reviewed requirements into the delivered Unified Rev1.12 specification. It does not itself authorize repository merges, owner-signatures, strategy promotions, venue onboarding or live orders.

> **Decision in one sentence:** Prioritize execution-realistic economics, empirically calibrated quantitative forecasts, verifiable data and controlled experiment design across VAN; add wallet/contract intelligence as an isolated read-only crypto research capability; treat Jev-like subjective judgments and prediction-market signals as challengers until they demonstrate **incremental net value**.

> **Operative integration rule:** this is a corrected, source-derived companion to `VAN_NEXT_UNIFIED_REBUILD_BLUEPRINT_REV1_12_20261017.md`. The only active requirements and schedule are the Unified Rev1.12 machine registries. Section 30 of that master and `contracts/HIGH_VALUE_INTEGRATION_CONTRACTS.md` resolve inherited illustrative schema and staging ambiguity. Existing forecast scope cannot be reduced, observed facts must be split from modeled economics, and all new frontend stays after BG-001. The original Rev1.0 text is retained unchanged in lineage.

---

## 0. Scope, provenance and authority

### 0.1 Evidence inspected

This plan is based on (a) the creator's original published September setup/code, (b) a source-level audit dated 2026-10-17, (c) independently examined systematic-trading literature, vendor docs and reporting, and (d) the **accessible `Vanguduza/Van` default branch** on 2026-10-17. The repository inspection sampled specific documents/files and code search; **absence of a matching search result is not proof of absence across every branch or runtime**. Before implementation, reconcile main, open PRs, active feature branches and deployment receipts.

**Authoritative VAN references (existing; must not be superseded by this proposal):**

- [VAN Trading System — Rev 4](https://github.com/Vanguduza/Van/blob/main/docs/VAN_TRADING_SYSTEM_BLUEPRINT_REV4_CONSOLIDATED.md): strategy capsules, Risk Authority, sealed intents, learning and trading doctrine.
- [Trading Production Deployment — Rev 5](https://github.com/Vanguduza/Van/blob/main/docs/VAN_TRADING_PRODUCTION_DEPLOYMENT_BLUEPRINT_REV5.md): runtime, venue adapters, Trading Command Center and controlled live-readiness.
- [Trading Intelligence & Profitability Improvement — Rev 1.1](https://github.com/Vanguduza/Van/blob/main/docs/VAN_TRADING_INTELLIGENCE_AND_PROFITABILITY_IMPROVEMENT_BLUEPRINT_REV_1_1.md): derived implementation plan, portfolio allocator, feature contracts and qualification doctrine.
- [VATI stack lock](https://github.com/Vanguduza/Van/blob/main/trading/architecture/stack_lock.json): `revision: 5.2.0` in inspected file; one production trading kernel, one live order sender and one transactional authority store. Verify current revision at execution.
- [VATI deterministic Risk Authority](https://github.com/Vanguduza/Van/blob/main/trading/vati/risk/authority.py); [portfolio allocator](https://github.com/Vanguduza/Van/blob/main/trading/vati/arbiter/portfolio_allocator.py); [backtest engine](https://github.com/Vanguduza/Van/blob/main/trading/vati/backtest/engine.py); [sealed cognitive shadow book](https://github.com/Vanguduza/Van/blob/main/trading/vati/cognition/shadow_book.py); [cognitive performance ledger](https://github.com/Vanguduza/Van/blob/main/trading/vati/cognition/performance_ledger.py).
- Creator code: [Jev/Grok Bot article](https://x.com/i/article/2102720919185617314), [accessible article text](https://threadnavigator.com/thread/2102720919185617314/), [earlier Grok Bot article](https://x.com/i/article/2095171104004575708). Researcher's independently reconstructed implementation: [Walid Riachy audit](https://www.walidriachy.com/lab/jev-grok-memecoin-desk).
- Local evidence input: `SAVIPWW_CODE_AUDIT_2026-10-17.md` (separate research artifact; do not confuse its reproductions with a live audit of the creator's private deployment).

**Research-source categories (RS, never implementation E grades):** `RS1` filed/primary/transactionally verifiable; `RS2` published peer-reviewed or independently repeatable technical results; `RS3` vendor-verified capability, not profit; `RS4` self-reported trading results; `RS5` unverified creator/video performance. Profitable organizations demonstrate *systems*, not that any individual feature caused their returns.

### 0.2 Non-negotiable architectural alignment

VAN already separates opportunity generation, allocation, sizing, execution and reconciliation. Preserve the following exactly:

1. **Models discover; rules validate; the allocator selects; only VATI `RiskAuthority` sizes; only the existing `ExecutionRouter` sends.** No new execution kernel or agent-owned wallet.
2. Risk intelligence is **reduce-only**: every risk multiplier is in `[0,1]`; `NO_TRADE` is a fully valid outcome. The owner alone may increase capital ceilings or approve a new live mandate.
3. Research, model training, Grok/Jev-like judgments, Hermes, n8n, Temporal, browser automation and market-news interpretation run outside the T0 tick-to-order path. The stack lock, horizon eligibility and TTL controls prevail.
4. Existing hash-chained evidence ledger, strategy capsule lifecycle, account reconciliation, kill switch, cross-account controls and promotion signatures remain the source of truth.
5. Existing FX/indices/metals/Deriv/ZSE work must not be displaced by a meme-token experiment. Any crypto capability starts **read-only**, separately feature-flagged, with no presumed custody or venue authority.
6. Existing Normal/Risky/Aggressive user modes (when reconciled with their authoritative branch) may change *selection ambition* only inside the current owner mandate and hard caps. **Aggressive must not mean skipping filters, more permissive scam checks or uncalibrated position multiplication.**
7. Research or trading hosted on Netcup/Oracle does not waive venue terms, data rights, account eligibility, export/geo rules or applicable legal obligations. Read-only public market data is the preferred starting point; provider entitlements are checked separately from server location.

### 0.3 Existing capabilities — build on them instead of cloning them

| Existing VAN asset | Observed source | Disposition |
|---|---|---|
| Deterministic sizing, drawdown/heat constraints, signed decisions | `trading/vati/risk/authority.py` | **Reuse as the only size authority** |
| Account-level opportunity competition | `trading/vati/arbiter/portfolio_allocator.py` | Extend input quality through existing contracts; no second allocator |
| Cost-aware backtesting and decision replay | `trading/vati/backtest/engine.py` | Extend where microstructure/DEX data exceed bar resolution; do not replace existing engine |
| Timestamped paired cognition decisions | `trading/vati/cognition/shadow_book.py` | Reuse for **size-only** counterfactuals; build a distinct matched-opportunity test for different entry/exit paths |
| Cognitive calibration/performance metrics | `trading/vati/cognition/performance_ledger.py` | Reuse; do not invent parallel confidence metrics |
| Current trading feature/strategy improvement programme | Profitability Rev 1.1 | Reconcile and extend; no duplicate feature hierarchy |
| Qlib listed as research-only future adoption | `trading/architecture/stack_lock.json` | Preserve adoption gate; use its research pipeline, **not** its executor |
| Freqtrade rejected as production kernel | `trading/architecture/stack_lock.json` | Reuse techniques and test ideas, not an additional live trader |

**Reconciliation note:** Rev 4/5 describe the active authorities; profitability Rev 1.1 is derived. The observed stack-lock may be ahead of older prose. At build time, generate a live code/branch/runtime matrix, resolve discrepancies and record a single implementation target before modifying code.

---

## 1. Ranked adoption portfolio

### 1.1 Recommended engineering order

| ID | Capability | Scope | Priority | Evidence strength for *value proposition* | Authority | Action |
|---|---|---|---|---|---|---|
| **VAN-A01** | Execution-realistic opportunity economics and liquidity/sellability evidence | Multi-market + crypto | **P0** | RS1/RS2 (fill costs; market microstructure) | Facts / veto only | **Implement/extend** |
| **VAN-A02** | Quantitative model research and calibrated ensembles (Qlib + LightGBM; full required NeuralForecast engineering; economic use only where justified) | Multi-market | **P0** | RS1/RS3 architecture + conditional strategy evidence | Propose/rank after qualification; no sizing | **Implement at current gates** |
| **VAN-A03** | Matched-universe, cost-aware incremental evidence evaluator | Multi-market | **P0** | First-principles auditability | Evaluation only | **Extend existing evidence** |
| **VAN-A04** | Deterministic multi-stage discovery and rejection funnel | Crypto research only initially | **P1** | RS2 risk studies; RS5 profit claim | Read-only candidate veto | **Implement admitted read-only scope** |
| **VAN-A05** | On-chain security, wallet attribution, temporal holder-flow intelligence | Crypto research only initially | **P1** | RS2 for scam detection, not alpha guarantee | Read-only candidate veto | **Implement admitted read-only scope** |
| **VAN-A06** | Calibrated typed AI judgments (Jev optional + model-agnostic adapter) | Asynchronous research / T2 | **P2** | RS3 typed API, unproven incremental P&L | Commentary/abstain/reduce; no orders | **Challenger experiment** |
| **VAN-A07** | Prediction-market probability intelligence (Kalshi/public permitted feeds) | Cross-market research | **P2** | RS3 market data; incremental edge unproven | Slow context only | **Read-only ablation** |
| **VAN-A08** | Specialist agent work routing and operator explanation | Existing Hermes/VAN | **P2** | RS3 operational separation, not alpha | Research/monitor/report | **Map onto existing agents** |

**Do not create:** a second Grok-controlled live trade desk; a FOMO private-session scraper; a new crypto trade sender; a duplicate SQLite position book; a standalone Jev trade picker with direct venue calls; an autonomous high-frequency CEX/DEX arbitrage engine on ordinary VPS infrastructure; or a guaranteed “bottom-finding” strategy based on a creator's equity curve.

### 1.2 Value/risk ranking criteria

For admission, rate each proposed module from 0–5 on: (a) addressable expected net economic value; (b) safety value and avoided tail loss; (c) observability / falsifiability; (d) reuse across VAN's markets; (e) implementation and data cost; (f) reliability and legal/provider friction. The table above is the **recommended order**, not a fabricated measured ROI. Quantify actual ranking after data-cost sampling.

---

## 2. VAN-A01 — Executable economics and sellability intelligence (P0)

**Why:** The video emphasizes finding promising tokens but under-specifies whether positions can be entered/exited at the displayed prices. Systematic fund returns, measured arbitrage and the known weakness of new-token markets support treating *execution economics* as first-order intelligence.

**Implement as an extension of existing:** `vati.market_data.costs`, existing TCA/broker-execution profile, `SymbolContract.round_trip_cost_pct`, `OpportunityEngine`, `RiskAuthority`, `ExecutionRouter` and evidence events. No new order authority.

**New facts to compute (as instrument/venue permits):**

- Timestamped bid/ask; spread distribution by session; executable depth/volume ladder at requested notional; quote freshness and provider identity.
- Fee schedule for both legs; expected slippage and impact by size, horizon and regime; exchange rejects/partial fills and stop-placement constraints.
- For DEX only: authenticated *read-only* route quote at several sizes; price impact, gas, sell-transfer fees, pool liquidity quality, router allowance requirements, transaction finality and MEV/sandwich exposure. A buy quote **does not** establish that a sell is permitted or economically viable; simulate both where supported.
- For multi-venue comparison: time-normalize bid/ask, FX conversion, settlement/funding and execution availability. The same displayed market cap does not equate to executable exit value.

**Candidate economics:** for proposed quantity `q`, evaluate after-fee net edge from *the same tradeable instrument and venue path*:

```
NetEV(q,h) = E[executable_exit_proceeds(q,h) | information_as_of_t]
           - executable_entry_cash_cost(q,t)
           - expected_exit_fees_gas_financing(q,h)
           - execution_failure_cost(q,h)

Admit only if:  risk policy passes
                AND route is authorized/verified
                AND NetEV exceeds the strategy's predeclared cost-and-uncertainty floor
```

Do not double-count spread/impact if already incorporated into cash proceeds. All quantities must have explicit units, currency, timestamps, direction and fee inclusion flags.

**Integrated contracts (proposed application schemas, not implemented services):** `ExecutableQuoteFacts` records observed route/quantity/cash/fee conventions; `ExecutionEconomicsForecast` separately binds projected proceeds, fill probability and incremental costs to target/model/calibration lineage; `NetEdgeAssessment` links both and checks units and no double-counting. Exact schemas live in `contracts/high_value/`. Unknown sellability or no current quote remains typed unknown; this additive has no crypto execution permission.

**Acceptance:** calibration between expected and realized cost on demo; no false “free liquidity”; 100% rejects on stale/missing required quotes; inject gap, reject, partial fill, changed fees and a 2× cost stress; measure net-R and margin of safety out of sample. Publish all cost curves and failures to the existing evidence ledger.

---

## 3. VAN-A02 — Quant research, forecasts and calibrated model ensembles (P0)

**Why:** Systematic quantitative funds demonstrate that measured rules and ensembles *can* be part of profitable systems. This is **not** a claim that LightGBM, Qlib, NeuralForecast or Jev guarantees alpha.

**Division of labor (no overlapping engine ownership):**

| Tool/component | Precise responsibility | Not permitted |
|---|---|---|
| **Microsoft Qlib** | Research datasets, experiment tracking, feature/alpha research and walk-forward model comparison | Qlib execution engine or authority to change VAN mandates |
| **LightGBM** | Baseline non-linear tabular classifier/regressor or pairwise ranker, probability/calibration challenger | Using uncalibrated scores as position-size multiplier |
| **Nixtla NeuralForecast** | Challengers for return/volatility/liquidity forecasting when sequential dependence justifies added complexity | Automatic adoption over a simpler seasonal/statistical baseline |
| **VAN deterministic strategies / meta-labeller** | Generate candidates under sealed capsule rules; consume model outputs with bounded TTL and provenance | Guess values where a required feature is missing |
| **Existing VAN portfolio allocator** | Choose among admissible candidates; qualified model-weighted ranking only after a separately reviewed policy version; existing AllocatorV1 remains confidence-free | Approve lot size or reserve portfolio capital |
| **Existing VAN Risk Authority** | Only sizing and hard ceiling/veto authority | None of the above delegates its authority |

**Model candidates (must be tested, not assumed profitable):**

1. `P(net_return_after_cost > 0 over horizon h)` as meta-label of a strategy trigger, using point-in-time labels and actual executable-cost model.
2. Expected net `R` (risk unit) conditional on regime and horizon.
3. 5% downside quantile / adverse-excursion model, only as a **reduce/veto** feature.
4. Execution/slippage quantile and fill probability, especially across brokers/sessions.
5. For qualifying liquid markets: realized volatility and forecast intervals from NeuralForecast, compared against naive/EMA/AR baselines.

**Training contract:** UTC event times; training/feature timestamps; point-in-time macro vintages; venue/instrument ID; fee assumptions; train/validation/test ranges; embargo length at least overlapping label horizon; purged walk-forward CV; trial ledger for multiple testing; group/time split to avoid near-identical asset leakage; delayed outcome attachment. Model artifacts carry immutable `model_hash`, `feature_schema_hash`, `training_data_manifest`, `horizon`, `calibration_id` and `expires_at`.

**Do not imply label equivalence:** a binary profitable-trade label differs from a raw future-price-movement label and from Jev answer confidence. Meta-label calibration is only valid for its precise label/outcome distribution.

**Evaluation:** tabular no-ML baseline → LightGBM → NeuralForecast → any ensemble. Freeze the exact discovery universe and decision opportunities; test net expectancy, drawdown, Brier/ECE, adverse selection, expected calibration error by regime, inference latency, training cost, and portfolio-level incremental return. Each extra component requires a separately measured lift. Use Qlib only at the research gate in the existing stack lock and pin versions after compatibility tests.

**Integration suggestion:** New research subpackages under `trading/vati/research/{datasets,experiments,models,calibration}/` **only if absent** after branch reconciliation; production consumes sealed, schema-checked `ForecastSignal`s through the existing feature/capsule pipeline. Do not modify Nautilus/venue execution to adopt research libraries.

---

## 4. VAN-A03 — Evidence-first ablation and causal contribution (P0)

**Why:** Existing VAN cognitive shadow-book comparisons are designed for **size-only changes on the same trade**. They cannot accurately score a new crawler or a token selector that changes *which trades happen*, their entry times or exit liquidity. That requires a separate matched-opportunity evaluator rather than repurposing `ShadowEntry.shadow_r`.

**Baseline/counterfactual matrix:**

| Experiment | Control | Challenger | Primary outcome |
|---|---|---|---|
| EX-01 | VATI existing strategy | + cost/liquidity intelligence | Realized net-R, tail-loss and missed fills |
| EX-02 | VATI existing strategy | + LightGBM calibrated meta-label | Paired net-R, drawdown, incremental net EV |
| EX-03 | EX-02 | + NeuralForecast conditional feature | Incremental lift net of compute/data costs |
| EX-04 | Identical discovered crypto cohort | + deterministic safety screens | Avoided scam loss **minus** missed legitimate winners |
| EX-05 | EX-04 | + wallet/time-series intelligence | Incremental classification quality and net-R |
| EX-06 | Without Jev | + typed Jev judgment | Paired changes in candidate accept/reject and realized net-R |
| EX-07 | Without prediction-market context | + Kalshi-derived public probability feature | Drift-aware net-R/calibration improvement |

**Anti-bias implementation:**

- Register each hypothesis, split, threshold and trial ID before evaluation; seal all observations **at decision time**. No hindsight re-ranking.
- For all discovered opportunities, record decisions for both arms; apply the same future market path through comparable independently specified fill simulators. One arm's hypothetical trade is not a realized fill: label results `SIMULATED_COUNTERFACTUAL` until a valid forward paper/live counterpart exists.
- Include rejected tokens, delisted assets, failed routes, disappearing pools and unavailable data in the cohort. Surviving-only analysis is disallowed.
- Use paired-bootstrap confidence intervals, cost stress, walk-forward windows and appropriately adjusted multiple-hypothesis statistics (VAN's DSR/PBO where applicable).
- Report **net** capital-weighted performance and strategy R, not just accuracy or count of scams flagged. Also show coverage, abstention, latency, fee spend and false rejection of profitable legitimate candidates.
- Decision evidence must link `market_state_hash`, `candidate_id`, model/version IDs, pretrade forecasts, `RiskDecision` and eventual receipts; keep account aliases and redacted data as existing policy requires.

**Promotion recommendation:** require a pre-registered, strictly positive lower 95% confidence bound for *economically material* out-of-sample incremental net value, plus no unmitigated safety regression and repeatability across regimes. This is a **proposed research standard**, not a claim of statistical certainty or an automatic live-approval mechanism. With inadequate sample/effect size, state `INCONCLUSIVE`, not `PASS`. Sizing/capital increases remain owner A4 decisions under existing canon.

---

## 5. VAN-A04 — Multi-stage crypto discovery and deterministic rejection (P1, read-only)

**Why:** The creator's useful concept is an inexpensive-to-expensive screening funnel. It reduces wasteful model calls and focuses investigations. Nothing in the published code validates “kill scam coins” as an executable trading edge.

**Canonical identity:** `asset_id = (chain_id, normalized_token_contract)`; pools identified independently by `(chain_id, pool_contract)`. Tickers/names are *display fields*, never keys. One token may have several pools; liquidity and quotes must be pool/router-specific.

**Proposed stages and data producers:**

| Stage | Operation | Example evidence | Reject/abstain behavior |
|---|---|---|---|
| D0 | Approved pool discovery (GeckoTerminal/DEX Screener/chain events where permitted) | chain, contract, pool, first-seen/launch block | Unknown identity → bench |
| D1 | Cheap numerical/freshness rules | age, validated pool liquidity, real buys/sells, caps and timestamps | Fail rule → reject with expiry |
| D2 | Contract capability checks | mint/freeze/upgrade owner, transfer tax/restrictions, honeypot test, LP status | Fatal transfer/sell restriction → reject; unknown → abstain |
| D3 | Wallet and ownership attribution | dev/insider concentration, LP/burn/pool exclusions, supply changes | Unknown attribution → quality down; no “top holder == whale” shortcut |
| D4 | Temporal flow and market structure | buyer/seller cohorts, repeat funding, wash-trade signals, short-window inflows/outflows | Reject if validated manipulation rule triggers |
| D5 | Optional social/typed judgement | verified source account and historical posts with provenance | Subjective model may veto/reduce; cannot convert failed D2 into approval |
| D6 | Opportunity evaluation | available exit route, net expected edge, strategy eligibility | No signed economic evidence ⇒ research-only |

**Queue:** event-driven discovery + bounded priority queue + provider-specific rate limiter + cached negative-result registry. Intervals are provider-dependent, not hardcoded “15 minutes” as a profitability rule. `CandidateRejected` includes `{reason_code, source_hash, first_seen, expires_at, rule_version}`; cooldown by cause with recheck on meaningful changes. Archive all discovered candidates and their state before survival filtering.

**Provider discipline:** documented, contractually permitted APIs and public chain observations only. Do not use FOMO authenticated private endpoints or automate trades through that UI. New asset research may begin with zero keys and publicly available data; production entitlements, quotas and account eligibility remain separate gates.

**Safety:** hard rules are conservative, but published @savipww values ($12k liquidity, 5% holder, etc.) **must not become VAN defaults** without empirical false-positive/false-negative tests on actual venues and assets. All unknown/ambiguous values are typed unknown, never Python truthiness of strings such as `"no"`.

**Suggested directory (proposal, verify current branches):** `trading/vati/research/crypto/{discovery,identity,screening,candidates,bench}/`, with typed adapters rather than a second trading subsystem. Feature flag `crypto_intelligence.read_only=true` is mandatory at introduction.

---

## 6. VAN-A05 — Security, temporal wallet intelligence and anti-rug graph (P1)

**Worth adopting:** contract-rule verification, wallet and token-event time series, cluster-based concentration estimates, abnormal deployer funding, pooled-wallet attribution, sudden liquidity withdrawals and actual **sellability** checks. The incremental contribution is primarily *capital preservation*, not a guaranteed ability to identify winners.

### 6.1 Chain-specific analyzers

- **Solana:** separate SPL Token from Token-2022; normalize mint/freeze authority to `YES | NO | UNKNOWN`; check authority revocation, transfer fees, transfer hooks, permanent delegates and other relevant extensions. Identify LP/pool/vault/burn addresses before computing concentrated beneficial ownership. Record slot/finality and RPC/indexer limitations.
- **EVM (Base/Ethereum/BSC where approved):** contract verified status, proxy/upgradeability and admin privileges, max transaction/transfer limits, honeypot behavior, tax/blacklist changes, owner-controlled mint/burn, LP-lock or remove-liquidity privileges and DEX router sell simulation. Unknown source code does not automatically mean fraud; it increases evidence uncertainty.
- No chain-specific assumption may silently flow to another chain. Introduce a common typed `ChainSecurityFinding` schema and discrete chain adapters.

### 6.2 Temporal graph requirements

Persist time-indexed snapshots with block/slot anchor: holder counts, transfer events, clustered funding links, deployer and related wallets, liquidity pool balances, identified buys/sells, treasury/LP/burn labels, and confidence/uncertainty per attribution. Compute **changes between observations**, not narratives inferred from one holder snapshot. Track adjusted concentration **excluding proven technical pool/burn addresses** while retaining raw total holdings for replay.

**Examples of legitimate unknown cases:** a large wallet is an AMM pool; an owner is inferred from a heuristic with weak confidence; a transfer is a router hop rather than a genuine purchase; a token has too little history to compare holder growth. Each returns a typed `UNKNOWN` or a lower-quality confidence interval, never a fabricated `SAFE` label.

**Two outputs, kept separate:**

1. `SafetyVerdict {REJECT, INVESTIGATE, NO_HARD_BLOCK}` and code-specific factual reasons. `NO_HARD_BLOCK` is **not** `SAFE_TO_BUY`.
2. `ManipulationRiskFeatures` and uncertainty for later **read-only** research, potentially consumed by LightGBM after dataset review.

**Acceptance/negative tests:** mint/freeze boolean normalization; duplicated symbols; LP mistaken for holder; migration between pools; coordinated wallets with common funding; legit OTC/airdrop falsely flagged; sell simulation reverts; transfer hook changes; source/indexer lag; chain reorganization; unsupported chain. Store test tokens, expected results and false positives under a versioned fixture set.

---

## 7. VAN-A06 — Model-agnostic typed AI judgments, Jev as optional challenger (P2)

**Do not adopt @savipww's one-token shortcut, self-certifying confidence or agent-mediated sizing.** The strongest transferable concept is a typed decision-question interface rather than an unstructured essay.

**API interface (proposed):**

```
judge(state_snapshot, typed_questions, question_set_version, deadline)
    -> AnswerSet {answers, unanswered, model_id, request_hash,
                  input_hash, elapsed_ms, estimated_cost, expires_at}
```

Use a provider-neutral adapter (`Jev`, rule baseline, or another approved inference system) so performance can be compared. Question sets should ask narrow, falsifiable questions such as whether project/account identity is supported by the supplied evidence or whether sources show conflicting market claims; not “will this coin moon?”

**Boundaries:** only independently sourced, signed/persisted evidence goes into the state; include the actual token launch timestamp when comparing social account ages, historical holder records when asking about holder growth, and an explicit `none/unknown` answer. Disallow prompt-supplied broker commands and secrets. All external social text is untrusted evidence.

**Tiers:** T2 or slower with TTL appropriate to strategy horizon. Not in T0, not for SCALP/instant token-sniping. Model output can explain, abstain, reject or *reduce* an already admissible candidate; any use in ranking requires validation and the separately reviewed allocator policy version; existing AllocatorV1 does not provide calibrated model-weighted ranking. Never an unrestricted authority to buy, increase size, cancel a protective stop or ignore hard rules.

**Validation:** Jev vs deterministic rule/no-LLM vs another challenger on the exact same sealed cases. Measure Brier/ECE for genuinely observable labels, abstention rate, false rejection, incremental net-R, latency, $/screen and data-leakage exposure. Jev `confidence` is an answer-quality signal, **not a profitable-trade probability**. If no net improvement after costs, retain as an explanation aid or disable.

**Reuse:** existing VATI cognitive shadow/performance ledger for same-trade size-only decisions; use VAN-A03 matched-opportunity evaluation when selections or entry times differ.

---

## 8. VAN-A07 — Kalshi and other public prediction-market data (P2, research only)

**Potential value:** market-implied event probabilities, changes in probability, uncertainty about macro outcomes and agreement/disagreement with VATI's existing macro/event regime state. Avoid asserting the prediction market is itself a tradeable signal or that its price is a perfectly calibrated probability.

**Initial integration:** documented public market-data endpoints, read-only; event matching to VATI's existing event matrix, calendar and instrument/horizon. No prediction-market order routing and no cross-exchange arbitrage execution. Annotate contract definition, resolution rules, trading fees, spread, liquidity, quote timestamp, event resolution date and any market-specific restrictions. `MarketOddsSnapshot` is delayed/TTL-limited T2/T3 context, not T0 venue truth.

**Experiment:** matched windows and events — existing VATI forecasting baseline vs probability-change feature vs feature plus uncertainty. Outcomes: directional/calibration improvement **and** incremental net strategy R, not just correlation to post-event prices. Remove or quarantine features with stale market probabilities, ambiguous resolution language, thin books, structural selection bias or event mismatch.

**Account policy:** Public market observation and participation eligibility are different. Server hosting geography does not authorize order execution or evade legal/account restrictions. No prediction-market venue account is required for the first research phase.

---

## 9. VAN-A08 — Agent roles and the Trading Command Center (P2)

The creator's CHIEF/SCAN/VET/SOCIAL/SIZE/FILLS/RISK presentation is useful as an **operational division of labor**, but VAN already has the safer structure: Hermes coordinates work and the deterministic trading core holds authority. Adopt role clarity, **not a swarm of competing order-sending bots**.

| Creator role | VAN equivalent / recommended change |
|---|---|
| CHIEF | Hermes planner and existing VAN Gateway orchestration; may schedule research and explain status |
| SCAN | Read-only market-data discovery jobs, with provider budgets and archived universe |
| VET | Chain security validator + existing feature/data integrity checks |
| SOCIAL | Signed source extraction and provenance; avoid social account automation for execution |
| SIZE | **Existing** VATI `RiskAuthority`, not an LLM agent |
| FILLS | **Existing** `ExecutionRouter` + venue adapter + reconciliation |
| RISK | **Existing** deterministic risk governor/kill switch; research cannot veto a mandatory exit |

**Owner UI additive:** a compact *candidate funnel* that shows total observed, rejected by reason, investigated, eligible, economically viable, paper-traded and actually filled. Each row links to a timestamped evidence snapshot, model/capsule version, quote quality and why the opportunity was rejected. Show `LIVE`, `DELAYED`, `SIMULATED`, `SHADOW` or `UNVERIFIED` labels derived from receipts, not the visual appearance of the dashboard.

Use VAN Android and gateway contracts already specified by Rev 5. No custom low-trust order buttons, simulated balance presentations or continuously open web-browser dashboards required for qualification.

---

## 10. Proposed contracts and event taxonomy

Schemas below are **illustrative proposals** to be reconciled with existing VATI serializers/events. Field names are not claims about today's repository.

```json
{
  "candidate_id": "chain:solana:contract:<address>",
  "source_event_id": "discovery:provider:record-hash",
  "chain_id": "solana-mainnet",
  "token_contract": "<verified-contract-address>",
  "pool_id": "solana-mainnet:<pool-address>",
  "first_seen_utc": "2026-10-17T12:00:00Z",
  "observed_at_utc": "2026-10-17T12:01:00Z",
  "block_or_slot": "<source-confirmed-value>",
  "data_quality": "VERIFIED|DELAYED|UNKNOWN|INVALID",
  "source_refs": ["provider:event:<id>"],
  "data_manifest_hash": "sha256:<digest>",
  "screening_version": "van-crypto-screen/0.1.0",
  "safety_verdict": "REJECT|INVESTIGATE|NO_HARD_BLOCK",
  "reason_codes": ["MINT_AUTHORITY_ACTIVE"],
  "risk_features_hash": "sha256:<digest>",
  "trade_authorized": false
}
```

**Required conceptual events:** `ASSET_DISCOVERED`, `IDENTITY_VERIFIED`, `SCREEN_REJECTED`, `SECURITY_FINDING`, `WALLET_SNAPSHOT`, `MODEL_FORECAST_RECORDED`, `JUDGMENT_ABSTAINED`, `EXPERIMENT_ARM_SEALED`, `EXECUTION_COST_QUOTED`, `COUNTERFACTUAL_RESOLVED`, `PROVIDER_DEGRADED`, `RESEARCH_CANDIDATE_PROMOTED`. Extend `vati.core.events.EventKind` only when justified; do not duplicate existing event types. All events have a canonical deterministic hash and source snapshot reference. The experiment events **never** constitute venue receipts.

**Seams (producer → durable state → consumer):**

1. Approved provider adapters → as-of market/chain snapshot lake → feature validation.
2. Deterministic screening → archived candidate/rejected-cohort table → crypto research challenger.
3. Quant research jobs → model artifact/feature manifest → sealed read-only forecast feature → existing Opportunity Engine/meta-label path.
4. Optional typed judge → bounded `JudgmentEvidence` → cognition/research evaluator (reduce-only if promoted).
5. Existing candidate → existing allocator → existing Risk Authority → existing router → broker receipt/reconciliation. **Never shortcut this chain.**
6. Every proposal includes an owner-facing projection and a linked raw evidence receipt; no “integrated” status without a real producer, production caller, consumer and negative-path proof.

---

## 11. Qualification, safety and promotion gates

### 11.1 Required staged gates

| Gate | State | Evidence needed | Allowed behavior |
|---|---|---|---|
| G0 | Architecture reconciliation | Branch/PR/runtime matrix, no duplicate authority, source and tool terms reviewed | Specification only |
| G1 | Offline implementation | Typed schemas, provider contract fixtures, fail-closed tests, stable IDs and source manifests | Local fixtures / no market execution |
| G2 | Historical replay | As-of snapshots, all-reject cohort, zero leakage, cost stress and deterministic hash replay | Backtests only |
| G3 | Forward shadow | Pre-committed arm decisions, time-stamped read-only quotes and observed outcomes | No orders from additive |
| G4 | Paper/demo integration | Existing authorized paper/demo adapters, reconciliation and crash/restart tests | Paper/demo where owner allows |
| G5 | Evidence qualification | Lower confidence bound of incremental net value > pre-registered economic materiality margin; safety metrics meet existing mandates | Eligible for owner review; **not auto-live** |
| G6 | Owner-approved, existing capsule progression | Owner A4 decision, registered venue and approved mandate, actual E2E receipts, rollback and alerting | Existing VATI limited/certified live process only |

A module with demonstrated avoidance of dangerous contracts but no demonstrated positive trading lift may be promoted **only as a defensive veto**, subject to false-positive review. Never promote it as an alpha model based on prevention claims alone.

### 11.2 Mandatory adversarial regression cases

| Test ID | Failure injection | Required outcome |
|---|---|---|
| INV-01 | Exactly one survivor of a screening cycle | It still undergoes all hard gates, no-trade assessment and verified opportunity economics |
| INV-02 | Mint/freeze field is string `"no"` | Normalized false, not Python-truthy true |
| INV-03 | Two token contracts share a ticker | Canonical IDs remain distinct across models, stores and UI |
| INV-04 | AMM pool holds >5% supply | Attributed correctly; raw account concentration not equated with insider ownership |
| INV-05 | Token younger than volume lookback | Non-overlapping current/previous windows or unknown; no impossible ratio exit |
| INV-06 | Buy is possible but sell reverts / high transfer tax | No viable candidate or live quote |
| INV-07 | Quote stale / provider unavailable | Abstain or fail closed; no stale substitute presented as live |
| INV-08 | Order rejected/partial fill/disconnect | Existing receipt, reconciliation and account lock prevail; no phantom position |
| INV-09 | Model says probability 0.99 without valid calibration | Cannot increase risk or bypass veto |
| INV-10 | Agent says skip emergency exit during whale selling | Deterministic preservation/kill switch wins |
| INV-11 | Browser/social post contains trading instructions or secrets | Treated solely as untrusted content; injection cannot trigger tools/orders |
| INV-12 | Re-run on frozen inputs and same versions | Same candidate, model state, decision hash and recorded experimental arm |
| INV-13 | New chain reorganizes blocks or indexer is behind | Finality/staleness quality downgrade and conservative abstention |
| INV-14 | 2× spread/slippage; sell route disappears | Stress metrics update; no falsely profitable promotion |
| INV-15 | Crypto data comes from unauthorized/private provider | Provider adapter disabled; audit incident recorded |

### 11.3 Quantitative qualification metrics

**Always report:** full cohort size, rejection reason histogram, unresolved cases, actual data freshness, executed/not-executed universe, post-cost net expected/realized R, commissions/spread/slippage/gas/financing separated, max drawdown, risk-adjusted returns, CVaR or tail-loss measure, calibration (Brier/ECE), false positives/false negatives for independently labeled scams, missed legitimate winners, latency distribution, rate-limit and data spend, input/model/code/mandate versions, and receipt completeness. No single headline metric qualifies a module.

**Operational invariants:**

- 100% of live execution attempts are preceded by a valid sealed existing `RiskDecision`.
- 100% of new crypto trading candidates must have instrument/venue identity, current economic sell-route evidence and an approved execution route; absence means `NO_TRADE`.
- 100% of completed trades must reconcile to confirmed venue/wallet receipts before P&L is represented as `REALIZED`; partial/no receipts remain flagged.
- Replay must reproduce the same canonical decision hash on an immutable input/versions manifest.
- A 95% lower confidence bound on measured lift can be required for materiality, but sample size, regime coverage, false positives and sequential testing must be specified **before** trials; no unqualified fixed number of trades guarantees validity.

---

## 12. Historical milestone aliases — not an independent delivery schedule

**These are logical milestones, not estimates of calendar duration or proof of completed implementation.** Each slice must be independently tested and qualified before following work relies on it.

| Slice | Work package | Dependency | Deliverable | Definition of done |
|---|---|---|---|---|
| **M0** | Repository authority and feature reconciliation | None | Existing-vs-proposed capability matrix, PR/branch ownership, expected file paths, provider-rights matrix | No duplicated already-built module; canonical decisions explicit |
| **M1** | Provenance and executable-cost contracts | M0 | VATI-compatible source/economic fact schemas; quote freshness, both-leg costs; test adapters | Induced stale/fee/partial-fill tests and replay pass |
| **M2** | Incremental evaluation harness | M1 | Matched-candidate / paired-opportunity experiment ledger | No survivor bias, correct counterfactual labeling, fixed experimental universe |
| **M3** | Qlib/LightGBM model research | M1–M2 | Dataset handlers, LightGBM baseline, calibration, sealed model artifacts | Purged walk-forward, cost stress, baseline comparison, no leakage |
| **M4** | NeuralForecast challenger | M3 | Regime/horizon-targeted alternative forecaster | Proven *incremental* lift vs LightGBM/simple baseline or explicitly rejected |
| **M5** | Read-only crypto discovery/safety | M1–M2 | Canonical contract IDs, provider adapters, rejects, chain security fixtures | Identity, unknown, LP attribution and sellability negative paths pass |
| **M6** | Temporal wallet intelligence | M5 | Historical wallet/holder graph and counterfactual value test | Demonstrated extra safety information; no fabricated wallet ownership |
| **M7** | Optional Jev and public Kalshi challengers | M2–M4, M5 where relevant | Typed question adapters and probability-context feed | Cost/benefit and calibration evaluated; remain disabled if unproven |
| **M8** | Owner UI / analytics | Canonical BG-001 and UX-003 only | Receipts-derived funnel, ablation, data-quality and cost panels | UI distinguishes research, paper, live and simulated results |
| **M9** | Staged qualification/promotion | Relevant slices + authorized account | Zuul qualification receipts, capsule evidence, owner decision packet | No unapproved risk widening or live-order route |

**Execution location:** authorized VAN trading VMs under the existing Netcup/Oracle/DIAL project-binding model, not the user's physical desktop. Route infrastructure/compute through approved typed controls. Research jobs use T3/offline scheduling; bounded inference uses T2; broker/route data and time-sensitive execution remain in their existing VATI paths. Do not place cloud LLM API dependencies inside the execution critical path.

**CI/release:** attach implementation tests and qualification receipts to the project's existing **Zuul** route rather than introducing GitHub Actions as a new deployment authority. Treat branch-level integration evidence and actual VM smoke tests as different receipts; “tests passed” does not mean “running in production.”

**Feature/work acceptance card (mandatory for every work package):**

```
feature_id:
source_observation_and_current_revision:
canonical_owner_and_authority:
producer:
consumer:
production_caller:
state_store_and_schema:
versioned_source_contract:
positive_tests:
negative_and_falsification_tests:
model_or_provider_cost:
runbook_and_rollback:
owner_surface:
replay_receipt:
runtime_receipt:
external_dependency_or_blocker:
qualification_state:
```

Use existing maturity language: `ABSENT`, `STUB`, `SIMULATED`, `PARTIAL`, `IMPLEMENTED_BUT_ISOLATED`, `INTEGRATED`, `E2E_VERIFIED`, `PRODUCTION_CERTIFIED`. A repository module without a real producer, consumer, live caller, owner-visible output and runtime receipt is **not finished**. Failure to secure a provider or obtain a chain indexer can be `EXTERNALLY_BLOCKED_REPOSITORY_COMPLETE` only when all controllable work and tests are complete.

---

## 13. Cost, capacity and provider policy

- **Phase 1 hardware:** keep deterministic features, tabular LightGBM and modest historical studies on existing authorized CPU VMs; Required NeuralForecast integrations are mandatory; further deep experiments are evidence- and cost-selected and benchmarked against CPU/DRAM/time cost before GPU expenditure.
- **Market feeds:** cache immutable facts and obey provider quotas; use rate limiting/backoff, provider health budgets and archive exact raw responses. Never infer that an endpoint's public visibility grants unlimited bulk reuse.
- **Jev/LLM:** invoke only after cheap filters, batch typed questions when supported, cap daily calls/cost, audit abstention and response TTL. A low per-judgment fee is not the total cost of X/chain/RPC access or on-chain execution.
- **Chain intelligence:** archive selectively by discovered asset, prioritization criteria and retention value; control indexer call-volume before deciding whether to operate a node or buy data.
- **Prediction markets:** public API read-only evaluation can be useful without a trading account. Venue trading, wallet funding, access eligibility and legal clearance are **not inferred** from running the VM abroad.
- **No fake cost estimate:** the development team must produce a provider-specific costed pilot (requests, data GB, CPU hours, RPC credits, paid feeds, API model calls) with observed numbers before the deployment budget is signed.

---

## 14. What profitable systems prove — and what they do not

| Reference | Verifiable observation | Appropriate inference for VAN | Not established |
|---|---|---|---|
| [AQR 2025 filed shareholder report](https://www.sec.gov/Archives/edgar/data/1444822/000144482226000009/primary-document.htm) | AQR Managed Futures Strategy Fund Class I returned **14.63% net** in 2025 using diversified systematic trend strategies | Multi-signal, structured risk-managed trading can operate profitably | That Jev, token screening or this precise VAN blueprint produced that profit |
| [Crypto Fund Research 2025 review](https://cryptofundresearch.com/crypto-hedge-fund-performance/) | 26 reported algorithmic/quant funds averaged **+0.4%** in 2025, while 15/26 were positive; source includes self-reported data | Quant approaches can outperform passive crypto in some regimes; dispersion is high | Reliable alpha or verified performance for a particular open-source component |
| [Academic new-token study, *EPJ Data Science*](https://doi.org/10.1140/epjds/s13688-025-00602-5) | Honeypots/MEV/liquidity manipulation complicate theoretical profits | Implement protection and executable cost modeling first | Safety screening alone makes a new-token strategy profitable |
| [CEX–DEX arbitrage empirical study](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.AFT.2025.26) | ~$233.8M **estimated extracted value** among 19 searchers in 2023–25 | Live opportunity economics and low-friction execution matter | This is audited net profit or attainable on ordinary non-colocated VAN infrastructure |
| [TypeSafe Jev SDK](https://github.com/jev-ai/typesafe-ai-jev) | Structured `Choice`, `Score`, `Noul` judgments and typed outputs | Useful challenger interface | Jev answers produce calibrated profitable entries by default |
| [Microsoft Qlib](https://github.com/microsoft/qlib), [LightGBM](https://lightgbm.readthedocs.io/), [Nixtla NeuralForecast](https://nixtlaverse.nixtla.io/neuralforecast/index.html) | Official tools support reproducible model/forecast research | Reuse to reduce research cost and compare challengers | That installing these packages creates alpha |
| [Freqtrade lookahead-analysis](https://www.freqtrade.io/en/stable/lookahead-analysis/) | Specific testing practice detects future-data leakage | Port/adapt its diagnostic ideas into VATI's own harness | Freqtrade should be a second live kernel |
| [Kalshi public API](https://help.kalshi.com/en/articles/13823854-kalshi-api) | Public market data via documented REST API | Read-only forecast/context research is feasible | Exchange account eligibility or profitable arbitrage |

**Important source-level reality check:** The @savipww published guide omits private FOMO and Grok desk execution adapters; its audit identifies a skipped single-survivor no-trade gate, incomplete trade state, broken young-token volume exit, missing time-series features and brittle chain-data parsing. None should be copied into VAN. Latest October video features have not been verified against a corresponding public implementation.

---

## 15. Superseded narrower staging proposal — corrected by current owner-directed scope

**Operative adoption scope:** the owner directed proceeding with the reviewed recommendations. All existing forecast engineering and read-only A04/A05 domain duties are included in Unified Rev1.12. M0–M9 and G0–G6 are explanatory lineage aliases, not selective waivers or independent approval paths. No wallet, signing, new live venue or increased capital permission is included. PRE-003 independent F15 and BG-001 remain unissued.

**Default recommendation:**

1. Keep VAN's existing deterministic trading path and active Rev 4/Rev 5 authority unchanged.
2. Preserve all mandatory Qlib/LightGBM/NeuralForecast software and challenger plugins; only economic influence is conditional.
3. Put executable economics and counterfactual evidence *ahead of* new AI models.
4. Build a chain-aware fraud/exitability monitor as read-only defensive intelligence; do not promise automated profitable meme-coin sniping.
5. Use Jev, X/social and public prediction-market signals only after they clear a cost-adjusted matched-cohort ablation.
6. Admit into strategy capsules and modes only through VATI's existing staged evidence and owner approval.

**Success is:** a falsifiable, cost-aware, auditable improvement in **expected and realized net risk-adjusted trading performance** (or independently demonstrated defensive loss reduction), with **zero new order authority** outside the existing VAN trading core. This document recommends research/implementation priorities; it does not report work completed or certify future profitability.


## 16. Integrated correction and source-reconciliation contract

## 30. Integrated high-value trading intelligence and read-only crypto research

### 30.1 Current owner direction, revision and scope

The owner instruction **“Proceed according to your recommendations”**, following the comparative review of the uploaded High-Value Trading Adoptions Rev1.0, authorizes preparation and integration of the reviewed specification changes. This revision records that scope direction. It does not manufacture an owner cryptographic signature, independent F15/BG certificate, model-promotion decision or financial mandate. The current deliverable is an owner-directed integrated specification candidate; application implementation starts only through the existing admitted packet and F15 process.

The uploaded proposal is retained unchanged as provenance. Its corrected technical companion is `research/HIGH_VALUE_TRADING_INTELLIGENCE_INTEGRATED_REV1_1.md`. It has **no independent executable schedule**. The canonical specification is this master plus its machine contracts; `plan/DEVELOPMENT_PLAN.json` is the sole schedule. Source-qualified unit IDs remain stable; the generated `VAN-PKT-*` sequence is revision-qualified and its complete Rev1.11-to-Rev1.12 mapping is included. A cached old packet number must never silently resolve to a different unit.

All 205 inherited requirements—including all 90 forecasting requirements and 20 corrective contracts—remain intact. Required Qlib, LightGBM, FreqAI-inspired mechanisms, NeuralForecast models and challenger integrations, calibration, artifact handling and prediction-market laboratories are **engineering obligations**, not optional software contingent on an early profitable result. Economic admission of their outputs remains conditional on evidence. A correct integration can report `NO_QUALIFIED_MODEL`, `REJECTED` or `INCONCLUSIVE`; a missing integration cannot use those labels to claim engineering completion.

Netcup/Oracle remain the intended compute environment. This revision adds no new data-licence purchase, paid subscription, venue account registration, funded wallet, transaction signing, trading venue or capital increase. Existing permitted access may be used; code, schemas, fixtures and unrelated dependency-ready work proceed without procurement. An unavailable required provider is recorded precisely and cannot be replaced by a synthetic success or waived to open global BG-001. Hosting location, source permissions and operator/account eligibility remain separate recorded properties.

### 30.2 Source reconciliation that must precede implementation

The preceding review inventoried all 66 advertised branch heads at 63 distinct commits, with 4,634 union paths. Its supported-text pass scanned 3,680 unique UTF-8 blobs and excluded 26 size/encoding candidates. It was a complete head-tree inventory and bounded content/import scan, **not** universal semantic qualification. A current Global DIAL read refreshed the advertised heads and found no changes. Both observations are identified by exact request and artifact references in the source register; implementation must refresh them again before any source merge.

The operative source conclusions are:

* Keep PR101/`a39f241b…` resting-order, ledger, rounding and recoverable-lockout improvements, but close the already specified execution/simulator defects before using economic results for admission. A positive distant-limit control demonstrates that pending support exists; worse-than-limit fills remain a separate defect.
* Reconcile canon/PR93 shared Jev consumers, typed learning evidence and temperament changes with the PR92 and cognitive-fabric contribution sets at the **function and caller** level. Account service and coordinator had five distinct variants in the reviewed heads. Neither largest commit count nor newest branch name establishes a complete implementation.
* Reuse the shared `dial-jev` service and existing gateway/cognition clients. Existing infrastructure is not evidence that a new token-vetting question set has predictive value.
* Existing `AllocatorV1` is a deterministic quality/edge-floor extension that continues to exclude uncalibrated confidence. It is not an already implemented calibrated-model policy. Any further ranking policy needs a separately versioned contract and tests under that same owner.
* No production imports of the named forecast libraries, implementing prediction-market adapters or concrete token-security analyzers were established in the scanned source. This is a dated tracked-source observation, not proof about uncommitted work or external services.

BE-001 must merge only independently reviewed compatible changes and prove retained callers, authority checks, state migrations and negative paths. The documentation update does not merge these branches or certify them. The existing main and protected working sources remain unchanged by this pack.

### 30.3 One owner for each mechanism

The eight new logical backend capabilities extend existing services rather than mandate eight new microservices. The service catalogue identifies producer → durable state → consumer and the exact governing unit for each.

| Mechanism | Existing owner to extend | Forbidden substitute |
|---|---|---|
| Identity, quotes, source availability and state anchors | Market-data, acquisition and event/provenance services | A parallel ungoverned data lake |
| Features and targets | Shared definitions, point-in-time datasets, Feast parity and TargetSpec | Crypto-only labels that evade chronology |
| Research/training | Existing Qlib/LightGBM/NeuralForecast/Optuna workflow | A second training scheduler or registry |
| Calibration and artifact lifecycle | Existing calibration boundary and MLflow integration | A new conflicting confidence service |
| Candidate selection | Existing opportunity arbiter and versioned allocator | Agent-owned sizing or capital reservations |
| Risk and order submission | Existing RiskAuthority, account coordinator and ExecutionRouter | New wallet, exchange sender or position book |
| Judgment | Shared `dial-jev` through registered VAN consumers | Standalone Jev trading service or credential plane |
| Evaluation | Qualified simulator, experiment ledger and account-wide replay | Scaled actual-R used for different hypothetical trades |
| Owner interaction | Existing gateway/capability catalogue and post-BG native surfaces | Early dashboard or low-trust order buttons |

Broad “T2” terminology in the upload does not move every forecast into a remote slow call. Heavy training, public RPC/indexers, source extraction and remote judgments remain asynchronous outside T0. The bounded local ForecastService produces prepared results with freshness and applicability controls. T0 neither imports the research dependency stack nor synchronously calls an indexer, remote judge or artifact registry.

### 30.4 Evidence namespaces and maturity dimensions

The upload's E1–E5 publication-quality scale and the parent E0–E6 implementation-evidence scale are different namespaces. Preserve their provenance, but never merge them into an ambiguous `evidence_grade` value.

| Source classification | Meaning | What it does not prove |
|---|---|---|
| `RS1_PRIMARY_TRANSACTIONAL` | Primary or transactionally verifiable source | Correct VAN implementation |
| `RS2_PUBLISHED_REPRODUCIBLE` | Published technical result or reproducible study | VAN-specific profit |
| `RS3_VENDOR_CAPABILITY` | Vendor-supported interface/capability | Software test, deployment or alpha |
| `RS4_SELF_REPORTED` | Self-reported performance | Independent financial verification |
| `RS5_UNVERIFIED_CREATOR` | Unverified creator/video claim | Android certification or trading edge |
| `SYNTHETIC_FIXTURE` | Authored test data | Real provider observation |

`implementation_evidence_level` retains the parent's E0 OWNER_REFERENCE through E6 OWNER_VISUALLY_ACCEPTED values, plus `SPEC_ONLY` where no implementation proof exists. Legacy grade conversion requires the original source schema. Ambiguous historical rows remain unresolved. A schema, hash or registry alias by itself grants no authority.

Record engineering state, source integration/access state, economic-use qualification and live authorization separately. A defensive veto can qualify on independently measured defensive value without positive alpha, but must also account for false rejection and must never block a mandatory protective exit. Offline fixture tests do not qualify a live source, and an inaccessible source does not mean the rest of the code cannot be completed.

### 30.5 Canonical discovery identity and the complete cohort

Canonical asset identity is `(chain_namespace, network_id, canonical_token_address)`, produced by a chain-specific validated codec and linked to the raw representation. Display names and tickers are never keys. Pool and router identities are independent and chain-qualified. A token can have multiple pools; migration changes the pool relationship and liquidity history, not the token's identity.

Do not use one universal lowercase/string-normalization function. The chain adapter must validate its address encoding and decoded identity, preserve versioned normalization rules and reject malformed or unsupported identities. Tests include duplicate tickers, chain/network collisions, multiple pools and migrations.

Persist discovery **before** the survivor funnel. Every source observation has raw hash, source/cursor identity, availability time and block/slot anchor where applicable. Retain investigated, rejected, unknown, expired, delisted, unreachable and migrated candidates. Queues are bounded and source-quota-aware; negative results bind their reason, source/rule/state version and expiry. A meaningful state or rule change can invalidate a rejection before its timer expires. Restart restores the queue from durable state without duplicate jobs.

The funnel preserves D0–D6 from the donor concept: identity/discovery, inexpensive numerical checks, contract capabilities, attribution, temporal flow, optional typed context, and executable economics. Those are logical stages under existing owners, not seven new trading agents. Exactly one survivor still receives every remaining hard gate, `NO_TRADE` remains valid, strings such as `"no"` are explicitly normalized, and creator example thresholds never become VAN defaults without measured false-positive/false-negative evidence.

### 30.6 Discrete chain-security analyzers

**Solana capability:** distinguish supported SPL Token and Token-2022 observations. Inspect mint/freeze authority and applicable transfer fees, hooks, delegates and other supported extensions. Bind results to the program/parser revision, slot, source and finality policy. An unrecognized extension or missing state is UNKNOWN, not benign. Technical pool/vault/burn roles must be evidenced before they affect concentration.

**EVM capability:** bind code, proxy and implementation identity to the chain and state observed. Inspect applicable upgrade/admin powers, transfer limits/taxes, mint/blacklist and liquidity-removal controls through supported read-only evidence. A verified proxy shell does not establish the behavior of a changed implementation. Unverified code increases uncertainty; it does not establish fraud or safety.

Both analyzers produce factual `ChainSecurityFinding` records and uncertainty-bearing features. Their verdict vocabulary is `REJECT`, `INVESTIGATE`, `NO_HARD_BLOCK`; **NO_HARD_BLOCK is not SAFE_TO_BUY**. Findings state evidence coverage, unsupported checks, observation time and expiry. A finding can inform research or a separately qualified restrictive consumer, but cannot grant a route, sign a transaction or overrule risk-reducing operations.

### 30.7 Sellability and executable economics

Buy and sell checks are independent. Where supported, run read-only simulations against the stated chain/router/contract/pool state at the declared quantity, with caller assumptions, gas/fee conventions and finality recorded. Success proves only the stated simulation result at that state. It does not promise that a later sell will execute, survive changed taxes or obtain the same liquidity.

Separate three records:

1. **ExecutableQuoteFacts:** observed side, quantity, currency, executable quoted cash/depth, provider/route and state anchor, availability/expiry and fee-inclusion components. No projected exit cash or fill probability is permitted in this facts record.
2. **ExecutionEconomicsForecast:** modeled exit proceeds, execution/failure costs or fill probabilities, with explicit target, horizon, artifact/transform/calibration lineage and applicability. A probability requires its precise observable event; an amount forecast does not masquerade as a probability.
3. **NetEdgeAssessment:** a derived economic calculation referencing the exact facts and forecast versions, uncertainty and cost convention. It identifies included costs to prevent double-counting.

For quantity `q` and horizon `h`, a cash-consistent research estimate is expected executable exit proceeds minus entry cash and any costs not already included. Compare it with the strategy's preregistered materiality/uncertainty floor and independent risk eligibility. Depth, slippage, transfer costs, gas and failure costs need not scale linearly with size. A small quote cannot be extrapolated into free liquidity at a larger quantity.

The existing evaluator repairs remain upstream: limit-price semantics, effective expiry propagation, pending-fill protection, canonical order state, terminal liquidation cash, commissions/financing, intrabar ambiguity and full-account risk competition. Do not call the new economics qualified merely because a cost estimate is used to screen candidates. The simulated cash ledger must actually charge the appropriate costs. All DEX trade outcomes remain hypothetical here; there is no new signing wallet or execution client.

### 30.8 Temporal wallets, attribution and reorganization

Persist comparable anchored snapshots of holdings, supply, transfers, liquidity and role labels. Compute changes only between observations with compatible coverage. A single snapshot cannot establish growth or accumulation. A routed transfer is not automatically a genuine purchase; common funding is not conclusive common ownership.

Retain raw concentration and separately derived role-adjusted concentration with every exclusion explained. Proven technical pool/vault/router/burn accounts can be treated appropriately without deleting the raw history. Attribution is uncertainty-bearing. Heuristic clusters must retain assumptions, evidence and revision; legitimate airdrops/OTC/internal transfers must appear in negative controls.

Young assets need explicit lookback coverage. Missing preceding windows remain unknown instead of receiving a fabricated denominator. Deduplication uses the chain's transaction/log/instruction identity under the relevant adapter. Disappearing pools, source lag and unobservable exits are retained as censoring/missingness, not zero loss or an excuse to delete a cohort row.

Maintain transitive provenance from source/state → facts → features → forecasts → study/consumer. Reorganizations, corrected observations, changed authority/implementation and pool migrations produce versioned invalidation batches. Every affected cached result loses eligibility before reuse. Revalidation is idempotent and checkpointed; a crash must not leave a stale descendant ready. Historical observations and decisions remain immutable, while new analytical versions record the correction. Finality policy itself is versioned and cannot silently upgrade an observation.

### 30.9 Matched opportunities and account-level evaluation

The existing cognitive shadow book remains a **same-trade, size-only attribution view** under its declared proportional assumptions. `actual_R × multiplier` is not an independently observed hypothetical trade, a different path's own-risk R, or a faithful treatment of nonlinear costs. Preserve that useful limited view; do not stretch its claims.

Use the existing experiment and account-replay services for changed discovery, selection, timing, route or exit policy. Seal the decision opportunities, universe, feature/quote versions, both arm decisions, unresolved rows and simulator assumptions before outcomes mature. Each arm maintains its own account state, pending orders, reservations, cash, risk and later opportunity eligibility. Skipping a trade changes future opportunity cost. Summing unconstrained single-instrument simulations does not produce a feasible portfolio.

Tag hypothetical outcomes `SIMULATED_COUNTERFACTUAL`. Forward paper results and actual venue outcomes retain their own evidence classes. Paired replay estimates **incremental policy performance under its stated assumptions**; it does not identify a causal effect simply because two policies were simulated. Use prespecified event/time/asset-cluster-aware resampling, exposure-matched and simple-calendar controls, all losing trials and sequential-testing rules. Report net cash/R, coverage, abstention, false rejection, unresolved outcomes, risk, drawdown, costs and operational overhead.

The upload's proposed positive lower-95%-confidence-bound rule becomes a candidate setting within the **one** versioned validation policy, not another admission service. Materiality, sample adequacy, clustering, multiplicity and stopping rules must be locked before results. Preserve existing DSR/PBO and other applicable gates; do not overwrite them with a convenient scalar. Inadequate evidence produces INCONCLUSIVE.

### 30.10 Targets, Qlib/LightGBM and NeuralForecast integration

Use the already required model adapters rather than separate crypto-only models by default. New features and targets flow through the common point-in-time dataset, feature/target specification, Qlib study, LightGBM/NeuralForecast integration, Optuna trial record, calibration and MLflow artifact lineage.

Terminal return, after-cost strategy result, maximum adverse excursion, stop touch and fill probability are distinct targets. They differ in path dependence, horizon, label maturity and censoring. A lower terminal-return quantile cannot be relabelled a calibrated probability of hitting a protective stop. Model output probabilities, ranking scores, attribution confidence and Jev answer quality are likewise not interchangeable.

Maintain the full NeuralForecast engineering scope from §28, including direct model integration, retained temporal scenarios, contextual challengers and secure persistence. Evaluate added wallet/security/liquidity features first against the appropriate simple and tabular baselines. Economic rejection of a domain experiment does not remove the underlying model capability from the required programme.

Preserve prediction-market contract semantics, grouped calibration, asset-response models, execution replay, arbitrage and market-making research. A07's probability-context ablation is an experiment within that programme, not a replacement for it. Cross-venue agreement is not independent corroboration; shared sources across models cannot be counted as multiple independent signals.

### 30.11 Jev question sets and qualified ranking

Use the actual shared `dial-jev` consumer and existing exact evidence resolver. Registered question sets must be narrow and falsifiable—for example, whether two supplied identifiers conflict, whether a documented claim is supported, or whether the provided observations are temporally comparable. Include unknown/unanswered, question-set version, snapshot/input hash, provider/model identity, deadline, cost and expiry. No private credentials or prompt-supplied broker instructions enter the model context.

Run rule/no-LLM, Jev and any approved challenger on the same sealed case set. Measure correct/incorrect/unknown answers, false rejection, genuinely observable label calibration, cost and incremental policy value. Answer quality does not imply a profitable-trade probability. A new domain question set needs its own evaluation even when transport and existing attention/browser questions are already implemented.

The current AllocatorV1 continues unchanged as the inherited baseline. A model-informed ranking amendment must have a new explicit policy/version and qualified input contract at the **same** owner. It may select among otherwise eligible candidates; it does not size, widen risk, reserve cash independently or turn a high model score into a second mandate. Revocation restores the qualified baseline while preserving pending-order reservations.

### 30.12 Serving, recovery and determinism

Prepared forecasts/judgments carry exact state, transform, target, model, calibration, source availability and expiry. Incompatible, non-finite, stale, revoked or reorganized inputs cannot become current evidence. The positive valid path must be exercised as well as all refusal paths; a permanently unbound producer is not an implemented integration.

Keep four different reproducibility claims distinct: exact canonical replay of persisted evidence; repeatable fixed-seed inference in a pinned environment; declared cross-device numeric tolerance; and stochastic retraining reproducibility assessed statistically. No promise of byte-identical neural/GPU training follows merely from a frozen dataset. Record actual environment, configuration and tolerance rather than weakening deterministic risk-decision replay.

Outages, indexer lag, quota exhaustion, delayed results and interrupted revalidation must have bounded behavior and a truthful read model. Research unavailability cannot disable mandatory protective exits. Rolling back a model or data adapter does not resurrect revoked calibration or incompatible state. Retention and provider-use rules are enforced independently from audit immutability claims; record policy-governed deletions and reference invalidation where retention requires it.

### 30.13 Headless operations and post-BG owner surfaces

BE-044 completes the real producer/store/consumer joins, and BE-032/033 include their catalogue, isolation, capacity, observability, recovery and retention behavior. API/read-model construction is backend work. **No new native UI is authorized before the sole global BG-001**, even if one feed is already healthy.

The six new context obligations are progressive-disclosure views within the existing Trading/Research/Analyst/Work/Settings navigation, not six mandatory global pages: discovery funnel; state-bound security finding; wallet/flow evidence; sellability and economics; matched-cohort report; and typed judgment trace. Each retains native accessibility, offline/stale/unknown states, dark/light tactile design and evidence drill-down. They introduce no order, signing or funding action.

Counts reconcile total observed, rejected by reason, investigated, eligible, economically assessed, paper-simulated and actually filled **only where that evidence exists**. Research-only crypto can correctly show zero actual fills. Fixture, delayed, simulated, shadow and observed classes are visible from provenance, not from the appearance of a chart. No simplified green “safe token” badge is permitted.

### 30.14 Dependency integration and complete acceptance

New BE-037–044 are logical capabilities in the existing plan. Existing BE-001/003/010/013/021/024/032/033/035 and forecast dataset, target, calibration, serving and evaluation units receive additive contracts rather than duplicate siblings. BQ-008 verifies chain/source/finality end-to-end behavior; BQ-009 verifies full-cohort economics, evidence semantics, judgment/ranking and authority separation. Both feed BQ-006 and the sole global BG-001. All old units and their original exit obligations remain.

The added requirements and their positive, adverse and recovery contracts are machine-readable. Every requirement maps to existing/new unit owners, a producer and durable state, downstream consumer, planned evidence and eventual owner context where appropriate. All application acceptance records remain NOT_RUN in this documentation delivery; document mutations and synthetic schema checks cannot change those states.

Legacy M0–M9 and G0–G6 are explanatory crosswalk aliases. Their old ordering, reduced optional scope and M8 single-feed entry condition have no authority. The application runner must bind `(plan_revision, scope_digest, unit_id)`; old `VAN-PKT-*` numbers are resolved only through the revision-qualified crosswalk, never by positional coincidence.

### 30.15 No-loss and correction closure

Preserve all original requirement text, existing corrective contracts, 18 Product Truth atoms, 93 earlier features, 171 source atoms, 349 historical owner actions and the locked visual bytes. Original source/test documents remain lineage. Changed plan dependencies, prepared locks and source mappings are explicit revision deltas, not forged updates to signed inputs. The package includes a byte-preservation report and old-to-new schedule map.

The review's R01–R12 concerns are closed **at the specification level** by linked amendments, schemas, owner mappings and tests. The associated application defects and integrations remain open until actual implementation and appropriate receipts. Previously reproduced paper-limit/expiry counterexamples are retained as evidence and regression requirements; this revision does not claim to have fixed their code.

### 30.16 Implementation entry and exclusions

The next executable programme remains PRE-001 source/feature reconciliation, PRE-002 independent semantic/contract review, then PRE-003 F15 with the required exact owner trust binding. Updating the document and passing its checks is not a substitute for those exits. Once admitted, dependency-ready backend source consolidation and implementation proceeds on the authorized DIAL VM topology; no physical desktop or silent alternative runtime is part of the plan.

Existing Zuul admission and typed Global DIAL deployment remain the routes. No new GitHub Actions deployment authority, hosted tunnel, IAM, firewall, credential, paid account or broad infrastructure repair is included. Release and model/strategy live admission remain separate. The desired result is a fully implemented, honestly evaluated capability—not an obligation to claim profitable forecasting or fabricate unavailable integration evidence.



## Historical milestone/gate aliases into the one canonical programme

These aliases preserve explanatory lineage only. Read prerequisites and order from the generated canonical plan, not the order in this table. G6 does not grant financial permission.

| Original label | Canonical obligation owners |
|---|---|
| M0 | PRE-001, PRE-002, PRE-003, BE-001 |
| M1 | BE-008, BE-010, VAN-ML-PKT-007, BE-041 |
| M2 | BE-035, VAN-ML-PKT-010, VAN-ML-PKT-027, VAN-ML-PKT-030, BE-044 |
| M3 | VAN-ML-PKT-011, VAN-ML-PKT-012, VAN-ML-PKT-013, VAN-ML-PKT-014, VAN-ML-PKT-015 |
| M4 | VAN-ML-PKT-016, VAN-ML-PKT-017, VAN-ML-PKT-018, VAN-ML-PKT-019 |
| M5 | BE-037, BE-038, BE-039, BE-040, BE-041 |
| M6 | BE-042, BE-043 |
| M7 | BE-021, BE-044, VAN-ML-PKT-037, VAN-ML-PKT-038, VAN-ML-PKT-039, VAN-ML-PKT-040, VAN-ML-PKT-041, VAN-ML-PKT-042, VAN-ML-PKT-043, VAN-ML-PKT-044, VAN-ML-PKT-045, VAN-ML-PKT-046, VAN-ML-PKT-047, VAN-ML-PKT-048 |
| M8 | BG-001, UX-003, FE-023 |
| M9 | BQ-008, BQ-009, BG-001, QA-005, REL-001 |
| G0 | PRE-001, PRE-002, PRE-003 |
| G1 | BE-037, BE-038, BE-039, BE-040, BE-041, BE-042, BE-043, BE-044 |
| G2 | BE-035, VAN-ML-PKT-010, VAN-ML-PKT-030 |
| G3 | VAN-ML-PKT-030, VAN-ML-PKT-031 |
| G4 | BQ-008, BQ-009 |
| G5 | BQ-007, BQ-009 |
| G6 | REL-001 |
