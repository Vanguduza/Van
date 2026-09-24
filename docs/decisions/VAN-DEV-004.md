# VAN-DEV-004 — DIAL state → VAN semantics (§4) with JVM proof

Pack: `VAN-DEVCC` (VAN Development Control Centre) · Spec: `VAN-DEVCC-R1` (DIAL
`docs/dial/final-audit/06_DEVELOPMENT_SYSTEM/VAN_DEVELOPMENT_CONTROL_CENTRE_DESIGN_REV_1.md`, the
contract this unit implements; DIAL owns design and logic, VAN builds — owner decision OD-C).
Canonical repository: `Vanguduza/Van` · Baseline SHA at implementation: `be49e8e` (`main`).
Authority: VAN Project Truth (`docs/PROJECT_TRUTH_PROTOCOL.md`), design authority
`docs/design/VAN_PRODUCT_DESIGN_DNA.md` + `docs/design/COMPONENT_CATALOGUE.md`, gates V1–V8.

**Status:** IMPLEMENTED — not built on a device or by CI yet; owner signature PENDING.
**Depends on:** —.
**Branch:** `claude/busy-bardeen-sbfo2u-van-android` (not merged, not pushed).

## Scope (`VAN-DEVCC-R1` §4)

`com.dial.van.dialdev.DialDevSemantics` maps every DIAL task/stage state to `MissionStatus`, a DNA
status role and a caption, through exhaustive `when`s with no `else`. VAN's avatar is not bound
to DIAL state (§4 "Embodiment"): nothing here produces an embodiment signal.

| DIAL state | `MissionStatus` | Role | Caption |
|---|---|---|---|
| `NOT_APPLICABLE` | — (hidden in lists) | `disabled` | Not applicable |
| `BLOCKED` | `WAITING` | `deteriorating` | Blocked · {first blocker} |
| `READY` | `WAITING` | `monitor` | Ready |
| `RUNNING` | `RUNNING` | `engaged` | Running · {harness}/{model} |
| `WAITING_OWNER` | `WAITING` | `eventRisk` | Needs you |
| `WAITING_EXTERNAL` | `WAITING_EXTERNAL` | `hypothesis` | Waiting · {external} |
| `VERIFYING` | `RUNNING` | `cognition` | Verifying |
| `PASS` | `DONE` | `favourable` | Passed · evidence admitted |
| `FAIL` | `FAILED` | `critical` | Failed |
| `INVALIDATED` | `FAILED` | `deteriorating` | Invalidated · plan changed |
| `SUPERSEDED` | `DONE` | `disabled` | Superseded |
| Completion candidate | `RUNNING` | `cognition` | Claimed done · verifying |

## Requirements (each with its proof)

| ID | Requirement | Proven by |
|---|---|---|
| DEV4-R1 | Every row above, exactly | `DialDevSemanticsTest` · `every row of the section 4 table maps exactly` |
| DEV4-R2 | No `else`; a new DIAL state is a compile error | `the table covers every DIAL state this build knows…`; deleting a branch was shown to fail compilation |
| DEV4-R3 | A completion candidate (flag on RUNNING/VERIFYING/READY, or its own state name) never renders as passed; only the projection's `PASS` does | `a completion candidate never renders as passed`; `only the projection's own PASS reads passed…`; `DialDevModelsTest` · `the completion flag on a task row reads as claimed, not passed` |
| DEV4-R4 | An unknown state is shown as itself in `disabled`, never guessed | `an unknown state is shown as itself in the disabled role, not guessed` |
| DEV4-R5 | Smaller vocabularies (health, capability ladder, severity, admission, result, progress events) map onto DNA roles exhaustively; a candidate is never favourable | `the smaller vocabularies map onto DNA roles…`; `progress events map onto DNA roles…` |

## Must not

Add an `else` to a role mapping; derive "passed" from anything but the projection's `PASS`.

## Evidence recorded at implementation (container run, 2026-09-24)

| Instrument | Baseline (`be49e8e`) | After this unit group | Command |
|---|---|---|---|
| `android/verification` pure-JVM tests | 100 classes · 915 tests · 0 failed | 104 classes · 977 tests · 0 failed | `cd android/verification && gradle test` |
| `VanNavModelTest` (V1) | 16 tests | 23 tests | same run |
| `:visual-preview:test` (standalone harness, see below) | 5 classes · 24 tests · 0 failed | 6 classes · 28 tests · 0 failed | `gradle :visual-preview:test` |
| `tests/contracts` (pytest) | 527 passed · 3 skipped · 1 instrument failure¹ | 528 passed · 3 skipped | `python -m pytest tests/contracts` |
| `tools/audit/android_design_lint.py --baseline …` (V2) | 179 violations, all in baseline | 179 violations, all in baseline; 0 in new files | same |

¹ The baseline was run from a `git archive` export, which is not a git checkout;
`test_debug_signing_identity.py::test_no_signing_key_is_committed_to_this_repository` needs one.
That is the instrument, not the code; on the real checkout the suite passes.

Gates broken on purpose to prove they bite (each reverted): a completion candidate captioned
"Passed" → 5 tests fail; dev routes parented to Home → 1 fails; stale threshold ignored → 3 fail;
forwarder's `APPLIED` trusted on 202 → 1 fails; action built with no revision → 1 fails; a §4
`when` branch deleted → compile error "'when' expression must be exhaustive".

**Not run here, and not claimed:** `./gradlew :app:testDebugUnitTest :app:assembleDebug
:app:lintDebug` and the in-tree `./gradlew :visual-preview:*`. The Android Gradle Plugin and SDK
come from `dl.google.com`, which this container's egress proxy refuses (`CONNECT tunnel failed,
response 403`), so the app module cannot be configured. Substitute evidence, stated as such:
(a) the pure half compiles and runs in `android/verification`; (b) every new Compose file under
`command/dev/**` plus `design/**`, `dialdev/**` and `VanRoute.kt` compiles (Kotlin 1.9.24 + Compose
compiler 1.5.14) against Compose Multiplatform desktop 1.6.11 with minimal Android/navigation stubs
in a local-only harness, which was shown to fail on an induced type error and an induced
`@Composable`-context error; (c) `visual-preview` built and tested through a standalone settings
file that includes only that module. CI's `android-and-visual-evidence` job is the real gate.

```yaml
owner_signature_status: PENDING
owner_signature_evidence_ref: null
implemented_by: agent (W5, Claude) — an agent may not sign this record
```
