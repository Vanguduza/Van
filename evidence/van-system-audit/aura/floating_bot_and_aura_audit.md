# VAN Floating Bot + Aura — Read-only Evidence Audit

Repo: /home/user/Van · Branch: claude/van-system-audit-ysgtcd · HEAD: dff38a0
Auditor mode: READ-ONLY. No repository files modified.
Date: 2026-09-18

Working tree at audit start: clean except untracked `evidence/` (not authored by this audit).

---

## 0. Inventory (line counts, `wc -l`)

```
  126 android/app/src/main/java/com/dial/van/visual/RiveContract.kt
   82 .../visual/VanArtPose.kt
  252 .../visual/VanAura.kt
  330 .../visual/VanAuraSpec.kt
   91 .../visual/VanBodyExclusionProfile.kt
  393 .../visual/VanCanvasFallback.kt
  113 .../visual/VanCharacterMotion.kt
  181 .../visual/VanDrawOp.kt
   78 .../visual/VanEffectBudget.kt
  515 .../visual/VanFieldGeometry.kt
  185 .../visual/VanGlassSurface.kt
  177 .../visual/VanGlassTokens.kt
  189 .../visual/VanLiveVisualState.kt
   58 .../visual/VanLivingFieldPreviews.kt
  201 .../visual/VanPresence.kt
  153 .../visual/VanPresenceFrame.kt
   74 .../visual/VanRiveAvatar.kt
  875 .../visual/VanScene.kt
   30 .../visual/VanStateArt.kt
  111 .../visual/VanStatusPalette.kt
   84 .../visual/VanVisualRuntime.kt
   98 .../visual/VanWindFieldMotion.kt
 1031 android/app/src/main/java/com/dial/van/overlay/FloatingOverlayService.kt
   20 .../overlay/OverlayRecoveryReceiver.kt
   99 .../overlay/OverlayStateStore.kt
   48 .../overlay/OverlayTheme.kt
  165 .../overlay/VanMinimizedAvatar.kt
   47 .../overlay/VanOverlayChrome.kt
  138 .../overlay/VanOverlayInteraction.kt
 5944 total
```

Unit tests present: RiveContractTest, VanAuraEnvelopeTest, VanCharacterMotionTest,
VanCharacterOpacityTest, VanEffectPolicyTest, VanFieldGeometryTest, VanFieldRev3Test,
VanPresenceFrameTest, VanPresenceTest, VanSceneIdentityTest, VanVisualRuntimeTest,
VanWindFieldMotionTest (12 files, android/app/src/test/java/com/dial/van/visual/).

visual-preview module (pure JVM/AWT): AwtVanRenderer.kt, GlassPainter.kt, OwnerArt.kt,
OwnerArtExtractor.kt, OwnerArtMain.kt, VanCommandCentreEvidence.kt, VanEvidenceMatrix.kt,
VanPreviewMain.kt, VanPreviewSheets.kt + 2 test files.

---

## 1. AURA IMPLEMENTATION

### 1.1 Drawing primitives — Compose Canvas ONLY. No AGSL, no blur, no RenderEffect.

`VanAura.kt:26-43` — `VanAuraLayer` is a plain `androidx.compose.foundation.Canvas`.
`VanAura.kt:48-145` — `DrawScope.drawVanAura` composes the whole field from three primitive
families only:
  * `drawPath(..., style = Stroke(...))` for field streams (`VanAura.kt:79-96`)
  * `drawCircle` for ion dots (`VanAura.kt:116-125`)
  * `Brush.radialGradient` circles for Zone A haze (`VanAura.kt:208-225`)

Verified absence of GPU shader / blur usage:

```
$ grep -rn "RuntimeShader|AGSL|RenderEffect|BlurEffect|Modifier\.blur|MaskFilter|asFrameworkPaint" \
    --include=*.kt android/app/src/main/java/com/dial/van/
  -> NO MATCHES (rc=1)
$ grep -rn "noise|simplex|perlin" --include=*.kt android/app/src/main/java/com/dial/van/
  -> only voice/NoiseSuppressor (audio). NO procedural noise anywhere in visual/.
```

**VERDICT 1.1:** The aura is *pure Compose Canvas vector drawing*: strokes, circles and one radial
gradient. There is **no AGSL/RuntimeShader**, **no `Modifier.blur`/`RenderEffect`**, **no real
Gaussian blur**, and **no procedural noise (Perlin/simplex/hash-lattice)** anywhere in the shipping
visual package. "Glow" is faked as a second, wider, lower-alpha stroke of the same path
(`VanAura.kt:79-96`, `VanAura.kt:166-180`) and "bloom" on dots as a 2.8x radius circle at alpha*0.16
(`VanAura.kt:116-120`). This is a legitimate cheap technique, but it is *not* a blurred/volumetric
field — edges are hard-stroked polylines.

Deterministic pseudo-randomness is a sine-hash (`VanFieldGeometry.kt:504-507`):
`seed01(index, salt) = frac(|sin(index*12.9898 + salt*78.233) * 43758.5453|)` — the classic GLSL
hash, used *per-element*, not as a spatial noise field. Motion irregularity therefore comes from
summed sinusoids, not turbulence.

### 1.2 Is it a live, independently animated FIELD or a body-hugging ring?

Structurally it is genuinely a **detached field**, not a border/ring. Evidence:

* **Zone A (identity haze)** — `VanAura.kt:187-245`. Two *displaced, off-centre* radial-gradient
  blobs at `center.x ± bodyEdge*0.31/0.34` with per-frame drift (`VanAura.kt:196-206`), alpha
  clamped 0.035–0.085 (`VanAura.kt:194`). The doc comment at `VanAura.kt:183-186` explicitly states
  it "must not form a body outline". Correct: it is deliberately NOT a halo.
* **Zone B (activity filaments)** — `VanFieldGeometry.kt:81-116`. 0–5 long advecting S-curve
  ribbons, each 35 sampled points (`VanFieldGeometry.kt:417`), laid out in a *wind frame*
  (along/across basis, `VanFieldGeometry.kt:490-500`) rather than polar-around-the-body. They are
  translated streams, so they read as wind, not as a ring.
* **Zone C (semantic envelope)** — `VanFieldGeometry.kt:132-214`. Sparse arc *fragments*
  (`VanAuraEnvelopeSegment(startDeg, sweepDeg, node)`), max 4 segments
  (`VanAuraSpec.kt:68`), combined sweep capped at 180° (`VanAuraSpec.kt:67`). Each fragment gets its
  own local wind direction rotated by `wrapPi(startDeg)*0.48` (`VanFieldGeometry.kt:144-146`).
* **Electrical branches** — `VanFieldGeometry.kt:320-398`. 1–4 forked polylines with a *finite
  lifecycle*: a branch is skipped entirely outside its active window (`VanFieldGeometry.kt:342-344`)
  and its alpha is a `sin()` life envelope (`VanFieldGeometry.kt:345-350`). Comment at
  `VanFieldGeometry.kt:340-341` states this is precisely to avoid "a permanently electrified
  outline".
* **Ion particles** — `VanFieldGeometry.kt:266-318`. 3–12 advected dots with a
  `sin(PI*progress)` lifetime fade (`VanFieldGeometry.kt:307`).

Motion primitives actually present (`VanFieldGeometry.kt:447-488` `flowPoint`):
| Documented quality | Present? | Evidence |
|---|---|---|
| Wave motion | YES — 3 summed harmonics 1.35/2.80/5.20 cycles | `VanFieldGeometry.kt:467-471` |
| Phase evolution / advection | YES — phase term in each harmonic + longitudinal advection | `:467-469`, `:475-479` |
| Turbulence / curl | PARTIAL — one extra sinusoid scaled by `turbulence` | `:472-473` |
| Displacement of perimeter | YES — `deformation`/`fieldAsymmetry` feed amplitude & wind angle | `VanWindFieldMotion.kt:57`, `:66-69` |
| Irregular (non-circular) perimeter | YES — streams are open ribbons in a wind basis, never a closed ellipse | `VanFieldGeometry.kt:400-445` |
| Layered glow | PARTIAL/FAKE — 2-pass stroke (glow stroke + core stroke), 3-pass for electrical (glow/white core/colour) | `VanAura.kt:79-96`, `:166-180` |
| Depth | WEAK — only alpha/width tiering by `tier = 0.40 + (index/2)*0.24` | `VanFieldGeometry.kt:85` |
| Translucency | YES — every alpha ≤ ~0.22 for glow, ≤0.92 core | `VanAura.kt:81`, `:178` |
| Breathing | YES — ±1.8–5.3% radial, second harmonic | `VanWindFieldMotion.kt:52-55` |
| Electrical activity | YES — forked branches with birth/death | `VanFieldGeometry.kt:320-398` |
| **True volumetric/noise turbulence** | **NO** — purely sums of sines, no noise field | (see 1.1) |
| **Real blur / bloom** | **NO** — faked by wide low-alpha strokes | (see 1.1) |

