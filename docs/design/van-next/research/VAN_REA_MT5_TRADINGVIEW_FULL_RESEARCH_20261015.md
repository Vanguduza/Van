# VAN — Reverse Engineering Research: MetaTrader 5 and TradingView Android

**Document:** `VAN-REA-RESEARCH-20261015-R1`  
**Purpose:** Technical research, evidence, comparison, and architecture recommendations for the VAN Android Tactile Spatial redesign.  
**Prepared:** 15 October 2026  
**Target consumer:** Opus 5.5, the DIAL development system, VAN architects, and independent forensic reviewers.  
**Status:** `STATIC_RESEARCH_RECORDED; DYNAMIC_QUALIFICATION_OPEN; PRODUCT_ADOPTION_PROPOSED`  
**Governing owner intent:** The two accepted dark/light VAN designs and the requirements discussed in the originating ChatGPT conversation. This document does **not** authorize legacy UI inheritance, trading-policy modifications, strategy promotion, or live trading.  
**Source-of-truth rule:** Third-party APKs are observational architecture donors only, not design authority, code import authority, broker adapters, or trading authority.

---

## 1. Executive determination

**Research conclusion:** VAN should provide a genuine mobile trading workstation whose professional chart, portfolio, risk, news, and intelligence interfaces are composable and responsive, while remaining visually faithful to VAN's locked Tactile Spatial design system. The best architectural synthesis takes **Android chart/surface lifecycle and order-domain exactness** from what MT5 exposes, and **typed chart capability separation, native/web event bridging, and state-based multi-domain data projection** from what TradingView exposes. It preserves VAN/VATI's own superior opportunity to connect verified chart observations, owner annotations, qualified event research, and position context to the backend intelligence fabric without allowing a UI, JavaScript engine, user drawing, JEV, Hermes, or LLM to execute a trade by itself.

This is an **inference from the verified client-side source evidence**, not a claim to have discovered proprietary server architecture. Neither APK was executed on an Android device during this research. No broker transaction was initiated.

**Recommended product architecture:**

1. A small **native chart preview renderer** for Trading Home, watchlists, search results, opportunity cards, and portfolio context. No heavy chart runtime is started for a thumbnail.
2. A separate **professional chart workstation** with an interchangeable renderer, typed chart-capability interface, high-performance viewport data path, and contextual native Compose controls. Candidate implementations (including the earlier OpenAlgo Charts proposal) remain conditional on performance, security, source/licensing and qualification.
3. A **single canonical market/portfolio projection layer**, which reconciles source timestamps, broker accounts, updates, risk state, corrections, subscriptions, disconnects, and user preferences. Display state is not a substitute for broker state.
4. A **read-only intelligence observation bridge**: bounded chart snapshots, verified indicators, user drawings and explanatory notes, market-event context, and replay annotations can be consumed by authorised research/JEV/LLM components. Only explicitly qualified VATI policy can convert admitted facts into changes in executable eligibility.
5. A **separate, fail-closed owner-intent lane** for pending orders, chart-based SL/TP modification, trailing protection, partial exits and supported manual actions: draft preview → deterministic revalidation → exact owner/device approval as required → VATI risk/authority → router/broker → independent fill/protection receipt → reconciliation.
6. A fully integrated **News Intelligence** experience with provenance, source correction, instrument joins, market-response observations, contradictory evidence, hypothesis/invalidation views, and actionable but non-authoritative analysis.

Do not adopt TradingView's or MT5's surface style, density, fonts, icons, layouts, code/assets or paywall logic. VAN's user-approved calm, sculpted metal/ceramic materials, dimensional orb, controlled highlights and progressive disclosure govern appearance.

---

## 2. Provenance and classification of evidence

### 2.1 Five evidence classes

- `REA_CONFIRMED`: Output of a successful REA 6.5.0 command under JADX Headless MCP 0.7.1, with an evidence ID and immutable input/shard digest.
- `APK_RAW_CONFIRMED`: Deterministic read-only inspection of supplied APK bytes: DEX headers, class definitions, declared fields/methods, manifest, ZIP payloads, asset metadata and signatures.
- `SOURCE_CODE_REFERENCE`: The user's previously supplied VAN blueprint and archived registry, plus current repository source observations from the audit. These are historical or current **source evidence**, not proof of deployed functionality.
- `ENGINEERING_INFERENCE`: A proposed architectural conclusion, plausible from evidence but not tested as a runtime property.
- `UNVERIFIED`: A dynamic behaviour, resource/performance property, upstream network protocol, renderer internals, broker implementation, datafeed SLA, proprietary computation or user-experience quality not proven by this study.

Do not promote `ENGINEERING_INFERENCE` or `UNVERIFIED` to `REA_CONFIRMED` in an Opus implementation prompt or a DIAL qualification receipt.

### 2.2 MetaTrader 5 source

| Parameter | Observed value |
|---|---|
| Source | MetaQuotes Android distribution file obtained on `van-trading-core` |
| APK | `/opt/van-rea-lab/references/metatrader5-official.apk` |
| SHA-256 | `6f220fc7ccc750ed0d670b32a0758a1800fe232c4c9b7637673d4f9c7ea7bdd6` |
| Size | 38,735,458 bytes |
| Package | `net.metaquotes.metatrader5` |
| Version | `500.6260` |
| minSdk / targetSdk | 23 / 36 |
| REA class count | 9,030 |
| REA resource count | 4,345 |
| Native ABIs identified | `arm64-v8a`, `armeabi-v7a` |
| Relevant native modules | `libcommon.so`, `libchannels.so` (presence, not internal behaviour) |
| Signing verification | Android `apksigner verify --print-certs` returned success |
| Signer certificate SHA-256 | `df67d8967ba0374ba9c4deff3e28bcb536a39562f6a6d87077c394c0c8f43696` |

**Base REA record:** `ev_0c95aff915a8601313a1966481cfae4ef207f648e47f5a1caa8d374030860f4c`.  
**Complete REA class inventory:** `ev_b0133c382a2681b47d3b40a2621a68d88f927c9d0a4271464e2e37387485097a`.

### 2.3 TradingView—authoritative uploaded APK

