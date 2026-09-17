> **Status (2026-09-16):** owner-supplied product/UX contract, retained as provenance. Implemented per `docs/VAN_TRADING_PRODUCTION_DEPLOYMENT_BLUEPRINT_REV5.md` Part I.

# VAN Trading Command Center
## Product, UX/UI & Implementation Blueprint — Rev 1

---

## 1. Purpose

The VAN Trading Command Center is the primary trading intelligence, portfolio awareness, account management, market analysis, execution-support, risk-management, and trading-review interface for VAN.

It must not be implemented as a conventional broker dashboard with AI added as an auxiliary feature.

The product must instead behave as a unified **trading operating environment** in which:

- accounts,
- markets,
- opportunities,
- positions,
- orders,
- strategies,
- technical analysis,
- risk,
- performance,
- historical trades,
- trading knowledge,
- and VAN interaction

share a coherent context and can be traversed without losing state.

The existing generated VAN trading dashboard benchmark establishes the desired visual direction and information density but is not intended to dictate every final implementation decision.

Fable retains authority to select the implementation strategy, component architecture, screen composition, charting solution, responsive layout method, data architecture, interaction patterns, and supporting feature set necessary to create the most complete and coherent product.

---

## 2. Product Objective

The Trading Command Center must answer six questions immediately:

1. **What is happening across my trading accounts?**
2. **What positions and risks do I currently have?**
3. **What potential trading opportunities are developing?**
4. **What markets require attention?**
5. **How has my trading been performing?**
6. **What does VAN know about the current trading situation?**

A user should be able to transition naturally from portfolio-level awareness to instrument-level analysis and then into trade, risk, strategy, journal, or conversational context.

---

## 3. Design Philosophy

The interface should combine:

- professional trading-terminal density,
- premium modern dashboard design,
- strong information hierarchy,
- high observability,
- low visual noise,
- VAN's distinctive animated identity,
- responsive multi-device behaviour,
- contextual AI interaction,
- and deterministic access to underlying trading state.

The visual system should feel like:

> **a professional trading terminal operated through an intelligent VAN command environment.**

It must not resemble:

- a generic crypto dashboard,
- a collection of independent cards,
- a broker web portal,
- a chatbot beside TradingView,
- or a decorative concept dashboard with fake information.

---

## 4. Authority Model

This blueprint defines:

### Locked product obligations

These must survive implementation changes.

### Flexible implementation zones

Fable may choose how these are achieved.

### Visual authority

The generated dashboard benchmark defines the intended broad design direction but does not impose pixel-level implementation where a stronger solution improves usability, density, responsiveness, or coherence.

Fable may:

- rearrange secondary information,
- alter card dimensions,
- replace cards with richer data surfaces,
- consolidate redundant controls,
- introduce progressive disclosure,
- add useful trading views,
- remove low-value visual elements,
- choose alternative navigation patterns,
- introduce richer desktop layouts,
- optimise mobile layouts separately,
- and implement superior interaction patterns.

Fable must preserve the underlying product semantics.

---

## 5. Primary Product Model

The system should conceptually support the following hierarchy:

```text
TRADING PORTFOLIO
│
├── Trading Accounts
│   ├── Broker account
│   ├── Prop account
│   ├── Demo account
│   └── Paper / simulation account
│
├── Markets
│   ├── FX
│   ├── Metals
│   ├── Indices
│   ├── Crypto
│   ├── Commodities
│   └── Other supported instruments
│
├── Opportunities
│
├── Orders
│
├── Positions
│
├── Strategies
│
├── Risk
│
├── Journal
│
├── Analytics
│
└── VAN Trading Intelligence
```

All major surfaces should understand the currently active:

```text
User
↓
Account scope
↓
Instrument
↓
Market/session context
↓
Strategy/setup
↓
Trade or opportunity
↓
Relevant historical knowledge
```

---

## 6. Primary Navigation

The canonical product should expose at least these functional areas:

- Overview / Command Center
- Markets
- Opportunities / Setups
- Trades
- Charts
- VAN Trade Chat
- Journal
- Analytics
- Risk
- Accounts
- Strategies
- Settings

Fable may:

- merge closely related pages,
- use tabs within larger workspaces,
- create command palettes,
- introduce split panes,
- use context drawers,
- support keyboard navigation,
- or introduce nested workspaces.

The user must always be able to understand where they are and return to the portfolio overview.

