# VAN Character Visual Identity

Status: LOCKED CANONICAL

## Canonical Van

- Silver/white swept hair (never dark hair)
- Cyan/blue transparent visor
- Medium-brown skin
- Blue eyes
- Black/white technical jacket
- Charcoal technical underlayer
- DIAL cyan accents
- Compact friendly stylized proportions
- Expressive face and hands
- Floating cyan holographic orb companion

## Forbidden substitutions

- Dark hair
- Generic robot mascot
- Random unrelated character
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

The owner-supplied design boards are the visual authority for the shipped UI. They are stored
unmodified under `visual-authority/assets/pack/`, and the locked composition sheet is
`visual-authority/assets/owner_visual_lock_sheet.jpg`.

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
| 2 | `OWNER_ART` | Every pose in `VanArtPose` is packaged under `res/drawable-nodpi/` |
| 3 | `CANVAS` | Last resort — the procedural `VanScene` character |

A missing, undersized, unloadable or partially-packaged source always demotes to the next
renderer. A half-bound avatar would misrepresent Van's state, so it is never shown.

### Rive status

The authored `van.riv` artboard is **EXTERNAL and not delivered**. No artifact, preview or
document in this repository may report Rive as `READY`. `rive_contract.json` and its input
schema are unchanged — the contract is honoured by the Canvas and owner-art renderers so the
artboard can drop in without a code change.

### Interim Canvas character

`VanScene` is a renderer-independent draw program shared by the Compose overlay and the JVM
preview renderer, so a preview can never flatter the app. It is an interim embodiment, not
owner-accepted art, and it honours the identity lock element for element: spiked silver swept
hair, the dark VAN headband, cyan transparent visor over blue eyes, medium-brown skin,
black/white technical jacket over a charcoal underlayer, the DIAL cyan chest emblem, and the
navy orb companion with its lit cyan face.

The headband brand mark is rendered as a cyan tag rather than lettering: at a 72–112dp
character height the word would be sub-pixel, and painting unreadable glyphs would be a fake
detail.
