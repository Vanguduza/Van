# Rev1.15 corrective delivery 1.15.1

Owner instruction: “Do the corrective work”, following review of Opus’s findings. This corrects published commit b5f56ebbc056bbd8eb3e9f7a562a8cd5d5b74bdf without changing product scope, test objects, unit dependencies, application code or certificate states.

- Correct the plan preservation summary and both blueprints’ active §16 totals to 309 requirements and 1,544 tests. Explicitly distinguish 301/1,520 preserved Rev1.14 objects from eight/24 additions. Label inherited Rev1.13 counts historical.
- Generate acceptance_test_ids on every plan unit from verification/TEST_CONTRACTS.json, including primary and additional unit assignments. The renderer consumes these explicit references and rejects stale, missing, extra or misassigned lists. The registry remains the sole owner of test definitions and execution_state.
- Keep every existing execution_state: NOT_RUN unchanged. All 1,544 tests already had this field; no duplicate status/state field is introduced.
- Retain the TCA finding as an incorrect decomposition, not a universal assertion that spread is always counted twice. The source omits arrival-to-submitted movement and substitutes half spread; its error depends on price conventions. No application repair is claimed.
- Rebuild unsigned fingerprints, rendered plan, manifest, ZIP and verification receipts. The earlier ZIP (SHA-256 889b9f910e45b17403bfaac23547ed0ca9799a991f46ec4019ca02951b3a1ce7) remains available at the preceding Git commit. The corrected ZIP has its own filename and identity.

Regression checks deliberately remove, duplicate, invent and move test references, and restore stale counts. These must fail independently of the unsigned scope lock. No F15, BG, runtime qualification or economic result is issued.
