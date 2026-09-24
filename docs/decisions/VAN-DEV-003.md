# VAN-DEV-003 — Routes, navigation, deep links and `PARENTS`

Pack: `VAN-DEVCC` (VAN Development Control Centre) · Spec: `VAN-DEVCC-R1` (DIAL
`docs/dial/final-audit/06_DEVELOPMENT_SYSTEM/VAN_DEVELOPMENT_CONTROL_CENTRE_DESIGN_REV_1.md`, the
contract this unit implements; DIAL owns design and logic, VAN builds — owner decision OD-C).
Canonical repository: `Vanguduza/Van` · Baseline SHA at implementation: `be49e8e` (`main`).
Authority: VAN Project Truth (`docs/PROJECT_TRUTH_PROTOCOL.md`), design authority
`docs/design/VAN_PRODUCT_DESIGN_DNA.md` + `docs/design/COMPONENT_CATALOGUE.md`, gates V1–V8.

**Status:** IMPLEMENTED — not built on a device or by CI yet; owner signature PENDING.
**Depends on:** —.
**Branch:** `claude/busy-bardeen-sbfo2u-van-android` (not merged, not pushed).

## Scope (`VAN-DEVCC-R1` §2.1, §7)

The Development Control Centre becomes routes *inside* Work. DNA §4's eight destinations stay
eight (`PRIMARY` and `MORE` are untouched and pinned by `tests/contracts/test_android_dashboard_navigation.py`).

## Requirements (each with its proof)

| ID | Requirement | Proven by |
|---|---|---|
| DEV3-R1 | The fifteen §2.1 templates exist as `VanRoute` constants: `work/dev?project={project}`, `work/dev/{projectId}/plan`, `work/dev/{projectId}/tasks?view={view}`, `work/dev/{projectId}/graph`, `work/dev/tasks/{taskId}`, `work/dev/agents`, `work/dev/workspaces`, `work/dev/workspaces/{workspaceId}`, `work/dev/research`, `work/dev/design`, `work/dev/ci`, `work/dev/security`, `work/dev/reviews`, `work/dev/memory`, `work/dev/evidence/{evidenceRef}` | `VanNavModelTest` · `the development templates are exactly the fifteen section 2_1 names, all registered` |
| DEV3-R2 | `ALL_TEMPLATES` includes them (`+ DEV_TEMPLATES`) and the one `NavHost` registers each | same test; `command/dev/DevNavGraph.kt` registers `DEV_TEMPLATES` in order, called from `CommandCentreActivity`'s `NavHost` |
| DEV3-R3 | `PARENTS` maps every `work/dev/**` to `work`; none is primary or "More" | `every work-dev route's parent is Work, and none is a new destination` |
| DEV3-R4 | Deep links are `van://work/dev/...`; only a query the template declares (`view`, `project`) survives | `development deep links use the van scheme and keep only declared queries`; the pre-existing `deepLink ignores a trailing query string` still passes |
| DEV3-R5 | When two templates fit one path, a literal segment beats a placeholder | `a literal segment beats a placeholder when two development templates both fit` |
| DEV3-R6 | Entry points: Work shows "Development — …" (`WorkRoute.onOpenDevelopment`); `projects/{projectId}` shows a "Development" section (`DevProjectSection`) that opens `work/dev?project={id}`; Attention opens a `dial-dev` item's `payload.deep_link` | code: `WorkRoute.kt`, `ProjectDetailRoute.kt`, `AttentionRoute.kt`; call shapes compiled in the typecheck harness |
| DEV3-R7 | Process-death restore keeps a development route | `restore keeps a development route across process death` |

## Known limitation (stated, not hidden)

A DIAL project whose id is literally `tasks`, `workspaces` or `evidence` cannot address its own
plan/tasks/graph routes by path (the literal template wins); it remains reachable through the hub
(`work/dev?project=…`). Pinned in `VanRoute.templateFor`'s KDoc.

## Must not

Add a ninth destination; change `PRIMARY`/`MORE`; register a dev route outside `DEV_TEMPLATES`.

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
