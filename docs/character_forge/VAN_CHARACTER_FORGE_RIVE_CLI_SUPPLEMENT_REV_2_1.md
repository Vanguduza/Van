# VAN Character Forge — Rive CLI Authoring Supplement, Rev 2.1

Status: toolchain-authority supplement to Rev 2. Identity, owner authority, milestone gates, S24 evidence and release rules from Rev 2 remain unchanged.

## Decision

The Linux x86_64 Rive CLI is the deterministic M2/M3 build authority on Netcup DIAL control. The Rive Editor remains an optional human visual-review lane, not a Linux build dependency.

The Netcup workstation must be capable of producing, inspecting and validating the real `.riv` candidate without requiring an unrelated desktop workstation.

## Commander authority

Character Forge runs under a dedicated `vanforge` user. Desktop Commander receives no generic root or `vanforge` shell. It may invoke only the bounded `/usr/local/libexec/van-character-forge-worker` surface through sudo.

The worker exposes deterministic preparation, Rive, Android/emulator and qualification operations. Owner-only actions remain outside that surface: source-set confirmation, core visual verdict, physical S24 checklist completion and biometric final acceptance.

## Workstation contents

The bootstrap installs and qualifies:

- Rive CLI from Rive's official installer.
- Inkscape, Potrace, VTracer and rembg + BiRefNet General.
- ImageMagick, FFmpeg and Blender.
- Chrome + Xvfb for optional web-Editor review.
- Java 17.
- Android command-line tools, platform-tools, platform 36/build-tools 36, Android Emulator, an API-31 Google APIs x86_64 image and a dedicated Forge AVD.
- Exact-SHA VAN checkout and a machine-readable toolchain lock.
- A bounded Commander worker and fail-closed qualifier.

## Truth rule

Bootstrap success means only `AUTHORING_WORKSTATION_READY`. It must never set owner confirmation, validation PASS, device qualification, owner acceptance or `QUAL-EMB-01=READY`.
