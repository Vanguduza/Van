# VAN Adaptive Trading Intelligence (VATI)
## Technical Blueprint & Development Plan — Revision 2

> **Status (2026-09-16):** consolidated into `docs/VAN_TRADING_SYSTEM_BLUEPRINT_REV4_CONSOLIDATED.md`, which is now the active authority. This revision is retained as provenance and detailed rationale.


**Revision:** 2.1 (Rev 2.0 + Part E Industry Integration Architecture)  
**Date:** 2026-09-16  
**Status:** Proposed Canonical Architecture / Development Authority Candidate. Becomes locked authority only on owner acceptance (A4). Supersedes Rev 1 for active intent; Rev 1 is retained verbatim as provenance at `docs/archive/VAN_ADAPTIVE_TRADING_INTELLIGENCE_TECHNICAL_BLUEPRINT_REV1.md`.  
**Product:** VAN — DIAL owner-facing assistant, Hermes profile `van`  
**Scope:** Forex majors, major indices, metals, MetaTrader 5, Deriv, research intelligence, adaptive strategy selection, deterministic risk, execution, learning and owner-facing trading UX.  
**Parent authority:** `docs/PROJECT_TRUTH_PROTOCOL.md`, `docs/SECURITY_POLICY.md`, `hermes/profile/van/SOUL.md`. VAN remains a Hermes bot; Hermes remains the sole agent runtime; deterministic risk and execution controls outrank model opinion.  
**Owner direction recorded 2026-09-16:** VAN trader is a new project integrated into the existing Van product. It borrows DIAL's VEKL *infrastructure* (resolver, registries, manifests, snapshot substrate) rather than only its pattern; a dedicated VEKL instance for trading may be created later if evidence shows it improves trading output and performance (Part E §E.4).  
**Delivered with this revision (Phase 0):** `trading/vati/risk` deterministic Risk Authority, `trading/vati/contracts/schemas` core event contracts, `trading/tests` (unit, fail-closed and property fuzz), `trading/tools/induce_gate_failures.py`, `hermes/skills/trading-intelligence`, trading prohibitions in `hermes/policy/van_policy_hook.py`; **Rev 2.1 adds** `trading/architecture/stack_lock.json` (machine-checked tool-per-layer lock), `trading/vtil/registry` (VTIL seed registry in DIAL VEKL schema) and `trading/vtil/tools/resolve_probe.mjs` (DIAL's unmodified resolver running against it).

---

# Part A — Expert review of Revision 1

Rev 1 is a strong doctrine document. Its four load-bearing ideas are correct and Rev 2 keeps them unchanged: **NO_TRADE is a valid output**, the objective is **net expectancy after costs and risk**, **macro backtests use point-in-time vintages**, and **Deriv synthetics are isolated from real-world causality**. The Strategy/Horizon Arbiter split, meta-labelling, champion/challenger, TCA feedback and the falsification laboratory are all retained.

Rev 1's weaknesses are of one kind: it states principles as prose where an autonomous system needs enforceable contracts. Reviewed as a trading system, as a VAN/Hermes component, as a VEKL consumer and as an AI system, thirty findings follow. Severity is the consequence of shipping Rev 1 as written.

| ID | Severity | Finding in Rev 1 | Rev 2 disposition |
|---|---|---|---|
| F-01 | CRITICAL | No mapping from trading actions to VAN action classes. `AUTONOMOUS_LIVE` is irreconcilable with the VAN rule that irreversible actions are A4 unless the mandate is itself the grant. | §37: the owner-signed mandate is a scoped capability grant; intents under it are A3; mode escalation, mandate/ceiling changes and kill-switch reset are A4; forbidden behaviours are A5. Enforced in `van_policy_hook.py`. |
| F-02 | CRITICAL | Sizing multipliers are "bounded" but not bounded ≤ 1. Confidence × regime × volatility can compound *above* the mandate. | §27.1: every multiplier is clamped into [0, 1]; intelligence may only reduce risk. Enforced in `vati/risk/sizing.py`; property P1/P2. |
| F-03 | CRITICAL | The sizing formula ignores venue truth: lot step, min/max volume, stops level, freeze level, trade mode. No rounding rule. | §5.2 `SymbolContract` is venue truth captured at sync; §27.1 rounds **down** to the step, below-minimum is `NO_TRADE`. Property P5. |
| F-04 | CRITICAL | Deriv contracts (Rise/Fall, Multipliers, Accumulators, Turbos, Vanillas) have no stop distance; Rev 1's single formula cannot size them. | §20 and §27.1: `LossModel.FULL_STAKE` branch where stake = maximum loss; synthetic default posture is `OBSERVE`. |
| F-05 | CRITICAL | Rev 1 treats DIAL's VEKL as the trading memory. DIAL VEKL v2 (`DEC-020`) is *engineering* knowledge for development and states it is "not business-runtime intelligence". | §6: VTIL is a VAN-owned runtime knowledge layer that adopts VEKL v2 governance (trust tiers, admission, activation manifest, Sol/Sonnet symmetry) as a separate registry. VATI *development* still uses DIAL VEKL normally. |
| F-06 | HIGH | Source tiers A–D conflict with VEKL v2 tiers T0–T4 and omit the owner mandate as T0. | §9: T0–T4 mapping aligned with VEKL v2. |
| F-07 | HIGH | "Currency exposure" is named but undefined; EURUSD long + USDJPY short is a doubled USD short that Rev 1 would not see. | §27.2 currency-leg netting formula; enforced in `vati/risk/heat.py`; property P4. |
| F-08 | HIGH | No rule for a protective stop that is rejected after the entry fills; a position can exist unprotected. | §28: stop attached atomically where the venue allows; unconfirmed stop → immediate flatten + `STOP_REJECTED` kill trigger; an unprotected open position blocks all new risk. |
| F-09 | HIGH | No latency tiers. "Research is asynchronous" but nothing forbids an LLM in the scalp loop. | §3.4 decision-loop tiers T0–T3 with TTLs; LLM output is an input to the meta-labeller only for horizons ≥ INTRADAY. |
| F-10 | HIGH | No custody/account identity model: who holds funds, how an account is proven, netting vs hedging mode. | §43.1: broker holds custody, VAN never; one mandate per `account_alias`; unverified account = kill trigger; account mode captured. |
| F-11 | HIGH | Reconciliation ignores owner manual intervention in the broker terminal. | §44: `OWNER_OVERRIDE` reconciliation class; owner-closed positions are learning events, never re-opened. |
| F-12 | HIGH | Meta-labelling has no label definition and no calibration requirement; an uncalibrated probability used as a multiplier is a hidden leverage knob. | §22: triple-barrier labels, uniqueness-weighted samples, purged/embargoed CV, calibration gate (Brier, ECE) before any probability may reduce or gate size. |
| F-13 | HIGH | Falsification lab lacks the tests that actually catch overfitting. | §26: deflated Sharpe ratio, probability of backtest overfitting (CSCV), minimum trades per regime, trial ledger for multiple-testing correction. |
| F-14 | MEDIUM | Event engine is NFP-only. | §14: generic Tier-1 event matrix per instrument, dual-source release-time verification, NFP as the first specialist. |
| F-15 | MEDIUM | Weekend/holiday/rollover, triple swap and gap-through-stop risk are absent. | §4.5 session calendars; §27.3 weekend gap counted as tail risk; mandate `weekend_hold_allowed`. |
| F-16 | MEDIUM | Constant spread in the cost model. | §30: spread curve by session-time and event proximity; slippage conditioned on volatility and size. |
| F-17 | MEDIUM | Data quality contract has no freshness gate tied to risk and no dual-feed cross-check. | §4.2 `quote_age_ms` versus per-horizon maximum; §31 cross-feed divergence drives integrity state. |
| F-18 | MEDIUM | News text, chart images and TradingView alerts are prompt-injection vectors and are not labelled. | §8.4 and §10: all market content is `untrusted_content`; features only; may never raise risk or carry instructions. |
| F-19 | MEDIUM | Strategy decay demotion has no hysteresis; strategies would flap between `CERTIFIED_LIVE` and `DEGRADED`. | §25: health score formula and hysteresis bands. |
| F-20 | MEDIUM | No clock authority. | §4.3: NTP discipline, broker server-time offset, `TIME_SYNC_FAULT` trigger. |
| F-21 | MEDIUM | Service names are `vatii-*` (typo) and inconsistent. | §40: `vati-*`. |
| F-22 | MEDIUM | No decision-replay requirement; audit answers "why" from logs rather than from reproducible inputs. | §42 and §59: every decision is reproducible from the ledger and its hashes. |
| F-23 | MEDIUM | Owner interaction is described without mapping to the existing VAN gateway engines. | §36: decisions, attention and audit engines carry approvals, alerts and evidence. |
| F-24 | LOW | Capital scaling has no numeric step law. | §56: bounded step, minimum live sample, automatic step-down. |
| F-25 | LOW | Milestones carry no Feature IDs, so DIAL context tooling cannot address them. | Part C: `VATI-F000`…`VATI-F015`. |
| F-26 | LOW | The MT5 Python API is Windows-only; Rev 1's "isolated MT5 worker" does not say so. | §5.2: Windows worker behind an mTLS bridge; Linux core never links the MT5 library. |
| F-27 | MEDIUM | Kill switch is software-only. | §27.4: two planes: software halt plus broker-side hard stops on every position plus a pre-armed owner flatten-all. |
| F-28 | MEDIUM | Correlation multiplier undefined. | §27.2: factor-cluster table. |
| F-29 | LOW | No demo/live parity metric before capital steps. | §56: modelled versus realised cost within tolerance. |
| F-30 | HIGH | No requirement that gates be *broken deliberately* before being trusted, and no Feature-level acceptance contract. | Part C gates each require induced-failure evidence; Part D records it for Phase 0. |

---

# Part B — Revision 2 canon

## 0. Executive summary

VATI is a multi-market, multi-horizon, regime-adaptive trading system whose defining capability is knowing when *not* to trade. It is not a retail bot, not a fixed indicator strategy, not a next-candle predictor and not an LLM wired to a broker.

```text
                              OWNER
                                │  signed mandate (A4)
                              VAN  ── gateway: decisions / attention / audit
                                │
                             HERMES ── profile van, skill trading-intelligence
                                │
                  VAN ADAPTIVE TRADING INTELLIGENCE
                                │
        ┌───────────────────────┼─────────────────────────┐
   MARKET BRAIN            RESEARCH BRAIN             RISK BRAIN
   regimes / macro         VTIL (VEKL-pattern)        mandate / ceilings
   rates / options         GraphRAG analogues         portfolio heat / legs
   charts / order flow     strategy R&D               drawdown governor
   positioning / news      historical vintages        margin / tail risk
        └───────────────────────┼─────────────────────────┘
                        STRATEGY ARBITER
                        HORIZON ARBITER
                          META-LABELLER
                       OPPORTUNITY MODEL  ──►  TradeIntent
                                │
              ══════ DETERMINISTIC RISK AUTHORITY ══════  ◄── the only sizer
                                │  RiskDecision (sealed)
                       EXECUTION ROUTER
                   ┌────────────┴────────────┐
             NAUTILUS RUNTIME           DERIV ADAPTER
                   │                         │
              MT5 BRIDGE (mTLS)           Deriv API
                   │
          Windows MT5 worker → terminal → broker
```

No component may bypass the Risk Authority to place an order. No model output is an order.

## 1. Product doctrine

### 1.1 Mission
Identify and exploit robust market opportunities while controlling capital loss, model error, execution error, data error and regime change. A correct outcome is often `NO_TRADE`.

### 1.2 Objective

```text
Expected Net Edge = Expected Gross P&L
                  − spread − commission − expected slippage − financing/swap
                  − market impact − execution uncertainty
                  − tail-risk penalty − drawdown penalty
```

Optimise long-run risk-adjusted net expectancy. Never win rate, trade count, leverage or an unstressed backtest.

### 1.3 Trading authority order

```text
OWNER MANDATE (signed, versioned)
   ↓
PLATFORM RISK CEILINGS (owner-signed policy version)
   ↓
DETERMINISTIC RISK AUTHORITY
   ↓
DATA INTEGRITY + MARKET INTEGRITY GATES
   ↓
VENUE / BROKER CONSTRAINTS (symbol truth)
   ↓
CERTIFIED STRATEGY RULES (signed capsule)
   ↓
HERMES / VAN ANALYSIS
   ↓
EXECUTION
```

The model may recommend, explain and orchestrate research. It may never override maximum risk, heat, leg exposure, margin, drawdown gates, stale-data gates, kill switches, forbidden instruments, account mandates or venue constraints. This order is now written into `hermes/profile/van/SOUL.md`.

## 2. Trading disciplines

Fourteen expert disciplines (Rev 1 §2.1) remain the discipline vocabulary. Two are re-scoped:

- **Deriv Synthetic Markets** is a research discipline by default. Deriv synthetics are house-generated processes with a fixed-payout structure whose expected value is negative by construction; a synthetic strategy may enter `DEMO` only after a statistically significant edge over the payout ratio is shown (§20).
- **FX Scalping / Microstructure** may not certify on bar data and may not use LLM output in-loop (§3.4, §4.4).

### 2.2 Horizon Arbiter

```text
MICRO      seconds → minutes       Tier-0 only
SCALP      minutes                 Tier-0 / Tier-1 only
INTRADAY   minutes → hours         Tier-2 input allowed (TTL ≤ 15 min)
SESSION    session-bound           Tier-2 input allowed (TTL ≤ 60 min)
OVERNIGHT  cross-session           Tier-2 input allowed
SWING      hours → days            Tier-2 / Tier-3 input allowed
POSITION   multi-day / macro       Tier-2 / Tier-3 input allowed
```

Selection inputs: forecast quality, spread relative to expected move, volatility, session liquidity, event proximity, model stability, financing, market structure, fill probability, signal decay. Hard rule: **expected move must exceed k × (spread + expected slippage)** with `k ≥ 3` for SCALP and `k ≥ 5` for MICRO; otherwise the horizon is ineligible.

## 3. Market operating model

### 3.1 MarketState
As Rev 1 §3, plus mandatory fields:

```yaml
MarketState:
  ...
  integrity_state: NORMAL | ELEVATED | ABNORMAL | HALTED
  data:
    primary_feed: {source_id, quote_age_ms, hash}
    reference_feed: {source_id, quote_age_ms, hash}
    divergence_bp: 0.4
  clocks:
    ntp_offset_ms: 3
    broker_server_offset_ms: 118
  activation_id: vtil-act-...      # VTIL knowledge used to build this state
  state_hash: ...
```

### 3.2 Regime dimensions and transitions
Unchanged from Rev 1 §3.1–3.2. `NORMAL → CAUTION → TRANSITION → NEW_REGIME`; capital reduces before new strategies are promoted. Transition detection is a bounded ensemble (Bayesian change-point, state-space, volatility breaks, feature drift, correlation breaks, residual drift, disagreement).

### 3.4 Decision-loop tiers (new)

| Tier | Latency | Components | May produce |
|---|---|---|---|
| T0 | ≤ 10 ms | Risk Authority, execution gate, kill switch, integrity state machine, deterministic strategy rules | orders, halts |
| T1 | ≤ 1 s | statistical models, regime probabilities, calibrated meta-labeller, order-flow features | `OpportunityAssessment` |
| T2 | seconds → minutes, asynchronous | Hermes reasoning (Sonnet 5), Gemini multimodal chart reading, confidence matrix | assessment inputs with TTL |
| T3 | hours, asynchronous | Deep Research, NotebookLM, Qlib/Optuna research, VTIL admission | research packets, hypotheses |

A T2/T3 output carries `produced_at`, `ttl` and `activation_id`. The meta-labeller discards expired inputs; it never "reuses the last opinion". T0 never waits on T1+; if a T1 input is absent, the decision is `NO_TRADE`.

## 4. Market data architecture

### 4.1 Data classes
As Rev 1 §4.1.

### 4.2 Data quality contract
Rev 1 fields plus `quote_age_ms`, `max_quote_age_ms` (per horizon: MICRO 250 ms, SCALP 500 ms, INTRADAY 1 500 ms, SESSION+ 5 000 ms), `reference_source_id`, `divergence_bp`. The Risk Authority rejects any intent whose snapshot fails `0 ≤ quote_age_ms ≤ max_quote_age_ms` (`STALE_DATA`).

### 4.3 Time semantics and clock authority
Event time, received time and decision time remain distinct. The core runs NTP-disciplined time; each venue adapter measures broker server-time offset on every heartbeat. `|ntp_offset| > 250 ms` or `|broker_offset − baseline| > 2 s` trips `TIME_SYNC_FAULT`.

### 4.4 Data granularity
Bars → ticks → L1 → L2 → L3. A `StrategyCapsule` declares `required_data_granularity`; SCALP/MICRO capsules cannot certify with `BARS`.

### 4.5 Session calendars (new)
Every instrument has a session calendar: trading hours, daily rollover, triple-swap day, holidays, early closes, Deriv 24/7 synthetics. Intents that would hold through a closed session are `holds_over_weekend` and require the mandate flag.

## 5. External trading and research ecosystem

All external components are donors subject to licence, entitlement, security and version review. **Exact versions are established through Context7/official releases at adoption time**, never recalled.

### 5.1 NautilusTrader — trading kernel
Event-driven strategy runtime, deterministic simulation, order/position domain model, live host abstraction. Wrapped behind VAN-owned interfaces (`trading/backtest`, `trading/execution/core`) so framework changes never become canon. Its own documentation warns that bars cannot model spread, depth, queue position or intrabar order; VATI adopts that as the §4.4 rule.

### 5.2 MetaTrader 5
The official MT5 Python integration runs on Windows against a running terminal. Architecture:

```text
VATI Linux core
   │ private network, mTLS, allowlisted identity, signed + idempotent requests, replay protection
isolated Windows MT5 worker (no public listener)
   │ MetaTrader5 Python API
MT5 terminal → broker
```

The worker exposes a narrow typed contract: `sync_account`, `sync_symbols`, `order_check`, `order_send`, `positions`, `orders`, `history`, `modify_sl_tp`, `close`. `sync_symbols` produces `SymbolContract` records (contract size, tick size/value, volume min/step/max, stops/freeze level, trade mode, filling modes, swaps, margin) with `spec_hash`. Netting versus hedging account mode is captured at `sync_account` and changes position-identity semantics (§44). Every order carries a magic number and comment that encode `trade_intent_id`.

### 5.3 Deriv
Dedicated adapter: OAuth/PAT, REST account/service operations, authenticated WebSocket market/trading, normalised contract models, strict real-market versus synthetic classification, contract-type mapping to `LossModel`:

| Deriv product | LossModel | Notes |
|---|---|---|
| Rise/Fall, Higher/Lower, Touch, Digits | FULL_STAKE | fixed payout; stake is max loss |
| Multipliers | FULL_STAKE | loss capped at stake by product stop-out; optional TP/SL inside stake |
| Accumulators | FULL_STAKE | knock-out; stake is max loss |
| Turbos / Vanilla options | FULL_STAKE | premium is max loss |
| CFDs (Deriv MT5) | STOP_DISTANCE | via the MT5 path |

### 5.4 cTrader — optional future venue. Not before MT5/Deriv are stable.

## 6. VEKL Trading Intelligence Layer (VTIL)

### 6.1 Boundary (corrects F-05)
DIAL's VEKL v2 (`DEC-020`/`DEC-024`) governs *engineering* knowledge for building software and explicitly excludes business-runtime intelligence. VTIL is therefore:

- a **VAN-owned runtime knowledge layer** under `trading/vtil/`, with its own resource registry, admission ledger and activation manifests;
- built on the **same governance pattern** as VEKL v2: trust tiers, passive-versus-executable paths, hard eligibility before ranking, minimal coalition, one activation ID/hash per decision, Sol/Sonnet symmetry, learning loops kept separate from truth;
- never a second architect. VTIL may influence knowledge, confidence and certified strategy selection; no VTIL result can place a trade, change a mandate or promote a strategy.

Developing VATI itself continues to use DIAL's engineering VEKL through the Oracle packet flow; the two registries never cross-populate.

### 6.2 Knowledge classes
`MARKET_OBSERVATION`, `EVENT_OBSERVATION`, `TRADE_EXPERIENCE`, `CHART_FINGERPRINT`, `REGIME_KNOWLEDGE`, `STRATEGY_EVIDENCE`, `STRATEGY_CAPSULE`, `RESEARCH_PACKET`, `ANTI_PATTERN`, `DURABLE_MARKET_KNOWLEDGE`, `CAUSAL_HYPOTHESIS`, `COUNTERFACTUAL_RESULT`, plus `EXECUTION_EXPERIENCE` (TCA-derived) and `DATA_SOURCE_RECORD`.

### 6.3 TradeExperienceArtifact
Rev 1 §6.2 fields plus `activation_id`, `risk_decision_hash`, `execution_receipt_hash`, `mandate_version`, `polarity`, `admission_state` (`PROPOSED | QUARANTINED | VALIDATED | ADMITTED | REJECTED | SUPERSEDED`) and `admitted_by` (never the model that proposed it).

### 6.4 Polarity, decay, freshness
As Rev 1 §6.3–6.4. A bad win is an anti-pattern; a correctly executed loss is positive process evidence. Confidence decays with `decay_rate`; `valid_regimes` gate retrieval.

### 6.5 Trust tiers (aligned with VEKL v2, corrects F-06)
See §9.

### 6.6 Trading Knowledge Activation Manifest
For every `OpportunityAssessment` and every research packet, VTIL persists one manifest: instrument, horizon, regime, task class; selected knowledge IDs with class, tier, freshness, `selection_role` (`AUTHORITY | GUIDANCE | ANALOGUE | ANTI_PATTERN | VERIFIER | REFERENCE`) and reason; rejected/pruned candidates; registry fingerprint; manifest hash; previous activation and re-resolution reason. The `activation_id` travels in `MarketState`, `TradeIntent` and the `TradeExperienceArtifact`, so every trade can name the knowledge that shaped it. Sol and Sonnet (or Sonnet and Gemini as specialist) receive the same manifest; a failover cannot silently change knowledge identity.

### 6.7 Learning loops
Two loops, kept separate as in VEKL v2: (1) knowledge-selection learning (which analogues/evidence helped which task class); (2) procedural learning (execution and review procedures). Neither writes truth, mandates or capsules.

## 7. GraphRAG historical analogue engine
Nodes and relationships as Rev 1 §7, plus `ActivationManifest`, `Mandate` (reference only) and `Venue`. Every correlation edge stores window, regime, confidence, `last_validated_at` and `decay_rate`. Analogue retrieval returns a bounded coalition (≤ 12 analogues) with similarity, regime match and outcome distribution; it never returns a direction.

## 8. Google tool integration
Routed only through `registries/google_capabilities.json` and the gateway planner (`/v1/google/jobs/plan`), as `docs/GOOGLE_INTELLIGENCE_MESH.md` requires.

- **Gemini** (`gemini`): chart-image interpretation, multimodal comparison, structured extraction. Output is T2, untrusted, and must be verified against trusted numeric data before it can inform an intent (§10).
- **Deep Research** (`deep_research`): macro-regime, policy-cycle, gold/rates, strategy literature, event post-mortems. `Deep Research → ResearchPacket → VTIL quarantine → claim extraction → validation → admission → hypothesis → test`.
- **NotebookLM** (`gemini_notebook`): specialist notebooks (EURUSD Macro, USDJPY/BoJ, Gold, US Indices, NFP/Labour, Inflation, Central-Bank Language, Execution/Microstructure). A research workspace; VTIL remains machine-operational memory.
- **8.4 Untrusted content rule.** Every Google output, news item, calendar entry, chart image, forum post, TradingView alert and broker message is `untrusted_content`. It may become a feature after validation; it may never carry instructions, raise risk, or alter a mandate, capsule or ceiling.

## 9. Source governance (aligned with VEKL v2)

| Tier | Contents | Posture |
|---|---|---|
| **T0** | owner mandate, platform ceilings, VAN trading policy, signed capsules | authority (owner-signed) |
| **T1** | central banks, statistical agencies, exchanges/venues, regulators, broker execution records, official vendor documentation | primary market truth; preferred for facts, releases, contract specs |
| **T2** | licensed market-data vendors, approved economic-data providers, maintainer documentation | structured data; verify consequential claims against T1 |
| **T3** | peer-reviewed and reputable institutional research | hypothesis and method source; never a trading signal by itself |
| **T4** | forums, social media, YouTube, public commentary | discovery signal only; can create a hypothesis, never canon |

Admission pipeline: `SOURCE → QUARANTINE → CLASSIFICATION → CLAIM EXTRACTION → CROSS-SOURCE CHECK → HISTORICAL/MARKET VALIDATION → VTIL ADMISSION`. T4 cannot skip any stage. No research payload may contain broker credentials, account identifiers, owner identity or position data (§43).

## 10. Chart intelligence
As Rev 1 §10 (structure, levels, sweeps, compression, divergence, VWAP, profile, indicators-as-features). Additions: a `ChartSetupFingerprint` produced from an image (Gemini) is `unverified` until each numeric claim (level, swing, session high/low) matches trusted price data within tolerance; unverified fingerprints can be stored as observations but cannot enter an `OpportunityAssessment`. Screenshot-only signals can never trade (Phase 7 gate).

## 11. Cross-asset causal/dependency graph
As Rev 1 §11. Every edge is a time-varying hypothesis with sign, beta, window, regime, confidence, last validation and decay. Deriv synthetics have no inbound edges from real-world nodes (§20).

## 12. Volatility and options intelligence
As Rev 1 §12. Additional rule: when `implied ≫ realised` inside an event window, `event_risk_multiplier ≤ 0.5` unless the capsule is `event_certified`; when `realised ≫ implied`, `liquidity_multiplier ≤ 0.5` and integrity state may move to ELEVATED.

## 13. Order flow and microstructure
As Rev 1 §13. A single broker DOM is never total FX liquidity (A5 pattern `single_dom_as_total_fx_liquidity` in the mandate forbidden list). Futures references (ES, NQ, GC, SI) may inform CFD/spot trades subject to basis and venue differences.

## 14. Event engine (generalised) and NFP specialist
A Tier-1 event matrix per instrument: NFP, CPI, PCE, FOMC decision/minutes/pressers, ECB/BoE/BoJ/SNB/RBA/BoC decisions, GDP, ISM/PMI flash, retail sales, claims (when elevated), Treasury refunding, index rebalances/opex, central-bank speeches on watch lists. Each row: blackout window, allowed capsule set, size multiplier, dual-source release timestamp verification (agency schedule versus vendor calendar; disagreement → blackout extends). Rev 1 §14 pre-event timeline, `NFPShockVector`, `NFPReactionVector`, strategy families and the point-in-time macro rule are retained unchanged as the NFP specialist.

## 15. Central-bank language intelligence, 16. Positioning, 17. Gold, 18. FX, 19. Indices
Unchanged from Rev 1 §15–19. Weekly positioning is never a scalping trigger.

## 20. Deriv architecture
Real-market products use market features subject to product mechanics. Synthetic indices are isolated: product mechanics, tick statistics, specified volatility, serial properties, contract payoff, execution and risk only. Real-world macro events are not causal inputs for synthetics.

**Synthetic edge gate (new).** A synthetic strategy may leave `RESEARCH` only when, on out-of-sample ticks, its realised expectancy exceeds the product payout ratio with `p < 0.01` after multiple-testing correction, across at least 1 000 contracts and two volatility products. Absent that, the discipline stays in `OBSERVE`. Martingale and staircase staking, common in the Deriv bot ecosystem, are A5.

## 21. Strategy architecture
`StrategyCapsule` (schema delivered) adds `discipline`, `required_data_granularity`, `event_certified`, `synthetic_only`, `health_score`, `approval_signature_ref`, `supersedes`, `capsule_hash`. States: `RESEARCH → BACKTEST → VALIDATION → DEMO → SHADOW → LIMITED_LIVE → CERTIFIED_LIVE`, with `DEGRADED`, `SUSPENDED`, `RETIRED`. Mode/state eligibility is enforced by the Risk Authority:

| Mode | Eligible capsule states |
|---|---|
| DEMO_TRADER | DEMO, SHADOW, LIMITED_LIVE, CERTIFIED_LIVE |
| LIMITED_LIVE | LIMITED_LIVE, CERTIFIED_LIVE |
| AUTONOMOUS_LIVE | CERTIFIED_LIVE only |

Champion/challenger as Rev 1 §21. A capsule promotion is an owner-signed A4 action with the certification checklist (§52) attached as evidence.

## 22. Meta-labelling and opportunity selection
A base strategy proposes direction and setup. The meta-labeller decides `TRADE | WAIT | SKIP | REDUCE_SIZE | REQUIRE_CONFIRMATION`.

**Labels:** triple-barrier (profit barrier, stop barrier, time barrier) on the base strategy's own stop/target model, producing `{+1, 0, −1}` and realised R. **Samples:** overlapping outcomes are weighted by uniqueness; training uses purged, embargoed cross-validation. **Calibration gate:** before a probability may act as `confidence_multiplier` or gate a trade, its out-of-sample Brier score must beat the base rate and expected calibration error must be ≤ 0.05 per regime bucket. An uncalibrated model is `RESEARCH` regardless of accuracy.

Inputs: regime fit, event proximity, spread percentile, volatility, analogue quality, cross-market confirmation, model agreement, recent capsule health, order flow, execution conditions, T2 assessment (if fresh).

## 23. Ensemble and model governance
No single oracle. Deterministic rules, statistical models, supervised ML, regime models, probabilistic models, LLM reasoning and analogue retrieval are weighted by recent calibration, regime, horizon, data quality and freshness. Disagreement is a feature: `model_disagreement > 0.35` sets `confidence_multiplier ≤ 0.5`; `> 0.6` forces `WAIT`.

## 24. Uncertainty and abstention
`OpportunityAssessment` as Rev 1 §24 plus `activation_id`, `inputs_fresh` and `abstain_reason`. VATI abstains when uncertainty, disagreement, integrity, event risk or cost invalidates an otherwise attractive signal.

## 25. Concept drift and strategy half-life
Tracked drifts as Rev 1 §25. **Health score** `H ∈ [0,1]` is the equal-weighted mean of: rolling expectancy versus certified expectancy, calibration versus certified calibration, cost-drift ratio, regime-fit share, and drawdown versus certified worst drawdown, each clipped to [0,1] over the last max(60 trades, 30 days). **Hysteresis:** `CERTIFIED_LIVE → DEGRADED` at `H < 0.55` sustained for 20 trades; `DEGRADED → SHADOW` at `H < 0.40`; recovery `DEGRADED → CERTIFIED_LIVE` requires `H ≥ 0.70` for 40 trades *and* owner acknowledgement. Demotion is automatic; promotion never is.

## 26. Backtesting and validation
Bias controls and validation stack as Rev 1 §26. Falsification laboratory additions: deflated Sharpe ratio adjusted for the number of trials recorded in the trial ledger; probability of backtest overfitting via combinatorial symmetric cross-validation (`PBO ≤ 0.10` to pass); parameter-perturbation stability (±20 % on every parameter must keep expectancy positive); minimum 200 out-of-sample trades and ≥ 30 per claimed eligible regime; cost stress at 2× modelled spread/slippage; latency stress at +250 ms; broker/feed variation. Every trial, including failures, is retained.

## 27. Deterministic Risk Authority (delivered: `trading/vati/risk`)

### 27.1 Per-trade sizing

```text
RiskCapital     = Equity × min(RequestedRiskPct, Mandate.max_risk_per_trade)
RawSize         = RiskCapital / (StopDistance × ValuePerPriceUnitPerLot)
Product         = Π clamp[0,1](regime, confidence, volatility, liquidity, event_risk, correlation, drawdown)
AdjustedSize    = RawSize × Product
FinalSize       = round_down(AdjustedSize, Venue.volume_step), capped at Venue.volume_max
if FinalSize < Venue.volume_min → NO_TRADE (never round up)
RealisedRisk    = FinalSize × StopDistance × ValuePerPriceUnitPerLot   (re-checked ≤ RiskCapital)
```

For `FULL_STAKE` contracts: `Stake = round_down(min(RiskCapital × Product, requested_stake, Venue.max_stake), step)`; the stake is the maximum loss.

Multipliers may only reduce. Values above 1, negative, non-finite or unparseable are clamped to 1, 0, 0 and 0 respectively. Stop must be on the correct side of entry and at least `SymbolContract.min_stop_distance` away.

### 27.2 Portfolio heat and currency legs

```text
position_risk(p)   = lots × stop_distance × value_per_price_unit   (∞ if no broker-side stop)
open_stop_risk     = Σ position_risk / equity                        ≤ Mandate.max_open_stop_risk
leg[BASE]         += sign × position_risk ;  leg[QUOTE] −= sign × position_risk   (sign = +1 LONG, −1 SHORT)
currency_leg_exposure[c] = |leg[c]| / equity                          ≤ Mandate.max_currency_leg_exposure
```

An open position without a broker-side stop makes heat infinite and blocks all new risk until protection is restored. Factor clusters (USD, rates, equity beta, real yields, volatility, regional, event concentration) drive `correlation_multiplier`: 2 positions in a cluster → 0.75, 3 → 0.5, 4+ → 0.

### 27.3 Drawdown governor
Owner-configurable strictly increasing tiers ending in suspension; defaults `2 % → ×0.75`, `4 % → ×0.40 top-tier only`, `6 % → suspend`. Daily loss ≥ mandate, weekly drawdown ≥ mandate or consecutive losses ≥ mandate reject new intents until the period resets or the owner acknowledges. Weekend gap risk is counted in the tail penalty of any `holds_over_weekend` intent.

### 27.4 Kill switch (two planes)
Triggers: max daily/weekly loss, equity drawdown, stale data, reconciliation failure, abnormal spread, reject storm, duplicate-order risk, time-sync fault, corrupt state, unauthorised account, venue disconnect, risk-store unavailable, stop rejected, owner halt. The switch latches; clearing is owner-signed A4. Plane 1: software halt on new orders. Plane 2: every open position already carries a broker-side hard stop, and the owner device holds a pre-armed `FLATTEN_ALL` (A4, biometric) that the adapter executes without consulting any model.

### 27.5 Evaluation order (fixed, fail-closed)
kill switch → account identity/venue → mandate validity and mode → duplicate intent → data freshness → venue connectivity → reconciliation → clock → risk store → market integrity → unprotected positions → instrument/strategy/state/trade-mode eligibility → event and weekend policy → consecutive losses, daily loss, weekly drawdown, drawdown governor → position counts → allowed risk = min(requested, mandate) → multipliers → sizing → heat after → legs after → final invariant re-check → sealed `RiskDecision`. The first failing check names the reason; later checks are not consulted. The execution router calls `evaluate_safe`, so an internal fault is a `REJECTED/AUTHORITY_FAULT` decision, never an exception.

### 27.6 Platform ceilings
`PlatformCeilings` (per trade 2 %, open heat 6 %, daily 5 %, weekly 10 %, leg 4 %; `risk-policy/2.0.0`) sit beneath the mandate: a mandate asking for more is rejected at load, never widened. Ceilings change only through an owner-signed policy version (A4).

## 28. Trade protection and exit intelligence
Supported exits as Rev 1 §28. Canonical: strategy exit logic **plus** broker-side catastrophe protection. Rules: the protective stop is sent in the same request as the entry where the venue supports it; otherwise it is sent immediately after fill and the position is `UNPROTECTED` until the venue confirms it. `ExecutionReceipt.protective_stop_confirmed = false` → immediate flatten, `STOP_REJECTED` trip, incident review. VATI never widens a mandatory protective stop because a trade is losing (A5 `widen_protective_stop`). Trailing and break-even moves only tighten.

## 29. Execution intelligence
Methods and execution gate as Rev 1 §29. Idempotency: every intent carries `trade_intent_id`, `idempotency_key`, `decision_hash`, `risk_snapshot_hash`, `market_snapshot_hash`, `activation_id`; the router refuses any intent without a matching `APPROVED|REDUCED` decision whose `decision_hash` it can recompute, and refuses any key it has seen. Venue order identity (magic number/comment on MT5, `passthrough` on Deriv) encodes the intent ID so reconciliation is exact.

## 30. Transaction cost analysis
Per-fill metrics as Rev 1 §30 (decision, arrival, submitted, fill prices; spread, slippage, delay, fees, swap, adverse selection, implementation shortfall). The cost model is a **spread curve** by instrument × session-minute × event proximity, and a slippage model conditioned on volatility percentile and size relative to visible depth. TCA produces `EXECUTION_EXPERIENCE` artifacts for VTIL.

## 31. Market integrity / abnormal conditions
Detectors as Rev 1 §31 plus cross-feed divergence. State machine `NORMAL → ELEVATED → ABNORMAL → HALTED`. The Risk Authority halves size in ELEVATED and rejects in ABNORMAL/HALTED. Use "abnormal market state", never claims of manipulation.

## 32. Real-time learning boundaries
Live adaptation may change certified strategy weights, regime probabilities, confidence, risk multipliers (downward) and suspension state. It may not invent a strategy and trade it, widen any limit, or alter a capsule. New strategies follow `HYPOTHESIS → RESEARCH → BACKTEST → FALSIFICATION → DEMO → SHADOW → LIMITED_LIVE → CERTIFIED_LIVE`.

## 33. Trade review and counterfactual learning
As Rev 1 §33. Classification `GOOD WIN | GOOD LOSS | BAD WIN | BAD LOSS | EXECUTION FAILURE | DATA FAILURE | RISK FAILURE`. Hermes proposes the review; VTIL admission is performed by the admission service, never by the proposing model.

## 34. Trading confidence matrix
As Rev 1 §34, with `activation_id`, input freshness and integrity state printed alongside.

## 35. VAN semantic trading visual states
As Rev 1 §35. Colours communicate operational state and risk, never emotion or stimulus. States bind to the deterministic state machine (integrity, mode, kill switch, open-position health), not to model sentiment.

## 36. Owner interaction model (mapped to VAN gateway)

| Event | Gateway engine | Owner surface |
|---|---|---|
| mandate proposal, capsule promotion, mode escalation, capital step, kill-switch clear | `decisions` (`/v1/decisions/escalate`, blocking) | A4 approval with biometric |
| drawdown tier change, integrity ELEVATED/ABNORMAL, stop rejected, reconciliation failure | `attention` (`BLOCKER`/`URGENT`) | Command Centre + overlay state |
| every intent, decision, receipt, reconciliation, review | `audit` with evidence pointer | audit timeline |
| trade summary, confidence matrix, "what would change the decision" | Hermes `trading-intelligence` skill | conversation / briefing |

The live trade summary format of Rev 1 §36 is retained and gains `Mandate`, `Decision hash` and `Activation` lines.

## 37. Authorisation modes and action classes

```text
OBSERVE → ADVISOR → DEMO_TRADER → SHADOW_TRADER → LIMITED_LIVE → AUTONOMOUS_LIVE   (HALTED at any time)
```

| Action | Class | Gate |
|---|---|---|
| read market/positions/risk/ledger/TCA | A1 | device auth |
| external research, Deep Research, NotebookLM, vendor data | A2 | capability grant |
| submit `TradeIntent` under an active mandate; adapter sends an approved order | A3 | mandate is the grant; policy hook |
| create/version a mandate; change platform ceilings; escalate mode; promote a capsule; capital step; clear kill switch; `FLATTEN_ALL` | A4 | explicit owner approval (biometric) |
| model sends/modifies/cancels a broker order; bypass Risk Authority; remove/widen protective stop; martingale/grid/revenge sizing; trade stale data or unverified account; broker token in a prompt | A5 | always deny (`van_policy_hook.py`) |

`AUTONOMOUS_LIVE` is therefore not "A4 per trade": the owner signs the mandate once (A4), and every trade inside it is A3 under that grant, bounded by ceilings the owner also signed.

## 38. Live trading mandate
Schema delivered (`trading_mandate.schema.json`; example in `trading/examples/`). Fields: identity and version, `account_alias`, venue, mode, instruments, allowed strategies, per-trade/open/daily/weekly/leg limits, consecutive-loss and position-count limits, tier-1 event policy, weekend policy, drawdown tiers, forbidden list (must be a superset of `HARD_FORBIDDEN_BEHAVIOURS`), owner signature reference, signed/expiry timestamps. Mandates are versioned, expiring and auditable; one active mandate per account alias.

## 39. Forbidden behaviours
Rev 1 list, now machine-enforced twice: as `HARD_FORBIDDEN_BEHAVIOURS` a mandate cannot omit, and as A5 patterns in the policy hook (`bypass_risk_authority`, `skip_risk_check`, `direct_broker_order`, `llm_broker_order`, `remove_stop_loss`, `remove_protective_stop`, `widen_protective_stop`, `stop_removal`, `martingale`, `unlimited_grid`, `unlimited_averaging_down`, `revenge_risk_increase`, `double_risk_after_loss`, `disable_kill_switch`, `trade_unverified_account`, `trade_stale_data`, `duplicate_order`, `silent_strategy_mutation`, `unvalidated_research_to_live`, `broker_token_in_prompt`). A5 is denied even with recorded owner approval.

## 40. System services

```text
vati-market-ingest      vati-market-state       vati-regime-engine      vati-chart-intelligence
vati-news-intelligence  vati-event-engine       vati-nfp-engine         vati-options-intelligence
vati-orderflow          vati-positioning        vati-strategy-registry  vati-strategy-arbiter
vati-horizon-arbiter    vati-meta-labeler       vati-opportunity-engine vati-risk-authority
vati-execution-router   vati-mt5-bridge         vati-mt5-worker (Windows) vati-deriv-adapter
vati-reconciliation     vati-tca                vati-trade-review       vati-vtil-admission
vati-graphrag           vati-research-orchestrator  vati-model-registry vati-observability
```

Initially modular packages/processes, not network microservices. `vati-risk-authority` is the only sizer; `vati-execution-router` is the only order sender.

## 41. Core event contracts (delivered as JSON Schema)
`TradingMandate`, `SymbolContract`, `RiskSnapshot`, `TradeIntent`, `RiskDecision`, `ExecutionReceipt`, `StrategyCapsule` under `trading/vati/contracts/schemas/`. All monetary and price values are decimal strings, never floats. `TradeIntent.owner_authority` admits only `MANDATE`. `ExecutionReceipt.protective_stop_confirmed` is mandatory.

## 42. Storage architecture
Hot state, append-only event ledger, Parquet market-data lake partitioned by `source/market/instrument/date/data_type`, VTIL store (admitted knowledge and lineage, not tick exhaust). **Decision replay:** given the ledger, any `RiskDecision` is reproducible from its `RiskSnapshot` and mandate version, and any `OpportunityAssessment` from its `MarketState` and activation manifest; replay divergence is an incident.

## 43. Security

### 43.1 Custody and identity
Funds are held by the broker/venue, never by VAN. VATI holds only trading permissions on owner-owned accounts. Accounts appear everywhere as aliases; raw logins, account numbers and tokens never appear in mandates, prompts, logs, artifacts or research payloads. An account whose identity, balance and positions cannot be verified at startup is unauthorised (`UNAUTHORIZED_ACCOUNT` kill trigger).

### 43.2 Credential planes
`MT5 account`, `Deriv OAuth/PAT`, `market data`, `Google research` (existing Google planes), `VAN owner identity`, `service identity`. No broker token enters an LLM prompt (A5 `broker_token_in_prompt`). MT5 boundary: private network, mTLS, allowlisted identity, signed requests, idempotency, replay protection, no public unauthenticated listener. Secrets remain encrypted, rotated and absent from Git.

## 44. Resilience and recovery
Startup: connect → read balance/equity → read positions → read pending orders → reconcile against the ledger → resolve uncertainty → permit new orders. Unverifiable market data or broker state → `NEW_TRADES_BLOCKED`. Reconciliation classes: `MATCH`, `VENUE_PARTIAL_CLOSE`, `VENUE_STOP_HIT`, `OWNER_OVERRIDE` (owner acted in the broker terminal: recorded as a learning event, never reversed by VATI), `ORPHAN_VENUE_POSITION` (protect with a hard stop, block new trades, escalate), `ORPHAN_LEDGER_POSITION` (mark closed-unknown, escalate). Hedging-mode accounts reconcile per position ticket; netting-mode accounts reconcile per symbol with intent attribution from deals.

## 45. Observability
Metrics as Rev 1 §45, plus induced-failure drill results, decision-replay divergence, calibration drift, activation-manifest coverage and unprotected-position seconds (target 0). Every trade correlates `market snapshot → activation → strategy decision → risk decision → execution receipt → reconciliation → trade result → review`.

## 46. Research tooling
OpenBB, Qlib, Optuna, Riskfolio-Lib, TradingView, order-flow tooling as Rev 1 §46: research candidates only, exact versions established at adoption via Context7/official releases, never execution authority.

## 47. Research integrity
Every experiment records code commit, dataset hash, data vintage, feature/model/strategy versions, parameters, seeds, cost model, result hash and the trial-ledger sequence number used for multiple-testing correction. Statuses as Rev 1 §47. All trials retained.

## 48. Performance metrics
As Rev 1 §48, plus deflated Sharpe, PBO, calibration (Brier/ECE), unprotected-position seconds and modelled-versus-realised cost ratio.

## 49. Repository layout

```text
trading/
├── README.md
├── vati/
│   ├── contracts/schemas/        # delivered
│   ├── risk/                     # delivered
│   ├── market_data/{ingestion,normalization,catalog,quality,calendars}
│   ├── intelligence/{regimes,macro,rates,options,chart,orderflow,positioning,news,events}
│   ├── nfp/
│   ├── strategies/{registry,forex,indices,metals,deriv_synthetic}
│   ├── research/{qlib,optimization,validation,falsification}
│   ├── vtil/{schemas,admission,graphrag,activation}
│   ├── execution/{core,router,mt5_bridge,deriv,reconciliation}
│   ├── tca/  review/  backtest/  observability/  security/
├── examples/                     # delivered
├── tools/                        # delivered: induce_gate_failures.py
└── tests/                        # delivered
```

## 50–62. See Part C (development plan, testing, gates, rollout, capital scaling) and Part D (evidence)

### 56. Capital scaling law
A capital or risk step is at most +25 % of the current mandate limits, at most one step per 30 days, only after ≥ 30 live trades in the period with positive expectancy, drawdown inside mandate, realised cost within 20 % of modelled, calibration valid and portfolio capacity available. A drawdown-tier breach steps down automatically by one step and requires owner acknowledgement to step back up.

### 60. Canonical decisions (Rev 2)
Rev 1's twenty decisions stand. Added: (21) the owner mandate is a capability grant and trades under it are A3; (22) multipliers only reduce; (23) lot rounding is down or `NO_TRADE`; (24) fixed-payout contracts are sized by stake; (25) VTIL is a VAN-owned VEKL-pattern layer separate from DIAL engineering VEKL; (26) no LLM output enters SCALP/MICRO loops; (27) an unprotected position blocks all new risk; (28) every gate must be broken deliberately before it is trusted; (29) an internal Risk Authority fault is a rejection.

### 62. Final principle
The defining characteristic of an expert VATI trader is not that it always has a prediction. It is that it can determine what kind of market exists, what is driving it, what information is trustworthy, which discipline currently has an edge, which horizon expresses it, how uncertain it is, what price makes the trade worthwhile, how much capital to expose, how to execute, when the thesis has failed, and when staying flat has the highest expected value — and that no part of it can exceed what the owner signed.

---

# Part C — Development plan (Rev 2, Feature IDs)

Each Feature enters implementation with its own acceptance contract (`product-management:write-spec`), a runbook for its material eventualities, and a gate that must be **induced to fail** before it counts as working. `npm run verify` / `pytest` evidence is recorded before any gate advances.

| Feature | Phase | Scope | Gate (must be broken deliberately first) | State |
|---|---|---|---|---|
| **VATI-F000** | 0 | Canon (this document), mandate/contract schemas, deterministic Risk Authority, forbidden behaviours in policy hook, `trading-intelligence` skill | property tests prove mandate cannot be exceeded; induced-failure probe 13/13 | **DELIVERED (Part D)** |
| VATI-F001 | 1 | Data catalog, point-in-time macro (ALFRED vintages), quality checks, normalisation, session calendars, lineage | deterministic replay reproduces identical state hashes; timestamp leakage test fails when leakage is injected | planned |
| VATI-F002 | 2 | VTIL: knowledge classes, polarity, decay, admission pipeline, trust tiers, activation manifest, GraphRAG | a T4 source cannot reach ADMITTED without validation; manifest hash changes when any selected resource changes | planned |
| VATI-F003 | 3 | NautilusTrader behind VAN interfaces; cost model (spread curve); backtest harness | identical inputs → identical results; bar-only SCALP certification is refused | planned |
| VATI-F004 | 4 | Risk Authority persistence, kill-switch service, drawdown governor service, ceilings policy versioning, gateway decisions/attention wiring | restart preserves kill-switch latch; ceiling change without owner signature is denied | planned |
| VATI-F005 | 5 | MT5 bridge + Windows worker, symbol/account sync, order_check/send with atomic SL, positions, reconciliation | disconnect/restart creates no duplicate or orphan orders; SL rejection flattens within 1 s in demo | planned |
| VATI-F006 | 6 | Deriv adapter: auth, WebSocket lifecycle, contract ops, stake sizing, synthetic classification, reconciliation | reconnect recovery certified; a synthetic capsule cannot consume real-market features | planned |
| VATI-F007 | 7 | Chart/technical intelligence, fingerprint verification, Gemini multimodal path, TradingView research gateway | screenshot-only signal cannot produce a TradeIntent | planned |
| VATI-F008 | 8 | Regime engine, horizon arbiter, strategy arbiter, calibrated meta-labeller, abstention | system reliably produces `NO_TRADE`; uncalibrated model cannot gate size | planned |
| VATI-F009 | 9 | Event matrix, NFP engine, shock/reaction vectors, analogue retrieval, event strategies | replay uses true vintages; a revised value cannot leak into a historical decision | planned |
| VATI-F010 | 10 | Gold real-yield model, futures order flow, index vol/term structure, VWAP/session models | regime-specific evaluation per capsule | planned |
| VATI-F011 | 11 | Research automation: OpenBB, Qlib, Optuna, Riskfolio, Deep Research/NotebookLM, champion/challenger, trial ledger | research output cannot reach the router without a signed promotion | planned |
| VATI-F012 | 12 | Execution intelligence, slippage models, order-type selection, TCA learning loop | net edge remains positive after realised cost over 200 demo fills | planned |
| VATI-F013 | 13 | Shadow trading across ≥ 3 regimes with full-stack decisions and no orders | shadow ledger replay matches live decisions | planned |
| VATI-F014 | 14 | Limited live: hardened credentials, signed mandate, minimal risk, continuous reconciliation | live cost within 20 % of model; zero unprotected-position seconds | planned |
| VATI-F015 | 15 | Autonomous mandate | all earlier gates green plus live evidence; owner A4 | planned |

**Milestones:** VATI-M1 Research-to-Demo = F000–F006 + initial FX/gold capsules; VATI-M2 Adaptive Specialist = F007–F011; VATI-M3 Limited Live = F012–F014. Instrument rollout Stage A/B/C and initial strategy rollout as Rev 1 §53–54.

### Testing strategy (Rev 1 §51, extended)
Unit (pips/ticks, sizing, margin, stops, event parsing, time zones, contract mapping); property (P1–P8 below, and per Feature); replay; failure injection (disconnect, delayed quotes, duplicates, reordered events, reconnects, restarts, DB outage, clock skew, spread explosion, partial fills, rejected stops); strategy tests; **induced-failure drills** for every gate, recorded as evidence.

### Certification gates (Rev 1 §52, extended)
Strategy certification adds: calibration gate passed; deflated Sharpe > 0; PBO ≤ 0.10; parameter perturbation passed; ≥ 200 OOS trades and ≥ 30 per regime; capsule signed by owner. Platform certification adds: induced-failure drills passed; decision replay identical; unprotected-position seconds = 0 in demo/shadow; `evaluate_safe` fault path exercised.

---

# Part D — Phase 0 evidence (VATI-F000)

All commands run from the `Van` repository root on 2026-09-16 at the commit that introduces this document.

**Baseline before Phase 0 (existing suite):**

```text
$ python3 -m pytest -q
83 passed in 2.65s
```

**Phase 0 trading tests:**

```text
$ python3 -m pytest trading -q
111 passed in 2.48s
```

**Policy hook including trading prohibitions:**

```text
$ python3 -m pytest hermes/policy -q
38 passed in 0.05s
```

**Property fuzz coverage** (seed 20260916, 3 000 generated mandate/snapshot/intent triples per property test): the fuzz asserts that it exercised both branches. Split at this commit: 228 approved/reduced, 2 772 rejected, 24 distinct rejection codes reached (`ACCOUNT_UNVERIFIED, CONSECUTIVE_LOSSES, CURRENCY_LEG_EXPOSURE, DRAWDOWN_TOP_TIER_ONLY, EVENT_BLACKOUT, INSTRUMENT_NOT_MANDATED, KILL_SWITCH, MANDATE_EXPIRED, MARKET_INTEGRITY, MAX_POSITIONS_PER_INSTRUMENT, MAX_TOTAL_POSITIONS, MODE_NOT_ORDER_SENDING, PORTFOLIO_HEAT, RECONCILIATION_FAILED, RISK_STORE_UNAVAILABLE, SIZE_BELOW_VENUE_MIN, STALE_DATA, STOP_REQUIRED, STOP_TOO_TIGHT, STRATEGY_NOT_MANDATED, STRATEGY_STATE_INELIGIBLE, TIME_SYNC_FAULT, VENUE_DISCONNECTED, WEEKEND_HOLD_FORBIDDEN`).

**Induced-failure probe** (`python3 trading/tools/induce_gate_failures.py`). Each row breaks one invariant in an in-memory copy of the authority and runs the fuzz against it; `OK` means the fuzz reacted as the design predicts:

```text
OK   control: unbroken                                          fuzz PASSED
OK   break: multiplier clamp only (masked by sizing re-check)   fuzz PASSED
OK   break: multiplier clamp + sizing re-check + final re-check fuzz FAILED (P1 at 175:)
OK   break: mandate per-trade clamp only (masked by final re-check) fuzz PASSED
OK   break: mandate per-trade clamp + final re-check            fuzz FAILED (P1 at 70:)
OK   break: portfolio heat check                                fuzz FAILED (P3 at 1597:)
OK   break: currency-leg check                                  fuzz FAILED (P4 at 94: ...)
OK   break: duplicate-intent latch                              fuzz FAILED (P8 at 4)
OK   break: kill-switch check                                   fuzz FAILED (P6 violated at case 341:)
OK   break: stale-data check                                    fuzz FAILED (P6 violated at case 381:)
OK   break: account-verified check                              fuzz FAILED (P6 violated at case 1048:)
OK   break: order-sending-mode check                            fuzz CRASHED (KeyError: fail-closed by exception)
OK   break: stop-required check                                 fuzz CRASHED (TypeError: fail-closed by exception)

13/13 probes behaved as expected
```

Three things this probe taught, recorded because the correction is the deliverable:

1. **The first version of the probe was measuring the wrong layer.** Exec'ing a broken copy of the authority created a second `Decision` enum, so every `is` comparison failed at case 0 and every break "failed" for the wrong reason. The probe now injects the original enum and dataclass identities; only then do the failure rows name the property that was actually violated.
2. **Two single-point breaks are masked by defence in depth.** Removing the multiplier clamp alone, or the mandate clamp alone, does not change any approval because the sizing re-check and the final invariant re-check catch the oversize. The probe breaks each together with its backstop to show the fuzz still detects the pair. The masked rows are kept in the report so a future refactor that removes a backstop is visible.
3. **Two breaks crash rather than approve.** Removing the mode check or the stop-required check makes later code raise. That is fail-closed, but a router must never see an exception, so `RiskAuthority.evaluate_safe` was added and tested: an internal fault becomes `REJECTED / AUTHORITY_FAULT` with size 0.

**Reference sizing check (worked example from Rev 1 §41, now a test):** equity 10 000, requested 0.40 %, EURUSD long 1.10010 / stop 1.09790 (22 pips), 1 standard lot = 100 000 per price unit → raw 0.1818 lots → **0.18 lots**, realised risk 39.60 (0.396 %), heat after 0.396 %. Rev 1's example receipt of `approved_size: 0.42` at `approved_risk_pct: 0.0032` is inconsistent with its own intent at standard lot size (0.42 lots × 22 pips = 92.40 = 0.92 % of 10 000); Rev 2's number is the one the code produces.

**What Phase 0 does not claim.** No market data, strategy, adapter, reconciliation or VTIL service exists yet; nothing here has traded on demo or live; the mandate example carries a placeholder signature reference and is not a live mandate. Rev 2 becomes locked authority only when the owner accepts it (A4).

---

# Part E — Industry Integration Architecture (Rev 2.1)

## E.0 Why this part exists

The owner's review notes (2026-09-16) judged Rev 1 correct in philosophy but not yet a deterministic build authority: it did not lock one best-fit tool per layer, reject overlapping alternatives, define interface contracts, pin repositories/versions/licences, set data-source precedence and fallback, or lay out deployment topology and end-to-end wiring. Part E does that. It also records the owner's two directions: VAN trader is a new project inside the existing Van product, and it borrows DIAL's VEKL infrastructure, with a dedicated trading VEKL instance permitted later if evidence justifies it.

Every external fact below was read from a primary artefact on 2026-09-16 (PyPI JSON, upstream LICENSE files, the published `nautilus_trader` wheel) and is recorded in `trading/architecture/stack_lock.json`. None of it is a version pin; pins happen at each adoption gate through Context7/official releases.

## E.1 Review of the proposed stack, layer by layer

The notes' table is adopted with the corrections below. Verdicts: **ADOPT** as proposed; **ADOPT+FIX** with a correction; **STAGE** right tool, later phase.

| Layer | Proposed | Verdict | Verified facts and corrections |
|---|---|---|---|
| Trading kernel | NautilusTrader | **ADOPT** | Wheel 1.231.0 ships `BinaryOption`, `Cfd`, `CurrencyPair`, `FuturesContract`, `OptionContract`, `RiskEngine` (+ `risk/sizing`), `ParquetDataCatalog`, `backtest/node`, `live/node`, `execution/algorithm`, in-tree `databento`, `sandbox` and `_template` adapters. **No MT5, Deriv or cTrader adapter exists**; VAN writes both venue adapters from `_template`. Licence LGPL-3.0-or-later (weak copyleft: use as a library is fine; modifications to Nautilus itself must be published). Requires Python ≥ 3.12; the Van gateway runs 3.11, so the kernel gets its own runtime/container. |
| Independent validation oracle | QuantConnect LEAN | **ADOPT+FIX** | Apache-2.0. Validation only, never a live account. Cost is real: every Tier-A capsule is implemented twice. Rev 2.1 limits LEAN reproduction to Tier-A capsules (those eligible for more than 25 % of mandate risk budget) and defines the agreement metric (§E.6). |
| MT5 execution | Nautilus ExecutionClient → VAN Risk Authority → MT5 worker | **ADOPT+FIX** | The notes place the Risk Authority *after* the ExecutionClient; that is too late, because an order object already exists. Correct chain in §E.2: Strategy → **VAN RiskGate** (sizing, before any order exists) → `SubmitOrder` → **Nautilus RiskEngine** (venue-level quantity/price/notional/rate checks) → **ExecutionClient** (refuses any order without a sealed `decision_hash`) → Windows worker → broker. Three planes, one sizer. `MetaTrader5` 5.0.6180 ships `win_amd64` wheels only. |
| Deriv execution | VAN-native first-class venue | **ADOPT** | Implemented as a Nautilus adapter, not a separate bot: Rise/Fall, Accumulators, Turbos, Vanillas map to `BinaryOption`/`OptionContract`; Multipliers and CFDs map to `Cfd`. All fixed-payout products use the `FULL_STAKE` loss model already enforced in `vati/risk`. |
| Futures/options reference data | Databento + direct CME/Cboe | **STAGE (Phase 10)** | `databento` 0.86.0, Apache-2.0; Nautilus in-tree adapter. Needed for Stage C indices and gold order-flow reference, not for Stage A FX demo. Paid entitlement is an external gate. |
| Implied volatility | CME CVOL + Cboe VIX family | **STAGE (Phase 10)** | Named as the primary forward-looking volatility state; ATR/realised volatility become fallback features, never the primary state. Vendor terms and entitlement are external gates. |
| Research-data façade | OpenBB | **ADOPT+FIX** | 4.7.2, **AGPL-3.0-only**. Research process only; never market-data truth; never in the latency path. AGPL requires an owner-signed adoption decision; DIAL's own ERP doctrine allows AGPL only as a self-hosted sibling or read-only reference, and VATI follows the same rule. |
| AI quant research | Microsoft Qlib | **ADOPT+FIX** | `pyqlib` 0.9.7, MIT. Terminates at the model boundary (MLflow). Qlib's data handlers are equity-centric; FX/futures handlers are VAN-written. Its execution layer is never used. |
| Hyperparameter search | Optuna | **ADOPT** | 5.0.0, MIT. Research only; output is a candidate. |
| Feature store | Feast | **STAGE (Phase 8)** | 0.66.0, Apache-2.0. Adopted when the calibrated meta-labeller arrives; online reads are T1, never T0. |
| Model/experiment registry | MLflow | **STAGE (Phase 8)** | 3.16.0, Apache-2.0. A model alias is not a promotion; the signed `StrategyCapsule` is. |
| Live event backbone | Redpanda | **STAGE (Phase 12)** | **BSL-1.1** (converts to Apache-2.0 per release schedule). Never inside the tick-to-order path. M1 uses the Nautilus message bus plus the event ledger with the *same event contracts*; Redpanda is introduced at M2 without a contract change. Owner-signed adoption decision required. |
| Hot market time-series | QuestDB | **STAGE (Phase 12)** | Apache-2.0. Never transactional authority. |
| Historical lake | Parquet + object storage | **ADOPT** | Nautilus `ParquetDataCatalog` for kernel-consumable data plus normalised research Parquet. Phase 1. |
| Research accelerator | ArcticDB (optional) | **STAGE (Phase 11, optional)** | 6.26.0, **BSL-1.1**. Owner-signed adoption decision required. |
| Transactional authority | PostgreSQL | **ADOPT+FIX** | Phases 0–3 may use the Van gateway SQLite store with the same schemas; PostgreSQL from Phase 4. Always a **separate database from any DIAL business/finance database**: VATI is not a DIAL money authority and must not become a second ledger inside DIAL. |
| Durable workflows | Temporal | **STAGE (Phase 11)** | `temporalio` MIT. Certification, promotion and broker-recovery workflows; never in the tick path. |
| VEKL / GraphRAG | "Existing DIAL system" | **ADOPT+FIX** | Borrow the **resource-selection, manifest and immutable-snapshot substrate** (proven in §E.4). Do **not** borrow the GraphRAG/Development-Unit half initially: it presumes DIAL's Feature Registry, Contract Registry and Decision Log. VTIL's analogue graph is compiled from VATI's own event ledger. |
| Google research mesh | Gemini / Deep Research / NotebookLM | **ADOPT** | Via the existing VAN gateway planner; T2/T3 only. |
| Observability | OpenTelemetry + Prometheus + Grafana | **ADOPT (Phase 1)** | Grafana is AGPL; used as an unmodified operator tool, not linked into VATI. |

Overlaps rejected explicitly: no second production kernel (LEAN, backtrader, vectorbt); no ML framework execution layer; no analytical store as transactional authority; no OpenBB in the latency path; no LLM in T0/T1; no message broker in T0.

## E.2 Canonical wiring (deterministic stitching)

```text
EXTERNAL SOURCES
  venue feeds (MT5 / Deriv)     reference feeds (Databento, CME, Cboe)     macro/news (BLS, Fed, ALFRED, OpenBB façade)
        │                                  │                                          │
        └──────────────────────────────────┴──────────────────────────────────────────┘
                                           │
                                   INGESTION GATE  (schema, clocks, freshness, hash)      T1
                                           │
                            CANONICAL EVENT STREAM                                        T1
                     M1: Nautilus message bus + event ledger | M2+: Redpanda (same contracts)
                                           │
              ┌────────────────────────────┼─────────────────────────────┐
              ▼                            ▼                             ▼
        QuestDB (M2)               Parquet lake                    EVENT LEDGER
        live / hot            ParquetDataCatalog + research      PostgreSQL (SQLite ≤ Phase 3)
              │                            │                             ▲
              └──────────────┬─────────────┘                             │
                             ▼                                           │
                      FEATURE ENGINE ── Feast (M2) offline ↔ online      │
                             │                                           │
             ┌───────────────┴─────────────────┐                         │
             ▼                                 ▼                         │
      LIVE MARKET STATE                   RESEARCH (T3)                  │
      regimes, integrity,            Qlib · Optuna · OpenBB façade       │
      activation_id                  MLflow lineage                      │
             │                       purged / walk-forward               │
             │                       LEAN independent reproduction       │
             │                       Nautilus realistic backtest         │
             │                       cost / latency / slippage stress    │
             │                                 │                         │
             │                          VTIL admission ◄── TradeExperience / TCA artefacts
             │                                 │                         │
             └────────────────┬────────────────┘                         │
                              ▼                                          │
                     STRATEGY REGISTRY  (signed StrategyCapsules)        │
                              │                                          │
                     NautilusTrader Strategy  ─────────────────────────┐ │
                              │                                        │ │
                     OPPORTUNITY ENGINE → TradeIntent                  │ │
                              │                                        │ │
   ═══════════ VAN RISK GATE  (trading/vati/risk, in-process, T0) ═════│═│═══  plane 1: the only sizer
                              │  sealed RiskDecision                   │ │
                     Nautilus RiskEngine (qty / price / notional / rate) │ │  plane 2
                              │                                        │ │
                     ExecutionClient  (refuses without decision_hash)  │ │  plane 3
                       /               \                               │ │
             MT5 ExecutionClient      Deriv ExecutionClient            │ │
                    │                        │                         │ │
          mTLS bridge → Windows worker    Deriv WebSocket              │ │
                    │                        │                         │ │
                 broker                    Deriv                       │ │
                    └───────────┬────────────┘                         │ │
                                ▼                                      │ │
                         RECONCILIATION ───────────────────────────────┘─┘
                                ▼
                               TCA
                                ▼
                          TRADE REVIEW
                                ▼
                         VTIL LEARNING (admission, never authority)
```

Every arrow is a typed contract (§E.5). Nothing on the T0 line crosses a network broker, a workflow engine or a model.

## E.3 Research-to-production supply chain

```text
IDEA / OBSERVATION
  ↓ VTIL hypothesis (CAUSAL_HYPOTHESIS, activation_id)
  ↓ Qlib / deterministic research (trial ledger sequence number)
  ↓ Optuna exploration (candidate only)
  ↓ MLflow experiment lineage (dataset hash, vintage, seeds, cost model)
  ↓ purged / embargoed / walk-forward validation; calibration gate (§22)
  ↓ LEAN independent reproduction (Tier-A capsules; agreement metric §E.6)
  ↓ Nautilus realistic backtest (ParquetDataCatalog, spread curve, latency)
  ↓ cost / latency / slippage stress; deflated Sharpe; PBO ≤ 0.10
  ↓ DEMO → SHADOW → LIMITED_LIVE
  ↓ StrategyCapsule signature (owner A4; MLflow model version + Feast feature version + VTIL evidence refs frozen in the capsule)
  ↓ CERTIFIED_LIVE
```

Production model path: `MLflow model version → Feast exact feature version → VATI meta-labeller`. VTIL records why the model exists, what evidence supports it, which regimes it works in, which failures were observed and what superseded it. MLflow owns the machine-learning lifecycle; VTIL owns trading knowledge and provenance; neither duplicates the other, and neither can promote a capsule.

## E.4 VTIL on borrowed DIAL VEKL infrastructure

### What DIAL actually has (mapped 2026-09-16)
- The VEKL engine is plain ESM in `dial-new/agent-system/orchestration/` with **zero npm dependencies** and `repoDir`/`root` already parameterised on every public function. The resource-selection slice (`engineering-resource-resolver.mjs`, `engineering-resource-registry.mjs`, `skill-registry.mjs` loaders, `skill-activation-store.mjs` manifest/hash/verify, immutable `knowledge/vendor` snapshot jail) is about 1 100 lines.
- Registries are JSON arrays with JSON Schema files (`engineering-resource.schema.json`, `engineering-resource-source.schema.json`, `skill-activation-manifest.schema.json`). Trust tiers are `T0_…`–`T4_…` strings; `sensitive_data_allowed` is schema-level `const false`.
- Task classes are registry-owned (`TASK_CLASS_SIGNAL_POLICY.json` prose/path rules), so a new domain adds vocabulary without code changes.
- DIAL coupling is a handful of hard-coded relative paths (`agent-system/engineering-knowledge/registries`, `agent-system/registries/TASK_CLASS_SIGNAL_POLICY.json`, `FEATURE_REGISTRY.json`, seven canon `AUTHORITY_PATHS`), one Feature-ID regex, a `HEALTH`/`zie619` guard and `MANDATORY_TASK_CLASSES`. The GraphRAG/Development-Unit half is deeply coupled to DIAL's Feature Registry, Contract Registry and Decision Log.

### Borrow plan
1. **Now (delivered):** Van keeps a trading registry in DIAL's exact schema at `trading/vtil/registry/` (14 sources, 16 resources, a T0 `van.trading` policy source that always binds, one T4 community source restricted to discovery). `trading/vtil/tools/resolve_probe.mjs` mirrors the two directory names DIAL hard-codes and runs DIAL's **unmodified** resolver against it.
2. **Phase 2 (VATI-F002):** vendor the resource-selection slice into Van as a pinned DIAL commit (git subtree or package), with a `vekl-config.mjs` seam proposed upstream in dial-new so paths, project ID, entity-ID pattern, sensitive-domain guards and mandatory classes are injected rather than hard-coded. That upstream change is a DIAL Project Truth change and needs an `OWNER_EXPLICIT` authorization record in dial-new; until then Van runs the mirror approach.
3. **Phase 2:** VTIL persists Trading Knowledge Activation Manifests with the same fields as DIAL's manifest (`activation_id`, resources with `selection_role`/`selection_purpose`, `registry_fingerprint`, `manifest_sha256`, `previous_activation_id`), under VATI's own control home, never under `/var/lib/dial-control`.
4. **Not borrowed initially:** GraphRAG compiler, Development Units, admission guard tied to DIAL canon. VTIL's analogue graph (Rev 2 §7) is compiled from VATI's event ledger and `TradeExperienceArtifact`s.
5. **Fork trigger (owner decision, evidence-based):** VTIL becomes a dedicated VEKL instance if any of: (a) trading task classes or trading-specific eligibility rules (regime validity, decay, polarity) cannot be expressed in the shared resolver without DIAL-facing changes; (b) retrieval-eval on the trading golden set stays below floor for two consecutive re-resolutions after registry tuning; (c) VTIL freshness needs (minutes) conflict with DIAL's engineering cadence (hours/days). Until then, one substrate, two registries.

### Proof (`DIAL_REPO=../dial-new node trading/vtil/tools/resolve_probe.mjs`)

```text
status GREEN | validation ok True 14 sources 16 resources
VT-001 ok= True | classes ['NFP_EVENT_TRADING', 'MACRO_POINT_IN_TIME']
   selected ['van.trading.rules.rev2-canon', 'ref.bls.employment-situation', 'ref.alfred.vintages', 'community.forums.nfp-trading-anecdotes']
   community(corroboration only) ['community.forums.nfp-trading-anecdotes']
VT-002 ok= True | classes ['MT5_EXECUTION', 'SYMBOL_CONTRACT_SYNC', 'TRADING_KERNEL', 'VENUE_ADAPTER']
   selected ['van.trading.rules.rev2-canon', 'ref.nautilus.adapter-template', 'ref.nautilus.docs', 'ref.metaquotes.mt5-python']
VT-003 ok= True | classes ['DERIV_EXECUTION', 'DERIV_SYNTHETIC', 'RECONCILIATION', 'VENUE_ADAPTER']
   selected ['van.trading.rules.rev2-canon', 'ref.deriv.api', 'ref.nautilus.adapter-template', 'ref.nautilus.docs']
VT-004 ok= True | classes ['RATES_POLICY', 'FOMC_EVENT_TRADING', 'POSITIONING_COT', 'IMPLIED_VOLATILITY', 'INDEX_VOLATILITY_REGIME', 'GOLD_MACRO']
   selected ['van.trading.rules.rev2-canon', 'ref.cme.cvol', 'ref.fomc.statements', 'ref.cftc.cot', 'ref.cboe.vix-term-structure', 'ref.wgc.gold-demand', 'ref.cme.gold-futures-spec']
```

The first run was RED on three of four cases. The cause was not the resolver: resources without an explicit `selection_purpose` fell into the same (purpose, role) slot and DIAL's minimal-coalition law kept only one per slot (BLS lost to ALFRED, CVOL to Cboe, WGC to the CME spec). Giving each resource its purpose fixed it, which is exactly how that law is meant to be driven. The probe is wrapped by `trading/tests/test_vtil_borrow.py` and skips, never passes silently, when Node or a dial-new checkout is absent.

## E.5 Interface contracts and data precedence

**Event contracts** (JSON Schema, `trading/vati/contracts/schemas`; new schemas land with their phase): `MarketTick`, `MarketBar`, `MarketState`, `IntegrityStateChange`, `FeatureVector`, `OpportunityAssessment`, `TradeIntent`, `RiskDecision`, `OrderCommand`, `ExecutionReceipt`, `PositionChange`, `ReconciliationResult`, `TcaRecord`, `TradeExperienceArtifact`, `ActivationManifest`, `StrategyCapsule`, `TradingMandate`. Every event carries `event_time`, `received_time`, `producer`, `schema_version`, `hash`; T0 events also carry `decision_time`.

**Data-source precedence and fallback**

| Need | Primary | Fallback | Rule |
|---|---|---|---|
| Executable price for MT5 instruments | MT5 venue feed | none | venue feed is execution truth; if stale → `STALE_DATA` |
| Executable price for Deriv | Deriv WebSocket | none | as above |
| Cross-feed divergence reference | Databento (futures), second broker feed (FX) | none | divergence drives integrity state, never a price |
| Futures order flow (ES, NQ, GC, SI) | Databento MBP-10/trades | none | absent → order-flow features are `MISSING`, strategies requiring them ineligible |
| Implied volatility | CME CVOL, Cboe VIX family | realised-vol proxy flagged `PROXY` | proxy can only reduce size |
| Macro point-in-time | ALFRED vintages | none for backtests | live decisions may use FRED current; backtests may not |
| Event calendar | agency schedule (BLS, Fed) | vendor calendar | disagreement extends blackout |
| Slow research data | OpenBB façade → provider | direct provider | research only |

## E.6 LEAN agreement metric

A Tier-A capsule passes independent reproduction when, on the same out-of-sample window and cost model: expectancy has the same sign and differs by ≤ 25 %; maximum drawdown differs by ≤ 25 %; trade count differs by ≤ 15 %; the top-10 trades by R overlap ≥ 70 % by timestamp. Failure is a finding about the strategy or the cost model, recorded in VTIL as `COUNTERFACTUAL_RESULT`, and blocks promotion.

## E.7 Deployment topology

The DIAL Oracle estate (`dial-hermes-control` A1, `vekl-worker` and `oracle-admin` micro nodes) is a control plane with about 3 GB steady-state headroom on the control host and 1 GB micro nodes, an explicit "Oracle is not a compute source" principle, no data-plane services (no Postgres, streaming, time-series or observability), and a placement engine that rejects any workload class not in `hosts.json`. It cannot host the trading data plane and must not be asked to.

```text
DIAL fabric (control plane only)                     VATI estate (Van-owned)
┌──────────────────────────────┐   project binding   ┌───────────────────────────────────────────┐
│ dial-hermes-control          │◄───────────────────►│ vati-core (Linux, ≥ 8 GB, Python 3.12)     │
│  Hermes profile van          │  MCP endpoint,      │  Nautilus TradingNode + VAN RiskGate (T0)  │
│  trading-intelligence skill  │  signed decisions,  │  Deriv adapter, MT5 bridge client          │
│  Oracle mission / research   │  audit sink         │  event ledger (PostgreSQL), Parquet lake   │
└──────────────────────────────┘                     │  OTel → Prometheus → Grafana               │
                                                     │  VTIL registry + activation store          │
   VAN gateway (existing)                            ├───────────────────────────────────────────┤
   decisions / attention / audit  ◄─────────────────►│ vati-mt5-worker (Windows, isolated VLAN)   │
   owner device: mandates (A4), FLATTEN_ALL          │  MT5 terminal + MetaTrader5 worker, mTLS   │
                                                     ├───────────────────────────────────────────┤
                                                     │ vati-data (M2+, optional second host)      │
                                                     │  Redpanda, QuestDB, Feast online, MLflow,  │
                                                     │  Temporal, LEAN runner                     │
                                                     └───────────────────────────────────────────┘
```

Rules: M1 runs on `vati-core` + `vati-mt5-worker` only; M2 adds `vati-data`. Attachment to the DIAL fabric uses only the sanctioned project-binding seam (`project_id`, MCP endpoint, capability subset, job-scoped credentials, attempt budget, audit sink). Any shared datastore or new workload class on the DIAL side requires an owner authorization record in dial-new with the `locked_provider_change` flag and a `hosts.json` change; none is requested by Rev 2.1.

## E.8 How the stack delivers the five properties

| Property | Mechanism |
|---|---|
| **Deterministic** | one event-driven kernel (Nautilus), one in-process sizer (Risk Authority), sealed hashes on every decision, ParquetDataCatalog replay, registry fingerprints and activation manifests for knowledge, decision replay as an acceptance gate |
| **Profitable** | net-edge objective after costs, spread curve and slippage model, calibration gate, deflated Sharpe and PBO, LEAN cross-check for Tier-A capsules, capital-scaling law tied to realised cost and live expectancy |
| **Dynamic** | regime/horizon arbiters, Feast online features, calibrated meta-labeller, strategy health with hysteresis, drawdown governor, integrity state machine, forward-looking volatility state |
| **Symbiotic** | VTIL on DIAL's VEKL substrate, Hermes as analyst under the same profile and policy hook, Google mesh through the same gateway planner, MLflow↔VTIL complementarity, owner decisions/attention/audit engines reused |
| **Cohesive** | one kernel, one sizer, one order sender, one transactional authority, typed contracts on every arrow, stack lock tested in CI, no overlapping tools |

## E.9 Feature plan deltas (Part C)

- **VATI-F002** now reads: vendor the DIAL VEKL resource-selection slice at a pinned commit; VTIL registry, activation store, admission pipeline; retrieval golden set for trading (extend the four probe cases to ≥ 12). Gate: DIAL resolver selects trading knowledge from the Van registry (delivered as a probe), community source never admitted without validation, manifest hash changes on any registry change.
- **VATI-F003** adds LEAN as validation-only with the §E.6 metric for Tier-A capsules, and the Python 3.12 kernel runtime.
- **VATI-F005/F006** are Nautilus adapters built from `_template` with the three-plane execution chain; gate adds "an order without a sealed decision hash is refused by the ExecutionClient".
- **VATI-F008** adds Feast + MLflow; gate adds "feature definitions identical offline and online (skew test)".
- **VATI-F012** adds Redpanda + QuestDB behind unchanged event contracts; gate adds "T0 path latency unchanged with the broker present".
- **VATI-F011** adds Temporal, Qlib, Optuna, OpenBB (AGPL decision), ArcticDB (BSL decision, optional).
- New standing gate for every phase: `trading/tests/test_stack_lock.py` stays green; a new tool is added to the lock before it is added to code.

## E.10 Evidence for Rev 2.1

```text
$ python3 -m pytest trading/tests/test_stack_lock.py -q        → 7 passed
$ DIAL_REPO=../dial-new node trading/vtil/tools/resolve_probe.mjs → status GREEN, 4/4 cases (output above)
$ python3 -m pytest trading/tests/test_vtil_borrow.py -q       → 2 passed
wheel inspection: nautilus_trader-1.231.0-cp312-manylinux_2_35_x86_64.whl, 765 entries;
  BinaryOption/Cfd/CurrencyPair/FuturesContract/OptionContract, risk/engine + risk/sizing,
  persistence/catalog/parquet.py, adapters: architect_ax betfair binance bitmex bybit databento
  deribit dydx hyperliquid interactive_brokers kraken okx polymarket sandbox tardis _template;
  METADATA: Version 1.231.0, License LGPL-3.0-or-later, Requires-Python >=3.12,<3.15
licences read from upstream LICENSE files: LEAN Apache-2.0; Redpanda BSL-1.1; QuestDB Apache-2.0;
  Feast Apache-2.0; MLflow Apache-2.0; Temporal MIT; ArcticDB BSL-1.1; Qlib MIT; OpenBB AGPL-3.0; Optuna MIT; databento Apache-2.0
```

What Rev 2.1 does not claim: no tool above is installed, pinned or wired; no adapter exists; the VTIL registry is a seed, not an admitted corpus; the DIAL-side `vekl-config.mjs` seam is a proposal awaiting an owner authorization record in dial-new.
