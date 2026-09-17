# VAN Adaptive Trading Intelligence (VATI)
## Comprehensive Technical Blueprint & Development Plan
**Revision:** 1.0
**Date:** 2026-09-16
**Status:** SUPERSEDED for active intent by `docs/VAN_ADAPTIVE_TRADING_INTELLIGENCE_TECHNICAL_BLUEPRINT_REV2.md` (2026-09-16). Retained as provenance.
**Product:** VAN — DIAL Hermes AI Assistant
**Primary scope:** Forex, major indices, metals, MetaTrader 5, Deriv, research intelligence, adaptive strategy selection, risk management, execution, learning and owner-facing trading UX
**Parent architecture:** VAN remains a Hermes bot. Hermes remains the planning/orchestration authority. VEKL is the versioned research-and-learning substrate. Deterministic risk and execution controls outrank model opinion.

---

# 0. Executive Summary

VAN Trader shall not be implemented as a conventional retail “AI trading bot,” a fixed indicator strategy, a single model that predicts the next candle, or an LLM directly connected to a broker.

The target is **VAN Adaptive Trading Intelligence (VATI)**: a multi-market, multi-horizon, regime-adaptive trading system capable of:

- understanding market fundamentals, macroeconomics, rates, positioning, volatility, order flow, charts, candles, indicators, pips/ticks, sessions and market microstructure;
- identifying which market discipline is currently appropriate;
- switching dynamically among certified strategy families rather than trading one static setup everywhere;
- scalping when execution conditions support it;
- holding intraday, session, swing or multi-day positions when the analysis supports a longer horizon;
- using live and historical news intelligently, including specialist NFP/event trading;
- learning from market history, prior trades, failures, regime changes and strategy decay through VEKL/GraphRAG;
- using Google research tools where slower, deeper research adds value;
- integrating with MetaTrader 5 and Deriv while preserving broker/venue-specific semantics;
- using stop losses, take profits, trailing/structural/time/event exits, partial exits and catastrophic protection;
- performing dynamic lot/position sizing based on risk, stop distance, volatility, liquidity, margin, correlation and portfolio heat;
- detecting abnormal market conditions and degrading safely rather than blindly executing;
- continuously researching and challenging production strategies without permitting unvalidated self-modifying live trading;
- optimizing for **net positive expectancy after costs and risk**, not superficial win rate or raw historical profit.

The core architecture is:

```text
                              OWNER
                                │
                              VAN
                                │
                             HERMES
                                │
                  VAN ADAPTIVE TRADING INTELLIGENCE
                                │
        ┌───────────────────────┼─────────────────────────┐
        │                       │                         │
   MARKET BRAIN            RESEARCH BRAIN             RISK BRAIN
        │                       │                         │
 Regimes / Macro            VEKL / GraphRAG          Capital Budget
 Rates / Options            Deep Research            Portfolio Heat
 Charts / Order Flow        Strategy R&D             Drawdown Governor
 Positioning / News         Historical Analogues     Margin / Tail Risk
        │                       │                         │
        └───────────────────────┼─────────────────────────┘
                                │
                        STRATEGY ARBITER
                                │
                         HORIZON ARBITER
                                │
                           META-LABELER
                                │
                       OPPORTUNITY MODEL
                                │
                    DETERMINISTIC RISK AUTHORITY
                                │
                     EXECUTION INTELLIGENCE
                                │
                   ┌────────────┴────────────┐
                   │                         │
            NAUTILUSTRADER              DERIV ADAPTER
                   │                         │
               MT5 ADAPTER                Deriv API
                   │
              MT5 TERMINAL
                   │
                 BROKER
```

No component may bypass the deterministic risk authority to place a live order.


# 1. Product Doctrine

## 1.1 Mission

VATI exists to identify and exploit robust market opportunities while controlling capital loss, model error, execution error, data error and regime change.

Its purpose is **not** to trade continuously.

A correct outcome may be:

```text
NO TRADE
```

if no certified edge exists after costs and risk.

## 1.2 Profit Objective

The optimization objective is:

```text
Expected Net Edge
=
Expected Gross P&L
- Spread
- Commission
- Expected Slippage
- Financing / Swap
- Market Impact
- Execution Uncertainty
- Tail-Risk Penalty
- Drawdown Penalty
```

VATI should optimize long-run risk-adjusted net expectancy, not raw P&L without costs, win rate, trade frequency, leverage, or cherry-picked backtests.

## 1.3 Safety/Authority Ordering

```text
OWNER MANDATE
      ↓
RISK AUTHORITY
      ↓
VENUE / BROKER CONSTRAINTS
      ↓
CERTIFIED STRATEGY RULES
      ↓
VAN / HERMES ANALYSIS
      ↓
EXECUTION
```

The LLM may recommend, explain and orchestrate research, but it may never override maximum risk, portfolio heat, margin limits, drawdown gates, stale-data gates, kill switches, forbidden instruments, account mandates or venue constraints.


# 2. Trading Disciplines

VATI must not treat all instruments or horizons identically.

## 2.1 Expert Disciplines

1. FX Macro & Rates
2. FX Intraday / Session Trading
3. FX Scalping / Microstructure
4. Index Futures / CFD Intraday
5. Index Swing / Macro
6. Gold / Metals Macro
7. Gold / Metals Order Flow & Intraday
8. NFP / CPI / FOMC / High-Impact Event Trading
9. Technical Price Action
10. Volatility / Options-Implied Analysis
11. Portfolio & Correlation Risk
12. Deriv Real-Market Products
13. Deriv Synthetic Markets
14. Execution & Transaction Cost Analysis

A Strategy Arbiter chooses among these; they are not merged into one universal model.

## 2.2 Horizon Arbiter

```text
MICRO            seconds → a few minutes
SCALP            minutes
INTRADAY         minutes → hours
SESSION          session-bound
OVERNIGHT        cross-session
SWING            hours → days
POSITION         multi-day / macro
```

The Horizon Arbiter evaluates forecast quality, spread relative to expected move, volatility, session liquidity, event proximity, model stability, financing/swap, market structure, fill probability and signal decay.


# 3. Market Operating Model

Before any strategy is selected, VATI constructs a live `MarketState`.

