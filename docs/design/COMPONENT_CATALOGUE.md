# VAN Android Component Catalogue

Authority: `docs/design/VAN_PRODUCT_DESIGN_DNA.md`. This is the implementation index for
`com.dial.van.design` — every component's states, data contract and the tokens it draws with.
Nothing here is a fixture: every field a component takes is either live data the caller
fetched, or a caller-supplied callback. Preview/fixture data belongs only in a future
`visual-preview` module, never in these files.

All components read tokens through `LocalVanTokens.current` (provided by
`com.dial.van.visual.VanTheme`), never a raw `Color`/`Dp`/`sp` literal —
`tools/audit/android_design_lint.py` enforces this mechanically for colour and font-size
literals and for stray `Card`/`ElevatedCard` usage.

## Token layer (`com.dial.van.design`)

| File | Provides | Pure (verification-tested)? |
|---|---|---|
| `ScreenState.kt` | `ScreenState<T>` sealed class, `ScreenAction`, `DegradedRow`, `DegradedCatalog`, `ScreenStateMerge.merge` | Yes |
| `DensityTier.kt` | `VanDensity` enum + `.from(widthDp, isOverlay)` | Yes |
| `MotionSpec.kt` | `VanMotionDurations`, `VanCubicEasing`, `VanMotionSpec` (durations, easings, press scale, `resolve(reducedMotion)`) | Yes |
| `StatusSemantics.kt` | `ThesisState`, `AttentionSeverity`, `MissionStatus` enums; `StatusSemantics` (domain state → colour-role **name**, a `String`) | Yes |
| `charts/ChartAxes.kt` | `ChartAxes` — nice-number value ticks, time-axis ticks/labels | Yes |
| `VanTokens.kt` | `VanColorTokens`, `VanTypeTokens`, `VanSpace`, `VanRadius`, `VanElevation`, `VanMotion` (Compose wrapper), `VanTokens`, `LocalVanTokens` | No — Compose types; cannot compile without AGP |

`VanColorTokens.forStatusRole(role: String)` is the one place a `StatusSemantics` role name
becomes a paintable `Color`; an unrecognised role name reads as `statusDisabled` rather than
throwing.

`com.dial.van.visual.VanPalette` carries the additive fields these tokens are built from:
`VanScheme.textTertiary` and `VanScheme.statusRoles` (keyed by the same role names as
`StatusSemantics.ALL_ROLES`), each contrast-checked at AA (4.5:1) against both `background`
and `surface`, for both the dark and light scheme, in
`android/verification/.../visual/VanDesignRolesTest.kt`.

`com.dial.van.visual.VanTheme(dark, isOverlay, reducedMotion) { content }` assembles one
`VanTokens` per composition and provides it through `LocalVanTokens`. `isOverlay` pins
`VanDensity` to `Compact` (DNA §1); `reducedMotion` collapses every `VanMotion` duration to
zero (DNA §2) — the same boolean the caller already computes for
`VanEffectBudget`/`VanEffectConditions.reducedMotion`.

---

## Components (`com.dial.van.design.components`)

