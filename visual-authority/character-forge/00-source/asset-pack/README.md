# VAN Rive Build Input Asset Pack

This directory is the deterministic input bundle for the VAN Character Forge Rive build.

It is **not a new visual authority**. It compiles the existing owner/canonical sources into
machine-readable build instructions so Commander/ChatGPT/Rive CLI can build without inventing
identity, public inputs, state/action values, or Android-owned visual effects.

Authority order:
1. owner visual lock sheet and owner boards in `visual-authority/assets/`
2. `visual-authority/rive_contract.json`
3. `docs/VAN_CHARACTER_VISUAL_IDENTITY.md`
4. `docs/VAN_VISUAL_ACCEPTANCE_MATRIX.md`
5. `visual-authority/van-visual-authority-v2.yaml`
6. this compiled asset pack
7. existing Canvas/motion implementation as reference only

Source images remain in `visual-authority/assets/`; Rev 2 forbids duplicating/copying them here.
The Forge source-admission command records their SHA-256 before M0. Git blob SHAs in this pack
identify the repository objects before that admission step.

The actual M1 art deliverable remains:
`visual-authority/character-forge/06-vectors-clean/van_layers.svg`

The Rive authoring work consumes that SVG plus the files in this directory and produces candidates
under `09-rive-working/`.

Hard exclusions from the .riv:
- Android-native aura/electrical field
- glass workboard/UI chrome
- full-artboard glow/particles/background
- extra public inputs or triggers
- per-state duplicate character rigs

Use `RIVE_AGENT_BRIEF.md` as the Commander/agent entry point.
