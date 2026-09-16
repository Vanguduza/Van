# VAN Visual Production System — Rev 2.2 Addendum
## Aura Semantic Envelope & Trade-State Expansion Patch

**Product:** VAN — DIAL Owner Operator  
**Document type:** Focused corrective addendum to Rev 2.1  
**Revision:** 2.2 Addendum A  
**Date:** 2026-09-16  
**Status:** Owner-directed correction patch  
**Purpose:** Fix the remaining aura limitation by introducing a larger, more expressive **outer semantic field** that can support restrained state semantics and future trade-state signalling without crowding the character.

---

# 1. Why this addendum exists

The current corrected visuals are improved relative to the earlier previews, but the aura still remains too close to VAN's body. The result is:

- insufficient spatial separation between identity glow and semantic signalling;
- weak room for restrained state differentiation;
- limited capacity for future trade-state colours and semantics;
- over-reliance on icons and lower glass strips for alert/approval/urgent meaning;
- visual compression in reduced-motion and low-budget variants.

The core correction is:

> The aura must no longer be treated as one body-hugging decorative system.  
> It must become a **three-zone field architecture** with an explicit **outer semantic envelope**.

---

# 2. New rule: three-zone aura architecture

VAN's aura is now divided into three functional zones.

## 2.1 Zone A — Inner Presence Field
**Role:** identity / presence / silhouette support

This is the close field around the head, shoulders, upper torso, visor and orb.

### Purpose
- separate VAN from the background;
- preserve brand identity;
- maintain soft premium liveliness;
- protect readability of the face and eyes.

### Colour policy
- predominantly DIAL cyan / blue;
- minimal semantic colour contamination;
- stable across most states.

### Behaviour
- soft;
- compact;
- body-adjacent;
- restrained motion;
- low semantic burden.

---

## 2.2 Zone B — Mid Interaction Field
**Role:** operational activity / task coupling / state behaviour

This contains:
- filaments,
- working arcs,
- orb coupling,
- hologram interaction,
- listening/searching/working motion signatures.

### Purpose
- show VAN is doing something;
- connect visor, orb and task surfaces;
- express activity class.

### Behaviour
- asymmetrical;
- more animated than Zone A;
- still visually attached to VAN;
- not the primary carrier of critical semantic colour.

---

## 2.3 Zone C — Outer Semantic Envelope
**Role:** restrained state semantics / future trade-state signalling

This is the missing visual layer.

### Purpose
- carry state emphasis at a greater radius from the body;
- hold warning/success/urgent/attention colour without repainting VAN;
- support future trading semantics;
- remain readable even in reduced motion / low effect budgets.

### Form
The outer semantic envelope is **not**:
- a full ring,
- a circular halo,
- a thick border,
- a second card outline.

It **is**:
- a sparse broken orbit;
- segmented brackets/arcs;
- contour fragments;
- subtle nodes or light anchors;
- a non-closed semantic lane.

### Design principle
The outer semantic envelope must have enough air around VAN to communicate meaning without interfering with body readability.

---

# 3. Geometry changes

## 3.1 Effective radius expansion
Do not scale the entire aura uniformly.

Instead:

- Zone A remains close to current body-adjacent size;
- Zone B remains moderate;
- Zone C expands outward to approximately **1.35×–1.70×** the effective current arc radius.

## 3.2 Spacing rule
There must be a visible gap between:
- the character silhouette / close aura (Zones A+B),
- and the outer semantic envelope (Zone C).

This gap creates semantic breathing room.

## 3.3 Composition rule
Zone C must visually frame VAN without becoming an enclosing ring.
It should feel like:
- a structured field,
- a semantic orbit,
- a restraint system for meaning,
not a full enclosure.

---

# 4. Updated aura token model

```yaml
aura_v2_2:
  inner_presence:
    radius_scale: 1.00
    alpha_idle: 0.12
    alpha_active: 0.20
    colour_mode: dial_identity
  mid_interaction:
    radius_scale: 1.12
    alpha_idle: 0.10
    alpha_active: 0.22
    filament_count_full: [2, 5]
    arc_count_full: [1, 4]
    colour_mode: activity_weighted_identity
  outer_semantic:
    radius_scale_min: 1.35
    radius_scale_max: 1.70
    alpha_idle: 0.08
    alpha_active: 0.18
    segment_count_full: [1, 4]
    max_total_coverage_degrees: 180
    full_ring_forbidden: true
    allow_local_nodes: true
    colour_mode: semantic
    minimum_gap_from_mid_field_dp: 8
```

These values are initial implementation targets. Tune only through visual acceptance, not arbitrary taste edits.

---

# 5. Colour-separation rule

## 5.1 Identity colour stays near the body
DIAL cyan/blue remains the primary colour of:
- character presence,
- visor baseline,
- orb baseline,
- inner presence field.

## 5.2 Semantic colour lives primarily in the outer envelope
Semantic colours should be applied primarily to Zone C and secondarily to localized Zone B accents where needed.

This allows the system to:
- preserve VAN's brand identity;
- avoid muddy recolouring of the silhouette;
- support more semantic classes in future.

## 5.3 Prohibition
Do not globally recolour the whole aura for every semantic state.
Do not flood Zone A with warning/red/green unless a deliberate exceptional state requires it.

---

# 6. State topology upgrade

Every state must now differ not only by icon/prop, but by **field topology**.

## 6.1 IDLE
- Zone A: quiet cyan presence
- Zone B: one or two calm fragments
- Zone C: very low semantic activation, sparse contour

## 6.2 CONNECTING
- Zone A: emerging stable presence
- Zone B: scan-like growth
- Zone C: one forming semantic fragment, low opacity