So: **not a static border, not a body-hugging ring** — but also **not a shader field**. It is a
deterministic, sinusoid-driven *vector particle/ribbon system*.

### 1.3 Body/aura separation — actual dp numbers vs doc targets

Everything in the exclusion profile is expressed as a **fraction of `bodyEdge`**, never in dp.
`VanBodyExclusionProfile.kt:156-184`:
```
gap       = bodyEdge * 0.055 * extraGapScale      (extraGapScale clamped 0.65..1.5)   :162
head      Ellipse rx = bodyEdge*0.255 + gap, ry = bodyEdge*0.300 + gap                :163-168
torso     Capsule radius = bodyEdge*0.295 + gap                                        :169-175
shoulders Ellipse rx = bodyEdge*0.355 + gap, ry = bodyEdge*0.155 + gap*0.7             :177-182
```
`bodyEdge = minEdge * characterScale.coerceIn(0.40f, 1f)` (`VanAura.kt:58`).

**There is no dp anywhere in the exclusion maths.** To compare with the doc's 10–14 / 16–28 /
30–48 dp three-zone targets you must pick a container size. The default gap is
`0.055 * bodyEdge`:
* a 96 dp minimized bubble at characterScale 1.0 -> gap = **5.3 dp** (below the 10–14 dp Zone A
  target)
* a 200 dp compact card -> gap = **11 dp** (inside the Zone A band)
* a 320 dp expanded panel -> gap = **17.6 dp**

i.e. the separation is **scale-relative, so it only lands inside the documented dp bands at one
particular size**. The docs' absolute dp targets are **not enforced anywhere in code** — grep:
```
$ grep -n "\.dp" VanBodyExclusionProfile.kt VanFieldGeometry.kt VanAura.kt
  -> NO MATCHES.    (only VanSceneIdentityTest.kt:89 mentions "76dp" in a comment)
```

### 1.4 Animation loop and time source

There is **no `withFrameNanos` anywhere in the app**. The only drivers are Compose
`rememberInfiniteTransition` + `infiniteRepeatable(tween(..., LinearEasing), RepeatMode.Restart)`:

* `VanCanvasFallback.kt:250-279` — `vanIdlePhase(state, reducedMotion)`. Returns a constant
  `NEUTRAL_PHASE` when reduced motion (`:251`); otherwise a 0→1 ramp whose **period depends on the
  state**: 2000 ms for LISTENING/WORKING/SEARCHING/CONNECTING (`:252-257`), 2800 ms for
  URGENT/WARNING/ERROR/WAITING_FOR_OWNER (`:258-262`), 6000 ms for SLEEPING/OFFLINE (`:263-265`),
  4200 ms otherwise (`:266`).
* `VanMinimizedAvatar.kt:36-45` — a separate 5200 ms linear phase for the minimized portrait only.

Consequences (real, not theoretical):
* **Only one global phase drives the entire aura.** `VanEmbodiment` computes `phase` once
  (`VanCanvasFallback.kt:134`) and hands the same scalar to Zone A, Zone B, Zone C, particles and
  electrical branches. There is no per-layer clock, no per-particle lifetime clock and no
  wall-clock. All "independent" motion is a deterministic function of that single 0..1 ramp.
* **The phase period changes when the state changes** (`:252-266`). Because
  `rememberInfiniteTransition`'s `animationSpec` is recreated with a new duration, the ramp
  restarts — a *discontinuity in phase velocity*, and in practice the phase jumps. `VanWindFieldMotion`
  is C0-continuous in `phase` at 0/1 (documented at `VanWindFieldMotion.kt:9-12`, tested), so there
  is no seam at wrap, but there **is** an untreated seam at *state change* because the whole
  transition object is replaced. No cross-fade or phase-carry-over exists for this.
* `RepeatMode.Restart` + the deliberate phase-0 == phase-1 identity means the wrap seam is handled.
* **The field is not time-based, it is phase-based**, so the aura's apparent speed is coupled to the
  state's chosen tween duration, not to a physical wind speed.

### 1.5 Effect budget, reduced motion, low power

`VanEffectBudget.kt:201-234` — 5-rung ladder FULL / REDUCED / REDUCED_MOTION / LOW / STATIC with
per-rung `filamentScale`, `bloomScale`, `allowRefraction`, `allowLiveBlur`, `allowMotion`,
`glowScale`. `keepsStateIndicators` is hardcoded `true` (`:233`) — a declaration, not an enforcement.

`VanEffectPolicy.resolve` (`VanEffectBudget.kt:258-266`) priority: reducedMotion > thermal-severe >
batterySaver > thermal-moderate > frameBudgetMissed > !crossWindowBlur > FULL.

Wiring to real device signals: `VanCanvasFallback.kt:156-182` `rememberVanEffectBudget()` reads
`PowerManager.isPowerSaveMode`, `currentThermalStatus` (API 29+), `WindowManager.isCrossWindowBlurEnabled`
(API 31+) and a reduced-motion helper. **This is genuinely wired.** Two caveats:
* It is inside `remember(context, reducedMotion)` (`:159`) — thermal status and power-save mode are
  sampled **once per composition** and never re-polled. A device that heats up mid-session keeps the
  FULL budget until something else recomposes.
* `VanEffectConditions.frameBudgetMissed` (`VanEffectBudget.kt:247`) is declared but **never set by
  any production caller** — there is no frame-time measurement anywhere. Grep confirms no
  `Choreographer`, no `JankStats`, no frame-time sampling.

`allowLiveBlur`/`allowRefraction` exist as flags but, per 1.1, **no blur or refraction is ever
drawn**, so surrendering them is a no-op in the aura path (they matter only for glass chrome —
see VanGlassSurface).

---

## 2. SEMANTIC STATE MODEL

### 2.1 The enums

`RiveContract.kt:7-31` — **`VanDurableState`, 18 members** (the "18 state topologies" of the docs):
```
OFFLINE(0) CONNECTING(1) IDLE(2) ATTENTIVE(3) LISTENING(4) THINKING(5) SEARCHING(6)
WORKING(7) DELEGATING(8) SPEAKING(9) WAITING(10) WAITING_FOR_OWNER(11) DEGRADED(12)
WARNING(13) ERROR(14) SUCCESS(15) URGENT(16) SLEEPING(17)
```
Orthogonal channels, `VanPresenceFrame.kt:10-16`:
* `VanHealthState` { NOMINAL, DEGRADED, OFFLINE }
* `VanAuthorityState` { NONE, WAITING_FOR_OWNER, WARNING, ERROR, URGENT }
* `VanSpeechState` { QUIET, LISTENING, SPEAKING }
* `VanTurnPhase` { IDLE, CAPTURING, THINKING, DISPATCHING }
Plus `VanFiniteAction` (`RiveContract.kt:33+`) for one-shot gestures, and
`VanRenderer`/`VanCanvasReason` (`VanVisualRuntime.kt:193-220`).

### 2.2 Requested-state coverage

| Requested state | Present? | Evidence |
|---|---|---|
| idle | YES | `RiveContract.kt:10` |
| attentive | YES | `RiveContract.kt:11` |
| listening | YES | `RiveContract.kt:12` |
| **hearing** (distinct from listening) | **ABSENT** — only one LISTENING | — |
| **interpreting** | **ABSENT** — nearest is THINKING | `RiveContract.kt:13` |
| thinking | YES | `RiveContract.kt:13` |
| researching | PARTIAL — `SEARCHING` | `RiveContract.kt:14` |
| planning | **ABSENT** — folded into THINKING | — |
| **tool use** | **ABSENT** — nearest `WORKING`/`DELEGATING` | `:15`, `:16` |
| **browser use** | **ABSENT** — no browser/web state at all | — |
| executing | PARTIAL — `WORKING` | `RiveContract.kt:15` |
| waiting-external | PARTIAL — `WAITING(10)` exists but **is never set by any production caller** (see 2.3) | `RiveContract.kt:18` |
| success | YES | `RiveContract.kt:23` |
| warning | YES | `RiveContract.kt:21` |
| error | YES | `RiveContract.kt:22` |
| **interrupted** | **ABSENT** | — |
| offline | YES | `RiveContract.kt:8` |
| reconnecting | PARTIAL — `CONNECTING(1)`, also never set in production | `RiveContract.kt:9` |
| **trade opportunity** | **ABSENT from the enum.** Only a preview-only spec exists: `VanAuraSpecs.tradePreview("setup"/"entry")`, `VanAuraSpec.kt:247-258`, whose own KDoc says "architecture capacity, not a live trading product" (`VanAuraSpec.kt:237`) | |
| **trade management** | **ABSENT from the enum** — `tradePreview("in_trade"/"risk"/"stop")` `VanAuraSpec.kt:259-288` only | |
| **restrained / high-risk** | **ABSENT** — `tradePreview("risk")` is the nearest, preview-only | `VanAuraSpec.kt:274-282` |

