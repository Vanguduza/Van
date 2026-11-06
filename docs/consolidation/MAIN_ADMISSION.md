# Main admission prerequisites

PR #104 is the published consolidated source candidate. It is usable as the Rev1.18 development starting point, while canonical main admission remains separate.

GitHub currently runs `python trusted/tools/ci/project_truth_ledger.py ...` from main `8eb1889822fc8a83f219977c15340172e16acd91`. That file is absent on main, so the gate fails before evaluating this candidate. Existing PR #94 proposes the framework bootstrap. Its source instructions explicitly describe a one-time owner adoption, followed by trusted-base enforcement. This consolidation does not self-issue that adoption, code-owner review or an exception to a red check.

The reviewable admission sequence is:

1. Resolve the existing framework/bootstrap review and adopt it through its authorized native process. Preserve protections; do not run the candidate's checker as the trusted main authority.
2. Review and admit the additive authorization records separately from the code they authorize. `MAIN_AUTHORIZATION_INTAKE.json` identifies the 39 candidate records and their exact hashes at source head b147f531. This inventory issues no approval and changes no existing records. Recompute it if the source or base changes.
3. Re-evaluate PR #104 against that actual trusted base, including complete ledger verification, required checks and independent/code-owner review. Carry existing records unchanged; retain every source/runtime/owner gate and release restriction.
4. Merge only through the admitted process after required evidence passes. Do not force-push main, disable checks, alter history to hide missing rows, or manufacture owner/device signatures.

The local ledger checks prove candidate consistency and append-only provenance. They do not establish trusted-base admission. PRE/F15/BG certificates, production release/signing and S24 acceptance remain their own programme decisions. This is a repository admission checklist, not a replacement product DAG.
