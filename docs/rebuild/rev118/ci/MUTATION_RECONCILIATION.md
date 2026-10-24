# Legacy mutation reconciliation — 22 October 2026

Source candidate: `5d6372fdea20b31b300c32b66bb164904211bb0f`, PR #105.
This is verification maintenance on the inherited implementation. It does not issue
PRE-003, independent admission, product qualification or handset acceptance.

All **374 original case descriptions are preserved**, with a Counter comparison
against `e56a38c8`. The 32 cases named by the original preflight now target the
current implementations. The three test-path findings are resolved. The entire
registry has valid anchors and targets. Four workflow cases now change both the
live workflow and its exact template, giving **380 edits** across the same 374
cases. This prevents template-drift detection from falsely proving the APK oracle.

## Semantic equivalence

| Original concern | Current binding and invariant |
| --- | --- |
| C38 offline command reconstruction | Store the exact request prepared before dispatch; a newly assembled body cannot replace an uncertain original request. |
| C36 server admission and reconciliation | Refusal releases only the matching unfinished admission; unwired delegates are rejected before durable admission; resume reports held/result-pending work instead of UNKNOWN. |
| C26 conflicting payload | Atomic admission still refuses a changed payload under a known identity. Removing the digest comparison must fail the service/router conflict oracles. |
| C24 unsigned browser deployment | Signing-dependent interactive credential/effect routes stay absent without a signer. The five independently guarded file-provider routes remain intentionally visible. |
| C20 mission UI | The typed Work destination renders WorkRoute, has a primary navigation entry, binds actual mission results and saves expanded mission state. The retired module grid is not restored. |
| C19 Google and reasoning | Backend paths are rooted correctly. Runtime scope/approval checks and evidence-aware premise assessment remain the actual targets. |
| C15 Kotlin scanner | Mutations affect the current shared scanner's consumer binding, independently exposing names in line comments, KDoc and strings, or incorrectly erasing real code. The retired regex stripper is not recreated. |
| C12 APK availability | The current multiline APK/signing upload and assembled variant are checked, with the workflow and template kept mutually consistent during mutation. |
| C29 browser navigation | The strict public-URL parser and loopback-literal CDP endpoint boundary replace the old prefix checks; file URLs and arbitrary hostnames remain refused. |
| C40 socket/event handling | Boolean acknowledgements are recognized; socket pages merge into existing history through the current reducer binding. |
| C37 uncertain irreversible effect | The owner is told the response was lost, the action may already have happened and nothing was queued. Replacing this with a promise of replay must fail. The retained historical description does not establish that an unknown effect never happened. |
| C34 provisioning | The current GatewayBaseUrl parser is authoritative. Release rejects plain HTTP; loopback HTTP needs the explicit debug allowance. |

## Controls and evidence

`tools/rebuild/mutation_reconciliation.py` selects the 32 original finding identities
from the committed reference receipt, checks identity preservation and Python mutant
syntax, runs the existing journalled harness and records baseline results plus the
specific failing tests. Collection/dependency failures, Gradle compilation failures
and unrelated process errors cannot become `ASSERTION_DETECTED` in these receipts.

An initial attempt found one real test-quality gap: deleting Google's local status
guard survived because the canonical ActionRuntime independently refuses the same
execution. The added regression creates a real unapproved execution and asserts
that Google refuses before even requesting an execution transition or provider
effect. This proves Google's own boundary, while retaining the downstream guard.
The initial result is preserved; it is not rewritten as a pass.

That attempt also refused to run browser mutants in the backend environment, which
lacks media dependencies. No mutation was counted for that failed control. Browser
tests use the separate stream lock. CI now prepares Python, browser and Kotlin
environments independently and partitions the complete corpus exactly once. Kotlin
dependencies are resolved with a passing online control before offline mutation.
Advisory job policy is preserved; errors and survivors remain visible failures.

Final per-component execution receipts and hosted job outcomes are recorded beside
this document. The full 374-case corpus must finish before claiming a complete score;
valid input anchors or a passing subset cannot substitute for that result.

The first Kotlin attempt also rejected an invalid replacement that used the computed
`loaded` property as a constructor argument. Its compiler failure remains in
`MUTATION_RECONCILIATION_KOTLIN_INITIAL.json`, never counted as detected. The
replacement now uses the current `pagesApplied` constructor field. The shared runner
also rejects pytest collection/usage failures and Gradle compilation/setup failures.

Final local results: **32/32 assertion-detected**, zero survivors and zero invalid
final executions: 23 Python, two browser and seven Kotlin. Each component's unmodified
control passed. The source diff was empty after restoration and the journal absent.
`MUTATION_RECONCILIATION_MAPPING.json` binds every old/new definition, input hash and
execution receipt. Python/browser evidence is at `77e45b56`; their case definitions
and source/test bytes are identical at `5d6372fd`. Kotlin was rerun at `5d6372fd`.
Thirty-five focused harness/CI/recovery regressions and 52 isolated rebuild tests pass.

Full hosted run `39721114929` at `5d6372fd` passed three Kotlin shards (87 cases)
and the browser shard (26 cases), but correctly stopped the fourth Kotlin shard on
another invalid replacement: C35 referred to an unimported queue constant. The
replacement now uses its fully qualified name and its assertion is detected in
`MUTATION_FOLLOWUP_C35.json`. No compiler failure is counted as a detection.

The concurrent mission-creation repair adds a second safe return path behind the
database uniqueness fence. C11 therefore now removes both the optimistic lookup
and the unique index to exercise the original no-duplicate-mission invariant;
deleting the lookup alone is safely tolerated. Its assertion is detected in
`MUTATION_FOLLOWUP_C11.json`. All **374 identities remain**, now with **381 edits**.
Four Python, four Kotlin and one browser shard cover every case exactly once.
The complete updated-source score remains pending its own hosted execution.


## First complete corpus and follow-up

`MUTATION_CORPUS_fca473cc.json` verifies every original identity against all nine
terminal job logs: **371 detected / three survived / 374 executed**. This is a
failed full score, retained unchanged. Unknown-kind refusal now has two independent
guards, so C26 removes both to exercise actual unsafe routing. C18 and C15 needed
synthetic fixtures for ignored maturity classes and a graph with a test-only class;
the clean real inventories could not prove those checker branches worked. All
three repaired cases pass controls and detect their intended failures in the
corresponding `MUTATION_FOLLOWUP_*.json` receipts. No identity was deleted.

The current registry has 374 cases / 382 edits. Python groups now stay intact on
balanced runners (59/58/58/57 cases, eight controls each), avoiding four repeated
controls per group. Partition tests prove each case and Python control runs once.
Fresh-source full execution and independent semantic review remain separate.


## Final source verification

Run `39725953372` at source `c2a27848` / merge `9ae436ab` (identical source tree
`42e4a6b0`) passes **all 374 original mutation cases / 382 edits**, with zero
survivors. `MUTATION_CORPUS_c2a27848.json` compares every terminal log identity
against the registry and proves exact, once-only coverage. All nine shards pass;
no invalid control/collection/compiler failure became a detection. The earlier
371/374 result and failed attempts remain preserved. This closes the legacy
source-verification finding; independent review and Rev1.18 unit admission remain
separate. No original planned acceptance identity or native certificate is issued.