So 10 of the 22 requested semantics are absent or preview-only. Notably there is **no state for
tool use, browser use, planning or interruption**, and all three trading semantics live outside the
state machine entirely.

### 2.3 WHO SETS the state — complete production trace

`grep -rn "VanLiveVisualState\." android/app/src/main/java/` gives **every** mutation site:

**Voice (`VanApplication.kt`):**
* `:151` `listeningStarted()` on partial transcript
* `:158` `finalTranscript(hasText)`
* `:171-172` `warning(0.25f)` + `settleToIdle(1200, allowCritical=true)` on recognizer failure
* `:177` `listeningStarted()/listeningEnded()`
* `:182-185` `speakingStarted()/speakingEnded()+settleToIdle()`
* `:190` `speechFrame(mouthOpen, viseme)`
* `:194-195` `speakingEnded() + settleToIdle()`

**Gateway (`VanGatewayClient.kt`):**
* `:419` `dispatchStarted()` → DELEGATING
* `:425-426` `warning(0.35)` + settle, on transport failure
* `:434` `"approval_required"` → `waitingForOwner()`
* `:437-438` `dispatchAccepted()` → WORKING, then settle after 900 ms
* `:442-446` `transition(...)` + settle 1200 ms
* `:450-456` `warning(0.35/0.40)` + settle
* `:459` `settleToIdle(700)`

**Readers only (no mutation):** `CommandCentreActivity.kt:140,247`,
`FloatingOverlayService.kt:186,653`.

**That is the entire production surface: voice recognition and the gateway response envelope.**
No other subsystem — not trading, not missions, not tools, not the browser — ever writes visual
state. `VanDurableState.WAITING`, `CONNECTING`, `SEARCHING`, `SUCCESS`, `SLEEPING`, `ATTENTIVE`
(as a direct set) are reachable only via the generic `transition()` bridge at
`VanGatewayClient.kt:442`, which passes whatever the gateway envelope said — grep shows no other
caller of `transition()`.

### 2.4 Arbitration, conflicts, stale state, transition duration

**Priority arbitration: PRESENT and real.**
* `VanLiveVisualState.kt:177-188` — an explicit integer priority ladder:
  ERROR/URGENT 100 > OFFLINE 95 > DEGRADED/WARNING 90 > WAITING_FOR_OWNER 80 >
  SPEAKING/LISTENING 70 > WORKING/SEARCHING/DELEGATING 60 > THINKING/CONNECTING/ATTENTIVE 50 >
  SUCCESS 45 > WAITING 30 > IDLE/SLEEPING 10.
* `VanLiveVisualState.kt:84-87` — a **320 ms anti-thrash hold** (`TRANSIENT_HOLD_MS`, `:19`):
  inside the hold window, a *lower-priority* non-interactive non-critical state is dropped.
  Direct interaction (`:161-164`) and critical states (`:166-175`) always win.
* `VanLiveVisualState.kt:118-135` — `settleToIdle` uses a **generation token** (`:122-124`) so a
  stale delayed idle cannot clobber a newer state. Also refuses to idle while a turn is live
  (`:125`) or while authority is raised (`:126`). This is a correct stale-state guard.
* **Orthogonality** (`VanPresenceFrame.kt:32-63`): pose vs semantic are resolved separately, so
  "listening while Google mesh unverified" renders LISTENING body + DEGRADED Zone C. This is the
  single strongest piece of design in the whole visual stack.

**Transition duration handling: ABSENT.** There is no interpolation between two states' aura specs.
`VanAuraSpecs.forState()` (`VanAuraSpec.kt:81`) returns a hard spec; `VanEmbodiment`
(`VanCanvasFallback.kt:132-133`) recomputes it every recomposition. When the state flips, intensity,
filament count, envelope segments, envelope radius and semantic colour **all change on the very next
frame**. There is no `animateFloatAsState`, no `Crossfade`, no spec lerp anywhere:
```
$ grep -rn "animateColorAsState|animateFloatAsState|Crossfade|animateDpAsState|lerp\(" \
    android/app/src/main/java/com/dial/van/{visual,overlay}/
  -> NO MATCHES (rc=1)
```
**Every aura state change is a hard cut on the next composed frame.** The only continuous quantity
is `phase`, and even that restarts because the tween duration is state-dependent (1.4).

---

## 3. TRADING → AURA

### VERDICT: **ABSENT.** There is no code path anywhere in the repo where a classified trading
state changes the aura's colour, topology or semantic state.

Evidence, exhaustive:

1. The only production writers of visual state are `VanApplication.kt` (voice) and
   `VanGatewayClient.kt` (command envelope) — see 2.3. Neither is trading-aware.
2. `grep -rn "VanLiveVisualState|VanAura|VanDurableState|semanticState" android/.../trading/`
   returns **five hits, all read-only**:
   * `trading/ui/TradingScreens.kt:57,62` — `VanVisualState` is only carried as an immutable field
     of `ScreenEnv` for chrome.
   * `trading/TradingCommandCentreActivity.kt:78` — `val cue = VanPresence.cue(degraded)`.
     The trading command centre's VAN presence is derived **only from subsystem DegradedMode
     health**, not from any trade.
   * `trading/TradingCommandCentreActivity.kt:81` — `remember(cue.durableState) { ScreenEnv(...) }`.
     The VAN state is *cached on degraded-mode state*, so it cannot even change with the market data
     the screen polls.
3. `grep -rni "aura|van_state|visual_state|durable_state|semantic_state" backend/ trading/ hermes/`
   returns exactly **one** hit — `backend/tests/test_automation_compiler.py:421`
   `test_hot_index_rebuilds_from_durable_state`, an unrelated persistence test. **No backend or
   trading service ever emits a visual/aura/presence semantic state.**
4. The `backend/.../requires_owner_presence` hits (`capability/models.py:124`,
   `mission/models.py:157`, `capability/registry.py:308`, `capability/router.py:144`,
   `mission/service.py:347`, `mission/api.py:382`) are an **authorization** concept (is the owner
   present to approve), not visual presence. Easy to mistake for a binding; it is not one.

### Nearest thing to a trading→aura binding
`VanAuraSpecs.tradePreview(kind)` — `VanAuraSpec.kt:238-299`. Seven trade semantic families
(`watching` teal, `setup` violet, `entry` gold, `in_trade` cyan, `profit` green, `risk` amber,
`stop` red) with distinct Zone C topologies. But:
* Its own KDoc (`VanAuraSpec.kt:237`) says: *"Topology-board trade examples — architecture capacity,
  not a live trading product."*
* Its **only caller in the entire repo** is `android/visual-preview/src/main/kotlin/.../VanPreviewSheets.kt:750`,
  i.e. the PNG evidence-board renderer. It is not referenced from `android/app` at all.
* The trade families are not members of `VanDurableState`, so no arbitration, no priority, no
  `VanPresence` path and no Rive input can carry them.

**Classification: the trade aura families are a rendered mock-up, not a binding.**

---
## 4. BODY ANIMATION

### 4.1 Three-way renderer ladder, and which rung actually runs

`VanVisualRuntime.decide()` (`VanVisualRuntime.kt:243-258`): RIVE → OWNER_ART → CANVAS.
`VanAvatar` (`VanCanvasFallback.kt:51-85`) dispatches on that decision, and
`resolveRenderer(context)` (`VanCanvasFallback.kt:184-202`) tries to open
`RiveBindingContract.ASSET_FILE` from `context.assets`.

**Hard facts about the Rive rung:**
```
$ find android/app/src/main -type d -name assets -o -type d -name raw   -> NOTHING
$ find . -name "*.riv"                                                  -> NOTHING
$ grep -n rive android/app/build.gradle.kts -> :148 implementation("app.rive:rive-android:9.6.5")
```
There is **no `assets/` directory and no `van.riv` anywhere in the repo**, while the 4–5 MB
`rive-android:9.6.5` dependency with its native libraries IS shipped in the APK.
So `context.assets.open(...)` throws `IOException` (`VanCanvasFallback.kt:196`), `assetBytes == null`,
and `VanVisualRuntime.decide` returns reason `ASSET_MISSING` (`VanVisualRuntime.kt:251`).
**The RIVE path is dead code on every build in this repo.** `VanRiveAvatar.kt:50-104` is a correct,
defensively-written binding to an artboard that does not exist.

**Which rung runs in practice: OWNER_ART**, because all eight drawables are packaged:
`res/drawable-nodpi/` contains `van_state_{idle,listening,thinking,working,searching,notifications,
success,warning}.png` plus `van_compact_docked.png`, and `VanStateArt.artAvailable()`
(`VanStateArt.kt:27-29`) requires all eight — which holds. So `VanOwnerArtAvatar`
(`VanCanvasFallback.kt:88-117`) is the shipping body.

### 4.2 Static PNG swap, not continuous articulation

