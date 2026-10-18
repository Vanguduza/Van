# VAN Next reviewed specification candidate — Rev1.15 (corrective delivery 1.15.1)

Start with `CANONICAL_AUTHORITY.json`, then `review/INDEPENDENT_AUDIT.md`.

The single master is `VAN_NEXT_UNIFIED_REBUILD_BLUEPRINT_REV1_15_20261018.md`; focused architecture is `VATI_SELF_OPTIMIZING_EXECUTION_AND_CRYPTO_BLUEPRINT_REV3_20261018.md`. The only active implementation schedule is `plan/DEVELOPMENT_PLAN.json`, rendered as `plan/VAN_NEXT_DETERMINISTIC_PLAN_REV1_15.md`.

This proposal preserves all 301 previous requirement objects, all 1,520 previous application test contracts, all 131 unit IDs, 234 context objects and 349 owner actions. It adds eight precise requirements and 24 acceptance contracts: totals 309 / 1,544. All application acceptance is NOT_RUN. No app source was changed, no merge was performed, no economic backtest or provider execution ran, and no F15/BG was issued.

Review proposals and measured-versus-expected evidence: `review/DESIGN_CHANGE_PROPOSALS.json`. Source preservation: `review/SOURCE_ADMISSION_CROSSWALK.json` plus original admission/crosswalk files. Complexity and ablation: `review/COMPLEXITY_AND_ABLATION_REGISTER.json`. Research prerequisites/outputs: `review/EVALUATION_PROTOCOL.md`. Frontend impact: `review/FRONTEND_IMPACT.md` and preserved `design/` registry.

The exact supplied parent ZIP is `lineage/REV1_14_EXACT_PARENT.zip`. Historical receipts retain their own source/date/scope and are not current application evidence. Current review receipts are only under `evidence/rev115/`.

Global DIAL is explicitly owner-authorized, but no callable DIAL/Commander tool or configured connection was available during this session. HTTPS Git source discovery succeeded. Native project/deployment identity, current runtime gates and independent admission remain unverified; this is not a request for repeat permission.

Documentary verification (Python 3 and jsonschema):

```sh
python3 -B plan/render_plan.py --check
python3 -B verification/verify_rev115.py --json
python3 -B verification/verify_rev115.py --selftest --json
python3 -B verification/verify_review_contracts.py
python3 -B verification/verify_rev115.py --check-package --json
```

These commands validate documents and reference fixtures only. The revised lifecycle and record schema v2 are proposed contracts, not deployed migrations. Native schema/version compatibility and signed authority are required in implementation.

Correction details: `review/REV115_CORRECTIONS.md`. Unit acceptance references are generated with `python3 -B plan/render_plan.py --sync-acceptance`; refresh unsigned fingerprints before rendering. `--check` rejects stale references or scope totals.
