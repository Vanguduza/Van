# VAN Next — Unified Rebuild Pack, Rev 1.11

**One canonical specification and one plan.** Consolidates Opus's current working source and Rev1.9b/OD0–39, your full backend-first instruction, Rev1.10's whole-product coverage, and the existing forecasting/prediction-research addendum. It retains useful implementations with explicit correction and admission requirements—not a blanket PR101 merge.

## Start here

- **Master:** `VAN_NEXT_UNIFIED_REBUILD_BLUEPRINT_REV1_11_20261017.md` — 3,427 lines, complete product/backend/design/correction specification.
- **Sole active plan:** `plan/VAN_NEXT_DETERMINISTIC_PLAN_REV1_11.md`, generated from `plan/DEVELOPMENT_PLAN.json`.
- **Implementation decisions:** `consolidation/OPUS_IMPLEMENTATION_DECISIONS.md` and machine admission register.
- **Exact repairs:** `contracts/CORRECTIVE_IMPLEMENTATION_CONTRACTS.md` — 20 mandatory contracts.
- **Every-screen design:** `design/ALL_SCREEN_TACTILE_SPECIFICATIONS.md` and machine contracts.
- **Continuation:** `OPUS_CONTINUATION_HANDOFF.md` and `CONSOLIDATION_APPLY_PROTOCOL.md`.

`CANONICAL_AUTHORITY.json` selects the operative master/plan. Older schedules in `lineage/` and nested research archives preserve evidence and original detail only. They cannot start work or issue a competing gate.

## Deterministic order

PRE-001 inventory → PRE-002 complete semantic/Product Truth reconciliation → independent PRE-003 F15 → **all 74 backend capability units in full** → **10 backend-verification units** → **BG-001 (VAN-PKT-088)** → full-product native UX/design beginning VAN-PKT-089 → all 23 frontend units → full qualification/physical S24 → controlled release and retirement.

These are logical development/qualification boundaries, not 74 mandated microservices. Headless integration catches problems during backend work. No new theme, UI shell, orb/chart renderer or native design prototype starts while a required backend capability remains incomplete. A backend omission discovered later reopens the gate; it is not implemented secretly in a screen.

## Preserved scope

77 current Opus VAN-NX requirements +18 backend-first clauses +90 forecast requirements +20 corrective requirements =**205 active requirements**. The 18 Product Truths, 93 earlier features, 171 source atoms, 78 historical surfaces and 349 owner actions retain traceable mappings. **228 context obligations** may share tabs/sheets/pages; they are not 228 top-level screens. Every relevant context adapts the same two locked tactile designs to its function.

The forecasting scope includes Qlib/LightGBM, admitted NeuralForecast models, Freqtrade/FreqAI reference patterns, dataset/target/model/calibration/evaluation governance, and prediction-market expectations and offline research labs. It does not add another live execution engine, new procurement or provider eligibility. No profitable strategy is promised; a truthful negative qualification result is supported.

## Evidence actually produced

On `van-trading-core` at exact head `a39f241b0135cf92cc5a6b9a28af226aa294603d`:43 focused trading tests passed; Opus plan/state checks reproduced;23/23 and24/24 original mutations caught. The new exported121-node graph passed with14/14 graph counterexamples caught. Paper-adapter probes independently reproduced both worse-than-limit fills and the24h-versus4h expiry discrepancy; those remain required fixes, not completed repairs.

Locally, the complete document/coverage validator caught52/52 deliberately broken inputs; news-readiness metadata caught12/12;18 forecast schemas and12 fixtures passed, with38/38 prediction fixture counterexamples caught. These are **document/fixture tests**, not application or economic qualification.

All **1,185 planned application acceptance obligations remain NOT_RUN**. F15 and BG remain NOT_ISSUED. No application code, production service, trading account, mandate, network configuration or protected branch was changed. The deliverable is a complete documentary consolidation candidate, not a fabricated signed freeze or deployment.

## Verify the pack

```sh
python3 verification/verify_package.py
python3 verification/verify_unified.py
python3 verification/verify_unified.py --selftest
python3 plan/render_plan.py --check
python3 verification/verify_graph_export.py --selftest
python3 verification/verify_news_readiness.py --selftest
python3 verification/verify_forecast_contracts.py --selftest
python3 verification/assert_readiness.py --gate F15  # must refuse (exit 2)
python3 verification/assert_readiness.py --gate BG   # must refuse (exit 2)
```

The source checks are intended to run on authorized DIAL VM topology. The portable scripts require Python standard library except forecast JSON-Schema fixture validation (`jsonschema`); no network or model training is required for document checks. A prepared lock and reproducible ZIP prove identity, not owner consent. Runtime certificates must be checked by the independent DIAL authority, not by trusting a supplied PASS field.

## Source availability

The complete Git repository and raw VM REA ledger are not duplicated in this ZIP. Exact source pins, bounded source evidence, a source collector, full portable REA research resources and the required VM evidence paths are included. `tools/collect_source_evidence.py` recreates the source blob/decision/checker archive from an already authorized exact checkout; it performs no fetch or mutation. Use the working source rather than reconstructing implementation from summaries.

The package has **not been committed to the working branch** in this consolidation. `CONSOLIDATION_APPLY_PROTOCOL.md` defines a single documentary admission path, preserving later commits and preventing old schedules from remaining operative. F15, actual code repairs and release remain distinct gated actions.