`VanOwnerArtAvatar` draws exactly one `Image(painterResource(resId))` (`VanCanvasFallback.kt:103-116`).
`VanStateArt.drawableFor(state)` (`VanStateArt.kt:20`) maps state → pose → drawable via
`VanArtPoses.forState` (`VanArtPose.kt:85-116`), which collapses **18 states onto 8 bitmaps**:
IDLE/CONNECTING/SPEAKING/SLEEPING/OFFLINE → the same `van_state_idle` image (`VanArtPose.kt:86-91`);
WARNING/ERROR/URGENT/DEGRADED → the same `van_state_warning` image (`VanArtPose.kt:111-115`);
ATTENTIVE/WAITING/WAITING_FOR_OWNER → `van_state_notifications` (`:104-107`).

* **Crossfade between poses: ABSENT.** There is no `Crossfade`, no `AnimatedContent`, no alpha
  tween (grep in 2.4 returned nothing). Changing state swaps the bitmap on the next frame — a
  **hard cut**. Also note: because five states share `van_state_idle`, transitions between them are
  visually invisible in the body; only the aura and chrome change.
* **Continuous motion that *is* present**: `VanCharacterMotion.sample()`
  (`VanCharacterMotion.kt:129-169`) applies four asynchronous harmonics (`hover` 1×, `breath` 1.31×,
  `drift` 0.57×, `settle` 2.17× — `:145-148`) to X/Y offset (dp), `rotationZ` and `scale`, via
  `Modifier.offset(...).graphicsLayer{...}` (`VanCanvasFallback.kt:107-112`). Per-state amplitude
  profiles at `VanCharacterMotion.kt:182-211`; alert tension for DEGRADED/WARNING/ERROR/URGENT at
  `:207-210` and `:153-157`. `headCounterDeg` is computed (`:167`) but **never consumed by the
  owner-art renderer** — a bitmap has no separable head.
* Amplitudes are small: max `bobDp` 1.65 dp, max `swayDeg` 0.82°, `breathScale` ≤ 0.007
  (`VanCharacterMotion.kt:187,206`). This is a *very* subtle float, not articulation.
* Reduced motion freezes it to an attention-only pose (`VanCharacterMotion.kt:134-141`).

### 4.3 Abrupt reset / loop seam / thrash protections

| Concern | Status |
|---|---|
| Phase loop seam | HANDLED for the field (`VanWindFieldMotion.kt:9-12`, phase 0 ≡ phase 1); `VanCharacterMotion` harmonics at 1.31/0.57/2.17× are **NOT** period-1, so the character motion *does* jump at each phase wrap (every 2.0–6.0 s). |
| Phase restart at state change | **NOT HANDLED.** `vanIdlePhase` changes tween duration per state (`VanCanvasFallback.kt:252-266`), so `rememberInfiniteTransition` restarts the ramp. |
| Pose swap thrash | Partially handled *upstream* by the 320 ms priority hold (`VanLiveVisualState.kt:84-87`); nothing in the renderer. |
| Stale delayed idle | HANDLED by generation token (`VanLiveVisualState.kt:122-124`). |
| Rive fallback thrash | HANDLED — `onLoadFailed` flips `decision` once into `remember` state (`VanCanvasFallback.kt:59,67-74`). |

**Classification of body animation: canned bitmap swaps with a continuous micro-transform overlay.
No crossfade, no articulation, no interpolation between poses.**

---

## 5. OVERLAY

### 5.1 Declarations
`AndroidManifest.xml:9` `SYSTEM_ALERT_WINDOW`; `:4` `FOREGROUND_SERVICE`; `:5`
`FOREGROUND_SERVICE_SPECIAL_USE`; `:12` `RECEIVE_BOOT_COMPLETED`; `:6` `POST_NOTIFICATIONS`.
Service at `AndroidManifest.xml:51-58`: `android:foregroundServiceType="specialUse"` with
`PROPERTY_SPECIAL_USE_FGS_SUBTYPE = "van_owner_assistant_overlay"`.
(`specialUse` is the honest choice here, but it is also the type Google Play scrutinises most; no
justification doc was found in `docs/` tying the subtype to a Play declaration.)

Window: `TYPE_APPLICATION_OVERLAY`, `PixelFormat.TRANSLUCENT`, `Gravity.TOP or START`
(`FloatingOverlayService.kt:137-147`). Foreground started in `onCreate` immediately after
`addView` (`:155-157`). `onStartCommand` returns `START_STICKY` (`:166`).

**No runtime `Settings.canDrawOverlays` check inside the service** — `onCreate` calls
`windowManager.addView` unguarded (`:155`). If the permission was revoked, this throws and the
service crashes. (A permission gate may exist in onboarding; it is not in the service.)

### 5.2 Drag / dock / dismiss
* `vanGestures()` (`FloatingOverlayService.kt:243-260`) attaches `detectDragGestures` +
  `combinedClickable(onClick=toggle, onDoubleClick=command centre, onLongClick=quick controls)`.
  Crucially it is applied **only to the VAN embodiment**, not the workboard
  (`:276-279`, `:686-690`, `:714-722`), which matches the class KDoc at `:98-99` — scroll is not
  hijacked. Good.
* `dragBy` (`:775-796`) clamps to screen bounds and calls `windowManager.updateViewLayout` per drag
  event.
* `finishDrag` (`:798-830`) snaps to an edge within 48 px (`OverlayStateStore.kt:80-90`) and records
  `DockEdge` (`:92-98`).
* A native-style bottom-centre **dismiss target** (`:857-880`) with haptic arm feedback
  (`:790`) that `stopSelf()`s and clears `serviceRunning` (`:802-804`).

### 5.3 Recovery after process kill
* `START_STICKY` (`:166`) covers OOM restart.
* `OverlayRecoveryReceiver.kt:107-118` restarts the service on `BOOT_COMPLETED` /
  `MY_PACKAGE_REPLACED` when `serviceRunning` was persisted true. Permission is declared
  (`AndroidManifest.xml:12`), receiver registered (`AndroidManifest.xml:69-76`).
* Position/presentation/dock persisted in SharedPreferences (`OverlayStateStore.kt:28-55`),
  written on every UI state change (`FloatingOverlayService.kt:756-762`).
* **Gap:** `START_STICKY` redelivers a null Intent; `onStartCommand` handles only its two actions
  (`:162-165`), which is fine, but on Android 12+ a `specialUse` FGS restarted from the background
  can hit `ForegroundServiceStartNotAllowedException` — `FloatingOverlayService.start()`
  (`:1024`) calls `startForegroundService` with **no try/catch**.
* **Gap:** `startForeground` (`:157`) is not wrapped either; on API 34 a `specialUse` FGS without a
  granted special-use case can throw.

### 5.4 Battery / lifecycle
* Custom `LifecycleOwner` + `SavedStateRegistryOwner` for the ComposeView (`:101`, `:110-111`,
  `:123-124`, `:151-152`). Lifecycle is driven to `STARTED` (`:156`) and `DESTROYED` (`:174`),
  **never to `RESUMED`, and never back to `CREATED`/`STOPPED` when the overlay is minimized or
  the screen turns off.** Consequence: `rememberInfiniteTransition` keeps animating the aura at
  ~2–6 s/cycle **whenever the service is alive**, including screen-off, because nothing ever moves
  the lifecycle below STARTED. There is no `ACTION_SCREEN_OFF` receiver and no visibility check:
  ```
  $ grep -rn "ACTION_SCREEN_OFF|isInteractive|onTrimMemory" overlay/  -> (see log; none)
  ```
* `applyBackdropBlur()` (`:971-981`) and `updateWindowFlags()` (`:958-969`) set
  `FLAG_BLUR_BEHIND` + `blurBehindRadius` on API 31+ — **this is the only real blur in the product,
  and it is window-level backdrop blur of the apps behind, not aura blur.**

### 5.5 What FloatingOverlayService actually renders
Six presentations (`:204-239`): FULL_FLOATING, WORKBOARD_COMPACT, WORKBOARD_EXPANDED,
WORKBOARD_MAXIMIZED, MINIMIZED, DOCKED.
* FULL_FLOATING (`:263-289`) — `VanEmbodiment` in a 184 dp hit box with a 96 dp character
  (`OverlayTheme.kt:13-14`), i.e. `characterFraction = 96/184 = 0.522`. With `bodyEdge = 184*0.522
  = 96 dp`, the exclusion gap is `96*0.055 = 5.3 dp` — see 1.3.
* WORKBOARD_* (`:345`, `:447`, `:509`) — `VanEmbodiment(..., characterFraction = 0.55f)` inside a
  `VanGlassSurface` with headline/caption/health line, chat list, trade list.
* MINIMIZED (`:686-691`) — `VanMinimizedAvatar` **only**; note this composable draws **no aura at
  all** (`VanMinimizedAvatar.kt:50-154` is face + rim stroke). Minimized VAN has no living field.
* DOCKED (`:711-725`) — a hand-drawn cyan blob `Path` (`:695-709`) plus `VanEmbodiment`.
* Chrome text comes from `VanOverlayChrome.resolve` (`VanOverlayChrome.kt:146-165`), which is where
  "no state relies on colour alone" is actually satisfied — every state also gets a
  `VanStatusPalette` label and a `VanCaptions` caption.

