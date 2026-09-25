# VAN EXPERT TRADING TERMINAL & UX BLUEPRINT — REV 1.1

Status: canonical implementation blueprint candidate
Repository: Vanguduza/Van
Primary client: Android / Jetpack Compose
Trading authority: VATI deterministic pipeline
Rich chart plane: OpenAlgo Charts-derived local runtime
Jev/LLM role: read-only/subordinate cognition and explanation
Date: 2026-09-25

## 1. Mission

Upgrade VAN from an advanced owner trading monitor into a professional mobile trading workstation that combines:

- TradingView-class charting, indicators, drawings, profiles, replay and workspaces.
- MetaTrader-class market navigation, watchlists, positions, history and depth.
- VAN-native deterministic evidence, strategy lineage, owner authority and auditability.
- VATI-native candidate, risk, sizing, protection, reconciliation, TCA and learning truth.
- A first-class Live Trading Analyst that explains every supported chart, candidate, open trade and closed trade in real time using bounded Jev System-1 judgments plus a reasoning LLM.

The Android application remains an owner interaction and evidence plane. It is not a second trading engine.

## 2. Hard authority boundary

The following relationships are invariant:

```text
MODEL != RISK AUTHORITY
JEV != RISK AUTHORITY
ANDROID != NUMERIC SIZING AUTHORITY
CHART ENGINE != ORDER SENDER
HERMES != BROKER ADAPTER
SIGNAL != ORDER
CANDIDATE != ORDER
EXPLANATION != EXECUTION AUTHORITY
MODEL CONFIDENCE != VATI ELIGIBILITY
```

Every executable trade still follows the VATI chain:

```text
market data
 -> market state
 -> strategy
 -> candidate
 -> allocation
 -> Risk Authority
 -> TradeIntent
 -> Execution Router
 -> broker adapter
 -> execution receipt
 -> protection verification
 -> reconciliation
 -> TCA
 -> review
 -> learning
```

No feature in this blueprint may bypass that chain.

## 3. Primary owner navigation

The owner-facing trading navigation converges on five destinations:

- Home
- Markets
- Chart
- Trades
- Intelligence

Existing routes remain reachable while the migration is staged.

### Home
Portfolio equity, P&L, heat, drawdown, accounts, open exposure, VATI status, active events, recent execution quality, potential-trade summary and Needs Your Attention.

### Markets
Watchlists, search, market groups, recent instruments, movers, volatility, candidate instruments, session state and market-data health.

### Chart
Persistent current-instrument workspace with rich charting, analysis, depth, VATI state and Live Trading Analyst.

### Trades
Open, pending, recent executions, closed trades and account scope.

### Intelligence
Potential trades, strategies, market state, cognition, research, TCA, reviews and learning.

## 4. Instrument Terminal

The Instrument Terminal is the central expert surface.

Portrait layout:

```text
EURUSD · FXCM                         LIVE
1.08442 +0.32%             spread .2 / 83ms
------------------------------------------------
1m 5m 15m 1H 4H D        Indicators  Draw
                                                 
               RICH CHART                        
                                                 
ENTRY -----------------------------------------
STOP  -----------------------------------------
TP    -----------------------------------------
candidate / event / execution overlays
------------------------------------------------
Chart | Depth | Analyst | Trade | Risk
------------------------------------------------
VATI: TRENDING · thesis STRONGER · eligible LIVE
Jev: SUPPORTS · structured confidence HIGH
LLM: "Trend remains intact; event risk is the main
      reason additional exposure is not preferred."
```

Landscape becomes a multi-panel expert workspace rather than a rotated phone screen.

Supported persistent workspace presets:

- Price Action
- Multi-Timeframe Analysis
- Order Flow
- Position Management
- VATI Intelligence
- Live Analyst
- Replay
- Execution Review

## 5. Rich chart plane

OpenAlgo Charts is the preferred chart-engine donor because it is Apache-2.0 and materially extends VAN beyond the current native candlestick renderer.

Target capabilities:

- candlestick / OHLC / line / area / Heikin-Ashi;
- multiple panes;
- indicator templates;
- drawing tools;
- entry/stop/target overlays;
- VATI candidate zones;
- event markers;
- execution markers;
- TCA markers;
- volume profile;
- market profile/TPO;
- footprint/order-flow views when feed data supports them;
- DOM;
- replay;
- chart linking;
- persistent workspaces;
- mobile and landscape controls.

The chart runtime is locally bundled and hosted by a hardened Android bridge.

The existing native `TradeChartCanvas` remains for cards, degraded mode, offline fallback, deterministic evidence rendering and low-memory operation.

## 6. Chart bridge security

The chart runtime is an untrusted presentation subsystem.