## 6.3 ATTENTIVE
- Zone C: slight forward-facing semantic bracket or lifted fragment
- tighter directionality than idle

## 6.4 LISTENING
- Zone B: audio-responsive rhythm
- Zone C: lifted lateral or upper-right bracket
- maintain calm, not noisy equaliser overload

## 6.5 THINKING
- Zone B: inward-contour logic
- Zone C: contemplative partial orbit, often upper-right / right-side bias
- restrained, not busy

## 6.6 SEARCHING
- Zone B: directional scan sweep
- Zone C: one exploratory forward arc or semantic sweep
- can suggest outward probing

## 6.7 WORKING
- Zone B: highest task coupling
- Zone C: stronger support frame with more fullness
- maintain restraint

## 6.8 DELEGATING
- Zone C: lightly branched or multi-node semantic structure
- signal outward coordination

## 6.9 SPEAKING
- Zone B: supportive conversational motion
- Zone C: calm outer frame, light activity only

## 6.10 WAITING
- Zone C: reduced activation, suspended expectation

## 6.11 WAITING_FOR_OWNER
- Zone C: amber semantic lane segments, clearly framing owner-attention state
- lower glass strip may remain, but Zone C should now do more of the semantic work

## 6.12 DEGRADED
- Zone C: partially diminished or interrupted semantic orbit
- maintain premium stillness, not visual collapse

## 6.13 WARNING
- Zone C: amber caution bracket / localized lane activation
- do not rely only on icon + strip

## 6.14 ERROR
- Zone C: red interrupted semantic contour
- stronger break / failure topology than warning

## 6.15 SUCCESS
- Zone C: green release / confirmation arc
- clean and celebratory, but restrained

## 6.16 URGENT
- Zone C: sharper red semantic brackets, more direct frontal emphasis
- distinct from warning and error

## 6.17 OFFLINE
- Zone C: almost absent or dim neutral remnant

## 6.18 SLEEPING
- Zone C: nearly absent, very soft stable remnant
- distinct from offline by warmth/restfulness, not by heavy colour

---

# 7. Trade-state-ready semantic architecture

This addendum reserves the outer semantic envelope for future trading semantics.

## 7.1 Principle
Trade-state semantics must live primarily in Zone C.
VAN's core identity must remain recognizable and stable.

## 7.2 Suggested trade semantic families

These are not mandatory labels, but the architecture must support them:

- **watching / monitoring** → cool teal-cyan semantic envelope
- **setup forming** → blue-violet envelope
- **entry opportunity** → focused gold / amber semantic envelope
- **in trade / active position** → stronger directional state framing
- **profit / target hit** → green semantic confirmation arc
- **risk rising** → amber-red mixed caution envelope
- **stop / invalidation / failure** → red interrupted envelope
- **urgent intervention** → vivid direct red segmented brackets
- **hedged / multi-signal / complex strategy** → carefully restrained dual-accent semantic nodes
- **paused / no-trade / guarded state** → low-activity dimmed semantic lane

## 7.3 Constraint
Trade semantics must not convert VAN into a rainbow assistant.
The character body remains identity-led; the outer semantic envelope carries the complexity.

---

# 8. Reduced motion / low budget / static requirements

## 8.1 Reduced motion
Reduced motion must preserve Zone C in static form.
Even with motion disabled, the semantic envelope remains visible and interpretable.

## 8.2 Low effect budget
Low budget may:
- reduce filament count,
- reduce arc count,
- remove deformable refraction,
- remove live blur,
but it must **retain at least one readable semantic envelope fragment**.

## 8.3 Static
Static mode must still preserve:
- inner presence;
- one or more outer semantic segments;
- state readability;
- separation between identity and semantic meaning.

---

# 9. Board corrections required

## 9.1 State matrix boards
Revise the following boards:
- 18 durable states;
- reduced motion;
- low effect budget.

For each:
- increase field breathing room;
- make Zone C visibly legible;
- ensure state topology diversity;
- reduce dependence on lower solid strips/icons for meaning.

## 9.2 Add a new board
Create a new authority board:

```text
VAN aura topology & semantic ladder
```

This board must show:

- Zone A / Zone B / Zone C labelled;
- state semantic examples;
- effect budget degradation across FULL / REDUCED / REDUCED_MOTION / LOW / STATIC;
- trade-state capability examples.

## 9.3 Glass/effect ladder note
Keep the existing glass/effect ladder board, but note that it no longer fully explains the aura system.
It must be paired with the aura-topology board.

---

# 10. Acceptance criteria for this patch

This addendum passes only if:

1. the aura no longer appears primarily body-hugging;
2. there is clearly more semantic breathing room around VAN;
3. warning/error/urgent/waiting-for-owner are more distinguishable through field architecture;
4. reduced motion and low budget retain semantic readability;
5. future trade-state colours can be added without recolouring the body/identity field;
6. the outer semantic envelope is visible but elegant;
7. the solution does not become a full ring or cluttered multicolour orbit.

---

# 11. Anti-patterns — forbidden

The following fail this addendum:

- scaling the whole aura outward uniformly without separating zones;
- using a thicker/glowier version of the current arcs and calling it solved;
- turning Zone C into a complete ring;
- placing semantic colour everywhere around the body;
- introducing too many segments so the field becomes noisy;
- making trade-state support depend on icons only;
- making reduced motion collapse back into body-only aura.

---

# 12. Final instruction

The next correction iteration must implement:

> **Inner Presence Field + Mid Interaction Field + Outer Semantic Envelope**

That is the required architecture for:
- clean state readability,
- restrained semantic colours,
- future trade-state integration,
- and a truly scalable VAN aura system.