---
## 6. VISUAL EVIDENCE

### 6.1 Build attempt (as instructed, once offline then once online) — **FAILED, no PNGs produced**
```
$ cd android && ./gradlew --offline :visual-preview:test :visual-preview:renderVanPreviews
FAILURE: ... Plugin [id: 'com.android.application', version: '8.10.1', apply: false] was not found
BUILD FAILED in 744ms   (EXIT=1)

$ cd android && ./gradlew :visual-preview:test :visual-preview:renderVanPreviews      # no --offline
FAILURE: ... same, could not resolve 'com.android.application:...gradle.plugin:8.10.1'
   Searched: Google, MavenRepo, Gradle Central Plugin Repository
BUILD FAILED in 2s      (EXIT=1)
```
The root `android/build.gradle.kts:1` declares AGP for the whole build, so even the pure-JVM
`:visual-preview` module cannot be configured without resolving AGP, which this sandbox's proxy
cannot reach. **No PNGs were regenerated; the committed artifacts could not be independently
reproduced in this environment.** Working tree remained clean (`git status --porcelain` shows only
the pre-existing untracked `evidence/`); no `git checkout` was needed and nothing was modified.

### 6.2 Does visual-preview share the shipping geometry? **PARTLY — and the divergence is material.**

`android/visual-preview/build.gradle.kts:14-38` compiles the *same source files* out of
`app/src/main/java` (not copies):
```
visual/VanDrawOp.kt, VanScene.kt, VanStatusPalette.kt, VanVisualRuntime.kt, VanPresence.kt,
VanPresenceFrame.kt, RiveContract.kt, VanGlassTokens.kt, VanAuraSpec.kt, VanEffectBudget.kt,
VanWindFieldMotion.kt, VanBodyExclusionProfile.kt, VanFieldGeometry.kt, VanArtPose.kt,
degraded/DegradedMode.kt, overlay/OverlayTheme.kt
```
So **`VanFieldGeometryEngine`, `VanWindFieldMotion`, `VanBodyExclusionProfile` and `VanAuraSpecs`
ARE genuinely shared** — the *point positions* in the PNGs are the same numbers the device computes.
That is a real and unusually good property, and the build file's claim (`build.gradle.kts:8-12`)
is accurate as far as geometry goes.

**BUT `VanAura.kt` is NOT in that list.** The painter — everything that turns geometry into pixels —
is re-implemented in AWT at `GlassPainter.kt:215-314` (`drawAura`, `drawZoneA`). Diffing the two
painters line by line:

| Aspect | Compose (ships) | AWT (evidence PNGs) | Divergent? |
|---|---|---|---|
| Electrical branches | drawn, 3-pass w/ white core — `VanAura.kt:99-111`, `:153-181` | **NOT DRAWN AT ALL** — `grep electricalBranches visual-preview/` returns **zero** hits | **YES — the PNGs omit an entire visual layer** |
| Zone A alpha | `(0.045+0.045·i).coerceIn(0.035,0.085)` `VanAura.kt:194` | `(0.10+0.08·i).coerceIn(0.08,0.18)` `GlassPainter.kt:294` | **YES — preview is ~2× brighter** |
| Zone A radius | `bodyEdge·0.13·breathing` `VanAura.kt:195` | `bodyEdge·0.20·INNER_RADIUS_SCALE·breathing` `GlassPainter.kt:295` | **YES — ~1.5× larger** |
| Zone A blob placement | `center.x ∓ bodyEdge·0.31 / 0.34` `VanAura.kt:199-206` | `cx ∓ bodyEdge·0.05 / 0.07` `GlassPainter.kt:298-299` | **YES — device blobs sit far off the body; preview blobs sit on it** |
| Dot bloom | 2.8× radius bloom circle `VanAura.kt:116-120` | none, flat ellipse `GlassPainter.kt:255-265` | **YES** |
| Stroke glow alpha | `(α·0.20).coerceAtMost(0.18)` `VanAura.kt:81` | `α·0.16`, uncapped `GlassPainter.kt:249` | YES (minor) |
| Ground glow | unclipped radial over a path `VanAura.kt:236-243` | clipped crescent `GlassPainter.kt:309-312` | YES |
| Orb link | pulse `0.18+0.34·p`, offsets .18/.30/.39 `VanAura.kt:128-143` | pulse `0.24+0.30·p`, offsets .11/.25/.35 `GlassPainter.kt:268-281` | YES |
| bodyEdge derivation | `minEdge · characterScale` `VanAura.kt:58` | `radius · 2` `GlassPainter.kt:226` | YES |
| Centre | `(w/2, h·0.48)` `VanAura.kt:59` | caller-supplied | YES |

**Conclusion for Q6: the PNGs are produced by a partially-shared pipeline. Geometry is shared;
appearance is not.** The evidence boards therefore *cannot* establish what the device shows,
and in one case they demonstrably show less (no electrical branches) and in another more
(brighter, closer, larger Zone A haze). The build file's "any drift in ... the living-field geometry
shows up in previews" is true for geometry and **false for the painted result**.

Also note: the character in every PNG is drawn by `OwnerArt.kt` reading the owner bitmap pack — the
same PNGs that ship — so the *body* is faithful. It is only the aura that diverges.

### 6.3 On-device evidence: NONE
```
$ ls android/app/src/                 -> main  test        (no androidTest source set)
$ find . -name "*.gif" -o -name "*.mp4" -o -name "*.webm" -o -name "*frame_*"   -> NOTHING
```
There are **no instrumented tests, no emulator/device screenshots, no Paparazzi/Roborazzi/
screenshot-testing harness, no animation frame sequences and no video**. `androidTestImplementation`
is declared once (`android/app/build.gradle.kts:129`) but there is no `androidTest` source set.
**Every single visual artifact is a static, single-frame, headless-JVM render at one fixed phase**
(`GlassPainter.kt:222` `phase: Float = 0.18f` — a hardcoded default). Motion is literally not
depicted anywhere.

### 6.4 Evidence-manifest integrity defect
`artifacts/release/preview/rev21/manifest.json` — the entries `command-centre-idle` and
`command-centre-degraded` carry the **identical** `sha256:57975c24cb0716cc83efe08b0894c5bdf864878cbfffc98de285168777f82682`
and identical `bytes: 266028`. They are the same image filed under two different states, and the
image I read visually (below) confirms it: `command-centre-idle.png` actually renders
"Van / **Degraded** / Some subsystems are down." **The IDLE evidence shot is a DEGRADED render.**

---

## 6.5 WHAT THE PNGs ACTUALLY SHOW (read visually, described honestly)

**`van_aura_topology.png`** (2320×1419) — a dark presentation board, "VAN aura topology & semantic
ladder". Top-left, one large hero: the owner-art chibi VAN (white swept hair, cyan visor, lab coat,
holding a holographic tablet) with **4–5 thin, hairline, unconnected teal curved strokes** scattered
loosely around him at roughly 1–1.5 body-widths out, plus two or three tiny dots. There is no visible
haze, no volume, no gradient field — just sparse thin arcs on black. The A/B/C legend text overlaps
one of the arcs. Top-right, the budget ladder FULL / REDUCED / REDUCED_MOTION / LOW / STATIC:
**all five cells look essentially identical** (same pose, same red warning triangle, same two or
three arcs); only the caption differs (`C×2` vs `C×1` for LOW). A reader cannot tell the budgets
apart. Middle row, five semantic examples (waiting-for-owner amber, warning amber, error red,
urgent red, success green): each is the same character with one or two coloured hairline arcs and a
large **baked-in vector icon** (⚠ triangle / ✓ tick / ✉ badge) — the icon, not the aura, is what
actually reads. Bottom row, eight "trade-state capability" cells (watching / setup forming / entry /
in trade / profit / risk rising / stop-invalid / intervention): **all eight use the identical
character bitmap** and differ only in one or two faint coloured arcs and a colour-coded label. The
board itself captions them "architecture reserved in Zone C, not a live trading product."
*Honest read: the aura in this board is a handful of stray thin curves, not an atmosphere.*

**`van_state_matrix.png`** (2152×1644) — "VAN state matrix — 18 durable states", 3×6 grid.
Each cell: the owner-art chibi (whose own bright cyan rim-light is **painted into the bitmap**, not
rendered) surrounded by 2–4 thin teal/amber/red arcs and occasional dots, with state name, caption
and telemetry line (`field 68% · Zone C 3 · scale 1.58`). Distinctions that genuinely read:
`offline` is desaturated grey; `searching` holds a magnifier; `listening` holds a waveform;
`attentive`/`waiting`/`waiting for owner` hold the same envelope-with-3 bitmap; `success` has a
green tick; `warning`/`error`/`urgent`/`degraded` share the identical warning-triangle bitmap and
differ only by arc colour and a small solid control pill. So of 18 cells, roughly 7 distinct bodies
and ~4 genuinely distinct arc colours. **Most of the per-state differentiation comes from the
bitmap prop and the text label, not from the aura.**