| Parameter | Observed value |
|---|---|
| Uploaded filename | `TradingViewcom.tradingview.tradingviewappv1.20.84.0.1002505.apk` |
| Original SHA-256 | `dfbc561d32fdd4405956d8bd0b3f30d7490f60a790ebfc143c48206c8f7671b1` |
| Original size | 105,686,346 bytes |
| Package | `com.tradingview.tradingviewapp` |
| Version | `1.20.84.0.1002505` (version code `1002505`) |
| minSdk / targetSdk | 26 / 36 |
| Raw DEX class definitions | 70,877 |
| Declared method implementations | 290,921 |
| Declared field implementations | 184,973 |
| DEX files | Seven (`classes.dex` through `classes7.dex`) |
| Archive members | 4,366 |
| Embedded chart bridge configuration | 167 method contracts, 49 subscription contracts |
| Required split | Manifest declares `base__abi` |
| Native libraries in supplied base APK | None; an ABI split may be needed for actual installation |
| Signing-block certificate fingerprint parsed | `44f047fc6b34b0ba0c491f825bb4e43770d2bc941220d290a70f3a8467aed601` |

The signature fingerprint is *parsed evidence*, not independent proof that the uploaded APK was delivered through the official Play channel. Dynamic installation must verify package/signing lineage and the required ABI splits. `AndroidManifest.xml` in this original attachment is authoritative for its build's declaration.

### 2.4 Why TradingView REA used a second archive

The attached 105.7-MB APK could not be transferred directly from ChatGPT's working container into `van-trading-core` through the available typed estate control. A second APK for **the same version** was obtained on the VM and admitted for analysis as an explicitly labelled **secondary distribution**, at:

`/opt/van-rea-lab/references/tradingview_v1.20.84.0.1002505_secondary.apk`

Its complete ZIP SHA-256 is `c762b6dfd910b552050e775eba739a0ed5a2838e6f3f433c238a5a8c6c4cf584`; it is **not** the original uploaded archive.

Byte-level comparison supports code/content equivalence for the analysed parts: all **seven DEX payloads**, all **53 asset files**, all **4,009 `res/` files**, and `resources.arsc` match by SHA-256 between the original uploaded APK and the VM secondary APK. The binary `AndroidManifest.xml` differs. Do not equate the APK-wide hashes or the original/secondary manifest and signer claims. This is enough to ground the *compiled Java/Kotlin and packaged JavaScript class/asset observations*, not an identical signed installed application.

**Secondary full package REA inspection:** `ev_dad9570ce40c2d71412285328fba05640b024614a9bd30ff1371469329c3e882`.

### 2.5 REA's full-APK timeout and reproducible partitioning

A single full-APK TradingView class-inventory request hit the JADX bridge's **120-second analysis timeout**. To avoid treating timeout as an incomplete app, the seven DEX payloads were isolated into seven **temporary, unsigned, static-analysis APK derivatives**, each containing an unchanged DEX payload plus manifest/resources needed by JADX. The original DEX bytes are hash-recorded; the partitions are **not** publisher-signed, deployable or testable Android releases. This approach prevents the full package's class-loading cost from invalidating the research.

Each `search-android-classes` run on the partition completed; evidence IDs:

| DEX partition | REA-reported names | Evidence ID |
|---|---:|---|
| 1 | 4,326 | `ev_bfdcd5faa86d09eb10595d7f64295eab798909f6179d6f0622cc58051284493b` |
| 2 | 5,421 | `ev_669b962ca776c57cb7eb483497c3733ebed082e2cd6d41f79898a01480a6f06b` |
| 3 | 4,299 | `ev_be030a8dacf5c52fac048684946a0d4604303bd9baddc1fdf6e3be6c26a1077c` |
| 4 | 8,457 | `ev_45f7294149faff8b1b4c2680ea1ce154537ea90e65b4ead204282294113e39d3` |
| 5 | 6,162 | `ev_954f10a05035638c3139bb5add2eb03c32b8acb51940e06f8d7e7b9a5a51062d` |
| 6 | 5,683 | `ev_5d2ded73a87b5fe6ab8287de09a3f6c5121c7fce67a92fbd712e68739c787d53` |
| 7 | 5,705 | `ev_12102a02f4635a7cd8f989891341a3c68a78eb25c7c62c67d89f5466215f7ac0` |

The sum of the seven REA class-name inventories is 40,053, **40,046 distinct names** after duplicate-name reconciliation. That is not equal to the original DEX `class_defs_size` sum (70,877): REA/JADX and the raw-Dex index have different class representation/filtering semantics and partitioned class-resolution constraints. Use the original raw DEX counts for byte-exhaustive coverage and the REA names for JADX-specific cross-referencing. **Inter-DEX references are not complete when inspected in isolation.**

**Reusable VM catalog:** `/opt/van-rea-lab/evidence/OPUS55_REA_VM_EVIDENCE_INDEX_20261015.json`  
**Catalog SHA-256:** `829af2ed8c9784da2a6affd5d093bd22e6e7dd1066c6a05af64cbea61e333744`  
**35-plus successful REA records:** The catalog lists 39 completed evidence records, their providers, subject hashes, operations and source file hashes. The exact count and paths in the catalog supersede any earlier progress summary.

---

## 3. REA findings — MetaTrader 5

### 3.1 Chart rendering and lifecycle

REA identified `net.metaquotes.metatrader5.ui.charts.ChartSurface` (23 declared members), `net.metaquotes.metatrader5.terminal.ChartRenderer` (11), `ChartToolbar`, chart fragments, chart settings and tick-chart views. `ChartSurface` declares `onSurfaceTextureAvailable`, `onSurfaceTextureDestroyed`, size/visibility updates, chart-ID setters, and terminal load/unload hooks. It references a native `EGLSurface`, a `SurfaceTexture`, a handler and a thread in its member fields. The renderer declares chart-not-ready, requesting, processing, ready and symbol-changed constants, cursor modes and various bitmap/font support methods.

**Method decompilation succeeded:** `ChartSurface.onSurfaceTextureAvailable` (`ev_3e78c2ee64613610e2751b7237461096c06106c2ee18fa00d52c43a79dfed976`) and `ChartSurface.onSurfaceTextureDestroyed` (`ev_ca84a8db2f90c80891cb34275ac3790208d76093ce6f9f8d6dc13646b47491c0`). `ChartSurface` has five incoming references in the class-level REA trace (`ev_32d367c5404ec262c621e94810cac00b3a3a85488912c18c7c92f894e0786c9a`).

