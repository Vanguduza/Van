# Review of the MT5 / TradingView REA study (15 October 2026)

**Reviewed:** `VAN_REA_MT5_TRADINGVIEW_FULL_RESEARCH_20261015.md` (`VAN-REA-RESEARCH-20261015-R1`) and its portable evidence pack `VAN_REA_Opus55_Full_Evidence_Pack_20261015.zip`.
**Applied in:** blueprint Rev 1.5 §7.8 (OD-15).
**Scope of this review:** checked the portable evidence, compared the findings with VAN's current code, and graded each recommendation. I did not run either app, did not decompile anything, and could not read the 39 remote REA records on `van-trading-core` (no Global DIAL MCP in this session).

## 1. What was verified

| Claim in the study | Check | Result |
|---|---|---|
| Portable pack integrity | SHA-256 of all 25 files against `MANIFEST_SHA256.json` | 25/25 match |
| TradingView bridge contract: 167 methods, 49 subscriptions | Counted `tv_js_bridge_methods.json/csv` and `tv_js_bridge_subscriptions.json/csv` | 167 and 49 |
| Method clusters 66 / 27 / 20 / 19 / 17 / 11 / 7 | Counted the `category` column | Exact match |
| 70,877 raw class definitions in 7 DEX files | Summed `class_defs` in `tradingview_apk_metadata.json` | 70,877 across 7 |
| Uploaded APK SHA-256 `dfbc561d…71b1`, 105,686,346 bytes | Read from the metadata file (the APK itself is not in the pack) | Matches the metadata; not independently re-hashed |
| MT5 class, method and decompilation findings (`ChartSurface`, `TradeOrder`, `TradePosition`, `IndicatorCollection`, news classes) | Need the remote REA records | **Not verified here**; graded as the study's `REA_CONFIRMED` claims |

The study is careful about evidence classes and repeatedly marks dynamic behaviour as unproven. I found no overclaiming in the parts I could check.

## 2. Findings compared with VAN today

| Study lesson | VAN today (code read 15 Oct, `main` 8eb1889) | Gap? | Applied as |
|---|---|---|---|
| Reactive, shared market projection with visible-subscription demand and freshness | Android: each screen calls one-shot `suspend` repository functions on a refresh tick (`TradingRepository.kt`; `LaunchedEffect(tick)` in Overview and Positions). No shared store, no subscription de-duplication. | **Yes** | §7.8.1 |
| Chart frame production separate from UI recomposition; surface lifecycle | Single Compose `Canvas` (`TradeChartCanvas.kt`) with pan/zoom/crosshair and levels, drawn inside recomposition | **Yes** | §7.8.2 |
| Renderer-independent typed chart capability API | None (one composable) | **Yes** | §7.8.2 |
| Typed, origin-checked web bridge with no authority | Blueprint §14.3 already restricts chart outputs; no envelope spec | Partly | §7.8.3 |
| Indicators and drawings as typed, saved models | Price levels only; no indicator or drawing model | **Yes** | §7.8.4 |
| Replay | None | **Yes** | §7.8.5 |
| Rich order vocabulary; never collapse states | VATI `ExecutionReceipt` already has `ACCEPTED/PARTIAL/FILLED/REJECTED/CANCELLED/EXPIRED/UNKNOWN`; entry types `MARKET/LIMIT/STOP/PASSIVE_LIMIT/CONTRACT_BUY`; TIF `DAY/GTC30` | Partly: no stop-limit, no fill policy, no specified expiry, no distinct WORKING state | §7.8.6 |
| Chart drag → draft proposal only | Blueprint §7.4 and §14.3 already require it | No | Confirmed |
| Chart observations to backend intelligence | Not present | **Yes** | §7.8.7 |
| Alerts as their own domain | Attention exists; no price/indicator/drawing alerts | **Yes** | §7.8.8 |
| Watchlists and screener | Not present (blueprint DU-12 planned) | **Yes** | §7.8.9 |
| News and calendar as first-class context | Blueprint §8 already goes beyond both apps | No | Confirmed |
| Project/task graph as a view over real state | Blueprint §9 | No | Confirmed |

## 3. Grading of the study's recommendations

| Study ID | Recommendation | Grade | Note |
|---|---|---|---|
| REA-VAN-001 | Visual grammar stays locked | KEEP_VAN | Already the rule |
| REA-VAN-002 | Native previews separate from workstation | ADOPT (architecture) | §7.8.2 |
| REA-VAN-003 | Renderer-independent chart capability interface | ADOPT | §7.8.2; renderer chosen by S24 measurement (OQ-14) |
| REA-VAN-004 | Web bridge presentation-only | ADOPT | §7.8.3 |
| REA-VAN-005 | Exact provider-aware order lifecycle | ADAPT | VATI already strong; add missing vocabulary per venue (§7.8.6) |
| REA-VAN-006 | Chart SL/TP proposals only | KEEP_VAN | Already in §7.4/§14.3 |
| REA-VAN-007 | Stream freshness, visibility, failures | ADOPT | §7.8.1 |
| REA-VAN-008 | Indicator/drawing provenance models | ADOPT | §7.8.4 |
| REA-VAN-009 | Isolated replay | ADOPT | §7.8.5, linked to behaviour diagnostics as practice data |
| REA-VAN-010 | News/calendar/market-reaction research | KEEP_VAN | Blueprint §8 already exceeds it |
| REA-VAN-011 | Canonical revision across screens | ADOPT | §7.8.1 |
| REA-VAN-012 | Chart context assists research without authority | ADOPT | §7.8.7 |
| REA-VAN-013–015 | Qualification, S24 E2E, evidence binding | KEEP_VAN | Existing gates |
| — | Competitor style, layouts, code, assets, paywalls, broker-auth design, client-side `placeOrder` | REJECT | As the study itself recommends |

## 4. Points to correct or watch

1. **Module list vs blueprint.** The study's module list (§6.2) uses `van.next.*` package names; the blueprint's §12.2/§12.6 tree and Gradle-module isolation are authoritative. Map rather than rename.
2. **Trading Home naming.** The study still says "Opportunities"; the system label is "Potential trades" (blueprint §2.6).
3. **Not covered by the study:** news-trading latency, manual trading flows, and the cTrader/Deriv adapters VAN actually uses. MT5 lessons on order vocabulary must be checked against each VAN venue's real capabilities.
4. **Legal posture.** The study used the user's uploaded APK and an official MT5 download for static analysis and extracted architecture, not code. Keep it that way: the method inventories stay out of the VAN repository (only this review and the report are committed), and no class names or bridge method names become VAN API names.

## 5. Open items

- **OQ-14:** choose the workstation renderer (extend the native canvas, a new native engine, or a qualified web engine) from S24 measurements of frame time, memory, battery and gesture latency.
- Read the 39 remote REA records on `van-trading-core` to verify the MT5 claims this review could not reach.