---

## 7. Main Command Center

The dashboard should act as the default trading landing screen.

It should communicate the entire trading state at a glance.

### Required information domains

#### Portfolio health

The user should be able to understand:

- total balance,
- equity,
- realised P&L,
- floating P&L,
- daily P&L,
- account growth,
- drawdown,
- risk utilisation,
- margin utilisation,
- and overall portfolio exposure.

Fable may determine which metrics deserve first-class prominence.

#### Account scope

The interface must support:

- All Accounts aggregate view,
- individual account selection,
- grouped accounts,
- optional account categories,
- and rapid switching without losing broader interface state.

The current account scope must always be obvious.

Examples:

```text
ALL ACCOUNTS

IC Markets — Personal

FTMO — Challenge 01

Pepperstone — Swing

Paper Trading — Strategy Lab
```

---

## 8. Multi-Account Architecture

Multi-account support is a core product capability rather than a later extension.

Each account may expose:

- broker/provider,
- account type,
- account currency,
- balance,
- equity,
- leverage,
- margin,
- margin level,
- floating P&L,
- realised P&L,
- daily result,
- weekly result,
- drawdown,
- account limits,
- account status,
- connection state,
- last synchronization,
- open positions,
- pending orders,
- and risk state.

The system should support a configurable reporting currency for aggregated portfolio analytics.

Original values should remain available in native account currency.

---

## 9. Account Safety Identity

Every execution-capable surface must clearly communicate whether the current context is:

```text
LIVE

DEMO

PAPER

PROP CHALLENGE

READ ONLY
```

Where applicable, the interface should make the selected execution account visually explicit.

Examples:

```text
LIVE — IC Markets Personal

PAPER — VAN Strategy Lab
```

The system should minimise accidental cross-account execution.

Fable is free to determine the best mechanism.

---

## 10. Central Market Workspace

The main dashboard should include a visually prominent market analysis surface.

The benchmark uses a live candlestick chart.

The final implementation may use:

- embedded professional charting,
- a proprietary chart renderer,
- broker charts,
- TradingView-compatible technology where licensing permits,
- or another production-grade chart engine.

The chart should support an appropriate subset of:

- candlesticks,
- line/area modes,
- multi-timeframe navigation,
- drawings,
- overlays,
- indicators,
- volume,
- trade entry/exit markers,
- risk/reward visualisation,
- historical trade overlays,
- VAN annotations,
- setup zones,
- and order/position levels.

Fable should select the feature set according to actual product value.

---

## 11. VAN Market State

The primary dashboard should contain an intelligent market-state surface associated with VAN.

Its purpose is to make VAN visually and functionally present in the trading experience.

Possible information:

- current market session,
- detected market regime,
- volatility state,
- major instruments requiring attention,
- risk state,
- active opportunities,
- account alerts,
- and high-level market observations.

The visual VAN representation should use the animated VAN visual system rather than a static avatar wherever technically practical.

---

## 12. VAN Aura Semantics

The animated VAN aura may communicate system state.

Potential states include:

### Passive monitoring
Subtle flowing field.

### Market activity
More active wave behaviour.

### Setup detected
Measured pulse or increased field activity.

### Setup approaching
Higher energy but controlled animation.

### Active position
Persistent animated field with execution-aware state.

### Risk alert
Distinctive but non-alarming urgency state.

### Offline / degraded
Reduced or muted energy.

The exact colour and animation logic should remain controlled by the canonical VAN visual production system.

Trading colours must not be confused with VAN emotional/state colours.

---

## 13. Open Positions

The main dashboard should expose current open positions.

A useful representation may include:

- symbol,
- direction,
- account,
- size,
- entry,
- current price,
- stop,
- target,
- floating P&L,
- R multiple,
- holding time,
- strategy,
- and trade status.

Fable may determine whether the default surface is:

- a table,
- compact cards,
- a position strip,
- or hybrid layout.

A position must open into a detailed trade workspace.

---

## 14. Opportunity / Potential Trade System

Potential trades must be modelled as structured trading objects rather than simple signals.

Suggested lifecycle:

```text
DISCOVERED
↓
WATCHING
↓
SETUP FORMING
↓
ENTRY APPROACHING
↓
READY
↓
ORDER PLACED
↓
ACTIVE
↓
MANAGING
↓
CLOSED
```

Possible side states:

