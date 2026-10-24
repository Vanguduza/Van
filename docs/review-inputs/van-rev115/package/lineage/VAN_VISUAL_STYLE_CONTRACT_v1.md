# VAN Graphite Command
## Deterministic visual style contract · Version 1.0.0

**Prepared:** 17 October 2026  
**Benchmark:** the owner's supplied 1536 × 1024 VAN presentation image  
**Status:** complete proposed style specification and reference implementation; owner approval and application qualification pending  
**Scope:** visual identity, tokens, components, responsive composition and verification. No repository, live application, trading configuration or infrastructure has been changed.

---

## 1. The identity to preserve

The benchmark establishes a **graphite, precision-instrument interface with restrained metallic depth**. Its identity is not simply “dark mode,” generic glass panels, or blue gradients. The important combination is a charcoal foundation, lightly raised graphite cards, soft upper-edge highlights, recessed working areas, silver typography and small amounts of functional colour.

The sphere and analyst avatar supply the richest material detail. Ordinary controls remain quieter. This contrast is important: making every card glossy, illuminated or animated would dilute the reference rather than reproduce it.

The production style should feel composed, tactile and operational. Colour has a job: blue identifies interaction and buy-side controls; mint indicates positive results; rose indicates negative results and separately supplies the sell-side treatment; muted gold identifies watch/caution and selected asset accents. Cyan is a tightly controlled identity/focus accent, not a full-screen glow.

**Style invariant:** graphite dominates the interface; a component gets emphasis through hierarchy, edge treatment, spacing and semantic state before it gets more colour.

**Not part of the app:** the poster's surrounding gradient, phone hardware, Dynamic Island, status-bar illustrations, lower captions, promotional slogans and framing. Native system UI and safe-area insets belong to the platform. Do not draw an iPhone frame inside the Android application.

## 2. What was measured, and what was designed

The original image is preserved at `benchmark/benchmark.png`. Its SHA-256 is recorded in `benchmark-analysis.json` and the package lock. The analysis records exact sampling rectangles and foreground masks. RGB samples are interpreted as sRGB for this reconstruction; the original colour-management and lighting pipeline is unknown.

| Region | Median of selected rendered pixels | Adopted implementation role |
|---|---|---|
| Trading screen, upper background | `#2A3235` | `color.canvasTop = #2A3235` |
| Trading screen, lower background | `#181D21` | `color.canvas = #181D21` |
| Position card, upper surface | `#363D40` | `color.surfaceTop = #363D40` |
| Portfolio card, lower surface | `#293035` | `color.surface = #293035` |
| Chart working area | `#10181E` | `color.inset = #10181E` |
| Heading foreground mask | `#F6FAFC` | `color.textPrimary = #F1F5F6` |
| Positive-result foreground mask | `#8EC3B5` | `color.positive = #98DFC8` |
| Negative-result foreground mask | `#BE7F7B` | `color.negative = #F0A09A` |
| Active-navigation foreground mask | `#6EACCE` | `color.accent = #8DC8E8` |
| Orb cyan foreground mask | `#A0CCDC` | `color.focus = #A0DCE7` |

These medians are evidence about rendered pixels, not proof of the original designer's token values. Anti-aliasing, compositing, gradients, image scaling and illumination influence the samples. Text and accent colours have deliberately been normalized and, in several cases, brightened to support legibility across the selected surfaces.

The screenshot does **not** establish the original font, logical viewport size, font files, component source, 3D scene, hidden states, animation or tablet/desktop layouts. This contract explicitly chooses those missing rules instead of pretending they were measured.

The design-space reference width is **390 logical units**. That is a reconstruction decision. Image pixels have not been treated as Android dp. Layout dimensions map to CSS logical px / Android dp; typography maps to CSS rem relative to a 16-unit base / Android sp. Platform font scaling and system insets remain active.

## 3. Determinism: the actual boundary

The initial interpretation of an image contains judgment. It is not mathematically determined by the pixels. Determinism starts after the selected interpretation is encoded and approved.

For this package:

```text
approved style version
+ approved assets and font artifacts
+ tokens and component recipes
+ screen composition and semantic states
+ viewport, font scale, locale and data fixtures
+ pinned compiler and rendering environment
= reproducible platform-specific rendering
```

A fresh AI interpretation of the image for every screen is expressly outside that boundary. A prompt is supporting documentation, not an enforcement mechanism.

