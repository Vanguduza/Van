# VAN Rive Export Checklist

Before every core/full export:

- Artboard is exactly `Van`; state machine exactly `VanRuntime`.
- Public input and trigger surface exactly matches `rive_contract.json`.
- Rive Editor version equals the pin in `docs/character_forge/TOOLS.yaml`.
- Candidate is exported under `09-rive-working/`.
- Packaging receipt records candidate SHA, SVG SHA, contract SHA, editor version, Rive file
  id/revision and artist.
- Candidate enters only `src/androidTest/assets` / `src/debug/assets`; never production.
- After M2 PASS, do not restructure bones/meshes/constraints. A structural change reopens M2.