```yaml
MarketState:
  instrument: EURUSD
  timestamp: ...
  regime:
    macro: disinflationary_soft_landing
    policy: fed_easing_priced
    rates: front_end_yields_falling
    risk: risk_on
    volatility: expanding
    liquidity: normal
    technical: bullish_trend
    order_flow: buyer_dominant
  event_proximity:
    tier_1_event_minutes: 74
  session:
    name: london_new_york_overlap
    liquidity_score: 0.88
  execution:
    spread_percentile: 0.32
    slippage_risk: low
  uncertainty:
    regime_confidence: 0.79
    model_disagreement: 0.18
```

## 3.1 Regime Dimensions

- growth;
- inflation;
- central-bank;
- rates;
- liquidity;
- risk-on/risk-off;
- realised volatility;
- implied volatility;
- trend/range/compression;
- positioning/crowding;
- technical structure;
- order flow;
- execution quality;
- event risk.

## 3.2 Regime Transitions

Use bounded combinations of Bayesian change-point detection, state-space models, volatility breaks, feature-distribution drift, rolling correlation breaks, trend persistence changes, spread/liquidity changes, strategy residual drift and ensemble disagreement.

```text
NORMAL → CAUTION → TRANSITION → NEW_REGIME
```

Capital should reduce before new strategies are promoted.


# 4. Market Data Architecture

## 4.1 Data Classes

```text
PRICE
quotes / trades / bars / ticks / depth

EXECUTION
spread / slippage / latency / fills / rejects

MACRO
actual / forecast / prior / revisions / vintages

RATES
policy expectations / yields / curves / futures

OPTIONS
IV / skew / term structure / expected move

POSITIONING
COT / open interest / ETF flows / futures positioning

NEWS
official releases / central-bank communication / trusted wires

FUNDAMENTAL
growth / inflation / labour / earnings / commodity demand

MARKET MICROSTRUCTURE
L1 / L2 / L3 where available
```

## 4.2 Data Quality Contract

```yaml
source_id:
source_tier:
instrument:
event_time:
received_time:
timezone:
revision_id:
vintage_time:
latency_ms:
quality_score:
stale_after:
license_class:
hash:
```

## 4.3 Time Semantics

Keep separate:

- event time;
- received time;
- decision time.

Backtests must reproduce these distinctions where latency matters.

## 4.4 Data Granularity

```text
Bars
 ↓
Trade ticks
 ↓
L1 bid/ask
 ↓
L2 depth
 ↓
L3 order-by-order
```

Scalping and tight-stop strategies cannot be certified solely from candle bars.


# 5. External Trading & Research Ecosystem

These are candidate components subject to license, entitlement and production review.

## 5.1 NautilusTrader — Canonical Trading Kernel

Use as:

- canonical event-driven strategy runtime;
- deterministic simulation;
- order/position domain model;
- portfolio/risk integration point;
- live execution host abstraction.

Keep VAN-owned interfaces around it so external framework changes do not become project canon.

## 5.2 MetaTrader 5

Use official MT5 capabilities for account/symbol data, ticks/bars, order checking/sending, position inspection, SL/TP and margin calculation.

Target architecture:

```text
VATI Linux Core
    │
private authenticated bridge
    │
isolated MT5 worker
    │
MT5 terminal
    │
broker
```

## 5.3 Deriv

Use a dedicated adapter supporting:

- OAuth/PAT as appropriate;
- REST account/service operations;
- authenticated WebSocket market/trading operations;
- normalized contract models;
- strict real-market vs synthetic classification.

## 5.4 cTrader — Optional Future Venue

Support later for brokers where it adds value. Do not add before MT5/Deriv are stable unless a broker requirement justifies it.


# 6. VEKL Trading Intelligence Layer (VTIL)

VEKL becomes VATI's durable research and experience substrate.

Canonical rule:

> VEKL may influence knowledge, confidence and certified strategy selection, but no VEKL result can directly place a live trade.

## 6.1 Knowledge Classes

```text
MARKET_OBSERVATION
EVENT_OBSERVATION
TRADE_EXPERIENCE
CHART_FINGERPRINT
REGIME_KNOWLEDGE
STRATEGY_EVIDENCE
STRATEGY_CAPSULE
RESEARCH_PACKET
ANTI_PATTERN
DURABLE_MARKET_KNOWLEDGE
CAUSAL_HYPOTHESIS
COUNTERFACTUAL_RESULT
```

## 6.2 TradeExperienceArtifact

```yaml
TradeExperienceArtifact:
  trade_id:
  instrument:
  venue:
  strategy_id:
  strategy_version:
  horizon:
  session:
  regime:
  volatility_regime:
  liquidity_regime:
  thesis:
  technical_features:
  macro_features:
  rate_features:
  news_context:
  sentiment_features:
  orderflow_features:
  options_features:
  entry:
  stop:
  targets:
  size:
  intended_risk_pct:
  spread_at_entry:
  slippage:
  latency:
  margin_used:
  mfe:
  mae:
  duration:
  pnl:
  r_multiple:
  exit_reason:
  thesis_correct:
  timing_quality:
  execution_quality:
  risk_quality:
  outcome_class:
  failure_mode:
  lessons:
```

## 6.3 Polarity

```text
POSITIVE:
Gold NY liquidity sweep + real yields falling + reclaim + futures confirmation

ANTI_PATTERN:
EURUSD London breakout inside Tier-1 US event blackout with elevated spread
```

A bad win can be an anti-pattern. A correctly executed loss can remain positive process evidence.

## 6.4 Knowledge Decay

```yaml
confidence:
sample_count:
created_at:
last_validated_at:
valid_regimes:
decay_rate:
freshness:
superseded_by:
```


# 7. GraphRAG Historical Analogue Engine

GraphRAG retrieves contextual analogues across:

```text
instrument
→ horizon
→ session
→ regime
→ volatility
→ liquidity
→ macro context
→ event type
→ chart structure
→ order flow
→ strategy
→ outcome
```

## 7.1 Nodes

```text
Instrument
Currency
Country
CentralBank
MacroEvent
Release
MarketRegime
Session
Strategy
StrategyVersion
Trade
ChartPattern
OrderFlowPattern
RiskEvent
ResearchPaper
DataSource
Model
Feature
Outcome
AntiPattern
```