```text
INVALIDATED

EXPIRED

REJECTED

CANCELLED

MISSED
```

Fable may refine this lifecycle where required by the eventual trading engine.

---

## 15. Opportunity Object

A potential trade may contain:

- instrument,
- direction,
- setup name,
- strategy,
- account eligibility,
- timeframe,
- entry zone,
- invalidation,
- stop,
- targets,
- projected risk/reward,
- setup score,
- market regime,
- session,
- detected conditions,
- required confirmations,
- blockers,
- expiry,
- supporting chart annotations,
- and VAN analysis.

Where an opportunity score is displayed, the interface must clearly represent what that score means.

A model-generated score must not automatically be labelled as probability of winning.

---

## 16. Opportunities Workspace

A dedicated opportunities surface should allow:

- filtering,
- sorting,
- account relevance,
- market filtering,
- strategy filtering,
- setup-state filtering,
- session filtering,
- score filtering,
- expiration,
- and watchlist management.

Potential display modes include:

- dense table,
- card board,
- timeline,
- kanban by setup stage,
- watchlist,
- chart-first layout,
- or combined layout.

Fable should select the strongest solution.

---

## 17. Instrument Workspace

Selecting an instrument should open an instrument-centric trading workspace.

The workspace should ideally combine:

### Chart

Primary chart and drawings.

### Current market context

Session, volatility, spread, regime, relevant events.

### Opportunity context

Detected setup(s), active strategy, potential trade structure.

### Position context

Existing positions and pending orders.

### Indicators

Relevant technical measurements.

### Historical context

Recent and similar trades.

### VAN

Context-aware trading conversation and analysis.

The workspace may use:

- panels,
- drawers,
- split panes,
- dockable modules,
- or configurable layouts.

---

## 18. Indicator Intelligence

The interface should avoid treating indicators merely as decorative technical widgets.

Indicators should be organised conceptually.

Possible categories:

### Structure
- swing structure,
- BOS,
- CHoCH,
- support/resistance,
- liquidity levels.

### Trend
- moving averages,
- VWAP,
- ADX,
- trend state.

### Momentum
- RSI,
- MACD,
- rate-of-change measures.

### Volatility
- ATR,
- realised volatility,
- Bollinger width,
- session range.

### Volume
- relative volume,
- volume profile,
- volume imbalance.

### Liquidity
- previous highs/lows,
- session highs/lows,
- liquidity pools,
- sweep detection.

### Market context
- session,
- spreads,
- economic calendar,
- correlation,
- volatility events.

Fable may implement only indicators relevant to the eventual trading methodology.

---

## 19. VAN Trade Chat

Trading chat must be a first-class trading surface.

VAN should receive deterministic context from the application rather than relying solely on conversational history.

Context may include:

```text
ACCOUNT

INSTRUMENT

TIMEFRAME

CHART STATE

ACTIVE STRATEGY

POTENTIAL TRADE

ACTIVE POSITION

RISK STATE

INDICATORS

MARKET SESSION

HISTORICAL SIMILAR TRADES
```

---

## 20. Contextual Conversation

The system should support questions such as:

- Why is this setup not ready?
- What invalidates this setup?
- What changed since the last candle?
- Show similar trades.
- Compare this setup to previous winners and losers.
- What risk would this trade add?
- How correlated is this with my other positions?
- Explain the current structure.
- Show the relevant strategy rule.
- What is my historical performance on this instrument?
- Why did this trade fail?
- What would happen to total risk if I opened this trade?

VAN should clearly separate:

- market facts,
- computed metrics,
- strategy rules,
- historical evidence,
- model interpretation,
- and speculative reasoning.

---

## 21. Interactive AI Responses

Where technically appropriate, VAN responses may produce structured interactive objects.

Examples:

- open chart,
- compare historical trades,
- show risk impact,
- highlight levels,
- open journal entry,
- inspect strategy,
- view opportunity,
- add to watchlist,
- open account,
- filter analytics,
- or navigate to relevant metrics.

The chat should function as an alternative navigation and command surface.

---

## 22. Trade Workspace

Every active or completed trade should have a dedicated workspace.

It may show:

- account,
- symbol,
- direction,
- size,
- entry,
- stop,
- targets,
- current market price,
- realised P&L,
- unrealised P&L,
- R multiple,
- timestamps,
- execution events,
- strategy,
- setup,
- position changes,
- trade notes,
- screenshots,
- and VAN interpretation.

