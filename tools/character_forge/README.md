# VAN Character Forge CLI

Authority: docs/character_forge/VAN_CHARACTER_FORGE_DEVELOPMENT_PACK_REV_2.md.

This tooling makes the art pipeline deterministic. It never authors or accepts artwork by itself.

Execution path:
1. Run source admit.
2. Owner confirms the source set in MANIFEST.yaml.
3. Run gate m0.
4. Artist creates and admits van_layers.svg.
5. Artist exports core/full Rive candidates and records packaging receipts.
6. Stage candidates only into androidTest/debug, push, and use CI evidence.
7. Owner performs the core verdict and final biometric acceptance.
8. android integrate refuses an unvalidated candidate.
9. release promote refuses until M4 is genuinely green.

Until a real .riv exists, instrumentation reports NO_RIVE_ASSET rather than treating absence as a pass.