## 7.2 Relationships

```text
IMPACTS
CORRELATED_WITH
LEADS
LAGS
INVALIDATES
CONFIRMS
TRADED_BY
OBSERVED_DURING
FAILED_DURING
WORKS_DURING
SUPERSEDES
DERIVED_FROM
SUPPORTED_BY
CONTRADICTED_BY
```

Correlations store window, regime, confidence and last validation.


# 8. Google Tool Integration

## Gemini
Use for chart-image interpretation, multimodal comparison and structured extraction. Visual chart analysis must be verified against trusted market data before autonomous execution.

## Deep Research
Use for macro-regime studies, policy-cycle research, gold/rates research, strategy literature surveys and event post-mortems.

```text
Deep Research
    ↓
ResearchPacket
    ↓
VEKL Admission
    ↓
Hypothesis
    ↓
Test
```

## NotebookLM
Maintain grounded specialist notebooks:

```text
EURUSD Macro
USDJPY / BoJ
Gold
US Indices
NFP / Labour
Inflation
Central Bank Language
Execution / Microstructure
```

NotebookLM is a research workspace. VEKL remains machine-operational memory.


# 9. Source Governance

## Tier A — Primary Authority
Central banks, statistical agencies, exchanges/venues, regulators, broker execution records.

## Tier B — Structured Market Data
Licensed market-data vendors and approved economic data providers.

## Tier C — Professional Research
Peer-reviewed or reputable institutional research.

## Tier D — Community/Social
Forums, social media, YouTube, public trading commentary.

Tier D can create a hypothesis but cannot become canonical trading truth without validation.

```text
SOURCE
  ↓
QUARANTINE
  ↓
CLASSIFICATION
  ↓
CLAIM EXTRACTION
  ↓
CROSS-SOURCE CHECK
  ↓
HISTORICAL / MARKET VALIDATION
  ↓
VEKL ADMISSION
```


# 10. Chart Intelligence

VAN should understand candles, wick/body structure, swings, HH/HL/LH/LL, channels, support/resistance, previous day/week/month levels, session highs/lows, breaks/retests, compression/expansion, liquidity sweeps, failed breakouts, volatility structure, divergence, VWAP, volume/profile where valid, and common indicators.

## ChartSetupFingerprint

```yaml
ChartSetupFingerprint:
  instrument:
  timeframe:
  trend:
  structure:
  location:
  pattern:
  candle_features:
  volatility_percentile:
  session:
  volume_features:
  orderflow_features:
  indicator_features:
  macro_state:
  event_proximity:
  timestamp:
```

## Indicators as Features

RSI, MACD, moving averages, ATR, ADX, Bollinger Bands, stochastic, Ichimoku, VWAP, pivots and volume profile are evidence features, not deterministic buy/sell commands.


# 11. Cross-Asset Causal/Dependency Graph

Examples:

```text
Fed expectations → US 2Y → USD → EURUSD / Gold / USDJPY
Real yields → Gold
Risk appetite → Equity indices / JPY / CHF
Energy prices → inflation / CAD / equity sectors
China growth → AUD / metals
VIX term structure → equity risk regime
```

Relationships are time-varying hypotheses:

```yaml
source:
target:
sign:
beta:
window:
regime:
confidence:
last_validated:
decay_rate:
```


# 12. Volatility and Options Intelligence

Use, where available:

- ATM implied volatility;
- volatility term structure;
- skew;
- risk reversals;
- expected move;
- convexity;
- implied vs realised volatility;
- event premium.

For US indices, use VIX-family term structure as risk context rather than a single VIX value.

Example:

```text
Implied >> Realised
→ market pricing large uncertainty
→ reduce risk unless strategy explicitly exploits event premium

Realised >> Implied
→ current movement exceeds priced risk
→ slippage/tail risk rises
```


# 13. Order Flow and Microstructure

For centralized futures references such as ES, NQ, GC and SI, use:

- L1;
- L2 depth;
- trade prints;
- aggressive flow;
- book imbalance;
- microprice;
- liquidity addition/removal;
- absorption;
- exhaustion;
- volume-at-price.

A CFD or spot trade may use futures as a reference subject to basis/venue differences.

Spot FX is decentralized; a single broker DOM must never be represented as total FX liquidity.


# 14. Specialist NFP/Event Trading Engine

NFP is a separate discipline.

## Pre-Event

```text
T-24h  build scenario tree
T-4h   refresh rates/options/positioning/expected move
T-60m  freeze eligible strategy set; tighten health checks
T-15m  event guard; reduce/cancel unsafe exposure if policy requires
T-1m   verify clock/feed/spread/account state
```

## NFPShockVector

```yaml
payroll_actual:
payroll_consensus:
payroll_surprise:
private_payroll_surprise:
revisions_1m:
revisions_2m:
unemployment_actual:
unemployment_surprise:
participation_surprise:
average_hourly_earnings_mom_surprise:
average_hourly_earnings_yoy_surprise:
average_weekly_hours_surprise:
household_employment_change:
sector_composition:
```

## NFPReactionVector

```yaml
us2y_bp:
us10y_bp:
real_yield_change:
dxy_return:
eurusd_return:
usdjpy_return:
gold_return:
es_return:
nq_return:
implied_vol_change:
```

## Strategy Families

- shock continuation;
- headline/internal divergence fade;
- rates-confirmed USD continuation;
- initial move failure/reclaim;
- gold yield-confirmation breakout;
- index rates-vs-growth interpretation;
- explicit no-trade ambiguity mode.

## Point-in-Time Macro Rule

Backtests use values available at that historical instant, including original releases and subsequent revisions as separate vintages.

Never backtest old NFP/CPI/GDP decisions using revised current databases as though the revisions were known then.


# 15. Central-Bank Language Intelligence

Maintain institution-specific language history for the Fed, ECB, BoE, BoJ and other relevant central banks.

Pipeline:

```text
official document
   ↓
semantic extraction
   ↓
phrase / topic change
   ↓
policy stance delta
   ↓
market-implied baseline
   ↓
surprise score
```

