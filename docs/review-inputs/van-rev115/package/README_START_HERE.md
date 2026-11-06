> Active delivery is Rev1.18 (21 October 2026). Start at `VAN_NEXT_UNIFIED_REBUILD_BLUEPRINT_REV1_18_20261021.md` and `contracts/whole_product/ARCHITECTURE_REV118.md`; execute acceptance from `verification/EFFECTIVE_TEST_CONTRACTS_REV118.json`. This header supersedes older entrypoint/revision references below; historical findings and financial gates remain applicable.

# VAN Next hardened self-improvement blueprint — Rev1.17

Start with `CANONICAL_AUTHORITY.json`. The active master is `VAN_NEXT_UNIFIED_REBUILD_BLUEPRINT_REV1_17_20261018.md`; the focused specification is `VATI_SELF_OPTIMIZING_EXECUTION_AND_CRYPTO_BLUEPRINT_REV5_20261018.md`. Normative §8.6 defines experience learning; §8.7 hardens Jev/model use and profitability research. The single schedule is `plan/DEVELOPMENT_PLAN.json`, rendered as `plan/VAN_NEXT_DETERMINISTIC_PLAN_REV1_17.md`.

Active scope: **324 requirements / 1,610 planned application tests**. All 316 Rev1.16 requirement objects and 1,586 test objects are unchanged; eight hardening requirements and 24 positive/adverse/recovery contracts are added. All 131 unit identities/dependencies, 234 context objects, 349 actions and locked visuals remain. Application contracts remain NOT_RUN and F15/BG remain NOT_ISSUED.

Read `research/REV117_MODEL_AND_PROFITABILITY_REVIEW.md` for verified Gemini 4 Argon and DeepSeek identities, cost arithmetic, exact source findings, the recommended comparison and its limitations. `research/PROFITABILITY_EXPERIMENTS.json` registers six experiment templates, all NOT_RUN. `contracts/self_optimization/MODEL_USE_CONTRACT.json` and its strict schema define required identity, calibration, budget and qualification boundaries. `design/MODEL_HARDENING_CONTEXT_BINDINGS.json` extends five existing contexts through the main registry; no new global screen or service is mandated.

Bounded source review executed two pure-function/property counterexamples and one static call-order probe. These establish specific source shortcomings; they are not application e2e tests or fixes. This revision changes documents and documentary verification only. No model API inference, paid study, backtest, deployment or handset acceptance ran. Model/provider documentation is not proof of financial edge or account access. Preserve exact native authority and all prior required integrations.

Verification (Python 3 and jsonschema):

```sh
python3 -B plan/render_plan.py --check
python3 -B verification/verify_rev117.py --json
python3 -B verification/verify_rev117.py --selftest --json
python3 -B verification/verify_review_contracts.py
python3 -B verification/verify_experience_learning.py
python3 -B verification/verify_model_hardening.py
python3 -B verification/verify_rev117.py --check-package --json
```

Current documentary receipts are in `evidence/rev117/final_checks/`; source probes are separately labeled in `evidence/rev117/source_probes.json`. Older checkers/blueprints/receipts retain historical scope. The prior Rev1.16 package is preserved at Git commit `874774d4ece98718f4d3e80002ec136320a84e13`; exact inherited objects are bound by `lineage/REV116_OBJECT_FINGERPRINTS.json`. No new all-branch audit or native qualification is claimed.