---

## 23. Trade Timeline

Each trade should support a deterministic timeline.

Example:

```text
08:32 — Setup discovered

08:41 — Confirmation detected

08:52 — Entry zone reached

08:53 — Order executed

09:04 — +1R reached

09:17 — Partial exit

09:38 — Stop adjusted

10:03 — Trade closed
```

The exact event model may be selected by Fable.

---

## 24. Trade Journal

The journal should turn each trade into a learning object.

Potential data:

- pre-trade reasoning,
- entry screenshot,
- exit screenshot,
- annotations,
- VAN analysis,
- strategy version,
- indicator state,
- market regime,
- account state,
- risk state,
- execution quality,
- modifications,
- manual notes,
- post-trade review,
- tags,
- and outcome.

The journal should integrate directly with analytics and VAN historical retrieval.

---

## 25. Historical Trades

Historical trades should support:

- search,
- filtering,
- sorting,
- instrument grouping,
- strategy grouping,
- account grouping,
- session grouping,
- outcome grouping,
- date range,
- risk bucket,
- setup score,
- regime,
- and journal completeness.

Historical trades should open directly into trade detail or chart replay where supported.

---

## 26. Analytics

The analytics surface should go substantially beyond broker-level statistics.

At minimum, the product should be capable of analysing performance across:

- account,
- instrument,
- strategy,
- setup,
- direction,
- session,
- day,
- hour,
- week,
- month,
- market regime,
- timeframe,
- risk size,
- holding duration,
- execution quality,
- setup score,
- and trade-management behaviour.

---

## 27. Analytics Metrics

Possible metrics include:

- win rate,
- loss rate,
- break-even rate,
- average win,
- average loss,
- expectancy,
- profit factor,
- average R,
- median R,
- maximum drawdown,
- recovery factor,
- consecutive wins,
- consecutive losses,
- average hold duration,
- MAE,
- MFE,
- realised vs potential R,
- slippage,
- spread,
- and execution latency.

Fable may select additional professional trading metrics where useful.

---

## 28. Behavioural Analytics

The product should eventually help identify behaviour such as:

- exiting winners early,
- moving stops,
- increasing risk after losses,
- overtrading particular sessions,
- taking trades outside strategy,
- skipping high-quality setups,
- excessive correlation,
- or poor execution conditions.

These observations must be based on data rather than unsupported AI speculation.

---

## 29. Risk Center

Risk should be a full workspace rather than a small dashboard widget.

Possible views:

### Portfolio risk

- total risk,
- current exposure,
- leverage,
- margin,
- drawdown,
- correlation.

### Account risk

- account-level drawdown,
- daily risk limits,
- max loss limits,
- account rules,
- challenge constraints.

### Position risk

- risk by open trade,
- stop-based monetary exposure,
- R exposure,
- correlated positions.

### Concentration

- by asset,
- currency,
- direction,
- sector,
- strategy,
- instrument.

---

## 30. Risk Visualisations

Potential visual components:

- risk utilisation gauges,
- exposure bars,
- concentration maps,
- correlation matrix,
- drawdown chart,
- margin state,
- scenario analysis,
- account rule indicators,
- and risk-limit timeline.

Fable should choose representations that maximise comprehension rather than decorative complexity.

---

## 31. Accounts Workspace

The Accounts page should support:

- connected trading accounts,
- broker identity,
- account type,
- live/demo status,
- connection health,
- balances,
- risk limits,
- permissions,
- synchronization state,
- and account-level analytics.

Where broker APIs allow it, account onboarding should be deterministic and secure.

Credentials must never be exposed in UI state or logs.

---

## 32. Strategies Workspace

Strategies should be represented as structured system objects.

A strategy may include:

- identity,
- description,
- market applicability,
- timeframe,
- entry conditions,
- exclusion conditions,
- invalidation rules,
- risk rules,
- exit rules,
- trade management,
- supported indicators,
- version,
- backtest results,
- live performance,
- and journal history.

VAN should be able to cite the relevant strategy rule when discussing a setup.

---

## 33. Market Discovery

A dedicated Markets surface may support:

- favourites,
- watchlists,
- movers,
- volatility,
- session activity,
- opportunities,
- spreads,
- economic-event exposure,
- technical state,
- or market regime.

Fable may determine whether this is a standalone screen or part of Opportunities.

---

## 34. Watchlists