**Confirmed:** Explicit Android surface lifecycle and chart-state separation exist in this APK.  
**Not confirmed:** GPU throughput, actual end-to-end frame scheduling, exchange feed latency, thread lifetime and correctness of every renderer path.

**VAN lesson:** Chart frame production, rendering state and Android lifecycle must be distinct from Compose page recomposition. Suspend rendering when invisible, handle texture loss, preserve viewport state, and recover after process/background transitions. Compose can own controls and data presentation while a dedicated chart renderer owns frames. Keep an accessible no-animation/flat fallback.

### 3.2 Trading order lifecycle

`net.metaquotes.metatrader5.types.TradeOrder` contains explicit constants for `BUY`, `SELL`, `BUY_LIMIT`, `SELL_LIMIT`, `BUY_STOP`, `SELL_STOP`, `BUY_STOP_LIMIT`, `SELL_STOP_LIMIT`, close-by, `FOK`, `IOC`, `RETURN`, BOC and GTC/day/specified expiries. Order states include started, requesting add/modify/cancel, placed, partial, filled, cancelled, expired and rejected. The REA class-reference trace contains 40 references (`ev_5a00b2f4dd6ce49fa902c1e76a980a53783c03f150cd8a08a27f5a3a86630ad2`). `OrderSendFragment` includes a method receiving `TradeResult`; REA decompilation for one result-handling method succeeded (`ev_cc5aeb1726fabfe2df5483b302fd53e1d447c97b08f8c56031e5420c8643a5b7`).

**Confirmed:** Rich order-status and instruction vocabulary in the Android client.  
**Not confirmed:** All order types are available at every supported broker or that any server transition follows the client enum exactly.

**VAN lesson:** The UI must never collapse `REQUESTED`, `ACCEPTED`, `WORKING`, `PARTIAL`, `FILLED`, `REJECTED`, `CANCELLED`, `EXPIRED` and `OUTCOME_UNKNOWN` into a single spinner/success. Use exact broker capabilities and canonical order/position IDs. On uncertain mutation results, reconcile against authoritative broker/ledger facts before allowing repeated action.

### 3.3 Positions and protective orders

`TradePosition` exposes entry/current price context, symbol, volume, currency precision, profit, `sl`, `tp`, fees/swap, and `canModify`/`canTrade` presentation flags. The class has 46 incoming-reference records (`ev_a7b3957b54d0223cab74e560733867ef2b0d73ff21ba365f0f60b3c39588cdf2`). Other relevant views include `TradePositionView`, `PositionViewInfo` and history positions.

**VAN lesson:** Present current positions with protection information and precision semantics intact. Graphical handles on entry/SL/TP must create **draft owner proposals**, not mutate live broker state. Preserve account routing, tick-size/point units, position netting/hedging, broker-enforced minimum stops and protective-order execution receipts. Distinguish price movement from eligibility for modification.

### 3.4 Indicators and chart configuration

`IndicatorCollection` exposes `add`, `delete`, `canAdd`, `getAvailableTypes`, `getDefaultSettings`, `getPreviousSettings`, `getWindows`, `initialize`, `resetLevelsToDefault`, `resetSettingsToDefault` and `update`; REA class references: nine (`ev_81a8ca764d3428c7f7568e1cdb6d5c35cb907df2a82d5526fbd1ff00302507ab`). Chart colour/settings and indicator parameter/level editor fragments are separate.

**VAN lesson:** Model indicators as independently versioned, serialisable instances with typed parameters, window/pane placement, source timeframe and indicator-provenance tier. Keep native technical indicators separate from VATI-certified decision inputs and from research/model-derived annotations.

### 3.5 News components

REA found `TerminalNews`, `NewsMessage`, `NewsCategory`, `NewsViewer`, phone and tablet news-list/category fragments. `NewsMessage` has seven incoming-reference records (`ev_9ac23cd063d3434f13077d78016d7dcf7252a6d69bd7d5d3f1bda925af17eafc`). There is a distinct `NewsListFragment` (`ev_db820279863b25c923ebb3ee9d697a47cd5895aba43e09f2c77ecc9f3f2c7a52`).

**VAN lesson:** News is a first-class instrument/trading context, not an afterthought hidden inside a portfolio table. However, the existence of news UI does **not** prove a specific source, ingestion method, sentiment algorithm or full contextual analysis. VAN's requested news-analysis intelligence is a separate, source-backed product feature that needs its own deterministic evidence and testing.

---

## 4. REA findings — TradingView

### 4.1 A layered mobile chart API, not just a WebView

REA confirms `com.tradingview.tradingviewapp.feature.chart.api.ChartApi` with **25 member accessors** corresponding to separate typed capabilities: `getChartTypes`, `getContextMenu`, `getScreen`, `getSharing`, `getAds`, `getAlerts`, `getAuth`, `getBarReplays`, `getChartIntervals`, `getCurrencyUnit`, `getDialogs`, `getDrawings`, `getIconsSettingsDrawer`, `getInitialError`, `getMultiChartSync`, `getMultiLayout`, `getNews`, `getPaywalls`, `getSymbolInterval`, `getTheme`, `getTools`, `getTrading`, `getUndoRedo`, `getUtils` and `getZoom`. The class-level REA record is `ev_419a47f40bdf5028b18c725dea3895b8a729f69f14e815d219ec4a5a12fb0e4c`.

The directly inspected `ChartBridge` has **266 methods**, including chart type/interval mutations, drawing-tool selection, replay, broker status query, dialog/panel presentation, chart zoom and many callbacks. This is a member inventory; it includes implementation members and is not equivalent to the 167 method declarations in the packaged JS bridge configuration. REA record: `ev_90b0a34bd90f1aa0e896e23904fef8c006588e91d68ac7e5da1146c44059a40d`.

**VAN lesson:** Define a capability-oriented chart API independent of the chosen renderer and a separate, tightly scoped UI interaction bridge. A renderer can be swapped or degraded without forcing navigation, research, portfolio and trading authority to be rewritten.

### 4.2 WebMessage and session lifecycle