**`van_floating_overlay_preview.png`** (2000×1223) — four mock phone frames with grey placeholder
grids behind. Resting: VAN at ~10% of screen height with two faint teal arcs. Compact: VAN + a
translucent dark rounded card with "I'm listening…" and four chips. Expanded: VAN + a wider card
with "Van / Working / Working on it… / Google mesh unverified" + chips. Docked: VAN clipped at the
right edge inside a thin amber crescent with a small ⚠. Caption states explicitly: *"The authored
van.riv artboard remains EXTERNAL — no state below claims Rive READY."* The "glass" is a flat dark
translucent fill with a 1px stroke — there is **no visible backdrop refraction or blur** in the
render (as expected; the real blur is a window flag that a JVM render cannot show).

**`rev21/floating-working.png`** (480×640) — one character at top with **three** thin teal arcs
(one above-left, one right, one below), and a dark rounded card reading "Van / working". The arcs
are broken and clearly detached from the body. Nothing glows.

**`rev21/floating-minimal-listening.png`** — character with waveform prop; **five** thin teal arcs
in a loose, deliberately non-concentric arrangement plus two small dots. This is the best-looking
of the set: the arcs at different radii genuinely read as a scattered field rather than a ring.
Still entirely hairline strokes; no haze, no depth.

**`rev21/floating-urgent.png`** — character + red ⚠; **two dark-red arcs and two red dots**, plus
one faint teal arc below. A dark card with a reddish tint holds four chips. The urgency reads
almost entirely from the ⚠ bitmap and the card tint; the two thin red arcs are subtle to the point
of being easy to miss.

**`rev21/docked-idle.png`** — mostly empty dark canvas; at the right edge a small VAN inside a thin
teal "D"-shaped crescent outline. **No aura arcs at all in this presentation.**

**`rev21/command-centre-idle.png`** (1180×1420) — a full command-centre page: hero card with VAN +
⚠, headline "Van / **Degraded** / Some subsystems are down. / Google mesh: Awaiting gateway
google_mesh evidence (CONFIGURED/READY) / Google mesh unverified"; six info cards (State/Mission,
Attention, Decisions, Tasks, Projects, Connections); a teal "Start floating Van" button; a solid
amber "Approve A4 action (biometric)" button; footer "Critical actions switch from translucent to
solid controls (§14)…" and, in cyan, *"Character is interim owner art / Canvas — authored .riv and
owner visual sign-off remain EXTERNAL."* **The file named `-idle` renders DEGRADED** (see 6.4).
A faint amber arc is visible behind the hero card. The page is honest about its own status, which
is to its credit.

**Common to all eight: single frame, one fixed phase, no motion depicted, aura = a few hairline
strokes.** The strongest visual identity in every image comes from the owner's bitmap art, not from
the rendered field.

---
## 6.6 THE COMMITTED EVIDENCE IS TWO REVISIONS STALE — the single largest evidence finding

* `VanEvidenceMatrix.kt:36` — `const val EVIDENCE_DIR = "rev23"`. The **current** generator writes
  `artifacts/release/preview/rev23/`.
* `$ ls artifacts/release/preview/` → only **`rev21`** exists. `artifacts/release/preview/rev23`
  does not exist.
* `artifacts/release/preview/rev21/manifest.json:2` → `"authority_revision": "2.1"`, while
  `visual-authority/van-visual-authority-v2.yaml:1-2` is `aura_v2_3 / revision: "2.3"` and
  `VAN_LIVING_WIND_FIELD_RUNTIME_REV_1.md` is the Rev 2.3 companion.
* `VAN_LIVING_WIND_FIELD_RUNTIME_REV_1.md §13` states: *"Canonical named evidence is written under
  `artifacts/release/preview/rev23/`; the Rev 2.3 generator no longer writes a `rev21/` directory"*
  and that `van_orthogonal_presence.png` / `rev23/orthogonal-presence.png` certify the orthogonal
  combinations.
  ```
  $ find artifacts -name "*orthogonal*"  -> NOTHING
  ```

**Therefore: every committed PNG in this repo was produced by an older generator against an older
authority revision. The visual evidence does not depict the code at HEAD.** The doc's central
certification board does not exist. Any claim of the form "the boards show the shipping field" is
unsupported at this commit.

---

## 7. DOC CONFORMANCE MATRIX

### 7.1 Rev 2.2 Addendum — three-zone architecture (§2–§4)

| Requirement | Status | Evidence |
|---|---|---|
| Zone A inner presence, identity cyan, body-adjacent | IMPLEMENTED | `VanAura.kt:187-245` |
| Zone A `radius_scale: 1.00` | PARTIAL — const exists (`VanAuraSpec.kt:71`) but Compose ignores it and hardcodes `0.13·bodyEdge` (`VanAura.kt:195`); only the AWT painter uses it (`GlassPainter.kt:295`) | |
| Zone A `alpha_idle 0.12 / alpha_active 0.20` | **NOT MET** — Compose clamps to `0.035..0.085` (`VanAura.kt:194`), i.e. **~2.5× dimmer than spec**. AWT preview uses `0.08..0.18` (`GlassPainter.kt:294`), close to spec. **The evidence complies; the device does not.** | |
| Zone B mid interaction, `radius_scale 1.12` | IMPLEMENTED | `VanAuraSpec.kt:72` `MID_RADIUS_SCALE=1.12`, used `VanFieldGeometry.kt:73,134` |
| Zone B `filament_count_full [2,5]` | IMPLEMENTED (0 allowed for OFFLINE/SLEEPING, which is sensible) | `VanAuraSpec.kt:218-224`, `VanFieldGeometry.kt:82` |
| Zone B `arc_count_full [1,4]` | IMPLEMENTED as electrical branches | `VanFieldGeometry.kt:334` `coerceIn(1,4)` |
| Zone C `radius_scale 1.35–1.70` | IMPLEMENTED and enforced | `VanAuraSpec.kt:69-70`, clamped `VanFieldGeometry.kt:135-138` |
| Zone C `alpha_idle 0.08 / alpha_active 0.18` | PARTIAL — clamp is `0.06..0.24` (`VanFieldGeometry.kt:139`); IDLE authored at `0.12` (`VanAuraSpec.kt:86`) vs spec 0.08 | |
| Zone C `segment_count_full [1,4]` | IMPLEMENTED | `VanAuraSpec.kt:68` `MAX_ENVELOPE_SEGMENTS=4` |
| Zone C `max_total_coverage_degrees: 180` | IMPLEMENTED + tested | `VanAuraSpec.kt:67`, `VanAuraSpec.kt:48`, `VanAuraEnvelopeTest.kt:12` |
| `full_ring_forbidden: true` | IMPLEMENTED + tested | `VanEffectPolicyTest.kt:28` `workingAuraNeverDrawsAFullRing`; `VanFieldRev3Test.kt:58` `frozenFrameDoesNotCollapseToCommonRadiusHalo` |
| `allow_local_nodes: true` | IMPLEMENTED | `VanAuraSpec.kt:14` `node`, `VanFieldGeometry.kt:183-212` |
| `colour_mode: semantic` — colour in Zone C only, never repaint the body | IMPLEMENTED | `VanAura.kt:77,100,114` ink split; `VanAuraEnvelopeTest.kt:45` |
| **`minimum_gap_from_mid_field_dp: 8`** | **ABSENT** — no dp gap is computed or asserted anywhere; the only gap is the body-exclusion `0.055·bodyEdge` (`VanBodyExclusionProfile.kt:162`), which is a *body* gap, not a B→C gap | |

### 7.2 Rev 2.2 §6 — 18 state topologies

| | Status | Evidence |
|---|---|---|
| All 18 states have a Zone C fragment | IMPLEMENTED + tested | `VanAuraSpec.kt:83-215` (all 18 branches), `VanAuraEnvelopeTest.kt:12` |
| Zone C topology unique per state | IMPLEMENTED + tested | `VanAuraEnvelopeTest.kt:24` `zoneCTopologyIsUniquePerState` |
| Each state differs by *topology*, not only icon/colour | PARTIAL — the spec numbers differ per state, and `VanFieldGeometryTest.kt:11` asserts geometric distinctness; but visually (see 6.5) the difference is 1–3 hairline arcs at slightly different angles, and the boards still lean on the baked-in bitmap prop (⚠/✓/✉) for readability, which §6 and §11 anti-patterns warn against | |
| §6.11 WAITING_FOR_OWNER: "Zone C should now do more of the semantic work" than the lower glass strip | **NOT MET in practice** — `van_state_matrix.png` still shows the solid control strip + envelope bitmap carrying the meaning | |
| §8.1 reduced motion preserves Zone C | IMPLEMENTED | `VanAuraSpec.kt:56-57` keeps ≤2 segments; `VanEffectPolicyTest.kt:11` |
| §8.2 LOW retains ≥1 readable fragment | IMPLEMENTED | `VanAuraSpec.kt:55`, `VanAuraEnvelopeTest.kt:34` |
| §8.3 STATIC keeps inner presence + ≥1 outer segment | IMPLEMENTED | `VanAuraSpec.kt:54` (2 if critical, else 1) |