Users should be able to maintain:

- global watchlists,
- strategy-specific lists,
- account-specific lists,
- session lists,
- temporary lists,
- and VAN-generated candidate lists.

Watchlists should connect directly into the instrument workspace.

---

## 35. Notifications

Relevant trading events may produce notifications.

Examples:

- setup detected,
- setup invalidated,
- entry approaching,
- order filled,
- stop triggered,
- target hit,
- drawdown threshold,
- margin warning,
- broker disconnect,
- economic event approaching,
- risk limit approached,
- position changed,
- strategy condition changed.

Notification urgency should correspond to actual importance.

---

## 36. Dashboard Quick Actions

The benchmark includes quick navigation to:

- Trade Chat,
- Indicators,
- Metrics,
- Strategy,
- Journal,
- Risk Center.

Fable may retain, redesign, or replace this region.

The requirement is rapid movement from overview to analysis.

---

## 37. Search and Command

A global search/command surface is strongly encouraged.

It should eventually support searching:

- instruments,
- trades,
- accounts,
- strategies,
- setups,
- journal notes,
- analytics,
- and VAN knowledge.

A command palette may provide:

```text
Open XAUUSD

Show active trades

Switch to FTMO

Open Risk Center

Show yesterday's trades

Ask VAN about NAS100

Show London session performance
```

---

## 38. Responsive Strategy

The Trading Command Center must be designed for:

- desktop,
- large tablet,
- compact tablet,
- and mobile.

Desktop may prioritise multi-panel observability.

Mobile should not attempt to shrink the desktop dashboard unchanged.

Instead it should expose:

- portfolio state,
- active positions,
- opportunities,
- selected chart,
- alerts,
- VAN,
- and essential risk data

through mobile-native navigation.

Fable has authority to design distinct responsive compositions.

---

## 39. Desktop Priority

Desktop should favour:

- multi-pane interaction,
- high information density,
- expandable charting,
- simultaneous account/risk visibility,
- and rapid contextual transitions.

---

## 40. Mobile Priority

Mobile should favour:

- glanceable metrics,
- current positions,
- trade status,
- opportunities,
- VAN interaction,
- notifications,
- and fast action.

Dense analytics and multi-chart analysis may open into dedicated mobile screens.

---

## 41. Visual Design System

The benchmark establishes the following high-level visual direction:

### Base

- dark graphite / near-black background,
- restrained depth,
- professional financial visual language.

### Surfaces

- subtle translucent panels,
- controlled glass effects,
- low-noise borders,
- minimal shadow.

### Accent

- VAN electric blue,
- violet,
- restrained cyan,
- occasional semantic gradients.

### Semantic trading colours

- positive,
- negative,
- warning,
- risk,
- neutral.

Colour must not be the sole communication mechanism.

---

## 42. Typography

Typography should prioritise data readability.

Hierarchy should clearly differentiate:

- primary monetary values,
- trade metrics,
- labels,
- instrument names,
- statuses,
- explanatory text,
- and VAN responses.

Numeric typography should support rapid scanning.

Tabular numerals are preferred where practical.

---

## 43. Motion

Motion should communicate:

- state change,
- data transition,
- focus,
- opportunity progression,
- and VAN presence.

Motion must never interfere with chart interpretation.

Heavy decorative animation should be avoided outside VAN's aura and designated ambient regions.

---

## 44. Density

The interface should feel dense but not congested.

Use:

- strong alignment,
- consistent spacing,
- visual grouping,
- progressive disclosure,
- collapsed secondary detail,
- hover/press inspection,
- context drawers,
- and expandable panels.

Not every metric should be visible simultaneously.

---

## 45. Empty States

All major modules require intentional empty states.

Examples:

- no open trades,
- no opportunities,
- disconnected account,
- market closed,
- no historical data,
- no strategy selected,
- no journal entries.

Empty states should provide useful next actions rather than decorative filler.

---

## 46. Degraded States

The system should visibly differentiate:

```text
LIVE

DELAYED

STALE

OFFLINE

SIMULATED

UNKNOWN
```

Market and account information must not appear current when the underlying feed is stale.

---

## 47. Deterministic Trading State

VAN must never infer authoritative trading state from chat history.

Authoritative state must come from deterministic services such as:

- broker adapters,
- account sync,
- market feeds,
- trading engine,
- position ledger,
- risk engine,
- strategy engine,
- event store.

