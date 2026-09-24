# VAN Character Forge CLI

Authority: `docs/character_forge/VAN_CHARACTER_FORGE_DEVELOPMENT_PACK_REV_2.md` plus the Rive CLI authoring supplement in `docs/character_forge/VAN_CHARACTER_FORGE_RIVE_CLI_SUPPLEMENT_REV_2_1.md`.

This tooling makes the art pipeline deterministic. It never grants itself owner authority and never treats tool installation as artwork or device evidence.

Execution path:

1. Bootstrap and qualify the Netcup Character Forge workstation.
2. Run `sudo -n -u vanforge /usr/local/libexec/van-character-forge-worker asset-pack-check`. Do not begin vector/Rive authoring if it fails.
3. Import its exact toolchain lock with `tools import-lock`; M2 remains blocked while Rive CLI is unpinned.
4. Run `source admit`; the owner separately confirms the source set.
5. Run `gate m0`.
6. Produce and admit `van_layers.svg`.
7. Build core/full Rive candidates with the pinned Rive CLI and record a receipt using `--authoring-version`.
8. Stage candidates only into androidTest/debug, push, and record exact CI evidence.
9. The owner performs the core verdict; an independent reviewer records the full-rig verdict.
10. `android integrate` refuses anything other than the M3-qualified exact candidate.
11. Complete production CI, S24 physical evidence and biometric owner acceptance.
12. `release promote` refuses until M4 is genuinely green.

Commander may operate source admission, preparation, Rive tooling, emulator validation, CI-support operations and toolchain import through the bounded worker. It cannot perform owner confirmation, owner verdict, biometric acceptance or release promotion.

Until a real `.riv` exists, instrumentation reports `NO_RIVE_ASSET` rather than treating absence as a pass.