Focus on changes in inflation, employment, growth, financial conditions, balance sheet, forward guidance and uncertainty language.


# 16. Positioning Intelligence

Use COT, open interest, ETF flows, options skew and approved sentiment data as context.

Derived features:

```text
position percentile
weekly change
crowding score
leveraged-fund direction
asset-manager direction
open-interest trend
```

Weekly/lagged positioning data is not a scalping trigger.


# 17. Gold/Metals Expert Module

## Medium/Long Horizon

- real yields;
- nominal yields;
- USD;
- inflation expectations;
- Fed expectations;
- geopolitical risk;
- central-bank purchases;
- ETF flows;
- COMEX positioning;
- futures curve;
- volatility;
- global demand.

## Intraday

- GC futures order flow;
- DXY;
- US 2Y/10Y;
- London/NY structure;
- previous session levels;
- event proximity;
- spread/slippage;
- volatility expansion.

## Strategy Families

- real-yield trend;
- macro breakout;
- London liquidity sweep;
- NY reclaim/reversal;
- futures-confirmed spot breakout;
- event continuation;
- event failure/fade;
- multi-day macro swing.


# 18. FX Expert Module

## Macro

- rate differentials;
- expected policy paths;
- yield curves;
- inflation/growth differentials;
- central-bank divergence;
- risk sentiment;
- commodity linkages;
- positioning;
- options state.

## Session

- Asia range;
- London open;
- London fix;
- NY open;
- London/NY overlap;
- roll;
- month/quarter-end.

## Strategy Families

- trend pullback;
- session breakout;
- compression expansion;
- liquidity sweep/reclaim;
- mean reversion;
- carry/rates;
- macro divergence;
- event momentum;
- event reversal;
- multi-day macro swing.


# 19. Index Expert Module

Inputs:

- index futures;
- rates;
- yield curve;
- VIX/term structure;
- breadth;
- sectors;
- earnings;
- major constituents;
- overnight range;
- cash open;
- VWAP;
- order flow;
- implied move;
- event proximity.

Strategies:

- opening range breakout;
- VWAP trend;
- overnight inventory correction;
- liquidity sweep;
- volatility breakout;
- order-flow continuation;
- macro rates impulse;
- multi-day risk regime;
- post-FOMC/NFP continuation/reversal.


# 20. Deriv Architecture

## Real-Market Products
Use appropriate market features subject to product mechanics.

## Synthetic Indices
Keep isolated:

```text
REAL FX / INDICES / METALS
  macro / news / rates / positioning / order flow / technicals

DERIV SYNTHETICS
  product mechanics / tick statistics / specified volatility
  serial properties / contract payoff / execution / risk
```

Real-world macro events must not be treated as causal inputs for synthetic strategies unless the product explicitly depends on those markets.


# 21. Strategy Architecture

## StrategyCapsule

```yaml
strategy_id:
version:
instruments:
horizons:
eligible_regimes:
forbidden_regimes:
required_features:
entry_logic:
invalidation_logic:
stop_model:
target_model:
risk_limits:
execution_model:
event_rules:
training_period:
validation_period:
cost_model:
approved_at:
approval_status:
evidence_refs:
```

## States

```text
RESEARCH
BACKTEST
VALIDATION
DEMO
SHADOW
LIMITED_LIVE
CERTIFIED_LIVE
DEGRADED
SUSPENDED
RETIRED
```

## Champion/Challenger

```text
CHAMPION       certified live
CHALLENGER A   shadow
CHALLENGER B   demo
CHALLENGER C   research
```


# 22. Meta-Labeling and Opportunity Selection

A base strategy proposes direction/setup.

The meta-labeler decides:

```text
TRADE
WAIT
SKIP
REDUCE SIZE
REQUIRE CONFIRMATION
```

It uses regime fit, event proximity, spread, volatility, analogue quality, cross-market confirmation, model agreement, recent strategy health, order flow and execution conditions.


# 23. Ensemble and Model Governance

No single oracle model.

Combine deterministic rules, statistical models, supervised ML, regime models, probabilistic models, LLM reasoning and historical analogue retrieval.

Weight models by recent calibration, regime, horizon, data quality, historical performance and freshness.

Disagreement is a feature, not a bug.


# 24. Uncertainty & Abstention

```yaml
OpportunityAssessment:
  direction:
  expected_return:
  expected_r:
  probability_positive:
  confidence:
  uncertainty:
  regime_confidence:
  analogue_confidence:
  execution_confidence:
  model_disagreement:
  tail_risk:
  decision:
```

VATI must abstain when uncertainty or risk invalidates otherwise attractive signals.


# 25. Concept Drift and Strategy Half-Life

Track feature drift, label drift, residual drift, regime-distribution shift, execution drift, cost drift, calibration drift and edge decay.

```text
0.84 → 0.77 → 0.61 → 0.43
```

Below threshold:

```text
CERTIFIED_LIVE → DEGRADED → SHADOW
```


# 26. Backtesting and Validation

## Mandatory Bias Controls

- look-ahead;
- survivorship;
- revision;
- leakage;
- timestamp leakage;
- overfitting;
- parameter snooping;
- unrealistic fills;
- ignored spread/commission/latency/swap;
- selection bias.

## Validation Stack

1. unit tests;
2. deterministic replay;
3. in-sample exploration;
4. untouched out-of-sample;
5. rolling walk-forward;
6. purged/embargoed CV where appropriate;
7. combinatorial purged validation where appropriate;
8. parameter perturbation;
9. regime-specific evaluation;
10. Monte Carlo sequencing;
11. cost/slippage stress;
12. latency stress;
13. broker/feed variation;
14. demo/shadow trading.

## Falsification Laboratory

Attempt to destroy every candidate strategy before promotion.
Failed experiments are preserved in VEKL.


# 27. Deterministic Risk Authority

## Per-Trade Risk

```text
RiskCapital = Equity × AllowedRiskPct

RawSize =
RiskCapital /
(StopDistance × ValuePerPriceUnit)
```

Then:

```text
FinalSize =
RawSize
× RegimeMultiplier
× ConfidenceMultiplier
× VolatilityMultiplier
× LiquidityMultiplier
× EventRiskMultiplier
× CorrelationMultiplier
× DrawdownMultiplier
```