Allowed input:

- bars;
- quotes;
- depth;
- VATI indicators;
- positions;
- candidate state;
- risk overlays;
- events;
- fills;
- TCA;
- strategy overlays;
- display-only indicators.

Allowed output:

- symbol/timeframe selection;
- crosshair selection;
- indicator/drawing changes;
- workspace changes;
- open candidate/position;
- request an owner intent draft;
- request Live Analyst explanation.

Forbidden bridge methods:

- placeOrder;
- modifyOrder;
- cancelOrder;
- closePosition;
- increasePosition;
- setLeverage;
- changeRiskLimit;
- sendBrokerCommand.

## 7. Markets and watchlists

Create first-class market discovery.

Owner watchlists may include:
- FX Majors
- Metals
- ZSE/VFEX
- High Conviction
- Research

System dynamic watchlists include:
- Candidate LIVE
- Candidate WAIT
- Open Exposure
- Weakening Positions
- Event Risk
- Abnormal Spread
- Research Needed

Every instrument row carries symbol, venue, price, change, spread, market state, freshness, candidate state and open-position state.

## 8. Depth and DOM

VAN exposes both compact mobile depth and a professional landscape DOM.

Depth is primarily observational. Depth-derived analytics remain presentation evidence unless VATI itself adopts the same feature through its governed pipeline.

## 9. Indicator classes

Three classes are visually distinguished:

1. Presentation indicators — user/workspace only.
2. VATI indicators — values used by VATI and accompanied by source/version/freshness.
3. Research indicators — experimental and clearly labelled RESEARCH.

Adding an indicator to a chart never changes production strategy parameters.

## 10. Potential Trades 2.0

Each candidate shows:

- VATI eligibility;
- strategy;
- thesis;
- net edge;
- uncertainty;
- multi-timeframe agreement;
- supports;
- contrary evidence;
- risk requirement;
- what would make it eligible;
- invalidation;
- evidence count;
- freshness;
- Jev structured assessment;
- Live Analyst explanation.

No candidate displays a direct BUY/SELL execution control.

## 11. Position Management 2.0

Tap an open position for a compact sheet containing:

- direction;
- live P&L and R;
- entry/current;
- size readback;
- initial and remaining risk;
- stop/target;
- protection state;
- thesis state;
- strategy;
- Jev/LLM current explanation.

Full position view contains Chart, Thesis, Evidence, Lifecycle, Risk, Execution, TCA, Timeline and Live Analyst.

VATI lifecycle proposals such as HOLD, ADD, REDUCE, MOVE_PROTECTION, PARTIAL_TAKE and EXIT are rendered as proposals. Android does not invent the quantity.

## 12. Risk Command Centre

Expose current/limit/remaining for:

- portfolio heat;
- per-trade risk;
- daily loss;
- weekly drawdown;
- currency legs;
- concentration;
- correlation;
- margin;
- position count;
- protection coverage;
- data integrity;
- broker connectivity;
- reconciliation.

Near-limit conditions become Attention items.

## 13. TCA and execution quality

Per-trade and aggregate views expose:

- requested/quoted/filled;
- slippage;
- spread;
- latency;
- partial fills;
- reject rate;
- fill rate;
- broker/venue;
- order type;
- expected vs realised execution;
- execution-quality classification.

## 14. Deterministic trade timeline and replay

Every trade exposes a ledger-derived timeline from candidate discovery through review.

Historical replay synchronizes:
- price;
- market state;
- VATI indicators;
- candidate state;
- risk decision;
- execution;
- protection;
- lifecycle;
- events;
- exit;
- TCA;
- review.

Replay uses recorded historical truth only. Present-day LLM interpretation is labelled as retrospective and is never presented as what the system knew at the time.

# 15. LIVE TRADING ANALYST — JEV + LLM

## 15.1 Purpose

Every supported chart, candidate, open trade and closed trade SHALL expose a real-time explanation layer answering:

- What is happening?
- Which strategy applies?
- Why does it apply?
- Which indicators/evidence support it?
- What contradicts it?
- What changed since the last explanation?
- What is VATI currently doing: LIVE / WAIT / SKIP / REDUCE / EXIT?
- Why is VATI in that state?
- What would change the decision?
- What would invalidate the thesis?
- What is the current risk context?
- Is Jev aligned, conflicting or abstaining?
- How fresh is the explanation?

This is not an autonomous trading engine.

## 15.2 Two-speed cognition

### Jev — fast structured System-1 layer

Jev handles bounded typed judgments such as:

- regime classification;
- setup-quality classification;
- thesis-health classification;
- multi-timeframe agreement summary;
- execution/TCA condition;
- volatility/liquidity classification;
- candidate-state explanation labels;
- change detection between consecutive snapshots.