VAN may interpret these objects but not replace them.

---

## 48. Suggested Logical Architecture

The final implementation architecture remains Fable's decision.

Conceptually, the system may contain:

```text
                     VAN
                      │
            Trading Intelligence Layer
                      │
     ┌────────────────┼──────────────────┐
     │                │                  │
 Market Data      Trading Engine     Account Engine
     │                │                  │
 Indicator        Opportunity        Broker Adapters
 Services          Engine                │
     │                │              Account Sync
     └────────┬───────┴───────────────┬──┘
              │                       │
          Risk Engine             Event Store
              │                       │
              └──────────┬────────────┘
                         │
                  Trading Knowledge
                         │
                 Analytics / Journal
                         │
                         VAN
```

This is a logical model rather than a mandated service decomposition.

---

## 49. Event Model

Trading activity should ideally produce structured events.

Possible examples:

```text
ACCOUNT_CONNECTED

ACCOUNT_DISCONNECTED

SETUP_DISCOVERED

SETUP_UPDATED

SETUP_READY

SETUP_INVALIDATED

ORDER_CREATED

ORDER_FILLED

POSITION_OPENED

POSITION_UPDATED

POSITION_CLOSED

STOP_CHANGED

TARGET_CHANGED

RISK_THRESHOLD_REACHED

TRADE_REVIEW_CREATED
```

Fable may redesign the event taxonomy.

---

## 50. Data Lineage

Important trading records should retain enough lineage to reconstruct:

- what the system knew,
- which strategy version was active,
- which market data was available,
- what risk state existed,
- what VAN was shown,
- and what actions occurred.

This becomes critical for:

- journaling,
- analytics,
- debugging,
- strategy development,
- and trustworthy VAN explanations.

---

## 51. Supporting Screens

At minimum, the final product should consider dedicated or embedded surfaces for:

1. Trading Command Center
2. Markets
3. Opportunities
4. Instrument workspace
5. Chart workspace
6. Active trades
7. Trade detail
8. Historical trades
9. VAN Trade Chat
10. Indicators
11. Analytics
12. Risk Center
13. Accounts
14. Account detail
15. Strategies
16. Strategy detail
17. Journal
18. Watchlists
19. Notifications
20. Settings

Fable may consolidate screens where it produces a better information architecture.

---

## 52. Fable Feature Selection Authority

Fable should not treat the above feature list as an instruction to build every possible feature indiscriminately.

Fable should prioritise features based on:

### Product value

Does the feature improve actual trading awareness or workflow?

### Context preservation

Does the feature improve movement between related trading objects?

### Risk relevance

Does it materially improve risk understanding?

### Data availability

Can the feature be supported by real deterministic information?

### UX clarity

Can it be presented without damaging information hierarchy?

### Implementation maturity

Can it be implemented reliably?

### VAN integration

Does VAN gain useful contextual intelligence from the feature?

---

## 53. Implementation Freedom

Fable may select:

- frontend framework,
- charting stack,
- state architecture,
- streaming mechanism,
- local caching,
- backend API structure,
- component system,
- responsive framework,
- design tokens,
- table implementation,
- virtualisation,
- animation stack,
- WebSocket or event strategy,
- analytics engine,
- chart overlays,
- broker abstraction,
- and AI context transport.

No architectural technology decision is locked by this blueprint unless separately specified in VAN Project Truth.

---

## 54. Feature Maturity Tiers

Fable may organise implementation into capability tiers.

Example:

### Core

- accounts,
- overview,
- positions,
- opportunities,
- chart,
- account switching,
- core risk,
- VAN context.

### Professional

- advanced charting,
- journal,
- analytics,
- strategies,
- richer risk,
- multi-account aggregate views.

### Intelligence

- similar-trade retrieval,
- behavioural analysis,
- market-state reasoning,
- opportunity progression,
- strategy comparison,
- knowledge-assisted VAN.

### Advanced

- scenario analysis,
- portfolio correlation,
- replay,
- automation,
- advanced execution tools,
- cross-account strategy orchestration.

These tiers are conceptual only.

---

## 55. Benchmark Interpretation

The generated benchmark should be treated as a visual and compositional reference.

It demonstrates:

- dark premium styling,
- portfolio metrics,
- central chart dominance,
- visible VAN market-state surface,
- right-side accounts,
- exposure analysis,
- open positions,
- potential trades,
- recent trades,
- and quick-access destinations.