All multipliers are bounded.

## Portfolio Heat

Track:

```text
total_open_stop_risk
currency exposure
USD factor
rates factor
equity beta
real-yield factor
volatility factor
regional factor
event concentration
```

## Drawdown Governor

Example:

```text
DD 0–2%     normal
DD 2–4%     risk × 0.75
DD 4–6%     risk × 0.40; top-tier only
DD >6%      suspend live strategy group; diagnostics
```

Owner-configurable.

## Kill Switch Triggers

- max daily/weekly loss;
- equity drawdown;
- stale data;
- reconciliation failure;
- abnormal spread;
- reject storm;
- duplicate-order risk;
- time-sync fault;
- corrupt state;
- unauthorized account;
- venue disconnect;
- risk-store unavailable.


# 28. Trade Protection & Exit Intelligence

Supported:

- broker-side hard stop;
- structural stop;
- ATR/volatility stop;
- time stop;
- event stop;
- break-even transition;
- trailing/structure trail;
- partial take-profit;
- volatility target;
- signal deterioration exit;
- cross-market invalidation;
- catastrophic protection.

Canonical:

```text
strategy exit logic
+
broker-side catastrophe protection
```

VATI must never widen a mandatory protective stop simply because a trade is losing.


# 29. Execution Intelligence

Potential execution methods:

- market;
- limit;
- stop;
- stop-limit;
- passive limit;
- sliced/TWAP-like execution;
- wait-for-spread normalization;
- pullback entry.

## Execution Gate

```yaml
spread_ok:
depth_ok:
quote_age_ok:
slippage_estimate_ok:
broker_connected:
account_synced:
symbol_tradeable:
margin_ok:
duplicate_intent_absent:
```

## Idempotency

Every order intent includes:

```text
trade_intent_id
strategy_id
strategy_version
decision_hash
risk_snapshot_hash
market_snapshot_hash
idempotency_key
```


# 30. Transaction Cost Analysis

For every fill:

```text
decision price
arrival price
submitted price
fill price
spread cost
slippage
delay cost
fees
swap
adverse-selection estimate
implementation shortfall
```

VEKL should learn execution-specific anti-patterns and improvements.


# 31. Market Integrity / Abnormal Conditions

Detect:

- cross-feed divergence;
- spread explosion;
- stale quotes;
- quote instability;
- liquidity withdrawal;
- extreme wick/tick behavior;
- abnormal order-book behavior;
- correlation break;
- execution latency spike;
- broker rejects.

State machine:

```text
NORMAL
ELEVATED
ABNORMAL
HALTED
```

Use “abnormal market state,” not unsupported claims of manipulation.


# 32. Real-Time Learning Boundaries

VATI may adapt live by changing certified strategy weights, regime probabilities, confidence, risk and suspension state.

VATI may not:

```text
invent strategy → immediately trade live
```

New strategies follow:

```text
HYPOTHESIS
→ RESEARCH
→ BACKTEST
→ FALSIFICATION
→ DEMO
→ SHADOW
→ LIMITED LIVE
→ CERTIFIED LIVE
```


# 33. Trade Review & Counterfactual Learning

Every closed trade asks:

- Was thesis valid?
- Was setup correct?
- Was timing correct?
- Was size correct?
- Was stop correct?
- Was exit correct?
- Was execution poor?
- Did regime change?
- Did an event invalidate the setup?

Classify:

```text
GOOD WIN
GOOD LOSS
BAD WIN
BAD LOSS
EXECUTION FAILURE
DATA FAILURE
RISK FAILURE
```

Counterfactuals may test alternative entries, exits, stops, sizing and no-trade outcomes. They are stored as evidence, not automatic causal truth.


# 34. Trading Confidence Matrix

Example:

```text
EURUSD

Macro          0.83 bullish
Rates          0.77 bullish
Technical      0.71 bullish
Order Flow     0.59 bullish
Positioning    0.48 neutral
Options        0.68 bullish
Execution      0.91 good
Event Risk     HIGH

Net Edge       0.69
Uncertainty    0.31
Decision       WAIT
```


# 35. VAN Semantic Trading Visual States

| State | Aura / glass meaning |
|---|---|
| Soft cyan | passive market surveillance |
| Bright cyan | valid setup developing |
| Blue-white | active high-confidence analysis |
| Violet-blue | regime/model disagreement |
| Amber | event/volatility danger |
| Cyan-green | live trade healthy and protected |
| Green pulse | trade closed successfully according to plan |
| Amber-red | thesis deterioration / risk intervention |
| Red | kill switch / execution fault / risk breach |
| Dim silver-blue | intentionally flat / no edge |

The color system communicates operational state and risk, not emotion or gambling stimulus.


# 36. Owner Interaction Model

VAN explanations should expose:

- current regime;
- current horizon;
- candidate setup;
- confirmation/missing confirmation;
- event risk;
- risk state;
- what would change the decision.

Live trade summary:

```text
XAUUSD LONG
Strategy: GOLD-NY-RECLAIM-04
Entry: ...
Stop: ...
Target: ...
Risk: 0.35% equity
Portfolio heat after trade: 1.10%
Event risk: Low
Execution: spread/slippage acceptable
Authority: mandate / approval required
```


# 37. Authorization Modes

```text
OBSERVE
ADVISOR
DEMO_TRADER
SHADOW_TRADER
LIMITED_LIVE
AUTONOMOUS_LIVE
HALTED
```

Recommended:

```text
OBSERVE → DEMO → SHADOW → LIMITED LIVE → AUTONOMOUS LIVE
```


# 38. Live Trading Mandate

```yaml
TradingMandate:
  account_id_alias: fx_primary
  instruments:
    - EURUSD
    - GBPUSD
    - USDJPY
    - XAUUSD
  max_risk_per_trade: 0.50%
  max_open_stop_risk: 1.50%
  max_daily_loss: 2.00%
  max_weekly_drawdown: 4.00%
  max_consecutive_losses: 4
  max_usd_factor: 1.00%
  tier1_event_policy: strategy_specific
  allowed_strategies:
    - FX-TREND-03
    - FX-LONDON-BREAKOUT-04
    - GOLD-NY-RECLAIM-04
  forbidden:
    - martingale
    - unlimited_grid
    - stop_removal
    - revenge_risk_increase
```