Jev output remains `authority_effect=NONE`.

It reports one of:

- JEV_SUPPORTS
- JEV_CONFLICTS
- JEV_ABSTAINS
- JEV_UNAVAILABLE

A conflict increases uncertainty; it can never increase risk.

### Reasoning LLM — explanatory System-2 layer

The LLM receives authoritative VATI read models plus the permitted Jev result and turns them into owner-readable explanation.

It does not compute authoritative size, eligibility, stop, leverage, mandate or route.

Its narrative must separate:

- FACT — authoritative read-model value;
- VATI — deterministic decision/state;
- JEV — structured subordinate assessment;
- INTERPRETATION — LLM explanation;
- UNKNOWN — missing/stale/unsupported information.

## 15.3 Live Analyst surfaces

The Analyst appears in four places.

### A. Chart Analyst strip

Collapsed:
```text
ANALYST
TRENDING · VATI WAIT · JEV SUPPORTS
Event proximity is the only active blocker.
updated 3s ago
```

Expanded:
- current state;
- strategy;
- setup;
- supports;
- against;
- change since previous snapshot;
- decision explanation;
- what would change it;
- invalidation;
- risk context;
- data/Jev/LLM freshness.

### B. Candidate Analyst
Explains why a potential trade exists, why it is eligible or blocked, what evidence is missing and what would invalidate it.

### C. Position Analyst
Explains why the current trade remains intact/stronger/weaker/invalidated, what risk has changed, why VATI proposes HOLD/ADD/REDUCE/etc., and what market evidence drove that change.

### D. Trade Review Analyst
Explains closed trades using the sealed historical record plus clearly labelled retrospective commentary.

## 15.4 Refresh model

The Live Analyst is event-driven, not free-running token spam.

A new explanation is eligible when one or more meaningful inputs change:

- VATI candidate state;
- thesis state;
- market regime;
- significant indicator state;
- event proximity band;
- spread/liquidity state;
- protection state;
- position lifecycle proposal;
- execution/TCA state;
- material risk headroom;
- owner changes timeframe/symbol and requests explanation.

Debounce/cooldown rules prevent repeated LLM calls for numerically insignificant ticks.

Jev can refresh at a tighter bounded cadence than the LLM where its module deadline permits.

The UI may update authoritative numeric values continuously even while the narrative remains unchanged.

## 15.5 Explanation freshness

Every analysis artifact carries:

- generated_at;
- valid_until;
- source snapshot hash;
- market data timestamp;
- VATI read-model version;
- strategy version;
- Jev module revision/status;
- LLM provider/model lineage;
- authority_effect=NONE.

States:
- LIVE
- AGING
- STALE
- MODEL_UNAVAILABLE
- JEV_ABSTAINS
- DEGRADED

A stale narrative remains visible only with a visible STALE badge and never as current advice.

## 15.6 Context contract

The LLM receives a bounded structured packet, not arbitrary app state.

Minimum packet:

```json
{
  "instrument": {},
  "account_alias": "...",
  "market_state": {},
  "candidate": {},
  "position": {},
  "strategy": {},
  "vtil_activation": {},
  "risk": {},
  "events": [],
  "indicators": {},
  "execution_quality": {},
  "timeline_tail": [],
  "data_freshness": {},
  "jev": {},
  "requested_view": {
    "timeframe": "...",
    "chart_window": {}
  }
}
```

Credentials and secret account identifiers never enter the packet.

## 15.7 Output contract

The LLM returns structured explanation plus narrative:

```json
{
  "schema": "van-live-trading-analysis/1.0",
  "summary": "...",
  "vanti_state": "WAIT",
  "strategy": {
    "id": "...",
    "why_fit": "..."
  },
  "supports": [],
  "against": [],
  "changed": [],
  "what_would_change_decision": [],
  "invalidation": [],
  "risk_commentary": "...",
  "jev_relationship": "JEV_SUPPORTS",
  "uncertainty": "...",
  "facts_used": [],
  "unknowns": [],
  "generated_at": "...",
  "valid_until": "...",
  "authority_effect": "NONE"
}
```

Typo protection: production schema field SHALL be `vati_state`, not `vanti_state`.

## 15.8 Deterministic claim verifier

Before Android receives the narrative, a verifier checks:

- every numeric claim matches an authoritative field or is omitted;
- no size is invented;
- no stop/target is invented;
- no unsupported probability-of-profit is produced;
- no model statement contradicts the current VATI decision;
- no action is represented as approved unless Risk Authority says so;
- authority_effect is NONE;
- source snapshot hash is present;
- TTL is valid.

Failed verification produces no narrative. UI falls back to authoritative VATI facts.

