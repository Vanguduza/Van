# VAN — High-Value Trading Intelligence Adoptions
## Additive, Repository-Aligned Engineering Blueprint — Revision 1.0

**Date:** 2026-10-17  
**Status:** **RECOMMENDATION / DERIVED IMPLEMENTATION BLUEPRINT — NOT ADOPTED, NOT DEPLOYED**  
**Product:** VAN Adaptive Trading Intelligence (VATI)  
**Primary purpose:** Adopt objectively useful capabilities from the @savipww Grok Bot + Jev design and from systematic/profitable trading practice **without importing its unverified results, replacing existing VAN architecture, or weakening established safety invariants**.  
**Change type:** Additive. No repository writes, owner-signatures, strategy promotions, venue onboarding or live orders are authorized by this document.

> **Decision in one sentence:** Prioritize execution-realistic economics, empirically calibrated quantitative forecasts, verifiable data and controlled experiment design across VAN; add wallet/contract intelligence as an isolated read-only crypto research capability; treat Jev-like subjective judgments and prediction-market signals as challengers until they demonstrate **incremental net value**.

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

**Evidence categories:** `E1` filed/primary/transactionally verifiable; `E2` published peer-reviewed or independently repeatable technical results; `E3` vendor-verified capability, not profit; `E4` self-reported trading results; `E5` unverified creator/video performance. Profitable organizations demonstrate *systems*, not that any individual feature caused their returns.

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
| **VAN-A01** | Execution-realistic opportunity economics and liquidity/sellability evidence | Multi-market + crypto | **P0** | E1/E2 (fill costs; market microstructure) | Facts / veto only | **Implement/extend** |
| **VAN-A02** | Quantitative model research and calibrated ensembles (Qlib + LightGBM; NeuralForecast where justified) | Multi-market | **P0** | E1/E3 architecture + conditional strategy evidence | Propose/rank after qualification; no sizing | **Implement at current gates** |
| **VAN-A03** | Matched-universe, cost-aware incremental evidence evaluator | Multi-market | **P0** | First-principles auditability | Evaluation only | **Extend existing evidence** |
| **VAN-A04** | Deterministic multi-stage discovery and rejection funnel | Crypto research only initially | **P1** | E2 risk studies; E5 profit claim | Read-only candidate veto | **Prototype** |
| **VAN-A05** | On-chain security, wallet attribution, temporal holder-flow intelligence | Crypto research only initially | **P1** | E2 for scam detection, not alpha guarantee | Read-only candidate veto | **Prototype in sequence** |
| **VAN-A06** | Calibrated typed AI judgments (Jev optional + model-agnostic adapter) | Asynchronous research / T2 | **P2** | E3 typed API, unproven incremental P&L | Commentary/abstain/reduce; no orders | **Challenger experiment** |
| **VAN-A07** | Prediction-market probability intelligence (Kalshi/public permitted feeds) | Cross-market research | **P2** | E3 market data; incremental edge unproven | Slow context only | **Read-only ablation** |
| **VAN-A08** | Specialist agent work routing and operator explanation | Existing Hermes/VAN | **P2** | E3 operational separation, not alpha | Research/monitor/report | **Map onto existing agents** |

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

**Contract (proposed, not an existing repository schema):** `ExecutableCostEvidence {account_alias, venue, instrument_id, decision_point_id, observed_at_utc, quote_id, buy_qty, entry_cost_ccy, projected_exit_cash_ccy, fee_components, route_depth, p_fill_estimate, data_quality, source_hash, expires_at_utc}`. Unknown sellability or no current quote ⇒ `UNKNOWN/NO_TRADE` on a crypto-trade request.

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
| **Existing VAN portfolio allocator** | Choose among admissible candidates; confidence-aware ranking only after calibration and authoritatively approved V1 gate | Approve lot size or reserve portfolio capital |
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

**Tiers:** T2 or slower with TTL appropriate to strategy horizon. Not in T0, not for SCALP/instant token-sniping. Model output can explain, abstain, reject or *reduce* an already admissible candidate; any use in ranking requires validation and the existing calibrated allocator upgrade. Never an unrestricted authority to buy, increase size, cancel a protective stop or ignore hard rules.

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

## 12. Dependency-ordered delivery programme

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
| **M8** | Owner UI / analytics | M2 and at least one qualified feed | Receipts-derived funnel, ablation, data-quality and cost panels | UI distinguishes research, paper, live and simulated results |
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

- **Phase 1 hardware:** keep deterministic features, tabular LightGBM and modest historical studies on existing authorized CPU VMs; NeuralForecast deep experiments are optional and benchmarked against CPU/DRAM/time cost before GPU expenditure.
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

## 15. Explicit owner decision requested before implementation

**Proposed adoption decision:** approve **M0 → M1 → M2 → M3** as the core, cross-market evidence/forecast programme and **M5** as a separate read-only crypto safety research track. Do **not** authorize a new live crypto venue, on-chain signing wallet, capital mandate increase or agent trade permission as part of that decision. M4/M6/M7/M8 follow results, capability admission and measured ROI.

**Default recommendation:**

1. Keep VAN's existing deterministic trading path and active Rev 4/Rev 5 authority unchanged.
2. Treat Qlib + LightGBM as the first model-adoption tranche, with NeuralForecast as a conditional challenger.
3. Put executable economics and counterfactual evidence *ahead of* new AI models.
4. Build a chain-aware fraud/exitability monitor as read-only defensive intelligence; do not promise automated profitable meme-coin sniping.
5. Use Jev, X/social and public prediction-market signals only after they clear a cost-adjusted matched-cohort ablation.
6. Admit into strategy capsules and modes only through VATI's existing staged evidence and owner approval.

**Success is:** a falsifiable, cost-aware, auditable improvement in **expected and realized net risk-adjusted trading performance** (or independently demonstrated defensive loss reduction), with **zero new order authority** outside the existing VAN trading core. This document recommends research/implementation priorities; it does not report work completed or certify future profitability.