REA confirms `WebMessageChannel` and its declared constructor with `BridgeMessageConfig` and `WebMessagePortCompat` instances, plus `initConnection(WebView)`, `sendMessage(BridgeMessage)`, `addListener`, `removeListener`, conversion helpers and `dispose`. Record `ev_487fe63869cb91998c551ac7b8918380a2b0ca906f2e06eb68b766773b1757dc`.

REA confirms `ChartService` exposes a typed chart API and `StateFlow<WebSession>`: `getChartApi()` and `getWebSession()` (`ev_6b261b7791013bfda0294fafad15784cbc9ad742c1066a51deda8e5ae90bfc79`).

**Confirmed:** Native web-messaging abstraction, session state and lifecycle separation.  
**Not confirmed:** Domain/origin checks on every message, authentication strength, full bridge-method semantics, or whether the WebView executes specific compiled modules on every phone.

**VAN lesson:** Chart sessions must have explicit readiness and teardown. Use a typed command/event schema, session nonce, origin validation, capability allowlist, monotonic sequence, cancellation, idempotency, bounded queue, reconnect rehydration and denial by default. JavaScript is subordinate and has no direct VATI/broker credentials or mutation authority.

### 4.3 Packaged JavaScript contract: 167 methods / 49 subscriptions

The uploaded APK's byte-identical `assets/config/config.json` defines **167 bridge methods** and **49 event subscription pairs**. The attached handoff includes `tv_js_bridge_methods.json/csv` and `tv_js_bridge_subscriptions.json/csv` with every exact method name, argument schema/callback type, serializer and inferred feature category, plus an extraction script. This is `APK_RAW_CONFIRMED` source evidence, not a REA decompiler response.

Contract clusters:

| Cluster | Observed methods | Implication for VAN |
|---|---|---|
| Chart state/navigation | 66 | Native task/navigation surface can drive chart symbol, interval, layout, selection, viewport and auxiliary panels through typed requests. |
| Drawing tools | 27 | Drawings deserve own saved model, revisioning, history and tool settings—not anonymous overlay pixels. |
| Replay | 19 | A separate simulated historical chart session can support research, owner training and intelligent review without live effects. |
| Dialogs/panels | 20 | Reveal deeper capabilities on demand instead of adding all controls to a crowded Home screen. |
| Orders/broker-facing UI | 11 | Expose broker context in the chart but funnel actual mutations through independent risk/owner authority. |
| Alerts/news | 7 | Connect chart context to notification/news pages using stable event and instrument identity. |
| Other | 17 | Maintain open capability extension points without hardcoding a monolithic screen. |

The 49 subscriptions cover various chart, replay, drawing, state, interval and toolbar events. They demonstrate a useful command-versus-notification separation. Do not infer that each subscription yields real-time server market data; many are local presentation state changes.

### 4.4 Market data and reactive projections

REA inspected `MarketDataProviderImpl` (**94 methods; 49 fields**) with `StateFlow` / `MutableStateFlow` / `Channel` and domain-specific projections. Named methods include `getConnectionState`, `getContentState`, `getAllSymbols`, `getCalendar`, `getFailedRequests`, `getInternetConnected`, `getLineCharts`, `getCurrentVisibleBlocks`, `getForex`, `getFutures`, `getStocks`-family context, `getCrypto`, `getBonds`, `getEtf`, `getEvents`, and `getCurrentTabPosition`. REA record: `ev_404629f13699e0cba59045e0b8842f42ae5afa6a1adfeadb5af3c8b7e743819a`.

**VAN lesson:** Adopt a **reactive read-projection architecture** with separate source health, content status, instrument grouping, visible subscription demand and chart preview state. A single data source can feed cards, watchlists and chart panels; UI recomposition must not be the source of broker decisions or repeated subscriptions. Staleness and source failure remain first-class data, not generic snackbar text.

### 4.5 Live alerts, economic-calendar and news domains

TradingView's raw classes and names identify independently modelled alert services, an alert web API with create/modify/restart/stop/delete operations, market-news update services, `NewsListInteractor` with news-state flows, market-news cards and publication navigation, and an economic-calendar feed with country/time/importance filters. A market feed exposes a calendar-related `MutableStateFlow` in REA.

These specific alert/news/economic-calendar method signatures were **extracted from the uploaded DEX** and their domain class names are corroborated by the REA shard class inventories. Their method bodies, network traffic and upstream feeds have not all been independently decompiled.

**VAN lesson:** Keep `News`, `Calendar`, `Alerts`, `Watchlist`, `Market Movements`, `Chart Events`, and `VATI Risk Events` as related but distinct event types. A merged Intelligence UI can cross-link them while retaining source lineage. A news headline is not a tradable signal and does not alter VATI eligibility merely because a model deems it bullish.

### 4.6 Watchlists, screeners and discovery

The raw class index supports distinct service/view-model/persistence interactions for watchlists, saved symbols, search, screeners, chart previews and market groups. Candidate examples include `WatchlistService`, `MarketScreenerService`, `ThrottledSymbolSearchService`, `ScreenerScanRequest/Response` and chart-watchlist adapters; method lists are included in the portable targeted-symbol analysis.

**VAN lesson:** Implement dynamic owner and intelligence watchlists (including opportunity and position attention filters) with saved preferences, price-age labels, effect-free preview charts and bidirectional navigation into the full instrument terminal. A screener should be typed, rate-limited and provenance-aware rather than an LLM emitting a potentially unauthorised executable strategy.

### 4.7 Native preview charts and dedicated chart workstation

Raw class evidence identifies `chartnative.charts.Chart`, `BarLineChartBase`, axes, dataset, highlight and touch components independently of the chart web bridge. This does not prove the publisher's exact dual-renderer deployment strategy. Combined with the separated web chart API, however, it supports a **promising VAN design**: inexpensive native chart widgets outside the terminal; a dedicated feature-rich chart engine only when requested.

The sharp rule is **one chart capability model, at least two presentation budgets**, not two disagreeing market sources or two trading authorities.

### 4.8 TradingPanel and broker connectivity

Raw DEX names and methods identify `TradingInteractor`, `TradingInteractorImpl`, broker connection status requests/subscriptions, `placeOrder`, and broker OAuth interaction. The REA-verified chart API exposes a separate trading capability, and `ChartBridge` has broker-status queries. **Do not adopt their broker authorization design or assume a `placeOrder` in a client class means VAN should place broker orders directly.**

