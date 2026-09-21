# VAN Product Design DNA — Rev 1 (Fable, 2026-09-21)

Authority: this document owns the Android visual language, information architecture, motion hierarchy and screen-state contract. Code implements it through `com.dial.van.design.*` tokens and components. Constants outside the token layer are a lint failure (`tools/audit/android_design_lint.py`).

Principle: **one VAN at the experience layer, modular execution underneath.** Every surface is VAN presenting something, never a module presenting itself.

## 1. Surfaces and their grammar

| Surface | Grammar | Glass | Density |
|---|---|---|---|
| Floating VAN (overlay, compact + expanded) | spatial, embodied, conversational cards | yes, restrained, one shell | low |
| Home | calm command-centre: embodiment + "now" | shell only behind the embodiment | medium |
| Attention / Decisions | triage: priority rail, swipe actions | no | medium |
| Command Centre (Work) | live control: missions, agents, activity | no (acrylic panels) | high |
| Trading | dense technical UI, precise status semantics, charts | no | very high |
| Projects / Memory | editorial, structured, provenance-aware | no | medium |
| Settings / Devices / Connections | crisp, predictable, no decoration | no | medium |

Glass policy: at most one glass shell per screen (the embodiment shell). Panels are acrylic (opaque surface tier + 1px hairline + soft shadow). No glass on cards. No blur behind text under 16sp.

## 2. Tokens (`com.dial.van.design.VanTokens`)

Colour roles (dark scheme primary; light scheme derived by `VanPalette`):
- `bg.canvas` #0B1116 · `bg.atmosphere` radial cyan 6% over canvas · `surface.0` #111820 · `surface.1` #16202A · `surface.2` #1C2833 · `surface.acrylic` surface.1 @ 92% + hairline `line.hair` #FFFFFF 8%
- `text.primary` #F2F7FA · `text.secondary` #BCD1D8 · `text.tertiary` #7F97A2 · `text.inverse` #0B1116
- `accent.cyan` #00E5FF (VAN) · `accent.cyanSoft` #4DD0E1 · `accent.blueWhite` #CFEFFF (cognition)
- Status semantics (shared with the aura, `VanStatusPalette`): `status.monitor` cyanSoft · `status.engaged` cyan · `status.cognition` blueWhite · `status.hypothesis` violet #B388FF · `status.eventRisk` amber #FFB300 · `status.favourable` greenCyan #64FFDA · `status.deteriorating` amberRed #FF6E40 · `status.critical` red #FF1744 · `status.disabled` silverBlue #78909C
- Never use raw green/red for P&L emotion; P&L uses `text.primary` with a directional glyph and `status.favourable`/`status.deteriorating` only when the thesis state says so.

Typography (Inter-compatible system sans; tabular numerals for data):
- `display` 28/34 semibold · `title` 20/26 semibold · `headline` 16/22 semibold · `body` 14/20 regular · `label` 12/16 medium · `data` 13/16 medium tabular · `dataLarge` 22/26 semibold tabular
- Minimum text size 12sp anywhere. Captions are `label`, never smaller.

Spacing: 4-pt grid; `space.1`=4 `space.2`=8 `space.3`=12 `space.4`=16 `space.5`=24 `space.6`=32. Page gutter 16. Panel padding 16. Dense (trading) panel padding 12.

Radius: `radius.s`=8 (chips) · `radius.m`=14 (panels) · `radius.l`=22 (embodiment shell, sheets). Hairline 1dp.

Depth: `elevation.flat` 0 · `elevation.panel` 2 · `elevation.sheet` 8 · `elevation.overlay` 16. Shadows are soft (blur 24, y 8, 24% black).

Motion (`VanMotion`): `instant` 80ms · `quick` 160ms · `standard` 240ms · `expressive` 360ms · easing `standard` cubic(0.2,0,0,1), `enter` cubic(0,0,0.2,1), `exit` cubic(0.4,0,1,1). Press scale 0.97 at `instant`. Shared-element for card→detail at `standard`. Data updates animate value + sparkline at `quick`. Reduced motion: all durations 0, state changes still communicated by colour/shape.

Density tiers: `Compact` (overlay expanded card), `Regular` (phone portrait), `Wide` (landscape / ≥600dp: two-pane). Layouts recompose, not scale.

Haptics: `confirm` on approval completion, `tick` on dock/snap, `warning` on URGENT arrival. Never on scroll.

## 3. Component catalogue (`com.dial.van.design.components`)

