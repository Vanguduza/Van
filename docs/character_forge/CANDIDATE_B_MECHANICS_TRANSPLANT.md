# Candidate B Mechanics Transplant

Candidate B remains VAN's sole character identity. This lane borrows **interaction and rigging patterns only** from reusable Rive character examples; no third-party character artwork or Rive asset bytes are imported.

The prototype decomposes Candidate B into body, head, left forearm, right forearm and orb, deterministically traces those cut-outs into non-canonical vectors, and authors them into the existing `Van / VanRuntime` contract. It exposes all 18 durable states, all 14 finite actions and the five locked visemes. The existing Android-native aura remains outside Rive.

The architecture deliberately separates three runtime layers: durable pose, finite action, and speech/viseme. This follows the reusable pattern found in the reference rigs while preserving VAN's existing numeric state/action authority and exact public input/trigger surface.

The generated prototype under `08-prototypes/candidate-b-mechanics/` is evidence that the mechanics can be authored around Candidate B. It is **not** M1 semantic vector admission and cannot be promoted to the shipping `van.riv`. Production still requires the reviewed `06-vectors-clean/van_layers.svg`, M2 skeleton/mesh review, M3 full animation review, emulator/CI evidence, physical S24 qualification and owner release.

The prototype path is intentionally useful: its vector traces and state-machine structure can be inspected, compared and harvested during M1/M2, while production reviewers retain the right to redraw or replace every traced shape that does not meet Candidate B's identity/silhouette thresholds.
