# Mutation evidence correction

The hosted mutation job at run `39710993846`, job `119602030315`, reported success after the runner aborted on a stale `gateway.buildCommandBody` marker. Its last output was an AssertionError, not a completed mutation score. The pipeline's `tee` exit and step-level continue-on-error masked that distinction. Any earlier statement that this run proved the mutation suite passed is withdrawn. The Android runtime, build/lint and documentary results are unaffected.

Corrections preserve the existing job-level advisory policy while making its failed step visible. Shell pipefail preserves the underlying status, the step no longer overrides its own failure, and a read-only preflight validates the entire registry before any source edit. Both preflight output and execution output are retained as artifacts. The existing mutation harness now requires the unmutated control command to pass before applying mutations, so an import/collection/toolchain failure cannot count as a caught mutant. Its killed-process recovery test still verifies that a genuinely applied mutation is restored after SIGTERM.

The preflight retains **all 374 mutation cases / 376 edits**. It reports **36 findings**: 22 stale anchors, 11 missing source targets and three missing test targets. The source findings affect 32 distinct mutation descriptions. `MUTATION_REGISTRY_PREFLIGHT.json` contains every finding. No case was deleted, relabeled as passing or silently skipped. Preflight exits 2 and executes no mutations while these inputs are invalid.

These findings require semantic reconciliation of the legacy mutation registry against the current source and its preserved replacements. Missing anchors are instrument incompatibilities, not proof that a product invariant is missing. Each affected case must be retargeted with its original invariant preserved, replaced through reviewed equivalence, or explicitly dispositioned through the appropriate procedure. The complete mutation score remains unqualified; the independent preparation reviewer must consider this evidence limitation. The lead has not invented a retirement decision or a pass.

Verification of the correction: twenty focused regressions passed, including failing-control rejection, actual killed/surviving mutations in isolated temporary files, signal recovery, read-only preflight defects, and execution of the real CI shell with induced preflight and runner failures. The two failure paths retain exit 2 and exit 7 respectively instead of becoming success through tee. These are harness checks, not execution of the 374-case corpus.

```sh
python tools/rebuild/mutation_registry.py --check
# Current result: INVALID_REGISTRY, exit 2; findings retained, no source mutation.
python -m pytest -q tests/contracts/test_ci_mutation_status.py \
  tests/contracts/test_mutation_harness_recovers.py \
  tests/contracts/test_ci_workflow_is_what_it_claims.py \
  tests/rebuild/test_mutation_controls.py
```