VAN's authority separation is more important than parity with this method surface: Android may assemble and sign a typed owner proposal where authorised; VATI/risk/router/broker enforce execution and independent readback. Do not put access keys or broker sessions into renderer-controlled JavaScript.

---

## 5. Direct comparison and adoption judgements

| Theme | MT5 evidence | TradingView evidence | VAN outcome | Action |
|---|---|---|---|---|
| Rendering | SurfaceTexture/EGL-aware chart surface; separate renderer | Typed chart API + WebMessage bridge; native chart classes also present | Dedicated chart lifecycle + native previews + isolated professional engine | **ADAPT** |
| Instrument detail | Price/order and position model fields | Symbol state, chart navigation and discovery modules | Canonical symbol/instrument contract with venue, currency, precision and feed identity | **ADOPT PRINCIPLE** |
| Live data | Chart ready/requesting/processing states | `StateFlow` market projections, failed requests, visible blocks | Timestamped reactive read models, backpressure and subscribe only what is visible | **ADAPT** |
| Indicators | IndicatorCollection and per-window settings | Indicator/drawing/replay feature API surfaces | Versioned indicator registry with provenance tiers | **ADAPT** |
| Drawings | MT5 chart/edit modes | Drawing APIs and event subscriptions | Durable evidence-linked drawing model, owner annotations and replay capture | **ADAPT** |
| Trading | Rich order states/pending types/fill policies | Chart trading panel + broker-status interfaces | Exact owner draft/approval lifecycle governed by VATI and verified broker receipts | **KEEP VAN AUTHORITY** |
| Positions | Explicit `sl`, `tp`, price/volume/profit and eligibility | Position/trading UI integrations | Broker-authoritative position overlays and protected edit proposals | **ADAPT** |
| Replay | Not fully mapped in this MT5 study | Replay API and settings/events | Clearly labelled isolated historical research and manual training sandbox | **ADAPT** |
| News | News model/category/list/viewer classes | News Flow, news updates, market cards, calendar | Source-backed full analysis and joins to strategy/portfolio and event-risk | **EXTEND BEYOND BOTH** |
| Alerts | Android notification capabilities | Alert API + chart event subscriptions | Canonical event identity, dedupe, user policy, orb state and route actions | **ADAPT** |
| Intelligence | Server strategy internals not exposed | UI research/news/calendar structures; no VATI analogue | VAN/JEV analysis of canonical verified evidence, not model-as-authority | **KEEP VAN** |
| Visual appearance | Precision trading UI, not VAN look | Multi-panel technical workflow, not VAN look | Locked Tactile Spatial dark/light reference, calm Home, progressive disclosure | **REJECT STYLE PORT** |
| Proprietary code/data | Closed-source components | Closed-source JavaScript and chart code | Do not import or repackage competitor code/assets or unauthorised premium feeds | **REJECT PORT** |

**Interpretation:** The best engineering transfer is architectural separation and user-workflow ergonomics, not implementation cloning. User-approved design and existing VAN capabilities take priority over these references.

---

## 6. Architectural requirements for VAN Next

### 6.1 Logical planes and authority ownership

```text
Android VAN Tactile Spatial Application
  ├── Home + dimensional state-aware Orb + compact Quick Hub
  ├── Trading Home (Markets | Watchlist | Opportunities | Chart | Intelligence)
  ├── NativeChartPreview widgets
  ├── ProfessionalChartWorkspace
  │   ├── Trusted Compose toolbar, tool sheets and account/security chrome
  │   ├── RendererAdapter (candidate web/native renderer, off main thread)
  │   ├── TypedChartBridge (presentation and research only)
  │   ├── Drawings/Indicator/Workspace/Replay presentation
  │   └── DraftIntentOverlay (never direct broker authority)
  ├── Position Detail, Orders, History, Accounts
  ├── News Intelligence + source/research reports
  └── Projects/Tasks/Agents Spatial Flow
                      |
              VAN Owner Gateway
                      |
        canonical observations, revisions,
        user choices, rights and receipts
          /                            \
  Market/News/Calendar             Work/Agent Evidence
  Licensed/Ingested Feeds          DIAL Development Fabric
          |                            |
  Read Models + Market Projection       |
          |                            |
  Research/JEV/LLM evidence <-----------+
     (read-only, bounded, explainable)
          |
  VATI policy/risk/execution authority ONLY
          |
  Broker router -> broker -> readback/ledger receipt
```

### 6.2 Proposed Android module boundaries

- `van.next.shell`: status, navigation, dark/light theme, privacy mode, back stack, short action sheets, native accessibility.
- `van.next.material`: accepted metallic/ceramic surfaces, elevation, token roles, controlled lighting, motion and scrim components.
- `van.next.orb`: orthogonal activity, health, authority, trade-event and attention reducer; shared Home/Floating representations.
- `van.next.market`: instrument identity, quote projection, symbol mapping, time and quality flags, subscription policy.
- `van.next.chart.contract`: typed chart capabilities, command schema, snapshots, chart workspace state, features and backpressure.
- `van.next.chart.preview`: small native price previews and reusable sparklines.
- `van.next.chart.workstation`: advanced renderer host with session lifecycle, tool sheets and accessibility fallback.
- `van.next.indicators`: typed indicator instances and parameter/pane registry.
- `van.next.drawings`: canonical drawings, coordinate systems, revisions and provenance.
- `van.next.replay`: historical session, deterministic timeline and no-live-effect guarantee.
- `van.next.trading`: provider-aware owner read models, draft intents, order/protection workflows and receipts.
- `van.next.intelligence`: news, calendars, live analyst, review, evidence and strategy/position relevance.
- `van.next.workflow`: spatial graph, live agent positions, task status/critical path, truth/receipt projection.
- `van.next.voice-overlay`: preserved Floating VAN gestures, voice/chat and OS lifecycle with new presentation.
- `van.next.compat`: typed adapters to current qualified gateway, storage, device proof, approval and deep-link protocols.

These are **proposed logical boundaries**, not an instruction to rename/install packages immediately. The migration must preserve Android signing, existing owner pairing, device authority, safe restoration and verified functionality. A compatibility adapter may remain until a replacement is qualified.

