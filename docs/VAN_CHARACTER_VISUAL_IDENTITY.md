# VAN Character Visual Identity

Status: LOCKED CANONICAL

## Canonical Van

- Silver/white swept hair (never dark hair)
- Cyan/blue transparent visor
- Medium-brown skin; canonical sampled token `#A4654E` (ΔE2000 tolerance ≤ 8)
- Blue eyes
- Black/white technical jacket
- Charcoal technical underlayer
- DIAL cyan accents
- Compact human-stylized proportions: 5.75 heads tall ±0.25 (not three-head chibi)
- Expressive face; black technical gloves on both hands
- Technical hood/collar; no headband
- Floating cyan holographic orb companion
- Hair, skin, eyes and clothing optically opaque; only visor/orb optical layers may be translucent

## Forbidden substitutions

- Dark hair
- Light/peach skin family
- Any headband or headband branding
- Bare/skin-coloured hands in place of the locked black technical gloves
- Three-head chibi proportions
- Generic robot mascot
- Random unrelated character
- Glassified/translucent body
- Significant proportion / visor / jacket / hair silhouette changes without a new visual-authority revision

## Presentation modes

| Mode | Use |
|---|---|
| Compact avatar | Floating overlay |
| Expanded quick actions | Mid-size docked |
| Command Centre | Full composition |
| Offline / degraded | Explicitly muted/cyan-desaturated with status |
| Urgent / decision | Urgency cues without frantic motion or excessive glow |

Source of truth: `visual-authority/` plus this document and the Rive contract.

## Owner UI lock

The owner-supplied boards remain stored unmodified under `visual-authority/assets/pack/`. The **sole
primary character image authority** is
`visual-authority/assets/pack/owner_board_visual_authority.png` (Git blob
`fc18bbe0b91e5b85d8cf8211314a69cb90b8bc0b`). The former light-skinned/headband lock sheet,
procedural placeholder sheets and their derived crops are rejected, deleted and denylisted by the
Character Forge approved asset pack. Other owner boards are context-only and cannot override the
primary board or `APPROVED_IDENTITY_LOCK.yaml`.

The interaction shell around the character is specified by
`docs/VAN_GLASSMORPHIC_FLOATING_ASSISTANT_DESIGN.md`. Its canonical rule governs every visual
decision: **Van is the solid visual anchor; glass is the contextual interface around him.**
Glassmorphism is never applied to the character himself.

## Renderer order

Van is painted by the first source that can be trusted to show a truthful character.
`VanVisualRuntime.decide` fails closed in this order:

| Order | Renderer | Condition |
|---|---|---|
| 1 | `RIVE` | `van.riv` present, ≥ `MIN_ARTBOARD_BYTES`, runtime loadable, bind succeeds |
| 2 | `CANVAS` | Fail-closed interim procedural `VanScene` while accepted Rive art is absent |

`OWNER_ART` bitmap poses are retired because the packaged pose set was derived from rejected/low-resolution source material. The runtime must never select that rung.

A missing, undersized, unloadable or partially-packaged source always demotes to the next
renderer. A half-bound avatar would misrepresent Van's state, so it is never shown.

### Rive status

The authored `van.riv` artboard is **EXTERNAL and not delivered**. No artifact, preview or
document in this repository may report Rive as `READY`. `rive_contract.json` preserves the public input/state/action surface while its identity lock is
strengthened with the approved skin token, gloves, no-headband, proportions and opacity rules. The
Canvas fallback follows the same identity lock so the artboard can replace it without product drift.

### Interim Canvas character

`VanScene` is a renderer-independent draw program shared by the Compose overlay and the JVM
preview renderer, so a preview can never flatter the app. It is an interim embodiment, not
owner-accepted art, and it honours the identity lock element for element: spiked silver swept
hair, **no headband**, cyan transparent visor over blue eyes, medium-brown skin,
black/white technical jacket over a charcoal underlayer, black technical gloves, the DIAL cyan
chest emblem, and the navy/cyan orb companion. Any residual headband geometry in the Canvas or
minimized portrait is a defect, not an identity feature.