The token source is `VAN.tokens.json`. The included compiler mechanically emits CSS variables, typography classes and Kotlin token definitions. It is a small compiler for the types used in this package, not a general image-to-system compiler or a full DTCG implementation.

This version defines **115 tokens**, **16 component recipes** and **five reference screen specimens**. A versioned contract fixes the style choices; production pixel reproducibility still requires approved font/asset artifacts and a pinned rendering environment.

## 4. Exact colour system

| Semantic token | Value | Use |
|---|---|---|
| `color.canvas` | `#181D21` | Main dark foundation |
| `color.canvasTop` | `#2A3235` | Upper end of the screen gradient |
| `color.surface` | `#293035` | Main card lower/base colour |
| `color.surfaceTop` | `#363D40` | Upper end of the card gradient |
| `color.surfaceRaised` | `#3D474C` | Raised controls; maximum ordinary surface brightness |
| `color.inset` | `#10181E` | Chart, fields and recessed working areas |
| `color.navigation` | `#20272B` | Navigation and subdued inset groups |
| `color.borderDecorative` | `#536168` | Decorative card rim; not a sufficient universal control outline |
| `color.borderControl` | `#83949D` | Necessary field/control boundary |
| `color.textPrimary` | `#F1F5F6` | Headings, main values, key labels |
| `color.textSecondary` | `#C4CDD1` | Supporting explanations |
| `color.textMuted` | `#ADBCC3` | Timestamps and secondary labels; not low-opacity text |
| `color.accent` | `#8DC8E8` | Selected navigation and informational emphasis |
| `color.focus` | `#A0DCE7` | Keyboard focus and identity cyan |
| `color.positive` | `#98DFC8` | Positive result / verified healthy state |
| `color.negative` | `#F0A09A` | Negative result / error |
| `color.warning` | `#DFC38D` | Watch/caution |

Buy buttons use a vertical `#35576B → #243F50` gradient. Sell buttons use `#69464B → #4E3338`. Both use primary light text. Blue buy and rose sell are **directional conventions**, whereas mint/rose profit and loss describe a result. Do not equate a buy order with a profitable order.

Instrument identities may retain their own approved icon colours. Those colours must not automatically become page accents. Flags in the benchmark are not a requirement to use emoji; use a consistent asset pipeline.

Do not apply opacity to an entire card containing readable text. For inactive controls, use the explicit disabled tokens and semantics. Disabled, warning, error, stale and pending are distinct states.

## 5. Material and elevation

Ordinary surfaces are opaque. Backdrop blur is **zero**. Translucent glass is not the defining material in this benchmark.

**Screen:** fixed top-to-bottom gradient from `canvasTop` to `canvas`.

**Card:** fixed top-to-bottom gradient from `surfaceTop` to `surface`, a 1-unit decorative rim, 20-unit corner radius, and the following two-layer shadow:

```css
box-shadow:
  0 4px 8px 0 rgba(0, 0, 0, 0.32),
  inset 0 1px 0 0 rgba(241, 245, 246, 0.12);
```

**Raised control:** upper surface `surfaceRaised`, base `surface`; shadow `0 6px 12px rgba(0,0,0,.38)` and an upper inset highlight with alpha `.16`.

**Pressed:** inset `0 2px 4px rgba(0,0,0,.35)`; no geometry shift. Pressed state must not move neighbouring content or resize a price field.

**Selected:** accent border, optional low-opacity 8-unit blue glow and explicit selected semantics. Do not use a large neon halo or tint the entire screen.

**Focus:** a separate 2-unit cyan outline with a 3-unit offset. It is additive to selected, invalid or other relevant styling, rather than replacing those states. Ensure parent clipping cannot hide it.

Use nested elevations sparingly. A card may contain a clearly recessed field group; it should not contain another identical raised card merely to add decoration. Charts use a flat dark working area, not the card gradient.

## 6. Typography and numerical clarity

**Proposed production family:** Inter, using regular 400, medium 500 and semibold 600. This is a chosen replacement, not an identification of the benchmark's original font.

The preview has an explicit fallback stack because this delivery includes no font files. The Android theme requires the caller to provide a `FontFamily`; it does not silently choose the production font. Before qualification, acquire the approved font artifacts through the application asset pipeline and pin their versions/checksums.