### 6.3 Chart Bridge — explicit, limited authority

**Example proposed envelope, not discovered TradingView or implemented VAN JSON:**

```json
{
  "schema": "van.chart.bridge.v1",
  "session_id": "opaque-session",
  "message_id": "opaque-uuid",
  "seq": 152,
  "created_at": "2026-10-15T12:00:00Z",
  "expires_at": "2026-10-15T12:00:04Z",
  "origin": "TRUSTED_NATIVE_CHART_HOST",
  "kind": "PRESENTATION_CHANGE",
  "capability": "chart.indicator.add",
  "payload": {"indicator_id":"rsi","params_ref":"immutable-params-id"},
  "data_revision": "market-revision-id",
  "authority_effect": "NONE"
}
```

Require strict version and capability negotiation, one configured origin, message-size limits, types and enum exhaustiveness, no arbitrary JavaScript commands, monotonic sequence and idempotency keys, per-session cancellation and teardown, and bounded event aggregation. All presentation effects are local and **non-authoritative**. A public WebView or downloaded chart bundle never receives owner approval tokens, brokerage secrets or VATI control grants.

### 6.4 Data projection and event streams

A canonical quote/bar/position snapshot needs symbol identity (not just ticker string), asset class/venue, data provider, account scope where applicable, timestamp of event, local observation time, revision/sequence, time-zone unit, price precision/tick size, validity/stale category, and stream status. Manage visible subscriptions; batch updates; coalesce high-frequency price ticks separately from slower portfolio, approval and strategy transitions. Recover via revisioned snapshot after stream gaps; use last-known data with clearly marked age.

The `Chart` and `Watchlist` consume the same underlying market projection, not independent quote pollers. Any cached chart is displayed as cached, not live. Only broker reconciler can assert position success or protection status.

### 6.5 New high-value interaction: chart to backend intelligence

The Android frontend can materially help backend reasoning by emitting **structured, owner-authorised observations**, not executable instructions:

- instrument and timeframe under investigation;
- chart viewport, selected bars, indicator identities/parameters and relevant revisions;
- observed support/resistance drawing geometry with exact price/time anchors;
- owner annotations with source, intent and correction history;
- replay experiments, hypotheses, decisions and post-hoc outcomes;
- news-event joins, market reaction windows and strategy relevance;
- explicit user feedback on why an opportunity was interesting, dismissed, wrong or unsupported.

These feed `ChartObservationEnvelope` / `ResearchObservationArtifact` through VAN gateway with bounded retention, provenance, quality/freshness, privacy consent and replay protection. The backend can contextualise and evaluate—but cannot mint risk authority, change strategy qualification or make an order because an annotation/LLM prompt says so. Source/owner confirmation, reproducible analysis and deliberate admission are required before any learned fact influences VATI's protected policy plane.

### 6.6 Position/Order draft lane

```text
Touch stop/target on chart → local draft overlay
→ instrument/account precision verification
→ provider capabilities / limits / risk preview
→ exact proposed diff, TTL and owner-intent scope
→ required biometrics / device-signed owner grant
→ VATI deterministic policy & risk approval
→ broker/router mutation
→ independent broker readback & ledger
→ VERIFIED / REJECTED / PARTIAL / OUTCOME_UNKNOWN
→ chart overlay update from authoritative truth
```

**Negative invariant:** The chart renderer, News page, replay engine, Floating Orb, alert handler, JEV, LLM or task agent has no direct order endpoint or bearer to one. Disconnected/offline/doubtful execution outcomes never report success or auto-retry consequential trades.

### 6.7 News, calendar and market-event intelligence

Deduplicate stories/press releases/calendar events; identify original publisher, time, correction lineage and licence; link claimed facts separately from verified market reaction; track affected instruments, positions, opportunities, strategies and chart time windows. Produce a `NewsAnalysisArtifact` with supports, contradictions, scenarios, observation timestamps, invalidation conditions, uncertainty and citations. Model narratives remain advisory. Real-time event triggers may notify or update the orb by priority only when source freshness and the configured event materiality warrant it.

### 6.8 Orb and Quick Hub coherence

The Home orb is a shared visual projection of canonical event states, not an omnipotent finance chatbot. It retains the accepted sculpted dimensional appearance and subtle semantic glow. No legend appears on Home. A tap opens a **compact** sheet showing only the most important alert, a tiny active-position performance line, task/progress summary and a few routes; full detail belongs to the destination screen. Trading chart/news/agent events feed the reducer by typed priority and TTL, not directly from unchecked JavaScript messages.

### 6.9 Projects and task graphs

The new professional trading interface should not undo the separate Work/Projects scope. Adopt the same *state projection versus rendered UI* separation: real dependency/agent nodes with live revisions, task ownership, blockers and receipts drive tactile diagram nodes; the diagram is a view, not the source of task authority. Preserve accessible list navigation and approved owner commands.

---

## 7. Requirements-to-adoption map (priority and proof)