Mandates are versioned and auditable.


# 39. Forbidden Behaviors

Hard-prohibit:

- martingale;
- unlimited averaging down;
- revenge trading;
- risk doubling after losses;
- removing mandatory stops;
- trading with unverifiable account state;
- trading stale data;
- duplicate orders;
- silent strategy mutation;
- unvalidated research changing live behavior;
- unbounded leverage;
- treating one broker DOM as total FX liquidity;
- applying macro causality to Deriv synthetics without valid linkage.


# 40. System Services

```text
vatii-market-ingest
vatii-market-state
vatii-regime-engine
vatii-chart-intelligence
vatii-news-intelligence
vatii-event-engine
vatii-nfp-engine
vatii-options-intelligence
vatii-orderflow
vatii-positioning
vatii-strategy-registry
vatii-strategy-arbiter
vatii-horizon-arbiter
vatii-meta-labeler
vatii-opportunity-engine
vatii-risk-authority
vatii-execution-router
vatii-mt5-adapter
vatii-deriv-adapter
vatii-reconciliation
vatii-tca
vatii-trade-review
vatii-vekl-admission
vatii-graphrag
vatii-research-orchestrator
vatii-model-registry
vatii-observability
```

These may initially be modular processes/packages rather than network microservices.


# 41. Core Event Contracts

## TradeIntent

```json
{
  "trade_intent_id": "uuid",
  "account_alias": "fx_primary",
  "venue": "mt5",
  "symbol": "EURUSD",
  "direction": "LONG",
  "strategy_id": "FX-LONDON-BREAKOUT-04",
  "strategy_version": "4.2.1",
  "entry_type": "STOP",
  "entry": 1.10010,
  "stop": 1.09790,
  "targets": [1.10340, 1.10600],
  "requested_risk_pct": 0.0040,
  "max_slippage": 0.00010,
  "expires_at": "...",
  "market_snapshot_hash": "...",
  "thesis_hash": "...",
  "owner_authority": "MANDATE",
  "idempotency_key": "..."
}
```

## RiskDecision

```json
{
  "trade_intent_id": "uuid",
  "decision": "APPROVED",
  "approved_size": 0.42,
  "approved_risk_pct": 0.0032,
  "portfolio_heat_before": 0.0061,
  "portfolio_heat_after": 0.0093,
  "constraints": [],
  "risk_policy_version": "1.0.0",
  "risk_snapshot_hash": "..."
}
```

## ExecutionReceipt

```json
{
  "trade_intent_id": "uuid",
  "broker_order_id": "...",
  "status": "FILLED",
  "filled_qty": 0.42,
  "average_fill": 1.10012,
  "spread_cost": "...",
  "slippage": "...",
  "broker_time": "...",
  "received_time": "...",
  "receipt_hash": "..."
}
```


# 42. Storage Architecture

## Hot State
Live positions, account state, market state, risk state and active signals.

## Event Ledger
Append-only market events, decisions, order intents, broker responses, fills, position changes, exits and reviews.

## Market Data Lake
Prefer columnar formats such as Parquet for bars, ticks, quotes, depth, macro vintages and features.

Partition:

```text
source / market / instrument / date / data_type
```

## VEKL
Stores admitted knowledge and lineage, not raw high-frequency tick exhaust.


# 43. Security

Credential planes:

```text
MT5 account
Deriv OAuth/PAT
market data
Google research
VAN owner identity
service identity
```

No broker token enters an LLM prompt.

MT5 boundary:

- private network;
- mTLS;
- allowlisted identity;
- signed requests;
- idempotency;
- replay protection;
- no public unauthenticated listener.

Secrets remain encrypted, rotated and absent from Git.


# 44. Resilience and Recovery

Startup:

```text
connect broker
↓
read balance/equity
↓
read open positions
↓
read pending orders
↓
reconcile against event ledger
↓
resolve uncertainty
↓
permit new orders
```

If market data or broker state cannot be verified:

```text
NEW_TRADES_BLOCKED
```

Existing positions rely on pre-defined deterministic protection/failover.


# 45. Observability

Track:

- P&L;
- realised/unrealised R;
- drawdown;
- strategy expectancy;
- win/loss distribution;
- slippage;
- spread;
- fill rate;
- latency;
- rejects;
- data freshness;
- feed divergence;
- regime confidence;
- model calibration;
- strategy decay;
- portfolio heat;
- event exposure.

Every trade must correlate:

```text
market snapshot
→ strategy decision
→ risk decision
→ execution receipt
→ trade result
```


# 46. Research Tooling

## OpenBB
Unified research/data abstraction where licensing and provider entitlements permit.

## Qlib
ML research, market dynamics, feature research and concept-drift experiments.

## Optuna
Controlled hyperparameter/model optimization. Output is a candidate, never live truth.

## Riskfolio-Lib
Advanced portfolio/risk research and constrained allocation.

## TradingView
Human-readable chart studies, Pine prototypes, alerts and webhook hypothesis ingestion. Never execution authority.

## Professional Order-Flow Tools
Bookmap-like tooling is useful for operator/research analysis; production automation should prefer licensed machine-readable feeds.


# 47. Research Integrity

Every experiment records:

```text
code commit
dataset hash
data vintage
feature version
model version
strategy version
parameters
random seeds
cost model
result hash
```

Statuses:

```text
PROPOSED
RUNNING
FAILED
PROMISING
REPRODUCED
VALIDATED
REJECTED
PROMOTED
```

All trials are retained to reduce selection/cherry-picking bias.


# 48. Performance Metrics

Evaluate a vector, not one metric:

- net return;
- expectancy;
- R distribution;
- Sharpe;
- Sortino;
- Calmar;
- max/average drawdown;
- recovery duration;
- CVaR/expected shortfall;
- tail losses;
- profit factor;
- win rate;
- payoff ratio;
- MAE/MFE;
- turnover;
- implementation shortfall;
- slippage;
- trade count;
- regime stability;
- parameter stability.


