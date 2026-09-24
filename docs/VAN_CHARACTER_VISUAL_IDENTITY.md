# VAN Character Visual Identity

Status: LOCKED CANONICAL — revision R2 (CF-D-05-REV2_1, 2026-09-24)

Primary visual authority: `visual-authority/character-forge/01-master-candidates/van_master_source_candidate_b.png`
(Candidate B, native 1536×1024). The original owner board is kept as history only.

## Canonical Van

- Silver/white swept, spiky hair (never dark hair)
- Clear cyan/blue wraparound goggle visor with dark side pods and cyan trim
- Medium-brown skin; canonical token `#AF6A53` measured on Candidate B (ΔE2000 tolerance ≤ 8)
- Large blue eyes
- Black/white technical jacket
- Charcoal technical underlayer
- DIAL cyan accents
- Compact chibi proportions: 3.2 ± 0.3 heads tall, measured hair crown to chin over crown to sole
- Expressive face; black technical gloves on both hands
- Technical hood/collar; no headband
- Floating dark orb companion with two vertical cyan bar eyes (no mouth)
- Hair, skin, eyes and clothing optically opaque; only visor/orb optical layers may be translucent

## Forbidden substitutions

- Dark hair
- Light/peach skin family
- Any headband or headband branding
- Bare/skin-coloured hands in place of the locked black technical gloves
- Tall realistic proportions (more than ~3.5 heads)
- The superseded cyan smiling-face orb
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

The owner-supplied boards remain stored unmodified under `visual-authority/assets/pack/`. Since
CF-D-05-REV2_1 the **sole primary character image authority** is Candidate B,
`visual-authority/character-forge/01-master-candidates/van_master_source_candidate_b.png` (Git blob `c925dcdbe7f05aa89eac862f2e258549fe5a49d4`). The original
`visual-authority/assets/pack/owner_board_visual_authority.png` (Git blob
`fc18bbe0b91e5b85d8cf8211314a69cb90b8bc0b`) is kept as history and no longer defines identity. The former light-skinned/headband lock sheet,
procedural placeholder sheets and their derived crops are rejected, deleted and denylisted by the
Character Forge approved asset pack. Other owner boards are context-only and cannot override
Candidate B or `APPROVED_IDENTITY_LOCK.yaml`.

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