### `VanScreen<T>`
The state-wrapper every destination renders through (DNA §5's seven states, exhaustively).

- **States**: `Loading` → default skeleton (or caller's `skeleton` slot) · `Content` → calls
  `content(data)` · `Empty` → `EmptyState` · `Error` → `VanErrorState` (+ retry) · `Degraded` →
  `VanDegradedBanner` then `content(data)` if `data` survived, banner alone otherwise ·
  `Offline` → `VanOfflineState` (queued-count aware) · `Stale` → `LiveBadge` then
  `content(content)`.
- **Data contract**: `state: ScreenState<T>` — built by the caller's reducer, typically via
  `ScreenStateMerge.merge(...)`, from the screen's own `@DataSource`-annotated fetch. `onRetry`,
  `onEmptyAction` are caller callbacks; `content: @Composable (T) -> Unit` never receives a
  nullable/placeholder `T`.
- **Tokens**: `space.space2/space3`, all via child components.

### `VanScreenSkeleton` / `SkeletonBlock`
LOADING geometry. `SkeletonBlock(modifier, cornerRadius?, reducedMotionOverride?)` draws an
animated-gradient shimmer sized to whatever the caller gives it — a `MetricTile`-sized block, a
row-height block — so layout does not jump when data arrives. At `tokens.motion.reducedMotion`
(or the override), the shimmer freezes at a static position rather than pulsing.

- **Tokens**: `color.surface1/surface2`, `radius.m` (default), `motion.reducedMotion`.

### `VanPanel`
The one container every screen except the embodiment shell/overlay uses instead of a bare
Material `Card`/`ElevatedCard` or `VanGlassSurface` (DNA §1: "Panels are acrylic... No glass on
cards").

- **States**: none — visual container only; `dense` (Boolean) switches
  `space.panelPadding`/`space.densePanelPadding`.
- **Data contract**: `header: (@Composable () -> Unit)?`, `content`.
- **Tokens**: `color.surfaceAcrylic`, `color.textPrimary`, `color.lineHair`, `radius.m`,
  `radius.hairline`, `elevation.panel`, `space.panelPaddingFor(dense)`.

### `StatusChip`
A short label + coloured dot, coloured by a `StatusSemantics` role **name** (never a raw
`Color`), so a chip and the aura for the same domain state always agree.

- **Data contract**: `label: String`, `role: String` (one of `StatusSemantics.ALL_ROLES`, or any
  string — unknown roles resolve to `statusDisabled`), `filled: Boolean` (solid fill vs. 16%
  tint).
- **Tokens**: `color.forStatusRole(role)`, `color.textInverse` (on `filled`), `radius.s`,
  `type.label`, `space.space1/space3`.

### `LiveBadge`
DNA §3: `LIVE` / `STALE hh:mm` / `OFFLINE` / `EXTERNAL`, the one place `ScreenState.Stale`'s
age becomes an `"hh:mm"` string.

- **States**: `LiveBadgeState.Live | Stale(ageMs) | Offline | External`.
- **Tokens**: delegates to `StatusChip` (`engaged`/`eventRisk`/`disabled`/`cognition` roles).

### `MetricTile`
DNA §3: value, delta, sparkline, tap → detail.

- **Data contract**: `label`, `value` (pre-formatted, tabular via `type.dataLarge`), `delta:
  String?`, `deltaRole: String?` (a `StatusSemantics` role — **not** derived from the sign of
  the delta; DNA §2's "never raw green/red for P&L" rule), `sparkline: List<Float>?`,
  `onClick: (() -> Unit)?`.
- **Tokens**: `type.label/dataLarge/data`, `color.textTertiary/textPrimary/textSecondary`,
  `motion.durations.quickMs` (value/sparkline animate at `quick`, DNA §2).

### `Sparkline`
`MetricTile`'s trend line — no axes, no interaction. `values.size <= 1` draws nothing (reserves
the space; no degenerate flat line).

- **Data contract**: `values: List<Float>`, `lineColor: Color?` (defaults to
  `color.accentCyanSoft`).

### `HeatBar`
DNA §3: portfolio heat / budget. Colour escalates by `fraction`: `< 0.60` → `favourable`,
`0.60–0.85` → `eventRisk`, `≥ 0.85` → `critical`.

- **Data contract**: `label`, `fraction: Float` (not clamped in the semantics/label, clamped
  only for the drawn width), `detail: String?`.
- **Tokens**: `color.forStatusRole(...)`, `color.surface2`, `radius.s`,
  `motion.durations.quickMs`.

### `TimelineRail`
DNA §3: mission and trade events with actor + severity.

- **Data contract**: `events: List<TimelineEvent>` (`id, title, actor, timeLabel,
  severityRole, detail?`), drawn in the order given.
- **Tokens**: `color.forStatusRole(severityRole)`, `color.lineHair`, `type.body/label`.

### `EvidenceRow`
DNA §3: source, trust tier, time, open.

- **Data contract**: `source`, `trustTier: String` (shown as text via `StatusChip`, never
  colour alone), `trustRole: String`, `timeLabel`, `onOpen: (() -> Unit)?`.
- **Tokens**: delegates to `StatusChip`; `type.body/label`.

### `FindingCard`
DNA §3: severity, actions. The Attention screen's non-swipeable cousin of `AttentionItem`, for
Work/Memory surfaces that list findings inline.

- **Data contract**: `title`, `severityRole: String`, `detail: String?`, `actions:
  List<FindingAction>` (`label, onClick, emphasized`).
- **Tokens**: `VanPanel`, `StatusChip`, `type.headline/body/label`.

### `ApprovalSheet`
DNA §3: biometric prompt inline, action digest. A `ModalBottomSheet` hosting a
caller-supplied approval action — **does not call `BiometricGate` itself**; that
authority-sensitive call belongs to the owning screen, which passes it in as `onApprove`.

- **Data contract**: `title`, `actionDigest: String` (shown above the control, never collapsed),
  `onApprove: suspend () -> Result<Unit>`, `onDismiss: () -> Unit`, `onApproved: (() ->
  Unit)?`. In-flight state (spinner, disabled buttons) and an on-failure error line are owned
  internally.
- **Tokens**: `color.surfaceAcrylic`, `color.accentCyan`/`textInverse`,
  `color.forStatusRole(critical)`, `type.title/body/label/headline`.
- **API note**: `ModalBottomSheet`/`rememberModalBottomSheetState` are
  `@ExperimentalMaterial3Api` in Compose BOM 2024.06.00 (material3 1.2.1); opted in at this one
  call site.

### `AttentionItem`
DNA §3/§4: severity rail, swipe: ack / snooze / open.

- **States**: severity rail colour + `StatusChip` text from `AttentionSeverity` →
  `StatusSemantics.forAttentionSeverity`. Swipe start→end fires `onAck`; swipe end→start fires
  `onSnooze`; tap (when `onOpen` set, via `VanPressable`) fires `onOpen`. The item always
  settles back after a swipe fires its callback — removal from a list is the caller's decision,
  not this component's.
- **Data contract**: `title`, `severity: AttentionSeverity`, `detail: String?`, `timeLabel:
  String?`, `onAck`, `onSnooze`, `onOpen` (each optional; a `null` handler disables that swipe
  direction).
- **Tokens**: `color.forStatusRole(role)`, `VanPanel` (dense), `StatusChip`.
- **API note**: `SwipeToDismissBox`/`rememberSwipeToDismissBoxState` are
  `@ExperimentalMaterial3Api` in material3 1.2.1; opted in at this one call site.

### `ThesisCard`
DNA §3: state, invalidation, confirmation. Takes `ThesisState` (this package's own enum, not a
`trading/`-owned type) so `design/` does not depend on `trading/`; the trading screens that
adopt this map their richer thesis model onto it.

- **Data contract**: `title`, `state: ThesisState`, `thesisSummary: String?`, `confirmation:
  String?`, `invalidation: String?`.
- **Tokens**: `StatusSemantics.forThesisState(state)`, `VanPanel`, `StatusChip`.

### `PositionCard`
DNA §3: direction, exposure, R, protection, thesis state. `rMultipleLabel`'s colour comes from
`thesisState`, never from the sign of the R (DNA §2).

- **Data contract**: `symbol`, `direction: PositionDirection` (`LONG`/`SHORT`, this package's
  own enum), `exposureLabel`, `rMultipleLabel` (both pre-formatted by the caller —
  `trading/TradingFormat` owns number formatting), `thesisState: ThesisState`,
  `protectionLabel: String?`, `onClick: (() -> Unit)?`.
- **Tokens**: `StatusSemantics.forThesisState`, `VanPanel`, `StatusChip`, `type.headline/data/label`.

### `SectionHeader`
Destination/panel-group heading with an optional detail line and trailing slot (a `LiveBadge`,
a count, an action).

- **Data contract**: `title`, `detail: String?`, `trailing: (@Composable () -> Unit)?`.
- **Tokens**: `type.title/body`, `color.textPrimary/textSecondary`, `space.space1/space2`.

### `EmptyState`
DNA §3/§5: VAN-voiced sentence, one action.

- **Data contract**: `sentence: String`, `action: ScreenAction?`, `onAction: (() -> Unit)?` —
  the action renders only when both are non-null.
- **Tokens**: `type.body/label`, `color.textSecondary/accentCyan`.

### `VanErrorState` / `VanOfflineState` / `VanDegradedBanner`
`VanScreen`'s ERROR/OFFLINE/DEGRADED renderers, usable standalone too.

- `VanErrorState(message, canRetry, onRetry)` — retry button shown only when both `canRetry`
  and `onRetry` are set.
- `VanOfflineState(queuedCount)` — pluralises "action is/are queued" itself.
- `VanDegradedBanner(rows: List<DegradedRow>)` — one `StatusChip("DEGRADED", eventRisk)` plus
  every row's owner-facing sentence (`DegradedCatalog.sentenceFor`); renders nothing for an
  empty list.

### `VanPressable`
The one press affordance (DNA §2: "Press scale 0.97 at `instant`") every tappable surface goes
through — not a component with its own visual identity, a wrapper. Ripple is suppressed
(`indication = null`): the scale is the feedback. Enforces the ≥48dp touch target via
`Modifier.sizeIn`.

- **Data contract**: `onClick`, `enabled`, `hapticOnPress: Boolean` (DNA §2 haptics: confirm on
  approval, tick on dock/snap — never on scroll), `role: Role`, `contentDescription: String?`,
  `content: @Composable BoxScope.() -> Unit`.
- **Tokens**: `motion.pressScale`, `motion.durations.instantMs`, `motion.standardEasing`,
  `radius.m`.

---

## `design/charts/ChartAxes.kt`

Not a component — pure axis arithmetic the trading worker's `CandlestickChart` draws with.

- `niceNumber(value, round)` — Heckbert's 1/2/5×10ⁿ rounding.
- `ticks(min, max, targetCount)` — evenly spaced "nice" value ticks spanning a range.
- `valueLabel(value, step)` — decimal precision derived from the step.
- `timeTicks(minEpochMs, maxEpochMs, targetCount)` — ticks snapped to a human boundary
  (second/minute/hour/day ladder) appropriate to the span.
- `timeLabel(epochMs, spanMs, zone)` — granularity (time-only / day+time / month+day /
  month+year) chosen from the *whole chart's* span, so every label on one axis matches.

All five are pure and tested in `android/verification/.../design/charts/ChartAxesTest.kt`.

---

## Lint coverage (`tools/audit/android_design_lint.py`)

| Rule | Scope | What it means for a screen |
|---|---|---|
| `raw_color_literal` | outside `design/`, `visual/` | Use `tokens.color.*`, never `Color(0x...)`. |
| `font_size_under_12sp` | everywhere, no exceptions | DNA's 12sp floor — even inside `design/`. |
| `font_size_literal_outside_design` | outside `design/` | Use `tokens.type.*`, never a bare `fontSize = N.sp`. |
| `material_card_outside_design` | outside `design/` | Use `VanPanel`, never `Card(`/`ElevatedCard(`. |

Ratcheted against `tools/audit/android_design_lint_baseline.json` (464 violations across 61
file/rule pairs at the time this catalogue was written — every one of them in a screen package
this worker does not own and has not touched). See that file's own module docstring and
`tests/contracts/test_android_design_lint.py` for the exact ratchet rule.