### 7.3 Rev 2.2 §7 — trade semantic families

| Family | Spec'd | In code | Wired to trading? |
|---|---|---|---|
| watching / monitoring (teal) | ✓ | `VanAuraSpec.kt:241-246` | **NO** |
| setup forming (blue-violet) | ✓ | `:247-252` | **NO** |
| entry opportunity (gold) | ✓ | `:253-258` | **NO** |
| in trade / active position | ✓ | `:259-267` | **NO** |
| profit / target hit (green) | ✓ | `:268-273` | **NO** |
| risk rising (amber-red) | ✓ | `:274-282` | **NO** |
| stop / invalidation (red) | ✓ | `:283-288` | **NO** |
| urgent intervention (vivid red) | ✓ | `:289-297` (`else` branch) | **NO** |
| **hedged / multi-signal / dual-accent nodes** | ✓ | **ABSENT** | — |
| **paused / no-trade / guarded dimmed lane** | ✓ | **ABSENT** | — |
Status: **SIMULATED.** 8 of 10 families exist as preview-only specs; 0 are reachable from the app.

### 7.4 Living Wind Field Rev 1(.2) §12 acceptance list

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 1 | No full/implied concentric ring in a frozen frame | IMPLEMENTED + tested | `VanFieldRev3Test.kt:58` |
| 2 | Zone B/C detached from body-safe region | IMPLEMENTED + tested | `VanFieldGeometryTest.kt:78`, `VanFieldRev3Test.kt:21`, `VanBodyExclusionProfile.kt:150-184` |
| 3 | Semantic states distinct in geometry not only colour | IMPLEMENTED + tested | `VanFieldGeometryTest.kt:11` |
| 4 | Phase wrapping seamless | IMPLEMENTED for the field, **NOT** for the character | `VanWindFieldMotionTest.kt:10` passes; `VanCharacterMotion.kt:146-148` harmonics at 1.31/0.57/2.17× are not period-1 so `VanCharacterMotionTest.kt:10 loopBoundaryIsSeamless` can only be checking the field-side wrap helper — the sampled character frame genuinely differs at p=0 vs p=1 |
| 5 | LISTENING + Google-unverified → LISTENING pose + DEGRADED Zone C | IMPLEMENTED + tested | `VanPresenceFrame.kt:32-63`, `VanFieldGeometryTest.kt:38`, `VanPresenceTest` |
| 6 | Mic-end ordering cannot erase THINKING | IMPLEMENTED | `VanPresenceFrame.kt:89-92` |
| 7 | TTS round-trip restores underlying activity | IMPLEMENTED | `VanPresenceFrame.kt:129-143`, `:40-44` |
| 8 | TTS cannot replace authority | IMPLEMENTED | `VanPresenceFrame.kt:35-45` (authority checked before speech) |
| 9 | OFFLINE uplink forces pose/semantics/chrome | IMPLEMENTED | `VanPresenceFrame.kt:34,51`, `VanPresence.kt:197-207`, `VanOverlayChrome.kt:153` |
| 10 | **Compose and Java2D both compose through `VanFieldGeometryEngine`** | PARTIAL — both call the engine (`VanAura.kt:66`, `GlassPainter.kt:233`) but the AWT painter **silently drops `geometry.electricalBranches`** and paints Zone A with different constants (see 6.2). The stated goal "removes the previous dual-painter drift" (§6) is **not achieved** | |
| 11 | Reduced motion produces stable geometry | IMPLEMENTED + tested | `VanFieldGeometryTest.kt:96` |
| 12 | Gateway `accepted` never displays SUCCESS | IMPLEMENTED | `VanGatewayClient.kt:436-439` → `dispatchAccepted()` → WORKING (`VanLiveVisualState.kt:42-50`) |
| 13 | Overlay + Command Centre react to `DegradedModeStore.state` | IMPLEMENTED | `FloatingOverlayService.kt:185`, `CommandCentreActivity.kt:140,247` |
| 14 | Android + visual-evidence Gradle gates pass | **UNVERIFIED** — could not build (6.1) |
| 15 | Rev 2.3 evidence incl. orthogonal presence board, manually inspected | **NOT MET** — `rev23/` and `van_orthogonal_presence.png` do not exist (6.6) |

Additional Living-Wind-Field divergence: **§7 publishes a wind formula that the code does not use.**
Doc: `sin(2π(2u − 2t + s)) + 0.38 sin(2π(3u + 3t + 1.71s)) + 0.14 sin(2π(5u − t + 0.47s))`.
Code (`VanFieldGeometry.kt:467-470`): `sin(TAU(1.35u − 1.35t + s)) + 0.30 sin(TAU(2.80u + 2.10t +
1.71s)) + 0.10 sin(TAU(5.20u − 0.75t + 0.47s))`. Every coefficient differs. The doc is stale.

### 7.5 Rev 3.0 §14–§19 (and §20–§25, §41–§42)