`VanScreen` (state wrapper: LOADING skeleton / CONTENT / EMPTY / ERROR / DEGRADED / OFFLINE / STALE with `LiveBadge`) · `VanPanel` (acrylic panel with header slot) · `StatusChip` · `LiveBadge` (LIVE / STALE hh:mm / OFFLINE / EXTERNAL) · `MetricTile` (value, delta, sparkline, tap → detail) · `Sparkline` · `EquityCurve` · `HeatBar` (portfolio heat / budget) · `TimelineRail` (mission and trade events with actor + severity) · `EvidenceRow` (source, trust tier, time, open) · `FindingCard` (severity, actions) · `ApprovalSheet` (biometric prompt inline, action digest) · `AttentionItem` (severity rail, swipe: ack / snooze / open) · `ThesisCard` (state, invalidation, confirmation) · `PositionCard` (direction, exposure, R, protection, thesis state) · `CandlestickChart` (custom Canvas; gestures: pan/zoom/inspect crosshair) · `SectionHeader` · `EmptyState` (VAN-voiced sentence, one action) · `SkeletonBlock`.

Every component takes tokens only. Every component has a preview in `visual-preview` for each of its states.

## 4. Information architecture

Destinations (adaptive nav: bottom rail with 5 primaries on Regular, side rail on Wide; the rest under "More" and deep links):
1. **Home** (`/home`) — embodiment, VAN's current state sentence, attention now (top 3), active work, significant trade state, upcoming, recent change.
2. **Attention** (`/attention`) — triage list INFO/FOLLOW_UP/BLOCKER/URGENT; decisions; approvals.
3. **Work** (`/work`, the Command Centre) — command bar (text + voice), missions (running / waiting / done), delegated agents, activity feed, browser & automation tasks as children.
4. **Trading** (`/trading`) — overview → positions → position detail (`/trading/positions/{id}`) → potential → history/intelligence → accounts → strategies.
5. **Memory** (`/memory`) — facts, decisions, assumptions, preferences, unresolved threads, provenance; add/correct/forget.
6. Projects (`/projects`, `/projects/{id}`) — health, phase, current work, blockers, decisions, next actions.
7. Connected (`/connected`) — Google planes, Hermes, knowledge providers, readiness.
8. Devices & Settings (`/settings`) — pairing, permissions, voice, notifications policy, quiet hours, character/renderer, diagnostics.

Removed: the flat 17-module grid; Trading as a separate activity (it becomes a destination inside one NavHost; `TradingCommandCentreActivity` forwards to the route for old intents).

## 5. Screen-state contract

Every destination implements all of: LOADING (skeleton matching final geometry), CONTENT, EMPTY, ERROR (retry), DEGRADED (which subsystem, what still works — from `/health.degraded[]`), OFFLINE (queued work visible), STALE (`LiveBadge` with age). Live data only: a panel's data source is declared in code (`@DataSource("GET /v1/trading/positions")` annotation or KDoc) and there is no fixture path in production. Preview fixtures live only in `visual-preview`.

## 6. Embodiment binding

`VanDurableState` and `VanFiniteAction` producers (Android):
- ATTENTIVE: overlay tap / command bar focus · LISTENING/SPEAKING: voice · THINKING: dispatch started · DELEGATING: mission RUNNING with Hermes run id · SEARCHING: research/browser task running · WORKING: local execution / automation · WAITING: mission WAITING_EXTERNAL · WAITING_FOR_OWNER: approval or decision pending · URGENT: attention URGENT_INTERRUPT arrival · SUCCESS: VERIFIED_SUCCESS · WARNING: UNVERIFIABLE / degraded partial · ERROR: FAILED · DEGRADED: gateway degraded · OFFLINE: no connectivity · CONNECTING: session handshake · SLEEPING: quiet hours with no open attention · IDLE otherwise.
- HELLO_WAVE: first session open of the day · ACK_NOD: command accepted · CONFIRM: VERIFIED_SUCCESS · CAUTION: WAITING_FOR_OWNER / URGENT · CELEBRATE: trade closed in the GOOD_DECISION_GOOD_OUTCOME quadrant (never on P&L alone) · SHRUG: UNVERIFIABLE · PRESENT_CARD: result summary ready · POINT_*: directing to a card in the expanded overlay · OPEN_PANEL/CLOSE_PANEL: overlay expand/collapse.

Aura semantics follow `VanStatusPalette` and `VanAuraSpec`; the trade semantic layer (`VanTradeSemantic`) maps thesis state → favourable / deteriorating / eventRisk / critical, never P&L.

## 7. Verification gates (V1–V8)

V1 structure (nav + hierarchy tests) · V2 DNA (lint: no inline hex, no <12sp, tokens only) · V3 interaction (JVM tests on reducers/gesture policies) · V4 motion (state→motion map tests; reduced-motion path) · V5 live data (every panel declares a source; contract test greps for fixture leakage) · V6 resilience (each screen renders all seven states in visual-preview) · V7 accessibility/performance (contrast table executed in `android/verification`; frame budget tokens) · V8 coherence (evidence renders reviewed against the anti-generic checklist).