| Role | Size / line height | Weight | Tracking |
|---|---|---|---|
| Main metric | 32 / 40 | 600 | −0.4 |
| Screen title | 28 / 36 | 600 | −0.35 |
| Section title | 20 / 28 | 600 | −0.15 |
| Body | 16 / 24 | 400 | 0 |
| Label | 14 / 20 | 500 | 0 |
| Caption | 12 / 18 | 400 | 0 |
| Navigation | 12 / 16 | 500 | 0 |

Font dimensions above are design-space units. Essential text does not become tiny to reproduce the reduced-size poster. Tabular numerals are required for quantities, balances, prices, timestamps where appropriate, and changing numeric columns.

Never ellipsize a financial amount, its sign, its unit or an order quantity. With increased font size, enlarge or reflow the layout, or provide an explicitly accessible scrollable value region where unavoidable. Do not silently reduce the user's requested font size. The preview is not yet a qualification of all large-text cases.

Use the approved vector wordmark when available. Typing “VAN” in Inter is not a substitute for the distinctive wordmark in the benchmark.

## 7. Geometry and density

The spacing scale is `0, 2, 4, 8, 12, 16, 20, 24, 32, 40, 48, 64`. These values are selected discrete tokens, not an invitation to vary padding independently per page.

Compact page gutters are 16 units. Cards have 16-unit padding and 12-unit internal gaps. Between related cards use 12 units; between distinct sections use 24. Text and icons share alignment anchors rather than being optically repositioned on every screen.

Radii are: small 8; control 12; card 20; large panel 24; pill/circle 999. The screenshot's hardware corner radius is not a control radius.

Main buttons and inputs have a **52-unit minimum height**. Interactive targets have a **48 × 48 minimum**. The visible icon is typically 24 units, with a 1.75-unit round-capped stroke. A compact icon can look small while retaining the larger hit region.

Cards use minimum heights, not fixed clipping boxes. A metric card begins at 176 units; stat tiles at 112; action rows at 88; position cards at 176; intelligence cards at 160. Content, translation and font scaling can increase those heights.

A three-stat row is valid from a 360-unit viewport under the compact fixture. Below that, use two columns with the first item spanning both. Increased font scale can require a further reflow even at larger widths.

## 8. The reusable component family

The complete machine-readable rules are in `component-recipes.json`.

**SurfaceCard and ActionRow.** SurfaceCard establishes the material. ActionRow adds a 48-unit icon tile, title/optional secondary line and a restrained chevron. The whole row is one action where appropriate. Do not create overlapping parent/child click targets.

**MetricCard and StatTile.** The main amount controls hierarchy. A sparkline is supporting evidence, not a competing hero. It may occupy up to 35% of the metric region without colliding with the value. Risk usage is a data field; the style system does not define its risk model.

**IconButton and PrimaryButton.** Both retain appropriate hit targets and visible keyboard focus. A primary action does not need a brightly saturated fill: a raised neutral button can be primary through placement, label and surrounding hierarchy. Busy state prevents duplicate action and retains label space.

**TradeSideButton.** Buy and sell are explicit variants, with visible side and quote. An order's validation, authorization, confirmation and execution are existing product responsibilities. A visual implementation must not weaken them.

**InputField.** Use a persistent label, units and visible error text. A red outline alone is insufficient. Numeric precision comes from the actual instrument and data schema, not from copied screenshot text.

**SegmentedControl.** Use a recessed track and raised selected segment. Selection requires accessible state. Use real tab semantics only when the controls truly select tab panels; otherwise use a correctly labelled selection group.

**PositionCard.** Instrument and side/size come first, followed by signed result, entry-to-current price and labelled SL/TP. Price formatting must be instrument-correct. Do not copy questionable mockup values into application fixtures as financial truth.

**IntelligenceCard.** Instrument, direction, brief evidence, status and timestamp form the hierarchy. “High probability,” “online” and similar claims are data-driven, never decorative defaults. The preview labels its data as illustrative.

**ChartPanel.** Use the inset background, recessed grid, light labels and restrained line colours. Up/down candles have a non-colour distinction: filled versus outlined. Provide an accessible textual summary or equivalent data view in the app. The included chart illustrates styling only; it is not a trading/charting engine.

**Navigation.** The benchmark shows Home, Trade, Work, Memory and More. That observation is not permission to remove, rename or break existing application routes. Reconcile the actual route graph during integration. Active navigation has current-page semantics plus a distinct visual treatment.

