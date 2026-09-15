# VAN Glassmorphic Floating Assistant Design System
**Document:** VAN Glassmorphic Floating Assistant Specification  
**Status:** Canonical design overlay / implementation-ready  
**Product:** VAN — DIAL Hermes AI Assistant  
**Purpose:** Define the visual and technical treatment for VAN as a floating Android assistant using glassmorphism while preserving VAN's locked character identity, readability, performance, accessibility, and state clarity.

---

## 1. Core Design Principle

VAN remains the solid, recognisable visual anchor.

Glassmorphism is applied to the **interaction shell around VAN** rather than to VAN's body. The character must remain crisp, opaque, high-contrast, expressive, and visually authoritative at all times.

Canonical rule:

> **VAN is the solid visual anchor; glass is the contextual interface around him.**

This prevents VAN from becoming visually washed out, preserves character recognition at small sizes, and allows the surrounding UI to feel modern, premium, and spatially integrated with the Android environment.

---

## 2. Blue Electrical Aura — Canonical Requirement

Yes. VAN should retain and strengthen the **blue electrical/cyan energy aura around him**.

The aura is a separate visual system from the glassmorphic shell.

It should appear as a restrained, high-quality electrical field around VAN's silhouette, strongest around the visor, shoulders, hands, boots, and orb companion.

### Aura characteristics

- Electric cyan / blue energy outline.
- Soft bloom extending beyond VAN's silhouette.
- Fine animated electrical filaments or arcs at low intensity.
- Occasional micro-sparks during active states.
- Stronger glow when listening, thinking, working, or executing.
- Subtle idle pulse when inactive.
- Aura must never obscure VAN's facial features or outfit details.
- No constant aggressive lightning effect.
- The aura should read as intelligent energy, not a superhero electricity effect.

### Canonical visual hierarchy

```text
BACKGROUND / USER APP
        ↓
GLASSMORPHIC VAN SHELL
        ↓
BLUE ELECTRICAL AURA
        ↓
VAN CHARACTER
        ↓
ORB / ACTIVE EFFECTS
```

The aura therefore sits visually between VAN and the glass shell, allowing VAN to appear luminous and dimensional while remaining legible.

---

## 3. DIAL Glass Design Language

The system should use a branded glass treatment rather than generic glassmorphism.

### DIAL Glass base

- Base tint: translucent charcoal / deep navy.
- Background opacity: approximately 55–72%.
- Backdrop blur: approximately 18–28 dp.
- Border: 1 dp cyan-white edge at low opacity.
- Corner radius: 18–24 dp.
- Inner highlight: restrained top-left glass sheen.
- Shadow: shallow, soft, spatial.
- Active glow: cyan only around interactive edges.
- Surface depth: subtle layered translucency rather than strong blur.
- Avoid milk-white or frosted-light glass styles.

The overall visual impression should be:

**dark glass + blue energy + crisp character + restrained neon**

---

## 4. Floating VAN Composition

The compact floating VAN should not be trapped inside a rectangular card.

Recommended composition:

```text
      VAN head / torso
          ↑
    partly outside glass

  ┌──────────────────┐
  │ translucent glass│
  │ status + actions │
  └──────────────────┘

       floating orb
```

### Composition rules

- VAN may visually overlap or break the edge of the glass shell.
- The orb companion may float partly outside the card.
- Character remains the primary focal point.
- Glass remains visually secondary.
- Quick controls should never visually dominate VAN.
- Compact surface should occupy minimum practical screen area.
- Draggable and dockable behaviour must remain obvious.

---

## 5. Compact Floating State

Default floating mode should show:

- VAN character.
- Blue electrical aura.
- Orb companion.
- Optional compact status text.
- 1–3 immediate quick actions.
- Glass capsule or compact glass rail.
- Drag/dock affordance.
- Tap target to expand Command Centre.

### Recommended geometry

- Character: approximately 72–112 dp visual height depending on display mode.
- Glass capsule: adaptive around state controls.
- Touch target: minimum 48 dp.
- Edge docking: character may partially tuck to screen edge.
- Orb can indicate state without increasing panel size.

---

## 6. State-Specific Visual Behaviour

### IDLE

