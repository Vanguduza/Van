# VAN Character Forge CLI

Authority: `docs/character_forge/VAN_CHARACTER_FORGE_DEVELOPMENT_PACK_REV_2.md` plus the Rive CLI authoring supplement in `docs/character_forge/VAN_CHARACTER_FORGE_RIVE_CLI_SUPPLEMENT_REV_2_1.md`.

This tooling makes the art pipeline deterministic. It never grants itself owner authority and never treats tool installation as artwork or device evidence.

Execution path:

1. Bootstrap and qualify the Netcup Character Forge workstation.
2. Import its exact toolchain lock with `tools import-lock` (exact repository SHA, the repository-pinned Rive CLI release, bare Inkscape version); M1/M2 remain blocked while unpinned.
3. Run `source admit`; the owner separately confirms the source set.
4. Run `gate m0`.
5. Produce and admit `van_layers.svg`.
6. Build core/full Rive candidates with the pinned Rive CLI from RML under `09-rive-working/rml/` and record a receipt using `--authoring-version` and `--source-project`.
7. Stage candidates only into androidTest/debug, push, download the `van-character-forge-validation-binding` (and screenshots) artifacts and run `rive record-validation`; it accepts only the CI-stated outcome for that exact run, SHA and commit.
8. The owner performs the core verdict; an independent reviewer records the full-rig verdict.
9. `android integrate` refuses anything other than the M3-qualified exact candidate.
10. Complete production CI, S24 physical evidence and biometric owner acceptance.
11. `release promote` refuses until M4 is genuinely green.

Commander may operate source admission, preparation, Rive tooling, emulator validation, CI-support operations and toolchain import through the bounded worker. It cannot perform owner confirmation, owner verdict, biometric acceptance or release promotion.

Until a real `.riv` exists, instrumentation reports `NO_RIVE_ASSET` rather than treating absence as a pass.
