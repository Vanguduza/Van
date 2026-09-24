# VAN-DEV-007 — Active Agents + Orca Workspaces (diff, terminal tail)

Pack: `VAN-DEVCC` (VAN Development Control Centre) · Spec: `VAN-DEVCC-R1` (DIAL
`docs/dial/final-audit/06_DEVELOPMENT_SYSTEM/VAN_DEVELOPMENT_CONTROL_CENTRE_DESIGN_REV_1.md`, the
contract this unit implements; DIAL owns design and logic, VAN builds — owner decision OD-C).
Canonical repository: `Vanguduza/Van` · Baseline SHA at implementation: `be49e8e` (`main`).
Authority: VAN Project Truth (`docs/PROJECT_TRUTH_PROTOCOL.md`), design authority
`docs/design/VAN_PRODUCT_DESIGN_DNA.md` + `docs/design/COMPONENT_CATALOGUE.md`, gates V1–V8.

**Status:** IMPLEMENTED — not built on a device or by CI yet; owner signature PENDING.
**Depends on:** VAN-DEV-005.
**Branch:** `claude/busy-bardeen-sbfo2u-van-android` (not merged, not pushed).

## Scope (`VAN-DEVCC-R1` §6.5, §6.6, §5)

| Route | File | `@DataSource` |
|---|---|---|
| `work/dev/agents` | `DevAgentsRoute.kt` | `GET /v1/dial-dev/agents` |
| `work/dev/workspaces` | `DevWorkspacesRoute.kt` | `GET /v1/dial-dev/workspaces` |
| `work/dev/workspaces/{workspaceId}` | `DevWorkspacesRoute.kt` | `GET /v1/dial-dev/workspaces/{id}`, `…/{id}/diff`, `…/{id}/terminal-tail?lines=200` |

- Agents: one panel per actor — objective, intent (paths/commands/tests), owned paths, next
  action, heartbeat, blockers. Overlap warnings: DIAL's when sent; otherwise derived from declared
  intents (equal or nested paths, never mere string prefixes) and labelled "derived … leases
  prevent real overlap" (`FindingCard`).
- Workspaces: 10 s stale threshold. Detail tabs Overview · Diff · Terminal · Evidence; the task
  action bar (VAN-DEV-009); **no raw Orca control**.
- Diff: file list first; a file's hunks are split out of the unified diff only when opened;
  "above DIAL's size bound → file list only" is said, not hidden.
- Terminal tail: **read-only, monospace, ≤ 200 lines (enforced client-side too), redacted spans
  marked in the `eventRisk` role and announced as "redacted", no input box anywhere**.

## Proof

`DialDevModelsTest`: diff split, 200-line bound, marker and range redaction (a redacted range is
never reconstructed), reported vs derived overlaps, sibling-prefix non-overlap. V6 sheets.

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