# 49. Repository Layout

```text
van/
└── trading/
    ├── README.md
    ├── architecture/
    ├── contracts/
    ├── market_data/
    │   ├── ingestion/
    │   ├── normalization/
    │   ├── catalog/
    │   └── quality/
    ├── intelligence/
    │   ├── regimes/
    │   ├── macro/
    │   ├── rates/
    │   ├── options/
    │   ├── chart/
    │   ├── orderflow/
    │   ├── positioning/
    │   ├── news/
    │   └── events/
    ├── nfp/
    ├── strategies/
    │   ├── registry/
    │   ├── forex/
    │   ├── indices/
    │   ├── metals/
    │   └── deriv_synthetic/
    ├── research/
    │   ├── qlib/
    │   ├── optimization/
    │   ├── validation/
    │   └── falsification/
    ├── vekl/
    │   ├── schemas/
    │   ├── admission/
    │   └── graphrag/
    ├── risk/
    ├── execution/
    │   ├── core/
    │   ├── mt5/
    │   ├── deriv/
    │   └── reconciliation/
    ├── tca/
    ├── review/
    ├── backtest/
    ├── observability/
    ├── security/
    ├── tests/
    └── docs/
```


# 50. Development Plan

## Phase 0 — Canon & Risk Boundary
Deliver ADRs, mandate schema, risk contracts, instrument registry, account aliases, forbidden behaviors and kill switch.

**Gate:** no execution work before deterministic risk contracts are testable.

## Phase 1 — Research/Data Foundation
Implement data catalog, point-in-time macro, quality checks, normalization, sessions/calendars and lineage.

**Gate:** deterministic replay and timestamps verified.

## Phase 2 — VEKL Trading Intelligence
Implement trading artifacts, polarity, decay, admission, source quality and GraphRAG.

**Gate:** research conclusions trace to evidence.

## Phase 3 — Core Backtesting
Integrate NautilusTrader behind VAN-owned interfaces.

**Gate:** identical inputs produce deterministic results.

## Phase 4 — Risk Authority
Implement sizing, margin, portfolio heat, factors, drawdown governor and kill switch.

**Gate:** property tests prove mandate cannot be exceeded.

## Phase 5 — MT5 Demo Integration
Implement account/symbol sync, orders, positions, SL/TP, recovery, reconciliation and authenticated bridge.

**Gate:** disconnect/restart creates no duplicate or orphan VAN orders.

## Phase 6 — Deriv Demo Integration
Implement auth, WebSocket lifecycle, market data, contract operations, reconciliation and synthetic classification.

**Gate:** demo restart recovery certified.

## Phase 7 — Chart/Technical Intelligence
Implement structure, indicators, fingerprints, multimodal verification and TradingView research gateway.

**Gate:** screenshot-only signals cannot autonomously trade.

## Phase 8 — Regime/Horizon/Meta-Labeling
Implement regime engine, horizon arbiter, strategy arbiter, meta-labeler, uncertainty and abstention.

**Gate:** system reliably produces `NO_TRADE`.

## Phase 9 — Macro/NFP Engine
Implement event calendars, point-in-time releases, surprise/reaction vectors, analogue retrieval and event strategies.

**Gate:** historical replays use true historical vintages and realistic costs.

## Phase 10 — Metals & Indices
Add gold real-yield model, futures order flow, index volatility/term-structure, VWAP/session models.

## Phase 11 — Research Automation
Integrate OpenBB, Qlib, Optuna, Riskfolio, Google research and champion/challenger.

**Gate:** research output cannot reach broker without promotion artifact.

## Phase 12 — Execution Intelligence/TCA
Implement slippage models, order-type selection and execution-learning loop.

**Gate:** expected net edge remains positive after cost.

## Phase 13 — Shadow Trading
Run live full-stack decisions without real orders across multiple regimes.

## Phase 14 — Limited Live
Use minimal capital/risk, limited symbols/strategies, strict owner mandate.

## Phase 15 — Autonomous Mandate
Only after all earlier gates and live evidence.


# 51. Testing Strategy

## Unit
Pip/tick calculations, sizing, margin, stops, event parsing, time zones and contract mapping.

## Property
- approved risk never exceeds mandate;
- duplicate intent never creates duplicate order;
- unknown account cannot trade;
- stale data blocks new trades.

## Replay
Market feeds, macro releases, broker messages and order responses.

## Failure Injection
Broker disconnect, delayed quotes, duplicates, reordered events, Deriv reconnect, MT5 restart, database outage, clock skew, huge spread, partial fills and rejected stops.

## Strategy Tests
Regime eligibility, event windows, entry/exit, sizing, cost sensitivity and stop behavior.


# 52. Production Acceptance Gates

Strategy certification:

```text
[ ] data lineage complete
[ ] point-in-time integrity
[ ] no look-ahead leakage
[ ] realistic costs
[ ] out-of-sample positive expectancy
[ ] walk-forward stability
[ ] parameter sensitivity acceptable
[ ] multi-regime evaluation
[ ] tail loss acceptable
[ ] drawdown within mandate
[ ] demo/shadow evidence
[ ] execution adapter certified
[ ] strategy capsule signed
[ ] risk policy compatible
[ ] rollback available
```

Platform certification:

```text
[ ] restart reconciliation
[ ] idempotent execution
[ ] no credential leakage
[ ] kill switch tested
[ ] stale feed blocks trading
[ ] risk service fails closed
[ ] immutable audit
[ ] owner mandate enforced
```


# 53. Initial Instrument Rollout

## Stage A
```text
EURUSD
GBPUSD
USDJPY
XAUUSD
```

## Stage B
```text
AUDUSD
USDCAD
USDCHF
EURJPY
XAGUSD
```

## Stage C
```text
US500 / ES reference
USTEC / NQ reference
GER40
```

Broker symbol aliases are normalized centrally.


# 54. Initial Strategy Rollout

Begin with interpretable candidates:

```text
FX-TREND-PULLBACK
FX-LONDON-BREAKOUT
FX-COMPRESSION-EXPANSION
FX-SWEEP-RECLAIM
GOLD-NY-RECLAIM
GOLD-RATES-CONTINUATION
INDEX-OPENING-RANGE
INDEX-VWAP-TREND
```