| ID | Requirement/decision | Priority | Evidence class | Main DIAL tests |
|---|---|---|---|---|
| REA-VAN-001 | Accepted Tactile Spatial visual grammar remains immutable without owner review | P0 | Owner authority | Golden screen fidelity in dark and light; visual regression on S24 |
| REA-VAN-002 | Native chart previews separate from heavy chart workstation | P1 | APK_RAW_CONFIRMED + INFERENCE | Low-power scroll, thumb FPS, app cold-start, no heavy worker per row |
| REA-VAN-003 | Typed renderer-independent chart capability interface | P0 | REA_CONFIRMED + INFERENCE | Renderer swap, invalid capability rejection, no UI rewrite |
| REA-VAN-004 | Web chart bridge restricted to presentation/research | P0 | REA_CONFIRMED + VAN authority | Origin and schema fuzz, no broker credentials, forbidden order call test |
| REA-VAN-005 | Exact provider-aware order lifecycle | P0 | MT5 REA_CONFIRMED | Partial, reject, cancel, expire, unknown, reconciliation and anti-duplicate |
| REA-VAN-006 | Authoritative, auditable chart SL/TP proposals | P0 | MT5 REA_CONFIRMED + VAN authority | Drag preview cannot execute; biometric/nonce/readback proof |
| REA-VAN-007 | Separate stream freshness, viewport/visibility and source failures | P0 | TV REA_CONFIRMED | Stale/offline/gap, sequence, viewport subscription tests |
| REA-VAN-008 | Indicator/drawing models with persistent source-referenced provenance | P1 | MT5/TV REA_CONFIRMED | Versioned params, chart geometry roundtrip, replay determinism |
| REA-VAN-009 | True isolated chart replay | P1 | TV APK_RAW_CONFIRMED + REA domain | Replay cannot reach live order endpoints; deterministic bars/events |
| REA-VAN-010 | News/calendar/market reaction research report | P0 | MT5/TV structure + user requirement | Source correction, stale/unknowns, contradiction, news/position join |
| REA-VAN-011 | Portfolio/account/order/quote UI agrees on canonical revision | P0 | VAN source + inference | Owner account isolation, privacy, cross-route read consistency |
| REA-VAN-012 | Chart-context evidence assists backend JEV/research without enabling trade | P0 | User requirement + inference | Evidence admission, no authority expansion, retention/privacy/counterexample |
| REA-VAN-013 | F0–F15 forensic/DIAL qualification for adopted capabilities | P0 | DIAL FFDRM | Independent runtime/device/owner receipts, replayable mutation tests |
| REA-VAN-014 | Complete physical Samsung S24 E2E and accessibility | P0 | Existing unqualified handset state | touch target, chart interaction, 60/120Hz devices, battery, overlays |
| REA-VAN-015 | REA artifacts version- and digest-bound | P0 | REA evidence | Exact APK/JADX evidence IDs and no mislabelled manifests |

---

## 8. DIAL implementation sequence and gates

The roadmap is additive to the **VAN Tactile Spatial Redesign Blueprint Rev 1**; no legacy UI copy is admitted as a shortcut.

| DU | Development unit | Dependency | Done condition |
|---|---|---|---|
| DU-REA-00 | Freeze accepted dark/light references, owner requirements, REA evidence, source SHA and branch reconciliation | none | Deterministic visual/functional source ledger, approved scope, no stale refs |
| DU-REA-01 | Reconcile VAN `main` with candidate PR #93 and other relevant branches; protect qualified backend and device pairing | 00 | Conflict/adoption ledger, no unreviewed old UI transitively retained |
| DU-REA-02 | Build new Tactile Spatial component/interaction and anti-contamination gate | 00/01 | Golden visuals, tokens, material/motion, accessibility and override review |
| DU-REA-03 | Canonical market, symbol, quote, position, order and account projection contracts | 01 | Provider-state versioned models, no stale claims, ownership tests |
| DU-REA-04 | Chart capability contract and native preview engine | 02/03 | Live preview with subscription budget, cache state, no false precision |
| DU-REA-05 | Professional chart renderer evaluation/qualification; isolated chart host | 03/04 | Chart instruments, UI lifecycle, crosshair/zoom/gesture acceptance, resource budgets |
| DU-REA-06 | Chart bridge, drawing/indicator state, persistent workspaces | 05 | Typed security, protocol tests, reproduction and bridge deny-by-default |
| DU-REA-07 | Position/order protection overlays and owner draft lane | 03/05/06 | Broker/ledger readback, risk/owner approval, negative mutation cases |
| DU-REA-08 | Independent replay sandbox and research observation bridge | 03/06 | Replay reproducibility, provenance, NoExecutionAuthority tests |
| DU-REA-09 | Intelligence/News/Calendar + event and portfolio research joins | 03/08 | Source corrections, evidence/revision confidence, scenario/invalidation support |
| DU-REA-10 | Trading Home, Markets, Watchlist, Opportunities, Chart, Intelligence composition | 02/04/07/09 | Five primary entries, calm first fold, no feature thinning; all detail routes accessible |
| DU-REA-11 | Shared orb event reducer, compact quick hub, Floating VAN visual parity | 02/03/09/10 | Multi-event precedence, offscreen power budget, true source-based notifications |
| DU-REA-12 | Spatial project/task diagrams and cross-app agent activity truth | 02 | Project/task/agent dependency/evidence semantics, mobile diagram and list parity |
| DU-REA-13 | Full 78-surface preservation/migration reconciliation and resilience testing | all | No functional-loss gaps, independent security and handset receipts |
| DU-REA-14 | Zuul/independent qualification, controlled rollout and rollback | 13 | Exact source/build identity, S24 acceptance, owner approval, no live service disruptions |

Do not mark any DU as done from this research alone. Before changing code, produce a project-scoped DIAL Development Pack with Product Truth lineage, feature/screen/action/state/authority/evidence graphs and current qualified source baseline. Apply the current DIAL F0–F15 forensic gates and independently qualify each production caller and postcondition; an old source assertion, REA class presence or passed unit test cannot close a runtime gate by itself.

### Non-negotiable acceptance cases

- Open and close the chart 500 times across background, restore, rotation and texture loss without stale chart/order overlays.
- Two pages viewing one symbol share one underlying data subscription or an explicitly bounded deduplicated equivalent.
- Source feed disconnect and reconnect recover from authoritative snapshot/revision; no fake live chart/timestamp.
- Touch-drag of SL/TP creates a proposal only. There is no broker mutation before exact authenticated owner intent, risk validation and readback.
- Repeated network POST after timeout does not produce duplicate orders or repeated receipt confirmation.
- Symbol alias conflict or differing tick/lot units blocks order proposal, not silently rounds it.
- JEV/LLM/news commentary cannot raise a blocked candidate to an executable order.
- Cached news/market reaction cannot masquerade as an observed current fact.
- Risk/approval status persists across Home, Chart, Position Detail and Floating VAN consistently.
- Replay, screenshots, rich drawings, chart widgets and evidence reporting are separately measured for memory, CPU, GPU and battery on Samsung S24 Ultra.
- Accessibility alternative to chart gestures and all dense tables; native screen reader test and reduced-motion settings.
- Dark/light theme fidelity against the accepted screenshots; semantic caution states never become noisy rainbow dashboards.

These are **proposed tests and targets**, not measured results.

---

## 9. Limitations, unanswered questions and falsification work