**HeroOrb and AgentAvatar.** One approved asset per identity. The orb is a Home identity object, not a default background for every module. Avoid regenerating it per screen. Agent online/busy/offline status comes from runtime evidence. The preview shows a labelled crop from the benchmark for calibration, not a recovered 3D asset.

**ModalSheet.** Retain the same surface, text and control rules. Support focus management and platform dialog semantics. Destructive-action confirmation belongs to product behaviour, not a generic visual template.

## 9. Composition across the app

| Screen family | Composition |
|---|---|
| Home | Greeting/header → optional single hero → real status → prioritized action rows → navigation |
| Trading | Header → portfolio metric → risk/position/order summary → task rows → navigation |
| Instrument terminal | Instrument/timeframe → chart → tools → trade/position/order context → order controls → action |
| Positions | Header → status filter → position cards → new-order action → navigation |
| Intelligence | Header → category selection → evidence cards → analyst presence → navigation |
| Work | Header → active work summary → mission rows → detail on demand |
| Memory | Header/search → grouped records → selected-record detail |
| More/settings | Grouped controls using the same field, row, state and modal recipes |

Do not make a memory page resemble a trading terminal just because both use this style. Shared identity is not identical page composition. Match components to the task while preserving material, geometry, hierarchy and interaction states.

Each task panel should have a clear primary action. Supporting detail can live in progressive disclosure or a detail page. Do not spread all stages of a workflow across the landing screen purely to demonstrate component coverage.

Responsive rules in `layout-rules.json` are deliberately separate from the mobile specimen. Compact is below 600 units, with one main column and bottom navigation; medium is 600–1023, with a rail and up to two content panes; expanded is 1024+, with side navigation, a 12-column planning grid and a maximum 1440-unit content region.

These breakpoints are proposed application composition rules, not claims about the current repository. The standalone HTML page itself is a showcase: at wide viewports it places a mobile specimen next to contract details. It does not implement the final tablet or desktop app shell.

## 10. State and motion contract

State modifiers are independent where necessary: enabled/disabled, busy, selected, validation, connection and focus. A disabled action can still have a visible validation explanation. A focused selected control must retain both meanings.

Default, hover, pressed, selected, focus-visible, disabled, loading, error, empty and offline/stale are required design cases. Hover applies only on devices that support it. Loading must not invent a balance, price, percentage or online state. Stale data needs an explicit freshness indication and applicable product behaviour.

Motion is a designed extension because the benchmark is static. Use 100 ms for press feedback, 160 ms for ordinary state transitions and 240 ms for panel transitions, with easing `cubic-bezier(0.2,0,0,1)`. Avoid continuous ambient animation by default. Honour reduced-motion preferences; a static orb is the baseline. No bounce, pulsing profits or celebratory animations are implied by this contract.

The compiler stores gradient stops as DTCG gradients; direction belongs to the component recipe. Cross-platform shadow rendering needs platform-specific adaptation and baselines, even when the input numbers match.

## 11. Accessibility and verification

The chosen policy is normal-text contrast of at least **4.5:1** and required non-text control/focus contrast of at least **3:1**, subject to the relevant WCAG criteria and exceptions. The 48-unit target policy is stronger than WCAG 2.2's general 24-CSS-pixel minimum and aligns with Android's documented 48-dp guidance. These are different standards/policies and must not be conflated. [S2–S5]

`tooling/verify_tokens.py` checks token references, the token shapes used in this package, fixed opaque sRGB colour pairs and byte-for-byte regeneration of generated outputs. It is not an official DTCG validator and not a full WCAG audit.

The delivery checks **66 specified colour pairs**: 49 ordinary text/semantic pairs, six action/badge pairs and 11 non-text focus/control/chart pairs. All meet the configured threshold. The check does not prove that every future composition, gradient, image overlay or disabled state is accessible. Validate those actual renderings.

The browser smoke test covers **30 cases**: five screen specimens at 320, 360, 390, 430, 768 and 1280 CSS pixels. It checks correct specimen visibility, horizontal document overflow, minimum visible button hit regions and JavaScript errors. It also checks a keyboard focus indicator and the preview's explicit non-submission feedback.

The included screenshots are **inspection evidence, not approved golden baselines**. There has been no automatic image-similarity claim against the poster. Production regression testing needs approved per-platform/component/screen-state baselines under a pinned browser/OS/font/environment. Playwright documents both screenshot comparison and the effects of rendering-environment differences. [S6]