- Aura: low-intensity cyan halo.
- Slow, subtle breathing/pulse.
- Glass opacity: medium-low.
- Minimal shadow.
- Orb neutral and softly lit.

### LISTENING

- Aura becomes brighter and slightly wider.
- Thin electrical arcs may travel around visor, shoulders, and orb.
- Glass edges brighten.
- Waveform appears behind or below VAN.
- Avoid pulsing the entire screen.

### THINKING

- Aura becomes concentrated around visor/head/orb.
- Slow moving light refraction across glass.
- Optional subtle particles around orb.
- Glass remains calm and neutral.
- No distracting rapid animation.

### WORKING / EXECUTING

- Aura increases in energy and activity.
- Occasional cyan micro-arcs between VAN and orb.
- Slightly denser glass opacity.
- Holographic task/progress element may appear.
- Motion should imply purposeful execution rather than visual noise.

### SUCCESS

- Cyan aura returns toward baseline.
- Green success accent appears as secondary highlight.
- Glass remains consistent.
- VAN may perform a short confirm gesture.
- Success glow should be brief.

### WARNING

- Aura partially shifts toward amber/red accenting.
- Main VAN identity remains cyan/blue.
- Glass border becomes more opaque.
- Warning copy receives higher contrast.
- Avoid visually ambiguous mixed states.

### APPROVAL REQUIRED

- Glass becomes more solid for readability.
- Approval controls must be opaque enough to prevent accidental taps.
- Red/amber edge emphasis.
- Aura restrained to keep action controls dominant.
- Destructive or irreversible actions must visually distinguish themselves.

### OFFLINE / DEGRADED

- Aura dims.
- Orb brightness reduced.
- Glass loses some cyan edge light.
- VAN remains visible and recognisable.
- Degraded state should not look broken or corrupted.

---

## 7. Aura System Specification

The blue electrical aura should be implemented as a layered effect rather than one heavy glow.

### Recommended layers

1. **Core rim glow**
   - 2–6 px equivalent.
   - Cyan/blue.
   - Closely follows character silhouette.

2. **Secondary bloom**
   - Larger blur radius.
   - Low opacity.
   - Provides spatial separation from glass/background.

3. **Electrical filaments**
   - Sparse.
   - Short-lived.
   - State-driven.
   - Never continuous everywhere.

4. **Micro-sparks**
   - Very low frequency at idle.
   - Increased during active execution.

5. **Ground/hover glow**
   - Optional under feet/body.
   - Soft elliptical cyan illumination.

6. **Orb link**
   - Occasional short energy bridge between VAN and orb.
   - Strongest during working/listening states.

### State intensity guidance

| State | Aura intensity | Arc activity |
|---|---:|---:|
| Idle | 20–30% | Minimal |
| Listening | 45–60% | Moderate |
| Thinking | 35–50% | Low / concentrated |
| Working | 60–75% | Moderate-high |
| Success | 35% | Brief |
| Warning | 40% + alert accent | Low |
| Approval | 30% | Minimal |
| Offline | 10–15% | None |

---

## 8. Glass Surface Tokens

Suggested initial design tokens:

```text
vanGlass.backgroundAlpha      = 0.62
vanGlass.blur                 = 24dp
vanGlass.borderWidth          = 1dp
vanGlass.borderAlpha          = 0.22
vanGlass.cornerRadius         = 22dp
vanGlass.innerHighlightAlpha  = 0.10
vanGlass.shadowElevation      = 8dp
vanGlass.activeGlowAlpha      = 0.28
```

These are starting values and should be tuned against actual Android screenshots and Visual Authority references.

---

## 9. Compose Implementation Contract

Suggested reusable component:

```kotlin
VanGlassSurface(
    blur = 24.dp,
    backgroundAlpha = 0.62f,
    borderAlpha = 0.22f,
    cornerRadius = 22.dp,
    glowIntensity = state.glow,
    auraIntensity = state.aura
)
```

Recommended state model:

```kotlin
data class VanVisualState(
    val glassOpacity: Float,
    val glassBlurDp: Float,
    val borderIntensity: Float,
    val auraIntensity: Float,
    val arcActivity: Float,
    val alertAccent: AlertAccent?,
    val reducedMotion: Boolean
)
```

---

## 10. Performance Strategy

Real-time blur must not compromise floating-assistant responsiveness.