1. **No dynamic Android execution.** Neither source APK has been launched in an Android guest/handset through this REA lab. `/dev/kvm` and connected ADB sessions were absent at inspection time. Interaction responsiveness, performance, authentication, chart CPU/GPU and end-to-end broker lifecycle are unmeasured.
2. **No upstream/server reverse engineering.** No proof of broker execution internals, TradingView's data-feed stack, cloud indicator algorithms, full chart rendering engine internals or MetaQuotes server protocols. The client APK alone cannot establish them.
3. **Secondary TradingView build.** Compiled DEX and assets are byte-identical to user attachment, but APK container, binary manifest and signing lineage differ; keep those claims separate.
4. **Partitioned JADX scope.** Seven independently analysed DEX shards produce complete per-shard class-names coverage but not guaranteed cross-DEX references or exact multi-DEX linking. The original uploaded DEX index is used for full declared-method coverage.
5. **Decompilation scope limited.** The report provides REA inventories, representative class member lists, and selected MT5 decompiled method receipts. It is **not** decompiled source for every declared method in the two apps. Full on-host REA evidence records and portable original-Dex method inventories are indexed.
6. **Play split APK.** The supplied TradingView base APK declares a required ABI split and has no `.so` libraries; live on-device verification needs the actual install package set.
7. **Source currency.** Results apply to the two exact versions/hashes. They should not be sold as statements about later MT5/TradingView versions.
8. **Design impact is proposed.** The accepted VAN visual DNA remains unchanged; no implementation or qualified deployment has occurred as part of this research.
9. **Independent forensic challenge pending.** Opus/DIAL should try to falsify bridge ownership, dataflow, method authenticity, state merges, source/asset lineage, readback semantics, and native chart performance before implementing.

**Unresolved research to perform if higher confidence is required:** Install verified full TradingView split set on an authorised handset/device; capture UI and trace chart lifecycle in instrumented owned sessions; inspect `ChartBridge` call sequences and origin/messaging policies; run measured chart renderer comparisons on S24; evaluate replay/drawing geometry accuracy; validate real news data provider contracts; confirm broker-authoritative pending-order/SL/TP route capabilities; compare strategy/event research joins against current VAN/VATI runtime.

---

## 10. Evidence and portable files for Opus 5.5

### 10.1 Remote REA (true REA/JADX files)

**Host:** `van-trading-core` via Global DIAL MCP typed grants.  
**Root evidence folder:** `/opt/van-rea-lab/evidence`  
**Index (39 verified REA records):** `OPUS55_REA_VM_EVIDENCE_INDEX_20261015.json`  
**Index SHA-256:** `829af2ed8c9784da2a6affd5d093bd22e6e7dd1066c6a05af64cbea61e333744`

MT5 examples:
- `mt5_package_inspection_20261015.json`, `mt5_all_classes_20261015.json`
- `mt5_class_detail_1..4_20261015.json`, `mt5_extra_3..4_20261015.json`
- `mt5_chart_surface_refs_20261015.json`, `mt5_trade_order_refs_20261015.json`, `mt5_trade_position_refs_20261015.json`, `mt5_indicator_collection_refs_20261015.json`, `mt5_news_message_refs_20261015.json`
- `mt5_method_1..3_20261015.json` for decompilation evidence.

TradingView examples:
- `tradingview_package_20261015.json`
- `tv_rea_dex1_full_classes_20261015.json` through `tv_rea_dex7_full_classes_20261015.json`
- `tv_rea_class_chartbridge_20261015.json`, `tv_rea_class_chartapi_20261015.json`, `tv_rea_class_webmessagechannel_20261015.json`, `tv_rea_class_chartservice_20261015.json`, `tv_rea_class_marketdataprovider_20261015.json`
- `tradingview_full_class_inventory_20261015.json` records **an attempted timeout** and is not successful REA analysis.

The digest-bound full catalog is more authoritative than a manually abbreviated file list; Opus should read it first.

### 10.2 Portable evidence from the exact uploaded APK

The accompanying evidence pack contains:

- `tradingview_apk_metadata.json` — original SHA/version, DEX and archive facts, manifest, signing-block parser record and explicit methodology.
- `tradingview_class_inventory.jsonl` — every raw DEX class definition, linked to its source DEX and metadata.
- `tradingview_method_inventory.jsonl` — every declared DEX method implementation and type/signature metadata.
- `tradingview_field_inventory.jsonl` — every declared DEX field implementation.
- `tradingview_archive_entries.jsonl` — original archive member inventory.
- `tradingview_targeted_symbol_contracts.json` — curated high-value method/field contracts for chart, news, alerts, calendar, screeners, watchlists and trading.
- `tv_js_bridge_methods.json/csv` — all 167 bridge methods and their typed input/output metadata.
- `tv_js_bridge_subscriptions.json/csv` — all 49 bridge subscriptions and callbacks.
- `tradingview_derived_overview.json` — package/feature counts and namespace groupings.
- Reproducible read-only Python extraction scripts.

`tradingview_strings_dex.jsonl` is excluded from the standard portable ZIP because raw strings can contain unrelated identifiers, embedded private material or copyrighted text; it remains only in the local analytical workspace if a private forensic reviewer needs it. The method/class inventories themselves are metadata, not original full proprietary decompiled bodies.

### 10.3 Required Opus evidence discipline

For each conclusion in a handoff review, use:

`claim_id → owner_requirement_id → source_kind → APK_SHA256/DEX_SHA256 → REA_evidence_id_or_RAW_FILE → class/method/event → observed_fact → inference → VAN_DU → tests → independent_qualification_state`

Where a source lacks a link, mark it `INFERENCE` or `OPEN_GAP`. Do not fabricate a REA trace or upgrade static presence to qualified live behaviour.

---

## 11. Final research verdict

**Adopt engineering concepts, not competitor code.** MT5's exact order/protection and chart-lifecycle modelling and TradingView's typed chart capability/messaging/data-flow structure are complementary. VAN can combine them into a professional, state-coherent and visually restrained trading experience that contributes useful, explainable and bounded observations to backend intelligence. Its differentiation remains its own deterministic risk and execution authority, source-backed news intelligence, integrated task/agent workflow, owner command controls and state-aware orb.

**No automatic production modification is authorised by this report.** First reconcile the candidate VAN branches and dependencies, then build and qualify the explicit Development Units against the approved visual references and owner-action contracts.