## 15.9 Conversational drill-down

Every Analyst panel exposes `Ask VAN`.

Example:
- Why are we waiting?
- Why did the thesis weaken?
- Which timeframe disagrees?
- What changed in the last 10 minutes?
- Why is ADD not allowed?
- Show evidence for the strategy.
- Explain the stop without changing it.
- Compare this trade with similar historical episodes.

The current instrument/trade context is attached automatically.

## 15.10 Jev + LLM disagreements

Disagreement is not hidden.

Example UI:

```text
VATI       WAIT
JEV        SUPPORTS SETUP
LLM        agrees setup is valid but notes event risk
DECISION   WAIT

Why?
VATI event gate remains authoritative.
```

The owner sees the difference between analytical opinion and executable state.

## 15.11 Failure behaviour

- Jev unavailable -> LLM may continue from authoritative VATI state and reports JEV_UNAVAILABLE.
- LLM unavailable -> Jev labels plus VATI facts remain visible.
- Both unavailable -> authoritative VATI facts remain visible.
- data stale -> no new explanation; state becomes STALE.
- invalid chart payload -> analysis request rejected.
- no strategy fit -> explanation says no certified strategy fits.

The trading platform remains operational without Jev or LLM.

# 16. Android domain structure

Target structure:

```text
com.dial.van.trading
  accounts/
  analyst/
    LiveTradingAnalysis.kt
    LiveTradingAnalystRepository.kt
    LiveTradingAnalystPanel.kt
    AnalystFreshness.kt
  chart/
    native/
    rich/
    bridge/
    workspace/
  execution/
  history/
  intelligence/
  markets/
  positions/
  replay/
  risk/
  strategies/
  tca/
  timeline/
  ui/
```

# 17. Gateway contracts

Prefer extension of existing read routes where equivalent data already exists.

Target read surfaces include:

- /v1/trading/markets
- /v1/trading/markets/search
- /v1/trading/watchlists
- /v1/trading/instrument/{symbol}
- /v1/trading/instrument/{symbol}/bars
- /v1/trading/instrument/{symbol}/depth
- /v1/trading/instrument/{symbol}/analysis
- /v1/trading/positions/{id}
- /v1/trading/potential/{id}
- /v1/trading/risk
- /v1/trading/tca
- /v1/trading/replay/{trade_id}

Live Analyst target:
- GET /v1/trading/analysis/{context_key} — latest verified analysis artifact.
- POST /v1/trading/analysis/request — owner/device-authenticated request to schedule an explanatory cognition run; it cannot submit TradeIntent.
- GET /v1/trading/analysis/{context_key}/history — verified explanation history.

Where possible this should ride the existing Hermes/VATI cognition infrastructure rather than create a second model runtime.

# 18. Offline/degraded behaviour

Every major trading surface explicitly supports LIVE, STALE, OFFLINE, DEGRADED, EXTERNAL and UNAVAILABLE.

Cached state always shows last authoritative update and age.

Live Analyst artifacts are cacheable only until their TTL and source snapshot validity permit.

# 19. Implementation milestones

M0 Semantic closure
- freeze authority/data-source map;
- Live Analyst claim taxonomy;
- Jev/LLM contract;
- donor licensing matrix;
- no ambiguous truth ownership.

M1 Information architecture
- Home / Markets / Chart / Trades / Intelligence;
- legacy deep links preserved.

M2 Markets/watchlists/search.

M3 Instrument Terminal foundation.

M4 OpenAlgo Charts integration with hardened bridge.

M5 indicators/drawings/depth/DOM/landscape.

M6 Live Trading Analyst
- structured packet;
- Jev typed batch;
- LLM explanation;
- verifier;
- TTL/history;
- chart/candidate/position UI.

M7 advanced trade-management UX.

M8 Risk/TCA/timeline/replay.

M9 Intelligence/strategy upgrade.

M10 physical Android certification.

# 20. Acceptance rules

A feature is not complete because a screen renders.

Completion requires:

```text
UI
+ authoritative data source
+ state semantics
+ freshness
+ degraded/failure behaviour
+ security boundary
+ tests
+ device evidence
+ owner-readable explanation
```

Live Analyst adds:

```text
structured source packet
+ Jev lineage
+ LLM lineage
+ claim verification
+ TTL
+ authority_effect=NONE
```

# 21. Final target

VAN should become simultaneously:

1. a professional mobile trading terminal;
2. an expert intelligence workstation;
3. an owner-control and evidence plane.

Its differentiator is not merely putting TradingView-like charts into an app. It is the fusion of professional charting with VATI deterministic authority, Jev+LLM real-time explanation, evidence lineage, risk truth, owner approvals and post-trade accountability.