Later:

```text
NFP-CONTINUATION
NFP-DIVERGENCE-REVERSAL
FOMC-POST-REACTION
OPTIONS-EVENT-REGIME
ORDERFLOW-SCALP
```


# 55. Product Milestones

## VATI-M1 — Research-to-Demo
Requires live market ingestion, VEKL schema, strategy registry, risk authority, Nautilus backtesting, MT5 demo, Deriv demo, initial FX/gold strategies, journal, TCA and VAN analysis.

Must complete:

```text
observe → analyze → propose → risk-check → demo execute
→ reconcile → review → learn
```

## VATI-M2 — Adaptive Specialist
Adds regime/horizon/meta-labeling, NFP, point-in-time macro, options/volatility, order flow, GraphRAG analogues, concept drift and champion/challenger.

## VATI-M3 — Limited Live
Adds hardened production credentials, signed live mandate, low risk budget and continuous live reconciliation.


# 56. Capital Scaling

Capital rises only when:

```text
live sample increases
AND live expectancy remains positive
AND drawdown remains acceptable
AND execution cost matches model
AND strategy calibration remains valid
AND portfolio capacity permits
```

Changes are stepwise, bounded and reversible.


# 57. Primary Research Sources

Prefer authoritative market truth from:

- Bank for International Settlements;
- U.S. Bureau of Labor Statistics;
- Federal Reserve;
- FRED/ALFRED;
- CFTC;
- CME Group;
- Cboe;
- World Gold Council;
- MetaQuotes/MQL5;
- Deriv developer documentation;
- cTrader Open API;
- NautilusTrader documentation;
- TradingView official docs;
- OpenBB documentation;
- Microsoft Qlib;
- Optuna;
- Riskfolio-Lib.

Community/social research is hypothesis input, not canonical truth.


# 58. Technical Source Notes

As of this revision:

- NautilusTrader documents a production-grade Rust-native multi-asset/multi-venue architecture spanning deterministic simulation, portfolio/risk and live execution with Python as a control plane.
- Its backtesting documentation distinguishes bars, trades, L1, L2 and L3 and warns that bars cannot model spread, depth, queue position or exact intrabar order.
- MetaTrader 5's official Python integration supports order submission and margin calculation; MQL5 exposes a built-in economic calendar.
- Deriv's current developer stack uses REST plus WebSocket for account/trading functions and supports OAuth/PAT patterns.
- Deriv states synthetic indices are generated and unaffected by real-world news/market volatility; they therefore require isolated strategy logic.
- TradingView supports alert/webhook workflows; VATI treats these as signals, not execution authority.
- ALFRED/FRED provides historical vintages/revision dates for point-in-time macro research.
- BLS publishes Employment Situation release schedules.
- Cboe provides volatility term-structure data; CME provides cross-asset volatility/rate-expectation resources.
- World Gold Council publishes gold performance, volatility, correlations, volumes, ETF, reserves and futures-positioning datasets.
- cTrader Open API supports real-time market data and demo/live trading operations.
- OpenBB, Qlib, Optuna and Riskfolio-Lib are research candidates for data integration, ML research, optimization and portfolio/risk research.

All capabilities, licenses and API terms must be re-verified before implementation/production.


# 59. Non-Functional Requirements

## Performance
Latency-sensitive trading must not wait on LLM or deep research. Research is asynchronous.

## Determinism
Same market events + same strategy/model/risk versions should produce the same deterministic decision path except documented seeded stochastic components.

## Auditability
Every live trade must answer:

```text
Why?
Which data?
Which strategy?
Which model?
Which regime?
Which risk calculation?
Which authorization?
What did the broker return?
What did VAN learn?
```

## Fail Closed
Unknown or unverifiable state produces:

```text
NO NEW TRADE
```


# 60. Canonical Decisions

1. VAN remains a Hermes bot.
2. Hermes orchestrates but does not override deterministic risk.
3. VEKL/GraphRAG is durable trading research/experience memory.
4. LLMs do not send broker orders directly.
5. Strategy selection is regime and horizon adaptive.
6. Scalping and swing trading are distinct disciplines.
7. NFP/event trading is a first-class subsystem.
8. Macro backtests use point-in-time vintages.
9. Execution-sensitive strategies require granular data.
10. MT5 and Deriv are separate venue adapters.
11. Deriv synthetics are isolated from real-world macro causality.
12. Dynamic position sizing is mandatory.
13. Portfolio/factor exposure outranks ticket-level thinking.
14. Stops/protection/kill switches are deterministic.
15. Live strategies are versioned and certified.
16. Research enters through admission/validation.
17. Failed research is retained.
18. Strategy decay can automatically demote.
19. No-trade is a valid action.
20. The objective is net expectancy after costs and risk.


# 61. Completion Definition

Production capability means VAN can repeatedly:

```text
INGEST
  ↓
VERIFY DATA
  ↓
UNDERSTAND MARKET STATE
  ↓
SELECT DISCIPLINE
  ↓
SELECT HORIZON
  ↓
SELECT CERTIFIED STRATEGY
  ↓
ASSESS UNCERTAINTY
  ↓
CALCULATE PORTFOLIO-AWARE RISK
  ↓
CHOOSE EXECUTION
  ↓
PLACE IDEMPOTENT ORDER
  ↓
VERIFY BROKER STATE
  ↓
PROTECT POSITION
  ↓
MANAGE / EXIT
  ↓
RECONCILE
  ↓
MEASURE COST
  ↓
REVIEW OUTCOME
  ↓
ADMIT VERIFIED LEARNING TO VEKL
```

under normal operation, restarts, feed failures, broker failures, high-impact events and regime transitions.


# 62. Final Principle

The defining characteristic of an expert VATI trader is not that it always has a prediction.

It is that it can determine:

> **what kind of market exists, what is driving it, what information is trustworthy, which trading discipline currently has an edge, which horizon best expresses that edge, how uncertain the edge is, what price makes the trade worthwhile, how much capital should be exposed, how the order should be executed, when the thesis has failed, and when remaining flat has the highest expected value.**

That is the production target for VAN Adaptive Trading Intelligence.
