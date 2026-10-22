# Mutation evidence correction

The hosted mutation job at run `39710993846`, job `119602030315`, reported success after the runner aborted on a stale `gateway.buildCommandBody` marker. Its last output was an AssertionError, not a completed mutation score. The pipeline's `tee` exit and step-level continue-on-error masked that distinction. Any earlier statement that this run proved the mutation suite passed is withdrawn. The Android runtime, build/lint and documentary results are unaffected.

Corrections preserve the existing job-level advisory policy while making its failed step visible. Shell pipefail preserves the underlying status, the step no longer overrides its own failure, and a read-only preflight validates the entire registry before any source edit. Both preflight output and execution output are retained as artifacts. The existing mutation harness now requires the unmutated control command to pass before applying mutations, so an import/collection/toolchain failure cannot count as a caught mutant. Its killed-process recovery test still verifies that a genuinely applied mutation is restored after SIGTERM.

At `e56a38c8`, the preflight retained **all 374 mutation cases / 376 edits** and reported **36 findings**: 22 stale anchors, 11 missing source targets and three missing test targets. The source findings affected 32 distinct mutation descriptions. `MUTATION_REGISTRY_PREFLIGHT.json` preserves that original finding receipt. No case was deleted, relabeled as passing or silently skipped.

These findings required semantic reconciliation against the preserved current implementations. That work is now source-tested in `MUTATION_RECONCILIATION.md`: all 374 identities remain, all 32 retargeted cases are assertion-detected after passing controls, and the current preflight has no findings. Four cases now mutate both workflow copies to avoid a misleading template-drift oracle (380 edits). No case was retired. The complete corpus score remains unqualified pending the full hosted run; independent semantic review is still separate.

Verification of the correction: twenty focused regressions passed, including failing-control rejection, actual killed/surviving mutations in isolated temporary files, signal recovery, read-only preflight defects, and execution of the real CI shell with induced preflight and runner failures. The two failure paths retain exit 2 and exit 7 respectively instead of becoming success through tee. These are harness checks, not execution of the 374-case corpus.

```sh
python tools/rebuild/mutation_registry.py --check
# Current: exit 0, valid anchors/targets only; execution evidence is separate.
python -m pytest -q tests/contracts/test_ci_mutation_status.py \
  tests/contracts/test_mutation_harness_recovers.py \
  tests/contracts/test_ci_workflow_is_what_it_claims.py \
  tests/rebuild/test_mutation_controls.py
```
