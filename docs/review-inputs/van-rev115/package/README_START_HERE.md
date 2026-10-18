# VAN Next integrated blueprint — Rev1.16

The owner’s experience-learning requirement is now part of the active blueprint and machine plan, not a pending companion. Start with `CANONICAL_AUTHORITY.json`.

- Master: `VAN_NEXT_UNIFIED_REBUILD_BLUEPRINT_REV1_16_20261018.md`.
- Focused architecture: `VATI_SELF_OPTIMIZING_EXECUTION_AND_CRYPTO_BLUEPRINT_REV4_20261018.md`, especially normative §8.6.
- Single schedule: `plan/DEVELOPMENT_PLAN.json`, rendered as `plan/VAN_NEXT_DETERMINISTIC_PLAN_REV1_16.md`.
- Integrated additions: `traceability/REV116_REQUIREMENTS.json` and `verification/REV116_ACCEPTANCE_CONTRACTS.json`; the main registries contain every addition.
- Evidence records, commands, API mappings and actual consumer obligations: `contracts/self_optimization/EXPERIENCE_LEARNING_CONTRACT.json`, its strict `EXPERIENCE_LEARNING_RECORDS.schema.json` and synthetic examples.
- Owner screens: `design/ALL_SURFACE_CONTRACTS.json` explicitly references `design/EXPERIENCE_LEARNING_CONTEXT_BINDINGS.json`.

Active scope is **316 requirements / 1,586 planned application tests**: all 309 / 1,544 Rev1.15 objects unchanged plus seven requirements and 42 positive/adverse/recovery contracts covering the 14 original owner scenarios. All 131 unit IDs/dependencies, 234 context objects, 349 actions and locked visuals are preserved. The same backend-first gate remains. All application tests are NOT_RUN, implementation units NOT_STARTED and F15/BG NOT_ISSUED.

The revision defines both strategy and execution improvement loops, evidence-based trade diagnosis, protected statistical confirmation, unknown/inconclusive outcomes, scoped adaptation, monitoring and recovery. It guarantees neither profit nor unique causal explanations for individual trades. Proposed API paths require real handlers, native authority and Android caller qualification before backend completion.

Historical Rev1.15 blueprint/plan files and receipts retain their old names and scope. Only the authority selector identifies the active documents. The exact Rev1.14 parent ZIP is retained; the previous Rev1.15.1 delivery remains in Git at `270d077b978d785b186b46b208a97ba188fad1a2`. `lineage/REV115_OBJECT_FINGERPRINTS.json` anchors unchanged inherited objects to the preceding publication. No new branch-wide source audit, application run or native runtime qualification is claimed.

Document checks (Python 3 and jsonschema):

```sh
python3 -B plan/render_plan.py --check
python3 -B verification/verify_rev116.py --json
python3 -B verification/verify_rev116.py --selftest --json
python3 -B verification/verify_review_contracts.py
python3 -B verification/verify_experience_learning.py
python3 -B verification/verify_rev116.py --check-package --json
```

Current receipts: `evidence/rev116/final_checks/`. Historical results under `evidence/rev115/` remain dated evidence. Refresh generated acceptance references with `plan/render_plan.py --sync-acceptance`, then unsigned fingerprints, rendered plan and manifest; no generated hash issues authority.