Fable is encouraged to improve it where necessary.

The final design should preserve its strengths:

- clarity,
- strong hierarchy,
- professional visual tone,
- compact density,
- cohesive dashboard composition,
- obvious VAN identity,
- and actionable navigation.

---

## 56. What Must Not Be Lost

Regardless of implementation strategy, the final trading experience must preserve:

- multiple account support,
- aggregate portfolio visibility,
- live account-state clarity,
- open position visibility,
- potential-trade visibility,
- risk awareness,
- central market analysis,
- VAN integration,
- historical context,
- supporting analysis screens,
- and context-preserving navigation.

---

## 57. What Must Not Be Faked

Production UI must not use fabricated values presented as live trading information.

Prototype data is acceptable during development only when clearly isolated from production behaviour.

The final system must differentiate:

- production data,
- simulated data,
- demo data,
- and unavailable data.

---

## 58. User-Control Principle

VAN should assist trading decision-making without obscuring the underlying information.

Important claims should be inspectable.

Where VAN suggests an interpretation, the user should be able to inspect:

- indicators,
- strategy conditions,
- historical examples,
- market data,
- and risk consequences.

The interface should support informed user control rather than opaque automation.

---

## 59. Performance Expectations

Trading surfaces should feel near-real-time.

Fable should design for:

- streaming updates,
- efficient chart rendering,
- virtualised dense lists,
- stable layout,
- low input latency,
- and predictable transitions.

Large account histories should not degrade the primary dashboard.

---

## 60. Security

Trading integrations must assume account credentials and broker access are security-critical.

Implementation should enforce:

- encrypted credential storage,
- least privilege,
- clear execution permissions,
- safe token handling,
- audit logging,
- account isolation,
- explicit live vs paper state,
- and secure session management.

---

## 61. Accessibility

Professional density must not come at the cost of usability.

The interface should support:

- sufficient contrast,
- semantic icons,
- keyboard navigation where applicable,
- readable text scaling,
- non-colour status signalling,
- and accessible interaction targets.

---

## 62. Suggested First-Class Design Screens

For visual-authority development, the strongest initial screens are:

### Screen A — Trading Command Center

Establishes:
- global navigation,
- portfolio metrics,
- main chart,
- VAN identity,
- account switching,
- opportunities,
- positions,
- exposure,
- recent trades.

### Screen B — Instrument Workspace

Establishes:
- chart-first layout,
- technical analysis,
- trading context,
- setup details,
- VAN contextual interaction.

### Screen C — VAN Trade Chat

Establishes:
- AI interaction,
- context chips,
- structured responses,
- trading-object navigation.

### Screen D — Risk Center

Establishes:
- data-heavy visual system,
- account/portfolio risk,
- exposure and correlations.

### Screen E — Analytics

Establishes:
- advanced metrics,
- time-series layouts,
- strategy performance,
- filtering architecture.

These five screens provide enough visual authority to derive most supporting surfaces.

---

## 63. Definition of a Successful Product

The final dashboard is successful when the user can open VAN Trading and, without navigating elsewhere, immediately understand:

- portfolio value,
- account health,
- current positions,
- risk,
- opportunities,
- important market state,
- recent results,
- and where VAN requires attention.

From there, no major trading object should require more than a short contextual navigation path to inspect.

---

## 64. Fable Completion Requirement

Fable should treat this blueprint as a **product and UX contract**, not a rigid implementation recipe.

Before implementation, Fable should derive:

```text
1. Final screen architecture

2. Chosen component hierarchy

3. Data and state boundaries

4. Charting strategy

5. Multi-account model

6. Trading-object model

7. VAN context model

8. Responsive strategy

9. Feature prioritisation

10. Visual system

11. Interaction model

12. Risk and execution safeguards
```

Fable should be free to improve the design where those improvements preserve the product obligations defined in this blueprint.

The goal is not to reproduce a mockup literally.

The goal is to produce the most coherent, comprehensive, responsive, professional and VAN-native trading command environment that satisfies the intent of this specification.

---

## 65. Canonical Design Principle

The central product principle is:

> **VAN Trading is one contextual trading system, not a collection of disconnected dashboards.**

Account state, market state, opportunities, positions, strategy, risk, historical evidence, analytics and VAN intelligence must operate on shared trading objects and shared user context.

That principle should guide every implementation decision.