Required before application release: owner visual approval; approved font and brand assets; source-token compliance checks in the actual app; all required interaction states; native compile/instrumentation; TalkBack/screen-reader checks; keyboard/focus checks; large-text/reflow; locale/long-content cases; quote freshness; responsive app layouts; safe areas, keyboard and navigation behaviour; device performance; and reviewed visual baselines.

## 12. Applying the contract without changing functionality

Treat this as a versioned style package, not a reason to rebuild the application. Inventory existing components and route/state combinations. Map them to these semantic roles, add wrappers where needed, and change presentation in a bounded branch. Preserve business behaviour and previously implemented features.

Web uses the generated `web/van.tokens.css` plus `web/van.components.css`. Application code should consume semantic tokens rather than primitive palette entries. Arbitrary raw visual values belong only in explicit adapter/geometry exceptions, not in each screen.

Android uses generated `android/VanTokens.kt`, the supplied `android/VanTheme.kt` bridge and appropriate custom component wrappers. Compose supports extending, replacing or building a custom design system; a colour theme alone does not reproduce this material. [S7] The native files have not been compiled against VAN's actual dependencies. The app must also map any additional Material surface/container roles and remove unintended dynamic-colour or tonal-elevation drift.

For the DDS frontend studio, attach this as an additive named style profile. A design tool or coding agent receives the same active contract, assets and component catalogue. Candidate layout exploration may continue, but a selected style must not be reinterpreted independently by each tool. This package does not change tool routing or assert the current state of DDS.

An integration sequence is: approve reconstruction → pin font/assets → map existing components → build and approve a component/state gallery → migrate one representative screen from each family → review web/native results → migrate the remainder → enforce source and visual checks. Unrelated repository housekeeping and infrastructure changes are outside this style task.

## 13. Locking and change management

`visual-style.lock.json` records the source benchmark hash, version, generated-file hashes, verification status and explicit unresolved qualifications. It labels the contract as proposed; it does not fabricate owner sign-off or a production receipt.

After approval, record the approved baseline identifiers and the font/asset hashes. Token changes must regenerate the CSS/Kotlin outputs and trigger dependent visual checks. Shared recipe changes require review of all affected variants. A passing screenshot update is not approval to replace all baselines automatically.

A new module consumes the existing style contract. A new style direction becomes a new profile or reviewed version; it does not silently overwrite this one.

## 14. Delivery and honest completion boundary

Delivered: benchmark analysis, 115-token source, 16 component recipes, responsive/layout rules, asset requirements, generated web/Android tokens, CSS components, Android theme bridge, five-screen standalone specimen, regeneration and verification scripts, inspection screenshots and machine-readable reports.

Not delivered or claimed: original font identification, recovered 3D assets, owner approval, final vector/icon asset admission, live app integration, compiled native UI, full application accessibility qualification, pixel-identical poster reproduction or deployment.

The result is a **concrete, reusable style contract**. It replaces “make it look like the image” with named values, component recipes, layout rules and inspectable outputs. The remaining qualifications are explicit rather than hidden inside a claim of visual certainty.

## Sources

The benchmark observations come from the owner's supplied image and the accompanying measurement record. All chosen layout, typography, material and motion values are this reconstruction's design decisions.

- **S1:** Design Tokens Community Group, Format and Color Modules 2025.10. Uses structured sRGB colour values, typed dimensions, aliases and composite tokens. This is a Community Group specification, not a W3C Recommendation. https://www.designtokens.org/tr/2025.10/format/ ; https://www.designtokens.org/tr/2025.10/color/
- **S2:** W3C, Understanding WCAG 2.2 — Contrast (Minimum). https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html
- **S3:** W3C, Understanding WCAG 2.2 — Non-text Contrast. https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html
- **S4:** W3C, Understanding WCAG 2.2 — Target Size (Minimum). https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html
- **S5:** Android Developers, Compose accessibility API defaults, minimum touch targets. https://developer.android.com/develop/ui/compose/accessibility/api-defaults
- **S6:** Playwright, Visual comparisons. https://playwright.dev/docs/test-snapshots
- **S7:** Android Developers, Custom design systems in Compose. https://developer.android.com/develop/ui/compose/designsystems/custom

Sources checked on 17 October 2026. The supplied token file uses the structured colour format from S1; it does not use the earlier illustrative hex-string-only colour example or claim an unverified official JSON Schema URL.