### Preferred rendering order

1. Android/app background.
2. Backdrop blur sampling.
3. Tinted glass surface.
4. Glass border/highlight.
5. Aura bloom.
6. Electrical filaments.
7. VAN character render.
8. Orb.
9. Text and controls.

### Performance fallback

If real-time blur becomes expensive:

- Disable live backdrop blur.
- Use a pre-tinted translucent navy surface.
- Preserve borders, radii, depth, and glow.
- Keep VAN and aura unchanged.
- Keep all interaction geometry identical.

The visual hierarchy must survive reduced rendering capability.

---

## 11. Battery and Thermal Behaviour

VAN should automatically reduce decorative effects when:

- Battery saver is enabled.
- Device becomes thermally constrained.
- App is in low-power overlay mode.
- Frame budget drops below target.

Fallback order:

1. Reduce filament frequency.
2. Reduce bloom radius.
3. Disable animated refraction.
4. Disable live blur.
5. Keep static cyan rim glow.
6. Never remove critical state indicators.

---

## 12. Accessibility

### Reduced Motion

When Android reduced-motion settings are active:

- Stop idle aura pulsing.
- Remove animated refraction.
- Replace electrical arc animation with static glow.
- Keep waveform only when materially useful.
- Use opacity/state transitions instead of motion.

### Contrast

- Text should never rely on translucency alone.
- Approval/warning actions require strong contrast.
- Glass must become more opaque over visually noisy backgrounds.
- VAN's face and eye/visor area must remain high-contrast.

---

## 13. Interaction Rules

### Tap

- Tap VAN → expand Command Centre.
- Tap orb → configurable quick action or assistant status.
- Tap glass action → execute only that bound action.

### Drag

- Drag VAN and attached glass shell together.
- Aura should lag very slightly for physicality, but not enough to feel sluggish.
- Docking animation should remain short and deterministic.

### Dock

- VAN may partially hide at screen edge.
- Aura compresses with character.
- A small cyan line/halo remains visible to indicate presence.
- Glass controls collapse when docked.

---

## 14. Command Centre Integration

When VAN expands into the full Command Centre:

- Glassmorphism can remain as the top-level material language.
- Panels should use more opaque glass than the floating compact surface.
- Character remains present but does not dominate operational content.
- Project status, commands, approvals and tool outputs use structured cards.
- Critical actions switch from translucent to solid controls.

---

## 15. Brand Consistency

The glass system must remain aligned with VAN's existing Visual Authority:

- Silver/white swept hair.
- Cyan/blue visor.
- Blue eyes.
- Black/white technical jacket.
- Cyan energy accents.
- Medium-brown skin.
- Floating orb companion.
- Friendly, capable, intelligent personality.
- No unauthorised character variants.

The new glass treatment is an **interface evolution**, not a character redesign.

---

## 16. Visual Acceptance Criteria

The design is accepted only if:

- VAN remains immediately recognisable at small sizes.
- Character detail remains crisp over all backgrounds.
- The blue electrical aura is visible but controlled.
- Glass never reduces readability.
- Quick actions remain obvious and tappable.
- Warning and approval states are unmistakable.
- Reduced-motion mode remains visually complete.
- Battery/performance fallbacks preserve the same layout hierarchy.
- No state relies only on colour.
- VAN still appears more important than the surrounding UI.

---

## 17. Canonical Visual Rule

The production look should be:

> **A crisp, solid VAN floating in front of a dark translucent DIAL glass shell, surrounded by a restrained blue electrical aura, with his orb companion and state-driven cyan energy effects.**

The aura should make VAN feel alive, intelligent, powerful, and always present, while the glass surface keeps the assistant modern, lightweight, and integrated with whatever is underneath on the user's phone.

---

## 18. Final Design Decision

**Approved direction:**

- Keep VAN's existing 3D character identity.
- Add premium DIAL glassmorphism to floating and expanded interaction surfaces.
- Preserve the blue electrical aura as a canonical character effect.
- Increase aura intensity contextually rather than constantly.
- Keep Hermes/VAN operational information readable and deterministic.
- Provide low-power and reduced-motion fallbacks.
- Treat glass and aura as production design systems with explicit tokens and state rules, not decorative one-off effects.