| § | Requirement | Status | Evidence |
|---|---|---|---|
| 14 | Field continuously advecting | IMPLEMENTED | `VanFieldGeometry.kt:475-479` |
| 14 | Visibly wavy | IMPLEMENTED | `:467-471` |
| 14 | Asymmetric | IMPLEMENTED | `fieldAsymmetry` `VanWindFieldMotion.kt:57`; per-segment local wind `VanFieldGeometry.kt:144` |
| 14 | Non-ring topology | IMPLEMENTED + tested | `VanFieldRev3Test.kt:58` |
| 14 | Detached from silhouette | IMPLEMENTED + tested | `VanFieldGeometryTest.kt:78` |
| 14 | Electrically alive | IMPLEMENTED on device, **ABSENT in evidence** | `VanFieldGeometry.kt:320-398` vs 6.2 |
| 14 | State-sensitive | IMPLEMENTED | `VanAuraSpec.kt:81-235` |
| 14 | Deterministic for reproducible evidence | IMPLEMENTED | `seed01` `VanFieldGeometry.kt:504-507` |
| 14 | **`VanAuraDynamics` (14 physical controls incl. curlStrength, waveFrequency, waveSpeed, particleDensity, electricalBranching, interactionAttractorX/Y, glassCondensation)** | **ABSENT** — `grep VanAuraDynamics` = 0 hits; `curlStrength`/`waveFrequency`/`interactionAttractor`/`glassCondensation` = 0 hits each. Partially subsumed by the 9-field `VanWindFieldFrame` (`VanWindFieldMotion.kt:17-36`), but there is **no attractor input at all**, so the field cannot respond to interaction | |
| 15 | Multi-primitive silhouette exclusion (Ellipse + Capsule) | IMPLEMENTED — exactly the doc's shape | `VanBodyExclusionProfile.kt:105-143`, head+torso+shoulders `:163-183` |
| 15 | **gaps 10–14 / 16–28 / 30–48 dp at ~92 dp character** | **ABSENT as a contract; NOT MET at the shipping size.** No dp anywhere (1.3). The floating character is 96 dp (`OverlayTheme.kt:14`) → body gap `= 0.055 × 96 =` **5.3 dp**, i.e. **less than half the 10–14 dp minimum**. Zone C sits at `0.60·1.12·1.35..1.70 · bodyEdge` ≈ 43–58 dp from centre, i.e. ≈ 14–29 dp beyond the ~29 dp body radius — inside the "middle-field" band, not the 30–48 dp outer-excursion band. **No test asserts any dp gap.** | |
| 15 | No strand continuously traces the body outline | IMPLEMENTED | `ribbonSegments` splits on exclusion `VanFieldGeometry.kt:434-443` |
| 16 | Streamline + wind + low wave + ripple + curl + attraction | PARTIAL — 5 of 6; **state-specific attraction is ABSENT** (no attractor input) | `VanFieldGeometry.kt:447-488` |
| 16 | Motion deforms/travels, not opacity pulsing | IMPLEMENTED | `:475-479` advection term |
| 17 | Non-ring invariant + automated rejection of common-radius collapse | IMPLEMENTED | `VanFieldRev3Test.kt:58` |
| 18 | `VanElectricalBranch` with trunk/children/ink | IMPLEMENTED (field names differ: `alpha/width/glowWidth/life` vs doc's `intensity/lifetime/progress`) | `VanFieldGeometry.kt:30-38` |
| 18 | Appear/propagate/fork/bloom/fade/die; never permanent outline | IMPLEMENTED + tested | `VanFieldGeometry.kt:342-350`, `VanFieldRev3Test.kt:45` |
| 18 | **Per-state electrical behaviour (10 distinct behaviours)** | **PARTIAL/ABSENT** — there is exactly *one* branch algorithm; state affects only scalar `energy = sparkRate·0.65 + arcActivity·0.35` (`VanFieldGeometry.kt:218`) and colour ink. There is no "scanning burst", "travelling computation pulse" or "directional pulse" variant | |
| 19 | Deterministic particle lifetimes spawn→advect→curl→fade→expire | IMPLEMENTED | `VanFieldGeometry.kt:283-287`, `:307-309` |
| 19 | **Cache stable topology, update only dynamic coords per frame** | **ABSENT** — `VanFieldGeometryEngine.build()` allocates fresh `mutableListOf` for strokes/dots/branches and rebuilds all 35-point polylines **every frame** (`VanFieldGeometry.kt:74-76`, `:415-444`). At 5 filaments × 35 points + 12 dots + 4 branches × 12 points this is several hundred `VanFieldPoint` allocations per frame per VAN instance — exactly what §42 says to avoid | |
| 20 | **Glass condensation from field (0.0→1.0 progression)** | **ABSENT** — `grep condensation --include=*.kt android/` = **1 hit, a comment only**; `glassCondensation` = 0 hits | |
| 21 | **`VanCharacterAnimationFrame` (13 channels: hoverY, breathing, torsoTilt, headTilt, gazeX/Y, blink, left/rightHandPose, mouthOpen, viseme, stateBlend)** | **ABSENT** — 0 hits. Implemented instead: 5-field `VanCharacterMotionFrame` (`VanCharacterMotion.kt:118-124`). No hand poses, no separate torso/head tilt, no `stateBlend` | |
| 21 | Board presentation must not restart animation phase | IMPLEMENTED in spirit — `VanCharacterMotion` takes only presence + time (`:116` KDoc) | |
| 22 | **One monotonic visual clock, never restarted on recomposition or transition** | **NOT MET.** There is no monotonic clock. `vanIdlePhase` builds a *per-state-duration* `rememberInfiniteTransition` (`VanCanvasFallback.kt:250-279`) so the phase restarts on state change; `VanMinimizedAvatar.kt:36` owns a *second, unrelated* 5.2 s transition; every `VanEmbodiment` instance creates its own. `grep withFrameNanos` = 0 hits | |
| 23 | Idle life: hover 3.5–5.5 s, breathing 3–4.5 s, blink 2.6–6.4 s, gaze, hand settling, hair/visor secondary, orb drift, desynchronised phases | PARTIAL — 4 desynchronised harmonics exist (`VanCharacterMotion.kt:145-148`) but they are *ratios of one period*, so hover and breathing periods are tied to the state's tween (2.0–6.0 s) rather than the specified independent 3.5–5.5 / 3–4.5 s. **Blink is not applied to owner art at all** (`blinkFor` exists at `VanCanvasFallback.kt:281-286` for the Canvas rig; `blinkAmount` at `VanMinimizedAvatar.kt:157-164` for the portrait; neither reaches the shipping `VanOwnerArtAvatar`). No hand/hair/visor/orb secondary motion on owner art — a bitmap cannot have it | |
| 23 | Bounds ≤1.6 dp X, ≤2.5 dp Y, ≤1.65°, scale 0.992–1.008, ≤0.5° head counter | IMPLEMENTED + tested exhaustively | `VanCharacterMotionTest.kt:61-85` |
| 24 | State-specific body behaviour (9 described postures) | PARTIAL — expressed only as amplitude profiles (`VanCharacterMotion.kt:182-211`); the *bitmap* is one of 8 fixed poses, so "slight forward inclination", "presenting gesture", "nod/release" are not achievable | |
| 25 | **Pose transitions blend 120–420 ms, fast-out-slow-in / low-overshoot spring** | **ABSENT** — no `Crossfade`, no `animate*AsState`, no spring anywhere (2.4). Every pose and aura change is a 1-frame snap | |
| 41 | Lifecycle split into `VanOverlayController` / `VanAnimationRuntime` | **ABSENT** — 0 hits for both; `FloatingOverlayService.kt` is 1031 lines holding windows, gestures, chat draft, trade view, workboard mode and all Composables | |
| 42 | 60 fps target, degrade to 30; reduce density before freezing body life | PARTIAL — the budget ladder exists and orders surrender correctly (`VanEffectBudget.kt:201-234`), but there is **no fps measurement**: `frameBudgetMissed` (`VanEffectBudget.kt:247`) has no producer, and `rememberVanEffectBudget` samples thermal/power once per composition (`VanCanvasFallback.kt:159`) | |
| 26 | `VanWorkboardMode {CONTEXT, CHAT, VOICE, APPROVAL, TASK}` | DIVERGENT — code has `{CONTEXT, CHAT, VOICE, TRADES}` (`FloatingOverlayService.kt:93`); APPROVAL and TASK absent, TRADES added | |
| 43 | Rive external/not READY | ACCURATE and honestly surfaced | `VanVisualRuntime.kt:194,209`, boards say so |

---

## 8. TESTS — what they prove and what they cannot

12 JVM unit test files in `android/app/src/test/java/com/dial/van/visual/` (~60 `@Test`s) plus 2 in
`android/visual-preview/src/test/kotlin/`. **None of them could be executed here** (6.1), so the
following is a reading of intent, not of a green run.

### What the tests genuinely prove (and they are good tests)
* **Non-ring invariant** — `VanEffectPolicyTest.kt:28 workingAuraNeverDrawsAFullRing`;
  `VanFieldRev3Test.kt:58 frozenFrameDoesNotCollapseToCommonRadiusHalo` (this one actually checks
  radius variance, which is the right property).
* **Body detachment** — `VanFieldGeometryTest.kt:78 zoneBAndZoneCNeverEnterBodySafeCore`;
  `VanFieldRev3Test.kt:21 fieldAndElectricalBranchesRespectInflatedBodySilhouette`.
* **Geometry ≠ colour-only** — `VanFieldGeometryTest.kt:11`;
  `VanSceneIdentityTest.kt` + `VanAcceptanceGateTest.kt:69 grayscaleKeepsCriticalStatesDistinct`
  (converts to grayscale and requires shape signatures to differ — genuinely strong).
* **Orthogonality** — `VanFieldGeometryTest.kt:38 degradedSemanticEnvelopeDoesNotReplaceListeningInteractionField`;
  9 tests in `VanPresenceFrameTest.kt`; 10 in `VanPresenceTest.kt`.
* **Phase seam of the field** — `VanWindFieldMotionTest.kt:10`.
* **Motion-bound envelope for owner art** — `VanCharacterMotionTest.kt:61` (exhaustive over 18
  states × 3 × 3 × 2 × 201 phases).
* **Budget ladder semantics** — `VanEffectPolicyTest.kt:11,21`; `VanWindFieldMotionTest.kt:41,55`;
  `VanAuraEnvelopeTest.kt:34`.
* **Zone C coverage/uniqueness** — `VanAuraEnvelopeTest.kt:12,24,45,54`.
* **Overlay geometry constants** — `VanAcceptanceGateTest.kt:21-40`.
* **Renderer fallback ladder** — 6 tests in `VanVisualRuntimeTest.kt`.
* **14 finite actions produce distinct poses** — `VanAcceptanceGateTest.kt:57`.

### What they structurally cannot prove
1. **Motion quality.** Every test samples the *pure geometry function* at chosen phases. Nothing
   measures perceived speed, smoothness, or whether the field looks alive. The one thing a test
   *could* catch — the phase restart at state change (§22) — is invisible to these tests because
   `vanIdlePhase` is a `@Composable` and is never exercised.
2. **The Compose painter.** Zero tests touch `VanAura.kt`. Alphas, glow widths, the Zone A
   constants and the electrical draw calls are entirely unverified. This is exactly where the
   device/evidence divergence (6.2) lives, and no test can see it.
3. **GPU / frame cost.** No benchmark, no `JankStats`, no `Choreographer` sampling, no macrobenchmark
   module. The per-frame allocation behaviour (§19/§42, above) is untested.
4. **Perceived aura.** No golden-image regression test compares a render against an approved
   reference — `VanAcceptanceGateTest` compares *two freshly-rendered images to each other*, never
   to a committed baseline. So a global regression that dims or deletes the whole field would keep
   every test green.
5. **Anything on a device.** No `androidTest` source set; the overlay service, WindowManager flags,
   `FLAG_BLUR_BEHIND`, drag, dock, dismiss, foreground-service type, boot recovery and permission
   revocation are **completely untested**.
6. **The committed artifacts.** `VanAcceptanceGateTest.kt:111,125` were clearly written in response
   to the very idle/degraded collapse I found — but they render into a **temp directory**
   (`Files.createTempDirectory`, `:126`) and assert on that. They never read
   `artifacts/release/preview/rev21/manifest.json`, which still carries the duplicate
   `sha256:57975c24…` for both `command-centre-idle` and `command-centre-degraded`. **The test passes
   while the shipped evidence remains wrong.**
7. **Whether the state machine is ever driven.** No test asserts that any production subsystem calls
   `VanLiveVisualState`; the reducer is tested in isolation. A build where nothing ever set a state
   would be fully green.

---
