# VAN Rive Export Checklist

Before every core/full export:

- Artboard is exactly `Van`; state machine exactly `VanRuntime`.
- Public input and trigger surface exactly matches `rive_contract.json`.
- Built by the Rive CLI version pinned in `docs/character_forge/TOOLS.yaml` (Rev 2.1) from an
  RML project under `09-rive-working/rml/`.
- Candidate is placed under `09-rive-working/` with a new number; candidates are immutable.
- Packaging receipt records candidate SHA, SVG SHA, contract SHA, Rive CLI version, the RML
  project and its source-tree digest, Rive file id/revision (`LOCAL` for CLI builds) and author.
- The RML project is committed with the candidate so the digest can be recomputed.
- Candidate enters only `src/androidTest/assets` / `src/debug/assets`; never production.
- After M2 PASS, do not restructure bones/meshes/constraints. A structural change reopens M2.
